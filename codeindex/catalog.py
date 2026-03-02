from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import psycopg
from psycopg import sql
from psycopg.errors import Error as PsycopgError

from . import config
from .errors import DatabaseError, NotFoundError

CATALOG_TABLE = "codeindex_indexes"


@dataclass(frozen=True)
class IndexMetadata:
    index_name: str
    source_path: str
    include_patterns: list[str]
    exclude_patterns: list[str]
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    min_chunk_size: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_indexed_at: datetime | None = None


def ensure_catalog_table(db_url: str) -> None:
    query = f"""
        CREATE TABLE IF NOT EXISTS {CATALOG_TABLE} (
            index_name TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            include_patterns TEXT[] NOT NULL,
            exclude_patterns TEXT[] NOT NULL,
            embedding_model TEXT NOT NULL,
            chunk_size INTEGER NOT NULL,
            chunk_overlap INTEGER NOT NULL,
            min_chunk_size INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_indexed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """
    try:
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(query)
            conn.commit()
    except PsycopgError as exc:
        raise DatabaseError(f"Unable to ensure catalog table: {exc}") from exc


def upsert_index_metadata(db_url: str, metadata: IndexMetadata) -> None:
    ensure_catalog_table(db_url)
    try:
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {CATALOG_TABLE} (
                    index_name,
                    source_path,
                    include_patterns,
                    exclude_patterns,
                    embedding_model,
                    chunk_size,
                    chunk_overlap,
                    min_chunk_size
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (index_name)
                DO UPDATE SET
                    source_path = EXCLUDED.source_path,
                    include_patterns = EXCLUDED.include_patterns,
                    exclude_patterns = EXCLUDED.exclude_patterns,
                    embedding_model = EXCLUDED.embedding_model,
                    chunk_size = EXCLUDED.chunk_size,
                    chunk_overlap = EXCLUDED.chunk_overlap,
                    min_chunk_size = EXCLUDED.min_chunk_size,
                    updated_at = NOW(),
                    last_indexed_at = NOW()
                """,
                (
                    metadata.index_name,
                    metadata.source_path,
                    metadata.include_patterns,
                    metadata.exclude_patterns,
                    metadata.embedding_model,
                    metadata.chunk_size,
                    metadata.chunk_overlap,
                    metadata.min_chunk_size,
                ),
            )
            conn.commit()
    except PsycopgError as exc:
        raise DatabaseError(f"Unable to save index metadata: {exc}") from exc


def _row_to_metadata(row: tuple) -> IndexMetadata:
    return IndexMetadata(
        index_name=row[0],
        source_path=row[1],
        include_patterns=list(row[2]),
        exclude_patterns=list(row[3]),
        embedding_model=row[4],
        chunk_size=row[5],
        chunk_overlap=row[6],
        min_chunk_size=row[7],
        created_at=row[8],
        updated_at=row[9],
        last_indexed_at=row[10],
    )


def list_index_metadata(db_url: str) -> list[IndexMetadata]:
    ensure_catalog_table(db_url)
    try:
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    index_name,
                    source_path,
                    include_patterns,
                    exclude_patterns,
                    embedding_model,
                    chunk_size,
                    chunk_overlap,
                    min_chunk_size,
                    created_at,
                    updated_at,
                    last_indexed_at
                FROM {CATALOG_TABLE}
                ORDER BY index_name
                """
            )
            return [_row_to_metadata(row) for row in cur.fetchall()]
    except PsycopgError as exc:
        raise DatabaseError(f"Unable to read index catalog: {exc}") from exc


def get_index_metadata(db_url: str, index_name: str) -> IndexMetadata | None:
    ensure_catalog_table(db_url)
    normalized_name = config.normalize_index_name(index_name)
    try:
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    index_name,
                    source_path,
                    include_patterns,
                    exclude_patterns,
                    embedding_model,
                    chunk_size,
                    chunk_overlap,
                    min_chunk_size,
                    created_at,
                    updated_at,
                    last_indexed_at
                FROM {CATALOG_TABLE}
                WHERE index_name = %s
                """,
                (normalized_name,),
            )
            row = cur.fetchone()
    except PsycopgError as exc:
        raise DatabaseError(f"Unable to read index metadata: {exc}") from exc
    if row is None:
        return None
    return _row_to_metadata(row)


def delete_index_metadata(db_url: str, index_name: str) -> bool:
    ensure_catalog_table(db_url)
    normalized_name = config.normalize_index_name(index_name)
    try:
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {CATALOG_TABLE} WHERE index_name = %s RETURNING 1",
                (normalized_name,),
            )
            row = cur.fetchone()
            conn.commit()
            return row is not None
    except PsycopgError as exc:
        raise DatabaseError(f"Unable to delete index metadata: {exc}") from exc


def table_exists(db_url: str, table_name: str) -> bool:
    try:
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = %s
                )
                """,
                (table_name,),
            )
            row = cur.fetchone()
    except PsycopgError as exc:
        raise DatabaseError(f"Unable to check table existence: {exc}") from exc
    return bool(row and row[0])


def index_document_count(db_url: str, index_name: str) -> int:
    table_name = config.table_name(index_name)
    if not table_exists(db_url, table_name):
        raise NotFoundError(f"Embeddings table '{table_name}' does not exist.")
    try:
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            query = sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table_name))
            cur.execute(query)
            row = cur.fetchone()
    except PsycopgError as exc:
        raise DatabaseError(f"Unable to count indexed chunks: {exc}") from exc
    return int(row[0]) if row is not None else 0


def delete_index_tables(db_url: str, index_name: str) -> list[str]:
    normalized_name = config.normalize_index_name(index_name)
    pattern = f"{normalized_name}__%"
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
                (pattern,),
            )
            table_names = [
                row[0] for row in cur.fetchall() if row[0] != CATALOG_TABLE
            ]
            for table_name in table_names:
                drop_query = sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
                    sql.Identifier(table_name)
                )
                cur.execute(drop_query)
            conn.commit()
            return table_names
    except PsycopgError as exc:
        raise DatabaseError(f"Unable to delete index tables: {exc}") from exc
