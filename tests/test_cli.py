from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

import pytest
from click.testing import CliRunner

from codeindex import searcher as searcher_types
from codeindex import service as service_types
from codeindex import updater as updater_types
from codeindex.doctor import DoctorCheck
from codeindex.errors import ConfigurationError

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


def test_list_shows_chunk_count_for_managed_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.setattr(
        cli_module.service,
        "list_indexes",
        lambda: service_module.IndexListResult(
            managed=(
                service_module.ManagedIndex(
                    index_name="demo_index",
                    source_path="/tmp/demo",
                    chunks=123,
                    last_indexed_at=None,
                ),
            ),
            unmanaged=(),
        ),
    )

    result = runner.invoke(cli_module.cli, ["list"])

    assert result.exit_code == 0
    assert "123" in result.output
    assert "demo_index" in result.output


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
            embedding_provider="local",
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        ),
    )

    result = runner.invoke(cli_module.cli, ["index", str(project_dir)])

    assert result.exit_code == 0
    assert "repo_default" in result.output
    assert "local | sentence-transformers/all-MiniLM-L6-v2" in result.output


def test_index_passes_embedding_model_to_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    captured: dict[str, object] = {}

    def _index(payload: service_types.IndexInput) -> service_types.IndexOperationResult:
        captured["embedding_provider"] = payload.embedding_provider
        captured["embedding_model"] = payload.embedding_model
        return service_types.IndexOperationResult(
            stats={},
            resolved_name="repo_default",
            project_config_file=None,
            embedding_provider="openrouter",
            embedding_model="openai/text-embedding-3-small",
        )

    monkeypatch.setattr(cli_module.service, "index_codebase", _index)

    result = runner.invoke(
        cli_module.cli,
        [
            "index",
            str(project_dir),
            "--embedding-provider",
            "openrouter",
            "--embedding-model",
            "openai/text-embedding-3-small",
        ],
    )

    assert result.exit_code == 0
    assert captured["embedding_provider"] == "openrouter"
    assert captured["embedding_model"] == "openai/text-embedding-3-small"
    assert "openrouter | openai/text-embedding-3-small" in result.output


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


def test_embedding_models_lists_presets() -> None:
    runner = CliRunner()
    result = runner.invoke(cli_module.cli, ["embedding-models"])

    assert result.exit_code == 0
    assert "fast" in result.output
    assert "balanced" in result.output
    assert "supermemory.ai" in result.output


def test_setup_writes_config_with_preset(
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    cfg = tmp_path / "config.toml"

    result = runner.invoke(
        cli_module.cli,
        [
            "setup",
            "--config-path",
            str(cfg),
            "--database-url",
            "postgresql://user:pw@localhost:5432/cocoindex",
            "--preset",
            "balanced",
        ],
    )

    assert result.exit_code == 0
    data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    assert data["database_url"] == "postgresql://user:pw@localhost:5432/cocoindex"
    assert data["embedding_provider"] == "local"
    assert data["embedding_model"] == "BAAI/bge-base-en-v1.5"


def test_setup_custom_embedding_model_overrides_preset(tmp_path: Path) -> None:
    runner = CliRunner()
    cfg = tmp_path / "config.toml"

    result = runner.invoke(
        cli_module.cli,
        [
            "setup",
            "--config-path",
            str(cfg),
            "--preset",
            "fast",
            "--embedding-model",
            "intfloat/e5-large-v2",
        ],
    )

    assert result.exit_code == 0
    data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    assert data["embedding_provider"] == "local"
    assert data["embedding_model"] == "intfloat/e5-large-v2"


def test_setup_openrouter_requires_api_key(tmp_path: Path) -> None:
    runner = CliRunner()
    cfg = tmp_path / "config.toml"

    result = runner.invoke(
        cli_module.cli,
        [
            "setup",
            "--config-path",
            str(cfg),
            "--embedding-provider",
            "openrouter",
        ],
    )

    assert result.exit_code == 2
    assert "OPEN_ROUTER_API_KEY" in result.output


def test_setup_openrouter_writes_default_model_with_api_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    cfg = tmp_path / "config.toml"
    monkeypatch.setenv("OPEN_ROUTER_API_KEY", "test-key")

    result = runner.invoke(
        cli_module.cli,
        [
            "setup",
            "--config-path",
            str(cfg),
            "--embedding-provider",
            "openrouter",
        ],
    )

    assert result.exit_code == 0
    data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    assert data["embedding_provider"] == "openrouter"
    assert data["embedding_model"] == "openai/text-embedding-3-small"


def test_setup_existing_file_requires_force(tmp_path: Path) -> None:
    runner = CliRunner()
    cfg = tmp_path / "config.toml"
    cfg.write_text("embedding_model = 'sentence-transformers/all-MiniLM-L6-v2'\n", encoding="utf-8")

    result = runner.invoke(
        cli_module.cli,
        [
            "setup",
            "--config-path",
            str(cfg),
        ],
    )

    assert result.exit_code == 3
    assert "already exists" in result.output


def test_setup_interactive_overwrite_and_prompts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        "\n".join(
            [
                "database_url = 'postgresql://old:old@localhost:5432/old'",
                "embedding_provider = 'local'",
                "embedding_model = 'sentence-transformers/all-MiniLM-L6-v2'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPEN_ROUTER_API_KEY", "test-key")

    result = runner.invoke(
        cli_module.cli,
        ["setup", "--config-path", str(cfg), "--interactive"],
        input=(
            "y\n"
            "2\n"
            "2\n"
            "1\n"
            "postgresql://new:new@localhost:5432/new\n"
        ),
    )

    assert result.exit_code == 0
    data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    assert data["database_url"] == "postgresql://new:new@localhost:5432/new"
    assert data["embedding_provider"] == "openrouter"
    assert data["embedding_model"] == "openai/text-embedding-3-small"


def test_setup_interactive_preset_selection(tmp_path: Path) -> None:
    runner = CliRunner()
    cfg = tmp_path / "config.toml"

    result = runner.invoke(
        cli_module.cli,
        ["setup", "--config-path", str(cfg), "--interactive"],
        input=(
            "1\n"
            "2\n"
            "\n"
        ),
    )

    assert result.exit_code == 0
    assert "Embedding setup mode" in result.output
    assert "Embedding presets" in result.output
    data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    assert data["embedding_provider"] == "local"
    assert data["embedding_model"] == "BAAI/bge-base-en-v1.5"


def test_setup_interactive_abort_when_overwrite_declined(tmp_path: Path) -> None:
    runner = CliRunner()
    cfg = tmp_path / "config.toml"
    original = "embedding_model = 'sentence-transformers/all-MiniLM-L6-v2'\n"
    cfg.write_text(original, encoding="utf-8")

    result = runner.invoke(
        cli_module.cli,
        ["setup", "--config-path", str(cfg), "--interactive"],
        input="n\n",
    )

    assert result.exit_code == 0
    assert "aborted" in result.output.lower()
    assert cfg.read_text(encoding="utf-8") == original


def test_completion_zsh_prints_block(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    monkeypatch.setenv("CODEINDEX_DISABLE_UPDATE_CHECK", "1")

    result = runner.invoke(cli_module.cli, ["completion", "zsh"])

    assert result.exit_code == 0
    assert "codeindex zsh completion" in result.output
    assert "_CODEINDEX_COMPLETE=zsh_source codeindex" in result.output


def test_completion_zsh_install_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    monkeypatch.setenv("CODEINDEX_DISABLE_UPDATE_CHECK", "1")
    zshrc = tmp_path / ".zshrc"
    zshrc.write_text("# existing\n", encoding="utf-8")

    first = runner.invoke(
        cli_module.cli,
        ["completion", "zsh", "--install", "--zshrc", str(zshrc)],
    )
    second = runner.invoke(
        cli_module.cli,
        ["completion", "zsh", "--install", "--zshrc", str(zshrc)],
    )

    assert first.exit_code == 0
    assert second.exit_code == 0
    content = zshrc.read_text(encoding="utf-8")
    assert content.count("codeindex zsh completion") == 2
    assert "_CODEINDEX_COMPLETE=zsh_source codeindex" in content
    assert "unchanged" in second.output


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


def test_reindex_passes_embedding_model_to_service(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}

    def _reindex(payload: service_types.ReindexInput) -> service_types.IndexOperationResult:
        captured["embedding_provider"] = payload.embedding_provider
        captured["embedding_model"] = payload.embedding_model
        return service_types.IndexOperationResult(
            stats={},
            resolved_name="demo_index",
            project_config_file=None,
            embedding_provider="openrouter",
            embedding_model="openai/text-embedding-3-small",
        )

    monkeypatch.setattr(cli_module.service, "reindex_codebase", _reindex)

    result = runner.invoke(
        cli_module.cli,
        [
            "reindex",
            "demo-index",
            "--embedding-provider",
            "openrouter",
            "--embedding-model",
            "openai/text-embedding-3-small",
        ],
    )

    assert result.exit_code == 0
    assert captured["embedding_provider"] == "openrouter"
    assert captured["embedding_model"] == "openai/text-embedding-3-small"
    assert "Embeddings:" in result.output
    assert "openrouter" in result.output
    assert "openai/text-embedding-3-small" in result.output


def test_skills_set_writes_codex_and_claude_templates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    codex_home = tmp_path / ".codex"
    claude_file = tmp_path / "CLAUDE.md"

    monkeypatch.setenv("CODEINDEX_DISABLE_UPDATE_CHECK", "1")

    result = runner.invoke(
        cli_module.cli,
        [
            "skills",
            "set",
            "--codex-home",
            str(codex_home),
            "--claude-file",
            str(claude_file),
        ],
    )

    assert result.exit_code == 0
    codex_skill = codex_home / "skills" / "codeindex-local" / "SKILL.md"
    assert codex_skill.is_file()
    assert claude_file.is_file()
    assert "codeindex list" in codex_skill.read_text(encoding="utf-8")
    assert "codeindex list" in claude_file.read_text(encoding="utf-8")


def test_skills_update_overwrites_existing_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    codex_home = tmp_path / ".codex"
    claude_file = tmp_path / "CLAUDE.md"
    codex_skill = codex_home / "skills" / "codeindex-local" / "SKILL.md"
    codex_skill.parent.mkdir(parents=True, exist_ok=True)
    codex_skill.write_text("old", encoding="utf-8")
    claude_file.write_text("old", encoding="utf-8")

    monkeypatch.setenv("CODEINDEX_DISABLE_UPDATE_CHECK", "1")

    result = runner.invoke(
        cli_module.cli,
        [
            "skills",
            "update",
            "--codex-home",
            str(codex_home),
            "--claude-file",
            str(claude_file),
        ],
    )

    assert result.exit_code == 0
    assert "old" not in codex_skill.read_text(encoding="utf-8")
    assert "old" not in claude_file.read_text(encoding="utf-8")


def test_skills_rejects_conflicting_selection_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.setenv("CODEINDEX_DISABLE_UPDATE_CHECK", "1")

    result = runner.invoke(
        cli_module.cli,
        ["skills", "set", "--codex-only", "--claude-only"],
    )

    assert result.exit_code == 3
    assert "only one" in result.output.lower()
