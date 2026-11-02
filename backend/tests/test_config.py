from app.config import Settings


def test_defaults():
    s = Settings()
    assert s.llm_model == "qwen2.5-coder:14b"
    assert s.embed_model == "nomic-embed-text"
    assert s.ollama_base_url == "http://host.docker.internal:11434"
    assert ".tsx" in s.extensions and ".md" in s.extensions
    assert "node_modules" in s.excluded_dirs
    assert s.llm_request_timeout == 300.0
    assert s.embed_request_timeout == 300.0


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "qwen2.5-coder:7b")
    monkeypatch.setenv("EMBED_MODEL", "mxbai-embed-large")
    monkeypatch.setenv("INDEX_EXTENSIONS", "ts, .vue")
    s = Settings()
    assert s.llm_model == "qwen2.5-coder:7b"
    assert s.extensions == {".ts", ".vue"}
    assert s.collection_name == "codebase_mxbai_embed_large"


def test_collection_name_derived_from_embed_model_or_explicit():
    assert Settings(embed_model="nomic-embed-text:v1.5").collection_name == "codebase_nomic_embed_text_v1_5"
    assert Settings(qdrant_collection="mine").collection_name == "mine"


def test_embedding_prefixes():
    nomic = Settings(embed_model="nomic-embed-text")
    assert nomic.query_prefix == "search_query: "
    assert nomic.doc_prefix == "search_document: "
    other = Settings(embed_model="bge-m3")
    assert other.query_prefix == other.doc_prefix == ""
    custom = Settings(embed_model="bge-m3", embed_query_prefix="q: ", embed_doc_prefix="d: ")
    assert custom.query_prefix == "q: "
    assert custom.doc_prefix == "d: "


def test_empty_prefix_env_means_auto(monkeypatch):
    # docker compose passes unset variables as empty strings.
    monkeypatch.setenv("EMBED_QUERY_PREFIX", "")
    monkeypatch.setenv("EMBED_DOC_PREFIX", "")
    monkeypatch.setenv("QDRANT_COLLECTION", "")
    s = Settings()
    assert s.query_prefix == "search_query: "
    assert s.doc_prefix == "search_document: "
    assert s.collection_name == "codebase_nomic_embed_text"


def test_request_timeouts_from_env(monkeypatch):
    monkeypatch.setenv("LLM_REQUEST_TIMEOUT", "600")
    monkeypatch.setenv("EMBED_REQUEST_TIMEOUT", "120")
    s = Settings()
    assert s.llm_request_timeout == 600.0
    assert s.embed_request_timeout == 120.0


def test_build_services_passes_timeouts_to_ollama_clients(monkeypatch):
    from qdrant_client import QdrantClient

    from app import services as services_module

    # No network: build_services would otherwise contact Qdrant for a version check.
    monkeypatch.setattr(services_module, "QdrantClient", lambda **_: QdrantClient(location=":memory:"))
    s = Settings(llm_request_timeout=111, embed_request_timeout=222, qdrant_url="http://qdrant.test:6333")
    services = services_module.build_services(s)
    assert services.llm.request_timeout == 111
    # OllamaEmbedding hands client_kwargs to ollama.Client, which builds an httpx client.
    assert services.embed_model._client._client.timeout.read == 222
