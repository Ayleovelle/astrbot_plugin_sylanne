"""Wave-L2/T2-02：补刀与改口接线测试。

杀的问题：她从不"话说完了又想起点什么"——unfinished_replies/中断断点残留只在
【下一轮用户消息】里被动带出，从不会自己先开口追发一句。默认关闭
（sylanne_alpha_afterthought_enabled）。

覆盖：
- ① 概率/延迟纯函数：_afterthought_probability 单调 + clamp、_afterthought_roll/
  _afterthought_delay 吃种子可复现。
- ② 内容来源优先级：unfinished_replies / 中断断点残留零 LLM 开销优先，否则走
  cheap LLM 调用。
- ③ 取消：_fire_afterthought 在延迟醒来时若 last_user_message_time 已前进
  （用户插了话）就不发。原打算用 conversation_input_epoch，排查发现它只在【消息
  撤回】特殊路径才递增，普通消息完全不碰它——当锚点会让取消判定永远命不中，
  改用真正随每条消息推进的 last_user_message_time（main.py on_message 更新）。
- refractory：8 轮冷却；config off = 全程零行为（不分配状态、不骰子、不调度）。
"""

from __future__ import annotations

import asyncio
import random

from sylanne_alpha.llm_response_pipeline import (
    _AFTERTHOUGHT_DELAY_MAX,
    _AFTERTHOUGHT_DELAY_MIN,
    _AFTERTHOUGHT_PROB_CEIL,
    _AFTERTHOUGHT_PROB_FLOOR,
    _AFTERTHOUGHT_REFRACTORY_EXCHANGES,
    LLMResponsePipeline,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeSessionMap:
    def __init__(self) -> None:
        self._d: dict = {}

    def get(self, key: str, default=None):
        return self._d.get(key, default)

    def set(self, key: str, value) -> None:
        self._d[key] = value

    def pop(self, key: str, default=None):
        return self._d.pop(key, default)

    def has(self, key: str) -> bool:
        return key in self._d

    def get_or_create(self, key: str, factory):
        if key not in self._d:
            self._d[key] = factory() if callable(factory) else factory
        return self._d[key]


class _FakeStore:
    def __init__(self) -> None:
        self.unfinished_replies = _FakeSessionMap()
        self.last_user_message_time = _FakeSessionMap()
        self.afterthought_state = _FakeSessionMap()
        self.last_bot_texts = _FakeSessionMap()
        self.segmented_tasks = _FakeSessionMap()


class _FakeEngine:
    def observe(self) -> dict:
        return {"arousal": 0.5, "tension": 0.0}


class _FakeComputation:
    def __init__(self) -> None:
        self.engine = _FakeEngine()


class _FakeMortality:
    exhaustion = 0.5


class _FakeBody:
    def __init__(self) -> None:
        self.mortality = _FakeMortality()


class _FakeKernel:
    def __init__(self) -> None:
        self.body = _FakeBody()
        self.computation = _FakeComputation()


class _FakeHost:
    def __init__(self) -> None:
        self.kernel = _FakeKernel()


class _FakeContext:
    def __init__(self) -> None:
        self.sent: list[tuple[str, object]] = []

    async def send_message(self, origin: str, message: object) -> None:
        self.sent.append((origin, message))


class _FakePlugin:
    def __init__(self, *, enabled: bool = True, llm_reply: str = "") -> None:
        self._config = {"sylanne_alpha_afterthought_enabled": enabled}
        self._store = _FakeStore()
        self._background_tasks: list = []
        self.context = _FakeContext()
        self._llm_reply = llm_reply
        self.llm_calls: list[str] = []

    def _host(self, session_key: str) -> _FakeHost:
        return _FakeHost()

    async def _assessor_llm_call(self, prompt: str) -> str:
        self.llm_calls.append(prompt)
        return self._llm_reply


def _pipe(plugin) -> LLMResponsePipeline:
    return LLMResponsePipeline(plugin=plugin)  # type: ignore[arg-type]


async def _completed_task() -> None:
    return None


def _make_task() -> "asyncio.Task":
    return asyncio.ensure_future(_completed_task())


# ---------------------------------------------------------------------------
# ① 概率 / 延迟纯函数
# ---------------------------------------------------------------------------


class TestAfterthoughtProbability:
    def test_constants_match_card_spec(self) -> None:
        assert _AFTERTHOUGHT_PROB_FLOOR == 0.05
        assert _AFTERTHOUGHT_PROB_CEIL == 0.45
        assert _AFTERTHOUGHT_DELAY_MIN == 20.0
        assert _AFTERTHOUGHT_DELAY_MAX == 180.0
        assert _AFTERTHOUGHT_REFRACTORY_EXCHANGES == 8

    def test_monotonic_in_expression_drive(self) -> None:
        low = LLMResponsePipeline._afterthought_probability(0.0)
        mid = LLMResponsePipeline._afterthought_probability(0.5)
        high = LLMResponsePipeline._afterthought_probability(1.0)
        assert low == _AFTERTHOUGHT_PROB_FLOOR
        assert low < mid < high
        assert high <= _AFTERTHOUGHT_PROB_CEIL

    def test_clamps_out_of_range_input(self) -> None:
        assert LLMResponsePipeline._afterthought_probability(-5.0) == _AFTERTHOUGHT_PROB_FLOOR
        assert LLMResponsePipeline._afterthought_probability(5.0) <= _AFTERTHOUGHT_PROB_CEIL


class TestAfterthoughtRollAndDelaySeeded:
    def test_roll_deterministic_with_seed(self) -> None:
        rng_a = random.Random(42)
        rng_b = random.Random(42)
        prob = 0.3
        assert LLMResponsePipeline._afterthought_roll(
            prob, rng=rng_a
        ) == LLMResponsePipeline._afterthought_roll(prob, rng=rng_b)

    def test_roll_probability_zero_never_fires(self) -> None:
        rng = random.Random(1)
        for _ in range(50):
            assert LLMResponsePipeline._afterthought_roll(0.0, rng=rng) is False

    def test_roll_probability_one_always_fires(self) -> None:
        rng = random.Random(1)
        for _ in range(50):
            assert LLMResponsePipeline._afterthought_roll(0.999999, rng=rng) is True

    def test_delay_within_bounds_seeded(self) -> None:
        for seed in range(30):
            rng = random.Random(seed)
            delay = LLMResponsePipeline._afterthought_delay(rng=rng)
            assert _AFTERTHOUGHT_DELAY_MIN <= delay <= _AFTERTHOUGHT_DELAY_MAX

    def test_no_rng_falls_back_to_global_random(self) -> None:
        delay = LLMResponsePipeline._afterthought_delay()
        assert _AFTERTHOUGHT_DELAY_MIN <= delay <= _AFTERTHOUGHT_DELAY_MAX


class TestAfterthoughtRefractory:
    def test_refractory_blocks_within_window(self) -> None:
        assert LLMResponsePipeline._afterthought_refractory_ok(1, 0) is False
        assert LLMResponsePipeline._afterthought_refractory_ok(7, 0) is False

    def test_refractory_allows_at_boundary_and_beyond(self) -> None:
        assert LLMResponsePipeline._afterthought_refractory_ok(8, 0) is True
        assert LLMResponsePipeline._afterthought_refractory_ok(100, 0) is True

    def test_refractory_allows_first_ever_call(self) -> None:
        # last_fired_at 初始值 -1_000_000，第一次 exchange_count=1 必然放行
        assert LLMResponsePipeline._afterthought_refractory_ok(1, -1_000_000) is True


# ---------------------------------------------------------------------------
# config off = 全程零行为
# ---------------------------------------------------------------------------


class TestAfterthoughtConfigOff:
    def test_disabled_schedules_nothing_and_allocates_no_state(self) -> None:
        plugin = _FakePlugin(enabled=False)
        pipe = _pipe(plugin)

        async def _run() -> None:
            task = _make_task()
            await asyncio.sleep(0)  # let dummy task finish
            pipe._on_segment_dispatch_done_maybe_afterthought(
                task, "s1", "origin", 1.0, rng=random.Random(0)
            )
            await asyncio.sleep(0)

        asyncio.run(_run())
        assert plugin._background_tasks == []
        assert not plugin._store.afterthought_state.has("s1")


# ---------------------------------------------------------------------------
# 调度挂钩：正常完成 / 被取消 / 报错三种 task 结局
# ---------------------------------------------------------------------------


class TestAfterthoughtSchedulingHook:
    def test_cancelled_dispatch_does_not_schedule(self) -> None:
        plugin = _FakePlugin(enabled=True)
        pipe = _pipe(plugin)

        async def _run() -> None:
            async def _never() -> None:
                await asyncio.sleep(10)

            task = asyncio.ensure_future(_never())
            await asyncio.sleep(0)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            pipe._on_segment_dispatch_done_maybe_afterthought(
                task, "s1", "origin", 1.0, rng=random.Random(0)
            )
            await asyncio.sleep(0)

        asyncio.run(_run())
        assert plugin._background_tasks == []

    def test_forced_high_roll_schedules_background_task(self) -> None:
        """强制命中骰子（rng.random() 恒 0）→ 应该往 _background_tasks 里追加任务。"""
        plugin = _FakePlugin(enabled=True, llm_reply="补一句")
        pipe = _pipe(plugin)

        class _AlwaysHitRng(random.Random):
            def random(self) -> float:
                return 0.0

            def uniform(self, a: float, b: float) -> float:
                return a  # 最小延迟，测试跑快点

        async def _run() -> None:
            task = _make_task()
            await asyncio.sleep(0)
            pipe._on_segment_dispatch_done_maybe_afterthought(
                task, "s1", "origin", 1.0, rng=_AlwaysHitRng()
            )
            # afterthought 后台任务应已入列
            assert len(plugin._background_tasks) == 1
            # 双保险：也应该写进 segmented_tasks，供下一条真实请求的既有
            # stale-task-cancel 机制兜底取消
            assert plugin._store.segmented_tasks.get("s1") is plugin._background_tasks[0]
            # 让它跑完（sleep(20) 起步用假 sleep 会太慢；直接取消，只验证「被调度过」）
            bg = plugin._background_tasks[0]
            bg.cancel()
            try:
                await bg
            except asyncio.CancelledError:
                pass

        asyncio.run(_run())
        state = plugin._store.afterthought_state.get("s1")
        assert state is not None
        assert state["exchange_count"] == 1

    def test_refractory_blocks_repeated_scheduling(self) -> None:
        """连续 7 次"正常发完"都不该再触发（哪怕骰子必中）。"""
        plugin = _FakePlugin(enabled=True)
        pipe = _pipe(plugin)
        # 手动种入"刚触发过一次"的状态
        plugin._store.afterthought_state.set(
            "s1", {"exchange_count": 0, "last_fired_at": 0}
        )

        class _AlwaysHitRng(random.Random):
            def random(self) -> float:
                return 0.0

        async def _run() -> None:
            for _ in range(_AFTERTHOUGHT_REFRACTORY_EXCHANGES - 1):
                task = _make_task()
                await asyncio.sleep(0)
                pipe._on_segment_dispatch_done_maybe_afterthought(
                    task, "s1", "origin", 1.0, rng=_AlwaysHitRng()
                )
            assert plugin._background_tasks == []
            # 第 8 次达到冷却边界，应该放行调度
            task = _make_task()
            await asyncio.sleep(0)
            pipe._on_segment_dispatch_done_maybe_afterthought(
                task, "s1", "origin", 1.0, rng=_AlwaysHitRng()
            )
            assert len(plugin._background_tasks) == 1
            bg = plugin._background_tasks[0]
            bg.cancel()
            try:
                await bg
            except asyncio.CancelledError:
                pass

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# ② 内容来源优先级
# ---------------------------------------------------------------------------


class TestAfterthoughtContentSource:
    def test_prefers_unfinished_replies_zero_llm_cost(self) -> None:
        plugin = _FakePlugin(enabled=True, llm_reply="不该被调用")
        pipe = _pipe(plugin)
        plugin._store.unfinished_replies.set("s1", "还有半句没说完")
        content = pipe._afterthought_content_from_remnants("s1")
        assert content == "还有半句没说完"
        # 消费后应清空，避免被下一轮重复捡到
        assert plugin._store.unfinished_replies.get("s1") is None

    def test_falls_back_to_interrupted_breakpoint_remnants(self) -> None:
        plugin = _FakePlugin(enabled=True)
        pipe = _pipe(plugin)
        plugin._interrupted_reply_breakpoints = {
            "s1": [
                {
                    "unsent_parts": ["后半段一", "后半段二"],
                    "consumed": False,
                }
            ]
        }
        content = pipe._afterthought_content_from_remnants("s1")
        assert content == "后半段一后半段二"
        assert plugin._interrupted_reply_breakpoints["s1"][0]["consumed"] is True

    def test_no_remnants_returns_empty(self) -> None:
        plugin = _FakePlugin(enabled=True)
        pipe = _pipe(plugin)
        assert pipe._afterthought_content_from_remnants("s1") == ""

    def test_llm_content_uses_last_bot_text_as_context(self) -> None:
        plugin = _FakePlugin(enabled=True, llm_reply="  啊对了，记得喝水  ")
        plugin._store.last_bot_texts.set("s1", "今天真的好累啊")
        pipe = _pipe(plugin)
        text = asyncio.run(pipe._afterthought_llm_content("s1"))
        assert text == "啊对了，记得喝水"
        assert len(plugin.llm_calls) == 1
        assert "今天真的好累啊" in plugin.llm_calls[0]

    def test_llm_content_empty_without_last_bot_text(self) -> None:
        plugin = _FakePlugin(enabled=True, llm_reply="不该被调用")
        pipe = _pipe(plugin)
        text = asyncio.run(pipe._afterthought_llm_content("s1"))
        assert text == ""
        assert plugin.llm_calls == []


# ---------------------------------------------------------------------------
# ③ _fire_afterthought：取消 / 正常发送 / refractory 落账
# ---------------------------------------------------------------------------


class TestFireAfterthoughtCancellation:
    def test_user_interrupt_during_delay_cancels_send(self) -> None:
        """last_user_message_time 在延迟期间前进（用户插了话）→ 不发送、不消耗内容。"""
        plugin = _FakePlugin(enabled=True)
        plugin._store.unfinished_replies.set("s1", "残留内容")
        pipe = _pipe(plugin)

        orig_sleep = asyncio.sleep

        async def _fake_sleep(seconds: float) -> None:
            # 模拟：睡觉这段时间用户发了新消息，last_user_message_time 前进
            plugin._store.last_user_message_time.set("s1", 100.0)
            await orig_sleep(0)

        asyncio.sleep = _fake_sleep  # type: ignore[assignment]
        try:
            asyncio.run(
                pipe._fire_afterthought("s1", "origin", 1.0, delay=20.0)
            )
        finally:
            asyncio.sleep = orig_sleep  # type: ignore[assignment]

        assert plugin.context.sent == []
        # 内容残留应该保持未消费（没被消耗掉，供下轮正常路径用）
        assert plugin._store.unfinished_replies.get("s1") == "残留内容"

    def test_no_interrupt_sends_and_updates_refractory(self) -> None:
        plugin = _FakePlugin(enabled=True)
        plugin._store.unfinished_replies.set("s1", "还有点想说的")
        plugin._store.afterthought_state.set(
            "s1", {"exchange_count": 3, "last_fired_at": -1_000_000}
        )
        pipe = _pipe(plugin)

        orig_sleep = asyncio.sleep

        async def _fake_sleep(seconds: float) -> None:
            await orig_sleep(0)

        asyncio.sleep = _fake_sleep  # type: ignore[assignment]
        try:
            # 锚点等于 last_user_message_time 默认值（0.0）且期间未再变化 → 视为未插话
            asyncio.run(
                pipe._fire_afterthought("s1", "origin", 0.0, delay=20.0)
            )
        finally:
            asyncio.sleep = orig_sleep  # type: ignore[assignment]

        assert len(plugin.context.sent) >= 1
        state = plugin._store.afterthought_state.get("s1")
        assert state["last_fired_at"] == 3

    def test_config_disabled_after_scheduling_aborts_send(self) -> None:
        """延迟期间被关掉 config（或原本就没开）→ 不发送。"""
        plugin = _FakePlugin(enabled=False)
        plugin._store.unfinished_replies.set("s1", "残留内容")
        pipe = _pipe(plugin)

        orig_sleep = asyncio.sleep

        async def _fake_sleep(seconds: float) -> None:
            await orig_sleep(0)

        asyncio.sleep = _fake_sleep  # type: ignore[assignment]
        try:
            asyncio.run(pipe._fire_afterthought("s1", "origin", 0, delay=20.0))
        finally:
            asyncio.sleep = orig_sleep  # type: ignore[assignment]

        assert plugin.context.sent == []

    def test_no_content_available_sends_nothing(self) -> None:
        """没有残留、LLM 也返回空 → 静默不发（不硬凑话）。"""
        plugin = _FakePlugin(enabled=True, llm_reply="")
        pipe = _pipe(plugin)

        orig_sleep = asyncio.sleep

        async def _fake_sleep(seconds: float) -> None:
            await orig_sleep(0)

        asyncio.sleep = _fake_sleep  # type: ignore[assignment]
        try:
            asyncio.run(pipe._fire_afterthought("s1", "origin", 0, delay=20.0))
        finally:
            asyncio.sleep = orig_sleep  # type: ignore[assignment]

        assert plugin.context.sent == []
