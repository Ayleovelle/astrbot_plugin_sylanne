"""fix/context-integrity 红队诊断验证：SILENT / thinking-only 轮的用户消息保存。

背景（诊断复核，见 PR 描述 PRIME/CONTRIB 两条 finding）：
  (a) PRIME 假设：v2core SILENT 把 completion_text 清空后，AstrBot 框架自身的
      _save_to_history 在 completion_text 为空时提前 return、不写库，因此整轮
      （包括用户刚发的那句话）从会话历史里消失。
  (b) CONTRIB 假设：legacy 非拦截分支（realtime_intercept=False，现网默认）里，
      thinking-only 草稿被剥空后直接返回，既不发送也没有 no-ghost 兜底。

本文件先用真实（非重新实现）的 sync_message_to_conv_mgr 路径复核 (a)：插件在
llm_request_pipeline._background_observe_request 里对**每一条**用户消息都会在
拿到 LLM 回复之前，异步把用户原文单独 append 进 AstrBot ConversationManager
（sylanne_alpha/state_persistence.py:_do_sync_to_conv_mgr）。这条写入路径完全
独立于 v2core 在 response 阶段对 completion_text 做了什么——SILENT 轮同样会走
到这次写入。因此 (a) 描述的"整轮从历史消失"在当前代码库里不成立：用户的话已经
在 LLM 甚至还没返回时就落了库；SILENT 分支本身不需要（也不应该）再补一次写，
否则会把同一句用户消息在 ConversationManager 历史里追加两次。

这份测试把这条既有链路端到端跑一遍（request 阶段的 conv_mgr 同步 + response
阶段真实的 apply_v2core_response SILENT 判定），断言：
  1. SILENT 轮结束后，conv_mgr 历史里恰好有一条用户消息，没有助手消息。
  2. 不会因为在 SILENT 分支重复调用同步而产生重复条目。

(b) 的验证见 test_llm_response_pipeline_nonintercept_fallback.py（同一 PR 分组）。
"""

from __future__ import annotations

import tempfile
from types import SimpleNamespace

import pytest

from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost
from sylanne_alpha.v2core.contracts import Reply, ReplyKind
from sylanne_alpha.v2core.integration import apply_v2core_response


class FakeConversationManager:
    """与 tests/test_astrbot_manager_integration.py 同款最小 AstrBot ConvMgr 桩。"""

    def __init__(self) -> None:
        self.conversations: dict[str, dict] = {}
        self._curr_ids: dict[str, str] = {}
        self._next_id = 1

    async def get_curr_conversation_id(self, uid: str) -> str | None:
        return self._curr_ids.get(uid)

    async def new_conversation(self, uid: str) -> str:
        cid = f"conv_{self._next_id}"
        self._next_id += 1
        self._curr_ids[uid] = cid
        self.conversations[cid] = {"uid": uid, "history": []}
        return cid

    async def get_conversation(self, uid: str, cid: str):
        data = self.conversations.get(cid)
        if data is None:
            return None
        return SimpleNamespace(history=data["history"])

    async def update_conversation(self, uid: str, cid: str, history=None, title=None):
        if cid in self.conversations:
            if history is not None:
                self.conversations[cid]["history"] = history


class _Resp:
    def __init__(self, t: str) -> None:
        self.completion_text = t


class _Pipe:
    def __init__(self, text: str) -> None:
        self._t = text

    def _text(self, _e: object) -> str:
        return self._t


class _Plugin:
    """最小插件桩：桥接 apply_v2core_response 需要的属性 + 真实
    StatePersistence.sync_message_to_conv_mgr 委托（与 main.py 的
    `_sync_message_to_conv_mgr` 委托写法完全一致，见 main.py:1852-1855）。
    """

    def __init__(self, *, root: str, conv_mgr: FakeConversationManager, text: str) -> None:
        self._config = {"sylanne_enable_v2core": True}
        self._root = root
        self._llm_response_pipeline = _Pipe(text)
        self._hosts: dict[str, SylanneAlphaHost] = {}
        self._conv_mgr = conv_mgr

        from sylanne_alpha.session_state_store import SessionStateStore
        from sylanne_alpha.state_persistence import StatePersistence

        self._store = SessionStateStore()
        self._state_persistence = StatePersistence(self)

    def _session_key(self, _e: object) -> str:
        return "u1"

    def _host(self, sk: str) -> SylanneAlphaHost:
        if sk not in self._hosts:
            self._hosts[sk] = SylanneAlphaHost(root=self._root, session_key=sk)
        return self._hosts[sk]

    def _has_conversation_manager(self) -> bool:
        return self._conv_mgr is not None

    async def _sync_message_to_conv_mgr(self, session_key: str, role: str, text: str) -> None:
        # 与 main.py:_sync_message_to_conv_mgr 完全一致的委托写法。
        await self._state_persistence.sync_message_to_conv_mgr(session_key, role, text)


class _Event:
    unified_msg_origin = "test:u1"


def _plugin(text: str) -> tuple[_Plugin, FakeConversationManager]:
    conv_mgr = FakeConversationManager()
    p = _Plugin(root=tempfile.mkdtemp(prefix="sylctxint_"), conv_mgr=conv_mgr, text=text)
    return p, conv_mgr


@pytest.mark.asyncio
async def test_request_time_user_sync_survives_silent_turn() -> None:
    """request 阶段已同步的用户消息，在 response 阶段判为 SILENT 后仍完整保留。

    顺序严格复刻真实管线：llm_request_pipeline 在拿到 LLM 回复之前就把用户原文
    异步写进 conv_mgr（这里直接调用同一入口方法模拟）；然后 response 阶段
    apply_v2core_response 判为 SILENT，只清空 completion_text，不触碰 conv_mgr。
    """
    text = "在干嘛呢"
    p, conv_mgr = _plugin(text)

    # Step 1：模拟 llm_request_pipeline._background_observe_request 里已经
    # 无条件跑过的那次同步（真实调用点：sylanne_alpha/llm_request_pipeline.py:2021）。
    await p._sync_message_to_conv_mgr("u1", "user", text)

    # Step 2：先跑一轮把 v2core 运行态建起来，再把 decision stage 打桩成 SILENT
    # （ignition 的真实分支条件多、难以从外部稳定触发，这里直接控制裁决产物，
    # 只验证 apply_v2core_response 对 SILENT 的处理是否会破坏/重复写 conv_mgr）。
    warmup = _Resp("warmup")
    await apply_v2core_response(p, _Event(), warmup)
    rt = p._v2core_runtimes["u1"]
    rt["runner"].run_decision_stage = lambda *a, **k: Reply(  # type: ignore[method-assign]
        kind=ReplyKind.SILENT, meta={"reason": "test_forced_silent"}
    )

    resp = _Resp("draft the model produced")
    took = await apply_v2core_response(p, _Event(), resp)
    assert took is True, "SILENT 应终结本轮（跳过 legacy）"
    assert resp.completion_text == "", "SILENT 轮仍应清空 completion_text（对外沉默）"

    # Step 3：框架侧 _save_to_history 在 completion_text 为空时提前 return，
    # 不做任何事——这里不模拟它，因为它本来就什么都不做。真正验证的是 conv_mgr
    # 里此刻已经落库的内容：用户那句话必须还在，且不应该因为 SILENT 分支被
    # 二次写入而重复。
    cid = conv_mgr._curr_ids["u1"]
    history = conv_mgr.conversations[cid]["history"]
    assert len(history) == 1, f"用户消息应恰好一条，不应被 SILENT 抹掉或重复写：{history}"

    user_entries = [h for h in history if _role_of(h) == "user"]
    assert len(user_entries) == 1
    assert _content_of(user_entries[0]) == text


@pytest.mark.asyncio
async def test_silent_branch_itself_makes_no_conv_mgr_writes() -> None:
    """进一步确认：apply_v2core_response 的 SILENT 分支不会自己触发任何
    conv_mgr 写入（写入职责完全在 request 阶段，SILENT 分支只清 completion_text）。
    """
    text = "喂"
    p, conv_mgr = _plugin(text)

    warmup = _Resp("warmup")
    await apply_v2core_response(p, _Event(), warmup)
    rt = p._v2core_runtimes["u1"]
    rt["runner"].run_decision_stage = lambda *a, **k: Reply(
        kind=ReplyKind.SILENT, meta={"reason": "test_forced_silent"}
    )

    # 注意：这里故意不调用 _sync_message_to_conv_mgr，模拟"request 阶段同步因为
    # 某种原因还没跑完"的极端情形——验证 SILENT 分支本身确实是零写（不会代为
    # 造一条记录），从而证明 conv_mgr 的持久化完全来自 request 阶段那条独立链路，
    # 不是 SILENT 分支内部有任何写库副作用。
    resp = _Resp("draft")
    took = await apply_v2core_response(p, _Event(), resp)
    assert took is True
    assert conv_mgr.conversations == {}, "SILENT 分支不应自己产生任何 conv_mgr 写入"


def _role_of(entry: object) -> str:
    if isinstance(entry, dict):
        return str(entry.get("role", ""))
    return str(getattr(entry, "role", ""))


def _content_of(entry: object) -> str:
    """兼容两种落库形状：dict（旧版/测试环境回退）与真实
    UserMessageSegment/AssistantMessageSegment 对象（AstrBot 消息类型可用时，
    _do_sync_to_conv_mgr 直接 append 的是 pydantic 对象本身，不是 model_dump()
    后的 dict——见 state_persistence.py:_do_sync_to_conv_mgr）。
    """
    if isinstance(entry, dict):
        content = entry.get("content")
    else:
        content = getattr(entry, "content", None)
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and "text" in part:
                return str(part["text"])
            text = getattr(part, "text", None)
            if text is not None:
                return str(text)
        return ""
    return str(content or "")
