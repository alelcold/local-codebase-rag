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
    }


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
