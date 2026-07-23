"""Release packaging must fail closed around machine-local artifacts."""

from __future__ import annotations

import os
import subprocess
import stat
from pathlib import Path

import pytest

from scripts import package_plugin


def _git(
    root: Path,
    *args: str,
    input_data: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        input=input_data,
        capture_output=True,
        check=True,
    )


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
            stdout=b"",
            stderr=b"",
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
            stdout=b"100644 blob " + (b"0" * 40) + b"\t" + record,
            stderr=b"",
        ),
    )

    with pytest.raises(RuntimeError, match="Git path"):
        package_plugin._head_tree_files()


@pytest.mark.parametrize(
    ("response", "checked_size"),
    [
        (b"HEAD:README.md missing\n", 2),
        ((b"0" * 40) + b" tree 1\nx\n", 1),
        ((b"0" * 40) + b" blob nope\n", 2),
        ((b"0" * 40) + b" blob 3\nab\n", 3),
        ((b"0" * 40) + b" blob 2\nabX", 2),
        ((b"0" * 40) + b" blob 2\nab\ntrailing", 2),
    ],
)
def test_head_blob_batch_rejects_malformed_or_missing_objects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    response: bytes,
    checked_size: int,
) -> None:
    oid = "0" * 40

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del kwargs
        stdout = (
            f"{oid} blob {checked_size}\n".encode("ascii")
            if "--batch-check" in args
            else response
        )
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr=b"")

    monkeypatch.setattr(package_plugin, "ROOT", tmp_path)
    monkeypatch.setattr(package_plugin.subprocess, "run", run)

    with pytest.raises(RuntimeError, match="git cat-file --batch"):
        package_plugin._head_blob_bytes(
            [package_plugin.HeadTreeEntry("README.md", "100644", oid)]
        )


@pytest.mark.parametrize(
    ("mode", "tree_path", "expected"),
    [
        ("120000", "README.md", "symlink"),
        ("160000", "UI/vendor", "gitlink"),
    ],
)
def test_head_tree_rejects_non_regular_entries_without_filesystem_symlinks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mode: str,
    tree_path: str,
    expected: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.name", "Packaging Test")
    _git(repo, "config", "user.email", "packaging-test@example.invalid")
    (repo / "anchor.txt").write_bytes(b"anchor\n")
    _git(repo, "add", "anchor.txt")
    _git(repo, "commit", "--quiet", "-m", "anchor")

    if mode == "120000":
        object_id = _git(repo, "hash-object", "-w", "--stdin", input_data=b"target\n").stdout
    else:
        object_id = _git(repo, "rev-parse", "HEAD").stdout
    oid = object_id.decode("ascii").strip()
    _git(repo, "update-index", "--add", "--cacheinfo", f"{mode},{oid},{tree_path}")
    _git(repo, "commit", "--quiet", "-m", f"add {mode}")
    commit = _git(repo, "rev-parse", "HEAD").stdout.decode("ascii").strip()

    monkeypatch.setattr(package_plugin, "ROOT", repo)
    with pytest.raises(RuntimeError, match=expected):
        package_plugin._head_tree_files(commit)


def test_head_tree_keeps_regular_entries_as_distinct_lexical_identities(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    oid_a = b"1" * 40
    oid_b = b"2" * 40
    listing = (
        b"100644 blob " + oid_a + b"\tUI/index.html\0"
        b"100644 blob " + oid_b + b"\tpages/index.html\0"
    )
    monkeypatch.setattr(package_plugin, "ROOT", tmp_path)
    monkeypatch.setattr(
        package_plugin.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=["git", "ls-tree"],
            returncode=0,
            stdout=listing,
            stderr=b"",
        ),
    )

    entries = package_plugin._head_tree_files("0" * 40)

    assert [(entry.relative_path, entry.oid) for entry in entries] == [
        ("UI/index.html", oid_a.decode("ascii")),
        ("pages/index.html", oid_b.decode("ascii")),
    ]


def test_selected_entry_limit_is_enforced_before_blob_queries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(package_plugin, "ROOT", tmp_path)
    monkeypatch.setattr(package_plugin, "MAX_SELECTED_ENTRIES", 2)
    entries = [
        package_plugin.HeadTreeEntry(f"UI/file-{index}.js", "100644", f"{index + 1:040x}")
        for index in range(3)
    ]
    monkeypatch.setattr(package_plugin, "_head_tree_files", lambda revision: entries)

    with pytest.raises(RuntimeError, match="selected entry count"):
        package_plugin.collect_files(revision="0" * 40)


@pytest.mark.parametrize(
    ("sizes", "single_limit", "total_limit", "expected"),
    [
        ([6], 5, 100, "single HEAD blob"),
        ([8, 8], 10, 15, "total HEAD blob"),
    ],
)
def test_head_blob_limits_reject_during_batch_check_before_content_capture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sizes: list[int],
    single_limit: int,
    total_limit: int,
    expected: str,
) -> None:
    monkeypatch.setattr(package_plugin, "ROOT", tmp_path)
    monkeypatch.setattr(package_plugin, "MAX_HEAD_BLOB_BYTES", single_limit)
    monkeypatch.setattr(package_plugin, "MAX_TOTAL_HEAD_BLOB_BYTES", total_limit)
    entries = [
        package_plugin.HeadTreeEntry(f"UI/file-{index}.js", "100644", f"{index + 1:040x}")
        for index in range(len(sizes))
    ]
    calls: list[list[str]] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del kwargs
        calls.append(args)
        if "--batch-check" not in args:
            raise AssertionError("content batch must not run after an oversized batch-check")
        output = b"".join(
            f"{entry.oid} blob {size}\n".encode("ascii")
            for entry, size in zip(entries, sizes, strict=True)
        )
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=output, stderr=b"")

    monkeypatch.setattr(package_plugin.subprocess, "run", run)

    with pytest.raises(RuntimeError, match=expected):
        package_plugin._head_blob_bytes(entries)

    assert len(calls) == 1
    assert "--batch-check" in calls[0]


def test_metadata_override_must_be_a_bounded_regular_non_symlink_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    directory = tmp_path / "directory"
    directory.mkdir()
    with pytest.raises(RuntimeError, match="regular file"):
        package_plugin._read_metadata_override(directory)

    oversized = tmp_path / "oversized.yaml"
    oversized.write_bytes(b"12345")
    monkeypatch.setattr(package_plugin, "MAX_METADATA_OVERRIDE_BYTES", 4)
    with pytest.raises(RuntimeError, match="metadata override.*bytes"):
        package_plugin._read_metadata_override(oversized)

    symlink_probe = tmp_path / "symlink.yaml"
    symlink_probe.write_bytes(b"x")
    real_lstat = package_plugin.os.lstat

    def fake_lstat(path: object) -> os.stat_result:
        if Path(path) == symlink_probe:
            values = [0] * 10
            values[stat.ST_MODE] = stat.S_IFLNK | 0o777
            values[stat.ST_SIZE] = 1
            return os.stat_result(values)
        return real_lstat(path)

    monkeypatch.setattr(package_plugin.os, "lstat", fake_lstat)
    with pytest.raises(RuntimeError, match="symlink"):
        package_plugin._read_metadata_override(symlink_probe)


def test_dirty_path_query_uses_the_captured_commit_and_lexical_nul_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    commit = "a" * 40
    calls: list[list[str]] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del kwargs
        calls.append(args)
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=b"main.py\0UI/new.js\0pages/deleted.js\0",
            stderr=b"",
        )

    monkeypatch.setattr(package_plugin, "ROOT", tmp_path)
    monkeypatch.setattr(package_plugin.subprocess, "run", run)

    assert package_plugin._paths_differing_from_revision(commit) == {
        "main.py",
        "UI/new.js",
        "pages/deleted.js",
    }
    assert calls == [["git", "diff", "--name-only", "-z", commit, "--"]]


def test_dirty_path_query_reports_modify_staged_add_and_staged_delete(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / "UI").mkdir(parents=True)
    (repo / "pages").mkdir()
    (repo / "README.md").write_bytes(b"before\n")
    (repo / "pages" / "deleted.js").write_bytes(b"delete me\n")
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.name", "Packaging Test")
    _git(repo, "config", "user.email", "packaging-test@example.invalid")
    _git(repo, "add", ".")
    _git(repo, "commit", "--quiet", "-m", "fixture")
    commit = _git(repo, "rev-parse", "HEAD").stdout.decode("ascii").strip()

    (repo / "README.md").write_bytes(b"after\n")
    (repo / "UI" / "new.js").write_bytes(b"new\n")
    _git(repo, "add", "UI/new.js")
    _git(repo, "rm", "--quiet", "pages/deleted.js")

    monkeypatch.setattr(package_plugin, "ROOT", repo)
    assert package_plugin._paths_differing_from_revision(commit) == {
        "README.md",
        "UI/new.js",
        "pages/deleted.js",
    }


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
