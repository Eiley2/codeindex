# codeindex

CLI local-first para indexar codebases y hacer búsqueda semántica con CocoIndex + PostgreSQL/pgvector.

## Quickstart (5 min)

### 1) Levantar PostgreSQL con pgvector

```bash
docker run --name codeindex-db \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=cocoindex \
  -p 5432:5432 \
  -d pgvector/pgvector:pg16
```

Crear extensión `vector` (una sola vez):

```bash
docker exec -i codeindex-db psql -U postgres -d cocoindex -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 2) Configurar conexión

```bash
cp .env.example .env
```

`.env.example`:

```dotenv
COCOINDEX_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/cocoindex
```

### 3) Instalar CLI

```bash
uv tool install .
codeindex --help
```

### 4) Indexar y consultar

```bash
codeindex index /path/al/repo mi_repo
codeindex search mi_repo "authentication middleware"
codeindex status mi_repo
```

## Installation

### Opción A: desarrollo local (recomendado para contribuir)

```bash
uv sync
uv run codeindex --help
```

### Opción B: instalación global desde repo local

```bash
uv tool install /ruta/absoluta/al/repo
codeindex --help
```

Para actualizar una instalación global:

```bash
uv tool install --force /ruta/absoluta/al/repo
```

## Uso diario

```bash
codeindex index /path/to/repo [name]
codeindex reindex my_repo
codeindex search my_repo "query" -k 10
codeindex list
codeindex status
codeindex doctor
```

Comandos destructivos y respaldos:

```bash
codeindex delete my_repo --dry-run
codeindex delete my_repo --yes
codeindex export metadata.json
codeindex import metadata.json --dry-run
codeindex import metadata.json
```

`codeindex` se puede ejecutar desde cualquier directorio; para indexar otro repo usa su path absoluto o relativo.

## Configuración

Resolución de DB URL (orden de precedencia):

1. `COCOINDEX_DATABASE_URL` (env)
2. `.env` en cwd o directorios padre
3. `~/.config/codeindex/config.toml`

Ejemplo `~/.config/codeindex/config.toml`:

```toml
database_url = "postgresql://user:password@localhost:5432/cocoindex"
```

## Config por proyecto

`codeindex` auto-descubre `.codeindex.toml` desde el path actual hacia arriba.

Plantilla:

```bash
cp .codeindex.toml.example /path/al/repo/.codeindex.toml
```

Claves soportadas:

- `[index].name`
- `[index].include_patterns`
- `[index].exclude_patterns`
- `[index].reset`
- `[index].max_files`
- `[index].max_file_bytes`
- `[chunking].chunk_size`
- `[chunking].chunk_overlap`
- `[chunking].min_chunk_size`

## Defaults operativos

Si no defines `.codeindex.toml` ni flags de override:

- `include_patterns`:
  `*.ts, *.tsx, *.js, *.jsx, *.py, *.go, *.rs, *.java, *.rb, *.php, *.cs, *.sql, *.md`
- `exclude_patterns`:
  `node_modules/**, .git/**, .venv/**, venv/**, env/**, .tox/**, .nox/**, build/**, dist/**, .next/**, __pycache__/**, .mypy_cache/**, .pytest_cache/**, .ruff_cache/**, *.min.js, *.lock, *.map`
- chunking:
  `chunk_size=1000`, `chunk_overlap=300`, `min_chunk_size=300`
- límites:
  `max_files` y `max_file_bytes` desactivados por defecto (sin límite)

Reglas de precedencia importantes:

- Si defines `[index].include_patterns`, reemplazas los includes por defecto.
- Si defines `[index].exclude_patterns`, reemplazas los excludes por defecto.
- `--exclude` en CLI se agrega al baseline activo (defaults o `.codeindex.toml`).
- Si personalizas `exclude_patterns`, mantén explícitamente exclusiones costosas como `.venv/**` y `node_modules/**`.

## Integraciones de agentes

- Codex skill: ver [docs/AGENT_INTEGRATIONS.md](docs/AGENT_INTEGRATIONS.md#codex-skill)
- Claude project instructions: ver [docs/AGENT_INTEGRATIONS.md](docs/AGENT_INTEGRATIONS.md#claude)

## Observabilidad

Usa `--verbose` para logs operativos (incluye tiempos por operación):

```bash
codeindex --verbose index /path/al/repo
```

## Tests

```bash
uv run ruff check .
uv run mypy codeindex tests
uv run pytest -q
```

E2E real (`index -> search`) con DB de prueba:

```bash
export COCOINDEX_TEST_DATABASE_URL='postgresql://postgres:postgres@localhost:5432/cocoindex_test'
export COCOINDEX_RUN_E2E=1
uv run pytest -q -m e2e
```

## Release hygiene

- Changelog: `CHANGELOG.md`
- CI de release por tag: `.github/workflows/release.yml`

Publicar release:

```bash
git tag v0.1.1
git push origin v0.1.1
```

## Exit codes

- `1` error interno
- `2` error de configuración
- `3` error de validación
- `4` recurso no encontrado
- `5` error de base de datos
- `6` doctor checks fallidos
