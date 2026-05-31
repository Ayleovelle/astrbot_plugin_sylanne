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
import importlib  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402
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
from sylanne_alpha.plugin_services import PluginServices  # noqa: E402
from sylanne_alpha.life_simulation import LifeSimulator  # noqa: E402
from sylanne_alpha.memory_system import MemorySystem  # noqa: E402
from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline  # noqa: E402
from sylanne_alpha.rhythm_learner import RhythmLearner  # noqa: E402
from sylanne_alpha.proactive_scheduler import ProactiveScheduler  # noqa: E402
from sylanne_alpha.session_context import SessionContext, SessionStateStore  # noqa: E402
from sylanne_alpha.social_field import SocialFieldCollector  # noqa: E402
from sylanne_alpha.llm_response_pipeline import LLMResponsePipeline  # noqa: E402
from sylanne_alpha.public_api import PublicAPI  # noqa: E402
from sylanne_alpha.state_persistence import StatePersistence  # noqa: E402
from sylanne_alpha.realtime_dispatch import RealtimeDispatch  # noqa: E402
from sylanne_alpha.background_queue import BackgroundPostQueue, BackgroundQueueState  # noqa: E402
from sylanne_alpha.webui_routes import WebUIRoutes  # noqa: E402

# 加载 WebUI dashboard HTML（从 UI/index.html）
_webui_dashboard_path = Path(_PLUGIN_DIR) / "UI" / "index.html"
if _webui_dashboard_path.exists():
    WEBUI_HTML = _webui_dashboard_path.read_text(encoding="utf-8")
else:
    WEBUI_HTML = "<html><body><h1>Sylanne Dashboard unavailable</h1></body></html>"

# AstrBot 热重载时可能重新 import main.py 但保留 sylanne_alpha 子模块，
# 强制 reload WebUI server 模块以确保监听器修复被应用
_sylanne_webui_server = importlib.reload(_sylanne_webui_server)
start_webui_background = _sylanne_webui_server.start_webui_background
stop_webui_server = _sylanne_webui_server.stop_webui_server

# ---------------------------------------------------------------------------
# 常量定义
# ---------------------------------------------------------------------------
PLUGIN_NAME = "astrbot_plugin_sylanne"

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
        self._init_session_containers()
        self._init_subsystems(context)
        self._init_webui()

    # ------------------------------------------------------------------
    # __init__ 拆分：会话容器初始化
    # ------------------------------------------------------------------

    def _init_session_containers(self) -> None:
        """Phase 1: 初始化所有 per-session 容器、BoundedDict、状态存储。"""
        # 会话管理：session_key → SylanneAlphaHost 映射
        self._hosts: BoundedDict = BoundedDict(maxsize=200)
        self._background_tasks: set[asyncio.Task] = set()
        # 流式回复相关缓冲区
        self._unfinished_replies: BoundedDict = BoundedDict(maxsize=200)
        self._stream_buffers: BoundedDict = BoundedDict(maxsize=200)
        self._stream_first_sent: BoundedDict = BoundedDict(maxsize=200)
        self._segmented_tasks: BoundedDict = BoundedDict(maxsize=200)
        # 请求/响应诊断缓存
        self._last_request_budgets: BoundedDict = BoundedDict(maxsize=200)
        self._last_understanding_closed_loop: BoundedDict = BoundedDict(maxsize=200)
        self._last_bot_expression_time: BoundedDict = BoundedDict(maxsize=200)
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
        # 三层记忆系统：session_key → MemorySystem 映射
        self._memory_systems: BoundedDict = BoundedDict(maxsize=100)
        # 对话缓冲区：用于 flush 到 L1 记忆池
        self._conversation_buffers: BoundedDict = BoundedDict(maxsize=100)
        self._meltdown_nonces: BoundedDict = BoundedDict(maxsize=50, ttl=300)
        self._last_user_texts: BoundedDict = BoundedDict(maxsize=200)
        self._last_bot_texts: BoundedDict = BoundedDict(maxsize=200)
        # 社交场收集器：群聊氛围感知
        self._social_field = SocialFieldCollector(config=self._config)
        self._conversation_input_epoch: BoundedDict = BoundedDict(maxsize=200)
        self._last_request_text: BoundedDict = BoundedDict(maxsize=200)
        self._user_message_withdrawals: BoundedDict = BoundedDict(maxsize=200)
        # 后台投递队列：异步发送主动消息/分段回复（状态集中在 BackgroundQueueState）
        self._background_queue_state = BackgroundQueueState(
            queues=BoundedDict(maxsize=200),
            active=BoundedDict(maxsize=200),
            dead_letters=BoundedDict(maxsize=200),
            latest_enqueued=BoundedDict(maxsize=200),
            last_committed=BoundedDict(maxsize=200),
            worker_state=BoundedDict(maxsize=200),
            checkpoint_tasks={},
            recovered_sessions=set(),
            sequence=BoundedDict(maxsize=200),
        )
        # 向后兼容别名：其他模块仍可通过 plugin._background_post_xxx 访问
        self._background_post_queues = self._background_queue_state.queues
        self._background_post_dead_letters = self._background_queue_state.dead_letters
        self._background_post_sequence = self._background_queue_state.sequence
        self._background_post_latest_enqueued = self._background_queue_state.latest_enqueued
        self._background_post_last_committed = self._background_queue_state.last_committed
        self._background_post_recovered_sessions = self._background_queue_state.recovered_sessions
        self._background_post_active = self._background_queue_state.active
        self._background_post_checkpoint_tasks = self._background_queue_state.checkpoint_tasks
        self._background_post_worker_state = self._background_queue_state.worker_state
        self._internal_assessor_llm_inflight: int = 0
        self._pending_outreach_context: BoundedDict = BoundedDict(maxsize=50)
        self._amnesia_sessions: set[str] = set()
        self._proactive_candidate_sessions: BoundedDict = BoundedDict(maxsize=100)
        self._proactive_scheduler_task: asyncio.Task | None = None
        self._proactive_scheduler_locks: dict[str, asyncio.Lock] = {}
        self._last_user_message_time: BoundedDict = BoundedDict(maxsize=200)
        self._sylanne_memory_cache: BoundedDict = BoundedDict(maxsize=200)
        self._conversation_pending_response_epochs: BoundedDict = BoundedDict(
            maxsize=200
        )
        self._group_atmosphere_injection_snapshot_cache: BoundedDict = BoundedDict(
            maxsize=200
        )
        self._realtime_ordinary_history_backfills: BoundedDict = BoundedDict(
            maxsize=200
        )
        self._realtime_chat_active_dispatches: BoundedDict = BoundedDict(maxsize=200)
        self._session_locks: dict[str, asyncio.Lock] = {}
        # 集中式可变状态容器：所有 per-session 可变状态的单一来源
        self._session_state = SessionStateStore(
            hosts=self._hosts,
            memory_systems=self._memory_systems,
            conversation_buffers=self._conversation_buffers,
            stream_buffers=self._stream_buffers,
            stream_first_sent=self._stream_first_sent,
            unfinished_replies=self._unfinished_replies,
            segmented_tasks=self._segmented_tasks,
            background_tasks=self._background_tasks,
            last_bot_texts=self._last_bot_texts,
            last_user_texts=self._last_user_texts,
            last_bot_expression_time=self._last_bot_expression_time,
            amnesia_sessions=self._amnesia_sessions,
            proactive_candidate_sessions=self._proactive_candidate_sessions,
            offline_buffers={},
            session_locks=self._session_locks,
            last_understanding_closed_loop=self._last_understanding_closed_loop,
        )

    # ------------------------------------------------------------------
    # __init__ 拆分：子系统初始化
    # ------------------------------------------------------------------

    def _init_subsystems(self, context: Any) -> None:
        """Phase 2: 构建 PluginServices 容器，初始化所有子系统对象。"""
        # 构建只读服务容器，供所有子模块共享
        self._plugin_services = PluginServices(
            config=self._config,
            logger=self.logger,
            context=self.context,
            rhythm_learner=self._rhythm_learner,
            social_field=self._social_field,
            put_kv_data=self.put_kv_data if hasattr(self, "put_kv_data") else None,
            get_kv_data=self.get_kv_data if hasattr(self, "get_kv_data") else None,
            delete_kv_data=self.delete_kv_data if hasattr(self, "delete_kv_data") else None,
            session_key_fn=self._session_key,
            host_fn=self._host,
            schedule_buffer_persist_fn=self._schedule_buffer_persist,
            has_conversation_manager_fn=self._has_conversation_manager,
            sync_message_to_conv_mgr_fn=self._sync_message_to_conv_mgr,
            observe_response_fn=self.observe_response,
            observed_now_fn=self._observed_now,
            assess_emotion_fn=self._assess_emotion,
            save_state_fn=self._save_state,
            max_hosts=self._MAX_HOSTS,
        )
        # 子系统初始化：各子系统持有 self 引用，通过委托模式分工
        _svc = self._plugin_services
        self._session_ctx = SessionContext(self, services=_svc, session_state=self._session_state)
        self._state_persistence = StatePersistence(self, services=_svc)
        _svc.state_persistence = self._state_persistence
        self._realtime_dispatch = RealtimeDispatch(self, services=_svc)
        self._background_queue = BackgroundPostQueue(
            self,
            services=_svc,
            state=self._background_queue_state,
            observed_now_cb=self._observed_now,
        )
        self._webui_routes = WebUIRoutes(self, services=_svc)
        self._memory_system = self._memory_system_for_session("default")
        # 异步评估器：调用 LLM 评估用户文本的情感维度
        self._async_assessor = AsyncAssessor(config=self._config)
        self._llm_response_pipeline = LLMResponsePipeline(self, services=_svc, session_state=self._session_state)
        self._llm_request_pipeline = LLMRequestPipeline(self, services=_svc, session_state=self._session_state)
        self._public_api = PublicAPI(self, services=_svc, session_state=self._session_state)
        # 主动发言调度器：基于身体需求和节律决定是否主动发言
        self._proactive_scheduler = ProactiveScheduler(self, services=_svc)
        self._register_web_apis(context)

        # AstrBot ConversationManager / PersonaManager 集成
        self._conv_mgr = self._state_persistence.init_conversation_manager()
        self._persona_mgr = self._state_persistence.init_persona_manager()

        self._state_persistence.load_config_defaults()

    # ------------------------------------------------------------------
    # __init__ 拆分：WebUI 生命周期
    # ------------------------------------------------------------------

    def _init_webui(self) -> None:
        """Phase 3: WebUI 生命周期管理——杀旧监听器、启动新服务。"""
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
        _svc = self._plugin_services
        self._webui_lifecycle = _sylanne_webui_server.WebUILifecycle(self, services=_svc)
        self._webui_lifecycle.publish_active_plugin()
        self._webui_lifecycle.start_if_enabled()
        self._webui_lifecycle.schedule_listener_takeover()

    # ------------------------------------------------------------------
    # Declarative route table: (sub_path, handler_name, methods, description)
    #   handler_name is resolved via getattr on self first, then self._webui_routes.
    # ------------------------------------------------------------------
    _WEB_API_ROUTES: list[tuple[str, str, list[str], str]] = [
        # Core plugin routes (handlers on self)
        ("observatory-status", "_observatory_route_handler", ["GET"], "Sylanne observatory readonly status"),
        ("memory-settings", "_memory_settings_get_handler", ["GET"], "Sylanne memory settings page data"),
        ("memory-settings", "_memory_settings_post_handler", ["POST"], "Update Sylanne memory settings"),
        ("lineage-observatory", "_lineage_observatory_handler", ["GET"], "Sylanne lineage observatory readonly"),
        # WebUI routes (handlers on self._webui_routes)
        ("webui", "page_handler", ["GET"], "Sylanne page_handler"),
        ("api/state", "state_handler", ["GET"], "Sylanne state_handler"),
        ("api/settings", "settings_get_handler", ["GET"], "Sylanne settings_get_handler"),
        ("api/settings", "settings_post_handler", ["POST"], "Sylanne settings_post_handler"),
        ("api/computation_logs", "computation_logs_handler", ["GET"], "Sylanne computation_logs_handler"),
        ("api/memory_pools", "memory_pools_handler", ["GET"], "Sylanne memory_pools_handler"),
        ("api/memory_meltdown", "memory_meltdown_handler", ["POST"], "Sylanne memory_meltdown_handler"),
        ("api/meltdown_nonce", "meltdown_nonce_handler", ["GET"], "Sylanne meltdown_nonce_handler"),
        ("api/memory_sink", "memory_sink_handler", ["GET"], "Sylanne memory_sink_handler"),
        ("api/memory_consolidate", "memory_consolidate_handler", ["POST"], "Sylanne memory_consolidate_handler"),
        ("api/webui_probe", "probe_handler", ["GET"], "Sylanne probe_handler"),
        ("assets/logo.png", "logo_handler", ["GET"], "Sylanne logo_handler"),
        ("logo.png", "logo_handler", ["GET"], "Sylanne logo_handler"),
        ("dashboard", "dashboard_handler", ["GET"], "Sylanne dashboard_handler"),
        ("api/config_presets", "config_presets_handler", ["GET"], "Sylanne config_presets_handler"),
        ("api/export_data", "export_data_handler", ["GET"], "Sylanne export_data_handler"),
        ("api/purge_data", "purge_data_handler", ["DELETE"], "Sylanne purge_data_handler"),
        ("health", "health_handler", ["GET"], "Sylanne health_handler"),
        ("api/error_stats", "error_stats_handler", ["GET"], "Sylanne error_stats_handler"),
        ("api/config_export", "config_export_handler", ["GET"], "Sylanne config_export_handler"),
        ("api/config_import", "config_import_handler", ["POST"], "Sylanne config_import_handler"),
        ("api/widget-state", "widget_state_handler", ["GET"], "Sylanne widget_state_handler"),
    ]

    def _register_web_apis(self, context: Any) -> None:
        """向 AstrBot 注册所有 WebUI HTTP 路由（基于 _WEB_API_ROUTES 声明式路由表）。"""
        if not hasattr(context, "register_web_api"):
            return
        for sub_path, handler_name, methods, desc in self._WEB_API_ROUTES:
            path = f"/{PLUGIN_NAME}/{sub_path}"
            handler = getattr(self, handler_name, None) or getattr(self._webui_routes, handler_name, None)
            if handler is None:
                logger.warning(
                    "WebUI route %s skipped: handler '%s' not found"
                    " — possible version mismatch",
                    path, handler_name,
                )
                continue
            context.register_web_api(path, handler, methods, desc)

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

    # Host management
    _MAX_HOSTS = 50
    _shared_encoder = None

    def _host(self, session_key: str) -> SylanneAlphaHost:
        return self._session_ctx.host(session_key)

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
        self._hosts[session_key] = SylanneAlphaHost(
            root=root, session_key=session_key, legacy=legacy
        )
        return self._hosts[session_key].snapshot()

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
        if self._state_persistence.has_kv_api():
            try:
                await self.put_kv_data(
                    self._state_persistence.kernel_kv_key(session_key), host.kernel.snapshot()
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
            self._last_user_message_time[session_key] = now
            # 喂给节奏学习器（记录 tempo，不受亲密度门控）
            self._rhythm_learner._record_tempo(session_key, now)
        except Exception:
            pass

    # on_llm_request 钩子：在 LLM 请求发出前注入情感状态上下文
    @filter.on_llm_request(desc="注入 Sylanne 情感计算上下文到 LLM prompt")
    async def on_llm_request(self, event: Any, request: Any) -> None:
        try:
            await self._llm_request_pipeline._on_llm_request_inner(event, request)
        except Exception as e:
            logger.error(f"Sylanne on_llm_request error: {e}", exc_info=True)
            return

    def _session_lock(self, session_key: str) -> asyncio.Lock:
        return self._session_ctx.session_lock(session_key)

    def _schedule_buffer_persist(self, session_key: str) -> None:
        self._state_persistence.schedule_buffer_persist(session_key)

    async def _trigger_consolidation(self, session_key: str) -> None:
        """手动触发一次 consolidation 评估（WebUI 按钮调用）。"""
        mem_sys = self._memory_system_for_session(session_key)
        if not mem_sys or not list(mem_sys._l1):
            return
        try:
            await self._llm_request_pipeline._run_consolidation(session_key, mem_sys)
        except Exception as e:
            logger.warning(f"Manual consolidation failed: {e}")

    # on_llm_response 钩子：在 LLM 回复后提取信号、更新状态、触发分段回复
    @filter.on_llm_response(desc="处理 LLM 回复，更新情感状态和记忆")
    async def on_llm_response(self, event: Any, response: Any) -> None:
        try:
            await self._llm_response_pipeline._on_llm_response_inner(event, response)
        except Exception as e:
            logger.error(f"Sylanne on_llm_response error: {e}", exc_info=True)
            return

    # on_llm_stream_chunk hook -- dispatch first sentence early
    async def on_llm_stream_chunk(self, event: Any, chunk: Any) -> None:
        await self._llm_response_pipeline.on_llm_stream_chunk(event, chunk)

    def _extract_first_sentence(self, text: str) -> str:
        return self._llm_response_pipeline._extract_first_sentence(text)

    async def _send_first_sentence(self, origin: str, text: str) -> None:
        await self._llm_response_pipeline._send_first_sentence(origin, text)

    # Memory prompt fragment
    def _memory_prompt_fragment(self, payload: dict[str, Any]) -> str:
        return self._llm_response_pipeline._memory_prompt_fragment(payload)

    def _append_request_prompt_fragment(self, request: Any, fragment: str) -> None:
        self._llm_response_pipeline._append_request_prompt_fragment(request, fragment)

    # Time context
    def _time_context_fragment(self, session_key: str) -> str:
        return self._llm_response_pipeline._time_context_fragment(session_key)

    def _event_time(self, now: float = 0.0) -> dict[str, Any]:
        return self._llm_response_pipeline._event_time(now)

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


    def _has_conversation_manager(self) -> bool:
        return self._state_persistence.has_conversation_manager()

    async def _sync_message_to_conv_mgr(
        self, session_key: str, role: str, text: str
    ) -> None:
        await self._state_persistence.sync_message_to_conv_mgr(session_key, role, text)

    def _has_persona_manager(self) -> bool:
        return self._state_persistence.has_persona_manager()

    def _sync_personality_to_persona_mgr(self, session_key: str) -> None:
        self._state_persistence.sync_personality_to_persona_mgr(session_key)

    async def _persist_kernel(self, session_key: str, host: SylanneAlphaHost) -> None:
        await self._state_persistence.persist_kernel(session_key, host)

    async def _load_state(
        self, session_key: str, persona_profile: Any = None, *, now: float = 0.0
    ) -> Any:
        return await self._state_persistence.load_state(
            session_key, persona_profile=persona_profile, now=now
        )

    async def _save_state(self, session_key: str, state: Any = None) -> None:
        await self._state_persistence.save_state(session_key, state)

    async def _delete_state(self, session_key: str) -> None:
        await self._state_persistence.delete_state(session_key)

    async def _delete_humanlike_state(self, session_key: str) -> None:
        await self._state_persistence.delete_humanlike_state(session_key)

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

    def _resolve_public_session_key(
        self, event: Any = None, *, request: Any = None, session_key: str = ""
    ) -> str:
        return self._session_ctx.resolve_public_session_key(
            event, request=request, session_key=session_key
        )

    def _record_conversation_pending_response_epoch(
        self, session_key: str, now: float = 0.0
    ) -> None:
        self._conversation_pending_response_epochs[session_key] = now or time.time()

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
        epochs = self._conversation_pending_response_epochs
        return epochs.pop(session_key, 0.0)

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

    async def _save_background_post_checkpoint(self, session_key: str) -> None:
        await self._background_queue.save_checkpoint(session_key)

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
    async def terminate(self) -> None:
        """插件卸载/更新前的清理：停止所有后台任务、关闭 WebUI、持久化状态。"""
        # 收集所有需要取消的任务
        tasks_to_cancel: list = []
        for task in list(self._background_tasks):
            if not task.done():
                task.cancel()
                tasks_to_cancel.append(task)
        self._background_tasks.clear()
        for task in list(self._background_post_checkpoint_tasks.values()):
            if not task.done():
                task.cancel()
                tasks_to_cancel.append(task)
        self._background_post_checkpoint_tasks.clear()
        sched_task = getattr(self, "_proactive_scheduler_task", None)
        if sched_task and not sched_task.done():
            sched_task.cancel()
            tasks_to_cancel.append(sched_task)
        # 等待所有取消的任务完成（带超时保护）
        if tasks_to_cancel:
            await asyncio.wait(tasks_to_cancel, timeout=10)
        # 停止生命模拟器
        if hasattr(self._life_simulator, "stop"):
            self._life_simulator.stop()
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

    # LLM Tool: query_agent_state
    @filter.llm_tool(name="query_agent_state")
    async def _llm_tool_query_agent_state(self, event: Any) -> Any:
        """查询 Sylanne 当前情感状态和计算脊柱摘要。"""
        return await self._public_api._llm_tool_query_agent_state(event)
