"""Phase G 测试：二重奏跨会话同步度可视化（trace + 端点 payload + 渲染工具）。

架构 §6 可视化。核心验收：
- UserModelDomain 记录 synchrony 轨迹、跨会话持久化、向后兼容旧档。
- _twin_synchrony_payload：开关关→空（enabled=False 不崩）；开→轨迹 + 收敛 summary。
- 渲染工具：空轨迹→占位、有数据→3 条序列、畸形数据不崩、收敛判据正确。
"""

from __future__ import annotations

from types import SimpleNamespace

from sylanne_alpha.v2core.contracts import Phase
from sylanne_alpha.v2core.domains.user_model import UserModelDomain
from tools.twin_synchrony_viz import (
    _synthetic_trajectory,
    render_html,
    render_svg,
)


def _ctx(text: str, turns: int, warmth: float, now: float) -> SimpleNamespace:
    c = SimpleNamespace()
    c.phase = Phase.EVOLVE
    c.text = text
    c.body = SimpleNamespace(turns=turns, warmth=warmth, surprise=0.3)
    c.scratch = {"now": now}
    return c


def _train(um: UserModelDomain, n: int = 15) -> None:
    now = 0.0
    for i in range(n):
        um.ingest(_ctx("我好喜欢你呀❤️抱抱", i, 0.6, now))
        now += 10.0


# ---- 领域轨迹 ----

def test_trace_records_each_turn() -> None:
    um = UserModelDomain()
    _train(um, 15)
    traj = um.synchrony_trajectory()
    assert len(traj) == 15
    for p in traj:
        assert {"turn", "sync", "grip", "user_pe"} <= set(p)


def test_trace_is_readonly_copy() -> None:
    """synchrony_trajectory() 返回拷贝，外部改不动内部轨迹。"""
    um = UserModelDomain()
    _train(um, 5)
    traj = um.synchrony_trajectory()
    traj[0]["sync"] = 999.0
    assert um.synchrony_trajectory()[0]["sync"] != 999.0


def test_trace_persistence_roundtrip() -> None:
    um = UserModelDomain()
    _train(um, 12)
    snap = um.to_dict()
    um2 = UserModelDomain()
    um2.load_dict(snap)
    assert um2.synchrony_trajectory() == um.synchrony_trajectory()


def test_trace_backward_compat_old_archive() -> None:
    """旧档无 sync_trace 字段 → 空起步不崩（铁律④）。"""
    um = UserModelDomain()
    um.load_dict({"disposition": {"warmth": 0.5}})   # 老格式，无 sync_trace
    assert um.synchrony_trajectory() == []


def test_grip_rises_user_pe_falls() -> None:
    """她越来越懂你：稳定输入下 grip 升、user_pe 降（收敛信号）。"""
    um = UserModelDomain()
    _train(um, 20)
    traj = um.synchrony_trajectory()
    assert traj[-1]["grip"] > traj[0]["grip"]        # 把握度升
    assert traj[-1]["user_pe"] < traj[0]["user_pe"]  # 预测误差降


# ---- 端点 payload ----

def test_payload_disabled_when_no_runtimes() -> None:
    """v2core 开关关 / 无运行态 → enabled=False、空轨迹，不崩。"""
    from sylanne_alpha.webui_server import _twin_synchrony_payload
    pl = _twin_synchrony_payload(SimpleNamespace())
    assert pl["enabled"] is False and pl["points"] == []


def test_payload_enabled_with_runtime() -> None:
    from sylanne_alpha.webui_server import _twin_synchrony_payload
    um = UserModelDomain()
    _train(um, 12)
    plugin = SimpleNamespace(_v2core_runtimes={"sess:A": {"domains": {"usermodel": um}}})
    pl = _twin_synchrony_payload(plugin, session="sess:A")
    assert pl["enabled"] is True
    assert pl["session"] == "sess:A"
    assert len(pl["points"]) == 12
    assert "samples" in pl["summary"]


def test_payload_autopicks_first_session() -> None:
    from sylanne_alpha.webui_server import _twin_synchrony_payload
    um = UserModelDomain()
    _train(um, 3)
    plugin = SimpleNamespace(_v2core_runtimes={"sess:Z": {"domains": {"usermodel": um}}})
    pl = _twin_synchrony_payload(plugin)               # 不传 session
    assert pl["session"] == "sess:Z" and len(pl["points"]) == 3


def test_payload_tolerates_missing_usermodel() -> None:
    from sylanne_alpha.webui_server import _twin_synchrony_payload
    plugin = SimpleNamespace(_v2core_runtimes={"s": {"domains": {}}})
    pl = _twin_synchrony_payload(plugin, session="s")
    assert pl["points"] == []                          # 无 usermodel 域不崩


# ---- 渲染工具 ----

def test_render_empty_trajectory_placeholder() -> None:
    svg = render_svg([])
    assert svg.startswith("<svg") and "暂无" in svg


def test_render_three_series() -> None:
    svg = render_svg(_synthetic_trajectory(40), title="t")
    assert svg.count("<polyline") == 3                 # grip/sync/user_pe 三条线


def test_render_tolerates_malformed_points() -> None:
    render_svg([{"grip": "bad"}, {}, {"sync": None}])  # 不抛即通过


def test_render_html_convergence_verdict() -> None:
    pts = _synthetic_trajectory(40)
    html = render_html({"session": "x", "points": pts,
                        "summary": {"grip_gain": 0.6, "user_pe_drop": 0.5}})
    assert "二重奏收敛中" in html and "<svg" in html


def test_synthetic_trajectory_converges() -> None:
    """合成轨迹本身是一条收敛曲线（grip↑、user_pe↓、sync↑）。"""
    pts = _synthetic_trajectory(40)
    assert pts[-1]["grip"] > pts[0]["grip"]
    assert pts[-1]["user_pe"] < pts[0]["user_pe"]
    assert pts[-1]["sync"] > pts[0]["sync"]
