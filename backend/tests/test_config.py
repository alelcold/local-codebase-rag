from app.config import Settings


def test_defaults():
    s = Settings()
    assert s.llm_model == "qwen2.5-coder:14b"
    assert s.embed_model == "nomic-embed-text"
    assert s.ollama_base_url == "http://host.docker.internal:11434"
    assert ".tsx" in s.extensions and ".md" in s.extensions
    assert "node_modules" in s.excluded_dirs


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
