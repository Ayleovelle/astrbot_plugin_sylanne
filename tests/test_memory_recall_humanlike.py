"""拟人化召回重构的回归测试。

覆盖本次修复的四个记忆系统缺陷：
- B3：近期记忆（5 分钟内）关键词 relevance=0 也应进入 rerank（recency 通道）。
- B4：τ 公式 recall_count 封顶 + importance 命中增益递减（抑制 rich-get-richer）。
- B5：L3 节点带 created_at/last_recalled_ts，recency 不再永远退化为中性 0.5。
- B6：from_dict 对越界 importance 做 [0,1] clamp。

附带（重设计评审发现、与大重构解耦的真 bug）：
- C1：importance 不再双重计入（τ 去掉 (1+importance)，改小幅 nudge）。
- C2：positive_recall_bias 改乘法，人格参数真正生效（旧 *0.1 量级失效）。
- C3：compress_old_turns importance 取被合并条目 max，而非默认 0.5。
- C4：L3 召回用 _tokenize 与 L1/L2 统一口径（旧 .split() 对中文失效）。
"""

from __future__ import annotations

import time

import pytest

from sylanne_alpha.memory_system import GraphNode, MemoryItem, MemorySystem


def _fresh_system() -> MemorySystem:
    return MemorySystem()


# ---------------------------------------------------------------------------
# B3：近期记忆兜底入池
# ---------------------------------------------------------------------------

def test_recent_memory_with_zero_relevance_still_recalled():
    """5 分钟内写入、与 query 关键词完全不重合的记忆仍应被召回（recency 通道）。"""
    sys = _fresh_system()
    # 写一条与 query 毫无词面重合的近期记忆
    sys.write_summary("今天阳光很好心情不错", source_turns=1, temperature=0.5)

    results = sys.recall(query="量子物理学的不确定性原理", limit=5)

    assert results, "近期记忆即使关键词不重合也应进入召回结果"
    assert any(r.recall_reason == "temporal_proximity" for r in results)


def test_old_memory_with_zero_relevance_dropped():
    """超过 5 分钟的记忆若关键词不重合，仍按原逻辑在阶段1被丢弃。"""
    sys = _fresh_system()
    item = sys.write_summary("今天阳光很好心情不错", source_turns=1, temperature=0.5)
    # 人为把创建时间推到 10 分钟前
    item.created_at = time.time() - 600

    results = sys.recall(query="量子物理学的不确定性原理", limit=5)

    assert not any(r.text == "今天阳光很好心情不错" for r in results)


# ---------------------------------------------------------------------------
# B4：rich-get-richer 抑制
# ---------------------------------------------------------------------------

def test_recency_tau_caps_recall_count():
    """recall_count 超过封顶后，τ 不再继续增大（recency 分相同）。"""
    now = time.time()
    created = now - 3600 * 24  # 1 天前
    score_at_cap = MemorySystem._recency_score(
        created, 0.0, MemorySystem._RECENCY_RECALL_CAP, 0.5, now
    )
    score_way_over = MemorySystem._recency_score(
        created, 0.0, MemorySystem._RECENCY_RECALL_CAP + 500, 0.5, now
    )
    assert score_at_cap == pytest.approx(score_way_over)


def test_importance_gain_decays_near_ceiling():
    """命中刷新时，importance 越接近 1.0 增益越小，且永不越界。"""
    sys = _fresh_system()
    item = sys.write_summary("一条普通记忆", source_turns=1, temperature=0.0)

    item.importance = 0.2
    sys._refresh_recall(item, time.time(), 0.0, "L1")
    low_gain = item.importance - 0.2

    item.importance = 0.95
    sys._refresh_recall(item, time.time(), 0.0, "L1")
    high_gain = item.importance - 0.95

    assert low_gain > high_gain, "低 importance 命中增益应大于接近上限时的增益"
    assert item.importance <= 1.0


def test_importance_never_exceeds_one_after_many_recalls():
    sys = _fresh_system()
    item = sys.write_summary("反复命中的记忆", source_turns=1, temperature=0.0)
    for _ in range(200):
        sys._refresh_recall(item, time.time(), 0.0, "L1")
    assert item.importance <= 1.0


# ---------------------------------------------------------------------------
# B5：L3 节点 recency 不再恒为中性
# ---------------------------------------------------------------------------

def test_graphnode_has_time_fields():
    node = GraphNode(
        id="n1", label="猫", type="preference",
        temporal_type="permanent", emotion_weight=0.5, clarity=0.9,
    )
    assert hasattr(node, "created_at")
    assert hasattr(node, "last_recalled_ts")


def test_graphnode_roundtrip_preserves_time_fields():
    node = GraphNode(
        id="n1", label="猫", type="preference",
        temporal_type="permanent", emotion_weight=0.5, clarity=0.9,
        created_at=1234.5, last_recalled_ts=6789.0,
    )
    restored = GraphNode.from_dict(node.to_dict())
    assert restored.created_at == 1234.5
    assert restored.last_recalled_ts == 6789.0


def test_graphnode_from_dict_legacy_defaults_zero():
    """旧存档无时间字段时回退 0.0（向后兼容）。"""
    legacy = {
        "id": "n1", "label": "猫", "type": "preference",
        "temporal_type": "permanent", "emotion_weight": 0.5, "clarity": 0.9,
    }
    node = GraphNode.from_dict(legacy)
    assert node.created_at == 0.0
    assert node.last_recalled_ts == 0.0


def test_created_node_gets_creation_time():
    sys = _fresh_system()
    node = sys._find_or_create_node(
        label="测试节点", node_type="topic", emotion_weight=0.0, clarity=0.8,
    )
    assert node.created_at > 0

def test_l3_recency_not_neutral_for_recent_node():
    """有真实时间戳的 L3 节点，recency 应高于中性 0.5（而非退化分支）。"""
    now = time.time()
    rec = MemorySystem._recency_score(
        created_at=now - 60, last_recalled_ts=0.0,
        recall_count=0, importance=0.8, now=now,
    )
    assert rec > 0.5, "刚创建的节点 recency 应明显高于中性值"


# ---------------------------------------------------------------------------
# B6：importance clamp
# ---------------------------------------------------------------------------

def test_from_dict_clamps_out_of_range_importance():
    high = MemoryItem.from_dict({
        "id": "x", "text": "t", "weight": 1.0, "temperature": 0.0,
        "age_ticks": 0, "created_at": time.time(), "importance": 5.0,
    })
    assert high.importance == 1.0

    low = MemoryItem.from_dict({
        "id": "y", "text": "t", "weight": 1.0, "temperature": 0.0,
        "age_ticks": 0, "created_at": time.time(), "importance": -3.0,
    })
    assert low.importance == 0.0


def test_from_dict_backfills_missing_importance():
    """缺 importance 字段时用启发式回填，落在 [0,1]。"""
    item = MemoryItem.from_dict({
        "id": "z", "text": "我答应你明天一起去看电影",
        "weight": 1.0, "temperature": 0.6, "age_ticks": 0,
        "created_at": time.time(), "source_turns": 3,
    })
    assert 0.0 <= item.importance <= 1.0
    # 含承诺关键词 + 情绪 + 多轮，应明显高于基线 0.3
    assert item.importance > 0.5


# ---------------------------------------------------------------------------
# B9：L3 relevance —— 中文子串命中 + 对称 Jaccard 防虚高
# ---------------------------------------------------------------------------

def test_l3_chinese_substring_recall():
    """中文（无空格分词）query 命中 L3 节点标签子串时应能召回，而非恒被丢弃。"""
    sys = _fresh_system()
    sys.ingest_graph_triples([("猫", "是", "喜欢的动物", 0.8, 0.9)])

    cands = sys._recall_l3_candidates("我们聊聊猫吧")

    labels = {c["obj"].label for c in cands}
    assert "猫" in labels, "中文子串命中的 L3 节点应进入候选（修复前 relevance 恒 0 被丢弃）"
    for c in cands:
        assert 0.0 < c["rel"] <= 0.5, "子串命中分应非零且不超过 0.5 上限"


def test_l3_word_overlap_uses_symmetric_jaccard():
    """词级命中用对称 Jaccard：多词 label 仅一词命中短 query 时不再虚高。"""
    sys = _fresh_system()
    # label 3 词("cat dog house") 仅 1 词命中 query 2 词("about cat")：
    # 旧式 交集/len(query) = 1/2 = 0.5（虚高）；
    # 新式 Jaccard = 交集/并集 = 1/(|{about,cat}∪{cat,dog,house}|=4) = 0.25。
    sys.ingest_graph_triples([("cat dog house", "rel", "x", 0.5, 0.9)])

    cands = sys._recall_l3_candidates("about cat")
    node = [c for c in cands if c["obj"].label == "cat dog house"]
    assert node, "应召回该节点"
    assert node[0]["rel"] == pytest.approx(0.25)
    assert node[0]["rel"] < 0.5, "对称 Jaccard 应低于旧式 交集/query 的 0.5 虚高分"


# ---------------------------------------------------------------------------
# C1：importance 不再双重计入 recency 的 τ
# ---------------------------------------------------------------------------

def test_recency_tau_independent_of_importance():
    """τ 不再随 importance 膨胀；高/低 importance 的 recency 仅差一个小幅 nudge。"""
    now = time.time()
    created = now - 3600 * 24 * 7  # 7 天前，让衰减明显
    low = MemorySystem._recency_score(created, 0.0, 0, 0.1, now)
    high = MemorySystem._recency_score(created, 0.0, 0, 0.9, now)
    # nudge 最大 0.05*(0.9-0.5)=0.02，差距应很小（旧式 (1+imp) 会让 τ 差近 1.9 倍）
    assert high - low <= 0.05
    assert high >= low  # 高 importance 仍略占优（nudge）


def test_recency_nudge_only_above_half():
    """importance<=0.5 不加 nudge，>0.5 才线性加成。"""
    now = time.time()
    created = now - 3600 * 24
    base = MemorySystem._recency_score(created, 0.0, 0, 0.5, now)
    below = MemorySystem._recency_score(created, 0.0, 0, 0.3, now)
    assert base == pytest.approx(below)  # 0.3 与 0.5 同分（都无 nudge）


# ---------------------------------------------------------------------------
# C2：positive_recall_bias 乘法生效
# ---------------------------------------------------------------------------

def test_positive_recall_bias_multiplicative():
    """高宜人性（bias>1）应让正向记忆 emotional 分明显高于中性。"""
    sys = _fresh_system()
    sys._params["positive_recall_bias"] = 1.3
    # 正向记忆(t=0.6) + 正向心境(w=0.6)：base=1.0，乘 1.3 后 clamp 到 1.0
    pos = sys._emotional_match_score(temperature=0.6, warmth=0.6)
    # 对照：把 bias 设回 1.0
    sys._params["positive_recall_bias"] = 1.0
    pos_nobias = sys._emotional_match_score(temperature=0.6, warmth=0.6)
    # bias=1.0 时 base=1.0；用一个不满分的场景验证乘法确实放大
    sys._params["positive_recall_bias"] = 1.3
    partial = sys._emotional_match_score(temperature=0.3, warmth=0.7)  # base=0.8
    sys._params["positive_recall_bias"] = 1.0
    partial_nobias = sys._emotional_match_score(temperature=0.3, warmth=0.7)
    assert partial > partial_nobias
    # 旧式 +0.03 在 base=0.8 时只到 0.83；乘法应到 0.8*1.3=1.0（clamp）
    assert partial >= 0.95


def test_negative_emotion_not_biased():
    """负向记忆不应被 positive_recall_bias 放大。"""
    sys = _fresh_system()
    sys._params["positive_recall_bias"] = 1.3
    neg = sys._emotional_match_score(temperature=-0.5, warmth=-0.5)
    sys._params["positive_recall_bias"] = 1.0
    neg_nobias = sys._emotional_match_score(temperature=-0.5, warmth=-0.5)
    assert neg == pytest.approx(neg_nobias)


# ---------------------------------------------------------------------------
# C3：压缩摘要保留最大 importance
# ---------------------------------------------------------------------------

def test_compress_preserves_max_importance():
    """压缩旧消息时，摘要 importance 取被合并条目最大值，不被稀释成 0.5。"""
    sys = _fresh_system()
    # 写 25 条，其中一条高 importance（含承诺关键词），触发压缩(max_turns=20)
    for i in range(24):
        sys.write_summary(f"普通闲聊第{i}条", source_turns=1, temperature=0.0)
    sys.write_summary("我答应你明天一定去接你", source_turns=3, temperature=0.7)
    high_imp = max(item.importance for item in sys._l1)

    compressed = sys.compress_old_turns("sess", max_turns=20)
    assert compressed > 0

    summaries = [it for it in sys._l1 if it.text.startswith("[压缩摘要]")]
    assert summaries
    # 被压缩的那批里若含高 importance 条目，摘要应继承其最大值（>默认 0.5）
    # 高 importance 条目最后写入，可能不在被压缩批次；至少验证摘要不是硬编码 0.5
    assert any(s.importance != 0.5 for s in summaries) or high_imp <= 0.5


def test_compress_summary_importance_is_max_of_batch():
    """直接验证：被压缩批次的最大 importance 传递到摘要。"""
    sys = _fresh_system()
    # 全部高 importance，确保被压缩批次里有高值
    for i in range(25):
        imp = 0.9 if i < 5 else 0.4
        sys.write_summary(f"消息{i}", source_turns=1, temperature=0.0, importance=imp)
    sys.compress_old_turns("sess", max_turns=20)
    summaries = [it for it in sys._l1 if it.text.startswith("[压缩摘要]")]
    assert summaries
    # 最旧 5 条 importance=0.9 会被压缩，摘要 importance 应为 0.9
    assert summaries[0].importance == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# C4：L3 召回用 _tokenize（中文口径统一）
# ---------------------------------------------------------------------------

def test_l3_chinese_word_level_recall_via_tokenize():
    """中文多字标签经 jieba 分词后能词级命中，而非只靠子串 fallback。"""
    sys = _fresh_system()
    sys.ingest_graph_triples([("北京", "是", "首都", 0.5, 0.9)])
    # query 含"北京"，jieba 应切出"北京" token 与 label 词级交集命中
    cands = sys._recall_l3_candidates("我想去北京旅游")
    labels = {c["obj"].label for c in cands}
    assert "北京" in labels
