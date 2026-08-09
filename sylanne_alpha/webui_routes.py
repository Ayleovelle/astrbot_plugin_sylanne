"""WebUI 路由处理器模块（AstrBot register_web_api 版本）。

封装所有通过 AstrBot 内置 Web 服务器注册的 HTTP 路由处理函数。
这些路由运行在 AstrBot 的 FastAPI 应用内，受 AstrBot 自身的认证保护。

与 webui_server.py 的区别：
- 本模块的路由注册在 AstrBot 的 Web 服务器上（共享端口）
- webui_server.py 是独立的 HTTP 服务器（独占端口 2718）
- 两者提供相同的 API 功能，但认证机制不同

路由功能：
- /api/state: 完整状态 JSON（情感/门控/路由/边界/表达/计时/层/脊柱/人格）
- /api/settings: 配置读写
- /api/computation_logs: 计算日志
- /api/memory_pools: 三层记忆池数据
- /api/memory_meltdown: 记忆清除（需 token 验证）
- /api/webui_probe: 独立 WebUI 探针
"""

from __future__ import annotations

import asyncio
import inspect
import json
import math
import secrets
import time
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sylanne_alpha.scoped_api import (
    SCOPE_NONCE_HEADER,
    ScopedApiAuthorization,
    ScopedApiError,
    ScopedApiRequest,
    scoped_api_service_for_plugin,
)
from sylanne_alpha.scope_contracts import ScopeApiPathEcho

if TYPE_CHECKING:
    from sylanne_alpha.protocols import PluginHost

try:
    from astrbot.api import logger  # type: ignore
except ImportError:
    import logging as _logging

    logger = _logging.getLogger("astrbot_plugin_sylanne")  # type: ignore


OBSERVATION_HISTORY_GROUPS = frozenset(
    {
        "emotion",
        "boundary",
        "timing",
        "routing",
        "gate",
        "expression",
        "feedback",
    }
)


def _observation_query_value(
    query: Mapping[str, Any],
    name: str,
) -> Any:
    value = query.get(name)
    if isinstance(value, (list, tuple)):
        return value[-1] if value else None
    return value


def _observation_query_int(
    query: Mapping[str, Any],
    name: str,
    *,
    default: int | None = None,
    nonnegative: bool = False,
) -> int | None:
    raw = _observation_query_value(query, name)
    if raw is None:
        return default
    if isinstance(raw, bool):
        raise ValueError(f"{name} must be an integer")
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, str):
        candidate = raw.strip()
        if not candidate:
            raise ValueError(f"{name} must be an integer")
        try:
            value = int(candidate, 10)
        except ValueError as exc:
            raise ValueError(f"{name} must be an integer") from exc
    else:
        raise ValueError(f"{name} must be an integer")
    if nonnegative and value < 0:
        raise ValueError(f"{name} must be nonnegative")
    return value


def parse_observation_history_query(
    query: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the shared observation-history query contract."""

    session = str(_observation_query_value(query, "session") or "").strip()
    if not session:
        raise ValueError("session is required")
    group = str(_observation_query_value(query, "group") or "").strip()
    if group not in OBSERVATION_HISTORY_GROUPS:
        allowed = ", ".join(sorted(OBSERVATION_HISTORY_GROUPS))
        raise ValueError(f"group must be one of: {allowed}")

    from_ms = _observation_query_int(query, "from_ms", nonnegative=True)
    to_ms = _observation_query_int(query, "to_ms", nonnegative=True)
    if from_ms is not None and to_ms is not None and from_ms > to_ms:
        raise ValueError("from_ms must be less than or equal to to_ms")
    max_points = _observation_query_int(query, "max_points", default=240)
    assert max_points is not None
    max_points = max(1, min(1000, max_points))
    return {
        "session": session,
        "group": group,
        "from_ms": from_ms,
        "to_ms": to_ms,
        "max_points": max_points,
    }


def build_observation_history_payload(
    plugin: Any,
    query: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the canonical history payload used by every HTTP surface."""

    parsed = parse_observation_history_query(query)
    session_context = getattr(plugin, "_session_ctx", None)
    store = getattr(session_context, "observation_history_store", None)
    if store is None or not callable(getattr(store, "query", None)):
        raise RuntimeError("observation history is unavailable")
    result = store.query(
        parsed["session"],
        group=parsed["group"],
        from_ms=parsed["from_ms"],
        to_ms=parsed["to_ms"],
        max_points=parsed["max_points"],
    )
    storage_source = result["storage"]
    limit_bytes = storage_source["limit_bytes"]
    storage = {
        "used_bytes": storage_source["used_bytes"],
        "limit_bytes": None if limit_bytes == 0 else limit_bytes,
        "oldest_ms": storage_source["oldest_ms"],
        "segment_count": storage_source["segment_count"],
        "cleanup_active": storage_source["cleanup_active"],
    }
    return {
        "schema_version": result["schema_version"],
        "session": result["session"],
        "group": result["group"],
        "points": result["points"],
        "sample_count": result["sample_count"],
        "downsampled": result["downsampled"],
        "partial": result["partial"],
        "storage": storage,
    }


# ---------------------------------------------------------------------------
# Item 62: 内置术语词典（供前端悬浮卡片使用）
# ---------------------------------------------------------------------------

GLOSSARY: dict[str, str] = {
    "伤痕": "Scar Algebra 中的核心概念。事件在系统中留下的不可删除的痕迹，改变对未来事件的敏感度。",
    "空洞": "Void Calculus 中的核心概念。没说出口的话形成的计算对象，有深度、压力和边界。",
    "共振": "Coherence。伤痕和空洞对齐时系统连贯，不对齐时'解离'。",
    "相变": "Phase Transition。压力积累超过阈值时的表达模式切换。",
    "层论": "Relational Sheaf Theory。用层上同调描述多关系之间的相互影响。",
    "脊柱": "Computation Spine。七层计算栈的统称。",
    "人格漂移": "Personality Drift。人格参数随经历缓慢变化的过程。",
    "熔毁": "Memory Meltdown。彻底清除所有记忆池的不可逆操作。",
}


def build_model_routing_payload(
    config: dict[str, Any],
    schema: dict[str, Any],
    providers: list[dict[str, Any]],
) -> dict[str, Any]:
    """Derive the compact routing summary without mutating stored values."""

    def provider_id(key: str) -> str:
        return str(config.get(key, "") or "").strip()

    auxiliary_id = provider_id("sylanne_alpha_aux_provider_id")
    transcription_id = provider_id("sylanne_alpha_transcription_provider_id")
    embedding_id = provider_id("sylanne_alpha_embedding_memory_provider_id")

    auxiliary: dict[str, Any] = {"mode": "inherit"}
    if auxiliary_id:
        auxiliary = {"mode": "explicit", "provider_id": auxiliary_id}

    transcription: dict[str, Any] = {"mode": "auto"}
    if transcription_id:
        transcription = {"mode": "explicit", "provider_id": transcription_id}

    embedding_enabled = bool(
        config.get(
            "sylanne_alpha_embedding_memory_enabled",
            schema.get("sylanne_alpha_embedding_memory_enabled", {}).get(
                "default", False
            ),
        )
    )
    embedding_providers = [
        item
        for item in providers
        if str(item.get("type", "") or "").strip().lower() == "embedding"
    ]
    if not embedding_enabled:
        embedding: dict[str, Any] = {"mode": "disabled"}
    elif embedding_id:
        embedding = {"mode": "explicit", "provider_id": embedding_id}
    elif len(embedding_providers) == 1:
        embedding = {
            "mode": "auto",
            "provider_id": str(embedding_providers[0].get("id", "") or ""),
        }
    elif embedding_providers:
        embedding = {"mode": "selection_required"}
    else:
        embedding = {"mode": "unavailable"}

    advanced_override_count = sum(
        1
        for key, meta in schema.items()
        if meta.get("ui_tier") == "advanced_provider" and provider_id(key)
    )
    return {
        "chat": {"mode": "current_conversation"},
        "auxiliary": auxiliary,
        "image_understanding": {"mode": "auto"},
        "transcription": transcription,
        "embedding": embedding,
        "advanced_override_count": advanced_override_count,
    }


CONFIG_PRESETS: dict[str, dict[str, Any]] = {
    "gentle": {
        "name": "温柔型",
        "description": "低主动性、高共情、柔和表达",
        "values": {
            "expression_drive_trait": 0.3,
            "perception_acuity": 0.7,
            "boundary_permeability": 0.4,
            "inner_order": 0.6,
            "relational_gravity": 0.7,
        },
    },
    "sharp": {
        "name": "锋利型",
        "description": "高表达驱力、直接、边界清晰",
        "values": {
            "expression_drive_trait": 0.8,
            "perception_acuity": 0.6,
            "boundary_permeability": 0.2,
            "inner_order": 0.8,
            "relational_gravity": 0.4,
        },
    },
    "quiet": {
        "name": "沉默型",
        "description": "低表达、高内省、深度观察",
        "values": {
            "expression_drive_trait": 0.15,
            "perception_acuity": 0.9,
            "boundary_permeability": 0.3,
            "inner_order": 0.7,
            "relational_gravity": 0.5,
        },
    },
}


def _comp_gate_dict(comp: object) -> dict:
    """取 ResonanceSpine gate 的可观测状态。"""
    try:
        return comp.gate.to_dict()  # type: ignore[attr-defined]
    except Exception:
        return {}


def _comp_boundary_dict(comp: object) -> dict:
    """取 ResonanceSpine boundary 的可观测状态。

    共振场字段名为 boundary_integrity/internal_entropy，补 integrity/entropy
    别名以兼容下游(state_handler 读 integrity/entropy)。
    """
    try:
        d = dict(comp.boundary.to_dict())  # type: ignore[attr-defined]
        d.setdefault("integrity", d.get("boundary_integrity", 1.0))
        d.setdefault("entropy", d.get("internal_entropy", 0.0))
        return d
    except Exception:
        return {}


def _comp_route_stats(comp: object, history: object = None) -> tuple[dict[str, int], dict[str, int]]:
    """Return the active computation backend's route counters in API/UI forms."""
    counts: dict[str, Any] = {}
    diagnostics = getattr(comp, "diagnostics", None)
    if callable(diagnostics):
        try:
            raw = diagnostics()
            if isinstance(raw, dict) and isinstance(raw.get("route_counts"), dict):
                counts = raw["route_counts"]
        except Exception:
            counts = {}

    if not counts and isinstance(history, list):
        for entry in history:
            if not isinstance(entry, dict):
                continue
            route = str(entry.get("route") or "").strip().lower()
            if route:
                counts[route] = int(counts.get(route, 0)) + 1

    route_stats: dict[str, int] = {}
    for name, value in counts.items():
        route = str(name).strip().lower()
        if not route:
            continue
        try:
            route_stats[route] = int(value)
        except (TypeError, ValueError):
            route_stats[route] = 0
    if not route_stats:
        route_stats = {"resonance": 0, "skip": 0}
    route_distribution = {name.upper(): count for name, count in route_stats.items()}
    return route_stats, route_distribution


def _webui_session_items(plugin: object, session_keys: list[str]) -> list[dict[str, Any]]:
    """Normalize session identifiers into the object contract consumed by the SPA."""
    hosts = getattr(plugin, "_hosts", {}) or {}
    items: list[dict[str, Any]] = []
    for session_key in session_keys:
        ticks = 0
        host = hosts.get(session_key) if isinstance(hosts, dict) else None
        if host is not None:
            kernel = getattr(host, "kernel", None)
            comp = getattr(kernel, "computation", None)
            ticks = int(getattr(comp, "_tick_count", 0) or 0)
        items.append({"id": session_key, "name": session_key, "tick_count": ticks})
    return items


_SCOPED_NUMERIC_KEYS = frozenset(
    {
        "activation",
        "arousal",
        "boundary_integrity",
        "coherence",
        "confidence",
        "drive",
        "energy",
        "entropy",
        "integrity",
        "internal_entropy",
        "load",
        "pressure",
        "score",
        "stability",
        "tension",
        "threshold",
        "valence",
        "value",
        "warmth",
    }
)
_SCOPED_ROUTE_KEYS = frozenset(
    {"resonance", "skip", "fallback", "error", "direct", "defer"}
)
_SCOPED_HISTORY_KEYS = frozenset(
    {"at_ms", "timestamp", "timestamp_ms", "score", "value", "confidence"}
)


def _scoped_number(value: object) -> int | float | None:
    if type(value) is int:
        return value
    if type(value) is float and math.isfinite(value):
        return round(value, 6)
    return None


def _scoped_metric_map(value: object) -> dict[str, int | float]:
    """Project only known numeric telemetry fields from private runtime state."""

    if not isinstance(value, Mapping):
        return {}
    projected: dict[str, int | float] = {}
    for key in _SCOPED_NUMERIC_KEYS:
        number = _scoped_number(value.get(key))
        if number is not None:
            projected[key] = number
    return projected


def _scoped_route_counts(value: object) -> dict[str, int | float]:
    if not isinstance(value, Mapping):
        return {}
    projected: dict[str, int | float] = {}
    for key in _SCOPED_ROUTE_KEYS:
        number = _scoped_number(value.get(key))
        if number is not None:
            projected[key] = number
    return projected


def _scoped_history_payload(plugin: object, authorization: ScopedApiAuthorization) -> dict[str, object]:
    store = getattr(getattr(plugin, "_session_ctx", None), "observation_history_store", None)
    query = getattr(store, "query", None)
    if not callable(query):
        return {"sample_count": 0, "points": [], "storage": {}}
    try:
        source = query(
            authorization.scope.storage_token,
            group="emotion",
            from_ms=None,
            to_ms=None,
            max_points=240,
        )
    except Exception:  # noqa: BLE001 - no private failure details cross the API
        return {"sample_count": 0, "points": [], "storage": {}}
    if not isinstance(source, Mapping):
        return {"sample_count": 0, "points": [], "storage": {}}
    points: list[dict[str, int | float]] = []
    raw_points = source.get("points")
    if isinstance(raw_points, list):
        for point in raw_points[:240]:
            if not isinstance(point, Mapping):
                continue
            public_point: dict[str, int | float] = {}
            for key in _SCOPED_HISTORY_KEYS:
                number = _scoped_number(point.get(key))
                if number is not None:
                    public_point[key] = number
            if public_point:
                points.append(public_point)
    storage_source = source.get("storage")
    storage: dict[str, int | float] = {}
    if isinstance(storage_source, Mapping):
        for key in ("used_bytes", "limit_bytes", "oldest_ms", "segment_count"):
            number = _scoped_number(storage_source.get(key))
            if number is not None:
                storage[key] = number
    sample_count = _scoped_number(source.get("sample_count"))
    return {
        "sample_count": 0 if sample_count is None else sample_count,
        "points": points,
        "storage": storage,
    }


def _scoped_memory_pools(plugin: object, authorization: ScopedApiAuthorization) -> dict[str, int]:
    memory = None
    getter = getattr(plugin, "_memory_system_for_scope", None)
    if callable(getter):
        try:
            memory = getter(authorization.scope)
        except Exception:  # noqa: BLE001 - unavailable private owner is empty
            memory = None
    if memory is None:
        return {
            "l1_count": 0,
            "l2_count": 0,
            "l3_node_count": 0,
            "l3_edge_count": 0,
            "tick": 0,
        }
    return {
        "l1_count": len(getattr(memory, "_l1", ()) or ()),
        "l2_count": len(getattr(memory, "_l2", ()) or ()),
        "l3_node_count": len(getattr(memory, "_l3_nodes", {}) or {}),
        "l3_edge_count": len(getattr(memory, "_l3_edges", ()) or ()),
        "tick": int(getattr(memory, "_tick", 0) or 0),
    }


async def scoped_api_payload(
    plugin: object,
    authorization: ScopedApiAuthorization,
    endpoint: str,
) -> dict[str, object]:
    """Build the exact-scope public DTO without exporting private payloads."""

    payload = authorization.public_payload()
    scope = authorization.scope
    if endpoint == "state":
        host = None
        getter = getattr(plugin, "_host_for_scope", None)
        if callable(getter):
            try:
                host = getter(scope)
            except Exception:  # noqa: BLE001 - empty projection is fail closed
                host = None
        computation = getattr(getattr(host, "kernel", None), "computation", None)
        payload["state"] = {
            "tick_count": int(getattr(computation, "_tick_count", 0) or 0),
            "gate": _scoped_metric_map(_comp_gate_dict(computation)),
            "boundary": _scoped_metric_map(_comp_boundary_dict(computation)),
        }
    elif endpoint == "observation-history":
        payload["observation_history"] = _scoped_history_payload(plugin, authorization)
    elif endpoint == "diagnostics":
        host = None
        getter = getattr(plugin, "_host_for_scope", None)
        if callable(getter):
            try:
                host = getter(scope)
            except Exception:  # noqa: BLE001 - empty projection is fail closed
                host = None
        computation = getattr(getattr(host, "kernel", None), "computation", None)
        diagnostics = getattr(computation, "diagnostics", None)
        raw = diagnostics() if callable(diagnostics) else {}
        route_counts = raw.get("route_counts") if isinstance(raw, Mapping) else {}
        payload["diagnostics"] = {"route_counts": _scoped_route_counts(route_counts)}
    elif endpoint == "memory-pools":
        payload["memory_pools"] = _scoped_memory_pools(plugin, authorization)
    return payload


def issue_scoped_meltdown_nonce(
    plugin: object,
    authorization: ScopedApiAuthorization,
) -> str | ScopedApiError:
    """Use the plugin's established destructive nonce map for one exact scope."""

    nonces = getattr(plugin, "_meltdown_nonces", None)
    if not isinstance(nonces, dict):
        return ScopedApiError(503, "meltdown_unavailable")
    nonce = secrets.token_hex(16)
    nonces[authorization.scope.storage_token] = nonce
    return nonce


def consume_scoped_meltdown_nonce(
    plugin: object,
    authorization: ScopedApiAuthorization,
    candidate: object,
) -> ScopedApiError | None:
    """Consume the existing nonce keyed by the frozen storage owner only."""

    if type(candidate) is not str or not candidate:
        return ScopedApiError(400, "invalid_meltdown_nonce")
    nonces = getattr(plugin, "_meltdown_nonces", None)
    if not isinstance(nonces, dict):
        return ScopedApiError(503, "meltdown_unavailable")
    expected = nonces.get(authorization.scope.storage_token)
    if type(expected) is not str or not secrets.compare_digest(candidate, expected):
        return ScopedApiError(403, "token_mismatch")
    nonces.pop(authorization.scope.storage_token, None)
    return None


async def purge_scoped_memory(
    plugin: object,
    authorization: ScopedApiAuthorization,
) -> dict[str, object]:
    """Clear only the exact scope owner after an already-consumed nonce."""

    scope = authorization.scope
    memory = None
    memory_getter = getattr(plugin, "_memory_system_for_scope", None)
    if callable(memory_getter):
        try:
            memory = memory_getter(scope)
        except Exception:  # noqa: BLE001 - no sibling fallback is permitted
            memory = None
    if memory is not None:
        for name in ("_l1", "_l2", "_l3_nodes", "_l3_edges"):
            value = getattr(memory, name, None)
            clear = getattr(value, "clear", None)
            if callable(clear):
                clear()
        if hasattr(memory, "_tick"):
            memory._tick = 0
        if hasattr(memory, "_hydrated"):
            memory._hydrated = True
    host = None
    host_getter = getattr(plugin, "_host_for_scope", None)
    if callable(host_getter):
        try:
            host = host_getter(scope)
        except Exception:  # noqa: BLE001 - no sibling fallback is permitted
            host = None
    body_memory = getattr(getattr(getattr(host, "kernel", None), "body", None), "memory", None)
    if isinstance(body_memory, dict):
        body_memory["traces"] = []
        body_memory.pop("_memory_system", None)
    persistence = getattr(plugin, "_state_persistence", None)
    purge = getattr(persistence, "purge_session_after_meltdown", None)
    if callable(purge):
        result = purge(scope.storage_token)
        if inspect.isawaitable(result):
            await result
    amnesia = getattr(plugin, "_amnesia_sessions", None)
    if not isinstance(amnesia, set):
        amnesia = set()
        try:
            setattr(plugin, "_amnesia_sessions", amnesia)
        except Exception:  # noqa: BLE001 - immutable test facade
            pass
    amnesia.add(scope.storage_token)
    payload = authorization.public_payload()
    payload["cleared"] = True
    payload["status"] = "accepted"
    return payload


class WebUIRoutes:
    """封装所有 WebUI HTTP 路由处理器。

    通过 self._p 引用插件实例，访问 hosts/config/memory 等资源。
    所有 handler 方法都是 async，返回 dict 由 FastAPI 自动序列化为 JSON。
    """

    def __init__(self, plugin: PluginHost) -> None:
        self._p = plugin

    def _bound_webui_session_key(self, requested_session: str = "") -> str | None:
        """Resolve only the exact session already bound to this request context.

        The WebUI query string is not an authenticated ``SessionScope``.  Once
        scope runtime ownership is active, it must never select ``default``, an
        overview, or a sibling session merely because a raw string was supplied.
        """

        registry = getattr(self._p, "_scope_runtime_registry", None)
        if registry is None:
            return None
        binding_getter = getattr(self._p, "_bound_runtime", None)
        if not callable(binding_getter):
            return None
        try:
            binding = binding_getter()
        except Exception:  # noqa: BLE001 - HTTP reads must fail closed
            return None
        scope = getattr(binding, "scope", None)
        if scope is None or not registry.is_live_session(scope):
            return None
        storage_token = getattr(scope, "storage_token", None)
        if not isinstance(storage_token, str) or not storage_token:
            return None
        if requested_session and requested_session != storage_token:
            return None
        return storage_token

    def _webui_scope_gate(
        self, requested_session: str = ""
    ) -> tuple[bool, str | None]:
        """Return the exact permitted session for a scoped HTTP request.

        The boolean distinguishes normal registry-free compatibility from a
        scoped request that must fail closed.  Callers must return
        :meth:`_scope_unavailable_payload` before touching private state when
        ``scoped`` is true and ``session_key`` is ``None``.
        """

        if getattr(self._p, "_scope_runtime_registry", None) is None:
            return False, None
        return True, self._bound_webui_session_key(requested_session)

    @staticmethod
    def _scope_unavailable_payload() -> dict[str, Any]:
        return {"ok": False, "error": "scope_unavailable"}

    def _scoped_api_service(self):
        """Return the already-published shared scope gate, never create one."""

        return scoped_api_service_for_plugin(self._p)

    @staticmethod
    def _scoped_native_error(error: ScopedApiError) -> Any:
        """Preserve exact statuses where the AstrBot host exposes responses."""

        payload = error.public_payload()
        try:
            from astrbot.api.web import json_response
        except (ImportError, AttributeError):
            return {**payload, "status": error.status}
        for keyword in ("status", "status_code"):
            try:
                return json_response(payload, **{keyword: error.status})
            except TypeError:
                continue
        return {**payload, "status": error.status}

    async def scoped_api_handler(self, endpoint: str = "scope") -> Any:
        """Adapt an AstrBot request into the shared exact scoped API service."""

        from astrbot.api.web import request

        service = self._scoped_api_service()
        if service is None:
            return self._scoped_native_error(ScopedApiError(410, "scope_required"))
        query = getattr(request, "query", {})
        if isinstance(query, Mapping) and "session" in query:
            return self._scoped_native_error(
                ScopedApiError(400, "legacy_session_selector_forbidden")
            )
        params = getattr(request, "path_params", {})
        headers = getattr(request, "headers", {})
        try:
            scoped_request = ScopedApiRequest.from_tokens(
                bot_ref=params.get("bot_ref"),
                persona_ref=params.get("persona_ref"),
                session_ref=params.get("session_ref"),
                nonce=headers.get(SCOPE_NONCE_HEADER),
                endpoint=endpoint,
                method=getattr(request, "method", "GET"),
            )
        except (AttributeError, TypeError, ValueError):
            return self._scoped_native_error(ScopedApiError(400, "invalid_scoped_request"))
        authorization = service.authorize(scoped_request)
        if isinstance(authorization, ScopedApiError):
            return self._scoped_native_error(authorization)
        if not isinstance(authorization, ScopedApiAuthorization):
            return self._scoped_native_error(ScopedApiError(503, "scope_repository_unavailable"))
        if scoped_request.endpoint in {"stream", "ws"}:
            # AstrBot Pages stays serialized/polling; no unowned stream is opened.
            return self._scoped_native_error(ScopedApiError(410, "stream_unavailable"))
        if scoped_request.endpoint == "memory/meltdown-nonce":
            checked = service.revalidate(authorization)
            if isinstance(checked, ScopedApiError):
                return self._scoped_native_error(checked)
            meltdown_nonce = issue_scoped_meltdown_nonce(self._p, checked)
            if isinstance(meltdown_nonce, ScopedApiError):
                return self._scoped_native_error(meltdown_nonce)
            payload = checked.public_payload()
            payload["meltdown_nonce"] = meltdown_nonce
            return payload
        if scoped_request.endpoint == "memory/meltdown":
            try:
                body = await request.json()
            except Exception:  # noqa: BLE001 - malformed input is a client error
                body = None
            if type(body) is not dict or set(body) != {"meltdown_nonce"}:
                return self._scoped_native_error(ScopedApiError(400, "invalid_meltdown_request"))
            checked = service.revalidate(authorization)
            if isinstance(checked, ScopedApiError):
                return self._scoped_native_error(checked)
            nonce_error = consume_scoped_meltdown_nonce(
                self._p,
                checked,
                body.get("meltdown_nonce"),
            )
            if nonce_error is not None:
                return self._scoped_native_error(nonce_error)
            return await purge_scoped_memory(self._p, checked)
        return await scoped_api_payload(self._p, authorization, scoped_request.endpoint)

    async def scope_catalog_handler(self) -> Any:
        """Expose the redacted catalog used to choose a private API scope."""

        service = self._scoped_api_service()
        if service is None:
            return self._scoped_native_error(ScopedApiError(410, "scope_required"))
        result = service.catalog_payload()
        if isinstance(result, ScopedApiError):
            return self._scoped_native_error(result)
        return result

    async def persona_dossier_handler(self) -> Any:
        """Read one durable Persona projection without accepting a Session selector."""

        from astrbot.api.web import request

        service = self._scoped_api_service()
        if service is None:
            return self._scoped_native_error(ScopedApiError(410, "scope_required"))
        query = getattr(request, "query", {})
        if isinstance(query, Mapping) and "session" in query:
            return self._scoped_native_error(
                ScopedApiError(400, "legacy_session_selector_forbidden")
            )
        params = getattr(request, "path_params", {})
        try:
            result = service.persona_dossier_payload(
                params.get("bot_ref"),
                params.get("persona_ref"),
            )
        except AttributeError:
            return self._scoped_native_error(ScopedApiError(400, "invalid_persona_request"))
        if isinstance(result, ScopedApiError):
            return self._scoped_native_error(result)
        return result

    async def scope_bootstrap_handler(self) -> Any:
        """Mint a fresh one-use nonce for one live exact catalog entry."""

        from astrbot.api.web import request

        service = self._scoped_api_service()
        if service is None:
            return self._scoped_native_error(ScopedApiError(410, "scope_required"))
        query = getattr(request, "query", {})
        if isinstance(query, Mapping) and "session" in query:
            return self._scoped_native_error(
                ScopedApiError(400, "legacy_session_selector_forbidden")
            )
        params = getattr(request, "path_params", {})
        try:
            path = ScopeApiPathEcho(
                bot_ref=params.get("bot_ref"),
                persona_ref=params.get("persona_ref"),
                session_ref=params.get("session_ref"),
            )
        except (AttributeError, TypeError, ValueError):
            return self._scoped_native_error(ScopedApiError(400, "invalid_scoped_request"))
        nonce = service.bootstrap_nonce(path)
        if isinstance(nonce, ScopedApiError):
            return self._scoped_native_error(nonce)
        return {
            "ok": True,
            "scope": {
                "bot_ref": path.bot_ref,
                "persona_ref": path.persona_ref,
                "session_ref": path.session_ref,
            },
            "scope_nonce": nonce,
        }

    # ------------------------------------------------------------------
    # Memory settings & lineage observatory
    # ------------------------------------------------------------------

    async def memory_settings_get_handler(self) -> dict[str, Any]:
        return await self._p._sylanne_memory_settings_page_payload()

    async def memory_settings_post_handler(self) -> dict[str, Any]:
        from astrbot.api.web import request

        body = await request.json() or {}
        return await self._p._update_sylanne_memory_settings_from_page(body)

    async def lineage_observatory_handler(self) -> dict[str, Any]:
        return await self._p._lineage_observatory_handler()

    # ------------------------------------------------------------------
    # WebUI page & state
    # ------------------------------------------------------------------

    async def page_handler(self) -> Any:
        """Return the full WebUI HTML page."""
        from astrbot.api.web import file_response, stream_response

        # WEBUI_HTML is a module-level constant in main.py; access via plugin module
        import main as _main_mod

        dashboard_path = Path(self._plugin_dir) / "UI" / "index.html"
        if dashboard_path.exists():
            return file_response(
                dashboard_path, content_type="text/html; charset=utf-8"
            )
        html = getattr(_main_mod, "WEBUI_HTML", "<html><body>unavailable</body></html>")
        return stream_response(
            [html], content_type="text/html; charset=utf-8"
        )

    async def state_handler(self) -> dict[str, Any]:
        """返回完整状态 JSON，供 WebUI dashboard 渲染。

        包含：情感向量、门控统计、路由统计、边界状态、表达状态、
        计时数据、各层诊断、计算脊柱信息、人格信息、反馈统计等。
        支持 ?session= 参数指定会话，默认选择最活跃的会话。
        """
        logger.debug("Sylanne WebUI: /api/state handler HIT")
        from astrbot.api.web import request

        requested_session = str(request.query.get("session") or "").strip()
        scoped, scoped_session = self._webui_scope_gate(requested_session)
        if scoped:
            session_key = scoped_session
            if session_key is None:
                return self._scope_unavailable_payload()
            all_sessions = [session_key]
        else:
            # Registry-free compatibility only: historic WebUI state pages used
            # an overview/default selector and are exercised by narrow test stubs.
            all_sessions = self._p._known_webui_sessions(requested_session)
            if (
                not requested_session
                or requested_session == "default"
                or requested_session not in all_sessions
            ):
                # Find session with highest tick count (most active)
                best_session = "default"
                best_ticks = -1
                for sk, h in (getattr(self._p, "_hosts", {}) or {}).items():
                    ticks = getattr(h.kernel.computation, "_tick_count", 0)
                    if ticks > best_ticks:
                        best_ticks = ticks
                        best_session = sk
                session_key = (
                    best_session
                    if best_ticks > 0
                    else (all_sessions[0] if all_sessions else "default")
                )
            else:
                session_key = requested_session
        host = self._p._host(session_key)
        comp = host.kernel.computation
        logger.info(
            f"Sylanne WebUI state: session={session_key}, tick={comp._tick_count}, route={comp._last_route}"
        )

        # Emotion from Void-Scar Engine
        _EMOTION_DEFAULTS = {
            "warmth": 0.0,
            "arousal": 0.0,
            "valence": 0.0,
            "tension": 0.0,
            "curiosity": 0.0,
            "repair_pressure": 0.0,
            "expression_drive": 0.0,
            "boundary_firmness": 0.0,
            "coherence": 1.0,
        }
        emotion = {**_EMOTION_DEFAULTS, **comp.engine.observe()}

        # Gate stats（共振场 gate 为私有 _gate，兼容取）
        gate_dict = _comp_gate_dict(comp)
        history = gate_dict.get("history", [])
        gate_info = {
            "precision": round(gate_dict.get("precision", 0.0), 4),
            "mean_surprise": round(gate_dict.get("mean_surprise", 0.0), 4),
            "threshold": round(gate_dict.get("threshold", 0.5), 4),
            "route": str(getattr(comp, "_last_route", "") or "resonance").upper(),
            "history_len": gate_dict.get("history_len", 0),
            "history": history[-60:] if isinstance(history, list) else [],
        }

        route_stats, route_distribution = _comp_route_stats(comp, history)

        # Void-Scar state as memory equivalent
        engine_diag = comp.engine.diagnostics()
        _void_info = engine_diag.get("void", {})
        _mem_info = {
            "size": int(emotion.get("active_voids", 0)),
            "connectivity": comp.engine._coherence,
            "holes_count": int(emotion.get("active_voids", 0)),
            "ghost_count": int(emotion.get("ghost_count", 0)),
        }
        comp_result = getattr(host.kernel, "_last_computation_result", None) or {}
        layers = comp_result.get("layers", {})
        if not isinstance(layers, dict):
            layers = {}
        recalled_items = comp_result.get("recalled", [])
        _recent_recall = [
            str(r.get("text", ""))[:60] for r in recalled_items if isinstance(r, dict)
        ]

        # Boundary（共振场 boundary 为私有 _boundary，兼容取）
        boundary_dict = _comp_boundary_dict(comp)
        boundary_info = {
            "integrity": round(boundary_dict.get("integrity", 1.0), 4),
            "entropy": round(boundary_dict.get("entropy", 0.0), 4),
            "stability": round(boundary_dict.get("stability", 1.0), 4),
            "phase_transitions": boundary_dict.get("phase_transitions", 0),
        }

        # Expression
        expr_state = comp.expression.state()
        expr_info = {
            "pressure": round(expr_state.get("pressure", 0.0), 4),
            "threshold": round(expr_state.get("threshold", 0.6), 4),
            "ratio": round(
                expr_state.get("pressure", 0.0)
                / max(0.01, expr_state.get("threshold", 0.6)),
                4,
            ),
            "mode": expr_state.get("mode", "silent"),
            "count": expr_state.get("count", 0),
        }

        # Timing (convert ns to ms for WebUI display)（共振场无 timing_stats→空）
        timing_raw = comp.timing_stats() if hasattr(comp, "timing_stats") else {}
        timing: dict[str, Any] = {}
        total_ms = 0.0
        for layer_name, layer_stats in timing_raw.items():
            ms_val = round(layer_stats.get("p50_ns", 0.0) / 1_000_000, 3)
            timing[f"{layer_name}_ms"] = ms_val
            total_ms += ms_val
        timing["total_ms"] = round(total_ms, 3)

        # Ensure L1_HDC layer always has sample_bits for frontend visualization
        sample_bits = list(
            (comp.last_hdc_sample if hasattr(comp, "last_hdc_sample") else None)
            or []
        )
        if "L1_HDC" not in layers:
            layers["L1_HDC"] = {
                "vector_dim": 2048,
                "density": sum(sample_bits) / max(len(sample_bits), 1)
                if sample_bits
                else 0.0,
                "sample_bits": sample_bits,
            }
        elif "sample_bits" not in layers["L1_HDC"]:
            layers["L1_HDC"]["sample_bits"] = sample_bits
            layers["L1_HDC"].setdefault("vector_dim", 2048)
            layers["L1_HDC"].setdefault(
                "density",
                sum(sample_bits) / max(len(sample_bits), 1) if sample_bits else 0.0,
            )

        # Feedback (from SSM diagnostics or computation diagnostics)
        comp_diag = comp.diagnostics()
        feedback_raw = comp_diag.get("feedback", {})
        if not feedback_raw:
            # Try to derive from body diagnostics
            surface = host.kernel.surface()
            diag = surface.get("diagnostics", {})
            feedback_raw = diag.get("feedback", {})
        feedback = {
            "accepted": int(feedback_raw.get("accepted", 0)),
            "ignored": int(feedback_raw.get("ignored", 0)),
            "rejected": int(feedback_raw.get("rejected", 0)),
        }
        spine_info = {
            "surprise": round(
                float(comp_result.get("surprise", gate_info["mean_surprise"]) or 0.0), 4
            ),
            "route": str(comp_result.get("route", "")),
            "last_text": str(comp_result.get("text", ""))[:120],
            "sheaf": comp_result.get("sheaf", {}),
            "hgt_decision": comp_result.get("hgt_decision", []),
            "boundary": boundary_info,
            "expression": expr_info,
            "layers": layers,
        }
        personality = (
            host.kernel._personality() if hasattr(host.kernel, "_personality") else {}
        )
        persona_info = {
            "profile": self._p._persona_profile(None),
            "traits": personality.get(
                "traits", personality if isinstance(personality, dict) else {}
            ),
            "voice": personality.get("voice", {})
            if isinstance(personality, dict)
            else {},
            "drift": personality.get("drift", {})
            if isinstance(personality, dict)
            else {},
        }

        return {
            "schema_version": "sylanne.webui.state.v2",
            "runtime": self._p._webui_runtime_info(),
            "current_session": session_key,
            "session_id": session_key,
            "emotion": {k: round(v, 4) for k, v in emotion.items()},
            "gate": gate_info,
            "route_stats": route_stats,
            "route_distribution": route_distribution,
            "boundary": boundary_info,
            "expression": expr_info,
            "timing": timing,
            "layers": layers,
            "spine": spine_info,
            "persona": persona_info,
            "personality": self._frontend_personality(personality),
            "spine_layers": self._frontend_spine_layers(comp),
            "theme": {"base": "#F3A7C8", "source": "emotion", "mode": "soft"},
            "feedback": feedback,
            "sessions": (
                [
                    {
                        "id": session_key,
                        "name": session_key,
                        "tick_count": int(getattr(comp, "_tick_count", 0) or 0),
                    }
                ]
                if scoped
                else _webui_session_items(self._p, all_sessions)
            ),
            "life_simulation": self._p._life_simulator.to_dict(),
        }

    async def observation_history_handler(self) -> dict[str, Any]:
        """Return persisted, numeric-only observation history."""

        from astrbot.api.web import request

        requested_session = str(request.query.get("session") or "").strip()
        scoped, scoped_session = self._webui_scope_gate(requested_session)
        if scoped:
            if scoped_session is None:
                return self._scope_unavailable_payload()
            query: Mapping[str, Any] = dict(request.query)
            query["session"] = scoped_session
        else:
            query = request.query
        try:
            return build_observation_history_payload(self._p, query)
        except (RuntimeError, ValueError) as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Settings handlers
    # ------------------------------------------------------------------

    async def settings_get_handler(self) -> dict[str, Any]:
        """返回当前配置值和 schema，供设置面板渲染表单控件。"""
        schema = self._p._load_conf_schema()
        values = {}
        for key in schema:
            raw = self._p._config.get(key, schema[key].get("default"))
            # 敏感字段(cookie/token/密钥…)不明文下发到设置面板;有值则以哨兵替代。
            if self._is_sensitive_key(key) and raw:
                values[key] = self._MASKED_VALUE
            else:
                values[key] = raw
        providers = await self.provider_items()
        return {
            "schema": schema,
            "values": values,
            "providers": providers,
            "model_routing": self._model_routing_payload(schema, providers),
        }

    def _model_routing_payload(
        self,
        schema: dict[str, Any],
        providers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return build_model_routing_payload(self._p._config, schema, providers)

    async def provider_items(self) -> list[dict[str, Any]]:
        """尽力获取 AstrBot 已注册的 LLM/Embedding provider 列表，供设置面板下拉选择。"""
        context = getattr(self._p, "context", None)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        def _add(provider: Any, provider_type: str = "") -> None:
            config = getattr(provider, "provider_config", None)
            if not isinstance(config, dict):
                config = {}
            provider_id = str(
                config.get("id")
                or config.get("provider_id")
                or getattr(provider, "provider_id", "")
                or getattr(provider, "id", "")
                or "",
            ).strip()
            if not provider_id or provider_id in seen:
                return
            seen.add(provider_id)
            items.append(
                {
                    "id": provider_id,
                    "name": str(
                        config.get("name")
                        or config.get("display_name")
                        or getattr(provider, "name", "")
                        or provider_id
                    ),
                    "type": str(
                        provider_type
                        or config.get("provider_type")
                        or getattr(provider, "provider_type", "")
                        or ""
                    ),
                }
            )

        # Specific registries first: a generic registry may contain both kinds,
        # and deduplication must not accidentally relabel an embedding model as LLM.
        for method_name, provider_type in (
            ("get_all_embedding_providers", "embedding"),
            ("get_all_llm_providers", "llm"),
            ("get_all_providers", ""),
        ):
            getter = getattr(context, method_name, None)
            if not callable(getter):
                continue
            try:
                providers = getter()
                if hasattr(providers, "__await__"):
                    providers = await providers
            except Exception:
                continue
            iterable = (
                providers.values() if isinstance(providers, dict) else (providers or [])
            )
            for provider in iterable:
                _add(provider, provider_type)
        return items

    async def settings_post_handler(self) -> dict[str, Any]:
        """接收设置面板提交的配置更新，按 schema 做类型强转后持久化。"""
        from astrbot.api.web import request

        body = await request.json() or {}
        schema = self._p._load_conf_schema()
        updated: list[str] = []
        for key, value in body.items():
            if key not in schema:
                continue
            # 面板回传脱敏哨兵 = 用户未改动该敏感字段;跳过,绝不用 "***" 覆盖真凭据。
            if self._is_sensitive_key(key) and value == self._MASKED_VALUE:
                continue
            meta = schema[key]
            # Type coercion
            if meta.get("type") == "bool":
                value = bool(value)
            elif meta.get("type") == "int":
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    continue
            elif meta.get("type") == "float":
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    continue
            else:
                value = str(value)
            self._p._config[key] = value
            updated.append(key)
        # Persist if possible
        config = self._p.config if hasattr(self._p, "config") else self._p._config
        if isinstance(config, dict):
            for key in updated:
                config[key] = self._p._config[key]
        if hasattr(config, "save_config"):
            config.save_config()
        self._p._start_webui_if_enabled()
        return {"ok": True, "updated": updated}

    # ------------------------------------------------------------------
    # Computation logs
    # ------------------------------------------------------------------

    async def computation_logs_handler(self) -> dict[str, Any]:
        """返回最近的计算日志条目，支持 ?limit= 和 ?session= 过滤。"""
        from astrbot.api.web import request

        try:
            limit = max(1, min(200, int(request.query.get("limit", "50"))))
        except (TypeError, ValueError):
            limit = 50
        requested_session = str(request.query.get("session") or "").strip()
        scoped, scoped_session = self._webui_scope_gate(requested_session)
        if scoped:
            if scoped_session is None:
                return self._scope_unavailable_payload()
            requested_session = scoped_session
        logs = list(self._p._computation_logs)
        if requested_session:
            logs = [
                entry
                for entry in logs
                if str(entry.get("session", "")) == requested_session
            ]
        entries = logs[-limit:]
        return {
            "logs": entries,
            "total": len(logs) if scoped else len(self._p._computation_logs),
            "total_for_session": len(logs),
            "session": requested_session or "",
        }

    # ------------------------------------------------------------------
    # Memory pools
    # ------------------------------------------------------------------

    async def memory_pools_handler(self) -> dict[str, Any]:
        """返回三层记忆池数据（L1 Hot / L2 Warm / L3 Cold Graph）。

        支持跨会话聚合（overview 模式）或单会话查看。
        自动适配新版 MemorySystem 三层架构和旧版 body.memory.traces。
        """
        from astrbot.api.web import request

        def _bounded_limit(raw: Any) -> int:
            try:
                return max(1, min(100, int(raw)))
            except (TypeError, ValueError):
                return 50

        def _temperature(record_data: dict[str, Any]) -> float:
            signature = record_data.get("emotional_signature") or {}
            if not isinstance(signature, dict):
                return 0.5
            arousal = abs(
                float(signature.get("arousal", signature.get("tension", 0.35)) or 0.35)
            )
            warmth = abs(
                float(signature.get("warmth", signature.get("valence", 0.45)) or 0.45)
            )
            return round(max(0.0, min(1.0, (arousal + warmth) / 2.0)), 4)

        def _weight(record_data: dict[str, Any]) -> float:
            depth = float(record_data.get("depth", 0.0) or 0.0)
            confidence = float(record_data.get("confidence", 0.35) or 0.35)
            recall = min(1.0, float(record_data.get("recall_count", 0) or 0) / 5.0)
            evidence = min(1.0, float(record_data.get("evidence_count", 1) or 1) / 4.0)
            interference = float(record_data.get("interference", 0.0) or 0.0)
            value = (
                depth * 0.45
                + confidence * 0.25
                + recall * 0.20
                + evidence * 0.10
                - interference * 0.15
            )
            return round(max(0.0, min(1.0, value)), 4)

        def _payload(record: Any) -> dict[str, Any]:
            data = (
                record.to_dict() if hasattr(record, "to_dict") else dict(record or {})
            )
            data["weight"] = _weight(data)
            data["temperature"] = _temperature(data)
            data["has_embedding"] = bool(
                data.get("embedding")
                or data.get("semantic_embedding")
                or data.get("embedding_provider_id")
            )
            data.pop("embedding", None)
            data.pop("semantic_embedding", None)
            return data

        def _has_memory_content(state: Any) -> bool:
            if state is None:
                return False
            if (
                hasattr(state, "_l1")
                or hasattr(state, "_l2")
                or hasattr(state, "_l3_nodes")
            ):
                return bool(
                    list(getattr(state, "_l1", []) or [])
                    or list(getattr(state, "_l2", []) or [])
                    or dict(getattr(state, "_l3_nodes", {}) or {})
                    or list(getattr(state, "_l3_edges", []) or [])
                )
            return bool(list(getattr(state, "records", []) or []))

        limit = _bounded_limit(request.query.get("limit", "50"))
        requested_session = str(request.query.get("session") or "").strip()
        scoped, scoped_session = self._webui_scope_gate(requested_session)
        if scoped:
            session_key = scoped_session
            if session_key is None:
                return self._scope_unavailable_payload()
            all_sessions = [session_key]
            overview_requested = False
            source_sessions = [session_key]
        else:
            # Registry-free compatibility only: the legacy overview endpoint may
            # aggregate already-known sessions, but scoped runtime never does.
            session_key = requested_session
            all_sessions = self._p._known_webui_sessions(session_key)
            overview_requested = not session_key or session_key == "default"
            if session_key and session_key not in all_sessions:
                all_sessions.append(session_key)
            if not session_key or (
                session_key not in all_sessions and session_key != "default"
            ):
                session_key = all_sessions[0] if all_sessions else "default"
            source_sessions = (
                [item for item in all_sessions if item]
                if overview_requested
                else [session_key]
            )
            if not source_sessions:
                source_sessions = [session_key or "default"]

        state = await self._p._load_sylanne_memory_state(session_key)

        # Fallback to the live 3-layer MemorySystem if KV state is unavailable
        if state is None:
            state = self._p._memory_system_for_session(session_key)

        def _memory_item_payload(item: Any) -> dict[str, Any]:
            data = item.to_dict() if hasattr(item, "to_dict") else dict(item or {})
            data["weight"] = round(
                max(0.0, min(1.0, float(data.get("weight", 0.0) or 0.0))), 4
            )
            data["temperature"] = round(
                max(0.0, min(1.0, float(data.get("temperature", 0.5) or 0.5))), 4
            )
            data["has_embedding"] = bool(
                data.get("embedding")
                or data.get("semantic_embedding")
                or data.get("embedding_provider_id")
            )
            data.setdefault("recall_reason", "")
            data.pop("embedding", None)
            data.pop("semantic_embedding", None)
            return data

        def _graph_node_payload(node: Any) -> dict[str, Any]:
            data = node.to_dict() if hasattr(node, "to_dict") else dict(node or {})
            clarity = float(data.get("clarity", data.get("weight", 0.0)) or 0.0)
            emotion_weight = float(
                data.get("emotion_weight", data.get("temperature", 0.0)) or 0.0
            )
            data["summary"] = data.get(
                "label", data.get("summary", data.get("text", ""))
            )
            data["text"] = (
                data.get("text")
                or f"{data.get('type', 'node')} / {data.get('temporal_type', 'episodic')}"
            )
            data["weight"] = round(max(0.0, min(1.0, clarity)), 4)
            data["temperature"] = round(
                max(0.0, min(1.0, (emotion_weight + 1.0) / 2.0)), 4
            )
            data["has_embedding"] = False
            return data

        # Duplicated in webui_server.py for standalone mode
        def _legacy_trace_payload(trace: Any, source_session: str) -> dict[str, Any]:
            data = (
                dict(trace or {})
                if isinstance(trace, dict)
                else {"text": str(trace or "")}
            )
            weight = float(data.get("weight", data.get("depth", 0.35)) or 0.35)
            temperature = float(data.get("temperature", data.get("warmth", 0.5)) or 0.5)
            data["session"] = source_session
            data["source"] = data.get("source") or "body.memory.traces"
            data["weight"] = round(max(0.0, min(1.0, weight)), 4)
            data["temperature"] = round(max(0.0, min(1.0, temperature)), 4)
            data["created_at"] = float(
                data.get("created_at", data.get("updated_at", 0.0)) or 0.0
            )
            data["has_embedding"] = bool(
                data.get("embedding")
                or data.get("semantic_embedding")
                or data.get("embedding_provider_id")
            )
            data.pop("embedding", None)
            data.pop("semantic_embedding", None)
            return data

        async def _state_for_display(source_session: str) -> Any:
            loaded = await self._p._load_sylanne_memory_state(source_session)
            if loaded is not None:
                return loaded
            return self._p._memory_system_for_session(source_session)

        # Duplicated in webui_server.py for standalone mode
        def _body_traces_for_session(source_session: str) -> list[dict[str, Any]]:
            traces: list[dict[str, Any]] = []
            try:
                host = self._p._host(source_session)
                raw_traces = host.kernel.body.memory.get("traces", [])
            except Exception:
                raw_traces = []
            for trace in list(raw_traces or []):
                traces.append(_legacy_trace_payload(trace, source_session))
            return traces

        l1_items: list[dict[str, Any]] = []
        l2_items: list[dict[str, Any]] = []
        l3_nodes: list[dict[str, Any]] = []
        l3_edges: list[dict[str, Any]] = []
        raw_l1_count = 0
        raw_l2_count = 0
        raw_l3_node_count = 0
        raw_l3_edge_count = 0
        legacy_hot: list[dict[str, Any]] = []
        legacy_warm: list[dict[str, Any]] = []

        for source_session in source_sessions:
            source_state = await _state_for_display(source_session)
            if source_state is not None and (
                hasattr(source_state, "_l1")
                or hasattr(source_state, "_l2")
                or hasattr(source_state, "_l3_nodes")
            ):
                source_l1 = [
                    _memory_item_payload(item)
                    for item in list(getattr(source_state, "_l1", []) or [])
                ]
                source_l2 = [
                    _memory_item_payload(item)
                    for item in list(getattr(source_state, "_l2", []) or [])
                ]
                source_l3_nodes_raw = getattr(source_state, "_l3_nodes", {}) or {}
                source_l3_edges_raw = getattr(source_state, "_l3_edges", []) or []
                for item in source_l1 + source_l2:
                    item.setdefault("session", source_session)
                source_l3_nodes = [
                    _graph_node_payload(node)
                    for node in list(source_l3_nodes_raw.values())
                ]
                for node in source_l3_nodes:
                    node.setdefault("session", source_session)
                source_l3_edges = [
                    edge.to_dict() if hasattr(edge, "to_dict") else dict(edge or {})
                    for edge in list(source_l3_edges_raw)
                ]
                for edge in source_l3_edges:
                    edge.setdefault("session", source_session)
                l1_items.extend(source_l1)
                l2_items.extend(source_l2)
                l3_nodes.extend(source_l3_nodes)
                l3_edges.extend(source_l3_edges)
                raw_l1_count += len(getattr(source_state, "_l1", []) or [])
                raw_l2_count += len(getattr(source_state, "_l2", []) or [])
                raw_l3_node_count += len(source_l3_nodes_raw)
                raw_l3_edge_count += len(source_l3_edges_raw)
                if _has_memory_content(source_state):
                    continue

            traces = _body_traces_for_session(source_session)
            legacy_hot.extend(traces)
            legacy_warm.extend(
                item for item in traces if float(item.get("weight", 0.0) or 0.0) >= 0.5
            )

        if l1_items or l2_items or l3_nodes or legacy_hot:
            if legacy_hot:
                l1_items.extend(legacy_hot)
                l2_items.extend(legacy_warm)
                raw_l1_count += len(legacy_hot)
                raw_l2_count += len(legacy_warm)
            l1_items = sorted(
                l1_items,
                key=lambda item: float(item.get("created_at", 0.0) or 0.0),
                reverse=True,
            )[:limit]
            l2_items = sorted(
                l2_items,
                key=lambda item: (
                    float(item.get("weight", 0.0) or 0.0),
                    float(item.get("created_at", 0.0) or 0.0),
                ),
                reverse=True,
            )[:limit]
            l3_nodes = sorted(
                l3_nodes,
                key=lambda item: float(item.get("weight", 0.0) or 0.0),
                reverse=True,
            )[:limit]
            l3_edges = l3_edges[:limit]
            records = l1_items + l2_items + l3_nodes
            total = len(records)
            summary = {
                "total": total,
                "l1_count": raw_l1_count,
                "l2_count": raw_l2_count,
                "l3_node_count": raw_l3_node_count,
                "l3_edge_count": raw_l3_edge_count,
                "legacy_trace_count": len(legacy_hot),
                "embedded": sum(
                    1 for item in l1_items + l2_items if item.get("has_embedding")
                ),
                "avg_weight": round(
                    sum(float(item.get("weight", 0.0) or 0.0) for item in records)
                    / total,
                    4,
                )
                if total
                else 0.0,
                "avg_temperature": round(
                    sum(float(item.get("temperature", 0.0) or 0.0) for item in records)
                    / total,
                    4,
                )
                if total
                else 0.5,
            }
            return {
                "schema_version": "sylanne.webui.memory.v1",
                "architecture": "sylanne_alpha.memory_system.three_layer",
                "session": "default" if overview_requested else session_key,
                "mode": "overview" if overview_requested else "session",
                "sessions": source_sessions,
                "layers": {
                    "l1_hot": {
                        "label": "L1 Hot Pool",
                        "count": summary["l1_count"],
                        "capacity": 50,
                        "items": l1_items,
                    },
                    "l2_warm": {
                        "label": "L2 Warm Pool",
                        "count": summary["l2_count"],
                        "items": l2_items,
                    },
                    "l3_cold": {
                        "label": "L3 Cold Graph",
                        "count": summary["l3_node_count"],
                        "edge_count": summary["l3_edge_count"],
                        "nodes": l3_nodes,
                        "edges": l3_edges,
                    },
                },
                "hot": l1_items,
                "warm": l2_items,
                "cold": l3_nodes,
                "summary": summary,
            }

        records = [
            _payload(record) for record in list(getattr(state, "records", []) or [])
        ]
        hot = sorted(
            records,
            key=lambda item: float(item.get("created_at", 0.0) or 0.0),
            reverse=True,
        )[:limit]
        warm = sorted(
            (
                item
                for item in records
                if float(item.get("weight", 0.0) or 0.0) >= 0.5
                or int(item.get("recall_count", 0) or 0) > 0
            ),
            key=lambda item: (
                float(item.get("weight", 0.0) or 0.0),
                float(item.get("updated_at", 0.0) or 0.0),
            ),
            reverse=True,
        )[:limit]
        total = len(records)
        summary = {
            "total": total,
            "l1_count": len(hot),
            "l2_count": len(warm),
            "l3_node_count": 0,
            "l3_edge_count": 0,
            "embedded": sum(1 for item in records if item.get("has_embedding")),
            "avg_weight": round(
                sum(float(item.get("weight", 0.0) or 0.0) for item in records) / total,
                4,
            )
            if total
            else 0.0,
            "avg_temperature": round(
                sum(float(item.get("temperature", 0.0) or 0.0) for item in records)
                / total,
                4,
            )
            if total
            else 0.5,
        }
        return {
            "schema_version": "sylanne.webui.memory.v1",
            "architecture": "legacy.sylanne_memory_state.compat",
            "session": session_key,
            "layers": {
                "l1_hot": {
                    "label": "L1 Hot Pool",
                    "count": len(hot),
                    "capacity": 50,
                    "items": hot,
                },
                "l2_warm": {"label": "L2 Warm Pool", "count": len(warm), "items": warm},
                "l3_cold": {
                    "label": "L3 Cold Graph",
                    "count": 0,
                    "edge_count": 0,
                    "nodes": [],
                    "edges": [],
                },
            },
            "hot": hot,
            "warm": warm,
            "cold": [],
            "long_term": warm,
            "summary": summary,
        }

    # ------------------------------------------------------------------
    # Memory meltdown
    # ------------------------------------------------------------------

    async def memory_meltdown_handler(self) -> dict[str, Any]:
        """清除指定会话的所有记忆池。需要 token 验证（仅服务端 nonce）。"""
        from astrbot.api.web import request

        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            return {"ok": False, "error": "invalid_body"}
        session = str(body.get("session", "")).strip()
        nonce = str(body.get("nonce", "") or body.get("token", "")).strip()
        scoped, _scoped_session = self._webui_scope_gate(session)
        if scoped:
            # HTTP input names only a raw session string.  Until the WebUI has an
            # authenticated SessionScope resolver it must not mutate a private
            # session owner (including its one-shot amnesia flag).
            return self._scope_unavailable_payload()
        # S4 fix: validate ONLY against server-side stored nonce — never trust
        # client-supplied expected_token (allows trivial bypass).
        server_nonce = getattr(self._p, "_meltdown_nonces", {}).get(session, "")
        if not server_nonce or not nonce or nonce != server_nonce:
            return {"ok": False, "error": "token_mismatch"}
        # Consume the nonce (single-use)
        self._p._meltdown_nonces.pop(session, None)
        # Clear memory for the session
        mem_sys = (
            self._p._memory_system_for_session(session)
            if hasattr(self._p, "_memory_system_for_session")
            else getattr(self._p, "_memory_system", None)
        )
        if mem_sys:
            mem_sys._l1.clear()
            mem_sys._l2.clear()
            mem_sys._l3_nodes.clear()
            mem_sys._l3_edges.clear()
            mem_sys._tick = 0
            # MEM-02②/①: 显式擦除是唯一允许"空对象覆盖 KV"的路径——标记为已补水，
            # 使 save_sylanne_memory_state 的空对象保护闸门不拦这次之后的写入；
            # 同时若一次尚未完成的后台补水任务此刻正好读完 KV 准备合并，它会在
            # merge 前重新检查 _hydrated 并发现已被这里设为 True，从而放弃合并，
            # 避免把刚清除的记忆从 KV 旧档里复活回来。
            mem_sys._hydrated = True
        # Also clear legacy body traces
        hosts = getattr(self._p, "_hosts", {}) or {}
        if session in hosts:
            hosts[session].kernel.body.memory["traces"] = []
            hosts[session].kernel.body.memory.pop("_memory_system", None)
        sp = getattr(self._p, "_state_persistence", None)
        if sp is not None and hasattr(sp, "purge_session_after_meltdown"):
            await sp.purge_session_after_meltdown(session)
        logger.info(f"Sylanne MEMORY MELTDOWN: session={session} — all memory cleared")
        # Registry-free legacy path: retain the historical raw-key cue for test
        # doubles.  The scoped path returned above rather than selecting a session.
        if not hasattr(self._p, "_amnesia_sessions"):
            self._p._amnesia_sessions: set[str] = set()
        self._p._amnesia_sessions.add(session)
        return {"ok": True, "session": session, "cleared": True}

    def generate_meltdown_nonce(self, session: str) -> str:
        """生成一次性 nonce 用于记忆清除确认，防止 CSRF。"""
        nonce = secrets.token_hex(16)
        self._p._meltdown_nonces[session] = nonce
        return nonce

    async def meltdown_nonce_handler(self) -> dict[str, Any]:
        """GET /api/meltdown_nonce — 生成并返回一次性 nonce。"""
        from astrbot.api.web import request

        session = str(request.query.get("session") or "").strip()
        scoped, _scoped_session = self._webui_scope_gate(session)
        if scoped:
            # Nonces are a legacy process-global map; do not recreate that owner
            # from a raw HTTP session string while scoped runtime is active.
            return self._scope_unavailable_payload()
        nonce = self.generate_meltdown_nonce(session)
        return {"nonce": nonce}

    # ------------------------------------------------------------------
    # Memory sink (L1→L2 手动下沉)
    # ------------------------------------------------------------------

    async def memory_consolidate_handler(self) -> dict[str, Any]:
        """POST /api/memory_consolidate — 触发一次后台 consolidation 评估。

        异步启动 LLM 评估流程，立即返回预估时间。
        评估完成后 consolidation_candidates() 会有已确认条目可供下沉。
        """
        from astrbot.api.web import request

        body = await request.json() or {}
        session = str(body.get("session", "")).strip()
        if not session:
            return {"ok": False, "error": "missing session param"}
        scoped, scoped_session = self._webui_scope_gate(session)
        if scoped:
            if scoped_session is None:
                return self._scope_unavailable_payload()
            session = scoped_session
        try:
            plugin = self._p
            mem_sys = (
                plugin._memory_system_for_session(session)
                if hasattr(plugin, "_memory_system_for_session")
                else getattr(plugin, "_memory_system", None)
            )
            if mem_sys is None or not list(mem_sys._l1):
                return {"ok": True, "estimated_seconds": 0}
            asyncio.ensure_future(plugin._trigger_consolidation(session))
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "estimated_seconds": 30}

    async def memory_sink_handler(self) -> dict[str, Any]:
        """GET /api/memory_sink — 手动触发 L1→L2 记忆下沉。

        将 L1 中已确认（confirmed）的条目批量下沉到 L2 温池。
        前端可通过此接口在不等待 12h 定时整理的情况下立即执行下沉操作。

        Query params:
            session: 目标会话 ID

        Returns:
            {"ok": true, "sunk": <下沉条目数>}
            {"ok": false, "error": "..."}  — 无可下沉条目或会话无效时
        """
        from astrbot.api.web import request

        session = str(request.query.get("session") or "").strip()
        if not session:
            return {"ok": False, "error": "missing session param"}
        scoped, scoped_session = self._webui_scope_gate(session)
        if scoped:
            if scoped_session is None:
                return self._scope_unavailable_payload()
            session = scoped_session

        # 获取该会话的记忆系统实例
        mem_sys = (
            self._p._memory_system_for_session(session)
            if hasattr(self._p, "_memory_system_for_session")
            else getattr(self._p, "_memory_system", None)
        )
        if mem_sys is None:
            return {"ok": False, "error": "memory system unavailable"}

        # 只下沉已确认的条目（不再强制下沉全部 L1）
        candidates = mem_sys.consolidation_candidates()
        if not candidates:
            return {"ok": False, "error": "no_confirmed_items", "sunk": 0}

        # 执行下沉：将条目从 L1 移入 L2
        item_ids = [item.id for item in candidates]
        mem_sys.sink_to_l2(item_ids)

        logger.info(
            f"Sylanne MEMORY SINK: session={session}, sunk={len(item_ids)} items L1→L2"
        )
        return {"ok": True, "sunk": len(item_ids)}

    # ------------------------------------------------------------------
    # Phase 4：生活观测面板（AstrBot 端镜像 webui_server 的 /api/life/* 接口）
    # ------------------------------------------------------------------

    async def life_status_handler(self) -> dict[str, Any]:
        """GET /api/life/status — 只读生活状态概览（节律/活动/最近事件/分布/prompt 预览）。"""
        scoped, scoped_session = self._webui_scope_gate()
        if scoped and scoped_session is None:
            return self._scope_unavailable_payload()
        life_sim = getattr(self._p, "_life_simulator", None)
        if life_sim is None:
            return {"enabled": False, "available": False}
        try:
            state = life_sim.state
            recent = list(state.events[-8:])
            source_dist: dict[str, int] = {}
            privacy_dist: dict[str, int] = {}
            for e in state.events:
                src = e.source or "unknown"
                priv = getattr(e, "privacy_level", "") or "unknown"
                source_dist[src] = source_dist.get(src, 0) + 1
                privacy_dist[priv] = privacy_dist.get(priv, 0) + 1
            seconds_since_tick = (
                round(time.time() - state.world.last_tick_at, 1)
                if state.world.last_tick_at
                else None
            )
            seconds_since_outreach = (
                round(time.time() - state.last_outreach_time, 1)
                if state.last_outreach_time
                else None
            )
            return {
                "available": True,
                "enabled": bool(life_sim.enabled),
                "schema_version": getattr(state.world, "schema_version", None),
                "world": {
                    "phase": state.world.phase,
                    "local_date": state.world.local_date,
                    "energy": round(state.world.energy, 3),
                    "focus": round(state.world.focus, 3),
                    "current_activity_id": state.world.current_activity_id,
                    "last_tick_at": state.world.last_tick_at,
                    "seconds_since_tick": seconds_since_tick,
                },
                "current_activity": state.current_activity,
                "counts": {
                    "simulation_count": state.simulation_count,
                    "outreach_count": state.outreach_count,
                    "events_total": len(state.events),
                },
                "timing": {
                    "last_simulation_time": state.last_simulation_time,
                    "last_outreach_time": state.last_outreach_time,
                    "seconds_since_outreach": seconds_since_outreach,
                },
                "recent_events": [
                    {
                        "event_id": e.event_id,
                        "ts": e.timestamp,
                        "text": e.text,
                        "mood": e.mood,
                        "event_type": e.event_type,
                        "source": e.source,
                        "privacy_level": getattr(e, "privacy_level", ""),
                        "importance": round(e.importance, 3),
                        "wants_to_share": e.wants_to_share,
                        "shared": e.shared,
                    }
                    for e in recent
                ],
                "distribution": {"source": source_dist, "privacy": privacy_dist},
                "prompt_fragment_preview": (
                    life_sim.life_prompt_fragment(limit=3) or ""
                )[:300],
            }
        except Exception as e:
            return {"available": True, "error": f"{type(e).__name__}: {e}"}

    async def life_events_handler(self) -> dict[str, Any]:
        """GET /api/life/events — 最近 20 条生活事件（含归属字段）。"""
        scoped, scoped_session = self._webui_scope_gate()
        if scoped and scoped_session is None:
            return self._scope_unavailable_payload()
        life_sim = getattr(self._p, "_life_simulator", None)
        if life_sim is None:
            return {"events": [], "available": False}
        try:
            events: list[dict[str, Any]] = []
            for ev in list(life_sim.state.events[-20:]):
                events.append(
                    {
                        "event_id": getattr(ev, "event_id", "") or "",
                        "text": getattr(ev, "text", "") or "",
                        "event_type": getattr(ev, "event_type", "") or "",
                        "timestamp": float(getattr(ev, "timestamp", 0.0) or 0.0),
                        "source": getattr(ev, "source", "") or "",
                        "importance": round(
                            float(getattr(ev, "importance", 0.5) or 0.0), 3
                        ),
                        "wants_to_share": bool(getattr(ev, "wants_to_share", False)),
                        "shared": bool(getattr(ev, "shared", False)),
                        "project_id": getattr(ev, "project_id", "") or "",
                        "origin_session": getattr(ev, "origin_session", "") or "",
                        "privacy_level": getattr(ev, "privacy_level", "") or "",
                    }
                )
            return {"events": events, "available": True}
        except Exception as e:
            return {"events": [], "available": True, "error": f"{type(e).__name__}: {e}"}

    async def life_projects_handler(self) -> dict[str, Any]:
        """GET /api/life/projects — 活跃项目 + 技能库。"""
        scoped, scoped_session = self._webui_scope_gate()
        if scoped and scoped_session is None:
            return self._scope_unavailable_payload()
        life_sim = getattr(self._p, "_life_simulator", None)
        if life_sim is None:
            return {"projects": [], "skills": [], "available": False}
        try:
            from sylanne_alpha.life_simulation import (
                _project_to_dict,
                _skill_to_dict,
            )

            projects = [_project_to_dict(p) for p in list(life_sim.state.projects)]
            skills = [_skill_to_dict(s) for s in list(life_sim.state.skills)]
            return {"projects": projects, "skills": skills, "available": True}
        except Exception as e:
            return {
                "projects": [],
                "skills": [],
                "available": True,
                "error": f"{type(e).__name__}: {e}",
            }

    async def life_audit_handler(self) -> dict[str, Any]:
        """GET /api/life/audit — outreach 审计日志。"""
        scoped, scoped_session = self._webui_scope_gate()
        if scoped and scoped_session is None:
            return self._scope_unavailable_payload()
        life_sim = getattr(self._p, "_life_simulator", None)
        if life_sim is None:
            return {"audit": {}, "available": False}
        try:
            audit = {
                str(k): list(v or [])
                for k, v in dict(life_sim.state.outreach_audit or {}).items()
            }
            return {"audit": audit, "available": True}
        except Exception as e:
            return {"audit": {}, "available": True, "error": f"{type(e).__name__}: {e}"}

    async def life_diagnostics_handler(self) -> dict[str, Any]:
        """GET /api/life/diagnostics — 一键完整状态导出（含 prompt fragment 预览）。"""
        scoped, scoped_session = self._webui_scope_gate()
        if scoped and scoped_session is None:
            return self._scope_unavailable_payload()
        life_sim = getattr(self._p, "_life_simulator", None)
        if life_sim is None:
            return {"available": False}
        try:
            data = life_sim.state.to_dict()
            try:
                data["prompt_fragment"] = life_sim.life_prompt_fragment(
                    limit=5, max_budget=2000
                )
            except TypeError:
                data["prompt_fragment"] = life_sim.life_prompt_fragment(limit=5)
            except Exception:
                data["prompt_fragment"] = ""
            data["available"] = True
            return data
        except Exception as e:
            return {"available": True, "error": f"{type(e).__name__}: {e}"}

    async def life_controls_handler(self) -> dict[str, Any]:
        """POST /api/life/controls — 用户控制（开关 / 强度 / 清除 journal/projects/plan）。"""
        from astrbot.api.web import request

        scoped, scoped_session = self._webui_scope_gate()
        if scoped and scoped_session is None:
            return self._scope_unavailable_payload()
        life_sim = getattr(self._p, "_life_simulator", None)
        if life_sim is None:
            return {"error": "life sim not available"}
        body = await request.json() or {}
        if not isinstance(body, dict):
            return {"error": "invalid body"}
        action = str(body.get("action", "") or "").strip()
        config = getattr(self._p, "_config", None)
        if config is None:
            config = {}
            try:
                self._p._config = config
            except Exception:
                pass

        def _persist_config(key: str, value: Any) -> None:
            config[key] = value
            if hasattr(self._p, "config") and isinstance(self._p.config, dict):
                self._p.config[key] = value
                save = getattr(self._p.config, "save_config", None)
                if callable(save):
                    try:
                        save()
                    except Exception:
                        pass

        if action == "toggle_enabled":
            value = bool(body.get("value", False))
            _persist_config("sylanne_alpha_life_simulation_enabled", value)
            return {"ok": True, "enabled": value}
        if action == "set_share_intensity":
            intensity = str(body.get("value", "standard") or "standard")
            if intensity not in ("off", "low", "standard", "high"):
                return {"error": "invalid intensity"}
            _persist_config(
                "sylanne_alpha_life_simulation_share_intensity", intensity
            )
            return {"ok": True, "share_intensity": intensity}
        if action == "clear_journal":
            life_sim.state.events.clear()
            return {"ok": True, "cleared": "events"}
        if action == "clear_projects":
            life_sim.state.projects.clear()
            return {"ok": True, "cleared": "projects"}
        if action == "clear_plan":
            life_sim.state.plan = None
            return {"ok": True, "cleared": "plan"}
        return {"error": f"unknown action: {action}"}

    # ------------------------------------------------------------------
    # Config presets
    # ------------------------------------------------------------------

    async def config_presets_handler(self) -> dict[str, Any]:
        """GET /api/config_presets — 返回人格配置预设模板列表。"""
        return {"presets": CONFIG_PRESETS}

    # ------------------------------------------------------------------
    # Item 62: GET /api/glossary 术语词典
    # ------------------------------------------------------------------

    async def glossary_handler(self) -> dict[str, Any]:
        """GET /api/glossary — 返回 Sylanne 专有术语词典，供前端悬浮卡片渲染。"""
        return {"glossary": GLOSSARY}

    # ------------------------------------------------------------------
    # Data export & purge
    # ------------------------------------------------------------------

    async def export_data_handler(self) -> dict[str, Any]:
        """GET /api/export_data?session_key=xxx — 导出指定会话的所有数据。

        导出内容包括：记忆系统状态、人格参数、伤痕/虚空状态、计算栈快照。
        """
        from astrbot.api.web import request

        session_key = str(request.query.get("session_key") or "").strip()
        if not session_key:
            return {"ok": False, "error": "missing session_key param"}
        scoped, scoped_session = self._webui_scope_gate(session_key)
        if scoped:
            if scoped_session is None:
                return self._scope_unavailable_payload()
            session_key = scoped_session

        export: dict[str, Any] = {"session_key": session_key}

        # Memory system
        mem_sys = (
            self._p._memory_system_for_session(session_key)
            if hasattr(self._p, "_memory_system_for_session")
            else getattr(self._p, "_memory_system", None)
        )
        if mem_sys is not None:
            export["memory"] = {
                "l1": [
                    item.to_dict() if hasattr(item, "to_dict") else dict(item or {})
                    for item in list(getattr(mem_sys, "_l1", []) or [])
                ],
                "l2": [
                    item.to_dict() if hasattr(item, "to_dict") else dict(item or {})
                    for item in list(getattr(mem_sys, "_l2", []) or [])
                ],
                "l3_nodes": {
                    k: (v.to_dict() if hasattr(v, "to_dict") else dict(v or {}))
                    for k, v in dict(
                        getattr(mem_sys, "_l3_nodes", {}) or {}
                    ).items()
                },
                "l3_edges": [
                    e.to_dict() if hasattr(e, "to_dict") else dict(e or {})
                    for e in list(getattr(mem_sys, "_l3_edges", []) or [])
                ],
            }

        # Personality & computation state.  Scoped runtime may read only its
        # bound host; registry-free compatibility retains the raw host map.
        if scoped:
            host = self._p._host(session_key)
        else:
            hosts = getattr(self._p, "_hosts", {}) or {}
            host = hosts.get(session_key)
        if host is not None:
            comp = host.kernel.computation
            export["personality"] = dict(comp._personality)
            export["computation"] = comp.to_dict()
        else:
            export["personality"] = None
            export["computation"] = None

        # Persisted state (KV)
        try:
            state = await self._p._load_state(session_key)
            if state is not None:
                export["persisted_state"] = (
                    state.to_dict() if hasattr(state, "to_dict") else state
                )
        except Exception:
            export["persisted_state"] = None

        return {"ok": True, "data": export}

    async def purge_data_handler(self) -> dict[str, Any]:
        """DELETE /api/purge_data?session_key=xxx — 彻底删除指定会话的所有数据。

        删除内容：记忆系统、持久化 KV 状态、host 实例、对话缓冲。
        """
        from astrbot.api.web import request

        session_key = str(request.query.get("session_key") or "").strip()
        if not session_key:
            return {"ok": False, "error": "missing session_key param"}
        scoped, _scoped_session = self._webui_scope_gate(session_key)
        if scoped:
            # Deletion still fans out through legacy raw-key persistence and
            # host cleanup paths.  Keep it disabled until a scoped delete API
            # exists rather than risking a cross-owner purge.
            return self._scope_unavailable_payload()

        purged: list[str] = []

        # Clear memory system
        mem_sys = (
            self._p._memory_system_for_session(session_key)
            if hasattr(self._p, "_memory_system_for_session")
            else getattr(self._p, "_memory_system", None)
        )
        if mem_sys is not None:
            mem_sys._l1.clear()
            mem_sys._l2.clear()
            mem_sys._l3_nodes.clear()
            mem_sys._l3_edges.clear()
            mem_sys._tick = 0
            # FIX(F1，完整性复审)：与 meltdown 同理——显式擦除必须把 _hydrated 置 True，
            # 否则 _memory_system_for_session 懒创建时排的后台补水任务会在本 handler 的
            # 后续 await 期间跑起来、从尚未删除的 KV 旧档把刚清空的记忆合并回活体，随后
            # 一次周期 save 又把它写回 KV——显式清除被自己的补水复活。置 True 让补水的
            # 二次 _hydrated 检查放弃合并。
            mem_sys._hydrated = True
            purged.append("memory_system")

        # Remove host instance
        hosts = getattr(self._p, "_hosts", {}) or {}
        if session_key in hosts:
            del hosts[session_key]
            purged.append("host")

        # Clear conversation buffer
        buffers = getattr(self._p, "_conversation_buffers", {}) or {}
        if session_key in buffers:
            del buffers[session_key]
            purged.append("conversation_buffer")

        # Delete persisted KV states
        try:
            await self._p._delete_state(session_key)
            purged.append("kv_state")
        except Exception:
            pass
        try:
            await self._p._delete_humanlike_state(session_key)
            purged.append("kv_humanlike")
        except Exception:
            pass
        try:
            await self._p._delete_personality_drift_state(session_key)
            purged.append("kv_personality_drift")
        except Exception:
            pass
        try:
            await self._p._delete_sylanne_memory_state(session_key)
            purged.append("kv_memory")
        except Exception:
            pass

        logger.info(
            f"Sylanne PURGE DATA: session={session_key}, purged={purged}"
        )
        return {"ok": True, "session_key": session_key, "purged": purged}

    # ------------------------------------------------------------------
    # Frontend data format helpers
    # ------------------------------------------------------------------

    def _frontend_personality(self, personality: dict) -> dict[str, Any]:
        """将内部人格数据转换为前端期望的 {five, six, drift} 格式。"""
        traits = personality.get(
            "traits", personality if isinstance(personality, dict) else {}
        )
        five = {
            "openness": float(traits.get("openness", traits.get("curiosity", 0.5)) or 0.5),
            "warmth": float(traits.get("warmth", 0.5) or 0.5),
            "intensity": float(traits.get("intensity", traits.get("arousal", 0.5)) or 0.5),
            "autonomy": float(traits.get("autonomy", traits.get("sovereignty", 0.5)) or 0.5),
            "resilience": float(traits.get("resilience", traits.get("repair", 0.5)) or 0.5),
        }
        six_names = ["Curiosity", "Empathy", "Precision", "Playfulness", "Defiance", "Melancholy"]
        six_keys = ["curiosity", "warmth", "coherence", "playfulness", "sovereignty", "melancholy"]
        six_colors = ["#B88A9E", "#00b4d8", "#ffaa00", "#4caf50", "#ff4444", "#9c27b0"]
        six = [
            {"name": n, "value": float(traits.get(k, 0.5) or 0.5), "color": c}
            for n, k, c in zip(six_names, six_keys, six_colors)
        ]
        drift_raw = personality.get("drift", {}) if isinstance(personality, dict) else {}
        drift_history = drift_raw.get("history", []) if isinstance(drift_raw, dict) else []
        drift = [
            {"time": str(d.get("time", "")), "text": str(d.get("text", d.get("signal", "")))}
            for d in drift_history[-10:]
        ]
        return {"five": five, "six": six, "drift": drift}

    def _frontend_spine_layers(self, comp: Any) -> list[dict[str, Any]]:
        """将计时数据转换为前端期望的 spine_layers 数组。"""
        layer_meta = [
            ("L1", "perception", "HDC Perception", "Hyperdimensional binary encoding. Converts text to 2048-bit vectors."),
            ("L2", "gate", "Predictive Coding Gate", "Computes Hamming surprise against prediction. Routes processing path."),
            ("L3", "void_scar", "Void-Scar Engine", "Irreversible scar state tracking. Wounds heal through stages."),
            ("L4", "sheaf", "Relational Sheaf", "Cross-relationship propagation via sheaf Laplacian."),
            ("L5", "hgt", "MoE-HGT", "Mixture-of-Experts + Heterogeneous Graph Transformer."),
            ("L6", "boundary", "Autopoietic Boundary", "32-dim identity kernel with orthogonal projection."),
            ("L7", "expression", "Phase Transition", "Pressure accumulation to threshold. Expression modes."),
        ]
        timing_raw = comp.timing_stats() if hasattr(comp, "timing_stats") else {}
        result = []
        for lid, internal_key, name, desc in layer_meta:
            stats = timing_raw.get(
                internal_key,
                timing_raw.get(lid, timing_raw.get(lid.replace("L", "layer_"), {})),
            )
            if not isinstance(stats, dict):
                stats = {}
            avg_ms = round(
                stats.get("mean_ns", stats.get("p50_ns", 0)) / 1_000_000, 6
            )
            p50_ms = round(stats.get("p50_ns", 0) / 1_000_000, 6)
            p95_ms = round(
                stats.get("p95_ns", stats.get("p99_ns", 0)) / 1_000_000, 6
            )
            p99_ms = round(
                stats.get("p99_ns", stats.get("p95_ns", 0)) / 1_000_000, 6
            )
            count = int(stats.get("count", 0))
            result.append({
                "id": lid, "name": name, "status": "active" if count > 0 else "idle",
                "avg": avg_ms, "p50": p50_ms, "p95": p95_ms, "p99": p99_ms,
                "count": count, "desc": desc,
            })
        return result

    async def probe_handler(self) -> dict[str, Any]:
        """探测独立 WebUI 监听器的健康状态。

        从插件进程内部向 localhost:port 发起 HTTP 请求，
        验证 schema_version 和 runtime_id 是否匹配当前实例。
        同时处理过期模块的清理和重启。
        """
        import urllib.error
        import urllib.request

        enabled = self._p._cfg_bool("sylanne_webui_enabled", False)
        host = str(self._p._cfg("sylanne_webui_host", "127.0.0.1") or "127.0.0.1")
        port = self._p._cfg_int("sylanne_webui_port", 2718)
        expected_runtime = self._p._webui_runtime_info()
        stopped: list[str] = []
        module_count_before = len(self._p._iter_loaded_webui_server_modules())
        if enabled:
            stopped = await self._p._stop_stale_webui_server_modules(
                include_current=True
            )
            if stopped:
                self._p.logger.info(
                    f"Sylanne WebUI probe stopped stale listener modules: {stopped}"
                )
            self._p._start_webui_if_enabled()
            await asyncio.sleep(0.2)
        module_count_after = len(self._p._iter_loaded_webui_server_modules())

        local_url = f"http://127.0.0.1:{port}/api/state"

        def _probe_local() -> dict[str, Any]:
            probe: dict[str, Any] = {
                "ok": False,
                "url": local_url,
                "status": 0,
                "schema_version": "",
                "runtime": {},
                "runtime_match": False,
                "error": "",
            }
            try:
                with urllib.request.urlopen(local_url, timeout=2.0) as response:
                    raw = response.read().decode("utf-8", errors="replace")
                    payload = json.loads(raw)
                    runtime = (
                        payload.get("runtime", {}) if isinstance(payload, dict) else {}
                    )
                    if not isinstance(runtime, dict):
                        runtime = {}
                    runtime_match = (
                        str(runtime.get("runtime_id", ""))
                        == expected_runtime["runtime_id"]
                    )
                    probe.update(
                        {
                            "ok": response.status == 200
                            and payload.get("schema_version")
                            == "sylanne.webui.state.v1"
                            and runtime_match,
                            "status": response.status,
                            "schema_version": str(payload.get("schema_version", "")),
                            "runtime": runtime,
                            "runtime_match": runtime_match,
                        }
                    )
            except urllib.error.HTTPError as exc:
                probe.update({"status": exc.code, "error": str(exc)})
            except Exception as exc:
                probe["error"] = f"{type(exc).__name__}: {exc}"
            return probe

        probe = await asyncio.to_thread(_probe_local)

        return {
            "schema_version": "sylanne.webui.probe.v1",
            "enabled": enabled,
            "host": host,
            "port": port,
            "expected_runtime": expected_runtime,
            "local": probe,
            "takeover": {
                "module_count_before": module_count_before,
                "module_count_after": module_count_after,
                "stopped": stopped,
            },
            "public_hint": f"http://<server-ip>:{port}/",
        }

    # ------------------------------------------------------------------
    # Logo & dashboard
    # ------------------------------------------------------------------

    async def logo_handler(self) -> Any:
        """返回插件 logo.png，设置正确的 Content-Type。"""
        from astrbot.api.web import error_response, file_response

        logo_path = Path(self._plugin_dir) / "logo.png"
        if not logo_path.exists():
            return error_response("Not Found", status_code=404)
        return file_response(logo_path, content_type="image/png")

    async def dashboard_handler(self) -> Any:
        """通过 AstrBot 内置 Web 服务器提供 WebUI dashboard HTML 页面。"""
        from astrbot.api.web import error_response, file_response

        dashboard_path = Path(self._plugin_dir) / "UI" / "index.html"
        if not dashboard_path.exists():
            return error_response("Dashboard not found", status_code=404)
        return file_response(
            dashboard_path, content_type="text/html; charset=utf-8"
        )

    # ------------------------------------------------------------------
    # Item 47: /health 健康检查（不需要认证）
    # ------------------------------------------------------------------

    async def health_handler(self) -> dict[str, Any]:
        """返回服务健康状态，不需要认证。"""
        from sylanne_alpha.webui_server import _start_time, _get_process_memory_mb

        uptime_s = int(time.time() - _start_time)
        if getattr(self._p, "_scope_runtime_registry", None) is not None:
            # Health is process-level; do not enumerate legacy host maps in a
            # scoped plugin merely to report a cross-session count.
            sessions_count = 0
        else:
            hosts_dict = getattr(self._p, "_hosts", {}) or {}
            sessions_count = len(hosts_dict) if isinstance(hosts_dict, dict) else 0
        memory_mb = _get_process_memory_mb()
        return {
            "status": "ok",
            "uptime_s": uptime_s,
            "sessions": sessions_count,
            "memory_mb": memory_mb,
        }

    # ------------------------------------------------------------------
    # Item 49: /api/error_stats 错误率仪表盘
    # ------------------------------------------------------------------

    async def error_stats_handler(self) -> list[dict[str, Any]]:
        """返回最近 1h 内每分钟的 ERROR/WARNING 计数。"""
        from sylanne_alpha.webui_server import _error_counts, _error_counts_lock

        cutoff = int(time.time()) // 60 * 60 - 3600
        with _error_counts_lock:
            data = [
                {"minute": ts, "errors": errs, "warnings": warns}
                for ts, errs, warns in _error_counts
                if ts >= cutoff
            ]
        return data

    # ------------------------------------------------------------------
    # Item 53: /api/config_export & /api/config_import
    # ------------------------------------------------------------------

    _SENSITIVE_CONFIG_KEYS = frozenset({
        "sylanne_webui_token", "api_key", "secret", "token",
        "password", "credential", "auth_key", "openai_key",
        "anthropic_key", "gemini_key", "cookie",
    })
    # GET 侧脱敏用的哨兵；POST 侧收到该值表示"未改动",不覆盖已存凭据。
    _MASKED_VALUE = "***"

    def _is_sensitive_key(self, key: str) -> bool:
        lower = key.lower()
        return any(s in lower for s in self._SENSITIVE_CONFIG_KEYS)

    async def config_export_handler(self) -> dict[str, Any]:
        """GET /api/config_export — 返回当前配置 JSON（敏感字段脱敏）。"""
        config = dict(getattr(self._p, "_config", {}) or {})
        return {
            k: ("***" if self._is_sensitive_key(k) else v)
            for k, v in config.items()
        }

    async def config_import_handler(self) -> dict[str, Any]:
        """POST /api/config_import — 接收 JSON body 覆盖写入配置（安全字段保护）。"""
        from astrbot.api.web import request

        body = await request.json()
        if not isinstance(body, dict) or not body:
            return {"ok": False, "error": "expected_object"}
        config = getattr(self._p, "_config", None)
        if config is None:
            return {"ok": False, "error": "no_config"}
        blocked = [k for k in body if self._is_sensitive_key(k)]
        if blocked:
            return {"ok": False, "error": "sensitive_keys_blocked", "keys": blocked}
        config.update(body)
        persistent = getattr(self._p, "config", config)
        if isinstance(persistent, dict):
            persistent.update(body)
        if hasattr(persistent, "save_config"):
            persistent.save_config()
        return {"ok": True, "keys": list(body.keys())}

    # ------------------------------------------------------------------
    # Item 66: /api/widget-state AstrBot 管理面板状态卡片
    # ------------------------------------------------------------------

    async def widget_state_handler(self) -> dict[str, Any]:
        """返回 AstrBot 管理面板状态卡片数据。"""
        from sylanne_alpha.webui_server import _build_widget_state

        scoped, _scoped_session = self._webui_scope_gate()
        if scoped:
            # The shared widget builder is aggregate-only; no scoped projection
            # exists yet, so never let it inspect sibling owners.
            return self._scope_unavailable_payload()
        return _build_widget_state(self._p)

    # ------------------------------------------------------------------
    # 认知核页镜像：GET /api/v2core_state（与独立 webui_server 共用同一 builder）
    # ------------------------------------------------------------------

    async def v2core_state_handler(self) -> dict[str, Any]:
        """v2core 认知核状态（嵌入式 AstrBot Web 服务器镜像，纯只读）。"""
        from astrbot.api.web import request

        from sylanne_alpha.webui_server import _v2core_state_payload

        session = str(request.query.get("session") or "").strip()
        scoped, scoped_session = self._webui_scope_gate(session)
        if scoped:
            if scoped_session is None:
                return self._scope_unavailable_payload()
            session = scoped_session
        return _v2core_state_payload(self._p, session=session)

    # ------------------------------------------------------------------
    # MEM-03 PR-7：三只读 admin 端点（嵌入式镜像，与独立 webui_server 共用
    # 同一批 _admin_* builder，见 webui_server.py 同名函数注释）。
    # ------------------------------------------------------------------

    async def admin_inspect_handler(self) -> dict[str, Any]:
        """GET /api/admin/inspect — 单 session 记忆诊断（纯只读）。"""
        from astrbot.api.web import request

        from sylanne_alpha.webui_server import _admin_inspect_payload

        session = str(request.query.get("session") or "").strip()
        scoped, scoped_session = self._webui_scope_gate(session)
        if scoped:
            if scoped_session is None:
                return self._scope_unavailable_payload()
            session = scoped_session
        return await _admin_inspect_payload(self._p, session=session)

    async def admin_quarantine_view_handler(self) -> dict[str, Any]:
        """GET /api/admin/quarantine_view — quarantine 侧车只读视图。"""
        from astrbot.api.web import request

        from sylanne_alpha.webui_server import _admin_quarantine_view_payload

        session = str(request.query.get("session") or "").strip()
        scoped, scoped_session = self._webui_scope_gate(session)
        if scoped:
            if scoped_session is None:
                return self._scope_unavailable_payload()
            session = scoped_session
        return await _admin_quarantine_view_payload(self._p, session=session)

    async def admin_pending_deletes_handler(self) -> dict[str, Any]:
        """GET /api/admin/pending_deletes — 跨重启 pending-delete 索引镜像快照。"""
        from sylanne_alpha.webui_server import _admin_pending_deletes_payload

        scoped, _scoped_session = self._webui_scope_gate()
        if scoped:
            # This payload aggregates a process-wide mirror and has no exact
            # session projection, so scoped runtime deliberately exposes none.
            return self._scope_unavailable_payload()
        return _admin_pending_deletes_payload(self._p)

    # ------------------------------------------------------------------
    # Item 6: POST /api/proactive_feedback 主动发言反馈
    # ------------------------------------------------------------------

    async def proactive_feedback_handler(self) -> dict[str, Any]:
        """接收用户对主动发言的反馈（positive/negative）。"""
        from astrbot.api.web import request

        body = await request.json() or {}
        session_key = str(body.get("session_key", "")).strip()
        timestamp = float(body.get("timestamp", 0))
        rating = str(body.get("rating", "")).strip()
        if not session_key or not rating or rating not in ("positive", "negative"):
            return {"ok": False, "error": "invalid_params"}
        scoped, scoped_session = self._webui_scope_gate(session_key)
        if scoped:
            if scoped_session is None:
                return self._scope_unavailable_payload()
            session_key = scoped_session
        scheduler = getattr(self._p, "_proactive_scheduler", None)
        if scheduler is not None and hasattr(scheduler, "record_feedback"):
            scheduler.record_feedback(session_key, timestamp, rating)
        return {"ok": True}

    # ------------------------------------------------------------------
    # Item 69: GET /api/weekly_report 周报自动生成
    # ------------------------------------------------------------------

    async def weekly_report_handler(self) -> dict[str, Any]:
        """返回过去 7 天的周报统计数据。"""
        from sylanne_alpha.analytics import generate_weekly_report

        scoped, _scoped_session = self._webui_scope_gate()
        if scoped:
            # The report is an aggregate with no exact-session contract.
            return self._scope_unavailable_payload()
        return generate_weekly_report(self._p)

    # ------------------------------------------------------------------
    # Item 70: GET /api/memory/decay_curve 记忆衰减曲线可视化数据
    # ------------------------------------------------------------------

    async def memory_decay_curve_handler(self) -> dict[str, Any]:
        """GET /api/memory/decay_curve?memory_id=xxx — 返回记忆衰减时间序列。"""
        import math as _math

        from astrbot.api.web import request

        memory_id = str(request.query.get("memory_id") or "").strip()
        if not memory_id:
            return {"ok": False, "error": "missing memory_id param"}

        scoped, scoped_session = self._webui_scope_gate()
        if scoped and scoped_session is None:
            return self._scope_unavailable_payload()

        # Scoped mode searches only the exact bound memory owner.  The legacy
        # compatibility path below retains the historical cross-session scan.
        target_memory = None
        if scoped:
            memory_systems = [
                self._p._memory_system_for_session(scoped_session)
                if hasattr(self._p, "_memory_system_for_session")
                else None
            ]
        else:
            hosts = getattr(self._p, "_hosts", {}) or {}
            memory_systems = [
                self._p._memory_system_for_session(session_key)
                if hasattr(self._p, "_memory_system_for_session")
                else None
                for session_key in list(hosts.keys())
            ]
        for mem_sys in memory_systems:
            if mem_sys is None:
                continue
            for pool in (
                getattr(mem_sys, "_l1", []) or [],
                getattr(mem_sys, "_l2", []) or [],
            ):
                for item in list(pool):
                    item_id = getattr(item, "id", None) or (
                        item.get("id") if isinstance(item, dict) else None
                    )
                    if str(item_id) == memory_id:
                        target_memory = item
                        break
                if target_memory:
                    break
            if target_memory:
                break

        if target_memory is None:
            return {"ok": False, "error": "memory_id not found"}

        # 提取参数
        created_at = float(
            getattr(target_memory, "created_at", 0)
            or (target_memory.get("created_at", 0) if isinstance(target_memory, dict) else 0)
        )
        rehearsal = int(
            getattr(target_memory, "recall_count", 0)
            or (target_memory.get("recall_count", 0) if isinstance(target_memory, dict) else 0)
        )
        emotional_weight = float(
            getattr(target_memory, "emotional_weight", 0.5)
            or (target_memory.get("emotional_weight", 0.5) if isinstance(target_memory, dict) else 0.5)
        )

        # 生成衰减曲线：每小时一个点，最多 168 点（7 天）
        stability = 24 * (1 + rehearsal * 0.5) * (1 + emotional_weight)
        curve = []
        for hour in range(169):
            retention = max(0.05, _math.exp(-hour / stability))
            curve.append({"hour": hour, "retention": round(retention, 4)})

        return {
            "memory_id": memory_id,
            "created_at": created_at,
            "stability": round(stability, 2),
            "rehearsal": rehearsal,
            "emotional_weight": round(emotional_weight, 3),
            "curve": curve,
        }

    # ------------------------------------------------------------------
    # Item 84: 人格配置分享市场 — 导出/导入人格参数
    # ------------------------------------------------------------------

    async def personality_export_handler(self) -> dict[str, Any]:
        """GET /api/personality/export — 导出当前人格参数为 JSON。

        包含 Embodiment Five、Sylanne Six、漂移历史摘要。
        """
        scoped, scoped_session = self._webui_scope_gate()
        if scoped and scoped_session is None:
            return self._scope_unavailable_payload()

        # Scoped mode reads only its exact host, never the first active host.
        if scoped:
            hosts = [self._p._host(scoped_session)]
        else:
            hosts = list((getattr(self._p, "_hosts", {}) or {}).values())
        personality: dict[str, Any] = {}
        for h in hosts:
            try:
                personality = (
                    h.kernel._personality()
                    if hasattr(h.kernel, "_personality")
                    else {}
                )
                if personality:
                    break
            except Exception:
                continue

        frontend_data = self._frontend_personality(personality)
        # 构建导出格式
        export_payload = {
            "embodiment_five": frontend_data.get("five", {}),
            "sylanne_six": {
                item["name"]: item["value"]
                for item in frontend_data.get("six", [])
            },
            "drift_history": frontend_data.get("drift", []),
            "description": "",
        }
        return {"ok": True, "personality": export_payload}

    async def personality_import_handler(self) -> dict[str, Any]:
        """POST /api/personality/import — 导入人格配置 JSON，覆盖当前人格参数。

        期望格式：{"embodiment_five": {...}, "sylanne_six": {...}, "description": "..."}
        """
        from astrbot.api.web import request

        body = await request.json()
        if not isinstance(body, dict):
            return {"ok": False, "error": "expected JSON object"}

        embodiment_five = body.get("embodiment_five")
        sylanne_six = body.get("sylanne_six")
        if not isinstance(embodiment_five, dict) and not isinstance(sylanne_six, dict):
            return {"ok": False, "error": "missing embodiment_five or sylanne_six"}

        scoped, scoped_session = self._webui_scope_gate()
        if scoped and scoped_session is None:
            return self._scope_unavailable_payload()

        # Scoped mode mutates only the exact bound host; registry-free stubs keep
        # the historical all-host import behavior.
        if scoped:
            hosts = [(scoped_session, self._p._host(scoped_session))]
        else:
            hosts = list((getattr(self._p, "_hosts", {}) or {}).items())
        updated_sessions: list[str] = []
        for sk, h in hosts:
            try:
                comp = h.kernel.computation
                personality = comp._personality
                if not isinstance(personality, dict):
                    continue
                traits = personality.setdefault("traits", {})
                # 写入 Embodiment Five
                if isinstance(embodiment_five, dict):
                    for key, value in embodiment_five.items():
                        try:
                            traits[key] = float(value)
                        except (TypeError, ValueError):
                            continue
                # 写入 Sylanne Six（名称→内部键映射）
                if isinstance(sylanne_six, dict):
                    six_name_to_key = {
                        "Curiosity": "curiosity",
                        "Empathy": "warmth",
                        "Precision": "coherence",
                        "Playfulness": "playfulness",
                        "Defiance": "sovereignty",
                        "Melancholy": "melancholy",
                    }
                    for name, value in sylanne_six.items():
                        internal_key = six_name_to_key.get(name, name.lower())
                        try:
                            traits[internal_key] = float(value)
                        except (TypeError, ValueError):
                            continue
                updated_sessions.append(sk)
            except Exception:
                continue

        if not updated_sessions:
            return {"ok": False, "error": "no active sessions to update"}
        return {"ok": True, "updated_sessions": updated_sessions}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def _plugin_dir(self) -> str:
        try:
            import main as _main_mod
            return getattr(_main_mod, "_PLUGIN_DIR", ".")
        except ImportError:
            return str(Path(__file__).resolve().parent.parent)
