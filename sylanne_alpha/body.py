from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .attention import attention_delta
from .shadow_memory import (
    SHADOW_MEMORY_SCHEMA_VERSION,
    ShadowMemory,
    shadow_kind as _shadow_kind,
    shadow_summary as _shadow_summary,
    shadow_weight as _shadow_weight,
)
from .vector import EVENT_AXES, STATE_AXES, clamp as _clamp, linear_delta


SCHEMA_VERSION = "sylanne.alpha.body.v1"
RELATIONSHIP_MEMORY_SCHEMA_VERSION = "sylanne.alpha.relationship_memory.v1"


@dataclass(slots=True)
class AlphaPulseState:
    beat: float = 0.0
    rhythm: float = 0.5
    strain: float = 0.0
    last_tick: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {"beat": round(self.beat, 6), "rhythm": round(self.rhythm, 6), "strain": round(self.strain, 6), "last_tick": round(self.last_tick, 6)}


@dataclass(slots=True)
class AlphaBloodflowState:
    warmth: float = 0.4
    circulation: float = 0.0
    memory_flow: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {"warmth": round(self.warmth, 6), "circulation": round(self.circulation, 6), "memory_flow": round(self.memory_flow, 6)}


@dataclass(slots=True)
class AlphaNerveState:
    plasticity: float = 0.0
    sensitivity: float = 0.0
    repetition: int = 0
    threshold_drift: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"plasticity": round(self.plasticity, 6), "sensitivity": round(self.sensitivity, 6), "repetition": self.repetition, "threshold_drift": round(self.threshold_drift, 6)}


@dataclass(slots=True)
class AlphaMuscleState:
    readiness: float = 0.2
    fatigue: float = 0.0
    trained_reach: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {"readiness": round(self.readiness, 6), "fatigue": round(self.fatigue, 6), "trained_reach": round(self.trained_reach, 6)}


@dataclass(slots=True)
class AlphaTemperatureState:
    warmth: float = 0.45
    volatility: float = 0.0
    repair_heat: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {"warmth": round(self.warmth, 6), "volatility": round(self.volatility, 6), "repair_heat": round(self.repair_heat, 6)}


@dataclass(slots=True)
class AlphaWoundState:
    open: float = 0.0
    scar: float = 0.0
    sensitivity: float = 0.0
    repair: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {"open": round(self.open, 6), "scar": round(self.scar, 6), "sensitivity": round(self.sensitivity, 6), "repair": round(self.repair, 6)}


@dataclass(slots=True)
class AlphaImmunityState:
    boundary_pressure: float = 0.0
    sovereignty: float = 1.0
    interruption_budget: float = 1.0
    cooldown: float = 0.0
    paused: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "boundary_pressure": round(self.boundary_pressure, 6),
            "sovereignty": round(self.sovereignty, 6),
            "interruption_budget": round(self.interruption_budget, 6),
            "cooldown": round(self.cooldown, 6),
            "paused": self.paused,
        }


@dataclass(slots=True)
class AlphaMortalityState:
    load: float = 0.0
    exhaustion: float = 0.0
    recovery_debt: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {"load": round(self.load, 6), "exhaustion": round(self.exhaustion, 6), "recovery_debt": round(self.recovery_debt, 6)}


@dataclass(slots=True)
class AlphaBodyState:
    pulse: AlphaPulseState = field(default_factory=AlphaPulseState)
    bloodflow: AlphaBloodflowState = field(default_factory=AlphaBloodflowState)
    nerve: AlphaNerveState = field(default_factory=AlphaNerveState)
    muscle: AlphaMuscleState = field(default_factory=AlphaMuscleState)
    temperature: AlphaTemperatureState = field(default_factory=AlphaTemperatureState)
    wound: AlphaWoundState = field(default_factory=AlphaWoundState)
    immunity: AlphaImmunityState = field(default_factory=AlphaImmunityState)
    mortality: AlphaMortalityState = field(default_factory=AlphaMortalityState)
    needs: dict[str, float] = field(default_factory=lambda: {"need_contact": 0.0, "need_quiet": 0.0, "need_repair": 0.0, "need_expression": 0.0})
    memory: dict[str, Any] = field(default_factory=lambda: {"traces": []})

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AlphaBodyState":
        body = cls()
        for name, state_type in (
            ("pulse", AlphaPulseState),
            ("bloodflow", AlphaBloodflowState),
            ("nerve", AlphaNerveState),
            ("muscle", AlphaMuscleState),
            ("temperature", AlphaTemperatureState),
            ("wound", AlphaWoundState),
            ("immunity", AlphaImmunityState),
            ("mortality", AlphaMortalityState),
        ):
            payload = data.get(name)
            if isinstance(payload, dict):
                setattr(body, name, state_type(**{key: value for key, value in payload.items() if key in state_type.__dataclass_fields__}))
        if isinstance(data.get("needs"), dict):
            body.needs.update({str(key): _clamp(float(value)) for key, value in data["needs"].items()})
        if isinstance(data.get("memory"), dict):
            memory_data = data["memory"]
            traces = memory_data.get("traces", [])
            relationship = memory_data.get("relationship") if isinstance(memory_data.get("relationship"), dict) else {}
            shadow = memory_data.get("shadow") if isinstance(memory_data.get("shadow"), dict) else {}
            events = shadow.get("events", []) if isinstance(shadow.get("events"), list) else []
            body.memory = {
                "traces": [dict(item) for item in traces if isinstance(item, dict)][-50:],
                "relationship": dict(relationship),
                "shadow": {"events": [dict(item) for item in events if isinstance(item, dict)][-24:]},
            }
            memory_system = memory_data.get("_memory_system")
            if isinstance(memory_system, dict):
                body.memory["_memory_system"] = dict(memory_system)
        return body

    def state_vector(self) -> dict[str, float]:
        vector = {
            "pulse.beat": self.pulse.beat,
            "pulse.rhythm": self.pulse.rhythm,
            "pulse.strain": self.pulse.strain,
            "needs.need_contact": self.needs["need_contact"],
            "needs.need_quiet": self.needs["need_quiet"],
            "needs.need_repair": self.needs["need_repair"],
            "needs.need_expression": self.needs["need_expression"],
            "nerve.plasticity": self.nerve.plasticity,
            "nerve.sensitivity": self.nerve.sensitivity,
            "nerve.threshold_drift": self.nerve.threshold_drift,
            "bloodflow.circulation": self.bloodflow.circulation,
            "bloodflow.memory_flow": self.bloodflow.memory_flow,
            "bloodflow.warmth": self.bloodflow.warmth,
            "muscle.trained_reach": self.muscle.trained_reach,
            "muscle.fatigue": self.muscle.fatigue,
            "muscle.readiness": self.muscle.readiness,
            "temperature.warmth": self.temperature.warmth,
            "temperature.volatility": self.temperature.volatility,
            "temperature.repair_heat": self.temperature.repair_heat,
            "wound.open": self.wound.open,
            "wound.repair": self.wound.repair,
            "wound.scar": self.wound.scar,
            "wound.sensitivity": self.wound.sensitivity,
            "immunity.boundary_pressure": self.immunity.boundary_pressure,
            "immunity.cooldown": self.immunity.cooldown,
            "immunity.interruption_budget": self.immunity.interruption_budget,
            "mortality.load": self.mortality.load,
            "mortality.exhaustion": self.mortality.exhaustion,
            "mortality.recovery_debt": self.mortality.recovery_debt,
        }
        return {axis: round(float(vector[axis]), 6) for axis in STATE_AXES}

    def event_vector(self, *, text: str = "", flags: list[str] | None = None, confidence: float = 0.0, elapsed: float = 1.0, repetition: int = 0) -> dict[str, float]:
        flags = list(flags or [])
        clean_text = text.strip()
        vector = {
            "elapsed": max(1.0, min(12.0, float(elapsed))),
            "has_text": 1.0 if clean_text else 0.0,
            "confidence": _clamp(confidence),
            "idle": 1.0 if "idle" in flags and not clean_text else 0.0,
            "safe": 1.0 if "safe" in flags else 0.0,
            "hurt": 1.0 if "hurt" in flags else 0.0,
            "boundary": 1.0 if "boundary" in flags else 0.0,
            "repair": 1.0 if "repair" in flags else 0.0,
            "repetition": float(max(0, repetition)),
        }
        return {axis: vector[axis] for axis in EVENT_AXES}

    def vector_delta(self, event: dict[str, float]) -> dict[str, float]:
        delta = linear_delta(event)
        for axis, value in attention_delta(self.state_vector(), event).items():
            delta[axis] = delta.get(axis, 0.0) + value
        return delta

    def apply_vector_delta(self, delta: dict[str, float], *, now: float = 0.0) -> None:
        self.pulse.beat = max(0.0, self.pulse.beat + delta.get("pulse.beat", 0.0))
        self.pulse.rhythm = _clamp(self.pulse.rhythm + delta.get("pulse.rhythm", 0.0))
        self.pulse.strain = _clamp(self.pulse.strain + delta.get("pulse.strain", 0.0))
        self.pulse.last_tick = now or self.pulse.last_tick + 1.0
        self.needs["need_contact"] = _clamp(self.needs["need_contact"] + delta.get("needs.need_contact", 0.0))
        self.needs["need_quiet"] = _clamp(self.needs["need_quiet"] + delta.get("needs.need_quiet", 0.0))
        self.needs["need_repair"] = _clamp(self.needs["need_repair"] + delta.get("needs.need_repair", 0.0))
        self.needs["need_expression"] = _clamp(self.needs["need_expression"] + delta.get("needs.need_expression", 0.0))
        self.nerve.plasticity = _clamp(self.nerve.plasticity + delta.get("nerve.plasticity", 0.0))
        self.nerve.sensitivity = _clamp(self.nerve.sensitivity + delta.get("nerve.sensitivity", 0.0))
        self.nerve.threshold_drift = _clamp(self.nerve.threshold_drift + delta.get("nerve.threshold_drift", 0.0))
        self.bloodflow.circulation = _clamp(self.bloodflow.circulation + delta.get("bloodflow.circulation", 0.0))
        self.bloodflow.memory_flow = _clamp(self.bloodflow.memory_flow + delta.get("bloodflow.memory_flow", 0.0))
        self.bloodflow.warmth = _clamp(self.bloodflow.warmth + delta.get("bloodflow.warmth", 0.0))
        self.muscle.trained_reach = _clamp(self.muscle.trained_reach + delta.get("muscle.trained_reach", 0.0))
        self.muscle.fatigue = _clamp(self.muscle.fatigue + delta.get("muscle.fatigue", 0.0))
        self.muscle.readiness = _clamp(self.muscle.readiness + delta.get("muscle.readiness", 0.0))
        self.temperature.warmth = _clamp(self.temperature.warmth + delta.get("temperature.warmth", 0.0))
        self.temperature.volatility = _clamp(self.temperature.volatility + delta.get("temperature.volatility", 0.0))
        self.temperature.repair_heat = _clamp(self.temperature.repair_heat + delta.get("temperature.repair_heat", 0.0))
        self.wound.open = _clamp(self.wound.open + delta.get("wound.open", 0.0))
        self.wound.repair = _clamp(self.wound.repair + delta.get("wound.repair", 0.0))
        self.wound.scar = _clamp(self.wound.scar + delta.get("wound.scar", 0.0))
        self.wound.sensitivity = _clamp(self.wound.sensitivity + delta.get("wound.sensitivity", 0.0))
        self.immunity.boundary_pressure = _clamp(self.immunity.boundary_pressure + delta.get("immunity.boundary_pressure", 0.0))
        self.immunity.sovereignty = _clamp(self.immunity.sovereignty + delta.get("immunity.sovereignty", 0.0))
        self.immunity.cooldown = _clamp(self.immunity.cooldown + delta.get("immunity.cooldown", 0.0))
        self.immunity.interruption_budget = _clamp(self.immunity.interruption_budget + delta.get("immunity.interruption_budget", 0.0))
        self.mortality.load = _clamp(self.mortality.load + delta.get("mortality.load", 0.0))
        self.mortality.exhaustion = _clamp(self.mortality.exhaustion + delta.get("mortality.exhaustion", 0.0))
        self.mortality.recovery_debt = _clamp(self.mortality.recovery_debt + delta.get("mortality.recovery_debt", 0.0))
    def simulate_vectors(self, events: list[dict[str, float]]) -> dict[str, float]:
        clone = AlphaBodyState.from_dict(self.to_dict())
        now = clone.pulse.last_tick
        for event in events:
            now += max(1.0, float(event.get("elapsed", 1.0)))
            clone.apply_vector_delta(clone.vector_delta(event), now=now)
        return clone.state_vector()

    def recall_memory(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        terms = {part for part in query.strip().split() if part}
        scored = []
        for trace in self.memory.get("traces", []):
            text = str(trace.get("text") or "")
            overlap = sum(1 for term in terms if term in text)
            exact = 1 if query and query in text else 0
            score = exact + overlap + float(trace.get("weight") or 0.0)
            scored.append((score, trace))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [dict(trace) for _, trace in scored[: max(0, limit)]]

    # Legacy: superseded by MemorySystem
    def decay_memory(self, factor: float = 0.95) -> None:
        factor = _clamp(factor)
        for trace in self.memory.get("traces", []):
            trace["weight"] = round(_clamp(float(trace.get("weight") or 0.0) * factor), 6)

    # Legacy: superseded by MemorySystem
    def compress_memory(self, *, limit: int = 50) -> None:
        traces = [dict(trace) for trace in self.memory.get("traces", [])]
        traces.sort(key=lambda trace: float(trace.get("weight") or 0.0), reverse=True)
        self.memory["traces"] = traces[: max(0, limit)]

    def relationship_memory(self) -> dict[str, Any]:
        relationship = self.memory.setdefault("relationship", {})
        signals = relationship.setdefault("signals", {})
        preference_count = int(signals.get("preference_count") or 0)
        boundary_count = int(signals.get("boundary_count") or 0)
        progress_count = int(signals.get("progress_count") or 0)
        repair_count = int(signals.get("repair_count") or 0)
        event_count = preference_count + boundary_count + progress_count + repair_count
        weight = _clamp(event_count / 12.0)
        phase = "low_signal"
        if weight >= 0.6:
            phase = "active_continuity"
        elif weight >= 0.25:
            phase = "forming_continuity"
        return {
            "schema_version": RELATIONSHIP_MEMORY_SCHEMA_VERSION,
            "kind": "relationship_memory",
            "internal_only": True,
            "read_only": True,
            "public_api_eligible": False,
            "prompt_eligible": event_count > 0,
            "signals": {
                "preference_count": preference_count,
                "boundary_count": boundary_count,
                "progress_count": progress_count,
                "repair_count": repair_count,
            },
            "continuity": {"event_count": event_count, "weight": round(weight, 6), "phase": phase},
            "constraints": ["explicit_signal_counts_only", "no_raw_text", "session_local", "does_not_override_current_user_text"],
        }

    def _observe_relationship_signal(self, *, flags: list[str], text: str) -> None:
        if not text:
            return
        relationship = self.memory.setdefault("relationship", {})
        signals = relationship.setdefault("signals", {})
        for name, markers in {
            "preference_count": {"preference", "style", "like"},
            "boundary_count": {"boundary", "pause"},
            "progress_count": {"progress", "followup", "project"},
            "repair_count": {"repair"},
        }.items():
            if any(marker in flags for marker in markers):
                signals[name] = int(signals.get(name) or 0) + 1

    def shadow_memory(self) -> dict[str, Any]:
        shadow = ShadowMemory.from_raw(self.memory.get("shadow"))
        return shadow.state()

    def observe_shadow_signal(self, *, text: str = "", flags: list[str] | None = None, kind: str = "") -> None:
        shadow = ShadowMemory.from_raw(self.memory.get("shadow"))
        shadow.observe_signal(text=text, flags=flags, kind=kind)
        self.memory["shadow"] = shadow.to_raw()

    def to_dict(self) -> dict[str, Any]:
        shadow = self.memory.get("shadow") if isinstance(self.memory.get("shadow"), dict) else {}
        memory_payload = {
            "traces": list(self.memory.get("traces", []))[-50:],
            "relationship": dict(self.memory.get("relationship") or {}),
            "shadow": {"events": [dict(item) for item in shadow.get("events", []) if isinstance(item, dict)][-24:]},
        }
        memory_system = self.memory.get("_memory_system")
        if isinstance(memory_system, dict):
            memory_payload["_memory_system"] = dict(memory_system)
        return {
            "pulse": self.pulse.to_dict(),
            "bloodflow": self.bloodflow.to_dict(),
            "nerve": self.nerve.to_dict(),
            "muscle": self.muscle.to_dict(),
            "temperature": self.temperature.to_dict(),
            "wound": self.wound.to_dict(),
            "immunity": self.immunity.to_dict(),
            "mortality": self.mortality.to_dict(),
            "needs": {key: round(value, 6) for key, value in self.needs.items()},
            "memory": memory_payload,
        }

    def apply(self, *, text: str = "", flags: list[str] | None = None, confidence: float = 0.0, now: float = 0.0) -> None:
        flags = list(flags or [])
        text = text.strip()
        elapsed = max(0.0, now - self.pulse.last_tick) if now else 1.0
        previous = [str(item.get("text") or "") for item in self.memory.get("traces", [])]
        repetition = previous.count(text) + 1 if text else 0

        event = self.event_vector(text=text, flags=flags, confidence=confidence, elapsed=elapsed, repetition=repetition)
        self.apply_vector_delta(self.vector_delta(event), now=now)
        self.nerve.repetition = repetition

        self.muscle.fatigue = _clamp(self.muscle.fatigue + (0.06 if self.needs["need_contact"] > 0.65 else 0.0))
        self.muscle.readiness = _clamp(0.2 + self.muscle.trained_reach + self.needs["need_expression"] - self.muscle.fatigue)
        self.wound.repair = _clamp(self.wound.repair + (0.02 if self.wound.open > 0.0 and "repair" not in flags else 0.0))
        self.wound.scar = _clamp(self.wound.scar + max(0.0, self.wound.open - self.wound.repair) * 0.05)
        self.wound.sensitivity = _clamp(self.wound.sensitivity + self.wound.scar * 0.02)
        self.immunity.paused = "pause" in flags or self.immunity.paused and "resume" not in flags
        if "reset" in flags:
            self.immunity.interruption_budget = 1.0
            self.immunity.cooldown = 0.0
            self.immunity.paused = False
        target_flow = _clamp(len(self.memory.get("traces", [])) / 50.0 + self.nerve.plasticity * 0.2)
        self.bloodflow.memory_flow = _clamp(self.bloodflow.memory_flow * 0.9 + target_flow * 0.1)

        if text:
            self.memory.setdefault("traces", []).append({"id": f"trace-{len(self.memory.get('traces', [])) + 1}", "text": text[:500], "weight": round(_clamp(0.35 + repetition * 0.08), 6), "temperature": self.temperature.to_dict()["warmth"]})
            self.memory["traces"] = self.memory["traces"][-50:]
            self._observe_relationship_signal(flags=flags, text=text)
            self.observe_shadow_signal(text=text, flags=flags)


