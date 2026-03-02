from __future__ import annotations

import json
from pathlib import Path

import pytest

from codeindex import catalog, project_config, service
from codeindex.errors import NotFoundError, ValidationError


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


def test_index_propagates_project_limits_to_indexer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "repo"
    source.mkdir()

    monkeypatch.setattr(service.config, "get_database_url", lambda: "postgresql://example")
    monkeypatch.setattr(service.migrations, "apply_migrations", lambda _db: [])
    monkeypatch.setattr(
        service.project_config,
        "discover",
        lambda _path: project_config.ProjectConfig(max_files=123, max_file_bytes=4567),
    )

    captured: dict[str, object] = {}

    def _run(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"flow": {"rows": 1}}

    monkeypatch.setattr(service.indexer, "run", _run)

    service.index_codebase(service.IndexInput(path=source))

    assert captured["max_files"] == 123
    assert captured["max_file_bytes"] == 4567


def test_import_metadata_dry_run_validates_payload(tmp_path: Path) -> None:
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "version": 1,
                "items": [
                    {
                        "index_name": "demo_index",
                        "source_path": "/tmp/demo",
                        "include_patterns": ["*.py"],
                        "exclude_patterns": [".git/**"],
                        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
                        "chunk_size": 1000,
                        "chunk_overlap": 300,
                        "min_chunk_size": 300,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    count = service.import_metadata(metadata_path, dry_run=True)
    assert count == 1


def test_import_metadata_invalid_payload_raises(tmp_path: Path) -> None:
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps({"version": 1}), encoding="utf-8")

    with pytest.raises(ValidationError):
        service.import_metadata(metadata_path, dry_run=True)


def test_export_metadata_writes_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "out.json"
    monkeypatch.setattr(service.config, "get_database_url", lambda: "postgresql://example")
    monkeypatch.setattr(service.migrations, "apply_migrations", lambda _db: [])
    monkeypatch.setattr(
        service.catalog,
        "list_index_metadata",
        lambda _db: [
            catalog.IndexMetadata(
                index_name="demo_index",
                source_path="/tmp/demo",
                include_patterns=("*.py",),
                exclude_patterns=(".git/**",),
                embedding_model="sentence-transformers/all-MiniLM-L6-v2",
                chunk_size=1000,
                chunk_overlap=300,
                min_chunk_size=300,
            )
        ],
    )

    count = service.export_metadata(output)
    assert count == 1

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["items"][0]["index_name"] == "demo_index"
