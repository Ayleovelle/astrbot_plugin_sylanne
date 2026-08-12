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
        self._session_state = SimpleNamespace(
            proactive_dispatch_last_sent=_Map({"shared-session": 999.0})
        )
        self._proactive_dispatch_last_sent = {"shared-session": 999.0}
        self._proactive_dispatch_audit = {
            "shared-session": [
                {"feedback_status": "unanswered", "event_id": "ambient-event"}
            ]
        }

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

    async def _call_internal_assessor_llm(self, **_kwargs: Any) -> Any:
        raise AssertionError("explicit services must not use plugin assessor callbacks")


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

    assert asyncio.run(scheduler.run_once()) == {"checked": 0, "dispatched": 0}


def test_explicit_public_api_dispatch_tool_fails_closed_without_plugin_callback() -> None:
    plugin = _PluginTrap()
    api = PublicAPI(
        plugin,
        services=PluginServices(
            config={},
            session_key_fn=lambda _event=None, explicit="": explicit or "shared-session",
            observed_now_fn=lambda: 1.0,
        ),
    )

    async def exercise() -> dict[str, Any]:
        results = [
            json.loads(item)
            async for item in api.request_bot_proactive_speech_dispatch_tool(object())
        ]
        assert len(results) == 1
        return results[0]

    payload = asyncio.run(exercise())
    assert payload["kind"] == "proactive_speech_dispatch"
    assert payload["dry_run"] is True
    assert payload["dispatched"] is False
    assert payload["reason"] == "explicit_dispatch_capability_required"


def test_explicit_public_api_assessor_uses_only_injected_callback() -> None:
    plugin = _PluginTrap()
    calls: list[tuple[str, str, Any]] = []
    expected = SimpleNamespace(
        values={"valence": 0.75},
        confidence=0.9,
        label="service",
        source="service",
        reason="injected",
        appraisal={},
    )

    async def assess(
        *, session_key: str, text: str, event: Any = None, **_kwargs: Any
    ) -> Any:
        calls.append((session_key, text, event))
        return expected

    api = PublicAPI(
        plugin,
        services=PluginServices(config={}, assess_emotion_fn=assess),
    )
    event = object()

    result = asyncio.run(
        api._assess_emotion(
            session_key="shared-session",
            text="this is deliberately longer than the low signal threshold",
            event=event,
        )
    )

    assert result is expected
    assert calls == [
        (
            "shared-session",
            "this is deliberately longer than the low signal threshold",
            event,
        )
    ]


def test_missing_explicit_assessor_returns_neutral_without_plugin_callback() -> None:
    api = PublicAPI(_PluginTrap(), services=PluginServices(config={}))

    result = asyncio.run(
        api._assess_emotion(
            session_key="shared-session",
            text="this is deliberately longer than the low signal threshold",
        )
    )

    assert result.label == "neutral"
    assert result.source == "heuristic"
    assert result.reason == "assessor service unavailable"


def test_same_plugin_same_session_explicit_schedulers_keep_state_isolated() -> None:
    plugin = _PluginTrap()
    services_a, _host_a, _calls_a = _services(
        name="a",
        now=1000.0,
        moral_enabled=False,
        dispatch_enabled=True,
    )
    services_b, _host_b, _calls_b = _services(
        name="b",
        now=2000.0,
        moral_enabled=False,
        dispatch_enabled=False,
    )
    services_a.session_key_fn = lambda _event=None, _explicit="": "shared-session"
    services_b.session_key_fn = lambda _event=None, _explicit="": "shared-session"
    scheduler_a = ProactiveScheduler(plugin, services=services_a)
    scheduler_b = ProactiveScheduler(plugin, services=services_b)

    assert scheduler_a._session_state is None
    assert scheduler_b._session_state is None
    assert scheduler_a.derive_dispatch_policy(session_key="shared-session")[
        "feedback_pressure"
    ] == 0.0
    assert scheduler_b.derive_dispatch_policy(session_key="shared-session")[
        "feedback_pressure"
    ] == 0.0

    scheduler_a.record_message_time("shared-session")
    scheduler_b.record_message_time("shared-session")
    assert scheduler_a._last_user_ts("shared-session") == 1000.0
    assert scheduler_b._last_user_ts("shared-session") == 2000.0
    assert "shared-session" not in plugin._store.last_user_message_time

    assert asyncio.run(
        scheduler_a.request_dispatch(object(), session_key="shared-session")
    ) == {
        "dispatched": False,
        "reason": "explicit_dispatch_capability_required",
        "session_key": "shared-session",
        "dry_run": False,
    }


def test_default_scheduler_keeps_legacy_dispatch_and_session_state() -> None:
    plugin = _PluginTrap()
    dispatch_calls: list[tuple[Any, bool]] = []

    async def dispatch(event: Any, *, dry_run: bool) -> dict[str, Any]:
        dispatch_calls.append((event, dry_run))
        return {"dispatched": True}

    event = SimpleNamespace(unified_msg_origin="legacy-session")
    plugin.request_proactive_speech_dispatch = dispatch  # type: ignore[method-assign]
    plugin._store.proactive_candidate_sessions["legacy-session"] = {"event": event}
    scheduler = ProactiveScheduler(plugin)

    assert scheduler._session_state is plugin._session_state
    assert asyncio.run(scheduler.run_once()) == {"checked": 1, "dispatched": 1}
    assert dispatch_calls == [(event, False)]


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


class _PoisonPlugin:
    """Trap every ambient plugin path forbidden after explicit service injection."""

    _TRAPPED = frozenset(
        {
            "config",
            "_config",
            "context",
            "_context",
            "_store",
            "_scope_runtime_registry",
            "_bound_runtime",
            "_agent_identity_profile_cache",
            "_agent_trail_cache",
            "_conversation_event_ledger",
            "_proactive_dispatch_audit",
            "_life_simulator",
            "_proactive_bridge",
            "_proactive_dispatch_last_sent",
            "_session_state",
            "_self_core",
            "_host",
            "_session_key",
            "_observed_now",
            "_event_time",
            "request_proactive_speech_dispatch",
            "_call_internal_assessor_llm",
            "_internal_assessor_llm_cond",
            "_internal_assessor_llm_inflight",
            "_memory_system_for_session",
            "query_sylanne_memory",
            "_memory_prompt_fragment",
            "_add_transient_context",
            "_load_state",
            "_load_moral_repair_state",
            "_load_psychological_state",
            "_load_humanlike_state",
            "_load_lifelike_learning_state",
            "_load_personality_drift_state",
            "_load_fallibility_state",
            "_delete_state",
            "_delete_humanlike_state",
            "_delete_moral_repair_state",
            "_delete_fallibility_state",
            "_delete_lifelike_learning_state",
            "_delete_personality_drift_state",
            "_humanlike_reset_impl",
        }
    )

    def __init__(self) -> None:
        object.__setattr__(self, "ambient_accesses", [])

    def __getattribute__(self, name: str) -> Any:
        trapped = object.__getattribute__(self, "_TRAPPED")
        if name in trapped:
            accesses = object.__getattribute__(self, "ambient_accesses")
            accesses.append(("get", name))
            raise AssertionError(f"explicit services accessed ambient plugin attribute {name}")
        return object.__getattribute__(self, name)

    def __setattr__(self, name: str, value: Any) -> None:
        trapped = object.__getattribute__(self, "_TRAPPED")
        if name in trapped:
            accesses = object.__getattribute__(self, "ambient_accesses")
            accesses.append(("set", name))
            raise AssertionError(f"explicit services mutated ambient plugin attribute {name}")
        object.__setattr__(self, name, value)


class _IsolatedHost:
    def __init__(self, name: str) -> None:
        self.name = name
        self.events: list[Any] = []
        self.feedback: list[tuple[str, float]] = []
        computation = SimpleNamespace(
            feedback=lambda status, *, dt: self.feedback.append((status, dt))
        )
        self.kernel = SimpleNamespace(
            computation=computation,
            turns=0,
            last_event={"text": ""},
        )

    def on_request(self, event: Any) -> dict[str, Any]:
        self.events.append(event)
        return {"host": self.name, "now": event.now}

    def on_response(self, event: Any) -> dict[str, Any]:
        self.events.append(event)
        return {"host": self.name, "now": event.now}

    def on_proactive_check(self, event: Any) -> dict[str, Any]:
        self.events.append(event)
        return {
            "schema_version": "test.v1",
            "session_key": "shared-session",
            "decision": {"action": "wait"},
            "guard": {"allowed": False},
            "host_payload": {
                "reason": f"service-{self.name}",
                "reason_code": f"service_{self.name}",
            },
        }


def _isolated_services(
    *,
    host: _IsolatedHost,
    clock: list[float],
    context: Any = None,
    config: dict[str, Any] | None = None,
) -> PluginServices:
    return PluginServices(
        config=dict(config or {}),
        context=context,
        host_fn=lambda _session_key: host,
        session_key_fn=lambda _event=None, _explicit="": "shared-session",
        observed_now_fn=lambda: clock[0],
    )


def test_same_plugin_same_session_explicit_public_apis_keep_state_isolated() -> None:
    plugin = _PoisonPlugin()
    clock_a = [1000.0]
    clock_b = [2000.0]
    host_a = _IsolatedHost("a")
    host_b = _IsolatedHost("b")
    api_a = PublicAPI(
        plugin,
        services=_isolated_services(host=host_a, clock=clock_a),
    )
    api_b = PublicAPI(
        plugin,
        services=_isolated_services(host=host_b, clock=clock_b),
    )
    alice = SimpleNamespace(sender_id="same-sender", sender_name="Alice")
    bob = SimpleNamespace(sender_id="same-sender", sender_name="Bob")

    async def exercise() -> None:
        assert await api_a.observe_response("shared-session", now=1000.0) == {
            "host": "a",
            "now": 1000.0,
        }
        await api_a.observe_request("shared-session", now=1010.0)
        await api_b.observe_request("shared-session", now=1010.0)

        await api_a.get_agent_identity_profile(alice)
        await api_b.get_agent_identity_profile(bob)
        profile_a = await api_a.get_agent_identity_profile(alice)
        profile_b = await api_b.get_agent_identity_profile(bob)
        assert [item["name"] for item in profile_a["aliases"]] == ["Alice"]
        assert [item["name"] for item in profile_b["aliases"]] == ["Bob"]
        assert (await api_a.get_agent_trail(alice))["items"] == []
        assert (await api_b.get_agent_trail(bob))["items"] == []

    asyncio.run(exercise())
    assert host_a.feedback == [("accepted", pytest.approx(10.0 / 60.0))]
    assert host_b.feedback == []
    assert plugin.ambient_accesses == []


def test_explicit_public_api_unrepresentable_plugin_operations_fail_closed() -> None:
    plugin = _PoisonPlugin()
    host = _IsolatedHost("only")
    services = _isolated_services(
        host=host,
        clock=[2718.0],
        config={
            "enable_shadow_diagnostics": True,
            "enable_sylanne_memory": True,
            "enable_moral_repair_state": True,
            "enable_psychological_screening": True,
            "enable_fallibility_state": True,
            "allow_emotion_reset_backdoor": True,
            "allow_humanlike_reset_backdoor": True,
            "allow_moral_repair_reset_backdoor": True,
            "allow_fallibility_reset_backdoor": True,
            "allow_lifelike_learning_reset_backdoor": True,
            "allow_personality_drift_reset_backdoor": True,
        },
    )
    api = PublicAPI(plugin, services=services)
    event = SimpleNamespace(sender_id="same-sender", sender_name="Alice")

    async def collect(stream: Any) -> list[Any]:
        return [item async for item in stream]

    async def exercise() -> None:
        assert await api._observatory_route_handler() == {
            "ok": False,
            "error": "scope_unavailable",
        }
        assert api._legacy_observatory_session_key() is None
        assert api._lineage_observatory_route_payload() == {
            "ok": False,
            "error": "scope_unavailable",
        }
        assert api._sylanne_lineage_observatory_page_payload("shared-session") == {
            "ok": False,
            "error": "explicit_runtime_diagnostics_capability_required",
        }
        assert api._understanding_closed_loop_diagnostics("shared-session") == {
            "ok": False,
            "error": "explicit_runtime_diagnostics_capability_required",
        }
        assert await api.get_agent_runtime_diagnostics(event) == {
            "ok": False,
            "error": "explicit_runtime_diagnostics_capability_required",
        }
        shadow = await collect(api.shadow_diagnostics_status(event))
        assert json.loads(shadow[0])["error"] == (
            "explicit_runtime_diagnostics_capability_required"
        )
        assert api._agent_identity(event) == "shared-session::agent:same-sender"
        assert (await api.query_agent_state(event, state="emotion"))["error"] == (
            "explicit_state_read_capability_required"
        )
        assert (
            await api._query_single_agent_state(
                "emotion",
                event,
                session_key="shared-session",
            )
        )["error"] == "explicit_state_read_capability_required"
        assert await api.observe_user_message_withdrawal(
            event,
            session_key="shared-session",
        ) == {
            "ok": False,
            "error": "explicit_state_mutation_capability_required",
        }
        assert await api.get_emotion_state(session_key="shared-session") == {
            "ok": False,
            "error": "explicit_state_read_capability_required",
        }
        assert api.humanlike_reset(session_key="shared-session") == {
            "ok": False,
            "error": "explicit_state_mutation_capability_required",
        }
        assert await collect(api.sylanne_memory_status(event)) == [
            "explicit_state_read_capability_required"
        ]
        assert await collect(api.humanlike_status(event)) == [
            "explicit_state_read_capability_required"
        ]
        assert await collect(api.moral_repair_status(event)) == [
            "explicit_state_read_capability_required"
        ]
        assert await collect(api.psychological_screening_status(event)) == [
            "explicit_state_read_capability_required"
        ]
        assert await collect(api.lifelike_learning_status(event)) == [
            "explicit_state_read_capability_required"
        ]
        assert await collect(api.personality_drift_status(event)) == [
            "explicit_state_read_capability_required"
        ]
        assert await collect(api.fallibility_status(event)) == [
            "explicit_state_read_capability_required"
        ]
        assert await collect(api.emotion_reset(event)) == [
            "explicit_state_mutation_capability_required"
        ]
        assert await collect(api._humanlike_reset_command(event)) == [
            "explicit_state_mutation_capability_required"
        ]
        assert await collect(api.moral_repair_reset(event)) == [
            "explicit_state_mutation_capability_required"
        ]
        assert await collect(api.fallibility_reset(event)) == [
            "explicit_state_mutation_capability_required"
        ]
        assert await collect(api.lifelike_learning_reset(event)) == [
            "explicit_state_mutation_capability_required"
        ]
        assert await collect(api.personality_drift_reset(event)) == [
            "explicit_state_mutation_capability_required"
        ]
        assert await api.build_emotion_memory_payload(event) == {
            "ok": False,
            "error": "explicit_state_read_capability_required",
        }
        assert await api.query_sylanne_memory(
            session_key="shared-session",
            query="hello",
        ) == {
            "schema_version": "sylanne.alpha.memory_system.v1",
            "session_key": "shared-session",
            "slice": "sylanne_memory",
            "query": "hello",
            "source": "explicit_state_read_capability_required",
            "matches": [],
            "count": 0,
            "error": "explicit_state_read_capability_required",
        }
        request = SimpleNamespace(prompt="keep me unchanged")
        assert await api.inject_emotion_context(event, request) == {
            "prompt": "keep me unchanged",
            "error": "explicit_state_read_capability_required",
        }
        proactive = await api.proactive_sylanne(session_key="shared-session")
        assert proactive["decision"]["reason_code"] == "service_only"
        assert "v2core_reach" not in proactive["decision"]

    asyncio.run(exercise())
    assert plugin.ambient_accesses == []


def test_explicit_public_api_internal_assessor_state_is_instance_owned() -> None:
    plugin = _PoisonPlugin()
    calls_a: list[dict[str, Any]] = []
    calls_b: list[dict[str, Any]] = []

    async def llm_a(**kwargs: Any) -> Any:
        calls_a.append(kwargs)
        return SimpleNamespace(completion_text="a")

    async def llm_b(**kwargs: Any) -> Any:
        calls_b.append(kwargs)
        return SimpleNamespace(completion_text="b")

    api_a = PublicAPI(
        plugin,
        services=_isolated_services(
            host=_IsolatedHost("a"),
            clock=[1.0],
            context=SimpleNamespace(llm_generate=llm_a),
        ),
    )
    api_b = PublicAPI(
        plugin,
        services=_isolated_services(
            host=_IsolatedHost("b"),
            clock=[2.0],
            context=SimpleNamespace(llm_generate=llm_b),
        ),
    )

    async def exercise() -> None:
        assert api_a._internal_assessor_llm_condition() is not (
            api_b._internal_assessor_llm_condition()
        )
        assert (await api_a._call_internal_assessor_llm(prompt="one")).completion_text == "a"
        assert (await api_b._call_internal_assessor_llm(prompt="two")).completion_text == "b"

    asyncio.run(exercise())
    assert calls_a == [{"prompt": "one"}]
    assert calls_b == [{"prompt": "two"}]
    assert api_a._internal_assessor_llm_concurrency_decision()["inflight"] == 0
    assert api_b._internal_assessor_llm_concurrency_decision()["inflight"] == 0
    assert plugin.ambient_accesses == []


def test_explicit_scheduler_policy_never_reads_plugin_scope_or_audit() -> None:
    plugin = _PoisonPlugin()
    scheduler = ProactiveScheduler(
        plugin,
        services=_isolated_services(
            host=_IsolatedHost("scheduler"),
            clock=[2718.0],
            config={
                "enable_proactive_speech_dispatch": True,
                "proactive_speech_dispatch_cooldown_seconds": 120.0,
            },
        ),
    )

    assert scheduler._bound_session_runtime("shared-session") is None
    assert scheduler.derive_dispatch_policy(session_key="shared-session") == {
        "should_dispatch": True,
        "reason": "policy",
        "cooldown_seconds": 120.0,
        "feedback_pressure": 0.0,
    }
    assert plugin.ambient_accesses == []


def test_scheduler_rejects_explicit_services_with_scoped_persistence() -> None:
    with pytest.raises(
        ValueError,
        match="explicit services cannot be combined with scoped persistence",
    ):
        ProactiveScheduler(
            _PoisonPlugin(),
            services=PluginServices(),
            persistence=object(),  # type: ignore[arg-type]
        )
