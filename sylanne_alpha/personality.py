from __future__ import annotations

import hashlib
from typing import Any

PERSONALITY_SCHEMA_VERSION = "sylanne.alpha.personality.v1"
_TRAIT_NAMES = ("warmth_bias", "edge", "curiosity", "patience", "intimacy_gravity", "sovereignty_guard")


def initial_personality(session_key: str, *, seed_text: str = "Sylanne Soulful") -> dict[str, Any]:
    signature = _digest(f"{session_key}\0{seed_text}")
    traits = {
        "warmth_bias": _trait(signature, 0, base=0.56),
        "edge": _trait(signature, 1, base=0.42),
        "curiosity": _trait(signature, 2, base=0.58),
        "patience": _trait(signature, 3, base=0.52),
        "intimacy_gravity": _trait(signature, 4, base=0.50),
        "sovereignty_guard": _trait(signature, 5, base=0.68),
    }
    return {
        "schema_version": PERSONALITY_SCHEMA_VERSION,
        "signature": signature,
        "traits": traits,
        "voice": _voice(traits),
        "drift": {"mode": "slow_plasticity", "events": 0, "plasticity": 0.0},
    }


def drift_personality(personality: dict[str, Any], *, event: dict[str, Any] | None = None, rate: float = 0.02) -> dict[str, Any]:
    event = dict(event or {})
    traits = dict(personality.get("traits") or {})
    confidence = max(0.0, min(1.0, float(event.get("confidence") or 0.0)))
    text = str(event.get("text") or "")
    direction = _event_direction(text)
    step = max(0.0, min(0.05, rate * confidence))
    drifted = {}
    for name in _TRAIT_NAMES:
        current = float(traits.get(name, 0.5))
        drifted[name] = round(max(0.0, min(1.0, current + direction.get(name, 0.0) * step)), 6)
    previous_drift = dict(personality.get("drift") or {})
    return {
        "schema_version": PERSONALITY_SCHEMA_VERSION,
        "signature": str(personality.get("signature") or _digest(str(traits))),
        "traits": drifted,
        "voice": _voice(drifted),
        "drift": {
            "mode": "slow_plasticity",
            "events": int(previous_drift.get("events") or 0) + 1,
            "plasticity": round(min(1.0, float(previous_drift.get("plasticity") or 0.0) + step), 6),
        },
    }


def _event_direction(text: str) -> dict[str, float]:
    direction = {name: 0.0 for name in _TRAIT_NAMES}
    if any(word in text for word in ("锋利", "直接", "尖锐")):
        direction["edge"] += 1.0
        direction["patience"] -= 0.4
    if any(word in text for word in ("温柔", "靠近", "想你")):
        direction["warmth_bias"] += 1.0
        direction["intimacy_gravity"] += 0.8
    if any(word in text for word in ("边界", "不要", "暂停")):
        direction["sovereignty_guard"] += 1.0
    if not any(abs(value) > 0 for value in direction.values()):
        direction["curiosity"] += 0.5
    return direction


def _voice(traits: dict[str, float]) -> dict[str, Any]:
    return {
        "temperature": round((traits["warmth_bias"] + traits["edge"]) / 2, 6),
        "cadence": "slow_burn" if traits["patience"] >= 0.5 else "quick_cut",
        "boundary": "strong" if traits["sovereignty_guard"] >= 0.6 else "soft",
    }


def _trait(signature: str, index: int, *, base: float) -> float:
    byte = int(signature[index * 2 : index * 2 + 2], 16)
    return round(max(0.0, min(1.0, base + (byte / 255.0 - 0.5) * 0.12)), 6)


def _digest(text: str) -> str:
    return hashlib.blake2s(text.encode("utf-8"), digest_size=12).hexdigest()


__all__ = ["PERSONALITY_SCHEMA_VERSION", "drift_personality", "initial_personality"]
