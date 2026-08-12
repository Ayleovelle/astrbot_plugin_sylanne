from __future__ import annotations

from types import SimpleNamespace

import pytest

from sylanne_alpha.public_api import PublicAPI
from sylanne_alpha.scope_contracts import (
    BotRef,
    PersonaRevisionRef,
    SessionRef,
    SessionScope,
)
from sylanne_alpha.v2core.integration import _existing_runtime_from_scope_or_legacy
from sylanne_alpha.webui_routes import WebUIRoutes
from tests.scope_fixtures import scope_storage_token


class _NoneReturningMap:
    def get(self, _key: str, _default: float = 0.0) -> None:
        return None


@pytest.mark.asyncio
async def test_observe_request_treats_missing_last_expression_time_as_absent() -> None:
    feedback_calls: list[tuple[str, float]] = []
    host = SimpleNamespace(
        kernel=SimpleNamespace(
            computation=SimpleNamespace(
                feedback=lambda outcome, *, dt: feedback_calls.append((outcome, dt))
            )
        ),
        on_request=lambda _event: {"ok": True},
    )
    plugin = SimpleNamespace(
        config={},
        _store=SimpleNamespace(last_bot_expression_time=_NoneReturningMap()),
        _host=lambda _session_key: host,
        _event_time=lambda observed_now: {"epoch": observed_now},
    )

    result = await PublicAPI(plugin).observe_request("session", now=42.0)

    assert result == {"ok": True}
    assert feedback_calls == []


def test_scope_api_path_rejects_non_string_request_components() -> None:
    with pytest.raises(ValueError, match="scoped request path components"):
        WebUIRoutes._scope_api_path_from_params(
            {
                "bot_ref": "bot_v1_valid",
                "persona_ref": "persona_v1_valid",
                "session_ref": None,
            }
        )


def test_existing_v2_runtime_fails_closed_for_non_iterable_registry_snapshot() -> None:
    bot = BotRef("bot_v1_pyright_guard", 1)
    scope = SessionScope(
        bot_ref=bot,
        persona_ref=PersonaRevisionRef(
            "persona_v1_pyright_guard",
            bot,
            "a" * 64,
            "b" * 64,
            1,
        ),
        session_ref=SessionRef("session_v1_pyright_guard", bot, 1),
        storage_token=scope_storage_token("pyright-guard"),
        scope_generation=1,
    )
    plugin = SimpleNamespace(
        _scope_runtime_registry=SimpleNamespace(
            is_live_session=lambda _scope: True,
            live_persona_runtimes=lambda: object(),
        )
    )

    assert _existing_runtime_from_scope_or_legacy(plugin, scope) is None
