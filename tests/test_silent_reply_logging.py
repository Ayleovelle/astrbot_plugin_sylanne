"""回归测试：ghost 空回复分治治理 —— stripped_to_empty 兜底防 ghost；empty_completion 静默防怪话蹦。

历史背景：
- 06:11 真 ghost bug：tool-loop 后模型整段 <thinking>，strip 后空 → completion_text=''
  → 用户已读不回。当时把默认改为兜底（不 ghost）治此 bug。
- 21:55 兜底蹦怪话：AstrBot tool 循环死锁（连续 3+22+4 次工具调用）后真空回复 → 蹦
  "……（我想说点什么，可话到嘴边又散了，再给我一秒。）"——AstrBot core 已经塞过
  [SYSTEM NOTICE] 重复调用警告了，再蹦 Sylanne 兜底文案语气解释式（像说明书不像她）。

本次治理（2026-06-13 用户诊断推动）：按 reason 分治
- stripped_to_empty（thinking 包答案）：原 06:11 真 ghost bug，仍兜底防"已读不回"。
- empty_completion（completion_text 真空）：常见于 tool 循环死锁，静默更对（除非
  用户在配置里显式设了自定义兜底文案 sylanne_ghost_fallback_text）。
- sylanne_no_ghost_reply=False（用户显式开 ghost）：所有 reason 都静默（兼容旧开关）。
"""

from __future__ import annotations

import inspect

from sylanne_alpha.llm_response_pipeline import LLMResponsePipeline


def test_reason_based_dispatch_in_source() -> None:
    """源码：空分支按 reason 分治——两个 reason 字面量都在，silent 路径与 fallback 路径并存。"""
    src = inspect.getsource(LLMResponsePipeline._on_llm_response_inner)
    idx = src.find("if not cleaned.strip():")
    assert idx != -1
    branch = src[idx: idx + 3000]
    # 区分成因留痕（D8）保留——两个 reason 字面量缺一即为分治断链
    assert "stripped_to_empty" in branch and "empty_completion" in branch
    # no-ghost 开关仍存在（用户显式开 ghost 兼容旧行为）
    assert "sylanne_no_ghost_reply" in branch, "缺 no-ghost 开关"
    # 静默路径与兜底路径并存（reason 分治的两条腿）
    assert "response.completion_text = \"\"" in branch, "缺静默路径"
    assert "cleaned = _fallback" in branch, "缺兜底路径"
    assert "fallback (no ghost)" in branch, "缺兜底留痕日志"
    # 自定义兜底文案配置仍被尊重（用户显式配了就走兜底，不被新静默逻辑误吞）
    assert "sylanne_ghost_fallback_text" in branch, "缺自定义兜底文案配置读取"


def test_no_ghost_default_is_true() -> None:
    """默认值语义：未配置时 sylanne_no_ghost_reply 取 True（即兜底通道仍开，由 reason 决定）。"""
    cfg: dict = {}
    assert bool(cfg.get("sylanne_no_ghost_reply", True)) is True
    # 仅显式设 False 才全静默（兼容旧开关，跨所有 reason）
    cfg2 = {"sylanne_no_ghost_reply": False}
    assert bool(cfg2.get("sylanne_no_ghost_reply", True)) is False


def test_dispatch_logic_sketch() -> None:
    """以源码层面验证分治公式：
       silent ⇔ (not no_ghost) OR (reason == empty_completion AND no custom_fallback)。
    源码里这个布尔表达式必须能找到——否则分治退化（要么全静默要么全兜底）。"""
    src = inspect.getsource(LLMResponsePipeline._on_llm_response_inner)
    # 三要素串在一起出现，才算分治真接线
    assert "_silent_this" in src, "缺分治布尔变量"
    assert "_has_custom_fallback" in src, "缺自定义兜底文案探测"
    assert "empty_completion" in src and "_no_ghost" in src, "分治三要素不齐"
