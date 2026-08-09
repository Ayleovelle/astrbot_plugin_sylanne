"""Wave-L2/T3-01：状态改变消息形状——缺陷行为/表达风格的派发力学调制。

杀的缺陷：10 个缺陷行为里犯懒/冲动泄露/逃避的文本指令在说"回得短/脱口而出/拖着不碰"，
但派发参数（cps/max_part_chars/首段延迟）此前完全不受影响——纯文本装饰，力学零变化。
express.segment_bias/pause_bias 同理：只喂 fragment._style_line 的口吻提示，从没真正
改过任何数字。

覆盖四层：
  ① behavior.py：_BEHAVIORS 挂载的 modulators + _clamp_modulators 夹紧。
  ② integration.py：_compose_dispatch_modulators（行为 + 表达风格合成）与
     consume_dispatch_modulators（一次性取走 + TTL）。
  ③ llm_response_pipeline.py：_apply_dispatch_modulators（叠加到身体基线）。
  ④ 端到端：调制后的 (cps, max_part_chars, predelay) 喂进 realtime_plan，plan 输出
     可测量地变化；无调制/无信号轮完全不变（回归锚点）。
"""

from __future__ import annotations

import time

from sylanne_alpha.llm_response_pipeline import LLMResponsePipeline
from sylanne_alpha.message_dispatch import realtime_plan
from sylanne_alpha.v2core import integration as ig
from sylanne_alpha.v2core.behavior import _BEHAVIORS, _clamp_modulators, select_behavior
from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase


def _body(**kw) -> BodySnapshot:
    return BodySnapshot(session_key="u", turns=3, **kw)


# ---------------------------------------------------------------------------
# ① behavior.py：modulators 挂载 + clamp
# ---------------------------------------------------------------------------


class TestBehaviorModulators:
    def test_laziness_modulators(self) -> None:
        sel = select_behavior(_body(exhaustion=0.9, load=0.9, expression_drive=0.0), {}, {}, 1000.0)
        assert sel and sel["id"] == "laziness"
        assert sel["modulators"] == {"cps_mult": 0.75, "max_part_chars_mult": 0.8}

    def test_impulse_modulators(self) -> None:
        sel = select_behavior(_body(expression_drive=0.9, void_pressure=18.0), {}, {}, 1000.0)
        assert sel and sel["id"] == "impulse"
        assert sel["modulators"] == {"cps_mult": 1.2}

    def test_avoidance_modulators(self) -> None:
        sel = select_behavior(_body(void_pressure=24.0, boundary_pressure=0.7), {}, {}, 1000.0)
        assert sel and sel["id"] == "avoidance"
        assert sel["modulators"] == {"extra_predelay_s": 3.0}

    def test_teasing_has_no_modulators(self) -> None:
        """没在 card 名单上的行为：modulators 恒为空 dict（不是随手挂的）。"""
        sel = select_behavior(_body(warmth=0.85, tension=0.05, intimacy_gravity=0.75), {}, {}, 1000.0)
        assert sel and sel["id"] == "teasing"
        assert sel["modulators"] == {}

    def test_only_four_behaviors_carry_modulators(self) -> None:
        """card 明确只挂文本本身就在说"打字方式会变"的几条，其余留空。Wave-L2 二批
        新增 winddown（T2-03④："要转身走了"同样是打字方式会变的文本）加入这个名单。"""
        with_mods = {bid for bid, _fn, _dir, mods in _BEHAVIORS if mods}
        assert with_mods == {"laziness", "impulse", "avoidance", "winddown"}

    def test_clamp_multipliers_upper(self) -> None:
        clamped = _clamp_modulators({"cps_mult": 5.0, "max_part_chars_mult": 5.0})
        assert clamped == {"cps_mult": 1.3, "max_part_chars_mult": 1.3}

    def test_clamp_multipliers_lower(self) -> None:
        clamped = _clamp_modulators({"cps_mult": 0.01, "max_part_chars_mult": -1.0})
        assert clamped == {"cps_mult": 0.7, "max_part_chars_mult": 0.7}

    def test_clamp_predelay_bounds(self) -> None:
        assert _clamp_modulators({"extra_predelay_s": 999.0}) == {"extra_predelay_s": 5.0}
        assert _clamp_modulators({"extra_predelay_s": -3.0}) == {"extra_predelay_s": 0.0}

    def test_clamp_drops_unknown_and_malformed_keys(self) -> None:
        clamped = _clamp_modulators({"cps_mult": "not_a_float", "bogus_key": 1.0})
        assert clamped == {}

    def test_no_behavior_no_modulators(self) -> None:
        """中性 body → select_behavior 返回 None，没有 modulators 可言（上游按 {} 处理）。"""
        assert select_behavior(_body(), {}, {}, 1000.0) is None


# ---------------------------------------------------------------------------
# ② integration.py：合成 + 一次性消费
# ---------------------------------------------------------------------------


def _ctx_with(behavior_modulators=None, express=None) -> BeatContext:
    c = BeatContext(session_key="u", event=None, body=_body(), text="x",
                     phase=Phase.PERCEPT, domains={})
    if behavior_modulators is not None:
        c.scratch["behavior_modulators"] = behavior_modulators
    if express is not None:
        c.scratch["express"] = express
    return c


class TestComposeDispatchModulators:
    def test_no_signals_neutral(self) -> None:
        mods = ig._compose_dispatch_modulators(_ctx_with())
        assert mods == {"cps_mult": 1.0, "max_part_chars_mult": 1.0, "extra_predelay_s": 0.0}

    def test_behavior_only_passthrough(self) -> None:
        mods = ig._compose_dispatch_modulators(
            _ctx_with(behavior_modulators={"cps_mult": 0.75, "max_part_chars_mult": 0.8})
        )
        assert mods["cps_mult"] == 0.75
        assert mods["max_part_chars_mult"] == 0.8
        assert mods["extra_predelay_s"] == 0.0

    def test_express_segment_bias_above_threshold_shrinks_parts(self) -> None:
        """同 fragment._style_line "想多说几句" 的 1.5 阈值——过线才生效，不是线性叠加。"""
        mods = ig._compose_dispatch_modulators(_ctx_with(express={"segment_bias": 2.0, "pause_bias": 0.0}))
        assert mods["max_part_chars_mult"] == 0.9
        assert mods["extra_predelay_s"] == 0.0

    def test_express_segment_bias_below_threshold_no_effect(self) -> None:
        mods = ig._compose_dispatch_modulators(_ctx_with(express={"segment_bias": 1.0, "pause_bias": 0.0}))
        assert mods["max_part_chars_mult"] == 1.0

    def test_express_pause_bias_above_threshold_adds_predelay(self) -> None:
        """同 fragment._style_line "说话带停顿" 的 0.8 阈值。"""
        mods = ig._compose_dispatch_modulators(_ctx_with(express={"segment_bias": 0.0, "pause_bias": 1.3}))
        assert mods["extra_predelay_s"] > 0.0
        assert mods["extra_predelay_s"] <= 1.5  # 内部 min(1.5, ...) 软顶

    def test_express_pause_bias_below_threshold_no_effect(self) -> None:
        mods = ig._compose_dispatch_modulators(_ctx_with(express={"segment_bias": 0.0, "pause_bias": 0.5}))
        assert mods["extra_predelay_s"] == 0.0

    def test_behavior_and_express_combine_same_direction(self) -> None:
        """犯懒(max_part_chars_mult=0.8) + 想多说几句(再乘 0.9) → 更小，仍在 clamp 区间内。"""
        mods = ig._compose_dispatch_modulators(_ctx_with(
            behavior_modulators={"cps_mult": 0.75, "max_part_chars_mult": 0.8},
            express={"segment_bias": 2.0, "pause_bias": 0.0},
        ))
        assert abs(mods["max_part_chars_mult"] - 0.72) < 1e-9
        assert mods["max_part_chars_mult"] >= 0.7  # 仍夹在合法区间

    def test_final_clamp_holds_at_extremes(self) -> None:
        """极端 behavior 调制器（未经 behavior.py clamp 的手造场景）：compose 出口仍要夹紧。"""
        mods = ig._compose_dispatch_modulators(_ctx_with(
            behavior_modulators={"cps_mult": 10.0, "max_part_chars_mult": 0.01, "extra_predelay_s": 999.0}
        ))
        assert mods["cps_mult"] == 1.3
        assert mods["max_part_chars_mult"] == 0.7
        assert mods["extra_predelay_s"] == 5.0

    def test_malformed_express_does_not_crash(self) -> None:
        mods = ig._compose_dispatch_modulators(_ctx_with(express={"segment_bias": "nan_ish", "pause_bias": None}))
        assert mods == {"cps_mult": 1.0, "max_part_chars_mult": 1.0, "extra_predelay_s": 0.0}


class _ConsumePlugin:
    def __init__(self, *, v2core: bool = True) -> None:
        self._config = {"sylanne_enable_v2core": v2core}
        self._v2core_runtimes: dict = {}


class TestApplyV2coreResponseResetsStaleModulators:
    def test_exception_before_compose_resets_to_none_not_stale(self) -> None:
        """防泄漏：本轮 v2core 处理中途异常回落 legacy 时，turn_dispatch_modulators
        必须已清成 None——不能让异常轮误继承上一轮遗留的非中性调制器（红队命门变种：
        跨轮串味不只发生在正常路径，异常回落路径更要防）。"""
        import asyncio
        import tempfile

        from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost

        root = tempfile.mkdtemp(prefix="t3_01_leak_")

        class _P:
            _config = {"sylanne_enable_v2core": True}

            def __init__(self) -> None:
                self._h: dict = {}

            def _host(self, sk: str) -> SylanneAlphaHost:
                if sk not in self._h:
                    self._h[sk] = SylanneAlphaHost(root=root, session_key=sk)
                return self._h[sk]

            def _session_key(self, _e: object) -> str:
                return "s"

        class _Ev:
            unified_msg_origin = "s"
            message_str = "hi"

        class _Resp:
            completion_text = "hi there"

        p = _P()
        rt = ig._runtime_for(p, "s")
        rt["loaded"] = True
        rt["turn_dispatch_modulators"] = {
            "cps_mult": 1.2, "max_part_chars_mult": 1.0, "extra_predelay_s": 0.0,
            "ts": time.time(),
        }

        def _boom(*_a, **_kw):
            raise RuntimeError("forced percept failure")

        rt["runner"].run_percept_stage = _boom  # 强制在 compose 之后的路径失败

        handled = asyncio.run(ig.apply_v2core_response(p, _Ev(), _Resp()))
        assert handled is False  # 顶层 except 兜底回落 legacy
        assert rt["turn_dispatch_modulators"] is None  # 不是那份陈旧的 cps_mult=1.2


class TestConsumeDispatchModulators:
    def test_legacy_disable_key_is_ignored(self) -> None:
        p = _ConsumePlugin(v2core=False)
        p._v2core_runtimes["s"] = {"turn_dispatch_modulators": {
            "cps_mult": 1.2, "max_part_chars_mult": 1.0, "extra_predelay_s": 0.0, "ts": time.time(),
        }}
        assert ig.consume_dispatch_modulators(p, "s") == {
            "cps_mult": 1.2,
            "max_part_chars_mult": 1.0,
            "extra_predelay_s": 0.0,
        }
        assert p._v2core_runtimes["s"]["turn_dispatch_modulators"] is None

    def test_no_runtime_returns_none(self) -> None:
        p = _ConsumePlugin()
        assert ig.consume_dispatch_modulators(p, "missing_session") is None

    def test_fresh_value_consumed_once(self) -> None:
        p = _ConsumePlugin()
        p._v2core_runtimes["s"] = {"turn_dispatch_modulators": {
            "cps_mult": 1.2, "max_part_chars_mult": 0.9, "extra_predelay_s": 1.5, "ts": time.time(),
        }}
        first = ig.consume_dispatch_modulators(p, "s")
        assert first == {"cps_mult": 1.2, "max_part_chars_mult": 0.9, "extra_predelay_s": 1.5}
        # 一次性：第二次取走 → None（已被清空，不会跨轮串味）
        second = ig.consume_dispatch_modulators(p, "s")
        assert second is None

    def test_stale_value_discarded(self) -> None:
        p = _ConsumePlugin()
        p._v2core_runtimes["s"] = {"turn_dispatch_modulators": {
            "cps_mult": 1.2, "max_part_chars_mult": 1.0, "extra_predelay_s": 0.0,
            "ts": time.time() - ig._DISPATCH_MOD_TTL - 5.0,
        }}
        assert ig.consume_dispatch_modulators(p, "s") is None

    def test_none_stored_returns_none(self) -> None:
        p = _ConsumePlugin()
        p._v2core_runtimes["s"] = {"turn_dispatch_modulators": None}
        assert ig.consume_dispatch_modulators(p, "s") is None


# ---------------------------------------------------------------------------
# ③ llm_response_pipeline.py：叠加到身体基线
# ---------------------------------------------------------------------------


class TestApplyDispatchModulatorsPipeline:
    def test_no_mods_passthrough_unchanged(self) -> None:
        """card 要求：no-behavior turns unchanged。"""
        cps, max_part, predelay = LLMResponsePipeline._apply_dispatch_modulators(7.5, 48, None)
        assert cps == 7.5
        assert max_part == 48
        assert predelay == 0.0

    def test_empty_dict_also_passthrough(self) -> None:
        cps, max_part, predelay = LLMResponsePipeline._apply_dispatch_modulators(7.5, 48, {})
        assert (cps, max_part, predelay) == (7.5, 48, 0.0)

    def test_laziness_slows_and_shrinks(self) -> None:
        cps, max_part, predelay = LLMResponsePipeline._apply_dispatch_modulators(
            7.5, 48, {"cps_mult": 0.75, "max_part_chars_mult": 0.8, "extra_predelay_s": 0.0}
        )
        assert abs(cps - 5.625) < 1e-9
        assert max_part == int(round(48 * 0.8))
        assert predelay == 0.0

    def test_impulse_speeds_up(self) -> None:
        cps, _max_part, _predelay = LLMResponsePipeline._apply_dispatch_modulators(
            7.5, 48, {"cps_mult": 1.2}
        )
        assert abs(cps - 9.0) < 1e-9

    def test_avoidance_adds_predelay(self) -> None:
        _cps, _max_part, predelay = LLMResponsePipeline._apply_dispatch_modulators(
            7.5, 48, {"extra_predelay_s": 3.0}
        )
        assert predelay == 3.0

    def test_cps_reclamped_to_body_range(self) -> None:
        """极端 cps_mult(1.3) 作用在已经贴近硬顶的身体基线上：结果仍不越过 [4.5, 11]。"""
        from sylanne_alpha.llm_response_pipeline import _CPS_MAX, _CPS_MIN

        cps, _mp, _pd = LLMResponsePipeline._apply_dispatch_modulators(11.0, 48, {"cps_mult": 1.3})
        assert cps <= _CPS_MAX
        cps2, _mp2, _pd2 = LLMResponsePipeline._apply_dispatch_modulators(4.5, 48, {"cps_mult": 0.7})
        assert cps2 >= _CPS_MIN

    def test_max_part_floor_at_eight(self) -> None:
        """极端小 max_part_chars_mult 也不能把分段剁到不可读碎片（>=8 字符安全下限）。"""
        _cps, max_part, _pd = LLMResponsePipeline._apply_dispatch_modulators(
            7.5, 10, {"max_part_chars_mult": 0.7}
        )
        assert max_part >= 8


# ---------------------------------------------------------------------------
# ④ 端到端：调制后的参数喂进 realtime_plan，plan 输出可测量地变化
# ---------------------------------------------------------------------------


class TestPlanOutputMeasurablyChanges:
    def test_laziness_produces_more_and_slower_segments(self) -> None:
        """同一段较长文本：犯懒调制（更慢 cps + 更小 max_part）应产生 >= 段数、且总耗时更长。"""
        text = "今天有点累啊，不太想多说话，但还是想回你一句，晚点再聊吧，先这样。"

        base_cps, base_max_part, base_predelay = LLMResponsePipeline._apply_dispatch_modulators(
            7.5, 48, None
        )
        lazy_cps, lazy_max_part, lazy_predelay = LLMResponsePipeline._apply_dispatch_modulators(
            7.5, 48, {"cps_mult": 0.75, "max_part_chars_mult": 0.8, "extra_predelay_s": 0.0}
        )
        assert lazy_cps < base_cps
        assert lazy_max_part < base_max_part

        import random

        base_plan = realtime_plan(
            "s", text, max_part_chars=base_max_part, chars_per_second=base_cps,
            first_delay=base_predelay, rng=random.Random(7),
        )
        lazy_plan = realtime_plan(
            "s", text, max_part_chars=lazy_max_part, chars_per_second=lazy_cps,
            first_delay=lazy_predelay, rng=random.Random(7),
        )
        # 更小的 max_part_chars → 同样文本切出至少一样多、通常更多段
        assert lazy_plan["message_count"] >= base_plan["message_count"]
        # 更慢的 cps → 段内打字延迟总和不会变短
        base_total_delay = sum(p["delay_before_seconds"] for p in base_plan["message_parts"])
        lazy_total_delay = sum(p["delay_before_seconds"] for p in lazy_plan["message_parts"])
        assert lazy_total_delay >= base_total_delay - 1e-6

    def test_avoidance_delays_first_segment(self) -> None:
        text = "嗯。"
        _cps, _max_part, predelay = LLMResponsePipeline._apply_dispatch_modulators(
            7.5, 48, {"extra_predelay_s": 3.0}
        )
        think_delay = 1.0 + predelay  # 模拟 think_delay + extra_predelay 的组合
        plan = realtime_plan("s", text, first_delay=think_delay)
        assert plan["message_parts"][0]["delay_before_seconds"] == think_delay

    def test_no_behavior_turn_plan_identical_to_baseline(self) -> None:
        """回归锚点：无调制信号时，plan 输出必须与调制器接入前完全一致（同 rng 种子）。"""
        text = "今天天气不错，我们出去走走吧，记得带伞哦。"
        import random

        cps, max_part, predelay = LLMResponsePipeline._apply_dispatch_modulators(7.5, 48, None)
        modulated_plan = realtime_plan(
            "s", text, max_part_chars=max_part, chars_per_second=cps,
            first_delay=predelay, rng=random.Random(3),
        )
        baseline_plan = realtime_plan(
            "s", text, max_part_chars=48, chars_per_second=7.5,
            first_delay=0.0, rng=random.Random(3),
        )
        assert modulated_plan["message_parts"] == baseline_plan["message_parts"]
