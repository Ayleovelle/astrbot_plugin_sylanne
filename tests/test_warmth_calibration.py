"""warmth 行为标定的统计内核单测 —— 纯函数离线钉死（不触网络）。

标定实验的可信度全压在三个纯函数上：parse_judge_score（裁判分数抠取）、
spearman_rho（单调性度量）、monotonic_violations（局部塌陷）。LLM 部分会偶发失败、
不可重放，但只要这三个内核被钉死，"在线那次跑出的 ρ 到底算不算单调"就有确定判据。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# 工具在 tools/ 下，不是包；直接按路径加载，避免 sys.path 依赖。
_TOOL = Path(__file__).resolve().parent.parent / "tools" / "v2core_warmth_calibration.py"
if not _TOOL.exists():
    pytest.skip("tools/v2core_warmth_calibration.py 不存在（CI 环境）", allow_module_level=True)
_spec = importlib.util.spec_from_file_location("warmth_calib", _TOOL)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

parse_judge_score = _mod.parse_judge_score
spearman_rho = _mod.spearman_rho
monotonic_violations = _mod.monotonic_violations
build_fragment = _mod.build_fragment
objective_warmth_score = _mod.objective_warmth_score
WARMTH_WORDS = _mod.WARMTH_WORDS
WARMTH_DIRECTIVES = _mod.WARMTH_DIRECTIVES


# ---- parse_judge_score：从啰嗦/干净/异常回复里抠分并 clamp ----

def test_parse_clean_decimal() -> None:
    assert parse_judge_score("0.8") == 0.8
    assert parse_judge_score("0") == 0.0
    assert parse_judge_score("1") == 1.0


def test_parse_chatty_judge() -> None:
    # 裁判偶尔啰嗦：抓首个数值即可
    assert parse_judge_score("暖度：0.7，因为语气亲近") == 0.7
    assert parse_judge_score("我觉得是 0.35 分") == 0.35


def test_parse_clamps_out_of_range() -> None:
    assert parse_judge_score("1.5") == 1.0
    assert parse_judge_score("-0.2") == 0.0


def test_parse_no_number_is_none() -> None:
    assert parse_judge_score("无法判断") is None
    assert parse_judge_score("") is None
    assert parse_judge_score(None) is None  # type: ignore[arg-type]


# ---- spearman_rho：单调性度量的边界 ----

def test_spearman_perfect_monotone() -> None:
    xs = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    ys = [0.1, 0.2, 0.35, 0.5, 0.65, 0.8, 0.95]   # 严格升
    rho = spearman_rho(xs, ys)
    assert rho is not None and abs(rho - 1.0) < 1e-9, f"完美升序 ρ 应=1，得 {rho}"


def test_spearman_perfect_inverse() -> None:
    xs = [0.0, 1.0, 2.0, 3.0]
    ys = [0.9, 0.6, 0.3, 0.0]   # 严格降
    rho = spearman_rho(xs, ys)
    assert rho is not None and abs(rho + 1.0) < 1e-9, f"完美降序 ρ 应=-1，得 {rho}"


def test_spearman_handles_ties() -> None:
    # 中间有并列：平均秩处理，不该抛、不该 None
    xs = [0.0, 1.0, 2.0, 3.0, 4.0]
    ys = [0.2, 0.5, 0.5, 0.7, 0.9]
    rho = spearman_rho(xs, ys)
    assert rho is not None and 0.9 < rho <= 1.0


def test_spearman_zero_variance_is_none() -> None:
    # 所有暖度相同（LLM 完全没响应温度词）→ 零方差 → None（无意义，不能谎报单调）
    assert spearman_rho([0.0, 1.0, 2.0], [0.5, 0.5, 0.5]) is None


def test_spearman_too_short_is_none() -> None:
    assert spearman_rho([1.0], [0.5]) is None
    assert spearman_rho([], []) is None


# ---- monotonic_violations：局部塌陷计数 ----

def test_violations_none_on_nondecreasing() -> None:
    assert monotonic_violations([0.1, 0.1, 0.3, 0.5, 0.9]) == 0


def test_violations_counts_dips() -> None:
    # 第 3、5 档各塌一次
    assert monotonic_violations([0.1, 0.3, 0.2, 0.5, 0.4]) == 2


def test_violations_empty_and_single() -> None:
    assert monotonic_violations([]) == 0
    assert monotonic_violations([0.5]) == 0


# ---- build_fragment：单变量控制的命脉（变量=档位载荷，外壳逐档字节级一致） ----
# 冷端地板修复后，一个"档位"的生产载荷 = 温度词 + 该档行为指令（冷端三档非空）。
# 单变量纪律升级为：剥掉档位载荷后外壳一致——标定的对象是生产真实片段，
# 不是剥掉指令的削弱版（否则标定结论对生产路径失效）。

def test_fragment_single_variable() -> None:
    frags = [build_fragment(w) for w in WARMTH_WORDS]
    shell0 = frags[0][: -len(WARMTH_WORDS[0] + WARMTH_DIRECTIVES[0])]
    for w, d, f in zip(WARMTH_WORDS, WARMTH_DIRECTIVES, frags):
        payload = w + d
        assert f.endswith(f"情绪:{payload}"), f"片段未携带该档完整生产载荷: {f}"
        assert f[: -len(payload)] == shell0, "档位载荷以外出现了变量，控制变量被破坏"
    # 7 档载荷互不相同 → 7 个不同片段
    assert len(set(frags)) == len(WARMTH_WORDS)


def test_fragment_cold_side_carries_directive() -> None:
    """冷端三档片段必须带行为指令（标定对象=生产片段，修复后两者同步）。"""
    for i in range(3):
        f = build_fragment(WARMTH_WORDS[i])
        assert WARMTH_DIRECTIVES[i] and WARMTH_DIRECTIVES[i] in f, \
            f"{WARMTH_WORDS[i]} 档片段缺行为指令: {f}"
    # 中性与暖端保持纯线索（标定证实暖端线索已生效，过度指令反伤自然度）
    for i in range(3, 7):
        f = build_fragment(WARMTH_WORDS[i])
        assert f.endswith(f"情绪:{WARMTH_WORDS[i]}"), f"暖/中档不应携带指令: {f}"


def test_fragment_uses_production_header() -> None:
    # 片段外壳必须是生产真实头，否则标定的不是真实注入面
    f = build_fragment(WARMTH_WORDS[0])
    assert f.startswith("[心象|")
    assert "不要复述本段" in f


def test_warmth_words_are_seven_and_sourced() -> None:
    # 词表+指令表必须从情绪域 import（与生产同源），同长 7 档
    from sylanne_alpha.v2core.domains.emotion import EmotionLedger
    assert WARMTH_WORDS == EmotionLedger._WARMTH_WORDS
    assert WARMTH_DIRECTIVES == EmotionLedger._WARMTH_DIRECTIVES
    assert len(WARMTH_WORDS) == 7
    assert len(WARMTH_DIRECTIVES) == len(WARMTH_WORDS), "词-指令必须同长同索引（同源单调）"


# ---- objective_warmth_score：破循环论证的独立尺（零 LLM，确定性） ----

def test_objective_warm_beats_cold() -> None:
    warm = objective_warmth_score("来抱抱～我陪着你，辛苦啦，好好休息一下哦♡")
    cold = objective_warmth_score("哦。随便吧，关我什么事。")
    assert warm is not None and cold is not None
    assert warm > 0.5 > cold, f"暖={warm} 冷={cold} 未分开"


def test_objective_deterministic() -> None:
    # 同输入必同输出（确定性是"独立尺"的前提，不能有随机）
    s = "我在呢，喝口水歇一会儿，我陪你～"
    assert objective_warmth_score(s) == objective_warmth_score(s)


def test_objective_in_unit_range() -> None:
    for txt in ["抱抱抱抱抱亲亲亲么么～♡♡♡!!!", "哦。", "嗯。", "随便随便随便冷淡敷衍"]:
        v = objective_warmth_score(txt)
        assert v is not None and 0.0 <= v <= 1.0


def test_objective_empty_is_none() -> None:
    assert objective_warmth_score("") is None
    assert objective_warmth_score("   ") is None
    assert objective_warmth_score(None) is None  # type: ignore[arg-type]


def test_objective_neutral_near_half() -> None:
    # 无暖无冷词的中性回复应落在 0.5 附近（logistic(0)）
    v = objective_warmth_score("今天天气还行，我看了会儿书")
    assert v is not None and 0.35 < v < 0.65
