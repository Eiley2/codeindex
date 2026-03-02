# codeindex-local

`codeindex` sirve para indexar repos locales y hacer búsqueda semántica.

## Cuándo usarlo

- Preguntas de ubicación/flujo/implementación de código.
- Cuando no basta con búsqueda literal.

## Flujo recomendado

1. Ver proyectos indexados:
```bash
codeindex list
codeindex status
```

2. Si no existe índice, crearlo:
```bash
codeindex index <repo_path> [index_name]
```

3. Consultar:
```bash
codeindex search <index_name> "<query>" -k 10
```

4. Si el repo cambió:
```bash
codeindex reindex <index_name>
```

## Operación segura

```bash
codeindex delete <index_name> --dry-run
```
