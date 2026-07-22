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
Both defects this gate used to pin as ``xfail(strict=True)`` are now resolved and
the gate PASSES (``test_the_gate_passes_now_that_the_snn_defect_was_deleted``):

* the structurally-silent reservoir (formerly ``test_snn_emits_spikes``) was
  resolved by formula v2 DELETING the entire SNN subsystem -- a behaviour change, not
  a fix that made it fire -- so that test is gone with the subsystem it certified; and
* the mid-axis envelope breach (``test_mid_axis_recovers_within_its_envelope``) was
  resolved by widening the persisted ``latent_axes`` to float32 (state codec v2).

The strict-xfail mechanism paid out before that -- worth reading before trusting any
pin here:

That mechanism has now paid out twice, and both payouts are worth reading before
trusting any pin here:

* ``test_invocations_are_not_rejected_wholesale`` (the STATE_QUANTIZE_ERROR
  livelock) started passing when the float16 bound vocabulary was fixed, the
  strict xfail failed the suite, and the test was converted to a plain assertion
  carrying its own history.
* ``test_mid_axis_recovers_within_its_envelope`` stayed red but for an entirely
  different reason than its pin claimed: it blamed a mid<-slow coupling that does
  not exist in ``_advance_axes``, when most of the measured shortfall was the
  probe's own 40-turn settle and the small remainder is the envelope's thin
  margin. **A pin records a measurement; it does not license the explanation
  attached to it.** Re-measure before trusting a pin's reason -- and size the
  sample for the defect rate you mean to detect, which is why RECOVERY_SESSIONS
  is no longer 3.
"""

from __future__ import annotations

import json
import os

import pytest

from scripts import v3_stability


LONG_GATES = os.environ.get("SYLANNE_V3_LONG_GATES") == "1"

#: The plan's declared stream size; the default keeps the suite usable.
FULL_GATE_TURNS = 100_000
DEFAULT_TURNS = 400
STREAM_TURNS = FULL_GATE_TURNS if LONG_GATES else DEFAULT_TURNS
#: Matches ``run_gate``'s own default. Was 3, which was too small a sample to see the
#: mid envelope's ~9% breach rate: seeds 2718-2720 all pass, so the suite showed a
#: green tick for an envelope the G0 report fails. Sizing a sample below the defect
#: rate it is meant to detect is not a saving.
RECOVERY_SESSIONS = 32 if LONG_GATES else 8
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


def test_the_gate_passes_now_that_the_snn_defect_was_deleted() -> None:
    """The G0 gate now PASSES.

    It used to FAIL for one live defect: the SNN reservoir was structurally silent,
    so ``total_spikes == 0`` raised a "zero spikes" failure (and the mid-axis envelope
    breach, since fixed by state codec v2).  formula v2 deleted the SNN subsystem
    entirely, so that defect is resolved by removal rather than by making the reservoir
    fire -- the "zero spikes" failure is retired and the remaining invariants hold.
    """

    report = v3_stability.run_gate(2718, 400, sessions=1, k_turns=40)
    assert report["passed"] is True, report["failures"]
    assert report["failures"] == []


# --------------------------------------------------------------------------- #
# Known production defects — pinned, not hidden
# --------------------------------------------------------------------------- #


# NOTE (formula v2): the former ``test_snn_emits_spikes`` strict-xfail is DELETED.
# It pinned the measured defect that the SNN reservoir never fired through
# ``orchestrate`` (max membrane ~0.32 vs a 0.65 threshold floor).  That defect did
# not need fixing -- the whole SNN subsystem was deleted -- so its death certificate
# is retired along with the subsystem it certified.


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


def test_mid_axis_recovers_within_its_envelope(recoveries: list[dict]) -> None:
    """The mid axis meets its declared <=0.35-of-peak-at-turn-20 envelope.

    Was ``xfail(strict)`` through two *different* wrong attributions. Both are kept
    here, because the way this pin was read is the actual lesson.

    Attribution 1 (wrong): "slow is retentive by design and couples into mid via
    OFF_DIAGONAL_COUPLINGS, so mid relaxes toward a slow-shifted equilibrium."
    There is no such coupling. ``dynamics/multiscale.py::_advance_axes`` computes
    mid from ``(mid, fast')`` only; slow is never read by the mid update. Resetting
    slow after the pulse leaves the mid trajectory bit-identical.

    Attribution 2 (wrong, and the one that nearly closed the case): "root cause is
    margin, not a bug -- 0.35@20 leaves almost no headroom against the declared step
    0.12, so whether a session passes depends on how late mid peaks. Needs an
    architect ruling on the envelope, NOT another probe fix and NOT a constant
    tweak." Every number in it was real (29/32 within, breaches at 2725/2744/2745)
    and the conclusion drawn from them was still wrong. Nothing was wrong with the
    envelope: the same probe run against pure float64 arithmetic passes 32/32 with a
    max of 0.338, so the declared 0.35 gate was always satisfiable by the declared
    dynamics. The breaches were not the architecture failing its own envelope; they
    were the *storage grid* failing the architecture.

    Real root cause (state codec v1): ``latent_axes`` persisted as float16, and
    ``orchestrate`` advances the DECODED state, so the persistence grid sat inside
    the dynamics loop. Mid moves ``0.066*deviation`` per turn; float16 ulp at
    |mid|~0.3 is 2.4e-4, so every deviation below ~2e-3 had its update rounded to
    zero and the axis froze mid-recovery. Measured on the same trajectory, float16
    vs float64: seed 2725 froze at a constant 0.169 from turn 60 onward while
    float64 decayed 0.011 -> 0.000; turn-200 residual 6.6e-3 vs 3.9e-9. That is not
    a thin margin, it is a ratchet: each shock left a permanent residue and mid
    became a second slow axis, with the retention rate set by each axis's absolute
    magnitude. Widening that one field to float32 (codec v2) restores the declared
    behaviour: 32/32 within the envelope, max 0.3377, matching the float64 reference
    to three decimals.

    No gate constant was moved to make this pass. MID_RECOVERY_RATIO is still 0.35,
    MID_RECOVERY_TURNS still 20, RECOVERY_SESSIONS still 8, DYNAMICS_STEP_SIZES and
    OFF_DIAGONAL_COUPLINGS untouched, FORMULA_DIGEST unchanged (the codec is not in
    ``build_formula_manifest``). The fix is in ``state/codec.py``, and
    ``tests/test_v3_state_codec.py::test_persistence_grid_does_not_swallow_mid_axis_dynamics``
    pins the root cause directly, so reverting to float16 turns that test red rather
    than merely nudging this ratio.

    The lesson the module docstring already stated, now demonstrated a third time: a
    pin records a measurement, not an explanation. This one carried correct numbers
    under two successive wrong causes, and the second explicitly ruled out the
    category the bug was actually in.
    """

    within = sum(1 for r in recoveries if r["mid_within_envelope"])
    assert within / len(recoveries) >= v3_stability.RECOVERY_SESSION_FRACTION


# --------------------------------------------------------------------------- #
# Retired K-resampling evidence
# --------------------------------------------------------------------------- #


def test_formula_v2_gate_has_no_live_retired_profile_evidence() -> None:
    report = v3_stability.run_gate(2718, 120, sessions=1, k_turns=K_TURNS)
    assert report["evaluation_profile_id"] == "FORMULA_V2_SCALAR"
    assert "k_resampling" not in report
    report_text = json.dumps(report, sort_keys=True).lower()
    assert "snn_16" not in report_text
    assert "full_24" not in report_text
    assert "stdp" not in report_text


def test_legacy_k_divergence_api_is_an_explicit_non_executing_tombstone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("retired profile must not be replayed as formula-v2 evidence")

    monkeypatch.setattr(v3_stability, "k_action_distribution", fail_if_executed)
    report = v3_stability.k_divergence_report(2718, K_TURNS)
    assert report == {
        "status": "RETIRED_LEGACY_COMPATIBILITY",
        "live_gate": False,
        "reason": "formula v2 has no tick-count selector",
    }
