"""2.4.1 跨锁双写回归哨——由 scratchpad/crosslock_repro.py 转化。

关键认知（转化时必须保留，勿反转）：crosslock_repro.py 的 Outcome A 直接调用
【原语】state_persistence.sync_message_to_conv_mgr(...,"user",...)，该原语本就
为 user 侧【永不去重】而设计（state_persistence.py:2489 对 user 豁免幂等守卫）
——原样跑这条原语，回归修复后仍然会产生 [P,u,b,u] 悬挂重复。所以不能在原语层
期望"红转绿"；真正的回归必须落在【调用者/编排层】——main.py 收口
_on_llm_response_inner 的 finally 里，只有 _framework_will_persist_this_turn
判定框架本轮会落库时才【不】调用这条原语，从源头不产生跨锁双写。

三个必需断言（对应 v241 最终实现计划验收门 #3）：
  1. Outcome A 根除：SPEAK 轮（completion 非空、有 conversation、未 stop、未
     abort）framework_save 先落 [P,u,b]，驱动 plugin._backfill_user_if_framework_skips
     -> 对 _sync_message_to_conv_mgr 零调用，最终 history 仍是 [P,u,b]（role 序列
     user,assistant,user,assistant；u_count==1；末条==b）——[P,u,b,u] 不再出现。
  2. SILENT 变体（never-lose-user）：SILENT 轮（completion 空、无 tool_res、未
     abort）framework 本轮不 save -> 补写写 1 条 user -> [P,u] 保住。
  3. Outcome B 附带根除：SPEAK 轮补写零写 -> 不存在"陈旧快照整表覆盖抹掉 b"这条
     竞态窗口 -> b 恒在。

原语层三场景（Normal/OutcomeA/OutcomeB）保留为 characterization（非门禁），
文档化"原语层 user 永不去重"这一前提——正是因为原语本身不设防，调用者才必须被
判据严格门控。
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from main import EmotionalStatePlugin
from sylanne_alpha.session_state_store import SessionStateStore
from sylanne_alpha.state_persistence import StatePersistence

# ---------------------------------------------------------------------------
# 常量与框架落库形状（对齐 crosslock_repro.py）
# ---------------------------------------------------------------------------

SESSION_KEY = "sess:aylovelle:2300184498"  # 插件内部 session_key
UMO = "aiocqhttp:FriendMessage:2300184508"  # 框架 unified_msg_origin（与 session_key 不同）
CID = "cid-uuid-1"
U_TEXT = "中午吃什么"
B_TEXT = "点外卖吧，我懒得动"


def user_dict(text: str) -> dict:
    return {"role": "user", "content": [{"type": "text", "text": text}]}


def asst_dict(text: str) -> dict:
    return {"role": "assistant", "content": [{"type": "text", "text": text}]}


P: list[dict] = [user_dict("早"), asst_dict("早呀，起这么早")]  # 先前上下文（prior turn）


def text_of(entry: dict) -> str:
    c = entry.get("content")
    if isinstance(c, list):
        return "".join(
            str(p.get("text") or "") for p in c if isinstance(p, dict) and "text" in p
        )
    return str(c or "")


def role_seq(content: list[dict]) -> list[str]:
    return [str(e.get("role", "?")) for e in content]


def u_count(content: list[dict]) -> int:
    return sum(1 for e in content if e.get("role") == "user" and text_of(e) == U_TEXT)


def b_present(content: list[dict]) -> bool:
    return any(text_of(e) == B_TEXT for e in content)


class FakeConvMgr:
    """框架 ConversationManager 的忠实最小仿造（同 crosslock_repro.py）。

    _content 是唯一真源（对应 ConversationV2.content）。get_conversation 返回的
    .history 是 JSON 字符串（对齐 conversation_mgr.py:_convert_conv_from_v2_to_v1），
    update_conversation 整行覆盖（对齐真码整表覆盖写语义）。
    """

    def __init__(self, initial: list[dict] | None = None) -> None:
        self._content: list[dict] = list(initial or [])
        self._umo_seen: set[str] = set()

    async def get_curr_conversation_id(self, umo: str) -> str:
        self._umo_seen.add(umo)
        return CID

    async def new_conversation(self, umo: str) -> str:
        self._umo_seen.add(umo)
        return CID

    async def get_conversation(self, umo, cid, create_if_not_exists: bool = False):
        self._umo_seen.add(umo)
        return SimpleNamespace(history=json.dumps(list(self._content), ensure_ascii=False))

    async def update_conversation(self, umo, cid=None, history=None, **kw) -> None:
        self._umo_seen.add(umo)
        self._content = list(history or [])


async def framework_save(mgr: FakeConvMgr, full_history: list[dict]) -> None:
    """仿框架 _save_to_history（internal.py:503-508）：整表覆盖写完整历史。"""
    await mgr.update_conversation(UMO, CID, history=list(full_history))


# ---------------------------------------------------------------------------
# 调用者层：main.py 真实收口方法 + 真实 state_persistence 原语（走真实锁/守卫）
# ---------------------------------------------------------------------------


class _ReqStub:
    def __init__(self, *, has_conversation: bool = True, tool_calls_result=None) -> None:
        self.conversation = object() if has_conversation else None
        self.tool_calls_result = tool_calls_result


class _Event:
    def __init__(self, *, req: _ReqStub, is_stopped: bool = False) -> None:
        self._req = req
        self._is_stopped = is_stopped
        self.unified_msg_origin = UMO

    def get_extra(self, key: str, default=None):
        if key == "provider_request":
            return self._req
        return default

    def is_stopped(self) -> bool:
        return self._is_stopped


class _Resp:
    def __init__(self, completion_text: str = "") -> None:
        self.completion_text = completion_text


class _RegressionPlugin:
    """驱动 main.py 真实 _backfill_user_if_framework_skips /
    _framework_will_persist_this_turn，写入路径走真实 StatePersistence 原语
    （非 call-spy）——回归必须在这一层（调用者层）证明，而不是在原语层。"""

    _framework_will_persist_this_turn = EmotionalStatePlugin._framework_will_persist_this_turn
    _backfill_user_if_framework_skips = EmotionalStatePlugin._backfill_user_if_framework_skips

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

    def _agent_was_aborted(self, _event) -> bool:
        return False

    async def _sync_message_to_conv_mgr(self, session_key: str, role: str, text: str) -> None:
        self.sync_calls.append((session_key, role, text))
        await self._state_persistence.sync_message_to_conv_mgr(session_key, role, text)


@pytest.mark.asyncio
async def test_speak_turn_backfill_zero_calls_no_dangling_user() -> None:
    """主断言①：SPEAK 轮，framework 先落 [P,u,b]，补写必须零调用——
    [P,u,b,u] 不再产生。"""
    mgr = FakeConvMgr(initial=list(P))
    p = _RegressionPlugin(mgr)

    await framework_save(mgr, P + [user_dict(U_TEXT), asst_dict(B_TEXT)])

    event = _Event(req=_ReqStub(has_conversation=True), is_stopped=False)
    resp = _Resp(B_TEXT)  # SPEAK：completion 非空

    await p._backfill_user_if_framework_skips(event, resp)

    assert p.sync_calls == [], (
        f"框架已判定本轮会落库（SPEAK），补写必须零调用，实际：{p.sync_calls!r}"
    )
    final = mgr._content
    assert role_seq(final) == ["user", "assistant", "user", "assistant"]
    assert u_count(final) == 1, f"不应出现悬挂重复 user，实际：{role_seq(final)}"
    assert text_of(final[-1]) == B_TEXT


@pytest.mark.asyncio
async def test_speak_turn_backfill_zero_calls_b_always_present() -> None:
    """主断言③（Outcome B 附带根除）：补写零写 -> 不存在陈旧快照整表覆盖抹掉 b
    的竞态窗口 -> b 恒在。"""
    mgr = FakeConvMgr(initial=list(P))
    p = _RegressionPlugin(mgr)

    await framework_save(mgr, P + [user_dict(U_TEXT), asst_dict(B_TEXT)])

    event = _Event(req=_ReqStub(has_conversation=True), is_stopped=False)
    resp = _Resp(B_TEXT)

    await p._backfill_user_if_framework_skips(event, resp)

    assert b_present(mgr._content), "补写不写库 -> b 不可能被陈旧快照覆盖写掉"


@pytest.mark.asyncio
async def test_silent_variant_never_loses_user() -> None:
    """主断言②：SILENT 轮，framework 本轮不 save，补写恰好写 1 条 user -> [P,u]。"""
    mgr = FakeConvMgr(initial=list(P))
    p = _RegressionPlugin(mgr)

    event = _Event(req=_ReqStub(has_conversation=True), is_stopped=False)
    resp = _Resp("")  # SILENT：completion 空、无 tool_calls_result、未 abort

    await p._backfill_user_if_framework_skips(event, resp)

    assert p.sync_calls == [(SESSION_KEY, "user", U_TEXT)]
    final = mgr._content
    assert role_seq(final) == ["user", "assistant", "user"]
    assert u_count(final) == 1
    assert not b_present(final), "SILENT 轮framework不写，不应凭空出现 b"


@pytest.mark.asyncio
async def test_regression_would_fail_with_old_unconditional_leg3_write() -> None:
    """对照跑（临时保留 leg-3 无条件写的旧编排）：验证本断言确实是真回归哨——
    若插件在 SPEAK 轮无条件（不经判据）写 user，[P,u,b,u] 就会重现。"""
    mgr = FakeConvMgr(initial=list(P))
    p = _RegressionPlugin(mgr)

    await framework_save(mgr, P + [user_dict(U_TEXT), asst_dict(B_TEXT)])

    # 模拟旧 leg-3：不经 _framework_will_persist_this_turn 判据，直接无条件同步。
    await p._sync_message_to_conv_mgr(SESSION_KEY, "user", U_TEXT)

    final = mgr._content
    roles = role_seq(final)
    assert roles == ["user", "assistant", "user", "assistant", "user"], (
        "旧 leg-3 无条件写重现 [P,u,b,u] 悬挂重复，证明判据门控是必需的、"
        "不是可有可无的锦上添花"
    )
    assert u_count(final) == 2


# ---------------------------------------------------------------------------
# 原语层三场景（characterization，非门禁）：user 永不去重是既有设计，
# 说明为何回归必须落在调用者层而非原语层。
# ---------------------------------------------------------------------------


def build_primitive_instance(mgr: FakeConvMgr) -> StatePersistence:
    lock_pool: dict[str, asyncio.Lock] = {}

    def get_conv_sync_lock(session_key: str) -> asyncio.Lock:
        return lock_pool.setdefault(session_key, asyncio.Lock())

    store = SimpleNamespace()
    store.session_origins = {SESSION_KEY: UMO}
    store.get_conv_sync_lock = get_conv_sync_lock

    plugin = SimpleNamespace(_conv_mgr=mgr, _store=store)
    return StatePersistence(plugin)


@pytest.mark.asyncio
async def test_characterization_primitive_normal_leg3_first() -> None:
    """characterization：原语层，leg-3 先写、框架后整表覆盖 -> [P,u,b]，无重复。"""
    mgr = FakeConvMgr(initial=list(P))
    inst = build_primitive_instance(mgr)

    await inst.sync_message_to_conv_mgr(SESSION_KEY, "user", U_TEXT)
    await framework_save(mgr, P + [user_dict(U_TEXT), asst_dict(B_TEXT)])

    final = mgr._content
    assert role_seq(final) == ["user", "assistant", "user", "assistant"]
    assert u_count(final) == 1
    assert text_of(final[-1]) == B_TEXT


@pytest.mark.asyncio
async def test_characterization_primitive_outcome_a_user_never_deduped() -> None:
    """characterization：原语层，框架先写、leg-3 后读后写（role=user）——守卫
    :2489 对 user 不设防，原样穿透产生 [P,u,b,u]。这正是本文件主断言要在调用者
    层根除的悬挂重复，原语本身【不会】、也【不该】自己去重（去重会误伤真实的
    连续两条相同用户消息，见 test_conv_mgr_sync_race.py 的 never-drop 回归锁）。"""
    mgr = FakeConvMgr(initial=list(P))
    inst = build_primitive_instance(mgr)

    await framework_save(mgr, P + [user_dict(U_TEXT), asst_dict(B_TEXT)])
    await inst.sync_message_to_conv_mgr(SESSION_KEY, "user", U_TEXT)

    final = mgr._content
    assert role_seq(final) == ["user", "assistant", "user", "assistant", "user"]
    assert u_count(final) == 2
    assert final[-1].get("role") == "user"
    assert text_of(final[-1]) == U_TEXT
    assert b_present(final)


@pytest.mark.asyncio
async def test_characterization_primitive_outcome_b_stale_snapshot_overwrite() -> None:
    """characterization：原语层，若插件的读发生在框架写之前、写回发生在框架写
    之后（陈旧快照整表覆盖），b 会被抹掉——这是本文件主断言③在调用者层要根除的
    另一半（补写零写从源头消灭这个时序窗口）。"""
    mgr = FakeConvMgr(initial=list(P))
    inst = build_primitive_instance(mgr)

    async def frame_write_between_read_and_write() -> None:
        await framework_save(mgr, P + [user_dict(U_TEXT), asst_dict(B_TEXT)])

    orig_get = mgr.get_conversation
    hook_fired = False

    async def get_with_hook(umo, cid, create_if_not_exists: bool = False):
        nonlocal hook_fired
        snap = await orig_get(umo, cid, create_if_not_exists)
        if not hook_fired:
            hook_fired = True
            await frame_write_between_read_and_write()
        return snap

    mgr.get_conversation = get_with_hook  # type: ignore[method-assign]

    await inst.sync_message_to_conv_mgr(SESSION_KEY, "user", U_TEXT)

    final = mgr._content
    assert role_seq(final) == ["user", "assistant", "user"]
    assert not b_present(final), "陈旧快照写回抹掉了框架刚落库的 b（lost update）"
    assert u_count(final) == 1
