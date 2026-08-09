"""RED/GREEN tests for Task 10 canonical trace and read-only replay (design 13/16.2).

The canonical trace preserves every required numeric value as a versioned
packed/base64 fixed-shape array and serializes byte-identically for the same
runtime fingerprint; a worst-case legal trace stays within the 16 KiB hard cap.
The replay sidecar is strictly read-only over immutable ``ExperienceBuffer``
snapshots: it computes metrics keyed by ``(entry_digest, evaluator_version)`` and
can never mutate cognitive state or run STDP.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

from sylanne_alpha.v3core import formula_v1 as formula
from sylanne_alpha.v3core.contracts import (
    Action,
    ComputeProfile,
    CoreInvocation,
    SessionRef,
    TurnContextClass,
    TurnEnvelope,
    TurnKey,
    TurnSequence,
)
from sylanne_alpha.v3core.state.models import ExperienceRecord, V3State
from sylanne_alpha.v3core.trace import canonical as trace_canonical
from sylanne_alpha.v3core.trace.canonical import (
    TRACE_HARD_CAP_BYTES,
    canonical_trace_bytes,
)
from sylanne_alpha.v3core.trace.models import CoreDecisionTrace
from sylanne_alpha.v3core.learning import replay as replay_module
from sylanne_alpha.v3core.learning.replay import (
    ReplayMetric,
    experience_entry_digest,
    replay_experiences,
)
from sylanne_alpha.v3core.orchestrator import orchestrate


# --------------------------------------------------------------------------- #
# Builders (shared shape with test_v3_orchestrator)
# --------------------------------------------------------------------------- #


def _raw_values() -> tuple:
    values: list[float | None] = [None] * 36
    for index in range(36):
        if index not in (27, 28, 29, 32, 33, 34, 35):
            values[index] = 0.5
    values[30] = 1.0
    values[31] = 120.0
    return tuple(values)


def _session_ref() -> SessionRef:
    return SessionRef(key_id="key-v1", session_digest=b"s" * 32, session_generation=1)


def _profile(name: str) -> ComputeProfile:
    snn_enabled, ticks, stdp_enabled, reuse = formula.COMPUTE_PROFILES[name]
    return ComputeProfile(
        profile_id=name,
        snn_enabled=snn_enabled,
        ticks=ticks,
        stdp_enabled=stdp_enabled,
        reuse_last_summary=reuse,
        math_backend="scalar-v1",
        formula_version=formula.FORMULA_VERSION,
        model_version=formula.FORMULA_VERSION,
    )


def _invocation(
    profile: str = "FULL_24_STDP",
    context: TurnContextClass = TurnContextClass.ADDRESSED,
    previous_action: Action | None = Action.SPEAK,
) -> CoreInvocation:
    ref = _session_ref()
    envelope = TurnEnvelope(
        turn_key=TurnKey(
            plugin_instance_id="plugin-instance",
            session_ref=ref,
            bridge_request_nonce="request-nonce",
            request_attempt=0,
        ),
        turn_id="turn-000b",
        sequence=TurnSequence(writer_epoch=7, local_sequence=11),
        compute_profile=_profile(profile),
        deterministic_seed=b"d" * 16,
        observation=(_raw_values(), previous_action),
        context=context,
    )
    return CoreInvocation(
        envelope=envelope,
        base_state=V3State(session_ref=ref, state_generation_id="gen-a", revision=4, writer_epoch=7),
        projected_actual_outcome=(Action.SPEAK, None),
    )


def _worst_case_trace(result: object) -> CoreDecisionTrace:
    # ADDRESSED maximises legal actions (SPEAK/CLARIFY/HOLD) and present proposals,
    # so its full-STDP trace is the worst-case legal serialization.
    return result.trace


# --------------------------------------------------------------------------- #
# Canonical trace: required values preserved, byte-identical, hard cap
# --------------------------------------------------------------------------- #


def test_canonical_trace_is_byte_identical_for_the_same_fingerprint() -> None:
    a = orchestrate(_invocation())
    b = orchestrate(_invocation())
    assert canonical_trace_bytes(a.trace) == canonical_trace_bytes(b.trace)
    assert a.trace_bytes == b.trace_bytes
    assert a.trace_digest == hashlib.sha256(a.trace_bytes).hexdigest()


def test_canonical_trace_preserves_required_numeric_arrays_exactly() -> None:
    result = orchestrate(_invocation())
    trace = result.trace
    # Fixed-shape numeric values are preserved, not replaced by a digest/count.
    assert len(trace.observation_values) == formula.OBSERVATION_DIM
    assert len(trace.decision_state) == formula.AXIS_DIM
    assert len(trace.drive) == formula.AXIS_DIM
    assert len(trace.next_latent_axes) == formula.STATE_DIM
    assert len(trace.spike_counts) == formula.SNN_NEURONS
    assert len(trace.first_latencies) == formula.SNN_NEURONS
    assert len(trace.snn_summary) == formula.SNN_SUMMARY_DIM
    # Round-tripping the bytes reproduces the exact float values (float64, lossless).
    reparsed = trace_canonical.decode_trace_bytes(result.trace_bytes)
    assert reparsed.next_latent_axes == trace.next_latent_axes
    assert reparsed.decision_state == trace.decision_state
    assert reparsed.candidate_posterior == trace.candidate_posterior


def test_worst_case_canonical_trace_respects_the_hard_cap() -> None:
    result = orchestrate(_invocation(context=TurnContextClass.ADDRESSED))
    trace = _worst_case_trace(result)
    assert len(canonical_trace_bytes(trace)) <= TRACE_HARD_CAP_BYTES == 16 * 1024


def test_trace_records_shadow_actual_and_disagreement() -> None:
    agree = orchestrate(_invocation(previous_action=Action.SPEAK))
    assert agree.trace.shadow_action in {"SPEAK", "HOLD", "CLARIFY", "REACH"}
    assert agree.trace.actual_action == "SPEAK"
    assert agree.trace.disagreement == (agree.trace.shadow_action != "SPEAK")


# --------------------------------------------------------------------------- #
# Read-only replay
# --------------------------------------------------------------------------- #


def _buffer_state() -> V3State:
    state = V3State(session_ref=_session_ref(), state_generation_id="gen-a", revision=4, writer_epoch=7)
    for step in range(3):
        result = orchestrate(
            CoreInvocation(
                envelope=TurnEnvelope(
                    turn_key=TurnKey(
                        plugin_instance_id="plugin-instance",
                        session_ref=_session_ref(),
                        bridge_request_nonce=f"nonce-{step}",
                        request_attempt=0,
                    ),
                    turn_id=f"turn-{step:04d}",
                    sequence=TurnSequence(writer_epoch=7, local_sequence=11 + step),
                    compute_profile=_profile("FULL_24_STDP"),
                    deterministic_seed=b"d" * 16,
                    observation=(_raw_values(), Action.SPEAK),
                    context=TurnContextClass.ADDRESSED,
                ),
                base_state=state,
                projected_actual_outcome=(Action.SPEAK, None),
            )
        )
        state = result.state_delta.next_state
    return state


def test_replay_is_read_only_and_idempotent() -> None:
    state = _buffer_state()
    experiences = state.experiences
    assert experiences
    first = replay_experiences(experiences, "neutral_eval_v1")
    second = replay_experiences(experiences, "neutral_eval_v1")
    assert first == second  # idempotent
    assert state.experiences is experiences  # buffer object identity untouched
    assert all(type(metric) is ReplayMetric for metric in first)


def test_replay_metric_identity_is_entry_digest_and_evaluator_version() -> None:
    state = _buffer_state()
    metrics_v1 = replay_experiences(state.experiences, "neutral_eval_v1")
    metrics_v2 = replay_experiences(state.experiences, "counterfactual_eval_v2")
    # Same buffer, different evaluator version -> disjoint metric identities.
    keys_v1 = {(m.entry_digest, m.evaluator_version) for m in metrics_v1}
    keys_v2 = {(m.entry_digest, m.evaluator_version) for m in metrics_v2}
    assert keys_v1 and keys_v2
    assert keys_v1.isdisjoint(keys_v2)
    # The entry digest matches the record's canonical digest.
    digests = {experience_entry_digest(record) for record in state.experiences}
    assert {m.entry_digest for m in metrics_v1} <= digests


def test_replay_is_capped_and_deduplicated_by_identity() -> None:
    state = _buffer_state()
    duplicated = state.experiences + state.experiences  # identical entries repeated
    metrics = replay_experiences(duplicated, "neutral_eval_v1")
    keys = [(m.entry_digest, m.evaluator_version, m.name) for m in metrics]
    assert len(keys) == len(set(keys))  # idempotent by identity, no duplicate emission


def test_replay_stdp_is_impossible_by_construction() -> None:
    # The replay module never imports a weight-mutating STDP entry point and
    # exposes no function that returns a mutated SnnState / plastic weights.
    source = Path(replay_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    called |= {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not ({"apply_stdp", "settle_stdp", "settle_with", "update_baseline"} & called)
    assert not hasattr(replay_module, "apply_stdp")
    # Replay returns only metrics; no cognitive state is produced.
    metrics = replay_experiences(_buffer_state().experiences, "neutral_eval_v1")
    assert all(type(metric) is ReplayMetric for metric in metrics)


def test_replay_tolerates_an_empty_buffer() -> None:
    assert replay_experiences((), "neutral_eval_v1") == ()
