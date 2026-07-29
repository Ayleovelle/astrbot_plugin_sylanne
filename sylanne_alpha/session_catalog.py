"""Bot-owned, durable transport-session turn catalog."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import stat
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import infra
from .infra import atomic_write_owner_only_bytes
from .scope_contracts import ResolvedTransportScope, SessionScope
from .scope_identity import ScopeIdentityKey, load_or_create_scope_identity_key
from .scope_repository import (
    RepositoryCorruptionError,
    ScopeRepository,
    StaleScopeWrite,
    _canonical_json_bytes,
)

_TRANSPORT_SCHEMA = "sylanne.transport.session.v1"
_DELIVERY_BINDING_SCHEMA = "sylanne.delivery.binding.v1"
_BINDING_DIGEST_DOMAIN = b"sylanne.scope.delivery-binding.v1\x00"


def _require_token(value: object, prefix: str) -> str:
    if type(value) is not str or not value.startswith(prefix) or len(value) == len(prefix):
        raise ValueError(f"invalid {prefix} token")
    return value


def _require_text(value: object, name: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"{name} must be a non-empty exact str")
    return value


def _require_generation(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative int")
    return value


@dataclass(frozen=True, slots=True, repr=False)
class ProtectedDeliveryBinding:
    """Sensitive address material captured from the original adapter boundary."""

    platform_id: str = field(repr=False)
    self_id: str = field(repr=False)
    message_session: str = field(repr=False)
    target_address: str = field(repr=False)
    adapter_capability: str = field(repr=False)
    account_proof_digest: str = field(repr=False)
    account_proof_generation: int
    account_proof_expires_at_ms: int
    binding_generation: int

    def __post_init__(self) -> None:
        _require_text(self.platform_id, "platform_id")
        _require_text(self.self_id, "self_id")
        _require_text(self.message_session, "message_session")
        _require_text(self.target_address, "target_address")
        _require_text(self.adapter_capability, "adapter_capability")
        _require_text(self.account_proof_digest, "account_proof_digest")
        _require_generation(
            self.account_proof_generation,
            "account_proof_generation",
        )
        _require_generation(
            self.account_proof_expires_at_ms,
            "account_proof_expires_at_ms",
        )
        _require_generation(self.binding_generation, "binding_generation")

    def _document(self) -> dict[str, object]:
        return {
            "schema_version": _DELIVERY_BINDING_SCHEMA,
            "platform_id": self.platform_id,
            "self_id": self.self_id,
            "message_session": self.message_session,
            "target_address": self.target_address,
            "adapter_capability": self.adapter_capability,
            "account_proof_digest": self.account_proof_digest,
            "account_proof_generation": self.account_proof_generation,
            "account_proof_expires_at_ms": self.account_proof_expires_at_ms,
            "binding_generation": self.binding_generation,
        }


@dataclass(frozen=True, slots=True)
class TransportTurn:
    """Opaque persisted view of one transport session's current turn."""

    bot_ref: str
    session_ref: str
    session_generation: int
    turn_generation: int
    turn_state: str
    active_persona_ref: str | None
    persona_lifecycle_generation: int | None
    active_scope_token: str | None
    scope_generation: int | None
    binding_digest: str
    identity_quality: str
    updated_at_ms: int

    def __post_init__(self) -> None:
        _require_token(self.bot_ref, "bot_v1_")
        _require_token(self.session_ref, "session_v1_")
        _require_generation(self.session_generation, "session_generation")
        _require_generation(self.turn_generation, "turn_generation")
        _require_text(self.binding_digest, "binding_digest")
        _require_text(self.identity_quality, "identity_quality")
        _require_generation(self.updated_at_ms, "updated_at_ms")
        if self.turn_state == "resolving":
            if any(
                value is not None
                for value in (
                    self.active_persona_ref,
                    self.persona_lifecycle_generation,
                    self.active_scope_token,
                    self.scope_generation,
                )
            ):
                raise ValueError("resolving turn must not carry a frozen scope")
            return
        if self.turn_state != "frozen":
            raise ValueError("turn_state must be resolving or frozen")
        _require_token(self.active_persona_ref, "persona_v1_")
        _require_generation(
            self.persona_lifecycle_generation,
            "persona_lifecycle_generation",
        )
        _require_token(self.active_scope_token, "scope_v1_")
        _require_generation(self.scope_generation, "scope_generation")


SessionCatalogRecord = TransportTurn


class SessionCatalog:
    """Persist monotonic transport turns under the owning Bot namespace."""

    def __init__(
        self,
        repository: ScopeRepository,
        *,
        identity_key: ScopeIdentityKey | None = None,
    ) -> None:
        if type(repository) is not ScopeRepository:
            raise ValueError("repository must be a ScopeRepository")
        if identity_key is not None and type(identity_key) is not ScopeIdentityKey:
            raise ValueError("identity_key must be a ScopeIdentityKey or None")
        self.repository = repository
        self._identity_key = identity_key or load_or_create_scope_identity_key(
            repository.root / "identity.key"
        )

    def _binding_digest(self, document: dict[str, object]) -> str:
        digest = hmac.new(
            self._identity_key.secret,
            _BINDING_DIGEST_DOMAIN + _canonical_json_bytes(document),
            hashlib.sha256,
        ).hexdigest()
        return f"binding-v1-{digest}"

    @staticmethod
    def _turn_document(turn: TransportTurn) -> dict[str, object]:
        return {
            "schema_version": _TRANSPORT_SCHEMA,
            "bot_ref": turn.bot_ref,
            "session_ref": turn.session_ref,
            "session_generation": turn.session_generation,
            "turn_generation": turn.turn_generation,
            "turn_state": turn.turn_state,
            "active_persona_ref": turn.active_persona_ref,
            "persona_lifecycle_generation": turn.persona_lifecycle_generation,
            "active_scope_token": turn.active_scope_token,
            "scope_generation": turn.scope_generation,
            "binding_digest": turn.binding_digest,
            "identity_quality": turn.identity_quality,
            "updated_at_ms": turn.updated_at_ms,
        }

    @staticmethod
    def _turn_from_document(document: dict[str, object]) -> TransportTurn:
        expected = {
            "schema_version",
            "bot_ref",
            "session_ref",
            "session_generation",
            "turn_generation",
            "turn_state",
            "active_persona_ref",
            "persona_lifecycle_generation",
            "active_scope_token",
            "scope_generation",
            "binding_digest",
            "identity_quality",
            "updated_at_ms",
        }
        if set(document) != expected or document["schema_version"] != _TRANSPORT_SCHEMA:
            raise RepositoryCorruptionError("transport catalog has an invalid envelope")
        try:
            return TransportTurn(
                bot_ref=document["bot_ref"],
                session_ref=document["session_ref"],
                session_generation=document["session_generation"],
                turn_generation=document["turn_generation"],
                turn_state=document["turn_state"],
                active_persona_ref=document["active_persona_ref"],
                persona_lifecycle_generation=document[
                    "persona_lifecycle_generation"
                ],
                active_scope_token=document["active_scope_token"],
                scope_generation=document["scope_generation"],
                binding_digest=document["binding_digest"],
                identity_quality=document["identity_quality"],
                updated_at_ms=document["updated_at_ms"],
            )
        except (TypeError, ValueError) as exc:
            raise RepositoryCorruptionError("transport catalog is invalid") from exc

    def _load_turn_locked(
        self,
        bot_token: str,
        session_token: str,
    ) -> TransportTurn | None:
        path = self.repository.transport_catalog_path(bot_token, session_token)
        try:
            loaded = self.repository._read_json(
                path,
                error_label="transport catalog",
            )
            if loaded is None:
                return None
            raw, document = loaded
            if raw != _canonical_json_bytes(document):
                raise RepositoryCorruptionError("transport catalog is not canonical")
            turn = self._turn_from_document(document)
            if turn.bot_ref != bot_token or turn.session_ref != session_token:
                raise RepositoryCorruptionError("transport catalog parent is invalid")
            return turn
        except RepositoryCorruptionError:
            self.repository._quarantine_locked(path)
            raise

    def _write_turn_locked(self, turn: TransportTurn) -> None:
        self.repository._atomic_json_replace(
            self.repository.transport_catalog_path(
                turn.bot_ref,
                turn.session_ref,
            ),
            self._turn_document(turn),
        )
        self.repository._commit_catalog_generation_locked()

    def _write_binding_locked(
        self,
        turn: TransportTurn,
        binding: ProtectedDeliveryBinding,
    ) -> None:
        document = binding._document()
        if self._binding_digest(document) != turn.binding_digest:
            raise RepositoryCorruptionError("delivery binding digest is invalid")
        atomic_write_owner_only_bytes(
            self.repository.transport_delivery_binding_path(
                turn.bot_ref,
                turn.session_ref,
            ),
            _canonical_json_bytes(document),
            error_label="delivery binding",
        )

    def _validate_binding_locked(self, turn: TransportTurn) -> bool:
        path = self.repository.transport_delivery_binding_path(
            turn.bot_ref,
            turn.session_ref,
        )
        try:
            if os.name == "nt":
                infra._validate_windows_path(path, error_label="delivery binding")
            else:
                info = infra._validate_posix_owner_only(
                    path,
                    directory=False,
                    error_label="delivery binding",
                )
                if not stat.S_ISREG(info.st_mode):
                    return False
            raw = path.read_bytes()
            document = json.loads(raw.decode("utf-8"))
            if (
                type(document) is not dict
                or raw != _canonical_json_bytes(document)
                or document.get("schema_version") != _DELIVERY_BINDING_SCHEMA
            ):
                return False
            return hmac.compare_digest(
                self._binding_digest(document),
                turn.binding_digest,
            )
        except (OSError, UnicodeDecodeError, ValueError):
            return False

    def begin_turn(
        self,
        transport_scope: ResolvedTransportScope,
        delivery_binding: ProtectedDeliveryBinding,
    ) -> TransportTurn:
        if type(transport_scope) is not ResolvedTransportScope:
            raise ValueError("transport_scope must be a ResolvedTransportScope")
        if type(delivery_binding) is not ProtectedDeliveryBinding:
            raise ValueError("delivery_binding must be a ProtectedDeliveryBinding")
        if (
            transport_scope.private_scope_enabled is not True
            or transport_scope.disabled_reason is not None
        ):
            raise ValueError("transport scope is not enabled")
        with self.repository.transaction():
            self.repository._ensure_bot_locked(transport_scope.bot_ref)
            current = self._load_turn_locked(
                transport_scope.bot_ref.token,
                transport_scope.session_ref.token,
            )
            if current is not None and (
                current.bot_ref != transport_scope.bot_ref.token
                or current.session_ref != transport_scope.session_ref.token
                or current.session_generation
                != transport_scope.session_ref.generation
            ):
                raise StaleScopeWrite(
                    transport_scope.session_ref.generation,
                    current.session_generation,
                    code="session_generation_stale",
                )
            binding_document = delivery_binding._document()
            turn = TransportTurn(
                bot_ref=transport_scope.bot_ref.token,
                session_ref=transport_scope.session_ref.token,
                session_generation=transport_scope.session_ref.generation,
                turn_generation=(
                    1 if current is None else current.turn_generation + 1
                ),
                turn_state="resolving",
                active_persona_ref=None,
                persona_lifecycle_generation=None,
                active_scope_token=None,
                scope_generation=None,
                binding_digest=self._binding_digest(binding_document),
                identity_quality=transport_scope.identity_quality,
                updated_at_ms=self._now_ms(),
            )
            # Publishing resolving first makes any interrupted update fail closed.
            self._write_turn_locked(turn)
            self._write_binding_locked(turn, delivery_binding)
            return turn

    def freeze_persona(
        self,
        turn: TransportTurn,
        scope: SessionScope,
    ) -> TransportTurn:
        if type(turn) is not TransportTurn:
            raise ValueError("turn must be a TransportTurn")
        if type(scope) is not SessionScope:
            raise ValueError("scope must be a SessionScope")
        with self.repository.transaction():
            current = self._load_turn_locked(turn.bot_ref, turn.session_ref)
            if current != turn or current.turn_state != "resolving":
                raise StaleScopeWrite(
                    turn.turn_generation,
                    None if current is None else current.turn_generation,
                    code="turn_generation_stale",
                )
            active_scope = self.repository._require_active_scope_locked(scope)
            if (
                active_scope.bot_ref.token != turn.bot_ref
                or active_scope.session_ref.token != turn.session_ref
                or active_scope.session_ref.generation != turn.session_generation
                or not self._validate_binding_locked(turn)
            ):
                raise StaleScopeWrite(code="turn_parent_stale")
            frozen = replace(
                turn,
                turn_state="frozen",
                active_persona_ref=active_scope.persona_ref.token,
                persona_lifecycle_generation=(
                    active_scope.persona_ref.lifecycle_generation
                ),
                active_scope_token=active_scope.storage_token,
                scope_generation=active_scope.scope_generation,
                updated_at_ms=self._now_ms(),
            )
            self._write_turn_locked(frozen)
            return frozen

    def current(self, session_ref_token: str) -> TransportTurn:
        token = _require_token(session_ref_token, "session_v1_")
        with self.repository.transaction():
            matches: list[TransportTurn] = []
            if self.repository.bots_directory.is_dir():
                for bot_directory in self.repository.bots_directory.iterdir():
                    if (
                        not bot_directory.is_dir()
                        or not bot_directory.name.startswith("bot_v1_")
                    ):
                        continue
                    path = self.repository.transport_catalog_path(
                        bot_directory.name,
                        token,
                    )
                    if not path.exists():
                        continue
                    turn = self._load_turn_locked(bot_directory.name, token)
                    if turn is not None:
                        matches.append(turn)
            if not matches:
                raise KeyError("transport session not found")
            if len(matches) != 1:
                raise RepositoryCorruptionError(
                    "transport session ownership is ambiguous"
                )
            return matches[0]

    def can_issue_proactive(self, turn: TransportTurn) -> bool:
        if type(turn) is not TransportTurn:
            return False
        try:
            current = self.current(turn.session_ref)
            if current != turn or current.turn_state != "frozen":
                return False
            with self.repository.transaction():
                return self._validate_binding_locked(current)
        except (KeyError, RepositoryCorruptionError, StaleScopeWrite, ValueError):
            return False

    @staticmethod
    def _now_ms() -> int:
        return time.time_ns() // 1_000_000


__all__ = [
    "ProtectedDeliveryBinding",
    "SessionCatalog",
    "SessionCatalogRecord",
    "TransportTurn",
]
