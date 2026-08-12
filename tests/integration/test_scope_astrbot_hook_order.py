from __future__ import annotations

import asyncio
import ast
import contextvars
from dataclasses import replace
import inspect
import textwrap
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from main import EmotionalStatePlugin
from sylanne_alpha.scope_contracts import (
    AuthenticatedSubject,
    RelationRef,
    TurnSubjectProof,
)
from sylanne_alpha.scope_identity import BotBinding, ScopeResolver
from sylanne_alpha.scope_runtime import (
    PersonaRuntime,
    RequestRuntimeView,
    ScopeRuntimeRegistry,
    ScopeUnavailable,
)
from sylanne_alpha.session_context import SessionContext


class _Session:
    platform_id = "adapter"
    session_id = "42"

    def __str__(self) -> str:
        return "adapter:FriendMessage:42"


class _ProofSession:
    platform_id = "adapter"

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id

    def __str__(self) -> str:
        return f"adapter:FriendMessage:{self.session_id}"


class _ProofEvent:
    def __init__(
        self,
        session_id: str,
        sender_id: str,
        *,
        self_id: str = "10001",
        message_id: str | None = None,
    ) -> None:
        self.session = _ProofSession(session_id)
        self.session_id = session_id
        self.unified_msg_origin = str(self.session)
        self.message_obj = SimpleNamespace(
            message_id=message_id or f"message-{session_id}"
        )
        self.message_str = "hello"
        self.extras: dict[str, object] = {}
        self.self_id = self_id
        self.sender_id = sender_id
        self.sender_reads = 0

    def get_platform_id(self) -> str:
        return "adapter"

    def get_platform_name(self) -> str:
        return "aiocqhttp"

    def get_self_id(self) -> str:
        return self.self_id

    def get_sender_id(self) -> str:
        self.sender_reads += 1
        return self.sender_id

    def get_message_type(self) -> object:
        return SimpleNamespace(name="FRIEND_MESSAGE")

    def get_extra(self, key: str, default: object = None) -> object:
        return self.extras.get(key, default)

    def set_extra(self, key: str, value: object) -> None:
        self.extras[key] = value


def _ready_scope_runtime_registry(resolver: ScopeResolver) -> ScopeRuntimeRegistry:
    def ready_persona_runtime(scope) -> PersonaRuntime:
        runtime = PersonaRuntime(persona_ref=scope.persona_ref)

        def construct_services(owner: PersonaRuntime) -> bool:
            owner.self_core = object()
            owner.autonomy_scheduler = object()
            return True

        runtime.persona_services_factory = construct_services
        return runtime

    return ScopeRuntimeRegistry(
        runtime_factory=ready_persona_runtime,
        repository=resolver._repository,
    )


def _bind_ready_scope_registry(plugin, resolver: ScopeResolver) -> None:
    plugin._scope_runtime_registry = _ready_scope_runtime_registry(resolver)
    plugin._scope_runtime_binding = contextvars.ContextVar(
        f"proof_binding_{id(plugin)}",
        default=None,
    )
    plugin._bound_runtime = lambda: EmotionalStatePlugin._bound_runtime(plugin)


def _proof_plugin(tmp_path):
    manager = SimpleNamespace(
        resolve_selected_persona=AsyncMock(
            return_value=(
                "narrator",
                {
                    "prompt": "quiet",
                    "begin_dialogs": [],
                    "tools": None,
                    "skills": [],
                },
                None,
                False,
            )
        )
    )
    context = SimpleNamespace(
        get_config=lambda *, umo: {"provider_settings": {}},
        persona_manager=manager,
    )
    resolver = ScopeResolver.for_test(context, root=tmp_path)
    plugin = object.__new__(EmotionalStatePlugin)
    plugin.context = context
    plugin.config = {}
    plugin._config = {}
    plugin._scope_resolver_v1 = resolver
    _bind_ready_scope_registry(plugin, resolver)
    plugin._session_ctx = SessionContext(plugin)
    plugin._inbound_seen = {}
    return plugin, manager


def _install_proof_tail(monkeypatch, observed: list[RequestRuntimeView]) -> None:
    monkeypatch.setattr(
        EmotionalStatePlugin,
        "_on_transport_ready_safety",
        lambda *_args: None,
    )

    async def legacy_ready(*_args) -> bool:
        return True

    async def tail(plugin, event, _request) -> None:
        view = event.get_extra("_sylanne_runtime_view_v1")
        assert type(view) is RequestRuntimeView
        binding = plugin._bound_runtime()
        assert binding is not None
        assert binding.scope == view.resolved.scope
        assert binding.persona_runtime is view.persona_runtime
        assert binding.session_runtime is view.session_runtime
        assert binding.relation_runtime is view.relation_runtime
        observed.append(view)

    monkeypatch.setattr(
        EmotionalStatePlugin,
        "_on_message_after_scope_frozen",
        legacy_ready,
    )
    monkeypatch.setattr(
        EmotionalStatePlugin,
        "_publish_transport_runtime_owner",
        lambda *_args: True,
    )
    monkeypatch.setattr(
        EmotionalStatePlugin,
        "_start_life_simulator",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        EmotionalStatePlugin,
        "_on_scope_ready_llm_request",
        tail,
    )


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
        session_id="42",
        unified_msg_origin="adapter:FriendMessage:42",
        get_platform_id=lambda: "adapter",
        get_platform_name=lambda: "aiocqhttp",
        get_self_id=lambda: "10001",
        get_extra=lambda key, default=None: extras.get(key, default),
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

    def resolve_identity(_event):
        order.append("identity")
        return None

    plugin = SimpleNamespace(
        _scope_resolver_v1=resolver,
        config={},
        _session_ctx=SimpleNamespace(
            session_key=lambda _event: "adapter:FriendMessage:42",
            resolve_authenticated_identity=resolve_identity,
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
    _bind_ready_scope_registry(plugin, resolver)

    monkeypatch.setattr(
        EmotionalStatePlugin,
        "_on_transport_ready_safety",
        lambda *_args: None,
    )

    async def legacy_ready(*_args) -> bool:
        return True

    monkeypatch.setattr(
        EmotionalStatePlugin,
        "_on_message_after_scope_frozen",
        legacy_ready,
    )
    monkeypatch.setattr(
        EmotionalStatePlugin,
        "_publish_transport_runtime_owner",
        lambda *_args: True,
    )
    monkeypatch.setattr(
        EmotionalStatePlugin,
        "_start_life_simulator",
        lambda *_args: None,
    )
    await EmotionalStatePlugin.on_message(plugin, event)
    transport = extras["_sylanne_transport_scope_v1"]
    await EmotionalStatePlugin._on_llm_request_inner(
        plugin,
        event,
        SimpleNamespace(conversation=SimpleNamespace(persona_id=None)),
    )

    assert order.count("identity") == 1
    assert order.index("persona resolve") < order.index("identity")
    assert order.index("identity") < order.index("publish/freeze")
    assert order.index("publish/freeze") < order.index("existing pipeline")
    assert extras["_sylanne_transport_scope_v1"] is transport
    assert extras["_sylanne_resolved_scope_v1"].private_scope_enabled is True


@pytest.mark.asyncio
async def test_redelivered_event_stops_before_any_legacy_private_write(
    tmp_path,
    monkeypatch,
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
    _bind_ready_scope_registry(plugin, resolver)
    plugin._inbound_dup_gate = lambda event: (
        EmotionalStatePlugin._inbound_dup_gate(plugin, event)
    )
    transport_attempts: list[str] = []
    original_begin_scope_transport = EmotionalStatePlugin._begin_scope_transport

    def begin_scope_transport(live_plugin, event: Event) -> bool:
        transport_attempts.append(event.label)
        return original_begin_scope_transport(live_plugin, event)

    monkeypatch.setattr(
        EmotionalStatePlugin,
        "_begin_scope_transport",
        begin_scope_transport,
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
    assert transport_attempts == ["first"]
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
        session_id="42",
        unified_msg_origin="adapter:FriendMessage:42",
        get_platform_id=lambda: "adapter",
        get_platform_name=lambda: "aiocqhttp",
        get_self_id=lambda: "10001",
        get_extra=lambda key, default=None: extras.get(key, default),
        set_extra=set_extra,
    )
    plugin = SimpleNamespace(_scope_resolver_v1=resolver)
    _bind_ready_scope_registry(plugin, resolver)

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
        session_id="42",
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
    _bind_ready_scope_registry(plugin, resolver)
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
    _bind_ready_scope_registry(plugin, resolver)
    await EmotionalStatePlugin.on_message(plugin, event)
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
    _bind_ready_scope_registry(plugin, resolver)
    request = SimpleNamespace(conversation=SimpleNamespace(persona_id=None))
    await EmotionalStatePlugin.on_message(plugin, event)

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
    _bind_ready_scope_registry(plugin, resolver)
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
    _bind_ready_scope_registry(plugin, resolver)
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
        session_id="42",
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
    _bind_ready_scope_registry(plugin, resolver)
    await EmotionalStatePlugin.on_message(plugin, event)

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


@pytest.mark.asyncio
async def test_decorated_hooks_read_sender_once_and_publish_only_opaque_subject(
    tmp_path,
    monkeypatch,
) -> None:
    plugin, manager = _proof_plugin(tmp_path)
    observed: list[RequestRuntimeView] = []
    _install_proof_tail(monkeypatch, observed)
    raw_sender = "RAW-SENDER-MUST-NOT-SURVIVE"
    event = _ProofEvent("42", raw_sender)
    request = SimpleNamespace(conversation=SimpleNamespace(persona_id=None))

    await EmotionalStatePlugin.on_message(plugin, event)

    assert event.get_extra("_sylanne_turn_subject_v1") is None
    assert event.sender_reads == 0
    assert all(raw_sender not in repr(value) for value in event.extras.values())

    await EmotionalStatePlugin.on_llm_request(plugin, event, request)

    assert manager.resolve_selected_persona.await_count == 1
    assert event.sender_reads == 1
    assert event.get_extra("_sylanne_turn_subject_v1") is None
    assert len(observed) == 1
    assert observed[0].relation_runtime is not None
    assert raw_sender not in repr(event.extras)


@pytest.mark.asyncio
async def test_same_bot_same_delivery_key_is_still_deduplicated(tmp_path) -> None:
    plugin, _manager = _proof_plugin(tmp_path)
    first = _ProofEvent(
        "42",
        "same-human",
        self_id="bot-left",
        message_id="same-delivery",
    )
    duplicate = _ProofEvent(
        "42",
        "same-human",
        self_id="bot-left",
        message_id="same-delivery",
    )

    await EmotionalStatePlugin.on_message(plugin, first)
    await EmotionalStatePlugin.on_message(plugin, duplicate)

    assert first.get_extra("_syl_inbound_duplicate") is False
    assert duplicate.get_extra("_syl_inbound_duplicate") is True
    assert first.sender_reads == duplicate.sender_reads == 0
    assert len(plugin._inbound_seen) == 1


@pytest.mark.asyncio
async def test_missing_receiving_bot_identity_fails_open_without_sender_read(
    tmp_path,
) -> None:
    plugin, _manager = _proof_plugin(tmp_path)
    events = [
        _ProofEvent(
            "42",
            "same-human",
            self_id="",
            message_id="same-delivery",
        )
        for _ in range(2)
    ]

    await asyncio.gather(
        *(EmotionalStatePlugin.on_message(plugin, event) for event in events)
    )

    assert [event.get_extra("_syl_inbound_duplicate") for event in events] == [
        False,
        False,
    ]
    assert [event.sender_reads for event in events] == [0, 0]
    assert plugin._inbound_seen == {}


def test_inbound_registration_and_fallback_gate_share_canonical_key_helper(
    tmp_path,
    monkeypatch,
) -> None:
    plugin, _manager = _proof_plugin(tmp_path)
    calls: list[_ProofEvent] = []

    def canonical_key(event: _ProofEvent):
        calls.append(event)
        return (
            event.get_platform_id(),
            event.get_self_id(),
            event.unified_msg_origin,
            event.message_obj.message_id,
        )

    monkeypatch.setattr(
        EmotionalStatePlugin,
        "_canonical_inbound_duplicate_key",
        staticmethod(canonical_key),
    )
    registered = _ProofEvent(
        "42",
        "same-human",
        self_id="bot-left",
        message_id="registered-path",
    )
    fallback = _ProofEvent(
        "42",
        "same-human",
        self_id="bot-left",
        message_id="fallback-path",
    )

    assert EmotionalStatePlugin._register_inbound_duplicate(plugin, registered) is False
    assert EmotionalStatePlugin._inbound_dup_gate(plugin, fallback) is False
    assert calls == [registered, fallback]


@pytest.mark.asyncio
async def test_concurrent_same_transport_message_isolated_by_bot_account(
    tmp_path,
    monkeypatch,
) -> None:
    plugin, manager = _proof_plugin(tmp_path)
    observed: list[RequestRuntimeView] = []
    _install_proof_tail(monkeypatch, observed)
    arrivals = 0
    overlap = asyncio.Event()

    async def select_persona(**_kwargs):
        nonlocal arrivals
        arrivals += 1
        if arrivals == 2:
            overlap.set()
        try:
            await asyncio.wait_for(overlap.wait(), timeout=0.25)
        except TimeoutError:
            pass
        return (
            "narrator",
            {
                "prompt": "quiet",
                "begin_dialogs": [],
                "tools": None,
                "skills": [],
            },
            None,
            False,
        )

    manager.resolve_selected_persona.side_effect = select_persona
    left = _ProofEvent(
        "42",
        "same-human",
        self_id="bot-left",
        message_id="shared-adapter-message",
    )
    right = _ProofEvent(
        "42",
        "same-human",
        self_id="bot-right",
        message_id="shared-adapter-message",
    )

    await asyncio.gather(
        EmotionalStatePlugin.on_message(plugin, left),
        EmotionalStatePlugin.on_message(plugin, right),
    )
    await asyncio.gather(
        EmotionalStatePlugin.on_llm_request(
            plugin,
            left,
            SimpleNamespace(conversation=SimpleNamespace(persona_id=None)),
        ),
        EmotionalStatePlugin.on_llm_request(
            plugin,
            right,
            SimpleNamespace(conversation=SimpleNamespace(persona_id=None)),
        ),
    )

    assert arrivals == 2, "inbound dedup must include the receiving Bot identity"
    assert overlap.is_set() is True
    assert manager.resolve_selected_persona.await_count == 2
    assert left.sender_reads == right.sender_reads == 1
    left_view = left.get_extra("_sylanne_runtime_view_v1")
    right_view = right.get_extra("_sylanne_runtime_view_v1")
    assert type(left_view) is RequestRuntimeView
    assert type(right_view) is RequestRuntimeView
    left_scope = left_view.resolved.scope
    right_scope = right_view.resolved.scope
    assert left_scope is not None and right_scope is not None
    assert left_scope.bot_ref != right_scope.bot_ref
    assert left_scope.persona_ref != right_scope.persona_ref
    assert left_scope.session_ref != right_scope.session_ref
    assert left_view.persona_runtime is not right_view.persona_runtime
    assert left_view.session_runtime is not right_view.session_runtime
    assert left_view.relation_runtime is not right_view.relation_runtime
    assert left_view.persona_runtime.store is not right_view.persona_runtime.store
    assert left_view.session_runtime.store is left_view.persona_runtime.store
    assert right_view.session_runtime.store is right_view.persona_runtime.store
    assert left_view.relation_runtime is not None
    assert right_view.relation_runtime is not None
    assert (
        left_view.relation_runtime.scope.relation_ref
        != right_view.relation_runtime.scope.relation_ref
    )
    assert {id(view) for view in observed} == {id(left_view), id(right_view)}

    left_view.persona_runtime.store.last_user_texts.set(
        left_scope.storage_token,
        "left-only",
    )
    right_view.persona_runtime.store.last_user_texts.set(
        right_scope.storage_token,
        "right-only",
    )
    assert (
        left_view.persona_runtime.store.last_user_texts.get(left_scope.storage_token)
        == "left-only"
    )
    assert (
        right_view.persona_runtime.store.last_user_texts.get(right_scope.storage_token)
        == "right-only"
    )
    assert (
        left_view.persona_runtime.store.last_user_texts.get(right_scope.storage_token)
        is None
    )
    assert (
        right_view.persona_runtime.store.last_user_texts.get(left_scope.storage_token)
        is None
    )


@pytest.mark.asyncio
async def test_same_event_on_message_begins_and_fences_transport_once(
    tmp_path,
    monkeypatch,
) -> None:
    plugin, _manager = _proof_plugin(tmp_path)
    event = _ProofEvent("42", "sender-42")
    begins: list[object] = []
    safeties: list[object] = []
    original_begin = EmotionalStatePlugin._begin_scope_transport
    original_safety = EmotionalStatePlugin._on_transport_ready_safety

    def counted_begin(live_plugin, live_event) -> bool:
        begins.append(live_event)
        return original_begin(live_plugin, live_event)

    def counted_safety(live_plugin, live_event) -> None:
        safeties.append(live_event)
        original_safety(live_plugin, live_event)

    monkeypatch.setattr(
        EmotionalStatePlugin,
        "_begin_scope_transport",
        counted_begin,
    )
    monkeypatch.setattr(
        EmotionalStatePlugin,
        "_on_transport_ready_safety",
        counted_safety,
    )

    await EmotionalStatePlugin.on_message(plugin, event)
    first_turn = event.get_extra("_sylanne_transport_turn_v1")
    await EmotionalStatePlugin.on_message(plugin, event)

    assert begins == [event]
    assert safeties == [event]
    assert event.get_extra("_sylanne_transport_turn_v1") is first_turn
    assert plugin._scope_resolver_v1.catalog.current(first_turn.session_ref) == first_turn
    assert event.get_extra("_syl_inbound_registered") is True
    assert event.get_extra("_syl_inbound_duplicate") is False


@pytest.mark.asyncio
async def test_sequential_request_reentry_preserves_published_scope_and_view(
    tmp_path,
    monkeypatch,
) -> None:
    plugin, manager = _proof_plugin(tmp_path)
    observed: list[RequestRuntimeView] = []
    _install_proof_tail(monkeypatch, observed)
    event = _ProofEvent("42", "sender-42")
    request = SimpleNamespace(conversation=SimpleNamespace(persona_id=None))
    await EmotionalStatePlugin.on_message(plugin, event)

    await EmotionalStatePlugin.on_llm_request(plugin, event, request)
    first_scope = event.get_extra("_sylanne_resolved_scope_v1")
    first_view = event.get_extra("_sylanne_runtime_view_v1")
    await EmotionalStatePlugin.on_llm_request(plugin, event, request)

    assert event.get_extra("_sylanne_resolved_scope_v1") is first_scope
    assert event.get_extra("_sylanne_runtime_view_v1") is first_view
    assert manager.resolve_selected_persona.await_count == 1
    assert event.sender_reads == 1
    assert observed == [first_view]


@pytest.mark.asyncio
async def test_concurrent_request_reentry_runs_persona_identity_and_tail_once(
    tmp_path,
    monkeypatch,
) -> None:
    plugin, manager = _proof_plugin(tmp_path)
    observed: list[RequestRuntimeView] = []
    _install_proof_tail(monkeypatch, observed)
    event = _ProofEvent("42", "sender-42")
    request = SimpleNamespace(conversation=SimpleNamespace(persona_id=None))
    entered = asyncio.Event()
    release = asyncio.Event()

    async def select_persona(**_kwargs):
        entered.set()
        await release.wait()
        return (
            "narrator",
            {
                "prompt": "quiet",
                "begin_dialogs": [],
                "tools": None,
                "skills": [],
            },
            None,
            False,
        )

    manager.resolve_selected_persona.side_effect = select_persona
    await EmotionalStatePlugin.on_message(plugin, event)

    first = asyncio.create_task(
        EmotionalStatePlugin.on_llm_request(plugin, event, request)
    )
    await entered.wait()
    second = asyncio.create_task(
        EmotionalStatePlugin.on_llm_request(plugin, event, request)
    )
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(first, second)

    resolved = event.get_extra("_sylanne_resolved_scope_v1")
    view = event.get_extra("_sylanne_runtime_view_v1")
    assert resolved.private_scope_enabled is True
    assert type(view) is RequestRuntimeView
    assert manager.resolve_selected_persona.await_count == 1
    assert event.sender_reads == 1
    assert observed == [view]


@pytest.mark.asyncio
async def test_mismatched_subject_proof_after_prepare_blocks_freeze_and_private_runtime(
    tmp_path,
    monkeypatch,
) -> None:
    plugin, manager = _proof_plugin(tmp_path)
    observed: list[RequestRuntimeView] = []
    _install_proof_tail(monkeypatch, observed)
    event = _ProofEvent("42", "sender-42")
    request = SimpleNamespace(conversation=SimpleNamespace(persona_id=None))

    await EmotionalStatePlugin.on_message(plugin, event)
    turn = event.get_extra("_sylanne_transport_turn_v1")
    event.set_extra(
        "_sylanne_turn_subject_v1",
        TurnSubjectProof(
            transport_session_token=turn.session_ref,
            turn_generation=turn.turn_generation + 1,
            subject=None,
        ),
    )

    await EmotionalStatePlugin.on_llm_request(plugin, event, request)

    resolved = event.get_extra("_sylanne_resolved_scope_v1")
    assert resolved.private_scope_enabled is False
    assert resolved.disabled_reason == "turn_subject_proof_mismatch"
    assert manager.resolve_selected_persona.await_count == 1
    assert plugin._scope_runtime_registry.persona_count == 0
    assert plugin._scope_runtime_registry.session_count == 0
    assert event.get_extra("_sylanne_runtime_view_v1") is None
    assert observed == []


@pytest.mark.asyncio
async def test_direct_llm_hook_without_on_message_proof_fails_closed(
    tmp_path,
    monkeypatch,
) -> None:
    plugin, manager = _proof_plugin(tmp_path)
    observed: list[RequestRuntimeView] = []
    _install_proof_tail(monkeypatch, observed)
    event = _ProofEvent("42", "sender-42")

    await EmotionalStatePlugin.on_llm_request(
        plugin,
        event,
        SimpleNamespace(conversation=SimpleNamespace(persona_id=None)),
    )

    resolved = event.get_extra("_sylanne_resolved_scope_v1")
    assert resolved.private_scope_enabled is False
    assert resolved.disabled_reason == "turn_subject_proof_mismatch"
    assert manager.resolve_selected_persona.await_count == 0
    assert plugin._scope_runtime_registry.persona_count == 0
    assert plugin._scope_runtime_registry.session_count == 0
    assert observed == []


@pytest.mark.asyncio
async def test_foreign_bot_subject_proof_after_prepare_blocks_freeze_and_relation_write(
    tmp_path,
    monkeypatch,
) -> None:
    plugin, manager = _proof_plugin(tmp_path)
    observed: list[RequestRuntimeView] = []
    _install_proof_tail(monkeypatch, observed)
    event = _ProofEvent("42", "sender-42")
    await EmotionalStatePlugin.on_message(plugin, event)
    turn = event.get_extra("_sylanne_transport_turn_v1")
    foreign_bot = plugin._scope_resolver_v1._identity.bot_ref(
        BotBinding(platform_id="adapter", self_id="other-bot"),
        0,
    )
    event.set_extra(
        "_sylanne_turn_subject_v1",
        TurnSubjectProof(
            transport_session_token=turn.session_ref,
            turn_generation=turn.turn_generation,
            subject=AuthenticatedSubject(
                relation_ref=RelationRef(
                    token="relation_v1_foreign_subject",
                    bot_ref=foreign_bot,
                ),
                identity_quality="event_get_sender_id",
            ),
        ),
    )

    await EmotionalStatePlugin.on_llm_request(
        plugin,
        event,
        SimpleNamespace(conversation=SimpleNamespace(persona_id=None)),
    )

    resolved = event.get_extra("_sylanne_resolved_scope_v1")
    assert resolved.private_scope_enabled is False
    assert resolved.disabled_reason == "turn_subject_proof_mismatch"
    assert manager.resolve_selected_persona.await_count == 1
    assert plugin._scope_runtime_registry.persona_count == 0
    assert plugin._scope_runtime_registry.session_count == 0
    assert observed == []


@pytest.mark.asyncio
async def test_missing_subject_keeps_session_runtime_without_relation(
    tmp_path,
    monkeypatch,
) -> None:
    plugin, _manager = _proof_plugin(tmp_path)
    observed: list[RequestRuntimeView] = []
    _install_proof_tail(monkeypatch, observed)
    event = _ProofEvent("42", "")

    await EmotionalStatePlugin.on_message(plugin, event)
    assert event.get_extra("_sylanne_turn_subject_v1") is None
    assert event.sender_reads == 0

    await EmotionalStatePlugin.on_llm_request(
        plugin,
        event,
        SimpleNamespace(conversation=SimpleNamespace(persona_id=None)),
    )

    assert len(observed) == 1
    assert event.sender_reads == 1
    assert observed[0].session_runtime is not None
    assert observed[0].relation_runtime is None
    assert plugin._scope_runtime_registry.session_count == 1


@pytest.mark.asyncio
async def test_same_authenticated_subject_reuses_relation_across_transport_sessions(
    tmp_path,
    monkeypatch,
) -> None:
    plugin, _manager = _proof_plugin(tmp_path)
    observed: list[RequestRuntimeView] = []
    _install_proof_tail(monkeypatch, observed)
    request = SimpleNamespace(conversation=SimpleNamespace(persona_id=None))
    first = _ProofEvent("42", "same-human")
    second = _ProofEvent("84", "same-human")

    for event in (first, second):
        await EmotionalStatePlugin.on_message(plugin, event)
        await EmotionalStatePlugin.on_llm_request(plugin, event, request)

    assert len(observed) == 2
    assert observed[0].resolved.scope.session_ref != observed[1].resolved.scope.session_ref
    assert observed[0].session_runtime is not observed[1].session_runtime
    assert observed[0].relation_runtime is observed[1].relation_runtime


@pytest.mark.asyncio
async def test_late_hook_rejects_runtime_view_after_event_scope_tamper(
    tmp_path,
    monkeypatch,
) -> None:
    plugin, _manager = _proof_plugin(tmp_path)
    observed: list[RequestRuntimeView] = []
    _install_proof_tail(monkeypatch, observed)
    event = _ProofEvent("42", "sender-42")
    await EmotionalStatePlugin.on_message(plugin, event)
    await EmotionalStatePlugin.on_llm_request(
        plugin,
        event,
        SimpleNamespace(conversation=SimpleNamespace(persona_id=None)),
    )
    event.set_extra(
        "_sylanne_resolved_scope_v1",
        observed[0].resolved.disabled(
            "tampered",
            resolved_at_ms=observed[0].resolved.resolved_at_ms,
        ),
    )

    with pytest.raises(ScopeUnavailable):
        with plugin._bind_runtime_for_event(event):
            pass


def test_identity_is_read_once_only_after_persona_prepare() -> None:
    on_message_tree = ast.parse(
        textwrap.dedent(inspect.getsource(EmotionalStatePlugin.on_message))
    )
    on_message_identity_reads = [
        node
        for node in ast.walk(on_message_tree)
        if isinstance(node, ast.Attribute)
        and node.attr == "resolve_authenticated_identity"
    ]
    assert on_message_identity_reads == []

    request_tree = ast.parse(
        textwrap.dedent(inspect.getsource(EmotionalStatePlugin._on_llm_request_inner))
    )
    request_identity_reads = [
        node
        for node in ast.walk(request_tree)
        if isinstance(node, ast.Attribute)
        and node.attr == "resolve_authenticated_identity"
    ]
    assert len(request_identity_reads) == 1

    for method in (
        EmotionalStatePlugin._on_scope_ready_llm_request,
        EmotionalStatePlugin._on_message_after_scope_frozen,
    ):
        tree = ast.parse(textwrap.dedent(inspect.getsource(method)))
        attributes = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
        }
        assert "get_sender_id" not in attributes
        assert "resolve_authenticated_identity" not in attributes
