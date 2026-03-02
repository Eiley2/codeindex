import json
import re
from dataclasses import dataclass
from typing import Any

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
    location: Any | None = None
    line_start: int | None = None
    line_end: int | None = None


def _coerce_positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else None
    return None


def _extract_line_range(location: Any) -> tuple[int | None, int | None]:
    if location is None:
        return None, None

    if isinstance(location, str):
        stripped = location.strip()
        if not stripped:
            return None, None
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            start_match = re.search(
                r"(?:line|lineno|line_start|start_line)\D+(\d+)",
                stripped,
                re.I,
            )
            end_match = re.search(r"(?:line_end|end_line)\D+(\d+)", stripped, re.I)
            start = int(start_match.group(1)) if start_match else None
            end = int(end_match.group(1)) if end_match else start
            return start, end
        return _extract_line_range(parsed)

    if isinstance(location, dict):
        direct_start = (
            location.get("line_start")
            or location.get("start_line")
            or location.get("line")
            or location.get("lineno")
            or location.get("row")
        )
        direct_end = (
            location.get("line_end")
            or location.get("end_line")
            or location.get("line")
            or location.get("lineno")
            or location.get("row")
        )
        start = _coerce_positive_int(direct_start)
        end = _coerce_positive_int(direct_end)
        if start is not None:
            return start, end or start

        start_block = location.get("start")
        end_block = location.get("end")
        nested_start, _ = _extract_line_range(start_block)
        nested_end, _ = _extract_line_range(end_block)
        if nested_start is not None:
            return nested_start, nested_end or nested_start

        for value in location.values():
            nested_start, nested_end = _extract_line_range(value)
            if nested_start is not None:
                return nested_start, nested_end or nested_start
        return None, None

    if isinstance(location, (list, tuple)):
        if len(location) >= 2:
            left_start, _ = _extract_line_range(location[0])
            right_start, _ = _extract_line_range(location[1])
            if left_start is not None:
                return left_start, right_start or left_start
        for item in location:
            nested_start, nested_end = _extract_line_range(item)
            if nested_start is not None:
                return nested_start, nested_end or nested_start
        return None, None

    return None, None


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


def search(
    index_name: str,
    query: str,
    top_k: int = config.DEFAULT_TOP_K,
    db_url: str | None = None,
) -> list[SearchResult]:
    if top_k < 1:
        raise ValidationError("--top-k must be >= 1.")
    if not query.strip():
        raise ValidationError("Query cannot be empty.")

    effective_db_url = db_url or config.get_database_url()
    table = _resolve_table(effective_db_url, index_name)

    cocoindex.init(
        cocoindex.Settings(database=cocoindex.DatabaseConnectionSpec(url=effective_db_url))
    )
    query_vector = _text_to_embedding.eval(query)

    try:
        with psycopg.connect(effective_db_url) as conn:
            register_vector(conn)
            with conn.cursor() as cur:
                query_sql = sql.SQL(
                    """
                    SELECT filename, location, text, 1 - (embedding <=> %s::vector) AS score
                    FROM {table}
                    ORDER BY score DESC
                    LIMIT %s
                    """
                ).format(table=sql.Identifier(table))
                cur.execute(query_sql, (query_vector, top_k))
                results: list[SearchResult] = []
                for i, (filename, location, text, score) in enumerate(cur.fetchall()):
                    line_start, line_end = _extract_line_range(location)
                    results.append(
                        SearchResult(
                            rank=i + 1,
                            score=score,
                            filename=filename,
                            text=text,
                            location=location,
                            line_start=line_start,
                            line_end=line_end,
                        )
                    )
                return results
    except PsycopgError as exc:
        raise DatabaseError(f"Search query failed: {exc}") from exc
