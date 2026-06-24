"""Phase 4：WebUI 生活观测面板 API 契约测试。

覆盖：
- /api/life/events     GET — events 列表 + Phase 3 字段（含 project_id / origin_session）
- /api/life/projects   GET — projects + skills
- /api/life/audit      GET — outreach_audit
- /api/life/diagnostics GET — to_dict() + prompt_fragment
- /api/life/controls   POST — toggle_enabled / set_share_intensity / clear_* / unknown action

策略：
- WebUIRoutes 直接以 SimpleNamespace 注入 plugin._life_simulator + plugin._config，
  绕开真实 LLM / async runtime，专注 schema 与降级行为。
- aiohttp 端的相同闭包行为通过 WebUIRoutes 镜像测试覆盖（两套实现共享 plugin._life_simulator
  这一相同抽象），降低双倍 fixture 成本但仍保证 contract 一致。
"""

from __future__ import annotations

import asyncio
import time
import types

import pytest

from sylanne_alpha.life_simulation import (
    LifeEvent,
    LifeProject,
    LifeSimulationState,
    LifeWorldState,
)
from sylanne_alpha.webui_routes import WebUIRoutes


# ---------------------------------------------------------------------------
# 工具 fixture
# ---------------------------------------------------------------------------


def _make_plugin(life_sim=None, config=None):
    """构造极小 plugin 替身。

    plugin._life_simulator 可为 None（降级路径）。
    plugin._config / plugin.config 均提供，模拟 AstrBot 配置双写。
    """
    p = types.SimpleNamespace()
    p._life_simulator = life_sim
    p._config = dict(config or {})
    p.config = dict(p._config)
    return p


def _stub_life_sim(events=None, projects=None, skills=None, audit=None, enabled=True):
    """构造一个 LifeSimulator 替身（仅暴露 state + life_prompt_fragment）。"""
    state = LifeSimulationState(
        events=list(events or []),
        world=LifeWorldState(phase="evening", energy=0.6, focus=0.4, last_tick_at=time.time()),
        projects=list(projects or []),
    )
    if skills is not None:
        state.skills = list(skills)
    if audit is not None:
        state.outreach_audit = dict(audit)
    sim = types.SimpleNamespace()
    sim.state = state
    sim.enabled = enabled
    sim.life_prompt_fragment = lambda limit=5, max_budget=2000: "PROMPT_FRAGMENT_PREVIEW"
    return sim


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture
def loop():
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    yield loop


# ---------------------------------------------------------------------------
# /api/life/events
# ---------------------------------------------------------------------------


def test_life_events_unavailable_when_sim_missing(loop):
    routes = WebUIRoutes(_make_plugin(life_sim=None))
    resp = loop.run_until_complete(routes.life_events_handler())
    assert resp == {"events": [], "available": False}


def test_life_events_returns_recent_events(loop):
    ev = LifeEvent(
        text="reading at the lakeside",
        mood="content",
        urgency=0.2,
        timestamp=time.time(),
        event_type="reading",
        source="life_simulation",
        importance=0.7,
        project_id="proj-abc-123",
        origin_session="session_main",
        wants_to_share=True,
        shared=False,
    )
    sim = _stub_life_sim(events=[ev])
    routes = WebUIRoutes(_make_plugin(life_sim=sim))
    resp = loop.run_until_complete(routes.life_events_handler())
    assert resp["available"] is True
    assert len(resp["events"]) == 1
    item = resp["events"][0]
    assert item["text"] == "reading at the lakeside"
    assert item["project_id"] == "proj-abc-123"
    assert item["origin_session"] == "session_main"
    assert item["wants_to_share"] is True
    assert item["shared"] is False
    assert 0.0 <= item["importance"] <= 1.0


# ---------------------------------------------------------------------------
# /api/life/projects
# ---------------------------------------------------------------------------


def test_life_projects_unavailable_when_sim_missing(loop):
    routes = WebUIRoutes(_make_plugin(life_sim=None))
    resp = loop.run_until_complete(routes.life_projects_handler())
    assert resp == {"projects": [], "skills": [], "available": False}


def test_life_projects_returns_projects_and_skills(loop):
    proj = LifeProject(title="thesis chapter draft", kind="creating", state="active", progress=0.4)
    sim = _stub_life_sim(projects=[proj])
    routes = WebUIRoutes(_make_plugin(life_sim=sim))
    resp = loop.run_until_complete(routes.life_projects_handler())
    assert resp["available"] is True
    assert len(resp["projects"]) == 1
    assert resp["projects"][0]["title"] == "thesis chapter draft"
    # 种子技能默认三条
    assert len(resp["skills"]) >= 3
    names = {s["name"] for s in resp["skills"]}
    assert "evening_soft_checkin" in names


# ---------------------------------------------------------------------------
# /api/life/audit
# ---------------------------------------------------------------------------


def test_life_audit_unavailable_when_sim_missing(loop):
    routes = WebUIRoutes(_make_plugin(life_sim=None))
    resp = loop.run_until_complete(routes.life_audit_handler())
    assert resp == {"audit": {}, "available": False}


def test_life_audit_returns_outreach_log(loop):
    audit = {
        "session_main": [
            {"timestamp": 100.0, "status": "dispatched", "reason": "share_intent_high"},
            {"timestamp": 200.0, "status": "gated", "reason": "cooldown"},
        ],
        "_global": [{"timestamp": 50.0, "status": "skipped", "reason": "no_origin_session"}],
    }
    sim = _stub_life_sim(audit=audit)
    routes = WebUIRoutes(_make_plugin(life_sim=sim))
    resp = loop.run_until_complete(routes.life_audit_handler())
    assert resp["available"] is True
    assert "session_main" in resp["audit"]
    assert len(resp["audit"]["session_main"]) == 2
    assert resp["audit"]["_global"][0]["status"] == "skipped"


# ---------------------------------------------------------------------------
# /api/life/diagnostics
# ---------------------------------------------------------------------------


def test_life_diagnostics_unavailable_when_sim_missing(loop):
    routes = WebUIRoutes(_make_plugin(life_sim=None))
    resp = loop.run_until_complete(routes.life_diagnostics_handler())
    assert resp == {"available": False}


def test_life_diagnostics_includes_full_state_and_prompt(loop):
    sim = _stub_life_sim()
    routes = WebUIRoutes(_make_plugin(life_sim=sim))
    resp = loop.run_until_complete(routes.life_diagnostics_handler())
    assert resp["available"] is True
    # to_dict 关键字段
    assert "events" in resp
    assert "world" in resp
    assert "projects" in resp
    assert "skills" in resp
    assert "outreach_audit" in resp
    assert resp["prompt_fragment"] == "PROMPT_FRAGMENT_PREVIEW"


# ---------------------------------------------------------------------------
# /api/life/controls
# ---------------------------------------------------------------------------


class _FakeQuartRequest:
    """轻量化 quart.request 替身，按 body 直接返回。"""

    def __init__(self, body):
        self._body = body

    async def get_json(self, silent: bool = True):
        return self._body


def _patch_quart_request(monkeypatch, body):
    fake = _FakeQuartRequest(body)
    # 直接给 quart.request 打补丁；webui_routes.life_controls_handler 内 import 局部
    import quart  # noqa: WPS433  (运行时 import 与目标模块一致)

    monkeypatch.setattr(quart, "request", fake, raising=False)
    return fake


def test_life_controls_unavailable_when_sim_missing(loop, monkeypatch):
    _patch_quart_request(monkeypatch, {"action": "toggle_enabled", "value": True})
    routes = WebUIRoutes(_make_plugin(life_sim=None))
    resp = loop.run_until_complete(routes.life_controls_handler())
    assert resp == {"error": "life sim not available"}


def test_life_controls_toggle_enabled_persists_config(loop, monkeypatch):
    sim = _stub_life_sim()
    plugin = _make_plugin(life_sim=sim, config={"sylanne_alpha_life_simulation_enabled": False})
    routes = WebUIRoutes(plugin)
    _patch_quart_request(monkeypatch, {"action": "toggle_enabled", "value": True})
    resp = loop.run_until_complete(routes.life_controls_handler())
    assert resp == {"ok": True, "enabled": True}
    assert plugin._config["sylanne_alpha_life_simulation_enabled"] is True


def test_life_controls_set_share_intensity_validates(loop, monkeypatch):
    sim = _stub_life_sim()
    plugin = _make_plugin(life_sim=sim)
    routes = WebUIRoutes(plugin)
    # 有效值
    _patch_quart_request(monkeypatch, {"action": "set_share_intensity", "value": "high"})
    resp = loop.run_until_complete(routes.life_controls_handler())
    assert resp == {"ok": True, "share_intensity": "high"}
    assert plugin._config["sylanne_alpha_life_simulation_share_intensity"] == "high"
    # 非法值
    _patch_quart_request(monkeypatch, {"action": "set_share_intensity", "value": "extreme"})
    resp = loop.run_until_complete(routes.life_controls_handler())
    assert resp == {"error": "invalid intensity"}


def test_life_controls_clear_actions(loop, monkeypatch):
    ev = LifeEvent(
        text="some event",
        mood="neutral",
        urgency=0.1,
        timestamp=time.time(),
        event_type="resting",
    )
    proj = LifeProject(title="p1", kind="resting")
    sim = _stub_life_sim(events=[ev], projects=[proj])
    sim.state.plan = types.SimpleNamespace(arc="rest")
    plugin = _make_plugin(life_sim=sim)
    routes = WebUIRoutes(plugin)

    _patch_quart_request(monkeypatch, {"action": "clear_journal"})
    resp = loop.run_until_complete(routes.life_controls_handler())
    assert resp == {"ok": True, "cleared": "events"}
    assert sim.state.events == []

    _patch_quart_request(monkeypatch, {"action": "clear_projects"})
    resp = loop.run_until_complete(routes.life_controls_handler())
    assert resp == {"ok": True, "cleared": "projects"}
    assert sim.state.projects == []

    _patch_quart_request(monkeypatch, {"action": "clear_plan"})
    resp = loop.run_until_complete(routes.life_controls_handler())
    assert resp == {"ok": True, "cleared": "plan"}
    assert sim.state.plan is None


def test_life_controls_unknown_action(loop, monkeypatch):
    sim = _stub_life_sim()
    routes = WebUIRoutes(_make_plugin(life_sim=sim))
    _patch_quart_request(monkeypatch, {"action": "nope_not_a_real_action"})
    resp = loop.run_until_complete(routes.life_controls_handler())
    assert resp == {"error": "unknown action: nope_not_a_real_action"}


# ---------------------------------------------------------------------------
# 路由注册：main.py / webui_server.py 路径常量与名字一致性 smoke
# ---------------------------------------------------------------------------


def test_life_routes_registered_in_main():
    """main._register_web_apis 必须包含 5 个生活观测路径，且 handler 名与 WebUIRoutes 对齐。"""
    import inspect

    import main as _main

    plugin_cls = _main.EmotionalStatePlugin
    src = inspect.getsource(plugin_cls._register_web_apis)
    for handler_name in (
        "life_status_handler",
        "life_events_handler",
        "life_projects_handler",
        "life_audit_handler",
        "life_diagnostics_handler",
        "life_controls_handler",
    ):
        assert handler_name in src, f"missing route handler reference: {handler_name}"
        assert hasattr(WebUIRoutes, handler_name), f"WebUIRoutes lacks {handler_name}"


def test_life_routes_registered_in_webui_server():
    """webui_server.start_webui_server 内必须 router.add_get/post 注册 5 个生活路径。"""
    import inspect

    from sylanne_alpha import webui_server as srv

    src = inspect.getsource(srv.start_webui_server)
    for path in (
        "/api/life/events",
        "/api/life/projects",
        "/api/life/audit",
        "/api/life/diagnostics",
        "/api/life/controls",
    ):
        assert path in src, f"webui_server.py missing route registration: {path}"


# ---------------------------------------------------------------------------
# 配置 schema 新增三键 smoke
# ---------------------------------------------------------------------------


def test_phase4_config_keys_present():
    import json
    from pathlib import Path

    schema = json.loads(Path("_conf_schema.json").read_text(encoding="utf-8"))
    for key in (
        "sylanne_alpha_life_simulation_share_intensity",
        "sylanne_alpha_life_simulation_night_consolidation",
        "sylanne_alpha_life_simulation_allow_memory_write",
    ):
        assert key in schema, f"missing config key: {key}"
    intensity = schema["sylanne_alpha_life_simulation_share_intensity"]
    assert intensity.get("default") == "standard"
    assert set(intensity.get("options", [])) == {"off", "low", "standard", "high"}
