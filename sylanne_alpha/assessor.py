from __future__ import annotations

from collections.abc import Callable
from typing import Any

ASSESSOR_SCHEMA_VERSION = "sylanne.alpha.assessor.v1"


def assess_with_lanes(
    *,
    text: str = "",
    switches: dict[str, Any] | None = None,
    fast_provider: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    switches = dict(switches or {})
    fast = dict(switches.get("fast_assessor") or {})
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
            fallback = _local_gate(text)
            fallback["fallback_reason"] = "fast_assessor_failed"
            return fallback
    return _local_gate(text)


def _local_gate(text: str) -> dict[str, Any]:
    normalized = " ".join(str(text or "").split())
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
    preview = " ".join(str(text or "").split())[:160]
    return f"Decide whether this user fragment is complete. Return JSON only. text={preview!r}"


def _safe_decision(decision: str) -> str:
    return decision if decision in {"hold", "release"} else "hold"


__all__ = ["ASSESSOR_SCHEMA_VERSION", "assess_with_lanes"]
