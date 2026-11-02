"""Retrieval + answer generation with file/line citations."""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass

import httpx
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.llms import LLM

from .config import Settings
from .store import CodeVectorStore

SYSTEM_PROMPT = """You are a senior engineer helping a team understand a game front-end codebase.
Answer ONLY from the code excerpts provided. Rules:
- Cite every claim with the excerpt number and location, e.g. [2] src/game/Player.ts:12-30.
- If the excerpts do not contain the answer, say so plainly and suggest what to search for instead. Never invent files, functions or line numbers.
- Quote short code snippets in fenced code blocks when they help.
- Reply in the same language as the question (for Traditional Chinese questions, answer in Traditional Chinese)."""

NO_INDEX_ANSWER = "目前還沒有任何索引資料。請先執行索引（介面上的「更新索引」按鈕，或 scripts/index.sh）。"
NO_MATCH_ANSWER = "在目前的索引中找不到與這個問題相關的程式碼。"


class OllamaTimeoutError(Exception):
    """Ollama did not answer within the configured timeout.

    ``stage`` is ``"embedding"`` or ``"llm"`` so the API can tell the user which
    setting to raise (EMBED_REQUEST_TIMEOUT or LLM_REQUEST_TIMEOUT).
    """

    def __init__(self, stage: str, timeout: float, setting: str):
        self.stage = stage
        self.timeout = timeout
        self.setting = setting
        super().__init__(f"Ollama {stage} request timed out after {timeout:g}s ({setting})")


def is_timeout(exc: BaseException) -> bool:
    """True if ``exc`` or anything it was raised from is an HTTP timeout."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        if isinstance(current, (httpx.TimeoutException, TimeoutError)):
            return True
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return False


@dataclass
class Source:
    ref: int
    file_path: str
    start_line: int
    end_line: int
    symbol: str
    kind: str
    language: str
    score: float
    text: str

    @property
    def location(self) -> str:
        return f"{self.file_path}:{self.start_line}-{self.end_line}"


@dataclass
class QueryResult:
    answer: str
    sources: list[Source]

    def to_dict(self) -> dict:
        return {"answer": self.answer, "sources": [asdict(s) for s in self.sources]}


def build_prompt(question: str, sources: list[Source]) -> str:
    blocks = []
    for s in sources:
        title = f"[{s.ref}] {s.location}"
        if s.symbol:
            title += f" ({s.kind} {s.symbol})"
        fence_lang = "md" if s.language == "markdown" else s.language
        blocks.append(f"{title}\n```{fence_lang}\n{s.text}\n```")
    context = "\n\n".join(blocks)
    return f"{SYSTEM_PROMPT}\n\n## Code excerpts\n\n{context}\n\n## Question\n\n{question}\n\n## Answer\n"


@dataclass
class StreamEvent:
    """One step of a streamed answer.

    ``kind`` is ``"sources"`` (data: list of source dicts), ``"token"`` (data:
    ``{"text": ...}``) or ``"done"`` (data: timing stats). Errors are raised,
    not yielded, so the caller decides how to report them.
    """

    kind: str
    data: object


class RagService:
    def __init__(self, settings: Settings, store: CodeVectorStore, embed_model: BaseEmbedding, llm: LLM):
        self.settings = settings
        self.store = store
        self.embed_model = embed_model
        self.llm = llm

    def retrieve(self, question: str, top_k: int | None = None) -> list[Source]:
        k = top_k or self.settings.top_k
        try:
            embedding = self.embed_model.get_query_embedding(f"{self.settings.query_prefix}{question}")
        except Exception as exc:
            if is_timeout(exc):
                s = self.settings
                raise OllamaTimeoutError("embedding", s.embed_request_timeout, "EMBED_REQUEST_TIMEOUT") from exc
            raise
        results = self.store.query(embedding, k)
        sources = []
        for ref, hit in enumerate(results, start=1):
            meta = hit.node.metadata
            sources.append(
                Source(
                    ref=ref,
                    file_path=meta.get("file_path", "?"),
                    start_line=int(meta.get("start_line", 0)),
                    end_line=int(meta.get("end_line", 0)),
                    symbol=meta.get("symbol", ""),
                    kind=meta.get("kind", ""),
                    language=meta.get("language", ""),
                    score=round(float(hit.score or 0.0), 4),
                    text=hit.node.get_content(),
                )
            )
        return sources

    def _llm_timeout(self, exc: BaseException) -> OllamaTimeoutError | None:
        if not is_timeout(exc):
            return None
        return OllamaTimeoutError("llm", self.settings.llm_request_timeout, "LLM_REQUEST_TIMEOUT")

    def answer(self, question: str, top_k: int | None = None) -> QueryResult:
        if not self.store.exists():
            return QueryResult(answer=NO_INDEX_ANSWER, sources=[])
        sources = self.retrieve(question, top_k)
        if not sources:
            return QueryResult(answer=NO_MATCH_ANSWER, sources=[])
        try:
            response = self.llm.complete(build_prompt(question, sources))
        except Exception as exc:
            timeout = self._llm_timeout(exc)
            if timeout:
                raise timeout from exc
            raise
        return QueryResult(answer=response.text.strip(), sources=sources)

    def stream(self, question: str, top_k: int | None = None) -> Iterator[StreamEvent]:
        """Same pipeline as :meth:`answer`, but yields as soon as each part is ready:
        the retrieved sources first, then the answer token by token, then stats.

        Sources go first because retrieval takes seconds while generation can
        take minutes on CPU: the user can start reading the cited files while
        the model is still thinking (ADR 0010).
        """
        started = time.monotonic()
        stats: dict[str, float | int | None] = {
            "retrieval_seconds": None,
            "first_token_seconds": None,
            "total_seconds": None,
            "tokens": 0,
            "answer_chars": 0,
        }

        def finish() -> StreamEvent:
            stats["total_seconds"] = round(time.monotonic() - started, 3)
            return StreamEvent("done", stats)

        def canned(text: str) -> Iterator[StreamEvent]:
            stats["retrieval_seconds"] = round(time.monotonic() - started, 3)
            yield StreamEvent("sources", [])
            stats["first_token_seconds"] = stats["retrieval_seconds"]
            stats["tokens"], stats["answer_chars"] = 1, len(text)
            yield StreamEvent("token", {"text": text})
            yield finish()

        if not self.store.exists():
            yield from canned(NO_INDEX_ANSWER)
            return
        sources = self.retrieve(question, top_k)
        if not sources:
            yield from canned(NO_MATCH_ANSWER)
            return
        stats["retrieval_seconds"] = round(time.monotonic() - started, 3)
        yield StreamEvent("sources", [asdict(s) for s in sources])

        text_so_far = ""
        raw_chars = 0  # length of chunk.text seen so far, before stripping
        try:
            for chunk in self.llm.stream_complete(build_prompt(question, sources)):
                # Ollama sends the new text in ``delta``; fall back to diffing
                # the accumulated ``text`` for LLMs that only fill that in.
                delta = chunk.delta if chunk.delta is not None else chunk.text[raw_chars:]
                raw_chars += len(delta)
                if not delta:
                    continue
                if not text_so_far:
                    # The model often starts with whitespace or a newline.
                    delta = delta.lstrip()
                    if not delta:
                        continue
                    stats["first_token_seconds"] = round(time.monotonic() - started, 3)
                text_so_far += delta
                stats["tokens"] = int(stats["tokens"] or 0) + 1
                yield StreamEvent("token", {"text": delta})
        except Exception as exc:
            timeout = self._llm_timeout(exc)
            if timeout:
                raise timeout from exc
            raise
        stats["answer_chars"] = len(text_so_far)
        yield finish()
