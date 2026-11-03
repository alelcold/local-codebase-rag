"""SCORE_THRESHOLD (ADR 0014) and RERANK (ADR 0015).

The cross-encoder is replaced by ``FakeReranker``: no model download, no torch.
"""

from __future__ import annotations

import json
import sys
import types

import pytest
from fastapi.testclient import TestClient

from app import rerank as rerank_mod
from app.main import create_app
from app.rag import NO_MATCH_ANSWER, NO_RELEVANT_ANSWER
from app.rerank import CrossEncoderReranker, RerankUnavailableError, rerank_order
from app.retrieval import contains_identifier

from .conftest import FakeLLM, FakeReranker, make_services

# Words that occur nowhere in the fixture project: every cosine is low.
OFF_TOPIC = "multiplayer websocket synchronization lobby matchmaking"


def sse_events(text: str) -> list[tuple[str, dict]]:
    events = []
    for frame in text.strip().split("\n\n"):
        name = data = None
        for line in frame.splitlines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:])
        if name and name != "heartbeat":
            events.append((name, data))
    return events


# --- SCORE_THRESHOLD -----------------------------------------------------------


def test_threshold_off_keeps_previous_behaviour_and_reports_cosine(services):
    services.indexer.run()
    found = services.rag.retrieve_detailed("player jump vy ground", top_k=3)
    assert found.below_threshold == 0 and not found.no_relevant
    assert len(found.sources) == 3
    for s in found.sources:
        assert s.vector_score == s.score  # vector-only: score is the cosine
        assert s.rerank_score is None


def test_threshold_drops_vector_hits_below_it(settings):
    services = make_services(settings)
    services.indexer.run()
    everything = services.rag.retrieve("player jump vy ground", top_k=8)
    cut = sorted(s.vector_score for s in everything)[len(everything) // 2]
    settings.score_threshold = cut
    found = services.rag.retrieve_detailed("player jump vy ground", top_k=8)
    assert found.sources and all(s.vector_score >= cut for s in found.sources)
    assert found.below_threshold == sum(s.vector_score < cut for s in everything)


def test_nothing_above_threshold_answers_without_calling_the_llm(settings):
    settings.score_threshold = 0.95
    llm = FakeLLM(prompts=[])
    services = make_services(settings, llm=llm)
    services.indexer.run()

    result = services.rag.answer(OFF_TOPIC)
    assert result.answer == NO_RELEVANT_ANSWER and result.sources == []

    events = list(services.rag.stream(OFF_TOPIC))
    assert [e.kind for e in events] == ["sources", "token", "done"]
    assert events[0].data == []
    assert events[1].data["text"] == NO_RELEVANT_ANSWER
    assert events[2].data["no_relevant"] is True and events[2].data["below_threshold"] > 0
    assert llm.prompts == []
    # scripts/evaluate.py counts 「找不到」 as a refusal for the trick question.
    assert "找不到" in NO_RELEVANT_ANSWER


def test_empty_retrieval_without_threshold_keeps_the_old_message(settings):
    services = make_services(settings)
    services.indexer.run()
    object.__setattr__(services.store, "query", lambda *a, **k: [])
    assert services.rag.answer("anything").answer == NO_MATCH_ANSWER


def test_query_and_stream_endpoints_refuse_the_same_way(settings):
    settings.score_threshold = 0.95
    llm = FakeLLM(prompts=[])
    services = make_services(settings, llm=llm)
    with TestClient(create_app(services)) as c:
        c.post("/index", json={"wait": True})
        plain = c.post("/query", json={"question": OFF_TOPIC}).json()
        streamed = sse_events(c.post("/query/stream", json={"question": OFF_TOPIC}).text)
        health = c.get("/health").json()
    assert plain == {"answer": NO_RELEVANT_ANSWER, "sources": []}
    assert [n for n, _ in streamed] == ["sources", "token", "done"]
    assert streamed[1][1]["text"] == plain["answer"]
    assert llm.prompts == []
    assert health["retrieval"]["score_threshold"] == 0.95


def test_identifier_hits_are_exempt_from_the_threshold(settings):
    settings.hybrid_search = True
    settings.score_threshold = 0.99  # nothing passes on cosine
    services = make_services(settings)
    services.indexer.run()
    found = services.rag.retrieve_detailed("GRAVITY 在哪裡設定？", top_k=4)
    assert found.sources, "the chunk defining GRAVITY must survive the threshold"
    assert found.sources[0].file_path == "src/player.ts"
    assert "identifier" in found.sources[0].matched_by
    assert "vector" not in found.sources[0].matched_by
    assert found.below_threshold > 0


def test_keyword_hits_without_an_exact_identifier_are_filtered(settings):
    settings.hybrid_search = True
    settings.score_threshold = 0.99
    services = make_services(settings)
    services.indexer.run()
    # "player" is a plain word: BM25 matches it, but it is not exact evidence.
    found = services.rag.retrieve_detailed("how does the player sync over the network", top_k=4)
    assert found.sources == [] and found.no_relevant


def test_contains_identifier_is_whole_word_and_case_sensitive():
    text = "export const INVINCIBLE_MS = 1500;\nthis.takeDamage(1); Game.frame();"
    assert contains_identifier(text, ["INVINCIBLE_MS"])
    assert not contains_identifier(text, ["INVINCIBLE"])  # part of a longer name
    assert not contains_identifier(text, ["invincible_ms"])
    assert contains_identifier(text, ["Player.takeDamage"])  # method name is code-like
    assert not contains_identifier("the frame rate", ["Game.frame"])  # "frame" alone is prose
    assert not contains_identifier(text, [])


# --- RERANK --------------------------------------------------------------------


def test_rerank_reorders_candidates_and_keeps_top_n(settings):
    settings.rerank = True
    settings.rerank_candidates = 6
    settings.rerank_top_n = 2
    reranker = FakeReranker(boost=("Scoring",))
    services = make_services(settings, reranker=reranker)
    services.indexer.run()

    found = services.rag.retrieve_detailed("player jump vy ground")
    assert len(reranker.calls) == 1
    question, passages = reranker.calls[0]
    assert question == "player jump vy ground"
    assert len(passages) == 6  # RERANK_CANDIDATES
    assert len(found.sources) == 2  # RERANK_TOP_N (default when the request has no top_k)
    assert found.sources[0].symbol.endswith("Scoring")  # promoted by the fake cross-encoder
    assert found.sources[0].rerank_score is not None
    assert [s.ref for s in found.sources] == [1, 2]
    assert found.rerank_seconds is not None and found.rerank_seconds >= 0
    # Path and symbol are given to the cross-encoder with the text.
    assert any(p.startswith("docs/guide.md Game Guide > Scoring\n") for p in passages)


def test_request_top_k_overrides_rerank_top_n(settings):
    settings.rerank = True
    settings.rerank_candidates = 3
    reranker = FakeReranker()
    services = make_services(settings, reranker=reranker)
    services.indexer.run()
    found = services.rag.retrieve_detailed("player jump", top_k=5)
    assert len(found.sources) == 5
    assert len(reranker.calls[0][1]) == 5  # candidates are never fewer than top_k


def test_rerank_after_split_keeps_doc_cap_and_code_first(settings):
    settings.rerank = settings.split_retrieval = True
    settings.doc_top_k = 1
    settings.rerank_candidates = 8
    settings.rerank_top_n = 3
    # The fake cross-encoder loves documentation: the cap must still hold.
    reranker = FakeReranker(boost=("#", "Guide", "Controls", "Scoring"))
    services = make_services(settings, reranker=reranker)
    services.indexer.run()
    found = services.rag.retrieve_detailed("jump score controls")
    passages = reranker.calls[0][1]
    assert sum(p.startswith("docs/") for p in passages) <= 1  # split ran before rerank
    paths = [s.file_path for s in found.sources]
    assert sum(p.endswith(".md") for p in paths) <= 1
    is_doc = [p.endswith(".md") for p in paths]
    assert is_doc == sorted(is_doc)  # code first


def test_threshold_runs_before_rerank_and_skips_it_when_nothing_is_left(settings):
    settings.rerank = True
    settings.score_threshold = 0.95
    reranker = FakeReranker()
    services = make_services(settings, reranker=reranker)
    services.indexer.run()
    assert services.rag.answer(OFF_TOPIC).answer == NO_RELEVANT_ANSWER
    assert reranker.calls == []


def test_stream_done_event_reports_rerank_seconds(settings):
    services = make_services(settings)
    services.indexer.run()
    done = list(services.rag.stream("jump", top_k=2))[-1]
    assert done.kind == "done" and done.data["rerank_seconds"] is None

    settings.rerank = True
    services = make_services(settings, reranker=FakeReranker())
    services.indexer.run()
    done = list(services.rag.stream("jump"))[-1]
    assert isinstance(done.data["rerank_seconds"], float)


def test_rerank_off_never_builds_or_imports_the_cross_encoder(settings):
    services = make_services(settings)
    assert services.reranker is None and services.rag.reranker is None
    services.indexer.run()
    services.rag.answer("jump")
    assert "sentence_transformers" not in sys.modules
    with TestClient(create_app(services)) as c:
        body = c.get("/health").json()
    assert body["reranker"] == {"enabled": False}
    assert body["retrieval"]["rerank"] is False


def test_rerank_on_builds_a_lazy_cross_encoder(settings, monkeypatch):
    settings.rerank = True
    services = make_services(settings)
    assert isinstance(services.reranker, CrossEncoderReranker)
    assert services.reranker.loaded is False  # nothing loaded at startup
    assert services.reranker.model_name == "BAAI/bge-reranker-base"


def test_health_degraded_when_rerank_dependencies_are_missing(settings, monkeypatch):
    monkeypatch.setattr("app.services.rerank_installed", lambda: False)
    settings.rerank = True
    settings.rerank_top_n = 2
    services = make_services(settings)
    with TestClient(create_app(services)) as c:
        body = c.get("/health").json()
    assert body["status"] == "degraded"
    assert body["reranker"]["installed"] is False and body["reranker"]["loaded"] is False
    assert body["top_k"] == 2  # the UI starts from the number actually sent to the LLM


def test_cross_encoder_without_dependencies_explains_how_to_rebuild(monkeypatch):
    monkeypatch.setattr(rerank_mod, "rerank_installed", lambda: False)
    with pytest.raises(RerankUnavailableError, match="INSTALL_RERANK=true"):
        CrossEncoderReranker("any").score("q", ["p"])


def test_cross_encoder_loads_once_on_first_use(monkeypatch):
    created = []

    class FakeCrossEncoder:
        def __init__(self, name, max_length):
            created.append((name, max_length))

        def predict(self, pairs, show_progress_bar=False):
            return [float(len(p)) for _, p in pairs]

    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(CrossEncoder=FakeCrossEncoder))
    monkeypatch.setattr(rerank_mod, "rerank_installed", lambda: True)
    r = CrossEncoderReranker("some/model", max_length=256)
    assert created == [] and not r.loaded
    assert r.score("q", []) == [] and created == []  # no passages: nothing to load for
    assert r.score("q", ["aa", "a"]) == [2.0, 1.0]
    assert r.take_load_seconds() is not None and r.take_load_seconds() is None
    r.score("q", ["b"])
    assert created == [("some/model", 256)]


def test_rerank_order_is_stable_on_ties():
    assert rerank_order([0.1, 0.9, 0.9, 0.5]) == [1, 2, 3, 0]
