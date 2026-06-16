"""实机回归：BodySnapshot.warmth/tension/repair 必须跟随【真实躯体】(body.temperature 等)。

实机暴露的真 bug（2026-06-12，单测/离线 demo 都没抓到，只有真模型双 tick 才暴露）：
warmth 旧读 host_payload.affect_dynamics.computation_emotion.warmth（近零内部增量，实测 0.005），
害得 BodySnapshot.warmth≈0 → 整个 Appraisal/Emotion 层饿死、affect 永远进不了躯体。
修：优先读 body.temperature.warmth（真实躯体温度），映射成 [-1,1] 效价。本测钉死不回归。
"""

from __future__ import annotations

from sylanne_alpha.v2core.body_port import snapshot_from_surface


def _surface(warmth01: float, strain: float = 0.0, need_repair: float = 0.0) -> dict:
    """构造一个带真实 body.temperature 的 surface（仿 host.diagnostics()）。"""
    return {
        "session_key": "s", "turns": 1,
        "body": {
            "temperature": {"warmth": warmth01, "volatility": 0.0, "repair_heat": 0.0},
            "pulse": {"strain": strain},
            "immunity": {"sovereignty": 1.0, "boundary_pressure": 0.0},
            "needs": {"need_repair": need_repair},
            "wound": {"scar": 0.0, "repair": 0.0},
            "nerve": {"threshold_drift": 0.0},
            "mortality": {"exhaustion": 0.0},
        },
        "host_payload": {},  # 旧路径全空：证明新路径独立生效
    }


def test_warmth_tracks_real_body_temperature() -> None:
    """body.temperature.warmth=0.9（暖）→ BodySnapshot.warmth≈+0.8 效价（不再被 0.005 饿死）。"""
    snap = snapshot_from_surface(_surface(0.9), "s")
    assert snap.warmth > 0.5, f"暖躯体却映射成 {snap.warmth}（warmth 死链复发）"


def test_warmth_neutral_and_cold() -> None:
    """0.5→中性≈0；0.1→冷≈−0.8。映射 (raw−0.5)*2 正确。"""
    assert abs(snapshot_from_surface(_surface(0.5), "s").warmth) < 0.05
    assert snapshot_from_surface(_surface(0.1), "s").warmth < -0.5


def test_warmth_not_starved_when_host_payload_empty() -> None:
    """host_payload 全空（旧路径无数据）时，warmth 仍从 body.temperature 拿到真值。"""
    snap = snapshot_from_surface(_surface(0.8), "s")
    assert snap.warmth > 0.3, "host_payload 空就饿死 = 旧 bug"


def test_tension_repair_from_real_body() -> None:
    """tension 读 pulse.strain；repair 读 needs.need_repair（body 真实路径优先）。"""
    snap = snapshot_from_surface(_surface(0.5, strain=0.7, need_repair=0.6), "s")
    assert snap.tension >= 0.6
    assert snap.repair_pressure >= 0.5
