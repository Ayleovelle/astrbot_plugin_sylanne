"""PR-C 专项测试：ShareIntent + 四时点投递 + H3 双路径 gate 收口。

覆盖 Phase 1 分享策略升级核心契约：
- ShareIntent 评分与 delivery_mode 映射（silent/next_reply/bridge/direct）
- delivery_mode=SILENT 时跳过 outreach（只留 journal）
- LifeEvent 投递四时点（queued/dispatched/consumed/dropped）回写
- pending_share_events 用四时点语义（M11）
- _life_sim_outreach 扩展 pending 字段 + 回调签名兼容（三参/两参）
- H3：evaluate_outreach_gate 在 fallback 中被调用（scheduler gate 不再被绕过）
"""

import asyncio
import json
import time

from sylanne_alpha.life_simulation import (
    DeliveryMode,
    LifeEvent,
    LifePhase,
    LifePrivacy,
    LifeSimulator,
    ShareIntent,
    _score_to_delivery,
)


def _good_caller(payload: dict):
    async def _c(prompt: str):
        return json.dumps(payload)
    return _c


# ---------------------------------------------------------------------------
# ShareIntent 评分与 delivery_mode 映射
# ---------------------------------------------------------------------------
def test_score_to_delivery_thresholds():
    """v2 §4.6 阈值：< 0.25 silent / < 0.55 next_reply / < 0.78 bridge / >= 0.78 direct。"""
    assert _score_to_delivery(0.10) == DeliveryMode.SILENT
    assert _score_to_delivery(0.30) == DeliveryMode.NEXT_REPLY
    assert _score_to_delivery(0.60) == DeliveryMode.BRIDGE
    assert _score_to_delivery(0.80) == DeliveryMode.DIRECT


def test_silent_event_skips_outreach():
    """delivery_mode=SILENT 时只留 journal，不触发 outreach_callback（v2 §4.6）。"""
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})
    outreach_calls = []

    async def _outreach(reason, mood, intent=None):
        outreach_calls.append((reason, mood, intent))

    # 让 final_score 低：urgency=0, 内部低重要性事件
    sim.configure(
        llm_caller=_good_caller(
            {"activity": "发呆", "thought": "", "mood": "neutral",
             "wants_to_share": True, "urgency": 0.0}
        ),
        outreach_callback=_outreach,
    )
    # 强制冷期内（cooldown_penalty 高 → score 低 → SILENT）
    sim.state.last_outreach_time = time.time()  # 刚 outreach 过
    asyncio.run(sim.simulate_tick())

    assert len(sim.state.events) == 1
    ev = sim.state.events[0]
    assert ev.share_intent_id  # 仍评估了 intent
    intent = sim._share_intents[ev.share_intent_id]
    # SILENT 不应触发 outreach callback
    assert outreach_calls == []
    assert intent.delivery_mode == DeliveryMode.SILENT


def test_share_intent_stored_and_attached():
    """wants_to_share 事件会评估 ShareIntent 并存入 _share_intents + 挂到 event。"""
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})
    sim.configure(llm_caller=_good_caller(
        {"activity": "做了一件有意思的事", "thought": "", "mood": "happy",
         "wants_to_share": True, "urgency": 0.5}
    ))
    asyncio.run(sim.simulate_tick())
    ev = sim.state.events[0]
    assert ev.share_intent_id in sim._share_intents
    intent = sim._share_intents[ev.share_intent_id]
    assert intent.event_id == ev.event_id
    assert 0.0 <= intent.final_score <= 1.0
    assert intent.delivery_mode in (
        DeliveryMode.SILENT, DeliveryMode.NEXT_REPLY,
        DeliveryMode.BRIDGE, DeliveryMode.DIRECT,
    )


# ---------------------------------------------------------------------------
# 投递四时点 + pending_share_events 语义（M11）
# ---------------------------------------------------------------------------
def test_pending_share_events_uses_four_timestamps():
    """pending = wants_to_share AND queued>0 AND consumed==0 AND dropped==0。"""
    sim = LifeSimulator(config={})
    sim.state.events = [
        LifeEvent(text="未消费", mood="m", urgency=0.1, timestamp=1.0,
                  wants_to_share=True, queued_at=1.0, consumed_at=0.0, dropped_at=0.0),
        LifeEvent(text="已消费", mood="m", urgency=0.1, timestamp=2.0,
                  wants_to_share=True, queued_at=2.0, consumed_at=3.0, dropped_at=0.0),
        LifeEvent(text="已丢弃", mood="m", urgency=0.1, timestamp=3.0,
                  wants_to_share=True, queued_at=3.0, consumed_at=0.0, dropped_at=4.0),
    ]
    pending = sim.pending_share_events()
    assert len(pending) == 1
    assert pending[0].text == "未消费"


def test_mark_outcome_helpers_write_timestamps():
    sim = LifeSimulator(config={})
    sim.state.events = [
        LifeEvent(text="e", mood="m", urgency=0.1, timestamp=1.0, wants_to_share=True),
    ]
    eid = sim.state.events[0].event_id
    sim.mark_outreach_dispatched(eid, now=100.0)
    assert sim.state.events[0].dispatched_at == 100.0
    assert sim.state.events[0].shared is True  # 兼容
    sim.mark_outreach_consumed(eid, now=200.0)
    assert sim.state.events[0].consumed_at == 200.0
    sim.mark_outreach_dropped(eid, now=300.0)
    assert sim.state.events[0].dropped_at == 300.0


def test_share_intent_id_persists_roundtrip():
    sim = LifeSimulator(config={})
    sim.state.events = [
        LifeEvent(text="e", mood="m", urgency=0.1, timestamp=1.0,
                  share_intent_id="intent_abc"),
    ]
    data = sim.to_dict()
    sim2 = LifeSimulator(config={})
    sim2.from_dict(data)
    assert sim2.state.events[0].share_intent_id == "intent_abc"


# ---------------------------------------------------------------------------
# _life_sim_outreach 扩展字段 + 回调签名兼容（三参/两参）
# ---------------------------------------------------------------------------
def test_do_outreach_passes_intent_to_callback():
    """三参回调收到 intent dict；_do_outreach 携带 ShareIntent。"""
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})
    captured = {}

    async def _outreach3(reason, mood, intent=None):
        captured["reason"] = reason
        captured["mood"] = mood
        captured["intent"] = intent

    sim.configure(
        llm_caller=_good_caller(
            {"activity": "开心事", "thought": "", "mood": "happy",
             "wants_to_share": True, "urgency": 0.6}
        ),
        outreach_callback=_outreach3,
    )
    asyncio.run(sim.simulate_tick())
    assert "reason" in captured
    assert captured["intent"] is not None
    assert "intent_id" in captured["intent"]
    assert "delivery_mode" in captured["intent"]


def test_do_outreach_falls_back_to_two_arg_callback():
    """旧的两参回调（reason, mood）仍兼容——TypeError 退化。"""
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})
    captured = {}

    async def _outreach2(reason, mood):  # 故意只收两参
        captured["reason"] = reason
        captured["mood"] = mood

    sim.configure(
        llm_caller=_good_caller(
            {"activity": "开心事", "thought": "", "mood": "happy",
             "wants_to_share": True, "urgency": 0.6}
        ),
        outreach_callback=_outreach2,
    )
    asyncio.run(sim.simulate_tick())  # 不应抛 TypeError
    assert captured["reason"]


# ---------------------------------------------------------------------------
# H3：evaluate_outreach_gate 收口（scheduler gate 不再被绕过）
# ---------------------------------------------------------------------------
def test_evaluate_outreach_gate_blocks_when_cooldown_active():
    """ProactiveScheduler.evaluate_outreach_gate：冷却期未过返回 blocked。"""
    from sylanne_alpha.proactive_scheduler import ProactiveScheduler

    class _FakeStore:
        proactive_candidate_sessions = {}  # 经 _store 访问（2.1.0）
        hosts = {}  # line 203 取人格用（空 → 用默认 expression_drive）

    class _FakePlugin:
        config = {"enable_proactive_speech_dispatch": True,
                  "proactive_speech_dispatch_cooldown_seconds": 1800.0,
                  "proactive_speech_min_idle_seconds": 300.0}
        _observed_now = time.time()
        _store = _FakeStore()
        _proactive_dispatch_last_sent = {"s1": time.time()}  # 刚发过 → cooldown 活跃

    sched = ProactiveScheduler(_FakePlugin())
    allowed, reason = sched.evaluate_outreach_gate("s1")
    assert allowed is False
    assert reason == "cooldown_active"


def test_evaluate_outreach_gate_allows_when_clear():
    from sylanne_alpha.proactive_scheduler import ProactiveScheduler

    class _FakeStore:
        proactive_candidate_sessions = {"s1": {"last_seen_at": 0.0}}
        hosts = {}

    class _FakePlugin:
        config = {"enable_proactive_speech_dispatch": True,
                  "proactive_speech_dispatch_cooldown_seconds": 60.0,
                  "proactive_speech_min_idle_seconds": 10.0}
        _observed_now = time.time()
        _store = _FakeStore()
        _proactive_dispatch_last_sent = {"s1": 0.0}  # 很久前发过

    sched = ProactiveScheduler(_FakePlugin())
    allowed, reason = sched.evaluate_outreach_gate("s1")
    assert allowed is True
    assert reason == ""


def test_pipeline_mark_life_outcome_writes_back_to_event():
    """_mark_life_outcome 把 dispatched/consumed/dropped 回写到 LifeEvent。"""
    from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline

    sim = LifeSimulator(config={})
    sim.state.events = [
        LifeEvent(text="e", mood="m", urgency=0.1, timestamp=1.0, wants_to_share=True),
    ]
    eid = sim.state.events[0].event_id

    class _FakePlugin:
        _life_simulator = sim

    pipe = LLMRequestPipeline.__new__(LLMRequestPipeline)
    pipe._p = _FakePlugin()

    pipe._mark_life_outcome(eid, "dispatched")
    assert sim.state.events[0].dispatched_at > 0
    pipe._mark_life_outcome(eid, "consumed")
    assert sim.state.events[0].consumed_at > 0
    pipe._mark_life_outcome(eid, "dropped")
    assert sim.state.events[0].dropped_at > 0
