"""回归测试：#1 乱码外泄修复 —— query_agent_state 工具不再把原始诊断 JSON 糊给用户。

旧 bug：_llm_tool_query_agent_state 调 event.plain_result(json.dumps(host.diagnostics()))，
把 16KB 内部 JSON 直接发用户 → 用户看到"乱码"。
修复：委托 query_agent_state_tool，返回紧凑投影【字符串】给 LLM（由 LLM 转述），不外泄原始内部结构。
"""

from __future__ import annotations

import inspect

import pytest

from sylanne_alpha.public_api import PublicAPI


def test_llm_tool_query_agent_state_does_not_use_plain_result() -> None:
    """方法体内不得再调 event.plain_result / 直接 host.diagnostics()（仅 docstring 可提及）。"""
    src = inspect.getsource(PublicAPI._llm_tool_query_agent_state)
    # 砍掉 docstring 后看真实代码体
    body = src.split('"""', 2)[-1] if '"""' in src else src
    assert "plain_result" not in body, "修复回退：仍在用 plain_result 把原始 JSON 发用户"
    assert "host.diagnostics" not in body, "修复回退：仍在直接 dump host.diagnostics"
    assert "query_agent_state_tool" in body, "应委托紧凑投影的 query_agent_state_tool"


@pytest.mark.asyncio
async def test_llm_tool_delegates_and_returns_compact_string() -> None:
    """委托 query_agent_state_tool 并原样返回其紧凑字符串（不经 plain_result 旁路发用户）。"""

    class _StubPlugin:
        config = {"llm_tool_response_max_chars": 400}

        def _cfg_int(self, k: str, d: int) -> int:
            return int(self.config.get(k, d))

    api = PublicAPI.__new__(PublicAPI)
    api._p = _StubPlugin()  # type: ignore[attr-defined]

    sentinel = '{"kind":"agent_state_query","state":"integrated"}'
    called = {"n": 0}

    async def _fake_tool(event):  # noqa: ANN001
        called["n"] += 1
        return sentinel

    api.query_agent_state_tool = _fake_tool  # type: ignore[method-assign]

    class _Event:
        def plain_result(self, _s):  # 若被调用即说明 bug 复发
            raise AssertionError("不应调用 plain_result —— 原始结构会外泄给用户")

    out = await api._llm_tool_query_agent_state(_Event())
    assert out == sentinel, "应原样返回委托结果（字符串给 LLM）"
    assert called["n"] == 1
    assert isinstance(out, str)


# ---------------------------------------------------------------------------
# AUDIT-20260612-001：工具返回值浮点诱饵根因修复
# 根因链：query_agent_state 返回 4-6 位小数 → LLM "验算冲动" → 连环调
# astrbot_execute_python ×10-30。修复（包装层收口）：①浮点全量化到 2 位；
# ②首位注入"请勿计算/勿调代码工具"指令（审计 §7.4：原提示被数字淹没，须前移）。
# ---------------------------------------------------------------------------

def test_tool_json_quantizes_floats_and_injects_no_compute_note() -> None:
    payload = {
        "kind": "agent_state_query",
        "snapshots": {
            "emotion": {"warmth": 0.652344, "arousal": 0.341256,
                        "nested": [0.123456, {"deep": 0.999999}]},
        },
    }
    raw = PublicAPI._tool_json(payload)
    # ① 高精度浮点不复存在（4+ 位小数是"需要验算"的视觉诱饵）
    assert "0.652344" not in raw and "0.123456" not in raw
    assert "0.65" in raw and "0.12" in raw and "1.0" in raw
    # ② "请勿计算"指令在首位（不被数字淹没）
    import json as _json
    parsed = _json.loads(raw)
    first_key = next(iter(parsed))
    assert first_key == "note"
    assert "请勿计算" in parsed["note"] and "代码工具" in parsed["note"]


def test_quantize_floats_recursive_pure() -> None:
    q = PublicAPI._quantize_floats
    assert q(0.123456) == 0.12
    assert q({"a": [1.999999, {"b": (0.555555,)}], "s": "text", "i": 7}) == \
        {"a": [2.0, {"b": [0.56]}], "s": "text", "i": 7}


@pytest.mark.asyncio
async def test_query_agent_state_tool_output_is_sanitized() -> None:
    """实弹包装层：query_agent_state_tool 的输出已量化 + 带请勿计算指令。"""

    class _StubPlugin:
        config = {"llm_tool_response_max_chars": 4000}

    api = PublicAPI.__new__(PublicAPI)
    api._p = _StubPlugin()  # type: ignore[attr-defined]

    async def _fake_query(event, **kw):  # noqa: ANN001, ANN003
        return {"kind": "agent_state_query",
                "snapshots": {"emotion": {"warmth": 0.652344, "drive": 0.901234}}}

    api.query_agent_state = _fake_query  # type: ignore[method-assign]
    out = await api.query_agent_state_tool(None)
    assert "0.652344" not in out and "0.901234" not in out
    assert "请勿计算" in out
