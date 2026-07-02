"""fix/context-integrity round-2 复审：conv_mgr bot 同步"跳过 vs 保留"两个调用点
的行为钉死，以及 _do_sync_to_conv_mgr 幂等守卫在读写交错时的语义。

背景（round-2 MAJOR，adjudicated 结论见 PR 描述）：641ae74 把 _do_sync_to_conv_mgr
从"看似生效实际 no-op / 写坏数据"修成"真的会写"，副作用是【非拦截默认路径】
（llm_response_pipeline.py 里 `if not realtime_enabled or not intercept:` 分支，
现网默认配置就走这条）的 response-phase bot 同步现在会跟 AstrBot 框架自己的
_save_to_history（在 on_llm_response 钩子返回后，用 agent_runner.run_context.
messages 对同一个 conv_mgr.update_conversation 做一次全量覆盖写）产生真实的并发
写竞态：
  - 我们的读发生在框架写之前 → 用陈旧快照覆盖掉框架刚写的 tool_calls / 多模态 /
    checkpoint 记录；
  - 我们的读发生在框架写之后 → 把同一句话重复 append 成连续两条 assistant 记录
    （已知 Gemini 连续 assistant turn 结构雷区）。

两道防线：
  ① llm_response_pipeline.py 非拦截分支调用 _append_bot_reply_buffer 时显式传
     skip_conv_sync=True——从源头不产生这次并发写（框架才是这条路径唯一权威的
     历史写入者）。拦截 / 分段发送分支（_background_observe_response 调用同一
     函数）不传这个 flag，继续照常同步——插件在那条路径上仍是唯一的历史写入者。
  ② state_persistence.py::_do_sync_to_conv_mgr 加一道幂等守卫：append 前若末条
     历史已经是同 role+content，直接跳过（不追加、不写回）——万一未来还有别的
     时序意外，这是廉价的第二道防线。

本文件钉死：
  1. 非拦截分支正常（非空）回复不再触发插件自己的 conv_mgr bot 同步。
  2. 拦截 / 分段发送分支正常回复仍然触发（"保留"语义不受影响的回归锁）。
  3. 组合回归：同一会话里先 SILENT 后普通非拦截 SPEAK，两轮都不应产生插件自己
     的 conv_mgr bot 写入，用户消息（request 阶段已同步）应完整保留。
  4. _do_sync_to_conv_mgr 幂等守卫：模拟"框架的全量覆盖写恰好插在我们的读之后"
     这一时序——读到的末条已经是这次要同步的同一条 assistant 记录，守卫应跳过
     重复 append，框架那次写（这里用只有框架才会写的 tool_calls 字段代表"更全"
     的内容）原样保留，不被我们的写回吞掉；同时确认内容不同的普通 append 不受
     误伤（不会把守卫做成"完全不追加"的死锁）。
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
    """非拦截分支（现网默认配置就走这条）：正常非空回复不应再触发插件自己的
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
        "非拦截分支正常回复不应再触发插件自己的 conv_mgr bot 同步"
    )
    buf = p._store.conversation_buffers.get("sess:convrace")
    assert buf is not None and any(m.get("role") == "bot" for m in buf.messages), (
        "跳过的只是 conv_mgr 同步这一步，conversation_buffers 仍应照常写入"
    )


def test_intercept_segmented_reply_still_syncs_bot_to_conv_mgr() -> None:
    """拦截 / 分段发送分支：插件是这条路径唯一的历史写入者，正常回复仍应触发
    conv_mgr bot 同步——回归锁，防止未来重构误把这条路径也一并 skip 掉。"""
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

    assert p.conv_sync_calls == [
        ("sess:convrace", "bot", "今天天气不错，我们出去走走吧")
    ], "拦截/分段发送分支应照常同步 bot 回复到 conv_mgr（保留语义未受影响）"


@pytest.mark.asyncio
async def test_silent_turn_then_normal_turn_both_avoid_plugin_bot_sync() -> None:
    """组合回归：同一会话里，先来一轮 SILENT（v2core 直接终结本轮，写入职责完全
    在 request 阶段），再来一轮普通非拦截 SPEAK 回复——两轮都不应触发插件自己对
    conv_mgr 的 bot 侧写入；用户那句话（request 阶段已同步）应完整保留、不被
    任何一轮"顺手"修改或重复写。"""
    from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost
    from sylanne_alpha.v2core.contracts import Reply, ReplyKind
    from sylanne_alpha.v2core.integration import apply_v2core_response

    conv_sync_calls: list[tuple[str, str, str]] = []

    class _Plugin:
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

    class _Event:
        unified_msg_origin = "test:u1"

    p = _Plugin(tempfile.mkdtemp(prefix="convrace_combo_"))
    pipe = p._llm_response_pipeline

    # --- 第一轮：SILENT（request 阶段已同步用户消息，response 阶段判为 SILENT）---
    await p._sync_message_to_conv_mgr("u1", "user", "在干嘛呢")
    warmup = _Resp("warmup")
    await apply_v2core_response(p, _Event(), warmup)
    rt = p._v2core_runtimes["u1"]
    rt["runner"].run_decision_stage = lambda *a, **k: Reply(  # type: ignore[method-assign]
        kind=ReplyKind.SILENT, meta={"reason": "test_forced_silent"}
    )
    resp1 = _Resp("draft the model produced")
    took = await apply_v2core_response(p, _Event(), resp1)
    assert took is True
    assert resp1.completion_text == ""
    assert conv_sync_calls == [("u1", "user", "在干嘛呢")], (
        "SILENT 轮本身不应产生任何额外 conv_mgr 写入（写入职责完全在 request 阶段）"
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
    的竞态更容易踩中。request 阶段的 user 同步发生在 LLM 调用之前，本来就不存在
    并发写，所以守卫必须只对 bot/assistant 侧生效，user 侧永远照常 append。"""
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
