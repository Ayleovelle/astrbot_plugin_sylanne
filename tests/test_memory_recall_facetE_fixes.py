"""facet E 点名缺陷修复回归测试（3/4/5/6）。

- 3：RPE/novelty importance（重复信息不再因文本长持续拿高分）。
- 4：rewrite_item 同时遍历 L1/L2（L1 命中不再静默失败）。
- 5：reconsolidation 三层对称（L1 temperature / L3 emotion_weight 也随心境漂移）。
- 6：ACTIVATION 用 _layer_confidence 取代 _LAYER_WEIGHTS 硬乘（L3 不再被 0.4 重罚）。
"""

from __future__ import annotations

import time

from sylanne_alpha.memory_system import MemorySystem, RecallMode


def _sys() -> MemorySystem:
    return MemorySystem(recall_mode=RecallMode.ACTIVATION)


# ---------------------------------------------------------------------------
# 3：RPE/novelty importance
# ---------------------------------------------------------------------------

def test_repeated_content_importance_decays():
    """反复写入相同内容，后写的 importance 明显低于首条（不再因文本长持续拿高分）。"""
    m = MemorySystem()
    imps = [
        m.write_summary("今天好累啊感觉很疲惫", source_turns=1, temperature=0.0).importance
        for _ in range(11)
    ]
    assert imps[-1] < imps[0]
    assert (imps[0] - imps[-1]) / imps[0] >= 0.10  # 降幅 ≥10%


def test_novel_content_keeps_high_importance():
    """新颖内容不被 novelty 压低（与近期记忆重合少 → 加成大）。"""
    m = MemorySystem()
    for _ in range(5):
        m.write_summary("闲聊天气", temperature=0.0)
    novel = m.write_summary(
        "我们约好下周去爬黄山看日出庆祝你生日", source_turns=2, temperature=0.6
    )
    repeated = m.write_summary("闲聊天气", temperature=0.0)
    assert novel.importance > repeated.importance


def test_novelty_explicit_importance_not_affected():
    """显式传 importance 时不走 novelty（调用方意图优先）。"""
    m = MemorySystem()
    m.write_summary("重复内容", temperature=0.0)
    item = m.write_summary("重复内容", temperature=0.0, importance=0.9)
    assert item.importance == 0.9


def test_novelty_first_memory_no_crash():
    """首条记忆（无参照样本）不崩溃，给中性加成。"""
    m = MemorySystem()
    item = m.write_summary("第一条记忆", temperature=0.0)
    assert 0.0 <= item.importance <= 1.0


# ---------------------------------------------------------------------------
# 4：rewrite_item 覆盖 L1
# ---------------------------------------------------------------------------

def test_rewrite_item_finds_l1():
    m = _sys()
    item = m.write_summary("原始文本", temperature=0.0)
    assert m.rewrite_item(item.id, "重写后的文本") is True
    assert item.text == "重写后的文本"
    assert item.rewrite_count == 1


def test_rewrite_item_finds_l2():
    m = _sys()
    item = m.write_summary("L2 文本", temperature=0.0)
    item.confirmed = True
    m.sink_to_l2([item.id])
    assert m.rewrite_item(item.id, "L2 重写") is True
    assert any(it.text == "L2 重写" for it in m._l2)


def test_rewrite_item_missing_returns_false():
    m = _sys()
    assert m.rewrite_item("nonexistent", "x") is False


def test_rewrite_item_respects_freeze():
    m = _sys()
    item = m.write_summary("文本", temperature=0.0)
    item.rewrite_count = 20  # REWRITE_FREEZE_AFTER
    assert m.rewrite_item(item.id, "新") is False


def test_rewrite_weight_clamped():
    m = _sys()
    item = m.write_summary("文本", temperature=0.0)
    item.weight = 0.99
    m.rewrite_item(item.id, "新")
    assert item.weight <= 1.0


# ---------------------------------------------------------------------------
# 5：三层 reconsolidation 对称
# ---------------------------------------------------------------------------

def test_l1_temperature_drifts_on_recall():
    """L1 命中后 temperature 向 current_warmth 漂移（与 L2 对称）。"""
    m = _sys()
    item = m.write_summary("聊天记录", temperature=0.0)
    before = item.temperature
    m._refresh_recall(item, time.time(), current_warmth=0.8, layer="L1")
    assert item.temperature > before  # 向 +0.8 漂移
    beta = m._params["reconsolidation_rate"]
    assert abs(item.temperature - (before * (1 - beta) + 0.8 * beta)) < 1e-9


def test_l3_emotion_drifts_on_recall():
    """L3 节点命中后 emotion_weight 向 current_warmth 漂移。"""
    m = _sys()
    m.ingest_graph_triples([("用户", "喜欢", "猫", 0.2, 0.9)])
    node = next(n for n in m._l3_nodes.values() if n.label == "猫")
    before = node.emotion_weight
    m._refresh_recall(node, time.time(), current_warmth=-0.6, layer="L3")
    assert node.emotion_weight < before  # 向 -0.6 漂移


def test_l2_reconsolidation_still_works():
    """L2 漂移行为不变（回归保护）。"""
    m = _sys()
    item = m.write_summary("重要记忆", temperature=0.0)
    item.confirmed = True
    m.sink_to_l2([item.id])
    l2_item = m._l2[0]
    before = l2_item.temperature
    m._refresh_recall(l2_item, time.time(), current_warmth=0.5, layer="L2")
    assert l2_item.temperature > before


# ---------------------------------------------------------------------------
# 6：_layer_confidence 取代硬乘
# ---------------------------------------------------------------------------

def test_layer_confidence_no_l3_penalty():
    """L3 不再被 0.4 折扣（_layer_confidence(L3)=1.0）。"""
    m = _sys()
    assert m._layer_confidence("L3") == 1.0
    assert m._layer_confidence("L2") == 1.0


def test_layer_confidence_l1_discount():
    """L1 仍有置信折扣（未确认记忆）。"""
    m = _sys()
    assert m._layer_confidence("L1") < 1.0
    assert m._layer_confidence("L1") >= 0.70


def test_layer_confidence_personalized():
    """l1_confidence 是人格函数（inner_order 高→折扣轻）。"""
    orderly = MemorySystem(recall_mode=RecallMode.ACTIVATION, inner_order=0.9)
    chaotic = MemorySystem(recall_mode=RecallMode.ACTIVATION, inner_order=0.1)
    assert orderly._layer_confidence("L1") > chaotic._layer_confidence("L1")


def test_legacy_still_uses_layer_weights():
    """LEGACY 路径仍用 _LAYER_WEIGHTS 硬乘（零行为变化保护）。"""
    m = MemorySystem(recall_mode=RecallMode.LEGACY)
    assert m._LAYER_WEIGHTS == {"L1": 1.0, "L2": 0.7, "L3": 0.4}


def test_l3_recall_ranks_higher_without_penalty():
    """ACTIVATION 下高 clarity 的 L3 节点不再被 0.4 系统性压制。"""
    m = _sys()
    m.ingest_graph_triples([("北京", "是", "首都", 0.5, 0.95)])
    results = m.recall("北京", current_warmth=0.0, limit=5)
    l3 = [r for r in results if r.layer == "L3"]
    assert l3, "L3 节点应被召回"
    # final_score 不再被 0.4 折扣，应保有 composite 的较大比例
    assert l3[0].final_score > 0.4 * l3[0].debug.get("comp", 1.0) - 1e-9
