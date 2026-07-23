"""Release packaging must fail closed around machine-local artifacts."""

from __future__ import annotations

import os
import subprocess
import stat
from pathlib import Path

import pytest

from scripts import package_plugin


class _ChunkedStdout:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = iter(chunks)

    def read(self, size: int) -> bytes:
        del size
        return next(self._chunks, b"")


class _FakeGitProcess:
    def __init__(self, chunks: list[bytes], *, returncode: int = 0) -> None:
        self.stdout = _ChunkedStdout(chunks)
        self._returncode = returncode
        self.killed = False
        self.waited = False

    def kill(self) -> None:
        self.killed = True

    def wait(self) -> int:
        self.waited = True
        return self._returncode

    def poll(self) -> int | None:
        return self._returncode if self.waited else None


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
    def _fail(*args: object, **kwargs: object) -> _FakeGitProcess:
        del args, kwargs
        raise OSError("spawn failed")

    monkeypatch.setattr(package_plugin.subprocess, "Popen", _fail)

    with pytest.raises(RuntimeError, match="git ls-files"):
        package_plugin._tracked_files()


def test_empty_tracked_file_query_aborts_packaging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        package_plugin.subprocess,
        "Popen",
        lambda *args, **kwargs: _FakeGitProcess([b""]),
    )

    with pytest.raises(RuntimeError, match="empty file list"):
        package_plugin._tracked_files()


def test_tracked_file_query_is_scoped_to_v3_source_dirs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def popen(args: list[str], **kwargs: object) -> _FakeGitProcess:
        del kwargs
        calls.append(args)
        return _FakeGitProcess([b"sylanne_alpha/v3core/probe.py\0"])

    monkeypatch.setattr(package_plugin.subprocess, "Popen", popen)

    assert package_plugin._tracked_files() == {"sylanne_alpha/v3core/probe.py"}
    assert calls == [["git", "ls-files", "-z", "--", *package_plugin.V3_SOURCE_DIRS]]


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
        "Popen",
        lambda *args, **kwargs: _FakeGitProcess(
            [b"100644 blob " + (b"0" * 40) + b"\t" + record]
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
        "Popen",
        lambda *args, **kwargs: _FakeGitProcess([listing]),
    )

    entries = package_plugin._head_tree_files("0" * 40)

    assert [(entry.relative_path, entry.oid) for entry in entries] == [
        ("UI/index.html", oid_a.decode("ascii")),
        ("pages/index.html", oid_b.decode("ascii")),
    ]


@pytest.mark.parametrize(
    ("chunks", "max_bytes", "max_records", "expected"),
    [
        ([b"abcdef\0"], 6, 10, "byte"),
        ([b"a\0b\0c\0"], 100, 2, "record"),
    ],
)
def test_bounded_nul_reader_kills_and_waits_before_excess_accumulation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    chunks: list[bytes],
    max_bytes: int,
    max_records: int,
    expected: str,
) -> None:
    process = _FakeGitProcess(chunks)
    monkeypatch.setattr(package_plugin, "ROOT", tmp_path)
    monkeypatch.setattr(package_plugin.subprocess, "Popen", lambda *args, **kwargs: process)

    with pytest.raises(RuntimeError, match=expected):
        package_plugin._git_nul_records(
            ["ls-tree", "-r", "-z", "0" * 40, "--", "README.md"],
            max_bytes=max_bytes,
            max_records=max_records,
        )

    assert process.killed is True
    assert process.waited is True


@pytest.mark.parametrize(
    ("chunks", "returncode", "expected"),
    [
        ([b"unterminated"], 0, "non-NUL-terminated"),
        ([b"valid\0"], 128, "exited with 128"),
    ],
)
def test_bounded_nul_reader_fails_closed_on_malformed_or_failed_process(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    chunks: list[bytes],
    returncode: int,
    expected: str,
) -> None:
    process = _FakeGitProcess(chunks, returncode=returncode)
    monkeypatch.setattr(package_plugin, "ROOT", tmp_path)
    monkeypatch.setattr(package_plugin.subprocess, "Popen", lambda *args, **kwargs: process)

    with pytest.raises(RuntimeError, match=expected):
        package_plugin._git_nul_records(
            ["ls-files", "-z", "--", *package_plugin.V3_SOURCE_DIRS],
            max_bytes=100,
            max_records=10,
        )

    assert process.waited is True


def test_head_tree_query_uses_only_release_allowlist_pathspecs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    oid = b"1" * 40
    listing = b"100644 blob " + oid + b"\tREADME.md\0"
    popen_calls: list[list[str]] = []

    def popen(args: list[str], **kwargs: object) -> _FakeGitProcess:
        del kwargs
        popen_calls.append(args)
        return _FakeGitProcess([listing])

    monkeypatch.setattr(package_plugin, "ROOT", tmp_path)
    monkeypatch.setattr(package_plugin.subprocess, "Popen", popen)

    entries = package_plugin._head_tree_files("0" * 40)

    assert [entry.relative_path for entry in entries] == ["README.md"]
    command = popen_calls[0][1:]
    pathspecs = command[command.index("--") + 1 :]
    assert set(package_plugin.INCLUDE_ROOT_FILES) <= set(pathspecs)
    assert set(package_plugin.INCLUDE_DIRS) <= set(pathspecs)
    assert "tests" not in pathspecs
    assert "scripts" not in pathspecs
    assert "docs" not in pathspecs


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


def test_metadata_override_rejects_hardlink_alias_of_tracked_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    tracked_metadata = plugin_root / "metadata.yaml"
    tracked_metadata.write_bytes(b'version: "2.5.0"\n')
    _git(plugin_root, "init", "--quiet")
    _git(plugin_root, "config", "user.name", "Packaging Test")
    _git(plugin_root, "config", "user.email", "packaging-test@example.invalid")
    _git(plugin_root, "add", "metadata.yaml")
    _git(plugin_root, "commit", "--quiet", "-m", "track metadata")
    alias = tmp_path / "metadata-hardlink.yaml"
    os.link(tracked_metadata, alias)
    assert os.path.samefile(tracked_metadata, alias)

    monkeypatch.setattr(package_plugin, "ROOT", plugin_root)
    with pytest.raises(RuntimeError, match="same file|hardlink|alias"):
        package_plugin._read_metadata_override(alias)


def test_metadata_override_rejects_parent_symlink_alias_of_tracked_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    tracked_metadata = plugin_root / "metadata.yaml"
    tracked_metadata.write_bytes(b'version: "2.5.0"\n')
    alias_parent = tmp_path / "plugin-alias"
    try:
        alias_parent.symlink_to(plugin_root, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink unavailable: {exc}")
    alias = alias_parent / "metadata.yaml"
    assert os.path.samefile(tracked_metadata, alias)

    monkeypatch.setattr(package_plugin, "ROOT", plugin_root)
    with pytest.raises(RuntimeError, match="same file|hardlink|alias"):
        package_plugin._read_metadata_override(alias)


def test_dirty_path_query_uses_the_captured_commit_and_lexical_nul_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    commit = "a" * 40
    calls: list[list[str]] = []

    def popen(args: list[str], **kwargs: object) -> _FakeGitProcess:
        del kwargs
        calls.append(args)
        return _FakeGitProcess([b"main.py\0UI/new.js\0pages/deleted.js\0"])

    monkeypatch.setattr(package_plugin, "ROOT", tmp_path)
    monkeypatch.setattr(package_plugin.subprocess, "Popen", popen)

    assert package_plugin._paths_differing_from_revision(commit) == {
        "main.py",
        "UI/new.js",
        "pages/deleted.js",
    }
    assert calls[0][:6] == ["git", "diff", "--name-only", "-z", commit, "--"]
    assert set(package_plugin.INCLUDE_ROOT_FILES) <= set(calls[0][6:])


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
