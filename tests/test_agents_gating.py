"""CP8-P3a 9 个认知 agent 的 perceive/gate 单元测试。

纯逻辑验证（不接主流程）：构造 surface，验证各 agent 的门控档位判定。
"""

from sylanne_alpha.agents import (
    LLM,
    RULE,
    SKIP,
    AssessorAgent,
    DialogueAgent,
    EmotionAgent,
    MemoryAgent,
    PersonaAgent,
    ProactiveAgent,
    RhythmAgent,
)
from sylanne_alpha.agents.event_bus import EventBus


class _StubStore:
    class _M:
        def __init__(self): self._d = {}
        def get(self, k, d=None): return self._d.get(k, d)
        def set(self, k, v): self._d[k] = v
    def __init__(self):
        self.last_user_texts = self._M()
        self.last_bot_texts = self._M()
        self.hosts = self._M()


class _StubPlugin:
    def __init__(self):
        self.config = {}
        self._store = _StubStore()


def _surface(*, valence=0.0, arousal=0.0, tension=0.0, boundary_pressure=0.0,
             coherence=1.0, intimacy_gravity=0.5, sovereignty_guard=0.5, edge=0.5,
             need_expression=0.0, action="express", allowed=True,
             expression_drive=0.0, repair_pressure=0.0, plasticity=0.0):
    return {
        "host_payload": {
            "personality": {
                "traits": {
                    "intimacy_gravity": intimacy_gravity,
                    "sovereignty_guard": sovereignty_guard,
                    "edge": edge,
                },
                "drift": {"plasticity": plasticity},
            },
            "affect_dynamics": {
                "computation_emotion": {
                    "valence": valence, "arousal": arousal, "tension": tension,
                    "coherence": coherence, "expression_drive": expression_drive,
                    "repair_pressure": repair_pressure, "warmth": 0.5,
                },
            },
        },
        "body": {
            "needs": {"need_expression": need_expression},
            "immunity": {"boundary_pressure": boundary_pressure},
        },
        "decision": {"action": action, "confidence": 0.8},
        "guard": {"allowed": allowed},
    }


def _mk(cls):
    return cls(_StubPlugin(), EventBus())


# ── EmotionAgent ──
def test_emotion_boundary_high_triggers_llm():
    a = _mk(EmotionAgent)
    assert a.gate(a.perceive(_surface(boundary_pressure=0.95, sovereignty_guard=0.2))) == LLM


def test_emotion_flat_skips():
    a = _mk(EmotionAgent)
    assert a.gate(a.perceive(_surface(valence=0.05, arousal=0.05, tension=0.05))) == SKIP


def test_emotion_strong_valence_llm():
    a = _mk(EmotionAgent)
    assert a.gate(a.perceive(_surface(valence=-0.8))) == LLM


# ── MemoryAgent ──
def test_memory_gate_always_rule_for_post_decay():
    # CP8-P6：MemoryAgent gate 恒 RULE，避免误杀 POST 的 tick_decay（必跑维护）。
    a = _mk(MemoryAgent)
    assert a.gate(a.perceive(_surface(intimacy_gravity=0.1))) == RULE
    assert a.gate(a.perceive(_surface(intimacy_gravity=0.8, repair_pressure=0.8))) == RULE


def test_memory_shallow_intimacy_pre_recall_skipped():
    # 浅关系：gate 仍放行（为 POST 衰减），但 PRE 召回在 act 内被亲密度阈值挡掉。
    import asyncio
    a = _mk(MemoryAgent)
    perceived = a.perceive(_surface(intimacy_gravity=0.1))
    perceived["_evo_delta"] = lambda k: 0.0
    a._p._store.last_user_texts.set("s", "想起一件事")
    from sylanne_alpha.agents.base import PRE
    out = asyncio.run(a.act("s", RULE, perceived, phase=PRE))
    assert out is None  # 浅关系不主动翻记忆


# ── PersonaAgent ──
def test_persona_low_coherence_llm():
    a = _mk(PersonaAgent)
    assert a.gate(a.perceive(_surface(coherence=0.3))) == LLM


def test_persona_stable_skips():
    a = _mk(PersonaAgent)
    assert a.gate(a.perceive(_surface(coherence=0.9, plasticity=0.1))) == SKIP


# ── ProactiveAgent ──
def test_proactive_guard_blocks():
    a = _mk(ProactiveAgent)
    assert a.gate(a.perceive(_surface(allowed=False))) == SKIP


def test_proactive_wait_action_skips():
    a = _mk(ProactiveAgent)
    assert a.gate(a.perceive(_surface(action="wait"))) == SKIP


def test_proactive_high_expression_rule():
    a = _mk(ProactiveAgent)
    got = a.gate(a.perceive(_surface(
        action="reach_out", need_expression=0.9, boundary_pressure=0.1,
        sovereignty_guard=0.3, intimacy_gravity=0.7,
    )))
    assert got == RULE


# ── DialogueAgent ──
def test_dialogue_wait_skips():
    a = _mk(DialogueAgent)
    assert a.gate(a.perceive(_surface(action="wait"))) == SKIP


def test_dialogue_express_llm():
    a = _mk(DialogueAgent)
    assert a.gate(a.perceive(_surface(action="express", allowed=True))) == LLM


# ── RhythmAgent / AssessorAgent（恒 RULE/LLM）──
def test_rhythm_always_rule():
    a = _mk(RhythmAgent)
    assert a.gate(a.perceive(_surface())) == RULE


def test_assessor_always_llm():
    a = _mk(AssessorAgent)
    assert a.gate(a.perceive(_surface())) == LLM
