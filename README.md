# codeindex

**Semantic search over codebases — local-first, embeddings-powered, agent-ready.**

`codeindex` is a CLI tool that indexes source code into a local PostgreSQL/pgvector database and answers natural language queries using vector similarity search. It is designed for developers and AI agents that need to navigate large codebases efficiently, without relying on cloud services or proprietary APIs.

---

## How it works

1. **Index** — `codeindex` walks a repository, filters files by configurable include/exclude patterns, splits content into overlapping text chunks, and generates vector embeddings using a local `sentence-transformers` model.
2. **Store** — Embeddings and metadata are persisted in PostgreSQL via the [pgvector](https://github.com/pgvector/pgvector) extension, managed through [CocoIndex](https://github.com/cocoindex-io/cocoindex) flows.
3. **Search** — Queries are embedded with the same model and matched against stored chunks using cosine similarity, returning ranked results with file paths and snippets.

Everything runs locally. No API keys, no internet required after the initial model download.

---

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- PostgreSQL 14+ with the [pgvector](https://github.com/pgvector/pgvector) extension

---

## Quickstart

### 1. Start PostgreSQL with pgvector

```bash
docker run --name codeindex-db \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=cocoindex \
  -p 5432:5432 \
  -d pgvector/pgvector:pg16
```

Enable the `vector` extension (once):

```bash
docker exec -i codeindex-db psql -U postgres -d cocoindex \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 2. Configure the database connection

```bash
cp .env.example .env
```

`.env.example`:

```dotenv
COCOINDEX_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/cocoindex
```

### 3. Install the CLI

```bash
uv tool install .
codeindex --help
```

### 4. Index and search

```bash
codeindex index /path/to/repo my_project
codeindex search my_project "authentication middleware"
codeindex status my_project
```

---

## Installation

### Development (recommended for contributors)

```bash
uv sync
uv run codeindex --help
```

### Global install from a local clone

```bash
uv tool install /absolute/path/to/repo
codeindex --help
```

To upgrade an existing global install:

```bash
uv tool install --force /absolute/path/to/repo
```

---

## CLI reference

All commands accept `--debug` (print full Python traceback) and `--verbose` (enable operational logs with timing) at the top level.

```
codeindex [--debug] [--verbose] <command> [options]
```

### `index`

Index a codebase at `PATH` under an optional `NAME` (defaults to the directory name).

```bash
codeindex index <path> [name] [options]
```

| Option | Description |
|--------|-------------|
| `-i, --include PATTERN` | File glob patterns to include. Repeatable. Replaces defaults when specified. |
| `-e, --exclude PATTERN` | Additional glob patterns to exclude. Repeatable. Added on top of active baseline. |
| `--reset` | Drop the existing index and rebuild from scratch. |
| `--max-files N` | Abort if the matched file count exceeds N. |
| `--max-file-bytes N` | Abort if any individual file exceeds N bytes. |

### `search`

Search an index using a natural language query.

```bash
codeindex search <name> "<query>" [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `-k, --top-k N` | 5 | Number of results to return. |
| `-s, --snippet-length N` | 250 | Characters to display per result. |

Results are ranked by cosine similarity score and color-coded (green ≥ 0.4, yellow ≥ 0.25, red below).

### `reindex`

Re-index an existing project using its saved metadata or project defaults.

```bash
codeindex reindex <name> [options]
```

Accepts the same `--path`, `--include`, `--exclude`, `--reset`, `--max-files`, and `--max-file-bytes` options as `index`. Useful to pick up code changes since the last index run.

### `list`

List all available indexes.

```bash
codeindex list
```

### `status`

Show index metadata: source path, chunk count, and last indexed timestamp.

```bash
codeindex status [name]
```

Omit `name` to show all indexes.

### `delete`

Delete index tables and catalog metadata with a confirmation step.

```bash
codeindex delete <name> [--dry-run] [--yes]
```

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview what would be deleted without making changes. |
| `--yes` | Skip the interactive confirmation prompt. |

Without `--yes`, you must type the index name to confirm deletion.

### `doctor`

Run environment diagnostics: database connectivity, pgvector availability, privilege checks, applied migrations, and package imports.

```bash
codeindex doctor
```

Exits with code `6` if any check fails.

### `export` / `import`

Back up and restore index metadata (catalog entries, not the embeddings themselves).

```bash
codeindex export metadata.json [name]
codeindex import metadata.json [--dry-run]
```

`export` writes a JSON file. `import` reads it back, with an optional `--dry-run` to validate without writing.

---

## Configuration

### Database URL

Resolved in the following precedence order:

1. `COCOINDEX_DATABASE_URL` environment variable
2. `.env` file discovered from the current directory upward
3. `~/.config/codeindex/config.toml`

Global config file example:

```toml
# ~/.config/codeindex/config.toml
database_url = "postgresql://user:password@localhost:5432/cocoindex"
```

### Project config (`.codeindex.toml`)

`codeindex` auto-discovers `.codeindex.toml` by walking from the current directory toward the filesystem root. Place one at the root of a repository to codify its indexing settings.

```bash
cp .codeindex.toml.example /path/to/repo/.codeindex.toml
```

All keys are optional:

```toml
[index]
name = "my_project"                    # Defaults to directory name
include_patterns = ["*.py", "*.md"]   # Replaces built-in defaults
exclude_patterns = [                   # Replaces built-in defaults
  "node_modules/**",
  ".git/**",
  ".venv/**",
]
reset = false                          # Drop and rebuild on every run
max_files = 20000                      # Abort threshold (file count)
max_file_bytes = 5000000               # Abort threshold (per-file bytes)

[chunking]
chunk_size = 1000                      # Target chunk size in characters
chunk_overlap = 300                    # Overlap between adjacent chunks
min_chunk_size = 300                   # Discard chunks smaller than this
```

### Built-in defaults

Applied when no `include_patterns` or `exclude_patterns` are set in `.codeindex.toml` or via CLI flags:

**Include patterns:**
```
*.ts  *.tsx  *.js  *.jsx  *.py  *.go  *.rs  *.java  *.rb  *.php  *.cs  *.sql  *.md
```

**Exclude patterns:**
```
node_modules/**  .git/**  .venv/**  venv/**  env/**  .tox/**  .nox/**
build/**  dist/**  .next/**  __pycache__/**  .mypy_cache/**
.pytest_cache/**  .ruff_cache/**  *.min.js  *.lock  *.map
```

**Chunking defaults:**
- `chunk_size`: 1000 characters
- `chunk_overlap`: 300 characters
- `min_chunk_size`: 300 characters

### Precedence rules

- Defining `[index].include_patterns` in `.codeindex.toml` **replaces** the built-in include list entirely.
- Defining `[index].exclude_patterns` in `.codeindex.toml` **replaces** the built-in exclude list entirely. When doing so, explicitly retain high-cost directories like `node_modules/**` and `.venv/**`.
- The `--exclude` CLI flag **appends** to whatever baseline is active (built-in defaults or `.codeindex.toml`).

---

## Agent integrations

`codeindex` is designed to be used by AI coding agents as a semantic context retrieval layer.

- **Codex skill:** see [docs/AGENT_INTEGRATIONS.md](docs/AGENT_INTEGRATIONS.md#codex)
- **Claude project instructions:** see [docs/AGENT_INTEGRATIONS.md](docs/AGENT_INTEGRATIONS.md#claude)

---

## Observability

Use `--verbose` to enable operational logs, including per-operation timing:

```bash
codeindex --verbose index /path/to/repo
```

---

## Development

### Running the test suite

```bash
uv run ruff check .
uv run mypy codeindex tests
uv run pytest -q
```

### End-to-end tests

E2E tests perform a real `index → search` cycle against a live database and are opt-in:

```bash
export COCOINDEX_TEST_DATABASE_URL='postgresql://postgres:postgres@localhost:5432/cocoindex_test'
export COCOINDEX_RUN_E2E=1
uv run pytest -q -m e2e
```

---

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Internal error |
| `2` | Configuration error |
| `3` | Validation error |
| `4` | Resource not found |
| `5` | Database error |
| `6` | Doctor checks failed |

---

## Release

Changes are tracked in [CHANGELOG.md](CHANGELOG.md). Releases are published by pushing a version tag; CI handles the rest:

```bash
git tag v0.1.1
git push origin v0.1.1
```
