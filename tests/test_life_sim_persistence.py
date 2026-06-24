"""PR-A6：LifeSimulator 持久化与零副作用单元测试。

覆盖 Phase 0 契约（H4 修复 + L17 修复 + L13 清理）：
- provider 未配置时零副作用（不调 LLM、不改状态）。
- to_dict/from_dict 往返一致（含 events）。
- state_dirty_callback 在 tick 末尾被触发（PR-A5 节流落盘钩子）。
- memory_summary_getter 回调被 _build_prompt 消费（L17 修复）。
- _pending_emotion_delta 死字段已移除（L13 清理）。

不依赖真实 LLM：用 fake caller 返回固定 JSON。
"""

import asyncio
import json

from sylanne_alpha.life_simulation import (
    LifeEvent,
    LifePlan,
    LifePrivacy,
    LifeSimulationState,
    LifeSimulator,
    LifeSource,
    LifeWorldState,
)


# ---------------------------------------------------------------------------
# 辅助：fake LLM caller
# ---------------------------------------------------------------------------
def _fake_llm_returning(payload: dict):
    """返回一个 async caller，固定返回 payload 的 JSON。"""

    async def _caller(prompt: str) -> str:
        _caller.last_prompt = prompt  # 供测试检视
        return json.dumps(payload)

    _caller.last_prompt = ""
    return _caller


# ---------------------------------------------------------------------------
# 契约：provider 未配置 / enabled=False 时零副作用
# ---------------------------------------------------------------------------
def test_disabled_simulator_is_noop():
    sim = LifeSimulator(config={})  # enabled 默认 False
    assert sim.enabled is False
    events_before = list(sim.state.events)
    asyncio.run(sim.simulate_tick())
    assert sim.state.events == events_before
    assert sim.state.simulation_count == 0  # 未 bump


def test_enabled_but_no_llm_caller_is_noop():
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})
    assert sim.enabled is True
    # configure 不传 llm_caller（None）→ simulate_tick 应在 provider 检查处返回
    sim.configure()
    count_before = sim.state.simulation_count
    asyncio.run(sim.simulate_tick())
    assert sim.state.simulation_count == count_before
    assert sim.state.events == []


def test_configured_caller_returning_empty_is_noop():
    """真实集成路径：main.py 总会注入 _life_sim_llm_call，而它在 provider_id
    为空时返回空串。此路径下必须零副作用（不 bump 计数/时间，不产 event，
    不触发 dirty save，不拨动 countdown——后者会改写大饼主动发言调度）。
    覆盖 PR-A review HIGH + 二审 HIGH。"""
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})

    async def _empty_caller(prompt: str):
        return ""  # 模拟 provider 未配置时的返回

    dirty_calls = []
    countdown_calls = []

    async def _dirty_cb():
        dirty_calls.append(True)

    async def _countdown_cb():
        countdown_calls.append(True)

    sim.configure(
        llm_caller=_empty_caller,
        state_dirty_callback=_dirty_cb,
        countdown_callback=_countdown_cb,
    )
    count_before = sim.state.simulation_count
    last_before = sim.state.last_simulation_time
    asyncio.run(sim.simulate_tick())
    assert sim.state.simulation_count == count_before      # 不 bump
    assert sim.state.last_simulation_time == last_before   # 不 bump
    assert sim.state.events == []                           # 不产 event
    assert dirty_calls == []                                # 不触发持久化
    assert countdown_calls == []                            # 二审：不拨动倒计时


def test_configured_caller_invalid_json_is_noop():
    """LLM 返回无法解析的文本（invalid JSON）→ _parse_response 返回 None。
    此路径同样必须零副作用（不 bump、不 event、不 dirty、不 countdown）。
    覆盖二审 HIGH 的解析失败分支。"""
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})

    async def _bad_json_caller(prompt: str):
        return "这不是 JSON，解析会失败 {{{ 乱码"  # _parse_response 找不到合法 JSON

    dirty_calls = []
    countdown_calls = []

    async def _dirty_cb():
        dirty_calls.append(True)

    async def _countdown_cb():
        countdown_calls.append(True)

    sim.configure(
        llm_caller=_bad_json_caller,
        state_dirty_callback=_dirty_cb,
        countdown_callback=_countdown_cb,
    )
    count_before = sim.state.simulation_count
    asyncio.run(sim.simulate_tick())
    assert sim.state.simulation_count == count_before
    assert sim.state.events == []
    assert dirty_calls == []
    assert countdown_calls == []


def test_disabled_simulator_with_llm_caller_is_noop():
    """enabled=False 防线（即使 caller 被注入）。"""
    sim = LifeSimulator(config={})  # enabled 默认 False
    calls = []

    async def _caller(prompt: str):
        calls.append(prompt)
        return "{}"

    async def _countdown_cb():
        calls.append("countdown")

    sim.configure(llm_caller=_caller, countdown_callback=_countdown_cb)
    asyncio.run(sim.simulate_tick())
    assert calls == []                                     # 根本不调 LLM，也不拨 countdown
    assert sim.state.simulation_count == 0


def test_countdown_fires_on_successful_event():
    """正向路径：产生有效事件时，countdown 与 dirty 都应触发（门控正确性回归）。"""
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})

    async def _good_caller(prompt: str):
        import json as _json
        return _json.dumps(
            {"activity": "看书", "thought": "", "mood": "calm",
             "wants_to_share": False, "urgency": 0.1}
        )

    dirty_calls = []
    countdown_calls = []

    async def _dirty_cb():
        dirty_calls.append(True)

    async def _countdown_cb():
        countdown_calls.append(True)

    sim.configure(
        llm_caller=_good_caller,
        state_dirty_callback=_dirty_cb,
        countdown_callback=_countdown_cb,
    )
    asyncio.run(sim.simulate_tick())
    assert len(sim.state.events) == 1                       # 有效事件已产
    assert sim.state.simulation_count == 1
    assert len(countdown_calls) == 1                       # body 演化后拨动
    assert len(dirty_calls) == 1                           # 状态真变脏 → 落盘


# ---------------------------------------------------------------------------
# 契约：to_dict / from_dict 往返一致（H4 节流落盘的基础）
# ---------------------------------------------------------------------------
def test_state_roundtrip_preserves_events_and_activity():
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})
    sim.state.current_activity = "整理 shader 笔记"
    sim.state.last_simulation_time = 1000.0
    sim.state.simulation_count = 7
    sim.state.events = [
        LifeEvent(text="读书", mood="calm", urgency=0.1, timestamp=900.0,
                  wants_to_share=False, shared=False, event_type="reading"),
        LifeEvent(text="散步", mood="fresh", urgency=0.2, timestamp=950.0,
                  wants_to_share=True, shared=False, event_type="walking"),
    ]

    data = sim.to_dict()
    sim2 = LifeSimulator(config={})
    sim2.from_dict(data)

    assert sim2.state.current_activity == "整理 shader 笔记"
    assert sim2.state.last_simulation_time == 1000.0
    assert sim2.state.simulation_count == 7
    assert len(sim2.state.events) == 2
    assert sim2.state.events[0].text == "读书"
    assert sim2.state.events[1].wants_to_share is True
    # PR-B2 修复：to_dict/from_dict 现完整保存 event_type（v1 缺陷已修）
    assert sim2.state.events[0].event_type == "reading"
    assert sim2.state.events[1].event_type == "walking"


def test_legacy_archive_migration_marks_source_and_defaults():
    """PR-B2 迁移契约：读 v1 旧档（无 V2 字段）时，事件补 source=LEGACY、
    confidence=0.5、privacy_level=INTERNAL；world/plan 兜底默认。"""
    legacy_data = {
        # 无 schema_version，无 world/plan，事件只有 v1 字段
        "events": [
            {"text": "旧事件", "mood": "ok", "urgency": 0.2, "timestamp": 100.0,
             "wants_to_share": False, "shared": False},
        ],
        "current_activity": "旧的",
        "last_simulation_time": 100.0,
        "simulation_count": 3,
        "outreach_count": 1,
    }
    state = LifeSimulationState.from_dict(legacy_data)
    assert len(state.events) == 1
    ev = state.events[0]
    assert ev.source == LifeSource.LEGACY
    assert ev.confidence == 0.5
    assert ev.privacy_level == LifePrivacy.INTERNAL
    assert ev.event_id  # 迁移补了 id
    # world/plan 旧档兜底
    assert isinstance(state.world, LifeWorldState)
    assert state.plan is None


def test_v2_fields_roundtrip():
    """V2 增量字段经 to_dict/from_dict 完整保留。"""
    from sylanne_alpha.life_simulation import LifeWorldState, LifePlan
    sim = LifeSimulator(config={})
    sim.state.world = LifeWorldState(
        phase="evening", energy=0.3, focus=0.7, local_date="2026-06-18",
        current_activity_id="act1", last_tick_at=1234.0,
    )
    sim.state.plan = LifePlan(date="2026-06-18", confidence=0.6)
    sim.state.events = [
        LifeEvent(
            text="写 shader", mood="focused", urgency=0.4, timestamp=1234.0,
            event_type="creating", source="planned_tick", importance=0.8,
            confidence=0.9, privacy_level="shareable", activity_id="act1",
            caused_by=["prev1"], followups=["next1"], queued_at=1234.0,
        )
    ]
    data = sim.to_dict()
    sim2 = LifeSimulator(config={})
    sim2.from_dict(data)

    assert sim2.state.world.phase == "evening"
    assert sim2.state.world.energy == 0.3
    assert sim2.state.world.current_activity_id == "act1"
    assert sim2.state.plan is not None
    assert sim2.state.plan.confidence == 0.6
    ev = sim2.state.events[0]
    assert ev.source == "planned_tick"
    assert ev.importance == 0.8
    assert ev.confidence == 0.9
    assert ev.privacy_level == "shareable"
    assert ev.activity_id == "act1"
    assert ev.caused_by == ["prev1"]
    assert ev.queued_at == 1234.0


def test_state_roundtrip_truncates_to_recent_20():
    """to_dict 仅保留最近 20 个事件（基线契约，迁移时不能破坏）。"""
    sim = LifeSimulator(config={})
    sim.state.events = [
        LifeEvent(text=f"evt{i}", mood="m", urgency=0.0, timestamp=float(i))
        for i in range(30)
    ]
    data = sim.to_dict()
    assert len(data["events"]) == 20
    # 保留的是最后 20 个
    assert data["events"][0]["text"] == "evt10"
    assert data["events"][-1]["text"] == "evt29"


# ---------------------------------------------------------------------------
# 契约：state_dirty_callback 在 tick 末尾触发（PR-A5）
# ---------------------------------------------------------------------------
def test_state_dirty_callback_fires_after_tick():
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})
    fired = []

    async def _dirty_cb():
        fired.append(time_now())

    async def _noop_countdown():
        pass

    sim.configure(
        llm_caller=_fake_llm_returning(
            {"activity": "看书", "thought": "shader", "mood": "calm",
             "wants_to_share": False, "urgency": 0.1}
        ),
        countdown_callback=_noop_countdown,
        state_dirty_callback=_dirty_cb,
    )
    asyncio.run(sim.simulate_tick())
    # tick 成功产生事件后，dirty callback 应被触发一次
    assert len(fired) == 1
    assert len(sim.state.events) == 1


def test_state_dirty_callback_failure_does_not_break_tick():
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})

    async def _bad_dirty_cb():
        raise RuntimeError("kv down")

    async def _noop_countdown():
        pass

    sim.configure(
        llm_caller=_fake_llm_returning(
            {"activity": "看书", "thought": "", "mood": "calm",
             "wants_to_share": False, "urgency": 0.1}
        ),
        countdown_callback=_noop_countdown,
        state_dirty_callback=_bad_dirty_cb,
    )
    # dirty callback 抛异常不应阻断 tick（事件应仍写入）
    asyncio.run(sim.simulate_tick())
    assert len(sim.state.events) == 1


# ---------------------------------------------------------------------------
# 契约：memory_summary_getter 被 _build_prompt 消费（L17 修复）
# ---------------------------------------------------------------------------
def test_memory_summary_getter_is_consumed_by_build_prompt():
    sim = LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})

    def _mem_getter():
        return "用户最近在聊毕业设计"

    sim.configure(
        llm_caller=_fake_llm_returning(
            {"activity": "看书", "thought": "", "mood": "calm",
             "wants_to_share": False, "urgency": 0.1}
        ),
        memory_summary_getter=_mem_getter,
    )
    prompt = sim._build_prompt(now=1700000000.0)
    assert "毕业设计" in prompt


# ---------------------------------------------------------------------------
# 契约：_pending_emotion_delta 死字段已移除（L13 清理）
# ---------------------------------------------------------------------------
def test_pending_emotion_delta_field_removed():
    assert not hasattr(LifeSimulationState(), "_pending_emotion_delta")
    # 序列化结果也不含该字段
    sim = LifeSimulator(config={})
    assert "_pending_emotion_delta" not in sim.to_dict()


# ---------------------------------------------------------------------------
# Pipeline 级接线：_life_sim_memory_summary 从最近活跃 host 取 memory
# （PR-A review §2：原测试只覆盖直接注入 fake getter，未覆盖真实 pipeline 路径）
# ---------------------------------------------------------------------------
class _FakeMemorySystem:
    def __init__(self, findings):
        self._findings = findings

    def get_recent_findings(self, n: int = 5):
        return self._findings[:n]


class _FakeHost:
    def __init__(self, last_now: float):
        self.kernel = type(
            "K",
            (),
            {"last_event": {"now": last_now}},
        )()


class _FakeStore:
    def __init__(self, hosts):
        self.hosts = hosts  # dict-like


class _FakePlugin:
    def __init__(self, hosts, mem_sys):
        self._store = _FakeStore(hosts)
        self._mem_sys = mem_sys

    def _memory_system_for_session(self, session_key):
        return self._mem_sys


def test_pipeline_memory_summary_extracts_recent_findings():
    """验证 _life_sim_memory_summary 真实从最近活跃 host 的 memory_system 取摘要。"""
    from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline

    hosts = {"sess_a": _FakeHost(last_now=1000.0)}
    mem = _FakeMemorySystem(
        findings=[
            {"text": "用户在聊毕业设计"},
            {"text": "提到了 shader 实验"},
            {"text": ""},
            {"text": "这条超出 n=3 不应出现"},
        ]
    )
    plugin = _FakePlugin(hosts=hosts, mem_sys=mem)
    pipe = LLMRequestPipeline.__new__(LLMRequestPipeline)
    pipe._p = plugin

    summary = pipe._life_sim_memory_summary()
    assert "毕业设计" in summary
    assert "shader" in summary
    assert "不应出现" not in summary  # n=3 截断
    assert summary.count("；") == 1    # 两条有效，一个分隔符


def test_pipeline_memory_summary_no_hosts_returns_empty():
    from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline

    plugin = _FakePlugin(hosts={}, mem_sys=_FakeMemorySystem(findings=[]))
    pipe = LLMRequestPipeline.__new__(LLMRequestPipeline)
    pipe._p = plugin

    assert pipe._life_sim_memory_summary() == ""


def test_pipeline_memory_summary_exception_returns_empty():
    """memory_system_for_session 抛异常时降级为空串，不阻断 life sim。"""
    from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline

    class _BrokenPlugin:
        class _store:
            hosts = {"s1": _FakeHost(last_now=1.0)}

        def _memory_system_for_session(self, sk):
            raise RuntimeError("db down")

    pipe = LLMRequestPipeline.__new__(LLMRequestPipeline)
    pipe._p = _BrokenPlugin()
    assert pipe._life_sim_memory_summary() == ""


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------
def time_now():
    import time
    return time.time()
