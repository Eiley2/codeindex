from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import find_dotenv, load_dotenv

from .errors import ConfigurationError, ValidationError

DEFAULT_EMBEDDING_PROVIDER = "local"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_OPENROUTER_EMBEDDING_MODEL = "openai/text-embedding-3-small"
EMBEDDING_DIM = 384
DATABASE_URL_ENV_VAR = "COCOINDEX_DATABASE_URL"
EMBEDDING_PROVIDER_ENV_VAR = "COCOINDEX_EMBEDDING_PROVIDER"
EMBEDDING_MODEL_ENV_VAR = "COCOINDEX_EMBEDDING_MODEL"
OPEN_ROUTER_API_KEY_ENV_VAR = "OPEN_ROUTER_API_KEY"
OPENROUTER_API_KEY_ENV_VAR = "OPENROUTER_API_KEY"
TRACKING_TABLE_SUFFIX = "__cocoindex_tracking"
EMBEDDING_BENCHMARK_SOURCE = (
    "https://supermemory.ai/blog/best-open-source-embedding-models-benchmarked-and-ranked/"
)
EMBEDDING_PROVIDERS: tuple[str, ...] = ("local", "openrouter")

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
    ".venv/**",
    "venv/**",
    "env/**",
    ".tox/**",
    ".nox/**",
    "build/**",
    "dist/**",
    ".next/**",
    "__pycache__/**",
    ".mypy_cache/**",
    ".pytest_cache/**",
    ".ruff_cache/**",
    "*.min.js",
    "*.lock",
    "*.map",
]

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 300
MIN_CHUNK_SIZE = 300
DEFAULT_TOP_K = 10


@dataclass(frozen=True)
class EmbeddingModelPreset:
    key: str
    label: str
    provider: str
    model_id: str
    summary: str


EMBEDDING_MODEL_PRESETS: tuple[EmbeddingModelPreset, ...] = (
    EmbeddingModelPreset(
        key="fast",
        label="Fastest / low resource",
        provider="local",
        model_id="sentence-transformers/all-MiniLM-L6-v2",
        summary="Low latency and low memory footprint; good baseline quality.",
    ),
    EmbeddingModelPreset(
        key="balanced",
        label="Balanced quality-speed",
        provider="local",
        model_id="BAAI/bge-base-en-v1.5",
        summary="Strong retrieval quality with moderate resource usage.",
    ),
    EmbeddingModelPreset(
        key="quality",
        label="Highest quality",
        provider="local",
        model_id="intfloat/e5-large-v2",
        summary="Best retrieval quality among common open-source options, heavier model.",
    ),
    EmbeddingModelPreset(
        key="multilingual",
        label="Long context / multilingual",
        provider="local",
        model_id="nomic-ai/nomic-embed-text-v1.5",
        summary="Good multilingual and long-context behavior.",
    ),
)
_PRESET_BY_KEY = {preset.key: preset for preset in EMBEDDING_MODEL_PRESETS}


def _default_config_path() -> Path:
    xdg_home = os.getenv("XDG_CONFIG_HOME")
    base_dir = Path(xdg_home) if xdg_home else Path.home() / ".config"
    return base_dir / "codeindex" / "config.toml"


def default_config_path() -> Path:
    return _default_config_path()


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


def _resolve_env_value(env_var: str) -> tuple[str | None, str]:
    source = f"env:{env_var}"
    existing = os.getenv(env_var)
    if not existing:
        dotenv_path = find_dotenv(usecwd=True)
        if dotenv_path:
            load_dotenv(dotenv_path, override=False)
            if os.getenv(env_var):
                source = f".env:{dotenv_path}"
    return os.getenv(env_var), source


def _config_value(data: dict[str, Any], key: str) -> Any:
    raw = data.get(key)
    if raw is None:
        nested = data.get("codeindex", {})
        if isinstance(nested, dict):
            raw = nested.get(key)
    return raw


def get_database_url(config_path: Path | None = None) -> str:
    url, _ = resolve_database_url(config_path=config_path)
    return url


def resolve_database_url(config_path: Path | None = None) -> tuple[str, str]:
    url, env_source = _resolve_env_value(DATABASE_URL_ENV_VAR)
    if not url:
        conf_path = config_path or _default_config_path()
        data = _read_toml_file(conf_path)
        raw_value = _config_value(data, "database_url")
        if isinstance(raw_value, str):
            url = raw_value.strip()
            if url:
                return url, f"config:{conf_path}"

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
    return url, env_source


def validate_embedding_model_name(model_name: str) -> str:
    cleaned = model_name.strip()
    if not cleaned:
        raise ValidationError("Embedding model cannot be empty.")
    return cleaned


def validate_embedding_provider(provider: str) -> str:
    cleaned = provider.strip().lower()
    if cleaned not in EMBEDDING_PROVIDERS:
        expected = ", ".join(EMBEDDING_PROVIDERS)
        raise ValidationError(
            f"Embedding provider '{provider}' is invalid. Expected one of: {expected}."
        )
    return cleaned


def default_embedding_model_for_provider(provider: str) -> str:
    normalized_provider = validate_embedding_provider(provider)
    if normalized_provider == "openrouter":
        return DEFAULT_OPENROUTER_EMBEDDING_MODEL
    return DEFAULT_EMBEDDING_MODEL


def resolve_embedding_provider(
    explicit_provider: str | None = None,
    config_path: Path | None = None,
) -> tuple[str, str]:
    if explicit_provider is not None:
        return validate_embedding_provider(explicit_provider), "explicit"

    env_provider, env_source = _resolve_env_value(EMBEDDING_PROVIDER_ENV_VAR)
    if env_provider:
        return validate_embedding_provider(env_provider), env_source

    conf_path = config_path or _default_config_path()
    data = _read_toml_file(conf_path)
    raw_value = _config_value(data, "embedding_provider")
    if isinstance(raw_value, str) and raw_value.strip():
        return validate_embedding_provider(raw_value), f"config:{conf_path}"

    return DEFAULT_EMBEDDING_PROVIDER, "default"


def get_embedding_model_preset(key: str) -> EmbeddingModelPreset:
    preset = _PRESET_BY_KEY.get(key)
    if preset is None:
        allowed = ", ".join(_PRESET_BY_KEY)
        raise ValidationError(f"Invalid preset '{key}'. Expected one of: {allowed}.")
    return preset


def resolve_embedding_model(
    explicit_model: str | None = None,
    config_path: Path | None = None,
    provider: str | None = None,
) -> tuple[str, str]:
    if explicit_model is not None:
        return validate_embedding_model_name(explicit_model), "explicit"

    env_model, env_source = _resolve_env_value(EMBEDDING_MODEL_ENV_VAR)
    if env_model:
        return validate_embedding_model_name(env_model), env_source

    conf_path = config_path or _default_config_path()
    data = _read_toml_file(conf_path)
    raw_value = _config_value(data, "embedding_model")
    if isinstance(raw_value, str) and raw_value.strip():
        return validate_embedding_model_name(raw_value), f"config:{conf_path}"

    effective_provider = provider
    if effective_provider is None:
        effective_provider, _ = resolve_embedding_provider(config_path=config_path)
    default_model = default_embedding_model_for_provider(effective_provider)
    return default_model, f"default:{effective_provider}"


def resolve_embedding(
    explicit_provider: str | None = None,
    explicit_model: str | None = None,
    config_path: Path | None = None,
) -> tuple[str, str]:
    provider, _ = resolve_embedding_provider(
        explicit_provider=explicit_provider,
        config_path=config_path,
    )
    model, _ = resolve_embedding_model(
        explicit_model=explicit_model,
        config_path=config_path,
        provider=provider,
    )
    return provider, model


def get_default_embedding_provider(config_path: Path | None = None) -> str:
    provider, _ = resolve_embedding_provider(config_path=config_path)
    return provider


def get_default_embedding_model(config_path: Path | None = None) -> str:
    provider, _ = resolve_embedding_provider(config_path=config_path)
    model, _ = resolve_embedding_model(config_path=config_path, provider=provider)
    return model


def require_embedding_provider_credentials(provider: str) -> None:
    normalized_provider = validate_embedding_provider(provider)
    if normalized_provider != "openrouter":
        return

    if os.getenv(OPEN_ROUTER_API_KEY_ENV_VAR) or os.getenv(OPENROUTER_API_KEY_ENV_VAR):
        return
    raise ConfigurationError(
        "OpenRouter embedding provider requires OPEN_ROUTER_API_KEY "
        "(or OPENROUTER_API_KEY) to be set."
    )


def slugify(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "_", name).strip("_")


def normalize_index_name(name: str) -> str:
    normalized = slugify(name).lower()
    if not normalized:
        raise ValidationError(
            "Index name must contain at least one alphanumeric character."
        )
    if normalized[0].isdigit():
        normalized = f"_{normalized}"
    return normalized


def table_name(index_name: str) -> str:
    return f"{normalize_index_name(index_name)}__code_embeddings"


def tracking_table_suffix() -> str:
    return TRACKING_TABLE_SUFFIX
