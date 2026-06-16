"""Phase A 地基契约测试 —— canonical PE 单一来源 + 躯体标记投影 + fast-path 降级。

这是 2.1.0 认知架构的地基硬化：无论上层架构怎么设计，这些不变量必须成立。
- canonical PE（surprise/precision/mean_surprise）经 extras 注入，不在 surface dict 里重算。
- 躯体标记从真实 surface["body"].* 路径投影。
- extras 缺省（fast-path）→ 降级中性值，绝不崩。
- 铁律2：PE/躯体量不 clamp 上限（只防 None），漂移即研究信号。
"""

from __future__ import annotations

import tempfile

from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost
from sylanne_alpha.v2core.body_port import snapshot_from_surface
from sylanne_alpha.v2core.body_port_v2 import CanonicalKernelBodyPort
from sylanne_alpha.v2core.contracts import BodySnapshot


def test_canonical_pe_single_source_via_extras() -> None:
    """canonical PE 只从 extras 注入；surface 不含 surprise 时仍由 extras 决定。"""
    surface = {"session_key": "u1", "turns": 1, "body": {}, "host_payload": {}}
    snap = snapshot_from_surface(surface, "u1", extras={
        "surprise": 0.73, "precision": 0.61, "mean_surprise": 0.55,
    })
    assert snap.surprise == 0.73
    assert snap.precision == 0.61
    assert snap.mean_surprise == 0.55


def test_fast_path_extras_none_degrades_neutral() -> None:
    """extras 缺省（fast-path）→ 中性默认，不崩。"""
    snap = snapshot_from_surface({"session_key": "u", "turns": 0}, "u")
    assert isinstance(snap, BodySnapshot)
    assert snap.surprise == 0.0       # 中性
    assert snap.precision == 0.5
    assert snap.sovereignty == 1.0    # 主权缺省满


def test_somatic_markers_projected_from_body_path() -> None:
    """躯体标记从真实 surface["body"].* 路径投影。"""
    surface = {
        "session_key": "u", "turns": 2,
        "body": {
            "wound": {"scar": 0.42},
            "pulse": {"strain": 0.3},
            "immunity": {"sovereignty": 0.8},
            "mortality": {"exhaustion": 0.15},
            "nerve": {"threshold_drift": 0.05},
        },
        "host_payload": {"affect_dynamics": {"body_coupling": {"expression_drive": 0.9}}},
    }
    snap = snapshot_from_surface(surface, "u")
    assert snap.scar == 0.42
    assert snap.strain == 0.3
    assert snap.sovereignty == 0.8
    assert snap.exhaustion == 0.15
    assert snap.threshold_drift == 0.05
    assert snap.expression_drive == 0.9


def test_pe_not_clamped_above_one() -> None:
    """铁律2：PE/情感量不 clamp 上限（漂移即研究信号），只防 None。"""
    snap = snapshot_from_surface(
        {"session_key": "u", "turns": 0}, "u",
        extras={"surprise": 1.8, "precision": 2.3},  # 超 1 也原样透出，不被夹
    )
    assert snap.surprise == 1.8
    assert snap.precision == 2.3


def test_real_host_injects_canonical_pe() -> None:
    """真实 host：observe() 把 kernel.computation 的 surprise/precision 真实注入（实机验证）。"""
    h = SylanneAlphaHost(root=tempfile.mkdtemp(prefix="sylpa_"), session_key="cog")
    bp = CanonicalKernelBodyPort.from_host(h, "cog")
    bp.tick({"phase": "request", "text": "我好难过，你为什么不理我"})
    snap = bp.observe()
    assert snap.surprise > 0.0, "canonical surprise 未从真实 host 注入"
    assert 0.0 < snap.precision <= 1.0, "precision 异常"
