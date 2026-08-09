"""Offline, default-deny authority for importing unscoped legacy records.

The migration claim service owns legacy bytes and destination capabilities.  This
module owns only the narrow question of whether an already authenticated WebUI
principal may view the inventory or bind one exact record to one frozen scope.
It deliberately has no HTTP, configuration, or legacy-source dependencies.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from typing import Final

from .scope_contracts import (
    BotRef,
    PersonaRevisionRef,
    RelationRef,
    RelationScope,
    ScopeApiPathEcho,
    ScopedPrincipal,
    SessionRef,
    SessionScope,
)
from .scope_repository import RepositoryCorruptionError, ScopeRepository, _canonical_json_bytes


LEGACY_CLAIM_ACTION: Final[str] = "POST:legacy-claim"
_SCHEMA: Final[str] = "sylanne.legacy-claim-authority.v1"
_ACTOR_DOMAIN: Final[bytes] = b"sylanne.legacy-claim.actor.v1\x00"
_HEX = frozenset("0123456789abcdef")


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _token(value: object, prefix: str) -> str:
    if (
        type(value) is not str
        or not value.startswith(prefix)
        or not value[len(prefix) :]
        or len(value) > 192
        or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in value[len(prefix) :])
    ):
        raise ValueError(f"invalid {prefix} token")
    return value


def _record_id(value: object) -> str:
    if type(value) is not str or len(value) != 64 or any(item not in _HEX for item in value):
        raise ValueError("record_id must be a lowercase SHA-256 fingerprint")
    return value


def _optional_expiry(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ValueError("expires_at_ms must be a non-negative int or None")
    return value


def _revision(value: object, name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive int")
    return value


def _actor_id(value: object) -> str:
    if type(value) is not str or not value:
        raise ValueError("actor_id must be a non-empty str")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError("actor_id must be UTF-8") from exc
    if len(encoded) > 4096:
        raise ValueError("actor_id is too large")
    return value


def _scope_document(scope: SessionScope) -> dict[str, object]:
    return {
        "bot_generation": scope.bot_ref.generation,
        "bot_ref": scope.bot_ref.token,
        "persona_id_digest": scope.persona_ref.persona_id_digest,
        "persona_lifecycle_generation": scope.persona_ref.lifecycle_generation,
        "persona_ref": scope.persona_ref.token,
        "persona_source_fingerprint": scope.persona_ref.source_fingerprint,
        "scope_generation": scope.scope_generation,
        "session_generation": scope.session_ref.generation,
        "session_ref": scope.session_ref.token,
        "storage_token": scope.storage_token,
    }


def _relation_document(relation: RelationScope) -> dict[str, object]:
    return {
        "bot_generation": relation.bot_ref.generation,
        "bot_ref": relation.bot_ref.token,
        "persona_id_digest": relation.persona_ref.persona_id_digest,
        "persona_lifecycle_generation": relation.persona_ref.lifecycle_generation,
        "persona_ref": relation.persona_ref.token,
        "persona_source_fingerprint": relation.persona_ref.source_fingerprint,
        "relation_generation": relation.relation_generation,
        "relation_ref": relation.relation_ref.token,
    }


def _scope_from_document(value: object) -> SessionScope:
    if type(value) is not dict or set(value) != {
        "bot_generation", "bot_ref", "persona_id_digest", "persona_lifecycle_generation", "persona_ref",
        "persona_source_fingerprint", "scope_generation", "session_generation", "session_ref", "storage_token",
    }:
        raise ValueError("claim scope is invalid")
    bot = BotRef(token=_token(value["bot_ref"], "bot_v1_"), generation=value["bot_generation"])
    persona = PersonaRevisionRef(
        token=_token(value["persona_ref"], "persona_v1_"), bot_ref=bot,
        persona_id_digest=value["persona_id_digest"], source_fingerprint=value["persona_source_fingerprint"],
        lifecycle_generation=value["persona_lifecycle_generation"],
    )
    return SessionScope(
        bot_ref=bot, persona_ref=persona,
        session_ref=SessionRef(token=_token(value["session_ref"], "session_v1_"), bot_ref=bot, generation=value["session_generation"]),
        storage_token=_token(value["storage_token"], "scope_v1_"), scope_generation=value["scope_generation"],
    )


def _relation_from_document(value: object) -> RelationScope:
    if type(value) is not dict or set(value) != {
        "bot_generation", "bot_ref", "persona_id_digest", "persona_lifecycle_generation", "persona_ref",
        "persona_source_fingerprint", "relation_generation", "relation_ref",
    }:
        raise ValueError("claim relation is invalid")
    bot = BotRef(token=_token(value["bot_ref"], "bot_v1_"), generation=value["bot_generation"])
    persona = PersonaRevisionRef(
        token=_token(value["persona_ref"], "persona_v1_"), bot_ref=bot,
        persona_id_digest=value["persona_id_digest"], source_fingerprint=value["persona_source_fingerprint"],
        lifecycle_generation=value["persona_lifecycle_generation"],
    )
    return RelationScope(
        bot_ref=bot, persona_ref=persona,
        relation_ref=RelationRef(token=_token(value["relation_ref"], "relation_v1_"), bot_ref=bot),
        relation_generation=value["relation_generation"],
    )


@dataclass(frozen=True, slots=True)
class LegacyInventoryViewGrant:
    principal: ScopedPrincipal = field(repr=False)
    audit_id: str
    grant_id: str
    grant_revision: int = 1
    expires_at_ms: int | None = None
    revoked: bool = False

    def __post_init__(self) -> None:
        if type(self.principal) is not ScopedPrincipal:
            raise ValueError("principal must be a ScopedPrincipal")
        _token(self.audit_id, "audit_v1_")
        _token(self.grant_id, "grant_v1_")
        _revision(self.grant_revision, "grant_revision")
        _optional_expiry(self.expires_at_ms)
        if type(self.revoked) is not bool:
            raise ValueError("revoked must be an exact bool")


@dataclass(frozen=True, slots=True)
class LegacyClaimGrant:
    principal: ScopedPrincipal = field(repr=False)
    scope: SessionScope = field(repr=False)
    relation_scope: RelationScope = field(repr=False)
    record_id: str
    actor_binding: str = field(repr=False)
    audit_id: str
    grant_id: str
    action: str = LEGACY_CLAIM_ACTION
    grant_revision: int = 1
    expires_at_ms: int | None = None
    revoked: bool = False

    def __post_init__(self) -> None:
        if type(self.principal) is not ScopedPrincipal or type(self.scope) is not SessionScope:
            raise ValueError("claim principal and scope are required")
        if type(self.relation_scope) is not RelationScope:
            raise ValueError("claim relation scope is required")
        if (
            self.relation_scope.bot_ref != self.scope.bot_ref
            or self.relation_scope.persona_ref != self.scope.persona_ref
        ):
            raise ValueError("claim relation does not belong to scope")
        _record_id(self.record_id)
        _token(self.actor_binding, "actorbind_v1_")
        _token(self.audit_id, "audit_v1_")
        _token(self.grant_id, "grant_v1_")
        if self.action != LEGACY_CLAIM_ACTION:
            raise ValueError("claim action must be canonical")
        _revision(self.grant_revision, "grant_revision")
        _optional_expiry(self.expires_at_ms)
        if type(self.revoked) is not bool:
            raise ValueError("revoked must be an exact bool")


@dataclass(frozen=True, slots=True)
class LegacyClaimIntent:
    document_revision: int
    grant_id: str
    grant_revision: int
    audit_id: str
    principal: ScopedPrincipal = field(repr=False)
    record_id: str
    scope: SessionScope = field(repr=False)
    relation_scope: RelationScope = field(repr=False)
    action: str = LEGACY_CLAIM_ACTION

    def __post_init__(self) -> None:
        _revision(self.document_revision, "document_revision")
        _token(self.grant_id, "grant_v1_")
        _revision(self.grant_revision, "grant_revision")
        _token(self.audit_id, "audit_v1_")
        if type(self.principal) is not ScopedPrincipal:
            raise ValueError("intent principal must be a ScopedPrincipal")
        _record_id(self.record_id)
        if type(self.scope) is not SessionScope or type(self.relation_scope) is not RelationScope:
            raise ValueError("intent scope and relation scope are required")
        if (
            self.relation_scope.bot_ref != self.scope.bot_ref
            or self.relation_scope.persona_ref != self.scope.persona_ref
        ):
            raise ValueError("intent relation does not belong to scope")
        if self.action != LEGACY_CLAIM_ACTION:
            raise ValueError("intent action must be canonical")


class LegacyClaimAuthority:
    """One repository-owned, offline-replaceable legacy migration ACL."""

    def __init__(self, repository: ScopeRepository, *, clock_ms=None) -> None:
        if type(repository) is not ScopeRepository:
            raise ValueError("repository must be a ScopeRepository")
        self.repository = repository
        self._clock_ms = _now_ms if clock_ms is None else clock_ms
        if not callable(self._clock_ms):
            raise ValueError("clock_ms must be callable")
        self._actor_secret = repository.legacy_claim_actor_secret()

    def _actor_binding(self, actor_id: object) -> str:
        raw = _actor_id(actor_id).encode("utf-8")
        digest = hmac.new(self._actor_secret, _ACTOR_DOMAIN + raw, hashlib.sha256).hexdigest()
        return f"actorbind_v1_{digest}"

    @staticmethod
    def _grant_id() -> str:
        return f"grant_v1_{secrets.token_urlsafe(18)}"

    def enroll_inventory_view_grant(
        self, *, principal: ScopedPrincipal, audit_id: str, expires_at_ms: int | None = None
    ) -> LegacyInventoryViewGrant:
        return LegacyInventoryViewGrant(
            principal=principal, audit_id=audit_id, grant_id=self._grant_id(), expires_at_ms=expires_at_ms
        )

    def enroll_claim_grant(
        self, *, principal: ScopedPrincipal, scope: SessionScope, relation_scope: RelationScope,
        record_id: str, actor_id: str, audit_id: str, expires_at_ms: int | None = None,
    ) -> LegacyClaimGrant:
        return LegacyClaimGrant(
            principal=principal, scope=scope, relation_scope=relation_scope, record_id=record_id,
            actor_binding=self._actor_binding(actor_id), audit_id=audit_id, grant_id=self._grant_id(),
            expires_at_ms=expires_at_ms,
        )

    @staticmethod
    def _view_document(grant: LegacyInventoryViewGrant) -> dict[str, object]:
        return {
            "audit_id": grant.audit_id, "expires_at_ms": grant.expires_at_ms,
            "grant_id": grant.grant_id, "grant_revision": grant.grant_revision,
            "principal": grant.principal.token, "revoked": grant.revoked,
        }

    @staticmethod
    def _claim_document(grant: LegacyClaimGrant) -> dict[str, object]:
        return {
            "action": grant.action, "actor_binding": grant.actor_binding, "audit_id": grant.audit_id,
            "expires_at_ms": grant.expires_at_ms, "grant_id": grant.grant_id,
            "grant_revision": grant.grant_revision, "principal": grant.principal.token,
            "record_id": grant.record_id, "relation_scope": _relation_document(grant.relation_scope),
            "revoked": grant.revoked, "scope": _scope_document(grant.scope),
        }

    @staticmethod
    def _view_from_document(value: object) -> LegacyInventoryViewGrant:
        if type(value) is not dict or set(value) != {
            "audit_id", "expires_at_ms", "grant_id", "grant_revision", "principal", "revoked",
        }:
            raise ValueError("inventory grant is invalid")
        return LegacyInventoryViewGrant(
            principal=ScopedPrincipal(_token(value["principal"], "principal_v1_")), audit_id=value["audit_id"],
            grant_id=value["grant_id"], grant_revision=value["grant_revision"],
            expires_at_ms=value["expires_at_ms"], revoked=value["revoked"],
        )

    @staticmethod
    def _claim_from_document(value: object) -> LegacyClaimGrant:
        if type(value) is not dict or set(value) != {
            "action", "actor_binding", "audit_id", "expires_at_ms", "grant_id", "grant_revision",
            "principal", "record_id", "relation_scope", "revoked", "scope",
        }:
            raise ValueError("claim grant is invalid")
        return LegacyClaimGrant(
            principal=ScopedPrincipal(_token(value["principal"], "principal_v1_")),
            scope=_scope_from_document(value["scope"]), relation_scope=_relation_from_document(value["relation_scope"]),
            record_id=value["record_id"], actor_binding=value["actor_binding"], audit_id=value["audit_id"],
            grant_id=value["grant_id"], action=value["action"], grant_revision=value["grant_revision"],
            expires_at_ms=value["expires_at_ms"], revoked=value["revoked"],
        )

    @staticmethod
    def _active(grant: LegacyInventoryViewGrant | LegacyClaimGrant, now_ms: int) -> bool:
        return grant.revoked is False and (grant.expires_at_ms is None or now_ms < grant.expires_at_ms)

    def _document_locked(self) -> tuple[int, tuple[LegacyInventoryViewGrant, ...], tuple[LegacyClaimGrant, ...]]:
        loaded = self.repository._read_legacy_claim_authority_locked()
        if loaded is None:
            return 0, (), ()
        raw, document = loaded
        if (
            set(document) != {"claim_grants", "document_revision", "inventory_grants", "schema_version"}
            or document["schema_version"] != _SCHEMA
            or type(document["document_revision"]) is not int
            or document["document_revision"] < 1
            or type(document["inventory_grants"]) is not list
            or type(document["claim_grants"]) is not list
            or raw != _canonical_json_bytes(document)
        ):
            raise RepositoryCorruptionError("legacy claim authority is invalid")
        try:
            views = tuple(self._view_from_document(item) for item in document["inventory_grants"])
            claims = tuple(self._claim_from_document(item) for item in document["claim_grants"])
        except (TypeError, ValueError) as exc:
            raise RepositoryCorruptionError("legacy claim authority is invalid") from exc
        identifiers = [grant.grant_id for grant in (*views, *claims)]
        if len(identifiers) != len(set(identifiers)):
            raise RepositoryCorruptionError("legacy claim authority grant identifiers conflict")
        return document["document_revision"], views, claims

    def replace_grants(
        self, *, inventory_grants: tuple[LegacyInventoryViewGrant, ...], claim_grants: tuple[LegacyClaimGrant, ...]
    ) -> int:
        """Trusted offline full replacement; HTTP and settings never call this."""

        if type(inventory_grants) is not tuple or type(claim_grants) is not tuple:
            raise ValueError("grants must be exact tuples")
        if any(type(grant) is not LegacyInventoryViewGrant for grant in inventory_grants) or any(
            type(grant) is not LegacyClaimGrant for grant in claim_grants
        ):
            raise ValueError("invalid authority grant")
        identifiers = [grant.grant_id for grant in (*inventory_grants, *claim_grants)]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("grant identifiers must be unique")
        with self.repository._repository_lock():
            current, _views, _claims = self._document_locked()
            revision = current + 1
            document = {
                "schema_version": _SCHEMA,
                "document_revision": revision,
                "inventory_grants": [self._view_document(item) for item in sorted(inventory_grants, key=lambda item: item.grant_id)],
                "claim_grants": [self._claim_document(item) for item in sorted(claim_grants, key=lambda item: item.grant_id)],
            }
            self.repository._write_legacy_claim_authority_locked(document)
        return revision

    def _load(self) -> tuple[int, tuple[LegacyInventoryViewGrant, ...], tuple[LegacyClaimGrant, ...]] | None:
        try:
            with self.repository._repository_lock_nowait():
                return self._document_locked()
        except Exception:  # noqa: BLE001 - request authority is strictly fail closed
            return None

    def inventory_view_allowed(self, principal: ScopedPrincipal) -> bool:
        if type(principal) is not ScopedPrincipal:
            return False
        loaded = self._load()
        if loaded is None:
            return False
        _revision_value, views, _claims = loaded
        now_ms = self._clock_ms()
        return any(grant.principal == principal and self._active(grant, now_ms) for grant in views)

    def _preflight_matches(
        self, principal: ScopedPrincipal, record_id: str, path: ScopeApiPathEcho,
    ) -> tuple[int, tuple[LegacyClaimGrant, ...]] | None:
        if type(principal) is not ScopedPrincipal or type(path) is not ScopeApiPathEcho:
            return None
        try:
            record = _record_id(record_id)
        except ValueError:
            return None
        loaded = self._load()
        if loaded is None:
            return None
        revision, _views, claims = loaded
        now_ms = self._clock_ms()
        matched = tuple(
            grant for grant in claims
            if self._active(grant, now_ms) and grant.principal == principal and grant.record_id == record
            and grant.action == LEGACY_CLAIM_ACTION
            and grant.scope.bot_ref.token == path.bot_ref and grant.scope.persona_ref.token == path.persona_ref
            and grant.scope.session_ref.token == path.session_ref
        )
        return revision, matched

    def preflight_claim(self, principal: ScopedPrincipal, record_id: str, path: ScopeApiPathEcho) -> LegacyClaimIntent | None:
        """Check exact ACL intent without touching a legacy source or nonce."""

        matched = self._preflight_matches(principal, record_id, path)
        if matched is None:
            return None
        revision, grants = matched
        if len(grants) != 1:
            return None
        grant = grants[0]
        return LegacyClaimIntent(
            document_revision=revision, grant_id=grant.grant_id, grant_revision=grant.grant_revision,
            audit_id=grant.audit_id, principal=principal, record_id=grant.record_id, scope=grant.scope,
            relation_scope=grant.relation_scope,
        )

    def relation_for_scope_action(self, principal: ScopedPrincipal, scope: SessionScope, action: str) -> RelationScope | None:
        if type(principal) is not ScopedPrincipal or type(scope) is not SessionScope or action != LEGACY_CLAIM_ACTION:
            return None
        loaded = self._load()
        if loaded is None:
            return None
        _revision_value, _views, claims = loaded
        now_ms = self._clock_ms()
        relations = {
            grant.relation_scope for grant in claims
            if self._active(grant, now_ms) and grant.principal == principal and grant.scope == scope
            and grant.action == action
        }
        return next(iter(relations)) if len(relations) == 1 else None

    def revalidate_claim(
        self, intent: LegacyClaimIntent, *, principal: ScopedPrincipal, record_id: str, scope: SessionScope,
        relation_scope: RelationScope, action: str, actor_id: str,
    ) -> bool:
        """Fence a prior preflight against ACL replacement, scope drift, and actor drift."""

        try:
            if (
                type(intent) is not LegacyClaimIntent or type(principal) is not ScopedPrincipal
                or type(scope) is not SessionScope or type(relation_scope) is not RelationScope
                or action != LEGACY_CLAIM_ACTION or intent.action != LEGACY_CLAIM_ACTION
                or principal != intent.principal or record_id != intent.record_id
                or scope != intent.scope or relation_scope != intent.relation_scope
            ):
                return False
        except (AttributeError, TypeError, ValueError):
            return False
        loaded = self._load()
        return self._revalidate_loaded(
            loaded, intent=intent, principal=principal, record_id=record_id, scope=scope,
            relation_scope=relation_scope, action=action, actor_id=actor_id,
        )

    def revalidate_pre_source(
        self, intent: LegacyClaimIntent, *, principal: ScopedPrincipal, record_id: str,
        scope: SessionScope, relation_scope: RelationScope, action: str,
    ) -> bool:
        """Fence all non-secret claim fields before an inventory source lookup."""

        return self._revalidate_loaded(
            self._load(), intent=intent, principal=principal, record_id=record_id,
            scope=scope, relation_scope=relation_scope, action=action, actor_id=None,
        )

    def revalidate_claim_locked(
        self, intent: LegacyClaimIntent, *, principal: ScopedPrincipal, record_id: str,
        scope: SessionScope, relation_scope: RelationScope, action: str, actor_id: str,
    ) -> bool:
        """Recheck the exact durable ACL while ``ScopeRepository.transaction`` is held."""

        try:
            self.repository._validate_relation_scope_locked(relation_scope)
            loaded = self._document_locked()
        except Exception:  # noqa: BLE001 - a durable ACL fence always fails closed
            return False
        return self._revalidate_loaded(
            loaded, intent=intent, principal=principal, record_id=record_id, scope=scope,
            relation_scope=relation_scope, action=action, actor_id=actor_id,
        )

    def _revalidate_loaded(
        self,
        loaded: tuple[int, tuple[LegacyInventoryViewGrant, ...], tuple[LegacyClaimGrant, ...]] | None,
        *, intent: LegacyClaimIntent, principal: ScopedPrincipal, record_id: str,
        scope: SessionScope, relation_scope: RelationScope, action: str, actor_id: str | None,
    ) -> bool:
        try:
            if (
                loaded is None or type(intent) is not LegacyClaimIntent
                or type(principal) is not ScopedPrincipal or type(scope) is not SessionScope
                or type(relation_scope) is not RelationScope or action != LEGACY_CLAIM_ACTION
                or intent.action != LEGACY_CLAIM_ACTION or principal != intent.principal
                or record_id != intent.record_id or scope != intent.scope
                or relation_scope != intent.relation_scope
            ):
                return False
            revision, _views, claims = loaded
            if revision != intent.document_revision:
                return False
            matches = tuple(
                grant for grant in claims
                if grant.grant_id == intent.grant_id and grant.grant_revision == intent.grant_revision
            )
            if len(matches) != 1:
                return False
            grant = matches[0]
            if (
                not self._active(grant, self._clock_ms()) or grant.principal != principal
                or grant.record_id != record_id or grant.scope != scope
                or grant.relation_scope != relation_scope or grant.action != action
                or grant.audit_id != intent.audit_id
            ):
                return False
            if actor_id is None:
                return True
            return hmac.compare_digest(grant.actor_binding, self._actor_binding(actor_id))
        except (AttributeError, TypeError, ValueError):
            return False


__all__ = [
    "LEGACY_CLAIM_ACTION",
    "LegacyClaimAuthority",
    "LegacyClaimGrant",
    "LegacyClaimIntent",
    "LegacyInventoryViewGrant",
]
