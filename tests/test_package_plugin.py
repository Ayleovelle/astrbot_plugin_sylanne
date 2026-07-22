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


@pytest.mark.parametrize(
    "record",
    [
        b"README.md\nunsafe.md\0",
        b"README.md\runsafe.md\0",
        b"../README.md\0",
        b"dir\\README.md\0",
    ],
)
def test_head_tree_query_rejects_unsafe_archive_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    record: bytes,
) -> None:
    monkeypatch.setattr(package_plugin, "ROOT", tmp_path)
    monkeypatch.setattr(
        package_plugin.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=["git", "ls-tree"],
            returncode=0,
            stdout=record,
            stderr=b"",
        ),
    )

    with pytest.raises(RuntimeError, match="HEAD tree path"):
        package_plugin._head_tree_files()


@pytest.mark.parametrize(
    "response",
    [
        b"HEAD:README.md missing\n",
        (b"0" * 40) + b" tree 1\nx\n",
        (b"0" * 40) + b" blob nope\n",
        (b"0" * 40) + b" blob 3\nab\n",
        (b"0" * 40) + b" blob 2\nabX",
        (b"0" * 40) + b" blob 2\nab\ntrailing",
    ],
)
def test_head_blob_batch_rejects_malformed_or_missing_objects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    response: bytes,
) -> None:
    source = tmp_path / "README.md"
    monkeypatch.setattr(package_plugin, "ROOT", tmp_path)
    monkeypatch.setattr(
        package_plugin.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=["git", "cat-file", "--batch"],
            returncode=0,
            stdout=response,
            stderr=b"",
        ),
    )

    with pytest.raises(RuntimeError, match="git cat-file --batch"):
        package_plugin._head_blob_bytes([source])


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
