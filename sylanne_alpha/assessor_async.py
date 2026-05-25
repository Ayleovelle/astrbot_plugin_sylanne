"""Async LLM assessor for Sylanne-Embodiment.

Two-level assessment architecture:
  - Fast assessor: runs on every message, small model, 1.5s timeout
  - Main assessor: runs only on full-path messages, strong model, 3s timeout

If the LLM responds within the timeout, its result modulates Void-Scar state
in the same tick. If it times out, the system falls back to HDC coarse judgment.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Coroutine
from typing import Any

ASSESSOR_ASYNC_SCHEMA_VERSION = "sylanne.alpha.assessor_async.v1"

_FAST_TIMEOUT = 2.0
_MAIN_TIMEOUT = 15.0  # Main runs in background, no rush


class AsyncAssessor:
    """Two-level async LLM semantic assessor with bounded timeouts."""

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
        """Fast assessment: small model, minimal prompt, short timeout.

        Runs on every message for basic emotion classification.
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
        """Main assessment: strong model, richer prompt with context, longer timeout.

        Runs only on full-path messages for deep semantic analysis.
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
        """Legacy interface -- delegates to assess_fast."""
        return await self.assess_fast(text, llm_caller, timeout=timeout)

    def diagnostics(self) -> dict[str, Any]:
        """Return diagnostic info about assessor performance."""
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
        parsed = self._parse_response(response)
        if parsed:
            parsed["assessed_at"] = time.time()
        return parsed

    def _build_fast_prompt(self, text: str) -> str:
        """Minimal prompt for fast assessor -- single-line JSON output."""
        preview = text[:60]
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
        parsed = self._parse_response(response)
        if parsed:
            parsed["assessed_at"] = time.time()
        return parsed

    def _build_main_prompt(self, text: str, context_lines: list[str]) -> str:
        """Richer prompt for main assessor with conversation context."""
        ctx = ""
        if context_lines:
            ctx = "\n".join(context_lines[-2:])
            ctx = f"{ctx}\n"
        preview = text[:120]
        return (
            f'{ctx}"{preview}"\n'
            '{"v":?,"a":?,"i":"?","w":?,"m":?,"subtext":"?","avoidance":"?"}\n'
            "m=1 if contains facts/preferences/events/boundaries worth remembering long-term, else 0"
        )

    # ------------------------------------------------------------------
    # Response parsing (shared)
    # ------------------------------------------------------------------
    def _parse_response(self, response: str) -> dict[str, Any]:
        """Parse LLM JSON response, tolerant of surrounding text.

        Accepts both short keys (v/a/i/w) and full keys.
        Also extracts subtext/avoidance from main assessor output.
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
