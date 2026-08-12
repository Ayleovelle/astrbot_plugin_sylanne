from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest

from sylanne_alpha.plugin_services import PluginServices
from sylanne_alpha.proactive_scheduler import ProactiveScheduler
from sylanne_alpha.public_api import PublicAPI


class _Map(dict[str, Any]):
    def set(self, key: str, value: Any) -> None:
        self[key] = value


class _PluginTrap:
    def __init__(self) -> None:
        self.config = {
            "enable_moral_repair_state": False,
            "enable_proactive_speech_dispatch": False,
            "proactive_speech_dispatch_cooldown_seconds": 999.0,
            "proactive_speech_min_idle_seconds": 999.0,
            "sylanne_memory_embedding_provider_id": "plugin-provider",
        }
        self._config = self.config
        self.context = SimpleNamespace(name="plugin-context")
        self._store = SimpleNamespace(
            proactive_candidate_sessions=_Map(),
            hosts=_Map(),
            last_user_message_time=_Map(),
            last_bot_expression_time=_Map(),
        )

    def _host(self, _session_key: str) -> Any:
        raise AssertionError("explicit services must not use plugin host lookup")

    def _session_key(self, _event: Any = None, _session_key: str = "") -> str:
        raise AssertionError("explicit services must not use plugin session lookup")

    def _observed_now(self) -> float:
        raise AssertionError("explicit services must not use plugin observed clock")

    def _event_time(self, _now: float) -> dict[str, float]:
        raise AssertionError("explicit services must not use plugin event-time callbacks")

    async def request_proactive_speech_dispatch(
        self, _event: Any, *, dry_run: bool
    ) -> dict[str, Any]:
        raise AssertionError(
            f"explicit services must not use plugin dispatch callbacks: {dry_run=}"
        )


def _services(
    *,
    name: str,
    now: float,
    moral_enabled: bool,
    dispatch_enabled: bool,
) -> tuple[PluginServices, Any, list[tuple[Any, str]]]:
    class _Host:
        def __init__(self) -> None:
            self.events: list[Any] = []

        def _event_result(self, event: Any) -> dict[str, float]:
            self.events.append(event)
            return {
                "now": float(event.now),
                "event_epoch": float(event.event_time["epoch"]),
            }

        def on_request(self, event: Any) -> dict[str, float]:
            return self._event_result(event)

        def on_response(self, event: Any) -> dict[str, float]:
            return self._event_result(event)

        def on_proactive_check(self, event: Any) -> dict[str, Any]:
            self.events.append(event)
            return {
                "schema_version": "test.v1",
                "session_key": f"service-session-{name}",
                "decision": {"action": "wait"},
                "guard": {"allowed": False},
                "host_payload": {
                    "reason": "test fence",
                    "reason_code": "test_fence",
                },
            }

    host = _Host()
    session_calls: list[tuple[Any, str]] = []

    def session_key(event: Any = None, explicit: str = "") -> str:
        session_calls.append((event, explicit))
        return explicit or f"service-session-{name}" if event is not None else explicit

    provider = SimpleNamespace(
        provider_config={
            "id": f"service-provider-{name}",
            "embedding_model": "embedding-test",
            "embedding_dimensions": 8,
        }
    )
    context = SimpleNamespace(get_all_embedding_providers=lambda: [provider])
    services = PluginServices(
        config={
            "enable_moral_repair_state": moral_enabled,
            "enable_proactive_speech_dispatch": dispatch_enabled,
            "proactive_speech_dispatch_cooldown_seconds": 120.0,
            "proactive_speech_min_idle_seconds": 45.0,
            "sylanne_memory_embedding_provider_id": f"service-provider-{name}",
        },
        context=context,
        host_fn=lambda _session_key: host,
        session_key_fn=session_key,
        observed_now_fn=lambda: now,
    )
    return services, host, session_calls


def test_public_api_explicit_services_are_the_only_migrated_read_authority() -> None:
    plugin = _PluginTrap()
    services, host, session_calls = _services(
        name="a",
        now=1234.5,
        moral_enabled=True,
        dispatch_enabled=True,
    )
    api = PublicAPI(plugin, services=services)
    event = SimpleNamespace(
        unified_msg_origin="raw-plugin-session",
        session_id="raw-plugin-session",
        sender_id="sender-a",
        sender_name="Alice",
    )

    assert api._p is plugin
    assert api._plugin is plugin
    assert api._services is services
    assert api._host("ignored") is host
    assert api._session_key(event) == "service-session-a"
    assert api._agent_identity(event) == "service-session-a::agent:sender-a"

    async def exercise() -> None:
        moral = [item async for item in api.get_bot_moral_repair_state_tool()]
        assert json.loads(moral[0])["enabled"] is True
        profile = await api.get_agent_identity_profile(event)
        assert profile["conversation_id"] == "service-session-a"
        assert profile["updated_at"] == 1234.5
        trail = await api.get_agent_trail(event)
        assert trail["session_key"] == "service-session-a"
        observation = await api.observe_response("service-session-a")
        assert observation == {"now": 1234.5, "event_epoch": 1234.5}
        settings = await api._sylanne_memory_settings_page_payload()
        assert settings["current_embedding_provider_id"] == "service-provider-a"
        assert settings["embedding_providers"] == [
            {
                "id": "service-provider-a",
                "model": "embedding-test",
                "dimensions": 8,
            }
        ]

    asyncio.run(exercise())
    assert session_calls == [(event, "")] * 4


def test_proactive_scheduler_explicit_services_do_not_mix_plugin_config_or_time() -> None:
    plugin_a = _PluginTrap()
    plugin_b = plugin_a
    services_a, host_a, calls_a = _services(
        name="a",
        now=1000.0,
        moral_enabled=False,
        dispatch_enabled=True,
    )
    services_b, host_b, calls_b = _services(
        name="b",
        now=2000.0,
        moral_enabled=False,
        dispatch_enabled=False,
    )
    scheduler_a = ProactiveScheduler(plugin_a, services=services_a)
    scheduler_b = ProactiveScheduler(plugin_b, services=services_b)
    event = SimpleNamespace(unified_msg_origin="raw-plugin-session")

    assert scheduler_a._p is scheduler_a._plugin is plugin_a
    assert scheduler_b._p is scheduler_b._plugin is plugin_b
    assert scheduler_a._services is services_a
    assert scheduler_b._services is services_b
    assert scheduler_a._host("ignored") is host_a
    assert scheduler_b._host("ignored") is host_b
    assert scheduler_a._session_key(event) == "service-session-a"
    assert scheduler_b._session_key(event) == "service-session-b"
    assert scheduler_a.derive_dispatch_policy(session_key="service-session-a")[
        "should_dispatch"
    ] is True
    assert scheduler_b.derive_dispatch_policy(session_key="service-session-b")[
        "should_dispatch"
    ] is False
    assert scheduler_a.build_dispatch_request(session_key="service-session-a")[
        "quiet_gate"
    ] == {"min_idle_seconds": 45.0}

    scheduler_a.record_message_time("service-session-a")
    scheduler_b.record_message_time("service-session-b")
    assert scheduler_a._last_message_times["service-session-a"] == 1000.0
    assert scheduler_b._last_message_times["service-session-b"] == 2000.0
    assert calls_a == [(event, "")]
    assert calls_b == [(event, "")]


def test_explicit_services_without_observed_clock_fail_closed() -> None:
    plugin = _PluginTrap()
    services = PluginServices(
        session_key_fn=lambda _event=None, explicit="": explicit or "service-session",
        host_fn=lambda _session_key: object(),
    )

    with pytest.raises(RuntimeError, match="observed time service is unavailable"):
        PublicAPI(plugin, services=services)._observed_now()
    with pytest.raises(RuntimeError, match="observed time service is unavailable"):
        ProactiveScheduler(plugin, services=services)._observed_now()


def test_explicit_observatory_routes_never_select_a_legacy_first_host() -> None:
    plugin = _PluginTrap()
    plugin._store.hosts["ambient-plugin-session"] = object()
    api = PublicAPI(
        plugin,
        services=PluginServices(
            session_key_fn=lambda _event=None, _explicit="": "service-session",
            host_fn=lambda _session_key: object(),
            observed_now_fn=lambda: 1.0,
        ),
    )
    selected: list[str] = []

    async def observatory(*, session_key: str) -> dict[str, Any]:
        selected.append(session_key)
        return {"ok": True, "session_key": session_key}

    api.sylanne_observatory = observatory  # type: ignore[method-assign]
    api._sylanne_lineage_observatory_page_payload = (  # type: ignore[method-assign]
        lambda session_key: selected.append(session_key) or {"session_key": session_key}
    )

    assert asyncio.run(api._observatory_route_handler()) == {
        "ok": False,
        "error": "scope_unavailable",
    }
    assert api._lineage_observatory_route_payload() == {
        "ok": False,
        "error": "scope_unavailable",
    }
    assert selected == []


def test_explicit_public_api_builds_event_time_without_plugin_callback() -> None:
    plugin = _PluginTrap()
    services, host, _calls = _services(
        name="isolated",
        now=3141.5,
        moral_enabled=False,
        dispatch_enabled=False,
    )
    api = PublicAPI(plugin, services=services)

    async def exercise() -> None:
        request = await api.observe_request("service-session-isolated")
        response = await api.observe_response("service-session-isolated")
        proactive = await api.proactive_sylanne(
            session_key="service-session-isolated"
        )
        assert request == {"now": 3141.5, "event_epoch": 3141.5}
        assert response == {"now": 3141.5, "event_epoch": 3141.5}
        assert proactive["decision"]["reason_code"] == "test_fence"

    asyncio.run(exercise())
    assert [event.event_time for event in host.events] == [
        {"epoch": 3141.5},
        {"epoch": 3141.5},
        {"epoch": 3141.5},
    ]


def test_explicit_scheduler_run_once_never_uses_plugin_dispatch_callback() -> None:
    plugin = _PluginTrap()
    plugin._store.proactive_candidate_sessions["ambient-plugin-session"] = {
        "event": SimpleNamespace(unified_msg_origin="ambient-plugin-session")
    }
    scheduler = ProactiveScheduler(
        plugin,
        services=PluginServices(
            config={"enable_proactive_speech_dispatch": True},
            session_key_fn=lambda _event=None, explicit="": explicit,
            host_fn=lambda _session_key: object(),
            observed_now_fn=lambda: 1.0,
        ),
    )

    assert asyncio.run(scheduler.run_once()) == {"checked": 1, "dispatched": 0}


def test_missing_explicit_host_service_returns_neutral_denials() -> None:
    plugin = _PluginTrap()
    services = PluginServices(
        session_key_fn=lambda _event=None, explicit="": explicit or "service-session",
        observed_now_fn=lambda: 1.0,
    )
    scheduler = ProactiveScheduler(plugin, services=services)
    api = PublicAPI(plugin, services=services)

    async def exercise() -> None:
        assert await scheduler.get_speech_decision(object()) == {
            "should_speak": False,
            "reason": "host_unavailable",
        }
        assert await api.build_emotion_memory_payload(object()) == {
            "ok": False,
            "error": "host_unavailable",
        }

    asyncio.run(exercise())


def test_default_services_keep_exact_plugin_aliases_and_callbacks() -> None:
    plugin = _PluginTrap()
    plugin._host = lambda session_key: ("plugin-host", session_key)  # type: ignore[method-assign]
    plugin._session_key = (  # type: ignore[method-assign]
        lambda _event=None, session_key="": session_key or "plugin-session"
    )
    plugin._observed_now = lambda: 2718.0  # type: ignore[method-assign]

    api = PublicAPI(plugin)
    scheduler = ProactiveScheduler(plugin)

    assert api._p is api._plugin is plugin
    assert scheduler._p is scheduler._plugin is plugin
    assert api._host("one") == ("plugin-host", "one")
    assert scheduler._host("two") == ("plugin-host", "two")
    assert api._session_key() == "plugin-session"
    assert scheduler._observed_now() == 2718.0


def test_proactive_decision_without_a_service_session_never_uses_default_host() -> None:
    plugin = _PluginTrap()
    host_calls: list[str] = []
    services = PluginServices(
        config={"enable_proactive_speech_dispatch": True},
        host_fn=lambda session_key: host_calls.append(session_key),
        session_key_fn=lambda _event=None, _explicit="": "",
        observed_now_fn=lambda: 1.0,
    )
    scheduler = ProactiveScheduler(plugin, services=services)
    api = PublicAPI(plugin, services=services)

    event = SimpleNamespace(unified_msg_origin="raw-session-must-not-fallback")
    result = asyncio.run(
        scheduler.get_speech_decision(
            event,
            session_key="explicit-session-must-not-fallback",
        )
    )
    memory_result = asyncio.run(
        api.build_emotion_memory_payload(
            event,
            session_key="explicit-session-must-not-fallback",
        )
    )

    assert result == {"should_speak": False, "reason": "no_session_key"}
    assert memory_result == {"ok": False, "error": "session_unavailable"}
    assert host_calls == []
