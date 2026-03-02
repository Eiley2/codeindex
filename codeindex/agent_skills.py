from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

WriteMode = Literal["set", "update"]
WriteStatus = Literal["created", "updated", "unchanged", "skipped_exists"]

CODEX_SKILL_NAME = "codeindex-local"

CODEX_SKILL_TEMPLATE = """---
name: codeindex-local
description: >
  Index and semantically search local repositories with codeindex.
  Use when the user asks where logic lives, how a flow is implemented,
  or when keyword search is insufficient.
  Supports index discovery, indexing, reindexing, and semantic queries.
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
- If a repository defines `exclude_patterns` in `.codeindex.toml`,
  built-in exclude defaults are replaced.
  Retain `node_modules/**` and `.venv/**` explicitly in custom lists
  to avoid slow or oversized indexing runs.
"""

CLAUDE_TEMPLATE = """# codeindex

Use `codeindex` for semantic search over this repository before answering
questions about where logic lives, how a feature is implemented,
or which files handle a given concern.

## Standard workflow

1. Check existing indexes:
```bash
codeindex list
```

2. Create an index if none exists:
```bash
codeindex index . [index_name]
```

3. Query for relevant context:
```bash
codeindex search <index_name> "<query>" -k 10
```

4. Refresh after code changes:
```bash
codeindex reindex <index_name>
```

5. Preview before deleting:
```bash
codeindex delete <index_name> --dry-run
```

## Notes

- `codeindex list` shows available indexes and metadata (index name and source path).
- If this repository defines `exclude_patterns` in `.codeindex.toml`,
  built-in exclude defaults are replaced.
  Ensure `node_modules/**` and `.venv/**` are present in the custom list
  to avoid slow indexing.
"""


def default_codex_home() -> Path:
    return Path(os.getenv("CODEX_HOME", Path.home() / ".codex"))


def codex_skill_path(codex_home: Path) -> Path:
    return codex_home / "skills" / CODEX_SKILL_NAME / "SKILL.md"


def write_template(path: Path, content: str, mode: WriteMode) -> WriteStatus:
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    if existing == content:
        return "unchanged"
    if existing is not None and mode == "set":
        return "skipped_exists"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if existing is None:
        return "created"
    return "updated"
