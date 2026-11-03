#!/usr/bin/env python3
"""Summary Markdown for scripts/benchmark-mac.sh.

Reads the evaluate.py reports of one benchmark run plus the measurements the
shell script passes in BENCH_* environment variables, and prints Markdown
whose tables have the same columns as docs/metrics.md §2, §3, §4, §4a and §5
(English tables first, then the Traditional Chinese ones), so rows can be
pasted as they are. Values that were not measured are printed as {待填}.

    BENCH_OUT_DIR=docs/evaluation/results BENCH_DATE=2026-11-10 ... python3 scripts/benchmark_summary.py

Only the Python standard library is used (runs with -I).
"""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path

TODO = "{待填}"
ROOT = Path(__file__).resolve().parent.parent
METRICS_RESULTS = ROOT / "docs" / "evaluation" / "results"

GROUP_NAMES = {
    "baseline": ("A. baseline", "A. 基準線"),
    "hybrid-split": ("D. + hybrid + split", "D. + 混合 + 分類"),
    "hybrid-split-rerank": ("I. hybrid + split + rerank", "I. 混合 + 分類 + Rerank"),
}


def env(name: str, default: str = "") -> str:
    return os.environ.get(f"BENCH_{name}", default).strip()


def or_todo(v: object) -> str:
    return TODO if v in (None, "") else str(v)


def num(v: str) -> str:
    """'20.34 tokens/s' → '20.34'; '' → {待填}."""
    m = re.match(r"[0-9.]+", v or "")
    return m.group(0) if m else TODO


def f1(v: float | None) -> str:
    return TODO if v is None else f"{v:.1f}"


def pct(v: float | None) -> str:
    # Round half up (0.225 → 23%), like the numbers already in docs/metrics.md.
    return TODO if v is None else f"{math.floor(v * 100 + 0.5)}%"


def rate(r: dict | None) -> str:
    if not r or not r.get("of"):
        return "—"
    return f"{r['hit']}/{r['of']} ({pct(r['rate'])})"


def p90(values: list[float]) -> float | None:
    """Nearest-rank 90th percentile."""
    v = sorted(values)
    return v[max(0, math.ceil(0.9 * len(v)) - 1)] if v else None


class Run:
    def __init__(self, out_dir: Path, date: str, label: str) -> None:
        self.json_path = out_dir / f"{date}-{label}.json"
        self.md_path = self.json_path.with_suffix(".md")
        self.data = json.loads(self.json_path.read_text(encoding="utf-8")) if self.json_path.exists() else None

    @property
    def ok(self) -> bool:
        return self.data is not None

    @property
    def s(self) -> dict:
        return (self.data or {}).get("summary") or {}

    def totals(self) -> list[float]:
        return [
            r["metrics"]["total_seconds"]
            for r in (self.data or {}).get("results", [])
            if not r.get("error") and r["metrics"].get("total_seconds") is not None
        ]

    def manual(self) -> str:
        m = self.s.get("manual_correctness")
        if m and m.get("judged") and m.get("judged") == m.get("of"):
            return f"{m['total']}/{m['max']}"
        return TODO

    def link(self, text: str) -> str:
        """Link relative to docs/metrics.md when the report is in docs/evaluation/results/."""
        try:
            rel = self.md_path.resolve().relative_to(METRICS_RESULTS)
            return f"[{text}](evaluation/results/{rel.as_posix()})"
        except ValueError:
            pass
        try:  # e.g. a --quick run under .logs/
            return f"[{text}]({self.md_path.resolve().relative_to(ROOT).as_posix()})"
        except ValueError:
            return f"[{text}]({self.md_path.as_posix()})"


def refused(r: dict | None, zh: bool) -> str:
    if not r or not r.get("of"):
        return "—"
    yes = r["hit"] == r["of"]
    if zh:
        return f"{'是' if yes else '否'}（{r['hit']}/{r['of']}）"
    return f"{'Yes' if yes else 'No'} ({r['hit']}/{r['of']})"


def pair(a: Run, b: Run, key: str, fmt=f1) -> str:
    va = a.s.get(key) if a.ok else None
    vb = b.s.get(key) if b.ok else None
    if va is None and vb is None:
        return "—"
    return f"{fmt(va) if va is not None else '—'} / {fmt(vb) if vb is not None else '—'}"


def main() -> None:
    out_dir = Path(env("OUT_DIR", "docs/evaluation/results"))
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    date = env("DATE")
    prefix = env("PREFIX", "mac-m2-14b-k8")
    groups = env("GROUPS", "baseline hybrid-split").split()
    quick = env("QUICK") == "1"
    llm = env("LLM", "qwen2.5-coder:14b")
    embed = env("EMBED", "nomic-embed-text")
    top_k = env("TOP_K", "8")
    num_ctx = env("NUM_CTX", "16384")
    chip = env("CHIP", "Apple M2").replace("Apple ", "Mac ")
    mem = env("MEM_GB")
    machine = f"{chip} {mem} GB" if mem else chip
    machine_zh = f"{chip} {mem}GB" if mem else chip

    runs = {g: (Run(out_dir, date, f"{prefix}-{g}"), Run(out_dir, date, f"{prefix}-{g}-ident")) for g in groups}
    base, base_id = runs.get("baseline", (None, None))
    n_main = base.s.get("questions") if base and base.ok else None

    switches = {
        "baseline": ("all off", "全部關閉"),
        "hybrid-split": ("`HYBRID_SEARCH`, `SPLIT_RETRIEVAL`, `DOC_TOP_K=1`", "`HYBRID_SEARCH`、`SPLIT_RETRIEVAL`、`DOC_TOP_K=1`"),
        "hybrid-split-rerank": (
            f"`HYBRID_SEARCH`, `SPLIT_RETRIEVAL`, `DOC_TOP_K=1`, `RERANK`, {env('RERANK_CANDIDATES', '20')} → {top_k}",
            f"`HYBRID_SEARCH`、`SPLIT_RETRIEVAL`、`DOC_TOP_K=1`、`RERANK`，{env('RERANK_CANDIDATES', '20')} → {top_k}",
        ),
    }

    gpu = env("EVAL_PROC") or env("RUN_PROC")
    gpu_en = TODO if not gpu else ("Yes" if gpu == "100% GPU" else "Partly" if "GPU" in gpu else "No") + f" ({gpu})"
    gpu_zh = TODO if not gpu else ("是" if gpu == "100% GPU" else "部分" if "GPU" in gpu else "否") + f"（{gpu}）"
    mem_used = env("EVAL_MEM") or env("RUN_MEM")
    mem_note_en = f"{mem_used} (`LLM_NUM_CTX={num_ctx}`)" if env("EVAL_MEM") else (f"{mem_used} (default context)" if mem_used else TODO)
    mem_note_zh = f"{mem_used}（`LLM_NUM_CTX={num_ctx}`）" if env("EVAL_MEM") else (f"{mem_used}（預設上下文）" if mem_used else TODO)

    L: list[str] = []
    w = L.append

    w(f"# Mac benchmark {date} · {prefix}")
    w("")
    w("> Generated by `scripts/benchmark-mac.sh` (ADR 0016). English first; 繁體中文版本在下方.")
    w("> Paste the English rows into the English half of `docs/metrics.md` and the Chinese rows into the Chinese half.")
    w("> Manual correctness stays {待填} until a person judges the answers and runs `evaluate.py --apply-manual`.")
    w("> 由 `scripts/benchmark-mac.sh` 產生（ADR 0016）。英文表格貼到 `docs/metrics.md` 的英文段，中文表格貼到中文段。")
    w("> 人工判定正確性在有人讀過回答並執行 `evaluate.py --apply-manual` 之前保持 {待填}。")
    w("")
    if quick:
        w("> ⚠️ **`--quick` run**: 3 questions per set. Do **not** paste these numbers into `docs/metrics.md`.")
        w("> ⚠️ **`--quick` 執行**：每個題組只有 3 題，**不要**貼到 `docs/metrics.md`。")
        w("")

    w("## Environment / 環境")
    w("")
    w("| Item | Value |")
    w("| --- | --- |")
    w(f"| Machine | {chip}, {or_todo(mem)} GB, macOS {or_todo(env('MACOS'))} |")
    w(f"| Ollama | {or_todo(env('OLLAMA'))} (native on macOS, Metal) |")
    w(f"| Models | `{llm}` ({or_todo(env('LLM_DOWNLOAD'))} on disk) / `{embed}` |")
    w(f"| `TOP_K` / `LLM_NUM_CTX` | {top_k} / {num_ctx} |")
    w(f"| Groups | {', '.join(f'`{prefix}-{g}`' for g in groups)} |")
    w(f"| Raw logs (not committed) | `{env('LOG_DIR')}/` |")
    w("")

    # ── English tables ────────────────────────────────────────────────
    w("## English tables")
    w("")
    w("### §2 Indexing")
    w("")
    w("| Date | Environment | Project | Files | Chunks | Full index (s) | Incremental, no changes (s) | Embedding model |")
    w("| --- | --- | --- | --- | --- | --- | --- | --- |")
    w(f"| {date} | {machine} | Sample | {or_todo(env('FILES'))} | {or_todo(env('CHUNKS'))} | {or_todo(env('FULL_SECONDS'))} | {or_todo(env('INCR_SECONDS'))} | {embed} |")
    w("")

    def latency_rows(zh: bool) -> None:
        for g in groups:
            m, _ = runs[g]
            if not m.ok:
                continue
            first = env("FIRST_QUERY") if g == "baseline" else ""
            label = GROUP_NAMES[g][1 if zh else 0]
            n = m.s.get("questions")
            if zh:
                note = f"{label}，{n} 題，`LLM_NUM_CTX={num_ctx}`" + ("；第一次查詢 = 卸載模型後的暖機題" if first else "") + f"；{m.link('報告')}"
                env_txt = f"{machine_zh}，`scripts/evaluate.py`"
            else:
                note = f"{label}, {n} questions, `LLM_NUM_CTX={num_ctx}`" + ("; first query = warm-up after unloading the model" if first else "") + f"; {m.link('report')}"
                env_txt = f"{machine}, `scripts/evaluate.py`"
            w(f"| {date} | {env_txt} | {llm} | {top_k} | {first or '—'} | {f1(m.s.get('total_seconds_mean'))} | {f1(p90(m.totals()))} | {f1(m.s.get('first_token_seconds_mean'))} | {note} |")

    w("### §3 Query latency")
    w("")
    w("| Date | Environment | Model | top_k | First query (s) | Avg of 10 queries (s) | p90 (s) | Time to first token, avg (s) | Notes |")
    w("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    latency_rows(zh=False)
    w("")

    def eval_row(zh: bool) -> None:
        if not (base and base.ok):
            return
        s = base.s
        w(
            f"| {date} | {chip} | {llm} | {top_k} | {base.manual()} | {rate(s.get('code_hit'))} | {rate(s.get('definition_hit'))} | "
            f"{pct(s.get('keyword_rate_mean'))} | {s.get('simplified_answers', TODO)} | {refused(s.get('no_answer_refused'), zh)} | "
            f"{f1(s.get('first_token_seconds_mean'))} | {f1(s.get('total_seconds_mean'))} | {base.link('報告' if zh else 'report')} |"
        )

    w("### §4 Evaluation results (baseline, main set)")
    w("")
    w("| Date | Environment | Model | top_k | Manual correctness (/20) | Code file retrieved | Defining file retrieved | Keyword hit rate | Answers with Simplified | Q10 refused | First token, mean (s) | Total, mean (s) | Report |")
    w("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    eval_row(zh=False)
    w("")

    def switch_rows(zh: bool) -> None:
        for g in groups:
            m, i = runs[g]
            if not (m.ok or i.ok):
                continue
            name = f"{GROUP_NAMES[g][1 if zh else 0]} · {machine_zh if zh else machine}, {llm.split(':')[-1]}, k{top_k}"
            links = " · ".join(
                x.link(t) for x, t in ((m, "主要" if zh else "main"), (i, "識別字" if zh else "ident.")) if x.ok
            )
            w(
                f"| {date} | {name} | {switches[g][1 if zh else 0]} | {m.manual() if m.ok else TODO} | "
                f"{rate(m.s.get('definition_hit')) if m.ok else '—'} | {rate(i.s.get('definition_hit')) if i.ok else '—'} | "
                f"{rate(m.s.get('code_hit')) if m.ok else '—'} | {pct(m.s.get('retrieved_doc_share_mean')) if m.ok else '—'} | "
                f"{pair(m, i, 'simplified_answers', fmt=str)} | {refused(m.s.get('no_answer_refused'), zh) if m.ok else '—'} | "
                f"{pair(m, i, 'first_token_seconds_mean')} | {pair(m, i, 'rerank_seconds_mean')} | {links} |"
            )

    w("### §4a Retrieval switches")
    w("")
    w("| Date | Group | Switches | Manual correctness, main (/20) | Defining file retrieved, main | Defining file retrieved, ident. | Code file retrieved, main | Docs among retrieved chunks, main | Answers with Simplified | Q10 refused | First token, mean (s) | Rerank time, mean (s) | Report |")
    w("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    switch_rows(zh=False)
    w("")
    w("\"Answers with Simplified\", \"First token\" and \"Rerank time\" are main / ident.")
    w("")

    tokens = num(env("WARM_EVAL_RATE"))
    avg_query = f1(base.s.get("total_seconds_mean")) if base and base.ok else TODO
    w("### §5 Model comparison")
    w("")
    w("| Model | Download size | Memory in use (`ollama ps`) | Runs on GPU? | Tokens/s (generation) | Avg query (s) | Eval score (/20) | Citation accuracy | Subjective quality notes |")
    w("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    w(f"| {llm} | {or_todo(env('LLM_DOWNLOAD'))} | {mem_note_en} | {gpu_en} | {tokens} | {avg_query} | {base.manual() if base and base.ok else TODO} | {TODO} | {TODO} |")
    w("")

    # ── Chinese tables ────────────────────────────────────────────────
    w("## 中文表格")
    w("")
    w("### §2 索引")
    w("")
    w("| 日期 | 環境 | 專案 | 檔案數 | 片段數 | 完整索引（秒） | 無變更增量索引（秒） | Embedding 模型 |")
    w("| --- | --- | --- | --- | --- | --- | --- | --- |")
    w(f"| {date} | {machine_zh} | 範例專案 | {or_todo(env('FILES'))} | {or_todo(env('CHUNKS'))} | {or_todo(env('FULL_SECONDS'))} | {or_todo(env('INCR_SECONDS'))} | {embed} |")
    w("")
    w("### §3 查詢時間")
    w("")
    w("| 日期 | 環境 | 模型 | top_k | 第一次查詢（秒） | 10 次平均（秒） | p90（秒） | 首字延遲平均（秒） | 備註 |")
    w("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    latency_rows(zh=True)
    w("")
    w("### §4 評估結果（基準線，主要題組）")
    w("")
    w("| 日期 | 環境 | 模型 | top_k | 人工判定正確性（/20） | 程式碼檔命中 | 定義檔命中 | 關鍵字命中率 | 混入簡體字的回答 | 第 10 題拒答 | 首字延遲平均（秒） | 總耗時平均（秒） | 報告 |")
    w("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    eval_row(zh=True)
    w("")
    w("### §4a 檢索開關")
    w("")
    w("| 日期 | 組別 | 開關 | 人工判定正確性，主要（/20） | 定義檔命中，主要 | 定義檔命中，識別字 | 程式碼檔命中，主要 | 取回片段中文件比例，主要 | 混入簡體字的回答 | Q10 拒答 | 首字延遲平均（秒） | rerank 耗時平均（秒） | 報告 |")
    w("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    switch_rows(zh=True)
    w("")
    w("「混入簡體字的回答」、「首字延遲」與「rerank 耗時」的格式為 主要 / 識別字。")
    w("")
    w("### §5 模型比較")
    w("")
    w("| 模型 | 下載大小 | 實際記憶體（`ollama ps`） | 是否在 GPU 上執行 | 生成速度（tokens/s） | 平均查詢（秒） | 評估分數（/20） | 引用正確率 | 主觀品質備註 |")
    w("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    w(f"| {llm} | {or_todo(env('LLM_DOWNLOAD'))} | {mem_note_zh} | {gpu_zh} | {tokens} | {avg_query} | {base.manual() if base and base.ok else TODO} | {TODO} | {TODO} |")
    w("")

    # ── Raw measurements ──────────────────────────────────────────────
    w("## Raw measurements / 原始量測")
    w("")
    w("`ollama run --verbose` (cold = model unloaded first, short prompt; warm = model loaded, prompt with the sample project's `Player.ts`):")
    w("`ollama run --verbose`（冷啟動 = 先卸載模型、短提示；暖機後 = 模型已載入、提示含範例專案的 `Player.ts`）：")
    w("")
    w("| Run / 執行 | Load / 載入 | Total / 總計 | Prompt eval rate | Eval rate | Prompt / eval tokens |")
    w("| --- | --- | --- | --- | --- | --- |")
    w(f"| cold / 冷啟動 | {or_todo(env('COLD_LOAD'))} | {or_todo(env('COLD_TOTAL'))} | {or_todo(env('COLD_PROMPT_RATE'))} | {or_todo(env('COLD_EVAL_RATE'))} | — |")
    w(f"| warm / 暖機後 | — | — | {or_todo(env('WARM_PROMPT_RATE'))} | {or_todo(env('WARM_EVAL_RATE'))} | {or_todo(env('WARM_PROMPT_COUNT'))} / {or_todo(env('WARM_EVAL_COUNT'))} |")
    w("")
    w("| Item / 項目 | Value / 數值 |")
    w("| --- | --- |")
    w(f"| `ollama ps` after `ollama run` (default context) / `ollama run` 後 | {or_todo(env('RUN_MEM'))}, {or_todo(env('RUN_PROC'))} |")
    w(f"| `ollama ps` after the baseline main set (`LLM_NUM_CTX={num_ctx}`) / 基準線主要題組後 | {or_todo(env('EVAL_MEM'))}, {or_todo(env('EVAL_PROC'))} |")
    w(f"| System memory free (`memory_pressure`) / 系統可用記憶體 | {or_todo(env('MEM_FREE'))} |")
    w(f"| Full index: indexer / wall clock incl. `docker compose up` (s) / 全量索引：索引器／牆鐘 | {or_todo(env('FULL_SECONDS'))} / {or_todo(env('FULL_WALL'))} |")
    w(f"| Incremental, no changes: indexer / wall clock (s) / 增量：索引器／牆鐘 | {or_todo(env('INCR_SECONDS'))} / {or_todo(env('INCR_WALL'))} |")
    w(f"| Files scanned / skipped (too large) / 掃描／略過的檔案 | {or_todo(env('FILES'))} / {or_todo(env('SKIPPED'))} |")
    w(f"| First query after model load (s) / 模型載入後第一次查詢 | {or_todo(env('FIRST_QUERY'))} |")
    w("")

    w("## Reports / 報告")
    w("")
    for g in groups:
        for r in runs[g]:
            w(f"- `{r.md_path.name}`" + ("" if r.ok else " — **missing / 缺少**"))
    for cmp in sorted(out_dir.glob(f"{date}-{prefix}-*-vs-*.md")):
        w(f"- `{cmp.name}`")
    w("")
    if n_main is not None and not quick and n_main != 10:
        w(f"> ⚠️ The baseline main set has {n_main} questions instead of 10. / 基準線主要題組只有 {n_main} 題。")
        w("")
    print("\n".join(L))


if __name__ == "__main__":
    main()
