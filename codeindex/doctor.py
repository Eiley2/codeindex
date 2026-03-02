from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import psycopg
from psycopg.errors import Error as PsycopgError

from . import catalog, migrations
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
            start = perf_counter()
            cur.execute("SELECT 1")
            latency_ms = (perf_counter() - start) * 1000.0
            checks.append(
                DoctorCheck(
                    "database_connection",
                    True,
                    f"PostgreSQL connection is healthy ({latency_ms:.2f}ms).",
                )
            )

            cur.execute("SHOW server_version")
            version_row = cur.fetchone()
            pg_version = str(version_row[0]) if version_row is not None else "unknown"
            checks.append(
                DoctorCheck(
                    "postgres_version",
                    True,
                    f"Server version: {pg_version}",
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

            cur.execute(
                "SELECT has_schema_privilege(current_user, 'public', 'CREATE')"
            )
            privilege_row = cur.fetchone()
            can_create = bool(privilege_row[0]) if privilege_row is not None else False
            checks.append(
                DoctorCheck(
                    "public_schema_create_privilege",
                    can_create,
                    "Current user can create tables in schema 'public'."
                    if can_create
                    else "Current user lacks CREATE privilege on schema 'public'.",
                )
            )
    except PsycopgError as exc:
        raise DatabaseError(f"Doctor failed while validating database: {exc}") from exc

    try:
        applied_migrations = migrations.list_applied_migrations(db_url)
        latest_version = migrations.latest_migration_version()
        applied_latest = applied_migrations[-1][0] if applied_migrations else 0
        up_to_date = applied_latest >= latest_version
        checks.append(
            DoctorCheck(
                "migrations",
                up_to_date,
                f"Applied up to version {applied_latest}; latest is {latest_version}."
                if up_to_date
                else (
                    f"Migrations are behind: applied {applied_latest}, "
                    f"latest is {latest_version}."
                ),
            )
        )
    except DatabaseError as exc:
        checks.append(DoctorCheck("migrations", False, str(exc)))

    try:
        catalog.ensure_catalog_table(db_url)
        checks.append(DoctorCheck("catalog_table", True, "Catalog table is present."))
    except DatabaseError as exc:
        checks.append(DoctorCheck("catalog_table", False, str(exc)))

    try:
        import sentence_transformers  # noqa: F401

        checks.append(
            DoctorCheck(
                "sentence_transformers_import",
                True,
                "sentence-transformers package is importable.",
            )
        )
    except Exception as exc:
        checks.append(
            DoctorCheck(
                "sentence_transformers_import",
                False,
                f"sentence-transformers import failed: {exc}",
            )
        )

    return checks
