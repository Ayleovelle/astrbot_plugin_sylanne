"""Wave-L2/T1-03：夜间温和版（config: sylanne_alpha_night_rhythm_enabled，默认关）。

杀的问题：她此前对深夜和白天用完全相同的读信/打字速度回复——不是"一直在"该有的
质感，缺一点"深夜人有点迷糊"的软纹理。红队铁律：绝不能让这层拖成分钟级不理人，
更不能拖慢『睡不着』『在吗』这类低唤醒高孤独感消息——夜里一直在是核心安全感，
这张卡只加轻微质感。

覆盖：
  ① proactive_bridge.is_night_fast_reply_exempt：豁免关键词纯函数。
  ② llm_response_pipeline._apply_night_rhythm：最终力学缩放（cps/think_delay），
     纯函数、seeded rng、硬顶验证。
  ③ llm_response_pipeline._night_rhythm_active：总开关 + 免打扰时段 + 豁免关键词
     三道闸门的接线（复用 proactive_bridge._in_quiet_hours）。
  ④ v2core.integration._apply_night_texture_scratch + _apply_v2core_feature_flags：
     心象线索注入（quiet hours 软纹理 + 首条夜间消息小概率"刚被叫醒"）。
  ⑤ v2core.fragment._night_line + build_mind_fragment：渲染层，端到端到 system
     prompt 片段。
  ⑥ 配置关闭 = 全链路零变化（day path untouched）。
"""

from __future__ import annotations

import datetime as _dt
import random
from types import SimpleNamespace

from sylanne_alpha.llm_response_pipeline import (
    _CPS_MAX,
    _CPS_MIN,
    _NIGHT_CPS_DELTA,
    _NIGHT_THINK_DELAY_CAP,
    _NIGHT_THINK_DELAY_MULT_MAX,
    _NIGHT_THINK_DELAY_MULT_MIN,
    LLMResponsePipeline,
)
from sylanne_alpha.proactive_bridge import (
    NIGHT_EXEMPT_KEYWORDS,
    ProactiveBridge,
    is_night_fast_reply_exempt,
)
from sylanne_alpha.v2core import fragment as frag
from sylanne_alpha.v2core import integration as ig
from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase


# ---------------------------------------------------------------------------
# 测试替身：复用 test_proactive_bridge.py 同款"必然覆盖/必然不覆盖当前小时"技巧，
# 避免真依赖系统时钟造成 flaky。
# ---------------------------------------------------------------------------


class _FakeProactivePlugin:
    """模拟大饼插件：只暴露 _get_session_config 供 _daping_schedule_conf 读取。"""

    def __init__(self, quiet_hours: str) -> None:
        self.timezone = None
        self._schedule_settings = {"quiet_hours": quiet_hours}
        self.session_override_manager = object()

    def _get_session_config(self, sid: str) -> dict:
        return {"schedule_settings": dict(self._schedule_settings)}

    async def check_and_chat(self, sid: str) -> None:
        pass

    async def _schedule_next_chat_and_save(self, sid: str) -> None:
        pass


class _FakeMeta:
    def __init__(self, star_cls) -> None:
        self.star_cls = star_cls


class _FakeContext:
    def __init__(self, star_cls) -> None:
        self._star = star_cls

    def get_registered_star(self, name: str):
        if name == "astrbot_plugin_proactive_chat":
            return _FakeMeta(self._star)
        return None


class _BridgeHostPlugin:
    """ProactiveBridge 自己持有的宿主桩：_resolve_origin/_in_quiet_hours 需要的最小面。"""

    def __init__(self, context=None) -> None:
        self.context = context
        self._store = None


def _always_quiet_bridge() -> ProactiveBridge:
    """构造一个必然覆盖当前小时的免打扰区间（0-23，跨天时用 23-0）。"""
    hour = _dt.datetime.now().hour
    quiet = "23-0" if hour == 23 else "0-23"
    host = _BridgeHostPlugin(context=_FakeContext(_FakeProactivePlugin(quiet)))
    return ProactiveBridge(host)


def _never_quiet_bridge() -> ProactiveBridge:
    """构造一个必然不覆盖当前小时的窄区间（下一个小时的单点）。"""
    hour = _dt.datetime.now().hour
    nxt = (hour + 2) % 24
    host = _BridgeHostPlugin(
        context=_FakeContext(_FakeProactivePlugin(f"{nxt}-{(nxt + 1) % 24}"))
    )
    return ProactiveBridge(host)


# ---------------------------------------------------------------------------
# ① is_night_fast_reply_exempt：纯函数
# ---------------------------------------------------------------------------


class TestNightExemptKeywords:
    def test_loneliness_keywords_exempt(self) -> None:
        assert is_night_fast_reply_exempt("我睡不着啊") is True
        assert is_night_fast_reply_exempt("你在吗") is True
        assert is_night_fast_reply_exempt("好难受") is True
        assert is_night_fast_reply_exempt("突然好想你") is True

    def test_ordinary_message_not_exempt(self) -> None:
        assert is_night_fast_reply_exempt("今天做了个梦，挺奇怪的") is False

    def test_empty_text_not_exempt(self) -> None:
        assert is_night_fast_reply_exempt("") is False
        assert is_night_fast_reply_exempt(None) is False  # type: ignore[arg-type]

    def test_keyword_list_is_chinese_tuple(self) -> None:
        assert isinstance(NIGHT_EXEMPT_KEYWORDS, tuple)
        assert all(isinstance(kw, str) and kw for kw in NIGHT_EXEMPT_KEYWORDS)


# ---------------------------------------------------------------------------
# ② _apply_night_rhythm：纯函数力学缩放
# ---------------------------------------------------------------------------


class TestApplyNightRhythmBounds:
    def test_inactive_passthrough_unchanged(self) -> None:
        cps, delay = LLMResponsePipeline._apply_night_rhythm(7.5, 2.0, active=False)
        assert cps == 7.5
        assert delay == 2.0

    def test_active_lowers_cps_within_body_range(self) -> None:
        cps, _delay = LLMResponsePipeline._apply_night_rhythm(
            7.5, 2.0, active=True, rng=random.Random(1)
        )
        assert cps == max(_CPS_MIN, 7.5 + _NIGHT_CPS_DELTA)
        assert _CPS_MIN <= cps <= _CPS_MAX

    def test_active_cps_never_below_floor(self) -> None:
        cps, _delay = LLMResponsePipeline._apply_night_rhythm(
            _CPS_MIN, 1.0, active=True, rng=random.Random(2)
        )
        assert cps >= _CPS_MIN

    def test_active_scales_delay_within_mult_range(self) -> None:
        for seed in range(30):
            rng = random.Random(seed)
            base_delay = 2.0
            _cps, delay = LLMResponsePipeline._apply_night_rhythm(
                7.5, base_delay, active=True, rng=rng
            )
            assert (
                base_delay * _NIGHT_THINK_DELAY_MULT_MIN
                <= delay
                <= min(_NIGHT_THINK_DELAY_CAP, base_delay * _NIGHT_THINK_DELAY_MULT_MAX) + 1e-9
            )

    def test_active_never_exceeds_hard_cap(self) -> None:
        """card 铁律：绝不滑向分钟级不理人——无论 base_delay 多大，硬顶 10s。"""
        for seed in range(20):
            rng = random.Random(seed)
            _cps, delay = LLMResponsePipeline._apply_night_rhythm(
                7.5, _NIGHT_THINK_DELAY_CAP, active=True, rng=rng
            )
            assert delay <= _NIGHT_THINK_DELAY_CAP

    def test_seeded_reproducible(self) -> None:
        r1 = LLMResponsePipeline._apply_night_rhythm(7.5, 2.0, active=True, rng=random.Random(9))
        r2 = LLMResponsePipeline._apply_night_rhythm(7.5, 2.0, active=True, rng=random.Random(9))
        assert r1 == r2

    def test_no_rng_falls_back_to_global_random(self) -> None:
        cps, delay = LLMResponsePipeline._apply_night_rhythm(7.5, 2.0, active=True)
        assert _CPS_MIN <= cps <= _CPS_MAX
        assert delay <= _NIGHT_THINK_DELAY_CAP


# ---------------------------------------------------------------------------
# ③ _night_rhythm_active：总开关 + 免打扰时段 + 豁免关键词接线
# ---------------------------------------------------------------------------


class _RespPlugin:
    def __init__(self, config: dict, bridge) -> None:
        self._config = config
        self._proactive_bridge = bridge


class TestNightRhythmActiveWiring:
    def test_config_off_always_false(self) -> None:
        pipe = LLMResponsePipeline(
            plugin=_RespPlugin(
                {"sylanne_alpha_night_rhythm_enabled": False}, _always_quiet_bridge()
            )
        )
        assert pipe._night_rhythm_active("s", "今天做了个梦") is False

    def test_config_missing_key_defaults_off(self) -> None:
        pipe = LLMResponsePipeline(plugin=_RespPlugin({}, _always_quiet_bridge()))
        assert pipe._night_rhythm_active("s", "今天做了个梦") is False

    def test_exempt_keyword_false_even_when_quiet(self) -> None:
        """红队铁律：孤独/紧急消息即便在免打扰时段也必须豁免。"""
        pipe = LLMResponsePipeline(
            plugin=_RespPlugin(
                {"sylanne_alpha_night_rhythm_enabled": True}, _always_quiet_bridge()
            )
        )
        assert pipe._night_rhythm_active("s", "我睡不着，在吗") is False

    def test_quiet_and_not_exempt_true(self) -> None:
        pipe = LLMResponsePipeline(
            plugin=_RespPlugin(
                {"sylanne_alpha_night_rhythm_enabled": True}, _always_quiet_bridge()
            )
        )
        assert pipe._night_rhythm_active("s", "今天做了个梦，挺奇怪的") is True

    def test_not_quiet_hours_false(self) -> None:
        pipe = LLMResponsePipeline(
            plugin=_RespPlugin(
                {"sylanne_alpha_night_rhythm_enabled": True}, _never_quiet_bridge()
            )
        )
        assert pipe._night_rhythm_active("s", "今天做了个梦，挺奇怪的") is False

    def test_missing_bridge_false(self) -> None:
        pipe = LLMResponsePipeline(
            plugin=_RespPlugin({"sylanne_alpha_night_rhythm_enabled": True}, None)
        )
        assert pipe._night_rhythm_active("s", "今天做了个梦") is False


# ---------------------------------------------------------------------------
# ④ v2core.integration：心象线索注入
# ---------------------------------------------------------------------------


def _ctx(text: str = "今天做了个梦，挺奇怪的") -> BeatContext:
    return BeatContext(
        session_key="u",
        event=None,
        body=BodySnapshot(session_key="u", turns=1),
        text=text,
        phase=Phase.PERCEPT,
        domains={},
    )


class _IntegrationPlugin:
    def __init__(self, bridge) -> None:
        self._proactive_bridge = bridge


class TestFeatureFlagWiring:
    def test_enabled_flag_from_config(self) -> None:
        ctx = _ctx()
        plugin = SimpleNamespace(_config={"sylanne_alpha_night_rhythm_enabled": True})
        ig._apply_v2core_feature_flags(ctx, plugin)
        assert ctx.scratch["night_rhythm_enabled"] is True

    def test_default_off(self) -> None:
        ctx = _ctx()
        plugin = SimpleNamespace(_config={})
        ig._apply_v2core_feature_flags(ctx, plugin)
        assert ctx.scratch["night_rhythm_enabled"] is False


class TestApplyNightTextureScratch:
    def test_exempt_text_produces_no_cue(self) -> None:
        ctx = _ctx("我睡不着")
        rt: dict = {}
        plugin = _IntegrationPlugin(_always_quiet_bridge())
        ig._apply_night_texture_scratch(plugin, "s", ctx, rt, "我睡不着", 1_000_000.0)
        assert "night_texture_cue" not in ctx.scratch
        assert "night_wake_cue" not in ctx.scratch
        # 豁免时仍更新时间戳，供后续非豁免消息计算 gap
        assert rt["night_last_request_time"] == 1_000_000.0

    def test_quiet_hours_sets_texture_cue(self) -> None:
        ctx = _ctx()
        rt: dict = {}
        plugin = _IntegrationPlugin(_always_quiet_bridge())
        ig._apply_night_texture_scratch(
            plugin, "s", ctx, rt, "今天做了个梦，挺奇怪的", 1_000_000.0
        )
        assert ctx.scratch.get("night_texture_cue") is True

    def test_not_quiet_hours_no_cue(self) -> None:
        ctx = _ctx()
        rt: dict = {}
        plugin = _IntegrationPlugin(_never_quiet_bridge())
        ig._apply_night_texture_scratch(
            plugin, "s", ctx, rt, "今天做了个梦，挺奇怪的", 1_000_000.0
        )
        assert "night_texture_cue" not in ctx.scratch

    def test_missing_bridge_no_crash_no_cue(self) -> None:
        ctx = _ctx()
        rt: dict = {}
        plugin = _IntegrationPlugin(None)
        ig._apply_night_texture_scratch(
            plugin, "s", ctx, rt, "今天做了个梦，挺奇怪的", 1_000_000.0
        )
        assert "night_texture_cue" not in ctx.scratch

    def test_wake_cue_requires_gap_over_one_hour(self, monkeypatch) -> None:
        plugin = _IntegrationPlugin(_always_quiet_bridge())
        rt: dict = {}
        monkeypatch.setattr(ig.random, "random", lambda: 0.0)  # 概率强制命中

        # 首次调用：无 prev_time → gap=0，不触发 wake cue
        ctx1 = _ctx()
        ig._apply_night_texture_scratch(plugin, "s", ctx1, rt, ctx1.text, 1_000_000.0)
        assert "night_wake_cue" not in ctx1.scratch

        # 第二次：gap 仅 60s（<1h）→ 概率强制 100% 也不触发
        ctx2 = _ctx()
        ig._apply_night_texture_scratch(plugin, "s", ctx2, rt, ctx2.text, 1_000_060.0)
        assert "night_wake_cue" not in ctx2.scratch

        # 第三次：gap 超过 1h + 概率强制 100% → 触发
        ctx3 = _ctx()
        ig._apply_night_texture_scratch(
            plugin, "s", ctx3, rt, ctx3.text, 1_000_060.0 + 3700.0
        )
        assert ctx3.scratch.get("night_wake_cue") is True
        assert ctx3.scratch.get("night_texture_cue") is True

    def test_wake_cue_probability_can_miss(self, monkeypatch) -> None:
        plugin = _IntegrationPlugin(_always_quiet_bridge())
        rt: dict = {"night_last_request_time": 1_000_000.0}
        monkeypatch.setattr(ig.random, "random", lambda: 0.99)  # 概率强制不命中
        ctx = _ctx()
        ig._apply_night_texture_scratch(
            plugin, "s", ctx, rt, ctx.text, 1_000_000.0 + 4000.0
        )
        assert ctx.scratch.get("night_texture_cue") is True
        assert "night_wake_cue" not in ctx.scratch


# ---------------------------------------------------------------------------
# ⑤ v2core.fragment：渲染层
# ---------------------------------------------------------------------------


class TestNightLineRendering:
    def test_no_cue_silent(self) -> None:
        assert frag._night_line(_ctx()) == ("", 0.0)

    def test_texture_only(self) -> None:
        c = _ctx()
        c.scratch["night_texture_cue"] = True
        text, boost = frag._night_line(c)
        assert text == frag._NIGHT_TEXTURE_LINE
        assert boost == 0.0

    def test_texture_and_wake_combined(self) -> None:
        c = _ctx()
        c.scratch["night_texture_cue"] = True
        c.scratch["night_wake_cue"] = True
        text, boost = frag._night_line(c)
        assert frag._NIGHT_WAKE_LINE in text
        assert frag._NIGHT_TEXTURE_LINE in text
        assert boost == frag._SAL_NIGHT_WAKE_BOOST

    def test_wake_alone_without_texture_stays_silent(self) -> None:
        """integration 总是先设 texture_cue 才可能设 wake_cue；即便孤立出现
        wake_cue，渲染层也不该只凭它单独发声（防御性行为，非当前可达路径）。"""
        c = _ctx()
        c.scratch["night_wake_cue"] = True
        assert frag._night_line(c) == ("", 0.0)

    def test_reaches_fragment_end_to_end(self) -> None:
        c = _ctx()
        c.scratch["night_texture_cue"] = True
        out = frag.build_mind_fragment(c, {})
        assert frag._NIGHT_TEXTURE_LINE in out

    def test_no_scratch_no_line_in_fragment(self) -> None:
        c = _ctx()
        out = frag.build_mind_fragment(c, {})
        assert frag._NIGHT_TEXTURE_LINE not in out
        assert frag._NIGHT_WAKE_LINE not in out


# ---------------------------------------------------------------------------
# ⑥ 配置关闭 = 全链路零变化
# ---------------------------------------------------------------------------


class TestConfigOffZeroChange:
    def test_response_pipeline_inactive_when_config_absent(self) -> None:
        pipe = LLMResponsePipeline(plugin=_RespPlugin({}, _always_quiet_bridge()))
        assert pipe._night_rhythm_active("s", "深夜随便聊聊") is False
        cps, delay = LLMResponsePipeline._apply_night_rhythm(7.5, 2.0, active=False)
        assert (cps, delay) == (7.5, 2.0)

    def test_integration_scratch_flag_off_skips_cue_block_semantics(self) -> None:
        """_apply_v2core_feature_flags 关闭时，调用方（apply_v2core_request）不会
        走到 _apply_night_texture_scratch——这里直接验证 flag 语义本身正确，
        真实调用路径见 apply_v2core_request 里的 `if ctx.scratch.get(...)` 闸门。"""
        ctx = _ctx()
        plugin = SimpleNamespace(_config={"sylanne_alpha_night_rhythm_enabled": False})
        ig._apply_v2core_feature_flags(ctx, plugin)
        assert ctx.scratch["night_rhythm_enabled"] is False

    def test_day_path_think_delay_math_untouched(self) -> None:
        """白天路径：_apply_night_rhythm(active=False) 必须是纯粹的恒等映射，
        不触碰既有 T1-01/T1-02/T3-01 已经算好的 (cps, think_delay)。"""
        for cps, delay in ((4.5, 0.8), (7.5, 3.2), (11.0, 6.0)):
            out_cps, out_delay = LLMResponsePipeline._apply_night_rhythm(
                cps, delay, active=False
            )
            assert out_cps == cps
            assert out_delay == delay
