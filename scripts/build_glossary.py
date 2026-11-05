#!/usr/bin/env python3
"""Draft a query glossary (QUERY_GLOSSARY, ADR 0020) from a project's code and docs.

從專案的程式碼與文件半自動產生查詢詞彙表草稿（QUERY_GLOSSARY，ADR 0020），供人工審核。

    python3 scripts/build_glossary.py examples/sample-game-frontend
    python3 scripts/build_glossary.py /path/to/project --out ~/glossary-draft.yaml
    python3 scripts/build_glossary.py /path/to/project --existing glossary/my.yaml --out new-terms.yaml

What it collects:

1. Declarations: top-level constants, classes, functions, enums, interfaces and
   types in the code files (function-local variables and methods are left out).
2. Chinese ↔ identifier pairs, each with where it was found:
   - parentheses in Markdown: 「衝刺（dash）」, 「3 條命（`PLAYER_MAX_LIVES`）」. An
     English word maps to every declaration whose name contains it (dash →
     DASH_SPEED, DASH_COOLDOWN_MS…), the same word split the backend uses;
   - a Chinese phrase right before a backticked declaration: 「無敵狀態 `INVINCIBLE_MS`」;
   - Markdown table rows with a declaration and Chinese cells:
     「| ScoreSystem | … | 分數、連擊倍率 |」;
   - Chinese comments on or right above a declaration: 「// 無敵時間」.
3. Declarations without any Chinese term, grouped by their shared word, as
   comments at the end, so a person can add the terms users would type.

The output is a glossary file that loads as is, but it is a draft: heuristics
also pick up phrases such as 「超過」 or single measure words. Review every entry,
delete the wrong ones, and add missing terms before using it.

Privacy (CLAUDE.md): a draft of a real project contains its identifiers. Write
it outside this repository (the default is stdout) and point QUERY_GLOSSARY_PATH
/ GLOSSARY_DIR at it; only the sample project's glossary is committed here.

Needs Python 3.9+ only (no PyYAML needed to write the draft).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

CODE_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
DOC_EXTENSIONS = {".md", ".mdx", ".markdown"}
EXCLUDE_DIRS = {"node_modules", "dist", "build", "out", "coverage", "vendor"}
EXCLUDE_SUFFIXES = (".min.js", ".bundle.js", ".d.ts")

DECL_RE = re.compile(
    r"^(?:export\s+)?(?:default\s+)?(?:declare\s+)?(?:abstract\s+)?(?:async\s+)?"
    r"(const|let|var|class|function|enum|interface|type)\s+([A-Za-z_$][A-Za-z0-9_$]*)"
)
CJK = "㐀-䶿一-鿿豈-﫿"
CJK_RUN_END_RE = re.compile(rf"([{CJK}]+)\s*$")
CJK_RUN_RE = re.compile(rf"[{CJK}]+")
PAREN_RE = re.compile(rf"([{CJK}]+)\s*[（(]\s*([^）)\n]{{1,60}}?)\s*[）)]")
BACKTICK_RE = re.compile(rf"([{CJK}]+)\s*`([A-Za-z_$][A-Za-z0-9_$.]*)(?:\(\))?`")
IDENT_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
PATH_RE = re.compile(r"\S*/\S*|\S+\.[A-Za-z]{1,5}\b")
COMMENT_RE = re.compile(r"(?://|/\*+|^\s*\*)(.*?)(?:\*/)?\s*$")

# Same splitting as backend/app/retrieval.py (a unit test checks they agree).
_CAMEL_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|[A-Z]+|\d+")
STOPWORDS = set("a an and are as at be by for from in is it of on or the to with".split())
# Chinese terms too short or too generic to be useful; a person can re-add any of them.
MIN_TERM, MAX_TERM = 2, 8
NOISE_TERMS = {"超過", "呼叫", "透過", "使用", "定義在", "設定在", "進入", "位於", "每收集", "例如", "以及", "或是"}
# Function words a phrase right before an identifier often starts with
# (「並進入無敵狀態 `INVINCIBLE_MS`」 → 無敵狀態), longest first.
LEADING_NOISE = ("並進入", "進入", "再以", "並", "再", "以", "在", "用", "把", "將", "會", "就", "也", "是", "的", "每", "從", "由")


def split_identifier(word: str) -> list[str]:
    parts: list[str] = []
    for piece in re.split(r"[_$]+", word):
        parts.extend(p.lower() for p in _CAMEL_RE.findall(piece))
    return [p for p in parts if p]


@dataclass
class Declaration:
    name: str
    kind: str
    file: str
    line: int

    @property
    def parts(self) -> list[str]:
        return split_identifier(self.name)


@dataclass
class Entry:
    term: str
    identifiers: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    def add(self, identifiers: list[str], where: str) -> None:
        for ident in identifiers:
            if ident not in self.identifiers:
                self.identifiers.append(ident)
        self.identifiers.sort()
        if where not in self.evidence:
            self.evidence.append(where)


def _files(root: Path, extensions: set[str]) -> list[Path]:
    out = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if not p.is_file() or p.suffix.lower() not in extensions or p.name.endswith(EXCLUDE_SUFFIXES):
            continue
        if any(part.startswith(".") or part in EXCLUDE_DIRS for part in rel.parts[:-1]):
            continue
        out.append(p)
    return out


def find_declarations(root: Path) -> list[Declaration]:
    """Top-level declarations: the line starts in column 0 (locals are indented).
    File names count too (``collision`` for ``collision.ts``): BM25 indexes the
    file path of every chunk, so a file name is a useful query word."""
    decls: list[Declaration] = []
    seen: set[str] = set()
    for path in _files(root, CODE_EXTENSIONS):
        stem = path.name.split(".")[0]
        if IDENT_RE.fullmatch(stem) and stem not in seen and stem not in {"index", "main"}:
            seen.add(stem)
            decls.append(Declaration(stem, "file", path.relative_to(root).as_posix(), 0))
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            m = DECL_RE.match(line)
            if m and m.group(2) not in seen:
                seen.add(m.group(2))
                decls.append(Declaration(m.group(2), m.group(1), path.relative_to(root).as_posix(), n))
    return decls


def _term(text: str) -> str | None:
    """The trailing Chinese phrase of ``text`` if it is a usable term."""
    m = CJK_RUN_END_RE.search(text)
    term = m.group(1) if m else ""
    stripped = True
    while stripped:
        stripped = False
        for prefix in LEADING_NOISE:
            if term.startswith(prefix) and len(term) - len(prefix) >= MIN_TERM:
                term, stripped = term[len(prefix):], True
                break
    if not MIN_TERM <= len(term) <= MAX_TERM or term in NOISE_TERMS or term in LEADING_NOISE:
        return None
    return term


def _by_words(words: list[str], decls: list[Declaration]) -> list[str]:
    """Declarations whose name contains the most of ``words`` (English words from the docs)."""
    words = [w.lower() for w in words if w.lower() not in STOPWORDS]
    if not words:
        return []
    scored = [(sum(w in d.parts for w in words), d.name) for d in decls]
    best = max((s for s, _ in scored), default=0)
    return sorted(name for s, name in scored if s and s == best)


def build_draft(root: Path, existing: set[str] | None = None) -> dict[str, Entry]:
    decls = find_declarations(root)
    names = {d.name for d in decls}
    entries: dict[str, Entry] = {}
    existing = existing or set()

    def add(term: str | None, idents: list[str], where: str) -> None:
        if term and idents and term not in existing:
            entries.setdefault(term, Entry(term)).add(idents, where)

    for path in _files(root, DOC_EXTENSIONS):
        rel = path.relative_to(root).as_posix()
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            where = f"{rel}:{n}"
            if line.lstrip().startswith("|"):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                # Paths (`src/systems/collision.ts`) are not names; the row's name cell is.
                plain = [PATH_RE.sub(" ", c.replace("`", " ")) for c in cells]
                idents = sorted({w for c in plain for w in IDENT_RE.findall(c) if w in names})
                if idents:
                    for cell in cells:
                        for part in re.split(r"[、，,／/；;]", cell):
                            part = part.strip()
                            if CJK_RUN_RE.fullmatch(part):
                                add(_term(part), idents, f"{where} (table)")
                continue
            for m in PAREN_RE.finditer(line):
                inside = m.group(2)
                idents = [w for w in IDENT_RE.findall(inside.replace("`", " ")) if w in names]
                if not idents and re.fullmatch(r"[A-Za-z][A-Za-z \-]*", inside.strip()):
                    idents = _by_words(re.split(r"[\s\-]+", inside.strip()), decls)
                add(_term(m.group(1)), idents, f"{where} (parenthesis)")
            for m in BACKTICK_RE.finditer(line):
                ident = m.group(2).split(".")[-1]
                if ident in names:
                    add(_term(m.group(1)), [ident], f"{where} (before `{ident}`)")

    for path in _files(root, CODE_EXTENSIONS):
        rel = path.relative_to(root).as_posix()
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(lines):
            m = DECL_RE.match(line)
            if not m:
                continue
            comments = []
            if "//" in line:
                comments.append(line.split("//", 1)[1])
            j = i - 1
            while j >= 0 and COMMENT_RE.match(lines[j].strip()) and lines[j].strip()[:2] in ("//", "/*", "* ", "*", "*/"):
                comments.append(COMMENT_RE.match(lines[j].strip()).group(1))
                j -= 1
            for text in comments:
                for run in CJK_RUN_RE.findall(text):
                    add(run if MIN_TERM <= len(run) <= MAX_TERM and run not in NOISE_TERMS else None,
                        [m.group(2)], f"{rel}:{i + 1} (comment)")
    return entries


def unmapped(decls: list[Declaration], entries: dict[str, Entry]) -> dict[str, list[str]]:
    """Declarations no term points at, grouped by their first word part."""
    mapped = {i for e in entries.values() for i in e.identifiers}
    groups: dict[str, list[str]] = {}
    for d in decls:
        if d.name not in mapped:
            key = next((p for p in d.parts if p not in {"max", "min", "is", "get", "set"}), d.name.lower())
            groups.setdefault(key, []).append(d.name)
    return dict(sorted(groups.items()))


def render(root: Path, entries: dict[str, Entry], decls: list[Declaration]) -> str:
    lines = [
        f"# DRAFT query glossary for {root.name}, generated by scripts/build_glossary.py (ADR 0020).",
        "# Review every entry before use: delete wrong pairs, add the terms users type.",
        "# 草稿：使用前請逐條審核，刪掉錯的對應，補上使用者會打的中文詞。",
        "version: 1",
        "terms:",
    ]
    for term in sorted(entries, key=lambda t: (entries[t].evidence[0], t)):
        e = entries[term]
        lines.append(f"  # from {', '.join(e.evidence[:3])}" + (f" (+{len(e.evidence) - 3} more)" if len(e.evidence) > 3 else ""))
        lines.append(f"  {term}: [{', '.join(e.identifiers)}]")
    groups = unmapped(decls, entries)
    lines += ["", "# Unmapped declarations (no Chinese term found), by shared word. Add terms for those users ask about:",
              "# 沒有找到中文詞的宣告（依共同字詞分組）。使用者會問到的，請補上中文詞："]
    for key, names in groups.items():
        lines.append(f"#   {key}: [{', '.join(names)}]")
    return "\n".join(lines) + "\n"


def load_existing_terms(path: Path) -> set[str]:
    """Terms of an existing glossary (top-level keys under ``terms:``), read without PyYAML."""
    terms: set[str] = set()
    in_terms = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("terms:"):
            in_terms = True
            continue
        if in_terms and line and not line.startswith(" ") and not line.startswith("#"):
            break
        m = re.match(r"^  ([^\s#][^:]*):", line)
        if in_terms and m:
            terms.add(m.group(1).strip().strip("'\""))
    return terms


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("project", type=Path, help="the project folder (the one that is indexed)")
    p.add_argument("--out", type=Path, help="write the draft here (default: stdout). Keep real projects' drafts outside this repo")
    p.add_argument("--existing", type=Path, help="an existing glossary: terms already in it are left out of the draft")
    args = p.parse_args(argv)
    if not args.project.is_dir():
        p.error(f"{args.project} is not a folder")
    existing = load_existing_terms(args.existing) if args.existing else set()
    decls = find_declarations(args.project)
    entries = build_draft(args.project, existing)
    text = render(args.project.resolve(), entries, decls)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"{len(entries)} draft terms, {len(decls)} declarations → {args.out} (review before use)", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
