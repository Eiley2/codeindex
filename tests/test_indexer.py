from __future__ import annotations

from pathlib import Path

import pytest

from codeindex import indexer


def test_run_with_reset_drops_index_tables_before_rebuild(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "repo"
    source.mkdir()
    (source / "app.py").write_text("print('ok')\n", encoding="utf-8")

    deleted: list[tuple[str, str]] = []

    monkeypatch.setattr(indexer.cocoindex, "init", lambda _settings: None)
    monkeypatch.setattr(indexer, "_build_flow", lambda *args, **kwargs: None)
    def _delete_index_tables(db_url: str, index_name: str) -> list[str]:
        deleted.append((db_url, index_name))
        return []

    monkeypatch.setattr(indexer.catalog, "delete_index_tables", _delete_index_tables)
    monkeypatch.setattr(indexer.catalog, "upsert_index_metadata", lambda _db, _meta: None)

    async def _fake_run_async(*, reset: bool) -> dict:
        assert reset is True
        return {"demo_index": {"rows": 1}}

    monkeypatch.setattr(indexer, "_run_async", _fake_run_async)

    stats = indexer.run(
        path=str(source),
        name="demo-index",
        included=["*.py"],
        excluded=[],
        reset=True,
        db_url="postgresql://example",
        embedding_provider="local",
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    )

    assert stats == {"demo_index": {"rows": 1}}
    assert deleted == [("postgresql://example", "demo_index")]
