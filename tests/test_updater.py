from __future__ import annotations

from pathlib import Path

import pytest

from codeindex import updater


def test_is_newer_semver_comparison() -> None:
    assert updater._is_newer("0.1.0", "0.1.1") is True
    assert updater._is_newer("0.2.0", "0.1.9") is False
    assert updater._is_newer("0.1.0", "0.1.0") is False


def test_source_from_repo() -> None:
    assert updater.source_from_repo("owner/repo") == "git+https://github.com/owner/repo.git"


def test_update_notification_uses_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.delenv("CODEINDEX_DISABLE_UPDATE_CHECK", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(updater, "installed_version", lambda: "0.1.0")

    calls: dict[str, int] = {"count": 0}

    def _check(
        repo: str = updater.DEFAULT_REPO,
        timeout_seconds: float = 2.0,
    ) -> updater.VersionStatus:
        calls["count"] += 1
        return updater.VersionStatus(
            current_version="0.1.0",
            latest_version="0.1.1",
            update_available=True,
        )

    monkeypatch.setattr(updater, "check_for_updates", _check)

    first = updater.update_notification(ttl_seconds=3600)
    second = updater.update_notification(ttl_seconds=3600)

    assert "Update available" in str(first)
    assert "0.1.1" in str(second)
    assert calls["count"] == 1
