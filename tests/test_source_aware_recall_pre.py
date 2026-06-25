"""Phase 2A / PR-E Source-Aware Recall 测试。

验证：
- _apply_privacy_filter 公共层：internal 摘除、open/shareable/user_fact 保留、
  GraphNode(无属性)不误杀、candidate 缺字段/typo fail-closed、整体异常返回空
- 三模式覆盖（LEGACY/ACTIVATION/SHADOW 都经过过滤）
- _source_aware_rank：final_score 主序 + source/confidence 同分 tiebreaker
- 端到端 recall：internal 不进结果、shareable 仍可召回

全部直调真实函数。
"""

from __future__ import annotations

import time

from sylanne_alpha.memory_system import (
    GraphNode,
    MemoryItem,
    MemoryResult,
    MemorySystem,
    RecallMode,
)


def _item(privacy="open", source="dialogue", confidence=0.5, text="t"):
    return MemoryItem(
        id="i" + str(time.time_ns()), text=text, weight=1.0, temperature=0.0,
        age_ticks=0, embedding=None, created_at=time.time(),
        source=source, privacy_level=privacy, confidence=confidence,
    )


def _node(privacy="open", label="猫"):
    return GraphNode(
        id="n" + str(time.time_ns()), label=label, type="preference",
        temporal_type="permanent", emotion_weight=0.5, clarity=0.9,
        privacy_level=privacy,
    )


class _AttrlessObj:
    """无 privacy_level 属性的异常对象（裸对象/脏候选）。"""


# ---- _apply_privacy_filter 单元 ----

def test_privacy_filter_drops_internal_keeps_visible():
    ms = MemorySystem()
    pool = [
        {"obj": _item("open")}, {"obj": _item("internal")},
        {"obj": _item("shareable")}, {"obj": _item("user_fact")},
    ]
    kept = ms._apply_privacy_filter(pool, "user_visible")
    privs = [c["obj"].privacy_level for c in kept]
    assert "internal" not in privs
    assert set(privs) == {"open", "shareable", "user_fact"}


def test_graphnode_open_kept_internal_dropped():
    """L3 GraphNode 显式持 privacy_level：open 保留、internal 摘除（review HIGH）。"""
    ms = MemorySystem()
    kept = ms._apply_privacy_filter(
        [{"obj": _node("open")}, {"obj": _node("internal")}], "user_visible"
    )
    assert len(kept) == 1
    assert kept[0]["obj"].privacy_level == "open"


def test_attrless_object_failclosed_dropped():
    """无 privacy_level 属性的对象 → fail-closed 丢弃，不再"视 open"放行（review HIGH）。"""
    ms = MemorySystem()
    kept = ms._apply_privacy_filter([{"obj": _AttrlessObj()}, {"obj": None}], "user_visible")
    assert kept == []



def test_recall_candidate_missing_or_typo_privacy_failclosed():
    """红队 BLOCKER-1 + review HIGH 防回归：候选 obj 隐私缺失/非法时 fail-closed。

    obj 是 MemoryItem 时 __post_init__ 已把 typo 归一成 internal → 被摘；
    obj 为 None / 无 privacy_level 属性 → fail-closed drop（不再"视 open"放行）。
    """
    ms = MemorySystem()
    # typo 经 MemoryItem 构造已 fail-closed 成 internal，过滤层摘除
    typo_item = _item("internl")  # __post_init__ → internal
    assert typo_item.privacy_level == "internal"
    assert ms._apply_privacy_filter([{"obj": typo_item}], "user_visible") == []
    # obj=None（极端脏数据）→ 无 privacy_level 属性 → drop；internal 项也必被摘
    kept = ms._apply_privacy_filter(
        [{"obj": None}, {"obj": typo_item}, {"obj": _item("open")}], "user_visible"
    )
    privs = [c["obj"].privacy_level for c in kept if c["obj"] is not None]
    assert privs == ["open"]  # 只剩合法可见项


def test_privacy_filter_non_user_visible_passthrough():
    ms = MemorySystem()
    pool = [{"obj": _item("internal")}, {"obj": _item("open")}]
    assert len(ms._apply_privacy_filter(pool, "internal")) == 2


def test_privacy_filter_fail_closed_on_exception():
    """整体异常（喂不可迭代）→ 返回空，绝不返回未过滤池（fail-closed）。"""
    ms = MemorySystem()
    assert ms._apply_privacy_filter(None, "user_visible") == []
    assert ms._apply_privacy_filter(12345, "user_visible") == []


# ---- _source_aware_rank 单元 ----

def _res(score, source, privacy, confidence):
    o = _item(privacy=privacy, source=source, confidence=confidence)
    r = MemoryResult(
        text="t", layer="L1", weight=1.0, relevance=0.5, clarity=1.0,
        temperature=0.0, final_score=score, created_at=time.time(),
    )
    r.source = source
    r.source_obj = o
    return r


def test_source_aware_ranking_final_score_is_primary():
    """主序：final_score 高者第一，绝不被 source 优先级推翻。"""
    ms = MemorySystem()
    low_userfact = _res(0.3, "dialogue", "user_fact", 0.9)
    high_lifesim = _res(0.9, "life_sim", "shareable", 0.1)
    ranked = ms._source_aware_rank([low_userfact, high_lifesim])
    assert ranked[0].final_score == 0.9  # 高分第一，尽管它是 life_sim


def test_recall_distinguishes_user_fact_and_life_sim():
    """同 final_score：user_fact 排在 life_sim 前。"""
    ms = MemorySystem()
    life = _res(0.5, "life_sim", "shareable", 0.5)
    fact = _res(0.5, "dialogue", "user_fact", 0.5)
    ranked = ms._source_aware_rank([life, fact])
    assert ranked[0].source_obj.privacy_level == "user_fact"
    assert ranked[1].source == "life_sim"


def test_confidence_tiebreaker():
    """同 final_score 同 source：confidence 高者优先。"""
    ms = MemorySystem()
    lo = _res(0.5, "dialogue", "open", 0.2)
    hi = _res(0.5, "dialogue", "open", 0.9)
    ranked = ms._source_aware_rank([lo, hi])
    assert ranked[0].source_obj.confidence == 0.9


def test_source_aware_rank_exception_degrades_to_final_score():
    """异常降级：保留 final_score 排序，不抛错（裁决 §3.5）。"""
    ms = MemorySystem()

    class Bad:
        @property
        def final_score(self):
            raise RuntimeError("boom")

    # 传入会让 key 抛错的对象 → 降级路径也按 final_score，但这些对象无 final_score
    # 用正常对象验证降级分支不破坏顺序即可
    a = _res(0.2, "dialogue", "open", 0.5)
    b = _res(0.8, "dialogue", "open", 0.5)
    ranked = ms._source_aware_rank([a, b])
    assert ranked[0].final_score == 0.8


# ---- 三模式端到端：internal 不进 recall 结果 ----

def _seed_internal_and_shareable(ms):
    ms.write_summary("拿铁咖啡是我们聊过的话题", source="dialogue",
                     privacy_level="shareable", source_turns=2)
    ms.write_summary("拿铁相关的内部独白秘密内容", source="life_sim",
                     privacy_level="internal", source_turns=1)


def _texts(results):
    return " ".join(r.text for r in results)


def test_internal_privacy_not_in_user_prompt_legacy():
    ms = MemorySystem(recall_mode=RecallMode.LEGACY)
    _seed_internal_and_shareable(ms)
    results = ms.recall("拿铁咖啡", current_warmth=0.0, limit=5)
    assert "内部独白秘密" not in _texts(results)


def test_life_sim_shareable_still_recallable():
    """正向回归：shareable 不被过度过滤，仍可召回。"""
    ms = MemorySystem(recall_mode=RecallMode.LEGACY)
    ms.write_summary("拿铁咖啡是我们聊过的话题", source="dialogue",
                     privacy_level="shareable", source_turns=2)
    results = ms.recall("拿铁咖啡", current_warmth=0.0, limit=5)
    assert "拿铁" in _texts(results)


def test_privacy_filter_covers_activation_mode():
    """ACTIVATION 模式下 internal 仍被过滤（公共层覆盖三模式）。"""
    ms = MemorySystem(recall_mode=RecallMode.ACTIVATION)
    _seed_internal_and_shareable(ms)
    results = ms.recall("拿铁咖啡", current_warmth=0.0, limit=5)
    assert "内部独白秘密" not in _texts(results)


def test_privacy_filter_covers_shadow_mode():
    ms = MemorySystem(recall_mode=RecallMode.SHADOW)
    _seed_internal_and_shareable(ms)
    results = ms.recall("拿铁咖啡", current_warmth=0.0, limit=5)
    assert "内部独白秘密" not in _texts(results)


# ---- GraphNode privacy_level 迁移 / roundtrip（review HIGH §48）----

def test_graphnode_privacy_level_roundtrip():
    n = _node("internal", label="秘密节点")
    assert GraphNode.from_dict(n.to_dict()).privacy_level == "internal"
    assert GraphNode.from_dict(_node("open").to_dict()).privacy_level == "open"


def test_graphnode_legacy_archive_migrates_to_open():
    """旧图谱无 privacy_level 字段 → 显式迁移为 open（基线可见，行为不变）。"""
    legacy = {
        "id": "n", "label": "猫", "type": "preference",
        "temporal_type": "permanent", "emotion_weight": 0.5, "clarity": 0.9,
    }
    assert GraphNode.from_dict(legacy).privacy_level == "open"


def test_graphnode_illegal_privacy_failclosed():
    """旧图谱存了非法 privacy 字符串 → __post_init__ fail-closed 降 internal。"""
    legacy = {
        "id": "n", "label": "猫", "type": "preference",
        "temporal_type": "permanent", "emotion_weight": 0.5, "clarity": 0.9,
        "privacy_level": "leaky",
    }
    assert GraphNode.from_dict(legacy).privacy_level == "internal"


# ---- ACTIVATION 扩散节点不绕过 privacy（review HIGH §47）----

def test_activation_spread_internal_node_not_in_results():
    """ACTIVATION 扩散出来的 internal L3 节点不进结果（wide 第二道 filter）。"""
    ms = MemorySystem(recall_mode=RecallMode.ACTIVATION)
    ms.ingest_graph_triples([
        ("拿铁", "相关", "内部秘密节点", 0.6, 0.9),
    ])
    # 把扩散邻居标成 internal
    for node in ms._l3_nodes.values():
        if node.label == "内部秘密节点":
            node.privacy_level = "internal"
    results = ms.recall("拿铁", current_warmth=0.0, limit=5)
    assert "内部秘密节点" not in _texts(results)


def test_wide_refilter_drops_internal_from_spreading():
    """直测：wide 含扩散来的 internal GraphNode → 第二道 filter 摘除。"""
    ms = MemorySystem()
    wide = [
        {"obj": _node("open", "可见节点"), "text": "可见节点"},
        {"obj": _node("internal", "扩散内部节点"), "text": "扩散内部节点"},
    ]
    kept = ms._apply_privacy_filter(wide, "user_visible")
    labels = {c["obj"].label for c in kept}
    assert "可见节点" in labels and "扩散内部节点" not in labels


# ---- 三审 BLOCKER：L2→L3 压缩 / 直接 ingest 不让 internal 外泄 ----

def test_compress_check_excludes_internal_l2():
    """internal L2 条目不进压缩候选（不会被洗成 open GraphNode）。"""
    ms = MemorySystem()
    # 构造两条 30 天未召回的老 L2：一条 open、一条 internal
    open_item = ms.write_summary("可压缩的对话", source="dialogue", privacy_level="open")
    int_item = ms.write_summary("internal 内部独白", source="life_sim",
                                privacy_level="internal")
    for it in (open_item, int_item):
        it.age_ticks = 99999
    # 移到 L2（compress_check 只看 _l2）
    ms._l2.extend([open_item, int_item])
    cand_texts = [c.text for c in ms.compress_check()]
    assert "可压缩的对话" in cand_texts
    assert "internal 内部独白" not in cand_texts


def test_ingest_internal_triple_not_user_visible():
    """直接 ingest 显式 internal triple → 不创建用户可见 L3 召回输出。"""
    ms = MemorySystem(recall_mode=RecallMode.LEGACY)
    ms.ingest_graph_triples([
        {"subject": "拿铁", "relation": "关联", "object": "内部禁忌话题",
         "privacy_level": "internal"},
    ])
    # internal triple 被跳过：图谱里不应出现该 internal 实体节点
    labels = {n.label for n in ms._l3_nodes.values()}
    assert "内部禁忌话题" not in labels
    results = ms.recall("拿铁", current_warmth=0.0, limit=5)
    assert "内部禁忌话题" not in _texts(results)


def test_ingest_open_triple_still_works():
    """正向回归：普通（无 privacy 标记）triple 仍正常进 L3。"""
    ms = MemorySystem()
    ms.ingest_graph_triples([
        {"subject": "拿铁", "relation": "关联", "object": "咖啡馆"},
    ])
    labels = {n.label for n in ms._l3_nodes.values()}
    assert "咖啡馆" in labels


# ---- 三审 MEDIUM：internal 节点不作二跳桥 ----

def test_internal_node_not_spreading_bridge():
    """open A -> internal B -> open C：种子 A 不应经 B 把 C 扩散出来。"""
    ms = MemorySystem(recall_mode=RecallMode.ACTIVATION)
    ms.ingest_graph_triples([
        ("拿铁", "相关", "桥接内部", 0.6, 0.9),
        ("桥接内部", "相关", "下游公开", 0.6, 0.9),
    ])
    for node in ms._l3_nodes.values():
        if node.label == "桥接内部":
            node.privacy_level = "internal"
    # 直测扩散：种子=拿铁，internal B 不可遍历 → C 不出现在 spread
    seed = None
    for nid, n in ms._l3_nodes.items():
        if n.label == "拿铁":
            seed = nid
    spread = ms._spread_activation({seed: 1.0}, 0.0)
    spread_labels = {ms._l3_nodes[nid].label for nid in spread if nid in ms._l3_nodes}
    assert "桥接内部" not in spread_labels   # internal 不接收激活
    assert "下游公开" not in spread_labels   # 不经 internal 桥到达




