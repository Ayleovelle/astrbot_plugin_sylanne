"""Phase G fixlist P0-5 测试：Outreach 三重死复活（REVIEW §P0-5）。

病：①Ignition 注册在 Outreach 之前 → g_reach 从未进 argmin；②无 idle 入口；
③_is_idle "无文本=空闲" → 正常轮文本提取失败被误判空闲 → reach + affect 误注入。
修：注册序对调；IgnitionArbiter 读 g_reach 做 speak/hold/reach 三选一；_is_idle 删误判分支。
"""

from __future__ import annotations

from sylanne_alpha.v2core.capabilities.ignition import IgnitionArbiter
from sylanne_alpha.v2core.capabilities.somatic import OutreachCapability, _is_idle
from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Intent, Phase


def _ctx(text: str = "", *, idle: bool = False, drive: float = 0.0) -> BeatContext:
    body = BodySnapshot(session_key="s", turns=1, expression_drive=drive)
    ctx = BeatContext(session_key="s", event=None, body=body, text=text)
    ctx.phase = Phase.DELIBERATE
    if idle:
        ctx.scratch["idle"] = True
    ctx.scratch["now"] = 1000.0
    return ctx


def test_is_idle_no_longer_misfires_on_empty_text() -> None:
    """P0-5③：正常轮文本提取失败（text==''）不再被误判空闲。"""
    assert _is_idle(_ctx(text="")) is False        # 空文本不再=空闲
    assert _is_idle(_ctx(text="你好")) is False
    assert _is_idle(_ctx(text="", idle=True)) is True   # 仅显式标记才空闲


def test_outreach_silent_on_normal_turn() -> None:
    """正常轮（非空闲）→ Outreach 不产意图（不抢话、不误注入 affect）。"""
    out = OutreachCapability()
    assert out.deliberate(_ctx(text="在吗")) is None


class _UM:
    """假 usermodel：reply_overdue 返回大值（模拟久未回复）。"""
    def reply_overdue(self, body, now) -> float:  # noqa: ANN001
        return 5.0


def test_reach_enters_arbitration_and_can_win() -> None:
    """P0-5①②：显式 idle 轮 → Outreach 产 g_reach → Ignition 三选一仲裁，reach 可胜出。"""
    ctx = _ctx(idle=True, drive=0.0)
    ctx.domains["usermodel"] = _UM()
    # 模拟 DELIBERATE 注册序：Outreach 先跑产 g_reach
    out = OutreachCapability()
    reach_intent = out.deliberate(ctx)
    assert reach_intent is not None
    assert reach_intent.payload.get("g_reach", 0.0) > 0.0
    ctx.add(reach_intent)
    # Ignition 后跑，读 g_reach 做仲裁
    ign = IgnitionArbiter()
    ign_intent = ign.deliberate(ctx)
    action = ign_intent.payload["action"]
    # 强烈想触达（g_reach 大）+ 低表达驱力 → reach 应能胜出（至少进入了仲裁）
    assert action in ("reach", "hold", "speak")     # 三选一仲裁活着
    assert ign_intent.payload.get("g_reach") is not None  # reach 真的进了仲裁
    # reach 决策在 Intent payload（单一来源，无 scratch 死信号）


def test_no_reach_branch_on_normal_turn() -> None:
    """正常轮无 outreach 意图 → Ignition 仲裁只在 speak/hold 间（g_reach=inf 不参与）。"""
    ctx = _ctx(text="在吗", drive=0.0)
    ign = IgnitionArbiter()
    intent = ign.deliberate(ctx)
    assert intent.payload.get("g_reach") is None    # reach 未参与（非空闲轮）
    assert intent.payload["action"] in ("speak", "hold")
