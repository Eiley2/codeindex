from __future__ import annotations

from dataclasses import dataclass

import psycopg
from psycopg.errors import Error as PsycopgError

from . import catalog
from .errors import DatabaseError


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str


def run_checks(db_url: str) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []

    try:
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            checks.append(
                DoctorCheck(
                    "database_connection",
                    True,
                    "PostgreSQL connection is healthy.",
                )
            )

            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_extension
                    WHERE extname = 'vector'
                )
                """
            )
            row = cur.fetchone()
            has_vector = bool(row[0]) if row is not None else False
            checks.append(
                DoctorCheck(
                    "pgvector_extension",
                    has_vector,
                    "Extension 'vector' is installed."
                    if has_vector
                    else "Extension 'vector' is missing. Run: CREATE EXTENSION vector;",
                )
            )
    except PsycopgError as exc:
        raise DatabaseError(f"Doctor failed while validating database: {exc}") from exc

    try:
        catalog.ensure_catalog_table(db_url)
        checks.append(DoctorCheck("catalog_table", True, "Catalog table is present."))
    except DatabaseError as exc:
        checks.append(DoctorCheck("catalog_table", False, str(exc)))

    return checks
