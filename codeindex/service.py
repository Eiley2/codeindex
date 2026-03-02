from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import catalog, config, doctor, indexer, migrations, project_config, searcher
from .errors import NotFoundError


@dataclass(frozen=True)
class IndexInput:
    path: Path
    name: str | None = None
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    reset: bool = False


@dataclass(frozen=True)
class ReindexInput:
    name: str
    path: Path | None = None
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    reset: bool | None = None


@dataclass(frozen=True)
class StatusItem:
    index_name: str
    source_path: str
    chunks: int | None
    last_indexed_at: datetime | None


@dataclass(frozen=True)
class IndexListResult:
    managed: tuple[catalog.IndexMetadata, ...]
    unmanaged: tuple[str, ...]


@dataclass(frozen=True)
class DeletePlan:
    index_name: str
    tables: tuple[str, ...]
    metadata_exists: bool


@dataclass(frozen=True)
class DoctorReport:
    database_url_source: str
    checks: tuple[doctor.DoctorCheck, ...]
    applied_migrations: tuple[tuple[int, str, datetime], ...]
    project_config_file: Path | None


@dataclass(frozen=True)
class IndexOperationResult:
    stats: dict
    resolved_name: str
    project_config_file: Path | None


def _chunking_values(pcfg: project_config.ProjectConfig) -> tuple[int, int, int]:
    return (
        pcfg.chunk_size if pcfg.chunk_size is not None else config.CHUNK_SIZE,
        pcfg.chunk_overlap if pcfg.chunk_overlap is not None else config.CHUNK_OVERLAP,
        pcfg.min_chunk_size if pcfg.min_chunk_size is not None else config.MIN_CHUNK_SIZE,
    )


def index_codebase(payload: IndexInput) -> IndexOperationResult:
    db_url = config.get_database_url()
    migrations.apply_migrations(db_url)

    pcfg = project_config.discover(payload.path)
    resolved_name = config.normalize_index_name(
        payload.name or pcfg.index_name or payload.path.name
    )

    included = list(payload.include) if payload.include else list(
        pcfg.include_patterns or config.DEFAULT_INCLUDED_PATTERNS
    )

    base_excluded = list(pcfg.exclude_patterns or config.DEFAULT_EXCLUDED_PATTERNS)
    excluded = base_excluded + list(payload.exclude)

    reset = payload.reset
    if not payload.reset and pcfg.default_reset is True:
        reset = True

    chunk_size, chunk_overlap, min_chunk_size = _chunking_values(pcfg)

    stats = indexer.run(
        path=str(payload.path),
        name=resolved_name,
        included=included,
        excluded=excluded,
        reset=reset,
        db_url=db_url,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        min_chunk_size=min_chunk_size,
    )

    return IndexOperationResult(
        stats=stats,
        resolved_name=resolved_name,
        project_config_file=pcfg.source_file,
    )


def reindex_codebase(payload: ReindexInput) -> IndexOperationResult:
    db_url = config.get_database_url()
    migrations.apply_migrations(db_url)

    normalized_name = config.normalize_index_name(payload.name)
    metadata = catalog.get_index_metadata(db_url, normalized_name)

    if payload.path is None and metadata is None:
        raise NotFoundError(
            f"Index '{normalized_name}' has no catalog metadata. Provide --path to proceed."
        )

    if payload.path is not None:
        source_path = payload.path
    else:
        if metadata is None:
            raise NotFoundError(
                f"Index '{normalized_name}' has no catalog metadata. Provide --path to proceed."
            )
        source_path = Path(metadata.source_path)
    pcfg = project_config.discover(source_path)

    if payload.include:
        included = list(payload.include)
    elif pcfg.include_patterns is not None:
        included = list(pcfg.include_patterns)
    elif metadata is not None:
        included = list(metadata.include_patterns)
    else:
        included = list(config.DEFAULT_INCLUDED_PATTERNS)

    if pcfg.exclude_patterns is not None:
        base_excluded = list(pcfg.exclude_patterns)
    elif metadata is not None:
        base_excluded = list(metadata.exclude_patterns)
    else:
        base_excluded = list(config.DEFAULT_EXCLUDED_PATTERNS)
    excluded = base_excluded + list(payload.exclude)

    if payload.reset is not None:
        reset = payload.reset
    elif pcfg.default_reset is not None:
        reset = pcfg.default_reset
    else:
        reset = True

    if pcfg.chunk_size is not None:
        chunk_size = pcfg.chunk_size
    elif metadata is not None:
        chunk_size = metadata.chunk_size
    else:
        chunk_size = config.CHUNK_SIZE

    if pcfg.chunk_overlap is not None:
        chunk_overlap = pcfg.chunk_overlap
    elif metadata is not None:
        chunk_overlap = metadata.chunk_overlap
    else:
        chunk_overlap = config.CHUNK_OVERLAP

    if pcfg.min_chunk_size is not None:
        min_chunk_size = pcfg.min_chunk_size
    elif metadata is not None:
        min_chunk_size = metadata.min_chunk_size
    else:
        min_chunk_size = config.MIN_CHUNK_SIZE

    stats = indexer.run(
        path=str(source_path),
        name=normalized_name,
        included=included,
        excluded=excluded,
        reset=reset,
        db_url=db_url,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        min_chunk_size=min_chunk_size,
    )

    return IndexOperationResult(
        stats=stats,
        resolved_name=normalized_name,
        project_config_file=pcfg.source_file,
    )


def search_index(index_name: str, query: str, top_k: int) -> list[searcher.SearchResult]:
    db_url = config.get_database_url()
    migrations.apply_migrations(db_url)
    return searcher.search(index_name, query, top_k=top_k, db_url=db_url)


def list_indexes() -> IndexListResult:
    db_url = config.get_database_url()
    migrations.apply_migrations(db_url)

    managed = tuple(catalog.list_index_metadata(db_url))
    if managed:
        return IndexListResult(managed=managed, unmanaged=())

    unmanaged = tuple(searcher.list_indexes(db_url))
    return IndexListResult(managed=(), unmanaged=unmanaged)


def status(index_name: str | None = None) -> list[StatusItem]:
    db_url = config.get_database_url()
    migrations.apply_migrations(db_url)

    if index_name:
        normalized_name = config.normalize_index_name(index_name)
        metadata = catalog.get_index_metadata(db_url, normalized_name)
        if metadata is None:
            raise NotFoundError(f"Index '{normalized_name}' not found in catalog.")
        items = [metadata]
    else:
        items = catalog.list_index_metadata(db_url)

    result: list[StatusItem] = []
    for item in items:
        try:
            chunks = catalog.index_document_count(db_url, item.index_name)
        except NotFoundError:
            chunks = None
        result.append(
            StatusItem(
                index_name=item.index_name,
                source_path=item.source_path,
                chunks=chunks,
                last_indexed_at=item.last_indexed_at,
            )
        )

    return result


def preview_delete(index_name: str) -> DeletePlan:
    db_url = config.get_database_url()
    migrations.apply_migrations(db_url)
    normalized_name = config.normalize_index_name(index_name)

    tables = tuple(catalog.list_index_tables(db_url, normalized_name))
    metadata_exists = catalog.get_index_metadata(db_url, normalized_name) is not None

    return DeletePlan(
        index_name=normalized_name,
        tables=tables,
        metadata_exists=metadata_exists,
    )


def delete_index(index_name: str, dry_run: bool = False) -> DeletePlan:
    plan = preview_delete(index_name)

    if dry_run:
        return plan

    if not plan.tables and not plan.metadata_exists:
        raise NotFoundError(f"Index '{plan.index_name}' not found.")

    db_url = config.get_database_url()
    catalog.delete_index_tables(db_url, plan.index_name)
    catalog.delete_index_metadata(db_url, plan.index_name)
    return plan


def run_doctor(start_path: Path | None = None) -> DoctorReport:
    db_url, source = config.resolve_database_url()
    checks = doctor.run_checks(db_url)
    applied = migrations.list_applied_migrations(db_url)
    pcfg = project_config.discover(start_path)

    return DoctorReport(
        database_url_source=source,
        checks=tuple(checks),
        applied_migrations=tuple(applied),
        project_config_file=pcfg.source_file,
    )
