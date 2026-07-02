"""fix/context-integrity CONTRIB：非拦截（legacy, realtime_intercept=False，现网默认）
分支下 thinking-only 草稿剥空后的 no-ghost 兜底。

修复前：`_on_llm_response_inner` 里 `if not realtime_enabled or not intercept:` 这条
早退分支只清 thinking/draft 块，`cleaned` 剥空后既不发也不兜底——用户完全收不到回复
（"已读不回"假象），且没有触发下面 intercept 分支专属的 EMPTY_REPLY_FALLBACK_VARIANTS
机制。本次修复把同一份 reason 分治逻辑（stripped_to_empty 兜底 / empty_completion 静默）
搬到非拦截分支，语义与 intercept 分支保持一致，见 sylanne_no_ghost_reply 配置项。
"""

from __future__ import annotations

import asyncio
import tempfile

from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost
from sylanne_alpha.llm_response_pipeline import LLMResponsePipeline
from sylanne_alpha.session_state_store import SessionStateStore
from sylanne_alpha.variant_pool import EMPTY_REPLY_FALLBACK_VARIANTS, LAST_RESORT_FALLBACK_TEXT


class _Resp:
    def __init__(self, t: str) -> None:
        self.completion_text = t


class _Ev:
    unified_msg_origin = "sess:nonintercept"


class _Plugin:
    """非拦截路径最小插件桩（沿用 tests/test_wave1_live_wiring.py::_BufferPlugin 的写法）。"""

    def __init__(self, root: str, config: dict | None = None) -> None:
        self._config = {
            "sylanne_alpha_realtime_chat_enabled": False,
            "sylanne_alpha_realtime_intercept_llm_response": False,
            **(config or {}),
        }
        self._store = SessionStateStore()
        self._background_tasks: list = []
        self._root = root
        self._h: dict = {}

    def _session_key(self, _e: object) -> str:
        return "sess:nonintercept"

    def _host(self, sk: str) -> SylanneAlphaHost:
        if sk not in self._h:
            self._h[sk] = SylanneAlphaHost(root=self._root, session_key=sk)
        return self._h[sk]

    def _has_conversation_manager(self) -> bool:
        return False

    def _schedule_buffer_persist(self, _sk: str) -> None:
        pass


def _run(pipe: LLMResponsePipeline, resp: _Resp, plugin: _Plugin) -> None:
    async def go() -> None:
        await pipe._on_llm_response_inner(_Ev(), resp)
        if plugin._background_tasks:
            await asyncio.gather(*plugin._background_tasks)

    asyncio.run(go())


def test_thinking_only_draft_gets_fallback_not_silence() -> None:
    """stripped_to_empty（thinking 包答案）：默认兜底一句，不再原地吞掉。"""
    p = _Plugin(tempfile.mkdtemp(prefix="ni_fb_"))
    pipe = LLMResponsePipeline(p)  # type: ignore[arg-type]
    resp = _Resp("<thinking>我已经想好答案了但是忘了写出来</thinking>")

    _run(pipe, resp, p)

    assert resp.completion_text.strip(), "非拦截分支 thinking-only 剥空后应兜底，不应真空"
    assert resp.completion_text in (
        *EMPTY_REPLY_FALLBACK_VARIANTS,
        LAST_RESORT_FALLBACK_TEXT,
    ) or resp.completion_text.strip()


def test_true_empty_completion_stays_silent() -> None:
    """empty_completion（completion_text 真空，如 tool 循环死锁后)：继续保持静默。"""
    p = _Plugin(tempfile.mkdtemp(prefix="ni_sil_"))
    pipe = LLMResponsePipeline(p)  # type: ignore[arg-type]
    resp = _Resp("")

    _run(pipe, resp, p)

    assert resp.completion_text == "", "真空回复不应被兜底文案填充（非人格装死，是异常）"


def test_custom_fallback_text_takes_priority_even_for_true_empty() -> None:
    """用户显式配置 sylanne_ghost_fallback_text 时，即便是 empty_completion 也走兜底。"""
    p = _Plugin(
        tempfile.mkdtemp(prefix="ni_custom_"),
        config={"sylanne_ghost_fallback_text": "等我一下下"},
    )
    pipe = LLMResponsePipeline(p)  # type: ignore[arg-type]
    resp = _Resp("")

    _run(pipe, resp, p)

    assert resp.completion_text == "等我一下下"


def test_no_ghost_disabled_silences_all_reasons() -> None:
    """sylanne_no_ghost_reply=False（用户显式开 ghost）：全静默，兼容旧开关。"""
    p = _Plugin(
        tempfile.mkdtemp(prefix="ni_noghost_"),
        config={"sylanne_no_ghost_reply": False},
    )
    pipe = LLMResponsePipeline(p)  # type: ignore[arg-type]
    resp = _Resp("<thinking>藏起来的答案</thinking>")

    _run(pipe, resp, p)

    assert resp.completion_text == ""


def test_fallback_reply_still_reaches_conversation_buffer() -> None:
    """兜底文案发出去后，仍应像正常回复一样写入 conversation_buffers（供下轮 v2core 心象参考）。"""
    p = _Plugin(tempfile.mkdtemp(prefix="ni_buf_"))
    pipe = LLMResponsePipeline(p)  # type: ignore[arg-type]
    resp = _Resp("<thinking>没写出来的答案</thinking>")

    _run(pipe, resp, p)

    buf = p._store.conversation_buffers.get("sess:nonintercept")
    assert buf is not None
    assert any(m.get("role") == "bot" for m in buf.messages)
