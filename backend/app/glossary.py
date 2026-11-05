"""Query glossary: Chinese terms -> code identifiers (QUERY_GLOSSARY, ADR 0020).

The keyword channel of HYBRID_SEARCH (ADR 0013) indexes ASCII identifiers
only, so a Chinese question such as 「連擊倍率怎麼計算？」 gives BM25 nothing to
match and the identifier channel nothing to look up. With QUERY_GLOSSARY=true
the Chinese terms of a reviewed glossary that occur in the question add their
identifiers to the BM25 query and to the identifier channel. The vector
channel and the prompt still see the original question.

File format (YAML)::

    version: 1
    terms:
      連擊: [combo, COMBO_STEP, COMBO_WINDOW_MS, MAX_COMBO_MULTIPLIER]
      倍率: [multiplier, MAX_COMBO_MULTIPLIER]

Matching is a plain substring search, longest term first, without overlaps:
with 「連擊倍率」 and 「連擊」 both listed, 「連擊倍率怎麼算」 matches only the
longer one. ASCII terms match case-insensitively. A draft can be generated
from the code and docs with ``scripts/build_glossary.py``.
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

# The identifiers a term may expand to: ASCII names, optionally dotted (Player.takeDamage).
IDENT_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*")


class GlossaryError(ValueError):
    """The glossary file is missing or malformed. The message names the file and the problem."""


@dataclass
class GlossaryHit:
    terms: list[str] = field(default_factory=list)  # matched terms, in question order
    identifiers: list[str] = field(default_factory=list)  # their identifiers, deduplicated, in order

    def to_dict(self) -> dict:
        return {"terms": self.terms, "identifiers": self.identifiers}


@dataclass
class Glossary:
    terms: dict[str, list[str]]
    path: str = ""

    def __post_init__(self) -> None:
        # Longest first, so 「連擊倍率」 wins over 「連擊」 at the same position.
        self._ordered = sorted(self.terms, key=lambda t: (-len(t), t))

    def __len__(self) -> int:
        return len(self.terms)

    def match(self, question: str) -> GlossaryHit:
        folded = question.casefold()
        taken = [False] * len(folded)
        found: list[tuple[int, str]] = []
        for term in self._ordered:
            needle = term.casefold()
            start = folded.find(needle)
            while start != -1:
                end = start + len(needle)
                if not any(taken[start:end]):
                    for i in range(start, end):
                        taken[i] = True
                    found.append((start, term))
                    break  # one hit per term is enough
                start = folded.find(needle, start + 1)
        found.sort()
        hit = GlossaryHit(terms=[t for _, t in found])
        for term in hit.terms:
            for ident in self.terms[term]:
                if ident not in hit.identifiers:
                    hit.identifiers.append(ident)
        return hit


def parse_glossary(data: object, path: str = "") -> Glossary:
    where = path or "glossary"
    if not isinstance(data, dict) or not isinstance(data.get("terms"), dict):
        raise GlossaryError(f"{where}: expected a mapping with a 'terms:' mapping (term -> identifiers)")
    version = data.get("version", 1)
    if version != 1:
        raise GlossaryError(f"{where}: unsupported version {version!r} (expected 1)")
    terms: dict[str, list[str]] = {}
    for raw_term, raw_idents in data["terms"].items():
        term = str(raw_term).strip()
        if not term:
            raise GlossaryError(f"{where}: empty term")
        if raw_idents is None:
            continue  # an unfinished draft entry (``連擊:``): ignored, not an error
        idents = [raw_idents] if isinstance(raw_idents, str) else raw_idents
        if not isinstance(idents, list):
            raise GlossaryError(f"{where}: {term}: expected a list of identifiers")
        clean: list[str] = []
        for ident in idents:
            ident = str(ident).strip()
            if not IDENT_RE.fullmatch(ident):
                raise GlossaryError(f"{where}: {term}: {ident!r} is not a code identifier")
            if ident not in clean:
                clean.append(ident)
        if clean:
            terms[term] = clean
    return Glossary(terms=terms, path=path)


def load_glossary(path: str | os.PathLike[str]) -> Glossary:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - environment problem
        raise GlossaryError("PyYAML is not installed (backend/requirements.txt)") from exc
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise GlossaryError(f"{p}: cannot read the glossary ({exc.strerror or exc})") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise GlossaryError(f"{p}: invalid YAML: {exc}") from exc
    return parse_glossary(data, str(p))


class GlossaryFile:
    """The glossary at ``path``, reloaded when the file changes (edit it without
    restarting the backend). Load errors are kept, not raised: /health reports
    them and queries go on without expansion."""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._stamp: tuple[float, int] | None = None
        self._glossary: Glossary | None = None
        self.error: str | None = None

    def get(self) -> Glossary | None:
        with self._lock:
            try:
                st = os.stat(self.path)
                stamp = (st.st_mtime, st.st_size)
            except OSError:
                stamp = None
            if stamp is not None and stamp == self._stamp:
                return self._glossary
            try:
                self._glossary = load_glossary(self.path)
                self.error = None
            except GlossaryError as exc:
                self._glossary = None
                self.error = str(exc)
            self._stamp = stamp
            return self._glossary
