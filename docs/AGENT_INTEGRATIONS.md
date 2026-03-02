# Agent Integrations

## Codex

Instala el skill local:

```bash
mkdir -p "$CODEX_HOME/skills/codeindex-local"
cp integrations/codex-skill/SKILL.md "$CODEX_HOME/skills/codeindex-local/SKILL.md"
```

El skill explica a Codex para qué sirve `codeindex`, cuándo usarlo y flujo recomendado (`index` -> `search` -> `reindex`).

## Claude

Copia la plantilla al proyecto:

```bash
cp integrations/claude/CLAUDE.md.example CLAUDE.md
```

La guía está orientada al LLM: propósito, señales de cuándo usar `codeindex`, pasos mínimos y tipo de resultado esperado.
