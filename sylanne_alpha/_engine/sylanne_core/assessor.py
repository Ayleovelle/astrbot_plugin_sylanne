"""LLM-based text assessor for semantic flag classification."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger("sylanne_core")

_SYSTEM_PROMPT = """你是一个文本情感分类器。分析用户输入的文本，返回 JSON 格式的评估结果。

输出格式（严格 JSON，不要多余文字）：
{
    "confidence": 0.0-1.0,
    "flags": ["tag1", "tag2"]
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

规则：
- confidence 表示你对分类的确信程度
- flags 可以有多个标签
- 短文本或模糊文本给较低 confidence
- 明确的情感表达给较高 confidence"""


async def assess_text(
    text: str,
    llm: Callable[[str, str], Awaitable[str]],
) -> dict[str, Any]:
    if not text.strip():
        return {"confidence": 0.0, "flags": ["idle"]}

    try:
        response = await llm(_SYSTEM_PROMPT, text)
        return _parse_response(response)
    except Exception as e:
        logger.debug("Assessor LLM call failed: %s", e)
        result = _local_fallback(text)
        result["_degraded"] = True
        return result


def _parse_response(response: str) -> dict[str, Any]:
    response = response.strip()
    if response.startswith("```"):
        lines = response.split("\n")
        response = "\n".join(lines[1:-1])

    try:
        data = json.loads(response)
        confidence = float(data.get("confidence", 0.5))
        flags = data.get("flags", [])
        if not isinstance(flags, list):
            flags = [str(flags)]
        return {
            "confidence": max(0.0, min(1.0, confidence)),
            "flags": [f for f in flags if isinstance(f, str)],
        }
    except (json.JSONDecodeError, ValueError, TypeError):
        return {"confidence": 0.3, "flags": ["idle"]}


_POSITIVE_KEYWORDS = {"谢谢", "感谢", "开心", "高兴", "喜欢", "爱", "好的", "棒", "赞"}
_NEGATIVE_KEYWORDS = {"讨厌", "烦", "滚", "恨", "难过", "伤心", "生气", "愤怒"}
_GREETING_KEYWORDS = {"你好", "嗨", "hi", "hello", "早", "晚上好", "下午好"}
_FAREWELL_KEYWORDS = {"再见", "拜拜", "bye", "晚安", "回见"}


def _local_fallback(text: str) -> dict[str, Any]:
    text_lower = text.lower()
    flags: list[str] = []

    if any(k in text_lower for k in _GREETING_KEYWORDS):
        flags.append("greeting")
    if any(k in text_lower for k in _FAREWELL_KEYWORDS):
        flags.append("farewell")
    if any(k in text_lower for k in _POSITIVE_KEYWORDS):
        flags.append("positive")
    if any(k in text_lower for k in _NEGATIVE_KEYWORDS):
        flags.append("negative")

    if not flags:
        flags.append("idle")

    return {"confidence": 0.3, "flags": flags}
