"""Opaque, immutable contracts for multibot scope resolution and delivery."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .scope_identity import PersonaSource

_TOKEN_PAYLOAD = re.compile(r"[A-Za-z0-9_-]+\Z", re.ASCII)
_IDENTITY_QUALITY = "event_get_sender_id"
_IDENTITY_QUALITY_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}\Z", re.ASCII)
_SUBJECT_KIND = "user"
_MAX_SUBJECT_COMPONENT_BYTES = 4096


def _require_token(value: object, prefix: str) -> str:
    """Return one exact opaque token, rejecting values outside its namespace."""

    if (
        type(value) is not str
        or not value.startswith(prefix)
        or _TOKEN_PAYLOAD.fullmatch(value[len(prefix) :]) is None
    ):
        raise ValueError(f"invalid {prefix} token")
    return value


def _require_generation(value: object, name: str = "generation") -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative int")
    return value


def _require_text(value: object, name: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"{name} must be a non-empty str")
    return value


def _require_optional_text(value: object, name: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, name)


def _require_bool(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be an exact bool")
    return value


def _require_subject_component(value: object, name: str) -> str:
    """Validate a raw identity component without ever echoing it back."""

    if type(value) is not str:
        raise ValueError(f"{name} must be an exact non-empty str")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError(f"{name} must be an exact non-empty str") from exc
    if not encoded or len(encoded) > _MAX_SUBJECT_COMPONENT_BYTES:
        raise ValueError(f"{name} must be an exact non-empty str")
    return value


def _require_authenticated_identity_quality(value: object) -> str:
    """Permit only the one adapter call path with sender authentication proof."""

    if type(value) is not str or _IDENTITY_QUALITY_PATTERN.fullmatch(value) is None:
        raise ValueError("identity_quality must be event_get_sender_id")
    if value != _IDENTITY_QUALITY:
        raise ValueError("identity_quality must be event_get_sender_id")
    return value


def _require_bot_ref(value: object) -> BotRef:
    if type(value) is not BotRef:
        raise ValueError("bot_ref must be a BotRef")
    return value


def _require_persona_ref(value: object) -> PersonaRevisionRef:
    if type(value) is not PersonaRevisionRef:
        raise ValueError("persona_ref must be a PersonaRevisionRef")
    return value


def _require_session_ref(value: object) -> SessionRef:
    if type(value) is not SessionRef:
        raise ValueError("session_ref must be a SessionRef")
    return value


def _require_relation_ref(value: object) -> RelationRef:
    if type(value) is not RelationRef:
        raise ValueError("relation_ref must be a RelationRef")
    return value


def _require_persona_belongs(bot_ref: BotRef, persona_ref: PersonaRevisionRef) -> None:
    if persona_ref.bot_ref != bot_ref:
        raise ValueError("persona does not belong to bot")


def _require_session_belongs(bot_ref: BotRef, session_ref: SessionRef) -> None:
    if session_ref.bot_ref != bot_ref:
        raise ValueError("session does not belong to bot")


@dataclass(frozen=True, slots=True)
class BotRef:
    token: str
    generation: int

    def __post_init__(self) -> None:
        _require_token(self.token, "bot_v1_")
        _require_generation(self.generation)


@dataclass(frozen=True, slots=True)
class PersonaRevisionRef:
    token: str
    bot_ref: BotRef
    persona_id_digest: str
    source_fingerprint: str
    lifecycle_generation: int

    def __post_init__(self) -> None:
        _require_token(self.token, "persona_v1_")
        _require_bot_ref(self.bot_ref)
        if type(self.persona_id_digest) is not str or len(self.persona_id_digest) != 64:
            raise ValueError("persona_id_digest must be a 64-character str")
        if type(self.source_fingerprint) is not str or len(self.source_fingerprint) != 64:
            raise ValueError("source_fingerprint must be a 64-character str")
        _require_generation(self.lifecycle_generation, "lifecycle_generation")


@dataclass(frozen=True, slots=True)
class SessionRef:
    token: str
    bot_ref: BotRef
    generation: int

    def __post_init__(self) -> None:
        _require_token(self.token, "session_v1_")
        _require_bot_ref(self.bot_ref)
        _require_generation(self.generation)


@dataclass(frozen=True, slots=True)
class SessionScope:
    bot_ref: BotRef
    persona_ref: PersonaRevisionRef
    session_ref: SessionRef
    storage_token: str
    scope_generation: int

    def __post_init__(self) -> None:
        bot_ref = _require_bot_ref(self.bot_ref)
        persona_ref = _require_persona_ref(self.persona_ref)
        session_ref = _require_session_ref(self.session_ref)
        _require_persona_belongs(bot_ref, persona_ref)
        _require_session_belongs(bot_ref, session_ref)
        _require_token(self.storage_token, "scope_v1_")
        _require_generation(self.scope_generation, "scope_generation")

    def storage_components(self) -> tuple[str, str, str]:
        """Return only opaque storage partition components."""

        return (self.bot_ref.token, self.persona_ref.token, self.session_ref.token)


@dataclass(frozen=True, slots=True)
class PersonaScope:
    bot_ref: BotRef
    persona_ref: PersonaRevisionRef

    def __post_init__(self) -> None:
        bot_ref = _require_bot_ref(self.bot_ref)
        persona_ref = _require_persona_ref(self.persona_ref)
        _require_persona_belongs(bot_ref, persona_ref)


@dataclass(frozen=True, slots=True)
class RelationRef:
    token: str
    bot_ref: BotRef

    def __post_init__(self) -> None:
        _require_token(self.token, "relation_v1_")
        _require_bot_ref(self.bot_ref)


@dataclass(frozen=True, slots=True)
class RelationScope:
    bot_ref: BotRef
    persona_ref: PersonaRevisionRef
    relation_ref: RelationRef
    relation_generation: int

    def __post_init__(self) -> None:
        bot_ref = _require_bot_ref(self.bot_ref)
        persona_ref = _require_persona_ref(self.persona_ref)
        relation_ref = _require_relation_ref(self.relation_ref)
        _require_persona_belongs(bot_ref, persona_ref)
        if relation_ref.bot_ref != bot_ref:
            raise ValueError("relation does not belong to bot")
        _require_generation(self.relation_generation, "relation_generation")


@dataclass(frozen=True, slots=True)
class VerifiedSubjectInput:
    """Ephemeral adapter proof material for one verified human sender.

    ``subject_id`` is intentionally the only raw sender value in this path.  It
    is accepted solely to HMAC-derive a :class:`RelationRef` and is redacted from
    the dataclass representation; no durable/runtime contract carries it onward.
    """

    platform_realm: str
    subject_kind: str = _SUBJECT_KIND
    subject_id: str = field(default="", repr=False)
    identity_quality: str = _IDENTITY_QUALITY

    def __post_init__(self) -> None:
        _require_subject_component(self.platform_realm, "platform_realm")
        if type(self.subject_kind) is not str or self.subject_kind != _SUBJECT_KIND:
            raise ValueError("subject_kind must be user")
        _require_subject_component(self.subject_id, "subject_id")
        _require_authenticated_identity_quality(self.identity_quality)


@dataclass(frozen=True, slots=True)
class AuthenticatedSubject:
    """Opaque relation identity retained after raw adapter subject disposal."""

    relation_ref: RelationRef
    identity_quality: str

    def __post_init__(self) -> None:
        _require_relation_ref(self.relation_ref)
        _require_authenticated_identity_quality(self.identity_quality)


@dataclass(frozen=True, slots=True)
class TurnSubjectProof:
    """A subject proof bound to one opaque transport session turn."""

    transport_session_token: str
    turn_generation: int
    subject: AuthenticatedSubject | None

    def __post_init__(self) -> None:
        _require_token(self.transport_session_token, "session_v1_")
        _require_generation(self.turn_generation, "turn_generation")
        if self.subject is not None and type(self.subject) is not AuthenticatedSubject:
            raise ValueError("subject must be an AuthenticatedSubject or None")


@dataclass(frozen=True, slots=True)
class ResolvedTransportScope:
    """Transport identity result, with an explicit fail-closed disabled state."""

    bot_ref: BotRef | None
    session_ref: SessionRef | None
    identity_quality: str | None
    private_scope_enabled: bool
    disabled_reason: str | None

    def __post_init__(self) -> None:
        _require_bool(self.private_scope_enabled, "private_scope_enabled")
        if self.private_scope_enabled is False:
            if (
                self.bot_ref is not None
                or self.session_ref is not None
                or self.identity_quality is not None
            ):
                raise ValueError("invalid disabled transport scope state")
            _require_text(self.disabled_reason, "disabled_reason")
            return
        bot_ref = _require_bot_ref(self.bot_ref)
        session_ref = _require_session_ref(self.session_ref)
        _require_session_belongs(bot_ref, session_ref)
        _require_text(self.identity_quality, "identity_quality")
        if self.disabled_reason is not None:
            raise ValueError("invalid successful transport scope state")

    @classmethod
    def disabled(cls, reason: str) -> ResolvedTransportScope:
        return cls(
            bot_ref=None,
            session_ref=None,
            identity_quality=None,
            private_scope_enabled=False,
            disabled_reason=reason,
        )


@dataclass(frozen=True, slots=True)
class ResolvedScope:
    scope: SessionScope | None
    persona_source: PersonaSource | None = field(repr=False)
    identity_quality: str | None
    resolution_source: str | None
    resolved_at_ms: int
    private_scope_enabled: bool
    disabled_reason: str | None
    turn_generation: int | None

    def __post_init__(self) -> None:
        _require_generation(self.resolved_at_ms, "resolved_at_ms")
        _require_bool(self.private_scope_enabled, "private_scope_enabled")

        if self.scope is None:
            if (
                self.persona_source is not None
                or self.identity_quality is not None
                or self.resolution_source is not None
                or self.private_scope_enabled is not False
                or self.turn_generation is not None
            ):
                raise ValueError("invalid disabled resolved scope state")
            _require_text(self.disabled_reason, "disabled_reason")
            return

        if type(self.scope) is not SessionScope:
            raise ValueError("scope must be a SessionScope or None")

        from .scope_identity import PersonaSource

        if type(self.persona_source) is not PersonaSource:
            raise ValueError("persona_source must be a PersonaSource")
        _require_text(self.identity_quality, "identity_quality")
        _require_text(self.resolution_source, "resolution_source")
        if self.private_scope_enabled is not True or self.disabled_reason is not None:
            raise ValueError("invalid successful resolved scope state")
        _require_generation(self.turn_generation, "turn_generation")

    @classmethod
    def disabled(cls, reason: str, *, resolved_at_ms: int) -> ResolvedScope:
        return cls(
            scope=None,
            persona_source=None,
            identity_quality=None,
            resolution_source=None,
            resolved_at_ms=resolved_at_ms,
            private_scope_enabled=False,
            disabled_reason=reason,
            turn_generation=None,
        )


@dataclass(frozen=True, slots=True)
class ScopeDiagnosticEcho:
    """Bounded diagnostic projection; do not pass this object to public serializers."""

    bot_ref: str
    persona_ref: str
    session_ref: str
    scope_generation: int
    resolved_at_ms: int

    def __post_init__(self) -> None:
        _require_token(self.bot_ref, "bot_v1_")
        _require_token(self.persona_ref, "persona_v1_")
        _require_token(self.session_ref, "session_v1_")
        _require_generation(self.scope_generation, "scope_generation")
        _require_generation(self.resolved_at_ms, "resolved_at_ms")


@dataclass(frozen=True, slots=True)
class ScopeApiPathEcho:
    bot_ref: str
    persona_ref: str
    session_ref: str

    def __post_init__(self) -> None:
        _require_token(self.bot_ref, "bot_v1_")
        _require_token(self.persona_ref, "persona_v1_")
        _require_token(self.session_ref, "session_v1_")


@dataclass(frozen=True, slots=True)
class ScopeApiEcho:
    scope: ScopeApiPathEcho
    scope_generation: int
    resolved_at_ms: int
    bot_generation: int | None = None
    persona_lifecycle_generation: int | None = None
    session_generation: int | None = None
    relation_generation: int | None = None
    turn_generation: int | None = None

    def __post_init__(self) -> None:
        if type(self.scope) is not ScopeApiPathEcho:
            raise ValueError("scope must be a ScopeApiPathEcho")
        _require_generation(self.scope_generation, "scope_generation")
        _require_generation(self.resolved_at_ms, "resolved_at_ms")
        for name, value in (
            ("bot_generation", self.bot_generation),
            ("persona_lifecycle_generation", self.persona_lifecycle_generation),
            ("session_generation", self.session_generation),
            ("relation_generation", self.relation_generation),
            ("turn_generation", self.turn_generation),
        ):
            if value is not None:
                _require_generation(value, name)


@dataclass(frozen=True, slots=True)
class PersonaApiPathEcho:
    bot_ref: str
    persona_ref: str

    def __post_init__(self) -> None:
        _require_token(self.bot_ref, "bot_v1_")
        _require_token(self.persona_ref, "persona_v1_")


@dataclass(frozen=True, slots=True)
class PersonaApiEcho:
    scope: PersonaApiPathEcho
    scope_generation: int
    resolved_at_ms: int

    def __post_init__(self) -> None:
        if type(self.scope) is not PersonaApiPathEcho:
            raise ValueError("scope must be a PersonaApiPathEcho")
        _require_generation(self.scope_generation, "scope_generation")
        _require_generation(self.resolved_at_ms, "resolved_at_ms")


@dataclass(frozen=True, slots=True)
class TurnDeliveryLease:
    transport_session_token: str
    resolved_scope_token: str
    bot_binding_generation: int
    persona_lifecycle_generation: int
    session_generation: int
    scope_generation: int
    turn_generation: int

    def __post_init__(self) -> None:
        _require_token(self.transport_session_token, "session_v1_")
        _require_token(self.resolved_scope_token, "scope_v1_")
        _require_generation(self.bot_binding_generation, "bot_binding_generation")
        _require_generation(self.persona_lifecycle_generation, "persona_lifecycle_generation")
        _require_generation(self.session_generation, "session_generation")
        _require_generation(self.scope_generation, "scope_generation")
        _require_generation(self.turn_generation, "turn_generation")


@dataclass(frozen=True, slots=True)
class ProactiveDeliveryLease:
    transport_session_token: str
    resolved_scope_token: str
    expected_persona_token: str
    persona_lifecycle_generation: int
    session_generation: int
    scope_generation: int
    expected_turn_generation: int
    expires_at_ms: int

    def __post_init__(self) -> None:
        _require_token(self.transport_session_token, "session_v1_")
        _require_token(self.resolved_scope_token, "scope_v1_")
        _require_token(self.expected_persona_token, "persona_v1_")
        _require_generation(self.persona_lifecycle_generation, "persona_lifecycle_generation")
        _require_generation(self.session_generation, "session_generation")
        _require_generation(self.scope_generation, "scope_generation")
        _require_generation(self.expected_turn_generation, "expected_turn_generation")
        _require_generation(self.expires_at_ms, "expires_at_ms")


@dataclass(frozen=True, slots=True, repr=False)
class BotDeliveryRef:
    token: str
    delivery_id: str
    bot_ref: BotRef
    persona_ref: PersonaRevisionRef
    session_ref: SessionRef
    platform_id: str = field(repr=False)
    self_id: str = field(repr=False)
    target_address: str = field(repr=False)
    adapter_capability: str = field(repr=False)

    def __post_init__(self) -> None:
        _require_token(self.token, "delivery_v1_")
        _require_text(self.delivery_id, "delivery_id")
        bot_ref = _require_bot_ref(self.bot_ref)
        persona_ref = _require_persona_ref(self.persona_ref)
        session_ref = _require_session_ref(self.session_ref)
        _require_persona_belongs(bot_ref, persona_ref)
        _require_session_belongs(bot_ref, session_ref)
        _require_text(self.platform_id, "platform_id")
        _require_text(self.self_id, "self_id")
        _require_text(self.target_address, "target_address")
        _require_text(self.adapter_capability, "adapter_capability")


@dataclass(frozen=True, slots=True, repr=False)
class ProactiveIntentDraft:
    delivery_ref: BotDeliveryRef
    lease: ProactiveDeliveryLease
    text: str = field(repr=False)
    idempotent: bool
    issuer_mac: str = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.delivery_ref) is not BotDeliveryRef:
            raise ValueError("delivery_ref must be a BotDeliveryRef")
        if type(self.lease) is not ProactiveDeliveryLease:
            raise ValueError("lease must be a ProactiveDeliveryLease")
        if type(self.text) is not str:
            raise ValueError("text must be an exact str")
        _require_bool(self.idempotent, "idempotent")
        if type(self.issuer_mac) is not str:
            raise ValueError("issuer_mac must be an exact str")


__all__ = [
    "AuthenticatedSubject",
    "BotDeliveryRef",
    "BotRef",
    "PersonaApiEcho",
    "PersonaApiPathEcho",
    "PersonaRevisionRef",
    "PersonaScope",
    "ProactiveDeliveryLease",
    "ProactiveIntentDraft",
    "RelationRef",
    "RelationScope",
    "ResolvedScope",
    "ResolvedTransportScope",
    "ScopeApiEcho",
    "ScopeApiPathEcho",
    "ScopeDiagnosticEcho",
    "SessionRef",
    "SessionScope",
    "TurnDeliveryLease",
    "TurnSubjectProof",
    "VerifiedSubjectInput",
]
