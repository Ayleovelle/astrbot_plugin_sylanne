from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .vector import clamp as _clamp


ATTENTION_SCHEMA_VERSION = "sylanne.alpha.attention.v1"
FLOOD_ATTENTION_SCHEMA_VERSION = "sylanne.alpha.attention.flood.v1"
SPARSE_ATTENTION_ROUTES = {
    "event.safe": ("bloodflow", "temperature", "immunity", "muscle"),
    "event.hurt": ("wound", "nerve", "immunity", "mortality"),
    "event.boundary": ("immunity", "nerve", "need.quiet", "mortality"),
    "event.repair": ("wound", "temperature", "need.repair", "bloodflow"),
    "event.idle": ("need.contact", "muscle", "immunity", "mortality"),
    "event.has_text": ("pulse", "bloodflow", "need.expression", "nerve"),
}


@dataclass(frozen=True, slots=True)
class BodyToken:
    name: str
    family: str
    values: tuple[float, ...]


def _token(name: str, family: str, *values: float) -> BodyToken:
    return BodyToken(name=name, family=family, values=tuple(_clamp(value) for value in values[:4]))


def body_tokens(state: dict[str, float], event: dict[str, float]) -> list[BodyToken]:
    tokens = [
        _token("organ.pulse", "pulse", state.get("pulse.rhythm", 0.0), state.get("pulse.strain", 0.0), state.get("pulse.beat", 0.0) % 1.0),
        _token("organ.bloodflow", "bloodflow", state.get("bloodflow.warmth", 0.0), state.get("bloodflow.circulation", 0.0), state.get("bloodflow.memory_flow", 0.0)),
        _token("organ.nerve", "nerve", state.get("nerve.sensitivity", 0.0), state.get("nerve.plasticity", 0.0), state.get("nerve.threshold_drift", 0.0)),
        _token("organ.muscle", "muscle", state.get("muscle.readiness", 0.0), state.get("muscle.fatigue", 0.0), state.get("muscle.trained_reach", 0.0)),
        _token("organ.temperature", "temperature", state.get("temperature.warmth", 0.0), state.get("temperature.volatility", 0.0), state.get("temperature.repair_heat", 0.0)),
        _token("organ.wound", "wound", state.get("wound.open", 0.0), state.get("wound.repair", 0.0), state.get("wound.sensitivity", 0.0), state.get("wound.scar", 0.0)),
        _token("law.immunity", "immunity", state.get("immunity.boundary_pressure", 0.0), state.get("immunity.cooldown", 0.0), state.get("immunity.interruption_budget", 1.0)),
        _token("organ.mortality", "mortality", state.get("mortality.load", 0.0), state.get("mortality.exhaustion", 0.0), state.get("mortality.recovery_debt", 0.0)),
        _token("need.contact", "needs", state.get("needs.need_contact", 0.0)),
        _token("need.quiet", "needs", state.get("needs.need_quiet", 0.0)),
        _token("need.repair", "needs", state.get("needs.need_repair", 0.0)),
        _token("need.expression", "needs", state.get("needs.need_expression", 0.0)),
    ]
    for axis in ("has_text", "confidence", "idle", "safe", "hurt", "boundary", "repair", "repetition"):
        value = float(event.get(axis, 0.0))
        if value > 0.0:
            tokens.append(_token(f"event.{axis}", "event", min(value, 1.0)))
    return tokens[:32]


class TinyBodyAttention:
    def __init__(self, *, hidden_dim: int = 32, heads: int = 2, layers: int = 1) -> None:
        self.hidden_dim = min(32, max(8, int(hidden_dim)))
        self.heads = min(2, max(1, int(heads)))
        self.layers = 1 if layers != 0 else 0

    def update(self, state: dict[str, float], event: dict[str, float]) -> dict[str, Any]:
        tokens = body_tokens(state, event)
        attention = self._attention(tokens)
        delta = self._project(tokens, attention)
        return {
            "schema_version": ATTENTION_SCHEMA_VERSION,
            "delta": {key: round(value, 6) for key, value in delta.items()},
            "attention": attention,
            "cost": {
                "tokens": len(tokens),
                "hidden_dim": self.hidden_dim,
                "heads": self.heads,
                "layers": self.layers,
                "complexity": f"O({len(tokens)}^2*{self.hidden_dim})",
                "route_edges": sum(len(targets) for targets in attention.values()),
                "route_complexity": "O(E*R)",
            },
        }

    def _attention(self, tokens: list[BodyToken]) -> dict[str, list[str]]:
        names = {token.name for token in tokens}
        return {
            event_name: list(targets)
            for event_name, targets in SPARSE_ATTENTION_ROUTES.items()
            if event_name in names
        }

    def _project(self, tokens: list[BodyToken], attention: dict[str, list[str]]) -> dict[str, float]:
        event_strength = {token.name: token.values[0] for token in tokens if token.family == "event" and token.values}
        delta: dict[str, float] = {}

        def add(axis: str, value: float) -> None:
            delta[axis] = delta.get(axis, 0.0) + value

        safe = event_strength.get("event.safe", 0.0)
        hurt = event_strength.get("event.hurt", 0.0)
        boundary = event_strength.get("event.boundary", 0.0)
        repair = event_strength.get("event.repair", 0.0)
        idle = event_strength.get("event.idle", 0.0)
        has_text = event_strength.get("event.has_text", 0.0)
        confidence = event_strength.get("event.confidence", 0.0)
        repetition = event_strength.get("event.repetition", 0.0)

        add("bloodflow.warmth", 0.045 * safe + 0.018 * has_text + 0.012 * confidence - 0.018 * hurt)
        add("bloodflow.circulation", 0.03 * has_text + 0.016 * safe)
        add("temperature.warmth", 0.04 * safe + 0.02 * repair - 0.035 * hurt)
        add("temperature.volatility", 0.055 * boundary + 0.035 * hurt - 0.025 * safe)
        add("wound.open", 0.075 * hurt + 0.03 * boundary - 0.05 * repair)
        add("wound.repair", 0.065 * repair + 0.012 * hurt)
        add("wound.sensitivity", 0.05 * hurt + 0.025 * boundary)
        add("nerve.sensitivity", 0.035 * hurt + 0.02 * boundary + 0.01 * has_text - 0.018 * safe)
        add("nerve.plasticity", 0.018 * has_text + 0.012 * repetition)
        add("needs.need_contact", 0.06 * idle + 0.014 * has_text - 0.03 * safe)
        add("needs.need_quiet", 0.045 * boundary + 0.02 * hurt - 0.02 * safe)
        add("needs.need_repair", 0.07 * hurt + 0.035 * boundary - 0.045 * repair)
        add("needs.need_expression", 0.04 * has_text + 0.02 * safe)
        add("muscle.readiness", 0.028 * has_text + 0.022 * idle + 0.018 * safe - 0.035 * hurt)
        add("muscle.fatigue", 0.018 * idle + 0.012 * boundary - 0.02 * safe)
        add("immunity.boundary_pressure", 0.065 * boundary + 0.025 * hurt - 0.028 * safe)
        add("immunity.cooldown", 0.025 * idle + 0.018 * boundary - 0.02 * safe)
        add("immunity.interruption_budget", 0.012 * safe + 0.001 * idle)
        add("mortality.load", 0.02 * boundary + 0.015 * hurt + 0.01 * idle - 0.014 * safe)
        add("mortality.exhaustion", 0.016 * idle + 0.012 * boundary - 0.018 * safe)

        return {axis: max(-0.08, min(0.08, value)) for axis, value in delta.items() if abs(value) > 0.0}


def focus_information_flood(
    events: list[dict[str, Any]],
    *,
    max_speakers: int = 3,
    max_events: int = 6,
    interests: dict[str, float] | None = None,
) -> dict[str, Any]:
    clean_events = [processed for event in events if (processed := _flood_event(event, interests=interests))["text"] or processed["flags"]]
    pressure = min(1.0, len(clean_events) / max(1, int(max_events)))
    speakers: dict[str, dict[str, Any]] = {}
    for event in clean_events:
        speaker = event["speaker"]
        bucket = speakers.setdefault(speaker, {"speaker": speaker, "event_count": 0, "urgency": 0.0, "latest": 0.0})
        bucket["event_count"] += 1
        bucket["urgency"] = max(bucket["urgency"], event["urgency"])
        bucket["latest"] = max(bucket["latest"], event["now"])
    ranked_speakers = sorted(
        speakers.values(),
        key=lambda item: (float(item["urgency"]), int(item["event_count"]), float(item["latest"])),
        reverse=True,
    )[: max(1, int(max_speakers))]
    allowed_speakers = {item["speaker"] for item in ranked_speakers}
    selected = sorted(
        [event for event in clean_events if event["speaker"] in allowed_speakers],
        key=lambda event: (event["urgency"], event["now"]),
        reverse=True,
    )[: max(1, int(max_events))]
    return {
        "schema_version": FLOOD_ATTENTION_SCHEMA_VERSION,
        "pressure": round(pressure, 6),
        "speakers": [{"speaker": item["speaker"], "event_count": item["event_count"], "urgency": round(item["urgency"], 6)} for item in ranked_speakers],
        "selected_events": [{"speaker": event["speaker"], "text": event["text"], "flags": event["flags"], "priority": round(event["urgency"], 6), "interest_matches": event["interest_matches"]} for event in selected],
        "deferred_count": max(0, len(clean_events) - len(selected)),
        "interests": {key: _clamp(value) for key, value in (interests or {}).items()},
        "policy": "focus_urgent_speakers_defer_overflow",
    }


def _flood_event(event: dict[str, Any], *, interests: dict[str, float] | None = None) -> dict[str, Any]:
    flags = [str(flag) for flag in event.get("flags", []) if str(flag)]
    confidence = _clamp(float(event.get("confidence") or 0.0))
    text = " ".join(str(event.get("text") or "").split())[:240]
    matches = [key for key in interests or {} if key and key in text]
    interest_boost = min(0.5, sum(_clamp((interests or {})[key]) for key in matches) * 0.25)
    urgency = confidence + interest_boost + (0.7 if "hurt" in flags else 0.0) + (0.6 if "boundary" in flags else 0.0) + (0.3 if "interrupt" in flags or "interruption" in flags else 0.0)
    return {
        "speaker": str(event.get("speaker") or event.get("source") or "unknown")[:80],
        "text": text,
        "flags": flags[:8],
        "confidence": confidence,
        "urgency": min(1.0, urgency),
        "interest_matches": matches[:5],
        "now": float(event.get("now") or 0.0),
    }

def project_attention_delta(result: dict[str, Any]) -> dict[str, float]:
    return dict(result.get("delta") or {})


def attention_delta(state: dict[str, float], event: dict[str, float]) -> dict[str, float]:
    return project_attention_delta(TinyBodyAttention().update(state, event))


__all__ = ["ATTENTION_SCHEMA_VERSION", "FLOOD_ATTENTION_SCHEMA_VERSION", "SPARSE_ATTENTION_ROUTES", "BodyToken", "TinyBodyAttention", "attention_delta", "body_tokens", "focus_information_flood", "project_attention_delta"]
