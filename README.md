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
uv run codeindex status
uv run codeindex reindex my_repo
uv run codeindex doctor
uv run codeindex delete my_repo --yes
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
2. `.env` file in current/parent directories
3. `~/.config/codeindex/config.toml`

Example `.env`:

```dotenv
COCOINDEX_DATABASE_URL=postgresql://user:password@localhost:5432/cocoindex
```

You can copy from `.env.example`.

Example config file:

```toml
database_url = "postgresql://user:password@localhost:5432/cocoindex"
```

## Exit codes

- `1` unexpected/internal error
- `2` configuration error
- `3` validation error
- `4` resource not found
- `5` database error
- `6` doctor checks failed
