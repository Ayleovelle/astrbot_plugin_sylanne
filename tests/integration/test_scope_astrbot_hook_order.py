from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from main import EmotionalStatePlugin
from sylanne_alpha.scope_identity import ScopeResolver


class _Session:
    platform_id = "adapter"
    session_id = "42"

    def __str__(self) -> str:
        return "adapter:FriendMessage:42"


@pytest.mark.asyncio
async def test_transport_turn_and_persona_freeze_precede_existing_pipeline(
    tmp_path, monkeypatch
) -> None:
    order: list[str] = []

    async def select_persona(**_kwargs):
        order.append("persona resolve")
        return (
            "narrator",
            {"prompt": "quiet", "begin_dialogs": [], "tools": None, "skills": []},
            None,
            False,
        )

    context = SimpleNamespace(
        get_config=lambda *, umo: {"provider_settings": {}},
        persona_manager=SimpleNamespace(resolve_selected_persona=select_persona),
    )
    resolver = ScopeResolver.for_test(context, root=tmp_path)
    extras: dict[str, object] = {}
    event = SimpleNamespace(
        session=_Session(),
        unified_msg_origin="adapter:FriendMessage:42",
        get_platform_id=lambda: "adapter",
        get_platform_name=lambda: "aiocqhttp",
        get_self_id=lambda: "10001",
        get_extra=lambda key: extras.get(key),
        set_extra=lambda key, value: extras.__setitem__(key, value),
    )

    original_transport = resolver.resolve_transport
    monkeypatch.setattr(
        resolver,
        "resolve_transport",
        lambda evt: (order.append("transport"), original_transport(evt))[1],
    )
    original_binding = resolver.delivery_binding
    monkeypatch.setattr(
        resolver,
        "delivery_binding",
        lambda evt, scope: (order.append("binding"), original_binding(evt, scope))[1],
    )
    original_begin = resolver.catalog.begin_turn
    monkeypatch.setattr(
        resolver.catalog,
        "begin_turn",
        lambda scope, binding, **kwargs: (
            order.append("begin_turn"),
            original_begin(scope, binding, **kwargs),
        )[1],
    )
    original_freeze = resolver.catalog.freeze_persona_published
    monkeypatch.setattr(
        resolver.catalog,
        "freeze_persona_published",
        lambda turn, scope, **kwargs: (
            order.append("publish/freeze"),
            original_freeze(turn, scope, **kwargs),
        )[1],
    )

    async def existing_pipeline(_event, _request):
        order.append("existing pipeline")

    async def save_rhythm():
        return None

    plugin = SimpleNamespace(
        _scope_resolver_v1=resolver,
        config={},
        _session_ctx=SimpleNamespace(
            session_key=lambda _event: "adapter:FriendMessage:42",
            resolve_authenticated_identity=lambda _event: None,
            detect_and_observe_ritual_from_text=lambda *_args: None,
        ),
        _store=SimpleNamespace(
            stash_authenticated_identity=lambda *_args: None,
            last_user_message_time=SimpleNamespace(set=lambda *_args: None),
            hosts=SimpleNamespace(get=lambda *_args: None),
        ),
        _rhythm_learner=SimpleNamespace(
            observe_user_message=lambda *_args: None,
        ),
        _rhythm_learner_throttled_save=save_rhythm,
        _inbound_dup_gate=lambda _event: False,
        _llm_request_pipeline=SimpleNamespace(_on_llm_request_inner=existing_pipeline),
    )

    assert EmotionalStatePlugin._begin_scope_transport(plugin, event) is True
    transport = extras["_sylanne_transport_scope_v1"]
    await EmotionalStatePlugin._on_llm_request_inner(
        plugin,
        event,
        SimpleNamespace(conversation=SimpleNamespace(persona_id=None)),
    )

    assert order == [
        "transport",
        "binding",
        "begin_turn",
        "persona resolve",
        "transport",
        "publish/freeze",
        "transport",
        "existing pipeline",
    ]
    assert extras["_sylanne_transport_scope_v1"] is transport
    assert extras["_sylanne_resolved_scope_v1"].private_scope_enabled is True


@pytest.mark.asyncio
async def test_redelivered_event_stops_before_any_legacy_private_write(
    tmp_path,
) -> None:
    async def select_persona(**_kwargs):
        return (
            "narrator",
            {"prompt": "quiet", "begin_dialogs": [], "tools": None, "skills": []},
            None,
            False,
        )

    resolver = ScopeResolver.for_test(
        SimpleNamespace(
            get_config=lambda *, umo: {"provider_settings": {}},
            persona_manager=SimpleNamespace(
                resolve_selected_persona=select_persona
            ),
        ),
        root=tmp_path,
    )

    class Event:
        def __init__(self, label: str) -> None:
            self.label = label
            self.session = _Session()
            self.session_id = "42"
            self.unified_msg_origin = "adapter:FriendMessage:42"
            self.message_obj = SimpleNamespace(message_id="same-message-id")
            self.message_str = "same payload"
            self.extras: dict[str, object] = {}
            self.stop_calls = 0

        def get_platform_id(self) -> str:
            return "adapter"

        def get_platform_name(self) -> str:
            return "aiocqhttp"

        def get_self_id(self) -> str:
            return "10001"

        def get_extra(self, key: str, default: object = None) -> object:
            return self.extras.get(key, default)

        def set_extra(self, key: str, value: object) -> None:
            self.extras[key] = value

        def stop_event(self) -> None:
            self.stop_calls += 1

    legacy_activity: list[str] = []
    pipeline_events: list[str] = []

    async def save_rhythm() -> None:
        legacy_activity.append("save_rhythm")

    async def existing_pipeline(event: Event, _request: object) -> None:
        pipeline_events.append(event.label)

    plugin = SimpleNamespace(
        _scope_resolver_v1=resolver,
        config={},
        _inbound_seen={},
        _session_ctx=SimpleNamespace(
            session_key=lambda _event: "42",
            resolve_authenticated_identity=lambda _event: legacy_activity.append(
                "resolve_identity"
            ),
            detect_and_observe_ritual_from_text=lambda *_args: legacy_activity.append(
                "observe_ritual"
            ),
        ),
        _store=SimpleNamespace(
            stash_authenticated_identity=lambda *_args: legacy_activity.append(
                "stash_identity"
            ),
            last_user_message_time=SimpleNamespace(
                set=lambda *_args: legacy_activity.append("last_message")
            ),
            hosts=SimpleNamespace(get=lambda *_args: None),
        ),
        _rhythm_learner=SimpleNamespace(
            observe_user_message=lambda *_args: legacy_activity.append(
                "observe_rhythm"
            )
        ),
        _rhythm_learner_throttled_save=save_rhythm,
        _llm_request_pipeline=SimpleNamespace(
            _on_llm_request_inner=existing_pipeline
        ),
    )
    plugin._inbound_dup_gate = lambda event: (
        EmotionalStatePlugin._inbound_dup_gate(plugin, event)
    )
    request = SimpleNamespace(conversation=SimpleNamespace(persona_id=None))
    first = Event("first")
    duplicate = Event("duplicate")

    await EmotionalStatePlugin.on_message(plugin, first)
    await EmotionalStatePlugin._on_llm_request_inner(plugin, first, request)
    baseline_activity = list(legacy_activity)

    await EmotionalStatePlugin.on_message(plugin, duplicate)
    await EmotionalStatePlugin._on_llm_request_inner(plugin, duplicate, request)
    await EmotionalStatePlugin._on_llm_request_inner(plugin, duplicate, request)

    assert baseline_activity
    assert legacy_activity == baseline_activity
    assert pipeline_events == ["first"]
    assert first.stop_calls == 0
    assert duplicate.stop_calls == 1
    assert duplicate.get_extra("_syl_inbound_duplicate") is True
    assert duplicate.get_extra("_sylanne_legacy_on_message_v1") == "duplicate"


@pytest.mark.asyncio
async def test_missing_scope_context_blocks_both_legacy_hook_paths() -> None:
    legacy_calls: list[str] = []

    async def existing_pipeline(_event, _request):
        legacy_calls.append("pipeline")

    plugin = SimpleNamespace(
        _scope_resolver_v1=None,
        context=None,
        config={},
        _session_ctx=SimpleNamespace(
            session_key=lambda _event: legacy_calls.append("on_message") or "legacy"
        ),
        _inbound_dup_gate=lambda _event: False,
        _llm_request_pipeline=SimpleNamespace(_on_llm_request_inner=existing_pipeline),
    )
    extras: dict[str, object] = {}
    event = SimpleNamespace(
        get_extra=lambda key, default=None: extras.get(key, default),
        set_extra=lambda key, value: extras.__setitem__(key, value),
    )

    assert EmotionalStatePlugin._begin_scope_transport(plugin, event) is False
    disabled = await EmotionalStatePlugin._freeze_scope_persona(
        plugin, event, SimpleNamespace(conversation=SimpleNamespace(persona_id=None))
    )
    assert disabled.private_scope_enabled is False

    await EmotionalStatePlugin.on_message(plugin, event)
    await EmotionalStatePlugin._on_llm_request_inner(
        plugin, event, SimpleNamespace(conversation=SimpleNamespace(persona_id=None))
    )

    assert legacy_calls == []


@pytest.mark.parametrize("extra_failure", ["raise", "drop"])
def test_transport_extra_failure_leaves_no_persisted_resolving_turn(
    tmp_path, extra_failure: str
) -> None:
    context = SimpleNamespace(
        get_config=lambda *, umo: {"provider_settings": {}},
        persona_manager=SimpleNamespace(resolve_selected_persona=None),
    )
    resolver = ScopeResolver.for_test(context, root=tmp_path)
    extras: dict[str, object] = {}

    def set_extra(key: str, value: object) -> None:
        if key == "_sylanne_transport_turn_v1":
            if extra_failure == "raise":
                raise RuntimeError("event extras unavailable")
            return
        extras[key] = value

    event = SimpleNamespace(
        session=_Session(),
        unified_msg_origin="adapter:FriendMessage:42",
        get_platform_id=lambda: "adapter",
        get_platform_name=lambda: "aiocqhttp",
        get_self_id=lambda: "10001",
        get_extra=lambda key, default=None: extras.get(key, default),
        set_extra=set_extra,
    )
    plugin = SimpleNamespace(_scope_resolver_v1=resolver)

    assert EmotionalStatePlugin._begin_scope_transport(plugin, event) is False

    assert list(resolver._repository.bots_directory.rglob("*")) == []
    bindings_root = resolver._repository.bot_bindings_directory
    assert not bindings_root.exists() or list(bindings_root.rglob("*")) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", ["config", "persona"])
async def test_persona_resolution_failure_runs_no_legacy_private_path(
    tmp_path, failure_stage: str
) -> None:
    legacy_calls: list[str] = []

    def get_config(*, umo: str) -> dict[str, object]:
        if failure_stage == "config":
            raise RuntimeError("config unavailable")
        return {"provider_settings": {}}

    manager = SimpleNamespace(
        resolve_selected_persona=AsyncMock(side_effect=RuntimeError("persona unavailable"))
    )
    context = SimpleNamespace(get_config=get_config, persona_manager=manager)
    resolver = ScopeResolver.for_test(context, root=tmp_path)
    extras: dict[str, object] = {}
    event = SimpleNamespace(
        session=_Session(),
        unified_msg_origin="adapter:FriendMessage:42",
        get_platform_id=lambda: "adapter",
        get_platform_name=lambda: "aiocqhttp",
        get_self_id=lambda: "10001",
        get_extra=lambda key, default=None: extras.get(key, default),
        set_extra=lambda key, value: extras.__setitem__(key, value),
    )

    async def existing_pipeline(_event, _request):
        legacy_calls.append("pipeline")

    plugin = SimpleNamespace(
        _scope_resolver_v1=resolver,
        config={},
        _session_ctx=SimpleNamespace(
            session_key=lambda _event: "adapter:FriendMessage:42",
            resolve_authenticated_identity=lambda _event: (
                legacy_calls.append("identity")
            ),
        ),
        _store=SimpleNamespace(
            conversation_input_epoch=None,
            segmented_delivery_turns=None,
        ),
        _inbound_dup_gate=lambda _event: False,
        _llm_request_pipeline=SimpleNamespace(_on_llm_request_inner=existing_pipeline),
    )
    request = SimpleNamespace(conversation=SimpleNamespace(persona_id=None))

    await EmotionalStatePlugin.on_message(plugin, event)
    await EmotionalStatePlugin._on_llm_request_inner(plugin, event, request)

    assert legacy_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("extra_failure", ["raise", "drop"])
async def test_resolved_scope_extra_failure_leaves_no_scope_or_frozen_artifact(
    tmp_path, extra_failure: str
) -> None:
    async def select_persona(**_kwargs):
        return (
            "narrator",
            {"prompt": "quiet", "begin_dialogs": [], "tools": None, "skills": []},
            None,
            False,
        )

    context = SimpleNamespace(
        get_config=lambda *, umo: {"provider_settings": {}},
        persona_manager=SimpleNamespace(resolve_selected_persona=select_persona),
    )
    resolver = ScopeResolver.for_test(context, root=tmp_path)
    extras: dict[str, object] = {}
    fail_resolved_extra = False

    def set_extra(key: str, value: object) -> None:
        if fail_resolved_extra and key == "_sylanne_resolved_scope_v1":
            if extra_failure == "raise":
                raise RuntimeError("resolved scope extra unavailable")
            return
        extras[key] = value

    event = SimpleNamespace(
        session=_Session(),
        unified_msg_origin="adapter:FriendMessage:42",
        get_platform_id=lambda: "adapter",
        get_platform_name=lambda: "aiocqhttp",
        get_self_id=lambda: "10001",
        get_extra=lambda key, default=None: extras.get(key, default),
        set_extra=set_extra,
    )
    plugin = SimpleNamespace(_scope_resolver_v1=resolver)
    assert EmotionalStatePlugin._begin_scope_transport(plugin, event) is True
    transport = extras["_sylanne_transport_scope_v1"]
    resolving_turn = extras["_sylanne_transport_turn_v1"]

    fail_resolved_extra = True
    result = await resolver.resolve(
        event,
        SimpleNamespace(conversation=SimpleNamespace(persona_id=None)),
    )

    assert result.private_scope_enabled is False
    assert resolver.catalog.current(transport.session_ref.token) == resolving_turn
    assert resolver.catalog.current(transport.session_ref.token).turn_state == "resolving"
    assert extras["_sylanne_transport_turn_v1"] is resolving_turn
    persona_root = (
        resolver._repository.bots_directory / transport.bot_ref.token / "personas"
    )
    assert not persona_root.exists() or list(persona_root.rglob("*")) == []
    with resolver._repository.transaction():
        assert resolver._repository._read_catalog_locked()["scopes"] == {}


@pytest.mark.asyncio
async def test_repeated_resolve_reuses_exact_published_scope_without_refreezing(
    tmp_path,
) -> None:
    manager = SimpleNamespace(
        resolve_selected_persona=AsyncMock(
            return_value=(
                "narrator",
                {"prompt": "quiet", "begin_dialogs": [], "tools": None, "skills": []},
                None,
                False,
            )
        )
    )
    resolver = ScopeResolver.for_test(
        SimpleNamespace(
            get_config=lambda *, umo: {"provider_settings": {}},
            persona_manager=manager,
        ),
        root=tmp_path,
    )
    extras: dict[str, object] = {}
    event = SimpleNamespace(
        session=_Session(),
        unified_msg_origin="adapter:FriendMessage:42",
        get_platform_id=lambda: "adapter",
        get_platform_name=lambda: "aiocqhttp",
        get_self_id=lambda: "10001",
        get_extra=lambda key, default=None: extras.get(key, default),
        set_extra=lambda key, value: extras.__setitem__(key, value),
    )
    plugin = SimpleNamespace(_scope_resolver_v1=resolver)
    request = SimpleNamespace(conversation=SimpleNamespace(persona_id=None))
    assert EmotionalStatePlugin._begin_scope_transport(plugin, event) is True

    first = await resolver.resolve(event, request)
    frozen_turn = extras["_sylanne_transport_turn_v1"]
    second = await resolver.resolve(event, request)

    assert second is first
    assert manager.resolve_selected_persona.await_count == 1
    assert extras["_sylanne_resolved_scope_v1"] is first
    assert extras["_sylanne_transport_turn_v1"] is frozen_turn
    assert resolver.catalog.current(first.scope.session_ref.token) == frozen_turn


@pytest.mark.asyncio
async def test_forged_published_scope_fails_closed_without_persona_resolution(
    tmp_path,
) -> None:
    manager = SimpleNamespace(
        resolve_selected_persona=AsyncMock(
            return_value=(
                "narrator",
                {"prompt": "quiet", "begin_dialogs": [], "tools": None, "skills": []},
                None,
                False,
            )
        )
    )
    resolver = ScopeResolver.for_test(
        SimpleNamespace(
            get_config=lambda *, umo: {"provider_settings": {}},
            persona_manager=manager,
        ),
        root=tmp_path,
    )
    extras: dict[str, object] = {}
    event = SimpleNamespace(
        session=_Session(),
        unified_msg_origin="adapter:FriendMessage:42",
        get_platform_id=lambda: "adapter",
        get_platform_name=lambda: "aiocqhttp",
        get_self_id=lambda: "10001",
        get_extra=lambda key, default=None: extras.get(key, default),
        set_extra=lambda key, value: extras.__setitem__(key, value),
    )
    plugin = SimpleNamespace(_scope_resolver_v1=resolver)
    request = SimpleNamespace(conversation=SimpleNamespace(persona_id=None))
    assert EmotionalStatePlugin._begin_scope_transport(plugin, event) is True
    first = await resolver.resolve(event, request)
    extras["_sylanne_resolved_scope_v1"] = replace(
        first,
        turn_generation=first.turn_generation + 1,
    )

    result = await resolver.resolve(event, request)

    assert result.private_scope_enabled is False
    assert result.disabled_reason == "resolved_scope_mismatch"
    assert manager.resolve_selected_persona.await_count == 1


@pytest.mark.asyncio
async def test_event_tamper_after_resolve_stops_legacy_and_existing_pipeline(
    tmp_path,
    monkeypatch,
) -> None:
    manager = SimpleNamespace(
        resolve_selected_persona=AsyncMock(
            return_value=(
                "narrator",
                {"prompt": "quiet", "begin_dialogs": [], "tools": None, "skills": []},
                None,
                False,
            )
        )
    )
    resolver = ScopeResolver.for_test(
        SimpleNamespace(
            get_config=lambda *, umo: {"provider_settings": {}},
            persona_manager=manager,
        ),
        root=tmp_path,
    )
    extras: dict[str, object] = {}
    event = SimpleNamespace(
        session=_Session(),
        unified_msg_origin="adapter:FriendMessage:42",
        get_platform_id=lambda: "adapter",
        get_platform_name=lambda: "aiocqhttp",
        get_self_id=lambda: "10001",
        get_extra=lambda key, default=None: extras.get(key, default),
        set_extra=lambda key, value: extras.__setitem__(key, value),
    )
    calls: list[str] = []

    async def existing_pipeline(_event, _request):
        calls.append("pipeline")

    plugin = SimpleNamespace(
        _scope_resolver_v1=resolver,
        config={},
        _session_ctx=SimpleNamespace(
            session_key=lambda _event: calls.append("legacy") or "legacy",
        ),
        _inbound_dup_gate=lambda _event: calls.append("dedup") or False,
        _llm_request_pipeline=SimpleNamespace(
            _on_llm_request_inner=existing_pipeline
        ),
    )
    assert EmotionalStatePlugin._begin_scope_transport(plugin, event) is True
    original_freeze = EmotionalStatePlugin._freeze_scope_persona

    async def freeze_then_tamper(self, live_event, request):
        resolved = await original_freeze(self, live_event, request)
        live_event.unified_msg_origin = "adapter:FriendMessage:different"
        return resolved

    monkeypatch.setattr(
        EmotionalStatePlugin,
        "_freeze_scope_persona",
        freeze_then_tamper,
    )

    await EmotionalStatePlugin._on_llm_request_inner(
        plugin,
        event,
        SimpleNamespace(conversation=SimpleNamespace(persona_id=None)),
    )

    assert calls == []


@pytest.mark.asyncio
async def test_legacy_core_error_stops_dedup_and_existing_pipeline(tmp_path) -> None:
    manager = SimpleNamespace(
        resolve_selected_persona=AsyncMock(
            return_value=(
                "narrator",
                {"prompt": "quiet", "begin_dialogs": [], "tools": None, "skills": []},
                None,
                False,
            )
        )
    )
    resolver = ScopeResolver.for_test(
        SimpleNamespace(
            get_config=lambda *, umo: {"provider_settings": {}},
            persona_manager=manager,
        ),
        root=tmp_path,
    )
    extras: dict[str, object] = {}
    event = SimpleNamespace(
        session=_Session(),
        unified_msg_origin="adapter:FriendMessage:42",
        get_platform_id=lambda: "adapter",
        get_platform_name=lambda: "aiocqhttp",
        get_self_id=lambda: "10001",
        get_extra=lambda key, default=None: extras.get(key, default),
        set_extra=lambda key, value: extras.__setitem__(key, value),
    )
    calls: list[str] = []

    def fail_core_write(*_args):
        raise RuntimeError("last-user-message store unavailable")

    async def existing_pipeline(_event, _request):
        calls.append("pipeline")

    plugin = SimpleNamespace(
        _scope_resolver_v1=resolver,
        config={},
        _session_ctx=SimpleNamespace(
            session_key=lambda _event: "adapter:FriendMessage:42",
            resolve_authenticated_identity=lambda _event: None,
        ),
        _store=SimpleNamespace(
            stash_authenticated_identity=lambda *_args: None,
            last_user_message_time=SimpleNamespace(set=fail_core_write),
        ),
        _inbound_dup_gate=lambda _event: calls.append("dedup") or False,
        _llm_request_pipeline=SimpleNamespace(
            _on_llm_request_inner=existing_pipeline
        ),
    )
    assert EmotionalStatePlugin._begin_scope_transport(plugin, event) is True

    await EmotionalStatePlugin._on_llm_request_inner(
        plugin,
        event,
        SimpleNamespace(conversation=SimpleNamespace(persona_id=None)),
    )
    await EmotionalStatePlugin._on_llm_request_inner(
        plugin,
        event,
        SimpleNamespace(conversation=SimpleNamespace(persona_id=None)),
    )

    assert calls == []
    assert extras["_sylanne_legacy_on_message_v1"] == "failed"
