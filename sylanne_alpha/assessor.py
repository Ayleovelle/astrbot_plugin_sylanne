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


__all__ = ["ASSESSOR_SCHEMA_VERSION", "assess_with_lanes"]
