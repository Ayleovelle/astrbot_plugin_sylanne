"""canonical 质量漂移链路端到端测试（迁移 2026-06-14，核查任务 wdjxyayf1）。

覆盖 feedback_quality 后门退役后的新链路：
  本轮 SPEAK 自评(float) → rt["pending_quality"] → consume_pending_quality 取出即清
  → 下轮 request tick event.values["dialogue_quality"] → process → _drift_embodiment 漂移。

p1_9 只验到 pending_quality 被设；本文件补"取出即清 + 一次性语义 + 注入形状"的契约缺口。
"""

from __future__ import annotations

from types import SimpleNamespace

from sylanne_alpha.v2core.integration import consume_pending_quality


def _plugin_with_rt(pending_quality) -> SimpleNamespace:  # noqa: ANN001
    p = SimpleNamespace()
    p._config = {"sylanne_enable_v2core": True}
    p._v2core_runtimes = {
        "s": {"pending_quality": pending_quality},
    }
    return p


def test_consume_returns_float_and_clears() -> None:
    """取出质量分后即清（一次性语义，防同一分被多轮重复注入）。"""
    p = _plugin_with_rt(0.92)
    got = consume_pending_quality(p, "s")
    assert got == 0.92
    # 取出即清
    assert p._v2core_runtimes["s"]["pending_quality"] is None
    # 再取为 None（不重复）
    assert consume_pending_quality(p, "s") is None


def test_consume_none_when_unset() -> None:
    """无暂存 → None（不注入 dialogue_quality，process 走默认无漂移）。"""
    p = _plugin_with_rt(None)
    assert consume_pending_quality(p, "s") is None


def test_consume_fresh_dict_returns_score() -> None:
    """生产格式 {"score","ts"}：新鲜分（ts 近）→ 返回 score。"""
    import time
    p = _plugin_with_rt({"score": 0.88, "ts": time.time()})
    assert consume_pending_quality(p, "s") == 0.88
    assert p._v2core_runtimes["s"]["pending_quality"] is None  # 取出即清


def test_consume_stale_dict_dropped() -> None:
    """陈旧分（ts 超 TTL，如长间隔 gap/新话题）→ 丢弃返 None，防错漂移不相关话题。"""
    import time
    from sylanne_alpha.v2core.integration import _QUALITY_TTL_S
    p = _plugin_with_rt({"score": 0.95, "ts": time.time() - _QUALITY_TTL_S - 60})
    assert consume_pending_quality(p, "s") is None
    assert p._v2core_runtimes["s"]["pending_quality"] is None  # 仍取出即清


def test_consume_disabled_returns_none() -> None:
    """v2core 关 → None（绞杀式回退，不碰新通道）。"""
    p = _plugin_with_rt(0.9)
    p._config = {"sylanne_enable_v2core": False}
    assert consume_pending_quality(p, "s") is None


def test_consume_bad_value_safe() -> None:
    """坏值（非数字）→ None，不掀翻请求（防御式）。"""
    p = _plugin_with_rt("not_a_number")
    assert consume_pending_quality(p, "s") is None


def test_consume_no_runtime_safe() -> None:
    """会话无 runtime → None（容错）。"""
    p = SimpleNamespace()
    p._config = {"sylanne_enable_v2core": True}
    p._v2core_runtimes = {}
    assert consume_pending_quality(p, "missing") is None


def test_injected_value_drives_drift_end_to_end() -> None:
    """端到端：模拟下轮 request tick 拿到注入的 dialogue_quality → 真漂移。

    复刻 llm_request_pipeline 注入逻辑：consume → event.values["dialogue_quality"]
    → body_port.tick → process → _drift_embodiment。验证链路真通（非仅契约）。
    """
    import tempfile
    from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost
    from sylanne_alpha.v2core.body_port_v2 import CanonicalKernelBodyPort

    h = SylanneAlphaHost(root=tempfile.mkdtemp(prefix="qd_"), session_key="s")
    bp = CanonicalKernelBodyPort.from_host(h, "s")
    bp.tick({"phase": "request", "text": "hi", "now": 1.0})
    comp = h.kernel.computation
    # 断 relational_gravity:只有 dialogue_quality_high 碰它(+0.15)，expression_fired 不碰，
    # 干净隔离"是注入的 dialogue_quality 在驱动"（红队 wjqkfgh4i major 修复）。
    before = float(comp._embodiment_traits["relational_gravity"].value)

    # 模拟 4 轮：每轮上一轮自评的 float 经 consume 注入本轮 request tick values
    p = _plugin_with_rt(None)
    for i in range(1, 5):
        p._v2core_runtimes["s"]["pending_quality"] = 0.95   # 上轮自评高质量
        _dq = consume_pending_quality(p, "s")
        event_values = {}
        if _dq is not None:
            event_values = {**event_values, "dialogue_quality": _dq}
        bp.tick({"phase": "request", "text": "好呀", "now": 1.0 + 30.0 * i,
                 "values": event_values})
    after = float(comp._embodiment_traits["relational_gravity"].value)
    assert after > before, "注入的 dialogue_quality 没经 canonical 链路推 relational_gravity"
