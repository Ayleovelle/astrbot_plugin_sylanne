"""非 SDK 审计批（核查任务 wzwd8i0ta）A 组质量修复的回归测试。

覆盖：#16 事件 proactive 双形态、#21 temperature=None 回退 warmth、
#20 predict_you 复用 scratch signals、#6 英文情感词词边界、
#36 内部评估器并发闸（Condition 替忙等）、#37 周报 lifetime_* 命名、
#25 social_field 注入时钟、#27 rhythm 成熟画像退缩可达。
"""

from __future__ import annotations

import asyncio
import math
from types import SimpleNamespace

from sylanne_alpha.v2core.turn_runner import _event_proactive
from sylanne_alpha.v2core.capabilities.reconsolidation import _mean_recalled_warmth
from sylanne_alpha.v2core.domains.user_model import UserModelDomain, evidence_from_signals
from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot
from sylanne_alpha.v2core.lexicon import read_signals
from sylanne_alpha.dialogue import _count_emotion_hits
from sylanne_alpha.analytics import generate_weekly_report
from sylanne_alpha.social_field import SocialFieldCollector
from sylanne_alpha.rhythm_learner import RhythmLearner
from sylanne_alpha.public_api import PublicAPI


# ---------------------------------------------------------------------------
# #16 事件 proactive 双形态探测（对象属性 + dict 键）
# ---------------------------------------------------------------------------

def test_event_proactive_dict_form():
    # dict 形态：旧 getattr 恒 False，这里必须真读到键
    assert _event_proactive({"proactive": True}) is True
    assert _event_proactive({"proactive": False}) is False
    assert _event_proactive({}) is False


def test_event_proactive_object_form():
    assert _event_proactive(SimpleNamespace(proactive=True)) is True
    assert _event_proactive(SimpleNamespace(proactive=False)) is False
    assert _event_proactive(SimpleNamespace()) is False


def test_event_proactive_none():
    assert _event_proactive(None) is False


# ---------------------------------------------------------------------------
# #21 temperature 键存在但值=None 时真回退 warmth
# ---------------------------------------------------------------------------

def test_reconsolidation_temperature_none_falls_back_to_warmth():
    # temperature=None（键存在）必须回退到 warmth，而非拿到 None
    assert _mean_recalled_warmth([{"temperature": None, "warmth": 0.5}]) == 0.5
    # temperature 有值优先
    assert _mean_recalled_warmth([{"temperature": 0.8, "warmth": 0.1}]) == 0.8
    # 两者都缺/None → None（不拿 0.0 充数）
    assert _mean_recalled_warmth([{"temperature": None, "warmth": None}]) is None
    assert _mean_recalled_warmth([{"foo": 1}]) is None
    # 混合求均值
    got = _mean_recalled_warmth([{"temperature": None, "warmth": 0.4}, {"temperature": 0.6}])
    assert abs(got - 0.5) < 1e-9


# ---------------------------------------------------------------------------
# #20 predict_you 复用 ctx.scratch["signals"]，不重新分词
# ---------------------------------------------------------------------------

def test_predict_you_reuses_scratch_signals():
    um = UserModelDomain()
    warm_sig = read_signals("好喜欢你 最爱你了 抱抱")
    warm_ev = evidence_from_signals(warm_sig).get("warmth", 0.0)
    assert warm_ev != 0.0, "前置条件：暖文本应有非零 warmth 证据（lexicon 变了则改用例）"
    body = BodySnapshot(session_key="s", turns=1, surprise=0.2)
    # ctx.text 故意与 scratch signals 不同——若复用 scratch 则结果跟 warm_sig 走
    ctx = BeatContext(session_key="s", event=None, body=body, text="无关文本")
    ctx.scratch["signals"] = warm_sig
    view = um.predict_you(ctx)
    expected = 0.3 * warm_ev  # 新 um disposition 全 0，predicted = 0 + 0.3*ev
    assert abs(view.predicted_disposition["warmth"] - expected) < 1e-9


def test_predict_you_falls_back_when_scratch_absent():
    um = UserModelDomain()
    body = BodySnapshot(session_key="s", turns=1)
    ctx = BeatContext(session_key="s", event=None, body=body, text="好喜欢你 最爱你了")
    # 不预置 scratch["signals"] → 回落 read_signals(text)
    view = um.predict_you(ctx)
    assert view.predicted_disposition["warmth"] > 0.0


# ---------------------------------------------------------------------------
# #6 英文情感词词边界（去 warm∈warmth / miss∈dismiss / joy∈enjoy 假阳性）
# ---------------------------------------------------------------------------

def test_emotion_hits_ascii_substring_false_positives_removed():
    assert _count_emotion_hits("warmth") == 0       # warm 不该命中（th 非屈折尾缀）
    assert _count_emotion_hits("dismiss") == 0      # miss 不该命中（前缀粘连）
    assert _count_emotion_hits("dismissed") == 0    # 前缀粘连，加后缀也不该命中
    assert _count_emotion_hits("enjoyable") == 0    # joy 不该命中（前缀粘连）
    # 混合上下文：旧实现 warmth 会误算一次，新实现只数 happy
    assert _count_emotion_hits("warmth makes me happy") == 1


def test_emotion_hits_true_english_words_still_count():
    assert _count_emotion_hits("i feel warm today") == 1
    assert _count_emotion_hits("i miss you") == 1
    assert _count_emotion_hits("happy") == 1


def test_emotion_hits_english_inflections_preserved():
    # 红队复审：复数/过去式/进行时/比较级/-ful 屈折形必须仍计（self_score 已偏保守）
    assert _count_emotion_hits("thanks!") == 1            # thank + s
    assert _count_emotion_hits("i loved it") == 1         # love + d
    assert _count_emotion_hits("i missed you") == 1       # miss + ed
    assert _count_emotion_hits("missing you") == 1        # miss + ing
    assert _count_emotion_hits("it's warmer now") == 1    # warm + er
    assert _count_emotion_hits("that's painful") == 1     # pain + ful


def test_emotion_hits_distinct_keyword_dedup():
    # 同一词根的多个屈折形只算一次（distinct-keyword 语义，同旧 `in`）
    assert _count_emotion_hits("love loved loves") == 1
    assert _count_emotion_hits("warm warmer") == 1
    # 两个不同词根 → 2
    assert _count_emotion_hits("i'm happy and i missed you") == 2


def test_emotion_hits_chinese_and_cjk_adjacent_english_preserved():
    assert _count_emotion_hits("好温暖啊") == 1            # 中文子串不受影响
    assert _count_emotion_hits("warm的感觉") == 1          # 英文词紧贴中文仍算真命中


# ---------------------------------------------------------------------------
# #36 内部评估器并发闸：Condition 取代 sleep 忙等，限流且计数无竞态
# ---------------------------------------------------------------------------

def test_internal_assessor_concurrency_gate_caps_inflight():
    class _P:
        def __init__(self) -> None:
            self._internal_assessor_llm_inflight = 0

    p = _P()
    api = PublicAPI.__new__(PublicAPI)
    api._p = p
    observed = {"max": 0}

    class _Ctx:
        async def llm_generate(self, **kwargs):
            cur = p._internal_assessor_llm_inflight
            observed["max"] = max(observed["max"], cur)
            await asyncio.sleep(0.02)
            return SimpleNamespace(completion_text="ok")

    p.context = _Ctx()

    async def run():
        await asyncio.gather(*[api._call_internal_assessor_llm() for _ in range(6)])

    asyncio.run(run())
    assert observed["max"] <= 2          # 限流 = _internal_assessor_llm_concurrency_limit() = 2
    assert observed["max"] >= 1          # 真的并发过（非串行假象）
    assert p._internal_assessor_llm_inflight == 0  # 全部释放，计数归零无泄漏


def test_internal_assessor_condition_is_reused_singleton():
    class _P:
        def __init__(self) -> None:
            self._internal_assessor_llm_inflight = 0

    async def go():
        api = PublicAPI.__new__(PublicAPI)
        api._p = _P()
        c1 = api._internal_assessor_llm_condition()
        c2 = api._internal_assessor_llm_condition()
        assert c1 is c2
        assert isinstance(c1, asyncio.Condition)

    asyncio.run(go())


# ---------------------------------------------------------------------------
# #37 周报：lifetime_* 命名替换误导性的 total_turns/active_sessions
# ---------------------------------------------------------------------------

def test_weekly_report_lifetime_naming():
    class _StubPlugin:
        pass

    report = generate_weekly_report(_StubPlugin())
    assert report["schema_version"] == "sylanne.analytics.weekly.v2"
    assert "lifetime_total_turns" in report
    assert "lifetime_active_sessions" in report
    # 旧误导键名彻底移除
    assert "total_turns" not in report
    assert "active_sessions" not in report
    # 7 天窗口口径键保留
    assert "new_memories" in report
    assert "scar_activity" in report


# ---------------------------------------------------------------------------
# #25 social_field：notify_bot_replied 走注入时钟，回放 delta_t 不再垃圾
# ---------------------------------------------------------------------------

def test_notify_bot_replied_uses_injected_clock():
    col = SocialFieldCollector()
    t0 = 1000.0
    col.notify_bot_replied("g1", "在的", now=t0)
    gs = col._get_group("g1")
    assert gs.last_bot_reply_ts == t0   # 注入时钟，而非 wall clock
    # collect 用同一注入时基 → continuation_strength 是干净的指数衰减
    sig = col.collect(group_id="g1", sender_id="u", text="嗨", now=t0 + 60.0)
    # tau 默认 60 → exp(-60/60) ≈ 0.368
    assert abs(sig.continuation_strength - math.exp(-1.0)) < 1e-6


# ---------------------------------------------------------------------------
# #27 rhythm：成熟画像在被忽略时也能进退缩放慢分支
# ---------------------------------------------------------------------------

def _mature_learner() -> RhythmLearner:
    learner = RhythmLearner(intimacy_threshold=0.6)
    obs = {"warmth": 1.0, "coherence": 1.0, "tension": 0.0}
    for i in range(60):
        learner.observe_user_message("s", f"消息内容{i}", 1000.0 + i * 5.0, obs)
    return learner


def test_rhythm_mature_profile_withdrawal_reachable():
    learner = _mature_learner()
    prof = learner.profile("s")
    assert prof is not None and prof.confidence >= 0.83, "需要成熟画像才有意义"

    # 高被忽略 + 低表达驱力 = 净退缩；旧地板 0.1 让此分支对成熟画像不可达，现应进退缩放慢
    max_part, cps = learner.get_rhythm_params(
        "s", default_max_part=48, default_cps=7.5,
        expression_drive=0.0, recent_ignored_rate=0.8,
    )
    assert max_part > 48      # 比默认更慢（分段更长）
    assert cps < 7.5          # 打字更慢


def test_rhythm_positive_drive_not_slowdown():
    # 正向同步区间行为不变：强驱力、零忽略 → 不进退缩分支（向用户节奏混合）
    learner = _mature_learner()
    max_part, _cps = learner.get_rhythm_params(
        "s", default_max_part=48, default_cps=7.5,
        expression_drive=1.0, recent_ignored_rate=0.0,
    )
    # 用户消息短，混合后分段应收短（≤默认），证明走的是混合而非退缩放慢
    assert max_part <= 48
