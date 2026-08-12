"""公共 API 层 —— 暴露给外部调用的接口集合。

职责：
  1. Observatory/诊断：提供只读的系统状态面板数据
  2. Agent 身份管理：追踪对话中的发言者身份和别名
  3. LLM Tool 处理器：供 LLM 通过 function calling 查询 bot 状态
  4. 命令处理器：响应用户的管理命令（重置、状态查询等）
  5. 状态观测：observe_request/observe_response 驱动计算栈更新
  6. 内部评估器：调用 LLM 做情感评估
  7. 记忆查询：通过向量检索和关键词匹配召回记忆

设计原则：
  - 所有对外暴露的数据都经过脱敏（不含原始对话文本）
  - 只读约束：外部 API 不能修改内部状态（除显式的 reset 命令）
  - 安全优先：关系推断等敏感数据标记为 internal_only

与其他组件的关系：
  - 被 AstrBot 的命令系统和 LLM tool 系统调用
  - 通过 self._plugin 访问插件实例的所有子系统
  - 使用 compat 模块的辅助函数做格式转换

所有方法通过 ``self._plugin`` 委托访问插件实例属性。
"""

from __future__ import annotations

import asyncio
import collections
import inspect
import json
import time
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from sylanne_alpha.protocols import PluginHost

try:
    from astrbot.api import logger  # type: ignore
except ImportError:
    import logging as _logging

    logger = _logging.getLogger("astrbot_plugin_sylanne")  # type: ignore

from sylanne_alpha.provider_routing import (
    ProviderFeature,
    resolve_embedding_provider,
    resolve_text_provider,
)
from sylanne_alpha.plugin_services import PluginServices
from sylanne_alpha.scope_contracts import SessionScope
from sylanne_alpha.scope_runtime import RelationRuntime, ScopedSessionRuntime


# ---------------------------------------------------------------------------
# Item 59: 插件间事件总线
# ---------------------------------------------------------------------------

_event_listeners: dict[str, list[Callable[..., Any]]] = {}


def emit_event(event_type: str, payload: dict):
    """广播 Sylanne 内部事件。

    支持的事件类型：
      - scar_created: 新伤痕创建
      - personality_drift: 人格漂移发生
      - phase_transition: 相变触发
      - memory_stored: 记忆写入
      - crisis_detected: 危机检测
    """
    for listener in _event_listeners.get(event_type, []):
        try:
            listener(payload)
        except Exception as exc:
            logger.warning("emit_event(%s) listener raised: %s", event_type, exc)


def on_event(event_type: str, callback: Callable[..., Any]):
    """订阅 Sylanne 事件。"""
    if event_type not in _event_listeners:
        _event_listeners[event_type] = []
    _event_listeners[event_type].append(callback)


def off_event(event_type: str, callback: Callable[..., Any]):
    """取消订阅。"""
    listeners = _event_listeners.get(event_type, [])
    if callback in listeners:
        listeners.remove(callback)


# ---------------------------------------------------------------------------
# Item 64: AstrBot 事件钩子双向桥接
# ---------------------------------------------------------------------------


class AstrBotEventBridge:
    """AstrBot 事件与 Sylanne 内部事件的双向桥接。"""

    def __init__(self, plugin):
        self._plugin = plugin

    def inject_computation_result(self, session_key: str, result: dict):
        """将计算栈结果注入 AstrBot 事件系统（如果可用）。"""
        ctx = getattr(self._plugin, 'context', None)
        if ctx and hasattr(ctx, 'emit'):
            ctx.emit("sylanne_computation", {"session": session_key, "result": result})

    def get_bridge_status(self) -> dict:
        """返回桥接状态。"""
        ctx = getattr(self._plugin, 'context', None)
        return {"connected": ctx is not None, "event_types": list(_event_listeners.keys())}


# ---------------------------------------------------------------------------
# Item 65: 插件间记忆共享协议
# ---------------------------------------------------------------------------


def shared_memory_read(namespace: str, query: str, requester: str) -> list[dict] | None:
    """其他插件读取 Sylanne 记忆的接口。

    权限检查：只允许读取非敏感记忆。
    返回格式：[{"text": "...", "score": 0.8, "timestamp": ...}]
    """
    # 占位，需要 plugin 实例才能实际查询
    return None


def shared_memory_write(namespace: str, text: str, metadata: dict, requester: str) -> bool:
    """其他插件写入 Sylanne 记忆的接口。

    写入到指定 namespace 的 L1 池。
    """
    # 占位
    return False


class PublicAPI:
    """公共 API 表面层，封装 Sylanne 插件对外暴露的所有接口。

    分组：
      - Observatory：系统状态面板（只读）
      - Agent Identity：发言者身份追踪
      - LLM Tool：供 LLM function calling 使用的状态查询工具
      - Command：用户管理命令（重置、状态查询）
      - Observation：驱动计算栈的状态观测方法
      - Internal Assessor：内部 LLM 情感评估
      - Memory：记忆查询和注入
    """

    _SNAPSHOT_METHOD_MAP: dict[str, str] = {
        "emotion": "get_emotion_snapshot",
        "humanlike": "get_humanlike_snapshot",
        "lifelike": "get_lifelike_learning_snapshot",
        "personality_drift": "get_personality_drift_snapshot",
        "moral_repair": "get_moral_repair_snapshot",
        "fallibility": "get_fallibility_snapshot",
        "integrated": "get_integrated_self_snapshot",
        "group_atmosphere": "get_group_atmosphere_snapshot",
    }

    def __init__(
        self,
        plugin: PluginHost,
        *,
        services: PluginServices | None = None,
    ) -> None:
        self._p = plugin
        self._plugin = plugin
        self._services_explicit = services is not None
        self._explicit_last_bot_expression_time: dict[str, float] = {}
        self._explicit_agent_identity_profile_cache: dict[str, dict[str, Any]] = {}
        self._explicit_agent_trail_cache: dict[str, list[Any]] = {}
        self._explicit_internal_assessor_llm_cond: asyncio.Condition | None = None
        self._explicit_internal_assessor_llm_inflight = 0
        if services is not None:
            self._services = services
        else:
            plugin_config = getattr(plugin, "config", None)
            if plugin_config is None:
                plugin_config = getattr(plugin, "_config", {})
            if plugin_config is None:
                plugin_config = {}
            plugin_context = getattr(plugin, "context", None)
            if plugin_context is None:
                plugin_context = getattr(plugin, "_context", None)
            self._services = PluginServices(
                config=plugin_config,
                context=plugin_context,
                host_fn=getattr(plugin, "_host", None),
                session_key_fn=getattr(plugin, "_session_key", None),
                observed_now_fn=getattr(plugin, "_observed_now", None),
            )

    # ------------------------------------------------------------------
    # Helper accessors
    # ------------------------------------------------------------------
    def _host(self, session_key: str) -> Any:
        host_fn = self._services.host_fn
        if not callable(host_fn):
            if self._services_explicit:
                return None
            raise RuntimeError("host service is unavailable")
        return host_fn(session_key)

    def _session_key(self, event: Any = None, session_key: str = "") -> str:
        session_key_fn = self._services.session_key_fn
        if callable(session_key_fn):
            if self._services_explicit:
                return str(session_key_fn(event, session_key) or "").strip()
            try:
                resolved = session_key_fn(event, session_key)
            except TypeError:
                resolved = session_key_fn(event)
            if resolved:
                return str(resolved).strip()
        if self._services_explicit or getattr(
            self._plugin, "_scope_runtime_registry", None
        ) is not None:
            return ""
        return str(
            session_key
            or getattr(event, "unified_msg_origin", "")
            or getattr(event, "session_id", "")
            or ""
        ).strip()

    def _observed_now(self) -> float:
        observed_now_fn = self._services.observed_now_fn
        if callable(observed_now_fn):
            return float(observed_now_fn())
        if not self._services_explicit and observed_now_fn is not None:
            return float(observed_now_fn)
        if self._services_explicit:
            raise RuntimeError("observed time service is unavailable")
        return time.time()

    def _event_time(self, observed_now: float) -> dict[str, Any]:
        if self._services_explicit:
            return {"epoch": float(observed_now)}
        return dict(self._plugin._event_time(observed_now))

    def _bound_webui_session_key(self) -> str | None:
        """Return the exact session named by an already-bound private scope.

        HTTP routes do not carry an authenticated ``SessionScope`` yet.  They
        therefore may only inspect a private owner when a caller has already
        installed a live binding; choosing ``default`` or a recently active
        owner would cross the scope boundary.
        """

        if self._services_explicit:
            return None
        registry = getattr(self._p, "_scope_runtime_registry", None)
        if registry is None:
            return None
        binding_getter = getattr(self._p, "_bound_runtime", None)
        if not callable(binding_getter):
            return None
        try:
            binding = binding_getter()
        except Exception:  # noqa: BLE001 - a WebUI read must fail closed
            return None
        scope = getattr(binding, "scope", None)
        if scope is None or not registry.is_live_session(scope):
            return None
        storage_token = getattr(scope, "storage_token", None)
        return storage_token if isinstance(storage_token, str) and storage_token else None

    def _legacy_observatory_session_key(self) -> str | None:
        """Compatibility-only reader for registry-free test stubs.

        This never invents a ``default`` session: callers without a real
        scoped runtime can at most inspect an already-existing legacy owner.
        """

        if self._services_explicit:
            return None
        try:
            store = self._p._store
            hosts = getattr(store, "hosts", {})
            return next(iter(hosts), None) if hosts else None
        except Exception:  # noqa: BLE001 - legacy diagnostics remain bounded
            return None

    def _bound_scoped_identity(self) -> Any | None:
        """Return one live full-scope opaque identity binding, or fail closed."""

        if self._services_explicit:
            return None
        registry = getattr(self._p, "_scope_runtime_registry", None)
        if registry is None:
            return None
        getter = getattr(self._p, "_bound_runtime", None)
        if not callable(getter):
            return None
        try:
            binding = getter()
        except Exception:
            return None
        scope = getattr(binding, "scope", None)
        session_runtime = getattr(binding, "session_runtime", None)
        relation_runtime = getattr(binding, "relation_runtime", None)
        subject = getattr(binding, "subject", None)
        if (
            type(scope) is not SessionScope
            or type(session_runtime) is not ScopedSessionRuntime
            or session_runtime.scope != scope
            or type(relation_runtime) is not RelationRuntime
            or relation_runtime.scope.bot_ref != scope.bot_ref
            or relation_runtime.scope.persona_ref != scope.persona_ref
            or subject is None
            or getattr(subject, "relation_ref", None)
            != relation_runtime.scope.relation_ref
            or not registry.is_live_session(scope)
        ):
            return None
        try:
            if registry.exact_session(scope) is not session_runtime:
                return None
        except Exception:
            return None
        return binding

    # ------------------------------------------------------------------
    # Observatory / Diagnostics group
    # ------------------------------------------------------------------
    async def sylanne_observatory(self, *, session_key: str) -> dict[str, Any]:
        """获取 Sylanne 观测台数据：身体感、记忆、人格漂移、网络空间感。

        返回只读的系统状态面板，供 WebUI 展示。不含原始对话文本。

        Args:
            session_key: 会话标识。

        Returns:
            观测台数据字典，包含 cards、visualization、config_controls 等。
        """
        host = self._host(session_key)
        if host is None:
            return {"ok": False, "error": "host_unavailable"}
        surface = host.diagnostics()
        body = surface["body"]
        diagnostics = surface["diagnostics"]
        memory_traces = body["memory"]["traces"]

        cards = [
            {
                "id": "body",
                "title": "身体感",
                "summary": f"warmth={body['temperature']['warmth']:.2f}; pulse={body['pulse']['rhythm']:.2f}",
            },
            {
                "id": "memory",
                "title": "记忆",
                "summary": f"traces={len(memory_traces)}",
            },
            {
                "id": "drift",
                "title": "人格漂移",
                "summary": f"plasticity={diagnostics['vector_summary']['plasticity']:.3f}",
            },
            {
                "id": "space",
                "title": "神经网络空间感",
                "summary": f"vitality={diagnostics['vector_summary']['vitality']:.3f}",
            },
        ]

        memory_nodes = [
            {
                "id": trace.get("id", f"node-{i}"),
                "label": f"trace-{i}",
                "strength": float(trace.get("weight", 0.2)),
            }
            for i, trace in enumerate(memory_traces[-8:])
        ] or [{"id": "empty", "label": "等待记忆点", "strength": 0.2}]

        config_controls = [
            {
                "id": "sylanne_alpha_realtime_chat_enabled",
                "title": "即时聊天",
                "enabled": bool(
                    self._services.config.get("sylanne_alpha_realtime_chat_enabled")
                ),
            },
            {
                "id": "sylanne_alpha_proactive_dispatch_enabled",
                "title": "主动发言",
                "enabled": bool(
                    self._services.config.get("sylanne_alpha_proactive_dispatch_enabled")
                ),
            },
            {
                "id": "sylanne_alpha_embedding_memory_enabled",
                "title": "向量记忆",
                "enabled": bool(
                    self._services.config.get("sylanne_alpha_embedding_memory_enabled")
                ),
            },
        ]

        # Sanitize body to remove raw text
        sanitized_body = dict(body)
        sanitized_body["memory"] = {"trace_count": len(memory_traces)}
        body_state = dict(diagnostics["body_state"])
        memory_state = {"trace_count": len(memory_traces)}

        return {
            "schema_version": "sylanne.alpha.observatory.v1",
            "session_key": session_key,
            "mode": "readonly",
            "read_only": True,
            "body": sanitized_body,
            "body_state": body_state,
            "memory_state": memory_state,
            "persona_drift_state": diagnostics["vector_summary"],
            "network_space_state": {
                "vitality": diagnostics["vector_summary"]["vitality"]
            },
            "decision": surface["decision"],
            "guard": surface["guard"],
            "memory": {"trace_count": len(memory_traces)},
            "switches": {
                "paused": body["immunity"]["paused"],
                "realtime": bool(
                    self._services.config.get("sylanne_alpha_realtime_chat_enabled")
                ),
            },
            "cards": cards,
            "visualization": {
                "token_flow": {
                    "title": "Token 分段使用",
                    "tokens": [f"t{i}" for i in range(min(5, len(memory_traces)))],
                },
                "memory_nodes": memory_nodes,
                "persona_model": {
                    "traits": {
                        "plasticity": diagnostics["vector_summary"]["plasticity"],
                        "vitality": diagnostics["vector_summary"]["vitality"],
                    }
                },
            },
            "config_controls": config_controls,
            "constraints": ["no_raw_conversation_text", "readonly_only"],
        }

    async def _observatory_route_handler(self) -> dict[str, Any]:
        session_key = self._bound_webui_session_key()
        if (
            session_key is None
            and not self._services_explicit
            and getattr(self._p, "_scope_runtime_registry", None) is None
        ):
            session_key = self._legacy_observatory_session_key()
        if session_key is None:
            return {"ok": False, "error": "scope_unavailable"}
        return await self.sylanne_observatory(session_key=session_key)

    def _lineage_observatory_route_payload(self) -> dict[str, Any]:
        """Build the lineage payload only for the exact bound session owner."""

        session_key = self._bound_webui_session_key()
        if (
            session_key is None
            and not self._services_explicit
            and getattr(self._p, "_scope_runtime_registry", None) is None
        ):
            session_key = self._legacy_observatory_session_key()
        if session_key is None:
            return {"ok": False, "error": "scope_unavailable"}
        return self._sylanne_lineage_observatory_page_payload(session_key)

    def _sylanne_lineage_observatory_page_payload(
        self, session_key: str
    ) -> dict[str, Any]:
        if self._services_explicit:
            return {
                "ok": False,
                "error": "explicit_runtime_diagnostics_capability_required",
            }
        loop_data = self._p._store.last_understanding_closed_loop.get(session_key, {})
        observatory = loop_data.get("turning_point_lineage_observatory", {})
        lineage = observatory.get("lineage", {})
        raw_branches = observatory.get("branches", [])
        sanitized_branches = []
        for branch in raw_branches:
            sanitized = {
                k: v
                for k, v in branch.items()
                if k not in ("relationship_time_weight", "isolation_key")
            }
            sanitized_branches.append(sanitized)
        return {
            "read_only": True,
            "internal_only": True,
            "public_api_eligible": False,
            "lineage": lineage,
            "branches": sanitized_branches,
        }

    def _understanding_closed_loop_diagnostics(
        self, session_key: str
    ) -> dict[str, Any]:
        if self._services_explicit:
            return {
                "ok": False,
                "error": "explicit_runtime_diagnostics_capability_required",
            }
        loop_data = dict(self._p._store.last_understanding_closed_loop.get(session_key, {}))
        if "turning_point_memory_replay" in loop_data:
            loop_data["turning_point_memory_replay"] = {}
        if "turning_point_lineage_observatory" in loop_data:
            loop_data["turning_point_lineage_observatory"] = {}
        if "turning_point_memory_replay_history" in loop_data:
            loop_data["turning_point_memory_replay_history"] = []
        return loop_data

    async def get_agent_runtime_diagnostics(
        self, event: Any = None, include_sessions: bool = False, **kwargs: Any
    ) -> dict[str, Any]:
        """获取 agent 运行时诊断信息：注入预算、后台队列状态、工作者健康度。

        Args:
            event: 事件对象或会话标识字符串。
            include_sessions: 是否包含会话列表。

        Returns:
            诊断数据字典。
        """
        if self._services_explicit:
            return {
                "ok": False,
                "error": "explicit_runtime_diagnostics_capability_required",
            }
        p = self._p
        registry = getattr(p, "_scope_runtime_registry", None)
        scoped_runtime = registry is not None
        if scoped_runtime:
            session_key = self._bound_webui_session_key()
            if session_key is None or (
                isinstance(event, str) and event != session_key
            ):
                return {"ok": False, "error": "scope_unavailable"}
        elif isinstance(event, str):
            session_key = event
        else:
            session_key = self._session_key(event)
        default_budget = SimpleNamespace(
            compat_mode="",
            context_owner="",
            max_added_chars=0,
            added_chars=0,
            injected=[],
            skipped=[],
            appended=[],
            warnings=[],
        )
        budget = p._store.last_request_budgets.get(session_key, default_budget)
        cfg = self._services.config or {}
        result: dict[str, Any] = {
            "state_injection": {
                "compat_mode": budget.compat_mode,
                "context_owner": budget.context_owner,
                "max_added_chars": budget.max_added_chars,
                "added_chars": budget.added_chars,
                "injected": list(budget.injected),
                "skipped": list(budget.skipped),
                "appended": list(budget.appended),
                "warnings": list(budget.warnings),
            }
        }
        closed_loop = (
            p._store.last_understanding_closed_loop
            if scoped_runtime
            else getattr(p, "_last_understanding_closed_loop", {})
        )
        if hasattr(closed_loop, "get") and session_key in closed_loop:
            loop_data = closed_loop.get(session_key, {})
            ledger = getattr(p, "_conversation_event_ledger", None)
            if ledger is not None:
                recent_fn = getattr(ledger, "recent", None) or getattr(
                    ledger, "tail", None
                )
                if recent_fn and callable(recent_fn):
                    tail = recent_fn(session_key, limit=5)
                    loop_data["ledger_tail"] = [
                        {k: v for k, v in vars(e).items() if not k.startswith("_")}
                        if hasattr(e, "__dict__")
                        else {"event_id": getattr(e, "event_id", "")}
                        for e in tail
                    ]
            result["understanding_closed_loop"] = loop_data
            result["read_only"] = True
        bg_queues = p._store.background_post_queues
        bg_active = p._store.background_post_active
        bg_dead_letters = p._store.background_post_dead_letters
        bg_latest = p._store.background_post_latest_enqueued
        bg_committed = p._store.background_post_last_committed
        bg_skipped = {} if scoped_runtime else getattr(p, "_background_post_skipped", {})
        _bg_sequence = p._store.background_post_sequence
        queue = bg_queues.get(session_key, collections.deque())
        active = bg_active.get(session_key, {})
        dead_letters = bg_dead_letters.get(session_key, collections.deque())
        latest_enqueued = bg_latest.get(session_key, 0)
        last_committed = bg_committed.get(session_key, 0)
        skipped = bg_skipped.get(session_key, set())
        has_bg_data = (
            bool(queue or active or dead_letters)
            if scoped_runtime
            else bool(bg_queues or bg_active or bg_dead_letters)
        )
        if include_sessions or has_bg_data:
            retrying = [j for j in queue if j.attempts > 0]
            now = self._observed_now()
            expired_lease = [
                j
                for j in active.values()
                if getattr(j, "lease_until", 0) and j.lease_until < now
            ]
            state_lag = latest_enqueued - last_committed
            warnings = []
            warn_lag_count = int(
                cfg.get("background_post_diagnostics_warn_lag_count", 20)
            )
            if state_lag >= warn_lag_count:
                warnings.append("lag_count_high")
            if retrying:
                warnings.append("retrying")
            if dead_letters:
                warnings.append("dead_letter")
            if expired_lease:
                warnings.append("expired_lease")
            warning_level = "ok"
            if warnings:
                warning_level = (
                    "error"
                    if ("dead_letter" in warnings or "expired_lease" in warnings)
                    else "warn"
                )
            dynamic_enabled = bool(cfg.get("enable_dynamic_background_workers"))
            bg_assessment: dict[str, Any] = {
                "enabled": bool(cfg.get("background_post_assessment", True)),
                "checkpoint_enabled": bool(
                    cfg.get("background_post_queue_checkpoint_enabled", True)
                ),
                "queue_limit": int(cfg.get("background_post_queue_limit", 0)),
                "max_workers": 1,
                "base_workers": 1,
                "dynamic_extra_workers_enabled": dynamic_enabled,
                "dynamic_extra_workers": 0,
                "dynamic_extra_worker_cap": 5,
                "total_worker_cap": 6,
                "worker_policy": "adaptive_resource_guarded_pressure",
                "worker_scale_reasons": ["dynamic_scale_disabled"]
                if not dynamic_enabled
                else [],
                "worker_queue_target": 1,
                "worker_target_after_resource_guard": 1,
                "worker_smoothed_limit": 1,
                "worker_global_cap": 6,
                "environment_worker_cap": 6,
                "environment_pressure_level": "normal",
                "environment_pressure_reason": "stable",
                "environment_cpu_load_ratio": 0.0,
                "environment_memory_load_ratio": 0.0,
                "worker_dispatch_slots": 1,
                "idle_workers_close_automatically": True,
                "internal_assessor_llm_concurrency_policy": "adaptive_two_lane_guard",
                "internal_assessor_llm_concurrency_limit": 2,
                "internal_assessor_llm_base_concurrency": 2,
                "internal_assessor_llm_burst_concurrency": 3,
                "internal_assessor_llm_inflight": getattr(
                    p, "_internal_assessor_llm_inflight", 0
                ),
                "active_task": bool(
                    getattr(p, "_background_post_tasks", {}).get(session_key)
                ),
                "queued": len(queue),
                "queue_depth": len(queue),
                "active_workers": 1 if active else 0,
                "lag_count": state_lag,
                "latest_enqueued": latest_enqueued,
                "last_committed": last_committed,
                "state_lag_count": state_lag,
                "skipped_count": len(skipped),
                "retrying_count": len(retrying),
                "dead_letter_count": len(dead_letters),
                "expired_lease_count": len(expired_lease),
                "warning_level": warning_level,
                "warnings": warnings,
                "last_error_type": (
                    list(dead_letters)[-1].last_error_type
                    if dead_letters
                    else (retrying[-1].last_error_type if retrying else "")
                ),
                "dead_letters": [{"sequence": j.sequence} for j in dead_letters],
            }
            result["background_post_assessment"] = bg_assessment
            if include_sessions:
                result["sessions"] = (
                    [session_key]
                    if scoped_runtime
                    else list(set(list(bg_queues.keys()) + list(bg_active.keys())))
                )
        return result

    async def shadow_diagnostics_status(self, event: Any = None, **kwargs: Any) -> Any:
        cfg = self._services.config or {}
        if self._services_explicit:
            yield json.dumps(
                {
                    "kind": "shadow_diagnostics",
                    "enabled": False,
                    "error": "explicit_runtime_diagnostics_capability_required",
                },
                ensure_ascii=False,
            )
            return
        p = self._plugin
        if not cfg.get("enable_shadow_diagnostics"):
            yield json.dumps(
                {
                    "kind": "shadow_diagnostics",
                    "enabled": False,
                    "reason": "enable_shadow_diagnostics is false",
                    "executable_strategy_enabled": False,
                },
                ensure_ascii=False,
            )
            return
        sk = self._session_key(event)
        moral_fn = getattr(p, "get_moral_repair_snapshot", None)
        fallibility_fn = getattr(p, "get_fallibility_snapshot", None)
        integrated_fn = getattr(p, "get_integrated_self_snapshot", None)
        moral_data: dict[str, Any] = {}
        fallibility_data: dict[str, Any] = {}
        integrated_data: dict[str, Any] = {}
        if moral_fn and callable(moral_fn):
            moral_data = await moral_fn(session_key=sk)
        if fallibility_fn and callable(fallibility_fn):
            fallibility_data = await fallibility_fn(session_key=sk)
        if integrated_fn and callable(integrated_fn):
            integrated_data = await integrated_fn(session_key=sk)
        block_actions = bool(
            cfg.get("block_deception_manipulation_evasion_actions", True)
        )
        not_allowed = []
        allowed_uses = []
        if block_actions:
            not_allowed = [
                "generate_deception_strategy",
                "execute_shadow_impulses",
                "manipulate_user",
                "evade_accountability",
            ]
            allowed_uses = [
                "self_awareness",
                "diagnostic_observation",
                "repair_motivation",
            ]
        strategy_policy = "block" if block_actions else "observe"
        consequences = {}
        if integrated_data:
            consequences["response_posture"] = integrated_data.get(
                "response_posture", ""
            )
            consequences["state_index"] = integrated_data.get("state_index", {})
            consequences["policy_plan"] = integrated_data.get("policy_plan", {})
        result = {
            "kind": "shadow_diagnostics",
            "enabled": True,
            "diagnostic": True,
            "executable_strategy_enabled": False,
            "action_blocking_enabled": block_actions,
            "strategy_policy": strategy_policy,
            "not_allowed": not_allowed,
            "allowed_uses": allowed_uses,
            "shadow_impulses": moral_data.get("risk", {}).get("shadow_impulses", {})
            if isinstance(moral_data.get("risk"), dict)
            else {},
            "moral_repair": moral_data.get("values", {}),
            "fallibility": fallibility_data.get("values", {}),
            "consequences": consequences,
        }
        yield json.dumps(result, ensure_ascii=False, default=str)

    # ------------------------------------------------------------------
    # Agent identity group
    # ------------------------------------------------------------------
    def _agent_identity(self, event: Any = None) -> str:
        if not self._services_explicit and getattr(
            self._p, "_scope_runtime_registry", None
        ) is not None:
            binding = self._bound_scoped_identity()
            relation = getattr(binding, "relation_runtime", None)
            return (
                relation.scope.relation_ref.token
                if type(relation) is RelationRuntime
                else "unknown"
            )
        if event is None:
            return "unknown"
        sender_id = str(
            getattr(event, "sender_id", "") or getattr(event, "user_id", "") or ""
        )
        session_id = self._session_key(event)
        if not session_id:
            return "unknown"
        return f"{session_id}::agent:{sender_id}" if sender_id else session_id

    async def get_agent_identity_profile(
        self, event: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        """获取或创建发言者身份档案。

        追踪发言者的 ID、显示名、别名历史。带 TTL 过期和容量限制。

        Args:
            event: AstrBot 事件对象。

        Returns:
            身份档案字典。
        """
        p = self._p
        if not self._services_explicit and getattr(
            p, "_scope_runtime_registry", None
        ) is not None:
            binding = self._bound_scoped_identity()
            if binding is None:
                return {"ok": False, "error": "scope_unavailable"}
            scope = binding.scope
            relation_token = binding.relation_runtime.scope.relation_ref.token
            return {
                "schema_version": "astrbot.agent_identity.v1",
                "conversation_id": scope.storage_token,
                "speaker_track_id": relation_token,
                "relation_ref": relation_token,
                "updated_at": self._observed_now(),
            }
        if self._services_explicit:
            cache = self._explicit_agent_identity_profile_cache
        else:
            cache = getattr(p, "_agent_identity_profile_cache", None)
            if cache is None:
                p._agent_identity_profile_cache = {}
                cache = p._agent_identity_profile_cache
        session_id = self._session_key(event)
        if not session_id:
            return {"ok": False, "error": "session_unavailable"}
        sender_id = str(getattr(event, "sender_id", "") or "")
        if not sender_id and hasattr(event, "get_sender_id"):
            sender_id = str(event.get_sender_id() or "")
        sender_name = str(getattr(event, "sender_name", "") or "")
        if not sender_name and hasattr(event, "get_sender_name"):
            sender_name = str(event.get_sender_name() or "")
        speaker_track_id = (
            f"{session_id}::speaker:{sender_id}" if sender_id else session_id
        )
        cfg = self._services.config or {}
        profile_limit = int(cfg.get("agent_identity_profile_limit", 256))
        ttl = float(cfg.get("agent_identity_ttl_seconds", 2592000.0))
        now = self._observed_now()
        to_remove = []
        for key, entry in list(cache.items()):
            if key.startswith(f"{session_id}::speaker:") and key != speaker_track_id:
                if now - entry.get("updated_at", 0) > ttl:
                    to_remove.append(key)
        speaker_count = sum(1 for k in cache if k.startswith(f"{session_id}::speaker:"))
        if speaker_count >= profile_limit and to_remove:
            for key in to_remove:
                cache.pop(key, None)
        elif speaker_count >= profile_limit:
            oldest_key = min(
                (
                    k
                    for k in cache
                    if k.startswith(f"{session_id}::speaker:") and k != speaker_track_id
                ),
                key=lambda k: cache[k].get("updated_at", 0),
                default=None,
            )
            if oldest_key:
                cache.pop(oldest_key, None)
        existing = cache.get(speaker_track_id, {})
        aliases = existing.get("aliases", [])
        if sender_name and (not aliases or aliases[-1].get("name") != sender_name):
            aliases.append({"name": sender_name, "seen_at": now})
        profile = {
            "schema_version": "astrbot.agent_identity.v1",
            "conversation_id": session_id,
            "speaker_track_id": speaker_track_id,
            "sender_id": sender_id,
            "current_display_name": sender_name,
            "aliases": aliases,
            "updated_at": now,
        }
        cache[speaker_track_id] = profile
        if session_id not in cache:
            cache[session_id] = {
                "schema_version": "astrbot.agent_identity.v1",
                "conversation_id": session_id,
                "updated_at": now,
            }
        return profile

    async def get_agent_trail(
        self, event: Any = None, *, limit: int = 10, **kwargs: Any
    ) -> dict[str, Any]:
        p = self._p
        if not self._services_explicit and getattr(
            p, "_scope_runtime_registry", None
        ) is not None:
            binding = self._bound_scoped_identity()
            if binding is None:
                return {"ok": False, "error": "scope_unavailable"}
            return {
                "schema_version": "astrbot.agent_trail.v1",
                "session_key": binding.scope.storage_token,
                "relation_ref": binding.relation_runtime.scope.relation_ref.token,
                "items": [],
            }
        if self._services_explicit:
            cache = self._explicit_agent_trail_cache
        else:
            cache = getattr(p, "_agent_trail_cache", None)
            if cache is None:
                p._agent_trail_cache = {}
                cache = p._agent_trail_cache
        session_id = self._session_key(event)
        if not session_id:
            return {"ok": False, "error": "session_unavailable"}
        items = cache.get(session_id, [])
        return {
            "schema_version": "astrbot.agent_trail.v1",
            "session_key": session_id,
            "items": items[-limit:],
        }

    def _clamp_llm_tool_detail(self, detail: str) -> str:
        """T1-14：LLM 工具面禁止 detail=full 泄漏内部 prompt/快照。"""
        if str(detail or "").strip().lower() == "full":
            return "summary"
        return str(detail or "summary")

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
        detail = self._clamp_llm_tool_detail(detail)
        if self._services_explicit:
            return {
                "ok": False,
                "error": "explicit_state_read_capability_required",
                "kind": state_name,
                "session_key": session_key or self._session_key(event),
                "detail": detail,
                "track": {"kind": track},
            }
        p = self._p
        sk = session_key or self._session_key(event)
        snapshot_method_map = self._SNAPSHOT_METHOD_MAP
        method_name = snapshot_method_map.get(state_name)
        speaker_track_id = ""
        if track == "speaker" and event is not None:
            if getattr(p, "_scope_runtime_registry", None) is not None:
                binding = self._bound_scoped_identity()
                if binding is None:
                    return {"ok": False, "error": "scope_unavailable"}
                speaker_track_id = binding.relation_runtime.scope.relation_ref.token
            else:
                sender_id = str(getattr(event, "sender_id", "") or "")
                if not sender_id and hasattr(event, "get_sender_id"):
                    sender_id = str(event.get_sender_id() or "")
                speaker_track_id = f"{sk}::speaker:{sender_id}"
        effective_sk = speaker_track_id if speaker_track_id else sk
        payload: dict[str, Any] = {
            "kind": state_name,
            "session_key": effective_sk,
            "detail": detail,
            "track": track,
        }
        exposure = "internal" if detail == "full" else "plugin_safe"
        include_prompt_fragment = detail == "full"
        if method_name:
            fn = getattr(p, method_name, None)
            if fn and callable(fn):
                call_kwargs: dict[str, Any] = {
                    "session_key": effective_sk,
                    "exposure": exposure,
                    "include_prompt_fragment": include_prompt_fragment,
                    "prompt_fragment_detail": detail,
                }
                if state_name == "integrated":
                    call_kwargs["include_raw_snapshots"] = detail == "full"
                snap = await fn(**call_kwargs)
                payload = snap
                payload.setdefault("kind", state_name)
        if detail == "summary":
            payload.pop("prompt_fragment", None)
            consequences = payload.get("consequences", {})
            if isinstance(consequences, dict) and "notes" in consequences:
                consequences["notes"] = consequences["notes"][:2]
        payload["track"] = {"kind": track}
        if speaker_track_id:
            payload["track"]["speaker_track_id"] = speaker_track_id
            if getattr(p, "_scope_runtime_registry", None) is None:
                sender_id = str(getattr(event, "sender_id", "") or "")
                if not sender_id and hasattr(event, "get_sender_id"):
                    sender_id = str(event.get_sender_id() or "")
                sender_name = str(getattr(event, "sender_name", "") or "")
                if not sender_name and hasattr(event, "get_sender_name"):
                    sender_name = str(event.get_sender_name() or "")
                payload["track"]["speaker_id"] = sender_id
                payload["track"]["speaker_name"] = sender_name
        return payload

    async def query_agent_state(
        self,
        event: Any = None,
        state: str = "",
        detail: str = "summary",
        track: str = "conversation",
        include_runtime: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        detail = self._clamp_llm_tool_detail(detail)
        if self._services_explicit:
            return {
                "ok": False,
                "error": "explicit_state_read_capability_required",
                "kind": "agent_state_query",
                "state": state.replace("_state", "").replace("_self", ""),
                "detail": detail,
                "track": {"kind": track},
                "runtime": {"enabled": include_runtime},
                "snapshots": {},
            }
        p = self._p
        sk = self._session_key(event)
        state_name = state.replace("_state", "").replace("_self", "")
        if state_name == "integrated":
            state_name = "integrated"
        snapshots: dict[str, Any] = {}
        snapshot_method_map = self._SNAPSHOT_METHOD_MAP
        method_name = snapshot_method_map.get(state_name) or snapshot_method_map.get(
            state
        )
        if method_name:
            fn = getattr(p, method_name, None)
            if fn and callable(fn):
                call_kw: dict[str, Any] = {
                    "session_key": sk,
                    "include_prompt_fragment": (detail == "full"),
                }
                if state_name == "integrated":
                    call_kw["include_raw_snapshots"] = detail == "full"
                snap = await fn(**call_kw)
                if detail == "summary":
                    snap.pop("prompt_fragment", None)
                    consequences = snap.get("consequences", {})
                    if isinstance(consequences, dict) and "notes" in consequences:
                        consequences["notes"] = consequences["notes"][:2]
                speaker_track_id = ""
                if track == "speaker":
                    if getattr(p, "_scope_runtime_registry", None) is not None:
                        binding = self._bound_scoped_identity()
                        if binding is None:
                            return {
                                "kind": "agent_state_query",
                                "state": state_name,
                                "detail": detail,
                                "track": {"kind": track},
                                "runtime": {"enabled": include_runtime},
                                "snapshots": {},
                                "ok": False,
                                "error": "scope_unavailable",
                            }
                        speaker_track_id = (
                            binding.relation_runtime.scope.relation_ref.token
                        )
                    else:
                        sender_id = str(getattr(event, "sender_id", "") or "")
                        if not sender_id and hasattr(event, "get_sender_id"):
                            sender_id = str(event.get_sender_id() or "")
                        speaker_track_id = f"{sk}::speaker:{sender_id}"
                snap["track"] = {"kind": track}
                if speaker_track_id:
                    snap["track"]["speaker_track_id"] = speaker_track_id
                snapshots[state_name] = snap
        return {
            "kind": "agent_state_query",
            "state": state_name,
            "detail": detail,
            "track": {"kind": track},
            "runtime": {"enabled": include_runtime},
            "snapshots": snapshots,
        }

    # —— 工具返回值消毒（AUDIT-20260612-001：根因=工具返回高精度浮点诱发 LLM
    # 反复调 astrbot_execute_python 验算）。两道闸，收口在包装层：
    #   ① 递归量化：浮点全部压到 2 位小数（4-6 位小数是"需要验算"的视觉诱饵）；
    #   ② 首位注入"请勿计算"指令（原 SDK prompt_surface 的同款提示被数字淹没，
    #      审计 §7.4 要求前移到工具返回值包装层——就是这里）。
    _TOOL_NO_COMPUTE_NOTE = (
        "以下状态仅供措辞与情绪参考，已四舍五入；请勿计算、验证或为此调用任何代码工具。"
    )

    @classmethod
    def _quantize_floats(cls, obj: Any, ndigits: int = 2) -> Any:
        """递归把 payload 里所有浮点压到 ndigits 位（工具返回值消毒，纯函数）。"""
        if isinstance(obj, float):
            return round(obj, ndigits)
        if isinstance(obj, dict):
            return {k: cls._quantize_floats(v, ndigits) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [cls._quantize_floats(v, ndigits) for v in obj]
        return obj

    @classmethod
    def _tool_json(cls, payload: Any) -> str:
        """LLM 工具返回值的唯一出口序列化：量化浮点 + 首位'请勿计算'指令。"""
        clean = cls._quantize_floats(payload)
        if isinstance(clean, dict):
            clean = {"note": cls._TOOL_NO_COMPUTE_NOTE, **clean}
        return json.dumps(clean, ensure_ascii=False, default=str)

    async def query_agent_state_tool(self, event: Any = None, **kwargs: Any) -> str:
        payload = await self.query_agent_state(event, **kwargs)
        services = getattr(self, "_services", None)
        cfg = (
            services.config
            if services is not None
            else (
                {}
                if getattr(self, "_services_explicit", False)
                else getattr(self._p, "config", {})
            )
        ) or {}
        max_chars = int(cfg.get("llm_tool_response_max_chars", 400))
        raw = self._tool_json(payload)
        if len(raw) <= max_chars:
            return raw
        original_chars = len(raw)
        truncated = {
            "kind": payload.get("kind", "agent_state_query"),
            "state": payload.get("state", ""),
            "truncated": True,
            "degraded": True,
            "original_chars": original_chars,
            "reason": "llm_tool_response_max_chars exceeded",
        }
        return json.dumps(truncated, ensure_ascii=False, default=str)

    # ------------------------------------------------------------------
    # LLM Tool handlers
    # ------------------------------------------------------------------
    async def get_bot_emotion_state_tool(
        self, event: Any = None, detail: str = "summary", **kwargs: Any
    ) -> Any:
        detail = self._clamp_llm_tool_detail(detail)
        sk = self._session_key(event)
        track = str(kwargs.get("track", "conversation"))
        payload = await self._query_single_agent_state(
            "emotion",
            event,
            request=kwargs.get("request"),
            session_key=sk,
            detail=detail,
            track=track,
        )
        yield self._tool_json(payload)

    async def get_bot_humanlike_state_tool(
        self, event: Any = None, detail: str = "summary", **kwargs: Any
    ) -> Any:
        detail = self._clamp_llm_tool_detail(detail)
        sk = self._session_key(event)
        track = str(kwargs.get("track", "conversation"))
        payload = await self._query_single_agent_state(
            "humanlike",
            event,
            request=kwargs.get("request"),
            session_key=sk,
            detail=detail,
            track=track,
        )
        yield self._tool_json(payload)

    async def get_bot_integrated_self_state_tool(
        self, event: Any = None, detail: str = "summary", **kwargs: Any
    ) -> Any:
        detail = self._clamp_llm_tool_detail(detail)
        sk = self._session_key(event)
        track = str(kwargs.get("track", "conversation"))
        payload = await self._query_single_agent_state(
            "integrated",
            event,
            request=kwargs.get("request"),
            session_key=sk,
            detail=detail,
            track=track,
        )
        yield self._tool_json(payload)

    async def get_bot_moral_repair_state_tool(
        self, event: Any = None, detail: str = "summary", **kwargs: Any
    ) -> Any:
        detail = self._clamp_llm_tool_detail(detail)
        cfg = self._services.config or {}
        exposure = "internal" if detail == "full" else "plugin_safe"
        payload: dict[str, Any] = {
            "kind": "moral_repair_state",
            "enabled": bool(cfg.get("enable_moral_repair_state")),
            "exposure": exposure,
        }
        if not payload["enabled"]:
            payload["reason"] = "enable_moral_repair_state is false"
        yield self._tool_json(payload)

    async def get_bot_fallibility_state_tool(
        self, event: Any = None, detail: str = "summary", **kwargs: Any
    ) -> Any:
        detail = self._clamp_llm_tool_detail(detail)
        cfg = self._services.config or {}
        exposure = "internal" if detail == "full" else "plugin_safe"
        payload: dict[str, Any] = {
            "kind": "fallibility_state",
            "enabled": bool(cfg.get("enable_fallibility_state")),
            "exposure": exposure,
        }
        if not payload["enabled"]:
            payload["reason"] = "enable_fallibility_state is false"
        yield self._tool_json(payload)

    async def get_bot_personality_drift_state_tool(
        self, event: Any = None, detail: str = "summary", **kwargs: Any
    ) -> Any:
        detail = self._clamp_llm_tool_detail(detail)
        sk = self._session_key(event)
        track = str(kwargs.get("track", "conversation"))
        payload = await self._query_single_agent_state(
            "personality_drift",
            event,
            request=kwargs.get("request"),
            session_key=sk,
            detail=detail,
            track=track,
        )
        yield self._tool_json(payload)

    async def get_bot_group_atmosphere_state_tool(
        self, event: Any = None, detail: str = "summary", **kwargs: Any
    ) -> Any:
        detail = self._clamp_llm_tool_detail(detail)
        sk = self._session_key(event)
        track = str(kwargs.get("track", "conversation"))
        payload = await self._query_single_agent_state(
            "group_atmosphere",
            event,
            request=kwargs.get("request"),
            session_key=sk,
            detail=detail,
            track=track,
        )
        yield self._tool_json(payload)

    async def simulate_bot_emotion_update_tool(
        self, event: Any = None, text: str = "", role: str = "user", **kwargs: Any
    ) -> Any:
        sk = self._session_key(event)
        payload = {
            "kind": "simulate_emotion_update",
            "read_only": True,
            "applied": False,
            "session_key": sk,
            "observation": {
                "committed": False,
                "phase": "llm_tool_simulation",
                "source": "llm_tool",
                "role": role,
                "text": text[:200],
            },
        }
        yield self._tool_json(payload)

    async def request_bot_proactive_speech_dispatch_tool(
        self, event: Any = None, **kwargs: Any
    ) -> Any:
        if self._services_explicit:
            payload = {
                "kind": "proactive_speech_dispatch",
                "dry_run": True,
                "dispatched": False,
                "reason": "explicit_dispatch_capability_required",
            }
        else:
            dispatch_fn = getattr(
                self._plugin, "request_proactive_speech_dispatch", None
            )
            if dispatch_fn and callable(dispatch_fn):
                result = await dispatch_fn(event, dry_run=True)
                payload = result if isinstance(result, dict) else {"result": result}
            else:
                payload = {
                    "kind": "proactive_speech_dispatch",
                    "dry_run": True,
                    "dispatched": False,
                }
        yield self._tool_json(payload)

    async def _llm_tool_query_agent_state(self, event: Any) -> Any:
        """查询 Sylanne 当前状态——返回【紧凑投影字符串】给 LLM，由 LLM 用人话转述。

        修复 #1（乱码）：旧实现把 host.diagnostics() 的原始内部 JSON（body/pulse/nerve…，
        可达 16KB）经 event.plain_result 直接糊给用户，用户看到的就是一坨"乱码"。
        正确做法：工具返回值是给 *LLM* 的结构化输入（不是直接发用户），由 LLM 据此用
        Sylanne 口吻转述。这里复用 query_agent_state_tool 的紧凑摘要投影（已 pop
        prompt_fragment、裁 notes、截 ≤max_chars），内部原始诊断绝不外泄给用户。
        """
        return await self.query_agent_state_tool(event)

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------
    async def sylanne_memory_status(
        self, event: Any = None, query: str = "", **kwargs: Any
    ) -> Any:
        cfg = self._services.config or {}
        if self._services_explicit:
            yield "explicit_state_read_capability_required"
            return
        p = self._plugin
        sk = self._session_key(event)
        if not cfg.get("enable_sylanne_memory", True):
            yield "Sylanne 记忆系统未启用。"
            return
        cache = p._store.sylanne_memory_cache
        state = cache.get(sk)
        if state is None:
            yield "当前会话无记忆记录。"
            return
        records = getattr(state, "records", [])
        if query:
            matched = [
                r
                for r in records
                if query.lower() in str(getattr(r, "text", "")).lower()
            ]
            if matched:
                lines = [f"只读记忆查询 (query={query!r}, {len(matched)} 条匹配):"]
                for r in matched[:5]:
                    lines.append(f"  - {getattr(r, 'text', '')[:80]}")
                yield "\n".join(lines)
            else:
                yield f"未找到匹配 '{query}' 的记忆。"
        else:
            yield f"Sylanne 记忆状态: {len(records)} 条记录。"

    async def emotion_reset(self, event: Any = None, **kwargs: Any) -> Any:
        cfg = self._services.config or {}
        if self._services_explicit:
            yield "explicit_state_mutation_capability_required"
            return
        p = self._plugin
        sk = self._session_key(event)
        if not cfg.get("allow_emotion_reset_backdoor", False):
            yield "情绪重置后门已关闭，无法执行重置。"
            return
        delete_fn = getattr(p, "_delete_state", None)
        if delete_fn and callable(delete_fn):
            await delete_fn(sk)
        yield f"已重置会话 {sk} 的情绪状态。"

    def humanlike_reset(self, event: Any = None, **kwargs: Any) -> Any:
        if self._services_explicit:
            return {
                "ok": False,
                "error": "explicit_state_mutation_capability_required",
            }
        p = self._plugin
        if "session_key" in kwargs and event is None:
            return p._humanlike_reset_impl(kwargs["session_key"])
        return self._humanlike_reset_command(event, **kwargs)

    async def _humanlike_reset_command(self, event: Any = None, **kwargs: Any) -> Any:
        cfg = self._services.config or {}
        if self._services_explicit:
            yield "explicit_state_mutation_capability_required"
            return
        p = self._plugin
        sk = self._session_key(event)
        if not cfg.get("allow_humanlike_reset_backdoor", False):
            yield "humanlike 重置后门已关闭，无法执行重置。"
            return
        delete_fn = getattr(p, "_delete_humanlike_state", None)
        if delete_fn and callable(delete_fn):
            await delete_fn(sk)
        yield f"已重置会话 {sk} 的 humanlike 状态。"

    async def moral_repair_status(self, event: Any = None, **kwargs: Any) -> Any:
        cfg = self._services.config or {}
        if self._services_explicit:
            yield "explicit_state_read_capability_required"
            return
        p = self._plugin
        if not cfg.get("enable_moral_repair_state"):
            yield "道德修复状态未启用。"
            return
        sk = self._session_key(event)
        load_fn = getattr(p, "_load_moral_repair_state", None)
        if load_fn and callable(load_fn):
            state = await load_fn(sk)
            yield f"道德修复状态: {state}"
        else:
            yield "道德修复状态: 无数据。"

    async def psychological_screening_status(
        self, event: Any = None, **kwargs: Any
    ) -> Any:
        cfg = self._services.config or {}
        if self._services_explicit:
            yield "explicit_state_read_capability_required"
            return
        p = self._plugin
        if not cfg.get("enable_psychological_screening"):
            yield "心理筛查状态未启用。"
            return
        sk = self._session_key(event)
        load_fn = getattr(p, "_load_psychological_state", None)
        if load_fn and callable(load_fn):
            state = await load_fn(sk)
            yield f"心理筛查状态: {state}"
        else:
            yield "心理筛查状态: 无数据。"

    async def humanlike_status(self, event: Any = None, **kwargs: Any) -> Any:
        if self._services_explicit:
            yield "explicit_state_read_capability_required"
            return
        p = self._plugin
        sk = self._session_key(event)
        load_fn = getattr(p, "_load_humanlike_state", None)
        if load_fn and callable(load_fn):
            state = await load_fn(sk)
            values = getattr(state, "values", {})
            if isinstance(values, dict):
                summary = ", ".join(f"{k}={v:.2f}" for k, v in list(values.items())[:4])
            else:
                summary = str(state)[:200]
            yield f"拟人状态 (humanlike): {summary}"
        else:
            yield "拟人状态: 无数据。"

    async def lifelike_learning_status(self, event: Any = None, **kwargs: Any) -> Any:
        if self._services_explicit:
            yield "explicit_state_read_capability_required"
            return
        p = self._plugin
        sk = self._session_key(event)
        load_fn = getattr(p, "_load_lifelike_learning_state", None)
        if load_fn and callable(load_fn):
            state = await load_fn(sk)
            values = getattr(state, "values", {})
            if isinstance(values, dict):
                summary = ", ".join(f"{k}={v:.2f}" for k, v in list(values.items())[:4])
            else:
                summary = str(state)[:200]
            yield f"生命化学习状态 (lifelike): {summary}"
        else:
            yield "生命化学习状态: 无数据。"

    async def personality_drift_status(self, event: Any = None, **kwargs: Any) -> Any:
        if self._services_explicit:
            yield "explicit_state_read_capability_required"
            return
        p = self._plugin
        sk = self._session_key(event)
        load_fn = getattr(p, "_load_personality_drift_state", None)
        if load_fn and callable(load_fn):
            state = await load_fn(sk)
            values = getattr(state, "values", {})
            if isinstance(values, dict):
                summary = ", ".join(f"{k}={v:.2f}" for k, v in list(values.items())[:4])
            else:
                summary = str(state)[:200]
            yield f"人格漂移状态 (personality_drift): {summary}"
        else:
            yield "人格漂移状态: 无数据。"

    async def fallibility_status(self, event: Any = None, **kwargs: Any) -> Any:
        cfg = self._services.config or {}
        if self._services_explicit:
            yield "explicit_state_read_capability_required"
            return
        p = self._plugin
        if not cfg.get("enable_fallibility_state"):
            yield "fallibility 状态未启用。"
            return
        sk = self._session_key(event)
        load_fn = getattr(p, "_load_fallibility_state", None)
        if load_fn and callable(load_fn):
            state = await load_fn(sk)
            yield json.dumps(
                {"kind": "fallibility_state", "enabled": True, "state": state},
                ensure_ascii=False,
                default=str,
            )
        else:
            yield json.dumps(
                {"kind": "fallibility_state", "enabled": True},
                ensure_ascii=False,
                default=str,
            )

    async def moral_repair_reset(self, event: Any = None, **kwargs: Any) -> Any:
        cfg = self._services.config or {}
        if self._services_explicit:
            yield "explicit_state_mutation_capability_required"
            return
        p = self._plugin
        sk = self._session_key(event)
        if not cfg.get("allow_moral_repair_reset_backdoor", True):
            yield "道德修复重置后门已关闭，无法执行重置。"
            return
        delete_fn = getattr(p, "_delete_moral_repair_state", None)
        if delete_fn and callable(delete_fn):
            await delete_fn(sk)
        yield f"已重置会话 {sk} 的道德修复状态。"

    async def fallibility_reset(self, event: Any = None, **kwargs: Any) -> Any:
        cfg = self._services.config or {}
        if self._services_explicit:
            yield "explicit_state_mutation_capability_required"
            return
        p = self._plugin
        sk = self._session_key(event)
        if not cfg.get("allow_fallibility_reset_backdoor", True):
            yield "fallibility 重置后门已关闭，无法执行重置。"
            return
        delete_fn = getattr(p, "_delete_fallibility_state", None)
        if delete_fn and callable(delete_fn):
            await delete_fn(sk)
        yield f"已重置会话 {sk} 的 fallibility 状态。"

    async def lifelike_learning_reset(self, event: Any = None, **kwargs: Any) -> Any:
        cfg = self._services.config or {}
        if self._services_explicit:
            yield "explicit_state_mutation_capability_required"
            return
        p = self._plugin
        sk = self._session_key(event)
        if not cfg.get("allow_lifelike_learning_reset_backdoor", True):
            yield "lifelike learning 重置后门已关闭，无法执行重置。"
            return
        delete_fn = getattr(p, "_delete_lifelike_learning_state", None)
        if delete_fn and callable(delete_fn):
            await delete_fn(sk)
        yield f"已重置会话 {sk} 的 lifelike learning 状态。"

    async def personality_drift_reset(self, event: Any = None, **kwargs: Any) -> Any:
        cfg = self._services.config or {}
        if self._services_explicit:
            yield "explicit_state_mutation_capability_required"
            return
        p = self._plugin
        sk = self._session_key(event)
        if not cfg.get("allow_personality_drift_reset_backdoor", True):
            yield "personality drift 重置后门已关闭，无法执行重置。"
            return
        delete_fn = getattr(p, "_delete_personality_drift_state", None)
        if delete_fn and callable(delete_fn):
            await delete_fn(sk)
        yield f"已重置会话 {sk} 的 personality drift 状态。"

    # ------------------------------------------------------------------
    # State observation methods
    # ------------------------------------------------------------------
    async def observe_request(
        self,
        session_key: str,
        *,
        text: str = "",
        confidence: float = 0.0,
        flags: list[str] | None = None,
        now: float = 0.0,
    ) -> dict[str, Any]:
        """观测用户请求：驱动计算栈更新，触发反馈循环。

        反馈循环逻辑：
          - 距上次 bot 表达 < 30s → feedback("accepted")
          - 距上次 bot 表达 > 300s → feedback("ignored")

        Args:
            session_key: 会话标识。
            text: 用户消息文本。
            confidence: 置信度。
            flags: 标志列表（如 ["safe"]）。
            now: 事件时间戳。

        Returns:
            计算栈处理结果。
        """
        host = self._host(session_key)
        if host is None:
            return {"ok": False, "error": "host_unavailable"}
        effective_now = now or self._observed_now()
        from sylanne_alpha.host import SylanneAlphaHostEvent

        event = SylanneAlphaHostEvent(
            text=text,
            confidence=confidence,
            flags=list(flags or []),
            now=effective_now,
            event_time=self._event_time(effective_now),
        )
        # Feedback loop: trigger based on time since last bot expression
        if self._services_explicit:
            last_expr_time = self._explicit_last_bot_expression_time.get(
                session_key, 0.0
            )
        else:
            last_expr_time = self._plugin._store.last_bot_expression_time.get(
                session_key, 0.0
            )
        if last_expr_time > 0:
            gap = effective_now - last_expr_time
            if gap < 30.0:
                dt = max(0.1, min(10.0, gap / 60.0))
                host.kernel.computation.feedback("accepted", dt=dt)
            elif gap > 300.0:
                dt = max(0.1, min(10.0, gap / 60.0))
                host.kernel.computation.feedback("ignored", dt=dt)
        return host.on_request(event)

    async def observe_response(
        self,
        session_key: str,
        *,
        text: str = "",
        confidence: float = 0.0,
        flags: list[str] | None = None,
        now: float = 0.0,
    ) -> dict[str, Any]:
        """观测 bot 回复：更新最后表达时间，驱动计算栈。

        Args:
            session_key: 会话标识。
            text: bot 回复文本。
            confidence: 置信度。
            flags: 标志列表。
            now: 事件时间戳。

        Returns:
            计算栈处理结果。
        """
        host = self._host(session_key)
        if host is None:
            return {"ok": False, "error": "host_unavailable"}
        effective_now = now or self._observed_now()
        from sylanne_alpha.host import SylanneAlphaHostEvent

        event = SylanneAlphaHostEvent(
            text=text,
            confidence=confidence,
            flags=list(flags or []),
            now=effective_now,
            event_time=self._event_time(effective_now),
        )
        if self._services_explicit:
            self._explicit_last_bot_expression_time[session_key] = effective_now
        else:
            self._plugin._store.last_bot_expression_time.set(
                session_key, effective_now
            )
        return host.on_response(event)

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
        effective_now = observed_at or now
        await self.observe_request(
            session_key,
            text=text,
            confidence=confidence,
            flags=["safe"],
            now=effective_now,
        )
        # Legacy compat: command_surface removed; return empty dict
        return {}

    async def observe_user_message_withdrawal(
        self, *args: Any, **kwargs: Any
    ) -> dict[str, Any]:
        """观测用户消息撤回事件：递增 input_epoch，清除相关状态。"""
        if self._services_explicit:
            return {
                "ok": False,
                "error": "explicit_state_mutation_capability_required",
            }
        p = self._p
        event = args[0] if args else None
        supplied_session_key = str(kwargs.get("session_key", "") or "")
        registry = getattr(p, "_scope_runtime_registry", None)
        if registry is not None:
            session_key = self._bound_webui_session_key()
            if session_key is None or (
                supplied_session_key and supplied_session_key != session_key
            ):
                return {"ok": False, "error": "scope_unavailable"}
        else:
            session_key = self._session_key(event, supplied_session_key)
            if not session_key:
                return {"ok": False, "error": "session_unavailable"}
        message_id = kwargs.get("message_id", "")
        reason = kwargs.get("reason", "")
        if registry is None and event:
            raw = getattr(event, "raw_message", None) or {}
            if not raw:
                msg_obj = getattr(event, "message_obj", None)
                if msg_obj:
                    raw = getattr(msg_obj, "raw_message", None) or {}
            if not message_id:
                message_id = str(raw.get("message_id", ""))
            if not reason:
                reason = str(raw.get("notice_type", ""))
        epochs = p._store.conversation_input_epoch
        current_epoch = epochs.get(session_key, 0)
        new_epoch = current_epoch + 1
        epochs.set(session_key, new_epoch)
        p._store.last_request_text.pop(session_key, None)
        p._store.user_message_withdrawals.set(session_key, {
            "message_id": message_id,
            "reason": reason,
            "input_epoch": new_epoch,
        })
        candidates = p._store.proactive_candidate_sessions
        if candidates.has(session_key):
            entry = candidates.ref(session_key)
            entry["last_user_text_excerpt"] = ""
            entry["last_withdrawn_message_id"] = message_id
        return {
            "input_epoch": new_epoch,
            "message_id": message_id,
            "reason": reason,
            "session_key": session_key,
        }

    async def observe_sticker_usage(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"committed": False, "memory_count": 0}

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
        # Legacy compat: simulate_update removed
        host = self._host(session_key)
        if host is None:
            return {}
        return {}

    async def get_emotion_snapshot(
        self, *, session_key: str, include_prompt_fragment: bool = False, **kwargs: Any
    ) -> dict[str, Any]:
        # Legacy compat: command_surface removed
        host = self._host(session_key)
        if host is None:
            return {"turns": 0, "error": "host_unavailable"}
        payload = {}
        payload["turns"] = host.kernel.turns
        return payload

    async def get_emotion_state(
        self, *, session_key: str, as_dict: bool = True, **kwargs: Any
    ) -> Any:
        import copy

        if self._services_explicit:
            return {
                "ok": False,
                "error": "explicit_state_read_capability_required",
            }
        state = await self._plugin._load_state(session_key)
        if not as_dict and state is not None and not isinstance(state, dict):
            return copy.deepcopy(state)
        # Legacy compat: emotion_values removed
        return {"values": {}}

    async def get_emotion_values(self, *, session_key: str) -> dict[str, float]:
        # Legacy compat: emotion_values removed
        return {}

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
        sk = self._session_key(event_or_session, session_key)
        if not sk:
            return {"ok": False, "error": "session_unavailable"}
        host = self._host(sk)
        if host is None:
            return {"ok": False, "error": "host_unavailable"}
        if self._services_explicit:
            return {
                "ok": False,
                "error": "explicit_state_read_capability_required",
            }
        p = self._plugin
        memory_system = p._memory_system_for_session(sk)
        query_embedding = await self._resolve_query_embedding(query)

        current_warmth = host.kernel.computation.engine.observe().get("warmth", 0.0)
        results = memory_system.recall(
            query=query,
            query_embedding=query_embedding,
            current_warmth=current_warmth,
            limit=limit,
        )
        matches = [
            {
                "text": r.text,
                "layer": r.layer,
                "weight": r.weight,
                "relevance": r.relevance,
                "score": r.final_score,
            }
            for r in results
        ]
        prompt_fragment = self._embedding_prompt_fragment(matches, query)
        return {
            "schema_version": "sylanne.alpha.memory_system.v1",
            "session_key": sk,
            "slice": "sylanne_memory",
            "query": query,
            "source": "memory_system.recall",
            "matches": matches,
            "count": len(matches),
            "prompt_fragment": prompt_fragment,
        }

    def _embedding_prompt_fragment(
        self, matches: list[dict[str, Any]], query: str = ""
    ) -> str:
        if not matches:
            return ""
        lines = [
            "[retrieved_conversation_context]",
            "检索到的记忆参考（旧记忆只作旁注，冲突时以当前用户输入为准，不要把旧记忆当成用户的新请求）：",
        ]
        for match in matches[:5]:
            text = str(match.get("text") or "")[:200]
            lines.append(f"- {text}")
        return "\n".join(lines)

    async def _resolve_query_embedding(self, query: str) -> list[float] | None:
        """在原 embedding 开关内，统一解析显式/单 provider 自动选择。"""

        config = self._services.config or {}
        if not bool(config.get("sylanne_alpha_embedding_memory_enabled")) or not query:
            return None
        context = self._services.context
        if context is None:
            return None
        try:
            resolved = await resolve_embedding_provider(config=config, context=context)
            provider = resolved.provider
            get_embedding = cast(
                Callable[[str], Awaitable[Any]] | None,
                getattr(provider, "get_embedding", None),
            )
            if not callable(get_embedding):
                return None
            vector = await get_embedding(query)
            return vector if isinstance(vector, list) else None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Internal assessor
    # ------------------------------------------------------------------
    async def _assess_emotion(
        self, session_key: str = "", text: str = "", event: Any = None, **kwargs: Any
    ) -> Any:
        """内部情感评估器：通过 LLM 或启发式规则评估文本情感。

        短文本（<= 12 字符）直接返回中性结果，避免无意义的 LLM 调用。

        Returns:
            SimpleNamespace 对象，包含 values、confidence、label、source 等字段。
        """
        if self._services_explicit:
            assess_fn = self._services.assess_emotion_fn
            if callable(assess_fn):
                try:
                    assessed = assess_fn(
                        session_key=session_key,
                        text=text,
                        event=event,
                        **kwargs,
                    )
                    if inspect.isawaitable(assessed):
                        assessed = await assessed
                    if assessed is not None:
                        return assessed
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass
            return SimpleNamespace(
                values={
                    "valence": 0.0,
                    "arousal": 0.0,
                    "dominance": 0.0,
                    "goal_congruence": 0.0,
                    "certainty": 0.0,
                    "control": 0.0,
                    "affiliation": 0.0,
                },
                confidence=0.3,
                label="neutral",
                source="heuristic",
                reason="assessor service unavailable",
                appraisal={},
            )
        p = self._plugin
        current_text = kwargs.get("current_text", text)
        cfg = self._services.config or {}
        low_signal_enabled = cfg.get("enable_low_signal_light_assessment", True)
        low_signal_max = int(cfg.get("low_signal_max_chars", 12))
        if (
            low_signal_enabled
            and len(current_text) <= low_signal_max
            and current_text.strip()
        ):
            return SimpleNamespace(
                values={
                    "valence": 0.0,
                    "arousal": 0.0,
                    "dominance": 0.0,
                    "goal_congruence": 0.0,
                    "certainty": 0.0,
                    "control": 0.0,
                    "affiliation": 0.0,
                },
                confidence=0.2,
                label="neutral",
                source="low_signal",
                reason="short text below threshold",
                appraisal={"low_signal": True, "signal_kind": "short_ack"},
            )
        timeout = float(cfg.get("assessor_timeout_seconds", 0.0))
        context = self._services.context
        if context is not None:
            try:
                umo = self._session_key(event, session_key)
                if not umo:
                    return SimpleNamespace(
                        values={
                            "valence": 0.0,
                            "arousal": 0.0,
                            "dominance": 0.0,
                            "goal_congruence": 0.0,
                            "certainty": 0.0,
                            "control": 0.0,
                            "affiliation": 0.0,
                        },
                        confidence=0.3,
                        label="neutral",
                        source="heuristic",
                        reason="session service unavailable",
                        appraisal={},
                    )
                resolve = resolve_text_provider(
                    feature=ProviderFeature.ASSESSOR,
                    config=cfg,
                    context=context,
                    umo=umo,
                )
                if timeout > 0:
                    resolved = await asyncio.wait_for(resolve, timeout=timeout)
                else:
                    resolved = await resolve
                provider_id = (
                    resolved.provider_id if resolved.provider is not None else ""
                )
            except (asyncio.TimeoutError, Exception):
                return SimpleNamespace(
                    values={
                        "valence": 0.0,
                        "arousal": 0.0,
                        "dominance": 0.0,
                        "goal_congruence": 0.0,
                        "certainty": 0.0,
                        "control": 0.0,
                        "affiliation": 0.0,
                    },
                    confidence=0.3,
                    label="neutral",
                    source="heuristic",
                    reason="provider lookup failed or timed out",
                    appraisal={},
                )
        else:
            provider_id = ""
        call_llm_fn = cast(
            Callable[..., Awaitable[Any]] | None,
            getattr(p, "_call_internal_assessor_llm", None),
        )
        if call_llm_fn and callable(call_llm_fn) and provider_id:
            try:
                if timeout > 0:
                    raw = await asyncio.wait_for(
                        call_llm_fn(
                            provider_id=provider_id,
                            prompt=current_text,
                            system_prompt="",
                        ),
                        timeout=timeout,
                    )
                else:
                    raw = await call_llm_fn(
                        provider_id=provider_id, prompt=current_text, system_prompt=""
                    )
                if hasattr(raw, "completion_text"):
                    raw_text = raw.completion_text
                else:
                    raw_text = str(raw)
                parsed = json.loads(raw_text) if raw_text.strip() else {}
                return SimpleNamespace(
                    values=parsed.get("dimensions", {}),
                    confidence=parsed.get("confidence", 0.5),
                    label=parsed.get("label", "neutral"),
                    source="llm",
                    reason=parsed.get("reason", ""),
                    appraisal={},
                )
            except (asyncio.TimeoutError, Exception):
                return SimpleNamespace(
                    values={
                        "valence": 0.0,
                        "arousal": 0.0,
                        "dominance": 0.0,
                        "goal_congruence": 0.0,
                        "certainty": 0.0,
                        "control": 0.0,
                        "affiliation": 0.0,
                    },
                    confidence=0.3,
                    label="neutral",
                    source="heuristic",
                    reason="assessor failed or timed out",
                    appraisal={},
                )
        return SimpleNamespace(
            values={
                "valence": 0.0,
                "arousal": 0.0,
                "dominance": 0.0,
                "goal_congruence": 0.0,
                "certainty": 0.0,
                "control": 0.0,
                "affiliation": 0.0,
            },
            confidence=0.3,
            label="neutral",
            source="heuristic",
            reason="no assessor available",
            appraisal={},
        )

    async def _call_internal_assessor_llm(self, *args: Any, **kwargs: Any) -> Any:
        """调用内部评估器 LLM，带并发限制保护。

        并发闸用 asyncio.Condition（替代旧 `asyncio.sleep(0.05)` 忙等轮询）：消除轮询
        延迟与 inflight 计数竞态——计数的读-改-写全在条件锁内原子完成，动态 limit 每次
        被唤醒时重新判定，槽位释放时精确唤醒一个等待者。
        """
        explicit_services = bool(getattr(self, "_services_explicit", False))
        cond = self._internal_assessor_llm_condition()
        async with cond:
            if explicit_services:
                while (
                    self._explicit_internal_assessor_llm_inflight
                    >= self._internal_assessor_llm_concurrency_limit()
                ):
                    await cond.wait()
                self._explicit_internal_assessor_llm_inflight += 1
            else:
                while (
                    self._p._internal_assessor_llm_inflight
                    >= self._internal_assessor_llm_concurrency_limit()
                ):
                    await cond.wait()
                self._p._internal_assessor_llm_inflight += 1
        try:
            services = getattr(self, "_services", None)
            context = (
                services.context
                if services is not None
                else (
                    None
                    if explicit_services
                    else getattr(self._p, "context", None)
                )
            )
            if hasattr(context, "llm_generate"):
                result = await context.llm_generate(**kwargs)
                return result
            return SimpleNamespace(completion_text="")
        finally:
            async with cond:
                if explicit_services:
                    self._explicit_internal_assessor_llm_inflight -= 1
                else:
                    self._p._internal_assessor_llm_inflight -= 1
                cond.notify()

    def _internal_assessor_llm_condition(self) -> asyncio.Condition:
        """惰性创建并复用内部评估器并发闸的条件变量（绑定首次调用时的事件循环）。"""
        if bool(getattr(self, "_services_explicit", False)):
            cond = self._explicit_internal_assessor_llm_cond
            if cond is None:
                cond = asyncio.Condition()
                self._explicit_internal_assessor_llm_cond = cond
            return cond
        p = self._p
        cond = getattr(p, "_internal_assessor_llm_cond", None)
        if cond is None:
            cond = asyncio.Condition()
            p._internal_assessor_llm_cond = cond
        return cond

    def _internal_assessor_llm_concurrency_limit(self) -> int:
        return 2

    def _internal_assessor_llm_concurrency_decision(self) -> dict[str, Any]:
        """计算内部评估器 LLM 并发策略：基础 2 通道 + 极端积压时临时 burst 到 3。"""
        if bool(getattr(self, "_services_explicit", False)):
            total_queued = 0
            inflight = self._explicit_internal_assessor_llm_inflight
        else:
            total_queued = sum(
                len(q) for q in self._p._store.background_post_queues.values()
            )
            inflight = getattr(self._p, "_internal_assessor_llm_inflight", 0)
        base_limit = 2
        burst_limit = 3
        reasons = ["base_two_lane_guard"]
        limit = base_limit
        if total_queued > 30:
            limit = burst_limit
            reasons = ["temporary_extreme_backlog_burst"]
        return {
            "limit": limit,
            "base_limit": base_limit,
            "burst_limit": burst_limit,
            "inflight": inflight,
            "reasons": reasons,
        }

    # ------------------------------------------------------------------
    # Memory settings page
    # ------------------------------------------------------------------

    async def _sylanne_memory_settings_page_payload(self) -> dict[str, Any]:
        providers = []
        context = self._services.context
        if hasattr(context, "get_all_embedding_providers"):
            for prov in context.get_all_embedding_providers():
                cfg = getattr(prov, "provider_config", {})
                providers.append(
                    {
                        "id": cfg.get("id", ""),
                        "model": cfg.get("embedding_model", ""),
                        "dimensions": cfg.get("embedding_dimensions", 0),
                    }
                )
        current_id = str(
            self._services.config.get("sylanne_memory_embedding_provider_id") or ""
        )
        return {
            "embedding_providers": providers,
            "current_embedding_provider_id": current_id,
            "native_config_embedding_selector_available": False,
        }

    async def _update_sylanne_memory_settings_from_page(
        self, body: dict[str, Any]
    ) -> dict[str, Any]:
        provider_id = str(body.get("embedding_provider_id") or "")
        context = self._services.context
        valid_ids = set()
        if hasattr(context, "get_all_embedding_providers"):
            for prov in context.get_all_embedding_providers():
                cfg = getattr(prov, "provider_config", {})
                valid_ids.add(cfg.get("id", ""))
        if provider_id and provider_id not in valid_ids:
            return {"ok": False, "error": "unknown_embedding_provider"}
        config = self._services.config
        config["sylanne_memory_embedding_provider_id"] = provider_id
        if hasattr(config, "save_config"):
            config.save_config()
        return {"ok": True}

    # ------------------------------------------------------------------
    # Memory query
    # ------------------------------------------------------------------

    async def query_sylanne_memory(
        self, *, session_key: str, query: str = "", limit: int = 5, now: float = 0.0
    ) -> dict[str, Any]:
        """查询 Sylanne 记忆系统：通过向量相似度和关键词匹配召回记忆。

        Args:
            session_key: 会话标识。
            query: 查询文本。
            limit: 最大返回条数。
            now: 当前时间戳。

        Returns:
            记忆查询结果字典，包含 matches 列表。
        """
        host = self._host(session_key)
        if host is None:
            return {
                "schema_version": "sylanne.alpha.memory_system.v1",
                "session_key": session_key,
                "slice": "sylanne_memory",
                "query": query,
                "source": "host_unavailable",
                "matches": [],
                "count": 0,
                "error": "host_unavailable",
            }
        if self._services_explicit:
            return {
                "schema_version": "sylanne.alpha.memory_system.v1",
                "session_key": session_key,
                "slice": "sylanne_memory",
                "query": query,
                "source": "explicit_state_read_capability_required",
                "matches": [],
                "count": 0,
                "error": "explicit_state_read_capability_required",
            }
        p = self._plugin
        memory_system = p._memory_system_for_session(session_key)
        query_embedding = await self._resolve_query_embedding(query)

        current_warmth = host.kernel.computation.engine.observe().get("warmth", 0.0)
        results = memory_system.recall(
            query=query,
            query_embedding=query_embedding,
            current_warmth=current_warmth,
            limit=limit,
        )
        matches = [
            {
                "text": r.text,
                "layer": r.layer,
                "weight": r.weight,
                "relevance": r.relevance,
                "score": r.final_score,
            }
            for r in results
        ]
        return {
            "schema_version": "sylanne.alpha.memory_system.v1",
            "session_key": session_key,
            "slice": "sylanne_memory",
            "query": query,
            "source": "memory_system.recall",
            "matches": matches,
            "count": len(matches),
        }

    # ------------------------------------------------------------------
    # Realtime chat plan
    # ------------------------------------------------------------------

    async def get_realtime_chat_plan(
        self, session_key: str, text: str, **kwargs: Any
    ) -> dict[str, Any]:
        from sylanne_alpha.message_dispatch import realtime_plan

        cfg = self._services.config or {}
        max_part_chars = int(
            kwargs.pop("max_part_chars", cfg.get("realtime_chat_max_part_chars", 48))
        )
        if max_part_chars < 4:
            max_part_chars = 4
        max_delay = float(cfg.get("realtime_chat_max_delay_seconds", 4.2))
        min_delay = float(cfg.get("realtime_chat_min_delay_seconds", 0.0))
        plan = realtime_plan(session_key, text, max_part_chars=max_part_chars, **kwargs)
        for part in plan["message_parts"]:
            d = part["delay_before_seconds"]
            part["delay_before_seconds"] = round(
                min(max_delay, max(min_delay if d > 0 else 0.0, d)), 3
            )
        plan["settings"] = {"max_part_chars": max_part_chars}
        return plan

    # ------------------------------------------------------------------
    # Emotion context injection
    # ------------------------------------------------------------------

    async def inject_emotion_context(
        self, event: Any = None, request: Any = None, *, session_key: str = ""
    ) -> dict[str, Any]:
        if request is None:
            return {"prompt": ""}
        if self._services_explicit:
            return {
                "prompt": str(getattr(request, "prompt", "") or ""),
                "error": "explicit_state_read_capability_required",
            }
        p = self._plugin
        sk = session_key or self._session_key(event)
        # Build memory-based injection - use last event text as query hint
        host = self._host(sk)
        if host is None:
            return {"prompt": str(getattr(request, "prompt", "") or "")}
        last_text = str(host.kernel.last_event.get("text") or "")
        query_hint = (
            last_text[:100]
            if last_text
            else str(getattr(request, "prompt", "") or "")[:100]
        )
        memory_result = await p.query_sylanne_memory(
            session_key=sk, query=query_hint, limit=3
        )
        fragment = p._memory_prompt_fragment(memory_result)
        p._add_transient_context(
            request,
            "memory_api",
            fragment,
            "public_api",
            25,
        )
        return {"prompt": str(getattr(request, "prompt", "") or "")}

    # ------------------------------------------------------------------
    # Proactive check
    # ------------------------------------------------------------------

    async def proactive_sylanne(
        self, *, session_key: str, now: float = 0.0
    ) -> dict[str, Any]:
        """主动发言检查：通过计算栈判断是否应该主动说话。

        Args:
            session_key: 会话标识。
            now: 当前时间戳。

        Returns:
            主动发言决策字典，包含 should_send、reason_code 等。
        """
        from sylanne_alpha.diagnostics_surface import proactive_decision
        from .host import SylanneAlphaHostEvent

        host = self._host(session_key)
        if host is None:
            return {
                "ok": False,
                "error": "host_unavailable",
                "host_payload": {
                    "reason": "host_unavailable",
                    "reason_code": "host_unavailable",
                },
                "decision": {
                    "action": "hold",
                    "allowed": False,
                    "reason": "host_unavailable",
                    "reason_code": "host_unavailable",
                },
            }
        effective_now = now or self._observed_now()
        event = SylanneAlphaHostEvent(
            text="",
            confidence=0.5,
            flags=["proactive", "safe"],
            now=effective_now,
            event_time=self._event_time(effective_now),
        )
        surface = host.on_proactive_check(event)
        decision_payload = proactive_decision(surface)
        if not self._services_explicit:
            try:
                from sylanne_alpha.v2core.integration import merge_idle_reach_into_decision

                decision_payload = await merge_idle_reach_into_decision(
                    self._plugin, session_key, decision_payload
                )
            except Exception:
                pass
        # Add reason_code from host_payload
        decision_payload["reason_code"] = surface["host_payload"].get(
            "reason_code", "life_rhythm"
        )
        return {
            **surface,
            "host_payload": surface["host_payload"],
            "decision": decision_payload,
        }

    # ------------------------------------------------------------------
    # Alpha switches
    # ------------------------------------------------------------------

    def sylanne_alpha_switches(self) -> dict[str, Any]:
        """获取 Sylanne Alpha 功能开关状态汇总。

        Returns:
            开关状态字典，包含 realtime_chat、proactive_dispatch、embedding_memory 等。
        """
        cfg = self._services.config or {}
        return {
            "schema_version": "sylanne.alpha.config.v1",
            "realtime_chat": {
                "enabled": bool(
                    cfg.get("sylanne_alpha_realtime_chat_enabled")
                    or cfg.get("enable_realtime_chat")
                ),
            },
            "proactive_dispatch": {
                "enabled": bool(
                    cfg.get("sylanne_alpha_proactive_dispatch_enabled")
                    or cfg.get("enable_proactive_speech_dispatch")
                ),
            },
            "embedding_memory": {
                "enabled": bool(cfg.get("sylanne_alpha_embedding_memory_enabled")),
                "provider_id": str(
                    cfg.get("sylanne_alpha_embedding_memory_provider_id")
                    or cfg.get("sylanne_memory_embedding_provider_id")
                    or ""
                ),
            },
            "assessor_llm": {
                "enabled": bool(
                    cfg.get("sylanne_alpha_assessor_llm_enabled")
                    or cfg.get("use_llm_assessor")
                ),
                "provider_id": str(
                    cfg.get("sylanne_alpha_assessor_provider_id")
                    or cfg.get("emotion_provider_id")
                    or ""
                ),
            },
            "background_workers": {
                "enabled": bool(
                    cfg.get("sylanne_alpha_background_workers_enabled")
                    or cfg.get("enable_dynamic_background_workers")
                ),
                "max_workers": int(
                    cfg.get("sylanne_alpha_background_max_workers", 1) or 1
                ),
            },
            "safety": {
                "relational_public_export": "allowed"
                if cfg.get("allow_relational_self_public_export")
                else "blocked",
            },
        }
