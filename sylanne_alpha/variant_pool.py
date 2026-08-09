"""通用变体池 —— 把散落各处的"逐字复读"静态模板换成同调不同词的候选集合。

动机（T4-02）：多处硬编码单句模板（空回复兜底文案、犹豫踌躇词、状态自述骨架）逐字复读，
是最容易被识破"这是模板不是人"的 AI 味信号源之一。本模块只做一件事：从一组候选变体里
挑一个出来，并且不让同一 session 连续挑到同一个（recent-N 去重），可选按 condition 标签
分桶（如按 warmth 冷/暖分挑不同语气）。

纯 stdlib，无新依赖，风格对齐 proactive_bridge.py 既有的 random.uniform/choice 用法。

设计要点：
- 调用方自己持有 dedup 历史 state（dict[str, list[str]]，recent_key -> 最近选过的变体），
  本模块不做任何持久化/单例——纯函数式挑选 + 就地维护调用方传入的历史列表。这样"per-session"
  语义由调用方决定（把该 session 的 state dict 传进来即可），本模块不关心 session 是什么。
- state=None 时退化为无状态的 random.choice（没有 session 上下文可用时的兜底，比如渲染层
  异常兜底路径拿不到干净 ctx）。
- variants 既可以是扁平列表，也可以是 {condition: [..]} 的分桶字典；后者配合 condition 参数
  做"按温度档/张力档挑语气"这种轻量条件化，缺桶或 condition=None 时退回 None 桶或字典首个
  非空桶。
"""

from __future__ import annotations

import random
from typing import Mapping, Sequence

# 默认 recent-N：避免与最近 2 次选过的变体重复（连续 2 次不撞，第 3 次允许重复）。
DEFAULT_RECENT_N = 2


def warmth_bucket(warmth: float | None) -> str | None:
    """把 warmth 标量粗分成 cold/warm/neutral 三档，供 condition 参数使用。

    阈值对齐 v2core/renderer.py StateProjector._narrate 的既有分档习惯（|warmth| < 0.1 记中性）。
    warmth 为 None（拿不到/不可达）时返回 None——调用方据此退回无条件的扁平/默认桶。
    """
    if warmth is None:
        return None
    try:
        w = float(warmth)
    except (TypeError, ValueError):
        return None
    if w >= 0.1:
        return "warm"
    if w <= -0.1:
        return "cold"
    return "neutral"


def _resolve_bucket(
    variants: Sequence[str] | Mapping[str, Sequence[str]],
    condition: str | None,
) -> list[str]:
    """把 variants（扁平列表或 condition 分桶字典）解析成一份具体候选列表。

    优先级：精确命中 condition → 显式 None 桶 → 约定俗成的 "neutral" 桶 → 字典里第一个
    非空桶（兜底，保证总有得选，但不作为"正确默认"依赖——调用方该给 None/neutral 桶）。
    """
    if isinstance(variants, Mapping):
        bucket = variants.get(condition)
        if not bucket:
            bucket = variants.get(None)  # type: ignore[arg-type]
        if not bucket:
            bucket = variants.get("neutral")  # type: ignore[arg-type]
        if not bucket:
            for v in variants.values():
                if v:
                    bucket = v
                    break
        return list(bucket or ())
    return list(variants)


def choose(
    variants: Sequence[str] | Mapping[str, Sequence[str]],
    *,
    recent_key: str,
    state: dict[str, list[str]] | None = None,
    condition: str | None = None,
    recent_n: int = DEFAULT_RECENT_N,
    rng: random.Random | None = None,
) -> str:
    """从 variants 里挑一个变体，避免与该 recent_key 最近 recent_n 次撞同一个。

    Args:
        variants: 扁平候选列表，或 {condition: [候选...]} 分桶字典。
        recent_key: dedup 历史的键（同一 recent_key 共享一份"最近选过"记录，一般用模板
            家族名，如 "empty_reply_fallback"；需要更细粒度按 session 去重时由调用方把
            session_key 编进这个键里）。
        state: 调用方持有的 dedup 历史 dict（recent_key -> 最近变体列表），就地更新。
            None 时不做去重，纯 random.choice。
        condition: 分桶字典下选哪一桶（如 warmth_bucket 的返回值）；扁平列表时忽略。
        recent_n: 避免撞的最近条数，<=1 桶只有一个候选时天然无法去重。
        rng: 可选自定义随机源（测试用，默认走全局 random 模块，与仓库既有风格一致）。

    Returns:
        挑中的变体文本；候选桶为空时返回 ""（调用方应有更外层的静态兜底）。
    """
    bucket = _resolve_bucket(variants, condition)
    if not bucket:
        return ""
    picker = rng if rng is not None else random
    if len(bucket) == 1:
        picked = bucket[0]
        # 单候选桶也要记入历史：调用方可能在同一 recent_key 下于不同 turn 切换到别的桶
        # （如 warmth 分档变化），若这里不记录，前一次的单候选桶挑选不会计入 avoid 集合，
        # 下一次换到别的桶又切回来时可能出现"看似连续复读"（MINOR，2026-07-02 修）。
        if state is not None and recent_n > 0:
            recent = state.setdefault(recent_key, [])
            recent.append(picked)
            overflow = recent_n * 4
            if len(recent) > overflow:
                del recent[: len(recent) - recent_n * 2]
        return picked
    if state is None or recent_n <= 0:
        return picker.choice(bucket)
    recent = state.setdefault(recent_key, [])
    avoid = set(recent[-recent_n:]) if recent_n > 0 else set()
    candidates = [v for v in bucket if v not in avoid] or bucket
    picked = picker.choice(candidates)
    recent.append(picked)
    # 历史列表只需留最近这一小段，防止无界增长（每个 recent_key 最多留 recent_n*4 条）。
    overflow = recent_n * 4
    if len(recent) > overflow:
        del recent[: len(recent) - recent_n * 2]
    return picked


# ===========================================================================
# 共享变体池数据 —— 空回复兜底文案（renderer.py + llm_response_pipeline.py 共用一份）
# ===========================================================================

# 按 warmth 分档：语气不是同义改写，是真的换调门（软糯 / 简短生硬 / 走神念叨）。
# 无全角括号"舞台指示"（旧文案"（我想说点什么……）"的说明书感来源）。
EMPTY_REPLY_FALLBACK_VARIANTS: dict[str | None, list[str]] = {
    "warm": [
        "唔…让我缓一下，马上跟你说。",
        "等我一下嘛，脑子突然卡壳了。",
        "刚才想说什么来着…你先别急，等等我。",
    ],
    "cold": [
        "……等一下。",
        "嗯，让我想想。",
        "……先别催。",
    ],
    "neutral": [
        "等我一下。",
        "刚才想说什么来着…算了。",
        "唔…等下再说。",
        "让我缓一下。",
    ],
}


# 绝对最后一道兜底：EMPTY_REPLY_FALLBACK_VARIANTS 桶为空（理论上不会，桶恒非空）或
# choose() 因异常返回 "" 时的静态安全网。两个调用方（renderer.py / llm_response_pipeline.py）
# 共用这一份常量，不再各自内联复制字符串字面量（MINOR，2026-07-02 修：堵住 T4-02 本该
# 消灭的"同一句话两处硬编码"复读，即便这条分支实际不可达）。
LAST_RESORT_FALLBACK_TEXT = "……（我想说点什么，可话到嘴边又散了，再给我一秒。）"


__all__ = [
    "DEFAULT_RECENT_N",
    "warmth_bucket",
    "choose",
    "EMPTY_REPLY_FALLBACK_VARIANTS",
    "LAST_RESORT_FALLBACK_TEXT",
]
