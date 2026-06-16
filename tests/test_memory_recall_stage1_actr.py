"""阶段1 ACT-R 激活核回归测试。

验证 base-level learning 取代 τ/四维线性加权后的核心行为：
- base-level 统一频次+近因：高频旧记忆不被低频新记忆的近因完全碾压。
- importance 只经 activation 先验计入一次（不再双重计入）。
- EMA 累加器递推正确且不爆炸（Δt 下限保护）。
- emotional 走检索阈值调节（情感契合→更易过门控）。
- 命中后 actr_acc 按 base-level 更新。
"""

from __future__ import annotations

import time

from sylanne_alpha.memory_system import MemorySystem, RecallMode


def _sys() -> MemorySystem:
    return MemorySystem(recall_mode=RecallMode.ACTIVATION)


# ---------------------------------------------------------------------------
# EMA 累加器
# ---------------------------------------------------------------------------

def test_actr_acc_does_not_explode_on_immediate_recall():
    """刚创建立即召回时 Δt→0，actr_acc 不应因 t⁻ᵈ 爆炸（下限保护）。"""
    m = _sys()
    it = m.write_summary("刚写的记忆", temperature=0.0)
    m.recall("记忆")
    assert it.actr_acc < 10.0, f"actr_acc 异常膨胀: {it.actr_acc}"


def test_actr_acc_accumulates_with_repeated_recall():
    """反复召回 actr_acc 应单调累积（频次信号）。"""
    m = _sys()
    it = m.write_summary("常聊的话题", temperature=0.0)
    vals = []
    for _ in range(5):
        m.recall("话题")
        vals.append(it.actr_acc)
    assert vals == sorted(vals), "actr_acc 应随召回单调不减"
    assert vals[-1] > vals[0]


def test_update_actr_acc_uses_old_timestamp():
    """_update_actr_acc 必须在 last_recalled_ts 刷新前用旧 ts 算 Δt。"""
    m = _sys()
    now = time.time()
    it = m.write_summary("x", temperature=0.0)
    it.created_at = now - 3600 * 10  # 10h 前
    it.last_recalled_ts = 0.0
    before = it.actr_acc
    m._update_actr_acc(it, now)
    # 10h 前、d=0.5：acc = 1*(10)^-0.5 + 1 ≈ 1.316
    assert it.actr_acc > before  # 叠加了 +1
    assert it.actr_acc < before + 1.0 + 1e-6  # 衰减后小于 +1 满额


# ---------------------------------------------------------------------------
# base-level：频次 vs 近因
# ---------------------------------------------------------------------------

def test_frequency_competes_with_recency():
    """高频旧记忆的激活应能与低频新记忆相抗衡（ACT-R 核心价值）。"""
    m = _sys()
    now = time.time()
    a_old, _ = m._activation_score(
        actr_acc=10.0, last_recalled_ts=now - 3600 * 24 * 21,
        created_at=now - 3600 * 24 * 30, importance=0.5,
        temperature=0.0, current_warmth=0.0, now=now,
    )
    a_new, _ = m._activation_score(
        actr_acc=1.0, last_recalled_ts=now - 3600 * 24,
        created_at=now - 3600 * 24 * 2, importance=0.5,
        temperature=0.0, current_warmth=0.0, now=now,
    )
    # 高频旧不应被低频新碾压（旧 τ 模型里末次召回久远会让它远低于新近记忆）
    assert a_old >= a_new


def test_recency_still_matters_for_equal_frequency():
    """频次相同时，更近的记忆激活更高。"""
    m = _sys()
    now = time.time()
    a_recent, _ = m._activation_score(
        1.0, now - 3600, now - 3600 * 2, 0.5, 0.0, 0.0, now,
    )
    a_old, _ = m._activation_score(
        1.0, now - 3600 * 24 * 10, now - 3600 * 24 * 11, 0.5, 0.0, 0.0, now,
    )
    assert a_recent > a_old


# ---------------------------------------------------------------------------
# importance 单一计入
# ---------------------------------------------------------------------------

def test_importance_raises_activation():
    """importance 作先验偏置抬高激活（唯一计入点）。"""
    m = _sys()
    now = time.time()
    a_low, _ = m._activation_score(1.0, now - 3600, now - 3600, 0.1, 0.0, 0.0, now)
    a_high, _ = m._activation_score(1.0, now - 3600, now - 3600, 0.9, 0.0, 0.0, now)
    assert a_high > a_low


def test_no_independent_wimp_in_activation_mode():
    """ACTIVATION 模式不应再用 _composite 的四维 w_imp（importance 已并入 activation）。

    回归保护：确认激活路径打分不调用 _composite（否则就是双重计入）。
    """
    m = _sys()
    called = {"composite": False}
    orig = m._composite

    def spy(*a, **k):
        called["composite"] = True
        return orig(*a, **k)

    m._composite = spy  # type: ignore
    m.write_summary("测试记忆", temperature=0.3)
    m.recall("测试")
    assert not called["composite"], "ACTIVATION 路径不应调用四维 _composite"


# ---------------------------------------------------------------------------
# emotional → 检索阈值
# ---------------------------------------------------------------------------

def test_emotional_congruence_lowers_threshold():
    """情绪契合的记忆更易过检索阈值（mood-congruent 特权）。"""
    m = _sys()
    now = time.time()
    # 一条激活很低的记忆（久远、低频、低重要）
    args = dict(actr_acc=1.0, last_recalled_ts=now - 3600 * 24 * 40,
                created_at=now - 3600 * 24 * 41, importance=0.2, now=now)
    # 情绪契合（都正向）vs 情绪冲突
    _, pass_congruent = m._activation_score(temperature=0.8, current_warmth=0.8, **args)
    _, pass_conflict = m._activation_score(temperature=0.8, current_warmth=-0.8, **args)
    # 契合时阈值更低，更可能通过（至少不会更难通过）
    assert pass_congruent or not pass_conflict


# ---------------------------------------------------------------------------
# 端到端
# ---------------------------------------------------------------------------

def test_activation_recall_end_to_end():
    m = _sys()
    m.write_summary("我们昨天聊到旅行计划", source_turns=2, temperature=0.4)
    m.write_summary("你说你喜欢喝拿铁", source_turns=1, temperature=0.5)
    results = m.recall("旅行", limit=5)
    assert results
    assert all(0.0 <= r.activation <= 1.0 for r in results)
    assert results[0].debug.get("act") is not None
