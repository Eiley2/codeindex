from dataclasses import dataclass

import cocoindex
import psycopg
from pgvector.psycopg import register_vector
from psycopg import sql
from psycopg.errors import Error as PsycopgError

from . import config
from .errors import DatabaseError, NotFoundError, ValidationError


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
    try:
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name LIKE %s
                    ORDER BY table_name
                    """,
                (f"%{config.tracking_table_suffix()}",),
            )
            suffix = config.tracking_table_suffix()
            return [
                row[0].replace(suffix, "")
                for row in cur.fetchall()
                if row[0].endswith(suffix)
            ]
    except PsycopgError as exc:
        raise DatabaseError(f"Unable to list indexes: {exc}") from exc


def _resolve_table(db_url: str, index_name: str) -> str:
    """Find the embeddings table for the given index name using exact table match."""
    table = config.table_name(index_name)
    try:
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = %s
                    """,
                (table,),
            )
            row = cur.fetchone()
    except PsycopgError as exc:
        raise DatabaseError(f"Unable to resolve index table: {exc}") from exc

    if row and isinstance(row[0], str):
        return row[0]

    available = list_indexes(db_url)
    hint = f"Available indexes: {', '.join(available)}" if available else "No indexes found."
    raise NotFoundError(f"Index '{index_name}' not found. {hint}")


def search(index_name: str, query: str, top_k: int = config.DEFAULT_TOP_K) -> list[SearchResult]:
    if top_k < 1:
        raise ValidationError("--top-k must be >= 1.")
    if not query.strip():
        raise ValidationError("Query cannot be empty.")

    db_url = config.get_database_url()
    table = _resolve_table(db_url, index_name)

    cocoindex.init(
        cocoindex.Settings(database=cocoindex.DatabaseConnectionSpec(url=db_url))
    )
    query_vector = _text_to_embedding.eval(query)

    try:
        with psycopg.connect(db_url) as conn:
            register_vector(conn)
            with conn.cursor() as cur:
                query_sql = sql.SQL(
                    """
                    SELECT filename, text, 1 - (embedding <=> %s::vector) AS score
                    FROM {table}
                    ORDER BY score DESC
                    LIMIT %s
                    """
                ).format(table=sql.Identifier(table))
                cur.execute(query_sql, (query_vector, top_k))
                return [
                    SearchResult(rank=i + 1, score=score, filename=filename, text=text)
                    for i, (filename, text, score) in enumerate(cur.fetchall())
                ]
    except PsycopgError as exc:
        raise DatabaseError(f"Search query failed: {exc}") from exc
