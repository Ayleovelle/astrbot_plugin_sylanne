"""Phase 3 / M8 audit 补建测试。

验证 LifeSimulator.state.outreach_audit + scheduler 桥接：
- dispatch 被记录到 state.outreach_audit
- record_user_response 把 pending 标为 answered
- _check_outreach_timeouts 在 OUTREACH_TIMEOUT_SECONDS 后标 unanswered
- feedback_pressure 读 state.outreach_audit 非零
- 每会话条数上限 OUTREACH_AUDIT_PER_SESSION 不被突破
- 会话隔离：A 的 unanswered 不抬 B
"""

from __future__ import annotations

import asyncio
import json
import types

from sylanne_alpha.bounded_dict import BoundedDict
from sylanne_alpha.life_simulation import (
    OUTREACH_AUDIT_MAX_SESSIONS,
    OUTREACH_AUDIT_PER_SESSION,
    OUTREACH_TIMEOUT_SECONDS,
    LifeEvent,
    LifeSimulator,
)
from sylanne_alpha.proactive_scheduler import ProactiveScheduler


def _fake_llm(payload: dict):
    async def _caller(prompt: str):
        return json.dumps(payload)
    return _caller


def _setup_sim_dispatching(origin_session: str = ""):
    """构造一个能成功 dispatch 的 sim：高 score 事件 + outreach callback 不抛错。"""
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})
    payload = {
        "activity": "创作", "thought": "灵感", "mood": "excited",
        "wants_to_share": True, "urgency": 0.9,
    }
    outreach_calls = []

    async def _cb(reason, mood, intent=None):
        outreach_calls.append((reason, mood, intent))

    sim.configure(llm_caller=_fake_llm(payload), outreach_callback=_cb)
    # 覆写 _parse_response 让事件 event_type=creating 且 origin_session 可控
    real_parse = sim._parse_response

    def _wrapped(response, now):
        out = real_parse(response, now)
        if out is None:
            return None
        event, weights = out
        event.event_type = "creating"
        event.origin_session = origin_session
        return event, weights

    sim._parse_response = _wrapped  # type: ignore
    return sim, outreach_calls


# ---------------------------------------------------------------------------
# dispatch 被记录
# ---------------------------------------------------------------------------

def test_dispatch_records_audit_entry():
    sim, outreach_calls = _setup_sim_dispatching(origin_session="sessA")
    asyncio.run(sim.simulate_tick())
    assert len(outreach_calls) == 1
    bucket = sim.state.outreach_audit.get("sessA")
    assert bucket is not None
    assert len(bucket) == 1
    entry = bucket[0]
    assert entry["kind"] == "dispatch"
    assert entry["feedback_status"] == "pending"
    assert entry["event_id"]


def test_dispatch_audit_falls_back_to_global_key_when_no_origin_session():
    """origin_session 为空 → 用 _global 兜底（不污染真实会话 key）。"""
    sim, _ = _setup_sim_dispatching(origin_session="")
    asyncio.run(sim.simulate_tick())
    assert "_global" in sim.state.outreach_audit
    assert "sessA" not in sim.state.outreach_audit


# ---------------------------------------------------------------------------
# record_user_response
# ---------------------------------------------------------------------------

def test_record_user_response_marks_pending_as_answered():
    sim, _ = _setup_sim_dispatching(origin_session="sessA")
    asyncio.run(sim.simulate_tick())
    marked = sim.record_user_response("sessA", now=1000.0)
    assert marked == 1
    entry = sim.state.outreach_audit["sessA"][0]
    assert entry["feedback_status"] == "answered"
    assert entry["response_at"] == 1000.0


def test_record_user_response_no_session_returns_zero():
    sim = LifeSimulator(config={})
    assert sim.record_user_response("") == 0
    assert sim.record_user_response("unknown_session") == 0


# ---------------------------------------------------------------------------
# Timeout 扫描
# ---------------------------------------------------------------------------

def test_check_timeout_marks_unanswered_after_threshold():
    sim = LifeSimulator(config={})
    sim.state.outreach_audit["sessA"] = [
        {
            "kind": "dispatch", "event_id": "e1", "intent_id": "", "skill_id": "",
            "ts": 0.0, "response_at": 0.0, "timeout_at": 0.0,
            "feedback_status": "pending",
        }
    ]
    # 未到阈值（半个 timeout）→ 仍 pending
    sim._check_outreach_timeouts(now=OUTREACH_TIMEOUT_SECONDS / 2)
    assert sim.state.outreach_audit["sessA"][0]["feedback_status"] == "pending"
    # 超过阈值 → unanswered
    sim._check_outreach_timeouts(now=OUTREACH_TIMEOUT_SECONDS + 1)
    entry = sim.state.outreach_audit["sessA"][0]
    assert entry["feedback_status"] == "unanswered"
    assert entry["timeout_at"] >= OUTREACH_TIMEOUT_SECONDS


def test_check_timeout_does_not_touch_answered():
    sim = LifeSimulator(config={})
    sim.state.outreach_audit["sessA"] = [
        {
            "kind": "dispatch", "event_id": "e1", "ts": 0.0,
            "feedback_status": "answered", "response_at": 100.0, "timeout_at": 0.0,
        }
    ]
    sim._check_outreach_timeouts(now=OUTREACH_TIMEOUT_SECONDS + 1)
    assert sim.state.outreach_audit["sessA"][0]["feedback_status"] == "answered"


# ---------------------------------------------------------------------------
# feedback_pressure 真有数据
# ---------------------------------------------------------------------------

def test_feedback_pressure_nonzero_from_life_sim_audit():
    """scheduler.derive_dispatch_policy 读 state.outreach_audit 后压力非零。"""
    sim = LifeSimulator(config={})
    sim.state.outreach_audit["sessA"] = [
        {"feedback_status": "unanswered", "ts": 0.0},
        {"feedback_status": "unanswered", "ts": 0.0},
    ]
    p = types.SimpleNamespace()
    p._life_simulator = sim
    p._proactive_dispatch_audit = BoundedDict(maxsize=100)  # 空：pipeline 视角空
    p.config = {"enable_proactive_speech_dispatch": True}
    sched = ProactiveScheduler(p)
    pol = sched.derive_dispatch_policy(session_key="sessA")
    assert pol["feedback_pressure"] > 0.0


def test_feedback_pressure_zero_without_unanswered():
    sim = LifeSimulator(config={})
    sim.state.outreach_audit["sessA"] = [
        {"feedback_status": "answered", "ts": 0.0, "response_at": 100.0},
    ]
    p = types.SimpleNamespace()
    p._life_simulator = sim
    p._proactive_dispatch_audit = BoundedDict(maxsize=100)
    p.config = {"enable_proactive_speech_dispatch": True}
    sched = ProactiveScheduler(p)
    assert sched.derive_dispatch_policy(session_key="sessA")["feedback_pressure"] == 0.0


# ---------------------------------------------------------------------------
# 容量上限：每会话 OUTREACH_AUDIT_PER_SESSION
# ---------------------------------------------------------------------------

def test_audit_per_session_capped():
    sim = LifeSimulator(config={})
    event = LifeEvent(text="e", mood="m", urgency=0.1, timestamp=0.0,
                      origin_session="sessA", event_type="creating")
    # 写入 OUTREACH_AUDIT_PER_SESSION + 5 条
    for i in range(OUTREACH_AUDIT_PER_SESSION + 5):
        e = LifeEvent(
            text=f"e{i}", mood="m", urgency=0.1, timestamp=float(i),
            origin_session="sessA", event_type="creating",
        )
        sim._record_audit_dispatch(e, intent=None, skill=None, now=float(i))
    bucket = sim.state.outreach_audit["sessA"]
    assert len(bucket) == OUTREACH_AUDIT_PER_SESSION
    # 保留最新的（FIFO 裁旧）
    assert bucket[-1]["event_id"]  # 最后一个有 id


def test_audit_max_sessions_capped_lru():
    """超过 OUTREACH_AUDIT_MAX_SESSIONS 个会话时，最旧的被淘汰（第二轮 review 用例）。"""
    sim = LifeSimulator(config={})
    total_sessions = OUTREACH_AUDIT_MAX_SESSIONS + 5
    for i in range(total_sessions):
        session_id = f"sess{i}"
        event = LifeEvent(
            text=f"e{i}", mood="m", urgency=0.1, timestamp=float(i),
            origin_session=session_id, event_type="creating",
        )
        sim._record_audit_dispatch(event, intent=None, skill=None, now=float(i))
    audit = sim.state.outreach_audit
    assert len(audit) == OUTREACH_AUDIT_MAX_SESSIONS
    # 最新写入的会话保留
    assert f"sess{total_sessions - 1}" in audit
    # 最旧的会话已被 LRU 淘汰
    assert "sess0" not in audit


# ---------------------------------------------------------------------------
# 会话隔离
# ---------------------------------------------------------------------------

def test_session_isolation_unanswered_does_not_cross():
    sim = LifeSimulator(config={})
    sim.state.outreach_audit["sessA"] = [
        {"feedback_status": "unanswered", "ts": 0.0},
        {"feedback_status": "unanswered", "ts": 0.0},
    ]
    sim.state.outreach_audit["sessB"] = []
    p = types.SimpleNamespace()
    p._life_simulator = sim
    p._proactive_dispatch_audit = BoundedDict(maxsize=100)
    p.config = {"enable_proactive_speech_dispatch": True}
    sched = ProactiveScheduler(p)
    pa = sched.derive_dispatch_policy(session_key="sessA")
    pb = sched.derive_dispatch_policy(session_key="sessB")
    assert pa["feedback_pressure"] > 0.0
    assert pb["feedback_pressure"] == 0.0


# ---------------------------------------------------------------------------
# 兼容：unanswered_penalty 保持 *0.0（M8 单一惩罚通道守线）
# ---------------------------------------------------------------------------

def test_unanswered_penalty_remains_zero_in_share_intent():
    """单一惩罚通道：ShareIntent 侧 unanswered_penalty 贡献仍为 0.0。"""
    from sylanne_alpha.life_simulation import _SHARE_WEIGHTS
    # 权重定义可以非零（设计意图），但被乘以 0 后不影响 final_score
    assert "unanswered_penalty" in _SHARE_WEIGHTS
    # 通过 _recompute_final 验证：构造两个 intent 差异在 unanswered_penalty，结果一致
    from sylanne_alpha.life_simulation import ShareIntent
    sim = LifeSimulator(config={})
    a = ShareIntent(content_value=0.5, relationship_value=0.5)
    a.unanswered_penalty = 0.0
    b = ShareIntent(content_value=0.5, relationship_value=0.5)
    b.unanswered_penalty = 1.0  # 即使设满
    fa = sim._recompute_final(a)
    fb = sim._recompute_final(b)
    assert fa == fb  # *0.0 后不变
