from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from typing import Any

from .errors import ConfigurationError, ValidationError

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
DATABASE_URL_ENV_VAR = "COCOINDEX_DATABASE_URL"
TRACKING_TABLE_SUFFIX = "__cocoindex_tracking"

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


def _default_config_path() -> Path:
    xdg_home = os.getenv("XDG_CONFIG_HOME")
    base_dir = Path(xdg_home) if xdg_home else Path.home() / ".config"
    return base_dir / "codeindex" / "config.toml"


def _read_toml_file(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
            if not isinstance(data, dict):
                raise ConfigurationError(f"Invalid TOML in '{path}': expected a table at root.")
            return data
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationError(f"Invalid TOML in '{path}': {exc}") from exc


def get_database_url(config_path: Path | None = None) -> str:
    url = os.getenv(DATABASE_URL_ENV_VAR)
    if not url:
        conf_path = config_path or _default_config_path()
        data = _read_toml_file(conf_path)
        raw_value = data.get("database_url")
        if raw_value is None:
            nested = data.get("codeindex", {})
            if isinstance(nested, dict):
                raw_value = nested.get("database_url")
        if isinstance(raw_value, str):
            url = raw_value.strip()

    if not url:
        raise ConfigurationError(
            f"{DATABASE_URL_ENV_VAR} is not set and no config file value was found.\n"
            f"Set env var:\n"
            f"  export {DATABASE_URL_ENV_VAR}='postgresql://user:password@localhost:5432/cocoindex'\n"
            f"or create:\n"
            f"  {_default_config_path()}\n"
            f"with:\n"
            f"  database_url = 'postgresql://user:password@localhost:5432/cocoindex'"
        )
    return url


def slugify(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "_", name).strip("_")


def normalize_index_name(name: str) -> str:
    normalized = slugify(name).lower()
    if not normalized:
        raise ValidationError(
            "Index name must contain at least one alphanumeric character."
        )
    return normalized


def table_name(index_name: str) -> str:
    return f"{normalize_index_name(index_name)}__code_embeddings"


def tracking_table_suffix() -> str:
    return TRACKING_TABLE_SUFFIX
