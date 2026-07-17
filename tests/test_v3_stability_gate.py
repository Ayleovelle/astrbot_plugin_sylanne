"""G0 synthetic stability gate (design 17.4 / plan Task 15).

Runs `scripts/v3_stability.py` over synthetic normal/repeated/out-of-order/
extreme/malformed turns and checks the declared invariants: recovery envelopes,
no all-speak/all-hold/winner-lock/saturation, K-resampling JS divergence, and
bounded state.

Sizing
------
The plan's gate is 100,000 turns per seed. One orchestrated turn costs ~7 ms
(measured), so the full stream is minutes of CPU — too slow for the default
suite. The default is therefore a small stream that always runs, and
``SYLANNE_V3_LONG_GATES=1`` opens it to the full declared 100,000.

Be honest about what the shrunk default costs. ``max_action_run``,
``max_winner_run`` and ``max_posterior_lock_run`` are maxima over the stream and
are monotone non-decreasing in its length, so **a short stream genuinely can miss
a lock-in that a long stream would catch**. The long gate is not decoration.

The ``STATE_QUANTIZE_ERROR`` livelock used to make this worse still: nothing was
accepted after turn ~358, so a 100,000-turn run observed *the same 358 accepted
turns* as the 400-turn default and the long gate added no coverage at all. That
defect is fixed (see ``test_invocations_are_not_rejected_wholesale``), so the long
gate now genuinely buys coverage the default cannot — which is a reason to run it,
not a licence to keep the default small.

What this gate does NOT claim
-----------------------------
G0 is synthetic. It makes no claim about conversational gain, no claim that a
learned configuration beats a control, and no claim about calibration. Those are
G1/G3/G4 gates on frozen real data.

Known production defects pinned below
-------------------------------------
Two declared invariants still fail against real code. They are pinned with
``xfail(strict=True)`` rather than deleted, weakened, or skipped: the suite fails
if any of them starts passing, which forces re-reading the gate the moment
someone fixes the underlying defect. Each names its measured root cause.

That mechanism has now paid out once: the third pin
(``test_invocations_are_not_rejected_wholesale``, the STATE_QUANTIZE_ERROR
livelock) started passing when the float16 bound vocabulary was fixed, the strict xfail
failed the suite, and the gate was re-read and the test converted to a plain
assertion carrying its own history.
"""

from __future__ import annotations

import os

import pytest

from scripts import v3_stability


LONG_GATES = os.environ.get("SYLANNE_V3_LONG_GATES") == "1"

#: The plan's declared stream size; the default keeps the suite usable.
FULL_GATE_TURNS = 100_000
DEFAULT_TURNS = 400
STREAM_TURNS = FULL_GATE_TURNS if LONG_GATES else DEFAULT_TURNS
RECOVERY_SESSIONS = 32 if LONG_GATES else 3
K_TURNS = 2_000 if LONG_GATES else 60


@pytest.fixture(scope="module")
def stream() -> v3_stability.StreamStats:
    return v3_stability.run_stream(2718, STREAM_TURNS)


@pytest.fixture(scope="module")
def recoveries() -> list[dict]:
    return [v3_stability.recovery_probe(2718 + offset) for offset in range(RECOVERY_SESSIONS)]


# --------------------------------------------------------------------------- #
# Stream shape
# --------------------------------------------------------------------------- #


def test_the_gate_declares_the_five_turn_classes() -> None:
    assert v3_stability.TURN_CLASSES == (
        "normal", "repeated", "out_of_order", "extreme", "malformed",
    )


def test_the_stream_actually_exercises_every_turn_class(stream: v3_stability.StreamStats) -> None:
    # A gate that never fed a malformed or out-of-order turn proves nothing about them.
    assert stream.turns == STREAM_TURNS
    assert stream.malformed_fed > 0
    assert stream.repeated_fed > 0
    assert stream.out_of_order_fed > 0


# --------------------------------------------------------------------------- #
# Invariants that hold today
# --------------------------------------------------------------------------- #


def test_no_nonfinite_value_ever_appears(stream: v3_stability.StreamStats) -> None:
    assert stream.nonfinite == 0


def test_every_malformed_turn_fails_closed(stream: v3_stability.StreamStats) -> None:
    """Malformed input must raise and leave committed state byte-identical.

    ``run_stream`` itself raises StabilityFailure if a malformed turn mutated
    state, so reaching this assertion already proves the byte-identity half.
    """

    assert stream.malformed_fed == stream.malformed_rejected


def test_a_repeated_invocation_is_deterministic(stream: v3_stability.StreamStats) -> None:
    # Same revision, same pre-state, same seed => identical bytes, advanced once.
    assert stream.repeated_divergent == 0


def test_state_stays_bounded(stream: v3_stability.StreamStats) -> None:
    assert stream.max_abs_latent <= 1.0 + 1e-6


def test_no_permanent_single_action_behaviour(stream: v3_stability.StreamStats) -> None:
    distinct = sum(1 for count in stream.action_counts.values() if count > 0)
    assert distinct >= 2, "permanent all-speak/all-hold"
    assert stream.max_action_run <= 0.5 * max(stream.accepted, 1)


def test_no_workspace_winner_lock(stream: v3_stability.StreamStats) -> None:
    assert stream.max_winner_run <= 0.5 * max(stream.accepted, 1)


def test_no_action_locks_above_posterior_098_for_20_turns(stream: v3_stability.StreamStats) -> None:
    assert stream.max_posterior_lock_run < v3_stability.POSTERIOR_LOCK_TURNS


def test_no_weight_saturation(stream: v3_stability.StreamStats) -> None:
    assert stream.max_weight_saturation < 1.0


def test_fast_axis_recovers_within_its_envelope(recoveries: list[dict]) -> None:
    within = sum(1 for r in recoveries if r["fast_within_envelope"])
    assert within / len(recoveries) >= v3_stability.RECOVERY_SESSION_FRACTION


def test_slow_axis_moves_at_most_003_per_neutral_turn(recoveries: list[dict]) -> None:
    within = sum(1 for r in recoveries if r["slow_within_envelope"])
    assert within / len(recoveries) >= v3_stability.RECOVERY_SESSION_FRACTION


def test_slow_state_stays_bounded(recoveries: list[dict]) -> None:
    assert all(r["slow_bounded"] for r in recoveries)


# --------------------------------------------------------------------------- #
# The gate makes no scientific claim
# --------------------------------------------------------------------------- #


def test_g0_report_disclaims_gain_superiority_and_calibration() -> None:
    report = v3_stability.run_gate(2718, 120, sessions=1, k_turns=40)
    assert report["claims"] == {
        "conversational_gain": False,
        "learned_vs_control_superiority": False,
        "calibration": False,
    }
    for key in ("gate_manifest_digest", "runtime_fingerprint_digest", "report_digest", "formula_digest"):
        assert report[key], f"the report must embed {key}"


def test_the_gate_reports_failures_rather_than_passing_silently() -> None:
    """The G0 gate must currently FAIL: real defects are live (see xfails below)."""

    report = v3_stability.run_gate(2718, 400, sessions=1, k_turns=40)
    assert report["passed"] is False
    assert report["failures"], "a failing gate must name its failures"


# --------------------------------------------------------------------------- #
# Known production defects — pinned, not hidden
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    strict=True,
    reason=(
        "MAJOR (measured): the SNN never spikes through orchestrate(). Max membrane "
        "voltage is ~0.32 across 1000 driven turns while the threshold adaptation "
        "floor is 0.65 (SNN_THRESHOLD_BOUNDS), so no neuron can ever reach threshold "
        "from build_initial_snn_state() (v=0, theta=1.0). snn_summary is therefore "
        "permanently all-zero, Q*summary contributes nothing to the drive, and every "
        "SNN-dependent gate passes vacuously. tests/test_v3_lif_reservoir.py only ever "
        "observes spikes by pre-charging the membrane to v=1.5 with theta=0.65."
    ),
)
def test_snn_emits_spikes(stream: v3_stability.StreamStats) -> None:
    assert stream.total_spikes > 0


def test_invocations_are_not_rejected_wholesale(stream: v3_stability.StreamStats) -> None:
    """No STATE_QUANTIZE_ERROR livelock: the shadow keeps advancing state.

    Was xfail(strict) for the measured livelock: because the SNN never fires,
    homeostasis drove every threshold down to its 0.65 clamp floor, and
    float16(0.65) = 0.64990234375 is BELOW the declared [0.65, 1.35] bound, so
    decode(encode(state)) raised and orchestrate() rejected the whole turn -- from
    turn ~358 onward, permanently. Same class for PLASTIC_WEIGHT_BOUNDS, whose 0.35
    ceiling quantizes UP to 0.35009765625.

    Resolved by ``v3core.state.models.quantization_safe_bounds``: state is persisted
    on the float16 grid, so bounded reals are now *validated* against the declared
    interval widened outward to that grid, instead of against the exact declared
    interval the storage format cannot represent. Measured on seed 2718/400 turns:
    reject rate 0.052 (21/400, all STATE_QUANTIZE_ERROR) -> 0.000, accepted 358 -> 379.

    Note this gate is about *rejection*, not about the reservoir: the SNN is still
    silent (see test_snn_emits_spikes), which is a separate live defect.
    """

    assert stream.rejected / max(stream.turns, 1) <= 0.05, stream.reject_reasons


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Declared mid-axis envelope is not met (measured ratio-to-peak ~0.57 at turn 20 "
        "against a <=0.35 gate), and the mid perturbation starts RISING again around "
        "turn 17. The slow axis is retentive by design (17.4 permits it not to return) "
        "and couples into mid via OFF_DIAGONAL_COUPLINGS, so mid relaxes toward a "
        "slow-shifted equilibrium rather than the pre-pulse baseline. Needs an "
        "architect ruling: either the envelope is measured against the shifted "
        "equilibrium, or the mid<-slow coupling/step constants are wrong."
    ),
)
def test_mid_axis_recovers_within_its_envelope(recoveries: list[dict]) -> None:
    within = sum(1 for r in recoveries if r["mid_within_envelope"])
    assert within / len(recoveries) >= v3_stability.RECOVERY_SESSION_FRACTION


# --------------------------------------------------------------------------- #
# K resampling
# --------------------------------------------------------------------------- #


def test_k32_is_reported_as_not_implementable_rather_than_faked() -> None:
    """SNN_ALLOWED_TICKS declares 32 but COMPUTE_PROFILES never does."""

    report = v3_stability.k_divergence_report(2718, 40)
    assert report["pairs"]["24_vs_32"]["status"] == "NOT_IMPLEMENTABLE"
    assert report["pairs"]["16_vs_32"]["status"] == "NOT_IMPLEMENTABLE"
    assert "COMPUTE_PROFILES" in report["k32_note"]


def test_k16_vs_k24_js_divergence_is_below_the_gate() -> None:
    report = v3_stability.k_divergence_report(2718, K_TURNS)
    pair = report["pairs"]["16_vs_24"]
    assert pair["js_divergence"] < v3_stability.MAX_JS_DIVERGENCE
    # Honesty guard: this currently passes only because the reservoir is silent, so
    # K cannot matter. Without this note the green tick would be read as evidence
    # that K-invariance was demonstrated. See test_snn_emits_spikes.
    assert pair["within_gate"] is True
