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
