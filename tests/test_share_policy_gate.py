"""Phase 3 / share_policy 项目级门控测试。

验证：
- milestone 策略：非里程碑事件 → 强制 SILENT（即便 score 高）
- never 策略：一律阻断
- casual 策略：放行
- 无 project 匹配的事件：passthrough（不受门控影响）
- 门控只影响 outreach 路径，不阻止项目认领与技能匹配
"""

from __future__ import annotations

import asyncio
import json

from sylanne_alpha.life_simulation import (
    DeliveryMode,
    LifeProject,
    LifeSimulator,
    LifeSkill,
    SHARE_POLICY_CASUAL,
    SHARE_POLICY_MILESTONE,
    SHARE_POLICY_NEVER,
)


def _fake_llm(payload: dict):
    async def _caller(prompt: str):
        return json.dumps(payload)
    return _caller


def _setup_sim_with_project(
    share_policy: str,
    milestones: list[str] | None = None,
    milestones_shared: list[str] | None = None,
    event_type: str = "creating",
):
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})
    proj = LifeProject(
        title="项目",
        kind="create",
        event_type=event_type,
        state="active",
        share_policy=share_policy,
        milestones=list(milestones or []),
        milestones_shared=list(milestones_shared or []),
    )
    sim.state.projects = [proj]
    # 高 share_tendency 的 wants_to_share 事件 payload
    payload = {
        "activity": "创作",
        "thought": "灵感来了",
        "mood": "excited",
        "wants_to_share": True,
        "urgency": 0.8,
    }
    outreach_calls = []

    async def _cb(reason, mood, intent=None):
        outreach_calls.append((reason, mood, intent))

    sim.configure(llm_caller=_fake_llm(payload), outreach_callback=_cb)
    return sim, proj, outreach_calls


def _force_event_type(sim: LifeSimulator, event_type: str):
    """因为 _infer_event_type 据关键词推断，我们改写 _parse_response 以确保 event_type。"""
    real_parse = sim._parse_response

    def _wrapped(response, now):
        out = real_parse(response, now)
        if out is None:
            return None
        event, weights = out
        event.event_type = event_type
        return event, weights

    sim._parse_response = _wrapped  # type: ignore


# ---------------------------------------------------------------------------
# milestone：默认策略，非里程碑 → SILENT
# ---------------------------------------------------------------------------

def test_milestone_policy_blocks_non_milestone_event():
    """share_policy=milestone 且项目无未分享里程碑 → 事件被强制 SILENT。"""
    sim, proj, outreach_calls = _setup_sim_with_project(SHARE_POLICY_MILESTONE)
    _force_event_type(sim, "creating")
    asyncio.run(sim.simulate_tick())
    # 事件已产生
    assert len(sim.state.events) == 1
    event = sim.state.events[0]
    # intent 被门控强制 SILENT
    intent = sim._share_intents.get(event.share_intent_id)
    assert intent is not None
    assert intent.delivery_mode == DeliveryMode.SILENT
    assert intent.reason_code == "policy_milestone"
    # outreach 未触发
    assert outreach_calls == []


def test_milestone_policy_allows_when_unshared_milestone_pending():
    """share_policy=milestone 且有未分享里程碑 → 不阻断。"""
    sim, proj, outreach_calls = _setup_sim_with_project(
        SHARE_POLICY_MILESTONE,
        milestones=["50"],
        milestones_shared=[],  # 50 未分享
    )
    _force_event_type(sim, "creating")
    asyncio.run(sim.simulate_tick())
    event = sim.state.events[0]
    intent = sim._share_intents.get(event.share_intent_id)
    # 不被门控（reason_code 不应是 policy_milestone）
    assert intent is not None
    assert intent.reason_code != "policy_milestone"


def test_milestone_marked_shared_after_successful_outreach():
    """第一轮 review 修复回归：outreach 成功后，首个未分享 milestone 必须被标 shared。

    否则 _check_share_policy_gate 在下一次 tick 仍放行，等价于 milestone 门控失效。
    """
    sim, proj, outreach_calls = _setup_sim_with_project(
        SHARE_POLICY_MILESTONE,
        milestones=["50", "75"],
        milestones_shared=[],  # 全部未分享
    )
    _force_event_type(sim, "creating")
    asyncio.run(sim.simulate_tick())
    # outreach 真的被调用（intent 评分够高 + 项目门控放行）
    assert len(outreach_calls) == 1, f"expected one outreach, got {outreach_calls}"
    # 首个未分享 milestone（"50"）被标 shared；"75" 仍未分享
    assert proj.milestones_shared == ["50"]
    # 重置 outreach 冷却让第二次 tick 也能发；验证 "75" 也会被依次消费
    sim.state.last_outreach_time = 0.0
    asyncio.run(sim.simulate_tick())
    assert proj.milestones_shared == ["50", "75"]
    # 再次重置冷却：所有 milestone 已分享 → 门控应阻断（policy_milestone）
    sim.state.last_outreach_time = 0.0
    asyncio.run(sim.simulate_tick())
    last_event = sim.state.events[-1]
    last_intent = sim._share_intents.get(last_event.share_intent_id)
    assert last_intent is not None
    assert last_intent.reason_code == "policy_milestone"
    assert last_intent.delivery_mode == DeliveryMode.SILENT


# ---------------------------------------------------------------------------
# never：一律阻断
# ---------------------------------------------------------------------------

def test_never_policy_always_blocks():
    sim, proj, outreach_calls = _setup_sim_with_project(SHARE_POLICY_NEVER)
    _force_event_type(sim, "creating")
    asyncio.run(sim.simulate_tick())
    event = sim.state.events[0]
    intent = sim._share_intents.get(event.share_intent_id)
    assert intent is not None
    assert intent.delivery_mode == DeliveryMode.SILENT
    assert intent.reason_code == "policy_never"
    assert outreach_calls == []


# ---------------------------------------------------------------------------
# casual：放行
# ---------------------------------------------------------------------------

def test_casual_policy_passes_through():
    sim, proj, outreach_calls = _setup_sim_with_project(SHARE_POLICY_CASUAL)
    _force_event_type(sim, "creating")
    asyncio.run(sim.simulate_tick())
    event = sim.state.events[0]
    intent = sim._share_intents.get(event.share_intent_id)
    assert intent is not None
    # reason_code 不应是 policy_*（不被门控）
    assert "policy_" not in intent.reason_code


# ---------------------------------------------------------------------------
# 无项目匹配：passthrough
# ---------------------------------------------------------------------------

def test_no_project_match_event_passes_gate():
    """事件 event_type 与任何项目都不匹配 → 不受门控影响。"""
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})
    # 项目 event_type=reading，但事件是 creating
    sim.state.projects = [
        LifeProject(
            title="读书", kind="study", event_type="reading", state="active",
            share_policy=SHARE_POLICY_NEVER,
        )
    ]
    payload = {
        "activity": "创作", "thought": "", "mood": "excited",
        "wants_to_share": True, "urgency": 0.8,
    }

    async def _cb(reason, mood, intent=None):
        pass

    sim.configure(llm_caller=_fake_llm(payload), outreach_callback=_cb)
    _force_event_type(sim, "creating")
    asyncio.run(sim.simulate_tick())
    event = sim.state.events[0]
    # event.project_id 应为空（无匹配项目）
    assert event.project_id == ""
    intent = sim._share_intents.get(event.share_intent_id)
    assert intent is not None
    # 不被项目门控（reason_code 不是 policy_*）
    assert "policy_" not in intent.reason_code


# ---------------------------------------------------------------------------
# 项目认领独立：门控不阻止 event.project_id 被设
# ---------------------------------------------------------------------------

def test_blocked_event_still_claims_project():
    """即便事件被 share_policy 门控为 SILENT，event.project_id 仍被认领（供后续巩固跟踪）。"""
    sim, proj, _ = _setup_sim_with_project(SHARE_POLICY_NEVER)
    _force_event_type(sim, "creating")
    asyncio.run(sim.simulate_tick())
    event = sim.state.events[0]
    assert event.project_id == proj.project_id
