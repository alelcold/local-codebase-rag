import json
from unittest.mock import MagicMock

import httpx

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

from .conftest import FakeLLM, make_services, ollama_transport


@pytest.fixture
def llm():
    return FakeLLM(prompts=[], answer="Jump logic is in Player.jump [1].")


@pytest.fixture
def client(settings, llm):
    services = make_services(settings, llm=llm)
    with TestClient(create_app(services)) as c:
        yield c


def test_health_ok(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["ollama"]["ok"] is True
    assert body["ollama"]["missing_models"] == []
    assert body["qdrant"] == {
        "ok": True,
        "url": "http://qdrant.test:6333",
        "collection": "codebase_nomic_embed_text",
        "indexed": False,
        "points": 0,
        "index_config": body["qdrant"]["index_config"],
        "reindex_needed": False,
    }
    assert "chunk_metadata=off" in body["qdrant"]["index_config"]
    assert body["retrieval"]["hybrid_search"] is False
    assert body["retrieval"]["prompt_variant"] == "v1"


def test_health_reports_missing_model(settings):
    services = make_services(settings, transport=ollama_transport(models=["nomic-embed-text:latest"]))
    with TestClient(create_app(services)) as c:
        body = c.get("/health").json()
    assert body["status"] == "degraded"
    assert body["ollama"]["missing_models"] == ["qwen2.5-coder:14b"]


def test_health_reports_ollama_down(settings):
    services = make_services(settings, transport=ollama_transport(down=True))
    with TestClient(create_app(services)) as c:
        body = c.get("/health").json()
    assert body["status"] == "degraded"
    assert body["ollama"]["ok"] is False
    assert "ConnectError" in body["ollama"]["error"]


def test_health_reports_qdrant_down(settings):
    services = make_services(settings)
    services.store.client = MagicMock()
    services.store.client.collection_exists.side_effect = ConnectionError("qdrant down")
    with TestClient(create_app(services)) as c:
        body = c.get("/health").json()
    assert body["status"] == "degraded"
    assert body["qdrant"]["ok"] is False
    assert "qdrant down" in body["qdrant"]["error"]


def test_index_wait_then_query(client, llm):
    resp = client.post("/index", json={"wait": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "done"
    assert len(body["report"]["added"]) == 4
    assert client.get("/index/status").json()["state"] == "done"
    assert client.get("/health").json()["qdrant"]["points"] > 0

    resp = client.post("/query", json={"question": "How does the player jump?", "top_k": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "Jump logic is in Player.jump [1]."
    assert len(body["sources"]) == 3
    src = body["sources"][0]
    assert set(src) >= {"ref", "file_path", "start_line", "end_line", "symbol", "score", "text"}
    assert len(llm.prompts) == 1


def test_index_in_background(client):
    resp = client.post("/index", json={"full": True})
    assert resp.status_code == 200
    assert resp.json()["state"] == "running"
    # Wait for the background thread by polling status.
    for _ in range(200):
        status = client.get("/index/status").json()
        if status["state"] != "running":
            break
        import time

        time.sleep(0.02)
    assert status["state"] == "done"
    assert status["full"] is True


def test_index_without_body_defaults_to_incremental(client):
    resp = client.post("/index")
    assert resp.status_code == 200
    assert resp.json()["full"] is False


def test_index_conflict_when_running(client):
    client.app.state.index_job.state = "running"
    assert client.post("/index", json={"wait": True}).status_code == 409


def test_index_error_is_reported(settings, tmp_path):
    settings.codebase_path = str(tmp_path / "missing")
    with TestClient(create_app(make_services(settings))) as c:
        resp = c.post("/index", json={"wait": True})
        assert resp.status_code == 500
        assert "FileNotFoundError" in resp.json()["detail"]
        assert c.get("/index/status").json()["state"] == "error"


def test_query_before_index(client, llm):
    body = client.post("/query", json={"question": "anything"}).json()
    assert "還沒有任何索引" in body["answer"]
    assert body["sources"] == []
    assert llm.prompts == []


@pytest.mark.parametrize("payload", [{}, {"question": ""}, {"question": "   "}, {"question": "q", "top_k": 0}])
def test_query_validation(client, payload):
    assert client.post("/query", json=payload).status_code == 422


def test_query_llm_failure_returns_502(settings):
    llm = FakeLLM(prompts=[])
    services = make_services(settings, llm=llm)
    services.indexer.run()
    object.__setattr__(services.rag, "llm", MagicMock(complete=MagicMock(side_effect=RuntimeError("model crashed"))))
    with TestClient(create_app(services)) as c:
        resp = c.post("/query", json={"question": "jump"})
    assert resp.status_code == 502
    assert "RuntimeError" in resp.json()["detail"]


def _wrapped_read_timeout() -> Exception:
    # The ollama client lets httpx.ReadTimeout escape; LlamaIndex may wrap it.
    try:
        try:
            raise httpx.ReadTimeout("timed out")
        except httpx.ReadTimeout as inner:
            raise RuntimeError("completion failed") from inner
    except RuntimeError as outer:
        return outer


@pytest.mark.parametrize("error", [httpx.ReadTimeout("timed out"), TimeoutError("slow"), _wrapped_read_timeout()])
def test_query_llm_timeout_returns_504_with_setting_name(settings, error):
    settings = settings.model_copy(update={"llm_request_timeout": 300.0})
    services = make_services(settings)
    services.indexer.run()
    object.__setattr__(services.rag, "llm", MagicMock(complete=MagicMock(side_effect=error)))
    with TestClient(create_app(services)) as c:
        resp = c.post("/query", json={"question": "jump"})
    assert resp.status_code == 504
    detail = resp.json()["detail"]
    assert "生成回答逾時" in detail
    assert "300 秒" in detail
    assert "LLM_REQUEST_TIMEOUT" in detail


def test_query_embedding_timeout_returns_504(settings):
    settings = settings.model_copy(update={"embed_request_timeout": 45.0})
    services = make_services(settings)
    services.indexer.run()
    slow = MagicMock(get_query_embedding=MagicMock(side_effect=httpx.ReadTimeout("timed out")))
    object.__setattr__(services.rag, "embed_model", slow)
    with TestClient(create_app(services)) as c:
        resp = c.post("/query", json={"question": "jump"})
    assert resp.status_code == 504
    detail = resp.json()["detail"]
    assert "embedding" in detail
    assert "45 秒" in detail
    assert "EMBED_REQUEST_TIMEOUT" in detail


# --- /query/stream (Server-Sent Events) -------------------------------------


def parse_sse(body: str) -> list[tuple[str, dict]]:
    """Parse an SSE body into (event, data) pairs, the way the frontend does."""
    events = []
    for frame in body.split("\n\n"):
        name, data = "message", []
        for line in frame.splitlines():
            if line.startswith("event:"):
                name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data.append(line[len("data:") :].strip())
        if data:
            events.append((name, json.loads("\n".join(data))))
    return events


def stream_query(client, payload: dict) -> tuple[httpx.Response, list[tuple[str, dict]]]:
    with client.stream("POST", "/query/stream", json=payload) as resp:
        body = "".join(resp.iter_text())
    return resp, parse_sse(body)


def without_heartbeats(events):
    return [(name, data) for name, data in events if name != "heartbeat"]


def test_stream_sends_sources_then_tokens_then_done(client, llm):
    client.post("/index", json={"wait": True})
    resp, events = stream_query(client, {"question": "How does the player jump?", "top_k": 3})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers["cache-control"] == "no-cache"
    assert resp.headers["x-accel-buffering"] == "no"
    # The first frame is sent before any slow work, so proxies see bytes at once.
    assert events[0][0] == "heartbeat"

    names = [name for name, _ in without_heartbeats(events)]
    assert names[0] == "sources"
    assert names[-1] == "done"
    assert set(names[1:-1]) == {"token"}
    assert len(names[1:-1]) > 1, "the answer should arrive in several token events"

    sources = without_heartbeats(events)[0][1]
    assert len(sources) == 3
    assert set(sources[0]) >= {"ref", "file_path", "start_line", "end_line", "symbol", "score", "text"}

    tokens = "".join(data["text"] for name, data in events if name == "token")
    assert tokens == "Jump logic is in Player.jump [1]."

    stats = events[-1][1]
    assert stats["tokens"] == len(names[1:-1])
    assert stats["answer_chars"] == len(tokens)
    assert 0 <= stats["retrieval_seconds"] <= stats["first_token_seconds"] <= stats["total_seconds"]
    assert len(llm.prompts) == 1


def test_stream_answer_matches_non_streaming_query(client):
    client.post("/index", json={"wait": True})
    payload = {"question": "How is the score shown?", "top_k": 2}
    plain = client.post("/query", json=payload).json()
    _, events = stream_query(client, payload)
    tokens = "".join(data["text"] for name, data in events if name == "token")
    sources = next(data for name, data in events if name == "sources")
    assert tokens == plain["answer"]
    assert [s["file_path"] for s in sources] == [s["file_path"] for s in plain["sources"]]


def test_stream_sends_heartbeats_while_the_model_is_silent(settings):
    settings = settings.model_copy(update={"stream_heartbeat_seconds": 0.05})
    llm = FakeLLM(prompts=[], answer="Slow answer [1].", delay=0.4)
    services = make_services(settings, llm=llm)
    services.indexer.run()
    with TestClient(create_app(services)) as c:
        _, events = stream_query(c, {"question": "jump"})
    names = [name for name, _ in events]
    first_token = names.index("token")
    sources_at = names.index("sources")
    # Several heartbeats between the sources and the first token (0.4 s / 0.05 s).
    assert names[sources_at:first_token].count("heartbeat") >= 3
    elapsed = [data["elapsed_seconds"] for name, data in events if name == "heartbeat"]
    assert elapsed == sorted(elapsed)
    assert names[-1] == "done"
    assert events[-1][1]["first_token_seconds"] >= 0.4


def test_stream_before_index_returns_hint(client, llm):
    _, events = stream_query(client, {"question": "anything"})
    events = without_heartbeats(events)
    assert [name for name, _ in events] == ["sources", "token", "done"]
    assert events[0][1] == []
    assert "還沒有任何索引" in events[1][1]["text"]
    assert llm.prompts == []


@pytest.mark.parametrize("payload", [{}, {"question": ""}, {"question": "   "}, {"question": "q", "top_k": 0}])
def test_stream_validation(client, payload):
    assert client.post("/query/stream", json=payload).status_code == 422


def _streaming_llm(error: Exception, after: list[str] | None = None) -> MagicMock:
    from llama_index.core.llms import CompletionResponse

    def gen(prompt):
        text = ""
        for piece in after or []:
            text += piece
            yield CompletionResponse(text=text, delta=piece)
        raise error

    return MagicMock(stream_complete=MagicMock(side_effect=gen))


def test_stream_llm_timeout_sends_error_event_after_sources(settings):
    settings = settings.model_copy(update={"llm_request_timeout": 120.0})
    services = make_services(settings)
    services.indexer.run()
    object.__setattr__(services.rag, "llm", _streaming_llm(httpx.ReadTimeout("timed out"), after=["Partial ", "answer"]))
    with TestClient(create_app(services)) as c:
        resp, events = stream_query(c, {"question": "jump"})
    assert resp.status_code == 200  # the status line went out before the timeout
    events = without_heartbeats(events)
    assert [name for name, _ in events] == ["sources", "token", "token", "error"]
    error = events[-1][1]
    assert error["kind"] == "timeout"
    assert error["stage"] == "llm"
    assert "生成回答逾時" in error["detail"]
    assert "120 秒" in error["detail"]
    assert "LLM_REQUEST_TIMEOUT" in error["detail"]


def test_stream_embedding_timeout_sends_error_event(settings):
    services = make_services(settings)
    services.indexer.run()
    slow = MagicMock(get_query_embedding=MagicMock(side_effect=httpx.ReadTimeout("timed out")))
    object.__setattr__(services.rag, "embed_model", slow)
    with TestClient(create_app(services)) as c:
        _, events = stream_query(c, {"question": "jump"})
    events = without_heartbeats(events)
    assert [name for name, _ in events] == ["error"]
    assert events[0][1]["stage"] == "embedding"
    assert "EMBED_REQUEST_TIMEOUT" in events[0][1]["detail"]


def test_stream_llm_failure_sends_error_event(settings):
    services = make_services(settings)
    services.indexer.run()
    object.__setattr__(services.rag, "llm", _streaming_llm(RuntimeError("model crashed")))
    with TestClient(create_app(services)) as c:
        _, events = stream_query(c, {"question": "jump"})
    events = without_heartbeats(events)
    assert [name for name, _ in events] == ["sources", "error"]
    assert events[-1][1] == {"kind": "error", "detail": "RuntimeError: model crashed"}


def test_health_reports_default_top_k(client):
    assert client.get("/health").json()["top_k"] == 4


# --- Retrieval switches (ADR 0013) ---------------------------------------------


def test_health_reports_reindex_needed_after_changing_chunk_metadata(settings):
    services = make_services(settings)
    with TestClient(create_app(services)) as c:
        assert c.post("/index", json={"wait": True}).status_code == 200
        assert c.get("/health").json()["qdrant"]["reindex_needed"] is False
        settings.chunk_metadata = True
        body = c.get("/health").json()
        assert body["qdrant"]["reindex_needed"] is True
        assert body["retrieval"]["chunk_metadata"] is True
        report = c.post("/index", json={"wait": True}).json()["report"]
        assert report["full"] is True and "chunk_metadata=on" in report["rebuild_reason"]
        assert c.get("/health").json()["qdrant"]["reindex_needed"] is False


def test_stream_with_every_switch_on_reports_matched_by(settings):
    settings.hybrid_search = settings.split_retrieval = settings.chunk_metadata = True
    settings.prompt_variant = "v2"
    services = make_services(settings, llm=FakeLLM(prompts=[], answer="在 [1] src/player.ts。"))
    with TestClient(create_app(services)) as c:
        c.post("/index", json={"wait": True})
        resp, events = stream_query(c, {"question": "GRAVITY 在哪裡設定？", "top_k": 3})
    assert resp.status_code == 200
    events = without_heartbeats(events)
    assert [name for name, _ in events][0] == "sources" and events[-1][0] == "done"
    sources = events[0][1]
    assert sources[0]["file_path"] == "src/player.ts"
    assert "identifier" in sources[0]["matched_by"]
    assert sum(s["file_path"].endswith(".md") for s in sources) <= 1
