# codeindex

**Semantic search over codebases — local-first, embeddings-powered, agent-ready.**

`codeindex` is a CLI tool that indexes source code into a local PostgreSQL/pgvector database and answers natural language queries using vector similarity search. It is designed for developers and AI agents that need to navigate large codebases efficiently, without relying on cloud services or proprietary APIs.

---

## How it works

1. **Index** — `codeindex` walks a repository, filters files by configurable include/exclude patterns, splits content into overlapping text chunks, and generates vector embeddings using a configurable local `sentence-transformers` model.
2. **Store** — Embeddings and metadata are persisted in PostgreSQL via the [pgvector](https://github.com/pgvector/pgvector) extension, managed through [CocoIndex](https://github.com/cocoindex-io/cocoindex) flows.
3. **Search** — Queries are embedded with the same model and matched against stored chunks using cosine similarity, returning ranked results with file paths and snippets.

Everything runs locally. No API keys, no internet required after the initial model download.

---

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- PostgreSQL 14+ with the [pgvector](https://github.com/pgvector/pgvector) extension

---

## Quickstart (Copy/Paste)

Assumes you already have `git`, `docker`, and `uv` installed.

```bash
# 1) Clone and enter the repo
git clone https://github.com/Eiley2/codeindex.git
cd codeindex

# 2) Start PostgreSQL + pgvector (idempotent for local testing)
docker rm -f codeindex-db >/dev/null 2>&1 || true
docker run --name codeindex-db \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=cocoindex \
  -p 5432:5432 \
  -d pgvector/pgvector:pg16

# 3) Enable vector extension
docker exec -i codeindex-db psql -U postgres -d cocoindex \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 4) Install CLI globally from this clone
uv tool install . --force

# 5) Initial setup (writes ~/.config/codeindex/config.toml)
codeindex setup --database-url "postgresql://postgres:postgres@localhost:5432/cocoindex" --preset fast

# 6) See model presets (optional)
codeindex embedding-models

# 7) Sanity check
codeindex doctor

# 8) Index this same repository and query it
codeindex index "$(pwd)" codeindex_demo
codeindex search codeindex_demo "how does reindex work" -k 5
codeindex list
```

Run from any directory after install:

```bash
cd /tmp
codeindex list
codeindex search codeindex_demo "catalog metadata"
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
uv tool install --force --refresh /absolute/path/to/repo
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
| `--embedding-provider {local,openrouter}` | Override embedding provider for this run. |
| `--embedding-model MODEL_ID` | Override embedding model for this run. |

### `search`

Search an index using a natural language query.

```bash
codeindex search <name> "<query>" [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `-k, --top-k N` | 10 | Number of results to return. |
| `-s, --snippet-length N` | 500 | Characters to display per result. |
| `--embedding-provider {local,openrouter}` | auto | Override query embedding provider. |
| `--embedding-model MODEL_ID` | auto | Override query embedding model. |

Results are ranked by cosine similarity score and color-coded (green ≥ 0.4, yellow ≥ 0.25, red below). When the stored chunk location includes line metadata, output also shows line/range (for example `path/to/file.py:42-58`).

For legacy/unmanaged indexes created with an older model, you can force a compatible query model:

```bash
codeindex search <name> "<query>" \
  --embedding-provider local \
  --embedding-model "sentence-transformers/all-MiniLM-L6-v2"
```

### `reindex`

Re-index an existing project using its saved metadata or project defaults.

```bash
codeindex reindex <name> [options]
```

Accepts the same `--path`, `--include`, `--exclude`, `--reset`, `--max-files`, `--max-file-bytes`, `--embedding-provider`, and `--embedding-model` options as `index`. Useful to pick up code changes since the last index run.

### `list`

List all available indexes.

```bash
codeindex list
```

For managed indexes, output includes source path, chunk count, and last indexed timestamp.

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

### `check-update`

Check whether your installed CLI is behind the latest GitHub release.

```bash
codeindex check-update
```

### `update`

Update the installed CLI package.

```bash
codeindex update
```

From a local clone instead of GitHub:

```bash
codeindex update --path /absolute/path/to/codeindex
```

The CLI also shows a lightweight update notification when a newer release is detected.

### `embedding-models`

List model presets derived from the benchmark study:

```bash
codeindex embedding-models
```

Current presets:

| Preset | Provider | Model ID | Typical usage |
|--------|----------|----------|----------------|
| `fast` | `local` | `sentence-transformers/all-MiniLM-L6-v2` | Fastest, low resource usage |
| `balanced` | `local` | `BAAI/bge-base-en-v1.5` | Quality/speed balance |
| `quality` | `local` | `intfloat/e5-large-v2` | Best retrieval quality (heavier) |
| `multilingual` | `local` | `nomic-ai/nomic-embed-text-v1.5` | Multilingual / long-context scenarios |

### `setup`

Create initial global config with DB URL and embedding model:

```bash
codeindex setup --database-url "postgresql://user:password@localhost:5432/cocoindex" --preset fast
```

Run interactive setup (recommended for local use):

```bash
codeindex setup
```

Interactive mode shows numbered menus for setup mode, presets, provider, and model, so you can select values instead of typing them manually.

Use OpenRouter:

```bash
export OPEN_ROUTER_API_KEY="<your_key>"
codeindex setup --embedding-provider openrouter --embedding-model "openai/text-embedding-3-small"
```

Use a custom local model id instead of preset:

```bash
codeindex setup --embedding-model "intfloat/e5-large-v2"
```

For scripts/CI, disable prompts explicitly:

```bash
codeindex setup --no-interactive --force --preset fast
```

Model/provider overrides at command level:

```bash
codeindex index . my_repo --embedding-provider local --embedding-model "BAAI/bge-base-en-v1.5"
codeindex reindex my_repo --embedding-provider openrouter --embedding-model "openai/text-embedding-3-small" --reset
```

### `completion zsh`

Print zsh autocomplete config:

```bash
codeindex completion zsh
```

Install it automatically in `~/.zshrc`:

```bash
codeindex completion zsh --install
source ~/.zshrc
```

### `skills set` / `skills update`

Set or update Codex/Claude/Cursor integration templates.

```bash
codeindex skills set
codeindex skills update
```

Target only one integration:

```bash
codeindex skills set --codex-only
codeindex skills update --claude-only
codeindex skills set --cursor-only
```

For Cursor, the default install path is `~/.cursor/skills/codeindex-local/SKILL.md`.

### `export` / `import`

Back up and restore index metadata (catalog entries, not the embeddings themselves).

```bash
codeindex export metadata.json [name]
codeindex import metadata.json [--dry-run]
```

`export` writes a JSON file. `import` reads it back, with an optional `--dry-run` to validate without writing.

---

## Configuration

### Global config

Use `codeindex setup` (recommended):

```bash
codeindex setup --database-url "postgresql://user:password@localhost:5432/cocoindex" --preset balanced
```

Or create the file manually:

```toml
# ~/.config/codeindex/config.toml
database_url = "postgresql://user:password@localhost:5432/cocoindex"
embedding_provider = "local"
embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
```

### Database URL

Resolved in the following precedence order:

1. `COCOINDEX_DATABASE_URL` environment variable
2. `.env` file discovered from the current directory upward
3. `~/.config/codeindex/config.toml`

### Embedding model

Resolution order depends on command:

1. `index`: CLI `--embedding-provider/--embedding-model` -> `.codeindex.toml` (`[index].embedding_provider`, `[index].embedding_model`) -> global (`COCOINDEX_EMBEDDING_PROVIDER`, `COCOINDEX_EMBEDDING_MODEL` or `~/.config/codeindex/config.toml`) -> built-in defaults.
2. `reindex`: CLI provider/model -> `.codeindex.toml` -> catalog metadata -> global -> built-in defaults.
3. `search`: catalog metadata -> global -> built-in default.

For `openrouter`, set `OPEN_ROUTER_API_KEY` (or `OPENROUTER_API_KEY`).

### Supported Models By Provider

`codeindex` supports two embedding providers:

1. `local`
- Uses `cocoindex.functions.SentenceTransformerEmbed`.
- Accepts sentence-transformers compatible model IDs (Hugging Face style), for example:
  `sentence-transformers/all-MiniLM-L6-v2`, `BAAI/bge-base-en-v1.5`, `intfloat/e5-large-v2`.

2. `openrouter`
- Uses `cocoindex.functions.EmbedText` with `OPEN_ROUTER`.
- Accepts embedding-capable OpenRouter model IDs, for example:
  `openai/text-embedding-3-small`.
- Requires `OPEN_ROUTER_API_KEY` (or `OPENROUTER_API_KEY`).

### Switching Models Safely

If you change provider/model for an existing index, re-run indexing with reset to avoid mixed vectors:

```bash
codeindex reindex <name> --embedding-provider <provider> --embedding-model "<model_id>" --reset
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
embedding_provider = "local"           # local | openrouter
embedding_model = "BAAI/bge-base-en-v1.5"  # Optional per-project model override
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
- **Cursor skill:** see [docs/AGENT_INTEGRATIONS.md](docs/AGENT_INTEGRATIONS.md#cursor)

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
git tag vX.Y.Z
git push origin vX.Y.Z
```
