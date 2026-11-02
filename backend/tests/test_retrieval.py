"""Keyword search, identifier matching, RRF and split selection (app/retrieval.py, ADR 0013)."""

from llama_index.core.schema import TextNode

from app.chunker import declared_names
from app.retrieval import (
    KeywordIndex,
    extract_identifiers,
    rrf,
    split_identifier,
    split_select,
    tokenize,
)


def node(path: str, text: str, symbol: str = "", language: str = "typescript", defines: str | None = None) -> TextNode:
    meta = {"file_path": path, "symbol": symbol, "language": language}
    if defines is not None:
        meta["defines"] = defines
    return TextNode(id_=f"{path}:{symbol}", text=text, metadata=meta)


# ── tokenize ───────────────────────────────────────────────────────────────


def test_split_identifier_handles_constant_camel_and_pascal_case():
    assert split_identifier("INVINCIBLE_MS") == ["invincible", "ms"]
    assert split_identifier("ScoreSystem") == ["score", "system"]
    assert split_identifier("useSyncExternalStore") == ["use", "sync", "external", "store"]
    assert split_identifier("HTTPServer2") == ["http", "server", "2"]


def test_tokenize_keeps_whole_identifier_plus_parts_and_drops_stopwords():
    tokens = tokenize("Where is INVINCIBLE_MS set in ScoreSystem?")
    assert "invincible_ms" in tokens and "invincible" in tokens and "ms" in tokens
    assert "scoresystem" in tokens and "score" in tokens and "system" in tokens
    assert "where" not in tokens and "is" not in tokens


def test_tokenize_ignores_cjk_and_keeps_numbers():
    # Chinese is left to vector search: it would favour Chinese docs over code.
    assert tokenize("無敵時間是 1500 毫秒") == ["1500"]
    assert tokenize("1.5 秒") == ["1.5"]


# ── identifiers in the question ────────────────────────────────────────────


def test_extract_identifiers_finds_code_names_not_plain_words():
    q = "玩家的 INVINCIBLE_MS 在哪？ScoreSystem 跟 takeDamage、Player.takeDamage 呢？HUD 和 Player 呢？"
    assert extract_identifiers(q) == ["INVINCIBLE_MS", "ScoreSystem", "takeDamage", "Player.takeDamage"]
    assert extract_identifiers("How does the player jump? Press Esc.") == []
    assert extract_identifiers("What does Game.frame do?") == ["Game.frame"]
    # Chinese written right next to the identifier (no space) must not stick to it.
    assert extract_identifiers("INVINCIBLE_MS是多久？GRAVITY在哪") == ["INVINCIBLE_MS", "GRAVITY"]
    assert tokenize("INVINCIBLE_MS是多久")[:1] == ["invincible_ms"]


# ── declared names (chunk metadata) ────────────────────────────────────────


def test_declared_names_top_level_exports_and_class_members():
    text = (
        "import { x } from './x';\n"
        "/** doc */\n"
        "export const INVINCIBLE_MS = 1500;\n"
        "const local = 1;\n"
        "export function circlesOverlap(a, b) {\n  return true;\n}\n"
        "export default class Player {\n"
        "  private hp = 3;\n"
        "  takeDamage(now: number): boolean {\n    if (x) {\n      update(1);\n    }\n  }\n"
        "  onKey = (e: KeyboardEvent) => {\n  };\n"
        "  constructor() {\n  }\n"
        "}\n"
        "export { local as renamed, x };\n"
    )
    defines, exports = declared_names(text, "typescript")
    assert defines == ["INVINCIBLE_MS", "local", "circlesOverlap", "Player", "takeDamage", "onKey"]
    assert exports == ["INVINCIBLE_MS", "circlesOverlap", "Player", "renamed", "x"]


def test_declared_names_skips_non_js_languages():
    assert declared_names("const A = 1", "markdown") == ([], [])


# ── BM25 ───────────────────────────────────────────────────────────────────


def corpus() -> list[TextNode]:
    return [
        node("src/config/gameConfig.ts", "export const INVINCIBLE_MS = 1500;\nexport const PLAYER_SPEED = 260;",
             defines="INVINCIBLE_MS,PLAYER_SPEED"),
        node("src/entities/Player.ts", "class Player {\n  takeDamage(now) {\n    this.until = now + INVINCIBLE_MS;\n  }\n}",
             symbol="Player", defines="Player,takeDamage"),
        node("src/systems/ScoreSystem.ts", "export class ScoreSystem {\n  combo = 0;\n}", symbol="ScoreSystem",
             defines="ScoreSystem"),
        node("docs/gameplay.md", "Invincibility lasts a while after a hit. The score system tracks combos.",
             symbol="Gameplay", language="markdown", defines=""),
    ]


def paths(results) -> list[str]:
    return [(n if isinstance(n, TextNode) else n[0]).metadata["file_path"] for n in results]


def test_bm25_ranks_exact_identifier_and_matches_path_and_symbol():
    index = KeywordIndex(corpus())
    assert len(index) == 4
    hits = index.search("Where is INVINCIBLE_MS configured?", 10)
    assert paths(hits)[:2] == ["src/config/gameConfig.ts", "src/entities/Player.ts"]
    assert all(score > 0 for _, score in hits)
    # "score system" (prose) reaches ScoreSystem through the split identifier and the file path.
    assert paths(index.search("score system", 10))[0] == "src/systems/ScoreSystem.ts"


def test_bm25_returns_nothing_for_unknown_or_empty_queries():
    index = KeywordIndex(corpus())
    assert index.search("無敵時間", 5) == []
    assert index.search("nonexistentword", 5) == []
    assert KeywordIndex([]).search("anything", 5) == []


def test_identifier_matches_prefer_definitions_and_are_case_sensitive():
    index = KeywordIndex(corpus())
    # Player.ts mentions INVINCIBLE_MS, but only gameConfig.ts defines it.
    assert paths(index.identifier_matches(["INVINCIBLE_MS"], 5)) == ["src/config/gameConfig.ts"]
    assert paths(index.identifier_matches(["invincible_ms"], 5)) == []
    assert paths(index.identifier_matches(["Player.takeDamage"], 5)) == ["src/entities/Player.ts"]
    assert paths(index.identifier_matches(["ScoreSystem", "INVINCIBLE_MS"], 5)) == [
        "src/config/gameConfig.ts",
        "src/systems/ScoreSystem.ts",
    ]
    assert index.identifier_matches([], 5) == []


def test_identifier_matches_method_chunks_by_symbol():
    method = node("src/game/Game.ts", "  frame(now) {\n  }", symbol="Game.frame (part 1)", defines="frame")
    index = KeywordIndex([method])
    assert len(index.identifier_matches(["Game.frame"], 5)) == 1
    assert len(index.identifier_matches(["frame"], 5)) == 1


def test_keyword_index_derives_defines_for_points_without_the_field():
    legacy = node("src/a.ts", "export const MAX_COMBO_MULTIPLIER = 4;")  # no "defines" key
    assert len(KeywordIndex([legacy]).identifier_matches(["MAX_COMBO_MULTIPLIER"], 5)) == 1


# ── RRF ────────────────────────────────────────────────────────────────────


def test_rrf_rewards_items_found_by_several_retrievers():
    fused = rrf([["a", "b", "c"], ["c", "d"], ["c"]], k=60)
    assert [item for item, _ in fused] == ["c", "a", "b", "d"]
    scores = dict(fused)
    assert abs(scores["a"] - 1 / 61) < 1e-12
    assert abs(scores["c"] - (1 / 63 + 1 / 61 + 1 / 61)) < 1e-12


def test_rrf_ties_keep_first_seen_order_and_handles_empty_lists():
    assert [i for i, _ in rrf([["a"], ["b"]], k=60)] == ["a", "b"]
    assert rrf([[], []]) == []


def test_rrf_small_k_favours_top_ranks_more():
    # Same lists: with a small k, rank 1 in one list beats rank 2 in both.
    lists = [["x", "y"], ["z", "y"]]
    assert rrf(lists, k=0)[0][0] == "x"
    assert rrf(lists, k=60)[0][0] == "y"


# ── split selection ────────────────────────────────────────────────────────


def is_doc(name: str) -> bool:
    return name.endswith(".md")


def test_split_select_caps_docs_and_puts_code_first():
    ranked = ["a.md", "b.md", "c.md", "x.ts", "y.ts", "z.ts"]
    assert split_select(ranked, 4, 1, is_doc) == ["x.ts", "y.ts", "z.ts", "a.md"]
    assert split_select(ranked, 4, 2, is_doc) == ["x.ts", "y.ts", "a.md", "b.md"]


def test_split_select_backfills_when_a_type_runs_short():
    assert split_select(["a.md", "b.md", "c.md", "x.ts"], 4, 1, is_doc) == ["x.ts", "a.md", "b.md", "c.md"]
    assert split_select(["x.ts", "y.ts", "z.ts", "w.ts", "v.ts"], 4, 2, is_doc) == ["x.ts", "y.ts", "z.ts", "w.ts"]


def test_split_select_edge_cases():
    # top_k=1 has no room for a doc unless there is no code at all.
    assert split_select(["a.md", "x.ts"], 1, 1, is_doc) == ["x.ts"]
    assert split_select(["a.md"], 1, 1, is_doc) == ["a.md"]
    assert split_select(["a.md", "x.ts"], 0, 1, is_doc) == []
    assert split_select(["a.md", "x.ts"], 3, 0, is_doc) == ["x.ts", "a.md"]
