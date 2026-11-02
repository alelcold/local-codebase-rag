"""Keyword search, identifier matching, Reciprocal Rank Fusion and per-type
selection: the parts of retrieval that do not need the embedding model.

Design and trade-offs: docs/decisions/0013-hybrid-retrieval-and-split-retrieval.md

- :func:`tokenize` is code aware: ``INVINCIBLE_MS`` yields ``invincible_ms``,
  ``invincible`` and ``ms``; ``ScoreSystem`` yields ``scoresystem``, ``score``
  and ``system``. The full identifier is kept as its own token, so an exact
  identifier in the question matches rarely and scores high (high IDF), while
  its parts still match prose such as "score system".
- :class:`KeywordIndex` is a small in-memory BM25 index over every chunk. A
  50-300 file project has a few thousand chunks at most; building it takes
  milliseconds and needs no extra service or re-index.
- :func:`identifier_matches` ranks chunks that *define* an identifier named
  in the question (``export const INVINCIBLE_MS``, ``class ScoreSystem``,
  method ``Player.takeDamage``). This is what makes "where is X set?" land on
  the code that declares X rather than on the docs that mention it.
- :func:`rrf` merges ranked lists by rank, not score, so cosine similarities and
  BM25 scores never have to be put on one scale.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass, field
from typing import TypeVar

from llama_index.core.schema import BaseNode

from .chunker import declared_names

T = TypeVar("T", bound=Hashable)

# ---------------------------------------------------------------------------
# Tokenizing
# ---------------------------------------------------------------------------

# ASCII words, identifiers and numbers only (``\w`` would be Unicode-aware and
# glue "INVINCIBLE_MS是多久" into one token). CJK text is deliberately not
# indexed: in a Chinese-speaking team the Markdown docs are Chinese and the code
# is not, so CJK terms would make the keyword channel favour exactly the docs
# that already crowd out code. Chinese meaning is the vector channel's job.
_TOKEN_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*|\d+(?:\.\d+)?")
_CAMEL_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|[A-Z]+|\d+")

# Words that carry no meaning for code search. Kept short on purpose: BM25's
# IDF already discounts common words; this only drops question filler.
STOPWORDS = frozenset(
    """a an and are as at be by can do does for from how i in is it of on or the this
    to was what when where which who why with did there their then than into
    after before about been being its we you""".split()
)


def split_identifier(word: str) -> list[str]:
    """``INVINCIBLE_MS`` -> [invincible, ms]; ``useSyncExternalStore`` -> [use, sync, external, store]."""
    parts: list[str] = []
    for piece in re.split(r"[_$]+", word):
        parts.extend(p.lower() for p in _CAMEL_RE.findall(piece))
    return [p for p in parts if p]


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(text):
        if raw[0].isdigit():
            tokens.append(raw)
            continue
        lower = raw.lower()
        if lower in STOPWORDS:
            continue
        tokens.append(lower)
        parts = split_identifier(raw)
        if len(parts) > 1:
            tokens.extend(p for p in parts if len(p) > 1 and p not in STOPWORDS)
    return tokens


# ---------------------------------------------------------------------------
# Identifiers named in a question
# ---------------------------------------------------------------------------

_IDENT_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*")


def looks_like_identifier(word: str) -> bool:
    """True for words that are almost certainly code, not prose: ``INVINCIBLE_MS``,
    ``ScoreSystem``, ``takeDamage``, ``Player.takeDamage``. Plain words such as
    ``Player`` or ``HUD`` are left to BM25: they are also ordinary English. An
    all-caps word of 4+ letters (``GRAVITY``) counts: it is a constant far more
    often than an acronym, and a wrong guess only costs an empty match."""
    if "." in word:
        parts = word.split(".")
        # Player.takeDamage, store.set, Game.frame
        return any(looks_like_identifier(p) for p in parts) or (
            len(parts) == 2 and parts[0][:1].isupper() and parts[1][:1].islower()
        )
    if "_" in word.strip("_") and len(word) > 2:
        return True
    if len(word) >= 4 and word.isupper() and word.isalpha():
        return True
    return bool(re.search(r"[a-z][A-Z]", word))


def extract_identifiers(question: str) -> list[str]:
    found: list[str] = []
    for word in _IDENT_RE.findall(question):
        word = word.strip(".")
        if word and looks_like_identifier(word) and word not in found:
            found.append(word)
    return found


# ---------------------------------------------------------------------------
# BM25
# ---------------------------------------------------------------------------


@dataclass
class _Doc:
    node: BaseNode
    tf: Counter
    length: int
    defines: set[str] = field(default_factory=set)
    symbol: str = ""


def _meta_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return [v for v in str(value or "").split(",") if v]


class KeywordIndex:
    """In-memory BM25 (Okapi; k1=1.2, b=0.75) over chunk text plus its file path,
    symbol and defined names."""

    def __init__(self, nodes: Sequence[BaseNode], k1: float = 1.2, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs: list[_Doc] = []
        df: Counter = Counter()
        for node in nodes:
            meta = node.metadata or {}
            text = node.get_content()
            defines = _meta_list(meta.get("defines"))
            if not defines and "defines" not in meta:
                # Index built before the field existed: derive it from the text.
                defines, _ = declared_names(text, str(meta.get("language", "")))
            symbol = str(meta.get("symbol", "") or "")
            searchable = " ".join([str(meta.get("file_path", "")), symbol, " ".join(defines), text])
            tf = Counter(tokenize(searchable))
            self.docs.append(_Doc(node, tf, sum(tf.values()), set(defines), symbol))
            df.update(tf.keys())
        n = len(self.docs)
        self.avgdl = (sum(d.length for d in self.docs) / n) if n else 0.0
        # BM25+ style IDF that is never negative (common terms score ~0, not < 0).
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def __len__(self) -> int:
        return len(self.docs)

    def search(self, query: str, top_k: int) -> list[tuple[BaseNode, float]]:
        terms = [t for t in dict.fromkeys(tokenize(query)) if t in self.idf]
        if not terms or not self.docs:
            return []
        scored: list[tuple[float, int]] = []
        for i, doc in enumerate(self.docs):
            score = 0.0
            norm = self.k1 * (1 - self.b + self.b * doc.length / (self.avgdl or 1.0))
            for t in terms:
                f = doc.tf.get(t)
                if f:
                    score += self.idf[t] * f * (self.k1 + 1) / (f + norm)
            if score > 0:
                scored.append((score, i))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [(self.docs[i].node, round(s, 4)) for s, i in scored[:top_k]]

    def identifier_matches(self, identifiers: Sequence[str], top_k: int) -> list[BaseNode]:
        """Chunks that define (declare, or are the symbol for) a named identifier.

        Ranked by how many of the identifiers they define; ties keep index
        order. Matching is case-sensitive: ``INVINCIBLE_MS`` must not match a
        local ``invincibleMs``.
        """
        if not identifiers:
            return []
        hits: list[tuple[int, int]] = []
        for i, doc in enumerate(self.docs):
            symbol = doc.symbol.split(" (part")[0]
            count = 0
            for ident in identifiers:
                last = ident.rsplit(".", 1)[-1]
                if (
                    ident in doc.defines
                    or symbol == ident
                    or symbol.endswith(f".{ident}")  # takeDamage -> Player.takeDamage
                    or ("." in ident and last in doc.defines and symbol.startswith(ident.split(".")[0]))
                ):
                    count += 1
            if count:
                hits.append((count, i))
        hits.sort(key=lambda x: (-x[0], x[1]))
        return [self.docs[i].node for _, i in hits[:top_k]]


# ---------------------------------------------------------------------------
# Fusion and per-type selection
# ---------------------------------------------------------------------------


def rrf(rankings: Sequence[Sequence[T]], k: int = 60) -> list[tuple[T, float]]:
    """Reciprocal Rank Fusion: score(d) = sum over lists of 1 / (k + rank(d)), rank from 1.

    Items found by several retrievers rise to the top; the order of first
    appearance breaks ties so the result is deterministic.
    """
    scores: dict[T, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    order = {item: i for i, item in enumerate(scores)}
    return sorted(scores.items(), key=lambda kv: (-kv[1], order[kv[0]]))


def split_select(ranked: Sequence[T], top_k: int, doc_top_k: int, is_doc: Callable[[T], bool]) -> list[T]:
    """Pick ``top_k`` items: at most ``doc_top_k`` documentation items, the rest code.

    Quotas are caps, not reservations: if one type has too few candidates the
    other fills the remaining slots. Code comes first in the result (each group
    keeps its ranked order), because the answer should lead with code locations
    and the model tends to cite the first excerpts most.
    """
    if top_k <= 0:
        return []
    doc_quota = max(0, min(doc_top_k, top_k - 1)) if top_k > 1 else 0
    code = [x for x in ranked if not is_doc(x)]
    docs = [x for x in ranked if is_doc(x)]
    take_code = min(len(code), top_k - doc_quota)
    take_docs = min(len(docs), top_k - take_code)
    if take_code + take_docs < top_k:  # not enough docs: give the slots back to code
        take_code = min(len(code), top_k - take_docs)
    return list(code[:take_code]) + list(docs[:take_docs])
