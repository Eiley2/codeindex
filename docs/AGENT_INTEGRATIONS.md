# Agent Integrations

## Codex

Instalar skill:

```bash
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
mkdir -p "$CODEX_HOME/skills/codeindex-local"
cp integrations/codex-skill/SKILL.md \
  "$CODEX_HOME/skills/codeindex-local/SKILL.md"
```

El skill incluye flujo para:
- ver proyectos (`list`, `status`)
- indexar (`index`)
- consultar (`search`)
- actualizar (`reindex`)

## Claude

```bash
cp integrations/claude/CLAUDE.md.example CLAUDE.md
```

La plantilla incluye el mismo checklist operativo (`list/status/index/search/reindex`).
