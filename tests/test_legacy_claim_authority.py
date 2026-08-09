"""Fail-closed durable authority for explicit legacy claim migration."""

from __future__ import annotations

from dataclasses import replace

import pytest

from sylanne_alpha.scope_contracts import (
    BotRef,
    PersonaRevisionRef,
    RelationRef,
    RelationScope,
    ScopeApiPathEcho,
    ScopedPrincipal,
    SessionRef,
    SessionScope,
)
from sylanne_alpha.scope_repository import ScopeRepository


def _scope(*, generation: int = 0) -> SessionScope:
    bot = BotRef(token="bot_v1_legacy", generation=generation)
    persona = PersonaRevisionRef(
        token="persona_v1_legacy",
        bot_ref=bot,
        persona_id_digest="a" * 64,
        source_fingerprint="b" * 64,
        lifecycle_generation=generation,
    )
    return SessionScope(
        bot_ref=bot,
        persona_ref=persona,
        session_ref=SessionRef(
            token="session_v1_legacy", bot_ref=bot, generation=generation
        ),
        storage_token="scope_v1_legacy",
        scope_generation=generation,
    )


def _relation(scope: SessionScope, *, token: str = "relation_v1_legacy") -> RelationScope:
    return RelationScope(
        bot_ref=scope.bot_ref,
        persona_ref=scope.persona_ref,
        relation_ref=RelationRef(token=token, bot_ref=scope.bot_ref),
        relation_generation=scope.scope_generation,
    )


def _path(scope: SessionScope) -> ScopeApiPathEcho:
    return ScopeApiPathEcho(
        bot_ref=scope.bot_ref.token,
        persona_ref=scope.persona_ref.token,
        session_ref=scope.session_ref.token,
    )


def _claim_grant(authority, principal, scope, relation, *, record_id="c" * 64, actor_id="actor-1", **changes):
    return replace(
        authority.enroll_claim_grant(
            principal=principal,
            scope=scope,
            relation_scope=relation,
            record_id=record_id,
            actor_id=actor_id,
            audit_id="audit_v1_claim",
        ),
        **changes,
    )


def test_missing_acl_and_hostile_or_stale_claim_variants_fail_closed(tmp_path) -> None:
    from sylanne_alpha.legacy_claim_authority import LegacyClaimAuthority

    authority = LegacyClaimAuthority(ScopeRepository(tmp_path), clock_ms=lambda: 1_000)
    scope = _scope()
    relation = _relation(scope)
    path = _path(scope)
    principal = ScopedPrincipal("principal_v1_admin")

    assert authority.inventory_view_allowed(principal) is False
    assert authority.preflight_claim(principal, "c" * 64, path) is None

    grant = _claim_grant(authority, principal, scope, relation)
    authority.replace_grants(inventory_grants=(), claim_grants=(grant,))
    intent = authority.preflight_claim(principal, "c" * 64, path)
    assert intent is not None
    assert authority.preflight_claim(ScopedPrincipal("principal_v1_other"), "c" * 64, path) is None
    assert authority.preflight_claim(principal, "d" * 64, path) is None
    assert authority.revalidate_claim(
        intent,
        principal=principal,
        record_id="c" * 64,
        scope=scope,
        relation_scope=relation,
        action="POST:legacy-claim",
        actor_id="actor-1",
    ) is True
    assert authority.revalidate_claim(
        intent,
        principal=principal,
        record_id="c" * 64,
        scope=scope,
        relation_scope=relation,
        action="GET:legacy-claim",
        actor_id="actor-1",
    ) is False
    assert authority.revalidate_claim(
        intent,
        principal=principal,
        record_id="c" * 64,
        scope=replace(scope, scope_generation=1),
        relation_scope=relation,
        action="POST:legacy-claim",
        actor_id="actor-1",
    ) is False
    assert authority.revalidate_claim(
        intent,
        principal=principal,
        record_id="c" * 64,
        scope=scope,
        relation_scope=replace(relation, relation_generation=1),
        action="POST:legacy-claim",
        actor_id="actor-1",
    ) is False
    assert authority.revalidate_claim(
        intent,
        principal=principal,
        record_id="c" * 64,
        scope=scope,
        relation_scope=relation,
        action="POST:legacy-claim",
        actor_id="actor-2",
    ) is False

    authority.replace_grants(
        inventory_grants=(),
        claim_grants=(replace(grant, revoked=True),),
    )
    assert authority.revalidate_claim(
        intent,
        principal=principal,
        record_id="c" * 64,
        scope=scope,
        relation_scope=relation,
        action="POST:legacy-claim",
        actor_id="actor-1",
    ) is False


def test_claim_replacement_expiry_and_ambiguous_relation_invalidate_prior_intent(tmp_path) -> None:
    from sylanne_alpha.legacy_claim_authority import LegacyClaimAuthority

    clock = [1_000]
    authority = LegacyClaimAuthority(ScopeRepository(tmp_path), clock_ms=lambda: clock[0])
    scope = _scope()
    relation = _relation(scope)
    path = _path(scope)
    principal = ScopedPrincipal("principal_v1_admin")
    grant = _claim_grant(authority, principal, scope, relation, expires_at_ms=1_001)
    authority.replace_grants(inventory_grants=(), claim_grants=(grant,))
    intent = authority.preflight_claim(principal, "c" * 64, path)
    assert intent is not None
    authority.replace_grants(inventory_grants=(), claim_grants=(grant,))
    assert authority.revalidate_claim(
        intent,
        principal=principal,
        record_id="c" * 64,
        scope=scope,
        relation_scope=relation,
        action="POST:legacy-claim",
        actor_id="actor-1",
    ) is False
    clock[0] = 1_001
    assert authority.preflight_claim(principal, "c" * 64, path) is None

    clock[0] = 1_000
    alternate = _claim_grant(
        authority,
        principal,
        scope,
        _relation(scope, token="relation_v1_second"),
        audit_id="audit_v1_second",
    )
    authority.replace_grants(inventory_grants=(), claim_grants=(grant, alternate))
    assert authority.relation_for_scope_action(principal, scope, "POST:legacy-claim") is None
    assert authority.preflight_claim(principal, "c" * 64, path) is None


def test_inventory_view_grant_is_explicit_revocable_and_does_not_persist_raw_actor(tmp_path) -> None:
    from sylanne_alpha.legacy_claim_authority import LegacyClaimAuthority

    repository = ScopeRepository(tmp_path)
    authority = LegacyClaimAuthority(repository, clock_ms=lambda: 1_000)
    principal = ScopedPrincipal("principal_v1_admin")
    inventory = authority.enroll_inventory_view_grant(
        principal=principal,
        audit_id="audit_v1_inventory",
    )
    authority.replace_grants(inventory_grants=(inventory,), claim_grants=())
    assert authority.inventory_view_allowed(principal) is True
    scope = _scope()
    claim = _claim_grant(authority, principal, scope, _relation(scope))
    authority.replace_grants(inventory_grants=(inventory,), claim_grants=(claim,))
    raw = repository.legacy_claim_authority_path.read_text(encoding="utf-8")
    assert "actor-1" not in raw
    authority.replace_grants(
        inventory_grants=(replace(inventory, revoked=True),), claim_grants=()
    )
    assert authority.inventory_view_allowed(principal) is False


def test_malformed_or_noncanonical_authority_document_never_grants(tmp_path) -> None:
    from sylanne_alpha.legacy_claim_authority import LegacyClaimAuthority

    repository = ScopeRepository(tmp_path)
    authority = LegacyClaimAuthority(repository, clock_ms=lambda: 1_000)
    principal = ScopedPrincipal("principal_v1_admin")
    repository.legacy_claim_authority_path.parent.mkdir(parents=True, exist_ok=True)
    repository.legacy_claim_authority_path.write_text(
        '{"schema_version":"sylanne.legacy-claim-authority.v1","document_revision":1,"inventory_grants":[],"claim_grants":[],"unknown":true}',
        encoding="utf-8",
    )

    assert authority.inventory_view_allowed(principal) is False


def test_revalidation_rejects_forged_intent_audit_or_action_binding(tmp_path) -> None:
    from sylanne_alpha.legacy_claim_authority import LegacyClaimAuthority, LegacyClaimIntent

    authority = LegacyClaimAuthority(ScopeRepository(tmp_path), clock_ms=lambda: 1_000)
    scope = _scope()
    relation = _relation(scope)
    principal = ScopedPrincipal("principal_v1_admin")
    grant = _claim_grant(authority, principal, scope, relation)
    authority.replace_grants(inventory_grants=(), claim_grants=(grant,))
    intent = authority.preflight_claim(principal, "c" * 64, _path(scope))
    assert intent is not None

    forged_audit = replace(intent, audit_id="audit_v1_forged")
    assert authority.revalidate_claim(
        forged_audit,
        principal=principal,
        record_id="c" * 64,
        scope=scope,
        relation_scope=relation,
        action="POST:legacy-claim",
        actor_id="actor-1",
    ) is False
    with pytest.raises(ValueError, match="intent action"):
        LegacyClaimIntent(
            document_revision=intent.document_revision,
            grant_id=intent.grant_id,
            grant_revision=intent.grant_revision,
            audit_id=intent.audit_id,
            principal=intent.principal,
            record_id=intent.record_id,
            scope=intent.scope,
            relation_scope=intent.relation_scope,
            action="GET:legacy-claim",
        )
