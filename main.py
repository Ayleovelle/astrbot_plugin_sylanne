"""Sylanne-Embodiment -- AstrBot 插件主入口模块。

本模块是 Sylanne 长期对话状态与行为运行时的 AstrBot 插件薄宿主层，职责：
1. 继承 AstrBot Star 基类，注册为 AstrBot 插件
2. 初始化所有子系统（kernel/host/memory/assessor/scheduler/webui 等）
3. 注册 LLM 请求/响应事件钩子，在 LLM 管线中注入情感状态
4. 注册 WebUI 路由，提供 dashboard/API 访问
5. 通过委托模式将大量公共 API 方法分发到子对象

架构说明：
- 实际计算逻辑在 sylanne_alpha/ 子包中
- 本模块主要是胶水代码：事件钩子 → 子系统调用 → 状态持久化
- 大量方法是一行 return 委托到子对象的 stub（不需要注释）
"""

from __future__ import annotations

import hmac
import os
import sys

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

# ---------------------------------------------------------------------------
# 热重载防腐:导入任何 sylanne_alpha 之前,先清掉 sys.modules 里残留的旧 sylanne_alpha*。
# 根因:本插件把插件目录加进 sys.path、用【顶层绝对名】`sylanne_alpha.*` 导入子包,
# 这些 sys.modules 键不带 `data.plugins.<dir>.` 前缀,逃过了 AstrBot 重载时的模块清理
# (star_manager._get_plugin_related_modules 只删该前缀的键)。于是装过旧版的进程热
# 重载/覆盖安装新版时,旧的 sylanne_alpha.* 会赖在 sys.modules 里遮蔽磁盘新文件——
# Python 直接返回缓存,新增符号(如 realtime_flags)报 "cannot import name"。这里主动
# 清一次,强制每次(重)加载都从磁盘读新文件。全新进程无残留 → no-op。
# 仅在非 pytest 下执行:测试进程里其他用例可能已按顶层名导入过 sylanne_alpha,若在此
# 清掉会造成新旧两份同名模块共存(isinstance/类身份断裂),故测试环境跳过(测试不走
# AstrBot 热重载路径,无此问题)。生产由 AstrBot import main 触发,此清理必然先于插件
# 自身的 sylanne_alpha 导入。
if "pytest" not in sys.modules:
    import importlib as _importlib

    for _stale_mod in [
        _k
        for _k in list(sys.modules)
        if _k == "sylanne_alpha" or _k.startswith("sylanne_alpha.")
    ]:
        del sys.modules[_stale_mod]
    _importlib.invalidate_caches()

import asyncio  # noqa: E402
import collections  # noqa: E402
import contextvars  # noqa: E402
import importlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import time  # noqa: E402
from datetime import timedelta, timezone  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

# ---------------------------------------------------------------------------
# AstrBot imports -- 优雅降级：当 astrbot 未安装时提供 stub 实现
# ---------------------------------------------------------------------------
try:
    from astrbot.api import logger  # type: ignore  # noqa: E402
    from astrbot.api.event import (  # type: ignore  # noqa: E402
        AstrMessageEvent,
        MessageChain,
        filter,
    )
    from astrbot.api.message_components import Plain  # type: ignore  # noqa: E402
    from astrbot.api.star import Context, Star, register  # type: ignore  # noqa: E402
    from astrbot.core.utils.astrbot_path import get_astrbot_data_path  # type: ignore  # noqa: E402
except ImportError:
    import logging as _logging  # noqa: E402

    logger = _logging.getLogger("astrbot_plugin_sylanne")  # type: ignore

    class _FakeFilter:
        def command(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def on_llm_request(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def on_llm_response(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def on_agent_begin(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def on_agent_done(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def on_llm_stream_chunk(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def on_decorating_result(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def after_message_sent(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def llm_tool(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def on_using_llm_tool(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def on_llm_tool_respond(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def event_message_type(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        class EventMessageType:
            ALL = "all"
            PRIVATE_MESSAGE = "private"
            GROUP_MESSAGE = "group"

    filter = _FakeFilter()  # type: ignore

    class AstrMessageEvent:  # type: ignore
        pass

    class MessageChain:  # type: ignore
        def __init__(self):
            self.chain = []

        def message(self, text):
            self.chain.append(text)
            return self

    class Plain:  # type: ignore
        def __init__(self, text=""):
            self.text = text

    class Context:  # type: ignore
        pass

    class Star:  # type: ignore
        def __init__(self, context: Any = None):
            self.context = context

    def register(*args, **kwargs):  # type: ignore
        def decorator(cls):
            return cls

        return decorator

    def get_astrbot_data_path() -> Path:  # type: ignore
        return Path.home()


# ---------------------------------------------------------------------------
# Sylanne alpha 子包导入
# ---------------------------------------------------------------------------
from sylanne_alpha import webui_server as _sylanne_webui_server  # noqa: E402
from sylanne_alpha.assessor_async import AsyncAssessor  # noqa: E402
from sylanne_alpha.bounded_dict import BoundedDict  # noqa: E402
from sylanne_alpha.diagnostics_surface import command_surface, memory_surface, reset_surface  # noqa: E402
from sylanne_alpha.message_dispatch import realtime_dispatch, realtime_flags  # noqa: E402
from sylanne_alpha.host import SylanneAlphaHost, SylanneAlphaHostEvent  # noqa: E402
from sylanne_alpha.life_simulation import LifeSimulator  # noqa: E402
from sylanne_alpha.memory_system import MemorySystem  # noqa: E402
from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline  # noqa: E402
from sylanne_alpha.rhythm_learner import RhythmLearner  # noqa: E402
from sylanne_alpha.proactive_scheduler import ProactiveScheduler  # noqa: E402
from sylanne_alpha.proactive_bridge import ProactiveBridge  # noqa: E402
from sylanne_alpha.emotion_spirit_bridge import EmotionSpiritBridge  # noqa: E402
from sylanne_alpha.session_context import SessionContext, RitualRegistry  # noqa: E402
from sylanne_alpha.session_state_store import SessionStateStore  # noqa: E402
from sylanne_alpha.agents import (  # noqa: E402
    SelfCore,
    AutonomyScheduler,
    LifeAgent,
)
from sylanne_alpha.social_field import SocialFieldCollector  # noqa: E402
from sylanne_alpha.llm_response_pipeline import LLMResponsePipeline  # noqa: E402
from sylanne_alpha.public_api import PublicAPI  # noqa: E402
from sylanne_alpha.state_persistence import StatePersistence  # noqa: E402
from sylanne_alpha.memory_facade import MemoryFacade  # noqa: E402
from sylanne_alpha.realtime_dispatch import RealtimeDispatch  # noqa: E402
from sylanne_alpha.background_queue import BackgroundPostQueue  # noqa: E402
from sylanne_alpha.webui_routes import WebUIRoutes  # noqa: E402

# 加载 WebUI dashboard HTML（从 UI/index.html）
_webui_dashboard_path = Path(_PLUGIN_DIR) / "UI" / "index.html"
if _webui_dashboard_path.exists():
    WEBUI_HTML = _webui_dashboard_path.read_text(encoding="utf-8")
else:
    WEBUI_HTML = "<html><body><h1>Sylanne Dashboard unavailable</h1></body></html>"

# AstrBot 热重载时可能重新 import main.py 但保留 sylanne_alpha 子模块，
# 强制 reload WebUI server 模块以确保监听器修复被应用。
# 注意：webui_server 依赖 sylanne_alpha.infra 的符号。热更新（如 1.4.5→1.4.6
# 新增 infra 函数）时，sys.modules 里的 infra 可能仍是旧缓存模块，直接 reload
# webui_server 会因 import 不到新符号而崩溃（见 issue #17）。故先 reload 依赖
# 模块 infra 让新符号到位；整段加兜底：即使 reload 失败也沿用第 132 行已成功
# 导入的模块，避免插件加载崩溃。
try:
    import sylanne_alpha.infra as _sylanne_infra  # noqa: E402

    importlib.reload(_sylanne_infra)
    _sylanne_webui_server = importlib.reload(_sylanne_webui_server)
except Exception as _reload_err:  # noqa: BLE001
    logger.warning(
        f"Sylanne webui_server 热重载失败，沿用已加载模块: {_reload_err}"
    )
start_webui_background = _sylanne_webui_server.start_webui_background
stop_webui_server = _sylanne_webui_server.stop_webui_server

# ---------------------------------------------------------------------------
# 常量定义
# ---------------------------------------------------------------------------
PLUGIN_NAME = "astrbot_plugin_sylanne"
# Release identity — keep in sync with metadata.yaml `version` and the @register() below.
PLUGIN_VERSION = "2.5.0"
PUBLIC_API_VERSION = "1.0"
MAX_LLM_REQUEST_PROMPT_CHARS = 12000
_MAX_PAYLOAD_SERIALIZED_CHARS = 60000
_MAX_UNFINISHED_CONTEXT_CHARS = 2000
_CHINA_TZ = timezone(timedelta(hours=8))

_INTERNAL_LLM_CALL: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "_INTERNAL_LLM_CALL", default=False
)
PROACTIVE_SCHEDULER_WAKE_DELAY_SECONDS = 30.0
# PR-A5：life sim tick 后节流落盘 KV 的最小间隔（秒）。区间 60-180s，
# 默认 90s：既保护崩溃不丢太多事件，又避免每 tick（默认 1800s）都写 IO。
_LIFE_SIM_SAVE_MIN_GAP_SECONDS = 90.0
# PR-H 解耦：关系层独立节流间隔。比 life_sim 短——/bond·/unbond 是用户即时动作，
# 期望几秒内落盘；rel_register 高频累积则靠节流压成稀疏写。
_REL_STATE_SAVE_MIN_GAP_SECONDS = 10.0
PROACTIVE_SCHEDULER_IDLE_DELAY_SECONDS = 1800.0
# T1-04②：RhythmLearner 节流落盘间隔（秒）。由 on_message 高频驱动，节流到与
# life_sim 同量级，避免每条消息都写 KV。
_RHYTHM_LEARNER_SAVE_MIN_GAP_SECONDS = 90.0
# PR-Qzone：说说审计/频率闸状态节流落盘间隔。与 rel_state 同量级——发布/确认
# 都是用户即时动作或低频候选事件，不需要 life_sim 那种 tick 级节流。
_QZONE_AUDIT_SAVE_MIN_GAP_SECONDS = 10.0

from sylanne_alpha.utils import safe_ensure_future  # noqa: E402, F401


_REQUIRED_EMOTION_SERVICE_METHODS = (
    "get_emotion_snapshot",
    "get_emotion_state",
    "get_emotion_values",
    "get_emotion_consequences",
    "get_emotion_relationship",
    "get_emotion_prompt_fragment",
    "build_emotion_memory_payload",
    "inject_emotion_context",
    "observe_emotion_text",
    "get_psychological_screening_snapshot",
    "get_psychological_screening_values",
    "observe_psychological_text",
    "simulate_psychological_update",
    "reset_psychological_screening_state",
    "simulate_emotion_update",
    "reset_emotion_state",
    "get_integrated_self_snapshot",
    "get_integrated_self_prompt_fragment",
    "get_integrated_self_policy_plan",
    "build_integrated_self_replay_bundle",
    "replay_integrated_self_bundle",
    "probe_integrated_self_compatibility",
    "export_integrated_self_diagnostics",
    "get_agent_runtime_diagnostics",
    "get_lifelike_learning_snapshot",
    "get_lifelike_initiative_policy",
    "get_proactive_speech_decision",
    "request_proactive_speech_dispatch",
    "get_realtime_chat_plan",
    "request_realtime_chat_dispatch",
    "observe_user_message_withdrawal",
    "observe_sticker_usage",
    "query_sylanne_memory",
    "get_lifelike_prompt_fragment",
    "observe_lifelike_text",
    "simulate_lifelike_update",
    "reset_lifelike_learning_state",
    "get_personality_drift_snapshot",
    "get_personality_drift_values",
    "get_personality_drift_prompt_fragment",
    "observe_personality_drift_event",
    "simulate_personality_drift_update",
    "reset_personality_drift_state",
    "get_fallibility_snapshot",
    "get_fallibility_values",
    "get_fallibility_prompt_fragment",
    "observe_fallibility_text",
    "simulate_fallibility_update",
    "reset_fallibility_state",
)

_EMOTION_SERVICE_EXPECTED_VERSIONS = {
    "emotion_api_version": "1.0",
    "emotion_schema_version": "astrbot.emotion_state.v2",
    "emotion_memory_schema_version": "astrbot.emotion_memory.v1",
    "personality_profile_schema_version": "astrbot.personality_profile.v1",
    "psychological_screening_schema_version": "astrbot.psychological_screening.v1",
    "integrated_self_schema_version": "astrbot.integrated_self_state.v1",
    "lifelike_learning_schema_version": "astrbot.lifelike_learning_state.v1",
    "personality_drift_schema_version": "astrbot.personality_drift_state.v1",
    "fallibility_state_schema_version": "astrbot.fallibility_state.v1",
}


def get_emotional_state_plugin(context: Any) -> Any:
    """从 AstrBot context 中获取已注册的 Sylanne 插件实例。

    验证插件的 API 版本和必需方法是否完整，不完整则返回 None。
    """
    star_context = getattr(context, "star_context", None)
    if isinstance(star_context, dict) and PLUGIN_NAME in star_context:
        return star_context[PLUGIN_NAME]
    getter = getattr(context, "get_registered_star", None)
    if not callable(getter):
        return None
    metadata = getter(PLUGIN_NAME)
    if not metadata or not getattr(metadata, "activated", True):
        return None
    plugin = getattr(metadata, "star_cls", None)
    if (
        plugin
        and all(
            getattr(plugin, name, None) == value
            for name, value in _EMOTION_SERVICE_EXPECTED_VERSIONS.items()
        )
        and all(
            callable(getattr(plugin, name, None))
            for name in _REQUIRED_EMOTION_SERVICE_METHODS
        )
    ):
        return plugin
    return None


# ---------------------------------------------------------------------------
# StateInjectionBudget -- 跟踪每次 LLM 请求中注入/跳过了哪些状态片段
# ---------------------------------------------------------------------------
class _StateInjectionBudget:
    __slots__ = (
        "session_key",
        "compat_mode",
        "injected",
        "skipped",
        "max_added_chars",
        "max_parts",
        "added_chars",
        "appended",
        "warnings",
        "context_owner",
    )

    def __init__(self, session_key: str = ""):
        self.session_key = session_key
        self.compat_mode = ""
        self.injected: list[dict[str, Any]] = []
        self.skipped: list[dict[str, Any]] = []
        self.max_added_chars: int = 2400
        self.max_parts: int = 8
        self.added_chars: int = 0
        self.appended: list[dict[str, Any]] = []
        self.warnings: list[str] = []
        self.context_owner: str = "sylanne_plugin"


# ---------------------------------------------------------------------------
# EmotionalStatePlugin -- Sylanne-Embodiment 薄宿主层
# ---------------------------------------------------------------------------
def _optional_stream_chunk_filter(**kwargs: Any):
    """AstrBot 部分版本 filter 无 on_llm_stream_chunk → 直通注册。"""
    dec = getattr(filter, "on_llm_stream_chunk", None)
    if dec is None:
        return lambda f: f
    return dec(**kwargs)


def _optional_tool_use_filter(**kwargs: Any):
    """AstrBot 部分版本 filter 无 on_using_llm_tool → 直通注册（不挂钩子，降级为无操作）。"""
    dec = getattr(filter, "on_using_llm_tool", None)
    if dec is None:
        return lambda f: f
    return dec(**kwargs)


def _optional_tool_respond_filter(**kwargs: Any):
    """AstrBot 旧版本无 on_llm_tool_respond 时安全降级为不注册该钩子。"""
    dec = getattr(filter, "on_llm_tool_respond", None)
    if dec is None:
        return lambda f: f
    return dec(**kwargs)


def _optional_agent_done_filter(**kwargs: Any):
    """AstrBot 旧版本无 on_agent_done 时安全降级为不注册该钩子。"""

    dec = getattr(filter, "on_agent_done", None)
    if dec is None:
        return lambda f: f
    return dec(**kwargs)


def _optional_agent_begin_filter(**kwargs: Any):
    """AstrBot 旧版本无 on_agent_begin 时安全降级为不注册该钩子。"""

    dec = getattr(filter, "on_agent_begin", None)
    if dec is None:
        return lambda f: f
    return dec(**kwargs)


def _model_function_tool(**kwargs: Any):
    """Register a model-callable function tool, including zero-argument tools."""
    return filter.llm_tool(**kwargs)


# ---------------------------------------------------------------------------
# v3 shadow：构建期开关的隔离影子（plan Task 13 / design 4.3、14.1、14.2、16.1）
#
# 红线（违反即回退）：
#   - 默认关（build_flags.V3_SHADOW_ENABLED=False，只有 grey 打包才翻）；开着也只观察，
#     绝不改 v2 的 reply/prompt/history/memory/body，绝不多发一次 LLM/tool 调用。
#   - 绝不把 v3 身份写进 event.extra；v3 的 future/task 绝不进 plugin._background_tasks
#     （那份列表的关停顺序归 legacy/v2 所有）。
#   - 每个异常封死在 v3 内，绝不外泄进 v2；v3 fail 时 v2 照常完成。
# 本 facade 只做「宿主边界 + 惰性所有权」：__init__ 纯构造零 IO，仓库/线程池全部推迟到
# initialize()。v3bridge 一律函数内惰性 import（对齐本文件 v2core 的既有写法），import
# 失败只 fail-close v3。
# ---------------------------------------------------------------------------

_V3_MAX_PENDING_TURNS = 256
_V3_SETTLED_HISTORY = 64
_V3_SHADOW_TERMINATE_TIMEOUT_S = 5.0


class _V3PendingTurn:
    """一轮已捕获、待终端结算的不可变宿主事实。"""

    __slots__ = (
        "handle",
        "platform_id",
        "unified_msg_origin",
        "message_id",
        "observation",
        "context",
        "session_ref",
        "speaker_digest",
        "is_group",
        "token",
    )

    def __init__(
        self,
        *,
        handle: Any,
        platform_id: str,
        unified_msg_origin: str,
        message_id: str,
        observation: Any,
        context: Any,
        session_ref: Any,
        speaker_digest: bytes | None,
        is_group: bool | None,
        token: int,
    ) -> None:
        self.handle = handle
        self.platform_id = platform_id
        self.unified_msg_origin = unified_msg_origin
        self.message_id = message_id
        self.observation = observation
        self.context = context
        self.session_ref = session_ref
        self.speaker_digest = speaker_digest
        self.is_group = is_group
        # 单调递增的栅栏令牌：同一 session_key 上后一轮会顶掉前一轮，令牌让"迟到的
        # 终端回调"能认出自己要结算的那轮已经不在了，从而放手而不是错结下一轮。
        self.token = token


class _V3ShadowFacade:
    """插件持有的唯一 v3 对象；构造零 IO，全部失败模式 fail-close v3。"""

    def __init__(self) -> None:
        self.enabled = False
        try:
            from sylanne_alpha.v3bridge.build_flags import V3_SHADOW_ENABLED

            self.enabled = bool(V3_SHADOW_ENABLED)
        except Exception:  # noqa: BLE001 - v3 缺失/损坏一律当关闭，绝不影响 v2 装载
            self.enabled = False
        self.runtime: Any = None
        self.counters: Any = None
        self.accepting = False
        self._identity: Any = None
        self._pending: "collections.OrderedDict[str, _V3PendingTurn]" = collections.OrderedDict()
        self._migration_tasks: dict[Any, asyncio.Task] = {}
        self._deferred_offer_tasks: set[asyncio.Task] = set()
        self._ready_sessions: "collections.OrderedDict[Any, None]" = collections.OrderedDict()
        self._last_speakers: "collections.OrderedDict[Any, bytes]" = collections.OrderedDict()
        self._lifecycle_lock = asyncio.Lock()
        self._initialize_task: asyncio.Task | None = None
        self._terminate_task: asyncio.Task | None = None
        self._migration_gate = asyncio.Semaphore(1)
        self._next_token = 0
        self.settled_actions: collections.deque = collections.deque(maxlen=_V3_SETTLED_HISTORY)
        # 每进程一次性随机身份/密钥：只活在内存，绝不落盘、绝不进 trace。
        self._instance_id = f"sylanne-v3-{os.urandom(8).hex()}"
        self._correlation_secret = os.urandom(32)

    # -- 生命周期 ---------------------------------------------------------

    async def initialize(self, *, root: Any, supervisor_kwargs: dict | None = None) -> bool:
        """Coalesce concurrent starts; caller cancellation cannot cancel startup."""

        async with self._lifecycle_lock:
            if not self.enabled or self.runtime is not None:
                return False
            if self._terminate_task is not None and self._terminate_task.done():
                self._terminate_task = None
            if self._terminate_task is not None and not self._terminate_task.done():
                return False
            if self._initialize_task is None:
                self._initialize_task = asyncio.create_task(
                    self._initialize(root=root, supervisor_kwargs=supervisor_kwargs)
                )
            task = self._initialize_task
        return bool(await asyncio.shield(task))

    async def _initialize(self, *, root: Any, supervisor_kwargs: dict | None) -> bool:
        runtime = None
        try:
            from sylanne_alpha.v3bridge.integration import V3ShadowRuntime
            from sylanne_alpha.v3bridge.session_identity import (
                load_or_create_session_identity_key,
            )
            root_path = Path(root)
            identity = await asyncio.to_thread(
                load_or_create_session_identity_key,
                root_path / "session_identity.key",
            )
            runtime = await asyncio.to_thread(
                lambda: V3ShadowRuntime(
                    root=root_path,
                    plugin_data_root=root_path.parent,
                    plugin_instance_id=self._instance_id,
                    correlation_secret=self._correlation_secret,
                    **(supervisor_kwargs or {}),
                )
            )
            # V3ShadowRuntime.initialize() 内部就是「先 committer.acquire_epoch()，
            # 再造 registry/supervisor 起 worker」的顺序，不要在这里重排。
            await runtime.initialize()
        except BaseException as exc:  # cleanup also covers loop-shutdown cancellation
            if runtime is not None:
                try:
                    await asyncio.shield(runtime.terminate())
                except BaseException:  # noqa: BLE001
                    pass
            self.runtime = None
            self.counters = None
            self.accepting = False
            if isinstance(exc, asyncio.CancelledError):
                raise
            self.enabled = False
            logger.warning(f"Sylanne v3 shadow disabled (initialize failed): {exc}")
            return False
        self.runtime = runtime
        self.counters = runtime.counters
        self._identity = identity
        self.accepting = True
        return True

    def begin_shutdown(self) -> None:
        """同步关闸：v2 的收尾 save 开始 drain 之前，先断掉新的 v3 准入。"""

        self.accepting = False

    async def terminate(
        self,
        *,
        timeout: float = _V3_SHADOW_TERMINATE_TIMEOUT_S,
    ) -> None:
        """Coalesce teardown, but never let wedged v3 IO block plugin shutdown."""

        self.accepting = False
        async with self._lifecycle_lock:
            initialize_task = self._initialize_task
            if (
                self.runtime is None
                and (initialize_task is None or initialize_task.done())
                and self._terminate_task is None
            ):
                return
            if self._terminate_task is None:
                self._terminate_task = asyncio.create_task(self._terminate())
            task = self._terminate_task
        try:
            completed = bool(
                await asyncio.wait_for(asyncio.shield(task), timeout=float(timeout))
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Sylanne v3 shadow terminate timed out; "
                "cleanup remains tracked while plugin teardown continues"
            )
            return
        if not completed:
            async with self._lifecycle_lock:
                if self._terminate_task is task:
                    self._terminate_task = None

    async def _terminate(self) -> bool:
        initialize_task = self._initialize_task
        if initialize_task is not None and not initialize_task.done():
            await asyncio.gather(initialize_task, return_exceptions=True)
        runtime = self.runtime
        if runtime is None:
            return True
        try:
            await self.join_private_tasks()
            await runtime.terminate()
        except Exception as exc:  # noqa: BLE001 - v3 关停失败绝不阻断 v2 关停
            logger.warning(f"Sylanne v3 shadow terminate failed: {exc}")
            return False
        self.runtime = None
        self.counters = None
        self._identity = None
        self._pending.clear()
        self._migration_tasks.clear()
        self._deferred_offer_tasks.clear()
        self._ready_sessions.clear()
        self._last_speakers.clear()
        self._initialize_task = None
        return True

    async def join_private_tasks(self) -> None:
        """Drain migration and deferred-offer tasks owned only by this facade."""

        while True:
            # A task may finish immediately before its done-callback gets an event-loop
            # turn to remove it from the owner collection.  Re-gathering that completed
            # task returns synchronously, which can otherwise spin forever and starve
            # the callback that would remove it.  Prune completed entries explicitly so
            # teardown never depends on callback scheduling order.
            for session_ref, task in tuple(self._migration_tasks.items()):
                if task.done() and self._migration_tasks.get(session_ref) is task:
                    self._migration_tasks.pop(session_ref, None)
            self._deferred_offer_tasks.difference_update(
                task for task in self._deferred_offer_tasks if task.done()
            )
            tasks = tuple(self._migration_tasks.values()) + tuple(self._deferred_offer_tasks)
            if not tasks:
                return
            await asyncio.gather(*tasks, return_exceptions=True)

    def ensure_session(
        self,
        *,
        plugin: Any,
        session_key: str,
        platform_id: Any,
        unified_msg_origin: Any,
    ) -> bool:
        """Start one background seed migration and reserve sequence 1.

        The request path never waits for disk IO. A terminal arriving before the
        migration completes is deferred inside the private v3 task set.
        """

        if not self.accepting or self.runtime is None or self._identity is None:
            return False
        try:
            from sylanne_alpha.v3bridge.limits import MAX_REPOSITORY_SESSIONS

            platform = _v3_text(platform_id)
            origin = _v3_text(unified_msg_origin)
            if not platform or not origin:
                return False
            session_ref = self._identity.session_ref(platform, origin, session_generation=0)
            if session_ref is None:
                return False
            if session_ref in self._ready_sessions:
                self._ready_sessions.move_to_end(session_ref)
                return True
            if session_ref in self._migration_tasks:
                return False
            if len(self._migration_tasks) + len(self._ready_sessions) >= MAX_REPOSITORY_SESSIONS:
                return False
            self.runtime.reserve_migration_sequence(session_ref)
            task = asyncio.get_running_loop().create_task(
                self._migrate_session(plugin, session_key, session_ref)
            )
            self._migration_tasks[session_ref] = task

            def completed(done: asyncio.Task, ref: Any = session_ref) -> None:
                self._migration_tasks.pop(ref, None)
                try:
                    ready = bool(done.result())
                except BaseException:
                    ready = False
                if ready:
                    self._ready_sessions[ref] = None
                    self._ready_sessions.move_to_end(ref)
                    while len(self._ready_sessions) > MAX_REPOSITORY_SESSIONS:
                        self._ready_sessions.popitem(last=False)

            task.add_done_callback(completed)
            return False
        except Exception as exc:  # noqa: BLE001 - migration admission is shadow-only
            logger.debug(f"Sylanne v3 shadow migration scheduling skipped: {exc}")
            return False

    async def _migrate_session(self, plugin: Any, session_key: str, session_ref: Any) -> bool:
        try:
            from sylanne_alpha.v2core.shadow_snapshot import (
                SeedSnapshotUnavailable,
                freeze_seed_snapshot_fallback,
            )
            from sylanne_alpha.v3bridge.effect_committer import CommitStatus
            from sylanne_alpha.v3bridge.migration_coordinator import RecoveryDecision
            from sylanne_alpha.v3core.formula_v1 import FORMULA_DIGEST

            async with self._migration_gate:
                if not self.accepting or self.runtime is None:
                    return False
                runtime = self.runtime
                recovery = await asyncio.to_thread(
                    runtime.recover,
                    session_ref,
                    source_digest=FORMULA_DIGEST,
                    writer_epoch=runtime.epoch,
                )
                if recovery.decision is not RecoveryDecision.FRESH_MIGRATION_REQUIRED:
                    ready = recovery.state is not None
                    if ready:
                        runtime.complete_migration_sequence(session_ref)
                    return ready
                try:
                    seed = await freeze_seed_snapshot_fallback(plugin, session_key)
                except SeedSnapshotUnavailable:
                    return False
                outcome = await asyncio.to_thread(
                    runtime.migrate,
                    session_ref,
                    source_digest=FORMULA_DIGEST,
                    writer_epoch=runtime.epoch,
                    seed_snapshot=seed,
                )
                ready = outcome.status in {
                    CommitStatus.COMMITTED,
                    CommitStatus.ALREADY_MIGRATED,
                }
                if ready:
                    runtime.complete_migration_sequence(session_ref)
                return ready
        except Exception as exc:  # noqa: BLE001 - v3 migration never escapes into v2
            logger.debug(
                f"Sylanne v3 shadow migration skipped: {type(exc).__name__}: {exc}",
                exc_info=True,
            )
            return False

    # -- 请求边界（design 14.1）-------------------------------------------

    def capture_request(
        self,
        *,
        session_key: str,
        platform_id: Any,
        unified_msg_origin: Any,
        message_id: Any,
        text_length: int,
        history_present: bool,
        gap_seconds: Any,
        body: Any,
        addressed: bool = True,
        proactive: bool = False,
        text_warm: float | None = None,
        text_cold: float | None = None,
        text_distress: float | None = None,
        text_question: bool | None = None,
        text_exclaim: float | None = None,
        text_punct: float | None = None,
        text_valence_cue: float | None = None,
        text_engagement_cue: float | None = None,
        sender_id: Any = None,
        is_group: bool | None = None,
    ) -> None:
        """冻结一轮的公开输入事实；不推进 v3 状态，不阻塞 v2。

        context 必须在【捕获时】就定对，不能事后按终端证据倒推：主动轮走的也是大饼的
        LLM 管线、同样触发 on_llm_request，若一律冻成 ADDRESSED，影子学到的就是
        「ADDRESSED ⇒ REACH」这条假规律——群里没点名的环境轮同理会被误标成点名。
        """

        if not self.accepting or self.runtime is None or self._identity is None:
            return
        try:
            from sylanne_alpha.v3bridge.actual_action import ActualAction
            from sylanne_alpha.v3bridge.observation_adapter import build_observation_facts
            from sylanne_alpha.v3core.contracts import TurnContextClass
            from sylanne_alpha.v2core.shadow_snapshot import V2TurnObservationSnapshotV1

            platform = _v3_text(platform_id)
            origin = _v3_text(unified_msg_origin)
            message = _v3_text(message_id)
            if not platform or not origin or not message:
                return
            session_ref = self._identity.session_ref(platform, origin, session_generation=0)
            if session_ref is None:
                return
            try:
                sender = _v3_text(sender_id)
            except Exception:  # noqa: BLE001 - relation becomes unknown, turn remains valid
                sender = ""
            speaker_digest = self._identity.speaker_digest(platform, sender or None)
            # 三个上下文位互斥（快照自己会校验），且必须与 context class 一致。
            is_proactive = bool(proactive)
            is_addressed = bool(addressed) and not is_proactive
            if is_proactive:
                context = TurnContextClass.PROACTIVE
            elif is_addressed:
                context = TurnContextClass.ADDRESSED
            else:
                context = TurnContextClass.AMBIENT
            snapshot = V2TurnObservationSnapshotV1(
                body_warmth=_v3_finite(body, "warmth"),
                body_tension=_v3_finite(body, "tension"),
                text_length=max(0, int(text_length)),
                addressed=is_addressed,
                idle=False,
                proactive=is_proactive,
                history_present=bool(history_present),
                gap_seconds=_v3_gap(gap_seconds),
                text_warm=_v3_optional_finite(text_warm),
                text_cold=_v3_optional_finite(text_cold),
                text_distress=_v3_optional_finite(text_distress),
                text_question=text_question if type(text_question) is bool else None,
                text_exclaim=_v3_optional_finite(text_exclaim),
                text_punct=_v3_optional_finite(text_punct),
                text_valence_cue=_v3_optional_finite(text_valence_cue),
                text_engagement_cue=_v3_optional_finite(text_engagement_cue),
            )
            facts = build_observation_facts(
                snapshot,
                context,
                ActualAction.UNKNOWN,
            )
            handle = self.runtime.capture_request(
                session_ref=session_ref,
                bridge_request_nonce=os.urandom(16).hex(),
                request_attempt=0,
                platform_id=platform,
                unified_msg_origin=origin,
                message_id=message,
            )
            if handle is None:
                return
            self._next_token += 1
            self._pending[session_key] = _V3PendingTurn(
                handle=handle,
                platform_id=platform,
                unified_msg_origin=origin,
                message_id=message,
                observation=(facts.raw_values, facts.previous_action),
                context=context,
                session_ref=session_ref,
                speaker_digest=speaker_digest,
                is_group=is_group if type(is_group) is bool else None,
                token=self._next_token,
            )
            while len(self._pending) > _V3_MAX_PENDING_TURNS:
                self._pending.popitem(last=False)
        except Exception as exc:  # noqa: BLE001 - 捕获失败只丢这一轮影子
            logger.debug(f"Sylanne v3 shadow capture skipped: {exc}")

    # -- 响应边界（design 14.2）-------------------------------------------

    def settle(
        self,
        *,
        session_key: str,
        route_kind: str,
        reply_kind: str | None = None,
        part_count: int = 0,
        after_message_sent: bool = False,
        all_segments_succeeded: bool | None = None,
        proactive_dispatched: bool | None = None,
        token: int | None = None,
    ) -> None:
        """认领这一轮的终端证据并做一次非阻塞 offer；一轮只结算一次。

        token 是可选的栅栏：调用方在【投递开始时】取一次 pending_token()，投递结束
        （成功/失败/取消，可能是好几秒后）再带着它来结算。期间若同一 session_key 上
        已经换成了下一轮，令牌对不上就放手——绝不把下一轮的 handle 认领成本轮的结果，
        也就不会把下一轮真正的终端证据挤掉。不传 token 则退化为"结算当前那轮"。
        """

        if self.runtime is None:
            return
        pending = self._pending.get(session_key)
        if pending is None:
            return  # 没捕获过 / 已结算过 → 重复终端回调天然只算一次
        if token is not None and pending.token != token:
            return  # 迟到的终端回调：它那轮早已不在，这轮不归它
        del self._pending[session_key]
        if not self.accepting:
            return
        try:
            from sylanne_alpha.v2core.shadow_snapshot import V2ResponseCandidateV1
            from sylanne_alpha.v3bridge.actual_action import project_actual_action
            from sylanne_alpha.v3core.contracts import ReactionFacts

            candidate = V2ResponseCandidateV1(
                route_kind=route_kind,
                reply_kind=reply_kind,
                part_count=part_count,
                correlation_proven=True,
                after_message_sent=after_message_sent,
                all_segments_succeeded=all_segments_succeeded,
                proactive_dispatched=proactive_dispatched,
            )
            action = project_actual_action(candidate)
            self.settled_actions.append(action)
            # ``same_sender`` is a response-boundary fact (formula-v2 spec §1.4).
            # A later request can arrive while an earlier response is still in flight;
            # request-time comparison would then use a stale previous speaker.  Compare
            # against the latest *settled* speaker first, and only afterward publish this
            # turn's speaker as the baseline for the next response boundary.
            previous_speaker = self._last_speakers.get(pending.session_ref)
            if pending.is_group is False:
                same_sender: bool | None = True
            elif previous_speaker is None or pending.speaker_digest is None:
                same_sender = None
            else:
                same_sender = hmac.compare_digest(previous_speaker, pending.speaker_digest)
            reaction_facts = ReactionFacts(same_sender=same_sender)
            if pending.speaker_digest is not None:
                self._last_speakers[pending.session_ref] = pending.speaker_digest
                self._last_speakers.move_to_end(pending.session_ref)
                while len(self._last_speakers) > _V3_SETTLED_HISTORY:
                    self._last_speakers.popitem(last=False)
            migration = self._migration_tasks.get(pending.session_ref)
            if migration is None:
                self._offer_pending(pending, action, reaction_facts)
            else:
                task = asyncio.get_running_loop().create_task(
                    self._offer_after_migration(migration, pending, action, reaction_facts)
                )
                self._deferred_offer_tasks.add(task)
                task.add_done_callback(self._deferred_offer_tasks.discard)
        except Exception as exc:  # noqa: BLE001 - 结算失败只丢这一轮影子
            logger.debug(f"Sylanne v3 shadow settle skipped: {exc}")

    def _offer_pending(
        self,
        pending: _V3PendingTurn,
        action: Any,
        reaction_facts: Any,
    ) -> None:
        runtime = self.runtime
        if runtime is None:
            return
        runtime.offer_response(
            handle=pending.handle,
            context=pending.context,
            observation=pending.observation,
            actual_action=action,
            quality_score=None,
            reaction_facts=reaction_facts,
            platform_id=pending.platform_id,
            unified_msg_origin=pending.unified_msg_origin,
            message_id=pending.message_id,
        )

    async def _offer_after_migration(
        self,
        migration: asyncio.Task,
        pending: _V3PendingTurn,
        action: Any,
        reaction_facts: Any,
    ) -> None:
        await asyncio.gather(migration, return_exceptions=True)
        try:
            self._offer_pending(pending, action, reaction_facts)
        except Exception as exc:  # noqa: BLE001 - deferred offer is shadow-only
            logger.debug(f"Sylanne v3 shadow deferred offer skipped: {exc}")

    def has_pending(self, session_key: str) -> bool:
        """这一轮是否还有未结算的捕获（供调用方在多个候选键里挑对的那个）。"""

        return session_key in self._pending

    def pending_token(self, session_key: str) -> int | None:
        """当前待结算那轮的栅栏令牌；没有待结算轮就是 None。"""

        pending = self._pending.get(session_key)
        return None if pending is None else pending.token

    def pending_is_proactive(self, session_key: str) -> bool:
        """待结算的这一轮是不是主动轮（它只能由 REACH 结算，别的终端面必须让开）。"""

        pending = self._pending.get(session_key)
        if pending is None:
            return False
        try:
            from sylanne_alpha.v3core.contracts import TurnContextClass

            return pending.context is TurnContextClass.PROACTIVE
        except Exception:  # noqa: BLE001 - 判不出来就当普通轮
            return False

    def build_local_g2_report(self) -> dict[str, Any]:
        """Build the canonical local-shadow G2 evidence from bounded diagnostics."""

        runtime = self.runtime
        counters = self.counters
        if runtime is None or counters is None or runtime.registry is None:
            raise RuntimeError("local G2 report requires an initialized v3 runtime")

        import hashlib
        import platform

        from sylanne_alpha.v3bridge.build_flags import BUILD_CHANNEL, V3_SHADOW_ENABLED
        from sylanne_alpha.v3core import formula_v1 as formula
        from sylanne_alpha.v3core.canonical import canonical_json_bytes, canonical_sha256

        telemetry = runtime.telemetry.recent()
        registry_stats = runtime.registry.stats()
        isolation_counters = counters.as_dict()
        runtime_fingerprint = {
            "formula_version": formula.FORMULA_VERSION,
            "formula_digest": formula.FORMULA_DIGEST,
            "model_revision": formula.ACTION_MODEL_REVISION,
            "profile_id": formula.FORMULA_V2_PROFILE_ID,
            "python_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
            "math_backend": "scalar-v1",
            "cpu_architecture": platform.machine(),
        }
        runtime_fingerprint_digest = hashlib.sha256(
            b"sylanne.v3.runtime-fingerprint.v1\x00"
            + canonical_json_bytes(runtime_fingerprint)
        ).hexdigest()
        model_fingerprint = {
            "revision": formula.ACTION_MODEL_REVISION,
            "formula_digest": formula.FORMULA_DIGEST,
        }
        model_fingerprint["digest"] = canonical_sha256(model_fingerprint)
        accepted_count = sum(1 for record in telemetry if record.queue_accepted)
        dropped_count = sum(1 for record in telemetry if record.dropped)
        correlated_count = registry_stats.accepted_terminal_claims
        report: dict[str, Any] = {
            "report_kind": "v3_local_shadow_g2_v1",
            "plugin_version": PLUGIN_VERSION,
            "source_channel": "grey" if "grey" in PLUGIN_VERSION.lower() else "stable",
            "build_channel": BUILD_CHANNEL,
            "build_shadow_enabled": bool(V3_SHADOW_ENABLED),
            "formula_fingerprint": {
                "version": formula.FORMULA_VERSION,
                "digest": formula.FORMULA_DIGEST,
            },
            "model_fingerprint": model_fingerprint,
            "runtime_fingerprint": runtime_fingerprint,
            "runtime_fingerprint_digest": runtime_fingerprint_digest,
            "accepted_count": accepted_count,
            "dropped_count": dropped_count,
            "correlated_count": correlated_count,
            "isolation_counters": isolation_counters,
            "passed": (
                accepted_count > 0
                and dropped_count == 0
                and correlated_count > 0
                and counters.all_zero()
            ),
        }
        report["report_digest"] = canonical_sha256(report)
        return report

    @staticmethod
    def _local_g2_report_path_from_environment() -> Path | None:
        key = "SYLANNE_V3_GATE_REPORT"
        if key not in os.environ:
            return None
        raw = os.environ[key]
        if (
            not raw
            or raw != raw.strip()
            or raw.startswith("~")
            or any(character in raw for character in "\x00*?\"<>|")
        ):
            raise ValueError("G2 report path is malformed")
        path = Path(raw)
        if path.name in {"", ".", ".."} or path.suffix.lower() != ".json":
            raise ValueError("G2 report path must name one explicit .json file")
        if path.exists() and not path.is_file():
            raise ValueError("G2 report path points to a non-file target")
        return path

    def write_local_g2_report_from_environment(self) -> dict[str, Any] | None:
        """Write G2 only when an explicit target is requested by the gate command."""

        path = self._local_g2_report_path_from_environment()
        if path is None:
            return None

        from sylanne_alpha.v3core.canonical import canonical_json_bytes, canonical_sha256

        report = self.build_local_g2_report()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_json_bytes(report) + b"\n")
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            body = dict(loaded)
            digest = body.pop("report_digest")
        except (OSError, TypeError, ValueError, KeyError) as exc:
            raise RuntimeError("requested G2 report is missing or malformed") from exc
        if loaded != report or digest != canonical_sha256(body):
            raise RuntimeError("requested G2 report failed canonical validation")
        return report

    @property
    def pending_count(self) -> int:
        return len(self._pending)


def _v3_text(value: Any) -> str:
    return "" if value is None else str(value)


def _v3_finite(body: Any, name: str) -> float | None:
    """只接受有限数；其它一律 None（→ 编码器清有效位，design 14.3）。"""

    if not isinstance(body, dict):
        return None
    value = body.get(name)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _v3_optional_finite(value: Any) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    resolved = float(value)
    return resolved if math.isfinite(resolved) else None


def _v3_gap(value: Any) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        return None  # 生产里 gap 会是 inf（首轮），快照只收有限值
    return value


def _v3_shadow_of(owner: Any) -> Any:
    """从任意持有插件引用的对象上取 facade；取不到就是 None（v3 不在场）。"""

    return getattr(owner, "_v3_shadow", None)


@register(
    "astrbot_plugin_sylanne",
    "2718 Labs",
    "Long-term memory, relational state modelling, and real-time chat for AstrBot.",
    "2.5.0",  # keep in sync with metadata.yaml version + PLUGIN_VERSION
    "https://github.com/Ayleovelle/astrbot_plugin_sylanne",
)
class EmotionalStatePlugin(Star):
    """Sylanne-Embodiment 长期对话状态与行为运行时插件。

    继承 AstrBot Star 基类，作为 AstrBot 插件运行。
    通过事件钩子（on_llm_request/on_llm_response）在 LLM 管线中
    注入对话状态上下文，为回复策略与行为调度提供运行时输入。

    核心子系统（在 __init__ 中初始化）：
    - _hosts: 会话→宿主映射（每个会话一个 SylanneAlphaHost）
    - _async_assessor: 异步 LLM 评估器（评估用户文本的情感维度）
    - _llm_request_pipeline: LLM 请求管线（注入状态到 prompt）
    - _llm_response_pipeline: LLM 响应管线（从回复中提取信号）
    - _proactive_scheduler: 主动发言调度器
    - _social_field: 社交场收集器（群聊氛围感知）
    - _life_simulator: 生命模拟器（idle 时的自主状态演化）
    - _webui_routes: WebUI 路由处理器
    - _webui_lifecycle: WebUI 服务器生命周期管理
    - _memory_systems: 会话→三层记忆系统映射
    - _public_api: 对外公共 API 门面
    """

    emotion_api_version = "1.0"
    emotion_schema_version = "astrbot.emotion_state.v2"
    emotion_memory_schema_version = "astrbot.emotion_memory.v1"
    personality_profile_schema_version = "astrbot.personality_profile.v1"
    psychological_screening_schema_version = "astrbot.psychological_screening.v1"
    integrated_self_schema_version = "astrbot.integrated_self_state.v1"
    humanlike_state_schema_version = "astrbot.humanlike_state.v1"
    lifelike_learning_schema_version = "astrbot.lifelike_learning_state.v1"
    personality_drift_schema_version = "astrbot.personality_drift_state.v1"
    fallibility_state_schema_version = "astrbot.fallibility_state.v1"
    moral_repair_state_schema_version = "astrbot.moral_repair_state.v1"
    group_atmosphere_schema_version = "astrbot.group_atmosphere_state.v1"

    def __init__(self, context: Any = None, config: Any = None):
        super().__init__(context)
        self.config = config or {}
        self._config = self.config
        # 会话态集中存储：所有 session-keyed 容器收拢于此（CP8-P2）。
        # 经语义方法访问，release_session 统一清理。
        self._store = SessionStateStore()
        self._background_tasks: list[asyncio.Task] = []
        # hosts/记忆系统/对话缓冲已迁入 self._store（CP8-P2 批3）
        # 计算日志环形缓冲区（供 WebUI 实时显示）
        self._computation_logs: collections.deque = collections.deque(maxlen=200)
        # WebUI 运行时标识（用于探针验证实例一致性）
        self._webui_runtime_id = f"{int(time.time() * 1000)}-{id(self):x}"
        # 节律学习器：学习用户的交互节奏
        self._rhythm_learner = RhythmLearner(intimacy_threshold=0.6)
        # T1-04②：节奏学习器节流落盘状态（镜像 life_sim 的节流落盘模式）
        self._rhythm_learner_last_save_ts: float = 0.0
        self._rhythm_learner_dirty_in_flight: bool = False
        self.logger = logger
        # 生命模拟器：idle 时自主演化身体状态
        self._life_simulator = LifeSimulator(config=self._config)
        self._life_simulator_started = False
        # PR-A5：life sim 节流落盘状态（tick 间最多 _throttle 秒一次 KV 写）
        self._life_sim_last_save_ts: float = 0.0
        self._life_sim_dirty_in_flight: bool = False
        # PR-H 解耦：关系层独立节流落盘状态（不再折进 life_sim 落盘——
        # 否则 life_sim 关掉时 throttled 路径整段被早返回挡掉，只剩 terminate 兜底）。
        self._rel_state_last_save_ts: float = 0.0
        self._rel_state_dirty_in_flight: bool = False
        # trailing-edge：节流窗内被丢弃的变更标脏，由后续触发补落（防非优雅退出丢尾改）。
        self._rel_state_pending_dirty: bool = False
        self._meltdown_nonces: BoundedDict = BoundedDict(maxsize=50, ttl=300)
        # v2.5.0 入站消息级幂等闸（issue43-repeat v2 修复）：以
        # (unified_msg_origin, 入站 message_id) 为键去重，拦下"同一条入站消息
        # 被处理两个 pass"（平台重投/重连 replay），阻止框架 _save_to_history
        # 在第二 pass 把已悬挂的 user 轮再拼一次、烤成 [user:X, user:X]。
        # 全局单表（非 SessionMap，不进 self._store._reg 清理表）：自身 LRU
        # 有界即可，不按 session 生命周期清理。见 _inbound_dup_gate。
        self._inbound_seen: BoundedDict = BoundedDict(maxsize=1024)
        # M8：主动发言反馈 audit（feedback_pressure 单一数据源）。按 session_key 索引，
        # 值为 deque（_record_dispatch_feedback 写、derive_dispatch_policy 读）。
        # BoundedDict LRU 防会话无限增长；每会话内 deque maxlen 防单会话条目无界。
        self._proactive_dispatch_audit: BoundedDict = BoundedDict(maxsize=100)
        # 社交场收集器：群聊氛围感知
        self._social_field = SocialFieldCollector(config=self._config)
        # PR-Qzone：说说功能审计/频率闸状态 + HTTP session（initialize 时按需建立，
        # terminate 时收；session 建立前 qzone_share._do_publish 会因 None 直接失败，
        # 不阻塞其余子系统初始化）。
        self._qzone_audit = None
        self._qzone_audit_last_save_ts: float = 0.0
        self._qzone_audit_dirty_in_flight: bool = False
        self._qzone_http_session: Any = None
        # 后台投递队列已迁入 self._store（CP8-P2 批2）
        self._background_post_recovered_sessions: set[str] = set()
        self._internal_assessor_llm_inflight: int = 0
        # outreach/origins/candidates/locks/realtime_dispatches 已迁入 self._store（批3）
        self._amnesia_sessions: set[str] = set()
        self._proactive_scheduler_task: asyncio.Task | None = None
        # 子系统初始化：各子系统持有 self 引用，通过委托模式分工
        self._session_ctx = SessionContext(self)
        self._state_persistence = StatePersistence(self)
        # MEM-03 PR-6：记忆门面，薄转发到 _session_ctx（同步 accessor）+
        # _state_persistence（写走单写咽喉），本身不持有新状态。
        self._memory_facade = MemoryFacade(self)
        self._realtime_dispatch = RealtimeDispatch(self)
        self._background_queue = BackgroundPostQueue(self)
        self._webui_routes = WebUIRoutes(self)
        self._memory_system = self._memory_system_for_session("default")
        # 异步评估器：调用 LLM 评估用户文本的情感维度
        self._async_assessor = AsyncAssessor(config=self._config)
        self._llm_response_pipeline = LLMResponsePipeline(self)
        self._llm_request_pipeline = LLMRequestPipeline(self)
        self._public_api = PublicAPI(self)
        # SelfCore 自主生命周期：仅注册 LifeAgent。
        self._self_core = SelfCore(self)
        self._self_core.register(LifeAgent(self))
        # 全局自驱心跳（CP8-P3b）：让她没人说话也演化。initialize 启动、terminate 回收。
        self._autonomy_scheduler = AutonomyScheduler(self, self._self_core)
        # 主动发言调度器：基于身体需求和节律决定是否主动发言
        self._proactive_scheduler = ProactiveScheduler(self)
        # 主动发言桥接器：把意图+生活素材交给大饼插件执行发送
        self._proactive_bridge = ProactiveBridge(self)
        # emotion_spirit 适配桥（检测门控；未装即 no-op，对现有行为零影响）
        self._emotion_spirit_bridge = EmotionSpiritBridge(self)
        # v3 shadow facade（plan Task 13）：纯构造、零 IO——仓库/线程池/epoch 全在
        # initialize() 里拿。默认关（源码/stable 构建 V3_SHADOW_ENABLED=False），
        # 只有 grey 打包生成的 build_flags 才翻开；不是用户可选项，故不进 _conf_schema。
        self._v3_shadow = _V3ShadowFacade()
        self._register_web_apis(context)

        # AstrBot ConversationManager / PersonaManager 集成
        self._conv_mgr = self._init_conversation_manager()
        self._persona_mgr = self._init_persona_manager()

        self._load_config_defaults()
        # WebUI 生命周期管理：先强杀旧监听器（解决热更新时旧实例残留问题），再启动新的
        try:
            import asyncio as _aio
            try:
                loop = _aio.get_running_loop()
                loop.create_task(stop_webui_server())
            except RuntimeError:
                _aio.run(stop_webui_server())
        except Exception:
            pass
        self._webui_lifecycle = _sylanne_webui_server.WebUILifecycle(self)
        self._webui_lifecycle.publish_active_plugin()
        self._webui_lifecycle.start_if_enabled()
        self._webui_lifecycle.schedule_listener_takeover()

    def _register_web_apis(self, context: Any) -> None:
        """向 AstrBot 注册所有 WebUI HTTP 路由（getattr 延迟解析，防版本不一致崩溃）。"""
        if not hasattr(context, "register_web_api"):
            return
        P = PLUGIN_NAME
        wr = self._webui_routes

        # self 上的路由（版本一致性风险低，直接引用）
        core_routes: list[tuple[str, Any, list[str], str]] = [
            (
                f"/{P}/observatory-status",
                self._observatory_route_handler,
                ["GET"],
                "Sylanne observatory readonly status",
            ),
            (
                f"/{P}/memory-settings",
                self._memory_settings_get_handler,
                ["GET"],
                "Sylanne memory settings page data",
            ),
            (
                f"/{P}/memory-settings",
                self._memory_settings_post_handler,
                ["POST"],
                "Update Sylanne memory settings",
            ),
            (
                f"/{P}/lineage-observatory",
                self._lineage_observatory_handler,
                ["GET"],
                "Sylanne lineage observatory readonly",
            ),
        ]
        for path, handler, methods, desc in core_routes:
            context.register_web_api(path, handler, methods, desc)

        # WebUI 路由（跨文件引用，用字符串名 + getattr 防御性解析）
        webui_routes: list[tuple[str, str, list[str]]] = [
            (f"/{P}/webui", "page_handler", ["GET"]),
            (f"/{P}/api/state", "state_handler", ["GET"]),
            (f"/{P}/api/observation_history", "observation_history_handler", ["GET"]),
            (f"/{P}/api/settings", "settings_get_handler", ["GET"]),
            (f"/{P}/api/settings", "settings_post_handler", ["POST"]),
            (f"/{P}/api/computation_logs", "computation_logs_handler", ["GET"]),
            (f"/{P}/api/memory_pools", "memory_pools_handler", ["GET"]),
            (f"/{P}/api/memory_meltdown", "memory_meltdown_handler", ["POST"]),
            (f"/{P}/api/meltdown_nonce", "meltdown_nonce_handler", ["GET"]),
            (f"/{P}/api/memory_sink", "memory_sink_handler", ["GET"]),
            (f"/{P}/api/memory_consolidate", "memory_consolidate_handler", ["POST"]),
            (f"/{P}/api/webui_probe", "probe_handler", ["GET"]),
            (f"/{P}/assets/logo.png", "logo_handler", ["GET"]),
            (f"/{P}/logo.png", "logo_handler", ["GET"]),
            (f"/{P}/dashboard", "dashboard_handler", ["GET"]),
            (f"/{P}/api/config_presets", "config_presets_handler", ["GET"]),
            (f"/{P}/api/export_data", "export_data_handler", ["GET"]),
            (f"/{P}/api/purge_data", "purge_data_handler", ["DELETE"]),
            (f"/{P}/health", "health_handler", ["GET"]),
            (f"/{P}/api/error_stats", "error_stats_handler", ["GET"]),
            (f"/{P}/api/config_export", "config_export_handler", ["GET"]),
            (f"/{P}/api/config_import", "config_import_handler", ["POST"]),
            (f"/{P}/api/widget-state", "widget_state_handler", ["GET"]),
            (f"/{P}/api/v2core_state", "v2core_state_handler", ["GET"]),
            # MEM-03 PR-7：三只读 admin 端点（嵌入式镜像，独立 webui_server 侧见
            # /api/admin/* 的 aiohttp 注册）。
            (f"/{P}/api/admin/inspect", "admin_inspect_handler", ["GET"]),
            (f"/{P}/api/admin/quarantine_view", "admin_quarantine_view_handler", ["GET"]),
            (f"/{P}/api/admin/pending_deletes", "admin_pending_deletes_handler", ["GET"]),
            # Phase 4：生活观测面板（与独立 webui_server 镜像）
            (f"/{P}/api/life/status", "life_status_handler", ["GET"]),
            (f"/{P}/api/life/events", "life_events_handler", ["GET"]),
            (f"/{P}/api/life/projects", "life_projects_handler", ["GET"]),
            (f"/{P}/api/life/audit", "life_audit_handler", ["GET"]),
            (f"/{P}/api/life/diagnostics", "life_diagnostics_handler", ["GET"]),
            (f"/{P}/api/life/controls", "life_controls_handler", ["POST"]),
        ]
        for path, handler_name, methods in webui_routes:
            handler = getattr(wr, handler_name, None)
            if handler is None:
                logger.warning(
                    "WebUI route %s skipped: handler '%s' not found"
                    " — possible version mismatch in webui_routes.py",
                    path, handler_name,
                )
                continue
            context.register_web_api(path, handler, methods, f"Sylanne {handler_name}")

    @property
    def config(self) -> dict[str, Any]:
        try:
            return self._config
        except AttributeError:
            self._config = {}
            return self._config

    @config.setter
    def config(self, value: Any) -> None:
        if isinstance(value, dict):
            self._config = value
        else:
            self._config = dict(value) if value else {}

    # Config helpers (schema contract compatibility)
    def _cfg(self, key: str, default: Any = "") -> Any:
        return self._config.get(key, default)

    def _cfg_bool(self, key: str, default: bool = False) -> bool:
        val = self._config.get(key, default)
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ("true", "1", "yes")
        return bool(val)

    def _cfg_float(
        self,
        key: str,
        default: float = 0.0,
        *,
        min: float | None = None,
        max: float | None = None,
    ) -> float:
        val = self._config.get(key, default)
        try:
            result = float(val)
        except (TypeError, ValueError):
            return default
        if min is not None and result < min:
            logger.warning(
                "Config '%s' value %.4f below min %.4f, using default %.4f",
                key, result, min, default,
            )
            return default
        if max is not None and result > max:
            logger.warning(
                "Config '%s' value %.4f above max %.4f, using default %.4f",
                key, result, max, default,
            )
            return default
        return result

    def _cfg_int(
        self,
        key: str,
        default: int = 0,
        *,
        min: int | None = None,
        max: int | None = None,
    ) -> int:
        val = self._config.get(key, default)
        try:
            result = int(val)
        except (TypeError, ValueError):
            return default
        if min is not None and result < min:
            logger.warning(
                "Config '%s' value %d below min %d, using default %d",
                key, result, min, default,
            )
            return default
        if max is not None and result > max:
            logger.warning(
                "Config '%s' value %d above max %d, using default %d",
                key, result, max, default,
            )
            return default
        return result

    # AstrBot group context awareness detection
    def _detect_astrbot_group_context(self) -> bool:
        return self._state_persistence.detect_astrbot_group_context()

    def _load_config_defaults(self) -> None:
        self._state_persistence.load_config_defaults()

    def _start_webui_if_enabled(self) -> None:
        return self._webui_lifecycle.start_if_enabled()

    def _webui_runtime_info(self) -> dict[str, Any]:
        return self._webui_lifecycle.runtime_info()

    def _iter_loaded_webui_server_modules(self) -> list[tuple[str, Any]]:
        return self._webui_lifecycle.iter_loaded_server_modules()

    async def _stop_stale_webui_server_modules(
        self, *, include_current: bool = False
    ) -> list[str]:
        return await self._webui_lifecycle.stop_stale_server_modules(
            include_current=include_current
        )

    def _assessment_timing(self) -> str:
        timing = str(self._cfg("assessment_timing", "post") or "post").strip().lower()
        if timing in {"pre", "post", "both"}:
            return timing
        return "post"

    # Web API route handlers (memory-settings, lineage-observatory)
    async def _memory_settings_get_handler(self) -> dict[str, Any]:
        return await self._sylanne_memory_settings_page_payload()

    async def _memory_settings_post_handler(self) -> dict[str, Any]:
        from astrbot.api.web import request

        body = await request.json() or {}
        return await self._update_sylanne_memory_settings_from_page(body)

    async def _lineage_observatory_handler(self) -> dict[str, Any]:
        session_key = "default"
        return self._sylanne_lineage_observatory_page_payload(session_key)

    # WebUI route handlers (kept for internal cross-references)
    async def _webui_provider_items(self) -> list[dict[str, Any]]:
        return await self._webui_routes.provider_items()

    def _generate_meltdown_nonce(self, session: str) -> str:
        return self._webui_routes.generate_meltdown_nonce(session)

    def _load_conf_schema(self) -> dict[str, Any]:
        """Load _conf_schema.json from plugin directory."""
        schema_path = Path(_PLUGIN_DIR) / "_conf_schema.json"
        if schema_path.exists():
            try:
                return json.loads(schema_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    async def _sylanne_memory_settings_page_payload(self) -> dict[str, Any]:
        return await self._public_api._sylanne_memory_settings_page_payload()

    async def _update_sylanne_memory_settings_from_page(
        self, body: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._public_api._update_sylanne_memory_settings_from_page(body)

    def _sylanne_lineage_observatory_page_payload(
        self, session_key: str
    ) -> dict[str, Any]:
        return self._public_api._sylanne_lineage_observatory_page_payload(session_key)

    def _understanding_closed_loop_diagnostics(
        self, session_key: str
    ) -> dict[str, Any]:
        return self._public_api._understanding_closed_loop_diagnostics(session_key)

    # Host management
    _MAX_HOSTS = 50
    _shared_encoder = None

    def _host(self, session_key: str) -> SylanneAlphaHost:
        return self._session_ctx.host(session_key)

    def _forget_evolution_session(self, session_key: str) -> None:
        """收口清理某会话的进化层 per-session 状态（CP8-P6 防无界泄漏）。

        进化层状态挂在引擎对象上（非 store 登记的 SessionMap），release_session 碰
        不到，故这里显式 fan-out。两个触发点：① 会话删除回调 ② host LRU 驱逐
        （驱逐后同 key 重建时 _restored 守卫须先清，否则学习成果不再从 KV 恢复）。
        """
        for owner in (
            getattr(self, "_self_core", None),
            getattr(self, "_autonomy_scheduler", None),
            getattr(self, "_proactive_bridge", None),
        ):
            fn = getattr(owner, "forget_session", None)
            if callable(fn):
                try:
                    fn(session_key)
                except Exception as e:
                    logger.debug(f"Sylanne forget_session [{session_key}]: {e}")

    def _memory_system_for_session(self, session_key: str) -> MemorySystem:
        return self._memory_facade.memory_system_for_session(session_key)

    def _memory_system_has_content(self, memory_system: Any) -> bool:
        return self._session_ctx.memory_system_has_content(memory_system)

    def _hydrate_memory_system_from_body_traces(
        self, session_key: str, memory_system: MemorySystem, traces: Any
    ) -> None:
        return self._session_ctx.hydrate_memory_system_from_body_traces(
            session_key, memory_system, traces
        )

    def _known_webui_sessions(self, requested: str = "") -> list[str]:
        return self._session_ctx.known_webui_sessions(requested)

    def _session_key(self, event: Any = None, session_key: str = "") -> str:
        return self._session_ctx.session_key(event, session_key)

    # Core observe lifecycle
    async def observe_request(
        self,
        session_key: str,
        *,
        text: str = "",
        confidence: float = 0.0,
        flags: list[str] | None = None,
        now: float = 0.0,
    ) -> dict[str, Any]:
        return await self._public_api.observe_request(
            session_key, text=text, confidence=confidence, flags=flags, now=now
        )

    async def observe_response(
        self,
        session_key: str,
        *,
        text: str = "",
        confidence: float = 0.0,
        flags: list[str] | None = None,
        now: float = 0.0,
    ) -> dict[str, Any]:
        return await self._public_api.observe_response(
            session_key, text=text, confidence=confidence, flags=flags, now=now
        )

    # Immediate chat
    async def chat_sylanne(
        self, *, session_key: str, text: str = "", now: float = 0.0
    ) -> dict[str, Any]:
        host = self._host(session_key)
        event = SylanneAlphaHostEvent(
            text=text,
            confidence=0.7,
            flags=["safe", "chat_request"],
            now=now or time.time(),
            event_time=self._event_time(now),
        )
        return host.on_chat(event)

    # Command surfaces
    async def emotion(self, *, session_key: str) -> dict[str, Any]:
        return command_surface(self._host(session_key), "emotion")

    async def psych_state(self, *, session_key: str) -> dict[str, Any]:
        return command_surface(self._host(session_key), "psych_state")

    async def humanlike_state(self, *, session_key: str) -> dict[str, Any]:
        return command_surface(self._host(session_key), "humanlike_state")

    async def lifelike_state(self, *, session_key: str) -> dict[str, Any]:
        return command_surface(self._host(session_key), "lifelike_state")

    async def personality_drift_state(self, *, session_key: str) -> dict[str, Any]:
        return command_surface(self._host(session_key), "personality_drift_state")

    async def moral_repair_state(self, *, session_key: str) -> dict[str, Any]:
        return command_surface(self._host(session_key), "moral_repair_state")

    async def integrated_self(self, *, session_key: str) -> dict[str, Any]:
        return command_surface(self._host(session_key), "integrated_self")

    async def shadow_diagnostics(self, *, session_key: str) -> dict[str, Any]:
        return command_surface(self._host(session_key), "shadow_diagnostics")

    async def fallibility_state(self, *, session_key: str) -> dict[str, Any]:
        return command_surface(self._host(session_key), "fallibility_state")

    async def _humanlike_reset_impl(self, session_key: str) -> dict[str, Any]:
        return reset_surface(self._host(session_key), "humanlike_state")

    # Memory
    async def sylanne_memory(
        self, *, session_key: str, query: str = "", limit: int = 5
    ) -> dict[str, Any]:
        return memory_surface(self._host(session_key), query=query, limit=limit)

    async def query_sylanne_memory(
        self, *, session_key: str, query: str = "", limit: int = 5, now: float = 0.0
    ) -> dict[str, Any]:
        return await self._public_api.query_sylanne_memory(
            session_key=session_key, query=query, limit=limit, now=now
        )

    def _get_embedding_provider(self, provider_id: str) -> Any:
        if not provider_id:
            return None
        context = self.context
        if hasattr(context, "get_provider_by_id"):
            return context.get_provider_by_id(provider_id)
        return None

    # Public API facade
    async def observe_emotion_text(
        self,
        session_key: str = "",
        *,
        text: str = "",
        confidence: float = 0.0,
        now: float = 0.0,
        use_llm: bool = True,
        observed_at: float = 0.0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return await self._public_api.observe_emotion_text(
            session_key,
            text=text,
            confidence=confidence,
            now=now,
            use_llm=use_llm,
            observed_at=observed_at,
            **kwargs,
        )

    async def get_emotion_snapshot(
        self, *, session_key: str, include_prompt_fragment: bool = False, **kwargs: Any
    ) -> dict[str, Any]:
        return await self._public_api.get_emotion_snapshot(
            session_key=session_key,
            include_prompt_fragment=include_prompt_fragment,
            **kwargs,
        )

    async def get_emotion_state(
        self, *, session_key: str, as_dict: bool = True, **kwargs: Any
    ) -> Any:
        return await self._public_api.get_emotion_state(
            session_key=session_key, as_dict=as_dict, **kwargs
        )

    async def get_emotion_values(self, *, session_key: str) -> dict[str, float]:
        return await self._public_api.get_emotion_values(session_key=session_key)

    async def build_emotion_memory_payload(
        self,
        event_or_session: Any = None,
        *,
        session_key: str = "",
        query: str = "",
        limit: int = 5,
        memory: Any = None,
        source: str = "",
        written_at: float = 0.0,
        include_raw_snapshot: bool = True,
        include_state_annotations_envelope: bool = True,
        memory_text: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        return await self._public_api.build_emotion_memory_payload(
            event_or_session,
            session_key=session_key,
            query=query,
            limit=limit,
            memory=memory,
            source=source,
            written_at=written_at,
            include_raw_snapshot=include_raw_snapshot,
            include_state_annotations_envelope=include_state_annotations_envelope,
            memory_text=memory_text,
            **kwargs,
        )

    def _embedding_prompt_fragment(
        self, matches: list[dict[str, Any]], query: str = ""
    ) -> str:
        return self._public_api._embedding_prompt_fragment(matches, query)

    async def get_proactive_speech_decision(
        self,
        event_or_session: Any = None,
        *,
        session_key: str = "",
        now: float = 0.0,
        candidate_context: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        return await self._proactive_scheduler.get_speech_decision(
            event_or_session,
            session_key=session_key,
            now=now,
            candidate_context=candidate_context,
            **kwargs,
        )

    async def get_realtime_chat_plan(
        self, session_key: str, text: str, **kwargs
    ) -> dict[str, Any]:
        return await self._public_api.get_realtime_chat_plan(
            session_key, text, **kwargs
        )

    async def request_realtime_chat_dispatch(
        self, session_key: str, text: str
    ) -> dict[str, Any]:
        return realtime_dispatch(session_key, text)

    async def inject_emotion_context(
        self, event: Any = None, request: Any = None, *, session_key: str = ""
    ) -> dict[str, Any]:
        return await self._public_api.inject_emotion_context(
            event, request, session_key=session_key
        )

    async def simulate_emotion_update(
        self,
        *,
        session_key: str,
        text: str = "",
        flags: list[str] | None = None,
        confidence: float = 0.5,
        role: str = "user",
        source: str = "",
        observed_at: float = 0.0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return await self._public_api.simulate_emotion_update(
            session_key=session_key,
            text=text,
            flags=flags,
            confidence=confidence,
            role=role,
            source=source,
            observed_at=observed_at,
            **kwargs,
        )

    # Diagnostics / Export / Control
    async def sylanne_diagnostics(self, *, session_key: str) -> dict[str, Any]:
        host = self._host(session_key)
        return host.diagnostics()

    async def export_sylanne_alpha(self, *, session_key: str) -> dict[str, Any]:
        host = self._host(session_key)
        snapshot = host.snapshot()
        snapshot["session_key"] = session_key
        return snapshot

    async def pause_sylanne(self, *, session_key: str) -> dict[str, Any]:
        from sylanne_alpha.state_persistence import mark_dirty

        host = self._host(session_key)
        host.kernel.body.immunity.paused = True
        mark_dirty("session")
        await self._persist_kernel(session_key, host)
        return host.diagnostics()

    async def resume_sylanne(self, *, session_key: str) -> dict[str, Any]:
        from sylanne_alpha.state_persistence import mark_dirty

        host = self._host(session_key)
        host.kernel.body.immunity.paused = False
        mark_dirty("session")
        await self._persist_kernel(session_key, host)
        return host.diagnostics()

    async def cooldown_sylanne(self, *, session_key: str) -> dict[str, Any]:
        from sylanne_alpha.state_persistence import mark_dirty

        host = self._host(session_key)
        host.kernel.body.immunity.cooldown = max(
            host.kernel.body.immunity.cooldown, 0.5
        )
        mark_dirty("session")
        await self._persist_kernel(session_key, host)
        return host.diagnostics()

    async def reset_sylanne(self, *, session_key: str) -> dict[str, Any]:
        host = self._host(session_key)
        host.kernel = host.runtime.reset(session_key)
        # Also persist the fresh kernel to KV
        if self._has_kv_api():
            try:
                await self.put_kv_data(
                    self._kernel_kv_key(session_key), host.kernel.snapshot()
                )
            except Exception as e:
                logger.warning(f"Sylanne kernel KV persist: {e}", exc_info=True)
        return host.diagnostics()

    async def proactive_sylanne(
        self, *, session_key: str, now: float = 0.0
    ) -> dict[str, Any]:
        return await self._public_api.proactive_sylanne(
            session_key=session_key, now=now
        )

    async def sylanne_smoke(self, *, session_key: str) -> dict[str, Any]:
        host = self._host(session_key)
        return {"ok": True, "session_key": session_key, "turns": host.kernel.turns}

    # -----------------------------------------------------------------------
    # 消息事件监听：捕获所有消息（含未经 LLM 的），更新时间戳和节奏
    # -----------------------------------------------------------------------

    def _advance_inbound_delivery_epoch(self, event: Any, session_key: str) -> None:
        """Register one real inbound message and interrupt an older delivery.

        This hook runs before AstrBot enters its per-session agent lock. That is
        the only point where a newly arrived user message can stop an older reply
        that is still generating or sleeping between bubbles.
        """

        get_extra = getattr(event, "get_extra", None)
        set_extra = getattr(event, "set_extra", None)
        if callable(get_extra):
            try:
                if get_extra("_syl_inbound_registered", False):
                    return
            except Exception:
                pass

        duplicate = False
        key = ""
        seen: Any = None
        registered_new = False
        try:
            umo = str(getattr(event, "unified_msg_origin", "") or "")
            mid = getattr(getattr(event, "message_obj", None), "message_id", None)
            key = (
                umo + "\x00" + mid
                if umo and isinstance(mid, str) and mid.strip()
                else ""
            )
            seen = getattr(self, "_inbound_seen", None)
            # Only pre-register when the event can carry ownership into
            # on_llm_request. Otherwise the legacy gate below would mistake this
            # first legitimate pass for a redelivery.
            if key and seen is not None and callable(set_extra):
                duplicate = key in seen
                if not duplicate:
                    seen[key] = time.time()
                    registered_new = True
        except Exception:
            logger.warning(
                "Sylanne inbound epoch registration failed open",
                exc_info=True,
            )

        if callable(set_extra):
            try:
                set_extra("_syl_inbound_duplicate", duplicate)
                # Commit marker last: _inbound_dup_gate only trusts the pair
                # after both values have been written.
                set_extra("_syl_inbound_registered", True)
            except Exception:
                registered = False
                if callable(get_extra):
                    try:
                        registered = bool(
                            get_extra("_syl_inbound_registered", False)
                        )
                    except Exception:
                        pass
                if registered_new and not registered and seen is not None:
                    try:
                        seen.pop(key, None)
                    except Exception:
                        pass

        if duplicate:
            return

        epochs = getattr(self._store, "conversation_input_epoch", None)
        input_epoch = 0
        if epochs is not None:
            try:
                input_epoch = int(epochs.get(session_key, 0) or 0) + 1
                epochs.set(session_key, input_epoch)
            except Exception:
                logger.warning(
                    "Sylanne inbound epoch advance failed: session=%s",
                    session_key,
                    exc_info=True,
                )
                input_epoch = 0
        if callable(set_extra):
            try:
                set_extra("_syl_input_epoch", input_epoch)
            except Exception:
                pass

        active_turns = getattr(self._store, "segmented_delivery_turns", None)
        if active_turns is None:
            return
        try:
            turn = active_turns.get(session_key)
            interrupt = getattr(turn, "interrupt", None)
            if callable(interrupt):
                interrupt()
        except Exception:
            logger.warning(
                "Sylanne active delivery interrupt failed: session=%s",
                session_key,
                exc_info=True,
            )

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: Any, *args: Any, **kwargs: Any):
        """监听所有消息事件，更新 proactive scheduler 时间戳和节奏学习器。

        *args/**kwargs：吸收 AstrBot 各版本给事件钩子多传的位置/关键字参数
        （v4.26.x 起框架内部会多传若干上下文参数，见 context_utils.call_event_hook
        `handler(event, *args, **kwargs)`）。签名固定为 (event) 会在这些版本上报
        TypeError "takes 2 positional but N given"，故一律用 *args/**kwargs 兜住，
        本插件只用 event。"""
        try:
            # M4a（realtime 完整重做 Model-D）：即时聊天接管开启时强制关闭本轮
            # 流式，让响应侧走非流式档（on_decorating_result 才够得着、能抑制
            # 框架重发）。此处（filter.event_message_type(ALL)，由 ProcessStage
            # 内 star_request_sub_stage 触发）确定运行在 AgentRequestSubStage/
            # InternalAgentSubStage 读取 event.get_extra("enable_streaming")
            # （internal.py:169）之前——见 process_stage/stage.py 的调用顺序：
            # star_request_sub_stage.process 先于 agent_sub_stage.process。
            # 默认两开关皆关时这里零行为（不碰 enable_streaming，流式配置原样）。
            try:
                _realtime_enabled, _realtime_intercept = realtime_flags(self.config)
                if _realtime_enabled and _realtime_intercept:
                    set_extra = getattr(event, "set_extra", None)
                    if callable(set_extra):
                        set_extra("enable_streaming", False)
            except Exception:
                pass
            session_key = self._session_ctx.session_key(event)
            # Call through the class so narrow plugin-host stubs that bind only
            # on_message still exercise the real hook without needing to copy
            # every private helper onto their namespace.
            EmotionalStatePlugin._advance_inbound_delivery_epoch(
                self,
                event,
                session_key,
            )
            now = time.time()
            # v2.5.0 slice-1b（design §8 BLOCKER B1，全矩阵扎实版修正）：主判据
            # 消费——供三写点（货架写/profile 软同步/出生播种，本 slice 货架写
            # 已接线）将来只读的"已认证身份记录"。on_message 覆盖
            # EventMessageType.ALL（含未触发 LLM 的群聊噪音），比 on_llm_request
            # 覆盖面更广。
            # 取值改用 `SessionContext.resolve_authenticated_identity`——只用
            # event 的公开方法（get_sender_id/get_message_type/get_group_id/
            # session_id），不再复用 `raw_bucket_sender_id`（只读裸属性
            # sender_id/user_id，真实 AstrBot 事件从不设这两个属性，在生产上
            # 对**所有**事件恒返回空串，曾让本暂存层永久哑火——连本该天生
            # per-user 的私聊都不例外，详见两个方法各自的文档字符串）。
            # `stash_authenticated_identity` 内部叠加次判据（发言人一致性坍缩）
            # 与"已坍缩 session_key 永久 SKIP"逻辑，本处只负责主判据求值 + 落地。
            # 独立 try/except：本插桩失败绝不能连带吞掉本函数其余的 tempo/proactive
            # 记录逻辑（与下方 rhythm_learner 支路同一收敛纪律）。
            try:
                identity = self._session_ctx.resolve_authenticated_identity(event)
                self._store.stash_authenticated_identity(session_key, identity)
            except Exception:
                pass
            # 更新最后消息时间，供 proactive scheduler 计算沉默时长
            self._store.last_user_message_time.set(session_key, now)
            sched = getattr(self, "_proactive_scheduler", None)
            if sched is not None and hasattr(sched, "record_message_time"):
                sched.record_message_time(session_key, now)
            # T2-07①：喂主动反馈回路——用户真的回应了，把该会话所有 pending
            # outreach 标 answered（此前只有超时会标 unanswered，她学不到"他回我了"）。
            life_sim = getattr(self, "_life_simulator", None)
            if life_sim is not None and hasattr(life_sim, "record_user_response"):
                life_sim.record_user_response(session_key, now)
            # T1-04①：复活 RhythmLearner 画像学习（内部已含 _record_tempo，
            # 始终记录 tempo、亲密度不够时跳过画像学习——不再只调低层 _record_tempo）。
            # 用 hosts.get() 非创建式查询：on_message 对 EventMessageType.ALL 触发，
            # 若改用 self._host() 会为从未真正对话过的会话（如纯群聊噪音）也提前建
            # host/记忆系统，这是本次纯接线之外的资源副作用，不做。没有 host 时退化
            # engine_obs={}（is_intimate 判非亲密），tempo 仍照常记录。
            try:
                message_text = str(getattr(event, "message_str", "") or "")
                engine_obs: dict[str, float] = {}
                try:
                    existing_host = self._store.hosts.get(session_key)
                    kernel = getattr(existing_host, "kernel", None)
                    if kernel is not None:
                        engine_obs = kernel.computation.engine.observe()
                except Exception:
                    # 宿主/内核链路部分初始化时的任何异常都退化为 engine_obs={}，
                    # 绝不能让 tempo 记录（observe_user_message）跟着一起被吞掉。
                    engine_obs = {}
                self._rhythm_learner.observe_user_message(
                    session_key, message_text, now, engine_obs
                )
                # T2-06④：早安/晚安等重复问候模式观察（关键词兜底识别，见
                # session_context._detect_greeting_ritual_pattern 的偏差说明）。
                self._session_ctx.detect_and_observe_ritual_from_text(
                    session_key, message_text, now
                )
            except Exception:
                pass
            # T1-04②：节流落盘节奏学习器状态（镜像 life_sim 的节流落盘模式）。
            await self._rhythm_learner_throttled_save()
        except Exception:
            pass

    # on_llm_request 钩子：在 LLM 请求发出前注入情感状态上下文
    @filter.on_llm_request(desc="注入 Sylanne 情感计算上下文到 LLM prompt")
    async def on_llm_request(
        self, event: Any, request: Any, *args: Any, **kwargs: Any
    ) -> None:
        # *args/**kwargs：兜住 AstrBot 各版本多传的钩子参数（req 仍固定为第 2 位，
        # 见 4.26.5 文档 (event, req: ProviderRequest)）；否则新版报 TypeError。
        try:
            await self._on_llm_request_inner(event, request)
        except Exception as e:
            logger.error(f"Sylanne on_llm_request error: {e}", exc_info=True)
            return

    def _session_lock(self, session_key: str) -> asyncio.Lock:
        return self._session_ctx.session_lock(session_key)

    def _inbound_dup_gate(self, event: Any) -> bool:
        """True = 本条入站消息是重复二次投递（同一 (umo, message_id) 已见过），
        调用方应 stop_event 并早退。

        判定"可去重 id"：仅当 unified_msg_origin 与 message_obj.message_id 都
        是非空稳定串时才登记/比对；否则（None/空/非串——如 webchat 前端未带 id、
        或任何适配器缺省）直接放行、不登记，宁可漏 dedup 也不误杀合法消息。

        本闸只在 on_llm_request（main.py:_on_llm_request_inner 顶端）调用，该
        钩子由框架 internal.py 在 per-session 锁（session_lock_manager）持有
        窗口内触发；notice/request 等 message_str 为空的事件走不到这个钩子
        （internal.py 的 has_valid_message/has_media_content 早退），故它们的
        uuid4 型 message_id 天然不会进这张表——不需要额外甄别事件类型。

        绝不对消息文本做任何比对去重——那会回归 state_persistence.py:2499
        注释警告的"用户在 bot 沉默时连发相同文字被误杀"，本轮禁区。
        """
        try:
            # on_message 已在 AstrBot 的 per-session agent 锁之前登记了这条入站
            # 消息。复用事件级判定，避免合法 on_llm_request 被自己的登记误杀；
            # 独立重投递事件则携带 duplicate=True，在这里正常 stop。
            get_extra = getattr(event, "get_extra", None)
            if callable(get_extra) and get_extra(
                "_syl_inbound_registered", False
            ):
                return bool(get_extra("_syl_inbound_duplicate", False))

            umo = str(getattr(event, "unified_msg_origin", "") or "")
            mid = getattr(getattr(event, "message_obj", None), "message_id", None)
            if not umo or not isinstance(mid, str) or not mid.strip():
                return False  # 豁免：无稳定 id，宁漏 dedup 不误杀
            key = umo + "\x00" + mid
            # check-then-set：中间无 await，单线程协作式原子；外层框架 per-session
            # 锁（internal.py:209）再对同 umo 的重复 pass 做一层串行化保障。
            if key in self._inbound_seen:
                return True
            self._inbound_seen[key] = time.time()
            return False
        except Exception:
            # 闸自身异常绝不阻断正常请求（fail-safe 向放行）；但要留信号——
            # 否则闸内潜在缺陷会让去重静默失效、退回重复 bug 而无人察觉。
            logger.warning("Sylanne inbound dedup gate error (failing open)", exc_info=True)
            return False

    async def _on_llm_request_inner(self, event: Any, request: Any) -> None:
        # v2.5.0 入站消息级幂等闸：必须在任何早退（尤其 should_express 静默
        # return）之前拦截，否则 SILENT 轮的 message_id 不会入集，漏掉最可能
        # 触发悬挂重复的链路。命中即 stop_event + 早退，框架不再跑
        # build/run_agent/_save_to_history，第二 pass 净写 0 条。
        if self._inbound_dup_gate(event):
            logger.info(
                "Sylanne inbound dedup: dropped re-delivered message umo=%s mid=%s",
                getattr(event, "unified_msg_origin", ""),
                getattr(getattr(event, "message_obj", None), "message_id", None),
            )
            stop_event = getattr(event, "stop_event", None)
            if callable(stop_event):
                try:
                    stop_event()
                except Exception:
                    pass
            return
        # 2.4.1 err 轮兜底（三态标记，第一态）：标记"本轮确实发起了 LLM 请求"。
        # 三态语义（after_message_sent 侧消费，见 _on_after_message_sent_err_backfill）：
        #   None  = 本轮压根没走 LLM 请求（纯指令 / 被前置插件拦截）-> 绝不补写 user
        #   False = LLM 请求跑过，但 on_llm_response 从未触发（provider 全挂的 err 轮）-> 补写
        #   True  = on_llm_response 跑过（正常/SILENT/异常兜底都已在其 finally 里处理）-> 不补写
        # 若只用 truthy 判定，None 会被误当作 False，非 LLM 轮会盲补一条 user 进历史。
        set_extra = getattr(event, "set_extra", None)
        if callable(set_extra):
            try:
                set_extra("_syl_resp_handled", False)
            except Exception:  # 标记失败绝不阻断请求管线
                pass
        # v2core PERCEPT 在请求管线内执行（碎片合并 + SFPD 判定之后），
        # 避免早跑 PERCEPT 与合并文本不一致，以及群聊静默时心象已注入却无 tick。
        return await self._llm_request_pipeline._on_llm_request_inner(event, request)

    async def _process_llm_request_final(
        self,
        event: Any,
        request: Any,
        message_text: str,
        session_key: str,
        realtime_enabled: bool,
        intercept: bool,
    ) -> None:
        return await self._llm_request_pipeline._process_llm_request_final(
            event,
            request,
            message_text,
            session_key,
            realtime_enabled,
            intercept,
        )

    def _schedule_buffer_persist(self, session_key: str) -> None:
        self._state_persistence.schedule_buffer_persist(session_key)

    def _schedule_kernel_persist(self, session_key: str) -> None:
        self._state_persistence.schedule_kernel_persist(session_key)

    async def _flush_pending_kernel_persists(self) -> None:
        await self._state_persistence.flush_pending_kernel_persists()

    async def _do_buffer_persist(self, session_key: str) -> None:
        await self._state_persistence._do_buffer_persist(session_key)

    def _restore_buffers_on_boot(self) -> None:
        self._state_persistence.restore_buffers_on_boot()

    async def _background_observe_request(self, session_key: str, text: str) -> None:
        return await self._llm_request_pipeline._background_observe_request(
            session_key, text
        )

    async def _compress_memories(self, session_key: str, items: list) -> None:
        return await self._llm_request_pipeline._compress_memories(session_key, items)

    # Memory v2: conversation buffer flush + consolidation + reconsolidation

    async def _flush_conversation_to_l1(self, session_key: str) -> None:
        return await self._llm_request_pipeline._flush_conversation_to_l1(session_key)

    async def _session_idle_check_loop(self) -> None:
        return await self._llm_request_pipeline._session_idle_check_loop()

    async def _consolidation_loop(self) -> None:
        return await self._llm_request_pipeline._consolidation_loop()

    async def _trigger_consolidation(self, session_key: str) -> None:
        """手动触发一次 consolidation 评估（WebUI 按钮调用）。"""
        mem_sys = self._memory_system_for_session(session_key)
        if not mem_sys or not list(mem_sys._l1):
            return
        try:
            await self._llm_request_pipeline._run_consolidation(session_key, mem_sys)
        except Exception as e:
            logger.warning(f"Manual consolidation failed: {e}")

    async def _run_consolidation(
        self, session_key: str, memory_system: MemorySystem
    ) -> None:
        return await self._llm_request_pipeline._run_consolidation(
            session_key, memory_system
        )

    async def _reconsolidation_rewrite(
        self, session_key: str, memory_system: MemorySystem
    ) -> None:
        return await self._llm_request_pipeline._reconsolidation_rewrite(
            session_key, memory_system
        )

    def _recent_context_lines(self, session_key: str) -> list[str]:
        return self._llm_request_pipeline._recent_context_lines(session_key)

    # Assessor LLM callback
    async def _assessor_llm_call(self, prompt: str) -> str:
        return await self._llm_request_pipeline._assessor_llm_call(prompt)

    async def _main_assessor_llm_call(self, prompt: str) -> str:
        return await self._llm_request_pipeline._main_assessor_llm_call(prompt)

    async def _summarizer_llm_call(self, prompt: str) -> str:
        return await self._llm_request_pipeline._summarizer_llm_call(prompt)

    # Life Simulator callbacks
    async def _life_sim_llm_call(self, prompt: str) -> str:
        return await self._llm_request_pipeline._life_sim_llm_call(prompt)

    async def _life_sim_outreach(self, reason: str, mood: str) -> None:
        return await self._llm_request_pipeline._life_sim_outreach(reason, mood)

    async def _generate_outreach_message(self, reason: str, mood: str) -> str:
        return await self._llm_request_pipeline._generate_outreach_message(reason, mood)

    def _life_sim_emotion(self) -> dict[str, float]:
        return self._llm_request_pipeline._life_sim_emotion()

    # on_llm_response 钩子：在 LLM 回复后提取信号、更新状态、触发分段回复
    @filter.on_llm_response(desc="处理 LLM 回复，更新情感状态和记忆")
    async def on_llm_response(
        self, event: Any, response: Any, *args: Any, **kwargs: Any
    ) -> None:
        # *args/**kwargs：兜住 AstrBot 各版本多传的钩子参数（resp 仍固定为第 2 位，
        # 见 4.26.5 文档 (event, resp: LLMResponse)）；否则新版报 TypeError。
        try:
            await self._on_llm_response_inner(event, response)
        except Exception as e:
            logger.error(f"Sylanne on_llm_response error: {e}", exc_info=True)
            return

    @_optional_agent_begin_filter()
    async def on_agent_begin(
        self,
        event: Any,
        run_context: Any,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """在 provider 调用前建立不写穿透会话 DB 的临时历史视图。"""

        try:
            self._llm_response_pipeline.on_agent_begin(event, run_context)
        except Exception as e:
            logger.warning(
                f"Sylanne on_agent_begin history projection failed: {e}",
                exc_info=True,
            )

    # 必须先于可能 stop 的普通 hook 恢复 provider-only 历史。
    @_optional_agent_done_filter(priority=1000)
    async def on_agent_done(
        self,
        event: Any,
        run_context: Any,
        response: Any,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """绑定本轮历史对象；已启动的分段投递则提交真实送达文本。"""

        try:
            self._llm_response_pipeline.on_agent_done(event, run_context, response)
        except Exception as e:
            logger.warning(f"Sylanne on_agent_done scrub failed: {e}", exc_info=True)

        delivered_override: str | None = None
        delivery_deferred = False
        try:
            bind_delivery = getattr(
                self._llm_response_pipeline,
                "bind_segmented_delivery_context",
                None,
            )
            if callable(bind_delivery):
                delivery_deferred = bool(
                    bind_delivery(
                        event,
                        run_context,
                        response,
                    )
                )
            settle_delivery = getattr(
                self._llm_response_pipeline,
                "settle_segmented_delivery_history",
                None,
            )
            if not delivery_deferred and callable(settle_delivery):
                delivered_override = await settle_delivery(
                    event,
                    run_context,
                    response,
                )
        except Exception as e:
            # A ledger turn must fail closed. Keeping the provider's complete
            # draft here would teach the next turn words that transport never sent.
            event_extra = getattr(
                self._llm_response_pipeline,
                "_event_extra",
                None,
            )
            turn = (
                event_extra(
                    event,
                    getattr(
                        self._llm_response_pipeline,
                        "_DELIVERY_TURN_EXTRA",
                        "_syl_segmented_delivery_turn",
                    ),
                    None,
                )
                if callable(event_extra)
                else None
            )
            if turn is not None:
                rewrite_assistant = getattr(
                    self._llm_response_pipeline,
                    "_rewrite_current_assistant",
                    None,
                )
                if callable(rewrite_assistant):
                    rewrite_assistant(run_context, "")
                delivered_override = ""
            logger.warning(
                f"Sylanne on_agent_done delivery settlement failed: {e}",
                exc_info=True,
            )

        try:
            assistant_text = (
                delivered_override
                if delivered_override is not None
                else self._canonical_assistant_text(run_context, response)
            )
            await self._backfill_turn_if_framework_skips(
                event,
                response,
                assistant_override=assistant_text,
            )
        except Exception as e:
            logger.warning(
                f"Sylanne on_agent_done turn finalization failed: {e}",
                exc_info=True,
            )

    # 只对"把文本念出来/发出去"类工具清理 text 参数（白名单）。绝不碰 FileWrite/
    # FileEdit 的 content、execute_python 的 code 等——那些 strip/截断会静默写坏文件/代码。
    _DIRECT_DELIVERY_TOOL_NAMES = (
        "clone_tts",
        "tts",
        "send_message_to_user",
        "send_message",
    )
    _DIRECT_DELIVERY_EXTRA = "_syl_direct_delivery"

    @staticmethod
    def _visible_text(value: Any) -> str:
        if not isinstance(value, str):
            return ""
        return value if any(c.isprintable() and not c.isspace() for c in value) else ""

    def _assistant_content_text(self, content: Any) -> str:
        if isinstance(content, str):
            return self._visible_text(content)
        if not isinstance(content, (list, tuple)):
            return ""
        parts: list[str] = []
        for part in content:
            value = part.get("text") if isinstance(part, dict) else getattr(part, "text", None)
            if isinstance(value, str):
                parts.append(value)
        return self._visible_text("".join(parts))

    def _canonical_assistant_text(self, run_context: Any, response: Any) -> str:
        messages = getattr(run_context, "messages", None)
        if isinstance(messages, (list, tuple)):
            for message in reversed(messages):
                if isinstance(message, dict):
                    role = message.get("role", "")
                    content = message.get("content", "")
                else:
                    role = getattr(message, "role", "")
                    content = getattr(message, "content", "")
                if role == "user":
                    break
                if role == "assistant" and (
                    text := self._assistant_content_text(content)
                ):
                    return text

        role = getattr(response, "role", "assistant") or "assistant"
        if role != "assistant":
            return ""
        return self._visible_text(getattr(response, "completion_text", ""))

    @_optional_tool_use_filter(desc="语音/发言类工具调用前清理 text（防 thinking 进 TTS）")
    async def on_using_llm_tool(self, event: Any, tool: Any, tool_args: Any) -> None:
        """path3 兜底：模型把要"说"的内容打包进【语音/发言类】工具参数（如 clone_tts 的
        text）时，绕过了 on_llm_response 的剥离。这里在工具执行【前】就地清理。tool_args 是
        executor 实际消费的同一 dict（tool_loop_agent_runner:1075/1083 验证），就地改即生效。

        【白名单】只处理 _DIRECT_DELIVERY_TOOL_NAMES——别的工具（文件写入/代码执行）的文本参数原样
        放过，否则 strip/截断会静默写坏文件（M3 审查）。
        - 剥 thinking/draft 块：核心安全项——别让内心独白被念成语音/发出去。
        - 极端超长才句末截断：TTS 只长度有害（数分钟音频）。strip 后为空则不写回（n1）。
        """
        try:
            if not isinstance(tool_args, dict) or not tool_args:
                return
            tool_name = tool if isinstance(tool, str) else str(getattr(tool, "name", "") or "")
            if tool_name not in self._DIRECT_DELIVERY_TOOL_NAMES:
                return  # 非语音/发言类工具：一概不碰，避免误伤文件/代码参数
            from sylanne_alpha.message_dispatch import strip_draft_blocks, truncate_at_sentence

            _HARD_MAX = 1200  # 极端兜底；正常语音远不到
            spoken_text = ""
            for key in ("text", "content", "message", "msg"):
                val = tool_args.get(key)
                if not isinstance(val, str) or not val.strip():
                    continue
                cleaned = strip_draft_blocks(val)
                cleaned = truncate_at_sentence(cleaned, _HARD_MAX)
                # 全是 thinking 被剥空：不写回（喂 TTS 空串会报错/产 0 长音频）
                if not cleaned.strip():
                    logger.warning(
                        "Sylanne tool-arg %s 剥后为空，保留原文交工具自行处理: tool=%s",
                        key, tool_name,
                    )
                    continue
                if cleaned != val:
                    tool_args[key] = cleaned
                    logger.info(
                        "Sylanne tool-arg cleaned: tool=%s key=%s %d→%d chars",
                        tool_name, key, len(val), len(cleaned),
                    )
                spoken_text = cleaned
            set_extra = getattr(event, "set_extra", None)
            if spoken_text and callable(set_extra):
                set_extra(self._DIRECT_DELIVERY_EXTRA, (tool_name, spoken_text))
        except Exception as e:
            # 安全闸降级必须可见（m1）：不静默吞到 debug
            logger.warning(f"Sylanne on_using_llm_tool clean failed: {e}", exc_info=True)

    @_optional_tool_respond_filter(
        priority=1000,
        desc="直接发言工具返回后终结本轮历史",
    )
    async def on_llm_tool_respond(
        self,
        event: Any,
        tool: Any = None,
        tool_args: Any = None,
        tool_result: Any = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """直接发言工具终结后，补齐框架不会保存的完整回合。"""
        try:
            if tool_result is not None:
                return
            tool_name = (
                tool if isinstance(tool, str) else str(getattr(tool, "name", "") or "")
            )
            if tool_name not in self._DIRECT_DELIVERY_TOOL_NAMES:
                return
            if self._agent_run_done(event) is not True:
                return

            get_extra = getattr(event, "get_extra", None)
            delivery = (
                get_extra(self._DIRECT_DELIVERY_EXTRA) if callable(get_extra) else None
            )
            if not (
                isinstance(delivery, tuple)
                and len(delivery) == 2
                and delivery[0] == tool_name
            ):
                return
            assistant_text = self._visible_text(delivery[1])
            if not assistant_text:
                return
            await self._backfill_turn_if_framework_skips(
                event,
                None,
                assistant_override=assistant_text,
            )
        except Exception as e:
            logger.warning(
                f"Sylanne on_llm_tool_respond turn finalization failed: {e}",
                exc_info=True,
            )

    @filter.on_decorating_result(priority=1000)
    async def on_decorating_result(self, event: Any, *args: Any, **kwargs: Any) -> None:
        """Stage 8 前置清洗：在 TTS/图片装饰器消费文本前移除内部控制内容。

        *args/**kwargs：兜住 AstrBot 各版本多传的钩子参数，避免新版 TypeError。
        """
        try:
            from sylanne_alpha.message_dispatch import strip_draft_blocks

            result = event.get_result()
            if result is None:
                return
            chain = getattr(result, "chain", None)
            if not chain:
                return
            cleaned_chain = []
            for seg in chain:
                if isinstance(seg, Plain):
                    text = strip_draft_blocks(seg.text)
                    text = self._llm_response_pipeline.scrub_owned_semantic_markers(
                        event, text
                    )
                    if text:
                        seg.text = text
                        cleaned_chain.append(seg)
                else:
                    cleaned_chain.append(seg)
            # 切片赋值：保留 chain 的对象身份（若为 list 子类/MessageChain
            # 包装），避免下游依赖原类型方法时 AttributeError
            if isinstance(result.chain, list):
                result.chain[:] = cleaned_chain
            else:
                result.chain = cleaned_chain
        except Exception as e:
            logger.warning(
                f"Sylanne on_decorating_result strip failed: {e}", exc_info=True
            )

    @filter.on_decorating_result(priority=-1000)
    async def _on_final_output_arbitration(
        self,
        event: Any,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """在普通装饰器完成后决定由框架 chain 还是 Sylanne 分段 transport 发送。"""

        try:
            # 主动消息和即时聊天都必须等 TTS/图片等装饰完成后再认领输出，
            # 否则会先直发文字，稍后又由框架发送 Record/Image。
            if await self._maybe_takeover_segments(event):
                return
            await self._maybe_suppress_realtime_takeover(event)
        except Exception as e:
            logger.warning(
                f"Sylanne final output arbitration failed: {e}",
                exc_info=True,
            )

    def _v3_settle_ordinary(self, event: Any) -> None:
        """ordinary 输出的 v3 终端证据（默认关时是空操作）。

        恒 UNKNOWN：AstrBot 4.26.5 的 after_message_sent 只证明"尝试发过"，不证明送达。
        实时接管轮显式跳过——那条路由的证据由 _dispatch_segmented_parts 的全段成功回调
        结算成 SPEAK，这里若抢先认领就会把它压成 UNKNOWN。
        """

        facade = getattr(self, "_v3_shadow", None)
        if facade is None:
            return
        try:
            get_extra = getattr(event, "get_extra", None)
            if callable(get_extra) and get_extra("_syl_realtime_takeover", None) is True:
                return
            session_key = self._session_ctx.session_key(event)
            # 让路①：主动轮。大饼的 check_and_chat 也走 RespondStage，本钩子照样会响；
            # 若在这里认领，proactive_bridge 的 REACH 就永远落不到 —— 主动轮只能由它结算。
            if facade.pending_is_proactive(session_key):
                return
            # 让路②：接管轮的兜底判据。上面那个 extra 标记是 best-effort 写的（写失败被
            # 刻意吞掉），标记丢了就只剩这条：本会话有在飞的分段任务 = 投递证据归分段回调，
            # 这里不能抢着记成 UNKNOWN。
            task = self._store.segmented_tasks.get(session_key)
            if task is not None and not task.done():
                return
        except Exception as e:  # noqa: BLE001 - 取不到会话只丢这一轮影子
            logger.debug(f"Sylanne v3 shadow ordinary settle skipped: {e}")
            return
        facade.settle(
            session_key=session_key,
            route_kind="ORDINARY_TEXT",
            reply_kind="SPEAK",
            part_count=1,
            after_message_sent=True,
        )

    @filter.after_message_sent()
    async def _on_after_message_sent_err_backfill(
        self, event: Any, *args: Any, **kwargs: Any
    ) -> None:
        """终结轮兜底：框架本轮不落库时把 user 补进会话历史（唯一能覆盖 provider
        全挂 err 轮的插件挂点——那条路径 step() 不调 on_agent_done，故 on_llm_response
        及其 finally 补写根本不触发，见 tool_loop_agent_runner.py:772-788 /
        astr_agent_hooks.py:32-36；框架 _save_to_history 又因 role != 'assistant'
        早退 internal.py:453-455 不落库，该轮 user 谁都不写）。

        锁内安全（非跨锁 fire-and-forget 老路）：AstrBot scheduler 是洋葱模型，
        RespondStage 在 ProcessStage 生成器【挂起于 yield】时嵌套运行，此刻
        internal.py:209 的 session_lock 仍持有（canary E2 实测 holding==1、补写落库
        序先于框架 save）。故与框架落库同锁同轮、补写在前，是该轮唯一 user 写者。

        两道门 + 一道兜底（缺一不可，红线闸 Finding #1 的教训）：
          门1·三态标记 _syl_resp_handled：None=没走 LLM 请求（纯指令/被拦截）→绝不补
          （若用 truthy 判定，None 会被当 False 盲补）；True=on_llm_response 跑过→不补；
          False=请求跑过而响应钩子未触发。
          门2·终态门 runner.done()：关键——False 不只是 err 轮，还覆盖【整个 tool 循环
          中间步】：模型带 preamble 文本调工具时，中间步也会发消息、触发本钩子，而此刻
          flag 仍 False。仅当 agent runner 到终态（DONE/ERROR）才放行，挡掉中间步（及
          第三方 runner 每轮 flag=False 的污染）；取不到 runner 则跳过（宁丢不重）。
        终态门仍不足以独挡（buffered 模式 err 先发、合并 preamble 后发，两次 done()
        皆 True），故最终防线是 _backfill_user_if_framework_skips 内的【每轮 once-guard】
        （本轮至多补一次），三者叠加才封死 [U, U] 悬挂重复。

        限制：仅非流式档成立（框架默认 streaming_response=False，用户实例已确认）；
        流式档 graceful err 走 STREAMING_FINISH，RespondStage 早退不触发本钩子。
        """
        # v3 shadow：ordinary 输出的终端记账（design 14.2 + Task 2 钉住的 4.26.5 真源事实）。
        # after_message_sent 【不是成功回执】——respond/stage.py 里 send 的异常被 except 吞掉
        # 之后照样发这个事件，所以它只能收尾本轮生命周期，永远结算不出 SPEAK，恒 UNKNOWN。
        # 放在本钩子最前、在下面那三道 backfill 门【之前】：那些门是为 err 轮补写设的，
        # 正常 SPEAK 轮(_syl_resp_handled=True)会早退，记账挂它们后面就永远收不到证据。
        # getattr 而非直调：本钩子被窄插件桩借去无绑定调用（见下方 backfill 的同款写法），
        # 那些桩没有 v3 面；v3 缺席绝不能让这条 v2 兜底路径炸。
        _v3_settle_ordinary = getattr(self, "_v3_settle_ordinary", None)
        if callable(_v3_settle_ordinary):
            _v3_settle_ordinary(event)
        try:
            get_extra = getattr(event, "get_extra", None)
            if not callable(get_extra):
                return
            if get_extra("_syl_resp_handled", None) is not False:
                return  # None（非 LLM 轮）/ True（已处理）一律不补
            if self._agent_run_done(event) is not True:
                return  # 终态门：tool 循环中间步 runner 未 done，不在此补写
            # response=None -> 判据 role 腿判"框架不落库"；once-guard 保证本轮至多一次
            backfill_turn = getattr(
                self, "_backfill_turn_if_framework_skips", None
            )
            if callable(backfill_turn):
                await backfill_turn(event, None)
            else:  # compatibility for narrow legacy test/plugin stubs
                await self._backfill_user_if_framework_skips(event, None)
        except Exception as e:
            logger.warning(f"Sylanne err-turn user backfill failed: {e}", exc_info=True)

    # -----------------------------------------------------------------------
    # issue43 PRIMARY 修复：AstrBot /reset（及 /new 切换新会话）幽灵源清理
    # -----------------------------------------------------------------------
    #
    # 根因（已用真模型 A/B 复核，详见任务交接记录）：AstrBot 内置 /reset 会清空
    # 它自己的 conversation.history（→ 真实对话历史丢失），但从不触碰本插件的
    # MemorySystem/ConversationBuffer/pending_outreach_context（→ 幽灵话题存活，
    # 继续被召回进 [心象] 记忆线索 与 [life_event_context] 槽位）。真实历史缺失 +
    # 幽灵注入残留 —— 这个联合条件才会让模型漂移到幽灵话题；单独一边都不会。
    #
    # AstrBot 侧机制（astrbot/builtin_stars/builtin_commands/commands/conversation.py
    # 的 reset()/new_conv()）：`message.set_extra("_clean_ltm_session", True)`，
    # 仅在 AstrBot 自己的 after_message_sent 钩子里被消费一次（调用它自己的内置
    # LTM.remove_session，与本插件无关）。本插件此前完全不读这个标记——这里补上
    # 同名钩子，跟随同一套约定读同一个 extra key（API 参考 §3 after_message_sent /
    # §4 event.get_extra）。
    @filter.after_message_sent()
    async def on_after_message_sent_reset_ghost_cleanup(
        self, event: Any, *args: Any, **kwargs: Any
    ) -> None:
        """AstrBot /reset 发生后清理本插件的幽灵记忆源（不触碰关系/人格状态）。

        *args/**kwargs：兜住 AstrBot 各版本多传的钩子参数，避免新版 TypeError。"""
        try:
            clean_session = False
            get_extra = getattr(event, "get_extra", None)
            if callable(get_extra):
                clean_session = bool(get_extra("_clean_ltm_session", False))
            if not clean_session:
                return
            session_key = self._session_ctx.session_key(event)
            self._on_session_reset(session_key)
        except Exception as e:
            logger.warning(
                f"Sylanne on_after_message_sent_reset_ghost_cleanup failed: {e}",
                exc_info=True,
            )

    def _on_session_reset(self, session_key: str) -> None:
        """/reset 触发的幽灵源清理（同步、可测试）。

        清（透明工作记忆/瞬时携带者，"忘记这段对话"）：
        - MemorySystem L1 热池（clear_l1_hot_pool）——近期未确认摘要，最直接的
          temporal_proximity 幽灵搬运工。
        - MemorySystem 自动召回纪元边界（set_recall_epoch_boundary）——非破坏性
          门控：早于此刻的 L1/L2/L3 记忆不再被自动召回拼进 prompt，但条目本身
          不删除、不清零，管理面板/WebUI 直读旁路不受影响。
        - ConversationBuffer（本轮暂存原文，尚未 flush 进记忆的部分）。
        - pending_outreach_context（[life_event_context] 槽位的待发送生活事件，
          幽灵话题的另一条直接注入通路）。

        保留（关系/人格/身份状态，"忘记这段对话" != "忘记你是谁/我们的关系"）：
        - L2/L3 已下沉/已压缩的记忆本体（只是纪元门控，不删除）。
        - v2core 人格/关系/身份域（usermodel disposition、narrative self、
          emotion baseline、distill 等）——本方法完全不触碰。
        - _incarnation_epoch（从不序列化，本方法也不touch）。
        """
        now = time.time()
        memory_system = self._store.memory_systems.get(session_key)
        if memory_system is not None:
            try:
                memory_system.set_recall_epoch_boundary(now)
            except Exception as e:
                logger.debug(f"Sylanne _on_session_reset epoch boundary [{session_key}]: {e}")
            try:
                memory_system.clear_l1_hot_pool()
            except Exception as e:
                logger.debug(f"Sylanne _on_session_reset clear L1 [{session_key}]: {e}")
        conv_buf = self._store.conversation_buffers.get(session_key)
        if conv_buf is not None:
            try:
                conv_buf.drain()
            except Exception as e:
                logger.debug(f"Sylanne _on_session_reset drain buffer [{session_key}]: {e}")
        try:
            self._store.pending_outreach_context.pop(session_key, None)
        except Exception as e:
            logger.debug(f"Sylanne _on_session_reset pop outreach [{session_key}]: {e}")

    async def _maybe_takeover_segments(self, event: Any) -> bool:
        """若 event 对应的 origin 被桥接登记为待接管分段：

        提取文本 → 清空 chain（大饼见空 chain 不发送）→ 后台用 Sylanne 分段连发。
        返回 True 表示已接管（调用方应 return，跳过后续 strip）。
        """
        bridge = getattr(self, "_proactive_bridge", None)
        if bridge is None:
            return False
        origin = str(getattr(event, "unified_msg_origin", "") or "")
        if not origin or not bridge.claim_segment_takeover(origin):
            return False
        try:
            result = event.get_result()
            chain = getattr(result, "chain", None) if result is not None else None
            # issue#26 根治（手术刀）：chain 含【非 Plain 组件】（大饼 TTS 的 Record 语音 /
            # 图片 Image 等）时【不接管】，return False 让大饼原样发送——避免下方"只提 Plain
            # 文本 + 无条件清空 chain"把语音/图片整条吞掉（语音被清、Sylanne 又因无 Plain 不发
            # → QQ 收不到、无报错）。仅【纯 Plain 文本 chain】才接管分段。
            # 判据只依赖已 import 的 Plain（不枚举所有非文本类型，最不易漏判）。
            # claim 已消费标记（一次性），return False 后大饼正常发，本条不被吞，标记不泄漏到下条。
            if chain and any(not isinstance(seg, Plain) for seg in chain):
                logger.info(
                    "Sylanne proactive segment takeover skipped: chain 含非文本组件"
                    "(TTS语音/图片)，放行大饼原样发送 for %s",
                    origin,
                )
                return False
            text = ""
            if chain:
                text = "".join(
                    seg.text for seg in chain if isinstance(seg, Plain) and seg.text
                )
            # 清空 chain → 大饼 _send_chain_with_hooks 见空链直接 return，不发送
            if result is not None:
                if isinstance(chain, list):
                    chain[:] = []  # 切片清空，保留 list/MessageChain 子类对象身份
                else:
                    result.chain = []
            text = text.strip()
            if not text:
                return True  # 已拦截，无内容可发
            # 后台连发 Sylanne 人格化分段（不阻塞装饰链）
            from sylanne_alpha.message_dispatch import realtime_plan

            plan = realtime_plan(origin, text)
            parts = plan.get("message_parts", [])
            # 连发中欲言又止：犹豫开启时，按强度给分段插入加长停顿/半句省略号
            if (self.config or {}).get("sylanne_alpha_proactive_hesitation", False):
                try:
                    surface = await self.proactive_sylanne(session_key=origin)
                    body = surface.get("body", {}) if isinstance(surface, dict) else {}
                    parts = bridge.apply_segment_hesitation(parts, body)
                except Exception as e:
                    logger.warning(f"Sylanne segment hesitation skip: {e}")
            task = safe_ensure_future(
                self._llm_response_pipeline._dispatch_segmented_parts(origin, parts),
                name="proactive_segment_takeover",
            )
            if isinstance(getattr(self, "_background_tasks", None), list):
                self._background_tasks.append(task)
                task.add_done_callback(
                    lambda t: (
                        self._background_tasks.remove(t)
                        if t in self._background_tasks
                        else None
                    )
                )
            logger.info(
                f"Sylanne proactive segment takeover: {len(parts)} parts for {origin}"
            )
            return True
        except Exception as e:
            logger.warning(
                f"Sylanne proactive segment takeover failed: {e}", exc_info=True
            )
            return False

    async def _maybe_suppress_realtime_takeover(self, event: Any) -> bool:
        """即时聊天 LLM 响应接管的发送抑制（realtime 完整重做 Model-D 核心）。

        ``_on_llm_response_inner`` 只登记分段候选，绝不启动 transport；
        ``on_agent_done`` 只把 run_context/response 绑定到账本。此装饰器以低优先级
        在常规 TTS/图片装饰器之后查看【最终】event.result.chain：

        - 仍为纯 Plain：提交文本所有权、启动分段 transport、清空框架 chain，
          等实际投递结算后把成功送达前缀写回历史；
        - 已变为 Record/Image 等非 Plain（或被其他装饰器清空）：放弃文本所有权，
          不启动 transport，完整交给框架发送。

        AstrBot 只会在 run_agent 生成器（包含本装饰阶段）消费完成后覆盖写历史，
        因此纯文本分支的送达结算仍发生在保存之前；非文本分支则保留 provider
        assistant 文本作为语音/图片回合的上下文。这个最终链仲裁点消除了
        “先发分段文字，稍后 CloneTTS 又发 Record”的竞态。

        返回 True 表示本轮由本机制处理（调用方应 return，跳过后续通用
        strip_draft_blocks 逻辑——分段发送前已经 sanitize/strip 过）。
        """
        pipeline = getattr(self, "_llm_response_pipeline", None)
        has_candidate = getattr(
            pipeline,
            "has_pending_segmented_candidate",
            None,
        )
        candidate_pending = bool(has_candidate(event)) if callable(has_candidate) else False
        get_extra = getattr(event, "get_extra", None)
        if not candidate_pending and (
            not callable(get_extra)
            or not get_extra("_syl_realtime_takeover", False)
        ):
            return False
        try:
            result = event.get_result()
            chain = getattr(result, "chain", None) if result is not None else None
            if candidate_pending:
                if not chain or any(not isinstance(seg, Plain) for seg in chain):
                    delegate = getattr(
                        pipeline,
                        "delegate_segmented_candidate_to_framework",
                        None,
                    )
                    if callable(delegate):
                        await delegate(event)
                    logger.info(
                        "Sylanne final output delegated to framework chain: "
                        "non_plain=%s for %s",
                        bool(
                            chain
                            and any(not isinstance(seg, Plain) for seg in chain)
                        ),
                        getattr(event, "unified_msg_origin", ""),
                    )
                    return False

                activate = getattr(pipeline, "activate_segmented_delivery", None)
                if not callable(activate) or not activate(event):
                    return False

            if chain and any(not isinstance(seg, Plain) for seg in chain):
                logger.info(
                    "Sylanne realtime takeover suppression skipped: chain 含非 "
                    "Plain 组件，放行框架原样发送 for %s",
                    getattr(event, "unified_msg_origin", ""),
                )
                # 不视为"已处理"：交回调用方走通用 strip_draft_blocks 清理
                # （只清 Plain 段、非 Plain 原样放行），而不是完全零处理。
                return False
            if result is not None:
                if isinstance(chain, list):
                    chain[:] = []  # 切片清空，保留 list/MessageChain 子类身份
                else:
                    result.chain = []
            if candidate_pending:
                settle_delivery = getattr(
                    pipeline,
                    "settle_segmented_delivery_history",
                    None,
                )
                if callable(settle_delivery):
                    await settle_delivery(event, None, None)
            return True
        except Exception as e:
            logger.warning(
                f"Sylanne realtime takeover suppression failed: {e}", exc_info=True
            )
            return False

    async def _on_llm_response_inner(self, event: Any, response: Any) -> None:
        # 2.4.1 err 轮兜底（三态标记，第二态）：本钩子跑过即置 True。必须在【入口】置位，
        # 这样即便下面 v2 裁决/投递续接抛异常，finally 里的补写也已经执行过，
        # after_message_sent 侧就会早退，不会对同一轮重复补写 user。
        set_extra = getattr(event, "set_extra", None)
        if callable(set_extra):
            try:
                set_extra("_syl_resp_handled", True)
            except Exception:  # 标记失败绝不阻断回复
                pass
        # v2core 认知阶段二：裁决草稿 + 学习。suppress_delivery=True 仅 SILENT；
        # SPEAK/FALLBACK/异常均续接唯一投递管线，完成 sanitize、分段与观测。
        try:
            suppress_delivery = False
            try:
                from sylanne_alpha.v2core.integration import apply_v2core_response
                suppress_delivery = await apply_v2core_response(self, event, response)
            except Exception as exc:  # 桥接自身异常绝不阻断回复
                logger.error(
                    f"Sylanne v2core decision error; continuing delivery pipeline: {exc}",
                    exc_info=True,
                )
                suppress_delivery = False
            if not suppress_delivery:
                await self._llm_response_pipeline._on_llm_response_inner(event, response)
        finally:
            # 2.4.1 leg-3 双写根治：无论上面抑制投递、续接投递或抛异常，都在此
            # 判定"框架本轮是否落库"，仅框架不落库时补写 user（放 finally 保证异常路径
            # 也不吞补写——这是 SILENT 不丢历史的红线）。
            try:
                backfill_turn = getattr(
                    self, "_backfill_turn_if_framework_skips", None
                )
                if callable(backfill_turn):
                    await backfill_turn(event, response)
                else:  # compatibility for narrow legacy test/plugin stubs
                    await self._backfill_user_if_framework_skips(event, response)
            except Exception as exc:
                logger.warning("Sylanne user backfill failed: %s", exc)

    async def _background_observe_response(
        self, session_key: str, text: str, *, skip_conv_sync: bool = False
    ) -> None:
        await self._llm_response_pipeline._background_observe_response(
            session_key, text, skip_conv_sync=skip_conv_sync
        )

    @_optional_stream_chunk_filter(desc="流式首句提前发送")
    async def on_llm_stream_chunk(self, event: Any, chunk: Any) -> None:
        await self._llm_response_pipeline.on_llm_stream_chunk(event, chunk)

    def _extract_first_sentence(self, text: str) -> str:
        return self._llm_response_pipeline._extract_first_sentence(text)

    async def _send_first_sentence(self, origin: str, text: str) -> None:
        await self._llm_response_pipeline._send_first_sentence(origin, text)

    # Segmented dispatch
    async def _dispatch_segmented_parts(
        self,
        origin: str,
        parts: list[dict[str, Any]],
        session_key: str = "",
        *,
        settle_v3: bool = True,
    ) -> None:
        # settle_v3 必须原样转发：这层只是兼容转发壳，把它吞掉的话，将来若有调用方
        # 经这里走补刀式（复用 session_key 的延迟）投递，就会重新踩上"认领下一轮"的坑。
        await self._llm_response_pipeline._dispatch_segmented_parts(
            origin, parts, session_key=session_key, settle_v3=settle_v3
        )

    # Memory prompt fragment
    def _memory_prompt_fragment(self, payload: dict[str, Any]) -> str:
        return self._llm_response_pipeline._memory_prompt_fragment(payload)

    def _append_request_prompt_fragment(self, request: Any, fragment: str) -> None:
        self._llm_response_pipeline._append_request_prompt_fragment(request, fragment)

    # Time context
    def _time_context_fragment(self, session_key: str) -> str:
        return self._llm_response_pipeline._time_context_fragment(session_key)

    def _gap_label_from_seconds(self, seconds: float, has_previous: bool) -> str:
        return self._llm_response_pipeline._gap_label_from_seconds(
            seconds, has_previous
        )

    def _event_time(self, now: float = 0.0) -> dict[str, Any]:
        return self._llm_response_pipeline._event_time(now)

    # Payload capping
    def _cap_llm_request_payload(self, request: Any) -> None:
        self._llm_response_pipeline._cap_llm_request_payload(request)

    def _trim_payload_list(
        self, items: list, keep_items: int = 2, text_limit: int = 5000
    ) -> list:
        return self._llm_response_pipeline._trim_payload_list(
            items, keep_items, text_limit
        )

    def _cap_item_text(self, item: Any, limit: int) -> Any:
        return self._llm_response_pipeline._cap_item_text(item, limit)

    def _make_trim_marker(self, items: list) -> Any:
        return self._llm_response_pipeline._make_trim_marker(items)

    # Observatory (WebUI readonly)
    async def sylanne_observatory(self, *, session_key: str) -> dict[str, Any]:
        return await self._public_api.sylanne_observatory(session_key=session_key)

    async def _observatory_route_handler(self) -> dict[str, Any]:
        return await self._public_api._observatory_route_handler()

    # State injection budget
    def _state_injection_budget_for_request(
        self, session_key: str, request: Any
    ) -> _StateInjectionBudget:
        return self._llm_response_pipeline._state_injection_budget_for_request(
            session_key, request
        )

    # Text extraction from event
    def _text(self, event: Any) -> str:
        return self._llm_response_pipeline._text(event)

    # AstrBot message building
    def _astrbot_message(self, text: str) -> Any:
        return self._llm_response_pipeline._astrbot_message(text)

    # Stub methods for AstrBot decorator compatibility
    async def sylanne_status(self, *args, **kwargs) -> dict[str, Any]:
        return {"ok": True}

    async def sylanne_proactive(self, *args, **kwargs) -> dict[str, Any]:
        return {"ok": True}

    # Public API protocol stubs (engine state snapshots / observations)
    async def get_emotion_consequences(self, *args, **kwargs) -> dict[str, Any]:
        sk = self._session_key(
            kwargs.get("event_or_session"), kwargs.get("session_key", "")
        )
        return command_surface(self._host(sk), "emotion")

    async def get_emotion_relationship(self, *args, **kwargs) -> dict[str, Any]:
        sk = self._session_key(
            kwargs.get("event_or_session"), kwargs.get("session_key", "")
        )
        return command_surface(self._host(sk), "emotion")

    async def get_emotion_prompt_fragment(self, *args, **kwargs) -> str:
        return ""

    async def get_psychological_screening_snapshot(
        self, *args, **kwargs
    ) -> dict[str, Any]:
        sk = self._session_key(
            kwargs.get("event_or_session"), kwargs.get("session_key", "")
        )
        return command_surface(self._host(sk), "psych_state")

    async def get_psychological_screening_values(
        self, *args, **kwargs
    ) -> dict[str, float]:
        return {}

    async def observe_psychological_text(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def simulate_psychological_update(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def reset_psychological_screening_state(self, *args, **kwargs) -> bool:
        return True

    async def reset_emotion_state(self, *args, **kwargs) -> bool:
        sk = self._session_key(
            kwargs.get("event_or_session"), kwargs.get("session_key", "")
        )
        await self.reset_sylanne(session_key=sk)
        return True

    async def get_integrated_self_snapshot(self, *args, **kwargs) -> dict[str, Any]:
        sk = self._session_key(
            kwargs.get("event_or_session"), kwargs.get("session_key", "")
        )
        return command_surface(self._host(sk), "integrated_self")

    async def get_integrated_self_prompt_fragment(self, *args, **kwargs) -> str:
        return ""

    async def get_integrated_self_policy_plan(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def build_integrated_self_replay_bundle(
        self, *args, **kwargs
    ) -> dict[str, Any]:
        return {}

    async def replay_integrated_self_bundle(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def probe_integrated_self_compatibility(
        self, *args, **kwargs
    ) -> dict[str, Any]:
        return {}

    async def export_integrated_self_diagnostics(
        self, *args, **kwargs
    ) -> dict[str, Any]:
        return {}

    async def get_lifelike_learning_snapshot(self, *args, **kwargs) -> dict[str, Any]:
        sk = self._session_key(
            kwargs.get("event_or_session"), kwargs.get("session_key", "")
        )
        result = command_surface(self._host(sk), "lifelike_state")
        result.setdefault("enabled", True)
        result.setdefault("exposure", kwargs.get("exposure", "plugin_safe"))
        return result

    async def get_lifelike_initiative_policy(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def request_proactive_speech_dispatch(
        self, *args, **kwargs
    ) -> dict[str, Any]:
        return await self._proactive_scheduler.request_dispatch(*args, **kwargs)

    async def observe_user_message_withdrawal(self, *args, **kwargs) -> dict[str, Any]:
        return await self._public_api.observe_user_message_withdrawal(*args, **kwargs)

    async def observe_sticker_usage(self, *args, **kwargs) -> dict[str, Any]:
        return await self._public_api.observe_sticker_usage(*args, **kwargs)

    async def get_lifelike_prompt_fragment(self, *args, **kwargs) -> str:
        return ""

    async def observe_lifelike_text(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def simulate_lifelike_update(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def reset_lifelike_learning_state(self, *args, **kwargs) -> bool:
        return True

    async def get_personality_drift_snapshot(self, *args, **kwargs) -> dict[str, Any]:
        sk = self._session_key(
            kwargs.get("event_or_session"), kwargs.get("session_key", "")
        )
        result = command_surface(self._host(sk), "personality_drift_state")
        result.setdefault("enabled", True)
        result.setdefault("exposure", kwargs.get("exposure", "plugin_safe"))
        return result

    async def get_personality_drift_values(self, *args, **kwargs) -> dict[str, float]:
        return {}

    async def get_personality_drift_prompt_fragment(self, *args, **kwargs) -> str:
        return ""

    async def observe_personality_drift_event(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def simulate_personality_drift_update(
        self, *args, **kwargs
    ) -> dict[str, Any]:
        return {}

    async def reset_personality_drift_state(self, *args, **kwargs) -> bool:
        return True

    async def get_fallibility_snapshot(self, *args, **kwargs) -> dict[str, Any]:
        sk = self._session_key(
            kwargs.get("event_or_session"), kwargs.get("session_key", "")
        )
        return command_surface(self._host(sk), "fallibility_state")

    async def get_fallibility_values(self, *args, **kwargs) -> dict[str, float]:
        return {}

    async def get_fallibility_prompt_fragment(self, *args, **kwargs) -> str:
        return ""

    async def observe_fallibility_text(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def simulate_fallibility_update(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def reset_fallibility_state(self, *args, **kwargs) -> bool:
        return True

    async def get_humanlike_snapshot(self, *args, **kwargs) -> dict[str, Any]:
        sk = self._session_key(
            kwargs.get("event_or_session"), kwargs.get("session_key", "")
        )
        result = command_surface(self._host(sk), "humanlike_state")
        result.setdefault("enabled", True)
        result.setdefault("exposure", kwargs.get("exposure", "plugin_safe"))
        return result

    async def get_humanlike_values(self, *args, **kwargs) -> dict[str, float]:
        return {}

    async def get_humanlike_prompt_fragment(self, *args, **kwargs) -> str:
        return ""

    async def observe_humanlike_text(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def simulate_humanlike_update(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def reset_humanlike_state(self, *args, **kwargs) -> bool:
        return True

    async def get_moral_repair_snapshot(self, *args, **kwargs) -> dict[str, Any]:
        sk = self._session_key(
            kwargs.get("event_or_session"), kwargs.get("session_key", "")
        )
        return command_surface(self._host(sk), "moral_repair_state")

    async def get_moral_repair_values(self, *args, **kwargs) -> dict[str, float]:
        return {}

    async def get_moral_repair_prompt_fragment(self, *args, **kwargs) -> str:
        return ""

    async def observe_moral_repair_text(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def simulate_moral_repair_update(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def reset_moral_repair_state(self, *args, **kwargs) -> bool:
        return True

    async def get_group_atmosphere_snapshot(self, *args, **kwargs) -> dict[str, Any]:
        result: dict[str, Any] = {"kind": "group_atmosphere_state"}
        result.setdefault("enabled", True)
        result.setdefault("exposure", kwargs.get("exposure", "plugin_safe"))
        return result

    async def get_group_atmosphere_values(self, *args, **kwargs) -> dict[str, float]:
        return {}

    async def get_group_atmosphere_prompt_fragment(self, *args, **kwargs) -> str:
        return ""

    async def observe_group_atmosphere_text(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def simulate_group_atmosphere_update(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def reset_group_atmosphere_state(self, *args, **kwargs) -> bool:
        return True

    # Legacy 3.x compatibility shims
    def _agent_identity(self, event: Any = None) -> str:
        return self._public_api._agent_identity(event)

    async def get_agent_identity_profile(
        self, event: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        return await self._public_api.get_agent_identity_profile(event, **kwargs)

    async def get_agent_trail(
        self, event: Any = None, *, limit: int = 10, **kwargs: Any
    ) -> dict[str, Any]:
        return await self._public_api.get_agent_trail(event, limit=limit, **kwargs)

    async def _provider_id(self, event: Any = None) -> str:
        return await self._state_persistence.provider_id(event)

    def _kv_key(self, session_key: str) -> str:
        return self._state_persistence.kv_key(session_key)

    def _humanlike_kv_key(self, session_key: str) -> str:
        return self._state_persistence.humanlike_kv_key(session_key)

    def _lifelike_learning_kv_key(self, session_key: str) -> str:
        return self._state_persistence.lifelike_learning_kv_key(session_key)

    def _personality_drift_kv_key(self, session_key: str) -> str:
        return self._state_persistence.personality_drift_kv_key(session_key)

    def _moral_repair_kv_key(self, session_key: str) -> str:
        return self._state_persistence.moral_repair_kv_key(session_key)

    def _fallibility_kv_key(self, session_key: str) -> str:
        return self._state_persistence.fallibility_kv_key(session_key)

    def _psychological_kv_key(self, session_key: str) -> str:
        return self._state_persistence.psychological_kv_key(session_key)

    def _safe_session_key(self, session_key: str) -> str:
        return self._session_ctx.safe_session_key(session_key)

    def _sylanne_memory_kv_key(self, session_key: str) -> str:
        return self._state_persistence.sylanne_memory_kv_key(session_key)

    def _background_post_checkpoint_kv_key(self, session_key: str) -> str:
        return self._background_queue.checkpoint_kv_key(session_key)

    # KV-first persistence helpers
    def _kernel_kv_key(self, session_key: str) -> str:
        return self._state_persistence.kernel_kv_key(session_key)

    def _buffer_kv_key(self, session_key: str) -> str:
        return self._state_persistence.buffer_kv_key(session_key)

    def _has_kv_api(self) -> bool:
        return self._state_persistence.has_kv_api()

    # AstrBot ConversationManager / PersonaManager integration
    def _init_conversation_manager(self) -> Any:
        return self._state_persistence.init_conversation_manager()

    def _has_conversation_manager(self) -> bool:
        return self._state_persistence.has_conversation_manager()

    async def _sync_message_to_conv_mgr(
        self, session_key: str, role: str, text: str
    ) -> bool:
        return await self._state_persistence.sync_message_to_conv_mgr(
            session_key, role, text
        )

    async def _sync_turn_to_conv_mgr(
        self,
        session_key: str,
        user_text: str,
        assistant_text: str = "",
    ) -> bool:
        return await self._state_persistence.sync_turn_to_conv_mgr(
            session_key, user_text, assistant_text
        )

    # ── 2.4.1：user 侧对齐 bot 侧 skip 哲学，仅框架不落库轮补写 user ──────────
    def _framework_will_persist_this_turn(self, event: Any, response: Any) -> bool:
        """镜像 AstrBot 私有 _save_to_history 落库判据（4.25.1，internal.py:395+447-467）。
        True = 框架本轮会写 user（插件必须【不】补写，避免双写）；
        False = 框架不写（插件补写 = 该轮唯一 user 写者）。
        依赖框架私有谓词 + abort 时序：升级须回核 internal.py:395/447-469、
        astr_agent_run_util、tool_loop_agent_runner.was_aborted。
        注意：state_persistence.py:2489 对 user【豁免】幂等去重 -> 对 user dup 零保护；
        防 dup 的唯一防线就是本判据准确（框架写则插件不写），不可指望守卫兜底。

        2.4.1 补丁（红线闸 finding #1）：原实现只镜像了 internal.py:447(无 conversation)
        和 :463-467(空 completion)，遗漏了 :450(final_resp 为 None) 与 :453-455
        (llm_response.role != "assistant") 这两条早退。本判据新增的 role 腿覆盖的是
        【run_agent 外层异常兜底】这一条路径：astr_agent_run_util.py:303-339 会现造一个
        role='err'、completion_text 非空的 error_llm_response 直接喂给 on_agent_done
        （故我们的 hook 会被调用），却从不回写 agent_runner.final_llm_resp（留 None）；
        框架侧 _save_to_history 读到 final_resp=None 落在 :450 的"不存"分支。旧实现
        只看 completion_text 非空就误判"框架会存"，从而漏补 user。

        provider 全挂 err 轮的覆盖归属：当 provider 连同全部 fallback 一并失败时，
        step()（tool_loop_agent_runner.py:772-788）把 role='err' 响应赋给 final_llm_resp
        后直接 return，【不调用 on_agent_done】→ on_llm_response 及其 finally 补写不触发，
        本判据在【响应期】那条路径上确实够不着。该轮由 after_message_sent 兜底钩子
        _on_after_message_sent_err_backfill（非流式档，锁内）负责补写，仍复用本判据的
        role 腿（response=None → 返回 False → 补写）。唯一残留：流式档下 RespondStage
        早退不触发兜底钩子，err 轮 user 丢失（与原生 AstrBot 一致，已记 CHANGELOG）。"""
        get_extra = getattr(event, "get_extra", None)
        req = get_extra("provider_request") if callable(get_extra) else None
        # internal.py:447 —— 无 conversation，框架直接 return，不落库
        if req is None or getattr(req, "conversation", None) is None:
            return False
        # Only the internal agent sub-stage owns AstrBot's `_save_to_history`.
        # Third-party runners invoke on_agent_done hooks too, but do not run that
        # sub-stage; absence from the active-runner registry therefore means the
        # plugin must persist this turn itself. Partial legacy stubs without the
        # probe retain the old predicate behavior.
        runner_probe = getattr(self, "_agent_run_done", None)
        if callable(runner_probe) and runner_probe(event) is None:
            return False
        aborted = self._agent_was_aborted(event)
        is_stopped = bool(event.is_stopped()) if hasattr(event, "is_stopped") else False
        # internal.py:395 —— event 被 stop 且【未】abort，框架根本不调 save
        if is_stopped and not aborted:
            return False
        # internal.py:450 —— 无响应对象（run_agent 外层异常兜底 / err-backfill 传 None）。
        # 此时下面 role/completion 两腿恒等价于 aborted（role 缺省 'assistant' 落不到
        # role 腿；completion 从 None 取空、tool_res 归 req），提前返回，避免对 None 取属性。
        if response is None:
            return aborted
        # internal.py:453-455 —— 响应 role 非 assistant（如 'err'）且未 abort -> 不落库
        role = getattr(response, "role", "assistant") or "assistant"
        if role != "assistant" and not aborted:
            return False
        # internal.py:463-467 —— completion 空 且 无 tool_calls_result 且 未 abort -> 不落库
        # 【不 strip】：精确镜像框架 `not completion_text`（" " 在框架为真 -> 会 save）
        completion = getattr(response, "completion_text", "") or ""
        tool_res = bool(getattr(req, "tool_calls_result", None))
        return bool(completion) or tool_res or aborted

    def _agent_was_aborted(self, event: Any) -> bool:
        """权威读取本轮 was_aborted。钩子时刻 runner._aborted 已置位
        （tool_loop_agent_runner.py:1367 早于 :1385 触发钩子），且 runner 仍注册在
        follow_up._ACTIVE_AGENT_RUNNERS（register internal.py:267 / unregister :414，
        后者在 _save_to_history 之后）。读不到时保守回退 False：偏向保住 SILENT 常见
        路径，仅"abort 且此处读取失败"双重罕见时才可能 dup，可接受。"""
        try:
            from astrbot.core.pipeline.process_stage.follow_up import (
                _ACTIVE_AGENT_RUNNERS,
            )
            umo = getattr(event, "unified_msg_origin", "") or ""
            runner = _ACTIVE_AGENT_RUNNERS.get(umo)
            if runner is not None and hasattr(runner, "was_aborted"):
                return bool(runner.was_aborted())
        except Exception:
            pass
        return False

    def _agent_run_done(self, event: Any) -> bool | None:
        """读本轮 agent runner 是否已到终态（DONE/ERROR，tool_loop_agent_runner.py:
        1338-1340）。err-backfill 钩子的终态门用它挡掉 tool 循环中间步——那些中间步
        也会触发 after_message_sent 且此刻 _syl_resp_handled 仍 False，但 runner 尚
        未 done。返回 None（取不到 runner，如第三方 runner 部署或注册表未命中）时钩子
        跳过补写，宁丢不重（丢=与原生 AstrBot 一致）。runner 注册期见 _agent_was_aborted
        （unregister 在 _save_to_history 之后，故 after_message_sent :292 时刻仍在）。"""
        try:
            from astrbot.core.pipeline.process_stage.follow_up import (
                _ACTIVE_AGENT_RUNNERS,
            )
            umo = getattr(event, "unified_msg_origin", "") or ""
            runner = _ACTIVE_AGENT_RUNNERS.get(umo)
            if runner is not None and hasattr(runner, "done"):
                return bool(runner.done())
        except Exception:
            pass
        return None

    async def _backfill_turn_if_framework_skips(
        self,
        event: Any,
        response: Any,
        *,
        assistant_override: str | None = None,
    ) -> None:
        """Atomically persist the turn when AstrBot will not do so itself."""
        if not self._has_conversation_manager():
            return
        get_extra = getattr(event, "get_extra", None)
        if callable(get_extra) and (
            get_extra("_syl_turn_backfilled", False)
            or get_extra("_syl_user_backfilled", False)
        ):
            return
        if self._framework_will_persist_this_turn(event, response):
            return

        user_text = self._text(event)
        if not user_text:
            return

        stopped = bool(event.is_stopped()) if hasattr(event, "is_stopped") else False
        assistant_text = assistant_override if assistant_override is not None else ""
        if assistant_override is None and response is not None and not stopped:
            role = getattr(response, "role", "assistant") or "assistant"
            completion = getattr(response, "completion_text", "") or ""
            if role == "assistant" and completion:
                assistant_text = completion

        sync_turn = getattr(self, "_sync_turn_to_conv_mgr", None)
        if callable(sync_turn):
            success = bool(
                await sync_turn(
                    self._session_key(event), user_text, assistant_text
                )
            )
        else:
            # Keep narrow legacy stubs working; the real plugin always uses the
            # atomic turn delegate above.
            result = await self._sync_message_to_conv_mgr(
                self._session_key(event), "user", user_text
            )
            success = True if result is None else bool(result)

        if not success:
            return

        set_extra = getattr(event, "set_extra", None)
        if callable(set_extra):
            for key in ("_syl_turn_backfilled", "_syl_user_backfilled"):
                try:
                    set_extra(key, True)
                except Exception:
                    pass

    async def _backfill_user_if_framework_skips(
        self, event: Any, response: Any
    ) -> None:
        """Compatibility wrapper for the grey.4 atomic turn backfill."""
        await EmotionalStatePlugin._backfill_turn_if_framework_skips(
            self, event, response
        )

    def _init_persona_manager(self) -> Any:
        return self._state_persistence.init_persona_manager()

    def _has_persona_manager(self) -> bool:
        return self._state_persistence.has_persona_manager()

    def _sync_personality_to_persona_mgr(self, session_key: str) -> None:
        self._state_persistence.sync_personality_to_persona_mgr(session_key)

    async def _persist_kernel(self, session_key: str, host: SylanneAlphaHost) -> None:
        await self._state_persistence.persist_kernel(session_key, host)

    def _persist_kernel_sync(self, session_key: str, host: SylanneAlphaHost) -> None:
        self._state_persistence.persist_kernel_sync(session_key, host)

    async def _persist_buffer(
        self, session_key: str, host: SylanneAlphaHost, buf_dict: dict[str, Any]
    ) -> None:
        await self._state_persistence.persist_buffer(session_key, host, buf_dict)

    async def _load_buffer_data(
        self, session_key: str, host: SylanneAlphaHost
    ) -> dict[str, Any] | None:
        return await self._state_persistence.load_buffer_data(session_key, host)

    async def _load_state(
        self, session_key: str, persona_profile: Any = None, *, now: float = 0.0
    ) -> Any:
        return await self._state_persistence.load_state(
            session_key, persona_profile=persona_profile, now=now
        )

    async def _load_psychological_state(self, session_key: str) -> Any:
        return await self._state_persistence.load_psychological_state(session_key)

    async def _load_humanlike_state(self, session_key: str) -> Any:
        return await self._state_persistence.load_humanlike_state(session_key)

    async def _load_lifelike_learning_state(
        self, session_key: str, **kwargs: Any
    ) -> Any:
        return await self._state_persistence.load_lifelike_learning_state(
            session_key, **kwargs
        )

    async def _load_personality_drift_state(
        self, session_key: str, **kwargs: Any
    ) -> Any:
        return await self._state_persistence.load_personality_drift_state(
            session_key, **kwargs
        )

    async def _load_moral_repair_state(self, session_key: str) -> Any:
        return await self._state_persistence.load_moral_repair_state(session_key)

    async def _load_fallibility_state(self, session_key: str) -> Any:
        return await self._state_persistence.load_fallibility_state(session_key)

    async def _save_state(self, session_key: str, state: Any = None) -> None:
        await self._state_persistence.save_state(session_key, state)

    async def _delete_state(self, session_key: str) -> None:
        await self._state_persistence.delete_state(session_key)

    async def _delete_humanlike_state(self, session_key: str) -> None:
        await self._state_persistence.delete_humanlike_state(session_key)

    async def _delete_lifelike_learning_state(self, session_key: str) -> None:
        await self._state_persistence.delete_lifelike_learning_state(session_key)

    async def _delete_personality_drift_state(self, session_key: str) -> None:
        await self._state_persistence.delete_personality_drift_state(session_key)

    async def _delete_moral_repair_state(self, session_key: str) -> None:
        await self._state_persistence.delete_moral_repair_state(session_key)

    async def _delete_fallibility_state(self, session_key: str) -> None:
        await self._state_persistence.delete_fallibility_state(session_key)

    async def _save_humanlike_state(self, session_key: str, state: Any = None) -> None:
        await self._state_persistence.save_humanlike_state(session_key, state)

    async def _save_psychological_state(
        self, session_key: str, state: Any = None
    ) -> None:
        await self._state_persistence.save_psychological_state(session_key, state)

    async def _save_moral_repair_state(
        self, session_key: str, state: Any = None
    ) -> None:
        await self._state_persistence.save_moral_repair_state(session_key, state)

    async def _save_lifelike_learning_state(
        self, session_key: str, state: Any = None
    ) -> None:
        await self._state_persistence.save_lifelike_learning_state(session_key, state)

    async def _save_fallibility_state(
        self, session_key: str, state: Any = None
    ) -> None:
        await self._state_persistence.save_fallibility_state(session_key, state)

    async def _save_personality_drift_state(
        self, session_key: str, state: Any = None
    ) -> None:
        await self._state_persistence.save_personality_drift_state(session_key, state)

    async def _load_group_atmosphere_state(self, session_key: str) -> Any:
        return await self._state_persistence.load_group_atmosphere_state(session_key)

    async def _delete_psychological_state(self, session_key: str) -> None:
        await self._state_persistence.delete_psychological_state(session_key)

    def _engine_for_persona(self, persona_profile: Any = None) -> Any:
        engine = getattr(self, "engine", None)
        return engine

    async def _judge_proactive_topic(
        self, session_key: str = "", **kwargs: Any
    ) -> dict[str, Any]:
        return await self._proactive_scheduler.judge_topic(
            session_key=session_key, **kwargs
        )

    def _persona_profile(self, event: Any = None) -> dict[str, Any]:
        name = str(self._config.get("sylanne_persona_name") or "Sylanne")
        # 版本号从 metadata.yaml 读取，不依赖配置项
        try:
            import yaml
            meta_path = Path(_PLUGIN_DIR) / "metadata.yaml"
            if meta_path.exists():
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = yaml.safe_load(f) or {}
                version = str(meta.get("version", ""))
            else:
                version = ""
        except Exception:
            version = ""
        return {"name": name, "version": version}

    def _observed_now(self) -> float:
        cfg = self.config or {}
        if cfg.get("benchmark_enable_simulated_time"):
            return time.time() + float(cfg.get("benchmark_time_offset_seconds", 0.0))
        return time.time()

    def _request_to_text(self, request: Any) -> str:
        if request is None:
            return ""
        return str(getattr(request, "prompt", "") or "")[:500]

    def _resolve_public_session_key(
        self, event: Any = None, *, request: Any = None, session_key: str = ""
    ) -> str:
        return self._session_ctx.resolve_public_session_key(
            event, request=request, session_key=session_key
        )

    def _record_conversation_pending_response_epoch(
        self, session_key: str, now: float = 0.0
    ) -> None:
        self._store.conversation_pending_response_epochs.set(session_key, now or time.time())

    async def _sylanne_memory_recall_summary_for_request(
        self,
        request: Any = None,
        *,
        session_key: str = "",
        current_user_text: str = "",
        observed_at: Any = None,
        **kwargs: Any,
    ) -> str:
        return ""

    async def _sylanne_memory_recall_query_for_request(
        self, session_key: str, text: str = "", **kwargs: Any
    ) -> str:
        return text[:100] if text else ""

    async def _save_sylanne_memory_state(
        self, session_key: str, state: Any = None
    ) -> None:
        await self._memory_facade.save_sylanne_memory_state(session_key, state)

    async def _load_sylanne_memory_state(
        self, session_key: str, *, now: float = 0.0
    ) -> Any:
        return await self._memory_facade.load_sylanne_memory_state(
            session_key, now=now
        )

    async def _delete_sylanne_memory_state(self, session_key: str) -> None:
        await self._memory_facade.delete_sylanne_memory_state(session_key)

    def _consume_conversation_pending_response_epoch(self, session_key: str) -> float:
        return self._store.conversation_pending_response_epochs.pop(session_key, 0.0)

    async def _observe_sylanne_memory_event_if_enabled(
        self, session_key: str, text: str = "", **kwargs: Any
    ) -> None:
        pass

    async def _commit_sylanne_memory_observations_batch(
        self, session_key: str, observations: Any = None, **kwargs: Any
    ) -> None:
        pass

    def _schedule_background_task(self, coro: Any, *, label: str = "") -> Any:
        return self._realtime_dispatch.schedule_background_task(coro, label=label)

    def _ensure_runtime_state_containers(self) -> None:
        self._realtime_dispatch.ensure_runtime_state_containers()

    def _build_astrbot_message_chain(self, text: str = "", **kwargs: Any) -> Any:
        return self._realtime_dispatch.build_astrbot_message_chain(text, **kwargs)

    async def _assess_emotion(
        self, session_key: str = "", text: str = "", event: Any = None, **kwargs: Any
    ) -> Any:
        return await self._public_api._assess_emotion(
            session_key, text=text, event=event, **kwargs
        )

    async def _call_internal_assessor_llm(self, *args: Any, **kwargs: Any) -> Any:
        return await self._public_api._call_internal_assessor_llm(*args, **kwargs)

    def _internal_assessor_llm_concurrency_limit(self) -> int:
        return self._public_api._internal_assessor_llm_concurrency_limit()

    def _internal_assessor_llm_concurrency_decision(self) -> dict[str, Any]:
        return self._public_api._internal_assessor_llm_concurrency_decision()

    def _build_realtime_input_completion_prompt(
        self, session_key: str = "", text: str = "", **kwargs: Any
    ) -> str:
        return self._realtime_dispatch.build_realtime_input_completion_prompt(
            session_key, text, **kwargs
        )

    def _extract_realtime_response_media_parts(self, response: Any = None) -> list[Any]:
        return self._realtime_dispatch.extract_realtime_response_media_parts(response)

    def _build_group_atmosphere_injection_for_session(
        self, session_key: str = "", state: Any = None, **kwargs: Any
    ) -> str:
        return self._realtime_dispatch.build_group_atmosphere_injection_for_session(
            session_key, state, **kwargs
        )

    def _context_item_to_text(self, item: Any) -> str:
        return self._realtime_dispatch.context_item_to_text(item)

    def _conversation_time_payload(
        self, session_key_or_timestamp: Any = "", *, event: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        return self._realtime_dispatch.conversation_time_payload(
            session_key_or_timestamp, event=event, **kwargs
        )

    def _napcat_recall_payload(self, event: Any = None) -> dict[str, Any]:
        return self._realtime_dispatch.napcat_recall_payload(event)

    def _derive_proactive_dispatch_policy(
        self, decision: Any = None, *, session_key: str = "", **kwargs: Any
    ) -> dict[str, Any]:
        return self._proactive_scheduler.derive_dispatch_policy(
            decision, session_key=session_key, **kwargs
        )

    def _observe_proactive_dispatch_feedback(
        self, session_key: str = "", **kwargs: Any
    ) -> None:
        return self._proactive_scheduler.observe_dispatch_feedback(
            session_key=session_key, **kwargs
        )

    async def _observe_stickers_background(
        self, event: Any = None, stickers: Any = None, **kwargs: Any
    ) -> None:
        await self._realtime_dispatch.observe_stickers_background(
            event, stickers, **kwargs
        )

    def _extract_sticker_observations_from_event(
        self, event: Any = None
    ) -> list[dict[str, Any]]:
        return self._realtime_dispatch.extract_sticker_observations_from_event(event)

    def _proactive_scheduler_should_exit_after_idle(
        self, session_key: str = "", **kwargs: Any
    ) -> bool:
        return self._proactive_scheduler.should_exit_after_idle(
            session_key=session_key, **kwargs
        )

    def _build_proactive_dispatch_request(
        self, decision: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        return self._proactive_scheduler.build_dispatch_request(decision, **kwargs)

    def _proactive_dispatch_blocked_reason(
        self, decision: Any = None, dispatch: Any = None, **kwargs: Any
    ) -> str:
        return self._proactive_scheduler.dispatch_blocked_reason(
            decision, dispatch, **kwargs
        )

    def _astrbot_active_runner_followup_texts(self, session_key: str = "") -> list[str]:
        return []

    def _last_request_text_for_session(self, session_key: str = "") -> str:
        return str(self._store.last_request_text.get(session_key, ""))

    def _background_post_adaptive_worker_decision(
        self, session_key: str = "", *, commit_scale: bool = False
    ) -> dict[str, Any]:
        return self._background_queue.adaptive_worker_decision(
            session_key, commit_scale=commit_scale
        )

    def _background_post_max_workers(self, session_key: str = "") -> int:
        return self._background_queue.max_workers(session_key)

    def _background_post_job_to_dict(self, job: Any) -> dict[str, Any]:
        return self._background_queue.job_to_dict(job)

    def _recover_expired_background_post_active(self, session_key: str) -> int:
        return self._background_queue.recover_expired_active(session_key)

    def _schedule_background_post_checkpoint(self, session_key: str) -> None:
        self._background_queue.schedule_checkpoint(session_key)

    async def _drain_background_post_assessments(self, session_key: str) -> None:
        await self._background_queue.drain_assessments(session_key)

    async def _save_background_post_checkpoint(self, session_key: str) -> None:
        await self._background_queue.save_checkpoint(session_key)

    async def _recover_background_post_queue(self, session_key: str) -> bool:
        return await self._background_queue.recover_queue(session_key)

    async def on_waiting_llm_request(self, event: Any, **kwargs: Any) -> None:
        await self._realtime_dispatch.on_waiting_llm_request(event, **kwargs)

    def sylanne_alpha_switches(self) -> dict[str, Any]:
        return self._public_api.sylanne_alpha_switches()

    async def sylanne_memory_status(
        self, event: Any = None, query: str = "", **kwargs: Any
    ) -> Any:
        async for chunk in self._public_api.sylanne_memory_status(
            event, query=query, **kwargs
        ):
            yield chunk

    async def emotion_reset(self, event: Any = None, **kwargs: Any) -> Any:
        async for chunk in self._public_api.emotion_reset(event, **kwargs):
            yield chunk

    def humanlike_reset(self, event: Any = None, **kwargs: Any) -> Any:
        return self._public_api.humanlike_reset(event, **kwargs)

    async def _humanlike_reset_command(self, event: Any = None, **kwargs: Any) -> Any:
        async for chunk in self._public_api._humanlike_reset_command(event, **kwargs):
            yield chunk

    async def moral_repair_status(self, event: Any = None, **kwargs: Any) -> Any:
        async for chunk in self._public_api.moral_repair_status(event, **kwargs):
            yield chunk

    async def query_agent_state(
        self,
        event: Any = None,
        state: str = "",
        detail: str = "summary",
        track: str = "conversation",
        include_runtime: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return await self._public_api.query_agent_state(
            event,
            state=state,
            detail=detail,
            track=track,
            include_runtime=include_runtime,
            **kwargs,
        )

    async def query_agent_state_tool(self, event: Any = None, **kwargs: Any) -> str:
        return await self._public_api.query_agent_state_tool(event, **kwargs)

    async def get_agent_runtime_diagnostics(
        self, event: Any = None, include_sessions: bool = False, **kwargs: Any
    ) -> dict[str, Any]:
        return await self._public_api.get_agent_runtime_diagnostics(
            event, include_sessions=include_sessions, **kwargs
        )

    def _append_realtime_ordinary_history_backfills_if_any(
        self, request: Any, session_key: str = "", **kwargs: Any
    ) -> bool:
        return (
            self._realtime_dispatch.append_realtime_ordinary_history_backfills_if_any(
                request, session_key=session_key, **kwargs
            )
        )

    # Command methods (status/reset commands expected by tests)
    async def psychological_screening_status(
        self, event: Any = None, **kwargs: Any
    ) -> Any:
        async for chunk in self._public_api.psychological_screening_status(
            event, **kwargs
        ):
            yield chunk

    async def humanlike_status(self, event: Any = None, **kwargs: Any) -> Any:
        async for chunk in self._public_api.humanlike_status(event, **kwargs):
            yield chunk

    async def lifelike_learning_status(self, event: Any = None, **kwargs: Any) -> Any:
        async for chunk in self._public_api.lifelike_learning_status(event, **kwargs):
            yield chunk

    async def personality_drift_status(self, event: Any = None, **kwargs: Any) -> Any:
        async for chunk in self._public_api.personality_drift_status(event, **kwargs):
            yield chunk

    async def fallibility_status(self, event: Any = None, **kwargs: Any) -> Any:
        async for chunk in self._public_api.fallibility_status(event, **kwargs):
            yield chunk

    async def shadow_diagnostics_status(self, event: Any = None, **kwargs: Any) -> Any:
        async for chunk in self._public_api.shadow_diagnostics_status(event, **kwargs):
            yield chunk

    async def moral_repair_reset(self, event: Any = None, **kwargs: Any) -> Any:
        async for chunk in self._public_api.moral_repair_reset(event, **kwargs):
            yield chunk

    async def fallibility_reset(self, event: Any = None, **kwargs: Any) -> Any:
        async for chunk in self._public_api.fallibility_reset(event, **kwargs):
            yield chunk

    async def lifelike_learning_reset(self, event: Any = None, **kwargs: Any) -> Any:
        async for chunk in self._public_api.lifelike_learning_reset(event, **kwargs):
            yield chunk

    async def personality_drift_reset(self, event: Any = None, **kwargs: Any) -> Any:
        async for chunk in self._public_api.personality_drift_reset(event, **kwargs):
            yield chunk

    # LLM Tool shims (bot state tools)
    async def _query_single_agent_state(
        self,
        state_name: str,
        event: Any = None,
        *,
        request: Any = None,
        session_key: str = "",
        detail: str = "summary",
        track: str = "conversation",
    ) -> dict[str, Any]:
        return await self._public_api._query_single_agent_state(
            state_name,
            event,
            request=request,
            session_key=session_key,
            detail=detail,
            track=track,
        )

    async def get_bot_emotion_state_tool(
        self, event: Any = None, detail: str = "summary", **kwargs: Any
    ) -> Any:
        async for chunk in self._public_api.get_bot_emotion_state_tool(
            event, detail=detail, **kwargs
        ):
            yield chunk

    async def get_bot_humanlike_state_tool(
        self, event: Any = None, detail: str = "summary", **kwargs: Any
    ) -> Any:
        async for chunk in self._public_api.get_bot_humanlike_state_tool(
            event, detail=detail, **kwargs
        ):
            yield chunk

    @filter.command("bond")
    async def bond_command(self, event: Any = None, **kwargs: Any) -> Any:
        """Phase 2B：标当前会话为亲密关系（仅主人 sylanne_alpha_owner_id 可用）。"""
        from sylanne_alpha import relationship_layer as _rl
        async for text in _rl.bond_command(self, event):
            yield event.plain_result(text) if hasattr(event, "plain_result") else text

    @filter.command("unbond")
    async def unbond_command(self, event: Any = None, **kwargs: Any) -> Any:
        """Phase 2B：取消当前会话亲密标记，恢复自动判定（仅主人可用）。"""
        from sylanne_alpha import relationship_layer as _rl
        async for text in _rl.unbond_command(self, event):
            yield event.plain_result(text) if hasattr(event, "plain_result") else text

    @filter.command("说说草稿")
    async def qzone_status_command(self, event: Any = None, **kwargs: Any) -> Any:
        """PR-Qzone：查看当前是否有等主人过目的说说草稿（仅主人可用）。"""
        from sylanne_alpha import qzone_share as _qz
        async for text in _qz.status_command(self, event):
            yield event.plain_result(text) if hasattr(event, "plain_result") else text

    @filter.command("说说确认")
    async def qzone_confirm_command(self, event: Any = None, **kwargs: Any) -> Any:
        """PR-Qzone：确认发出待确认的说说草稿（owner 过目门，唯一发布路径）。"""
        from sylanne_alpha import qzone_share as _qz
        async for text in _qz.confirm_command(self, event):
            yield event.plain_result(text) if hasattr(event, "plain_result") else text

    @filter.command("说说取消")
    async def qzone_cancel_command(self, event: Any = None, **kwargs: Any) -> Any:
        """PR-Qzone：放弃待确认的说说草稿（仅主人可用）。"""
        from sylanne_alpha import qzone_share as _qz
        async for text in _qz.cancel_command(self, event):
            yield event.plain_result(text) if hasattr(event, "plain_result") else text

    async def get_bot_integrated_self_state_tool(
        self, event: Any = None, detail: str = "summary", **kwargs: Any
    ) -> Any:
        async for chunk in self._public_api.get_bot_integrated_self_state_tool(
            event, detail=detail, **kwargs
        ):
            yield chunk

    async def get_bot_moral_repair_state_tool(
        self, event: Any = None, detail: str = "summary", **kwargs: Any
    ) -> Any:
        async for chunk in self._public_api.get_bot_moral_repair_state_tool(
            event, detail=detail, **kwargs
        ):
            yield chunk

    async def get_bot_fallibility_state_tool(
        self, event: Any = None, detail: str = "summary", **kwargs: Any
    ) -> Any:
        async for chunk in self._public_api.get_bot_fallibility_state_tool(
            event, detail=detail, **kwargs
        ):
            yield chunk

    async def get_bot_personality_drift_state_tool(
        self, event: Any = None, detail: str = "summary", **kwargs: Any
    ) -> Any:
        async for chunk in self._public_api.get_bot_personality_drift_state_tool(
            event, detail=detail, **kwargs
        ):
            yield chunk

    async def get_bot_group_atmosphere_state_tool(
        self, event: Any = None, detail: str = "summary", **kwargs: Any
    ) -> Any:
        async for chunk in self._public_api.get_bot_group_atmosphere_state_tool(
            event, detail=detail, **kwargs
        ):
            yield chunk

    async def simulate_bot_emotion_update_tool(
        self, event: Any = None, text: str = "", role: str = "user", **kwargs: Any
    ) -> Any:
        async for chunk in self._public_api.simulate_bot_emotion_update_tool(
            event, text=text, role=role, **kwargs
        ):
            yield chunk

    async def request_bot_proactive_speech_dispatch_tool(
        self, event: Any = None, **kwargs: Any
    ) -> Any:
        async for chunk in self._public_api.request_bot_proactive_speech_dispatch_tool(
            event, **kwargs
        ):
            yield chunk

    # Proactive scheduler / realtime delivery shims
    def _ensure_proactive_scheduler_state(self) -> None:
        self._proactive_scheduler.ensure_state()

    async def _run_proactive_scheduler_once(self) -> dict[str, Any]:
        return await self._proactive_scheduler.run_once()

    def _start_life_simulator(self) -> None:
        """配置生命模拟器并启动全局自驱心跳（幂等）。

        CP8-P3b：LifeSimulator 不再自跑 _loop（已纯函数化）。改由 AutonomyScheduler
        全局心跳驱动 LifeAgent 的 AUTONOMOUS 时点调 simulate_tick。configure 仍需
        注入回调（simulate_tick 内部用 llm/outreach/body_delta 等）。
        """
        if getattr(self, "_life_simulator_started", False):
            return
        life_sim = getattr(self, "_life_simulator", None)
        if life_sim is None:
            return
        self._life_simulator_started = True
        # issue#43 Wave1：启用了生活模拟却没配 provider_id 是「静默冻结」的配置陷阱根源，
        # 启动时响亮告警一次（_life_sim_llm_call 里还会按 cause 节流告警，但这条最早可见）。
        if life_sim.enabled and not str(
            self._config.get("sylanne_alpha_life_simulation_provider_id") or ""
        ).strip():
            logger.warning(
                "Sylanne autonomy: 生活模拟已启用，但未配置 "
                "sylanne_alpha_life_simulation_provider_id —— 生活模拟会静默失效"
                "（生活状态冻结、主动消息可能复读）。请在插件配置里为它选一个 LLM Provider。"
            )
        pipe = self._llm_request_pipeline
        life_sim.configure(
            llm_caller=pipe._life_sim_llm_call,
            outreach_callback=pipe._life_sim_outreach,
            emotion_getter=pipe._life_sim_emotion,
            body_delta_callback=pipe._life_sim_body_delta,
            persona_getter=pipe._life_sim_persona_getter,
            memory_summary_getter=pipe._life_sim_memory_summary,
            countdown_callback=self._life_sim_adjust_countdown,
            state_dirty_callback=self._life_sim_throttled_save,
            qzone_candidate_callback=pipe._qzone_candidate_handler,
        )
        # 启动全局自驱心跳（替代原 life_sim.start() 的后台循环）。
        # LifeSim 持久化状态恢复在 async initialize 里 await（KV 读为异步）。
        self._autonomy_scheduler.start()
        logger.info(
            f"Sylanne autonomy: life_sim enabled={life_sim.enabled}, "
            f"interval={life_sim.interval_seconds}s, scheduler started at initialize"
        )

    async def initialize(self) -> None:
        """AstrBot 插件生命周期钩子：加载后调用（有 running loop，不依赖用户消息）。"""
        # MEM-03 PR-1：把记忆写入咽喉权威绑定到本 running loop——此后 off-loop（stdlib
        # WebUI 工作线程）提交经 call_soon_threadsafe 转入本 loop 串行执行，不再静默丢弃。
        try:
            sp = getattr(self, "_state_persistence", None)
            throat = getattr(sp, "_throat", None) if sp is not None else None
            if throat is not None:
                throat.bind_loop(asyncio.get_running_loop())
        except Exception as e:
            logger.debug(f"Sylanne memory throat loop bind skipped: {e}")
        # DATA-LOSS 修复：绑定 AstrBot 进程级 persistent main loop，供
        # webui_server.py 的 stdlib ThreadingHTTPServer 回退路径（worker 线程无
        # running loop）用 run_coroutine_threadsafe 提交持久化 purge/consolidation
        # 协程到「真正在跑」的 loop（镜像上面 throat.bind_loop 的既有模式）。必须在
        # 本 loop 上调用、且早于 stdlib 服务器开始处理任何请求——initialize() 保证
        # 两者都满足。WebUI 是可选子系统，绑定失败不应阻断插件其余初始化。
        try:
            _sylanne_webui_server.set_main_loop(asyncio.get_running_loop())
        except Exception as e:
            logger.debug(f"Sylanne WebUI main loop bind skipped: {e}")
        # MEM-03 PR-4：启动扫描跨重启 pending-delete 索引——完成/驳回上一次进程运行
        # 遗留的删除意图残留（primary 已空则补完；primary 非空绝不重放，交管理员），
        # 并把未决 entry 载入进程内镜像供本次运行期间 hydrate/load-admit 消费
        # （见 state_persistence.py::_scan_pending_deletes）。须在 bind_loop 之后、
        # 任何用户消息/WebUI 请求之前跑；扫描本身失败不应阻断插件其余初始化。
        try:
            sp = getattr(self, "_state_persistence", None)
            scan_fn = getattr(sp, "_scan_pending_deletes", None) if sp is not None else None
            if callable(scan_fn):
                await scan_fn()
        except Exception as e:
            logger.debug(f"Sylanne memory pending-delete scan skipped: {e}")
        # 恢复 LifeSim 持久化状态（修复历史「重启丢作息」缺陷）——KV 读为异步，故在此 await
        try:
            life_sim = getattr(self, "_life_simulator", None)
            if life_sim is not None and self._has_kv_api():
                saved = await self.get_kv_data("sylanne_life_sim_state", None)
                if saved and isinstance(saved, dict):
                    life_sim.from_dict(saved)
        except Exception as e:
            logger.debug(f"Sylanne life sim state restore skipped: {e}")
        # T1-04②：恢复 RhythmLearner 持久化状态（重启保节奏画像，不从零重学）。
        try:
            if self._has_kv_api():
                saved_rhythm = await self.get_kv_data(
                    "sylanne_rhythm_learner_state", None
                )
                if saved_rhythm and isinstance(saved_rhythm, dict):
                    self._rhythm_learner = RhythmLearner.from_dict(
                        saved_rhythm,
                        intimacy_threshold=self._rhythm_learner._intimacy_threshold,
                    )
        except Exception as e:
            logger.debug(f"Sylanne rhythm learner state restore skipped: {e}")
        # T2-06⑤：恢复关系仪式注册表持久化状态（重启不丢已学到的问候/晚安仪式），
        # 并把已注册的仪式重新接线回 ProactiveScheduler（否则重启后 check_ritual_absence
        # 读到的调度器仪式表是空的，需要再攒 3 次观测才恢复可达）。
        try:
            if self._has_kv_api():
                from sylanne_alpha.session_context import _RITUAL_REGISTRY_KV_KEY

                saved_rituals = await self.get_kv_data(_RITUAL_REGISTRY_KV_KEY, None)
                if saved_rituals and isinstance(saved_rituals, dict):
                    registry = RitualRegistry.from_dict(saved_rituals)
                    self._session_ctx._ritual_registry = registry
                    scheduler = getattr(self, "_proactive_scheduler", None)
                    register = getattr(scheduler, "register_ritual", None)
                    if callable(register):
                        for key, ritual in registry._rituals.items():
                            key_session, _, _pattern_key = key.rpartition(":")
                            if not key_session:
                                continue
                            register(
                                key_session,
                                str(ritual.get("pattern", _pattern_key)),
                                int(ritual.get("hour_start", 0)),
                                int(ritual.get("hour_end", 1)),
                            )
        except Exception as e:
            logger.debug(f"Sylanne ritual registry state restore skipped: {e}")
        # Phase 2B / PR-H：恢复关系层状态（register_state + override，独立 KV key）
        try:
            if self._has_kv_api():
                from sylanne_alpha import relationship_layer as _rl
                rel_saved = await self.get_kv_data(_rl._KV_KEY, None)
                if rel_saved and isinstance(rel_saved, dict):
                    _rl.restore(self, rel_saved)
        except Exception as e:
            logger.debug(f"Sylanne relationship state restore skipped: {e}")
        # PR-Qzone：恢复说说功能审计/频率闸状态（独立 KV key，重启不丢当日/当周计数，
        # 否则重启即可绕过频率闸上限）。
        try:
            if self._has_kv_api():
                from sylanne_alpha import qzone_share as _qz
                qzone_saved = await self.get_kv_data(_qz._KV_KEY, None)
                if qzone_saved and isinstance(qzone_saved, dict):
                    self._qzone_audit = _qz.QzoneAuditState.from_dict(qzone_saved)
        except Exception as e:
            logger.debug(f"Sylanne qzone audit state restore skipped: {e}")
        # PR-Qzone：建立说说发布用的 aiohttp session（terminate 时收）。建立失败
        # （aiohttp 未装等极端情况）不阻断其余初始化——发布时 qzone_share._do_publish
        # 会因 session 为 None 直接返回失败，走 owner 过目门的失败提示路径。
        try:
            import aiohttp
            if self._qzone_http_session is None or self._qzone_http_session.closed:
                self._qzone_http_session = aiohttp.ClientSession()
        except Exception as e:
            logger.debug(f"Sylanne qzone http session init skipped: {e}")
        # issue#43 Wave2：还原崩溃中断的主动发言桥接 override 基线（provenance 恢复，
        # 把用户自配 proactive_prompt 一起带回；无残留则 no-op，绝不盲删大饼配置）。
        try:
            bridge = getattr(self, "_proactive_bridge", None)
            if bridge is not None:
                n = await bridge.recover_inflight_baselines()
                if n:
                    logger.info(
                        f"Sylanne proactive_bridge: 启动还原了 {n} 个崩溃残留的 override 基线"
                    )
        except Exception as e:
            logger.debug(f"Sylanne proactive_bridge baseline recovery skipped: {e}")
        # emotion_spirit 适配桥：仅在配置开启且探测到 emotion_spirit 时激活（关它的 persona
        # 注入，让 Sylanne 当 system_prompt 唯一主）。未装 / 未开 → 完全 no-op，零影响。
        try:
            es_bridge = getattr(self, "_emotion_spirit_bridge", None)
            es_on = bool(
                (self.config or {}).get("sylanne_alpha_emotion_spirit_bridge_enabled", False)
            )
            # v2core 请求阶段无条件运行；本桥只保留自身配置、存在性和可用性门控。
            if es_bridge is not None and es_on and es_bridge.available():
                res = es_bridge.activate()
                if res.get("active"):
                    logger.info(
                        "Sylanne emotion_spirit 桥：已激活（persona 注入交还 Sylanne 主控，每轮请求"
                        "自愈重申）。状态消费已按稳定契约接线（v2core 请求阶段、观察式）。注：emotion_spirit"
                        " v1.1.0 的 SurfaceConsumer 缓存上游未喂 session_id，PublicAPI 暂对任何 key 返"
                        " None → 状态消费暂空转，待上游修复自动生效。记忆仍以 Sylanne 原生为主控（写入"
                        "接管/镜像双写按 Design B 延后）；引擎共享已确认结构上不可行、不提供该开关。"
                    )
        except Exception as e:
            logger.debug(f"Sylanne emotion_spirit bridge activation skipped: {e}")
        try:
            self._start_life_simulator()
        except Exception as e:
            logger.error(f"Sylanne initialize: autonomy start failed: {e}", exc_info=True)
        # v3 shadow（plan Task 13）：默认关时 initialize() 直接 return False，零 IO 零线程。
        # 开启时它内部先 acquire epoch 再起私有 worker；起不来只 fail-close v3，v2 照常。
        # 放在最后：v3 只观察，绝不能挡住任何 v2 子系统的初始化。
        await self._v3_shadow.initialize(
            root=Path(get_astrbot_data_path()) / "plugin_data" / PLUGIN_NAME / "v3_shadow"
        )

    async def _life_sim_adjust_countdown(self) -> None:
        """生命模拟 tick 回调：用 Sylanne 当前状态拨动大饼下一次主动发言倒计时。

        仅在桥接开关开启且大饼可用时生效；选最近活跃会话。失败静默。
        """
        bridge = getattr(self, "_proactive_bridge", None)
        if bridge is None:
            return
        if not (self.config or {}).get("sylanne_alpha_proactive_bridge_enabled", False):
            return
        if not bridge.available():
            return
        session_key = self._llm_request_pipeline._most_recent_host_key()
        if not session_key:
            return
        try:
            await bridge.adjust_countdown(session_key)
        except Exception as e:
            logger.warning(f"Sylanne adjust_countdown callback: {e}", exc_info=True)

    async def _life_sim_throttled_save(self) -> None:
        """PR-A5：tick 后节流落盘 life sim 状态到 KV。

        规则（修 H4：原基线仅 initialize/terminate 读写，崩溃丢全部演化）：
        - 距上次落盘 < _LIFE_SIM_SAVE_MIN_GAP_SECONDS（默认 90s）则跳过。
        - 上一次保存仍在进行则跳过（_dirty_in_flight 防重入）。
        - 无 KV API 则跳过（与 initialize/terminate 的 _has_kv_api 一致）。
        - 失败静默（不阻断演化心跳），最后一次仍由 terminate 兜底。
        """
        now = time.time()
        if self._life_sim_dirty_in_flight:
            return
        if (now - self._life_sim_last_save_ts) < _LIFE_SIM_SAVE_MIN_GAP_SECONDS:
            return
        if not self._has_kv_api():
            return
        life_sim = getattr(self, "_life_simulator", None)
        if life_sim is None:
            return
        self._life_sim_dirty_in_flight = True
        self._life_sim_last_save_ts = now
        try:
            await self.put_kv_data("sylanne_life_sim_state", life_sim.to_dict())
        except Exception as e:
            logger.debug(f"Sylanne life sim throttled save skipped: {e}")
        finally:
            self._life_sim_dirty_in_flight = False

    async def _qzone_audit_throttled_save(self) -> None:
        """PR-Qzone：节流落盘说说审计/频率闸状态（镜像 _life_sim_throttled_save）。

        由 qzone_share 模块每次记审计条目时派发，受 min-gap 节流；失败静默，
        最后一次仍由 terminate 兜底。频率闸计数（daily/weekly post_timestamps）
        重启不落盘会让频率闸失效，因此本方法与 initialize 的 KV 恢复是配套契约。
        """
        now = time.time()
        if self._qzone_audit_dirty_in_flight:
            return
        if (now - self._qzone_audit_last_save_ts) < _QZONE_AUDIT_SAVE_MIN_GAP_SECONDS:
            return
        if not self._has_kv_api():
            return
        audit = getattr(self, "_qzone_audit", None)
        if audit is None:
            return
        self._qzone_audit_dirty_in_flight = True
        self._qzone_audit_last_save_ts = now
        try:
            from sylanne_alpha import qzone_share as _qz
            await self.put_kv_data(_qz._KV_KEY, audit.to_dict())
        except Exception as e:
            logger.debug(f"Sylanne qzone audit throttled save skipped: {e}")
        finally:
            self._qzone_audit_dirty_in_flight = False

    async def _rhythm_learner_throttled_save(self) -> None:
        """T1-04②：节流落盘 RhythmLearner 状态（镜像 _life_sim_throttled_save）。

        由 on_message 高频驱动（每条消息都尝试一次），但受 min-gap 节流，实际
        写 KV 频率与 life_sim 同量级。失败静默（不阻断消息处理），最后一次仍由
        terminate 兜底。
        """
        now = time.time()
        if self._rhythm_learner_dirty_in_flight:
            return
        if (now - self._rhythm_learner_last_save_ts) < _RHYTHM_LEARNER_SAVE_MIN_GAP_SECONDS:
            return
        if not self._has_kv_api():
            return
        self._rhythm_learner_dirty_in_flight = True
        self._rhythm_learner_last_save_ts = now
        try:
            await self.put_kv_data(
                "sylanne_rhythm_learner_state", self._rhythm_learner.to_dict()
            )
        except Exception as e:
            logger.debug(f"Sylanne rhythm learner throttled save skipped: {e}")
        finally:
            self._rhythm_learner_dirty_in_flight = False

    async def _rel_state_throttled_save(self) -> None:
        """PR-H 解耦：关系层状态独立节流落盘到 KV（独立 KV key）。

        由真正写关系层状态的三点位触发（rel_register 累积 / /bond / /unbond），
        经 relationship_layer.request_persist → safe_ensure_future 后台跑。
        与 _life_sim_throttled_save 完全独立——life_sim 关闭不影响关系层落盘。

        leading+trailing edge 节流：
        - 窗外（距上次 ≥ gap）：立即落盘（leading edge）。
        - 窗内：标脏 + 调度一个窗口末兜底落盘（trailing edge），确保最后一次改
          （如 /bond 紧接 /unbond）即便无后续事件、非优雅退出也能落，不丢尾改。
        """
        now = time.time()
        gap = now - self._rel_state_last_save_ts
        if gap < _REL_STATE_SAVE_MIN_GAP_SECONDS:
            # 节流窗内：标脏并调度窗口末强制落盘（只调度一次，避免任务堆积）
            if not self._rel_state_pending_dirty:
                self._rel_state_pending_dirty = True
                delay = _REL_STATE_SAVE_MIN_GAP_SECONDS - gap
                from sylanne_alpha.infra import safe_ensure_future

                async def _trailing_save() -> None:
                    try:
                        await asyncio.sleep(max(0.0, delay))
                    except Exception:
                        return
                    # 窗末兜底：仅当仍有未落的尾改才落盘（延迟期间若已被 leading
                    # edge 落过，pending_dirty 已清，跳过以免冗余写）
                    if self._rel_state_pending_dirty:
                        await self._do_rel_state_save()

                safe_ensure_future(
                    _trailing_save(),
                    name="rel_state_trailing_save",
                    task_list=getattr(self, "_background_tasks", None),
                )
            return
        await self._do_rel_state_save()

    async def _do_rel_state_save(self) -> None:
        """实际落盘（绕过节流，供 leading edge 与 trailing 兜底共用）。防重入 + 失败静默。"""
        if self._rel_state_dirty_in_flight:
            self._rel_state_pending_dirty = True  # 在途时来的改，落完再补
            return
        if not self._has_kv_api():
            return
        self._rel_state_dirty_in_flight = True
        self._rel_state_last_save_ts = time.time()
        self._rel_state_pending_dirty = False
        try:
            from sylanne_alpha import relationship_layer as _rl
            await self.put_kv_data(_rl._KV_KEY, _rl.snapshot(self))
        except Exception as e:
            logger.debug(f"Sylanne relationship state throttled save skipped: {e}")
        finally:
            self._rel_state_dirty_in_flight = False
            # 落盘期间若又有改（pending_dirty 被重新置位），再补一次
            if self._rel_state_pending_dirty:
                self._rel_state_pending_dirty = False
                from sylanne_alpha.infra import safe_ensure_future
                safe_ensure_future(
                    self._do_rel_state_save(),
                    name="rel_state_followup_save",
                    task_list=getattr(self, "_background_tasks", None),
                )

    async def terminate(self) -> None:
        """插件卸载/更新前的清理：停止所有后台任务、关闭 WebUI、持久化状态。"""
        # v3 shadow（plan Task 13）：先【同步】关闸，让接下来的 v2 收尾 save 排干期间
        # 不再有新的影子轮进来。同步是关键——这里不能 await，否则 drain 之前就出让了
        # 事件循环，还能被塞进新的 capture/settle。
        self._v3_shadow.begin_shutdown()
        # v2core：先排干在途域状态落盘 + 终扫一遍（必须在 cancel 后台任务【之前】，
        # 否则最后一轮 fire-and-forget 存档会被反手 cancel——她的最近成长就丢了）
        try:
            from sylanne_alpha.v2core.integration import (
                drain_pending_saves,
                save_all_domains,
            )

            await drain_pending_saves(timeout=5)
            await save_all_domains(self)
        except Exception as e:
            logger.warning(
                "Sylanne v2core terminate save failed (domain state may be stale): %s",
                e,
                exc_info=True,
            )
        # emotion_spirit 桥：卸载前还原它的 persona_mode（接管时我们把它设成了 disabled，不还原
        # 会把人家插件永久静音、需重启才恢复，红队 lifecycle MAJOR）。cheap getattr/setattr、吞错。
        try:
            es_bridge = getattr(self, "_emotion_spirit_bridge", None)
            if es_bridge is not None and es_bridge.is_active():
                es_bridge.deactivate()
        except Exception as e:
            logger.debug(f"Sylanne emotion_spirit bridge deactivate skipped: {e}")
        # v3 shadow：v2 的 save 已经排干，这里给 v3 自己的有序关停一个有限窗口。正常时
        # 它仍在下面那轮【通用 task 取消】之前完成；若 commit/fsync/线程退出永久卡住，facade
        # 会保留清理 task 但按上限返回，绝不能把 v2 与整个插件退出一起拖死。
        await self._v3_shadow.terminate()
        # 收集所有需要取消的任务
        tasks_to_cancel: list = []
        for task in list(self._background_tasks):
            if not task.done():
                task.cancel()
                tasks_to_cancel.append(task)
        self._background_tasks.clear()
        for task in list(self._store.background_post_checkpoint_tasks.values()):
            if not task.done():
                task.cancel()
                tasks_to_cancel.append(task)
        self._store.background_post_checkpoint_tasks.clear()
        sched_task = getattr(self, "_proactive_scheduler_task", None)
        if sched_task and not sched_task.done():
            sched_task.cancel()
            tasks_to_cancel.append(sched_task)
        # 等待所有取消的任务完成（带超时保护）
        if tasks_to_cancel:
            await asyncio.wait(tasks_to_cancel, timeout=10)
        # 停止全局自驱心跳（CP8-P3b：替代原 life_simulator.stop）
        sched = getattr(self, "_autonomy_scheduler", None)
        if sched is not None:
            sched_self_task = sched._task
            sched.stop()
            # 等自驱 task 真正收尾，消除「stop 仅 cancel 未 await」与下方
            # 退出巩固之间的并发窗口（避免重入 session_lock 的潜在竞态）。
            if sched_self_task is not None and not sched_self_task.done():
                try:
                    await asyncio.wait_for(
                        asyncio.shield(sched_self_task), timeout=5
                    )
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                except Exception as e:
                    logger.debug(f"Sylanne autonomy task drain: {e}")
            # CP8-P4-D：退出前对活跃会话做一次最终巩固（tick_decay + 进化档案落盘），
            # 保证反应式学习累积的门控偏置不随关机丢失。零 LLM、绕 needs 守卫强制落盘。
            consol = getattr(sched, "_consolidation", None)
            if consol is not None:
                try:
                    now = time.time()
                    for sk, _host in self._store.hosts.snapshot_items():
                        await consol.consolidate(sk, now)
                except Exception as e:
                    logger.debug(f"Sylanne terminate consolidate skipped: {e}")
        # 持久化 LifeSim 状态（修复历史「重启丢作息」缺陷）
        try:
            life_sim = getattr(self, "_life_simulator", None)
            if life_sim is not None and self._has_kv_api():
                await self.put_kv_data("sylanne_life_sim_state", life_sim.to_dict())
        except Exception as e:
            logger.debug(f"Sylanne life sim state persist skipped: {e}")
        # T1-04②：持久化 RhythmLearner 状态（终扫落盘，兜底 throttled save 漏窗）
        try:
            if self._has_kv_api():
                await self.put_kv_data(
                    "sylanne_rhythm_learner_state", self._rhythm_learner.to_dict()
                )
        except Exception as e:
            logger.debug(f"Sylanne rhythm learner state persist skipped: {e}")
        # T2-06⑤：持久化 RitualRegistry 状态（终扫落盘，兜底命中即存漏窗）
        try:
            if self._has_kv_api():
                from sylanne_alpha.session_context import _RITUAL_REGISTRY_KV_KEY

                await self.put_kv_data(
                    _RITUAL_REGISTRY_KV_KEY, self._session_ctx._ritual_registry.to_dict()
                )
        except Exception as e:
            logger.debug(f"Sylanne ritual registry state persist skipped: {e}")
        # Phase 2B / PR-H：关系层状态终扫落盘（独立 KV key）
        try:
            if self._has_kv_api():
                from sylanne_alpha import relationship_layer as _rl
                await self.put_kv_data(_rl._KV_KEY, _rl.snapshot(self))
        except Exception as e:
            logger.debug(f"Sylanne relationship state persist skipped: {e}")
        # PR-Qzone：说说审计/频率闸状态终扫落盘（独立 KV key，兜底节流漏窗）
        try:
            audit = getattr(self, "_qzone_audit", None)
            if audit is not None and self._has_kv_api():
                from sylanne_alpha import qzone_share as _qz
                await self.put_kv_data(_qz._KV_KEY, audit.to_dict())
        except Exception as e:
            logger.debug(f"Sylanne qzone audit state persist skipped: {e}")
        # PR-Qzone：关闭说说发布用的 aiohttp session
        try:
            session = getattr(self, "_qzone_http_session", None)
            if session is not None and not session.closed:
                await session.close()
        except Exception as e:
            logger.debug(f"Sylanne qzone http session close skipped: {e}")
        # 关闭独立 WebUI 服务器
        try:
            await stop_webui_server()
        except Exception as e:
            logger.warning(f"Sylanne WebUI terminate: {e}")
        # 持久化运行时状态（带超时保护）
        try:
            await asyncio.wait_for(self._state_persistence.terminate(), timeout=15)
        except asyncio.TimeoutError:
            logger.warning("Sylanne state persistence terminate timed out (15s)")

    async def _send_realtime_chat_plan(
        self,
        event: Any,
        plan: dict[str, Any],
        *,
        source: str = "",
        record_history_shadow: bool = False,
    ) -> dict[str, Any]:
        return await self._realtime_dispatch.send_realtime_chat_plan(
            event, plan, source=source, record_history_shadow=record_history_shadow
        )

    async def _flush_sylanne_memory_pending_observations(
        self, session_key: str, *, generation: int = 0, force: bool = False
    ) -> None:
        flush_fn = getattr(self, "_flush_memory_observations", None)
        if flush_fn and callable(flush_fn):
            await flush_fn(session_key, force=force)

    def _record_realtime_assistant_history_shadow(
        self, session_key: str, **kwargs: Any
    ) -> None:
        self._realtime_dispatch.record_realtime_assistant_history_shadow(
            session_key, **kwargs
        )

    def _record_interrupted_reply_breakpoint(
        self, session_key: str, **kwargs: Any
    ) -> None:
        self._realtime_dispatch.record_interrupted_reply_breakpoint(
            session_key, **kwargs
        )

    def _realtime_delivery_context_kv_key(self, session_key: str) -> str:
        return self._realtime_dispatch.realtime_delivery_context_kv_key(session_key)

    def _record_realtime_ordinary_history_backfill(
        self, session_key: str, **kwargs: Any
    ) -> None:
        self._realtime_dispatch.record_realtime_ordinary_history_backfill(
            session_key, **kwargs
        )

    def _record_active_agent_pending_user_turn(
        self, session_key: str, identity: Any = None, **kwargs: Any
    ) -> None:
        self._realtime_dispatch.record_active_agent_pending_user_turn(
            session_key, identity, **kwargs
        )

    def _fast_assessor_max_context_chars(self) -> int:
        return self._realtime_dispatch.fast_assessor_max_context_chars()

    def _discard_conversation_pending_response_epoch(
        self, session_key: str, epoch: int = 0
    ) -> None:
        self._realtime_dispatch.discard_conversation_pending_response_epoch(
            session_key, epoch
        )

    def _conversation_reply_is_stale(self, session_key: str, reply_epoch: int) -> bool:
        return self._realtime_dispatch.conversation_reply_is_stale(
            session_key, reply_epoch
        )

    def _realtime_assistant_history_shadow_cache(
        self,
    ) -> dict[str, list[dict[str, Any]]]:
        return self._realtime_dispatch.realtime_assistant_history_shadow_cache()

    def _append_realtime_assistant_history_shadow_if_any(
        self, request: Any, session_key: str, **kwargs: Any
    ) -> bool:
        return self._realtime_dispatch.append_realtime_assistant_history_shadow_if_any(
            request, session_key, **kwargs
        )

    def _append_interrupted_reply_breakpoint_if_any(
        self, request: Any, session_key: str, **kwargs: Any
    ) -> bool:
        return self._realtime_dispatch.append_interrupted_reply_breakpoint_if_any(
            request, session_key, **kwargs
        )

    def _build_realtime_delivery_envelope_text(self, text: str, **kwargs: Any) -> str:
        return self._realtime_dispatch.build_realtime_delivery_envelope_text(
            text, **kwargs
        )

    def _start_realtime_chat_active_dispatch(
        self, session_key: str, **kwargs: Any
    ) -> None:
        self._realtime_dispatch.start_realtime_chat_active_dispatch(
            session_key, **kwargs
        )

    def _append_realtime_chat_active_dispatch_if_any(
        self, request: Any, session_key: str, **kwargs: Any
    ) -> bool:
        return self._realtime_dispatch.append_realtime_chat_active_dispatch_if_any(
            request, session_key, **kwargs
        )

    def _append_realtime_continuity_context_if_any(
        self, request: Any, session_key: str, **kwargs: Any
    ) -> bool:
        return self._realtime_dispatch.append_realtime_continuity_context_if_any(
            request, session_key, **kwargs
        )

    def _realtime_ordinary_history_backfill_cache(
        self,
    ) -> dict[str, list[dict[str, Any]]]:
        return self._realtime_dispatch.realtime_ordinary_history_backfill_cache()

    async def _release_realtime_temporary_context_after_background_post(
        self, session_key: str, **kwargs: Any
    ) -> None:
        await self._realtime_dispatch.release_realtime_temporary_context_after_background_post(
            session_key, **kwargs
        )

    def _release_realtime_temporary_context_after_background_post_in_memory(
        self, session_key: str, **kwargs: Any
    ) -> bool:
        return self._realtime_dispatch.release_realtime_temporary_context_after_background_post_in_memory(
            session_key, **kwargs
        )

    # LLM Tool: query_agent_state
    @_model_function_tool(name="query_agent_state")
    async def _llm_tool_query_agent_state(self, event: Any) -> Any:
        """查询 Sylanne 当前情感状态和计算脊柱摘要。"""
        return await self._public_api._llm_tool_query_agent_state(event)
