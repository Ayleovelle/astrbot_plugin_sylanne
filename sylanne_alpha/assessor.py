"""同步评估器 —— 快速判断用户消息片段是否完整（hold/release 决策）。

职责：
  - 在消息碎片防抖阶段，快速判断用户输入是否已经完成
  - 优先使用 LLM fast_provider 做语义判断
  - 若 LLM 不可用或超时，回退到本地标点/长度启发式规则

与其他组件的关系：
  - 被 llm_request_pipeline 的碎片防抖逻辑调用
  - 与 assessor_async.py 互补：本模块是同步/轻量版，async 版做深度语义分析
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# 评估器 schema 版本号，用于序列化兼容性检查
ASSESSOR_SCHEMA_VERSION = "sylanne.alpha.assessor.v1"


def assess_with_lanes(
    *,
    text: str = "",
    switches: dict[str, Any] | None = None,
    fast_provider: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """多通道评估入口：优先走 LLM fast_provider，失败则回退本地规则。

    Args:
        text: 待评估的用户消息文本。
        switches: 配置开关字典，包含 fast_assessor 子配置。
        fast_provider: 可选的 LLM 快速评估回调，接收 prompt 返回 JSON dict。

    Returns:
        评估结果字典，包含 decision（"hold"/"release"）、confidence、reason 等字段。
    """
    switches = dict(switches or {})
    fast = dict(switches.get("fast_assessor") or {})
    # 当 fast_assessor 启用且有 provider 时，尝试 LLM 语义判断
    if fast.get("enabled") and fast.get("provider_id") and fast_provider is not None:
        try:
            payload = fast_provider(_fast_prompt(text))
            decision = str(
                payload.get("decision")
                or ("release" if payload.get("complete") else "hold")
            )
            return {
                "schema_version": ASSESSOR_SCHEMA_VERSION,
                "source": "fast_assessor",
                "decision": _safe_decision(decision),
                "confidence": float(payload.get("confidence") or 0.5),
                "reason": str(payload.get("reason") or "fast_assessor"),
            }
        except Exception:
            # LLM 调用失败，回退到本地启发式
            fallback = _local_gate(text)
            fallback["fallback_reason"] = "fast_assessor_failed"
            return fallback
    # 无 LLM 可用时直接走本地规则
    return _local_gate(text)


def _local_gate(text: str) -> dict[str, Any]:
    """本地启发式门控：通过标点符号或文本长度判断消息是否完整。

    Args:
        text: 用户消息文本。

    Returns:
        评估结果字典。
    """
    normalized = " ".join(str(text or "").split())
    # 以句末标点结尾或长度 >= 18 字符视为完整消息
    complete = (
        normalized.endswith(("。", "！", "？", ".", "!", "?")) or len(normalized) >= 18
    )
    return {
        "schema_version": ASSESSOR_SCHEMA_VERSION,
        "source": "local_gate",
        "decision": "release" if complete else "hold",
        "confidence": 0.55 if complete else 0.45,
        "reason": "punctuation_or_length" if complete else "fragment_likely_incomplete",
    }


def _fast_prompt(text: str) -> str:
    """构建发送给 LLM 的快速评估 prompt。"""
    preview = " ".join(str(text or "").split())[:160]
    return f"Decide whether this user fragment is complete. Return JSON only. text={preview!r}"


def _safe_decision(decision: str) -> str:
    """确保 decision 值只能是 hold 或 release，防止 LLM 返回非法值。"""
    return decision if decision in {"hold", "release"} else "hold"


__all__ = [
    "ASSESSOR_SCHEMA_VERSION",
    "assess_with_lanes",
    "CrisisDetector",
    "AssessorConfig",
    "DEFAULT_DIMENSIONS",
    "MediaEmotion",
    "tag_media_emotion",
    "multimodal_fusion",
]


# ---------------------------------------------------------------------------
# Item 104: 表情包/媒体情绪理解接口
# ---------------------------------------------------------------------------

from dataclasses import dataclass


@dataclass
class MediaEmotion:
    """媒体情绪标注结果。"""

    emotion: str  # "happy" / "sad" / "angry" / "neutral" / "ironic"
    intensity: float  # 0-1
    irony_probability: float  # 0-1


def tag_media_emotion(media_type: str, context_text: str) -> MediaEmotion:
    """简单的媒体情绪标注（基于上下文推断）。

    Args:
        media_type: 媒体类型（如 "sticker", "image", "gif"）。
        context_text: 伴随媒体的上下文文本。

    Returns:
        MediaEmotion 标注结果。
    """
    # 哭笑表情 + 正面文字 → ironic
    cry_laugh_markers = ("😂", "🤣", "哭笑", "笑哭")
    if any(m in context_text for m in cry_laugh_markers):
        return MediaEmotion("ironic", 0.6, 0.7)
    # 简单情绪关键词
    if any(w in context_text for w in ("开心", "哈哈", "太好了", "😊", "🥰")):
        return MediaEmotion("happy", 0.5, 0.1)
    if any(w in context_text for w in ("难过", "伤心", "😢", "😭")):
        return MediaEmotion("sad", 0.5, 0.1)
    return MediaEmotion("neutral", 0.3, 0.0)


# ---------------------------------------------------------------------------
# Item 110: 媒体情绪与文本情绪融合
# ---------------------------------------------------------------------------


def multimodal_fusion(
    text_valence: float,
    media_valence: float | None,
    media_irony: float = 0.0,
) -> float:
    """融合文本情绪和媒体情绪。

    Args:
        text_valence: 文本情绪 valence（-1 到 1）。
        media_valence: 媒体情绪 valence（-1 到 1），None 表示无媒体。
        media_irony: 媒体反讽概率（0-1），> 0.5 时取反 media_valence。

    Returns:
        融合后的 valence 值。
    """
    if media_valence is None:
        return text_valence
    # 如果反讽概率高，取反媒体情绪
    adjusted_media = -media_valence if media_irony > 0.5 else media_valence
    # 融合公式：文本 60% + 媒体 40%
    fused = text_valence * 0.6 + adjusted_media * 0.4
    return fused


# ---------------------------------------------------------------------------
# Item 77: 自定义评分维度扩展点
# ---------------------------------------------------------------------------

DEFAULT_DIMENSIONS = ("valence", "arousal", "tension", "warmth", "surprise", "dominance", "formality", "intimacy")


class AssessorConfig:
    """可配置的评分维度管理器。

    将评分维度从硬编码改为可配置，允许外部模块自定义评估维度集合。
    validate_assessment() 确保评估结果包含所有配置的维度（缺失维度补 0.0）。
    """

    def __init__(self, dimensions: tuple[str, ...] = DEFAULT_DIMENSIONS):
        self.dimensions = dimensions

    def validate_assessment(self, result: dict) -> dict:
        """确保评估结果包含所有配置的维度，缺失的补 0.0。

        Args:
            result: 原始评估结果字典。

        Returns:
            包含所有配置维度的标准化评估结果。
        """
        return {d: result.get(d, 0.0) for d in self.dimensions}


# ---------------------------------------------------------------------------
# Item 92: 用户情绪危机检测
# ---------------------------------------------------------------------------


class CrisisDetector:
    """用户情绪危机检测：基于连续负面情绪斜率 + 关键词。"""

    CRISIS_KEYWORDS = (
        "不想活", "自杀", "结束一切", "活着没意思",
        "死", "跳楼", "割腕", "安眠药", "遗书",
    )
    WARNING_KEYWORDS = (
        "好累", "撑不住", "崩溃", "绝望",
        "没有意义", "放弃", "消失",
    )

    def __init__(self):
        self._negative_streak: int = 0
        self._last_level: str = "normal"  # normal / concern / warning / crisis

    def assess(self, text: str, valence: float) -> str:
        """评估当前消息的危机等级。"""
        # 关键词检测
        text_lower = text.lower()
        if any(kw in text_lower for kw in self.CRISIS_KEYWORDS):
            self._last_level = "crisis"
            return "crisis"
        if any(kw in text_lower for kw in self.WARNING_KEYWORDS):
            self._negative_streak += 2

        # 连续负面情绪
        if valence < -0.5:
            self._negative_streak += 1
        elif valence > 0:
            self._negative_streak = max(0, self._negative_streak - 1)

        if self._negative_streak >= 5:
            self._last_level = "warning"
            return "warning"
        elif self._negative_streak >= 3:
            self._last_level = "concern"
            return "concern"

        self._last_level = "normal"
        return "normal"

    def get_safety_hint(self, level: str) -> str | None:
        """返回安全提示（注入 prompt）。"""
        if level == "crisis":
            return (
                "用户可能处于危机状态。温和关心，不要说教，"
                "建议寻求专业帮助。不要忽视也不要过度反应。"
            )
        elif level == "warning":
            return "用户情绪持续低落。保持温暖陪伴，适当询问是否需要帮助。"
        elif level == "concern":
            return "注意到用户情绪偏低，保持关注但不要过度追问。"
        return None
