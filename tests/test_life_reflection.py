"""Phase 2 核心：LifeReflection 生活反思测试。

验证（直调真引擎，fake LLM caller）：
- 当天生活 → 产 next_plan_hint（arc + kind_bias），写 world.next_plan_hint
- 单写者：反思不写 state.plan（只写 hint）
- kind_bias 有界 clamp（±0.10，防自证循环放大）
- 不读 consumed_at/dropped_at（与 M8 解耦防回归）
- 预算闸（日预算耗尽 / 间隔内不重复反思）
- 事件太少不反思（不烧 LLM）
- 闭环：hint.kind_bias 影响 LifeConsolidation 次日计划权重
"""

from __future__ import annotations

import asyncio
import json
import time
import types

from sylanne_alpha.life_reflection import LifeReflectionEngine
from sylanne_alpha.life_consolidation import LifeConsolidationEngine
from sylanne_alpha.life_simulation import (
    LifeEvent,
    LifeSimulationState,
    LifeWorldState,
)


def _event(event_type, importance=0.5, ts=None):
    return LifeEvent(
        text="活动内容",
        mood="平静",
        urgency=0.3,
        timestamp=ts if ts is not None else time.time(),
        event_type=event_type,
        importance=importance,
    )


def _make_sim(events, plan=None):
    state = LifeSimulationState(
        events=list(events),
        current_activity="",
        last_simulation_time=0.0,
        last_outreach_time=0.0,
        simulation_count=0,
        outreach_count=0,
        enabled=True,
        world=LifeWorldState(),
        plan=plan,
    )
    return types.SimpleNamespace(state=state)


class _FakeStore:
    def __init__(self):
        self.last_user_message_time = {}


def _make_plugin(events, llm_reply, plan=None):
    p = types.SimpleNamespace()
    p._life_simulator = _make_sim(events, plan)
    p._store = _FakeStore()
    p.config = {"sylanne_alpha_life_reflection_daily_budget": 1}
    p._locks = {}

    def _session_lock(sk):
        import asyncio as _a
        if sk not in p._locks:
            p._locks[sk] = _a.Lock()
        return p._locks[sk]

    p._session_lock = _session_lock

    async def _summarizer_llm_call(prompt):
        return llm_reply

    p._summarizer_llm_call = _summarizer_llm_call
    return p


def _run(coro):
    return asyncio.run(coro)


def test_reflection_produces_hint():
    """当天生活足够 → 产 hint 写入 world.next_plan_hint。"""
    now = time.time()
    reply = json.dumps({"arc": "她今天创作很多", "kind_bias": {"create": 0.08}})
    p = _make_plugin([_event("create", ts=now), _event("create", ts=now), _event("study", ts=now)], reply)
    eng = LifeReflectionEngine(p)
    ok = _run(eng.maybe_reflect("s1", now))
    assert ok is True
    hint = p._life_simulator.state.world.next_plan_hint
    assert hint["arc"] == "她今天创作很多"
    assert hint["kind_bias"]["create"] == 0.08


def test_reflection_does_not_write_state_plan():
    """单写者：反思只写 hint，绝不碰 state.plan。"""
    now = time.time()
    reply = json.dumps({"arc": "t", "kind_bias": {"study": 0.05}})
    p = _make_plugin([_event("study", ts=now)] * 3, reply)
    eng = LifeReflectionEngine(p)
    _run(eng.maybe_reflect("s1", now))
    assert p._life_simulator.state.plan is None  # 反思没碰 plan


def test_kind_bias_clamped():
    """kind_bias 超界值被 clamp 到 ±0.10（防自证循环放大）。"""
    now = time.time()
    reply = json.dumps({"arc": "t", "kind_bias": {"create": 0.9, "study": -0.5}})
    p = _make_plugin([_event("create", ts=now)] * 3, reply)
    eng = LifeReflectionEngine(p)
    _run(eng.maybe_reflect("s1", now))
    kb = p._life_simulator.state.world.next_plan_hint["kind_bias"]
    assert kb["create"] == 0.10   # 0.9 → clamp 0.10
    assert kb["study"] == -0.10   # -0.5 → clamp -0.10


def test_budget_gate():
    """日预算耗尽后不再反思。"""
    now = time.time()
    reply = json.dumps({"arc": "t", "kind_bias": {"study": 0.05}})
    p = _make_plugin([_event("study", ts=now)] * 3, reply)
    eng = LifeReflectionEngine(p)
    assert _run(eng.maybe_reflect("s1", now)) is True
    # 同日 + 间隔外，但预算=1 已耗尽 → 拒
    assert _run(eng.maybe_reflect("s1", now + 2000)) is False


def test_interval_gate():
    """间隔内不重复反思。"""
    now = time.time()
    reply = json.dumps({"arc": "t", "kind_bias": {"study": 0.05}})
    p = _make_plugin([_event("study", ts=now)] * 3, reply)
    p.config["sylanne_alpha_life_reflection_daily_budget"] = 5  # 预算够，单看间隔
    eng = LifeReflectionEngine(p)
    assert _run(eng.maybe_reflect("s1", now)) is True
    assert _run(eng.maybe_reflect("s1", now + 10)) is False  # 间隔内拒


def test_too_few_events_no_reflect():
    """当天事件 < 3 → 不反思（不烧 LLM、不占预算）。"""
    now = time.time()
    reply = json.dumps({"arc": "t", "kind_bias": {"study": 0.05}})
    p = _make_plugin([_event("study", ts=now)], reply)  # 只 1 条
    eng = LifeReflectionEngine(p)
    assert _run(eng.maybe_reflect("s1", now)) is False
    # 预算未被消耗（事件太少在扣预算前就返回）
    assert eng._has_budget("s1", now) is True


def test_reflection_ignores_dispatch_outcome():
    """解耦防回归：反思不读 consumed_at/dropped_at（M8 维度）。

    构造带 consumed_at/dropped_at 的事件，反思的 summary 只看 event_type/完成率，
    投递成败对反思输出无影响——两条同 event_type 等同对待。
    """
    now = time.time()
    e1 = _event("study", ts=now); e1.consumed_at = now
    e2 = _event("study", ts=now); e2.dropped_at = now
    e3 = _event("study", ts=now)
    reply = json.dumps({"arc": "学习日", "kind_bias": {"study": 0.05}})
    p = _make_plugin([e1, e2, e3], reply)
    eng = LifeReflectionEngine(p)
    # summary 构造不抛、正常产 hint（不依赖投递字段）
    ok = _run(eng.maybe_reflect("s1", now))
    assert ok is True


def test_hint_influences_consolidation():
    """闭环：反思产的 kind_bias 影响巩固的次日计划权重。

    两个 event_type 重要性接近，hint 给 create 正 bias → create 在锚点中排序提升。
    """
    now = time.time()
    # study 和 create 各一条，importance 相同
    events = [_event("study", importance=0.5, ts=now), _event("create", importance=0.5, ts=now)]
    sim_plugin = _make_plugin(events, None)
    # 先设 hint（模拟反思已产出）
    sim_plugin._life_simulator.state.world.next_plan_hint = {
        "arc": "多创作", "kind_bias": {"create": 0.10}
    }
    cons = LifeConsolidationEngine(sim_plugin)
    snap = cons.consolidate_sync("s1", now)
    assert snap is not None
    anchors = sim_plugin._life_simulator.state.plan.anchors
    kinds = [a.kind for a in anchors]
    # create 因 hint 加权，排在 study 前
    assert kinds[0] == "create"
