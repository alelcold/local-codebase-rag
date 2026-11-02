"""FastAPI app: /health, /index, /index/status, /query, /query/stream."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .config import get_settings
from .rag import OllamaTimeoutError, RagService
from .services import Services, build_services, check_ollama, check_qdrant

log = logging.getLogger(__name__)


class IndexRequest(BaseModel):
    full: bool = Field(False, description="Drop the collection and rebuild everything")
    wait: bool = Field(False, description="Block until indexing finishes (default: run in background)")


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    top_k: int | None = Field(None, ge=1, le=30)


def timeout_detail(exc: OllamaTimeoutError) -> str:
    stage = "產生向量（embedding）" if exc.stage == "embedding" else "生成回答"
    return f"Ollama {stage}逾時：超過 {exc.timeout:g} 秒仍未回應（{exc.setting}）"


def sse(event: str, data: object) -> str:
    """One Server-Sent Events frame. JSON never contains a raw newline, so one data line is enough."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


_END = object()


async def stream_answer(
    rag: RagService, question: str, top_k: int | None, heartbeat_seconds: float
) -> AsyncIterator[str]:
    """Run the blocking RAG pipeline in a worker thread and relay its events as SSE.

    Events, in order: ``sources`` → ``token``* → ``done``, or ``error`` at any
    point. ``heartbeat`` is sent whenever nothing else was sent for
    ``heartbeat_seconds`` (retrieval and prompt processing can be silent for a
    long time on CPU), so idle-timeout proxies keep the connection open.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[object] = asyncio.Queue()
    cancelled = threading.Event()
    started = time.monotonic()

    def put(item: object) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, item)
        except RuntimeError:  # event loop already closed: the client is gone
            cancelled.set()

    def produce() -> None:
        events = rag.stream(question, top_k)
        try:
            for event in events:
                if cancelled.is_set():
                    break
                put(event)
        except Exception as exc:  # reported to the client as an error event
            put(exc)
        finally:
            events.close()  # closes the Ollama HTTP stream if we stopped early
            put(_END)

    threading.Thread(target=produce, name="query-stream", daemon=True).start()
    # Sent right away: response headers and the first bytes reach the browser
    # before any slow work starts.
    yield sse("heartbeat", {"elapsed_seconds": 0.0})
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
            except asyncio.TimeoutError:
                yield sse("heartbeat", {"elapsed_seconds": round(time.monotonic() - started, 1)})
                continue
            if item is _END:
                return
            if isinstance(item, OllamaTimeoutError):
                log.warning("Streaming query timed out: %s", item)
                yield sse("error", {"kind": "timeout", "stage": item.stage, "detail": timeout_detail(item)})
            elif isinstance(item, Exception):
                log.error("Streaming query failed", exc_info=item)
                yield sse("error", {"kind": "error", "detail": f"{type(item).__name__}: {item}"})
            else:
                yield sse(item.kind, item.data)  # type: ignore[attr-defined]
    finally:
        # Normal end, or the client disconnected (generator closed / cancelled).
        cancelled.set()


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
            "top_k": s.top_k,
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
        except OllamaTimeoutError as exc:
            # 504 (not 502) so the UI can explain timeouts separately from crashes.
            log.warning("Query timed out: %s", exc)
            raise HTTPException(status_code=504, detail=timeout_detail(exc)) from exc
        except Exception as exc:
            log.exception("Query failed")
            raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from exc

    @app.post("/query/stream")
    async def query_stream(req: QueryRequest) -> StreamingResponse:
        """Like /query, but streamed as Server-Sent Events (see ``stream_answer``).

        Errors after the stream has started arrive as an ``error`` event, since
        the 200 status line has already been sent.
        """
        question = req.question.strip()
        if not question:
            raise HTTPException(status_code=422, detail="question must not be blank")
        s = svc()
        return StreamingResponse(
            stream_answer(s.rag, question, req.top_k, s.settings.stream_heartbeat_seconds),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                # Tells nginx (and compatible proxies) not to buffer this response.
                "X-Accel-Buffering": "no",
            },
        )

    return app


app = create_app()
