"""Wave-L2/T2-04：连发不缝合（always-on）。

杀的问题：用户快速连发几条消息被碎片防抖用空格糊成一句，边界全丢，LLM 逐句逐点
公式化回应（客服感的根因之一）；固定 1.5s/4s 防抖窗口不管打字快慢一刀切，慢打字
的人容易被切断。

覆盖：
  ① LLMRequestPipeline._merge_fragments：换行拼接，不加任何标记。
     review 修复（contrib）：曾经 N>=2 时会加一句『(他连着发了N条)』标记并
     写进 request.prompt——但 request.prompt 会被 AstrBot 写穿透持久化为
     "用户说了什么"，标记因此永久混入历史成为异物；现在改为 request.prompt/
     event.message_str/message_text 三处统一使用不带标记的纯换行拼接文本
     （见 TestMarkerRemovedFromAllPaths）。连发计数改由
     event._sylanne_burst_count 传递，burst_cue 提示的渲染从未依赖这段文本
     标记，去掉标记不影响 ④ 的行为。
  ② LLMRequestPipeline._adaptive_max_wait：画像可用时 clamp 到 [1.5, 8.0]，画像
     不成熟（median_gap=None）时原样回退配置值。median<configured 时收窄窗口是
     接受的权衡（见 TestAdaptiveMaxWaitAcceptedTradeoff）。
  ②b LLMRequestPipeline._adaptive_probe_delay（review MAJOR 修复）：真正卡住慢
     打字连发的是 probe_delay 不是 max_wait，只在"已确认在连发"（已有 ≥1 条在
     缓冲区）时才放宽单条探测等待，孤立单发消息零延迟增加。
  ③ RhythmLearner.get_median_inter_message_gap / RhythmProfile.median_gap_seconds：
     样本不足 → None；样本足够 → 真实中位数。
  ③b RhythmLearner.get_intra_burst_median_gap / RhythmProfile.intra_burst_median_gap_seconds
     （review MAJOR 修复）：过滤跨轮对话停顿污染，只用"像连发"的间隔样本。
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

    def test_two_fragments_newline_joined_no_marker(self) -> None:
        merged = LLMRequestPipeline._merge_fragments(["第一条", "第二条"])
        assert merged == "第一条\n第二条"
        assert "连着发了" not in merged
        # 边界保留：换行拼接，不是空格糊成一句
        assert " ".join(["第一条", "第二条"]) not in merged

    def test_three_fragments_no_marker(self) -> None:
        merged = LLMRequestPipeline._merge_fragments(["a", "b", "c"])
        assert merged == "a\nb\nc"
        assert "连着发了" not in merged

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


class TestAdaptiveMaxWaitAcceptedTradeoff:
    """决策记录（review MINOR-3）：median_gap < configured_max_wait 时窗口会收窄
    到低于 configured，导致这类"手速快、连发间隔本就短"的用户在长连发场景下比
    改动前更早命中 elapsed>=max_wait 的强制切分。这是接受的权衡（见
    _adaptive_max_wait 文档），本测试把它钉死成显式断言而不是隐性行为。
    """

    def test_median_below_configured_shrinks_window_and_would_force_earlier_claim(
        self,
    ) -> None:
        configured_max_wait = 4.0
        median_gap = 2.0  # 手速快，连发间隔中位数低于默认 4s
        adaptive = LLMRequestPipeline._adaptive_max_wait(configured_max_wait, median_gap)
        assert adaptive == 2.0
        assert adaptive < configured_max_wait
        # 模拟一次跨度 3s 的连发：改动前 (elapsed=3.0 < max_wait=4.0) 不会被强制
        # 切分；改动后 (elapsed=3.0 >= max_wait=2.0) 会被强制切分——这就是权衡本身。
        elapsed = 3.0
        assert elapsed < configured_max_wait
        assert elapsed >= adaptive


# ---------------------------------------------------------------------------
# ②b _adaptive_probe_delay：只在已确认连发时放宽单条探测等待（review MAJOR 修复）
# ---------------------------------------------------------------------------


class TestAdaptiveProbeDelay:
    def test_first_fragment_not_bursting_uses_configured_even_with_median(self) -> None:
        """孤立的第一条消息（already_bursting=False）不该被延迟，哪怕画像成熟。"""
        assert (
            LLMRequestPipeline._adaptive_probe_delay(1.5, 3.0, already_bursting=False)
            == 1.5
        )

    def test_none_median_falls_back_even_when_bursting(self) -> None:
        assert (
            LLMRequestPipeline._adaptive_probe_delay(1.5, None, already_bursting=True)
            == 1.5
        )

    def test_bursting_with_median_widens_probe_delay(self) -> None:
        """慢一点的连发（间隔中位数 2.5s > 默认 probe_delay 1.5s）：第 2+ 条到达后
        应该把等待撑宽到 2.5s，而不是仍然只等 1.5s（这正是 review MAJOR 指出的
        "慢打字连发对 max_wait 自适应免疫"的根治点）。
        """
        assert (
            LLMRequestPipeline._adaptive_probe_delay(1.5, 2.5, already_bursting=True)
            == 2.5
        )

    def test_bursting_median_below_configured_does_not_shrink(self) -> None:
        """放宽只应该扩大等待，不该让连发中途的探测比配置的 probe_delay 更短。"""
        assert (
            LLMRequestPipeline._adaptive_probe_delay(1.5, 0.5, already_bursting=True)
            == 1.5
        )

    def test_bursting_clamped_to_four_seconds_upper_bound(self) -> None:
        assert (
            LLMRequestPipeline._adaptive_probe_delay(1.5, 30.0, already_bursting=True)
            == 4.0
        )


# ---------------------------------------------------------------------------
# ① review 修复（contrib）：标记从所有路径里彻底移除，request.prompt / plain
# 两条路径产物完全一致（marker 不再存在，无处可漏）
# ---------------------------------------------------------------------------


class TestMarkerRemovedFromAllPaths:
    """review 修复（contrib，foreign matter persisted as user speech）：曾经
    pipeline 在赢家分支里把带『(他连着发了N条)』标记的版本喂给 request.prompt，
    而 request.prompt 正是 AstrBot 写穿透持久化为"用户说了什么"的字段
    （core/provider/entities.py assemble_context 读 self.prompt）——标记因此
    被当成用户说过的话永久存进历史。修复后 _merge_fragments 不再产出任何
    标记，request.prompt / event.message_str / message_text 三处统一使用同一
    段纯换行拼接文本，不存在"哪条路径漏了标记"的问题。
    """

    def test_plain_join_has_no_marker(self) -> None:
        texts = ["第一条", "第二条", "第三条"]
        merged_plain = "\n".join(texts)
        assert "连着发了" not in merged_plain
        assert merged_plain == "第一条\n第二条\n第三条"

    def test_prompt_path_identical_to_plain_path_no_marker(self) -> None:
        texts = ["在吗", "有空吗"]
        merged_prompt = LLMRequestPipeline._merge_fragments(texts)  # request.prompt 路径
        merged_plain = "\n".join(texts)  # event.message_str 路径
        assert "连着发了" not in merged_prompt
        assert "连着发了" not in merged_plain
        # 两条路径现在完全一致——不再有标记造成的分歧
        assert merged_prompt == merged_plain

    def test_single_fragment_plain_and_prompt_identical(self) -> None:
        texts = ["就这一句"]
        merged_prompt = LLMRequestPipeline._merge_fragments(texts)
        merged_plain = "\n".join(texts)
        assert merged_prompt == merged_plain == "就这一句"


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
# ③b RhythmLearner/RhythmProfile：连发内间隔中位数（review MAJOR 修复）
# ---------------------------------------------------------------------------


class TestIntraBurstMedianGap:
    def test_profile_insufficient_candidates_returns_none(self) -> None:
        """过滤 burst_threshold 后候选不足 3 个 → None，即便原始样本数够。"""
        profile = RhythmProfile()
        for gap in (2.0, 3.0, 20.0, 25.0, 30.0):
            profile._inter_msg_gaps.append(gap)
        # burst_threshold 默认 10.0：候选只剩 [2.0, 3.0]，不足 3 个
        assert profile.intra_burst_median_gap_seconds() is None

    def test_filters_out_cross_turn_pauses_contaminating_global_median(self) -> None:
        """核心回归：全量中位数被跨轮长停顿拉高，intra-burst 版本不该被拉高。"""
        profile = RhythmProfile()
        # 3 个"像连发"的短间隔 + 3 个几十秒的跨轮停顿
        for gap in (1.5, 2.0, 2.5, 45.0, 60.0, 90.0):
            profile._inter_msg_gaps.append(gap)
        # 全量中位数（sorted[3]）落在跨轮停顿量级，被污染
        assert profile.median_gap_seconds() == 45.0
        # intra-burst 版本只用 [1.5, 2.0, 2.5]，中位数 2.0——不被跨轮停顿污染
        assert profile.intra_burst_median_gap_seconds() == 2.0

    def test_custom_burst_threshold(self) -> None:
        profile = RhythmProfile()
        for gap in (1.0, 5.0, 9.0, 11.0, 15.0):
            profile._inter_msg_gaps.append(gap)
        # threshold=6.0 时候选 [1.0, 5.0]，不足 3 个
        assert profile.intra_burst_median_gap_seconds(burst_threshold=6.0) is None
        # threshold=12.0 时候选 [1.0, 5.0, 9.0, 11.0]，中位数取 sorted[2]=9.0
        assert profile.intra_burst_median_gap_seconds(burst_threshold=12.0) == 9.0

    def test_learner_no_profile_returns_none(self) -> None:
        learner = RhythmLearner()
        assert learner.get_intra_burst_median_gap("no-such-session") is None

    def test_learner_low_confidence_returns_none(self) -> None:
        learner = RhythmLearner(intimacy_threshold=0.0)
        engine_obs = {"warmth": 1.0, "coherence": 1.0, "tension": 0.0}
        t = 1000.0
        for i in range(3):
            learner.observe_user_message("s1", f"消息{i}", t, engine_obs)
            t += 2.0
        assert learner.get_intra_burst_median_gap("s1") is None

    def test_learner_mature_profile_filters_cross_turn_gaps(self) -> None:
        """模拟真实分布：真实会话里"孤立单条消息、隔几十秒才开口"的轮次远多于
        "连着发好几条"的轮次——这正是 review 指出的污染场景：跨轮停顿样本在
        数量上占多数，把全量中位数拉到停顿量级，intra-burst 口径不受影响。

        构造：1 次 4 条连发（3 个 2s 短间隔）+ 11 次孤立单条消息（11 个 80s
        跨轮间隔）。短间隔样本数(3) 够跨过 intra-burst 的 <3 门槛，但在全量
        17 个样本里占少数，长间隔(11)占多数。
        """
        learner = RhythmLearner(intimacy_threshold=0.0)
        engine_obs = {"warmth": 1.0, "coherence": 1.0, "tension": 0.0}
        t = 1000.0
        # 一次连发：4 条消息，3 个 2.0s 间隔
        for i in range(4):
            learner.observe_user_message("s1", f"burst{i}", t, engine_obs)
            t += 2.0
        # 之后 11 次孤立单条消息，彼此间隔 80s（含burst结束到第一条孤立消息的间隔）
        for i in range(11):
            t += 80.0
            learner.observe_user_message("s1", f"lone{i}", t, engine_obs)

        intra = learner.get_intra_burst_median_gap("s1")
        assert intra is not None
        assert intra == 2.0
        # 全量中位数被占多数的跨轮停顿样本拉高，与 intra-burst 版本不再一致——
        # 正是 review 指出的污染问题，intra-burst 口径修复了它。
        full = learner.get_median_inter_message_gap("s1")
        assert full is not None
        assert full != intra
        assert full >= 80.0


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
