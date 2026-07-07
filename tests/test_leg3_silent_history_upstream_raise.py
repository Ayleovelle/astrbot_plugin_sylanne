"""上下文丢失 leg-3：SILENT/空回轮的用户消息持久化必须先于任何可能抛异常的代码。

背景（见 context-loss-rootcause-proven-jointcondition + test_context_integrity_silent_history）：
用户轮经 _sync_message_to_conv_mgr 落进 AstrBot ConversationManager，是"用户说过这句话"
的唯一权威前置写入。既有 SILENT-历史测试早已假设这次同步是"无条件跑过的"，但真代码里
它曾埋在 _background_observe_request 的大 try 深处——上游任一异常（ensure_restored /
host.on_request / compress_check…）都会跳到只重试 observe_request 的 except、静默漏掉本次
同步；若该轮又被判 SILENT，AstrBot 自身 _save_to_history 也因 completion 为空提前 return，
用户消息永久从会话历史消失（跳话题联合条件里"历史丢失"那条腿）。

leg-3 把这次同步上移到 try 之前，兑现该契约。本测试专打既有 Step-1-直调测试抓不到的洞：
上游抛异常时，同步仍恰好被调度一次；且不双写。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline


def _pipe_with_spy(*, host_raises: bool):
    calls: list[tuple] = []

    class _P:
        def _has_conversation_manager(self) -> bool:
            return True

        def _sync_message_to_conv_mgr(self, session_key, role, text):
            # 在【创建协程时】同步记录一次调用（即"调度点"）。返回一个真协程供
            # safe_ensure_future 调度，避免 "coroutine never awaited" 噪声。
            calls.append((session_key, role, text))

            async def _noop():
                return None

            return _noop()

        def _host(self, sk):
            if host_raises:
                raise RuntimeError("upstream boom before the old sync point")
            return SimpleNamespace()

        async def observe_request(self, *a, **k):
            # except 兜底会调它——no-op，避免测试里真跑评估
            return None

    pipe = LLMRequestPipeline.__new__(LLMRequestPipeline)
    pipe._p = _P()
    return pipe, calls


def test_user_sync_scheduled_even_when_upstream_raises():
    """上游（host.on_request 之类）抛异常，用户轮同步仍恰好被调度一次。

    这是回归旧洞的核心：老实现里同步在 try 深处，此异常会让它被跳过。
    """
    pipe, calls = _pipe_with_spy(host_raises=True)
    asyncio.run(pipe._background_observe_request("sk1", "在干嘛呢"))
    assert calls == [("sk1", "user", "在干嘛呢")], (
        f"上游异常下用户同步应恰好一次，实际：{calls!r}"
    )


def test_user_sync_scheduled_exactly_once_no_double_write():
    """正常（无上游异常）路径下也恰好一次——移动非新增，不双写。

    role=='user' 侧本就不参与 state_persistence 幂等去重，双写会直接污染历史，
    故"恰好一次"是硬约束。
    """
    pipe, calls = _pipe_with_spy(host_raises=False)
    # host 不抛，但最小 stub 会在 try 内更深处自然抛 → 落 except（observe_request no-op）。
    # 无论走到哪，try 之前的同步都应恰好触发一次，且旧调用点已删除故不会二次触发。
    asyncio.run(pipe._background_observe_request("sk2", "喂"))
    assert calls == [("sk2", "user", "喂")], f"应恰好一次，实际：{calls!r}"


def test_empty_text_not_synced():
    """空 text 不触发同步（无内容可持久化）。"""
    pipe, calls = _pipe_with_spy(host_raises=True)
    asyncio.run(pipe._background_observe_request("sk3", ""))
    assert calls == [], f"空文本不应同步，实际：{calls!r}"
