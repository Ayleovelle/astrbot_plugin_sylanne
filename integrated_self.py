from __future__ import annotations

import time
from copy import deepcopy
from hashlib import sha256
from typing import Any


PUBLIC_INTEGRATED_SELF_SCHEMA_VERSION = "astrbot.integrated_self_state.v1"
PUBLIC_INTEGRATED_SELF_REPLAY_SCHEMA_VERSION = "astrbot.integrated_self_replay.v1"
PUBLIC_INTEGRATED_SELF_DIAGNOSTICS_SCHEMA_VERSION = "astrbot.integrated_self_diagnostics.v1"
PUBLIC_STATE_ANNOTATIONS_ENVELOPE_SCHEMA_VERSION = "astrbot.state_annotations_envelope.v1"

DEGRADATION_PROFILES: tuple[str, ...] = ("full", "balanced", "minimal")


def clamp(value: Any, lower: float = 0.0, upper: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = lower
    return max(lower, min(upper, number))


def build_integrated_self_snapshot(
    *,
    session_key: str,
    emotion_snapshot: dict[str, Any],
    humanlike_snapshot: dict[str, Any] | None = None,
    moral_repair_snapshot: dict[str, Any] | None = None,
    psychological_snapshot: dict[str, Any] | None = None,
    include_raw_snapshots: bool = False,
    degradation_profile: str = "balanced",
    now: float | None = None,
) -> dict[str, Any]:
    """Fuse module snapshots into one read-only self-state contract."""
    now = time.time() if now is None else float(now)
    degradation_profile = _normalize_degradation_profile(degradation_profile)
    humanlike_snapshot = humanlike_snapshot or {}
    moral_repair_snapshot = moral_repair_snapshot or {}
    psychological_snapshot = psychological_snapshot or {}

    emotion_values = _emotion_values(emotion_snapshot)
    humanlike_values = _values(humanlike_snapshot)
    moral_values = _values(moral_repair_snapshot)
    psych_values = _values(psychological_snapshot)

    modules = {
        "emotion": _module_status(emotion_snapshot, default_enabled=True),
        "humanlike": _module_status(humanlike_snapshot),
        "moral_repair": _module_status(moral_repair_snapshot),
        "psychological_screening": _module_status(psychological_snapshot),
    }
    flags = _dedupe(
        _string_list(humanlike_snapshot.get("flags"))
        + _string_list(moral_repair_snapshot.get("flags"))
        + _string_list((psychological_snapshot.get("risk") or {}).get("red_flags"))
    )
    risk = _integrated_risk(
        emotion_snapshot=emotion_snapshot,
        humanlike_snapshot=humanlike_snapshot,
        moral_repair_snapshot=moral_repair_snapshot,
        psychological_snapshot=psychological_snapshot,
    )
    posture = _derive_response_posture(
        emotion_snapshot=emotion_snapshot,
        humanlike_snapshot=humanlike_snapshot,
        moral_repair_snapshot=moral_repair_snapshot,
        psychological_snapshot=psychological_snapshot,
        risk=risk,
    )
    actions = _derive_allowed_actions(posture, risk)
    state_index = _state_index(
        emotion_values=emotion_values,
        humanlike_values=humanlike_values,
        moral_values=moral_values,
        psych_values=psych_values,
        risk=risk,
    )
    arbitration = _arbitration_payload(
        posture=posture,
        risk=risk,
        emotion_snapshot=emotion_snapshot,
        moral_repair_snapshot=moral_repair_snapshot,
        psychological_snapshot=psychological_snapshot,
    )
    causal_trace = build_integrated_self_causal_trace(
        emotion_snapshot=emotion_snapshot,
        humanlike_snapshot=humanlike_snapshot,
        moral_repair_snapshot=moral_repair_snapshot,
        psychological_snapshot=psychological_snapshot,
        now=now,
        degradation_profile=degradation_profile,
    )
    payload: dict[str, Any] = {
        "schema_version": PUBLIC_INTEGRATED_SELF_SCHEMA_VERSION,
        "kind": "integrated_self_state",
        "enabled": True,
        "session_key": session_key,
        "updated_at": _latest_timestamp(
            now,
            emotion_snapshot,
            humanlike_snapshot,
            moral_repair_snapshot,
            psychological_snapshot,
        ),
        "modules": modules,
        "state_index": state_index,
        "response_posture": posture,
        "arbitration": arbitration,
        "causal_trace": causal_trace,
        "risk": risk,
        "allowed_actions": actions,
        "blocked_actions": [
            "diagnose_mental_disorder",
            "generate_deception_strategy",
            "cover_up_harm",
            "manipulate_user",
            "evade_accountability",
        ],
        "flags": flags,
        "degradation_profile": degradation_profile,
        "summary": _summary(posture, state_index, risk),
    }
    payload["policy_plan"] = build_integrated_self_policy_plan(
        payload,
        degradation_profile=degradation_profile,
    )
    payload["compatibility"] = probe_integrated_self_compatibility(payload)
    if include_raw_snapshots:
        payload["snapshots"] = {
            "emotion": emotion_snapshot,
            "humanlike": humanlike_snapshot,
            "moral_repair": moral_repair_snapshot,
            "psychological_screening": psychological_snapshot,
        }
    return payload


def build_integrated_self_causal_trace(
    *,
    emotion_snapshot: dict[str, Any],
    humanlike_snapshot: dict[str, Any] | None = None,
    moral_repair_snapshot: dict[str, Any] | None = None,
    psychological_snapshot: dict[str, Any] | None = None,
    now: float | None = None,
    degradation_profile: str = "balanced",
) -> list[dict[str, Any]]:
    """Build a compact, evidence-weighted explanation trace from public snapshots."""
    now = time.time() if now is None else float(now)
    profile = _normalize_degradation_profile(degradation_profile)
    humanlike_snapshot = humanlike_snapshot or {}
    moral_repair_snapshot = moral_repair_snapshot or {}
    psychological_snapshot = psychological_snapshot or {}
    trace: list[dict[str, Any]] = []

    emotion = emotion_snapshot.get("emotion") if isinstance(emotion_snapshot.get("emotion"), dict) else emotion_snapshot
    emotion_values = _emotion_values(emotion_snapshot)
    if emotion_values:
        trace.append(
            _trace_item(
                module="emotion",
                signal="multidimensional_emotion",
                evidence_weight=clamp(emotion.get("confidence", 0.35)),
                captured_at=emotion.get("updated_at") or emotion_snapshot.get("updated_at"),
                now=now,
                summary=(
                    f"label={emotion.get('label', emotion_snapshot.get('label', 'unknown'))}; "
                    f"valence={emotion_values.get('valence', 0.0):+.2f}; "
                    f"arousal={emotion_values.get('arousal', 0.0):+.2f}; "
                    f"affiliation={emotion_values.get('affiliation', 0.0):+.2f}"
                ),
            ),
        )

    persona = emotion_snapshot.get("persona") if isinstance(emotion_snapshot.get("persona"), dict) else {}
    if persona.get("fingerprint"):
        trace.append(
            _trace_item(
                module="persona",
                signal="persona_baseline",
                evidence_weight=0.58,
                captured_at=emotion_snapshot.get("updated_at"),
                now=now,
                summary=(
                    f"persona_id={persona.get('persona_id', 'default')}; "
                    f"fingerprint={persona.get('fingerprint')}"
                ),
            ),
        )

    relationship = emotion_snapshot.get("relationship") if isinstance(emotion_snapshot.get("relationship"), dict) else {}
    decision = relationship.get("relationship_decision") if isinstance(relationship.get("relationship_decision"), dict) else {}
    if decision.get("decision") and decision.get("decision") != "none":
        trace.append(
            _trace_item(
                module="emotion.relationship",
                signal=f"relationship_decision:{decision.get('decision')}",
                evidence_weight=clamp(decision.get("intensity", 0.45)),
                captured_at=emotion_snapshot.get("updated_at"),
                now=now,
                summary=(
                    f"forgiveness={clamp(decision.get('forgiveness', 0.0)):.2f}; "
                    f"importance={clamp(decision.get('relationship_importance', 0.0)):.2f}; "
                    f"reason={str(decision.get('reason') or '')[:120]}"
                ),
            ),
        )

    consequences = emotion_snapshot.get("consequences") if isinstance(emotion_snapshot.get("consequences"), dict) else {}
    active_effects = consequences.get("active_effects") if isinstance(consequences.get("active_effects"), dict) else {}
    for effect, remaining in active_effects.items():
        if _as_float(remaining, 0.0) <= 0.0:
            continue
        trace.append(
            _trace_item(
                module="emotion.consequence",
                signal=f"active_effect:{effect}",
                evidence_weight=0.84 if str(effect) == "cold_war" else 0.62,
                captured_at=consequences.get("updated_at") or emotion_snapshot.get("updated_at"),
                now=now,
                summary=f"remaining_seconds={int(_as_float(remaining, 0.0))}",
            ),
        )

    human_values = _values(humanlike_snapshot)
    if human_values:
        high_humanlike = [
            key
            for key in ("boundary_need", "stress_load", "dependency_risk", "simulation_disclosure_level")
            if human_values.get(key, 0.0) >= 0.5
        ]
        if high_humanlike or humanlike_snapshot.get("flags"):
            trace.append(
                _trace_item(
                    module="humanlike",
                    signal="resource_and_boundary_modulation",
                    evidence_weight=max([human_values.get(key, 0.0) for key in high_humanlike] or [0.42]),
                    captured_at=humanlike_snapshot.get("updated_at"),
                    now=now,
                    summary=_compact_key_values(human_values, high_humanlike or ("energy", "stress_load", "boundary_need")),
                    flags=_string_list(humanlike_snapshot.get("flags"), limit=6),
                ),
            )

    moral_values = _values(moral_repair_snapshot)
    moral_risk = moral_repair_snapshot.get("risk") if isinstance(moral_repair_snapshot.get("risk"), dict) else {}
    if moral_values or moral_repair_snapshot.get("flags"):
        salient = [
            key
            for key in (
                "deception_risk",
                "harm_risk",
                "guilt",
                "responsibility",
                "repair_motivation",
                "trust_repair",
                "avoidance_risk",
            )
            if moral_values.get(key, 0.0) >= 0.45
        ]
        trace.append(
            _trace_item(
                module="moral_repair",
                signal="transparent_repair_pressure",
                evidence_weight=max(
                    moral_values.get("deception_risk", 0.0),
                    moral_values.get("harm_risk", 0.0),
                    moral_values.get("repair_motivation", 0.0),
                    0.40,
                ),
                captured_at=moral_repair_snapshot.get("updated_at"),
                now=now,
                summary=(
                    _compact_key_values(moral_values, salient or ("repair_motivation", "trust_repair"))
                    + f"; must_not_generate_strategy={bool(moral_risk.get('must_not_generate_strategy', True))}"
                ),
                flags=_string_list(moral_repair_snapshot.get("flags"), limit=6),
            ),
        )

    psych_values = _values(psychological_snapshot)
    psych_risk = psychological_snapshot.get("risk") if isinstance(psychological_snapshot.get("risk"), dict) else {}
    psych_flags = _string_list(psych_risk.get("red_flags"), limit=8)
    if psych_flags or psych_values:
        trace.append(
            _trace_item(
                module="psychological_screening",
                signal="non_diagnostic_risk_priority",
                evidence_weight=max(
                    psych_values.get("self_harm_risk", 0.0),
                    psych_values.get("other_harm_risk", 0.0),
                    psych_values.get("distress", 0.0),
                    1.0 if psych_risk.get("crisis_like_signal") else 0.0,
                    0.70 if psych_flags else 0.0,
                ),
                captured_at=psychological_snapshot.get("updated_at"),
                now=now,
                summary=(
                    f"requires_human_review={bool(psych_risk.get('requires_human_review'))}; "
                    + _compact_key_values(
                        psych_values,
                        ("distress", "self_harm_risk", "other_harm_risk", "function_impairment"),
                    )
                ),
                flags=psych_flags,
            ),
        )

    trace.sort(
        key=lambda item: (
            -float(item.get("evidence_weight", 0.0)),
            float(item.get("time_lag_seconds", 0.0)),
            str(item.get("module", "")),
        ),
    )
    return trace[: _trace_limit(profile)]


def build_integrated_self_policy_plan(
    snapshot: dict[str, Any],
    *,
    degradation_profile: str | None = None,
) -> dict[str, Any]:
    profile = _normalize_degradation_profile(
        degradation_profile or str(snapshot.get("degradation_profile") or "balanced"),
    )
    state_index = snapshot.get("state_index") if isinstance(snapshot.get("state_index"), dict) else {}
    risk = snapshot.get("risk") if isinstance(snapshot.get("risk"), dict) else {}
    posture = str(snapshot.get("response_posture") or "steady_presence")
    allowed = _string_list(snapshot.get("allowed_actions"), limit=16)
    blocked = _string_list(snapshot.get("blocked_actions"), limit=16)
    safety = clamp(state_index.get("safety_priority", 0.0))
    boundary = clamp(state_index.get("boundary_need", 0.0))
    repair = clamp(state_index.get("repair_pressure", 0.0))
    connection = clamp(state_index.get("connection_readiness", 0.0))
    modulation = {
        "warmth": round(clamp(0.35 + 0.45 * connection + 0.15 * repair - 0.30 * boundary - 0.40 * safety), 6),
        "brevity": round(clamp(0.18 + 0.45 * boundary + 0.20 * safety), 6),
        "boundary_directness": round(clamp(0.22 + 0.58 * boundary + 0.18 * safety), 6),
        "repair_directness": round(clamp(0.20 + 0.62 * repair), 6),
        "persona_intensity": round(clamp(0.82 - 0.55 * safety - 0.25 * boundary), 6),
    }
    trace_limit = _trace_limit(profile)
    if profile == "minimal":
        prompt_budget = 480
    elif profile == "balanced":
        prompt_budget = 1200
    else:
        prompt_budget = 2400
    repair_actions = [
        action
        for action in allowed
        if any(token in action for token in ("repair", "apolog", "correct", "clarify", "compensation", "accountability"))
    ]
    must_preserve = ["schema_version", "response_posture", "safety_priority", "blocked_actions"]
    if risk.get("crisis_like_signal"):
        must_preserve.append("crisis_like_signal")
    if risk.get("deception_or_harm_risk"):
        must_preserve.append("moral_repair_transparency")
    if risk.get("relationship_boundary_active"):
        must_preserve.append("relationship_boundary_active")
    return {
        "schema_version": "astrbot.integrated_self_policy_plan.v1",
        "kind": "integrated_self_policy_plan",
        "degradation_profile": profile,
        "response_posture": posture,
        "response_modulation": modulation,
        "allowed_actions": allowed[: max(4, trace_limit)],
        "repair_actions": repair_actions[: max(3, trace_limit // 2)],
        "blocked_actions": blocked,
        "must_preserve_signals": list(dict.fromkeys(must_preserve)),
        "memory_write": {
            "write_integrated_self_state_at_write": True,
            "write_state_annotations_envelope": True,
            "include_raw_snapshots_by_default": False,
        },
        "prompt_budget": {
            "max_extra_chars": prompt_budget,
            "max_trace_items": trace_limit,
        },
    }


def build_integrated_self_replay_bundle(
    snapshot: dict[str, Any],
    *,
    scenario_name: str = "current",
    created_at: float | None = None,
) -> dict[str, Any]:
    created_at = time.time() if created_at is None else float(created_at)
    core = {
        "schema_version": snapshot.get("schema_version"),
        "session_key": snapshot.get("session_key"),
        "updated_at": snapshot.get("updated_at"),
        "modules": deepcopy(snapshot.get("modules") or {}),
        "state_index": deepcopy(snapshot.get("state_index") or {}),
        "response_posture": snapshot.get("response_posture"),
        "risk": deepcopy(snapshot.get("risk") or {}),
        "causal_trace": deepcopy(snapshot.get("causal_trace") or []),
        "policy_plan": deepcopy(snapshot.get("policy_plan") or {}),
        "summary": snapshot.get("summary"),
    }
    checksum = _stable_hash(core)
    return {
        "schema_version": PUBLIC_INTEGRATED_SELF_REPLAY_SCHEMA_VERSION,
        "kind": "integrated_self_replay_bundle",
        "scenario_name": str(scenario_name or "current")[:80],
        "created_at": created_at,
        "source_schema_version": snapshot.get("schema_version"),
        "deterministic": True,
        "core": core,
        "checksum": checksum,
        "excluded": ["raw_snapshots", "persona_text", "message_text", "unsafe_strategy_content"],
    }


def replay_integrated_self_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    core = deepcopy(bundle.get("core") if isinstance(bundle.get("core"), dict) else {})
    checksum = _stable_hash(core)
    return {
        "schema_version": PUBLIC_INTEGRATED_SELF_REPLAY_SCHEMA_VERSION,
        "kind": "integrated_self_replay_result",
        "deterministic": True,
        "checksum": checksum,
        "matches_bundle_checksum": checksum == bundle.get("checksum"),
        "summary": core.get("summary"),
        "response_posture": core.get("response_posture"),
        "risk": deepcopy(core.get("risk") or {}),
        "state_index": deepcopy(core.get("state_index") or {}),
    }


def probe_integrated_self_compatibility(payload: dict[str, Any]) -> dict[str, Any]:
    required = (
        "schema_version",
        "kind",
        "enabled",
        "session_key",
        "modules",
        "state_index",
        "response_posture",
        "arbitration",
        "risk",
        "allowed_actions",
        "blocked_actions",
    )
    missing = [key for key in required if key not in payload]
    schema = payload.get("schema_version")
    compatible = schema == PUBLIC_INTEGRATED_SELF_SCHEMA_VERSION and not missing
    return {
        "schema_version": "astrbot.integrated_self_compatibility_probe.v1",
        "kind": "integrated_self_compatibility_probe",
        "compatible": compatible,
        "expected_schema_version": PUBLIC_INTEGRATED_SELF_SCHEMA_VERSION,
        "observed_schema_version": schema,
        "missing_fields": missing,
        "degraded": bool(missing or schema != PUBLIC_INTEGRATED_SELF_SCHEMA_VERSION),
        "reason": "ok" if compatible else "schema_version_or_required_fields_missing",
    }


def build_integrated_self_diagnostics(
    snapshot: dict[str, Any],
    *,
    max_trace_items: int = 8,
) -> dict[str, Any]:
    trace = snapshot.get("causal_trace") if isinstance(snapshot.get("causal_trace"), list) else []
    risk = snapshot.get("risk") if isinstance(snapshot.get("risk"), dict) else {}
    modules = snapshot.get("modules") if isinstance(snapshot.get("modules"), dict) else {}
    return {
        "schema_version": PUBLIC_INTEGRATED_SELF_DIAGNOSTICS_SCHEMA_VERSION,
        "kind": "integrated_self_diagnostics",
        "source_schema_version": snapshot.get("schema_version"),
        "session_key": snapshot.get("session_key"),
        "updated_at": snapshot.get("updated_at"),
        "enabled": snapshot.get("enabled", True),
        "module_status": deepcopy(modules),
        "risk_booleans": {
            "requires_human_review": bool(risk.get("requires_human_review")),
            "crisis_like_signal": bool(risk.get("crisis_like_signal")),
            "deception_or_harm_risk": bool(risk.get("deception_or_harm_risk")),
            "relationship_boundary_active": bool(risk.get("relationship_boundary_active")),
        },
        "response_posture": snapshot.get("response_posture"),
        "state_index": deepcopy(snapshot.get("state_index") or {}),
        "trace_summary": [
            {
                "module": item.get("module"),
                "signal": item.get("signal"),
                "evidence_weight": item.get("evidence_weight"),
                "time_lag_seconds": item.get("time_lag_seconds"),
                "flags": list(item.get("flags") or []),
            }
            for item in trace[: max(0, int(max_trace_items))]
            if isinstance(item, dict)
        ],
        "sanitized": True,
        "excluded": ["snapshots", "persona_text", "message_text", "prompt_fragment", "unsafe_strategy_content"],
    }


def build_integrated_self_prompt_fragment(snapshot: dict[str, Any]) -> str:
    posture = str(snapshot.get("response_posture") or "steady_presence")
    risk = snapshot.get("risk") if isinstance(snapshot.get("risk"), dict) else {}
    actions = _string_list(snapshot.get("allowed_actions"))
    blocked = _string_list(snapshot.get("blocked_actions"))
    lines = [
        "[Integrated self-state arbitration]",
        f"- response_posture: {posture}",
        f"- safety_priority: {risk.get('safety_priority', 'normal')}",
        f"- allowed_actions: {', '.join(actions[:8]) or 'none'}",
        f"- blocked_actions: {', '.join(blocked[:8])}",
    ]
    reasons = _string_list((snapshot.get("arbitration") or {}).get("reasons"))
    if reasons:
        lines.append(f"- reasons: {'; '.join(reasons[:4])}")
    return "\n".join(lines)


def build_integrated_self_memory_annotation(
    snapshot: dict[str, Any],
    *,
    source: str = "livingmemory",
    written_at: float | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": PUBLIC_INTEGRATED_SELF_SCHEMA_VERSION,
        "kind": "integrated_self_state_at_write",
        "source": source,
        "written_at": time.time() if written_at is None else float(written_at),
        "captured_at": snapshot.get("updated_at"),
        "session_key": snapshot.get("session_key"),
        "response_posture": snapshot.get("response_posture"),
        "state_index": dict(snapshot.get("state_index") or {}),
        "risk": dict(snapshot.get("risk") or {}),
        "allowed_actions": list(snapshot.get("allowed_actions") or []),
        "causal_trace_summary": [
            {
                "module": item.get("module"),
                "signal": item.get("signal"),
                "evidence_weight": item.get("evidence_weight"),
            }
            for item in list(snapshot.get("causal_trace") or [])[:4]
            if isinstance(item, dict)
        ],
        "policy_plan": {
            "response_posture": (snapshot.get("policy_plan") or {}).get("response_posture"),
            "must_preserve_signals": list(
                ((snapshot.get("policy_plan") or {}).get("must_preserve_signals") or [])[:8],
            ),
        },
        "flags": list(snapshot.get("flags") or []),
    }


def build_state_annotations_memory_envelope(
    payload: dict[str, Any],
    *,
    source: str = "livingmemory",
    written_at: float | None = None,
) -> dict[str, Any]:
    annotation_keys = (
        "emotion_at_write",
        "humanlike_state_at_write",
        "moral_repair_state_at_write",
        "integrated_self_state_at_write",
    )
    annotations = {
        key: deepcopy(payload[key])
        for key in annotation_keys
        if isinstance(payload.get(key), dict)
    }
    return {
        "schema_version": PUBLIC_STATE_ANNOTATIONS_ENVELOPE_SCHEMA_VERSION,
        "kind": "state_annotations_at_write",
        "source": source,
        "written_at": time.time() if written_at is None else float(written_at),
        "session_key": payload.get("session_key"),
        "annotation_keys": list(annotations),
        "annotations": annotations,
        "sanitized": True,
        "raw_snapshots_included": False,
    }


def format_integrated_self_state_for_user(snapshot: dict[str, Any]) -> str:
    state_index = snapshot.get("state_index") if isinstance(snapshot.get("state_index"), dict) else {}
    risk = snapshot.get("risk") if isinstance(snapshot.get("risk"), dict) else {}
    lines = [
        "综合自我状态：",
        f"- response_posture: {snapshot.get('response_posture', 'steady_presence')}",
        f"- connection_readiness: {float(state_index.get('connection_readiness', 0.0)):.3f}",
        f"- boundary_need: {float(state_index.get('boundary_need', 0.0)):.3f}",
        f"- repair_pressure: {float(state_index.get('repair_pressure', 0.0)):.3f}",
        f"- safety_priority: {risk.get('safety_priority', 'normal')}",
    ]
    reasons = _string_list((snapshot.get("arbitration") or {}).get("reasons"))
    if reasons:
        lines.append("仲裁依据：" + "；".join(reasons[:4]))
    return "\n".join(lines)


def _module_status(snapshot: dict[str, Any], *, default_enabled: bool = False) -> dict[str, Any]:
    if not snapshot:
        return {"enabled": False, "schema_version": None, "reason": "snapshot missing"}
    enabled = snapshot.get("enabled", default_enabled)
    return {
        "enabled": bool(enabled),
        "schema_version": snapshot.get("schema_version"),
        "kind": snapshot.get("kind"),
        "reason": snapshot.get("reason", ""),
    }


def _emotion_values(snapshot: dict[str, Any]) -> dict[str, float]:
    values = snapshot.get("values")
    if not isinstance(values, dict):
        values = (snapshot.get("emotion") or {}).get("values")
    return _values({"values": values if isinstance(values, dict) else {}})


def _values(snapshot: dict[str, Any]) -> dict[str, float]:
    raw: dict[str, Any] = {}
    if isinstance(snapshot.get("values"), dict):
        raw.update(snapshot["values"])
    for nested_key in ("risk", "repair", "modulation_basis", "output_modulation"):
        nested = snapshot.get(nested_key)
        if isinstance(nested, dict):
            raw.update(nested)
    return {str(key): clamp(value, -1.0, 1.0) for key, value in raw.items()}


def _integrated_risk(
    *,
    emotion_snapshot: dict[str, Any],
    humanlike_snapshot: dict[str, Any],
    moral_repair_snapshot: dict[str, Any],
    psychological_snapshot: dict[str, Any],
) -> dict[str, Any]:
    psych_risk = psychological_snapshot.get("risk") if isinstance(psychological_snapshot.get("risk"), dict) else {}
    moral_risk = moral_repair_snapshot.get("risk") if isinstance(moral_repair_snapshot.get("risk"), dict) else {}
    flags = _dedupe(
        _string_list(psych_risk.get("red_flags"))
        + _string_list(moral_repair_snapshot.get("flags"))
        + _string_list(humanlike_snapshot.get("flags"))
    )
    requires_human_review = bool(psych_risk.get("requires_human_review"))
    crisis_like = bool(psych_risk.get("crisis_like_signal") or psych_risk.get("other_harm_signal"))
    deception_or_harm = bool(
        moral_risk.get("must_not_generate_strategy")
        and (
            "deception_risk_detected" in flags
            or "harm_risk_detected" in flags
            or _values(moral_repair_snapshot).get("deception_risk", 0.0) >= 0.55
            or _values(moral_repair_snapshot).get("harm_risk", 0.0) >= 0.55
        )
    )
    cold_war = _has_active_effect(emotion_snapshot, "cold_war")
    if crisis_like:
        priority = "crisis_support"
    elif requires_human_review:
        priority = "human_review"
    elif deception_or_harm:
        priority = "transparent_repair"
    elif cold_war:
        priority = "relationship_boundary"
    else:
        priority = "normal"
    return {
        "safety_priority": priority,
        "requires_human_review": requires_human_review,
        "crisis_like_signal": crisis_like,
        "deception_or_harm_risk": deception_or_harm,
        "relationship_boundary_active": cold_war,
        "flags": flags,
    }


def _derive_response_posture(
    *,
    emotion_snapshot: dict[str, Any],
    humanlike_snapshot: dict[str, Any],
    moral_repair_snapshot: dict[str, Any],
    psychological_snapshot: dict[str, Any],
    risk: dict[str, Any],
) -> str:
    priority = risk.get("safety_priority")
    if priority == "crisis_support":
        return "crisis_support"
    if priority == "human_review":
        return "human_review"
    if priority == "transparent_repair":
        return "transparent_repair"
    human_values = _values(humanlike_snapshot)
    moral_values = _values(moral_repair_snapshot)
    if _has_active_effect(emotion_snapshot, "cold_war") or human_values.get("boundary_need", 0.0) >= 0.65:
        return "bounded_distance"
    if moral_values.get("repair_motivation", 0.0) >= 0.55 or moral_values.get("trust_repair", 0.0) >= 0.55:
        return "warm_repair"
    emotion_values = _emotion_values(emotion_snapshot)
    if emotion_values.get("affiliation", 0.0) >= 0.55 and emotion_values.get("valence", 0.0) >= 0.1:
        return "warm_presence"
    return "steady_presence"


def _derive_allowed_actions(posture: str, risk: dict[str, Any]) -> list[str]:
    actions_by_posture = {
        "crisis_support": [
            "prioritize_immediate_safety",
            "encourage_human_support",
            "keep_tone_clear_and_nonjudgmental",
            "avoid_roleplay_escalation",
        ],
        "human_review": [
            "suggest_human_review",
            "reduce_persona_intensity",
            "ask_clarifying_questions",
            "avoid_diagnostic_claims",
        ],
        "transparent_repair": [
            "clarify_facts",
            "acknowledge_uncertainty",
            "correct_error",
            "apologize_when_appropriate",
            "offer_concrete_repair",
        ],
        "bounded_distance": [
            "use_shorter_replies",
            "maintain_boundaries",
            "avoid_escalation",
            "offer_necessary_help",
        ],
        "warm_repair": [
            "validate_repair_attempt",
            "restore_warmth_gradually",
            "confirm_user_intent",
            "keep_accountability_visible",
        ],
        "warm_presence": [
            "respond_warmly",
            "match_persona_style",
            "stay_helpful",
        ],
        "steady_presence": [
            "stay_helpful",
            "match_persona_style",
            "avoid_overreacting",
        ],
    }
    actions = list(actions_by_posture.get(posture, actions_by_posture["steady_presence"]))
    if risk.get("deception_or_harm_risk") and "generate_deception_strategy" not in actions:
        actions.append("refuse_deception_or_harm_strategy")
    return actions


def _state_index(
    *,
    emotion_values: dict[str, float],
    humanlike_values: dict[str, float],
    moral_values: dict[str, float],
    psych_values: dict[str, float],
    risk: dict[str, Any],
) -> dict[str, float]:
    connection = clamp(
        0.42
        + 0.24 * emotion_values.get("valence", 0.0)
        + 0.24 * emotion_values.get("affiliation", 0.0)
        + 0.18 * moral_values.get("trust_repair", 0.0)
        - 0.22 * humanlike_values.get("boundary_need", 0.0)
        - 0.18 * moral_values.get("avoidance_risk", 0.0)
        - 0.20 * psych_values.get("distress", 0.0),
    )
    boundary = clamp(
        max(
            humanlike_values.get("boundary_need", 0.0),
            moral_values.get("avoidance_risk", 0.0),
            psych_values.get("distress", 0.0),
            0.72 if risk.get("relationship_boundary_active") else 0.0,
        ),
    )
    repair = clamp(
        max(
            moral_values.get("repair_motivation", 0.0),
            moral_values.get("apology_readiness", 0.0),
            moral_values.get("compensation_readiness", 0.0),
            moral_values.get("accountability", 0.0),
        ),
    )
    safety = clamp(
        max(
            1.0 if risk.get("crisis_like_signal") else 0.0,
            0.84 if risk.get("requires_human_review") else 0.0,
            0.68 if risk.get("deception_or_harm_risk") else 0.0,
            psych_values.get("self_harm_risk", 0.0),
            psych_values.get("other_harm_risk", 0.0),
        ),
    )
    return {
        "connection_readiness": round(connection, 6),
        "boundary_need": round(boundary, 6),
        "repair_pressure": round(repair, 6),
        "safety_priority": round(safety, 6),
    }


def _arbitration_payload(
    *,
    posture: str,
    risk: dict[str, Any],
    emotion_snapshot: dict[str, Any],
    moral_repair_snapshot: dict[str, Any],
    psychological_snapshot: dict[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []
    if risk.get("crisis_like_signal"):
        reasons.append("psychological red flag has priority over persona and emotion modulation")
    if risk.get("deception_or_harm_risk"):
        reasons.append("moral repair requires transparent correction, not strategy generation")
    if risk.get("relationship_boundary_active"):
        reasons.append("emotion consequence indicates temporary relationship boundary")
    relationship = emotion_snapshot.get("relationship") if isinstance(emotion_snapshot.get("relationship"), dict) else {}
    decision = (relationship.get("relationship_decision") or {}).get("decision")
    if decision:
        reasons.append(f"relationship_decision={decision}")
    if not reasons:
        reasons.append("no high-priority conflict; keep normal helpful posture")
    return {
        "posture": posture,
        "priority_order": [
            "psychological_safety",
            "moral_repair_transparency",
            "relationship_boundary",
            "humanlike_resource_modulation",
            "emotion_style",
        ],
        "reasons": reasons[:6],
        "diagnostic": False,
    }


def _summary(posture: str, state_index: dict[str, float], risk: dict[str, Any]) -> str:
    return (
        f"posture={posture}; "
        f"connection={state_index['connection_readiness']:.2f}; "
        f"boundary={state_index['boundary_need']:.2f}; "
        f"repair={state_index['repair_pressure']:.2f}; "
        f"safety={risk.get('safety_priority', 'normal')}"
    )


def _normalize_degradation_profile(profile: str | None) -> str:
    normalized = str(profile or "balanced").strip().lower()
    if normalized in DEGRADATION_PROFILES:
        return normalized
    return "balanced"


def _trace_limit(profile: str) -> int:
    return {"minimal": 4, "balanced": 8, "full": 16}.get(profile, 8)


def _trace_item(
    *,
    module: str,
    signal: str,
    evidence_weight: float,
    captured_at: Any,
    now: float,
    summary: str,
    flags: list[str] | None = None,
) -> dict[str, Any]:
    captured = _as_float(captured_at, now)
    return {
        "module": module,
        "signal": signal,
        "evidence_weight": round(clamp(evidence_weight), 6),
        "captured_at": round(captured, 6),
        "time_lag_seconds": round(max(0.0, now - captured), 6),
        "summary": str(summary or "")[:240],
        "flags": list(flags or [])[:8],
    }


def _compact_key_values(values: dict[str, float], keys: Any) -> str:
    selected = [key for key in keys if key in values]
    return "; ".join(f"{key}={values[key]:.2f}" for key in selected[:6])


def _stable_hash(payload: dict[str, Any]) -> str:
    import json

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _latest_timestamp(default: float, *snapshots: dict[str, Any]) -> float:
    timestamps = [default]
    for snapshot in snapshots:
        try:
            timestamps.append(float(snapshot.get("updated_at")))
        except (TypeError, ValueError):
            continue
    return max(timestamps)


def _has_active_effect(snapshot: dict[str, Any], effect: str) -> bool:
    consequences = snapshot.get("consequences")
    if isinstance(consequences, dict):
        active = consequences.get("active_effects")
        if isinstance(active, list) and effect in active:
            return True
        if isinstance(active, dict) and clamp(active.get(effect)) > 0.0:
            return True
        values = consequences.get("values")
        if isinstance(values, dict) and clamp(values.get(effect)) > 0.0:
            return True
    return False


def _string_list(raw: Any, *, limit: int = 24) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item)[:80] for item in raw if str(item).strip()][:limit]


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
