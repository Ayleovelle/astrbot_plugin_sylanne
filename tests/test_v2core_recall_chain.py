"""v2core 第一条主链端到端测试：用户消息 → 召回。

覆盖 BodyPort 提炼、MemoryDomain 领域边界、RecallCapability 能力、SelfCore 三拍编排，
并与旧 MemorySystem.recall 做 oracle 对照（绞杀式：新链路结果须与旧实现一致）。
"""

from __future__ import annotations

import asyncio
import time

from sylanne_alpha.memory_system import MemorySystem, RecallMode
from sylanne_alpha.v2core.body_port_v2 import snapshot_from_surface
from sylanne_alpha.v2core.capabilities.recall import RecallCapability
from sylanne_alpha.v2core.contracts import BodySnapshot, Phase
from sylanne_alpha.v2core.domains.memory import MemoryDomain
from sylanne_alpha.v2core.self_core import SelfCore


def _run(coro):
    return asyncio.run(coro)


# --- BodyPort 提炼 --------------------------------------------------------

def test_snapshot_from_surface_extracts_fields():
    surface = {
        "session_key": "u1",
        "turns": 7,
        "host_payload": {
            "affect_dynamics": {"computation_emotion": {"warmth": 0.6, "repair_pressure": 0.3}},
            "personality": {"traits": {"intimacy_gravity": 0.7, "perception_acuity": 0.9}},
            "integrated_self": {"state_index": {"risk": 0.2, "boundary_need": 0.1}},
        },
    }
    snap = snapshot_from_surface(surface, "fallback")
    assert snap.session_key == "u1"
    assert snap.turns == 7
    assert snap.warmth == 0.6
    assert snap.repair_pressure == 0.3
    assert snap.intimacy_gravity == 0.7
    assert snap.trait("perception_acuity") == 0.9


def test_snapshot_from_surface_robust_to_missing():
    """surface 残缺不崩，给中性默认。"""
    snap = snapshot_from_surface({}, "u2")
    assert snap.session_key == "u2"
    assert snap.warmth == 0.0
    assert snap.intimacy_gravity == 0.5  # relationship_signal_weight 缺省


def test_snapshot_clamps():
    surface = {"host_payload": {"affect_dynamics": {"computation_emotion": {"warmth": 5.0}}}}
    snap = snapshot_from_surface(surface, "u")
    assert snap.warmth == 1.0  # clamp


# --- MemoryDomain 领域边界 ------------------------------------------------

def _seeded_domain() -> MemoryDomain:
    ms = MemorySystem()
    ms.write_summary("我们聊过去日本旅行的计划", source_turns=2, temperature=0.4)
    ms.write_summary("你说你喜欢喝拿铁", source_turns=1, temperature=0.5)
    return MemoryDomain(ms)


def test_memory_domain_recall_returns_plain_dicts():
    dom = _seeded_domain()
    out = dom.recall("旅行", warmth=0.3, limit=3)
    assert isinstance(out, list)
    assert all(isinstance(x, dict) and "text" in x for x in out)


def test_memory_domain_intimacy_gate():
    dom = _seeded_domain()
    low = BodySnapshot(session_key="s", turns=1, intimacy_gravity=0.1)
    high = BodySnapshot(session_key="s", turns=1, intimacy_gravity=0.8)
    assert dom.intimacy_ok(low) is False
    assert dom.intimacy_ok(high) is True


def test_memory_domain_roundtrip_preserves_state():
    dom = _seeded_domain()
    data = dom.to_dict()
    ms2 = MemorySystem()
    dom2 = MemoryDomain(ms2)
    dom2.load_dict(data)
    assert len(dom2.system._l1) == len(dom.system._l1)


# --- 端到端主链 + oracle 对照 --------------------------------------------

class FakeBody:
    def __init__(self, snap):
        self._snap = snap
    def observe(self):
        return self._snap
    def tick(self, event, assessment=None):
        return self._snap
    def snapshot(self):
        return {}


def test_recall_chain_end_to_end():
    """SelfCore 跑一轮 → RecallCapability 经 MemoryDomain 召回 → Intent 落在 ctx。"""
    dom = _seeded_domain()
    body = FakeBody(BodySnapshot(session_key="u", turns=1, warmth=0.3, intimacy_gravity=0.8))
    sc = SelfCore(body)
    sc.register(RecallCapability())

    ctx = _run(sc.turn("u", object(), "旅行", domains={"memory": dom}))
    recall_intents = [i for i in ctx.intents if i.source == "recall"]
    assert recall_intents, "应产出召回意图"
    assert recall_intents[0].payload["recalled"]
    assert "recalled_deliberate" in ctx.scratch


def test_recall_chain_blocked_by_low_intimacy():
    """关系不够亲密 → 不召回（门控生效）。"""
    dom = _seeded_domain()
    body = FakeBody(BodySnapshot(session_key="u", turns=1, intimacy_gravity=0.1))
    sc = SelfCore(body)
    sc.register(RecallCapability())
    ctx = _run(sc.turn("u", object(), "旅行", domains={"memory": dom}))
    assert not [i for i in ctx.intents if i.source == "recall"]


def test_recall_chain_matches_oracle():
    """绞杀 oracle 对照：新链路召回的文本 == 旧 MemorySystem.recall 直调结果。"""
    # 同样 seed 两个独立系统
    def seed():
        ms = MemorySystem()
        ms.write_summary("我们聊过去日本旅行的计划", source_turns=2, temperature=0.4)
        ms.write_summary("你说你喜欢喝拿铁", source_turns=1, temperature=0.5)
        return ms

    oracle_ms = seed()
    oracle = [r.text for r in oracle_ms.recall("旅行", None, 0.3, limit=3)]

    new_ms = seed()
    dom = MemoryDomain(new_ms)
    body = FakeBody(BodySnapshot(session_key="u", turns=1, warmth=0.3, intimacy_gravity=0.8))
    sc = SelfCore(body)
    sc.register(RecallCapability())
    ctx = _run(sc.turn("u", object(), "旅行", domains={"memory": dom}))
    new_texts = [m["text"] for m in ctx.scratch.get("recalled_deliberate", [])]

    assert new_texts == oracle, f"新链路 {new_texts} 应与 oracle {oracle} 一致"


# --- 情感旁路 v2core 择点过滤（PRIME a：flood 修复）------------------------

def test_domain_recall_drops_low_relevance_emotion_bypass():
    """ACTIVATION 模式下，emotion_bypass 补回的 rel≈0 强情绪项在 MemoryDomain.recall
    这个唯一 v2core choke 点被过滤掉（防高 warmth 场景每轮打断话题）；同一份记忆用
    MemorySystem.recall 直调（legacy/直连路径）时仍原样含情感旁路项——不动其本身。
    """
    ms = MemorySystem(recall_mode=RecallMode.ACTIVATION)
    now = time.time()
    sad = ms.write_summary(
        "那天你说工作压力很大很难过", source_turns=3,
        temperature=-0.8, importance=0.8,
    )
    sad.created_at = now - 3600 * 24 * 30
    sad.last_recalled_ts = 0.0
    sad.actr_acc = 1.0

    # oracle：MemorySystem.recall 直连（v2core 之外的路径）——情感旁路项仍在。
    oracle = ms.recall("随便聊聊", current_warmth=-0.6, limit=5)
    oracle_texts = [r.text for r in oracle]
    assert any("工作压力" in t for t in oracle_texts), (
        "直连 MemorySystem.recall 的情感旁路行为不应被本次修复改变"
    )
    bypassed = [r for r in oracle if r.recall_reason == "emotion_bypass"]
    assert bypassed and bypassed[0].relevance < 0.15

    # MemoryDomain.recall：v2core 唯一 choke 点——同一召回应把低相关的情感旁路项丢弃。
    dom = MemoryDomain(ms)
    out = dom.recall("随便聊聊", warmth=-0.6, limit=5)
    out_texts = [r["text"] for r in out]
    assert not any("工作压力" in t for t in out_texts), (
        "MemoryDomain.recall 应过滤掉 relevance<0.15 的 emotion_bypass 项"
    )


def test_domain_recall_keeps_relevant_emotion_bypass():
    """情感旁路项若本身语义也相关（relevance>=0.15），MemoryDomain.recall 不应误删。"""
    ms = MemorySystem(recall_mode=RecallMode.ACTIVATION)
    now = time.time()
    sad = ms.write_summary(
        "工作压力很大让人很难过", source_turns=3,
        temperature=-0.8, importance=0.8,
    )
    sad.created_at = now - 3600 * 24 * 30
    sad.last_recalled_ts = 0.0
    sad.actr_acc = 1.0

    dom = MemoryDomain(ms)
    # 查询词与记忆文本有实义词重合 → relevance 应 >= 0.15，不应被当成低相关旁路丢弃。
    out = dom.recall("最近工作压力好大", warmth=-0.6, limit=5)
    out_texts = [r["text"] for r in out]
    assert any("工作压力" in t for t in out_texts)


def test_tick_decay_via_domain():
    """记忆衰减经领域接口（写操作）。"""
    dom = _seeded_domain()
    before = dom.system._tick
    dom.tick_decay()
    assert dom.system._tick == before + 1
