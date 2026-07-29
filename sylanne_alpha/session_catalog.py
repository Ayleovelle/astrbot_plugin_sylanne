"""Bot-owned, durable transport-session turn catalog."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

from . import infra
from .infra import atomic_write_owner_only_bytes
from .scope_contracts import ResolvedTransportScope, SessionScope
from .scope_identity import (
    BotBinding,
    ScopeIdentityKey,
    load_or_create_scope_identity_key,
)
from .scope_repository import (
    RepositoryCorruptionError,
    ScopeRepository,
    StaleScopeWrite,
    _canonical_json_bytes,
)

_TRANSPORT_SCHEMA = "sylanne.transport.session.v1"
_DELIVERY_BINDING_SCHEMA = "sylanne.delivery.binding.v1"
_BOT_BINDING_SCHEMA = "sylanne.bot.binding.v1"
_BINDING_DIGEST_DOMAIN = b"sylanne.scope.delivery-binding.v1\x00"
_BOT_BINDING_TOKEN_DOMAIN = b"sylanne.scope.bot-binding-token.v1\x00"
_TOKEN_PAYLOAD = re.compile(r"[A-Za-z0-9_-]+\Z", re.ASCII)


def _require_token(value: object, prefix: str) -> str:
    if (
        type(value) is not str
        or not value.startswith(prefix)
        or _TOKEN_PAYLOAD.fullmatch(value[len(prefix) :]) is None
    ):
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
        if type(self.self_id) is not str:
            raise ValueError("self_id must be an exact str")
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

    def _bot_binding_token(self, platform_id: str, self_id: str) -> str:
        material = _canonical_json_bytes(
            {
                "platform_id": _require_text(platform_id, "platform_id"),
                "self_id": _require_text(self_id, "self_id"),
            }
        )
        digest = hmac.new(
            self._identity_key.secret,
            _BOT_BINDING_TOKEN_DOMAIN + material,
            hashlib.sha256,
        ).hexdigest()
        return f"binding_v1_{digest}"

    def _load_bot_binding_locked(
        self,
        binding_token: str,
    ) -> tuple[int, str] | None:
        token = _require_token(binding_token, "binding_v1_")
        loaded = self.repository._read_json(
            self.repository.bot_binding_manifest_path(token),
            error_label="bot binding authority",
        )
        if loaded is None:
            return None
        raw, document = loaded
        expected_fields = {
            "schema_version",
            "binding_token",
            "bot_ref",
            "binding_generation",
            "updated_at_ms",
        }
        if (
            set(document) != expected_fields
            or document["schema_version"] != _BOT_BINDING_SCHEMA
            or document["binding_token"] != token
            or raw != _canonical_json_bytes(document)
        ):
            raise RepositoryCorruptionError("bot binding authority is invalid")
        try:
            bot_token = _require_token(document["bot_ref"], "bot_v1_")
            generation = _require_generation(
                document["binding_generation"],
                "binding_generation",
            )
            _require_generation(document["updated_at_ms"], "updated_at_ms")
        except ValueError as exc:
            raise RepositoryCorruptionError(
                "bot binding authority is invalid"
            ) from exc
        return generation, bot_token

    def _write_bot_binding_locked(
        self,
        binding_token: str,
        *,
        bot_token: str,
        generation: int,
    ) -> None:
        token = _require_token(binding_token, "binding_v1_")
        self.repository._atomic_json_replace(
            self.repository.bot_binding_manifest_path(token),
            {
                "schema_version": _BOT_BINDING_SCHEMA,
                "binding_token": token,
                "bot_ref": _require_token(bot_token, "bot_v1_"),
                "binding_generation": _require_generation(
                    generation,
                    "binding_generation",
                ),
                "updated_at_ms": self._now_ms(),
            },
            owner_only=True,
        )
        self.repository._commit_catalog_generation_locked()

    def binding_generation(self, platform_id: str, self_id: str) -> int:
        """Return the durable generation for one proven non-empty bot binding."""

        binding = BotBinding(
            platform_id=_require_text(platform_id, "platform_id"),
            self_id=_require_text(self_id, "self_id"),
        )
        binding_token = self._bot_binding_token(
            binding.platform_id,
            binding.self_id,
        )
        with self.repository.transaction():
            authority = self._load_bot_binding_locked(binding_token)
            if authority is None:
                generation = 0
                expected_bot = self._identity_key.bot_ref(binding, generation)
                self.repository._ensure_bot_locked(expected_bot)
                self._write_bot_binding_locked(
                    binding_token,
                    bot_token=expected_bot.token,
                    generation=generation,
                )
                return generation
            generation, stored_bot_token = authority
            expected_bot = self._identity_key.bot_ref(binding, generation)
            if not hmac.compare_digest(stored_bot_token, expected_bot.token):
                raise RepositoryCorruptionError(
                    "bot binding authority does not match identity key"
                )
            self.repository._ensure_bot_locked(expected_bot)
            return generation

    def binding_generation_candidate(self, platform_id: str, self_id: str) -> int:
        """Return the current generation without creating binding authority."""

        binding = BotBinding(
            platform_id=_require_text(platform_id, "platform_id"),
            self_id=_require_text(self_id, "self_id"),
        )
        binding_token = self._bot_binding_token(
            binding.platform_id,
            binding.self_id,
        )
        with self.repository.transaction():
            authority = self._load_bot_binding_locked(binding_token)
            if authority is None:
                return 0
            generation, stored_bot_token = authority
            expected_bot = self._identity_key.bot_ref(binding, generation)
            if not hmac.compare_digest(stored_bot_token, expected_bot.token):
                raise RepositoryCorruptionError(
                    "bot binding authority does not match identity key"
                )
            return generation

    def _binding_generation_for_bot_ref_locked(self, bot_ref: object) -> int | None:
        """Return one persisted binding authority for a proof-derived BotRef.

        A proof never creates authority: a missing, malformed, or ambiguous
        manifest is indistinguishable from an unverified account to callers.
        """

        from .scope_contracts import BotRef

        if type(bot_ref) is not BotRef:
            return None
        directory = self.repository.bot_bindings_directory
        if not directory.is_dir():
            return None
        matches: list[int] = []
        try:
            entries = tuple(directory.iterdir())
        except OSError:
            return None
        for entry in entries:
            if not entry.is_dir() or not entry.name.startswith("binding_v1_"):
                continue
            try:
                authority = self._load_bot_binding_locked(entry.name)
            except (RepositoryCorruptionError, ValueError, OSError):
                return None
            if authority is None:
                continue
            generation, stored_bot_token = authority
            if (
                generation == bot_ref.generation
                and hmac.compare_digest(stored_bot_token, bot_ref.token)
            ):
                matches.append(generation)
        return matches[0] if len(matches) == 1 else None

    def binding_generation_for_bot_ref(self, bot_ref: object) -> int | None:
        """Find only an already-persisted unique authority for ``bot_ref``."""

        with self.repository.transaction():
            return self._binding_generation_for_bot_ref_locked(bot_ref)

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

    def _load_binding_locked(
        self,
        turn: TransportTurn,
    ) -> ProtectedDeliveryBinding | None:
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
                or set(document)
                != {
                    "schema_version",
                    "platform_id",
                    "self_id",
                    "message_session",
                    "target_address",
                    "adapter_capability",
                    "account_proof_digest",
                    "account_proof_generation",
                    "account_proof_expires_at_ms",
                    "binding_generation",
                }
            ):
                return None
            binding = ProtectedDeliveryBinding(
                platform_id=document["platform_id"],
                self_id=document["self_id"],
                message_session=document["message_session"],
                target_address=document["target_address"],
                adapter_capability=document["adapter_capability"],
                account_proof_digest=document["account_proof_digest"],
                account_proof_generation=document[
                    "account_proof_generation"
                ],
                account_proof_expires_at_ms=document[
                    "account_proof_expires_at_ms"
                ],
                binding_generation=document["binding_generation"],
            )
            if (
                binding._document() != document
                or not hmac.compare_digest(
                    self._binding_digest(document),
                    turn.binding_digest,
                )
            ):
                return None
            return binding
        except (KeyError, OSError, TypeError, UnicodeDecodeError, ValueError):
            return None

    def _validate_binding_locked(self, turn: TransportTurn) -> bool:
        if self._load_binding_locked(turn) is None:
            return False
        return True

    def begin_turn(
        self,
        transport_scope: ResolvedTransportScope,
        delivery_binding: ProtectedDeliveryBinding,
        *,
        publish: Callable[[TransportTurn], bool] | None = None,
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
            create_binding_authority = False
            stored_bot_token: str | None
            if delivery_binding.self_id:
                binding = BotBinding(
                    platform_id=delivery_binding.platform_id,
                    self_id=delivery_binding.self_id,
                )
                binding_token = self._bot_binding_token(
                    binding.platform_id,
                    binding.self_id,
                )
                authority = self._load_bot_binding_locked(binding_token)
                if authority is None:
                    if publish is None:
                        raise ValueError("bot binding authority is missing")
                    binding_generation = 0
                    stored_bot_token = None
                    create_binding_authority = True
                else:
                    binding_generation, stored_bot_token = authority
                expected_bot = self._identity_key.bot_ref(
                    binding,
                    binding_generation,
                )
            else:
                if transport_scope.bot_ref is None:
                    raise ValueError("bot binding authority is missing")
                binding_generation = self._binding_generation_for_bot_ref_locked(
                    transport_scope.bot_ref
                )
                if binding_generation is None:
                    raise ValueError("bot binding authority is missing or ambiguous")
                stored_bot_token = transport_scope.bot_ref.token
                expected_bot = transport_scope.bot_ref
            if delivery_binding.binding_generation != binding_generation:
                raise ValueError("binding generation is stale")
            if (
                expected_bot != transport_scope.bot_ref
                or (
                    stored_bot_token is not None
                    and not hmac.compare_digest(
                        stored_bot_token,
                        expected_bot.token,
                    )
                )
            ):
                raise ValueError("bot binding does not match transport scope")
            current = self._load_turn_locked(
                transport_scope.bot_ref.token,
                transport_scope.session_ref.token,
            )
            if create_binding_authority and current is not None:
                raise RepositoryCorruptionError(
                    "transport turn exists without bot binding authority"
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
            if publish is not None:
                try:
                    published = publish(turn)
                except Exception as exc:
                    raise ValueError("transport turn publication failed") from exc
                if published is not True:
                    raise ValueError("transport turn publication failed")
            # The exact event objects are published before either durable turn
            # artifact, so an attachment failure cannot strand a resolving turn.
            self.repository._ensure_bot_locked(expected_bot)
            if create_binding_authority:
                self._write_bot_binding_locked(
                    binding_token,
                    bot_token=expected_bot.token,
                    generation=binding_generation,
                )
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

    def freeze_persona_published(
        self,
        turn: TransportTurn,
        candidate_scope: SessionScope,
        *,
        publish: Callable[[SessionScope, TransportTurn], bool],
    ) -> tuple[SessionScope, TransportTurn]:
        """Publish exact prospective objects before committing scope and freeze."""

        if type(turn) is not TransportTurn:
            raise ValueError("turn must be a TransportTurn")
        if type(candidate_scope) is not SessionScope:
            raise ValueError("candidate_scope must be a SessionScope")
        if not callable(publish):
            raise ValueError("publish must be callable")
        with self.repository.transaction():
            current = self._load_turn_locked(turn.bot_ref, turn.session_ref)
            if current != turn or current.turn_state != "resolving":
                raise StaleScopeWrite(
                    turn.turn_generation,
                    None if current is None else current.turn_generation,
                    code="turn_generation_stale",
                )
            prepared = self.repository._prepare_scope_locked(candidate_scope)
            if (
                prepared.bot_ref.token != turn.bot_ref
                or prepared.session_ref.token != turn.session_ref
                or prepared.session_ref.generation != turn.session_generation
                or not self._validate_binding_locked(turn)
            ):
                raise StaleScopeWrite(code="turn_parent_stale")
            frozen = replace(
                turn,
                turn_state="frozen",
                active_persona_ref=prepared.persona_ref.token,
                persona_lifecycle_generation=(
                    prepared.persona_ref.lifecycle_generation
                ),
                active_scope_token=prepared.storage_token,
                scope_generation=prepared.scope_generation,
                updated_at_ms=self._now_ms(),
            )
            try:
                published = publish(prepared, frozen)
            except Exception as exc:
                raise ValueError("resolved scope publication failed") from exc
            if published is not True:
                raise ValueError("resolved scope publication failed")
            committed = self.repository._create_scope_locked(candidate_scope)
            if committed != prepared:
                raise RepositoryCorruptionError(
                    "prepared scope changed during freeze commit"
                )
            self._write_turn_locked(frozen)
            return committed, frozen

    def matches_frozen_scope(
        self,
        transport_scope: ResolvedTransportScope,
        turn: object,
        scope: SessionScope,
        *,
        turn_generation: int,
    ) -> bool:
        """Read-only exact-match check for one already-published frozen scope."""

        if (
            type(transport_scope) is not ResolvedTransportScope
            or type(turn) is not TransportTurn
            or type(scope) is not SessionScope
            or type(turn_generation) is not int
        ):
            return False
        try:
            with self.repository.transaction():
                current = self._load_turn_locked(turn.bot_ref, turn.session_ref)
                active_scope = self.repository._require_active_scope_locked(scope)
                return (
                    transport_scope.private_scope_enabled is True
                    and transport_scope.bot_ref == scope.bot_ref
                    and transport_scope.session_ref == scope.session_ref
                    and transport_scope.identity_quality == turn.identity_quality
                    and current == turn
                    and turn.turn_state == "frozen"
                    and turn.turn_generation == turn_generation
                    and turn.bot_ref == scope.bot_ref.token
                    and turn.session_ref == scope.session_ref.token
                    and turn.session_generation == scope.session_ref.generation
                    and turn.active_persona_ref == scope.persona_ref.token
                    and turn.persona_lifecycle_generation
                    == scope.persona_ref.lifecycle_generation
                    and turn.active_scope_token == scope.storage_token
                    and turn.scope_generation == scope.scope_generation
                    and active_scope == scope
                    and self._validate_binding_locked(turn)
                )
        except Exception:
            return False

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

    def can_issue_proactive(
        self,
        turn: TransportTurn,
        *,
        current_account_proof_digest: str | None = None,
        current_account_proof_generation: int | None = None,
        now_ms: int | None = None,
    ) -> bool:
        if (
            type(turn) is not TransportTurn
            or type(current_account_proof_digest) is not str
            or not current_account_proof_digest
            or type(current_account_proof_generation) is not int
            or current_account_proof_generation < 0
            or type(now_ms) is not int
            or now_ms < 0
        ):
            return False
        try:
            with self.repository.transaction():
                current = self._load_turn_locked(
                    turn.bot_ref,
                    turn.session_ref,
                )
                if (
                    current != turn
                    or current is None
                    or current.turn_state != "frozen"
                    or current.active_scope_token is None
                ):
                    return False
                active_scope = self.repository._resolve_scope_locked(
                    current.active_scope_token
                )
                if (
                    active_scope.bot_ref.token != current.bot_ref
                    or active_scope.persona_ref.token
                    != current.active_persona_ref
                    or active_scope.session_ref.token != current.session_ref
                    or active_scope.persona_ref.lifecycle_generation
                    != current.persona_lifecycle_generation
                    or active_scope.session_ref.generation
                    != current.session_generation
                    or active_scope.storage_token
                    != current.active_scope_token
                    or active_scope.scope_generation
                    != current.scope_generation
                ):
                    return False
                binding = self._load_binding_locked(current)
                if (
                    binding is None
                    or not hmac.compare_digest(
                        binding.account_proof_digest,
                        current_account_proof_digest,
                    )
                    or binding.account_proof_generation
                    != current_account_proof_generation
                    or now_ms >= binding.account_proof_expires_at_ms
                ):
                    return False
                binding_token = self._bot_binding_token(
                    binding.platform_id,
                    binding.self_id,
                )
                authority = self._load_bot_binding_locked(binding_token)
                if authority is None:
                    return False
                binding_generation, stored_bot_token = authority
                expected_bot = self._identity_key.bot_ref(
                    BotBinding(
                        platform_id=binding.platform_id,
                        self_id=binding.self_id,
                    ),
                    binding_generation,
                )
                return (
                    binding.binding_generation == binding_generation
                    and expected_bot == active_scope.bot_ref
                    and hmac.compare_digest(
                        stored_bot_token,
                        current.bot_ref,
                    )
                )
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
