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
    PersonaRevisionRef,
    RelationRef,
    ScopeApiPathEcho,
    ScopedPrincipal,
    SessionRef,
    SessionScope,
)
from sylanne_alpha.scope_repository import ScopeRepository
from sylanne_alpha.scope_runtime import ScopeRuntimeRegistry
from sylanne_alpha.scoped_api import (
    SCOPED_API_ROUTE_SPECS,
    ScopeRouteSpec,
    ScopedApiAuthorization,
    ScopedApiError,
    ScopedApiRequest,
    ScopedApiService,
    scoped_api_route_spec,
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
    service = ScopedApiService(
        repository,
        registry,
        turn_lookup=lambda candidate: turn if candidate == scope else None,
        clock_ms=lambda: 1_000,
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

    assert state == ScopeRouteSpec(endpoint="state", method="GET")
    assert state.action == "GET:state"
    assert melt.action == "POST:memory/meltdown"
    with pytest.raises(TypeError):
        SCOPED_API_ROUTE_SPECS["state"] = state  # type: ignore[index]


def _safe_genesis_profile() -> dict[str, object]:
    return {
        "traits_prior": {},
        "voice_prior": {},
        "boundary_prior": {},
        "proactivity_prior": {},
        "circadian_prior": {},
    }


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
    )

    assert not isinstance(payload, ScopedApiError)
    assert payload["ok"] is True
    assert payload["persona_scope"] == {
        "bot_ref": scope.bot_ref.token,
        "persona_ref": scope.persona_ref.token,
    }
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
    )
    assert not isinstance(payload, ScopedApiError)
    assert payload["persona"]["genesis"] == {"state": "awaiting"}

    missing = service.persona_dossier_payload(scope.bot_ref.token, "persona_v1_missing")
    assert isinstance(missing, ScopedApiError)
    assert missing.status == 404
    assert missing.public_payload() == {"error": "persona_not_found"}

    malformed = service.persona_dossier_payload("not_a_bot_ref", scope.persona_ref.token)
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


def test_scoped_nonce_expiry_and_ambiguous_bootstrap_fail_closed(tmp_path) -> None:
    service, _repository, registry, scope, relation = _service(tmp_path)
    nonce = service.issue_nonce(scope, relation, turn_generation=7, principal=_principal())
    expiry = service._pending_nonces[nonce].expires_at_ms
    service._clock_ms = lambda: expiry + 1

    expired = service.authorize(_request(scope, nonce))
    assert isinstance(expired, ScopedApiError)
    assert expired.status == 403
    assert expired.code == "scope_nonce_expired"

    service, _repository, registry, scope, _relation = _service(tmp_path / "ambiguous")
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
    assert isinstance(bootstrap, ScopedApiError)
    assert bootstrap.status == 410


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

    assert payload["ok"] is True
    assert payload["persona_scope"] == {
        "bot_ref": scope.bot_ref.token,
        "persona_ref": scope.persona_ref.token,
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
                assert response.status == 200
                payload = await response.json()
            assert payload["persona_scope"] == {
                "bot_ref": scope.bot_ref.token,
                "persona_ref": scope.persona_ref.token,
            }

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
