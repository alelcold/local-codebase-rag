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
