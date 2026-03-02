from __future__ import annotations

from pathlib import Path

import pytest

from codeindex import config
from codeindex.errors import ConfigurationError, ValidationError


def test_normalize_index_name() -> None:
    assert config.normalize_index_name("My App-1") == "my_app_1"
    assert config.normalize_index_name("2vanguard") == "_2vanguard"


def test_table_name_for_numeric_prefix_index() -> None:
    assert config.table_name("2vanguard") == "_2vanguard__code_embeddings"


def test_normalize_index_name_invalid() -> None:
    with pytest.raises(ValidationError):
        config.normalize_index_name("___")


def test_get_database_url_prefers_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        config.DATABASE_URL_ENV_VAR,
        "postgresql://env-user:pw@localhost:5432/envdb",
    )
    conf = tmp_path / "config.toml"
    conf.write_text(
        "database_url = 'postgresql://file-user:pw@localhost:5432/filedb'\n",
        encoding="utf-8",
    )

    assert config.get_database_url(conf) == "postgresql://env-user:pw@localhost:5432/envdb"


def test_get_database_url_from_dotenv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv(config.DATABASE_URL_ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "COCOINDEX_DATABASE_URL=postgresql://dotenv-user:pw@localhost:5432/dotenvdb\n",
        encoding="utf-8",
    )

    value, source = config.resolve_database_url()

    assert value == "postgresql://dotenv-user:pw@localhost:5432/dotenvdb"
    assert source.startswith(".env:")


def test_get_database_url_from_config_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv(config.DATABASE_URL_ENV_VAR, raising=False)
    conf = tmp_path / "config.toml"
    conf.write_text(
        "[codeindex]\ndatabase_url = 'postgresql://file-user:pw@localhost:5432/filedb'\n",
        encoding="utf-8",
    )

    assert config.get_database_url(conf) == "postgresql://file-user:pw@localhost:5432/filedb"


def test_get_database_url_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv(config.DATABASE_URL_ENV_VAR, raising=False)

    with pytest.raises(ConfigurationError):
        config.get_database_url(tmp_path / "missing.toml")


def test_resolve_database_url_precedence_env_over_dotenv_and_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        config.DATABASE_URL_ENV_VAR,
        "postgresql://env-user:pw@localhost:5432/envdb",
    )

    (tmp_path / ".env").write_text(
        "COCOINDEX_DATABASE_URL=postgresql://dotenv-user:pw@localhost:5432/dotenvdb\n",
        encoding="utf-8",
    )
    conf = tmp_path / "config.toml"
    conf.write_text(
        "database_url = 'postgresql://file-user:pw@localhost:5432/filedb'\n",
        encoding="utf-8",
    )

    value, source = config.resolve_database_url(config_path=conf)

    assert value == "postgresql://env-user:pw@localhost:5432/envdb"
    assert source == f"env:{config.DATABASE_URL_ENV_VAR}"


def test_resolve_database_url_precedence_dotenv_over_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(config.DATABASE_URL_ENV_VAR, raising=False)

    (tmp_path / ".env").write_text(
        "COCOINDEX_DATABASE_URL=postgresql://dotenv-user:pw@localhost:5432/dotenvdb\n",
        encoding="utf-8",
    )
    conf = tmp_path / "config.toml"
    conf.write_text(
        "database_url = 'postgresql://file-user:pw@localhost:5432/filedb'\n",
        encoding="utf-8",
    )

    value, source = config.resolve_database_url(config_path=conf)

    assert value == "postgresql://dotenv-user:pw@localhost:5432/dotenvdb"
    assert source.startswith(".env:")
