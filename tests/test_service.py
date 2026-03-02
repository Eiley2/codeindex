from __future__ import annotations

import json
from pathlib import Path

import pytest

from codeindex import catalog, config, project_config, service
from codeindex.errors import NotFoundError, ValidationError
from codeindex.searcher import SearchResult


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
    expected_excluded = list(config.DEFAULT_EXCLUDED_PATTERNS) + ["tests/**"]
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
                embedding_provider="local",
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


def test_search_uses_catalog_path_to_attach_line_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service.config, "get_database_url", lambda: "postgresql://example")
    monkeypatch.setattr(service.migrations, "apply_migrations", lambda _db: [])

    captured: dict[str, object] = {}

    def _search(
        name: str,
        query: str,
        top_k: int,
        db_url: str | None = None,
        embedding_provider: str | None = None,
        embedding_model: str | None = None,
    ) -> list[SearchResult]:
        captured["name"] = name
        captured["query"] = query
        captured["top_k"] = top_k
        captured["db_url"] = db_url
        captured["embedding_provider"] = embedding_provider
        captured["embedding_model"] = embedding_model
        return [
            SearchResult(
                rank=1,
                score=0.8,
                filename="pkg/mod.py",
                text="hello",
                offset_start=5,
                offset_end=10,
            )
        ]

    monkeypatch.setattr(service.searcher, "search", _search)
    monkeypatch.setattr(
        service.catalog,
        "get_index_metadata",
        lambda _db, _name: catalog.IndexMetadata(
            index_name="demo_index",
            source_path="/tmp/demo",
            include_patterns=("*.py",),
            exclude_patterns=(".git/**",),
            embedding_provider="local",
            embedding_model=config.DEFAULT_EMBEDDING_MODEL,
            chunk_size=config.CHUNK_SIZE,
            chunk_overlap=config.CHUNK_OVERLAP,
            min_chunk_size=config.MIN_CHUNK_SIZE,
        ),
    )

    attach_calls: list[tuple[list[SearchResult], Path]] = []

    def _attach(results: list[SearchResult], source_root: Path) -> None:
        attach_calls.append((results, source_root))

    monkeypatch.setattr(service.searcher, "attach_line_numbers", _attach)

    results = service.search_index("Demo-Index", "hello", top_k=3)

    assert len(results) == 1
    assert captured["name"] == "demo_index"
    assert captured["query"] == "hello"
    assert captured["top_k"] == 3
    assert captured["db_url"] == "postgresql://example"
    assert captured["embedding_provider"] == "local"
    assert captured["embedding_model"] == config.DEFAULT_EMBEDDING_MODEL
    assert len(attach_calls) == 1
    assert attach_calls[0][1] == Path("/tmp/demo")


def test_index_prefers_cli_embedding_model_over_project_and_default(
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
        lambda _path: project_config.ProjectConfig(
            embedding_model="sentence-transformers/project-model"
        ),
    )
    monkeypatch.setattr(
        service.config,
        "get_default_embedding_model",
        lambda: "sentence-transformers/default-model",
    )

    captured: dict[str, object] = {}

    def _run(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"flow": {"rows": 1}}

    monkeypatch.setattr(service.indexer, "run", _run)

    service.index_codebase(
        service.IndexInput(path=source, embedding_model="sentence-transformers/cli-model")
    )

    assert captured["embedding_model"] == "sentence-transformers/cli-model"


def test_reindex_uses_metadata_embedding_model_when_no_overrides(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "repo"
    source.mkdir()

    monkeypatch.setattr(service.config, "get_database_url", lambda: "postgresql://example")
    monkeypatch.setattr(service.migrations, "apply_migrations", lambda _db: [])
    monkeypatch.setattr(
        service.catalog,
        "get_index_metadata",
        lambda _db, _name: catalog.IndexMetadata(
            index_name="demo_index",
            source_path=str(source),
            include_patterns=("*.py",),
            exclude_patterns=(".git/**",),
            embedding_provider="local",
            embedding_model="sentence-transformers/metadata-model",
            chunk_size=config.CHUNK_SIZE,
            chunk_overlap=config.CHUNK_OVERLAP,
            min_chunk_size=config.MIN_CHUNK_SIZE,
        ),
    )
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

    service.reindex_codebase(service.ReindexInput(name="demo_index"))

    assert captured["embedding_provider"] == "local"
    assert captured["embedding_model"] == "sentence-transformers/metadata-model"


def test_search_uses_default_embedding_model_when_metadata_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service.config, "get_database_url", lambda: "postgresql://example")
    monkeypatch.setattr(service.migrations, "apply_migrations", lambda _db: [])
    monkeypatch.setattr(service.catalog, "get_index_metadata", lambda _db, _name: None)
    monkeypatch.setattr(
        service.config,
        "get_default_embedding_provider",
        lambda: "local",
    )
    monkeypatch.setattr(
        service.config,
        "resolve_embedding_model",
        lambda explicit_model=None, config_path=None, provider=None: (
            "sentence-transformers/default-model",
            "default:local",
        ),
    )

    captured: dict[str, object] = {}

    def _search(
        name: str,
        query: str,
        top_k: int,
        db_url: str | None = None,
        embedding_provider: str | None = None,
        embedding_model: str | None = None,
    ) -> list[SearchResult]:
        captured["name"] = name
        captured["embedding_provider"] = embedding_provider
        captured["embedding_model"] = embedding_model
        return []

    monkeypatch.setattr(service.searcher, "search", _search)

    service.search_index("demo-index", "hello", top_k=3)

    assert captured["name"] == "demo_index"
    assert captured["embedding_provider"] == "local"
    assert captured["embedding_model"] == "sentence-transformers/default-model"
