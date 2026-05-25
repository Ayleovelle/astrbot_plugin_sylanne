"""Sylanne-Embodiment: Prompt surface rendering.

Extracted from kernel.py to keep the kernel focused on tick/decide/guard.
Contains prompt fragment generation, context bus assembly, host payload
construction, and diagnostics rendering.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .kernel import AlphaKernel


def render_prompt_fragment(
    kernel: "AlphaKernel", decision: dict[str, Any], guard: dict[str, Any]
) -> str:
    """Render the full prompt fragment string for host injection."""
    reason = guard["reason"] if not guard["allowed"] else decision["reason"]
    relational_time = kernel.relational_time or kernel._relational_time_layer(
        current=kernel.last_event, previous=kernel.previous_event
    )
    current_time = relational_time["current_time"]
    time_gap = relational_time["time_gap"]
    relational_fragment = (
        "[sylanne_relational_time] "
        f"current_time={current_time['local_datetime']}; "
        f"timezone={current_time['timezone']}; "
        f"time_gap={time_gap['label']}; "
        f"gap_seconds={time_gap['seconds']}; "
        f"day_relation={relational_time['day_relation']}"
    )
    relationship_memory = kernel.body.relationship_memory()
    signals = relationship_memory["signals"]
    memory_fragment = (
        "[sylanne_relationship_memory] "
        f"phase={relationship_memory['continuity']['phase']}; "
        f"weight={relationship_memory['continuity']['weight']}; "
        f"preference_count={signals['preference_count']}; "
        f"boundary_count={signals['boundary_count']}; "
        f"progress_count={signals['progress_count']}; "
        f"repair_count={signals['repair_count']}; "
        "constraints=no_raw_text,session_local,does_not_override_current_user_text"
    )
    integrated_self = kernel._integrated_self(decision, guard)
    intent = integrated_self["intent_plan"]
    self_fragment = (
        "[sylanne_integrated_self] "
        f"posture={integrated_self['response_posture']}; "
        f"primary_goal={intent['primary_goal']}; "
        f"lanes={','.join(intent['lanes'])}; "
        f"safety_priority={integrated_self['risk']['safety_priority']}; "
        "constraints=current_user_text_priority,no_raw_text,no_relationship_fact_without_user_confirmation"
    )
    affect = kernel._affect_dynamics()
    personality = kernel._personality()
    moral = kernel._moral_repair_state()
    fallibility = kernel._fallibility_state()
    group = kernel._group_atmosphere()
    proactive = kernel._proactive_source(decision, guard)
    bus = render_prompt_context_bus(kernel, integrated_self=integrated_self)
    comp_emotion = kernel._computation_emotion_overlay()
    # Arbitrate between two emotion signals: SSM continuous dynamics vs body affect
    comp_expression_drive = comp_emotion.get("expression_drive", 0.0)
    body_expression_drive = affect["body_coupling"]["expression_drive"]
    if abs(comp_expression_drive - body_expression_drive) > 0.3:
        # Large divergence: trust SSM continuous dynamics
        arbitrated_expression_drive = comp_expression_drive
    else:
        # Small divergence: average
        arbitrated_expression_drive = (
            comp_expression_drive + body_expression_drive
        ) / 2.0
    # Expression intensity signal: modulates LLM reply tone
    expr_intensity = kernel.computation.expression.expression_intensity()
    if expr_intensity > 0.8:
        expression_tendency = "[表达倾向:急切]"
    elif expr_intensity > 0.3:
        expression_tendency = "[表达倾向:正常]"
    else:
        expression_tendency = ""
    extra_fragments = [
        f"[sylanne_affect_dynamics] repair_drive={affect['body_coupling']['repair_drive']}; expression_drive={arbitrated_expression_drive:.6f}; constraints=weak_style_modulation_only,no_medicalized_body_claims",
        f"[sylanne_computation_emotion] warmth={comp_emotion.get('warmth', 0.0):.4f}; arousal={comp_emotion.get('arousal', 0.0):.4f}; valence={comp_emotion.get('valence', 0.0):.4f}; tension={comp_emotion.get('tension', 0.0):.4f}; expression_drive={comp_emotion.get('expression_drive', 0.0):.4f}",
        f"[sylanne_personality] cadence={personality['voice']['cadence']}; boundary={personality['voice']['boundary']}; drift_events={personality['drift']['events']}; constraints=bounded_offsets_not_persona_rewrite,no_raw_text",
        f"[sylanne_moral_repair] state={moral['state']}; events={moral['events']}; constraints=brief_repair_only,no_guilt_loop",
        f"[sylanne_fallibility] claim_caution={fallibility['claim_caution']}; events={fallibility['events']}; constraints=admit_uncertainty,correct_once",
        f"[sylanne_group_atmosphere] mode={group['mode']}; joinability={group['joinability']}; interrupt_risk={group['interrupt_risk']}; constraints=no_group_mind_reading,no_speaking_for_others",
        f"[sylanne_proactive_source] decision={proactive['decision']}; body_need={proactive['drivers']['body_need']}; relationship_continuity={proactive['drivers']['relationship_continuity']}; constraints=current_user_sovereignty_first,no_private_memory_recall",
        f"[sylanne_prompt_context_bus] primary={bus['primary']}; posture={bus['posture']}; fragments={','.join(bus['fragments'])}; policy={bus['policy']}",
    ]
    base = (
        f"Sylanne 4.0 body: action={decision['action']}; reason={reason}; keep user sovereignty first.\n{relational_fragment}\n{memory_fragment}\n{self_fragment}\n"
        + "\n".join(extra_fragments)
    )
    if expression_tendency:
        base = f"{expression_tendency}\n{base}"
    return base


SCHEMA_PROMPT_CONTEXT_BUS_VERSION = "sylanne.alpha.prompt_context_bus.v1"


def render_prompt_context_bus(
    kernel: "AlphaKernel", *, integrated_self: dict[str, Any]
) -> dict[str, Any]:
    """Assemble the prompt context bus payload."""
    fragments = [
        "relational_time",
        "relationship_memory",
        "integrated_self",
        "affect_dynamics",
        "personality",
        "moral_repair",
        "fallibility",
        "group_atmosphere",
        "proactive_source",
    ]
    return {
        "schema_version": SCHEMA_PROMPT_CONTEXT_BUS_VERSION,
        "kind": "prompt_context_bus",
        "internal_only": True,
        "read_only": True,
        "fragments": fragments,
        "primary": "integrated_self",
        "posture": integrated_self["response_posture"],
        "policy": "safety_first_single_arbitration",
        "constraints": [
            "current_user_text_priority",
            "derived_fields_only",
            "drop_to_minimal_prompt_on_conflict",
        ],
    }


def render_host_payload(
    kernel: "AlphaKernel", decision: dict[str, Any], guard: dict[str, Any]
) -> dict[str, Any]:
    """Build the full host payload dict."""
    should_send = bool(
        guard["allowed"] and decision["action"] in {"express", "reach_out", "repair"}
    )
    advice = "send" if should_send else "wait"
    if decision["action"] == "withdraw":
        advice = "withdraw"
    if decision["action"] == "repair" and guard["allowed"]:
        advice = "repair"
    integrated_self = kernel._integrated_self(decision, guard)
    affect_dynamics = kernel._affect_dynamics()
    personality = kernel._personality()
    moral_repair = kernel._moral_repair_state()
    fallibility = kernel._fallibility_state()
    shadow_memory = kernel.body.shadow_memory()
    group_atmosphere = kernel._group_atmosphere()
    proactive_source = kernel._proactive_source(decision, guard)
    prompt_bus = render_prompt_context_bus(kernel, integrated_self=integrated_self)
    # Overlay computation-layer emotion onto affect_dynamics
    computation_emotion = kernel._computation_emotion_overlay()
    if computation_emotion:
        affect_dynamics["computation_emotion"] = computation_emotion
    # Include computation recalled/holes from last tick
    comp_result = getattr(kernel, "_last_computation_result", None) or {}
    return {
        "kind": "proactive_dispatch"
        if decision["action"] in {"express", "reach_out", "repair"}
        else "body_surface",
        "action": decision["action"],
        "advice": advice,
        "should_send": should_send,
        "should_wait": decision["action"] in {"wait", "hold"} or advice == "wait",
        "needs_repair": kernel.body.needs["need_repair"] > 0.2,
        "should_withdraw": decision["action"] == "withdraw",
        "reason": guard["reason"] if not guard["allowed"] else decision["reason"],
        "reason_code": decision.get("reason_code", "life_rhythm"),
        "next_check_seconds": kernel._next_check_seconds(decision, guard),
        "relational_time": kernel.relational_time
        or kernel._relational_time_layer(
            current=kernel.last_event, previous=kernel.previous_event
        ),
        "relationship_memory": kernel.body.relationship_memory(),
        "integrated_self": integrated_self,
        "affect_dynamics": affect_dynamics,
        "personality": personality,
        "moral_repair": moral_repair,
        "fallibility": fallibility,
        "shadow_memory": shadow_memory,
        "group_atmosphere": group_atmosphere,
        "proactive_source": proactive_source,
        "prompt_context_bus": prompt_bus,
        "prompt_fragment": render_prompt_fragment(kernel, decision, guard),
        "recalled": comp_result.get("recalled", []),
        "holes": comp_result.get("holes", []),
    }


def render_diagnostics(
    kernel: "AlphaKernel",
    decision: dict[str, Any],
    guard: dict[str, Any],
    workset: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the diagnostics payload."""
    vector_summary = kernel._vector_summary()
    body = kernel.body.to_dict()
    risk_score = kernel._risk_score()
    return {
        "life_principle": "I'm living a life by design",
        "load": body["mortality"]["load"],
        "interruption_budget": body["immunity"]["interruption_budget"],
        "vector_summary": vector_summary,
        "workset": {
            "mode": (workset or {}).get("mode", "fragment"),
            "primary_department": (workset or {})
            .get("coordination", {})
            .get("primary_department", "none"),
            "fast_path": (workset or {}).get("coordination", {}).get("fast_path", []),
            "slow_path": (workset or {}).get("coordination", {}).get("slow_path", []),
        },
        "body_state": {
            "pulse": body["pulse"],
            "temperature": body["temperature"],
            "mortality": body["mortality"],
        },
        "needs": body["needs"],
        "memory": {
            "trace_count": len(body["memory"]["traces"]),
            "recent": body["memory"]["traces"][-3:],
        },
        "boundary": {
            "pressure": body["immunity"]["boundary_pressure"],
            "sovereignty": body["immunity"]["sovereignty"],
            "paused": body["immunity"]["paused"],
            "guard_flags": list(guard["flags"]),
        },
        "agency": {
            "action": decision["action"],
            "reason": guard["reason"] if not guard["allowed"] else decision["reason"],
            "reason_code": decision.get("reason_code", "life_rhythm"),
            "allowed": guard["allowed"],
        },
        "risk": {
            "score": risk_score,
            "reason": guard["reason"] if not guard["allowed"] else "within body limits",
        },
    }
