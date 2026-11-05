"""QUERY_GLOSSARY (ADR 0020): Chinese terms -> identifiers for the keyword and identifier channels."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.glossary import Glossary, GlossaryError, GlossaryFile, load_glossary, parse_glossary
from app.main import create_app
from app.retrieval import split_identifier

from .conftest import make_services

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "examples" / "sample-game-frontend"
SAMPLE_GLOSSARY = ROOT / "glossary" / "sample-game-frontend.yaml"


# ── Matching ───────────────────────────────────────────────────────────────


def test_match_longest_term_first_without_overlap_in_question_order():
    g = Glossary({"連擊": ["combo"], "連擊倍率": ["MAX_COMBO_MULTIPLIER", "combo"], "歸零": ["reset"]})
    hit = g.match("連擊倍率怎麼計算？什麼時候會歸零？")
    assert hit.terms == ["連擊倍率", "歸零"]  # 連擊 is inside 連擊倍率: not matched again
    assert hit.identifiers == ["MAX_COMBO_MULTIPLIER", "combo", "reset"]
    # Elsewhere in the question the shorter term still matches.
    assert g.match("連擊倍率和連擊有什麼不同").terms == ["連擊倍率", "連擊"]


def test_match_nothing_and_ascii_terms_are_case_insensitive():
    g = Glossary({"HUD": ["Hud", "HudProps"]})
    assert g.match("與這無關").identifiers == []
    assert g.match("hud 怎麼更新").terms == ["HUD"]


def test_parse_validates_and_skips_unfinished_draft_entries():
    g = parse_glossary({"version": 1, "terms": {"衝刺": ["DASH_SPEED", "DASH_SPEED", "Player.startDash"],
                                                "暫停": "paused", "待填": None}})
    assert g.terms == {"衝刺": ["DASH_SPEED", "Player.startDash"], "暫停": ["paused"]}
    for bad, message in [
        ({"terms": ["連擊"]}, "'terms:' mapping"),
        ({"version": 2, "terms": {}}, "unsupported version"),
        ({"terms": {"連擊": ["連擊數"]}}, "not a code identifier"),
        ({"terms": {"連擊": {"a": 1}}}, "list of identifiers"),
        ({"terms": {" ": ["x"]}}, "empty term"),
    ]:
        with pytest.raises(GlossaryError, match=re.escape(message)):
            parse_glossary(bad, "g.yaml")


def test_load_reports_missing_file_and_bad_yaml(tmp_path):
    with pytest.raises(GlossaryError, match="cannot read"):
        load_glossary(tmp_path / "nope.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("terms: [unclosed", encoding="utf-8")
    with pytest.raises(GlossaryError, match="invalid YAML"):
        load_glossary(bad)


def test_glossary_file_reloads_when_edited_and_keeps_errors(tmp_path):
    path = tmp_path / "g.yaml"
    gf = GlossaryFile(str(path))
    assert gf.get() is None and "cannot read" in gf.error
    path.write_text("version: 1\nterms:\n  重力: [GRAVITY]\n", encoding="utf-8")
    assert gf.get().terms == {"重力": ["GRAVITY"]} and gf.error is None
    first = gf.get()
    assert gf.get() is first  # cached while the file is unchanged
    path.write_text("version: 1\nterms:\n  重力: [GRAVITY, vy]\n", encoding="utf-8")
    st = path.stat()
    os.utime(path, (st.st_atime, st.st_mtime + 5))
    assert gf.get().terms == {"重力": ["GRAVITY", "vy"]}


# ── The sample project's glossary ──────────────────────────────────────────


def test_sample_glossary_loads_and_every_identifier_exists_in_the_sample_project():
    g = load_glossary(SAMPLE_GLOSSARY)
    assert len(g) >= 20
    source = "\n".join(p.read_text(encoding="utf-8") for p in (SAMPLE / "src").rglob("*") if p.is_file())
    for term, idents in g.terms.items():
        for ident in idents:
            for part in ident.split("."):
                assert re.search(rf"(?<![\w$]){re.escape(part)}(?![\w$])", source), f"{term}: {ident} not in the sample code"


def test_sample_glossary_maps_question_2_to_the_combo_code():
    """Question 2 (連擊倍率) retrieved neither ScoreSystem.ts nor gameConfig.ts in any group A–J."""
    hit = load_glossary(SAMPLE_GLOSSARY).match("連擊倍率怎麼計算？什麼時候會歸零？")
    assert {"COMBO_STEP", "MAX_COMBO_MULTIPLIER", "COMBO_WINDOW_MS", "ScoreSystem"} <= set(hit.identifiers)


# ── Retrieval and /health ──────────────────────────────────────────────────


def write_glossary(tmp_path: Path) -> str:
    path = tmp_path / "glossary.yaml"
    path.write_text(yaml.safe_dump({"version": 1, "terms": {"重力": ["GRAVITY"]}}, allow_unicode=True), encoding="utf-8")
    return str(path)


QUESTION = "玩家的重力是多少？"


def test_glossary_adds_identifiers_to_keyword_and_identifier_channels(settings, tmp_path):
    settings.hybrid_search = True
    services = make_services(settings)
    services.indexer.run()
    # Without the glossary a Chinese question gives BM25 and the identifier channel nothing.
    plain = services.rag.retrieve_detailed(QUESTION, top_k=3)
    assert all(s.matched_by == ["vector"] for s in plain.sources) and plain.glossary is None

    settings.query_glossary = True
    settings.query_glossary_path = write_glossary(tmp_path)
    found = services.rag.retrieve_detailed(QUESTION, top_k=3)
    assert found.glossary.to_dict() == {"terms": ["重力"], "identifiers": ["GRAVITY"]}
    top = found.sources[0]
    assert top.file_path == "src/player.ts" and "export const GRAVITY = 1800;" in top.text
    assert "identifier" in top.matched_by and "keyword" in top.matched_by


def test_glossary_does_nothing_without_hybrid_search(settings, tmp_path):
    settings.query_glossary = True
    settings.query_glossary_path = write_glossary(tmp_path)
    services = make_services(settings)
    services.indexer.run()
    found = services.rag.retrieve_detailed(QUESTION, top_k=3)
    assert found.glossary is None and all(s.matched_by == ["vector"] for s in found.sources)
    events = list(services.rag.stream(QUESTION, top_k=2))
    assert events[-1].data["glossary"] is None


def test_stream_done_event_reports_glossary_expansion(settings, tmp_path):
    settings.hybrid_search = settings.query_glossary = True
    settings.query_glossary_path = write_glossary(tmp_path)
    services = make_services(settings)
    services.indexer.run()
    done = list(services.rag.stream(QUESTION, top_k=2))[-1]
    assert done.kind == "done" and done.data["glossary"] == {"terms": ["重力"], "identifiers": ["GRAVITY"]}


def test_missing_glossary_degrades_health_but_queries_still_work(settings, tmp_path):
    settings.hybrid_search = settings.query_glossary = True
    settings.query_glossary_path = str(tmp_path / "missing.yaml")
    services = make_services(settings)
    services.indexer.run()
    found = services.rag.retrieve_detailed(QUESTION, top_k=2)
    assert found.sources and found.glossary.identifiers == []
    with TestClient(create_app(services)) as c:
        body = c.get("/health").json()
    assert body["status"] == "degraded"
    assert body["glossary"]["ok"] is False and "cannot read" in body["glossary"]["error"]


def test_health_reports_glossary_state(settings, tmp_path):
    services = make_services(settings)
    with TestClient(create_app(services)) as c:
        assert c.get("/health").json()["glossary"] == {"enabled": False}
        settings.query_glossary = True
        settings.query_glossary_path = write_glossary(tmp_path)
        body = c.get("/health").json()
        assert body["status"] == "ok"
        assert body["glossary"]["terms"] == 1 and body["glossary"]["active"] is False
        assert "HYBRID_SEARCH=true" in body["glossary"]["note"]
        assert body["retrieval"]["query_glossary"] is True and body["retrieval"]["query_glossary_active"] is False
        settings.hybrid_search = True
        body = c.get("/health").json()
        assert body["glossary"]["active"] is True and "note" not in body["glossary"]
        assert body["retrieval"]["query_glossary_active"] is True


# ── scripts/build_glossary.py ──────────────────────────────────────────────

sys.path.insert(0, str(ROOT / "scripts"))
import build_glossary as bg  # noqa: E402


def test_declarations_are_constants_classes_and_functions_not_locals():
    names = {d.name for d in bg.find_declarations(SAMPLE)}
    assert {"COMBO_STEP", "INVINCIBLE_MS", "ScoreSystem", "SoundManager", "circlesOverlap", "GamePhase"} <= names
    assert not names & {"dx", "ctx", "osc", "pkg"}  # function-local consts


def test_doc_pairs_from_parentheses_backticks_and_tables(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.ts").write_text(
        "export const DASH_SPEED = 1;\nexport const DASH_COOLDOWN_MS = 2;\n"
        "export const PLAYER_MAX_LIVES = 3;\nexport class ScoreSystem {}\n"
        "// 無敵時間\nexport const INVINCIBLE_MS = 1500;\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "g.md").write_text(
        "- Shift：衝刺（dash），有冷卻時間\n"
        "玩家一開始有 3 條命（`PLAYER_MAX_LIVES`）。\n"
        "| ScoreSystem | `src/a.ts` | 分數、連擊倍率 |\n", encoding="utf-8")
    draft = bg.build_draft(tmp_path)
    assert draft["衝刺"].identifiers == ["DASH_COOLDOWN_MS", "DASH_SPEED"]  # English word "dash" -> parts
    assert "PLAYER_MAX_LIVES" in draft["條命"].identifiers
    assert draft["連擊倍率"].identifiers == ["ScoreSystem"] and draft["分數"].identifiers == ["ScoreSystem"]
    assert draft["無敵時間"].identifiers == ["INVINCIBLE_MS"]  # Chinese comment above the declaration
    assert any("docs/g.md:1" in e for e in draft["衝刺"].evidence)


def test_draft_yaml_is_a_loadable_glossary_with_evidence_and_unmapped_list(tmp_path):
    out = tmp_path / "draft.yaml"
    assert bg.main([str(SAMPLE), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "# from docs/" in text and "# Unmapped" in text
    g = load_glossary(out)
    assert "衝刺" in g.terms and "DASH_SPEED" in g.terms["衝刺"]
    # Every identifier in the draft is a real declaration (or a part-matched one).
    names = {d.name for d in bg.find_declarations(SAMPLE)}
    assert {i for ids in g.terms.values() for i in ids} <= names


def test_identifier_parts_match_backend_tokenizer():
    for name in ("MAX_COMBO_MULTIPLIER", "useSyncExternalStore", "HIGH_SCORE_KEY"):
        assert bg.split_identifier(name) == split_identifier(name)
