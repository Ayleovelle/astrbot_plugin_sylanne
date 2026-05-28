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
import secrets
import sys
import threading
import time
from types import ModuleType
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

from pathlib import Path

try:
    from astrbot.core.utils.astrbot_path import get_astrbot_data_path  # type: ignore
except ImportError:

    def get_astrbot_data_path() -> Path:  # type: ignore
        return Path.home()


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# 模块级全局状态：跨热重载保持监听器引用
# 使用 globals().get() 是为了在 AstrBot hot-upload 重新 import 时保留已有值
_server_task: asyncio.Task | None = globals().get("_server_task")
_httpd: Any = globals().get("_httpd")
_httpd_thread: threading.Thread | None = globals().get("_httpd_thread")
_active_plugin: Any = globals().get("_active_plugin")
_active_token: str = ""
_meltdown_nonces: dict[str, str] = {}
# 线程安全锁：stdlib HTTP server 的多线程 handler 访问插件状态时使用
_plugin_access_lock = threading.Lock()

# diagnostics 自动联动：有 /api/computation_logs 请求时开启，30s 无请求后关闭
_last_diag_request: float = 0


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
    global _active_token
    token = str(config.get("sylanne_webui_token", "") or "")
    if not token:
        token = secrets.token_urlsafe(32)
        config["sylanne_webui_token"] = token
    _active_token = token
    return token


def _set_active_plugin(plugin: Any) -> None:
    """将独立监听器指向最新的插件实例（热重载时调用）。"""
    global _active_plugin
    _active_plugin = plugin


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
        if request.path in ("/", "/logo.png", "/assets/logo.png"):
            return await handler(request)
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != _active_token:
            return web.json_response({"error": "unauthorized"}, status=401)
        return await handler(request)

    # Serve the dashboard HTML from UI/index.html
    plugin_root = Path(__file__).resolve().parent.parent
    dashboard_path = plugin_root / "UI" / "index.html"
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

    async def handle_page(request: web.Request) -> web.Response:
        return web.Response(
            text=dashboard_html, content_type="text/html", charset="utf-8"
        )

    async def handle_state(request: web.Request) -> web.Response:
        # 自动关闭 diagnostics：超过 30s 无 computation_logs 请求
        if _last_diag_request and time.time() - _last_diag_request > 30:
            current = _plugin(plugin)
            if current is not None:
                _set_spine_diagnostics(current, False)
        data = _build_state(
            _plugin(plugin), session=str(request.query.get("session", "") or "")
        )
        return web.json_response(data)

    async def handle_settings_get(request: web.Request) -> web.Response:
        current_plugin = _plugin(plugin)
        schema = _load_schema(current_plugin)
        config = dict(getattr(current_plugin, "_config", {}) or {})
        # Ensure every schema key is present in values (use default if unconfigured)
        values = {}
        for key, meta in schema.items():
            values[key] = config.get(key, meta.get("default"))
        return web.json_response(
            {
                "schema": schema,
                "values": values,
                "providers": await _provider_items(current_plugin),
            }
        )

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
        import os

        logo_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logo.png"
        )
        if not os.path.exists(logo_path):
            return web.Response(text="Not Found", status=404)
        with open(logo_path, "rb") as f:
            data = f.read()
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
        hosts = getattr(current_plugin, "_hosts", {}) or {}
        if session in hosts:
            hosts[session].kernel.body.memory["traces"] = []
            hosts[session].kernel.body.memory.pop("_memory_system", None)
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

    app.router.add_get("/", handle_page)
    app.router.add_get("/api/state", handle_state)
    app.router.add_get("/api/settings", handle_settings_get)
    app.router.add_post("/api/settings", handle_settings_post)
    app.router.add_get("/api/computation_logs", handle_computation_logs)
    app.router.add_get("/api/memory_pools", handle_memory_pools)
    app.router.add_get("/api/meltdown_nonce", handle_meltdown_nonce)
    app.router.add_get("/api/memory_sink", handle_memory_sink)
    app.router.add_post("/api/memory_consolidate", handle_memory_consolidate)
    app.router.add_post("/api/memory_meltdown", handle_memory_meltdown)
    app.router.add_get("/assets/logo.png", handle_logo)
    app.router.add_get("/logo.png", handle_logo)

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
        while True:
            await asyncio.sleep(3600)
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
    global _server_task, _httpd, _httpd_thread, _active_plugin
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
        _RATE_LIMIT_MAX = 60  # max requests per window
        _RATE_LIMIT_WINDOW_SEC = 60.0

        def log_message(self, fmt: str, *args: Any) -> None:
            logger.debug("Sylanne WebUI: " + fmt, *args)

        def _check_rate_limit(self) -> bool:
            """Return True if request should be rejected (rate limited)."""
            client_ip = self.client_address[0]
            now = time.time()
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
            self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
            self.send_header(
                "Access-Control-Allow-Headers", "Content-Type,Authorization"
            )
            self.end_headers()

        def do_GET(self) -> None:
            global _last_diag_request
            if self._check_rate_limit():
                self._send_json({"error": "rate_limited"}, status=429)
                return
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            if path not in ("/", "/logo.png", "/assets/logo.png"):
                auth = self.headers.get("Authorization", "")
                if not auth.startswith("Bearer ") or auth[7:] != _active_token:
                    self._send_json({"error": "unauthorized"}, status=401)
                    return
            query = self._query()
            try:
                if path == "/":
                    self._send_text(dashboard_html)
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
                    self._send_json(state)
                elif path == "/api/settings":
                    with _plugin_access_lock:
                        current_plugin = _plugin(plugin)
                        schema = _load_schema(current_plugin)
                        config = dict(getattr(current_plugin, "_config", {}) or {})
                        values = {
                            key: config.get(key, meta.get("default"))
                            for key, meta in schema.items()
                        }
                    self._send_json(
                        {"schema": schema, "values": values, "providers": []}
                    )
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
                elif path in {"/assets/logo.png", "/logo.png"}:
                    self._send_logo()
                else:
                    self.send_error(404)
            except Exception as exc:
                logger.warning(f"Sylanne WebUI GET error: {exc}", exc_info=True)
                self._send_json({"ok": False, "error": "internal_error"}, status=500)

        def do_POST(self) -> None:
            if self._check_rate_limit():
                self._send_json({"error": "rate_limited"}, status=429)
                return
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            if path not in ("/", "/logo.png", "/assets/logo.png"):
                auth = self.headers.get("Authorization", "")
                if not auth.startswith("Bearer ") or auth[7:] != _active_token:
                    self._send_json({"error": "unauthorized"}, status=401)
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
                    self._send_json({"ok": True, "updated": updated})
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=500)
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
                    loop = asyncio.get_event_loop()
                    loop.call_soon_threadsafe(
                        asyncio.ensure_future,
                        current_plugin._trigger_consolidation(session),
                    )
                    self._send_json({"ok": True, "estimated_seconds": 30})
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=500)
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
                        hosts = getattr(current_plugin, "_hosts", {}) or {}
                        if session in hosts:
                            hosts[session].kernel.body.memory["traces"] = []
                            hosts[session].kernel.body.memory.pop(
                                "_memory_system", None
                            )
                    logger.info(f"Sylanne MEMORY MELTDOWN (stdlib): session={session}")
                    self._send_json({"ok": True, "session": session, "cleared": True})
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=500)
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

    for method_name, provider_type in (
        ("get_all_providers", "llm"),
        ("get_all_llm_providers", "llm"),
        ("get_all_embedding_providers", "embedding"),
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
        root = Path(
            str(
                config.get("sylanne_alpha_root")
                or get_astrbot_data_path() / "sylanne_alpha"
            )
        )
        if root.exists():
            for path in root.glob("*.alpha.json"):
                add(path.name[: -len(".alpha.json")])
    except Exception:
        pass
    if not sessions:
        add("default")
    return sessions


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
        avg_ms = round(stats.get("mean_ns", stats.get("p50_ns", 0)) / 1_000_000, 1)
        p50_ms = round(stats.get("p50_ns", 0) / 1_000_000, 1)
        p99_ms = round(stats.get("p99_ns", stats.get("p95_ns", 0)) / 1_000_000, 1)
        count = int(stats.get("count", 0))
        result.append(
            {
                "id": lid,
                "name": name,
                "status": "active" if count > 0 else "idle",
                "avg": avg_ms,
                "p50": p50_ms,
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
            "schema_version": "sylanne.webui.state.v1",
            "runtime": _runtime_info(plugin),
            "current_session": "default",
            "emotion": {},
            "gate": {},
            "route_stats": {"fast": 0, "normal": 0, "full": 0, "skip": 0},
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
    if not session or session not in all_sessions:
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
        gate = comp.gate.to_dict()
        # Route stats from computation spine counters
        comp_diag = comp.diagnostics() if hasattr(comp, "diagnostics") else {}
        route_counts = (
            comp_diag.get("route_counts", {}) if isinstance(comp_diag, dict) else {}
        )
        route_stats = {
            "fast": int(route_counts.get("fast", 0)),
            "normal": int(route_counts.get("normal", 0)),
            "full": int(route_counts.get("full", 0)),
            "skip": int(route_counts.get("skip", 0)),
        }
        comp_result = getattr(host.kernel, "_last_computation_result", None) or {}
        layers = dict(comp_result.get("layers", {}))
        if not isinstance(layers, dict):
            layers = {}
        # Boundary: map internal field names to frontend-expected names
        boundary_raw = comp.boundary.to_dict()
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
        timing_raw = comp.timing_stats()
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
        sample_bits = comp.last_hdc_sample if hasattr(comp, "last_hdc_sample") else []
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
            "schema_version": "sylanne.webui.state.v1",
            "tick_count": comp._tick_count,
            "runtime": _runtime_info(plugin),
            "current_session": session_key,
            "emotion": {
                **_EMOTION_DEFAULTS,
                **comp.engine.observe(),
                **_assessment_overlay(comp._last_assessment),
            },
            "gate": {
                **gate,
                "history": gate.get("surprise_history", [])[-60:],
                "route": comp_result.get("route", "NORMAL"),
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
            "sessions": all_sessions,
            "social_field": social_field_state,
            "life_simulation": getattr(plugin, "_life_simulator", None)
            and plugin._life_simulator.to_dict()
            or {},
            # --- 新前端兼容字段 ---
            "session_id": session_key,
            "route_distribution": {
                "FAST": route_stats["fast"],
                "NORMAL": route_stats["normal"],
                "FULL": route_stats["full"],
                "SKIP": route_stats["skip"],
            },
            "personality": _frontend_personality(personality),
            "spine_layers": _frontend_spine_layers(timing_raw, comp_diag),
        }
    except Exception:
        return {
            "schema_version": "sylanne.webui.state.v1",
            "runtime": _runtime_info(plugin),
            "current_session": session_key,
            "emotion": {},
            "gate": {},
            "route_stats": {"fast": 0, "normal": 0, "full": 0, "skip": 0},
            "boundary": {},
            "expression": {},
            "timing": {},
            "layers": {},
            "spine": {"layers": {}},
            "persona": {},
            "theme": {"base": "#F3A7C8", "source": "emotion", "mode": "soft"},
            "feedback": {"accepted": 0, "ignored": 0, "rejected": 0},
            "sessions": all_sessions,
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
    import os

    schema_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_conf_schema.json"
    )
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


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

    def __init__(self, plugin: Any) -> None:
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
        self._p.logger.info(f"Sylanne WebUI token: {token}")
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
        self._p._background_tasks.append(task)

    def _current_webui_module_ref(self) -> Any:
        """Return the current webui_server module reference from sys.modules."""
        return sys.modules.get("sylanne_alpha.webui_server", sys.modules[__name__])
