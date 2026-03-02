from __future__ import annotations

import importlib

import pytest
from click.testing import CliRunner

from codeindex.doctor import DoctorCheck
from codeindex.errors import ConfigurationError

cli_module = importlib.import_module("codeindex.cli")


def _raise(exc: Exception) -> None:
    raise exc


def test_list_returns_configuration_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.setattr(
        cli_module.config,
        "get_database_url",
        lambda: _raise(ConfigurationError("missing db url")),
    )

    result = runner.invoke(cli_module.cli, ["list"])

    assert result.exit_code == 2
    assert "missing db url" in result.output


def test_status_returns_not_found_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.setattr(cli_module.config, "get_database_url", lambda: "postgresql://example")
    monkeypatch.setattr(cli_module.catalog, "get_index_metadata", lambda _db, _name: None)

    result = runner.invoke(cli_module.cli, ["status", "missing_index"])

    assert result.exit_code == 4
    assert "not found" in result.output.lower()


def test_doctor_returns_exit_6_when_checks_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.setattr(
        cli_module.config,
        "resolve_database_url",
        lambda: ("postgresql://example", "env:COCOINDEX_DATABASE_URL"),
    )
    monkeypatch.setattr(
        cli_module.doctor,
        "run_checks",
        lambda _db: [DoctorCheck(name="pgvector_extension", ok=False, detail="missing")],
    )

    result = runner.invoke(cli_module.cli, ["doctor"])

    assert result.exit_code == 6
    assert "FAIL" in result.output
