from __future__ import annotations

from typing import Any

COMPAT_SCHEMA_VERSION = "sylanne.alpha.compat.v1"
MEMORY_SCHEMA_VERSION = "sylanne.alpha.compat.memory.v1"

SLICE_LABELS = {
    "emotion": "body affect surface",
    "emotion_model": "alpha body computation model",
    "emotion_effects": "body consequence surface",
    "psych_state": "risk and boundary screening",
    "humanlike_state": "nonhuman body expressiveness",
    "lifelike_state": "life rhythm and agency",
    "personality_drift_state": "plasticity and adaptation",
    "moral_repair_state": "wound and repair state",
    "integrated_self": "bounded integrated self summary",
    "shadow_diagnostics": "readonly shadow diagnostics",
    "fallibility_state": "fallibility and recovery state",
}


def command_surface(host: Any, slice_name: str) -> dict[str, Any]:
    surface = host.diagnostics()
    body = surface["body"]
    decision = surface["decision"]
    guard = surface["guard"]
    values = _slice_values(slice_name, body, surface)
    payload = {
        "schema_version": COMPAT_SCHEMA_VERSION,
        "session_key": surface["session_key"],
        "slice": slice_name,
        "summary": _summary(slice_name, body, decision, guard),
        "values": values,
        "decision": {
            "action": decision["action"],
            "reason_code": decision.get("reason_code", "life_rhythm"),
            "allowed": guard["allowed"],
        },
        "prompt_fragment": surface["host_payload"]["prompt_fragment"],
        "visibility": "diagnostic_readonly"
        if slice_name in {"integrated_self", "shadow_diagnostics"}
        else "public_surface",
    }
    if slice_name == "shadow_diagnostics":
        payload.pop("prompt_fragment", None)
    return payload


def reset_surface(host: Any, slice_name: str) -> dict[str, Any]:
    host.kernel.body = type(host.kernel.body)()
    host.kernel.computation.from_dict({})
    host.kernel.last_decision = host.kernel._decide()
    host.kernel.last_guard = host.kernel._guard(host.kernel.last_decision)
    host.runtime.save(host.kernel)
    payload = command_surface(host, slice_name)
    payload["reset"] = True
    return payload


def memory_surface(host: Any, query: str = "", limit: int = 5) -> dict[str, Any]:
    surface = host.diagnostics()
    matches = (
        host.kernel.body.recall_memory(query, limit=limit)
        if query
        else list(surface["body"]["memory"]["traces"])[-limit:]
    )
    return {
        "schema_version": MEMORY_SCHEMA_VERSION,
        "session_key": surface["session_key"],
        "slice": "sylanne_memory",
        "query": query,
        "matches": matches,
        "count": len(matches),
        "summary": f"Sylanne memory returned {len(matches)} trace(s).",
        "visibility": "public_surface",
    }


def _slice_values(
    slice_name: str, body: dict[str, Any], surface: dict[str, Any]
) -> dict[str, Any]:
    needs = body["needs"]
    diagnostics = surface["diagnostics"]
    if slice_name in {"emotion", "emotion_model", "emotion_effects"}:
        return {
            "warmth": body["temperature"]["warmth"],
            "pulse": body["pulse"]["rhythm"],
            "expression": needs["need_expression"],
            "repair": needs["need_repair"],
            "effects": {
                "contact_need": needs["need_contact"],
                "quiet_need": needs["need_quiet"],
                "risk": diagnostics["risk"]["score"],
            },
        }
    if slice_name == "psych_state":
        return {
            "risk": diagnostics["risk"],
            "boundary": diagnostics["boundary"],
            "mortality": body["mortality"],
        }
    if slice_name == "humanlike_state":
        return {
            "muscle": body["muscle"],
            "temperature": body["temperature"],
            "expression": needs["need_expression"],
        }
    if slice_name == "lifelike_state":
        return {"pulse": body["pulse"], "needs": needs, "agency": diagnostics["agency"]}
    if slice_name == "personality_drift_state":
        return {
            "nerve": body["nerve"],
            "plasticity": diagnostics["vector_summary"]["plasticity"],
        }
    if slice_name == "moral_repair_state":
        return {"wound": body["wound"], "repair_need": needs["need_repair"]}
    if slice_name == "fallibility_state":
        return {
            "mortality": body["mortality"],
            "wound": body["wound"],
            "recovery": body["mortality"]["recovery_debt"],
        }
    if slice_name == "integrated_self":
        return {
            "summary_state": diagnostics["vector_summary"],
            "agency": diagnostics["agency"],
            "boundary": diagnostics["boundary"],
        }
    if slice_name == "shadow_diagnostics":
        shadow = surface["host_payload"].get("shadow_memory", {})
        return {
            "signals": shadow.get("signals", {}),
            "state_index": shadow.get("state_index", {}),
            "memory_gate": shadow.get("memory_gate", {}),
            "risk": diagnostics["risk"],
            "guard_flags": diagnostics["boundary"]["guard_flags"],
        }
    return {"body": body}


def _summary(
    slice_name: str,
    body: dict[str, Any],
    decision: dict[str, Any],
    guard: dict[str, Any],
) -> str:
    label = SLICE_LABELS.get(slice_name, slice_name)
    return f"{label}: action={decision['action']}; allowed={guard['allowed']}; warmth={body['temperature']['warmth']:.2f}."
