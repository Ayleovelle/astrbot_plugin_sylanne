"""Release packaging must fail closed around machine-local artifacts."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts import package_plugin


def test_tracked_file_query_failure_aborts_packaging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        del args, kwargs
        raise subprocess.CalledProcessError(128, ["git", "ls-files", "-z"])

    monkeypatch.setattr(package_plugin.subprocess, "run", _fail)

    with pytest.raises(RuntimeError, match="git ls-files"):
        package_plugin._tracked_files()


def test_empty_tracked_file_query_aborts_packaging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        package_plugin.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=["git", "ls-files", "-z"],
            returncode=0,
            stdout="",
            stderr="",
        ),
    )

    with pytest.raises(RuntimeError, match="empty file list"):
        package_plugin._tracked_files()


@pytest.mark.parametrize("filename", ["_identity.json", "_identity.json.tmp"])
def test_machine_local_identity_is_always_excluded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    filename: str,
) -> None:
    monkeypatch.setattr(package_plugin, "ROOT", tmp_path)
    identity = (
        tmp_path
        / "sylanne_alpha"
        / "_engine"
        / "sylanne_core"
        / filename
    )

    assert package_plugin.should_include(identity) is False
