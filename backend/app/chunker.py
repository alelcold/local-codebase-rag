"""Split source files into retrieval chunks that keep their original line numbers.

- .ts/.tsx/.js/.jsx/.mjs/.cjs: parsed with tree-sitter, one chunk per top-level
  function / class / interface / type / enum (leading JSDoc attached). Imports
  and other top-level statements are grouped into "module" chunks. Classes that
  are too large are split into one chunk per member.
- .md: one chunk per heading section (headings inside fenced code are ignored).
- anything else: fixed-size line windows.

Chunks larger than ``max_chars`` are further split into line windows, so every
chunk stays small enough for the embedding model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import PurePosixPath

import tree_sitter
import tree_sitter_javascript
import tree_sitter_typescript

# Bump when chunking output changes, so incremental indexing re-chunks every file.
CHUNKER_VERSION = "1"

WINDOW_OVERLAP_LINES = 3

JS_LIKE_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts"}
MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdx"}

_FUNCTION_VALUE_TYPES = {
    "arrow_function",
    "function_expression",
    "function",
    "generator_function",
}
_CLASS_VALUE_TYPES = {"class", "class_expression"}
_DECLARATION_KINDS = {
    "function_declaration": "function",
    "generator_function_declaration": "function",
    "function_signature": "function",
    "class_declaration": "class",
    "abstract_class_declaration": "class",
    "interface_declaration": "interface",
    "type_alias_declaration": "type",
    "enum_declaration": "enum",
    "internal_module": "namespace",
    "module": "namespace",
}
_CLASS_MEMBER_TYPES = {
    "method_definition",
    "method_signature",
    "abstract_method_signature",
}
_CLASS_FIELD_TYPES = {"public_field_definition", "field_definition"}


@dataclass(frozen=True)
class Chunk:
    file_path: str
    start_line: int  # 1-based, inclusive
    end_line: int  # 1-based, inclusive
    text: str
    kind: str
    symbol: str | None
    language: str


def language_for(path: str) -> str:
    ext = PurePosixPath(path).suffix.lower()
    if ext in {".ts", ".mts", ".cts"}:
        return "typescript"
    if ext == ".tsx":
        return "tsx"
    if ext in {".js", ".jsx", ".mjs", ".cjs"}:
        return "javascript"
    if ext in MARKDOWN_EXTENSIONS:
        return "markdown"
    return ext.lstrip(".") or "text"


def chunk_file(path: str, text: str, max_chars: int = 3000) -> list[Chunk]:
    """Chunk one file. ``path`` is the project-relative POSIX path."""
    if not text.strip():
        return []
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    ext = PurePosixPath(path).suffix.lower()
    language = language_for(path)
    if ext in JS_LIKE_EXTENSIONS:
        try:
            return _chunk_js(path, text, language, max_chars)
        except Exception:  # pragma: no cover - tree-sitter is error tolerant
            pass
    if ext in MARKDOWN_EXTENSIONS:
        return _chunk_markdown(path, text, max_chars)
    lines = text.split("\n")
    return _window_chunks(path, lines, 1, len(lines), "text", None, language, max_chars)


# ---------------------------------------------------------------------------
# Line windows
# ---------------------------------------------------------------------------


def _window_chunks(
    path: str,
    lines: list[str],
    start: int,
    end: int,
    kind: str,
    symbol: str | None,
    language: str,
    max_chars: int,
) -> list[Chunk]:
    """Emit lines[start..end] (1-based, inclusive), split into windows if too large."""
    # Trim blank lines at both ends so line ranges point at real content.
    while start <= end and not lines[start - 1].strip():
        start += 1
    while end >= start and not lines[end - 1].strip():
        end -= 1
    if start > end:
        return []

    body = "\n".join(lines[start - 1 : end])
    if len(body) <= max_chars:
        return [Chunk(path, start, end, body, kind, symbol, language)]

    chunks: list[Chunk] = []
    win_start = start
    while win_start <= end:
        size = 0
        win_end = win_start
        while win_end <= end:
            size += len(lines[win_end - 1]) + 1
            if size > max_chars and win_end > win_start:
                win_end -= 1
                break
            win_end += 1
        win_end = min(win_end, end)
        segment = "\n".join(lines[win_start - 1 : win_end])
        if len(segment) > max_chars:  # a single enormous line (e.g. minified code)
            segment = segment[:max_chars]
        part = len(chunks) + 1
        if segment.strip():
            chunks.append(Chunk(path, win_start, win_end, segment, kind, _part(symbol, part), language))
        if win_end >= end:
            break
        # Overlap a few lines for context, but only when the window is big
        # enough that the overlap does not dominate it.
        overlap = WINDOW_OVERLAP_LINES if win_end - win_start + 1 > 2 * WINDOW_OVERLAP_LINES else 0
        win_start = win_end + 1 - overlap
    return chunks


def _part(symbol: str | None, part: int) -> str:
    return f"{symbol} (part {part})" if symbol else f"part {part}"


# ---------------------------------------------------------------------------
# TypeScript / JavaScript
# ---------------------------------------------------------------------------


@lru_cache(maxsize=None)
def _parser(language: str) -> tree_sitter.Parser:
    if language == "typescript":
        lang = tree_sitter_typescript.language_typescript()
    elif language == "tsx":
        lang = tree_sitter_typescript.language_tsx()
    else:
        lang = tree_sitter_javascript.language()
    return tree_sitter.Parser(tree_sitter.Language(lang))


def _name_of(node: tree_sitter.Node) -> str | None:
    name = node.child_by_field_name("name")
    return name.text.decode("utf8", "replace") if name is not None else None


def _wraps_function(node: tree_sitter.Node) -> bool:
    """True for calls like React.memo(() => ...) or forwardRef(function X() {})."""
    if node.type != "call_expression":
        return False
    args = node.child_by_field_name("arguments")
    if args is None:
        return False
    return any(a.type in _FUNCTION_VALUE_TYPES or _wraps_function(a) for a in args.named_children)


def _member_name(member: tree_sitter.Node) -> str | None:
    """Name of a class method, or of a field holding a function (``onKey = () => {}``)."""
    if member.type in _CLASS_MEMBER_TYPES:
        return _name_of(member) or "method"
    if member.type in _CLASS_FIELD_TYPES:
        value = member.child_by_field_name("value")
        if value is not None and value.type in _FUNCTION_VALUE_TYPES:
            name = member.child_by_field_name("name") or member.child_by_field_name("property")
            return name.text.decode("utf8", "replace") if name is not None else "method"
    return None


def _describe(node: tree_sitter.Node) -> tuple[str, str | None, tree_sitter.Node] | None:
    """Return (kind, symbol, declaration node) for a declaration, else None."""
    if node.type == "export_statement":
        decl = node.child_by_field_name("declaration")
        if decl is not None:
            return _describe(decl)
        value = node.child_by_field_name("value")
        if value is not None:
            if value.type in _FUNCTION_VALUE_TYPES or _wraps_function(value):
                return "function", _name_of(value) or "default", value
            if value.type in _CLASS_VALUE_TYPES:
                return "class", _name_of(value) or "default", value
        return None

    if node.type in _DECLARATION_KINDS:
        return _DECLARATION_KINDS[node.type], _name_of(node), node

    if node.type == "ambient_declaration":  # declare module/namespace/function ...
        for child in node.named_children:
            described = _describe(child)
            if described is not None:
                return described
        return None

    if node.type in {"lexical_declaration", "variable_declaration"}:
        for declarator in node.named_children:
            if declarator.type != "variable_declarator":
                continue
            value = declarator.child_by_field_name("value")
            if value is None:
                continue
            if value.type in _FUNCTION_VALUE_TYPES or _wraps_function(value):
                return "function", _name_of(declarator), node
            if value.type in _CLASS_VALUE_TYPES:
                return "class", _name_of(declarator), value
    return None


@dataclass
class _Segment:
    start: int  # 1-based
    end: int  # 1-based
    kind: str
    symbol: str | None
    node: tree_sitter.Node | None = None


def _chunk_js(path: str, text: str, language: str, max_chars: int) -> list[Chunk]:
    tree = _parser(language).parse(text.encode("utf8"))
    lines = text.split("\n")

    segments: list[_Segment] = []
    module: _Segment | None = None
    comments: list[tree_sitter.Node] = []

    def flush_module() -> None:
        nonlocal module
        if module is not None:
            segments.append(module)
            module = None

    def add_module(start: int, end: int) -> None:
        nonlocal module
        if module is None:
            module = _Segment(start, end, "module", None)
        else:
            module.end = max(module.end, end)

    for node in tree.root_node.children:
        start, end = node.start_point.row + 1, node.end_point.row + 1
        if node.type == "comment":
            comments.append(node)
            continue

        described = _describe(node)
        # Leading comments directly above a declaration belong to it (JSDoc).
        lead_start = start
        if described is not None:
            while comments and start - (comments[-1].end_point.row + 1) <= 1:
                lead_start = comments[-1].start_point.row + 1
                start = lead_start
                comments.pop()
        for comment in comments:
            add_module(comment.start_point.row + 1, comment.end_point.row + 1)
        comments = []

        if described is None:
            add_module(start, end)
            continue

        kind, symbol, decl = described
        flush_module()
        if segments and lead_start <= segments[-1].end:
            # Shares a line with the previous declaration; merge to avoid overlap.
            segments[-1].end = max(segments[-1].end, end)
            continue
        segments.append(_Segment(lead_start, end, kind, symbol, decl))

    for comment in comments:
        add_module(comment.start_point.row + 1, comment.end_point.row + 1)
    flush_module()

    chunks: list[Chunk] = []
    for seg in segments:
        size = sum(len(line) + 1 for line in lines[seg.start - 1 : seg.end])
        if seg.kind == "class" and size > max_chars and seg.node is not None:
            chunks.extend(_split_class(path, lines, seg, language, max_chars))
        else:
            chunks.extend(
                _window_chunks(path, lines, seg.start, seg.end, seg.kind, seg.symbol, language, max_chars)
            )
    return chunks


def _split_class(
    path: str, lines: list[str], seg: _Segment, language: str, max_chars: int
) -> list[Chunk]:
    """Split an oversized class into one chunk per method; fields are grouped."""
    assert seg.node is not None
    body = seg.node.child_by_field_name("body")
    class_name = seg.symbol or "class"
    if body is None:
        return _window_chunks(path, lines, seg.start, seg.end, "class", class_name, language, max_chars)

    # Everything between methods (header, fields, closing brace) is grouped
    # into "class" chunks; each method becomes its own chunk.
    groups: list[_Segment] = []
    cursor = seg.start  # first line not yet assigned to a group
    for member in body.named_children:
        member_name = _member_name(member)
        if member_name is None:
            continue
        method_start, m_end = member.start_point.row + 1, member.end_point.row + 1
        prev = member.prev_named_sibling
        while prev is not None and prev.type == "comment" and method_start - (prev.end_point.row + 1) <= 1:
            method_start = prev.start_point.row + 1
            prev = prev.prev_named_sibling
        method_start = max(method_start, cursor)
        if method_start > cursor:
            groups.append(_Segment(cursor, method_start - 1, "class", class_name))
        groups.append(_Segment(method_start, m_end, "method", f"{class_name}.{member_name}"))
        cursor = m_end + 1
    if cursor <= seg.end:
        groups.append(_Segment(cursor, seg.end, "class", class_name))

    chunks: list[Chunk] = []
    for group in groups:
        chunks.extend(
            _window_chunks(path, lines, group.start, group.end, group.kind, group.symbol, language, max_chars)
        )
    # Drop chunks that are only a closing brace.
    return [c for c in chunks if c.text.strip() not in {"}", "};"}]


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def _chunk_markdown(path: str, text: str, max_chars: int) -> list[Chunk]:
    lines = text.split("\n")
    sections: list[tuple[int, int, str | None]] = []
    stack: list[tuple[int, str]] = []
    current_start = 1
    current_symbol: str | None = None
    fence: str | None = None

    for idx, line in enumerate(lines, start=1):
        fence_match = _FENCE_RE.match(line)
        if fence_match:
            marker = fence_match.group(1)
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        if fence is not None:
            continue
        heading = _HEADING_RE.match(line)
        if not heading:
            continue
        if idx > current_start:
            sections.append((current_start, idx - 1, current_symbol))
        level, title = len(heading.group(1)), heading.group(2)
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        current_start = idx
        current_symbol = " > ".join(t for _, t in stack)
    sections.append((current_start, len(lines), current_symbol))

    # A heading directly followed by a sub-heading has no body of its own; fold
    # it into the next section instead of emitting a one-line chunk.
    merged: list[tuple[int, int, str | None]] = []
    carry: int | None = None
    for i, (start, end, symbol) in enumerate(sections):
        if carry is not None:
            start, carry = carry, None
        has_body = any(line.strip() for line in lines[start:end])  # lines after the heading
        if symbol is not None and not has_body and i < len(sections) - 1:
            carry = start
            continue
        merged.append((start, end, symbol))
    sections = merged

    chunks: list[Chunk] = []
    for start, end, symbol in sections:
        chunks.extend(_window_chunks(path, lines, start, end, "section", symbol, "markdown", max_chars))
    return chunks
