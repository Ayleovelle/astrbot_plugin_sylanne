"""CP8-P3a 多智能体基础设施单元测试。"""

import asyncio

from sylanne_alpha.agents import (
    LLM,
    SKIP,
    AgentIntent,
    CognitiveAgent,
    EventBus,
    ResponseObserved,
    SelfCore,
)


class _StubPlugin:
    """最小 plugin 桩，满足 SelfCore/agent 构造。"""

    def __init__(self):
        self.config = {}


# ---------------------------------------------------------------------------
# EventBus: fire-forget 广播
# ---------------------------------------------------------------------------
def test_eventbus_publish_delivers_to_subscribers():
    bus = EventBus()
    received = []
    bus.subscribe(ResponseObserved, lambda e: received.append(e.text))
    bus.publish(ResponseObserved(source="dialogue", session_key="s1", text="hi", confidence=0.8))
    assert received == ["hi"]


def test_eventbus_handler_exception_isolated():
    bus = EventBus()
    hits = []
    bus.subscribe(ResponseObserved, lambda e: (_ for _ in ()).throw(ValueError("boom")))
    bus.subscribe(ResponseObserved, lambda e: hits.append("ok"))
    # 第一个 handler 抛异常，不应阻断第二个，也不应冒泡
    bus.publish(ResponseObserved(source="x", session_key="s1"))
    assert hits == ["ok"]


# ---------------------------------------------------------------------------
# compose_inputs: 意图融合
# ---------------------------------------------------------------------------
def test_compose_filters_invalid_flags():
    sc = SelfCore(_StubPlugin())
    intents = [
        AgentIntent(source="emotion", flags=["hurt", "NOT_A_FLAG", "boundary"]),
    ]
    out = sc.compose_inputs(intents)
    assert "hurt" in out.flags and "boundary" in out.flags
    assert "NOT_A_FLAG" not in out.flags  # 非法 flag 被过滤


def test_compose_confidence_priority_weighted():
    sc = SelfCore(_StubPlugin())
    intents = [
        AgentIntent(source="a", confidence_hint=1.0, priority=1.0),
        AgentIntent(source="b", confidence_hint=0.0, priority=1.0),
    ]
    out = sc.compose_inputs(intents)
    assert abs(out.confidence - 0.5) < 1e-9  # 等权重→0.5


def test_compose_affect_dual_channel_and_group_heat():
    sc = SelfCore(_StubPlugin())
    intents = [
        AgentIntent(source="emotion", affect={"valence": 0.4}, priority=1.0, group_heat=1.2),
    ]
    out = sc.compose_inputs(intents)
    assert out.values.get("valence") == 0.4       # hot_pool 通道
    assert out.assessment.get("valence") == 0.4   # Void-Scar 通道
    assert out.values.get("group_heat") == 1.2


def test_compose_carries_high_level_payload():
    sc = SelfCore(_StubPlugin())
    intents = [AgentIntent(source="memory", payload={"recall": "初遇那天"})]
    out = sc.compose_inputs(intents)
    assert out.carried["memory"]["recall"] == "初遇那天"


def test_compose_empty_confidence_is_none():
    sc = SelfCore(_StubPlugin())
    out = sc.compose_inputs([AgentIntent(source="x")])
    assert out.confidence is None  # 无贡献→None，调用方用既有默认


# ---------------------------------------------------------------------------
# run_cycle + LLM 预算闸
# ---------------------------------------------------------------------------
class _GateAgent(CognitiveAgent):
    def __init__(self, plugin, bus, name, mode, intent_flags=None):
        super().__init__(plugin, bus)
        self.name = name
        self._mode = mode
        self._flags = intent_flags or []

    def gate(self, perceived):
        return self._mode

    async def act(self, session_key, mode, perceived, phase="post"):
        return AgentIntent(source=self.name, flags=self._flags)


def test_run_cycle_skips_skip_agents():
    sc = SelfCore(_StubPlugin())
    sc.register(_GateAgent(sc._p, sc.bus, "emotion", LLM, ["hurt"]))
    sc.register(_GateAgent(sc._p, sc.bus, "idle_one", SKIP))
    intents = asyncio.run(sc.run_cycle("s1", {}))
    sources = {i.source for i in intents}
    assert sources == {"emotion"}  # SKIP 的不产意图


def test_llm_budget_downgrades_low_priority():
    sc = SelfCore(_StubPlugin(), llm_budget=1)
    # 两个都想要 LLM 档，预算只 1：dialogue 优先级高于 memory，memory 被降级
    sc.register(_GateAgent(sc._p, sc.bus, "memory", LLM))
    sc.register(_GateAgent(sc._p, sc.bus, "dialogue", LLM))
    # act 仍会跑（降级只改 mode，不取消），两者都产意图
    intents = asyncio.run(sc.run_cycle("s1", {}))
    assert {i.source for i in intents} == {"memory", "dialogue"}
