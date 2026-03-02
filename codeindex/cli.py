from __future__ import annotations

from pathlib import Path

import click
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import config, indexer, searcher
from .errors import CodeIndexError

console = Console()


def _handle_error(exc: Exception, debug: bool) -> None:
    if debug:
        raise exc
    raise click.ClickException(str(exc))


def _validate_index_name(
    _ctx: click.Context, _param: click.Parameter, value: str
) -> str:
    try:
        return config.normalize_index_name(value)
    except CodeIndexError as exc:
        raise click.BadParameter(str(exc)) from exc


@click.group()
@click.option("--debug", is_flag=True, help="Show Python traceback on errors.")
@click.pass_context
def cli(ctx: click.Context, debug: bool) -> None:
    """Semantic search over codebases using CocoIndex and pgvector."""
    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug


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
    """Index a codebase at PATH under the given NAME.

    \b
    Examples:
      codeindex index ~/projects/my-app MyApp
      codeindex index ~/projects/my-api MyApi --include '*.py' --include '*.sql'
      codeindex index ~/projects/my-app MyApp --reset
    """
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
        stats = indexer.run(
            path=str(path),
            name=name,
            included=included,
            excluded=excluded,
            reset=reset,
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
    ctx: click.Context, name: str, query: str, top_k: int, snippet_length: int
) -> None:
    """Search NAME index for QUERY.

    \b
    Examples:
      codeindex search MyApp "authentication middleware"
      codeindex search MyApp "database connection" -k 20
      codeindex search MyApp "player contract" -k 5 --snippet-length 400
    """
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
