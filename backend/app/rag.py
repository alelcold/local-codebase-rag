"""Retrieval + answer generation with file/line citations."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field

import httpx
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.llms import LLM
from llama_index.core.schema import BaseNode

from .config import Settings, is_doc_path
from .rerank import Reranker, rerank_order
from .retrieval import KeywordIndex, contains_identifier, extract_identifiers, rrf, split_select
from .store import CodeVectorStore

SYSTEM_PROMPT = """You are a senior engineer helping a team understand a game front-end codebase.
Answer ONLY from the code excerpts provided. Rules:
- Cite every claim with the excerpt number and location, e.g. [2] src/game/Player.ts:12-30.
- If the excerpts do not contain the answer, say so plainly and suggest what to search for instead. Never invent files, functions or line numbers.
- Quote short code snippets in fenced code blocks when they help.
- Reply in the same language as the question (for Traditional Chinese questions, answer in Traditional Chinese)."""

# PROMPT_VARIANT=v2 (ADR 0013): always Traditional Chinese (small models drift
# into Simplified Chinese or English otherwise), and lead with where the code
# is, because "where is X configured?" is the most common question and the
# docs that merely mention X used to be cited instead of the code defining it.
SYSTEM_PROMPT_V2 = """你是資深工程師，協助團隊理解一個遊戲前端專案的程式碼。只能根據下方提供的片段回答。規則：
- 一律使用繁體中文（台灣用語）回答，不要使用簡體字。程式碼識別字、檔名維持原文。
- 先說明程式碼位置：第一段就指出相關的檔案與行號，格式如 [2] src/game/Player.ts:12-30，並寫出關鍵的常數、函式或 class 名稱與數值。
- 優先引用標示為「程式碼」的片段；標示為「文件」的片段只能作為補充說明，不能取代程式碼位置。
- 每個論點都要附上片段編號與位置。片段中沒有答案時，直接說明找不到，並建議改用哪些關鍵字查詢；絕對不要編造檔案、函式或行號。
- 需要時用程式碼區塊引用簡短的程式碼。"""

# PROMPT_VARIANT=v3 (ADR 0016): v1 plus an explicit "not found" rule for
# features the project does not have (questions.yaml Q10 was answered with
# invented code in every group A-I; no similarity or rerank threshold
# separates it from real questions). Built on v1, not v2: group F showed no
# gain from v2's other changes. Kept short for qwen2.5-coder:3b, which drops
# rules from long instructions:
# - one rule per line, numbered, the refusal rule right after "use only the excerpts";
# - the refusal is one fixed sentence to copy, not a description of what to say;
# - it names the two failure modes seen in Q10's answers: general knowledge
#   ("usually WebSockets") and a similar word in an unrelated function name;
# - the rule is repeated right after the question (REFUSAL_REMINDER): after
#   four code excerpts, the top of the prompt is far away for a small model;
# - v1's "suggest what to search for instead" is dropped: it invited the model
#   to talk about related code instead of saying "not found".
REFUSAL_SENTENCE = "在索引的專案中找不到相關內容。"
SYSTEM_PROMPT_V3 = f"""You are a senior engineer helping a team understand a game front-end codebase.
Rules:
1. Answer ONLY from the code excerpts below. Do not guess. Do not use general knowledge.
2. If no excerpt directly mentions the topic of the question, reply with exactly: {REFUSAL_SENTENCE}
   A similar word in a function or variable name is not enough.
3. Cite every claim with the excerpt number and location, e.g. [2] src/game/Player.ts:12-30. Never invent files, functions or line numbers.
4. Quote short code snippets in fenced code blocks when they help.
5. Always answer in Traditional Chinese (繁體中文), even if the question is in English."""
REFUSAL_REMINDER = f"(If no excerpt directly mentions this topic, reply only: {REFUSAL_SENTENCE})"

PROMPTS = {"v1": SYSTEM_PROMPT, "v2": SYSTEM_PROMPT_V2, "v3": SYSTEM_PROMPT_V3}

NO_INDEX_ANSWER = "目前還沒有任何索引資料。請先執行索引（介面上的「更新索引」按鈕，或 scripts/index.sh）。"
NO_MATCH_ANSWER = "在目前的索引中找不到與這個問題相關的程式碼。"
# SCORE_THRESHOLD removed every excerpt (ADR 0014). Fixed text, the LLM is not
# called: with nothing relevant to read, a model would only guess. Must contain
# 「找不到」 (scripts/evaluate.py counts it as a refusal for the trick question).
NO_RELEVANT_ANSWER = (
    "在目前索引的專案中找不到與這個問題相關的內容：所有取回片段的相似度都低於門檻（SCORE_THRESHOLD），"
    "因此不產生回答，以免編造不存在的程式碼。"
    "如果確定專案中有相關功能，請換個說法，或直接寫出檔名、函式或常數名稱再查詢一次。"
)


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
    # Which retrievers found this excerpt: "vector", "keyword", "identifier".
    matched_by: list[str] = field(default_factory=list)
    # Cosine similarity from the vector channel (None if only keyword /
    # identifier search found it). Unlike ``score`` it is comparable across
    # retrieval settings; scripts/calibrate_threshold.py reads it. ADR 0014.
    vector_score: float | None = None
    # Cross-encoder relevance when RERANK=true (ADR 0015), else None.
    rerank_score: float | None = None

    @property
    def location(self) -> str:
        return f"{self.file_path}:{self.start_line}-{self.end_line}"


@dataclass
class QueryResult:
    answer: str
    sources: list[Source]

    def to_dict(self) -> dict:
        return {"answer": self.answer, "sources": [asdict(s) for s in self.sources]}


def build_prompt(question: str, sources: list[Source], variant: str = "v1") -> str:
    blocks = []
    for s in sources:
        title = f"[{s.ref}] {s.location}"
        if s.symbol:
            title += f" ({s.kind} {s.symbol})"
        if variant == "v2":
            title += " — 文件" if is_doc_path(s.file_path) else " — 程式碼"
        fence_lang = "md" if s.language == "markdown" else s.language
        blocks.append(f"{title}\n```{fence_lang}\n{s.text}\n```")
    context = "\n\n".join(blocks)
    if variant == "v2":
        return f"{SYSTEM_PROMPT_V2}\n\n## 程式碼片段\n\n{context}\n\n## 問題\n\n{question}\n\n## 回答\n"
    if variant == "v3":
        return (
            f"{SYSTEM_PROMPT_V3}\n\n## Code excerpts\n\n{context}\n\n## Question\n\n{question}\n"
            f"{REFUSAL_REMINDER}\n\n## Answer\n"
        )
    return f"{PROMPTS['v1']}\n\n## Code excerpts\n\n{context}\n\n## Question\n\n{question}\n\n## Answer\n"


@dataclass
class StreamEvent:
    """One step of a streamed answer.

    ``kind`` is ``"sources"`` (data: list of source dicts), ``"token"`` (data:
    ``{"text": ...}``) or ``"done"`` (data: timing stats). Errors are raised,
    not yielded, so the caller decides how to report them.
    """

    kind: str
    data: object


@dataclass
class Retrieval:
    """What :meth:`RagService.retrieve_detailed` found, plus what it filtered and how long reranking took."""

    sources: list[Source]
    # Vector hits dropped by SCORE_THRESHOLD (before fusion).
    below_threshold: int = 0
    # True when SCORE_THRESHOLD removed every candidate: answer with NO_RELEVANT_ANSWER.
    no_relevant: bool = False
    rerank_seconds: float | None = None
    rerank_load_seconds: float | None = None


class RagService:
    def __init__(
        self,
        settings: Settings,
        store: CodeVectorStore,
        embed_model: BaseEmbedding,
        llm: LLM,
        reranker: Reranker | None = None,
    ):
        self.settings = settings
        self.store = store
        self.embed_model = embed_model
        self.llm = llm
        # Only used when settings.rerank; built lazily by the services (ADR 0015).
        self.reranker = reranker
        self._keyword_lock = threading.Lock()
        self._keyword_index: KeywordIndex | None = None
        self._keyword_signature: str | None = None

    def keyword_index(self) -> KeywordIndex:
        """The BM25 index, rebuilt whenever the stored points changed (also when
        another process, e.g. the CLI indexer, re-indexed)."""
        with self._keyword_lock:
            signature = self.store.signature()
            if self._keyword_index is None or signature != self._keyword_signature:
                self._keyword_index = KeywordIndex(self.store.all_nodes())
                self._keyword_signature = signature
            return self._keyword_index

    def _embed_query(self, question: str) -> list[float]:
        try:
            return self.embed_model.get_query_embedding(f"{self.settings.query_prefix}{question}")
        except Exception as exc:
            if is_timeout(exc):
                s = self.settings
                raise OllamaTimeoutError("embedding", s.embed_request_timeout, "EMBED_REQUEST_TIMEOUT") from exc
            raise

    def retrieve(self, question: str, top_k: int | None = None) -> list[Source]:
        return self.retrieve_detailed(question, top_k).sources

    def retrieve_detailed(self, question: str, top_k: int | None = None) -> Retrieval:
        """The retrieval pipeline, in this order (ADR 0013, 0014, 0015):

        1. vector search (+ BM25 and identifier search with HYBRID_SEARCH);
        2. SCORE_THRESHOLD on the vector channel's cosine scores, *before* fusion
           (identifier hits and keyword hits containing an exact identifier are exempt);
        3. RRF fusion of the remaining lists (HYBRID_SEARCH);
        4. per-type selection (SPLIT_RETRIEVAL) of the candidates;
        5. cross-encoder rerank of those candidates, keep the best (RERANK).

        ``top_k`` (or the default: RERANK_TOP_N with rerank, else TOP_K) is the
        number of excerpts returned, i.e. sent to the LLM.
        """
        s = self.settings
        k = top_k or s.default_top_k
        # With rerank, steps 1-4 select this many candidates instead of k.
        n_candidates = max(k, s.rerank_candidates) if s.rerank else k
        pool = n_candidates
        if s.hybrid_search or s.split_retrieval:
            pool = max(pool, s.retrieval_candidates)
        vector_hits = self.store.query(self._embed_query(question), pool)

        nodes: dict[str, BaseNode] = {}
        found_by: dict[str, list[str]] = {}
        cosine = {h.node.node_id: float(h.score or 0.0) for h in vector_hits}

        def note(node: BaseNode, retriever: str) -> str:
            nodes.setdefault(node.node_id, node)
            found_by.setdefault(node.node_id, []).append(retriever)
            return node.node_id

        threshold = s.score_threshold
        below = 0
        if threshold is not None:
            kept = [h for h in vector_hits if float(h.score or 0.0) >= threshold]
            below = len(vector_hits) - len(kept)
            vector_hits = kept
        vector_ranking = [note(h.node, "vector") for h in vector_hits]

        if s.hybrid_search:
            index = self.keyword_index()
            identifiers = extract_identifiers(question)
            keyword_hits = [n for n, _ in index.search(question, pool)]
            if threshold is not None:
                # A keyword hit must either be semantically close (its vector hit
                # passed the threshold) or contain an exact identifier from the
                # question; otherwise common words ("player") would let anything through.
                passed = set(vector_ranking)
                keyword_hits = [
                    n for n in keyword_hits if n.node_id in passed or contains_identifier(n.get_content(), identifiers)
                ]
            keyword_ranking = [note(n, "keyword") for n in keyword_hits]
            # Identifier hits define a name the question spells out: exact evidence, never filtered.
            ident_ranking = [note(n, "identifier") for n in index.identifier_matches(identifiers, pool)]
            fused = rrf([vector_ranking, keyword_ranking, ident_ranking], k=s.rrf_k)
            ranked = [node_id for node_id, _ in fused]
            scores = {node_id: score for node_id, score in fused}
        else:
            ranked = vector_ranking
            scores = {nid: cosine[nid] for nid in vector_ranking}

        if threshold is not None and not ranked:
            return Retrieval(sources=[], below_threshold=below, no_relevant=bool(below))

        def is_doc(nid: str) -> bool:
            return is_doc_path(str(nodes[nid].metadata.get("file_path", "")))

        if s.split_retrieval:
            chosen = split_select(ranked, n_candidates, s.doc_top_k, is_doc)
        else:
            chosen = ranked[:n_candidates]

        rerank_scores: dict[str, float] = {}
        rerank_seconds = rerank_load_seconds = None
        if s.rerank and len(chosen) > 0:
            chosen, rerank_scores, rerank_seconds, rerank_load_seconds = self._rerank(question, chosen, nodes, k)
            if s.split_retrieval:
                # Keep SPLIT_RETRIEVAL's presentation: code first, each group in rerank order.
                chosen = [n for n in chosen if not is_doc(n)] + [n for n in chosen if is_doc(n)]
        chosen = chosen[:k]

        sources = []
        for ref, node_id in enumerate(chosen, start=1):
            node = nodes[node_id]
            meta = node.metadata
            sources.append(
                Source(
                    ref=ref,
                    file_path=meta.get("file_path", "?"),
                    start_line=int(meta.get("start_line", 0)),
                    end_line=int(meta.get("end_line", 0)),
                    symbol=meta.get("symbol", ""),
                    kind=meta.get("kind", ""),
                    language=meta.get("language", ""),
                    score=round(scores.get(node_id, 0.0), 4),
                    text=node.get_content(),
                    matched_by=found_by[node_id],
                    vector_score=round(cosine[node_id], 4) if node_id in cosine else None,
                    rerank_score=round(rerank_scores[node_id], 4) if node_id in rerank_scores else None,
                )
            )
        return Retrieval(
            sources=sources,
            below_threshold=below,
            rerank_seconds=rerank_seconds,
            rerank_load_seconds=rerank_load_seconds,
        )

    def _rerank(
        self, question: str, candidates: list[str], nodes: dict[str, BaseNode], k: int
    ) -> tuple[list[str], dict[str, float], float, float | None]:
        if self.reranker is None:
            raise RuntimeError("RERANK=true but no reranker was configured")
        passages = []
        for nid in candidates:
            meta = nodes[nid].metadata
            # The path and symbol help the cross-encoder as much as they help a reader.
            header = " ".join(str(x) for x in (meta.get("file_path", ""), meta.get("symbol", "")) if x)
            passages.append(f"{header}\n{nodes[nid].get_content()}" if header else nodes[nid].get_content())
        started = time.monotonic()
        raw = self.reranker.score(question, passages)
        elapsed = time.monotonic() - started
        load = getattr(self.reranker, "take_load_seconds", lambda: None)()
        # Report scoring time only; a first-query model load is reported separately.
        seconds = round(max(0.0, elapsed - (load or 0.0)), 3)
        order = rerank_order(raw)
        reranked = [candidates[i] for i in order][:k]
        return reranked, {candidates[i]: raw[i] for i in range(len(candidates))}, seconds, load

    def _llm_timeout(self, exc: BaseException) -> OllamaTimeoutError | None:
        if not is_timeout(exc):
            return None
        return OllamaTimeoutError("llm", self.settings.llm_request_timeout, "LLM_REQUEST_TIMEOUT")

    def answer(self, question: str, top_k: int | None = None) -> QueryResult:
        if not self.store.exists():
            return QueryResult(answer=NO_INDEX_ANSWER, sources=[])
        found = self.retrieve_detailed(question, top_k)
        sources = found.sources
        if not sources:
            return QueryResult(answer=NO_RELEVANT_ANSWER if found.no_relevant else NO_MATCH_ANSWER, sources=[])
        try:
            response = self.llm.complete(build_prompt(question, sources, self.settings.prompt_variant))
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
            # ADR 0014: vector hits dropped by SCORE_THRESHOLD; True when nothing was left.
            "below_threshold": 0,
            "no_relevant": False,
            # ADR 0015: cross-encoder time (None with RERANK=false); model load on first use.
            "rerank_seconds": None,
            "rerank_load_seconds": None,
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
        found = self.retrieve_detailed(question, top_k)
        sources = found.sources
        stats["below_threshold"] = found.below_threshold
        stats["no_relevant"] = found.no_relevant
        stats["rerank_seconds"] = found.rerank_seconds
        stats["rerank_load_seconds"] = found.rerank_load_seconds
        if not sources:
            yield from canned(NO_RELEVANT_ANSWER if found.no_relevant else NO_MATCH_ANSWER)
            return
        stats["retrieval_seconds"] = round(time.monotonic() - started, 3)
        yield StreamEvent("sources", [asdict(s) for s in sources])

        text_so_far = ""
        raw_chars = 0  # length of chunk.text seen so far, before stripping
        try:
            for chunk in self.llm.stream_complete(build_prompt(question, sources, self.settings.prompt_variant)):
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
