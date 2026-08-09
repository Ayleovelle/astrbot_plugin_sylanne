"""v2.5.0 入站消息级幂等闸（issue43-repeat v2 修复）回归测试。

覆盖 main.py 新增电路：
  - `EmotionalStatePlugin._inbound_dup_gate`：以 (unified_msg_origin,
    message_obj.message_id) 为键的 check-then-set 去重判定。
  - `_on_scope_ready_llm_request` 请求尾段接线：命中重复 ->
    `event.stop_event()` + 早退，
    不委托给 `_llm_request_pipeline._on_llm_request_inner`（即不再触发
    build/run_agent/_save_to_history，第二 pass 净写 0 条）。

不改动：state_persistence.py:2499 的 user 幂等豁免（原语层永不去重，本闸是
入站级防线，工作在原语之前）。

对照 scratchpad/dup_msgid_gate_repro.py 的真码复现（该脚本证明了修前会烤出
[user:X, user:X]、修后闸拦下第二 pass DB 只剩 1 份）——本文件把同一条电路
钉成可重复运行的 pytest 回归。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from main import EmotionalStatePlugin
from sylanne_alpha.infra import BoundedDict
from sylanne_alpha.state_persistence import StatePersistence

UMO = "aiocqhttp:FriendMessage:1432192649"
X = "连说两遍是指哪一句啊？"


class _MsgObj:
    def __init__(self, message_id):
        self.message_id = message_id


class _Event:
    """真事件桩：只提供闸 + scope-ready 请求尾段需要的最小面。"""

    def __init__(self, umo=UMO, message_id=None):
        self.unified_msg_origin = umo
        self.message_obj = _MsgObj(message_id)
        self._stopped = False

    def stop_event(self):
        self._stopped = True

    def is_stopped(self):
        return self._stopped


class _EventNoMessageObj:
    """message_obj 属性压根不存在（旧桩/异常事件形状）——闸必须 fail-safe 放行。"""

    def __init__(self, umo=UMO):
        self.unified_msg_origin = umo
        self._stopped = False

    def stop_event(self):
        self._stopped = True


def _gate_only_plugin():
    class _GatePlugin:
        _inbound_dup_gate = EmotionalStatePlugin._inbound_dup_gate

        def __init__(self):
            self._inbound_seen = BoundedDict(maxsize=1024)

    return _GatePlugin()


def _req_pipeline_plugin():
    """挂真实 `_inbound_dup_gate` + 真实 scope-ready 请求尾段，
    `_llm_request_pipeline._on_llm_request_inner` 用 AsyncMock 隔离
    （显式假定 frozen-scope 前置契约已满足，只钉"闸 -> 是否委托下游"
    这条门控，不伪造 scope，也不掺真实 pipeline 逻辑）。"""

    class _Plugin:
        _inbound_dup_gate = EmotionalStatePlugin._inbound_dup_gate
        _on_scope_ready_llm_request = (
            EmotionalStatePlugin._on_scope_ready_llm_request
        )

        def __init__(self):
            self._inbound_seen = BoundedDict(maxsize=1024)
            self._llm_request_pipeline = SimpleNamespace(
                _on_llm_request_inner=AsyncMock(return_value=None)
            )

    return _Plugin()


# ---------------------------------------------------------------------------
# 组 1：闸函数本身（_inbound_dup_gate）的判定真值表
# ---------------------------------------------------------------------------


def test_same_umo_and_mid_second_call_is_duplicate() -> None:
    """同 (umo, mid) 第二次调用 -> True（判为重复）；第一次 -> False。"""
    p = _gate_only_plugin()
    e1 = _Event(message_id="111111")
    e2 = _Event(message_id="111111")

    assert p._inbound_dup_gate(e1) is False
    assert p._inbound_dup_gate(e2) is True


def test_different_mid_same_umo_never_flagged_duplicate() -> None:
    """同一 umo 下两条不同 message_id 的真实消息都不该被判重（不误杀）。"""
    p = _gate_only_plugin()
    e1 = _Event(message_id="111111")
    e2 = _Event(message_id="222222")

    assert p._inbound_dup_gate(e1) is False
    assert p._inbound_dup_gate(e2) is False


def test_none_message_id_always_exempt() -> None:
    """message_id=None（如 webchat 前端未带 id）——豁免，不登记不拦，
    即便同一 umo 反复出现也永远放行（宁漏 dedup 不误杀）。"""
    p = _gate_only_plugin()
    e1 = _Event(message_id=None)
    e2 = _Event(message_id=None)
    e3 = _Event(message_id=None)

    assert p._inbound_dup_gate(e1) is False
    assert p._inbound_dup_gate(e2) is False
    assert p._inbound_dup_gate(e3) is False


def test_empty_string_message_id_exempt() -> None:
    """message_id="" / 纯空白——同样豁免（`mid.strip()` 判空）。"""
    p = _gate_only_plugin()
    e1 = _Event(message_id="")
    e2 = _Event(message_id="   ")

    assert p._inbound_dup_gate(e1) is False
    assert p._inbound_dup_gate(e2) is False


def test_non_str_message_id_exempt() -> None:
    """message_id 非字符串（如某些桩给 int）——豁免，不因类型异常而报错。"""
    p = _gate_only_plugin()
    e1 = _Event(message_id=123456)
    e2 = _Event(message_id=123456)

    assert p._inbound_dup_gate(e1) is False
    assert p._inbound_dup_gate(e2) is False


def test_uuid4_style_ids_each_unique_never_collide() -> None:
    """notice/request 事件形态的 uuid4 hex——每次投递随机不同，天然不会撞键
    （即便闸本身不做类型甄别，唯一性已经保证它们不会被误判重复）。"""
    p = _gate_only_plugin()
    import uuid

    e1 = _Event(message_id=uuid.uuid4().hex)
    e2 = _Event(message_id=uuid.uuid4().hex)

    assert p._inbound_dup_gate(e1) is False
    assert p._inbound_dup_gate(e2) is False


def test_missing_message_obj_attribute_exempt_no_crash() -> None:
    """event 压根没有 message_obj 属性（异常/旧桩形状）——闸 fail-safe 放行，
    不抛异常。"""
    p = _gate_only_plugin()
    e = _EventNoMessageObj()

    assert p._inbound_dup_gate(e) is False
    assert p._inbound_dup_gate(e) is False  # 反复调用同样安全


def test_empty_umo_exempt() -> None:
    """unified_msg_origin 为空——同样豁免（键的另一半缺失，无法安全去重）。"""
    p = _gate_only_plugin()
    e1 = _Event(umo="", message_id="111111")
    e2 = _Event(umo="", message_id="111111")

    assert p._inbound_dup_gate(e1) is False
    assert p._inbound_dup_gate(e2) is False


def test_different_umo_same_mid_not_flagged_duplicate() -> None:
    """不同 umo（不同会话/不同人）恰好撞了相同 message_id——键包含 umo，不误杀。"""
    p = _gate_only_plugin()
    e1 = _Event(umo="aiocqhttp:FriendMessage:AAA", message_id="999")
    e2 = _Event(umo="aiocqhttp:FriendMessage:BBB", message_id="999")

    assert p._inbound_dup_gate(e1) is False
    assert p._inbound_dup_gate(e2) is False


# ---------------------------------------------------------------------------
# 组 2：scope-ready 请求尾段 —— 命中即 stop_event + 不委托下游
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_pass_stops_event_and_skips_pipeline_delegate() -> None:
    """同一 (umo, mid) 第二个 pass：`event.stop_event()` 被调用，且
    `_llm_request_pipeline._on_llm_request_inner` 不再被委托调用
    （框架侧 build/run_agent/_save_to_history 因此不会触发）。"""
    p = _req_pipeline_plugin()
    e1 = _Event(message_id="111111")
    e2 = _Event(message_id="111111")

    await p._on_scope_ready_llm_request(e1, request=SimpleNamespace())
    await p._on_scope_ready_llm_request(e2, request=SimpleNamespace())

    p._llm_request_pipeline._on_llm_request_inner.assert_awaited_once()
    assert e1._stopped is False, "首个 pass 不应被 stop"
    assert e2._stopped is True, "第二 pass 命中闸必须被 stop_event"


@pytest.mark.asyncio
async def test_two_distinct_real_messages_both_delegate_no_stop() -> None:
    """两条不同 message_id 的真实消息都正常放行，都委托给下游 pipeline，
    都不被 stop——正常世界(每条消息 id 唯一)下闸恒等价于现状。"""
    p = _req_pipeline_plugin()
    e1 = _Event(message_id="111111")
    e2 = _Event(message_id="222222")

    await p._on_scope_ready_llm_request(e1, request=SimpleNamespace())
    await p._on_scope_ready_llm_request(e2, request=SimpleNamespace())

    assert p._llm_request_pipeline._on_llm_request_inner.await_count == 2
    assert e1._stopped is False
    assert e2._stopped is False


@pytest.mark.asyncio
async def test_silent_round_message_id_still_registered_before_early_return() -> None:
    """SILENT 轮场景：闸位于 `_on_llm_request_inner` 顶端，早于任何下游早退
    （should_express 静默 return 在 pipeline 内部，本测试用 AsyncMock 模拟
    "pipeline 内部静默、无可观察副作用"这一形状）——即便下游什么都没做，
    message_id 依然会先被登记进 `_inbound_seen`；同一条消息的第二 pass
    因此照样会被拦下，不会因为第一 pass 是 SILENT 就漏判。"""
    p = _req_pipeline_plugin()
    mid = "333333"
    e1 = _Event(message_id=mid)  # 模拟 SILENT 轮：下游 mock 直接返回 None
    e2 = _Event(message_id=mid)  # 平台重投同一条消息

    await p._on_scope_ready_llm_request(e1, request=SimpleNamespace())
    key = UMO + "\x00" + mid
    assert key in p._inbound_seen, "SILENT 轮的 message_id 必须已被登记"

    await p._on_scope_ready_llm_request(e2, request=SimpleNamespace())

    p._llm_request_pipeline._on_llm_request_inner.assert_awaited_once()
    assert e2._stopped is True


@pytest.mark.asyncio
async def test_none_message_id_both_passes_delegate_no_stop() -> None:
    """webchat 等 message_id 恒 None 的平台——两次调用都正常委托，零行为变化。"""
    p = _req_pipeline_plugin()
    e1 = _Event(message_id=None)
    e2 = _Event(message_id=None)

    await p._on_scope_ready_llm_request(e1, request=SimpleNamespace())
    await p._on_scope_ready_llm_request(e2, request=SimpleNamespace())

    assert p._llm_request_pipeline._on_llm_request_inner.await_count == 2
    assert e1._stopped is False
    assert e2._stopped is False


@pytest.mark.asyncio
async def test_gate_survives_event_missing_stop_event_method() -> None:
    """event 没有 `stop_event` 方法（极端旧桩）——命中重复时不应抛异常，
    只是无法真正 stop（getattr+callable 判空防御）。"""

    class _NoStopEvent:
        def __init__(self, umo=UMO, message_id=None):
            self.unified_msg_origin = umo
            self.message_obj = _MsgObj(message_id)

    p = _req_pipeline_plugin()
    e1 = _NoStopEvent(message_id="444444")
    e2 = _NoStopEvent(message_id="444444")

    await p._on_scope_ready_llm_request(e1, request=SimpleNamespace())
    await p._on_scope_ready_llm_request(
        e2, request=SimpleNamespace()
    )  # 不应抛异常

    p._llm_request_pipeline._on_llm_request_inner.assert_awaited_once()


# ---------------------------------------------------------------------------
# 组 3：端到端 —— 真实 StatePersistence 原语，证明重复 pass 对 conv_mgr 零新增写
# ---------------------------------------------------------------------------


class _FakeConvMgr:
    """依据 conversation_mgr.py 语义：整表覆盖、无 CAS（同 dup 系列脚本忠实建模）。"""

    def __init__(self) -> None:
        self._content: dict[str, list[dict]] = {}
        self._curr: dict[str, str] = {}

    async def get_curr_conversation_id(self, umo: str):
        return self._curr.get(umo)

    async def new_conversation(self, umo: str, *a, **k) -> str:
        cid = f"cid-{umo}"
        self._curr[umo] = cid
        self._content[cid] = []
        return cid

    async def get_conversation(self, umo: str, cid: str):
        content = self._content.get(cid, [])
        return SimpleNamespace(history=json.dumps(content or [], ensure_ascii=False))

    async def update_conversation(self, umo: str, cid: str, history=None, **k) -> None:
        self._content[cid] = list(history or [])


def _role_seq(entries: list[dict]) -> list[str]:
    return [str(e.get("role", "?")) for e in entries]


@pytest.mark.asyncio
async def test_duplicate_pass_yields_zero_new_conv_mgr_user_writes() -> None:
    """核心回归（对应 repro 脚本 post_fix_with_gate）：pass1 通过真实
    `StatePersistence._do_sync_to_conv_mgr` 写下悬挂 user:X；pass2 是同一条
    消息的重投（同 umo+mid），过闸后必须在真正调用任何 conv_mgr 写入
    （悬挂 backfill 或框架整表覆盖）之前就被拦下 —— 最终 conv_mgr 里只有 1
    份 user，不会被烤成 [user:X, user:X]。"""

    class _Probe(StatePersistence):
        def __init__(self):
            pass

    sp = _Probe()
    cm = _FakeConvMgr()
    cid = await cm.new_conversation(UMO)
    gate_plugin = _gate_only_plugin()

    # pass1：先过闸（首次，放行），随后走真实 SILENT backfill 写入
    e1 = _Event(message_id="555555")
    assert gate_plugin._inbound_dup_gate(e1) is False
    await sp._do_sync_to_conv_mgr(cm, UMO, "user", X)
    assert _role_seq(cm._content[cid]) == ["user"]

    # pass2：同一条消息重投，过闸即命中重复 -> 不应再调用任何写入原语
    e2 = _Event(message_id="555555")
    is_dup = gate_plugin._inbound_dup_gate(e2)
    assert is_dup is True
    if not is_dup:  # pragma: no cover - 仅为显式对照真实调用路径的分支形状
        await sp._do_sync_to_conv_mgr(cm, UMO, "user", X)

    final = cm._content[cid]
    assert _role_seq(final) == ["user"], (
        f"闸未能拦下重复 pass，conv_mgr 被多写了一次：{_role_seq(final)}"
    )
    assert final[0]["content"] == X or final[0].get("content") == [
        {"type": "text", "text": X}
    ]
