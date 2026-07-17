"""Seeded property/invariant loops for the deterministic v3 core (plan Task 15).

WHY this file exists
--------------------
The per-stage RED/GREEN suites (``test_v3_orchestrator.py``, ``test_v3_stdp_plasticity.py``,
``test_v3_encoded_export.py``, ...) pin *chosen* examples: one envelope, one profile, one
hand-picked weight vector.  They prove the stages do the right thing on the inputs the author
thought of.  They cannot prove the core holds together over an *input distribution* — and the
v3 core makes distributional promises that a fixed example can never falsify:

* malformed facts must fail **closed** at a boundary and never leave a half-built state;
* an *invalid* (masked-off) channel must be inert — its value can never reach the drive or
  the decision (``observation/models.py``: "every downstream consumer gates on ``valid_mask``";
  ``compute_drive``: "changing an invalid channel's raw value can never change the drive");
* Dale signs and the incoming-L1 budget must hold *after every update*, not just after one;
* the same fingerprint must produce byte-identical bytes, and the same revision must advance
  at most once, no matter which turn you are on.

Each property below therefore has a hand-written **fixed-seed loop** (``random.Random(SEED)``
over N iterations) as its authoritative implementation.  Hypothesis is installed and adds
*extra* coverage at the end of the file, but it is never the sole implementation of any
acceptance property: delete the hypothesis section and every property is still proven here.
No ``pytest.importorskip``, no skips — these always run.

Two measured production defects shape the loop budgets (diagnosed elsewhere; NOT re-litigated,
NOT worked around, merely not assumed away):

* the SNN never spikes through ``orchestrate`` (max membrane voltage ~0.32 vs the 0.65
  threshold floor), so no property here assumes a spike ever occurs;
* after ~358 turns of ordinary input the threshold clamps to exactly 0.65 and
  ``float16(0.65) = 0.64990 < 0.65`` fails the codec bound check, so ``orchestrate`` returns
  ``accepted=False`` / ``STATE_QUANTIZE_ERROR`` forever after.  Every seeded loop therefore
  stays well under ~300 turns per session and no loop assumes ``.trace`` exists without first
  checking ``result.accepted``.

Synthetic/seeded data only: this file never reads real AstrBot history and never sets
``ASTRBOT_DATA_DIR``.
"""

from __future__ import annotations

import math
import random

import pytest
# Hypothesis is OPTIONAL, additive coverage. It is not in requirements.txt (a
# test-only dependency must not ship to plugin users), so an unguarded import
# would take this entire mandatory acceptance-property file down at COLLECTION
# on any checkout without it -- and Task 16's `pytest -q` with it. The guard is
# not `pytest.importorskip` (forbidden, and it would skip the whole module):
# every acceptance property below is proven by its fixed-seed loop and ALWAYS
# runs. Only the additive `test_hypothesis_*` section depends on this import.
try:
    from hypothesis import HealthCheck, given, settings
    from hypothesis import strategies as hyp

    HAS_HYPOTHESIS = True
except ImportError:  # pragma: no cover - exercised only on a hypothesis-less checkout
    HAS_HYPOTHESIS = False

from scripts import v3_export
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
from sylanne_alpha.v3core.dynamics.multiscale import advance_dynamics
from sylanne_alpha.v3core.features import decision_state
from sylanne_alpha.v3core.inference.policy_scorer import score_policy
from sylanne_alpha.v3core.observation.encoder import encode_observation
from sylanne_alpha.v3core.observation.models import (
    DERIVED_CHANNELS,
    ObservationFacts,
    ObservationFrame,
)
from sylanne_alpha.v3core.orchestrator import orchestrate
from sylanne_alpha.v3core.state.codec import encode_state
from sylanne_alpha.v3core.state.models import (
    PLASTIC_WEIGHT_BOUNDS,
    THRESHOLD_BOUNDS,
    VOLTAGE_BOUNDS,
    V3State,
)
from sylanne_alpha.v3core.workspace.competition import run_workspace

# One seed per property so a failure names its own loop and reproduces in isolation.
SEED_MALFORMED = 2718
SEED_BOUNDS = 31415
SEED_NONINTERFERENCE = 16180
SEED_DALE = 14142
SEED_LEGAL = 57721
SEED_TRACE = 26458
SEED_CAS = 12345
SEED_DATASET = 86420

#: The 29 channels that carry raw facts; the other seven are derived and must stay ``None``.
VALUE_CHANNELS = tuple(index for index in range(formula.OBSERVATION_DIM) if index not in DERIVED_CHANNELS)
#: Channels the encoder reads through ``_boolean`` — any nonzero float means "true".
BOOL_CHANNELS = (22, 30)
#: The gap channel is clamped at 86400 s by the encoder.
GAP_CHANNEL = 31

#: Derived straight from the frozen manifest (never restated by hand) so the legal-action
#: property can never drift away from the scorer's own masks.
LEGAL_ACTIONS_BY_CONTEXT = v3_export.LEGAL_ACTIONS_BY_CONTEXT

CONTEXTS = tuple(TurnContextClass)
_L1_LIMIT = formula.RECURRENT_FIXED_INCOMING_L1_LIMIT
_EXCITATORY_BOUNDS = formula.SNN_EXCITATORY_WEIGHT_BOUNDS
_INHIBITORY_BOUNDS = formula.SNN_INHIBITORY_WEIGHT_BOUNDS


# --------------------------------------------------------------------------- #
# Builders (same shape as tests/test_v3_orchestrator.py)
# --------------------------------------------------------------------------- #


def _raw_values(overrides: dict[int, float | None] | None = None) -> tuple:
    """A well-formed 36-slot raw fact vector; derived channels stay absent."""

    values: list[float | None] = [None] * formula.OBSERVATION_DIM
    for index in VALUE_CHANNELS:
        values[index] = 0.5
    values[30] = 1.0  # history_present bit (bool-coded)
    values[GAP_CHANNEL] = 120.0
    for index, value in (overrides or {}).items():
        values[index] = value
    return tuple(values)


def _random_raw_values(rng: random.Random, *, drop: frozenset[int] = frozenset()) -> tuple:
    """A random but *well-formed* fact vector; channels in ``drop`` are genuinely missing."""

    values: list[float | None] = [None] * formula.OBSERVATION_DIM
    for index in VALUE_CHANNELS:
        if index in drop:
            continue  # a genuinely missing fact stays None -> invalid
        if index in BOOL_CHANNELS:
            values[index] = float(rng.randint(0, 1))
        elif index == GAP_CHANNEL:
            values[index] = float(rng.randint(0, 90_000))  # deliberately past the 86400 clamp
        else:
            values[index] = rng.uniform(-3.0, 3.0)  # normalizers must absorb out-of-range facts
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
    raw: tuple | None = None,
    turn_id: str = "turn-000b",
    seed: bytes = b"d" * 16,
) -> TurnEnvelope:
    return TurnEnvelope(
        turn_key=TurnKey(
            plugin_instance_id="plugin-instance",
            session_ref=_session_ref(),
            bridge_request_nonce="request-nonce",
            request_attempt=0,
        ),
        turn_id=turn_id,
        sequence=TurnSequence(writer_epoch=7, local_sequence=local_sequence),
        compute_profile=_profile(profile),
        deterministic_seed=seed,
        observation=(_raw_values() if raw is None else raw, previous_action),
        context=context,
    )


def _base_state(**overrides: object) -> V3State:
    return V3State(session_ref=_session_ref(), state_generation_id="gen-a", revision=4, writer_epoch=7, **overrides)


def _invocation(base: V3State | None = None, **envelope_kwargs: object) -> CoreInvocation:
    return CoreInvocation(
        envelope=_envelope(**envelope_kwargs),
        base_state=_base_state() if base is None else base,
        projected_actual_outcome=(Action.SPEAK, None),
    )


def _fixed_incoming_l1(post: int) -> float:
    """Incoming L1 of the *non-plastic* edges of one neuron (reference, not the SUT).

    Mirrors ``tests/test_v3_stdp_plasticity.py::_fixed_l1`` — the plastic (E->E) edges are
    excluded because they are exactly the ones carried in ``SnnState.plastic_weights``.
    """

    return sum(
        abs(formula.recurrent_initial_weight(post, pre))
        for pre in formula.RECURRENT_TOPOLOGY[post]
        if not (post < formula.SNN_EXCITATORY and pre < formula.SNN_EXCITATORY)
    )


def _plastic_by_post() -> dict[int, list[int]]:
    """Canonical plastic-synapse indices grouped by postsynaptic neuron."""

    grouped: dict[int, list[int]] = {}
    for index, (post, _pre) in enumerate(formula.PLASTIC_SYNAPSES):
        grouped.setdefault(post, []).append(index)
    return grouped


_PLASTIC_BY_POST = _plastic_by_post()


# --------------------------------------------------------------------------- #
# Property 1: malformed streams fail closed, with no partial state
# --------------------------------------------------------------------------- #

#: Every mutation is *structurally* malformed: a fact that is not a finite float, a vector of
#: the wrong length/type, or a derived channel supplied as if it were a fact.  Some are caught
#: by the ``TurnEnvelope`` DTO guard and some by ``ObservationFacts`` inside ``orchestrate`` —
#: the property is that *some* boundary refuses, never that a specific one does.
_MALFORMED_KINDS = (
    "nan",
    "inf",
    "negative_inf",
    "int_instead_of_float",
    "bool_instead_of_float",
    "str_instead_of_float",
    "derived_channel_supplied",
    "too_short",
    "too_long",
    "list_instead_of_tuple",
    "previous_action_str",
    "observation_not_a_pair",
)


def _malformed_observation(rng: random.Random, kind: str) -> tuple:
    """Build one malformed ``(raw_values, previous_action)`` observation of the given kind."""

    channel = rng.choice(VALUE_CHANNELS)
    if kind == "nan":
        return _raw_values({channel: float("nan")}), Action.SPEAK
    if kind == "inf":
        return _raw_values({channel: float("inf")}), Action.SPEAK
    if kind == "negative_inf":
        return _raw_values({channel: float("-inf")}), Action.SPEAK
    if kind == "int_instead_of_float":
        return _raw_values({channel: rng.randint(0, 3)}), Action.SPEAK
    if kind == "bool_instead_of_float":
        return _raw_values({channel: rng.choice((True, False))}), Action.SPEAK
    if kind == "str_instead_of_float":
        return _raw_values({channel: "0.5"}), Action.SPEAK
    if kind == "derived_channel_supplied":
        # ObservationFacts requires channels 27/28/29/32/33/34/35 to be None.
        return _raw_values({rng.choice(sorted(DERIVED_CHANNELS)): 1.0}), Action.SPEAK
    if kind == "too_short":
        return _raw_values()[: formula.OBSERVATION_DIM - 1], Action.SPEAK
    if kind == "too_long":
        return _raw_values() + (0.5,), Action.SPEAK
    if kind == "list_instead_of_tuple":
        return list(_raw_values()), Action.SPEAK
    if kind == "previous_action_str":
        return _raw_values(), "SPEAK"
    if kind == "observation_not_a_pair":
        return (_raw_values(),)
    raise AssertionError(f"unhandled malformed kind {kind!r}")


def _run_malformed(observation: object, base: V3State) -> Exception | None:
    """Push a malformed observation through the real pipeline; return what refused it.

    The refusal may come from the ``TurnEnvelope`` DTO guard (construction) or from
    ``ObservationFacts`` inside ``orchestrate``.  Both are the same promise: fail closed
    before anything is built.
    """

    try:
        envelope = TurnEnvelope(
            turn_key=TurnKey(
                plugin_instance_id="plugin-instance",
                session_ref=_session_ref(),
                bridge_request_nonce="request-nonce",
                request_attempt=0,
            ),
            turn_id="turn-malformed",
            sequence=TurnSequence(writer_epoch=7, local_sequence=11),
            compute_profile=_profile(),
            deterministic_seed=b"d" * 16,
            observation=observation,
            context=TurnContextClass.ADDRESSED,
        )
    except (TypeError, ValueError) as exc:
        return exc
    try:
        orchestrate(CoreInvocation(envelope=envelope, base_state=base, projected_actual_outcome=None))
    except (TypeError, ValueError) as exc:
        return exc
    return None


def test_malformed_streams_fail_closed_and_never_leave_a_partial_state() -> None:
    rng = random.Random(SEED_MALFORMED)
    base = _base_state()
    before = encode_state(base)
    seen: set[str] = set()
    for _ in range(360):
        kind = rng.choice(_MALFORMED_KINDS)
        seen.add(kind)
        refusal = _run_malformed(_malformed_observation(rng, kind), base)
        assert refusal is not None, f"malformed observation {kind!r} was accepted"
        assert isinstance(refusal, (TypeError, ValueError)), f"{kind!r} raised {type(refusal).__name__}"
        # No partial state: the immutable base is byte-identical after every refusal.
        assert encode_state(base) == before
        assert base.revision == 4
    assert seen == set(_MALFORMED_KINDS), "the seeded loop must exercise every malformed kind"


def test_encoder_refuses_every_malformed_fact_vector_directly() -> None:
    """The same fail-closed promise at the ``ObservationFacts`` boundary itself."""

    rng = random.Random(SEED_MALFORMED + 1)
    for _ in range(240):
        channel = rng.choice(VALUE_CHANNELS)
        bad = rng.choice((float("nan"), float("inf"), float("-inf"), 1, True, "0.5", [0.5]))
        with pytest.raises((TypeError, ValueError)):
            ObservationFacts(
                raw_values=_raw_values({channel: bad}),
                context=TurnContextClass.ADDRESSED,
                previous_action=Action.SPEAK,
            )
    # A derived channel supplied as a fact is refused for every one of the seven.
    for channel in sorted(DERIVED_CHANNELS):
        with pytest.raises(ValueError, match="derived"):
            ObservationFacts(raw_values=_raw_values({channel: 1.0}), context=TurnContextClass.ADDRESSED)


def test_observation_frame_refuses_non_finite_or_unnormalized_values() -> None:
    """A frame is the core's internal currency: it must refuse to exist if malformed."""

    rng = random.Random(SEED_MALFORMED + 2)
    good = encode_observation(ObservationFacts(raw_values=_raw_values(), context=TurnContextClass.ADDRESSED))
    for _ in range(200):
        index = rng.randrange(formula.OBSERVATION_DIM)
        bad = rng.choice((float("nan"), float("inf"), 1.5, -0.5, 1, "0.5"))
        values = list(good.values)
        values[index] = bad
        with pytest.raises((TypeError, ValueError)):
            ObservationFrame(values=tuple(values), valid_mask=good.valid_mask)
    # The 36-bit mask is a hard bound.
    with pytest.raises(ValueError, match="36-bit"):
        ObservationFrame(values=good.values, valid_mask=1 << formula.OBSERVATION_DIM)


# --------------------------------------------------------------------------- #
# Property 2: the 36 / 24 / 96 shapes of real orchestrated artifacts
# --------------------------------------------------------------------------- #


def test_declared_shapes_are_36_observation_24_latent_96_neurons() -> None:
    assert formula.OBSERVATION_DIM == 36
    assert formula.STATE_DIM == 24
    assert formula.SNN_NEURONS == 96
    # 96 neurons is exactly 77 excitatory + 19 inhibitory — not a coincidence to be re-typed.
    assert formula.SNN_EXCITATORY == 77
    assert formula.SNN_INHIBITORY == 19
    assert formula.SNN_EXCITATORY + formula.SNN_INHIBITORY == formula.SNN_NEURONS
    assert len(formula.SEMANTIC_DEFAULTS) == formula.OBSERVATION_DIM
    assert len(formula.RECURRENT_TOPOLOGY) == formula.SNN_NEURONS


def test_real_orchestrated_artifacts_carry_the_declared_shapes() -> None:
    rng = random.Random(SEED_BOUNDS)
    state = _base_state()
    for step in range(24):  # far under the ~358-turn STATE_QUANTIZE_ERROR livelock
        result = orchestrate(
            CoreInvocation(
                envelope=_envelope(
                    local_sequence=11 + step,
                    turn_id=f"shape-{step:04d}",
                    raw=_random_raw_values(rng),
                    context=rng.choice(CONTEXTS),
                ),
                base_state=state,
                projected_actual_outcome=(Action.SPEAK, None),
            )
        )
        assert result.accepted is True, result.reject_reason
        trace = result.trace
        next_state = result.state_delta.next_state

        # 36: the observation frame the core actually saw.
        assert len(trace.observation_values) == formula.OBSERVATION_DIM
        assert 0 <= trace.observation_valid_mask < (1 << formula.OBSERVATION_DIM)
        # 24: the latent axes (8 axes x 3 timescales), on the trace and in the state.
        assert len(trace.next_latent_axes) == formula.STATE_DIM
        assert len(next_state.latent_axes) == formula.STATE_DIM
        # 8: the derived per-axis views.
        assert len(trace.drive) == formula.AXIS_DIM
        assert len(trace.decision_state) == formula.AXIS_DIM
        # 96: one entry per neuron, on every SNN-shaped artifact.
        assert len(trace.spike_counts) == formula.SNN_NEURONS
        assert len(trace.first_latencies) == formula.SNN_NEURONS
        assert len(next_state.snn.voltages) == formula.SNN_NEURONS
        assert len(next_state.snn.thresholds) == formula.SNN_NEURONS
        assert len(next_state.snn.pre_trace) == formula.SNN_NEURONS
        assert len(next_state.snn.post_trace) == formula.SNN_NEURONS
        assert len(trace.snn_summary) == formula.SNN_SUMMARY_DIM
        state = next_state


# --------------------------------------------------------------------------- #
# Property 3: everything finite and inside its declared bound, every turn
# --------------------------------------------------------------------------- #


def _assert_trace_is_finite_and_bounded(trace: object) -> None:
    """Every numeric the trace publishes is finite and inside its declared bound."""

    for value in trace.next_latent_axes:
        assert math.isfinite(value) and -1.0 <= value <= 1.0
    for value in trace.drive:  # drive = tanh(...) so it is bounded by construction
        assert math.isfinite(value) and -1.0 <= value <= 1.0
    for value in trace.decision_state:
        assert math.isfinite(value) and -1.0 <= value <= 1.0
    for value in trace.candidate_posterior:
        assert math.isfinite(value) and 0.0 <= value <= 1.0
    # A posterior over the legal actions is a distribution, not just bounded numbers.
    assert sum(trace.candidate_posterior) == pytest.approx(1.0)
    assert math.isfinite(trace.policy_confidence) and 0.0 <= trace.policy_confidence <= 1.0
    assert math.isfinite(trace.weight_saturation) and 0.0 <= trace.weight_saturation <= 1.0
    for name in ("pace", "directness", "warmth"):
        value = getattr(trace, name)
        assert math.isfinite(value) and 0.0 <= value <= 1.0
    for value in trace.rho_hold_after, trace.rho_reach_after, trace.rho_hold_before, trace.rho_reach_before:
        assert math.isfinite(value) and 0.0 <= value <= 1.0
    for value in trace.effective_salience + trace.activation + trace.inhibition:
        assert math.isfinite(value)
    for value in trace.candidate_expected_free_energy + trace.candidate_logit + trace.candidate_risk:
        assert math.isfinite(value)
    for _action_name, value in trace.support + trace.log_evidence:
        assert math.isfinite(value)
    for value in trace.snn_summary:
        assert math.isfinite(value)
    # Spike counts / latencies are the SNN's integer contract.
    for count in trace.spike_counts:
        assert type(count) is int and count >= 0
    for latency in trace.first_latencies:
        assert type(latency) is int and latency >= -1


def _assert_state_is_finite_and_bounded(state: V3State) -> None:
    for value in state.latent_axes:
        assert math.isfinite(value) and -1.0 <= value <= 1.0
    assert 0.0 <= state.rho_hold <= 1.0
    assert 0.0 <= state.rho_reach <= 1.0
    snn = state.snn
    if snn is None:
        return
    for value in snn.voltages:
        assert math.isfinite(value) and VOLTAGE_BOUNDS[0] <= value <= VOLTAGE_BOUNDS[1]
    for value in snn.thresholds:
        assert math.isfinite(value) and THRESHOLD_BOUNDS[0] <= value <= THRESHOLD_BOUNDS[1]
    for value in snn.plastic_weights:
        assert math.isfinite(value) and PLASTIC_WEIGHT_BOUNDS[0] <= value <= PLASTIC_WEIGHT_BOUNDS[1]


def test_every_latent_posterior_and_trace_numeric_stays_finite_and_bounded() -> None:
    """A long seeded walk of random turns never escapes a declared bound."""

    rng = random.Random(SEED_BOUNDS + 1)
    # Four independent sessions of 30 turns: variety without approaching the ~358-turn livelock.
    for session in range(4):
        state = _base_state()
        for step in range(30):
            result = orchestrate(
                CoreInvocation(
                    envelope=_envelope(
                        local_sequence=11 + step,
                        turn_id=f"bounds-{session}-{step:04d}",
                        raw=_random_raw_values(rng, drop=frozenset(rng.sample(VALUE_CHANNELS, k=rng.randint(0, 8)))),
                        context=rng.choice(CONTEXTS),
                        previous_action=rng.choice((None, *Action)),
                    ),
                    base_state=state,
                    projected_actual_outcome=rng.choice(((Action.SPEAK, None), (Action.HOLD, 0.75), None)),
                )
            )
            assert result.accepted is True, result.reject_reason
            _assert_trace_is_finite_and_bounded(result.trace)
            _assert_state_is_finite_and_bounded(result.state_delta.next_state)
            state = result.state_delta.next_state


def test_encoded_frame_values_are_always_normalized_to_the_unit_interval() -> None:
    """The encoder must absorb wildly out-of-range facts, not propagate them."""

    rng = random.Random(SEED_BOUNDS + 2)
    for _ in range(400):
        raw = list(_random_raw_values(rng))
        # Deliberately shove extreme magnitudes at the saturating normalizers.
        for index in rng.sample(VALUE_CHANNELS, k=4):
            raw[index] = rng.choice((-1e9, 1e9, -1e300, 1e300, 0.0))
        frame = encode_observation(
            ObservationFacts(
                raw_values=tuple(raw),
                context=rng.choice(CONTEXTS),
                previous_action=rng.choice((None, *Action)),
            )
        )
        for value in frame.values:
            assert math.isfinite(value) and 0.0 <= value <= 1.0
        assert 0 <= frame.valid_mask < (1 << formula.OBSERVATION_DIM)


# --------------------------------------------------------------------------- #
# Property 4: invalid (masked-off) channels are inert
# --------------------------------------------------------------------------- #
#
# This is the load-bearing one.  Three complementary legs, because "invalid" is reachable in
# exactly one way through the encoder (a missing fact -> None) but the *contract* is broader:
#
#   4a  encoder pinning: a missing fact becomes SEMANTIC_DEFAULTS[i] with its bit clear, and
#       nothing else in the vector can perturb that slot.  (Also: present => valid, always.)
#   4b  stage non-interference: hand-build frames that differ ONLY at masked-off channels and
#       prove the drive / latent / workspace / decision are bit-identical.  This is the leg
#       with real teeth — it is the only one that can observe a downstream stage reading an
#       ungated ``frame.values[i]``.
#   4c  end-to-end: two envelopes agreeing outside the dropped set produce byte-identical
#       traces through the full ``encode_observation`` -> ``orchestrate`` composition.
#
# NOTE on scope: this asserts values / drive / decision (the three the design names).  It
# deliberately does not assert the *expression* constraints, because
# ``expression/policy.py::_base_constraints`` reads ``frame_values[10]`` without consulting
# the mask.  That is inert through the real encoder (an invalid channel 10 is pinned to
# SEMANTIC_DEFAULTS[10] == 0.0) but it is not mask-gated the way the drive is; asserting
# invariance there would fail, and asserting the leak would enshrine it.  Reported separately.


def test_missing_facts_are_pinned_to_semantic_defaults_with_their_bit_clear() -> None:
    """4a: nothing else in the fact vector can reach a dropped channel's slot."""

    rng = random.Random(SEED_NONINTERFERENCE)
    for _ in range(300):
        drop = frozenset(rng.sample(VALUE_CHANNELS, k=rng.randint(1, 12)))
        frame = encode_observation(
            ObservationFacts(
                raw_values=_random_raw_values(rng, drop=drop),  # every other channel is random
                context=rng.choice(CONTEXTS),
                previous_action=rng.choice((None, *Action)),
            )
        )
        for index in drop:
            # Pinned exactly — not approximately — however the rest of the vector varies.
            assert frame.values[index] == formula.SEMANTIC_DEFAULTS[index]
            assert frame.is_valid(index) is False
        # And the converse: a channel that was supplied is always valid. "Present but
        # masked-off" is unreachable through the encoder, which is what makes the semantic
        # default inert rather than merely conventional.
        for index in VALUE_CHANNELS:
            if index not in drop:
                assert frame.is_valid(index) is True


def test_perturbing_masked_off_channels_cannot_change_drive_latent_workspace_or_decision() -> None:
    """4b: the real non-interference test — masked-off values are never read."""

    rng = random.Random(SEED_NONINTERFERENCE + 1)
    for _ in range(200):
        drop = frozenset(rng.sample(VALUE_CHANNELS, k=rng.randint(1, 12)))
        context = rng.choice(CONTEXTS)
        state = _base_state(latent_axes=tuple(rng.uniform(-1.0, 1.0) for _ in range(formula.STATE_DIM)))
        frame = encode_observation(
            ObservationFacts(
                raw_values=_random_raw_values(rng, drop=drop),
                context=context,
                previous_action=Action.SPEAK,
            )
        )
        # Rebuild the frame with arbitrary values in every masked-off slot. The mask is
        # untouched, so a mask-gating consumer cannot notice; an ungated one would.
        perturbed_values = list(frame.values)
        for index in drop:
            perturbed_values[index] = rng.random()
        perturbed = ObservationFrame(values=tuple(perturbed_values), valid_mask=frame.valid_mask)
        assert perturbed.values != frame.values  # the perturbation is real
        assert perturbed.valid_mask == frame.valid_mask

        revision = state.revision + 1
        clean = advance_dynamics(state, frame, revision, None)
        dirty = advance_dynamics(state, perturbed, revision, None)
        assert dirty.drive == clean.drive
        assert dirty.next_latent_axes == clean.next_latent_axes

        axes = decision_state(clean.next_latent_axes)
        refractory = tuple(0.0 for _ in range(formula.WORKSPACE_CAPACITY))
        clean_broadcast = run_workspace(axes, frame, None, context, refractory)
        dirty_broadcast = run_workspace(axes, perturbed, None, context, refractory)
        assert dirty_broadcast == clean_broadcast

        clean_policy = score_policy(state, clean_broadcast, context)
        dirty_policy = score_policy(state, dirty_broadcast, context)
        assert dirty_policy.selected_action == clean_policy.selected_action
        assert dirty_policy.candidates == clean_policy.candidates


def test_dropped_channels_cannot_leak_through_the_full_orchestrated_turn() -> None:
    """4c: end-to-end — what a dropped channel *would* have been never reaches the trace."""

    rng = random.Random(SEED_NONINTERFERENCE + 2)
    for step in range(40):
        drop = frozenset(rng.sample(VALUE_CHANNELS, k=rng.randint(1, 10)))
        context = rng.choice(CONTEXTS)
        first = _random_raw_values(rng, drop=drop)
        # A second vector drawn independently, then forced to agree everywhere the first is
        # present. The two differ only in what the dropped channels *would* have carried.
        other = _random_raw_values(rng, drop=drop)
        second = tuple(first[i] if i not in drop else other[i] for i in range(formula.OBSERVATION_DIM))
        assert second == first  # dropped slots are None in both: the value is simply gone

        kwargs = {"context": context, "local_sequence": 11 + step, "turn_id": f"leak-{step:04d}"}
        left = orchestrate(_invocation(raw=first, **kwargs))
        right = orchestrate(_invocation(raw=second, **kwargs))
        assert left.accepted is True and right.accepted is True
        assert right.trace_bytes == left.trace_bytes
        assert right.payload_digest == left.payload_digest
        assert right.decision_plan.action == left.decision_plan.action
        # And the frame the core saw pins every dropped channel to its semantic default.
        for index in drop:
            assert left.trace.observation_values[index] == formula.SEMANTIC_DEFAULTS[index]
            assert not (left.trace.observation_valid_mask >> index) & 1


# --------------------------------------------------------------------------- #
# Property 5: Dale signs and the incoming-L1 budget after every update
# --------------------------------------------------------------------------- #
#
# tests/test_v3_stdp_plasticity.py already proves this at the unit level over random
# eligibility/delta vectors (``test_all_updates_keep_bounds_and_l1_under_random_deltas``).
# This file does not repeat that loop; it reuses the same reference helpers (_fixed_incoming_l1,
# _plastic_by_post) and asks the complementary question the unit test cannot: do the invariants
# survive *real orchestrated turns*, where the eligibility and reward are whatever the core
# actually computed rather than whatever the test chose?


def test_fixed_topology_weights_obey_dale_signs_for_every_edge() -> None:
    """Dale's law is a property of the frozen topology, before any learning happens."""

    excitatory_lo, excitatory_hi = _EXCITATORY_BOUNDS
    inhibitory_lo, inhibitory_hi = _INHIBITORY_BOUNDS
    edges = 0
    for post in range(formula.SNN_NEURONS):
        for pre in formula.RECURRENT_TOPOLOGY[post]:
            weight = formula.recurrent_initial_weight(post, pre)
            edges += 1
            if pre < formula.SNN_EXCITATORY:
                # An excitatory presynaptic neuron may never inhibit.
                assert weight >= 0.0
                assert excitatory_lo <= weight <= excitatory_hi
            else:
                # An inhibitory presynaptic neuron may never excite.
                assert weight <= 0.0
                assert inhibitory_lo <= weight <= inhibitory_hi
    assert edges > 0
    # Every plastic synapse is excitatory->excitatory, so plastic weights are non-negative.
    for post, pre in formula.PLASTIC_SYNAPSES:
        assert 0 <= post < formula.SNN_EXCITATORY and 0 <= pre < formula.SNN_EXCITATORY


def test_initial_fixed_incoming_l1_is_within_budget_for_every_neuron() -> None:
    """The fixed edges alone must leave room for the plastic budget."""

    for post in range(formula.SNN_NEURONS):
        assert _fixed_incoming_l1(post) <= _L1_LIMIT + 1e-9


def test_dale_and_incoming_l1_hold_after_every_real_orchestrated_update() -> None:
    rng = random.Random(SEED_DALE)
    excitatory_lo, excitatory_hi = _EXCITATORY_BOUNDS
    state = _base_state()
    for step in range(60):  # well under the ~358-turn livelock
        result = orchestrate(
            CoreInvocation(
                envelope=_envelope(
                    local_sequence=11 + step,
                    turn_id=f"dale-{step:04d}",
                    raw=_random_raw_values(rng),
                    context=rng.choice(CONTEXTS),
                ),
                # A projected outcome that sometimes agrees with the shadow action is what
                # opens the STDP credit gate, so real settlement actually runs in this loop.
                base_state=state,
                projected_actual_outcome=(rng.choice(tuple(Action)), rng.uniform(-1.0, 1.0)),
            )
        )
        assert result.accepted is True, result.reject_reason
        snn = result.state_delta.next_state.snn
        assert snn is not None
        assert len(snn.plastic_weights) == len(formula.PLASTIC_SYNAPSES)

        # (1) Dale: every plastic (E->E) weight is non-negative and inside the per-edge bound.
        for weight in snn.plastic_weights:
            assert weight >= 0.0
            assert excitatory_lo <= weight <= excitatory_hi

        # (2) The incoming absolute-weight limit holds simultaneously with the fixed edges.
        for post, indices in _PLASTIC_BY_POST.items():
            incoming = _fixed_incoming_l1(post) + sum(snn.plastic_weights[i] for i in indices)
            assert incoming <= _L1_LIMIT + 1e-9, f"neuron {post} incoming L1 {incoming} exceeds {_L1_LIMIT}"
        state = result.state_delta.next_state


# --------------------------------------------------------------------------- #
# Property 6: the selected action is always legal for its context
# --------------------------------------------------------------------------- #


def test_context_action_priors_declare_the_expected_legal_sets() -> None:
    """Pin the frozen manifest itself, so the loop below cannot pass against a drifted map."""

    assert LEGAL_ACTIONS_BY_CONTEXT == {
        "ADDRESSED": ("CLARIFY", "HOLD", "SPEAK"),
        "AMBIENT": ("HOLD", "SPEAK"),
        "PROACTIVE": ("HOLD", "REACH"),
        "IDLE": ("HOLD",),
    }


def test_selected_action_is_always_legal_for_its_context() -> None:
    rng = random.Random(SEED_LEGAL)
    for context in CONTEXTS:
        legal = LEGAL_ACTIONS_BY_CONTEXT[context.value]
        state = _base_state()
        for step in range(35):  # 4 contexts x 35 turns, each session far under the livelock
            result = orchestrate(
                CoreInvocation(
                    envelope=_envelope(
                        context=context,
                        local_sequence=11 + step,
                        turn_id=f"legal-{context.value}-{step:04d}",
                        raw=_random_raw_values(rng, drop=frozenset(rng.sample(VALUE_CHANNELS, k=rng.randint(0, 6)))),
                        previous_action=rng.choice((None, *Action)),
                    ),
                    base_state=state,
                    projected_actual_outcome=(rng.choice(tuple(Action)), None),
                )
            )
            assert result.accepted is True, result.reject_reason
            selected = result.decision_plan.action
            assert selected.value in legal, f"{context.value} selected illegal {selected.value}"
            # The trace, the plan, and the expression constraints must name the same action.
            assert result.trace.selected_action == selected.value
            assert result.trace.shadow_action == selected.value
            assert result.decision_plan.expression.action is selected
            # Only legal actions may even be scored: an illegal one must not enter the softmax.
            assert set(result.trace.candidate_actions) == set(legal)
            state = result.state_delta.next_state


def test_idle_context_can_only_ever_hold() -> None:
    """IDLE has a single legal action, so its posterior is degenerate by construction."""

    rng = random.Random(SEED_LEGAL + 1)
    state = _base_state()
    for step in range(20):
        result = orchestrate(
            CoreInvocation(
                envelope=_envelope(
                    context=TurnContextClass.IDLE,
                    local_sequence=11 + step,
                    turn_id=f"idle-{step:04d}",
                    raw=_random_raw_values(rng),
                ),
                base_state=state,
                projected_actual_outcome=None,
            )
        )
        assert result.accepted is True, result.reject_reason
        assert result.decision_plan.action is Action.HOLD
        assert result.trace.candidate_actions == ("HOLD",)
        assert result.trace.policy_confidence == 1.0  # a single candidate has no runner-up
        state = result.state_delta.next_state


# --------------------------------------------------------------------------- #
# Property 7: deterministic, byte-identical traces
# --------------------------------------------------------------------------- #


def test_same_fingerprint_and_state_yields_byte_identical_traces() -> None:
    """Same fingerprint + same inputs + same state + same seed => byte-identical trace."""

    rng = random.Random(SEED_TRACE)
    state = _base_state()
    for step in range(45):
        kwargs = {
            "local_sequence": 11 + step,
            "turn_id": f"det-{step:04d}",
            "raw": _random_raw_values(rng, drop=frozenset(rng.sample(VALUE_CHANNELS, k=rng.randint(0, 6)))),
            "context": rng.choice(CONTEXTS),
            "previous_action": rng.choice((None, *Action)),
            "seed": bytes(rng.randrange(256) for _ in range(16)),
        }
        outcome = rng.choice(((Action.SPEAK, None), (Action.HOLD, 0.5), None))
        first = orchestrate(
            CoreInvocation(envelope=_envelope(**kwargs), base_state=state, projected_actual_outcome=outcome)
        )
        # A freshly built, equal invocation — not the same object — must reproduce every byte.
        second = orchestrate(
            CoreInvocation(envelope=_envelope(**kwargs), base_state=state, projected_actual_outcome=outcome)
        )
        assert first.accepted is True, first.reject_reason
        assert second.trace_bytes == first.trace_bytes
        assert second.trace_digest == first.trace_digest
        assert second.payload_digest == first.payload_digest
        assert second.journal_digest == first.journal_digest
        assert second.trace == first.trace
        assert second.state_delta.next_state == first.state_delta.next_state
        state = first.state_delta.next_state


def test_changing_only_the_deterministic_seed_changes_no_decision() -> None:
    """The seed is recorded, not consumed: the core has no randomness for it to drive.

    The trace bytes *do* differ (the seed is a trace field), but nothing downstream of it may:
    if a decision or the state payload moved with the seed, the "no randomness" contract in the
    orchestrator's module docstring would be false.
    """

    rng = random.Random(SEED_TRACE + 1)
    for step in range(20):
        raw = _random_raw_values(rng)
        context = rng.choice(CONTEXTS)
        kwargs = {"raw": raw, "context": context, "local_sequence": 11 + step, "turn_id": f"seed-{step:04d}"}
        left = orchestrate(_invocation(seed=b"a" * 16, **kwargs))
        right = orchestrate(_invocation(seed=b"z" * 16, **kwargs))
        assert left.accepted is True and right.accepted is True
        assert right.trace.seed != left.trace.seed
        assert right.decision_plan.action == left.decision_plan.action
        assert right.trace.next_latent_axes == left.trace.next_latent_axes
        assert right.trace.drive == left.trace.drive
        # The seed is not part of the cognitive payload, so the state bytes are identical.
        assert right.payload_digest == left.payload_digest


# --------------------------------------------------------------------------- #
# Property 8: CAS — a revision advances at most once
# --------------------------------------------------------------------------- #


def test_replaying_an_identical_invocation_advances_the_same_revision_once() -> None:
    """Re-running the identical CoreInvocation is idempotent: base+1, never base+2."""

    rng = random.Random(SEED_CAS)
    state = _base_state()
    for step in range(40):
        invocation = CoreInvocation(
            envelope=_envelope(
                local_sequence=11 + step,
                turn_id=f"cas-{step:04d}",
                raw=_random_raw_values(rng),
                context=rng.choice(CONTEXTS),
            ),
            base_state=state,
            projected_actual_outcome=(rng.choice(tuple(Action)), None),
        )
        base_revision = state.revision
        before = encode_state(state)

        first = orchestrate(invocation)
        second = orchestrate(invocation)  # the retry a CAS loser would perform
        third = orchestrate(invocation)
        assert first.accepted is True, first.reject_reason

        # A single advance: the same base revision maps to exactly one next revision.
        assert first.state_delta.next_state.revision == base_revision + 1
        assert second.state_delta.next_state.revision == base_revision + 1
        assert third.state_delta.next_state.revision == base_revision + 1
        assert first.state_delta.base_revision == base_revision
        # ...and an identical payload, so a duplicate commit is a no-op, not a fork.
        assert second.payload_digest == first.payload_digest
        assert third.payload_digest == first.payload_digest
        assert second.state_delta.next_state == first.state_delta.next_state
        # The base state is immutable: replaying can never mutate what it read.
        assert encode_state(state) == before
        assert state.revision == base_revision
        state = first.state_delta.next_state


def test_a_rejected_invocation_leaves_the_base_state_byte_identical(monkeypatch: pytest.MonkeyPatch) -> None:
    """A rejection commits nothing: no state, no trace, only bounded telemetry."""

    import sylanne_alpha.v3core.orchestrator as orchestrator_module

    rng = random.Random(SEED_CAS + 1)
    # Force the trace over its hard cap so the whole invocation is refused (design 16.2).
    monkeypatch.setattr(orchestrator_module, "TRACE_HARD_CAP_BYTES", 8)
    for step in range(20):
        state = _base_state()
        before = encode_state(state)
        result = orchestrate(
            CoreInvocation(
                envelope=_envelope(
                    local_sequence=11 + step,
                    turn_id=f"reject-{step:04d}",
                    raw=_random_raw_values(rng),
                    context=rng.choice(CONTEXTS),
                ),
                base_state=state,
                projected_actual_outcome=(Action.SPEAK, None),
            )
        )
        assert result.accepted is False
        assert result.reject_reason == "TRACE_OVERSIZE"
        assert result.state_delta is None
        assert result.effects is None
        assert result.trace is None
        assert result.payload_digest == ""
        # Nothing advanced and nothing mutated.
        assert encode_state(state) == before
        assert state.revision == 4
        assert result.telemetry  # only bounded runtime telemetry survives


# --------------------------------------------------------------------------- #
# Property 9: the encoded dataset re-encodes a stored turn identically
# --------------------------------------------------------------------------- #


def _stored_turn(rng: random.Random) -> dict:
    """A synthetic stored turn row in the shape ``scripts/v3_export.py`` writes."""

    values = [0.0] * formula.OBSERVATION_DIM
    mask = 0
    for channel in VALUE_CHANNELS:
        if rng.random() < 0.15:
            continue  # a genuinely missing fact stays invalid
        values[channel] = float(rng.uniform(0.0, 2.0))
        mask |= 1 << channel
    return {"values": values, "valid_mask": mask, "context": rng.choice(CONTEXTS).value}


def test_frame_for_turn_re_encodes_a_stored_turn_identically() -> None:
    """Replay must rebuild the exact frame the core saw, with no tolerance fudge."""

    rng = random.Random(SEED_DATASET)
    for _ in range(120):
        turn = _stored_turn(rng)
        previous = rng.choice((None, *Action))
        first = v3_export.frame_for_turn(turn, previous)
        second = v3_export.frame_for_turn(turn, previous)
        assert second == first  # deterministic: no hidden state between calls
        assert second.values == first.values
        assert second.valid_mask == first.valid_mask

        # ...and it equals encoding the same facts directly through the real core encoder.
        raw = tuple(
            None if (index in DERIVED_CHANNELS or not (turn["valid_mask"] >> index) & 1) else float(turn["values"][index])
            for index in range(formula.OBSERVATION_DIM)
        )
        direct = encode_observation(
            ObservationFacts(
                raw_values=raw,
                context=TurnContextClass(turn["context"]),
                previous_action=previous,
            )
        )
        assert first == direct


def test_frame_for_turn_ignores_stored_values_at_masked_off_channels() -> None:
    """Property 4 at the dataset boundary: a masked-off stored value is not evidence."""

    rng = random.Random(SEED_DATASET + 1)
    for _ in range(120):
        turn = _stored_turn(rng)
        mask = turn["valid_mask"]
        baseline = v3_export.frame_for_turn(turn, Action.SPEAK)
        # Rewrite every masked-off stored value; the frame must not notice.
        perturbed_values = list(turn["values"])
        touched = False
        for channel in VALUE_CHANNELS:
            if not (mask >> channel) & 1:
                perturbed_values[channel] = float(rng.uniform(0.0, 5.0))
                touched = True
        perturbed = v3_export.frame_for_turn(
            {"values": perturbed_values, "valid_mask": mask, "context": turn["context"]}, Action.SPEAK
        )
        assert perturbed == baseline
        if touched:
            assert perturbed_values != turn["values"]  # the perturbation was real


def test_neutral_evaluation_state_bytes_are_stable_and_canonical() -> None:
    """Every episode starts from the identical canonical state, or splits are not comparable."""

    first = v3_export.neutral_eval_state_bytes()
    second = v3_export.neutral_eval_state_bytes()
    assert second == first
    assert type(first) is bytes and first
    assert v3_export.neutral_eval_state_digest() == v3_export.neutral_eval_state_digest()


def test_encode_state_bytes_matches_the_core_codec_for_real_orchestrated_states() -> None:
    """The exporter's byte-identity helper must be the core codec, not a parallel encoder."""

    rng = random.Random(SEED_DATASET + 2)
    state = _base_state()
    for step in range(12):
        result = orchestrate(
            CoreInvocation(
                envelope=_envelope(
                    local_sequence=11 + step, turn_id=f"bytes-{step:04d}", raw=_random_raw_values(rng)
                ),
                base_state=state,
                projected_actual_outcome=(Action.SPEAK, None),
            )
        )
        assert result.accepted is True, result.reject_reason
        state = result.state_delta.next_state
        assert v3_export.encode_state_bytes(state) == encode_state(state)


# --------------------------------------------------------------------------- #
# Hypothesis: EXTRA coverage only
# --------------------------------------------------------------------------- #
#
# Every property above is fully proven by its fixed-seed loop.  Hypothesis is installed, so it
# is imported plainly (no importorskip) and used here to widen the input distribution — never
# as the sole implementation of an acceptance property.  ``derandomize=True`` keeps CI runs
# reproducible; ``deadline=None`` because an orchestrated turn is ~14 ms and a per-example
# deadline would flake rather than find bugs.

if HAS_HYPOTHESIS:
    _PROPERTY_SETTINGS = settings(
        max_examples=60,
        deadline=None,
        derandomize=True,
        suppress_health_check=[HealthCheck.too_slow],
    )
else:  # pragma: no cover - no-op decorators so the module still imports
    def _PROPERTY_SETTINGS(func):
        return func

    def given(**_kwargs):
        def decorate(func):
            return func

        return decorate

    class _NoHypothesis:
        def __getattr__(self, _name):
            def _unavailable(*_args, **_kw):
                return None

            return _unavailable

    hyp = _NoHypothesis()


def _finite_fact() -> hyp.SearchStrategy:
    return hyp.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis adds coverage; the seeded loops are authoritative")
@_PROPERTY_SETTINGS
@given(
    raw=hyp.lists(hyp.one_of(hyp.none(), _finite_fact()), min_size=len(VALUE_CHANNELS), max_size=len(VALUE_CHANNELS)),
    context=hyp.sampled_from(CONTEXTS),
    previous=hyp.sampled_from((None, *Action)),
)
def test_hypothesis_encoded_values_stay_normalized(raw: list, context: TurnContextClass, previous: Action | None) -> None:
    """Extra coverage for property 3 (bounds) — the fixed-seed loop remains authoritative."""

    values: list[float | None] = [None] * formula.OBSERVATION_DIM
    for slot, channel in enumerate(VALUE_CHANNELS):
        values[channel] = raw[slot]
    frame = encode_observation(
        ObservationFacts(raw_values=tuple(values), context=context, previous_action=previous)
    )
    for value in frame.values:
        assert math.isfinite(value) and 0.0 <= value <= 1.0
    assert 0 <= frame.valid_mask < (1 << formula.OBSERVATION_DIM)


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis adds coverage; the seeded loops are authoritative")
@_PROPERTY_SETTINGS
@given(
    raw=hyp.lists(hyp.one_of(hyp.none(), _finite_fact()), min_size=len(VALUE_CHANNELS), max_size=len(VALUE_CHANNELS)),
    context=hyp.sampled_from(CONTEXTS),
)
def test_hypothesis_missing_facts_are_pinned_to_semantic_defaults(raw: list, context: TurnContextClass) -> None:
    """Extra coverage for property 4a — the fixed-seed loop remains authoritative."""

    values: list[float | None] = [None] * formula.OBSERVATION_DIM
    for slot, channel in enumerate(VALUE_CHANNELS):
        values[channel] = raw[slot]
    frame = encode_observation(ObservationFacts(raw_values=tuple(values), context=context))
    for channel in VALUE_CHANNELS:
        if values[channel] is None:
            assert frame.values[channel] == formula.SEMANTIC_DEFAULTS[channel]
            assert frame.is_valid(channel) is False
        else:
            assert frame.is_valid(channel) is True


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis adds coverage; the seeded loops are authoritative")
@_PROPERTY_SETTINGS
@given(
    raw=hyp.lists(hyp.one_of(hyp.none(), _finite_fact()), min_size=len(VALUE_CHANNELS), max_size=len(VALUE_CHANNELS)),
    noise=hyp.lists(hyp.floats(min_value=0.0, max_value=1.0), min_size=len(VALUE_CHANNELS), max_size=len(VALUE_CHANNELS)),
    context=hyp.sampled_from(CONTEXTS),
)
def test_hypothesis_masked_off_channels_cannot_change_the_drive(
    raw: list, noise: list, context: TurnContextClass
) -> None:
    """Extra coverage for property 4b — the fixed-seed loop remains authoritative."""

    values: list[float | None] = [None] * formula.OBSERVATION_DIM
    for slot, channel in enumerate(VALUE_CHANNELS):
        values[channel] = raw[slot]
    frame = encode_observation(ObservationFacts(raw_values=tuple(values), context=context))
    perturbed_values = list(frame.values)
    for slot, channel in enumerate(VALUE_CHANNELS):
        if not frame.is_valid(channel):
            perturbed_values[channel] = noise[slot]
    perturbed = ObservationFrame(values=tuple(perturbed_values), valid_mask=frame.valid_mask)
    state = _base_state()
    assert advance_dynamics(state, perturbed, 5, None).drive == advance_dynamics(state, frame, 5, None).drive


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis adds coverage; the seeded loops are authoritative")
@_PROPERTY_SETTINGS
@given(
    channel=hyp.sampled_from(VALUE_CHANNELS),
    bad=hyp.sampled_from((float("nan"), float("inf"), float("-inf"), 1, True, "0.5", [0.5], (0.5,))),
)
def test_hypothesis_malformed_facts_fail_closed(channel: int, bad: object) -> None:
    """Extra coverage for property 1 — the fixed-seed loop remains authoritative."""

    with pytest.raises((TypeError, ValueError)):
        ObservationFacts(raw_values=_raw_values({channel: bad}), context=TurnContextClass.ADDRESSED)
