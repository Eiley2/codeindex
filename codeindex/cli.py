from __future__ import annotations

import os
import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from . import config
from . import indexer
from . import searcher

console = Console()
err_console = Console(stderr=True)


def _abort(message: str) -> None:
    err_console.print(f"[bold red]Error:[/bold red] {message}")
    sys.exit(1)


@click.group()
def cli() -> None:
    """Semantic search over codebases using CocoIndex and pgvector."""


@cli.command()
@click.argument("path")
@click.argument("name")
@click.option(
    "--include", "-i",
    multiple=True,
    metavar="PATTERN",
    help="File patterns to include (e.g. '*.py'). Can be repeated.",
)
@click.option(
    "--exclude", "-e",
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
def index(path: str, name: str, include: tuple, exclude: tuple, reset: bool) -> None:
    """Index a codebase at PATH under the given NAME.

    \b
    Examples:
      codeindex index ~/projects/my-app MyApp
      codeindex index ~/projects/my-api MyApi --include '*.py' --include '*.sql'
      codeindex index ~/projects/my-app MyApp --reset
    """
    try:
        db_url = config.get_database_url()
    except EnvironmentError as e:
        _abort(str(e))

    abs_path = os.path.abspath(path)
    if not os.path.isdir(abs_path):
        _abort(f"'{path}' is not a valid directory.")

    included = list(include) or config.DEFAULT_INCLUDED_PATTERNS
    excluded = config.DEFAULT_EXCLUDED_PATTERNS + list(exclude)

    console.print()
    info = Table.grid(padding=(0, 2))
    info.add_row("[bold]Path[/bold]", abs_path)
    info.add_row("[bold]Name[/bold]", name)
    info.add_row("[bold]Include[/bold]", ", ".join(included))
    info.add_row("[bold]Exclude[/bold]", ", ".join(excluded))
    if reset:
        info.add_row("[bold]Mode[/bold]", "[yellow]full reset[/yellow]")
    console.print(Panel(info, title="[bold cyan]Indexing[/bold cyan]", border_style="cyan"))
    console.print()

    try:
        stats = indexer.run(
            path=abs_path,
            name=name,
            included=included,
            excluded=excluded,
            reset=reset,
        )
    except ValueError as e:
        _abort(str(e))
    except Exception as e:
        _abort(f"Indexing failed: {e}")

    console.print("\n[bold green]Done.[/bold green]")


@cli.command()
@click.argument("name")
@click.argument("query")
@click.option(
    "--top-k", "-k",
    default=config.DEFAULT_TOP_K,
    show_default=True,
    metavar="N",
    help="Number of results to return.",
)
@click.option(
    "--snippet-length", "-s",
    default=250,
    show_default=True,
    metavar="N",
    help="Characters to show per result.",
)
def search(name: str, query: str, top_k: int, snippet_length: int) -> None:
    """Search NAME index for QUERY.

    \b
    Examples:
      codeindex search MyApp "authentication middleware"
      codeindex search MyApp "database connection" -k 20
      codeindex search MyApp "player contract" -k 5 --snippet-length 400
    """
    try:
        results = searcher.search(name, query, top_k=top_k)
    except EnvironmentError as e:
        _abort(str(e))
    except ValueError as e:
        _abort(str(e))
    except Exception as e:
        _abort(f"Search failed: {e}")

    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    console.print()
    console.print(
        Panel(
            f"[bold]{query}[/bold]  [dim]·[/dim]  [cyan]{name}[/cyan]  [dim]·[/dim]  {len(results)} results",
            border_style="cyan",
        )
    )

    for result in results:
        score_color = "green" if result.score >= 0.4 else "yellow" if result.score >= 0.25 else "red"
        score_text = Text(f"{result.score:.3f}", style=f"bold {score_color}")

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
def list_indexes() -> None:
    """List all available indexes."""
    try:
        db_url = config.get_database_url()
        indexes = searcher.list_indexes(db_url)
    except EnvironmentError as e:
        _abort(str(e))
    except Exception as e:
        _abort(f"Failed to list indexes: {e}")

    if not indexes:
        console.print("[yellow]No indexes found. Run 'codeindex index <path> <name>' first.[/yellow]")
        return

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
    table.add_column("Index", style="bold white")

    for name in indexes:
        table.add_row(name)

    console.print()
    console.print(table)
