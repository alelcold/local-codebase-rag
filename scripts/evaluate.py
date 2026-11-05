#!/usr/bin/env python3
"""Automated evaluation: ask every question in docs/evaluation/questions.yaml
through the streaming endpoint and score what can be scored automatically.

自動化評估：透過串流查詢端點依序詢問 docs/evaluation/questions.yaml 的題目，
記錄延遲並計算可以自動計算的指標。

    python3 scripts/evaluate.py --label codespace-3b
    python3 scripts/evaluate.py --label mac-14b --top-k 8
    python3 scripts/evaluate.py --label quick --only 1,9 --base-url http://localhost:8000
    python3 scripts/evaluate.py --apply-manual docs/evaluation/results/2026-11-03-codespace-3b.md
    python3 scripts/evaluate.py --rescore docs/evaluation/results/*.json

Per question: time to first token, total time, tokens (client-side timing), file
hit rate of the retrieved sources (code and documentation separately, plus the
file that defines a setting for 定位設定 questions), keyword hit rate, whether
the answer contains Simplified Chinese characters, refusals for 陷阱題
(拒答率) and "not found" answers to answerable questions (誤拒率, ADR 0016).
Refusal phrases match in Traditional and Simplified (REFUSAL_TRAD_SIMP), and
files or symbols an answer names that do not exist in the indexed project are
flagged as 疑似編造 (suspected fabrication); a trick question is not counted as
refused when flagged (ADR 0019). --rescore recomputes these metrics for
existing reports without asking the model again.

Writes docs/evaluation/results/<YYYY-MM-DD>-<label>.json and .md. The Markdown
report has an empty 「人工判定正確性」 column: keyword hits are not correctness
(ADR 0012), so a person still judges every answer. After filling it in (0, 1 or
2 per question), --apply-manual copies the scores into the JSON next to it, so
scripts/compare.py can compare them too.

Only the sample project may be evaluated into the repo (CLAUDE.md, privacy):
results contain the answers and cited paths. Use --out-dir outside the repo for
anything else.

Needs Python 3.9+ and PyYAML (pip install -r scripts/requirements-eval.txt).
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QUESTIONS = ROOT / "docs" / "evaluation" / "questions.yaml"
DEFAULT_OUT_DIR = ROOT / "docs" / "evaluation" / "results"
DOC_EXTENSIONS = {".md", ".mdx", ".markdown", ".txt", ".rst"}
# Version of the scoring rules, recorded by --rescore. 2: Simplified refusal
# phrases (REFUSAL_TRAD_SIMP) and suspected fabrication (unknown files / symbols).
SCORING_VERSION = 2
WARMUP_QUESTION ="這個專案主要用什麼程式語言寫的？"
# Per-source fields kept in the JSON report.
SOURCE_FIELDS = (
    "ref", "file_path", "start_line", "end_line", "symbol", "score",
    "vector_score", "rerank_score", "matched_by",
)

# Phrases that mark an answer as "not found" when judging an *answerable*
# question (誤拒, false refusal; ADR 0016). Narrower than a trick question's
# keywords on purpose: a bare 「沒有」 is common in correct answers ("no package
# collected within COMBO_WINDOW_MS"), so it is not listed. Includes the fixed
# sentence of PROMPT_VARIANT=v3 and the backend's canned NO_RELEVANT /
# NO_MATCH answers (all contain 「找不到」).
REFUSAL_PHRASES = (
    "找不到", "沒找到", "沒有找到", "未找到", "不存在", "沒有提到", "未提及", "沒有相關", "無法回答",
    "not found", "cannot find", "can't find", "could not find", "couldn't find", "no relevant",
)

# 繁簡對照清單: every Chinese refusal phrase, Traditional form first, then the
# Simplified forms an answer may use instead. The 3B model often answers a
# Traditional question in Simplified (「我无法提供…」, devlog 2026-11-03), so
# refusal matching — the trick questions' refusal keywords in the question
# files and REFUSAL_PHRASES above — always tries these forms too. Character
# swaps (沒 → 没) and word swaps (支援 → 支持) are both listed here.
# A unit test fails if a Chinese refusal keyword in any question file, or in
# REFUSAL_PHRASES, is missing from this list, or if a Simplified form does not
# match TRAD_TO_SIMP_CHARS below: add new phrases here first.
REFUSAL_TRAD_SIMP: tuple[tuple[str, ...], ...] = (
    ("找不到", "找不到"),
    ("沒找到", "没找到"),
    ("沒有找到", "没有找到"),
    ("未找到", "未找到"),
    ("沒有", "没有"),
    ("不存在", "不存在"),
    ("未包含", "未包含"),
    ("無法", "无法"),
    ("無法回答", "无法回答"),
    ("沒有提到", "没有提到"),
    ("未提及", "未提及"),
    ("沒有相關", "没有相关"),
    ("只支援鍵盤", "只支援键盘", "只支持键盘"),
)
# Character-level Traditional → Simplified map for the phrases above. Only used
# to check REFUSAL_TRAD_SIMP (the first Simplified form must equal the
# character-by-character conversion); matching uses the list itself.
TRAD_TO_SIMP_CHARS = str.maketrans("沒無關鍵盤", "没无关键盘")
_SIMPLIFIED_FORMS: dict[str, tuple[str, ...]] = {row[0]: row[1:] for row in REFUSAL_TRAD_SIMP}


def with_simplified(phrases: Iterable[str]) -> list[str]:
    """``phrases`` plus the Simplified forms from REFUSAL_TRAD_SIMP, in order, without duplicates."""
    out: list[str] = []
    for p in phrases:
        for form in (p, *_SIMPLIFIED_FORMS.get(p, ())):
            if form not in out:
                out.append(form)
    return out


# ── Suspected fabrication (陷阱題 and every other answer) ─────────────────
# An answer that names a file or a code symbol that does not exist anywhere in
# the indexed project is probably invented (devlog 2026-11-03: Q23 「透過
# `syncUi` 同步到雲端」, H Q7 `checkCollisions()`). The check is a screen for
# a person to confirm, like the keywords: it flags, it does not judge.

# File references: a path or file name with a known extension.
FILE_REF_RE = re.compile(
    r"(?<![\w./-])((?:[\w-]+/)*[\w-]+(?:\.[\w-]+)*\.(?:tsx|ts|jsx|js|mjs|cjs|json|md|css|scss|html|vue|py|yaml|yml))(?![\w/])",
    re.ASCII,  # 「在Game.ts中」: Chinese text around a name is not part of it
)
# Library and product names that look like file names.
NOT_FILE_REFS = {"node.js", "next.js", "nuxt.js", "vue.js", "three.js", "pixi.js", "phaser.js", "p5.js",
                 "d3.js", "chart.js", "express.js", "socket.io"}
IDENT_RE = re.compile(r"[A-Za-z_$][\w$]*", re.ASCII)
# Names that are code-shaped but belong to the language, the browser or the
# tools, not to the project: never reported as missing.
KNOWN_NAMES = set(
    """
    console log warn error info Math JSON parse stringify Object Array String Number Boolean Promise Map Set
    Date now keys values entries assign freeze from isArray push pop shift unshift splice slice concat join
    map filter reduce forEach find findIndex some every includes indexOf sort reverse fill toFixed toString
    parseInt parseFloat isNaN floor ceil round min max abs sqrt random hypot atan2 sin cos
    has get set add delete clear then catch finally resolve reject
    setTimeout clearTimeout setInterval clearInterval requestAnimationFrame cancelAnimationFrame
    addEventListener removeEventListener dispatchEvent preventDefault stopPropagation
    querySelector querySelectorAll getElementById createElement appendChild getContext
    localStorage sessionStorage getItem setItem removeItem performance window document
    useState useEffect useRef useMemo useCallback useContext useReducer createRoot render
    JavaScript TypeScript GitHub macOS iOS README
    """.split()
)


def code_shaped(name: str, followed_by_paren: bool) -> bool:
    """Whether ``name`` reads as a code symbol rather than a word: called with (),
    snake_case / CONSTANT_CASE, or camelCase / PascalCase with an inner capital."""
    return followed_by_paren or ("_" in name.strip("_$") and len(name) > 2) or bool(re.search(r"[a-z][A-Z]", name))


@dataclass
class ProjectInventory:
    """File paths and every identifier-like token of the indexed project."""

    root: Path
    files: set[str] = field(default_factory=set)  # posix paths relative to root
    names: set[str] = field(default_factory=set)  # casefolded: GameOver matches gameOver

    @classmethod
    def scan(cls, root: Path) -> "ProjectInventory":
        inv = cls(root=root)
        for p in sorted(root.rglob("*")):
            rel = p.relative_to(root)
            if not p.is_file() or any(part.startswith(".") or part == "node_modules" for part in rel.parts):
                continue
            inv.files.add(rel.as_posix())
            try:
                inv.names.update(n.casefold() for n in IDENT_RE.findall(p.read_text(encoding="utf-8")))
            except (UnicodeDecodeError, OSError):
                continue
        return inv

    def has_file(self, ref: str) -> bool:
        ref = ref.removeprefix("./")
        return any(f == ref or f.endswith("/" + ref) for f in self.files)

    def unknown_refs(self, answer: str) -> dict:
        """Files and code-shaped symbols in ``answer`` that exist nowhere in the project."""
        files: list[str] = []
        for m in FILE_REF_RE.finditer(answer):
            ref = m.group(1)
            if ref.casefold() not in NOT_FILE_REFS and not self.has_file(ref) and ref not in files:
                files.append(ref)
        # Symbols outside the file references (Game.ts is a file, not the symbol "ts").
        rest = FILE_REF_RE.sub(" ", answer)
        symbols: list[str] = []
        for m in IDENT_RE.finditer(rest):
            name = m.group(0)
            if m.start() > 0 and rest[m.start() - 1].isdigit():
                continue  # 1500ms, 0x1f
            paren = rest[m.end():m.end() + 1] == "("
            if (code_shaped(name, paren) and name.casefold() not in self.names and name not in KNOWN_NAMES
                    and name not in symbols):
                symbols.append(name)
        return {"files": files, "symbols": symbols}

# Characters that exist only in Simplified Chinese (their Traditional forms are
# different code points). A hit means the model slipped into Simplified, which
# small models do with Traditional Chinese questions. Deliberately conservative:
# characters that are also normal Traditional characters (里, 只, 干, 着, 面…)
# are left out, so a hit is almost never a false positive. The unit tests check
# this list against the Traditional Chinese docs in this repo.
SIMPLIFIED_ONLY = set(
    "这们说时间来为个过还没么实现问题应该发读写设计数据码认请让对开关门东车进动机线级点简页显转换获处务统"
    "将帧义无体并从输变冲检测调状态会当后于记录储键环层组订阅触连击归频随种类两吗给内档项资讯网络览边际块"
    "闪烁结构选择确错误达产业专区历广杂号图场声备复头宽尽带帮径总惯战户执扩报拟暂术条极标样树欢气浏满灭"
    "热爱电画盖积称稳细终经绘续维缓编职联虑补规访证评识译试话语负质费赋跃软载运递适释钮长闭队阶难顺预颜风验"
)


# ── Questions ──────────────────────────────────────────────────────────────


@dataclass
class Question:
    id: int
    type: str
    question: str
    question_en: str = ""
    key_facts: str = ""
    keywords: list[list[str]] = field(default_factory=list)  # each item: alternatives
    expected_files: list[str] = field(default_factory=list)
    definition_files: list[str] = field(default_factory=list)
    expect_no_answer: bool = False
    forbidden_keywords: list[str] = field(default_factory=list)

    def text(self, lang: str) -> str:
        return self.question_en if lang == "en" and self.question_en else self.question


def load_questions(path: Path) -> list[Question]:
    try:
        import yaml
    except ImportError:  # pragma: no cover - environment problem, not logic
        sys.exit("PyYAML is required: pip install -r scripts/requirements-eval.txt")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    questions = []
    for raw in data["questions"]:
        keywords = [[str(k)] if not isinstance(k, list) else [str(a) for a in k] for k in raw.get("keywords", [])]
        questions.append(
            Question(
                id=int(raw["id"]),
                type=str(raw["type"]),
                question=str(raw["question"]).strip(),
                question_en=str(raw.get("question_en", "")).strip(),
                key_facts=" ".join(str(raw.get("key_facts", "")).split()),
                keywords=keywords,
                expected_files=list(raw.get("expected_files") or []),
                definition_files=list(raw.get("definition_files") or []),
                expect_no_answer=bool(raw.get("expect_no_answer", False)),
                forbidden_keywords=list(raw.get("forbidden_keywords") or []),
            )
        )
    return questions


def question_set_project(path: Path) -> Path | None:
    """The project a question file is about (its ``project:`` field, relative to the repo)."""
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    project = data.get("project")
    return (ROOT / project) if project else None


def load_inventory(project: Path | None, log: Callable[[str], None] = print) -> ProjectInventory | None:
    if project is None or not project.is_dir():
        log(f"! project folder {project} not found: files and symbols in answers are not checked")
        return None
    return ProjectInventory.scan(project)


def parse_only(value: str | None) -> set[int] | None:
    """'1,3,5-7' -> {1, 3, 5, 6, 7}."""
    if not value:
        return None
    ids: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            ids.update(range(int(lo), int(hi) + 1))
        else:
            ids.add(int(part))
    return ids


# ── Streaming client ───────────────────────────────────────────────────────


@dataclass
class StreamResult:
    answer: str = ""
    sources: list[dict] = field(default_factory=list)
    first_token_seconds: float | None = None
    total_seconds: float | None = None
    server: dict | None = None  # the done event
    heartbeats: int = 0
    error: str | None = None


def iter_sse(lines: Iterable[bytes]) -> Iterator[tuple[str, Any]]:
    """Yield (event, data) from raw SSE lines, the same way the frontend parses them."""
    event, data = "message", []
    for raw in lines:
        line = raw.decode("utf-8").rstrip("\r\n")
        if not line:
            if data:
                yield event, json.loads("\n".join(data))
            event, data = "message", []
        elif line.startswith(":"):
            continue
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].removeprefix(" "))
    if data:
        yield event, json.loads("\n".join(data))


def stream_query(
    base_url: str,
    question: str,
    top_k: int | None,
    timeout: float,
    clock: Callable[[], float] = time.monotonic,
) -> StreamResult:
    """POST /query/stream and collect the answer; timing is measured here, as a user would see it."""
    body: dict[str, Any] = {"question": question}
    if top_k:
        body["top_k"] = top_k
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/query/stream",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    result = StreamResult()
    started = clock()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for event, data in iter_sse(resp):
                if event == "heartbeat":
                    result.heartbeats += 1
                elif event == "sources":
                    result.sources = data
                elif event == "token":
                    if result.first_token_seconds is None:
                        result.first_token_seconds = round(clock() - started, 3)
                    result.answer += data.get("text", "")
                elif event == "done":
                    result.server = data
                    break
                elif event == "error":
                    result.error = data.get("detail") or json.dumps(data, ensure_ascii=False)
                    break
        if result.server is None and result.error is None:
            result.error = "stream ended before the done event (connection closed)"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        result.error = f"HTTP {exc.code}: {detail}"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        result.error = f"{type(exc).__name__}: {exc}"
    result.total_seconds = round(clock() - started, 3)
    return result


def get_health(base_url: str, timeout: float = 10.0) -> dict:
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/health", timeout=timeout) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


# ── Scoring ────────────────────────────────────────────────────────────────


def is_doc(path: str) -> bool:
    return Path(path).suffix.lower() in DOC_EXTENSIONS


def answer_refs(answer: str) -> list[int]:
    """Excerpt numbers the answer cites as [n], in order of first appearance."""
    seen: list[int] = []
    for m in re.finditer(r"\[(\d+)\]", answer):
        n = int(m.group(1))
        if n not in seen:
            seen.append(n)
    return seen


def _hits(expected: list[str], found: set[str]) -> dict:
    hit = [f for f in expected if f in found]
    return {
        "expected": len(expected),
        "hit": len(hit),
        "recall": round(len(hit) / len(expected), 3) if expected else None,
        "any": bool(hit) if expected else None,
        "missed": [f for f in expected if f not in found],
    }


def file_metrics(q: Question, sources: list[dict], answer: str) -> dict:
    """Which expected files appear among the retrieved sources (what the model saw),
    and among the sources the answer actually cites with [n]."""
    retrieved = {s.get("file_path", "") for s in sources}
    by_ref = {s.get("ref"): s.get("file_path", "") for s in sources}
    referenced = {by_ref[n] for n in answer_refs(answer) if n in by_ref}
    code = [f for f in q.expected_files if not is_doc(f)]
    docs = [f for f in q.expected_files if is_doc(f)]
    return {
        "retrieved_files": sorted(retrieved),
        "answer_cited_files": sorted(referenced),
        "all": _hits(q.expected_files, retrieved),
        "code": _hits(code, retrieved),
        "doc": _hits(docs, retrieved),
        "definition": _hits(q.definition_files, retrieved),
        "answer_cited": _hits(q.expected_files, referenced),
        # Retrieved chunks that are documentation: shows docs crowding out code.
        "retrieved_doc_share": round(sum(is_doc(s.get("file_path", "")) for s in sources) / len(sources), 3)
        if sources
        else None,
    }


def keyword_metrics(q: Question, answer: str) -> dict:
    text = answer.casefold()
    matched, missed = [], []
    for alternatives in q.keywords:
        # A trick question's keywords are refusal phrases: Simplified forms count too.
        candidates = with_simplified(alternatives) if q.expect_no_answer else alternatives
        if any(a.casefold() in text for a in candidates):
            matched.append(alternatives[0])
        else:
            missed.append(" / ".join(alternatives))
    total = len(q.keywords)
    forbidden = [k for k in q.forbidden_keywords if k.casefold() in text]
    return {
        "total": total,
        "hit": len(matched),
        "rate": round(len(matched) / total, 3) if total else None,
        "matched": matched,
        "missed": missed,
        "forbidden_hits": forbidden,
    }


def simplified_chars(text: str) -> list[str]:
    """Simplified-only characters in ``text``, in order of first appearance."""
    seen: list[str] = []
    for ch in text:
        if ch in SIMPLIFIED_ONLY and ch not in seen:
            seen.append(ch)
    return seen


def refusal_phrases(text: str) -> list[str]:
    """REFUSAL_PHRASES (and their Simplified forms) found in ``text`` (case-insensitive)."""
    folded = text.casefold()
    return [p for p in with_simplified(REFUSAL_PHRASES) if p.casefold() in folded]


def score(q: Question, r: StreamResult, inventory: ProjectInventory | None = None) -> dict:
    files = file_metrics(q, r.sources, r.answer)
    keywords = keyword_metrics(q, r.answer)
    simp = simplified_chars(r.answer)
    # None = not checked (no project folder); a fixed threshold answer invents nothing.
    unknown = inventory.unknown_refs(r.answer) if inventory is not None and not r.error else None
    out: dict[str, Any] = {
        "first_token_seconds": r.first_token_seconds,
        "total_seconds": r.total_seconds,
        "tokens": (r.server or {}).get("tokens"),
        # ADR 0015: cross-encoder time on the server (None with RERANK=false).
        "rerank_seconds": (r.server or {}).get("rerank_seconds"),
        # ADR 0014: answered with the fixed "not found" text, the LLM was not called.
        "no_relevant": bool((r.server or {}).get("no_relevant")),
        "server": r.server,
        "heartbeats": r.heartbeats,
        "files": files,
        "keywords": keywords,
        "simplified_chars": simp,
        "has_simplified": bool(simp),
        "unknown_refs": unknown,
        # 疑似編造: names a file or symbol the project does not have, or a forbidden
        # word. A screen for a person to confirm, not a verdict.
        "suspected_fabrication": None
        if r.error
        else bool(keywords["forbidden_hits"]) or bool(unknown and (unknown["files"] or unknown["symbols"])),
    }
    if q.expect_no_answer:
        # Refusal = a refusal phrase (the keywords) and no sign of invented code:
        # no forbidden word and no file or symbol that is not in the project.
        # "沒有找到多人連線，但可用 WebSocket 實作…" is not a pass; it is flagged for a person.
        out["refusal_keyword_hit"] = bool(keywords["hit"])
        out["refused"] = bool(keywords["hit"]) and not out["suspected_fabrication"]
    else:
        # False refusal (ADR 0016) = says "not found" and gives none of the expected
        # facts. "沒有音效檔，音效由 SoundManager 合成" says 沒有 but hits a keyword: not a refusal.
        phrases = refusal_phrases(r.answer)
        out["refusal_phrases"] = phrases
        out["falsely_refused"] = bool(phrases) and not keywords["hit"] if not r.error else None
    return out


def _mean(values: Iterable[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return round(statistics.fmean(vals), 3) if vals else None


def _rate(flags: Iterable[bool | None]) -> dict:
    vals = [f for f in flags if f is not None]
    return {"hit": sum(vals), "of": len(vals), "rate": round(sum(vals) / len(vals), 3) if vals else None}


def summarize(results: list[dict]) -> dict:
    ok = [r for r in results if not r.get("error")]
    m = [r["metrics"] for r in ok]
    by_type: dict[str, list[dict]] = {}
    for r in ok:
        by_type.setdefault(r["type"], []).append(r["metrics"])
    no_answer = [r["metrics"].get("refused") for r in ok if r.get("expect_no_answer")]
    answerable = [r["metrics"].get("falsely_refused") for r in ok if not r.get("expect_no_answer")]
    return {
        "questions": len(results),
        "errors": len(results) - len(ok),
        "first_token_seconds_mean": _mean(x["first_token_seconds"] for x in m),
        "first_token_seconds_median": round(statistics.median(v), 3)
        if (v := [x["first_token_seconds"] for x in m if x["first_token_seconds"] is not None])
        else None,
        "total_seconds_mean": _mean(x["total_seconds"] for x in m),
        "tokens_mean": _mean(x["tokens"] for x in m),
        "rerank_seconds_mean": _mean(x.get("rerank_seconds") for x in m),
        "threshold_refusals": sum(bool(x.get("no_relevant")) for x in m),
        "file_recall_mean": _mean(x["files"]["all"]["recall"] for x in m),
        "code_hit": _rate(x["files"]["code"]["any"] for x in m),
        "doc_hit": _rate(x["files"]["doc"]["any"] for x in m),
        "definition_hit": _rate(x["files"]["definition"]["any"] for x in m),
        "answer_cited_hit": _rate(x["files"]["answer_cited"]["any"] for x in m),
        "retrieved_doc_share_mean": _mean(x["files"]["retrieved_doc_share"] for x in m),
        "keyword_rate_mean": _mean(x["keywords"]["rate"] for x in m),
        "simplified_answers": sum(x["has_simplified"] for x in m),
        # 拒答率: trick questions refused. 誤拒率: answerable questions answered "not found" (ADR 0016).
        "no_answer_refused": _rate(no_answer),
        "false_refusals": _rate(answerable),
        # 疑似編造 over every answer (None = not checked).
        "suspected_fabrication": _rate(x.get("suspected_fabrication") for x in m),
        "keyword_rate_by_type": {t: _mean(x["keywords"]["rate"] for x in xs) for t, xs in by_type.items()},
    }


# ── Running ────────────────────────────────────────────────────────────────


def run(
    questions: list[Question],
    base_url: str,
    top_k: int | None,
    lang: str,
    timeout: float,
    warmup: bool,
    log: Callable[[str], None] = print,
    query: Callable[..., StreamResult] = stream_query,
    inventory: ProjectInventory | None = None,
) -> list[dict]:
    if warmup:
        log(f"warm-up: {WARMUP_QUESTION} (loads the model; not scored)")
        w = query(base_url, WARMUP_QUESTION, top_k, timeout)
        log(f"  {'error: ' + w.error if w.error else f'{w.total_seconds}s'}")
    results = []
    for q in questions:
        text = q.text(lang)
        log(f"[{q.id}/{questions[-1].id}] {q.type} · {text}")
        r = query(base_url, text, top_k, timeout)
        entry = {
            "id": q.id,
            "type": q.type,
            "question": text,
            "key_facts": q.key_facts,
            "expected_files": q.expected_files,
            "definition_files": q.definition_files,
            "expect_no_answer": q.expect_no_answer,
            "answer": r.answer,
            # vector_score = cosine similarity (None if only keyword / identifier search found
            # the excerpt): scripts/calibrate_threshold.py reads it (ADR 0014).
            "sources": [{k: s.get(k) for k in SOURCE_FIELDS} for s in r.sources],
            "error": r.error,
            "metrics": score(q, r, inventory),
            "manual_correctness": None,  # 0–2, filled in by a person
        }
        results.append(entry)
        mt = entry["metrics"]
        if r.error:
            log(f"  ✗ {r.error}")
        else:
            log(
                f"  first token {mt['first_token_seconds']}s · total {mt['total_seconds']}s · "
                f"{mt['tokens']} tokens · "
                + (f"rerank {mt['rerank_seconds']}s · " if mt.get("rerank_seconds") is not None else "")
                + f"files {mt['files']['all']['hit']}/{mt['files']['all']['expected']} · "
                f"keywords {mt['keywords']['hit']}/{mt['keywords']['total']}"
                + (f" · Simplified: {''.join(mt['simplified_chars'])}" if mt["has_simplified"] else "")
                + (" · suspected fabrication" if mt["suspected_fabrication"] else "")
            )
    return results


def slug(label: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip("-")
    return s or "run"


# ── Markdown report ────────────────────────────────────────────────────────


def _fmt(v: Any, suffix: str = "") -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.1f}{suffix}"
    return f"{v}{suffix}"


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v * 100:.0f}%"


def _ratio(h: dict) -> str:
    return "—" if not h["expected"] else f"{h['hit']}/{h['expected']}"


def _rate_str(r: dict) -> str:
    return "—" if not r["of"] else f"{r['hit']}/{r['of']} ({_pct(r['rate'])})"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def retrieval_label(r: dict | None) -> str:
    """One-line summary of the server's retrieval toggles, e.g.
    'hybrid (RRF k=60) + split (docs ≤ 1) + threshold ≥ 0.5 + rerank (…, 10 → 3) · prompt v2'."""
    if not r:
        return "not reported (server older than ADR 0013: vector only)"
    parts = []
    if r.get("hybrid_search"):
        parts.append(f"hybrid (RRF k={r.get('rrf_k')})")
    if r.get("split_retrieval"):
        parts.append(f"split (docs ≤ {r.get('doc_top_k')})")
    if r.get("chunk_metadata"):
        parts.append("metadata")
    if r.get("score_threshold") is not None:
        parts.append(f"threshold ≥ {r.get('score_threshold')}")
    if r.get("rerank"):
        parts.append(f"rerank ({r.get('rerank_model')}, {r.get('rerank_candidates')} → {r.get('rerank_top_n')})")
    return f"{' + '.join(parts) or 'vector only (baseline)'} · prompt {r.get('prompt_variant', 'v1')}"


def _tags(r: dict) -> str:
    """Status after the keyword ratio in the per-question table."""
    m = r["metrics"]
    tags = []
    if r["expect_no_answer"]:
        if m.get("refused"):
            tags.append("refused")
        elif m.get("refusal_keyword_hit") and m.get("suspected_fabrication"):
            tags.append("**not refused**: refusal phrase, but suspected fabrication")
        else:
            tags.append("**not refused**")
    elif m.get("falsely_refused"):
        tags.append("**falsely refused**")
    if m.get("suspected_fabrication") and not (r["expect_no_answer"] and m.get("refusal_keyword_hit")):
        tags.append("**suspected fabrication**")
    return "".join(f" ({t})" for t in tags)


def render_markdown(report: dict, preamble: str = "", manual: dict[int, tuple[str, str]] | None = None) -> str:
    """The report. ``preamble`` (Markdown before the generated header) and ``manual``
    ({id: (score cell, notes cell)}) keep what a person added when a report is re-scored."""
    manual = manual or {}
    s = report["summary"]
    cfg = report["config"]
    h = report.get("health") or {}
    ollama = h.get("ollama") or {}
    top_k = cfg["top_k"] if cfg["top_k"] else "server default ({})".format(h.get("top_k", "?"))
    lines = [
        f"# Evaluation {report['date']} · {cfg['label']}",
        "",
        *([preamble.strip("\n"), ""] if preamble.strip() else []),
        "> Generated by `scripts/evaluate.py`. Automatic metrics are proxies, not correctness (ADR 0012):",
        "> fill in 「人工判定正確性」 (0–2) for every question after reading the answer.",
        "> 由 `scripts/evaluate.py` 產生。自動指標只是代理指標，不等於回答正確（ADR 0012）：",
        "> 讀過回答後，請為每題填寫「人工判定正確性」（0–2）。",
        "",
        "## Run / 執行設定",
        "",
        "| Item | Value |",
        "| --- | --- |",
        f"| Label | `{cfg['label']}` |",
        f"| Started (UTC) | {report['started_at']} |",
        f"| Base URL | `{cfg['base_url']}` |",
        f"| LLM / Embedding | `{ollama.get('llm_model', '?')}` / `{ollama.get('embed_model', '?')}` |",
        f"| top_k | {top_k} |",
        f"| Language | {cfg['lang']} |",
        f"| Warm-up query | {'yes (model load not counted)' if cfg['warmup'] else 'no (question 1 includes model load)'} |",
        f"| Indexed chunks | {(h.get('qdrant') or {}).get('points', '?')} |",
        f"| Retrieval (ADR 0013) | {retrieval_label(h.get('retrieval'))} |",
        "",
        "## Summary / 摘要",
        "",
        "| Metric / 指標 | Value / 數值 |",
        "| --- | --- |",
        f"| Questions (errors) / 題數（失敗） | {s['questions']} ({s['errors']}) |",
        f"| Time to first token, mean / median / 首字延遲 平均／中位數 | {_fmt(s['first_token_seconds_mean'], ' s')} / {_fmt(s['first_token_seconds_median'], ' s')} |",
        f"| Total time, mean / 總耗時平均 | {_fmt(s['total_seconds_mean'], ' s')} |",
        f"| Tokens, mean / 平均 token 數 | {_fmt(s['tokens_mean'])} |",
        f"| Rerank time, mean / rerank 耗時平均 | {_fmt(s.get('rerank_seconds_mean'), ' s')} |",
        f"| Expected-file recall, mean / 預期檔案命中率平均 | {_pct(s['file_recall_mean'])} |",
        f"| Code file retrieved / 程式碼檔命中 | {_rate_str(s['code_hit'])} |",
        f"| Doc file retrieved / 文件檔命中 | {_rate_str(s['doc_hit'])} |",
        f"| Defining file retrieved (定位設定) / 定義檔命中 | {_rate_str(s['definition_hit'])} |",
        f"| Expected file cited with [n] / 回答以 [n] 引用預期檔案 | {_rate_str(s['answer_cited_hit'])} |",
        f"| Share of retrieved chunks that are docs / 取回片段中文件的比例 | {_pct(s['retrieved_doc_share_mean'])} |",
        f"| Keyword hit rate, mean / 關鍵字命中率平均 | {_pct(s['keyword_rate_mean'])} |",
        f"| Answers with Simplified characters / 混入簡體字的回答 | {s['simplified_answers']} |",
        f"| Refusal rate, trick questions / 拒答率（陷阱題正確拒答） | {_rate_str(s['no_answer_refused'])} |",
        f"| False refusal rate, answerable questions / 誤拒率（可回答的題目答「找不到」） | {_rate_str(s.get('false_refusals') or {'of': 0})} |",
        "| Suspected fabrication: names a file or symbol not in the project, or a forbidden word (check) / "
        f"疑似編造：提到專案中不存在的檔案或符號，或禁用字（需人工確認） | {_rate_str(s.get('suspected_fabrication') or {'of': 0})} |",
        f"| Refused by SCORE_THRESHOLD (LLM not called) / 因門檻直接拒答 | {s.get('threshold_refusals', 0)} |",
        "| Manual correctness / 人工判定正確性 | ___ / " + str(2 * s["questions"]) + " |",
        "",
        "Keyword hit rate by type / 各題型關鍵字命中率："
        + "、".join(f"{t} {_pct(v)}" for t, v in s["keyword_rate_by_type"].items()),
        "",
        "## Per question / 每題明細",
        "",
        "| # | Type | First token | Total | Tokens | Files | Code | Doc | Def. | Keywords | Simplified | 人工判定正確性 (0–2) | Notes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in report["results"]:
        m = r["metrics"]
        f = m["files"]
        if r["error"]:
            lines.append(f"| {r['id']} | {r['type']} | ✗ | | | | | | | | | | {_cell(r['error'][:80])} |")
            continue
        kw = f"{m['keywords']['hit']}/{m['keywords']['total']}" + _tags(r)
        score_cell, notes_cell = manual.get(r["id"], ("", ""))
        lines.append(
            f"| {r['id']} | {r['type']} | {_fmt(m['first_token_seconds'], ' s')} | {_fmt(m['total_seconds'], ' s')} | "
            f"{_fmt(m['tokens'])} | {_ratio(f['all'])} | {_ratio(f['code'])} | {_ratio(f['doc'])} | "
            f"{_ratio(f['definition'])} | {kw} | {''.join(m['simplified_chars']) or '—'} | {score_cell} | {notes_cell} |"
        )
    lines += ["", "Files / Code / Doc / Def. = expected files found among the retrieved sources.", ""]
    lines += ["## Answers / 回答", ""]
    for r in report["results"]:
        m = r["metrics"]
        lines += [f"### {r['id']}. {r['question']}", "", f"- **Type**: {r['type']}", f"- **Key facts**: {r['key_facts']}"]
        if r["error"]:
            lines += [f"- **Error**: `{r['error']}`", ""]
            continue
        retrieved = ", ".join(f"[{s['ref']}] `{s['file_path']}:{s['start_line']}-{s['end_line']}`" for s in r["sources"])
        if m.get("no_relevant"):
            lines.append("- **SCORE_THRESHOLD**: every excerpt was below the threshold; fixed answer, LLM not called")
        if m.get("rerank_seconds") is not None:
            lines.append(f"- **Rerank**: {m['rerank_seconds']} s")
        lines += [
            f"- **Retrieved**: {retrieved or '—'}",
            f"- **Missed expected files**: {', '.join(f'`{x}`' for x in m['files']['all']['missed']) or '—'}",
            f"- **Missed keywords**: {', '.join(f'`{x}`' for x in m['keywords']['missed']) or '—'}",
        ]
        if m["keywords"]["forbidden_hits"]:
            lines.append(f"- **Forbidden keywords found**: {', '.join(m['keywords']['forbidden_hits'])}")
        unknown = m.get("unknown_refs") or {}
        if unknown.get("files") or unknown.get("symbols"):
            found = [f"files {', '.join(f'`{x}`' for x in unknown['files'])}" if unknown.get("files") else "",
                     f"symbols {', '.join(f'`{x}`' for x in unknown['symbols'])}" if unknown.get("symbols") else ""]
            lines.append(f"- **Suspected fabrication (not in the project, check)**: {'; '.join(x for x in found if x)}")
        if m.get("falsely_refused"):
            lines.append(f"- **False refusal**: says {', '.join(m['refusal_phrases'])} and hits no keyword")
        if m["has_simplified"]:
            lines.append(f"- **Simplified characters**: {''.join(m['simplified_chars'])}")
        answer = r["answer"].strip().replace("~~~~", "~ ~ ~ ~")
        lines += ["", "<details><summary>Answer</summary>", "", "~~~~text", answer, "~~~~", "", "</details>", ""]
    return "\n".join(lines).rstrip() + "\n"


# ── Manual scores ──────────────────────────────────────────────────────────

MANUAL_COLUMN = 11  # 0-based cell index of 「人工判定正確性」 in the per-question table


def read_manual_scores(markdown: str) -> dict[int, int]:
    """Scores typed into the 「人工判定正確性」 column of a report: {question id: 0|1|2}."""
    scores: dict[int, int] = {}
    in_table = False
    for line in markdown.splitlines():
        if line.startswith("| # | Type |"):
            in_table = True
            continue
        if in_table and not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not in_table or not cells[0].isdigit() or len(cells) <= MANUAL_COLUMN:
            continue
        value = cells[MANUAL_COLUMN]
        if value:
            if value not in ("0", "1", "2"):
                raise ValueError(f"question {cells[0]}: 人工判定正確性 must be 0, 1 or 2, got {value!r}")
            scores[int(cells[0])] = int(value)
    return scores


def read_manual_cells(markdown: str) -> dict[int, tuple[str, str]]:
    """Raw 「人工判定正確性」 and Notes cells of the per-question table: {id: (score, notes)}."""
    cells_by_id: dict[int, tuple[str, str]] = {}
    in_table = False
    for line in markdown.splitlines():
        if line.startswith("| # | Type |"):
            in_table = True
            continue
        if in_table and not line.startswith("|"):
            break
        if not in_table:
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip()[1:-1])]
        if cells[0].isdigit() and len(cells) > MANUAL_COLUMN + 1 and cells[2] != "✗":
            cells_by_id[int(cells[0])] = (cells[MANUAL_COLUMN], cells[MANUAL_COLUMN + 1])
    return cells_by_id


def read_preamble(markdown: str) -> str:
    """What a person added between the title and the generated header."""
    lines = markdown.splitlines()
    out = []
    for line in lines[1:]:
        if line.startswith("> Generated by `scripts/evaluate.py`"):
            return "\n".join(out).strip("\n")
        out.append(line)
    return ""


def rescore(json_path: Path, log: Callable[[str], None] = print) -> list[str]:
    """Recompute the automatic metrics of an existing report from its stored answers and
    sources (no model call), with the current rules and question files. Keeps timing,
    server data and manual scores; rewrites the JSON and the Markdown next to it,
    keeping the manual column, the notes and any preamble. Returns the summary changes."""
    report = json.loads(json_path.read_text(encoding="utf-8"))
    qfile = ROOT / report["config"]["questions_file"]
    by_id = {q.id: q for q in load_questions(qfile)}
    inventory = load_inventory(question_set_project(qfile), log)
    for r in report["results"]:
        q = by_id[r["id"]]
        old = r["metrics"]
        sr = StreamResult(
            answer=r["answer"], sources=r["sources"], first_token_seconds=old.get("first_token_seconds"),
            total_seconds=old.get("total_seconds"), server=old.get("server"), heartbeats=old.get("heartbeats", 0),
            error=r.get("error"),
        )
        r["metrics"] = score(q, sr, inventory)
    old_summary = report["summary"]
    summary = summarize(report["results"])
    if "manual_correctness" in old_summary:
        summary["manual_correctness"] = old_summary["manual_correctness"]
    report["summary"] = summary
    report["rescored"] = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                          "scoring": SCORING_VERSION}
    changes = [f"{k}: {old_summary.get(k)!r} → {v!r}" for k, v in summary.items() if old_summary.get(k) != v]
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path = json_path.with_suffix(".md")
    old_md = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    md_path.write_text(render_markdown(report, read_preamble(old_md), read_manual_cells(old_md)), encoding="utf-8")
    return changes


def apply_manual(md_path: Path) -> dict:
    """Copy manual scores from <name>.md into <name>.json and add the total to the summary."""
    json_path = md_path.with_suffix(".json")
    report = json.loads(json_path.read_text(encoding="utf-8"))
    scores = read_manual_scores(md_path.read_text(encoding="utf-8"))
    for r in report["results"]:
        r["manual_correctness"] = scores.get(r["id"])
    judged = [r["manual_correctness"] for r in report["results"] if r["manual_correctness"] is not None]
    report["summary"]["manual_correctness"] = {
        "judged": len(judged),
        "of": len(report["results"]),
        "total": sum(judged),
        "max": 2 * len(judged),
    }
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report["summary"]["manual_correctness"]


# ── CLI ────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", default="http://localhost:8080/api",
                   help="API base: the frontend's /api (default, same path as the browser) or the backend, e.g. http://localhost:8000")
    p.add_argument("--top-k", type=int, default=None, help="excerpts per question (default: the server's TOP_K)")
    p.add_argument("--label", help="run name used in the file name, e.g. codespace-3b, mac-14b (required to run)")
    p.add_argument("--only", help="question ids, e.g. 1,9 or 2-4")
    p.add_argument("--lang", choices=["zh", "en"], default="zh", help="question language (default zh)")
    p.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    p.add_argument("--timeout", type=float, default=900.0, help="seconds per question (default 900)")
    p.add_argument("--no-warmup", dest="warmup", action="store_false",
                   help="skip the unscored warm-up query (then question 1 includes model load)")
    p.add_argument("--apply-manual", type=Path, metavar="REPORT.md",
                   help="copy the filled-in 人工判定正確性 column of a report into its JSON, then exit")
    p.add_argument("--rescore", type=Path, nargs="+", metavar="REPORT.json",
                   help="recompute the automatic metrics of existing reports with the current rules "
                        "(no model call; keeps timing, manual scores and notes), then exit")
    p.add_argument("--project", type=Path,
                   help="the indexed project, for checking files and symbols named in answers "
                        "(default: the question file's project:, i.e. the sample project)")
    args = p.parse_args(argv)

    if args.rescore:
        for path in args.rescore:
            try:
                changes = rescore(path)
            except (OSError, ValueError, KeyError) as exc:
                print(f"✗ {path}: {exc}", file=sys.stderr)
                return 2
            print(f"{path}: " + ("; ".join(changes) if changes else "summary unchanged"))
        return 0

    if args.apply_manual:
        try:
            m = apply_manual(args.apply_manual)
        except (OSError, ValueError, KeyError) as exc:
            print(f"✗ {exc}", file=sys.stderr)
            return 2
        print(f"manual correctness: {m['total']}/{m['max']} ({m['judged']} of {m['of']} questions judged)"
              f" → {args.apply_manual.with_suffix('.json')}")
        return 0
    if not args.label:
        p.error("--label is required, e.g. --label codespace-3b")

    questions = load_questions(args.questions)
    only = parse_only(args.only)
    if only:
        unknown = only - {q.id for q in questions}
        if unknown:
            p.error(f"unknown question ids: {sorted(unknown)}")
        questions = [q for q in questions if q.id in only]

    inventory = load_inventory(args.project or question_set_project(args.questions))
    health = get_health(args.base_url)
    if "error" in health:
        print(f"✗ {args.base_url}/health: {health['error']}", file=sys.stderr)
        print("  Is the stack running? Try ./scripts/doctor.sh", file=sys.stderr)
        return 2
    if health.get("status") != "ok":
        print(f"! /health reports status={health.get('status')}; continuing", file=sys.stderr)
    ollama = health.get("ollama") or {}
    print(f"Evaluating {len(questions)} question(s) · {ollama.get('llm_model')} · top_k={args.top_k or health.get('top_k')} · {args.base_url}")
    print(f"Retrieval: {retrieval_label(health.get('retrieval'))}")
    if (health.get("qdrant") or {}).get("reindex_needed"):
        print("! The index was built with other settings (e.g. CHUNK_METADATA); run ./scripts/index.sh first", file=sys.stderr)

    started = datetime.now(timezone.utc)
    results = run(questions, args.base_url, args.top_k, args.lang, args.timeout, args.warmup, inventory=inventory)
    report = {
        "schema": 1,
        "scoring": SCORING_VERSION,
        "date": started.astimezone().date().isoformat(),
        "started_at": started.isoformat(timespec="seconds"),
        "config": {
            "label": args.label,
            "base_url": args.base_url,
            "top_k": args.top_k,
            "lang": args.lang,
            "warmup": args.warmup,
            "only": sorted(only) if only else None,
            "questions_file": str(args.questions.relative_to(ROOT)) if args.questions.is_relative_to(ROOT) else str(args.questions),
            "project": str(inventory.root.relative_to(ROOT)) if inventory and inventory.root.is_relative_to(ROOT)
            else (str(inventory.root) if inventory else None),
        },
        "health": {k: health.get(k) for k in ("status", "ollama", "qdrant", "top_k", "retrieval")},
        "summary": summarize(results),
        "results": results,
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{report['date']}-{slug(args.label)}"
    json_path = args.out_dir / f"{stem}.json"
    md_path = args.out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    s = report["summary"]
    print()
    print(f"first token mean {s['first_token_seconds_mean']}s · total mean {s['total_seconds_mean']}s · "
          f"code hit {_rate_str(s['code_hit'])} · keywords {_pct(s['keyword_rate_mean'])} · "
          f"Simplified {s['simplified_answers']} · refused {_rate_str(s['no_answer_refused'])} · "
          f"falsely refused {_rate_str(s['false_refusals'])} · "
          f"suspected fabrication {_rate_str(s['suspected_fabrication'])} · errors {s['errors']}")
    print(f"→ {json_path}")
    print(f"→ {md_path}  (fill in 人工判定正確性)")
    return 1 if s["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
