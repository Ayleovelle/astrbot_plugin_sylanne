"""LLM-based text assessor for semantic classification.

The SDK has no independent language understanding of its own — the HDC encoder
only produces a (semantics-blind) hash. Semantic judgement therefore lives here,
delegated to an external LLM. Besides the coarse ``flags``/``confidence`` used by
the body/needs layer, the assessor emits three *continuous* affective reads —
``valence`` / ``arousal`` / ``wound_risk`` — that drive the emotion core
(VoidScarEngine) directly. These are genuine semantic judgements only the LLM can
make; the local fallback approximates them coarsely from keywords.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from ._numeric import _coerce_float

logger = logging.getLogger("sylanne_core")

_SYSTEM_PROMPT = """你是一个文本情感分析器。分析用户输入的文本，返回 JSON 格式的评估结果。

输出格式（严格 JSON，不要多余文字）：
{
    "confidence": 0.0-1.0,
    "flags": ["tag1", "tag2"],
    "valence": -1.0-1.0,
    "arousal": 0.0-1.0,
    "wound_risk": 0.0-1.0
}

可用标签：
- positive: 正向/安全交互
- negative: 负向/伤害性内容
- boundary: 边界触碰
- recovery: 修复/恢复行为
- idle: 空闲/无实质内容
- intimate: 亲密内容
- conflict: 冲突内容
- farewell: 告别
- greeting: 问候

字段说明：
- confidence: 你对分类的确信程度
- flags: 可以有多个标签
- valence: 情感效价，-1.0(极负面/痛苦) 到 +1.0(极正面/愉悦)，中性为 0
- arousal: 情绪唤起强度，0.0(平静) 到 1.0(强烈激动)
- wound_risk: 这段话戳痛/伤害倾诉对象的风险，0.0(无害) 到 1.0(强烈伤害)

规则：
- 短文本或模糊文本给较低 confidence
- 明确的情感表达给较高 confidence
- valence/arousal/wound_risk 是连续语义判断，请按文本真实含义给值，不要一律给 0"""


async def assess_text(
    text: str,
    llm: Callable[[str, str], Awaitable[str]],
) -> dict[str, Any]:
    if not text.strip():
        return _neutral(flags=["idle"], confidence=0.0)

    try:
        response = await llm(_SYSTEM_PROMPT, text)
        return _parse_response(response)
    except Exception as e:
        logger.debug("Assessor LLM call failed: %s", e)
        result = _local_fallback(text)
        result["_degraded"] = True
        return result


def _neutral(*, flags: list[str], confidence: float) -> dict[str, Any]:
    return {
        "confidence": confidence,
        "flags": list(flags),
        "valence": 0.0,
        "arousal": 0.0,
        "wound_risk": 0.0,
    }


def _parse_response(response: str) -> dict[str, Any]:
    response = response.strip()
    if response.startswith("```"):
        lines = response.split("\n")
        response = "\n".join(lines[1:-1])

    try:
        data = json.loads(response)
        confidence = _coerce_float(data.get("confidence", 0.5), 0.0, 1.0, 0.5)
        flags = data.get("flags", [])
        if not isinstance(flags, list):
            flags = [str(flags)]
        return {
            "confidence": confidence,
            "flags": [f for f in flags if isinstance(f, str)],
            # Continuous affect — older LLMs that only return confidence/flags
            # gracefully default to neutral (0.0) rather than breaking the path.
            "valence": _coerce_float(data.get("valence", 0.0), -1.0, 1.0, 0.0),
            "arousal": _coerce_float(data.get("arousal", 0.0), 0.0, 1.0, 0.0),
            "wound_risk": _coerce_float(data.get("wound_risk", 0.0), 0.0, 1.0, 0.0),
        }
    except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
        # AttributeError: legal-but-non-dict JSON (``[]`` / ``"text"`` / ``null``)
        # parses fine, then ``data.get`` blows up — treat it as malformed, same as
        # a decode error, rather than letting it propagate out of the assessor.
        return _neutral(flags=["idle"], confidence=0.3)


_POSITIVE_KEYWORDS = {"谢谢", "感谢", "开心", "高兴", "喜欢", "爱", "好的", "棒", "赞"}
_NEGATIVE_KEYWORDS = {"讨厌", "烦", "滚", "恨", "难过", "伤心", "生气", "愤怒"}
_HURTFUL_KEYWORDS = {"讨厌", "滚", "恨", "烦"}  # directed-at-listener subset of negative
_GREETING_KEYWORDS = {"你好", "嗨", "hi", "hello", "早", "晚上好", "下午好"}
_FAREWELL_KEYWORDS = {"再见", "拜拜", "bye", "晚安", "回见"}


def _local_fallback(text: str) -> dict[str, Any]:
    """Keyword heuristic used when no LLM is reachable. Coarse on purpose —
    real semantic discrimination (e.g. user's own sadness vs. hostility toward
    the listener) is the LLM's job; here we only approximate from keywords."""
    text_lower = text.lower()
    flags: list[str] = []

    has_greeting = any(k in text_lower for k in _GREETING_KEYWORDS)
    has_farewell = any(k in text_lower for k in _FAREWELL_KEYWORDS)
    has_positive = any(k in text_lower for k in _POSITIVE_KEYWORDS)
    has_negative = any(k in text_lower for k in _NEGATIVE_KEYWORDS)
    has_hurtful = any(k in text_lower for k in _HURTFUL_KEYWORDS)

    if has_greeting:
        flags.append("greeting")
    if has_farewell:
        flags.append("farewell")
    if has_positive:
        flags.append("positive")
    if has_negative:
        flags.append("negative")
    if not flags:
        flags.append("idle")

    valence = 0.0
    arousal = 0.2
    wound_risk = 0.0
    if has_positive:
        valence += 0.6
        arousal += 0.2
    if has_negative:
        valence -= 0.6
        arousal += 0.4
    if has_hurtful:
        wound_risk = 0.45
    if has_greeting:
        valence += 0.2

    return {
        "confidence": 0.3,
        "flags": flags,
        "valence": max(-1.0, min(1.0, valence)),
        "arousal": max(0.0, min(1.0, arousal)),
        "wound_risk": max(0.0, min(1.0, wound_risk)),
    }
