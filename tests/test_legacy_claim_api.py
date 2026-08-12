"""Transport-neutral safe projections for the legacy claim hosts."""

from __future__ import annotations

import json
from types import SimpleNamespace

from sylanne_alpha.scope_contracts import (
    AuthenticatedSubject,
    BotRef,
    PersonaRevisionRef,
    RelationRef,
    RelationScope,
    ResolvedTransportScope,
    ScopeApiPathEcho,
    ScopedPrincipal,
    SessionRef,
    SessionScope,
)
from sylanne_alpha.scope_repository import ScopeRepository
from sylanne_alpha.scope_runtime import ScopeRuntimeRegistry
from tests.scope_fixtures import scope_storage_token


def _scope() -> SessionScope:
    bot = BotRef(token="bot_v1_api", generation=0)
    persona = PersonaRevisionRef(
        token="persona_v1_api", bot_ref=bot, persona_id_digest="a" * 64,
        source_fingerprint="b" * 64, lifecycle_generation=0,
    )
    return SessionScope(
        bot_ref=bot, persona_ref=persona,
        session_ref=SessionRef(token="session_v1_api", bot_ref=bot, generation=0),
        storage_token=scope_storage_token("legacy-claim-api"), scope_generation=0,
    )


def _relation(scope: SessionScope) -> RelationScope:
    return RelationScope(
        bot_ref=scope.bot_ref, persona_ref=scope.persona_ref,
        relation_ref=RelationRef(token="relation_v1_api", bot_ref=scope.bot_ref),
        relation_generation=0,
    )


def _runtime_fenced_claim_stack(tmp_path, *, lock_timeout_seconds: float = 2.0):
    """Build real copy services around a SessionCatalog-shaped turn lookup."""

    from sylanne_alpha.legacy_claim_api import LegacyClaimApi
    from sylanne_alpha.legacy_claim_authority import LegacyClaimAuthority
    from sylanne_alpha.legacy_scope_claim import LegacyScopeClaimService
    from sylanne_alpha.memory_system import MemorySystem
    from sylanne_alpha.scope_identity import BotBinding, load_or_create_scope_identity_key
    from sylanne_alpha.scoped_api import (
        ScopedApiAuthorization,
        ScopedApiRequest,
        ScopedApiService,
    )
    from sylanne_alpha.session_catalog import ProtectedDeliveryBinding, SessionCatalog

    repository = ScopeRepository(
        tmp_path,
        lock_timeout_seconds=lock_timeout_seconds,
    )
    catalog = SessionCatalog(repository)
    binding_generation = catalog.binding_generation(
        "private-platform-id",
        "private-self-id",
    )
    identity = load_or_create_scope_identity_key(repository.root / "identity.key")
    bot = identity.bot_ref(
        BotBinding(
            platform_id="private-platform-id",
            self_id="private-self-id",
        ),
        binding_generation,
    )
    template = _scope()
    scope = repository.create_scope(
        SessionScope(
            bot_ref=bot,
            persona_ref=PersonaRevisionRef(
                token=template.persona_ref.token,
                bot_ref=bot,
                persona_id_digest=template.persona_ref.persona_id_digest,
                source_fingerprint=template.persona_ref.source_fingerprint,
                lifecycle_generation=template.persona_ref.lifecycle_generation,
            ),
            session_ref=SessionRef(
                token=template.session_ref.token,
                bot_ref=bot,
                generation=template.session_ref.generation,
            ),
            storage_token=template.storage_token,
            scope_generation=template.scope_generation,
        ),
        expected_absent=True,
    )
    transport = ResolvedTransportScope(
        bot_ref=scope.bot_ref,
        session_ref=scope.session_ref,
        identity_quality="event_get_sender_id",
        private_scope_enabled=True,
        disabled_reason=None,
    )
    binding = ProtectedDeliveryBinding(
        platform_id="private-platform-id",
        self_id="private-self-id",
        message_session="private:FriendMessage:42",
        target_address="private-target-address",
        adapter_capability="reactive_only",
        account_proof_digest="proof-v1",
        account_proof_generation=0,
        account_proof_expires_at_ms=100_000,
        binding_generation=binding_generation,
    )
    frozen = catalog.freeze_persona(catalog.begin_turn(transport, binding), scope)
    assert frozen.turn_generation == 1
    registry = ScopeRuntimeRegistry.for_test(repository=repository)
    registry.exact_session(scope)
    relation_runtime = registry.relation_for(
        scope,
        AuthenticatedSubject(
            relation_ref=RelationRef(
                token="relation_v1_final_turn_fence",
                bot_ref=scope.bot_ref,
            ),
            identity_quality="event_get_sender_id",
        ),
    )
    assert relation_runtime is not None
    state = {
        "inside_final_guard": False,
        "reentrant_lookup": False,
        "locked_fence_calls": 0,
    }

    def session_catalog_current_exact(candidate: SessionScope) -> object | None:
        assert candidate == scope
        if state["inside_final_guard"]:
            state["reentrant_lookup"] = True
            raise AssertionError("SessionCatalog.current_exact re-entered its repository")
        return catalog.current_exact(candidate.bot_ref.token, candidate.session_ref.token)

    def session_catalog_turn_fence_locked(
        candidate: SessionScope,
        generation: int,
    ) -> bool:
        assert candidate == scope
        state["locked_fence_calls"] += 1
        return catalog.turn_fence_locked(candidate, generation)

    principal = ScopedPrincipal("principal_v1_final_turn_fence")

    def grant(
        candidate_principal: ScopedPrincipal,
        candidate_scope: SessionScope,
        action: str,
    ) -> RelationScope | None:
        if (
            candidate_principal == principal
            and candidate_scope == scope
            and action == "POST:legacy-claim"
        ):
            return relation_runtime.scope
        return None

    gate = ScopedApiService(
        repository,
        registry,
        turn_lookup=session_catalog_current_exact,
        turn_fence_locked=session_catalog_turn_fence_locked,
        clock_ms=lambda: 1_000,
        principal_scope_grant=grant,
        principal_persona_grant=lambda *_args: None,
    )
    claims = LegacyScopeClaimService(repository)
    source = claims.inventory_memory(
        actor_id="actor-1",
        source_id="manual-export-001",
        payload=MemorySystem().to_dict(),
    )
    authority = LegacyClaimAuthority(repository, clock_ms=lambda: 1_000)
    acl_grant = authority.enroll_claim_grant(
        principal=principal,
        scope=scope,
        relation_scope=relation_runtime.scope,
        record_id=source.source_fingerprint,
        actor_id="actor-1",
        audit_id="audit_v1_final_turn_fence",
    )
    authority.replace_grants(inventory_grants=(), claim_grants=(acl_grant,))
    api = LegacyClaimApi(authority, claims)
    intent = api.preflight(
        principal,
        source.source_fingerprint,
        ScopeApiPathEcho(scope.bot_ref.token, scope.persona_ref.token, scope.session_ref.token),
    )
    assert not hasattr(intent, "status")
    nonce = gate.issue_nonce(
        scope,
        relation_runtime.scope,
        turn_generation=1,
        principal=principal,
        endpoint="legacy-claim",
        method="POST",
    )
    authorization = gate.authorize(
        ScopedApiRequest.from_tokens(
            bot_ref=scope.bot_ref.token,
            persona_ref=scope.persona_ref.token,
            session_ref=scope.session_ref.token,
            nonce=nonce,
            endpoint="legacy-claim",
            method="POST",
            principal=principal,
        )
    )
    assert isinstance(authorization, ScopedApiAuthorization)
    checked = gate.revalidate(authorization)
    assert isinstance(checked, ScopedApiAuthorization)
    return SimpleNamespace(
        api=api,
        authority=authority,
        authorization=checked,
        gate=gate,
        principal=principal,
        relation_scope=relation_runtime.scope,
        repository=repository,
        scope=scope,
        source=source,
        state=state,
        catalog=catalog,
        transport=transport,
        binding=binding,
        intent=intent,
        registry=registry,
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


def _repository_file_snapshot(repository: ScopeRepository) -> dict[str, bytes]:
    return {
        path.relative_to(repository.root).as_posix(): path.read_bytes()
        for path in repository.root.rglob("*")
        if path.is_file()
    }


def _assert_claim_failure_left_no_artifacts(
    stack: SimpleNamespace,
    before: dict[str, bytes],
) -> None:
    assert _repository_file_snapshot(stack.repository) == before
    assert not stack.repository.component_path(stack.scope, "memory").exists()
    assert not (stack.repository.legacy_unscoped_root / "staging").exists()
    assert not (stack.repository.legacy_unscoped_root / "quarantine").exists()


def test_stale_scope_from_claim_memory_returns_redacted_conflict_without_retry(
    tmp_path,
    monkeypatch,
) -> None:
    from sylanne_alpha.legacy_claim_api import LegacyClaimApiError
    from sylanne_alpha.scope_repository import StaleScopeWrite

    stack = _runtime_fenced_claim_stack(tmp_path)
    before = _repository_file_snapshot(stack.repository)
    before_manifest = json.loads(
        stack.repository.legacy_unscoped_manifest_path.read_text(encoding="utf-8")
    )
    target = stack.repository.component_path(stack.scope, "memory")
    original_write = stack.repository._write_snapshot_locked
    calls = {"target": 0}

    def stale_target_write(path, *, expected_generation, payload):
        if path == target:
            calls["target"] += 1
            raise StaleScopeWrite(
                stack.scope.scope_generation,
                stack.scope.scope_generation + 1,
                code="scope_generation_stale_sensitive_detail",
            )
        return original_write(
            path,
            expected_generation=expected_generation,
            payload=payload,
        )

    monkeypatch.setattr(
        stack.repository,
        "_write_snapshot_locked",
        stale_target_write,
    )
    result = stack.api.claim_after_authorization(
        stack.intent,
        principal=stack.principal,
        record_id=stack.source.source_fingerprint,
        scope=stack.scope,
        relation_scope=stack.relation_scope,
        post_lookup_revalidate=lambda: True,
        runtime_fence=lambda: True,
    )

    assert isinstance(result, LegacyClaimApiError)
    assert result.public_payload() == {"error": "scope_stale"}
    assert (result.status, result.code) == (409, "scope_stale")
    assert calls == {"target": 1}
    after = _repository_file_snapshot(stack.repository)
    after_manifest = json.loads(
        stack.repository.legacy_unscoped_manifest_path.read_text(encoding="utf-8")
    )
    assert set(after) == set(before)
    assert after_manifest["inventory"] == before_manifest["inventory"]
    assert after_manifest["claims"] == before_manifest["claims"] == {}
    assert after_manifest["generation"] == before_manifest["generation"] + 2
    assert not target.exists()
    staging = stack.repository.legacy_unscoped_root / "staging"
    if staging.exists():
        assert tuple(staging.glob("*.stage")) == ()
    assert not (stack.repository.legacy_unscoped_root / "quarantine").exists()


def test_claim_lock_failure_returns_redacted_unavailable_without_retry(tmp_path) -> None:
    from sylanne_alpha.legacy_claim_api import LegacyClaimApiError

    stack = _runtime_fenced_claim_stack(tmp_path, lock_timeout_seconds=0.0)
    before = _repository_file_snapshot(stack.repository)
    calls = {"claim": 0}
    original_claim = stack.api.claims.claim_memory
    competing = ScopeRepository(stack.repository.root)

    def locked_claim(*args, **kwargs):
        calls["claim"] += 1
        with competing.transaction():
            return original_claim(*args, **kwargs)

    stack.api.claims.claim_memory = locked_claim
    result = stack.api.claim_after_authorization(
        stack.intent,
        principal=stack.principal,
        record_id=stack.source.source_fingerprint,
        scope=stack.scope,
        relation_scope=stack.relation_scope,
        post_lookup_revalidate=lambda: True,
        runtime_fence=lambda: True,
    )

    assert isinstance(result, LegacyClaimApiError)
    assert result.public_payload() == {"error": "scope_repository_unavailable"}
    assert (result.status, result.code) == (503, "scope_repository_unavailable")
    assert calls == {"claim": 1}
    _assert_claim_failure_left_no_artifacts(stack, before)


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


def test_final_runtime_guard_never_reenters_session_catalog_repository_lock(tmp_path) -> None:
    """A real copy succeeds when current_exact would lock its repository."""

    from sylanne_alpha.scoped_api import ScopedApiAuthorization

    stack = _runtime_fenced_claim_stack(tmp_path)

    def final_runtime_fence() -> bool:
        stack.state["inside_final_guard"] = True
        try:
            return stack.gate.runtime_fence(stack.authorization)
        finally:
            stack.state["inside_final_guard"] = False

    result = stack.api.claim_after_authorization(
        stack.api.preflight(
            stack.principal,
            stack.source.source_fingerprint,
            ScopeApiPathEcho(
                stack.scope.bot_ref.token,
                stack.scope.persona_ref.token,
                stack.scope.session_ref.token,
            ),
        ),
        principal=stack.principal,
        record_id=stack.source.source_fingerprint,
        scope=stack.scope,
        relation_scope=stack.relation_scope,
        post_lookup_revalidate=lambda: isinstance(
            stack.gate.revalidate(stack.authorization), ScopedApiAuthorization
        ),
        runtime_fence=final_runtime_fence,
    )

    assert result == {
        "ok": True,
        "claim": {"record_id": stack.source.source_fingerprint, "status": "copied"},
    }
    assert stack.state["reentrant_lookup"] is False
    assert stack.repository.read_component(stack.scope, "memory") is not None


def test_new_published_turn_after_lookup_blocks_the_final_target_write(tmp_path) -> None:
    """A newer resolving turn revokes an old authorization before target publish."""

    from sylanne_alpha.legacy_claim_api import LegacyClaimApiError
    from sylanne_alpha.scoped_api import ScopedApiAuthorization

    stack = _runtime_fenced_claim_stack(tmp_path)
    published = {"newer_turn": False}

    def post_lookup_revalidate_then_begin_next_turn() -> bool:
        if not isinstance(stack.gate.revalidate(stack.authorization), ScopedApiAuthorization):
            return False
        published["newer_turn"] = stack.registry.publish_frozen_turn(
            stack.scope,
            8,
        )
        return published["newer_turn"]

    def final_runtime_fence() -> bool:
        stack.state["inside_final_guard"] = True
        try:
            return stack.gate.runtime_fence(stack.authorization)
        finally:
            stack.state["inside_final_guard"] = False

    result = stack.api.claim_after_authorization(
        stack.api.preflight(
            stack.principal,
            stack.source.source_fingerprint,
            ScopeApiPathEcho(
                stack.scope.bot_ref.token,
                stack.scope.persona_ref.token,
                stack.scope.session_ref.token,
            ),
        ),
        principal=stack.principal,
        record_id=stack.source.source_fingerprint,
        scope=stack.scope,
        relation_scope=stack.relation_scope,
        post_lookup_revalidate=post_lookup_revalidate_then_begin_next_turn,
        runtime_fence=final_runtime_fence,
    )

    assert published["newer_turn"] is True
    assert isinstance(result, LegacyClaimApiError)
    assert (result.status, result.code) == (409, "scope_stale")
    assert stack.state["reentrant_lookup"] is False
    assert stack.repository.read_component(stack.scope, "memory") is None


def test_new_durable_turn_after_lookup_blocks_target_without_local_snapshot_update(
    tmp_path,
) -> None:
    """A different process can advance the durable catalog after local revalidation."""

    from sylanne_alpha.legacy_claim_api import LegacyClaimApiError
    from sylanne_alpha.scoped_api import ScopedApiAuthorization
    from sylanne_alpha.session_catalog import SessionCatalog

    stack = _runtime_fenced_claim_stack(tmp_path)
    remote_repository = ScopeRepository(stack.repository.root)
    remote_catalog = SessionCatalog(remote_repository)

    def post_lookup_revalidate_then_other_process_writes_turn() -> bool:
        if not isinstance(stack.gate.revalidate(stack.authorization), ScopedApiAuthorization):
            return False
        # This deliberately bypasses the local runtime registry, as a separate
        # process would.  Only the shared owner-only catalog can see it.
        newer = remote_catalog.begin_turn(stack.transport, stack.binding)
        assert newer.turn_generation == 2 and newer.turn_state == "resolving"
        return True

    def final_runtime_fence() -> bool:
        stack.state["inside_final_guard"] = True
        try:
            return stack.gate.runtime_fence(stack.authorization)
        finally:
            stack.state["inside_final_guard"] = False

    result = stack.api.claim_after_authorization(
        stack.api.preflight(
            stack.principal,
            stack.source.source_fingerprint,
            ScopeApiPathEcho(
                stack.scope.bot_ref.token,
                stack.scope.persona_ref.token,
                stack.scope.session_ref.token,
            ),
        ),
        principal=stack.principal,
        record_id=stack.source.source_fingerprint,
        scope=stack.scope,
        relation_scope=stack.relation_scope,
        post_lookup_revalidate=post_lookup_revalidate_then_other_process_writes_turn,
        runtime_fence=final_runtime_fence,
    )

    assert isinstance(result, LegacyClaimApiError)
    assert (result.status, result.code) == (409, "scope_stale")
    assert stack.state["locked_fence_calls"] >= 1
    assert stack.state["reentrant_lookup"] is False
    assert stack.repository.read_component(stack.scope, "memory") is None


def test_missing_durable_delivery_binding_blocks_the_final_target_write(tmp_path) -> None:
    """The final catalog fence requires the current protected binding as well."""

    from sylanne_alpha.legacy_claim_api import LegacyClaimApiError
    from sylanne_alpha.scoped_api import ScopedApiAuthorization

    stack = _runtime_fenced_claim_stack(tmp_path)

    def post_lookup_revalidate_then_remove_binding() -> bool:
        if not isinstance(stack.gate.revalidate(stack.authorization), ScopedApiAuthorization):
            return False
        stack.repository.transport_delivery_binding_path(
            stack.scope.bot_ref.token,
            stack.scope.session_ref.token,
        ).unlink()
        return True

    def final_runtime_fence() -> bool:
        stack.state["inside_final_guard"] = True
        try:
            return stack.gate.runtime_fence(stack.authorization)
        finally:
            stack.state["inside_final_guard"] = False

    result = stack.api.claim_after_authorization(
        stack.api.preflight(
            stack.principal,
            stack.source.source_fingerprint,
            ScopeApiPathEcho(
                stack.scope.bot_ref.token,
                stack.scope.persona_ref.token,
                stack.scope.session_ref.token,
            ),
        ),
        principal=stack.principal,
        record_id=stack.source.source_fingerprint,
        scope=stack.scope,
        relation_scope=stack.relation_scope,
        post_lookup_revalidate=post_lookup_revalidate_then_remove_binding,
        runtime_fence=final_runtime_fence,
    )

    assert isinstance(result, LegacyClaimApiError)
    assert (result.status, result.code) == (409, "scope_stale")
    assert stack.state["locked_fence_calls"] >= 1
    assert stack.repository.read_component(stack.scope, "memory") is None


def test_corrupt_durable_binding_returns_unavailable_without_target_write(tmp_path) -> None:
    """A malformed persisted binding is unavailable, not merely a stale turn."""

    from sylanne_alpha.legacy_claim_api import LegacyClaimApiError
    from sylanne_alpha.scoped_api import ScopedApiAuthorization

    stack = _runtime_fenced_claim_stack(tmp_path)

    def post_lookup_revalidate_then_corrupt_binding() -> bool:
        if not isinstance(stack.gate.revalidate(stack.authorization), ScopedApiAuthorization):
            return False
        stack.repository.transport_delivery_binding_path(
            stack.scope.bot_ref.token,
            stack.scope.session_ref.token,
        ).write_text("{", encoding="utf-8")
        return True

    def final_runtime_fence() -> bool:
        stack.state["inside_final_guard"] = True
        try:
            return stack.gate.runtime_fence(stack.authorization)
        finally:
            stack.state["inside_final_guard"] = False

    result = stack.api.claim_after_authorization(
        stack.api.preflight(
            stack.principal,
            stack.source.source_fingerprint,
            ScopeApiPathEcho(
                stack.scope.bot_ref.token,
                stack.scope.persona_ref.token,
                stack.scope.session_ref.token,
            ),
        ),
        principal=stack.principal,
        record_id=stack.source.source_fingerprint,
        scope=stack.scope,
        relation_scope=stack.relation_scope,
        post_lookup_revalidate=post_lookup_revalidate_then_corrupt_binding,
        runtime_fence=final_runtime_fence,
    )

    assert isinstance(result, LegacyClaimApiError)
    assert (result.status, result.code) == (503, "scope_repository_unavailable")
    assert stack.repository.read_component(stack.scope, "memory") is None


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
