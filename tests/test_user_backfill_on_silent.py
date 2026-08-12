"""2.4.1 leg-3 双写根治——收口层补写（main.py::_backfill_user_if_framework_skips）
的判据与行为矩阵。

对应 v241 最终实现计划第四节"新增测试"①-⑧。判据 _framework_will_persist_this_turn
镜像 AstrBot 4.25.1 私有 _save_to_history 落库条件：
    F = C ∧ (¬S∨A) ∧ (E∨T∨A)
    ¬F = ¬C ∨ (S∧¬A) ∨ (¬E∧¬T∧¬A)
C=有 conversation，S=is_stopped，A=was_aborted，E=completion 非空，T=tool_calls_result 非空。
本文件驱动 plugin._backfill_user_if_framework_skips 或收口 _on_llm_response_inner，
逐条钉死 ¬F 的三腿分支 + H1（异常不吞补写）+ H2（stopped-未abort 回归点）。
"""

from __future__ import annotations

import json
import tempfile
from types import SimpleNamespace

import pytest

from main import EmotionalStatePlugin


# ---------------------------------------------------------------------------
# 最小桩：provider_request / event / response
# ---------------------------------------------------------------------------


class _ReqStub:
    def __init__(self, *, has_conversation: bool = True, tool_calls_result=None) -> None:
        self.conversation = object() if has_conversation else None
        self.tool_calls_result = tool_calls_result


class _Event:
    def __init__(
        self,
        *,
        req: _ReqStub | None = None,
        is_stopped: bool = False,
        umo: str = "sess:backfill",
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
    def __init__(self, completion_text: str = "", role: str = "assistant") -> None:
        self.completion_text = completion_text
        self.role = role


class _Pipe:
    def __init__(self, *, raises: bool = False) -> None:
        self._raises = raises
        self.calls: list = []

    async def _on_llm_response_inner(self, event, response) -> None:
        self.calls.append((event, response))
        if self._raises:
            raise RuntimeError("legacy boom")


class _Plugin:
    """最小插件桩：绑定 main.py 真实的判据 + 补写方法，只喂最小依赖。"""

    _framework_will_persist_this_turn = EmotionalStatePlugin._framework_will_persist_this_turn
    _agent_was_aborted = EmotionalStatePlugin._agent_was_aborted
    _backfill_user_if_framework_skips = EmotionalStatePlugin._backfill_user_if_framework_skips
    _on_llm_response_with_bound_runtime = (
        EmotionalStatePlugin._on_llm_response_with_bound_runtime
    )

    def __init__(
        self,
        *,
        text: str = "在干嘛呢",
        has_conv_mgr: bool = True,
        aborted: bool = False,
        legacy_raises: bool = False,
    ) -> None:
        self._text_value = text
        self._has_conv_mgr = has_conv_mgr
        self._aborted = aborted
        self._llm_response_pipeline = _Pipe(raises=legacy_raises)
        self.user_sync_calls: list[tuple[str, str, str]] = []

    def _has_conversation_manager(self) -> bool:
        return self._has_conv_mgr

    def _text(self, _event) -> str:
        return self._text_value

    def _session_key(self, _event) -> str:
        return "sk1"

    async def _sync_message_to_conv_mgr(self, session_key: str, role: str, text: str) -> None:
        self.user_sync_calls.append((session_key, role, text))


class _AbortablePlugin(_Plugin):
    """覆盖 _agent_was_aborted，绕开 follow_up._ACTIVE_AGENT_RUNNERS 真实查表——
    场景④要精确控制 abort 权威值，不依赖框架内部注册表状态。"""

    def _agent_was_aborted(self, _event) -> bool:  # type: ignore[override]
        return self._aborted


# ---------------------------------------------------------------------------
# ①-④：_framework_will_persist_this_turn 的三腿 ¬F + H2 回归点
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_1_silent_backfills_exactly_once() -> None:
    """① SILENT（completion="" + 无 tool_res + 未 stop + 有 conversation + 未 abort）
    -> 恰好 1 条 user（¬E∧¬T∧¬A 腿）。"""
    p = _AbortablePlugin(text="在干嘛呢", aborted=False)
    event = _Event(is_stopped=False, req=_ReqStub(has_conversation=True))
    resp = _Resp("")

    await p._backfill_user_if_framework_skips(event, resp)

    assert p.user_sync_calls == [("sk1", "user", "在干嘛呢")]


@pytest.mark.asyncio
async def test_2_speak_zero_user_writes() -> None:
    """② SPEAK（completion 非空）-> 零 user 写（框架是写者）。"""
    p = _AbortablePlugin(text="在干嘛呢", aborted=False)
    event = _Event(is_stopped=False, req=_ReqStub(has_conversation=True))
    resp = _Resp("在写代码呢")

    await p._backfill_user_if_framework_skips(event, resp)

    assert p.user_sync_calls == []


@pytest.mark.asyncio
async def test_3_empty_completion_with_tool_calls_result_zero_user_writes() -> None:
    """③ 空 completion + tool_calls_result 非空（tool 循环轮）-> 零 user 写
    （镜像 internal.py:465，防双写：框架仍会 save，因为 T 为真）。"""
    p = _AbortablePlugin(text="在干嘛呢", aborted=False)
    event = _Event(
        is_stopped=False,
        req=_ReqStub(has_conversation=True, tool_calls_result=[{"id": "call_1"}]),
    )
    resp = _Resp("")

    await p._backfill_user_if_framework_skips(event, resp)

    assert p.user_sync_calls == []


@pytest.mark.asyncio
async def test_4a_stopped_and_aborted_zero_user_writes() -> None:
    """④a is_stopped=True ∧ aborted=True -> 零 user 写
    （框架 internal.py:395 放行 + :463 因 abort save，框架是写者）。"""
    p = _AbortablePlugin(text="在干嘛呢", aborted=True)
    event = _Event(is_stopped=True, req=_ReqStub(has_conversation=True))
    resp = _Resp("")  # abort 时 completion 常为空，仍应因 aborted=True 判框架会存

    await p._backfill_user_if_framework_skips(event, resp)

    assert p.user_sync_calls == []


@pytest.mark.asyncio
async def test_4b_stopped_not_aborted_backfills_exactly_once() -> None:
    """④b is_stopped=True ∧ aborted=False -> 恰好 1 条 user 写
    （框架 internal.py:395 该轮根本不调 save，H2/甲-1b 修复的回归核心，绝不能丢）。"""
    p = _AbortablePlugin(text="在干嘛呢", aborted=False)
    event = _Event(is_stopped=True, req=_ReqStub(has_conversation=True))
    resp = _Resp("这段草稿本来会被框架无视")

    await p._backfill_user_if_framework_skips(event, resp)

    assert p.user_sync_calls == [("sk1", "user", "在干嘛呢")], (
        "stopped-未abort 轮框架不落库，补写必须发生，否则历史丢失（H2 回归点）"
    )


@pytest.mark.asyncio
async def test_no_conversation_backfills_exactly_once() -> None:
    """¬C 腿：无 conversation -> 框架 internal.py:447 直接 return，插件必须补写。"""
    p = _AbortablePlugin(text="在干嘛呢", aborted=False)
    event = _Event(is_stopped=False, req=_ReqStub(has_conversation=False))
    resp = _Resp("draft")

    await p._backfill_user_if_framework_skips(event, resp)

    assert p.user_sync_calls == [("sk1", "user", "在干嘛呢")]


@pytest.mark.asyncio
async def test_no_conversation_manager_short_circuits_before_judging() -> None:
    """插件自身没接 conv_mgr 时，补写直接短路——不产生任何写、不误判。"""
    p = _AbortablePlugin(text="在干嘛呢", aborted=False, has_conv_mgr=False)
    event = _Event(is_stopped=False, req=_ReqStub(has_conversation=True))
    resp = _Resp("")

    await p._backfill_user_if_framework_skips(event, resp)

    assert p.user_sync_calls == []


# ---------------------------------------------------------------------------
# 红线闸 finding #1 回归哨：response.role != "assistant"（LLM/provider 错误轮）
# -> 框架侧 _save_to_history 实际因 internal.py:450(final_resp=None) 或
# :453-455(role != "assistant" 且未 abort) 而不落库，插件必须补写，否则该轮
# user 彻底无人写（无条件 leg-3 时代不会丢，是真回归）。
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_error_role_response_with_text_backfills_exactly_once() -> None:
    """role='err' 但 completion_text 非空（provider 报错文案）-> 仍必须补写。
    旧实现只看 completion_text 非空就误判"框架会存"，在这类 role != assistant
    的响应上会漏补——这是本轮红线闸 finding #1 的核心断言。"""
    p = _AbortablePlugin(text="中午吃什么", aborted=False)
    event = _Event(is_stopped=False, req=_ReqStub(has_conversation=True))
    resp = _Resp("Error occurred during AI execution.\nError Type: Timeout", role="err")

    await p._backfill_user_if_framework_skips(event, resp)

    assert p.user_sync_calls == [("sk1", "user", "中午吃什么")], (
        f"role='err' 的错误响应也应触发补写，实际：{p.user_sync_calls!r}"
    )


@pytest.mark.asyncio
async def test_error_role_response_but_aborted_zero_user_writes() -> None:
    """role != assistant 但 aborted=True -> 框架仍会存（internal.py:453-455 的
    user_aborted 分支会把非 assistant 响应强转成 assistant），插件不应重复补写。"""
    p = _AbortablePlugin(text="中午吃什么", aborted=True)
    event = _Event(is_stopped=False, req=_ReqStub(has_conversation=True))
    resp = _Resp("err text", role="err")

    await p._backfill_user_if_framework_skips(event, resp)

    assert p.user_sync_calls == []


@pytest.mark.asyncio
async def test_assistant_role_default_unaffected_by_role_check() -> None:
    """role 缺省/显式为 assistant 时行为不变（新判据不误伤既有 SPEAK 分支）。"""
    p = _AbortablePlugin(text="中午吃什么", aborted=False)
    event = _Event(is_stopped=False, req=_ReqStub(has_conversation=True))
    resp = _Resp("正常回复", role="assistant")

    await p._backfill_user_if_framework_skips(event, resp)

    assert p.user_sync_calls == []


# ---------------------------------------------------------------------------
# ⑤：v2core 回落既有管线时，空 completion 静默走收口，仍恰好补写一次
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_5_v2core_fallthrough_legacy_silent_still_backfills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v2core 返回 handled=False 后，legacy empty_completion 静默仍补写一条 user。"""
    import sylanne_alpha.v2core.integration as integration_mod

    async def _v2core_falls_through(*_a, **_k):
        # SPEAK/FALLBACK/异常都可能 handled=False，随后进入既有管线。
        return False

    monkeypatch.setattr(integration_mod, "apply_v2core_response", _v2core_falls_through)

    p = _AbortablePlugin(text="在干嘛呢", aborted=False, legacy_raises=False)
    event = _Event(is_stopped=False, req=_ReqStub(has_conversation=True))
    resp = _Resp("")  # legacy 空 completion，静默不发（SILENT 等价形态）

    await p._on_llm_response_with_bound_runtime(event, resp)

    assert p.user_sync_calls == [("sk1", "user", "在干嘛呢")], (
        f"v2core 回落后 legacy SILENT 也应经收口恰好补写一次，实际：{p.user_sync_calls!r}"
    )


# ---------------------------------------------------------------------------
# ⑥：连发相同文本 + 中间 SILENT -> never-drop（靠 state_persistence.py:2489 user 豁免）
# ---------------------------------------------------------------------------


class _FakeConversationManager:
    """贴近真实框架关键窄面的最小桩（同 test_context_integrity_silent_history.py
    的 FakeConversationManager 精简版）：history 以 JSON 字符串往返。"""

    def __init__(self) -> None:
        self._content: dict[str, list] = {}
        self._curr_ids: dict[str, str] = {}
        self._next_id = 1

    async def get_curr_conversation_id(self, uid: str) -> str | None:
        return self._curr_ids.get(uid)

    async def new_conversation(self, uid: str) -> str:
        cid = f"conv_{self._next_id}"
        self._next_id += 1
        self._curr_ids[uid] = cid
        self._content[cid] = []
        return cid

    async def get_conversation(self, uid: str, cid: str):
        if cid not in self._content:
            return None
        history_json = json.dumps(self._content[cid], ensure_ascii=False)
        return SimpleNamespace(history=history_json)

    async def update_conversation(self, uid: str, cid: str, history=None, title=None):
        if cid not in self._content:
            return
        if history is not None:
            json.dumps(history, ensure_ascii=False)
            self._content[cid] = history


class _RealPersistPlugin:
    """走真实 StatePersistence.sync_message_to_conv_mgr 委托（而非记录调用的
    call-spy），才能验证 state_persistence.py:2489 的 user 永不去重豁免。"""

    _framework_will_persist_this_turn = EmotionalStatePlugin._framework_will_persist_this_turn
    _agent_was_aborted = EmotionalStatePlugin._agent_was_aborted
    _backfill_user_if_framework_skips = EmotionalStatePlugin._backfill_user_if_framework_skips

    def __init__(self, *, root: str, conv_mgr: _FakeConversationManager, text: str) -> None:
        self._root = root
        self._conv_mgr = conv_mgr
        self._text_value = text

        from sylanne_alpha.session_state_store import SessionStateStore
        from sylanne_alpha.state_persistence import StatePersistence

        self._store = SessionStateStore()
        self._state_persistence = StatePersistence(self)

    def _has_conversation_manager(self) -> bool:
        return self._conv_mgr is not None

    def _text(self, _event) -> str:
        return self._text_value

    def _session_key(self, _event) -> str:
        return "u1"

    def _agent_was_aborted(self, _event) -> bool:
        return False

    async def _sync_message_to_conv_mgr(self, session_key: str, role: str, text: str) -> None:
        await self._state_persistence.sync_message_to_conv_mgr(session_key, role, text)


@pytest.mark.asyncio
async def test_6_consecutive_identical_user_messages_never_dropped() -> None:
    """⑥ 连发相同 "在吗" + 第二条那轮 SILENT -> history len==2（never-drop，
    靠 :2489 对 user 侧的豁免；两轮都走真实收口补写路径）。"""
    conv_mgr = _FakeConversationManager()
    root = tempfile.mkdtemp(prefix="backfill_dup_")
    p = _RealPersistPlugin(root=root, conv_mgr=conv_mgr, text="在吗")
    p._store.session_origins.set("u1", "test:u1")

    event1 = _Event(is_stopped=False, req=_ReqStub(has_conversation=True), umo="test:u1")
    await p._backfill_user_if_framework_skips(event1, _Resp(""))

    event2 = _Event(is_stopped=False, req=_ReqStub(has_conversation=True), umo="test:u1")
    await p._backfill_user_if_framework_skips(event2, _Resp(""))

    cid = conv_mgr._curr_ids["test:u1"]
    history = conv_mgr._content[cid]
    assert len(history) == 2, f"两条相同用户消息都应保留，不应被幂等守卫误删：{history}"


# ---------------------------------------------------------------------------
# ⑦：legacy 抛异常 -> finally 仍补写恰好一次（H1）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_7_legacy_raises_finally_still_backfills(monkeypatch: pytest.MonkeyPatch) -> None:
    """⑦ legacy 分支抛异常（H1）-> finally 仍补写恰好一次（异常上抛不吞 user）。"""
    import sylanne_alpha.v2core.integration as integration_mod

    async def _v2core_falls_through(*_a, **_k):
        return False

    monkeypatch.setattr(integration_mod, "apply_v2core_response", _v2core_falls_through)

    p = _AbortablePlugin(text="在干嘛呢", aborted=False, legacy_raises=True)
    event = _Event(is_stopped=False, req=_ReqStub(has_conversation=True))
    resp = _Resp("")

    with pytest.raises(RuntimeError, match="legacy boom"):
        await p._on_llm_response_with_bound_runtime(event, resp)

    assert p.user_sync_calls == [("sk1", "user", "在干嘛呢")], (
        f"legacy 抛异常也不应吞掉 finally 补写，实际：{p.user_sync_calls!r}"
    )


# ---------------------------------------------------------------------------
# ⑧（非门禁，characterization）：burst 合并轮 SILENT，记录补写文本形状
# ---------------------------------------------------------------------------


class _BurstEvent(_Event):
    """message_str 已被请求期 burst 合并覆写为 merged_plain
    （llm_request_pipeline.py:1159），但 message_chain 仍保留原始未合并的
    Plain 分段——甲-2 LOW 残留：_text() 可能把两者重复拼接。"""

    def __init__(self, *, merged: str, fragments: list[str], **kw) -> None:
        super().__init__(**kw)
        self.message_str = merged
        self.message_chain = [SimpleNamespace(type="Plain", text=f) for f in fragments]


@pytest.mark.asyncio
async def test_8_burst_merged_silent_backfill_text_shape_characterization() -> None:
    """非门禁：仅记录 burst 合并轮 SILENT 补写文本的实际形状，供后续处理
    "文本可能拼歪"（非丢非重，甲-2 LOW 残留）时有一条基线可对比。"""
    from sylanne_alpha.llm_response_pipeline import LLMResponsePipeline

    class _RealTextPlugin(_Plugin):
        def _text(self, event) -> str:  # type: ignore[override]
            return LLMResponsePipeline._text(self, event)  # type: ignore[arg-type]

    p = _RealTextPlugin()
    event = _BurstEvent(
        merged="第一句 第二句",
        fragments=["第一句", "第二句"],
        is_stopped=False,
        req=_ReqStub(has_conversation=True),
    )
    resp = _Resp("")

    await p._backfill_user_if_framework_skips(event, resp)

    assert len(p.user_sync_calls) == 1
    _, role, text = p.user_sync_calls[0]
    assert role == "user"
    # characterization-only：不对具体拼接结果做强断言，只记录非空、非门禁。
    assert text, f"burst 合并轮补写文本形状：{text!r}"
