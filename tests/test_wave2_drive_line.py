"""Wave 2：6 个死字段路由到表达（_drive_line）。

审计（roadmap part1）：expression_drive / intimacy_gravity / surprise / mean_surprise /
threshold_drift / precision 每轮都算、却零路径进 prompt。本文件钉死它们各自在明显偏离
中性时占一个线索位、按强度封顶 3 条、中性 body 不误触发。
"""

from __future__ import annotations

import pytest

from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase
from sylanne_alpha.v2core.fragment import build_mind_fragment, _drive_line, _norm


def _ctx(body: BodySnapshot) -> BeatContext:
    return BeatContext(session_key="u", event=None, body=body, text="测试",
                       phase=Phase.PERCEPT, domains={})


def _body(**kw) -> BodySnapshot:
    return BodySnapshot(session_key="u", turns=1, **kw)


def test_neutral_body_emits_no_drive_line() -> None:
    """6 字段全在中性默认 → 不出驱力行（不无中生有）。"""
    text, intensity = _drive_line(_ctx(_body()))
    assert text == "" and intensity == 0.0
    frag = build_mind_fragment(_ctx(_body()), {})
    assert "此刻我:" not in frag


def test_surprise_high_surfaces() -> None:
    """surprise 相对均值骤升 → '有点意外'（她会'等等你说什么'而非平滑吸收）。"""
    text, _ = _drive_line(_ctx(_body(surprise=0.6, mean_surprise=0.4)))
    assert "有点意外" in text


def test_mean_surprise_low_surfaces_familiarity() -> None:
    """mean_surprise 长期低位 → '已经很熟，不太用解释'（她停止过度解释）。"""
    text, _ = _drive_line(_ctx(_body(surprise=0.0, mean_surprise=0.25)))
    assert "已经很熟" in text


def test_precision_low_surfaces_uncertainty() -> None:
    """precision 低 → '拿不太准你的意思'（问清而非臆断）。"""
    text, _ = _drive_line(_ctx(_body(precision=0.2)))
    assert "拿不太准" in text


def test_threshold_drift_high_surfaces_informality() -> None:
    """threshold_drift 高 → '越来越随便'（降正式度）。"""
    text, _ = _drive_line(_ctx(_body(threshold_drift=0.4)))
    assert "越来越随便" in text


def test_intimacy_high_surfaces_closeness() -> None:
    """intimacy_gravity 高（≥0.66，对齐 renderer 近档）→ '想再靠近一点'。"""
    text, _ = _drive_line(_ctx(_body(intimacy_gravity=0.8)))
    assert "想再靠近" in text


def test_expression_drive_high_surfaces_urge() -> None:
    """expression_drive 越过人格 speak 阈（neutral≈0.95）→ '心里有话想说'。"""
    text, _ = _drive_line(_ctx(_body(expression_drive=1.2)))
    assert "心里有话想说" in text


def test_drive_line_capped_at_three_bits() -> None:
    """全字段同时拉满 → 只保留归一强度最高的 3 条（roadmap 兜底：防刷屏）。"""
    body = _body(expression_drive=1.5, surprise=0.9, mean_surprise=0.3,
                 precision=0.1, threshold_drift=0.9, intimacy_gravity=0.9)
    text, _ = _drive_line(_ctx(body))
    bits = text.replace("此刻我:", "").split("、")
    assert len(bits) == 3, f"驱力线索该封顶 3 条，实际 {len(bits)}：{text}"
    # 归一后强度最高三条：drift(0.875) / intimacy(0.75) / precision(0.6875)
    assert "越来越随便" in text and "想再靠近" in text and "拿不太准" in text
    # 较弱两条被挤掉（归一后 expression 0.55 / surprise 0.545）
    assert "心里有话想说" not in text and "有点意外" not in text


def test_surprise_survives_cap_against_marginal_ambient() -> None:
    """归一秤修复：一个真触发的 surprise 不再被带固定加项的勉强环境位挤掉（finding high）。

    surprise(delta 0.15) 与 precision/threshold_drift 都只勉强过阈——旧的 +0.2 地板会让环境位
    系统性盖过 surprise；归一后各按"越阈程度"公平比，surprise 稳留。
    """
    body = _body(surprise=0.45, mean_surprise=0.30, precision=0.31, threshold_drift=0.21)
    text, headline = _drive_line(_ctx(body))
    bits = text.replace("此刻我:", "").split("、")
    assert len(bits) <= 3
    assert "有点意外" in text, "真触发的 surprise 反被勉强环境位挤掉了（归一秤失效）"


def test_familiarity_no_spam_at_settled_baseline() -> None:
    """稳态熟络（surprise≈mean≈0.29）不再每轮刷'已经很熟'——transient gate 防稳态刷屏（finding）。"""
    text, _ = _drive_line(_ctx(_body(surprise=0.29, mean_surprise=0.29)))
    assert "已经很熟" not in text


def test_intimacy_inert_at_baseline() -> None:
    """intimacy 在该 trait 的自然基线(~0.52)不触发——门 0.6 高于天花板，中性人格不冒'想靠近'。"""
    text, _ = _drive_line(_ctx(_body(intimacy_gravity=0.52)))
    assert "想再靠近" not in text


def test_drive_line_reaches_fragment() -> None:
    """驱力行真进 system_prompt 片段（端到端，不只是函数）。"""
    frag = build_mind_fragment(_ctx(_body(surprise=0.7, mean_surprise=0.4)), {})
    assert "此刻我:" in frag and "有点意外" in frag


def test_familiarity_fires_at_extreme_low_baseline() -> None:
    """gemini review：mean_surprise 极低(<0.05)且本轮完美预测(surprise=0) → '已经很熟'仍触发。

    旧式 `surprise <= mean_s - 0.05` 在 mean_s<0.05 时阈值为负、surprise 非负恒不成立 →
    最熟络的极端反成死区。`max(0.0, mean_s-0.05)` 掐下限修复。移除该修复时本测试 FAIL。
    """
    text, _ = _drive_line(_ctx(_body(surprise=0.0, mean_surprise=0.02)))
    assert "已经很熟" in text, "极低基线+完美预测下熟络线索被死区吞掉了"


# --------------------------------------------------------------------------
# _norm 焦点单测（sourcery review）：cap-3 排序的公平秤，独立钉死其边界/clip 行为，
# 不再只靠 drive-line 间接覆盖。期望值经独立手推 + 实跑双核对。
# --------------------------------------------------------------------------

def test_norm_below_false_interior_and_clamps() -> None:
    """below=False：线性映射 [thr,hi]→[0,1]，value=thr→0、value=hi→1、越界 clamp。"""
    assert _norm(0.0, 0.0, 1.0) == pytest.approx(0.0)    # value=thr → 0
    assert _norm(1.0, 0.0, 1.0) == pytest.approx(1.0)    # value=hi → 1
    assert _norm(0.5, 0.0, 1.0) == pytest.approx(0.5)    # 中点
    assert _norm(2.0, 0.0, 1.0) == pytest.approx(1.0)    # 上 clamp（越过 hi）
    assert _norm(-1.0, 0.0, 1.0) == pytest.approx(0.0)   # 下 clamp（低于 thr）


def test_norm_span_guard_returns_zero() -> None:
    """span≤0（防除零）→ 直接退 0.0，不做除法。覆盖 below 两种模式。"""
    assert _norm(0.5, 1.0, 1.0) == 0.0                   # below=False, span=hi-thr=0
    assert _norm(0.5, 1.0, 0.5) == 0.0                   # below=False, span<0
    assert _norm(0.16, 0.0, 0.32, below=True) == 0.0     # below=True, span=thr-hi=-0.32<0


def test_norm_below_true_interior_and_clamps() -> None:
    """below=True（越低越强）：value=thr→0、value=hi→1、越界 clamp。"""
    assert _norm(0.32, 0.32, 0.0, below=True) == pytest.approx(0.0)   # value=thr → 0
    assert _norm(0.0, 0.32, 0.0, below=True) == pytest.approx(1.0)    # value=hi → 1
    assert _norm(0.16, 0.32, 0.0, below=True) == pytest.approx(0.5)   # 中点
    assert _norm(0.5, 0.32, 0.0, below=True) == pytest.approx(0.0)    # 下 clamp（value>thr）
    assert _norm(-0.1, 0.32, 0.0, below=True) == pytest.approx(1.0)   # 上 clamp（value<hi）
