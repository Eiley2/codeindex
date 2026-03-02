from __future__ import annotations

from pathlib import Path

import pytest

from codeindex import project_config, service
from codeindex.errors import NotFoundError


def test_reindex_without_metadata_and_path_raises_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service.config, "get_database_url", lambda: "postgresql://example")
    monkeypatch.setattr(service.migrations, "apply_migrations", lambda _db: [])
    monkeypatch.setattr(service.catalog, "get_index_metadata", lambda _db, _name: None)

    with pytest.raises(NotFoundError):
        service.reindex_codebase(service.ReindexInput(name="missing_index"))


def test_reindex_with_path_works_without_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "repo"
    source.mkdir()

    monkeypatch.setattr(service.config, "get_database_url", lambda: "postgresql://example")
    monkeypatch.setattr(service.migrations, "apply_migrations", lambda _db: [])
    monkeypatch.setattr(service.catalog, "get_index_metadata", lambda _db, _name: None)
    monkeypatch.setattr(
        service.project_config,
        "discover",
        lambda _path: project_config.ProjectConfig(),
    )

    captured: dict[str, object] = {}

    def _run(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"flow": {"rows": 1}}

    monkeypatch.setattr(service.indexer, "run", _run)

    result = service.reindex_codebase(
        service.ReindexInput(
            name="My-Index",
            path=source,
            include=("*.py",),
            exclude=("tests/**",),
            reset=False,
        )
    )

    assert result.resolved_name == "my_index"
    assert result.stats == {"flow": {"rows": 1}}
    assert captured["path"] == str(source)
    assert captured["name"] == "my_index"
    assert captured["included"] == ["*.py"]
    expected_excluded = [
        "node_modules/**",
        ".git/**",
        "build/**",
        "dist/**",
        ".next/**",
        "__pycache__/**",
        "*.min.js",
        "*.lock",
        "*.map",
        "tests/**",
    ]
    assert captured["excluded"] == expected_excluded
    assert captured["reset"] is False
