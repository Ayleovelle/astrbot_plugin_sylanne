"""Sylanne-Embodiment: 独立 WebUI HTTP 服务器模块。

在可配置端口（默认 2718）上运行独立的 HTTP 服务器，
不依赖 AstrBot 的认证体系，通过 Bearer token 自行鉴权。

架构设计：
- 优先使用 aiohttp（异步，性能好）
- 若 aiohttp 不可用，回退到 stdlib http.server（线程模式）
- 通过 _plugin_access_lock 保证线程安全（stdlib 模式下多线程访问插件状态）
- 支持热重载：AstrBot hot-upload 时自动接管旧监听器

生命周期管理：
- start_webui_background(): 启动后台任务
- stop_webui_server(): 停止监听器
- WebUILifecycle: 封装启动/停止/接管的完整生命周期逻辑
"""

from __future__ import annotations

import asyncio
import gc
import json
import logging
import os
import secrets
import sys
import threading
import time
from collections import deque
from types import ModuleType
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

from pathlib import Path

from sylanne_alpha.webui_routes import (
    _comp_boundary_dict,
    _comp_gate_dict,
    _comp_route_stats,
    _webui_session_items,
    build_observation_history_payload,
    build_model_routing_payload,
    consume_scoped_meltdown_nonce,
    issue_scoped_meltdown_nonce,
    purge_scoped_memory,
    scoped_api_payload,
)
from sylanne_alpha.scoped_api import (
    SCOPE_NONCE_HEADER,
    ScopedApiAuthorization,
    ScopedApiError,
    ScopedApiRequest,
    scoped_api_service_for_plugin,
)
from sylanne_alpha.scope_contracts import ScopeApiPathEcho


def _get_plugin_version() -> str:
    """从 metadata.yaml 读取版本号（缓存结果）。"""
    if not hasattr(_get_plugin_version, "_cache"):
        try:
            meta_path = Path(__file__).resolve().parent.parent / "metadata.yaml"
            for line in meta_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("version:"):
                    _get_plugin_version._cache = line.split(":", 1)[1].strip().strip('"').strip("'")
                    break
            else:
                _get_plugin_version._cache = "unknown"
        except Exception:
            _get_plugin_version._cache = "unknown"
    return _get_plugin_version._cache


try:
    from astrbot.core.utils.astrbot_path import get_astrbot_data_path  # type: ignore
except ImportError:

    def get_astrbot_data_path() -> Path:  # type: ignore
        return Path.home()

from sylanne_alpha.infra import ensure_background_tasks_list, resolve_data_root


if TYPE_CHECKING:
    from sylanne_alpha.protocols import PluginHost

logger = logging.getLogger(__name__)

# 模块级静态路径常量（__file__ 派生、恒定）：在 import 时算一次，避免在 async 处理器里
# 调 Path.resolve()/os.path（ASYNC240：会在事件循环上做阻塞 FS 调用）。
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_DASHBOARD_HTML_PATH = _PLUGIN_ROOT / "UI" / "index.html"
_LOGO_PATH = _PLUGIN_ROOT / "logo.png"

# 模块级全局状态：跨热重载保持监听器引用
# 使用 globals().get() 是为了在 AstrBot hot-upload 重新 import 时保留已有值
_server_task: asyncio.Task | None = globals().get("_server_task")
_httpd: Any = globals().get("_httpd")
_httpd_thread: threading.Thread | None = globals().get("_httpd_thread")
_active_plugin: Any = globals().get("_active_plugin")
# DATA-LOSS 修复：stdlib ThreadingHTTPServer 回退模式下，worker 线程没有自己的
# running loop，`asyncio.get_event_loop()` 在线程里拿到的是新建的、从未 run 过的
# loop——`call_soon_threadsafe` 排的回调永远不会执行，导致"永久删除"类操作
# （meltdown 的持久化 purge）悄悄变成 no-op，却仍对用户回 {ok: True}。
# 这里持有 AstrBot 进程级 persistent main loop 的引用（由 main.py 的 async
# initialize() 在其运行的 loop 上调用 set_main_loop() 权威绑定，镜像
# MemoryWriteThroat.bind_loop 的既有模式），供 stdlib handler 用
# run_coroutine_threadsafe 提交到「真正在跑」的 loop。
_main_loop: asyncio.AbstractEventLoop | None = globals().get("_main_loop")
_active_token: str = ""
_meltdown_nonces: dict[str, str] = {}
# Item 24: CSRF token — 登录成功后生成，POST/DELETE 端点校验
_csrf_token: str = ""
# 线程安全锁：stdlib HTTP server 的多线程 handler 访问插件状态时使用
_plugin_access_lock = threading.Lock()

# S1/S2: 敏感配置键保护（子串匹配；"cookie" 覆盖 sylanne_alpha_qzone_cookie 登录凭据）
_SENSITIVE_KEYS = frozenset({"token", "password", "secret", "api_key", "access_token", "auth_token", "bearer", "credential", "cookie"})
_LEGACY_SCOPED_PRIVATE_PATHS = frozenset(
    {
        "/api/state",
        "/api/observation_history",
        "/api/computation_logs",
        "/api/memory_pools",
        "/api/meltdown_nonce",
        "/api/memory_sink",
        "/api/memory_consolidate",
        "/api/memory_meltdown",
        "/ws/state",
    }
)


def _is_sensitive_key(key: str) -> bool:
    """检查配置键是否包含敏感子串。"""
    lower = key.lower()
    return any(s in lower for s in _SENSITIVE_KEYS)


# diagnostics 自动联动：有 /api/computation_logs 请求时开启，30s 无请求后关闭
_last_diag_request: float = 0

# Item 112: WebUI 主题偏好
_theme_preference: str = "dark"

# Item 47: 健康检查 — 记录服务器启动时间
_start_time: float = time.time()

# Item 49: 错误率仪表盘 — 每分钟 ERROR/WARNING 计数
# (timestamp_minute, errors, warnings)
_error_counts: deque[tuple[int, int, int]] = deque(maxlen=60)
_error_counts_lock = threading.Lock()


class _ErrorStatsHandler(logging.Handler):
    """捕获 ERROR/WARNING 级别日志，按分钟聚合计数。"""

    def emit(self, record: logging.LogRecord) -> None:
        minute = int(time.time()) // 60 * 60
        with _error_counts_lock:
            if _error_counts and _error_counts[-1][0] == minute:
                ts, errs, warns = _error_counts[-1]
                if record.levelno >= logging.ERROR:
                    _error_counts[-1] = (ts, errs + 1, warns)
                elif record.levelno >= logging.WARNING:
                    _error_counts[-1] = (ts, errs, warns + 1)
            else:
                if record.levelno >= logging.ERROR:
                    _error_counts.append((minute, 1, 0))
                elif record.levelno >= logging.WARNING:
                    _error_counts.append((minute, 0, 1))


# 安装 handler 到 root logger（仅安装一次，用 name 去重避免 reload 累积）
_ESH_NAME = "sylanne_error_stats"
if not any(getattr(h, "name", None) == _ESH_NAME for h in logging.root.handlers):
    _error_stats_handler = _ErrorStatsHandler(level=logging.WARNING)
    _error_stats_handler.name = _ESH_NAME
    logging.root.addHandler(_error_stats_handler)


def _build_metrics() -> str:
    """生成 Prometheus 格式指标文本。"""
    lines = []
    lines.append("# HELP sylanne_uptime_seconds Plugin uptime in seconds")
    lines.append("# TYPE sylanne_uptime_seconds gauge")
    lines.append(f"sylanne_uptime_seconds {time.time() - _start_time:.1f}")

    lines.append("# HELP sylanne_sessions_active Number of active sessions")
    lines.append("# TYPE sylanne_sessions_active gauge")
    sessions = 0
    if _active_plugin:
        hosts = getattr(_active_plugin, '_hosts', {})
        sessions = len(hosts) if isinstance(hosts, dict) else 0
    lines.append(f"sylanne_sessions_active {sessions}")

    lines.append("# HELP sylanne_spine_process_total Total spine process calls")
    lines.append("# TYPE sylanne_spine_process_total counter")
    logs = getattr(_active_plugin, '_computation_logs', []) if _active_plugin else []
    lines.append(f"sylanne_spine_process_total {len(logs)}")

    return "\n".join(lines) + "\n"


def _set_spine_diagnostics(plugin: Any, enabled: bool) -> None:
    """安全地对所有活跃 host 的 computation spine 设置 diagnostics 开关。"""
    hosts = getattr(plugin, "_hosts", None)
    if hosts is None:
        return
    try:
        values = hosts.values() if hasattr(hosts, "values") else []
        for host in values:
            spine = getattr(getattr(host, "kernel", None), "computation", None)
            if spine is not None and hasattr(spine, "set_diagnostics"):
                spine.set_diagnostics(enabled)
    except Exception:
        pass


def _ensure_token(config: dict[str, Any]) -> str:
    """生成或获取 WebUI Bearer token，用于 API 鉴权。"""
    global _active_token, _csrf_token
    token = str(config.get("sylanne_webui_token", "") or "")
    if not token:
        token = secrets.token_urlsafe(32)
        config["sylanne_webui_token"] = token
    _active_token = token
    # Item 24: 每次登录/启动时生成 CSRF token
    _csrf_token = secrets.token_hex(16)
    return token


def _set_active_plugin(plugin: Any) -> None:
    """将独立监听器指向最新的插件实例（热重载时调用）。"""
    global _active_plugin
    _active_plugin = plugin


def set_main_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    """绑定 AstrBot 进程级 persistent main loop（供 stdlib 回退路径提交持久化协程）。

    必须在 main.py 的 async initialize()（保证运行在该 persistent loop 上）里调用；
    调用点须早于 stdlib 服务器开始处理请求。插件卸载/停止时传 None 清除，防止
    持有已关闭 loop 的悬垂引用。
    """
    global _main_loop
    _main_loop = loop


def _get_main_loop() -> asyncio.AbstractEventLoop | None:
    """返回当前绑定的 persistent main loop（未绑定或已停止则返回 None）。"""
    loop = _main_loop
    if loop is None:
        return None
    try:
        if loop.is_closed():
            return None
    except Exception:
        return None
    return loop


def _plugin(default: Any = None) -> Any:
    return _active_plugin if _active_plugin is not None else default


def _runtime_info(plugin: Any) -> dict[str, Any]:
    return {
        "plugin_name": "astrbot_plugin_sylanne",
        "runtime_id": str(getattr(plugin, "_webui_runtime_id", "") or ""),
        "instance_id": hex(id(plugin)) if plugin is not None else "",
        "module": str(
            getattr(plugin.__class__, "__module__", "") if plugin is not None else ""
        ),
    }


async def start_webui_server(plugin: Any, host: str = "127.0.0.1", port: int = 2718):
    """启动独立 WebUI 服务器（aiohttp 版本）。

    注册所有 API 路由，配置 Bearer token 中间件，
    加载 dashboard HTML，然后无限循环直到被取消。
    """
    _set_active_plugin(plugin)
    try:
        from aiohttp import web
    except ImportError:
        logger.warning(
            "Sylanne WebUI: aiohttp not installed, falling back to stdlib HTTP server"
        )
        start_webui_thread_server(plugin, host=host, port=port)
        return

    from pathlib import Path

    @web.middleware
    async def auth_middleware(request: web.Request, handler: Any) -> web.Response:
        if request.path in ("/", "/twin", "/favicon.ico", "/health", "/logo.png", "/assets/logo.png"):
            return await handler(request)
        # S9: /metrics requires Bearer token when auth is configured
        if request.path == "/metrics":
            if _active_token:
                auth = request.headers.get("Authorization", "")
                if not auth.startswith("Bearer ") or auth[7:] != _active_token:
                    return web.json_response({"error": "unauthorized"}, status=401)
            return await handler(request)
        auth = request.headers.get("Authorization", "")
        # fail-closed：_active_token 为空（未配置 / setup 未跑）时一律 401，绝不让空 Bearer
        # （Authorization: Bearer ）因 auth[7:]=="" == _active_token=="" 漏进受保护路由。
        # 正常运行 token 必被自动生成（setup 处 secrets.token_urlsafe），故零回归。
        if not _active_token or not auth.startswith("Bearer ") or auth[7:] != _active_token:
            return web.json_response({"error": "unauthorized"}, status=401)
        if (
            request.path in _LEGACY_SCOPED_PRIVATE_PATHS
            and getattr(_plugin(plugin), "_scope_runtime_registry", None) is not None
        ):
            return web.json_response({"error": "scope_required"}, status=410)
        # Item 24: CSRF 防护 — POST/DELETE 需要 X-CSRF-Token header
        if request.method in ("POST", "DELETE"):
            csrf_header = request.headers.get("X-CSRF-Token", "")
            if csrf_header != _csrf_token:
                return web.json_response({"error": "csrf_token_mismatch"}, status=403)
        return await handler(request)

    # Serve the dashboard HTML from UI/index.html（路径为模块级常量，避免 async 里 resolve）
    dashboard_path = _DASHBOARD_HTML_PATH
    if dashboard_path.exists():
        dashboard_html = dashboard_path.read_text(encoding="utf-8")
        logger.info(
            f"Sylanne WebUI: loaded dashboard from {dashboard_path} ({len(dashboard_html)} bytes)"
        )
    else:
        dashboard_html = (
            "<html><body><h1>Sylanne Dashboard unavailable</h1></body></html>"
        )

    app = web.Application(middlewares=[auth_middleware])

    def scoped_error(error: ScopedApiError) -> web.Response:
        return web.json_response(error.public_payload(), status=error.status)

    async def handle_scope_catalog(request: web.Request) -> web.Response:
        service = scoped_api_service_for_plugin(_plugin(plugin))
        if service is None:
            return scoped_error(ScopedApiError(410, "scope_required"))
        result = service.catalog_payload()
        if isinstance(result, ScopedApiError):
            return scoped_error(result)
        # The catalog is the first authenticated response on a fresh standalone
        # page.  It must seed the CSRF double-submit token before the client can
        # POST an exact-scope nonce bootstrap; no session payload is exposed here.
        return web.json_response({**result, "csrf_token": _csrf_token})

    async def handle_scope_bootstrap(request: web.Request) -> web.Response:
        service = scoped_api_service_for_plugin(_plugin(plugin))
        if service is None:
            return scoped_error(ScopedApiError(410, "scope_required"))
        if "session" in request.query:
            return scoped_error(ScopedApiError(400, "legacy_session_selector_forbidden"))
        try:
            path = ScopeApiPathEcho(
                bot_ref=request.match_info.get("bot_ref"),
                persona_ref=request.match_info.get("persona_ref"),
                session_ref=request.match_info.get("session_ref"),
            )
        except (TypeError, ValueError):
            return scoped_error(ScopedApiError(400, "invalid_scoped_request"))
        nonce = service.bootstrap_nonce(path)
        if isinstance(nonce, ScopedApiError):
            return scoped_error(nonce)
        return web.json_response(
            {
                "ok": True,
                "scope": {
                    "bot_ref": path.bot_ref,
                    "persona_ref": path.persona_ref,
                    "session_ref": path.session_ref,
                },
                "scope_nonce": nonce,
            }
        )

    async def handle_scoped_api(request: web.Request) -> web.StreamResponse:
        """Serve the sole private root through the host-neutral scope gate."""

        service = scoped_api_service_for_plugin(_plugin(plugin))
        if service is None:
            return scoped_error(ScopedApiError(410, "scope_required"))
        if "session" in request.query:
            return scoped_error(ScopedApiError(400, "legacy_session_selector_forbidden"))
        endpoint = str(request.match_info.get("endpoint", "") or "scope").strip("/")
        params = request.match_info
        try:
            scoped_request = ScopedApiRequest.from_tokens(
                bot_ref=params.get("bot_ref"),
                persona_ref=params.get("persona_ref"),
                session_ref=params.get("session_ref"),
                nonce=request.headers.get(SCOPE_NONCE_HEADER),
                endpoint=endpoint,
                method=request.method,
            )
        except (TypeError, ValueError):
            return scoped_error(ScopedApiError(400, "invalid_scoped_request"))
        authorization = service.authorize(scoped_request)
        if isinstance(authorization, ScopedApiError):
            return scoped_error(authorization)
        if not isinstance(authorization, ScopedApiAuthorization):
            return scoped_error(ScopedApiError(503, "scope_repository_unavailable"))
        if scoped_request.endpoint == "memory/meltdown-nonce":
            checked = service.revalidate(authorization)
            if isinstance(checked, ScopedApiError):
                return scoped_error(checked)
            meltdown_nonce = issue_scoped_meltdown_nonce(_plugin(plugin), checked)
            if isinstance(meltdown_nonce, ScopedApiError):
                return scoped_error(meltdown_nonce)
            payload = checked.public_payload()
            payload["meltdown_nonce"] = meltdown_nonce
            return web.json_response(payload)
        if scoped_request.endpoint == "memory/meltdown":
            try:
                body = await request.json()
            except Exception:  # noqa: BLE001 - malformed input is a client error
                body = None
            if type(body) is not dict or set(body) != {"meltdown_nonce"}:
                return scoped_error(ScopedApiError(400, "invalid_meltdown_request"))
            checked = service.revalidate(authorization)
            if isinstance(checked, ScopedApiError):
                return scoped_error(checked)
            nonce_error = consume_scoped_meltdown_nonce(
                _plugin(plugin),
                checked,
                body.get("meltdown_nonce"),
            )
            if nonce_error is not None:
                return scoped_error(nonce_error)
            return web.json_response(await purge_scoped_memory(_plugin(plugin), checked))
        if scoped_request.endpoint == "stream":
            response = web.StreamResponse(
                status=200,
                headers={
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                },
            )
            await response.prepare(request)
            stale_sent = False
            while True:
                response_task = response.task
                if response_task is None or response_task.done():
                    break
                checked = service.revalidate(authorization)
                if isinstance(checked, ScopedApiError):
                    if not stale_sent:
                        marker = json.dumps(service.stream_stale_payload(), separators=(",", ":"))
                        await response.write(f"event: scope_stale\ndata: {marker}\n\n".encode())
                        stale_sent = True
                    break
                heartbeat = json.dumps(checked.public_payload(), separators=(",", ":"))
                await response.write(f"event: scope_status\ndata: {heartbeat}\n\n".encode())
                await asyncio.sleep(1)
            await response.write_eof()
            return response
        if scoped_request.endpoint == "ws":
            socket = web.WebSocketResponse(heartbeat=30)
            await socket.prepare(request)
            stale_sent = False
            while not socket.closed:
                checked = service.revalidate(authorization)
                if isinstance(checked, ScopedApiError):
                    if not stale_sent:
                        await socket.send_json(service.stream_stale_payload())
                        stale_sent = True
                    await socket.close(code=4409, message=b"scope_stale")
                    break
                await socket.send_json(
                    {"event": "scope_status", "data": checked.public_payload()}
                )
                await asyncio.sleep(1)
            return socket
        return web.json_response(
            await scoped_api_payload(_plugin(plugin), authorization, scoped_request.endpoint)
        )

    async def handle_page(request: web.Request) -> web.Response:
        return web.Response(
            text=dashboard_html, content_type="text/html", charset="utf-8"
        )

    async def handle_twin_page(request: web.Request) -> web.Response:
        return web.Response(
            text=_TWIN_VIEWER_HTML, content_type="text/html", charset="utf-8"
        )

    async def handle_state(request: web.Request) -> web.Response:
        global _last_diag_request
        if _last_diag_request and time.time() - _last_diag_request > 30:
            current = _plugin(plugin)
            if current is not None:
                _set_spine_diagnostics(current, False)
        data = _build_state(
            _plugin(plugin), session=str(request.query.get("session", "") or "")
        )
        # Item 24: 在 state 响应中附带 csrf_token
        data["csrf_token"] = _csrf_token
        return web.json_response(data)

    async def handle_observation_history(request: web.Request) -> web.Response:
        try:
            payload = build_observation_history_payload(
                _plugin(plugin),
                request.query,
            )
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except RuntimeError as exc:
            return web.json_response({"error": str(exc)}, status=503)
        return web.json_response(payload)

    async def handle_life_status(request: web.Request) -> web.Response:
        """PR-B6：生活模拟只读可观测面板。

        暴露：节律(phase/energy/focus)、当前活动、最近事件、事件来源/隐私分布、
        统计计数、prompt fragment 预览。便于排查"为什么生成这个事件 /
        为什么没有主动发言"。只读，不修改状态。
        """
        current = _plugin(plugin)
        life_sim = getattr(current, "_life_simulator", None)
        if life_sim is None:
            return web.json_response({"enabled": False, "available": False})
        try:
            state = life_sim.state
            recent = state.events[-8:]
            # 来源/隐私分布（观测 life_sim 是否污染 user_fact）
            source_dist: dict[str, int] = {}
            privacy_dist: dict[str, int] = {}
            for e in state.events:
                source_dist[e.source or "unknown"] = source_dist.get(e.source or "unknown", 0) + 1
                privacy_dist[e.privacy_level or "unknown"] = privacy_dist.get(e.privacy_level or "unknown", 0) + 1
            import time as _t
            return web.json_response({
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
                    "seconds_since_tick": (
                        round(_t.time() - state.world.last_tick_at, 1)
                        if state.world.last_tick_at else None
                    ),
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
                    "seconds_since_outreach": (
                        round(_t.time() - state.last_outreach_time, 1)
                        if state.last_outreach_time else None
                    ),
                },
                "recent_events": [
                    {
                        "event_id": e.event_id,
                        "ts": e.timestamp,
                        "text": e.text,
                        "mood": e.mood,
                        "event_type": e.event_type,
                        "source": e.source,
                        "privacy_level": e.privacy_level,
                        "importance": round(e.importance, 3),
                        "wants_to_share": e.wants_to_share,
                        "shared": e.shared,
                    }
                    for e in recent
                ],
                "distribution": {
                    "source": source_dist,
                    "privacy": privacy_dist,
                },
                "prompt_fragment_preview": (life_sim.life_prompt_fragment(limit=3) or "")[:300],
            })
        except Exception as e:
            return web.json_response({"available": True, "error": f"{type(e).__name__}: {e}"})

    # ------------------------------------------------------------------
    # Phase 4：生活观测面板（events / projects / audit / diagnostics / controls）
    # ------------------------------------------------------------------

    async def handle_life_events(request: web.Request) -> web.Response:
        """GET /api/life/events — 最近 20 条生活事件（含 Phase 3 归属字段）。"""
        current = _plugin(plugin)
        life_sim = getattr(current, "_life_simulator", None)
        if life_sim is None:
            return web.json_response({"events": [], "available": False})
        try:
            state = life_sim.state
            events: list[dict[str, Any]] = []
            for ev in list(state.events[-20:]):
                events.append(
                    {
                        "event_id": getattr(ev, "event_id", "") or "",
                        "text": getattr(ev, "text", "") or "",
                        "event_type": getattr(ev, "event_type", "") or "",
                        "timestamp": float(getattr(ev, "timestamp", 0.0) or 0.0),
                        "source": getattr(ev, "source", "") or "",
                        "importance": round(float(getattr(ev, "importance", 0.5) or 0.0), 3),
                        "wants_to_share": bool(getattr(ev, "wants_to_share", False)),
                        "shared": bool(getattr(ev, "shared", False)),
                        "project_id": getattr(ev, "project_id", "") or "",
                        "origin_session": getattr(ev, "origin_session", "") or "",
                        "privacy_level": getattr(ev, "privacy_level", "") or "",
                    }
                )
            return web.json_response({"events": events, "available": True})
        except Exception as e:
            return web.json_response(
                {"events": [], "available": True, "error": f"{type(e).__name__}: {e}"}
            )

    async def handle_life_projects(request: web.Request) -> web.Response:
        """GET /api/life/projects — 活跃项目 + 技能库。"""
        current = _plugin(plugin)
        life_sim = getattr(current, "_life_simulator", None)
        if life_sim is None:
            return web.json_response({"projects": [], "skills": [], "available": False})
        try:
            from sylanne_alpha.life_simulation import _project_to_dict, _skill_to_dict
            projects = [_project_to_dict(p) for p in list(life_sim.state.projects)]
            skills = [_skill_to_dict(s) for s in list(life_sim.state.skills)]
            return web.json_response(
                {"projects": projects, "skills": skills, "available": True}
            )
        except Exception as e:
            return web.json_response(
                {
                    "projects": [],
                    "skills": [],
                    "available": True,
                    "error": f"{type(e).__name__}: {e}",
                }
            )

    async def handle_life_audit(request: web.Request) -> web.Response:
        """GET /api/life/audit — outreach 审计（M8 单一数据源 + Phase 3 分享决策）。"""
        current = _plugin(plugin)
        life_sim = getattr(current, "_life_simulator", None)
        if life_sim is None:
            return web.json_response({"audit": {}, "available": False})
        try:
            audit = {
                str(k): list(v or [])
                for k, v in dict(life_sim.state.outreach_audit or {}).items()
            }
            return web.json_response({"audit": audit, "available": True})
        except Exception as e:
            return web.json_response(
                {"audit": {}, "available": True, "error": f"{type(e).__name__}: {e}"}
            )

    async def handle_life_diagnostics(request: web.Request) -> web.Response:
        """GET /api/life/diagnostics — 一键完整状态导出（含 prompt fragment 预览）。"""
        current = _plugin(plugin)
        life_sim = getattr(current, "_life_simulator", None)
        if life_sim is None:
            return web.json_response({"available": False})
        try:
            data = life_sim.state.to_dict()
            try:
                data["prompt_fragment"] = life_sim.life_prompt_fragment(
                    limit=5, max_budget=2000
                )
            except TypeError:
                # 旧签名不支持 max_budget kwarg
                data["prompt_fragment"] = life_sim.life_prompt_fragment(limit=5)
            except Exception:
                data["prompt_fragment"] = ""
            data["available"] = True
            return web.json_response(data)
        except Exception as e:
            return web.json_response(
                {"available": True, "error": f"{type(e).__name__}: {e}"}
            )

    async def handle_life_controls(request: web.Request) -> web.Response:
        """POST /api/life/controls — 用户控制（开关 / 强度 / 清除 journal/projects/plan）。

        body: {"action": str, "value": Any}
        actions:
          - toggle_enabled              value: bool
          - set_share_intensity         value: off|low|standard|high
          - clear_journal               clear state.events
          - clear_projects              clear state.projects
          - clear_plan                  state.plan = None
        """
        current = _plugin(plugin)
        life_sim = getattr(current, "_life_simulator", None)
        if life_sim is None:
            return web.json_response(
                {"error": "life sim not available"}, status=400
            )
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            return web.json_response({"error": "invalid body"}, status=400)
        action = str(body.get("action", "") or "").strip()
        config = getattr(current, "_config", None)
        if config is None:
            config = {}
            current._config = config

        def _persist_config(key: str, value: Any) -> None:
            config[key] = value
            if hasattr(current, "config") and isinstance(current.config, dict):
                current.config[key] = value
                save = getattr(current.config, "save_config", None)
                if callable(save):
                    try:
                        save()
                    except Exception:
                        pass

        if action == "toggle_enabled":
            value = bool(body.get("value", False))
            _persist_config("sylanne_alpha_life_simulation_enabled", value)
            return web.json_response({"ok": True, "enabled": value})
        if action == "set_share_intensity":
            intensity = str(body.get("value", "standard") or "standard")
            if intensity not in ("off", "low", "standard", "high"):
                return web.json_response({"error": "invalid intensity"}, status=400)
            _persist_config(
                "sylanne_alpha_life_simulation_share_intensity", intensity
            )
            return web.json_response({"ok": True, "share_intensity": intensity})
        if action == "clear_journal":
            life_sim.state.events.clear()
            return web.json_response({"ok": True, "cleared": "events"})
        if action == "clear_projects":
            life_sim.state.projects.clear()
            return web.json_response({"ok": True, "cleared": "projects"})
        if action == "clear_plan":
            life_sim.state.plan = None
            return web.json_response({"ok": True, "cleared": "plan"})
        return web.json_response(
            {"error": f"unknown action: {action}"}, status=400
        )

    async def handle_settings_get(request: web.Request) -> web.Response:
        current_plugin = _plugin(plugin)
        return web.json_response(await _settings_payload(current_plugin))

    async def handle_settings_post(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            return web.json_response({"ok": False, "updated": []})
        current_plugin = _plugin(plugin)
        schema = _load_schema(current_plugin)
        config = getattr(current_plugin, "_config", {})
        updated = []
        for key, value in body.items():
            if key not in schema:
                continue
            # 敏感字段若收到掩码占位值，说明前端未改动，跳过避免覆盖真实值
            if _is_sensitive_key(key) and value == "********":
                continue
            meta = schema[key]
            # Type coercion per schema
            field_type = meta.get("type", "string")
            if field_type == "bool":
                value = bool(value)
            elif field_type == "int":
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    continue
            elif field_type == "float":
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    continue
            else:
                value = str(value)
            config[key] = value
            updated.append(key)
        if hasattr(current_plugin, "config") and isinstance(
            current_plugin.config, dict
        ):
            for key in updated:
                current_plugin.config[key] = config[key]
            if hasattr(current_plugin.config, "save_config"):
                current_plugin.config.save_config()
        return web.json_response({"ok": True, "updated": updated})

    async def handle_computation_logs(request: web.Request) -> web.Response:
        global _last_diag_request
        _last_diag_request = time.time()
        current = _plugin(plugin)
        if current is not None:
            _set_spine_diagnostics(current, True)
        try:
            limit = max(1, min(200, int(request.query.get("limit", "50"))))
        except (TypeError, ValueError):
            limit = 50
        session = str(request.query.get("session", "") or "").strip()
        logs = getattr(_plugin(plugin), "_computation_logs", None)
        if logs is None:
            return web.json_response(
                {"logs": [], "total": 0, "total_for_session": 0, "session": session}
            )
        all_entries = list(logs)
        session_entries = (
            [entry for entry in all_entries if str(entry.get("session", "")) == session]
            if session
            else all_entries
        )
        entries = session_entries[-limit:]
        return web.json_response(
            {
                "logs": entries,
                "total": len(logs),
                "total_for_session": len(session_entries),
                "session": session,
            }
        )

    async def handle_memory_pools(request: web.Request) -> web.Response:
        try:
            limit = max(1, min(100, int(request.query.get("limit", "50"))))
        except (TypeError, ValueError):
            limit = 50
        session = str(request.query.get("session", "") or "").strip()
        data = await _build_memory_pools(_plugin(plugin), session=session, limit=limit)
        return web.json_response(data)

    async def handle_logo(request: web.Request) -> web.Response:
        # 路径为模块级常量；.exists() 走 pathlib（ASYNC240 只报 os.path / .resolve()）
        if not _LOGO_PATH.exists():
            return web.Response(text="Not Found", status=404)
        data = await asyncio.to_thread(_LOGO_PATH.read_bytes)
        return web.Response(body=data, content_type="image/png")

    async def handle_memory_meltdown(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            return web.json_response({"ok": False, "error": "invalid_body"})
        session = str(body.get("session", "")).strip()
        nonce = str(body.get("nonce", "")).strip()
        expected = _meltdown_nonces.pop(session, None)
        if not nonce or nonce != expected:
            return web.json_response(
                {"ok": False, "error": "invalid_nonce"}, status=403
            )
        current_plugin = _plugin(plugin)
        mem_getter = getattr(current_plugin, "_memory_system_for_session", None)
        if callable(mem_getter):
            mem_sys = mem_getter(session)
            if mem_sys:
                mem_sys._l1.clear()
                mem_sys._l2.clear()
                mem_sys._l3_nodes.clear()
                mem_sys._l3_edges.clear()
                mem_sys._tick = 0
                # FIX(F2，完整性复审)：显式擦除必须置 _hydrated=True，否则懒创建时排的
                # 后台补水任务会把尚未删除的 KV 旧档合并回活体，令 meltdown 被自己的
                # 补水复活（详见 webui_routes 同名注释）。
                mem_sys._hydrated = True
        hosts = getattr(current_plugin, "_hosts", {}) or {}
        if session in hosts:
            hosts[session].kernel.body.memory["traces"] = []
            hosts[session].kernel.body.memory.pop("_memory_system", None)
        sp = getattr(current_plugin, "_state_persistence", None)
        if sp is not None and hasattr(sp, "purge_session_after_meltdown"):
            import asyncio as _asyncio

            await sp.purge_session_after_meltdown(session)
        logger.info(f"Sylanne MEMORY MELTDOWN (standalone): session={session}")
        return web.json_response({"ok": True, "session": session, "cleared": True})

    async def handle_meltdown_nonce(request: web.Request) -> web.Response:
        session = str(request.query.get("session", "") or "").strip()
        nonce = secrets.token_urlsafe(16)
        _meltdown_nonces[session] = nonce
        return web.json_response({"nonce": nonce})

    async def handle_memory_sink(request: web.Request) -> web.Response:
        """手动触发 L1→L2 记忆下沉（独立服务器版本）。"""
        session = str(request.query.get("session", "") or "").strip()
        if not session:
            return web.json_response({"ok": False, "error": "missing session param"})
        current_plugin = _plugin(plugin)
        mem_getter = getattr(current_plugin, "_memory_system_for_session", None)
        mem_sys = mem_getter(session) if callable(mem_getter) else getattr(current_plugin, "_memory_system", None)
        if mem_sys is None:
            return web.json_response({"ok": False, "error": "memory system unavailable"})
        candidates = mem_sys.consolidation_candidates()
        if not candidates:
            return web.json_response({"ok": False, "error": "no_confirmed_items", "sunk": 0})
        item_ids = [item.id for item in candidates]
        mem_sys.sink_to_l2(item_ids)
        logger.info(f"Sylanne MEMORY SINK (standalone): session={session}, sunk={len(item_ids)}")
        return web.json_response({"ok": True, "sunk": len(item_ids)})

    async def handle_memory_consolidate(request: web.Request) -> web.Response:
        """POST /api/memory_consolidate — 触发后台 consolidation 评估。"""
        try:
            body = await request.json()
        except Exception:
            body = {}
        session = str((body or {}).get("session", "")).strip()
        if not session:
            return web.json_response({"ok": False, "error": "missing session param"})
        current_plugin = _plugin(plugin)
        mem_getter = getattr(current_plugin, "_memory_system_for_session", None)
        mem_sys = mem_getter(session) if callable(mem_getter) else getattr(current_plugin, "_memory_system", None)
        if mem_sys is None or not list(mem_sys._l1):
            return web.json_response({"ok": True, "estimated_seconds": 0})
        try:
            asyncio.ensure_future(current_plugin._trigger_consolidation(session))
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)})
        return web.json_response({"ok": True, "estimated_seconds": 30})

    async def handle_config_presets(request: web.Request) -> web.Response:
        """GET /api/config_presets — 返回人格配置预设模板。"""
        from sylanne_alpha.webui_routes import CONFIG_PRESETS

        return web.json_response({"presets": CONFIG_PRESETS})

    async def handle_glossary(request: web.Request) -> web.Response:
        """GET /api/glossary — 返回 Sylanne 专有术语词典。"""
        from sylanne_alpha.webui_routes import GLOSSARY

        return web.json_response({"glossary": GLOSSARY})

    async def handle_export_data(request: web.Request) -> web.Response:
        """GET /api/export_data?session_key=xxx — 导出指定会话的所有数据。"""
        session_key = str(request.query.get("session_key", "") or "").strip()
        if not session_key:
            return web.json_response({"ok": False, "error": "missing session_key param"})
        current_plugin = _plugin(plugin)
        export: dict[str, Any] = {"session_key": session_key}

        # Memory system
        mem_getter = getattr(current_plugin, "_memory_system_for_session", None)
        mem_sys = mem_getter(session_key) if callable(mem_getter) else getattr(current_plugin, "_memory_system", None)
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
                    for k, v in dict(getattr(mem_sys, "_l3_nodes", {}) or {}).items()
                },
                "l3_edges": [
                    e.to_dict() if hasattr(e, "to_dict") else dict(e or {})
                    for e in list(getattr(mem_sys, "_l3_edges", []) or [])
                ],
            }

        # Personality & computation state
        hosts_dict = getattr(current_plugin, "_hosts", {}) or {}
        if session_key in hosts_dict:
            host_obj = hosts_dict[session_key]
            comp = host_obj.kernel.computation
            export["personality"] = dict(comp._personality)
            export["computation"] = comp.to_dict()
        else:
            export["personality"] = None
            export["computation"] = None

        return web.json_response({"ok": True, "data": export})

    async def handle_purge_data(request: web.Request) -> web.Response:
        """DELETE /api/purge_data?session_key=xxx — 彻底删除指定会话的所有数据。"""
        session_key = str(request.query.get("session_key", "") or "").strip()
        if not session_key:
            return web.json_response({"ok": False, "error": "missing session_key param"})
        current_plugin = _plugin(plugin)
        purged: list[str] = []

        # Clear memory system
        mem_getter = getattr(current_plugin, "_memory_system_for_session", None)
        mem_sys = mem_getter(session_key) if callable(mem_getter) else getattr(current_plugin, "_memory_system", None)
        if mem_sys is not None:
            mem_sys._l1.clear()
            mem_sys._l2.clear()
            mem_sys._l3_nodes.clear()
            mem_sys._l3_edges.clear()
            mem_sys._tick = 0
            # FIX(F1，完整性复审)：同 meltdown——置 _hydrated=True 阻断懒创建补水任务
            # 把刚清空的记忆从 KV 旧档复活回活体再被周期 save 写回。
            mem_sys._hydrated = True
            purged.append("memory_system")

        # Remove host instance
        hosts_dict = getattr(current_plugin, "_hosts", {}) or {}
        if session_key in hosts_dict:
            del hosts_dict[session_key]
            purged.append("host")

        # Clear conversation buffer
        buffers = getattr(current_plugin, "_conversation_buffers", {}) or {}
        if session_key in buffers:
            del buffers[session_key]
            purged.append("conversation_buffer")

        # Delete persisted KV states
        for delete_method in (
            "_delete_state",
            "_delete_humanlike_state",
            "_delete_personality_drift_state",
            "_delete_sylanne_memory_state",
        ):
            try:
                deleter = getattr(current_plugin, delete_method, None)
                if callable(deleter):
                    await deleter(session_key)
                    purged.append(f"kv_{delete_method}")
            except Exception:
                pass

        logger.info(f"Sylanne PURGE DATA (standalone): session={session_key}, purged={purged}")
        return web.json_response({"ok": True, "session_key": session_key, "purged": purged})

    # ------------------------------------------------------------------
    # Item 47: /health 健康检查（不需要认证）
    # ------------------------------------------------------------------

    async def handle_health(request: web.Request) -> web.Response:
        uptime_s = int(time.time() - _start_time)
        # 活跃 host 数量
        current = _plugin(plugin)
        hosts_dict = getattr(current, "_hosts", {}) or {}
        sessions_count = len(hosts_dict) if isinstance(hosts_dict, dict) else 0
        # 进程内存
        memory_mb = _get_process_memory_mb()
        return web.json_response({
            "status": "ok",
            "uptime_s": uptime_s,
            "sessions": sessions_count,
            "memory_mb": memory_mb,
        })

    # ------------------------------------------------------------------
    # Item 48: /metrics Prometheus 指标导出（需要 Bearer token 认证）
    # ------------------------------------------------------------------

    async def handle_metrics(request: web.Request) -> web.Response:
        metrics_text = _build_metrics()
        return web.Response(
            text=metrics_text,
            content_type="text/plain; version=0.0.4; charset=utf-8",
        )

    # ------------------------------------------------------------------
    # Item 49: /api/error_stats 错误率仪表盘
    # ------------------------------------------------------------------

    async def handle_error_stats(request: web.Request) -> web.Response:
        cutoff = int(time.time()) // 60 * 60 - 3600
        with _error_counts_lock:
            data = [
                {"minute": ts, "errors": errs, "warnings": warns}
                for ts, errs, warns in _error_counts
                if ts >= cutoff
            ]
        return web.json_response(data)

    # ------------------------------------------------------------------
    # Item 53: /api/config_export & /api/config_import
    # ------------------------------------------------------------------

    async def handle_config_export(request: web.Request) -> web.Response:
        current_plugin = _plugin(plugin)
        config = dict(getattr(current_plugin, "_config", {}) or {})
        # S1: 过滤敏感键
        config = {k: v for k, v in config.items() if not _is_sensitive_key(k)}
        return web.json_response(config)

    async def handle_config_import(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "invalid_json"}, status=400)
        if not isinstance(body, dict):
            return web.json_response({"ok": False, "error": "expected_object"}, status=400)
        # S2: 拒绝写入敏感键
        sensitive_found = [k for k in body if _is_sensitive_key(k)]
        if sensitive_found:
            return web.json_response({"ok": False, "error": "cannot_import_sensitive_keys", "keys": sensitive_found}, status=403)
        current_plugin = _plugin(plugin)
        config = getattr(current_plugin, "_config", None)
        if config is None:
            return web.json_response({"ok": False, "error": "no_config"}, status=500)
        config.update(body)
        # 持久化
        persistent = getattr(current_plugin, "config", config)
        if isinstance(persistent, dict):
            persistent.update(body)
        if hasattr(persistent, "save_config"):
            persistent.save_config()
        return web.json_response({"ok": True, "keys": list(body.keys())})

    # ------------------------------------------------------------------
    # Item 66: /api/widget-state AstrBot 管理面板状态卡片
    # ------------------------------------------------------------------

    async def handle_widget_state(request: web.Request) -> web.Response:
        current = _plugin(plugin)
        data = _build_widget_state(current)
        return web.json_response(data)

    # ------------------------------------------------------------------
    # Item 6: POST /api/proactive_feedback 主动发言反馈
    # ------------------------------------------------------------------

    async def handle_proactive_feedback(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            return web.json_response({"ok": False, "error": "invalid_body"}, status=400)
        session_key = str(body.get("session_key", "")).strip()
        timestamp = float(body.get("timestamp", 0))
        rating = str(body.get("rating", "")).strip()
        if not session_key or not rating or rating not in ("positive", "negative"):
            return web.json_response({"ok": False, "error": "invalid_params"}, status=400)
        current = _plugin(plugin)
        scheduler = getattr(current, "_proactive_scheduler", None)
        if scheduler is not None and hasattr(scheduler, "record_feedback"):
            scheduler.record_feedback(session_key, timestamp, rating)
        return web.json_response({"ok": True})

    # ------------------------------------------------------------------
    # Item 69: GET /api/weekly_report 周报自动生成
    # ------------------------------------------------------------------

    async def handle_weekly_report(request: web.Request) -> web.Response:
        from sylanne_alpha.analytics import generate_weekly_report
        current = _plugin(plugin)
        report = generate_weekly_report(current)
        return web.json_response(report)

    # ------------------------------------------------------------------
    # Item 70: GET /api/memory/decay_curve 记忆衰减曲线可视化数据
    # ------------------------------------------------------------------

    async def handle_memory_decay_curve(request: web.Request) -> web.Response:
        """返回指定记忆的 Ebbinghaus 衰减时间序列。"""
        import math as _math

        memory_id = str(request.query.get("memory_id", "") or "").strip()
        if not memory_id:
            return web.json_response(
                {"ok": False, "error": "missing memory_id param"}, status=400
            )
        current_plugin = _plugin(plugin)
        # 在所有会话的记忆系统中查找目标记忆
        target_memory = None
        hosts_dict = getattr(current_plugin, "_hosts", {}) or {}
        mem_getter = getattr(current_plugin, "_memory_system_for_session", None)
        for sk in list(hosts_dict.keys()):
            mem_sys = mem_getter(sk) if callable(mem_getter) else None
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
            return web.json_response(
                {"ok": False, "error": "memory_id not found"}, status=404
            )

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
        max_hours = 168
        for hour in range(max_hours + 1):
            retention = max(0.05, _math.exp(-hour / stability))
            curve.append({"hour": hour, "retention": round(retention, 4)})

        return web.json_response({
            "memory_id": memory_id,
            "created_at": created_at,
            "stability": round(stability, 2),
            "rehearsal": rehearsal,
            "emotional_weight": round(emotional_weight, 3),
            "curve": curve,
        })

    # ------------------------------------------------------------------
    # GET /api/memory/recall_debug 召回引擎调试快照（灰度模式/影子差异/参数）
    # ------------------------------------------------------------------

    async def handle_memory_recall_debug(request: web.Request) -> web.Response:
        """返回指定会话记忆系统的召回调试快照（含 recall_mode、影子差异统计）。"""
        session = str(request.query.get("session", "") or "").strip() or "default"
        current_plugin = _plugin(plugin)
        mem_getter = getattr(current_plugin, "_memory_system_for_session", None)
        if not callable(mem_getter):
            return web.json_response(
                {"ok": False, "error": "memory system unavailable"}, status=503
            )
        mem_sys = mem_getter(session)
        snap_fn = getattr(mem_sys, "get_debug_snapshot", None)
        if not callable(snap_fn):
            return web.json_response(
                {"ok": False, "error": "snapshot unsupported"}, status=501
            )
        return web.json_response({"ok": True, "session": session, "snapshot": snap_fn()})

    # ------------------------------------------------------------------
    # Item 84: GET/POST /api/personality/export & /api/personality/import
    # ------------------------------------------------------------------

    async def handle_personality_export(request: web.Request) -> web.Response:
        """GET /api/personality/export — 导出当前人格参数。"""
        current_plugin = _plugin(plugin)
        hosts_dict = getattr(current_plugin, "_hosts", {}) or {}
        personality: dict[str, Any] = {}
        for h in hosts_dict.values():
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
        frontend_data = _frontend_personality(personality)
        export_payload = {
            "embodiment_five": frontend_data.get("five", {}),
            "sylanne_six": {
                item["name"]: item["value"]
                for item in frontend_data.get("six", [])
            },
            "drift_history": frontend_data.get("drift", []),
            "description": "",
        }
        return web.json_response({"ok": True, "personality": export_payload})

    async def handle_personality_import(request: web.Request) -> web.Response:
        """POST /api/personality/import — 导入人格配置 JSON。"""
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            return web.json_response({"ok": False, "error": "expected JSON object"}, status=400)
        embodiment_five = body.get("embodiment_five")
        sylanne_six = body.get("sylanne_six")
        if not isinstance(embodiment_five, dict) and not isinstance(sylanne_six, dict):
            return web.json_response({"ok": False, "error": "missing embodiment_five or sylanne_six"}, status=400)
        current_plugin = _plugin(plugin)
        hosts_dict = getattr(current_plugin, "_hosts", {}) or {}
        updated_sessions: list[str] = []
        six_name_to_key = {
            "Curiosity": "curiosity", "Empathy": "warmth", "Precision": "coherence",
            "Playfulness": "playfulness", "Defiance": "sovereignty", "Melancholy": "melancholy",
        }
        for sk, h in hosts_dict.items():
            try:
                comp = h.kernel.computation
                personality_dict = comp._personality
                if not isinstance(personality_dict, dict):
                    continue
                traits = personality_dict.setdefault("traits", {})
                if isinstance(embodiment_five, dict):
                    for key, value in embodiment_five.items():
                        try:
                            traits[key] = float(value)
                        except (TypeError, ValueError):
                            continue
                if isinstance(sylanne_six, dict):
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
            return web.json_response({"ok": False, "error": "no active sessions to update"})
        return web.json_response({"ok": True, "updated_sessions": updated_sessions})

    # ------------------------------------------------------------------
    # Item 112: GET/POST /api/theme 主题系统
    # ------------------------------------------------------------------

    async def handle_theme_get(request: web.Request) -> web.Response:
        global _theme_preference
        return web.json_response({"theme": _theme_preference})

    async def handle_theme_post(request: web.Request) -> web.Response:
        global _theme_preference
        try:
            body = await request.json()
        except Exception:
            body = {}
        theme = str((body or {}).get("theme", "")).strip()
        if theme not in ("dark", "light", "auto"):
            return web.json_response({"ok": False, "error": "invalid theme, must be dark|light|auto"}, status=400)
        _theme_preference = theme
        return web.json_response({"ok": True, "theme": _theme_preference})

    # ------------------------------------------------------------------
    # Item 5: GET /api/rhythm_profile 对话节奏可视化数据
    # ------------------------------------------------------------------

    async def handle_rhythm_profile(request: web.Request) -> web.Response:
        current = _plugin(plugin)
        rhythm_learner = getattr(current, "_rhythm_learner", None)
        if rhythm_learner is None:
            return web.json_response({"ok": False, "error": "rhythm_learner unavailable"})
        # 确定当前活跃会话
        session = str(request.query.get("session", "") or "").strip()
        if not session:
            hosts = getattr(current, "_hosts", {}) or {}
            if isinstance(hosts, dict) and hosts:
                session = next(iter(hosts))
            else:
                session = "default"
        profile = rhythm_learner.profile(session)
        tempo = rhythm_learner.tempo
        reply_length_factor = rhythm_learner.get_reply_length_factor(session)
        # breath_hold: 需要最后一条消息时间
        last_msg_time = 0.0
        if profile is not None:
            last_msg_time = profile._last_msg_time
        breath_hold = rhythm_learner.detect_breath_hold(last_msg_time, time.time()) if last_msg_time > 0 else False
        avg_message_length = profile.avg_part_chars if profile is not None else 0.0
        return web.json_response({
            "ok": True,
            "session": session,
            "tempo": round(tempo, 3),
            "avg_message_length": round(avg_message_length, 1),
            "reply_length_factor": round(reply_length_factor, 3),
            "breath_hold": breath_hold,
            "confidence": round(profile.confidence, 3) if profile is not None else 0.0,
            "chars_per_second": round(profile.chars_per_second, 2) if profile is not None else 0.0,
        })

    # ------------------------------------------------------------------
    # Item 40: GET /api/relationship_temperature 关系温度计
    # ------------------------------------------------------------------

    async def handle_relationship_temperature(request: web.Request) -> web.Response:
        current = _plugin(plugin)
        hosts_dict = getattr(current, "_hosts", {}) or {}
        all_sessions = _known_sessions(current)
        session_key = str(request.query.get("session", "") or "").strip()
        if not session_key and all_sessions:
            session_key = all_sessions[0]

        temperature = 0.5
        trend = "stable"
        try:
            host = hosts_dict.get(session_key) if isinstance(hosts_dict, dict) else None
            if host is not None:
                comp = host.kernel.computation
                engine_obs = comp.engine.observe()
                warmth = float(engine_obs.get("warmth", 0.0))
                # 从 session_context 获取关系年龄信息
                sc = getattr(current, "_session_context", None)
                intimacy = 0.0
                if sc is not None:
                    first_time = sc.first_interaction_time(session_key)
                    age_days = (time.time() - first_time) / 86400
                    # 关系年龄贡献：越久越高，上限 0.3
                    intimacy = min(0.3, age_days / 365 * 0.3)
                # 近期互动频率：从 computation logs 估算
                logs = getattr(current, "_computation_logs", None)
                freq_bonus = 0.0
                if logs:
                    now = time.time()
                    recent = sum(
                        1 for e in logs
                        if str(e.get("session", "")) == session_key
                        and now - float(e.get("ts", 0)) < 3600
                    )
                    freq_bonus = min(0.2, recent * 0.02)
                temperature = max(0.0, min(1.0, 0.3 + warmth * 0.3 + intimacy + freq_bonus))
                # 趋势判断：基于 warmth 正负
                if warmth > 0.1:
                    trend = "warming"
                elif warmth < -0.1:
                    trend = "cooling"
        except Exception:
            pass
        return web.json_response({"temperature": round(temperature, 4), "trend": trend})

    # ------------------------------------------------------------------
    # Item 60: GET /api/diagnostic_report 自动诊断报告
    # ------------------------------------------------------------------

    async def handle_diagnostic_report(request: web.Request) -> web.Response:
        current = _plugin(plugin)
        hosts_dict = getattr(current, "_hosts", {}) or {}
        anomalies: list[str] = []
        total_sessions = len(_known_sessions(current))
        total_memories = 0
        total_scars = 0
        spine_ok = True
        memory_ok = True
        personality_ok = True

        try:
            mem_getter = getattr(current, "_memory_system_for_session", None)
            if callable(mem_getter) and isinstance(hosts_dict, dict):
                for sk in hosts_dict:
                    ms = mem_getter(sk)
                    if ms:
                        total_memories += len(getattr(ms, "_l1", []) or [])
                        total_memories += len(getattr(ms, "_l2", []) or [])
        except Exception:
            memory_ok = False

        try:
            for h in (hosts_dict.values() if isinstance(hosts_dict, dict) else []):
                comp = h.kernel.computation
                engine_obs = comp.engine.observe()
                total_scars += int(engine_obs.get("active_scars", engine_obs.get("scar_count", 0)))
                # 检查人格维度是否被 clamp
                personality = h.kernel._personality() if hasattr(h.kernel, "_personality") else {}
                traits = personality.get("traits", personality) if isinstance(personality, dict) else {}
                for dim, val in (traits.items() if isinstance(traits, dict) else []):
                    if isinstance(val, (int, float)):
                        if val >= 1.0:
                            anomalies.append(f"personality.{dim} was clamped from >{val:.1f} to 1.0")
                        elif val <= 0.0:
                            anomalies.append(f"personality.{dim} was clamped from <{val:.1f} to 0.0")
        except Exception:
            spine_ok = False

        # 运行时间估算
        uptime_hours = 0.0
        try:
            import os as _os
            pid = _os.getpid()
            import psutil  # type: ignore
            proc = psutil.Process(pid)
            uptime_hours = round((time.time() - proc.create_time()) / 3600, 1)
        except Exception:
            pass

        return web.json_response({
            "timestamp": int(time.time()),
            "health": {"spine_ok": spine_ok, "memory_ok": memory_ok, "personality_ok": personality_ok},
            "stats": {
                "total_sessions": total_sessions,
                "total_memories": total_memories,
                "total_scars": total_scars,
                "uptime_hours": uptime_hours,
            },
            "anomalies": anomalies,
            "version": _get_plugin_version(),
        })

    # ------------------------------------------------------------------
    # Item 118: GET /api/personality/drift-map 人格漂移可视化
    # ------------------------------------------------------------------

    async def handle_personality_drift_map(request: web.Request) -> web.Response:
        current = _plugin(plugin)
        hosts_dict = getattr(current, "_hosts", {}) or {}
        session_key = str(request.query.get("session", "") or "").strip()
        all_sessions = _known_sessions(current, requested=session_key)
        if not session_key and all_sessions:
            session_key = all_sessions[0]

        events: list[dict] = []
        current_traits: dict[str, float] = {}
        try:
            host = hosts_dict.get(session_key) if isinstance(hosts_dict, dict) else None
            if host is not None:
                comp = host.kernel.computation
                drift_attr = getattr(comp, "_drift_attribution", None)
                if drift_attr is not None:
                    n = int(request.query.get("limit", "50") or "50")
                    events = drift_attr.recent(n)
                # 当前特质值
                personality = host.kernel._personality() if hasattr(host.kernel, "_personality") else {}
                traits = personality.get("traits", personality) if isinstance(personality, dict) else {}
                if isinstance(traits, dict):
                    current_traits = {k: round(float(v), 4) for k, v in traits.items() if isinstance(v, (int, float))}
        except Exception:
            pass
        return web.json_response({"events": events, "current_traits": current_traits})

    # ------------------------------------------------------------------
    # Phase G: GET /api/twin_synchrony_trajectory 二重奏跨会话同步度轨迹
    # ------------------------------------------------------------------

    async def handle_twin_synchrony(request: web.Request) -> web.Response:
        """二重奏同步度轨迹（v2core UserModelDomain）：她越来越懂你的那条收敛曲线。"""
        current = _plugin(plugin)
        session = str(request.query.get("session", "") or "").strip()
        limit = max(1, min(200, int(request.query.get("limit", "200") or "200")))
        return web.json_response(_twin_synchrony_payload(current, session=session, limit=limit))

    # ------------------------------------------------------------------
    # 认知核页: GET /api/v2core_state — 三拍/四域/裁决/心象投影（纯只读）
    # ------------------------------------------------------------------

    async def handle_v2core_state(request: web.Request) -> web.Response:
        """v2core 认知核状态（SPA 第二页消费）：四域真状态 + 最近裁决 + 心象片段。"""
        current = _plugin(plugin)
        session = str(request.query.get("session", "") or "").strip()
        return web.json_response(_v2core_state_payload(current, session=session))

    # ------------------------------------------------------------------
    # Item 114: GET /api/quality-trend 对话质量趋势
    # ------------------------------------------------------------------

    async def handle_quality_trend(request: web.Request) -> web.Response:
        """聚合 dialogue.self_score 历史数据，返回最近 N 轮的分数列表。"""
        from sylanne_alpha.dialogue import self_score

        current = _plugin(plugin)
        session_key = str(request.query.get("session", "") or "").strip()
        all_sessions = _known_sessions(current, requested=session_key)
        if not session_key and all_sessions:
            session_key = all_sessions[0]

        limit = max(1, min(200, int(request.query.get("limit", "50") or "50")))
        scores: list[dict] = []

        try:
            # 从 computation_logs 中提取用户文本和 bot 回复，计算 self_score
            logs = getattr(current, "_computation_logs", None)
            if logs:
                session_logs = [
                    e for e in logs
                    if str(e.get("session", "")) == session_key
                ][-limit:]
                buffers = getattr(current, "_conversation_buffers", {}) or {}
                buf = buffers.get(session_key)
                tick = 0
                for entry in session_logs:
                    tick += 1
                    user_text = str(entry.get("text", ""))
                    # 尝试获取对应的 bot 回复
                    bot_text = ""
                    if buf and hasattr(buf, "_messages"):
                        for i, msg in enumerate(getattr(buf, "_messages", [])):
                            if msg.get("role") == "user" and msg.get("text", "")[:60] == user_text:
                                if i + 1 < len(getattr(buf, "_messages", [])):
                                    next_msg = getattr(buf, "_messages", [])[i + 1]
                                    if next_msg.get("role") == "bot":
                                        bot_text = str(next_msg.get("text", ""))
                                break
                    if not bot_text:
                        bot_text = user_text  # fallback
                    score = self_score(user_text, bot_text)
                    scores.append({
                        "tick": tick,
                        "coherence": round(score.get("coherence", 0.0), 4),
                        "emotion": round(score.get("emotion_match", 0.0), 4),
                        "density": round(score.get("info_density", 0.0), 4),
                    })
        except Exception:
            pass
        return web.json_response({"scores": scores})

    # ------------------------------------------------------------------
    # Item 32: GET /api/scar_map 伤痕可视化地图数据
    # ------------------------------------------------------------------

    async def handle_scar_map(request: web.Request) -> web.Response:
        """返回伤痕力导向图数据：nodes + edges。"""
        current = _plugin(plugin)
        session_key = str(request.query.get("session", "") or "").strip()
        hosts_dict = getattr(current, "_hosts", {}) or {}
        all_sessions = _known_sessions(current, requested=session_key)
        if not session_key and all_sessions:
            session_key = all_sessions[0]

        nodes: list[dict] = []
        edges: list[dict] = []
        try:
            host = hosts_dict.get(session_key) if isinstance(hosts_dict, dict) else None
            if host is not None:
                comp = host.kernel.computation
                scar_state = getattr(comp.engine, "scar_state", None)
                if scar_state is not None:
                    for idx, scar in enumerate(scar_state.scars):
                        nodes.append({
                            "id": f"scar_{idx}",
                            "dimension": scar.dimension,
                            "intensity": round(scar.alpha, 3),
                            "temperature": round(
                                1.0 - scar.ticks_in_stage / max(1, 150), 3
                            ),
                            "state": scar.stage.name.lower(),
                        })
                    # edges: 同维度伤痕之间的耦合
                    from collections import defaultdict
                    dim_groups: dict[int, list[int]] = defaultdict(list)
                    for idx, scar in enumerate(scar_state.scars):
                        dim_groups[scar.dimension].append(idx)
                    for dim, indices in dim_groups.items():
                        for i in range(len(indices)):
                            for j in range(i + 1, len(indices)):
                                # 耦合强度：两个伤痕 alpha 的几何平均
                                a_i = scar_state.scars[indices[i]].alpha
                                a_j = scar_state.scars[indices[j]].alpha
                                coupling = round((a_i * a_j) ** 0.5 / 2.0, 3)
                                edges.append({
                                    "source": f"scar_{indices[i]}",
                                    "target": f"scar_{indices[j]}",
                                    "coupling": coupling,
                                })
        except Exception:
            pass
        return web.json_response({"nodes": nodes, "edges": edges})

    # ------------------------------------------------------------------
    # Item 52: GET /api/sheaf_topology 关系层析可视化数据
    # ------------------------------------------------------------------

    async def handle_sheaf_topology(request: web.Request) -> web.Response:
        """返回关系层析拓扑数据：nodes + edges + cohomology_h1。"""
        from sylanne_alpha._engine.sylanne_core.compute.relational_sheaf import _REL_TYPE_NAMES

        current = _plugin(plugin)
        session_key = str(request.query.get("session", "") or "").strip()
        hosts_dict = getattr(current, "_hosts", {}) or {}
        all_sessions = _known_sessions(current, requested=session_key)
        if not session_key and all_sessions:
            session_key = all_sessions[0]

        nodes: list[dict] = []
        edges: list[dict] = []
        h1 = 0.0
        try:
            host = hosts_dict.get(session_key) if isinstance(hosts_dict, dict) else None
            if host is not None:
                sheaf = host.kernel.computation.sheaf
                obs = sheaf.observe()
                h1 = obs.get("h1_dim", 0)
                # 构建节点：每个顶点（partner）
                complex_ = sheaf.complex
                for v in complex_._vertices:
                    if v == 0:
                        nodes.append({"id": "agent", "type": "self"})
                    else:
                        edge_idx = complex_.edge_index(v)
                        rel_type_int = (
                            sheaf._rel_types[edge_idx]
                            if edge_idx < len(sheaf._rel_types)
                            else 1
                        )
                        type_name = (
                            _REL_TYPE_NAMES[rel_type_int]
                            if rel_type_int < len(_REL_TYPE_NAMES)
                            else "friendly"
                        )
                        nodes.append({"id": f"partner_{v}", "type": type_name})
                # 构建边
                incon = obs.get("inconsistency_per_edge", [])
                for ei, (_, partner) in enumerate(complex_._edges):
                    coupling = round(
                        1.0 - (incon[ei] if ei < len(incon) else 0.0), 4
                    )
                    edges.append({
                        "source": "agent",
                        "target": f"partner_{partner}",
                        "coupling": coupling,
                    })
        except Exception:
            pass
        return web.json_response({
            "nodes": nodes,
            "edges": edges,
            "cohomology_h1": h1,
        })

    # ------------------------------------------------------------------
    # Item 138: GET /api/topic-gravity 话题重力可视化数据
    # ------------------------------------------------------------------

    async def handle_topic_gravity(request: web.Request) -> web.Response:
        """返回话题重力场数据。"""
        import math as _math

        current = _plugin(plugin)
        session_key = str(request.query.get("session", "") or "").strip()
        hosts_dict = getattr(current, "_hosts", {}) or {}
        all_sessions = _known_sessions(current, requested=session_key)
        if not session_key and all_sessions:
            session_key = all_sessions[0]

        topics: list[dict] = []
        try:
            host = hosts_dict.get(session_key) if isinstance(hosts_dict, dict) else None
            if host is not None:
                tg = getattr(host, "_topic_gravity", None) or getattr(
                    host.kernel, "_topic_gravity", None
                )
                if tg is None:
                    # 尝试从插件级别获取
                    tg = getattr(current, "_topic_gravity", None)
                if tg is not None:
                    now = time.time()
                    for name, node in tg._topics.items():
                        age = now - node.last_active
                        half_life = getattr(tg, "_half_life", 7200)
                        decay = _math.exp(-age * _math.log(2) / half_life)
                        topics.append({
                            "name": node.name,
                            "mass": round(node.mass * decay, 4),
                            "decay_factor": round(decay, 4),
                            "visits": node.visit_count,
                        })
                    topics.sort(key=lambda x: x["mass"], reverse=True)
        except Exception:
            pass
        return web.json_response({"topics": topics})

    # ------------------------------------------------------------------
    # MEM-03 PR-7: GET /api/admin/inspect|quarantine_view|pending_deletes
    # 三只读 admin 端点——诚实只读，builder 见模块级 _admin_* 函数（两个消费面
    # 共享同一份 builder，见 _v2core_state_payload 上方注释的既有共享模式）。
    # ------------------------------------------------------------------

    async def handle_admin_inspect(request: web.Request) -> web.Response:
        """单 session 记忆诊断：KV 键存在性/字节数/version/backup CRC、
        _hydrated/_incarnation_epoch vs 当前纪元、写咽喉队深/拒写计数。"""
        current = _plugin(plugin)
        session = str(request.query.get("session", "") or "").strip()
        return web.json_response(await _admin_inspect_payload(current, session=session))

    async def handle_admin_quarantine_view(request: web.Request) -> web.Response:
        """quarantine 侧车只读视图（此前只写不读的缺口）。"""
        current = _plugin(plugin)
        session = str(request.query.get("session", "") or "").strip()
        return web.json_response(
            await _admin_quarantine_view_payload(current, session=session)
        )

    async def handle_admin_pending_deletes(request: web.Request) -> web.Response:
        """跨重启 pending-delete 索引进程内镜像快照。"""
        current = _plugin(plugin)
        return web.json_response(_admin_pending_deletes_payload(current))

    app.router.add_get("/", handle_page)
    app.router.add_get("/twin", handle_twin_page)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/metrics", handle_metrics)
    scope_catalog_root = "/api/scopes"
    scope_bootstrap_root = (
        "/api/scopes/{bot_ref}/personas/{persona_ref}/sessions/{session_ref}/nonce"
    )
    app.router.add_get(scope_catalog_root, handle_scope_catalog)
    app.router.add_post(scope_bootstrap_root, handle_scope_bootstrap)
    scoped_root = "/api/v1/bots/{bot_ref}/personas/{persona_ref}/sessions/{session_ref}"
    app.router.add_route("*", scoped_root, handle_scoped_api)
    app.router.add_route("*", f"{scoped_root}/{{endpoint:.*}}", handle_scoped_api)
    app.router.add_get("/api/state", handle_state)
    app.router.add_get("/api/observation_history", handle_observation_history)
    app.router.add_get("/api/life/status", handle_life_status)  # PR-B6 只读观测
    # Phase 4：生活观测面板（events / projects / audit / diagnostics / controls）
    app.router.add_get("/api/life/events", handle_life_events)
    app.router.add_get("/api/life/projects", handle_life_projects)
    app.router.add_get("/api/life/audit", handle_life_audit)
    app.router.add_get("/api/life/diagnostics", handle_life_diagnostics)
    app.router.add_post("/api/life/controls", handle_life_controls)
    app.router.add_get("/api/settings", handle_settings_get)
    app.router.add_post("/api/settings", handle_settings_post)
    app.router.add_get("/api/computation_logs", handle_computation_logs)
    app.router.add_get("/api/memory_pools", handle_memory_pools)
    app.router.add_get("/api/meltdown_nonce", handle_meltdown_nonce)
    app.router.add_get("/api/memory_sink", handle_memory_sink)
    app.router.add_post("/api/memory_consolidate", handle_memory_consolidate)
    app.router.add_post("/api/memory_meltdown", handle_memory_meltdown)
    app.router.add_get("/api/config_presets", handle_config_presets)
    app.router.add_get("/api/glossary", handle_glossary)
    app.router.add_get("/api/export_data", handle_export_data)
    app.router.add_delete("/api/purge_data", handle_purge_data)
    app.router.add_get("/api/error_stats", handle_error_stats)
    app.router.add_get("/api/config_export", handle_config_export)
    app.router.add_post("/api/config_import", handle_config_import)
    app.router.add_get("/api/widget-state", handle_widget_state)
    app.router.add_post("/api/proactive_feedback", handle_proactive_feedback)
    app.router.add_get("/api/weekly_report", handle_weekly_report)
    app.router.add_get("/api/memory/decay_curve", handle_memory_decay_curve)
    app.router.add_get("/api/memory/recall_debug", handle_memory_recall_debug)
    app.router.add_get("/api/personality/export", handle_personality_export)
    app.router.add_post("/api/personality/import", handle_personality_import)
    app.router.add_get("/api/relationship_temperature", handle_relationship_temperature)
    app.router.add_get("/api/diagnostic_report", handle_diagnostic_report)
    app.router.add_get("/api/personality/drift-map", handle_personality_drift_map)
    app.router.add_get("/api/twin_synchrony_trajectory", handle_twin_synchrony)
    app.router.add_get("/api/v2core_state", handle_v2core_state)
    app.router.add_get("/api/quality-trend", handle_quality_trend)
    app.router.add_get("/api/theme", handle_theme_get)
    app.router.add_post("/api/theme", handle_theme_post)
    app.router.add_get("/api/rhythm_profile", handle_rhythm_profile)
    app.router.add_get("/api/scar_map", handle_scar_map)
    app.router.add_get("/api/sheaf_topology", handle_sheaf_topology)
    app.router.add_get("/api/topic-gravity", handle_topic_gravity)
    app.router.add_get("/api/admin/inspect", handle_admin_inspect)
    app.router.add_get("/api/admin/quarantine_view", handle_admin_quarantine_view)
    app.router.add_get("/api/admin/pending_deletes", handle_admin_pending_deletes)
    app.router.add_get("/assets/logo.png", handle_logo)
    app.router.add_get("/logo.png", handle_logo)

    # ------------------------------------------------------------------
    # Item 16: WebSocket 实时状态推送（/ws/state）
    # ------------------------------------------------------------------

    _ws_connections: set[web.WebSocketResponse] = set()
    _WS_MAX_CONNECTIONS = 10

    async def handle_ws_state(request: web.Request) -> web.WebSocketResponse:
        # S3: WebSocket 连接鉴权 — 仅在配置了 token 时校验
        if _active_token:
            ws_token = request.query.get("token", "")
            if not ws_token or ws_token != _active_token:
                ws = web.WebSocketResponse()
                await ws.prepare(request)
                await ws.close(code=4001, message=b"unauthorized")
                return ws
        if len(_ws_connections) >= _WS_MAX_CONNECTIONS:
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            await ws.close(code=1013, message=b"too many connections")
            return ws
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        _ws_connections.add(ws)
        try:
            while not ws.closed:
                state = _build_state(_plugin(plugin))
                await ws.send_json(state)
                await asyncio.sleep(2)
        except Exception:
            pass
        finally:
            _ws_connections.discard(ws)
            if not ws.closed:
                await ws.close()
        return ws

    app.router.add_get("/ws/state", handle_ws_state)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    try:
        await site.start()
        logger.info(f"Sylanne WebUI server started at http://{host}:{port}")
    except OSError as e:
        logger.warning(f"Sylanne WebUI server failed to start on port {port}: {e}")
        await runner.cleanup()
        return

    # Keep running until cancelled
    try:
        await asyncio.Event().wait()   # 永久挂起直到被 cancel（async 原生，零周期唤醒）
    except asyncio.CancelledError:
        await runner.cleanup()


def start_webui_background(plugin: Any, host: str = "127.0.0.1", port: int = 2718):
    """将 WebUI 服务器作为后台 asyncio task 启动。若无事件循环则回退到线程模式。"""
    global _server_task
    _set_active_plugin(plugin)
    if _server_task and not _server_task.done():
        return
    if _httpd_thread and _httpd_thread.is_alive():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("Sylanne WebUI: no running event loop, using stdlib HTTP server")
        start_webui_thread_server(plugin, host=host, port=port)
        return
    _server_task = loop.create_task(start_webui_server(plugin, host=host, port=port))


async def stop_webui_server() -> None:
    """停止独立监听器（插件卸载/重载时调用）。清理 task、httpd、thread。"""
    global _server_task, _httpd, _httpd_thread, _active_plugin, _main_loop
    # 清掉 persistent main loop 引用：卸载/重载后旧 loop 即将失效（或已由新一轮
    # __init__ 抢占式清理），避免 stdlib handler 用 run_coroutine_threadsafe 提交
    # 到一个已经不再服务的悬垂 loop 上。main.py 的 async initialize() 会在新一轮
    # 生命周期里重新调用 set_main_loop() 权威绑定。
    _main_loop = None
    task = _server_task
    _server_task = None
    if task and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    if _httpd is not None:
        try:
            _httpd.shutdown()
        except Exception:
            pass
        try:
            _httpd.server_close()
        except Exception:
            pass
    if _httpd_thread and _httpd_thread.is_alive():
        try:
            _httpd_thread.join(timeout=2.0)
        except Exception:
            pass
    _httpd = None
    _httpd_thread = None
    _active_plugin = None


def start_webui_thread_server(
    plugin: Any, host: str = "127.0.0.1", port: int = 2718
) -> None:
    """启动无依赖的 stdlib HTTP 服务器（aiohttp 不可用时的回退方案）。

    使用 ThreadingHTTPServer 在守护线程中运行，
    包含速率限制、请求体大小限制、Bearer token 鉴权。
    """
    global _httpd, _httpd_thread
    _set_active_plugin(plugin)
    if _httpd_thread and _httpd_thread.is_alive():
        return

    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from pathlib import Path

    plugin_root = Path(__file__).resolve().parent.parent
    dashboard_path = plugin_root / "UI" / "index.html"
    if dashboard_path.exists():
        dashboard_html = dashboard_path.read_text(encoding="utf-8")
    else:
        dashboard_html = (
            "<html><body><h1>Sylanne Dashboard unavailable</h1></body></html>"
        )

    class SylanneWebUIHandler(BaseHTTPRequestHandler):
        server_version = "SylanneWebUI/1.0"
        _MAX_BODY_SIZE = 1024 * 1024  # 1MB max request body
        _rate_limit_window: dict[str, list[float]] = {}
        _rate_limit_lock = threading.Lock()
        _RATE_LIMIT_MAX = 60  # max requests per window
        _RATE_LIMIT_WINDOW_SEC = 60.0

        def log_message(self, fmt: str, *args: Any) -> None:
            logger.debug("Sylanne WebUI: " + fmt, *args)

        def _check_rate_limit(self) -> bool:
            """Return True if request should be rejected (rate limited)."""
            client_ip = self.client_address[0]
            now = time.time()
            with self._rate_limit_lock:
                # S8: 防止 rate_limit_window 无限增长
                if len(self._rate_limit_window) > 1000:
                    cutoff_global = now - self._RATE_LIMIT_WINDOW_SEC
                    stale_keys = [
                        ip for ip, timestamps in self._rate_limit_window.items()
                        if not timestamps or timestamps[-1] < cutoff_global
                    ]
                    for ip in stale_keys:
                        del self._rate_limit_window[ip]
                window = self._rate_limit_window.setdefault(client_ip, [])
                cutoff = now - self._RATE_LIMIT_WINDOW_SEC
                self._rate_limit_window[client_ip] = [t for t in window if t > cutoff]
                if len(self._rate_limit_window[client_ip]) >= self._RATE_LIMIT_MAX:
                    return True
                self._rate_limit_window[client_ip].append(now)
            return False

        def _send_json(self, payload: Any, status: int = 200) -> None:
            data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", f"http://127.0.0.1:{port}")
            self.end_headers()
            self.wfile.write(data)

        def _send_text(
            self, text: str, content_type: str = "text/html; charset=utf-8"
        ) -> None:
            data = text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_logo(self) -> None:
            logo_path = plugin_root / "logo.png"
            if not logo_path.exists():
                self.send_error(404)
                return
            data = logo_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _query(self) -> dict[str, str]:
            parsed = urlparse(self.path)
            return {
                key: values[-1]
                for key, values in parse_qs(parsed.query).items()
                if values
            }

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self.send_header(
                "Access-Control-Allow-Origin",
                f"http://127.0.0.1:{port}",
            )
            self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
            self.send_header(
                "Access-Control-Allow-Headers", "Content-Type,Authorization,X-CSRF-Token"
            )
            self.end_headers()

        def do_GET(self) -> None:
            global _last_diag_request, _theme_preference
            if self._check_rate_limit():
                self._send_json({"error": "rate_limited"}, status=429)
                return
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            if path not in ("/", "/twin", "/favicon.ico", "/health", "/metrics", "/logo.png", "/assets/logo.png"):
                auth = self.headers.get("Authorization", "")
                if not _active_token or not auth.startswith("Bearer ") or auth[7:] != _active_token:
                    self._send_json({"error": "unauthorized"}, status=401)
                    return
            # S9: /metrics requires Bearer token when auth is configured
            if path == "/metrics" and _active_token:
                auth = self.headers.get("Authorization", "")
                if not auth.startswith("Bearer ") or auth[7:] != _active_token:
                    self._send_json({"error": "unauthorized"}, status=401)
                    return
            query = self._query()
            try:
                if path == "/":
                    self._send_text(dashboard_html)
                elif path == "/twin":
                    self._send_text(_TWIN_VIEWER_HTML)
                elif path == "/api/state":
                    # 自动关闭 diagnostics：超过 30s 无 computation_logs 请求
                    if _last_diag_request and time.time() - _last_diag_request > 30:
                        with _plugin_access_lock:
                            current = _plugin(plugin)
                            if current is not None:
                                _set_spine_diagnostics(current, False)
                    with _plugin_access_lock:
                        state = _build_state(
                            _plugin(plugin), session=query.get("session", "")
                        )
                    # Item 24: 在 state 响应中附带 csrf_token
                    state["csrf_token"] = _csrf_token
                    self._send_json(state)
                elif path == "/api/observation_history":
                    try:
                        with _plugin_access_lock:
                            payload = build_observation_history_payload(
                                _plugin(plugin),
                                query,
                            )
                    except ValueError as exc:
                        self._send_json({"error": str(exc)}, status=400)
                        return
                    except RuntimeError as exc:
                        self._send_json({"error": str(exc)}, status=503)
                        return
                    self._send_json(payload)
                elif path == "/api/settings":
                    with _plugin_access_lock:
                        current_plugin = _plugin(plugin)
                    self._send_json(asyncio.run(_settings_payload(current_plugin)))
                elif path == "/api/computation_logs":
                    _last_diag_request = time.time()
                    with _plugin_access_lock:
                        current = _plugin(plugin)
                        if current is not None:
                            _set_spine_diagnostics(current, True)
                    limit = max(1, min(200, int(query.get("limit", "50"))))
                    session = str(query.get("session", "") or "").strip()
                    with _plugin_access_lock:
                        logs = getattr(_plugin(plugin), "_computation_logs", None)
                        all_entries = list(logs) if logs is not None else []
                    session_entries = (
                        [
                            entry
                            for entry in all_entries
                            if str(entry.get("session", "")) == session
                        ]
                        if session
                        else all_entries
                    )
                    entries = session_entries[-limit:]
                    self._send_json(
                        {
                            "logs": entries,
                            "total": len(all_entries),
                            "total_for_session": len(session_entries),
                            "session": session,
                        }
                    )
                elif path == "/api/memory_pools":
                    limit = max(1, min(100, int(query.get("limit", "50"))))
                    session = query.get("session", "")
                    with _plugin_access_lock:
                        data = _build_memory_pools_sync(
                            _plugin(plugin), session=session, limit=limit
                        )
                    self._send_json(data)
                elif path == "/api/meltdown_nonce":
                    session = query.get("session", "")
                    nonce = secrets.token_urlsafe(16)
                    _meltdown_nonces[session] = nonce
                    self._send_json({"nonce": nonce})
                elif path == "/api/memory_sink":
                    session = query.get("session", "")
                    if not session:
                        self._send_json({"ok": False, "error": "missing session param"})
                    else:
                        with _plugin_access_lock:
                            current_plugin = _plugin(plugin)
                            mem_getter = getattr(current_plugin, "_memory_system_for_session", None)
                            mem_sys = mem_getter(session) if callable(mem_getter) else getattr(current_plugin, "_memory_system", None)
                        if mem_sys is None:
                            self._send_json({"ok": False, "error": "memory system unavailable"})
                        else:
                            candidates = mem_sys.consolidation_candidates()
                            if not candidates:
                                self._send_json({"ok": False, "error": "no_confirmed_items", "sunk": 0})
                            else:
                                item_ids = [item.id for item in candidates]
                                mem_sys.sink_to_l2(item_ids)
                                logger.info(f"Sylanne MEMORY SINK (stdlib): session={session}, sunk={len(item_ids)}")
                                self._send_json({"ok": True, "sunk": len(item_ids)})
                elif path == "/health":
                    uptime_s = int(time.time() - _start_time)
                    current = _plugin(plugin)
                    hosts_dict = getattr(current, "_hosts", {}) or {}
                    sessions_count = len(hosts_dict) if isinstance(hosts_dict, dict) else 0
                    memory_mb = _get_process_memory_mb()
                    self._send_json({
                        "status": "ok",
                        "uptime_s": uptime_s,
                        "sessions": sessions_count,
                        "memory_mb": memory_mb,
                    })
                elif path == "/metrics":
                    metrics_text = _build_metrics()
                    data = metrics_text.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                elif path == "/api/error_stats":
                    cutoff = int(time.time()) // 60 * 60 - 3600
                    with _error_counts_lock:
                        data = [
                            {"minute": ts, "errors": errs, "warnings": warns}
                            for ts, errs, warns in _error_counts
                            if ts >= cutoff
                        ]
                    self._send_json(data)
                elif path == "/api/config_export":
                    with _plugin_access_lock:
                        current_plugin = _plugin(plugin)
                        config = dict(getattr(current_plugin, "_config", {}) or {})
                    # S1: 过滤敏感键
                    config = {k: v for k, v in config.items() if not _is_sensitive_key(k)}
                    self._send_json(config)
                elif path == "/api/glossary":
                    from sylanne_alpha.webui_routes import GLOSSARY
                    self._send_json({"glossary": GLOSSARY})
                elif path == "/api/widget-state":
                    with _plugin_access_lock:
                        current = _plugin(plugin)
                        data = _build_widget_state(current)
                    self._send_json(data)
                elif path == "/api/weekly_report":
                    from sylanne_alpha.analytics import generate_weekly_report
                    with _plugin_access_lock:
                        current = _plugin(plugin)
                        report = generate_weekly_report(current)
                    self._send_json(report)
                elif path == "/api/memory/decay_curve":
                    import math as _math
                    memory_id = query.get("memory_id", "")
                    if not memory_id:
                        self._send_json({"ok": False, "error": "missing memory_id param"})
                    else:
                        target_memory = None
                        with _plugin_access_lock:
                            current_plugin = _plugin(plugin)
                            hosts_d = getattr(current_plugin, "_hosts", {}) or {}
                            mem_getter = getattr(current_plugin, "_memory_system_for_session", None)
                            for sk in list(hosts_d.keys()):
                                mem_sys = mem_getter(sk) if callable(mem_getter) else None
                                if mem_sys is None:
                                    continue
                                for pool in (getattr(mem_sys, "_l1", []) or [], getattr(mem_sys, "_l2", []) or []):
                                    for item in list(pool):
                                        item_id = getattr(item, "id", None) or (item.get("id") if isinstance(item, dict) else None)
                                        if str(item_id) == memory_id:
                                            target_memory = item
                                            break
                                    if target_memory:
                                        break
                                if target_memory:
                                    break
                        if target_memory is None:
                            self._send_json({"ok": False, "error": "memory_id not found"})
                        else:
                            created_at = float(getattr(target_memory, "created_at", 0) or (target_memory.get("created_at", 0) if isinstance(target_memory, dict) else 0))
                            rehearsal = int(getattr(target_memory, "recall_count", 0) or (target_memory.get("recall_count", 0) if isinstance(target_memory, dict) else 0))
                            emotional_weight = float(getattr(target_memory, "emotional_weight", 0.5) or (target_memory.get("emotional_weight", 0.5) if isinstance(target_memory, dict) else 0.5))
                            stability = 24 * (1 + rehearsal * 0.5) * (1 + emotional_weight)
                            curve = []
                            for hour in range(169):
                                retention = max(0.05, _math.exp(-hour / stability))
                                curve.append({"hour": hour, "retention": round(retention, 4)})
                            self._send_json({"memory_id": memory_id, "created_at": created_at, "stability": round(stability, 2), "rehearsal": rehearsal, "emotional_weight": round(emotional_weight, 3), "curve": curve})
                elif path == "/api/theme":
                    self._send_json({"theme": _theme_preference})
                elif path == "/api/twin_synchrony_trajectory":
                    with _plugin_access_lock:
                        current = _plugin(plugin)
                    session = query.get("session", "")
                    try:
                        limit = max(1, min(200, int(query.get("limit", "200") or "200")))
                    except (TypeError, ValueError):
                        limit = 200
                    self._send_json(_twin_synchrony_payload(current, session=session, limit=limit))
                elif path == "/api/v2core_state":
                    with _plugin_access_lock:
                        current = _plugin(plugin)
                    self._send_json(_v2core_state_payload(current, session=query.get("session", "")))
                elif path == "/api/rhythm_profile":
                    with _plugin_access_lock:
                        current = _plugin(plugin)
                        rhythm_learner = getattr(current, "_rhythm_learner", None)
                    if rhythm_learner is None:
                        self._send_json({"ok": False, "error": "rhythm_learner unavailable"})
                    else:
                        session = query.get("session", "")
                        if not session:
                            with _plugin_access_lock:
                                hosts_d = getattr(current, "_hosts", {}) or {}
                            if isinstance(hosts_d, dict) and hosts_d:
                                session = next(iter(hosts_d))
                            else:
                                session = "default"
                        profile = rhythm_learner.profile(session)
                        tempo = rhythm_learner.tempo
                        reply_length_factor = rhythm_learner.get_reply_length_factor(session)
                        last_msg_time = profile._last_msg_time if profile is not None else 0.0
                        breath_hold = rhythm_learner.detect_breath_hold(last_msg_time, time.time()) if last_msg_time > 0 else False
                        avg_message_length = profile.avg_part_chars if profile is not None else 0.0
                        self._send_json({
                            "ok": True,
                            "session": session,
                            "tempo": round(tempo, 3),
                            "avg_message_length": round(avg_message_length, 1),
                            "reply_length_factor": round(reply_length_factor, 3),
                            "breath_hold": breath_hold,
                            "confidence": round(profile.confidence, 3) if profile is not None else 0.0,
                            "chars_per_second": round(profile.chars_per_second, 2) if profile is not None else 0.0,
                        })
                elif path == "/api/scar_map":
                    session_key = query.get("session", "")
                    with _plugin_access_lock:
                        current = _plugin(plugin)
                        hosts_dict = getattr(current, "_hosts", {}) or {}
                        all_sessions = _known_sessions(current, requested=session_key)
                        if not session_key and all_sessions:
                            session_key = all_sessions[0]
                    nodes: list = []
                    edges: list = []
                    try:
                        host = hosts_dict.get(session_key) if isinstance(hosts_dict, dict) else None
                        if host is not None:
                            comp = host.kernel.computation
                            scar_state = getattr(comp.engine, "scar_state", None)
                            if scar_state is not None:
                                for idx, scar in enumerate(scar_state.scars):
                                    nodes.append({
                                        "id": f"scar_{idx}",
                                        "dimension": scar.dimension,
                                        "intensity": round(scar.alpha, 3),
                                        "temperature": round(1.0 - scar.ticks_in_stage / max(1, 150), 3),
                                        "state": scar.stage.name.lower(),
                                    })
                                from collections import defaultdict
                                dim_groups: dict = defaultdict(list)
                                for idx, scar in enumerate(scar_state.scars):
                                    dim_groups[scar.dimension].append(idx)
                                for dim, indices in dim_groups.items():
                                    for i in range(len(indices)):
                                        for j in range(i + 1, len(indices)):
                                            a_i = scar_state.scars[indices[i]].alpha
                                            a_j = scar_state.scars[indices[j]].alpha
                                            coupling = round((a_i * a_j) ** 0.5 / 2.0, 3)
                                            edges.append({
                                                "source": f"scar_{indices[i]}",
                                                "target": f"scar_{indices[j]}",
                                                "coupling": coupling,
                                            })
                    except Exception:
                        pass
                    self._send_json({"nodes": nodes, "edges": edges})
                elif path == "/api/sheaf_topology":
                    from sylanne_alpha._engine.sylanne_core.compute.relational_sheaf import _REL_TYPE_NAMES
                    session_key = query.get("session", "")
                    with _plugin_access_lock:
                        current = _plugin(plugin)
                        hosts_dict = getattr(current, "_hosts", {}) or {}
                        all_sessions = _known_sessions(current, requested=session_key)
                        if not session_key and all_sessions:
                            session_key = all_sessions[0]
                    nodes = []
                    edges = []
                    h1 = 0.0
                    try:
                        host = hosts_dict.get(session_key) if isinstance(hosts_dict, dict) else None
                        if host is not None:
                            sheaf = host.kernel.computation.sheaf
                            obs = sheaf.observe()
                            h1 = obs.get("h1_dim", 0)
                            complex_ = sheaf.complex
                            for v in complex_._vertices:
                                if v == 0:
                                    nodes.append({"id": "agent", "type": "self"})
                                else:
                                    edge_idx = complex_.edge_index(v)
                                    rel_type_int = sheaf._rel_types[edge_idx] if edge_idx < len(sheaf._rel_types) else 1
                                    type_name = _REL_TYPE_NAMES[rel_type_int] if rel_type_int < len(_REL_TYPE_NAMES) else "friendly"
                                    nodes.append({"id": f"partner_{v}", "type": type_name})
                            incon = obs.get("inconsistency_per_edge", [])
                            for ei, (_, partner) in enumerate(complex_._edges):
                                coupling = round(1.0 - (incon[ei] if ei < len(incon) else 0.0), 4)
                                edges.append({"source": "agent", "target": f"partner_{partner}", "coupling": coupling})
                    except Exception:
                        pass
                    self._send_json({"nodes": nodes, "edges": edges, "cohomology_h1": h1})
                elif path == "/api/topic-gravity":
                    import math as _math
                    session_key = query.get("session", "")
                    with _plugin_access_lock:
                        current = _plugin(plugin)
                        hosts_dict = getattr(current, "_hosts", {}) or {}
                        all_sessions = _known_sessions(current, requested=session_key)
                        if not session_key and all_sessions:
                            session_key = all_sessions[0]
                    topics: list = []
                    try:
                        host = hosts_dict.get(session_key) if isinstance(hosts_dict, dict) else None
                        if host is not None:
                            tg = getattr(host, "_topic_gravity", None) or getattr(host.kernel, "_topic_gravity", None)
                            if tg is None:
                                tg = getattr(current, "_topic_gravity", None)
                            if tg is not None:
                                now = time.time()
                                for name, node in tg._topics.items():
                                    age = now - node.last_active
                                    half_life = getattr(tg, "_half_life", 7200)
                                    decay = _math.exp(-age * _math.log(2) / half_life)
                                    topics.append({
                                        "name": node.name,
                                        "mass": round(node.mass * decay, 4),
                                        "decay_factor": round(decay, 4),
                                        "visits": node.visit_count,
                                    })
                                topics.sort(key=lambda x: x["mass"], reverse=True)
                    except Exception:
                        pass
                    self._send_json({"topics": topics})
                elif path in {"/assets/logo.png", "/logo.png"}:
                    self._send_logo()
                else:
                    self.send_error(404)
            except Exception as exc:
                logger.warning(f"Sylanne WebUI GET error: {exc}", exc_info=True)
                self._send_json({"ok": False, "error": "internal_error"}, status=500)

        def do_POST(self) -> None:
            global _theme_preference
            if self._check_rate_limit():
                self._send_json({"error": "rate_limited"}, status=429)
                return
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            if path not in ("/", "/favicon.ico", "/logo.png", "/assets/logo.png"):
                auth = self.headers.get("Authorization", "")
                if not _active_token or not auth.startswith("Bearer ") or auth[7:] != _active_token:
                    self._send_json({"error": "unauthorized"}, status=401)
                    return
            # Item 24: CSRF 防护 — POST 需要 X-CSRF-Token header
            csrf_header = self.headers.get("X-CSRF-Token", "")
            if csrf_header != _csrf_token:
                self._send_json({"error": "csrf_token_mismatch"}, status=403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length > self._MAX_BODY_SIZE:
                    self._send_json({"error": "payload_too_large"}, status=413)
                    return
                raw = self.rfile.read(length) if length > 0 else b"{}"
                body = json.loads(raw.decode("utf-8") or "{}")
                if not isinstance(body, dict):
                    body = {}
            except Exception:
                body = {}

            if path == "/api/settings":
                try:
                    with _plugin_access_lock:
                        current_plugin = _plugin(plugin)
                        schema = _load_schema(current_plugin)
                        config = getattr(current_plugin, "_config", {})
                        updated = []
                        for key, value in body.items():
                            if key not in schema:
                                continue
                            meta = schema[key]
                            field_type = meta.get("type", "string")
                            if field_type == "bool":
                                value = bool(value)
                            elif field_type == "int":
                                try:
                                    value = int(value)
                                except (ValueError, TypeError):
                                    continue
                            elif field_type == "float":
                                try:
                                    value = float(value)
                                except (ValueError, TypeError):
                                    continue
                            else:
                                value = str(value)
                            config[key] = value
                            updated.append(key)
                    # Persist config to disk if AstrBot config supports it
                    if updated:
                        p_cfg = getattr(current_plugin, "config", None)
                        if p_cfg is not None and hasattr(p_cfg, "save_config"):
                            try:
                                p_cfg.save_config()
                            except Exception:
                                pass
                    self._send_json({"ok": True, "updated": updated})
                except Exception as exc:
                    logger.error(f"Sylanne WebUI POST /api/settings error: {exc}", exc_info=True)
                    self._send_json({"ok": False, "error": "Internal server error"}, status=500)
            elif path == "/api/memory_consolidate":
                try:
                    session = str(body.get("session", "")).strip()
                    if not session:
                        self._send_json({"ok": False, "error": "missing session param"})
                        return
                    with _plugin_access_lock:
                        current_plugin = _plugin(plugin)
                        mem_getter = getattr(current_plugin, "_memory_system_for_session", None)
                        mem_sys = mem_getter(session) if callable(mem_getter) else getattr(current_plugin, "_memory_system", None)
                    if mem_sys is None or not list(mem_sys._l1):
                        self._send_json({"ok": True, "estimated_seconds": 0})
                        return
                    # DATA-LOSS 修复：get_event_loop() 在 worker 线程里会造出一个从未
                    # run 过的新 loop，call_soon_threadsafe 排的回调永远不执行——
                    # consolidation 悄悄没跑却仍回 {ok: True}。改提交到真正在跑的
                    # persistent main loop（set_main_loop 绑定）；拿不到就诚实报错。
                    main_loop = _get_main_loop()
                    if main_loop is None or not main_loop.is_running():
                        logger.warning(
                            "Sylanne WebUI memory_consolidate (stdlib): 无可用的 "
                            "persistent main loop，consolidation 未调度"
                        )
                        self._send_json(
                            {"ok": False, "error": "consolidation_unavailable_no_loop"},
                            status=503,
                        )
                        return
                    asyncio.run_coroutine_threadsafe(
                        current_plugin._trigger_consolidation(session),
                        main_loop,
                    )
                    self._send_json({"ok": True, "estimated_seconds": 30})
                except Exception as exc:
                    logger.error(f"Sylanne WebUI POST /api/memory_consolidate error: {exc}", exc_info=True)
                    self._send_json({"ok": False, "error": "Internal server error"}, status=500)
            elif path == "/api/memory_meltdown":
                try:
                    session = str(body.get("session", "")).strip()
                    nonce = str(body.get("nonce", "")).strip()
                    expected = _meltdown_nonces.pop(session, None)
                    if not nonce or nonce != expected:
                        self._send_json(
                            {"ok": False, "error": "invalid_nonce"}, status=403
                        )
                        return
                    with _plugin_access_lock:
                        current_plugin = _plugin(plugin)
                        mem_getter = getattr(
                            current_plugin, "_memory_system_for_session", None
                        )
                        if callable(mem_getter):
                            mem_sys = mem_getter(session)
                            if mem_sys:
                                mem_sys._l1.clear()
                                mem_sys._l2.clear()
                                mem_sys._l3_nodes.clear()
                                mem_sys._l3_edges.clear()
                                mem_sys._tick = 0
                                # FIX(F2，完整性复审)：置 _hydrated=True 阻断补水复活
                                # （详见 webui_routes meltdown 同名注释）。
                                mem_sys._hydrated = True
                        hosts = getattr(current_plugin, "_hosts", {}) or {}
                        if session in hosts:
                            hosts[session].kernel.body.memory["traces"] = []
                            hosts[session].kernel.body.memory.pop(
                                "_memory_system", None
                            )
                        sp = getattr(current_plugin, "_state_persistence", None)
                    # DATA-LOSS 修复：原先用 get_event_loop()+call_soon_threadsafe+
                    # ensure_future 在 worker 线程里排持久化 purge——该线程没有自己的
                    # running loop，get_event_loop() 只会造一个从未 run 过的新 loop，
                    # 回调永远不会执行。disk 上的会话状态就此存活，重启后可"复活"，
                    # 但接口仍照常回 {ok: True, cleared: True} 造成假成功。
                    # 现在改提交到 AstrBot 进程级 persistent main loop（由 main.py 的
                    # async initialize() 用 set_main_loop() 绑定），并 block 等结果，
                    # 确保响应体如实反映持久化 purge 是否真的执行完成。
                    persistent_purge_ok = True
                    warning: str | None = None
                    if sp is not None and hasattr(sp, "purge_session_after_meltdown"):
                        main_loop = _get_main_loop()
                        if main_loop is not None and main_loop.is_running():
                            try:
                                fut = asyncio.run_coroutine_threadsafe(
                                    sp.purge_session_after_meltdown(session), main_loop
                                )
                                fut.result(timeout=10)
                            except Exception as purge_exc:
                                persistent_purge_ok = False
                                warning = (
                                    "in-memory cleared; persistent purge failed/"
                                    "timed out"
                                )
                                logger.error(
                                    "Sylanne MEMORY MELTDOWN (stdlib): persistent "
                                    f"purge failed for session={session}: {purge_exc}",
                                    exc_info=True,
                                )
                        else:
                            persistent_purge_ok = False
                            warning = (
                                "in-memory cleared; persistent purge unavailable "
                                "(no running loop)"
                            )
                            logger.warning(
                                "Sylanne MEMORY MELTDOWN (stdlib): no running "
                                f"persistent main loop, session={session} disk "
                                "state NOT purged"
                            )
                    logger.info(f"Sylanne MEMORY MELTDOWN (stdlib): session={session}")
                    if persistent_purge_ok:
                        self._send_json(
                            {"ok": True, "session": session, "cleared": True}
                        )
                    else:
                        # NEVER 裸 cleared:true——诚实告知内存已清但磁盘 purge 未执行。
                        self._send_json(
                            {
                                "ok": True,
                                "session": session,
                                "cleared": True,
                                "persistent_purge": False,
                                "warning": warning,
                            }
                        )
                except Exception as exc:
                    logger.error(f"Sylanne WebUI POST /api/memory_meltdown error: {exc}", exc_info=True)
                    self._send_json({"ok": False, "error": "Internal server error"}, status=500)
            elif path == "/api/config_import":
                try:
                    if not isinstance(body, dict) or not body:
                        self._send_json({"ok": False, "error": "expected_object"}, status=400)
                        return
                    # S2: 拒绝写入敏感键
                    sensitive_found = [k for k in body if _is_sensitive_key(k)]
                    if sensitive_found:
                        self._send_json({"ok": False, "error": "cannot_import_sensitive_keys", "keys": sensitive_found}, status=403)
                        return
                    with _plugin_access_lock:
                        current_plugin = _plugin(plugin)
                        config = getattr(current_plugin, "_config", None)
                        if config is None:
                            self._send_json({"ok": False, "error": "no_config"}, status=500)
                            return
                        config.update(body)
                        persistent = getattr(current_plugin, "config", config)
                        if isinstance(persistent, dict):
                            persistent.update(body)
                        if hasattr(persistent, "save_config"):
                            persistent.save_config()
                    self._send_json({"ok": True, "keys": list(body.keys())})
                except Exception as exc:
                    logger.error(f"Sylanne WebUI POST /api/config_import error: {exc}", exc_info=True)
                    self._send_json({"ok": False, "error": "Internal server error"}, status=500)
            elif path == "/api/proactive_feedback":
                try:
                    session_key = str(body.get("session_key", "")).strip()
                    timestamp = float(body.get("timestamp", 0))
                    rating = str(body.get("rating", "")).strip()
                    if not session_key or not rating or rating not in ("positive", "negative"):
                        self._send_json({"ok": False, "error": "invalid_params"}, status=400)
                        return
                    with _plugin_access_lock:
                        current = _plugin(plugin)
                        scheduler = getattr(current, "_proactive_scheduler", None)
                        if scheduler is not None and hasattr(scheduler, "record_feedback"):
                            scheduler.record_feedback(session_key, timestamp, rating)
                    self._send_json({"ok": True})
                except Exception as exc:
                    logger.error(f"Sylanne WebUI POST /api/proactive_feedback error: {exc}", exc_info=True)
                    self._send_json({"ok": False, "error": "Internal server error"}, status=500)
            elif path == "/api/theme":
                theme = str(body.get("theme", "")).strip()
                if theme not in ("dark", "light", "auto"):
                    self._send_json({"ok": False, "error": "invalid theme, must be dark|light|auto"}, status=400)
                    return
                _theme_preference = theme
                self._send_json({"ok": True, "theme": _theme_preference})
            else:
                self.send_error(404)

    try:
        _httpd = ThreadingHTTPServer((host, port), SylanneWebUIHandler)
    except OSError as e:
        logger.warning(f"Sylanne WebUI stdlib server failed to bind {host}:{port}: {e}")
        _httpd = None
        return
    _httpd_thread = threading.Thread(
        target=_httpd.serve_forever, name="SylanneWebUI", daemon=True
    )
    _httpd_thread.start()
    logger.info(f"Sylanne WebUI stdlib server started at http://{host}:{port}")


async def _provider_items(plugin: Any) -> list[dict[str, Any]]:
    """尽力获取 AstrBot 已注册的 provider 列表，供设置面板下拉选择。"""
    context = getattr(plugin, "context", None)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(provider: Any, provider_type: str = "") -> None:
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

    # Dedicated registries must win deduplication.  AstrBot's generic registry
    # may include embedding providers; visiting it first would mislabel them as
    # text models and make the compact embedding selector appear empty.
    for method_name, provider_type in (
        ("get_all_embedding_providers", "embedding"),
        ("get_all_llm_providers", "llm"),
        ("get_all_providers", "llm"),
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
            add(provider, provider_type)
    return items


async def _settings_payload(plugin: Any) -> dict[str, Any]:
    """Build the identical settings response for aiohttp and stdlib modes."""

    schema = _load_schema(plugin)
    config = dict(getattr(plugin, "_config", {}) or {})
    values: dict[str, Any] = {}
    for key, meta in schema.items():
        raw = config.get(key, meta.get("default"))
        values[key] = "********" if _is_sensitive_key(key) and raw else raw
    providers = await _provider_items(plugin)
    return {
        "schema": schema,
        "values": values,
        "providers": providers,
        "model_routing": build_model_routing_payload(config, schema, providers),
    }


def _known_sessions(plugin: Any, *, requested: str = "") -> list[str]:
    """收集所有已知会话标识符。

    来源：活跃 hosts、内存缓存、运行时快照、磁盘文件。
    """
    sessions: list[str] = []

    def add(value: Any) -> None:
        text = str(value or "").strip()
        if text and text not in sessions:
            sessions.append(text)

    add(requested)
    hosts = getattr(plugin, "_hosts", {}) or {}
    if isinstance(hosts, dict):
        for key in hosts.keys():
            add(key)
    mem_systems = getattr(plugin, "_memory_systems", {}) or {}
    if isinstance(mem_systems, dict):
        for key in mem_systems.keys():
            add(key)
    cache = getattr(plugin, "_sylanne_memory_cache", {}) or {}
    if isinstance(cache, dict):
        for key in cache.keys():
            add(key)
    for host in list(hosts.values()) if isinstance(hosts, dict) else []:
        runtime = getattr(host, "runtime", None)
        export_all = getattr(runtime, "export_all", None)
        if not callable(export_all):
            continue
        try:
            exported = export_all()
        except Exception:
            continue
        persisted = exported.get("sessions", {}) if isinstance(exported, dict) else {}
        if isinstance(persisted, dict):
            for key in persisted.keys():
                add(key)
    try:
        from pathlib import Path

        config = getattr(plugin, "_config", {}) or getattr(plugin, "config", {}) or {}
        root = Path(resolve_data_root(config))
        if root.exists():
            for path in root.glob("*.alpha.json"):
                add(path.name[: -len(".alpha.json")])
    except Exception:
        pass
    if not sessions:
        add("default")
    return sessions


# 二重奏同步度 —— 自包含 live 查看页（Phase G）。独立 /twin 路由，零依赖、不碰庞大的 SPA，
# 客户端拉 /api/twin_synchrony_trajectory 自渲染内联 SVG（与 tools/twin_synchrony_viz.py 同构）。
_TWIN_VIEWER_HTML = """<!doctype html><html lang=zh><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>二重奏同步度 · Sylanne</title>
<style>
body{background:#0b1120;color:#e2e8f0;font-family:system-ui,sans-serif;margin:0;padding:24px}
h1{font-size:18px;font-weight:600;margin:0 0 4px}
.sub{color:#64748b;font-size:12px;margin-bottom:14px}
.card{background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:16px;margin:12px 0;max-width:780px}
.verdict{font-size:14px;color:#38bdf8;margin:10px 0}
select,button{background:#1e293b;color:#e2e8f0;border:1px solid #334155;border-radius:6px;padding:6px 10px;font-size:13px}
table{border-collapse:collapse;font-size:13px}td{padding:3px 16px 3px 0;color:#94a3b8}
.empty{color:#64748b;text-align:center;padding:40px}
</style></head><body>
<h1>二重奏 · 跨会话同步度轨迹</h1>
<div class=sub>她越来越懂你的那条收敛曲线：grip↑（越懂你）+ user_pe↓（猜得越准）+ sync（广义同步度，Friston&Frith 2015）</div>
<div class=card>
  <span class=sub>会话</span>
  <select id=sess onchange=load()></select>
  <button onclick=load()>刷新</button>
</div>
<div class=verdict id=verdict>—</div>
<div class=card id=chart><div class=empty>加载中…</div></div>
<div class=card><table id=summary></table></div>
<script>
var W=720,H=360,PL=52,PR=16,PT=28,PB=36;
var SERIES=[["grip","#3b82f6","把握度 grip ↑"],["sync","#10b981","同步度 sync"],["user_pe","#f59e0b","预测误差 user_pe ↓"]];
function tok(){return localStorage.getItem('sylanne_token')||''}
function poly(points,key){
  var n=points.length; if(!n) return '';
  var pw=W-PL-PR, ph=H-PT-PB, out=[];
  for(var i=0;i<n;i++){var v=+points[i][key]||0; v=v<0?0:(v>1?1:v);
    var x=PL+(n>1?pw*(i/(n-1)):pw/2), y=PT+ph*(1-v); out.push(x.toFixed(1)+','+y.toFixed(1));}
  return out.join(' ');
}
function svg(points){
  var pw=W-PL-PR, ph=H-PT-PB, p=['<svg viewBox="0 0 '+W+' '+H+'" xmlns="http://www.w3.org/2000/svg" font-family="system-ui" font-size="11">'];
  p.push('<rect width="'+W+'" height="'+H+'" fill="#0f172a" rx="8"/>');
  [0,0.5,1].forEach(function(g){var gy=PT+ph*(1-g);
    p.push('<line x1="'+PL+'" y1="'+gy+'" x2="'+(W-PR)+'" y2="'+gy+'" stroke="#1e293b"/>');
    p.push('<text x="'+(PL-8)+'" y="'+(gy+3)+'" fill="#64748b" text-anchor="end">'+g.toFixed(1)+'</text>');});
  if(!points.length){p.push('<text x="'+(W/2)+'" y="'+(H/2)+'" fill="#64748b" text-anchor="middle">暂无数据（v2core 未启用 / 该会话未对话）</text>');p.push('</svg>');return p.join('');}
  SERIES.forEach(function(s){var pts=poly(points,s[0]); if(pts) p.push('<polyline points="'+pts+'" fill="none" stroke="'+s[1]+'" stroke-width="2" stroke-linejoin="round"/>');});
  var lx=PL; SERIES.forEach(function(s){p.push('<rect x="'+lx+'" y="6" width="10" height="10" fill="'+s[1]+'" rx="2"/>');p.push('<text x="'+(lx+14)+'" y="15" fill="#cbd5e1">'+s[2]+'</text>');lx+=11*s[2].length+30;});
  p.push('</svg>'); return p.join('');
}
async function fetchJSON(path){
  var h={}; var t=tok(); if(t) h['Authorization']='Bearer '+t;
  var r=await fetch(path,{headers:h}); if(!r.ok) throw new Error('HTTP '+r.status); return r.json();
}
async function load(){
  var sess=document.getElementById('sess').value||'';
  var d; try{ d=await fetchJSON('/api/twin_synchrony_trajectory'+(sess?('?session='+encodeURIComponent(sess)):'')); }
  catch(e){ document.getElementById('chart').innerHTML='<div class=empty>加载失败：'+e.message+'</div>'; return; }
  var pts=d.points||[]; document.getElementById('chart').innerHTML=svg(pts);
  var sm=d.summary||{}, v='—';
  if(sm.grip_gain>0&&sm.user_pe_drop>0) v='✓ 二重奏收敛中：她越来越懂你（grip↑ + user_pe↓）';
  else if(sm.grip_gain>0||sm.user_pe_drop>0) v='～ 部分收敛（单指标改善）';
  else if(pts.length) v='· 尚未显现收敛（样本不足或关系波动期）';
  document.getElementById('verdict').textContent=v;
  document.getElementById('summary').innerHTML=Object.keys(sm).length?Object.keys(sm).map(function(k){return '<tr><td>'+k+'</td><td>'+sm[k]+'</td></tr>';}).join(''):'<tr><td>无数据</td></tr>';
  var sel=document.getElementById('sess'); if(!sel.dataset.filled&&d.sessions&&d.sessions.length){
    sel.innerHTML=d.sessions.map(function(s){return '<option'+(s===d.session?' selected':'')+'>'+s+'</option>';}).join(''); sel.dataset.filled='1';}
}
load();
</script></body></html>"""


def _twin_synchrony_payload(plugin: Any, *, session: str = "", limit: int = 200) -> dict[str, Any]:
    """二重奏同步度轨迹（Phase G 可视化）：读 v2core UserModelDomain.synchrony_trajectory()。

    数据源是 plugin._v2core_runtimes[session]["domains"]["usermodel"]（v2core 开关开启后
    每会话累积的真 agent 状态）。开关关 / 该会话没跑过 v2core → 空轨迹（enabled=False），
    前端据此显示"未启用/无数据"，绝不报错。纯只读，不碰任何 SDK / kernel。

    返回 {enabled, session, sessions, points:[{turn,sync,grip,user_pe}], summary}。
    summary 给"她越来越懂你"的收敛结论：grip 升幅 + user_pe 降幅 + 样本数。
    """
    runtimes = getattr(plugin, "_v2core_runtimes", None)
    sessions = sorted(runtimes.keys()) if isinstance(runtimes, dict) else []
    out: dict[str, Any] = {
        "enabled": bool(sessions), "session": session,
        "sessions": sessions, "points": [], "summary": {},
    }
    if not isinstance(runtimes, dict) or not runtimes:
        return out
    sk = session.strip() if session and session.strip() in runtimes else (sessions[0] if sessions else "")
    out["session"] = sk
    rt = runtimes.get(sk) if sk else None
    doms = rt.get("domains") if isinstance(rt, dict) else None
    um = doms.get("usermodel") if isinstance(doms, dict) else None
    traj_fn = getattr(um, "synchrony_trajectory", None)
    if not callable(traj_fn):
        return out
    try:
        points = traj_fn()
    except Exception:
        return out
    if limit and len(points) > limit:
        points = points[-limit:]
    out["points"] = points
    if points:
        first, last = points[0], points[-1]
        out["summary"] = {
            "samples": len(points),
            "grip_gain": round(float(last.get("grip", 0.0)) - float(first.get("grip", 0.0)), 4),
            "user_pe_drop": round(float(first.get("user_pe", 0.0)) - float(last.get("user_pe", 0.0)), 4),
            "sync_latest": round(float(last.get("sync", 0.5)), 4),
            "grip_latest": round(float(last.get("grip", 0.5)), 4),
        }
    return out


def _v2core_state_payload(plugin: Any, *, session: str = "") -> dict[str, Any]:
    """v2core 认知核状态投影（WebUI 认知核页 /api/v2core_state）。

    与 _twin_synchrony_payload 同款纪律：纯只读——域走各自公开只读接口
    （view/self_prior/synchrony/to_dict/prompt_line），躯体走 body_port.observe()
    （唯一边界，零 tick 零写）；开关关 / 会话没跑过 → enabled=False 空数据，
    前端显示"未启用"，绝不报错、绝不拿假数据冒充。

    返回 {enabled, session, sessions, fragment, decision, body, domains}。
    fragment = 最近一轮注入 LLM 的心象片段原文（她看到什么，你也看到什么）；
    decision = 最近一轮 ignition 裁决留痕（说/不说的代价比较现场）。
    """
    runtimes = getattr(plugin, "_v2core_runtimes", None)
    sessions = sorted(runtimes.keys()) if isinstance(runtimes, dict) else []
    out: dict[str, Any] = {
        "enabled": bool(sessions), "session": session, "sessions": sessions,
        "fragment": "", "decision": {}, "body": {}, "domains": {},
    }
    if not isinstance(runtimes, dict) or not runtimes:
        return out
    sk = session.strip() if session and session.strip() in runtimes else (sessions[0] if sessions else "")
    out["session"] = sk
    rt = runtimes.get(sk)
    if not isinstance(rt, dict):
        return out

    out["fragment"] = str(rt.get("last_fragment", "") or "")
    dec = rt.get("last_decision")
    out["decision"] = dict(dec) if isinstance(dec, dict) else {}

    # —— 躯体切面（四域的共同输入；observe 只读不 tick）——
    body = None
    try:
        bp = rt.get("body_port")
        if bp is not None and hasattr(bp, "observe"):
            body = bp.observe()
            out["body"] = {
                "warmth": round(float(body.warmth), 4),
                "tension": round(float(body.tension), 4),
                "repair_pressure": round(float(body.repair_pressure), 4),
                "scar": round(float(body.scar), 4),
                "sovereignty": round(float(body.sovereignty), 4),
                "exhaustion": round(float(body.exhaustion), 4),
                "expression_drive": round(float(body.expression_drive), 4),
                "surprise": round(float(body.surprise), 4),
                "precision": round(float(body.precision), 4),
                "turns": int(body.turns),
            }
    except Exception:
        body = None

    doms = rt.get("domains") if isinstance(rt.get("domains"), dict) else {}

    # —— 各域独立容错：任何一域失败只丢那一块，绝不拖垮整个 payload ——
    emo = doms.get("emotion")
    if emo is not None:
        try:
            block: dict[str, Any] = {}
            if body is not None and hasattr(emo, "view"):
                v = emo.view(body)
                block.update({
                    "warmth": round(float(v.warmth), 4),
                    "valence": round(float(v.valence), 4),
                    "arousal": round(float(v.arousal), 4),
                    "tension": round(float(v.tension), 4),
                    "volatility": round(float(v.volatility), 4),
                    "trend": round(float(v.trend), 4),
                })
            d = emo.to_dict() if hasattr(emo, "to_dict") else {}
            block["unexpressed"] = round(float(d.get("unexpressed", 0.0) or 0.0), 4)
            if body is not None and hasattr(emo, "prompt_line"):
                block["line"] = str(emo.prompt_line(body) or "")
            out["domains"]["emotion"] = block
        except Exception:
            pass

    um = doms.get("usermodel")
    if um is not None:
        try:
            d = um.to_dict() if hasattr(um, "to_dict") else {}
            disp = d.get("disposition") if isinstance(d.get("disposition"), dict) else {}
            prec = d.get("disp_precision") if isinstance(d.get("disp_precision"), dict) else {}
            block = {
                "synchrony": round(float(um.synchrony()), 4) if hasattr(um, "synchrony") else 0.5,
                "grip": round(sum(prec.values()) / len(prec), 4) if prec else 0.5,
                "rhythm_ema": (round(float(d["rhythm_ema"]), 1)
                               if d.get("rhythm_ema") is not None else None),
                "disposition": {k: round(float(v), 4) for k, v in disp.items()},
                "line": str(um.prompt_line() or "") if hasattr(um, "prompt_line") else "",
            }
            out["domains"]["usermodel"] = block
        except Exception:
            pass

    nar = doms.get("narrative")
    if nar is not None:
        try:
            d = nar.to_dict() if hasattr(nar, "to_dict") else {}
            oss = d.get("ossification") if isinstance(d.get("ossification"), dict) else {}
            rigidity = round(sum(oss.values()) / len(oss), 4) if oss else 0.0
            block = {
                "epoch": int(d.get("epoch", 0) or 0),
                "rigidity": rigidity,
                "ossification": {k: round(float(v), 4) for k, v in oss.items()},
                "anchor_count": len(d.get("anchors") or []),
                "anchor_total": int(d.get("anchor_total", 0) or 0),
                "line": str(nar.prompt_line() or "") if hasattr(nar, "prompt_line") else "",
            }
            out["domains"]["narrative"] = block
        except Exception:
            pass

    dis = doms.get("distill")
    if dis is not None:
        try:
            d = dis.to_dict() if hasattr(dis, "to_dict") else {}
            err = d.get("err_ema") if isinstance(d.get("err_ema"), dict) else {}
            block = {
                "fidelity": round(float(dis.fidelity()), 4) if hasattr(dis, "fidelity") else 0.0,
                "samples": int(d.get("samples", 0) or 0),
                "mean_error": (round(sum(err.values()) / len(err), 4) if err else 1.0),
            }
            out["domains"]["distill"] = block
        except Exception:
            pass

    return out


# ---------------------------------------------------------------------------
# MEM-03 PR-7：三只读 admin 端点（诚实只读——只暴露已存在的字段，绝不新增持久
# 状态）。两个消费面（独立 aiohttp 服务器 + 嵌入式 AstrBot Web 服务器）共用
# 本节的模块级 builder，镜像 `_build_widget_state` / `_v2core_state_payload`
# 的既有共享模式。
# ---------------------------------------------------------------------------


def _admin_inspect_fence_stats(plugin: Any, session: str = "") -> dict[str, Any]:
    """化身栅栏 + 写咽喉部分（同步、纯内存读取，无 await）：`_hydrated` /
    `_incarnation_epoch`（只从活体内存对象上 getattr，绝不经 to_dict/序列化）
    vs 当前纪元、队深、拒写等计数、未决删除。抽成独立同步辅助供
    `_admin_inspect_payload` 复用，不直接对外注册为 handler。
    """
    out: dict[str, Any] = {
        "hydrated": None,
        "incarnation_epoch": None,
        "current_epoch": None,
        "epoch_matches": None,
        "queue_depth": None,
        "throat_stats": None,
        "has_pending_delete": None,
    }
    sp = getattr(plugin, "_state_persistence", None)
    if sp is None or not session:
        return out
    try:
        store = getattr(plugin, "_store", None)
        systems = getattr(store, "memory_systems", None) if store is not None else None
        live = systems.get(session) if systems is not None else None
        throat = getattr(sp, "_throat", None)
        current_epoch = throat.current_epoch(session) if throat is not None else None
        stamp = getattr(live, "_incarnation_epoch", None) if live is not None else None
        out["hydrated"] = getattr(live, "_hydrated", None) if live is not None else None
        out["incarnation_epoch"] = stamp
        out["current_epoch"] = current_epoch
        out["epoch_matches"] = (
            (stamp == current_epoch) if stamp is not None and current_epoch is not None else None
        )
    except Exception:
        pass
    try:
        throat = getattr(sp, "_throat", None)
        if throat is not None:
            out["queue_depth"] = throat.queue_depth(session)
            out["throat_stats"] = throat.stats()
            out["has_pending_delete"] = throat.has_pending_delete(session)
    except Exception:
        pass
    return out


async def _admin_inspect_payload(plugin: Any, session: str = "") -> dict[str, Any]:
    """单 session 诊断：键存在性/字节数/version/backup CRC/_hydrated/
    _incarnation_epoch vs 当前纪元/写咽喉队深/拒写计数。

    Best-effort：任何一块读取失败只把该块置 null，绝不因单点异常炸掉整个响应。
    `_incarnation_epoch` 只从【活体内存对象】上读（getattr），从不经过任何
    to_dict/序列化路径——冻结面：该属性绝不允许出现在任何持久化 blob 里，本
    builder 也只读不写，绝不把它塞回任何 dict 之外的地方。两个 HTTP 消费面
    （独立 aiohttp / 嵌入式 quart）都在 async 上下文中，故本 builder 是唯一
    真实实现（不提供假的同步壳，避免"看起来能同步跑，其实读不到 KV"的假象）。
    """
    out: dict[str, Any] = {"session": session, "kv_keys": None}
    out.update(_admin_inspect_fence_stats(plugin, session))
    if not session:
        return out

    sp = getattr(plugin, "_state_persistence", None)
    if sp is None:
        return out

    import json as _json

    get_fn = getattr(plugin, "get_kv_data", None)
    kv_keys: dict[str, Any] = {}
    if callable(get_fn):
        primary_key = sp.sylanne_memory_kv_key(session)
        backup_key = sp.sylanne_memory_backup_v2_kv_key(session)
        try:
            from .memory_legacy_formats import quarantine_kv_key

            quarantine_key = quarantine_kv_key(sp._safe_session_key(session))
        except Exception:
            quarantine_key = None

        async def _probe(key: str | None) -> dict[str, Any] | None:
            if key is None:
                return None
            try:
                blob = await get_fn(key, None)
            except Exception:
                return {"exists": None, "error": True}
            if blob is None:
                return {"exists": False}
            try:
                size = len(_json.dumps(blob, ensure_ascii=False).encode("utf-8"))
            except Exception:
                size = None
            entry: dict[str, Any] = {"exists": True, "bytes": size}
            if isinstance(blob, dict) and "version" in blob:
                entry["version"] = blob.get("version")
            return entry

        kv_keys["primary"] = await _probe(primary_key)
        backup_entry = await _probe(backup_key)
        if backup_entry is not None and backup_entry.get("exists"):
            try:
                backup_blob = await get_fn(backup_key, None)
                backup_entry["crc_valid"] = (
                    sp._backup_blob_is_valid(backup_blob)
                    if hasattr(sp, "_backup_blob_is_valid")
                    else None
                )
            except Exception:
                backup_entry["crc_valid"] = None
        kv_keys["v2_backup"] = backup_entry
        kv_keys["quarantine"] = await _probe(quarantine_key)
    out["kv_keys"] = kv_keys or None
    return out


async def _admin_quarantine_view_payload(plugin: Any, session: str = "") -> dict[str, Any]:
    """MEM-01 quarantine 侧车（此前只写不读的缺口）：可选按 session 过滤，
    否则聚合遍历所有已知 session 的 quarantine 键（best-effort，KV 无枚举 API，
    只能基于 `_known_sessions` 已知集合探测）。逐 session 读 quarantine 侧车键
    （未知 session 的残留侧车键无法被发现，诚实标注在 `note` 字段）。
    """
    sp = getattr(plugin, "_state_persistence", None)
    get_fn = getattr(plugin, "get_kv_data", None)
    out: dict[str, Any] = {
        "session": session,
        "sessions": {},
        "total_entries": 0,
        "note": (
            "AstrBot KV 无键枚举 API，仅覆盖 _known_sessions 已知的会话集合；"
            "未活跃过的会话残留 quarantine 侧车键不可见（诚实遗留，见设计文档 §9）"
        ),
    }
    if sp is None or not callable(get_fn):
        return out
    try:
        from .memory_legacy_formats import quarantine_kv_key
    except Exception:
        return out

    candidates = [session] if session else _known_sessions(plugin)
    sessions_out: dict[str, Any] = {}
    total = 0
    for sk in candidates:
        if not sk:
            continue
        try:
            safe = sp._safe_session_key(sk)
            key = quarantine_kv_key(safe)
            blob = await get_fn(key, None)
        except Exception:
            sessions_out[sk] = {"error": True}
            continue
        if not isinstance(blob, dict):
            continue
        items = blob.get("items") if isinstance(blob.get("items"), list) else []
        if not items:
            continue
        count = int(blob.get("count", len(items)) or len(items))
        sessions_out[sk] = {"count": count, "items": items}
        total += count
    out["sessions"] = sessions_out
    out["total_entries"] = total
    return out


def _admin_pending_deletes_payload(plugin: Any) -> dict[str, Any]:
    """跨重启 pending-delete 索引：进程内镜像（`_pending_delete_mirror`）快照，
    含扫描完成标志——纯只读，绝不修改镜像/绝不触发 clear。
    """
    sp = getattr(plugin, "_state_persistence", None)
    out: dict[str, Any] = {
        "scan_done": None,
        "entries": {},
        "count": 0,
    }
    if sp is None:
        return out
    try:
        mirror = getattr(sp, "_pending_delete_mirror", None)
        out["scan_done"] = getattr(sp, "_pending_delete_scan_done", None)
        if isinstance(mirror, dict):
            out["entries"] = dict(mirror)
            out["count"] = len(mirror)
    except Exception:
        pass
    return out


def _last_bot_text(plugin: Any, session_key: str) -> str:
    """获取指定会话的最后一条 bot 回复文本（截断到 120 字符）。"""
    buffers = getattr(plugin, "_conversation_buffers", {})
    buf = buffers.get(session_key)
    if buf is not None:
        for msg in reversed(buf.messages):
            if msg.get("role") == "bot":
                return str(msg.get("text", ""))[:120]
    last_texts = getattr(plugin, "_last_bot_texts", {})
    if session_key in last_texts:
        return str(last_texts[session_key])[:120]
    return ""


def _last_user_text(plugin: Any, session_key: str) -> str:
    """获取指定会话的最后一条用户输入文本（截断到 120 字符）。"""
    buffers = getattr(plugin, "_conversation_buffers", {})
    buf = buffers.get(session_key)
    if buf is not None:
        for msg in reversed(buf.messages):
            if msg.get("role") == "user":
                return str(msg.get("text", ""))[:120]
    last_texts = getattr(plugin, "_last_user_texts", {})
    if session_key in last_texts:
        return str(last_texts[session_key])[:120]
    return ""


def _assessment_overlay(assessment: dict | None) -> dict[str, float]:
    """将 LLM assessor 的评估结果转换为情感兼容的覆盖值。

    在两次计算 tick 之间保持情感条活跃，120 秒后过期避免陈旧数据主导。
    """
    if not assessment:
        return {}
    assessed_at = float(assessment.get("assessed_at", 0) or 0)
    if assessed_at and (time.time() - assessed_at > 120):
        return {}
    overlay: dict[str, float] = {}
    v = float(assessment.get("valence", 0.0))
    a = float(assessment.get("arousal", 0.0))
    if v != 0.0:
        overlay["valence"] = max(-1.0, min(1.0, v))
        if v > 0:
            overlay["warmth"] = max(overlay.get("warmth", 0.0), v * 0.6)
        else:
            overlay["tension"] = max(overlay.get("tension", 0.0), abs(v) * 0.5)
    if a != 0.0:
        overlay["arousal"] = max(0.0, min(1.0, a))
        if a > 0:
            overlay["curiosity"] = min(1.0, a * 0.4)
    return overlay


def _frontend_personality(personality: dict) -> dict[str, Any]:
    """将内部人格数据转换为新前端期望的格式。"""
    traits = personality.get(
        "traits", personality if isinstance(personality, dict) else {}
    )
    five = {
        "openness": traits.get("openness", traits.get("curiosity", 0.5)),
        "warmth": traits.get("warmth", 0.5),
        "intensity": traits.get("intensity", traits.get("arousal", 0.5)),
        "autonomy": traits.get("autonomy", traits.get("sovereignty", 0.5)),
        "resilience": traits.get("resilience", traits.get("repair", 0.5)),
    }
    six_names = [
        "Curiosity",
        "Empathy",
        "Precision",
        "Playfulness",
        "Defiance",
        "Melancholy",
    ]
    six_keys = [
        "curiosity",
        "warmth",
        "coherence",
        "playfulness",
        "sovereignty",
        "melancholy",
    ]
    six_colors = ["#B88A9E", "#00b4d8", "#ffaa00", "#4caf50", "#ff4444", "#9c27b0"]
    six = [
        {"name": n, "value": float(traits.get(k, 0.5)), "color": c}
        for n, k, c in zip(six_names, six_keys, six_colors)
    ]
    drift_raw = personality.get("drift", {}) if isinstance(personality, dict) else {}
    drift_history = drift_raw.get("history", []) if isinstance(drift_raw, dict) else []
    drift = [
        {
            "time": str(d.get("time", "")),
            "text": str(d.get("text", d.get("signal", ""))),
        }
        for d in drift_history[-10:]
    ]
    return {"five": five, "six": six, "drift": drift}


def _frontend_spine_layers(timing_raw: dict, comp_diag: dict) -> list[dict[str, Any]]:
    """将内部计时数据转换为新前端期望的 spine_layers 数组。

    timing_raw 的 key 是内部名（perception/gate/void_scar/sheaf/hgt/boundary/expression），
    需要映射到前端的 L1-L7 标识。
    """
    # (前端ID, 内部timing key, 显示名, 描述)
    layer_meta = [
        ("L1", "perception", "HDC Perception",
         "Hyperdimensional binary encoding. Converts text to 2048-bit vectors."),
        ("L2", "gate", "Predictive Coding Gate",
         "Computes Hamming surprise against prediction. Routes processing path."),
        ("L3", "void_scar", "Void-Scar Engine",
         "Irreversible scar state tracking. Wounds heal through stages."),
        ("L4", "sheaf", "Relational Sheaf",
         "Cross-relationship propagation via sheaf Laplacian."),
        ("L5", "hgt", "MoE-HGT",
         "Mixture-of-Experts + Heterogeneous Graph Transformer."),
        ("L6", "boundary", "Autopoietic Boundary",
         "32-dim identity kernel with orthogonal projection."),
        ("L7", "expression", "Phase Transition",
         "Pressure accumulation to threshold. Expression modes."),
    ]
    result = []
    for lid, internal_key, name, desc in layer_meta:
        # 按内部 key 查找，兼容旧格式（L1/L2/...）
        stats = timing_raw.get(internal_key, timing_raw.get(lid, {}))
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
        result.append(
            {
                "id": lid,
                "name": name,
                "status": "active" if count > 0 else "idle",
                "avg": avg_ms,
                "p50": p50_ms,
                "p95": p95_ms,
                "p99": p99_ms,
                "count": count,
                "desc": desc,
            }
        )
    return result


def _build_state(plugin: Any, *, session: str = "") -> dict[str, Any]:
    """构建完整的 WebUI 状态字典。

    聚合情感向量、门控统计、路由统计、边界/表达/计时/层诊断、
    人格信息、社交场信息、生命模拟等，供前端 dashboard 渲染。
    """
    hosts = getattr(plugin, "_hosts", {}) or {}
    all_sessions = _known_sessions(plugin, requested=session)
    if not all_sessions:
        return {
            "schema_version": "sylanne.webui.state.v2",
            "runtime": _runtime_info(plugin),
            "current_session": "default",
            "emotion": {},
            "gate": {},
            "route_stats": {"resonance": 0, "skip": 0},
            "route_distribution": {"RESONANCE": 0, "SKIP": 0},
            "boundary": {},
            "expression": {},
            "timing": {},
            "layers": {},
            "spine": {"layers": {}},
            "persona": {},
            "theme": {"base": "#F3A7C8", "source": "emotion", "mode": "soft"},
            "feedback": {"accepted": 0, "ignored": 0, "rejected": 0},
            "sessions": [],
            "life_simulation": {},
        }

    session_key = session if session in all_sessions else all_sessions[0]

    # 如果没有指定 session，自动选择最活跃的（tick_count 最高的 host）
    # 避免选到从未处理过消息的 "default" 空 host
    if not session or session == "default" or session not in all_sessions:
        best_key = all_sessions[0]
        best_ticks = -1
        for sk in all_sessions:
            h = hosts.get(sk)
            if h is None:
                continue
            ticks = getattr(h.kernel.computation, "_tick_count", 0) if hasattr(h, "kernel") else 0
            if ticks > best_ticks:
                best_ticks = ticks
                best_key = sk
        session_key = best_key
    try:
        host = hosts.get(session_key)
        if host is None:
            host_getter = getattr(plugin, "_host", None)
            if callable(host_getter):
                host = host_getter(session_key)
                hosts = getattr(plugin, "_hosts", {}) or {}
        if host is None:
            raise KeyError(session_key)
        comp = host.kernel.computation
        gate = _comp_gate_dict(comp)
        # Route stats from computation spine counters
        comp_diag = comp.diagnostics() if hasattr(comp, "diagnostics") else {}
        route_stats, route_distribution = _comp_route_stats(comp)
        comp_result = getattr(host.kernel, "_last_computation_result", None) or {}
        layers = dict(comp_result.get("layers", {}))
        if not isinstance(layers, dict):
            layers = {}
        # Boundary: map internal field names to frontend-expected names
        boundary_raw = _comp_boundary_dict(comp)
        boundary = {
            "integrity": boundary_raw.get("boundary_integrity", 1.0),
            "entropy": boundary_raw.get("internal_entropy", 0.0),
            "stability": boundary_raw.get("stability", 1.0),
            "rotation": boundary_raw.get("phase_transitions", 0) * 6.0,
            "phase_transitions": boundary_raw.get("phase_transitions", 0),
            "self_repair_rate": boundary_raw.get("stability", 1.0),
        }
        expression = comp.expression.state()
        # Ensure all 9 emotion dimensions are present for the frontend
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
        # Timing: convert ns to ms
        timing_raw = comp.timing_stats() if hasattr(comp, "timing_stats") else {}
        timing = {}
        total_ms = 0.0
        for layer_name, layer_stats in timing_raw.items():
            ms_val = round(layer_stats.get("p50_ns", 0.0) / 1_000_000, 3)
            timing[f"{layer_name}_ms"] = ms_val
            total_ms += ms_val
        timing["total_ms"] = round(total_ms, 3)
        # 新前端期望 timing 为数组格式
        timing_array = []
        for layer_name, layer_stats in timing_raw.items():
            if not isinstance(layer_stats, dict):
                continue
            timing_array.append(
                {
                    "layer": layer_name,
                    "avg": f"{round(layer_stats.get('mean_ns', layer_stats.get('p50_ns', 0)) / 1_000_000, 1)}ms",
                    "p95": f"{round(layer_stats.get('p95_ns', layer_stats.get('p99_ns', 0)) / 1_000_000, 1)}ms",
                    "count": int(layer_stats.get("count", 0)),
                }
            )
        # Ensure L1_HDC layer has all fields from computation result + sample_bits
        sample_bits = list(
            (comp.last_hdc_sample if hasattr(comp, "last_hdc_sample") else None)
            or []
        )
        comp_l1 = comp_result.get("layers", {}).get("L1_HDC", {})
        if comp_l1:
            layers["L1_HDC"] = {**layers.get("L1_HDC", {}), **comp_l1}
        layers.setdefault("L1_HDC", {})
        layers["L1_HDC"].setdefault("sample_bits", sample_bits)
        layers["L1_HDC"].setdefault("vector_dim", 2048)
        layers["L1_HDC"].setdefault(
            "density",
            sum(sample_bits) / max(len(sample_bits), 1) if sample_bits else 0.0,
        )
        # L5 MoE-HGT rich diagnostics
        hgt = comp.hgt
        _hgt_attn = getattr(hgt, "_last_attention_weights", [])
        _hgt_experts = getattr(hgt, "_last_active_experts", [])
        _hgt_gates = getattr(hgt, "_last_gate_values", [])
        layers["L5_HGT"] = {
            "source": "moe_hgt",
            "decision": list(comp_result.get("hgt_decision", [])),
            "attention": [list(row) for row in _hgt_attn] if _hgt_attn else [],
            "experts": {
                "active": list(_hgt_experts) if _hgt_experts else [],
                "gates": [round(g, 4) for g in _hgt_gates] if _hgt_gates else [0] * 5,
                "names": ["defense", "curiosity", "social", "silence", "repair"],
            },
            "adaptation": hgt.adaptation_state()
            if hasattr(hgt, "adaptation_state")
            else {},
        }
        # Feedback stats (comp_diag already computed above for route_counts)
        feedback_raw = (
            comp_diag.get("feedback", {}) if isinstance(comp_diag, dict) else {}
        )
        feedback = {
            "accepted": int(feedback_raw.get("accepted", 0)),
            "ignored": int(feedback_raw.get("ignored", 0)),
            "rejected": int(feedback_raw.get("rejected", 0)),
            "positive": int(feedback_raw.get("accepted", 0)),
            "negative": int(feedback_raw.get("rejected", 0)),
            "neutral": int(feedback_raw.get("ignored", 0)),
        }
        personality = (
            host.kernel._personality() if hasattr(host.kernel, "_personality") else {}
        )
        persona_profile = (
            plugin._persona_profile(None)
            if hasattr(plugin, "_persona_profile")
            else {"name": "", "version": ""}
        )
        # Social field state
        social_field_state = {}
        try:
            sf = getattr(plugin, "_social_field", None)
            if sf:
                for gid, gs in sf._groups.items():
                    social_field_state[gid] = {
                        "shadow_buffer_size": len(gs.shadow_buffer),
                        "silence_ticks": gs.silence_ticks,
                        "void_pressure": round(gs.social_void_pressure, 3),
                        "ema_rate": round(gs.ema_rate, 3),
                    }
        except Exception:
            pass
        return {
            "schema_version": "sylanne.webui.state.v2",
            "tick_count": comp._tick_count,
            "runtime": _runtime_info(plugin),
            "current_session": session_key,
            "emotion": {
                **_EMOTION_DEFAULTS,
                **comp.engine.observe(),
                **_assessment_overlay(getattr(comp, "_last_assessment", None)),
            },
            "gate": {
                **gate,
                "history": gate.get("surprise_history", [])[-60:],
                "route": comp_result.get("route", "RESONANCE"),
            },
            "route_stats": route_stats,
            "boundary": boundary,
            "expression": expression,
            "timing": timing_array if timing_array else timing,
            "layers": layers,
            "spine": {
                "surprise": comp_result.get("surprise", gate.get("mean_surprise", 0.0)),
                "route": comp_result.get("route", ""),
                "last_text": _last_user_text(plugin, session_key),
                "last_bot_text": _last_bot_text(plugin, session_key)[:120],
                "sheaf": comp_result.get("sheaf", {}),
                "hgt_decision": comp_result.get("hgt_decision", []),
                "boundary": boundary,
                "expression": expression,
                "layers": layers,
            },
            "persona": {
                "profile": persona_profile,
                "traits": personality.get(
                    "traits", personality if isinstance(personality, dict) else {}
                ),
                "voice": personality.get("voice", {})
                if isinstance(personality, dict)
                else {},
                "drift": personality.get("drift", {})
                if isinstance(personality, dict)
                else {},
            },
            "theme": {"base": "#F3A7C8", "source": "emotion", "mode": "soft"},
            "feedback": feedback,
            "sessions": _webui_session_items(plugin, all_sessions),
            "social_field": social_field_state,
            "life_simulation": getattr(plugin, "_life_simulator", None)
            and plugin._life_simulator.to_dict()
            or {},
            # --- 新前端兼容字段 ---
            "session_id": session_key,
            "route_distribution": route_distribution,
            "personality": _frontend_personality(personality),
            "spine_layers": _frontend_spine_layers(timing_raw, comp_diag),
        }
    except Exception:
        logger.exception("Sylanne WebUI state build failed: session=%s", session_key)
        return {
            "schema_version": "sylanne.webui.state.v2",
            "runtime": _runtime_info(plugin),
            "current_session": session_key,
            "emotion": {},
            "gate": {},
            "route_stats": {"resonance": 0, "skip": 0},
            "route_distribution": {"RESONANCE": 0, "SKIP": 0},
            "boundary": {},
            "expression": {},
            "timing": {},
            "layers": {},
            "spine": {"layers": {}},
            "persona": {},
            "theme": {"base": "#F3A7C8", "source": "emotion", "mode": "soft"},
            "feedback": {"accepted": 0, "ignored": 0, "rejected": 0},
            "sessions": _webui_session_items(plugin, all_sessions),
            "life_simulation": {},
        }


def _memory_state_has_content(state: Any) -> bool:
    if state is None:
        return False
    if hasattr(state, "_l1") or hasattr(state, "_l2") or hasattr(state, "_l3_nodes"):
        return bool(
            list(getattr(state, "_l1", []) or [])
            or list(getattr(state, "_l2", []) or [])
            or dict(getattr(state, "_l3_nodes", {}) or {})
            or list(getattr(state, "_l3_edges", []) or [])
        )
    return bool(list(getattr(state, "records", []) or []))


def _legacy_trace_payload(trace: Any, session_key: str) -> dict[str, Any]:
    data = dict(trace or {}) if isinstance(trace, dict) else {"text": str(trace or "")}
    weight = float(data.get("weight", data.get("depth", 0.35)) or 0.35)
    temperature = float(data.get("temperature", data.get("warmth", 0.5)) or 0.5)
    data["session"] = session_key
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


def _body_traces_for_session(plugin: Any, session_key: str) -> list[dict[str, Any]]:
    try:
        host_getter = getattr(plugin, "_host", None)
        host = (
            host_getter(session_key)
            if callable(host_getter)
            else (getattr(plugin, "_hosts", {}) or {}).get(session_key)
        )
        raw_traces = (
            host.kernel.body.memory.get("traces", []) if host is not None else []
        )
    except Exception:
        raw_traces = []
    return [
        _legacy_trace_payload(trace, session_key) for trace in list(raw_traces or [])
    ]


def _memory_response_from_sources(
    *,
    source_sessions: list[str],
    states: dict[str, Any],
    legacy_traces: dict[str, list[dict[str, Any]]],
    session_key: str,
    overview: bool,
    limit: int,
) -> dict[str, Any]:
    l1_items: list[dict[str, Any]] = []
    l2_items: list[dict[str, Any]] = []
    l3_nodes: list[dict[str, Any]] = []
    l3_edges: list[dict[str, Any]] = []
    raw_l1_count = raw_l2_count = raw_l3_node_count = raw_l3_edge_count = 0
    legacy_hot: list[dict[str, Any]] = []
    legacy_warm: list[dict[str, Any]] = []
    legacy_records: list[dict[str, Any]] = []

    for source_session in source_sessions:
        state = states.get(source_session)
        if state is not None and (
            hasattr(state, "_l1")
            or hasattr(state, "_l2")
            or hasattr(state, "_l3_nodes")
        ):
            source_l1 = [
                _memory_system_item_payload(item)
                for item in list(getattr(state, "_l1", []) or [])
            ]
            source_l2 = [
                _memory_system_item_payload(item)
                for item in list(getattr(state, "_l2", []) or [])
            ]
            for item in source_l1 + source_l2:
                item.setdefault("session", source_session)
            nodes_raw = getattr(state, "_l3_nodes", {}) or {}
            edges_raw = getattr(state, "_l3_edges", []) or []
            source_nodes = [
                _memory_graph_node_payload(node) for node in list(nodes_raw.values())
            ]
            for node in source_nodes:
                node.setdefault("session", source_session)
            source_edges = [
                edge.to_dict() if hasattr(edge, "to_dict") else dict(edge or {})
                for edge in list(edges_raw)
            ]
            for edge in source_edges:
                edge.setdefault("session", source_session)
            l1_items.extend(source_l1)
            l2_items.extend(source_l2)
            l3_nodes.extend(source_nodes)
            l3_edges.extend(source_edges)
            raw_l1_count += len(getattr(state, "_l1", []) or [])
            raw_l2_count += len(getattr(state, "_l2", []) or [])
            raw_l3_node_count += len(nodes_raw)
            raw_l3_edge_count += len(edges_raw)
        elif state is not None:
            records = [
                _memory_record_payload(record)
                for record in list(getattr(state, "records", []) or [])
            ]
            for record in records:
                record.setdefault("session", source_session)
            legacy_records.extend(records)

        if not _memory_state_has_content(state):
            traces = legacy_traces.get(source_session, [])
            legacy_hot.extend(traces)
            legacy_warm.extend(
                item for item in traces if float(item.get("weight", 0.0) or 0.0) >= 0.5
            )

    if legacy_records and not (l1_items or l2_items or l3_nodes or legacy_hot):
        hot = sorted(
            legacy_records,
            key=lambda item: float(item.get("created_at", 0.0) or 0.0),
            reverse=True,
        )[:limit]
        warm = sorted(
            (
                item
                for item in legacy_records
                if float(item.get("weight", 0.0) or 0.0) >= 0.5
                or int(item.get("recall_count", 0) or 0) > 0
            ),
            key=lambda item: (
                float(item.get("weight", 0.0) or 0.0),
                float(item.get("updated_at", 0.0) or 0.0),
            ),
            reverse=True,
        )[:limit]
        payloads = hot + warm
        total = len(payloads)
        summary = {
            "total": total,
            "l1_count": len(hot),
            "l2_count": len(warm),
            "l3_node_count": 0,
            "l3_edge_count": 0,
            "embedded": sum(1 for item in payloads if item.get("has_embedding")),
            "avg_weight": round(
                sum(float(item.get("weight", 0.0) or 0.0) for item in payloads) / total,
                4,
            )
            if total
            else 0.0,
            "avg_temperature": round(
                sum(float(item.get("temperature", 0.0) or 0.0) for item in payloads)
                / total,
                4,
            )
            if total
            else 0.5,
        }
        return {
            "schema_version": "sylanne.webui.memory.v1",
            "architecture": "legacy.sylanne_memory_state.compat",
            "session": "default" if overview else session_key,
            "mode": "overview" if overview else "session",
            "sessions": source_sessions,
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
        l3_nodes, key=lambda item: float(item.get("weight", 0.0) or 0.0), reverse=True
    )[:limit]
    l3_edges = l3_edges[:limit]
    payloads = l1_items + l2_items + l3_nodes
    total = len(payloads)
    summary = {
        "total": total,
        "l1_count": raw_l1_count,
        "l2_count": raw_l2_count,
        "l3_node_count": raw_l3_node_count,
        "l3_edge_count": raw_l3_edge_count,
        "legacy_trace_count": len(legacy_hot),
        "embedded": sum(1 for item in l1_items + l2_items if item.get("has_embedding")),
        "avg_weight": round(
            sum(float(item.get("weight", 0.0) or 0.0) for item in payloads) / total, 4
        )
        if total
        else 0.0,
        "avg_temperature": round(
            sum(float(item.get("temperature", 0.0) or 0.0) for item in payloads)
            / total,
            4,
        )
        if total
        else 0.5,
    }
    return {
        "schema_version": "sylanne.webui.memory.v1",
        "architecture": "sylanne_alpha.memory_system.three_layer",
        "session": "default" if overview else session_key,
        "mode": "overview" if overview else "session",
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


async def _build_memory_pools(
    plugin: Any, *, session: str = "", limit: int = 50
) -> dict[str, Any]:
    """构建三层记忆池数据（异步版本，支持 KV 存储加载）。"""
    sessions = _known_sessions(plugin, requested=session)
    overview = not session or session == "default"
    session_key = (
        session if session in sessions else (sessions[0] if sessions else "default")
    )
    source_sessions = [item for item in sessions if item] if overview else [session_key]
    if not source_sessions:
        source_sessions = [session_key or "default"]

    states: dict[str, Any] = {}
    legacy_traces: dict[str, list[dict[str, Any]]] = {}
    loader = getattr(plugin, "_load_sylanne_memory_state", None)
    getter = getattr(plugin, "_memory_system_for_session", None)
    cache = getattr(plugin, "_sylanne_memory_cache", {}) or {}
    for source_session in source_sessions:
        state = None
        if callable(loader):
            try:
                state = await loader(source_session)
            except Exception:
                state = None
        if state is None and isinstance(cache, dict):
            state = cache.get(source_session)
        if state is None and callable(getter):
            state = getter(source_session)
        states[source_session] = state
        legacy_traces[source_session] = _body_traces_for_session(plugin, source_session)

    return _memory_response_from_sources(
        source_sessions=source_sessions,
        states=states,
        legacy_traces=legacy_traces,
        session_key=session_key,
        overview=overview,
        limit=limit,
    )


def _build_memory_pools_sync(
    plugin: Any, *, session: str = "", limit: int = 50
) -> dict[str, Any]:
    """构建三层记忆池数据（同步版本，供 stdlib HTTP server 使用）。"""
    sessions = _known_sessions(plugin, requested=session)
    overview = not session or session == "default"
    session_key = (
        session if session in sessions else (sessions[0] if sessions else "default")
    )
    source_sessions = [item for item in sessions if item] if overview else [session_key]
    if not source_sessions:
        source_sessions = [session_key or "default"]

    states: dict[str, Any] = {}
    legacy_traces: dict[str, list[dict[str, Any]]] = {}
    cache = getattr(plugin, "_sylanne_memory_cache", {}) or {}
    getter = getattr(plugin, "_memory_system_for_session", None)
    for source_session in source_sessions:
        state = cache.get(source_session) if isinstance(cache, dict) else None
        if state is None and callable(getter):
            state = getter(source_session)
        states[source_session] = state
        legacy_traces[source_session] = _body_traces_for_session(plugin, source_session)

    return _memory_response_from_sources(
        source_sessions=source_sessions,
        states=states,
        legacy_traces=legacy_traces,
        session_key=session_key,
        overview=overview,
        limit=limit,
    )


def _memory_record_payload(record: Any) -> dict[str, Any]:
    data = record.to_dict() if hasattr(record, "to_dict") else dict(record or {})
    signature = data.get("emotional_signature") or {}
    if not isinstance(signature, dict):
        signature = {}
    arousal = abs(
        float(signature.get("arousal", signature.get("tension", 0.35)) or 0.35)
    )
    warmth = abs(float(signature.get("warmth", signature.get("valence", 0.45)) or 0.45))
    depth = float(data.get("depth", 0.0) or 0.0)
    confidence = float(data.get("confidence", 0.35) or 0.35)
    recall = min(1.0, float(data.get("recall_count", 0) or 0) / 5.0)
    evidence = min(1.0, float(data.get("evidence_count", 1) or 1) / 4.0)
    interference = float(data.get("interference", 0.0) or 0.0)
    weight = (
        depth * 0.45
        + confidence * 0.25
        + recall * 0.20
        + evidence * 0.10
        - interference * 0.15
    )
    data["weight"] = round(max(0.0, min(1.0, weight)), 4)
    data["temperature"] = round(max(0.0, min(1.0, (arousal + warmth) / 2.0)), 4)
    data["has_embedding"] = bool(
        data.get("embedding")
        or data.get("semantic_embedding")
        or data.get("embedding_provider_id")
    )
    data.pop("embedding", None)
    data.pop("semantic_embedding", None)
    return data


def _memory_system_item_payload(item: Any) -> dict[str, Any]:
    data = item.to_dict() if hasattr(item, "to_dict") else dict(item or {})
    data["weight"] = round(max(0.0, min(1.0, float(data.get("weight", 0.0) or 0.0))), 4)
    data["temperature"] = round(
        max(0.0, min(1.0, float(data.get("temperature", 0.5) or 0.5))), 4
    )
    data["has_embedding"] = bool(
        data.get("embedding")
        or data.get("semantic_embedding")
        or data.get("embedding_provider_id")
    )
    data.pop("embedding", None)
    data.pop("semantic_embedding", None)
    return data


def _memory_graph_node_payload(node: Any) -> dict[str, Any]:
    data = node.to_dict() if hasattr(node, "to_dict") else dict(node or {})
    clarity = float(data.get("clarity", data.get("weight", 0.0)) or 0.0)
    emotion_weight = float(
        data.get("emotion_weight", data.get("temperature", 0.0)) or 0.0
    )
    data["summary"] = data.get("label", data.get("summary", data.get("text", "")))
    data["text"] = (
        data.get("text")
        or f"{data.get('type', 'node')} / {data.get('temporal_type', 'episodic')}"
    )
    data["weight"] = round(max(0.0, min(1.0, clarity)), 4)
    data["temperature"] = round(max(0.0, min(1.0, (emotion_weight + 1.0) / 2.0)), 4)
    data["has_embedding"] = False
    return data


def _load_schema(plugin: Any) -> dict[str, Any]:
    """加载配置 schema（_conf_schema.json）。"""
    schema_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_conf_schema.json"
    )
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _get_process_memory_mb() -> float:
    """获取当前进程内存占用（MB）。优先 psutil，其次 resource，都不可用返回 -1。"""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return round(process.memory_info().rss / 1024 / 1024, 1)
    except Exception:
        pass
    try:
        import resource
        # resource.getrusage 在 Linux 返回 KB，macOS 返回 bytes
        usage = resource.getrusage(resource.RUSAGE_SELF)
        rss_kb = usage.ru_maxrss
        if sys.platform == "darwin":
            return round(rss_kb / 1024 / 1024, 1)
        return round(rss_kb / 1024, 1)
    except Exception:
        pass
    return -1


def _build_widget_state(plugin: Any) -> dict[str, Any]:
    """构建 AstrBot 管理面板状态卡片数据。"""
    # phase: 从最活跃 host 的 computation spine 获取
    phase = "normal"
    temperature = 0.0
    scars = 0
    memory_count = 0
    hosts = getattr(plugin, "_hosts", {}) or {}
    if isinstance(hosts, dict):
        for h in hosts.values():
            try:
                comp = h.kernel.computation
                expr = comp.expression.state()
                phase = str(expr.get("mode", "normal"))
                engine_obs = comp.engine.observe()
                temperature = round(float(engine_obs.get("warmth", 0.0)), 2)
                scars = int(engine_obs.get("active_scars", engine_obs.get("scar_count", 0)))
                break
            except Exception:
                continue
    # memory_count: 所有会话的 L1+L2 条目总数
    try:
        mem_getter = getattr(plugin, "_memory_system_for_session", None)
        if callable(mem_getter) and isinstance(hosts, dict):
            for sk in hosts:
                ms = mem_getter(sk)
                if ms:
                    memory_count += len(getattr(ms, "_l1", []) or [])
                    memory_count += len(getattr(ms, "_l2", []) or [])
    except Exception:
        pass
    return {
        "phase": phase,
        "temperature": temperature,
        "scars": scars,
        "memory_count": memory_count,
        "version": _get_plugin_version(),
    }


# ---------------------------------------------------------------------------
# WebUILifecycle: server lifecycle management extracted from main.py
# ---------------------------------------------------------------------------


class WebUILifecycle:
    """WebUI 服务器生命周期管理器。

    封装启动/停止/接管的完整逻辑，处理 AstrBot 热重载场景下的
    旧监听器清理和新监听器启动。

    关键能力：
    - start_if_enabled(): 幂等启动
    - publish_active_plugin(): 将所有已加载的 WebUI 模块指向当前插件实例
    - stop_stale_server_modules(): 清理热重载遗留的旧监听器
    - schedule_listener_takeover(): 延迟接管（等待旧模块完全卸载）
    """

    def __init__(self, plugin: PluginHost) -> None:
        self._p = plugin

    def start_if_enabled(self) -> None:
        """当配置启用 WebUI 时启动独立服务器。

        幂等设计：若已有活跃的 task 或 thread 则跳过。
        """
        if not self._p._cfg_bool("sylanne_webui_enabled", False):
            return
        self.publish_active_plugin()
        webui_mod = self._current_webui_module_ref()
        if (
            getattr(webui_mod, "_server_task", None)
            and not webui_mod._server_task.done()
        ) or (
            getattr(webui_mod, "_httpd_thread", None)
            and webui_mod._httpd_thread.is_alive()
        ):
            return
        webui_host = str(self._p._cfg("sylanne_webui_host", "127.0.0.1") or "127.0.0.1")
        webui_port = self._p._cfg_int("sylanne_webui_port", 2718)
        token = _ensure_token(self._p._config or {})
        # 不把 bearer token 明文写进日志(日志常被收集/转发/共享=凭据泄露);token 已由
        # _ensure_token 持久化进配置,运维需要时从配置取。这里只记"已就绪 + 长度"。
        self._p.logger.info("Sylanne WebUI auth token ready (redacted, %d chars)", len(token))
        try:
            start_webui_background(self._p, host=webui_host, port=webui_port)
            self._p.logger.info(
                f"Sylanne WebUI server start requested: http://{webui_host}:{webui_port}"
            )
        except RuntimeError as exc:
            self._p.logger.debug(
                f"Sylanne WebUI server deferred until event loop is running: {exc}"
            )
        except Exception as exc:
            self._p.logger.warning(f"Sylanne WebUI server failed: {exc}")

    def runtime_info(self) -> dict[str, Any]:
        return {
            "plugin_name": "astrbot_plugin_sylanne",
            "runtime_id": str(getattr(self._p, "_webui_runtime_id", "") or ""),
            "instance_id": hex(id(self._p)),
            "module": self._p.__class__.__module__,
        }

    def iter_loaded_server_modules(self) -> list[tuple[str, Any]]:
        modules: list[tuple[str, Any]] = []
        seen: set[int] = set()

        def add_module(name: str, module: Any) -> None:
            if module is None or id(module) in seen:
                return
            module_file = str(getattr(module, "__file__", "") or "").replace("\\", "/")
            if not module_file.endswith("/sylanne_alpha/webui_server.py"):
                return
            if not any(
                hasattr(module, attr)
                for attr in (
                    "_set_active_plugin",
                    "stop_webui_server",
                    "start_webui_background",
                    "_server_task",
                    "_httpd",
                    "_httpd_thread",
                )
            ):
                return
            seen.add(id(module))
            modules.append((name, module))

        def add_namespace(name: str, namespace: Any) -> None:
            if not isinstance(namespace, dict) or id(namespace) in seen:
                return
            module_file = str(namespace.get("__file__", "") or "").replace("\\", "/")
            if not module_file.endswith("/sylanne_alpha/webui_server.py"):
                return
            if not any(
                attr in namespace
                for attr in (
                    "_set_active_plugin",
                    "stop_webui_server",
                    "start_webui_background",
                    "_server_task",
                    "_httpd",
                    "_httpd_thread",
                )
            ):
                return
            seen.add(id(namespace))
            modules.append((name, namespace))

        for name, module in list(sys.modules.items()):
            add_module(name, module)
        try:
            for obj in gc.get_objects():
                if isinstance(obj, ModuleType):
                    add_module(str(getattr(obj, "__name__", "gc.module")), obj)
                elif isinstance(obj, dict):
                    add_namespace(str(obj.get("__name__", "gc.globals")), obj)
        except Exception:
            pass  # cleanup: gc introspection failure acceptable
        return modules

    def module_get(self, module: Any, attr: str, default: Any = None) -> Any:
        if isinstance(module, dict):
            return module.get(attr, default)
        return getattr(module, attr, default)

    def module_set(self, module: Any, attr: str, value: Any) -> None:
        if isinstance(module, dict):
            module[attr] = value
        else:
            setattr(module, attr, value)

    def is_current_module(self, module: Any) -> bool:
        webui_mod = self._current_webui_module_ref()
        return module is webui_mod or module is getattr(webui_mod, "__dict__", None)

    def is_server_task(self, task: asyncio.Task) -> bool:
        try:
            stack = list(task.get_stack(limit=8))
        except Exception:
            stack = []
        for frame in stack:
            filename = str(
                getattr(getattr(frame, "f_code", None), "co_filename", "") or ""
            ).replace("\\", "/")
            if filename.endswith("/sylanne_alpha/webui_server.py"):
                return True

        coro: Any = None
        try:
            coro = task.get_coro()
        except Exception:
            return False
        seen: set[int] = set()
        while coro is not None and id(coro) not in seen:
            seen.add(id(coro))
            code = (
                getattr(coro, "cr_code", None)
                or getattr(coro, "gi_code", None)
                or getattr(coro, "ag_code", None)
            )
            filename = str(getattr(code, "co_filename", "") or "").replace("\\", "/")
            if filename.endswith("/sylanne_alpha/webui_server.py"):
                return True

            frame = (
                getattr(coro, "cr_frame", None)
                or getattr(coro, "gi_frame", None)
                or getattr(coro, "ag_frame", None)
            )
            globals_dict = getattr(frame, "f_globals", {}) if frame is not None else {}
            module_file = str((globals_dict or {}).get("__file__", "") or "").replace(
                "\\", "/"
            )
            if module_file.endswith("/sylanne_alpha/webui_server.py"):
                return True
            coro = (
                getattr(coro, "cr_await", None)
                or getattr(coro, "gi_yieldfrom", None)
                or getattr(coro, "ag_await", None)
            )
        return False

    async def stop_server_tasks(self) -> list[str]:
        stopped: list[str] = []
        try:
            tasks = [
                task
                for task in asyncio.all_tasks()
                if task is not asyncio.current_task()
            ]
        except Exception:
            return stopped
        webui_tasks = [
            task for task in tasks if not task.done() and self.is_server_task(task)
        ]
        for task in webui_tasks:
            try:
                task.cancel()
                coro = task.get_coro()
                name = (
                    getattr(coro, "__qualname__", "")
                    or getattr(coro, "__name__", "")
                    or repr(coro)
                )
                stopped.append(f"task:{name}")
            except Exception:
                continue
        if webui_tasks:
            try:
                await asyncio.wait(webui_tasks, timeout=2.0)
            except Exception:
                pass  # cleanup: task wait failure acceptable
        return stopped

    def publish_active_plugin(self) -> list[str]:
        """将所有已加载的 Sylanne WebUI 监听器模块指向当前插件实例。"""
        updated: list[str] = []
        for name, module in self.iter_loaded_server_modules():
            setter = self.module_get(module, "_set_active_plugin")
            if not callable(setter):
                continue
            try:
                setter(self._p)
                updated.append(name)
            except Exception:
                continue
        return updated

    async def stop_stale_server_modules(
        self, *, include_current: bool = False
    ) -> list[str]:
        """停止热重载遗留的旧 WebUI 模块，释放端口占用。"""
        stopped: list[str] = []
        for name, module in self.iter_loaded_server_modules():
            if self.is_current_module(module) and not include_current:
                continue
            try:
                if await self.stop_server_module(module):
                    stopped.append(name)
            except Exception:
                continue
        if include_current:
            try:
                stopped.extend(await self.stop_server_tasks())
            except Exception:
                pass  # cleanup: failure acceptable
        self.publish_active_plugin()
        return stopped

    async def stop_server_module(self, module: Any) -> bool:
        """尽力关闭一个 WebUI 模块（支持新旧两种模块格式）。"""
        stopper = self.module_get(module, "stop_webui_server")
        if callable(stopper):
            result = stopper()
            if hasattr(result, "__await__"):
                await result
            return True

        stopped = False
        task = self.module_get(module, "_server_task")
        if task is not None:
            try:
                if not task.done():
                    task.cancel()

                    try:
                        await asyncio.wait_for(task, timeout=2.0)
                    except (
                        asyncio.CancelledError,
                        asyncio.TimeoutError,
                        RuntimeError,
                        ValueError,
                    ):
                        pass
                stopped = True
            except Exception:
                pass  # cleanup: task cancel failure acceptable

        httpd = self.module_get(module, "_httpd")
        if httpd is not None:
            for method_name in ("shutdown", "server_close"):
                method = getattr(httpd, method_name, None)
                if callable(method):
                    try:
                        method()
                    except Exception:
                        pass  # cleanup: failure acceptable
            stopped = True

        thread = self.module_get(module, "_httpd_thread")
        if thread is not None and callable(getattr(thread, "is_alive", None)):
            try:
                if thread.is_alive():
                    thread.join(timeout=2.0)
            except Exception:
                pass  # cleanup: failure acceptable
            stopped = True

        for attr in ("_server_task", "_httpd", "_httpd_thread", "_active_plugin"):
            exists = (
                attr in module if isinstance(module, dict) else hasattr(module, attr)
            )
            if exists:
                try:
                    self.module_set(module, attr, None)
                except Exception:
                    pass  # cleanup: failure acceptable
        return stopped

    def schedule_listener_takeover(self) -> None:
        if not self._p._cfg_bool("sylanne_webui_enabled", False):
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        async def _takeover() -> None:
            await asyncio.sleep(0.3)
            stopped = await self.stop_stale_server_modules(include_current=True)
            if stopped:
                self._p.logger.info(
                    f"Sylanne WebUI stopped stale listener modules: {stopped}"
                )
            self.start_if_enabled()

        task = loop.create_task(_takeover())
        ensure_background_tasks_list(self._p).append(task)

    def _current_webui_module_ref(self) -> Any:
        """Return the current webui_server module reference from sys.modules."""
        return sys.modules.get("sylanne_alpha.webui_server", sys.modules[__name__])
