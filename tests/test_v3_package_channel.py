"""Task 14: the grey/stable artifact channel contract.

The v3 shadow is activated by a build-time flag that is never user-selectable.
These tests pin the whole contract: which channel produces which flag, that the
generated flag *replaces* the source entry, that the manifest/payload digests
are independently reproducible, that repeated builds are byte-identical, and
that every named refusal condition actually refuses.

The digest recomputations below are deliberately written from the plan text
rather than by calling `package_plugin` helpers: an independent implementation
is the only thing that can catch a self-consistent but wrong digest.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import struct
import subprocess
import sys
import unicodedata
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from scripts import package_plugin


PLUGIN = package_plugin.PLUGIN_NAME
FLAGS_ARCNAME = f"{PLUGIN}/sylanne_alpha/v3bridge/build_flags.py"
MANIFEST_ARCNAME = f"{PLUGIN}/sylanne_build_manifest.json"

# Files that are the user-facing configuration/UI/API surface. None of them may
# ever mention v3: the shadow is a build artifact property, not a setting.
SELECTOR_SURFACE = (
    f"{PLUGIN}/_conf_schema.json",
    f"{PLUGIN}/astrbot_widget.json",
    f"{PLUGIN}/UI/index.html",
    f"{PLUGIN}/sylanne_alpha/public_api.py",
    f"{PLUGIN}/sylanne_alpha/webui_routes.py",
)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _grey_metadata(tmp_path: Path) -> Path:
    """A temporary metadata copy whose version is a grey release version."""
    source = (package_plugin.ROOT / "metadata.yaml").read_text(encoding="utf-8")
    patched = re.sub(
        r'(?m)^version:\s*.*$',
        'version: "2.5.0-grey.7"',
        source,
        count=1,
    )
    assert 'version: "2.5.0-grey.7"' in patched
    target = tmp_path / "metadata.yaml"
    target.write_text(patched, encoding="utf-8")
    return target


def _load_flags_module(path: Path, name: str) -> ModuleType:
    """Import an extracted build_flags.py without touching sys.path."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _independent_payload_digest(archive: Path) -> str:
    """Recompute payload_digest straight from the plan's definition.

    SHA-256 over archive entries sorted by UTF-8 path bytes, excluding
    ``sylanne_build_manifest.json``, each framed as unsigned big-endian
    ``u32(path_utf8_len) || path_utf8 || u64(content_len) || entry_bytes``.
    """
    digest = hashlib.sha256()
    with zipfile.ZipFile(archive) as zf:
        names = [n for n in zf.namelist() if Path(n).name != "sylanne_build_manifest.json"]
        for name in sorted(names, key=lambda item: item.encode("utf-8")):
            raw = zf.read(name)
            path_bytes = name.encode("utf-8")
            digest.update(struct.pack(">I", len(path_bytes)))
            digest.update(path_bytes)
            digest.update(struct.pack(">Q", len(raw)))
            digest.update(raw)
    return digest.hexdigest()


def _independent_file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest(archive: Path) -> dict[str, Any]:
    with zipfile.ZipFile(archive) as zf:
        return json.loads(zf.read(MANIFEST_ARCNAME).decode("utf-8"))


def _build(tmp_path: Path, channel: str, *, metadata: Path | None = None) -> Path:
    output = tmp_path / f"probe-{channel}.zip"
    return package_plugin.build_package(
        output,
        channel=channel,
        metadata_override=metadata,
    )


@pytest.fixture(scope="module")
def grey_archive(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("grey")
    return _build(root, "grey", metadata=_grey_metadata(root))


@pytest.fixture(scope="module")
def stable_archive(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build(tmp_path_factory.mktemp("stable"), "stable")


# --------------------------------------------------------------------------
# RED: channel flags, single archive entry, no selector
# --------------------------------------------------------------------------


def test_channel_argument_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["package_plugin.py"])
    with pytest.raises(SystemExit) as excinfo:
        package_plugin.main()
    assert excinfo.value.code != 0


def test_unknown_channel_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="channel"):
        package_plugin.build_package(tmp_path / "x.zip", channel="nightly")


def test_grey_archive_flag_enables_shadow(grey_archive: Path, tmp_path: Path) -> None:
    with zipfile.ZipFile(grey_archive) as zf:
        zf.extract(FLAGS_ARCNAME, tmp_path)
    module = _load_flags_module(tmp_path / FLAGS_ARCNAME, "probe_flags_grey")

    assert module.V3_SHADOW_ENABLED is True
    assert module.BUILD_CHANNEL == "grey"


def test_stable_archive_flag_disables_shadow(stable_archive: Path, tmp_path: Path) -> None:
    with zipfile.ZipFile(stable_archive) as zf:
        zf.extract(FLAGS_ARCNAME, tmp_path)
    module = _load_flags_module(tmp_path / FLAGS_ARCNAME, "probe_flags_stable")

    assert module.V3_SHADOW_ENABLED is False
    assert module.BUILD_CHANNEL == "stable"


def test_source_tree_flag_stays_disabled() -> None:
    """Packaging must never rewrite the worktree."""
    module = _load_flags_module(
        package_plugin.ROOT / "sylanne_alpha" / "v3bridge" / "build_flags.py",
        "probe_flags_source",
    )

    assert module.V3_SHADOW_ENABLED is False
    assert module.BUILD_CHANNEL == "source"


@pytest.mark.parametrize("channel", ["grey", "stable"])
def test_archive_has_exactly_one_build_flags_entry(
    channel: str,
    grey_archive: Path,
    stable_archive: Path,
) -> None:
    archive = grey_archive if channel == "grey" else stable_archive
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()

    assert names.count(FLAGS_ARCNAME) == 1
    assert [n for n in names if n.endswith("v3bridge/build_flags.py")] == [FLAGS_ARCNAME]


@pytest.mark.parametrize("channel", ["grey", "stable"])
def test_archive_config_and_ui_api_schema_have_no_v3_selector(
    channel: str,
    grey_archive: Path,
    stable_archive: Path,
) -> None:
    archive = grey_archive if channel == "grey" else stable_archive
    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
        present = [name for name in SELECTOR_SURFACE if name in names]
        assert f"{PLUGIN}/_conf_schema.json" in present, "config schema must ship"
        for name in present:
            text = zf.read(name).decode("utf-8", errors="replace")
            assert "v3" not in text.lower(), f"{name} exposes a v3 selector"

        schema = json.loads(zf.read(f"{PLUGIN}/_conf_schema.json").decode("utf-8"))
    assert not [key for key in _walk_keys(schema) if "v3" in key.lower()]


def _walk_keys(node: object) -> list[str]:
    keys: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            keys.append(str(key))
            keys.extend(_walk_keys(value))
    elif isinstance(node, list):
        for item in node:
            keys.extend(_walk_keys(item))
    return keys


# --------------------------------------------------------------------------
# RED: metadata/channel agreement
# --------------------------------------------------------------------------


def test_grey_packaging_rejects_checked_in_stable_metadata(tmp_path: Path) -> None:
    version = package_plugin._read_metadata_version(
        (package_plugin.ROOT / "metadata.yaml").read_bytes()
    )
    assert version == "2.5.0"

    with pytest.raises(RuntimeError, match="grey"):
        _build(tmp_path, "grey")


def test_stable_packaging_rejects_grey_metadata(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="stable"):
        _build(tmp_path, "stable", metadata=_grey_metadata(tmp_path))


def test_metadata_override_may_not_be_the_tracked_metadata_file(tmp_path: Path) -> None:
    """A generated entry skips the HEAD check, so it must be a real temporary copy.

    Otherwise `--metadata metadata.yaml` would exempt the tracked file from the
    HEAD-cleanliness check and ship uncommitted bytes under an old commit id.
    """
    with pytest.raises(RuntimeError, match="temporary copy"):
        _build(tmp_path, "stable", metadata=package_plugin.ROOT / "metadata.yaml")

    # ... including via a non-normalized path spelling.
    with pytest.raises(RuntimeError, match="temporary copy"):
        _build(tmp_path, "stable", metadata=package_plugin.ROOT / "docs" / ".." / "metadata.yaml")


def test_metadata_override_does_not_exempt_other_inputs_from_the_head_check(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dirty = (package_plugin.ROOT / "main.py").resolve()
    monkeypatch.setattr(package_plugin, "_paths_differing_from_head", lambda: {dirty})

    with pytest.raises(RuntimeError, match="HEAD"):
        _build(tmp_path, "grey", metadata=_grey_metadata(tmp_path))


def test_grey_archive_carries_the_temporary_grey_version(grey_archive: Path) -> None:
    assert _manifest(grey_archive)["metadata_version"] == "2.5.0-grey.7"
    with zipfile.ZipFile(grey_archive) as zf:
        shipped = zf.read(f"{PLUGIN}/metadata.yaml").decode("utf-8")
    assert 'version: "2.5.0-grey.7"' in shipped


# --------------------------------------------------------------------------
# RED: manifest and digests
# --------------------------------------------------------------------------


def test_manifest_records_channel_version_commit_and_digests(stable_archive: Path) -> None:
    manifest = _manifest(stable_archive)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=package_plugin.ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    assert manifest["channel"] == "stable"
    assert manifest["metadata_version"] == "2.5.0"
    assert manifest["git_commit"] == commit
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["payload_digest"])
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["generated_file_digest"])

    with zipfile.ZipFile(stable_archive) as zf:
        flags = zf.read(FLAGS_ARCNAME)
    assert manifest["generated_file_digest"] == hashlib.sha256(flags).hexdigest()
    assert manifest["generated_files"][FLAGS_ARCNAME] == hashlib.sha256(flags).hexdigest()


@pytest.mark.parametrize("channel", ["grey", "stable"])
def test_payload_digest_matches_independent_recomputation(
    channel: str,
    grey_archive: Path,
    stable_archive: Path,
) -> None:
    archive = grey_archive if channel == "grey" else stable_archive
    assert _manifest(archive)["payload_digest"] == _independent_payload_digest(archive)


def test_payload_digest_sorts_entries_and_excludes_the_manifest() -> None:
    """Pin the two digest rules that a real build's entry list cannot exercise.

    Real builds hand `payload_digest` an already-sorted, manifest-free list, so
    the sort and the exclusion are unreachable there and would survive being
    deleted. Drive them directly instead.
    """
    entries = [
        (f"{PLUGIN}/b.py", b"bbb"),
        (f"{PLUGIN}/a.py", b"aaa"),
    ]
    expected = package_plugin.payload_digest(entries)

    assert package_plugin.payload_digest(list(reversed(entries))) == expected
    assert package_plugin.payload_digest([*entries, (MANIFEST_ARCNAME, b"anything")]) == expected
    assert package_plugin.payload_digest([*entries, (f"{PLUGIN}/c.py", b"")]) != expected


def test_payload_digest_framing_separates_path_from_content() -> None:
    """The length framing must make path/content boundaries unambiguous."""
    shifted = package_plugin.payload_digest([(f"{PLUGIN}/ab", b"c")])
    other = package_plugin.payload_digest([(f"{PLUGIN}/a", b"bc")])

    assert shifted != other


def test_grey_and_stable_payload_digests_differ(
    grey_archive: Path,
    stable_archive: Path,
) -> None:
    assert _manifest(grey_archive)["payload_digest"] != _manifest(stable_archive)["payload_digest"]


@pytest.mark.parametrize("channel", ["grey", "stable"])
def test_whole_zip_digest_lives_only_in_the_adjacent_sidecar(
    channel: str,
    grey_archive: Path,
    stable_archive: Path,
) -> None:
    archive = grey_archive if channel == "grey" else stable_archive
    sidecar = archive.parent / f"{archive.name}.sha256"

    assert sidecar.is_file()
    recomputed = _independent_file_digest(archive)
    assert sidecar.read_text(encoding="utf-8").split()[0] == recomputed

    # A whole-zip digest can never be inside the zip it describes.
    with zipfile.ZipFile(archive) as zf:
        assert not [n for n in zf.namelist() if n.endswith(".sha256")]
        assert recomputed not in zf.read(MANIFEST_ARCNAME).decode("utf-8")


def test_compression_level_policy_is_actually_applied(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The declared compression policy must not be inert.

    `writestr` only honours ZipFile's default compresslevel when it builds the
    ZipInfo itself; handing it a pre-built ZipInfo silently falls back to the
    zlib default. A zip stores no readable compression level, so the only way to
    observe the policy is that changing it changes the output.
    """
    entries = [(f"{PLUGIN}/blob.bin", b"sylanne compressible payload " * 4000)]
    sizes: dict[int, int] = {}
    for level in (1, 9):
        monkeypatch.setattr(package_plugin, "ZIP_COMPRESSLEVEL", level)
        target = tmp_path / f"level-{level}.zip"
        package_plugin._write_archive(target, entries)
        sizes[level] = target.stat().st_size

    assert sizes[1] != sizes[9], "ZIP_COMPRESSLEVEL is ignored by the archive writer"


def test_repeated_builds_from_the_same_tracked_tree_are_byte_identical(
    tmp_path: Path,
) -> None:
    first = package_plugin.build_package(tmp_path / "a" / "p.zip", channel="stable")
    second = package_plugin.build_package(tmp_path / "b" / "p.zip", channel="stable")

    assert first.read_bytes() == second.read_bytes()
    assert _independent_file_digest(first) == _independent_file_digest(second)
    assert (
        (first.parent / "p.zip.sha256").read_text(encoding="utf-8").split()[0]
        == (second.parent / "p.zip.sha256").read_text(encoding="utf-8").split()[0]
    )


def test_same_head_build_is_identical_across_lf_and_crlf_checkouts(tmp_path: Path) -> None:
    """A manifest naming HEAD must package bytes reproducible from that commit."""

    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "scripts").mkdir()
    (seed / "sylanne_alpha" / "v3core").mkdir(parents=True)
    (seed / "sylanne_alpha" / "v3bridge").mkdir(parents=True)

    (seed / ".gitattributes").write_bytes(
        b"* text=auto\n*.md text\n*.py text\n*.yaml text\n"
    )
    (seed / "README.md").write_bytes(b"line one\nline two\n")
    (seed / "metadata.yaml").write_bytes(b'name: probe\nversion: "2.5.0"\n')
    (seed / "main.py").write_bytes(
        b'PLUGIN_VERSION = "2.5.0"\n'
        b'@register("probe", "2718 Labs", "probe", "2.5.0", "https://example.com")\n'
        b"class Plugin:\n"
        b"    pass\n"
    )
    (seed / "sylanne_alpha" / "v3core" / "probe.py").write_bytes(b"VALUE = 1\n")
    (seed / "sylanne_alpha" / "v3bridge" / "build_flags.py").write_bytes(
        b'V3_SHADOW_ENABLED: bool = False\nBUILD_CHANNEL: str = "source"\n'
    )
    (seed / "scripts" / "package_plugin.py").write_bytes(
        (package_plugin.ROOT / "scripts" / "package_plugin.py").read_bytes()
    )

    def git(*args: str, cwd: Path) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            check=True,
        )

    git("init", "--quiet", cwd=seed)
    git("config", "user.name", "Packaging Test", cwd=seed)
    git("config", "user.email", "packaging-test@example.invalid", cwd=seed)
    git("add", ".", cwd=seed)
    git("commit", "--quiet", "-m", "fixture", cwd=seed)

    checkouts: dict[str, Path] = {}
    for label, autocrlf, eol in (
        ("lf", "false", "lf"),
        ("crlf", "true", "crlf"),
    ):
        checkout = tmp_path / label
        git(
            "clone",
            "--quiet",
            "--config",
            f"core.autocrlf={autocrlf}",
            "--config",
            f"core.eol={eol}",
            str(seed),
            str(checkout),
            cwd=tmp_path,
        )
        checkouts[label] = checkout

    working_tree_readmes = {
        label: (checkout / "README.md").read_bytes()
        for label, checkout in checkouts.items()
    }
    assert working_tree_readmes["lf"] != working_tree_readmes["crlf"]
    assert b"\r\n" not in working_tree_readmes["lf"]
    assert b"\r\n" in working_tree_readmes["crlf"]

    head_readme = git("show", "HEAD:README.md", cwd=seed).stdout
    archives: dict[str, Path] = {}
    shipped_readmes: dict[str, bytes] = {}
    for label, checkout in checkouts.items():
        archive = tmp_path / "output" / f"{label}.zip"
        archive.parent.mkdir(exist_ok=True)
        subprocess.run(
            [
                sys.executable,
                str(checkout / "scripts" / "package_plugin.py"),
                "--channel",
                "stable",
                "--output",
                str(archive),
            ],
            cwd=checkout,
            capture_output=True,
            check=True,
        )
        archives[label] = archive
        with zipfile.ZipFile(archive) as zf:
            shipped_readmes[label] = zf.read(f"{PLUGIN}/README.md")

    zip_bytes_match = archives["lf"].read_bytes() == archives["crlf"].read_bytes()
    entries_match_head = {
        label: content == head_readme for label, content in shipped_readmes.items()
    }
    working_tree_sizes = {
        label: len(data) for label, data in working_tree_readmes.items()
    }
    shipped_sizes = {label: len(data) for label, data in shipped_readmes.items()}
    assert zip_bytes_match and all(entries_match_head.values()), (
        f"zip_bytes_match={zip_bytes_match}, entries_match_head={entries_match_head}, "
        f"working_tree_sizes={working_tree_sizes}, shipped_sizes={shipped_sizes}"
    )


@pytest.mark.parametrize("channel", ["grey", "stable"])
def test_archive_paths_are_forward_slash_nfc(
    channel: str,
    grey_archive: Path,
    stable_archive: Path,
) -> None:
    archive = grey_archive if channel == "grey" else stable_archive
    with zipfile.ZipFile(archive) as zf:
        infos = zf.infolist()

    for info in infos:
        assert "\\" not in info.filename
        assert unicodedata.is_normalized("NFC", info.filename)
        assert info.date_time == package_plugin.ZIP_TIMESTAMP
        assert info.compress_type == zipfile.ZIP_DEFLATED
        assert info.create_system == 3
        expected_attr = (
            package_plugin.DIR_EXTERNAL_ATTR
            if info.filename.endswith("/")
            else package_plugin.FILE_EXTERNAL_ATTR
        )
        assert info.external_attr == expected_attr

    folded = [info.filename.casefold() for info in infos]
    assert len(folded) == len(set(folded))


# --------------------------------------------------------------------------
# RED: the seven refusal conditions
# --------------------------------------------------------------------------


def test_refuses_when_a_tracked_archive_input_differs_from_head(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dirty = (package_plugin.ROOT / "main.py").resolve()
    monkeypatch.setattr(package_plugin, "_paths_differing_from_head", lambda: {dirty})

    with pytest.raises(RuntimeError, match="HEAD"):
        _build(tmp_path, "stable")


def test_ignores_head_differences_outside_the_archive_input_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Dirty docs/tests/scripts must not block a stable build."""
    unrelated = (package_plugin.ROOT / "scripts" / "package_plugin.py").resolve()
    monkeypatch.setattr(package_plugin, "_paths_differing_from_head", lambda: {unrelated})

    assert _build(tmp_path, "stable").is_file()


def test_refuses_when_the_generated_flag_disagrees_with_the_channel(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        package_plugin,
        "_render_build_flags",
        lambda channel: b'V3_SHADOW_ENABLED: bool = True\nBUILD_CHANNEL: str = "grey"\n',
    )

    with pytest.raises(RuntimeError, match="generated"):
        _build(tmp_path, "stable")


def test_refuses_when_a_v3_source_file_is_untracked(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    real = package_plugin._tracked_files()
    victim = (package_plugin.ROOT / "sylanne_alpha" / "v3core" / "orchestrator.py").resolve()
    assert victim in real
    monkeypatch.setattr(package_plugin, "_tracked_files", lambda: real - {victim})

    with pytest.raises(RuntimeError, match="untracked"):
        _build(tmp_path, "stable")


def test_refuses_duplicate_archive_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        package_plugin,
        "_archive_entries",
        lambda *args, **kwargs: [
            (f"{PLUGIN}/main.py", b"a"),
            (f"{PLUGIN}/main.py", b"b"),
        ],
    )

    with pytest.raises(RuntimeError, match="duplicate"):
        _build(tmp_path, "stable")


def test_refuses_case_fold_colliding_archive_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        package_plugin,
        "_archive_entries",
        lambda *args, **kwargs: [
            (f"{PLUGIN}/main.py", b"a"),
            (f"{PLUGIN}/MAIN.py", b"b"),
        ],
    )

    with pytest.raises(RuntimeError, match="case-fold"):
        _build(tmp_path, "stable")


@pytest.mark.parametrize(
    "arcname",
    [
        f"{PLUGIN}/sylanne_alpha/_engine/sylanne_core/_identity.json",
        f"{PLUGIN}/sylanne_alpha/_engine/sylanne_core/_identity.json.tmp",
        f"{PLUGIN}/sylanne_alpha/_engine/sylanne_core/state.db",
        f"{PLUGIN}/sylanne_alpha/_engine/runtime.log",
    ],
)
def test_refuses_engine_identity_and_runtime_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    arcname: str,
) -> None:
    monkeypatch.setattr(
        package_plugin,
        "_archive_entries",
        lambda *args, **kwargs: [
            (f"{PLUGIN}/main.py", b"a"),
            (arcname, b"{}"),
        ],
    )

    with pytest.raises(RuntimeError, match="_engine"):
        _build(tmp_path, "stable")


def test_engine_python_sources_are_still_allowed(stable_archive: Path) -> None:
    """The refusal must be about runtime data, not about shipping the engine."""
    with zipfile.ZipFile(stable_archive) as zf:
        engine = [
            n for n in zf.namelist()
            if n.startswith(f"{PLUGIN}/sylanne_alpha/_engine/")
        ]

    assert engine, "the engine package must still ship"
    assert all(n.endswith((".py", "py.typed")) for n in engine)
    assert not [n for n in engine if Path(n).name.startswith("_identity.json")]


def test_unrelated_untracked_file_is_excluded_and_left_untouched(tmp_path: Path) -> None:
    probe = package_plugin.ROOT / "sylanne_alpha" / "_stable_channel_untracked_probe.py"
    assert not probe.exists(), "probe path must not collide with a real file"
    payload = b"# untracked probe; packaging must ignore me\n"

    # Snapshot every pre-existing untracked file so the build cannot touch them.
    others = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=package_plugin.ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    existing = [package_plugin.ROOT / rel for rel in others.split("\0") if rel]
    before = {
        path: path.read_bytes()
        for path in existing
        if path.is_file() and path.stat().st_size < 1 << 20
    }

    try:
        probe.write_bytes(payload)
        archive = _build(tmp_path, "stable")

        with zipfile.ZipFile(archive) as zf:
            names = zf.namelist()
        assert f"{PLUGIN}/sylanne_alpha/_stable_channel_untracked_probe.py" not in names
        assert probe.read_bytes() == payload

        for path, content in before.items():
            assert path.read_bytes() == content, f"packaging mutated {path}"
    finally:
        probe.unlink(missing_ok=True)
