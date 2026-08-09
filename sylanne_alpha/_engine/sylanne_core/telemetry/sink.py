"""Privacy-safe distillation corpus sink for the v3 student model.

When enabled via :class:`~sylanne_core.config.SylanneConfig`, this appends one
numeric training tuple per assessed tick to a local JSONL dataset, to be used
later for OFFLINE distillation of a small student model. It is OFF by default
and collects nothing unless explicitly turned on.

Privacy contract (this is multi-user data):
- Never writes raw message text or any PII — only numeric features, the raw
  assessor affect scalars, and a salted SHA-256 session hash.
- Local-only: a plain file append via stdlib; there is no network code path.
- The output path is confined to a dedicated telemetry sub-directory and is
  validated against path traversal.
- The dataset file is created with mode 0o600 (effective on POSIX).

Hot path: when the sink is disabled every method returns on a single boolean
check, so a caller that has not opted in pays no measurable cost.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from threading import Lock
from typing import Any, TextIO

logger = logging.getLogger("sylanne_core")

# Bump when the row schema changes so offline parsers can branch on the version.
FEATURE_SCHEMA_VERSION = 1

# Numeric feature columns captured per tick, in stable order. Offline code reads
# this tuple to assemble the input matrix. Strictly numeric — never raw text.
AFFECT_CONTEXT_FIELDS: tuple[str, ...] = (
    "f_warmth",
    "f_arousal",
    "f_valence",
    "f_tension",
    "f_curiosity",
    "f_repair_pressure",
    "f_expression_drive",
    "f_boundary_firmness",
    "f_coherence",
    "f_void_pressure",
    "f_active_voids",
    "f_surprise",
    "f_boundary_stability",
    "f_resonance_energy",
    "f_sync_order",
    "f_phi",
    "f_plasticity_ratio",
    "f_need_contact",
    "f_need_quiet",
    "f_need_repair",
    "f_need_expression",
    "f_boundary_pressure",
    "f_sovereignty",
    "f_interruption_budget",
    "f_cooldown",
    "f_affect_debt",
)


def anonymize_session(session_key: str, salt: str) -> str:
    """Return a non-reversible 16-hex session id = SHA-256(salt + ':' + key).

    The raw session key never enters the dataset and the salt is never written,
    so rows group per user offline without exposing identity. Without the local
    salt the hash cannot be reversed or correlated across deployments.
    """
    digest = hashlib.sha256(f"{salt}:{session_key}".encode()).hexdigest()
    return digest[:16]


def _resolve_under_base(path: Path, base: Path) -> Path:
    """Resolve ``path`` and assert it stays under ``base`` (anti path-traversal).

    Any caller-supplied path that escapes the telemetry directory (e.g. via
    ``..`` segments) is rejected before a single byte is written.
    """
    resolved = path.expanduser().resolve()
    base_resolved = base.expanduser().resolve()
    if not resolved.is_relative_to(base_resolved):
        raise ValueError(f"telemetry path {resolved} escapes base {base_resolved}")
    return resolved


class DistillationSink:
    """Append-only, thread-safe local JSONL writer for distillation tuples.

    Construct one instance per engine (shared across all sessions). When
    ``enabled`` is False the object opens no file and every method is a no-op,
    so a disabled sink is safe to attach unconditionally.
    """

    __slots__ = ("_enabled", "_fh", "_lock", "_path", "_salt")

    _enabled: bool
    _path: Path | None
    _salt: str
    _lock: Lock
    _fh: TextIO | None

    def __init__(
        self,
        *,
        enabled: bool,
        path: Path | None,
        salt: str,
        base_dir: Path,
    ) -> None:
        self._enabled = bool(enabled) and path is not None
        self._salt = salt
        self._lock = Lock()
        self._fh = None
        self._path = None
        if self._enabled and path is not None:
            resolved = _resolve_under_base(path, base_dir)
            resolved.parent.mkdir(parents=True, exist_ok=True)
            # Create restrictively (0o600) so a multi-user host does not expose
            # the corpus by default; the mode is ignored on Windows but harmless.
            if not resolved.exists():
                os.close(os.open(resolved, os.O_CREAT | os.O_WRONLY, 0o600))
            self._fh = resolved.open("a", encoding="utf-8")
            self._path = resolved

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def path(self) -> Path | None:
        return self._path

    def session_hash(self, session_key: str) -> str:
        """Salted, non-reversible hash of ``session_key`` for grouping rows."""
        return anonymize_session(session_key, self._salt)

    def record_tick(self, *, session_key: str, row: dict[str, Any]) -> None:
        """Append one tuple as a compact JSONL line. No-op when disabled.

        ``row`` must contain numeric features only; this writer stamps the
        schema version and the salted session hash and performs no text capture
        of its own. The raw ``session_key`` is hashed here and never written.
        """
        if not self._enabled or self._fh is None:
            return
        full: dict[str, Any] = {
            "schema_version": FEATURE_SCHEMA_VERSION,
            "session_hash": anonymize_session(session_key, self._salt),
            **row,
        }
        line = json.dumps(full, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self._fh.write(line + "\n")
            self._fh.flush()

    def close(self) -> None:
        """Flush and close the dataset file. Idempotent and safe when disabled."""
        if self._fh is None:
            return
        with self._lock:
            if self._fh is not None:
                try:
                    self._fh.flush()
                    self._fh.close()
                finally:
                    self._fh = None
