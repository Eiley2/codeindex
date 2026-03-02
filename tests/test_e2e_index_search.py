from __future__ import annotations

import os
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

import pytest

from codeindex import config, service
from codeindex.errors import NotFoundError


@pytest.mark.e2e
@pytest.mark.integration
def test_e2e_index_and_search(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_url = os.getenv("COCOINDEX_TEST_DATABASE_URL")
    if not db_url:
        pytest.skip("Set COCOINDEX_TEST_DATABASE_URL to run e2e test")
    if os.getenv("COCOINDEX_RUN_E2E") != "1":
        pytest.skip("Set COCOINDEX_RUN_E2E=1 to run e2e index/search test")

    monkeypatch.setenv(config.DATABASE_URL_ENV_VAR, db_url)

    project = tmp_path / "demo_repo"
    project.mkdir()
    (project / "auth.py").write_text(
        """
from fastapi import Request


def authentication_middleware(request: Request) -> bool:
    token = request.headers.get('authorization', '')
    return token.startswith('Bearer ')
""".strip()
        + "\n",
        encoding="utf-8",
    )

    index_name = f"e2e_{uuid4().hex[:8]}"

    try:
        service.index_codebase(
            service.IndexInput(
                path=project,
                name=index_name,
                include=("*.py",),
                reset=True,
            )
        )

        results = service.search_index(index_name, "authentication middleware", top_k=5)
        assert results
        assert any("auth.py" in result.filename for result in results)
    finally:
        with suppress(Exception):
            service.delete_index(index_name, dry_run=False)


@pytest.mark.e2e
@pytest.mark.integration
def test_e2e_lifecycle_index_list_delete(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_url = os.getenv("COCOINDEX_TEST_DATABASE_URL")
    if not db_url:
        pytest.skip("Set COCOINDEX_TEST_DATABASE_URL to run e2e test")
    if os.getenv("COCOINDEX_RUN_E2E") != "1":
        pytest.skip("Set COCOINDEX_RUN_E2E=1 to run e2e index/search lifecycle test")

    monkeypatch.setenv(config.DATABASE_URL_ENV_VAR, db_url)

    project = tmp_path / "lifecycle_repo"
    project.mkdir()
    (project / "main.py").write_text(
        "def answer() -> int:\n    return 42\n",
        encoding="utf-8",
    )

    index_name = f"life_{uuid4().hex[:8]}"

    try:
        service.index_codebase(
            service.IndexInput(
                path=project,
                name=index_name,
                include=("*.py",),
                reset=True,
            )
        )

        listing = service.list_indexes()
        assert len(listing.managed) == 1
        assert listing.managed[0].index_name == index_name

        search_results = service.search_index(index_name, "return 42", top_k=3)
        assert search_results

        plan = service.preview_delete(index_name)
        assert plan.metadata_exists is True

        service.delete_index(index_name, dry_run=False)

        with pytest.raises(NotFoundError):
            service.search_index(index_name, "return 42", top_k=3)
    finally:
        with suppress(Exception):
            service.delete_index(index_name, dry_run=False)
