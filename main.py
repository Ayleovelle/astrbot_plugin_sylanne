"""Sylanne-Embodiment -- AstrBot 插件主入口模块。

本模块是 Sylanne 情感身体运行时的 AstrBot 插件薄宿主层，职责：
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

import os
import sys

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

import asyncio  # noqa: E402
import collections  # noqa: E402
import contextvars  # noqa: E402
import importlib  # noqa: E402
import json  # noqa: E402
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

        def on_decorating_result(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def llm_tool(self, *args, **kwargs):
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
from sylanne_alpha.compat import (  # noqa: E402
    command_surface,
    memory_surface,
    realtime_dispatch,
    reset_surface,  # noqa: E402
)
from sylanne_alpha.host import SylanneAlphaHost, SylanneAlphaHostEvent  # noqa: E402
from sylanne_alpha.life_simulation import LifeSimulator  # noqa: E402
from sylanne_alpha.memory_system import MemorySystem  # noqa: E402
from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline  # noqa: E402
from sylanne_alpha.rhythm_learner import RhythmLearner  # noqa: E402
from sylanne_alpha.proactive_scheduler import ProactiveScheduler  # noqa: E402
from sylanne_alpha.proactive_bridge import ProactiveBridge  # noqa: E402
from sylanne_alpha.session_context import SessionContext  # noqa: E402
from sylanne_alpha.session_state_store import SessionStateStore  # noqa: E402
from sylanne_alpha.agents import (  # noqa: E402
    SelfCore,
    AutonomyScheduler,
    EmotionAgent,
    AssessorAgent,
    PersonaAgent,
    LifeAgent,
    MemoryAgent,
    RhythmAgent,
    ProactiveAgent,
    SocialAgent,
    DialogueAgent,
)
from sylanne_alpha.social_field import SocialFieldCollector  # noqa: E402
from sylanne_alpha.llm_response_pipeline import LLMResponsePipeline  # noqa: E402
from sylanne_alpha.public_api import PublicAPI  # noqa: E402
from sylanne_alpha.state_persistence import StatePersistence  # noqa: E402
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
PLUGIN_VERSION = "1.4.5"
PUBLIC_API_VERSION = "1.0"
MAX_LLM_REQUEST_PROMPT_CHARS = 12000
_MAX_PAYLOAD_SERIALIZED_CHARS = 60000
_MAX_UNFINISHED_CONTEXT_CHARS = 2000
_CHINA_TZ = timezone(timedelta(hours=8))

_INTERNAL_LLM_CALL: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "_INTERNAL_LLM_CALL", default=False
)
PROACTIVE_SCHEDULER_WAKE_DELAY_SECONDS = 30.0
PROACTIVE_SCHEDULER_IDLE_DELAY_SECONDS = 1800.0

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
        "model_hint",
        "max_added_chars",
        "max_parts",
        "added_chars",
        "appended",
        "warnings",
        "context_owner",
    )

    def __init__(self, session_key: str = "", model_hint: str = ""):
        self.session_key = session_key
        self.compat_mode = ""
        self.injected: list[dict[str, Any]] = []
        self.skipped: list[dict[str, Any]] = []
        self.model_hint = model_hint
        self.max_added_chars: int = 2400
        self.max_parts: int = 8
        self.added_chars: int = 0
        self.appended: list[dict[str, Any]] = []
        self.warnings: list[str] = []
        self.context_owner: str = "sylanne_plugin"


# ---------------------------------------------------------------------------
# EmotionalStatePlugin -- Sylanne-Embodiment 薄宿主层
# ---------------------------------------------------------------------------
@register(
    "astrbot_plugin_sylanne",
    "Aylovelle.S.S",
    "Sylanne-Embodiment: sovereign emotional body runtime.",
    "1.3.0",
    "https://github.com/Ayleovelle/astrbot_plugin_sylanne",
)
class EmotionalStatePlugin(Star):
    """Sylanne-Embodiment 情感身体运行时插件。

    继承 AstrBot Star 基类，作为 AstrBot 插件运行。
    通过事件钩子（on_llm_request/on_llm_response）在 LLM 管线中
    注入情感状态上下文，实现「有身体感的 AI」。

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
        self.logger = logger
        # 生命模拟器：idle 时自主演化身体状态
        self._life_simulator = LifeSimulator(config=self._config)
        self._life_simulator_started = False
        self._meltdown_nonces: BoundedDict = BoundedDict(maxsize=50, ttl=300)
        # 社交场收集器：群聊氛围感知
        self._social_field = SocialFieldCollector(config=self._config)
        # 后台投递队列已迁入 self._store（CP8-P2 批2）
        self._background_post_recovered_sessions: set[str] = set()
        self._internal_assessor_llm_inflight: int = 0
        # outreach/origins/candidates/locks/realtime_dispatches 已迁入 self._store（批3）
        self._amnesia_sessions: set[str] = set()
        self._proactive_scheduler_task: asyncio.Task | None = None
        # 子系统初始化：各子系统持有 self 引用，通过委托模式分工
        self._session_ctx = SessionContext(self)
        self._state_persistence = StatePersistence(self)
        self._realtime_dispatch = RealtimeDispatch(self)
        self._background_queue = BackgroundPostQueue(self)
        self._webui_routes = WebUIRoutes(self)
        self._memory_system = self._memory_system_for_session("default")
        # 异步评估器：调用 LLM 评估用户文本的情感维度
        self._async_assessor = AsyncAssessor(config=self._config)
        self._llm_response_pipeline = LLMResponsePipeline(self)
        self._llm_request_pipeline = LLMRequestPipeline(self)
        self._public_api = PublicAPI(self)
        # SelfCore 认知编排器（CP8-P3a）：注册全部 9 个 agent。
        # PRE（影响计算）：emotion/assessor/persona/life/memory；
        # 请求-POST（消化计算结果）：rhythm/memory/proactive；
        # 响应-POST（消化 bot 回复）：social/dialogue。
        self._self_core = SelfCore(self, llm_budget=3)
        for _agent_cls in (
            EmotionAgent, AssessorAgent, PersonaAgent, LifeAgent,
            MemoryAgent, RhythmAgent, ProactiveAgent,
            SocialAgent, DialogueAgent,
        ):
            self._self_core.register(_agent_cls(self, self._self_core.bus))
        # 全局自驱心跳（CP8-P3b）：让她没人说话也演化。initialize 启动、terminate 回收。
        self._autonomy_scheduler = AutonomyScheduler(self, self._self_core)
        # 主动发言调度器：基于身体需求和节律决定是否主动发言
        self._proactive_scheduler = ProactiveScheduler(self)
        # 主动发言桥接器：把意图+生活素材交给大饼插件执行发送
        self._proactive_bridge = ProactiveBridge(self)
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
        from quart import request as quart_request

        body = await quart_request.get_json(silent=True) or {}
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
        return self._session_ctx.memory_system_for_session(session_key)

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

    # Diagnostics / Export / Import / Control
    async def sylanne_diagnostics(self, *, session_key: str) -> dict[str, Any]:
        host = self._host(session_key)
        return host.diagnostics()

    async def export_sylanne_alpha(self, *, session_key: str) -> dict[str, Any]:
        host = self._host(session_key)
        snapshot = host.snapshot()
        snapshot["session_key"] = session_key
        return snapshot

    async def import_sylanne_legacy(
        self, legacy: dict[str, Any], *, session_key: str
    ) -> dict[str, Any]:
        root = self._config.get("sylanne_alpha_root") or str(
            Path(get_astrbot_data_path()) / "plugin_data" / PLUGIN_NAME
        )
        _host_obj = SylanneAlphaHost(
            root=root, session_key=session_key, legacy=legacy
        )
        self._store.set_host(session_key, _host_obj)
        return _host_obj.snapshot()

    async def pause_sylanne(self, *, session_key: str) -> dict[str, Any]:
        host = self._host(session_key)
        host.kernel.body.immunity.paused = True
        await self._persist_kernel(session_key, host)
        return host.diagnostics()

    async def resume_sylanne(self, *, session_key: str) -> dict[str, Any]:
        host = self._host(session_key)
        host.kernel.body.immunity.paused = False
        await self._persist_kernel(session_key, host)
        return host.diagnostics()

    async def cooldown_sylanne(self, *, session_key: str) -> dict[str, Any]:
        host = self._host(session_key)
        host.kernel.body.immunity.cooldown = max(
            host.kernel.body.immunity.cooldown, 0.5
        )
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

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: Any):
        """监听所有消息事件，更新 proactive scheduler 时间戳和节奏学习器。"""
        try:
            session_key = self._session_ctx.session_key(event)
            now = time.time()
            # 更新最后消息时间，供 proactive scheduler 计算沉默时长
            self._store.last_user_message_time.set(session_key, now)
            # 喂给节奏学习器（记录 tempo，不受亲密度门控）
            self._rhythm_learner._record_tempo(session_key, now)
        except Exception:
            pass

    # on_llm_request 钩子：在 LLM 请求发出前注入情感状态上下文
    @filter.on_llm_request(desc="注入 Sylanne 情感计算上下文到 LLM prompt")
    async def on_llm_request(self, event: Any, request: Any) -> None:
        try:
            await self._on_llm_request_inner(event, request)
        except Exception as e:
            logger.error(f"Sylanne on_llm_request error: {e}", exc_info=True)
            return

    def _session_lock(self, session_key: str) -> asyncio.Lock:
        return self._session_ctx.session_lock(session_key)

    async def _on_llm_request_inner(self, event: Any, request: Any) -> None:
        return await self._llm_request_pipeline._on_llm_request_inner(event, request)

    async def _process_llm_request_final(
        self,
        event: Any,
        request: Any,
        message_text: str,
        session_key: str,
        realtime_enabled: bool,
        hajide: bool,
        intercept: bool,
    ) -> None:
        return await self._llm_request_pipeline._process_llm_request_final(
            event,
            request,
            message_text,
            session_key,
            realtime_enabled,
            hajide,
            intercept,
        )

    async def _get_model_hint(self, event: Any = None) -> str:
        return await self._llm_request_pipeline._get_model_hint(event)

    def _schedule_buffer_persist(self, session_key: str) -> None:
        self._state_persistence.schedule_buffer_persist(session_key)

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
    async def on_llm_response(self, event: Any, response: Any) -> None:
        try:
            await self._on_llm_response_inner(event, response)
        except Exception as e:
            logger.error(f"Sylanne on_llm_response error: {e}", exc_info=True)
            return

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: Any) -> None:
        """Stage 8 兜底：strip thinking/draft 块，防止 tool loop 中间步骤泄露。

        另：若该消息是 Sylanne 主动发言桥接登记的"待接管分段"，则清空 chain 阻止
        大饼整段发送，改由 Sylanne 后台连发人格化分段。
        """
        try:
            # 分段接管优先判定（大饼主动消息）
            if await self._maybe_takeover_segments(event):
                return

            from sylanne_alpha.compat import strip_draft_blocks

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
            from sylanne_alpha.compat.facade import realtime_plan

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


    async def _on_llm_response_inner(self, event: Any, response: Any) -> None:
        await self._llm_response_pipeline._on_llm_response_inner(event, response)

    async def _background_observe_response(self, session_key: str, text: str) -> None:
        await self._llm_response_pipeline._background_observe_response(
            session_key, text
        )

    # on_llm_stream_chunk hook -- dispatch first sentence early
    async def on_llm_stream_chunk(self, event: Any, chunk: Any) -> None:
        await self._llm_response_pipeline.on_llm_stream_chunk(event, chunk)

    def _extract_first_sentence(self, text: str) -> str:
        return self._llm_response_pipeline._extract_first_sentence(text)

    async def _send_first_sentence(self, origin: str, text: str) -> None:
        await self._llm_response_pipeline._send_first_sentence(origin, text)

    # Segmented dispatch
    async def _dispatch_segmented_parts(
        self, origin: str, parts: list[dict[str, Any]], session_key: str = ""
    ) -> None:
        await self._llm_response_pipeline._dispatch_segmented_parts(
            origin, parts, session_key=session_key
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

    # Claude/hajide compat stubs (minimal implementation)
    def _state_injection_budget_for_request(
        self, session_key: str, request: Any, model_hint: str = ""
    ) -> _StateInjectionBudget:
        return self._llm_response_pipeline._state_injection_budget_for_request(
            session_key, request, model_hint
        )

    def _append_temp_text_part(
        self,
        request: Any,
        text: str,
        source: str = "",
        budget: _StateInjectionBudget | None = None,
    ) -> bool:
        return self._llm_response_pipeline._append_temp_text_part(
            request, text, source, budget
        )

    def _normalize_claude_request_payload(
        self, request: Any, budget: _StateInjectionBudget | None = None
    ) -> None:
        self._llm_response_pipeline._normalize_claude_request_payload(request, budget)

    def _prune_hajide_tools(
        self, request: Any, budget: _StateInjectionBudget | None = None
    ) -> None:
        self._llm_response_pipeline._prune_hajide_tools(request, budget)

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
    ) -> None:
        await self._state_persistence.sync_message_to_conv_mgr(session_key, role, text)

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

    def _request_model_hint_text(self, event: Any = None) -> str:
        return ""

    async def _request_model_hint_for_event(
        self, event: Any = None, request: Any = None
    ) -> str:
        return await self._get_model_hint(event)

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
        await self._state_persistence.save_sylanne_memory_state(session_key, state)

    async def _load_sylanne_memory_state(
        self, session_key: str, *, now: float = 0.0
    ) -> Any:
        return await self._state_persistence.load_sylanne_memory_state(
            session_key, now=now
        )

    async def _delete_sylanne_memory_state(self, session_key: str) -> None:
        await self._state_persistence.delete_sylanne_memory_state(session_key)

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
        pipe = self._llm_request_pipeline
        life_sim.configure(
            llm_caller=pipe._life_sim_llm_call,
            outreach_callback=pipe._life_sim_outreach,
            emotion_getter=pipe._life_sim_emotion,
            body_delta_callback=pipe._life_sim_body_delta,
            persona_getter=pipe._life_sim_persona_getter,
            countdown_callback=self._life_sim_adjust_countdown,
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
        # 恢复 LifeSim 持久化状态（修复历史「重启丢作息」缺陷）——KV 读为异步，故在此 await
        try:
            life_sim = getattr(self, "_life_simulator", None)
            if life_sim is not None and self._has_kv_api():
                saved = await self.get_kv_data("sylanne_life_sim_state", None)
                if saved and isinstance(saved, dict):
                    life_sim.from_dict(saved)
        except Exception as e:
            logger.debug(f"Sylanne life sim state restore skipped: {e}")
        try:
            self._start_life_simulator()
        except Exception as e:
            logger.error(f"Sylanne initialize: autonomy start failed: {e}", exc_info=True)

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

    async def terminate(self) -> None:
        """插件卸载/更新前的清理：停止所有后台任务、关闭 WebUI、持久化状态。"""
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
    @filter.llm_tool(name="query_agent_state")
    async def _llm_tool_query_agent_state(self, event: Any) -> Any:
        """查询 Sylanne 当前情感状态和计算脊柱摘要。"""
        return await self._public_api._llm_tool_query_agent_state(event)
