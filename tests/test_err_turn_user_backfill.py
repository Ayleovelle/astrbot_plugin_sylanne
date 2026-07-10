"""2.4.1 err 轮兜底（未提交新增）——覆盖 main.py 三处改动：

  1. `_on_llm_request_inner` 入口 set_extra("_syl_resp_handled", False)
  2. `_on_llm_response_inner` 入口 set_extra("_syl_resp_handled", True)
  3. 新增 `@filter.after_message_sent` 钩子 `_on_after_message_sent_err_backfill`：
     仅当 `handled is False`（三态里唯一的"err 轮"态）才补写 user。

三态语义（钉死，不可反转为 truthy 判定）：
  None  = 本轮没走 LLM 请求（纯指令/被前置插件拦截）-> 绝不补写
  True  = on_llm_response 已跑（正常/SILENT/异常兜底都在其 finally 处理过）-> 不补
  False = 请求跑过、响应钩子从未触发（provider 全挂的 err 轮）-> 补写

本文件不重跑 test_leg3_crosslock_regression.py 已覆盖的 SPEAK/SILENT 主判据
（_framework_will_persist_this_turn 的 completion/tool_res/abort 腿），只聚焦
err 轮兜底这条新增电路：三态分区、幂等、判据的 response=None 腿、标记健壮性、
钩子自身异常隔离、以及"同一插件可注册多个 after_message_sent handler 且都会被
框架调用"这条契约（对应实现计划验收门 #6）。
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import inspect
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from main import EmotionalStatePlugin
from sylanne_alpha.session_state_store import SessionStateStore
from sylanne_alpha.state_persistence import StatePersistence

SESSION_KEY = "sess:aylovelle:2300184508"
UMO = "aiocqhttp:FriendMessage:2300184508"
CID = "cid-uuid-err-1"
U_TEXT = "喂，你死机了吗"


def user_dict(text: str) -> dict:
    return {"role": "user", "content": [{"type": "text", "text": text}]}


def text_of(entry: dict) -> str:
    c = entry.get("content")
    if isinstance(c, list):
        return "".join(
            str(p.get("text") or "") for p in c if isinstance(p, dict) and "text" in p
        )
    return str(c or "")


def role_seq(content: list[dict]) -> list[str]:
    return [str(e.get("role", "?")) for e in content]


# ---------------------------------------------------------------------------
# 事件桩：三种形状
# ---------------------------------------------------------------------------


class _MarkedEvent:
    """支持 get_extra/set_extra 的标准桩（模拟真实 AstrMessageEvent 的 extra 面）。"""

    def __init__(self, *, extras: dict | None = None) -> None:
        self._extras: dict = dict(extras or {})
        self.unified_msg_origin = UMO
        self._stopped = False

    def get_extra(self, key: str, default=None):
        return self._extras.get(key, default)

    def set_extra(self, key: str, value) -> None:
        self._extras[key] = value

    def is_stopped(self) -> bool:
        return self._stopped


class _LegacyEventNoExtra:
    """旧桩：完全没有 get_extra/set_extra 属性（不是抛异常，是压根不存在）。

    main.py 用 `getattr(event, "set_extra", None)` / `getattr(event, "get_extra", None)`
    + `callable(...)` 判空，覆盖的正是这种旧事件对象形状。"""

    def __init__(self) -> None:
        self.unified_msg_origin = UMO

    def is_stopped(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# 终态门（_agent_run_done）测试桩：仿造 tool_loop_agent_runner 的 .done()/.was_aborted()
# 面，注册进真实 follow_up._ACTIVE_AGENT_RUNNERS，驱动真实 _agent_run_done 实现
# （而非 mock 掉整个终态门——终态门本身就是本轮红线闸吸收的 Finding #1 三道防线
# 之一，必须用真实实现覆盖，不能只信任调用者按约定传参）。
# ---------------------------------------------------------------------------


class _FakeRunner:
    def __init__(self, *, done: bool | None = True, aborted: bool = False) -> None:
        self._done = done
        self._aborted = aborted

    def done(self) -> bool | None:
        return self._done

    def was_aborted(self) -> bool:
        return self._aborted


@contextlib.contextmanager
def _registered_runner(umo: str, runner: _FakeRunner | None):
    """在 `follow_up._ACTIVE_AGENT_RUNNERS` 里临时注册/摘除一个假 runner。
    `runner=None` 时不注册任何东西，模拟"注册表未命中"（_agent_run_done 应返回 None）。"""
    from astrbot.core.pipeline.process_stage.follow_up import _ACTIVE_AGENT_RUNNERS

    if runner is None:
        _ACTIVE_AGENT_RUNNERS.pop(umo, None)
        yield
        return
    _ACTIVE_AGENT_RUNNERS[umo] = runner
    try:
        yield
    finally:
        _ACTIVE_AGENT_RUNNERS.pop(umo, None)


# ---------------------------------------------------------------------------
# 组 1：三态分区 + 幂等（钉死主循环手改的核心防线；用 mock 隔离写路径）
# ---------------------------------------------------------------------------


class _HookOnlyPlugin:
    """只装三态标记读取用得到的最小面，`_backfill_user_if_framework_skips` 用
    AsyncMock 隔离——这组测试只钉"标记 -> 是否触发补写调用"这条门控逻辑本身，
    不掺写路径的真实持久化（那条在组 3 单独用真实原语覆盖）。

    `_agent_run_done` 用的是真实实现（读真实 `_ACTIVE_AGENT_RUNNERS` 注册表），
    不 mock——终态门本身就是被测对象的一部分，见下方 `_registered_runner`。"""

    _on_after_message_sent_err_backfill = (
        EmotionalStatePlugin._on_after_message_sent_err_backfill
    )
    _agent_run_done = EmotionalStatePlugin._agent_run_done

    def __init__(self) -> None:
        self._backfill_user_if_framework_skips = AsyncMock()


@pytest.mark.asyncio
async def test_handled_none_zero_writes_non_llm_turn() -> None:
    """(a) handled=None（纯指令/被前置插件拦截，从未走 LLM 请求）-> 钩子零 user 写。

    这是主循环手改的核心防线：若误用 truthy 判定，None 会被当成 False 而盲补
    一条 user 进历史——纯指令轮压根没有对应的用户 LLM 轮文本可补。

    刻意注册一个 done=True 的 runner：让终态门【放行】，把这条断言单独压在三态门上。
    否则终态门会先因取不到 runner 而早退，替三态门挡枪，三态判定本身就没被独立钉死
    （若把 `is not False` 退化成 truthy，本测试仍会因终态门早退而误绿）。"""
    p = _HookOnlyPlugin()
    event = _MarkedEvent(extras={})  # 从未被 _on_llm_request_inner 碰过

    with _registered_runner(UMO, _FakeRunner(done=True)):
        await p._on_after_message_sent_err_backfill(event)

    p._backfill_user_if_framework_skips.assert_not_awaited()


@pytest.mark.asyncio
async def test_handled_true_zero_writes_response_hook_ran() -> None:
    """(b) handled=True（on_llm_response 跑过，finally 已经处理过补写）-> 零写。

    同上注册 done=True runner 让终态门放行，把断言单独压在三态门（True 分支）上。"""
    p = _HookOnlyPlugin()
    event = _MarkedEvent(extras={"_syl_resp_handled": True})

    with _registered_runner(UMO, _FakeRunner(done=True)):
        await p._on_after_message_sent_err_backfill(event)

    p._backfill_user_if_framework_skips.assert_not_awaited()


@pytest.mark.asyncio
async def test_handled_false_backfills_exactly_once_err_turn() -> None:
    """(c) handled=False（err 轮：请求跑过，响应钩子从未触发）且终态门
    `_agent_run_done` 真实返回 True（runner 已到 DONE/ERROR，真 err 轮的真实
    形状）-> 恰好补写 1 条。

    此前版本没有注册 runner，_agent_run_done 会因 self 缺该属性直接
    AttributeError（旧版 _HookOnlyPlugin 未挂 _agent_run_done），钩子自身的
    try/except 把异常吞掉、测试断言落空——现在改用真实 _agent_run_done +
    真实注册表，逼真还原终态门这道防线。"""
    p = _HookOnlyPlugin()
    event = _MarkedEvent(extras={"_syl_resp_handled": False})

    with _registered_runner(UMO, _FakeRunner(done=True)):
        await p._on_after_message_sent_err_backfill(event)

    p._backfill_user_if_framework_skips.assert_awaited_once_with(event, None)


# ---------------------------------------------------------------------------
# 组 1b：终态门（_agent_run_done）三分区 —— handled=False 之后仍有三种终态门结果，
# 只有 done()==True 才放行；None（取不到 runner）与 False（中间步未 done）都要
# 零补写。这是钩子文档里"两道门 + 一道兜底"中的门2，此前完全没有独立测试覆盖。
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_terminal_gate_none_when_runner_missing_zero_writes() -> None:
    """(a) handled=False 但 `_agent_run_done` 返回 None（注册表未命中/第三方
    runner 部署）-> 宁丢不重，零补写。"""
    p = _HookOnlyPlugin()
    event = _MarkedEvent(extras={"_syl_resp_handled": False})

    with _registered_runner(UMO, None):
        await p._on_after_message_sent_err_backfill(event)

    p._backfill_user_if_framework_skips.assert_not_awaited()


@pytest.mark.asyncio
async def test_terminal_gate_false_when_runner_mid_tool_loop_zero_writes() -> None:
    """(b) handled=False 但 `_agent_run_done` 返回 False（runner 已注册但未
    done，即 tool 循环中间步——模型带 preamble 文本调工具时的中间发消息）
    -> 零补写，不能把中间步误判成 err 轮。"""
    p = _HookOnlyPlugin()
    event = _MarkedEvent(extras={"_syl_resp_handled": False})

    with _registered_runner(UMO, _FakeRunner(done=False)):
        await p._on_after_message_sent_err_backfill(event)

    p._backfill_user_if_framework_skips.assert_not_awaited()


@pytest.mark.asyncio
async def test_terminal_gate_true_backfills_once() -> None:
    """(c) handled=False 且 `_agent_run_done` 返回 True -> 补写 1 次（与
    test_handled_false_backfills_exactly_once_err_turn 重复覆盖同一分区，
    这里独立成组方便一眼看清终态门的完整真值表）。"""
    p = _HookOnlyPlugin()
    event = _MarkedEvent(extras={"_syl_resp_handled": False})

    with _registered_runner(UMO, _FakeRunner(done=True)):
        await p._on_after_message_sent_err_backfill(event)

    p._backfill_user_if_framework_skips.assert_awaited_once_with(event, None)


@pytest.mark.asyncio
async def test_idempotent_response_hook_ran_then_after_message_sent_fires_too() -> None:
    """幂等/双写：同一轮既跑了 on_llm_response（finally 补写一次）又触发
    after_message_sent（handled 已是 True）-> user 只被写一次，不是两次。

    这里直接驱动真实 `_on_llm_response_inner`（会在入口置 True、finally 里调用
    一次 `_backfill_user_if_framework_skips`），再驱动真实
    `_on_after_message_sent_err_backfill`（应因 handled=True 早退零调用）。
    汇总两次驱动，`_backfill_user_if_framework_skips` 总调用次数必须恰好 1。"""

    class _FullTurnPlugin:
        _on_llm_response_inner = EmotionalStatePlugin._on_llm_response_inner
        _on_after_message_sent_err_backfill = (
            EmotionalStatePlugin._on_after_message_sent_err_backfill
        )

        def __init__(self) -> None:
            self._backfill_user_if_framework_skips = AsyncMock()
            self._llm_response_pipeline = SimpleNamespace(
                _on_llm_response_inner=AsyncMock()
            )
            # 无 .config / ._config -> v2core_enabled 走默认 True 分支，
            # apply_v2core_response 内部会因缺属性抛异常，被 main.py 的
            # try/except 吸收、handled=False，回落到 legacy pipeline 的 mock。
            # 与本测试目的（只看补写调用次数）无关，属实现细节，任其自然发生。

    p = _FullTurnPlugin()
    event = _MarkedEvent(extras={})
    resp = SimpleNamespace(role="assistant", completion_text="嗯")

    await p._on_llm_response_inner(event, resp)  # 响应钩子跑过 -> 补写 1 次 + handled=True
    await p._on_after_message_sent_err_backfill(event)  # handled=True -> 早退

    assert p._backfill_user_if_framework_skips.await_count == 1, (
        "响应钩子已处理过的轮，after_message_sent 兜底必须早退，"
        f"实际调用次数：{p._backfill_user_if_framework_skips.await_count}"
    )
    assert event.get_extra("_syl_resp_handled") is True


# ---------------------------------------------------------------------------
# 组 2：请求/响应管线三态标记置位健壮性（旧桩无 get_extra/set_extra）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_pipeline_survives_event_without_extra_api() -> None:
    """标记置位健壮性：event 没有 set_extra（旧桩）时，请求管线不炸、正常委派。"""

    class _ReqPipelinePlugin:
        _on_llm_request_inner = EmotionalStatePlugin._on_llm_request_inner

        def __init__(self) -> None:
            self._llm_request_pipeline = SimpleNamespace(
                _on_llm_request_inner=AsyncMock(return_value=None)
            )

    p = _ReqPipelinePlugin()
    event = _LegacyEventNoExtra()  # 无 get_extra/set_extra

    await p._on_llm_request_inner(event, request=SimpleNamespace())  # 不应抛异常

    p._llm_request_pipeline._on_llm_request_inner.assert_awaited_once()


@pytest.mark.asyncio
async def test_response_pipeline_survives_event_without_extra_api() -> None:
    """标记置位健壮性：event 没有 set_extra（旧桩）时，响应管线不炸。

    `_backfill_user_if_framework_skips` 本身也要能扛住同一个旧桩（它内部读
    get_extra("provider_request") 用的是同一套 getattr+callable 判空），
    这里直接放行真实实现验证零异常。"""

    class _RespPipelinePlugin:
        _on_llm_response_inner = EmotionalStatePlugin._on_llm_response_inner
        _backfill_user_if_framework_skips = (
            EmotionalStatePlugin._backfill_user_if_framework_skips
        )
        _framework_will_persist_this_turn = (
            EmotionalStatePlugin._framework_will_persist_this_turn
        )
        _agent_was_aborted = EmotionalStatePlugin._agent_was_aborted

        def __init__(self) -> None:
            self._llm_response_pipeline = SimpleNamespace(
                _on_llm_response_inner=AsyncMock(return_value=None)
            )

        def _has_conversation_manager(self) -> bool:
            return False  # 旧桩场景下不需要真正落库，只验证不抛异常

    p = _RespPipelinePlugin()
    event = _LegacyEventNoExtra()
    resp = SimpleNamespace(role="assistant", completion_text="")

    await p._on_llm_response_inner(event, resp)  # 不应抛异常


@pytest.mark.asyncio
async def test_after_message_sent_hook_early_returns_without_extra_api() -> None:
    """(d) 旧桩场景：`_on_after_message_sent_err_backfill` 自身必须安全早退——
    不是"不炸"这么低的要求，而是【压根不该尝试补写】（没有标记可读，视同未知态，
    宁可漏补也不可能盲补）。"""
    p = _HookOnlyPlugin()
    event = _LegacyEventNoExtra()

    await p._on_after_message_sent_err_backfill(event)  # 不应抛异常

    p._backfill_user_if_framework_skips.assert_not_awaited()


# ---------------------------------------------------------------------------
# 组 3：err 轮判据路径 —— 真实 `_framework_will_persist_this_turn` +
# 真实 `_backfill_user_if_framework_skips` + 真实 StatePersistence 原语
# ---------------------------------------------------------------------------


class FakeConvMgr:
    """同 test_leg3_crosslock_regression.py 的忠实最小仿造。"""

    def __init__(self, initial: list[dict] | None = None) -> None:
        self._content: list[dict] = list(initial or [])

    async def get_curr_conversation_id(self, umo: str) -> str:
        return CID

    async def new_conversation(self, umo: str) -> str:
        return CID

    async def get_conversation(self, umo, cid, create_if_not_exists: bool = False):
        return SimpleNamespace(history=json.dumps(list(self._content), ensure_ascii=False))

    async def update_conversation(self, umo, cid=None, history=None, **kw) -> None:
        self._content = list(history or [])


class _RealPrimitivePlugin:
    """驱动真实 `_framework_will_persist_this_turn` / `_backfill_user_if_framework_skips`
    / `_agent_was_aborted`，写入路径走真实 StatePersistence 原语（非 call-spy）。"""

    _framework_will_persist_this_turn = EmotionalStatePlugin._framework_will_persist_this_turn
    _backfill_user_if_framework_skips = EmotionalStatePlugin._backfill_user_if_framework_skips
    _agent_was_aborted = EmotionalStatePlugin._agent_was_aborted

    def __init__(self, conv_mgr: FakeConvMgr) -> None:
        self._conv_mgr = conv_mgr
        self._store = SessionStateStore()
        self._store.session_origins.set(SESSION_KEY, UMO)
        self._state_persistence = StatePersistence(self)
        self.sync_calls: list[tuple[str, str, str]] = []

    def _has_conversation_manager(self) -> bool:
        return True

    def _text(self, _event) -> str:
        return U_TEXT

    def _session_key(self, _event) -> str:
        return SESSION_KEY

    async def _sync_message_to_conv_mgr(self, session_key: str, role: str, text: str) -> None:
        self.sync_calls.append((session_key, role, text))
        await self._state_persistence.sync_message_to_conv_mgr(session_key, role, text)


def _req_stub(*, has_conversation: bool = True):
    return SimpleNamespace(
        conversation=object() if has_conversation else None,
        tool_calls_result=None,
    )


@pytest.mark.asyncio
async def test_framework_will_persist_returns_false_for_none_response() -> None:
    """err 轮判据路径 ①：response=None 时 `_framework_will_persist_this_turn`
    必须返回 False（命中"无有效 assistant 回复"腿：`response is None`）。"""
    p = _RealPrimitivePlugin(FakeConvMgr())
    event = _MarkedEvent(extras={"provider_request": _req_stub()})

    result = p._framework_will_persist_this_turn(event, None)

    assert result is False


@pytest.mark.asyncio
async def test_backfill_writes_user_on_err_turn_response_none() -> None:
    """err 轮判据路径 ②：`_backfill_user_if_framework_skips(event, None)` 端到端
    真实写入——恰好补写 1 条 user，历史里没有多余的 assistant（err 轮本来就没有
    可用的助手回复）。"""
    mgr = FakeConvMgr()
    p = _RealPrimitivePlugin(mgr)
    event = _MarkedEvent(extras={"provider_request": _req_stub()})

    await p._backfill_user_if_framework_skips(event, None)

    assert p.sync_calls == [(SESSION_KEY, "user", U_TEXT)]
    final = mgr._content
    assert role_seq(final) == ["user"]
    assert text_of(final[0]) == U_TEXT


@pytest.mark.asyncio
async def test_backfill_noop_when_no_conversation_manager() -> None:
    """`_has_conversation_manager()` False 时（未接 ConversationManager 的部署）
    补写直接早退，不触碰任何写路径——即便标记是 err 轮态。"""

    class _NoConvMgrPlugin(_RealPrimitivePlugin):
        def _has_conversation_manager(self) -> bool:
            return False

    p = _NoConvMgrPlugin(FakeConvMgr())
    event = _MarkedEvent(extras={"provider_request": _req_stub()})

    await p._backfill_user_if_framework_skips(event, None)

    assert p.sync_calls == []


# ---------------------------------------------------------------------------
# 组 3b：once-guard 核心回归（红线闸 Finding #1 直接回归）—— 真实原语
# （真 SessionStateStore + StatePersistence + FakeConvMgr，非 call-spy），驱动
# 同一事件两次触发补写路径，断言历史最终只有一条 user，而非悬挂重复
# ["user","user"]。这条测试的价值在于：如果有人以后"优化"掉 once-guard 的
# check-then-set，本组必须翻红（已用变异验证确认，见任务交接记录）。
# ---------------------------------------------------------------------------


class _RealHookPlugin(_RealPrimitivePlugin):
    """在真实原语插件基础上再挂真实 `_on_after_message_sent_err_backfill` +
    真实 `_agent_run_done`，用于驱动"钩子被多次触发"的端到端回归（组 4 的
    buffered 模式顺序反转测试）。"""

    _on_after_message_sent_err_backfill = (
        EmotionalStatePlugin._on_after_message_sent_err_backfill
    )
    _agent_run_done = EmotionalStatePlugin._agent_run_done


@pytest.mark.asyncio
async def test_once_guard_survives_two_backfill_triggers_real_primitives() -> None:
    """核心回归：同一事件（同一轮）连续两次直接触发
    `_backfill_user_if_framework_skips(event, None)`——对应"err 钩子先补一次，
    tool 循环 preamble 合并步又补一次"的真实悬挂重复场景——once-guard 必须让
    最终历史恰好是 ["user"]，而不是 ["user", "user"]。

    变异验证（已执行，验证后已还原，不留在代码里）：临时把
    `_backfill_user_if_framework_skips` 里 once-guard 的 check
    （`get_extra("_syl_user_backfilled", False)` 提前 return）与 set
    （`set_extra("_syl_user_backfilled", True)`）两处都删掉后，本测试断言
    `role_seq == ["user"]` 立即翻红为 `["user", "user"]`，`sync_calls` 长度从
    1 变 2——证明本测试确实在盯 once-guard 这条电路，不是摆设。"""
    mgr = FakeConvMgr()
    p = _RealPrimitivePlugin(mgr)
    event = _MarkedEvent(extras={"provider_request": _req_stub()})

    await p._backfill_user_if_framework_skips(event, None)
    await p._backfill_user_if_framework_skips(event, None)

    assert role_seq(mgr._content) == ["user"], (
        f"once-guard 失守，产出悬挂重复：{role_seq(mgr._content)}"
    )
    assert p.sync_calls == [(SESSION_KEY, "user", U_TEXT)], (
        f"_sync_message_to_conv_mgr 被多写了一次：{p.sync_calls}"
    )


@pytest.mark.asyncio
async def test_buffered_mode_order_reversal_once_guard_still_single_write() -> None:
    """buffered 模式顺序反转回归：err 先触发一次 after_message_sent 钩子
    （此刻 handled 仍 False、runner 已 done -> 终态门放行、once-guard 补写 1
    次），随后同一轮内合并 preamble 又触发一次同一个钩子（handled 仍 False——
    err-backfill 钩子本身从不消费 `_syl_resp_handled`，那面标记只由响应钩子
    写——terminal gate 仍是 done()==True，两次都会进到
    `_backfill_user_if_framework_skips`）——once-guard 必须挡住第二次，最终
    历史仍只有一条 user。"""
    mgr = FakeConvMgr()
    p = _RealHookPlugin(mgr)
    event = _MarkedEvent(
        extras={"_syl_resp_handled": False, "provider_request": _req_stub()}
    )

    with _registered_runner(UMO, _FakeRunner(done=True)):
        await p._on_after_message_sent_err_backfill(event)  # err 先触发
        await p._on_after_message_sent_err_backfill(event)  # preamble 合并后再触发

    assert role_seq(mgr._content) == ["user"], (
        f"buffered 顺序反转下 once-guard 失守：{role_seq(mgr._content)}"
    )
    assert p.sync_calls == [(SESSION_KEY, "user", U_TEXT)]


# ---------------------------------------------------------------------------
# 组 4：钩子自身异常隔离（不阻断 after_message_sent 链上其它 handler）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hook_exception_is_swallowed_not_propagated() -> None:
    """钩子自身异常不上抛：`_backfill_user_if_framework_skips` 炸了，
    `_on_after_message_sent_err_backfill` 必须吞掉（warning 即可），不能让异常
    冒到调用方（框架的 call_event_hook 循环）。"""
    p = _HookOnlyPlugin()
    p._backfill_user_if_framework_skips = AsyncMock(side_effect=RuntimeError("boom"))
    event = _MarkedEvent(extras={"_syl_resp_handled": False})

    await p._on_after_message_sent_err_backfill(event)  # 不应抛出


@pytest.mark.asyncio
async def test_hook_exception_does_not_block_sibling_handler_in_manual_chain() -> None:
    """模拟框架 call_event_hook 的循环形状（context_utils.py:92-100：per-handler
    try/except BaseException，不因单个 handler 异常中断整个链）：即便本插件的
    err-backfill 钩子抛异常，同插件另一个 after_message_sent handler
    （on_after_message_sent_reset_ghost_cleanup）依然要被调用到。"""

    class _TwoHandlerPlugin:
        _on_after_message_sent_err_backfill = (
            EmotionalStatePlugin._on_after_message_sent_err_backfill
        )
        on_after_message_sent_reset_ghost_cleanup = (
            EmotionalStatePlugin.on_after_message_sent_reset_ghost_cleanup
        )

        def __init__(self) -> None:
            # 让 err-backfill 内部触发异常路径（get_extra 存在但 backfill 炸）
            self._backfill_user_if_framework_skips = AsyncMock(
                side_effect=RuntimeError("boom")
            )
            self.reset_called_with: list = []

        def _on_session_reset(self, session_key: str) -> None:
            self.reset_called_with.append(session_key)

        class _SessionCtx:
            def session_key(self, event):
                return SESSION_KEY

        _session_ctx = _SessionCtx()

    p = _TwoHandlerPlugin()
    event = _MarkedEvent(
        extras={"_syl_resp_handled": False, "_clean_ltm_session": True}
    )

    handlers = [
        p._on_after_message_sent_err_backfill,
        p.on_after_message_sent_reset_ghost_cleanup,
    ]
    for handler in handlers:
        try:
            await handler(event)
        except BaseException:  # noqa: BLE001 -- 精确复刻框架 call_event_hook 的宽捕获
            pytest.fail(
                f"{handler} 泄漏了异常到调用方，违反 call_event_hook 的 per-handler 隔离契约"
            )

    assert p.reset_called_with == [SESSION_KEY], (
        "err-backfill 钩子内部异常已被自己吞掉，不应影响同链上第二个 handler 正常执行"
    )


# ---------------------------------------------------------------------------
# 组 5：契约 pin —— 同一插件注册多个 after_message_sent handler，
# AstrBot 是否都会调用（若否，是 BLOCKER）
# ---------------------------------------------------------------------------


def test_contract_both_after_message_sent_handlers_are_distinct_registry_entries() -> None:
    """契约 pin ①：main.py 两个 `@filter.after_message_sent()` 装饰的方法
    （`_on_after_message_sent_err_backfill` / `on_after_message_sent_reset_ghost_cleanup`）
    在框架 `star_handlers_registry` 里必须是【两条独立记录】，而不是后者覆盖前者。

    依据：`astrbot.core.star.register.star_handler.get_handler_full_name` 用
    `f"{module}_{funcname}"` 做 key（非"每插件每事件类型一条"的粗粒度 key），
    两个方法名不同 -> 两个 key -> 两条记录，互不覆盖。这是"能否注册多个同类
    钩子"的地基；若框架实现改成按 (module, event_type) 做 key，这条测试会失败，
    此时才是真正的 BLOCKER，需要合并进既有钩子。"""
    from astrbot.core.star.star_handler import EventType, star_handlers_registry

    err_backfill_full_name = "main__on_after_message_sent_err_backfill"
    ghost_cleanup_full_name = "main_on_after_message_sent_reset_ghost_cleanup"

    md_err = star_handlers_registry.get_handler_by_full_name(err_backfill_full_name)
    md_ghost = star_handlers_registry.get_handler_by_full_name(ghost_cleanup_full_name)

    assert md_err is not None, (
        "err-backfill 钩子未在框架注册表中找到——装饰器要么未生效要么被覆盖"
    )
    assert md_ghost is not None, (
        "ghost-cleanup 钩子未在框架注册表中找到——若因新增钩子覆盖了它，是 BLOCKER"
    )
    assert md_err is not md_ghost
    assert md_err.event_type == EventType.OnAfterMessageSentEvent
    assert md_ghost.event_type == EventType.OnAfterMessageSentEvent


@pytest.mark.asyncio
async def test_contract_framework_invokes_both_after_message_sent_handlers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """契约 pin ②：驱动框架真实的 `call_event_hook`（不是我们自己模拟的循环），
    证明它会把两个 handler 都调用到——即便其中一个抛异常也不影响另一个。

    绑定方式精确复刻插件激活时的真实动作（star_manager.py:1064-1068）：
    `handler.handler = functools.partial(handler.handler, plugin_instance)`。
    仅 monkeypatch `star_map`（激活状态查询表）使两个 handler 通过
    `only_activated` 过滤；不触碰全局 `star_handlers_registry` 本身的持久状态。
    """
    from astrbot.core.pipeline.context_utils import call_event_hook
    from astrbot.core.star.star import StarMetadata
    from astrbot.core.star.star_handler import EventType, star_handlers_registry

    err_backfill_full_name = "main__on_after_message_sent_err_backfill"
    ghost_cleanup_full_name = "main_on_after_message_sent_reset_ghost_cleanup"
    md_err = star_handlers_registry.get_handler_by_full_name(err_backfill_full_name)
    md_ghost = star_handlers_registry.get_handler_by_full_name(ghost_cleanup_full_name)
    assert md_err is not None and md_ghost is not None

    class _Plugin:
        def __init__(self) -> None:
            self.backfill_calls = 0
            self.reset_calls = 0

        async def _on_after_message_sent_err_backfill(self, event) -> None:
            self.backfill_calls += 1
            raise RuntimeError("err-backfill 内部炸了")  # 未被自身 try/except 吞时的最坏假设

        async def on_after_message_sent_reset_ghost_cleanup(self, event) -> None:
            self.reset_calls += 1

    plugin_instance = _Plugin()

    # 备份，测试结束恢复，避免污染其它测试对 registry 的假设
    orig_err_handler = md_err.handler
    orig_ghost_handler = md_ghost.handler
    try:
        md_err.handler = functools.partial(
            plugin_instance._on_after_message_sent_err_backfill
        )
        md_ghost.handler = functools.partial(
            plugin_instance.on_after_message_sent_reset_ghost_cleanup
        )

        fake_meta = StarMetadata(
            name="sylanne-embodiment-test",
            module_path="main",
            activated=True,
        )
        monkeypatch.setattr(
            "astrbot.core.star.star_handler.star_map",
            {"main": fake_meta},
        )

        event = _MarkedEvent(extras={})
        event.plugins_name = None  # call_event_hook 用它做插件白名单过滤，None=不过滤

        await call_event_hook(event, EventType.OnAfterMessageSentEvent)

        assert plugin_instance.backfill_calls == 1
        assert plugin_instance.reset_calls == 1, (
            "err-backfill handler 抛异常后，同链上第二个 handler 必须依然被调用——"
            "若为 0，说明框架并未采用 per-handler 隔离，是真正的 BLOCKER"
        )
    finally:
        md_err.handler = orig_err_handler
        md_ghost.handler = orig_ghost_handler
