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

Defaults útiles para agentes:
- Excluye por defecto `node_modules/**`, `.venv/**`, `.git/**`, `dist/**`, caches y artefactos.
- Si el repo define `[index].exclude_patterns` en `.codeindex.toml`, esos defaults se reemplazan; conviene mantener `node_modules/**` y `.venv/**`.

## Claude

```bash
cp integrations/claude/CLAUDE.md.example CLAUDE.md
```

La plantilla incluye el mismo checklist operativo (`list/status/index/search/reindex`).
