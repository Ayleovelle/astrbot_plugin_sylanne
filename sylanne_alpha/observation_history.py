"""Privacy-safe, durable observation history for Alpha kernel snapshots.

The store deliberately persists only a small numeric projection of a kernel
snapshot. It never writes the snapshot itself, event text, prompts, memories,
or token material.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

logger = logging.getLogger("astrbot_plugin_sylanne")

SAMPLE_SCHEMA_VERSION = "sylanne.observation.sample.v1"
MANIFEST_SCHEMA_VERSION = "sylanne.observation.manifest.v1"
SCOPED_MANIFEST_SCHEMA_VERSION = "sylanne.observation.history.v2"
HISTORY_SCHEMA_VERSION = "sylanne.observation.history.v1"
DEFAULT_MAX_BYTES = 128 * 1024 * 1024
DEFAULT_SEGMENT_BYTES = 1024 * 1024

_EMOTION_KEYS = (
    "warmth",
    "arousal",
    "valence",
    "tension",
    "curiosity",
    "repair_pressure",
    "expression_drive",
    "boundary_firmness",
    "coherence",
)
_BOUNDARY_KEYS = (
    "boundary_integrity",
    "internal_entropy",
    "stability",
    "repair_rate",
    "phase_transitions",
)
_EXPRESSION_KEYS = (
    "pressure",
    "threshold",
    "silence_duration",
    "expression_count",
)
_FEEDBACK_KEYS = ("accepted", "ignored", "rejected")
_TIMING_KEYS = (
    "total_ms",
    "perception",
    "gate",
    "void_scar",
    "sheaf",
    "hgt",
    "boundary",
    "expression",
)
_COUNT_KEYS = {
    "history_len",
    "phase_transitions",
    "expression_count",
    "accepted",
    "ignored",
    "rejected",
}
_HEX_DIGEST_RE = re.compile(r"[0-9a-f]{64}")
_SEGMENT_NAME_RE = re.compile(r"segment-(\d{8})\.jsonl")
_SHORT_ENUM_RE = re.compile(r"[A-Za-z0-9_.-]{1,32}")
_SCOPE_TOKEN_RE = re.compile(r"scope_v1_[A-Za-z0-9_-]+\Z")
_TOKEN_PAYLOAD_RE = re.compile(r"[A-Za-z0-9_-]+\Z")
_CLEANUP_DIAGNOSTIC_LIMIT = 64
_CLEANUP_TRIGGERS = frozenset({"append", "duplicate", "maintenance", "regression"})
_UNFINISHED_CLEANUP_REASONS = frozenset({"budget_unsatisfiable", "cleanup_active"})


@dataclass(frozen=True, slots=True)
class CleanupResult:
    """One scoped cleanup decision.

    ``bool(result)`` remains useful to callers that only need to know whether a
    segment was removed, while the explicit fields expose the durable outcome
    for diagnostics and restart tests.
    """

    deleted_scope: str | None = None
    deleted_segment: str | None = None
    budget_unsatisfiable: bool = False
    cleanup_active: bool = False
    manifest_generation: int = 0

    def __bool__(self) -> bool:
        return self.deleted_segment is not None


class _ManifestView(Mapping[str, Any]):
    """Read-only mapping that also supports the plan's attribute notation."""

    __slots__ = ("_payload",)

    def __init__(self, payload: Mapping[str, Any]) -> None:
        self._payload = json.loads(json.dumps(payload, ensure_ascii=False))

    def __getitem__(self, key: str) -> Any:
        return self._payload[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._payload)

    def __len__(self) -> int:
        return len(self._payload)

    def __getattr__(self, name: str) -> Any:
        try:
            return self._payload[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(self._payload, ensure_ascii=False))


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _finite_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)):
        return None
    return value


def _count(value: Any, *, default: int | None = None) -> int | None:
    number = _finite_number(value)
    if number is None:
        return default
    return max(0, int(number))


def _numeric_projection(
    source: dict[str, Any],
    keys: tuple[str, ...],
) -> dict[str, int | float]:
    projected: dict[str, int | float] = {}
    for key in keys:
        value = source.get(key)
        if key in _COUNT_KEYS:
            count = _count(value)
            if count is not None:
                projected[key] = count
            continue
        number = _finite_number(value)
        if number is not None:
            projected[key] = number
    return projected


def _short_enum(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not _SHORT_ENUM_RE.fullmatch(candidate):
        return None
    return candidate


def _opaque_diagnostic_token(value: Any, prefix: str) -> bool:
    return (
        isinstance(value, str)
        and value.startswith(prefix)
        and _TOKEN_PAYLOAD_RE.fullmatch(value[len(prefix) :]) is not None
    )


def _captured_at_ms(value: Any) -> int:
    resolved = _count(value)
    if resolved is not None:
        return resolved
    return time.time_ns() // 1_000_000


def _session_key(session: str) -> str:
    return hashlib.sha256(session.encode("utf-8")).hexdigest()


def _digest_payload(row: dict[str, Any]) -> str:
    payload = {key: value for key, value in row.items() if key not in {"captured_at_ms", "digest"}}
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def project_observation(
    session_key: str,
    snapshot: dict[str, Any],
    captured_at_ms: int | None = None,
) -> dict[str, Any]:
    """Project a full kernel snapshot to the explicit observation allow-list."""

    session = str(session_key)
    source = snapshot if isinstance(snapshot, dict) else {}
    computation = _dict(source.get("computation"))
    result = _dict(source.get("_last_computation_result"))
    emotion = _numeric_projection(_dict(result.get("emotion")), _EMOTION_KEYS)

    gate_source = _dict(computation.get("gate"))
    gate: dict[str, int | float] = {}
    surprise = _finite_number(result.get("surprise"))
    if surprise is not None:
        gate["surprise"] = surprise
    gate.update(
        _numeric_projection(
            gate_source,
            ("precision", "mean_surprise", "history_len"),
        )
    )

    route_counts: dict[str, int] = {}
    for name, value in _dict(computation.get("route_counts")).items():
        safe_name = _short_enum(name)
        count = _count(value)
        if safe_name is not None and count is not None:
            route_counts[safe_name] = count
    route: dict[str, Any] = {"route_counts": route_counts}
    route_name = _short_enum(result.get("route"))
    if route_name is not None:
        route = {"route": route_name, **route}

    boundary = _numeric_projection(
        _dict(computation.get("boundary")),
        _BOUNDARY_KEYS,
    )

    expression_source = _dict(computation.get("expression"))
    expression: dict[str, Any] = _numeric_projection(
        expression_source,
        _EXPRESSION_KEYS,
    )
    drive = _finite_number(computation.get("expression_drive"))
    result_expression = _dict(result.get("expression_state"))
    if drive is None:
        drive = _finite_number(result_expression.get("drive"))
    if drive is not None:
        expression["drive"] = drive
    mode = _short_enum(result_expression.get("mode"))
    if mode is None:
        mode = _short_enum(expression_source.get("mode"))
    if mode is not None:
        expression["mode"] = mode

    feedback = _numeric_projection(
        _dict(computation.get("feedback_counts")),
        _FEEDBACK_KEYS,
    )
    timing = _numeric_projection(
        _dict(computation.get("timing")),
        _TIMING_KEYS,
    )

    row: dict[str, Any] = {
        "schema_version": SAMPLE_SCHEMA_VERSION,
        "captured_at_ms": _captured_at_ms(captured_at_ms),
        "session": session,
        "turns": _count(source.get("turns"), default=0),
        "tick_count": _count(computation.get("tick_count"), default=0),
        "groups": {
            "emotion": emotion,
            "gate": gate,
            "route": route,
            "timing": timing,
            "boundary": boundary,
            "expression": expression,
            "feedback": feedback,
        },
    }
    row["digest"] = _digest_payload(row)
    return row


class ObservationHistoryStore:
    """Append-only segmented JSONL store with legacy and scoped backends.

    The original constructor remains the ``legacy-unscoped`` compatibility
    path.  Scoped production callers use :meth:`from_scope_repository`, which
    keeps one repository-owned manifest and partitions bytes by opaque
    ``SessionScope.storage_token``.
    """

    def __init__(
        self,
        root: str | Path,
        max_bytes_provider: Callable[[], int],
        *,
        segment_bytes: int = DEFAULT_SEGMENT_BYTES,
        target_ratio: float = 0.9,
    ) -> None:
        if int(segment_bytes) <= 0:
            raise ValueError("segment_bytes must be positive")
        if isinstance(target_ratio, bool) or not isinstance(target_ratio, (int, float)):
            raise TypeError("target_ratio must be a finite number")
        resolved_target_ratio = float(target_ratio)
        if not math.isfinite(resolved_target_ratio) or not 0.0 < resolved_target_ratio <= 1.0:
            raise ValueError("target_ratio must be in (0, 1]")
        self._root = Path(root)
        self._max_bytes_provider = max_bytes_provider
        self._segment_bytes = int(segment_bytes)
        self._target_ratio = resolved_target_ratio
        self._lock = threading.RLock()
        self._scope_repository: Any | None = None
        self._scoped = False
        self._manifest_path = self._root / "manifest.json"
        with self._lock:
            self._root.mkdir(parents=True, exist_ok=True)
            self._manifest = self._load_or_rebuild_manifest()

    @classmethod
    def from_scope_repository(
        cls,
        repository: Any,
        max_bytes_provider: Callable[[], int] | None = None,
        *,
        limit_bytes: int | None = None,
        segment_bytes: int = DEFAULT_SEGMENT_BYTES,
        target_ratio: float = 0.9,
    ) -> "ObservationHistoryStore":
        """Construct the single scoped store owned by ``ScopeRepository``.

        ``limit_bytes`` is a small test/configuration convenience; production
        callers should pass a provider so changing the setting takes effect on
        the next append or maintenance cycle.
        """

        if repository is None:
            raise ValueError("repository is required for scoped history")
        if max_bytes_provider is not None and limit_bytes is not None:
            raise ValueError("provide max_bytes_provider or limit_bytes, not both")
        if max_bytes_provider is None:
            fixed = DEFAULT_MAX_BYTES if limit_bytes is None else int(limit_bytes)
            max_bytes_provider = lambda fixed=fixed: fixed
        if isinstance(target_ratio, bool) or not isinstance(target_ratio, (int, float)):
            raise TypeError("target_ratio must be a finite number")
        resolved_target_ratio = float(target_ratio)
        if not math.isfinite(resolved_target_ratio) or not 0.0 < resolved_target_ratio <= 1.0:
            raise ValueError("target_ratio must be in (0, 1]")
        root = Path(repository.observation_root)
        instance = cls.__new__(cls)
        if int(segment_bytes) <= 0:
            raise ValueError("segment_bytes must be positive")
        instance._root = root
        instance._max_bytes_provider = max_bytes_provider
        instance._segment_bytes = int(segment_bytes)
        instance._target_ratio = resolved_target_ratio
        instance._lock = threading.RLock()
        instance._scope_repository = repository
        instance._scoped = True
        instance._manifest_path = Path(repository.observation_manifest_path)
        with instance._lock, repository.transaction():
            root.mkdir(parents=True, exist_ok=True)
            instance._manifest = instance._load_scoped_manifest()
        return instance

    @property
    def root(self) -> Path:
        return self._root

    @property
    def scoped(self) -> bool:
        return self._scoped

    @property
    def manifest(self) -> _ManifestView:
        """Return a snapshot of the current manifest for diagnostics/tests."""

        if self._scoped:
            with self._lock, self._scope_repository.transaction():
                self._refresh_scoped_manifest_locked()
                return _ManifestView(self._manifest)
        with self._lock:
            if self._scoped:
                self._refresh_scoped_manifest_locked()
            return _ManifestView(self._manifest)

    # ------------------------------------------------------------------
    # Scoped v2 API
    # ------------------------------------------------------------------

    @staticmethod
    def _require_scope(scope: Any) -> Any:
        # Import lazily to keep the legacy store importable in lightweight
        # environments where scope-v1 dependencies are not installed.
        from .scope_contracts import SessionScope

        if type(scope) is not SessionScope:
            raise ValueError("a frozen SessionScope is required")
        token = scope.storage_token
        if _SCOPE_TOKEN_RE.fullmatch(token) is None:
            raise ValueError("scope storage_token is invalid")
        return scope

    def append(
        self,
        scope: Any,
        snapshot: dict[str, Any],
        *,
        captured_at_ms: int | None = None,
    ) -> bool:
        """Append one projected sample for exactly one frozen ``SessionScope``."""

        if not self._scoped:
            raise RuntimeError("append(scope, ...) requires a scoped history store")
        scope = self._require_scope(scope)
        if not isinstance(snapshot, dict):
            raise ValueError("snapshot must be a dict")
        repository = self._scope_repository
        with self._lock, repository.transaction():
            repository._validate_session_scope_locked(scope)
            self._refresh_scoped_manifest_locked()
            row = self._scoped_row(scope, snapshot, captured_at_ms)
            scope_token = scope.storage_token
            scope_meta = self._manifest["scopes"].setdefault(
                scope_token,
                self._new_scoped_scope_meta(),
            )
            if scope_meta.get("last_digest") == row["digest"]:
                self._scoped_cleanup_once_locked(trigger="duplicate")
                return False
            line = self._row_bytes(row)
            active = self._scoped_active_segment(scope_meta)
            if active is not None and active["size"] > 0 and active["size"] + len(line) > self._segment_bytes:
                active["closed"] = True
                scope_meta["active_segment"] = None
                scope_meta["latest_closed_segment"] = active["path"]
                active = None
            if active is None:
                active = self._create_scoped_segment(scope_token, scope_meta)
            path = self._scoped_segment_path(scope_token, active["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("ab") as stream:
                stream.write(line)
                stream.flush()
                os.fsync(stream.fileno())
            active["size"] = path.stat().st_size
            active["sample_count"] += 1
            captured = int(row["captured_at_ms"])
            active["oldest_ms"] = self._earliest(active.get("oldest_ms"), captured)
            active["newest_ms"] = self._latest(active.get("newest_ms"), captured)
            scope_meta["used_bytes"] = sum(
                int(segment.get("size", 0))
                for segment in scope_meta.get("segments", [])
            )
            scope_meta["last_digest"] = row["digest"]
            self._scoped_cleanup_once_locked(trigger="append", persist=False)
            self._write_scoped_manifest_locked()
            return True

    def read(self, scope: Any) -> list[dict[str, Any]]:
        """Read all valid rows for one scope, preserving chronological order."""

        if not self._scoped:
            raise RuntimeError("read(scope) requires a scoped history store")
        scope = self._require_scope(scope)
        repository = self._scope_repository
        with self._lock, repository.transaction():
            repository._validate_session_scope_locked(scope)
            self._refresh_scoped_manifest_locked()
            metadata = self._manifest["scopes"].get(scope.storage_token)
            if not isinstance(metadata, dict):
                return []
            rows: list[dict[str, Any]] = []
            for segment in metadata.get("segments", []):
                path = self._scoped_segment_path(scope.storage_token, segment["path"])
                if not path.is_file():
                    continue
                segment_rows, _ = self._read_segment(path, expected_session=scope.storage_token)
                rows.extend(segment_rows)
            rows.sort(key=lambda row: row["captured_at_ms"])
            return rows

    def cleanup_once(self) -> CleanupResult | bool:
        """Delete at most one segment in a scoped store (legacy returns bool)."""

        if not self._scoped:
            with self._lock:
                before = bool(self._manifest.get("cleanup_active"))
                deleted = self._cleanup_once()
                after = bool(self._manifest.get("cleanup_active"))
                if deleted or before != after:
                    self._write_manifest()
                return deleted
        repository = self._scope_repository
        from .scope_repository import StaleScopeWrite

        # A repository lock normally makes the first attempt sufficient.  The
        # bounded retry is still important for injected/direct writers: reload
        # the manifest and recompute the candidate rather than deleting from a
        # stale byte ledger.
        for attempt in range(2):
            try:
                with self._lock, repository.transaction():
                    self._refresh_scoped_manifest_locked()
                    return self._scoped_cleanup_once_locked(trigger="maintenance")
            except StaleScopeWrite:
                if attempt:
                    raise
        raise AssertionError("unreachable cleanup retry")

    # These bounded seed/corruption hooks are intentionally small diagnostics
    # helpers used by restart/retention tests.  They never accept a filesystem
    # path and can only touch the repository-owned opaque scope directory.
    def _seed_closed(
        self,
        scope: Any,
        sizes: list[int] | tuple[int, ...],
        *,
        mark_latest: bool = False,
    ) -> None:
        """Seed closed segment byte counts for deterministic cleanup tests."""

        if not self._scoped:
            raise RuntimeError("seed_closed requires a scoped history store")
        scope = self._require_scope(scope)
        if type(mark_latest) is not bool:
            raise ValueError("mark_latest must be an exact bool")
        if not isinstance(sizes, (list, tuple)):
            raise ValueError("sizes must be a list or tuple")
        resolved_sizes: list[int] = []
        for size in sizes:
            if type(size) is not int or size < 0:
                raise ValueError("segment sizes must be non-negative ints")
            resolved_sizes.append(size)
        repository = self._scope_repository
        with self._lock, repository.transaction():
            repository._validate_session_scope_locked(scope)
            self._refresh_scoped_manifest_locked()
            metadata = self._manifest["scopes"].setdefault(
                scope.storage_token,
                self._new_scoped_scope_meta(),
            )
            created: list[str] = []
            for size in resolved_sizes:
                number = int(metadata["next_segment"])
                path_name = f"segment-{number:08d}.jsonl"
                metadata["next_segment"] = number + 1
                path = self._scoped_segment_path(scope.storage_token, path_name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x" * size)
                metadata["segments"].append(
                    {
                        "path": path_name,
                        "closed": True,
                        "size": size,
                        "sample_count": 0,
                        "oldest_ms": None,
                        "newest_ms": None,
                        "partial": size > 0,
                    }
                )
                created.append(path_name)
            metadata["used_bytes"] = sum(
                int(segment.get("size", 0))
                for segment in metadata["segments"]
            )
            if mark_latest and created:
                metadata["latest_closed_segment"] = created[-1]
            self._write_scoped_manifest_locked()

    def _seed_active(self, scope: Any, *, size: int = 0) -> None:
        """Seed one active segment byte count for protected-budget tests."""

        if not self._scoped:
            raise RuntimeError("seed_active requires a scoped history store")
        scope = self._require_scope(scope)
        if type(size) is not int or size < 0:
            raise ValueError("size must be a non-negative int")
        repository = self._scope_repository
        with self._lock, repository.transaction():
            repository._validate_session_scope_locked(scope)
            self._refresh_scoped_manifest_locked()
            metadata = self._manifest["scopes"].setdefault(
                scope.storage_token,
                self._new_scoped_scope_meta(),
            )
            old_active = self._scoped_active_segment(metadata)
            if old_active is not None:
                old_active["closed"] = True
                metadata["active_segment"] = None
                metadata["latest_closed_segment"] = old_active["path"]
            number = int(metadata["next_segment"])
            path_name = f"segment-{number:08d}.jsonl"
            metadata["next_segment"] = number + 1
            path = self._scoped_segment_path(scope.storage_token, path_name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x" * size)
            metadata["segments"].append(
                {
                    "path": path_name,
                    "closed": False,
                    "size": size,
                    "sample_count": 0,
                    "oldest_ms": None,
                    "newest_ms": None,
                    "partial": size > 0,
                }
            )
            metadata["active_segment"] = path_name
            metadata["used_bytes"] = sum(
                int(segment.get("size", 0))
                for segment in metadata["segments"]
            )
            self._write_scoped_manifest_locked()

    def _seed_orphaned_bytes(self, *, size: int) -> None:
        """Create opaque-unreferenced bytes for corrupt-manifest recovery tests."""

        if not self._scoped:
            raise RuntimeError("seed_orphaned_bytes requires a scoped history store")
        if type(size) is not int or size < 0:
            raise ValueError("size must be a non-negative int")
        repository = self._scope_repository
        with self._lock, repository.transaction():
            self._refresh_scoped_manifest_locked()
            orphan_dir = self._root / "scopes" / "orphaned"
            orphan_dir.mkdir(parents=True, exist_ok=True)
            path = orphan_dir / f"orphan-{os.urandom(8).hex()}.bin"
            path.write_bytes(b"x" * size)
            self._write_scoped_manifest_locked()

    def _corrupt_manifest(self) -> None:
        """Replace the scoped manifest with invalid JSON for recovery tests."""

        if not self._scoped:
            raise RuntimeError("corrupt_manifest requires a scoped history store")
        repository = self._scope_repository
        with self._lock, repository.transaction():
            self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
            self._manifest_path.write_text("{broken", encoding="utf-8")

    @staticmethod
    def _row_bytes(row: dict[str, Any]) -> bytes:
        return (
            json.dumps(
                row,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            + b"\n"
        )

    def _scoped_row(
        self,
        scope: Any,
        snapshot: dict[str, Any],
        captured_at_ms: int | None,
    ) -> dict[str, Any]:
        # Kernel snapshots retain the established privacy-safe projection.  A
        # tiny numeric shorthand is accepted for migration/tests without ever
        # persisting arbitrary text or nested payloads.
        if "computation" in snapshot or "_last_computation_result" in snapshot:
            row = project_observation(scope.storage_token, snapshot, captured_at_ms)
        else:
            captured = _captured_at_ms(captured_at_ms)
            values: dict[str, int | float] = {}
            for key, value in snapshot.items():
                if not isinstance(key, str) or _SHORT_ENUM_RE.fullmatch(key) is None:
                    continue
                number = _finite_number(value)
                if number is not None:
                    values[key] = number
            row = {
                "schema_version": SAMPLE_SCHEMA_VERSION,
                "captured_at_ms": captured,
                "session": scope.storage_token,
                "turns": 0,
                "tick_count": 0,
                "groups": {"state": values},
            }
            row["digest"] = _digest_payload(row)
        return row

    @staticmethod
    def _new_scoped_manifest() -> dict[str, Any]:
        return {
            "schema_version": SCOPED_MANIFEST_SCHEMA_VERSION,
            "generation": 0,
            "cleanup_active": False,
            "cleanup_cursor": None,
            "budget_unsatisfiable": False,
            "orphaned_bytes": 0,
            "cleanup_diagnostics": [],
            "scopes": {},
        }

    @staticmethod
    def _new_scoped_scope_meta() -> dict[str, Any]:
        return {
            "used_bytes": 0,
            "next_segment": 1,
            "active_segment": None,
            "latest_closed_segment": None,
            "last_digest": None,
            "segments": [],
        }

    def _load_scoped_manifest(self) -> dict[str, Any]:
        repository = self._scope_repository
        try:
            loaded = repository._read_json(
                self._manifest_path,
                error_label="observation history manifest",
            )
            candidate = None if loaded is None else loaded[1]
        except Exception:
            candidate = None
        if self._scoped_manifest_valid(candidate):
            normalized, diagnostics_corrupt = self._normalize_scoped_manifest(candidate)
            self._manifest = normalized
            if diagnostics_corrupt:
                self._write_scoped_manifest_locked()
            return normalized
        rebuilt = self._rebuild_scoped_manifest()
        rebuilt["generation"] = self._manifest_generation(candidate)
        self._manifest = rebuilt
        self._write_scoped_manifest_locked()
        return rebuilt

    def _refresh_scoped_manifest_locked(self) -> None:
        if not self._scoped:
            return
        repository = self._scope_repository
        try:
            loaded = repository._read_json(
                self._manifest_path,
                error_label="observation history manifest",
            )
            candidate = None if loaded is None else loaded[1]
        except Exception:
            candidate = None
        if self._scoped_manifest_valid(candidate):
            normalized, diagnostics_corrupt = self._normalize_scoped_manifest(candidate)
            self._manifest = normalized
            if diagnostics_corrupt:
                self._write_scoped_manifest_locked()
            return
        rebuilt = self._rebuild_scoped_manifest()
        rebuilt["generation"] = self._manifest_generation(candidate)
        self._manifest = rebuilt
        self._write_scoped_manifest_locked()

    @staticmethod
    def _manifest_generation(candidate: Any) -> int:
        """Return a usable durable generation, or zero for a missing/corrupt file."""

        if isinstance(candidate, dict):
            generation = candidate.get("generation")
            if type(generation) is int and generation >= 0:
                return generation
        return 0

    @classmethod
    def _cleanup_diagnostic_valid(cls, candidate: Any) -> bool:
        if not isinstance(candidate, dict) or set(candidate) != {
            "scope",
            "manifest_generation",
            "segment",
            "before_bytes",
            "after_bytes",
            "cursor",
            "trigger",
            "unfinished_reason",
        }:
            return False
        scope = candidate["scope"]
        if scope is not None:
            if not isinstance(scope, dict) or set(scope) != {
                "bot_ref",
                "persona_ref",
                "session_ref",
                "scope_generation",
                "resolved_at_ms",
            }:
                return False
            if (
                not _opaque_diagnostic_token(scope["bot_ref"], "bot_v1_")
                or not _opaque_diagnostic_token(scope["persona_ref"], "persona_v1_")
                or not _opaque_diagnostic_token(scope["session_ref"], "session_v1_")
                or type(scope["scope_generation"]) is not int
                or scope["scope_generation"] < 0
                or type(scope["resolved_at_ms"]) is not int
                or scope["resolved_at_ms"] < 0
            ):
                return False
        for field in ("manifest_generation", "before_bytes", "after_bytes"):
            if type(candidate[field]) is not int or candidate[field] < 0:
                return False
        segment = candidate["segment"]
        if segment is not None and (
            not isinstance(segment, str) or _SEGMENT_NAME_RE.fullmatch(segment) is None
        ):
            return False
        cursor = candidate["cursor"]
        if cursor is not None and (
            not isinstance(cursor, str) or _SCOPE_TOKEN_RE.fullmatch(cursor) is None
        ):
            return False
        if (
            not isinstance(candidate["trigger"], str)
            or candidate["trigger"] not in _CLEANUP_TRIGGERS
        ):
            return False
        unfinished_reason = candidate["unfinished_reason"]
        return unfinished_reason is None or (
            isinstance(unfinished_reason, str)
            and unfinished_reason in _UNFINISHED_CLEANUP_REASONS
        )

    @classmethod
    def _cleanup_diagnostics_valid(cls, candidate: Any) -> bool:
        return (
            isinstance(candidate, list)
            and len(candidate) <= _CLEANUP_DIAGNOSTIC_LIMIT
            and all(cls._cleanup_diagnostic_valid(item) for item in candidate)
        )

    @classmethod
    def _normalize_scoped_manifest(
        cls,
        candidate: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        """Keep old v2 manifests readable while isolating diagnostics damage."""

        normalized = dict(candidate)
        if "cleanup_diagnostics" not in normalized:
            normalized["cleanup_diagnostics"] = []
            return normalized, False
        if not cls._cleanup_diagnostics_valid(normalized["cleanup_diagnostics"]):
            normalized["cleanup_diagnostics"] = []
            return normalized, True
        return normalized, False

    def _scoped_manifest_valid(self, candidate: Any) -> bool:
        if (
            not isinstance(candidate, dict)
            or candidate.get("schema_version") != SCOPED_MANIFEST_SCHEMA_VERSION
            or type(candidate.get("generation")) is not int
            or candidate["generation"] < 0
            or not isinstance(candidate.get("cleanup_active"), bool)
            or not (
                candidate.get("cleanup_cursor") is None
                or (
                    isinstance(candidate.get("cleanup_cursor"), str)
                    and _SCOPE_TOKEN_RE.fullmatch(candidate["cleanup_cursor"]) is not None
                )
            )
            or not isinstance(candidate.get("budget_unsatisfiable"), bool)
            or type(candidate.get("orphaned_bytes", 0)) is not int
            or candidate.get("orphaned_bytes", 0) < 0
            or not isinstance(candidate.get("scopes"), dict)
        ):
            return False
        cursor = candidate.get("cleanup_cursor")
        if cursor is not None and cursor not in candidate["scopes"]:
            return False
        referenced: set[tuple[str, str]] = set()
        for token, metadata in candidate["scopes"].items():
            if not isinstance(token, str) or _SCOPE_TOKEN_RE.fullmatch(token) is None:
                return False
            if not self._scoped_scope_meta_valid(token, metadata):
                return False
            for segment in metadata["segments"]:
                path = self._scoped_segment_path(token, segment["path"])
                if not path.is_file() or path.stat().st_size != segment["size"]:
                    return False
                referenced.add((token, segment["path"]))
        actual: set[tuple[str, str]] = set()
        scopes_root = self._root / "scopes"
        if scopes_root.is_dir():
            for scope_dir in scopes_root.iterdir():
                if not scope_dir.is_dir() or _SCOPE_TOKEN_RE.fullmatch(scope_dir.name) is None:
                    continue
                for path in scope_dir.glob("segment-????????.jsonl"):
                    if path.is_file():
                        actual.add((scope_dir.name, path.name))
        return (
            referenced == actual
            and candidate.get("orphaned_bytes", 0) == self._scoped_orphaned_bytes(candidate)
        )

    def _scoped_scope_meta_valid(self, token: str, metadata: Any) -> bool:
        if not isinstance(metadata, dict) or not isinstance(metadata.get("segments"), list):
            return False
        for key in ("used_bytes", "next_segment"):
            if type(metadata.get(key)) is not int or metadata[key] < 0:
                return False
        active = metadata.get("active_segment")
        latest = metadata.get("latest_closed_segment")
        if active is not None and not isinstance(active, str):
            return False
        if latest is not None and not isinstance(latest, str):
            return False
        last_digest = metadata.get("last_digest")
        if last_digest is not None and (
            not isinstance(last_digest, str)
            or _HEX_DIGEST_RE.fullmatch(last_digest) is None
        ):
            return False
        paths: set[str] = set()
        active_matches = latest_matches = 0
        used = 0
        numbers: list[int] = []
        for segment in metadata["segments"]:
            if not isinstance(segment, dict):
                return False
            path = segment.get("path")
            if not isinstance(path, str) or _SEGMENT_NAME_RE.fullmatch(path) is None or path in paths:
                return False
            paths.add(path)
            for name in ("size", "sample_count"):
                if type(segment.get(name)) is not int or segment[name] < 0:
                    return False
            if not isinstance(segment.get("closed"), bool):
                return False
            if not isinstance(segment.get("partial"), bool):
                return False
            if segment.get("oldest_ms") is not None and type(segment["oldest_ms"]) is not int:
                return False
            if segment.get("newest_ms") is not None and type(segment["newest_ms"]) is not int:
                return False
            if path == active:
                active_matches += 1
                if segment["closed"]:
                    return False
            if path == latest:
                latest_matches += 1
                if not segment["closed"]:
                    return False
            used += int(segment["size"])
            numbers.append(int(Path(path).stem.split("-")[1]))
        if metadata["used_bytes"] != used:
            return False
        if numbers and metadata["next_segment"] <= max(numbers):
            return False
        if active is None:
            if active_matches != 0:
                return False
        elif active_matches != 1:
            return False
        if latest is None:
            return latest_matches == 0
        if latest_matches != 1:
            return False
        closed_paths = [
            segment["path"]
            for segment in metadata["segments"]
            if segment["closed"]
        ]
        return bool(closed_paths) and latest == closed_paths[-1]

    def _rebuild_scoped_manifest(self) -> dict[str, Any]:
        manifest = self._new_scoped_manifest()
        scopes_root = self._root / "scopes"
        if not scopes_root.is_dir():
            return manifest
        for scope_dir in sorted(scopes_root.iterdir(), key=lambda path: path.name):
            token = scope_dir.name
            if not scope_dir.is_dir() or _SCOPE_TOKEN_RE.fullmatch(token) is None:
                continue
            paths = sorted(
                (path for path in scope_dir.glob("segment-????????.jsonl") if path.is_file()),
                key=self._segment_number,
            )
            if not paths:
                continue
            metadata = self._new_scoped_scope_meta()
            last_digest: str | None = None
            for index, path in enumerate(paths):
                rows, partial = self._read_segment(path, expected_session=token)
                timestamps = [int(row["captured_at_ms"]) for row in rows]
                segment = {
                    "path": path.name,
                    "closed": index < len(paths) - 1 or partial,
                    "size": path.stat().st_size,
                    "sample_count": len(rows),
                    "oldest_ms": min(timestamps) if timestamps else None,
                    "newest_ms": max(timestamps) if timestamps else None,
                    "partial": bool(partial),
                }
                metadata["segments"].append(segment)
                metadata["used_bytes"] += int(segment["size"])
                if rows:
                    last_digest = rows[-1].get("digest")
            metadata["next_segment"] = max(
                int(Path(segment["path"]).stem.split("-")[1])
                for segment in metadata["segments"]
            ) + 1
            active = next((segment for segment in reversed(metadata["segments"]) if not segment["closed"]), None)
            metadata["active_segment"] = None if active is None else active["path"]
            closed = [segment for segment in metadata["segments"] if segment["closed"]]
            metadata["latest_closed_segment"] = None if not closed else closed[-1]["path"]
            metadata["last_digest"] = last_digest
            manifest["scopes"][token] = metadata
        manifest["orphaned_bytes"] = self._scoped_orphaned_bytes(manifest)
        return manifest

    def _scoped_orphaned_bytes(self, manifest: dict[str, Any]) -> int:
        known = {
            self._scoped_segment_path(token, segment["path"])
            for token, metadata in manifest.get("scopes", {}).items()
            for segment in metadata.get("segments", [])
        }
        total = 0
        scopes_root = self._root / "scopes"
        if not scopes_root.is_dir():
            return 0
        for path in scopes_root.rglob("*"):
            if not path.is_file() or path in known:
                continue
            try:
                total += path.stat().st_size
            except OSError:
                continue
        return total

    def _scoped_segment_path(self, scope_token: str, relative: str) -> Path:
        if _SCOPE_TOKEN_RE.fullmatch(scope_token) is None or _SEGMENT_NAME_RE.fullmatch(relative) is None:
            raise ValueError("unsafe scoped observation history segment path")
        return self._root / "scopes" / scope_token / relative

    def _scoped_active_segment(self, metadata: dict[str, Any]) -> dict[str, Any] | None:
        active = metadata.get("active_segment")
        if not isinstance(active, str):
            return None
        return next(
            (segment for segment in metadata.get("segments", []) if segment.get("path") == active and not segment.get("closed")),
            None,
        )

    def _create_scoped_segment(self, token: str, metadata: dict[str, Any]) -> dict[str, Any]:
        number = int(metadata["next_segment"])
        path = f"segment-{number:08d}.jsonl"
        metadata["next_segment"] = number + 1
        metadata["active_segment"] = path
        segment = {
            "path": path,
            "closed": False,
            "size": 0,
            "sample_count": 0,
            "oldest_ms": None,
            "newest_ms": None,
            "partial": False,
        }
        metadata["segments"].append(segment)
        return segment

    def _write_scoped_manifest_locked(self) -> None:
        repository = self._scope_repository
        expected_generation = self._assert_scoped_generation_locked()
        self._manifest["generation"] = expected_generation + 1
        self._manifest["orphaned_bytes"] = self._scoped_orphaned_bytes(self._manifest)
        repository._atomic_json_replace(self._manifest_path, self._manifest)

    def _assert_scoped_generation_locked(self) -> int:
        """Check the durable generation before any scoped destructive write."""

        repository = self._scope_repository
        expected_generation = int(self._manifest.get("generation", 0))
        try:
            loaded = repository._read_json(
                self._manifest_path,
                error_label="observation history manifest",
            )
        except Exception:
            loaded = None
        actual_generation = (
            0
            if loaded is None
            else self._manifest_generation(loaded[1])
        )
        # Repository transactions serialize normal writers, but this explicit
        # check also fences direct/stale writers and makes the durable CAS
        # contract testable independently of the lock implementation.
        if actual_generation != expected_generation:
            from .scope_repository import StaleScopeWrite

            raise StaleScopeWrite(
                expected_generation,
                actual_generation,
                code="observation_manifest_stale",
            )
        return expected_generation

    def _scoped_used_bytes(
        self,
        *,
        manifest_generation: int | None = None,
    ) -> int:
        # Cleanup diagnostics are a bounded audit trail, not retained
        # observation history.  Keeping them outside the retention ledger
        # prevents their own records from creating artificial cleanup churn.
        quota_manifest = dict(self._manifest)
        quota_manifest.pop("cleanup_diagnostics", None)
        if manifest_generation is not None:
            quota_manifest["generation"] = manifest_generation
        return len(
            json.dumps(
                quota_manifest,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ) + sum(
            int(metadata.get("used_bytes", 0))
            for metadata in self._manifest.get("scopes", {}).values()
            if isinstance(metadata, dict)
        )

    def _scoped_deletable(self, token: str, metadata: dict[str, Any]) -> list[dict[str, Any]]:
        active = metadata.get("active_segment")
        latest = metadata.get("latest_closed_segment")
        return [
            segment
            for segment in metadata.get("segments", [])
            if segment.get("closed")
            and segment.get("path") != active
            and segment.get("path") != latest
        ]

    def _current_scoped_cleanup_result(self) -> CleanupResult:
        return CleanupResult(
            budget_unsatisfiable=bool(self._manifest.get("budget_unsatisfiable")),
            cleanup_active=bool(self._manifest.get("cleanup_active")),
            manifest_generation=int(self._manifest.get("generation", 0)),
        )

    def _append_cleanup_diagnostic_locked(
        self,
        *,
        deleted_scope: str | None,
        deleted_segment: str | None,
        before_bytes: int,
        after_bytes: int,
        trigger: str,
        unfinished_reason: str | None,
    ) -> None:
        """Append a bounded, opaque audit record for one cleanup decision."""

        if trigger not in _CLEANUP_TRIGGERS:
            raise ValueError("unsupported cleanup trigger")
        if unfinished_reason not in _UNFINISHED_CLEANUP_REASONS | {None}:
            raise ValueError("unsupported cleanup unfinished reason")
        if min(before_bytes, after_bytes) < 0:
            raise ValueError("cleanup byte counts must be non-negative")
        if deleted_segment is not None and _SEGMENT_NAME_RE.fullmatch(deleted_segment) is None:
            raise ValueError("cleanup segment must be a filename")

        echo = None
        if deleted_scope is not None:
            echo = self._scope_repository._observation_cleanup_diagnostic_echo_locked(
                deleted_scope
            )
        scope: dict[str, Any] | None = None
        if echo is not None:
            # This is intentionally explicit rather than dataclasses.asdict():
            # diagnostics are an allow-list boundary, not a generic serializer.
            scope = {
                "bot_ref": echo.bot_ref,
                "persona_ref": echo.persona_ref,
                "session_ref": echo.session_ref,
                "scope_generation": echo.scope_generation,
                "resolved_at_ms": echo.resolved_at_ms,
            }
        diagnostic = {
            "scope": scope,
            "manifest_generation": int(self._manifest.get("generation", 0)) + 1,
            "segment": deleted_segment,
            "before_bytes": before_bytes,
            "after_bytes": after_bytes,
            "cursor": self._manifest.get("cleanup_cursor"),
            "trigger": trigger,
            "unfinished_reason": unfinished_reason,
        }
        diagnostics = self._manifest.setdefault("cleanup_diagnostics", [])
        if not isinstance(diagnostics, list):
            raise ValueError("cleanup diagnostics must be a list")
        diagnostics.append(diagnostic)
        if len(diagnostics) > _CLEANUP_DIAGNOSTIC_LIMIT:
            del diagnostics[:-_CLEANUP_DIAGNOSTIC_LIMIT]

    def _finish_scoped_cleanup_decision_locked(
        self,
        *,
        deleted_scope: str | None,
        deleted_segment: str | None,
        budget_unsatisfiable: bool,
        cleanup_active: bool,
        before_bytes: int,
        trigger: str,
        unfinished_reason: str | None,
        persist: bool,
    ) -> CleanupResult:
        expected_generation = int(self._manifest.get("generation", 0)) + 1
        after_bytes = self._scoped_used_bytes(
            manifest_generation=expected_generation,
        )
        self._append_cleanup_diagnostic_locked(
            deleted_scope=deleted_scope,
            deleted_segment=deleted_segment,
            before_bytes=before_bytes,
            after_bytes=after_bytes,
            trigger=trigger,
            unfinished_reason=unfinished_reason,
        )
        if persist:
            self._write_scoped_manifest_locked()
            expected_generation = int(self._manifest["generation"])
        return CleanupResult(
            deleted_scope=deleted_scope,
            deleted_segment=deleted_segment,
            budget_unsatisfiable=budget_unsatisfiable,
            cleanup_active=cleanup_active,
            manifest_generation=expected_generation,
        )

    def _scoped_cleanup_once_locked(
        self,
        *,
        trigger: str,
        persist: bool = True,
    ) -> CleanupResult:
        limit = self._limit_bytes()
        before_bytes = self._scoped_used_bytes()
        was_cleanup_active = bool(self._manifest.get("cleanup_active"))
        was_budget_unsatisfiable = bool(
            self._manifest.get("budget_unsatisfiable")
        )
        if limit == 0:
            if not was_cleanup_active and not was_budget_unsatisfiable:
                return self._current_scoped_cleanup_result()
            self._manifest["cleanup_active"] = False
            self._manifest["budget_unsatisfiable"] = False
            return self._finish_scoped_cleanup_decision_locked(
                deleted_scope=None,
                deleted_segment=None,
                budget_unsatisfiable=False,
                cleanup_active=False,
                before_bytes=before_bytes,
                trigger=trigger,
                unfinished_reason=None,
                persist=persist,
            )
        used = before_bytes
        target = math.floor(limit * self._target_ratio)
        if used <= target:
            if not was_cleanup_active and not was_budget_unsatisfiable:
                return self._current_scoped_cleanup_result()
            self._manifest["cleanup_active"] = False
            self._manifest["budget_unsatisfiable"] = False
            return self._finish_scoped_cleanup_decision_locked(
                deleted_scope=None,
                deleted_segment=None,
                budget_unsatisfiable=False,
                cleanup_active=False,
                before_bytes=before_bytes,
                trigger=trigger,
                unfinished_reason=None,
                persist=persist,
            )
        if used <= limit and not self._manifest.get("cleanup_active"):
            if not was_budget_unsatisfiable:
                return self._current_scoped_cleanup_result()
            self._manifest["budget_unsatisfiable"] = False
            return self._finish_scoped_cleanup_decision_locked(
                deleted_scope=None,
                deleted_segment=None,
                budget_unsatisfiable=False,
                cleanup_active=False,
                before_bytes=before_bytes,
                trigger=trigger,
                unfinished_reason=None,
                persist=persist,
            )

        self._manifest["cleanup_active"] = True
        scopes = {
            token: metadata
            for token, metadata in self._manifest.get("scopes", {}).items()
            if isinstance(metadata, dict) and metadata.get("segments")
        }
        retained_count = max(1, len(scopes))
        soft_share = limit / retained_count
        over = [
            token
            for token, metadata in scopes.items()
            if int(metadata.get("used_bytes", 0)) > soft_share and self._scoped_deletable(token, metadata)
        ]
        over.sort()
        cursor = self._manifest.get("cleanup_cursor")
        target_token: str | None = None
        if over:
            if isinstance(cursor, str) and cursor in over:
                after = [token for token in over if token > cursor]
                target_token = after[0] if after else over[0]
            else:
                target_token = over[0]
        candidates: list[tuple[str, dict[str, Any]]] = []
        if target_token is not None:
            candidates = [(target_token, segment) for segment in self._scoped_deletable(target_token, scopes[target_token])]
        else:
            for token, metadata in scopes.items():
                candidates.extend((token, segment) for segment in self._scoped_deletable(token, metadata))
            candidates.sort(
                key=lambda item: (
                    item[1].get("oldest_ms") if item[1].get("oldest_ms") is not None else math.inf,
                    item[1].get("newest_ms") if item[1].get("newest_ms") is not None else math.inf,
                    item[0],
                    item[1]["path"],
                )
            )
        if not candidates:
            self._manifest["budget_unsatisfiable"] = True
            if was_cleanup_active and was_budget_unsatisfiable:
                return self._current_scoped_cleanup_result()
            return self._finish_scoped_cleanup_decision_locked(
                deleted_scope=None,
                deleted_segment=None,
                budget_unsatisfiable=True,
                cleanup_active=True,
                before_bytes=before_bytes,
                trigger=trigger,
                unfinished_reason="budget_unsatisfiable",
                persist=persist,
            )
        token, segment = min(
            candidates,
            key=lambda item: (
                item[1].get("oldest_ms") if item[1].get("oldest_ms") is not None else math.inf,
                item[1].get("newest_ms") if item[1].get("newest_ms") is not None else math.inf,
                item[1]["path"],
            ),
        )
        self._assert_scoped_generation_locked()
        path = self._scoped_segment_path(token, segment["path"])
        path.unlink(missing_ok=True)
        metadata = scopes[token]
        metadata["segments"].remove(segment)
        metadata["used_bytes"] = sum(int(item.get("size", 0)) for item in metadata["segments"])
        closed = [item for item in metadata["segments"] if item.get("closed")]
        metadata["latest_closed_segment"] = None if not closed else closed[-1]["path"]
        self._manifest["cleanup_cursor"] = token
        self._manifest["budget_unsatisfiable"] = False
        self._manifest["cleanup_active"] = (
            self._scoped_used_bytes(
                manifest_generation=int(self._manifest.get("generation", 0)) + 1,
            )
            > target
        )
        return self._finish_scoped_cleanup_decision_locked(
            deleted_scope=token,
            deleted_segment=segment["path"],
            budget_unsatisfiable=False,
            cleanup_active=bool(self._manifest["cleanup_active"]),
            before_bytes=before_bytes,
            trigger=trigger,
            unfinished_reason=(
                "cleanup_active" if self._manifest["cleanup_active"] else None
            ),
            persist=persist,
        )

    def append_snapshot(
        self,
        session_key: str,
        snapshot: dict[str, Any],
        *,
        captured_at_ms: int | None = None,
    ) -> bool:
        """Append one changed projected sample, returning False for a duplicate."""

        if self._scoped:
            return self.append(
                session_key,
                snapshot,
                captured_at_ms=captured_at_ms,
            )

        with self._lock:
            row = project_observation(session_key, snapshot, captured_at_ms)
            key = _session_key(row["session"])
            session_meta = self._manifest["sessions"].get(key)
            if session_meta is not None:
                if session_meta["session"] != row["session"]:
                    raise ValueError("observation history session hash collision")
                if session_meta.get("last_digest") == row["digest"]:
                    cleanup_was_active = bool(self._manifest.get("cleanup_active"))
                    deleted = self._cleanup_once()
                    if deleted or cleanup_was_active != bool(self._manifest.get("cleanup_active")):
                        self._write_manifest()
                    return False
            else:
                session_meta = self._new_session_meta(row["session"])
                self._manifest["sessions"][key] = session_meta

            line = (
                json.dumps(
                    row,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
                + b"\n"
            )
            segment_meta = self._active_segment(session_meta)
            if (
                segment_meta is not None
                and segment_meta["size"] > 0
                and segment_meta["size"] + len(line) > self._segment_bytes
            ):
                segment_meta["closed"] = True
                session_meta["active_segment"] = None
                segment_meta = None
            if segment_meta is None:
                segment_meta = self._create_segment(key, session_meta)

            path = self._path_for_segment(segment_meta["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("ab") as stream:
                stream.write(line)
                stream.flush()
                os.fsync(stream.fileno())

            captured = row["captured_at_ms"]
            segment_meta["size"] = path.stat().st_size
            segment_meta["sample_count"] += 1
            segment_meta["oldest_ms"] = self._earliest(
                segment_meta.get("oldest_ms"),
                captured,
            )
            segment_meta["newest_ms"] = self._latest(
                segment_meta.get("newest_ms"),
                captured,
            )
            session_meta["last_digest"] = row["digest"]
            self._cleanup_once()
            self._write_manifest()
            return True

    def maintenance(self) -> bool:
        """Perform at most one global cleanup deletion."""

        if self._scoped:
            return bool(self.cleanup_once())

        with self._lock:
            before = bool(self._manifest.get("cleanup_active"))
            deleted = self._cleanup_once()
            after = bool(self._manifest.get("cleanup_active"))
            if deleted or before != after:
                self._write_manifest()
            return deleted

    def query(
        self,
        session_key: str,
        *,
        group: str,
        from_ms: int | None = None,
        to_ms: int | None = None,
        max_points: int | None = None,
    ) -> dict[str, Any]:
        """Return numeric observation buckets in chronological order."""

        if self._scoped:
            return self._query_scoped(
                session_key,
                group=group,
                from_ms=from_ms,
                to_ms=to_ms,
                max_points=max_points,
            )

        resolved_max_points = 240 if max_points is None else int(max_points)
        resolved_max_points = max(1, min(1000, resolved_max_points))
        requested_group = str(group)
        stored_group = "route" if requested_group == "routing" else requested_group
        session = str(session_key)
        with self._lock:
            samples: list[tuple[int, dict[str, int | float]]] = []
            partial = False
            session_meta = self._manifest["sessions"].get(_session_key(session))
            if session_meta is not None and session_meta.get("session") == session:
                for segment in session_meta["segments"]:
                    path = self._path_for_segment(segment["path"])
                    if not path.is_file():
                        partial = True
                        continue
                    rows, segment_partial = self._read_segment(
                        path,
                        expected_session=session,
                    )
                    partial = partial or segment_partial
                    for row in rows:
                        captured = row["captured_at_ms"]
                        if from_ms is not None and captured < int(from_ms):
                            continue
                        if to_ms is not None and captured > int(to_ms):
                            continue
                        values = self._numeric_group_values(
                            stored_group,
                            _dict(_dict(row.get("groups")).get(stored_group)),
                        )
                        if not values:
                            continue
                        samples.append((captured, values))
            samples.sort(key=lambda sample: sample[0])
            points = self._bucket_samples(samples, resolved_max_points)
            storage = self._storage_metadata()
            return {
                "schema_version": HISTORY_SCHEMA_VERSION,
                "session": session,
                "group": requested_group,
                "points": points,
                "sample_count": len(samples),
                "downsampled": len(samples) > resolved_max_points,
                "partial": partial,
                "storage": storage,
            }

    def _query_scoped(
        self,
        scope: Any,
        *,
        group: str,
        from_ms: int | None,
        to_ms: int | None,
        max_points: int | None,
    ) -> dict[str, Any]:
        scope = self._require_scope(scope)
        resolved_max_points = 240 if max_points is None else int(max_points)
        resolved_max_points = max(1, min(1000, resolved_max_points))
        requested_group = str(group)
        stored_group = "route" if requested_group == "routing" else requested_group
        repository = self._scope_repository
        with self._lock, repository.transaction():
            repository._validate_session_scope_locked(scope)
            self._refresh_scoped_manifest_locked()
            metadata = self._manifest["scopes"].get(scope.storage_token)
            samples: list[tuple[int, dict[str, int | float]]] = []
            partial = False
            if isinstance(metadata, dict):
                for segment in metadata.get("segments", []):
                    path = self._scoped_segment_path(scope.storage_token, segment["path"])
                    if not path.is_file():
                        partial = True
                        continue
                    rows, segment_partial = self._read_segment(
                        path,
                        expected_session=scope.storage_token,
                    )
                    partial = partial or segment_partial
                    for row in rows:
                        captured = int(row["captured_at_ms"])
                        if from_ms is not None and captured < int(from_ms):
                            continue
                        if to_ms is not None and captured > int(to_ms):
                            continue
                        values = self._numeric_group_values(
                            stored_group,
                            _dict(_dict(row.get("groups")).get(stored_group)),
                        )
                        if values:
                            samples.append((captured, values))
            samples.sort(key=lambda sample: sample[0])
            points = self._bucket_samples(samples, resolved_max_points)
            return {
                "schema_version": HISTORY_SCHEMA_VERSION,
                "session": scope.storage_token,
                "group": requested_group,
                "points": points,
                "sample_count": len(samples),
                "downsampled": len(samples) > resolved_max_points,
                "partial": partial,
                "storage": self._scoped_storage_metadata(),
            }

    @staticmethod
    def _numeric_group_values(
        stored_group: str,
        values: dict[str, Any],
    ) -> dict[str, int | float]:
        source = (
            _dict(values.get("route_counts"))
            if stored_group == "route"
            else values
        )
        numeric: dict[str, int | float] = {}
        for key, value in source.items():
            if not isinstance(key, str):
                continue
            number = _finite_number(value)
            if number is not None:
                numeric[key] = number
        return numeric

    @classmethod
    def _bucket_samples(
        cls,
        samples: list[tuple[int, dict[str, int | float]]],
        max_points: int,
    ) -> list[dict[str, Any]]:
        if not samples:
            return []
        if len(samples) <= max_points:
            return [cls._summarize_bucket([sample]) for sample in samples]

        first_ms = samples[0][0]
        span = samples[-1][0] - first_ms + 1
        by_index: dict[int, list[tuple[int, dict[str, int | float]]]] = {}
        for sample in samples:
            index = min(
                max_points - 1,
                ((sample[0] - first_ms) * max_points) // span,
            )
            by_index.setdefault(index, []).append(sample)
        return [
            cls._summarize_bucket(by_index[index])
            for index in sorted(by_index)
        ]

    @staticmethod
    def _summarize_bucket(
        samples: list[tuple[int, dict[str, int | float]]],
    ) -> dict[str, Any]:
        first: dict[str, int | float] = {}
        last: dict[str, int | float] = {}
        minimum: dict[str, int | float] = {}
        maximum: dict[str, int | float] = {}
        for _, values in samples:
            for key, value in values.items():
                if key not in first:
                    first[key] = value
                    minimum[key] = value
                    maximum[key] = value
                last[key] = value
                minimum[key] = min(minimum[key], value)
                maximum[key] = max(maximum[key], value)
        return {
            "from_ms": samples[0][0],
            "to_ms": samples[-1][0],
            "first": first,
            "last": last,
            "min": minimum,
            "max": maximum,
        }

    @staticmethod
    def _new_session_meta(session: str) -> dict[str, Any]:
        return {
            "session": session,
            "next_segment": 1,
            "active_segment": None,
            "last_digest": None,
            "segments": [],
        }

    @staticmethod
    def _earliest(left: int | None, right: int) -> int:
        return right if left is None else min(left, right)

    @staticmethod
    def _latest(left: int | None, right: int) -> int:
        return right if left is None else max(left, right)

    @staticmethod
    def _new_manifest() -> dict[str, Any]:
        return {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "cleanup_active": False,
            "sessions": {},
        }

    def _limit_bytes(self) -> int:
        try:
            value = int(self._max_bytes_provider())
        except (TypeError, ValueError, OverflowError):
            return DEFAULT_MAX_BYTES
        return DEFAULT_MAX_BYTES if value < 0 else value

    @staticmethod
    def _active_segment(
        session_meta: dict[str, Any],
    ) -> dict[str, Any] | None:
        active = session_meta.get("active_segment")
        if not isinstance(active, str):
            return None
        for segment in session_meta["segments"]:
            if segment["path"] == active and not segment["closed"]:
                return segment
        return None

    @staticmethod
    def _create_segment(
        key: str,
        session_meta: dict[str, Any],
    ) -> dict[str, Any]:
        number = int(session_meta["next_segment"])
        relative = f"{key}/segment-{number:08d}.jsonl"
        session_meta["next_segment"] = number + 1
        session_meta["active_segment"] = relative
        segment = {
            "path": relative,
            "closed": False,
            "size": 0,
            "sample_count": 0,
            "oldest_ms": None,
            "newest_ms": None,
            "partial": False,
        }
        session_meta["segments"].append(segment)
        return segment

    def _path_for_segment(self, relative: str) -> Path:
        parts = Path(relative).parts
        if (
            len(parts) != 2
            or _HEX_DIGEST_RE.fullmatch(parts[0]) is None
            or _SEGMENT_NAME_RE.fullmatch(parts[1]) is None
        ):
            raise ValueError("unsafe observation history segment path")
        return self._root / parts[0] / parts[1]

    def _write_manifest(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        temporary = self._manifest_path.with_suffix(".json.tmp")
        try:
            with temporary.open("wb") as stream:
                stream.write(self._manifest_bytes())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._manifest_path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def _manifest_bytes(self) -> bytes:
        return json.dumps(
            self._manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")

    def _load_or_rebuild_manifest(self) -> dict[str, Any]:
        try:
            candidate = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            candidate = None
        if self._manifest_valid(candidate):
            return candidate
        rebuilt = self._rebuild_manifest()
        self._manifest = rebuilt
        self._write_manifest()
        return rebuilt

    def _manifest_valid(self, candidate: Any) -> bool:
        if (
            not isinstance(candidate, dict)
            or candidate.get("schema_version") != MANIFEST_SCHEMA_VERSION
            or not isinstance(candidate.get("cleanup_active"), bool)
            or not isinstance(candidate.get("sessions"), dict)
        ):
            return False
        referenced: set[str] = set()
        for key, session_meta in candidate["sessions"].items():
            if not self._session_meta_valid(key, session_meta):
                return False
            for segment in session_meta["segments"]:
                path = self._path_for_segment(segment["path"])
                if not path.is_file() or path.stat().st_size != segment["size"]:
                    return False
                referenced.add(segment["path"])
        actual = {
            path.relative_to(self._root).as_posix()
            for path in self._root.glob("*/segment-????????.jsonl")
            if path.is_file()
        }
        return referenced == actual

    def _session_meta_valid(self, key: Any, session_meta: Any) -> bool:
        if (
            not isinstance(key, str)
            or _HEX_DIGEST_RE.fullmatch(key) is None
            or not isinstance(session_meta, dict)
            or not isinstance(session_meta.get("session"), str)
            or _session_key(session_meta["session"]) != key
            or not isinstance(session_meta.get("next_segment"), int)
            or session_meta["next_segment"] < 1
            or not isinstance(session_meta.get("segments"), list)
        ):
            return False
        last_digest = session_meta.get("last_digest")
        if last_digest is not None and (
            not isinstance(last_digest, str) or _HEX_DIGEST_RE.fullmatch(last_digest) is None
        ):
            return False
        active = session_meta.get("active_segment")
        if active is not None and not isinstance(active, str):
            return False
        paths: set[str] = set()
        segment_numbers: list[int] = []
        active_matches = 0
        for segment in session_meta["segments"]:
            if not self._segment_meta_valid(key, segment):
                return False
            path = segment["path"]
            if path in paths:
                return False
            paths.add(path)
            if path == active:
                active_matches += 1
                if segment["closed"]:
                    return False
            segment_name = Path(path).name
            match = _SEGMENT_NAME_RE.fullmatch(segment_name)
            if match is None:
                return False
            segment_numbers.append(int(match.group(1)))
        if segment_numbers and session_meta["next_segment"] <= max(segment_numbers):
            return False
        return (active is None and active_matches == 0) or active_matches == 1

    @staticmethod
    def _segment_meta_valid(key: str, segment: Any) -> bool:
        if not isinstance(segment, dict):
            return False
        path = segment.get("path")
        if not isinstance(path, str):
            return False
        parts = Path(path).parts
        if len(parts) != 2 or parts[0] != key or _SEGMENT_NAME_RE.fullmatch(parts[1]) is None:
            return False
        for name in ("size", "sample_count"):
            if not isinstance(segment.get(name), int) or isinstance(segment.get(name), bool) or segment[name] < 0:
                return False
        for name in ("oldest_ms", "newest_ms"):
            value = segment.get(name)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                return False
        return isinstance(segment.get("closed"), bool) and isinstance(
            segment.get("partial"),
            bool,
        )

    def _rebuild_manifest(self) -> dict[str, Any]:
        manifest = self._new_manifest()
        for directory in sorted(self._root.iterdir()):
            key = directory.name
            if not directory.is_dir() or _HEX_DIGEST_RE.fullmatch(key) is None:
                continue
            segment_paths = sorted(
                (
                    path
                    for path in directory.glob("segment-????????.jsonl")
                    if path.is_file() and _SEGMENT_NAME_RE.fullmatch(path.name)
                ),
                key=self._segment_number,
            )
            if not segment_paths:
                continue
            scans: list[tuple[Path, list[dict[str, Any]], bool]] = []
            sessions: set[str] = set()
            for path in segment_paths:
                rows, partial = self._read_segment(path)
                scans.append((path, rows, partial))
                for row in rows:
                    session = row["session"]
                    if _session_key(session) == key:
                        sessions.add(session)
            if len(sessions) != 1:
                continue
            session = sessions.pop()
            session_meta = self._new_session_meta(session)
            last_digest: str | None = None
            max_number = 0
            for index, (path, rows, partial) in enumerate(scans):
                match = _SEGMENT_NAME_RE.fullmatch(path.name)
                if match is None:
                    continue
                max_number = max(max_number, int(match.group(1)))
                valid_rows = [row for row in rows if row["session"] == session]
                if len(valid_rows) != len(rows):
                    partial = True
                timestamps = [row["captured_at_ms"] for row in valid_rows]
                if valid_rows:
                    last_digest = valid_rows[-1]["digest"]
                relative = path.relative_to(self._root).as_posix()
                segment_meta = {
                    "path": relative,
                    "closed": index < len(scans) - 1,
                    "size": path.stat().st_size,
                    "sample_count": len(valid_rows),
                    "oldest_ms": min(timestamps) if timestamps else None,
                    "newest_ms": max(timestamps) if timestamps else None,
                    "partial": partial,
                }
                session_meta["segments"].append(segment_meta)
            if not session_meta["segments"]:
                continue
            session_meta["next_segment"] = max_number + 1
            newest_segment = session_meta["segments"][-1]
            if newest_segment["partial"]:
                newest_segment["closed"] = True
                session_meta["active_segment"] = None
            else:
                session_meta["active_segment"] = newest_segment["path"]
            session_meta["last_digest"] = last_digest
            manifest["sessions"][key] = session_meta
        return manifest

    @staticmethod
    def _segment_number(path: Path) -> int:
        match = _SEGMENT_NAME_RE.fullmatch(path.name)
        return int(match.group(1)) if match is not None else 0

    def _read_segment(
        self,
        path: Path,
        *,
        expected_session: str | None = None,
    ) -> tuple[list[dict[str, Any]], bool]:
        try:
            contents = path.read_bytes()
        except OSError:
            return [], True
        rows: list[dict[str, Any]] = []
        partial = False
        for raw_line in contents.splitlines(keepends=True):
            if not raw_line.endswith(b"\n"):
                partial = True
                continue
            payload = raw_line[:-1]
            if payload.endswith(b"\r"):
                payload = payload[:-1]
            try:
                row = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                partial = True
                continue
            if not self._row_valid(row, expected_session=expected_session):
                partial = True
                continue
            rows.append(row)
        return rows, partial

    @staticmethod
    def _row_valid(
        row: Any,
        *,
        expected_session: str | None,
    ) -> bool:
        if (
            not isinstance(row, dict)
            or row.get("schema_version") != SAMPLE_SCHEMA_VERSION
            or not isinstance(row.get("captured_at_ms"), int)
            or isinstance(row.get("captured_at_ms"), bool)
            or row["captured_at_ms"] < 0
            or not isinstance(row.get("session"), str)
            or not isinstance(row.get("groups"), dict)
            or not isinstance(row.get("digest"), str)
            or _HEX_DIGEST_RE.fullmatch(row["digest"]) is None
        ):
            return False
        if expected_session is not None and row["session"] != expected_session:
            return False
        return row["digest"] == _digest_payload(row)

    def _used_bytes(self) -> int:
        total = len(self._manifest_bytes())
        for session_meta in self._manifest["sessions"].values():
            for segment in session_meta["segments"]:
                path = self._path_for_segment(segment["path"])
                try:
                    total += path.stat().st_size
                except OSError:
                    continue
        return total

    def _all_segments(self) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        result: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for session_meta in self._manifest["sessions"].values():
            for segment in session_meta["segments"]:
                result.append((session_meta, segment))
        return result

    def _cleanup_once(self) -> bool:
        limit = self._limit_bytes()
        if limit == 0:
            self._manifest["cleanup_active"] = False
            return False
        used = self._used_bytes()
        if not self._manifest["cleanup_active"] and used > limit:
            self._manifest["cleanup_active"] = True
        if not self._manifest["cleanup_active"]:
            return False
        target = math.floor(limit * 0.9)
        if used <= target:
            self._manifest["cleanup_active"] = False
            return False

        all_segments = self._all_segments()
        newest_timestamp = max(
            (segment["newest_ms"] for _, segment in all_segments if segment.get("newest_ms") is not None),
            default=None,
        )
        candidates = [
            (session_meta, segment)
            for session_meta, segment in all_segments
            if segment["closed"]
            and segment["path"] != session_meta.get("active_segment")
            and (newest_timestamp is None or segment.get("newest_ms") != newest_timestamp)
        ]
        if not candidates:
            return False
        candidates.sort(
            key=lambda item: (
                item[1].get("oldest_ms") if item[1].get("oldest_ms") is not None else math.inf,
                item[1].get("newest_ms") if item[1].get("newest_ms") is not None else math.inf,
                item[1]["path"],
            )
        )
        session_meta, segment = candidates[0]
        path = self._path_for_segment(segment["path"])
        path.unlink(missing_ok=True)
        session_meta["segments"].remove(segment)
        used = self._used_bytes()
        if used <= target:
            self._manifest["cleanup_active"] = False
        return True

    def _storage_metadata(self) -> dict[str, Any]:
        segments = self._all_segments()
        oldest_values = [segment["oldest_ms"] for _, segment in segments if segment.get("oldest_ms") is not None]
        return {
            "used_bytes": self._used_bytes(),
            "limit_bytes": self._limit_bytes(),
            "oldest_ms": min(oldest_values) if oldest_values else None,
            "segment_count": len(segments),
            "cleanup_active": bool(self._manifest.get("cleanup_active")),
        }

    def _scoped_storage_metadata(self) -> dict[str, Any]:
        segments = [
            segment
            for metadata in self._manifest.get("scopes", {}).values()
            if isinstance(metadata, dict)
            for segment in metadata.get("segments", [])
        ]
        oldest_values = [
            segment["oldest_ms"]
            for segment in segments
            if segment.get("oldest_ms") is not None
        ]
        return {
            "used_bytes": self._scoped_used_bytes(),
            "limit_bytes": self._limit_bytes(),
            "oldest_ms": min(oldest_values) if oldest_values else None,
            "segment_count": len(segments),
            "cleanup_active": bool(self._manifest.get("cleanup_active")),
            "budget_unsatisfiable": bool(self._manifest.get("budget_unsatisfiable")),
        }


__all__ = [
    "CleanupResult",
    "DEFAULT_MAX_BYTES",
    "HISTORY_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "ObservationHistoryStore",
    "SCOPED_MANIFEST_SCHEMA_VERSION",
    "SAMPLE_SCHEMA_VERSION",
    "project_observation",
]
