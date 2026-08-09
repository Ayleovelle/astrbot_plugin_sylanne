"""Phase 2A 二审修复测试：MED-1 双重注入去重 + MED-2 _mark_life_outcome warning。

直调真实 _prepare_memory_context（不复刻逻辑，二审 LOW3 纪律）。
"""

from __future__ import annotations

import asyncio
import time

from sylanne_alpha.life_simulation import LifeEvent, LifeSimulator
from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline
from sylanne_alpha.memory_system import MemorySystem, RecallMode
from sylanne_alpha.session_state_store import SessionStateStore


class _FakeEngine:
    def observe(self):
        return {"warmth": 0.0}


class _FakeComputation:
    engine = _FakeEngine()


class _FakeKernel:
    computation = _FakeComputation()
    last_event = {"now": 0.0}


class _FakeHost:
    kernel = _FakeKernel()


def _make_pipe(sim, mem_sys):
    store = SessionStateStore()

    class _FakePlugin:
        _life_simulator = sim
        _store = store
        config = {}
        _config = {}

        def _host(self, sk):
            return _FakeHost()

        def _memory_system_for_session(self, sk):
            return mem_sys

    pipe = LLMRequestPipeline.__new__(LLMRequestPipeline)
    pipe._p = _FakePlugin()
    return pipe, store


def _fresh_ctx(eid, reason="我去咖啡馆写代码了"):
    return {
        "reason": reason, "mood": "calm", "intent_id": "i1", "event_id": eid,
        "delivery_mode": "next_reply", "reason_code": "score_0.5",
        "expires_at": time.time() + 1000.0, "target_session": "s1", "queued_at": 1.0,
    }


def test_no_double_injection_same_round_prepare_memory_context():
    """MED-1：同一 life event 本轮不会同时进 outreach_fragment 与 memory_fragment。

    life_sim 写 memory 延后到 recall 之后，本轮 recall 取不到刚写入的记忆。
    """
    sim = LifeSimulator(config={})
    ev = LifeEvent(text="我去咖啡馆写代码了", mood="calm", urgency=0.3,
                   timestamp=1.0, wants_to_share=True, queued_at=1.0)
    sim.state.events = [ev]
    eid = ev.event_id
    mem_sys = MemorySystem(recall_mode=RecallMode.LEGACY)
    pipe, store = _make_pipe(sim, mem_sys)
    store.pending_outreach_context.set("s1", _fresh_ctx(eid))

    # 开启 recall：message_text 非空 + gap 足够大 + realtime_enabled
    unfinished, outreach_fragment, memory_fragment = asyncio.run(
        pipe._prepare_memory_context(
            "s1", "咖啡馆写代码", gap_seconds=1000.0, realtime_enabled=True
        )
    )

    # outreach_fragment 含该事件；memory_fragment 本轮不含（写入已延后）
    assert "咖啡馆写代码" in outreach_fragment
    assert "咖啡馆写代码" not in memory_fragment
    # 写入确实发生了（延后执行）：下一轮可被 recall
    assert any(
        getattr(it, "life_event_id", "") == eid
        for it in list(mem_sys._l1)
    )


def test_deferred_write_carries_metadata():
    """延后写入仍带 source/privacy/life_event_id metadata。"""
    sim = LifeSimulator(config={})
    ev = LifeEvent(text="我读了论文", mood="calm", urgency=0.3,
                   timestamp=1.0, wants_to_share=True, queued_at=1.0)
    sim.state.events = [ev]
    eid = ev.event_id
    mem_sys = MemorySystem(recall_mode=RecallMode.LEGACY)
    pipe, store = _make_pipe(sim, mem_sys)
    store.pending_outreach_context.set("s1", _fresh_ctx(eid, "我读了论文"))

    asyncio.run(pipe._prepare_memory_context(
        "s1", "论文", gap_seconds=1000.0, realtime_enabled=True
    ))
    written = [it for it in list(mem_sys._l1) if it.source == "life_sim"]
    assert written
    assert written[0].privacy_level == "shareable"
    assert written[0].confidence == 0.5
    assert written[0].life_event_id == eid


def test_mark_life_outcome_exception_warns_not_raises():
    """MED-2：_mark_life_outcome 内部抛异常 → warning 可观测，不 raise、不中断。"""
    import logging

    sim = LifeSimulator(config={})
    ev = LifeEvent(text="事件", mood="m", urgency=0.2, timestamp=1.0,
                   wants_to_share=True, queued_at=1.0)
    sim.state.events = [ev]
    eid = ev.event_id

    def _boom(*a, **k):
        raise RuntimeError("consume boom")

    sim.mark_outreach_consumed = _boom
    mem_sys = MemorySystem(recall_mode=RecallMode.LEGACY)
    pipe, store = _make_pipe(sim, mem_sys)
    store.pending_outreach_context.set("s1", _fresh_ctx(eid, "事件"))

    # 直接挂 handler 抓该 logger（其 propagate 可能关闭，caplog 抓不到）
    records: list[logging.LogRecord] = []

    class _Cap(logging.Handler):
        def emit(self, r):
            records.append(r)

    from sylanne_alpha.llm_request_pipeline import logger as pipe_logger
    lg = pipe_logger  # 直接用模块内真实 logger 对象（propagate 可能关闭，root 抓不到）
    h = _Cap()
    h.setLevel(logging.WARNING)
    lg.addHandler(h)
    try:
        # 不应抛异常（主流程不中断）
        unfinished, outreach_fragment, memory_fragment = asyncio.run(
            pipe._prepare_memory_context(
                "s1", "", gap_seconds=0, realtime_enabled=False
            )
        )
    finally:
        lg.removeHandler(h)

    msgs = " ".join(r.getMessage() for r in records)
    assert eid in msgs and "consumed" in msgs  # warning 含 event_id + outcome


def test_mark_life_outcome_warns_directly():
    """直调 _mark_life_outcome：life_sim 抛异常 → warning，不 raise。"""
    import logging

    class _BoomSim:
        def mark_outreach_dropped(self, *a, **k):
            raise ValueError("drop boom")

    class _P:
        _life_simulator = _BoomSim()

    pipe = LLMRequestPipeline.__new__(LLMRequestPipeline)
    pipe._p = _P()
    # 不抛即通过（warning 由 logger 记录）
    pipe._mark_life_outcome("evt-x", "dropped")

