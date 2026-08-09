"""阶段0 地基回归测试。

验证 ACT-R 重设计的地基改动「零行为变化」且可安全迭代：
- 新字段（actr_acc / GraphEdge.strength / MemoryResult.confidence 等）序列化往返。
- 旧存档（无新字段）回填出合理默认值，不崩溃。
- 灰度开关 RecallMode：LEGACY 行为与原 recall 一致；ACTIVATION 未实现时安全回退；
  SHADOW 返回 LEGACY 结果且不抛异常。
- get_debug_snapshot 只读快照可用。
"""

from __future__ import annotations

import time

from sylanne_alpha.memory_system import (
    GraphEdge,
    GraphNode,
    MemoryItem,
    MemoryResult,
    MemorySystem,
    RecallMode,
)


# ---------------------------------------------------------------------------
# 新字段序列化往返
# ---------------------------------------------------------------------------

def test_memoryitem_actr_acc_roundtrip():
    item = MemoryItem(
        id="x", text="t", weight=1.0, temperature=0.0, age_ticks=0,
        embedding=None, created_at=time.time(), actr_acc=3.7,
    )
    restored = MemoryItem.from_dict(item.to_dict())
    assert restored.actr_acc == 3.7


def test_memoryitem_legacy_archive_backfills_actr_acc():
    """旧存档无 actr_acc → 回填 1.0（中性激活）。"""
    legacy = {
        "id": "x", "text": "t", "weight": 1.0, "temperature": 0.0,
        "age_ticks": 0, "created_at": time.time(),
    }
    item = MemoryItem.from_dict(legacy)
    assert item.actr_acc == 1.0


def test_graphnode_actr_acc_roundtrip():
    node = GraphNode(
        id="n", label="猫", type="preference", temporal_type="permanent",
        emotion_weight=0.5, clarity=0.9, actr_acc=2.1,
    )
    assert GraphNode.from_dict(node.to_dict()).actr_acc == 2.1


def test_graphedge_strength_roundtrip():
    edge = GraphEdge(
        source="a", target="b", relation="喜欢",
        emotion_weight=0.8, clarity=0.9, strength=0.75,
    )
    assert GraphEdge.from_dict(edge.to_dict()).strength == 0.75


def test_graphedge_legacy_strength_backfill():
    """旧存档无 strength → 用 clarity*|emotion| 近似回填，clamp [0,1]。"""
    legacy = {
        "source": "a", "target": "b", "relation": "是",
        "emotion_weight": 0.5, "clarity": 0.8,
    }
    edge = GraphEdge.from_dict(legacy)
    assert edge.strength == 0.8 * 0.5  # 0.4


def test_memoryresult_observability_defaults():
    r = MemoryResult(
        text="t", layer="L1", weight=1.0, relevance=0.5, clarity=1.0,
        temperature=0.0, final_score=0.5, created_at=time.time(),
    )
    assert r.confidence == "clear"
    assert r.activation == 0.0
    assert r.debug == {}


def test_full_system_roundtrip_with_new_fields():
    """整系统 to_dict/from_dict 往返保留新字段。"""
    sys = MemorySystem()
    item = sys.write_summary("我喜欢猫", source_turns=2, temperature=0.6)
    item.actr_acc = 4.2
    sys.ingest_graph_triples([("猫", "是", "宠物", 0.8, 0.9)])

    restored = MemorySystem.create_from_dict(sys.to_dict())
    l1_item = next(it for it in restored._l1 if it.text == "我喜欢猫")
    assert l1_item.actr_acc == 4.2
    assert all(hasattr(e, "strength") for e in restored._l3_edges)


# ---------------------------------------------------------------------------
# 灰度开关
# ---------------------------------------------------------------------------

def _seed(sys: MemorySystem) -> None:
    sys.write_summary("我们昨天聊到了旅行计划", source_turns=2, temperature=0.4)
    sys.write_summary("你说你喜欢喝拿铁", source_turns=1, temperature=0.5)


def test_default_mode_is_legacy():
    assert MemorySystem()._recall_mode is RecallMode.LEGACY


def test_explicit_mode_via_kwarg():
    assert MemorySystem(recall_mode=RecallMode.SHADOW)._recall_mode is RecallMode.SHADOW
    assert MemorySystem(recall_mode="activation")._recall_mode is RecallMode.ACTIVATION


def test_invalid_mode_falls_back_to_legacy():
    assert MemorySystem(recall_mode="nonsense")._recall_mode is RecallMode.LEGACY


def test_legacy_dispatch_matches_direct_legacy():
    """recall()（LEGACY）与直接调 _recall_legacy 结果一致。"""
    sys = MemorySystem()
    _seed(sys)
    via_dispatch = sys.recall("旅行", limit=5)
    sys2 = MemorySystem()
    _seed(sys2)
    direct = sys2._recall_legacy("旅行", None, 0.0, 5)
    assert [r.text for r in via_dispatch] == [r.text for r in direct]


def test_activation_dispatch_routes_to_activation_engine():
    """ACTIVATION 模式应走 _recall_activation（阶段1 已实现）。

    通过 activation 字段被填充来确认走的是激活引擎而非 LEGACY
    （LEGACY 不设 MemoryResult.activation，保持默认 0.0）。
    """
    sys = MemorySystem(recall_mode=RecallMode.ACTIVATION)
    _seed(sys)
    assert hasattr(sys, "_recall_activation")
    results = sys.recall("拿铁", limit=5)
    assert results, "应有召回结果"
    assert any(r.activation > 0.0 for r in results), "ACTIVATION 引擎应填充 activation 字段"


def test_shadow_mode_returns_legacy_and_never_raises():
    """SHADOW 模式返回 LEGACY 结果；即使新引擎缺失也不抛异常。"""
    sys = MemorySystem(recall_mode=RecallMode.SHADOW)
    _seed(sys)
    results = sys.recall("旅行", limit=5)  # 不应抛
    legacy = MemorySystem()
    _seed(legacy)
    assert [r.text for r in results] == [r.text for r in legacy.recall("旅行", limit=5)]


# ---------------------------------------------------------------------------
# 可观测
# ---------------------------------------------------------------------------

def test_debug_snapshot_shape():
    sys = MemorySystem(recall_mode=RecallMode.SHADOW)
    _seed(sys)
    sys.recall("旅行")
    snap = sys.get_debug_snapshot()
    assert snap["recall_mode"] == "shadow"
    assert snap["l1_size"] >= 2
    assert "params" in snap and isinstance(snap["params"], dict)
    assert "tick" in snap


def test_debug_snapshot_is_readonly():
    """快照不触发召回/衰减副作用（tick 不变）。"""
    sys = MemorySystem()
    _seed(sys)
    before = sys._tick
    sys.get_debug_snapshot()
    assert sys._tick == before
