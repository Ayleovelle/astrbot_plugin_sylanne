from __future__ import annotations

import re
from typing import Any


_CONFIRMED_TYPO_PATTERN = re.compile(
    r"不是\s*(?P<wrong>[^，。,\.\s]{1,12})\s*[，,]?\s*是\s*(?P<right>[^，。,\.\s]{1,12})"
)
_HOMOPHONE_HINTS = ("谐音", "梗", "笑死", "哈哈", "草", "hh", "hhh")
_COMMON_HOMOPHONE_BITS = {
    "记亿犹新": "记忆犹新",
    "绝绝紫": "绝绝子",
    "针不戳": "真不错",
}


def _candidate(
    *,
    raw_text: str,
    candidate: str,
    kind: str,
    confidence: float,
    humor_likelihood: float,
    evidence: list[str],
    should_ask_confirmation: bool,
    should_memorize: bool,
) -> dict[str, Any]:
    return {
        "raw_text": raw_text,
        "candidate": candidate,
        "kind": kind,
        "confidence": round(max(0.0, min(1.0, confidence)), 3),
        "humor_likelihood": round(max(0.0, min(1.0, humor_likelihood)), 3),
        "evidence": evidence,
        "should_ask_confirmation": bool(should_ask_confirmation),
        "should_memorize": bool(should_memorize),
    }


def interpret_user_text(text: str, *, common_ground: dict[str, str] | None = None) -> dict[str, Any]:
    value = str(text or "").strip()
    candidates: list[dict[str, Any]] = []

    typo_match = _CONFIRMED_TYPO_PATTERN.search(value)
    if typo_match:
        candidates.append(
            _candidate(
                raw_text=typo_match.group("wrong"),
                candidate=typo_match.group("right"),
                kind="typo",
                confidence=0.92,
                humor_likelihood=0.05,
                evidence=["explicit_not_x_but_y_correction"],
                should_ask_confirmation=False,
                should_memorize=False,
            )
        )

    lower_value = value.lower()
    for raw, normalized in _COMMON_HOMOPHONE_BITS.items():
        if raw in value:
            humor = 0.72 if any(hint in lower_value for hint in _HOMOPHONE_HINTS) else 0.55
            candidates.append(
                _candidate(
                    raw_text=raw,
                    candidate=normalized,
                    kind="homophone",
                    confidence=0.78,
                    humor_likelihood=humor,
                    evidence=[
                        "known_lightweight_homophone",
                        "joke_hint" if humor >= 0.7 else "surface_homophone",
                    ],
                    should_ask_confirmation=False,
                    should_memorize=True,
                )
            )

    for raw, normalized in (common_ground or {}).items():
        if raw and raw in value:
            candidates.append(
                _candidate(
                    raw_text=raw,
                    candidate=normalized,
                    kind="slang",
                    confidence=0.86,
                    humor_likelihood=0.35,
                    evidence=["confirmed_common_ground"],
                    should_ask_confirmation=False,
                    should_memorize=True,
                )
            )

    return {"raw_text": value, "candidates": candidates}


def classify_memory_gate(candidate: dict[str, Any]) -> dict[str, Any]:
    kind = str(candidate.get("kind") or "uncertain")
    confidence = float(candidate.get("confidence") or 0.0)
    humor = float(candidate.get("humor_likelihood") or 0.0)

    if kind in {"homophone", "joke", "nickname", "slang"} and humor >= 0.45:
        return {
            "layer": "joke_or_bit",
            "allow_long_term_fact": False,
            "allow_common_ground": bool(candidate.get("should_memorize")),
            "reason": "playful_or_common_ground_expression",
        }

    if kind == "typo" and confidence >= 0.85:
        return {
            "layer": "correction",
            "allow_long_term_fact": False,
            "allow_common_ground": False,
            "reason": "explicit_typo_correction_not_fact",
        }

    return {
        "layer": "uncertain_interpretation",
        "allow_long_term_fact": False,
        "allow_common_ground": False,
        "reason": "low_confidence_or_unclassified",
    }
