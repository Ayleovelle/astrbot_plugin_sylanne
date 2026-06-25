"""PR-B/C review 复现测试（review §3 指定的 4 个最小复现）。

这些测试是 review 要求编写侧自行补充的回归，对应：
- case 1/2：空 tick 零副作用契约扩展到 world 状态（HIGH1）
- case 3：pending 过期在 _prepare_memory_context 路径也要 drop（HIGH2）
- case 4：三参回调内部 TypeError 不应触发二参重试（MED3）
"""

import asyncio
import copy
import json
import time

from sylanne_alpha.life_simulation import LifeEvent, LifeSimulator


# ---------------------------------------------------------------------------
# case 1 & 2：空 / 无效 LLM 响应时 state.world 完全不变（HIGH1）
# ---------------------------------------------------------------------------
def _assert_world_unchanged(sim, before):
    w = sim.state.world
    assert w.local_date == before.local_date, "local_date mutated on empty tick"
    assert w.phase == before.phase, "phase mutated on empty tick"
    assert w.energy == before.energy, "energy mutated on empty tick"
    assert w.focus == before.focus, "focus mutated on empty tick"
    assert w.current_activity_id == before.current_activity_id
    assert w.last_tick_at == before.last_tick_at


def test_case1_empty_response_world_unchanged():
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})

    async def _empty_caller(prompt: str):
        return ""

    sim.configure(llm_caller=_empty_caller)
    before = copy.deepcopy(sim.state.world)
    asyncio.run(sim.simulate_tick())
    _assert_world_unchanged(sim, before)
    assert sim.state.simulation_count == 0


def test_case2_invalid_json_world_unchanged():
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})

    async def _bad_json_caller(prompt: str):
        return "这不是 JSON {{{ 乱码"

    sim.configure(llm_caller=_bad_json_caller)
    before = copy.deepcopy(sim.state.world)
    asyncio.run(sim.simulate_tick())
    _assert_world_unchanged(sim, before)
    assert sim.state.simulation_count == 0


def test_case_world_mutates_on_successful_event():
    """正向回归：有效事件时 world.energy/phase/last_tick_at 应被提交。"""
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})
    sim.state.world.energy = 0.6
    sim.configure(llm_caller=_make_caller(
        {"activity": "看书", "thought": "", "mood": "calm",
         "wants_to_share": False, "urgency": 0.1}
    ))
    asyncio.run(sim.simulate_tick())
    assert sim.state.world.last_tick_at > 0          # commit 了
    assert sim.state.world.current_activity_id        # event_id 写入
    assert sim.state.world.phase in (
        "morning", "afternoon", "evening", "night", "sleep"
    )


def _make_caller(payload):
    async def _c(prompt: str):
        return json.dumps(payload)
    return _c


# ---------------------------------------------------------------------------
# case 3：直调真实 _prepare_memory_context，过期 pending 应 drop 不注入（HIGH2）
# （二审 LOW3：直调真实函数，不复制逻辑，防实现被改坏时测试一起假绿）
# ---------------------------------------------------------------------------
def test_case3_expired_pending_consumed_as_dropped():
    """直调 _prepare_memory_context，构造过期 pending → 期望 outreach_fragment 为空、
    事件标 dropped（非 consumed）。用 message_text="" + realtime_enabled=False
    绕开记忆召回重依赖，让 fake 只需最小 _store + life_sim。"""
    from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline
    from sylanne_alpha.session_state_store import SessionStateStore

    sim = LifeSimulator(config={})
    sim.state.events = [
        LifeEvent(text="过期事件", mood="m", urgency=0.2, timestamp=1.0,
                  wants_to_share=True, queued_at=1.0),
    ]
    eid = sim.state.events[0].event_id

    store = SessionStateStore()  # 真 store，含 pending_outreach_context/unfinished_replies

    class _FakePlugin:
        _life_simulator = sim
        _store = store
        config = {}
        _config = {}

    pipe = LLMRequestPipeline.__new__(LLMRequestPipeline)
    pipe._p = _FakePlugin()

    expired_ctx = {
        "reason": "过期事件", "mood": "m", "intent_id": "i1", "event_id": eid,
        "delivery_mode": "next_reply", "reason_code": "score_0.3",
        "expires_at": time.time() - 100.0,   # 已过期
        "target_session": "s1", "queued_at": 1.0,
    }
    pipe._p._store.pending_outreach_context.set("s1", expired_ctx)

    # 直调真实 _prepare_memory_context（message_text="" + realtime=False 绕记忆召回）
    unfinished, outreach_fragment, memory_fragment = asyncio.run(
        pipe._prepare_memory_context("s1", "", gap_seconds=0, realtime_enabled=False)
    )

    assert outreach_fragment == ""                       # 过期不注入
    assert sim.state.events[0].dropped_at > 0            # 标 dropped
    assert sim.state.events[0].consumed_at == 0          # 未误标 consumed


def test_case3b_fresh_pending_consumed_normally():
    """正向回归：未过期 pending 正常 consumed（直调真实函数）。"""
    from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline
    from sylanne_alpha.session_state_store import SessionStateStore

    sim = LifeSimulator(config={})
    sim.state.events = [
        LifeEvent(text="新鲜事件", mood="m", urgency=0.2, timestamp=1.0,
                  wants_to_share=True, queued_at=1.0),
    ]
    eid = sim.state.events[0].event_id
    store = SessionStateStore()

    class _FakePlugin:
        _life_simulator = sim
        _store = store
        config = {}
        _config = {}

    pipe = LLMRequestPipeline.__new__(LLMRequestPipeline)
    pipe._p = _FakePlugin()

    fresh_ctx = {
        "reason": "新鲜事件", "mood": "m", "intent_id": "i2", "event_id": eid,
        "delivery_mode": "next_reply", "reason_code": "score_0.3",
        "expires_at": time.time() + 1000.0,  # 未过期
        "target_session": "s1", "queued_at": 1.0,
    }
    pipe._p._store.pending_outreach_context.set("s1", fresh_ctx)

    _, outreach_fragment, _ = asyncio.run(
        pipe._prepare_memory_context("s1", "", gap_seconds=0, realtime_enabled=False)
    )
    assert outreach_fragment != ""                       # 注入了
    assert sim.state.events[0].consumed_at > 0           # consumed
    assert sim.state.events[0].dropped_at == 0            # 未 drop


# ---------------------------------------------------------------------------
# case 4：三参回调内部 TypeError 不退化重试、不推进状态（MED3）
# + 二审 MED1：异常不静默吞，记录 warning（可观测），但 outreach_count 不推进
# ---------------------------------------------------------------------------
def test_case4_internal_typeerror_no_retry_no_advance(caplog=None):
    """三参回调内部抛 TypeError：
    - 不退化二参重试（只调一次）
    - 不推进 outreach_count / last_outreach_time（失败回调不应假装成功）
    - 异常可观测（二审 MED1：不静默吞，记录 warning）
    """
    import logging
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})
    call_log = []

    async def _three_arg_callback(reason, mood, intent=None):
        call_log.append((reason, mood, intent))
        raise TypeError("内部 bug：比如某个 None.attr 访问")  # 真实 bug

    sim.configure(
        llm_caller=_make_caller(
            {"activity": "开心事", "thought": "", "mood": "happy",
             "wants_to_share": True, "urgency": 0.6}
        ),
        outreach_callback=_three_arg_callback,
    )
    outreach_count_before = sim.state.outreach_count
    last_before = sim.state.last_outreach_time

    # 捕获 warning 日志（二审 MED1：可观测）
    with caplog.at_level(logging.WARNING) if caplog else _NullCaplog():
        asyncio.run(sim.simulate_tick())

    assert len(call_log) == 1                             # 只调一次，不重试
    assert call_log[0][2] is not None                     # 三参调用
    assert sim.state.outreach_count == outreach_count_before  # 未推进
    assert sim.state.last_outreach_time == last_before    # 未推进


class _NullCaplog:
    """无 pytest caplog 时的 no-op context manager。"""
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def at_level(self, *a, **k): return self


def test_case4_warning_logged_on_callback_failure(caplog=None):
    """二审 MED1：outreach callback 失败时记录 warning（不静默吞，可观测）。"""
    import logging
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})

    async def _bad_callback(reason, mood, intent=None):
        raise RuntimeError("大饼挂了")

    sim.configure(
        llm_caller=_make_caller(
            {"activity": "开心事", "thought": "", "mood": "happy",
             "wants_to_share": True, "urgency": 0.6}
        ),
        outreach_callback=_bad_callback,
    )
    import io
    handler = logging.StreamHandler(io.StringIO())
    logger = logging.getLogger("sylanne_alpha.life_simulation")
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    try:
        asyncio.run(sim.simulate_tick())
        logs = handler.stream.getvalue()
        assert "outreach callback failed" in logs         # 可观测
    finally:
        logger.removeHandler(handler)


def test_case4b_two_arg_callback_still_supported():
    """两参回调仍被正确适配（inspect 判定 → 走两参路径）。"""
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})

    async def _two_arg_callback(reason, mood):  # 故意只收两参
        _two_arg_callback.last = (reason, mood)

    sim.configure(
        llm_caller=_make_caller(
            {"activity": "开心事", "thought": "", "mood": "happy",
             "wants_to_share": True, "urgency": 0.6}
        ),
        outreach_callback=_two_arg_callback,
    )
    asyncio.run(sim.simulate_tick())
    assert hasattr(_two_arg_callback, "last")
    assert _two_arg_callback.last[0]
