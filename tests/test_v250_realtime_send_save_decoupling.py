"""2.5.0 基调③ realtime 完整重做（Model-D）：send/save 解耦回归锁。

覆盖设计文档 M1-M4 + 次要修复①②，以及默认路径零回归红线闸：

  M1  非 Plain（图片/语音）保全：result_chain 含非 Plain 组件时，
      on_llm_response 彻底放弃接管——不碰 completion_text/result_chain，
      不置接管旗标，不分段调度。
  M2  历史真落库：不再清空 result_chain/chain，completion_text 保持非空
      （框架 SAVE-GATE 读的正是这个字段），result_chain 对象身份不被置 None。
  M3  跨 provider 不双发：result_chain 档（Gemini/OpenAI 形态）与
      _completion_text 档（Anthropic 形态）都先登记候选，不立即发送；
      on_decorating_result 看过最终 chain 后才提交文本接管并启动分段。
  M4  流式不双发：on_llm_response 入口检测 event.get_result().
      result_content_type == STREAMING_RESULT 时彻底放弃接管；请求侧
      do_first 门补 realtime_enabled，与响应侧对齐。
  次要①：_stream_first_do_first 三个开关都为真才抢发。
  次要②：realtime_flags 正规键/旧别名任一为真即算开启，两侧口径统一。

  main.py 侧：on_message 强制关流（M4a）+ on_decorating_result 的
  _maybe_suppress_realtime_takeover（M1-M3 发送抑制的落地点）。

本文件全部使用真实 astrbot.core.provider.entities.LLMResponse /
astrbot.core.message.message_event_result.MessageChain / astrbot.core.
message.components，精确复现框架 completion_text getter/setter 的真实
坍缩行为（不是自造模型），与设计文档里对框架源码的引用逐条对应。
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import tempfile
import types
from types import SimpleNamespace

import pytest

astrbot_entities = pytest.importorskip("astrbot.core.provider.entities")
astrbot_result = pytest.importorskip("astrbot.core.message.message_event_result")
astrbot_components = pytest.importorskip("astrbot.core.message.components")

LLMResponse = astrbot_entities.LLMResponse
MessageChain = astrbot_result.MessageChain
ResultContentType = astrbot_result.ResultContentType
Plain = astrbot_components.Plain
Record = astrbot_components.Record

from main import EmotionalStatePlugin
from sylanne_alpha import transient_context
from sylanne_alpha.delivery_ledger import SegmentedDeliveryTurn
from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline
from sylanne_alpha.llm_response_pipeline import LLMResponsePipeline
from sylanne_alpha.message_dispatch import realtime_flags
from sylanne_alpha.rhythm_learner import RhythmLearner
from sylanne_alpha.scope_contracts import ResolvedScope, ResolvedTransportScope
from sylanne_alpha.scope_identity import PersonaSource, ScopeResolver
from sylanne_alpha.scope_runtime import ScopeRuntimeRegistry
from sylanne_alpha.semantic_segmentation import (
    PauseClass,
    SEMANTIC_BEAT_NONCE_EXTRA,
    build_marker,
)
from sylanne_alpha.session_state_store import SessionStateStore
from tests.scope_fixtures import scopes as build_scopes


# ===========================================================================
# 共用桩件（沿用 tests/test_conv_mgr_sync_race.py 的最小插件桩写法）
# ===========================================================================


class _FrameworkTextPart:
    def __init__(self, text: str) -> None:
        self.text = text
        self._no_save = False

    def mark_as_temp(self) -> "_FrameworkTextPart":
        self._no_save = True
        return self


def _issued_view(registry: ScopeRuntimeRegistry):
    scope = build_scopes.__wrapped__().bot_a_persona_a
    return registry.issue_request_view(
        ResolvedScope(
            scope=scope,
            persona_source=PersonaSource(
                persona_id="v250-semantic-fixture",
                prompt="static persona",
                begin_dialogs=(),
                tools=None,
                skills=None,
                resolution_source="test",
            ),
            identity_quality="event_self_id",
            resolution_source="test",
            resolved_at_ms=1,
            private_scope_enabled=True,
            disabled_reason=None,
            turn_generation=1,
        ),
        subject=None,
        relation_runtime=None,
    )


def _bound_semantic_sink(monkeypatch):
    monkeypatch.setattr(transient_context, "_make_text_part", _FrameworkTextPart)
    registry = ScopeRuntimeRegistry.for_test()
    view = _issued_view(registry)
    return registry, view, view.transient_context_sink


class _FakeEngine:
    def expression_drive(self) -> float:
        return 0.5

    def observe(self) -> dict:
        return {"arousal": 0.5, "tension": 0.0}


class _FakeSocialVoid:
    def reset(self) -> None:
        pass


class _FakeComputation:
    def __init__(self) -> None:
        self.engine = _FakeEngine()
        self.engine.social_void = _FakeSocialVoid()  # type: ignore[attr-defined]


class _FakeMortality:
    exhaustion = 0.5


class _FakeBody:
    def __init__(self) -> None:
        self.mortality = _FakeMortality()


class _FakeKernel:
    def __init__(self) -> None:
        self.computation = _FakeComputation()
        self.body = _FakeBody()
        self.previous_event = {"now": 0.0}


class _FakeHost:
    def __init__(self) -> None:
        self.kernel = _FakeKernel()


class _Ev:
    """最小事件桩：跟真事件一样支持 get_result/set_extra/get_extra，
    生产事件（aiocqhttp 等）也是这三个方法，无裸属性——符合测试事件形态约束。
    """

    def __init__(self, result: object | None = None) -> None:
        self.unified_msg_origin = "sess:realtime-decouple"
        self._extras: dict = {}
        self._result = result

    def set_extra(self, key: str, value: object) -> None:
        self._extras[key] = value

    def get_extra(self, key: str, default: object = None) -> object:
        return self._extras.get(key, default)

    def get_result(self) -> object | None:
        return self._result


class _ScopeSession:
    platform_id = "adapter"
    session_id = "42"

    def __str__(self) -> str:
        return "adapter:FriendMessage:42"


class _ScopedEv(_Ev):
    """Minimal real-shape transport event for scope-gated on_message tests."""

    def __init__(self, *, set_calls: list | None = None) -> None:
        super().__init__()
        self.unified_msg_origin = "adapter:FriendMessage:42"
        self.session_id = "42"
        self.session = _ScopeSession()
        self.message_obj = SimpleNamespace(message_id="msg-next")
        self._set_calls = set_calls

    def get_platform_id(self) -> str:
        return "adapter"

    def get_platform_name(self) -> str:
        return "aiocqhttp"

    def get_self_id(self) -> str:
        return "10001"

    def set_extra(self, key: str, value: object) -> None:
        if self._set_calls is not None:
            self._set_calls.append((key, value))
        super().set_extra(key, value)


def _scope_resolver(root: object) -> ScopeResolver:
    context = SimpleNamespace(
        get_config=lambda *, umo: {"provider_settings": {}},
        persona_manager=SimpleNamespace(resolve_selected_persona=None),
    )
    return ScopeResolver.for_test(context, root=root)


class _Plugin:
    """intercept 分支完整跑通所需的最小插件桩（含 rhythm_learner/host）。"""

    def __init__(self, root: str, config: dict) -> None:
        self._config = config
        self._store = SessionStateStore()
        self._background_tasks: list = []
        self._root = root
        self._rhythm_learner = RhythmLearner(intimacy_threshold=0.6)

    def _session_key(self, _e: object) -> str:
        return "sess:realtime-decouple"

    def _host(self, _sk: str) -> _FakeHost:
        return _FakeHost()

    def _schedule_buffer_persist(self, _sk: str) -> None:
        pass

    def _has_conversation_manager(self) -> bool:
        return False

    async def observe_response(self, *args: object, **kwargs: object) -> None:
        return None


class _ReactiveContext:
    def __init__(self) -> None:
        self.sent: list[tuple[str, object]] = []

    async def send_message(self, origin: str, message: object) -> None:
        self.sent.append((origin, message))


class _RawSendEvent(_Ev):
    def __init__(self, *, request_view: object | None = None, after_send=None) -> None:
        super().__init__()
        if request_view is not None:
            self.set_extra("_sylanne_runtime_view_v1", request_view)
        self.after_send = after_send
        self.sent: list[tuple[str, str]] = []

    def plain_result(self, text: str) -> tuple[str, str]:
        return ("event-plain", text)

    async def send(self, result: object) -> None:
        assert isinstance(result, tuple)
        self.sent.append(result)
        if self.after_send is not None:
            self.after_send()


class _V3Recorder:
    def __init__(self) -> None:
        self.settled: list[dict[str, object]] = []

    def pending_token(self, _session_key: str) -> int:
        return 17

    def settle(self, **kwargs: object) -> None:
        self.settled.append(kwargs)


class _ReactivePlugin(_Plugin):
    def __init__(self, root: str, config: dict) -> None:
        super().__init__(root, config)
        self.context = _ReactiveContext()
        self._scope_runtime_registry = ScopeRuntimeRegistry.for_test()
        self.request_view = _issued_view(self._scope_runtime_registry)
        scope = self.request_view.resolved.scope
        assert scope is not None
        self._runtime_binding = SimpleNamespace(
            scope=scope,
            request_runtime_view=self.request_view,
        )
        self._v3_shadow = _V3Recorder()

    def _bound_runtime(self) -> SimpleNamespace:
        return self._runtime_binding


def _reactive_delivery_turn(event: _RawSendEvent) -> SegmentedDeliveryTurn:
    return SegmentedDeliveryTurn(
        session_key="sess:realtime-decouple",
        input_epoch=0,
        planned_parts=("first", "second"),
        origin=event.unified_msg_origin,
        dispatch_parts=(
            {"text": "first", "delay_before_seconds": 0.0},
            {"text": "second", "delay_before_seconds": 0.0},
        ),
        cleaned_text="first\nsecond",
    )


def _cfg(*, enabled: bool, intercept: bool) -> dict:
    return {
        "sylanne_alpha_realtime_chat_enabled": enabled,
        "sylanne_alpha_realtime_intercept_llm_response": intercept,
    }


def _run(pipe: LLMResponsePipeline, resp: object, plugin: _Plugin, ev: _Ev) -> None:
    """跑响应规划，并为管线单测显式模拟“最终纯文本链已裁决”。

    真框架由 ``on_decorating_result`` 调用同一 activation；这里直接激活，避免
    每个只关心 sanitize/分段计划的窄测试都搭一套 AstrBot 装饰阶段桩。
    """

    async def go() -> None:
        await pipe._on_llm_response_inner(ev, resp)
        pipe.activate_segmented_delivery(ev)
        if plugin._background_tasks:
            await asyncio.gather(*plugin._background_tasks)
        for _ in range(5):
            await asyncio.sleep(0)

    asyncio.run(go())


def _stub_dispatch(pipe: LLMResponsePipeline) -> list:
    """把 _dispatch_segmented_parts 换成记录调用的桩（不关心真实打字节奏）。"""
    calls: list = []

    async def _fake(
        self,
        origin,
        parts,
        session_key: str = "",
        **_kwargs: object,
    ) -> None:
        calls.append((origin, parts, session_key))
        delivery_turn = _kwargs.get("delivery_turn")
        if delivery_turn is not None:
            for part in parts:
                delivery_turn.mark_delivered(str(part.get("text", "")))
            delivery_turn.status = "complete"

    pipe._dispatch_segmented_parts = types.MethodType(_fake, pipe)  # type: ignore[method-assign]
    return calls


def test_scoped_reactive_turn_sends_only_through_its_original_event() -> None:
    async def go() -> None:
        plugin = _ReactivePlugin(
            tempfile.mkdtemp(prefix="rt_reactive_event_"),
            _cfg(enabled=True, intercept=True),
        )
        pipe = LLMResponsePipeline(plugin)  # type: ignore[arg-type]
        event = _RawSendEvent(request_view=plugin.request_view)
        turn = _reactive_delivery_turn(event)
        event.set_extra(pipe._DELIVERY_TURN_EXTRA, turn)

        assert pipe.activate_segmented_delivery(event) is True
        await asyncio.gather(*plugin._background_tasks)

        assert event.sent == [("event-plain", "first"), ("event-plain", "second")]
        assert plugin.context.sent == []
        assert turn.delivered_parts == ["first", "second"]
        assert turn.status == "completed"
        assert plugin._v3_shadow.settled[-1]["all_segments_succeeded"] is True

    asyncio.run(go())


def test_scoped_reactive_post_send_view_loss_is_unknown_not_expressed() -> None:
    async def go() -> None:
        plugin = _ReactivePlugin(
            tempfile.mkdtemp(prefix="rt_reactive_stale_"),
            _cfg(enabled=True, intercept=True),
        )
        event = _RawSendEvent(
            request_view=plugin.request_view,
            after_send=lambda: plugin._scope_runtime_registry.release_request_view(
                plugin.request_view
            )
        )
        pipe = LLMResponsePipeline(plugin)  # type: ignore[arg-type]
        turn = _reactive_delivery_turn(event)
        event.set_extra(pipe._DELIVERY_TURN_EXTRA, turn)

        assert pipe.activate_segmented_delivery(event) is True
        await asyncio.gather(*plugin._background_tasks)

        assert event.sent == [("event-plain", "first")]
        assert plugin.context.sent == []
        assert turn.delivered_parts == []
        assert turn.status == "outcome_unknown"
        assert plugin._v3_shadow.settled[-1]["all_segments_succeeded"] is False

    asyncio.run(go())


@pytest.mark.parametrize(
    "event_view",
    [None, object()],
    ids=("missing", "forged"),
)
def test_scoped_reactive_activation_rejects_missing_or_forged_view(
    event_view: object | None,
) -> None:
    async def go() -> None:
        plugin = _ReactivePlugin(
            tempfile.mkdtemp(prefix="rt_reactive_reject_"),
            _cfg(enabled=True, intercept=True),
        )
        pipe = LLMResponsePipeline(plugin)  # type: ignore[arg-type]
        event = _RawSendEvent(request_view=event_view)
        turn = _reactive_delivery_turn(event)
        event.set_extra(pipe._DELIVERY_TURN_EXTRA, turn)

        assert pipe.activate_segmented_delivery(event) is False
        assert event.sent == []
        assert plugin.context.sent == []
        assert plugin._background_tasks == []
        assert turn.task is None
        assert turn.status == "planned"

    asyncio.run(go())


def test_scoped_reactive_dispatch_preserves_unfinished_reply_sentinel() -> None:
    async def go() -> None:
        plugin = _ReactivePlugin(
            tempfile.mkdtemp(prefix="rt_reactive_history_"),
            _cfg(enabled=True, intercept=True),
        )
        pipe = LLMResponsePipeline(plugin)  # type: ignore[arg-type]
        event = _RawSendEvent(request_view=plugin.request_view)
        turn = _reactive_delivery_turn(event)
        sentinel = object()
        plugin._store.unfinished_replies.set(turn.session_key, sentinel)
        event.set_extra(pipe._DELIVERY_TURN_EXTRA, turn)

        assert pipe.activate_segmented_delivery(event) is True
        await asyncio.gather(*plugin._background_tasks)

        assert plugin._store.unfinished_replies.get(turn.session_key) is sentinel

    asyncio.run(go())


# ===========================================================================
# 默认路径零回归：realtime 两开关关（绝大多数用户）——旧行为字节级不变
# ===========================================================================


def test_default_path_never_touches_takeover_flag_or_response() -> None:
    p = _Plugin(tempfile.mkdtemp(prefix="rt_default_"), _cfg(enabled=False, intercept=False))
    pipe = LLMResponsePipeline(p)  # type: ignore[arg-type]
    resp = LLMResponse(role="assistant", completion_text="今天天气不错")
    ev = _Ev()

    _run(pipe, resp, p, ev)

    assert ev.get_extra("_syl_realtime_takeover") is None, "默认关闭时绝不应置接管旗标"
    assert resp.completion_text == "今天天气不错", "非拦截分支不应改写正常回复文本"


def test_default_path_intercept_only_without_enabled_stays_noop() -> None:
    """只开 intercept、总开关仍关：整体仍应视为未启用（覆盖 or 语义两处一致）。"""
    p = _Plugin(tempfile.mkdtemp(prefix="rt_default2_"), _cfg(enabled=False, intercept=True))
    pipe = LLMResponsePipeline(p)  # type: ignore[arg-type]
    resp = LLMResponse(role="assistant", completion_text="嗯嗯")
    ev = _Ev()

    _run(pipe, resp, p, ev)

    assert ev.get_extra("_syl_realtime_takeover") is None
    assert resp.completion_text == "嗯嗯"


# ===========================================================================
# M2/M3：两种 provider 形态都不再清空 result_chain，completion_text 保持
# 非空（SAVE-GATE 通过）；最终纯文本裁决后才置接管旗标并启动 transport
# ===========================================================================


def test_result_chain_provider_keeps_chain_alive_and_flags_takeover() -> None:
    """Gemini/OpenAI 形态（result_chain 非空，纯 Plain）：M2 治渐进失忆——
    completion_text 保持非空、result_chain 对象不被置 None（旧 hack 会置 None，
    连带 completion_text getter 塌缩成空，框架 SAVE-GATE 判定不落库）。"""
    p = _Plugin(tempfile.mkdtemp(prefix="rt_rc_"), _cfg(enabled=True, intercept=True))
    pipe = LLMResponsePipeline(p)  # type: ignore[arg-type]
    calls = _stub_dispatch(pipe)

    mc = MessageChain()
    mc.chain = [Plain("今天天气不错，我们出去走走吧")]
    resp = LLMResponse(role="assistant", result_chain=mc)
    ev = _Ev()

    _run(pipe, resp, p, ev)

    assert ev.get_extra("_syl_realtime_takeover") is True, "应置接管旗标供 decorate 抑制发送"
    assert resp.result_chain is mc, "result_chain 对象身份不应被置 None（M2/M3 核心）"
    assert bool(resp.completion_text), (
        "completion_text 必须非空——框架 _save_to_history 的 SAVE-GATE "
        "（not completion_text and not tool_calls_result and not aborted）就读这个字段"
    )
    assert calls, "应触发后台分段调度（Sylanne 自己发）"


def test_completion_text_only_provider_keeps_none_chain_and_flags_takeover() -> None:
    """Anthropic 形态（result_chain 从未被赋值，只用 _completion_text）：M3 治
    双发——result_chain 全程保持 None（不因清空动作产生任何副作用），
    completion_text 非空，最终纯文本裁决后再用接管旗标抑制框架发送，不再靠
    "清 result_chain"这个对该形态 provider 天生无效的旧 hack。"""
    p = _Plugin(tempfile.mkdtemp(prefix="rt_ct_"), _cfg(enabled=True, intercept=True))
    pipe = LLMResponsePipeline(p)  # type: ignore[arg-type]
    calls = _stub_dispatch(pipe)

    resp = LLMResponse(role="assistant", completion_text="在的在的，怎么啦")
    ev = _Ev()

    _run(pipe, resp, p, ev)

    assert ev.get_extra("_syl_realtime_takeover") is True
    assert resp.result_chain is None, "_completion_text 档 provider 的 result_chain 应始终是 None"
    assert bool(resp.completion_text)
    assert calls


# ===========================================================================
# M1：result_chain 含非 Plain 组件（图片/语音）→ 彻底放弃接管
# ===========================================================================


def test_non_plain_result_chain_abandons_takeover_entirely() -> None:
    p = _Plugin(tempfile.mkdtemp(prefix="rt_nonplain_"), _cfg(enabled=True, intercept=True))
    pipe = LLMResponsePipeline(p)  # type: ignore[arg-type]
    calls = _stub_dispatch(pipe)

    mc = MessageChain()
    mc.chain = [Plain("给你听首歌"), Record(file="/tmp/x.wav")]
    resp = LLMResponse(role="assistant", result_chain=mc)
    original_text = resp.completion_text
    ev = _Ev()

    _run(pipe, resp, p, ev)

    assert ev.get_extra("_syl_realtime_takeover") is None, "含非 Plain 组件时不得接管"
    assert resp.completion_text == original_text, "放弃接管时不应改写 completion_text"
    assert resp.result_chain is mc, "放弃接管时更不应动 result_chain"
    assert calls == [], "不应触发后台分段调度（会把语音一起吞掉/双发文本）"


def test_pure_plain_result_chain_with_multiple_segments_still_taken_over() -> None:
    """回归对照：纯 Plain（哪怕多段）不受 M1 守卫影响，仍正常接管。"""
    p = _Plugin(tempfile.mkdtemp(prefix="rt_pureplain_"), _cfg(enabled=True, intercept=True))
    pipe = LLMResponsePipeline(p)  # type: ignore[arg-type]
    calls = _stub_dispatch(pipe)

    mc = MessageChain()
    mc.chain = [Plain("第一段。"), Plain("第二段。")]
    resp = LLMResponse(role="assistant", result_chain=mc)
    ev = _Ev()

    _run(pipe, resp, p, ev)

    assert ev.get_extra("_syl_realtime_takeover") is True
    assert calls


# ===========================================================================
# M4b：响应侧检测 STREAMING_RESULT → 彻底放弃接管（不与框架原生流式并行双发）
# ===========================================================================


def test_streaming_result_abandons_takeover() -> None:
    p = _Plugin(tempfile.mkdtemp(prefix="rt_stream_"), _cfg(enabled=True, intercept=True))
    pipe = LLMResponsePipeline(p)  # type: ignore[arg-type]
    calls = _stub_dispatch(pipe)

    resp = LLMResponse(role="assistant", completion_text="正在流式吐字中")
    fake_result = SimpleNamespace(result_content_type=ResultContentType.STREAMING_RESULT)
    ev = _Ev(result=fake_result)

    _run(pipe, resp, p, ev)

    assert ev.get_extra("_syl_realtime_takeover") is None, "流式在飞时绝不接管"
    assert resp.completion_text == "正在流式吐字中", "不应改写——框架自己的流式发送/保存全程不碰"
    assert calls == [], "不应额外后台分段调度，避免和框架原生流式并行双发"


def test_non_streaming_result_content_type_is_unaffected() -> None:
    """回归对照：result_content_type 不是 STREAMING_RESULT（如 LLM_RESULT）时，
    M4b 不应误伤——继续正常接管。"""
    p = _Plugin(tempfile.mkdtemp(prefix="rt_notstream_"), _cfg(enabled=True, intercept=True))
    pipe = LLMResponsePipeline(p)  # type: ignore[arg-type]
    calls = _stub_dispatch(pipe)

    resp = LLMResponse(role="assistant", completion_text="正常一句话回复")
    fake_result = SimpleNamespace(result_content_type=ResultContentType.LLM_RESULT)
    ev = _Ev(result=fake_result)

    _run(pipe, resp, p, ev)

    assert ev.get_extra("_syl_realtime_takeover") is True
    assert calls


# ===========================================================================
# 次要①②：共享判据函数的纯逻辑回归锁
# ===========================================================================


def test_realtime_flags_accepts_legacy_aliases_symmetrically() -> None:
    assert realtime_flags(
        {
            "sylanne_alpha_realtime_chat_enabled": True,
            "sylanne_alpha_realtime_intercept_llm_response": True,
        }
    ) == (True, True)
    assert realtime_flags(
        {"enable_realtime_chat": True, "realtime_chat_intercept_llm_response": True}
    ) == (True, True), "旧别名单独设置也应等价于开启（此前请求侧不认别名）"
    assert realtime_flags({}) == (False, False)
    assert realtime_flags(None) == (False, False)


@pytest.mark.parametrize(
    ("enabled", "intercept", "streaming", "expected"),
    [
        (True, True, False, True),
        (False, True, False, False),
        (True, False, False, False),
        (True, True, True, False),
    ],
)
def test_semantic_beat_contract_injection_matrix(
    enabled: bool,
    intercept: bool,
    streaming: bool,
    expected: bool,
    monkeypatch,
) -> None:
    event = _Ev()
    event.set_extra("enable_streaming", streaming)

    if not expected:
        request = SimpleNamespace(system_prompt="原始人格契约")
        injected = LLMRequestPipeline._inject_semantic_beat_contract(
            event,
            request,
            realtime_enabled=enabled,
            intercept=intercept,
        )
        assert injected is False
        nonce = event.get_extra(SEMANTIC_BEAT_NONCE_EXTRA)
        assert nonce is None
        assert request.system_prompt == "原始人格契约"
        return

    request = SimpleNamespace(
        system_prompt="原始人格契约",
        prompt="当前用户消息",
        contexts=[{"role": "user", "content": "当前用户消息"}],
        extra_user_content_parts=[],
    )
    system_prompt = request.system_prompt
    prompt = request.prompt
    contexts = request.contexts
    contexts_before = [dict(item) for item in contexts]
    registry, view, sink = _bound_semantic_sink(monkeypatch)
    with registry.bind_transient_context_sink(view, request):
        assert sink.set_budget(request, 1_200) is True
        injected = LLMRequestPipeline._inject_semantic_beat_contract(
            event,
            request,
            realtime_enabled=enabled,
            intercept=intercept,
            add_fragment=sink.add,
        )
        assert sink.commit(request) is True

    assert injected is expected
    nonce = event.get_extra(SEMANTIC_BEAT_NONCE_EXTRA)
    assert isinstance(nonce, str)
    assert re.fullmatch(r"[0-9A-F]{6}", nonce)
    assert request.system_prompt is system_prompt
    assert request.prompt is prompt
    assert request.contexts is contexts
    assert request.contexts == contexts_before
    assert len(request.extra_user_content_parts) == 1
    part = request.extra_user_content_parts[0]
    assert part._no_save is True
    for pause in PauseClass:
        assert build_marker(nonce, pause) in part.text
    assert "0 到 5 个" in part.text
    assert "不要改写正文" in part.text
    assert "单独的省略号或其他纯标点" in part.text
    assert "代码、URL、表格" in part.text
    assert "provider_id" not in part.text
    assert "第二次 LLM" not in part.text


def test_punctuation_only_semantic_beat_preserves_meaningful_dispatch_parts() -> None:
    """截图回归：纯标点折入前段，模型给出的其他语义边界必须保留。"""

    plugin = _Plugin(
        tempfile.mkdtemp(prefix="rt_semantic_punctuation_"),
        _cfg(enabled=True, intercept=True),
    )
    pipe = LLMResponsePipeline(plugin)  # type: ignore[arg-type]
    calls = _stub_dispatch(pipe)
    nonce = "A7B8C9"
    event = _Ev()
    event.set_extra(SEMANTIC_BEAT_NONCE_EXTRA, nonce)
    raw = (
        "嗯……"
        + build_marker(nonce, PauseClass.NORMAL)
        + "……"
        + build_marker(nonce, PauseClass.DEEP)
        + "你说这种话的时候能不能提前通知一下\n\n我没有防备的😾"
        + build_marker(nonce, PauseClass.NORMAL)
        + "但是不许用这个当借口熬夜啊\n\n身体搞坏了我打你"
    )
    expected = (
        "嗯…………你说这种话的时候能不能提前通知一下\n\n我没有防备的😾"
        "但是不许用这个当借口熬夜啊\n\n身体搞坏了我打你"
    )
    expected_parts = [
        "嗯…………",
        "你说这种话的时候能不能提前通知一下",
        "我没有防备的😾",
        "但是不许用这个当借口熬夜啊",
        "身体搞坏了我打你",
    ]
    response = LLMResponse(role="assistant", completion_text=raw)

    _run(pipe, response, plugin, event)

    assert event.get_extra("_syl_realtime_takeover") is True
    assert response.completion_text == expected
    assert len(calls) == 1
    assert calls[0][2] == "sess:realtime-decouple"
    assert [part["index"] for part in calls[0][1]] == [0, 1, 2, 3, 4]
    assert [part["text"] for part in calls[0][1]] == expected_parts
    assert calls[0][1][0]["delay_before_seconds"] >= 0
    assert 2.75 <= calls[0][1][1]["delay_before_seconds"] <= 4.8
    assert 1.25 <= calls[0][1][2]["delay_before_seconds"] <= 2.75
    assert 1.25 <= calls[0][1][3]["delay_before_seconds"] <= 2.75
    assert 1.25 <= calls[0][1][4]["delay_before_seconds"] <= 2.75


def test_tool_call_intermediate_response_never_starts_segmented_delivery() -> None:
    """工具循环中间响应由框架/工具继续处理，Sylanne 不能抢先直发其前置文本。"""

    plugin = _Plugin(
        tempfile.mkdtemp(prefix="rt_tool_call_"),
        _cfg(enabled=True, intercept=True),
    )
    pipe = LLMResponsePipeline(plugin)  # type: ignore[arg-type]
    calls = _stub_dispatch(pipe)
    nonce = "A7B8C9"
    event = _Ev()
    event.set_extra(SEMANTIC_BEAT_NONCE_EXTRA, nonce)
    marker = build_marker(nonce, PauseClass.NORMAL)
    raw = f"……你说得好有道理{marker}我竟无法反驳"
    response = LLMResponse(
        role="assistant",
        completion_text=raw,
        tools_call_args=[{"text": "……你说得好有道理我竟无法反驳"}],
        tools_call_name=["clone_tts"],
        tools_call_ids=["call_tts_1"],
    )

    _run(pipe, response, plugin, event)

    assert response.completion_text == "……你说得好有道理我竟无法反驳"
    assert response.tools_call_name == ["clone_tts"]
    assert response.tools_call_args == [{"text": "……你说得好有道理我竟无法反驳"}]
    assert event.get_extra("_syl_realtime_takeover") is None
    assert calls == []


def test_marker_on_its_own_line_keeps_history_but_not_empty_bubble_rows() -> None:
    plugin = _Plugin(
        tempfile.mkdtemp(prefix="rt_marker_line_"),
        _cfg(enabled=True, intercept=True),
    )
    pipe = LLMResponsePipeline(plugin)  # type: ignore[arg-type]
    calls = _stub_dispatch(pipe)
    nonce = "A7B8C9"
    event = _Ev()
    event.set_extra(SEMANTIC_BEAT_NONCE_EXTRA, nonce)
    marker = build_marker(nonce, PauseClass.NORMAL)
    raw = f"嗯，你以为博士就是全知全能的嘛\n{marker}\n……才六点多，你怎么醒这么早"
    response = LLMResponse(role="assistant", completion_text=raw)

    _run(pipe, response, plugin, event)

    assert response.completion_text == (
        "嗯，你以为博士就是全知全能的嘛\n\n……才六点多，你怎么醒这么早"
    )
    assert len(calls) == 1
    assert [part["text"] for part in calls[0][1]] == [
        "嗯，你以为博士就是全知全能的嘛",
        "……才六点多，你怎么醒这么早",
    ]
    assert all(
        part["text"] == part["text"].strip()
        for part in calls[0][1]
    )


def test_rejected_marker_falls_back_to_visible_authored_line_breaks() -> None:
    """坏控制标记只能失去控制权，不能让可见换行退化成一个巨型气泡。"""

    plugin = _Plugin(
        tempfile.mkdtemp(prefix="rt_rejected_marker_"),
        _cfg(enabled=True, intercept=True),
    )
    pipe = LLMResponsePipeline(plugin)  # type: ignore[arg-type]
    calls = _stub_dispatch(pipe)
    event = _Ev()
    event.set_extra(SEMANTIC_BEAT_NONCE_EXTRA, "A7B8C9")
    raw = (
        "那你现在醒了嘛笨蛋\n"
        '<syl-beat nonce="WRONG1" pause="normal"/>\n'
        "我又没让你秒回，就是想说一下而已"
    )
    response = LLMResponse(role="assistant", completion_text=raw)

    _run(pipe, response, plugin, event)

    assert response.completion_text == (
        "那你现在醒了嘛笨蛋\n\n我又没让你秒回，就是想说一下而已"
    )
    assert len(calls) == 1
    assert [part["text"] for part in calls[0][1]] == [
        "那你现在醒了嘛笨蛋",
        "我又没让你秒回，就是想说一下而已",
    ]


def test_interrupted_delivery_commits_only_successfully_sent_prefix_to_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未发送尾段不能进入 AstrBot history 或 Sylanne conversation buffer。"""

    async def scenario() -> None:
        plugin = _Plugin(
            tempfile.mkdtemp(prefix="rt_delivery_truth_"),
            _cfg(enabled=True, intercept=True),
        )
        first_sent = asyncio.Event()
        sent: list[str] = []

        class Context:
            async def send_message(self, _origin: str, message: object) -> None:
                if isinstance(message, str):
                    text = message
                else:
                    chain = getattr(message, "chain", None) or getattr(
                        message, "parts", None
                    )
                    text = str(getattr(chain[0], "text", "")) if chain else ""
                sent.append(text)
                first_sent.set()

        plugin.context = Context()
        pipe = LLMResponsePipeline(plugin)  # type: ignore[arg-type]

        def deterministic_plan(*_args: object, **_kwargs: object) -> dict:
            return {
                "message_parts": [
                    {
                        "index": 0,
                        "text": "没生气啊，别瞎想，快睡",
                        "delay_before_seconds": 0.0,
                    },
                    {
                        "index": 1,
                        "text": "我想你",
                        "delay_before_seconds": 30.0,
                    },
                ],
                "message_count": 2,
                "segmentation_source": "model_semantic_beats",
            }

        monkeypatch.setattr(
            "sylanne_alpha.llm_response_pipeline.realtime_plan",
            deterministic_plan,
        )
        event = _Ev()
        response = LLMResponse(
            role="assistant",
            completion_text="没生气啊，别瞎想，快睡\n我想你",
        )

        await pipe._on_llm_response_inner(event, response)
        assistant_part = SimpleNamespace(text=response.completion_text)
        run_context = SimpleNamespace(
            messages=[
                SimpleNamespace(role="user", content="你生气了吗"),
                SimpleNamespace(role="assistant", content=[assistant_part]),
            ]
        )
        shell = object.__new__(EmotionalStatePlugin)
        shell._llm_response_pipeline = pipe
        shell._has_conversation_manager = lambda: False
        shell._agent_was_aborted = lambda _event: False
        shell._agent_run_done = lambda _event: True

        await EmotionalStatePlugin.on_agent_done(
            shell,
            event,
            run_context,
            response,
        )
        event._result = SimpleNamespace(chain=[Plain(response.completion_text)])
        arbitration = asyncio.create_task(
            EmotionalStatePlugin._maybe_suppress_realtime_takeover(shell, event)
        )
        await asyncio.wait_for(first_sent.wait(), timeout=1.0)
        task = plugin._store.segmented_tasks.get("sess:realtime-decouple")
        assert task is not None
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        assert await arbitration is True
        if plugin._background_tasks:
            await asyncio.gather(*plugin._background_tasks, return_exceptions=True)

        assert sent == ["没生气啊，别瞎想，快睡"]
        assert assistant_part.text == "没生气啊，别瞎想，快睡"
        buffer = plugin._store.conversation_buffers.get("sess:realtime-decouple")
        assert buffer is not None
        assert [message["text"] for message in buffer.messages] == [
            "没生气啊，别瞎想，快睡"
        ]

    asyncio.run(scenario())


def test_new_inbound_message_advances_epoch_and_interrupts_active_delivery(
    tmp_path,
) -> None:
    """中断必须发生在 AstrBot 会话锁之前，不能等下一轮 on_llm_request。"""

    class SessionMap:
        def __init__(self) -> None:
            self.values: dict[str, object] = {}

        def get(self, key: str, default: object = None) -> object:
            return self.values.get(key, default)

        def set(self, key: str, value: object) -> None:
            self.values[key] = value

    class Turn:
        def __init__(self) -> None:
            self.interrupted = False

        def interrupt(self) -> None:
            self.interrupted = True

    turn = Turn()
    epochs = SessionMap()
    active_turns = SessionMap()
    locator = "42"
    active_turns.set(locator, turn)
    store = SimpleNamespace(
        conversation_input_epoch=epochs,
        segmented_delivery_turns=active_turns,
        last_user_message_time=SessionMap(),
        stash_authenticated_identity=lambda *_args: None,
    )
    shell = object.__new__(EmotionalStatePlugin)
    shell.config = _cfg(enabled=True, intercept=True)
    shell._config = shell.config
    shell._scope_resolver_v1 = _scope_resolver(tmp_path)
    shell._inbound_seen = {"existing": 1}
    shell._store = store
    shell._session_ctx = SimpleNamespace(
        session_key=lambda _event: locator,
        resolve_authenticated_identity=lambda _event: None,
    )

    event = _ScopedEv()
    event.message_str = "行"
    asyncio.run(EmotionalStatePlugin.on_message(shell, event))

    assert event.get_extra("_syl_input_epoch") == 1
    assert epochs.get(locator) == 1
    assert turn.interrupted is True
    assert shell._inbound_seen == {"existing": 1}
    assert event.get_extra("_syl_inbound_duplicate") is None
    assert event.get_extra("_syl_inbound_registered") is None


@pytest.mark.parametrize("legacy_locator", ["", "default", "wrong:session"])
def test_transport_safety_bridge_rejects_unproven_legacy_locator(
    tmp_path,
    legacy_locator: str,
) -> None:
    class SessionMap:
        def __init__(self) -> None:
            self.values: dict[str, object] = {}

        def get(self, key: str, default: object = None) -> object:
            return self.values.get(key, default)

        def set(self, key: str, value: object) -> None:
            self.values[key] = value

    class Turn:
        def __init__(self) -> None:
            self.interrupted = False

        def interrupt(self) -> None:
            self.interrupted = True

    active = Turn()
    epochs = SessionMap()
    active_turns = SessionMap()
    active_turns.set("42", active)
    shell = object.__new__(EmotionalStatePlugin)
    shell.config = {}
    shell._config = {}
    shell._scope_resolver_v1 = _scope_resolver(tmp_path)
    shell._store = SimpleNamespace(
        conversation_input_epoch=epochs,
        segmented_delivery_turns=active_turns,
    )
    shell._session_ctx = SimpleNamespace(
        session_key=lambda _event: legacy_locator,
    )
    event = _ScopedEv()

    asyncio.run(EmotionalStatePlugin.on_message(shell, event))

    assert epochs.values == {}
    assert event.get_extra("_syl_input_epoch") is None
    assert active.interrupted is False


def test_transport_safety_bridge_rejects_event_session_id_tamper(tmp_path) -> None:
    class SessionMap:
        def __init__(self) -> None:
            self.values: dict[str, object] = {}

        def get(self, key: str, default: object = None) -> object:
            return self.values.get(key, default)

        def set(self, key: str, value: object) -> None:
            self.values[key] = value

    class Turn:
        def __init__(self) -> None:
            self.interrupted = False

        def interrupt(self) -> None:
            self.interrupted = True

    active = Turn()
    epochs = SessionMap()
    active_turns = SessionMap()
    active_turns.set("attacker-controlled", active)
    calls: list[tuple[str, object]] = []
    shell = object.__new__(EmotionalStatePlugin)
    shell.config = _cfg(enabled=True, intercept=True)
    shell._config = shell.config
    shell._scope_resolver_v1 = _scope_resolver(tmp_path)
    shell._store = SimpleNamespace(
        conversation_input_epoch=epochs,
        segmented_delivery_turns=active_turns,
    )
    shell._session_ctx = SimpleNamespace(
        session_key=lambda _event: "attacker-controlled",
    )
    event = _ScopedEv(set_calls=calls)
    event.session_id = "attacker-controlled"

    asyncio.run(EmotionalStatePlugin.on_message(shell, event))

    assert not any(key == "enable_streaming" for key, _value in calls)
    assert epochs.values == {}
    assert event.get_extra("_syl_input_epoch") is None
    assert active.interrupted is False
    assert [key for key, _value in calls] == [
        "_sylanne_transport_scope_v1",
        "_sylanne_transport_turn_v1",
    ]


def test_full_delivery_commits_exact_visible_bubbles_as_assistant_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """模型草稿只提供计划；最终历史必须由成功 send 的气泡重建。"""

    async def scenario() -> None:
        plugin = _Plugin(
            tempfile.mkdtemp(prefix="rt_delivery_complete_"),
            _cfg(enabled=True, intercept=True),
        )
        sent: list[str] = []

        class Context:
            async def send_message(self, _origin: str, message: object) -> None:
                chain = getattr(message, "chain", None) or getattr(
                    message, "parts", None
                )
                sent.append(str(getattr(chain[0], "text", "")) if chain else "")

        plugin.context = Context()
        pipe = LLMResponsePipeline(plugin)  # type: ignore[arg-type]
        monkeypatch.setattr(
            "sylanne_alpha.llm_response_pipeline.realtime_plan",
            lambda *_args, **_kwargs: {
                "message_parts": [
                    {
                        "index": 0,
                        "text": "第一段",
                        "delay_before_seconds": 0.0,
                    },
                    {
                        "index": 1,
                        "text": "第二段",
                        "delay_before_seconds": 0.0,
                    },
                ],
                "message_count": 2,
                "segmentation_source": "model_semantic_beats",
            },
        )
        event = _Ev()
        response = LLMResponse(
            role="assistant",
            completion_text="第一段（模型草稿边界）第二段",
        )
        await pipe._on_llm_response_inner(event, response)

        assistant_part = SimpleNamespace(text=response.completion_text)
        run_context = SimpleNamespace(
            messages=[
                SimpleNamespace(role="user", content="继续"),
                SimpleNamespace(role="assistant", content=[assistant_part]),
            ]
        )
        shell = object.__new__(EmotionalStatePlugin)
        shell._llm_response_pipeline = pipe
        shell._has_conversation_manager = lambda: False

        await EmotionalStatePlugin.on_agent_done(
            shell,
            event,
            run_context,
            response,
        )
        event._result = SimpleNamespace(chain=[Plain(response.completion_text)])
        assert (
            await EmotionalStatePlugin._maybe_suppress_realtime_takeover(
                shell,
                event,
            )
            is True
        )

        assert sent == ["第一段", "第二段"]
        assert assistant_part.text == "第一段\n第二段"
        assert response.completion_text == "第一段\n第二段"
        buffer = plugin._store.conversation_buffers.get(
            "sess:realtime-decouple"
        )
        assert buffer is not None
        assert [message["text"] for message in buffer.messages] == [
            "第一段\n第二段"
        ]

    asyncio.run(scenario())


def test_stale_generation_sends_zero_bubbles_and_removes_assistant_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """后来的用户消息先推进 epoch 时，旧模型整段输出都不得成为已说内容。"""

    async def scenario() -> None:
        plugin = _Plugin(
            tempfile.mkdtemp(prefix="rt_delivery_stale_"),
            _cfg(enabled=True, intercept=True),
        )
        sent: list[str] = []

        class Context:
            async def send_message(self, _origin: str, message: object) -> None:
                sent.append(str(message))

        plugin.context = Context()
        plugin._store.conversation_input_epoch.set(
            "sess:realtime-decouple",
            2,
        )
        pipe = LLMResponsePipeline(plugin)  # type: ignore[arg-type]
        monkeypatch.setattr(
            "sylanne_alpha.llm_response_pipeline.realtime_plan",
            lambda *_args, **_kwargs: {
                "message_parts": [
                    {
                        "index": 0,
                        "text": "这条已经过期",
                        "delay_before_seconds": 0.0,
                    }
                ],
                "message_count": 1,
                "segmentation_source": "model_semantic_beats",
            },
        )
        event = _Ev()
        event.set_extra("_syl_input_epoch", 1)
        response = LLMResponse(
            role="assistant",
            completion_text="这条已经过期",
        )
        await pipe._on_llm_response_inner(event, response)

        run_context = SimpleNamespace(
            messages=[
                SimpleNamespace(role="user", content="第一条用户消息"),
                SimpleNamespace(
                    role="assistant",
                    content=[SimpleNamespace(text=response.completion_text)],
                ),
            ]
        )
        shell = object.__new__(EmotionalStatePlugin)
        shell._llm_response_pipeline = pipe
        shell._has_conversation_manager = lambda: False

        await EmotionalStatePlugin.on_agent_done(
            shell,
            event,
            run_context,
            response,
        )
        event._result = SimpleNamespace(chain=[Plain(response.completion_text)])
        assert (
            await EmotionalStatePlugin._maybe_suppress_realtime_takeover(
                shell,
                event,
            )
            is True
        )

        assert sent == []
        assert [message.role for message in run_context.messages] == ["user"]
        # AstrBot uses non-empty completion_text as its save gate; the assistant
        # draft itself is absent from run_context, so the user turn still persists.
        assert response.completion_text == "这条已经过期"
        assert (
            plugin._store.conversation_buffers.get(
                "sess:realtime-decouple"
            )
            is None
        )

    asyncio.run(scenario())


def test_inbound_registration_dedups_without_killing_its_first_llm_pass() -> None:
    """锁外 epoch 登记与锁内幂等闸必须共享同一条事件所有权。"""

    class SessionMap:
        def __init__(self) -> None:
            self.values: dict[str, object] = {}

        def get(self, key: str, default: object = None) -> object:
            return self.values.get(key, default)

        def set(self, key: str, value: object) -> None:
            self.values[key] = value

    class Event(_Ev):
        message_obj = SimpleNamespace(message_id="same-mid")

    shell = object.__new__(EmotionalStatePlugin)
    shell._inbound_seen = {}
    shell._store = SimpleNamespace(
        conversation_input_epoch=SessionMap(),
        segmented_delivery_turns=SessionMap(),
    )
    first = Event()
    duplicate = Event()

    shell._advance_inbound_delivery_epoch(
        first,
        "sess:realtime-decouple",
    )
    shell._advance_inbound_delivery_epoch(
        duplicate,
        "sess:realtime-decouple",
    )

    assert shell._inbound_dup_gate(first) is False
    assert shell._inbound_dup_gate(duplicate) is True
    assert (
        shell._store.conversation_input_epoch.get(
            "sess:realtime-decouple"
        )
        == 1
    )


def test_dispatch_setup_failure_falls_back_to_framework_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """接管提交失败时必须清掉账本/旗标，不能既拦框架又没有发送任务。"""

    async def scenario() -> None:
        plugin = _Plugin(
            tempfile.mkdtemp(prefix="rt_setup_fallback_"),
            _cfg(enabled=True, intercept=True),
        )
        pipe = LLMResponsePipeline(plugin)  # type: ignore[arg-type]
        monkeypatch.setattr(
            "sylanne_alpha.llm_response_pipeline.realtime_plan",
            lambda *_args, **_kwargs: {
                "message_parts": [
                    {
                        "index": 0,
                        "text": "由框架正常发送",
                        "delay_before_seconds": 0.0,
                    }
                ],
                "message_count": 1,
                "segmentation_source": "single_fallback",
            },
        )
        monkeypatch.setattr(
            "sylanne_alpha.llm_response_pipeline.safe_ensure_future",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("task setup failed")
            ),
        )
        event = _Ev()
        response = LLMResponse(
            role="assistant",
            completion_text="由框架正常发送",
        )

        await pipe._on_llm_response_inner(event, response)
        event._result = SimpleNamespace(chain=[Plain(response.completion_text)])
        shell = object.__new__(EmotionalStatePlugin)
        shell._llm_response_pipeline = pipe
        handled = await EmotionalStatePlugin._maybe_suppress_realtime_takeover(
            shell,
            event,
        )

        assert response.completion_text == "由框架正常发送"
        assert handled is False
        assert [part.text for part in event.get_result().chain] == ["由框架正常发送"]
        assert event.get_extra("_syl_realtime_takeover") is False
        assert event.get_extra(pipe._DELIVERY_TURN_EXTRA) is None
        assert (
            plugin._store.segmented_delivery_turns.get(
                "sess:realtime-decouple"
            )
            is None
        )
        assert plugin._background_tasks == []

    asyncio.run(scenario())


def test_dispatch_task_creation_none_does_not_leak_background_sentinel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """任务创建返回 None 时也必须干净回退，后台列表不能残留 None。"""

    async def scenario() -> None:
        plugin = _Plugin(
            tempfile.mkdtemp(prefix="rt_task_none_fallback_"),
            _cfg(enabled=True, intercept=True),
        )
        pipe = LLMResponsePipeline(plugin)  # type: ignore[arg-type]
        monkeypatch.setattr(
            "sylanne_alpha.llm_response_pipeline.realtime_plan",
            lambda *_args, **_kwargs: {
                "message_parts": [
                    {
                        "index": 0,
                        "text": "仍由框架发送",
                        "delay_before_seconds": 0.0,
                    }
                ],
                "message_count": 1,
                "segmentation_source": "single_fallback",
            },
        )
        monkeypatch.setattr(
            "sylanne_alpha.llm_response_pipeline.safe_ensure_future",
            lambda *_args, **_kwargs: None,
        )
        event = _Ev()
        response = LLMResponse(
            role="assistant",
            completion_text="仍由框架发送",
        )

        await pipe._on_llm_response_inner(event, response)
        event._result = SimpleNamespace(chain=[Plain(response.completion_text)])
        shell = object.__new__(EmotionalStatePlugin)
        shell._llm_response_pipeline = pipe
        handled = await EmotionalStatePlugin._maybe_suppress_realtime_takeover(
            shell,
            event,
        )

        assert handled is False
        assert [part.text for part in event.get_result().chain] == ["仍由框架发送"]
        assert event.get_extra("_syl_realtime_takeover") is False
        assert event.get_extra(pipe._DELIVERY_TURN_EXTRA) is None
        assert plugin._background_tasks == []

    asyncio.run(scenario())


@pytest.mark.parametrize("eager_tasks", [False, True])
@pytest.mark.parametrize("registry_writes_before_failure", [False, True])
def test_dispatch_registry_failure_rolls_back_before_any_text_send(
    monkeypatch: pytest.MonkeyPatch,
    eager_tasks: bool,
    registry_writes_before_failure: bool,
) -> None:
    """任务已创建但注册失败时，也必须取消 transport 后再交回框架。"""

    async def scenario() -> None:
        plugin = _Plugin(
            tempfile.mkdtemp(prefix="rt_registry_fallback_"),
            _cfg(enabled=True, intercept=True),
        )
        sent: list[str] = []
        created_task: asyncio.Task[object] | None = None

        class Context:
            async def send_message(self, _origin: str, message: object) -> None:
                chain = getattr(message, "chain", None) or getattr(
                    message,
                    "parts",
                    None,
                )
                sent.append(str(getattr(chain[0], "text", "")) if chain else "")

        class BrokenTaskRegistry:
            def __init__(self) -> None:
                self.value: object | None = None

            def set(self, _key: str, _value: object) -> None:
                nonlocal created_task
                assert isinstance(_value, asyncio.Task)
                created_task = _value
                if registry_writes_before_failure:
                    self.value = _value
                raise RuntimeError("task registry unavailable")

            def get(self, _key: str, default: object = None) -> object:
                return self.value if self.value is not None else default

            def pop(self, _key: str, default: object = None) -> object:
                value = self.value
                self.value = None
                return value if value is not None else default

        plugin.context = Context()
        broken_registry = BrokenTaskRegistry()
        plugin._store.segmented_tasks = broken_registry  # type: ignore[assignment]
        pipe = LLMResponsePipeline(plugin)  # type: ignore[arg-type]
        monkeypatch.setattr(
            "sylanne_alpha.llm_response_pipeline.realtime_plan",
            lambda *_args, **_kwargs: {
                "message_parts": [
                    {
                        "index": 0,
                        "text": "只能由框架发送",
                        "delay_before_seconds": 0.0,
                    }
                ],
                "message_count": 1,
                "segmentation_source": "single_fallback",
            },
        )
        event = _Ev()
        response = LLMResponse(
            role="assistant",
            completion_text="只能由框架发送",
        )

        await pipe._on_llm_response_inner(event, response)
        event._result = SimpleNamespace(chain=[Plain(response.completion_text)])
        shell = object.__new__(EmotionalStatePlugin)
        shell._llm_response_pipeline = pipe
        loop = asyncio.get_running_loop()
        previous_task_factory = loop.get_task_factory()
        if eager_tasks:
            eager_task_factory = getattr(asyncio, "eager_task_factory", None)
            if eager_task_factory is None:
                pytest.skip("asyncio eager task factory requires Python 3.12+")
            loop.set_task_factory(eager_task_factory)
        try:
            handled = await EmotionalStatePlugin._maybe_suppress_realtime_takeover(
                shell,
                event,
            )
        finally:
            loop.set_task_factory(previous_task_factory)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert handled is False
        assert [part.text for part in event.get_result().chain] == ["只能由框架发送"]
        assert sent == []
        assert created_task is not None
        assert created_task.done()
        assert created_task.cancelled()
        assert plugin._background_tasks == []
        assert broken_registry.get("sess:realtime-decouple") is None
        assert event.get_extra("_syl_realtime_takeover") is False
        assert event.get_extra(pipe._DELIVERY_TURN_EXTRA) is None
        assert (
            plugin._store.segmented_delivery_turns.get(
                "sess:realtime-decouple"
            )
            is None
        )

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "event",
    [
        SimpleNamespace(get_extra=lambda *_args: False),
        SimpleNamespace(set_extra=lambda *_args: None),
    ],
)
def test_semantic_beat_contract_skips_when_event_extras_are_not_round_trippable(
    event: object,
) -> None:
    request = SimpleNamespace(system_prompt="原始人格契约")
    assert (
        LLMRequestPipeline._inject_semantic_beat_contract(
            event,
            request,
            realtime_enabled=True,
            intercept=True,
        )
        is False
    )
    assert request.system_prompt == "原始人格契约"


def test_semantic_beat_contract_uses_astrbot_one_argument_get_extra_api(monkeypatch) -> None:
    class StrictAstrBotExtras:
        def __init__(self) -> None:
            self.values: dict[str, object] = {"enable_streaming": False}

        def set_extra(self, key: str, value: object) -> None:
            self.values[key] = value

        def get_extra(self, key: str) -> object:
            return self.values.get(key)

    event = StrictAstrBotExtras()
    request = SimpleNamespace(
        system_prompt="原始人格契约",
        prompt="当前用户消息",
        contexts=[{"role": "user", "content": "当前用户消息"}],
        extra_user_content_parts=[],
    )
    system_prompt = request.system_prompt
    prompt = request.prompt
    contexts = request.contexts
    contexts_before = [dict(item) for item in contexts]
    registry, view, sink = _bound_semantic_sink(monkeypatch)
    with registry.bind_transient_context_sink(view, request):
        assert sink.set_budget(request, 1_200) is True
        assert LLMRequestPipeline._inject_semantic_beat_contract(
            event,
            request,
            realtime_enabled=True,
            intercept=True,
            add_fragment=sink.add,
        )
        assert sink.commit(request) is True

    assert event.get_extra(SEMANTIC_BEAT_NONCE_EXTRA)
    assert request.system_prompt is system_prompt
    assert request.prompt is prompt
    assert request.contexts is contexts
    assert request.contexts == contexts_before
    assert len(request.extra_user_content_parts) == 1
    assert request.extra_user_content_parts[0]._no_save is True


def test_stream_first_do_first_requires_all_three_gates() -> None:
    """次要①回归锁：此前 do_first 只看 stream_first/intercept，realtime 总
    开关关时仍会抢发首句——now 三者都真才抢发。"""
    assert LLMRequestPipeline._stream_first_do_first(True, True, True) is True
    assert LLMRequestPipeline._stream_first_do_first(True, False, True) is False, (
        "回归锁：realtime 总开关关时不应抢发（此前的 bug）"
    )
    assert LLMRequestPipeline._stream_first_do_first(True, True, False) is False
    assert LLMRequestPipeline._stream_first_do_first(False, True, True) is False


# ===========================================================================
# main.py：M4a 请求侧强制关流 + on_decorating_result 发送抑制落地点
# ===========================================================================


def test_on_message_forces_streaming_off_when_realtime_takeover_active(
    tmp_path,
) -> None:
    calls: list = []

    self_stub = SimpleNamespace(
        _scope_resolver_v1=_scope_resolver(tmp_path),
        config={
            "sylanne_alpha_realtime_chat_enabled": True,
            "sylanne_alpha_realtime_intercept_llm_response": True,
        }
    )
    asyncio.run(
        EmotionalStatePlugin.on_message(
            self_stub,
            _ScopedEv(set_calls=calls),
        )
    )

    assert ("enable_streaming", False) in calls


@pytest.mark.parametrize(
    "cfg",
    [
        {},
        {"sylanne_alpha_realtime_chat_enabled": True},
        {"sylanne_alpha_realtime_intercept_llm_response": True},
    ],
)
def test_on_message_leaves_streaming_alone_when_not_fully_enabled(cfg: dict) -> None:
    calls: list = []

    class _StreamEv:
        def set_extra(self, key: str, value: object) -> None:
            calls.append((key, value))

    self_stub = SimpleNamespace(config=cfg)
    asyncio.run(EmotionalStatePlugin.on_message(self_stub, _StreamEv()))

    assert not any(
        key == "enable_streaming" for key, _value in calls
    ), f"两开关未同时开启时不应碰 enable_streaming (cfg={cfg})"
    assert len(calls) == 1
    key, disabled = calls[0]
    assert key == "_sylanne_transport_scope_v1"
    assert type(disabled) is ResolvedTransportScope
    assert disabled.private_scope_enabled is False
    assert disabled.disabled_reason == "scope_resolver_unavailable"


def _decorate_event(chain: list, *, takeover: bool = True) -> SimpleNamespace:
    result = SimpleNamespace(chain=chain)
    extras = {"_syl_realtime_takeover": takeover}
    return SimpleNamespace(
        unified_msg_origin="sess:decorate",
        get_result=lambda: result,
        get_extra=lambda k, default=None: extras.get(k, default),
    )


def test_suppress_realtime_takeover_clears_pure_plain_chain() -> None:
    event = _decorate_event([Plain("接管分段已在后台发了")])
    self_stub = SimpleNamespace()

    handled = asyncio.run(
        EmotionalStatePlugin._maybe_suppress_realtime_takeover(self_stub, event)
    )

    assert handled is True
    assert event.get_result().chain == [], "纯 Plain 应被清空以抑制框架重发"


def test_suppress_realtime_takeover_leaves_non_plain_chain_alone() -> None:
    rec = Record(file="/tmp/x.wav")
    event = _decorate_event([Plain("配文"), rec])
    self_stub = SimpleNamespace()

    handled = asyncio.run(
        EmotionalStatePlugin._maybe_suppress_realtime_takeover(self_stub, event)
    )

    assert handled is False, "安全网：非 Plain 不吞，交回通用 strip 流程"
    assert event.get_result().chain == [Plain("配文"), rec], "chain 不应被清空/改动"


def test_suppress_realtime_takeover_noop_without_flag() -> None:
    event = _decorate_event([Plain("普通装饰阶段")], takeover=False)
    self_stub = SimpleNamespace()

    handled = asyncio.run(
        EmotionalStatePlugin._maybe_suppress_realtime_takeover(self_stub, event)
    )

    assert handled is False
    assert event.get_result().chain == [Plain("普通装饰阶段")]


# ===========================================================================
# 端到端衔接：on_llm_response 登记候选 → 最终装饰阶段提交文本所有权
# ===========================================================================


def test_end_to_end_takeover_flag_flows_into_decorate_suppression() -> None:
    """最终 chain 仍是纯文本时，装饰阶段才启动 transport 并抑制框架发送。"""

    async def scenario() -> None:
        plugin = _Plugin(
            tempfile.mkdtemp(prefix="rt_e2e_"),
            _cfg(enabled=True, intercept=True),
        )
        pipe = LLMResponsePipeline(plugin)  # type: ignore[arg-type]
        calls = _stub_dispatch(pipe)

        chain = MessageChain()
        chain.chain = [Plain("原始未清理文本")]
        response = LLMResponse(role="assistant", result_chain=chain)
        event = _Ev()
        await pipe._on_llm_response_inner(event, response)

        assert event.get_extra("_syl_realtime_candidate") is True
        assert event.get_extra("_syl_realtime_takeover") is False
        assert calls == [], "最终 chain 尚未完成装饰前不得提前发送"

        assistant_part = SimpleNamespace(text=response.completion_text)
        run_context = SimpleNamespace(
            messages=[
                SimpleNamespace(role="user", content="继续"),
                SimpleNamespace(role="assistant", content=[assistant_part]),
            ]
        )
        shell = object.__new__(EmotionalStatePlugin)
        shell._llm_response_pipeline = pipe
        shell._has_conversation_manager = lambda: False
        await EmotionalStatePlugin.on_agent_done(
            shell,
            event,
            run_context,
            response,
        )

        # 模拟框架在 CloneTTS 等常规装饰器之后，把最终纯 Plain chain 交给
        # Sylanne 的低优先级仲裁器。
        event._result = SimpleNamespace(chain=list(response.result_chain.chain))
        handled = await EmotionalStatePlugin._maybe_suppress_realtime_takeover(
            shell,
            event,
        )

        assert handled is True
        assert event.get_result().chain == []
        assert event.get_extra("_syl_realtime_takeover") is True
        assert len(calls) == 1
        assert assistant_part.text == "原始未清理文本"

    asyncio.run(scenario())


def test_late_tts_record_owns_turn_before_segmented_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """下游装饰器把最终文本变成 Record 时，只能发送语音，不能先发分段文本。"""

    async def scenario() -> None:
        plugin = _Plugin(
            tempfile.mkdtemp(prefix="rt_late_tts_owner_"),
            _cfg(enabled=True, intercept=True),
        )
        sent: list[str] = []

        class Context:
            async def send_message(self, _origin: str, message: object) -> None:
                chain = getattr(message, "chain", None) or getattr(
                    message, "parts", None
                )
                sent.append(str(getattr(chain[0], "text", "")) if chain else "")

        plugin.context = Context()
        pipe = LLMResponsePipeline(plugin)  # type: ignore[arg-type]
        monkeypatch.setattr(
            "sylanne_alpha.llm_response_pipeline.realtime_plan",
            lambda *_args, **_kwargs: {
                "message_parts": [
                    {
                        "index": 0,
                        "text": "写什么插件呀",
                        "delay_before_seconds": 0.0,
                    },
                    {
                        "index": 1,
                        "text": "你最近好像一直在折腾这些",
                        "delay_before_seconds": 0.0,
                    },
                ],
                "message_count": 2,
                "segmentation_source": "model_semantic_beats",
            },
        )
        event = _Ev()
        response = LLMResponse(
            role="assistant",
            completion_text="写什么插件呀\n你最近好像一直在折腾这些",
        )

        await pipe._on_llm_response_inner(event, response)
        assistant_part = SimpleNamespace(text=response.completion_text)
        run_context = SimpleNamespace(
            messages=[
                SimpleNamespace(role="user", content="在写插件 没干啥啊"),
                SimpleNamespace(role="assistant", content=[assistant_part]),
            ]
        )
        shell = object.__new__(EmotionalStatePlugin)
        shell._llm_response_pipeline = pipe
        shell._has_conversation_manager = lambda: False

        await EmotionalStatePlugin.on_agent_done(
            shell,
            event,
            run_context,
            response,
        )

        record = Record(file="/tmp/clonetts.wav")
        event._result = SimpleNamespace(chain=[record])
        handled = await EmotionalStatePlugin._maybe_suppress_realtime_takeover(
            shell,
            event,
        )

        assert handled is False
        assert event.get_result().chain == [record]
        assert sent == [], "最终输出已由 Record 接管时，不得提前发送任何文本气泡"

    asyncio.run(scenario())


def test_sanitizer_precedes_default_tts_and_arbitrator_follows_it() -> None:
    """清洗先于 TTS，输出所有权仲裁晚于 TTS，形成固定三阶段顺序。"""

    from astrbot.core.star.register.star_handler import star_handlers_registry

    handlers = {
        metadata.handler_name: metadata
        for metadata in star_handlers_registry.get_handlers_by_module_name("main")
        if metadata.handler_name
        in {"on_decorating_result", "_on_final_output_arbitration"}
    }
    assert handlers["on_decorating_result"].extras_configs.get("priority") == 1000
    assert handlers["_on_final_output_arbitration"].extras_configs.get("priority") == -1000
