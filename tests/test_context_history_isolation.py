from __future__ import annotations

import ast
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sylanne_alpha.llm_request_pipeline import (
    LLMRequestPipeline,
    _PROACTIVE_TEMPLATE_PLACEHOLDER,
    _PROACTIVE_TEMPLATE_SIGNATURE,
)
from sylanne_alpha.llm_response_pipeline import LLMResponsePipeline


@dataclass
class _Message:
    role: str
    content: Any
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


class _Event:
    def __init__(self, request: Any) -> None:
        self.extras: dict[str, Any] = {"provider_request": request}

    def get_extra(self, key: str, default: Any = None) -> Any:
        return self.extras.get(key, default)

    def set_extra(self, key: str, value: Any) -> None:
        self.extras[key] = value


class _StoppableEvent:
    plugins_name: list[str] | None = None

    def __init__(self) -> None:
        self._stopped = False

    def stop_event(self) -> None:
        self._stopped = True

    def is_stopped(self) -> bool:
        return self._stopped


def _request(*, contexts: list[dict[str, Any]], token_usage: int = 900) -> Any:
    return SimpleNamespace(
        contexts=contexts,
        conversation=SimpleNamespace(token_usage=token_usage),
        prompt="current user message",
        image_urls=[],
        audio_urls=[],
        extra_user_content_parts=[],
        system_prompt="",
    )


def _response_pipeline() -> LLMResponsePipeline:
    return LLMResponsePipeline(SimpleNamespace())


def _source_path(*parts: str) -> Path:
    return Path(__file__).parents[1].joinpath(*parts)


def _request_context_writes(source_path: Path) -> list[int]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    return sorted(
        {
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Store)
            and node.attr == "contexts"
            and isinstance(node.value, ast.Name)
            and node.value.id == "request"
        }
    )


def _on_agent_done_registration_priority() -> int:
    tree = ast.parse(_source_path("main.py").read_text(encoding="utf-8"))
    decorators = [
        decorator
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "on_agent_done"
        for decorator in node.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Name)
        and decorator.func.id == "_optional_agent_done_filter"
    ]
    assert len(decorators) == 1, "expected one registered async on_agent_done hook"

    priority_nodes = [
        keyword.value
        for keyword in decorators[0].keywords
        if keyword.arg == "priority"
    ]
    if not priority_nodes:
        return 0
    assert len(priority_nodes) == 1
    priority_node = priority_nodes[0]
    assert (
        isinstance(priority_node, ast.Constant)
        and isinstance(priority_node.value, int)
        and not isinstance(priority_node.value, bool)
    ), "on_agent_done priority must be an integer literal"
    return priority_node.value


def test_request_cleanup_never_mutates_provider_request_contexts() -> None:
    contexts = [
        {"role": "assistant", "content": "[inner_context] private state"},
        {
            "role": "user",
            "content": f"{_PROACTIVE_TEMPLATE_SIGNATURE}\nold injected task",
        },
    ]
    before = json.dumps(contexts, ensure_ascii=False, sort_keys=True)
    request = _request(contexts=contexts)
    plugin = SimpleNamespace(
        _store=SimpleNamespace(
            stream_buffers={},
            stream_first_sent={},
            segmented_tasks={},
        ),
        config={},
        _config={},
    )

    asyncio.run(
        LLMRequestPipeline(plugin)._clean_incoming_message(
            None,
            request,
            "",
            "session",
            False,
            False,
        )
    )

    assert request.contexts is contexts
    assert json.dumps(request.contexts, ensure_ascii=False, sort_keys=True) == before


def test_inner_context_injection_is_provider_neutral_and_history_read_only() -> None:
    system_prompts: list[str] = []
    for provider_model in ("standard", "claude"):
        contexts = [{"role": "user", "content": "existing history"}]
        before = json.dumps(contexts, ensure_ascii=False, sort_keys=True)
        request = _request(contexts=contexts)
        request.provider_model = provider_model
        plugin = SimpleNamespace(
            config={},
            _rhythm_learner=SimpleNamespace(
                get_reply_length_factor=lambda _session_key: 1.0
            ),
            _amnesia_sessions=set(),
            _life_simulator_started=True,
        )

        LLMRequestPipeline(plugin)._assemble_final_prompt(
            request=request,
            session_key="session",
            budget=None,
            gap_seconds=0.0,
            current_prompt=request.prompt,
            time_fragment="",
            message_text=request.prompt,
            state_fragment="quietly attentive",
            unfinished_fragment="",
            outreach_fragment="",
            memory_fragment="",
        )

        system_prompts.append(request.system_prompt)
        assert "[inner_context]" in request.system_prompt
        assert request.contexts is contexts
        assert json.dumps(request.contexts, ensure_ascii=False, sort_keys=True) == before

    assert system_prompts[0] == system_prompts[1]


def test_llm_pipelines_have_no_request_contexts_write_through() -> None:
    source_paths = (
        _source_path("sylanne_alpha", "llm_request_pipeline.py"),
        _source_path("sylanne_alpha", "llm_response_pipeline.py"),
    )
    writes = {
        source_path.relative_to(_source_path()).as_posix(): lines
        for source_path in source_paths
        if (lines := _request_context_writes(source_path))
    }

    assert writes == {}, f"request.contexts write-through assignments found: {writes}"


def test_main_agent_done_hook_has_restore_priority() -> None:
    priority = _on_agent_done_registration_priority()

    assert priority >= 100, (
        "main.py on_agent_done must register with priority >= 100 so history "
        f"restoration cannot be skipped; got {priority}"
    )


def test_astrbot_runs_restore_before_a_priority_zero_handler_stops(
    monkeypatch: Any,
) -> None:
    from astrbot.core.pipeline import context_utils
    from astrbot.core.star import star_handler as star_handler_module
    from astrbot.core.star.star_handler import (
        EventType,
        StarHandlerMetadata,
        StarHandlerRegistry,
    )

    registry = StarHandlerRegistry()
    plugins: dict[str, Any] = {}
    calls: list[str] = []

    async def ordinary_stop(event: _StoppableEvent, *_args: Any) -> None:
        calls.append("ordinary_stop")
        event.stop_event()

    async def sylanne_restore(_event: _StoppableEvent, *_args: Any) -> None:
        calls.append("sylanne_restore")

    def register(name: str, handler: Any, priority: int) -> None:
        module_path = f"tests.context_history.{name}"
        plugins[module_path] = SimpleNamespace(
            activated=True,
            name=name,
            reserved=False,
        )
        registry.append(
            StarHandlerMetadata(
                event_type=EventType.OnAgentDoneEvent,
                handler_full_name=f"{module_path}.{name}",
                handler_name=name,
                handler_module_path=module_path,
                handler=handler,
                event_filters=[],
                extras_configs={"priority": priority},
            )
        )

    register("ordinary_stop", ordinary_stop, priority=0)
    restore_priority = _on_agent_done_registration_priority()
    register("sylanne_restore", sylanne_restore, priority=restore_priority)
    monkeypatch.setattr(context_utils, "star_handlers_registry", registry)
    monkeypatch.setattr(context_utils, "star_map", plugins)
    monkeypatch.setattr(star_handler_module, "star_map", plugins)

    stopped = asyncio.run(
        context_utils.call_event_hook(
            _StoppableEvent(),
            EventType.OnAgentDoneEvent,
            SimpleNamespace(messages=[]),
            None,
        )
    )

    assert stopped is True
    assert calls == ["sylanne_restore", "ordinary_stop"], (
        f"priority {restore_priority} let a priority-0 handler stop propagation "
        f"before Sylanne restored history: {calls}"
    )


def test_provider_history_projection_is_reversible_and_invalidates_trusted_tokens() -> None:
    proactive = _Message(
        "user", f"{_PROACTIVE_TEMPLATE_SIGNATURE}\nold injected task"
    )
    leaked_inner = _Message("assistant", "[inner_context] private state")
    current = _Message("user", "current user message")
    messages = [
        _Message("user", "my name is Lin"),
        _Message("assistant", "I will remember that"),
        proactive,
        leaked_inner,
        current,
    ]
    original_messages = list(messages)
    request = _request(contexts=[])
    event = _Event(request)
    run_context = SimpleNamespace(messages=messages)
    pipeline = _response_pipeline()

    assert pipeline.on_agent_begin(event, run_context) is True
    assert request.conversation.token_usage == 0
    assert run_context.messages[2] is not proactive
    assert run_context.messages[2].content == _PROACTIVE_TEMPLATE_PLACEHOLDER
    assert leaked_inner not in run_context.messages

    generated = _Message("assistant", "current answer")
    run_context.messages.append(generated)
    assert pipeline.on_agent_done(event, run_context, None) is True

    assert run_context.messages == original_messages + [generated]
    assert run_context.messages[2] is proactive
    assert run_context.messages[3] is leaked_inner
    assert event.get_extra("_syl_provider_history_txn") is None


def test_agent_done_restores_history_without_semantic_correlation() -> None:
    proactive = _Message(
        "user", f"{_PROACTIVE_TEMPLATE_SIGNATURE}\nold injected task"
    )
    current = _Message("user", "current user message")
    request = _request(contexts=[])
    event = _Event(request)
    run_context = SimpleNamespace(messages=[proactive, current])
    pipeline = _response_pipeline()

    pipeline.on_agent_begin(event, run_context)
    assert event.get_extra("_syl_semantic_beat_correlation") is None
    pipeline.on_agent_done(event, run_context, None)

    assert run_context.messages[0] is proactive
    assert run_context.messages[0].content.startswith(_PROACTIVE_TEMPLATE_SIGNATURE)


def test_orphan_tool_is_provider_only_and_returns_before_persistence() -> None:
    first = _Message("user", "older real question")
    orphan = _Message(
        "assistant",
        "",
        tool_calls=[{"id": "missing-result", "type": "function"}],
    )
    current = _Message("user", "current user message")
    request = _request(contexts=[])
    event = _Event(request)
    run_context = SimpleNamespace(messages=[first, orphan, current])
    pipeline = _response_pipeline()

    pipeline.on_agent_begin(event, run_context)
    assert run_context.messages == [first, current]

    generated = _Message("assistant", "answer")
    run_context.messages.append(generated)
    pipeline.on_agent_done(event, run_context, None)
    assert run_context.messages == [first, orphan, current, generated]


def test_hidden_history_is_not_resurrected_after_real_context_truncation() -> None:
    old = _Message("user", "old turn")
    leaked_inner = _Message("assistant", "[inner_context] private state")
    current = _Message("user", "current user message")
    request = _request(contexts=[])
    event = _Event(request)
    run_context = SimpleNamespace(messages=[old, leaked_inner, current])
    pipeline = _response_pipeline()

    pipeline.on_agent_begin(event, run_context)
    assert run_context.messages == [old, current]
    run_context.messages[:] = [current, _Message("assistant", "answer")]
    pipeline.on_agent_done(event, run_context, None)

    assert old not in run_context.messages
    assert leaked_inner not in run_context.messages


def test_clean_history_does_not_invalidate_trusted_token_usage() -> None:
    current = _Message("user", "current user message")
    request = _request(contexts=[], token_usage=321)
    event = _Event(request)
    run_context = SimpleNamespace(messages=[current])

    assert _response_pipeline().on_agent_begin(event, run_context) is False
    assert request.conversation.token_usage == 321
    assert event.get_extra("_syl_provider_history_txn") is None


def test_release_paths_have_no_hajide_compatibility_symbols() -> None:
    release_paths = (
        _source_path("_conf_schema.json"),
        _source_path("main.py"),
        _source_path("sylanne_alpha", "llm_request_pipeline.py"),
        _source_path("sylanne_alpha", "llm_response_pipeline.py"),
    )
    findings: dict[str, list[int]] = {}
    for source_path in release_paths:
        matching_lines = [
            lineno
            for lineno, line in enumerate(
                source_path.read_text(encoding="utf-8").splitlines(),
                start=1,
            )
            if "hajide" in line.casefold() or "哈基德" in line
        ]
        if matching_lines:
            findings[source_path.relative_to(_source_path()).as_posix()] = matching_lines

    assert findings == {}, f"Hajide compatibility symbols remain in release paths: {findings}"
