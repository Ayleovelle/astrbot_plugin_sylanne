"""Authoritative, durable storage for opaque Bot/Persona/Session scopes."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import secrets
import stat
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType
from typing import Iterator

import portalocker

from . import infra
from .infra import atomic_write_owner_only_bytes, load_or_create_owner_only_secret
from .scope_contracts import (
    BotRef,
    PersonaRevisionRef,
    RelationRef,
    RelationScope,
    SessionRef,
    ScopeDiagnosticEcho,
    SessionScope,
)

_SNAPSHOT_SCHEMA = "sylanne.scope.snapshot.v1"
_CATALOG_SCHEMA = "sylanne.scope.catalog.v1"
_BOT_SCHEMA = "sylanne.scope.bot.v1"
_PERSONA_SCHEMA = "sylanne.scope.persona.v1"
_SCOPE_META_SCHEMA = "sylanne.scope.meta.v1"
_RELATION_META_SCHEMA = "sylanne.scope.relation-meta.v1"
_PERSONA_GENESIS_GLOBAL_SCHEMA = "sylanne.persona-genesis.global.v1"
_PERSONA_GENESIS_CORRUPTION_SCHEMA = "sylanne.persona-genesis.corruption.v1"
_LEGACY_UNSCOPED_MANIFEST_SCHEMA = "sylanne.scope.legacy-unscoped.v1"
_WEBUI_PRINCIPAL_KEY_MAGIC = b"SYLANNE-WEBUI-PRINCIPAL\x01\x00"
_LEGACY_CLAIM_ACTOR_KEY_MAGIC = b"SYLANNE-LEGACY-CLAIM-ACTOR\x01\x00"
_OWNER_ONLY_SECRET_BYTES = 32
_PERSONA_GENESIS_DAILY_LIMIT = 32
_PERSONA_GENESIS_LEASE_MS = 5 * 60 * 1000
_COMPONENT_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
_TOKEN_PAYLOAD = re.compile(r"[A-Za-z0-9_-]+\Z", re.ASCII)

# These names are an authority boundary, not merely a filesystem convenience.
# A scoped runtime may only persist one of the known state partitions below.
_SESSION_COMPONENTS = frozenset(
    {
        "runtime",
        "host",
        "memory",
        "conversation",
        "life",
        "rhythm",
        "social",
        "scheduler",
        "background-queue",
        "device-context",
        "v2",
        "v3-shadow",
    }
)
_RELATION_COMPONENTS = frozenset(
    {
        "profile",
        "shelf",
        "relationship",
        "relationship-age",
        "first-impression",
        "ritual",
    }
)


class RepositoryCorruptionError(RuntimeError):
    """A scope-owned authority record could not be validated."""


class ScopeCorrupt(RepositoryCorruptionError):
    """A scoped authority record has a valid shape but inconsistent parents."""


class ScopeParentMismatch(ValueError):
    """A child scope/ref does not belong to the named Bot or Persona parent."""


class ScopeBotNotFound(KeyError):
    """The requested durable Bot parent does not exist."""


class ScopePersonaNotFound(KeyError):
    """The requested active Persona does not exist under its Bot parent."""


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


@dataclass(frozen=True, slots=True)
class PersonaDossierSnapshot:
    """Read-only Persona-owned projection without a Session dependency."""

    persona_ref: PersonaRevisionRef = field(repr=False)
    updated_at_ms: int
    genesis: Snapshot | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class PersonaGenesisLease:
    """One durable, fenced authority to make a paid Persona Genesis attempt."""

    persona_token: str
    lifecycle_generation: int
    source_fingerprint: str
    origin_turn_generation: int
    attempt: int
    lease_id: str
    fence: int
    expires_at_ms: int


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
    if (
        type(value) is not str
        or not value.startswith(prefix)
        or _TOKEN_PAYLOAD.fullmatch(value[len(prefix) :]) is None
    ):
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


def _require_session_component(component: object) -> str:
    name = _require_component(component)
    if name not in _SESSION_COMPONENTS:
        raise ValueError(f"unsupported scoped component: {name}")
    return name


def _require_relation_component(component: object) -> str:
    name = _require_component(component)
    if name not in _RELATION_COMPONENTS:
        raise ValueError(f"unsupported relation component: {name}")
    return name


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
        self.bot_bindings_directory = self.root / "bot-bindings"
        # Observation history is the one intentionally global, repository-owned
        # retention domain.  Segment bytes are partitioned by opaque Scope token
        # below this root; its manifest is never stored inside a Session folder.
        self.observation_root = self.root / "observation"
        self.observation_manifest_path = self.observation_root / "manifest.json"
        # Legacy imports are intentionally not mixed into any live Session
        # partition.  The claim service is the only caller allowed to inspect
        # this owner-only, explicit-inventory root.
        self.legacy_unscoped_root = self.root / "legacy-unscoped"
        self.legacy_unscoped_manifest_path = self.legacy_unscoped_root / "manifest.json"
        # These files are distinct authority roots.  The principal signing key
        # is neither the scope identity key nor V3's ephemeral correlation key.
        self.webui_principal_key_path = self.root / "webui-principal.key"
        self.legacy_claim_actor_key_path = self.legacy_unscoped_root / "actor-binding.key"
        self.legacy_claim_authority_path = self.legacy_unscoped_root / "legacy-claim-authority.json"
        self._lock_path = self.root / ".scope-v1.lock"
        self._persona_genesis_global_path = self.root / "persona-genesis-global.json"
        self._persona_genesis_slot_path = self.root / ".persona-genesis-provider.lock"
        self._lock_timeout_seconds = timeout
        self._replace_attempts = max(1, int(replace_attempts))
        self._replace_retry_seconds = max(0.0, float(replace_retry_seconds))
        self._webui_principal_secret: bytes | None = None
        self._legacy_claim_actor_secret: bytes | None = None
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
        # ScopeResolver.for_context creates this repository, which initializes
        # the distinct WebUI issuer before any request adapter can consume it.
        self.initialize_webui_principal_key()

    def initialize_webui_principal_key(self) -> None:
        """Initialize both request-adjacent owner-only WebUI authority keys.

        ScopeResolver calls this during construction.  HTTP request paths only
        consume its already-published in-memory copy, so a missing or corrupt
        file after startup never becomes an on-demand credential creation.
        """

        with self._repository_lock():
            self._webui_principal_secret = load_or_create_owner_only_secret(
                self.webui_principal_key_path,
                magic=_WEBUI_PRINCIPAL_KEY_MAGIC,
                secret_bytes=_OWNER_ONLY_SECRET_BYTES,
                error_label="WebUI principal key",
            )
            self._legacy_claim_actor_secret = load_or_create_owner_only_secret(
                self.legacy_claim_actor_key_path,
                magic=_LEGACY_CLAIM_ACTOR_KEY_MAGIC,
                secret_bytes=_OWNER_ONLY_SECRET_BYTES,
                error_label="legacy claim actor binding key",
            )

    def derive_webui_principal_token(self, host: object, identity: object) -> str | None:
        """Derive a domain-separated opaque host principal without HTTP-side IO."""

        secret = self._webui_principal_secret
        if (
            host not in {"pages", "standalone"}
            or type(identity) is not str
            or not identity
            or len(identity) > 512
            or type(secret) is not bytes
            or len(secret) != _OWNER_ONLY_SECRET_BYTES
        ):
            return None
        try:
            payload = (
                b"sylanne-webui-principal-v1\x00"
                + host.encode("ascii")
                + b"\x00"
                + identity.encode("utf-8")
            )
        except UnicodeEncodeError:
            return None
        return "principal_v1_" + hmac.new(secret, payload, hashlib.sha256).hexdigest()

    def legacy_claim_actor_secret(self) -> bytes:
        """Return only the startup-published actor-binding key; never create it."""

        secret = self._legacy_claim_actor_secret
        if type(secret) is not bytes or len(secret) != _OWNER_ONLY_SECRET_BYTES:
            raise RepositoryCorruptionError("legacy claim actor binding key is unavailable")
        return secret

    def _observation_scope_dir_locked(self, scope: SessionScope) -> Path:
        if type(scope) is not SessionScope:
            raise ValueError("scope must be a SessionScope")
        self._validate_session_scope_locked(scope)
        return self.observation_root / "scopes" / _require_token(
            scope.storage_token,
            "scope_v1_",
        )

    def observation_scope_dir(self, scope: SessionScope) -> Path:
        """Return the opaque observation directory after a full scope fence."""

        with self._repository_lock():
            return self._observation_scope_dir_locked(scope)

    def _observation_cleanup_diagnostic_echo_locked(
        self,
        storage_token: str,
    ) -> ScopeDiagnosticEcho | None:
        """Project one registered observation owner without requiring activity.

        Cleanup can legitimately outlive a Session reset or Persona retirement.
        The catalog and persisted scope metadata still have to agree, but this
        diagnostic-only projection must not call the active-scope fence.
        """

        token = _require_token(storage_token, "scope_v1_")
        parent = self._read_catalog_locked()["scopes"].get(token)
        if parent is None:
            return None
        if type(parent) is not dict:
            raise RepositoryCorruptionError("scope catalog parent is invalid")
        bot_token = _require_token(parent["bot_ref"], "bot_v1_")
        persona_token = _require_token(parent["persona_ref"], "persona_v1_")
        session_token = _require_token(parent["session_ref"], "session_v1_")
        metadata = self._load_scope_meta_locked(
            self._scope_directory(bot_token, persona_token, session_token)
            / "scope-meta.json"
        )
        if metadata is None:
            return None
        if (
            metadata["storage_token"] != token
            or metadata["bot_ref"] != bot_token
            or metadata["persona_ref"] != persona_token
            or metadata["session_ref"] != session_token
        ):
            raise RepositoryCorruptionError("scope catalog parent is invalid")
        return ScopeDiagnosticEcho(
            bot_ref=bot_token,
            persona_ref=persona_token,
            session_ref=session_token,
            scope_generation=int(metadata["scope_generation"]),
            resolved_at_ms=self._now_ms(),
        )

    def _repository_lock(self) -> _InterProcessLock:
        return _InterProcessLock(
            self._lock_path,
            timeout_seconds=self._lock_timeout_seconds,
        )

    def _repository_lock_nowait(self) -> _InterProcessLock:
        """Return the scope lock in immediate fail-closed mode for request paths."""

        return _InterProcessLock(self._lock_path, timeout_seconds=0.0)

    @contextmanager
    def persona_genesis_provider_slot(self) -> Iterator[bool]:
        """Try to own the cross-process provider slot for one full awaited call.

        The caller holds this context across the provider ``await``.  The
        durable lease remains the recovery fence; this portalocker slot merely
        prevents two live processes from overlapping a paid call before either
        observes the other's lease.
        """

        slot = _InterProcessLock(
            self._persona_genesis_slot_path,
            timeout_seconds=0.0,
        )
        try:
            slot.__enter__()
        except portalocker.exceptions.LockException:
            yield False
            return
        try:
            yield True
        finally:
            slot.__exit__(None, None, None)

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

    def _ensure_scope_registration_locked(self, scope: SessionScope) -> None:
        """Repair a missing scope index entry without bumping an intact catalog."""

        if type(scope) is not SessionScope:
            raise ValueError("scope must be a SessionScope")
        proposed = {
            "bot_ref": scope.bot_ref.token,
            "persona_ref": scope.persona_ref.token,
            "session_ref": scope.session_ref.token,
        }
        catalog = self._read_catalog_locked()
        existing = catalog["scopes"].get(scope.storage_token)
        if existing is not None:
            if existing != proposed:
                raise RepositoryCorruptionError("scope catalog parent conflict")
            return
        self._commit_catalog_generation_locked(
            registration=(
                scope.storage_token,
                scope.bot_ref.token,
                scope.persona_ref.token,
                scope.session_ref.token,
            )
        )

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

    def _relation_directory(
        self,
        bot_token: str,
        persona_token: str,
        relation_token: str,
    ) -> Path:
        return (
            self._persona_directory(bot_token, persona_token)
            / "relations"
            / _require_token(relation_token, "relation_v1_")
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
        name = _require_session_component(component)
        return self.scope_meta_path(scope).parent / "components" / f"{name}.json"

    def relation_meta_path(self, scope: RelationScope) -> Path:
        if type(scope) is not RelationScope:
            raise ValueError("scope must be a RelationScope")
        return (
            self._relation_directory(
                scope.bot_ref.token,
                scope.persona_ref.token,
                scope.relation_ref.token,
            )
            / "relation-meta.json"
        )

    def relation_component_path(self, scope: RelationScope, component: str) -> Path:
        if type(scope) is not RelationScope:
            raise ValueError("scope must be a RelationScope")
        name = _require_relation_component(component)
        return self.relation_meta_path(scope).parent / "components" / f"{name}.json"

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

    def delivery_outbox_path(self, scope: SessionScope) -> Path:
        """Return the owner-only proactive outbox location for one Persona scope.

        The filename and all parent directories contain only opaque scope tokens.
        Address material lives in the document itself and is never reconstructed
        from an arbitrary session string.
        """

        if type(scope) is not SessionScope:
            raise ValueError("scope must be a SessionScope")
        return (
            self._persona_directory(scope.bot_ref.token, scope.persona_ref.token)
            / "delivery"
            / "outbox.json"
        )

    def _read_delivery_outbox_locked(
        self,
        scope: SessionScope,
    ) -> tuple[bytes, dict[str, object]] | None:
        """Read one protected outbox document while the repository lock is held."""

        return self._read_owner_json_locked(
            self.delivery_outbox_path(scope),
            error_label="delivery outbox",
        )

    def _read_owner_json_locked(
        self,
        path: Path,
        *,
        error_label: str,
    ) -> tuple[bytes, dict[str, object]] | None:
        """Read one owner-only JSON document while the repository lock is held."""

        if not path.exists():
            return None
        try:
            if os.name == "nt":
                infra._validate_windows_path(path, error_label=error_label)
            else:
                info = infra._validate_posix_owner_only(
                    path,
                    directory=False,
                    error_label=error_label,
                )
                if not stat.S_ISREG(info.st_mode):
                    raise RepositoryCorruptionError(f"{error_label} is not a regular file")
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise RepositoryCorruptionError(f"{error_label} is unreadable") from exc
        return self._read_json(path, error_label=error_label)

    @staticmethod
    def _legacy_fingerprint(value: object) -> str:
        if (
            type(value) is not str
            or len(value) != 64
            or value != value.lower()
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError("legacy source fingerprint is invalid")
        return value

    def legacy_unscoped_source_path(self, fingerprint: str) -> Path:
        """Return one opaque explicit-inventory source path.

        The path accepts only a digest generated from supplied inventory bytes;
        it is never derived from a transport key, KV key, or legacy filename.
        """

        digest = self._legacy_fingerprint(fingerprint)
        return self.legacy_unscoped_root / "sources" / f"{digest}.json"

    def _read_legacy_unscoped_manifest_locked(self) -> dict[str, object]:
        """Read the single atomic inventory/claim index under the scope lock."""

        loaded = self._read_owner_json_locked(
            self.legacy_unscoped_manifest_path,
            error_label="legacy unscoped manifest",
        )
        if loaded is None:
            return {
                "schema_version": _LEGACY_UNSCOPED_MANIFEST_SCHEMA,
                "generation": 0,
                "inventory": {},
                "claims": {},
            }
        raw, document = loaded
        if (
            set(document) != {"schema_version", "generation", "inventory", "claims"}
            or document["schema_version"] != _LEGACY_UNSCOPED_MANIFEST_SCHEMA
            or type(document["generation"]) is not int
            or int(document["generation"]) < 1
            or type(document["inventory"]) is not dict
            or type(document["claims"]) is not dict
            or raw != _canonical_json_bytes(document)
        ):
            raise RepositoryCorruptionError("legacy unscoped manifest is invalid")
        for collection_name in ("inventory", "claims"):
            collection = document[collection_name]
            assert type(collection) is dict
            for fingerprint, record in collection.items():
                self._legacy_fingerprint(fingerprint)
                if type(record) is not dict:
                    raise RepositoryCorruptionError(
                        "legacy unscoped manifest record is invalid"
                    )
        return document

    def _read_legacy_claim_authority_locked(
        self,
    ) -> tuple[bytes, dict[str, object]] | None:
        """Read the owner-only legacy claim ACL while holding the scope lock."""

        return self._read_owner_json_locked(
            self.legacy_claim_authority_path,
            error_label="legacy claim authority",
        )

    def _write_legacy_claim_authority_locked(self, document: dict[str, object]) -> None:
        """Atomically publish the complete authority replacement document."""

        atomic_write_owner_only_bytes(
            self.legacy_claim_authority_path,
            _canonical_json_bytes(document),
            error_label="legacy claim authority",
        )
        self._fsync_dir(self.legacy_unscoped_root)

    def _write_legacy_unscoped_manifest_locked(
        self,
        document: dict[str, object],
    ) -> None:
        """Publish inventory and claim completion in one owner-only replace."""

        if type(document) is not dict:
            raise ValueError("legacy unscoped manifest must be an exact dict")
        payload = _canonical_json_bytes(document)
        atomic_write_owner_only_bytes(
            self.legacy_unscoped_manifest_path,
            payload,
            error_label="legacy unscoped manifest",
        )
        self._fsync_dir(self.legacy_unscoped_root)

    def _read_legacy_unscoped_source_locked(
        self,
        fingerprint: str,
    ) -> tuple[bytes, dict[str, object]] | None:
        return self._read_owner_json_locked(
            self.legacy_unscoped_source_path(fingerprint),
            error_label="legacy unscoped source",
        )

    def _write_legacy_unscoped_source_locked(
        self,
        fingerprint: str,
        document: dict[str, object],
    ) -> None:
        payload = _canonical_json_bytes(document)
        atomic_write_owner_only_bytes(
            self.legacy_unscoped_source_path(fingerprint),
            payload,
            error_label="legacy unscoped source",
        )

    def _write_legacy_unscoped_stage_locked(
        self,
        fingerprint: str,
        payload: bytes,
    ) -> Path:
        """Durably stage a copy before a legacy claim can publish it."""

        digest = self._legacy_fingerprint(fingerprint)
        if type(payload) is not bytes:
            raise TypeError("legacy staging payload must have exact type bytes")
        stage = (
            self.legacy_unscoped_root
            / "staging"
            / f"{digest}.{secrets.token_hex(12)}.stage"
        )
        atomic_write_owner_only_bytes(
            stage,
            payload,
            error_label="legacy unscoped staging",
        )
        return stage

    def _write_legacy_unscoped_quarantine_locked(
        self,
        document: dict[str, object],
    ) -> Path:
        """Record a rejected import outside live scope partitions."""

        payload = _canonical_json_bytes(document)
        path = (
            self.legacy_unscoped_root
            / "quarantine"
            / f"{secrets.token_hex(16)}.json"
        )
        atomic_write_owner_only_bytes(
            path,
            payload,
            error_label="legacy unscoped quarantine",
        )
        return path

    def _iter_delivery_outboxes_locked(
        self,
    ) -> Iterator[tuple[Path, bytes, dict[str, object]]]:
        """Yield only opaque-token owner-only delivery outbox documents."""

        if not self.bots_directory.is_dir():
            return
        try:
            bot_directories = tuple(self.bots_directory.iterdir())
        except OSError as exc:
            raise RepositoryCorruptionError("delivery outbox root is unreadable") from exc
        for bot_directory in bot_directories:
            if not bot_directory.is_dir() or not bot_directory.name.startswith("bot_v1_"):
                continue
            _require_token(bot_directory.name, "bot_v1_")
            personas = bot_directory / "personas"
            if not personas.is_dir():
                continue
            try:
                persona_directories = tuple(personas.iterdir())
            except OSError as exc:
                raise RepositoryCorruptionError("delivery persona root is unreadable") from exc
            for persona_directory in persona_directories:
                if (
                    not persona_directory.is_dir()
                    or not persona_directory.name.startswith("persona_v1_")
                ):
                    continue
                _require_token(persona_directory.name, "persona_v1_")
                path = persona_directory / "delivery" / "outbox.json"
                loaded = self._read_owner_json_locked(
                    path,
                    error_label="delivery outbox",
                )
                if loaded is not None:
                    raw, document = loaded
                    yield path, raw, document

    def _write_delivery_outbox_locked(
        self,
        scope: SessionScope,
        document: dict[str, object],
    ) -> None:
        """Atomically replace one owner-only outbox document under the lock."""

        if type(document) is not dict:
            raise ValueError("delivery outbox document must be an exact dict")
        atomic_write_owner_only_bytes(
            self.delivery_outbox_path(scope),
            _canonical_json_bytes(document),
            error_label="delivery outbox",
        )
        self._commit_catalog_generation_locked()

    def bot_binding_manifest_path(self, binding_token: str) -> Path:
        return (
            self.bot_bindings_directory
            / _require_token(binding_token, "binding_v1_")
            / "manifest.json"
        )

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

    def _read_snapshot_locked(
        self,
        path: Path,
        *,
        quarantine_on_error: bool = True,
    ) -> Snapshot | None:
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
            if quarantine_on_error:
                self._quarantine_locked(path)
                return None
            raise

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

    def _validate_bot_ref_locked(self, bot_ref: BotRef) -> None:
        """Fence a Bot manifest before any child state is inspected.

        A token-looking directory alone is never authority.  Reads use this
        exact check as well as writes so a retired/rebound parent cannot expose
        stale child bytes to an active runtime.
        """

        if type(bot_ref) is not BotRef:
            raise ValueError("bot_ref must be a BotRef")
        path = self._bot_directory(bot_ref.token) / "manifest.json"
        loaded = self._read_json(path, error_label="bot manifest")
        if loaded is None:
            raise StaleScopeWrite(
                bot_ref.generation,
                None,
                code="bot_generation_stale",
            )
        raw, document = loaded
        expected_fields = {
            "schema_version",
            "bot_ref",
            "bot_generation",
            "state",
            "updated_at_ms",
        }
        if (
            set(document) != expected_fields
            or document["schema_version"] != _BOT_SCHEMA
            or type(document["bot_generation"]) is not int
            or int(document["bot_generation"]) < 0
            or document["state"] not in {"active", "retired"}
            or type(document["updated_at_ms"]) is not int
            or raw != _canonical_json_bytes(document)
        ):
            raise RepositoryCorruptionError("bot manifest is invalid")
        if (
            document["bot_ref"] != bot_ref.token
            or document["bot_generation"] != bot_ref.generation
            or document["state"] != "active"
        ):
            raise StaleScopeWrite(
                bot_ref.generation,
                int(document["bot_generation"]),
                code="bot_generation_stale",
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
        self._validate_bot_ref_locked(bot_ref)

    def _active_bot_ref_locked(self, bot_token: str) -> BotRef | None:
        """Load one active durable Bot without treating its directory as authority."""

        resolved_bot_token = _require_token(bot_token, "bot_v1_")
        loaded_bot = self._read_json(
            self._bot_directory(resolved_bot_token) / "manifest.json",
            error_label="bot manifest",
        )
        if loaded_bot is None:
            return None
        _raw_bot, bot_document = loaded_bot
        bot_generation = bot_document.get("bot_generation")
        if type(bot_generation) is not int or bot_generation < 0:
            raise RepositoryCorruptionError("bot manifest is invalid")
        bot = BotRef(token=resolved_bot_token, generation=bot_generation)
        self._validate_bot_ref_locked(bot)
        return bot

    def _resolve_active_persona_tokens_locked(
        self,
        bot_token: str,
        persona_token: str,
    ) -> tuple[PersonaRevisionRef, dict[str, object]]:
        """Resolve an active Persona directly from its durable parent manifests."""

        bot = self._active_bot_ref_locked(bot_token)
        if bot is None:
            raise KeyError("persona not found")

        resolved_persona_token = _require_token(persona_token, "persona_v1_")
        stub = PersonaRevisionRef(
            token=resolved_persona_token,
            bot_ref=bot,
            persona_id_digest="0" * 64,
            source_fingerprint="0" * 64,
            lifecycle_generation=0,
        )
        manifest = self._load_persona_manifest_locked(stub, validate_material=False)
        if manifest is None:
            raise KeyError("persona not found")
        persona = PersonaRevisionRef(
            token=resolved_persona_token,
            bot_ref=bot,
            persona_id_digest=str(manifest["persona_id_digest"]),
            source_fingerprint=str(manifest["source_fingerprint"]),
            lifecycle_generation=int(manifest["lifecycle_generation"]),
        )
        return self._require_active_persona_locked(persona), manifest

    def _active_persona_under_other_bot_locked(
        self,
        bot_token: str,
        persona_token: str,
    ) -> bool:
        """Check durable active Persona parentage without consulting Session state."""

        try:
            bot_directories = tuple(self.bots_directory.iterdir())
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise RepositoryCorruptionError("bot directory is unreadable") from exc
        for directory in bot_directories:
            try:
                if not directory.is_dir():
                    continue
            except OSError as exc:
                raise RepositoryCorruptionError("bot directory is unreadable") from exc
            candidate_bot_token = directory.name
            if candidate_bot_token == bot_token:
                continue
            try:
                active, _manifest = self._resolve_active_persona_tokens_locked(
                    candidate_bot_token,
                    persona_token,
                )
            except ValueError:
                # Directory names are not authority.  Only a validated manifest
                # can establish parentage for the requested Persona token.
                continue
            except (KeyError, StaleScopeWrite):
                # Missing or retired foreign Personas are intentionally not
                # disclosed through this parent classifier.
                continue
            if active.bot_ref.token != bot_token:
                return True
        return False

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
        self._validate_bot_ref_locked(persona_ref.bot_ref)
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
            self._retire_persona_relations_locked(
                active,
                retired_lifecycle_generation=generation,
                reason=reason,
            )
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

    def _prepare_scope_locked(
        self,
        candidate: SessionScope,
        *,
        expected_absent: bool = False,
    ) -> SessionScope:
        """Preview the exact authoritative scope without writing repository state."""

        if type(candidate) is not SessionScope:
            raise ValueError("candidate must be a SessionScope")
        if type(expected_absent) is not bool:
            raise ValueError("expected_absent must be an exact bool")
        manifest = self._load_persona_manifest_locked(candidate.persona_ref)
        persona_generation = (
            0 if manifest is None else int(manifest["lifecycle_generation"])
        )
        active_persona = replace(
            candidate.persona_ref,
            lifecycle_generation=persona_generation,
        )
        normalized = replace(candidate, persona_ref=active_persona)
        current = self._load_scope_meta_locked(self.scope_meta_path(normalized))
        if current is None:
            return replace(normalized, scope_generation=0)
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
        return replace(
            normalized,
            scope_generation=int(current["scope_generation"]) + 1,
        )

    def _create_scope_locked(
        self,
        candidate: SessionScope,
        *,
        expected_absent: bool = False,
    ) -> SessionScope:
        prepared = self._prepare_scope_locked(
            candidate,
            expected_absent=expected_absent,
        )
        active_persona = self._activate_persona_revision_locked(candidate.persona_ref)
        if active_persona != prepared.persona_ref:
            raise RepositoryCorruptionError(
                "prepared persona generation changed during scope commit"
            )
        path = self.scope_meta_path(prepared)
        current = self._load_scope_meta_locked(path)
        if (
            current is not None
            and current["state"] == "active"
            and current["persona_lifecycle_generation"]
            == active_persona.lifecycle_generation
        ):
            self._ensure_scope_registration_locked(prepared)
            return prepared
        transition = "created" if current is None else "reactivated"
        if current is not None:
            self._cleanup_scope_components_locked(path.parent)
        self._atomic_json_replace(
            path,
            self._scope_meta_document(
                prepared,
                state="active",
                last_transition=transition,
            ),
        )
        self._ensure_scope_registration_locked(prepared)
        return prepared

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
            return self._create_scope_locked(
                candidate,
                expected_absent=expected_absent,
            )

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

    def _resolve_exact_scope_locked(
        self,
        bot_token: str,
        persona_token: str,
        session_token: str,
        *,
        missing_is_corruption: bool,
    ) -> SessionScope:
        """Resolve one known Bot/Persona/Session path without catalog scanning."""

        bot_token = _require_token(bot_token, "bot_v1_")
        persona_token = _require_token(persona_token, "persona_v1_")
        session_token = _require_token(session_token, "session_v1_")
        path = self._scope_directory(bot_token, persona_token, session_token) / "scope-meta.json"
        metadata = self._load_scope_meta_locked(path)
        if metadata is None:
            if missing_is_corruption:
                raise RepositoryCorruptionError("scope metadata is missing")
            raise KeyError("scope not found")
        if (
            metadata["bot_ref"] != bot_token
            or metadata["persona_ref"] != persona_token
            or metadata["session_ref"] != session_token
        ):
            raise RepositoryCorruptionError("scope parent chain is invalid")
        storage_token = _require_token(metadata["storage_token"], "scope_v1_")
        expected_parent = {
            "bot_ref": bot_token,
            "persona_ref": persona_token,
            "session_ref": session_token,
        }
        registered_parent = self._read_catalog_locked()["scopes"].get(storage_token)
        if registered_parent is None:
            # A scope-meta file is not authority.  A failed/partial write may
            # leave one behind, but callers must never select it by its path.
            raise KeyError("scope not found")
        if registered_parent != expected_parent:
            raise RepositoryCorruptionError("scope catalog parent is invalid")
        bot = BotRef(token=bot_token, generation=int(metadata["bot_generation"]))
        self._validate_bot_ref_locked(bot)
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
            storage_token=storage_token,
            scope_generation=int(metadata["scope_generation"]),
        )

    def _resolve_scope_locked(self, storage_token: str) -> SessionScope:
        token = _require_token(storage_token, "scope_v1_")
        catalog = self._read_catalog_locked()
        parent = catalog["scopes"].get(token)
        if type(parent) is not dict:
            raise KeyError("scope not found")
        resolved = self._resolve_exact_scope_locked(
            _require_token(parent["bot_ref"], "bot_v1_"),
            _require_token(parent["persona_ref"], "persona_v1_"),
            _require_token(parent["session_ref"], "session_v1_"),
            missing_is_corruption=True,
        )
        if resolved.storage_token != token:
            raise RepositoryCorruptionError("scope parent chain is invalid")
        return resolved

    def resolve_scope(self, storage_token: str) -> SessionScope:
        with self._repository_lock():
            return self._resolve_scope_locked(storage_token)

    def resolve_exact_scope(
        self,
        bot_token: str,
        persona_token: str,
        session_token: str,
    ) -> SessionScope:
        """Resolve only the supplied opaque three-token path under one lock."""

        with self._repository_lock():
            return self._resolve_exact_scope_locked(
                bot_token,
                persona_token,
                session_token,
                missing_is_corruption=False,
            )

    def resolve_exact_persona(
        self,
        bot_token: str,
        persona_token: str,
    ) -> PersonaRevisionRef:
        """Resolve one active durable Bot/Persona parent chain without a Session."""

        with self._repository_lock():
            resolved_bot_token = _require_token(bot_token, "bot_v1_")
            resolved_persona_token = _require_token(persona_token, "persona_v1_")
            bot = self._active_bot_ref_locked(resolved_bot_token)
            if bot is None:
                raise ScopeBotNotFound("bot not found")
            try:
                active, _manifest = self._resolve_active_persona_tokens_locked(
                    resolved_bot_token,
                    resolved_persona_token,
                )
            except KeyError as exc:
                if self._active_persona_under_other_bot_locked(
                    resolved_bot_token,
                    resolved_persona_token,
                ):
                    raise ScopeParentMismatch("persona does not belong to bot") from exc
                raise ScopePersonaNotFound("persona not found") from exc
            return active

    def list_active_scopes(self) -> tuple[SessionScope, ...]:
        """List current scopes through catalog registrations only.

        The catalog is the authoritative index.  This deliberately does not
        discover arbitrary ``scope-meta.json`` files from the filesystem.
        """

        with self._repository_lock():
            catalog = self._read_catalog_locked()
            active: list[SessionScope] = []
            for storage_token, parent in sorted(catalog["scopes"].items()):
                try:
                    scope = self._resolve_exact_scope_locked(
                        _require_token(parent["bot_ref"], "bot_v1_"),
                        _require_token(parent["persona_ref"], "persona_v1_"),
                        _require_token(parent["session_ref"], "session_v1_"),
                        missing_is_corruption=True,
                    )
                except StaleScopeWrite:
                    # Catalog registrations outlive Persona/session retirement.
                    # They remain authoritative history, but are not active UI
                    # choices. Corrupt or missing registrations still propagate.
                    continue
                if scope.storage_token != storage_token:
                    raise RepositoryCorruptionError("scope catalog parent is invalid")
                active.append(scope)
            return tuple(active)

    def read_persona_dossier(
        self,
        bot_token: str,
        persona_token: str,
    ) -> PersonaDossierSnapshot:
        """Read one active Persona and Genesis record without resolving a Session."""

        with self._repository_lock():
            active, manifest = self._resolve_active_persona_tokens_locked(
                bot_token,
                persona_token,
            )
            genesis = self._read_genesis_locked(active)
            if genesis is not None and not self._payload_matches_persona(
                genesis.payload,
                active,
            ):
                genesis = None
            return PersonaDossierSnapshot(
                persona_ref=active,
                updated_at_ms=int(manifest["updated_at_ms"]),
                genesis=genesis,
            )

    def current_scope_generation(self, storage_token: str) -> int | None:
        try:
            return self.resolve_scope(storage_token).scope_generation
        except (KeyError, StaleScopeWrite):
            return None

    def _require_active_scope_locked(self, scope: SessionScope) -> SessionScope:
        return self._validate_session_scope_locked(scope)

    def _validate_session_scope_locked(self, scope: SessionScope) -> SessionScope:
        """Fence every Session parent before inspecting a component snapshot."""

        if type(scope) is not SessionScope:
            raise ValueError("scope must be a SessionScope")
        self._validate_bot_ref_locked(scope.bot_ref)
        self._require_active_persona_locked(scope.persona_ref)
        metadata = self._load_scope_meta_locked(self.scope_meta_path(scope))
        if metadata is None:
            raise StaleScopeWrite(
                scope.scope_generation,
                None,
                code="scope_generation_stale",
            )
        if (
            metadata["storage_token"] != scope.storage_token
            or metadata["bot_ref"] != scope.bot_ref.token
            or metadata["bot_generation"] != scope.bot_ref.generation
            or metadata["persona_ref"] != scope.persona_ref.token
            or metadata["persona_lifecycle_generation"]
            != scope.persona_ref.lifecycle_generation
            or metadata["session_ref"] != scope.session_ref.token
            or metadata["session_generation"] != scope.session_ref.generation
        ):
            raise StaleScopeWrite(code="scope_parent_stale")
        if (
            metadata["state"] != "active"
            or metadata["scope_generation"] != scope.scope_generation
        ):
            raise StaleScopeWrite(
                scope.scope_generation,
                int(metadata["scope_generation"]),
                code="scope_generation_stale",
            )
        catalog = self._read_catalog_locked()
        parent = catalog["scopes"].get(scope.storage_token)
        expected_parent = {
            "bot_ref": scope.bot_ref.token,
            "persona_ref": scope.persona_ref.token,
            "session_ref": scope.session_ref.token,
        }
        if parent != expected_parent:
            raise StaleScopeWrite(code="scope_parent_stale")
        return scope

    def validate_session_scope(self, scope: SessionScope) -> SessionScope:
        """Public fail-closed validator for a frozen SessionScope."""

        with self._repository_lock():
            return self._validate_session_scope_locked(scope)

    def write_component(
        self,
        scope: SessionScope,
        component: str,
        *,
        expected_generation: int,
        payload: dict[str, object],
    ) -> int:
        name = _require_session_component(component)
        with self._repository_lock():
            self._require_active_scope_locked(scope)
            return self._write_snapshot_locked(
                self.component_path(scope, name),
                expected_generation=expected_generation,
                payload=payload,
            )

    def read_component(
        self,
        scope: SessionScope,
        component: str,
    ) -> Snapshot | None:
        name = _require_session_component(component)
        with self._repository_lock():
            self._require_active_scope_locked(scope)
            return self._read_snapshot_locked(self.component_path(scope, name))

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
            # Delete and fsync only this exact scope's bounded component files
            # before publishing the next generation.  If the process dies here,
            # the old active metadata may survive but cannot point at stale bytes;
            # once the new generation is durable, old bytes are already gone.
            self._cleanup_scope_components_locked(path.parent)
            self._atomic_json_replace(
                path,
                self._scope_meta_document(
                    invalidated,
                    state="active",
                    last_transition=reason,
                ),
            )
            self._commit_catalog_generation_locked()
            return invalidated

    def purge_session(
        self,
        scope: SessionScope,
        *,
        expected_scope_generation: int | None = None,
        reason: str = "purge",
    ) -> SessionScope:
        """Invalidate exactly one SessionScope and fence its captured writers."""

        expected = (
            scope.scope_generation
            if expected_scope_generation is None
            else _require_generation(expected_scope_generation, "expected_scope_generation")
        )
        return self.invalidate_scope(
            scope,
            expected_scope_generation=expected,
            reason=reason,
        )

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

    def _retire_persona_relations_locked(
        self,
        persona_ref: PersonaRevisionRef,
        *,
        retired_lifecycle_generation: int,
        reason: str,
    ) -> None:
        """Retire only one Persona's opaque relation lineage.

        The Persona manifest has already been published as retired before this
        helper runs, so an interruption anywhere below is fail-closed: old
        relation gateways cannot pass their Persona lifecycle fence.  Components
        are removed before the new retired metadata is published; activation can
        safely repeat that cleanup if a process stops between those writes.
        """

        _require_generation(
            retired_lifecycle_generation,
            "retired_lifecycle_generation",
        )
        if type(reason) is not str or not reason:
            raise ValueError("reason must be a non-empty str")
        relations = self._persona_directory(
            persona_ref.bot_ref.token,
            persona_ref.token,
        ) / "relations"
        if not relations.is_dir():
            return
        retired_persona = replace(
            persona_ref,
            lifecycle_generation=retired_lifecycle_generation,
        )
        for child in sorted(relations.iterdir(), key=lambda entry: entry.name):
            if not child.is_dir() or not child.name.startswith("relation_v1_"):
                continue
            try:
                relation_ref = RelationRef(
                    token=child.name,
                    bot_ref=persona_ref.bot_ref,
                )
            except ValueError as exc:
                raise ScopeCorrupt("relation directory token is invalid") from exc
            # A previous interruption may have left this record in an older
            # lifecycle.  Static Bot/Persona/relation parents still have to
            # match exactly; only an earlier Persona lifecycle is recoverable.
            metadata = self._read_relation_meta_locked(
                persona_ref,
                relation_ref,
                allow_prior_persona_lifecycle=True,
            )
            self._cleanup_relation_components_locked(child)
            if metadata is None:
                continue
            self._write_relation_meta_locked(
                retired_persona,
                relation_ref,
                state="retired",
                relation_generation=int(metadata["relation_generation"]),
                last_transition=reason,
            )

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

    def _relation_meta_path_for_refs(
        self,
        persona_ref: PersonaRevisionRef,
        relation_ref: RelationRef,
    ) -> Path:
        if type(persona_ref) is not PersonaRevisionRef:
            raise ValueError("persona_ref must be a PersonaRevisionRef")
        if type(relation_ref) is not RelationRef:
            raise ValueError("relation_ref must be a RelationRef")
        if relation_ref.bot_ref != persona_ref.bot_ref:
            raise ScopeParentMismatch("relation does not belong to persona Bot")
        return (
            self._relation_directory(
                persona_ref.bot_ref.token,
                persona_ref.token,
                relation_ref.token,
            )
            / "relation-meta.json"
        )

    def _relation_meta_document(
        self,
        persona_ref: PersonaRevisionRef,
        relation_ref: RelationRef,
        *,
        state: str,
        relation_generation: int,
        last_transition: str,
    ) -> dict[str, object]:
        if state not in {"active", "retired"}:
            raise ValueError("relation metadata state is invalid")
        _require_generation(relation_generation, "relation_generation")
        if type(last_transition) is not str or not last_transition:
            raise ValueError("last_transition must be a non-empty str")
        return {
            "schema_version": _RELATION_META_SCHEMA,
            "bot_ref": persona_ref.bot_ref.token,
            "bot_generation": persona_ref.bot_ref.generation,
            "persona_ref": persona_ref.token,
            "persona_lifecycle_generation": persona_ref.lifecycle_generation,
            "relation_ref": relation_ref.token,
            "relation_generation": relation_generation,
            "state": state,
            "updated_at_ms": self._now_ms(),
            "last_transition": last_transition,
        }

    def _read_relation_meta_locked(
        self,
        persona_ref: PersonaRevisionRef,
        relation_ref: RelationRef,
        *,
        allow_prior_persona_lifecycle: bool = False,
    ) -> dict[str, object] | None:
        """Read one opaque relation authority record without subject material."""

        if type(allow_prior_persona_lifecycle) is not bool:
            raise ValueError("allow_prior_persona_lifecycle must be an exact bool")
        path = self._relation_meta_path_for_refs(persona_ref, relation_ref)
        loaded = self._read_json(path, error_label="relation metadata")
        if loaded is None:
            return None
        raw, document = loaded
        expected_fields = {
            "schema_version",
            "bot_ref",
            "bot_generation",
            "persona_ref",
            "persona_lifecycle_generation",
            "relation_ref",
            "relation_generation",
            "state",
            "updated_at_ms",
            "last_transition",
        }
        if (
            set(document) != expected_fields
            or document["schema_version"] != _RELATION_META_SCHEMA
            or type(document["bot_generation"]) is not int
            or int(document["bot_generation"]) < 0
            or type(document["persona_lifecycle_generation"]) is not int
            or int(document["persona_lifecycle_generation"]) < 0
            or type(document["relation_generation"]) is not int
            or int(document["relation_generation"]) < 0
            or document["state"] not in {"active", "retired"}
            or type(document["updated_at_ms"]) is not int
            or type(document["last_transition"]) is not str
            or raw != _canonical_json_bytes(document)
        ):
            raise ScopeCorrupt("relation metadata is invalid")
        _require_token(document["bot_ref"], "bot_v1_")
        _require_token(document["persona_ref"], "persona_v1_")
        _require_token(document["relation_ref"], "relation_v1_")
        if (
            document["bot_ref"] != persona_ref.bot_ref.token
            or document["bot_generation"] != persona_ref.bot_ref.generation
            or document["persona_ref"] != persona_ref.token
            or document["relation_ref"] != relation_ref.token
        ):
            raise ScopeParentMismatch("relation metadata parent mismatch")
        recorded_lifecycle_generation = int(document["persona_lifecycle_generation"])
        if recorded_lifecycle_generation != persona_ref.lifecycle_generation and (
            not allow_prior_persona_lifecycle
            or recorded_lifecycle_generation > persona_ref.lifecycle_generation
        ):
            raise ScopeParentMismatch("relation metadata parent mismatch")
        return document

    def _write_relation_meta_locked(
        self,
        persona_ref: PersonaRevisionRef,
        relation_ref: RelationRef,
        *,
        state: str,
        relation_generation: int,
        last_transition: str,
    ) -> None:
        self._atomic_json_replace(
            self._relation_meta_path_for_refs(persona_ref, relation_ref),
            self._relation_meta_document(
                persona_ref,
                relation_ref,
                state=state,
                relation_generation=relation_generation,
                last_transition=last_transition,
            ),
        )
        self._commit_catalog_generation_locked()

    def _cleanup_relation_components_locked(self, directory: Path) -> None:
        """Remove only known component files beneath one exact relation path."""

        components = directory / "components"
        changed = False
        for component in _RELATION_COMPONENTS:
            try:
                (components / f"{component}.json").unlink()
            except FileNotFoundError:
                continue
            changed = True
        if changed:
            self._fsync_dir(components)

    def _activate_relation_scope_locked(
        self,
        persona_ref: PersonaRevisionRef,
        relation_ref: RelationRef,
        *,
        expected_absent: bool = False,
    ) -> RelationScope:
        """Locked relation activation; callers never choose a generation."""

        if type(persona_ref) is not PersonaRevisionRef:
            raise ValueError("persona_ref must be a PersonaRevisionRef")
        if type(relation_ref) is not RelationRef:
            raise ValueError("relation_ref must be a RelationRef")
        if type(expected_absent) is not bool:
            raise ValueError("expected_absent must be an exact bool")
        if relation_ref.bot_ref != persona_ref.bot_ref:
            raise ScopeParentMismatch("relation does not belong to persona Bot")
        active_persona = self._require_active_persona_locked(persona_ref)
        current = self._read_relation_meta_locked(
            active_persona,
            relation_ref,
            allow_prior_persona_lifecycle=True,
        )
        if expected_absent and current is not None:
            raise StaleScopeWrite(
                0,
                int(current["relation_generation"]),
                code="relation_exists",
            )
        if current is None:
            generation = 0
            transition = "created"
        elif int(current["persona_lifecycle_generation"]) != active_persona.lifecycle_generation:
            # A crash may have retired the Persona manifest before the relation
            # record.  The read helper permits only an *older* lifecycle here;
            # static Bot/Persona/relation parents remain exact.  Advance the
            # relation generation so every old gateway stays fenced.
            generation = int(current["relation_generation"]) + 1
            transition = "persona-reactivated"
        elif current["state"] == "active":
            return RelationScope(
                bot_ref=active_persona.bot_ref,
                persona_ref=active_persona,
                relation_ref=relation_ref,
                relation_generation=int(current["relation_generation"]),
            )
        elif current["state"] == "retired":
            generation = int(current["relation_generation"]) + 1
            transition = "reactivated"
            self._cleanup_relation_components_locked(
                self._relation_meta_path_for_refs(
                    active_persona,
                    relation_ref,
                ).parent
            )
        else:  # Defensive even though _read_relation_meta_locked validates it.
            raise ScopeCorrupt("relation metadata state is invalid")
        # Remove bounded old component bytes before publishing a new active
        # generation.  This also clears component-only remnants when metadata
        # was lost before a prior create reached its metadata publication.
        self._cleanup_relation_components_locked(
            self._relation_meta_path_for_refs(
                active_persona,
                relation_ref,
            ).parent
        )
        self._write_relation_meta_locked(
            active_persona,
            relation_ref,
            state="active",
            relation_generation=generation,
            last_transition=transition,
        )
        return RelationScope(
            bot_ref=active_persona.bot_ref,
            persona_ref=active_persona,
            relation_ref=relation_ref,
            relation_generation=generation,
        )

    def activate_relation_scope(
        self,
        persona_ref: PersonaRevisionRef,
        relation_ref: RelationRef,
    ) -> RelationScope:
        """Activate exactly one opaque relation beneath an active Persona.

        The caller supplies no relation generation.  A retired relation advances
        exactly once while the repository lock is held; concurrent activators
        then observe the same active generation.
        """

        if type(persona_ref) is not PersonaRevisionRef:
            raise ValueError("persona_ref must be a PersonaRevisionRef")
        if type(relation_ref) is not RelationRef:
            raise ValueError("relation_ref must be a RelationRef")
        if relation_ref.bot_ref != persona_ref.bot_ref:
            raise ScopeParentMismatch("relation does not belong to persona Bot")
        with self._repository_lock():
            return self._activate_relation_scope_locked(persona_ref, relation_ref)

    def create_relation_scope(
        self,
        candidate: RelationScope,
        *,
        expected_absent: bool = False,
    ) -> RelationScope:
        """Narrow compatibility seam; production must use activation directly."""

        if type(candidate) is not RelationScope:
            raise ValueError("candidate must be a RelationScope")
        if type(expected_absent) is not bool:
            raise ValueError("expected_absent must be an exact bool")
        # ``candidate.relation_generation`` is a stale-writer fence, never an
        # input used to choose a new generation.  The expected-absent decision
        # and activation share one repository lock so a concurrent creator
        # cannot pass a generation-zero TOCTOU window.
        with self._repository_lock():
            active = self._activate_relation_scope_locked(
                candidate.persona_ref,
                candidate.relation_ref,
                expected_absent=expected_absent,
            )
            if active.relation_generation != candidate.relation_generation:
                raise StaleScopeWrite(
                    candidate.relation_generation,
                    active.relation_generation,
                    code="relation_generation_stale",
                )
            return active

    def _validate_relation_scope_locked(self, scope: RelationScope) -> RelationScope:
        """Fence Bot, Persona lifecycle, relation parent, and relation generation."""

        if type(scope) is not RelationScope:
            raise ValueError("scope must be a RelationScope")
        if scope.relation_ref.bot_ref != scope.bot_ref:
            raise ScopeParentMismatch("relation does not belong to scope Bot")
        self._validate_bot_ref_locked(scope.bot_ref)
        self._require_active_persona_locked(scope.persona_ref)
        current = self._read_relation_meta_locked(scope.persona_ref, scope.relation_ref)
        if (
            current is None
            or current["state"] != "active"
            or current["relation_generation"] != scope.relation_generation
        ):
            raise StaleScopeWrite(
                scope.relation_generation,
                None if current is None else int(current["relation_generation"]),
                code="relation_generation_stale",
            )
        return scope

    def validate_relation_scope(self, scope: RelationScope) -> RelationScope:
        """Public fail-closed validator for a frozen RelationScope."""

        with self._repository_lock():
            return self._validate_relation_scope_locked(scope)

    def write_relation_component(
        self,
        scope: RelationScope,
        component: str,
        *,
        expected_generation: int,
        payload: dict[str, object],
    ) -> int:
        name = _require_relation_component(component)
        with self._repository_lock():
            self._validate_relation_scope_locked(scope)
            return self._write_snapshot_locked(
                self.relation_component_path(scope, name),
                expected_generation=expected_generation,
                payload=payload,
            )

    def read_relation_component(
        self,
        scope: RelationScope,
        component: str,
    ) -> Snapshot | None:
        name = _require_relation_component(component)
        with self._repository_lock():
            self._validate_relation_scope_locked(scope)
            return self._read_snapshot_locked(self.relation_component_path(scope, name))

    def invalidate_relation(
        self,
        scope: RelationScope,
        *,
        expected_relation_generation: int,
        reason: str,
    ) -> RelationScope:
        _require_generation(expected_relation_generation, "expected_relation_generation")
        if type(reason) is not str or not reason:
            raise ValueError("reason must be a non-empty str")
        with self._repository_lock():
            self._validate_relation_scope_locked(scope)
            if scope.relation_generation != expected_relation_generation:
                raise StaleScopeWrite(
                    expected_relation_generation,
                    scope.relation_generation,
                    code="relation_generation_stale",
                )
            self._cleanup_relation_components_locked(self.relation_meta_path(scope).parent)
            self._write_relation_meta_locked(
                scope.persona_ref,
                scope.relation_ref,
                state="retired",
                relation_generation=scope.relation_generation,
                last_transition=reason,
            )
            return scope

    def purge_relation(
        self,
        scope: RelationScope,
        *,
        expected_relation_generation: int,
        reason: str = "purge",
    ) -> RelationScope:
        """Purge exactly one relation and leave its old gateway fenced."""

        return self.invalidate_relation(
            scope,
            expected_relation_generation=expected_relation_generation,
            reason=reason,
        )

    # -- Persona Genesis: persona-owned control and activation record --------

    def genesis_path(self, persona_ref: PersonaRevisionRef) -> Path:
        if type(persona_ref) is not PersonaRevisionRef:
            raise ValueError("persona_ref must be a PersonaRevisionRef")
        return (
            self._persona_directory(persona_ref.bot_ref.token, persona_ref.token)
            / "genesis.json"
        )

    def _genesis_corruption_marker_path(self, persona_ref: PersonaRevisionRef) -> Path:
        return self.genesis_path(persona_ref).parent / "quarantine" / "genesis-markers.json"

    def _read_genesis_corruption_markers_locked(
        self,
        persona_ref: PersonaRevisionRef,
    ) -> set[tuple[int, str]]:
        loaded = self._read_json(
            self._genesis_corruption_marker_path(persona_ref),
            error_label="persona genesis corruption markers",
        )
        if loaded is None:
            return set()
        raw, document = loaded
        entries = document.get("entries")
        if (
            set(document) != {"schema_version", "entries"}
            or document["schema_version"] != _PERSONA_GENESIS_CORRUPTION_SCHEMA
            or type(entries) is not list
            or raw != _canonical_json_bytes(document)
        ):
            raise RepositoryCorruptionError("persona genesis corruption markers are invalid")
        parsed: set[tuple[int, str]] = set()
        for entry in entries:
            if (
                type(entry) is not dict
                or set(entry) != {"lifecycle_generation", "source_fingerprint"}
                or type(entry["lifecycle_generation"]) is not int
                or entry["lifecycle_generation"] < 0
                or type(entry["source_fingerprint"]) is not str
                or len(entry["source_fingerprint"]) != 64
            ):
                raise RepositoryCorruptionError("persona genesis corruption marker is invalid")
            parsed.add((entry["lifecycle_generation"], entry["source_fingerprint"]))
        if len(parsed) != len(entries):
            raise RepositoryCorruptionError("persona genesis corruption markers are duplicated")
        return parsed

    def _has_genesis_corruption_marker_locked(
        self,
        persona_ref: PersonaRevisionRef,
    ) -> bool:
        try:
            markers = self._read_genesis_corruption_markers_locked(persona_ref)
        except RepositoryCorruptionError:
            # A damaged deny marker must never silently turn into a retry permit.
            return True
        return (
            persona_ref.lifecycle_generation,
            persona_ref.source_fingerprint,
        ) in markers

    def _mark_genesis_corruption_locked(self, persona_ref: PersonaRevisionRef) -> None:
        path = self._genesis_corruption_marker_path(persona_ref)
        try:
            markers = self._read_genesis_corruption_markers_locked(persona_ref)
        except RepositoryCorruptionError:
            # Keep the malformed marker as an evidence-bearing fail-closed fence.
            return
        marker = (
            persona_ref.lifecycle_generation,
            persona_ref.source_fingerprint,
        )
        if marker in markers:
            return
        markers.add(marker)
        entries = [
            {
                "lifecycle_generation": lifecycle_generation,
                "source_fingerprint": source_fingerprint,
            }
            for lifecycle_generation, source_fingerprint in sorted(markers)
        ]
        self._atomic_json_replace(
            path,
            {
                "schema_version": _PERSONA_GENESIS_CORRUPTION_SCHEMA,
                "entries": entries,
            },
        )

    def _quarantine_genesis_locked(
        self,
        path: Path,
        persona_ref: PersonaRevisionRef,
    ) -> None:
        # Persist the exact lifecycle/source deny marker before moving evidence.
        # A later source revision remains independently schedulable.
        self._mark_genesis_corruption_locked(persona_ref)
        self._quarantine_locked(path)

    @staticmethod
    def _require_genesis_source(
        persona_ref: PersonaRevisionRef,
        source_fingerprint: object,
    ) -> str:
        if (
            type(source_fingerprint) is not str
            or source_fingerprint != persona_ref.source_fingerprint
        ):
            raise StaleScopeWrite(code="persona_source_stale")
        return source_fingerprint

    @staticmethod
    def _require_genesis_lease(lease: object) -> PersonaGenesisLease:
        if type(lease) is not PersonaGenesisLease:
            raise ValueError("lease must be a PersonaGenesisLease")
        if (
            type(lease.persona_token) is not str
            or type(lease.lifecycle_generation) is not int
            or lease.lifecycle_generation < 0
            or type(lease.source_fingerprint) is not str
            or type(lease.origin_turn_generation) is not int
            or lease.origin_turn_generation < 0
            or type(lease.attempt) is not int
            or lease.attempt < 1
            or type(lease.lease_id) is not str
            or not lease.lease_id
            or type(lease.fence) is not int
            or lease.fence < 1
            or type(lease.expires_at_ms) is not int
            or lease.expires_at_ms < 0
        ):
            raise ValueError("lease is invalid")
        return lease

    @staticmethod
    def _require_genesis_now(now_ms: int | None) -> int:
        value = ScopeRepository._now_ms() if now_ms is None else now_ms
        if type(value) is not int or value < 0:
            raise ValueError("now_ms must be a non-negative exact int")
        return value

    @staticmethod
    def _utc_day(now_ms: int) -> str:
        return datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")

    @staticmethod
    def _is_canonical_utc_day(value: object) -> bool:
        if type(value) is not str:
            return False
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return False
        return parsed.isoformat() == value

    def _read_persona_genesis_global_locked(
        self,
        *,
        now_ms: int,
    ) -> tuple[dict[str, object], bool]:
        loaded = self._read_json(
            self._persona_genesis_global_path,
            error_label="persona genesis global control",
        )
        if loaded is None:
            return {
                "schema_version": _PERSONA_GENESIS_GLOBAL_SCHEMA,
                "day": self._utc_day(now_ms),
                "calls": 0,
                "fence": 0,
                "lease": None,
            }, False
        raw, document = loaded
        if (
            set(document) != {"schema_version", "day", "calls", "fence", "lease"}
            or document["schema_version"] != _PERSONA_GENESIS_GLOBAL_SCHEMA
            or not self._is_canonical_utc_day(document["day"])
            or type(document["calls"]) is not int
            or not 0 <= document["calls"] <= _PERSONA_GENESIS_DAILY_LIMIT
            or type(document["fence"]) is not int
            or document["fence"] < 0
            or raw != _canonical_json_bytes(document)
        ):
            raise RepositoryCorruptionError("persona genesis global control is invalid")
        lease = document["lease"]
        if lease is not None and (
            type(lease) is not dict
            or set(lease) != {"lease_id", "fence", "expires_at_ms"}
            or type(lease["lease_id"]) is not str
            or not lease["lease_id"]
            or type(lease["fence"]) is not int
            or lease["fence"] < 1
            or type(lease["expires_at_ms"]) is not int
            or lease["expires_at_ms"] < 0
        ):
            raise RepositoryCorruptionError("persona genesis global lease is invalid")

        normalized = dict(document)
        changed = False
        current_day = self._utc_day(now_ms)
        # ISO UTC dates compare chronologically.  Only a strictly later wall
        # clock day earns a reset; rollback must retain the persisted budget.
        if current_day > normalized["day"]:
            normalized["day"] = current_day
            normalized["calls"] = 0
            changed = True
        if lease is not None and lease["expires_at_ms"] <= now_ms:
            normalized["lease"] = None
            changed = True
        return normalized, changed

    def _write_persona_genesis_global_locked(self, document: dict[str, object]) -> None:
        self._atomic_json_replace(self._persona_genesis_global_path, document)

    @staticmethod
    def _validate_genesis_payload(payload: object) -> dict[str, object]:
        if type(payload) is not dict:
            raise RepositoryCorruptionError("persona genesis payload is invalid")
        state = payload.get("state")
        common = {
            "state",
            "persona_lifecycle_generation",
            "source_fingerprint",
            "attempt",
        }
        if state == "claimed":
            expected = common | {
                "lease_id",
                "fence",
                "lease_expires_at_ms",
                "origin_turn_generation",
            }
        elif state == "backoff":
            expected = common | {"next_attempt_at_ms"}
        elif state == "active":
            expected = common | {
                "accepted_profile",
                "initial_runtime",
                "growth_enabled",
                "origin_turn_generation",
                "safe_metadata",
            }
        else:
            raise RepositoryCorruptionError("persona genesis state is invalid")
        if set(payload) != expected:
            raise RepositoryCorruptionError("persona genesis payload has an invalid shape")
        if (
            type(payload["persona_lifecycle_generation"]) is not int
            or payload["persona_lifecycle_generation"] < 0
            or type(payload["source_fingerprint"]) is not str
            or len(payload["source_fingerprint"]) != 64
            or type(payload["attempt"]) is not int
            or payload["attempt"] < 1
        ):
            raise RepositoryCorruptionError("persona genesis payload has invalid control fields")
        if state == "claimed":
            if (
                type(payload["lease_id"]) is not str
                or not payload["lease_id"]
                or type(payload["fence"]) is not int
                or payload["fence"] < 1
                or type(payload["lease_expires_at_ms"]) is not int
                or payload["lease_expires_at_ms"] < 0
                or type(payload["origin_turn_generation"]) is not int
                or payload["origin_turn_generation"] < 0
            ):
                raise RepositoryCorruptionError("persona genesis claim is invalid")
        elif state == "backoff":
            if (
                type(payload["next_attempt_at_ms"]) is not int
                or payload["next_attempt_at_ms"] < 0
            ):
                raise RepositoryCorruptionError("persona genesis backoff is invalid")
        else:
            from .persona_genesis import (
                PersonaGenesisParseError,
                canonical_persona_genesis_json,
                parse_persona_genesis_profile,
            )

            profile = payload["accepted_profile"]
            try:
                canonical = canonical_persona_genesis_json(profile)
                if parse_persona_genesis_profile(canonical.decode("utf-8")) != profile:
                    raise PersonaGenesisParseError("profile changed during validation")
            except (PersonaGenesisParseError, UnicodeDecodeError) as exc:
                raise RepositoryCorruptionError("persona genesis profile is invalid") from exc
            origin = payload["origin_turn_generation"]
            expected_runtime = {
                "priors": profile,
                "growth_enabled": True,
                "origin_turn_generation": origin,
            }
            if (
                type(origin) is not int
                or origin < 0
                or payload["growth_enabled"] is not True
                or payload["initial_runtime"] != expected_runtime
                or type(payload["safe_metadata"]) is not dict
                or set(payload["safe_metadata"]) != {"accepted_at_ms"}
                or type(payload["safe_metadata"]["accepted_at_ms"]) is not int
                or payload["safe_metadata"]["accepted_at_ms"] < 0
            ):
                raise RepositoryCorruptionError("persona genesis activation is invalid")
        return payload

    def _read_genesis_locked(self, persona_ref: PersonaRevisionRef) -> Snapshot | None:
        if self._has_genesis_corruption_marker_locked(persona_ref):
            return None
        path = self.genesis_path(persona_ref)
        try:
            snapshot = self._read_snapshot_locked(path, quarantine_on_error=False)
            if snapshot is None:
                return None
            self._validate_genesis_payload(snapshot.payload)
        except RepositoryCorruptionError:
            self._quarantine_genesis_locked(path, persona_ref)
            return None
        return snapshot

    @staticmethod
    def _payload_matches_persona(
        payload: dict[str, object],
        persona_ref: PersonaRevisionRef,
    ) -> bool:
        return (
            payload["persona_lifecycle_generation"] == persona_ref.lifecycle_generation
            and payload["source_fingerprint"] == persona_ref.source_fingerprint
        )

    def _read_genesis_schedule_snapshot_locked(
        self,
        persona_ref: PersonaRevisionRef,
    ) -> Snapshot | None:
        """Read Genesis control and durably quarantine malformed input."""

        return self._read_genesis_locked(persona_ref)

    def _persona_genesis_schedule_preflight_locked(
        self,
        active: PersonaRevisionRef,
        *,
        now_ms: int,
    ) -> str:
        """Return one atomic local-control decision while the repository is locked."""

        if self._has_genesis_corruption_marker_locked(active):
            return "blocked"
        snapshot = self._read_genesis_schedule_snapshot_locked(active)
        if snapshot is None:
            if self._has_genesis_corruption_marker_locked(active):
                return "blocked"
            locally_allowed = True
        else:
            payload = snapshot.payload
            if not self._payload_matches_persona(payload, active):
                # The Genesis file is reused across lifecycle reactivation of
                # one exact Persona token.  A structurally valid record from a
                # prior lifecycle is historical state, not a durable deny
                # marker for the newly active generation.  Treat it like an
                # absent current record so preflight agrees with the claim CAS.
                locally_allowed = True
            else:
                if payload["state"] == "active":
                    return "active"
                if payload["state"] == "claimed":
                    locally_allowed = payload["lease_expires_at_ms"] <= now_ms
                elif payload["state"] == "backoff":
                    locally_allowed = payload["next_attempt_at_ms"] <= now_ms
                else:
                    return "blocked"
        if not locally_allowed:
            return "blocked"
        global_state, _changed = self._read_persona_genesis_global_locked(now_ms=now_ms)
        if (
            self._utc_day(now_ms) < global_state["day"]
            or global_state["lease"] is not None
            or global_state["calls"] >= _PERSONA_GENESIS_DAILY_LIMIT
        ):
            return "blocked"
        return "allowed"

    def persona_genesis_schedule_preflight_nowait(
        self,
        persona_ref: PersonaRevisionRef,
        *,
        source_fingerprint: str,
        now_ms: int | None = None,
    ) -> str:
        """Immediate request-path Genesis preflight: ``allowed``/``active``/blocked.

        This uses a single timeout-zero interprocess lock.  Contention, malformed
        records, and any lifecycle ambiguity fail closed without creating a task.
        """

        if type(persona_ref) is not PersonaRevisionRef:
            return "blocked"
        try:
            now = self._require_genesis_now(now_ms)
            with self._repository_lock_nowait():
                active = self._require_active_persona_locked(persona_ref)
                self._require_genesis_source(active, source_fingerprint)
                return self._persona_genesis_schedule_preflight_locked(
                    active,
                    now_ms=now,
                )
        except (
            portalocker.exceptions.LockException,
            RepositoryCorruptionError,
            StaleScopeWrite,
            OSError,
            ValueError,
        ):
            return "blocked"

    def persona_genesis_schedule_allowed(
        self,
        persona_ref: PersonaRevisionRef,
        *,
        source_fingerprint: str,
        now_ms: int | None = None,
    ) -> bool:
        """Fail closed before creating a Genesis task or resolving a provider."""

        if type(persona_ref) is not PersonaRevisionRef:
            return False
        try:
            now = self._require_genesis_now(now_ms)
            with self._repository_lock():
                active = self._require_active_persona_locked(persona_ref)
                self._require_genesis_source(active, source_fingerprint)
                return (
                    self._persona_genesis_schedule_preflight_locked(active, now_ms=now)
                    == "allowed"
                )
        except (RepositoryCorruptionError, StaleScopeWrite, OSError, ValueError):
            return False

    def persona_genesis_authorization_valid(
        self,
        persona_ref: PersonaRevisionRef,
        *,
        source_fingerprint: str,
    ) -> bool:
        """Read-only lifecycle/source fence for an in-flight Genesis result."""

        if type(persona_ref) is not PersonaRevisionRef:
            return False
        try:
            with self._repository_lock():
                active = self._require_active_persona_locked(persona_ref)
                self._require_genesis_source(active, source_fingerprint)
                return not self._has_genesis_corruption_marker_locked(active)
        except (RepositoryCorruptionError, StaleScopeWrite, OSError, ValueError):
            return False

    @staticmethod
    def _claim_matches_lease(
        payload: dict[str, object],
        lease: PersonaGenesisLease,
    ) -> bool:
        return (
            payload.get("state") == "claimed"
            and payload.get("lease_id") == lease.lease_id
            and payload.get("fence") == lease.fence
            and payload.get("attempt") == lease.attempt
            and payload.get("lease_expires_at_ms") == lease.expires_at_ms
            and payload.get("origin_turn_generation") == lease.origin_turn_generation
        )

    @staticmethod
    def _global_lease_matches(
        document: dict[str, object],
        lease: PersonaGenesisLease,
    ) -> bool:
        value = document.get("lease")
        return (
            type(value) is dict
            and value.get("lease_id") == lease.lease_id
            and value.get("fence") == lease.fence
        )

    def _release_global_lease_locked(
        self,
        document: dict[str, object],
        lease: PersonaGenesisLease,
    ) -> bool:
        if not self._global_lease_matches(document, lease):
            return False
        released = dict(document)
        released["lease"] = None
        self._write_persona_genesis_global_locked(released)
        return True

    def claim_persona_genesis(
        self,
        persona_ref: PersonaRevisionRef,
        *,
        source_fingerprint: str,
        origin_turn_generation: int,
        now_ms: int | None = None,
        lease_ms: int = _PERSONA_GENESIS_LEASE_MS,
    ) -> PersonaGenesisLease | None:
        """CAS-claim a single globally budgeted Genesis provider attempt.

        Calls are consumed before the provider runs and are deliberately never
        refunded.  A live global lease, a Persona-local cooldown, or a completed
        activation all fail closed without touching provider-facing state.
        """

        if type(persona_ref) is not PersonaRevisionRef:
            raise ValueError("persona_ref must be a PersonaRevisionRef")
        if type(origin_turn_generation) is not int or origin_turn_generation < 0:
            raise ValueError("origin_turn_generation must be a non-negative exact int")
        if type(lease_ms) is not int or lease_ms < 1:
            raise ValueError("lease_ms must be a positive exact int")
        now = self._require_genesis_now(now_ms)
        with self._repository_lock():
            active = self._require_active_persona_locked(persona_ref)
            source = self._require_genesis_source(active, source_fingerprint)
            if self._has_genesis_corruption_marker_locked(active):
                return None
            snapshot = self._read_genesis_locked(active)
            if self._has_genesis_corruption_marker_locked(active):
                return None
            payload = None if snapshot is None else snapshot.payload
            is_current = payload is not None and self._payload_matches_persona(payload, active)
            if is_current and payload["state"] == "active":
                return None
            if is_current and payload["state"] == "claimed" and payload["lease_expires_at_ms"] > now:
                return None
            if is_current and payload["state"] == "backoff" and payload["next_attempt_at_ms"] > now:
                return None

            global_state, changed = self._read_persona_genesis_global_locked(now_ms=now)
            # A clock rollback may not reopen yesterday's quota.  Leave the
            # persisted control untouched; a strictly later UTC day resets it.
            if self._utc_day(now) < global_state["day"]:
                return None
            if global_state["lease"] is not None or global_state["calls"] >= _PERSONA_GENESIS_DAILY_LIMIT:
                if changed:
                    self._write_persona_genesis_global_locked(global_state)
                return None
            attempt = int(payload["attempt"]) + 1 if is_current else 1
            fence = int(global_state["fence"]) + 1
            lease = PersonaGenesisLease(
                persona_token=active.token,
                lifecycle_generation=active.lifecycle_generation,
                source_fingerprint=source,
                origin_turn_generation=origin_turn_generation,
                attempt=attempt,
                lease_id=secrets.token_hex(16),
                fence=fence,
                expires_at_ms=now + lease_ms,
            )
            next_global = dict(global_state)
            next_global["calls"] = int(global_state["calls"]) + 1
            next_global["fence"] = fence
            next_global["lease"] = {
                "lease_id": lease.lease_id,
                "fence": lease.fence,
                "expires_at_ms": lease.expires_at_ms,
            }
            self._write_persona_genesis_global_locked(next_global)
            claim = {
                "state": "claimed",
                "persona_lifecycle_generation": active.lifecycle_generation,
                "source_fingerprint": source,
                "attempt": attempt,
                "lease_id": lease.lease_id,
                "fence": lease.fence,
                "lease_expires_at_ms": lease.expires_at_ms,
                "origin_turn_generation": origin_turn_generation,
            }
            expected_generation = 0 if snapshot is None else snapshot.generation
            self._write_snapshot_locked(
                self.genesis_path(active),
                expected_generation=expected_generation,
                payload=claim,
            )
            return lease

    def commit_persona_genesis_activation(
        self,
        persona_ref: PersonaRevisionRef,
        lease: PersonaGenesisLease,
        *,
        profile: dict[str, object],
        source_fingerprint: str,
        origin_turn_generation: int,
        now_ms: int | None = None,
    ) -> Snapshot:
        """Atomically replace a matching claim with the sole active record."""

        if type(persona_ref) is not PersonaRevisionRef:
            raise ValueError("persona_ref must be a PersonaRevisionRef")
        if type(profile) is not dict:
            raise ValueError("profile must be an exact dict")
        if type(origin_turn_generation) is not int or origin_turn_generation < 0:
            raise ValueError("origin_turn_generation must be a non-negative exact int")
        claim_lease = self._require_genesis_lease(lease)
        now = self._require_genesis_now(now_ms)
        with self._repository_lock():
            active = self._require_active_persona_locked(persona_ref)
            source = self._require_genesis_source(active, source_fingerprint)
            if (
                claim_lease.persona_token != active.token
                or claim_lease.lifecycle_generation != active.lifecycle_generation
                or claim_lease.source_fingerprint != source
                or claim_lease.origin_turn_generation != origin_turn_generation
                or claim_lease.expires_at_ms <= now
            ):
                raise StaleScopeWrite(code="persona_genesis_lease_stale")
            snapshot = self._read_genesis_locked(active)
            if (
                snapshot is None
                or not self._payload_matches_persona(snapshot.payload, active)
                or not self._claim_matches_lease(snapshot.payload, claim_lease)
            ):
                raise StaleScopeWrite(code="persona_genesis_claim_stale")
            global_state, _changed = self._read_persona_genesis_global_locked(now_ms=now)
            if not self._global_lease_matches(global_state, claim_lease):
                raise StaleScopeWrite(code="persona_genesis_lease_stale")
            from .persona_genesis import canonical_persona_genesis_json, parse_persona_genesis_profile

            accepted_profile = parse_persona_genesis_profile(
                canonical_persona_genesis_json(profile).decode("utf-8")
            )
            activation = {
                "state": "active",
                "persona_lifecycle_generation": active.lifecycle_generation,
                "source_fingerprint": source,
                "attempt": claim_lease.attempt,
                "accepted_profile": accepted_profile,
                "initial_runtime": {
                    "priors": accepted_profile,
                    "growth_enabled": True,
                    "origin_turn_generation": origin_turn_generation,
                },
                "growth_enabled": True,
                "origin_turn_generation": origin_turn_generation,
                "safe_metadata": {"accepted_at_ms": now},
            }
            generation = self._write_snapshot_locked(
                self.genesis_path(active),
                expected_generation=snapshot.generation,
                payload=activation,
            )
            self._release_global_lease_locked(global_state, claim_lease)
            return Snapshot(generation=generation, payload=activation)

    def reject_persona_genesis_claim(
        self,
        persona_ref: PersonaRevisionRef,
        lease: PersonaGenesisLease,
        *,
        source_fingerprint: str,
        now_ms: int | None = None,
        backoff_ms: int = 60_000,
    ) -> bool:
        """CAS a matching claim into retry backoff and conditionally free its slot."""

        if type(persona_ref) is not PersonaRevisionRef:
            raise ValueError("persona_ref must be a PersonaRevisionRef")
        if type(backoff_ms) is not int or backoff_ms < 0:
            raise ValueError("backoff_ms must be a non-negative exact int")
        claim_lease = self._require_genesis_lease(lease)
        now = self._require_genesis_now(now_ms)
        with self._repository_lock():
            active = self._require_active_persona_locked(persona_ref)
            source = self._require_genesis_source(active, source_fingerprint)
            if (
                claim_lease.persona_token != active.token
                or claim_lease.lifecycle_generation != active.lifecycle_generation
                or claim_lease.source_fingerprint != source
            ):
                return False
            # Backoff is only legal while this exact, still-live global lease is
            # current.  A stale task must leave its Persona claim byte-for-byte
            # intact and may never overwrite a replacement attempt.
            global_state, _changed = self._read_persona_genesis_global_locked(now_ms=now)
            if (
                claim_lease.expires_at_ms <= now
                or not self._global_lease_matches(global_state, claim_lease)
            ):
                return False
            snapshot = self._read_genesis_locked(active)
            if (
                snapshot is None
                or not self._payload_matches_persona(snapshot.payload, active)
                or not self._claim_matches_lease(snapshot.payload, claim_lease)
            ):
                return False
            backoff = {
                "state": "backoff",
                "persona_lifecycle_generation": active.lifecycle_generation,
                "source_fingerprint": source,
                "attempt": claim_lease.attempt,
                "next_attempt_at_ms": now + backoff_ms,
            }
            self._write_snapshot_locked(
                self.genesis_path(active),
                expected_generation=snapshot.generation,
                payload=backoff,
            )
            self._release_global_lease_locked(global_state, claim_lease)
            return True

    def release_persona_genesis_lease(
        self,
        lease: PersonaGenesisLease,
        *,
        now_ms: int | None = None,
    ) -> bool:
        """Release only the exact current global lease; stale releases are inert."""

        claim_lease = self._require_genesis_lease(lease)
        now = self._require_genesis_now(now_ms)
        with self._repository_lock():
            global_state, changed = self._read_persona_genesis_global_locked(now_ms=now)
            released = self._release_global_lease_locked(global_state, claim_lease)
            if not released and changed:
                self._write_persona_genesis_global_locked(global_state)
            return released

    def write_genesis(
        self,
        persona_ref: PersonaRevisionRef,
        *,
        expected_lifecycle_generation: int,
        payload: dict[str, object],
        expected_generation: int = 0,
    ) -> int:
        """Legacy seam retained solely to preserve lifecycle-fence diagnostics.

        Genesis records cannot be written generically: a caller must use a
        durable claim followed by ``commit_persona_genesis_activation`` so no
        partial or neutral activation can ever become visible.
        """

        if type(persona_ref) is not PersonaRevisionRef:
            raise ValueError("persona_ref must be a PersonaRevisionRef")
        _require_generation(expected_lifecycle_generation, "expected_lifecycle_generation")
        _require_generation(expected_generation, "expected_generation")
        _require_payload(payload)
        with self._repository_lock():
            self._require_active_persona_locked(
                persona_ref,
                expected_lifecycle_generation=expected_lifecycle_generation,
            )
        raise ValueError("generic persona genesis writes are forbidden")

    def read_genesis(self, persona_ref: PersonaRevisionRef) -> Snapshot | None:
        if type(persona_ref) is not PersonaRevisionRef:
            raise ValueError("persona_ref must be a PersonaRevisionRef")
        with self._repository_lock():
            active = self._require_active_persona_locked(persona_ref)
            snapshot = self._read_genesis_locked(active)
            if snapshot is None or not self._payload_matches_persona(snapshot.payload, active):
                return None
            return snapshot

    @staticmethod
    def _now_ms() -> int:
        return time.time_ns() // 1_000_000


@dataclass(frozen=True, slots=True)
class ScopedPersistenceGateway:
    """Immutable capability for one frozen SessionScope generation."""

    repository: ScopeRepository
    scope: SessionScope

    def __post_init__(self) -> None:
        if not isinstance(self.repository, ScopeRepository):
            raise ValueError("repository must be a ScopeRepository")
        if type(self.scope) is not SessionScope:
            raise ValueError("scope must be a SessionScope")

    def load(self, component: str) -> Snapshot | None:
        return self.repository.read_component(self.scope, component)

    def save(
        self,
        component: str,
        *,
        expected_generation: int,
        payload: dict[str, object],
    ) -> int:
        return self.repository.write_component(
            self.scope,
            component,
            expected_generation=expected_generation,
            payload=payload,
        )

    def purge(self, *, reason: str = "purge") -> SessionScope:
        return self.repository.purge_session(
            self.scope,
            expected_scope_generation=self.scope.scope_generation,
            reason=reason,
        )


@dataclass(frozen=True, slots=True)
class RelationScopedPersistenceGateway:
    """Immutable capability for one frozen RelationScope generation."""

    repository: ScopeRepository
    scope: RelationScope

    def __post_init__(self) -> None:
        if not isinstance(self.repository, ScopeRepository):
            raise ValueError("repository must be a ScopeRepository")
        if type(self.scope) is not RelationScope:
            raise ValueError("scope must be a RelationScope")

    def load(self, component: str) -> Snapshot | None:
        return self.repository.read_relation_component(self.scope, component)

    def save(
        self,
        component: str,
        *,
        expected_generation: int,
        payload: dict[str, object],
    ) -> int:
        return self.repository.write_relation_component(
            self.scope,
            component,
            expected_generation=expected_generation,
            payload=payload,
        )

    def purge(self, *, reason: str = "purge") -> RelationScope:
        return self.repository.purge_relation(
            self.scope,
            expected_relation_generation=self.scope.relation_generation,
            reason=reason,
        )


# The shorter names mirror the Task-6 construction contract while retaining an
# explicit ``Gateway`` spelling for capability-oriented call sites.
ScopedPersistence = ScopedPersistenceGateway
RelationScopedPersistence = RelationScopedPersistenceGateway


__all__ = [
    "PersonaGenesisLease",
    "RelationScopedPersistence",
    "RelationScopedPersistenceGateway",
    "RepositoryCorruptionError",
    "ScopeBotNotFound",
    "ScopeCorrupt",
    "ScopeParentMismatch",
    "ScopePersonaNotFound",
    "ScopeRepository",
    "ScopedPersistence",
    "ScopedPersistenceGateway",
    "Snapshot",
    "StaleScopeWrite",
]
