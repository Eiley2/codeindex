from __future__ import annotations

import argparse
from pathlib import Path

from codeindex.cli import cli


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compatibility wrapper. Prefer: codeindex index <path> <name>"
    )
    parser.add_argument("path", help="Path to index")
    parser.add_argument("--name", help="Index name (default: folder name)")
    parser.add_argument("--include", nargs="+", metavar="PATTERN")
    parser.add_argument("--exclude", nargs="+", metavar="PATTERN")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    name = args.name or Path(args.path).resolve().name

    cli_args = ["index", args.path, name]
    for pattern in args.include or []:
        cli_args.extend(["--include", pattern])
    for pattern in args.exclude or []:
        cli_args.extend(["--exclude", pattern])
    if args.reset:
        cli_args.append("--reset")

    cli.main(args=cli_args, prog_name="index_codebase.py")


if __name__ == "__main__":
    main()
