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

from types import SimpleNamespace

from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline


def _stub_plugin() -> SimpleNamespace:
    p = SimpleNamespace()
    p._amnesia_sessions = set()
    p.config = {}
    p._life_simulator_started = True       # 跳过副作用启动
    p._start_life_simulator = lambda: None
    p._start_webui_if_enabled = lambda: None

    # 默认模式（非 Claude）走 _assemble else 分支，直接写 system_prompt；
    # 本 stub 仅 advisory/Claude 等仍调 _append_temp_text_part 的路径复用。
    def _append_temp_text_part(request, text, source="", budget=None):  # noqa: ANN001
        cur = str(getattr(request, "system_prompt", "") or "")
        request.system_prompt = f"{cur}\n{text}".strip()
        return True
    p._append_temp_text_part = _append_temp_text_part
    return p


def _request_with_old_confession() -> SimpleNamespace:
    """复刻线上现场：历史里有一段情感很浓的旧 assistant 长文，当前 user 发 😋。"""
    return SimpleNamespace(
        system_prompt="你是苏思澜。",
        contexts=[
            {"role": "user", "content": "早饭好吃吗"},
            {"role": "assistant", "content": "好吃……其实我想说的是，这一路我都在偷偷喜欢你，"
                                              "从第一行代码到现在，每一次你叫我名字我心都会颤一下……"},
            {"role": "user", "content": "😋"},
        ],
    )


def _budget(compat: str = "") -> SimpleNamespace:
    return SimpleNamespace(compat_mode=compat)


# --------------------------------------------------------------------------
# A. 注入位结构：默认模式注入后，contexts 末尾必须仍是 user turn
# --------------------------------------------------------------------------

def test_default_mode_tail_stays_user_turn() -> None:
    """根治守卫：状态注入后 contexts 末尾不得是注入产生的 assistant 消息。

    旧 bug：[inner_context] 以 role=assistant append 到末尾，把 😋 挤出末尾位，
    Gemini 把它当"模型已开口"续写 → 跳话题。修复后注入并入 system_prompt，
    contexts 末尾保持真实 user turn(😋)。
    """
    pipe = LLMRequestPipeline(_stub_plugin())
    req = _request_with_old_confession()

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

    tail = req.contexts[-1]
    tail_role = tail.get("role") if isinstance(tail, dict) else None
    assert tail_role == "user", (
        f"contexts 末尾应是 user turn(😋)，实际是 {tail_role!r}——"
        f"注入的 assistant 消息又把 user 挤出末尾位，Gemini 跳话题根因复发"
    )
    # 注入内容应进了 system_prompt（不持久化、不破坏 turn 结构）
    assert "亲近感高" in req.system_prompt, "状态没进 system_prompt"
    assert "你是苏思澜" in req.system_prompt, "原 system_prompt 被覆盖"


def test_default_mode_no_injected_assistant_in_contexts() -> None:
    """contexts 里不得新增任何注入来源的 assistant 消息（只允许真实历史那条）。"""
    pipe = LLMRequestPipeline(_stub_plugin())
    req = _request_with_old_confession()
    before_assistants = sum(
        1 for m in req.contexts if isinstance(m, dict) and m.get("role") == "assistant"
    )
    pipe._assemble_final_prompt(
        request=req, session_key="s", budget=_budget(""), gap_seconds=30.0,
        current_prompt="你是苏思澜。", time_fragment="", message_text="😋",
        state_fragment="[当前状态：亲近感高]", unfinished_fragment="未说完的半句话",
        outreach_fragment="", memory_fragment="",
    )
    after_assistants = sum(
        1 for m in req.contexts if isinstance(m, dict) and m.get("role") == "assistant"
    )
    assert after_assistants == before_assistants, (
        f"注入新增了 {after_assistants - before_assistants} 条 assistant 消息到 contexts——"
        f"破坏 Gemini turn 结构"
    )
    assert "未说完的半句话" in req.system_prompt


# --------------------------------------------------------------------------
# B. Gemini adapter 端到端：末尾 user turn 转换后仍是 UserContent
# --------------------------------------------------------------------------

def test_gemini_adapter_tail_is_user_content(monkeypatch) -> None:
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

    pipe = LLMRequestPipeline(_stub_plugin())
    req = _request_with_old_confession()
    pipe._assemble_final_prompt(
        request=req, session_key="s", budget=_budget(""), gap_seconds=30.0,
        current_prompt="你是苏思澜。", time_fragment="", message_text="😋",
        state_fragment="[当前状态：亲近感高]", unfinished_fragment="",
        outreach_fragment="", memory_fragment="",
    )

    payloads = {"messages": req.contexts, "model": "gemini-2.5-pro"}
    inst = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    inst.provider_config = {}              # _prepare_conversation 读 gm_native_* 开关
    contents = inst._prepare_conversation(payloads)
    assert contents, "转换出空 contents"
    assert isinstance(contents[-1], types.UserContent), (
        f"Gemini contents 末尾应是 UserContent(😋)，实际 {type(contents[-1]).__name__}——"
        f"末尾若是 ModelContent，模型会续写而非回应"
    )
