---
name: codeindex-local
description: Index and semantically search local repositories with codeindex. Use when the user asks where logic lives, how a flow is implemented, or when keyword search is insufficient. Supports index discovery, indexing, reindexing, and semantic queries.
---

# codeindex-local

```bash
codeindex list
codeindex setup --database-url "<postgres-url>" --preset fast
codeindex index <repo_path> [index_name]
codeindex search <index_name> "<query>" -k 10
codeindex reindex <index_name>
codeindex delete <index_name> --dry-run
```

## Notes

- `codeindex list` shows available projects/indexes (name, path, chunks).
- Run `codeindex setup` once if global config is missing.
- Use `--embedding-provider <local|openrouter>` and `--embedding-model <model_id>` on `index`/`reindex` to override embeddings.
- OpenRouter requires `OPEN_ROUTER_API_KEY` (or `OPENROUTER_API_KEY`).
- If a repository defines `exclude_patterns` in `.codeindex.toml`, the built-in exclude defaults are replaced. Retain `node_modules/**` and `.venv/**` explicitly in custom lists to avoid slow or oversized indexing runs.
