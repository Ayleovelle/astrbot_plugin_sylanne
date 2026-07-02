"""Per-copy SDK identity: a write-once, persistent UUID for each installed copy.

Each physical install of sylanne_core gets ONE stable id, minted on first import
and persisted to ``<package_dir>/_identity.json``. The id is purely a diagnostic
LABEL — it tells copies apart so the runtime can spot version skew between two
vendored copies and report what is loaded via health()/list_shared(). It is NOT
an election token and NOT a security credential: in one shared process there is
no trust boundary, so the record is plaintext and cooperative.

Resolution order:
  1. If ``_identity.json`` exists and parses, adopt its ``copy_id`` (stable across
     restarts AND across in-place version upgrades — the file outlives them).
  2. Otherwise mint ``uuid4().hex`` and write it ONCE, race-safely (O_EXCL: the
     first writer wins; a concurrent loser reads the winner's file).
  3. If the package dir is not writable (read-only install), fall back to a
     deterministic path-derived hash. That id is NOT persistent (it changes if
     the copy moves) and is flagged ``persistent=False``.

The uuid and the path hash are opaque labels only — never sorted on, never
trusted. The hash here just shortens a long path into a label; we never read the
path back out of it, which is why hashing is fine for this and would be wrong for
anything we needed to order or authenticate.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_IDENTITY_FILENAME = "_identity.json"


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _short(copy_id: str) -> str:
    """Human-scannable log label, e.g. 'sylc-0d7f4e2a'."""
    stem = copy_id.replace("-", "")[:8]
    return f"sylc-{stem}"


def _path_hash_id(pkg_dir: Path) -> str:
    """Deterministic fallback id from the normalized package path (non-persistent)."""
    key = os.path.normcase(str(pkg_dir)).encode("utf-8")
    return hashlib.blake2s(key, digest_size=4).hexdigest()  # 8 hex chars


def _read_identity(path: Path) -> dict[str, Any] | None:
    """Return the parsed identity record, or None if missing/corrupt."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if isinstance(data, dict) and isinstance(data.get("copy_id"), str) and data["copy_id"]:
        return data
    return None


def _best_effort_fsync(fileno: int) -> None:
    """fsync, ignoring failures on filesystems that do not support it (containers,
    network mounts). The identity file is diagnostic, so durability is best-effort
    and an fsync error must not nuke an otherwise-good write."""
    try:
        os.fsync(fileno)
    except OSError:
        pass


def _write_new_fd(fd: int, path: Path, record: dict[str, Any]) -> dict[str, Any] | None:
    """Write ``record`` to an already-created (O_EXCL) fd. Cleans up on failure."""
    try:
        try:
            f = os.fdopen(fd, "w", encoding="utf-8")
        except OSError:
            os.close(fd)  # fdopen failed: close the raw fd so it cannot leak
            raise
        with f:
            f.write(json.dumps(record, ensure_ascii=False))
            f.flush()
            _best_effort_fsync(f.fileno())
    except OSError:
        # Partial write: drop the half-file so a later import can re-create it cleanly.
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    return record


def _atomic_overwrite(path: Path, record: dict[str, Any]) -> dict[str, Any] | None:
    """Replace ``path`` atomically (tmp + fsync + os.replace). Used to repair a
    corrupt id file. Returns the record, or None if the dir is unwritable."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False))
            f.flush()
            _best_effort_fsync(f.fileno())
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    return record


def _mint_persistent(path: Path) -> dict[str, Any] | None:
    """Write a fresh uuid id exactly ONCE, race-safely.

    Returns the on-disk record, or None if the id could not be persisted (the
    directory is read-only, or a concurrent writer is mid-create) — the caller
    then retries the read or falls back to the path hash.
    """
    record = {"copy_id": uuid.uuid4().hex, "born": _now_utc()}
    try:
        # O_EXCL makes "create the id file" atomic across processes: exactly one
        # writer wins; every loser takes the FileExistsError branch and reads it.
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        existing = _read_identity(path)
        if existing is not None:
            return existing  # adopt the winner (None below means the file is corrupt)
        # File is present but unparseable: repair it once so a corrupt id never
        # wedges the copy permanently into the non-persistent fallback.
        return _atomic_overwrite(path, record)
    except OSError:
        return None  # read-only / unwritable dir -> caller falls back to path hash
    return _write_new_fd(fd, path, record)


def resolve_identity(pkg_dir: str | Path, version: str, module_name: str) -> dict[str, Any]:
    """Resolve this copy's identity record. Idempotent: same install -> same id.

    Args:
        pkg_dir: The directory of THIS sylanne_core copy (``Path(__file__).parent``).
        version: This copy's ``__version__`` (refreshed every load, never persisted).
        module_name: This copy's import name (e.g. ``sylanne_core`` or
            ``astrbot_plugin_x.deps.sylanne_core``), to tell vendored copies apart.

    Returns a plaintext dict: ``copy_id`` (stable label), ``short`` (log label),
    ``version``, ``module``, ``path``, ``pid``, ``persistent`` (False on the
    read-only fallback), and ``born`` (install time, or None when non-persistent).
    """
    pkg_dir = Path(pkg_dir)
    id_path = pkg_dir / _IDENTITY_FILENAME

    record = _read_identity(id_path)
    persistent = True
    if record is None:
        record = _mint_persistent(id_path)
    if record is None:
        # A concurrent writer may have been mid-create on the first pass; re-read.
        record = _read_identity(id_path)
    if record is None:
        # Unwritable dir (or unrecoverable race): deterministic, non-persistent id.
        record = {"copy_id": _path_hash_id(pkg_dir), "born": None}
        persistent = False

    copy_id = record["copy_id"]
    return {
        "copy_id": copy_id,
        "short": _short(copy_id),
        "version": version,
        "module": module_name,
        "path": str(pkg_dir),
        "pid": os.getpid(),
        "persistent": persistent,
        "born": record.get("born"),
    }
