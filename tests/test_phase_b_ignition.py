"""Phase B 测试：personality_saddle（A7 外壳）+ IgnitionArbiter（点火/分岔）+ 铁律②不clamp。

架构 §1.4/§3.3.1。验证：
- 鞍点是人格显函数（中性锚定到 SDK 旧常数 0.95/0.10 + 单调性）。
- 高表达驱力 → speak；低驱力且无未表达积分 → hold + 写 scratch['silent'] 带 reason。
- IgnitionArbiter 只比较不 clamp（铁律②）：它产的 observability Intent 不带 affect，
  绝不改写其它能力的 affect（点火只门控表达、不门控漂移）。
- 与 Renderer compose 模式集成：hold → Reply.silent(reason)。
"""

from __future__ import annotations

from sylanne_alpha.v2core.capabilities.ignition import IgnitionArbiter, personality_saddle
from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Intent, Phase
from sylanne_alpha.v2core.domains.emotion import EmotionLedger
from sylanne_alpha.v2core.renderer import DefaultRenderer


def _body(**kw) -> BodySnapshot:
    p = kw.pop("personality", {})
    return BodySnapshot(session_key="u", turns=1, personality=p, **kw)


def _ctx(body: BodySnapshot, *, domains=None, intents=None) -> BeatContext:
    c = BeatContext(session_key="u", event=None, body=body, phase=Phase.DELIBERATE,
                    domains=domains or {})
    for it in (intents or []):
        c.add(it)
    return c


def test_saddle_neutral_anchoring() -> None:
    """trait≈0.5 → 鞍点回到 SDK 旧常数语义 0.95 / 0.10 / 0.15。

    Fable 版鞍点只用 surface 实测真实暴露的 trait（curiosity/warmth_bias/
    sovereignty_guard/patience），没有任何恒回落中性的死轴。
    """
    body = _body(personality={"curiosity": 0.5, "warmth_bias": 0.5,
                              "sovereignty_guard": 0.5, "patience": 0.5})
    express_at, hold_below, hold_floor = personality_saddle(body)
    assert abs(express_at - 0.95) < 1e-9
    assert abs(hold_below - 0.10) < 1e-9
    assert abs(hold_floor - 0.15) < 1e-9


def test_saddle_monotonicity() -> None:
    """好奇/暖底↑ → express_at↓（更早开口）；主权↑ → hold_below↑；耐性↑ → hold_floor↑。"""
    lo = _body(personality={"curiosity": 0.0, "warmth_bias": 0.0,
                            "sovereignty_guard": 0.0, "patience": 0.0})
    hi = _body(personality={"curiosity": 1.0, "warmth_bias": 1.0,
                            "sovereignty_guard": 1.0, "patience": 1.0})
    e_lo, h_lo, f_lo = personality_saddle(lo)
    e_hi, h_hi, f_hi = personality_saddle(hi)
    assert e_hi < e_lo          # 好奇+暖底强 → 鞍点低 → 易点火
    assert h_hi > h_lo          # 主权强 → hold 下区大
    assert f_hi > f_lo          # 耐性好 → 更能憋住赌气


def test_saddle_uses_only_exposed_traits() -> None:
    """实测 surface 只暴露这六个 trait——鞍点读不存在的 trait 时回中性，不读死轴。"""
    real_surface_traits = {"curiosity": 0.62, "edge": 0.41, "intimacy_gravity": 0.50,
                           "patience": 0.48, "sovereignty_guard": 0.64, "warmth_bias": 0.57}
    body = _body(personality=real_surface_traits)
    e, h, f = personality_saddle(body)
    # 全部三个阈值都应偏离中性锚点（证明每条轴都吃到了真实 trait，无死轴）
    assert e != 0.95 and h != 0.10 and f != 0.15


def test_high_drive_speaks() -> None:
    """表达驱力越过鞍点 → action=speak，不写 silent。"""
    body = _body(expression_drive=0.99,
                 personality={"expression_drive_trait": 0.5, "sovereignty_guard": 0.5})
    ctx = _ctx(body, domains={"emotion": EmotionLedger()})
    out = IgnitionArbiter().deliberate(ctx)
    assert out.payload["action"] == "speak"
    assert "silent" not in ctx.scratch


def test_low_drive_holds_with_reason() -> None:
    """低驱力 + 无未表达积分 → action=hold，写 scratch['silent'] 带 reason（D8）。"""
    body = _body(expression_drive=0.0,
                 personality={"expression_drive_trait": 0.5, "sovereignty_guard": 0.5})
    ctx = _ctx(body, domains={"emotion": EmotionLedger()})   # 新 ledger，_unexpressed=0
    out = IgnitionArbiter().deliberate(ctx)
    assert out.payload["action"] == "hold"
    assert ctx.scratch.get("silent", {}).get("reason") == "ignition_hold"


def test_ignition_does_not_clamp_affect() -> None:
    """铁律②：IgnitionArbiter 的 Intent 不带 affect，不改写他人 affect（只门控表达不门控漂移）。"""
    body = _body(expression_drive=0.0,
                 personality={"expression_drive_trait": 0.5, "sovereignty_guard": 0.5})
    other = Intent(source="appraisal", affect={"warmth": 0.8, "tension": 0.3}, priority=0.6)
    ctx = _ctx(body, domains={"emotion": EmotionLedger()}, intents=[other])
    ign = IgnitionArbiter().deliberate(ctx)
    assert ign.affect == {}, "点火 Intent 不应携带 affect"
    # 他人 affect 原样保留（漂移不被点火决策削减）
    appraisal_intents = [i for i in ctx.intents if i.source == "appraisal"]
    assert appraisal_intents[0].affect == {"warmth": 0.8, "tension": 0.3}


def test_hold_integrates_to_renderer_silent() -> None:
    """compose 模式：IgnitionArbiter 写 silent → DefaultRenderer 产 Reply.silent(reason)。"""
    body = _body(expression_drive=0.0,
                 personality={"expression_drive_trait": 0.5, "sovereignty_guard": 0.5})
    ctx = _ctx(body, domains={"emotion": EmotionLedger()})
    IgnitionArbiter().deliberate(ctx)
    reply = DefaultRenderer().render(ctx, draft=None)   # compose 模式
    from sylanne_alpha.v2core.contracts import ReplyKind
    assert reply.kind is ReplyKind.SILENT
    assert reply.meta.get("reason") == "ignition_hold"
