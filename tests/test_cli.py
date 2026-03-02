from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from click.testing import CliRunner

from codeindex import service as service_types
from codeindex.doctor import DoctorCheck
from codeindex.errors import ConfigurationError, NotFoundError

cli_module = importlib.import_module("codeindex.cli")
service_module = importlib.import_module("codeindex.service")


def test_list_returns_configuration_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()

    def _raise() -> None:
        raise ConfigurationError("missing db url")

    monkeypatch.setattr(cli_module.service, "list_indexes", _raise)

    result = runner.invoke(cli_module.cli, ["list"])

    assert result.exit_code == 2
    assert "missing db url" in result.output


def test_status_returns_not_found_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()

    def _raise(_name: str | None = None) -> list[service_types.StatusItem]:
        raise NotFoundError("Index 'missing_index' not found")

    monkeypatch.setattr(cli_module.service, "status", _raise)

    result = runner.invoke(cli_module.cli, ["status", "missing_index"])

    assert result.exit_code == 4
    assert "not found" in result.output.lower()


def test_doctor_returns_exit_6_when_checks_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.setattr(
        cli_module.service,
        "run_doctor",
        lambda _path: service_module.DoctorReport(
            database_url_source="env:COCOINDEX_DATABASE_URL",
            checks=(DoctorCheck(name="pgvector_extension", ok=False, detail="missing"),),
            applied_migrations=(),
            project_config_file=None,
        ),
    )

    result = runner.invoke(cli_module.cli, ["doctor"])

    assert result.exit_code == 6
    assert "FAIL" in result.output


def test_delete_dry_run_shows_plan_and_does_not_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.setattr(
        cli_module.service,
        "preview_delete",
        lambda _name: service_module.DeletePlan(
            index_name="demo_index",
            tables=("demo_index__code_embeddings", "demo_index__cocoindex_tracking"),
            metadata_exists=True,
        ),
    )

    def _delete(_name: str, dry_run: bool = False) -> service_types.DeletePlan:
        raise AssertionError("delete_index should not be called during dry-run")

    monkeypatch.setattr(cli_module.service, "delete_index", _delete)

    result = runner.invoke(cli_module.cli, ["delete", "demo_index", "--dry-run"])

    assert result.exit_code == 0
    assert "Delete Plan" in result.output
    assert "Dry-run only" in result.output


def test_index_uses_project_defaults_when_name_is_omitted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    monkeypatch.setattr(
        cli_module.service,
        "index_codebase",
        lambda _payload: service_module.IndexOperationResult(
            stats={},
            resolved_name="repo_default",
            project_config_file=project_dir / ".codeindex.toml",
        ),
    )

    result = runner.invoke(cli_module.cli, ["index", str(project_dir)])

    assert result.exit_code == 0
    assert "repo_default" in result.output


def test_delete_confirmation_mismatch_aborts_without_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.setattr(
        cli_module.service,
        "preview_delete",
        lambda _name: service_module.DeletePlan(
            index_name="demo_index",
            tables=("demo_index__code_embeddings",),
            metadata_exists=True,
        ),
    )

    def _delete(_name: str, dry_run: bool = False) -> service_types.DeletePlan:
        raise AssertionError("delete_index should not be called when confirmation mismatches")

    monkeypatch.setattr(cli_module.service, "delete_index", _delete)

    result = runner.invoke(cli_module.cli, ["delete", "demo_index"], input="wrong_name\n")

    assert result.exit_code == 0
    assert "mismatch" in result.output.lower()


def test_delete_with_yes_executes_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr(
        cli_module.service,
        "preview_delete",
        lambda _name: service_module.DeletePlan(
            index_name="demo_index",
            tables=("demo_index__code_embeddings",),
            metadata_exists=True,
        ),
    )

    called: dict[str, object] = {"value": False}

    def _delete(name: str, dry_run: bool = False) -> service_types.DeletePlan:
        called["value"] = True
        assert name == "demo_index"
        assert dry_run is False
        return service_types.DeletePlan(
            index_name="demo_index",
            tables=("demo_index__code_embeddings",),
            metadata_exists=True,
        )

    monkeypatch.setattr(cli_module.service, "delete_index", _delete)

    result = runner.invoke(cli_module.cli, ["delete", "demo_index", "--yes"])

    assert result.exit_code == 0
    assert called["value"] is True
    assert "Deletion completed" in result.output
