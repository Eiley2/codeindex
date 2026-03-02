# codeindex-local

## Qué es

`codeindex` permite indexar repositorios locales y hacer búsqueda semántica sobre el código.

## Cuándo usarlo

- Cuando el usuario pide "buscar dónde está X" en un repo.
- Cuando necesitas contexto semántico (no solo grep literal).
- Cuando el índice no existe o está desactualizado.

## Flujo

1. Asegura índice del repo objetivo:
```bash
codeindex index <repo_path> [index_name]
```

2. Haz consultas semánticas:
```bash
codeindex search <index_name> "<query>" -k 10
```

3. Si ya existe índice y cambió el repo:
```bash
codeindex reindex <index_name>
```

## Resultado esperado

- `index/reindex`: crea o actualiza embeddings del repo.
- `search`: devuelve archivos/snippets relevantes por similitud semántica.
