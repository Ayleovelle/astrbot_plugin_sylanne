"""issue#26 根治守卫：分段接管不再吞掉非 Plain（TTS 语音/图片）chain。

根因（深挖 docs/ISSUE-26-...）：_maybe_takeover_segments 旧实现"只提 Plain 文本 +
无条件清空 chain"——当大饼 TTS 发 [Record语音] 时，提 Plain 得空 → 清空 chain（语音没了）
+ 空文本静默 return（Sylanne 也不发）→ QQ 收不到、无报错。

手术刀修复：claim 命中后，chain 含任何非 Plain 组件 → return False 不接管，让大饼原样发。
仅纯 Plain 文本 chain 才接管分段。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from astrbot.api.message_components import Plain, Record

from main import EmotionalStatePlugin


class _ClaimBridge:
    """claim 恒命中的 bridge stub（模拟该 origin 已登记待接管）。"""
    def claim_segment_takeover(self, origin: str) -> bool:
        return True


def _event(chain: list) -> SimpleNamespace:
    result = SimpleNamespace(chain=chain)
    return SimpleNamespace(
        unified_msg_origin="aiocqhttp:FriendMessage:123",
        get_result=lambda: result,
    )


def _call(self_stub, event) -> bool:
    # unbound async 方法 + self stub，不实例化重类
    return asyncio.run(EmotionalStatePlugin._maybe_takeover_segments(self_stub, event))


def test_record_chain_not_taken_over():
    """chain 含 Record(TTS语音) → 不接管(return False)，chain 不被清空（语音保留）。"""
    rec = Record(file="/tmp/x.wav")
    event = _event([rec])
    self_stub = SimpleNamespace(_proactive_bridge=_ClaimBridge())
    taken = _call(self_stub, event)
    assert taken is False, "含非Plain组件不该接管(否则吞语音)"
    # chain 未被清空，语音 Record 仍在
    assert event.get_result().chain == [rec], "chain 被清空了——语音会丢"


def test_mixed_chain_not_taken_over():
    """chain 含 Plain + Record 混合 → 仍不接管（避免吞掉其中的语音）。"""
    event = _event([Plain("早呀"), Record(file="/tmp/x.wav")])
    self_stub = SimpleNamespace(_proactive_bridge=_ClaimBridge())
    assert _call(self_stub, event) is False


def test_pure_plain_chain_still_taken_over():
    """纯 Plain 文本 chain → 仍接管（原行为不破，return True + chain 清空）。"""
    event = _event([Plain("早呀，今天想你了")])
    # 纯 Plain 路径会走到 realtime_plan/_dispatch_segmented_parts，给足 stub
    self_stub = SimpleNamespace(
        _proactive_bridge=_ClaimBridge(),
        config={},
        _llm_response_pipeline=SimpleNamespace(
            _dispatch_segmented_parts=lambda origin, parts: asyncio.sleep(0)
        ),
        _background_tasks=[],
    )
    taken = _call(self_stub, event)
    assert taken is True, "纯文本 chain 应正常接管"
    # 纯文本接管会清空 chain（交给 Sylanne 自己连发）
    assert event.get_result().chain == [], "接管后 chain 应被清空"


def test_no_claim_not_taken_over():
    """claim 未命中（非 Sylanne 登记的消息）→ 不接管，不碰 chain。"""
    class _NoBridge:
        def claim_segment_takeover(self, origin: str) -> bool:
            return False
    event = _event([Plain("普通消息")])
    self_stub = SimpleNamespace(_proactive_bridge=_NoBridge())
    assert _call(self_stub, event) is False
    assert event.get_result().chain == [Plain("普通消息")] or len(event.get_result().chain) == 1
