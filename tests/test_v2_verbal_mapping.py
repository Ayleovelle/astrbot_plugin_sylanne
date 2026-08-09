"""verbal 映射层测试 —— "说给 LLM 听"的三元组编码（级别+方向+基线偏离）。

设计断言（回应"简单映射不够精准"）：
- 级别是 7 级序数（≈0.14 分辨率，措辞消费者的满精度），单调、越界 clamp；
- 方向与基线偏离是浮点数不携带的措辞信息——映射层信息量严格超过裸浮点；
- 所有面向 LLM 的渲染（prompt_line / 心象片段）零小数（审计：浮点=验算诱饵）；
- 系统内部全精度不受影响（映射是纯函数渲染层，不回写任何状态）。
"""

from __future__ import annotations

import re

from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase
from sylanne_alpha.v2core.domains.emotion import EmotionLedger
from sylanne_alpha.v2core.domains.narrative_self import NarrativeSelfDomain
from sylanne_alpha.v2core.domains.user_model import UserModelDomain
from sylanne_alpha.v2core.verbal import LEVELS7, level7, level_index, trend_word, vs_baseline

_DECIMAL = re.compile(r"\d+\.\d")   # 小数模式（整数允许：纪元2/经历5枚 不是验算诱饵）


def _body(**kw) -> BodySnapshot:
    return BodySnapshot(session_key="v", turns=1, **kw)


# ---- 通用阶梯 ----

def test_level_index_monotone_and_clamped() -> None:
    xs = [-1.0, 0.0, 0.14, 0.3, 0.5, 0.71, 0.86, 1.0, 2.0]
    idxs = [level_index(x) for x in xs]
    assert idxs == sorted(idxs), "级别必须单调"
    assert idxs[0] == 0 and idxs[-1] == 6, "越界必须 clamp 到两端"


def test_level7_boundaries() -> None:
    assert level7(0.0) == LEVELS7[0]
    assert level7(0.5) == LEVELS7[3]      # 中等
    assert level7(1.0) == LEVELS7[-1]
    # 自定义词组 + 有符号域
    words = ("冰", "凉", "平", "暖", "烫")
    assert level7(-1.0, -1.0, 1.0, words) == "冰"
    assert level7(0.0, -1.0, 1.0, words) == "平"
    assert level7(1.0, -1.0, 1.0, words) == "烫"


def test_trend_and_baseline_words() -> None:
    assert trend_word(0.1) == "在升"
    assert trend_word(-0.1) == "在降"
    assert trend_word(0.0) == ""                       # 平稳默认不占 token
    assert vs_baseline(0.8, 0.3) == "高于平时"
    assert vs_baseline(0.1, 0.6) == "低于平时"
    assert vs_baseline(0.5, 0.5) == ""


def test_trend_and_baseline_two_tier_magnitude() -> None:
    """双档强度：缓变/骤变、偏一点/偏很远是不同的措辞局面（修"方向丢幅度"）。"""
    kw = dict(eps=0.08, up="在升温", down="在降温",
              strong_eps=0.3, up_strong="骤然升温", down_strong="骤然降温")
    assert trend_word(0.15, **kw) == "在升温"
    assert trend_word(0.5, **kw) == "骤然升温"
    assert trend_word(-0.15, **kw) == "在降温"
    assert trend_word(-0.5, **kw) == "骤然降温"
    assert trend_word(0.02, **kw) == ""

    bkw = dict(band=0.25, above="比平时暖", below="比平时凉",
               strong_band=0.55, above_strong="比平时暖得多", below_strong="比平时凉得多")
    assert vs_baseline(0.4, 0.0, **bkw) == "比平时暖"
    assert vs_baseline(0.8, 0.0, **bkw) == "比平时暖得多"
    assert vs_baseline(-0.8, 0.0, **bkw) == "比平时凉得多"


def test_emotion_line_strong_tier() -> None:
    """骤变场景：惯常很凉的她突然滚烫 → 强档词出现。"""
    emo = EmotionLedger()
    emo.load_dict({"fast_ema": 0.9, "slow_ema": -0.6})
    line = emo.prompt_line(_body(warmth=0.95, tension=0.0))
    assert "比平时暖得多" in line
    assert "骤然升温" in line
    assert not _DECIMAL.search(line)


# ---- 领域 prompt_line：三元组真的在、且零小数 ----

def test_emotion_line_levels_and_deviation() -> None:
    emo = EmotionLedger()
    # 她的惯常底色是凉的（慢 EMA=-0.5），此刻很暖 → 级别+基线偏离都该出现
    emo.load_dict({"fast_ema": 0.6, "slow_ema": -0.5, "unexpressed": 3.0})
    line = emo.prompt_line(_body(warmth=0.8, tension=0.6))
    assert not _DECIMAL.search(line), f"出现小数: {line}"
    assert "暖" in line                      # ① 级别
    assert "比平时暖" in line                # ③ 基线偏离（浮点不携带的信息）
    assert "升温" in line                    # ② 方向（缓/骤任一档；此处背离大→骤然升温）
    assert "张力" in line and "憋了很多话" in line


def test_emotion_line_cold_side() -> None:
    emo = EmotionLedger()
    emo.load_dict({"fast_ema": -0.6, "slow_ema": 0.4})
    line = emo.prompt_line(_body(warmth=-0.7, tension=0.1))
    assert "凉" in line and "比平时凉" in line and "降温" in line
    assert "张力" not in line                # 松弛区不占 token


# ---- 冷端行为指令（AUDIT-20260612-001 标定修复：冷端状态词被人设底色盖掉）----

def test_cold_directives_same_length_and_cold_only() -> None:
    """词-指令同长同索引（同源单调）；指令只在冷端三档，暖端/中性纯线索。"""
    assert len(EmotionLedger._WARMTH_DIRECTIVES) == len(EmotionLedger._WARMTH_WORDS)
    for i in range(3):
        assert EmotionLedger._WARMTH_DIRECTIVES[i], f"冷端档 {i} 缺行为指令"
    for i in range(3, 7):
        assert EmotionLedger._WARMTH_DIRECTIVES[i] == "", f"暖/中档 {i} 不应携带指令"


def test_emotion_line_cold_levels_carry_directives() -> None:
    """冷端三档 prompt_line 必须携带与档位同源的行为指令（词-指令永不撕裂）。"""
    cases = [(-1.0, 0), (-0.7, 1), (-0.35, 2)]   # 冰凉 / 很凉 / 微凉
    for warmth, idx in cases:
        line = EmotionLedger().prompt_line(_body(warmth=warmth))
        assert EmotionLedger._WARMTH_WORDS[idx] in line, f"warmth={warmth} 档位词错: {line}"
        assert EmotionLedger._WARMTH_DIRECTIVES[idx] in line, \
            f"warmth={warmth} 缺该档行为指令: {line}"
        assert not _DECIMAL.search(line)


def test_emotion_line_warm_and_neutral_no_directive() -> None:
    """中性与暖端不带指令（标定证实暖端线索天然生效，过度指令反伤自然度）。"""
    for warmth in (0.0, 0.3, 0.8, 1.0):
        line = EmotionLedger().prompt_line(_body(warmth=warmth))
        for d in EmotionLedger._WARMTH_DIRECTIVES[:3]:
            assert d not in line, f"warmth={warmth} 误带冷端指令: {line}"


def test_user_model_line_levels_and_direction() -> None:
    um = UserModelDomain()
    # 高把握 + 上行同步轨迹
    um.load_dict({
        "disp_precision": {"warmth": 0.9, "engagement": 0.9,
                           "defensiveness": 0.9, "distress": 0.9},
        "sync_trace": [{"turn": float(i), "sync": 0.3 + 0.08 * i,
                        "grip": 0.5, "user_pe": 0.2} for i in range(6)],
        "disposition": {"warmth": 0.4, "engagement": 0.5,
                        "defensiveness": 0.0, "distress": 0.0},
    })
    line = um.prompt_line()
    assert not _DECIMAL.search(line), f"出现小数: {line}"
    assert "懂Ta" in line or "了如指掌" in line     # ① 级别（高把握档位）
    assert "越来越合拍" in line                     # ② 方向（轨迹上行）
    assert "偏暖" in line                           # ③ 画像


def test_user_model_line_cold_start_low_levels() -> None:
    um = UserModelDomain()
    line = um.prompt_line()
    assert not _DECIMAL.search(line)
    assert "认识Ta" in line or "素未谋面" in line   # 低把握档位
    assert "越来越合拍" not in line                 # 无轨迹不编方向


# ---- 心象片段端到端：零小数 ----

def test_mind_fragment_has_no_decimals() -> None:
    from sylanne_alpha.v2core.fragment import build_mind_fragment

    emo = EmotionLedger()
    emo.load_dict({"fast_ema": 0.5, "slow_ema": 0.1, "unexpressed": 1.0})
    um = UserModelDomain()
    nd = NarrativeSelfDomain()
    domains = {"emotion": emo, "usermodel": um, "narrative": nd}
    ctx = BeatContext(session_key="v", event=None,
                      body=_body(warmth=0.7, tension=0.6, sovereignty=0.4,
                                 repair_pressure=0.5, exhaustion=0.6),
                      text="在吗", domains=domains)
    ctx.phase = Phase.PERCEPT
    ctx.scratch["you_probably"] = {"disposition": {"warmth": 0.4, "distress": 0.0,
                                                   "defensiveness": 0.0}}
    frag = build_mind_fragment(ctx, domains)
    assert frag and "[心象" in frag
    assert not _DECIMAL.search(frag), f"心象片段出现小数（验算诱饵）: {frag}"
