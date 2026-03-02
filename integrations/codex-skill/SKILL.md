---
name: codeindex-local
description: Index and semantically search local repositories with codeindex. Use when a user asks where logic lives, how a flow is implemented, or when keyword search is insufficient. Supports index discovery, indexing/reindexing, and semantic queries.
---

# codeindex-local

```bash
codeindex list
codeindex status
codeindex index <repo_path> [index_name]
codeindex search <index_name> "<query>" -k 10
codeindex reindex <index_name>
codeindex delete <index_name> --dry-run
```

Notas:
- `codeindex list` y `codeindex status` muestran los proyectos/indexes disponibles.
- Si un repo define `exclude_patterns` en `.codeindex.toml`, mantener `node_modules/**` y `.venv/**` para evitar indexado lento.
