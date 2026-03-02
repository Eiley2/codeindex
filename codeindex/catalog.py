from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import psycopg
from psycopg import sql
from psycopg.errors import Error as PsycopgError

from . import config, migrations
from .errors import DatabaseError, NotFoundError

CATALOG_TABLE = "codeindex_indexes"
_CATALOG_ID = sql.Identifier(CATALOG_TABLE)


@dataclass(frozen=True)
class IndexMetadata:
    index_name: str
    source_path: str
    include_patterns: tuple[str, ...]
    exclude_patterns: tuple[str, ...]
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    min_chunk_size: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_indexed_at: datetime | None = None


def ensure_catalog_table(db_url: str) -> None:
    migrations.apply_migrations(db_url)
    if not table_exists(db_url, CATALOG_TABLE):
        raise DatabaseError("Catalog table migration did not create expected table.")


def upsert_index_metadata(db_url: str, metadata: IndexMetadata) -> None:
    ensure_catalog_table(db_url)
    try:
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    """
                    INSERT INTO {} (
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
                    """
                ).format(_CATALOG_ID),
                (
                    metadata.index_name,
                    metadata.source_path,
                    list(metadata.include_patterns),
                    list(metadata.exclude_patterns),
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
        include_patterns=tuple(row[2]),
        exclude_patterns=tuple(row[3]),
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
                sql.SQL(
                    """
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
                    FROM {}
                    ORDER BY index_name
                    """
                ).format(_CATALOG_ID)
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
                sql.SQL(
                    """
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
                    FROM {}
                    WHERE index_name = %s
                    """
                ).format(_CATALOG_ID),
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
                sql.SQL("DELETE FROM {} WHERE index_name = %s RETURNING 1").format(
                    _CATALOG_ID
                ),
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
    table_names = list_index_tables(db_url, index_name)
    try:
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            for table_name in table_names:
                drop_query = sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
                    sql.Identifier(table_name)
                )
                cur.execute(drop_query)
            conn.commit()
            return table_names
    except PsycopgError as exc:
        raise DatabaseError(f"Unable to delete index tables: {exc}") from exc


def list_index_tables(db_url: str, index_name: str) -> list[str]:
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
            return table_names
    except PsycopgError as exc:
        raise DatabaseError(f"Unable to list index tables: {exc}") from exc
