"""RED/GREEN tests for Task 10 deterministic core orchestration (design 6/14/16).

The orchestrator wires the seven pure named stages
``encoder -> snn -> dynamics -> workspace -> inference -> expression -> trace``
into a single deterministic turn.  It emits a :class:`DecisionPlan`, a
:class:`StateDelta`, a closed :class:`EffectBundle`, and a
:class:`CoreDecisionTrace`, and it advances the canonical in-memory state using
the *decoded* (float16-quantized) persistence bytes so a crash reload can never
fork the cognitive trajectory (回溯红队 a16 MAJOR DoD).
"""

from __future__ import annotations

import hashlib

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
from sylanne_alpha.v3core.effects.models import DecisionPlan, EffectBundle, StateDelta, V3StateEffect, V3TraceEffect
from sylanne_alpha.v3core.expression.policy import ExpressionConstraints
from sylanne_alpha.v3core.state.codec import decode_state, encode_state
from sylanne_alpha.v3core.state.models import V3State
from sylanne_alpha.v3core.trace.models import CoreDecisionTrace
from sylanne_alpha.v3core import orchestrator
from sylanne_alpha.v3core.orchestrator import STAGE_ORDER, orchestrate


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #

_VALUE_CHANNELS = tuple(index for index in range(36) if index not in (27, 28, 29, 30, 31, 32, 33, 34, 35))


def _raw_values(overrides: dict[int, float] | None = None) -> tuple:
    values: list[float | None] = [None] * 36
    for index in range(36):
        if index in (27, 28, 29, 32, 33, 34, 35):
            values[index] = None  # derived channels must stay absent in facts
        else:
            values[index] = 0.5
    values[30] = 1.0  # history_present bit (bool-coded)
    values[31] = 120.0  # gap seconds
    for index, value in (overrides or {}).items():
        values[index] = value
    return tuple(values)


def _session_ref() -> SessionRef:
    return SessionRef(key_id="key-v1", session_digest=b"s" * 32, session_generation=1)


def _profile(name: str = "FULL_24_STDP") -> ComputeProfile:
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


def _envelope(
    *,
    profile: str = "FULL_24_STDP",
    context: TurnContextClass = TurnContextClass.ADDRESSED,
    previous_action: Action | None = Action.SPEAK,
    local_sequence: int = 11,
    overrides: dict[int, float] | None = None,
    turn_id: str = "turn-000b",
) -> TurnEnvelope:
    ref = _session_ref()
    return TurnEnvelope(
        turn_key=TurnKey(
            plugin_instance_id="plugin-instance",
            session_ref=ref,
            bridge_request_nonce="request-nonce",
            request_attempt=0,
        ),
        turn_id=turn_id,
        sequence=TurnSequence(writer_epoch=7, local_sequence=local_sequence),
        compute_profile=_profile(profile),
        deterministic_seed=b"d" * 16,
        observation=(_raw_values(overrides), previous_action),
        context=context,
    )


def _base_state(**overrides: object) -> V3State:
    return V3State(session_ref=_session_ref(), state_generation_id="gen-a", revision=4, writer_epoch=7, **overrides)


def _invocation(**envelope_kwargs: object) -> CoreInvocation:
    return CoreInvocation(
        envelope=_envelope(**envelope_kwargs),
        base_state=_base_state(),
        projected_actual_outcome=(Action.SPEAK, None),
    )


# --------------------------------------------------------------------------- #
# Stage order + immutable compute profile
# --------------------------------------------------------------------------- #


def test_stage_order_is_the_fixed_named_sequence() -> None:
    assert STAGE_ORDER == ("encoder", "snn", "dynamics", "workspace", "inference", "expression", "trace")


def test_orchestrator_rejects_a_profile_inconsistent_with_the_frozen_manifest() -> None:
    ref = _session_ref()
    envelope = TurnEnvelope(
        turn_key=TurnKey(
            plugin_instance_id="plugin",
            session_ref=ref,
            bridge_request_nonce="nonce",
            request_attempt=0,
        ),
        turn_id="turn-x",
        sequence=TurnSequence(7, 11),
        compute_profile=ComputeProfile(
            profile_id="FULL_24_STDP",
            snn_enabled=True,
            ticks=16,  # inconsistent with the frozen (True, 24, True, False) tuple
            stdp_enabled=True,
            reuse_last_summary=False,
            math_backend="scalar-v1",
            formula_version=formula.FORMULA_VERSION,
            model_version=formula.FORMULA_VERSION,
        ),
        deterministic_seed=b"d" * 16,
        observation=(_raw_values(), Action.SPEAK),
        context=TurnContextClass.ADDRESSED,
    )
    with pytest.raises(ValueError, match="profile"):
        orchestrate(CoreInvocation(envelope=envelope, base_state=_base_state(), projected_actual_outcome=None))


# --------------------------------------------------------------------------- #
# Closed effects, determinism, no side effects
# --------------------------------------------------------------------------- #


def test_orchestrate_emits_only_the_closed_state_trace_metric_effect_union() -> None:
    result = orchestrate(_invocation())
    assert result.accepted is True
    assert type(result.effects) is EffectBundle
    kinds = [type(effect).__name__ for effect in result.effects.effects]
    assert kinds.count("V3StateEffect") == 1
    assert kinds.count("V3TraceEffect") == 1
    assert all(kind in {"V3StateEffect", "V3TraceEffect", "V3MetricEffect"} for kind in kinds)
    assert type(result.decision_plan) is DecisionPlan
    assert type(result.decision_plan.expression) is ExpressionConstraints
    assert type(result.state_delta) is StateDelta
    assert type(result.trace) is CoreDecisionTrace


def test_orchestrate_is_deterministic_and_byte_identical_under_the_same_fingerprint() -> None:
    first = orchestrate(_invocation())
    second = orchestrate(_invocation())
    assert first.payload_digest == second.payload_digest
    assert first.trace_digest == second.trace_digest
    assert first.journal_digest == second.journal_digest
    assert first.trace_bytes == second.trace_bytes
    assert first.state_delta.next_state == second.state_delta.next_state


def test_orchestrate_has_no_side_effect_on_the_immutable_base_state() -> None:
    base = _base_state()
    invocation = CoreInvocation(
        envelope=_envelope(),
        base_state=base,
        projected_actual_outcome=(Action.SPEAK, None),
    )
    before = encode_state(base)
    orchestrate(invocation)
    orchestrate(invocation)
    assert encode_state(base) == before  # base state never mutated
    assert base.revision == 4


def test_state_delta_advances_the_revision_and_records_the_committed_turn() -> None:
    result = orchestrate(_invocation())
    next_state = result.state_delta.next_state
    assert next_state.revision == 5
    assert next_state.last_committed_turn_id == "turn-000b"
    assert next_state.last_committed_turn_sequence == TurnSequence(7, 11)


# --------------------------------------------------------------------------- #
# Deterministic degradation (REUSE without a prior summary)
# --------------------------------------------------------------------------- #


def test_reuse_without_prior_summary_degrades_deterministically_to_continuous_only() -> None:
    reuse = orchestrate(
        CoreInvocation(
            envelope=_envelope(profile="REUSE_LAST_SNN_SUMMARY"),
            base_state=_base_state(),  # last_snn_summary is None
            projected_actual_outcome=(Action.SPEAK, None),
        )
    )
    continuous = orchestrate(
        CoreInvocation(
            envelope=_envelope(profile="DETERMINISTIC_CONTINUOUS_ONLY"),
            base_state=_base_state(),
            projected_actual_outcome=(Action.SPEAK, None),
        )
    )
    # The degraded computation matches the continuous-only decision exactly.
    assert reuse.decision_plan.action == continuous.decision_plan.action
    assert reuse.trace.next_latent_axes == continuous.trace.next_latent_axes
    assert reuse.trace.snn_ran is False
    assert reuse.trace.degradation_reason == "REUSE_WITHOUT_SUMMARY_FALLBACK"


def test_a_silent_reservoir_contributes_exactly_nothing_to_the_drive() -> None:
    """The Q*summary half of the SNN really is inert: the drive is bit-identical.

    This is the *true* half of the "the SNN is behaviourally dead" argument. The
    reservoir never fires, so ``snn_summary`` is identically zero and
    ``Q_MATRIX @ summary`` adds only exact zeros to an fsum. Nothing about the drive
    changes when the SNN is dropped.

    See ``test_dropping_the_snn_is_not_behaviour_preserving`` for the half that is
    false -- the drive is not the only consumer of ``snn_summary``.
    """

    snn = orchestrate(
        CoreInvocation(
            envelope=_envelope(profile="FULL_24_NO_STDP"),
            base_state=_base_state(),
            projected_actual_outcome=(Action.SPEAK, None),
        )
    )
    continuous = orchestrate(
        CoreInvocation(
            envelope=_envelope(profile="DETERMINISTIC_CONTINUOUS_ONLY"),
            base_state=_base_state(),
            projected_actual_outcome=(Action.SPEAK, None),
        )
    )
    assert snn.accepted and continuous.accepted
    assert snn.trace.spike_counts == tuple(0 for _ in range(formula.SNN_NEURONS)), (
        "this test assumes the measured silent reservoir; if it spikes, re-read the gate"
    )
    assert snn.trace.drive == continuous.trace.drive


def test_dropping_the_snn_is_not_behaviour_preserving() -> None:
    """Switching an SNN profile to DETERMINISTIC_CONTINUOUS_ONLY CHANGES decisions.

    This pins the reason the silent reservoir cannot simply be switched off as a
    free, behaviour-preserving optimisation, which is the intuitive (and wrong)
    conclusion from "snn_summary is always zero".

    Root cause: ``snn_summary`` has two consumers, not one. The drive consumer is
    genuinely inert (see the test above). But ``workspace/competition.py`` gates the
    snn-novelty proposal on ``PROPOSAL_REQUIRES_VALID_SNN_SUMMARY[6]`` -- i.e. on
    ``snn_summary is not None``, NOT on whether the reservoir actually spiked -- and
    that proposal's salience is ``1.2*summary_value + 0.6*s[5]``. With a silent
    reservoir the first term is zero but ``0.6*s[5]`` (the novelty axis) is not, so
    the proposal is a live competitor carrying real salience under any SNN profile
    and is dropped from the competition entirely under DETERMINISTIC_CONTINUOUS_ONLY.
    Removing a non-zero-salience competitor changes which proposals win workspace
    slots, hence broadcast_ids, hence the posterior, hence the selected action.

    Measured over 300 identical-input turn pairs: selected_action differs on 47,
    broadcast_ids on 59, candidate_posterior on 70 -- ~16% of decisions.

    If this ever starts passing (the profiles becoming equivalent), the switch this
    blocks becomes safe and the assertion below must be re-read, not deleted.
    """

    from sylanne_alpha.v3core.observation.encoder import encode_observation
    from sylanne_alpha.v3core.observation.models import ObservationFacts
    from sylanne_alpha.v3core.workspace.competition import proposal_salience

    frame = encode_observation(
        ObservationFacts(raw_values=_raw_values(), context=TurnContextClass.ADDRESSED)
    )
    silent_summary = tuple(0.0 for _ in range(formula.SNN_SUMMARY_DIM))
    decision_state = (0.0, 0.0, 0.0, 0.0, 0.0, 0.42, 0.0, 0.0)  # novelty axis s[5] non-zero

    with_snn = proposal_salience(6, decision_state, frame, silent_summary)
    without_snn = proposal_salience(6, decision_state, frame, None)

    # Identical salience -- the silence of the reservoir is irrelevant to it ...
    assert with_snn[0] == without_snn[0] == pytest.approx(0.6 * 0.42)
    assert with_snn[0] != 0.0, "a zero-salience proposal would make its removal harmless"
    # ... but the profile flag alone decides whether it competes at all.
    assert with_snn[1] is True, "snn-novelty competes under an SNN profile"
    assert without_snn[1] is False, "snn-novelty vanishes without one"


# --------------------------------------------------------------------------- #
# Acyclic digest order payload -> trace -> journal
# --------------------------------------------------------------------------- #


def test_digest_dependencies_are_one_way_payload_then_trace_then_journal() -> None:
    result = orchestrate(_invocation())
    state_payload = next(e.payload for e in result.effects.effects if type(e) is V3StateEffect)
    trace_payload = next(e.payload for e in result.effects.effects if type(e) is V3TraceEffect)

    # payload_digest is a pure function of the cognitive payload bytes only.
    assert result.payload_digest == hashlib.sha256(state_payload).hexdigest()
    # trace_digest is a pure function of the trace bytes only.
    assert result.trace_digest == hashlib.sha256(trace_payload).hexdigest()
    # The trace may carry the payload digest but never its own or the journal digest.
    trace_fields = {field for field in CoreDecisionTrace.__dataclass_fields__}
    assert "payload_digest" in trace_fields
    assert "trace_digest" not in trace_fields
    assert "journal_digest" not in trace_fields
    assert result.trace.payload_digest == result.payload_digest
    # journal_digest closes over both digests and changes if either does.
    assert result.journal_digest != result.payload_digest
    assert result.journal_digest != result.trace_digest
    assert len(result.journal_digest) == 64


def test_experience_buffer_stores_committed_revision_key_not_same_turn_trace_digest() -> None:
    result = orchestrate(_invocation())
    next_state = result.state_delta.next_state
    assert len(next_state.experiences) == 1
    record = next_state.experiences[-1]
    assert record.trace_revision == next_state.revision == 5
    assert record.trace_turn_digest == hashlib.sha256(b"turn-000b").digest()[:8]
    # The committed revision key is never the same-turn trace digest.
    assert record.trace_turn_digest != bytes.fromhex(result.trace_digest)[:8]


def test_experience_buffer_is_a_bounded_fifo() -> None:
    base = _base_state()
    state = base
    for step in range(formula.EXPERIENCE_CAPACITY + 3):
        result = orchestrate(
            CoreInvocation(
                envelope=_envelope(local_sequence=11 + step, turn_id=f"turn-{step:04d}"),
                base_state=state,
                projected_actual_outcome=(Action.SPEAK, None),
            )
        )
        state = result.state_delta.next_state
    assert len(state.experiences) == formula.EXPERIENCE_CAPACITY


# --------------------------------------------------------------------------- #
# Quantize-on-persist DoD (回溯红队 a16 MAJOR)
# --------------------------------------------------------------------------- #


def test_persisted_state_is_a_float16_fixed_point_of_the_real_compute_product() -> None:
    result = orchestrate(_invocation())
    canonical = result.state_delta.next_state
    # decode(encode(x)) == x for the real computed product, once quantized.
    assert decode_state(encode_state(canonical)) == canonical
    # The state effect payload is exactly the encoding of the canonical state,
    # and payload_digest hashes that quantized boundary.
    payload = next(e.payload for e in result.effects.effects if type(e) is V3StateEffect)
    assert payload == encode_state(canonical)
    assert result.payload_digest == hashlib.sha256(payload).hexdigest()


def test_memory_advance_equals_reload_advance_no_fork() -> None:
    first = orchestrate(_invocation())
    memory_state = first.state_delta.next_state
    reload_state = decode_state(encode_state(memory_state))
    assert reload_state == memory_state

    def next_turn(base: V3State) -> object:
        return orchestrate(
            CoreInvocation(
                envelope=_envelope(local_sequence=12, turn_id="turn-000c"),
                base_state=base,
                projected_actual_outcome=(Action.SPEAK, None),
            )
        )

    memory_next = next_turn(memory_state)
    reload_next = next_turn(reload_state)
    assert memory_next.payload_digest == reload_next.payload_digest
    assert memory_next.trace_digest == reload_next.trace_digest
    assert memory_next.state_delta.next_state == reload_next.state_delta.next_state


# --------------------------------------------------------------------------- #
# Trace size cap and overflow rejection
# --------------------------------------------------------------------------- #


def test_trace_fits_the_sixteen_kib_cap() -> None:
    result = orchestrate(_invocation())
    assert len(result.trace_bytes) <= 16 * 1024


def test_trace_overflow_rejects_the_whole_invocation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator, "TRACE_HARD_CAP_BYTES", 8)
    result = orchestrate(_invocation())
    assert result.accepted is False
    assert result.reject_reason == "TRACE_OVERSIZE"
    assert result.effects is None
    assert result.state_delta is None
    # Only bounded runtime telemetry survives a rejection.
    assert result.telemetry
