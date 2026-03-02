from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import psycopg
from psycopg import sql
from psycopg.errors import Error as PsycopgError

from .errors import DatabaseError

SCHEMA_MIGRATIONS_TABLE = "codeindex_schema_migrations"
CATALOG_TABLE = "codeindex_indexes"


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=1,
        name="create_catalog_table",
        statements=(
            f"""
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
            """.strip(),
        ),
    ),
)


def _ensure_migrations_table(conn: psycopg.Connection) -> None:
    table_identifier = sql.Identifier(SCHEMA_MIGRATIONS_TABLE)
    query = sql.SQL(
        """
        CREATE TABLE IF NOT EXISTS {} (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    ).format(table_identifier)
    with conn.cursor() as cur:
        cur.execute(query)


def _applied_versions(conn: psycopg.Connection) -> set[int]:
    table_identifier = sql.Identifier(SCHEMA_MIGRATIONS_TABLE)
    query = sql.SQL("SELECT version FROM {} ORDER BY version").format(table_identifier)
    with conn.cursor() as cur:
        cur.execute(query)
        return {int(row[0]) for row in cur.fetchall()}


def apply_migrations(db_url: str) -> list[int]:
    try:
        with psycopg.connect(db_url) as conn:
            _ensure_migrations_table(conn)
            applied = _applied_versions(conn)
            newly_applied: list[int] = []

            for migration in MIGRATIONS:
                if migration.version in applied:
                    continue

                with conn.cursor() as cur:
                    for statement in migration.statements:
                        cur.execute(statement)
                    cur.execute(
                        sql.SQL("INSERT INTO {} (version, name) VALUES (%s, %s)").format(
                            sql.Identifier(SCHEMA_MIGRATIONS_TABLE)
                        ),
                        (migration.version, migration.name),
                    )
                newly_applied.append(migration.version)

            conn.commit()
            return newly_applied
    except PsycopgError as exc:
        raise DatabaseError(f"Unable to apply migrations: {exc}") from exc


def list_applied_migrations(db_url: str) -> list[tuple[int, str, datetime]]:
    try:
        with psycopg.connect(db_url) as conn:
            _ensure_migrations_table(conn)
            conn.commit()
            query = sql.SQL(
                "SELECT version, name, applied_at FROM {} ORDER BY version"
            ).format(sql.Identifier(SCHEMA_MIGRATIONS_TABLE))
            with conn.cursor() as cur:
                cur.execute(query)
                return [
                    (int(row[0]), str(row[1]), row[2])
                    for row in cur.fetchall()
                ]
    except PsycopgError as exc:
        raise DatabaseError(f"Unable to list migrations: {exc}") from exc


def latest_migration_version() -> int:
    if not MIGRATIONS:
        return 0
    return MIGRATIONS[-1].version
