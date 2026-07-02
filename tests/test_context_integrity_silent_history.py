"""fix/context-integrity 红队诊断验证：SILENT / thinking-only 轮的用户消息保存。

背景（诊断复核，见 PR 描述 PRIME/CONTRIB 两条 finding，以及后续验收 BLOCKER 回合）：
  (a) PRIME 假设：v2core SILENT 把 completion_text 清空后，AstrBot 框架自身的
      _save_to_history 在 completion_text 为空时提前 return、不写库，因此整轮
      （包括用户刚发的那句话）从会话历史里消失。
  (b) CONTRIB 假设：legacy 非拦截分支（realtime_intercept=False，现网默认）里，
      thinking-only 草稿被剥空后直接返回，既不发送也没有 no-ghost 兜底。

第一次复核（be5f7b8）声称 (a) 不成立，理由是 llm_request_pipeline 在拿到 LLM
回复之前就已经把用户原文经 sync_message_to_conv_mgr 异步写进了 AstrBot
ConversationManager。verify 阶段指出这个复核本身是假的：真实的
_do_sync_to_conv_mgr（state_persistence.py）当时有三处独立缺陷，任何一处单独
就足以让这条"保护"在生产环境里变成静默 no-op 或者写坏数据：

  1. 把 AstrBot 消息类型（UserMessageSegment/AssistantMessageSegment，pydantic
     对象）原样 append 进历史列表再整体写回；框架的持久化列（SQLAlchemy JSON
     列）用默认 json.dumps 序列化器，遇到 pydantic 对象直接 TypeError，被
     _do_sync_to_conv_mgr 自己的 broad except 静默吞掉——表现为"同步看似成功，
     实际库里什么都没写"。
  2. AstrBot ConversationManager.get_conversation() 返回的 V1 Conversation
     dataclass，其 history 字段是 **JSON 字符串**
     （conversation_mgr.py:_convert_conv_from_v2_to_v1 里
     `history=json.dumps(conv_v2.content or [])`），不是 list。旧代码直接
     `list(conversation.history)` 会把字符串拆成单字符列表；一旦走到
     dict-fallback（AstrBot 消息类型 ImportError 时）分支，这些单字符 + 一条
     dict 全部可 JSON 序列化，写回会 **成功**，把整段已保存历史替换成字符垃圾
     ——这是一条主动破坏数据的路径，不只是"没生效"。
  3. 同步用插件内部 session_key 当 key，而框架按 unified_msg_origin
     （session_context.py 里群聊场景会在 session_key 后面追加 ":sender_id"）
     建索引——两者不是同一 key 空间，即便前两个缺陷都不存在，写入也可能落进一个
     框架从未读取的会话里。

本文件现在验证的是**修复后的真实行为**（sylanne_alpha/state_persistence.py：
sync_message_to_conv_mgr 做 session_key → unified_msg_origin 映射查询，
_do_sync_to_conv_mgr 在 append 前对 AstrBot 消息类型调用 model_dump()，
_extract_conv_history_list 显式处理 JSON 字符串 / list / None 三种历史形状）：
  1. SILENT 轮结束后，conv_mgr 历史里恰好有一条用户消息，没有助手消息。
  2. 不会因为在 SILENT 分支重复调用同步而产生重复条目。
  3. 同步会用 session_origins 映射出的 unified_msg_origin 建会话，而不是插件
     内部的 session_key。
  4. history 以 JSON 字符串形状往返（模拟真实框架），依然能正确 append 而不是
     被拆成字符。

FakeConversationManager 因此刻意贴近真实框架的关键窄面：get_conversation()
返回 JSON 字符串形态的 history；update_conversation() 收到的 history 必须是
可 JSON 序列化的普通 list[dict]（存之前先 json.dumps 校验一遍，任何漏网的
pydantic 对象都会像真实 SQLAlchemy JSON 列一样在这里炸出来，而不是被静默放过）。

(b) 的验证见 test_llm_response_pipeline_nonintercept_fallback.py（同一 PR 分组）。
"""

from __future__ import annotations

import json
import tempfile
from types import SimpleNamespace

import pytest

from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost
from sylanne_alpha.v2core.contracts import Reply, ReplyKind
from sylanne_alpha.v2core.integration import apply_v2core_response


class FakeConversationManager:
    """贴近真实 AstrBot ConversationManager 关键窄面的最小桩。

    与 tests/test_astrbot_manager_integration.py 的同名桩不同：这里的
    get_conversation() 故意返回 JSON **字符串**形态的 history（对齐
    conversation_mgr.py:_convert_conv_from_v2_to_v1 的
    `history=json.dumps(conv_v2.content or [])`），update_conversation() 写入前
    做一次 json.dumps 可序列化性校验（对齐真实 SQLAlchemy JSON 列落库时的隐性
    要求）。任何一处 state_persistence.py 里没做对的读写形状转换，都会在这里
    要么读出乱码字符列表，要么写入时直接炸 TypeError——不会像旧桩那样悄悄放过。
    """

    def __init__(self) -> None:
        self._content: dict[str, list] = {}  # cid -> list[dict]（DB 侧真值）
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
            json.dumps(history, ensure_ascii=False)  # 校验可序列化性，模拟真实落库
            self._content[cid] = history


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

    # 模拟 llm_request_pipeline 里维护的 session_key → unified_msg_origin 映射
    # （真实调用点：llm_request_pipeline.py:846-849，在 _sync_message_to_conv_mgr
    # 之前就已经写好）。
    p._store.session_origins.set("u1", "test:u1")

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
    # 二次写入而重复。会话必须落在 unified_msg_origin（"test:u1"）下，而不是
    # 插件内部的 session_key（"u1"）。
    assert "u1" not in conv_mgr._curr_ids, (
        "conv_mgr 必须按 unified_msg_origin 建会话，不能用插件内部 session_key"
    )
    cid = conv_mgr._curr_ids["test:u1"]
    history = conv_mgr._content[cid]
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
    p._store.session_origins.set("u1", "test:u1")

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
    assert conv_mgr._content == {}, "SILENT 分支不应自己产生任何 conv_mgr 写入"


@pytest.mark.asyncio
async def test_sync_uses_unified_msg_origin_when_mapping_present() -> None:
    """回归 BLOCKER 缺陷 (3)：同步必须按 unified_msg_origin 建会话，插件内部
    session_key（群聊场景下会带 ":sender_id" 后缀）不是框架的 key 空间。
    """
    p, conv_mgr = _plugin("占位")
    p._store.session_origins.set("group:123:sender_9", "aiocqhttp:GroupMessage:123")

    await p._sync_message_to_conv_mgr("group:123:sender_9", "user", "有人在吗")

    assert "group:123:sender_9" not in conv_mgr._curr_ids
    assert "aiocqhttp:GroupMessage:123" in conv_mgr._curr_ids
    cid = conv_mgr._curr_ids["aiocqhttp:GroupMessage:123"]
    assert len(conv_mgr._content[cid]) == 1


@pytest.mark.asyncio
async def test_sync_falls_back_to_session_key_when_no_mapping() -> None:
    """映射还没建立（比如同步先于 request 主流程跑到）时，退化用 session_key
    自己当 key——好过完全不同步；行为应与旧代码在无映射时一致。
    """
    p, conv_mgr = _plugin("占位")
    # 故意不调用 p._store.session_origins.set(...)

    await p._sync_message_to_conv_mgr("no_mapping_session", "user", "有人在吗")

    assert "no_mapping_session" in conv_mgr._curr_ids
    cid = conv_mgr._curr_ids["no_mapping_session"]
    assert len(conv_mgr._content[cid]) == 1


@pytest.mark.asyncio
async def test_history_json_string_roundtrip_appends_not_explodes() -> None:
    """回归 BLOCKER 缺陷 (2)：history 以 JSON 字符串往返时（真实框架形状），
    第二次同步必须正确 append 成两条记录，而不是把字符串拆成单字符列表。
    """
    p, conv_mgr = _plugin("占位")
    p._store.session_origins.set("u1", "test:u1")

    await p._sync_message_to_conv_mgr("u1", "user", "第一句")
    await p._sync_message_to_conv_mgr("u1", "bot", "第二句回复")

    cid = conv_mgr._curr_ids["test:u1"]
    history = conv_mgr._content[cid]
    assert len(history) == 2, f"两条消息应恰好 append 两次，不应被字符串炸开：{history}"
    assert _role_of(history[0]) == "user"
    assert _content_of(history[0]) == "第一句"
    assert _role_of(history[1]) in ("assistant", "bot")
    assert _content_of(history[1]) == "第二句回复"


def _role_of(entry: object) -> str:
    if isinstance(entry, dict):
        return str(entry.get("role", ""))
    return str(getattr(entry, "role", ""))


def _content_of(entry: object) -> str:
    """修复后 _do_sync_to_conv_mgr 在 append 前总是对 AstrBot 消息类型调用
    model_dump()，因此历史条目现在保证是普通 dict（不再是裸 pydantic 对象）。
    dict 形态下 content 字段可能是字符串，也可能是 [{"type": "text", "text": ...}]
    这种分段列表（TextPart.model_dump() 的形状），两种都兼容取出。
    """
    content = entry.get("content") if isinstance(entry, dict) else None
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and "text" in part:
                return str(part["text"])
        return ""
    return str(content or "")
