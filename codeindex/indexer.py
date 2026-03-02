from __future__ import annotations

import asyncio
import os

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
