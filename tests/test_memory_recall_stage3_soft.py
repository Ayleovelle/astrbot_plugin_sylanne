"""阶段3 软召回 + 三级分级注入 + 舌尖现象 + 情感特权 回归测试。

验证硬门控被三级置信替代，"她记得我"体验落地：
- _classify_confidence 分级 clear/vague/tot/None。
- 情感特权加成 _compute_final_activation 抬高强情绪记忆。
- 情感旁路：心境带情绪时召回同频强情绪记忆；中性闲聊时不触发。
- format_recall_injection 按置信度用不同措辞（含舌尖模糊）。
- 修正"感知越敏锐越健忘"：pa 高 → vague 区间更宽而非整体更难召回。
- LEGACY 注入行为不变（confidence 默认 clear）。
"""

from __future__ import annotations

import time

from sylanne_alpha.memory_system import MemoryResult, MemorySystem, RecallMode


def _sys() -> MemorySystem:
    return MemorySystem(recall_mode=RecallMode.ACTIVATION)


# ---------------------------------------------------------------------------
# 三级分级
# ---------------------------------------------------------------------------

def test_classify_clear():
    m = _sys()
    assert m._classify_confidence(0.8, 0.5, 0.3) == "clear"


def test_classify_vague():
    m = _sys()
    assert m._classify_confidence(0.3, 0.3, 0.3) == "vague"


def test_classify_tot_by_importance():
    """激活低但重要性高 → 舌尖现象（而非彻底遗忘）。"""
    m = _sys()
    assert m._classify_confidence(0.05, 0.8, 0.2) == "tot"


def test_classify_tot_by_emotion():
    """激活低但情感强 → 舌尖现象。"""
    m = _sys()
    assert m._classify_confidence(0.05, 0.3, 0.7) == "tot"


def test_classify_none_when_all_low():
    """激活/重要性/情感都低 → 彻底想不起（None）。"""
    m = _sys()
    assert m._classify_confidence(0.05, 0.3, 0.3) is None


# ---------------------------------------------------------------------------
# 情感特权加成
# ---------------------------------------------------------------------------

def test_emotion_privilege_boosts_congruent():
    """强情绪 + 心境契合 → 激活被抬高。"""
    m = _sys()
    base = 0.3
    boosted = m._compute_final_activation(base, emotional_weight=0.9,
                                          current_warmth=0.8, temperature=0.8)
    assert boosted > base


def test_emotion_privilege_no_boost_when_weak():
    """情感弱（<=0.6）不加成。"""
    m = _sys()
    base = 0.3
    same = m._compute_final_activation(base, emotional_weight=0.4,
                                       current_warmth=0.8, temperature=0.8)
    assert same == base


def test_emotion_privilege_clamped():
    m = _sys()
    out = m._compute_final_activation(0.95, 1.0, 1.0, 1.0)
    assert out <= 1.0


# ---------------------------------------------------------------------------
# 情感旁路
# ---------------------------------------------------------------------------

def test_emotion_bypass_triggers_on_mood():
    """心境带情绪时，语义不相关但情感同频的强情绪记忆被召回。"""
    m = _sys()
    now = time.time()
    m.write_summary("今天天气真好", temperature=0.1)
    sad = m.write_summary("那天你说工作压力很大很难过", source_turns=3,
                          temperature=-0.8, importance=0.8)
    sad.created_at = now - 3600 * 24 * 30
    sad.last_recalled_ts = 0.0
    sad.actr_acc = 1.0
    results = m.recall("随便聊聊", current_warmth=-0.6, limit=5)
    texts = [r.text for r in results]
    assert any("工作压力" in t for t in texts), "心境低落时应召回同频情绪记忆"


def test_emotion_bypass_silent_when_neutral():
    """中性心境（|warmth|<0.3）不触发情感旁路，不被无关旧情绪打断。"""
    m = _sys()
    now = time.time()
    sad = m.write_summary("那天你说工作压力很大很难过", source_turns=3,
                          temperature=-0.8, importance=0.8)
    sad.created_at = now - 3600 * 24 * 30
    sad.last_recalled_ts = 0.0
    sad.actr_acc = 1.0
    results = m.recall("今天午饭吃什么", current_warmth=0.0, limit=5)
    texts = [r.text for r in results]
    assert not any("工作压力" in t for t in texts), "中性闲聊不该翻出旧情绪记忆"


def test_emotion_bypass_mood_congruent_direction():
    """开心时不该翻出难过的事（情绪方向需同向）。"""
    m = _sys()
    now = time.time()
    sad = m.write_summary("那次吵架很伤心", source_turns=3,
                          temperature=-0.8, importance=0.8)
    sad.created_at = now - 3600 * 24 * 30
    sad.last_recalled_ts = 0.0
    sad.actr_acc = 1.0
    results = m.recall("好开心啊", current_warmth=0.7, limit=5)
    assert not any("吵架" in r.text for r in results)


# ---------------------------------------------------------------------------
# 分级注入
# ---------------------------------------------------------------------------

def _mk(text: str, confidence: str, temperature: float = 0.0) -> MemoryResult:
    return MemoryResult(
        text=text, layer="L1", weight=1.0, relevance=0.5, clarity=1.0,
        temperature=temperature, final_score=0.5, created_at=time.time(),
        confidence=confidence,
    )


def test_injection_clear_wording():
    m = _sys()
    out = m.format_recall_injection([_mk("你喜欢拿铁", "clear")], max_items=3)
    assert "你喜欢拿铁" in out


def test_injection_vague_wording():
    m = _sys()
    out = m.format_recall_injection([_mk("我们聊过旅行计划", "vague")], max_items=3)
    assert "依稀记得" in out
    assert "记得不太清" in out


def test_injection_tot_hides_content():
    """舌尖现象不直述记忆内容，只给情感线索。"""
    m = _sys()
    out = m.format_recall_injection(
        [_mk("用户的银行卡密码是1234", "tot", temperature=-0.7)], max_items=3
    )
    assert "1234" not in out  # 内容不泄露
    assert "记不太清" in out
    assert "情绪有点低落" in out  # 负向情感线索


def test_injection_legacy_unchanged():
    """LEGACY 结果（confidence 默认 clear）注入行为不变。"""
    m = _sys()
    r = MemoryResult(
        text="确信的记忆", layer="L1", weight=1.0, relevance=0.5, clarity=1.0,
        temperature=0.0, final_score=0.5, created_at=time.time(),
    )
    assert r.confidence == "clear"
    out = m.format_recall_injection([r], max_items=3)
    assert "确信的记忆" in out
    assert "依稀记得" not in out


# ---------------------------------------------------------------------------
# 修正"越敏锐越健忘"反直觉
# ---------------------------------------------------------------------------

def test_high_perception_widens_vague_not_forgets():
    """高 perception_acuity → clear 门槛升高（分辨更细），但 tot 下限不随之升高，
    即低激活记忆仍以 vague/tot 浮现，而非整体更难召回。"""
    sharp = MemorySystem(recall_mode=RecallMode.ACTIVATION, perception_acuity=0.9)
    dull = MemorySystem(recall_mode=RecallMode.ACTIVATION, perception_acuity=0.1)
    # 高感知：theta_clear 更高（更挑剔确信），但 theta_tot 由 C 决定、不被 pa 抬高
    assert sharp._params["theta_clear"] > dull._params["theta_clear"]
    # 一个中等激活的记忆：高感知者归为 vague（依稀），不是直接遗忘
    mid_act = (sharp._params["theta_clear"] + sharp._params["theta_tot"]) / 2
    assert sharp._classify_confidence(mid_act, 0.3, 0.3) in ("vague", "clear")
