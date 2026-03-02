"""
Búsqueda semántica sobre un codebase indexado con CocoIndex.

Uso:
    python search.py <index> <query> [opciones]

Ejemplos:
    python search.py VanguardCode "player contract"
    python search.py MiProyecto "authentication" -k 20
    python search.py --list
"""

import os
import re
import cocoindex
import psycopg
from pgvector.psycopg import register_vector

DATABASE_URL = os.getenv(
    "COCOINDEX_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/cocoindex",
)
TOP_K = 10


@cocoindex.transform_flow()
def text_to_embedding(
    text: cocoindex.DataSlice[str],
) -> cocoindex.DataSlice[cocoindex.Vector[cocoindex.Float32]]:
    return text.transform(
        cocoindex.functions.SentenceTransformerEmbed(
            model="sentence-transformers/all-MiniLM-L6-v2"
        )
    )


def slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "_", text).strip("_")


def list_indexes():
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name LIKE '%__cocoindex_tracking'
                ORDER BY table_name
            """)
            rows = cur.fetchall()

    if not rows:
        print("No hay índices disponibles. Corre index_codebase.py primero.")
        return

    print("\nÍndices disponibles:")
    for (table,) in rows:
        name = table.replace("__cocoindex_tracking", "")
        print(f"  {name}")


def search(index_name: str, query: str, top_k: int = TOP_K):
    prefix = slugify(index_name).lower()

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name LIKE %s
                  AND table_name NOT LIKE '%%tracking'
                  AND table_name NOT LIKE '%%metadata'
                ORDER BY table_name
            """, (f"{prefix}__%",))
            row = cur.fetchone()
            if not row:
                print(f"Error: índice '{index_name}' no encontrado. Usa --list para ver los disponibles.")
                return
            table = row[0]

    cocoindex.init(cocoindex.Settings(database=cocoindex.DatabaseConnectionSpec(url=DATABASE_URL)))
    query_vector = text_to_embedding.eval(query)

    with psycopg.connect(DATABASE_URL) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT filename, text, embedding <=> %s::vector AS distance
                FROM {table}
                ORDER BY distance
                LIMIT %s
                """,
                (query_vector, top_k),
            )
            results = cur.fetchall()

    print(f"\nResultados para: '{query}' [{index_name}]\n{'─' * 60}")
    for i, (filename, text, distance) in enumerate(results, 1):
        score = 1.0 - distance
        print(f"\n#{i} [{score:.3f}] {filename}")
        print(f"  {text[:200].strip().replace(chr(10), ' ')}...")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("index", nargs="?", help="Nombre del índice")
    parser.add_argument("query", nargs="*", help="Texto a buscar")
    parser.add_argument("-k", "--top-k", type=int, default=TOP_K)
    parser.add_argument("--list", action="store_true", help="Listar índices disponibles")
    args = parser.parse_args()

    if args.list or not args.index:
        list_indexes()
    else:
        if not args.query:
            parser.error("Debes especificar una query.")
        search(args.index, " ".join(args.query), top_k=args.top_k)
