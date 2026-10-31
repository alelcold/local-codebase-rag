from app.chunker import chunk_file, language_for

from .conftest import FIXTURE_PROJECT


def _by_symbol(chunks):
    return {c.symbol: c for c in chunks}


def _lines(text: str, start: int, end: int) -> str:
    return "\n".join(text.split("\n")[start - 1 : end])


def test_typescript_splits_by_function_and_class_with_line_numbers():
    text = (FIXTURE_PROJECT / "src/player.ts").read_text()
    chunks = chunk_file("src/player.ts", text)
    symbols = _by_symbol(chunks)

    assert symbols["Player"].kind == "class"
    assert symbols["createPlayer"].kind == "function"
    # JSDoc above the class is part of the class chunk.
    player = symbols["Player"]
    assert player.text.startswith("/**\n * The controllable character.")
    assert (player.start_line, player.end_line) == (6, 25)
    # Reported line range matches the chunk text exactly.
    for c in chunks:
        assert c.text == _lines(text, c.start_line, c.end_line)
        assert c.language == "typescript"


def test_imports_and_constants_become_module_chunks():
    text = (FIXTURE_PROJECT / "src/player.ts").read_text()
    chunks = chunk_file("src/player.ts", text)
    module = [c for c in chunks if c.kind == "module"]
    assert len(module) == 1
    assert "import { clamp }" in module[0].text
    assert "GRAVITY = 1800" in module[0].text
    assert module[0].start_line == 1


def test_tsx_arrow_components_interfaces_and_default_export():
    text = (FIXTURE_PROJECT / "src/hud.tsx").read_text()
    symbols = _by_symbol(chunk_file("src/hud.tsx", text))
    assert symbols["HudProps"].kind == "interface"
    assert symbols["Hud"].kind == "function"
    assert "<span>Score: {score}</span>" in symbols["Hud"].text
    assert symbols["GameOver"].kind == "function"
    assert symbols["GameOver"].language == "tsx"


def test_javascript_function_and_arrow():
    text = (FIXTURE_PROJECT / "src/util.js").read_text()
    symbols = _by_symbol(chunk_file("src/util.js", text))
    assert (symbols["clamp"].start_line, symbols["clamp"].end_line) == (1, 3)
    assert (symbols["lerp"].start_line, symbols["lerp"].end_line) == (5, 5)


def test_wrapped_components_and_classes_detected():
    text = (
        "const Memo = React.memo(function Inner() { return null; });\n"
        "const Fwd = forwardRef((props, ref) => null);\n"
        "const Klass = class { run() {} };\n"
        "export default () => 42;\n"
    )
    symbols = _by_symbol(chunk_file("src/x.jsx", text))
    assert symbols["Memo"].kind == "function"
    assert symbols["Fwd"].kind == "function"
    assert symbols["Klass"].kind == "class"
    assert symbols["default"].kind == "function"


def test_oversized_class_is_split_per_method():
    methods = "\n".join(
        f"  /** method {i} */\n  method{i}(): number {{\n" + "    const v = 1;\n" * 8 + f"    return {i};\n  }}\n"
        for i in range(6)
    )
    text = f"export class Big {{\n  field = 1;\n\n{methods}}}\n"
    chunks = chunk_file("src/big.ts", text, max_chars=400)
    method_chunks = [c for c in chunks if c.kind == "method"]
    assert [c.symbol for c in method_chunks] == [f"Big.method{i}" for i in range(6)]
    first = method_chunks[0]
    assert first.text.lstrip().startswith("/** method 0 */")
    assert first.text == _lines(text, first.start_line, first.end_line)
    # Header with the field is kept as its own class chunk.
    assert any(c.kind == "class" and "field = 1" in c.text for c in chunks)
    assert all(len(c.text) <= 400 for c in chunks)


def test_oversized_function_is_split_into_line_windows():
    body = "".join(f"  const value{i} = compute({i});\n" for i in range(200))
    text = f"function huge() {{\n{body}}}\n"
    chunks = chunk_file("src/huge.js", text, max_chars=1000)
    assert len(chunks) > 1
    assert all(len(c.text) <= 1000 for c in chunks)
    assert chunks[0].start_line == 1
    assert chunks[-1].end_line == 202
    assert chunks[0].symbol == "huge (part 1)"
    # Windows are contiguous or overlapping: no line is lost.
    for prev, nxt in zip(chunks, chunks[1:]):
        assert nxt.start_line <= prev.end_line + 1


def test_markdown_splits_by_heading_and_ignores_fenced_hashes():
    text = (FIXTURE_PROJECT / "docs/guide.md").read_text()
    chunks = chunk_file("docs/guide.md", text)
    assert [c.symbol for c in chunks] == ["Game Guide", "Game Guide > Controls", "Game Guide > Scoring"]
    controls = chunks[1]
    assert "# this is not a heading" in controls.text
    assert controls.text == _lines(text, controls.start_line, controls.end_line)
    assert all(c.kind == "section" and c.language == "markdown" for c in chunks)


def test_markdown_preamble_before_first_heading():
    chunks = chunk_file("notes.md", "intro text\n\n# A\nbody\n### Deep\nmore\n## B\nx\n")
    assert [(c.symbol, c.start_line) for c in chunks] == [(None, 1), ("A", 3), ("A > Deep", 5), ("A > B", 7)]


def test_other_extensions_use_line_windows():
    text = "\n".join(f"line {i}" for i in range(50))
    chunks = chunk_file("styles/app.css", text, max_chars=100)
    assert len(chunks) > 1
    assert all(c.kind == "text" for c in chunks)


def test_empty_file_and_crlf():
    assert chunk_file("src/empty.ts", "  \n\n") == []
    chunks = chunk_file("src/crlf.ts", "function a() {\r\n  return 1;\r\n}\r\n")
    assert chunks[0].symbol == "a"
    assert "\r" not in chunks[0].text


def test_language_for():
    assert language_for("a/b.ts") == "typescript"
    assert language_for("a/b.tsx") == "tsx"
    assert language_for("a/b.mjs") == "javascript"
    assert language_for("README.md") == "markdown"


def test_heading_without_body_is_merged_into_next_section():
    text = "# Rules\n\n## Controls\nPress space.\n## Lives\nThree lives.\n"
    chunks = chunk_file("docs/rules.md", text)
    assert [(c.symbol, c.start_line, c.end_line) for c in chunks] == [
        ("Rules > Controls", 1, 4),
        ("Rules > Lives", 5, 6),
    ]


def test_arrow_function_class_fields_are_split_like_methods():
    handlers = "\n".join(
        f"  private on{i} = (e: Event) => {{\n" + "    console.log(e);\n" * 10 + "  };\n" for i in range(4)
    )
    text = f"class Input {{\n  held = new Set();\n{handlers}}}\n"
    chunks = chunk_file("src/input.ts", text, max_chars=400)
    assert [c.symbol for c in chunks if c.kind == "method"] == [f"Input.on{i}" for i in range(4)]
