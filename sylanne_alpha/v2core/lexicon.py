"""v2core 文本信号词典 —— 全内核唯一的浅层文本观测模型。

为什么要有这个模块（Fable 重做版）：
旧实现里同一个概念（"这条消息暖不暖"）在 user_model / understanding / distillation
三个文件里各养了一套互不一致的字符表，且 user_model 把 "？?！!" 计入冷漠证据——
用户每提一个问题，"防御性"证据就上升。这是没有设计观测模型的直接后果。

本模块是修正：
- 全内核只有这一份词表与一份 `read_signals()`。任何能力/领域要文本线索，读它，不许自算。
- 提问是【投入】信号（engagement），不是冷漠。感叹/标点是唤起线索，不进效价。
- `distill_features()` 保持 8 维、与旧档权重维序一致（蒸馏域旧存档可继续用，铁律④）。

诚实定位：这是零-LLM 的浅层启发式观测，不是语义理解。它的输出永远要再被领域后验
（精度加权）消化，单条信号不可信任——这是它与"硬编码 intent==撒娇"的本质区别：
它只产证据，不直接动任何状态。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# —— 词表（可调，但全内核只此一份）——
# 多字词优先（"想你"比裸 "想" 准），少量高置信单字保留。
_WARM_WORDS: tuple[str, ...] = (
    "❤", "🥰", "😊", "😼", "💕", "亲亲", "抱抱", "贴贴", "喜欢", "想你", "爱你",
    "谢谢", "辛苦了", "晚安", "早安", "啵", "蹭", "摸摸",
)
_COLD_WORDS: tuple[str, ...] = (
    "哼", "烦", "滚", "闭嘴", "讨厌", "无聊", "算了", "随便", "呵呵", "别说了",
)
_DISTRESS_WORDS: tuple[str, ...] = (
    "难过", "想哭", "哭了", "好累", "累死", "疼", "痛", "委屈", "崩溃", "唉",
    "睡不着", "焦虑", "害怕", "😭", "💔",
)
_PUNCT_CHARS = "，。！？、…,.!?；;"


@dataclass(frozen=True, slots=True)
class TextSignals:
    """一条消息的浅层观测向量（全部零-LLM、纯计数派生）。

    密度类字段（warm/cold/distress/exclaim/punct）已按文本长度归一并 ×10 缩放，
    短消息里一个暖词的权重高于长消息——符合直觉（短句一个"抱抱"就是重点）。
    """

    length: int = 0
    warm: float = 0.0          # 暖词密度（正向效价证据）
    cold: float = 0.0          # 冷词密度（负向效价证据；不含问号/感叹）
    distress: float = 0.0      # 苦恼词密度
    question: bool = False     # 是否在提问（投入/求回应信号，非冷漠）
    exclaim: float = 0.0       # 感叹密度（唤起线索，无效价方向）
    punct: float = 0.0         # 标点密度（表达节奏线索）

    @property
    def valence_cue(self) -> float:
        """文本效价线索 = 暖 − 冷（有符号，不封顶）。"""
        return self.warm - self.cold

    @property
    def engagement_cue(self) -> float:
        """投入线索：长度饱和 + 提问加成。[0, ~1.3]"""
        base = min(1.0, self.length / 40.0)
        return base + (0.3 if self.question else 0.0)


def read_signals(text: str) -> TextSignals:
    """从文本读出浅层信号。空文本 → 全零（调用方按需判空降级）。"""
    t = text or ""
    n = len(t)
    if n == 0:
        return TextSignals()
    inv10 = 10.0 / n
    warm = sum(t.count(w) for w in _WARM_WORDS)
    cold = sum(t.count(w) for w in _COLD_WORDS)
    distress = sum(t.count(w) for w in _DISTRESS_WORDS)
    exclaim = t.count("!") + t.count("！")
    punct = sum(t.count(c) for c in _PUNCT_CHARS)
    return TextSignals(
        length=n,
        warm=warm * inv10,
        cold=cold * inv10,
        distress=distress * inv10,
        question=("?" in t or "？" in t),
        exclaim=exclaim * inv10,
        punct=punct * inv10,
    )


# 静态词表全集（供 SharedLexicon 梗采集排除：人人都说的词不配当"我们的梗"）
STATIC_WORDS: frozenset = frozenset(_WARM_WORDS + _COLD_WORDS + _DISTRESS_WORDS)


# —— 蒸馏域特征（8 维，维序与旧档权重严格一致：铁律④）——
# 旧序：bias, log_len, warm_cue, cold_cue, question, distress_cue, exclaim, punct_density
DISTILL_FEATURE_NAMES: tuple[str, ...] = (
    "bias", "log_len", "warm_cue", "cold_cue", "question",
    "distress_cue", "exclaim", "punct_density",
)
N_DISTILL_FEATURES = len(DISTILL_FEATURE_NAMES)


def distill_features(text: str) -> list[float]:
    """蒸馏学生编码器的 8 维输入特征。只含文本线索，绝不含目标维（防泄漏）。"""
    sig = read_signals(text)
    if sig.length == 0:
        feats = [0.0] * N_DISTILL_FEATURES
        feats[0] = 1.0
        return feats
    return [
        1.0,
        math.log1p(sig.length) / 6.0,
        sig.warm,
        sig.cold,
        1.0 if sig.question else 0.0,
        sig.distress,
        sig.exclaim,
        sig.punct,
    ]


__all__ = ["TextSignals", "read_signals", "distill_features",
           "DISTILL_FEATURE_NAMES", "N_DISTILL_FEATURES", "STATIC_WORDS"]
