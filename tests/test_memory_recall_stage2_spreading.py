"""阶段2 L3 spreading activation 回归测试。

验证知识图谱的边真正参与召回（联想扩散），而非仅拼接文本：
- query 命中种子节点后，激活沿边扩散到邻居节点并作为候选。
- boundary 节点不接收扩散（边界保护）。
- fan effect：高连接度节点向每个邻居传导被稀释。
- 硬上限 / 激活地板剪枝，守住性能预算。
- 关系强度规则表 + 边 strength 赋值与回填。
- LEGACY 模式完全不触发 spreading（零行为变化）。
"""

from __future__ import annotations

import time

from sylanne_alpha.memory_system import (
    GraphEdge,
    MemorySystem,
    RecallMode,
    _relation_strength,
)


def _sys() -> MemorySystem:
    return MemorySystem(recall_mode=RecallMode.ACTIVATION)


# ---------------------------------------------------------------------------
# 关系强度规则表
# ---------------------------------------------------------------------------

def test_relation_strength_table():
    assert _relation_strength("爱") == 1.0
    assert _relation_strength("喜欢") == 0.9
    assert _relation_strength("类似") == 0.3
    assert _relation_strength("不在表里的关系") == 0.4  # 默认


def test_relation_strength_substring_match():
    """措辞变体（含核心词）应匹配到规则表。"""
    assert _relation_strength("非常喜欢") == 0.9


def test_ingest_assigns_edge_strength():
    m = _sys()
    m.ingest_graph_triples([("用户", "喜欢", "猫", 0.8, 0.9)])
    edge = m._l3_edges[0]
    assert edge.strength == 0.9  # "喜欢"


# ---------------------------------------------------------------------------
# 扩散核心
# ---------------------------------------------------------------------------

def test_spreading_reaches_neighbors():
    """query 命中种子 → 激活扩散到一跳/二跳邻居。"""
    m = _sys()
    m.ingest_graph_triples([
        ("用户", "喜欢", "猫", 0.8, 0.9),
        ("猫", "相关", "猫咪视频", 0.6, 0.8),
    ])
    pool = m._gather_pool("猫", None, time.time())
    extra = m._spreading_candidates(pool, 0.5, time.time())
    labels = {c["obj"].label for c in extra}
    assert "用户" in labels or "猫咪视频" in labels, "应扩散到邻居节点"
    assert all(c["reason"] == "spreading_activation" for c in extra)


def test_spreading_candidate_relevance_capped():
    """扩散候选的 relevance 不超过上限（弱于直接命中）。"""
    m = _sys()
    m.ingest_graph_triples([
        ("用户", "爱", "猫", 1.0, 1.0),
        ("猫", "是", "宠物", 1.0, 1.0),
    ])
    pool = m._gather_pool("猫", None, time.time())
    extra = m._spreading_candidates(pool, 0.5, time.time())
    assert all(c["rel"] <= m._SPREAD_REL_CAP for c in extra)


def test_boundary_node_not_spread():
    """boundary 节点不接收扩散（用户边界/禁忌保护）。"""
    m = _sys()
    m.ingest_graph_triples([
        ("猫", "相关", "隐私秘密", 0.0, 0.9),
    ])
    for node in m._l3_nodes.values():
        if node.label == "隐私秘密":
            node.type = "boundary"
    pool = m._gather_pool("猫", None, time.time())
    extra = m._spreading_candidates(pool, 0.5, time.time())
    labels = {c["obj"].label for c in extra}
    assert "隐私秘密" not in labels


def test_spreading_respects_max_nodes():
    """高扇出图：扩散触达节点数不超过硬上限。"""
    m = _sys()
    # 一个中心节点连 100 个邻居
    triples = [("中心", "相关", f"邻居{i}", 0.5, 0.9) for i in range(100)]
    m.ingest_graph_triples(triples)
    pool = m._gather_pool("中心", None, time.time())
    extra = m._spreading_candidates(pool, 0.5, time.time())
    assert len(extra) <= m._SPREAD_MAX_NODES


def test_no_seeds_no_spread():
    """query 不命中任何 L3 节点时，不产生扩散候选。"""
    m = _sys()
    m.ingest_graph_triples([("用户", "喜欢", "猫", 0.8, 0.9)])
    pool = m._gather_pool("完全不相关的查询xyz", None, time.time())
    extra = m._spreading_candidates(pool, 0.5, time.time())
    assert extra == []


def test_edge_weight_components():
    """边权重 = clarity × strength × 情绪调节，clamp [0,1]。"""
    m = _sys()
    edge = GraphEdge(source="a", target="b", relation="喜欢",
                     emotion_weight=0.5, clarity=0.8, strength=0.9)
    w_congruent = m._edge_weight(edge, current_warmth=0.5)  # 情绪契合
    w_conflict = m._edge_weight(edge, current_warmth=-0.5)  # 情绪冲突
    assert w_congruent > w_conflict  # 契合传导更强
    assert 0.0 <= w_congruent <= 1.0


def test_fan_effect_dilutes_high_degree():
    """fan effect：高连接度节点对单个邻居的传导被 1/√fan 稀释。"""
    m = _sys()
    now = time.time()
    # 低扇出：中心A 只连 1 个邻居
    m.ingest_graph_triples([("中心A", "相关", "邻居A", 0.5, 0.9)])
    # 高扇出：中心B 连 9 个邻居
    m.ingest_graph_triples(
        [("中心B", "相关", f"邻B{i}", 0.5, 0.9) for i in range(9)]
    )
    spread_a = m._spread_activation({_node_id(m, "中心A"): 1.0}, 0.5)
    spread_b = m._spread_activation({_node_id(m, "中心B"): 1.0}, 0.5)
    act_a = spread_a[_node_id(m, "邻居A")]
    act_b = spread_b[_node_id(m, "邻B0")]
    assert act_a > act_b, "低扇出邻居获得更强激活（fan effect）"


def _node_id(m: MemorySystem, label: str) -> str:
    for nid, n in m._l3_nodes.items():
        if n.label == label:
            return nid
    raise KeyError(label)


# ---------------------------------------------------------------------------
# LEGACY 不触发 spreading
# ---------------------------------------------------------------------------

def test_legacy_mode_no_spreading():
    """LEGACY 模式召回不应调用 spreading（零行为变化）。"""
    m = MemorySystem(recall_mode=RecallMode.LEGACY)
    m.ingest_graph_triples([
        ("用户", "喜欢", "猫", 0.8, 0.9),
        ("猫", "相关", "猫咪视频", 0.6, 0.8),
    ])
    called = {"spread": False}
    orig = m._spread_activation

    def spy(*a, **k):
        called["spread"] = True
        return orig(*a, **k)

    m._spread_activation = spy  # type: ignore
    m.recall("猫", limit=5)
    assert not called["spread"], "LEGACY 不应触发 spreading"


# ---------------------------------------------------------------------------
# 性能
# ---------------------------------------------------------------------------

def test_spreading_performance_under_budget():
    """1000 节点规模下，spreading 应在合理时间内（远低于 5ms 预算）。"""
    m = _sys()
    triples = []
    for i in range(500):
        triples.append((f"节点{i}", "相关", f"节点{i+1}", 0.5, 0.9))
    m.ingest_graph_triples(triples)
    pool = m._gather_pool("节点0", None, time.time())
    start = time.perf_counter()
    for _ in range(10):
        m._spreading_candidates(pool, 0.5, time.time())
    elapsed_ms = (time.perf_counter() - start) / 10 * 1000
    assert elapsed_ms < 5.0, f"spreading 耗时 {elapsed_ms:.2f}ms 超预算"
