"""Scoped WebUI API authorization and generation-fence regressions."""

from __future__ import annotations

import asyncio
import socket
from contextlib import closing
from types import SimpleNamespace
from types import ModuleType
import sys

import pytest

from sylanne_alpha.scope_contracts import (
    AuthenticatedSubject,
    BotRef,
    PersonaScope,
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
from sylanne_alpha.scoped_api import (
    PERSONA_DOSSIER_ROUTE_SPEC,
    SCOPED_API_METHODS,
    SCOPED_API_ROUTE_SPECS,
    PersonaRouteSpec,
    ScopeRouteSpec,
    ScopedApiAuthorization,
    ScopedApiError,
    ScopedApiRequest,
    ScopedApiService,
    scoped_api_route_spec,
    scoped_api_service_for_plugin,
)


def _scope(
    *,
    bot_token: str = "bot_v1_api",
    persona_token: str = "persona_v1_api",
    session_token: str = "session_v1_api",
) -> SessionScope:
    bot = BotRef(token=bot_token, generation=0)
    persona = PersonaRevisionRef(
        token=persona_token,
        bot_ref=bot,
        persona_id_digest="a" * 64,
        source_fingerprint="b" * 64,
        lifecycle_generation=0,
    )
    return SessionScope(
        bot_ref=bot,
        persona_ref=persona,
        session_ref=SessionRef(token=session_token, bot_ref=bot, generation=0),
        storage_token=f"scope_v1_{session_token.rsplit('_', 1)[-1]}",
        scope_generation=0,
    )


def _frozen_turn(scope: SessionScope, *, turn_generation: int = 7) -> object:
    return SimpleNamespace(
        bot_ref=scope.bot_ref.token,
        session_ref=scope.session_ref.token,
        session_generation=scope.session_ref.generation,
        turn_generation=turn_generation,
        turn_state="frozen",
        active_persona_ref=scope.persona_ref.token,
        persona_lifecycle_generation=scope.persona_ref.lifecycle_generation,
        active_scope_token=scope.storage_token,
        scope_generation=scope.scope_generation,
    )


def _service(tmp_path):
    repository = ScopeRepository(tmp_path)
    scope = repository.create_scope(_scope(), expected_absent=True)
    registry = ScopeRuntimeRegistry.for_test(repository=repository)
    registry.exact_session(scope)
    relation = registry.relation_for(
        scope,
        AuthenticatedSubject(
            relation_ref=RelationRef(
                token="relation_v1_scoped_api",
                bot_ref=scope.bot_ref,
            ),
            identity_quality="event_get_sender_id",
        ),
    )
    assert relation is not None
    turn = _frozen_turn(scope)

    def test_grant(
        _principal: ScopedPrincipal,
        candidate: SessionScope,
        _action: str,
    ) -> RelationScope | None:
        return relation.scope if candidate == scope else None

    def test_persona_grant(
        _principal: ScopedPrincipal,
        candidate: PersonaScope,
        _action: str,
    ) -> RelationScope | None:
        if (
            candidate.bot_ref == scope.bot_ref
            and candidate.persona_ref == scope.persona_ref
        ):
            return relation.scope
        return None

    service = ScopedApiService(
        repository,
        registry,
        turn_lookup=lambda candidate: turn if candidate == scope else None,
        turn_fence_locked=lambda candidate, generation: (
            candidate == scope and generation == 7
        ),
        clock_ms=lambda: 1_000,
        principal_scope_grant=test_grant,
        principal_persona_grant=test_persona_grant,
    )
    return service, repository, registry, scope, relation.scope


def _request(scope: SessionScope, nonce: str | None) -> ScopedApiRequest:
    return ScopedApiRequest.from_tokens(
        bot_ref=scope.bot_ref.token,
        persona_ref=scope.persona_ref.token,
        session_ref=scope.session_ref.token,
        nonce=nonce,
        endpoint="state",
        principal=_principal(),
    )


def _principal(token: str = "principal_v1_scoped_api") -> ScopedPrincipal:
    return ScopedPrincipal(token=token)


def test_scoped_route_specs_are_immutable_and_bind_the_method_to_each_action() -> None:
    state = scoped_api_route_spec("state")
    melt = scoped_api_route_spec("memory/meltdown")
    legacy_claim = scoped_api_route_spec("legacy-claim")

    assert state == ScopeRouteSpec(endpoint="state", method="GET")
    assert state.action == "GET:state"
    assert melt.action == "POST:memory/meltdown"
    assert legacy_claim.action == "POST:legacy-claim"
    with pytest.raises(TypeError):
        SCOPED_API_ROUTE_SPECS["state"] = state  # type: ignore[index]


def test_persona_dossier_route_is_immutable_and_owns_its_action() -> None:
    assert PERSONA_DOSSIER_ROUTE_SPEC == PersonaRouteSpec(
        endpoint="dossier",
        method="GET",
    )
    assert PERSONA_DOSSIER_ROUTE_SPEC.action == "GET:persona-dossier"
    with pytest.raises(ValueError):
        PersonaRouteSpec(endpoint="dossier", method="POST")
    with pytest.raises(ValueError):
        PersonaRouteSpec(endpoint="scope", method="GET")
    with pytest.raises(AttributeError):
        PERSONA_DOSSIER_ROUTE_SPEC.method = "POST"  # type: ignore[misc]


def test_scoped_method_and_route_contracts_cannot_mutate_at_runtime() -> None:
    original_method = SCOPED_API_METHODS["state"]
    try:
        with pytest.raises(TypeError):
            SCOPED_API_METHODS["state"] = "POST"  # type: ignore[index]
    finally:
        if type(SCOPED_API_METHODS) is dict:
            SCOPED_API_METHODS["state"] = original_method
    assert scoped_api_route_spec("state").action == "GET:state"
    assert SCOPED_API_METHODS["legacy-claim"] == "POST"


def test_runtime_fence_rejects_a_retired_session_without_reentering_repository(
    tmp_path,
) -> None:
    service, _repository, registry, scope, relation = _service(tmp_path)
    nonce = service.issue_nonce(
        scope,
        relation,
        turn_generation=7,
        principal=_principal(),
        endpoint="legacy-claim",
        method="POST",
    )
    authorized = service.authorize(
        ScopedApiRequest.from_tokens(
            bot_ref=scope.bot_ref.token,
            persona_ref=scope.persona_ref.token,
            session_ref=scope.session_ref.token,
            nonce=nonce,
            endpoint="legacy-claim",
            method="POST",
            principal=_principal(),
        )
    )

    assert isinstance(authorized, ScopedApiAuthorization)
    with _repository.transaction():
        assert service.runtime_fence(authorized)
    registry.release_session(scope)
    with _repository.transaction():
        assert not service.runtime_fence(authorized)


def test_runtime_fence_uses_a_published_turn_without_reentering_repository(
    tmp_path,
) -> None:
    """The final write guard must not call SessionCatalog under its lock."""

    repository = ScopeRepository(tmp_path)
    scope = repository.create_scope(_scope(), expected_absent=True)
    registry = ScopeRuntimeRegistry.for_test(repository=repository)
    registry.exact_session(scope)
    relation_runtime = registry.relation_for(
        scope,
        AuthenticatedSubject(
            relation_ref=RelationRef(
                token="relation_v1_published_turn",
                bot_ref=scope.bot_ref,
            ),
            identity_quality="event_get_sender_id",
        ),
    )
    assert relation_runtime is not None
    state = {"inside_final_guard": False, "reentrant_lookup": False}
    turn = _frozen_turn(scope)

    def production_turn_lookup(candidate: SessionScope) -> object | None:
        assert candidate == scope
        if state["inside_final_guard"]:
            state["reentrant_lookup"] = True
            raise AssertionError("turn lookup re-entered the repository transaction")
        # SessionCatalog.current_exact uses this same repository transaction
        # boundary in production.
        with repository.transaction():
            return turn

    def grant(
        _principal: ScopedPrincipal,
        candidate: SessionScope,
        action: str,
    ) -> RelationScope | None:
        if candidate == scope and action == "POST:legacy-claim":
            return relation_runtime.scope
        return None

    service = ScopedApiService(
        repository,
        registry,
        turn_lookup=production_turn_lookup,
        turn_fence_locked=lambda candidate, generation: (
            candidate == scope and generation == 7
        ),
        clock_ms=lambda: 1_000,
        principal_scope_grant=grant,
        principal_persona_grant=lambda *_args: None,
    )
    principal = _principal("principal_v1_published_turn")
    nonce = service.issue_nonce(
        scope,
        relation_runtime.scope,
        turn_generation=7,
        principal=principal,
        endpoint="legacy-claim",
        method="POST",
    )
    authorized = service.authorize(
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

    assert isinstance(authorized, ScopedApiAuthorization)
    with repository.transaction():
        state["inside_final_guard"] = True
        try:
            assert service.runtime_fence(authorized)
        finally:
            state["inside_final_guard"] = False
    assert state["reentrant_lookup"] is False


def test_new_resolving_transport_turn_advances_and_clears_the_final_fence(tmp_path) -> None:
    """Every new begin_turn publication revokes the old exact authorization."""

    service, _repository, registry, scope, relation = _service(tmp_path)
    principal = _principal("principal_v1_new_resolving_turn")
    nonce = service.issue_nonce(
        scope,
        relation,
        turn_generation=7,
        principal=principal,
        endpoint="legacy-claim",
        method="POST",
    )
    authorized = service.authorize(
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
    assert isinstance(authorized, ScopedApiAuthorization)
    transport = ResolvedTransportScope(
        bot_ref=scope.bot_ref,
        session_ref=scope.session_ref,
        identity_quality="event_get_sender_id",
        private_scope_enabled=True,
        disabled_reason=None,
    )

    assert registry.publish_transport_turn(
        transport,
        SimpleNamespace(
            bot_ref=scope.bot_ref.token,
            session_ref=scope.session_ref.token,
            session_generation=scope.session_ref.generation,
            turn_generation=8,
            turn_state="resolving",
        ),
    )
    with _repository.transaction():
        assert not service.runtime_fence(authorized)
    registry.release_session(scope)
    assert not registry.matches_published_turn(scope, 8)


def test_principal_scope_grant_is_required_and_revalidated_before_relation_runtime(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = ScopeRepository(tmp_path)
    scope = repository.create_scope(_scope(), expected_absent=True)
    registry = ScopeRuntimeRegistry.for_test(repository=repository)
    registry.exact_session(scope)
    relation_runtime = registry.relation_for(
        scope,
        AuthenticatedSubject(
            relation_ref=RelationRef(
                token="relation_v1_grant_owner",
                bot_ref=scope.bot_ref,
            ),
            identity_quality="event_get_sender_id",
        ),
    )
    other_relation_runtime = registry.relation_for(
        scope,
        AuthenticatedSubject(
            relation_ref=RelationRef(
                token="relation_v1_grant_other",
                bot_ref=scope.bot_ref,
            ),
            identity_quality="event_get_sender_id",
        ),
    )
    assert relation_runtime is not None
    assert other_relation_runtime is not None
    owner = _principal("principal_v1_grant_owner")
    arbitrary = _principal("principal_v1_grant_arbitrary")
    grant_state = {"allowed": True}
    grant_calls: list[tuple[ScopedPrincipal, SessionScope, str]] = []

    def grant(
        principal: ScopedPrincipal,
        candidate: SessionScope,
        action: str,
    ) -> RelationScope | None:
        grant_calls.append((principal, candidate, action))
        if (
            grant_state["allowed"]
            and principal == owner
            and candidate == scope
            and action == "GET:state"
        ):
            return relation_runtime.scope
        return None

    service = ScopedApiService(
        repository,
        registry,
        turn_lookup=lambda candidate: _frozen_turn(scope) if candidate == scope else None,
        clock_ms=lambda: 1_000,
        principal_scope_grant=grant,
    )
    nonce = service.issue_nonce(
        scope,
        relation_runtime.scope,
        turn_generation=7,
        principal=owner,
    )
    assert grant_calls[-1] == (owner, scope, "GET:state")

    with pytest.raises(RuntimeError, match="scope_principal_forbidden"):
        service.issue_nonce(
            scope,
            relation_runtime.scope,
            turn_generation=7,
            principal=arbitrary,
        )
    with pytest.raises(RuntimeError, match="scope_principal_forbidden"):
        service.issue_nonce(
            scope,
            other_relation_runtime.scope,
            turn_generation=7,
            principal=owner,
        )

    service._principal_scope_grant = None
    with pytest.raises(RuntimeError, match="scope_principal_forbidden"):
        service.issue_nonce(
            scope,
            relation_runtime.scope,
            turn_generation=7,
            principal=owner,
        )
    service._principal_scope_grant = grant

    grant_state["allowed"] = False
    monkeypatch.setattr(
        repository,
        "validate_relation_scope",
        lambda *_args: (_ for _ in ()).throw(AssertionError("grant denial must precede relation lookup")),
    )
    monkeypatch.setattr(
        registry,
        "relation_or_none",
        lambda *_args: (_ for _ in ()).throw(AssertionError("grant denial must precede runtime lookup")),
    )
    denied = service.authorize(
        ScopedApiRequest.from_tokens(
            bot_ref=scope.bot_ref.token,
            persona_ref=scope.persona_ref.token,
            session_ref=scope.session_ref.token,
            nonce=nonce,
            endpoint="state",
            principal=owner,
        )
    )
    assert isinstance(denied, ScopedApiError)
    assert (denied.status, denied.code) == (403, "scope_principal_forbidden")


def test_principal_scope_grant_revocation_blocks_consume_and_revalidate(tmp_path) -> None:
    service, _repository, _registry, scope, relation = _service(tmp_path)
    principal = _principal()
    granted = {"enabled": True}

    def grant(
        candidate_principal: ScopedPrincipal,
        candidate_scope: SessionScope,
        action: str,
    ) -> RelationScope | None:
        if granted["enabled"] and candidate_principal == principal and candidate_scope == scope:
            return relation
        return None

    service._principal_scope_grant = grant
    consume_nonce = service.issue_nonce(
        scope,
        relation,
        turn_generation=7,
        principal=principal,
    )
    granted["enabled"] = False
    denied_consume = service.authorize(_request(scope, consume_nonce))
    assert isinstance(denied_consume, ScopedApiError)
    assert (denied_consume.status, denied_consume.code) == (403, "scope_principal_forbidden")

    granted["enabled"] = True
    stream_nonce = service.issue_nonce(
        scope,
        relation,
        turn_generation=7,
        principal=principal,
    )
    authorization = service.authorize(_request(scope, stream_nonce))
    assert isinstance(authorization, ScopedApiAuthorization)
    granted["enabled"] = False
    denied_stream = service.revalidate(authorization)
    assert isinstance(denied_stream, ScopedApiError)
    assert (denied_stream.status, denied_stream.code) == (403, "scope_principal_forbidden")


def test_plugin_service_requires_host_principal_scope_grant(tmp_path) -> None:
    repository = ScopeRepository(tmp_path)
    scope = repository.create_scope(_scope(), expected_absent=True)
    registry = ScopeRuntimeRegistry.for_test(repository=repository)
    registry.exact_session(scope)
    resolver = SimpleNamespace(
        _repository=repository,
        catalog=SimpleNamespace(
            current_exact=lambda bot_ref, session_ref: (
                _frozen_turn(scope)
                if (bot_ref, session_ref) == (scope.bot_ref.token, scope.session_ref.token)
                else None
            )
        ),
    )
    plugin = SimpleNamespace(
        _scope_runtime_registry=registry,
        _scope_resolver_v1=resolver,
    )

    assert scoped_api_service_for_plugin(plugin) is None
    plugin._scoped_api_principal_scope_grant = lambda *_args: None
    assert scoped_api_service_for_plugin(plugin) is None
    plugin._scoped_api_principal_persona_grant = lambda *_args: None
    assert isinstance(scoped_api_service_for_plugin(plugin), ScopedApiService)


def _safe_genesis_profile() -> dict[str, object]:
    return {
        "traits_prior": {},
        "voice_prior": {},
        "boundary_prior": {},
        "proactivity_prior": {},
        "circadian_prior": {},
    }


def _dossier_service(tmp_path):
    repository = ScopeRepository(tmp_path)
    scope = repository.create_scope(_scope(), expected_absent=True)
    registry = ScopeRuntimeRegistry.for_test(repository=repository)
    registry.exact_session(scope)
    relation_runtime = registry.relation_for(
        scope,
        AuthenticatedSubject(
            relation_ref=RelationRef(
                token="relation_v1_dossier_owner",
                bot_ref=scope.bot_ref,
            ),
            identity_quality="event_get_sender_id",
        ),
    )
    assert relation_runtime is not None
    principal = _principal("principal_v1_dossier_owner")
    grant_state = {"allowed": True}
    grant_calls: list[tuple[ScopedPrincipal, PersonaScope, str]] = []

    def session_grant(
        _candidate_principal: ScopedPrincipal,
        candidate_scope: SessionScope,
        _action: str,
    ) -> RelationScope | None:
        return relation_runtime.scope if candidate_scope == scope else None

    def persona_grant(
        candidate_principal: ScopedPrincipal,
        candidate_scope: PersonaScope,
        action: str,
    ) -> RelationScope | None:
        grant_calls.append((candidate_principal, candidate_scope, action))
        if (
            grant_state["allowed"]
            and candidate_principal == principal
            and candidate_scope.bot_ref == scope.bot_ref
            and candidate_scope.persona_ref == scope.persona_ref
            and action == "GET:persona-dossier"
        ):
            return relation_runtime.scope
        return None

    service = ScopedApiService(
        repository,
        registry,
        turn_lookup=lambda _candidate: None,
        clock_ms=lambda: 1_000,
        principal_scope_grant=session_grant,
        principal_persona_grant=persona_grant,
    )
    return service, repository, scope, principal, grant_state, grant_calls


def test_persona_dossier_requires_principal_before_reader(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, repository, _registry, scope, _relation = _service(tmp_path)
    monkeypatch.setattr(
        repository,
        "read_persona_dossier",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("principal denial must precede dossier reader")
        ),
    )

    result = service.persona_dossier_payload(
        scope.bot_ref.token,
        scope.persona_ref.token,
    )

    assert isinstance(result, ScopedApiError)
    assert (result.status, result.code) == (403, "scope_principal_required")


def test_persona_dossier_classifies_parent_before_reader(tmp_path, monkeypatch) -> None:
    service, repository, scope, principal, _grant_state, _grant_calls = _dossier_service(tmp_path)
    foreign = repository.create_scope(
        _scope(
            bot_token="bot_v1_other",
            persona_token="persona_v1_foreign",
            session_token="session_v1_other",
        ),
        expected_absent=True,
    )
    monkeypatch.setattr(
        repository,
        "read_persona_dossier",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("parent classification must precede dossier reader")
        ),
    )

    wrong_parent = service.persona_dossier_payload(
        scope.bot_ref.token,
        foreign.persona_ref.token,
        principal=principal,
    )
    missing = service.persona_dossier_payload(
        scope.bot_ref.token,
        "persona_v1_missing",
        principal=principal,
    )
    missing_bot = service.persona_dossier_payload(
        "bot_v1_missing",
        scope.persona_ref.token,
        principal=principal,
    )

    assert isinstance(wrong_parent, ScopedApiError)
    assert (wrong_parent.status, wrong_parent.code) == (403, "scope_persona_not_owned")
    assert isinstance(missing, ScopedApiError)
    assert (missing.status, missing.code) == (404, "scope_persona_not_found")
    assert isinstance(missing_bot, ScopedApiError)
    assert (missing_bot.status, missing_bot.code) == (404, "scope_bot_not_found")


def test_persona_dossier_preserves_retired_persona_as_stale(tmp_path) -> None:
    service, repository, scope, principal, _grant_state, _grant_calls = _dossier_service(tmp_path)
    repository.retire_persona_revision(
        scope.persona_ref,
        expected_lifecycle_generation=scope.persona_ref.lifecycle_generation,
        reason="test",
    )

    result = service.persona_dossier_payload(
        scope.bot_ref.token,
        scope.persona_ref.token,
        principal=principal,
    )

    assert isinstance(result, ScopedApiError)
    assert (result.status, result.code) == (409, "scope_stale")


def test_persona_dossier_grant_echo_and_post_read_revocation(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, repository, scope, principal, grant_state, grant_calls = _dossier_service(tmp_path)

    monkeypatch.setattr(
        repository,
        "list_active_scopes",
        lambda: (_ for _ in ()).throw(
            AssertionError("Persona dossier must not enumerate Session scopes")
        ),
    )
    payload = service.persona_dossier_payload(
        scope.bot_ref.token,
        scope.persona_ref.token,
        principal=principal,
    )

    assert not isinstance(payload, ScopedApiError)
    assert payload["scope"] == {
        "bot_ref": scope.bot_ref.token,
        "persona_ref": scope.persona_ref.token,
    }
    assert payload["scope_generation"] == scope.persona_ref.lifecycle_generation
    assert payload["resolved_at_ms"] == 1_000
    assert payload["generations"] == {
        "bot": scope.bot_ref.generation,
        "persona_lifecycle": scope.persona_ref.lifecycle_generation,
    }
    assert grant_calls[-1] == (
        principal,
        PersonaScope(bot_ref=scope.bot_ref, persona_ref=scope.persona_ref),
        "GET:persona-dossier",
    )

    original_reader = repository.read_persona_dossier

    def revoke_after_reader(*args):
        snapshot = original_reader(*args)
        grant_state["allowed"] = False
        return snapshot

    monkeypatch.setattr(repository, "read_persona_dossier", revoke_after_reader)
    revoked = service.persona_dossier_payload(
        scope.bot_ref.token,
        scope.persona_ref.token,
        principal=principal,
    )

    assert isinstance(revoked, ScopedApiError)
    assert (revoked.status, revoked.code) == (403, "scope_principal_forbidden")


def test_plugin_service_requires_host_persona_grant(tmp_path) -> None:
    repository = ScopeRepository(tmp_path)
    scope = repository.create_scope(_scope(), expected_absent=True)
    registry = ScopeRuntimeRegistry.for_test(repository=repository)
    registry.exact_session(scope)
    resolver = SimpleNamespace(
        _repository=repository,
        catalog=SimpleNamespace(
            current_exact=lambda bot_ref, session_ref: (
                _frozen_turn(scope)
                if (bot_ref, session_ref) == (scope.bot_ref.token, scope.session_ref.token)
                else None
            )
        ),
    )
    plugin = SimpleNamespace(
        _scope_runtime_registry=registry,
        _scope_resolver_v1=resolver,
        _scoped_api_principal_scope_grant=lambda *_args: None,
    )

    assert scoped_api_service_for_plugin(plugin) is None
    plugin._scoped_api_principal_persona_grant = lambda *_args: None
    assert isinstance(scoped_api_service_for_plugin(plugin), ScopedApiService)


def test_persona_dossier_projects_only_safe_active_genesis(tmp_path) -> None:
    service, repository, _registry, scope, _relation = _service(tmp_path)
    profile = _safe_genesis_profile()
    lease = repository.claim_persona_genesis(
        scope.persona_ref,
        source_fingerprint=scope.persona_ref.source_fingerprint,
        origin_turn_generation=7,
        now_ms=1_000,
    )
    assert lease is not None
    repository.commit_persona_genesis_activation(
        scope.persona_ref,
        lease,
        profile=profile,
        source_fingerprint=scope.persona_ref.source_fingerprint,
        origin_turn_generation=7,
        now_ms=1_001,
    )

    payload = service.persona_dossier_payload(
        scope.bot_ref.token,
        scope.persona_ref.token,
        principal=_principal(),
    )

    assert not isinstance(payload, ScopedApiError)
    assert payload["ok"] is True
    assert payload["scope"] == {
        "bot_ref": scope.bot_ref.token,
        "persona_ref": scope.persona_ref.token,
    }
    assert payload["scope_generation"] == scope.persona_ref.lifecycle_generation
    assert payload["resolved_at_ms"] == 1_000
    assert payload["generations"] == {
        "bot": scope.bot_ref.generation,
        "persona_lifecycle": scope.persona_ref.lifecycle_generation,
    }
    assert payload["persona"] == {
        "display": f"Persona {scope.persona_ref.token[-8:]}",
        "ref_short": scope.persona_ref.token[-8:],
        "fingerprint_short": scope.persona_ref.source_fingerprint[-12:],
        "resolution": "active",
        "genesis": {
            "state": "active",
            "priors": profile,
            "growth_enabled": True,
            "accepted_at_ms": 1_001,
        },
        "updated_at_ms": payload["persona"]["updated_at_ms"],
    }
    assert isinstance(payload["persona"]["updated_at_ms"], int)
    rendered = repr(payload)
    for forbidden in (
        "prompt",
        "begin_dialog",
        "persona_id",
        "session_ref",
        "storage_token",
        "provider",
        "address",
    ):
        assert forbidden not in rendered


def test_persona_dossier_is_two_level_and_fail_closed(tmp_path, monkeypatch) -> None:
    service, repository, _registry, scope, _relation = _service(tmp_path)

    def no_session_catalog() -> tuple[SessionScope, ...]:
        raise AssertionError("Persona dossier must not enumerate session scopes")

    monkeypatch.setattr(repository, "list_active_scopes", no_session_catalog)
    payload = service.persona_dossier_payload(
        scope.bot_ref.token,
        scope.persona_ref.token,
        principal=_principal(),
    )
    assert not isinstance(payload, ScopedApiError)
    assert payload["persona"]["genesis"] == {"state": "awaiting"}

    missing = service.persona_dossier_payload(
        scope.bot_ref.token,
        "persona_v1_missing",
        principal=_principal(),
    )
    assert isinstance(missing, ScopedApiError)
    assert missing.status == 404
    assert missing.public_payload() == {"error": "scope_persona_not_found"}

    malformed = service.persona_dossier_payload(
        "not_a_bot_ref",
        scope.persona_ref.token,
        principal=_principal(),
    )
    assert isinstance(malformed, ScopedApiError)
    assert malformed.status == 400
    assert malformed.public_payload() == {"error": "invalid_persona_request"}


def test_scoped_nonce_is_single_use_and_returns_only_scope_echo(tmp_path) -> None:
    service, _repository, _registry, scope, relation = _service(tmp_path)

    nonce = service.issue_nonce(scope, relation, turn_generation=7, principal=_principal())
    result = service.authorize(_request(scope, nonce))

    assert isinstance(result, ScopedApiAuthorization)
    assert result.echo.scope.bot_ref == scope.bot_ref.token
    assert result.echo.scope.persona_ref == scope.persona_ref.token
    assert result.echo.scope.session_ref == scope.session_ref.token
    public = result.public_payload()
    assert public["ok"] is True
    assert public["scope"] == {
        "bot_ref": scope.bot_ref.token,
        "persona_ref": scope.persona_ref.token,
        "session_ref": scope.session_ref.token,
    }
    assert public["scope_generation"] == scope.scope_generation
    assert public["resolved_at_ms"] == 1_000
    assert public["generations"]["relation"] == relation.relation_generation
    assert "relation_v1_" not in repr(public)
    assert "principal_v1_" not in repr(public)
    assert "memory" not in repr(public)

    replay = service.authorize(_request(scope, nonce))
    assert isinstance(replay, ScopedApiError)
    assert replay.status == 403
    assert replay.code == "scope_nonce_replayed"


def test_scope_resolver_distinguishes_absent_and_wrong_parents_without_selection(tmp_path) -> None:
    service, repository, _registry, scope, _relation = _service(tmp_path)
    other = repository.create_scope(
        _scope(
            bot_token="bot_v1_other",
            persona_token="persona_v1_other",
            session_token="session_v1_other",
        ),
        expected_absent=True,
    )

    missing_bot = service.resolve(
        "bot_v1_missing",
        scope.persona_ref.token,
        scope.session_ref.token,
    )
    assert isinstance(missing_bot, ScopedApiError)
    assert (missing_bot.status, missing_bot.code) == (404, "scope_bot_not_found")

    wrong_persona = service.resolve(
        scope.bot_ref.token,
        other.persona_ref.token,
        scope.session_ref.token,
    )
    assert isinstance(wrong_persona, ScopedApiError)
    assert (wrong_persona.status, wrong_persona.code) == (403, "scope_persona_not_owned")

    wrong_session = service.resolve(
        scope.bot_ref.token,
        scope.persona_ref.token,
        other.session_ref.token,
    )
    assert isinstance(wrong_session, ScopedApiError)
    assert (wrong_session.status, wrong_session.code) == (403, "scope_session_not_owned")


def test_scoped_nonce_rejects_cross_principal_or_action_before_data_access(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, repository, _registry, scope, relation = _service(tmp_path)
    owner = _principal("principal_v1_owner")
    other = _principal("principal_v1_other")
    principal_nonce = service.issue_nonce(
        scope,
        relation,
        turn_generation=7,
        principal=owner,
        endpoint="state",
    )
    action_nonce = service.issue_nonce(
        scope,
        relation,
        turn_generation=7,
        principal=owner,
        endpoint="state",
    )

    def no_data_access(*_args: object, **_kwargs: object) -> SessionScope:
        raise AssertionError("principal/action nonce mismatch must reject before scope lookup")

    monkeypatch.setattr(repository, "resolve_exact_scope", no_data_access)
    missing_principal = ScopedApiRequest.from_tokens(
        bot_ref=scope.bot_ref.token,
        persona_ref=scope.persona_ref.token,
        session_ref=scope.session_ref.token,
        nonce=principal_nonce,
        endpoint="state",
    )
    missing_principal_error = service.authorize(missing_principal)
    assert isinstance(missing_principal_error, ScopedApiError)
    assert (missing_principal_error.status, missing_principal_error.code) == (
        403,
        "scope_principal_required",
    )

    cross_principal = ScopedApiRequest.from_tokens(
        bot_ref=scope.bot_ref.token,
        persona_ref=scope.persona_ref.token,
        session_ref=scope.session_ref.token,
        nonce=principal_nonce,
        endpoint="state",
        principal=other,
    )
    principal_error = service.authorize(cross_principal)
    assert isinstance(principal_error, ScopedApiError)
    assert (principal_error.status, principal_error.code) == (
        409,
        "scope_nonce_binding_mismatch",
    )

    cross_action = ScopedApiRequest.from_tokens(
        bot_ref=scope.bot_ref.token,
        persona_ref=scope.persona_ref.token,
        session_ref=scope.session_ref.token,
        nonce=action_nonce,
        endpoint="diagnostics",
        principal=owner,
    )
    action_error = service.authorize(cross_action)
    assert isinstance(action_error, ScopedApiError)
    assert (action_error.status, action_error.code) == (
        409,
        "scope_nonce_binding_mismatch",
    )

    replay = service.authorize(cross_principal)
    assert isinstance(replay, ScopedApiError)
    assert (replay.status, replay.code) == (403, "scope_nonce_replayed")


def test_bootstrap_nonce_binds_the_explicit_requested_route_action(tmp_path) -> None:
    service, _repository, _registry, scope, _relation = _service(tmp_path)
    owner = _principal("principal_v1_bootstrap_owner")
    path = ScopeApiPathEcho(
        bot_ref=scope.bot_ref.token,
        persona_ref=scope.persona_ref.token,
        session_ref=scope.session_ref.token,
    )
    nonce = service.bootstrap_nonce(
        path,
        principal=owner,
        endpoint="diagnostics",
    )

    assert isinstance(nonce, str)
    authorized = service.authorize(
        ScopedApiRequest.from_tokens(
            bot_ref=scope.bot_ref.token,
            persona_ref=scope.persona_ref.token,
            session_ref=scope.session_ref.token,
            nonce=nonce,
            endpoint="diagnostics",
            principal=owner,
        )
    )
    assert isinstance(authorized, ScopedApiAuthorization)

    replay_nonce = service.bootstrap_nonce(
        path,
        principal=owner,
        endpoint="diagnostics",
    )
    assert isinstance(replay_nonce, str)
    cross_action = service.authorize(
        ScopedApiRequest.from_tokens(
            bot_ref=scope.bot_ref.token,
            persona_ref=scope.persona_ref.token,
            session_ref=scope.session_ref.token,
            nonce=replay_nonce,
            endpoint="state",
            principal=owner,
        )
    )
    assert isinstance(cross_action, ScopedApiError)
    assert (cross_action.status, cross_action.code) == (409, "scope_nonce_binding_mismatch")

    invalid_method = service.bootstrap_nonce(
        path,
        principal=owner,
        endpoint="memory/meltdown",
        method="GET",
    )
    assert isinstance(invalid_method, ScopedApiError)
    assert (invalid_method.status, invalid_method.code) == (400, "invalid_scoped_request")


def test_scope_catalog_bootstrap_is_redacted_and_refreshes_exact_nonce(tmp_path) -> None:
    service, _repository, _registry, scope, _relation = _service(tmp_path)
    path = ScopeApiPathEcho(
        bot_ref=scope.bot_ref.token,
        persona_ref=scope.persona_ref.token,
        session_ref=scope.session_ref.token,
    )

    catalog = service.catalog_payload()
    assert catalog == {
        "ok": True,
        "scopes": [
            {
                "scope": {
                    "bot_ref": scope.bot_ref.token,
                    "persona_ref": scope.persona_ref.token,
                    "session_ref": scope.session_ref.token,
                },
                "generations": {
                    "bot": 0,
                    "persona_lifecycle": 0,
                    "session": 0,
                    "scope": 0,
                },
            }
        ],
    }
    assert "storage_token" not in repr(catalog)
    assert "relation" not in repr(catalog)

    first = service.bootstrap_nonce(path, principal=_principal())
    second = service.bootstrap_nonce(path, principal=_principal())
    assert isinstance(first, str)
    assert isinstance(second, str)
    assert first != second
    assert isinstance(
        service.authorize(
            ScopedApiRequest.from_tokens(
                bot_ref=scope.bot_ref.token,
                persona_ref=scope.persona_ref.token,
                session_ref=scope.session_ref.token,
                nonce=first,
                principal=_principal(),
            )
        ),
        ScopedApiAuthorization,
    )
    assert isinstance(
        service.authorize(
            ScopedApiRequest.from_tokens(
                bot_ref=scope.bot_ref.token,
                persona_ref=scope.persona_ref.token,
                session_ref=scope.session_ref.token,
                nonce=second,
                principal=_principal(),
            )
        ),
        ScopedApiAuthorization,
    )

    absent = service.bootstrap_nonce(
        ScopeApiPathEcho(
            bot_ref=scope.bot_ref.token,
            persona_ref=scope.persona_ref.token,
            session_ref="session_v1_absent",
        ),
        principal=_principal(),
    )
    assert isinstance(absent, ScopedApiError)
    assert absent.status == 404
    assert absent.code == "scope_session_not_found"


def test_issued_nonce_returns_conflict_when_its_scope_is_purged(tmp_path) -> None:
    service, repository, _registry, scope, relation = _service(tmp_path)
    nonce = service.issue_nonce(scope, relation, turn_generation=7, principal=_principal())
    repository.scope_meta_path(scope).unlink()

    stale = service.authorize(_request(scope, nonce))

    assert isinstance(stale, ScopedApiError)
    assert stale.status == 409
    assert stale.code == "scope_stale"


def test_scope_echo_includes_every_public_generation_fence(tmp_path) -> None:
    service, _repository, _registry, scope, relation = _service(tmp_path)
    nonce = service.issue_nonce(scope, relation, turn_generation=7, principal=_principal())

    result = service.authorize(_request(scope, nonce))

    assert isinstance(result, ScopedApiAuthorization)
    assert result.public_payload()["generations"] == {
        "bot": scope.bot_ref.generation,
        "persona_lifecycle": scope.persona_ref.lifecycle_generation,
        "session": scope.session_ref.generation,
        "relation": relation.relation_generation,
        "scope": scope.scope_generation,
        "turn": 7,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("bot_ref", "bot_v1_replaced"),
        ("session_generation", 1),
        ("turn_generation", 8),
        ("turn_state", "resolving"),
        ("active_persona_ref", "persona_v1_replaced"),
        ("persona_lifecycle_generation", 1),
        ("active_scope_token", "scope_v1_replaced"),
        ("scope_generation", 1),
    ),
)
def test_issued_nonce_rejects_every_frozen_turn_fence_drift(
    tmp_path,
    field: str,
    value: object,
) -> None:
    service, _repository, _registry, scope, relation = _service(tmp_path)
    turn = _frozen_turn(scope)
    service._turn_lookup = lambda candidate: turn if candidate == scope else None
    nonce = service.issue_nonce(scope, relation, turn_generation=7, principal=_principal())
    setattr(turn, field, value)

    stale = service.authorize(_request(scope, nonce))

    assert isinstance(stale, ScopedApiError)
    assert stale.status == 409
    assert stale.code == "scope_stale"


def test_issued_nonce_rejects_relation_and_scope_generation_staleness(tmp_path) -> None:
    service, repository, _registry, scope, relation = _service(tmp_path)
    relation_nonce = service.issue_nonce(
        scope,
        relation,
        turn_generation=7,
        principal=_principal(),
    )
    repository.invalidate_relation(
        relation,
        expected_relation_generation=relation.relation_generation,
        reason="test",
    )
    relation_stale = service.authorize(_request(scope, relation_nonce))

    assert isinstance(relation_stale, ScopedApiError)
    assert relation_stale.status == 409

    service, repository, _registry, scope, relation = _service(tmp_path / "scope")
    scope_nonce = service.issue_nonce(scope, relation, turn_generation=7, principal=_principal())
    repository.invalidate_scope(
        scope,
        expected_scope_generation=scope.scope_generation,
        reason="test",
    )
    scope_stale = service.authorize(_request(scope, scope_nonce))

    assert isinstance(scope_stale, ScopedApiError)
    assert scope_stale.status == 409


def test_issued_nonce_maps_runtime_loss_to_410_and_repository_failure_to_503(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, repository, registry, scope, relation = _service(tmp_path)
    runtime_nonce = service.issue_nonce(scope, relation, turn_generation=7, principal=_principal())
    registry.release_session(scope)

    runtime_error = service.authorize(_request(scope, runtime_nonce))
    assert isinstance(runtime_error, ScopedApiError)
    assert runtime_error.status == 410
    assert runtime_error.code == "scope_required"

    service, repository, _registry, scope, relation = _service(tmp_path / "repository")
    repository_nonce = service.issue_nonce(
        scope,
        relation,
        turn_generation=7,
        principal=_principal(),
    )
    monkeypatch.setattr(
        repository,
        "resolve_exact_scope",
        lambda *_args: (_ for _ in ()).throw(OSError("offline")),
    )

    repository_error = service.authorize(_request(scope, repository_nonce))
    assert isinstance(repository_error, ScopedApiError)
    assert repository_error.status == 503
    assert repository_error.code == "scope_repository_unavailable"


def test_scoped_nonce_expiry_and_bootstrap_uses_the_principal_grant(tmp_path) -> None:
    service, _repository, registry, scope, relation = _service(tmp_path)
    nonce = service.issue_nonce(scope, relation, turn_generation=7, principal=_principal())
    expiry = service._pending_nonces[nonce].expires_at_ms
    service._clock_ms = lambda: expiry + 1

    expired = service.authorize(_request(scope, nonce))
    assert isinstance(expired, ScopedApiError)
    assert expired.status == 403
    assert expired.code == "scope_nonce_expired"

    service, _repository, registry, scope, relation = _service(tmp_path / "ambiguous")
    other = registry.relation_for(
        scope,
        AuthenticatedSubject(
            relation_ref=RelationRef(
                token="relation_v1_second_scoped_api",
                bot_ref=scope.bot_ref,
            ),
            identity_quality="event_get_sender_id",
        ),
    )
    assert other is not None
    bootstrap = service.bootstrap_nonce(
        ScopeApiPathEcho(
            bot_ref=scope.bot_ref.token,
            persona_ref=scope.persona_ref.token,
            session_ref=scope.session_ref.token,
        ),
        principal=_principal(),
    )
    assert isinstance(bootstrap, str)
    assert service._pending_nonces[bootstrap].relation_scope == relation


def test_scoped_nonce_path_substitution_fails_without_resolving_sibling(tmp_path, monkeypatch) -> None:
    service, repository, _registry, scope, relation = _service(tmp_path)
    sibling = repository.create_scope(_scope(session_token="session_v1_sibling"), expected_absent=True)
    nonce = service.issue_nonce(scope, relation, turn_generation=7, principal=_principal())

    def no_sibling_resolution(*_args, **_kwargs):
        raise AssertionError("cross-scope nonce must be rejected before lookup")

    monkeypatch.setattr(repository, "resolve_exact_scope", no_sibling_resolution)
    result = service.authorize(_request(sibling, nonce))

    assert isinstance(result, ScopedApiError)
    assert result.status == 403
    assert result.code == "scope_nonce_mismatch"
    assert result.public_payload() == {"error": "scope_nonce_mismatch"}


def test_scoped_stream_revalidates_live_owner_before_each_send(tmp_path) -> None:
    service, _repository, registry, scope, relation = _service(tmp_path)
    nonce = service.issue_nonce(scope, relation, turn_generation=7, principal=_principal())
    authorization = service.authorize(_request(scope, nonce))
    assert isinstance(authorization, ScopedApiAuthorization)

    registry.release_session(scope)

    stale = service.revalidate(authorization)
    assert isinstance(stale, ScopedApiError)
    assert stale.status == 409
    assert stale.code == "scope_stale"
    assert stale.websocket_close_code == 4409


def test_scoped_request_rejects_missing_or_malformed_nonce(tmp_path) -> None:
    service, _repository, _registry, scope, _relation = _service(tmp_path)

    missing = service.authorize(_request(scope, None))
    malformed = service.authorize(_request(scope, "not-a-scope-nonce"))

    assert isinstance(missing, ScopedApiError)
    assert missing.status == 400
    assert isinstance(malformed, ScopedApiError)
    assert malformed.status == 400


def test_shaped_but_unissued_scope_nonce_is_invalid(tmp_path) -> None:
    """A nonce that looks valid cannot be used as an existence probe."""

    service, _repository, _registry, scope, _relation = _service(tmp_path)

    forged = "scope_nonce_v1_" + ("A" * 32)
    result = service.authorize(_request(scope, forged))

    assert isinstance(result, ScopedApiError)
    assert result.status == 403
    assert result.code == "scope_nonce_invalid"


@pytest.mark.asyncio
async def test_astrbot_scoped_handler_fails_closed_without_a_principal_adapter(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sylanne_alpha.scoped_api import SCOPE_NONCE_HEADER
    from sylanne_alpha.webui_routes import WebUIRoutes

    service, _repository, _registry, scope, relation = _service(tmp_path)
    nonce = service.issue_nonce(scope, relation, turn_generation=7, principal=_principal())
    web = ModuleType("astrbot.api.web")
    web.request = SimpleNamespace(
        headers={SCOPE_NONCE_HEADER: nonce},
        path_params={
            "bot_ref": scope.bot_ref.token,
            "persona_ref": scope.persona_ref.token,
            "session_ref": scope.session_ref.token,
        },
        query={},
        method="GET",
    )
    monkeypatch.setitem(sys.modules, "astrbot.api.web", web)

    payload = await WebUIRoutes(SimpleNamespace(_scoped_api_service=service)).scoped_api_handler(
        "state"
    )

    assert payload == {"error": "scope_principal_required", "status": 403}
    assert nonce in service._pending_nonces


@pytest.mark.asyncio
async def test_astrbot_persona_dossier_handler_uses_no_session_nonce(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sylanne_alpha.webui_routes import WebUIRoutes

    service, _repository, _registry, scope, _relation = _service(tmp_path)
    web = ModuleType("astrbot.api.web")
    web.request = SimpleNamespace(
        headers={},
        path_params={
            "bot_ref": scope.bot_ref.token,
            "persona_ref": scope.persona_ref.token,
        },
        query={},
        method="GET",
    )
    monkeypatch.setitem(sys.modules, "astrbot.api.web", web)
    routes = WebUIRoutes(SimpleNamespace(_scoped_api_service=service))

    payload = await routes.persona_dossier_handler()

    assert payload == {
        "error": "scope_principal_required",
        "status": 403,
    }

    web.request.query = {"session": scope.session_ref.token}
    rejected = await routes.persona_dossier_handler()
    assert rejected == {
        "error": "legacy_session_selector_forbidden",
        "status": 400,
    }


@pytest.mark.asyncio
async def test_scoped_read_dtos_are_real_and_strictly_redacted(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sylanne_alpha.scoped_api import SCOPE_NONCE_HEADER
    from sylanne_alpha.webui_routes import WebUIRoutes

    service, _repository, registry, scope, relation = _service(tmp_path)
    secret = "private conversational text"

    class _Memory:
        def __init__(self) -> None:
            self._l1 = [object(), object()]
            self._l2 = [object()]
            self._l3_nodes = {"hidden-topic": object()}
            self._l3_edges = [("hidden-a", "hidden-b")]
            self._tick = 9

    class _History:
        def query(self, session, **_kwargs):
            assert session == scope.storage_token
            return {
                "points": [{"at_ms": 7, "score": 0.25, "text": secret}],
                "sample_count": 1,
                "storage": {"used_bytes": 12, "segment_count": 1},
            }

    class _Persistence:
        def __init__(self) -> None:
            self.purged: list[str] = []

        async def purge_session_after_meltdown(self, storage_token: str) -> None:
            self.purged.append(storage_token)

    memory = _Memory()
    computation = SimpleNamespace(
        _tick_count=12,
        gate=SimpleNamespace(to_dict=lambda: {"drive": 0.8, "prompt": secret}),
        boundary=SimpleNamespace(to_dict=lambda: {"integrity": 0.9, "note": secret}),
        diagnostics=lambda: {"route_counts": {"resonance": 4}, "reason": secret},
    )
    host = SimpleNamespace(
        kernel=SimpleNamespace(
            computation=computation,
            body=SimpleNamespace(memory={"traces": [secret]}),
        )
    )
    persistence = _Persistence()
    plugin = SimpleNamespace(
        _scoped_api_service=service,
        _scope_runtime_registry=registry,
        _meltdown_nonces={},
        _session_ctx=SimpleNamespace(observation_history_store=_History()),
        _state_persistence=persistence,
        _memory_system_for_scope=lambda candidate: memory if candidate == scope else None,
        _host_for_scope=lambda candidate: host if candidate == scope else None,
    )
    routes = WebUIRoutes(plugin)
    web = ModuleType("astrbot.api.web")
    monkeypatch.setitem(sys.modules, "astrbot.api.web", web)

    def install_request(endpoint: str, nonce: str, *, method: str = "GET", body=None) -> None:
        async def json_body():
            return body

        web.request = SimpleNamespace(
            headers={SCOPE_NONCE_HEADER: nonce},
            path_params={
                "bot_ref": scope.bot_ref.token,
                "persona_ref": scope.persona_ref.token,
                "session_ref": scope.session_ref.token,
            },
            query={},
            method=method,
            json=json_body,
        )

    payloads = {}
    for endpoint in ("state", "observation-history", "diagnostics", "memory-pools"):
        nonce = service.issue_nonce(
            scope,
            relation,
            turn_generation=7,
            principal=_principal(),
            endpoint=endpoint,
        )
        install_request(endpoint, nonce)
        payloads[endpoint] = await routes.scoped_api_handler(endpoint)

    for payload in payloads.values():
        assert payload == {"error": "scope_principal_required", "status": 403}
        rendered = repr(payload)
        assert secret not in rendered
        assert scope.storage_token not in rendered
        assert "hidden-topic" not in rendered

    nonce = service.issue_nonce(
        scope,
        relation,
        turn_generation=7,
        principal=_principal(),
        endpoint="memory/meltdown",
        method="POST",
    )
    install_request(
        "memory/meltdown",
        nonce,
        method="POST",
        body={"meltdown_nonce": "unreachable"},
    )
    blocked = await routes.scoped_api_handler("memory/meltdown")
    assert blocked == {"error": "scope_principal_required", "status": 403}
    assert plugin._meltdown_nonces == {}
    assert memory._l1 == [memory._l1[0], memory._l1[1]]
    assert memory._l2 == [memory._l2[0]]
    assert memory._l3_nodes == {"hidden-topic": memory._l3_nodes["hidden-topic"]}
    assert memory._l3_edges == [("hidden-a", "hidden-b")]
    assert host.kernel.body.memory["traces"] == [secret]
    assert persistence.purged == []


def test_scope_service_has_no_private_meltdown_nonce_store(tmp_path) -> None:
    service, _repository, _registry, _scope_value, _relation = _service(tmp_path)

    assert not hasattr(service, "issue_meltdown_nonce")
    assert not hasattr(service, "authorize_meltdown")


def test_only_a_frozen_relation_runtime_binding_can_issue_a_scope_nonce(tmp_path) -> None:
    from sylanne_alpha.scoped_api import issue_scoped_api_nonce_for_binding

    service, _repository, _registry, scope, relation = _service(tmp_path)
    binding = SimpleNamespace(
        scope=scope,
        relation_runtime=SimpleNamespace(scope=relation),
        turn_generation=7,
        principal=_principal(),
    )

    nonce = issue_scoped_api_nonce_for_binding(service, binding)
    assert isinstance(nonce, str)
    assert isinstance(service.authorize(_request(scope, nonce)), ScopedApiAuthorization)
    assert issue_scoped_api_nonce_for_binding(
        service,
        SimpleNamespace(scope=scope, relation_runtime=None, turn_generation=7),
    ) is None


def _unused_local_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as stream:
        stream.bind(("127.0.0.1", 0))
        return int(stream.getsockname()[1])


@pytest.mark.asyncio
async def test_aiohttp_scoped_route_fails_closed_without_a_principal_adapter(
    tmp_path,
) -> None:
    from aiohttp import ClientSession

    from sylanne_alpha import webui_server
    from sylanne_alpha.scoped_api import SCOPE_NONCE_HEADER, scoped_api_path
    from sylanne_alpha.scope_contracts import ScopeApiPathEcho

    service, _repository, registry, scope, relation = _service(tmp_path)
    plugin = SimpleNamespace(
        _scoped_api_service=service,
        _scope_runtime_registry=registry,
    )
    token = "scoped-api-test-token"
    port = _unused_local_port()
    previous_token = webui_server._active_token
    webui_server._active_token = token
    task = asyncio.create_task(
        webui_server.start_webui_server(plugin, host="127.0.0.1", port=port)
    )
    try:
        path = scoped_api_path(
            ScopeApiPathEcho(
                bot_ref=scope.bot_ref.token,
                persona_ref=scope.persona_ref.token,
                session_ref=scope.session_ref.token,
            ),
            "state",
        )
        nonce = service.issue_nonce(
            scope,
            relation,
            turn_generation=7,
            principal=_principal(),
            endpoint="state",
        )
        async with ClientSession(headers={"Authorization": f"Bearer {token}"}) as client:
            response = None
            for _ in range(100):
                try:
                    response = await client.get(
                        f"http://127.0.0.1:{port}{path}",
                        headers={SCOPE_NONCE_HEADER: nonce},
                    )
                    break
                except OSError:
                    await asyncio.sleep(0.01)
            assert response is not None
            async with response:
                assert response.status == 403
                assert await response.json() == {"error": "scope_principal_required"}
            assert nonce in service._pending_nonces
            legacy = await client.get(f"http://127.0.0.1:{port}/api/state")
            async with legacy:
                assert legacy.status == 410
                assert await legacy.json() == {"error": "scope_required"}
    finally:
        task.cancel()
        await task
        webui_server._active_token = previous_token


@pytest.mark.asyncio
async def test_aiohttp_scope_bootstrap_fails_closed_without_a_principal_adapter(tmp_path) -> None:
    from aiohttp import ClientSession

    from sylanne_alpha import webui_server
    from sylanne_alpha.scoped_api import SCOPE_NONCE_HEADER, scoped_api_path

    service, _repository, registry, scope, relation = _service(tmp_path)
    plugin = SimpleNamespace(
        _scoped_api_service=service,
        _scope_runtime_registry=registry,
    )
    token = "scope-catalog-test-token"
    port = _unused_local_port()
    previous_token = webui_server._active_token
    webui_server._active_token = token
    task = asyncio.create_task(
        webui_server.start_webui_server(plugin, host="127.0.0.1", port=port)
    )
    try:
        async with ClientSession(headers={"Authorization": f"Bearer {token}"}) as client:
            catalog = None
            for _ in range(100):
                try:
                    catalog = await client.get(f"http://127.0.0.1:{port}/api/scopes")
                    break
                except OSError:
                    await asyncio.sleep(0.01)
            assert catalog is not None
            async with catalog:
                assert catalog.status == 200
                body = await catalog.json()
            assert body["scopes"][0]["scope"]["session_ref"] == scope.session_ref.token
            assert body["csrf_token"] == webui_server._csrf_token
            assert scope.storage_token not in repr(body)

            bootstrap_path = (
                f"/api/scopes/{scope.bot_ref.token}/personas/{scope.persona_ref.token}"
                f"/sessions/{scope.session_ref.token}/nonce"
            )
            async with client.post(
                f"http://127.0.0.1:{port}{bootstrap_path}",
                headers={"X-CSRF-Token": body["csrf_token"]},
            ) as bootstrap:
                assert bootstrap.status == 403
                assert await bootstrap.json() == {"error": "scope_principal_required"}
    finally:
        task.cancel()
        await task
        webui_server._active_token = previous_token


@pytest.mark.asyncio
async def test_aiohttp_persona_dossier_is_two_level_and_rejects_session_selector(tmp_path) -> None:
    from aiohttp import ClientSession

    from sylanne_alpha import webui_server

    service, _repository, registry, scope, _relation = _service(tmp_path)
    plugin = SimpleNamespace(
        _scoped_api_service=service,
        _scope_runtime_registry=registry,
    )
    token = "persona-dossier-test-token"
    port = _unused_local_port()
    previous_token = webui_server._active_token
    webui_server._active_token = token
    task = asyncio.create_task(
        webui_server.start_webui_server(plugin, host="127.0.0.1", port=port)
    )
    path = (
        f"/api/v1/bots/{scope.bot_ref.token}/personas/{scope.persona_ref.token}/dossier"
    )
    try:
        async with ClientSession(headers={"Authorization": f"Bearer {token}"}) as client:
            response = None
            for _ in range(100):
                try:
                    response = await client.get(f"http://127.0.0.1:{port}{path}")
                    break
                except OSError:
                    await asyncio.sleep(0.01)
            assert response is not None
            async with response:
                assert response.status == 403
                payload = await response.json()
            assert payload == {"error": "scope_principal_required"}

            async with client.get(f"http://127.0.0.1:{port}{path}?session=default") as rejected:
                assert rejected.status == 400
                assert await rejected.json() == {
                    "error": "legacy_session_selector_forbidden"
                }
    finally:
        task.cancel()
        await task
        webui_server._active_token = previous_token


@pytest.mark.asyncio
async def test_scoped_websocket_fails_closed_without_a_principal_adapter(tmp_path) -> None:
    from aiohttp import ClientSession

    from sylanne_alpha import webui_server
    from sylanne_alpha.scoped_api import SCOPE_NONCE_HEADER, scoped_api_path
    from sylanne_alpha.scope_contracts import ScopeApiPathEcho

    service, _repository, registry, scope, relation = _service(tmp_path)
    plugin = SimpleNamespace(
        _scoped_api_service=service,
        _scope_runtime_registry=registry,
    )
    token = "scoped-websocket-test-token"
    port = _unused_local_port()
    previous_token = webui_server._active_token
    webui_server._active_token = token
    task = asyncio.create_task(
        webui_server.start_webui_server(plugin, host="127.0.0.1", port=port)
    )
    try:
        path = scoped_api_path(
            ScopeApiPathEcho(
                bot_ref=scope.bot_ref.token,
                persona_ref=scope.persona_ref.token,
                session_ref=scope.session_ref.token,
            ),
            "ws",
        )
        nonce = service.issue_nonce(
            scope,
            relation,
            turn_generation=7,
            principal=_principal(),
            endpoint="ws",
        )
        async with ClientSession(headers={"Authorization": f"Bearer {token}"}) as client:
            response = None
            for _ in range(100):
                try:
                    response = await client.get(
                        f"http://127.0.0.1:{port}{path}",
                        headers={SCOPE_NONCE_HEADER: nonce},
                    )
                    break
                except OSError:
                    await asyncio.sleep(0.01)
            assert response is not None
            async with response:
                assert response.status == 403
                assert await response.json() == {"error": "scope_principal_required"}
            assert nonce in service._pending_nonces
    finally:
        task.cancel()
        await task
        webui_server._active_token = previous_token


@pytest.mark.asyncio
async def test_scoped_sse_fails_closed_without_a_principal_adapter(
    tmp_path,
) -> None:
    """The real SSE loop must fence every emission after the initial status."""

    from aiohttp import ClientSession

    from sylanne_alpha import webui_server
    from sylanne_alpha.scoped_api import SCOPE_NONCE_HEADER, scoped_api_path
    from sylanne_alpha.scope_contracts import ScopeApiPathEcho

    service, _repository, registry, scope, relation = _service(tmp_path)
    plugin = SimpleNamespace(
        _scoped_api_service=service,
        _scope_runtime_registry=registry,
    )
    token = "scoped-sse-test-token"
    port = _unused_local_port()
    previous_token = webui_server._active_token
    webui_server._active_token = token
    task = asyncio.create_task(
        webui_server.start_webui_server(plugin, host="127.0.0.1", port=port)
    )
    try:
        path = scoped_api_path(
            ScopeApiPathEcho(
                bot_ref=scope.bot_ref.token,
                persona_ref=scope.persona_ref.token,
                session_ref=scope.session_ref.token,
            ),
            "stream",
        )
        nonce = service.issue_nonce(
            scope,
            relation,
            turn_generation=7,
            principal=_principal(),
            endpoint="stream",
        )
        async with ClientSession(headers={"Authorization": f"Bearer {token}"}) as client:
            response = None
            for _ in range(100):
                try:
                    response = await client.get(
                        f"http://127.0.0.1:{port}{path}",
                        headers={SCOPE_NONCE_HEADER: nonce},
                    )
                    break
                except OSError:
                    await asyncio.sleep(0.01)
            assert response is not None
            async with response:
                assert response.status == 403
                assert await response.json() == {"error": "scope_principal_required"}
            assert nonce in service._pending_nonces
    finally:
        task.cancel()
        await task
        webui_server._active_token = previous_token


def test_astrbot_registers_only_the_exact_scoped_root() -> None:
    import inspect

    import main

    source = inspect.getsource(main.EmotionalStatePlugin._register_web_apis)

    assert "/api/v1/bots/<bot_ref>/personas/<persona_ref>/sessions/<session_ref>" in source
    assert "{{bot_ref}}" not in source
    assert "scoped_api_handler" in source
    assert "/api/scopes" in source
    assert "scope_catalog_handler" in source
    assert "/api/v1/bots/<bot_ref>/personas/<persona_ref>/dossier" in source
    assert "persona_dossier_handler" in source
