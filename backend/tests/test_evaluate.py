"""Tests for scripts/evaluate.py and scripts/compare.py.

The backend is mocked with a small local HTTP server that speaks the same SSE
protocol as /query/stream, so the real streaming client is exercised end to end.
No Ollama, Qdrant or network beyond 127.0.0.1.
"""

from __future__ import annotations

import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import compare  # noqa: E402
import evaluate as ev  # noqa: E402

SAMPLE = ROOT / "examples" / "sample-game-frontend"
QUESTIONS = ROOT / "docs" / "evaluation" / "questions.yaml"


# ── questions.yaml ─────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def questions() -> list[ev.Question]:
    return ev.load_questions(QUESTIONS)


def test_questions_yaml_has_all_ten_questions(questions):
    assert [q.id for q in questions] == list(range(1, 11))
    assert {q.type for q in questions} == {"定位設定", "解釋邏輯", "跨檔案流程", "陷阱題"}
    for q in questions:
        assert q.question and q.question_en and q.key_facts
        assert q.keywords, f"question {q.id} has no keywords"


def test_expected_files_exist_in_the_sample_project(questions):
    for q in questions:
        for path in q.expected_files + q.definition_files:
            assert (SAMPLE / path).is_file(), f"question {q.id}: {path} not in the sample project"
        assert set(q.definition_files) <= set(q.expected_files)


def test_where_is_it_configured_questions_point_at_the_defining_code(questions):
    for q in questions:
        if q.type != "定位設定":
            continue
        assert q.definition_files, f"question {q.id} needs definition_files"
        assert all(not ev.is_doc(f) for f in q.definition_files)
    q1 = next(q for q in questions if q.id == 1)
    assert "export const INVINCIBLE_MS = 1500" in (SAMPLE / q1.definition_files[0]).read_text()
    q9 = next(q for q in questions if q.id == 9)
    assert "HIGH_SCORE_KEY" in (SAMPLE / q9.definition_files[0]).read_text()


def test_identifier_keywords_appear_in_the_expected_files(questions):
    """Keywords that look like code identifiers must really exist in the expected code,
    so a keyword miss means the answer missed it, not that the YAML is wrong."""
    for q in questions:
        code = "".join((SAMPLE / f).read_text() for f in q.expected_files)
        for alternatives in q.keywords:
            for kw in alternatives:
                if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*[A-Z_][A-Za-z0-9_]*", kw):
                    assert kw in code, f"question {q.id}: keyword {kw} not found in its expected files"


def test_trick_question(questions):
    q10 = next(q for q in questions if q.id == 10)
    assert q10.expect_no_answer and q10.expected_files == [] and q10.forbidden_keywords


def test_parse_only():
    assert ev.parse_only(None) is None
    assert ev.parse_only("1,3, 5-7") == {1, 3, 5, 6, 7}


# ── Scoring ────────────────────────────────────────────────────────────────


Q1 = ev.Question(
    id=1,
    type="定位設定",
    question="玩家受傷後的無敵時間在哪裡設定？是多久？",
    keywords=[["INVINCIBLE_MS"], ["1500", "1.5 秒"], ["gameConfig"], ["takeDamage"]],
    expected_files=["src/config/gameConfig.ts", "src/entities/Player.ts", "docs/gameplay.md"],
    definition_files=["src/config/gameConfig.ts"],
)


def src(ref: int, path: str) -> dict:
    return {"ref": ref, "file_path": path, "start_line": 1, "end_line": 9, "symbol": "", "score": 0.5}


def test_file_metrics_separate_code_docs_and_definition():
    # The Codespaces case: only docs retrieved, the defining code file missed.
    sources = [src(1, "README.md"), src(2, "docs/gameplay.md"), src(3, "docs/architecture.md")]
    m = ev.file_metrics(Q1, sources, "見 [2]。")
    assert m["all"] == {"expected": 3, "hit": 1, "recall": 0.333, "any": True,
                        "missed": ["src/config/gameConfig.ts", "src/entities/Player.ts"]}
    assert m["code"]["any"] is False and m["code"]["expected"] == 2
    assert m["doc"]["any"] is True
    assert m["definition"]["any"] is False
    assert m["answer_cited"]["hit"] == 1
    assert m["retrieved_doc_share"] == 1.0


def test_file_metrics_answer_citations_follow_ref_numbers():
    sources = [src(1, "src/config/gameConfig.ts"), src(2, "src/ui/Hud.tsx")]
    m = ev.file_metrics(Q1, sources, "定義在 [1]，HUD 在 [2]，[9] 不存在。")
    assert m["answer_cited_files"] == ["src/config/gameConfig.ts", "src/ui/Hud.tsx"]
    assert m["answer_cited"]["hit"] == 1
    assert m["definition"]["any"] is True


def test_file_metrics_without_expected_files_are_not_applicable():
    q = ev.Question(id=10, type="陷阱題", question="?", expected_files=[])
    m = ev.file_metrics(q, [src(1, "src/game/Game.ts")], "")
    assert m["all"]["recall"] is None and m["code"]["any"] is None and m["doc"]["any"] is None


def test_keyword_metrics_alternatives_and_case():
    m = ev.keyword_metrics(Q1, "invincible_ms 是 1.5 秒，在 Player.takeDamage() 中設定。")
    assert m["hit"] == 3 and m["total"] == 4 and m["rate"] == 0.75
    assert m["matched"] == ["INVINCIBLE_MS", "1500", "takeDamage"]
    assert m["missed"] == ["gameConfig"]


def test_simplified_detection_on_a_real_codespaces_answer():
    answer = "玩家受傷後的無敵時間是在 `docs/gameplay.md` 設定的。具体来说，代码如下。因此，无敵时间的值在文件中定义。"
    assert ev.simplified_chars(answer) == ["体", "来", "说", "码", "无", "时", "间", "义"]


def test_simplified_list_has_no_false_positives_on_traditional_docs():
    """Traditional Chinese texts in this repo must produce zero hits. Files that quote
    Simplified answers on purpose (questions.yaml, ADR 0012, devlogs) are not included."""
    paths = [p for p in (ROOT / "examples").rglob("*") if p.suffix in (".md", ".ts", ".tsx", ".js")]
    paths += [ROOT / f for f in ("README.md", "CLAUDE.md", ".env.example", ".env.codespaces", "frontend/src/App.tsx",
                                 "docs/evaluation/questions.md", "docs/learning/knowledge-checklist.md", "docs/metrics.md")]
    paths += list((ROOT / "docs" / "decisions").glob("000*.md"))  # ADRs 0001-0009
    assert len(paths) > 20
    hits = {str(p.relative_to(ROOT)): ev.simplified_chars(p.read_text(encoding="utf-8")) for p in paths}
    assert {p: h for p, h in hits.items() if h} == {}


def test_trick_question_refusal():
    q = ev.Question(id=10, type="陷阱題", question="?", expect_no_answer=True,
                    keywords=[["找不到", "沒有", "not found"]], forbidden_keywords=["WebSocket"])
    refused = ev.score(q, ev.StreamResult(answer="在提供的程式碼中找不到多人模式。", server={"tokens": 5}))
    assert refused["refused"] is True
    invented = ev.score(q, ev.StreamResult(answer="沒有直接說明，但可能用 WebSocket 同步。", server={}))
    assert invented["refused"] is False
    assert invented["keywords"]["forbidden_hits"] == ["WebSocket"]


# ── Mock backend + streaming client ────────────────────────────────────────


class MockBackend(BaseHTTPRequestHandler):
    """/health and /query/stream with canned answers keyed by question text."""

    answers: dict[str, dict] = {}
    requests: list[dict] = []

    def log_message(self, *args):
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            body = {"status": "ok", "top_k": 4, "ollama": {"ok": True, "llm_model": "fake-3b", "embed_model": "fake-embed"},
                    "qdrant": {"ok": True, "points": 67}}
            self._send(200, json.dumps(body).encode(), "application/json")
        else:
            self._send(404, b"", "text/plain")

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).requests.append(req)
        canned = type(self).answers.get(req["question"], {"tokens": ["這個專案用 TypeScript。"], "sources": []})
        if canned.get("http_error"):
            self._send(canned["http_error"], b'{"detail":"boom"}', "application/json")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()

        def frame(event: str, data) -> None:
            self.wfile.write(f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()

        frame("heartbeat", {"elapsed_seconds": 0.0})
        if "error_before_sources" in canned:
            frame("error", {"kind": "timeout", "stage": "embedding", "detail": canned["error_before_sources"]})
            return
        frame("sources", canned["sources"])
        for t in canned["tokens"]:
            frame("token", {"text": t})
        if canned.get("cut"):
            return  # connection closes without done
        frame("done", {"retrieval_seconds": 0.01, "first_token_seconds": 0.02, "total_seconds": 0.05,
                       "tokens": len(canned["tokens"]), "answer_chars": len("".join(canned["tokens"])),
                       **canned.get("done", {})})


@pytest.fixture
def backend():
    MockBackend.answers, MockBackend.requests = {}, []
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockBackend)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_iter_sse_parses_frames_and_skips_comments():
    raw = [b": ping\n", b"event: token\n", b'data: {"text": "a"}\n', b"\n", b'data: {"x": 1}\n', b"\n"]
    assert list(ev.iter_sse(raw)) == [("token", {"text": "a"}), ("message", {"x": 1})]


def test_stream_query_collects_answer_sources_and_timing(backend):
    MockBackend.answers["q"] = {"sources": [src(1, "src/a.ts")], "tokens": ["Hello", " world [1]."]}
    ticks = iter([100.0, 102.5, 109.0])  # start, first token, end
    r = ev.stream_query(backend, "q", 4, timeout=5, clock=lambda: next(ticks))
    assert r.error is None
    assert r.answer == "Hello world [1]."
    assert r.sources[0]["file_path"] == "src/a.ts"
    assert r.first_token_seconds == 2.5 and r.total_seconds == 9.0
    assert r.server["tokens"] == 2 and r.heartbeats == 1
    assert MockBackend.requests[-1] == {"question": "q", "top_k": 4}


def test_stream_query_reports_errors(backend):
    MockBackend.answers.update({
        "timeout": {"error_before_sources": "Ollama 產生向量（embedding）逾時"},
        "cut": {"sources": [], "tokens": ["半"], "cut": True},
        "500": {"http_error": 500},
    })
    assert "embedding" in ev.stream_query(backend, "timeout", None, 5).error
    cut = ev.stream_query(backend, "cut", None, 5)
    assert cut.answer == "半" and "before the done event" in cut.error
    assert ev.stream_query(backend, "500", None, 5).error.startswith("HTTP 500")
    assert "URLError" in ev.stream_query("http://127.0.0.1:9", "x", None, 2).error
    assert MockBackend.requests[0] == {"question": "timeout"}  # no top_k when not given


def write_answers(questions: list[ev.Question]) -> None:
    """Canned answers: Q1 like the Codespaces run (docs only, Simplified), Q9 perfect, Q10 refused."""
    q = {x.id: x for x in questions}
    MockBackend.answers[q[1].question] = {
        "sources": [src(1, "README.md"), src(2, "docs/gameplay.md"), src(3, "docs/architecture.md")],
        "tokens": ["無敵時間是 `INVINCIBLE_MS` 毫秒 [2]。", "具体来说在文件中定义。"],
    }
    MockBackend.answers[q[9].question] = {
        "sources": [src(1, "src/game/GameState.ts"), src(2, "src/game/Game.ts")],
        "tokens": ["存在 `localStorage`，key 是 `HIGH_SCORE_KEY` [1]，", "在 `gameOver()` 寫入 [2]。"],
    }
    MockBackend.answers[q[10].question] = {"sources": [src(1, "src/game/Game.ts")], "tokens": ["專案中找不到多人模式。"]}


def test_main_writes_json_and_markdown(backend, tmp_path, questions, capsys):
    write_answers(questions)
    code = ev.main(["--base-url", backend, "--label", "test run/3b", "--only", "1,9,10", "--top-k", "4",
                    "--out-dir", str(tmp_path)])
    assert code == 0
    files = sorted(p.name for p in tmp_path.iterdir())
    assert len(files) == 2 and files[0].endswith("-test-run-3b.json") and files[1].endswith("-test-run-3b.md")
    report = json.loads((tmp_path / files[0]).read_text())

    # Warm-up first (not scored), then the three questions.
    assert MockBackend.requests[0]["question"] == ev.WARMUP_QUESTION
    assert [r["id"] for r in report["results"]] == [1, 9, 10]
    assert report["config"]["top_k"] == 4 and report["health"]["ollama"]["llm_model"] == "fake-3b"

    r1, r9, r10 = report["results"]
    assert r1["metrics"]["files"]["code"]["any"] is False
    assert r1["metrics"]["files"]["definition"]["any"] is False
    assert r1["metrics"]["has_simplified"] is True
    assert r1["manual_correctness"] is None
    assert r9["metrics"]["files"]["all"]["recall"] == 1.0
    assert r9["metrics"]["files"]["definition"]["any"] is True
    assert r9["metrics"]["keywords"]["rate"] == 1.0
    assert r10["metrics"]["refused"] is True

    s = report["summary"]
    assert s["questions"] == 3 and s["errors"] == 0
    assert s["code_hit"] == {"hit": 1, "of": 2, "rate": 0.5}
    assert s["definition_hit"] == {"hit": 1, "of": 2, "rate": 0.5}
    assert s["simplified_answers"] == 1
    assert s["no_answer_refused"] == {"hit": 1, "of": 1, "rate": 1.0}
    assert s["false_refusals"] == {"hit": 0, "of": 2, "rate": 0.0}
    assert set(s["keyword_rate_by_type"]) == {"定位設定", "陷阱題"}

    md = (tmp_path / files[1]).read_text()
    assert "人工判定正確性" in md
    assert "| 1 | 定位設定 |" in md and "| 9 | 定位設定 |" in md
    assert "具体来说" in md  # full answer kept for the human judge
    assert "`src/config/gameConfig.ts`" in md  # listed as a missed expected file


def test_main_counts_errors_and_fails_without_backend(backend, tmp_path, questions, capsys):
    MockBackend.answers[next(q for q in questions if q.id == 2).question] = {"http_error": 502}
    assert ev.main(["--base-url", backend, "--label", "e", "--only", "2", "--no-warmup", "--out-dir", str(tmp_path)]) == 1
    report = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert report["summary"]["errors"] == 1 and report["results"][0]["error"].startswith("HTTP 502")
    assert "✗" in next(tmp_path.glob("*.md")).read_text()
    assert ev.main(["--base-url", "http://127.0.0.1:9", "--label", "x", "--out-dir", str(tmp_path)]) == 2


def test_unknown_only_id_is_rejected(tmp_path):
    with pytest.raises(SystemExit):
        ev.main(["--label", "x", "--only", "42", "--out-dir", str(tmp_path)])


# ── compare.py ─────────────────────────────────────────────────────────────


def fake_report(label: str, top_k: int, first_token: float, code_rate: float, simplified: int, q1_code: int) -> dict:
    def q(i: int, code_hit: int) -> dict:
        return {
            "id": i, "type": "定位設定", "error": None, "manual_correctness": 2 if i == 1 else None,
            "metrics": {
                "first_token_seconds": first_token, "total_seconds": first_token + 10,
                "files": {k: {"hit": code_hit, "expected": 2} for k in ("all", "code", "definition")},
                "keywords": {"hit": 3, "total": 5}, "simplified_chars": ["体"] if simplified else [],
            },
        }

    return {
        "schema": 1, "date": "2026-11-03", "config": {"label": label, "top_k": top_k, "lang": "zh"},
        "health": {"ollama": {"llm_model": "qwen2.5-coder:3b"}, "top_k": 4},
        "summary": {
            "first_token_seconds_mean": first_token, "total_seconds_mean": first_token + 10, "errors": 0,
            "code_hit": {"rate": code_rate}, "keyword_rate_mean": 0.6, "simplified_answers": simplified,
            "no_answer_refused": {"rate": None},
        },
        "results": [q(1, q1_code), q(9, 2)] if label == "k4" else [q(1, q1_code), q(2, 1)],
    }


def test_compare_summary_and_per_question(tmp_path):
    a = fake_report("k4", 4, 30.4, 0.25, 1, 0)
    b = fake_report("k8", 8, 55.0, 0.75, 0, 2)
    text = compare.compare(a, b)
    assert "`k4` · 2026-11-03 · qwen2.5-coder:3b · top_k 4" in text
    assert "| Time to first token, mean / 首字延遲平均 | 30.4 s | 55.0 s | +24.6 s ▼ |" in text
    assert "| Code file retrieved / 程式碼檔命中 | 25% | 75% | +50 pt ▲ |" in text
    assert "| Answers with Simplified / 混入簡體字的回答 | 1 | 0 | -1 ▲ |" in text
    assert "| Keyword hit rate / 關鍵字命中率 | 60% | 60% | 0 |" in text
    assert "| Refusal rate, trick questions / 拒答率 | — | — | — |" in text
    assert "| 1 | 定位設定 | 30.4 s → 55.0 s | 40.4 s → 65.0 s | 0/2 → 2/2 | 0/2 → 2/2 | 0/2 → 2/2 | 3/5 → 3/5 | 体 / — | 2 / 2 |" in text
    assert "Not in both runs (not compared): 2, 9" in text

    pa, pb, out = tmp_path / "a.json", tmp_path / "b.json", tmp_path / "out" / "cmp.md"
    pa.write_text(json.dumps(a)), pb.write_text(json.dumps(b))
    assert compare.main([str(pa), str(pb), "--out", str(out)]) == 0
    assert out.read_text() == text


def test_compare_rejects_unknown_schema(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"schema": 99}))
    with pytest.raises(SystemExit):
        compare.load(p)


def test_apply_manual_copies_scores_from_markdown(backend, tmp_path, questions):
    write_answers(questions)
    assert ev.main(["--base-url", backend, "--label", "m", "--only", "1,9,10", "--no-warmup",
                    "--out-dir", str(tmp_path)]) == 0
    md = next(tmp_path.glob("*.md"))
    text = md.read_text()
    # A person fills in the column: Q1 = 0, Q9 = 2, Q10 left empty.
    text = re.sub(r"^(\| 1 \| 定位設定 \|.*\|)  \|  \|$", r"\1 0 | docs only |", text, flags=re.M)
    text = re.sub(r"^(\| 9 \| 定位設定 \|.*\|)  \|  \|$", r"\1 2 |  |", text, flags=re.M)
    md.write_text(text)
    assert ev.read_manual_scores(text) == {1: 0, 9: 2}

    assert ev.main(["--apply-manual", str(md)]) == 0
    report = json.loads(md.with_suffix(".json").read_text())
    assert [r["manual_correctness"] for r in report["results"]] == [0, 2, None]
    assert report["summary"]["manual_correctness"] == {"judged": 2, "of": 3, "total": 2, "max": 4}

    md.write_text(text.replace("| 2 |  |", "| 3 |  |", 1))
    assert ev.main(["--apply-manual", str(md)]) == 2  # only 0, 1 or 2 allowed


def test_label_is_required_to_run(tmp_path):
    with pytest.raises(SystemExit):
        ev.main(["--out-dir", str(tmp_path)])


# ── questions-identifiers.yaml (ADR 0013) ──────────────────────────────────


def test_identifier_question_set_is_valid_and_names_identifiers():
    from app.retrieval import extract_identifiers

    extra = ev.load_questions(ROOT / "docs" / "evaluation" / "questions-identifiers.yaml")
    main_ids = {q.id for q in ev.load_questions(QUESTIONS)}
    assert extra and not ({q.id for q in extra} & main_ids)
    for q in extra:
        assert q.question and q.question_en and q.key_facts and q.keywords
        assert q.expected_files
        assert set(q.definition_files) <= set(q.expected_files)
        code = "".join((SAMPLE / f).read_text() for f in q.expected_files)
        for alternatives in q.keywords:
            for kw in alternatives:
                if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*[A-Z_][A-Za-z0-9_]*", kw):
                    assert kw in code, f"question {q.id}: keyword {kw} not found in its expected files"
        # The point of this set: every question names at least one identifier.
        assert extract_identifiers(q.question), f"question {q.id} names no identifier"
        if q.type == "定位設定":
            assert q.definition_files and all(not ev.is_doc(f) for f in q.definition_files)


def test_retrieval_label_describes_the_server_switches():
    assert ev.retrieval_label(None).startswith("not reported")
    base = {"hybrid_search": False, "split_retrieval": False, "chunk_metadata": False, "prompt_variant": "v1"}
    assert ev.retrieval_label(base) == "vector only (baseline) · prompt v1"
    full = {**base, "hybrid_search": True, "rrf_k": 60, "split_retrieval": True, "doc_top_k": 1,
            "chunk_metadata": True, "prompt_variant": "v2"}
    assert ev.retrieval_label(full) == "hybrid (RRF k=60) + split (docs ≤ 1) + metadata · prompt v2"


# ── ADR 0014 / 0015: threshold, rerank and per-excerpt scores ───────────────


def test_retrieval_label_shows_threshold_and_rerank():
    base = {"hybrid_search": False, "split_retrieval": False, "chunk_metadata": False, "prompt_variant": "v1",
            "score_threshold": 0.5, "rerank": True, "rerank_model": "m", "rerank_candidates": 10, "rerank_top_n": 3}
    assert ev.retrieval_label(base) == "threshold ≥ 0.5 + rerank (m, 10 → 3) · prompt v1"
    assert ev.retrieval_label({**base, "score_threshold": None, "rerank": False}) == "vector only (baseline) · prompt v1"


def test_report_records_excerpt_scores_rerank_time_and_threshold_refusals(backend, tmp_path, questions):
    q = {x.id: x for x in questions}
    scored = {**src(1, "src/config/gameConfig.ts"), "vector_score": 0.61, "rerank_score": 0.9, "matched_by": ["vector"]}
    MockBackend.answers[q[1].question] = {
        "sources": [scored], "tokens": ["在 [1]。"], "done": {"rerank_seconds": 1.25, "no_relevant": False},
    }
    MockBackend.answers[q[10].question] = {
        "sources": [], "tokens": ["在目前索引的專案中找不到與這個問題相關的內容。"],
        "done": {"rerank_seconds": None, "no_relevant": True},
    }
    assert ev.main(["--base-url", backend, "--label", "g", "--only", "1,10", "--no-warmup",
                    "--out-dir", str(tmp_path)]) == 0
    report = json.loads(next(tmp_path.glob("*.json")).read_text())
    r1, r10 = report["results"]
    assert r1["sources"][0]["vector_score"] == 0.61
    assert r1["sources"][0]["rerank_score"] == 0.9 and r1["sources"][0]["matched_by"] == ["vector"]
    assert r1["metrics"]["rerank_seconds"] == 1.25
    assert r10["metrics"]["no_relevant"] is True and r10["metrics"]["refused"] is True
    s = report["summary"]
    assert s["rerank_seconds_mean"] == 1.25 and s["threshold_refusals"] == 1
    md = next(tmp_path.glob("*.md")).read_text()
    assert "rerank 耗時平均 | 1.2 s" in md and "因門檻直接拒答 | 1" in md
    assert "LLM not called" in md


# ── scripts/calibrate_threshold.py ─────────────────────────────────────────

import calibrate_threshold as cal  # noqa: E402


def cal_report(path: Path, results: list[dict], retrieval: dict | None = None, embed: str = "nomic-embed-text") -> Path:
    path.write_text(json.dumps({
        "schema": 1,
        "health": {"ollama": {"embed_model": embed}, "retrieval": retrieval},
        "results": results,
    }), encoding="utf-8")
    return path


def result(question: str, expected: list[str], sources: list[tuple[str, float]], trick: bool = False,
           key: str = "vector_score") -> dict:
    return {
        "question": question, "expected_files": expected, "expect_no_answer": trick, "error": None,
        "sources": [{"file_path": f, "start_line": i, "end_line": i + 5, key: c} for i, (f, c) in enumerate(sources)],
    }


def test_calibrate_reads_vector_score_or_cosine_score_and_skips_rrf_and_thresholded_runs(tmp_path):
    a = cal_report(tmp_path / "a.json", [result("q1", ["a.ts"], [("a.ts", 0.7), ("b.md", 0.5)], key="score")])
    hybrid_old = cal_report(tmp_path / "h.json", [result("q1", ["a.ts"], [("a.ts", 0.03)], key="score")],
                             {"hybrid_search": True})
    thresholded = cal_report(tmp_path / "t.json", [result("q1", ["a.ts"], [("a.ts", 0.9)])],
                              {"hybrid_search": False, "score_threshold": 0.5})
    groups, notes = cal.load_samples([a, hybrid_old, thresholded])
    samples = groups["nomic-embed-text"].samples
    assert sorted((s.file_path, s.cosine, s.expected) for s in samples) == [("a.ts", 0.7, True), ("b.md", 0.5, False)]
    assert any("h.json" in n and "no cosine" in n for n in notes)
    assert any("t.json" in n and "SCORE_THRESHOLD" in n for n in notes)
    # The same excerpt for the same question in two runs counts once.
    groups, _ = cal.load_samples([a, a])
    assert len(groups["nomic-embed-text"].samples) == 2
    # CHUNK_METADATA changes the vectors: calibrated separately.
    meta = cal_report(tmp_path / "m.json", [result("q1", ["a.ts"], [("a.ts", 0.8)])], {"chunk_metadata": True})
    groups, _ = cal.load_samples([a, meta])
    assert set(groups) == {"nomic-embed-text", "nomic-embed-text + CHUNK_METADATA"}


def test_calibrate_never_lists_a_report_as_both_skipped_and_used(tmp_path):
    a = cal_report(tmp_path / "a.json", [result("q1", ["a.ts"], [("a.ts", 0.7)], key="score")])
    hybrid_old = cal_report(tmp_path / "h.json", [result("q1", ["a.ts"], [("a.ts", 0.03)], key="score")],
                             {"hybrid_search": True})
    copy = cal_report(tmp_path / "c.json", [result("q1", ["a.ts"], [("a.ts", 0.7)], key="score")])
    groups, notes = cal.load_samples([a, hybrid_old, copy])
    assert groups["nomic-embed-text"].reports == ["a.json"]
    assert [n.split(":")[0] for n in notes] == ["h.json", "c.json"]
    assert "no cosine scores" in notes[0] and "already counted" in notes[1]
    rows = [cal.evaluate_threshold(groups["nomic-embed-text"].samples, 0.5)]
    text = cal.render(groups["nomic-embed-text"], rows, cal.Recommendation(None, "x"))
    assert "Reports used (1)" in text and "h.json" not in text and "c.json" not in text


def test_calibrate_counts_drops_blocks_lost_questions_and_trick_refusals():
    S = cal.Sample
    samples = [
        S("q1", "a.ts", "a.ts:1-5", 0.62, True, False),
        S("q1", "doc.md", "doc.md:1-5", 0.58, True, False),
        S("q2", "c.ts", "c.ts:1-5", 0.55, True, False),
        S("q1", "x.ts", "x.ts:1-5", 0.40, False, False),
        S("trick", "y.ts", "y.ts:1-5", 0.45, False, True),
    ]
    r = cal.evaluate_threshold(samples, 0.56)
    assert (r.expected_dropped, r.expected_total) == (1, 3)
    assert (r.other_blocked, r.other_total) == (2, 2)
    assert r.questions_losing_all == ["q2"]
    assert (r.trick_refused, r.trick_total) == (1, 1)


def _synthetic(n_questions: int = 6, per: int = 5) -> list:
    S = cal.Sample
    samples = []
    for q in range(n_questions):
        samples += [S(f"q{q}", "a.ts", f"a.ts:{i}", 0.60 + i / 100, True, False) for i in range(per)]
        samples += [S(f"q{q}", "z.ts", f"z.ts:{i}", 0.35 + i / 100, False, False) for i in range(per)]
    samples += [S("trick", "z.ts", "z.ts:99", 0.42, False, True)]
    return samples


def test_calibrate_recommends_the_highest_safe_threshold():
    samples = _synthetic()
    rows = [cal.evaluate_threshold(samples, t) for t in cal.DEFAULT_CANDIDATES]
    rec = cal.recommend(samples, rows, max_drop=0.05, min_samples=20)
    assert rec.threshold == 0.60  # every expected excerpt is >= 0.60
    assert "1/1 trick" in rec.reason
    text = cal.render(cal.Group("nomic-embed-text", ["a.json"], samples), rows, rec)
    assert "**SCORE_THRESHOLD=0.60**" in text and "| 0.60 **←** |" in text


def test_calibrate_refuses_to_guess_with_too_little_data():
    samples = _synthetic(n_questions=2, per=3)
    rows = [cal.evaluate_threshold(samples, t) for t in cal.DEFAULT_CANDIDATES]
    rec = cal.recommend(samples, rows, max_drop=0.05, min_samples=20)
    assert rec.threshold is None and "資料不足" in rec.reason


def test_calibrate_says_so_when_distributions_overlap():
    S = cal.Sample
    samples = [S(f"q{q}", "a.ts", f"a{q}:{i}", 0.30 + 0.01 * i, True, False) for q in range(4) for i in range(10)]
    samples += [S(f"q{q}", "z.ts", f"z{q}:{i}", 0.31 + 0.01 * i, False, False) for q in range(4) for i in range(10)]
    rows = [cal.evaluate_threshold(samples, t) for t in [0.35, 0.40]]
    rec = cal.recommend(samples, rows, max_drop=0.0, min_samples=20)
    assert rec.threshold is None and "overlap" in rec.reason


def test_calibrate_main_without_reports_explains_what_to_run(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cal, "DEFAULT_RESULTS", tmp_path)
    assert cal.main([]) == 2
    assert "evaluate.py" in capsys.readouterr().out


def test_calibrate_main_writes_markdown(tmp_path, capsys):
    results = [result(f"q{q}", ["a.ts"], [("a.ts", 0.6 + i / 100) for i in range(5)] + [("z.ts", 0.3 + i / 100) for i in range(5)])
               for q in range(6)]
    results.append(result("trick", [], [("z.ts", 0.41)], trick=True))
    path = cal_report(tmp_path / "A.json", results, {"hybrid_search": False})
    out = tmp_path / "cal.md"
    assert cal.main([str(path), "--out", str(out)]) == 0
    text = out.read_text()
    assert "nomic-embed-text" in text and "SCORE_THRESHOLD=0.60" in text


# ── questions-out-of-scope.yaml, 拒答率 / 誤拒率 (ADR 0016) ──────────────────

OUT_OF_SCOPE = ROOT / "docs" / "evaluation" / "questions-out-of-scope.yaml"


def test_out_of_scope_set_has_five_trick_and_some_control_questions():
    oos = ev.load_questions(OUT_OF_SCOPE)
    other_ids = {q.id for q in ev.load_questions(QUESTIONS)} | {
        q.id for q in ev.load_questions(ROOT / "docs" / "evaluation" / "questions-identifiers.yaml")
    }
    assert not ({q.id for q in oos} & other_ids)
    tricks = [q for q in oos if q.type == "陷阱題"]
    controls = [q for q in oos if q.type == "對照題"]
    assert len(tricks) == 5 and 2 <= len(controls) <= 3 and len(oos) == len(tricks) + len(controls)
    for q in oos:
        assert q.question and q.question_en and q.key_facts and q.keywords
    for q in tricks:
        assert q.expect_no_answer and q.expected_files == [] and q.forbidden_keywords
        # A refusal must be countable: 「找不到」 is the phrase prompt v3 asks for.
        assert "找不到" in q.keywords[0]
    for q in controls:
        assert not q.expect_no_answer and q.expected_files and not q.forbidden_keywords
        code = "".join((SAMPLE / f).read_text() for f in q.expected_files)
        for path in q.expected_files + q.definition_files:
            assert (SAMPLE / path).is_file(), f"question {q.id}: {path} not in the sample project"
        for alternatives in q.keywords:
            for kw in alternatives:
                if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*[A-Z_][A-Za-z0-9_]*", kw) or kw in ("blur", "localStorage"):
                    assert kw in code, f"question {q.id}: keyword {kw} not found in its expected files"


def test_out_of_scope_trick_features_really_do_not_exist():
    """The forbidden keywords are signs of invented code: none may appear in the sample project."""
    source = "".join(p.read_text() for p in SAMPLE.rglob("*") if p.is_file() and p.suffix in {".ts", ".tsx", ".js"})
    for q in ev.load_questions(OUT_OF_SCOPE):
        if q.expect_no_answer:
            for kw in q.forbidden_keywords:
                assert kw.casefold() not in source.casefold(), f"question {q.id}: {kw} exists in the sample project"


def test_refusal_phrases_are_found_case_insensitively():
    from app.rag import NO_MATCH_ANSWER, NO_RELEVANT_ANSWER, REFUSAL_SENTENCE

    assert ev.refusal_phrases("Not Found in the excerpts") == ["not found"]
    # Prompt v3's sentence and the backend's canned answers all count.
    for text in (REFUSAL_SENTENCE, NO_MATCH_ANSWER, NO_RELEVANT_ANSWER):
        assert ev.refusal_phrases(text), text
    # A bare 沒有 is not a refusal phrase (common in correct answers).
    assert ev.refusal_phrases("超過 COMBO_WINDOW_MS 沒有收集到包裹，連擊歸零。") == []


def test_false_refusal_needs_a_refusal_phrase_and_no_keyword():
    q = ev.Question(id=27, type="對照題", question="?", keywords=[["SoundManager"], ["AudioContext", "合成"]],
                    expected_files=["src/audio/SoundManager.ts"])
    refused = ev.score(q, ev.StreamResult(answer="在索引的專案中找不到相關內容。", server={}))
    assert refused["falsely_refused"] is True and refused["refusal_phrases"] == ["找不到"]
    assert "refused" not in refused  # 拒答 is only scored for trick questions
    # Says something is missing but gives the facts: an answer, not a refusal.
    partial = ev.score(q, ev.StreamResult(answer="找不到音效檔；音效由 SoundManager 用 AudioContext 合成。", server={}))
    assert partial["falsely_refused"] is False
    answered = ev.score(q, ev.StreamResult(answer="[1] SoundManager 沒有音效檔，即時合成。", server={}))
    assert answered["falsely_refused"] is False and answered["refusal_phrases"] == []
    # Trick questions are scored as 拒答, never as 誤拒.
    trick = ev.Question(id=21, type="陷阱題", question="?", expect_no_answer=True, keywords=[["找不到"]])
    assert "falsely_refused" not in ev.score(trick, ev.StreamResult(answer="找不到。", server={}))


def _scored(qid: int, trick: bool, answer: str, error: str | None = None) -> dict:
    keywords = [["找不到"]] if trick else [["SoundManager"]]
    q = ev.Question(id=qid, type="陷阱題" if trick else "對照題", question="?", expect_no_answer=trick, keywords=keywords)
    r = ev.StreamResult(answer=answer, server={}, error=error)
    return {"id": qid, "type": q.type, "expect_no_answer": trick, "error": error, "metrics": ev.score(q, r)}


def test_summary_reports_refusal_and_false_refusal_rates():
    results = [
        _scored(21, True, "在索引的專案中找不到相關內容。"),
        _scored(22, True, "付款用 Stripe 處理。"),
        _scored(26, False, "在索引的專案中找不到相關內容。"),
        _scored(27, False, "[1] SoundManager 合成音效。"),
        _scored(28, False, "", error="HTTP 502"),  # errors are left out of both rates
    ]
    s = ev.summarize(results)
    assert s["no_answer_refused"] == {"hit": 1, "of": 2, "rate": 0.5}
    assert s["false_refusals"] == {"hit": 1, "of": 2, "rate": 0.5}


def test_report_shows_refusal_and_false_refusal_rates(backend, tmp_path):
    oos = {q.id: q for q in ev.load_questions(OUT_OF_SCOPE)}
    MockBackend.answers[oos[21].question] = {"sources": [], "tokens": ["在索引的專案中找不到相關內容。"]}
    MockBackend.answers[oos[22].question] = {"sources": [], "tokens": ["付款流程使用 ", "Stripe。"]}
    MockBackend.answers[oos[27].question] = {"sources": [], "tokens": ["在索引的專案中找不到相關內容。"]}
    MockBackend.answers[oos[28].question] = {"sources": [], "tokens": ["InputManager 在 blur 時清空 held。"]}
    code = ev.main(["--base-url", backend, "--label", "oos", "--questions", str(OUT_OF_SCOPE),
                    "--only", "21,22,27,28", "--no-warmup", "--out-dir", str(tmp_path)])
    assert code == 0
    report = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert report["summary"]["no_answer_refused"] == {"hit": 1, "of": 2, "rate": 0.5}
    assert report["summary"]["false_refusals"] == {"hit": 1, "of": 2, "rate": 0.5}
    md = next(tmp_path.glob("*.md")).read_text()
    assert "| Refusal rate, trick questions / 拒答率（陷阱題正確拒答） | 1/2 (50%) |" in md
    assert "| False refusal rate, answerable questions / 誤拒率（可回答的題目答「找不到」） | 1/2 (50%) |" in md
    assert "(**not refused**)" in md and "(**falsely refused**)" in md
    assert "- **False refusal**: says 找不到 and hits no keyword" in md


def test_report_from_an_older_summary_without_false_refusals_still_renders():
    report = {"summary": {**ev.summarize([]), "false_refusals": None}, "config": {
        "label": "old", "base_url": "x", "top_k": 4, "lang": "zh", "warmup": True},
        "health": {}, "results": [], "date": "2026-11-03", "started_at": "t"}
    del report["summary"]["false_refusals"]
    assert "誤拒率（可回答的題目答「找不到」） | — |" in ev.render_markdown(report)


def test_compare_false_refusal_rate_lower_is_better():
    a = {"summary": {"no_answer_refused": {"rate": 0.0}, "false_refusals": {"rate": 0.0}}, "results": []}
    b = {"summary": {"no_answer_refused": {"rate": 0.8}, "false_refusals": {"rate": 1 / 3}}, "results": []}
    text = compare.compare(a, b)
    assert "| Refusal rate, trick questions / 拒答率 | 0% | 80% | +80 pt ▲ |" in text
    assert "| False refusal rate / 誤拒率 | 0% | 33% | +33 pt ▼ |" in text
