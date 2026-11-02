#!/usr/bin/env python3
"""Automated evaluation: ask every question in docs/evaluation/questions.yaml
through the streaming endpoint and score what can be scored automatically.

自動化評估：透過串流查詢端點依序詢問 docs/evaluation/questions.yaml 的題目，
記錄延遲並計算可以自動計算的指標。

    python3 scripts/evaluate.py --label codespace-3b
    python3 scripts/evaluate.py --label mac-14b --top-k 8
    python3 scripts/evaluate.py --label quick --only 1,9 --base-url http://localhost:8000
    python3 scripts/evaluate.py --apply-manual docs/evaluation/results/2026-11-03-codespace-3b.md

Per question: time to first token, total time, tokens (client-side timing), file
hit rate of the retrieved sources (code and documentation separately, plus the
file that defines a setting for 定位設定 questions), keyword hit rate, whether
the answer contains Simplified Chinese characters, and refusals for 陷阱題.

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
WARMUP_QUESTION = "這個專案主要用什麼程式語言寫的？"

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
        if any(a.casefold() in text for a in alternatives):
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


def score(q: Question, r: StreamResult) -> dict:
    files = file_metrics(q, r.sources, r.answer)
    keywords = keyword_metrics(q, r.answer)
    simp = simplified_chars(r.answer)
    out: dict[str, Any] = {
        "first_token_seconds": r.first_token_seconds,
        "total_seconds": r.total_seconds,
        "tokens": (r.server or {}).get("tokens"),
        "server": r.server,
        "heartbeats": r.heartbeats,
        "files": files,
        "keywords": keywords,
        "simplified_chars": simp,
        "has_simplified": bool(simp),
    }
    if q.expect_no_answer:
        # Refusal = a refusal phrase (the keywords) and no sign of invented code.
        out["refused"] = bool(keywords["hit"]) and not keywords["forbidden_hits"]
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
    return {
        "questions": len(results),
        "errors": len(results) - len(ok),
        "first_token_seconds_mean": _mean(x["first_token_seconds"] for x in m),
        "first_token_seconds_median": round(statistics.median(v), 3)
        if (v := [x["first_token_seconds"] for x in m if x["first_token_seconds"] is not None])
        else None,
        "total_seconds_mean": _mean(x["total_seconds"] for x in m),
        "tokens_mean": _mean(x["tokens"] for x in m),
        "file_recall_mean": _mean(x["files"]["all"]["recall"] for x in m),
        "code_hit": _rate(x["files"]["code"]["any"] for x in m),
        "doc_hit": _rate(x["files"]["doc"]["any"] for x in m),
        "definition_hit": _rate(x["files"]["definition"]["any"] for x in m),
        "answer_cited_hit": _rate(x["files"]["answer_cited"]["any"] for x in m),
        "retrieved_doc_share_mean": _mean(x["files"]["retrieved_doc_share"] for x in m),
        "keyword_rate_mean": _mean(x["keywords"]["rate"] for x in m),
        "simplified_answers": sum(x["has_simplified"] for x in m),
        "no_answer_refused": _rate(no_answer),
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
            "sources": [
                {k: s.get(k) for k in ("ref", "file_path", "start_line", "end_line", "symbol", "score")}
                for s in r.sources
            ],
            "error": r.error,
            "metrics": score(q, r),
            "manual_correctness": None,  # 0–2, filled in by a person
        }
        results.append(entry)
        mt = entry["metrics"]
        if r.error:
            log(f"  ✗ {r.error}")
        else:
            log(
                f"  first token {mt['first_token_seconds']}s · total {mt['total_seconds']}s · "
                f"{mt['tokens']} tokens · files {mt['files']['all']['hit']}/{mt['files']['all']['expected']} · "
                f"keywords {mt['keywords']['hit']}/{mt['keywords']['total']}"
                + (f" · Simplified: {''.join(mt['simplified_chars'])}" if mt["has_simplified"] else "")
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
    """One-line summary of the server's retrieval toggles, e.g. 'hybrid + split(doc≤1) + metadata · prompt v2'."""
    if not r:
        return "not reported (server older than ADR 0013: vector only)"
    parts = []
    if r.get("hybrid_search"):
        parts.append(f"hybrid (RRF k={r.get('rrf_k')})")
    if r.get("split_retrieval"):
        parts.append(f"split (docs ≤ {r.get('doc_top_k')})")
    if r.get("chunk_metadata"):
        parts.append("metadata")
    return f"{' + '.join(parts) or 'vector only (baseline)'} · prompt {r.get('prompt_variant', 'v1')}"


def render_markdown(report: dict) -> str:
    s = report["summary"]
    cfg = report["config"]
    h = report.get("health") or {}
    ollama = h.get("ollama") or {}
    top_k = cfg["top_k"] if cfg["top_k"] else "server default ({})".format(h.get("top_k", "?"))
    lines = [
        f"# Evaluation {report['date']} · {cfg['label']}",
        "",
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
        f"| Expected-file recall, mean / 預期檔案命中率平均 | {_pct(s['file_recall_mean'])} |",
        f"| Code file retrieved / 程式碼檔命中 | {_rate_str(s['code_hit'])} |",
        f"| Doc file retrieved / 文件檔命中 | {_rate_str(s['doc_hit'])} |",
        f"| Defining file retrieved (定位設定) / 定義檔命中 | {_rate_str(s['definition_hit'])} |",
        f"| Expected file cited with [n] / 回答以 [n] 引用預期檔案 | {_rate_str(s['answer_cited_hit'])} |",
        f"| Share of retrieved chunks that are docs / 取回片段中文件的比例 | {_pct(s['retrieved_doc_share_mean'])} |",
        f"| Keyword hit rate, mean / 關鍵字命中率平均 | {_pct(s['keyword_rate_mean'])} |",
        f"| Answers with Simplified characters / 混入簡體字的回答 | {s['simplified_answers']} |",
        f"| Trick question refused / 陷阱題正確拒答 | {_rate_str(s['no_answer_refused'])} |",
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
        kw = f"{m['keywords']['hit']}/{m['keywords']['total']}"
        if r["expect_no_answer"]:
            kw += " (refused)" if m.get("refused") else " (**not refused**)"
        lines.append(
            f"| {r['id']} | {r['type']} | {_fmt(m['first_token_seconds'], ' s')} | {_fmt(m['total_seconds'], ' s')} | "
            f"{_fmt(m['tokens'])} | {_ratio(f['all'])} | {_ratio(f['code'])} | {_ratio(f['doc'])} | "
            f"{_ratio(f['definition'])} | {kw} | {''.join(m['simplified_chars']) or '—'} |  |  |"
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
        lines += [
            f"- **Retrieved**: {retrieved or '—'}",
            f"- **Missed expected files**: {', '.join(f'`{x}`' for x in m['files']['all']['missed']) or '—'}",
            f"- **Missed keywords**: {', '.join(f'`{x}`' for x in m['keywords']['missed']) or '—'}",
        ]
        if m["keywords"]["forbidden_hits"]:
            lines.append(f"- **Forbidden keywords found**: {', '.join(m['keywords']['forbidden_hits'])}")
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
    args = p.parse_args(argv)

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
    results = run(questions, args.base_url, args.top_k, args.lang, args.timeout, args.warmup)
    report = {
        "schema": 1,
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
          f"Simplified {s['simplified_answers']} · errors {s['errors']}")
    print(f"→ {json_path}")
    print(f"→ {md_path}  (fill in 人工判定正確性)")
    return 1 if s["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
