"""Transport-neutral safe projections for the legacy claim hosts."""

from __future__ import annotations

from types import SimpleNamespace

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


def _scope() -> SessionScope:
    bot = BotRef(token="bot_v1_api", generation=0)
    persona = PersonaRevisionRef(
        token="persona_v1_api", bot_ref=bot, persona_id_digest="a" * 64,
        source_fingerprint="b" * 64, lifecycle_generation=0,
    )
    return SessionScope(
        bot_ref=bot, persona_ref=persona,
        session_ref=SessionRef(token="session_v1_api", bot_ref=bot, generation=0),
        storage_token="scope_v1_api", scope_generation=0,
    )


def _relation(scope: SessionScope) -> RelationScope:
    return RelationScope(
        bot_ref=scope.bot_ref, persona_ref=scope.persona_ref,
        relation_ref=RelationRef(token="relation_v1_api", bot_ref=scope.bot_ref),
        relation_generation=0,
    )


class _Claims:
    def __init__(self, repository: ScopeRepository | None = None) -> None:
        self.list_calls = 0
        self.lookup_calls = 0
        self.issue_calls = 0
        self.claim_calls = 0
        self.repository = repository

    def list_inventory(self):
        self.list_calls += 1
        return (
            SimpleNamespace(record_id="a" * 64, source_kind="memory", checksum="b" * 64, byte_size=7, actor_id="secret"),
        )

    def lookup_memory_source(self, _record_id):
        self.lookup_calls += 1
        return SimpleNamespace(actor_id="actor-1", source_fingerprint="c" * 64)

    def issue_destination(self, scope, *, actor_id):
        self.issue_calls += 1
        return SimpleNamespace(scope=scope, actor_id=actor_id)

    def claim_memory(self, _destination, _source, *, authorization_guard):
        self.claim_calls += 1
        if self.repository is None:
            assert authorization_guard() is True
        else:
            with self.repository.transaction():
                assert authorization_guard() is True
        return SimpleNamespace(idempotent=False, recovered=False)


def test_inventory_acl_runs_before_listing_and_whitelists_fields(tmp_path) -> None:
    from sylanne_alpha.legacy_claim_api import LegacyClaimApi, LegacyClaimApiError
    from sylanne_alpha.legacy_claim_authority import LegacyClaimAuthority

    authority = LegacyClaimAuthority(ScopeRepository(tmp_path), clock_ms=lambda: 1_000)
    claims = _Claims()
    api = LegacyClaimApi(authority, claims)
    principal = ScopedPrincipal("principal_v1_admin")

    denied = api.inventory_payload(principal)
    assert isinstance(denied, LegacyClaimApiError)
    assert denied.status == 403
    assert claims.list_calls == 0

    view = authority.enroll_inventory_view_grant(principal=principal, audit_id="audit_v1_view")
    authority.replace_grants(inventory_grants=(view,), claim_grants=())
    assert api.inventory_payload(principal) == {
        "ok": True,
        "records": [{"record_id": "a" * 64, "source_kind": "memory", "checksum": "b" * 64, "byte_size": 7}],
    }
    assert claims.list_calls == 1


def test_claim_preflight_rejects_before_legacy_side_effects(tmp_path) -> None:
    from sylanne_alpha.legacy_claim_api import LegacyClaimApi, LegacyClaimApiError
    from sylanne_alpha.legacy_claim_authority import LegacyClaimAuthority

    authority = LegacyClaimAuthority(ScopeRepository(tmp_path), clock_ms=lambda: 1_000)
    claims = _Claims()
    api = LegacyClaimApi(authority, claims)
    scope = _scope()
    path = ScopeApiPathEcho(scope.bot_ref.token, scope.persona_ref.token, scope.session_ref.token)
    result = api.preflight(ScopedPrincipal("principal_v1_no_grant"), "c" * 64, path)

    assert isinstance(result, LegacyClaimApiError)
    assert result.status == 403
    assert (claims.lookup_calls, claims.issue_calls, claims.claim_calls) == (0, 0, 0)


def test_exact_claim_returns_only_scope_safe_status_after_authorization(tmp_path) -> None:
    from sylanne_alpha.legacy_claim_api import LegacyClaimApi
    from sylanne_alpha.legacy_claim_authority import LegacyClaimAuthority

    repository = ScopeRepository(tmp_path)
    scope = repository.create_scope(_scope(), expected_absent=True)
    relation = repository.create_relation_scope(_relation(scope), expected_absent=True)
    authority = LegacyClaimAuthority(repository, clock_ms=lambda: 1_000)
    claims = _Claims(repository)
    api = LegacyClaimApi(authority, claims)
    principal = ScopedPrincipal("principal_v1_admin")
    grant = authority.enroll_claim_grant(
        principal=principal,
        scope=scope,
        relation_scope=relation,
        record_id="c" * 64,
        actor_id="actor-1",
        audit_id="audit_v1_claim",
    )
    authority.replace_grants(inventory_grants=(), claim_grants=(grant,))
    intent = api.preflight(
        principal,
        "c" * 64,
        ScopeApiPathEcho(scope.bot_ref.token, scope.persona_ref.token, scope.session_ref.token),
    )

    assert api.claim_after_authorization(
        intent,
        principal=principal,
        record_id="c" * 64,
        scope=scope,
        relation_scope=relation,
        post_lookup_revalidate=lambda: True,
        runtime_fence=lambda: True,
    ) == {"ok": True, "claim": {"record_id": "c" * 64, "status": "copied"}}
    assert (claims.lookup_calls, claims.issue_calls, claims.claim_calls) == (1, 1, 1)


def test_post_lookup_runtime_fence_aborts_before_destination_write(tmp_path) -> None:
    from sylanne_alpha.legacy_claim_api import LegacyClaimApi, LegacyClaimApiError
    from sylanne_alpha.legacy_claim_authority import LegacyClaimAuthority

    repository = ScopeRepository(tmp_path)
    scope = repository.create_scope(_scope(), expected_absent=True)
    relation = repository.create_relation_scope(_relation(scope), expected_absent=True)
    authority = LegacyClaimAuthority(repository, clock_ms=lambda: 1_000)
    claims = _Claims(repository)
    api = LegacyClaimApi(authority, claims)
    principal = ScopedPrincipal("principal_v1_runtime_fence")
    grant = authority.enroll_claim_grant(
        principal=principal,
        scope=scope,
        relation_scope=relation,
        record_id="c" * 64,
        actor_id="actor-1",
        audit_id="audit_v1_runtime_fence",
    )
    authority.replace_grants(inventory_grants=(), claim_grants=(grant,))
    intent = api.preflight(
        principal,
        "c" * 64,
        ScopeApiPathEcho(scope.bot_ref.token, scope.persona_ref.token, scope.session_ref.token),
    )

    result = api.claim_after_authorization(
        intent,
        principal=principal,
        record_id="c" * 64,
        scope=scope,
        relation_scope=relation,
        post_lookup_revalidate=lambda: False,
        runtime_fence=lambda: True,
    )

    assert isinstance(result, LegacyClaimApiError)
    assert (result.status, result.code) == (409, "scope_stale")
    assert (claims.lookup_calls, claims.issue_calls, claims.claim_calls) == (1, 0, 0)


def test_locked_claim_fence_rejects_a_retired_durable_relation(tmp_path) -> None:
    from sylanne_alpha.legacy_claim_authority import LEGACY_CLAIM_ACTION, LegacyClaimAuthority

    repository = ScopeRepository(tmp_path)
    scope = repository.create_scope(_scope(), expected_absent=True)
    relation = repository.create_relation_scope(_relation(scope), expected_absent=True)
    authority = LegacyClaimAuthority(repository, clock_ms=lambda: 1_000)
    principal = ScopedPrincipal("principal_v1_retired_relation")
    grant = authority.enroll_claim_grant(
        principal=principal,
        scope=scope,
        relation_scope=relation,
        record_id="c" * 64,
        actor_id="actor-1",
        audit_id="audit_v1_retired_relation",
    )
    authority.replace_grants(inventory_grants=(), claim_grants=(grant,))
    intent = authority.preflight_claim(
        principal,
        "c" * 64,
        ScopeApiPathEcho(scope.bot_ref.token, scope.persona_ref.token, scope.session_ref.token),
    )
    assert intent is not None
    with repository.transaction():
        assert authority.revalidate_claim_locked(
            intent,
            principal=principal,
            record_id="c" * 64,
            scope=scope,
            relation_scope=relation,
            action=LEGACY_CLAIM_ACTION,
            actor_id="actor-1",
        )

    repository.retire_persona_revision(
        scope.persona_ref,
        expected_lifecycle_generation=scope.persona_ref.lifecycle_generation,
        reason="test-retire-relation",
    )

    with repository.transaction():
        assert not authority.revalidate_claim_locked(
            intent,
            principal=principal,
            record_id="c" * 64,
            scope=scope,
            relation_scope=relation,
            action=LEGACY_CLAIM_ACTION,
            actor_id="actor-1",
        )
