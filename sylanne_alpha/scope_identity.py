"""HMAC-derived opaque identities for isolated multibot scope namespaces."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .infra import load_or_create_owner_only_secret
from .scope_contracts import (
    BotRef,
    PersonaRevisionRef,
    RelationRef,
    ResolvedScope,
    ResolvedTransportScope,
    SessionRef,
    SessionScope,
)

_BOT_DOMAIN = b"sylanne.scope.bot.v1\x00"
_PERSONA_DOMAIN = b"sylanne.scope.persona.v1\x00"
_SESSION_DOMAIN = b"sylanne.scope.session.v1\x00"
_RELATION_DOMAIN = b"sylanne.scope.relation.v1\x00"
_STORAGE_DOMAIN = b"sylanne.scope.storage.v1\x00"
_MANAGED_EMBODIMENT_PREFIX = "sylanne_embodiment_"
_MAX_IDENTITY_COMPONENT_BYTES = 4096
_SCOPE_KEY_MAGIC = b"SYLANNE-SCOPE-IDENTITY\x01\x00"
_SCOPE_KEY_ID_DOMAIN = b"sylanne.scope.key-id.v1\x00"
_SCOPE_SECRET_BYTES = 32


def _token(prefix: str, digest: bytes) -> str:
    """Encode a digest in an opaque, URL-safe, unpadded token namespace."""

    if type(prefix) is not str or type(digest) is not bytes:
        raise ValueError("invalid token input")
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return f"{prefix}{encoded}"


def _frame(value: str) -> bytes:
    """Return a bounded, unambiguous frame for one raw identity component."""

    if type(value) is not str:
        raise ValueError("invalid identity component")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError("invalid identity component") from exc
    if not encoded or len(encoded) > _MAX_IDENTITY_COMPONENT_BYTES:
        raise ValueError("invalid identity component")
    return len(encoded).to_bytes(4, "big") + encoded


def _require_nonnegative_int(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative int")
    return value


def _require_text(value: object, name: str) -> str:
    if type(value) is not str:
        raise ValueError(f"{name} must be an exact str")
    return value


def _require_optional_tuple_text(value: object, name: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    return _require_tuple_text(value, name)


def _require_tuple_text(value: object, name: str) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise ValueError(f"{name} must be an exact tuple")
    for item in value:
        _require_text(item, name)
    return value


@dataclass(frozen=True, slots=True, repr=False)
class BotBinding:
    platform_id: str
    self_id: str

    def __post_init__(self) -> None:
        _frame(self.platform_id)
        _frame(self.self_id)


@dataclass(frozen=True, slots=True, repr=False)
class PersonaSource:
    persona_id: str
    prompt: str
    begin_dialogs: tuple[str, ...]
    tools: tuple[str, ...] | None
    skills: tuple[str, ...] | None
    resolution_source: str

    def __post_init__(self) -> None:
        _require_text(self.persona_id, "persona_id")
        _require_text(self.prompt, "prompt")
        _require_tuple_text(self.begin_dialogs, "begin_dialogs")
        _require_optional_tuple_text(self.tools, "tools")
        _require_optional_tuple_text(self.skills, "skills")
        _require_text(self.resolution_source, "resolution_source")

    def canonical_bytes(self) -> bytes:
        """Return the stable source representation used to fingerprint a revision."""

        payload = {
            "begin_dialogs": list(self.begin_dialogs),
            "persona_id": self.persona_id,
            "prompt": self.prompt,
            "resolution_source": self.resolution_source,
            "skills": None if self.skills is None else sorted(self.skills),
            "tools": None if self.tools is None else sorted(self.tools),
        }
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class ScopeIdentityKey:
    key_id: str
    secret: bytes = field(repr=False)

    def __post_init__(self) -> None:
        _frame(self.key_id)
        if type(self.secret) is not bytes or len(self.secret) != _SCOPE_SECRET_BYTES:
            raise ValueError("secret must be exact bytes with length 32")

    def _digest(self, domain: bytes, *values: str) -> bytes:
        if type(domain) is not bytes:
            raise ValueError("invalid identity domain")
        payload = domain + _frame(self.key_id) + b"".join(_frame(value) for value in values)
        return hmac.new(self.secret, payload, hashlib.sha256).digest()

    def bot_ref(self, binding: BotBinding, generation: int) -> BotRef:
        if type(binding) is not BotBinding:
            raise ValueError("binding must be a BotBinding")
        _require_nonnegative_int(generation, "generation")
        return BotRef(
            token=_token(
                "bot_v1_",
                self._digest(
                    _BOT_DOMAIN,
                    binding.platform_id,
                    binding.self_id,
                    str(generation),
                ),
            ),
            generation=generation,
        )

    def persona_revision(
        self,
        bot_ref: BotRef,
        source: PersonaSource,
        lifecycle_generation: int,
    ) -> PersonaRevisionRef:
        if type(bot_ref) is not BotRef:
            raise ValueError("bot_ref must be a BotRef")
        if type(source) is not PersonaSource:
            raise ValueError("source must be a PersonaSource")
        if source.persona_id.startswith(_MANAGED_EMBODIMENT_PREFIX):
            raise ValueError("managed embodiment persona is forbidden")
        _require_nonnegative_int(lifecycle_generation, "lifecycle_generation")
        source_fingerprint = hashlib.sha256(source.canonical_bytes()).hexdigest()
        persona_id_digest = hashlib.sha256(source.persona_id.encode("utf-8")).hexdigest()
        return PersonaRevisionRef(
            token=_token(
                "persona_v1_",
                self._digest(
                    _PERSONA_DOMAIN,
                    bot_ref.token,
                    persona_id_digest,
                    source_fingerprint,
                ),
            ),
            bot_ref=bot_ref,
            persona_id_digest=persona_id_digest,
            source_fingerprint=source_fingerprint,
            lifecycle_generation=lifecycle_generation,
        )

    def session_ref(
        self,
        bot_ref: BotRef,
        platform_id: str,
        canonical_umo: str,
        generation: int,
    ) -> SessionRef:
        if type(bot_ref) is not BotRef:
            raise ValueError("bot_ref must be a BotRef")
        _require_nonnegative_int(generation, "generation")
        return SessionRef(
            token=_token(
                "session_v1_",
                self._digest(
                    _SESSION_DOMAIN,
                    bot_ref.token,
                    platform_id,
                    canonical_umo,
                    str(generation),
                ),
            ),
            bot_ref=bot_ref,
            generation=generation,
        )

    def scope_token(
        self,
        bot_ref: BotRef,
        persona_ref: PersonaRevisionRef,
        session_ref: SessionRef,
    ) -> str:
        if (
            type(bot_ref) is not BotRef
            or type(persona_ref) is not PersonaRevisionRef
            or type(session_ref) is not SessionRef
            or persona_ref.bot_ref != bot_ref
            or session_ref.bot_ref != bot_ref
        ):
            raise ValueError("scope parent mismatch")
        return _token(
            "scope_v1_",
            self._digest(
                _STORAGE_DOMAIN,
                bot_ref.token,
                persona_ref.token,
                session_ref.token,
            ),
        )

    def relation_ref(
        self,
        bot_ref: BotRef,
        platform_realm: str,
        subject_kind: str,
        authenticated_subject_id: str,
    ) -> RelationRef:
        if type(bot_ref) is not BotRef:
            raise ValueError("bot_ref must be a BotRef")
        return RelationRef(
            token=_token(
                "relation_v1_",
                self._digest(
                    _RELATION_DOMAIN,
                    bot_ref.token,
                    platform_realm,
                    subject_kind,
                    authenticated_subject_id,
                ),
            ),
            bot_ref=bot_ref,
        )


def load_or_create_scope_identity_key(
    path: str | os.PathLike[str],
) -> ScopeIdentityKey:
    """Load the stable scope HMAC key or create it once with owner-only access."""

    secret = load_or_create_owner_only_secret(
        path,
        magic=_SCOPE_KEY_MAGIC,
        secret_bytes=_SCOPE_SECRET_BYTES,
        error_label="scope identity key",
    )
    digest = hashlib.sha256(_SCOPE_KEY_ID_DOMAIN + secret).hexdigest()
    return ScopeIdentityKey(key_id=f"scope-key-v1-{digest[:32]}", secret=secret)


@dataclass(frozen=True, slots=True)
class AdapterAccountProof:
    platform_id: str = field(repr=False)
    bot_ref: BotRef
    proof_generation: int
    verified_at_ms: int
    expires_at_ms: int
    account_set_digest: str
    account_count: int

    def __post_init__(self) -> None:
        _frame(self.platform_id)
        if type(self.bot_ref) is not BotRef:
            raise ValueError("bot_ref must be a BotRef")
        _require_nonnegative_int(self.proof_generation, "proof_generation")
        _require_nonnegative_int(self.verified_at_ms, "verified_at_ms")
        _require_nonnegative_int(self.expires_at_ms, "expires_at_ms")
        _frame(self.account_set_digest)
        _require_nonnegative_int(self.account_count, "account_count")


@dataclass(frozen=True, slots=True)
class CurrentAdapterAccountProof:
    proof: AdapterAccountProof
    current_account_set_digest: str
    current_proof_generation: int

    def __post_init__(self) -> None:
        if type(self.proof) is not AdapterAccountProof:
            raise ValueError("proof must be an AdapterAccountProof")
        _frame(self.current_account_set_digest)
        _require_nonnegative_int(self.current_proof_generation, "current_proof_generation")


class AdapterAccountProofProvider(Protocol):
    def current(self, platform_id: str) -> CurrentAdapterAccountProof | None: ...


class NoAdapterAccountProofProvider:
    """Fail-closed production default until an adapter exposes current account proof."""

    def current(self, platform_id: str) -> CurrentAdapterAccountProof | None:
        return None


def resolve_proven_single_account(
    proof: AdapterAccountProof | None,
    *,
    platform_id: str,
    current_account_set_digest: str,
    current_proof_generation: int,
    now_ms: int,
) -> BotRef | None:
    """Return only a live adapter-proven single account; otherwise fail closed."""

    if (
        type(proof) is not AdapterAccountProof
        or type(platform_id) is not str
        or type(current_account_set_digest) is not str
        or type(current_proof_generation) is not int
        or type(now_ms) is not int
    ):
        return None
    if current_proof_generation < 0 or now_ms < 0:
        return None
    if (
        proof.platform_id != platform_id
        or proof.account_count != 1
        or proof.proof_generation != current_proof_generation
        or proof.account_set_digest != current_account_set_digest
        or proof.verified_at_ms > now_ms
        or now_ms >= proof.expires_at_ms
    ):
        return None
    return proof.bot_ref


class ScopeResolver:
    """Resolve AstrBot's applied Persona and freeze it beneath one transport turn."""

    def __init__(
        self,
        context: Any,
        *,
        repository: Any,
        catalog: Any,
        identity: ScopeIdentityKey,
        account_proofs: AdapterAccountProofProvider | None = None,
        clock_ms: Any = None,
        allow_test_synthetic_turn: bool = False,
    ) -> None:
        self._context = context
        self._repository = repository
        self._catalog = catalog
        self._identity = identity
        self._account_proofs = account_proofs or NoAdapterAccountProofProvider()
        self._clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)
        self._allow_test_synthetic_turn = allow_test_synthetic_turn

    @classmethod
    def for_context(
        cls,
        context: Any,
        root: str | os.PathLike[str],
        *,
        account_proofs: AdapterAccountProofProvider | None = None,
    ) -> ScopeResolver:
        """Create the durable production resolver for one plugin instance."""

        from .scope_repository import ScopeRepository
        from .session_catalog import SessionCatalog

        repository = ScopeRepository(root)
        identity = load_or_create_scope_identity_key(repository.root / "identity.key")
        return cls(
            context,
            repository=repository,
            catalog=SessionCatalog(repository, identity_key=identity),
            identity=identity,
            account_proofs=account_proofs,
        )

    @classmethod
    def for_test(
        cls,
        context: Any,
        *,
        account_proofs: AdapterAccountProofProvider | None = None,
        root: str | os.PathLike[str] | None = None,
    ) -> ScopeResolver:
        """Construct an isolated resolver; production code never uses this helper."""

        test_root = Path(root) if root is not None else Path(
            tempfile.mkdtemp(prefix="sylanne-scope-")
        )
        resolver = cls.for_context(context, test_root, account_proofs=account_proofs)
        resolver._allow_test_synthetic_turn = True
        return resolver

    @property
    def catalog(self) -> Any:
        return self._catalog

    @staticmethod
    def _event_extra(event: Any, key: str, default: Any = None) -> Any:
        getter = getattr(event, "get_extra", None)
        if not callable(getter):
            return default
        try:
            return getter(key, default)
        except TypeError:
            try:
                value = getter(key)
            except Exception:
                return default
            return default if value is None else value
        except Exception:
            return default

    @staticmethod
    def set_event_extra(event: Any, key: str, value: Any) -> bool:
        setter = getattr(event, "set_extra", None)
        if not callable(setter):
            return False
        try:
            setter(key, value)
        except Exception:
            return False
        return True

    def resolve_transport(self, event: Any) -> ResolvedTransportScope:
        """Use only the adapter event's current canonical session and identity."""

        try:
            platform_id = str(event.get_platform_id() or "")
            session = getattr(event, "session", None)
            canonical_umo = str(session) if session is not None else ""
            session_platform_id = str(getattr(session, "platform_id", "") or "")
        except Exception:
            return ResolvedTransportScope.disabled("transport_session_unverified")
        if not platform_id or not canonical_umo:
            return ResolvedTransportScope.disabled("transport_session_unverified")
        if session_platform_id != platform_id:
            return ResolvedTransportScope.disabled("umo_platform_conflict")
        try:
            self_id = str(event.get_self_id() or "")
        except Exception:
            self_id = ""
        try:
            if self_id:
                generation = self._catalog.binding_generation(platform_id, self_id)
                bot_ref = self._identity.bot_ref(
                    BotBinding(platform_id=platform_id, self_id=self_id), generation
                )
                identity_quality = "event_self_id"
            else:
                current_proof = self._account_proofs.current(platform_id)
                if current_proof is None:
                    return ResolvedTransportScope.disabled("bot_identity_unverified")
                bot_ref = resolve_proven_single_account(
                    current_proof.proof,
                    platform_id=platform_id,
                    current_account_set_digest=current_proof.current_account_set_digest,
                    current_proof_generation=current_proof.current_proof_generation,
                    now_ms=int(self._clock_ms()),
                )
                if (
                    bot_ref is None
                    or self._catalog.binding_generation_for_bot_ref(bot_ref) is None
                ):
                    return ResolvedTransportScope.disabled("bot_identity_unverified")
                identity_quality = "single_account_proven"
            session_ref = self._identity.session_ref(
                bot_ref, platform_id, canonical_umo, generation=0
            )
            return ResolvedTransportScope(
                bot_ref=bot_ref,
                session_ref=session_ref,
                identity_quality=identity_quality,
                private_scope_enabled=True,
                disabled_reason=None,
            )
        except Exception:
            return ResolvedTransportScope.disabled("bot_identity_unverified")

    def delivery_binding(self, event: Any, transport: ResolvedTransportScope) -> Any | None:
        """Capture one protected binding from this exact live adapter event."""

        from .session_catalog import ProtectedDeliveryBinding

        if (
            type(transport) is not ResolvedTransportScope
            or transport.private_scope_enabled is not True
            or transport.bot_ref is None
            or transport.session_ref is None
        ):
            return None
        try:
            platform_id = str(event.get_platform_id() or "")
            self_id = str(event.get_self_id() or "")
            session = getattr(event, "session", None)
            canonical_umo = str(session) if session is not None else ""
            if (
                not platform_id
                or not canonical_umo
                or str(getattr(session, "platform_id", "") or "") != platform_id
                or self._identity.session_ref(
                    transport.bot_ref, platform_id, canonical_umo, generation=0
                )
                != transport.session_ref
            ):
                return None
            proof_digest = "proof-unavailable"
            proof_generation = 0
            proof_expires_at_ms = 0
            if not self_id:
                current = self._account_proofs.current(platform_id)
                if current is None:
                    return None
                proven = resolve_proven_single_account(
                    current.proof,
                    platform_id=platform_id,
                    current_account_set_digest=current.current_account_set_digest,
                    current_proof_generation=current.current_proof_generation,
                    now_ms=int(self._clock_ms()),
                )
                if proven != transport.bot_ref:
                    return None
                proof_digest = current.current_account_set_digest
                proof_generation = current.current_proof_generation
                proof_expires_at_ms = current.proof.expires_at_ms
            else:
                current = self._account_proofs.current(platform_id)
                if current is not None:
                    proof_digest = current.current_account_set_digest
                    proof_generation = current.current_proof_generation
                    proof_expires_at_ms = current.proof.expires_at_ms
            return ProtectedDeliveryBinding(
                platform_id=platform_id,
                self_id=self_id,
                message_session=canonical_umo,
                target_address=canonical_umo,
                adapter_capability="reactive_only",
                account_proof_digest=proof_digest,
                account_proof_generation=proof_generation,
                account_proof_expires_at_ms=proof_expires_at_ms,
                binding_generation=transport.bot_ref.generation,
            )
        except Exception:
            return None

    @staticmethod
    def _persona_source(
        selected_id: Any,
        personality: Any,
        *,
        resolution_source: str,
    ) -> PersonaSource | None:
        if (
            type(selected_id) is not str
            or selected_id in {"[%None]", "_chatui_default_"}
            or personality is None
            or type(personality) is not dict
        ):
            return None
        try:
            def as_tuple(value: Any, *, optional: bool) -> tuple[str, ...] | None:
                if value is None and optional:
                    return None
                if type(value) not in (list, tuple):
                    raise ValueError
                result = tuple(value)
                if any(type(item) is not str for item in result):
                    raise ValueError
                return result

            return PersonaSource(
                persona_id=selected_id,
                prompt=personality["prompt"],
                begin_dialogs=as_tuple(personality.get("begin_dialogs", []), optional=False) or (),
                tools=as_tuple(personality.get("tools"), optional=True),
                skills=as_tuple(personality.get("skills"), optional=True),
                resolution_source=resolution_source,
            )
        except (KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def _resolution_source(request: Any, forced_id: Any) -> str:
        if forced_id is not None:
            return "forced"
        conversation = getattr(request, "conversation", None)
        if getattr(conversation, "persona_id", None) is not None:
            return "conversation"
        return "default"

    def _scope_for(
        self,
        transport: ResolvedTransportScope,
        source: PersonaSource,
        *,
        platform_id: str,
        canonical_umo: str,
    ) -> SessionScope:
        assert transport.bot_ref is not None
        assert transport.session_ref is not None
        candidate = self._identity.persona_revision(
            transport.bot_ref, source, lifecycle_generation=0
        )
        persona_ref = self._repository.activate_persona_revision(candidate)
        session_ref = self._identity.session_ref(
            transport.bot_ref, platform_id, canonical_umo, generation=0
        )
        candidate_scope = SessionScope(
            bot_ref=transport.bot_ref,
            persona_ref=persona_ref,
            session_ref=session_ref,
            storage_token=self._identity.scope_token(
                transport.bot_ref, persona_ref, session_ref
            ),
            scope_generation=0,
        )
        return self._repository.create_scope(candidate_scope)

    def _test_turn(self, event: Any, transport: ResolvedTransportScope) -> Any | None:
        if not self._allow_test_synthetic_turn or transport.bot_ref is None:
            return None
        from .session_catalog import ProtectedDeliveryBinding

        session = getattr(event, "session", None)
        platform_id = str(event.get_platform_id() or "")
        self_id = str(event.get_self_id() or "")
        try:
            return self._catalog.begin_turn(
                transport,
                ProtectedDeliveryBinding(
                    platform_id=platform_id,
                    self_id=self_id,
                    message_session=str(session),
                    target_address="test-reactive-target",
                    adapter_capability="reactive_only",
                    account_proof_digest="test-unverified-proof",
                    account_proof_generation=0,
                    account_proof_expires_at_ms=0,
                    binding_generation=transport.bot_ref.generation,
                ),
            )
        except Exception:
            return None

    async def resolve(self, event: Any, request: Any) -> ResolvedScope:
        """Freeze the exact Persona AstrBot selected for this request once."""

        now_ms = int(self._clock_ms())
        conversation = getattr(request, "conversation", None)
        if conversation is None:
            return ResolvedScope.disabled(
                "persona_application_unverified", resolved_at_ms=now_ms
            )
        transport = self._event_extra(event, "_sylanne_transport_scope_v1")
        turn = self._event_extra(event, "_sylanne_transport_turn_v1")
        if type(transport) is not ResolvedTransportScope:
            transport = self.resolve_transport(event) if self._allow_test_synthetic_turn else None
        if (
            type(transport) is not ResolvedTransportScope
            or transport.private_scope_enabled is not True
            or transport.bot_ref is None
            or transport.session_ref is None
        ):
            return ResolvedScope.disabled(
                "transport_session_unverified", resolved_at_ms=now_ms
            )
        if turn is None:
            turn = self._test_turn(event, transport)
        if turn is None:
            return ResolvedScope.disabled("transport_turn_unverified", resolved_at_ms=now_ms)
        try:
            cfg = self._context.get_config(umo=event.unified_msg_origin)
            selected_id, personality, forced_id, _is_webchat_special = (
                await self._context.persona_manager.resolve_selected_persona(
                    umo=event.unified_msg_origin,
                    conversation_persona_id=(
                        request.conversation.persona_id if request.conversation else None
                    ),
                    platform_name=event.get_platform_name(),
                    provider_settings=cfg.get("provider_settings", {}),
                )
            )
        except Exception:
            return ResolvedScope.disabled("persona_unavailable", resolved_at_ms=now_ms)
        if selected_id is None or personality is None:
            return ResolvedScope.disabled("persona_unavailable", resolved_at_ms=now_ms)
        if type(selected_id) is str and selected_id.startswith(_MANAGED_EMBODIMENT_PREFIX):
            return ResolvedScope.disabled(
                "managed_persona_forbidden", resolved_at_ms=now_ms
            )
        source = self._persona_source(
            selected_id,
            personality,
            resolution_source=self._resolution_source(request, forced_id),
        )
        if source is None:
            return ResolvedScope.disabled("persona_unavailable", resolved_at_ms=now_ms)
        try:
            session = getattr(event, "session", None)
            platform_id = str(event.get_platform_id() or "")
            canonical_umo = str(session) if session is not None else ""
            scope = self._scope_for(
                transport,
                source,
                platform_id=platform_id,
                canonical_umo=canonical_umo,
            )
            frozen_turn = self._catalog.freeze_persona(turn, scope)
            resolved = ResolvedScope(
                scope=scope,
                persona_source=source,
                identity_quality=transport.identity_quality,
                resolution_source=source.resolution_source,
                resolved_at_ms=now_ms,
                private_scope_enabled=True,
                disabled_reason=None,
                turn_generation=frozen_turn.turn_generation,
            )
        except Exception:
            return ResolvedScope.disabled("scope_resolution_unverified", resolved_at_ms=now_ms)
        if not self.set_event_extra(event, "_sylanne_resolved_scope_v1", resolved):
            return ResolvedScope.disabled("scope_resolution_unverified", resolved_at_ms=now_ms)
        return resolved

    async def resolve_test_values(
        self,
        *,
        platform_id: str,
        self_id: str,
        umo: str,
        persona_id: str,
        proof: AdapterAccountProof | None = None,
        current_account_set_digest: str = "",
        current_proof_generation: int = 0,
        now_ms: int | None = None,
    ) -> ResolvedScope:
        """Small test seam for transport/persona rejection cases."""

        class _Session:
            def __init__(self, platform: str, value: str) -> None:
                self.platform_id = platform
                self._value = value

            def __str__(self) -> str:
                return self._value

        if proof is not None:
            class _Proofs:
                def current(self, _platform_id: str) -> CurrentAdapterAccountProof:
                    return CurrentAdapterAccountProof(
                        proof=proof,
                        current_account_set_digest=current_account_set_digest,
                        current_proof_generation=current_proof_generation,
                    )

            previous = self._account_proofs
            self._account_proofs = _Proofs()
        else:
            previous = None
        previous_clock = self._clock_ms
        if now_ms is not None:
            self._clock_ms = lambda: now_ms
        try:
            event = type("ScopeEvent", (), {})()
            event.session = _Session(umo.split(":", 1)[0] if umo else platform_id, umo)
            event.get_platform_id = lambda: platform_id
            event.get_self_id = lambda: self_id
            transport = self.resolve_transport(event)
        finally:
            if previous is not None:
                self._account_proofs = previous
            self._clock_ms = previous_clock
        resolved_at_ms = int(self._clock_ms()) if now_ms is None else now_ms
        if transport.private_scope_enabled is not True:
            return ResolvedScope.disabled(
                transport.disabled_reason or "transport_session_unverified",
                resolved_at_ms=resolved_at_ms,
            )
        if persona_id.startswith(_MANAGED_EMBODIMENT_PREFIX):
            return ResolvedScope.disabled(
                "managed_persona_forbidden", resolved_at_ms=resolved_at_ms
            )
        try:
            source = PersonaSource(
                persona_id=persona_id,
                prompt="test persona",
                begin_dialogs=(),
                tools=None,
                skills=None,
                resolution_source="default",
            )
            turn = self._test_turn(event, transport)
            if turn is None:
                raise ValueError("transport turn unavailable")
            scope = self._scope_for(
                transport,
                source,
                platform_id=platform_id,
                canonical_umo=umo,
            )
            frozen = self._catalog.freeze_persona(turn, scope)
            return ResolvedScope(
                scope=scope,
                persona_source=source,
                identity_quality=transport.identity_quality,
                resolution_source=source.resolution_source,
                resolved_at_ms=resolved_at_ms,
                private_scope_enabled=True,
                disabled_reason=None,
                turn_generation=frozen.turn_generation,
            )
        except Exception:
            return ResolvedScope.disabled(
                "scope_resolution_unverified", resolved_at_ms=resolved_at_ms
            )


__all__ = [
    "AdapterAccountProof",
    "AdapterAccountProofProvider",
    "BotBinding",
    "CurrentAdapterAccountProof",
    "NoAdapterAccountProofProvider",
    "PersonaSource",
    "ScopeResolver",
    "ScopeIdentityKey",
    "load_or_create_scope_identity_key",
    "resolve_proven_single_account",
]
