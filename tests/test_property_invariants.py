"""v2core 核心不变量的性质测试（Hypothesis 随机轰炸，2026-06-13 全量评审落地）。

为什么要有这个文件：仓库 447 条测试几乎全是例子测试（特定输入→特定输出）。
v2core 的纪律大量是【全输入域不变量】——"防御式边界收敛到适配器""权重有界"
"固化只增""total function 永不抛"——例子测不完输入域，性质测试可以。

纪律：
- 只测【项目契约内的输入域】：有限 float（可越界，clamp 是被测物的职责），
  不喂 NaN/Inf——SDK 数值链不产它们，防 NaN 不是任何铁律，测了只产生假阳性。
- 每条性质对应一条明文纪律（注释标注出处），不测臆造的性质。
- 测试依赖 hypothesis 不进 requirements.txt（那是 AstrBot 宿主给用户装的
  运行时依赖）；本地/CI `pip install hypothesis`，未装则整文件跳过。
"""

from __future__ import annotations

import math

import pytest

hypothesis = pytest.importorskip("hypothesis")

from hypothesis import given, settings, strategies as st  # noqa: E402

from sylanne_alpha.v2core.body_port import snapshot_from_surface  # noqa: E402
from sylanne_alpha.v2core.capabilities.expression import compose_style  # noqa: E402
from sylanne_alpha.v2core.capabilities.ignition import personality_saddle  # noqa: E402
from sylanne_alpha.v2core.capabilities.somatic import guard_soften_from_body  # noqa: E402
from sylanne_alpha.v2core.contracts import (  # noqa: E402
    BeatContext,
    BodySnapshot,
    Intent,
    Phase,
    Reply,
    ReplyKind,
)
from sylanne_alpha.v2core.domains.distillation import DistillationDomain  # noqa: E402
from sylanne_alpha.v2core.domains.emotion import EmotionLedger  # noqa: E402
from sylanne_alpha.v2core.domains.narrative_self import NarrativeSelfDomain  # noqa: E402
from sylanne_alpha.v2core.domains.user_model import UserModelDomain  # noqa: E402
from sylanne_alpha.v2core.lexicon import N_DISTILL_FEATURES, distill_features, read_signals  # noqa: E402
from sylanne_alpha.v2core.renderer import DefaultRenderer  # noqa: E402
from sylanne_alpha.v2core.verbal import LEVELS7, level7, level_index  # noqa: E402

# 全局：Windows 下计时抖动会让 hypothesis 误报慢例，关 deadline（不影响断言强度）
settings.register_profile("sylanne", deadline=None)
settings.load_profile("sylanne")

# —— 共用策略 ——
finite = st.floats(allow_nan=False, allow_infinity=False, width=32)
unit = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
signed_unit = st.floats(min_value=-1.0, max_value=1.0, allow_nan=False)
any_text = st.text(max_size=200)   # 任意 unicode（含空串/emoji/控制符）


def _body(**kw) -> BodySnapshot:
    return BodySnapshot(session_key="p", turns=1, **kw)


body_strategy = st.builds(
    _body,
    warmth=signed_unit, tension=unit, repair_pressure=unit,
    scar=unit, strain=unit, sovereignty=unit, exhaustion=unit,
    surprise=unit, expression_drive=unit,
)


# ===========================================================================
# lexicon —— 全内核唯一观测模型：任意 unicode 不抛、密度非负有限（防御式边界）
# ===========================================================================

@given(any_text)
def test_read_signals_total_and_nonnegative(text: str) -> None:
    sig = read_signals(text)
    for v in (sig.warm, sig.cold, sig.distress, sig.exclaim, sig.punct):
        assert math.isfinite(v) and v >= 0.0
    assert sig.length == len(text or "")
    assert math.isfinite(sig.valence_cue)
    assert 0.0 <= sig.engagement_cue <= 1.3


@given(any_text)
def test_distill_features_shape_and_finite(text: str) -> None:
    """蒸馏特征恒 8 维有限（维序=旧档权重契约，铁律④的前提）。"""
    feats = distill_features(text)
    assert len(feats) == N_DISTILL_FEATURES
    assert all(math.isfinite(f) for f in feats)
    assert feats[0] == 1.0   # bias 恒 1


# ===========================================================================
# verbal —— 数值→语言映射：界内、单调（AUDIT-20260612-001 的序数保证）
# ===========================================================================

@given(finite)
def test_level_index_in_range(x: float) -> None:
    idx = level_index(x, -1.0, 1.0, n=7)
    assert 0 <= idx <= 6


@given(finite, finite)
def test_level_index_monotone(a: float, b: float) -> None:
    """单调性：x 更大 → 级别不降（7 级序数映射的核心契约）。"""
    lo, hi = sorted((a, b))
    assert level_index(lo, -1.0, 1.0) <= level_index(hi, -1.0, 1.0)


@given(finite)
def test_level7_returns_word_from_table(x: float) -> None:
    assert level7(x, 0.0, 1.0) in LEVELS7


# ===========================================================================
# personality_saddle —— A7 人格显函数：有限 + 三条单调性（ignition docstring 明文）
# ===========================================================================

@given(st.dictionaries(
    st.sampled_from(["curiosity", "warmth_bias", "sovereignty_guard", "patience", "edge"]),
    finite, max_size=5,
))
def test_saddle_finite_for_any_traits(traits: dict) -> None:
    express_at, hold_below, hold_floor = personality_saddle(_body(personality=traits))
    assert all(math.isfinite(v) for v in (express_at, hold_below, hold_floor))


@given(unit, unit)
def test_saddle_monotonicity(t1: float, t2: float) -> None:
    """∂express_at/∂curiosity<0；∂hold_below/∂sovereignty>0；∂hold_floor/∂patience>0。"""
    lo, hi = sorted((t1, t2))
    e_lo = personality_saddle(_body(personality={"curiosity": lo}))[0]
    e_hi = personality_saddle(_body(personality={"curiosity": hi}))[0]
    assert e_hi <= e_lo
    h_lo = personality_saddle(_body(personality={"sovereignty_guard": lo}))[1]
    h_hi = personality_saddle(_body(personality={"sovereignty_guard": hi}))[1]
    assert h_hi >= h_lo
    f_lo = personality_saddle(_body(personality={"patience": lo}))[2]
    f_hi = personality_saddle(_body(personality={"patience": hi}))[2]
    assert f_hi >= f_lo


# ===========================================================================
# DistillationDomain —— NLMS 数值稳定：权重有界、保真度在界、垃圾档不炸
# ===========================================================================

def _evolve_ctx(body: BodySnapshot, text: str) -> BeatContext:
    return BeatContext(session_key="p", event=None, body=body, text=text,
                       phase=Phase.EVOLVE)


@given(st.lists(st.tuples(any_text, signed_unit, unit), max_size=30))
def test_distill_weights_bounded_after_any_stream(stream: list) -> None:
    """任意文本/体感流 ingest 后：|w|≤8（_W_CLIP）、fidelity∈[0,1]、误差 EMA 有限。"""
    d = DistillationDomain()
    for text, warmth, surprise in stream:
        d.ingest(_evolve_ctx(_body(warmth=warmth, surprise=surprise), text))
    for row in d._w.values():
        assert all(math.isfinite(w) and abs(w) <= 8.0 for w in row)
    assert 0.0 <= d.fidelity() <= 1.0
    assert all(math.isfinite(e) for e in d._err_ema.values())


@given(any_text, body_strategy)
def test_distill_atypicality_in_unit_interval(text: str, body: BodySnapshot) -> None:
    d = DistillationDomain()
    d.ingest(_evolve_ctx(_body(warmth=0.3), "热身样本"))
    assert 0.0 <= d.atypicality(text, body) <= 1.0


@given(st.dictionaries(st.text(max_size=8), st.none() | st.integers() | st.text(max_size=8)
                       | st.lists(st.integers(), max_size=3), max_size=6))
def test_distill_load_garbage_archive_never_raises(garbage: dict) -> None:
    """铁律④容缺加载：任意垃圾存档 → 不抛、状态仍可用。"""
    d = DistillationDomain()
    d.load_dict(garbage)
    assert 0.0 <= d.fidelity() <= 1.0


def test_distill_roundtrip_exact() -> None:
    """存档往返逐位保真（铁律④：她学到的东西一位都不能丢）。"""
    d = DistillationDomain()
    for i in range(15):
        d.ingest(_evolve_ctx(_body(warmth=0.1 * (i % 7) - 0.3, surprise=0.4), f"样本{i}抱抱"))
    d2 = DistillationDomain()
    d2.load_dict(d.to_dict())
    assert d2._w == d._w and d2._samples == d._samples


# ===========================================================================
# EmotionLedger —— 积分非负、SPEAK 释放单调、垃圾档不炸（铁律②④）
# ===========================================================================

@given(st.lists(st.tuples(signed_unit, st.sampled_from(["speak", "silent", "fallback"])),
                max_size=40))
def test_emotion_integral_nonnegative_and_speak_releases(stream: list) -> None:
    led = EmotionLedger()
    for warmth, outcome in stream:
        ctx = _evolve_ctx(_body(warmth=warmth, tension=abs(warmth)), "x")
        ctx.scratch["render_outcome"] = outcome
        before = led._unexpressed
        led.ingest(ctx)
        assert led._unexpressed >= 0.0
        if outcome == "speak":
            assert led._unexpressed <= before + 1e-9   # 表达即释放，绝不增
    assert led._volatility() >= 0.0


@given(st.dictionaries(st.text(max_size=8), st.none() | st.text(max_size=8)
                       | st.lists(st.text(max_size=4), max_size=3), max_size=6))
def test_emotion_load_garbage_never_raises(garbage: dict) -> None:
    led = EmotionLedger()
    led.load_dict(garbage)
    led.ingest(_evolve_ctx(_body(warmth=0.2), "x"))   # 加载后仍可正常推进


# ===========================================================================
# UserModelDomain —— 精度在 [floor,ceil]、同步度在 (0,1]、垃圾档不炸
# ===========================================================================

@given(st.lists(any_text, max_size=25))
def test_usermodel_precision_and_synchrony_bounded(texts: list) -> None:
    um = UserModelDomain()
    for i, text in enumerate(texts):
        ctx = _evolve_ctx(_body(warmth=0.1), text)
        ctx.scratch["now"] = 1000.0 + i * 60.0
        um.ingest(ctx)
    for p in um._disp_precision.values():
        assert 0.05 <= p <= 0.99
    assert 0.0 < um.synchrony() <= 1.0
    assert 0.0 <= um._grip() <= 1.0
    line = um.prompt_line()
    assert isinstance(line, str) and line


@given(st.dictionaries(st.sampled_from(["disposition", "disp_precision", "pe_history",
                                        "sync_trace", "rhythm_ema", "junk"]),
                       st.none() | st.text(max_size=6) | st.integers()
                       | st.lists(st.none() | st.text(max_size=4), max_size=3), max_size=6))
def test_usermodel_load_garbage_never_raises(garbage: dict) -> None:
    um = UserModelDomain()
    um.load_dict(garbage)
    assert 0.0 < um.synchrony() <= 1.0


# ===========================================================================
# NarrativeSelfDomain —— 纪元/固化只增（A6 不可逆）、可塑性在 [0,1]
# ===========================================================================

@given(st.lists(st.tuples(unit, unit), max_size=30))
def test_narrative_monotone_irreversibles(stream: list) -> None:
    nd = NarrativeSelfDomain()
    prev_epoch, prev_oss = 0, 0.0
    for scar, npe in stream:
        ctx = _evolve_ctx(_body(scar=scar, warmth=0.1), "x")
        ctx.scratch["narrative_pe"] = npe
        nd.ingest(ctx)
        oss = nd.ossification("warmth")
        assert nd._epoch >= prev_epoch          # 纪元只增（A6）
        assert oss >= prev_oss and oss <= 0.95  # 固化只增且封顶台阶内
        assert 0.0 <= nd.plasticity_scale("warmth") <= 1.0
        prev_epoch, prev_oss = nd._epoch, oss


# ===========================================================================
# snapshot_from_surface —— 防御式边界：任意嵌套垃圾 → 不抛 + clamp 字段在界
# ===========================================================================

_garbage_value = st.recursive(
    st.none() | st.booleans() | finite | st.text(max_size=10),
    lambda children: st.lists(children, max_size=3)
    | st.dictionaries(st.sampled_from(
        ["host_payload", "body", "affect_dynamics", "computation_emotion", "personality",
         "traits", "temperature", "warmth", "wound", "pulse", "needs", "immunity",
         "mortality", "nerve", "integrated_self", "state_index", "turns", "junk"]),
        children, max_size=5),
    max_leaves=20,
)


@given(st.dictionaries(st.sampled_from(["host_payload", "body", "session_key", "turns", "junk"]),
                       _garbage_value, max_size=5),
       st.dictionaries(st.sampled_from(["surprise", "mean_surprise", "precision", "epoch"]),
                       st.none() | finite | st.text(max_size=4), max_size=4))
def test_snapshot_from_surface_total_and_clamped(surface: dict, extras: dict) -> None:
    """旧架构 hp.get().get() 脆弱穿透的反面：脆弱性全部收敛在这一处且它是 total。"""
    snap = snapshot_from_surface(surface, "s", extras=extras)
    assert -1.0 <= snap.warmth <= 1.0
    assert 0.0 <= snap.tension <= 1.0
    assert 0.0 <= snap.repair_pressure <= 1.0
    assert 0.0 <= snap.intimacy_gravity <= 1.0
    assert isinstance(snap.personality, dict)


# ===========================================================================
# Renderer —— total function：任意 intents/scratch/draft → 永远返回合法 Reply
# ===========================================================================

@given(st.lists(st.builds(
        Intent,
        source=st.sampled_from(["state_query", "expression", "ignition", "junk"]),
        payload=st.dictionaries(st.sampled_from(["reason", "action", "x"]),
                                st.text(max_size=8), max_size=2),
        flags=st.sampled_from([(), ("silent",), ("speak_drive",)]),
    ), max_size=4),
    st.none() | any_text,
    st.dictionaries(st.sampled_from(["silent", "express", "recalled"]),
                    st.none() | st.text(max_size=8)
                    | st.dictionaries(st.text(max_size=4), st.text(max_size=4), max_size=2),
                    max_size=3))
def test_renderer_total_function(intents: list, draft, scratch: dict) -> None:
    ctx = BeatContext(session_key="p", event=None, body=_body(), text="在吗",
                      intents=intents)
    ctx.scratch.update(scratch)
    reply = DefaultRenderer().render(ctx, draft=draft)
    assert isinstance(reply, Reply)
    assert reply.kind in (ReplyKind.SPEAK, ReplyKind.SILENT, ReplyKind.FALLBACK)
    if reply.kind is ReplyKind.SPEAK:
        assert reply.parts and all(isinstance(p, str) and p.strip() for p in reply.parts)


@given(st.lists(st.text(max_size=10), max_size=5))
def test_reply_speak_filters_blank_or_falls_back(parts: list) -> None:
    """Reply.speak：空白分段滤除；全空 → FALLBACK（"空=静默"歧义在类型层消灭）。"""
    r = Reply.speak(*parts)
    if any(p.strip() for p in parts):
        assert r.kind is ReplyKind.SPEAK and all(p.strip() for p in r.parts)
    else:
        assert r.kind is ReplyKind.FALLBACK


# ===========================================================================
# 风格/躯体公式 —— 任意 body：有限输出；recall 加成恰 +0.2 进 segment（review F1/F2）
# ===========================================================================

@given(body_strategy)
def test_style_and_guard_finite(body: BodySnapshot) -> None:
    style = compose_style(body)
    assert all(math.isfinite(float(style[k]))
               for k in ("intensity", "segment_bias", "pause_bias"))
    g, s = guard_soften_from_body(body)
    assert math.isfinite(g) and math.isfinite(s)


@given(body_strategy, finite, finite, unit)
def test_style_recall_bonus_isolated(body: BodySnapshot, arousal: float,
                                     valence: float, vol: float) -> None:
    a = compose_style(body, arousal=arousal, valence=valence, volatility=vol)
    b = compose_style(body, arousal=arousal, valence=valence, volatility=vol,
                      has_recall=True)
    assert b["segment_bias"] == pytest.approx(a["segment_bias"] + 0.2)
    assert b["intensity"] == pytest.approx(a["intensity"])
    assert b["pause_bias"] == pytest.approx(a["pause_bias"])
