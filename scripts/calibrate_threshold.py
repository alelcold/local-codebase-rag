#!/usr/bin/env python3
"""Pick SCORE_THRESHOLD from evaluation results instead of guessing (ADR 0014).

從評估結果決定 SCORE_THRESHOLD，而不是套用通用值（ADR 0014）。

    python3 scripts/calibrate_threshold.py                      # every report in docs/evaluation/results/
    python3 scripts/calibrate_threshold.py results/A.json results/B.json --out calibration.md
    python3 scripts/calibrate_threshold.py --candidates 0.45,0.5,0.55 --max-drop 0

Reads the JSON reports written by scripts/evaluate.py and takes the cosine
similarity of every retrieved excerpt:

- ``vector_score`` (reports written since ADR 0014), or
- ``score`` from runs without HYBRID_SEARCH, where ``score`` *is* the cosine
  (with hybrid search ``score`` is an RRF score and is ignored).

Each excerpt is labelled **expected** (its file is in the question's
``expected_files``) or **not expected** (any other file, and every excerpt of a
trick question). "Not expected" is an approximation of "irrelevant":
``expected_files`` lists the main files, so a helpful neighbour counts as not
expected too.

For each candidate threshold it prints how many expected excerpts would be
dropped, how many not-expected ones blocked, which questions would lose *all*
their expected excerpts, and whether trick questions would be refused (every
excerpt below the threshold). The suggestion is the highest candidate that keeps
at least one expected excerpt for every question and drops at most --max-drop
of the expected excerpts. With too little data it says so and suggests nothing.

Runs made with SCORE_THRESHOLD set are skipped (excerpts under that threshold
are missing from them, which would bias the result) unless --include-thresholded.
Thresholds depend on what was embedded: reports are grouped by EMBED_MODEL and
CHUNK_METADATA (the metadata header changes every chunk's vector), so groups
A–D and G–H (no metadata) and E, F and I (metadata) are calibrated separately.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RESULTS = ROOT / "docs" / "evaluation" / "results"
DEFAULT_CANDIDATES = [round(0.30 + 0.05 * i, 2) for i in range(11)]  # 0.30 … 0.80


@dataclass(frozen=True)
class Sample:
    question: str
    file_path: str
    location: str
    cosine: float
    expected: bool
    trick: bool


@dataclass
class Group:
    embed_model: str
    reports: list[str] = field(default_factory=list)
    samples: list[Sample] = field(default_factory=list)


def cosine_of(source: dict, retrieval: dict | None) -> float | None:
    """The excerpt's cosine similarity, or None when the report does not have it."""
    if "vector_score" in source:
        v = source["vector_score"]
        return float(v) if v is not None else None
    # Older report: ``score`` is the cosine only when hybrid search was off.
    if not (retrieval or {}).get("hybrid_search") and source.get("score") is not None:
        return float(source["score"])
    return None


def load_samples(paths: list[Path], include_thresholded: bool = False) -> tuple[dict[str, Group], list[str]]:
    """Group samples by embedding model; returns (groups, notes about skipped files)."""
    groups: dict[str, Group] = {}
    notes: list[str] = []
    seen: set[tuple] = set()
    for path in paths:
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            notes.append(f"{path.name}: unreadable ({exc})")
            continue
        if "results" not in report:
            notes.append(f"{path.name}: not an evaluate.py report")
            continue
        health = report.get("health") or {}
        retrieval = health.get("retrieval")
        if (retrieval or {}).get("score_threshold") is not None and not include_thresholded:
            notes.append(f"{path.name}: skipped, run with SCORE_THRESHOLD={retrieval['score_threshold']}")
            continue
        model = (health.get("ollama") or {}).get("embed_model") or "unknown"
        if (retrieval or {}).get("chunk_metadata"):
            model += " + CHUNK_METADATA"
        group = groups.setdefault(model, Group(model))
        group.reports.append(path.name)
        before = len(group.samples)
        for r in report["results"]:
            if r.get("error"):
                continue
            expected = set(r.get("expected_files") or [])
            trick = bool(r.get("expect_no_answer"))
            for s in r.get("sources") or []:
                c = cosine_of(s, retrieval)
                if c is None:
                    continue
                loc = f"{s.get('file_path')}:{s.get('start_line')}-{s.get('end_line')}"
                key = (model, r.get("question"), loc, round(c, 4))
                if key in seen:  # the same excerpt for the same question in another run
                    continue
                seen.add(key)
                group.samples.append(
                    Sample(
                        question=str(r.get("question")),
                        file_path=str(s.get("file_path")),
                        location=loc,
                        cosine=c,
                        expected=(s.get("file_path") in expected) and not trick,
                        trick=trick,
                    )
                )
        if len(group.samples) == before:
            notes.append(f"{path.name}: no cosine scores (hybrid run written before vector_score existed?)")
    return groups, notes


@dataclass
class Row:
    threshold: float
    expected_dropped: int
    expected_total: int
    other_blocked: int
    other_total: int
    questions_losing_all: list[str]
    trick_refused: int
    trick_total: int

    @property
    def drop_rate(self) -> float:
        return self.expected_dropped / self.expected_total if self.expected_total else 0.0

    @property
    def block_rate(self) -> float:
        return self.other_blocked / self.other_total if self.other_total else 0.0


def evaluate_threshold(samples: list[Sample], t: float) -> Row:
    expected = [s for s in samples if s.expected]
    other = [s for s in samples if not s.expected]
    by_question: dict[str, list[Sample]] = {}
    for s in expected:
        by_question.setdefault(s.question, []).append(s)
    losing = sorted(q for q, xs in by_question.items() if all(x.cosine < t for x in xs))
    trick: dict[str, list[float]] = {}
    for s in samples:
        if s.trick:
            trick.setdefault(s.question, []).append(s.cosine)
    return Row(
        threshold=t,
        expected_dropped=sum(s.cosine < t for s in expected),
        expected_total=len(expected),
        other_blocked=sum(s.cosine < t for s in other),
        other_total=len(other),
        questions_losing_all=losing,
        trick_refused=sum(max(v) < t for v in trick.values()),
        trick_total=len(trick),
    )


@dataclass
class Recommendation:
    threshold: float | None
    reason: str


def recommend(
    samples: list[Sample], rows: list[Row], max_drop: float, min_samples: int
) -> Recommendation:
    n_expected = sum(s.expected for s in samples)
    n_other = len(samples) - n_expected
    questions = len({s.question for s in samples if s.expected})
    if n_expected < min_samples or n_other < min_samples or questions < 3:
        return Recommendation(
            None,
            f"Not enough data / 資料不足: {n_expected} expected and {n_other} not-expected excerpts "
            f"from {questions} question(s); need at least {min_samples} of each and 3 questions. "
            "Run more groups of the experiment plan (A–F) first. "
            "Keep SCORE_THRESHOLD empty until then.",
        )
    ok = [r for r in rows if not r.questions_losing_all and r.drop_rate <= max_drop]
    if not ok:
        return Recommendation(
            None,
            "No candidate keeps an expected excerpt for every question within --max-drop. "
            "The score distributions overlap: a threshold would cost correct answers. "
            "沒有任何候選值能在容許範圍內保留每一題的預期片段：分數分布重疊，門檻會犧牲正確回答。",
        )
    best = max(ok, key=lambda r: r.threshold)
    if best.other_blocked == 0:
        return Recommendation(
            None,
            f"Every safe candidate (≤ {best.threshold}) blocks no not-expected excerpt: a threshold would do "
            "nothing on this data. 安全的候選值都擋不到任何非預期片段，門檻在這些資料上沒有作用。",
        )
    reason = (
        f"Highest candidate that keeps an expected excerpt for every question and drops "
        f"{best.expected_dropped}/{best.expected_total} expected excerpts (≤ {max_drop:.0%}); "
        f"it blocks {best.other_blocked}/{best.other_total} not-expected excerpts"
    )
    if best.trick_total:
        reason += f" and would refuse {best.trick_refused}/{best.trick_total} trick question(s)"
        if best.trick_refused < best.trick_total:
            reason += (
                " — not all: a trick question's best excerpt scores as high as real answers, "
                "so the threshold alone cannot guarantee the refusal"
            )
    return Recommendation(best.threshold, reason + ".")


def _stats(values: list[float]) -> str:
    if not values:
        return "—"
    v = sorted(values)
    q = statistics.quantiles(v, n=4) if len(v) >= 2 else [v[0]] * 3
    return f"n={len(v)} · min {v[0]:.3f} · p25 {q[0]:.3f} · median {q[1]:.3f} · p75 {q[2]:.3f} · max {v[-1]:.3f}"


def render(group: Group, rows: list[Row], rec: Recommendation) -> str:
    samples = group.samples
    expected = [s.cosine for s in samples if s.expected]
    other = [s.cosine for s in samples if not s.expected and not s.trick]
    trick = [s.cosine for s in samples if s.trick]
    lines = [
        f"## Embedding `{group.embed_model}`",
        "",
        f"Reports ({len(group.reports)}): " + ", ".join(f"`{r}`" for r in group.reports),
        "",
        "### Cosine distribution / 分數分布",
        "",
        "| Excerpts / 片段 | Cosine |",
        "| --- | --- |",
        f"| Expected file / 預期檔案 | {_stats(expected)} |",
        f"| Other file / 非預期檔案 | {_stats(other)} |",
        f"| Trick question (should be refused) / 陷阱題 | {_stats(trick)} |",
        "",
        "Lowest expected excerpts (what a threshold would cut first) / 分數最低的預期片段：",
        "",
    ]
    for s in sorted((s for s in samples if s.expected), key=lambda s: s.cosine)[:5]:
        lines.append(f"- {s.cosine:.3f} `{s.location}` — {s.question}")
    lines += [
        "",
        "### Candidates / 候選門檻",
        "",
        "| Threshold | Expected dropped / 丟掉的正確片段 | Not-expected blocked / 擋掉的非預期片段 | Questions losing every expected excerpt / 失去所有預期片段的題目 | Trick refused / 陷阱題拒答 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        mark = " **←**" if rec.threshold == r.threshold else ""
        lines.append(
            f"| {r.threshold:.2f}{mark} | {r.expected_dropped}/{r.expected_total} ({r.drop_rate:.0%}) | "
            f"{r.other_blocked}/{r.other_total} ({r.block_rate:.0%}) | "
            f"{len(r.questions_losing_all)}{': ' + '; '.join(r.questions_losing_all) if r.questions_losing_all else ''} | "
            f"{r.trick_refused}/{r.trick_total} |"
        )
    lines += ["", "### Suggestion / 建議", ""]
    if rec.threshold is None:
        lines.append(f"**No value suggested / 不建議數值.** {rec.reason}")
    else:
        lines.append(f"**SCORE_THRESHOLD={rec.threshold:.2f}** — {rec.reason}")
        lines.append("")
        lines.append(
            "Check it with a run of the experiment plan's group G before turning it on anywhere else. "
            "建議值只適用於這個 embedding 模型與這份題組；請先跑 G 組驗證。"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("reports", nargs="*", type=Path, help="evaluate.py JSON reports (default: docs/evaluation/results/*.json)")
    p.add_argument("--candidates", help="comma-separated thresholds (default 0.30–0.80 in steps of 0.05)")
    p.add_argument("--max-drop", type=float, default=0.05,
                   help="largest share of expected excerpts a suggested threshold may drop (default 0.05)")
    p.add_argument("--min-samples", type=int, default=20,
                   help="minimum expected and not-expected excerpts before suggesting a value (default 20)")
    p.add_argument("--include-thresholded", action="store_true", help="also use runs made with SCORE_THRESHOLD set")
    p.add_argument("--out", type=Path, help="also write the Markdown report here")
    args = p.parse_args(argv)

    paths = args.reports or sorted(DEFAULT_RESULTS.glob("*.json"))
    if not paths:
        print(f"No reports found in {DEFAULT_RESULTS}. Run scripts/evaluate.py first (experiment plan A–F).")
        print("找不到評估報告。請先依實驗計畫執行 A～F 組的 scripts/evaluate.py。")
        return 2
    try:
        candidates = (
            sorted({round(float(x), 4) for x in args.candidates.split(",") if x.strip()})
            if args.candidates
            else DEFAULT_CANDIDATES
        )
    except ValueError:
        p.error("--candidates must be numbers, e.g. 0.45,0.5,0.55")

    groups, notes = load_samples(paths, args.include_thresholded)
    out = ["# SCORE_THRESHOLD calibration / 相似度門檻校準", ""]
    if notes:
        out += ["Skipped / 略過：", ""] + [f"- {n}" for n in notes] + [""]
    usable = [g for g in groups.values() if g.samples]
    if not usable:
        out.append("No cosine scores in these reports / 報告中沒有可用的 cosine 分數。")
    exit_code = 0
    for g in usable:
        rows = [evaluate_threshold(g.samples, t) for t in candidates]
        rec = recommend(g.samples, rows, args.max_drop, args.min_samples)
        if rec.threshold is None:
            exit_code = 1
        out += [render(g, rows, rec), ""]
    text = "\n".join(out).rstrip() + "\n"
    print(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"→ {args.out}")
    return exit_code if usable else 2


if __name__ == "__main__":
    sys.exit(main())
