"""Phase D 测试：SomaticMarker（连续偏置禁二元门）+ Outreach（沉默积累→分岔，不连发）。

架构 §3.3 / §5.3。
"""

from __future__ import annotations

import pytest

from sylanne_alpha.v2core.capabilities.somatic import (
    OutreachCapability,
    SomaticBias,
    SomaticMarkerCapability,
)
from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase
from sylanne_alpha.v2core.domains.emotion import EmotionLedger
from sylanne_alpha.v2core.domains.user_model import UserModelDomain


def _body(**kw) -> BodySnapshot:
    return BodySnapshot(session_key="u", turns=1, **kw)


def _ctx(body, *, text="", domains=None, scratch=None) -> BeatContext:
    c = BeatContext(session_key="u", event=None, body=body, text=text,
                    phase=Phase.DELIBERATE, domains=domains or {})
    if scratch:
        c.scratch.update(scratch)
    return c


def test_somatic_bias_is_continuous_not_binary() -> None:
    """scar 连续抑制 approach_recall（不是 <0 就砍断的二元门）。"""
    low = SomaticMarkerCapability().deliberate(_ctx(_body(scar=0.0)))
    mid = SomaticMarkerCapability().deliberate(_ctx(_body(scar=0.3)))
    hi = SomaticMarkerCapability().deliberate(_ctx(_body(scar=0.9)))
    r_low = low.payload["somatic"]["approach_recall"]
    r_mid = mid.payload["somatic"]["approach_recall"]
    r_hi = hi.payload["somatic"]["approach_recall"]
    assert r_low > r_mid > r_hi, "approach_recall 应随 scar 连续下降"


def test_somatic_writes_bias_to_scratch() -> None:
    ctx = _ctx(_body(scar=0.2, sovereignty=0.5, exhaustion=0.3, repair_pressure=0.4))
    SomaticMarkerCapability().deliberate(ctx)
    bias = ctx.scratch.get("somatic_bias")
    assert isinstance(bias, SomaticBias)
    assert bias.dominant in ("scar", "strain", "low_sovereignty", "exhaustion")


def test_somatic_does_not_gate_drift() -> None:
    """铁律②：躯体标记 priority=0，不参与表达驱力融合（只偏置不门控漂移）。"""
    out = SomaticMarkerCapability().deliberate(_ctx(_body(scar=0.5)))
    assert out.priority == 0.0
    assert out.affect == {}


def test_outreach_silent_when_not_idle() -> None:
    """正常对话轮（有用户文本）→ Outreach 不抢话。"""
    ctx = _ctx(_body(), text="你好", domains={"emotion": EmotionLedger(), "usermodel": UserModelDomain()})
    assert OutreachCapability().deliberate(ctx) is None


def test_outreach_fires_on_idle_with_accumulated_silence() -> None:
    """空闲 + 未表达积累 → 产 reach 倾向。"""
    emo = EmotionLedger()
    # 灌出未表达积分：沉默轮 ingest（render_outcome 非 SPEAK）
    for i in range(5):
        ec = BeatContext(session_key="u", event=None, body=_body(warmth=0.6, tension=0.4),
                         phase=Phase.EVOLVE, domains={})
        ec.scratch["render_outcome"] = "silent"
        emo.ingest(ec)
    assert emo.hold_free_energy(_body()) > 0.0   # 积分起来了
    ctx = _ctx(_body(), text="", domains={"emotion": emo, "usermodel": UserModelDomain()},
               scratch={"idle": True, "now": 100.0})
    out = OutreachCapability().deliberate(ctx)
    assert out is not None and out.payload.get("want") == "reach_out"
    assert out.payload["g_reach"] > 0.0


def test_outreach_no_reflood_after_expression() -> None:
    """reach/表达后未表达积分被释放 → g_reach 回落，不连发（旧 P4 轰炸消解）。"""
    emo = EmotionLedger()
    for i in range(5):
        ec = BeatContext(session_key="u", event=None, body=_body(warmth=0.6, tension=0.4),
                         phase=Phase.EVOLVE, domains={})
        ec.scratch["render_outcome"] = "silent"
        emo.ingest(ec)
    g_before = emo.hold_free_energy(_body())
    # 表达发生（SPEAK）→ 积分衰减
    for _ in range(3):
        ec = BeatContext(session_key="u", event=None, body=_body(warmth=0.6),
                         phase=Phase.EVOLVE, domains={})
        ec.scratch["render_outcome"] = "speak"
        emo.ingest(ec)
    g_after = emo.hold_free_energy(_body())
    assert g_after < g_before, "表达后 hold 能量应回落（不连发）"
