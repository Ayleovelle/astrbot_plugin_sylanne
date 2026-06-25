"""Phase 2A / PR-D Memory Contract 测试。

验证 MemoryItem 新增 confidence/privacy_level/life_event_id 三字段的：
- 默认值、roundtrip 序列化
- 旧档缺字段迁移（confidence=0.5 / privacy_level="open" / life_event_id=""）
- __post_init__ 单点规范化：confidence clamp、非法 privacy fail-closed→internal、life_event_id 兜 str
- write_summary 扩参向后兼容 + 透传

全部直调真实函数（不复刻逻辑）。
"""

from __future__ import annotations

import time

from sylanne_alpha.memory_system import MemoryItem, MemorySystem


def _mk(**kw) -> MemoryItem:
    base = dict(
        id="x", text="t", weight=1.0, temperature=0.0, age_ticks=0,
        embedding=None, created_at=time.time(),
    )
    base.update(kw)
    return MemoryItem(**base)


# ---- 默认值 + roundtrip ----

def test_memoryitem_pr_d_defaults():
    it = _mk()
    assert it.confidence == 0.5
    assert it.privacy_level == "open"
    assert it.life_event_id == ""


def test_memoryitem_pr_d_fields_roundtrip():
    it = _mk(confidence=0.8, privacy_level="shareable", life_event_id="evt123")
    d = it.to_dict()
    assert d["confidence"] == 0.8
    assert d["privacy_level"] == "shareable"
    assert d["life_event_id"] == "evt123"
    r = MemoryItem.from_dict(d)
    assert r.confidence == 0.8
    assert r.privacy_level == "shareable"
    assert r.life_event_id == "evt123"


# ---- 旧档迁移 ----

def test_old_memory_item_no_confidence_privacy_loads_defaults():
    legacy = {
        "id": "x", "text": "旧对话记忆", "weight": 1.0, "temperature": 0.0,
        "age_ticks": 0, "created_at": time.time(),
    }
    it = MemoryItem.from_dict(legacy)
    assert it.confidence == 0.5
    assert it.privacy_level == "open"   # 旧 dialogue 基线，可召回（行为不变）
    assert it.life_event_id == ""
    assert it.text == "旧对话记忆"


def test_old_life_sim_memory_not_upgraded_to_user_fact():
    """旧 life_sim 条目迁移后绝不变成 user_fact（防误升，ADR-002）。"""
    legacy = {
        "id": "x", "text": "我今天写了代码", "weight": 1.0, "temperature": 0.3,
        "age_ticks": 0, "created_at": time.time(), "source": "life_sim",
    }
    it = MemoryItem.from_dict(legacy)
    assert it.privacy_level != "user_fact"


# ---- __post_init__ 单点规范化 ----

def test_invalid_confidence_clamped():
    assert _mk(confidence=-0.5).confidence == 0.0
    assert _mk(confidence=2.0).confidence == 1.0
    assert _mk(confidence=0.7).confidence == 0.7


def test_non_numeric_confidence_falls_back():
    """非数字 confidence（脏数据）→ 回退中性 0.5，不抛错。"""
    assert _mk(confidence="garbage").confidence == 0.5
    assert _mk(confidence=None).confidence == 0.5


def test_invalid_privacy_level_normalizes_internal():
    """非法 privacy_level（typo/脏数据）→ fail-closed 降为 internal，不兜底 open。"""
    assert _mk(privacy_level="internl").privacy_level == "internal"
    assert _mk(privacy_level="public").privacy_level == "internal"
    assert _mk(privacy_level="???").privacy_level == "internal"
    # 合法值原样保留
    for legal in ("open", "internal", "shareable", "user_fact"):
        assert _mk(privacy_level=legal).privacy_level == legal


def test_none_or_empty_privacy_level_is_open_baseline():
    """None/空串视为缺省 → 基线 open（旧 dialogue 兼容），非 fail-closed。"""
    assert _mk(privacy_level=None).privacy_level == "open"
    assert _mk(privacy_level="").privacy_level == "open"


def test_life_event_id_coerced_to_str():
    assert _mk(life_event_id=None).life_event_id == ""
    assert _mk(life_event_id=12345).life_event_id == "12345"


def test_old_archive_illegal_privacy_failclosed_via_from_dict():
    """旧档存了非法 privacy 字符串 → from_dict 经 __post_init__ fail-closed 降 internal。"""
    legacy = {
        "id": "x", "text": "t", "weight": 1.0, "temperature": 0.0,
        "age_ticks": 0, "created_at": time.time(), "privacy_level": "leaky_typo",
    }
    assert MemoryItem.from_dict(legacy).privacy_level == "internal"


def test_old_archive_out_of_range_confidence_clamped_via_from_dict():
    legacy = {
        "id": "x", "text": "t", "weight": 1.0, "temperature": 0.0,
        "age_ticks": 0, "created_at": time.time(), "confidence": 9.9,
    }
    assert MemoryItem.from_dict(legacy).confidence == 1.0


# ---- write_summary 扩参 ----

def test_write_summary_backward_compatible_defaults():
    """旧调用方不传新参 → confidence=0.5, privacy_level="open", life_event_id=""。"""
    ms = MemorySystem()
    it = ms.write_summary("一条普通对话", source_turns=1, temperature=0.0)
    assert it.confidence == 0.5
    assert it.privacy_level == "open"
    assert it.life_event_id == ""


def test_write_summary_passes_new_fields():
    ms = MemorySystem()
    it = ms.write_summary(
        "Sylanne 自己经历的事", source_turns=1, temperature=0.3,
        source="life_sim", confidence=0.5, privacy_level="shareable",
        life_event_id="evt-xyz",
    )
    assert it.source == "life_sim"
    assert it.privacy_level == "shareable"
    assert it.life_event_id == "evt-xyz"
    assert it.confidence == 0.5


def test_write_summary_illegal_privacy_failclosed():
    """write_summary 传非法 privacy → __post_init__ fail-closed 降 internal。"""
    ms = MemorySystem()
    it = ms.write_summary("x", privacy_level="bogus")
    assert it.privacy_level == "internal"

