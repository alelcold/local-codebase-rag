from pathlib import Path

import pytest

from app.config import Settings
from app.indexer import scan_files

from .conftest import FailingEmbedding, make_services


def _payloads(services):
    points, _ = services.store.client.scroll(services.store.collection, limit=1000, with_payload=True)
    return [p.payload for p in points]


def test_scan_respects_extensions_excluded_dirs_and_patterns(settings, codebase):
    files, skipped = scan_files(codebase, settings)
    assert sorted(files) == ["docs/guide.md", "src/hud.tsx", "src/player.ts", "src/util.js"]
    assert skipped == []


def test_scan_skips_large_files(codebase):
    (codebase / "src/huge.ts").write_text("x" * 2000)
    settings = Settings(codebase_path=str(codebase), max_file_bytes=1000)
    files, skipped = scan_files(codebase, settings)
    assert "src/huge.ts" not in files
    assert skipped == ["src/huge.ts"]


def test_first_run_indexes_all_files_with_line_metadata(services):
    report = services.indexer.run()
    assert report.scanned == 4
    assert sorted(report.added) == ["docs/guide.md", "src/hud.tsx", "src/player.ts", "src/util.js"]
    assert report.errors == {}
    assert report.chunks_written == services.store.count() > 0

    payloads = _payloads(services)
    clamp = next(p for p in payloads if p["symbol"] == "clamp")
    assert clamp["file_path"] == "src/util.js"
    assert (clamp["start_line"], clamp["end_line"]) == (1, 3)
    assert clamp["language"] == "javascript"


def test_second_run_skips_unchanged_files(services):
    services.indexer.run()
    calls_before = services.embed_model.calls
    report = services.indexer.run()
    assert report.unchanged == 4
    assert report.added == report.updated == report.deleted == []
    assert report.chunks_written == 0
    assert services.embed_model.calls == calls_before  # nothing re-embedded


def test_changed_added_and_deleted_files_are_synced(services, codebase: Path):
    services.indexer.run()
    count_before = services.store.count()

    (codebase / "src/util.js").write_text("export function clamp01(v) {\n  return clamp(v, 0, 1);\n}\n")
    (codebase / "src/enemy.ts").write_text("export class Enemy {\n  hp = 3;\n}\n")
    (codebase / "src/hud.tsx").unlink()

    report = services.indexer.run()
    assert report.updated == ["src/util.js"]
    assert report.added == ["src/enemy.ts"]
    assert report.deleted == ["src/hud.tsx"]
    assert report.unchanged == 2

    payloads = _payloads(services)
    files = {p["file_path"] for p in payloads}
    assert "src/hud.tsx" not in files
    util_symbols = {p["symbol"] for p in payloads if p["file_path"] == "src/util.js"}
    assert util_symbols == {"clamp01"}  # old chunks removed, not duplicated
    assert services.store.count() != count_before


def test_full_reindex_rebuilds_everything(services):
    services.indexer.run()
    count = services.store.count()
    report = services.indexer.run(full=True)
    assert report.full is True
    assert len(report.added) == 4
    assert services.store.count() == count


def test_chunk_setting_change_triggers_reindex(services, settings):
    services.indexer.run()
    settings.chunk_max_chars = 800
    report = services.indexer.run()
    assert len(report.updated) == 4


def test_embedding_failure_keeps_old_version_and_reports_error(settings, codebase):
    embed = FailingEmbedding()
    services = make_services(settings, embed=embed)
    services.indexer.run()
    old = {p["symbol"] for p in _payloads(services) if p["file_path"] == "src/util.js"}

    (codebase / "src/util.js").write_text("export function brokenEmbed() {}\n")
    embed.fail_on = "brokenEmbed"
    report = services.indexer.run()
    assert "src/util.js" in report.errors
    assert "ollama unavailable" in report.errors["src/util.js"]
    still = {p["symbol"] for p in _payloads(services) if p["file_path"] == "src/util.js"}
    assert still == old

    embed.fail_on = ""
    report = services.indexer.run()
    assert report.updated == ["src/util.js"]


def test_embedded_text_uses_document_prefix_and_location_header(settings):
    from app.chunker import Chunk
    from app.indexer import embed_text

    chunk = Chunk("src/a.ts", 3, 9, "function a() {}", "function", "a", "typescript")
    text = embed_text(chunk, settings)
    assert text.startswith("search_document: File: src/a.ts\nSymbol: a (function)")
    assert text.endswith("function a() {}")


def test_missing_codebase_path_raises(tmp_path):
    services = make_services(Settings(codebase_path=str(tmp_path / "nope")))
    with pytest.raises(FileNotFoundError):
        services.indexer.run()


def test_store_created_before_collection_sees_collection_made_elsewhere(settings):
    """The API process builds its store before the CLI indexer (another process)
    creates the collection; queries must still work afterwards."""
    from app.store import CodeVectorStore

    services = make_services(settings)
    api_store = CodeVectorStore(services.store.client, services.store.collection)
    assert not api_store.exists()

    services.indexer.run()  # "CLI" creates the collection through its own store
    embedding = services.embed_model.get_query_embedding("player jump")
    assert len(api_store.query(embedding, 3)) == 3

    # ...and again after the other process drops and recreates it.
    services.indexer.run(full=True)
    assert len(api_store.query(embedding, 3)) == 3
