"""PR-B 专项测试：结构化世界模型 + 编排器 + prompt fragment。

覆盖 Phase 1 核心契约（不含 ShareIntent，那是 PR-C）：
- V2 字段在 tick 后正确填充（source/privacy_level/importance/valence_delta/world 更新）
- 活动延续：连续 tick 中 world.current_activity_id 演化、计数递增
- 节律一致性：相位/能量注入 prompt（夜间低能量不应鼓励剧烈活动）
- prompt fragment 长度上限 + 结构化 [life_world] 格式
- recent_context_for_prompt 兼容 alias 与 life_prompt_fragment 一致
- 隐私过滤：user_fact 事件不进 prompt fragment
"""

import asyncio
import json

from sylanne_alpha.life_simulation import (
    LifeEvent,
    LifePhase,
    LifePrivacy,
    LifeSimulator,
    LifeSource,
)


def _good_caller(payload: dict):
    async def _c(prompt: str):
        _c.last_prompt = prompt
        return json.dumps(payload)
    _c.last_prompt = ""
    return _c


# ---------------------------------------------------------------------------
# V2 字段填充
# ---------------------------------------------------------------------------
def test_tick_fills_v2_fields():
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})
    sim.configure(llm_caller=_good_caller(
        {"activity": "写 shader", "thought": "调颜色", "mood": "focused",
         "wants_to_share": True, "urgency": 0.5}
    ))
    asyncio.run(sim.simulate_tick())

    assert len(sim.state.events) == 1
    ev = sim.state.events[0]
    assert ev.source == LifeSource.PLANNED_TICK
    assert ev.privacy_level == LifePrivacy.SHAREABLE   # life sim 默认可分享
    assert ev.importance > 0.0                          # 规则评分
    assert ev.event_id                                  # 自动生成
    assert ev.queued_at > 0                             # 入队时间戳
    # world 更新
    assert sim.state.world.current_activity_id == ev.event_id
    assert sim.state.world.last_tick_at > 0
    assert sim.state.world.phase in (
        LifePhase.MORNING, LifePhase.AFTERNOON,
        LifePhase.EVENING, LifePhase.NIGHT, LifePhase.SLEEP,
    )


def test_life_sim_never_marks_user_fact():
    """life sim 自造内容永不标 USER_FACT（v2 ADR-002 / §10.1）。"""
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})
    sim.configure(llm_caller=_good_caller(
        {"activity": "听说用户下周考试", "thought": "", "mood": "neutral",
         "wants_to_share": False, "urgency": 0.1}
    ))
    asyncio.run(sim.simulate_tick())
    ev = sim.state.events[0]
    assert ev.privacy_level != LifePrivacy.USER_FACT
    assert ev.source != LifeSource.LEGACY               # 是 PLANNED_TICK


# ---------------------------------------------------------------------------
# 活动延续 + 计数递增
# ---------------------------------------------------------------------------
def test_consecutive_ticks_advance_state():
    """连续 3 次 tick：计数递增、world.last_tick_at 递增、activity_id 各异。"""
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})
    activities = ["看书", "散步", "做饭"]
    sim.configure(llm_caller=_good_caller(
        {"activity": "看书", "thought": "", "mood": "calm",
         "wants_to_share": False, "urgency": 0.1}
    ))
    # 用可变 caller 依次返回不同活动
    state = {"i": 0}
    async def _seq(prompt):
        act = activities[state["i"] % len(activities)]
        state["i"] += 1
        return json.dumps({"activity": act, "thought": "", "mood": "ok",
                           "wants_to_share": False, "urgency": 0.1})
    sim._llm_caller = _seq
    for _ in range(3):
        asyncio.run(sim.simulate_tick())

    assert sim.state.simulation_count == 3
    assert len(sim.state.events) == 3
    ids = [e.event_id for e in sim.state.events]
    assert len(set(ids)) == 3                            # 各异
    # last_tick_at 递增
    assert sim.state.world.last_tick_at > 0


# ---------------------------------------------------------------------------
# 节律一致性：prompt 注入相位/能量
# ---------------------------------------------------------------------------
def test_rhythm_hint_injected_for_low_energy_phase():
    """模拟夜间/低能量时，prompt 应注入节律约束（避免凌晨高能活动）。"""
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})
    sim.configure(llm_caller=_good_caller(
        {"activity": "x", "thought": "", "mood": "m", "wants_to_share": False, "urgency": 0.0}
    ))
    # 直接构造一个 SLEEP 相位 + 低能量的 world，跑 _load_world_context
    import datetime
    # 找一个凌晨 3 点的时间戳
    dt = datetime.datetime(2026, 6, 18, 3, 0, 0)
    ts = dt.timestamp()
    # HIGH1 修复：_load_world_context 现在纯计算，候选值进 ctx（不写 state.world）
    before_energy = sim.state.world.energy
    ctx = sim._load_world_context(ts, datetime)
    assert ctx["phase"] == LifePhase.SLEEP
    # state.world 未被改（空 tick 不 commit）
    assert sim.state.world.energy == before_energy
    # 但候选 energy 朝 SLEEP 目标(0.3)走一步
    assert ctx["_cand_energy"] < 0.6
    # prompt 含节律提示
    prompt = sim._build_prompt(ts, ctx)
    assert "夜间" in prompt or "低能量" in prompt or "安静" in prompt


def test_rhythm_no_hint_for_normal_afternoon():
    import datetime
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})
    sim.configure(llm_caller=_good_caller(
        {"activity": "x", "thought": "", "mood": "m", "wants_to_share": False, "urgency": 0.0}
    ))
    # 把 energy 抬高到正常，相位设为 AFTERNOON
    sim.state.world.energy = 0.7
    dt = datetime.datetime(2026, 6, 18, 15, 0, 0)
    ts = dt.timestamp()
    ctx = sim._load_world_context(ts, datetime)
    assert ctx["phase"] == LifePhase.AFTERNOON
    prompt = sim._build_prompt(ts, ctx)
    # 下午 + 正常能量不应有夜间约束
    assert "夜间" not in prompt


# ---------------------------------------------------------------------------
# prompt fragment：结构化格式 + 长度上限 + 隐私过滤
# ---------------------------------------------------------------------------
def test_life_prompt_fragment_structured_and_capped():
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})
    # 塞 30 条事件
    sim.state.events = [
        LifeEvent(text=f"事件{i}" * 5, mood="mood", urgency=0.1, timestamp=float(i))
        for i in range(30)
    ]
    sim.state.current_activity = "当前活动"
    sim.state.world.phase = LifePhase.EVENING
    frag = sim.life_prompt_fragment(limit=3, max_budget=200)
    assert frag.startswith("[life_world]")
    assert "当前活动" in frag
    assert len(frag) <= 200                              # 长度上限
    assert frag.endswith("...") or len(frag) < 200


def test_alias_recent_context_matches_fragment():
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})
    sim.state.events = [LifeEvent(text="事件A", mood="happy", urgency=0.1, timestamp=1.0)]
    sim.state.current_activity = "正在做某事"
    assert sim.recent_context_for_prompt(limit=3) == sim.life_prompt_fragment(limit=3)


def test_user_fact_events_filtered_from_fragment():
    """user_fact 隐私级事件不进用户可见 prompt fragment（防 life sim 污染用户事实）。"""
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})
    sim.state.events = [
        LifeEvent(text="普通生活", mood="ok", urgency=0.1, timestamp=1.0,
                  privacy_level=LifePrivacy.SHAREABLE),
        LifeEvent(text="用户下周考试", mood="ok", urgency=0.5, timestamp=2.0,
                  privacy_level=LifePrivacy.USER_FACT),
    ]
    sim.state.current_activity = "做事"
    frag = sim.life_prompt_fragment(limit=5)
    assert "普通生活" in frag
    assert "用户下周考试" not in frag                  # user_fact 过滤


def test_empty_state_returns_empty_fragment():
    sim = LifeSimulator(config={})
    assert sim.life_prompt_fragment() == ""
