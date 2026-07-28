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
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("astrbot_plugin_sylanne")

SAMPLE_SCHEMA_VERSION = "sylanne.observation.sample.v1"
MANIFEST_SCHEMA_VERSION = "sylanne.observation.manifest.v1"
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
    """Append-only segmented JSONL store with one global storage budget."""

    def __init__(
        self,
        root: str | Path,
        max_bytes_provider: Callable[[], int],
        *,
        segment_bytes: int = DEFAULT_SEGMENT_BYTES,
    ) -> None:
        if int(segment_bytes) <= 0:
            raise ValueError("segment_bytes must be positive")
        self._root = Path(root)
        self._max_bytes_provider = max_bytes_provider
        self._segment_bytes = int(segment_bytes)
        self._lock = threading.RLock()
        self._manifest_path = self._root / "manifest.json"
        with self._lock:
            self._root.mkdir(parents=True, exist_ok=True)
            self._manifest = self._load_or_rebuild_manifest()

    @property
    def root(self) -> Path:
        return self._root

    def append_snapshot(
        self,
        session_key: str,
        snapshot: dict[str, Any],
        *,
        captured_at_ms: int | None = None,
    ) -> bool:
        """Append one changed projected sample, returning False for a duplicate."""

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


__all__ = [
    "DEFAULT_MAX_BYTES",
    "HISTORY_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "ObservationHistoryStore",
    "SAMPLE_SCHEMA_VERSION",
    "project_observation",
]
