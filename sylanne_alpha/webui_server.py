"""Sylanne-Embodiment: Standalone WebUI Server.

Runs an independent HTTP server on a configurable port (default 2718).
Not behind AstrBot's auth - direct access to the dashboard.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_server_task: asyncio.Task | None = None


async def start_webui_server(plugin: Any, host: str = "0.0.0.0", port: int = 2718):
    """Start standalone WebUI server in background."""
    global _server_task
    if _server_task and not _server_task.done():
        return

    from aiohttp import web

    from .webui import WEBUI_HTML

    app = web.Application()

    async def handle_page(request: web.Request) -> web.Response:
        return web.Response(text=WEBUI_HTML, content_type="text/html", charset="utf-8")

    async def handle_state(request: web.Request) -> web.Response:
        data = _build_state(plugin)
        return web.json_response(data)

    async def handle_settings_get(request: web.Request) -> web.Response:
        schema = _load_schema(plugin)
        config = dict(getattr(plugin, "_config", {}) or {})
        return web.json_response({"schema": schema, "values": config})

    async def handle_settings_post(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if isinstance(body, dict):
            config = getattr(plugin, "_config", {})
            for key, value in body.items():
                config[key] = value
            if hasattr(plugin, "config"):
                plugin.config.update(body)
        return web.json_response({"ok": True, "updated": list(body.keys())})

    app.router.add_get("/", handle_page)
    app.router.add_get("/api/state", handle_state)
    app.router.add_get("/api/settings", handle_settings_get)
    app.router.add_post("/api/settings", handle_settings_post)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    try:
        await site.start()
        logger.info(f"Sylanne WebUI server started at http://{host}:{port}")
    except OSError as e:
        logger.warning(f"Sylanne WebUI server failed to start on port {port}: {e}")
        return

    # Keep running until cancelled
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        await runner.cleanup()


def start_webui_background(plugin: Any):
    """Launch the WebUI server as a background task."""
    global _server_task
    if _server_task and not _server_task.done():
        return
    config = getattr(plugin, "_config", {}) or {}
    if not config.get("sylanne_alpha_webui_enabled", True):
        return
    host = str(config.get("sylanne_alpha_webui_host", "0.0.0.0"))
    port = int(config.get("sylanne_alpha_webui_port", 2718))
    _server_task = asyncio.ensure_future(start_webui_server(plugin, host=host, port=port))


def _build_state(plugin: Any) -> dict[str, Any]:
    """Build full state dict for the WebUI."""
    hosts = getattr(plugin, "_hosts", {})
    all_sessions = list(hosts.keys())
    if not all_sessions:
        return {"emotion": {}, "gate": {}, "memory": {}, "boundary": {}, "expression": {}, "timing": {}, "sessions": []}

    session_key = all_sessions[0]
    try:
        host = hosts[session_key]
        comp = host.kernel.computation
        return {
            "emotion": comp.engine.observe(),
            "gate": comp.gate.to_dict(),
            "memory": {"voids": int(comp.engine.observe().get("active_voids", 0)), "coherence": comp.engine._coherence},
            "boundary": comp.boundary.to_dict(),
            "expression": comp.expression.state(),
            "timing": comp.timing_stats(),
            "sessions": all_sessions,
            "life_simulation": getattr(plugin, "_life_simulator", None) and plugin._life_simulator.to_dict() or {},
        }
    except Exception:
        return {"emotion": {}, "gate": {}, "memory": {}, "boundary": {}, "expression": {}, "timing": {}, "sessions": all_sessions}


def _load_schema(plugin: Any) -> dict[str, Any]:
    """Load config schema."""
    import os
    schema_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_conf_schema.json")
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}
