from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

PACKAGE_NAME = "codeindex"
DEFAULT_REPO = "Eiley2/codeindex"
DEFAULT_GIT_SOURCE = f"git+https://github.com/{DEFAULT_REPO}.git"
UPDATE_CHECK_TTL_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class VersionStatus:
    current_version: str
    latest_version: str | None
    update_available: bool


def installed_version() -> str:
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        return "0.0.0"


def _parse_version(value: str) -> tuple[int, int, int] | None:
    normalized = value.strip().lstrip("v")
    if not normalized:
        return None
    core = normalized.split("+", maxsplit=1)[0].split("-", maxsplit=1)[0]
    parts = core.split(".")
    if len(parts) < 3:
        return None
    try:
        major, minor, patch = (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None
    return major, minor, patch


def _is_newer(current: str, latest: str) -> bool:
    current_parsed = _parse_version(current)
    latest_parsed = _parse_version(latest)
    if current_parsed is None or latest_parsed is None:
        return False
    return latest_parsed > current_parsed


def _latest_release_api(repo: str) -> str:
    return f"https://api.github.com/repos/{repo}/releases/latest"


def _request_json(url: str, timeout_seconds: float) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "codeindex-update-check",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        return {}
    return payload


def latest_version(repo: str = DEFAULT_REPO, timeout_seconds: float = 2.5) -> str | None:
    try:
        payload = _request_json(_latest_release_api(repo), timeout_seconds)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    tag = payload.get("tag_name")
    if not isinstance(tag, str):
        return None
    return tag.lstrip("v")


def check_for_updates(repo: str = DEFAULT_REPO, timeout_seconds: float = 2.5) -> VersionStatus:
    current = installed_version()
    latest = latest_version(repo=repo, timeout_seconds=timeout_seconds)
    return VersionStatus(
        current_version=current,
        latest_version=latest,
        update_available=bool(latest and _is_newer(current, latest)),
    )


def run_self_update(source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "tool", "install", "--force", "--refresh", source],
        capture_output=True,
        text=True,
        check=True,
    )


def source_from_repo(repo: str) -> str:
    return f"git+https://github.com/{repo}.git"


def _cache_path() -> Path:
    xdg_cache = os.getenv("XDG_CACHE_HOME")
    base = Path(xdg_cache) if xdg_cache else Path.home() / ".cache"
    return base / "codeindex" / "update-check.json"


def _read_cache() -> dict:
    path = _cache_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _write_cache(payload: dict) -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def update_notification(
    repo: str = DEFAULT_REPO,
    ttl_seconds: int = UPDATE_CHECK_TTL_SECONDS,
    timeout_seconds: float = 2.0,
) -> str | None:
    if os.getenv("CODEINDEX_DISABLE_UPDATE_CHECK") == "1":
        return None
    if os.getenv("CI") == "true":
        return None
    if os.getenv("PYTEST_CURRENT_TEST"):
        return None

    current = installed_version()
    now = int(time.time())
    cached = _read_cache()

    cached_checked = cached.get("checked_at")
    cached_current = cached.get("current_version")
    cached_latest = cached.get("latest_version")
    cached_available = cached.get("update_available")

    if (
        isinstance(cached_checked, int)
        and cached_current == current
        and now - cached_checked <= ttl_seconds
    ):
        if cached_available and isinstance(cached_latest, str):
            return (
                f"Update available: {current} -> {cached_latest}. "
                "Run `codeindex update`."
            )
        return None

    try:
        status = check_for_updates(repo=repo, timeout_seconds=timeout_seconds)
    except Exception:
        return None
    _write_cache(
        {
            "checked_at": now,
            "current_version": status.current_version,
            "latest_version": status.latest_version,
            "update_available": status.update_available,
        }
    )

    if status.update_available and status.latest_version is not None:
        return (
            f"Update available: {status.current_version} -> {status.latest_version}. "
            "Run `codeindex update`."
        )
    return None
