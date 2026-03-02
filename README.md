# codeindex

Local-first CLI for indexing codebases and running semantic search with CocoIndex + PostgreSQL/pgvector.

## Install

```bash
pip install .
# or for global CLI without manual venv activation:
# pipx install .
```

## Configuration

`codeindex` resolves database URL in this order:

1. Environment variable `COCOINDEX_DATABASE_URL`
2. `~/.config/codeindex/config.toml`

Example config file:

```toml
database_url = "postgresql://user:password@localhost:5432/cocoindex"
```

## Usage

```bash
codeindex index /path/to/repo my_repo
codeindex search my_repo "authentication middleware" --top-k 10
codeindex list
```

Legacy scripts `index_codebase.py` and `search.py` are kept as compatibility wrappers and delegate to `codeindex`.
