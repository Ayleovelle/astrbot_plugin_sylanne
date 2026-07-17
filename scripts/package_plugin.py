from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import struct
import subprocess
import unicodedata
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "astrbot_plugin_sylanne"

# --- v3 grey/stable artifact channel -------------------------------------
#
# The v3 shadow is activated by a build-time flag, never by a user setting: the
# generated ``build_flags.py`` *replaces* the source entry inside the zip while
# the worktree stays untouched. Everything below exists to make that artifact
# auditable — a fixed archive layout, a payload digest anyone can recompute from
# the zip alone, and refusal conditions that fail the build closed.

CHANNELS = ("grey", "stable")

MANIFEST_NAME = "sylanne_build_manifest.json"
MANIFEST_ARCNAME = f"{PLUGIN_NAME}/{MANIFEST_NAME}"

BUILD_FLAGS_RELPATH = Path("sylanne_alpha/v3bridge/build_flags.py")
BUILD_FLAGS_ARCNAME = f"{PLUGIN_NAME}/{BUILD_FLAGS_RELPATH.as_posix()}"
METADATA_RELPATH = Path("metadata.yaml")
METADATA_ARCNAME = f"{PLUGIN_NAME}/{METADATA_RELPATH.as_posix()}"

V3_SOURCE_DIRS = ("sylanne_alpha/v3core", "sylanne_alpha/v3bridge")

# The engine is shipped as source only. Any other file under it is per-install
# runtime/identity state (e.g. the diagnostic ``_identity.json`` copy_id) and
# must never reach a distributed artifact.
ENGINE_PREFIX = f"{PLUGIN_NAME}/sylanne_alpha/_engine/"
ENGINE_ALLOWED_NAMES = ("py.typed",)

# One fixed timestamp/permission/compression policy: builds from the same
# tracked tree must be byte-identical.
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ZIP_COMPRESSLEVEL = 6
ZIP_CREATE_SYSTEM = 3  # unix, regardless of the build host
FILE_EXTERNAL_ATTR = 0o100644 << 16
DIR_EXTERNAL_ATTR = (0o40755 << 16) | 0x10

_VERSION_PATTERN = re.compile(r"(?m)^version:[ \t]*(.+?)[ \t]*$")

INCLUDE_ROOT_FILES = {
    "__init__.py",
    "main.py",
    "metadata.yaml",
    "_conf_schema.json",
    "requirements.txt",
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
    "logo.png",
    "astrbot_widget.json",
}

INCLUDE_DIRS = {
    "sylanne_alpha",
    "pages",
    "UI",
}

ALLOWED_DOC_ASSETS: set[Path] = set()

EXCLUDED_FILES: set[Path] = set()

EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "output",
    "dist",
    "tests",
    "scripts",
    "raw",
    ".cache",
    "ChineseBQB",
    "auto-stickers",
    "sticker_cache",
    "sticker-cache",
    "stickers",
    "pet-frames",
    "literature_kb",
    "personality_literature_kb",
    "psychological_literature_kb",
    "humanlike_agent_literature_kb",
}

EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".stackdump",
}

EXCLUDED_FILENAMES = {
    "_identity.json",
    "_identity.json.tmp",
    "pet-contact-sheet.png",
    "sylanne-pet.webp",
    "BACKEND_API.md",
    "HANDOFF.md",
    "arknights-design-language.md",
}


def should_include(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if len(relative.parts) >= 2 and relative.parts[:2] == ("docs", "assets"):
        return relative in ALLOWED_DOC_ASSETS
    if len(relative.parts) >= 2 and relative.parts[:2] == ("docs", "reports"):
        return False
    if relative in EXCLUDED_FILES:
        return False
    parts = set(relative.parts)
    if parts & EXCLUDED_PARTS:
        return False
    if path.suffix in EXCLUDED_SUFFIXES:
        return False
    if path.name in EXCLUDED_FILENAMES:
        return False
    if len(relative.parts) == 1:
        return relative.name in INCLUDE_ROOT_FILES
    return relative.parts[0] in INCLUDE_DIRS


def _tracked_files() -> set[Path]:
    """Set of git-tracked files (absolute, resolved).

    Packaging must ship only tracked content: `rglob` over the working tree would
    otherwise sweep in git-ignored runtime artifacts that match the allowlist —
    e.g. ``sylanne_core/_identity.json`` (a per-install diagnostic copy_id) — which
    must never be distributed. Git lookup failures and empty results abort the
    build instead of silently widening the package to the whole working tree.
    """
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "git ls-files failed; refusing to package untracked workspace files"
        ) from exc
    tracked = {(ROOT / rel).resolve() for rel in out.split("\0") if rel}
    if not tracked:
        raise RuntimeError(
            "git ls-files returned an empty file list; refusing to package"
        )
    return tracked


def collect_files(exclude_paths: set[Path] | None = None) -> list[Path]:
    resolved_excludes = {path.resolve() for path in (exclude_paths or set())}
    tracked = _tracked_files()
    files = [
        path for path in ROOT.rglob("*")
        if path.is_file()
        and path.resolve() not in resolved_excludes
        and path.resolve() in tracked
        and should_include(path)
    ]
    return sorted(files, key=lambda item: item.relative_to(ROOT).as_posix())


def _git_output(args: list[str]) -> str:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"git {' '.join(args)} failed; refusing to package") from exc


def _paths_differing_from_head() -> set[Path]:
    """Tracked paths whose worktree/index content differs from committed HEAD.

    This is git's own content comparison, which is eol-normalized: with
    ``core.autocrlf=true`` most worktree files differ from their HEAD blob at the
    byte level while being identical as far as git is concerned. Comparing raw
    bytes instead would refuse every build on a CRLF checkout, so "differs from
    HEAD" means "``git diff HEAD`` reports it". Consequence to be aware of: a
    ``payload_digest`` is reproducible from the same checkout, not from the
    commit id alone across eol platforms.
    """
    out = _git_output(["diff", "--name-only", "-z", "HEAD", "--"])
    return {(ROOT / rel).resolve() for rel in out.split("\0") if rel}


def _head_commit() -> str:
    commit = _git_output(["rev-parse", "HEAD"]).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RuntimeError(f"unexpected git HEAD commit {commit!r}; refusing to package")
    return commit


def _checked_metadata_override(metadata_override: Path | None) -> Path | None:
    """Validate a `--metadata` override before it is trusted as a generated entry.

    Generated entries are exempt from the HEAD-cleanliness check, so an override
    aimed back at the tracked `metadata.yaml` would smuggle uncommitted bytes
    into the archive while the manifest still names the old HEAD. The override
    must be a genuinely separate temporary copy.
    """
    if metadata_override is None:
        return None
    resolved = metadata_override.resolve()
    if resolved == (ROOT / METADATA_RELPATH).resolve():
        raise RuntimeError(
            "--metadata must be a temporary copy, not the tracked metadata.yaml; "
            "refusing to package"
        )
    return resolved


def _read_metadata_version(data: bytes) -> str:
    matches = _VERSION_PATTERN.findall(data.decode("utf-8"))
    if len(matches) != 1:
        raise RuntimeError(
            f"metadata.yaml must declare exactly one top-level version (found {len(matches)})"
        )
    return matches[0].strip().strip('"').strip("'")


def _validate_metadata_channel(version: str, channel: str) -> None:
    is_grey_version = "grey" in version.lower()
    if channel == "grey" and not is_grey_version:
        raise RuntimeError(
            f"grey channel requires grey metadata, got version {version!r}; refusing to package"
        )
    if channel == "stable" and is_grey_version:
        raise RuntimeError(
            f"stable channel rejects grey metadata version {version!r}; "
            "supply a temporary stable metadata copy via --metadata"
        )


def _render_build_flags(channel: str) -> bytes:
    enabled = channel == "grey"
    return (
        '"""Generated build flags for the v3 shadow path. Do not edit by hand."""\n'
        "\n"
        f"V3_SHADOW_ENABLED: bool = {enabled}\n"
        f'BUILD_CHANNEL: str = "{channel}"\n'
    ).encode("utf-8")


def _verify_generated_flags(content: bytes, channel: str) -> None:
    """The generated flag must say exactly what the requested channel means."""
    values: dict[str, object] = {}
    for node in ast.parse(content.decode("utf-8")).body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                values[node.target.id] = ast.literal_eval(node.value)
    expected = {"V3_SHADOW_ENABLED": channel == "grey", "BUILD_CHANNEL": channel}
    if values != expected:
        raise RuntimeError(
            f"generated build flags {values!r} disagree with channel {channel!r}; "
            "refusing to package"
        )


def _untracked_v3_sources(tracked: set[Path]) -> list[Path]:
    missing: list[Path] = []
    for relative in V3_SOURCE_DIRS:
        for path in sorted((ROOT / relative).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            if path.resolve() not in tracked:
                missing.append(path)
    return missing


def _is_engine_source(name: str) -> bool:
    """The engine ships as source only; everything else under it is runtime state."""
    basename = name.rsplit("/", 1)[-1]
    return basename.endswith(".py") or basename in ENGINE_ALLOWED_NAMES


def _normalize_arcname(name: str) -> str:
    return unicodedata.normalize("NFC", name.replace("\\", "/"))


def _archive_entries(
    channel: str,
    metadata_override: Path | None = None,
    exclude_paths: set[Path] | None = None,
) -> list[tuple[str, bytes]]:
    """Build the full (arcname, uncompressed bytes) set for one channel."""
    flags_source = (ROOT / BUILD_FLAGS_RELPATH).resolve()
    metadata_source = (ROOT / METADATA_RELPATH).resolve()
    generated_sources = {flags_source}
    if _checked_metadata_override(metadata_override) is not None:
        generated_sources.add(metadata_source)

    files = collect_files(exclude_paths=exclude_paths)
    inputs = {path.resolve() for path in files} - generated_sources

    dirty = _paths_differing_from_head() & inputs
    if dirty:
        listed = ", ".join(sorted(str(path.relative_to(ROOT)) for path in dirty))
        raise RuntimeError(
            f"tracked archive inputs differ from committed HEAD: {listed}; refusing to package"
        )

    entries: list[tuple[str, bytes]] = [(f"{PLUGIN_NAME}/", b"")]
    for path in files:
        if path.resolve() in generated_sources:
            continue  # replaced below; never appended as a duplicate
        arcname = _normalize_arcname(Path(PLUGIN_NAME, path.relative_to(ROOT)).as_posix())
        entries.append((arcname, path.read_bytes()))

    flags = _render_build_flags(channel)
    _verify_generated_flags(flags, channel)
    entries.append((BUILD_FLAGS_ARCNAME, flags))
    if metadata_override is not None:
        entries.append((METADATA_ARCNAME, metadata_override.read_bytes()))

    return _sort_entries(entries)


def _sort_entries(entries: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    return sorted(entries, key=lambda entry: entry[0].encode("utf-8"))


def _validate_archive_entries(entries: list[tuple[str, bytes]]) -> None:
    seen: set[str] = set()
    folded: dict[str, str] = {}
    for name, _content in entries:
        if name in seen:
            raise RuntimeError(f"duplicate archive path {name!r}; refusing to package")
        seen.add(name)

        if "\\" not in name and unicodedata.is_normalized("NFC", name):
            pass
        else:
            raise RuntimeError(f"archive path {name!r} is not forward-slash NFC")

        key = name.casefold()
        if key in folded:
            raise RuntimeError(
                f"case-fold collision between {folded[key]!r} and {name!r}; refusing to package"
            )
        folded[key] = name

        if name.startswith(ENGINE_PREFIX) and not _is_engine_source(name):
            raise RuntimeError(
                f"_engine identity/runtime file {name!r} must never be packaged; refusing"
            )


def payload_digest(entries: list[tuple[str, bytes]]) -> str:
    """SHA-256 over UTF-8-path-sorted entries, excluding the manifest itself.

    Each entry is framed as unsigned big-endian
    ``u32(path_utf8_byte_len) || path_utf8_bytes || u64(content_len) || bytes``
    so that path and content boundaries can never be confused with each other.
    """
    digest = hashlib.sha256()
    for name, content in _sort_entries(list(entries)):
        if name == MANIFEST_ARCNAME:
            continue
        path_bytes = name.encode("utf-8")
        digest.update(struct.pack(">I", len(path_bytes)))
        digest.update(path_bytes)
        digest.update(struct.pack(">Q", len(content)))
        digest.update(content)
    return digest.hexdigest()


def _render_manifest(
    channel: str,
    version: str,
    commit: str,
    generated: dict[str, bytes],
    digest: str,
) -> bytes:
    manifest = {
        "schema": "sylanne_build_manifest_v1",
        "channel": channel,
        "metadata_version": version,
        "git_commit": commit,
        "generated_file_digest": hashlib.sha256(generated[BUILD_FLAGS_ARCNAME]).hexdigest(),
        "generated_files": {
            name: hashlib.sha256(content).hexdigest()
            for name, content in sorted(generated.items())
        },
        "payload_digest": digest,
    }
    text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
    return f"{text}\n".encode("utf-8")


def _write_archive(output: Path, entries: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=ZIP_COMPRESSLEVEL,
    ) as archive:
        for name, content in entries:
            info = zipfile.ZipInfo(filename=name, date_time=ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = ZIP_CREATE_SYSTEM
            info.external_attr = DIR_EXTERNAL_ATTR if name.endswith("/") else FILE_EXTERNAL_ATTR
            # compresslevel must be passed here: ZipFile's constructor default is
            # only consulted when writestr builds the ZipInfo itself, so handing
            # it a pre-built ZipInfo would silently fall back to the zlib default.
            archive.writestr(info, content, compresslevel=ZIP_COMPRESSLEVEL)


def build_package(
    output: Path,
    channel: str,
    metadata_override: Path | None = None,
) -> Path:
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel!r}; expected one of {list(CHANNELS)}")

    _checked_metadata_override(metadata_override)

    untracked = _untracked_v3_sources(_tracked_files())
    if untracked:
        listed = ", ".join(str(path.relative_to(ROOT)) for path in untracked)
        raise RuntimeError(f"untracked v3 source files: {listed}; refusing to package")

    metadata_path = metadata_override or (ROOT / METADATA_RELPATH)
    version = _read_metadata_version(metadata_path.read_bytes())
    _validate_metadata_channel(version, channel)

    commit = _head_commit()
    output.parent.mkdir(parents=True, exist_ok=True)
    checksum_path = output.parent / f"{output.name}.sha256"

    entries = _archive_entries(
        channel,
        metadata_override=metadata_override,
        exclude_paths={output, checksum_path},
    )
    _validate_archive_entries(entries)

    generated = {name: content for name, content in entries if name == BUILD_FLAGS_ARCNAME}
    if metadata_override is not None:
        generated.update(
            {name: content for name, content in entries if name == METADATA_ARCNAME}
        )
    if BUILD_FLAGS_ARCNAME not in generated:
        raise RuntimeError("generated build flags missing from archive; refusing to package")

    manifest = _render_manifest(channel, version, commit, generated, payload_digest(entries))
    _write_archive(output, _sort_entries([*entries, (MANIFEST_ARCNAME, manifest)]))

    # The whole-zip digest describes the closed file, so it can only live beside
    # it — never inside the archive it is supposed to authenticate.
    checksum_path.write_text(
        f"{hashlib.sha256(output.read_bytes()).hexdigest()}  {output.name}\n",
        encoding="utf-8",
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build an AstrBot plugin zip without tests or local artifacts.",
    )
    parser.add_argument(
        "--channel",
        required=True,
        choices=list(CHANNELS),
        help="Artifact channel: grey enables the v3 shadow flag, stable disables it.",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=None,
        help="Alternative metadata.yaml to package (stable builds need a stable version).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist" / f"{PLUGIN_NAME}.zip",
        help="Output zip path.",
    )
    args = parser.parse_args()
    output = build_package(args.output, channel=args.channel, metadata_override=args.metadata)
    print(output)


if __name__ == "__main__":
    main()
