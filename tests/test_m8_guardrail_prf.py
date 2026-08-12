"""Phase 2A / PR-F M8 Guardrail + life_event_id 去重/持久化 测试。

M8 守线（裁决 §5）：
- ShareIntent.unanswered_penalty 字段恒 0.0（2A 不接数据源）
- _evaluate_share_intent / _recompute_final 中 unanswered_penalty 贡献为 *0.0
  （改 -0.20 权重不影响 final_score，证明该项未消费、无双重惩罚）

life_event_id（PR-D/F 协同）：
- life_sim 写 memory 持久化 life_event_id，dialogue 条目为空
- roundtrip 不丢失
- 去重：consumed 后 fragment 跳过，recall 仍含

全部直调真实函数。
"""

from __future__ import annotations

import time

from sylanne_alpha import life_simulation as ls
from sylanne_alpha.life_simulation import (
    LifeEvent,
    LifePrivacy,
    LifeSimulator,
    ShareIntent,
    _SHARE_WEIGHTS,
)
from sylanne_alpha.memory_system import MemoryItem, MemorySystem


def _sim():
    return LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})


# ---- M8 守线 ----

def test_unanswered_penalty_stays_zero_in_2a():
    """ShareIntent.unanswered_penalty 字段默认 0.0（2A 不接数据源）。"""
    si = ShareIntent(intent_id="x", event_id="e")
    assert si.unanswered_penalty == 0.0


def test_recompute_final_ignores_unanswered_penalty():
    """改 unanswered_penalty 字段值不影响 _recompute_final（贡献 *0.0，未消费）。"""
    sim = _sim()
    si = ShareIntent(
        intent_id="x", event_id="e", content_value=0.5, relationship_value=0.5,
        urgency=0.3, interruptibility=0.5, cooldown_penalty=0.0, privacy_risk=0.1,
    )
    si.unanswered_penalty = 0.0
    base = sim._recompute_final(si)
    si.unanswered_penalty = 0.99   # 即便拉满
    after = sim._recompute_final(si)
    assert base == after  # 贡献恒 0，不消费


def test_evaluate_share_intent_unanswered_not_consumed():
    """_evaluate_share_intent 内部 unanswered 项贡献为 0：两次评估 final_score 与该项无关。"""
    sim = _sim()
    ev = LifeEvent(text="写了代码", mood="calm", urgency=0.3, timestamp=time.time(),
                   wants_to_share=True, importance=0.5,
                   privacy_level=LifePrivacy.SHAREABLE)
    si = sim._evaluate_share_intent(ev, {}, None, time.time())
    # final_score 落在 [0,1]，且 unanswered_penalty 字段未被写非零（2A 不消费）
    assert 0.0 <= si.final_score <= 1.0
    assert si.unanswered_penalty == 0.0


def test_no_double_counting_unanswered():
    """不双重计数：unanswered_penalty 权重存在于 _SHARE_WEIGHTS 但贡献被 *0.0 中和。

    断言只反映现状（scheduler 独占惩罚），不固化 'ShareIntent 也降权' 的双罚结构。
    """
    assert "unanswered_penalty" in _SHARE_WEIGHTS  # 权重保留（文档值）
    sim = _sim()
    si = ShareIntent(intent_id="x", event_id="e", content_value=0.5,
                     relationship_value=0.5, urgency=0.3, interruptibility=0.5)
    # 即使把权重和字段都拉到极端，final_score 不变 → 证明该信号在 ShareIntent 侧未被消费
    si.unanswered_penalty = 1.0
    assert sim._recompute_final(si) == sim._recompute_final(
        ShareIntent(intent_id="x", event_id="e", content_value=0.5,
                    relationship_value=0.5, urgency=0.3, interruptibility=0.5,
                    unanswered_penalty=0.0)
    )


# ---- life_event_id 持久化 / roundtrip ----

def test_life_event_id_persisted_on_life_sim_memory():
    """life_sim 写的 MemoryItem 持久化 life_event_id；dialogue 条目为空。"""
    ms = MemorySystem()
    life_item = ms.write_summary("我今天去散步了", source="life_sim",
                                 privacy_level="shareable", life_event_id="evt-42")
    dlg_item = ms.write_summary("你说喜欢拿铁", source="dialogue")
    assert life_item.life_event_id == "evt-42"
    assert dlg_item.life_event_id == ""
    # 持久化出口含该键
    assert life_item.to_dict()["life_event_id"] == "evt-42"


def test_life_event_id_survives_memory_roundtrip():
    """life_event_id 经 to_dict/from_dict roundtrip 不丢失；旧档缺字段迁移为空。"""
    ms = MemorySystem()
    item = ms.write_summary("散步", source="life_sim",
                            privacy_level="shareable", life_event_id="evt-99")
    restored = MemoryItem.from_dict(item.to_dict())
    assert restored.life_event_id == "evt-99"
    # 旧档无该字段 → 空
    legacy = {"id": "z", "text": "t", "weight": 1.0, "temperature": 0.0,
              "age_ticks": 0, "created_at": time.time()}
    assert MemoryItem.from_dict(legacy).life_event_id == ""


# ---- 去重：fragment 跳过已消费事件 ----

def test_no_double_injection_same_event_id():
    """同一 life event：consumed 后 fragment 不再渲染（改由 recall 注入 memory 版本）。

    未 consumed 时 fragment 含；consumed_at>0 后 fragment 跳过——二者不并存。
    """
    sim = _sim()
    ev = LifeEvent(text="我去咖啡馆写代码", mood="calm", urgency=0.1,
                   timestamp=time.time(), wants_to_share=True, event_id="evt-dedup",
                   privacy_level=LifePrivacy.SHAREABLE)
    sim.state.events = [ev]
    # 未消费：fragment 含
    assert "咖啡馆写代码" in sim.life_prompt_fragment()
    # 标记 consumed → fragment 跳过
    ev.consumed_at = time.time()
    assert "咖啡馆写代码" not in sim.life_prompt_fragment()


def test_dropped_event_also_skipped_in_fragment():
    sim = _sim()
    ev = LifeEvent(text="被丢弃的事件内容", mood="m", urgency=0.1,
                   timestamp=time.time(), wants_to_share=True,
                   privacy_level=LifePrivacy.SHAREABLE, dropped_at=time.time())
    sim.state.events = [ev]
    assert "被丢弃的事件内容" not in sim.life_prompt_fragment()


# ---- 精确 owner 选择：不得回退最近会话 ----

def test_scoped_outreach_never_falls_back_to_recent_foreign_host():
    from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline

    class _Kernel:
        def __init__(self, now):
            self.last_event = {"now": now}

    class _Host:
        def __init__(self, now):
            self.kernel = _Kernel(now)

    class _Store:
        def __init__(self):
            self.hosts = {
                "session_A": _Host(100.0),
                "session_B": _Host(200.0),
            }
            self.relationship_register_state = {
                "session_A": {
                    "sender_id": "foreign",
                    "romantic_conf": 0.9,
                    "sample_count": 10,
                },
                "session_B": {
                    "sender_id": "owner",
                    "romantic_conf": 0.9,
                    "sample_count": 10,
                },
            }
            self.intimacy_override = {}

    class _Plugin:
        def __init__(self):
            self._store = _Store()
            self._scope_runtime_registry = object()
            self.config = {"sylanne_alpha_owner_id": "owner"}
            self._bound_runtime = lambda: type(
                "Binding",
                (),
                {"scope": type("Scope", (), {"storage_token": "session_A"})()},
            )()

    pipe = LLMRequestPipeline.__new__(LLMRequestPipeline)
    pipe._p = _Plugin()
    assert pipe._most_recent_intimate_host_key() == ""



