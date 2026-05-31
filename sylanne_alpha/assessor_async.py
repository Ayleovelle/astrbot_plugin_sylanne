"""异步 LLM 评估器 —— 双层语义分析架构。

职责：
  - Fast 层：每条消息都运行，使用小模型，短超时（默认 2s）
    快速提取 valence/arousal/intent/wound_risk
  - Main 层：仅在完整路径消息上运行，使用强模型，长超时（默认 15s）
    深度分析 subtext/avoidance/memorable 等扩展字段

设计原则：
  - 若 LLM 在超时内返回，结果立即注入 Void-Scar 引擎调制情感状态
  - 若超时，系统回退到 HDC（高维计算）粗粒度判断，不阻塞主流程

与其他组件的关系：
  - 被 llm_request_pipeline._background_observe_request 调用
  - 结果通过 computation spine 影响 L3 Void-Scar 层和 L7 表达层
  - 与 assessor.py（同步版）互补：同步版做碎片完整性判断，本模块做情感语义分析
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Coroutine
from typing import Any

from sylanne_alpha.content_sanitizer import sanitize_for_assessment, is_content_filter_refusal

ASSESSOR_ASYNC_SCHEMA_VERSION = "sylanne.alpha.assessor_async.v1"

# Fast 层默认超时（秒）
_FAST_TIMEOUT = 2.0
# Main 层默认超时（秒）——后台运行，不急
_MAIN_TIMEOUT = 15.0


class AsyncAssessor:
    """双层异步 LLM 语义评估器，带有限超时保护。

    Fast 层：
      - 每条消息都运行
      - 极简 prompt（仅文本预览 + JSON 模板）
      - 提取 valence/arousal/intent/wound_risk

    Main 层：
      - 仅在完整路径消息上运行
      - 带对话上下文的丰富 prompt
      - 额外提取 subtext/avoidance/memorable

    与其他组件的关系：
      - 被 llm_request_pipeline._background_observe_request 调用
      - 结果注入 computation spine 调制 Void-Scar 状态
    """

    __slots__ = ("_config", "_stats")

    def __init__(self, config: dict[str, Any] | None = None):
        self._config: dict[str, Any] = dict(config or {})
        self._stats: dict[str, int] = {
            "fast_attempts": 0,
            "fast_successes": 0,
            "fast_timeouts": 0,
            "main_attempts": 0,
            "main_successes": 0,
            "main_timeouts": 0,
            "errors": 0,
        }

    async def assess_fast(
        self,
        text: str,
        llm_caller: Callable[[str], Coroutine[Any, Any, str]],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """快速评估：小模型、极简 prompt、短超时。

        每条消息都运行，用于基本情感分类。

        Args:
            text: 待评估的用户消息文本。
            llm_caller: 异步 LLM 调用回调。
            timeout: 可选超时覆盖（秒）。

        Returns:
            评估结果字典（valence/arousal/intent/wound_risk），超时返回空字典。
        """
        if timeout is None:
            timeout = float(
                self._config.get(
                    "sylanne_alpha_fast_assessor_timeout_seconds", _FAST_TIMEOUT
                )
            )
        self._stats["fast_attempts"] += 1
        try:
            result = await asyncio.wait_for(
                self._do_fast_assess(text, llm_caller), timeout=timeout
            )
            if result:
                self._stats["fast_successes"] += 1
                result["_level"] = "fast"
            return result
        except asyncio.TimeoutError:
            self._stats["fast_timeouts"] += 1
            return {}
        except Exception:
            self._stats["errors"] += 1
            return {}

    async def assess_main(
        self,
        text: str,
        context_lines: list[str],
        llm_caller: Callable[[str], Coroutine[Any, Any, str]],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """主评估：强模型、带上下文的丰富 prompt、长超时。

        仅在完整路径消息上运行，用于深度语义分析。

        Args:
            text: 待评估的用户消息文本。
            context_lines: 最近的对话上下文行。
            llm_caller: 异步 LLM 调用回调。
            timeout: 可选超时覆盖（秒）。

        Returns:
            评估结果字典（含 subtext/avoidance/memorable），超时返回空字典。
        """
        if timeout is None:
            timeout = float(
                self._config.get(
                    "sylanne_alpha_main_assessor_timeout_seconds", _MAIN_TIMEOUT
                )
            )
        self._stats["main_attempts"] += 1
        try:
            result = await asyncio.wait_for(
                self._do_main_assess(text, context_lines, llm_caller), timeout=timeout
            )
            if result:
                self._stats["main_successes"] += 1
                result["_level"] = "main"
            return result
        except asyncio.TimeoutError:
            self._stats["main_timeouts"] += 1
            return {}
        except Exception:
            self._stats["errors"] += 1
            return {}

    # Legacy single-call interface (delegates to fast)
    async def assess_with_timeout(
        self,
        text: str,
        llm_caller: Callable[[str], Coroutine[Any, Any, str]],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """兼容旧接口——委托给 assess_fast。"""
        return await self.assess_fast(text, llm_caller, timeout=timeout)

    def diagnostics(self) -> dict[str, Any]:
        """返回评估器性能诊断信息（命中率、超时次数等）。"""
        fast_total = max(1, self._stats["fast_attempts"])
        main_total = max(1, self._stats["main_attempts"])
        return {
            "schema_version": ASSESSOR_ASYNC_SCHEMA_VERSION,
            **self._stats,
            "fast_hit_rate": round(self._stats["fast_successes"] / fast_total, 3),
            "main_hit_rate": round(self._stats["main_successes"] / main_total, 3),
        }

    # ------------------------------------------------------------------
    # Internal: fast assessment
    # ------------------------------------------------------------------
    async def _do_fast_assess(
        self,
        text: str,
        llm_caller: Callable[[str], Coroutine[Any, Any, str]],
    ) -> dict[str, Any]:
        prompt = self._build_fast_prompt(text)
        response = await llm_caller(prompt)
        if is_content_filter_refusal(response):
            return {}
        parsed = self._parse_response(response)
        if parsed:
            parsed["assessed_at"] = time.time()
        return parsed

    def _build_fast_prompt(self, text: str) -> str:
        """构建快速评估 prompt：仅文本预览 + JSON 模板，最小化 token 消耗。"""
        preview = sanitize_for_assessment(text[:60])
        return f'"{preview}"\n{{"v":?,"a":?,"i":"?","w":?}}'

    # ------------------------------------------------------------------
    # Internal: main assessment
    # ------------------------------------------------------------------
    async def _do_main_assess(
        self,
        text: str,
        context_lines: list[str],
        llm_caller: Callable[[str], Coroutine[Any, Any, str]],
    ) -> dict[str, Any]:
        prompt = self._build_main_prompt(text, context_lines)
        response = await llm_caller(prompt)
        if is_content_filter_refusal(response):
            return {}
        parsed = self._parse_response(response)
        if parsed:
            parsed["assessed_at"] = time.time()
        return parsed

    def _build_main_prompt(self, text: str, context_lines: list[str]) -> str:
        """构建主评估 prompt：带对话上下文，要求输出扩展字段。"""
        ctx = ""
        if context_lines:
            ctx = "\n".join(sanitize_for_assessment(line) for line in context_lines[-2:])
            ctx = f"{ctx}\n"
        preview = sanitize_for_assessment(text[:120])
        return (
            f'{ctx}"{preview}"\n'
            '{"v":?,"a":?,"i":"?","w":?,"m":?,"subtext":"?","avoidance":"?"}\n'
            "m=1 if contains facts/preferences/events/boundaries worth remembering long-term, else 0"
        )

    # ------------------------------------------------------------------
    # Response parsing (shared)
    # ------------------------------------------------------------------
    def _parse_response(self, response: str) -> dict[str, Any]:
        """解析 LLM JSON 响应，容忍周围的非 JSON 文本。

        支持短键（v/a/i/w）和完整键名。
        同时提取主评估器的扩展字段（subtext/avoidance/memorable）。

        Returns:
            解析后的字典，解析失败返回空字典。
        """
        text = response.strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start < 0 or end <= start:
            return {}
        try:
            data = json.loads(text[start:end])
        except (json.JSONDecodeError, ValueError):
            return {}
        result: dict[str, Any] = {}
        valence = data.get("v") if "v" in data else data.get("valence")
        if valence is not None:
            result["valence"] = max(-1.0, min(1.0, float(valence)))
        arousal = data.get("a") if "a" in data else data.get("arousal")
        if arousal is not None:
            result["arousal"] = max(0.0, min(1.0, float(arousal)))
        intent = data.get("i") if "i" in data else data.get("intent")
        if intent is not None:
            result["intent"] = str(intent)[:20]
        wound_risk = data.get("w") if "w" in data else data.get("wound_risk")
        if wound_risk is not None:
            result["wound_risk"] = max(0.0, min(1.0, float(wound_risk)))
        # Main assessor extended fields
        subtext = data.get("subtext")
        if subtext is not None:
            result["subtext"] = str(subtext)[:60]
        avoidance = data.get("avoidance")
        if avoidance is not None:
            result["avoidance"] = str(avoidance)[:60]
        memorable = data.get("m") if "m" in data else data.get("memorable")
        if memorable is not None:
            try:
                result["memorable"] = bool(int(memorable))
            except (ValueError, TypeError):
                result["memorable"] = str(memorable).lower() in ("1", "true", "yes")
        return result


__all__ = ["ASSESSOR_ASYNC_SCHEMA_VERSION", "AsyncAssessor"]
