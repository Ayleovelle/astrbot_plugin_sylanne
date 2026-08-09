"""issue#43 Wave3 回归：记忆按 life_event_id 真去重（兑现 docstring 的「去重键」）。

原 bug（根因 H3）：write_summary docstring 自称 life_event_id 是去重键，函数体却无条件
append、从不比对 → 同一 life_sim 事件每轮被写入/召回、注入对话回复（已回「点外卖」仍问
「中午吃什么」式复读）。本组覆盖：

- dedup-on-write：同 life_event_id 第二次写入跳过、返回原件，L1 只一条
- dialogue 路径不变：life_event_id 恒空，永不折叠（行为字节不变）
- 去重返回原件【不改动】既有字段（recall_count 不被重置、近期性不复活）
- 召回侧折叠：同一非空 life_event_id 的多条只保留最高分一条，dialogue/无 id 条目原样保留
"""

from types import SimpleNamespace

from sylanne_alpha.memory_system import MemorySystem

_TEXT = "周末说好一起玩 Bread and Fred 的游戏邀请"


def _write_life(ms: MemorySystem, text: str, leid: str):
    return ms.write_summary(
        text, source="life_sim", privacy_level="shareable",
        confidence=0.5, importance=0.6, life_event_id=leid,
    )


def test_dedup_on_write_same_life_event_id():
    ms = MemorySystem()
    a = _write_life(ms, _TEXT, "e1")
    b = _write_life(ms, _TEXT, "e1")
    assert len(ms._l1) == 1, "同 life_event_id 写两次只应留一条"
    assert b is a, "第二次写入应返回既有原件，而非新建"
    assert [i.life_event_id for i in ms._l1] == ["e1"]


def test_dialogue_writes_not_deduped():
    """dialogue 写入 life_event_id 恒空，绝不互相折叠（保留原 append 行为）。"""
    ms = MemorySystem()
    ms.write_summary(_TEXT, source="dialogue")
    ms.write_summary(_TEXT, source="dialogue")
    assert len(ms._l1) == 2, "空 life_event_id 的 dialogue 摘要必须各自独立，不去重"


def test_dedup_returns_existing_untouched():
    """命中去重返回原件，且【不改动】其 recall_count/created_at（不复活近期性、不破 MED-1）。"""
    ms = MemorySystem()
    a = _write_life(ms, _TEXT, "e1")
    a.recall_count = 5
    a.last_recalled_ts = 999.0
    a.importance = 0.6
    created = a.created_at
    b = _write_life(ms, _TEXT, "e1")
    assert b is a
    assert b.recall_count == 5, "去重不得重置/递增 recall_count"
    assert b.created_at == created, "去重不得刷新 created_at（否则复活近期性）"
    assert b.last_recalled_ts == 999.0, "去重不得刷新 last_recalled_ts（否则破 MED-1 同轮防双注入）"
    assert b.importance == 0.6, "去重不得改 importance"
    assert len(ms._l1) == 1


def test_different_ids_not_deduped():
    ms = MemorySystem()
    _write_life(ms, _TEXT, "e1")
    _write_life(ms, _TEXT, "e2")
    assert len(ms._l1) == 2, "不同 life_event_id 是不同事件，不能折叠"


def test_fold_by_life_event_id_collapses_duplicates():
    """召回侧折叠：同一非空 id 只留首现（最高分），dialogue/无 id 原样保留、顺序不变。"""
    def _r(leid, score):
        return SimpleNamespace(
            source_obj=SimpleNamespace(life_event_id=leid), final_score=score
        )

    results = [_r("e1", 0.9), _r("e1", 0.5), _r("", 0.4), _r("e2", 0.3), _r("", 0.2)]
    folded = MemorySystem._fold_by_life_event_id(results)
    assert len(folded) == 4, "两条 e1 折成一条，其余保留"
    assert folded[0].final_score == 0.9, "保留 e1 中最高分（首现）"
    e1 = [r for r in folded if getattr(r.source_obj, "life_event_id", "") == "e1"]
    assert len(e1) == 1
    blanks = [r for r in folded if not getattr(r.source_obj, "life_event_id", "")]
    assert len(blanks) == 2, "dialogue（空 id）条目不被折叠"


def test_fold_keeps_l3_or_attrless_results():
    """source_obj 缺 life_event_id 字段（如 L3 GraphNode）的条目原样保留，不报错。"""
    folded = MemorySystem._fold_by_life_event_id(
        [SimpleNamespace(source_obj=object()), SimpleNamespace(source_obj=None)]
    )
    assert len(folded) == 2
