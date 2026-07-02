"""Wave-L2/T2-01（已读不回·软化版）+ T2-03（去忙收尾）：红队改造版测试。

T2-01 杀的问题：她 100% 回复所有消息；SILENT 此前自举死锁（addressed 分支要
g_hold > g_speak 才装死，而 g_hold 只在 SILENT 发生后才积累——从未发生过就永远
没食粮）。修法：
  ① ignition.context_hold_food：与未表达积分正交的语境食粮（低信息量/连发/边界
     压力/深夜），config 关时恒 0。
  ② DeliberateSilence 复活为第二沉默源：真触发的 SILENT 落地前先问它要不要软化成
     极简回应（"……"/"嗯。"）。
  ③ 事后认账：last_silent 记进 rt，下一轮心象心带一句"刚才没说话"的线索。

T2-03 杀的问题：她永不收线；无限可用是最强的"是服务器"破绽。修法：
  ④ behavior.py 新增 winddown（读 integration 注入的 life_sim_signals，config 关
     时恒 0）。
  ⑤ 点燃后开一个分钟级收尾窗口：期间 g_hold 加偏置 + 派发多等一会。
  ⑥ 窗口结束后台任务尝试主动"回来"；桥不可用时下一条消息带"刚忙完"心象线索。

两个 config（sylanne_alpha_deliberate_silence_enabled / sylanne_alpha_winddown_enabled）
默认关闭；关闭时两条链路都是纯 no-op（多处专项验证零变化）。
"""

from __future__ import annotations

import asyncio
import tempfile

from sylanne_alpha.realtime_dispatch import DeliberateSilence
from sylanne_alpha.v2core import fragment as frag_mod
from sylanne_alpha.v2core import integration as ig
from sylanne_alpha.v2core.behavior import _act_winddown, select_behavior
from sylanne_alpha.v2core.capabilities.ignition import (
    IgnitionArbiter,
    _is_deep_night,
    _is_low_info_text,
    context_hold_food,
)
from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Intent, Phase
from sylanne_alpha.v2core.domains.emotion import EmotionLedger


def _body(**kw) -> BodySnapshot:
    p = kw.pop("personality", {})
    return BodySnapshot(session_key="u", turns=3, personality=p, **kw)


def _ctx(body: BodySnapshot, *, text: str = "", domains=None, scratch=None) -> BeatContext:
    c = BeatContext(session_key="u", event=None, body=body, text=text,
                    phase=Phase.DELIBERATE, domains=domains or {})
    for k, v in (scratch or {}).items():
        c.scratch[k] = v
    return c


class _FakeUserModel:
    """T2-01① 测试桩：只暴露 ignition 需要的两个读接口。"""

    def __init__(self, last_text: str = "", gap: float | None = None) -> None:
        self._last_text = last_text
        self._gap = gap

    def last_user_text(self) -> str:
        return self._last_text

    def seconds_since_last_user(self, now: float) -> float | None:
        return self._gap


# ===========================================================================
# T2-01① context_hold_food：纯函数单元
# ===========================================================================


class TestLowInfoDetection:
    def test_short_ack_word_is_low_info(self) -> None:
        assert _is_low_info_text("哦", "") is True
        assert _is_low_info_text("嗯", "上一条") is True

    def test_ordinary_sentence_is_not_low_info(self) -> None:
        assert _is_low_info_text("今天天气很好想出去走走", "") is False

    def test_repeat_of_last_text_is_low_info(self) -> None:
        assert _is_low_info_text("在干嘛呢", "在干嘛呢") is True

    def test_bare_emoji_or_punct_is_low_info(self) -> None:
        assert _is_low_info_text("😂😂😂", "") is True
        assert _is_low_info_text("！！！", "") is True

    def test_empty_text_is_not_low_info(self) -> None:
        """空文本是空闲轮，不归这条判据管（别把它算成"低信息量已读"）。"""
        assert _is_low_info_text("", "") is False

    def test_666_is_low_info(self) -> None:
        """MINOR 修复回归：'666' 长度 3 超过 _LOW_INFO_MAXLEN=2，旧版先卡长度门再查
        词表，词表命中判据永远够不到；又因为全是数字能被 _HAS_WORD_RE 命中，连"纯
        符号"兜底也接不住——'666' 曾经无论如何都判不成低信息量。现在词表命中先判，
        不再看长度。"""
        assert _is_low_info_text("666", "") is True

    def test_other_long_ack_words_are_also_low_info(self) -> None:
        """同一个 bug 也曾漏判词表里其它超过 MAXLEN 的成员（"好的"/"是的"/"嗯呢"/
        "..."），一并钉住不回归。"""
        for word in ("好的", "是的", "嗯呢", "..."):
            assert _is_low_info_text(word, "") is True, word


class TestDeepNight:
    def test_now_le_zero_is_never_night(self) -> None:
        assert _is_deep_night(0.0) is False
        assert _is_deep_night(-1.0) is False

    def test_02_00_china_is_night(self) -> None:
        # 2026-01-01 02:00 CST epoch（UTC 前一日 18:00）
        import datetime
        dt = datetime.datetime(2026, 1, 1, 2, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=8)))
        assert _is_deep_night(dt.timestamp()) is True

    def test_14_00_china_is_not_night(self) -> None:
        import datetime
        dt = datetime.datetime(2026, 1, 1, 14, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=8)))
        assert _is_deep_night(dt.timestamp()) is False


class TestContextHoldFood:
    def test_disabled_flag_is_always_zero(self) -> None:
        """config 关（scratch 里没有 True）→ 恒 0，与该功能不存在时零差异。"""
        body = _body(boundary_pressure=0.95)
        ctx = _ctx(body, text="哦", domains={"usermodel": _FakeUserModel(gap=0.0)})
        assert context_hold_food(ctx) == 0.0

    def test_enabled_but_ordinary_message_contributes_little(self) -> None:
        """开着但只是句普通话、无连发/无边界压力/白天 → 食粮应为 0（无信号即无食粮）。"""
        body = _body(boundary_pressure=0.0)
        ctx = _ctx(body, text="今天点了麻辣烫，还挺好吃的",
                   domains={"usermodel": _FakeUserModel(gap=999.0)},
                   scratch={"deliberate_silence_enabled": True, "now": 0.0})
        assert context_hold_food(ctx) == 0.0

    def test_all_signals_stack_but_stay_small(self) -> None:
        """四个信号全部拉满也只是"小"——不封顶叠加，但量级刻意压低（卡片要求）。"""
        import datetime
        night_ts = datetime.datetime(
            2026, 1, 1, 2, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=8))
        ).timestamp()
        body = _body(boundary_pressure=0.95)
        ctx = _ctx(
            body, text="哦",
            domains={"usermodel": _FakeUserModel(last_text="哦", gap=0.0)},
            scratch={"deliberate_silence_enabled": True, "now": night_ts},
        )
        food = context_hold_food(ctx)
        assert 0.0 < food < 0.5, f"食粮应叠加但保持小量级，实得 {food}"

    def test_missing_usermodel_domain_degrades_gracefully(self) -> None:
        body = _body(boundary_pressure=0.0)
        ctx = _ctx(body, text="哦", domains={},
                   scratch={"deliberate_silence_enabled": True, "now": 0.0})
        # 低信息量判据不依赖 usermodel，仍应生效；不因缺域而抛异常
        assert context_hold_food(ctx) >= 0.0


# ===========================================================================
# T2-01① 死锁真的被打破：addressed 分支此前 g_hold 恒 0 永远够不到 g_speak，
# 现在语境食粮 + 适中表达驱力可以真的翻成 hold；config 关时行为分毫不变。
# ===========================================================================


class TestHoldBootstrapUnblocked:
    def _scenario(self, *, deliberate_silence_enabled: bool) -> BeatContext:
        import datetime
        night_ts = datetime.datetime(
            2026, 1, 1, 2, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=8))
        ).timestamp()
        body = _body(
            expression_drive=0.65,   # 适中驱力：g_speak = 0.95-0.65 = 0.30（不是强制 speak）
            boundary_pressure=0.95,
            personality={"curiosity": 0.5, "warmth_bias": 0.5,
                        "sovereignty_guard": 0.5, "patience": 0.5},
        )
        scratch = {"now": night_ts}
        if deliberate_silence_enabled:
            scratch["deliberate_silence_enabled"] = True
        ctx = _ctx(
            body, text="哦",
            domains={"emotion": EmotionLedger(),  # 全新账本：_unexpressed=0（死锁场景）
                    "usermodel": _FakeUserModel(last_text="哦", gap=0.0)},
            scratch=scratch,
        )
        return ctx

    def test_config_on_hold_becomes_reachable(self) -> None:
        """emo.hold_free_energy 恒 0（从未沉默过）；靠语境食粮单独把 g_hold 顶过 g_speak。"""
        ctx = self._scenario(deliberate_silence_enabled=True)
        out = IgnitionArbiter().deliberate(ctx)
        assert out.payload["action"] == "hold", out.payload
        assert "silent" in ctx.scratch

    def test_config_off_same_scenario_still_speaks(self) -> None:
        """一模一样的场景，只关掉总开关——语境食粮归零，回到"100% 回复"的旧行为。"""
        ctx = self._scenario(deliberate_silence_enabled=False)
        out = IgnitionArbiter().deliberate(ctx)
        assert out.payload["action"] == "speak", out.payload
        assert "silent" not in ctx.scratch


# ===========================================================================
# MAJOR 修复回归：idle 分支（未被问）是 min-cost 选择器——g_hold 在那里的语义是
# "hold 这一行动的代价"，而不是 addressed 分支里"沉默的吸引力"。T2-01①语境食粮 /
# T2-03⑤ winddown_hold_bias 若像 addressed 分支一样直接叠进 g_hold，会把 hold 的
# 代价推高、argmin 反而更容易滑向 reach——方向和卡片设计意图（"压一压 reach 倾向"）
# 刚好相反。这里直接钉住 IgnitionArbiter.deliberate 本身的防线：两路食粮只在
# addressed 分支生效；idle 分支即便 scratch 意外带着这些键也必须免疫。
# ===========================================================================


class TestIdleMinCostBiasGating:
    def _idle_ctx(self, *, winddown_bias: float = 0.0) -> BeatContext:
        """构造一个真正的边际带（不是冷启动全零）：g_hold=0.20 < g_reach=0.25 <
        g_speak=0.35——三个代价彼此接近，argmin 的选择对偏置真的敏感。"""
        body = _body(
            expression_drive=0.60,
            personality={"curiosity": 0.5, "warmth_bias": 0.5,
                        "sovereignty_guard": 0.5, "patience": 0.5},
        )
        emo = EmotionLedger()
        emo.load_dict({"unexpressed": 0.20})   # warmth/tension/repair_pressure=0 → 强度=0 → g_hold=0.20 整
        scratch: dict[str, object] = {"now": 0.0}
        if winddown_bias:
            scratch["winddown_hold_bias"] = winddown_bias
        ctx = _ctx(body, text="", domains={"emotion": emo}, scratch=scratch)
        # 手填 outreach 意图（跳过 OutreachCapability，直接控制 g_reach_raw=0.75 → g_reach=0.25）
        ctx.intents.append(Intent(source="outreach", payload={"g_reach": 0.75}, priority=0.5))
        return ctx

    def test_baseline_marginal_band_picks_hold(self) -> None:
        """无偏置基线：hold(0.20) < reach(0.25) < speak(0.35) → hold 胜出。"""
        ctx = self._idle_ctx()
        out = IgnitionArbiter().deliberate(ctx)
        assert out.payload["action"] == "hold", out.payload
        assert out.payload["g_hold"] == 0.20

    def test_winddown_bias_leaked_into_idle_ctx_does_not_flip_to_reach(self) -> None:
        """修复钉子——这正是红队描述的翻转场景：若 idle 分支像 addressed 分支一样
        把 winddown_hold_bias=0.30 直接叠进 g_hold，代价会变成 0.20+0.30=0.50，
        costs={hold:0.50, speak:0.35, reach:0.25} 的 argmin 从 hold 翻成 reach——
        她在"该安静"的窗口里反而更爱主动戳你。修复后 idle 分支对这个偏置免疫，
        g_hold 应与无偏置基线完全一致，action 也不该翻。"""
        ctx = self._idle_ctx(winddown_bias=0.30)
        out = IgnitionArbiter().deliberate(ctx)
        assert out.payload["g_hold"] == 0.20, (
            "idle 分支被偏置污染了——重演了红队描述的 hold→reach 翻转",
            out.payload,
        )
        assert out.payload["action"] == "hold", out.payload

    def test_addressed_branch_still_gets_the_bias_direction_unchanged(self) -> None:
        """方向对照：同一份偏置在 addressed 分支必须照常叠加——那边的方向本来就是
        对的（g_hold 越大越容易 hold/装死），不该被这次的 idle 门控误伤。"""
        body = _body(
            expression_drive=0.0,
            personality={"curiosity": 0.5, "warmth_bias": 0.5,
                        "sovereignty_guard": 0.5, "patience": 0.5},
        )
        emo = EmotionLedger()
        emo.load_dict({"unexpressed": 0.20})
        ctx = _ctx(body, text="在吗", domains={"emotion": emo},
                  scratch={"now": 0.0, "winddown_hold_bias": 0.30})
        out = IgnitionArbiter().deliberate(ctx)
        assert out.payload["g_hold"] == 0.20 + 0.30, out.payload


# ===========================================================================
# T2-01②：DeliberateSilence 软化（_maybe_soften_silence 纯单元）
# ===========================================================================


class _FakeRealtimeDispatch:
    def __init__(self, ds) -> None:
        self._ds = ds

    def deliberate_silence(self):
        return self._ds


class _FakePluginForSoften:
    def __init__(self, ds=None) -> None:
        self._realtime_dispatch = _FakeRealtimeDispatch(ds) if ds is not None else None


class TestMaybeSoftenSilence:
    def test_empty_text_never_softens(self) -> None:
        """空闲/主动轮（无文本）不归本条管——只软化"被问却装死"。"""
        body = _body(warmth=-0.5, tension=0.9)
        ctx = _ctx(body, text="")
        plugin = _FakePluginForSoften(ds=DeliberateSilence())
        reply, reason = ig._maybe_soften_silence(plugin, ctx)
        assert reply is None and reason == ""

    def test_no_realtime_dispatch_degrades_to_none(self) -> None:
        body = _body(warmth=-0.5, tension=0.9)
        ctx = _ctx(body, text="在吗")
        plugin = _FakePluginForSoften(ds=None)
        reply, reason = ig._maybe_soften_silence(plugin, ctx)
        assert reply is None and reason == ""

    def test_hurt_reason_softens_to_minimal_speak(self) -> None:
        """tension>0.7 且 valence<-0.3 → "hurt"，极简回应"……"。"""
        body = _body(warmth=-0.5, tension=0.9)
        ctx = _ctx(body, text="在吗")
        plugin = _FakePluginForSoften(ds=DeliberateSilence())
        reply, reason = ig._maybe_soften_silence(plugin, ctx)
        assert reason == "hurt"
        assert reply is not None
        from sylanne_alpha.v2core.contracts import ReplyKind
        assert reply.kind is ReplyKind.SPEAK
        assert reply.parts == ("……",)
        assert reply.meta.get("mode") == "minimal_silence"

    def test_content_reason_softens_to_minimal_speak(self) -> None:
        """MINOR 修复回归：tension<0.15 且 warmth>0.5（v2core 真实值域内）→ "content"，
        极简回应"嗯。"。红队 finding：旧阈值 tension<-0.5 在 [0,1] 值域下永不可达，
        本用例钉住重标定后用【契约域内的正常值】就能命中，不再需要越界手造 tension。"""
        body = _body(warmth=0.8, tension=0.05)
        ctx = _ctx(body, text="在吗")
        plugin = _FakePluginForSoften(ds=DeliberateSilence())
        reply, reason = ig._maybe_soften_silence(plugin, ctx)
        assert reason == "content"
        assert reply is not None
        from sylanne_alpha.v2core.contracts import ReplyKind
        assert reply.kind is ReplyKind.SPEAK
        assert reply.parts == ("嗯。",)
        assert reply.meta.get("mode") == "minimal_silence"

    def test_digesting_reason_keeps_full_silence(self) -> None:
        """void_pressure>3 且 valence>0 → "digesting"，get_minimal_response 返回 None：
        不软化，但理由仍回传供留痕/心象。"""
        body = _body(warmth=0.4, void_pressure=5.0)
        ctx = _ctx(body, text="在吗")
        plugin = _FakePluginForSoften(ds=DeliberateSilence())
        reply, reason = ig._maybe_soften_silence(plugin, ctx)
        assert reply is None
        assert reason == "digesting"

    def test_neutral_body_no_ds_trigger(self) -> None:
        body = _body(warmth=0.0, tension=0.0, void_pressure=0.0)
        ctx = _ctx(body, text="在吗")
        plugin = _FakePluginForSoften(ds=DeliberateSilence())
        reply, reason = ig._maybe_soften_silence(plugin, ctx)
        assert reply is None and reason == ""


# ===========================================================================
# T2-01②③ + T2-03⑤：实弹路径端到端（真 host，复用 test_v2core_bridge.py 套路）
# ===========================================================================


class _Resp:
    def __init__(self, t: str) -> None:
        self.completion_text = t


class _Pipe:
    def __init__(self, text: str = "在吗") -> None:
        self._t = text

    def _text(self, _e: object) -> str:
        return self._t


class _ForceHold:
    """假能力：DELIBERATE 强制写 scratch['silent']（模拟 ignition hold 判定命中）。"""

    name = "force_hold"
    phases = (Phase.DELIBERATE,)

    def deliberate(self, ctx: BeatContext):
        from sylanne_alpha.v2core.contracts import Intent
        ctx.scratch["silent"] = {"reason": "ignition_hold"}
        return Intent(source=self.name, priority=0.0)


class _FakeDS:
    """确定性假 DeliberateSilence：忽略 body 输入，恒定给出可控结果。"""

    def __init__(self, should: bool, reason: str, minimal: str | None) -> None:
        self._should, self._reason, self._minimal = should, reason, minimal

    def should_be_silent(self, valence, tension, void_pressure):  # noqa: ANN001
        return self._should, self._reason

    def get_minimal_response(self, reason):  # noqa: ANN001
        return self._minimal


def _make_host_plugin(*, config: dict, text: str = "在吗"):
    from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost

    class _Plugin:
        def __init__(self) -> None:
            self._config = dict(config)
            self._root = tempfile.mkdtemp(prefix="sylwl2t201_")
            self._hosts: dict[str, SylanneAlphaHost] = {}
            self._llm_response_pipeline = _Pipe(text)

        def _session_key(self, _e: object) -> str:
            return "u1"

        def _host(self, sk: str) -> SylanneAlphaHost:
            if sk not in self._hosts:
                self._hosts[sk] = SylanneAlphaHost(root=self._root, session_key=sk)
            return self._hosts[sk]

    return _Plugin()


class _Event:
    unified_msg_origin = "test:u1"

    def get_sender_id(self):
        return "u1"


class TestSoftenAndAcknowledgeEndToEnd:
    def test_softened_silence_speaks_minimal_and_records_last_silent(self) -> None:
        plugin = _make_host_plugin(config={
            "sylanne_enable_v2core": True,
            "sylanne_alpha_deliberate_silence_enabled": True,
        })
        plugin._realtime_dispatch = _FakeRealtimeDispatch(_FakeDS(True, "hurt", "……"))

        rt = ig._runtime_for(plugin, "u1")
        rt["runner"]._sc.register(_ForceHold())

        resp = _Resp("宿主草稿：我在的")
        handled = asyncio.run(ig.apply_v2core_response(plugin, _Event(), resp))

        assert handled is False, "软化后是 SPEAK，应故意回落 legacy 发送"
        assert resp.completion_text == "……"
        assert rt["last_silent"] is not None
        assert rt["last_silent"]["reason"] == "hurt"

    def test_digesting_stays_full_silent_but_still_records(self) -> None:
        plugin = _make_host_plugin(config={
            "sylanne_enable_v2core": True,
            "sylanne_alpha_deliberate_silence_enabled": True,
        })
        plugin._realtime_dispatch = _FakeRealtimeDispatch(_FakeDS(True, "digesting", None))

        rt = ig._runtime_for(plugin, "u1")
        rt["runner"]._sc.register(_ForceHold())

        resp = _Resp("宿主草稿")
        handled = asyncio.run(ig.apply_v2core_response(plugin, _Event(), resp))

        assert handled is True, "未软化仍是真 SILENT，本层终结本轮"
        assert resp.completion_text == ""
        assert rt["last_silent"]["reason"] == "digesting"

    def test_last_silent_cue_surfaces_next_turn_fragment(self) -> None:
        """③：上一轮软化沉默后，下一轮 apply_v2core_request 的 ctx 心象带认账线索。"""
        plugin = _make_host_plugin(config={
            "sylanne_enable_v2core": True,
            "sylanne_alpha_deliberate_silence_enabled": True,
        })
        plugin._realtime_dispatch = _FakeRealtimeDispatch(_FakeDS(True, "content", "嗯。"))
        rt = ig._runtime_for(plugin, "u1")
        rt["runner"]._sc.register(_ForceHold())

        resp = _Resp("草稿")
        asyncio.run(ig.apply_v2core_response(plugin, _Event(), resp))
        assert rt["last_silent"]["reason"] == "content"

        class _Req:
            system_prompt = ""

        req = _Req()
        asyncio.run(ig.apply_v2core_request(plugin, _Event(), req))
        pending_ctx = rt["pending"]["ctx"]
        assert pending_ctx.scratch.get("last_silent_cue") == "content"
        # 一次性：用过就清
        assert rt["last_silent"] is None
        # 真的渲染进心象片段（fragment 端到端）
        assert "刚才看到消息了" in (req.system_prompt or "")

    def test_config_off_soften_is_pure_noop(self) -> None:
        """两开关都关：即便强制 hold，也应是原样 SILENT，rt 里不出现 last_silent。"""
        plugin = _make_host_plugin(config={"sylanne_enable_v2core": True})
        plugin._realtime_dispatch = _FakeRealtimeDispatch(_FakeDS(True, "hurt", "……"))
        rt = ig._runtime_for(plugin, "u1")
        rt["runner"]._sc.register(_ForceHold())

        resp = _Resp("草稿")
        handled = asyncio.run(ig.apply_v2core_response(plugin, _Event(), resp))
        assert handled is True
        assert resp.completion_text == ""
        assert rt.get("last_silent") is None


# ===========================================================================
# fragment 渲染：last_silent_cue / winddown_return_cue 纯单元
# ===========================================================================


class TestFragmentCueLines:
    def test_last_silent_line_known_reason(self) -> None:
        ctx = _ctx(_body(), scratch={"last_silent_cue": "hurt"})
        line = frag_mod._last_silent_line(ctx)
        assert "刚才看到消息了" in line and "心里有点不舒服" in line

    def test_last_silent_line_unknown_reason_falls_back(self) -> None:
        ctx = _ctx(_body(), scratch={"last_silent_cue": "some_unmapped_reason"})
        line = frag_mod._last_silent_line(ctx)
        assert "没想好要说什么" in line

    def test_last_silent_line_absent_is_empty(self) -> None:
        ctx = _ctx(_body())
        assert frag_mod._last_silent_line(ctx) == ""

    def test_winddown_return_line(self) -> None:
        ctx = _ctx(_body(), scratch={"winddown_return_cue": True})
        assert "刚把手头那件事收了尾" in frag_mod._winddown_return_line(ctx)
        ctx2 = _ctx(_body())
        assert frag_mod._winddown_return_line(ctx2) == ""


# ===========================================================================
# T2-03④：winddown 行为激活（behavior.py）
# ===========================================================================


class TestWinddownActivation:
    def test_no_life_sim_signals_is_zero(self) -> None:
        assert _act_winddown(_body(), {}, {}) == 0.0

    def test_busy_and_focused_activates(self) -> None:
        sig = {"phase": "afternoon", "energy": 0.6, "focus": 0.95, "interruptibility": 0.1}
        act = _act_winddown(_body(), {}, {"life_sim_signals": sig})
        assert act >= 0.5

    def test_idle_and_unfocused_does_not_activate(self) -> None:
        sig = {"phase": "afternoon", "energy": 0.8, "focus": 0.2, "interruptibility": 0.9}
        act = _act_winddown(_body(), {}, {"life_sim_signals": sig})
        assert act < 0.5

    def test_exhausted_alone_can_activate(self) -> None:
        sig = {"phase": "night", "energy": 0.05, "focus": 0.5, "interruptibility": 0.7}
        act = _act_winddown(_body(), {}, {"life_sim_signals": sig})
        assert act >= 0.5

    def test_select_behavior_picks_winddown(self) -> None:
        sig = {"phase": "afternoon", "energy": 0.6, "focus": 0.95, "interruptibility": 0.05}
        sel = select_behavior(_body(), {"life_sim_signals": sig}, {}, 1000.0)
        assert sel is not None and sel["id"] == "winddown"
        assert "先去忙" in sel["directive"] or "收个尾" in sel["directive"]
        assert sel["modulators"].get("extra_predelay_s") == 2.5

    def test_config_off_no_signals_no_winddown(self) -> None:
        """未注入 life_sim_signals（config 关/life_sim 不可用）→ winddown 恒不参选。"""
        sel = select_behavior(_body(), {}, {}, 1000.0)
        assert sel is None or sel["id"] != "winddown"


# ===========================================================================
# T2-03⑤：收尾窗口开窗（_start_winddown_window，mocked clock）
# ===========================================================================


class _FakeSimDuration:
    def __init__(self, minutes: int | None) -> None:
        self._m = minutes

    def current_activity_duration_min(self):
        return self._m


class _CapturingScheduler:
    """假 _realtime_dispatch：记录被调度的协程但不真的跑（避免真睡 15~45 分钟）。"""

    def __init__(self) -> None:
        self.scheduled: list[tuple[object, str]] = []

    def schedule_background_task(self, coro, *, label: str = ""):
        self.scheduled.append((coro, label))
        coro.close()   # 不运行，避免 "coroutine was never awaited" 且不真的 sleep
        return None


class TestStartWinddownWindow:
    def test_duration_from_life_sim_clamped(self) -> None:
        plugin = type("P", (), {"_realtime_dispatch": _CapturingScheduler(),
                                "_proactive_bridge": None})()
        rt: dict = {}
        ig._start_winddown_window(plugin, "s1", rt, _FakeSimDuration(9999), now=1000.0)
        # 9999 分钟远超 45 分钟上限，应被夹到 _WINDDOWN_MAX_S
        assert rt["winddown_until"] == 1000.0 + ig._WINDDOWN_MAX_S
        assert rt["winddown_return_notified"] is False
        assert len(plugin._realtime_dispatch.scheduled) == 1

    def test_duration_below_floor_clamped(self) -> None:
        plugin = type("P", (), {"_realtime_dispatch": _CapturingScheduler()})()
        rt: dict = {}
        ig._start_winddown_window(plugin, "s1", rt, _FakeSimDuration(1), now=1000.0)
        assert rt["winddown_until"] == 1000.0 + ig._WINDDOWN_MIN_S

    def test_no_duration_available_uses_default(self) -> None:
        plugin = type("P", (), {"_realtime_dispatch": _CapturingScheduler()})()
        rt: dict = {}
        ig._start_winddown_window(plugin, "s1", rt, _FakeSimDuration(None), now=1000.0)
        assert rt["winddown_until"] == 1000.0 + ig._WINDDOWN_DEFAULT_S

    def test_no_sim_uses_default(self) -> None:
        plugin = type("P", (), {"_realtime_dispatch": _CapturingScheduler()})()
        rt: dict = {}
        ig._start_winddown_window(plugin, "s1", rt, None, now=1000.0)
        assert rt["winddown_until"] == 1000.0 + ig._WINDDOWN_DEFAULT_S

    def test_no_scheduler_available_does_not_crash(self) -> None:
        plugin = type("P", (), {})()   # 没有 _realtime_dispatch
        rt: dict = {}
        ig._start_winddown_window(plugin, "s1", rt, None, now=1000.0)
        assert rt["winddown_until"] == 1000.0 + ig._WINDDOWN_DEFAULT_S

    def test_scheduler_raises_closes_coro_no_leak(self) -> None:
        """MINOR 修复回归（红队 finding）：scheduler() 抛异常时，此前先构造好的
        _winddown_return_after(...) 协程对象从未被 await/close，GC 时会炸出
        "coroutine was never awaited" RuntimeWarning。现在 except 分支要 close 它——
        用 inspect 断言协程确已进入 CORO_CLOSED，而不是仅仅"没崩"。"""
        import inspect

        captured: dict[str, object] = {}

        class _RaisingScheduler:
            def schedule_background_task(self, coro, *, label: str = ""):
                captured["coro"] = coro
                raise RuntimeError("no running event loop")

        plugin = type("P", (), {"_realtime_dispatch": _RaisingScheduler()})()
        rt: dict = {}
        ig._start_winddown_window(plugin, "s1", rt, _FakeSimDuration(None), now=1000.0)
        # 窗口本身仍生效（调度失败不阻断）
        assert rt["winddown_until"] == 1000.0 + ig._WINDDOWN_DEFAULT_S
        assert "coro" in captured
        assert inspect.getcoroutinestate(captured["coro"]) == "CORO_CLOSED"


# ===========================================================================
# T2-03⑥：返场触达（_winddown_return_after）——桥不可用时静默退出，不抛
# ===========================================================================


class TestWinddownReturnAfter:
    def test_no_bridge_available_returns_quietly(self) -> None:
        plugin = type("P", (), {"_proactive_bridge": None})()
        asyncio.run(ig._winddown_return_after(plugin, "s1", 0.0))   # 不应抛异常

    def test_bridge_unavailable_flag_returns_quietly(self) -> None:
        class _Bridge:
            def available(self) -> bool:
                return False

        plugin = type("P", (), {"_proactive_bridge": _Bridge()})()
        asyncio.run(ig._winddown_return_after(plugin, "s1", 0.0))

    def test_bridge_available_but_throttled_skips_dispatch(self) -> None:
        calls: list[str] = []

        class _Bridge:
            def available(self) -> bool:
                return True

            def should_dispatch_now(self, session_key: str):
                return False, "min_interval_throttle"

            def build_motivation_text(self, *a, **kw):  # noqa: ANN002,ANN003
                calls.append("build")
                return "x"

            async def dispatch(self, *a, **kw):  # noqa: ANN002,ANN003
                calls.append("dispatch")

        plugin = type("P", (), {"_proactive_bridge": _Bridge()})()
        asyncio.run(ig._winddown_return_after(plugin, "s1", 0.0))
        assert calls == []   # 节流命中：不该走到 dispatch

    def test_bridge_available_and_allowed_dispatches(self) -> None:
        calls: list[str] = []

        class _Bridge:
            def available(self) -> bool:
                return True

            def should_dispatch_now(self, session_key: str):
                return True, "ok"

            def build_motivation_text(self, *a, **kw):  # noqa: ANN002,ANN003
                return "忙完了回来啦"

            async def dispatch(self, session_key: str, motivation_text: str):
                calls.append(motivation_text)

        plugin = type("P", (), {"_proactive_bridge": _Bridge()})()
        asyncio.run(ig._winddown_return_after(plugin, "s1", 0.0))
        assert calls == ["忙完了回来啦"]


# ===========================================================================
# T2-03④⑤⑥ 端到端（真 host）：winddown 点燃 → 开窗 → hold 偏置注入 → 返场退化线索
# ===========================================================================


class _FakeLifeSimForWinddown:
    """最小生活模拟桩：只暴露 integration 消费的只读接口，enabled 恒真。"""

    enabled = True

    class _World:
        phase = "afternoon"
        energy = 0.6
        focus = 0.95

    def __init__(self) -> None:
        self.state = type("S", (), {"world": self._World()})()

    def undertone_cue(self):
        return None

    def interruptibility(self) -> float:
        return 0.05

    def current_activity_duration_min(self):
        return 20   # 分钟，落在 [15,45] 区间内不用夹


class TestWinddownEndToEnd:
    def test_winddown_fires_opens_window_and_biases_same_turn(self) -> None:
        plugin = _make_host_plugin(config={
            "sylanne_enable_v2core": True,
            "sylanne_alpha_winddown_enabled": True,
        })
        plugin._life_simulator = _FakeLifeSimForWinddown()
        plugin._realtime_dispatch = _CapturingScheduler()

        class _Req:
            system_prompt = ""

        req = _Req()
        asyncio.run(ig.apply_v2core_request(plugin, _Event(), req))

        rt = ig._runtime_for(plugin, "u1")
        assert rt.get("winddown_until") is not None
        assert rt["winddown_until"] > 0.0
        pending_ctx = rt["pending"]["ctx"]
        assert pending_ctx.scratch.get("winddown_active") is True
        assert pending_ctx.scratch.get("winddown_hold_bias", 0.0) > 0.0
        assert "先去忙" in (req.system_prompt or "") or "收个尾" in (req.system_prompt or "")

    def test_config_off_never_touches_winddown_state(self) -> None:
        plugin = _make_host_plugin(config={"sylanne_enable_v2core": True})
        plugin._life_simulator = _FakeLifeSimForWinddown()
        plugin._realtime_dispatch = _CapturingScheduler()

        class _Req:
            system_prompt = ""

        req = _Req()
        asyncio.run(ig.apply_v2core_request(plugin, _Event(), req))
        rt = ig._runtime_for(plugin, "u1")
        assert rt.get("winddown_until") is None
        assert plugin._realtime_dispatch.scheduled == []

    def test_return_cue_surfaces_after_window_expires(self) -> None:
        plugin = _make_host_plugin(config={
            "sylanne_enable_v2core": True,
            "sylanne_alpha_winddown_enabled": True,
        })
        # 本例只验证⑥的退化路径本身，不掺和"她还忙着"的新一轮点燃——否则
        # _act_winddown 会在窗口过期的同一轮再次达标点燃，_start_winddown_window
        # 重开新窗口顺带把 return_notified 重置回 False，掩盖了本条要测的东西。
        # 真实运行时不会撞：不应期（3h）会挡住同一轮里的重复点燃。
        plugin._life_simulator = None
        plugin._realtime_dispatch = _CapturingScheduler()

        rt = ig._runtime_for(plugin, "u1")
        # 模拟"窗口早就过去了"：直接把 rt 状态摆到过期
        rt["winddown_until"] = 1.0   # 远早于 time.time()
        rt["winddown_return_notified"] = False

        class _Req:
            system_prompt = ""

        req = _Req()
        asyncio.run(ig.apply_v2core_request(plugin, _Event(), req))
        pending_ctx = rt["pending"]["ctx"]
        assert pending_ctx.scratch.get("winddown_return_cue") is True
        assert rt["winddown_return_notified"] is True
        assert "刚把手头那件事收了尾" in (req.system_prompt or "")

    def test_dispatch_modulators_get_extra_predelay_during_window(self) -> None:
        ctx = _ctx(_body(), scratch={"winddown_hold_bias": 0.30})
        mods = ig._compose_dispatch_modulators(ctx)
        assert mods["extra_predelay_s"] > 0.0

    def test_dispatch_modulators_neutral_without_winddown_bias(self) -> None:
        ctx = _ctx(_body())
        mods = ig._compose_dispatch_modulators(ctx)
        assert mods == {"cps_mult": 1.0, "max_part_chars_mult": 1.0, "extra_predelay_s": 0.0}


# ===========================================================================
# life_simulation.py 新增公开只读方法
# ===========================================================================


class TestLifeSimulatorWinddownReaders:
    def test_interruptibility_matches_phase_table(self) -> None:
        from sylanne_alpha.life_simulation import LifePhase, LifeSimulator

        sim = LifeSimulator()
        sim.state.world.phase = LifePhase.NIGHT
        assert sim.interruptibility() == 0.25
        sim.state.world.phase = LifePhase.EVENING
        assert sim.interruptibility() == 0.5
        sim.state.world.phase = LifePhase.AFTERNOON
        assert sim.interruptibility() == 0.7

    def test_current_activity_duration_min_no_events(self) -> None:
        """MAJOR 修复回归：无事件（无计划/刚启动）→ None，不臆造。"""
        from sylanne_alpha.life_simulation import LifeSimulator

        sim = LifeSimulator()
        assert sim.current_activity_duration_min() is None

    def test_current_activity_duration_min_matches_latest_event_type(self) -> None:
        """MAJOR 修复（红队 finding）：此前按 current_activity_id 匹配 plan 锚点/弹性槽
        是死代码——current_activity_id 恒被写成事件自身 event_id，与锚点 activity_id
        是两个从未相交的 id 空间，且唯一的计划生成器从不填 expected_duration_min。
        改读最近一条真实事件的 event_type（_record_event 每 tick 真写）估算典型时长，
        本用例用生产会真正产生的状态（append 一条 LifeEvent），不再手造匹配的 id。"""
        from sylanne_alpha.life_simulation import LifeEvent, LifeSimulator

        sim = LifeSimulator()
        sim.state.events.append(
            LifeEvent(text="在读书", mood="平静", urgency=0.1, timestamp=1000.0,
                      event_type="reading")
        )
        assert sim.current_activity_duration_min() == 30

    def test_current_activity_duration_min_unknown_event_type_is_none(self) -> None:
        from sylanne_alpha.life_simulation import LifeEvent, LifeSimulator

        sim = LifeSimulator()
        sim.state.events.append(
            LifeEvent(text="？？？", mood="", urgency=0.0, timestamp=1000.0,
                      event_type="")
        )
        assert sim.current_activity_duration_min() is None

    def test_current_activity_duration_min_uses_most_recent_event(self) -> None:
        from sylanne_alpha.life_simulation import LifeEvent, LifeSimulator

        sim = LifeSimulator()
        sim.state.events.append(
            LifeEvent(text="在读书", mood="平静", urgency=0.1, timestamp=1000.0,
                      event_type="reading")
        )
        sim.state.events.append(
            LifeEvent(text="在做饭", mood="专注", urgency=0.2, timestamp=1100.0,
                      event_type="cooking")
        )
        assert sim.current_activity_duration_min() == 25


# ===========================================================================
# UserModelDomain：T2-01① 新增读接口 + 持久化容缺
# ===========================================================================


class TestUserModelDomainNewReaders:
    def test_last_user_text_and_seconds_since_last_user(self) -> None:
        from sylanne_alpha.v2core.domains.user_model import UserModelDomain

        dom = UserModelDomain()
        assert dom.last_user_text() == ""
        assert dom.seconds_since_last_user(1000.0) is None

        ctx = _ctx(_body(), text="你好呀", scratch={"now": 1000.0})
        ctx.phase = Phase.EVOLVE
        dom.ingest(ctx)
        assert dom.last_user_text() == "你好呀"

        assert dom.seconds_since_last_user(1010.0) == 10.0
        assert dom.seconds_since_last_user(990.0) is None   # 负值（now 早于历史）不给假值

    def test_persistence_round_trip_includes_last_user_text(self) -> None:
        from sylanne_alpha.v2core.domains.user_model import UserModelDomain

        dom = UserModelDomain()
        ctx = _ctx(_body(), text="记得吃饭", scratch={"now": 500.0})
        ctx.phase = Phase.EVOLVE
        dom.ingest(ctx)
        blob = dom.to_dict()
        assert blob["last_user_text"] == "记得吃饭"

        dom2 = UserModelDomain()
        dom2.load_dict(blob)
        assert dom2.last_user_text() == "记得吃饭"

    def test_load_dict_tolerates_missing_key(self) -> None:
        """旧档没有 last_user_text 字段——容缺，不炸、维持默认空串。"""
        from sylanne_alpha.v2core.domains.user_model import UserModelDomain

        dom = UserModelDomain()
        dom.load_dict({"disposition": {"warmth": 0.1}})
        assert dom.last_user_text() == ""


# ===========================================================================
# 红队 finding 修复回归：pending ctx 过期后 response 阶段现场重建的 ctx，必须挂上
# winddown 窗口偏置（否则慢响应场景会漏挂偏置，读到假中性值）——这两个 addressed
# 分支的调用点方向是对的，偏置照常生效。
#
# MAJOR 修复（另一条红队 finding）：consult_idle_reach 的空闲 ctx 不再走这条注入
# ——idle 分支是 min-cost 选择器，同一份偏置在那里方向相反（见 ignition.py），
# 窗口内改成直接短路抑制，见 _FakeBodyPort 类下方两个用例。
# ===========================================================================


class _FakeBodyPort:
    """测试桩：让 consult_idle_reach 走真实 TurnRunner/SelfCore 路径，但 body
    快照可控——不依赖真实 kernel 人格/情绪默认值算出的边际态（那些默认值不是
    本测试的契约，写死了会很脆）。"""

    def __init__(self, body: BodySnapshot) -> None:
        self._body = body

    def observe(self) -> BodySnapshot:
        return self._body


class TestWinddownScratchAppliedOnAllCtxRebuildPaths:
    def test_helper_sets_bias_within_window(self) -> None:
        ctx = _ctx(_body())
        rt = {"winddown_until": ig.time.time() + 600.0}
        ig._apply_winddown_window_scratch(ctx, rt)
        assert ctx.scratch.get("winddown_active") is True
        assert ctx.scratch.get("winddown_hold_bias") == ig._WINDDOWN_HOLD_BIAS

    def test_helper_noop_outside_window(self) -> None:
        ctx = _ctx(_body())
        rt = {"winddown_until": ig.time.time() - 600.0}
        ig._apply_winddown_window_scratch(ctx, rt)
        assert "winddown_active" not in ctx.scratch
        assert "winddown_hold_bias" not in ctx.scratch

    def test_helper_noop_without_window(self) -> None:
        ctx = _ctx(_body())
        ig._apply_winddown_window_scratch(ctx, {})
        assert "winddown_active" not in ctx.scratch

    def test_response_phase_rebuild_after_pending_ttl_expiry_keeps_bias(self) -> None:
        """慢响应场景：request 阶段暂存的 ctx 已过 TTL，response 阶段现场重建——
        重建出的新 ctx 仍应带上仍在生效的收尾窗口偏置（红队 finding，见
        _apply_winddown_window_scratch 文档）。"""
        plugin = _make_host_plugin(config={
            "sylanne_enable_v2core": True,
            "sylanne_alpha_winddown_enabled": True,
        })
        rt = ig._runtime_for(plugin, "u1")
        rt["winddown_until"] = ig.time.time() + 600.0   # 仍在窗口内
        rt["pending"] = {"ctx": object(), "ts": 0.0, "text": "在吗"}  # 陈旧到必过期

        resp = _Resp("宿主草稿")
        asyncio.run(ig.apply_v2core_response(plugin, _Event(), resp))
        # 重建路径没有直接暴露 ctx，但派发调制器是从同一个重建 ctx 合成的——
        # 窗口内应该产生非中性的 extra_predelay（证明 winddown_hold_bias 真的被读到）。
        mods = rt.get("turn_dispatch_modulators")
        assert mods is not None
        assert mods["extra_predelay_s"] > 0.0

    def test_idle_reach_consult_suppressed_in_window_but_reachable_outside(self) -> None:
        """MAJOR 修复回归：旧版本这条测试在冷启动全零信号下断言"不是 reach"——
        emo.hold_free_energy 恒 0、outreach 无信号，costs={"hold":0, "speak":..}
        里 "hold" 代价 0 是不可能被打败的最小值，断言无论修复对不对都 trivially
        成立，从未真的进过边际带，测不出红队描述的方向翻转（旧实现把
        winddown_hold_bias 也叠进这条空闲咨询的 g_hold，方向反了——见 ignition.py
        deliberate() 与本模块 consult_idle_reach 的注释）。

        这里真造一个可达 reach 的边际态（中等 reply_overdue + 小额未表达积分），
        用可控 body port 让全链路（Somatic/Expression/Outreach/Ignition）跑出确定
        数值：g_reach≈0.008 < g_hold=0.05 < g_speak≈0.4375。先证明"窗口外这套
        信号真能判成 reach"（不是编的），再证明"窗口内被直接短路抑制"——不是
        靠偏置把 g_hold 顶回去掰断方向，是 T2-03⑤ 修复后 consult_idle_reach 压根
        不再咨询 deliberate。
        """
        plugin = _make_host_plugin(config={
            "sylanne_enable_v2core": True,
            "sylanne_alpha_winddown_enabled": True,
        })
        rt = ig._runtime_for(plugin, "u1")
        asyncio.run(ig._ensure_loaded(plugin, "u1", rt))   # 先落盘态就绪，再手填边际态，避免被 load 覆盖

        body = _body(personality={"curiosity": 0.5, "warmth_bias": 0.5,
                                  "sovereignty_guard": 0.5, "patience": 0.5})
        rt["runner"]._sc._body = _FakeBodyPort(body)
        rt["domains"]["emotion"].load_dict({"unexpressed": 0.05})
        now = ig.time.time()
        rt["domains"]["usermodel"].load_dict({"rhythm_ema": 90.0, "last_user_ts": now - 150.0})

        out_no_window = asyncio.run(ig.consult_idle_reach(plugin, "u1"))
        assert out_no_window["action"] == "reach", out_no_window   # 边际带真实可达，不是编的

        rt["winddown_until"] = ig.time.time() + 600.0
        out_in_window = asyncio.run(ig.consult_idle_reach(plugin, "u1"))
        # 短路：压根没跑 deliberate，回到 consult_idle_reach 的中性默认值
        assert out_in_window == {"reach": False, "g_reach": 0.0, "action": "hold"}

    def test_in_window_reach_never_promotes_decision_action(self) -> None:
        """T2-03⑤ 修复的下游关切（红队 finding 的直接后果链）：consult_idle_reach
        的 reach 一旦被 merge_idle_reach_into_decision 升格成
        decision["action"]="reach_out"，外部主动桥会真的发一条消息、顺手消费掉
        min_interval 冷却——这会挤占 T2-03⑥ 排定的"收尾窗口结束后回来"返场触达。
        这里用同一份【窗口外本该判成 reach】的边际信号验证：窗口内 decision.action
        绝不会被升格。"""
        plugin = _make_host_plugin(config={
            "sylanne_enable_v2core": True,
            "sylanne_alpha_winddown_enabled": True,
        })
        rt = ig._runtime_for(plugin, "u1")
        asyncio.run(ig._ensure_loaded(plugin, "u1", rt))

        body = _body(personality={"curiosity": 0.5, "warmth_bias": 0.5,
                                  "sovereignty_guard": 0.5, "patience": 0.5})
        rt["runner"]._sc._body = _FakeBodyPort(body)
        rt["domains"]["emotion"].load_dict({"unexpressed": 0.05})
        now = ig.time.time()
        rt["domains"]["usermodel"].load_dict({"rhythm_ema": 90.0, "last_user_ts": now - 150.0})
        rt["winddown_until"] = ig.time.time() + 600.0

        decision = asyncio.run(
            ig.merge_idle_reach_into_decision(plugin, "u1", {"allowed": True})
        )
        assert decision.get("action") != "reach_out"
        assert decision["v2core_reach"]["action"] != "reach"
