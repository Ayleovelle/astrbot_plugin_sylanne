"""Phase G fixlist P1-3 测试：IgnitionArbiter θ 标定（REVIEW §P1-3）。

防两个方向的退化：①修好 P0-2 后"永不装死"（话痨）；②冷启动被问就装死（ghost 复发）。
做 trait × drive 网格扫描，断言 speak/hold 分布合理：被问轮冷躯体必 speak（防 ghost），
积累了真实沉默自由能才 hold（赌气/退缩），未被问轮默认安静。
"""

from __future__ import annotations

from sylanne_alpha.v2core.capabilities.ignition import IgnitionArbiter, personality_saddle
from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Intent, Phase


def _decide(*, addressed: bool, drive: float, g_hold: float,
            personality: dict | None = None) -> str:
    """跑一次仲裁，返回 action。g_hold 经假 emotion 域注入。"""
    body = BodySnapshot(session_key="s", turns=1, expression_drive=drive,
                        personality=personality or {})
    ctx = BeatContext(session_key="s", event=None, body=body,
                      text=("在吗" if addressed else ""))
    ctx.phase = Phase.DELIBERATE

    class _Emo:
        def hold_free_energy(self, b) -> float:  # noqa: ANN001
            return g_hold
    ctx.domains["emotion"] = _Emo()
    intent = IgnitionArbiter().deliberate(ctx)
    return intent.payload["action"]


def test_addressed_cold_body_always_speaks() -> None:
    """被问 + 冷躯体（无积累沉默压力）→ 必 speak（防 ghost 复发，最关键判据）。"""
    for drive in (0.0, 0.1, 0.3, 0.5):
        assert _decide(addressed=True, drive=drive, g_hold=0.0) == "speak", \
            f"被问冷躯体 drive={drive} 装死了——ghost 复发！"


def test_addressed_with_real_hold_pressure_can_sulk() -> None:
    """被问 + 真实积累的高沉默自由能（赌气/退缩）→ 允许 hold（装死是人格的，不是 bug）。"""
    # g_hold 远超表达鞍距才赌气沉默
    assert _decide(addressed=True, drive=0.0, g_hold=5.0) == "hold"


def test_unaddressed_default_quiet() -> None:
    """未被问（idle/compose）+ 无积累 → 默认安静（不话痨）。"""
    assert _decide(addressed=False, drive=0.0, g_hold=0.0) == "hold"


def test_high_drive_always_speaks_both_modes() -> None:
    """表达驱力越过鞍点 → 无论被问与否都 speak（强制表达鞍点，人格显函数）。"""
    # express_at 中性≈0.95，给个超过的 drive
    assert _decide(addressed=True, drive=1.2, g_hold=10.0) == "speak"
    assert _decide(addressed=False, drive=1.2, g_hold=10.0) == "speak"


def test_grid_scan_not_degenerate() -> None:
    """trait×drive×addressed 网格扫描：speak/hold 都出现（既不永远装死也不永远话痨）。"""
    actions = set()
    for trait in (0.0, 0.5, 1.0):
        for drive in (0.0, 0.5, 1.0):
            for addressed in (True, False):
                for g_hold in (0.0, 2.0):
                    a = _decide(addressed=addressed, drive=drive, g_hold=g_hold,
                                personality={"curiosity": trait, "warmth_bias": trait,
                                             "sovereignty_guard": trait, "patience": trait})
                    actions.add(a)
    assert "speak" in actions, "网格里从不 speak（永远装死）"
    assert "hold" in actions, "网格里从不 hold（永远话痨）"


def test_saddle_neutral_anchor() -> None:
    """中性人格（trait=0.5）鞍点回到 SDK 默认锚点 0.95 / 0.10 / 0.15。"""
    body = BodySnapshot(session_key="s", turns=1,
                        personality={"curiosity": 0.5, "warmth_bias": 0.5,
                                     "sovereignty_guard": 0.5, "patience": 0.5})
    express_at, hold_below, hold_floor = personality_saddle(body)
    assert abs(express_at - 0.95) < 1e-6
    assert abs(hold_below - 0.10) < 1e-6
    assert abs(hold_floor - 0.15) < 1e-6
