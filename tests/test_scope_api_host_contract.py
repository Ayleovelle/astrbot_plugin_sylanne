"""Host-adapter regressions for the exact scoped WebUI contract."""

from __future__ import annotations

import asyncio
import http.client
import json
import socket
import sys
from contextlib import closing
from types import ModuleType, SimpleNamespace

import pytest

from sylanne_alpha.scope_contracts import PersonaScope, ScopeApiPathEcho, ScopedPrincipal
from sylanne_alpha.scoped_api import (
    PERSONA_DOSSIER_ROUTE_SPEC,
    SCOPE_NONCE_HEADER,
    ScopedApiError,
    scoped_api_path,
)


def _unused_local_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as stream:
        stream.bind(("127.0.0.1", 0))
        return int(stream.getsockname()[1])


def test_host_principal_uses_only_a_published_resolver_key_and_is_domain_separated(tmp_path) -> None:
    import main
    from sylanne_alpha.scope_repository import ScopeRepository

    plugin = object.__new__(main.EmotionalStatePlugin)
    plugin._correlation_secret = b"s" * 32
    plugin._scope_resolver_v1 = SimpleNamespace(
        _repository=ScopeRepository(tmp_path),
    )

    pages = plugin._scoped_api_principal_from_authenticated_host(
        "pages", "dashboard-user"
    )
    standalone = plugin._scoped_api_principal_from_authenticated_host(
        "standalone", "dashboard-user"
    )

    assert type(pages) is ScopedPrincipal
    assert type(standalone) is ScopedPrincipal
    assert pages != standalone
    assert "dashboard-user" not in pages.token
    assert (
        plugin._scoped_api_principal_from_authenticated_host("pages", "")
        is None
    )
    assert (
        plugin._scoped_api_principal_from_authenticated_host(
            "untrusted-header", "dashboard-user"
        )
        is None
    )
    plugin._scope_resolver_v1 = None
    assert plugin._scoped_api_principal_from_authenticated_host("pages", "dashboard-user") is None


def test_host_grant_is_fail_closed_without_an_authority_mapping() -> None:
    from tests.test_scoped_api import _scope
    import main

    plugin = object.__new__(main.EmotionalStatePlugin)
    plugin._correlation_secret = b"s" * 32
    scope = _scope()
    principal = plugin._scoped_api_principal_from_authenticated_host(
        "pages", "dashboard-user"
    )

    assert plugin._scoped_api_principal_scope_grant(
        principal,
        scope,
        "GET:state",
    ) is None
    assert plugin._scoped_api_principal_persona_grant(
        principal,
        PersonaScope(bot_ref=scope.bot_ref, persona_ref=scope.persona_ref),
        PERSONA_DOSSIER_ROUTE_SPEC.action,
    ) is None


def test_legacy_matcher_preserves_canonical_scoped_resources() -> None:
    from sylanne_alpha.webui_routes import is_legacy_scoped_private_path

    scope_root = "/api/v1/bots/bot/personas/persona/sessions/session"
    assert not is_legacy_scoped_private_path(scope_root)
    assert not is_legacy_scoped_private_path(f"{scope_root}/state")
    assert not is_legacy_scoped_private_path(
        "/api/v1/bots/bot/personas/persona/dossier"
    )
    assert not is_legacy_scoped_private_path(
        "/api/scopes/bot/personas/persona/sessions/session/nonce"
    )
    assert is_legacy_scoped_private_path(f"{scope_root}/ws/state")


def test_pages_registers_immutable_http_routes_but_never_the_scoped_websocket() -> None:
    import inspect

    import main

    source = inspect.getsource(main.EmotionalStatePlugin._register_web_apis)
    assert "SCOPED_API_ROUTE_SPECS" in source
    assert 'if endpoint == "ws":' in source
    assert "[route.method]" in source
    assert "legacy_scope_gone_handler" in source


@pytest.mark.asyncio
async def test_pages_rejects_injected_permissive_service_before_scope_access(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.test_scoped_api import _principal, _service
    from sylanne_alpha.webui_routes import WebUIRoutes

    service, _repository, registry, scope, relation = _service(tmp_path)
    expected_principal = _principal("principal_v1_pages_authenticated")

    class Plugin:
        _scoped_api_service = service
        _scope_runtime_registry = registry

        def __init__(self) -> None:
            self.identity_calls: list[tuple[str, str]] = []
            self.grant_calls: list[tuple[object, object, str]] = []

        def _scoped_api_principal_from_authenticated_host(
            self,
            host: object,
            identity: object,
        ) -> ScopedPrincipal | None:
            self.identity_calls.append((str(host), str(identity)))
            if (host, identity) == ("pages", "dashboard-user"):
                return expected_principal
            return None

        def _scoped_api_principal_scope_grant(
            self,
            principal: object,
            candidate: object,
            action: str,
        ) -> object | None:
            self.grant_calls.append((principal, candidate, action))
            return None

        def _scoped_api_principal_persona_grant(
            self,
            _principal: object,
            _candidate: object,
            _action: str,
        ) -> object | None:
            return None

    plugin = Plugin()
    service._principal_persona_grant = plugin._scoped_api_principal_persona_grant
    nonce = service.issue_nonce(
        scope,
        relation,
        turn_generation=7,
        principal=expected_principal,
        endpoint="state",
    )

    def scope_must_not_be_resolved(*_args: object) -> object:
        raise AssertionError("a mismatched injected service must not resolve scope")

    monkeypatch.setattr(service, "resolve", scope_must_not_be_resolved)
    web = ModuleType("astrbot.api.web")
    web.request = SimpleNamespace(
        username="dashboard-user",
        headers={
            SCOPE_NONCE_HEADER: nonce,
            "X-Sylanne-Principal": "principal_v1_forged",
        },
        path_params={
            "bot_ref": scope.bot_ref.token,
            "persona_ref": scope.persona_ref.token,
            "session_ref": scope.session_ref.token,
        },
        query={"principal": "principal_v1_forged", "scope_nonce": nonce},
        method="GET",
    )
    monkeypatch.setitem(sys.modules, "astrbot.api.web", web)

    result = await WebUIRoutes(plugin).scoped_api_handler("state")

    assert result == {"error": "scope_principal_forbidden", "status": 403}
    assert plugin.identity_calls == [("pages", "dashboard-user")]
    assert plugin.grant_calls == []
    assert nonce in service._pending_nonces


@pytest.mark.asyncio
async def test_pages_refuses_forged_carriers_without_a_verified_username(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.test_scoped_api import _principal, _service
    from sylanne_alpha.webui_routes import WebUIRoutes

    service, _repository, registry, scope, relation = _service(tmp_path)
    principal = _principal("principal_v1_pages_absent_username")

    class Plugin:
        _scoped_api_service = service
        _scope_runtime_registry = registry
        _scoped_api_principal_scope_grant = staticmethod(lambda *_args: relation)
        _scoped_api_principal_persona_grant = staticmethod(lambda *_args: None)

        @staticmethod
        def _scoped_api_principal_from_authenticated_host(
            _host: object,
            _identity: object,
        ) -> ScopedPrincipal | None:
            raise AssertionError("a missing Pages username must not invoke the issuer")

    nonce = service.issue_nonce(
        scope,
        relation,
        turn_generation=7,
        principal=principal,
        endpoint="scope",
    )

    async def body_must_not_be_read() -> object:
        raise AssertionError("forged body identity must not be parsed")

    web = ModuleType("astrbot.api.web")
    web.request = SimpleNamespace(
        username=None,
        headers={
            SCOPE_NONCE_HEADER: nonce,
            "X-Sylanne-Principal": "principal_v1_forged",
        },
        path_params={
            "bot_ref": scope.bot_ref.token,
            "persona_ref": scope.persona_ref.token,
            "session_ref": scope.session_ref.token,
        },
        query={"principal": "principal_v1_forged", "scope_nonce": nonce},
        method="GET",
        json=body_must_not_be_read,
    )
    monkeypatch.setitem(sys.modules, "astrbot.api.web", web)

    plugin = Plugin()
    service._principal_persona_grant = plugin._scoped_api_principal_persona_grant
    result = await WebUIRoutes(plugin).scoped_api_handler("scope")

    assert result == {"error": "scope_principal_required", "status": 403}
    assert nonce in service._pending_nonces


@pytest.mark.asyncio
async def test_pages_accepts_scope_nonce_only_from_the_header(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.test_scoped_api import _principal, _service
    from sylanne_alpha.webui_routes import WebUIRoutes

    service, _repository, registry, scope, relation = _service(tmp_path)
    principal = _principal("principal_v1_pages_header_only")

    class Plugin:
        _scoped_api_service = service
        _scope_runtime_registry = registry

        @staticmethod
        def _scoped_api_principal_from_authenticated_host(
            host: object,
            identity: object,
        ) -> ScopedPrincipal | None:
            return principal if (host, identity) == ("pages", "dashboard-user") else None

        @staticmethod
        def _scoped_api_principal_scope_grant(
            candidate_principal: object,
            candidate_scope: object,
            action: str,
        ) -> object | None:
            if (
                candidate_principal == principal
                and candidate_scope == scope
                and action == "POST:memory/meltdown"
            ):
                return relation
            return None

        _scoped_api_principal_persona_grant = staticmethod(lambda *_args: None)

    plugin = Plugin()
    monkeypatch.setattr(
        service,
        "_principal_scope_grant",
        plugin._scoped_api_principal_scope_grant,
    )
    service._principal_persona_grant = plugin._scoped_api_principal_persona_grant
    nonce = service.issue_nonce(
        scope,
        relation,
        turn_generation=7,
        principal=principal,
        endpoint="memory/meltdown",
        method="POST",
    )

    async def body_must_not_be_read() -> object:
        raise AssertionError("a query/body nonce must fail before body parsing")

    def scope_must_not_be_resolved(*_args: object) -> object:
        raise AssertionError("a missing header nonce must not resolve scope")

    monkeypatch.setattr(service, "resolve", scope_must_not_be_resolved)

    web = ModuleType("astrbot.api.web")
    web.request = SimpleNamespace(
        username="dashboard-user",
        headers={},
        path_params={
            "bot_ref": scope.bot_ref.token,
            "persona_ref": scope.persona_ref.token,
            "session_ref": scope.session_ref.token,
        },
        query={"scope_nonce": nonce},
        method="POST",
        json=body_must_not_be_read,
    )
    monkeypatch.setitem(sys.modules, "astrbot.api.web", web)

    result = await WebUIRoutes(plugin).scoped_api_handler("memory/meltdown")

    assert result == {"error": "scope_nonce_required", "status": 400}
    assert nonce in service._pending_nonces


@pytest.mark.asyncio
async def test_pages_sse_emits_one_scope_invalidated_frame_then_closes() -> None:
    from sylanne_alpha.webui_routes import WebUIRoutes

    class InvalidatedService:
        @staticmethod
        def revalidate(_authorization: object) -> ScopedApiError:
            return ScopedApiError(409, "scope_stale")

    frames = [
        frame
        async for frame in WebUIRoutes._scoped_sse_frames(
            InvalidatedService(),
            object(),
        )
    ]

    assert frames == [
        'event: scope_invalidated\ndata: {"event":"scope_invalidated","data":{"error":"scope_invalidated"}}\n\n'
    ]


@pytest.mark.asyncio
async def test_pages_dossier_delegates_trusted_principal_to_the_core_service(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pages must not replace the core Persona grant/error contract itself."""

    from tests.test_scoped_api import _principal, _service
    from sylanne_alpha.webui_routes import WebUIRoutes

    service, _repository, registry, scope, _relation = _service(tmp_path)
    principal = _principal("principal_v1_pages_dossier")

    class Plugin:
        _scoped_api_service = service
        _scope_runtime_registry = registry
        _scoped_api_principal_scope_grant = staticmethod(lambda *_args: None)
        _scoped_api_principal_persona_grant = staticmethod(lambda *_args: None)

        @staticmethod
        def _scoped_api_principal_from_authenticated_host(
            host: object,
            identity: object,
        ) -> ScopedPrincipal | None:
            return principal if (host, identity) == ("pages", "dashboard-user") else None

    plugin = Plugin()
    service._principal_scope_grant = plugin._scoped_api_principal_scope_grant
    service._principal_persona_grant = plugin._scoped_api_principal_persona_grant
    core_dossier = service.persona_dossier_payload
    calls: list[tuple[object, object, object]] = []

    def delegated_dossier(
        bot_ref: object,
        persona_ref: object,
        *,
        principal: object,
    ) -> dict[str, object]:
        calls.append((bot_ref, persona_ref, principal))
        return {"ok": True, "delegated": "pages"}

    monkeypatch.setattr(service, "persona_dossier_payload", delegated_dossier)
    web = ModuleType("astrbot.api.web")
    web.request = SimpleNamespace(
        username="dashboard-user",
        path_params={
            "bot_ref": scope.bot_ref.token,
            "persona_ref": scope.persona_ref.token,
        },
        query={},
    )
    monkeypatch.setitem(sys.modules, "astrbot.api.web", web)

    routes = WebUIRoutes(plugin)
    assert await routes.persona_dossier_handler() == {"ok": True, "delegated": "pages"}
    assert calls == [(scope.bot_ref.token, scope.persona_ref.token, principal)]

    expected_principal = principal

    def delegated_error(
        _bot_ref: object,
        _persona_ref: object,
        *,
        principal: object,
    ) -> ScopedApiError:
        assert principal == expected_principal
        return ScopedApiError(403, "scope_persona_not_owned")

    monkeypatch.setattr(service, "persona_dossier_payload", delegated_error)
    assert await routes.persona_dossier_handler() == {
        "error": "scope_persona_not_owned",
        "status": 403,
    }

    def read_must_not_run(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("an ungranted principal must not read the dossier")

    monkeypatch.setattr(_repository, "read_persona_dossier", read_must_not_run)
    monkeypatch.setattr(service, "persona_dossier_payload", core_dossier)
    assert await routes.persona_dossier_handler() == {
        "error": "scope_principal_forbidden",
        "status": 403,
    }

    service._principal_persona_grant = lambda *_args: None
    assert await routes.persona_dossier_handler() == {
        "error": "scope_principal_forbidden",
        "status": 403,
    }
    assert calls == [(scope.bot_ref.token, scope.persona_ref.token, principal)]


@pytest.mark.asyncio
async def test_aiohttp_dossier_delegates_trusted_principal_to_the_core_service(
    tmp_path,
) -> None:
    from aiohttp import ClientSession

    from sylanne_alpha import webui_server
    from tests.test_scoped_api import _principal, _service

    service, _repository, registry, scope, _relation = _service(tmp_path)
    principal = _principal("principal_v1_aiohttp_dossier")
    bearer = "aiohttp-dossier-token"

    class Plugin:
        _scoped_api_service = service
        _scope_runtime_registry = registry
        _scoped_api_principal_scope_grant = staticmethod(lambda *_args: None)
        _scoped_api_principal_persona_grant = staticmethod(lambda *_args: None)

        @staticmethod
        def _scoped_api_principal_from_authenticated_host(
            host: object,
            identity: object,
        ) -> ScopedPrincipal | None:
            return principal if (host, identity) == ("standalone", bearer) else None

    plugin = Plugin()
    service._principal_scope_grant = plugin._scoped_api_principal_scope_grant
    service._principal_persona_grant = plugin._scoped_api_principal_persona_grant
    calls: list[tuple[object, object, object]] = []

    def delegated_dossier(
        bot_ref: object,
        persona_ref: object,
        *,
        principal: object,
    ) -> dict[str, object]:
        calls.append((bot_ref, persona_ref, principal))
        return {"ok": True, "delegated": "aiohttp"}

    service.persona_dossier_payload = delegated_dossier
    path = (
        f"/api/v1/bots/{scope.bot_ref.token}/personas/{scope.persona_ref.token}/dossier"
    )
    port = _unused_local_port()
    previous_token = webui_server._active_token
    previous_plugin = webui_server._active_plugin
    webui_server._active_token = bearer
    task = asyncio.create_task(
        webui_server.start_webui_server(plugin, host="127.0.0.1", port=port)
    )
    try:
        async with ClientSession() as client:
            response = None
            for _ in range(100):
                try:
                    response = await client.get(
                        f"http://127.0.0.1:{port}{path}",
                        headers={"Authorization": f"Bearer {bearer}"},
                    )
                    break
                except OSError:
                    await asyncio.sleep(0.01)
            assert response is not None
            async with response:
                assert response.status == 200
                assert await response.json() == {"ok": True, "delegated": "aiohttp"}
        assert calls == [(scope.bot_ref.token, scope.persona_ref.token, principal)]
    finally:
        task.cancel()
        await task
        webui_server._active_token = previous_token
        webui_server._active_plugin = previous_plugin


def test_stdlib_dossier_delegates_trusted_principal_to_the_core_service(tmp_path) -> None:
    from sylanne_alpha import webui_server
    from tests.test_scoped_api import _principal, _service

    service, _repository, registry, scope, _relation = _service(tmp_path)
    principal = _principal("principal_v1_stdlib_dossier")
    bearer = "stdlib-dossier-token"

    class Plugin:
        _scoped_api_service = service
        _scope_runtime_registry = registry
        _scoped_api_principal_scope_grant = staticmethod(lambda *_args: None)
        _scoped_api_principal_persona_grant = staticmethod(lambda *_args: None)

        @staticmethod
        def _scoped_api_principal_from_authenticated_host(
            host: object,
            identity: object,
        ) -> ScopedPrincipal | None:
            return principal if (host, identity) == ("standalone", bearer) else None

    plugin = Plugin()
    service._principal_scope_grant = plugin._scoped_api_principal_scope_grant
    service._principal_persona_grant = plugin._scoped_api_principal_persona_grant
    calls: list[tuple[object, object, object]] = []

    def delegated_dossier(
        bot_ref: object,
        persona_ref: object,
        *,
        principal: object,
    ) -> dict[str, object]:
        calls.append((bot_ref, persona_ref, principal))
        return {"ok": True, "delegated": "stdlib"}

    service.persona_dossier_payload = delegated_dossier
    path = (
        f"/api/v1/bots/{scope.bot_ref.token}/personas/{scope.persona_ref.token}/dossier"
    )
    previous_token = webui_server._active_token
    previous_plugin = webui_server._active_plugin
    webui_server._active_token = bearer
    webui_server.start_webui_thread_server(plugin, host="127.0.0.1", port=0)
    try:
        assert webui_server._httpd is not None
        port = int(webui_server._httpd.server_address[1])
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        try:
            connection.request(
                "GET",
                path,
                headers={"Authorization": f"Bearer {bearer}"},
            )
            response = connection.getresponse()
            assert response.status == 200
            assert json.loads(response.read()) == {"ok": True, "delegated": "stdlib"}
        finally:
            connection.close()
        assert calls == [(scope.bot_ref.token, scope.persona_ref.token, principal)]
    finally:
        asyncio.run(webui_server.stop_webui_server())
        webui_server._active_token = previous_token
        webui_server._active_plugin = previous_plugin


@pytest.mark.asyncio
async def test_aiohttp_scoped_host_uses_only_verified_bearer_for_principal(
    tmp_path,
) -> None:
    from aiohttp import ClientSession

    from sylanne_alpha import webui_server
    from tests.test_scoped_api import _principal, _service

    service, _repository, registry, scope, relation = _service(tmp_path)
    principal = _principal("principal_v1_standalone_authenticated")
    bearer = "standalone-contract-token"

    class Plugin:
        _scoped_api_service = service
        _scope_runtime_registry = registry

        def __init__(self) -> None:
            self.issuer_calls = 0
            self.grant_enabled = True

        def _scoped_api_principal_from_authenticated_host(
            self,
            host: object,
            identity: object,
        ) -> ScopedPrincipal | None:
            self.issuer_calls += 1
            return principal if (host, identity) == ("standalone", bearer) else None

        def _scoped_api_principal_scope_grant(
            self,
            _candidate_principal: object,
            _candidate_scope: object,
            _action: object,
        ) -> object | None:
            # Revoke the map after issuance to model a current authenticated
            # host with no current relation authority.
            return relation if self.grant_enabled else None

        _scoped_api_principal_persona_grant = staticmethod(lambda *_args: None)

    plugin = Plugin()
    service._principal_scope_grant = plugin._scoped_api_principal_scope_grant
    service._principal_persona_grant = plugin._scoped_api_principal_persona_grant
    nonce = service.issue_nonce(
        scope,
        relation,
        turn_generation=7,
        principal=principal,
        endpoint="scope",
    )
    plugin.grant_enabled = False
    url_path = scoped_api_path(
        ScopeApiPathEcho(
            bot_ref=scope.bot_ref.token,
            persona_ref=scope.persona_ref.token,
            session_ref=scope.session_ref.token,
        )
    )
    port = _unused_local_port()
    previous_token = webui_server._active_token
    previous_plugin = webui_server._active_plugin
    previous_csrf = webui_server._csrf_token
    webui_server._active_token = bearer
    webui_server._csrf_token = "aiohttp-scoped-csrf"
    task = asyncio.create_task(
        webui_server.start_webui_server(plugin, host="127.0.0.1", port=port)
    )
    try:
        async with ClientSession() as client:
            forged_headers = {SCOPE_NONCE_HEADER: nonce, "X-Sylanne-Principal": "forged"}
            response = None
            for _ in range(100):
                try:
                    response = await client.get(
                        f"http://127.0.0.1:{port}{url_path}?principal=forged&scope_nonce={nonce}",
                        headers=forged_headers,
                        data=b'{"principal":"forged"}',
                    )
                    break
                except OSError:
                    await asyncio.sleep(0.01)
            assert response is not None
            async with response:
                assert response.status == 401
                assert await response.json() == {"error": "unauthorized"}
            assert plugin.issuer_calls == 0
            assert nonce in service._pending_nonces

            async with client.get(
                f"http://127.0.0.1:{port}{url_path}?scope_nonce={nonce}",
                headers={"Authorization": f"Bearer {bearer}"},
            ) as query_nonce:
                assert query_nonce.status == 400
                assert await query_nonce.json() == {"error": "scope_nonce_required"}
            assert plugin.issuer_calls == 1
            assert nonce in service._pending_nonces

            async with client.get(
                f"http://127.0.0.1:{port}{url_path}?principal=forged",
                headers={
                    "Authorization": f"Bearer {bearer}",
                    SCOPE_NONCE_HEADER: nonce,
                    "X-Sylanne-Principal": "principal_v1_forged",
                },
            ) as no_grant:
                assert no_grant.status == 403
                assert await no_grant.json() == {"error": "scope_principal_forbidden"}

            plugin.grant_enabled = True
            mutation_nonce = service.issue_nonce(
                scope,
                relation,
                turn_generation=7,
                principal=principal,
                endpoint="memory/meltdown",
                method="POST",
            )
            async with client.post(
                f"http://127.0.0.1:{port}{url_path}/memory/meltdown"
                f"?scope_nonce={mutation_nonce}",
                headers={
                    "Authorization": f"Bearer {bearer}",
                    "X-CSRF-Token": "aiohttp-scoped-csrf",
                },
                data=b"not-json-and-not-a-header-nonce",
            ) as body_nonce:
                assert body_nonce.status == 400
                assert await body_nonce.json() == {"error": "scope_nonce_required"}
            assert mutation_nonce in service._pending_nonces
    finally:
        task.cancel()
        await task
        webui_server._active_token = previous_token
        webui_server._active_plugin = previous_plugin
        webui_server._csrf_token = previous_csrf


@pytest.mark.asyncio
async def test_aiohttp_scoped_websocket_emits_one_invalidation_then_closes(
    tmp_path,
) -> None:
    from aiohttp import ClientSession, WSMsgType

    from sylanne_alpha import webui_server
    from tests.test_scoped_api import _principal, _service

    service, _repository, registry, scope, relation = _service(tmp_path)
    principal = _principal("principal_v1_standalone_ws")
    bearer = "standalone-websocket-token"

    class Plugin:
        _scoped_api_service = service
        _scope_runtime_registry = registry

        @staticmethod
        def _scoped_api_principal_from_authenticated_host(
            host: object,
            identity: object,
        ) -> ScopedPrincipal | None:
            return principal if (host, identity) == ("standalone", bearer) else None

        @staticmethod
        def _scoped_api_principal_scope_grant(
            candidate_principal: object,
            candidate_scope: object,
            action: object,
        ) -> object | None:
            if (
                candidate_principal == principal
                and candidate_scope == scope
                and action == "GET:ws"
            ):
                return relation
            return None

        _scoped_api_principal_persona_grant = staticmethod(lambda *_args: None)

    plugin = Plugin()
    service._principal_scope_grant = plugin._scoped_api_principal_scope_grant
    service._principal_persona_grant = plugin._scoped_api_principal_persona_grant
    nonce = service.issue_nonce(
        scope,
        relation,
        turn_generation=7,
        principal=principal,
        endpoint="ws",
    )
    path = scoped_api_path(
        ScopeApiPathEcho(
            bot_ref=scope.bot_ref.token,
            persona_ref=scope.persona_ref.token,
            session_ref=scope.session_ref.token,
        ),
        "ws",
    )
    port = _unused_local_port()
    previous_token = webui_server._active_token
    previous_plugin = webui_server._active_plugin
    webui_server._active_token = bearer
    task = asyncio.create_task(
        webui_server.start_webui_server(plugin, host="127.0.0.1", port=port)
    )
    try:
        async with ClientSession() as client:
            socket = None
            for _ in range(100):
                try:
                    socket = await client.ws_connect(
                        f"http://127.0.0.1:{port}{path}",
                        headers={
                            "Authorization": f"Bearer {bearer}",
                            SCOPE_NONCE_HEADER: nonce,
                        },
                    )
                    break
                except OSError:
                    await asyncio.sleep(0.01)
            assert socket is not None
            first_frame = await socket.receive_json(timeout=3)
            assert first_frame["event"] == "scope_status"
            assert isinstance(first_frame["data"], dict)
            registry.release_session(scope)
            assert await socket.receive_json(timeout=3) == {
                "event": "scope_invalidated",
                "data": {"error": "scope_invalidated"},
            }
            closed = await socket.receive(timeout=3)
            assert closed.type in {WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.CLOSING}
            await socket.close()
    finally:
        task.cancel()
        await task
        webui_server._active_token = previous_token
        webui_server._active_plugin = previous_plugin


@pytest.mark.asyncio
async def test_aiohttp_scoped_sse_emits_one_invalidation_then_eof(tmp_path) -> None:
    from aiohttp import ClientSession

    from sylanne_alpha import webui_server
    from tests.test_scoped_api import _principal, _service

    service, _repository, registry, scope, relation = _service(tmp_path)
    principal = _principal("principal_v1_standalone_sse")
    bearer = "standalone-sse-token"

    class Plugin:
        _scoped_api_service = service
        _scope_runtime_registry = registry

        @staticmethod
        def _scoped_api_principal_from_authenticated_host(
            host: object,
            identity: object,
        ) -> ScopedPrincipal | None:
            return principal if (host, identity) == ("standalone", bearer) else None

        @staticmethod
        def _scoped_api_principal_scope_grant(
            candidate_principal: object,
            candidate_scope: object,
            action: object,
        ) -> object | None:
            if (
                candidate_principal == principal
                and candidate_scope == scope
                and action == "GET:stream"
            ):
                return relation
            return None

        _scoped_api_principal_persona_grant = staticmethod(lambda *_args: None)

    plugin = Plugin()
    service._principal_scope_grant = plugin._scoped_api_principal_scope_grant
    service._principal_persona_grant = plugin._scoped_api_principal_persona_grant
    nonce = service.issue_nonce(
        scope,
        relation,
        turn_generation=7,
        principal=principal,
        endpoint="stream",
    )
    path = scoped_api_path(
        ScopeApiPathEcho(
            bot_ref=scope.bot_ref.token,
            persona_ref=scope.persona_ref.token,
            session_ref=scope.session_ref.token,
        ),
        "stream",
    )
    port = _unused_local_port()
    previous_token = webui_server._active_token
    previous_plugin = webui_server._active_plugin
    webui_server._active_token = bearer
    task = asyncio.create_task(
        webui_server.start_webui_server(plugin, host="127.0.0.1", port=port)
    )
    try:
        async with ClientSession() as client:
            response = None
            for _ in range(100):
                try:
                    response = await client.get(
                        f"http://127.0.0.1:{port}{path}",
                        headers={
                            "Authorization": f"Bearer {bearer}",
                            SCOPE_NONCE_HEADER: nonce,
                        },
                    )
                    break
                except OSError:
                    await asyncio.sleep(0.01)
            assert response is not None
            async with response:
                assert response.status == 200
                first_frame = await response.content.readuntil(b"\n\n")
                assert first_frame.startswith(b"event: scope_status\n")
                registry.release_session(scope)
                invalidated = await response.content.readuntil(b"\n\n")
                assert invalidated == (
                    b"event: scope_invalidated\n"
                    b'data: {"event":"scope_invalidated","data":{"error":"scope_invalidated"}}\n\n'
                )
                assert await response.content.read() == b""
    finally:
        task.cancel()
        await task
        webui_server._active_token = previous_token
        webui_server._active_plugin = previous_plugin


@pytest.mark.asyncio
async def test_aiohttp_legacy_paths_are_gone_before_auth_or_registry_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aiohttp import ClientSession, web

    from sylanne_alpha import webui_server
    from sylanne_alpha.webui_routes import LEGACY_SCOPED_PRIVATE_ROUTES

    class NoLegacyState:
        def __getattr__(self, name: str) -> object:
            raise AssertionError(f"legacy request accessed plugin attribute {name!r}")

    port = _unused_local_port()
    previous_token = webui_server._active_token
    previous_plugin = webui_server._active_plugin
    webui_server._active_token = "legacy-contract-token"

    async def websocket_prepare_must_not_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("a retired WebSocket path must not be prepared")

    monkeypatch.setattr(web.WebSocketResponse, "prepare", websocket_prepare_must_not_run)
    task = asyncio.create_task(
        webui_server.start_webui_server(NoLegacyState(), host="127.0.0.1", port=port)
    )
    try:
        async with ClientSession() as client:
            response = None
            for _ in range(100):
                try:
                    response = await client.post(
                        f"http://127.0.0.1:{port}/api/memory_meltdown?session=forged",
                        data=b'{"scope_nonce":"forged"}',
                    )
                    break
                except OSError:
                    await asyncio.sleep(0.01)
            assert response is not None
            async with response:
                assert response.status == 410
                assert await response.json() == {"error": "scope_required"}

            for legacy_path, methods in LEGACY_SCOPED_PRIVATE_ROUTES:
                async with client.request(
                    methods[0],
                    f"http://127.0.0.1:{port}{legacy_path}?session=forged",
                    data=b'{"scope_nonce":"forged"}',
                ) as legacy:
                    assert legacy.status == 410
                    assert await legacy.json() == {"error": "scope_required"}

            for path in (
                "/api/v1/bots/forged/personas/forged/sessions/forged/ws/state",
            ):
                async with client.get(f"http://127.0.0.1:{port}{path}") as legacy:
                    assert legacy.status == 410
                    assert await legacy.json() == {"error": "scope_required"}
    finally:
        task.cancel()
        await task
        webui_server._active_token = previous_token
        webui_server._active_plugin = previous_plugin


def test_stdlib_legacy_paths_are_gone_before_auth_csrf_or_body_parsing() -> None:
    from sylanne_alpha import webui_server
    from sylanne_alpha.webui_routes import LEGACY_SCOPED_PRIVATE_ROUTES

    class NoLegacyState:
        def __getattr__(self, name: str) -> object:
            raise AssertionError(f"legacy request accessed plugin attribute {name!r}")

    previous_token = webui_server._active_token
    previous_plugin = webui_server._active_plugin
    webui_server._active_token = "legacy-contract-token"
    webui_server.start_webui_thread_server(NoLegacyState(), host="127.0.0.1", port=0)
    try:
        assert webui_server._httpd is not None
        port = int(webui_server._httpd.server_address[1])
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        try:
            for legacy_path, methods in LEGACY_SCOPED_PRIVATE_ROUTES:
                method = methods[0]
                body = b'{"scope_nonce":"forged"}' if method == "POST" else None
                connection.request(
                    method,
                    f"{legacy_path}?session=forged",
                    body=body,
                )
                response = connection.getresponse()
                assert response.status == 410
                assert response.read() == b'{"error": "scope_required"}'

            connection.request("OPTIONS", "/api/purge_data?session=forged")
            options = connection.getresponse()
            assert options.status == 410
            assert options.read() == b'{"error": "scope_required"}'
        finally:
            connection.close()
    finally:
        asyncio.run(webui_server.stop_webui_server())
        webui_server._active_token = previous_token
        webui_server._active_plugin = previous_plugin


def test_stdlib_scoped_http_uses_bearer_and_header_nonce_only(tmp_path) -> None:
    from sylanne_alpha import webui_server
    from tests.test_scoped_api import _principal, _service

    service, _repository, registry, scope, relation = _service(tmp_path)
    principal = _principal("principal_v1_stdlib_authenticated")
    bearer = "stdlib-contract-token"

    class Plugin:
        _scoped_api_service = service
        _scope_runtime_registry = registry

        def __init__(self) -> None:
            self.issuer_calls = 0
            self.grant_enabled = True

        def _scoped_api_principal_from_authenticated_host(
            self,
            host: object,
            identity: object,
        ) -> ScopedPrincipal | None:
            self.issuer_calls += 1
            return principal if (host, identity) == ("standalone", bearer) else None

        def _scoped_api_principal_scope_grant(
            self,
            _candidate_principal: object,
            _candidate_scope: object,
            _action: object,
        ) -> object | None:
            return relation if self.grant_enabled else None

        _scoped_api_principal_persona_grant = staticmethod(lambda *_args: None)

    plugin = Plugin()
    service._principal_scope_grant = plugin._scoped_api_principal_scope_grant
    service._principal_persona_grant = plugin._scoped_api_principal_persona_grant
    nonce = service.issue_nonce(
        scope,
        relation,
        turn_generation=7,
        principal=principal,
        endpoint="scope",
    )
    plugin.grant_enabled = False
    path = scoped_api_path(
        ScopeApiPathEcho(
            bot_ref=scope.bot_ref.token,
            persona_ref=scope.persona_ref.token,
            session_ref=scope.session_ref.token,
        )
    )
    previous_token = webui_server._active_token
    previous_plugin = webui_server._active_plugin
    previous_csrf = webui_server._csrf_token
    webui_server._active_token = bearer
    webui_server._csrf_token = "stdlib-scoped-csrf"
    webui_server.start_webui_thread_server(plugin, host="127.0.0.1", port=0)
    try:
        assert webui_server._httpd is not None
        port = int(webui_server._httpd.server_address[1])
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        try:
            connection.request(
                "GET",
                f"{path}?principal=forged&scope_nonce={nonce}",
                headers={
                    "Authorization": "Bearer forged",
                    SCOPE_NONCE_HEADER: nonce,
                    "X-Sylanne-Principal": "principal_v1_forged",
                },
            )
            unauthorized = connection.getresponse()
            assert unauthorized.status == 401
            assert json.loads(unauthorized.read()) == {"error": "unauthorized"}
            assert plugin.issuer_calls == 0
            assert nonce in service._pending_nonces

            connection.request(
                "GET",
                f"{path}?scope_nonce={nonce}",
                headers={"Authorization": f"Bearer {bearer}"},
            )
            query_nonce = connection.getresponse()
            assert query_nonce.status == 400
            assert json.loads(query_nonce.read()) == {"error": "scope_nonce_required"}
            assert nonce in service._pending_nonces

            connection.request(
                "GET",
                path,
                headers={
                    "Authorization": f"Bearer {bearer}",
                    SCOPE_NONCE_HEADER: nonce,
                    "X-Sylanne-Principal": "principal_v1_forged",
                },
            )
            no_grant = connection.getresponse()
            assert no_grant.status == 403
            assert json.loads(no_grant.read()) == {
                "error": "scope_principal_forbidden"
            }

            plugin.grant_enabled = True
            mutation_nonce = service.issue_nonce(
                scope,
                relation,
                turn_generation=7,
                principal=principal,
                endpoint="memory/meltdown",
                method="POST",
            )
            connection.request(
                "POST",
                f"{path}/memory/meltdown?scope_nonce={mutation_nonce}",
                body=b"not-json-and-not-a-header-nonce",
                headers={
                    "Authorization": f"Bearer {bearer}",
                    "X-CSRF-Token": "stdlib-scoped-csrf",
                },
            )
            body_nonce = connection.getresponse()
            assert body_nonce.status == 400
            assert json.loads(body_nonce.read()) == {"error": "scope_nonce_required"}
            assert mutation_nonce in service._pending_nonces

            connection.request("OPTIONS", path)
            options = connection.getresponse()
            assert options.status == 204
            assert SCOPE_NONCE_HEADER in {
                value.strip()
                for value in options.getheader("Access-Control-Allow-Headers", "").split(",")
            }
            assert options.read() == b""
        finally:
            connection.close()
    finally:
        asyncio.run(webui_server.stop_webui_server())
        webui_server._active_token = previous_token
        webui_server._active_plugin = previous_plugin
        webui_server._csrf_token = previous_csrf
