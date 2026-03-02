# codeindex

Local-first CLI for indexing codebases and running semantic search with CocoIndex + PostgreSQL/pgvector.

## Setup with uv

```bash
uv sync
```

This creates/updates `.venv`, installs the project, and includes the `dev` group by default.

## Run with uv

```bash
uv run codeindex --help
uv run codeindex index /path/to/repo my_repo
uv run codeindex search my_repo "authentication middleware" --top-k 10
uv run codeindex list
```

## Install global CLI (optional)

```bash
uv tool install .
codeindex --help
```

## Developer commands

```bash
uv run ruff check .
uv run mypy codeindex tests
uv run pytest -q
```

## Configuration

`codeindex` resolves database URL in this order:

1. Environment variable `COCOINDEX_DATABASE_URL`
2. `~/.config/codeindex/config.toml`

Example config file:

```toml
database_url = "postgresql://user:password@localhost:5432/cocoindex"
```

Legacy scripts `index_codebase.py` and `search.py` are kept as compatibility wrappers and delegate to `codeindex`.
