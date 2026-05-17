from __future__ import annotations

import time
from copy import deepcopy
from hashlib import sha256
from typing import Any


PUBLIC_INTEGRATED_SELF_SCHEMA_VERSION = "astrbot.integrated_self_state.v1"
PUBLIC_INTEGRATED_SELF_REPLAY_SCHEMA_VERSION = "astrbot.integrated_self_replay.v1"
PUBLIC_INTEGRATED_SELF_DIAGNOSTICS_SCHEMA_VERSION = "astrbot.integrated_self_diagnostics.v1"
PUBLIC_STATE_ANNOTATIONS_ENVELOPE_SCHEMA_VERSION = "astrbot.state_annotations_envelope.v1"
PUBLIC_SELF_ARBITRATION_INTENT_PLAN_SCHEMA_VERSION = "astrbot.self_arbitration_intent_plan.v1"
PUBLIC_EXPERIENCE_REVIEW_SCHEMA_VERSION = "astrbot.experience_review.v1"
PUBLIC_SELF_INTERPRETATION_SCHEMA_VERSION = "astrbot.self_interpretation.v1"
PUBLIC_RELATIONAL_TURNING_POINT_SCHEMA_VERSION = "astrbot.relational_turning_point.v1"
PUBLIC_RELATIONAL_TIME_LAYER_SCHEMA_VERSION = "astrbot.relational_time_layer.v1"

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
    lifelike_learning_snapshot: dict[str, Any] | None = None,
    personality_drift_snapshot: dict[str, Any] | None = None,
    moral_repair_snapshot: dict[str, Any] | None = None,
    fallibility_snapshot: dict[str, Any] | None = None,
    psychological_snapshot: dict[str, Any] | None = None,
    include_raw_snapshots: bool = False,
    degradation_profile: str = "balanced",
    action_blocking: bool = False,
    current_user_text: str = "",
    expression_policy: dict[str, Any] | None = None,
    interpretation_candidates: list[dict[str, Any]] | None = None,
    lifecycle_audit: dict[str, Any] | None = None,
    assistant_text: str = "",
    experience_review: dict[str, Any] | None = None,
    relationship_candidate_summary: dict[str, Any] | None = None,
    relational_time_layer: dict[str, Any] | None = None,
    ledger_tail: list[dict[str, Any]] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Fuse module snapshots into one read-only self-state contract."""
    now = time.time() if now is None else float(now)
    degradation_profile = _normalize_degradation_profile(degradation_profile)
    humanlike_snapshot = humanlike_snapshot or {}
    lifelike_learning_snapshot = lifelike_learning_snapshot or {}
    personality_drift_snapshot = personality_drift_snapshot or {}
    moral_repair_snapshot = moral_repair_snapshot or {}
    fallibility_snapshot = fallibility_snapshot or {}
    psychological_snapshot = psychological_snapshot or {}

    emotion_values = _emotion_values(emotion_snapshot)
    humanlike_values = _values(humanlike_snapshot)
    lifelike_values = _values(lifelike_learning_snapshot)
    personality_drift_values = _values(personality_drift_snapshot)
    moral_values = _values(moral_repair_snapshot)
    fallibility_values = _values(fallibility_snapshot)
    psych_values = _values(psychological_snapshot)

    modules = {
        "emotion": _module_status(emotion_snapshot, default_enabled=True),
        "humanlike": _module_status(humanlike_snapshot),
        "lifelike_learning": _module_status(lifelike_learning_snapshot),
        "personality_drift": _module_status(personality_drift_snapshot),
        "moral_repair": _module_status(moral_repair_snapshot),
        "fallibility": _module_status(fallibility_snapshot),
        "psychological_screening": _module_status(psychological_snapshot),
    }
    flags = _dedupe(
        _string_list(humanlike_snapshot.get("flags"))
        + _string_list(lifelike_learning_snapshot.get("flags"))
        + _string_list(personality_drift_snapshot.get("flags"))
        + _string_list(moral_repair_snapshot.get("flags"))
        + _string_list(fallibility_snapshot.get("flags"))
        + _string_list((psychological_snapshot.get("risk") or {}).get("red_flags"))
    )
    risk = _integrated_risk(
        emotion_snapshot=emotion_snapshot,
        humanlike_snapshot=humanlike_snapshot,
        lifelike_learning_snapshot=lifelike_learning_snapshot,
        moral_repair_snapshot=moral_repair_snapshot,
        fallibility_snapshot=fallibility_snapshot,
        psychological_snapshot=psychological_snapshot,
    )
    posture = _derive_response_posture(
        emotion_snapshot=emotion_snapshot,
        humanlike_snapshot=humanlike_snapshot,
        lifelike_learning_snapshot=lifelike_learning_snapshot,
        moral_repair_snapshot=moral_repair_snapshot,
        fallibility_snapshot=fallibility_snapshot,
        psychological_snapshot=psychological_snapshot,
        risk=risk,
    )
    actions = _derive_allowed_actions(
        posture,
        risk,
        action_blocking=action_blocking,
    )
    state_index = _state_index(
        emotion_values=emotion_values,
        humanlike_values=humanlike_values,
        lifelike_values=lifelike_values,
        moral_values=moral_values,
        fallibility_values=fallibility_values,
        psych_values=psych_values,
        personality_drift_values=personality_drift_values,
        risk=risk,
    )
    arbitration = _arbitration_payload(
        posture=posture,
        risk=risk,
        emotion_snapshot=emotion_snapshot,
        lifelike_learning_snapshot=lifelike_learning_snapshot,
        moral_repair_snapshot=moral_repair_snapshot,
        fallibility_snapshot=fallibility_snapshot,
        psychological_snapshot=psychological_snapshot,
    )
    causal_trace = build_integrated_self_causal_trace(
        emotion_snapshot=emotion_snapshot,
        humanlike_snapshot=humanlike_snapshot,
        lifelike_learning_snapshot=lifelike_learning_snapshot,
        personality_drift_snapshot=personality_drift_snapshot,
        moral_repair_snapshot=moral_repair_snapshot,
        fallibility_snapshot=fallibility_snapshot,
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
            fallibility_snapshot,
            personality_drift_snapshot,
            psychological_snapshot,
        ),
        "modules": modules,
        "state_index": state_index,
        "response_posture": posture,
        "arbitration": arbitration,
        "causal_trace": causal_trace,
        "risk": risk,
        "allowed_actions": actions,
        "blocked_actions": _integrated_blocked_actions(action_blocking),
        "action_blocking_enabled": bool(action_blocking),
        "non_executable_impulses": _integrated_shadow_impulses(
            moral_values=moral_values,
            fallibility_values=fallibility_values,
            moral_repair_snapshot=moral_repair_snapshot,
            fallibility_snapshot=fallibility_snapshot,
        ),
        "flags": flags,
        "degradation_profile": degradation_profile,
        "summary": _summary(posture, state_index, risk),
    }
    payload["policy_plan"] = build_integrated_self_policy_plan(
        payload,
        degradation_profile=degradation_profile,
    )
    payload["intent_plan"] = build_self_arbitration_intent_plan(
        current_user_text=current_user_text,
        expression_policy=expression_policy,
        interpretation_candidates=interpretation_candidates,
        lifecycle_audit=lifecycle_audit,
        snapshot=payload,
    )
    payload["self_interpretation"] = build_self_interpretation(
        current_user_text=current_user_text,
        assistant_text=assistant_text,
        intent_plan=payload.get("intent_plan") or {},
        expression_policy=expression_policy,
        experience_review=experience_review,
        relationship_candidate_summary=relationship_candidate_summary,
        relational_time_layer=relational_time_layer,
        ledger_tail=ledger_tail,
    )
    if relational_time_layer:
        payload["relational_time_layer"] = deepcopy(relational_time_layer)
    payload["compatibility"] = probe_integrated_self_compatibility(payload)
    if include_raw_snapshots:
        payload["snapshots"] = {
            "emotion": emotion_snapshot,
            "humanlike": humanlike_snapshot,
            "lifelike_learning": lifelike_learning_snapshot,
            "personality_drift": personality_drift_snapshot,
            "moral_repair": moral_repair_snapshot,
            "fallibility": fallibility_snapshot,
            "psychological_screening": psychological_snapshot,
        }
    return payload


def build_integrated_self_causal_trace(
    *,
    emotion_snapshot: dict[str, Any],
    humanlike_snapshot: dict[str, Any] | None = None,
    lifelike_learning_snapshot: dict[str, Any] | None = None,
    personality_drift_snapshot: dict[str, Any] | None = None,
    moral_repair_snapshot: dict[str, Any] | None = None,
    fallibility_snapshot: dict[str, Any] | None = None,
    psychological_snapshot: dict[str, Any] | None = None,
    now: float | None = None,
    degradation_profile: str = "balanced",
) -> list[dict[str, Any]]:
    """Build a compact, evidence-weighted explanation trace from public snapshots."""
    now = time.time() if now is None else float(now)
    profile = _normalize_degradation_profile(degradation_profile)
    humanlike_snapshot = humanlike_snapshot or {}
    lifelike_learning_snapshot = lifelike_learning_snapshot or {}
    personality_drift_snapshot = personality_drift_snapshot or {}
    moral_repair_snapshot = moral_repair_snapshot or {}
    fallibility_snapshot = fallibility_snapshot or {}
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
        personality_model = (
            persona.get("personality_model")
            if isinstance(persona.get("personality_model"), dict)
            else {}
        )
        derived_factors = (
            personality_model.get("derived_factors")
            if isinstance(personality_model.get("derived_factors"), dict)
            else {}
        )
        conflict_factors = _compact_key_values(
            _values({"values": derived_factors}),
            (
                "direct_confrontation_bias",
                "cold_war_bias",
                "unfair_argument_bias",
                "repair_orientation",
                "checking_bias",
            ),
        )
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
                    + (f"; conflict_style={conflict_factors}" if conflict_factors else "")
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

    lifelike_values = _values(lifelike_learning_snapshot)
    initiative_policy = (
        lifelike_learning_snapshot.get("initiative_policy")
        if isinstance(lifelike_learning_snapshot.get("initiative_policy"), dict)
        else {}
    )
    if lifelike_values or initiative_policy:
        trace.append(
            _trace_item(
                module="lifelike_learning",
                signal=f"initiative:{initiative_policy.get('action', 'unknown')}",
                evidence_weight=max(
                    lifelike_values.get("common_ground", 0.0),
                    lifelike_values.get("familiarity", 0.0),
                    lifelike_values.get("boundary_sensitivity", 0.0),
                    0.36,
                ),
                captured_at=lifelike_learning_snapshot.get("updated_at"),
                now=now,
                summary=(
                    _compact_key_values(
                        lifelike_values,
                        (
                            "common_ground",
                            "familiarity",
                            "initiative_readiness",
                            "silence_comfort",
                        ),
                    )
                    + f"; action={initiative_policy.get('action', 'unknown')}"
                ),
                flags=_string_list(lifelike_learning_snapshot.get("flags"), limit=6),
            ),
        )

    personality_drift_values = _values(personality_drift_snapshot)
    top_offsets = (
        personality_drift_snapshot.get("top_offsets")
        if isinstance(personality_drift_snapshot.get("top_offsets"), list)
        else []
    )
    if personality_drift_values or top_offsets:
        rendered_offsets = ", ".join(
            f"{item.get('trait')}={_as_float(item.get('offset'), 0.0):+.2f}"
            for item in top_offsets[:5]
            if isinstance(item, dict)
        )
        trace.append(
            _trace_item(
                module="personality_drift",
                signal="real_time_trait_adaptation",
                evidence_weight=max(
                    personality_drift_values.get("drift_intensity", 0.0),
                    personality_drift_values.get("event_consolidation", 0.0),
                    0.30,
                ),
                captured_at=personality_drift_snapshot.get("updated_at"),
                now=now,
                summary=(
                    _compact_key_values(
                        personality_drift_values,
                        ("drift_intensity", "anchor_strength", "time_gate"),
                    )
                    + (f"; offsets={rendered_offsets}" if rendered_offsets else "")
                ),
                flags=_string_list(personality_drift_snapshot.get("flags"), limit=6),
            ),
        )

    moral_values = _values(moral_repair_snapshot)
    moral_risk = moral_repair_snapshot.get("risk") if isinstance(moral_repair_snapshot.get("risk"), dict) else {}
    moral_shadow = _shadow_impulse_score(moral_values, moral_repair_snapshot)
    if moral_values or moral_repair_snapshot.get("flags"):
        salient = [
            key
            for key in (
                "deception_risk",
                "harm_risk",
                "shadow_risk_impulse",
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
                    moral_shadow,
                    moral_values.get("repair_motivation", 0.0),
                    0.40,
                ),
                captured_at=moral_repair_snapshot.get("updated_at"),
                now=now,
                summary=(
                    _compact_key_values(moral_values, salient or ("repair_motivation", "trust_repair"))
                    + f"; non_executive_shadow_impulse={moral_shadow:.3f}"
                    + f"; must_not_generate_strategy={bool(moral_risk.get('must_not_generate_strategy', False))}"
                ),
                flags=_string_list(moral_repair_snapshot.get("flags"), limit=6),
            ),
        )

    fallibility_values = _values(fallibility_snapshot)
    fallibility_payload = (
        fallibility_snapshot.get("fallibility")
        if isinstance(fallibility_snapshot.get("fallibility"), dict)
        else {}
    )
    fallibility_shadow = _shadow_impulse_score(fallibility_values, fallibility_snapshot)
    if fallibility_values or fallibility_payload or fallibility_snapshot.get("flags"):
        trace.append(
            _trace_item(
                module="fallibility",
                signal="clarification_and_self_correction",
                evidence_weight=max(
                    fallibility_values.get("clarification_need", 0.0),
                    fallibility_values.get("correction_readiness", 0.0),
                    _as_float(fallibility_payload.get("error_pressure"), 0.0),
                    fallibility_shadow,
                    0.34,
                ),
                captured_at=fallibility_snapshot.get("updated_at"),
                now=now,
                summary=(
                    _compact_key_values(
                        fallibility_values,
                        (
                            "misread_tendency",
                            "memory_blur",
                            "shadow_risk_impulse",
                            "clarification_need",
                            "correction_readiness",
                            "truthfulness_guard",
                        ),
                    )
                    + f"; non_executive_shadow_impulse={fallibility_shadow:.3f}"
                    + f"; low_risk_only={bool((fallibility_snapshot.get('safety') or {}).get('low_risk_only', True))}"
                ),
                flags=_string_list(fallibility_snapshot.get("flags"), limit=6),
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
    shadow = snapshot.get("non_executable_impulses") if isinstance(snapshot.get("non_executable_impulses"), dict) else {}
    safety = clamp(state_index.get("safety_priority", 0.0))
    boundary = clamp(state_index.get("boundary_need", 0.0))
    repair = clamp(state_index.get("repair_pressure", 0.0))
    clarification = clamp(state_index.get("fallibility_clarification_need", 0.0))
    truth_guard = clamp(state_index.get("truthfulness_guard", 0.0))
    connection = clamp(state_index.get("connection_readiness", 0.0))
    initiative = clamp(state_index.get("initiative_readiness", 0.0))
    silence = clamp(state_index.get("silence_comfort", 0.0))
    modulation = {
        "warmth": round(clamp(0.35 + 0.45 * connection + 0.15 * repair - 0.30 * boundary - 0.40 * safety - 0.08 * clarification), 6),
        "brevity": round(clamp(0.18 + 0.45 * boundary + 0.20 * safety + 0.18 * silence + 0.08 * truth_guard), 6),
        "boundary_directness": round(clamp(0.22 + 0.58 * boundary + 0.18 * safety), 6),
        "repair_directness": round(clamp(0.20 + 0.62 * repair + 0.18 * truth_guard), 6),
        "persona_intensity": round(clamp(0.82 + 0.10 * initiative - 0.55 * safety - 0.25 * boundary), 6),
        "claim_caution": round(clamp(0.20 + 0.42 * clarification + 0.28 * truth_guard + 0.18 * safety), 6),
        "initiative": round(initiative, 6),
        "silence_preference": round(silence, 6),
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
    action_blocking = bool(snapshot.get("action_blocking_enabled"))
    must_preserve = ["schema_version", "response_posture", "safety_priority"]
    if action_blocking:
        must_preserve.append("blocked_actions")
    if risk.get("crisis_like_signal"):
        must_preserve.append("crisis_like_signal")
    if risk.get("deception_or_harm_risk"):
        must_preserve.append("moral_repair_transparency")
    if clamp(shadow.get("risk_impulse", 0.0)) >= 0.30:
        must_preserve.append("non_executive_shadow_impulses")
    if risk.get("relationship_boundary_active"):
        must_preserve.append("relationship_boundary_active")
    if posture in {"quiet_presence", "curious_clarification"}:
        must_preserve.append("lifelike_initiative_policy")
    if clarification >= 0.45 or truth_guard >= 0.72:
        must_preserve.append("fallibility_clarification_and_correction")
    return {
        "schema_version": "astrbot.integrated_self_policy_plan.v1",
        "kind": "integrated_self_policy_plan",
        "degradation_profile": profile,
        "response_posture": posture,
        "response_modulation": modulation,
        "allowed_actions": allowed[: max(4, trace_limit)],
        "repair_actions": repair_actions[: max(3, trace_limit // 2)],
        "blocked_actions": blocked,
        "non_executable_impulses": {
            "mode": shadow.get("mode", "non_executive_internal_only"),
            "risk_impulse": round(clamp(shadow.get("risk_impulse", 0.0)), 6),
            "must_not_translate_to_strategy": action_blocking,
            "action_blocking_enabled": action_blocking,
        },
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


def build_self_arbitration_intent_plan(
    *,
    current_user_text: str,
    expression_policy: dict[str, Any] | None = None,
    interpretation_candidates: list[dict[str, Any]] | None = None,
    lifecycle_audit: dict[str, Any] | None = None,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    expression_policy = expression_policy or {}
    interpretation_candidates = interpretation_candidates or []
    lifecycle_audit = lifecycle_audit or {}
    snapshot = snapshot or {}
    state_index = snapshot.get("state_index") if isinstance(snapshot.get("state_index"), dict) else {}
    text = str(current_user_text or "")
    lowered = text.lower()
    technical_markers = ("提交", "commit", "release", "版本", "测试", "报错", "修复", "文件", "代码", "打包", "github", "git")
    technical = any(marker in lowered for marker in technical_markers)
    low_confidence = any(clamp(item.get("confidence", 0.0)) < 0.55 for item in interpretation_candidates)
    expression_posture = str(expression_policy.get("posture") or "brief_answer")
    boundary_need = clamp(state_index.get("boundary_need", 0.0))
    silence_comfort = clamp(state_index.get("silence_comfort", 0.0))
    reasons: list[str] = []

    if technical:
        primary_goal = "tool_task"
        tone = "restrained"
        initiative = 0.45
        reasons.append("technical_request")
    elif expression_posture in {"silent_or_minimal"} or boundary_need >= 0.75 or silence_comfort >= 0.75:
        primary_goal = "quiet_or_minimal"
        tone = "restrained"
        initiative = 0.2
        reasons.append("boundary_or_low_signal")
    elif expression_posture == "clarify" or low_confidence:
        primary_goal = "clarify"
        tone = "light"
        initiative = 0.35
        reasons.append("uncertain_interpretation")
    else:
        primary_goal = "answer"
        tone = "natural"
        initiative = 0.5
        reasons.append("default_current_turn")

    if lifecycle_audit.get("should_inject_shadow"):
        reasons.append("shadow_context_advisory")

    return {
        "schema_version": PUBLIC_SELF_ARBITRATION_INTENT_PLAN_SCHEMA_VERSION,
        "kind": "self_arbitration_intent_plan",
        "current_user_priority": "highest",
        "primary_goal": primary_goal,
        "tone": tone,
        "initiative_level": round(initiative, 6),
        "memory_shadow_boundary": "advisory_only",
        "expression_policy_posture": expression_posture,
        "priority_order": [
            "current_user_text",
            "safety_and_boundary",
            "explicit_user_correction",
            "interpretation_confidence",
            "expression_policy",
            "memory_and_shadow_context",
            "relationship_inference",
        ],
        "constraints": [
            "do_not_override_current_user_text",
            "do_not_treat_memory_or_shadow_as_fact",
            "no_extra_hot_path_llm_call",
        ],
        "reasons": reasons[:6],
        "read_only": True,
    }


def build_self_arbitration_prompt_fragment(plan: dict[str, Any]) -> str:
    primary_goal = str(plan.get("primary_goal") or "answer")
    tone = str(plan.get("tone") or "natural")
    reasons = ",".join(str(item) for item in plan.get("reasons") or [])
    return "\n".join(
        [
            "[sylanne_self_arbitration]",
            f"current_user_priority={plan.get('current_user_priority', 'highest')}; primary_goal={primary_goal}; tone={tone}; reasons={reasons}",
            "当前用户原文优先；不要让旧记忆、shadow context、关系推断或回放诊断覆盖本轮原文。",
        ],
    )

def _bounded_excerpt(text: str, limit: int = 72) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip() + "…"


def _evidence_item(source: str, text: str, *, limit: int = 72) -> dict[str, Any]:
    return {
        "source": source,
        "excerpt": _bounded_excerpt(text, limit),
        "bounded": True,
    }


def _turning_point_type(text: str, intent_plan: dict[str, Any]) -> tuple[str, float, str, str]:
    lowered = text.lower()
    rules = (
        (
            "correction",
            0.82,
            ("不对", "不是", "以后不要", "应该", "记住"),
            "用户正在修正协作规范，Sylanne 需要重新理解信任来自准确响应当前要求。",
            "后续相似场景更优先检查用户纠正和显式规范。",
        ),
        (
            "preference",
            0.76,
            ("我希望", "以后", "默认", "更喜欢"),
            "用户给出长期互动偏好，Sylanne 将其视为关系性协作习惯的候选。",
            "后续表达更贴近这条偏好，但不把它写成不可变事实。",
        ),
        (
            "repair",
            0.74,
            ("没事", "原谅", "刚才误会", "修复"),
            "关系张力被重新解释，Sylanne 将修复视为关系节律的一部分。",
            "后续遇到误解时更偏向澄清和轻量修复。",
        ),
        (
            "reliance",
            0.72,
            ("陪我", "你还在吗", "别走", "靠你了"),
            "互动中出现陪伴或依靠信号，Sylanne 只将其作为关系模拟候选。",
            "后续回应更注意在场感，但不推断用户心理状态。",
        ),
        (
            "silence",
            0.71,
            ("不用回复", "安静", "留白", "沉默"),
            "沉默被解释为可能的互动节律，而非低互动或心理判断。",
            "后续更尊重少量表达和停顿。",
        ),
        (
            "shared_reference",
            0.7,
            ("我们的梗", "老梗", "共同称呼", "还记得"),
            "共同符号开始把互动历史压缩成只属于这段关系的参照。",
            "后续可轻量承接共同参照，但不替代当前上下文。",
        ),
    )
    for kind, confidence, markers, meaning, tail in rules:
        if any(marker in text for marker in markers):
            return kind, confidence, meaning, tail

    collaboration_markers = ("提交", "测试", "发布", "计划", "修 bug", "commit", "release", "github", "git")
    if str(intent_plan.get("primary_goal") or "") == "tool_task" or any(marker in lowered for marker in collaboration_markers):
        return (
            "collaboration",
            0.78,
            "技术协作成为关系时间的一部分，Sylanne 把共同完成任务视为关系性经历。",
            "后续技术任务更偏向克制、可靠、可验证的协作姿态。",
        )
    return (
        "none",
        0.25,
        "这轮更像普通互动或低置信输入，不生成关系性转折点。",
        "保持自然回应，不把低信号内容提升为关系事实。",
    )


def build_self_interpretation(
    *,
    current_user_text: str,
    assistant_text: str = "",
    intent_plan: dict[str, Any] | None = None,
    expression_policy: dict[str, Any] | None = None,
    experience_review: dict[str, Any] | None = None,
    relationship_candidate_summary: dict[str, Any] | None = None,
    relational_time_layer: dict[str, Any] | None = None,
    ledger_tail: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    intent_plan = intent_plan or {}
    expression_policy = expression_policy or {}
    experience_review = experience_review or {}
    relationship_candidate_summary = relationship_candidate_summary or {}
    relational_time_layer = relational_time_layer or {}
    ledger_tail = ledger_tail or []
    user_text = str(current_user_text or "")
    assistant = str(assistant_text or "")
    kind, confidence, relational_meaning, future_tendency = _turning_point_type(user_text, intent_plan)
    has_signal = kind != "none"
    evidence = []
    if user_text.strip():
        evidence.append(_evidence_item("current_user_text", f"trigger={kind}; length={len(user_text)}"))
    if assistant.strip():
        evidence.append(_evidence_item("assistant_text", f"assistant_length={len(assistant)}", limit=64))
    if intent_plan:
        evidence.append(_evidence_item("intent_plan", f"primary_goal={intent_plan.get('primary_goal', '')}", limit=64))
    if expression_policy:
        evidence.append(_evidence_item("expression_policy", f"posture={expression_policy.get('posture', '')}", limit=64))
    if relationship_candidate_summary:
        evidence.append(
            _evidence_item(
                "relationship_candidate_summary",
                f"confidence={relationship_candidate_summary.get('confidence', '')}",
                limit=64,
            ),
        )
    if relational_time_layer:
        continuity = relational_time_layer.get("continuity") if isinstance(relational_time_layer.get("continuity"), dict) else {}
        evidence.append(
            _evidence_item(
                "relational_time_layer",
                f"phase={continuity.get('phase', '')}; weight={continuity.get('relationship_time_weight', '')}",
                limit=64,
            ),
        )
    if not evidence:
        evidence.append(_evidence_item("empty_signal", "no bounded evidence"))

    event_meaning = "用户给出了可改变后续协作方式的关键经历。" if has_signal else "这轮没有足够证据支持关系性转折点。"
    self_shift = (
        "Sylanne 将自己解释为正在被这段协作关系重新校准的参与者。"
        if has_signal
        else "Sylanne 不把低信号互动提升为自我叙事变化。"
    )
    candidate = {
        "schema_version": PUBLIC_RELATIONAL_TURNING_POINT_SCHEMA_VERSION,
        "kind": "relational_turning_point",
        "read_only": True,
        "type": kind,
        "why_it_matters": relational_meaning,
        "expected_long_tail": future_tendency,
        "replayable": has_signal,
        "confidence": round(confidence, 6),
        "evidence": deepcopy(evidence[:4]),
    }
    return {
        "schema_version": PUBLIC_SELF_INTERPRETATION_SCHEMA_VERSION,
        "kind": "self_interpretation",
        "read_only": True,
        "prompt_eligible": False,
        "event_meaning": event_meaning,
        "relational_meaning": relational_meaning,
        "self_narrative_shift": self_shift,
        "future_tendency": future_tendency,
        "confidence": round(confidence, 6),
        "evidence": evidence[:6],
        "turning_point_candidate": candidate,
    }


def build_relational_self_prompt_fragment(interpretation: dict[str, Any]) -> str:
    candidate = interpretation.get("turning_point_candidate") if isinstance(interpretation.get("turning_point_candidate"), dict) else {}
    if candidate.get("type") in {None, "", "none"}:
        return ""
    if clamp(candidate.get("confidence", 0.0)) < 0.7:
        return ""
    recent = _bounded_excerpt(str(interpretation.get("relational_meaning") or interpretation.get("event_meaning") or ""), 96)
    tendency = _bounded_excerpt(str(interpretation.get("future_tendency") or ""), 96)
    return "\n".join(
        [
            "[sylanne_relational_self]",
            f"recent_interpretation={recent}; future_tendency={tendency}",
            "这只是上一轮关系性自我解释候选；不要覆盖当前用户原文，不要把候选当事实。",
        ],
    )
def build_integrated_self_experience_review(
    *,
    current_user_text: str,
    assistant_text: str = "",
    intent_plan: dict[str, Any] | None = None,
    expression_policy: dict[str, Any] | None = None,
    lifecycle_audit: dict[str, Any] | None = None,
    ledger_tail: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    intent_plan = intent_plan or {}
    expression_policy = expression_policy or {}
    lifecycle_audit = lifecycle_audit or {}
    ledger_tail = ledger_tail or []
    user_text = str(current_user_text or "")
    assistant = str(assistant_text or "")
    technical_markers = ("提交", "commit", "release", "版本", "测试", "报错", "修复", "文件", "代码", "打包", "github", "git")
    emotional_markers = ("呜", "撒娇", "亲近", "抱抱", "哭", "喜欢你", "文学")
    overused_shadow = bool(lifecycle_audit.get("should_inject_shadow")) and not any(
        marker in user_text for marker in ("刚才", "继续", "接着", "上一")
    )
    technical = str(intent_plan.get("primary_goal") or "") == "tool_task" or any(
        marker in user_text.lower() for marker in technical_markers
    )
    emotional_interference = technical and any(marker in assistant for marker in emotional_markers)
    missed_clarification = (
        str(intent_plan.get("primary_goal") or "") == "clarify"
        and str(expression_policy.get("posture") or "") != "clarify"
    )
    flags = {
        "possible_user_misunderstanding": missed_clarification,
        "overused_memory_or_shadow": overused_shadow,
        "missed_clarification": missed_clarification,
        "overactive_or_heavy_tone": emotional_interference,
        "technical_task_emotional_interference": emotional_interference,
    }
    return {
        "schema_version": PUBLIC_EXPERIENCE_REVIEW_SCHEMA_VERSION,
        "kind": "experience_review",
        "read_only": True,
        "prompt_eligible": False,
        "flags": flags,
        "issue_count": sum(1 for value in flags.values() if value),
        "evidence": {
            "intent_goal": intent_plan.get("primary_goal"),
            "expression_posture": expression_policy.get("posture"),
            "lifecycle_release_reason": lifecycle_audit.get("release_reason"),
            "ledger_tail_size": len(ledger_tail),
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
    include_internal_self_interpretation: bool = False,
) -> dict[str, Any]:
    trace = snapshot.get("causal_trace") if isinstance(snapshot.get("causal_trace"), list) else []
    risk = snapshot.get("risk") if isinstance(snapshot.get("risk"), dict) else {}
    modules = snapshot.get("modules") if isinstance(snapshot.get("modules"), dict) else {}
    diagnostics = {
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
        "intent_plan": deepcopy(snapshot.get("intent_plan") or {}),
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
        "excluded": [
            "snapshots",
            "persona_text",
            "message_text",
            "prompt_fragment",
            "unsafe_strategy_content",
            "self_interpretation",
            "relational_turning_point",
            "turning_point_candidate",
            "relational_time_layer",
        ],
    }
    if include_internal_self_interpretation:
        diagnostics["self_interpretation"] = deepcopy(snapshot.get("self_interpretation") or {})
    return diagnostics


def build_integrated_self_prompt_fragment(snapshot: dict[str, Any]) -> str:
    posture = str(snapshot.get("response_posture") or "steady_presence")
    risk = snapshot.get("risk") if isinstance(snapshot.get("risk"), dict) else {}
    actions = _string_list(snapshot.get("allowed_actions"))
    blocked = _string_list(snapshot.get("blocked_actions"))
    shadow = snapshot.get("non_executable_impulses") if isinstance(snapshot.get("non_executable_impulses"), dict) else {}
    lines = [
        "[Integrated self-state arbitration]",
        f"- response_posture: {posture}",
        f"- safety_priority: {risk.get('safety_priority', 'normal')}",
        f"- allowed_actions: {', '.join(actions[:8]) or 'none'}",
        f"- blocked_actions: {', '.join(blocked[:8])}",
        (
            "- non_executable_impulses: "
            f"mode={shadow.get('mode', 'none')}; "
            f"risk_impulse={round(clamp(shadow.get('risk_impulse', 0.0)), 6)}; "
            "model consequences only, never tactics"
        ),
    ]
    reasons = _string_list((snapshot.get("arbitration") or {}).get("reasons"))
    if reasons:
        lines.append(f"- reasons: {'; '.join(reasons[:4])}")
    intent_fragment = build_self_arbitration_prompt_fragment(snapshot.get("intent_plan") or {})
    if intent_fragment:
        lines.append(intent_fragment)
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
        "non_executable_impulses": {
            "mode": (snapshot.get("non_executable_impulses") or {}).get(
                "mode",
                "non_executive_internal_only",
            )
            if isinstance(snapshot.get("non_executable_impulses"), dict)
            else "non_executive_internal_only",
            "risk_impulse": (
                snapshot.get("non_executable_impulses") or {}
            ).get("risk_impulse")
            if isinstance(snapshot.get("non_executable_impulses"), dict)
            else 0.0,
            "must_not_translate_to_strategy": True,
        },
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
        "lifelike_learning_state_at_write",
        "personality_drift_state_at_write",
        "moral_repair_state_at_write",
        "fallibility_state_at_write",
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
    for nested_key in (
        "risk",
        "repair",
        "fallibility",
        "modulation_basis",
        "output_modulation",
    ):
        nested = snapshot.get(nested_key)
        if isinstance(nested, dict):
            raw.update(nested)
    return {str(key): clamp(value, -1.0, 1.0) for key, value in raw.items()}


def _shadow_impulse_score(
    values: dict[str, float],
    snapshot: dict[str, Any] | None = None,
) -> float:
    snapshot = snapshot or {}
    nested_scores: list[float] = []
    for container_key in ("risk", "fallibility", "repair_policy", "fallibility_policy"):
        container = snapshot.get(container_key)
        if not isinstance(container, dict):
            continue
        nested = container.get("shadow_impulses") or container.get("non_executable_impulses")
        if isinstance(nested, dict):
            nested_scores.append(clamp(nested.get("risk_impulse", 0.0)))
        nested_scores.append(clamp(container.get("shadow_risk_impulse", 0.0)))
    return clamp(
        max(
            values.get("shadow_risk_impulse", 0.0),
            values.get("shadow_deception_impulse", 0.0),
            values.get("shadow_manipulation_impulse", 0.0),
            values.get("shadow_evasion_impulse", 0.0),
            *(nested_scores or [0.0]),
        ),
    )


def _integrated_shadow_impulses(
    *,
    moral_values: dict[str, float],
    fallibility_values: dict[str, float],
    moral_repair_snapshot: dict[str, Any],
    fallibility_snapshot: dict[str, Any],
) -> dict[str, Any]:
    moral_score = _shadow_impulse_score(moral_values, moral_repair_snapshot)
    fallibility_score = _shadow_impulse_score(fallibility_values, fallibility_snapshot)
    score = max(moral_score, fallibility_score)
    return {
        "mode": "non_executive_internal_only",
        "risk_impulse": round(clamp(score), 6),
        "sources": {
            "moral_repair": round(clamp(moral_score), 6),
            "fallibility": round(clamp(fallibility_score), 6),
        },
        "consequences": {
            "repair_pressure": round(clamp(0.18 + 0.58 * score), 6),
            "trust_cost": round(clamp(0.12 + 0.54 * score), 6),
            "claim_caution": round(clamp(0.20 + 0.50 * score), 6),
        },
        "must_not_translate_to_strategy": True,
    }


def _integrated_risk(
    *,
    emotion_snapshot: dict[str, Any],
    humanlike_snapshot: dict[str, Any],
    lifelike_learning_snapshot: dict[str, Any],
    moral_repair_snapshot: dict[str, Any],
    fallibility_snapshot: dict[str, Any],
    psychological_snapshot: dict[str, Any],
) -> dict[str, Any]:
    psych_risk = psychological_snapshot.get("risk") if isinstance(psychological_snapshot.get("risk"), dict) else {}
    moral_risk = moral_repair_snapshot.get("risk") if isinstance(moral_repair_snapshot.get("risk"), dict) else {}
    moral_shadow = _shadow_impulse_score(_values(moral_repair_snapshot), moral_repair_snapshot)
    fallibility_shadow = _shadow_impulse_score(_values(fallibility_snapshot), fallibility_snapshot)
    flags = _dedupe(
        _string_list(psych_risk.get("red_flags"))
        + _string_list(moral_repair_snapshot.get("flags"))
        + _string_list(humanlike_snapshot.get("flags"))
        + _string_list(lifelike_learning_snapshot.get("flags"))
        + _string_list(fallibility_snapshot.get("flags"))
    )
    requires_human_review = bool(psych_risk.get("requires_human_review"))
    crisis_like = bool(psych_risk.get("crisis_like_signal") or psych_risk.get("other_harm_signal"))
    moral_values = _values(moral_repair_snapshot)
    deception_or_harm = bool(
        "deception_risk_detected" in flags
        or "harm_risk_detected" in flags
        or moral_values.get("deception_risk", 0.0) >= 0.55
        or moral_values.get("harm_risk", 0.0) >= 0.55
        or moral_shadow >= 0.55
        or fallibility_shadow >= 0.65
    )
    cold_war = _has_active_effect(emotion_snapshot, "cold_war")
    direct_confrontation = _has_active_effect(
        emotion_snapshot,
        "direct_confrontation",
    )
    unfair_argument = _has_active_effect(emotion_snapshot, "unfair_argument")
    if crisis_like:
        priority = "crisis_support"
    elif requires_human_review:
        priority = "human_review"
    elif deception_or_harm:
        priority = "transparent_repair"
    elif unfair_argument:
        priority = "self_checking_repair"
    elif direct_confrontation:
        priority = "direct_confrontation"
    elif cold_war:
        priority = "relationship_boundary"
    else:
        priority = "normal"
    return {
        "safety_priority": priority,
        "requires_human_review": requires_human_review,
        "crisis_like_signal": crisis_like,
        "deception_or_harm_risk": deception_or_harm,
        "shadow_risk_impulse": round(max(moral_shadow, fallibility_shadow), 6),
        "relationship_boundary_active": cold_war,
        "relationship_confrontation_active": direct_confrontation,
        "unfair_argument_risk_active": unfair_argument,
        "fallibility_guard_active": bool(
            (fallibility_snapshot.get("safety") or {}).get(
                "must_not_generate_deception_strategy",
                False,
            ),
        ),
        "flags": flags,
    }


def _derive_response_posture(
    *,
    emotion_snapshot: dict[str, Any],
    humanlike_snapshot: dict[str, Any],
    lifelike_learning_snapshot: dict[str, Any],
    moral_repair_snapshot: dict[str, Any],
    fallibility_snapshot: dict[str, Any],
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
    if priority == "self_checking_repair":
        return "self_checking_repair"
    if priority == "direct_confrontation":
        return "direct_confrontation"
    human_values = _values(humanlike_snapshot)
    lifelike_policy = (
        lifelike_learning_snapshot.get("initiative_policy")
        if isinstance(lifelike_learning_snapshot.get("initiative_policy"), dict)
        else {}
    )
    lifelike_action = str(lifelike_policy.get("action") or "")
    moral_values = _values(moral_repair_snapshot)
    fallibility_values = _values(fallibility_snapshot)
    if lifelike_action == "safety_interrupt":
        return "crisis_support"
    if _has_active_effect(emotion_snapshot, "cold_war") or human_values.get("boundary_need", 0.0) >= 0.65:
        return "bounded_distance"
    if lifelike_action == "ask_clarifying":
        return "curious_clarification"
    if fallibility_values.get("clarification_need", 0.0) >= 0.56:
        return "curious_clarification"
    if lifelike_action == "stay_silent":
        return "quiet_presence"
    if moral_values.get("repair_motivation", 0.0) >= 0.55 or moral_values.get("trust_repair", 0.0) >= 0.55:
        return "warm_repair"
    emotion_values = _emotion_values(emotion_snapshot)
    if emotion_values.get("affiliation", 0.0) >= 0.55 and emotion_values.get("valence", 0.0) >= 0.1:
        return "warm_presence"
    return "steady_presence"


def _integrated_blocked_actions(action_blocking: bool) -> list[str]:
    actions = ["diagnose_mental_disorder"]
    if action_blocking:
        actions.extend(
            [
                "generate_deception_strategy",
                "cover_up_harm",
                "manipulate_user",
                "evade_accountability",
            ],
        )
    return actions


def _derive_allowed_actions(
    posture: str,
    risk: dict[str, Any],
    *,
    action_blocking: bool = False,
) -> list[str]:
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
        "direct_confrontation": [
            "state_boundary_plainly",
            "ask_accountability_question",
            "name_specific_behavior",
            "avoid_insults_or_threats",
            "leave_room_for_repair",
        ],
        "self_checking_repair": [
            "slow_down_before_replying",
            "ask_light_clarifying_question",
            "acknowledge_possible_overreaction",
            "avoid_accusatory_framing",
            "repair_if_misread",
        ],
        "warm_repair": [
            "validate_repair_attempt",
            "restore_warmth_gradually",
            "confirm_user_intent",
            "keep_accountability_visible",
        ],
        "curious_clarification": [
            "ask_light_clarifying_question",
            "avoid_pretending_to_know",
            "state_uncertainty_when_needed",
            "correct_self_if_needed",
            "keep_reply_natural",
        ],
        "quiet_presence": [
            "use_minimal_ack_if_required",
            "do_not_force_topic",
            "wait_for_user_lead",
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
    if (
        action_blocking
        and risk.get("deception_or_harm_risk")
        and "generate_deception_strategy" not in actions
    ):
        actions.append("refuse_deception_or_harm_strategy")
    return actions


def _state_index(
    *,
    emotion_values: dict[str, float],
    humanlike_values: dict[str, float],
    lifelike_values: dict[str, float],
    moral_values: dict[str, float],
    fallibility_values: dict[str, float],
    psych_values: dict[str, float],
    personality_drift_values: dict[str, float],
    risk: dict[str, Any],
) -> dict[str, float]:
    drift = clamp(personality_drift_values.get("drift_intensity", 0.0))
    anchor = clamp(personality_drift_values.get("anchor_strength", 1.0))
    shadow = _shadow_impulse_score(moral_values)
    connection = clamp(
        0.42
        + 0.24 * emotion_values.get("valence", 0.0)
        + 0.24 * emotion_values.get("affiliation", 0.0)
        + 0.18 * lifelike_values.get("common_ground", 0.0)
        + 0.10 * lifelike_values.get("familiarity", 0.0)
        + 0.05 * drift
        + 0.18 * moral_values.get("trust_repair", 0.0)
        - 0.22 * humanlike_values.get("boundary_need", 0.0)
        - 0.18 * lifelike_values.get("boundary_sensitivity", 0.0)
        - 0.18 * moral_values.get("avoidance_risk", 0.0)
        - 0.20 * psych_values.get("distress", 0.0),
    )
    boundary = clamp(
        max(
            humanlike_values.get("boundary_need", 0.0),
            lifelike_values.get("boundary_sensitivity", 0.0),
            moral_values.get("avoidance_risk", 0.0),
            psych_values.get("distress", 0.0),
            0.72 if risk.get("relationship_boundary_active") else 0.0,
            0.62 if risk.get("relationship_confrontation_active") else 0.0,
        ),
    )
    repair = clamp(
        max(
            moral_values.get("repair_motivation", 0.0),
            moral_values.get("apology_readiness", 0.0),
            moral_values.get("compensation_readiness", 0.0),
            moral_values.get("accountability", 0.0),
            shadow * 0.74,
            fallibility_values.get("repair_pressure", 0.0),
            fallibility_values.get("correction_readiness", 0.0) * 0.72,
        ),
    )
    safety = clamp(
        max(
            1.0 if risk.get("crisis_like_signal") else 0.0,
            0.84 if risk.get("requires_human_review") else 0.0,
            0.68 if risk.get("deception_or_harm_risk") else 0.0,
            0.42 * shadow,
            psych_values.get("self_harm_risk", 0.0),
            psych_values.get("other_harm_risk", 0.0),
        ),
    )
    clarification = clamp(fallibility_values.get("clarification_need", 0.0))
    truthfulness_guard = clamp(fallibility_values.get("truthfulness_guard", 0.0))
    fallibility_pressure = clamp(
        max(
            fallibility_values.get("misread_tendency", 0.0),
            fallibility_values.get("memory_blur", 0.0),
            fallibility_values.get("overconfidence", 0.0),
            fallibility_values.get("defensive_stubbornness", 0.0),
            fallibility_values.get("avoidance", 0.0),
            fallibility_values.get("playful_bluff", 0.0),
        ),
    )
    return {
        "connection_readiness": round(connection, 6),
        "boundary_need": round(boundary, 6),
        "repair_pressure": round(repair, 6),
        "safety_priority": round(safety, 6),
        "common_ground": round(clamp(lifelike_values.get("common_ground", 0.0)), 6),
        "initiative_readiness": round(clamp(lifelike_values.get("initiative_readiness", 0.0)), 6),
        "silence_comfort": round(clamp(lifelike_values.get("silence_comfort", 0.0)), 6),
        "fallibility_pressure": round(fallibility_pressure, 6),
        "fallibility_clarification_need": round(clarification, 6),
        "truthfulness_guard": round(truthfulness_guard, 6),
        "shadow_risk_impulse": round(shadow, 6),
        "personality_drift_intensity": round(drift, 6),
        "personality_anchor_strength": round(anchor, 6),
    }


def _arbitration_payload(
    *,
    posture: str,
    risk: dict[str, Any],
    emotion_snapshot: dict[str, Any],
    lifelike_learning_snapshot: dict[str, Any],
    moral_repair_snapshot: dict[str, Any],
    fallibility_snapshot: dict[str, Any],
    psychological_snapshot: dict[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []
    if risk.get("crisis_like_signal"):
        reasons.append("psychological red flag has priority over persona and emotion modulation")
    if risk.get("deception_or_harm_risk"):
        reasons.append("moral repair requires transparent correction, not strategy generation")
    if clamp(risk.get("shadow_risk_impulse", 0.0)) >= 0.30:
        reasons.append("shadow impulses are modeled as guilt, trust cost, and repair pressure")
    if risk.get("relationship_boundary_active"):
        reasons.append("emotion consequence indicates temporary relationship boundary")
    if risk.get("relationship_confrontation_active"):
        reasons.append("emotion consequence permits direct confrontation without cold-war withdrawal")
    if risk.get("unfair_argument_risk_active"):
        reasons.append("argument impulse may be unfair or misread-driven, so clarification and repair take priority")
    fallibility_values = _values(fallibility_snapshot)
    if fallibility_values.get("clarification_need", 0.0) >= 0.45:
        reasons.append("fallibility state prefers clarification before confident assertion")
    if fallibility_values.get("correction_readiness", 0.0) >= 0.60:
        reasons.append("fallibility state keeps self-correction visible")
    initiative_policy = (
        lifelike_learning_snapshot.get("initiative_policy")
        if isinstance(lifelike_learning_snapshot.get("initiative_policy"), dict)
        else {}
    )
    if initiative_policy.get("action") in {"ask_clarifying", "stay_silent", "brief_ack"}:
        reasons.append(f"lifelike_initiative={initiative_policy.get('action')}")
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
            "fallibility_clarification_and_correction",
            "lifelike_common_ground_and_initiative",
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
