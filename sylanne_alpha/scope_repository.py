"""Authoritative, durable storage for opaque Bot/Persona/Session scopes."""

from __future__ import annotations

import json
import math
import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import TracebackType
from typing import Iterator

import portalocker

from . import infra
from .scope_contracts import BotRef, PersonaRevisionRef, SessionRef, SessionScope

_SNAPSHOT_SCHEMA = "sylanne.scope.snapshot.v1"
_CATALOG_SCHEMA = "sylanne.scope.catalog.v1"
_BOT_SCHEMA = "sylanne.scope.bot.v1"
_PERSONA_SCHEMA = "sylanne.scope.persona.v1"
_SCOPE_META_SCHEMA = "sylanne.scope.meta.v1"
_COMPONENT_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")


class RepositoryCorruptionError(RuntimeError):
    """A scope-owned authority record could not be validated."""


class StaleScopeWrite(RuntimeError):
    """A CAS or lifecycle fence rejected a stale writer."""

    def __init__(
        self,
        expected_generation: int | None = None,
        actual_generation: int | None = None,
        *,
        code: str = "generation_stale",
    ) -> None:
        self.expected_generation = expected_generation
        self.actual_generation = actual_generation
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class Snapshot:
    """One validated generation of a JSON object payload."""

    generation: int
    payload: dict[str, object] = field(repr=False)


class _InterProcessLock:
    """Bounded, non-reentrant cross-process lock for scope-v1 only."""

    def __init__(self, path: Path, *, timeout_seconds: float) -> None:
        check_interval = min(0.05, max(0.001, timeout_seconds / 4.0))
        self._lock = portalocker.Lock(
            path,
            mode="a+b",
            timeout=timeout_seconds,
            check_interval=check_interval,
            flags=portalocker.LOCK_EX | portalocker.LOCK_NB,
        )

    def __enter__(self) -> _InterProcessLock:
        self._lock.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._lock.__exit__(exc_type, exc_value, traceback)


def _require_token(value: object, prefix: str) -> str:
    if type(value) is not str or not value.startswith(prefix) or len(value) == len(prefix):
        raise ValueError(f"invalid {prefix} token")
    return value


def _require_generation(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative int")
    return value


def _require_payload(payload: object) -> dict[str, object]:
    if type(payload) is not dict:
        raise ValueError("payload must be an exact dict")
    return payload


def _require_component(component: object) -> str:
    if type(component) is not str or _COMPONENT_PATTERN.fullmatch(component) is None:
        raise ValueError("component has an invalid name")
    return component


def _canonical_json_bytes(document: dict[str, object]) -> bytes:
    try:
        encoded = json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("document is not canonical JSON") from exc
    return encoded.encode("utf-8")


class ScopeRepository:
    """Single-lock authority for all scope-v1 JSON snapshots and lifecycles."""

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        lock_timeout_seconds: float = 2.0,
        replace_attempts: int = 8,
        replace_retry_seconds: float = 0.05,
    ) -> None:
        if isinstance(lock_timeout_seconds, bool) or not isinstance(
            lock_timeout_seconds, (int, float)
        ):
            raise TypeError("lock_timeout_seconds must be a finite number")
        timeout = float(lock_timeout_seconds)
        if not math.isfinite(timeout) or timeout < 0.0:
            raise ValueError("lock_timeout_seconds must be finite and non-negative")
        self.root = Path(os.fspath(root))
        self.catalog_path = self.root / "catalog.json"
        self.bots_directory = self.root / "bots"
        self._lock_path = self.root / ".scope-v1.lock"
        self._lock_timeout_seconds = timeout
        self._replace_attempts = max(1, int(replace_attempts))
        self._replace_retry_seconds = max(0.0, float(replace_retry_seconds))
        self.root.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            infra._secure_windows_parent(
                self.root,
                key_exists=False,
                error_label="scope repository",
            )
        else:
            os.chmod(self.root, 0o700)
            infra._validate_posix_owner_only(
                self.root,
                directory=True,
                error_label="scope repository",
            )
        self.bots_directory.mkdir(parents=True, exist_ok=True)

    def _repository_lock(self) -> _InterProcessLock:
        return _InterProcessLock(
            self._lock_path,
            timeout_seconds=self._lock_timeout_seconds,
        )

    @contextmanager
    def transaction(self) -> Iterator[ScopeRepository]:
        """Hold the sole repository lock for a multi-record operation."""

        with self._repository_lock():
            yield self

    @staticmethod
    def _fsync_dir(directory: Path) -> None:
        if os.name == "nt":
            return
        try:
            fd = os.open(directory, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(fd)
        except OSError:
            pass
        finally:
            os.close(fd)

    def _atomic_replace(self, source: Path, destination: Path) -> None:
        last: OSError | None = None
        for attempt in range(self._replace_attempts):
            try:
                os.replace(source, destination)
                return
            except PermissionError as exc:
                if getattr(exc, "winerror", None) != 32:
                    raise
                last = exc
                if attempt + 1 < self._replace_attempts:
                    time.sleep(self._replace_retry_seconds)
        if last is not None:
            raise last

    def _atomic_json_replace(
        self,
        path: Path,
        document: dict[str, object],
        *,
        owner_only: bool = False,
    ) -> None:
        payload = _canonical_json_bytes(document)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.urandom(12).hex()}.tmp")
        try:
            with temporary.open("x", encoding="utf-8", newline="") as stream:
                if owner_only and os.name != "nt":
                    os.chmod(temporary, 0o600)
                stream.write(payload.decode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
            self._atomic_replace(temporary, path)
            if owner_only and os.name != "nt":
                os.chmod(path, 0o600)
            self._fsync_dir(path.parent)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _read_json(path: Path, *, error_label: str) -> tuple[bytes, dict[str, object]] | None:
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise RepositoryCorruptionError(f"{error_label} is unreadable") from exc
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise RepositoryCorruptionError(f"{error_label} is invalid JSON") from exc
        if type(value) is not dict:
            raise RepositoryCorruptionError(f"{error_label} has an invalid envelope")
        return raw, value

    def _read_catalog_locked(self) -> dict[str, object]:
        loaded = self._read_json(self.catalog_path, error_label="scope catalog")
        if loaded is None:
            return {
                "schema_version": _CATALOG_SCHEMA,
                "generation": 0,
                "scopes": {},
            }
        raw, document = loaded
        if set(document) != {"schema_version", "generation", "scopes"}:
            raise RepositoryCorruptionError("scope catalog has an invalid envelope")
        generation = document["generation"]
        scopes = document["scopes"]
        if (
            document["schema_version"] != _CATALOG_SCHEMA
            or type(generation) is not int
            or generation < 1
            or type(scopes) is not dict
            or raw != _canonical_json_bytes(document)
        ):
            raise RepositoryCorruptionError("scope catalog is invalid")
        for token, parent in scopes.items():
            _require_token(token, "scope_v1_")
            if type(parent) is not dict or set(parent) != {
                "bot_ref",
                "persona_ref",
                "session_ref",
            }:
                raise RepositoryCorruptionError("scope catalog parent is invalid")
            _require_token(parent["bot_ref"], "bot_v1_")
            _require_token(parent["persona_ref"], "persona_v1_")
            _require_token(parent["session_ref"], "session_v1_")
        return document

    def _commit_catalog_generation_locked(
        self,
        *,
        registration: tuple[str, str, str, str] | None = None,
    ) -> int:
        current = self._read_catalog_locked()
        scopes = dict(current["scopes"])
        if registration is not None:
            storage_token, bot_token, persona_token, session_token = registration
            proposed = {
                "bot_ref": bot_token,
                "persona_ref": persona_token,
                "session_ref": session_token,
            }
            existing = scopes.get(storage_token)
            if existing is not None and existing != proposed:
                raise RepositoryCorruptionError("scope catalog parent conflict")
            scopes[storage_token] = proposed
        generation = int(current["generation"]) + 1
        self._atomic_json_replace(
            self.catalog_path,
            {
                "schema_version": _CATALOG_SCHEMA,
                "generation": generation,
                "scopes": scopes,
            },
        )
        return generation

    def _bot_directory(self, bot_token: str) -> Path:
        return self.bots_directory / _require_token(bot_token, "bot_v1_")

    def _persona_directory(self, bot_token: str, persona_token: str) -> Path:
        return (
            self._bot_directory(bot_token)
            / "personas"
            / _require_token(persona_token, "persona_v1_")
        )

    def _scope_directory(
        self,
        bot_token: str,
        persona_token: str,
        session_token: str,
    ) -> Path:
        return (
            self._persona_directory(bot_token, persona_token)
            / "sessions"
            / _require_token(session_token, "session_v1_")
        )

    @staticmethod
    def _validated_components(components: object) -> tuple[str, str, str]:
        if type(components) is not tuple or len(components) != 3:
            raise ValueError("components must be an exact three-item tuple")
        bot_token, persona_token, session_token = components
        return (
            _require_token(bot_token, "bot_v1_"),
            _require_token(persona_token, "persona_v1_"),
            _require_token(session_token, "session_v1_"),
        )

    def session_path(self, components: tuple[str, str, str]) -> Path:
        bot_token, persona_token, session_token = self._validated_components(components)
        return self._scope_directory(bot_token, persona_token, session_token) / "snapshot.json"

    def persona_manifest_path(self, persona_ref: PersonaRevisionRef) -> Path:
        if type(persona_ref) is not PersonaRevisionRef:
            raise ValueError("persona_ref must be a PersonaRevisionRef")
        return (
            self._persona_directory(persona_ref.bot_ref.token, persona_ref.token)
            / "manifest.json"
        )

    def scope_meta_path(self, scope: SessionScope) -> Path:
        if type(scope) is not SessionScope:
            raise ValueError("scope must be a SessionScope")
        return (
            self._scope_directory(
                scope.bot_ref.token,
                scope.persona_ref.token,
                scope.session_ref.token,
            )
            / "scope-meta.json"
        )

    def component_path(self, scope: SessionScope, component: str) -> Path:
        if type(scope) is not SessionScope:
            raise ValueError("scope must be a SessionScope")
        name = _require_component(component)
        return self.scope_meta_path(scope).parent / "components" / f"{name}.json"

    def transport_session_directory(self, bot_token: str, session_token: str) -> Path:
        return (
            self._bot_directory(bot_token)
            / "transport-sessions"
            / _require_token(session_token, "session_v1_")
        )

    def transport_catalog_path(self, bot_token: str, session_token: str) -> Path:
        return self.transport_session_directory(bot_token, session_token) / "catalog.json"

    def transport_delivery_binding_path(self, bot_token: str, session_token: str) -> Path:
        return self.transport_session_directory(bot_token, session_token) / "delivery-binding.json"

    def _quarantine_locked(self, path: Path) -> None:
        quarantine = path.parent / "quarantine"
        quarantine.mkdir(parents=True, exist_ok=True)
        destination = quarantine / f"{path.stem}.{os.urandom(12).hex()}.corrupt.json"
        try:
            self._atomic_replace(path, destination)
        except FileNotFoundError:
            return
        self._fsync_dir(quarantine)
        self._fsync_dir(path.parent)
        self._commit_catalog_generation_locked()

    def _read_snapshot_locked(self, path: Path) -> Snapshot | None:
        try:
            loaded = self._read_json(path, error_label="scope snapshot")
            if loaded is None:
                return None
            raw, document = loaded
            if set(document) != {"schema_version", "generation", "payload"}:
                raise RepositoryCorruptionError("scope snapshot has an invalid envelope")
            generation = document["generation"]
            payload = document["payload"]
            if (
                document["schema_version"] != _SNAPSHOT_SCHEMA
                or type(generation) is not int
                or generation < 1
                or type(payload) is not dict
                or raw != _canonical_json_bytes(document)
            ):
                raise RepositoryCorruptionError("scope snapshot is invalid")
            return Snapshot(generation=generation, payload=payload)
        except RepositoryCorruptionError:
            self._quarantine_locked(path)
            return None

    def _write_snapshot_locked(
        self,
        path: Path,
        *,
        expected_generation: int,
        payload: dict[str, object],
    ) -> int:
        _require_generation(expected_generation, "expected_generation")
        _require_payload(payload)
        current = self._read_snapshot_locked(path)
        actual = 0 if current is None else current.generation
        if actual != expected_generation:
            raise StaleScopeWrite(expected_generation, actual)
        generation = actual + 1
        self._atomic_json_replace(
            path,
            {
                "schema_version": _SNAPSHOT_SCHEMA,
                "generation": generation,
                "payload": payload,
            },
        )
        self._commit_catalog_generation_locked()
        return generation

    def read_session(self, components: tuple[str, str, str]) -> Snapshot | None:
        path = self.session_path(components)
        with self._repository_lock():
            return self._read_snapshot_locked(path)

    def write_session(
        self,
        components: tuple[str, str, str],
        *,
        expected_generation: int,
        payload: dict[str, object],
    ) -> int:
        path = self.session_path(components)
        with self._repository_lock():
            return self._write_snapshot_locked(
                path,
                expected_generation=expected_generation,
                payload=payload,
            )

    def _ensure_bot_locked(self, bot_ref: BotRef) -> None:
        if type(bot_ref) is not BotRef:
            raise ValueError("bot_ref must be a BotRef")
        path = self._bot_directory(bot_ref.token) / "manifest.json"
        loaded = self._read_json(path, error_label="bot manifest")
        if loaded is None:
            self._atomic_json_replace(
                path,
                {
                    "schema_version": _BOT_SCHEMA,
                    "bot_ref": bot_ref.token,
                    "bot_generation": bot_ref.generation,
                    "state": "active",
                    "updated_at_ms": self._now_ms(),
                },
            )
            self._commit_catalog_generation_locked()
            return
        raw, document = loaded
        if (
            set(document)
            != {
                "schema_version",
                "bot_ref",
                "bot_generation",
                "state",
                "updated_at_ms",
            }
            or document["schema_version"] != _BOT_SCHEMA
            or document["bot_ref"] != bot_ref.token
            or document["bot_generation"] != bot_ref.generation
            or document["state"] != "active"
            or type(document["updated_at_ms"]) is not int
            or raw != _canonical_json_bytes(document)
        ):
            raise RepositoryCorruptionError("bot manifest is invalid")

    def _load_persona_manifest_locked(
        self,
        persona_ref: PersonaRevisionRef,
        *,
        validate_material: bool = True,
    ) -> dict[str, object] | None:
        loaded = self._read_json(
            self.persona_manifest_path(persona_ref),
            error_label="persona manifest",
        )
        if loaded is None:
            return None
        raw, document = loaded
        expected_fields = {
            "schema_version",
            "bot_ref",
            "persona_ref",
            "persona_id_digest",
            "source_fingerprint",
            "lifecycle_generation",
            "state",
            "updated_at_ms",
            "last_transition",
        }
        if (
            set(document) != expected_fields
            or document["schema_version"] != _PERSONA_SCHEMA
            or document["bot_ref"] != persona_ref.bot_ref.token
            or document["persona_ref"] != persona_ref.token
            or (
                validate_material
                and document["persona_id_digest"] != persona_ref.persona_id_digest
            )
            or (
                validate_material
                and document["source_fingerprint"] != persona_ref.source_fingerprint
            )
            or type(document["lifecycle_generation"]) is not int
            or int(document["lifecycle_generation"]) < 0
            or document["state"] not in {"active", "retired"}
            or type(document["updated_at_ms"]) is not int
            or type(document["last_transition"]) is not str
            or raw != _canonical_json_bytes(document)
        ):
            raise RepositoryCorruptionError("persona manifest is invalid")
        return document

    def _activate_persona_revision_locked(
        self,
        candidate: PersonaRevisionRef,
    ) -> PersonaRevisionRef:
        if type(candidate) is not PersonaRevisionRef:
            raise ValueError("candidate must be a PersonaRevisionRef")
        self._ensure_bot_locked(candidate.bot_ref)
        manifest = self._load_persona_manifest_locked(candidate)
        if manifest is None:
            generation = 0
            transition = "created"
        else:
            generation = int(manifest["lifecycle_generation"])
            if manifest["state"] == "active":
                return replace(candidate, lifecycle_generation=generation)
            transition = "reactivated"
        self._atomic_json_replace(
            self.persona_manifest_path(candidate),
            {
                "schema_version": _PERSONA_SCHEMA,
                "bot_ref": candidate.bot_ref.token,
                "persona_ref": candidate.token,
                "persona_id_digest": candidate.persona_id_digest,
                "source_fingerprint": candidate.source_fingerprint,
                "lifecycle_generation": generation,
                "state": "active",
                "updated_at_ms": self._now_ms(),
                "last_transition": transition,
            },
        )
        self._commit_catalog_generation_locked()
        return replace(candidate, lifecycle_generation=generation)

    def activate_persona_revision(
        self,
        candidate: PersonaRevisionRef,
    ) -> PersonaRevisionRef:
        with self._repository_lock():
            return self._activate_persona_revision_locked(candidate)

    def _require_active_persona_locked(
        self,
        persona_ref: PersonaRevisionRef,
        *,
        expected_lifecycle_generation: int | None = None,
    ) -> PersonaRevisionRef:
        manifest = self._load_persona_manifest_locked(persona_ref)
        actual = None if manifest is None else int(manifest["lifecycle_generation"])
        expected = (
            persona_ref.lifecycle_generation
            if expected_lifecycle_generation is None
            else _require_generation(
                expected_lifecycle_generation,
                "expected_lifecycle_generation",
            )
        )
        if (
            manifest is None
            or manifest["state"] != "active"
            or actual != expected
            or persona_ref.lifecycle_generation != actual
        ):
            raise StaleScopeWrite(
                expected,
                actual,
                code="persona_lifecycle_stale",
            )
        return replace(persona_ref, lifecycle_generation=actual)

    def retire_persona_revision(
        self,
        persona_ref: PersonaRevisionRef,
        *,
        expected_lifecycle_generation: int,
        reason: str,
    ) -> PersonaRevisionRef:
        if type(persona_ref) is not PersonaRevisionRef:
            raise ValueError("persona_ref must be a PersonaRevisionRef")
        _require_generation(
            expected_lifecycle_generation,
            "expected_lifecycle_generation",
        )
        if type(reason) is not str or not reason:
            raise ValueError("reason must be a non-empty str")
        with self._repository_lock():
            active = self._require_active_persona_locked(
                persona_ref,
                expected_lifecycle_generation=expected_lifecycle_generation,
            )
            generation = active.lifecycle_generation + 1
            self._atomic_json_replace(
                self.persona_manifest_path(active),
                {
                    "schema_version": _PERSONA_SCHEMA,
                    "bot_ref": active.bot_ref.token,
                    "persona_ref": active.token,
                    "persona_id_digest": active.persona_id_digest,
                    "source_fingerprint": active.source_fingerprint,
                    "lifecycle_generation": generation,
                    "state": "retired",
                    "updated_at_ms": self._now_ms(),
                    "last_transition": reason,
                },
            )
            self._commit_catalog_generation_locked()
            self._invalidate_persona_scopes_locked(active, reason=reason)
            return replace(active, lifecycle_generation=generation)

    def _scope_meta_document(
        self,
        scope: SessionScope,
        *,
        state: str,
        last_transition: str,
    ) -> dict[str, object]:
        return {
            "schema_version": _SCOPE_META_SCHEMA,
            "storage_token": scope.storage_token,
            "scope_generation": scope.scope_generation,
            "state": state,
            "bot_ref": scope.bot_ref.token,
            "bot_generation": scope.bot_ref.generation,
            "persona_ref": scope.persona_ref.token,
            "persona_lifecycle_generation": scope.persona_ref.lifecycle_generation,
            "session_ref": scope.session_ref.token,
            "session_generation": scope.session_ref.generation,
            "updated_at_ms": self._now_ms(),
            "last_transition": last_transition,
        }

    def _load_scope_meta_locked(self, path: Path) -> dict[str, object] | None:
        loaded = self._read_json(path, error_label="scope metadata")
        if loaded is None:
            return None
        raw, document = loaded
        expected_fields = {
            "schema_version",
            "storage_token",
            "scope_generation",
            "state",
            "bot_ref",
            "bot_generation",
            "persona_ref",
            "persona_lifecycle_generation",
            "session_ref",
            "session_generation",
            "updated_at_ms",
            "last_transition",
        }
        if (
            set(document) != expected_fields
            or document["schema_version"] != _SCOPE_META_SCHEMA
            or document["state"] not in {"active", "inactive"}
            or type(document["scope_generation"]) is not int
            or int(document["scope_generation"]) < 0
            or type(document["bot_generation"]) is not int
            or int(document["bot_generation"]) < 0
            or type(document["persona_lifecycle_generation"]) is not int
            or int(document["persona_lifecycle_generation"]) < 0
            or type(document["session_generation"]) is not int
            or int(document["session_generation"]) < 0
            or type(document["updated_at_ms"]) is not int
            or type(document["last_transition"]) is not str
            or raw != _canonical_json_bytes(document)
        ):
            raise RepositoryCorruptionError("scope metadata is invalid")
        _require_token(document["storage_token"], "scope_v1_")
        _require_token(document["bot_ref"], "bot_v1_")
        _require_token(document["persona_ref"], "persona_v1_")
        _require_token(document["session_ref"], "session_v1_")
        return document

    def create_scope(
        self,
        candidate: SessionScope,
        *,
        expected_absent: bool = False,
    ) -> SessionScope:
        if type(candidate) is not SessionScope:
            raise ValueError("candidate must be a SessionScope")
        if type(expected_absent) is not bool:
            raise ValueError("expected_absent must be an exact bool")
        with self._repository_lock():
            active_persona = self._activate_persona_revision_locked(candidate.persona_ref)
            normalized = replace(candidate, persona_ref=active_persona)
            path = self.scope_meta_path(normalized)
            current = self._load_scope_meta_locked(path)
            if current is None:
                active = replace(normalized, scope_generation=0)
                transition = "created"
            else:
                self._validate_scope_parent(current, normalized)
                if (
                    current["state"] == "active"
                    and current["persona_lifecycle_generation"]
                    == active_persona.lifecycle_generation
                ):
                    if expected_absent:
                        raise StaleScopeWrite(
                            0,
                            int(current["scope_generation"]),
                            code="scope_exists",
                        )
                    return replace(
                        normalized,
                        scope_generation=int(current["scope_generation"]),
                    )
                active = replace(
                    normalized,
                    scope_generation=int(current["scope_generation"]) + 1,
                )
                transition = "reactivated"
                self._cleanup_scope_components_locked(path.parent)
            self._atomic_json_replace(
                path,
                self._scope_meta_document(
                    active,
                    state="active",
                    last_transition=transition,
                ),
            )
            self._commit_catalog_generation_locked(
                registration=(
                    active.storage_token,
                    active.bot_ref.token,
                    active.persona_ref.token,
                    active.session_ref.token,
                )
            )
            return active

    @staticmethod
    def _validate_scope_parent(
        metadata: dict[str, object],
        scope: SessionScope,
    ) -> None:
        if (
            metadata["storage_token"] != scope.storage_token
            or metadata["bot_ref"] != scope.bot_ref.token
            or metadata["bot_generation"] != scope.bot_ref.generation
            or metadata["persona_ref"] != scope.persona_ref.token
            or metadata["session_ref"] != scope.session_ref.token
            or metadata["session_generation"] != scope.session_ref.generation
        ):
            raise RepositoryCorruptionError("scope parent chain is invalid")

    def _resolve_scope_locked(self, storage_token: str) -> SessionScope:
        token = _require_token(storage_token, "scope_v1_")
        catalog = self._read_catalog_locked()
        parent = catalog["scopes"].get(token)
        if type(parent) is not dict:
            raise KeyError("scope not found")
        bot_token = _require_token(parent["bot_ref"], "bot_v1_")
        persona_token = _require_token(parent["persona_ref"], "persona_v1_")
        session_token = _require_token(parent["session_ref"], "session_v1_")
        path = self._scope_directory(bot_token, persona_token, session_token) / "scope-meta.json"
        metadata = self._load_scope_meta_locked(path)
        if metadata is None:
            raise RepositoryCorruptionError("scope metadata is missing")
        if (
            metadata["storage_token"] != token
            or metadata["bot_ref"] != bot_token
            or metadata["persona_ref"] != persona_token
            or metadata["session_ref"] != session_token
        ):
            raise RepositoryCorruptionError("scope parent chain is invalid")
        bot = BotRef(token=bot_token, generation=int(metadata["bot_generation"]))
        persona_stub = PersonaRevisionRef(
            token=persona_token,
            bot_ref=bot,
            persona_id_digest="0" * 64,
            source_fingerprint="0" * 64,
            lifecycle_generation=int(metadata["persona_lifecycle_generation"]),
        )
        persona_manifest = self._load_persona_manifest_locked(
            persona_stub,
            validate_material=False,
        )
        if persona_manifest is None:
            raise RepositoryCorruptionError("persona manifest is missing")
        persona = PersonaRevisionRef(
            token=persona_token,
            bot_ref=bot,
            persona_id_digest=str(persona_manifest["persona_id_digest"]),
            source_fingerprint=str(persona_manifest["source_fingerprint"]),
            lifecycle_generation=int(persona_manifest["lifecycle_generation"]),
        )
        if (
            metadata["state"] != "active"
            or persona_manifest["state"] != "active"
            or metadata["persona_lifecycle_generation"] != persona.lifecycle_generation
        ):
            raise StaleScopeWrite(code="persona_lifecycle_stale")
        return SessionScope(
            bot_ref=bot,
            persona_ref=persona,
            session_ref=SessionRef(
                token=session_token,
                bot_ref=bot,
                generation=int(metadata["session_generation"]),
            ),
            storage_token=token,
            scope_generation=int(metadata["scope_generation"]),
        )

    def resolve_scope(self, storage_token: str) -> SessionScope:
        with self._repository_lock():
            return self._resolve_scope_locked(storage_token)

    def current_scope_generation(self, storage_token: str) -> int | None:
        try:
            return self.resolve_scope(storage_token).scope_generation
        except (KeyError, StaleScopeWrite):
            return None

    def _require_active_scope_locked(self, scope: SessionScope) -> SessionScope:
        if type(scope) is not SessionScope:
            raise ValueError("scope must be a SessionScope")
        current = self._resolve_scope_locked(scope.storage_token)
        if current.persona_ref.lifecycle_generation != scope.persona_ref.lifecycle_generation:
            raise StaleScopeWrite(
                scope.persona_ref.lifecycle_generation,
                current.persona_ref.lifecycle_generation,
                code="persona_lifecycle_stale",
            )
        if current.scope_generation != scope.scope_generation:
            raise StaleScopeWrite(
                scope.scope_generation,
                current.scope_generation,
                code="scope_generation_stale",
            )
        if (
            current.bot_ref != scope.bot_ref
            or current.persona_ref != scope.persona_ref
            or current.session_ref != scope.session_ref
        ):
            raise StaleScopeWrite(code="scope_parent_stale")
        return current

    def write_component(
        self,
        scope: SessionScope,
        component: str,
        *,
        expected_generation: int,
        payload: dict[str, object],
    ) -> int:
        path = self.component_path(scope, component)
        with self._repository_lock():
            self._require_active_scope_locked(scope)
            return self._write_snapshot_locked(
                path,
                expected_generation=expected_generation,
                payload=payload,
            )

    def read_component(
        self,
        scope: SessionScope,
        component: str,
    ) -> Snapshot | None:
        path = self.component_path(scope, component)
        with self._repository_lock():
            self._require_active_scope_locked(scope)
            return self._read_snapshot_locked(path)

    def invalidate_scope(
        self,
        scope: SessionScope,
        *,
        expected_scope_generation: int,
        reason: str,
    ) -> SessionScope:
        _require_generation(expected_scope_generation, "expected_scope_generation")
        if type(reason) is not str or not reason:
            raise ValueError("reason must be a non-empty str")
        with self._repository_lock():
            current = self._require_active_scope_locked(scope)
            if current.scope_generation != expected_scope_generation:
                raise StaleScopeWrite(
                    expected_scope_generation,
                    current.scope_generation,
                    code="scope_generation_stale",
                )
            invalidated = replace(
                current,
                scope_generation=current.scope_generation + 1,
            )
            path = self.scope_meta_path(current)
            self._atomic_json_replace(
                path,
                self._scope_meta_document(
                    invalidated,
                    state="active",
                    last_transition=reason,
                ),
            )
            self._commit_catalog_generation_locked()
            self._cleanup_scope_components_locked(path.parent)
            return invalidated

    def _invalidate_persona_scopes_locked(
        self,
        persona_ref: PersonaRevisionRef,
        *,
        reason: str,
    ) -> None:
        sessions = self._persona_directory(
            persona_ref.bot_ref.token,
            persona_ref.token,
        ) / "sessions"
        if not sessions.is_dir():
            return
        for child in sessions.iterdir():
            if not child.is_dir() or not child.name.startswith("session_v1_"):
                continue
            path = child / "scope-meta.json"
            metadata = self._load_scope_meta_locked(path)
            if metadata is None:
                continue
            metadata = dict(metadata)
            metadata["scope_generation"] = int(metadata["scope_generation"]) + 1
            metadata["persona_lifecycle_generation"] = (
                persona_ref.lifecycle_generation + 1
            )
            metadata["state"] = "inactive"
            metadata["updated_at_ms"] = self._now_ms()
            metadata["last_transition"] = reason
            self._atomic_json_replace(path, metadata)
            self._commit_catalog_generation_locked()
            self._cleanup_scope_components_locked(child)

    def _cleanup_scope_components_locked(self, directory: Path) -> None:
        targets = [directory / "snapshot.json"]
        components = directory / "components"
        if components.is_dir():
            targets.extend(
                child
                for child in components.iterdir()
                if child.is_file() and child.suffix == ".json"
            )
        changed: set[Path] = set()
        for target in targets:
            try:
                target.unlink()
            except FileNotFoundError:
                continue
            changed.add(target.parent)
        for parent in changed:
            self._fsync_dir(parent)

    def write_genesis(
        self,
        persona_ref: PersonaRevisionRef,
        *,
        expected_lifecycle_generation: int,
        payload: dict[str, object],
        expected_generation: int = 0,
    ) -> int:
        if type(persona_ref) is not PersonaRevisionRef:
            raise ValueError("persona_ref must be a PersonaRevisionRef")
        path = (
            self._persona_directory(persona_ref.bot_ref.token, persona_ref.token)
            / "genesis.json"
        )
        with self._repository_lock():
            self._require_active_persona_locked(
                persona_ref,
                expected_lifecycle_generation=expected_lifecycle_generation,
            )
            return self._write_snapshot_locked(
                path,
                expected_generation=expected_generation,
                payload=payload,
            )

    def read_genesis(self, persona_ref: PersonaRevisionRef) -> Snapshot | None:
        if type(persona_ref) is not PersonaRevisionRef:
            raise ValueError("persona_ref must be a PersonaRevisionRef")
        path = (
            self._persona_directory(persona_ref.bot_ref.token, persona_ref.token)
            / "genesis.json"
        )
        with self._repository_lock():
            self._require_active_persona_locked(persona_ref)
            return self._read_snapshot_locked(path)

    @staticmethod
    def _now_ms() -> int:
        return time.time_ns() // 1_000_000


__all__ = [
    "RepositoryCorruptionError",
    "ScopeRepository",
    "Snapshot",
    "StaleScopeWrite",
]
