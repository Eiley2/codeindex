# Agent Integrations

## Codex Skill

### Objetivo

Exponer `codeindex` como skill reusable dentro de Codex para que cualquier agente pueda indexar/buscar sin recordar comandos.

### 1) Crear skill local

```bash
mkdir -p "$CODEX_HOME/skills/codeindex-local"
cp integrations/codex-skill/SKILL.md "$CODEX_HOME/skills/codeindex-local/SKILL.md"
```

### 2) Verificar instalación

Abre una sesión de Codex y pide usar el skill por nombre (`codeindex-local`) o citándolo explícitamente.

### 3) Ejemplo de uso

- "Usa el skill codeindex-local para indexar este repo"
- "Con codeindex-local, busca dónde se maneja auth"

## Claude

### Opción A: Claude Code (repo local)

Claude Code lee instrucciones del archivo `CLAUDE.md` en la raíz del proyecto.

```bash
cp integrations/claude/CLAUDE.md.example CLAUDE.md
```

Esto le da comandos listos (`index`, `search`, `status`, `doctor`) dentro de ese repo.

### Opción B: Claude app (Project Instructions)

Si usas Claude Projects, copia el contenido de `integrations/claude/CLAUDE.md.example` en la sección de instrucciones del proyecto.

## Recomendaciones

- Mantén `codeindex` instalado globalmente con `uv tool install ...` para evitar dependencias del cwd.
- Define `COCOINDEX_DATABASE_URL` en `.env` del repo para minimizar fricción en agentes.
- Ejecuta `codeindex doctor` al inicio de nuevas sesiones de agente.
