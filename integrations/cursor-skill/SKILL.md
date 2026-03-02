---
name: codeindex-local
description: Use codeindex to semantically search the current repository before answering questions about implementation details, code ownership, or feature behavior.
---

# codeindex-local

## Standard workflow

1. Discover existing indexes:
```bash
codeindex list
```

2. Setup config if missing:
```bash
codeindex setup --database-url "<postgres-url>" --preset fast
```

3. Index if needed:
```bash
codeindex index . [index_name]
```

4. Query for context:
```bash
codeindex search <index_name> "<query>" -k 10
```

5. Refresh after code changes:
```bash
codeindex reindex <index_name>
```

## Notes

- `codeindex list` shows index name, source path, and chunk count.
- Use `--embedding-provider <local|openrouter>` and `--embedding-model <model_id>` on `index`/`reindex` when needed.
- OpenRouter requires `OPEN_ROUTER_API_KEY` (or `OPENROUTER_API_KEY`).
- If `.codeindex.toml` overrides `exclude_patterns`, keep `node_modules/**` and `.venv/**` excluded explicitly.
