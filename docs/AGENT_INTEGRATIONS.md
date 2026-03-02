# Agent Integrations

`codeindex` is designed to serve as a semantic context retrieval layer for AI coding agents. This document covers the available integration templates and how to set them up.

---

## Codex

The Codex skill teaches an agent how to discover, index, query, and maintain `codeindex` indexes. Install it once and any Codex session gains access to semantic codebase search.

### Installation

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
| Discover | `codeindex list` / `codeindex status` | Check which indexes exist and their metadata |
| Index | `codeindex index <path> [name]` | Create a new index for a repository |
| Search | `codeindex search <name> "<query>" -k 10` | Retrieve semantically relevant code chunks |
| Update | `codeindex reindex <name>` | Refresh the index after code changes |
| Clean up | `codeindex delete <name> --dry-run` | Preview deletion before committing |

### Notes for agents

- Built-in exclude patterns drop `node_modules/**`, `.venv/**`, `.git/**`, `dist/**`, caches, and build artifacts automatically.
- If a repository defines `[index].exclude_patterns` in `.codeindex.toml`, the built-in defaults are **replaced**. In that case, ensure `node_modules/**` and `.venv/**` are retained explicitly to avoid slow or oversized indexing runs.

---

## Claude

The Claude integration template provides project-level instructions for Claude Code (or any Claude-based agent reading a `CLAUDE.md` file).

### Installation

Copy the template to the root of the repository you want to integrate with:

```bash
cp integrations/claude/CLAUDE.md.example CLAUDE.md
```

Or merge its contents into an existing `CLAUDE.md`.

### What the template covers

The template instructs Claude to follow a standard `codeindex` workflow before answering questions about the codebase:

1. Check for existing indexes with `codeindex list` and `codeindex status`.
2. Create an index with `codeindex index . [name]` if none exists.
3. Query with `codeindex search <name> "<query>" -k 10` to retrieve relevant context.
4. Refresh with `codeindex reindex <name>` when the codebase has changed.

This lets Claude retrieve semantically relevant code instead of relying solely on file reads or keyword search.
