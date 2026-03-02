from __future__ import annotations

import os
import re

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

DEFAULT_INCLUDED_PATTERNS: list[str] = [
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

DEFAULT_EXCLUDED_PATTERNS: list[str] = [
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

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 300
MIN_CHUNK_SIZE = 300
DEFAULT_TOP_K = 10


def get_database_url() -> str:
    url = os.getenv("COCOINDEX_DATABASE_URL")
    if not url:
        raise EnvironmentError(
            "COCOINDEX_DATABASE_URL environment variable is not set.\n"
            "Example: export COCOINDEX_DATABASE_URL='postgresql://user:password@localhost:5432/cocoindex'"
        )
    return url


def slugify(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "_", name).strip("_")


def table_name(index_name: str) -> str:
    return f"{slugify(index_name).lower()}__code_embeddings"


def tracking_table_suffix() -> str:
    return "__cocoindex_tracking"
