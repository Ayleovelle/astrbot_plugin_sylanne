"""Phase 2 核心：LifeConsolidation 夜间巩固测试。

验证（真·零 LLM，直调真引擎）：
- 当天 LifeEvent → 次日 LifePlan（event_type 聚合成锚点）
- 关系摘要聚合（valence/arousal 均值，事件数）
- 间隔守卫（needs_consolidation 防 RETIRED 期反复巩固）
- 只取当天事件（跨日事件不计入）
- 持久化快照结构（_write_state 写独立 KV key）
- 不碰投递成败：plan/summary 不读 consumed_at/dropped_at（与 M8 解耦防回归）
"""

from __future__ import annotations

import time
import types

from sylanne_alpha.life_consolidation import LifeConsolidationEngine, _event_type_to_kind
from sylanne_alpha.life_simulation import (
    LifeEvent,
    LifeSimulationState,
    LifeWorldState,
)


def _event(event_type, importance=0.5, ts=None, valence=0.0, arousal=0.0, text="活动"):
    return LifeEvent(
        text=text,
        mood="平静",
        urgency=0.3,
        timestamp=ts if ts is not None else time.time(),
        event_type=event_type,
        importance=importance,
        valence_delta=valence,
        arousal_delta=arousal,
    )


def _make_sim(events):
    state = LifeSimulationState(
        events=list(events),
        current_activity="",
        last_simulation_time=0.0,
        last_outreach_time=0.0,
        simulation_count=0,
        outreach_count=0,
        enabled=True,
        world=LifeWorldState(),
        plan=None,
    )
    sim = types.SimpleNamespace(state=state)
    return sim


def _make_plugin(events):
    p = types.SimpleNamespace()
    p._life_simulator = _make_sim(events)
    p._kv_writes = []

    async def _put_kv_data(key, value):
        p._kv_writes.append((key, value))

    p.put_kv_data = _put_kv_data
    p._has_kv_api = lambda: True
    p._safe_session_key = lambda sk: sk.replace("!", "_")
    return p


def test_today_events_to_plan():
    """当天事件按 event_type 聚合成次日锚点。"""
    now = time.time()
    p = _make_plugin([
        _event("study", importance=0.9, ts=now),
        _event("study", importance=0.8, ts=now),
        _event("game", importance=0.4, ts=now),
    ])
    eng = LifeConsolidationEngine(p)
    snap = eng.consolidate_sync("s1", now)
    assert snap is not None
    plan = p._life_simulator.state.plan
    assert plan is not None
    kinds = [a.kind for a in plan.anchors]
    # study 权重最高（0.9+0.8），排在 game 前
    assert "study" in kinds
    assert kinds[0] == "study"
    assert plan.generated_from == ["consolidation"]


def test_relationship_summary():
    """关系摘要聚合 valence/arousal 均值 + 事件数。"""
    now = time.time()
    p = _make_plugin([
        _event("study", ts=now, valence=0.2, arousal=0.1),
        _event("rest", ts=now, valence=0.4, arousal=-0.1),
    ])
    eng = LifeConsolidationEngine(p)
    snap = eng.consolidate_sync("s1", now)
    summary = snap["relationship_summary"]
    assert summary["event_count"] == 2
    assert abs(summary["valence_avg"] - 0.3) < 1e-6
    assert abs(summary["arousal_avg"] - 0.0) < 1e-6


def test_interval_guard():
    """needs_consolidation 间隔守卫：刚巩固过则拒。"""
    now = time.time()
    p = _make_plugin([_event("study", ts=now)])
    eng = LifeConsolidationEngine(p)
    assert eng.needs_consolidation("s1", now) is True
    eng.consolidate_sync("s1", now)
    # 刚巩固 → 间隔内拒
    assert eng.needs_consolidation("s1", now + 10) is False
    # 超间隔 → 放行
    assert eng.needs_consolidation("s1", now + 1801) is True


def test_only_today_events():
    """跨日（昨天）事件不计入当天巩固。"""
    now = time.time()
    yesterday = now - 86400 * 1.5  # 1.5 天前，必在今天 00:00 之前
    p = _make_plugin([
        _event("study", ts=now),
        _event("game", ts=yesterday),  # 昨天的，应被排除
    ])
    eng = LifeConsolidationEngine(p)
    snap = eng.consolidate_sync("s1", now)
    assert snap["relationship_summary"]["event_count"] == 1  # 只数当天 1 条


def test_no_events_returns_none():
    """无当天事件 → 返回 None（无可巩固）。"""
    now = time.time()
    p = _make_plugin([])
    eng = LifeConsolidationEngine(p)
    assert eng.consolidate_sync("s1", now) is None


def test_persist_writes_independent_kv_key():
    """_write_state 写独立 KV key sylanne_life_consolidation_*（不污染 life_sim_state）。"""
    import asyncio
    now = time.time()
    p = _make_plugin([_event("study", ts=now)])
    eng = LifeConsolidationEngine(p)
    snap = eng.consolidate_sync("s1", now)

    async def _drive():
        await eng._write_state("s1", snap)

    asyncio.run(_drive())
    assert len(p._kv_writes) == 1
    key, val = p._kv_writes[0]
    assert key == "sylanne_life_consolidation_s1"
    assert key != "sylanne_life_sim_state"  # 独立 namespace
    assert "plan" in val and "relationship_summary" in val


def test_plan_does_not_read_dispatch_outcome():
    """解耦防回归：巩固不读 consumed_at/dropped_at（那是 M8 维度）。

    构造两个 event：一个 consumed_at>0、一个 dropped_at>0，但 event_type 相同。
    巩固结果只按 event_type/importance 聚合，对投递成败无感——两者等同对待。
    """
    now = time.time()
    e1 = _event("study", importance=0.5, ts=now)
    e1.consumed_at = now  # 投递成功
    e2 = _event("study", importance=0.5, ts=now)
    e2.dropped_at = now   # 投递失败
    p = _make_plugin([e1, e2])
    eng = LifeConsolidationEngine(p)
    snap = eng.consolidate_sync("s1", now)
    # 两条都计入（投递成败不影响巩固），event_count=2
    assert snap["relationship_summary"]["event_count"] == 2


def test_event_type_to_kind_mapping():
    """event_type → LifeActivity.kind 映射。"""
    assert _event_type_to_kind("research") == "study"
    assert _event_type_to_kind("creative") == "create"
    assert _event_type_to_kind("game") == "game"
    assert _event_type_to_kind("social") == "social"
    assert _event_type_to_kind("unknown_xyz") == "rest"  # 兜底
