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
uv run codeindex delete my_repo --dry-run
uv run codeindex export metadata.json
uv run codeindex import metadata.json --dry-run
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

## Per-Project Defaults

`codeindex` auto-discovers `.codeindex.toml` from the current path upward.

Use `.codeindex.toml.example` as a template:

```bash
cp .codeindex.toml.example /path/to/repo/.codeindex.toml
```

Supported keys:

- `[index].name`
- `[index].include_patterns`
- `[index].exclude_patterns`
- `[index].reset`
- `[index].max_files`
- `[index].max_file_bytes`
- `[chunking].chunk_size`
- `[chunking].chunk_overlap`
- `[chunking].min_chunk_size`

`index` and `reindex` commands use these defaults when matching CLI flags are not provided.

## Database Migrations

Migrations are applied automatically before operations that require schema setup.
Migration history is stored in `codeindex_schema_migrations`.

Run diagnostics to confirm migration state:

```bash
uv run codeindex doctor
```

## Safe Delete

`delete` now supports planning before destructive actions:

```bash
uv run codeindex delete my_repo --dry-run
```

Without `--yes`, the command requires typing the exact index name.

## Metadata Backup

Export and import index metadata:

```bash
uv run codeindex export metadata.json
uv run codeindex export metadata.json my_repo
uv run codeindex import metadata.json --dry-run
uv run codeindex import metadata.json
```

`import --dry-run` validates payload without writing to DB.

## Observability

Use `--verbose` to emit service operation logs with elapsed time.

```bash
uv run codeindex --verbose index /path/to/repo
```

## Tests

Standard suite:

```bash
uv run pytest -q
```

E2E (real CocoIndex index + search):

```bash
export COCOINDEX_TEST_DATABASE_URL='postgresql://postgres:postgres@localhost:5432/cocoindex_test'
export COCOINDEX_RUN_E2E=1
uv run pytest -q -m e2e
```

## Release Hygiene

- Changelog source of truth: `CHANGELOG.md`
- Tag-based release workflow: `.github/workflows/release.yml`

Create a release by pushing a semantic tag:

```bash
git tag v0.1.1
git push origin v0.1.1
```

## Exit codes

- `1` unexpected/internal error
- `2` configuration error
- `3` validation error
- `4` resource not found
- `5` database error
- `6` doctor checks failed
