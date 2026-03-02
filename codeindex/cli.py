from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import NoReturn

import click
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import config, service, updater
from .errors import ConfigurationError, DatabaseError, NotFoundError, ValidationError

console = Console()


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
    if ctx.invoked_subcommand in {"update", "check-update"}:
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
            )
        )
    except Exception as exc:
        _handle_error(exc, debug)

    info = Table.grid(padding=(0, 2))
    info.add_row("[bold]Path[/bold]", str(path))
    info.add_row("[bold]Resolved Name[/bold]", result.resolved_name)
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
        for item in listing.managed:
            table.add_row(item.index_name, item.source_path)
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
@click.argument("name", required=False)
@click.pass_context
def status(ctx: click.Context, name: str | None) -> None:
    """Show index status and metadata."""
    debug = bool(ctx.obj.get("debug")) if ctx.obj else False

    try:
        items = service.status(_normalize_optional_name(name))
    except Exception as exc:
        _handle_error(exc, debug)

    if not items:
        console.print("[yellow]No catalog metadata found yet. Index a project first.[/yellow]")
        return

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
    table.add_column("Index", style="bold white")
    table.add_column("Path", style="dim")
    table.add_column("Chunks", justify="right")
    table.add_column("Last Indexed", style="dim")

    for item in items:
        last_indexed = (
            item.last_indexed_at.isoformat(timespec="seconds")
            if item.last_indexed_at
            else "n/a"
        )
        chunks = str(item.chunks) if item.chunks is not None else "missing"
        table.add_row(item.index_name, item.source_path, chunks, last_indexed)

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
            )
        )
    except Exception as exc:
        _handle_error(exc, debug)

    console.print("\n[bold green]Reindex completed.[/bold green]")
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
