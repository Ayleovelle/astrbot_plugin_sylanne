"""fix/context-integrity round-3 复审：conv_mgr bot 同步的最终原则，以及
_do_sync_to_conv_mgr 幂等守卫在读写交错时的语义。

背景（round-2 → round-3 doctrine 修正，adjudicated 结论见 PR 描述）：641ae74 把
_do_sync_to_conv_mgr 从"看似生效实际 no-op / 写坏数据"修成"真的会写"，副作用是
让插件自己的 bot 侧 conv_mgr 同步跟 AstrBot 框架自己的 _save_to_history（在
on_llm_response 钩子返回后，用 agent_runner.run_context.messages 对同一个
conv_mgr.update_conversation 做一次全量覆盖写）产生真实的并发写竞态：
  - 我们的读发生在框架写之前 → 用陈旧快照覆盖掉框架刚写的 tool_calls / 多模态 /
    checkpoint 记录；
  - 我们的读发生在框架写之后 → 把同一句话重复 append 成连续两条 assistant 记录
    （已知 Gemini 连续 assistant turn 结构雷区）。

round-2 曾经的结论：只有【非拦截分支】需要 skip_conv_sync=True，【拦截/分段发送
分支】是插件唯一的历史写入者、应该继续同步。round-3 adjudicated 判定这个区分
不成立——框架源码显示 _save_to_history 的落库条件只看两件事：completion_text 是
否非空、事件是否被 event.stop_event() 终止，完全不区分调用方走的是拦截分支还是
非拦截分支。拦截/分段发送分支在 llm_response_pipeline.py 里同样保留了
response.completion_text（供 AstrBot 记录用）且从未 stop 事件，所以框架同样会
对这条分支的正常回复做一次全量覆盖写。

最终原则（doctrine）：框架是【每一个 completion_text 非空且事件未被 stop 的
turn】的权威历史写入者。插件自己的 bot 侧 conv_mgr 同步只应该存在于【框架确定
不会保存】的路径上。截至本轮，_append_bot_reply_buffer 的两个调用点（非拦截
分支 / 拦截-分段发送分支经 _background_observe_response）都满足"框架会保存"，
因此都显式传 skip_conv_sync=True——conv_mgr 同步这条支路目前是死代码，只等一个
真正符合"框架确定不保存"条件的未来调用点（详见
llm_response_pipeline.py::_append_bot_reply_buffer 的 docstring）。

两道防线：
  ① llm_response_pipeline.py 的两个调用点都显式传 skip_conv_sync=True——从源头
     不产生这次并发写。
  ② state_persistence.py::_do_sync_to_conv_mgr 保留一道幂等守卫（防御性纵深，
     供未来真正的"框架不保存"调用点使用）：append 前若末条历史（跳过尾随的
     checkpoint/system/tool 记录后）已经是同 role+content，直接跳过（不追加、
     不写回）。

已知残留问题（不在本卡范围，留给专门的历史补丁工作项）：框架 _save_to_history
落库的是 hook 前的原始 completion_text，插件实际发给用户的是清理后
（strip_draft_blocks/_sanitize_response）的 cleaned 文本，两者签名不一致，是
独立于本卡的"发送内容≠保存内容"缺陷。

本文件钉死：
  1. 非拦截分支正常（非空）回复不触发插件自己的 conv_mgr bot 同步。
  2. 拦截 / 分段发送分支正常回复【同样】不触发（round-3 doctrine 修正的回归
     锁——防止未来重构把这条路径的 skip_conv_sync 又误改回 False）。
  3. 组合回归：同一会话里先 SILENT 后普通非拦截 SPEAK，两轮都不应产生插件自己
     的 conv_mgr bot 写入，用户消息（request 阶段已同步）应完整保留。
  4. _do_sync_to_conv_mgr 幂等守卫：模拟"框架的全量覆盖写恰好插在我们的读之后"
     这一时序——读到的末条已经是这次要同步的同一条 assistant 记录，守卫应跳过
     重复 append，框架那次写（这里用只有框架才会写的 tool_calls 字段代表"更全"
     的内容）原样保留，不被我们的写回吞掉；同时确认内容不同的普通 append 不受
     误伤（不会把守卫做成"完全不追加"的死锁）。
  5. round-2 MINOR 修复回归锁：末条历史若是框架追加的尾随 CheckpointMessageSegment
     （role="_checkpoint"），守卫应扫过它找到真正的最后一条 assistant 消息来比较，
     而不是被 history[-1] 的 checkpoint 记录挡住导致漏检真实重复。
  6. round-4 adjudicated 修复回归锁：history 字段本身是损坏的 JSON 字符串（或
     解析结果不是 list）时，_extract_conv_history_list 必须 fail-closed 返回
     None，_do_sync_to_conv_mgr 必须整体跳过本次同步（绝不调用
     update_conversation）——旧实现遇到这种情况会静默退化成 `[]`，调用方随后
     append 新消息再整体写回，等价于用只含一条新消息的历史覆盖写回，把损坏
     之外原本可能仍然完好的历史数据一并摧毁。
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import types
from types import SimpleNamespace

import pytest

from sylanne_alpha.llm_response_pipeline import LLMResponsePipeline
from sylanne_alpha.rhythm_learner import RhythmLearner
from sylanne_alpha.session_state_store import SessionStateStore
from sylanne_alpha.state_persistence import StatePersistence


class _Resp:
    def __init__(self, t: str) -> None:
        self.completion_text = t


class _Ev:
    unified_msg_origin = "sess:convrace"

    def __init__(self) -> None:
        self._extras: dict[str, object] = {}

    def set_extra(self, key: str, value: object) -> None:
        self._extras[key] = value

    def get_extra(self, key: str, default: object = None) -> object:
        return self._extras.get(key, default)


class _FakeEngine:
    def expression_drive(self) -> float:
        return 0.5


class _FakeComputation:
    def __init__(self) -> None:
        self.engine = _FakeEngine()


class _FakeKernel:
    def __init__(self) -> None:
        self.computation = _FakeComputation()


class _FakeHost:
    def __init__(self) -> None:
        self.kernel = _FakeKernel()


async def _noop() -> None:
    return None


class _BasePlugin:
    """两个调用点（非拦截 / 拦截）共用的最小插件桩：conv_mgr "存在"，记录每次
    bot 侧同步调用的 (session_key, role, text)。"""

    def __init__(self, root: str, config: dict) -> None:
        self._config = config
        self._store = SessionStateStore()
        self._background_tasks: list = []
        self._root = root
        self._rhythm_learner = RhythmLearner(intimacy_threshold=0.6)
        self.conv_sync_calls: list[tuple[str, str, str]] = []

    def _session_key(self, _e: object) -> str:
        return "sess:convrace"

    def _host(self, _sk: str) -> _FakeHost:
        return _FakeHost()

    def _schedule_buffer_persist(self, _sk: str) -> None:
        pass

    def _has_conversation_manager(self) -> bool:
        return True

    async def _sync_message_to_conv_mgr(
        self, session_key: str, role: str, text: str
    ) -> None:
        self.conv_sync_calls.append((session_key, role, text))

    async def observe_response(self, *args: object, **kwargs: object) -> None:
        return None


def _run(pipe: LLMResponsePipeline, resp: _Resp, plugin: _BasePlugin) -> None:
    async def go() -> None:
        await pipe._on_llm_response_inner(_Ev(), resp)
        if plugin._background_tasks:
            await asyncio.gather(*plugin._background_tasks)
        # _append_bot_reply_buffer 内部对 conv_mgr 的同步是【未追踪】的 fire-and-
        # forget task（safe_ensure_future 没传 task_list）——多让出几次事件循环，
        # 确保它在断言前有机会跑完（如果它确实被调度了的话）。
        for _ in range(5):
            await asyncio.sleep(0)

    asyncio.run(go())


def test_non_intercept_normal_reply_skips_conv_mgr_bot_sync() -> None:
    """非拦截分支（现网默认配置就走这条）：正常非空回复不应触发插件自己的
    conv_mgr bot 同步——框架自己的 _save_to_history 才是这条路径唯一权威的历史
    写入者，两个写入者并发写同一份历史必出问题（clobber 或重复）。"""
    p = _BasePlugin(
        tempfile.mkdtemp(prefix="convrace_ni_"),
        {
            "sylanne_alpha_realtime_chat_enabled": False,
            "sylanne_alpha_realtime_intercept_llm_response": False,
        },
    )
    pipe = LLMResponsePipeline(p)  # type: ignore[arg-type]
    resp = _Resp("今天天气不错")

    _run(pipe, resp, p)

    assert resp.completion_text == "今天天气不错"
    assert p.conv_sync_calls == [], (
        "非拦截分支正常回复不应触发插件自己的 conv_mgr bot 同步"
    )
    buf = p._store.conversation_buffers.get("sess:convrace")
    assert buf is not None and any(m.get("role") == "bot" for m in buf.messages), (
        "跳过的只是 conv_mgr 同步这一步，conversation_buffers 仍应照常写入"
    )


def test_intercept_segmented_reply_also_skips_conv_mgr_bot_sync() -> None:
    """拦截 / 分段发送分支：round-3 doctrine 修正——round-2 曾以为这条路径是
    插件唯一的历史写入者而保留同步，但框架的 _save_to_history 不区分拦截/非
    拦截分支，这条分支的 completion_text 同样被保留（供框架记录用）且事件同样
    从未被 stop，框架一样会做一次全量覆盖写。故这条路径现在也必须
    skip_conv_sync=True——回归锁，防止未来重构把这里误改回 False，重新引入
    round-2 BLOCKER 那种并发写竞态。"""
    p = _BasePlugin(
        tempfile.mkdtemp(prefix="convrace_ic_"),
        {
            "sylanne_alpha_realtime_chat_enabled": True,
            "sylanne_alpha_realtime_intercept_llm_response": True,
        },
    )
    pipe = LLMResponsePipeline(p)  # type: ignore[arg-type]
    # 不关心真实分段发送/打字节奏（与本卡无关的下游机制），隔离掉；
    # _background_observe_response（走 _append_bot_reply_buffer）保持真实执行。
    pipe._dispatch_segmented_parts = types.MethodType(  # type: ignore[method-assign]
        lambda self, *a, **kw: _noop(), pipe
    )
    resp = _Resp("今天天气不错，我们出去走走吧")

    _run(pipe, resp, p)

    assert resp.completion_text == "今天天气不错，我们出去走走吧"
    assert p.conv_sync_calls == [], (
        "拦截/分段发送分支正常回复也不应再触发插件自己的 conv_mgr bot 同步"
    )
    buf = p._store.conversation_buffers.get("sess:convrace")
    assert buf is None, (
        "模型草稿不能在 transport 结算前写入 conversation_buffers；"
        "真实送达后的写入由 on_agent_done delivery ledger 负责"
    )


@pytest.mark.asyncio
async def test_silent_turn_then_normal_turn_both_avoid_plugin_bot_sync() -> None:
    """组合回归：同一会话里，先来一轮 SILENT（收口层补写产出 user，2.4.1 起写入
    职责搬到响应期收口层——见 v241 最终实现计划 STEP2/3），再来一轮普通非拦截
    SPEAK 回复——两轮都不应触发插件自己对 conv_mgr 的 bot 侧写入；用户那句话应
    完整保留、不被任何一轮"顺手"修改或重复写。"""
    from main import EmotionalStatePlugin
    from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost
    from sylanne_alpha.v2core.contracts import Reply, ReplyKind
    from sylanne_alpha.v2core.integration import apply_v2core_response

    conv_sync_calls: list[tuple[str, str, str]] = []

    class _Plugin:
        _framework_will_persist_this_turn = (
            EmotionalStatePlugin._framework_will_persist_this_turn
        )
        _agent_was_aborted = EmotionalStatePlugin._agent_was_aborted
        _backfill_user_if_framework_skips = (
            EmotionalStatePlugin._backfill_user_if_framework_skips
        )

        def __init__(self, root: str) -> None:
            self._config = {
                "sylanne_enable_v2core": True,
                "sylanne_alpha_realtime_chat_enabled": False,
                "sylanne_alpha_realtime_intercept_llm_response": False,
            }
            self._root = root
            self._hosts: dict[str, SylanneAlphaHost] = {}
            self._store = SessionStateStore()
            self._background_tasks: list = []
            self._llm_response_pipeline = LLMResponsePipeline(self)  # type: ignore[arg-type]

        def _session_key(self, _e: object) -> str:
            return "u1"

        def _text(self, _e: object) -> str:
            return "在干嘛呢"

        def _host(self, sk: str) -> SylanneAlphaHost:
            if sk not in self._hosts:
                self._hosts[sk] = SylanneAlphaHost(root=self._root, session_key=sk)
            return self._hosts[sk]

        def _has_conversation_manager(self) -> bool:
            return True

        def _schedule_buffer_persist(self, _sk: str) -> None:
            pass

        async def _sync_message_to_conv_mgr(
            self, session_key: str, role: str, text: str
        ) -> None:
            conv_sync_calls.append((session_key, role, text))

        async def observe_response(self, *args: object, **kwargs: object) -> None:
            return None

    class _ReqStub:
        """最小 provider_request 桩：有 conversation，无 tool_calls_result——供
        _framework_will_persist_this_turn 判据读取（getattr 防御，缺失字段按对应
        分支处理）。"""

        conversation = object()
        tool_calls_result = None

    class _Event:
        unified_msg_origin = "test:u1"

        def get_extra(self, key: str, default=None):
            if key == "provider_request":
                return _ReqStub()
            return default

        def is_stopped(self) -> bool:
            return False

    p = _Plugin(tempfile.mkdtemp(prefix="convrace_combo_"))
    pipe = p._llm_response_pipeline

    # --- 第一轮：SILENT（收口层补写恰好一次，产出 user）---
    warmup = _Resp("warmup")
    await apply_v2core_response(p, _Event(), warmup)
    rt = p._v2core_runtimes["u1"]
    rt["runner"].run_decision_stage = lambda *a, **k: Reply(  # type: ignore[method-assign]
        kind=ReplyKind.SILENT, meta={"reason": "test_forced_silent"}
    )
    resp1 = _Resp("draft the model produced")
    silent_event = _Event()
    took = await apply_v2core_response(p, silent_event, resp1)
    assert took is True
    assert resp1.completion_text == ""
    # main.py::_on_llm_response_inner 的 finally 在此处调用补写；框架因
    # completion 空本轮不落库，补写是该轮唯一 user 写者。
    await p._backfill_user_if_framework_skips(silent_event, resp1)
    assert conv_sync_calls == [("u1", "user", "在干嘛呢")], (
        "SILENT 轮由收口补写恰好一次（写入职责已从请求期搬到响应期收口层）"
    )

    # --- 第二轮：普通非拦截 SPEAK 回复（等价于 main.py 里 apply_v2core_response
    # 对 SPEAK/FALLBACK 返回 False、落入 legacy _llm_response_pipeline 的路径）---
    resp2 = _Resp("在写代码呢")
    await pipe._on_llm_response_inner(_Event(), resp2)
    if p._background_tasks:
        await asyncio.gather(*p._background_tasks)
    for _ in range(5):
        await asyncio.sleep(0)

    assert resp2.completion_text == "在写代码呢"
    assert conv_sync_calls == [("u1", "user", "在干嘛呢")], (
        "普通非拦截回复轮不应追加任何插件自己的 conv_mgr bot 同步调用——"
        "框架自己的 _save_to_history 才是这条路径唯一权威的历史写入者"
    )


# ===========================================================================
# state_persistence.py::_do_sync_to_conv_mgr 幂等守卫
# ===========================================================================


class _FrameworkInterleavingConvMgr:
    """模拟"我们的读，恰好发生在框架 _save_to_history 全量覆盖写之后"的时序。

    get_conversation 首次被调用时，先把框架那次全量覆盖写（这里用一个只有框架
    才会写的 tool_calls 占位字段代表"更全"的内容）灌进存储，再返回——这样调用
    方（_do_sync_to_conv_mgr）读到的历史末条，已经是这次要同步的同一句话（框架
    自己持久化的版本）。幂等守卫应识别出来并跳过，不覆盖掉框架那次写；
    update_conversation 被调用则代表守卫没有生效（用于断言"确实被跳过"）。
    """

    def __init__(self, framework_history: list[dict]) -> None:
        self._content: dict[str, list] = {}
        self._curr_ids: dict[str, str] = {}
        self._next_id = 1
        self._framework_history = framework_history
        self._framework_write_landed = False
        self.update_calls: list[list[dict]] = []

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
        if not self._framework_write_landed:
            self._content[cid] = list(self._framework_history)
            self._framework_write_landed = True
        history_json = json.dumps(self._content[cid], ensure_ascii=False)
        return SimpleNamespace(history=history_json)

    async def update_conversation(self, uid, cid, history=None, title=None):
        if cid not in self._content:
            return
        if history is not None:
            json.dumps(history, ensure_ascii=False)  # 校验可序列化性，模拟真实落库
            self.update_calls.append(history)
            self._content[cid] = history


@pytest.mark.asyncio
async def test_idempotence_guard_preserves_framework_write_on_interleaved_save() -> None:
    """幂等守卫核心场景：读恰好发生在框架全量覆盖写之后，守卫应跳过重复
    append/写回，框架那次写（含 tool_calls）原样保留、不被我们的写回覆盖。"""
    framework_history = [
        {"role": "user", "content": [{"type": "text", "text": "在干嘛"}]},
        {
            "role": "assistant",
            "content": [{"type": "text", "text": "在写代码呢"}],
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "noop"}}
            ],
        },
    ]
    conv_mgr = _FrameworkInterleavingConvMgr(framework_history)

    class _Plugin:
        def __init__(self) -> None:
            self._conv_mgr = conv_mgr
            self._store = SessionStateStore()

    p = _Plugin()
    sp = StatePersistence(p)  # type: ignore[arg-type]
    await conv_mgr.new_conversation("u1")

    # 我们要同步的这句话，恰好与框架已经落地的最后一条 assistant 消息完全相同
    # （两个写入者持久化的是同一轮结果，只是框架先落地了）。
    await sp.sync_message_to_conv_mgr("u1", "bot", "在写代码呢")

    cid = conv_mgr._curr_ids["u1"]
    assert conv_mgr._content[cid] == framework_history, (
        "幂等守卫应保留框架那次全量覆盖写（含 tool_calls）原样不动"
    )
    assert conv_mgr.update_calls == [], "命中幂等守卫时不应再调用 update_conversation"


@pytest.mark.asyncio
async def test_idempotence_guard_does_not_swallow_genuinely_different_content() -> None:
    """反向确认：守卫只在"末条完全同 role+content"时才跳过，内容不同的正常
    append 必须照常生效——不能把守卫做成"读到任何历史就不再写"的死锁。"""
    framework_history = [
        {"role": "user", "content": [{"type": "text", "text": "在干嘛"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "在摸鱼"}]},
    ]
    conv_mgr = _FrameworkInterleavingConvMgr(framework_history)

    class _Plugin:
        def __init__(self) -> None:
            self._conv_mgr = conv_mgr
            self._store = SessionStateStore()

    p = _Plugin()
    sp = StatePersistence(p)  # type: ignore[arg-type]
    await conv_mgr.new_conversation("u1")

    # 这次要追加的补刀文本与框架末条内容不同 → 不应被误杀
    await sp.sync_message_to_conv_mgr("u1", "bot", "开个玩笑啦")

    cid = conv_mgr._curr_ids["u1"]
    history = conv_mgr._content[cid]
    assert len(history) == 3, f"内容不同的正常 append 不应被幂等守卫误跳过：{history}"
    assert conv_mgr.update_calls, "内容不同时应正常调用 update_conversation"


@pytest.mark.asyncio
async def test_idempotence_guard_never_drops_a_genuinely_repeated_user_message() -> None:
    """对抗性自检发现的边界：幂等守卫按 (role, content) 判等，若不限定角色，
    用户连续两轮发完全相同的文字（中间那轮 bot 恰好 SILENT，没有任何 assistant
    记录夹在中间）会被误判成"重复"而丢掉第二条真实用户消息——这比守卫本来要防
    的竞态更容易踩中。2.4.1 起 user 同步搬到响应期收口层补写，补写是该轮唯一
    user 写者、无并发写，所以守卫必须只对 bot/assistant 侧生效，user 侧永远
    照常 append。"""
    conv_mgr = _FrameworkInterleavingConvMgr([{"role": "user", "content": "在吗"}])
    # 让 get_conversation 不做"框架交错写"模拟（这个测试只关心 user 侧不去重），
    # 直接标记为已落地，避免干扰。
    conv_mgr._framework_write_landed = True

    class _Plugin:
        def __init__(self) -> None:
            self._conv_mgr = conv_mgr
            self._store = SessionStateStore()

    p = _Plugin()
    sp = StatePersistence(p)  # type: ignore[arg-type]
    await conv_mgr.new_conversation("u1")

    # 两轮用户消息文字完全相同，中间没有任何 assistant 记录（模拟中间那轮 SILENT）。
    await sp.sync_message_to_conv_mgr("u1", "user", "在吗")
    await sp.sync_message_to_conv_mgr("u1", "user", "在吗")

    cid = conv_mgr._curr_ids["u1"]
    history = conv_mgr._content[cid]
    assert len(history) == 2, (
        f"用户连续两轮发相同文字都应被完整保留，不应被幂等守卫误删第二条：{history}"
    )


@pytest.mark.asyncio
async def test_idempotence_guard_skips_trailing_checkpoint_segment() -> None:
    """round-2 MINOR 回归锁：框架的 _save_to_history
    （AstrBot core/pipeline/.../internal.py:481-488）可能在 assistant 消息之后
    追加一条 CheckpointMessageSegment（role="_checkpoint"）。若守卫仍然硬编码
    history[-1]，读到的"末条"会是这条 checkpoint 记录而不是真正的 assistant
    消息，比较永远判"不同"，真实的重复写入会被漏检、照样重复 append。守卫必须
    跳过这类尾随的非对话记录，找到真正的最后一条 assistant 消息来比较。"""
    framework_history = [
        {"role": "user", "content": [{"type": "text", "text": "在干嘛"}]},
        {
            "role": "assistant",
            "content": [{"type": "text", "text": "在写代码呢"}],
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "noop"}}
            ],
        },
        # 框架在 assistant 消息之后追加的 checkpoint 尾巴（internal.py:483-488）。
        {"role": "_checkpoint", "content": {"id": "ckpt_1"}},
    ]
    conv_mgr = _FrameworkInterleavingConvMgr(framework_history)

    class _Plugin:
        def __init__(self) -> None:
            self._conv_mgr = conv_mgr
            self._store = SessionStateStore()

    p = _Plugin()
    sp = StatePersistence(p)  # type: ignore[arg-type]
    await conv_mgr.new_conversation("u1")

    # 这句要同步的 bot 文本，和框架已经落地的最后一条【真正】assistant 消息完全
    # 相同——中间隔着一条 checkpoint 尾巴，守卫应该跳过它识别出重复。
    await sp.sync_message_to_conv_mgr("u1", "bot", "在写代码呢")

    cid = conv_mgr._curr_ids["u1"]
    assert conv_mgr._content[cid] == framework_history, (
        "守卫应跳过尾随 checkpoint 记录识别出重复，原样保留框架那次写（含 "
        "tool_calls 与 checkpoint 尾巴），不追加出连续两条 assistant 记录"
    )
    assert conv_mgr.update_calls == [], "命中幂等守卫时不应再调用 update_conversation"


# ===========================================================================
# round-4 adjudicated：history 字段损坏时必须 fail-closed 整体跳过同步
# ===========================================================================


class _CorruptedHistoryConvMgr:
    """get_conversation() 返回损坏 JSON 字符串形态 history 的桩。

    用于验证 _extract_conv_history_list 遇到无法解析的 history 时 fail-closed
    返回 None，且 _do_sync_to_conv_mgr 整体放弃本次同步——不能退化成"当作空
    历史处理，append 新消息后整体写回"，那样等于用只含新消息的历史覆盖写回，
    静默摧毁损坏之外原本可能仍完好的历史数据。update_conversation 一旦被调用
    即代表 fail-closed 没生效。
    """

    def __init__(self, corrupted_history: str) -> None:
        self._content: dict[str, list] = {}
        self._curr_ids: dict[str, str] = {}
        self._next_id = 1
        self._corrupted_history = corrupted_history
        self.update_calls: list[list[dict]] = []

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
        return SimpleNamespace(history=self._corrupted_history)

    async def update_conversation(self, uid, cid, history=None, title=None):
        self.update_calls.append(history)
        if history is not None:
            self._content[cid] = history


@pytest.mark.asyncio
async def test_corrupted_json_history_skips_sync_never_calls_update() -> None:
    """回归 round-4 adjudicated finding①：history 字段是无法 json.loads 的损坏
    字符串时，同步必须整体跳过——不能调用 update_conversation 用只含新消息的
    重建历史覆盖写回。"""
    conv_mgr = _CorruptedHistoryConvMgr("{not valid json, corrupted]")

    class _Plugin:
        def __init__(self) -> None:
            self._conv_mgr = conv_mgr
            self._store = SessionStateStore()

    p = _Plugin()
    sp = StatePersistence(p)  # type: ignore[arg-type]

    await sp.sync_message_to_conv_mgr("u1", "user", "新消息")

    assert conv_mgr.update_calls == [], (
        "history JSON 损坏时必须 fail-closed 跳过整次同步，不能调用 "
        "update_conversation"
    )


@pytest.mark.asyncio
async def test_non_list_json_history_skips_sync_never_calls_update() -> None:
    """回归 round-4 adjudicated finding①的第二种损坏形状：history 字段是合法
    JSON 但解析结果不是 list（例如被写坏成一个 dict）——同样必须 fail-closed
    跳过，不能当作空历史处理再覆盖写回。"""
    conv_mgr = _CorruptedHistoryConvMgr(json.dumps({"not": "a list"}))

    class _Plugin:
        def __init__(self) -> None:
            self._conv_mgr = conv_mgr
            self._store = SessionStateStore()

    p = _Plugin()
    sp = StatePersistence(p)  # type: ignore[arg-type]

    await sp.sync_message_to_conv_mgr("u1", "bot", "新回复")

    assert conv_mgr.update_calls == [], (
        "history 解析结果不是 list 时同样必须 fail-closed，不能调用 "
        "update_conversation"
    )


def test_extract_conv_history_list_returns_none_on_corruption() -> None:
    """直接钉死 _extract_conv_history_list 的返回值契约：损坏输入 → None，
    合法的空历史（None / 空字符串）仍然 → []，不能一刀切都返回 []。"""
    from sylanne_alpha.state_persistence import StatePersistence as _SP

    assert _SP._extract_conv_history_list(None) == []
    assert _SP._extract_conv_history_list(SimpleNamespace(history=None)) == []
    assert _SP._extract_conv_history_list(SimpleNamespace(history="")) == []
    assert _SP._extract_conv_history_list(SimpleNamespace(history="   ")) == []
    assert _SP._extract_conv_history_list(SimpleNamespace(history=[1, 2])) == [1, 2]

    # 损坏形状：一律 None，绝不能悄悄退化成 []
    assert _SP._extract_conv_history_list(SimpleNamespace(history="{bad json")) is None
    assert (
        _SP._extract_conv_history_list(SimpleNamespace(history=json.dumps({"a": 1})))
        is None
    )
    assert _SP._extract_conv_history_list(SimpleNamespace(history=42)) is None
