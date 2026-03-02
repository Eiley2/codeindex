from __future__ import annotations

import json
import logging
import re
import subprocess
import tomllib
from pathlib import Path
from typing import NoReturn

import click
from click.core import ParameterSource
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import agent_skills, config, service, updater
from .errors import ConfigurationError, DatabaseError, NotFoundError, ValidationError

console = Console()
_ZSH_COMPLETION_BLOCK_START = "# >>> codeindex zsh completion >>>"
_ZSH_COMPLETION_BLOCK_END = "# <<< codeindex zsh completion <<<"


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )


def _error_exit_code(exc: Exception) -> int:
    if isinstance(exc, ConfigurationError):
        return 2
    if isinstance(exc, ValidationError):
        return 3
    if isinstance(exc, NotFoundError):
        return 4
    if isinstance(exc, DatabaseError):
        return 5
    return 1


def _handle_error(exc: Exception, debug: bool) -> NoReturn:
    if debug:
        raise exc
    click.echo(f"Error: {exc}", err=True)
    raise click.exceptions.Exit(code=_error_exit_code(exc))


def _normalize_optional_name(name: str | None) -> str | None:
    if name is None:
        return None
    return config.normalize_index_name(name)


def _read_database_url_from_config(path: Path) -> str | None:
    return _read_config_str(path, "database_url")


def _read_config_str(path: Path, key: str) -> str | None:
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    raw = data.get(key)
    if raw is None:
        nested = data.get("codeindex", {})
        if isinstance(nested, dict):
            raw = nested.get(key)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _zsh_completion_block() -> str:
    return "\n".join(
        [
            _ZSH_COMPLETION_BLOCK_START,
            'eval "$(_CODEINDEX_COMPLETE=zsh_source codeindex)"',
            _ZSH_COMPLETION_BLOCK_END,
        ]
    )


def _upsert_managed_block(path: Path, block: str, start_marker: str, end_marker: str) -> str:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    pattern = re.compile(
        re.escape(start_marker) + r".*?" + re.escape(end_marker),
        re.DOTALL,
    )
    if pattern.search(existing):
        updated = pattern.sub(block, existing, count=1)
        if updated == existing:
            return "unchanged"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(updated if updated.endswith("\n") else updated + "\n", encoding="utf-8")
        return "updated"

    separator = "" if not existing else "\n" if existing.endswith("\n") else "\n\n"
    updated = f"{existing}{separator}{block}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated, encoding="utf-8")
    return "created" if not existing else "updated"


def _select_indexed_option(
    title: str,
    options: list[str],
    *,
    default_index: int | None = None,
) -> int:
    console.print(f"\n[bold]{title}[/bold]")
    console.print("[dim]Type the option number and press Enter.[/dim]")
    for idx, option in enumerate(options, start=1):
        console.print(f"{idx}. {option}")

    default_value = None if default_index is None else default_index + 1
    selected = click.prompt(
        "Select option number",
        type=click.IntRange(1, len(options)),
        default=default_value,
        show_default=default_value is not None,
    )
    return int(selected) - 1


def _local_model_options() -> list[str]:
    known = []
    for preset in config.EMBEDDING_MODEL_PRESETS:
        if preset.provider == "local":
            known.append(preset.model_id)
    unique = list(dict.fromkeys(known))
    return unique + ["Custom model id"]


def _openrouter_model_options() -> list[str]:
    return [
        config.DEFAULT_OPENROUTER_EMBEDDING_MODEL,
        "Custom model id",
    ]


def _select_model_for_provider(provider: str, existing_model: str | None) -> str:
    options = _openrouter_model_options() if provider == "openrouter" else _local_model_options()

    default_index = None
    if existing_model:
        for i, option in enumerate(options):
            if option == existing_model:
                default_index = i
                break

    selected_idx = _select_indexed_option(
        f"Embedding model options ({provider})",
        options,
        default_index=default_index,
    )
    selected_value = options[selected_idx]
    if selected_value == "Custom model id":
        return config.validate_embedding_model_name(
            click.prompt("Custom embedding model id")
        )
    return config.validate_embedding_model_name(selected_value)


def _select_embedding_from_presets(
    existing_provider: str | None,
    existing_model: str | None,
) -> tuple[str, str]:
    presets = list(config.EMBEDDING_MODEL_PRESETS)
    rows = [
        f"{preset.key}: {preset.provider} | {preset.model_id} | {preset.label}"
        for preset in presets
    ]
    default_index = 0
    if existing_provider and existing_model:
        for idx, preset in enumerate(presets):
            if (
                preset.provider == existing_provider
                and preset.model_id == existing_model
            ):
                default_index = idx
                break
    choice = _select_indexed_option(
        "Embedding presets",
        rows,
        default_index=default_index,
    )
    selected = presets[choice]
    return selected.provider, selected.model_id


def _select_provider(existing_provider: str | None) -> str:
    provider_options = list(config.EMBEDDING_PROVIDERS)
    default_provider = existing_provider if existing_provider in provider_options else "local"
    default_index = provider_options.index(default_provider)
    provider_idx = _select_indexed_option(
        "Embedding providers",
        provider_options,
        default_index=default_index,
    )
    return config.validate_embedding_provider(provider_options[provider_idx])


def _select_embedding_manual(
    existing_provider: str | None,
    existing_model: str | None,
) -> tuple[str, str]:
    provider = _select_provider(existing_provider)
    model = _select_model_for_provider(provider, existing_model)
    return provider, model


@click.group()
@click.option("--debug", is_flag=True, help="Show Python traceback on errors.")
@click.option("--verbose", is_flag=True, help="Enable verbose logs.")
@click.pass_context
def cli(ctx: click.Context, debug: bool, verbose: bool) -> None:
    """Semantic search over codebases using CocoIndex and pgvector."""
    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug
    ctx.obj["verbose"] = verbose
    _configure_logging(verbose)

    if ctx.invoked_subcommand is None:
        return
    if ctx.invoked_subcommand in {"update", "check-update", "completion"}:
        return
    notice = updater.update_notification()
    if notice:
        console.print(f"[yellow]{notice}[/yellow]")


@cli.command()
@click.argument(
    "path",
    type=click.Path(
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        path_type=Path,
        resolve_path=True,
    ),
)
@click.argument("name", required=False)
@click.option(
    "--include",
    "-i",
    multiple=True,
    metavar="PATTERN",
    help="File patterns to include (e.g. '*.py'). Can be repeated.",
)
@click.option(
    "--exclude",
    "-e",
    multiple=True,
    metavar="PATTERN",
    help="Additional patterns to exclude. Can be repeated.",
)
@click.option(
    "--reset",
    is_flag=True,
    default=False,
    help="Drop and rebuild the index from scratch.",
)
@click.option(
    "--max-files",
    type=click.IntRange(min=1),
    default=None,
    help="Fail if matched files exceed this limit.",
)
@click.option(
    "--max-file-bytes",
    type=click.IntRange(min=1),
    default=None,
    help="Fail if any matched file exceeds this size in bytes.",
)
@click.option(
    "--embedding-provider",
    type=click.Choice(list(config.EMBEDDING_PROVIDERS)),
    default=None,
    help="Embedding provider to use: local or openrouter.",
)
@click.option(
    "--embedding-model",
    default=None,
    help=(
        "Sentence-transformers model id for embeddings "
        "(for example: sentence-transformers/all-MiniLM-L6-v2)."
    ),
)
@click.pass_context
def index(
    ctx: click.Context,
    path: Path,
    name: str | None,
    include: tuple[str, ...],
    exclude: tuple[str, ...],
    reset: bool,
    max_files: int | None,
    max_file_bytes: int | None,
    embedding_provider: str | None,
    embedding_model: str | None,
) -> None:
    """Index a codebase at PATH under the optional NAME."""
    debug = bool(ctx.obj.get("debug")) if ctx.obj else False

    try:
        result = service.index_codebase(
            service.IndexInput(
                path=path,
                name=_normalize_optional_name(name),
                include=include,
                exclude=exclude,
                reset=reset,
                max_files=max_files,
                max_file_bytes=max_file_bytes,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
            )
        )
    except Exception as exc:
        _handle_error(exc, debug)

    info = Table.grid(padding=(0, 2))
    info.add_row("[bold]Path[/bold]", str(path))
    info.add_row("[bold]Resolved Name[/bold]", result.resolved_name)
    if result.embedding_provider and result.embedding_model:
        info.add_row(
            "[bold]Embeddings[/bold]",
            f"{result.embedding_provider} | {result.embedding_model}",
        )
    if include:
        info.add_row("[bold]Include[/bold]", ", ".join(include))
    if exclude:
        info.add_row("[bold]Extra Exclude[/bold]", ", ".join(exclude))
    if result.project_config_file is not None:
        info.add_row("[bold]Project Config[/bold]", str(result.project_config_file))

    console.print()
    console.print(Panel(info, title="[bold cyan]Indexed[/bold cyan]", border_style="cyan"))

    if result.stats:
        table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
        table.add_column("Flow", style="bold white")
        table.add_column("Stats", style="dim")
        for flow_name, flow_stats in result.stats.items():
            table.add_row(str(flow_name), str(flow_stats))
        console.print(table)


@cli.command()
@click.argument("name")
@click.argument("query")
@click.option(
    "--top-k",
    "-k",
    type=click.IntRange(min=1),
    default=config.DEFAULT_TOP_K,
    show_default=True,
    metavar="N",
    help="Number of results to return.",
)
@click.option(
    "--snippet-length",
    "-s",
    type=click.IntRange(min=1),
    default=500,
    show_default=True,
    metavar="N",
    help="Characters to show per result.",
)
@click.pass_context
def search(
    ctx: click.Context,
    name: str,
    query: str,
    top_k: int,
    snippet_length: int,
) -> None:
    """Search NAME index for QUERY."""
    debug = bool(ctx.obj.get("debug")) if ctx.obj else False
    clean_query = query.strip()
    if not clean_query:
        raise click.ClickException("Query cannot be empty.")

    try:
        clean_name = config.normalize_index_name(name)
        results = service.search_index(clean_name, clean_query, top_k=top_k)
    except Exception as exc:
        _handle_error(exc, debug)

    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    console.print()
    console.print(
        Panel(
            (
                f"[bold]{clean_query}[/bold]  [dim]·[/dim]  [cyan]{clean_name}[/cyan]  "
                f"[dim]·[/dim]  {len(results)} results"
            ),
            border_style="cyan",
        )
    )

    for result in results:
        score_color = (
            "green" if result.score >= 0.4 else "yellow" if result.score >= 0.25 else "red"
        )
        snippet = result.text[:snippet_length].strip().replace("\n", " ")
        if len(result.text) > snippet_length:
            snippet += "…"

        header = Text()
        header.append(f"#{result.rank} ", style="dim")
        header.append(f"[{result.score:.3f}] ", style=f"bold {score_color}")
        header.append(result.filename, style="bold white")
        if result.line_start is not None:
            if result.line_end is not None and result.line_end != result.line_start:
                header.append(f":{result.line_start}-{result.line_end}", style="dim")
            else:
                header.append(f":{result.line_start}", style="dim")

        console.print()
        console.print(header)
        console.print(f"  [dim]{snippet}[/dim]")

    console.print()


@cli.command(name="list")
@click.pass_context
def list_indexes(ctx: click.Context) -> None:
    """List all available indexes."""
    debug = bool(ctx.obj.get("debug")) if ctx.obj else False
    try:
        listing = service.list_indexes()
    except Exception as exc:
        _handle_error(exc, debug)

    if listing.managed:
        table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
        table.add_column("Index", style="bold white")
        table.add_column("Path", style="dim")
        table.add_column("Chunks", justify="right")
        table.add_column("Last Indexed", style="dim")
        for item in listing.managed:
            chunks = str(item.chunks) if item.chunks is not None else "missing"
            last_indexed = (
                item.last_indexed_at.isoformat(timespec="seconds")
                if item.last_indexed_at
                else "n/a"
            )
            table.add_row(item.index_name, item.source_path, chunks, last_indexed)
        console.print()
        console.print(table)
        return

    if not listing.unmanaged:
        console.print(
            "[yellow]No indexes found. Run 'codeindex index <path> [name]' first.[/yellow]"
        )
        return

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
    table.add_column("Unmanaged Index", style="bold white")
    for name in listing.unmanaged:
        table.add_row(name)
    console.print()
    console.print(table)


@cli.command()
@click.argument("name")
@click.option(
    "--path",
    type=click.Path(
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        path_type=Path,
        resolve_path=True,
    ),
    default=None,
    help="Override source path. Defaults to catalog path.",
)
@click.option(
    "--include",
    "-i",
    multiple=True,
    metavar="PATTERN",
    help="Override include patterns.",
)
@click.option(
    "--exclude",
    "-e",
    multiple=True,
    metavar="PATTERN",
    help="Additional patterns to exclude.",
)
@click.option(
    "--reset/--no-reset",
    default=None,
    help="Rebuild index from scratch. If omitted, uses project/catalog default.",
)
@click.option(
    "--max-files",
    type=click.IntRange(min=1),
    default=None,
    help="Fail if matched files exceed this limit.",
)
@click.option(
    "--max-file-bytes",
    type=click.IntRange(min=1),
    default=None,
    help="Fail if any matched file exceeds this size in bytes.",
)
@click.option(
    "--embedding-provider",
    type=click.Choice(list(config.EMBEDDING_PROVIDERS)),
    default=None,
    help="Embedding provider to use: local or openrouter.",
)
@click.option(
    "--embedding-model",
    default=None,
    help=(
        "Sentence-transformers model id for embeddings "
        "(for example: sentence-transformers/all-MiniLM-L6-v2)."
    ),
)
@click.pass_context
def reindex(
    ctx: click.Context,
    name: str,
    path: Path | None,
    include: tuple[str, ...],
    exclude: tuple[str, ...],
    reset: bool | None,
    max_files: int | None,
    max_file_bytes: int | None,
    embedding_provider: str | None,
    embedding_model: str | None,
) -> None:
    """Re-index an existing index using saved metadata or project defaults."""
    debug = bool(ctx.obj.get("debug")) if ctx.obj else False

    try:
        result = service.reindex_codebase(
            service.ReindexInput(
                name=config.normalize_index_name(name),
                path=path,
                include=include,
                exclude=exclude,
                reset=reset,
                max_files=max_files,
                max_file_bytes=max_file_bytes,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
            )
        )
    except Exception as exc:
        _handle_error(exc, debug)

    console.print("\n[bold green]Reindex completed.[/bold green]")
    if result.embedding_provider and result.embedding_model:
        console.print(
            "Embeddings: "
            f"[bold]{result.embedding_provider}[/bold] | {result.embedding_model}"
        )
    if result.project_config_file is not None:
        console.print(f"Project config: {result.project_config_file}")
    if result.stats:
        for flow_name, flow_stats in result.stats.items():
            console.print(f"- [bold]{flow_name}[/bold]: {flow_stats}")


@cli.command()
@click.argument("name")
@click.option("--yes", is_flag=True, help="Delete without confirmation prompt.")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be deleted without applying changes.",
)
@click.pass_context
def delete(ctx: click.Context, name: str, yes: bool, dry_run: bool) -> None:
    """Delete index tables and metadata with safety checks."""
    debug = bool(ctx.obj.get("debug")) if ctx.obj else False

    try:
        normalized_name = config.normalize_index_name(name)
        plan = service.preview_delete(normalized_name)
    except Exception as exc:
        _handle_error(exc, debug)

    console.print()
    console.print(f"[bold]Delete Plan for[/bold] {plan.index_name}")
    if plan.tables:
        for table_name in plan.tables:
            console.print(f"- table: {table_name}")
    else:
        console.print("- no matching tables found")
    console.print(f"- catalog metadata: {'present' if plan.metadata_exists else 'missing'}")

    if dry_run:
        console.print("\n[yellow]Dry-run only. No changes were made.[/yellow]")
        return

    if not yes:
        typed = click.prompt(
            "Type the index name to confirm deletion",
            default="",
            show_default=False,
        )
        if typed.strip() != plan.index_name:
            console.print("[yellow]Aborted. Confirmation name mismatch.[/yellow]")
            return

    try:
        service.delete_index(plan.index_name, dry_run=False)
    except Exception as exc:
        _handle_error(exc, debug)

    console.print("\n[bold green]Deletion completed.[/bold green]")


@cli.command(name="doctor")
@click.pass_context
def doctor_cmd(ctx: click.Context) -> None:
    """Run local environment diagnostics for codeindex."""
    debug = bool(ctx.obj.get("debug")) if ctx.obj else False

    try:
        report = service.run_doctor(Path.cwd())
    except Exception as exc:
        _handle_error(exc, debug)

    console.print()
    console.print(f"[bold]Database URL source:[/bold] {report.database_url_source}")
    if report.project_config_file is not None:
        console.print(f"[bold]Project config:[/bold] {report.project_config_file}")

    all_ok = True
    for check in report.checks:
        status = "[green]OK[/green]" if check.ok else "[red]FAIL[/red]"
        console.print(f"- {status} [bold]{check.name}[/bold]: {check.detail}")
        if not check.ok:
            all_ok = False

    if report.applied_migrations:
        latest_version = report.applied_migrations[-1][0]
        console.print(f"\n[bold]Applied migrations:[/bold] {len(report.applied_migrations)}")
        console.print(f"[bold]Latest migration version:[/bold] {latest_version}")

    if all_ok:
        console.print("\n[bold green]Doctor checks passed.[/bold green]")
    else:
        raise click.exceptions.Exit(code=6)


@cli.command(name="export")
@click.argument(
    "output",
    type=click.Path(
        file_okay=True,
        dir_okay=False,
        writable=True,
        path_type=Path,
        resolve_path=True,
    ),
)
@click.argument("name", required=False)
@click.pass_context
def export_metadata(ctx: click.Context, output: Path, name: str | None) -> None:
    """Export index metadata to a JSON file."""
    debug = bool(ctx.obj.get("debug")) if ctx.obj else False
    try:
        count = service.export_metadata(
            output_path=output,
            index_name=_normalize_optional_name(name),
        )
    except Exception as exc:
        _handle_error(exc, debug)

    console.print(f"[bold green]Exported[/bold green] {count} metadata entries to {output}")


@cli.command(name="import")
@click.argument(
    "input_path",
    type=click.Path(
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        path_type=Path,
        resolve_path=True,
    ),
)
@click.option("--dry-run", is_flag=True, help="Validate input without writing to DB.")
@click.pass_context
def import_metadata_cmd(ctx: click.Context, input_path: Path, dry_run: bool) -> None:
    """Import index metadata from a JSON file."""
    debug = bool(ctx.obj.get("debug")) if ctx.obj else False
    try:
        count = service.import_metadata(input_path=input_path, dry_run=dry_run)
    except Exception as exc:
        _handle_error(exc, debug)

    if dry_run:
        console.print(f"[bold green]Validated[/bold green] {count} metadata entries.")
    else:
        console.print(f"[bold green]Imported[/bold green] {count} metadata entries.")


@cli.command(name="check-update")
@click.option(
    "--repo",
    default=updater.DEFAULT_REPO,
    show_default=True,
    help="GitHub repo in OWNER/REPO format to check latest release.",
)
@click.pass_context
def check_update(ctx: click.Context, repo: str) -> None:
    """Check if a newer codeindex version is available."""
    debug = bool(ctx.obj.get("debug")) if ctx.obj else False
    try:
        status = updater.check_for_updates(repo=repo)
    except Exception as exc:
        _handle_error(exc, debug)

    console.print(f"[bold]Current version:[/bold] {status.current_version}")
    if status.latest_version is None:
        console.print(
            "[yellow]Could not determine latest release version right now.[/yellow]"
        )
        return

    console.print(f"[bold]Latest version:[/bold] {status.latest_version}")
    if status.update_available:
        console.print(
            "[yellow]Update available.[/yellow] Run "
            "[bold]codeindex update[/bold]."
        )
    else:
        console.print("[bold green]You are using the latest version.[/bold green]")


@cli.command()
@click.option(
    "--repo",
    default=updater.DEFAULT_REPO,
    show_default=True,
    help="GitHub repo in OWNER/REPO format used when --path is not provided.",
)
@click.option(
    "--path",
    type=click.Path(
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        path_type=Path,
        resolve_path=True,
    ),
    default=None,
    help="Install from a local repository path instead of GitHub.",
)
@click.pass_context
def update(ctx: click.Context, repo: str, path: Path | None) -> None:
    """Update the installed codeindex CLI."""
    debug = bool(ctx.obj.get("debug")) if ctx.obj else False
    source = str(path) if path is not None else updater.source_from_repo(repo)
    try:
        updater.run_self_update(source)
    except FileNotFoundError:
        _handle_error(
            ValidationError("`uv` is required to run updates but was not found in PATH."),
            debug,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        stdout = exc.stdout.strip() if exc.stdout else ""
        detail = stderr or stdout or str(exc)
        _handle_error(ValidationError(f"Update failed: {detail}"), debug)

    console.print(f"[bold green]Update completed.[/bold green] Source: {source}")
    console.print("Run [bold]hash -r[/bold] if your shell caches command paths.")


@cli.command(name="embedding-models")
def embedding_models() -> None:
    """List embedding model presets derived from benchmark recommendations."""
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
    table.add_column("Preset", style="bold white")
    table.add_column("Provider", style="white")
    table.add_column("Model", style="cyan")
    table.add_column("Use Case", style="white")
    table.add_column("Summary", style="dim")
    for preset in config.EMBEDDING_MODEL_PRESETS:
        table.add_row(
            preset.key,
            preset.provider,
            preset.model_id,
            preset.label,
            preset.summary,
        )
    console.print()
    console.print(table)
    console.print(f"[dim]Source:[/dim] {config.EMBEDDING_BENCHMARK_SOURCE}")


@cli.command(name="setup")
@click.option(
    "--config-path",
    type=click.Path(
        file_okay=True,
        dir_okay=False,
        path_type=Path,
        resolve_path=True,
    ),
    default=None,
    help="Target config TOML path (defaults to ~/.config/codeindex/config.toml).",
)
@click.option(
    "--database-url",
    default=None,
    help="Database URL to store in config.toml.",
)
@click.option(
    "--preset",
    type=click.Choice([preset.key for preset in config.EMBEDDING_MODEL_PRESETS]),
    default="fast",
    show_default=True,
    help="Embedding preset based on benchmark recommendations.",
)
@click.option(
    "--embedding-provider",
    type=click.Choice(list(config.EMBEDDING_PROVIDERS)),
    default=None,
    help="Embedding provider (local or openrouter).",
)
@click.option(
    "--embedding-model",
    default=None,
    help="Custom embedding model id. Overrides --preset if provided.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite an existing config file.",
)
@click.option(
    "--interactive/--no-interactive",
    default=None,
    help=(
        "Prompt for values. Defaults to interactive when running setup without "
        "provider/model/db options in a TTY."
    ),
)
@click.pass_context
def setup_cmd(
    ctx: click.Context,
    config_path: Path | None,
    database_url: str | None,
    preset: str,
    embedding_provider: str | None,
    embedding_model: str | None,
    force: bool,
    interactive: bool | None,
) -> None:
    """Create initial global config with database URL and embedding model."""
    debug = bool(ctx.obj.get("debug")) if ctx.obj else False
    try:
        target = config_path or config.default_config_path()
        existing_db = _read_database_url_from_config(target)
        existing_provider = _read_config_str(target, "embedding_provider")
        existing_model = _read_config_str(target, "embedding_model")
        preset_source = ctx.get_parameter_source("preset")
        auto_interactive = (
            database_url is None
            and embedding_provider is None
            and embedding_model is None
            and (preset_source is ParameterSource.DEFAULT)
        )
        is_tty = (
            click.get_text_stream("stdin").isatty()
            and click.get_text_stream("stdout").isatty()
        )
        use_interactive = interactive if interactive is not None else (auto_interactive and is_tty)

        if target.exists() and not force:
            if use_interactive:
                overwrite = click.confirm(
                    f"Config file '{target}' already exists. Overwrite?",
                    default=False,
                )
                if not overwrite:
                    console.print("[yellow]Setup aborted.[/yellow]")
                    return
            else:
                raise ValidationError(
                    f"Config file '{target}' already exists. Use --force to overwrite."
                )

        preset_value = config.get_embedding_model_preset(preset)
        if embedding_provider is not None:
            chosen_provider = config.validate_embedding_provider(embedding_provider)
        else:
            chosen_provider = preset_value.provider

        if embedding_model is not None:
            chosen_model = config.validate_embedding_model_name(embedding_model)
        else:
            chosen_model = preset_value.model_id

        if (
            embedding_provider is not None
            and embedding_model is None
            and chosen_provider != preset_value.provider
        ):
            chosen_model = config.default_embedding_model_for_provider(chosen_provider)

        if use_interactive and embedding_provider is None and embedding_model is None:
            mode_options = [
                "Use benchmark preset (recommended)",
                "Choose provider and model manually",
            ]
            mode_idx = _select_indexed_option(
                "Embedding setup mode",
                mode_options,
                default_index=0,
            )
            if mode_idx == 0:
                chosen_provider, chosen_model = _select_embedding_from_presets(
                    existing_provider,
                    existing_model,
                )
            else:
                chosen_provider, chosen_model = _select_embedding_manual(
                    existing_provider,
                    existing_model,
                )
        elif use_interactive and embedding_provider is not None and embedding_model is None:
            chosen_model = _select_model_for_provider(chosen_provider, existing_model)
        elif use_interactive and embedding_provider is None and embedding_model is not None:
            chosen_provider = _select_provider(existing_provider)
            chosen_model = config.validate_embedding_model_name(embedding_model)

        config.require_embedding_provider_credentials(chosen_provider)
        if database_url is not None:
            chosen_db = database_url.strip() or None
        elif use_interactive:
            chosen_db = click.prompt(
                "Database URL (leave empty to skip)",
                default=existing_db or "",
                show_default=bool(existing_db),
            ).strip()
            chosen_db = chosen_db or None
        else:
            chosen_db = existing_db

        lines = [
            "# Generated by `codeindex setup`",
            f"# Benchmark source: {config.EMBEDDING_BENCHMARK_SOURCE}",
        ]
        if chosen_db:
            lines.append(f"database_url = {json.dumps(chosen_db)}")
        lines.append(f"embedding_provider = {json.dumps(chosen_provider)}")
        lines.append(f"embedding_model = {json.dumps(chosen_model)}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")

        console.print(f"[bold green]Config written:[/bold green] {target}")
        if chosen_db:
            console.print("[bold]database_url[/bold] configured")
        else:
            console.print(
                "[yellow]database_url not set in file.[/yellow] "
                "Set COCOINDEX_DATABASE_URL env var or rerun setup with --database-url."
            )
        console.print(f"[bold]embedding_provider:[/bold] {chosen_provider}")
        console.print(f"[bold]embedding_model:[/bold] {chosen_model}")
    except Exception as exc:
        _handle_error(exc, debug)


@cli.group(name="completion")
def completion_group() -> None:
    """Shell completion helpers."""


@completion_group.command(name="zsh")
@click.option(
    "--install",
    is_flag=True,
    help="Install completion block into your zshrc file.",
)
@click.option(
    "--zshrc",
    type=click.Path(
        file_okay=True,
        dir_okay=False,
        path_type=Path,
        resolve_path=True,
    ),
    default=Path.home() / ".zshrc",
    show_default=True,
    help="Path to zsh startup file.",
)
@click.pass_context
def completion_zsh(ctx: click.Context, install: bool, zshrc: Path) -> None:
    """Print or install zsh autocomplete configuration."""
    debug = bool(ctx.obj.get("debug")) if ctx.obj else False
    try:
        block = _zsh_completion_block()
        if not install:
            click.echo(block)
            return

        status = _upsert_managed_block(
            zshrc,
            block,
            _ZSH_COMPLETION_BLOCK_START,
            _ZSH_COMPLETION_BLOCK_END,
        )
        console.print(f"[bold green]zsh completion {status}:[/bold green] {zshrc}")
        console.print(f"Reload your shell or run: [bold]source {zshrc}[/bold]")
    except Exception as exc:
        _handle_error(exc, debug)


@cli.group(name="skills")
def skills_group() -> None:
    """Install or update agent integration templates."""


def _resolve_skill_selection(codex_only: bool, claude_only: bool) -> tuple[bool, bool]:
    if codex_only and claude_only:
        raise ValidationError("Use only one of --codex-only or --claude-only.")
    install_codex = not claude_only
    install_claude = not codex_only
    return install_codex, install_claude


def _render_skill_status(label: str, path: Path, status: agent_skills.WriteStatus) -> None:
    if status == "created":
        console.print(f"[bold green]{label} created:[/bold green] {path}")
    elif status == "updated":
        console.print(f"[bold green]{label} updated:[/bold green] {path}")
    elif status == "unchanged":
        console.print(f"[cyan]{label} unchanged:[/cyan] {path}")
    else:
        console.print(
            f"[yellow]{label} exists (skipped in set mode):[/yellow] {path}"
        )


@skills_group.command(name="set")
@click.option(
    "--codex-home",
    type=click.Path(
        file_okay=False,
        dir_okay=True,
        path_type=Path,
        resolve_path=True,
    ),
    default=None,
    help="Codex home directory (defaults to $CODEX_HOME or ~/.codex).",
)
@click.option(
    "--claude-file",
    type=click.Path(
        file_okay=True,
        dir_okay=False,
        path_type=Path,
        resolve_path=True,
    ),
    default=Path("CLAUDE.md"),
    show_default=True,
    help="Path to write Claude project instructions.",
)
@click.option("--codex-only", is_flag=True, help="Only set Codex skill template.")
@click.option("--claude-only", is_flag=True, help="Only set Claude template.")
@click.pass_context
def skills_set(
    ctx: click.Context,
    codex_home: Path | None,
    claude_file: Path,
    codex_only: bool,
    claude_only: bool,
) -> None:
    """Set agent templates without overwriting existing files."""
    debug = bool(ctx.obj.get("debug")) if ctx.obj else False
    try:
        install_codex, install_claude = _resolve_skill_selection(codex_only, claude_only)
        target_codex_home = codex_home or agent_skills.default_codex_home()

        if install_codex:
            codex_path = agent_skills.codex_skill_path(target_codex_home)
            status = agent_skills.write_template(
                codex_path,
                agent_skills.CODEX_SKILL_TEMPLATE,
                mode="set",
            )
            _render_skill_status("Codex skill", codex_path, status)

        if install_claude:
            status = agent_skills.write_template(
                claude_file,
                agent_skills.CLAUDE_TEMPLATE,
                mode="set",
            )
            _render_skill_status("Claude template", claude_file, status)
    except Exception as exc:
        _handle_error(exc, debug)


@skills_group.command(name="update")
@click.option(
    "--codex-home",
    type=click.Path(
        file_okay=False,
        dir_okay=True,
        path_type=Path,
        resolve_path=True,
    ),
    default=None,
    help="Codex home directory (defaults to $CODEX_HOME or ~/.codex).",
)
@click.option(
    "--claude-file",
    type=click.Path(
        file_okay=True,
        dir_okay=False,
        path_type=Path,
        resolve_path=True,
    ),
    default=Path("CLAUDE.md"),
    show_default=True,
    help="Path to write Claude project instructions.",
)
@click.option("--codex-only", is_flag=True, help="Only update Codex skill template.")
@click.option("--claude-only", is_flag=True, help="Only update Claude template.")
@click.pass_context
def skills_update(
    ctx: click.Context,
    codex_home: Path | None,
    claude_file: Path,
    codex_only: bool,
    claude_only: bool,
) -> None:
    """Update agent templates, overwriting existing files."""
    debug = bool(ctx.obj.get("debug")) if ctx.obj else False
    try:
        install_codex, install_claude = _resolve_skill_selection(codex_only, claude_only)
        target_codex_home = codex_home or agent_skills.default_codex_home()

        if install_codex:
            codex_path = agent_skills.codex_skill_path(target_codex_home)
            status = agent_skills.write_template(
                codex_path,
                agent_skills.CODEX_SKILL_TEMPLATE,
                mode="update",
            )
            _render_skill_status("Codex skill", codex_path, status)

        if install_claude:
            status = agent_skills.write_template(
                claude_file,
                agent_skills.CLAUDE_TEMPLATE,
                mode="update",
            )
            _render_skill_status("Claude template", claude_file, status)
    except Exception as exc:
        _handle_error(exc, debug)
