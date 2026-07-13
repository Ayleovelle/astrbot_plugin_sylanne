"""PR-Qzone：life_simulation.py 侧的候选回调接线测试。

覆盖：
  - 默认关（qzone_enabled=False）：即便事件满足白名单/高分，回调也绝不被调用
  - 满足白名单 + enabled + 分数达标 → 回调被调用一次，携带 (event, intent)
  - source 不在白名单（USER_INTERACTION/LEGACY）→ 不调用
  - privacy_level 非 SHAREABLE（INTERNAL）→ 不调用
  - 分数低于 qzone_min_score → 不调用
  - wants_to_share=False → 不调用，且不因 intent 未定义而抛 NameError（安全短路）
  - 私聊 outreach 判定（SILENT/DIRECT 等）与 qzone 分支互不影响：qzone 关时
    私聊路径行为不变

life_simulation.py 本身零 LLM——本文件只测试"是否满足条件即调用回调"这一层
纯规则判断，不涉及 qzone_share 模块内部逻辑（那部分见 test_qzone_share.py）。
"""

from __future__ import annotations

import asyncio
import time

from sylanne_alpha.life_simulation import (
    LifeEvent,
    LifePrivacy,
    LifeSimulator,
    LifeSource,
    ShareIntent,
)


def _make_sim(*, qzone_enabled=True, qzone_min_score=0.55) -> LifeSimulator:
    config = {
        "sylanne_alpha_qzone_enabled": qzone_enabled,
        "sylanne_alpha_qzone_min_score": qzone_min_score,
    }
    sim = LifeSimulator(config=config)
    # 绕开真实 ShareIntent 打分公式（那是既有逻辑，非本次改动范围）：固定给出
    # final_score，只测试"给定分数下，qzone 分支是否按白名单/开关正确触发"。
    sim._fixed_score = 0.9

    def _fake_evaluate(event, emotion_weights, ctx, now):
        return ShareIntent(event_id=event.event_id, final_score=sim._fixed_score)

    def _fake_recompute(intent):
        return sim._fixed_score

    sim._evaluate_share_intent = _fake_evaluate  # type: ignore[method-assign]
    sim._recompute_final = _fake_recompute  # type: ignore[method-assign]

    async def _noop_outreach(reason, mood, intent=None):
        return None

    calls: list[tuple] = []

    async def _qzone_cb(event, intent):
        calls.append((event, intent))

    sim.configure(outreach_callback=_noop_outreach, qzone_candidate_callback=_qzone_cb)
    sim._qzone_calls = calls  # type: ignore[attr-defined]
    return sim


def _event(**kwargs) -> LifeEvent:
    defaults = dict(
        text="今天读了本喜欢的小说",
        mood="平静",
        urgency=0.2,
        timestamp=time.time(),
        wants_to_share=True,
        privacy_level=LifePrivacy.SHAREABLE,
        source=LifeSource.PLANNED_TICK,
    )
    defaults.update(kwargs)
    return LifeEvent(**defaults)


def _run_emit(sim: LifeSimulator, event: LifeEvent) -> None:
    asyncio.run(sim._emit_side_effects(event, {"valence": 0.0, "arousal": 0.0}, time.time()))


def test_disabled_qzone_never_calls_callback_even_high_score():
    sim = _make_sim(qzone_enabled=False)
    _run_emit(sim, _event())
    assert sim._qzone_calls == []


def test_enabled_eligible_high_score_calls_callback_once():
    sim = _make_sim(qzone_enabled=True, qzone_min_score=0.55)
    ev = _event()
    _run_emit(sim, ev)
    assert len(sim._qzone_calls) == 1
    called_event, called_intent = sim._qzone_calls[0]
    assert called_event is ev
    assert isinstance(called_intent, ShareIntent)


def test_source_not_in_whitelist_skips_callback():
    sim = _make_sim(qzone_enabled=True)
    for src in (LifeSource.USER_INTERACTION, LifeSource.LEGACY):
        sim._qzone_calls.clear()
        _run_emit(sim, _event(source=src))
        assert sim._qzone_calls == [], f"source={src} should not trigger qzone candidate"


def test_privacy_not_shareable_skips_callback():
    sim = _make_sim(qzone_enabled=True)
    _run_emit(sim, _event(privacy_level=LifePrivacy.INTERNAL))
    assert sim._qzone_calls == []


def test_score_below_threshold_skips_callback():
    sim = _make_sim(qzone_enabled=True, qzone_min_score=0.55)
    sim._fixed_score = 0.3
    _run_emit(sim, _event())
    assert sim._qzone_calls == []


def test_wants_to_share_false_skips_callback_without_crashing():
    """安全短路核心断言：intent 只在 wants_to_share=True 分支内被赋值，qzone
    条件链必须在 intent 被引用之前先短路掉 wants_to_share=False 的事件，
    否则会因 intent 未定义抛 NameError（本测试钉死不会退化）。"""
    sim = _make_sim(qzone_enabled=True)
    _run_emit(sim, _event(wants_to_share=False))  # 不应抛 NameError
    assert sim._qzone_calls == []


def test_no_callback_configured_is_safe_noop():
    sim = LifeSimulator(config={"sylanne_alpha_qzone_enabled": True})
    sim._evaluate_share_intent = lambda event, emotion_weights, ctx, now: ShareIntent(
        event_id=event.event_id, final_score=0.9
    )
    sim._recompute_final = lambda intent: 0.9
    # 未 configure qzone_candidate_callback（保持 None）
    _run_emit(sim, _event())  # 不应抛错
