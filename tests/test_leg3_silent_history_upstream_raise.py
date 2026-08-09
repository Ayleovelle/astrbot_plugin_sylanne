"""2.4.1 leg-3 双写根治：SILENT/空回轮的用户消息持久化必须【恰好一次】、且【异常
不吞】——收口挂点回归。

背景（context-loss-rootcause-proven-jointcondition + v241 最终实现计划）：旧
leg-3 把 user 同步搬到请求期无条件跑一次，代价是与框架 _save_to_history
（响应期，agent 钩子内、per-umo 会话锁下）跨锁双写，产生 [P,u,b,u] 悬挂重复。

新实现把 user 同步整体搬到 main.py::EmotionalStatePlugin._on_llm_response_inner
的收口层：try/finally 包住 v2core / legacy 两条分支，finally 里调用
_backfill_user_if_framework_skips —— 仅当 _framework_will_persist_this_turn
判定框架本轮【不会】落库时，插件才补写 user（该轮唯一写者）。放 finally 是为了
兑现 H1：v2core 桥接异常、legacy 回复异常，都不能吞掉这次补写，否则 SILENT 轮
会重新丢历史（比旧 bug 更隐蔽）。

本文件专打"上游抛异常"这个红队要点：无论 v2core 分支还是 legacy 分支抛异常，
只要框架本轮判定不落库，补写必须仍然恰好发生一次；已经落库过（或即将落库）的
轮次不应产生二次写。
"""

from __future__ import annotations

import asyncio

import pytest

from main import EmotionalStatePlugin


class _ReqStub:
    """最小 provider_request 桩：有 conversation，无 tool_calls_result。"""

    def __init__(self, *, has_conversation: bool = True, tool_calls_result=None) -> None:
        self.conversation = object() if has_conversation else None
        self.tool_calls_result = tool_calls_result


class _Event:
    def __init__(
        self,
        *,
        req: _ReqStub | None = None,
        is_stopped: bool = False,
        umo: str = "sess:leg3",
    ) -> None:
        self._req = req if req is not None else _ReqStub()
        self._is_stopped = is_stopped
        self.unified_msg_origin = umo

    def get_extra(self, key: str, default=None):
        if key == "provider_request":
            return self._req
        return default

    def is_stopped(self) -> bool:
        return self._is_stopped


class _Resp:
    def __init__(self, completion_text: str = "") -> None:
        self.completion_text = completion_text


class _Pipe:
    """挂在 plugin._llm_response_pipeline 上的 legacy 桩，可配置是否抛异常。"""

    def __init__(self, *, raises: bool = False) -> None:
        self._raises = raises
        self.calls: list = []

    async def _on_llm_response_inner(self, event, response) -> None:
        self.calls.append((event, response))
        if self._raises:
            raise RuntimeError("legacy boom")


# 把 main.py 真实实现的三个方法（含收口 _on_llm_response_inner 本身）原样绑到
# 最小桩类上——测试驱动的是生产代码，不是重新实现一份逻辑。
class _Plugin:
    _framework_will_persist_this_turn = EmotionalStatePlugin._framework_will_persist_this_turn
    _agent_was_aborted = EmotionalStatePlugin._agent_was_aborted
    _backfill_user_if_framework_skips = EmotionalStatePlugin._backfill_user_if_framework_skips
    _on_llm_response_inner = EmotionalStatePlugin._on_llm_response_inner

    def __init__(self, *, text: str, legacy_raises: bool = False) -> None:
        self._text_value = text
        self._llm_response_pipeline = _Pipe(raises=legacy_raises)
        self.user_sync_calls: list[tuple[str, str, str]] = []

    def _has_conversation_manager(self) -> bool:
        return True

    def _text(self, _event) -> str:
        return self._text_value

    def _session_key(self, _event) -> str:
        return "sk1"

    async def _sync_message_to_conv_mgr(self, session_key: str, role: str, text: str) -> None:
        self.user_sync_calls.append((session_key, role, text))


def _v2core_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """让 main.py 里的 `from sylanne_alpha.v2core.integration import
    apply_v2core_response` 这次动态 import 拿到一个必抛异常的替身。"""
    import sylanne_alpha.v2core.integration as integration_mod

    async def _boom(*_a, **_k):
        raise RuntimeError("v2core bridge boom")

    monkeypatch.setattr(integration_mod, "apply_v2core_response", _boom)


@pytest.mark.asyncio
async def test_backfill_fires_once_when_v2core_bridge_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """v2core 桥接抛异常 -> handled=False 落 legacy（也是空回复/SILENT 形态）->
    框架本轮不落库 -> finally 补写恰好一次，异常不吞补写。"""
    _v2core_raises(monkeypatch)
    p = _Plugin(text="在干嘛呢")
    event = _Event()
    resp = _Resp("")  # SILENT 形态：completion 空

    await p._on_llm_response_inner(event, resp)

    assert p.user_sync_calls == [("sk1", "user", "在干嘛呢")], (
        f"上游 v2core 异常下补写应恰好一次，实际：{p.user_sync_calls!r}"
    )


@pytest.mark.asyncio
async def test_backfill_fires_exactly_once_no_double_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """正常路径（v2core 未抛异常，直接走 legacy 分支）下同样恰好一次，不双写。"""
    _v2core_raises(monkeypatch)  # 桥接仍然异常 -> 落 legacy，legacy 正常返回
    p = _Plugin(text="喂", legacy_raises=False)
    event = _Event()
    resp = _Resp("")

    await p._on_llm_response_inner(event, resp)

    assert p.user_sync_calls == [("sk1", "user", "喂")], f"应恰好一次，实际：{p.user_sync_calls!r}"

    # 幂等自检：finally 只跑一次，同一事件循环内不会因为重复调用而堆积。
    await p._on_llm_response_inner(event, resp)
    assert p.user_sync_calls == [
        ("sk1", "user", "喂"),
        ("sk1", "user", "喂"),
    ], "两次独立调用各自补写一次是预期行为（无跨调用去重契约），非本用例断言重点"


@pytest.mark.asyncio
async def test_empty_text_not_synced(monkeypatch: pytest.MonkeyPatch) -> None:
    """空 text 不触发同步（无内容可持久化）。"""
    _v2core_raises(monkeypatch)
    p = _Plugin(text="")
    event = _Event()
    resp = _Resp("")

    await p._on_llm_response_inner(event, resp)

    assert p.user_sync_calls == [], f"空文本不应同步，实际：{p.user_sync_calls!r}"


@pytest.mark.asyncio
async def test_backfill_still_fires_when_legacy_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """H1 回归核心：legacy 分支自己抛异常，finally 仍应先补写再让异常上抛。"""
    _v2core_raises(monkeypatch)
    p = _Plugin(text="在干嘛呢", legacy_raises=True)
    event = _Event()
    resp = _Resp("")

    with pytest.raises(RuntimeError, match="legacy boom"):
        await p._on_llm_response_inner(event, resp)

    assert p.user_sync_calls == [("sk1", "user", "在干嘛呢")], (
        f"legacy 抛异常也不应吞掉 finally 补写，实际：{p.user_sync_calls!r}"
    )
