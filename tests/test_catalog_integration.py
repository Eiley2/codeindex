from __future__ import annotations

import os
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from codeindex import catalog, config, migrations


@pytest.fixture
def integration_db_url() -> str:
    db_url = os.getenv("COCOINDEX_TEST_DATABASE_URL")
    if not db_url:
        pytest.skip("Set COCOINDEX_TEST_DATABASE_URL to run integration tests")
    migrations.apply_migrations(db_url)
    return db_url


@pytest.mark.integration
def test_catalog_upsert_and_get(integration_db_url: str) -> None:
    catalog.ensure_catalog_table(integration_db_url)
    index_name = f"it_{uuid4().hex[:8]}"

    metadata = catalog.IndexMetadata(
        index_name=index_name,
        source_path="/tmp/project",
        include_patterns=("*.py",),
        exclude_patterns=(".git/**",),
        embedding_model=config.EMBEDDING_MODEL,
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        min_chunk_size=config.MIN_CHUNK_SIZE,
    )

    catalog.upsert_index_metadata(integration_db_url, metadata)
    fetched = catalog.get_index_metadata(integration_db_url, index_name)

    assert fetched is not None
    assert fetched.index_name == index_name
    assert fetched.source_path == "/tmp/project"

    assert catalog.delete_index_metadata(integration_db_url, index_name) is True


@pytest.mark.integration
def test_delete_index_tables(integration_db_url: str) -> None:
    catalog.ensure_catalog_table(integration_db_url)
    index_name = f"it_{uuid4().hex[:8]}"
    embedding_table = config.table_name(index_name)
    tracking_table = f"{config.normalize_index_name(index_name)}{config.tracking_table_suffix()}"

    with psycopg.connect(integration_db_url) as conn, conn.cursor() as cur:
        cur.execute(
            sql.SQL("CREATE TABLE IF NOT EXISTS {} (id INTEGER)").format(
                sql.Identifier(embedding_table)
            )
        )
        cur.execute(
            sql.SQL("CREATE TABLE IF NOT EXISTS {} (id INTEGER)").format(
                sql.Identifier(tracking_table)
            )
        )
        conn.commit()

    listed = catalog.list_index_tables(integration_db_url, index_name)
    assert embedding_table in listed
    assert tracking_table in listed

    dropped = catalog.delete_index_tables(integration_db_url, index_name)

    assert embedding_table in dropped
    assert tracking_table in dropped
