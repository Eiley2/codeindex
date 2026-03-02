# codeindex-local

Usa este skill para indexar y consultar código local con `codeindex`.

## Prerrequisitos

- `codeindex` instalado y disponible en PATH.
- `COCOINDEX_DATABASE_URL` configurado o `.env` presente.

## Flujo recomendado

1. Validar entorno:

```bash
codeindex doctor
```

2. Indexar repositorio actual:

```bash
codeindex index .
```

3. Consultar contexto semántico:

```bash
codeindex search <index_name> "<query>" -k 10
```

4. Revisar estado:

```bash
codeindex status <index_name>
```

## Operaciones seguras

- Plan de borrado:

```bash
codeindex delete <index_name> --dry-run
```

- Borrado definitivo:

```bash
codeindex delete <index_name> --yes
```

## Backup de metadatos

```bash
codeindex export metadata.json
codeindex import metadata.json --dry-run
```
