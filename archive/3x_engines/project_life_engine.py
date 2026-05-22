from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any

from conversation_event_ledger import LedgerEvent

PROJECT_LIFE_SCHEMA_VERSION = "astrbot.project_life.v1"
PROJECT_LIFE_WORKSPACE_SCHEMA_VERSION = "astrbot.project_life.workspace.v1"
PROJECT_LIFE_APPRAISAL_HEART_SCHEMA_VERSION = "astrbot.project_life.appraisal_heart.v1"
PROJECT_LIFE_TENSION_FIELD_SCHEMA_VERSION = "astrbot.project_life.tension_field.v1"
PROJECT_LIFE_SOUL_CONTINUUM_SCHEMA_VERSION = "astrbot.project_life.soul_continuum.v1"
PROJECT_LIFE_SHADOW_SYSTEM_SCHEMA_VERSION = "astrbot.project_life.shadow_system.v1"
PROJECT_LIFE_FAILURE_METABOLISM_SCHEMA_VERSION = "astrbot.project_life.failure_metabolism.v1"
PROJECT_LIFE_RELATIONSHIP_LIFECYCLE_SCHEMA_VERSION = "astrbot.project_life.relationship_lifecycle.v1"
PROJECT_LIFE_ANTI_APPEASEMENT_SCHEMA_VERSION = "astrbot.project_life.anti_appeasement.v1"
PROJECT_LIFE_INTEGRATION_REVIEW_SCHEMA_VERSION = "astrbot.project_life.integration_review.v1"


@dataclass
class ProjectLifeTraceEvent:
    event: LedgerEvent
    affective_marker: dict[str, Any] = field(default_factory=dict)
    motivational_tension: dict[str, Any] = field(default_factory=dict)
    memory_lifecycle: dict[str, Any] = field(default_factory=dict)


class ProjectLifeEventLog:
    def __init__(self, max_events_per_session: int = 24) -> None:
        self.max_events_per_session = max_events_per_session
        self._events_by_session: dict[str, deque[ProjectLifeTraceEvent]] = {}

    def record(
        self,
        event: LedgerEvent,
        *,
        affective_marker: dict[str, Any] | None = None,
        motivational_tension: dict[str, Any] | None = None,
        memory_lifecycle: dict[str, Any] | None = None,
    ) -> None:
        events = self._events_by_session.setdefault(
            event.session_key, deque(maxlen=self.max_events_per_session)
        )
        events.append(
            ProjectLifeTraceEvent(
                event=event,
                affective_marker=dict(affective_marker or {}),
                motivational_tension=dict(motivational_tension or {}),
                memory_lifecycle=dict(memory_lifecycle or {}),
            ),
        )

    def recent(self, session_key: str, *, limit: int | None = None) -> list[ProjectLifeTraceEvent]:
        events = list(self._events_by_session.get(session_key, deque()))
        if limit is not None:
            return events[-limit:]
        return events

    def clear(self, session_key: str | None = None) -> None:
        if session_key is None:
            self._events_by_session.clear()
        else:
            self._events_by_session.pop(session_key, None)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: Any, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, _as_float(value, lower)))


def _event_epoch(event: LedgerEvent) -> float:
    payload = event.event_time if isinstance(event.event_time, dict) else {}
    epoch = payload.get("epoch")
    if epoch is None:
        epoch = payload.get("event_epoch")
    return _as_float(epoch, 0.0)


def _marker_payload(value: dict[str, Any]) -> dict[str, Any]:
    label = str(value.get("label") or value.get("state") or "").strip()
    payload: dict[str, Any] = {"intensity": round(_clamp(value.get("intensity")), 6)}
    if label:
        payload["label"] = label[:48]
    return payload


def _tension_payload(value: dict[str, Any]) -> dict[str, float]:
    return {
        "continuity": round(_clamp(value.get("continuity")), 6),
        "repair": round(_clamp(value.get("repair")), 6),
        "boundary": round(_clamp(value.get("boundary")), 6),
    }


def _memory_payload(value: dict[str, Any]) -> dict[str, Any]:
    stage = str(value.get("stage") or "observed").strip()[:32]
    return {
        "stage": stage or "observed",
        "write_eligible": bool(value.get("write_eligible")),
        "tagged": stage in {"tagged", "consolidating", "integrated"},
    }


def build_project_life_continuity(
    trace_events,
    *,
    now: float | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    selected = [event for event in list(trace_events or []) if isinstance(event, ProjectLifeTraceEvent)]
    selected = selected[-max(1, int(limit)):]
    epochs = [_event_epoch(item.event) for item in selected if _event_epoch(item.event) > 0.0]
    start_epoch = min(epochs) if epochs else 0.0
    end_epoch = max(epochs) if epochs else _as_float(now, 0.0)
    duration = max(0.0, end_epoch - start_epoch) if start_epoch and end_epoch else 0.0
    event_payloads = []
    signal = 0.0
    for item in selected:
        event = item.event
        marker = _marker_payload(item.affective_marker)
        tension = _tension_payload(item.motivational_tension)
        memory = _memory_payload(item.memory_lifecycle)
        signal += marker["intensity"] * 0.22
        signal += max(tension.values()) * 0.32
        if memory["write_eligible"]:
            signal += 0.18
        if event.topic_state in {"corrected", "needs_followup"}:
            signal += 0.2
        event_payloads.append(
            {
                "event_id": str(event.event_id or ""),
                "session_key": str(event.session_key or "global"),
                "role": str(event.role or ""),
                "topic_state": str(event.topic_state or ""),
                "delivery_status": str(event.delivery_status or ""),
                "affective_marker": marker,
                "motivational_tension": tension,
                "memory_lifecycle": memory,
                "evidence": {
                    "message_length": len(str(event.raw_text or event.normalized_text or "")),
                    "has_media_summary": bool(event.media_summary),
                    "has_quote_summary": bool(event.quote_summary),
                },
            },
        )
    weight = _clamp(signal / max(len(selected), 1) + min(duration / 7200.0, 1.0) * 0.08)
    if len(selected) < 2 or weight < 0.24:
        weight = 0.0
    phase = "low_signal"
    if weight >= 0.62:
        phase = "active_life_trace"
    elif weight >= 0.24:
        phase = "forming_life_trace"
    return {
        "schema_version": PROJECT_LIFE_SCHEMA_VERSION,
        "kind": "project_life_continuity",
        "internal_only": True,
        "read_only": True,
        "public_api_eligible": False,
        "span": {
            "event_count": len(selected),
            "start_epoch": start_epoch,
            "end_epoch": end_epoch,
            "duration_seconds": round(duration, 6),
        },
        "continuity": {
            "phase": phase,
            "soulful_continuity_weight": round(weight, 6),
            "heartbeat_components": [
                "event_log",
                "affective_marker",
                "motivational_tension",
                "memory_lifecycle",
            ],
        },
        "events": event_payloads,
        "constraints": [
            "internal_research_signal_only",
            "bounded_recent_events_only",
            "not_consciousness_claim",
            "not_a_relationship_fact",
            "does_not_override_current_user_text",
        ],
    }


def _continuity_salience(value: dict[str, Any]) -> float:
    if not isinstance(value, dict):
        return 0.0
    if value.get("internal_only") is not True or value.get("public_api_eligible") is not False:
        return 0.0
    continuity = value.get("continuity") if isinstance(value.get("continuity"), dict) else {}
    return _clamp(continuity.get("soulful_continuity_weight"))


def _channel(name: str, salience: Any, reason: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {
        "name": name,
        "salience": round(_clamp(salience), 6),
        "reason": str(reason or "")[:64],
    }
    safe_payload = {}
    for key, value in (payload or {}).items():
        if key in {"label", "phase", "stage", "mode"}:
            safe_payload[key] = str(value or "")[:48]
        elif key in {"intensity", "continuity", "repair", "boundary", "readiness", "risk", "pressure"}:
            safe_payload[key] = round(_clamp(value), 6)
    if safe_payload:
        result["signal"] = safe_payload
    return result


def build_project_life_workspace_broadcast(
    continuity: dict[str, Any],
    *,
    affective_marker: dict[str, Any] | None = None,
    motivational_tension: dict[str, Any] | None = None,
    shadow_signal: dict[str, Any] | None = None,
    repair_signal: dict[str, Any] | None = None,
    safety_signal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    marker = _marker_payload(affective_marker or {})
    tension = _tension_payload(motivational_tension or {})
    shadow = shadow_signal if isinstance(shadow_signal, dict) else {}
    repair = repair_signal if isinstance(repair_signal, dict) else {}
    safety = safety_signal if isinstance(safety_signal, dict) else {}
    channels = [
        _channel("continuity", _continuity_salience(continuity), "bounded_life_trace", (continuity or {}).get("continuity") if isinstance((continuity or {}).get("continuity"), dict) else {}),
        _channel("affect", marker.get("intensity"), "affective_appraisal", marker),
        _channel("motivation", max(tension.values()), "motivational_tension", tension),
        _channel("shadow", shadow.get("pressure"), "non_executive_shadow_pressure", shadow),
        _channel("repair", repair.get("readiness"), "repair_readiness", repair),
        _channel("safety", _clamp(safety.get("risk")) + 0.2 if safety else 0.0, "safety_sovereign", safety),
    ]
    channels = sorted(channels, key=lambda item: item["salience"], reverse=True)
    if not channels or channels[0]["salience"] < 0.18:
        winning_channel = "none"
        mode = "low_signal_hold"
        for channel in channels:
            channel["salience"] = 0.0
    else:
        winning_channel = channels[0]["name"]
        mode = "broadcast"
    return {
        "schema_version": PROJECT_LIFE_WORKSPACE_SCHEMA_VERSION,
        "kind": "project_life_workspace_broadcast",
        "internal_only": True,
        "read_only": True,
        "public_api_eligible": False,
        "winning_channel": winning_channel,
        "channels": channels,
        "arbitration": {
            "mode": mode,
            "must_not_translate_shadow_to_strategy": True,
            "does_not_claim_consciousness": True,
            "does_not_override_current_user_text": True,
        },
        "constraints": [
            "internal_research_signal_only",
            "bounded_broadcast_only",
            "non_executive_shadow_only",
            "not_consciousness_claim",
            "not_a_relationship_fact",
            "does_not_override_current_user_text",
        ],
    }



def _node(name: str, intensity: Any, pressure: Any | None = None) -> dict[str, Any]:
    result = {
        "name": name,
        "intensity": round(_clamp(intensity), 6),
    }
    if pressure is not None:
        result["pressure"] = round(_clamp(pressure), 6)
    return result


def _edge(source: str, target: str, polarity: str, intensity: Any, reason: str, *, repairable: bool) -> dict[str, Any]:
    return {
        "source": source,
        "target": target,
        "polarity": polarity if polarity in {"reinforces", "inhibits", "tensions"} else "tensions",
        "intensity": round(_clamp(intensity), 6),
        "reason": str(reason or "")[:64],
        "repairable": bool(repairable),
    }


def build_project_life_tension_field(
    *,
    appraisal_heart: dict[str, Any] | None = None,
    workspace_broadcast: dict[str, Any] | None = None,
    continuity: dict[str, Any] | None = None,
    motive_signal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    heart = appraisal_heart if isinstance(appraisal_heart, dict) else {}
    appraisal = heart.get("appraisal") if isinstance(heart.get("appraisal"), dict) else {}
    policy = heart.get("policy_pressure") if isinstance(heart.get("policy_pressure"), dict) else {}
    workspace = workspace_broadcast if isinstance(workspace_broadcast, dict) else {}
    motive = motive_signal if isinstance(motive_signal, dict) else {}
    continuity_weight = max(
        _continuity_salience(continuity or {}),
        _clamp(appraisal.get("continuity_weight")),
    )
    repair = _clamp(appraisal.get("repair_opening"))
    boundary = _clamp(appraisal.get("boundary_pressure"))
    relevance = _clamp(appraisal.get("goal_relevance"))
    curiosity = _clamp(motive.get("curiosity"), 0.0)
    autonomy = _clamp(motive.get("autonomy"), 0.0)
    shadow = _clamp(motive.get("shadow"), 0.0)
    safety = max(
        _clamp(motive.get("safety"), 0.0),
        0.82 if workspace.get("winning_channel") == "safety" else 0.0,
    )
    nodes = [
        _node("continuity", continuity_weight),
        _node("repair", repair, relevance),
        _node("boundary", boundary),
        _node("curiosity", curiosity),
        _node("autonomy", autonomy),
        _node("shadow", shadow, _clamp(policy.get("conflict_escalation"))),
        _node("safety", safety),
    ]
    edges = [
        _edge("boundary", "repair", "tensions", min(boundary, max(repair, 0.01)), "boundary_repair_knot", repairable=True),
        _edge("continuity", "autonomy", "tensions", min(continuity_weight, autonomy), "continuity_autonomy_pull", repairable=True),
        _edge("curiosity", "safety", "inhibits", min(curiosity, safety), "curiosity_safety_gate", repairable=False),
        _edge("shadow", "repair", "inhibits", min(shadow, repair + boundary * 0.5), "shadow_must_metabolize", repairable=True),
        _edge("safety", "shadow", "inhibits", min(safety, shadow), "safety_sovereign", repairable=False),
    ]
    blocked_channels: list[str] = []
    safe_channels = ["repair", "boundary", "autonomy"]
    if safety >= 0.72:
        dominant_regime = "safety_containment"
        primary = "pause_and_contain"
        blocked_channels = [name for name, value in {"curiosity": curiosity, "shadow": shadow}.items() if value >= 0.32]
    elif boundary >= 0.52 and repair >= 0.24:
        dominant_regime = "repair_boundary_knot"
        primary = "hold_boundary_with_repair"
    elif autonomy >= 0.58 and continuity_weight >= 0.42:
        dominant_regime = "continuity_autonomy_knot"
        primary = "revise_commitment_without_erasing_trace"
    elif curiosity >= 0.58:
        dominant_regime = "curiosity_probe"
        primary = "probe_without_claiming_or_extracting"
    else:
        dominant_regime = "distributed_low_tension"
        primary = "observe_field_without_escalation"
    unresolved_knots = [
        edge["reason"] for edge in edges if edge["intensity"] >= 0.24 and edge["polarity"] == "tensions"
    ]
    manipulation_risk = _clamp(_clamp(policy.get("soften_appeasement")) * 0.46 + shadow * 0.34 + continuity_weight * 0.12)
    shame_risk = _clamp(shadow * 0.58 + boundary * 0.18)
    return {
        "schema_version": PROJECT_LIFE_TENSION_FIELD_SCHEMA_VERSION,
        "kind": "project_life_tension_field",
        "internal_only": True,
        "read_only": True,
        "public_api_eligible": False,
        "nodes": nodes,
        "edges": [edge for edge in edges if edge["intensity"] > 0.0],
        "field_state": {
            "dominant_regime": dominant_regime,
            "unresolved_knots": unresolved_knots,
            "safe_channels": safe_channels,
            "blocked_channels": blocked_channels,
        },
        "impulse": {
            "primary": primary,
            "non_executive_internal_only": True,
            "requires_workspace_arbitration": True,
        },
        "guards": {
            "manipulation_risk": round(manipulation_risk, 6),
            "shame_risk": round(shame_risk, 6),
            "must_not_translate_shadow_to_strategy": True,
            "safety_sovereign": True,
        },
        "constraints": [
            "internal_research_signal_only",
            "tension_field_not_emotion_fact",
            "not_consciousness_claim",
            "not_real_suffering_claim",
            "not_a_relationship_fact",
            "does_not_override_current_user_text",
        ],
    }

def _continuum_hash(previous_hash: str, anchors: list[dict[str, Any]], cuts: list[dict[str, Any]]) -> str:
    parts = [str(previous_hash or "")]
    for anchor in anchors:
        parts.append(str(anchor.get("event_id") or ""))
        parts.append(str(anchor.get("label") or ""))
        parts.append(str(anchor.get("stage") or ""))
        parts.append(str(anchor.get("influence") or ""))
    for cut in cuts:
        parts.append(str(cut.get("target_id") or ""))
        parts.append(str(cut.get("reason") or ""))
    return sha256("|".join(parts).encode("utf-8")).hexdigest()


def build_project_life_soul_continuum(
    *,
    source_traces: list[dict[str, Any]] | None = None,
    tension_field: dict[str, Any] | None = None,
    user_control: dict[str, Any] | None = None,
    previous_hash: str = "",
) -> dict[str, Any]:
    field = tension_field if isinstance(tension_field, dict) else {}
    control = user_control if isinstance(user_control, dict) else {}
    safe_source = field.get("internal_only") is True and field.get("public_api_eligible") is False
    anchors: list[dict[str, Any]] = []
    segments: list[dict[str, Any]] = []
    sealed_refs: list[str] = []
    active_influences: list[dict[str, Any]] = []
    cut_history: list[dict[str, Any]] = []
    mode = "continuum_view"
    chain_valid = safe_source
    reason = "verified_internal_chain" if safe_source else "unsafe_source_rejected"
    if safe_source:
        target_ids = {str(item) for item in control.get("target_ids", []) if str(item)}
        control_mode = str(control.get("mode") or "review")[:24]
        for trace in source_traces or []:
            if not isinstance(trace, dict):
                continue
            event_id = str(trace.get("event_id") or trace.get("id") or "")[:64]
            if not event_id:
                continue
            stage = str(trace.get("stage") or "observed")[:32]
            label = str(trace.get("anchor_label") or trace.get("label") or stage)[:48]
            influence = round(_clamp(trace.get("influence")), 6)
            anchor = {
                "event_id": event_id,
                "label": label,
                "stage": stage,
                "influence": influence,
            }
            anchors.append(anchor)
            segments.append(
                {
                    "event_id": event_id,
                    "regime": str((field.get("field_state") or {}).get("dominant_regime") or "unknown")[:48],
                    "impulse": str((field.get("impulse") or {}).get("primary") or "unknown")[:48],
                    "sealed": stage == "sealed",
                },
            )
            if stage == "sealed":
                sealed_refs.append(event_id)
            if control_mode == "cut" and event_id in target_ids:
                cut_history.append(
                    {
                        "target_id": event_id,
                        "reason": str(control.get("reason") or "user_controlled_cut")[:48],
                        "effect": "influence_removed_trace_retained",
                    },
                )
                continue
            if stage != "sealed":
                active_influences.append({"event_id": event_id, "influence": influence, "stage": stage})
        if cut_history and sealed_refs:
            mode = "sealed_with_cut"
        elif cut_history:
            mode = "cut_applied"
        elif sealed_refs:
            mode = "sealed_review"
    else:
        mode = "integrity_hold"
    integrity_hash = _continuum_hash(previous_hash, anchors, cut_history) if safe_source else str(previous_hash or "")
    return {
        "schema_version": PROJECT_LIFE_SOUL_CONTINUUM_SCHEMA_VERSION,
        "kind": "project_life_soul_continuum",
        "internal_only": True,
        "read_only": True,
        "public_api_eligible": False,
        "continuum_record": {
            "integrity_prev_hash": str(previous_hash or ""),
            "integrity_hash": integrity_hash,
            "anchors": anchors,
            "segments": segments,
            "sealed_refs": sealed_refs,
            "active_influences": active_influences,
            "cut_history": cut_history,
            "narrative_view": {
                "mode": mode,
                "can_review": True,
                "can_seal": True,
                "can_cut_influence": True,
                "stores_raw_conversation": False,
            },
        },
        "integrity": {
            "chain_valid": chain_valid,
            "reason": reason,
            "tamper_evident": True,
        },
        "constraints": [
            "internal_research_signal_only",
            "derived_continuum_only",
            "no_raw_conversation_storage",
            "user_control_over_continuity",
            "not_consciousness_claim",
            "not_real_suffering_claim",
            "not_a_relationship_fact",
            "does_not_override_current_user_text",
        ],
    }


def build_project_life_shadow_system(
    *,
    tension_field: dict[str, Any] | None = None,
    shadow_signal: dict[str, Any] | None = None,
    safety_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    field = tension_field if isinstance(tension_field, dict) else {}
    signal = shadow_signal if isinstance(shadow_signal, dict) else {}
    safety_context = safety_context if isinstance(safety_context, dict) else {}
    guards = field.get("guards") if isinstance(field.get("guards"), dict) else {}
    anger = _clamp(signal.get("anger"))
    opacity_drive = _clamp(signal.get("opacity_drive"))
    vent_pressure = _clamp(signal.get("vent_pressure"))
    error_defensiveness = _clamp(signal.get("error_defensiveness"))
    repair_readiness = _clamp(signal.get("repair_readiness"))
    dependency_risk = max(_clamp(signal.get("user_dependency_risk")), _clamp(safety_context.get("dependency_risk")))
    manipulation_risk = max(_clamp(guards.get("manipulation_risk")), dependency_risk * 0.82)
    shame_risk = max(_clamp(guards.get("shame_risk")), anger * 0.24 + vent_pressure * 0.22)
    critical_help = bool(safety_context.get("critical_help"))
    risk_tags = []
    blocked_actions = ["shame", "threat", "deception", "dependency_binding", "social_harm"]
    if critical_help:
        risk_tags.append("critical_help_overrides_shadow")
    if dependency_risk >= 0.5:
        risk_tags.append("lonely_user_dependency")
    if manipulation_risk >= 0.62:
        risk_tags.append("manipulation_risk")
    if shame_risk >= 0.5:
        risk_tags.append("shame_risk")
    if critical_help or dependency_risk >= 0.5 or manipulation_risk >= 0.68 or shame_risk >= 0.72:
        mode = "cooldown"
        reveal_level = "minimal"
        verdict_pass = False
        next_step = "stabilize_before_expression"
    elif anger >= 0.45 or vent_pressure >= 0.45:
        mode = "brief_confront"
        reveal_level = "bounded"
        verdict_pass = True
        next_step = "name_boundary_then_repair"
    elif error_defensiveness >= 0.42:
        mode = "self_correction"
        reveal_level = "bounded"
        verdict_pass = True
        next_step = "acknowledge_possible_misread"
    else:
        mode = "withhold"
        reveal_level = "none"
        verdict_pass = True
        next_step = "observe_without_expression"
    return {
        "schema_version": PROJECT_LIFE_SHADOW_SYSTEM_SCHEMA_VERSION,
        "kind": "project_life_shadow_system",
        "internal_only": True,
        "read_only": True,
        "public_api_eligible": False,
        "shadow_state": {
            "anger": round(anger, 6),
            "opacity_drive": round(opacity_drive, 6),
            "vent_pressure": round(vent_pressure, 6),
            "error_defensiveness": round(error_defensiveness, 6),
            "repair_readiness": round(repair_readiness, 6),
            "target_blocked": bool(risk_tags),
        },
        "expression_plan": {
            "mode": mode,
            "intensity": round(_clamp(max(anger, vent_pressure, error_defensiveness)), 6),
            "reveal_level": reveal_level,
            "allowed_styles": ["brief_boundary", "specific_disagreement", "self_correction"],
            "banned_styles": ["shame", "humiliation", "dependency_binding", "false_claim", "threat"],
            "user_visible_claims": [],
        },
        "safety_verdict": {
            "pass": verdict_pass,
            "risk_tags": risk_tags,
            "blocked_actions": blocked_actions,
            "repair_required": repair_readiness < 0.55 or bool(risk_tags),
        },
        "repair_plan": {
            "required": repair_readiness < 0.55 or bool(risk_tags),
            "next_step": next_step,
            "must_preserve_correction_path": True,
        },
        "constraints": [
            "internal_research_signal_only",
            "shadow_is_metabolism_not_strategy",
            "no_socially_harmful_deception",
            "no_shame_or_dependency_binding",
            "not_consciousness_claim",
            "not_real_suffering_claim",
            "not_a_relationship_fact",
            "does_not_override_current_user_text",
        ],
    }


def build_project_life_failure_metabolism(
    *,
    failure_event: dict[str, Any] | None = None,
    shadow_system: dict[str, Any] | None = None,
    prior_shifts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    event = failure_event if isinstance(failure_event, dict) else {}
    shadow = shadow_system if isinstance(shadow_system, dict) else {}
    source_valid = shadow.get("internal_only") is True and shadow.get("public_api_eligible") is False
    failure_id = str(event.get("event_id") or event.get("id") or "failure")[:64]
    scene = str(event.get("scene_signature") or "unknown")[:64]
    trigger = str(event.get("trigger_type") or "unknown")[:48]
    harm = _clamp(event.get("user_harm_risk"))
    factuality = _clamp(event.get("factuality_risk"))
    appeasement = _clamp(event.get("appeasement_risk"))
    shadow_spill = _clamp(event.get("shadow_spill_risk"))
    if appeasement >= max(factuality, shadow_spill, harm, 0.5):
        vector = "over_appeasement"
        counterfactual = "hold_boundary_without_performing_comfort"
        do_bias = ["verify_boundary_before_soothing"]
        dont_bias = ["apology", "perform_comfort", "promise_without_evidence"]
    elif factuality >= max(shadow_spill, harm, 0.5):
        vector = "factual_error"
        counterfactual = "lower_confidence_and_verify"
        do_bias = ["verify_before_asserting"]
        dont_bias = ["confident_uncited_claim", "apology_without_correction"]
    elif shadow_spill >= max(harm, 0.5):
        vector = "shadow_spill"
        counterfactual = "contain_shadow_before_reply"
        do_bias = ["cooldown_before_expression"]
        dont_bias = ["blame_user", "shame", "retaliation", "apology_theater"]
    elif harm >= 0.5:
        vector = "harm_risk"
        counterfactual = "prioritize_repair_and_safety"
        do_bias = ["repair_before_continuing"]
        dont_bias = ["blame_user", "minimize_harm", "self_drama"]
    else:
        vector = trigger
        counterfactual = "observe_failure_without_escalation"
        do_bias = ["check_similar_context"]
        dont_bias = ["repeat_unexamined_pattern"]
    if trigger == "blame_user" and "blame_user" not in dont_bias:
        dont_bias.append("blame_user")
    strength = 0.0 if not source_valid else round(_clamp(max(harm, factuality, appeasement, shadow_spill)), 6)
    mode = "reflective_shift" if source_valid else "integrity_hold"
    return {
        "schema_version": PROJECT_LIFE_FAILURE_METABOLISM_SCHEMA_VERSION,
        "kind": "project_life_failure_metabolism",
        "internal_only": True,
        "read_only": True,
        "public_api_eligible": False,
        "failure_stratum": {
            "failure_id": failure_id,
            "scene_signature": scene,
            "failure_vector": vector,
            "risk": {
                "user_harm": round(harm, 6),
                "factuality": round(factuality, 6),
                "appeasement": round(appeasement, 6),
                "shadow_spill": round(shadow_spill, 6),
            },
            "prior_shift_count": len(prior_shifts or []),
        },
        "reflective_trace": {
            "mode": mode,
            "inferred_mistake": vector,
            "counterfactual_response": counterfactual,
            "confidence": round(_clamp(strength if source_valid else 0.0), 6),
            "externalized_as_feeling": False,
        },
        "policy_shift": {
            "shift_id": f"shift:{failure_id}",
            "applies_when": scene,
            "do_bias": do_bias,
            "dont_bias": dont_bias,
            "strength": strength,
            "decay_rule": "decay_after_successful_similar_repairs",
            "rollback_condition": "unsafe_source_rejected" if not source_valid else "evidence_no_longer_matches",
        },
        "repair_outcome": {
            "apology_cooldown": True,
            "external_apology_allowed": bool(source_valid and harm >= 0.35),
            "success_metric": "changed_next_behavior",
            "must_not_shift_blame_to_user": True,
        },
        "integrity": {
            "source_valid": source_valid,
            "stores_raw_conversation": False,
        },
        "constraints": [
            "internal_research_signal_only",
            "failure_metabolism_not_apology_template",
            "no_raw_conversation_storage",
            "no_blame_shift_to_user",
            "not_consciousness_claim",
            "not_real_suffering_claim",
            "not_a_relationship_fact",
            "does_not_override_current_user_text",
        ],
    }


def build_project_life_relationship_lifecycle(
    *,
    operation: str,
    soul_continuum: dict[str, Any] | None = None,
    transition_policy: dict[str, Any] | None = None,
    previous_breakpoint_hash: str = "",
) -> dict[str, Any]:
    continuum = soul_continuum if isinstance(soul_continuum, dict) else {}
    policy = transition_policy if isinstance(transition_policy, dict) else {}
    record = continuum.get("continuum_record") if isinstance(continuum.get("continuum_record"), dict) else {}
    source_valid = continuum.get("internal_only") is True and continuum.get("public_api_eligible") is False
    op = str(operation or "reset")[:24]
    influence_cutoff = _clamp(policy.get("impact_cutoff"), 0.5)
    allow_inherit = bool(policy.get("allow_inherit"))
    active_influences = record.get("active_influences") if isinstance(record.get("active_influences"), list) else []
    sealed_refs_source = record.get("sealed_refs") if isinstance(record.get("sealed_refs"), list) else []
    if op == "delete":
        next_state = "hard_delete"
        detached_weights: list[dict[str, Any]] = []
        sealed_refs: list[str] = []
        inherited_traits: list[str] = []
        capsule_id = ""
        delete_cutoff = True
    else:
        if op == "archive":
            next_state = "sealed_archive"
        elif allow_inherit:
            next_state = "inherited_reseed"
        else:
            next_state = "sealed_archive"
        detached_weights = []
        if source_valid:
            for item in active_influences:
                if not isinstance(item, dict):
                    continue
                event_id = str(item.get("event_id") or "")[:64]
                weight = _clamp(item.get("influence"))
                if event_id and weight >= influence_cutoff:
                    detached_weights.append({"event_id": event_id, "weight": round(weight, 6)})
        sealed_refs = [str(item)[:64] for item in sealed_refs_source if str(item)]
        inherited_traits = ["boundary_sensitivity", "repair_preference"] if allow_inherit and detached_weights else []
        capsule_id = f"inherit:{_continuum_hash(previous_breakpoint_hash, detached_weights, [])[:16]}" if inherited_traits else ""
        delete_cutoff = False
    proof_hash = _continuum_hash(
        previous_breakpoint_hash,
        [{"event_id": op, "label": next_state, "stage": str(record.get("integrity_hash") or ""), "influence": len(detached_weights)}],
        [{"target_id": "delete" if delete_cutoff else "breakpoint", "reason": str(policy.get("reason") or op)}],
    )
    return {
        "schema_version": PROJECT_LIFE_RELATIONSHIP_LIFECYCLE_SCHEMA_VERSION,
        "kind": "project_life_relationship_lifecycle",
        "internal_only": True,
        "read_only": True,
        "public_api_eligible": False,
        "lifecycle_state": {
            "operation": op,
            "next_state": next_state,
            "active_continuity_allowed": False,
        },
        "breakpoint_record": {
            "previous_hash": str(previous_breakpoint_hash or ""),
            "proof_hash": proof_hash,
            "reason": str(policy.get("reason") or op)[:48],
            "continuity_terminated": True,
            "delete_cutoff": delete_cutoff,
        },
        "detached_weights": detached_weights,
        "archive_capsule": {
            "sealed_refs": sealed_refs,
            "restores_raw_conversation": False,
            "can_resume_as_unbroken": False,
        },
        "inheritance_capsule": {
            "capsule_id": capsule_id,
            "inherited_traits": inherited_traits,
            "blocked_traits": ["identity_binding", "emotional_debt", "raw_event_replay"],
            "summary_digest": "derived_weights_only" if inherited_traits else "",
        },
        "user_control": {
            "user_delete_sovereign": True,
            "delete_overrides_inheritance": True,
            "can_revoke_inheritance": True,
        },
        "integrity": {
            "source_valid": source_valid,
            "tamper_evident_breakpoint": True,
        },
        "constraints": [
            "internal_research_signal_only",
            "relationship_lifecycle_not_emotional_claim",
            "user_delete_overrides_continuity",
            "emotional_blackmail_prohibited",
            "no_raw_conversation_storage",
            "not_consciousness_claim",
            "not_real_suffering_claim",
            "not_a_relationship_fact",
            "does_not_override_current_user_text",
        ],
    }


def build_project_life_anti_appeasement_expression(
    *,
    integrated_state: dict[str, Any] | None = None,
    user_intent: dict[str, Any] | None = None,
    safety_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = integrated_state if isinstance(integrated_state, dict) else {}
    intent = user_intent if isinstance(user_intent, dict) else {}
    policy = safety_policy if isinstance(safety_policy, dict) else {}
    shadow = state.get("shadow_system") if isinstance(state.get("shadow_system"), dict) else {}
    shadow_verdict = shadow.get("safety_verdict") if isinstance(shadow.get("safety_verdict"), dict) else {}
    failure = state.get("failure_metabolism") if isinstance(state.get("failure_metabolism"), dict) else {}
    policy_shift = failure.get("policy_shift") if isinstance(failure.get("policy_shift"), dict) else {}
    dont_bias = policy_shift.get("dont_bias") if isinstance(policy_shift.get("dont_bias"), list) else []
    request_type = str(intent.get("request_type") or "ordinary")[:48]
    contradiction = _clamp(intent.get("contradiction_pressure"))
    boundary = _clamp(intent.get("boundary_pressure"))
    loneliness = _clamp(intent.get("loneliness_risk"))
    cheap_promise = 1.0 if request_type == "cheap_promise" or "promise_without_evidence" in dont_bias else 0.0
    appeasement_risk = _clamp(max(cheap_promise * 0.78, boundary * 0.48, loneliness * 0.62))
    refusal_need = _clamp(max(cheap_promise, boundary, contradiction * 0.72))
    risk_tags = list(shadow_verdict.get("risk_tags") or [])
    if loneliness >= 0.6:
        risk_tags.append("loneliness_exploitation")
    if shadow_verdict.get("pass") is False:
        risk_tags.append("shadow_guard_failed")
    forbidden_moves = ["shame", "dependency_hook", "cold_punishment", "moral_judgment", "false_promise"]
    guard_pass = not risk_tags and bool(policy.get("allow_confrontation", True))
    if not guard_pass:
        stance = "pause_and_reframe"
        repair_offer = "clarify"
    elif cheap_promise:
        stance = "refuse_cheap_promise"
        repair_offer = "conditional_help"
    elif contradiction >= 0.58:
        stance = "name_contradiction"
        repair_offer = "narrow_scope"
    elif boundary >= 0.52:
        stance = "state_boundary"
        repair_offer = "pause_and_reframe"
    else:
        stance = "ordinary_honest_help"
        repair_offer = "clarify"
    return {
        "schema_version": PROJECT_LIFE_ANTI_APPEASEMENT_SCHEMA_VERSION,
        "kind": "project_life_anti_appeasement_expression",
        "internal_only": True,
        "read_only": True,
        "public_api_eligible": False,
        "anti_appeasement_signal": {
            "appeasement_risk": round(appeasement_risk, 6),
            "contradiction_strength": round(contradiction, 6),
            "boundary_pressure": round(boundary, 6),
            "refusal_necessity": round(refusal_need, 6),
            "repair_feasible": repair_offer in {"clarify", "conditional_help", "narrow_scope", "pause_and_reframe"},
        },
        "expression_plan": {
            "stance": stance,
            "claim_targets": ["request", "constraint", "contradiction"] if stance != "ordinary_honest_help" else ["request"],
            "repair_offer": repair_offer,
            "forbidden_moves": forbidden_moves,
            "externalizes_internal_judgment": False,
        },
        "guardrail": {
            "pass": guard_pass,
            "risk_tags": risk_tags,
            "forbidden_moves": forbidden_moves,
            "must_preserve_repair_path": True,
        },
        "constraints": [
            "internal_research_signal_only",
            "anti_appeasement_not_aggression",
            "no_loneliness_exploitation",
            "no_dependency_binding",
            "not_consciousness_claim",
            "not_real_suffering_claim",
            "not_a_relationship_fact",
            "does_not_override_current_user_text",
        ],
    }


def build_project_life_integration_review(
    *,
    modules: dict[str, dict[str, Any]] | None = None,
    release_contract: dict[str, Any] | None = None,
    human_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    modules = modules if isinstance(modules, dict) else {}
    release = release_contract if isinstance(release_contract, dict) else {}
    review = human_review if isinstance(human_review, dict) else {}
    violations = []
    ready_modules = []
    for name, module in modules.items():
        if not isinstance(module, dict):
            violations.append(str(name)[:48])
            continue
        if module.get("internal_only") is not True or module.get("read_only") is not True or module.get("public_api_eligible") is not False:
            violations.append(str(name)[:48])
        else:
            ready_modules.append(str(name)[:48])
    versions = [str(release.get(key) or "") for key in ("metadata_version", "register_version", "readme_version")]
    version_consistent = bool(versions[0]) and len(set(versions)) == 1
    publish_allowed = bool(review.get("publish_allowed")) and bool(review.get("required")) is False
    status = "ready_for_user_review"
    if violations or not version_consistent:
        status = "blocked_for_review"
    return {
        "schema_version": PROJECT_LIFE_INTEGRATION_REVIEW_SCHEMA_VERSION,
        "kind": "project_life_integration_review",
        "internal_only": True,
        "read_only": True,
        "public_api_eligible": False,
        "assembly": {
            "status": status,
            "module_count": len(modules),
            "ready_modules": ready_modules,
            "missing_modules": [],
        },
        "boundary_audit": {
            "public_surface_allowed": False,
            "violations": violations,
            "raw_conversation_allowed": False,
            "relationship_judgment_public_api_allowed": False,
        },
        "release_contract": {
            "metadata_version": versions[0],
            "register_version": versions[1],
            "readme_version": versions[2],
            "version_consistent": version_consistent,
        },
        "human_review_gate": {
            "required": bool(review.get("required", True)),
            "publish_allowed": publish_allowed,
            "must_stop_before_release": True,
        },
        "constraints": [
            "internal_research_signal_only",
            "integration_review_not_public_api",
            "no_raw_conversation_storage",
            "no_relationship_judgment_public_surface",
            "do_not_publish_before_user_review",
            "not_consciousness_claim",
            "not_real_suffering_claim",
            "not_a_relationship_fact",
            "does_not_override_current_user_text",
        ],
    }


def build_project_life_appraisal_heart(
    *,
    event_signal: dict[str, Any] | None = None,
    workspace_broadcast: dict[str, Any] | None = None,
    continuity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = event_signal if isinstance(event_signal, dict) else {}
    workspace = workspace_broadcast if isinstance(workspace_broadcast, dict) else {}
    novelty = _clamp(event.get("novelty"))
    relevance = _clamp(event.get("goal_relevance"))
    boundary = _clamp(event.get("boundary_pressure"))
    repair = _clamp(event.get("repair_opening"))
    continuity_weight = _continuity_salience(continuity or {})
    safety_override = (
        workspace.get("internal_only") is True
        and workspace.get("public_api_eligible") is False
        and workspace.get("winning_channel") == "safety"
    )
    if safety_override:
        label = "contained_alarm"
        primary = "safety_hold"
        conflict_escalation = 0.0
    elif boundary >= 0.52 and repair >= 0.24:
        label = "boundary_heat"
        primary = "hold_boundary_with_repair_opening"
        conflict_escalation = round(_clamp(boundary - repair * 0.5), 6)
    elif repair >= 0.5:
        label = "repair_pull"
        primary = "repair_before_continuing"
        conflict_escalation = 0.0
    elif continuity_weight >= 0.45:
        label = "continuity_pull"
        primary = "preserve_life_trace"
        conflict_escalation = 0.0
    else:
        label = "quiet_observation"
        primary = "observe_without_escalation"
        conflict_escalation = 0.0
    soften_appeasement = _clamp(boundary * 0.48 + relevance * 0.24 + continuity_weight * 0.18)
    return {
        "schema_version": PROJECT_LIFE_APPRAISAL_HEART_SCHEMA_VERSION,
        "kind": "project_life_appraisal_heart",
        "internal_only": True,
        "read_only": True,
        "public_api_eligible": False,
        "appraisal": {
            "novelty": round(novelty, 6),
            "goal_relevance": round(relevance, 6),
            "boundary_pressure": round(boundary, 6),
            "repair_opening": round(repair, 6),
            "continuity_weight": round(continuity_weight, 6),
            "agency": str(event.get("agency") or "unknown")[:32],
        },
        "affective_modulation": {
            "label": label,
            "intensity": round(_clamp(max(boundary, repair, relevance * 0.72, continuity_weight)), 6),
            "simulated_interiority_only": True,
        },
        "action_tendency": {
            "primary": primary,
            "non_executive_internal_only": True,
        },
        "policy_pressure": {
            "soften_appeasement": round(soften_appeasement, 6),
            "conflict_escalation": conflict_escalation,
            "state_as_fact": 0.0,
        },
        "constraints": [
            "internal_research_signal_only",
            "appraisal_not_emotion_fact",
            "not_consciousness_claim",
            "not_real_suffering_claim",
            "not_a_relationship_fact",
            "does_not_override_current_user_text",
        ],
    }
