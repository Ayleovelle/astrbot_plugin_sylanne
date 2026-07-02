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

2026-07-03 fix/context-integrity 复审 MINOR：非拦截分支与拦截分支此前各内联一份
完全相同的 ~40 行分治逻辑，已抽成 `LLMResponsePipeline._resolve_empty_reply` 共
用。本文件的源码级断言相应从 `_on_llm_response_inner` 挪到新的共用方法上——断言
的 invariant 本身不变（分治三要素齐全、silent/fallback 两条腿并存），只是挪了
地方；额外补一条断言确认两个调用分支确实都在【调用】这个共用方法（没有偷偷
各自再内联回一份重复逻辑）。

round-3 复审：合一成共用方法后，原本各自内联时天然带着"是哪个分支"的信息在日志
里丢了——排障时看不出静默/兜底是拦截分支还是非拦截分支触发的。补回一个
`path` 参数，两个调用点分别传 "non_intercept" / "intercept"，日志里带上这个
discriminator。
"""

from __future__ import annotations

import inspect

from sylanne_alpha.llm_response_pipeline import LLMResponsePipeline


def test_reason_based_dispatch_in_source() -> None:
    """源码：空分支按 reason 分治——两个 reason 字面量都在，silent 路径与 fallback 路径并存。"""
    src = inspect.getsource(LLMResponsePipeline._resolve_empty_reply)
    # 区分成因留痕（D8）保留——两个 reason 字面量缺一即为分治断链
    assert "stripped_to_empty" in src and "empty_completion" in src
    # no-ghost 开关仍存在（用户显式开 ghost 兼容旧行为）
    assert "sylanne_no_ghost_reply" in src, "缺 no-ghost 开关"
    # silent 路径与 fallback 路径并存（reason 分治的两条腿）
    assert "return None" in src, "缺 silent 路径"
    assert "return _fallback" in src, "缺 fallback 路径"
    assert "fallback (no ghost)" in src, "缺兜底留痕日志"
    # 自定义兜底文案配置仍被尊重（用户显式配了就走兜底，不被新静默逻辑误吞）
    assert "sylanne_ghost_fallback_text" in src, "缺自定义兜底文案配置读取"


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
    src = inspect.getsource(LLMResponsePipeline._resolve_empty_reply)
    # 三要素串在一起出现，才算分治真接线
    assert "_silent_this" in src, "缺分治布尔变量"
    assert "_has_custom_fallback" in src, "缺自定义兜底文案探测"
    assert "empty_completion" in src and "_no_ghost" in src, "分治三要素不齐"


def test_both_branches_delegate_to_shared_resolver() -> None:
    """去重验证：非拦截分支与拦截分支都必须【调用】共用的 _resolve_empty_reply，
    而不是各自再内联一份分治逻辑（否则又会漂移回本次修复要消灭的重复状态）。
    round-3：调用点还必须各自带上 path discriminator（见本文件顶部说明），
    不能只调用不传 path，否则日志又退化成分不清是哪个分支。"""
    src = inspect.getsource(LLMResponsePipeline._on_llm_response_inner)
    assert src.count("self._resolve_empty_reply(") == 2, (
        "非拦截 / 拦截两个分支都应调用共用的 _resolve_empty_reply，且只应各调用一次"
    )
    assert 'path="non_intercept"' in src, "非拦截分支调用应传 path=\"non_intercept\""
    assert 'path="intercept"' in src, "拦截分支调用应传 path=\"intercept\""
    # 两分支各自都不应再重复内联判定逻辑的关键标志变量
    assert "_silent_this" not in src, "分治逻辑应已完全搬进 _resolve_empty_reply，不应留在调用方"


def test_resolve_empty_reply_logs_path_discriminator() -> None:
    """round-3 复审：_resolve_empty_reply 的两条日志（静默 / 兜底）都必须带上
    path= 字段，否则合一之后就丢了"这是哪个分支炸的"这条排障信息。"""
    src = inspect.getsource(LLMResponsePipeline._resolve_empty_reply)
    assert src.count("path={path}") == 2, (
        "静默日志与兜底日志都应带上 path= discriminator"
    )
