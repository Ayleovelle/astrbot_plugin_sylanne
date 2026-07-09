"""Wave 3a：body_port_v2 把 4 个缺陷行为信号投影进 BodySnapshot。

void_pressure / load / plasticity / boundary_pressure 此前 SDK 在算却没投影进 BodySnapshot，
fragment 读不到 → Wave 3 行为触发不了。本文件钉死投影正确 + 缺失降级（中性默认），SDK 不动。
"""

from __future__ import annotations

from sylanne_alpha.v2core.body_port_v2 import snapshot_from_surface


def test_wave3_fields_projected_from_surface() -> None:
    """surface.body 路径 + extras 注入 → 4 字段如实投影。"""
    surface = {
        "session_key": "u",
        "turns": 1,
        "body": {
            "mortality": {"load": 0.7, "exhaustion": 0.1},
            "nerve": {"plasticity": 0.2, "threshold_drift": 0.0},
            "immunity": {"boundary_pressure": 0.6, "sovereignty": 1.0},
        },
        "host_payload": {},
    }
    snap = snapshot_from_surface(surface, "u", extras={"void_pressure": 0.8})
    assert snap.load == 0.7
    assert snap.plasticity == 0.2
    assert snap.boundary_pressure == 0.6
    assert snap.void_pressure == 0.8


def test_wave3_fields_default_when_absent() -> None:
    """缺字段 → 中性降级：load/boundary/void=0，plasticity=0.5（中性）。"""
    snap = snapshot_from_surface(
        {"session_key": "u", "turns": 0, "body": {}, "host_payload": {}}, "u"
    )
    assert snap.load == 0.0
    assert snap.plasticity == 0.5
    assert snap.boundary_pressure == 0.0
    assert snap.void_pressure == 0.0


def test_void_pressure_only_from_extras_not_surface() -> None:
    """void_pressure 只走 extras（canonical 单一来源），不在 surface.body 里瞎找。"""
    surface = {"session_key": "u", "turns": 1,
               "body": {"void": {"pressure": 9.9}}, "host_payload": {}}
    snap = snapshot_from_surface(surface, "u", extras=None)
    assert snap.void_pressure == 0.0  # extras 缺省 → 中性，不从 body 误读


def test_boundary_pressure_separate_from_tension() -> None:
    """boundary_pressure 既喂 tension（取 max）又单独可读——吃醋触发要的是它本身。"""
    surface = {
        "session_key": "u", "turns": 1,
        "body": {"immunity": {"boundary_pressure": 0.5}, "pulse": {"strain": 0.2}},
        "host_payload": {},
    }
    snap = snapshot_from_surface(surface, "u")
    assert snap.boundary_pressure == 0.5
    assert snap.tension == 0.5  # max(strain 0.2, boundary 0.5)
