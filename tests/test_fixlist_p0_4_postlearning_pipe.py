"""Phase G fixlist P0-4 测试：后学习喂对管道（canonical 迁移版 2026-06-14）。

迁移（核查任务 wdjxyayf1）：vendored 整树同步到 canonical main 后 `feedback_quality`
后门退役。L1 embodiment 漂移现在只发生在 process 内部（kernel.tick 末尾 _drift_embodiment）：
  - dialogue_quality：agent 经 event.values["dialogue_quality"] 数值注入 → 自动漂移（真闭环）
  - expression_fired：process 自派生 result["should_express"]（每轮 request 拍自动）
  - sustained_silence：canonical 通道不可达（route 恒 resonance），记 SDK backlog（缺口1）
本测试验证 dialogue_quality 数值通道真驱动 expression_drive_trait 漂移（走真实 host）。
注意 30s 限频（_drift_min_interval）：tick 间 now 须步进 ≥30s 才过闸触发漂移。
"""

from __future__ import annotations

import tempfile

from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost
from sylanne_alpha.v2core.body_port_v2 import CanonicalKernelBodyPort


def _bp() -> CanonicalKernelBodyPort:
    h = SylanneAlphaHost(root=tempfile.mkdtemp(prefix="p04t_"), session_key="s")
    bp = CanonicalKernelBodyPort.from_host(h, "s")
    bp.tick({"phase": "request", "text": "hi", "now": 1.0})
    return bp


def _expr_trait(bp: CanonicalKernelBodyPort) -> float:
    tm = bp._host.kernel.computation._embodiment_traits["expression_drive_trait"]
    return float(tm.value)


def _rel_gravity(bp: CanonicalKernelBodyPort) -> float:
    # relational_gravity 只被 dialogue_quality_high 推（+0.15），expression_fired 完全不碰它。
    # 断言它 → 干净隔离"是 dialogue_quality 信道在驱动"，排除 expression_fired 混淆（红队 major）。
    tm = bp._host.kernel.computation._embodiment_traits["relational_gravity"]
    return float(tm.value)


def test_drift_signal_reaches_embodiment() -> None:
    """L1 活着：高质量 dialogue_quality 经 event.values 注入 → relational_gravity 真漂移（+方向）。

    断 relational_gravity 而非 expression_drive_trait：后者 expression_fired 也推（+0.3），
    无法隔离信道；relational_gravity 只有 dialogue_quality_high 碰（+0.15），是 dialogue_quality
    信道的干净证据（红队 wjqkfgh4i major 修复）。
    """
    bp = _bp()
    before = _rel_gravity(bp)
    # 高质量分(>=0.7 → dialogue_quality_high, relational_gravity+0.15)；now 步进 30s 过限频闸
    for i in range(1, 21):
        bp.tick({"phase": "request", "text": "好呀", "now": 1.0 + 30.0 * i,
                 "values": {"dialogue_quality": 0.95}})
    after = _rel_gravity(bp)
    assert after > before, "高质量 dialogue_quality 没经 canonical 通道推 relational_gravity——信道断了"


def test_sustained_silence_drifts_down() -> None:
    """sustained_silence 经 canonical 通道【不可达】(route 恒 resonance)——记 SDK backlog 缺口1。

    本测试是负向文档：确认纯静默轮（空文本，无 dialogue_quality 注入）不会经 canonical
    漂移 expression_drive_trait。"沉默→表达欲缓抑"需远端 SDK 让装死轮 route=skip，本仓不 hack。
    替代的"质量低→下行"由 test_low_quality_drifts_down 覆盖（dialogue_quality_low，非等价语义）。
    """
    bp = _bp()
    before = _expr_trait(bp)
    for i in range(1, 21):
        bp.tick({"phase": "response", "text": "", "now": 1.0 + 30.0 * i,
                 "flags": ["response", "silent"]})
    after = _expr_trait(bp)
    assert after == before, "纯静默经 canonical 不该漂移（sustained_silence 不可达，见 SDK backlog）"


def test_low_quality_drifts_down() -> None:
    """低质量 dialogue_quality（<=0.3 → dialogue_quality_low, expr-0.15）的净贡献为负向。

    这不是 sustained_silence 的等价物（语义是"回复质量低"非"沉默"）。
    隔离测法（红队 R3）：expression_fired 会对非空文本自动派生 +0.3，与注入的 dialogue_quality
    同轮叠加；反向时（低质量）会被盖过。故用【对比】隔离 dialogue_quality 的净贡献——
    同文本/时序下喂高质量 vs 低质量，高质量结局应高于低质量，差值即 dialogue_quality 信道的方向。
    """
    def _run(dq: float) -> float:
        bp = _bp()
        for i in range(1, 21):
            bp.tick({"phase": "request", "text": "嗯", "now": 1.0 + 30.0 * i,
                     "values": {"dialogue_quality": dq}})
        return _expr_trait(bp)

    high = _run(0.95)
    low = _run(0.05)
    assert low < high, "低质量信道净贡献应低于高质量（dialogue_quality_low -0.15 vs high +0.25）"


def test_feedback_bus_no_unknown_outcome() -> None:
    """桥路径全程不再以未知 outcome 调 feedback()（只走 feedback_quality）。"""
    from unittest.mock import patch

    bp = _bp()
    comp = bp._host.kernel.computation
    seen_outcomes: list[str] = []
    orig_fb = type(comp).feedback

    def _spy_fb(self, outcome, *a, **k):  # noqa: ANN001, ANN002, ANN003
        seen_outcomes.append(outcome)
        return orig_fb(self, outcome, *a, **k)

    # 实例属性 read-only（slots）→ 在类上打补丁
    with patch.object(type(comp), "feedback", _spy_fb):
        bp.learn("", actual_expressed=True)
        bp.learn("", actual_expressed=False)
    # learn() 已退役表达结果驱动，是真实反应反馈占位；本期无真实反应判定源 → 不调 feedback()
    assert seen_outcomes == [], f"feedback() 被 learn 调用了: {seen_outcomes}"


def test_quality_signal_also_drifts() -> None:
    """高质量 dialogue_quality 数值经 canonical 通道驱动 relational_gravity 漂移（隔离信道）。"""
    bp = _bp()
    before = _rel_gravity(bp)
    for i in range(1, 16):
        bp.tick({"phase": "request", "text": "今天很开心", "now": 1.0 + 30.0 * i,
                 "values": {"dialogue_quality": 0.92}})
    after = _rel_gravity(bp)
    assert after > before


def test_mid_quality_no_drift() -> None:
    """中区质量(0.3~0.7)注入 → SDK 门控不产信号 → relational_gravity 零漂移。

    锁死"_assess_quality 无条件写 quality_score 是安全的"这个核心假设：中区注入不该乱漂
    （红队 wjqkfgh4i 盲区补测）。relational_gravity 排除 expression_fired 干扰，是干净探针。
    """
    bp = _bp()
    before = _rel_gravity(bp)
    for i in range(1, 16):
        bp.tick({"phase": "request", "text": "嗯哦", "now": 1.0 + 30.0 * i,
                 "values": {"dialogue_quality": 0.5}})   # 中区:既非 high(>=0.7) 也非 low(<=0.3)
    after = _rel_gravity(bp)
    assert after == before, "中区质量不该经 canonical 通道漂移 relational_gravity（无条件写 quality_score 不安全）"
