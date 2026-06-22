"""Phase 3 / LifeProject 项目线程测试。

验证：
- LifeProject dataclass to_dict/from_dict roundtrip
- LifeSimulationState v2→v3 迁移：projects=[]，skills=seed，audit={}
- _maybe_promote_projects 确定性聚类晋升（7天≥3天同类）
- _update_project_progress 推进与里程碑触发
- PROJECT_MAX_ACTIVE 上限（不超过 4 个 active）
- 不重复晋升已有 active 同类
"""

from __future__ import annotations

import time
import types

from sylanne_alpha.life_consolidation import LifeConsolidationEngine
from sylanne_alpha.life_simulation import (
    PROJECT_MAX_ACTIVE,
    PROJECT_MILESTONES,
    LifeEvent,
    LifeProject,
    LifeSimulationState,
    LifeWorldState,
    _project_from_dict,
    _project_to_dict,
)


def _event(event_type: str, ts: float, importance: float = 0.5, text: str = "活动") -> LifeEvent:
    return LifeEvent(
        text=text,
        mood="平静",
        urgency=0.3,
        timestamp=ts,
        event_type=event_type,
        importance=importance,
    )


def _make_sim(events: list[LifeEvent], projects: list[LifeProject] | None = None) -> types.SimpleNamespace:
    state = LifeSimulationState(
        events=list(events),
        world=LifeWorldState(),
        projects=list(projects or []),
    )
    return types.SimpleNamespace(state=state)


def _make_plugin(events: list[LifeEvent], projects: list[LifeProject] | None = None):
    p = types.SimpleNamespace()
    p._life_simulator = _make_sim(events, projects)
    p._kv_writes = []

    async def _put_kv_data(key, value):
        p._kv_writes.append((key, value))

    p.put_kv_data = _put_kv_data
    p._has_kv_api = lambda: True
    p._safe_session_key = lambda sk: sk
    return p


# ---------------------------------------------------------------------------
# dataclass / roundtrip
# ---------------------------------------------------------------------------

def test_life_project_roundtrip():
    proj = LifeProject(
        title="毕业设计",
        kind="study",
        progress=0.4,
        milestones=["25"],
        milestones_shared=[],
        event_type="reading",
        last_touched_at=1000.0,
        created_at=500.0,
        share_policy="milestone",
        effectiveness=0.6,
    )
    d = _project_to_dict(proj)
    p2 = _project_from_dict(d)
    assert p2.project_id == proj.project_id
    assert p2.title == "毕业设计"
    assert p2.kind == "study"
    assert p2.progress == 0.4
    assert p2.milestones == ["25"]
    assert p2.event_type == "reading"
    assert p2.share_policy == "milestone"
    assert p2.effectiveness == 0.6


def test_life_project_default_id_assigned():
    proj = LifeProject(title="x")
    assert proj.project_id and len(proj.project_id) == 12


# ---------------------------------------------------------------------------
# v2 → v3 migration
# ---------------------------------------------------------------------------

def test_v2_state_migrates_to_v3_with_empty_projects_and_seed_skills():
    """v2 旧档（无 projects/skills/outreach_audit 字段）→ v3 默认：[]/种子/{}。"""
    v2_data = {
        "schema_version": 2,
        "events": [
            {"text": "读书", "mood": "calm", "urgency": 0.1, "timestamp": 100.0,
             "event_type": "reading", "source": "planned_tick"}
        ],
        "current_activity": "读书",
        "last_simulation_time": 100.0,
        "simulation_count": 5,
        "outreach_count": 1,
    }
    state = LifeSimulationState.from_dict(v2_data)
    assert state.projects == []
    assert len(state.skills) == 3  # seed
    skill_names = {s.name for s in state.skills}
    assert "evening_soft_checkin" in skill_names
    assert "creative_milestone_share" in skill_names
    assert "thesis_companion" in skill_names
    assert state.outreach_audit == {}


def test_v3_state_full_roundtrip_keeps_projects():
    """v3 完整 roundtrip：projects 字段不丢失。"""
    state = LifeSimulationState()
    state.projects = [
        LifeProject(title="论文", kind="study", event_type="reading", progress=0.3)
    ]
    data = state.to_dict()
    s2 = LifeSimulationState.from_dict(data)
    assert len(s2.projects) == 1
    assert s2.projects[0].title == "论文"
    assert s2.projects[0].progress == 0.3


# ---------------------------------------------------------------------------
# Promotion: 7天窗口 ≥3 不同日同类
# ---------------------------------------------------------------------------

def test_promote_project_three_distinct_days():
    """7 天内 3 个不同日的 reading 事件 → 晋升 1 个 LifeProject。"""
    now = time.time()
    one_day = 86400.0
    events = [
        _event("reading", now - 2 * one_day),
        _event("reading", now - 1 * one_day),
        _event("reading", now),  # 今天 → 3 个不同日
    ]
    p = _make_plugin(events)
    eng = LifeConsolidationEngine(p)
    eng.consolidate_sync("s1", now)
    projects = p._life_simulator.state.projects
    assert len(projects) == 1
    assert projects[0].event_type == "reading"
    assert projects[0].state == "active"
    # kind 由 _event_type_to_kind 推断（无显式 reading→study 映射，落 rest 兜底）
    assert projects[0].kind in ("rest", "study")


def test_promote_project_skipped_when_too_few_days():
    """同一天 3 个事件不算 3 不同日 → 不晋升。"""
    now = time.time()
    events = [
        _event("reading", now),
        _event("reading", now + 60),
        _event("reading", now + 120),
    ]
    p = _make_plugin(events)
    eng = LifeConsolidationEngine(p)
    eng.consolidate_sync("s1", now)
    assert len(p._life_simulator.state.projects) == 0


def test_no_duplicate_promotion_when_active_exists():
    """已有 active 项目（同 event_type）不重复晋升。"""
    now = time.time()
    one_day = 86400.0
    existing = LifeProject(title="existing", kind="study", event_type="reading", state="active")
    events = [
        _event("reading", now - 2 * one_day),
        _event("reading", now - 1 * one_day),
        _event("reading", now),
    ]
    p = _make_plugin(events, [existing])
    eng = LifeConsolidationEngine(p)
    eng.consolidate_sync("s1", now)
    projs = p._life_simulator.state.projects
    assert len(projs) == 1  # 没有新增


def test_promote_max_active_cap():
    """已有 PROJECT_MAX_ACTIVE 个 active → 不再晋升。"""
    assert PROJECT_MAX_ACTIVE == 4
    now = time.time()
    one_day = 86400.0
    # 4 个不同 event_type 的 active 项目（占满）
    existing = [
        LifeProject(title=f"p{i}", kind="study", event_type=f"type{i}", state="active")
        for i in range(PROJECT_MAX_ACTIVE)
    ]
    events = [
        _event("reading", now - 2 * one_day),
        _event("reading", now - 1 * one_day),
        _event("reading", now),
    ]
    p = _make_plugin(events, existing)
    eng = LifeConsolidationEngine(p)
    eng.consolidate_sync("s1", now)
    projs = p._life_simulator.state.projects
    # 没新增（依然 4 个），且 reading 不在其中
    assert len(projs) == PROJECT_MAX_ACTIVE
    assert all(p.event_type != "reading" for p in projs)


# ---------------------------------------------------------------------------
# Progress + milestones
# ---------------------------------------------------------------------------

def test_progress_updates_on_matching_events():
    """匹配事件推进 progress 并标记里程碑。"""
    now = time.time()
    proj = LifeProject(
        title="论文", kind="study", event_type="reading", state="active", progress=0.0
    )
    # 高 importance 推进得多：0.05 * (0.5 + 1.0) = 0.075 / 次
    events = [_event("reading", now, importance=1.0) for _ in range(5)]
    p = _make_plugin(events, [proj])
    eng = LifeConsolidationEngine(p)
    eng.consolidate_sync("s1", now)
    # 5 次 0.075 = 0.375 → 命中 0.25 里程碑
    assert proj.progress >= 0.25
    assert "25" in proj.milestones


def test_progress_reaches_one_marks_finished():
    """progress 抵达 1.0 → state=finished。"""
    now = time.time()
    proj = LifeProject(
        title="x", kind="study", event_type="reading", state="active", progress=0.9
    )
    events = [_event("reading", now, importance=1.0) for _ in range(5)]
    p = _make_plugin(events, [proj])
    eng = LifeConsolidationEngine(p)
    eng.consolidate_sync("s1", now)
    assert proj.progress == 1.0
    assert proj.state == "finished"
    # 完成阈值（100）应在 milestones 中
    assert "100" in proj.milestones


def test_progress_no_change_without_match():
    """事件不匹配 event_type → progress 不变。"""
    now = time.time()
    proj = LifeProject(
        title="x", kind="study", event_type="reading", state="active", progress=0.2
    )
    events = [_event("walking", now), _event("cooking", now)]
    p = _make_plugin(events, [proj])
    eng = LifeConsolidationEngine(p)
    eng.consolidate_sync("s1", now)
    assert proj.progress == 0.2


def test_project_milestones_unique_per_threshold():
    """单一阈值不重复写入 milestones。"""
    now = time.time()
    proj = LifeProject(
        title="x", kind="study", event_type="reading", state="active",
        progress=0.20, milestones=["25"],  # 已标 25
    )
    events = [_event("reading", now, importance=1.0) for _ in range(3)]
    p = _make_plugin(events, [proj])
    eng = LifeConsolidationEngine(p)
    eng.consolidate_sync("s1", now)
    # 即使新 progress 跨过 0.25 仍只一个 "25"
    assert proj.milestones.count("25") == 1


def test_project_milestones_const():
    """里程碑常量在 (0.25, 0.5, 0.75, 1.0)。"""
    assert PROJECT_MILESTONES == (0.25, 0.5, 0.75, 1.0)
