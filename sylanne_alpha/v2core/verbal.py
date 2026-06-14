"""数值 → 语言的标定映射层 —— "说给 LLM 听"的唯一数值表达（Fable 版）。

为什么不给 LLM 浮点数（AUDIT-20260612-001）：高精度小数诱发验算冲动（连环调
代码工具），且 LLM 对 0.6523 vs 0.6589 没有任何措辞层面的分辨力——小数位是噪声。

为什么简单 5 档也不够：丢的不是小数位，是【序数密度】和【上下文】。措辞消费者
真正需要的"精度"是三元组——
  ① 级别 level：7 级序数（人类情感自陈量表 5-9 级 = 情感维度真实可分辨精度，
     Miller 7±2；7 级 ≈ [0,1] 上 0.14 分辨率，对措辞已是满精度）；
  ② 方向 trend：在升 / 在降 / 平稳（裸浮点不携带）；
  ③ 基线偏离 vs_baseline：相对【她自己的惯常水平】偏高/偏低（绝对值 0.6 不说明
     任何事，"比平时暖"才是措辞要的信息——裸浮点同样不携带）。
三样合起来，信息量严格超过一个 4 位小数，且零验算诱饵。

边界纪律：本模块只服务面向 LLM 的渲染（心象片段 / 工具返回的定性侧）。
系统内部（kernel/持久化/WebUI/dict API）永远 float64 全精度，绝不经过这里。
全部纯函数、零状态、零 IO。
"""

from __future__ import annotations

# 7 级通用强度词（单调，索引 0→6）
LEVELS7: tuple[str, ...] = ("极低", "很低", "偏低", "中等", "偏高", "很高", "极高")


def level_index(x: float, lo: float = 0.0, hi: float = 1.0, n: int = 7) -> int:
    """把 x∈[lo,hi] 映成 0..n-1 的级别索引（越界 clamp；单调）。"""
    if hi <= lo:
        return n // 2
    t = (float(x) - lo) / (hi - lo)
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    idx = int(t * n)
    return n - 1 if idx >= n else idx


def level7(x: float, lo: float = 0.0, hi: float = 1.0,
           words: tuple[str, ...] = LEVELS7) -> str:
    """7 级序数词。words 可换成领域专属词组（长度任意，等距分桶）。"""
    return words[level_index(x, lo, hi, n=len(words))]


def trend_word(delta: float, eps: float = 0.03,
               up: str = "在升", down: str = "在降", flat: str = "",
               strong_eps: float | None = None,
               up_strong: str | None = None, down_strong: str | None = None) -> str:
    """方向词，双档强度：|delta|>strong_eps → 强档（骤变），>eps → 缓档，否则 flat。

    强档可选（strong_eps=None 即单档）——补"方向丢幅度"的信息损失：
    缓缓升温和骤然升温对措辞是两种局面，单档方向词分不出来。
    """
    if strong_eps is not None and delta > strong_eps:
        return up_strong if up_strong is not None else up
    if delta > eps:
        return up
    if strong_eps is not None and delta < -strong_eps:
        return down_strong if down_strong is not None else down
    if delta < -eps:
        return down
    return flat


def vs_baseline(x: float, baseline: float, band: float = 0.2,
                above: str = "高于平时", below: str = "低于平时", usual: str = "",
                strong_band: float | None = None,
                above_strong: str | None = None, below_strong: str | None = None) -> str:
    """基线偏离词，双档强度：相对她自己的惯常水平偏了一点 vs 偏得很远。"""
    d = float(x) - float(baseline)
    if strong_band is not None and d > strong_band:
        return above_strong if above_strong is not None else above
    if d > band:
        return above
    if strong_band is not None and d < -strong_band:
        return below_strong if below_strong is not None else below
    if d < -band:
        return below
    return usual


__all__ = ["LEVELS7", "level_index", "level7", "trend_word", "vs_baseline"]
