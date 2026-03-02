from dataclasses import dataclass

import cocoindex
import psycopg
from pgvector.psycopg import register_vector

from . import config


@dataclass
class SearchResult:
    rank: int
    score: float
    filename: str
    text: str


@cocoindex.transform_flow()
def _text_to_embedding(
    text: cocoindex.DataSlice[str],
) -> cocoindex.DataSlice[cocoindex.Vector[cocoindex.Float32]]:
    return text.transform(
        cocoindex.functions.SentenceTransformerEmbed(model=config.EMBEDDING_MODEL)
    )


def list_indexes(db_url: str) -> "list[str]":
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name LIKE %s
                ORDER BY table_name
            """, (f"%{config.tracking_table_suffix()}",))
            return [
                row[0].replace(config.tracking_table_suffix(), "")
                for row in cur.fetchall()
            ]


def _resolve_table(db_url: str, index_name: str) -> str:
    """Find the embeddings table for the given index name."""
    prefix = config.slugify(index_name).lower()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name LIKE %s
                  AND table_name NOT LIKE '%%tracking'
                  AND table_name NOT LIKE '%%metadata'
                ORDER BY table_name
                LIMIT 1
            """, (f"{prefix}__%",))
            row = cur.fetchone()

    if not row:
        available = list_indexes(db_url)
        hint = f"Available indexes: {', '.join(available)}" if available else "No indexes found."
        raise ValueError(f"Index '{index_name}' not found. {hint}")

    return row[0]


def search(index_name: str, query: str, top_k: int = config.DEFAULT_TOP_K) -> list[SearchResult]:
    db_url = config.get_database_url()
    table = _resolve_table(db_url, index_name)

    cocoindex.init(
        cocoindex.Settings(database=cocoindex.DatabaseConnectionSpec(url=db_url))
    )
    query_vector = _text_to_embedding.eval(query)

    with psycopg.connect(db_url) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT filename, text, 1 - (embedding <=> %s::vector) AS score
                FROM {table}
                ORDER BY score DESC
                LIMIT %s
                """,
                (query_vector, top_k),
            )
            return [
                SearchResult(rank=i + 1, score=score, filename=filename, text=text)
                for i, (filename, text, score) in enumerate(cur.fetchall())
            ]
