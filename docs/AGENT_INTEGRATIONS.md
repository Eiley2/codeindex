# Agent Integrations

`codeindex` is designed to serve as a semantic context retrieval layer for AI coding agents. This document covers the available integration templates and how to set them up.

---

## Codex

The Codex skill gives agents a minimal, reliable workflow to discover projects, index, query, and maintain local `codeindex` indexes.

### Installation

```bash
codeindex skills set --codex-only
```

Manual fallback:

```bash
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
mkdir -p "$CODEX_HOME/skills/codeindex-local"
cp integrations/codex-skill/SKILL.md \
  "$CODEX_HOME/skills/codeindex-local/SKILL.md"
```

### What the skill covers

The skill provides the agent with the following workflow:

| Step | Command | Purpose |
|------|---------|---------|
| Discover | `codeindex list` | See projects/indexes (name, path, chunks) |
| Setup | `codeindex setup --database-url "<postgres-url>" --preset fast` | Create global config when missing |
| Index | `codeindex index <path> [name]` | Create a new index for a repository |
| Search | `codeindex search <name> "<query>" -k 10` | Retrieve semantically relevant code chunks |
| Update | `codeindex reindex <name>` | Refresh the index after code changes |
| Clean up | `codeindex delete <name> --dry-run` | Preview deletion before committing |

### Notes for agents

- Built-in exclude patterns drop `node_modules/**`, `.venv/**`, `.git/**`, `dist/**`, caches, and build artifacts automatically.
- Use `--embedding-provider <local|openrouter>` and `--embedding-model <model_id>` on `index` or `reindex` to override embeddings for a run.
- OpenRouter requires `OPEN_ROUTER_API_KEY` (or `OPENROUTER_API_KEY`).
- If a repository defines `[index].exclude_patterns` in `.codeindex.toml`, the built-in defaults are **replaced**. In that case, ensure `node_modules/**` and `.venv/**` are retained explicitly to avoid slow or oversized indexing runs.

---

## Claude

The Claude integration template provides project-level instructions for Claude Code (or any Claude-based agent reading a `CLAUDE.md` file).

### Installation

Copy the template to the root of the repository you want to integrate with:

```bash
codeindex skills set --claude-only
```

Manual fallback:

```bash
cp integrations/claude/CLAUDE.md.example CLAUDE.md
```

Or merge its contents into an existing `CLAUDE.md`.

### What the template covers

The template instructs Claude to follow a standard `codeindex` workflow before answering questions about the codebase:

1. Check for existing indexes with `codeindex list`.
2. Run `codeindex setup --database-url "<postgres-url>" --preset fast` if config is missing.
3. Create an index with `codeindex index . [name]` if none exists.
4. Query with `codeindex search <name> "<query>" -k 10` to retrieve relevant context.
5. Refresh with `codeindex reindex <name>` when the codebase has changed.

This lets Claude retrieve semantically relevant code instead of relying solely on file reads or keyword search.

---

## Cursor

The Cursor skill provides a repository-local `SKILL.md` that teaches Cursor how to use `codeindex` as a semantic retrieval layer before answering code questions.

### Installation

```bash
codeindex skills set --cursor-only
```

Manual fallback:

```bash
CURSOR_HOME="${CURSOR_HOME:-$HOME/.cursor}"
mkdir -p "$CURSOR_HOME/skills/codeindex-local"
cp integrations/cursor-skill/SKILL.md \
  "$CURSOR_HOME/skills/codeindex-local/SKILL.md"
```

### What the skill covers

The Cursor skill follows the same operating pattern:

1. Check existing indexes with `codeindex list`.
2. Run `codeindex setup --database-url "<postgres-url>" --preset fast` if config is missing.
3. Create an index with `codeindex index . [name]` if none exists.
4. Query with `codeindex search <name> "<query>" -k 10`.
5. Refresh with `codeindex reindex <name>` after code changes.

This keeps Cursor grounded in semantically relevant code chunks instead of relying only on keyword search.
