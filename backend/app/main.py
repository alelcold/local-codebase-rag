"""FastAPI app: /health, /index, /index/status, /query."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import get_settings
from .services import Services, build_services, check_ollama, check_qdrant

log = logging.getLogger(__name__)


class IndexRequest(BaseModel):
    full: bool = Field(False, description="Drop the collection and rebuild everything")
    wait: bool = Field(False, description="Block until indexing finishes (default: run in background)")


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    top_k: int | None = Field(None, ge=1, le=30)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class IndexJob:
    """One indexing run at a time; status is kept in memory for the UI to poll."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.state = "idle"  # idle | running | done | error
        self.full = False
        self.started_at: str | None = None
        self.finished_at: str | None = None
        self.progress: list[str] = []
        self.report: dict | None = None
        self.error: str | None = None

    def snapshot(self) -> dict:
        return {
            "state": self.state,
            "full": self.full,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "recent_progress": self.progress[-20:],
            "report": self.report,
            "error": self.error,
        }

    def try_start(self, full: bool) -> bool:
        with self._lock:
            if self.state == "running":
                return False
            self.state, self.full = "running", full
            self.started_at, self.finished_at = _now(), None
            self.progress, self.report, self.error = [], None, None
            return True

    def execute(self, run: Callable[..., object]) -> None:
        try:
            report = run(full=self.full, progress=self.progress.append)
            self.report = report.to_dict()  # type: ignore[attr-defined]
            self.state = "done"
        except Exception as exc:
            log.exception("Indexing failed")
            self.error = f"{type(exc).__name__}: {exc}"
            self.state = "error"
        finally:
            self.finished_at = _now()


def create_app(services: Services | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if getattr(app.state, "services", None) is None:
            app.state.services = build_services()
        yield

    app = FastAPI(title="Local Codebase RAG", version="1.0.0", lifespan=lifespan)
    app.state.services = services
    app.state.index_job = IndexJob()

    origins = (services.settings if services else get_settings()).cors_origin_list
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])

    def svc() -> Services:
        return app.state.services

    @app.get("/health")
    def health() -> dict:
        ollama = check_ollama(svc())
        qdrant = check_qdrant(svc())
        s = svc().settings
        return {
            "status": "ok" if ollama["ok"] and qdrant["ok"] else "degraded",
            "ollama": ollama,
            "qdrant": qdrant,
            "codebase_path": s.codebase_path,
            "index_job": app.state.index_job.state,
        }

    @app.post("/index")
    def index(req: IndexRequest | None = None) -> dict:
        req = req or IndexRequest()
        job: IndexJob = app.state.index_job
        if not job.try_start(req.full):
            raise HTTPException(status_code=409, detail="Indexing is already running")
        if req.wait:
            job.execute(svc().indexer.run)
            if job.state == "error":
                raise HTTPException(status_code=500, detail=job.error)
        else:
            threading.Thread(target=job.execute, args=(svc().indexer.run,), daemon=True).start()
        return job.snapshot()

    @app.get("/index/status")
    def index_status() -> dict:
        return app.state.index_job.snapshot()

    @app.post("/query")
    def query(req: QueryRequest) -> dict:
        question = req.question.strip()
        if not question:
            raise HTTPException(status_code=422, detail="question must not be blank")
        try:
            return svc().rag.answer(question, req.top_k).to_dict()
        except Exception as exc:
            log.exception("Query failed")
            raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from exc

    return app


app = create_app()
