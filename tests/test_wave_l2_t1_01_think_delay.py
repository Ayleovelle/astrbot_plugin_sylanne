"""Wave-L2/T1-01：读信时间接线测试。

杀的问题：零思考时间瞬发首段——深夜 300 字表白和一句"哦"此前拿到完全相同的
LLM 速度瞬发首段回复；流式首句抢发更是直接和 LLM 流赛跑，越抢越快。

覆盖：
- ① `_think_delay` 纯函数：种子固定下的边界（floor/ceiling）、长短消息差异、
  情绪强度反向关系（越强越快回）、gap 越久越慢一点。
- ② `_incoming_think_delay`：真实 host/event 接线（previous_event 取 gap、
  _text(event) 取消息、_body_signals 取 energy/arousal/tension）。
- ③ `realtime_plan(first_delay=...)`：首段吃到传入的 think_delay，不再恒为 0；
   不传时（默认 0）保持 wave-1 既有行为不变（回归保护）。
- ④ `_send_first_sentence`：流式抢发路径按 delay 睡够，不再零延迟直发。
"""

from __future__ import annotations

import asyncio
import random
import time

from sylanne_alpha.llm_response_pipeline import (
    _THINK_DELAY_CEILING,
    _THINK_DELAY_FLOOR,
    LLMResponsePipeline,
)
from sylanne_alpha.message_dispatch import _message_parts, realtime_plan


def _pipe() -> LLMResponsePipeline:
    return LLMResponsePipeline(plugin=object())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ① _think_delay 纯函数
# ---------------------------------------------------------------------------


class TestThinkDelayBounds:
    def test_always_within_conservative_range_seeded(self) -> None:
        """任意权重组合（含极端 arousal/tension/energy/gap）都不越出 [0.8, 6.0]。"""
        p = _pipe()
        for seed in range(50):
            rng = random.Random(seed)
            for arousal in (0.0, 0.5, 1.0):
                for tension in (0.0, 1.0):
                    for energy in (0.0, 1.0):
                        for gap in (0.0, 600.0, 999999.0):
                            delay = p._think_delay(
                                "随便一条消息内容",
                                arousal=arousal,
                                tension=tension,
                                energy=energy,
                                gap_seconds=gap,
                                rng=rng,
                            )
                            assert _THINK_DELAY_FLOOR <= delay <= _THINK_DELAY_CEILING

    def test_constants_match_card_spec(self) -> None:
        assert _THINK_DELAY_FLOOR == 0.8
        assert _THINK_DELAY_CEILING == 6.0

    def test_no_rng_falls_back_to_global_random(self) -> None:
        p = _pipe()
        delay = p._think_delay(
            "测试消息", arousal=0.5, tension=0.0, energy=0.5, gap_seconds=0.0
        )
        assert _THINK_DELAY_FLOOR <= delay <= _THINK_DELAY_CEILING


class TestThinkDelayLengthSensitivity:
    def test_long_message_delays_more_than_short(self) -> None:
        """长消息（300 字深夜表白）读信时间必须明显长于短消息（一句"哦"）。"""
        p = _pipe()
        short_text = "哦"
        long_text = "这段话很长很长" * 60  # 远超 300 字
        for seed in range(20):
            rng_short = random.Random(seed)
            rng_long = random.Random(seed)
            short_delay = p._think_delay(
                short_text,
                arousal=0.5,
                tension=0.0,
                energy=0.5,
                gap_seconds=0.0,
                rng=rng_short,
            )
            long_delay = p._think_delay(
                long_text,
                arousal=0.5,
                tension=0.0,
                energy=0.5,
                gap_seconds=0.0,
                rng=rng_long,
            )
            assert long_delay > short_delay, (
                f"seed={seed} short={short_delay} long={long_delay}"
            )


class TestThinkDelayIntensityInverse:
    def test_higher_intensity_replies_faster(self) -> None:
        """情绪强度（arousal 代理）越高，think_delay 越小（重话该更快回，不是更慢）。"""
        p = _pipe()
        text = "这是一条中等长度的消息内容用来测试"
        for seed in range(20):
            rng_low = random.Random(seed)
            rng_high = random.Random(seed)
            low_intensity_delay = p._think_delay(
                text, arousal=0.0, tension=0.0, energy=0.5, gap_seconds=0.0, rng=rng_low
            )
            high_intensity_delay = p._think_delay(
                text, arousal=1.0, tension=0.0, energy=0.5, gap_seconds=0.0, rng=rng_high
            )
            assert high_intensity_delay <= low_intensity_delay


class TestThinkDelayGapAndEnergy:
    def test_long_gap_slower_reengage(self) -> None:
        """隔了很久重新搭话（长 gap）应该比刚聊完接着回稍微慢一点。"""
        p = _pipe()
        text = "好久不见啦最近怎么样"
        for seed in range(20):
            rng_short_gap = random.Random(seed)
            rng_long_gap = random.Random(seed)
            short_gap_delay = p._think_delay(
                text,
                arousal=0.5,
                tension=0.0,
                energy=0.5,
                gap_seconds=0.0,
                rng=rng_short_gap,
            )
            long_gap_delay = p._think_delay(
                text,
                arousal=0.5,
                tension=0.0,
                energy=0.5,
                gap_seconds=7200.0,
                rng=rng_long_gap,
            )
            assert long_gap_delay >= short_gap_delay

    def test_low_energy_slower(self) -> None:
        """没精神（energy 低）启动更慢。"""
        p = _pipe()
        text = "今天有点累想聊会儿天"
        for seed in range(20):
            rng_high_energy = random.Random(seed)
            rng_low_energy = random.Random(seed)
            high_energy_delay = p._think_delay(
                text,
                arousal=0.5,
                tension=0.0,
                energy=1.0,
                gap_seconds=0.0,
                rng=rng_high_energy,
            )
            low_energy_delay = p._think_delay(
                text,
                arousal=0.5,
                tension=0.0,
                energy=0.0,
                gap_seconds=0.0,
                rng=rng_low_energy,
            )
            assert low_energy_delay >= high_energy_delay


# ---------------------------------------------------------------------------
# ② _incoming_think_delay：真实 host/event 接线
# ---------------------------------------------------------------------------


class _FakeEngine:
    def __init__(self, arousal: float, tension: float) -> None:
        self._obs = {"arousal": arousal, "tension": tension}

    def observe(self) -> dict:
        return self._obs


class _FakeComputation:
    def __init__(self, arousal: float, tension: float) -> None:
        self.engine = _FakeEngine(arousal, tension)


class _FakeMortality:
    def __init__(self, exhaustion: float) -> None:
        self.exhaustion = exhaustion


class _FakeBody:
    def __init__(self, exhaustion: float) -> None:
        self.mortality = _FakeMortality(exhaustion)


class _FakeKernel:
    def __init__(
        self,
        exhaustion: float,
        arousal: float,
        tension: float,
        previous_event: dict | None = None,
    ) -> None:
        self.body = _FakeBody(exhaustion)
        self.computation = _FakeComputation(arousal, tension)
        self.previous_event = previous_event or {}


class _FakeHost:
    def __init__(
        self,
        exhaustion: float = 0.5,
        arousal: float = 0.5,
        tension: float = 0.0,
        previous_event: dict | None = None,
    ) -> None:
        self.kernel = _FakeKernel(exhaustion, arousal, tension, previous_event)


class _FakePlugin:
    def __init__(self, host: _FakeHost) -> None:
        self._host_obj = host

    def _host(self, session_key: str) -> _FakeHost:
        return self._host_obj


class _FakeEvent:
    def __init__(self, message_str: str) -> None:
        self.message_str = message_str
        self.message_chain = None
        self.unified_msg_origin = "test:origin"


class TestIncomingThinkDelayWiring:
    def test_reads_gap_from_previous_event(self) -> None:
        """gap_seconds 正确来自 host.kernel.previous_event['now']（既有字段，
        与 kernel.py 内部 _has_sovereignty_opt_in 同一读法）。"""
        host = _FakeHost(previous_event={"now": time.time() - 10000.0, "text": "早前的消息"})
        plugin = _FakePlugin(host)
        pipe = LLMResponsePipeline(plugin=plugin)  # type: ignore[arg-type]
        event = _FakeEvent("嗯")
        delay = pipe._incoming_think_delay(event, "s")
        assert _THINK_DELAY_FLOOR <= delay <= _THINK_DELAY_CEILING

    def test_no_previous_event_defaults_gap_zero(self) -> None:
        """首次事件（无 previous_event）不应崩，gap 视为 0。"""
        host = _FakeHost(previous_event={})
        plugin = _FakePlugin(host)
        pipe = LLMResponsePipeline(plugin=plugin)  # type: ignore[arg-type]
        event = _FakeEvent("你好")
        delay = pipe._incoming_think_delay(event, "s")
        assert _THINK_DELAY_FLOOR <= delay <= _THINK_DELAY_CEILING

    def test_long_vs_short_incoming_message_measurably_differ(self) -> None:
        """card 验收点：长短消息产生可测量不同的首段延迟。"""
        host = _FakeHost()
        plugin = _FakePlugin(host)
        pipe = LLMResponsePipeline(plugin=plugin)  # type: ignore[arg-type]
        short_event = _FakeEvent("哦")
        long_event = _FakeEvent("这是一条非常长的深夜消息内容" * 20)
        short_delay = pipe._incoming_think_delay(short_event, "s")
        long_delay = pipe._incoming_think_delay(long_event, "s")
        assert long_delay > short_delay


# ---------------------------------------------------------------------------
# ③ realtime_plan(first_delay=...) 接线
# ---------------------------------------------------------------------------


class TestRealtimePlanFirstDelay:
    def test_first_delay_overrides_first_segment(self) -> None:
        plan = realtime_plan(
            "s", "第一段。第二段稍微长一点内容。", first_delay=2.5
        )
        parts = plan["message_parts"]
        assert parts[0]["delay_before_seconds"] == 2.5

    def test_default_first_delay_zero_keeps_wave1_behavior(self) -> None:
        """不传 first_delay（默认 0）：首段仍恒为 0，wave-1 既有测试不受影响。"""
        plan = realtime_plan("s", "第一段。第二段稍微长一点内容。")
        parts = plan["message_parts"]
        assert parts[0]["delay_before_seconds"] == 0.0

    def test_message_parts_first_delay_param_directly(self) -> None:
        parts = ["第一段", "第二段内容长一些", "第三段也补一点内容"]
        rng = random.Random(1)
        message_parts = _message_parts(parts, chars_per_second=7.5, rng=rng, first_delay=3.3)
        assert message_parts[0]["delay_before_seconds"] == 3.3
        # 非首段仍走既有抖动/走神逻辑，不受 first_delay 影响的硬顶约束破坏
        for mp in message_parts[1:]:
            assert 0.0 <= mp["delay_before_seconds"] <= 9.0 + 1e-6

    def test_first_delay_leaves_other_segments_within_existing_bounds(self) -> None:
        """first_delay 只覆盖首段展示值；非首段仍受既有硬顶/走神约束（不会因为
        首段改走新分支而破坏其余段的取值范围——注：首段跳过 jitter 抽样会挪动
        该 rng 流后续段的具体取值，这是预期行为，不在此断言逐段相等）。"""
        parts = ["第一段", "第二段内容长一些", "第三段也补一点内容"]
        rng = random.Random(7)
        with_first_delay = _message_parts(
            parts, chars_per_second=7.5, rng=rng, first_delay=4.0
        )
        assert with_first_delay[0]["delay_before_seconds"] == 4.0
        for mp in with_first_delay[1:]:
            assert 0.0 <= mp["delay_before_seconds"] <= 9.0 + 1e-6


# ---------------------------------------------------------------------------
# ④ _send_first_sentence 按 delay 睡够
# ---------------------------------------------------------------------------


class TestSendFirstSentenceHonorsDelay:
    def test_sleeps_at_least_given_delay(self) -> None:
        """delay>0 时先 sleep 再发送；用 monkeypatch 捕获 sleep 时长断言 >= floor。"""
        sleep_calls: list[float] = []

        class _FakeContext:
            def __init__(self) -> None:
                self.sent: list[tuple[str, object]] = []

            async def send_message(self, origin: str, message: object) -> None:
                self.sent.append((origin, message))

        class _FakePluginWithContext:
            def __init__(self) -> None:
                self.context = _FakeContext()

        async def _fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        plugin = _FakePluginWithContext()
        pipe = LLMResponsePipeline(plugin=plugin)  # type: ignore[arg-type]

        orig_sleep = asyncio.sleep
        asyncio.sleep = _fake_sleep  # type: ignore[assignment]
        try:
            asyncio.run(
                pipe._send_first_sentence("origin", "你好呀", delay=_THINK_DELAY_FLOOR)
            )
        finally:
            asyncio.sleep = orig_sleep  # type: ignore[assignment]

        assert sleep_calls == [_THINK_DELAY_FLOOR]
        assert len(plugin.context.sent) == 1
        sent_origin, sent_message = plugin.context.sent[0]
        assert sent_origin == "origin"
        # message 可能是纯字符串，也可能是 AstrBot MessageChain(Plain) —— 两种都接受
        sent_text = getattr(sent_message, "chain", None) or sent_message
        if isinstance(sent_text, list):
            sent_text = "".join(str(getattr(c, "text", "")) for c in sent_text)
        assert "你好呀" in str(sent_text)

    def test_zero_delay_skips_sleep(self) -> None:
        """delay=0（既有默认行为）不 sleep，向后兼容。"""
        sleep_called = False

        class _FakeContext:
            async def send_message(self, origin: str, message: object) -> None:
                pass

        class _FakePluginWithContext:
            def __init__(self) -> None:
                self.context = _FakeContext()

        async def _fake_sleep(seconds: float) -> None:
            nonlocal sleep_called
            sleep_called = True

        plugin = _FakePluginWithContext()
        pipe = LLMResponsePipeline(plugin=plugin)  # type: ignore[arg-type]

        orig_sleep = asyncio.sleep
        asyncio.sleep = _fake_sleep  # type: ignore[assignment]
        try:
            asyncio.run(pipe._send_first_sentence("origin", "你好呀"))
        finally:
            asyncio.sleep = orig_sleep  # type: ignore[assignment]

        assert sleep_called is False
