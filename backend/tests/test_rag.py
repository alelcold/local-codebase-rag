from app.rag import NO_INDEX_ANSWER, build_prompt

from .conftest import FakeLLM, make_services


def test_query_before_indexing_returns_hint_without_calling_llm(settings):
    llm = FakeLLM(prompts=[])
    services = make_services(settings, llm=llm)
    result = services.rag.answer("How does the player jump?")
    assert result.answer == NO_INDEX_ANSWER
    assert result.sources == []
    assert llm.prompts == []


def test_retrieval_ranks_relevant_code_first(services):
    services.indexer.run()
    sources = services.rag.retrieve("player jump vy ground", top_k=3)
    assert sources[0].file_path == "src/player.ts"
    assert [s.ref for s in sources] == [1, 2, 3]
    assert all(s.start_line >= 1 and s.end_line >= s.start_line for s in sources)


def test_answer_prompt_contains_numbered_citations_with_lines(settings):
    llm = FakeLLM(prompts=[], answer="It sets vy to -600 [1].")
    services = make_services(settings, llm=llm)
    services.indexer.run()

    result = services.rag.answer("How does the player jump?", top_k=2)
    assert result.answer == "It sets vy to -600 [1]."
    assert len(result.sources) == 2
    prompt = llm.prompts[0]
    first = result.sources[0]
    assert f"[1] {first.file_path}:{first.start_line}-{first.end_line}" in prompt
    assert first.text in prompt
    assert "How does the player jump?" in prompt


def test_query_uses_query_prefix(settings):
    seen = []
    services = make_services(settings)
    services.indexer.run()
    original = services.embed_model.get_query_embedding

    def spy(text):
        seen.append(text)
        return original(text)

    object.__setattr__(services.embed_model, "get_query_embedding", spy)
    services.rag.retrieve("score")
    assert seen == ["search_query: score"]


def test_build_prompt_formats_markdown_and_symbols(services):
    services.indexer.run()
    sources = services.rag.retrieve("controls jump space", top_k=8)
    prompt = build_prompt("q", sources)
    md = next(s for s in sources if s.language == "markdown")
    assert f"({md.kind} {md.symbol})" in prompt
    assert "```md\n" in prompt


def test_stream_strips_leading_whitespace_and_handles_missing_delta(settings):
    from llama_index.core.llms import CompletionResponse
    from unittest.mock import MagicMock

    services = make_services(settings)
    services.indexer.run()

    def gen(prompt):
        # Like an LLM that fills in only the accumulated text, starting with a newline.
        for text in ["\n", "\nIt ", "\nIt jumps [1]."]:
            yield CompletionResponse(text=text)

    object.__setattr__(services.rag, "llm", MagicMock(stream_complete=MagicMock(side_effect=gen)))
    events = list(services.rag.stream("jump", top_k=2))
    assert [e.kind for e in events] == ["sources", "token", "token", "done"]
    assert "".join(e.data["text"] for e in events if e.kind == "token") == "It jumps [1]."
    assert events[-1].data["tokens"] == 2
    assert events[-1].data["answer_chars"] == len("It jumps [1].")


def test_stream_with_no_matches_returns_hint(settings):
    from app.rag import NO_MATCH_ANSWER

    services = make_services(settings)
    services.indexer.run()
    object.__setattr__(services.store, "query", lambda embedding, k: [])
    events = list(services.rag.stream("anything"))
    assert [e.kind for e in events] == ["sources", "token", "done"]
    assert events[1].data == {"text": NO_MATCH_ANSWER}


# ── Hybrid retrieval, split retrieval, prompt v2 (ADR 0013) ────────────────

DOC_NOISE = "\n\n".join(
    f"## Section {i}\n\nThe player jumps with gravity. Player jump gravity ground, player jump vy." for i in range(6)
)


def _with_noisy_docs(codebase):
    # Docs that repeat the question's words and outrank the code in vector search.
    (codebase / "docs/notes.md").write_text(f"# Notes\n\n{DOC_NOISE}\n")


def test_defaults_are_the_vector_only_baseline(services):
    services.indexer.run()
    sources = services.rag.retrieve("player jump", top_k=3)
    assert all(s.matched_by == ["vector"] for s in sources)
    assert services.settings.retrieval_summary()["hybrid_search"] is False


def test_hybrid_search_finds_the_chunk_defining_a_named_identifier(settings):
    services = make_services(settings)
    services.indexer.run()
    question = "Where is GRAVITY defined?"
    # The fake embedding cannot see "GRAVITY" (it lower-cases words), so check the
    # identifier channel alone gets the defining chunk to the top.
    settings.hybrid_search = True
    sources = services.rag.retrieve(question, top_k=2)
    top = sources[0]
    assert top.file_path == "src/player.ts"
    assert "export const GRAVITY = 1800;" in top.text
    assert "identifier" in top.matched_by and "keyword" in top.matched_by
    assert 0 < top.score < 0.1  # an RRF score, not a cosine similarity


def test_hybrid_search_without_identifiers_still_returns_results(settings):
    settings.hybrid_search = True
    services = make_services(settings)
    services.indexer.run()
    sources = services.rag.retrieve("how does the player jump", top_k=3)
    assert len(sources) == 3
    assert sources[0].file_path == "src/player.ts"


def test_keyword_index_is_rebuilt_after_reindexing(settings, codebase):
    settings.hybrid_search = True
    services = make_services(settings)
    services.indexer.run()
    first = services.rag.keyword_index()
    assert services.rag.keyword_index() is first  # cached while nothing changed

    (codebase / "src/enemy.ts").write_text("export const ENEMY_SPEED = 42;\n")
    services.indexer.run()
    second = services.rag.keyword_index()
    assert second is not first
    assert services.rag.retrieve("ENEMY_SPEED", top_k=1)[0].file_path == "src/enemy.ts"


def test_split_retrieval_caps_documentation_and_lists_code_first(settings, codebase):
    _with_noisy_docs(codebase)
    services = make_services(settings)
    services.indexer.run()
    question = "player jump gravity ground"

    baseline = services.rag.retrieve(question, top_k=4)
    assert sum(s.file_path.endswith(".md") for s in baseline) >= 3  # docs crowd out code

    settings.split_retrieval = True
    settings.doc_top_k = 1
    split = services.rag.retrieve(question, top_k=4)
    kinds = ["doc" if s.file_path.endswith(".md") else "code" for s in split]
    assert kinds == ["code", "code", "code", "doc"]
    assert [s.ref for s in split] == [1, 2, 3, 4]
    assert split[0].file_path == "src/player.ts"


def test_all_toggles_together(settings, codebase):
    _with_noisy_docs(codebase)
    settings.hybrid_search = settings.split_retrieval = settings.chunk_metadata = True
    settings.prompt_variant = "v2"
    llm = FakeLLM(prompts=[], answer="位置在 [1] src/player.ts:4。")
    services = make_services(settings, llm=llm)
    services.indexer.run()
    result = services.rag.answer("GRAVITY 在哪裡設定？", top_k=3)
    assert result.sources[0].file_path == "src/player.ts"
    assert "GRAVITY = 1800" in result.sources[0].text
    assert sum(s.file_path.endswith(".md") for s in result.sources) <= 1
    assert "一律使用繁體中文" in llm.prompts[0]


def test_prompt_v2_asks_for_traditional_chinese_and_code_locations_first():
    from app.rag import Source

    sources = [
        Source(1, "src/config/gameConfig.ts", 1, 10, "", "module", "typescript", 0.5, "export const A = 1;"),
        Source(2, "docs/gameplay.md", 3, 8, "Rules", "section", "markdown", 0.4, "text"),
    ]
    v2 = build_prompt("無敵時間在哪裡設定？", sources, "v2")
    assert "繁體中文" in v2 and "不要使用簡體字" in v2
    assert "先說明程式碼位置" in v2
    assert "[1] src/config/gameConfig.ts:1-10 — 程式碼" in v2
    assert "[2] docs/gameplay.md:3-8 (section Rules) — 文件" in v2
    assert v2.rstrip().endswith("## 回答")

    v1 = build_prompt("q", sources)
    assert "Reply in the same language as the question" in v1
    assert "— 程式碼" not in v1


# ── Prompt v3: say "not found" for topics the excerpts do not mention (ADR 0016) ──


def _two_sources():
    from app.rag import Source

    return [
        Source(1, "src/config/gameConfig.ts", 1, 10, "", "module", "typescript", 0.5, "export const A = 1;"),
        Source(2, "docs/gameplay.md", 3, 8, "Rules", "section", "markdown", 0.4, "text"),
    ]


def test_prompt_v3_is_v1_plus_a_refusal_rule_and_traditional_chinese():
    from app.rag import REFUSAL_SENTENCE, SYSTEM_PROMPT, SYSTEM_PROMPT_V3

    v3 = build_prompt("線上多人模式怎麼同步玩家位置？", _two_sources(), "v3")
    assert v3.startswith(SYSTEM_PROMPT_V3)
    # The refusal is one fixed sentence the model can copy; it must contain 「找不到」,
    # which scripts/evaluate.py counts as a refusal.
    assert "找不到" in REFUSAL_SENTENCE and "索引的專案" in REFUSAL_SENTENCE
    assert f"reply with exactly: {REFUSAL_SENTENCE}" in SYSTEM_PROMPT_V3
    assert "directly mentions the topic" in SYSTEM_PROMPT_V3
    assert "Do not guess" in SYSTEM_PROMPT_V3 and "general knowledge" in SYSTEM_PROMPT_V3
    assert "Always answer in Traditional Chinese" in SYSTEM_PROMPT_V3
    # Kept from v1: citations and no invented files.
    assert "Cite every claim" in SYSTEM_PROMPT and "Cite every claim" in SYSTEM_PROMPT_V3
    assert "Never invent files, functions or line numbers" in SYSTEM_PROMPT_V3
    # Dropped from v1: it invited talking about related code instead of refusing.
    assert "suggest what to search for" in SYSTEM_PROMPT and "suggest what to search" not in SYSTEM_PROMPT_V3
    assert "Reply in the same language" not in SYSTEM_PROMPT_V3


def test_prompt_v3_keeps_v1_layout_and_repeats_the_rule_after_the_question():
    from app.rag import REFUSAL_REMINDER

    v1 = build_prompt("q?", _two_sources(), "v1")
    v3 = build_prompt("q?", _two_sources(), "v3")
    # Same excerpt headers as v1: no v2 「程式碼／文件」 labels, no v2 Chinese headings.
    for header in ("[1] src/config/gameConfig.ts:1-10\n", "[2] docs/gameplay.md:3-8 (section Rules)\n"):
        assert header in v1 and header in v3
    assert "— 程式碼" not in v3 and "— 文件" not in v3 and "## 程式碼片段" not in v3
    assert "## Code excerpts" in v3
    # The reminder sits between the question and the answer slot, where a small model still sees it.
    assert v3.rstrip().endswith(f"## Question\n\nq?\n{REFUSAL_REMINDER}\n\n## Answer")
    assert REFUSAL_REMINDER not in v1


def test_prompt_v3_rules_stay_short_for_small_models():
    """qwen2.5-coder:3b drops rules from long instructions (ADR 0016): keep v3 within
    a few lines more than v1 and shorter than v2."""
    from app.rag import SYSTEM_PROMPT, SYSTEM_PROMPT_V2, SYSTEM_PROMPT_V3

    rules = [line for line in SYSTEM_PROMPT_V3.splitlines() if line[:2] in {f"{n}." for n in range(1, 10)}]
    assert len(rules) <= 5
    assert len(SYSTEM_PROMPT_V3.splitlines()) <= len(SYSTEM_PROMPT.splitlines()) + 2
    assert len(SYSTEM_PROMPT_V3) < len(SYSTEM_PROMPT) * 1.5


def test_answer_and_stream_use_prompt_v3(settings):
    from app.rag import REFUSAL_REMINDER, REFUSAL_SENTENCE

    settings.prompt_variant = "v3"
    llm = FakeLLM(prompts=[], answer=REFUSAL_SENTENCE)
    services = make_services(settings, llm=llm)
    services.indexer.run()
    result = services.rag.answer("How does online multiplayer sync positions?", top_k=2)
    assert result.answer == REFUSAL_SENTENCE
    assert REFUSAL_REMINDER in llm.prompts[0]
    events = list(services.rag.stream("How does online multiplayer sync positions?", top_k=2))
    assert REFUSAL_REMINDER in llm.prompts[1]
    assert "".join(e.data["text"] for e in events if e.kind == "token") == REFUSAL_SENTENCE
