"""Phase 2C / M8：主动发言反馈单一数据源测试。

钉死 M8 契约（补建 _proactive_dispatch_audit 干涸数据源）：
- consumed → audit 记 answered；dropped(过期未消费) → 记 unanswered
- feedback_pressure 读 audit 出非零（源不再干涸）
- origin_session 隔离：A 未回应不抬 B 的 cooldown
- 无双罚：unanswered 只在 scheduler gate（feedback_pressure）生效，ShareIntent 侧 *0.0

用 MethodType 把真实方法（pipeline._record_dispatch_feedback / _mark_life_outcome,
scheduler.derive_dispatch_policy）绑到最小 fake plugin，测真实逻辑而非复刻品。
"""

from __future__ import annotations

import types

from sylanne_alpha.bounded_dict import BoundedDict
from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline
from sylanne_alpha.proactive_scheduler import ProactiveScheduler


def _make_plugin():
    """最小 plugin：仅含 audit 链路依赖（无 life_sim，验 audit 独立于 life_sim）。"""
    p = types.SimpleNamespace()
    p._proactive_dispatch_audit = BoundedDict(maxsize=100)
    p._life_simulator = None  # 无 life_sim：audit 写入不应依赖它
    p.config = {"enable_proactive_speech_dispatch": True}
    return p


def _bind_pipe(p):
    """把 pipeline 的 audit 相关真实方法绑到 fake plugin。"""
    pipe = types.SimpleNamespace()
    pipe._p = p
    pipe._record_dispatch_feedback = types.MethodType(
        LLMRequestPipeline._record_dispatch_feedback, pipe
    )
    pipe._mark_life_outcome = types.MethodType(
        LLMRequestPipeline._mark_life_outcome, pipe
    )
    return pipe


def _scheduler(p):
    return ProactiveScheduler(p)


def test_consumed_writes_answered():
    p = _make_plugin()
    pipe = _bind_pipe(p)
    pipe._mark_life_outcome("ev1", "consumed", "sessA")
    hist = list(p._proactive_dispatch_audit.get("sessA"))
    assert len(hist) == 1
    assert hist[0]["feedback_status"] == "answered"


def test_dropped_writes_unanswered():
    p = _make_plugin()
    pipe = _bind_pipe(p)
    pipe._mark_life_outcome("ev1", "dropped", "sessA")
    hist = list(p._proactive_dispatch_audit.get("sessA"))
    assert len(hist) == 1
    assert hist[0]["feedback_status"] == "unanswered"


def test_feedback_pressure_nonzero_after_unanswered():
    """源不再干涸：写入 unanswered 后 feedback_pressure > 0。"""
    p = _make_plugin()
    pipe = _bind_pipe(p)
    sched = _scheduler(p)
    # 干涸态：无 audit → 压力 0
    assert sched.derive_dispatch_policy(session_key="sessA")["feedback_pressure"] == 0.0
    # 写两条 unanswered
    pipe._mark_life_outcome("ev1", "dropped", "sessA")
    pipe._mark_life_outcome("ev2", "dropped", "sessA")
    pol = sched.derive_dispatch_policy(session_key="sessA")
    assert pol["feedback_pressure"] > 0.0  # 源通了
    # answered 不计入压力
    p2 = _make_plugin()
    pipe2 = _bind_pipe(p2)
    pipe2._mark_life_outcome("ev1", "consumed", "sessA")
    assert _scheduler(p2).derive_dispatch_policy(session_key="sessA")["feedback_pressure"] == 0.0


def test_origin_session_isolation():
    """A 未回应只抬 A 的压力，不影响 B。"""
    p = _make_plugin()
    pipe = _bind_pipe(p)
    sched = _scheduler(p)
    pipe._mark_life_outcome("ev1", "dropped", "sessA")
    pipe._mark_life_outcome("ev2", "dropped", "sessA")
    assert sched.derive_dispatch_policy(session_key="sessA")["feedback_pressure"] > 0.0
    assert sched.derive_dispatch_policy(session_key="sessB")["feedback_pressure"] == 0.0


def test_audit_independent_of_lifesim():
    """audit 写入不依赖 life_sim（_life_simulator=None 也照写）——M8 解耦核心。"""
    p = _make_plugin()
    assert p._life_simulator is None
    pipe = _bind_pipe(p)
    pipe._mark_life_outcome("ev1", "dropped", "sessA")
    assert p._proactive_dispatch_audit.get("sessA") is not None


def test_no_session_key_no_audit():
    """无 session_key（空）→ 不写 audit（防空 key 污染）。"""
    p = _make_plugin()
    pipe = _bind_pipe(p)
    pipe._mark_life_outcome("ev1", "dropped", "")
    assert p._proactive_dispatch_audit.get("") is None


# ---------------------------------------------------------------------------
# T2-07③：withheld（她自己的门控/迟疑取消）不是惩罚性 unanswered
# ---------------------------------------------------------------------------

def test_withheld_does_not_write_unanswered_audit():
    """gate 拒绝 / 犹豫收回 → withheld，不应写 unanswered（不是用户没回应）。"""
    p = _make_plugin()
    pipe = _bind_pipe(p)
    pipe._mark_life_outcome("ev1", "withheld", "sessA")
    assert p._proactive_dispatch_audit.get("sessA") is None


def test_withheld_does_not_raise_feedback_pressure():
    """withheld 不应贡献 feedback_pressure（否则等于她的收回反过来罚用户）。"""
    p = _make_plugin()
    pipe = _bind_pipe(p)
    sched = _scheduler(p)
    pipe._mark_life_outcome("ev1", "withheld", "sessA")
    pipe._mark_life_outcome("ev2", "withheld", "sessA")
    assert sched.derive_dispatch_policy(session_key="sessA")["feedback_pressure"] == 0.0


def test_withheld_still_marks_lifeevent_dropped_at():
    """withheld 仍要回写 LifeEvent.dropped_at（生命周期记账不受影响，只是不惩罚）。"""
    from sylanne_alpha.life_simulation import LifeEvent, LifeSimulator

    sim = LifeSimulator(config={})
    sim.state.events = [
        LifeEvent(text="e", mood="m", urgency=0.1, timestamp=1.0, wants_to_share=True),
    ]
    eid = sim.state.events[0].event_id
    p = _make_plugin()
    p._life_simulator = sim
    pipe = _bind_pipe(p)
    pipe._mark_life_outcome(eid, "withheld", "sessA")
    assert sim.state.events[0].dropped_at > 0
