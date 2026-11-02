#!/usr/bin/env python3
"""Compare two evaluation results from scripts/evaluate.py (e.g. two models, or two TOP_K values).

比較兩份 scripts/evaluate.py 的結果（例如不同模型或不同 TOP_K），輸出 Markdown 差異表。

    python3 scripts/compare.py docs/evaluation/results/2026-11-03-codespace-3b-k4.json \\
                               docs/evaluation/results/2026-11-03-codespace-3b-k8.json
    python3 scripts/compare.py A.json B.json --out docs/evaluation/results/k4-vs-k8.md

Δ is B − A. Only questions present in both files are compared per question.
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

# (label, getter, kind) — kind decides formatting and which direction is "better".
#   seconds: lower is better · rate: higher is better · count-lower: lower is better
SUMMARY_ROWS: list[tuple[str, Callable[[dict], Any], str]] = [
    ("Time to first token, mean / 首字延遲平均", lambda s: s.get("first_token_seconds_mean"), "seconds"),
    ("Time to first token, median / 首字延遲中位數", lambda s: s.get("first_token_seconds_median"), "seconds"),
    ("Total time, mean / 總耗時平均", lambda s: s.get("total_seconds_mean"), "seconds"),
    ("Tokens, mean / 平均 token 數", lambda s: s.get("tokens_mean"), "number"),
    ("Expected-file recall / 預期檔案命中率", lambda s: s.get("file_recall_mean"), "rate"),
    ("Code file retrieved / 程式碼檔命中", lambda s: (s.get("code_hit") or {}).get("rate"), "rate"),
    ("Doc file retrieved / 文件檔命中", lambda s: (s.get("doc_hit") or {}).get("rate"), "rate"),
    ("Defining file retrieved / 定義檔命中", lambda s: (s.get("definition_hit") or {}).get("rate"), "rate"),
    ("Expected file cited with [n] / 回答引用預期檔案", lambda s: (s.get("answer_cited_hit") or {}).get("rate"), "rate"),
    ("Docs among retrieved chunks / 取回片段中文件比例", lambda s: s.get("retrieved_doc_share_mean"), "share"),
    ("Keyword hit rate / 關鍵字命中率", lambda s: s.get("keyword_rate_mean"), "rate"),
    ("Answers with Simplified / 混入簡體字的回答", lambda s: s.get("simplified_answers"), "count-lower"),
    ("Trick question refused / 陷阱題正確拒答", lambda s: (s.get("no_answer_refused") or {}).get("rate"), "rate"),
    ("Manual correctness / 人工判定正確性", lambda s: (s.get("manual_correctness") or {}).get("total"), "number"),
    ("Errors / 失敗題數", lambda s: s.get("errors"), "count-lower"),
]


def load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != 1:
        sys.exit(f"{path}: unsupported schema {data.get('schema')!r} (expected 1)")
    return data


def fmt(v: Any, kind: str) -> str:
    if v is None:
        return "—"
    if kind == "seconds":
        return f"{v:.1f} s"
    if kind in ("rate", "share"):
        return f"{v * 100:.0f}%"
    if isinstance(v, float):
        return f"{v:.1f}"
    return str(v)


def delta(a: Any, b: Any, kind: str) -> str:
    """B − A, with ▲/▼ marking better/worse where the direction is clear."""
    if a is None or b is None:
        return "—"
    d = b - a
    # Below the displayed precision counts as no change (avoids "-0.0 s ▲").
    precision = {"seconds": 0.05, "rate": 0.005, "share": 0.005}.get(kind, 0.05 if isinstance(d, float) else 0.5)
    if abs(d) < precision:
        return "0"
    if kind == "seconds":
        text = f"{d:+.1f} s"
    elif kind in ("rate", "share"):
        text = f"{d * 100:+.0f} pt"
    elif isinstance(d, float):
        text = f"{d:+.1f}"
    else:
        text = f"{d:+d}"
    better = {"seconds": d < 0, "rate": d > 0, "count-lower": d < 0}.get(kind)
    if better is None:
        return text
    return f"{text} {'▲' if better else '▼'}"


def describe(r: dict) -> str:
    cfg = r.get("config", {})
    ollama = (r.get("health") or {}).get("ollama") or {}
    top_k = cfg.get("top_k") or f"default {(r.get('health') or {}).get('top_k', '?')}"
    return f"`{cfg.get('label')}` · {r.get('date')} · {ollama.get('llm_model', '?')} · top_k {top_k} · {cfg.get('lang', '?')}"


def per_question(a: dict, b: dict) -> list[str]:
    qa = {q["id"]: q for q in a["results"]}
    qb = {q["id"]: q for q in b["results"]}
    ids = sorted(set(qa) & set(qb))
    rows = [
        "| # | Type | First token A → B | Total A → B | Files A → B | Code A → B | Def. A → B | Keywords A → B | Simplified A / B | Manual A / B |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    def files(q: dict, key: str) -> str:
        if q.get("error"):
            return "✗"
        h = q["metrics"]["files"][key]
        return f"{h['hit']}/{h['expected']}" if h["expected"] else "—"

    def secs(q: dict, key: str) -> str:
        return "✗" if q.get("error") else fmt(q["metrics"].get(key), "seconds")

    def kw(q: dict) -> str:
        if q.get("error"):
            return "✗"
        k = q["metrics"]["keywords"]
        return f"{k['hit']}/{k['total']}"

    def simp(q: dict) -> str:
        return "✗" if q.get("error") else ("".join(q["metrics"]["simplified_chars"]) or "—")

    def manual(q: dict) -> str:
        v = q.get("manual_correctness")
        return "—" if v is None else str(v)

    for i in ids:
        x, y = qa[i], qb[i]
        rows.append(
            f"| {i} | {x['type']} | {secs(x, 'first_token_seconds')} → {secs(y, 'first_token_seconds')} | "
            f"{secs(x, 'total_seconds')} → {secs(y, 'total_seconds')} | {files(x, 'all')} → {files(y, 'all')} | "
            f"{files(x, 'code')} → {files(y, 'code')} | {files(x, 'definition')} → {files(y, 'definition')} | "
            f"{kw(x)} → {kw(y)} | {simp(x)} / {simp(y)} | {manual(x)} / {manual(y)} |"
        )
    only = sorted(set(qa) ^ set(qb))
    if only:
        rows += ["", f"Not in both runs (not compared): {', '.join(map(str, only))}"]
    return rows


def compare(a: dict, b: dict) -> str:
    sa, sb = a["summary"], b["summary"]
    lines = [
        "# Evaluation comparison / 評估比較",
        "",
        f"- **A**: {describe(a)}",
        f"- **B**: {describe(b)}",
        "",
        "Δ = B − A. ▲ better, ▼ worse. Automatic metrics are proxies, not correctness (ADR 0012).",
        "Δ = B − A。▲ 較好、▼ 較差。自動指標只是代理指標，不等於回答正確（ADR 0012）。",
        "",
        "## Summary / 摘要",
        "",
        "| Metric / 指標 | A | B | Δ |",
        "| --- | --- | --- | --- |",
    ]
    for label, get, kind in SUMMARY_ROWS:
        va, vb = get(sa), get(sb)
        lines.append(f"| {label} | {fmt(va, kind)} | {fmt(vb, kind)} | {delta(va, vb, kind)} |")
    lines += ["", "## Per question / 每題", ""] + per_question(a, b)
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("a", type=Path, help="result JSON A (baseline)")
    p.add_argument("b", type=Path, help="result JSON B")
    p.add_argument("--out", type=Path, help="also write the Markdown to this file")
    args = p.parse_args(argv)
    text = compare(load(args.a), load(args.b))
    print(text, end="")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"→ {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
