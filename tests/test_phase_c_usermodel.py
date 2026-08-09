"""Phase C 测试：UserModelDomain（预测你/同步/超期）+ Mentalize + Appraisal + 整轮集成。

架构 §3.2.1/§3.3.1。验证二重奏核心：她预测你→你回应→算 user_pe→精度加权更新→同步度变化。
"""

from __future__ import annotations

import tempfile

import pytest

from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost
from sylanne_alpha.v2core.body_port_v2 import CanonicalKernelBodyPort
from sylanne_alpha.v2core.capabilities.expression import ExpressionCapability
from sylanne_alpha.v2core.capabilities.ignition import IgnitionArbiter
from sylanne_alpha.v2core.capabilities.mentalize import AppraisalCapability, MentalizeCapability
from sylanne_alpha.v2core.capabilities.recall import RecallCapability
from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase
from sylanne_alpha.v2core.domains.emotion import EmotionLedger
from sylanne_alpha.v2core.domains.user_model import UserModelDomain, UserView
from sylanne_alpha.v2core.self_core import SelfCore
from sylanne_alpha.v2core.turn_runner import TurnRunner


def _body(**kw) -> BodySnapshot:
    return BodySnapshot(session_key="u", turns=1, **kw)


def _evolve_ctx(body, text, *, now=0.0, dom) -> BeatContext:
    c = BeatContext(session_key="u", event=None, body=body, text=text, phase=Phase.EVOLVE,
                    domains={"usermodel": dom})
    c.scratch["now"] = now
    return c


def _perceive_ctx(body, text) -> BeatContext:
    """predict_you 现吃 ctx（复用 scratch signals）；不预置 signals 则回落 read_signals(text)。"""
    return BeatContext(session_key="u", event=None, body=body, text=text)


def test_predict_you_returns_userview() -> None:
    dom = UserModelDomain()
    v = dom.predict_you(_perceive_ctx(_body(surprise=0.4, warmth=0.3), "你好呀❤️"))
    assert isinstance(v, UserView)
    assert v.surprised_by_you == 0.4
    assert set(v.predicted_disposition) == {"warmth", "engagement", "defensiveness", "distress"}


def test_user_pe_converges_she_learns_you() -> None:
    """二重奏核心：连续一致的你 → user_pe 单调收敛（她越来越懂你，广义同步逼近）。

    注：synchrony 的空历史基线是人造中性 0.5，不能拿学习后的值跟它比；真正的性质是
    【预测误差随轮次下降】——后半段平均 user_pe 显著低于前半段。
    """
    dom = UserModelDomain()
    for i in range(12):
        dom.ingest(_evolve_ctx(_body(surprise=0.1, warmth=0.5), "我很开心想你❤️", now=float(i), dom=dom))
    hist = list(dom._pe_history)
    first_half = sum(hist[:6]) / 6
    second_half = sum(hist[6:]) / 6
    assert second_half < first_half, f"预测误差应随学习收敛 {first_half:.3f}->{second_half:.3f}"
    assert hist[-1] < hist[1], "末轮误差应远低于初期"


def test_precision_rises_on_consistent_input() -> None:
    """一致输入 → 处置精度（grip）上升。"""
    dom = UserModelDomain()
    g0 = dom.predict_you(_perceive_ctx(_body(), "x")).grip
    for i in range(8):
        dom.ingest(_evolve_ctx(_body(surprise=0.05, warmth=0.6), "想你啦抱抱❤️", now=float(i), dom=dom))
    g1 = dom.predict_you(_perceive_ctx(_body(), "x")).grip
    assert g1 > g0


def test_reply_overdue_zero_without_rhythm() -> None:
    dom = UserModelDomain()
    assert dom.reply_overdue(_body(), now=100.0) == 0.0   # 无节律→0


def test_appraisal_produces_assessment_not_hardcoded() -> None:
    """Appraisal 产连续 assessment（valence/arousal/wound_risk，SDK apply_assessment
    真实消费键）；novelty 派生 body.surprise（canonical PE 不重算）；
    不产 intent 标签——绝不喂 SDK 里 intent=="撒娇" 的硬编码路径。"""
    cap = AppraisalCapability()
    ctx = BeatContext(session_key="u", event=None,
                      body=_body(surprise=0.6, warmth=-0.2, repair_pressure=0.3),
                      text="你为什么不理我", phase=Phase.PERCEPT)
    intent = cap.perceive(ctx)
    assert intent is not None
    a = ctx.scratch["assessment"]
    assert set(a) == {"valence", "arousal", "wound_risk"}
    assert "intent" not in a                       # 不喂硬编码 intent 路径
    assert a["arousal"] > 0.0                      # 高 surprise → 唤起
    assert intent.payload["appraisal"]["novelty"] == 0.6


def test_mentalize_low_sync_seeks_clarify() -> None:
    """失同步 → DELIBERATE 产 clarify 意图喂点火。"""
    dom = UserModelDomain()
    # 灌入高 user_pe 拉低同步
    for i in range(6):
        dom.ingest(_evolve_ctx(_body(surprise=0.9), "????" if i % 2 else "随便", now=float(i), dom=dom))
    cap = MentalizeCapability(sync_floor=0.9)   # 高地板，强制触发
    ctx = BeatContext(session_key="u", event=None, body=_body(), phase=Phase.DELIBERATE,
                      domains={"usermodel": dom})
    out = cap.deliberate(ctx)
    assert out is not None and out.payload.get("want") == "clarify_you"


@pytest.mark.asyncio
async def test_full_turn_phase_b_c_wired() -> None:
    """整轮：Mentalize+Appraisal(PERCEPT) → Recall+Expression+Ignition(DELIBERATE) →
    UserModel.ingest(EVOLVE)，对真实 host 端到端跑通、无异常。"""
    h = SylanneAlphaHost(root=tempfile.mkdtemp(prefix="sylpc_"), session_key="u1")
    bp = CanonicalKernelBodyPort.from_host(h, "u1")
    sc = SelfCore(bp)
    sc.register(MentalizeCapability())
    sc.register(AppraisalCapability())
    sc.register(RecallCapability())
    sc.register(ExpressionCapability())
    sc.register(IgnitionArbiter())
    runner = TurnRunner(sc)

    domains = {"emotion": EmotionLedger(), "usermodel": UserModelDomain()}
    reply, ctx = await runner.run_turn("u1", object(), "你好呀，今天想你了❤️",
                                       domains=domains, draft="嗯，我也想你。")
    assert reply is not None
    # Phase C 产物到位
    assert "you_probably" in ctx.scratch          # Mentalize 预测你
    assert "assessment" in ctx.scratch            # Appraisal 评价（待请求 tick 合并入体）
    # UserModel 真的学了（ingest 被驱动）
    assert domains["usermodel"]._last_prediction is not None
