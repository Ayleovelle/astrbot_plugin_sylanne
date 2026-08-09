"""Phase G 测试（Fable 重做版）：L3 学生编码器（DistillationDomain）。

核心验收：
- student 从 SDK 真实 body 维（teacher）学，收敛可分 → 真学习非循环自证。
- surprise 加权学习；fidelity 冷启动封顶低。
- 【真实消费者】atypicality：学生预测 vs 真实体感的失配 ×fidelity，
  喂 AppraisalCapability 的 novelty——旧版"跳 LLM 门控"无消费者，已删。
- to_dict/load_dict 容缺向后兼容（特征维序与旧档一致）。
- 单次 update 远 <500ms。
"""

from __future__ import annotations

import time
from types import SimpleNamespace

from sylanne_alpha.v2core.capabilities.mentalize import AppraisalCapability
from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase
from sylanne_alpha.v2core.domains.distillation import DistillationDomain
from sylanne_alpha.v2core.lexicon import read_signals


def _evolve_ctx(text: str, body: SimpleNamespace) -> SimpleNamespace:
    c = SimpleNamespace()
    c.phase = Phase.EVOLVE
    c.text = text
    c.body = body
    c.scratch = {}
    return c


def _body(warmth=0.0, tension=0.2, repair=0.1, surprise=0.3):
    return SimpleNamespace(warmth=warmth, tension=tension,
                           repair_pressure=repair, surprise=surprise)


def test_student_converges_to_teacher() -> None:
    """student 用浅层特征逼近 teacher 真值（warm↔暖、cold↔冷可分）。"""
    d = DistillationDomain()
    warm, cold = "我好喜欢你呀❤️😊抱抱", "哼 烦 滚"
    for _ in range(60):
        d.ingest(_evolve_ctx(warm, _body(warmth=0.8)))
        d.ingest(_evolve_ctx(cold, _body(warmth=-0.6)))
    pw = d.predict(warm).predicted["warmth"]
    pc = d.predict(cold).predicted["warmth"]
    assert pw > 0.5, pw
    assert pc < -0.2, pc
    assert pw - pc > 0.6


def test_teacher_is_body_not_heuristic() -> None:
    """同一文本不同 body teacher → 预测分道扬镳（学的是 body 不是文本自洽）。"""
    d1, d2 = DistillationDomain(), DistillationDomain()
    txt = "随便一句话"
    for _ in range(50):
        d1.ingest(_evolve_ctx(txt, _body(warmth=0.9)))
        d2.ingest(_evolve_ctx(txt, _body(warmth=-0.9)))
    assert d1.predict(txt).predicted["warmth"] > 0.3
    assert d2.predict(txt).predicted["warmth"] < -0.3


def test_fidelity_cold_start_low() -> None:
    d = DistillationDomain()
    assert d.fidelity() == 0.0
    d.ingest(_evolve_ctx("一句", _body(warmth=0.5)))
    assert d.fidelity() < 0.3


def test_surprise_weighted_learning() -> None:
    lo, hi = DistillationDomain(), DistillationDomain()
    txt = "测试文本"
    lo.ingest(_evolve_ctx(txt, _body(warmth=1.0, surprise=0.0)))
    hi.ingest(_evolve_ctx(txt, _body(warmth=1.0, surprise=1.0)))
    assert hi.predict(txt).predicted["warmth"] > lo.predict(txt).predicted["warmth"]


def test_persistence_roundtrip_and_backward_compat() -> None:
    d = DistillationDomain()
    for _ in range(20):
        d.ingest(_evolve_ctx("喜欢❤️", _body(warmth=0.7)))
    snap = d.to_dict()
    d2 = DistillationDomain()
    d2.load_dict(snap)
    assert abs(d2.predict("喜欢❤️").predicted["warmth"]
               - d.predict("喜欢❤️").predicted["warmth"]) < 1e-9
    assert d2._samples == d._samples
    DistillationDomain().load_dict({})
    DistillationDomain().load_dict({"w": "garbage", "samples": "x"})


def test_update_under_budget() -> None:
    d = DistillationDomain()
    t0 = time.perf_counter()
    for _ in range(100):
        d.ingest(_evolve_ctx("一段有点长的中文文本❤️用于压一下", _body(warmth=0.5)))
    per_update_ms = (time.perf_counter() - t0) * 1000.0 / 100
    assert per_update_ms < 50.0, per_update_ms


def test_atypicality_zero_when_cold_start() -> None:
    """冷启动 fidelity=0 → atypicality 恒 0（没学够不发言）。"""
    d = DistillationDomain()
    body = BodySnapshot(session_key="s", turns=1, warmth=0.9)
    assert d.atypicality("随便", body) == 0.0


def test_atypicality_detects_unusual_touch() -> None:
    """学熟"这类文本→中性体感"后：同文本配反常体感 → atypicality 明显更高。"""
    d = DistillationDomain()
    txt = "在么在么"
    for _ in range(40):
        d.ingest(_evolve_ctx(txt, _body(warmth=0.0, tension=0.2, repair=0.1, surprise=0.2)))
    usual = BodySnapshot(session_key="s", turns=1, warmth=0.0, tension=0.2,
                         repair_pressure=0.1, surprise=0.2)
    unusual = BodySnapshot(session_key="s", turns=1, warmth=0.9, tension=0.9,
                           repair_pressure=0.8, surprise=0.9)
    assert d.atypicality(txt, unusual) > d.atypicality(txt, usual) + 0.05


def test_atypicality_feeds_appraisal_arousal() -> None:
    """真实消费链：atypicality 高 → AppraisalCapability 的 arousal 更高（活信号）。"""
    d = DistillationDomain()
    txt = "在么在么"
    for _ in range(40):
        d.ingest(_evolve_ctx(txt, _body(warmth=0.0, tension=0.2, repair=0.1, surprise=0.2)))
    cap = AppraisalCapability()

    def _pctx(body: BodySnapshot, domains: dict) -> BeatContext:
        c = BeatContext(session_key="s", event=None, body=body, text=txt, domains=domains)
        c.phase = Phase.PERCEPT
        c.scratch["signals"] = read_signals(txt)
        return c

    unusual_body = BodySnapshot(session_key="s", turns=1, warmth=0.9, tension=0.9,
                                repair_pressure=0.8, surprise=0.2)
    with_distill = _pctx(unusual_body, {"distill": d})
    cap.perceive(with_distill)
    without = _pctx(unusual_body, {})
    cap.perceive(without)
    assert (with_distill.scratch["assessment"]["arousal"]
            > without.scratch["assessment"]["arousal"]), "atypicality 没有真的喂进评价"
