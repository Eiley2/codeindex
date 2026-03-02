from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from click.testing import CliRunner

from codeindex import searcher as searcher_types
from codeindex import service as service_types
from codeindex import updater as updater_types
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


def test_export_calls_service_and_writes_count(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    output = tmp_path / "metadata.json"

    monkeypatch.setattr(cli_module.service, "export_metadata", lambda **_kwargs: 2)

    result = runner.invoke(cli_module.cli, ["export", str(output)])

    assert result.exit_code == 0
    assert "Exported" in result.output


def test_import_dry_run_calls_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    input_path = tmp_path / "metadata.json"
    input_path.write_text("{\"version\":1,\"items\":[]}", encoding="utf-8")

    monkeypatch.setattr(cli_module.service, "import_metadata", lambda **_kwargs: 0)

    result = runner.invoke(cli_module.cli, ["import", str(input_path), "--dry-run"])

    assert result.exit_code == 0
    assert "Validated" in result.output


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


def test_search_shows_line_range_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()

    monkeypatch.setattr(
        cli_module.service,
        "search_index",
        lambda _name, _query, top_k: [
            searcher_types.SearchResult(
                rank=1,
                score=0.91,
                filename="app/main.py",
                text="def handler():\n    return True\n",
                location={"start": {"line": 12}, "end": {"line": 14}},
                line_start=12,
                line_end=14,
            )
        ],
    )

    result = runner.invoke(cli_module.cli, ["search", "demo-index", "handler"])

    assert result.exit_code == 0
    assert "app/main.py:12-14" in result.output


def test_check_update_reports_available_update(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr(
        cli_module.updater,
        "check_for_updates",
        lambda repo: updater_types.VersionStatus(
            current_version="0.1.0",
            latest_version="0.1.1",
            update_available=True,
        ),
    )

    result = runner.invoke(cli_module.cli, ["check-update"])

    assert result.exit_code == 0
    assert "Current version" in result.output
    assert "Latest version" in result.output
    assert "Update available" in result.output


def test_update_uses_local_path_when_provided(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    called: dict[str, str] = {}

    def _run(source: str) -> None:
        called["source"] = source

    monkeypatch.setattr(cli_module.updater, "run_self_update", _run)

    result = runner.invoke(cli_module.cli, ["update", "--path", str(repo_path)])

    assert result.exit_code == 0
    assert called["source"] == str(repo_path)
    assert "Update completed" in result.output
