from __future__ import annotations

from pathlib import Path

import pytest

from codeindex import project_config
from codeindex.errors import ConfigurationError


def test_discover_project_config(tmp_path: Path) -> None:
    project = tmp_path / "app"
    nested = project / "src" / "pkg"
    nested.mkdir(parents=True)

    (project / ".codeindex.toml").write_text(
        """
[index]
name = "My App"
embedding_provider = "openrouter"
embedding_model = "BAAI/bge-base-en-v1.5"
include_patterns = ["*.py", "*.md"]
exclude_patterns = [".git/**", "dist/**"]
reset = true

[chunking]
chunk_size = 1500
chunk_overlap = 250
min_chunk_size = 200
""".strip(),
        encoding="utf-8",
    )

    cfg = project_config.discover(nested)

    assert cfg.source_file == project / ".codeindex.toml"
    assert cfg.index_name == "my_app"
    assert cfg.embedding_provider == "openrouter"
    assert cfg.embedding_model == "BAAI/bge-base-en-v1.5"
    assert cfg.include_patterns == ("*.py", "*.md")
    assert cfg.exclude_patterns == (".git/**", "dist/**")
    assert cfg.default_reset is True
    assert cfg.chunk_size == 1500
    assert cfg.chunk_overlap == 250
    assert cfg.min_chunk_size == 200


def test_discover_without_file_returns_defaults(tmp_path: Path) -> None:
    cfg = project_config.discover(tmp_path)

    assert cfg.source_file is None
    assert cfg.index_name is None
    assert cfg.include_patterns is None


def test_invalid_types_raise(tmp_path: Path) -> None:
    project = tmp_path / "app"
    project.mkdir()
    (project / ".codeindex.toml").write_text(
        "[index]\ninclude_patterns = 'not-a-list'\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError):
        project_config.discover(project)


def test_invalid_embedding_model_type_raises(tmp_path: Path) -> None:
    project = tmp_path / "app"
    project.mkdir()
    (project / ".codeindex.toml").write_text(
        "[index]\nembedding_model = 123\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError):
        project_config.discover(project)


def test_invalid_embedding_provider_type_raises(tmp_path: Path) -> None:
    project = tmp_path / "app"
    project.mkdir()
    (project / ".codeindex.toml").write_text(
        "[index]\nembedding_provider = 123\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError):
        project_config.discover(project)
