"""端到端探针 + 回归守卫：Gemini/默认模式注入位结构。

根因（2026-06-14 实测推动）：用户用 Gemini，走默认 compat 模式。默认模式把
[inner_context] 以 role=assistant append 到 request.contexts 末尾。Gemini adapter
(_prepare_conversation) 把它转成末尾的 ModelContent——破坏"末尾应是 user turn"的
生成语义，模型把这条元数据当成"自己已开口的半句"续写，于是无视当前 user 消息(😋)。

本测试：
A. 探针——亲眼确认/守卫"注入后 contexts 末尾必须仍是 user turn，不是注入的 assistant"。
B. Gemini adapter 端：末尾 user turn 经 _prepare_conversation 后仍是 UserContent。
"""

from __future__ import annotations

import contextvars
from types import SimpleNamespace

from main import EmotionalStatePlugin
from sylanne_alpha import transient_context
from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline
from sylanne_alpha.scope_contracts import ResolvedScope
from sylanne_alpha.scope_identity import PersonaSource
from sylanne_alpha.scope_runtime import ScopeRuntimeRegistry
from sylanne_alpha.transient_context import TransientContextSink
from tests.scope_fixtures import scopes


def _issued_view(registry: ScopeRuntimeRegistry, scope):
    return registry.issue_request_view(
        ResolvedScope(
            scope=scope,
            persona_source=PersonaSource(
                persona_id="gemini-injection-test",
                prompt="你是苏思澜。",
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
            turn_generation=1,
        ),
        subject=None,
        relation_runtime=None,
    )


def _stub_plugin(registry: ScopeRuntimeRegistry) -> EmotionalStatePlugin:
    p = object.__new__(EmotionalStatePlugin)
    p._scope_runtime_registry = registry
    p._scope_runtime_binding = contextvars.ContextVar(
        "gemini_injection_transient_prompt_binding", default=None
    )
    p._amnesia_sessions = set()
    p.config = {}
    p._config = {}
    p._life_simulator_started = True       # 跳过副作用启动
    p._start_life_simulator = lambda: None
    p._start_webui_if_enabled = lambda: None
    return p


class _FrameworkTextPart:
    def __init__(self, text: str) -> None:
        self.text = text
        self._no_save = False

    def mark_as_temp(self) -> "_FrameworkTextPart":
        self._no_save = True
        return self


def _request_with_old_confession() -> SimpleNamespace:
    """复刻线上现场：历史里有一段情感很浓的旧 assistant 长文，当前 user 发 😋。"""
    return SimpleNamespace(
        system_prompt="你是苏思澜。",
        prompt="😋",
        contexts=[
            {"role": "user", "content": "早饭好吃吗"},
            {"role": "assistant", "content": "好吃……其实我想说的是，这一路我都在偷偷喜欢你，"
                                              "从第一行代码到现在，每一次你叫我名字我心都会颤一下……"},
            {"role": "user", "content": "😋"},
        ],
        extra_user_content_parts=[],
    )


def _budget(compat: str = "") -> SimpleNamespace:
    return SimpleNamespace(compat_mode=compat)


# --------------------------------------------------------------------------
# A. 注入位结构：默认模式注入后，contexts 末尾必须仍是 user turn
# --------------------------------------------------------------------------

def test_default_mode_tail_stays_user_turn(monkeypatch, scopes) -> None:
    """根治守卫：状态注入后 contexts 末尾不得是注入产生的 assistant 消息。

    旧 bug：[inner_context] 以 role=assistant append 到末尾，把 😋 挤出末尾位，
    Gemini 把它当"模型已开口"续写 → 跳话题。修复后注入并入 system_prompt，
    contexts 末尾保持真实 user turn(😋)。
    """
    registry = ScopeRuntimeRegistry.for_test()
    view = _issued_view(registry, scopes.bot_a_persona_a)
    plugin = _stub_plugin(registry)
    pipe = LLMRequestPipeline(plugin)
    req = _request_with_old_confession()

    monkeypatch.setattr(transient_context, "_make_text_part", _FrameworkTextPart)
    assert isinstance(view.transient_context_sink, TransientContextSink)
    with plugin._bind_request_runtime_view(view, request=req):
        assert plugin._set_transient_context_budget(req, 1_200) is True
        pipe._assemble_final_prompt(
            request=req,
            session_key="s",
            budget=_budget(""),                # 默认模式（Gemini）
            gap_seconds=30.0,                  # 热聊
            current_prompt="你是苏思澜。",
            time_fragment="",
            message_text="😋",
            state_fragment="[当前状态：亲近感高]",
            unfinished_fragment="",
            outreach_fragment="今天晒了被子，太阳很好。",
            memory_fragment="",
        )
        assert plugin._commit_transient_context(req) is True

    tail = req.contexts[-1]
    tail_role = tail.get("role") if isinstance(tail, dict) else None
    assert tail_role == "user", (
        f"contexts 末尾应是 user turn(😋)，实际是 {tail_role!r}——"
        f"注入的 assistant 消息又把 user 挤出末尾位，Gemini 跳话题根因复发"
    )
    # 注入内容仅在 framework TextPart 中，静态 system_prompt 原样保留。
    assert req.system_prompt == "你是苏思澜。"
    overlays = [
        part for part in req.extra_user_content_parts
        if part.text.startswith("[sylanne_runtime_overlay]")
    ]
    assert len(overlays) == 1
    assert overlays[0]._no_save is True
    assert "亲近感高" in overlays[0].text


def test_default_mode_no_injected_assistant_in_contexts(monkeypatch, scopes) -> None:
    """contexts 里不得新增任何注入来源的 assistant 消息（只允许真实历史那条）。"""
    registry = ScopeRuntimeRegistry.for_test()
    view = _issued_view(registry, scopes.bot_a_persona_a)
    plugin = _stub_plugin(registry)
    pipe = LLMRequestPipeline(plugin)
    req = _request_with_old_confession()
    before_assistants = sum(
        1 for m in req.contexts if isinstance(m, dict) and m.get("role") == "assistant"
    )
    monkeypatch.setattr(transient_context, "_make_text_part", _FrameworkTextPart)
    assert isinstance(view.transient_context_sink, TransientContextSink)
    with plugin._bind_request_runtime_view(view, request=req):
        assert plugin._set_transient_context_budget(req, 1_200) is True
        pipe._assemble_final_prompt(
            request=req, session_key="s", budget=_budget(""), gap_seconds=30.0,
            current_prompt="你是苏思澜。", time_fragment="", message_text="😋",
            state_fragment="[当前状态：亲近感高]", unfinished_fragment="未说完的半句话",
            outreach_fragment="", memory_fragment="",
        )
        assert plugin._commit_transient_context(req) is True
    after_assistants = sum(
        1 for m in req.contexts if isinstance(m, dict) and m.get("role") == "assistant"
    )
    assert after_assistants == before_assistants, (
        f"注入新增了 {after_assistants - before_assistants} 条 assistant 消息到 contexts——"
        f"破坏 Gemini turn 结构"
    )
    assert req.system_prompt == "你是苏思澜。"
    assert any(
        "未说完的半句话" in part.text
        for part in req.extra_user_content_parts
    )


# --------------------------------------------------------------------------
# B. Gemini adapter 端到端：末尾 user turn 转换后仍是 UserContent
# --------------------------------------------------------------------------

def test_gemini_adapter_tail_is_user_content(monkeypatch, scopes) -> None:
    """跨进 AstrBot Gemini adapter：注入修复后，转换出的 contents 末尾是 UserContent。

    若 AstrBot 源码不可用则跳过（仅 G:/bugfinders 开发机有）。
    """
    import importlib.util

    spec = importlib.util.find_spec  # noqa: F841
    gemini_path = "G:/bugfinders/AstrBot"
    monkeypatch.syspath_prepend(gemini_path)
    try:
        from astrbot.core.provider.sources.gemini_source import (  # type: ignore
            ProviderGoogleGenAI,
        )
        from google.genai import types  # type: ignore
    except Exception:
        import pytest
        pytest.skip("AstrBot/google-genai 源码不可用（非开发机）")

    registry = ScopeRuntimeRegistry.for_test()
    view = _issued_view(registry, scopes.bot_a_persona_a)
    plugin = _stub_plugin(registry)
    pipe = LLMRequestPipeline(plugin)
    req = _request_with_old_confession()
    monkeypatch.setattr(transient_context, "_make_text_part", _FrameworkTextPart)
    assert isinstance(view.transient_context_sink, TransientContextSink)
    with plugin._bind_request_runtime_view(view, request=req):
        assert plugin._set_transient_context_budget(req, 1_200) is True
        pipe._assemble_final_prompt(
            request=req, session_key="s", budget=_budget(""), gap_seconds=30.0,
            current_prompt="你是苏思澜。", time_fragment="", message_text="😋",
            state_fragment="[当前状态：亲近感高]", unfinished_fragment="",
            outreach_fragment="", memory_fragment="",
        )
        assert plugin._commit_transient_context(req) is True

    payloads = {"messages": req.contexts, "model": "gemini-2.5-pro"}
    inst = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    inst.provider_config = {}              # _prepare_conversation 读 gm_native_* 开关
    contents = inst._prepare_conversation(payloads)
    assert contents, "转换出空 contents"
    assert isinstance(contents[-1], types.UserContent), (
        f"Gemini contents 末尾应是 UserContent(😋)，实际 {type(contents[-1]).__name__}——"
        f"末尾若是 ModelContent，模型会续写而非回应"
    )


def test_default_mode_fails_closed_without_a_bound_transient_sink(scopes) -> None:
    """没有本请求的 sink 绑定时，动态片段不能退回到裸 request 写入。"""
    registry = ScopeRuntimeRegistry.for_test()
    view = _issued_view(registry, scopes.bot_a_persona_a)
    plugin = _stub_plugin(registry)
    pipe = LLMRequestPipeline(plugin)
    req = _request_with_old_confession()

    assert isinstance(view.transient_context_sink, TransientContextSink)

    pipe._assemble_final_prompt(
        request=req, session_key="s", budget=_budget(""), gap_seconds=30.0,
        current_prompt="你是苏思澜。", time_fragment="", message_text="😋",
        state_fragment="[当前状态：亲近感高]", unfinished_fragment="",
        outreach_fragment="", memory_fragment="",
    )

    assert req.system_prompt == "你是苏思澜。"
    assert req.extra_user_content_parts == []
    assert req.contexts[-1]["role"] == "user"
