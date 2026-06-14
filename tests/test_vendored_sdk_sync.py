"""vendored SDK 同步验证：T1 A7 鞍点已合规 + T2/T3 接口在 + canonical 漂移线在位。

附录 C 的运行时落点：插件跑 vendored（已整树同步=远端 main 干净镜像），需确认 T1/T2/T3
同步且 canonical 自我进化漂移线接通（旧的 feedback_quality 后门已退役，改走 process 自动漂移）。
"""

from __future__ import annotations

from sylanne_alpha._engine.sylanne_core.compute.expression_policy import ExpressionPolicy


def test_vendored_t1_neutral_anchoring() -> None:
    """trait≈0.5 → 鞍点回到旧常数 0.95/0.10（部署不带键时逐 tick 行为不变）。"""
    p = ExpressionPolicy()
    p.set_personality(0.5, expression_drive_trait=0.5, sovereignty_guard=0.5)
    assert abs(p._force_express - 0.95) < 1e-9
    assert abs(p._force_hold - 0.10) < 1e-9


def test_vendored_t1_personalized_monotone() -> None:
    """表达欲↑→force_express↓；主权↑→force_hold↑（A7 人格显函数）。"""
    p = ExpressionPolicy()
    p.set_personality(0.5, expression_drive_trait=1.0, sovereignty_guard=1.0)
    assert abs(p._force_express - 0.85) < 1e-9   # 1.05 - 0.20
    assert abs(p._force_hold - 0.18) < 1e-9      # 0.02 + 0.16


def test_vendored_t2_t3_signature() -> None:
    """update_from_feedback 接 actual_action + skip_forced（T2/T3）。"""
    import inspect
    sig = inspect.signature(ExpressionPolicy.update_from_feedback)
    assert "actual_action" in sig.parameters
    assert "skip_forced" in sig.parameters


def test_vendored_canonical_drift_wired() -> None:
    """canonical 自我进化漂移线在位（替代已退役的 feedback_quality 后门，迁移 2026-06-14）。

    确认：ResonanceSpine 有 _drift_embodiment（process 自动调）+ 旧后门 feedback_quality 已不存在
    + process 接 dialogue_quality 数值通道。这是"对话质量→人格漂移"的 canonical 正道。
    """
    import inspect
    from sylanne_alpha._engine.sylanne_core.compute import resonance_integration as ri

    spine = ri.ResonanceSpine
    assert hasattr(spine, "_drift_embodiment"), "canonical 漂移线 _drift_embodiment 缺失"
    assert not hasattr(spine, "feedback_quality"), "旧后门 feedback_quality 不该存在（应已退役）"
    proc_sig = inspect.signature(spine.process)
    assert "dialogue_quality" in proc_sig.parameters, "process 缺 dialogue_quality 数值通道"
    src = inspect.getsource(ri)
    assert "compute_embodiment_drift" in src, "漂移计算 compute_embodiment_drift 缺失"


def test_vendored_old_default_behavior_unchanged() -> None:
    """旧单参调用 set_personality(openness) 不动鞍点（向后兼容）。"""
    p = ExpressionPolicy()
    before_e, before_h = p._force_express, p._force_hold
    p.set_personality(0.7)   # 只给 openness，不给 trait
    assert p._force_express == before_e
    assert p._force_hold == before_h
