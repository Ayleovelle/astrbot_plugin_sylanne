"""HMAC-derived opaque identities for isolated multibot scope namespaces."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import Protocol

from .scope_contracts import BotRef, PersonaRevisionRef, RelationRef, SessionRef

_BOT_DOMAIN = b"sylanne.scope.bot.v1\x00"
_PERSONA_DOMAIN = b"sylanne.scope.persona.v1\x00"
_SESSION_DOMAIN = b"sylanne.scope.session.v1\x00"
_RELATION_DOMAIN = b"sylanne.scope.relation.v1\x00"
_STORAGE_DOMAIN = b"sylanne.scope.storage.v1\x00"
_MANAGED_EMBODIMENT_PREFIX = "sylanne_embodiment_"
_MAX_IDENTITY_COMPONENT_BYTES = 4096


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
        if type(self.secret) is not bytes or len(self.secret) < 32:
            raise ValueError("secret must be exact bytes with length at least 32")

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


@dataclass(frozen=True, slots=True)
class AdapterAccountProof:
    platform_id: str
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


__all__ = [
    "AdapterAccountProof",
    "AdapterAccountProofProvider",
    "BotBinding",
    "CurrentAdapterAccountProof",
    "NoAdapterAccountProofProvider",
    "PersonaSource",
    "ScopeIdentityKey",
    "resolve_proven_single_account",
]
