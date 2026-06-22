"""Phase 3 / LifeSkill 自适应技能测试。

验证：
- LifeSkill dataclass to_dict/from_dict roundtrip
- v2 → v3 迁移注入 3 个种子技能
- _match_skill 命中 trigger_event_types 且尊重冷却
- cooldown_multiplier 自适应（effectiveness 低 → 倍率拉长）
- SKILL_EFFECTIVENESS_FLOOR：effectiveness 不会跌破 0.1
- 巩固期 _update_skill_outcomes：answered→success、unanswered→failure
"""

from __future__ import annotations

import time
import types

from sylanne_alpha.life_consolidation import LifeConsolidationEngine
from sylanne_alpha.life_simulation import (
    SKILL_COOLDOWN_MULT_MAX,
    SKILL_COOLDOWN_MULT_MIN,
    SKILL_EFFECTIVENESS_FLOOR,
    LifeEvent,
    LifeSimulationState,
    LifeSimulator,
    LifeSkill,
    LifeWorldState,
    _seed_skills,
    _skill_from_dict,
    _skill_to_dict,
)


def _make_sim_with_skills(skills: list[LifeSkill], audit: dict | None = None):
    state = LifeSimulationState(
        events=[],
        world=LifeWorldState(),
        skills=list(skills),
        outreach_audit=dict(audit or {}),
    )
    return types.SimpleNamespace(state=state)


# ---------------------------------------------------------------------------
# Roundtrip
# ---------------------------------------------------------------------------

def test_life_skill_roundtrip():
    s = LifeSkill(
        name="evening_soft_checkin",
        trigger_event_types=["resting", "observing"],
        cooldown_seconds=7200,
        cooldown_multiplier=2.0,
        last_triggered_at=1000.0,
        success_count=3,
        failure_count=1,
        effectiveness=0.7,
    )
    d = _skill_to_dict(s)
    s2 = _skill_from_dict(d)
    assert s2.skill_id == s.skill_id
    assert s2.name == "evening_soft_checkin"
    assert s2.trigger_event_types == ["resting", "observing"]
    assert s2.cooldown_seconds == 7200
    assert s2.cooldown_multiplier == 2.0
    assert s2.last_triggered_at == 1000.0
    assert s2.success_count == 3
    assert s2.effectiveness == 0.7


def test_life_skill_default_id_assigned():
    s = LifeSkill(name="x")
    assert s.skill_id and len(s.skill_id) == 12


# ---------------------------------------------------------------------------
# Seed init / migration
# ---------------------------------------------------------------------------

def test_seed_skills_three_defaults():
    seeds = _seed_skills()
    assert len(seeds) == 3
    names = {s.name for s in seeds}
    assert names == {
        "evening_soft_checkin",
        "creative_milestone_share",
        "thesis_companion",
    }


def test_seed_skills_unique_ids():
    seeds = _seed_skills()
    ids = {s.skill_id for s in seeds}
    assert len(ids) == 3


def test_fresh_state_has_seed_skills():
    """LifeSimulationState 默认初始化时 skills 含种子三条。"""
    state = LifeSimulationState()
    assert len(state.skills) == 3


# ---------------------------------------------------------------------------
# Match + cooldown
# ---------------------------------------------------------------------------

def test_match_skill_triggers_on_event_type():
    skill = LifeSkill(
        name="x",
        trigger_event_types=["reading"],
        cooldown_seconds=3600,
    )
    sim = LifeSimulator(config={})
    sim.state = LifeSimulationState(skills=[skill])
    event = LifeEvent(text="读书", mood="calm", urgency=0.1, timestamp=1000.0,
                     event_type="reading")
    out = sim._match_skill(event, now=1000.0)
    assert out is skill
    assert skill.last_triggered_at == 1000.0


def test_match_skill_returns_none_when_event_type_not_in_triggers():
    skill = LifeSkill(name="x", trigger_event_types=["reading"], cooldown_seconds=3600)
    sim = LifeSimulator(config={})
    sim.state = LifeSimulationState(skills=[skill])
    event = LifeEvent(text="walk", mood="calm", urgency=0.1, timestamp=1000.0,
                     event_type="walking")
    assert sim._match_skill(event, now=1000.0) is None


def test_match_skill_respects_cooldown():
    skill = LifeSkill(
        name="x",
        trigger_event_types=["reading"],
        cooldown_seconds=3600,
        cooldown_multiplier=1.0,
        last_triggered_at=1000.0,
    )
    sim = LifeSimulator(config={})
    sim.state = LifeSimulationState(skills=[skill])
    event = LifeEvent(text="r", mood="c", urgency=0.1, timestamp=2000.0, event_type="reading")
    # 距上次 1000s，冷却 3600s → 不触发
    assert sim._match_skill(event, now=2000.0) is None
    # 跨过冷却 → 触发
    out = sim._match_skill(event, now=1000.0 + 3601)
    assert out is skill


def test_match_skill_cooldown_multiplier_extends_window():
    """multiplier > 1 时冷却窗口拉长。"""
    skill = LifeSkill(
        name="x",
        trigger_event_types=["reading"],
        cooldown_seconds=1000,
        cooldown_multiplier=2.0,
        last_triggered_at=1.0,  # 非零（last_triggered_at>0 才进冷却分支）
    )
    sim = LifeSimulator(config={})
    sim.state = LifeSimulationState(skills=[skill])
    event = LifeEvent(text="r", mood="c", urgency=0.1, timestamp=0.0, event_type="reading")
    # 1500s 后（< 2000s cooldown） → 仍然冷却
    assert sim._match_skill(event, now=1500.0) is None
    # 2100s 后 → 触发
    assert sim._match_skill(event, now=2100.0) is skill


# ---------------------------------------------------------------------------
# cooldown_multiplier 自适应公式
# ---------------------------------------------------------------------------

def test_adaptive_cooldown_multiplier_formula():
    """multiplier = clamp(1 + 2*(1-effectiveness), 1, 4)。"""
    sim = LifeSimulator(config={})
    # effectiveness=1.0 → multiplier=1.0
    assert sim._adaptive_cooldown_multiplier(1.0) == 1.0
    # effectiveness=0.5 → multiplier=2.0
    assert abs(sim._adaptive_cooldown_multiplier(0.5) - 2.0) < 1e-6
    # effectiveness=0.0 → 1+2*1 = 3.0（公式值，未触发 4 上界 clamp）
    assert abs(sim._adaptive_cooldown_multiplier(0.0) - 3.0) < 1e-6
    # effectiveness=-0.5 越界 → clamp 到下界 1.0（在 max() 内先 max(0, ...) 取 0）
    # 实际是 max(0, -0.5)=0 → 公式 = 3.0，仍在范围内
    # 测试边界 clamp：1.5 越界（被 min clamp 到 1.0）
    assert sim._adaptive_cooldown_multiplier(1.5) == SKILL_COOLDOWN_MULT_MIN
    # 不越上界（公式输出永远 ≤3.0，4.0 是为防极端调用而保留的上界）
    assert SKILL_COOLDOWN_MULT_MAX == 4.0


# ---------------------------------------------------------------------------
# Effectiveness floor + outcome update
# ---------------------------------------------------------------------------

def test_effectiveness_floor_after_repeated_failures():
    """连续 unanswered → effectiveness 不跌破 SKILL_EFFECTIVENESS_FLOOR。"""
    skill = LifeSkill(name="x", trigger_event_types=["x"], effectiveness=0.5)
    audit = {
        "_global": [
            {
                "kind": "dispatch",
                "event_id": f"e{i}",
                "skill_id": skill.skill_id,
                "feedback_status": "unanswered",
                "ts": 100.0 + i,
            }
            for i in range(50)
        ]
    }
    sim = _make_sim_with_skills([skill], audit)
    p = types.SimpleNamespace()
    p._life_simulator = sim
    eng = LifeConsolidationEngine(p)
    eng._update_skill_outcomes(sim.state, now=200.0)
    assert skill.effectiveness >= SKILL_EFFECTIVENESS_FLOOR
    assert skill.failure_count == 50


def test_answered_outcome_raises_effectiveness():
    """answered → success_count++，effectiveness 上行。"""
    skill = LifeSkill(name="x", trigger_event_types=["x"], effectiveness=0.3)
    audit = {
        "_global": [
            {
                "kind": "dispatch",
                "event_id": f"e{i}",
                "skill_id": skill.skill_id,
                "feedback_status": "answered",
                "ts": 100.0 + i,
            }
            for i in range(3)
        ]
    }
    sim = _make_sim_with_skills([skill], audit)
    p = types.SimpleNamespace()
    p._life_simulator = sim
    eng = LifeConsolidationEngine(p)
    eng._update_skill_outcomes(sim.state, now=200.0)
    assert skill.success_count == 3
    assert skill.effectiveness > 0.3  # 上行


def test_skill_outcome_idempotent_consumed_flag():
    """同一 entry 不重复消费（consumed_by_skill 标记）。"""
    skill = LifeSkill(name="x", trigger_event_types=["x"], effectiveness=0.5)
    audit = {
        "_global": [
            {
                "kind": "dispatch",
                "event_id": "e1",
                "skill_id": skill.skill_id,
                "feedback_status": "answered",
                "ts": 100.0,
            }
        ]
    }
    sim = _make_sim_with_skills([skill], audit)
    p = types.SimpleNamespace()
    p._life_simulator = sim
    eng = LifeConsolidationEngine(p)
    eng._update_skill_outcomes(sim.state, now=200.0)
    s1 = skill.success_count
    eng._update_skill_outcomes(sim.state, now=300.0)
    # 第二次跑同样 audit：consumed_by_skill 阻断重复消费
    assert skill.success_count == s1


def test_skill_outcome_updates_cooldown_multiplier():
    """outcome 更新后 cooldown_multiplier 重新计算。"""
    skill = LifeSkill(
        name="x", trigger_event_types=["x"], effectiveness=0.5, cooldown_multiplier=1.0
    )
    audit = {
        "_global": [
            {
                "kind": "dispatch",
                "event_id": f"e{i}",
                "skill_id": skill.skill_id,
                "feedback_status": "unanswered",
                "ts": 100.0 + i,
            }
            for i in range(10)
        ]
    }
    sim = _make_sim_with_skills([skill], audit)
    p = types.SimpleNamespace()
    p._life_simulator = sim
    eng = LifeConsolidationEngine(p)
    eng._update_skill_outcomes(sim.state, now=200.0)
    # effectiveness 跌 → multiplier 涨
    assert skill.cooldown_multiplier > 1.0
    assert skill.cooldown_multiplier <= SKILL_COOLDOWN_MULT_MAX
