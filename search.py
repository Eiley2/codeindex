from __future__ import annotations

import argparse

from codeindex.cli import cli


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compatibility wrapper. Prefer: codeindex search <name> <query>"
    )
    parser.add_argument("index", nargs="?", help="Index name")
    parser.add_argument("query", nargs="*", help="Search query")
    parser.add_argument("-k", "--top-k", type=int, default=10)
    parser.add_argument("--list", action="store_true", help="List available indexes")
    args = parser.parse_args()

    if args.list or not args.index:
        cli.main(args=["list"], prog_name="search.py")
        return

    if not args.query:
        parser.error("You must provide a query.")

    cli.main(
        args=["search", args.index, " ".join(args.query), "--top-k", str(args.top_k)],
        prog_name="search.py",
    )


if __name__ == "__main__":
    main()
