from __future__ import annotations

import logging
from pathlib import Path
from typing import NoReturn

import click
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import catalog, config, doctor, indexer, searcher
from .errors import (
    CodeIndexError,
    ConfigurationError,
    DatabaseError,
    NotFoundError,
    ValidationError,
)

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


def _validate_index_name(
    _ctx: click.Context, _param: click.Parameter, value: str
) -> str:
    try:
        return config.normalize_index_name(value)
    except CodeIndexError as exc:
        raise click.BadParameter(str(exc)) from exc


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
@click.argument("name", callback=_validate_index_name)
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
@click.pass_context
def index(
    ctx: click.Context,
    path: Path,
    name: str,
    include: tuple[str, ...],
    exclude: tuple[str, ...],
    reset: bool,
) -> None:
    """Index a codebase at PATH under the given NAME."""
    debug = bool(ctx.obj.get("debug")) if ctx.obj else False

    included = list(include) or list(config.DEFAULT_INCLUDED_PATTERNS)
    excluded = list(config.DEFAULT_EXCLUDED_PATTERNS) + list(exclude)

    console.print()
    info = Table.grid(padding=(0, 2))
    info.add_row("[bold]Path[/bold]", str(path))
    info.add_row("[bold]Name[/bold]", name)
    info.add_row("[bold]Include[/bold]", ", ".join(included))
    info.add_row("[bold]Exclude[/bold]", ", ".join(excluded))
    if reset:
        info.add_row("[bold]Mode[/bold]", "[yellow]full reset[/yellow]")
    console.print(
        Panel(info, title="[bold cyan]Indexing[/bold cyan]", border_style="cyan")
    )
    console.print()

    try:
        db_url = config.get_database_url()
        stats = indexer.run(
            path=str(path),
            name=name,
            included=included,
            excluded=excluded,
            reset=reset,
            db_url=db_url,
        )
    except Exception as exc:
        _handle_error(exc, debug)

    console.print("\n[bold green]Done.[/bold green]")
    if stats:
        table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
        table.add_column("Flow", style="bold white")
        table.add_column("Stats", style="dim")
        for flow_name, flow_stats in stats.items():
            table.add_row(flow_name, str(flow_stats))
        console.print(table)


@cli.command()
@click.argument("name", callback=_validate_index_name)
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
    default=250,
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
        results = searcher.search(name, clean_query, top_k=top_k)
    except Exception as exc:
        _handle_error(exc, debug)

    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    console.print()
    console.print(
        Panel(
            (
                f"[bold]{query}[/bold]  [dim]·[/dim]  [cyan]{name}[/cyan]  "
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
        db_url = config.get_database_url()
        indexed = catalog.list_index_metadata(db_url)
        if indexed:
            table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
            table.add_column("Index", style="bold white")
            table.add_column("Path", style="dim")
            for item in indexed:
                table.add_row(item.index_name, item.source_path)
            console.print()
            console.print(table)
            return

        indexes = searcher.list_indexes(db_url)
    except Exception as exc:
        _handle_error(exc, debug)

    if not indexes:
        console.print(
            "[yellow]No indexes found. Run 'codeindex index <path> <name>' first.[/yellow]"
        )
        return

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
    table.add_column("Index", style="bold white")
    for name in indexes:
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
        db_url = config.get_database_url()
        if name:
            normalized_name = config.normalize_index_name(name)
            one = catalog.get_index_metadata(db_url, normalized_name)
            if one is None:
                raise NotFoundError(f"Index '{normalized_name}' not found in catalog.")
            items = [one]
        else:
            items = catalog.list_index_metadata(db_url)
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
        try:
            chunks = str(catalog.index_document_count(db_url, item.index_name))
        except NotFoundError:
            chunks = "missing"
        last_indexed = (
            item.last_indexed_at.isoformat(timespec="seconds")
            if item.last_indexed_at
            else "n/a"
        )
        table.add_row(item.index_name, item.source_path, chunks, last_indexed)

    console.print()
    console.print(table)


@cli.command()
@click.argument("name", callback=_validate_index_name)
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
    help="Override include patterns. Defaults to catalog patterns.",
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
    default=True,
    show_default=True,
    help="Rebuild index from scratch.",
)
@click.pass_context
def reindex(
    ctx: click.Context,
    name: str,
    path: Path | None,
    include: tuple[str, ...],
    exclude: tuple[str, ...],
    reset: bool,
) -> None:
    """Re-index an existing index using saved metadata."""
    debug = bool(ctx.obj.get("debug")) if ctx.obj else False

    try:
        db_url = config.get_database_url()
        metadata = catalog.get_index_metadata(db_url, name)

        if path is None and metadata is None:
            raise NotFoundError(
                f"Index '{name}' has no catalog metadata. Provide --path to proceed."
            )

        if path is not None:
            source_path = str(path)
        else:
            if metadata is None:
                raise NotFoundError(
                    f"Index '{name}' has no catalog metadata. Provide --path to proceed."
                )
            source_path = metadata.source_path
        base_included = (
            list(metadata.include_patterns)
            if metadata is not None
            else list(config.DEFAULT_INCLUDED_PATTERNS)
        )
        base_excluded = (
            list(metadata.exclude_patterns)
            if metadata is not None
            else list(config.DEFAULT_EXCLUDED_PATTERNS)
        )
        included = list(include) if include else base_included
        excluded = base_excluded + list(exclude)

        stats = indexer.run(
            path=source_path,
            name=name,
            included=included,
            excluded=excluded,
            reset=reset,
            db_url=db_url,
        )
    except Exception as exc:
        _handle_error(exc, debug)

    console.print("\n[bold green]Reindex completed.[/bold green]")
    if stats:
        for flow_name, flow_stats in stats.items():
            console.print(f"- [bold]{flow_name}[/bold]: {flow_stats}")


@cli.command()
@click.argument("name", callback=_validate_index_name)
@click.option("--yes", is_flag=True, help="Delete without confirmation prompt.")
@click.pass_context
def delete(ctx: click.Context, name: str, yes: bool) -> None:
    """Delete index tables and metadata."""
    debug = bool(ctx.obj.get("debug")) if ctx.obj else False

    if not yes:
        confirmed = click.confirm(
            f"Delete index '{name}' tables and metadata?", default=False
        )
        if not confirmed:
            console.print("[yellow]Aborted.[/yellow]")
            return

    try:
        db_url = config.get_database_url()
        dropped_tables = catalog.delete_index_tables(db_url, name)
        metadata_deleted = catalog.delete_index_metadata(db_url, name)

        if not dropped_tables and not metadata_deleted:
            raise NotFoundError(f"Index '{name}' not found.")
    except Exception as exc:
        _handle_error(exc, debug)

    console.print()
    console.print(f"[bold green]Deleted index:[/bold green] {name}")
    if dropped_tables:
        for table_name in dropped_tables:
            console.print(f"- {table_name}")


@cli.command()
@click.pass_context
def doctor_cmd(ctx: click.Context) -> None:
    """Run local environment diagnostics for codeindex."""
    debug = bool(ctx.obj.get("debug")) if ctx.obj else False

    try:
        db_url, source = config.resolve_database_url()
        checks = doctor.run_checks(db_url)
    except Exception as exc:
        _handle_error(exc, debug)

    console.print()
    console.print(f"[bold]Database URL source:[/bold] {source}")

    all_ok = True
    for check in checks:
        status = "[green]OK[/green]" if check.ok else "[red]FAIL[/red]"
        console.print(f"- {status} [bold]{check.name}[/bold]: {check.detail}")
        if not check.ok:
            all_ok = False

    if all_ok:
        console.print("\n[bold green]Doctor checks passed.[/bold green]")
    else:
        raise click.exceptions.Exit(code=6)


cli.add_command(doctor_cmd, name="doctor")
