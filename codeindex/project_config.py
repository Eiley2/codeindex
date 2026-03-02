from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config
from .errors import ConfigurationError

PROJECT_CONFIG_FILENAME = ".codeindex.toml"


@dataclass(frozen=True)
class ProjectConfig:
    source_file: Path | None = None
    index_name: str | None = None
    include_patterns: tuple[str, ...] | None = None
    exclude_patterns: tuple[str, ...] | None = None
    default_reset: bool | None = None
    max_files: int | None = None
    max_file_bytes: int | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    min_chunk_size: int | None = None


def _as_str_tuple(value: Any, key: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigurationError(
            f"'{key}' must be an array of strings in {PROJECT_CONFIG_FILENAME}."
        )
    return tuple(value)


def _as_optional_int(value: Any, key: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int):
        raise ConfigurationError(f"'{key}' must be an integer in {PROJECT_CONFIG_FILENAME}.")
    return value


def _as_optional_bool(value: Any, key: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ConfigurationError(f"'{key}' must be a boolean in {PROJECT_CONFIG_FILENAME}.")
    return value


def _candidate_dirs(start_path: Path | None) -> list[Path]:
    if start_path is None:
        current = Path.cwd().resolve()
    else:
        resolved = start_path.resolve()
        current = resolved if resolved.is_dir() else resolved.parent

    dirs: list[Path] = [current]
    dirs.extend(current.parents)
    return dirs


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationError(f"Invalid TOML in '{path}': {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigurationError(f"Invalid TOML in '{path}': expected root table.")
    return data


def discover(start_path: Path | None = None) -> ProjectConfig:
    config_file: Path | None = None
    for directory in _candidate_dirs(start_path):
        candidate = directory / PROJECT_CONFIG_FILENAME
        if candidate.is_file():
            config_file = candidate
            break

    if config_file is None:
        return ProjectConfig()

    data = _load_toml(config_file)
    index_data = data.get("index", {})
    chunk_data = data.get("chunking", {})
    if not isinstance(index_data, dict):
        raise ConfigurationError(f"'index' must be a table in '{config_file}'.")
    if not isinstance(chunk_data, dict):
        raise ConfigurationError(f"'chunking' must be a table in '{config_file}'.")

    index_name_raw = index_data.get("name")
    if index_name_raw is not None and not isinstance(index_name_raw, str):
        raise ConfigurationError(f"'index.name' must be a string in '{config_file}'.")

    normalized_index_name = (
        config.normalize_index_name(index_name_raw)
        if isinstance(index_name_raw, str) and index_name_raw.strip()
        else None
    )

    return ProjectConfig(
        source_file=config_file,
        index_name=normalized_index_name,
        include_patterns=_as_str_tuple(
            index_data.get("include_patterns"),
            "index.include_patterns",
        ),
        exclude_patterns=_as_str_tuple(
            index_data.get("exclude_patterns"),
            "index.exclude_patterns",
        ),
        default_reset=_as_optional_bool(index_data.get("reset"), "index.reset"),
        max_files=_as_optional_int(index_data.get("max_files"), "index.max_files"),
        max_file_bytes=_as_optional_int(
            index_data.get("max_file_bytes"),
            "index.max_file_bytes",
        ),
        chunk_size=_as_optional_int(chunk_data.get("chunk_size"), "chunking.chunk_size"),
        chunk_overlap=_as_optional_int(
            chunk_data.get("chunk_overlap"),
            "chunking.chunk_overlap",
        ),
        min_chunk_size=_as_optional_int(
            chunk_data.get("min_chunk_size"),
            "chunking.min_chunk_size",
        ),
    )
