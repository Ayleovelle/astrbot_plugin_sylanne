"""Release packaging must fail closed around machine-local artifacts."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import stat
import struct
import sys
import zipfile
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


@pytest.mark.parametrize(
    ("raw_metadata", "expected"),
    [
        (b"version: 2.5.0\n", "2.5.0"),
        (b"version: '2.5.0'\n", "2.5.0"),
        (b'version: "2.5.0"\n', "2.5.0"),
        (b"version: 2.5.0-grey.7\n", "2.5.0-grey.7"),
        (b"version: '2.5.0-grey.7'\n", "2.5.0-grey.7"),
        (b'version: "2.5.0-grey.7"\n', "2.5.0-grey.7"),
    ],
)
def test_read_metadata_version_accepts_exact_release_scalars(
    raw_metadata: bytes,
    expected: str,
) -> None:
    assert package_plugin._read_metadata_version(raw_metadata) == expected


@pytest.mark.parametrize(
    "raw_metadata",
    [
        b"""version: "'2.5.0'"\n""",
        b"""version: '"2.5.0"'\n""",
        b'version: "2.5.0\n',
        b"version: '2.5.0\n",
        b'version: 2.5.0"\n',
        b"version: 2.5.0'\n",
        b'version: ""2.5.0""\n',
        b"version: ''2.5.0''\n",
        b'version: "2.5.0" trailing\n',
        b"version: 2.5.0 trailing\n",
        b'version: "2.5.0" # comment\n',
    ],
)
def test_read_metadata_version_rejects_ambiguous_or_trailing_syntax(
    raw_metadata: bytes,
) -> None:
    with pytest.raises(RuntimeError, match="version|quote|syntax"):
        package_plugin._read_metadata_version(raw_metadata)


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


def _stub_minimal_package_build(
    monkeypatch: pytest.MonkeyPatch,
    plugin_root: Path,
    *,
    tracked_sources: set[str] | None = None,
) -> None:
    main_data = (
        b'PLUGIN_VERSION = "2.5.0"\n'
        b'@register("probe", "2718 Labs", "probe", "2.5.0", "https://example.invalid")\n'
        b"class Plugin:\n"
        b"    pass\n"
    )
    entries = [
        (f"{package_plugin.PLUGIN_NAME}/", b""),
        (package_plugin.MAIN_ARCNAME, main_data),
        (package_plugin.METADATA_ARCNAME, b'version: "2.5.0"\n'),
        (package_plugin.BUILD_FLAGS_ARCNAME, b"# generated flags\n"),
    ]

    monkeypatch.setattr(package_plugin, "ROOT", plugin_root)
    monkeypatch.setattr(package_plugin, "_head_commit", lambda: "a" * 40)
    monkeypatch.setattr(package_plugin, "_tracked_files", set)
    monkeypatch.setattr(package_plugin, "_untracked_v3_sources", lambda tracked: [])
    monkeypatch.setattr(
        package_plugin,
        "_tracked_source_paths",
        lambda: tracked_sources or set(),
        raising=False,
    )
    monkeypatch.setattr(
        package_plugin,
        "_archive_entries",
        lambda *args, **kwargs: entries,
    )


@pytest.mark.parametrize(
    "relative_output",
    [
        Path("README.md"),
        Path("readME.md"),
        Path("dist") / ".." / "README.md",
    ],
)
def test_output_may_not_overwrite_a_release_input(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    relative_output: Path,
) -> None:
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    readme = plugin_root / "README.md"
    original = b"# keep this tracked release input\n"
    readme.write_bytes(original)
    _stub_minimal_package_build(monkeypatch, plugin_root)

    with pytest.raises(RuntimeError, match="output|release input|dist"):
        package_plugin.build_package(plugin_root / relative_output, channel="stable")

    assert readme.read_bytes() == original


def test_dist_output_rejects_hardlink_alias_of_tracked_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugin"
    dist = plugin_root / "dist"
    dist.mkdir(parents=True)
    readme = plugin_root / "README.md"
    original = b"# tracked source must survive\n"
    readme.write_bytes(original)
    output = dist / "probe.zip"
    os.link(readme, output)
    assert os.path.samefile(readme, output)
    _stub_minimal_package_build(
        monkeypatch,
        plugin_root,
        tracked_sources={"README.md"},
    )

    with pytest.raises(RuntimeError, match="same file|hardlink|alias|tracked"):
        package_plugin.build_package(output, channel="stable")

    assert readme.read_bytes() == original


def test_external_output_rejects_hardlink_alias_of_tracked_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    readme = plugin_root / "README.md"
    original = b"# tracked source must survive\n"
    readme.write_bytes(original)
    output = tmp_path / "external-probe.zip"
    os.link(readme, output)
    assert os.path.samefile(readme, output)
    _stub_minimal_package_build(
        monkeypatch,
        plugin_root,
        tracked_sources={"README.md"},
    )

    with pytest.raises(RuntimeError, match="same file|hardlink|alias|tracked"):
        package_plugin.build_package(output, channel="stable")

    assert readme.read_bytes() == original


def test_root_artifact_rejects_hardlink_alias_of_other_tracked_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    readme = plugin_root / "README.md"
    original = b"# tracked source must survive\n"
    readme.write_bytes(original)
    output = plugin_root / f"{package_plugin.PLUGIN_NAME}.zip"
    os.link(readme, output)
    assert os.path.samefile(readme, output)
    _stub_minimal_package_build(
        monkeypatch,
        plugin_root,
        tracked_sources={"README.md", f"{package_plugin.PLUGIN_NAME}.zip"},
    )

    with pytest.raises(RuntimeError, match="same file|hardlink|alias|tracked"):
        package_plugin.build_package(output, channel="stable")

    assert readme.read_bytes() == original


def test_root_artifact_may_replace_its_tracked_checksum_sidecar(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    output = plugin_root / f"{package_plugin.PLUGIN_NAME}.zip"
    checksum = output.parent / f"{output.name}.sha256"
    output.write_bytes(b"old package")
    checksum.write_text("old checksum\n", encoding="utf-8")
    monkeypatch.setattr(package_plugin, "ROOT", plugin_root)

    package_plugin._validate_output_targets(
        output,
        checksum,
        {
            f"{package_plugin.PLUGIN_NAME}.zip",
            f"{package_plugin.PLUGIN_NAME}.zip.sha256",
        },
        None,
    )


def test_root_artifact_self_exception_does_not_exempt_metadata_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    output = plugin_root / f"{package_plugin.PLUGIN_NAME}.zip"
    output.write_bytes(b'version: "2.5.0"\n')
    checksum = output.parent / f"{output.name}.sha256"
    monkeypatch.setattr(package_plugin, "ROOT", plugin_root)

    with pytest.raises(RuntimeError, match="release input|metadata|alias"):
        package_plugin._validate_output_targets(
            output,
            checksum,
            {f"{package_plugin.PLUGIN_NAME}.zip"},
            output,
        )


def test_checksum_sidecar_rejects_hardlink_alias_of_tracked_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugin"
    dist = plugin_root / "dist"
    dist.mkdir(parents=True)
    readme = plugin_root / "README.md"
    original = b"# tracked source must survive\n"
    readme.write_bytes(original)
    output = dist / "probe.zip"
    checksum = dist / "probe.zip.sha256"
    os.link(readme, checksum)
    assert os.path.samefile(readme, checksum)
    _stub_minimal_package_build(
        monkeypatch,
        plugin_root,
        tracked_sources={"README.md"},
    )

    with pytest.raises(RuntimeError, match="checksum|same file|hardlink|alias|tracked"):
        package_plugin.build_package(output, channel="stable")

    assert not output.exists()
    assert readme.read_bytes() == original


def _create_directory_alias(alias: Path, target: Path) -> None:
    try:
        alias.symlink_to(target, target_is_directory=True)
        return
    except OSError as symlink_error:
        if os.name != "nt":
            pytest.skip(f"directory symlink unavailable: {symlink_error}")
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(alias), str(target)],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(
            f"directory symlink/junction unavailable (exit {result.returncode})"
        )


def test_dist_parent_alias_may_not_resolve_to_a_tracked_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugin"
    ui = plugin_root / "UI"
    ui.mkdir(parents=True)
    source = ui / "index.html"
    original = b"tracked UI bytes\n"
    source.write_bytes(original)
    dist_alias = plugin_root / "dist"
    _create_directory_alias(dist_alias, ui)
    _stub_minimal_package_build(
        monkeypatch,
        plugin_root,
        tracked_sources={"UI/index.html"},
    )

    try:
        with pytest.raises(RuntimeError, match="resolve|same file|alias|tracked"):
            package_plugin.build_package(dist_alias / "index.html", channel="stable")
        assert source.read_bytes() == original
    finally:
        if dist_alias.is_symlink():
            dist_alias.unlink()
        elif dist_alias.exists():
            dist_alias.rmdir()


def test_external_parent_alias_may_not_resolve_to_a_tracked_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugin"
    ui = plugin_root / "UI"
    ui.mkdir(parents=True)
    source = ui / "index.html"
    original = b"tracked UI bytes\n"
    source.write_bytes(original)
    external_alias = tmp_path / "external-output"
    _create_directory_alias(external_alias, ui)
    _stub_minimal_package_build(
        monkeypatch,
        plugin_root,
        tracked_sources={"UI/index.html"},
    )

    try:
        with pytest.raises(RuntimeError, match="resolve|same file|alias|tracked"):
            package_plugin.build_package(
                external_alias / "index.html",
                channel="stable",
            )
        assert source.read_bytes() == original
    finally:
        if external_alias.is_symlink():
            external_alias.unlink()
        elif external_alias.exists():
            external_alias.rmdir()


def test_repo_dist_alias_may_not_leave_the_output_area(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    dist_alias = plugin_root / "dist"
    _create_directory_alias(dist_alias, outside)
    _stub_minimal_package_build(monkeypatch, plugin_root)

    try:
        with pytest.raises(RuntimeError, match="symlink|junction|allowed"):
            package_plugin.build_package(dist_alias / "probe.zip", channel="stable")
        assert not (outside / "probe.zip").exists()
    finally:
        if dist_alias.is_symlink():
            dist_alias.unlink()
        elif dist_alias.exists():
            dist_alias.rmdir()


def test_pair_commit_rolls_back_both_old_files_when_checksum_replace_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugin"
    dist = plugin_root / "dist"
    dist.mkdir(parents=True)
    output = dist / "probe.zip"
    checksum = dist / "probe.zip.sha256"
    old_output = b"old zip bytes\n"
    old_checksum = b"old checksum bytes\n"
    output.write_bytes(old_output)
    checksum.write_bytes(old_checksum)
    _stub_minimal_package_build(monkeypatch, plugin_root)

    real_replace = os.replace
    injected = False

    def fail_checksum_install(src: object, dst: object) -> None:
        nonlocal injected
        if Path(dst) == checksum and not injected:
            injected = True
            raise OSError("injected checksum replace failure")
        real_replace(src, dst)

    monkeypatch.setattr(package_plugin.os, "replace", fail_checksum_install)

    with pytest.raises(RuntimeError, match="commit|replace|rollback"):
        package_plugin.build_package(output, channel="stable")

    assert injected
    assert output.read_bytes() == old_output
    assert checksum.read_bytes() == old_checksum


def test_incomplete_rollback_preserves_the_only_old_output_backup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugin"
    dist = plugin_root / "dist"
    dist.mkdir(parents=True)
    output = dist / "probe.zip"
    checksum = dist / "probe.zip.sha256"
    old_output = b"irreplaceable old zip\n"
    old_checksum = b"old checksum\n"
    output.write_bytes(old_output)
    checksum.write_bytes(old_checksum)
    _stub_minimal_package_build(monkeypatch, plugin_root)

    real_replace = os.replace
    checksum_install_failed = False

    def fail_install_then_output_restore(src: object, dst: object) -> None:
        nonlocal checksum_install_failed
        source = Path(src)
        destination = Path(dst)
        if destination == checksum and not checksum_install_failed:
            checksum_install_failed = True
            raise OSError("injected checksum install failure")
        if (
            destination == output
            and checksum_install_failed
            and source.name.endswith(".zip-backup.tmp")
        ):
            raise OSError("injected output rollback failure")
        real_replace(src, dst)

    monkeypatch.setattr(
        package_plugin.os,
        "replace",
        fail_install_then_output_restore,
    )

    with pytest.raises(
        RuntimeError,
        match="incomplete.*preserv|preserv.*backup",
    ) as excinfo:
        package_plugin.build_package(output, channel="stable")

    backups = list(dist.glob(".probe.zip.*.zip-backup.tmp"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == old_output
    assert str(backups[0]) in str(excinfo.value)
    assert checksum.read_bytes() == old_checksum


def test_pair_commit_rolls_back_on_non_oserror_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugin"
    dist = plugin_root / "dist"
    dist.mkdir(parents=True)
    output = dist / "probe.zip"
    checksum = dist / "probe.zip.sha256"
    old_output = b"old zip bytes\n"
    old_checksum = b"old checksum bytes\n"
    output.write_bytes(old_output)
    checksum.write_bytes(old_checksum)
    _stub_minimal_package_build(monkeypatch, plugin_root)

    real_replace = os.replace
    injected = False

    def fail_checksum_install(src: object, dst: object) -> None:
        nonlocal injected
        if Path(dst) == checksum and not injected:
            injected = True
            raise RuntimeError("injected non-OSError failure")
        real_replace(src, dst)

    monkeypatch.setattr(package_plugin.os, "replace", fail_checksum_install)

    with pytest.raises(RuntimeError, match="commit"):
        package_plugin.build_package(output, channel="stable")

    assert injected
    assert output.read_bytes() == old_output
    assert checksum.read_bytes() == old_checksum
    assert not list(dist.glob(".*.tmp"))


@pytest.mark.parametrize("interrupt_type", [KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize(
    "interrupt_after_replace",
    [1, 2, 3, 4],
    ids=[
        "output-backup",
        "checksum-backup",
        "output-install",
        "checksum-install",
    ],
)
def test_pair_commit_recovers_when_interrupt_follows_successful_replace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    interrupt_type: type[BaseException],
    interrupt_after_replace: int,
) -> None:
    output = tmp_path / "probe.zip"
    checksum = tmp_path / "probe.zip.sha256"
    new_output = tmp_path / "new-probe.zip"
    new_checksum = tmp_path / "new-probe.zip.sha256"
    old_output = b"old zip survives every instruction boundary\n"
    old_checksum = b"old checksum survives every instruction boundary\n"
    output.write_bytes(old_output)
    checksum.write_bytes(old_checksum)
    new_output.write_bytes(b"new zip\n")
    new_checksum.write_bytes(b"new checksum\n")

    real_replace = os.replace
    replace_count = 0

    def replace_then_interrupt(src: object, dst: object) -> None:
        nonlocal replace_count
        replace_count += 1
        real_replace(src, dst)
        if replace_count == interrupt_after_replace:
            raise interrupt_type()

    monkeypatch.setattr(package_plugin.os, "replace", replace_then_interrupt)

    with pytest.raises(interrupt_type):
        package_plugin._commit_output_pair(
            new_output,
            new_checksum,
            output,
            checksum,
        )

    assert output.read_bytes() == old_output
    assert checksum.read_bytes() == old_checksum
    assert not list(tmp_path.glob(".*backup.tmp"))


def test_interrupt_after_backup_move_preserves_backup_if_rollback_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "probe.zip"
    checksum = tmp_path / "probe.zip.sha256"
    new_output = tmp_path / "new-probe.zip"
    new_checksum = tmp_path / "new-probe.zip.sha256"
    old_output = b"only surviving old zip bytes\n"
    output.write_bytes(old_output)
    checksum.write_bytes(b"old checksum\n")
    new_output.write_bytes(b"new zip\n")
    new_checksum.write_bytes(b"new checksum\n")

    real_replace = os.replace
    output_backup_moved = False

    def interrupt_then_fail_restore(src: object, dst: object) -> None:
        nonlocal output_backup_moved
        source = Path(src)
        destination = Path(dst)
        if not output_backup_moved:
            real_replace(src, dst)
            output_backup_moved = True
            raise KeyboardInterrupt()
        if (
            destination == output
            and source.name.endswith(".zip-backup.tmp")
        ):
            raise OSError("injected rollback failure")
        real_replace(src, dst)

    monkeypatch.setattr(
        package_plugin.os,
        "replace",
        interrupt_then_fail_restore,
    )

    with pytest.raises(RuntimeError, match="incomplete.*preserv|preserv.*backup"):
        package_plugin._commit_output_pair(
            new_output,
            new_checksum,
            output,
            checksum,
        )

    backups = list(tmp_path.glob(".probe.zip.*.zip-backup.tmp"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == old_output


def test_output_alias_is_rechecked_after_temp_archive_is_written(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugin"
    dist = plugin_root / "dist"
    dist.mkdir(parents=True)
    readme = plugin_root / "README.md"
    original = b"# tracked source must survive a late swap\n"
    readme.write_bytes(original)
    output = dist / "probe.zip"
    _stub_minimal_package_build(
        monkeypatch,
        plugin_root,
        tracked_sources={"README.md"},
    )
    real_write_archive = package_plugin._write_archive

    def write_then_swap(target: Path, entries: list[tuple[str, bytes]]) -> None:
        real_write_archive(target, entries)
        os.link(readme, output)

    monkeypatch.setattr(package_plugin, "_write_archive", write_then_swap)

    with pytest.raises(RuntimeError, match="alias|tracked|release input"):
        package_plugin.build_package(output, channel="stable")

    assert os.path.samefile(readme, output)
    assert readme.read_bytes() == original
    assert not list(dist.glob(".*.tmp"))


@pytest.mark.parametrize(
    "late_change",
    ["tracked-output", "tracked-hardlink"],
)
def test_tracked_source_set_is_refreshed_before_pair_commit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    late_change: str,
) -> None:
    plugin_root = tmp_path / "plugin"
    dist = plugin_root / "dist"
    dist.mkdir(parents=True)
    output = dist / "probe.zip"
    checksum = dist / "probe.zip.sha256"
    initial_sources = {"README.md"}
    changed_sources = set(initial_sources)
    if late_change == "tracked-output":
        changed_sources.add("dist/probe.zip")
    else:
        changed_sources.add("late-source.bin")
    _stub_minimal_package_build(
        monkeypatch,
        plugin_root,
        tracked_sources=initial_sources,
    )

    tracked_calls = 0

    def changing_tracked_sources() -> set[str]:
        nonlocal tracked_calls
        tracked_calls += 1
        return initial_sources if tracked_calls == 1 else changed_sources

    monkeypatch.setattr(
        package_plugin,
        "_tracked_source_paths",
        changing_tracked_sources,
    )

    if late_change == "tracked-hardlink":
        real_write_archive = package_plugin._write_archive

        def write_then_add_hardlink(
            target: Path,
            entries: list[tuple[str, bytes]],
        ) -> None:
            real_write_archive(target, entries)
            source = plugin_root / "late-source.bin"
            source.write_bytes(b"newly tracked source bytes\n")
            os.link(source, output)

        monkeypatch.setattr(package_plugin, "_write_archive", write_then_add_hardlink)

    with pytest.raises(RuntimeError, match="tracked.*changed|changed.*tracked"):
        package_plugin.build_package(output, channel="stable")

    assert tracked_calls >= 2
    assert not checksum.exists()
    assert not list(dist.glob(".*.tmp"))
    if late_change == "tracked-output":
        assert not output.exists()
    else:
        source = plugin_root / "late-source.bin"
        assert source.read_bytes() == b"newly tracked source bytes\n"
        assert os.path.samefile(source, output)


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


def test_clean_committed_repo_builds_auditable_importable_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    files = {
        ".gitignore": b"dist/\n",
        "__init__.py": b"\"\"\"Acceptance package root.\"\"\"\n",
        "main.py": (
            b'PLUGIN_VERSION = "9.8.7"\n\n'
            b"def register(*_args):\n"
            b"    return lambda target: target\n\n"
            b'@register("Sylanne", "2718labs", "acceptance", "9.8.7")\n'
            b"class EmotionalStatePlugin:\n"
            b"    pass\n"
        ),
        "metadata.yaml": b'version: "9.8.7"\n',
        "sylanne_alpha/__init__.py": b"",
        "sylanne_alpha/v3bridge/__init__.py": b"",
        "sylanne_alpha/v3bridge/build_flags.py": (
            b"raise RuntimeError('tracked placeholder must be replaced')\n"
        ),
        "sylanne_alpha/_engine/_identity.json": (
            b'{"copy_id":"RAW-COPY-ID-SENTINEL"}\n'
        ),
        "raw/provider-secret.txt": b"RAW-SECRET-SENTINEL\n",
        "UI/index.html": b"<!doctype html><title>Acceptance UI</title>\n",
        "pages/dashboard/index.html": (
            b"<!doctype html><title>Acceptance Pages</title>\n"
        ),
    }
    for relative, content in files.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.name", "Packaging Acceptance")
    _git(repo, "config", "user.email", "packaging-acceptance@example.invalid")
    _git(repo, "add", ".")
    _git(repo, "commit", "--quiet", "-m", "acceptance fixture")
    commit = _git(repo, "rev-parse", "HEAD").stdout.decode("ascii").strip()
    assert _git(repo, "status", "--porcelain").stdout == b""

    monkeypatch.setattr(package_plugin, "ROOT", repo)
    output = package_plugin.build_package(
        repo / "dist" / "acceptance.zip",
        channel="stable",
    )
    checksum = output.with_name(f"{output.name}.sha256")

    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        contents = {name: archive.read(name) for name in names}

    prefix = f"{package_plugin.PLUGIN_NAME}/"
    flags_name = f"{prefix}sylanne_alpha/v3bridge/build_flags.py"
    manifest_name = f"{prefix}{package_plugin.MANIFEST_NAME}"
    assert {
        f"{prefix}UI/index.html",
        f"{prefix}pages/dashboard/index.html",
        flags_name,
        manifest_name,
        f"{prefix}main.py",
        f"{prefix}metadata.yaml",
    } <= set(names)
    assert not [name for name in names if "_identity" in name or "/raw/" in name]
    shipped_bytes = b"\n".join(contents.values())
    assert b"RAW-COPY-ID-SENTINEL" not in shipped_bytes
    assert b"RAW-SECRET-SENTINEL" not in shipped_bytes

    manifest = json.loads(contents[manifest_name].decode("utf-8"))
    assert manifest["schema"] == "sylanne_build_manifest_v1"
    assert manifest["channel"] == "stable"
    assert manifest["metadata_version"] == "9.8.7"
    assert manifest["git_commit"] == commit
    flags_digest = hashlib.sha256(contents[flags_name]).hexdigest()
    assert manifest["generated_file_digest"] == flags_digest
    assert manifest["generated_files"] == {flags_name: flags_digest}

    payload = hashlib.sha256()
    for name in sorted(
        (entry for entry in names if entry != manifest_name),
        key=lambda entry: entry.encode("utf-8"),
    ):
        path_bytes = name.encode("utf-8")
        content = contents[name]
        payload.update(struct.pack(">I", len(path_bytes)))
        payload.update(path_bytes)
        payload.update(struct.pack(">Q", len(content)))
        payload.update(content)
    assert manifest["payload_digest"] == payload.hexdigest()
    archive_digest = hashlib.sha256(output.read_bytes()).hexdigest()
    assert checksum.read_text(encoding="utf-8") == (
        f"{archive_digest}  {output.name}\n"
    )

    sys.path.insert(0, str(output))
    try:
        flags = importlib.import_module(
            "astrbot_plugin_sylanne.sylanne_alpha.v3bridge.build_flags"
        )
        assert flags.V3_SHADOW_ENABLED is False
        assert flags.BUILD_CHANNEL == "stable"
    finally:
        sys.path.remove(str(output))
        for name in list(sys.modules):
            if name == package_plugin.PLUGIN_NAME or name.startswith(
                f"{package_plugin.PLUGIN_NAME}."
            ):
                del sys.modules[name]

    assert _git(repo, "status", "--porcelain").stdout == b""
