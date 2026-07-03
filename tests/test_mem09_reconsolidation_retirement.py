"""MEM-09：废除破坏性再固化（stop the ongoing history falsification）。

覆盖：
1. MemorySystem.rewrite_item 下线为 no-op（recall/rewrite 不再改写 item.text）。
2. LLMRequestPipeline._reconsolidation_rewrite(_guarded) 下线为 no-op（不再调 LLM、
   不再触碰 memory_system）。
3. v2core MemoryDomain：overlay 优先按 item.id 建键，text 键仅作旧档兜底解析。
4. reconsolidate() 单次漂移幅度钳位 |Δoverlay_warmth| <= _RECON_DRIFT_CAP。
5. 冻结面回归：recall() 全流程不再改写 item.text（旧行为的反向钉子）。
"""

from __future__ import annotations

import asyncio

from sylanne_alpha.memory_system import MemorySystem, RecallMode
from sylanne_alpha.v2core.domains.memory import MemoryDomain


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 1：MemorySystem.rewrite_item no-op
# ---------------------------------------------------------------------------

def test_rewrite_item_never_mutates_text():
    m = MemorySystem(recall_mode=RecallMode.ACTIVATION)
    item = m.write_summary("原始记忆文本", temperature=0.0)
    original_embedding = item.embedding
    assert m.rewrite_item(item.id, "被覆盖的假文本") is False
    assert item.text == "原始记忆文本"
    assert item.rewrite_count == 0
    assert item.embedding == original_embedding


def test_recall_does_not_mutate_item_text_across_many_recalls():
    """回归钉子：多次 recall 命中同一条目，item.text 全程不变（旧行为的反面）。"""
    m = MemorySystem(recall_mode=RecallMode.ACTIVATION)
    item = m.write_summary("会被回忆很多次的记忆", temperature=0.0)
    item.confirmed = True
    m.sink_to_l2([item.id])
    for _ in range(25):  # 超过旧 REWRITE_FREEZE_AFTER=20，确认无论多少次都不改写
        m.recall("回忆很多次", current_warmth=0.7, limit=3)
    l2_item = next(it for it in m._l2 if it.id == item.id)
    assert l2_item.text == "会被回忆很多次的记忆"


# ---------------------------------------------------------------------------
# 2：pipeline 侧调度/回调下线为 no-op
# ---------------------------------------------------------------------------

def test_reconsolidation_rewrite_guarded_is_noop():
    from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline

    pipe = LLMRequestPipeline.__new__(LLMRequestPipeline)

    class _BoomMS:
        def get_recalled_l2_items(self):
            raise AssertionError("MEM-09: no-op 不应再读取 recalled l2 items")

        def to_dict(self):
            raise AssertionError("MEM-09: no-op 不应再序列化 memory_system")

    _run(pipe._reconsolidation_rewrite_guarded("sess", _BoomMS()))
    _run(pipe._reconsolidation_rewrite("sess", _BoomMS()))


# ---------------------------------------------------------------------------
# 3/4：v2core overlay id 建键 + text 兜底 + 漂移钳位
# ---------------------------------------------------------------------------

def _seeded_domain() -> tuple[MemoryDomain, str]:
    ms = MemorySystem()
    item = ms.write_summary("我们说好周末去看海", source_turns=2, temperature=-0.6)
    return MemoryDomain(ms), item.id


def test_recall_row_carries_stable_item_id():
    dom, item_id = _seeded_domain()
    rows = dom.recall("看海", warmth=0.5)
    assert rows and rows[0]["id"] == item_id


def test_reconsolidate_keys_overlay_by_id_not_text():
    """MEM-09：新写入的影子条目按 item.id 建键（不再是 text）。"""
    dom, item_id = _seeded_domain()
    recalled = dom.recall("看海", warmth=0.9)
    n = dom.reconsolidate(recalled, current_warmth=0.9, narrative_pe=0.9, pe_gate=0.5)
    assert n == 1
    assert dom.overlay_for(item_id) is not None
    assert "我们说好周末去看海" not in dom._reconsolidation_overlay


def test_overlay_old_text_keyed_entry_resolves_via_fallback():
    """迁移兼容：MEM-09 之前按 text 持久化的旧影子条目，读侧（recall）与写侧
    （reconsolidate）都能通过 text 兜底继续解析到，不会因为改键而丢失历史信号。"""
    dom, item_id = _seeded_domain()
    # 模拟旧档：影子层曾按 text 键持久化（load_dict 从旧存档恢复进来的场景）
    dom._reconsolidation_overlay["我们说好周末去看海"] = {
        "overlay_warmth": 0.4, "rewrite_count": 3, "last_pe": 0.6,
    }

    # 读侧：recall 附带 overlay_warmth 时应命中旧 text 键（id 还未写入过影子层）
    rows = dom.recall("看海", warmth=0.5)
    assert rows[0]["id"] == item_id
    assert rows[0]["overlay_warmth"] == 0.4

    # 写侧：再固化一次后，旧 text 键条目被迁移到 id 键下，不留孤儿
    n = dom.reconsolidate(rows, current_warmth=0.9, narrative_pe=0.9, pe_gate=0.5)
    assert n == 1
    migrated = dom.overlay_for(item_id)
    assert migrated is not None
    assert migrated["rewrite_count"] == 4  # 3 (旧档) + 1 (本次)
    assert "我们说好周末去看海" not in dom._reconsolidation_overlay


def test_overlay_for_supports_explicit_text_fallback_kw():
    dom, item_id = _seeded_domain()
    dom._reconsolidation_overlay["我们说好周末去看海"] = {
        "overlay_warmth": 0.2, "rewrite_count": 1, "last_pe": 0.5,
    }
    assert dom.overlay_for(item_id) is None  # 尚未按 id 建过键
    ov = dom.overlay_for(item_id, text_fallback="我们说好周末去看海")
    assert ov is not None and ov["overlay_warmth"] == 0.2


def test_reconsolidate_drift_clamped_per_call():
    """MEM-09：单次重固化 |Δoverlay_warmth| <= _RECON_DRIFT_CAP，即便冷/热反差极大。"""
    dom, item_id = _seeded_domain()  # temperature=-0.6（冷）
    recalled = dom.recall("看海", warmth=1.0)
    n = dom.reconsolidate(recalled, current_warmth=1.0, narrative_pe=0.9, pe_gate=0.5)
    assert n == 1
    ov = dom.overlay_for(item_id)
    # 起始基线 -0.6，当下情绪 +1.0，若无钳位单次即可漂到 ~0.22；钳位后应贴着
    # -0.6 + _RECON_DRIFT_CAP 附近，而非直接跳到 target。
    delta = ov["overlay_warmth"] - (-0.6)
    assert 0.0 < delta <= MemoryDomain._RECON_DRIFT_CAP + 1e-9


def test_reconsolidate_drift_clamp_holds_over_many_calls():
    """连续多次重固化，每次漂移量都不超过钳位上限（不是钳位后又整体跳变）。"""
    dom, item_id = _seeded_domain()
    prev = None
    for _ in range(5):
        recalled = dom.recall("看海", warmth=1.0)
        dom.reconsolidate(recalled, current_warmth=1.0, narrative_pe=0.9, pe_gate=0.5)
        ov = dom.overlay_for(item_id)
        if prev is not None:
            assert abs(ov["overlay_warmth"] - prev) <= MemoryDomain._RECON_DRIFT_CAP + 1e-9
        prev = ov["overlay_warmth"]
