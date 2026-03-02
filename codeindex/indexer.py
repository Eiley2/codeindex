from __future__ import annotations

import asyncio
import os
from pathlib import Path, PurePosixPath

import cocoindex

from . import catalog, config
from .errors import ValidationError


def _build_flow(
    name: str,
    path: str,
    included: list[str],
    excluded: list[str],
    chunk_size: int,
    chunk_overlap: int,
    min_chunk_size: int,
) -> None:
    @cocoindex.flow_def(name=name)
    def _flow(
        flow_builder: cocoindex.FlowBuilder, data_scope: cocoindex.DataScope
    ) -> None:
        data_scope["files"] = flow_builder.add_source(
            cocoindex.sources.LocalFile(
                path=path,
                included_patterns=included,
                excluded_patterns=excluded,
            )
        )

        embeddings = data_scope.add_collector()

        with data_scope["files"].row() as file:
            file["language"] = file["filename"].transform(
                cocoindex.functions.DetectProgrammingLanguage()
            )
            file["chunks"] = file["content"].transform(
                cocoindex.functions.SplitRecursively(),
                language=file["language"],
                chunk_size=chunk_size,
                min_chunk_size=min_chunk_size,
                chunk_overlap=chunk_overlap,
            )

            with file["chunks"].row() as chunk:
                chunk["embedding"] = chunk["text"].transform(
                    cocoindex.functions.SentenceTransformerEmbed(
                        model=config.EMBEDDING_MODEL
                    )
                )
                embeddings.collect(
                    filename=file["filename"],
                    location=chunk["location"],
                    text=chunk["text"],
                    embedding=chunk["embedding"],
                )

        embeddings.export(
            "code_embeddings",
            cocoindex.storages.Postgres(),
            primary_key_fields=["filename", "location"],
            vector_indexes=[
                cocoindex.VectorIndexDef(
                    field_name="embedding",
                    metric=cocoindex.VectorSimilarityMetric.COSINE_SIMILARITY,
                )
            ],
        )


async def _run_async(reset: bool) -> dict:
    all_flows = list(cocoindex.flow.flows().values())
    setup_bundle = await cocoindex.flow.make_setup_bundle_async(all_flows)
    _, is_up_to_date = await setup_bundle.describe_async()
    if not is_up_to_date:
        await setup_bundle.apply_async(report_to_stdout=True)

    return await cocoindex.update_all_flows_async(
        cocoindex.FlowLiveUpdaterOptions(
            live_mode=False,
            full_reprocess=reset,
            print_stats=True,
        )
    )


def _matches(path: PurePosixPath, patterns: list[str]) -> bool:
    return any(path.match(pattern) for pattern in patterns)


def _preflight_file_limits(
    path: str,
    included: list[str],
    excluded: list[str],
    max_files: int | None,
    max_file_bytes: int | None,
) -> int:
    if max_files is not None and max_files < 1:
        raise ValidationError("--max-files must be >= 1 when provided.")
    if max_file_bytes is not None and max_file_bytes < 1:
        raise ValidationError("--max-file-bytes must be >= 1 when provided.")

    root = Path(path)
    matched_files = 0
    oversized_files: list[str] = []

    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        relative = PurePosixPath(file_path.relative_to(root).as_posix())
        if not _matches(relative, included):
            continue
        if _matches(relative, excluded):
            continue

        matched_files += 1
        if max_files is not None and matched_files > max_files:
            raise ValidationError(
                f"Matched files ({matched_files}) exceed max_files={max_files}. "
                "Narrow include/exclude patterns or increase the limit."
            )

        if max_file_bytes is not None:
            size = file_path.stat().st_size
            if size > max_file_bytes:
                oversized_files.append(f"{relative} ({size} bytes)")
                if len(oversized_files) >= 5:
                    break

    if oversized_files:
        details = ", ".join(oversized_files)
        raise ValidationError(
            "Found files larger than max_file_bytes="
            f"{max_file_bytes}: {details}."
        )

    return matched_files


def run(
    path: str,
    name: str,
    included: list[str],
    excluded: list[str],
    reset: bool,
    db_url: str | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    min_chunk_size: int | None = None,
    max_files: int | None = None,
    max_file_bytes: int | None = None,
) -> dict:
    abs_path = os.path.abspath(path)
    if not os.path.isdir(abs_path):
        raise ValidationError(f"'{path}' is not a valid directory.")
    if not included:
        raise ValidationError("At least one include pattern is required.")
    if not name.strip():
        raise ValidationError("Index name cannot be empty.")

    flow_name = config.normalize_index_name(name)
    effective_db_url = db_url or config.get_database_url()
    resolved_chunk_size = chunk_size if chunk_size is not None else config.CHUNK_SIZE
    resolved_chunk_overlap = (
        chunk_overlap if chunk_overlap is not None else config.CHUNK_OVERLAP
    )
    resolved_min_chunk_size = (
        min_chunk_size if min_chunk_size is not None else config.MIN_CHUNK_SIZE
    )
    _preflight_file_limits(
        abs_path,
        included=included,
        excluded=excluded,
        max_files=max_files,
        max_file_bytes=max_file_bytes,
    )

    cocoindex.init(
        cocoindex.Settings(
            database=cocoindex.DatabaseConnectionSpec(url=effective_db_url)
        )
    )
    _build_flow(
        flow_name,
        abs_path,
        included,
        excluded,
        chunk_size=resolved_chunk_size,
        chunk_overlap=resolved_chunk_overlap,
        min_chunk_size=resolved_min_chunk_size,
    )
    stats = asyncio.run(_run_async(reset=reset))
    catalog.upsert_index_metadata(
        effective_db_url,
        catalog.IndexMetadata(
            index_name=flow_name,
            source_path=abs_path,
            include_patterns=tuple(included),
            exclude_patterns=tuple(excluded),
            embedding_model=config.EMBEDDING_MODEL,
            chunk_size=resolved_chunk_size,
            chunk_overlap=resolved_chunk_overlap,
            min_chunk_size=resolved_min_chunk_size,
        ),
    )
    return stats
