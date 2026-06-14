"""Review 修复实弹测试（F1–F4）：四处死信号/失实声明的接活验证（2026-06-13 全量评审）。

F1 表达风格死通道：scratch["express"] 旧版挂在 DELIBERATE 拍，而 fragment 在宿主
   request 阶段（PERCEPT 后）构建——时序上永远读不到，docstring 却声称"真正影响
   她怎么说话"。修复：ExpressionCapability 增加 PERCEPT 拍 perceive()，
   fragment._style_line 真消费（浓度/节奏/停顿三量措辞化进心象）。
F2 公式双份：fragment 的 guard/soften 与 SomaticBias 同公式在两个文件各手写一份
   （改一处忘另一处的隐患），且 somatic docstring 声称 fragment 是 scratch 的
   "真实消费者"（时序不可能）。修复：somatic.guard_soften_from_body 单一来源。
F3 死读 quality：turn_runner 读 scratch["quality"] 零写者 → dialogue_quality_*
   漂移信号（CP8-P4，DRIFT_SIGNALS 真实在表）在 v2core 退役 v1 后断粮。修复：
   TurnRunner._assess_quality 用 v1 同尺（self_score 三维均值）同阈值（0.7/0.35）补上。
F4 死读 narrative_note：锚点 note 恒空串，自传锚点失去"那一刻是关于什么"的索引。
   修复：Reconsolidation 写首条被召回记忆的文本片段（≤40 字）。
"""

from __future__ import annotations

import tempfile

import pytest

from sylanne_alpha.v2core.capabilities.expression import ExpressionCapability, compose_style
from sylanne_alpha.v2core.capabilities.reconsolidation import ReconsolidationCapability
from sylanne_alpha.v2core.capabilities.somatic import (
    SomaticMarkerCapability,
    guard_soften_from_body,
)
from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase, Reply, ReplyKind
from sylanne_alpha.v2core.domains.memory import MemoryDomain
from sylanne_alpha.v2core.domains.narrative_self import NarrativeSelfDomain
from sylanne_alpha.v2core.fragment import build_mind_fragment
from sylanne_alpha.v2core.renderer import DefaultRenderer
from sylanne_alpha.v2core.self_core import SelfCore
from sylanne_alpha.v2core.turn_runner import TurnRunner


def _body(**kw) -> BodySnapshot:
    return BodySnapshot(session_key="u", turns=1, **kw)


def _ctx(body: BodySnapshot, *, text: str = "在吗", phase: Phase = Phase.PERCEPT,
         scratch: dict | None = None, domains: dict | None = None) -> BeatContext:
    c = BeatContext(session_key="u", event=None, body=body, text=text,
                    phase=phase, domains=domains or {})
    if scratch:
        c.scratch.update(scratch)
    return c


# ===========================================================================
# F1：表达风格在 PERCEPT 拍挂上，fragment 真消费
# ===========================================================================

def test_f1_perceive_hangs_express_in_percept() -> None:
    """PERCEPT 拍 perceive() 挂 scratch["express"]——fragment 唯一吃得到的时机。"""
    ctx = _ctx(_body(warmth=0.5, tension=0.3))
    ExpressionCapability().perceive(ctx)
    ex = ctx.scratch.get("express")
    assert isinstance(ex, dict) and "intensity" in ex
    # request 阶段召回未发生：has_recall 诚实为 False，不假装知道
    assert ex["has_recall"] is False


def test_f1_fragment_style_line_consumes_express() -> None:
    """高强度情绪轮：风格三量（浓度/节奏/停顿）的措辞真出现在心象"表达倾向"行。"""
    body = _body(warmth=0.9, tension=0.8, repair_pressure=0.6)
    ctx = _ctx(body)
    ExpressionCapability().perceive(ctx)   # intensity=2.3 / segment=3.2 / pause=1.4
    frag = build_mind_fragment(ctx, {})
    assert "表达倾向" in frag
    assert "情绪很满" in frag      # intensity > 2.0
    assert "想多说几句" in frag    # segment_bias > 1.5
    assert "说话带停顿" in frag    # pause_bias > 0.8


def test_f1_fragment_degrades_without_express() -> None:
    """express 缺失（ExpressionCapability 未注册的场景）→ 仅躯体行，容错不抛。"""
    body = _body(warmth=0.9, tension=0.8, repair_pressure=0.6)
    frag = build_mind_fragment(_ctx(body), {})
    assert "情绪很满" not in frag   # 风格量缺失就不臆造


def test_f1_compose_style_recall_bonus() -> None:
    """召回加成只在 has_recall=True 时进 segment_bias（+0.2），其余逐项相等。"""
    body = _body(warmth=0.4, tension=0.2)
    plain = compose_style(body)
    with_recall = compose_style(body, has_recall=True)
    assert with_recall["segment_bias"] == pytest.approx(plain["segment_bias"] + 0.2)
    assert with_recall["intensity"] == pytest.approx(plain["intensity"])
    assert with_recall["pause_bias"] == pytest.approx(plain["pause_bias"])


# ===========================================================================
# F2：guard/soften 单一来源公式
# ===========================================================================

def test_f2_somatic_bias_same_source_as_function() -> None:
    """SomaticBias 的 guard/soften 与单源函数逐位相等（公式永不漂移）。"""
    body = _body(sovereignty=0.3, strain=0.5, repair_pressure=0.4, scar=0.6)
    ctx = _ctx(body, phase=Phase.DELIBERATE)
    intent = SomaticMarkerCapability().deliberate(ctx)
    g, s = guard_soften_from_body(body)
    assert intent.payload["somatic"]["guard"] == pytest.approx(g)
    assert intent.payload["somatic"]["soften"] == pytest.approx(s)
    bias = ctx.scratch["somatic_bias"]
    assert bias.guard == pytest.approx(g) and bias.soften == pytest.approx(s)


def test_f2_fragment_guard_wording_from_same_formula() -> None:
    """fragment 的"措辞带防备"分档吃同一公式：低主权高拉伤 → 防备词出现。"""
    body = _body(sovereignty=0.3, strain=0.5)    # guard = 0.7 + 0.15 = 0.85 > 0.45
    frag = build_mind_fragment(_ctx(body), {})
    assert "措辞带防备" in frag


# ===========================================================================
# F3：CP8-P4 质量自评闭环（v2core 接管版）
# ===========================================================================

class _LearnRecorderPort:
    """最小 BodyPort 桩：observe/tick/snapshot + learn 调用记录。"""

    def __init__(self) -> None:
        self.learn_calls: list[dict] = []

    def observe(self) -> BodySnapshot:
        return _body()

    def tick(self, event, assessment=None) -> BodySnapshot:  # noqa: ANN001
        return self.observe()

    def snapshot(self) -> dict:
        return {}

    def learn(self, outcome: str, *, actual_expressed=None, quality_signal=None) -> None:  # noqa: ANN001
        self.learn_calls.append({"outcome": outcome, "actual_expressed": actual_expressed,
                                 "quality_signal": quality_signal})


@pytest.mark.asyncio
async def test_f3_quality_high_reaches_scratch_score() -> None:
    """高质量 SPEAK 轮：self_score 同尺同阈值 → 字符串标签 high + float quality_score≥0.7。

    canonical 迁移 2026-06-14：质量分不再经 learn(quality_signal)，改走 ctx.scratch
    ["quality_score"](float) → integration rt["pending_quality"] → 下轮 event.values。
    """
    bp = _LearnRecorderPort()
    runner = TurnRunner(SelfCore(bp), DefaultRenderer())
    # 长度比合适 + 情感词 ≥3（开心/温暖/幸福）+ 低重复 → 三维均值 ≥ 0.7
    reply, ctx = await runner.run_turn(
        "u", object(), "今天好开心，谢谢你陪我聊天",
        draft="我也很开心呀，能这样陪着你说话，心里觉得很温暖、很幸福。",
        do_response_tick=False,
    )
    assert reply.kind is ReplyKind.SPEAK
    assert ctx.scratch.get("quality") == "dialogue_quality_high"
    assert isinstance(ctx.scratch.get("quality_score"), float)
    assert ctx.scratch["quality_score"] >= 0.7
    # learn 不再承载质量信号（已退役 quality_signal 字符串路径）
    assert bp.learn_calls[-1]["quality_signal"] is None


@pytest.mark.asyncio
async def test_f3_quality_low_reaches_scratch_score() -> None:
    """劣质 SPEAK 轮（超长全重复无情感）→ 字符串标签 low + float quality_score≤0.35。"""
    bp = _LearnRecorderPort()
    runner = TurnRunner(SelfCore(bp), DefaultRenderer())
    reply, ctx = await runner.run_turn(
        "u", object(), "嗯", draft="哦" * 120, do_response_tick=False,
    )
    assert reply.kind is ReplyKind.SPEAK
    assert ctx.scratch.get("quality") == "dialogue_quality_low"
    assert isinstance(ctx.scratch.get("quality_score"), float)
    assert ctx.scratch["quality_score"] <= 0.35


def test_f3_no_quality_for_silent_turn() -> None:
    """SILENT 轮不自评（没说话就没有可评的回复）。"""
    ctx = _ctx(_body(), text="在吗")
    TurnRunner._assess_quality(ctx, Reply.silent("ignition_hold"))
    assert "quality" not in ctx.scratch


def test_f3_preset_quality_not_overwritten() -> None:
    """外部预置 scratch["quality"]（更强判定源/测试）→ 自评不覆盖。"""
    ctx = _ctx(_body(), text="今天好开心，谢谢你陪我聊天")
    ctx.scratch["quality"] = "dialogue_quality_low"
    TurnRunner._assess_quality(
        ctx, Reply.speak("我也很开心呀，能这样陪着你说话，心里觉得很温暖、很幸福。"))
    assert ctx.scratch["quality"] == "dialogue_quality_low"


@pytest.mark.asyncio
async def test_f3_mediocre_quality_stays_unsignaled() -> None:
    """中等质量（0.35–0.7 之间）→ 不发漂移信号（保守阈值防自评噪声）。"""
    bp = _LearnRecorderPort()
    runner = TurnRunner(SelfCore(bp), DefaultRenderer())
    # 长度比合适、低重复，但零情感词：quality ≈ (1+0+~0.9)/3 ≈ 0.63 → 不发信号
    reply, ctx = await runner.run_turn(
        "u", object(), "明天下午三点的会议改到几点了",
        draft="改到后天上午十点了，地点换成二楼大会议室。",
        do_response_tick=False,
    )
    assert reply.kind is ReplyKind.SPEAK
    assert "quality" not in ctx.scratch
    assert bp.learn_calls[-1]["quality_signal"] is None


# ===========================================================================
# F4：锚点注记（高失配时刻"是关于什么的"）
# ===========================================================================

class _FakeMS:
    def to_dict(self):  # noqa: ANN201
        return {}

    def from_dict(self, d):  # noqa: ANN001, ANN201
        pass


def test_f4_narrative_note_written_and_anchored() -> None:
    """重固化高失配轮 → note 写入 scratch（≤40 字）→ 锚点收录该片段。"""
    md = MemoryDomain(_FakeMS())
    nd = NarrativeSelfDomain()
    long_text = "我们说好等春天一起去看樱花的，那天你还拉了勾" * 3   # >40 字，验证截断
    ctx = _ctx(_body(warmth=0.9), phase=Phase.EVOLVE,
               scratch={"recalled": [{"text": long_text, "temperature": 0.0}]},
               domains={"memory": md, "narrative": nd})
    ReconsolidationCapability().evolve(ctx)
    note = ctx.scratch.get("narrative_note")
    assert note and len(note) <= 40 and note == long_text[:40]

    nd.ingest(ctx)   # EVOLVE：登记锚点
    assert nd._anchors and nd._anchors[-1].note == long_text[:40]


def test_f4_no_note_without_recall_text() -> None:
    """召回条目无文本 → 不写 note（不臆造），锚点 note 回落空串。"""
    md = MemoryDomain(_FakeMS())
    ctx = _ctx(_body(warmth=0.9), phase=Phase.EVOLVE,
               scratch={"recalled": [{"text": "", "temperature": 0.0}]},
               domains={"memory": md})
    ReconsolidationCapability().evolve(ctx)
    assert "narrative_note" not in ctx.scratch
