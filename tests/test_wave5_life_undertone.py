"""Wave 5：生活模拟双向（life → 表达底色 + 躯体 mood → 活动选择）。

钉死两件事：
- LifeSimulator.undertone_cue()：从主导项目派生 stalled/resolved 内心底色（不暴露标题/活动/数字）；
- fragment._life_line + build_mind_fragment：scratch["life_cue"] 渲染成一句脱钩话题的内心天气，
  平淡日不占预算、坏日子靠强度爬上来；
- _build_prompt 的 mood-coherence 分支：坏躯体态 → "倾向室内、低能量活动"。
"""

from __future__ import annotations

from sylanne_alpha.life_simulation import (
    LifeSimulator, LifeProject, LifeEvent, LifePrivacy,
    _LIFE_STALE_S, _LIFE_STALE_HI_S, _LIFE_RESOLVED_WINDOW_S,
)
from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase
from sylanne_alpha.v2core.fragment import build_mind_fragment, _life_line

_NOW = 1_000_000.0
_DAY = 86400.0


def _sim() -> LifeSimulator:
    return LifeSimulator(config={"sylanne_alpha_life_simulation_enabled": True})


def _ctx(scratch: dict | None = None) -> BeatContext:
    c = BeatContext(session_key="u", event=None, body=BodySnapshot(session_key="u", turns=1),
                    text="测试", phase=Phase.PERCEPT, domains={})
    if scratch:
        c.scratch.update(scratch)
    return c


# ---- undertone_cue（派生层）-------------------------------------------------

def test_undertone_stalled_scales_with_staleness() -> None:
    """active 项目久未触碰 → stalled；强度随停滞深度线性爬（中点≈0.5）。"""
    sim = _sim()
    # 停滞 3.5 天：(3.5-2)/(5-2)=0.5
    sim.state.projects = [LifeProject(title="论文", state="active", last_touched_at=_NOW - 3.5 * _DAY)]
    cue = sim.undertone_cue(now=_NOW)
    assert cue and cue["kind"] == "stalled"
    assert abs(cue["intensity"] - 0.5) < 0.05, cue


def test_undertone_neutral_when_fresh() -> None:
    """刚碰过的 active 项目不算停滞 → 无底色。"""
    sim = _sim()
    sim.state.projects = [LifeProject(title="论文", state="active", last_touched_at=_NOW - 0.5 * _DAY)]
    assert sim.undertone_cue(now=_NOW) is None


def test_undertone_resolved_within_window_decays() -> None:
    """近窗口内 finished → resolved；强度随时距衰减（1 天 / 2 天窗 ≈ 0.5）。"""
    sim = _sim()
    sim.state.projects = [LifeProject(title="论文", state="finished", last_touched_at=_NOW - 1.0 * _DAY)]
    cue = sim.undertone_cue(now=_NOW)
    assert cue and cue["kind"] == "resolved"
    assert abs(cue["intensity"] - 0.5) < 0.05, cue
    # 窗口外的 finished 不再触发
    sim.state.projects = [LifeProject(title="论文", state="finished",
                                      last_touched_at=_NOW - 3 * _DAY)]
    assert sim.undertone_cue(now=_NOW) is None


def test_undertone_stalled_wins_over_resolved() -> None:
    """蔫盖过轻快：同时有 stalled 与 resolved 时，底色取 stalled。"""
    sim = _sim()
    sim.state.projects = [
        LifeProject(title="A", state="finished", last_touched_at=_NOW - 0.5 * _DAY),
        LifeProject(title="B", state="active", last_touched_at=_NOW - 4 * _DAY),
    ]
    cue = sim.undertone_cue(now=_NOW)
    assert cue and cue["kind"] == "stalled"


def test_undertone_skips_project_with_bad_timestamp() -> None:
    """单个项目 last_touched_at 是脏数据（非数值字符串）→ 只跳它，不掀翻整条 cue。

    回归：修复前 float("garbage") 抛 ValueError 逃出 undertone_cue（loop 在 try 外），
    整条 cue 连同好项目一起丢；修复后坏项目被跳过，好的 stalled 项目照常出底色。
    """
    sim = _sim()
    sim.state.projects = [
        LifeProject(title="坏", state="active", last_touched_at="garbage"),
        LifeProject(title="好", state="active", last_touched_at=_NOW - 4 * _DAY),
    ]
    cue = sim.undertone_cue(now=_NOW)
    assert cue and cue["kind"] == "stalled", cue


def test_undertone_mood_skips_user_fact() -> None:
    """mood 取最近【非 USER_FACT】事件的词（隐私：不读用户事实/正文）。"""
    sim = _sim()
    sim.state.projects = [LifeProject(title="论文", state="active", last_touched_at=_NOW - 4 * _DAY)]
    sim.state.events = [
        LifeEvent(text="她读书", mood="闷", urgency=0.1, timestamp=_NOW - 100,
                  privacy_level=LifePrivacy.SHAREABLE),
        LifeEvent(text="用户说的事实", mood="ignored", urgency=0.1, timestamp=_NOW,
                  privacy_level=LifePrivacy.USER_FACT),
    ]
    cue = sim.undertone_cue(now=_NOW)
    assert cue and cue["mood"] == "闷", cue


# ---- _life_line（渲染层）----------------------------------------------------

def test_life_line_renders_stalled_with_mood() -> None:
    text, intensity = _life_line(_ctx({"life_cue": {"kind": "stalled", "intensity": 0.7, "mood": "闷"}}))
    assert "心里压着件没推动的事" in text and "（闷）" in text
    assert abs(intensity - 0.7) < 1e-6
    # 不暴露项目名/活动/数字
    assert "论文" not in text and "%" not in text


def test_life_line_renders_resolved() -> None:
    text, _ = _life_line(_ctx({"life_cue": {"kind": "resolved", "intensity": 0.4, "mood": ""}}))
    assert "总算松了口气，轻快些" in text


def test_life_line_silent_without_cue() -> None:
    assert _life_line(_ctx()) == ("", 0.0)
    assert _life_line(_ctx({"life_cue": "garbage"})) == ("", 0.0)
    assert _life_line(_ctx({"life_cue": {"kind": "??"}})) == ("", 0.0)


def test_life_line_reaches_fragment_end_to_end() -> None:
    """生活底色真进 system_prompt 片段（端到端，不只是函数）。"""
    frag = build_mind_fragment(_ctx({"life_cue": {"kind": "stalled", "intensity": 0.8, "mood": "闷"}}), {})
    assert "心里压着件没推动的事" in frag


# ---- 方向二：mood → 活动选择（rhythm body 分支）----------------------------

def test_bad_body_biases_toward_staying_in() -> None:
    """坏躯体态（tension 高）→ _build_prompt 追"倾向室内、低能量活动"。"""
    sim = _sim()
    sim._emotion_getter = lambda: {"tension": 0.9, "warmth": 0.0}
    prompt = sim._build_prompt(_NOW)
    assert "倾向待在室内" in prompt


def test_good_body_no_stay_in_hint() -> None:
    """中性躯体态 → 不追室内提示。"""
    sim = _sim()
    sim._emotion_getter = lambda: {"tension": 0.1, "warmth": 0.2}
    prompt = sim._build_prompt(_NOW)
    assert "倾向待在室内" not in prompt


def test_high_void_pressure_alone_does_not_trigger_indoor() -> None:
    """void_pressure 是无上界求和（observe() 里阈值 >1.0/>5.0），且语义=表达积压非疲惫。

    回归：修复前分支含 `void_pressure > 0.6`，void_pressure=9.0 会误触发室内提示，
    打穿“坏日子才室内”的意图；修复后只认 tension/warmth，单高 void_pressure 不触发。
    """
    sim = _sim()
    sim._emotion_getter = lambda: {"tension": 0.0, "warmth": 0.0, "void_pressure": 9.0}
    prompt = sim._build_prompt(_NOW)
    assert "倾向待在室内" not in prompt


def test_negative_warmth_triggers_indoor() -> None:
    """warmth 转负（< -0.1）= 状态低落 → 追室内提示（锁住 warmth 这条臂）。"""
    sim = _sim()
    sim._emotion_getter = lambda: {"tension": 0.0, "warmth": -0.3}
    prompt = sim._build_prompt(_NOW)
    assert "倾向待在室内" in prompt
