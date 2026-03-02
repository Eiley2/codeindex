"""
Indexa cualquier codebase en PostgreSQL con pgvector usando CocoIndex.

Uso:
    python index_codebase.py <path> [opciones]

Ejemplos:
    python index_codebase.py ~/Personales/mi-app
    python index_codebase.py ~/Personales/mi-app --name MiApp
    python index_codebase.py ~/Personales/mi-app --include "*.py" "*.md"
    python index_codebase.py ~/Personales/mi-app --exclude "tests/**" "docs/**"
    python index_codebase.py ~/Personales/mi-app --reset
"""

import argparse
import asyncio
import os
import re
import cocoindex

DEFAULT_EXCLUDED = [
    "node_modules/**",
    ".git/**",
    "build/**",
    "dist/**",
    ".next/**",
    "__pycache__/**",
    "*.min.js",
    "*.lock",
    "*.map",
]

DEFAULT_INCLUDED = [
    "*.ts", "*.tsx", "*.js", "*.jsx",
    "*.py",
    "*.go",
    "*.rs",
    "*.java",
    "*.rb",
    "*.php",
    "*.cs",
    "*.sql",
    "*.md",
]


def slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "_", text).strip("_")


def build_flow(name: str, path: str, included: list[str], excluded: list[str]):
    @cocoindex.flow_def(name=name)
    def _flow(flow_builder: cocoindex.FlowBuilder, data_scope: cocoindex.DataScope):
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
                chunk_size=1000,
                min_chunk_size=300,
                chunk_overlap=300,
            )

            with file["chunks"].row() as chunk:
                chunk["embedding"] = chunk["text"].transform(
                    cocoindex.functions.SentenceTransformerEmbed(
                        model="sentence-transformers/all-MiniLM-L6-v2"
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


async def run(reset: bool):
    all_flows = list(cocoindex.flow.flows().values())
    setup_bundle = await cocoindex.flow.make_setup_bundle_async(all_flows)
    _, is_up_to_date = await setup_bundle.describe_async()
    if not is_up_to_date:
        await setup_bundle.apply_async(report_to_stdout=True)

    stats = await cocoindex.update_all_flows_async(
        cocoindex.FlowLiveUpdaterOptions(
            live_mode=False,
            full_reprocess=reset,
            print_stats=True,
        )
    )
    for name, info in stats.items():
        print(f"\n{name}: {info}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Indexa un codebase con CocoIndex.")
    parser.add_argument("path", help="Ruta al codebase a indexar")
    parser.add_argument(
        "--name", help="Nombre del índice (por defecto: nombre del directorio)"
    )
    parser.add_argument(
        "--include", nargs="+", metavar="PATTERN",
        help="Patrones de archivos a incluir (ej: '*.py' '*.md')"
    )
    parser.add_argument(
        "--exclude", nargs="+", metavar="PATTERN",
        help="Patrones adicionales a excluir"
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Borra el índice existente y lo reconstruye desde cero"
    )
    args = parser.parse_args()

    path = os.path.abspath(args.path)
    if not os.path.isdir(path):
        print(f"Error: '{path}' no es un directorio válido.")
        exit(1)

    name = slugify(args.name or os.path.basename(path))
    included = args.include or DEFAULT_INCLUDED
    excluded = DEFAULT_EXCLUDED + (args.exclude or [])

    print(f"Indexando: {path}")
    print(f"Nombre:    {name}")
    print(f"Incluir:   {', '.join(included)}")
    print(f"Excluir:   {', '.join(excluded)}\n")

    cocoindex.init()
    build_flow(name, path, included, excluded)
    asyncio.run(run(reset=args.reset))
