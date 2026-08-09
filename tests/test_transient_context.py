"""Request-local TextPart overlays must remain transient and capability-bound."""

from __future__ import annotations

import asyncio
import contextvars
import inspect
from types import SimpleNamespace

import pytest

from main import EmotionalStatePlugin
from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline
from sylanne_alpha import transient_context
from sylanne_alpha.scope_contracts import ResolvedScope
from sylanne_alpha.scope_identity import PersonaSource
from sylanne_alpha.scope_runtime import (
    RequestRuntimeView,
    ScopeMismatch,
    ScopeRuntimeRegistry,
)
from sylanne_alpha.transient_context import TransientContextSink
from tests.scope_fixtures import scopes


class _FrameworkTextPart:
    def __init__(self, text: str) -> None:
        self.text = text
        self._no_save = False

    def mark_as_temp(self) -> "_FrameworkTextPart":
        self._no_save = True
        return self


def _resolved(scope, *, generation: int = 1) -> ResolvedScope:
    return ResolvedScope(
        scope=scope,
        persona_source=PersonaSource(
            persona_id="transient-context-test",
            prompt="static persona",
            begin_dialogs=(),
            tools=None,
            skills=None,
            resolution_source="test",
        ),
        identity_quality="event_self_id",
        resolution_source="test",
        resolved_at_ms=1,
        private_scope_enabled=True,
        disabled_reason=None,
        turn_generation=generation,
    )


def _issued_view(registry: ScopeRuntimeRegistry, scope, *, generation: int = 1):
    return registry.issue_request_view(
        _resolved(scope, generation=generation),
        subject=None,
        relation_runtime=None,
    )


def _request(existing_part: _FrameworkTextPart) -> SimpleNamespace:
    return SimpleNamespace(
        system_prompt="static persona",
        prompt="actual user words",
        contexts=[{"role": "user", "content": "actual user words"}],
        extra_user_content_parts=[existing_part],
    )


def _bare_plugin(registry: ScopeRuntimeRegistry) -> EmotionalStatePlugin:
    plugin = object.__new__(EmotionalStatePlugin)
    plugin._scope_runtime_registry = registry
    plugin._scope_runtime_binding = contextvars.ContextVar(
        "test_transient_context_binding", default=None
    )
    plugin._amnesia_sessions = set()
    plugin._cached_system_prompts = {}
    plugin.config = {}
    plugin._config = {}
    plugin._life_simulator_started = True
    plugin._start_life_simulator = lambda: None
    plugin._start_webui_if_enabled = lambda: None
    return plugin


def _overlay_parts(request: SimpleNamespace) -> list[_FrameworkTextPart]:
    return [
        part
        for part in request.extra_user_content_parts
        if getattr(part, "text", "").startswith("[sylanne_runtime_overlay]")
    ]


def test_commit_adds_one_temp_textpart_without_mutating_persisted_request_fields(
    monkeypatch, scopes
) -> None:
    monkeypatch.setattr(transient_context, "_make_text_part", _FrameworkTextPart)
    registry = ScopeRuntimeRegistry.for_test()
    view = _issued_view(registry, scopes.bot_a_persona_a)
    existing = _FrameworkTextPart("framework temporary").mark_as_temp()
    request = _request(existing)
    system_prompt = request.system_prompt
    prompt = request.prompt
    contexts = request.contexts
    contexts_snapshot = [dict(item) for item in contexts]
    extra = request.extra_user_content_parts
    sink = view.transient_context_sink

    assert isinstance(sink, TransientContextSink)
    with registry.bind_transient_context_sink(view, request):
        assert sink.add(request, "state", "unbudgeted", "request", 20) is False
        assert sink.set_budget(request, 1_000) is True
        assert sink.add(request, "state", "present", "request", 20) is True
        assert sink.add(request, "time", "now", "request", 10) is True
        assert sink.commit(request) is True

    overlays = _overlay_parts(request)
    assert request.system_prompt is system_prompt
    assert request.prompt is prompt
    assert request.contexts is contexts
    assert request.contexts == contexts_snapshot
    assert request.extra_user_content_parts is extra
    assert request.extra_user_content_parts[0] is existing
    assert len(overlays) == 1
    assert overlays[0]._no_save is True
    assert overlays[0].text.startswith("[sylanne_runtime_overlay]")
    assert overlays[0].text.index("present") < overlays[0].text.index("now")


def test_part_factory_failure_has_zero_request_mutation(monkeypatch, scopes) -> None:
    def _fail(_text: str) -> _FrameworkTextPart:
        raise RuntimeError("factory unavailable")

    monkeypatch.setattr(transient_context, "_make_text_part", _fail)
    registry = ScopeRuntimeRegistry.for_test()
    view = _issued_view(registry, scopes.bot_a_persona_a)
    existing = _FrameworkTextPart("framework temporary").mark_as_temp()
    request = _request(existing)
    before_extra = list(request.extra_user_content_parts)
    before_system = request.system_prompt
    before_prompt = request.prompt
    before_contexts = request.contexts
    sink = view.transient_context_sink

    with registry.bind_transient_context_sink(view, request):
        assert sink.set_budget(request, 1_000) is True
        assert sink.add(request, "state", "present", "request", 20) is True
        assert sink.commit(request) is False

    assert request.system_prompt is before_system
    assert request.prompt is before_prompt
    assert request.contexts is before_contexts
    assert request.extra_user_content_parts == before_extra
    assert request.extra_user_content_parts[0] is existing


def test_sink_fails_closed_for_missing_forged_released_or_wrong_request_context(
    monkeypatch, scopes
) -> None:
    monkeypatch.setattr(transient_context, "_make_text_part", _FrameworkTextPart)
    registry = ScopeRuntimeRegistry.for_test()
    scope = scopes.bot_a_persona_a
    view = _issued_view(registry, scope)
    request = _request(_FrameworkTextPart("framework temporary"))
    other_request = _request(_FrameworkTextPart("other"))
    sink = view.transient_context_sink

    assert sink.add(request, "state", "unbound", "request", 20) is False
    with registry.bind_transient_context_sink(view, request):
        assert sink.add(other_request, "state", "wrong", "request", 20) is False

    forged = RequestRuntimeView(
        resolved=view.resolved,
        persona_runtime=view.persona_runtime,
        session_runtime=view.session_runtime,
    )
    object.__setattr__(forged, "transient_context_sink", sink)
    with pytest.raises(ScopeMismatch):
        with registry.bind_transient_context_sink(forged, request):
            pass

    assert registry.release_request_view(view) is True
    assert sink.add(request, "state", "released", "request", 20) is False


def test_sink_rejects_double_commit_and_retained_contexts(monkeypatch, scopes) -> None:
    monkeypatch.setattr(transient_context, "_make_text_part", _FrameworkTextPart)
    registry = ScopeRuntimeRegistry.for_test()
    view = _issued_view(registry, scopes.bot_a_persona_a)
    request = _request(_FrameworkTextPart("framework temporary"))
    sink = view.transient_context_sink

    with registry.bind_transient_context_sink(view, request):
        assert sink.set_budget(request, 1_000) is True
        assert sink.add(request, "state", "present", "request", 20) is True
        assert sink.commit(request) is True
        assert sink.commit(request) is False
        copied_context = contextvars.copy_context()

    assert copied_context.run(sink.add, request, "state", "stale", "request", 20) is False

    async def _child_after_exit() -> bool:
        return sink.add(request, "state", "stale child", "request", 20)

    async def _run() -> bool:
        with registry.bind_transient_context_sink(view, request):
            child = asyncio.create_task(_child_after_exit())
        return await child

    assert asyncio.run(_run()) is False
    assert len(_overlay_parts(request)) == 1


def test_sink_bounds_and_lru_eviction_clear_collected_fragments(monkeypatch, scopes) -> None:
    monkeypatch.setattr(transient_context, "_make_text_part", _FrameworkTextPart)
    registry = ScopeRuntimeRegistry.for_test()
    view = _issued_view(registry, scopes.bot_a_persona_a)
    request = _request(_FrameworkTextPart("framework temporary"))
    sink = view.transient_context_sink

    with registry.bind_transient_context_sink(view, request):
        assert sink.set_budget(request, transient_context._MAX_OVERLAY_CHARS) is True
        assert sink.add(
            request,
            "state",
            "x" * (transient_context._MAX_FRAGMENT_CHARS + 1),
            "request",
            20,
        ) is False
        for index in range(transient_context._MAX_FRAGMENTS):
            assert sink.add(request, f"slot-{index}", "x", "request", 20) is True
        assert sink.add(request, "overflow", "x", "request", 20) is False

    for generation in range(2, 10):
        _issued_view(registry, scopes.bot_a_persona_a, generation=generation)

    assert sink._fragments == []
    assert sink.add(request, "state", "evicted", "request", 20) is False


def test_sink_dedupes_tags_orders_channels_and_counts_rendered_budget(
    monkeypatch, scopes
) -> None:
    monkeypatch.setattr(transient_context, "_make_text_part", _FrameworkTextPart)
    registry = ScopeRuntimeRegistry.for_test()
    view = _issued_view(registry, scopes.bot_a_persona_a)
    request = _request(_FrameworkTextPart("framework temporary"))
    sink = view.transient_context_sink
    one_fragment = (
        "[sylanne_runtime_overlay]\n"
        "[state source=request lifecycle=turn]\n"
        "x"
    )

    with registry.bind_transient_context_sink(view, request):
        assert sink.set_budget(request, len(one_fragment) - 1) is True
        assert sink.add(request, "state", "x", "request", 20) is False
        assert sink.set_budget(request, 1_000) is True
        assert sink.add(request, "deliverable", "last", "deliverable", 0) is True
        assert sink.add(request, "state", "same", "request", 20) is True
        assert sink.add(request, "state", "same", "request", 20) is True
        assert sink.add(request, "v2_mind", "mind", "v2core", 1) is True
        assert sink.commit(request) is True

    overlay = _overlay_parts(request)[0].text
    assert overlay.count("same") == 1
    assert "[state source=request lifecycle=turn]" in overlay
    assert overlay.index("same") < overlay.index("mind") < overlay.index("last")
    assert overlay.endswith("last")


def test_hard_budget_keeps_admitted_realtime_and_rejects_later_low_priority(
    monkeypatch, scopes
) -> None:
    monkeypatch.setattr(transient_context, "_make_text_part", _FrameworkTextPart)
    registry = ScopeRuntimeRegistry.for_test()
    view = _issued_view(registry, scopes.bot_a_persona_a)
    request = _request(_FrameworkTextPart("framework temporary"))
    sink = view.transient_context_sink
    realtime_render = (
        "[sylanne_runtime_overlay]\n"
        "[realtime_assistant_history source=realtime lifecycle=turn]\n"
        "keep realtime"
    )

    with registry.bind_transient_context_sink(view, request):
        assert sink.set_budget(request, len(realtime_render)) is True
        assert sink.add(
            request,
            "realtime_assistant_history",
            "keep realtime",
            "realtime",
            5,
        ) is True
        # A consumed realtime record has a truthful admission: later work may
        # be refused, but the accepted record is never silently displaced.
        assert sink.add(request, "memory", "later low priority", "request", 99) is False
        assert sink.set_budget(request, len(realtime_render) - 1) is False
        assert sink.commit(request) is True

    overlay = _overlay_parts(request)[0].text
    assert overlay == realtime_render
    assert len(overlay) == len(realtime_render)
    assert "later low priority" not in overlay


def test_first_bound_request_is_sealed_while_same_request_can_nest(monkeypatch, scopes) -> None:
    monkeypatch.setattr(transient_context, "_make_text_part", _FrameworkTextPart)
    registry = ScopeRuntimeRegistry.for_test()
    view = _issued_view(registry, scopes.bot_a_persona_a)
    request_a = _request(_FrameworkTextPart("framework temporary"))
    request_b = _request(_FrameworkTextPart("other request"))
    sink = view.transient_context_sink

    with registry.bind_transient_context_sink(view, request_a):
        assert sink.set_budget(request_a, 1_000) is True
        assert sink.add(request_a, "state", "from A", "request", 20) is True
        with registry.bind_transient_context_sink(view, request_a):
            assert sink.add(request_a, "nested", "still A", "request", 30) is True

    with pytest.raises(ScopeMismatch):
        with registry.bind_transient_context_sink(view, request_b):
            pass

    with registry.bind_transient_context_sink(view, request_a):
        assert sink.commit(request_a) is True

    overlay = _overlay_parts(request_a)[0].text
    assert "from A" in overlay and "still A" in overlay
    assert _overlay_parts(request_b) == []


def test_nested_binding_restores_outer_lease_and_pipeline_commits_once(
    monkeypatch, scopes
) -> None:
    monkeypatch.setattr(transient_context, "_make_text_part", _FrameworkTextPart)
    registry = ScopeRuntimeRegistry.for_test()
    view = _issued_view(registry, scopes.bot_a_persona_a)
    plugin = _bare_plugin(registry)
    pipeline = LLMRequestPipeline(plugin)
    existing = _FrameworkTextPart("framework temporary").mark_as_temp()
    request = _request(existing)
    request.system_prompt = "request-owned static prompt"
    before_system = request.system_prompt
    before_prompt = request.prompt
    before_contexts = request.contexts
    before_contexts_snapshot = [dict(item) for item in request.contexts]

    with plugin._bind_request_runtime_view(view, request=request):
        assert plugin._set_transient_context_budget(request, 1_000) is True
        pipeline._cache_system_prompt(scopes.bot_a_persona_a.storage_token)
        pipeline._assemble_final_prompt(
            request=request,
            session_key=scopes.bot_a_persona_a.storage_token,
            budget=None,
            gap_seconds=10.0,
            current_prompt=request.prompt,
            time_fragment="[time]",
            message_text=request.prompt,
            state_fragment="present",
            unfinished_fragment="",
            outreach_fragment="",
            memory_fragment="",
        )
        with plugin._bind_request_runtime_view(view, request=request):
            assert plugin._add_transient_context(
                request, "nested", "still live", "test", 50
            ) is True
        assert plugin._commit_transient_context(request) is True
        assert plugin._commit_transient_context(request) is False

    overlays = _overlay_parts(request)
    assert plugin._cached_system_prompts[scopes.bot_a_persona_a.storage_token] == "static persona"
    assert request.system_prompt is before_system
    assert request.prompt is before_prompt
    assert request.contexts is before_contexts
    assert request.contexts == before_contexts_snapshot
    assert request.extra_user_content_parts[0] is existing
    assert len(overlays) == 1
    assert "[time]" in overlays[0].text
    assert "present" in overlays[0].text
    assert "still live" in overlays[0].text


def test_static_persona_cache_precedes_v2_percept_stage() -> None:
    source = inspect.getsource(LLMRequestPipeline._process_llm_request_final)

    assert source.index("self._cache_system_prompt(session_key)") < source.index(
        "await apply_v2core_request"
    )
