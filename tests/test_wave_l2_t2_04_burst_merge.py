"""Wave-L2/T2-04：连发不缝合（always-on）。

杀的问题：用户快速连发几条消息被碎片防抖用空格糊成一句，边界全丢，LLM 逐句逐点
公式化回应（客服感的根因之一）；固定 1.5s/4s 防抖窗口不管打字快慢一刀切，慢打字
的人容易被切断。

覆盖：
  ① LLMRequestPipeline._merge_fragments：换行拼接 + N>=2 时前缀连发标记；N==1
     不加标记（单条碎片本就该原样透传）。
  ② LLMRequestPipeline._adaptive_max_wait：画像可用时 clamp 到 [1.5, 8.0]，画像
     不成熟（median_gap=None）时原样回退配置值。
  ③ RhythmLearner.get_median_inter_message_gap / RhythmProfile.median_gap_seconds：
     样本不足 → None；样本足够 → 真实中位数。
  ④ v2core.integration._apply_burst_cue_scratch + fragment._burst_line /
     build_mind_fragment：cue 只在本轮真发生连发合并（event 带
     `_sylanne_burst_count>=2`）时渲染，其余轮次不占位。
"""

from __future__ import annotations

from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline
from sylanne_alpha.rhythm_learner import RhythmLearner, RhythmProfile
from sylanne_alpha.v2core import fragment as frag
from sylanne_alpha.v2core import integration as ig
from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase


def _ctx(text: str = "在吗") -> BeatContext:
    return BeatContext(
        session_key="u",
        event=None,
        body=BodySnapshot(session_key="u", turns=1),
        text=text,
        phase=Phase.PERCEPT,
        domains={},
    )


class _FakeEvent:
    """最小事件替身：只需要能被 getattr(event, '_sylanne_burst_count', ...) 读到。"""

    def __init__(self, burst_count=None) -> None:
        if burst_count is not None:
            self._sylanne_burst_count = burst_count


# ---------------------------------------------------------------------------
# ① _merge_fragments：换行拼接 + 连发标记
# ---------------------------------------------------------------------------


class TestMergeFragments:
    def test_single_fragment_no_marker(self) -> None:
        merged = LLMRequestPipeline._merge_fragments(["就这一句"])
        assert merged == "就这一句"
        assert "连着发了" not in merged

    def test_two_fragments_newline_joined_with_marker(self) -> None:
        merged = LLMRequestPipeline._merge_fragments(["第一条", "第二条"])
        assert merged == "『(他连着发了2条)』\n第一条\n第二条"
        # 边界保留：换行拼接，不是空格糊成一句
        assert " ".join(["第一条", "第二条"]) not in merged

    def test_three_fragments_marker_count_matches(self) -> None:
        merged = LLMRequestPipeline._merge_fragments(["a", "b", "c"])
        assert merged.startswith("『(他连着发了3条)』\n")
        assert merged == "『(他连着发了3条)』\na\nb\nc"

    def test_empty_list_returns_empty_string(self) -> None:
        assert LLMRequestPipeline._merge_fragments([]) == ""


# ---------------------------------------------------------------------------
# ② _adaptive_max_wait：clamp + 低置信度回退
# ---------------------------------------------------------------------------


class TestAdaptiveMaxWait:
    def test_none_median_gap_falls_back_to_configured(self) -> None:
        assert LLMRequestPipeline._adaptive_max_wait(4.0, None) == 4.0
        assert LLMRequestPipeline._adaptive_max_wait(2.5, None) == 2.5

    def test_median_gap_within_range_used_directly(self) -> None:
        assert LLMRequestPipeline._adaptive_max_wait(4.0, 3.0) == 3.0

    def test_median_gap_clamped_to_lower_bound(self) -> None:
        assert LLMRequestPipeline._adaptive_max_wait(4.0, 0.2) == 1.5

    def test_median_gap_clamped_to_upper_bound(self) -> None:
        assert LLMRequestPipeline._adaptive_max_wait(4.0, 30.0) == 8.0

    def test_boundary_values_pass_through(self) -> None:
        assert LLMRequestPipeline._adaptive_max_wait(4.0, 1.5) == 1.5
        assert LLMRequestPipeline._adaptive_max_wait(4.0, 8.0) == 8.0


# ---------------------------------------------------------------------------
# ③ RhythmLearner/RhythmProfile：消息间隔中位数
# ---------------------------------------------------------------------------


class TestMedianInterMessageGap:
    def test_profile_insufficient_gap_samples_returns_none(self) -> None:
        profile = RhythmProfile()
        # 只塞 2 个间隔样本（<3 门槛）
        profile._inter_msg_gaps.append(2.0)
        profile._inter_msg_gaps.append(3.0)
        assert profile.median_gap_seconds() is None

    def test_profile_median_with_enough_samples(self) -> None:
        profile = RhythmProfile()
        for gap in (1.0, 5.0, 3.0):
            profile._inter_msg_gaps.append(gap)
        # sorted -> [1.0, 3.0, 5.0]，中位数 3.0
        assert profile.median_gap_seconds() == 3.0

    def test_learner_no_profile_returns_none(self) -> None:
        learner = RhythmLearner()
        assert learner.get_median_inter_message_gap("no-such-session") is None

    def test_learner_low_confidence_profile_returns_none(self) -> None:
        learner = RhythmLearner(intimacy_threshold=0.0)
        # 亲密度门槛设 0，保证 observe 能建画像；但样本数不足 8 条 → confidence 仍是 0
        engine_obs = {"warmth": 1.0, "coherence": 1.0, "tension": 0.0}
        t = 1000.0
        for i in range(3):
            learner.observe_user_message("s1", f"消息{i}", t, engine_obs)
            t += 2.0
        assert learner.get_median_inter_message_gap("s1") is None

    def test_learner_mature_profile_returns_real_median(self) -> None:
        learner = RhythmLearner(intimacy_threshold=0.0)
        engine_obs = {"warmth": 1.0, "coherence": 1.0, "tension": 0.0}
        t = 1000.0
        # 置信度 = (n-8)/(60-8)，需要 >=0.1 才跨过 get_median_inter_message_gap 门槛
        # （与 get_rhythm_params 同门槛），n=8 时置信度仍是 0——多发几条留足余量。
        for i in range(20):
            learner.observe_user_message("s1", f"消息{i}", t, engine_obs)
            t += 4.0
        gap = learner.get_median_inter_message_gap("s1")
        assert gap is not None
        assert gap == 4.0


# ---------------------------------------------------------------------------
# ④ integration._apply_burst_cue_scratch + fragment 渲染
# ---------------------------------------------------------------------------


class TestBurstCueScratch:
    def test_no_attribute_no_cue(self) -> None:
        ctx = _ctx()
        ig._apply_burst_cue_scratch(_FakeEvent(), ctx)
        assert "burst_cue" not in ctx.scratch

    def test_burst_count_one_no_cue(self) -> None:
        """单条碎片（没有真正连发）不该触发提示。"""
        ctx = _ctx()
        ig._apply_burst_cue_scratch(_FakeEvent(burst_count=1), ctx)
        assert "burst_cue" not in ctx.scratch

    def test_burst_count_two_sets_cue(self) -> None:
        ctx = _ctx()
        ig._apply_burst_cue_scratch(_FakeEvent(burst_count=2), ctx)
        assert ctx.scratch.get("burst_cue") is True

    def test_burst_count_many_sets_cue(self) -> None:
        ctx = _ctx()
        ig._apply_burst_cue_scratch(_FakeEvent(burst_count=5), ctx)
        assert ctx.scratch.get("burst_cue") is True

    def test_non_numeric_attribute_no_crash_no_cue(self) -> None:
        ctx = _ctx()
        ig._apply_burst_cue_scratch(_FakeEvent(burst_count="oops"), ctx)
        assert "burst_cue" not in ctx.scratch


class TestBurstLineRendering:
    def test_no_cue_silent(self) -> None:
        assert frag._burst_line(_ctx()) == ""

    def test_cue_renders_line(self) -> None:
        c = _ctx()
        c.scratch["burst_cue"] = True
        assert frag._burst_line(c) == frag._BURST_LINE

    def test_reaches_fragment_end_to_end_only_on_burst_turn(self) -> None:
        c = _ctx()
        c.scratch["burst_cue"] = True
        out = frag.build_mind_fragment(c, {})
        assert frag._BURST_LINE in out

    def test_no_scratch_no_line_in_fragment(self) -> None:
        c = _ctx()
        out = frag.build_mind_fragment(c, {})
        assert frag._BURST_LINE not in out
