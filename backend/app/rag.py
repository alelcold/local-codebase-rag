"""Retrieval + answer generation with file/line citations."""

from __future__ import annotations

from dataclasses import asdict, dataclass

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


class RagService:
    def __init__(self, settings: Settings, store: CodeVectorStore, embed_model: BaseEmbedding, llm: LLM):
        self.settings = settings
        self.store = store
        self.embed_model = embed_model
        self.llm = llm

    def retrieve(self, question: str, top_k: int | None = None) -> list[Source]:
        k = top_k or self.settings.top_k
        embedding = self.embed_model.get_query_embedding(f"{self.settings.query_prefix}{question}")
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

    def answer(self, question: str, top_k: int | None = None) -> QueryResult:
        if not self.store.exists():
            return QueryResult(answer=NO_INDEX_ANSWER, sources=[])
        sources = self.retrieve(question, top_k)
        if not sources:
            return QueryResult(answer=NO_MATCH_ANSWER, sources=[])
        response = self.llm.complete(build_prompt(question, sources))
        return QueryResult(answer=response.text.strip(), sources=sources)
