---
name: codeindex-local
description: Index and semantically search local repositories with codeindex. Use when the user asks where logic lives, how a flow is implemented, or when keyword search is insufficient. Supports index discovery, indexing, reindexing, and semantic queries.
---

# codeindex-local

```bash
codeindex list
codeindex index <repo_path> [index_name]
codeindex search <index_name> "<query>" -k 10
codeindex reindex <index_name>
codeindex delete <index_name> --dry-run
```

## Notes

- Run `codeindex list` first to discover available indexes and metadata.
- If a repository defines `exclude_patterns` in `.codeindex.toml`, the built-in exclude defaults are replaced. Retain `node_modules/**` and `.venv/**` explicitly in custom lists to avoid slow or oversized indexing runs.
