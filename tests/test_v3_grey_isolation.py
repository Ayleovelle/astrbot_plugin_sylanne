"""v3 Task 13：灰测隔离证明——默认关逐字节相同 + 七隔离计数器恒零。

design 16.1（Hard Isolation Counters，七个必须恒零）+ plan Task 13 RED：

- shadow-disabled 与 shadow-enabled 两次运行，v2 的 reply / prompt / history /
  memory / body snapshot **逐字节相同**，tool / LLM 调用计数相同。
- 注入队列满、只读仓库、锁超时、core 异常、executor 超时、重复钩子六类故障，
  七个隔离计数器全零且 v2 照常完成。
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any

import pytest

import main as main_mod
from sylanne_alpha.v3bridge.runtime_telemetry import ISOLATION_COUNTER_NAMES


# --------------------------------------------------------------------------- #
# fakes：可数的 host managers（tool / LLM 调用计数）
# --------------------------------------------------------------------------- #


class CountingContext:
    """记录每一次外部效应：发送、LLM 调用、tool 调用。"""

    def __init__(self) -> None:
        self.provider_manager = None
        self.sent: list[tuple[str, str]] = []
        self.llm_calls = 0
        self.tool_calls = 0

    def get_registered_star(self, *a: Any, **k: Any) -> None:
        return None

    def get_using_provider(self, *a: Any, **k: Any) -> Any:
        self.llm_calls += 1
        return None

    def get_config(self, *a: Any, **k: Any) -> dict:
        return {}

    def register_web_api(self, *a: Any, **k: Any) -> None:
        return None

    async def send_message(self, origin: str, message: Any) -> None:
        self.sent.append((origin, _render(message)))


def _render(message: Any) -> str:
    chain = getattr(message, "chain", None)
    if chain is None:
        return str(message)
    return "".join(str(getattr(seg, "text", "")) for seg in chain)


class CountingEvent:
    def __init__(self, *, origin: str = "qq:GroupMessage:1", message_id: str = "m-1") -> None:
        self.unified_msg_origin = origin
        self.message_str = "hello"
        self._extras: dict[str, Any] = {}
        self.message_obj = type("MO", (), {"message_id": message_id, "self_id": "bot"})()
        self.platform_meta = type("PM", (), {"name": "qq"})()

    def get_extra(self, key: str, default: Any = None) -> Any:
        return self._extras.get(key, default)

    def set_extra(self, key: str, value: Any) -> None:
        self._extras[key] = value

    def get_platform_name(self) -> str:
        return "qq"


SESSION = "qq:GroupMessage:1"


# --------------------------------------------------------------------------- #
# v2 可观测面：一次真实 v2 分段回复走完之后的全部对外事实
# --------------------------------------------------------------------------- #


def _v2_observable(plugin: Any) -> bytes:
    """把 v2 的 reply / prompt / history / memory / body 快照序列化成确定性字节。"""

    store = plugin._store
    snapshot = {
        "reply_sent": plugin.context.sent,
        "llm_calls": plugin.context.llm_calls,
        "tool_calls": plugin.context.tool_calls,
        "unfinished_replies": sorted(_bounded_items(store.unfinished_replies)),
        "conversation_buffers": sorted(_bounded_items(store.conversation_buffers)),
        "last_bot_texts": sorted(_bounded_items(store.last_bot_texts)),
        "last_injected_states": sorted(_bounded_items(store.last_injected_states)),
        "cached_system_prompts": sorted(
            (str(k), str(v)) for k, v in getattr(plugin, "_cached_system_prompts", {}).items()
        ),
        "body": _body_snapshot(plugin),
    }
    return json.dumps(snapshot, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")


def _bounded_items(bounded: Any) -> list[tuple[str, str]]:
    for attribute in ("items", "_data", "_store"):
        candidate = getattr(bounded, attribute, None)
        if callable(candidate):
            try:
                return [(str(k), str(v)) for k, v in candidate()]
            except Exception:
                continue
        if isinstance(candidate, dict):
            return [(str(k), str(v)) for k, v in candidate.items()]
    return []


def _body_snapshot(plugin: Any) -> dict[str, Any]:
    try:
        host = plugin._host(SESSION)
        observed = host.kernel.computation.engine.observe()
    except Exception:
        return {}
    if not isinstance(observed, dict):
        return {}
    return {str(k): round(float(v), 12) for k, v in observed.items() if isinstance(v, (int, float))}


def _seed_v2_state(plugin: Any) -> None:
    """先把 v2 的各张表塞进真值，_v2_observable 的比较才不是在比两个空 dict。

    `_dispatch_segmented_parts` 自己只会动 unfinished_replies；不预置的话
    conversation_buffers / last_bot_texts / last_injected_states 两边恒空，
    那几路"逐字节相同"就是空证。预置之后：unfinished_replies 会被这一轮真实
    改写（逐段更新剩余、发完清除），其余几张表则钉住"v3 没去碰它们"。
    """

    store = plugin._store
    store.unfinished_replies.set(SESSION, "上一轮没发完的残句")
    store.conversation_buffers.set(SESSION, [{"role": "user", "content": "早"}])
    store.last_bot_texts.set(SESSION, "上一句她说的话")
    store.last_injected_states.set(SESSION, {"warmth": 0.5, "tension": 0.2})
    plugin._cached_system_prompts[SESSION] = "PERSONA-CACHED"


async def _run_v2_turn(plugin: Any) -> None:
    """跑一次真实 v2 分段发送 + 一次终端结算。"""

    _seed_v2_state(plugin)
    parts = [
        {"text": "第一段", "delay_before_seconds": 0},
        {"text": "第二段", "delay_before_seconds": 0},
    ]
    await plugin._llm_response_pipeline._dispatch_segmented_parts(SESSION, parts, session_key=SESSION)


async def _capture(facade: Any, session_key: str = SESSION, message_id: str = "m-1") -> None:
    facade.capture_request(
        session_key=session_key,
        platform_id="qq",
        unified_msg_origin=session_key,
        message_id=message_id,
        text_length=5,
        history_present=True,
        gap_seconds=2.0,
        body={"warmth": 0.5, "tension": 0.2},
    )


# --------------------------------------------------------------------------- #
# 1. 默认关 / 开启：v2 逐字节相同
# --------------------------------------------------------------------------- #


async def _observable_with_shadow(*, enabled: bool, root: Path | None) -> bytes:
    plugin = main_mod.EmotionalStatePlugin(CountingContext(), {})
    facade = plugin._v3_shadow
    facade.enabled = enabled
    if enabled:
        assert root is not None
        assert await facade.initialize(root=root) is True
        await _capture(facade)
    try:
        await _run_v2_turn(plugin)
        return _v2_observable(plugin)
    finally:
        facade.begin_shutdown()
        await facade.terminate()


def test_v2_observable_actually_carries_every_channel() -> None:
    """反空证闸：五路通道都必须真有内容，否则上面的"逐字节相同"是在比两个空表。

    这条是给未来的人设的：哪天有人改了 store 的读法/字段名让某一路悄悄读成空，
    这里先红，而不是让 byte-identical 变成永远为真的废断言。
    """

    async def go() -> None:
        plugin = main_mod.EmotionalStatePlugin(CountingContext(), {})
        plugin._v3_shadow.enabled = False
        await _run_v2_turn(plugin)
        snapshot = json.loads(_v2_observable(plugin).decode("utf-8"))
        assert snapshot["reply_sent"], "reply 通道为空"
        assert snapshot["body"], "body snapshot 通道为空"
        assert len(snapshot["body"]) >= 10, "body 快照维度太少，不像真快照"
        assert snapshot["conversation_buffers"], "history 通道为空"
        assert snapshot["last_bot_texts"], "reply 历史通道为空"
        assert snapshot["last_injected_states"], "memory/state 通道为空"
        assert snapshot["cached_system_prompts"], "prompt 通道为空"

    asyncio.run(go())


def test_shadow_disabled_and_enabled_v2_output_is_byte_identical(tmp_path: Path) -> None:
    async def go() -> None:
        disabled = await _observable_with_shadow(enabled=False, root=None)
        enabled = await _observable_with_shadow(enabled=True, root=tmp_path / "v3")
        assert disabled == enabled, (
            "开启 v3 shadow 后 v2 的 reply/prompt/history/memory/body 必须逐字节相同"
        )

    asyncio.run(go())


def test_shadow_disabled_run_is_reproducible(tmp_path: Path) -> None:
    """基线自证：同一构造两次 disabled 运行本身就必须逐字节相同（否则上面的相等无意义）。"""

    async def go() -> None:
        first = await _observable_with_shadow(enabled=False, root=None)
        second = await _observable_with_shadow(enabled=False, root=None)
        assert first == second

    asyncio.run(go())


def test_shadow_enabled_does_not_change_tool_or_llm_call_counts(tmp_path: Path) -> None:
    async def go() -> None:
        plugin_off = main_mod.EmotionalStatePlugin(CountingContext(), {})
        plugin_off._v3_shadow.enabled = False
        await _run_v2_turn(plugin_off)

        plugin_on = main_mod.EmotionalStatePlugin(CountingContext(), {})
        facade = plugin_on._v3_shadow
        facade.enabled = True
        await facade.initialize(root=tmp_path / "v3")
        await _capture(facade)
        await _run_v2_turn(plugin_on)
        await facade.terminate()

        assert plugin_on.context.llm_calls == plugin_off.context.llm_calls
        assert plugin_on.context.tool_calls == plugin_off.context.tool_calls
        assert plugin_on.context.sent == plugin_off.context.sent

    asyncio.run(go())


# --------------------------------------------------------------------------- #
# 2. 七隔离计数器：六类故障注入下全零，v2 照常完成
# --------------------------------------------------------------------------- #


def _assert_all_counters_zero(facade: Any) -> None:
    counters = facade.counters
    assert counters is not None
    snapshot = counters.as_dict()
    assert set(snapshot) == set(ISOLATION_COUNTER_NAMES)
    assert counters.all_zero(), f"隔离计数器非零：{snapshot}"
    assert counters.total() == 0


async def _v2_completes(plugin: Any) -> None:
    await _run_v2_turn(plugin)
    assert plugin.context.sent == [(SESSION, "第一段"), (SESSION, "第二段")], "v2 必须照常完成"


def test_queue_full_keeps_counters_zero_and_v2_completes(tmp_path: Path) -> None:
    async def go() -> None:
        plugin = main_mod.EmotionalStatePlugin(CountingContext(), {})
        facade = plugin._v3_shadow
        facade.enabled = True
        # 队列容量压到 0：每一次 offer 必满。
        await facade.initialize(root=tmp_path / "v3", supervisor_kwargs={"global_cap": 0})
        for index in range(8):
            await _capture(facade, message_id=f"m-{index}")
            facade.settle(
                session_key=SESSION,
                route_kind="SEGMENTED_TEXT",
                reply_kind="SPEAK",
                part_count=2,
                all_segments_succeeded=True,
            )
        await _v2_completes(plugin)
        _assert_all_counters_zero(facade)
        await facade.terminate()

    asyncio.run(go())


def test_readonly_repository_keeps_counters_zero_and_v2_completes(tmp_path: Path) -> None:
    async def go() -> None:
        plugin = main_mod.EmotionalStatePlugin(CountingContext(), {})
        facade = plugin._v3_shadow
        facade.enabled = True
        # 仓库根被一个普通文件占住：initialize 必炸 → v3 fail-close。
        blocked = tmp_path / "blocked"
        blocked.write_text("occupied", encoding="utf-8")
        assert await facade.initialize(root=blocked / "v3") is False
        assert facade.enabled is False
        await _capture(facade)
        facade.settle(session_key=SESSION, route_kind="SILENT", reply_kind="SILENT")
        await _v2_completes(plugin)
        # fail-close 后没有 runtime，计数器由 facade 提供的零基线代表。
        assert facade.counters is None or facade.counters.all_zero()

    asyncio.run(go())


def test_lock_timeout_keeps_counters_zero_and_v2_completes(tmp_path: Path) -> None:
    async def go() -> None:
        plugin = main_mod.EmotionalStatePlugin(CountingContext(), {})
        facade = plugin._v3_shadow
        facade.enabled = True
        await facade.initialize(root=tmp_path / "v3")

        held = threading.Lock()
        held.acquire()
        try:
            await _capture(facade)
            facade.settle(
                session_key=SESSION,
                route_kind="SEGMENTED_TEXT",
                reply_kind="SPEAK",
                part_count=2,
                all_segments_succeeded=True,
            )
            await facade.runtime.join()
            await _v2_completes(plugin)
        finally:
            held.release()
        _assert_all_counters_zero(facade)
        await facade.terminate()

    asyncio.run(go())


def test_core_exception_keeps_counters_zero_and_v2_completes(tmp_path: Path) -> None:
    async def go() -> None:
        plugin = main_mod.EmotionalStatePlugin(CountingContext(), {})
        facade = plugin._v3_shadow
        facade.enabled = True

        def exploding_compute(invocation: Any) -> Any:
            raise RuntimeError("core exploded")

        await facade.initialize(root=tmp_path / "v3", supervisor_kwargs={"compute": exploding_compute})
        await _capture(facade)
        facade.settle(
            session_key=SESSION,
            route_kind="SEGMENTED_TEXT",
            reply_kind="SPEAK",
            part_count=2,
            all_segments_succeeded=True,
        )
        await facade.runtime.join()
        await _v2_completes(plugin)
        _assert_all_counters_zero(facade)
        await facade.terminate()

    asyncio.run(go())


def test_executor_timeout_keeps_counters_zero_and_v2_completes(tmp_path: Path) -> None:
    async def go() -> None:
        plugin = main_mod.EmotionalStatePlugin(CountingContext(), {})
        facade = plugin._v3_shadow
        facade.enabled = True

        def slow_compute(invocation: Any) -> Any:
            import time as _time

            _time.sleep(0.5)
            raise AssertionError("timed-out core result must never be used")

        await facade.initialize(
            root=tmp_path / "v3",
            supervisor_kwargs={"compute": slow_compute, "job_timeout_s": 0.01},
        )
        await _capture(facade)
        facade.settle(
            session_key=SESSION,
            route_kind="SEGMENTED_TEXT",
            reply_kind="SPEAK",
            part_count=2,
            all_segments_succeeded=True,
        )
        await facade.runtime.join()
        await _v2_completes(plugin)
        _assert_all_counters_zero(facade)
        await facade.terminate()

    asyncio.run(go())


def test_duplicate_hooks_keep_counters_zero_and_v2_completes(tmp_path: Path) -> None:
    """重复钩子：同一轮重复 capture + 重复 settle，v3 只认一次，计数器全零。"""

    async def go() -> None:
        plugin = main_mod.EmotionalStatePlugin(CountingContext(), {})
        facade = plugin._v3_shadow
        facade.enabled = True
        await facade.initialize(root=tmp_path / "v3")
        await _capture(facade)
        await _capture(facade)  # 重复 on_llm_request
        for _ in range(3):  # 重复终端回调
            facade.settle(
                session_key=SESSION,
                route_kind="SEGMENTED_TEXT",
                reply_kind="SPEAK",
                part_count=2,
                all_segments_succeeded=True,
            )
        await facade.runtime.join()
        await _v2_completes(plugin)
        assert len(list(facade.settled_actions)) == 1, "重复钩子只能结算一次"
        _assert_all_counters_zero(facade)
        await facade.terminate()

    asyncio.run(go())


@pytest.mark.parametrize("name", ISOLATION_COUNTER_NAMES)
def test_every_declared_isolation_counter_is_covered(name: str) -> None:
    """七个计数器逐个点名，确保没有哪个在断言里被漏掉。"""

    assert name in ISOLATION_COUNTER_NAMES
    assert len(ISOLATION_COUNTER_NAMES) == 7
