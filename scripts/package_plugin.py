from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import stat
import struct
import subprocess
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass
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
MAIN_RELPATH = Path("main.py")
MAIN_ARCNAME = f"{PLUGIN_NAME}/{MAIN_RELPATH.as_posix()}"
METADATA_RELPATH = Path("metadata.yaml")
METADATA_ARCNAME = f"{PLUGIN_NAME}/{METADATA_RELPATH.as_posix()}"

V3_SOURCE_DIRS = ("sylanne_alpha/v3core", "sylanne_alpha/v3bridge")

# The engine is shipped as source only. Any other file under it is per-install
# runtime/identity state (e.g. the diagnostic ``_identity.json`` copy_id) and
# must never reach a distributed artifact.
ENGINE_PREFIX = f"{PLUGIN_NAME}/sylanne_alpha/_engine/"
ENGINE_ALLOWED_NAMES = ("py.typed",)
REGULAR_BLOB_MODES = {"100644", "100755"}

# Release-input safety envelope. The current stable tree selects 216 files,
# whose largest blob is 246,376 bytes and total is about 4.55 MiB. These caps
# leave substantial growth room while bounding every Git subprocess capture.
MAX_SELECTED_ENTRIES = 1024
MAX_HEAD_BLOB_BYTES = 4 * 1024 * 1024
MAX_TOTAL_HEAD_BLOB_BYTES = 32 * 1024 * 1024
MAX_METADATA_OVERRIDE_BYTES = 256 * 1024
MAX_GIT_NUL_LISTING_BYTES = 2 * 1024 * 1024
MAX_GIT_NUL_LISTING_RECORDS = 4096
GIT_NUL_READ_CHUNK_BYTES = 64 * 1024

# One fixed timestamp/permission/compression policy: builds from the same
# tracked tree must be byte-identical.
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ZIP_COMPRESSLEVEL = 6
ZIP_CREATE_SYSTEM = 3  # unix, regardless of the build host
FILE_EXTERNAL_ATTR = 0o100644 << 16
DIR_EXTERNAL_ATTR = (0o40755 << 16) | 0x10

_VERSION_PATTERN = re.compile(r"(?m)^version:[ \t]*(.+?)[ \t]*$")
_SEMVER_COMPONENT = r"(?:0|[1-9][0-9]*)"
_STABLE_VERSION_PATTERN = re.compile(
    rf"{_SEMVER_COMPONENT}\.{_SEMVER_COMPONENT}\.{_SEMVER_COMPONENT}"
)
_GREY_VERSION_PATTERN = re.compile(
    rf"{_SEMVER_COMPONENT}\.{_SEMVER_COMPONENT}\.{_SEMVER_COMPONENT}"
    rf"-grey\.{_SEMVER_COMPONENT}"
)

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


def _tracked_files() -> set[str]:
    """Set of indexed v3 paths as validated repository-relative POSIX strings.

    This intentionally queries only the two v3 source roots used by the
    untracked-source safety gate. Release payload selection comes from the
    separately bounded committed-tree query.
    """
    records = _git_nul_records(
        ["ls-files", "-z", "--", *V3_SOURCE_DIRS],
        max_bytes=MAX_GIT_NUL_LISTING_BYTES,
        max_records=MAX_GIT_NUL_LISTING_RECORDS,
    )
    if not records:
        raise RuntimeError("git ls-files returned an empty file list; refusing to package")
    tracked = {
        _checked_repo_relative_path(raw)
        for raw in records
    }
    if not tracked:
        raise RuntimeError(
            "git ls-files returned an empty file list; refusing to package"
        )
    return tracked


def _tracked_source_paths() -> set[str]:
    """All tracked worktree paths protected from output and sidecar writes."""
    records = _git_nul_records(
        ["ls-files", "-z", "--"],
        max_bytes=MAX_GIT_NUL_LISTING_BYTES,
        max_records=MAX_GIT_NUL_LISTING_RECORDS,
    )
    if not records:
        raise RuntimeError("git ls-files returned no tracked sources; refusing to package")
    return {_checked_repo_relative_path(raw) for raw in records}


def _git_binary_output(args: list[str], *, input_data: bytes | None = None) -> bytes:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=ROOT,
            input=input_data,
            capture_output=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"git {' '.join(args)} failed; refusing to package") from exc


def _git_nul_records(
    args: list[str],
    *,
    max_bytes: int,
    max_records: int,
) -> list[bytes]:
    """Stream a NUL-delimited Git listing under hard byte and record bounds."""
    try:
        process = subprocess.Popen(
            ["git", *args],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise RuntimeError(f"git {' '.join(args)} failed to start; refusing") from exc
    if process.stdout is None:
        try:
            process.kill()
        finally:
            process.wait()
        raise RuntimeError(f"git {' '.join(args)} has no stdout pipe; refusing")

    finished = False

    def stop() -> None:
        nonlocal finished
        try:
            process.kill()
        except OSError:
            pass
        finally:
            process.wait()
            finished = True

    records: list[bytes] = []
    pending = bytearray()
    total_bytes = 0
    try:
        while True:
            chunk = process.stdout.read(GIT_NUL_READ_CHUNK_BYTES)
            if not chunk:
                break
            if total_bytes + len(chunk) > max_bytes:
                stop()
                raise RuntimeError(
                    f"git {' '.join(args)} exceeded the {max_bytes}-byte listing limit"
                )
            total_bytes += len(chunk)
            pending.extend(chunk)
            while True:
                delimiter = pending.find(0)
                if delimiter < 0:
                    break
                if len(records) >= max_records:
                    stop()
                    raise RuntimeError(
                        f"git {' '.join(args)} exceeded the {max_records}-record listing limit"
                    )
                record = bytes(pending[:delimiter])
                del pending[: delimiter + 1]
                if not record:
                    stop()
                    raise RuntimeError(
                        f"git {' '.join(args)} returned an empty NUL record; refusing"
                    )
                records.append(record)

        returncode = process.wait()
        finished = True
        if returncode != 0:
            raise RuntimeError(
                f"git {' '.join(args)} exited with {returncode}; refusing to package"
            )
        if pending:
            raise RuntimeError(
                f"git {' '.join(args)} returned a non-NUL-terminated record; refusing"
            )
        return records
    finally:
        if not finished and process.poll() is None:
            stop()


def _checked_repo_relative_path(raw: bytes) -> str:
    try:
        relative = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("Git path is not UTF-8; refusing to package") from exc
    parts = relative.split("/")
    if (
        not relative
        or relative.startswith("/")
        or "\\" in relative
        or "\r" in relative
        or "\n" in relative
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise RuntimeError(f"unsafe Git path {relative!r}; refusing to package")
    return relative


def _repo_path(relative: str) -> Path:
    return ROOT.joinpath(*relative.split("/"))


def _lexical_absolute(path: Path) -> Path:
    """Make a filesystem path absolute without resolving symlinks."""
    return Path(os.path.abspath(os.fspath(path)))


def _filesystem_identity_key(path: Path) -> str:
    """Return a platform-independent, case-folded lexical path identity."""
    rendered = _lexical_absolute(path).as_posix()
    return unicodedata.normalize("NFC", rendered).casefold()


def _identity_is_below(path_key: str, directory_key: str) -> bool:
    return path_key.startswith(f"{directory_key.rstrip('/')}/")


def _checked_output_locations(output: Path) -> tuple[Path, Path]:
    """Validate repo-local output locations before any directory or file write."""
    output = _lexical_absolute(output)
    checksum = output.parent / f"{output.name}.sha256"
    output_key = _filesystem_identity_key(output)
    checksum_key = _filesystem_identity_key(checksum)
    root_key = _filesystem_identity_key(ROOT)
    artifact_key = _filesystem_identity_key(ROOT / f"{PLUGIN_NAME}.zip")
    artifact_checksum_key = f"{artifact_key}.sha256"
    dist_key = _filesystem_identity_key(ROOT / "dist")

    output_is_repo_local = output_key == root_key or _identity_is_below(
        output_key,
        root_key,
    )
    output_is_allowed = (
        output_key == artifact_key
        or _identity_is_below(output_key, dist_key)
        or not output_is_repo_local
    )
    if not output_is_allowed:
        raise RuntimeError(
            "output inside the repository must be "
            f"{PLUGIN_NAME}.zip or live below dist/; refusing to package"
        )

    checksum_is_repo_local = checksum_key == root_key or _identity_is_below(
        checksum_key,
        root_key,
    )
    checksum_is_allowed = (
        checksum_key == artifact_checksum_key
        or _identity_is_below(checksum_key, dist_key)
        or not checksum_is_repo_local
    )
    if not checksum_is_allowed:
        raise RuntimeError(
            "checksum output inside the repository must accompany the root artifact "
            "or live below dist/; refusing to package"
        )
    if output_key == checksum_key:
        raise RuntimeError("archive output aliases its checksum sidecar; refusing to package")
    return output, checksum


def _resolved_absolute(path: Path) -> Path:
    try:
        return path.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise RuntimeError(f"cannot resolve output path {path}; refusing to package") from exc


def _checked_resolved_output_locations(output: Path, checksum: Path) -> None:
    """Ensure repo-local aliases still resolve only to the two output areas."""
    resolved_root = _resolved_absolute(ROOT)
    resolved_root_key = _filesystem_identity_key(resolved_root)
    resolved_artifact_key = _filesystem_identity_key(
        resolved_root / f"{PLUGIN_NAME}.zip"
    )
    resolved_artifact_checksum_key = f"{resolved_artifact_key}.sha256"
    resolved_dist_key = _filesystem_identity_key(resolved_root / "dist")
    lexical_root_key = _filesystem_identity_key(ROOT)

    for label, target, artifact_key in (
        ("output", output, resolved_artifact_key),
        ("checksum", checksum, resolved_artifact_checksum_key),
    ):
        resolved_key = _filesystem_identity_key(_resolved_absolute(target))
        resolves_into_repo = resolved_key == resolved_root_key or _identity_is_below(
            resolved_key,
            resolved_root_key,
        )
        if resolves_into_repo and not (
            resolved_key == artifact_key
            or _identity_is_below(resolved_key, resolved_dist_key)
        ):
            raise RuntimeError(
                f"{label} path resolves into a repository source location; "
                "refusing to package"
            )

        lexical_key = _filesystem_identity_key(target)
        is_lexically_repo_local = (
            lexical_key == lexical_root_key
            or _identity_is_below(lexical_key, lexical_root_key)
        )
        if is_lexically_repo_local and not (
            resolved_key == artifact_key
            or _identity_is_below(resolved_key, resolved_dist_key)
        ):
            raise RuntimeError(
                f"{label} path leaves its allowed repository output location "
                "through a symlink or junction; refusing to package"
            )


def _paths_share_existing_file(left: Path, right: Path) -> bool:
    try:
        left_stat = os.stat(left)
        right_stat = os.stat(right)
    except (FileNotFoundError, OSError):
        return False
    same_identity = _same_stable_file_identity(left_stat, right_stat)
    if same_identity is not None:
        return same_identity
    try:
        return os.path.samefile(left, right)
    except OSError:
        return False


def _validate_output_targets(
    output: Path,
    checksum: Path,
    tracked_sources: set[str],
    metadata_override: Path | None,
) -> None:
    """Reject lexical, resolved, and existing-file aliases of package inputs."""
    _checked_resolved_output_locations(output, checksum)
    if (
        _filesystem_identity_key(output) == _filesystem_identity_key(checksum)
        or _filesystem_identity_key(_resolved_absolute(output))
        == _filesystem_identity_key(_resolved_absolute(checksum))
        or _paths_share_existing_file(output, checksum)
    ):
        raise RuntimeError(
            "archive output aliases its checksum sidecar; refusing to package"
        )

    artifact_key = _filesystem_identity_key(ROOT / f"{PLUGIN_NAME}.zip")
    artifact_checksum_key = f"{artifact_key}.sha256"
    output_is_root_artifact = _filesystem_identity_key(output) == artifact_key
    checksum_is_root_sidecar = (
        _filesystem_identity_key(checksum) == artifact_checksum_key
    )
    protected = [
        (
            ROOT / Path(relative),
            _filesystem_identity_key(ROOT / Path(relative)) == artifact_key,
            _filesystem_identity_key(ROOT / Path(relative))
            == artifact_checksum_key,
        )
        for relative in sorted(tracked_sources)
    ]
    if metadata_override is not None:
        protected.append((metadata_override, False, False))

    for label, target in (("output", output), ("checksum", checksum)):
        try:
            target_lstat = os.lstat(target)
        except FileNotFoundError:
            target_lstat = None
        except OSError as exc:
            raise RuntimeError(f"cannot inspect {label} path {target}; refusing") from exc
        if target_lstat is not None and stat.S_ISDIR(target_lstat.st_mode):
            raise RuntimeError(f"{label} path is a directory; refusing to package")

        target_key = _filesystem_identity_key(target)
        resolved_target_key = _filesystem_identity_key(_resolved_absolute(target))
        for source, is_tracked_root_artifact, is_tracked_root_sidecar in protected:
            source_key = _filesystem_identity_key(source)
            if (
                (
                    label == "output"
                    and output_is_root_artifact
                    and is_tracked_root_artifact
                )
                or (
                    label == "checksum"
                    and checksum_is_root_sidecar
                    and is_tracked_root_sidecar
                )
            ):
                continue
            resolved_source_key = _filesystem_identity_key(_resolved_absolute(source))
            if (
                target_key == source_key
                or resolved_target_key == resolved_source_key
                or _paths_share_existing_file(target, source)
            ):
                raise RuntimeError(
                    f"{label} path aliases tracked or release input {source}; "
                    "refusing to package"
                )


def _filesystem_path_to_repo_relative(path: Path) -> str | None:
    try:
        relative = _lexical_absolute(path).relative_to(_lexical_absolute(ROOT)).as_posix()
    except ValueError:
        return None
    return _checked_repo_relative_path(relative.encode("utf-8"))


def _checked_revision(revision: str) -> str:
    if revision == "HEAD" or re.fullmatch(r"[0-9a-f]{40}", revision):
        return revision
    raise RuntimeError(f"unsafe git revision {revision!r}; refusing to package")


def _release_pathspecs() -> list[str]:
    candidates = {
        *INCLUDE_ROOT_FILES,
        *INCLUDE_DIRS,
        *(path.as_posix() for path in ALLOWED_DOC_ASSETS),
    }
    return sorted(
        _checked_repo_relative_path(candidate.encode("utf-8"))
        for candidate in candidates
    )


@dataclass(frozen=True, slots=True)
class HeadTreeEntry:
    relative_path: str
    mode: str
    oid: str


def _head_tree_files(revision: str = "HEAD") -> list[HeadTreeEntry]:
    """Return validated regular blobs from a committed Git tree."""
    revision = _checked_revision(revision)
    records = _git_nul_records(
        ["ls-tree", "-r", "-z", revision, "--", *_release_pathspecs()],
        max_bytes=MAX_GIT_NUL_LISTING_BYTES,
        max_records=MAX_GIT_NUL_LISTING_RECORDS,
    )
    if not records:
        raise RuntimeError("git ls-tree returned an empty HEAD release tree")
    entries: list[HeadTreeEntry] = []
    for record in records:
        try:
            header, raw_path = record.split(b"\t", 1)
        except ValueError as exc:
            raise RuntimeError("git ls-tree returned a malformed HEAD tree record") from exc
        fields = header.split(b" ")
        if len(fields) != 3:
            raise RuntimeError("git ls-tree returned a malformed HEAD tree header")
        try:
            mode = fields[0].decode("ascii")
            object_type = fields[1].decode("ascii")
            oid = fields[2].decode("ascii")
        except UnicodeDecodeError as exc:
            raise RuntimeError("git ls-tree returned a non-ASCII object header") from exc
        relative = _checked_repo_relative_path(raw_path)
        if mode == "120000":
            raise RuntimeError(f"HEAD tree symlink {relative!r} is not packageable; refusing")
        if mode == "160000":
            raise RuntimeError(f"HEAD tree gitlink {relative!r} is not packageable; refusing")
        if mode not in REGULAR_BLOB_MODES or object_type != "blob":
            raise RuntimeError(
                f"HEAD tree entry {relative!r} has unsupported mode/type "
                f"{mode!r}/{object_type!r}; refusing"
            )
        if re.fullmatch(r"[0-9a-f]{40}", oid) is None:
            raise RuntimeError(f"HEAD tree entry {relative!r} has an invalid object id")
        entries.append(HeadTreeEntry(relative_path=relative, mode=mode, oid=oid))
    if len({entry.relative_path for entry in entries}) != len(entries):
        raise RuntimeError("git ls-tree returned duplicate HEAD tree paths")
    return entries


def _head_blob_bytes(entries: list[HeadTreeEntry]) -> dict[str, bytes]:
    """Read selected tree blobs by OID through one strictly framed cat-file batch."""
    if not entries:
        return {}

    checked_sizes = _head_blob_sizes(entries)
    requests = b"".join(f"{entry.oid}\n".encode("ascii") for entry in entries)
    out = _git_binary_output(["cat-file", "--batch"], input_data=requests)
    cursor = 0
    blobs: dict[str, bytes] = {}
    for entry in entries:
        relative = entry.relative_path
        header_end = out.find(b"\n", cursor)
        if header_end < 0:
            raise RuntimeError(
                f"git cat-file --batch omitted the header for {relative!r}; refusing to package"
            )
        header = out[cursor:header_end]
        cursor = header_end + 1
        fields = header.split(b" ")
        if (
            len(fields) != 3
            or re.fullmatch(rb"[0-9a-f]{40}", fields[0]) is None
            or fields[0].decode("ascii") != entry.oid
            or fields[1] != b"blob"
            or re.fullmatch(rb"(?:0|[1-9][0-9]*)", fields[2]) is None
            or int(fields[2]) != checked_sizes[relative]
        ):
            raise RuntimeError(
                f"git cat-file --batch returned an invalid blob header for {relative!r}; "
                "refusing to package"
            )
        size = int(fields[2])
        content_end = cursor + size
        if content_end >= len(out) or out[content_end : content_end + 1] != b"\n":
            raise RuntimeError(
                f"git cat-file --batch returned invalid blob framing for {relative!r}; "
                "refusing to package"
            )
        blobs[relative] = out[cursor:content_end]
        cursor = content_end + 1

    if cursor != len(out):
        raise RuntimeError("git cat-file --batch returned trailing data; refusing to package")
    return blobs


def _head_blob_sizes(entries: list[HeadTreeEntry]) -> dict[str, int]:
    """Validate object types/sizes and enforce bounds before capturing blob content."""
    requests = b"".join(f"{entry.oid}\n".encode("ascii") for entry in entries)
    out = _git_binary_output(["cat-file", "--batch-check"], input_data=requests)
    cursor = 0
    total = 0
    sizes: dict[str, int] = {}
    for entry in entries:
        header_end = out.find(b"\n", cursor)
        if header_end < 0:
            raise RuntimeError(
                f"git cat-file --batch-check omitted {entry.relative_path!r}; refusing"
            )
        fields = out[cursor:header_end].split(b" ")
        cursor = header_end + 1
        if (
            len(fields) != 3
            or re.fullmatch(rb"[0-9a-f]{40}", fields[0]) is None
            or fields[0].decode("ascii") != entry.oid
            or fields[1] != b"blob"
            or re.fullmatch(rb"(?:0|[1-9][0-9]*)", fields[2]) is None
        ):
            raise RuntimeError(
                f"git cat-file --batch-check returned an invalid blob header for "
                f"{entry.relative_path!r}; refusing"
            )
        size = int(fields[2])
        if size > MAX_HEAD_BLOB_BYTES:
            raise RuntimeError(
                f"single HEAD blob {entry.relative_path!r} is {size} bytes, exceeding "
                f"the {MAX_HEAD_BLOB_BYTES}-byte release limit"
            )
        total += size
        if total > MAX_TOTAL_HEAD_BLOB_BYTES:
            raise RuntimeError(
                f"total HEAD blob bytes {total} exceed the "
                f"{MAX_TOTAL_HEAD_BLOB_BYTES}-byte release limit"
            )
        sizes[entry.relative_path] = size
    if cursor != len(out):
        raise RuntimeError("git cat-file --batch-check returned trailing data; refusing")
    return sizes


def collect_files(
    exclude_paths: set[Path] | None = None,
    *,
    revision: str = "HEAD",
) -> list[HeadTreeEntry]:
    excluded = {
        relative
        for path in (exclude_paths or set())
        if (relative := _filesystem_path_to_repo_relative(path)) is not None
    }
    files = [
        entry for entry in _head_tree_files(revision)
        if entry.relative_path not in excluded
        and should_include(_repo_path(entry.relative_path))
    ]
    if len(files) > MAX_SELECTED_ENTRIES:
        raise RuntimeError(
            f"selected entry count {len(files)} exceeds the "
            f"{MAX_SELECTED_ENTRIES}-entry release limit"
        )
    return sorted(files, key=lambda item: item.relative_path)


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


def _paths_differing_from_revision(revision: str) -> set[str]:
    """Tracked paths whose worktree/index content differs from captured commit.

    This is git's own content comparison, which is eol-normalized: with
    ``core.autocrlf=true`` most worktree files differ from their HEAD blob at the
    byte level while being identical as far as git is concerned. Comparing raw
    bytes instead would refuse every build on a CRLF checkout, so "differs from
    revision" means "``git diff <commit>`` reports it". Archive bytes themselves
    are read from the same captured commit and remain reproducible across EOLs.
    """
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise RuntimeError(f"dirty-path revision {revision!r} is not a captured commit")
    records = _git_nul_records(
        ["diff", "--name-only", "-z", revision, "--", *_release_pathspecs()],
        max_bytes=MAX_GIT_NUL_LISTING_BYTES,
        max_records=MAX_GIT_NUL_LISTING_RECORDS,
    )
    return {
        _checked_repo_relative_path(raw)
        for raw in records
    }


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
    absolute = _lexical_absolute(metadata_override)
    if absolute == _lexical_absolute(ROOT / METADATA_RELPATH):
        raise RuntimeError(
            "--metadata must be a temporary copy, not the tracked metadata.yaml; "
            "refusing to package"
        )
    return absolute


def _same_stable_file_identity(
    left: os.stat_result,
    right: os.stat_result,
) -> bool | None:
    if not left.st_ino or not right.st_ino:
        return None
    return left.st_dev == right.st_dev and left.st_ino == right.st_ino


def _read_metadata_override(metadata_override: Path | None) -> bytes | None:
    """Read a bounded regular override without accepting a symlink or directory."""
    checked = _checked_metadata_override(metadata_override)
    if checked is None:
        return None
    try:
        before = os.lstat(checked)
    except OSError as exc:
        raise RuntimeError(f"cannot stat metadata override {checked}; refusing") from exc
    if stat.S_ISLNK(before.st_mode):
        raise RuntimeError("metadata override must not be a symlink; refusing")
    if not stat.S_ISREG(before.st_mode):
        raise RuntimeError("metadata override must be a regular file; refusing")
    if before.st_size > MAX_METADATA_OVERRIDE_BYTES:
        raise RuntimeError(
            f"metadata override is {before.st_size} bytes, exceeding the "
            f"{MAX_METADATA_OVERRIDE_BYTES}-byte release limit"
        )

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(checked, flags)
    except OSError as exc:
        raise RuntimeError(f"cannot open metadata override {checked}; refusing") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise RuntimeError("metadata override must remain a regular file; refusing")
        if _same_stable_file_identity(before, opened) is False:
            raise RuntimeError("metadata override changed before it was opened; refusing")

        tracked_metadata = _lexical_absolute(ROOT / METADATA_RELPATH)
        try:
            tracked_stat = os.stat(tracked_metadata)
        except FileNotFoundError:
            tracked_stat = None
        except OSError as exc:
            raise RuntimeError("cannot identify tracked metadata.yaml; refusing") from exc
        same_as_tracked = (
            _same_stable_file_identity(opened, tracked_stat)
            if tracked_stat is not None
            else False
        )
        if same_as_tracked is not True and tracked_stat is not None:
            try:
                same_as_tracked = os.path.samefile(checked, tracked_metadata)
            except OSError:
                same_as_tracked = False
        if same_as_tracked:
            raise RuntimeError(
                "metadata override aliases the same file as tracked metadata.yaml; refusing"
            )

        chunks: list[bytes] = []
        remaining = MAX_METADATA_OVERRIDE_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
    finally:
        os.close(descriptor)

    try:
        after = os.lstat(checked)
    except OSError as exc:
        raise RuntimeError("metadata override changed while being read; refusing") from exc
    if (
        stat.S_ISLNK(after.st_mode)
        or not stat.S_ISREG(after.st_mode)
        or len(data) != opened.st_size
        or len(data) != after.st_size
        or (opened.st_ino and after.st_ino and opened.st_ino != after.st_ino)
        or (opened.st_dev and after.st_dev and opened.st_dev != after.st_dev)
    ):
        raise RuntimeError("metadata override changed while being read; refusing")
    if len(data) > MAX_METADATA_OVERRIDE_BYTES:
        raise RuntimeError(
            f"metadata override is over {MAX_METADATA_OVERRIDE_BYTES} bytes; refusing"
        )
    return data


def _read_metadata_version(data: bytes) -> str:
    matches = _VERSION_PATTERN.findall(data.decode("utf-8"))
    if len(matches) != 1:
        raise RuntimeError(
            f"metadata.yaml must declare exactly one top-level version (found {len(matches)})"
        )
    raw_value = matches[0].strip()
    if not raw_value:
        raise RuntimeError("metadata.yaml version must not be empty")
    if raw_value[0] in {"'", '"'}:
        quote = raw_value[0]
        if len(raw_value) < 2 or raw_value[-1] != quote:
            raise RuntimeError(
                "metadata.yaml version has an unmatched outer quote; refusing to package"
            )
        version = raw_value[1:-1]
    else:
        version = raw_value
    _metadata_channel_for_version(version)
    return version


class _ModulePluginVersionWriteVisitor(ast.NodeVisitor):
    """Find bindings that can change the module-level ``PLUGIN_VERSION`` name."""

    def __init__(self) -> None:
        self.writes: list[ast.AST] = []

    def _record_binding(self, name: str | None, node: ast.AST) -> None:
        if name == "PLUGIN_VERSION":
            self.writes.append(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id == "PLUGIN_VERSION" and isinstance(node.ctx, (ast.Store, ast.Del)):
            self.writes.append(node)

    def _visit_function_header(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._record_binding(node.name, node)
        for decorator in node.decorator_list:
            self.visit(decorator)
        self.visit(node.args)
        if node.returns is not None:
            self.visit(node.returns)
        for type_param in getattr(node, "type_params", ()):  # Python 3.12+
            self.visit(type_param)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function_header(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function_header(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        # Defaults/annotations execute in the containing scope; the body does not.
        self.visit(node.args)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._record_binding(node.name, node)
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword)
        for type_param in getattr(node, "type_params", ()):  # Python 3.12+
            self.visit(type_param)
        # The class body executes in a separate namespace, not the module namespace.

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._record_binding(alias.asname or alias.name.split(".", 1)[0], node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self._record_binding(alias.asname or alias.name, node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self._record_binding(node.name, node)
        if node.type is not None:
            self.visit(node.type)
        for statement in node.body:
            self.visit(statement)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        self._record_binding(node.name, node)
        self.generic_visit(node)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        self._record_binding(node.name, node)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        self._record_binding(node.rest, node)
        self.generic_visit(node)


def _literal_string(node: ast.AST, label: str) -> str:
    try:
        value = ast.literal_eval(node)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{label} must be a string literal; refusing to package") from exc
    if not isinstance(value, str):
        raise RuntimeError(f"{label} must be a string literal; refusing to package")
    return value


def _main_release_identity_nodes(
    data: bytes,
) -> tuple[str, str, ast.expr, ast.expr]:
    try:
        tree = ast.parse(data.decode("utf-8"), filename=str(MAIN_RELPATH))
    except (SyntaxError, UnicodeDecodeError) as exc:
        raise RuntimeError("cannot parse main.py release identity; refusing to package") from exc

    direct_assignments: list[tuple[ast.Assign, ast.Name]] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            direct_assignments.extend(
                (node, target)
                for target in node.targets
                if isinstance(target, ast.Name) and target.id == "PLUGIN_VERSION"
            )

    write_visitor = _ModulePluginVersionWriteVisitor()
    write_visitor.visit(tree)
    if (
        len(direct_assignments) != 1
        or len(write_visitor.writes) != 1
        or write_visitor.writes[0] is not direct_assignments[0][1]
    ):
        raise RuntimeError(
            "release identity requires exactly one PLUGIN_VERSION module-scope write, "
            "as a direct string assignment; refusing to package"
        )

    plugin_node = direct_assignments[0][0].value
    plugin_version = _literal_string(plugin_node, "PLUGIN_VERSION")

    register_nodes: list[ast.expr] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for decorator in node.decorator_list:
            if not (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Name)
                and decorator.func.id == "register"
            ):
                continue
            if len(decorator.args) < 4:
                raise RuntimeError(
                    "@register must declare its version as the fourth argument; "
                    "refusing to package"
                )
            register_nodes.append(decorator.args[3])

    if len(register_nodes) != 1:
        raise RuntimeError(
            "release identity requires exactly one @register version; refusing to package"
        )
    register_node = register_nodes[0]
    register_version = _literal_string(register_node, "@register version")
    return plugin_version, register_version, plugin_node, register_node


def _read_main_release_identity(data: bytes) -> tuple[str, str]:
    plugin_version, register_version, _plugin_node, _register_node = (
        _main_release_identity_nodes(data)
    )
    return plugin_version, register_version


def _ast_source_span(data: bytes, node: ast.AST) -> tuple[int, int]:
    if (
        not hasattr(node, "lineno")
        or not hasattr(node, "end_lineno")
        or node.end_lineno is None
        or node.end_col_offset is None
    ):
        raise RuntimeError("main.py release identity lacks source positions; refusing to package")
    lines = data.splitlines(keepends=True)
    if node.lineno < 1 or node.end_lineno > len(lines):
        raise RuntimeError("main.py release identity source position is invalid; refusing to package")
    start = sum(len(line) for line in lines[: node.lineno - 1]) + node.col_offset
    end = sum(len(line) for line in lines[: node.end_lineno - 1]) + node.end_col_offset
    if start < 0 or end <= start or end > len(data):
        raise RuntimeError("main.py release identity source span is invalid; refusing to package")
    return start, end


def _render_main_release_identity(data: bytes, version: str) -> bytes:
    plugin_version, register_version, plugin_node, register_node = (
        _main_release_identity_nodes(data)
    )
    if plugin_version != register_version:
        raise RuntimeError("main.py release identities disagree; refusing to package")

    replacement = repr(version).encode("utf-8")
    spans = sorted(
        (_ast_source_span(data, plugin_node), _ast_source_span(data, register_node)),
        reverse=True,
    )
    rendered = data
    previous_start = len(data)
    for (start, end) in spans:
        if end > previous_start:
            raise RuntimeError("main.py release identity spans overlap; refusing to package")
        rendered = rendered[:start] + replacement + rendered[end:]
        previous_start = start

    _validate_release_identity(version, rendered)
    return rendered


def _validate_release_identity(metadata_version: str, main_data: bytes) -> None:
    plugin_version, register_version = _read_main_release_identity(main_data)
    if metadata_version != plugin_version or metadata_version != register_version:
        raise RuntimeError(
            "release identity mismatch: "
            f"metadata.yaml={metadata_version!r}, "
            f"PLUGIN_VERSION={plugin_version!r}, "
            f"@register={register_version!r}; refusing to package"
        )


def _metadata_channel_for_version(version: str) -> str:
    if _STABLE_VERSION_PATTERN.fullmatch(version):
        return "stable"
    if _GREY_VERSION_PATTERN.fullmatch(version):
        return "grey"
    raise RuntimeError(
        f"metadata version {version!r} must be X.Y.Z or X.Y.Z-grey.N; "
        "refusing to package"
    )


def _validate_metadata_channel(version: str, channel: str) -> None:
    metadata_channel = _metadata_channel_for_version(version)
    if channel == "grey" and metadata_channel != "grey":
        raise RuntimeError(
            f"grey channel requires grey metadata, got version {version!r}; refusing to package"
        )
    if channel == "stable" and metadata_channel != "stable":
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


def _untracked_v3_sources(tracked: set[str]) -> list[Path]:
    missing: list[Path] = []
    for relative in V3_SOURCE_DIRS:
        for path in sorted((ROOT / relative).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            relative_path = path.relative_to(ROOT).as_posix()
            if relative_path not in tracked:
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
    *,
    commit: str,
) -> list[tuple[str, bytes]]:
    """Build the full (arcname, uncompressed bytes) set for one channel."""
    override_metadata = _read_metadata_override(metadata_override)
    flags_source = BUILD_FLAGS_RELPATH.as_posix()
    main_source = MAIN_RELPATH.as_posix()
    metadata_source = METADATA_RELPATH.as_posix()
    replaced_sources = {flags_source}
    dirty_exempt_sources = {flags_source}
    if override_metadata is not None:
        replaced_sources.update((main_source, metadata_source))
        # The checked-in metadata is irrelevant when a separate override is
        # packaged. main.py remains a tracked input: generated main.py is derived
        # from it, so a dirty main must still fail the HEAD-cleanliness gate.
        dirty_exempt_sources.add(metadata_source)

    files = collect_files(exclude_paths=exclude_paths, revision=commit)
    head_blobs = _head_blob_bytes(files)
    excluded = {
        relative
        for path in (exclude_paths or set())
        if (relative := _filesystem_path_to_repo_relative(path)) is not None
    }

    dirty = {
        relative
        for relative in _paths_differing_from_revision(commit)
        if relative not in excluded
        and relative not in dirty_exempt_sources
        and should_include(_repo_path(relative))
    }
    if dirty:
        listed = ", ".join(sorted(dirty))
        raise RuntimeError(
            f"tracked archive inputs differ from committed HEAD: {listed}; refusing to package"
        )

    try:
        checked_metadata = head_blobs[metadata_source]
        checked_main = head_blobs[main_source]
    except KeyError as exc:
        raise RuntimeError("release identity files missing from committed HEAD; refusing") from exc
    checked_version = _read_metadata_version(checked_metadata)
    _validate_release_identity(checked_version, checked_main)

    entries: list[tuple[str, bytes]] = [(f"{PLUGIN_NAME}/", b"")]
    for entry in files:
        relative = entry.relative_path
        if relative in replaced_sources:
            continue  # replaced below; never appended as a duplicate
        arcname = _normalize_arcname(f"{PLUGIN_NAME}/{relative}")
        entries.append((arcname, head_blobs[relative]))

    flags = _render_build_flags(channel)
    _verify_generated_flags(flags, channel)
    entries.append((BUILD_FLAGS_ARCNAME, flags))
    if override_metadata is not None:
        override_version = _read_metadata_version(override_metadata)
        entries.append(
            (
                MAIN_ARCNAME,
                _render_main_release_identity(checked_main, override_version),
            )
        )
        entries.append((METADATA_ARCNAME, override_metadata))

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


def _reserve_sibling_temp(target: Path, marker: str) -> Path:
    try:
        descriptor, raw_path = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=f".{marker}.tmp",
            dir=target.parent,
        )
    except OSError as exc:
        raise RuntimeError(
            f"cannot reserve temporary {marker} beside {target}; refusing to package"
        ) from exc
    os.close(descriptor)
    return Path(raw_path)


def _discard_file(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _commit_output_pair(
    new_output: Path,
    new_checksum: Path,
    output: Path,
    checksum: Path,
) -> None:
    """Install ZIP + checksum as a rollback-safe two-file transaction."""
    output_backup_stage = 1
    checksum_backup_stage = 2
    output_install_stage = 3
    checksum_install_stage = 4

    output_existed = os.path.lexists(output)
    checksum_existed = os.path.lexists(checksum)
    output_backup: Path | None = None
    checksum_backup: Path | None = None
    try:
        if output_existed:
            output_backup = _reserve_sibling_temp(output, "zip-backup")
        if checksum_existed:
            checksum_backup = _reserve_sibling_temp(checksum, "checksum-backup")
    except BaseException:
        _discard_file(output_backup)
        _discard_file(checksum_backup)
        raise

    attempted_stage = 0
    # Conservative until filesystem facts prove otherwise: an interrupt during
    # reconciliation must leave a possibly-old backup in place, never delete it.
    output_backed_up = output_backup is not None
    checksum_backed_up = checksum_backup is not None
    output_installed = False
    checksum_installed = False
    commit_succeeded = False
    try:
        if output_backup is not None:
            attempted_stage = output_backup_stage
            os.replace(output, output_backup)
        if checksum_backup is not None:
            attempted_stage = checksum_backup_stage
            os.replace(checksum, checksum_backup)

        attempted_stage = output_install_stage
        os.replace(new_output, output)
        attempted_stage = checksum_install_stage
        os.replace(new_checksum, checksum)
        commit_succeeded = True
    except BaseException as exc:
        commit_succeeded = False

        def stage_completed(stage: int, source: Path, destination: Path) -> bool:
            return attempted_stage > stage or (
                attempted_stage == stage
                and not os.path.lexists(source)
                and os.path.lexists(destination)
            )

        output_backed_up = (
            output_backup is not None
            and stage_completed(output_backup_stage, output, output_backup)
        )
        checksum_backed_up = (
            checksum_backup is not None
            and stage_completed(checksum_backup_stage, checksum, checksum_backup)
        )
        output_installed = stage_completed(output_install_stage, new_output, output)
        checksum_installed = stage_completed(
            checksum_install_stage,
            new_checksum,
            checksum,
        )

        rollback_errors: list[BaseException] = []
        rollback_interrupts: list[BaseException] = []

        def restore_backup(backup: Path, target: Path) -> bool:
            """Return True only while `backup` still holds the old file."""
            try:
                os.replace(backup, target)
            except BaseException as rollback_exc:
                if not os.path.lexists(backup) and os.path.lexists(target):
                    rollback_interrupts.append(rollback_exc)
                    return False
                rollback_errors.append(rollback_exc)
                return True
            return False

        def remove_new_target(target: Path) -> None:
            try:
                _discard_file(target)
            except BaseException as rollback_exc:
                if os.path.lexists(target):
                    rollback_errors.append(rollback_exc)
                else:
                    rollback_interrupts.append(rollback_exc)

        if checksum_backed_up and checksum_backup is not None:
            checksum_backed_up = restore_backup(checksum_backup, checksum)
        elif checksum_installed and not checksum_existed:
            remove_new_target(checksum)

        if output_backed_up and output_backup is not None:
            output_backed_up = restore_backup(output_backup, output)
        elif output_installed and not output_existed:
            remove_new_target(output)

        if rollback_errors:
            details = "; ".join(str(error) for error in rollback_errors)
            preserved = [
                str(path)
                for path, still_holds_old_data in (
                    (output_backup, output_backed_up),
                    (checksum_backup, checksum_backed_up),
                )
                if path is not None and still_holds_old_data
            ]
            preserved_message = ", ".join(preserved) if preserved else "none"
            raise RuntimeError(
                "package pair commit failed and rollback was incomplete; "
                f"preserved backups: {preserved_message}; errors: {details}"
            ) from exc
        for rollback_interrupt in rollback_interrupts:
            if isinstance(rollback_interrupt, (KeyboardInterrupt, SystemExit)):
                raise rollback_interrupt
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise RuntimeError(
            "package pair commit failed; previous ZIP and checksum were restored"
        ) from exc
    finally:
        _discard_file(new_output)
        _discard_file(new_checksum)
        if commit_succeeded or not output_backed_up:
            _discard_file(output_backup)
        if commit_succeeded or not checksum_backed_up:
            _discard_file(checksum_backup)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_output_pair(
    output: Path,
    checksum: Path,
    entries: list[tuple[str, bytes]],
    *,
    tracked_sources: set[str],
    metadata_override: Path | None,
) -> None:
    archive_temp: Path | None = None
    checksum_temp: Path | None = None
    try:
        archive_temp = _reserve_sibling_temp(output, "zip")
        checksum_temp = _reserve_sibling_temp(checksum, "checksum")
        _write_archive(archive_temp, entries)
        with checksum_temp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(f"{_file_sha256(archive_temp)}  {output.name}\n")
            handle.flush()
            os.fsync(handle.fileno())
        fresh_tracked_sources = _tracked_source_paths()
        if fresh_tracked_sources != tracked_sources:
            raise RuntimeError(
                "tracked source set changed while the package was being built; "
                "refusing to commit outputs"
            )
        _validate_output_targets(
            output,
            checksum,
            fresh_tracked_sources,
            metadata_override,
        )
        _commit_output_pair(archive_temp, checksum_temp, output, checksum)
        archive_temp = None
        checksum_temp = None
    finally:
        _discard_file(archive_temp)
        _discard_file(checksum_temp)


def build_package(
    output: Path,
    channel: str,
    metadata_override: Path | None = None,
) -> Path:
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel!r}; expected one of {list(CHANNELS)}")

    output, checksum_path = _checked_output_locations(output)
    checked_metadata_override = _checked_metadata_override(metadata_override)
    commit = _head_commit()
    tracked_v3_sources = _tracked_files()
    tracked_sources = _tracked_source_paths()
    _validate_output_targets(
        output,
        checksum_path,
        tracked_sources,
        checked_metadata_override,
    )

    untracked = _untracked_v3_sources(tracked_v3_sources)
    if untracked:
        listed = ", ".join(str(path.relative_to(ROOT)) for path in untracked)
        raise RuntimeError(f"untracked v3 source files: {listed}; refusing to package")

    output.parent.mkdir(parents=True, exist_ok=True)
    _validate_output_targets(
        output,
        checksum_path,
        tracked_sources,
        checked_metadata_override,
    )

    entries = _archive_entries(
        channel,
        metadata_override=metadata_override,
        exclude_paths={output, checksum_path},
        commit=commit,
    )
    _validate_archive_entries(entries)

    entry_map = dict(entries)
    try:
        effective_metadata = _read_metadata_version(entry_map[METADATA_ARCNAME])
        effective_main = entry_map[MAIN_ARCNAME]
    except KeyError as exc:
        raise RuntimeError("release identity files missing from archive; refusing to package") from exc
    _validate_release_identity(effective_metadata, effective_main)
    _validate_metadata_channel(effective_metadata, channel)
    version = effective_metadata

    generated = {name: content for name, content in entries if name == BUILD_FLAGS_ARCNAME}
    if metadata_override is not None:
        generated.update(
            {
                name: content
                for name, content in entries
                if name in {MAIN_ARCNAME, METADATA_ARCNAME}
            }
        )
    if BUILD_FLAGS_ARCNAME not in generated:
        raise RuntimeError("generated build flags missing from archive; refusing to package")

    manifest = _render_manifest(channel, version, commit, generated, payload_digest(entries))
    # The whole-zip digest describes the closed file, so it can only live beside
    # it — never inside the archive it is supposed to authenticate. Both files
    # are completed as siblings before the rollback-safe pair commit begins.
    _write_output_pair(
        output,
        checksum_path,
        _sort_entries([*entries, (MANIFEST_ARCNAME, manifest)]),
        tracked_sources=tracked_sources,
        metadata_override=checked_metadata_override,
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
