"""G0 synthetic stability gate (design 17.4 / plan Task 15).

Drives the deterministic core over long synthetic streams of normal, repeated,
out-of-order, extreme, and malformed turns and checks the declared invariants:

* no NaN/Inf and no state outside declared bounds;
* recovery envelopes after a single extreme pulse (fast axis to <=10% within 8
  neutral turns, mid axis to <=35% within 20), with online learning frozen and the
  baseline settled to an exact fixed point so the probe measures the declared
  dynamics rather than a moving target;
* slow state stays bounded, moves at most 0.03 per neutral turn, and cannot by
  itself lock an action at posterior >0.98 for 20 eligible turns;
* no permanent all-speak, all-hold, workspace winner lock, or weight saturation;
* the same revision advances at most once and a failed transaction leaves state
  byte-identical;
* the formula-v2 scalar profile is the only live computation profile exercised.

**What this gate does NOT claim.** G0 is a synthetic invariant/fault-injection
gate. It makes no claim about conversational gain, no claim that a learned
configuration beats a control, and no claim about calibration. Those live behind
G1/G3/G4 on frozen real data and are reported by name.

Tick-count resampling belonged to the retired formula-v1 subsystem. The legacy
API remains as a non-executing tombstone, but its profiles and thresholds cannot
contribute evidence to this formula-v2 gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts import v3_export
from sylanne_alpha.v3core import formula_v1 as formula
from sylanne_alpha.v3core.contracts import (
    Action,
    ComputeProfile,
    CoreInvocation,
    TurnContextClass,
    TurnEnvelope,
    TurnKey,
    TurnSequence,
)
from sylanne_alpha.v3core.orchestrator import orchestrate
from sylanne_alpha.v3core.state.codec import decode_state

TURN_CLASSES = ("normal", "repeated", "out_of_order", "extreme", "malformed")
ACTIONS = ("SPEAK", "HOLD", "CLARIFY", "REACH")

FAST_SLICE = slice(0, 8)
MID_SLICE = slice(8, 16)
SLOW_SLICE = slice(16, 24)

FAST_RECOVERY_TURNS = 8
FAST_RECOVERY_RATIO = 0.10
MID_RECOVERY_TURNS = 20
MID_RECOVERY_RATIO = 0.35
SLOW_MAX_STEP = 0.03
#: Upper bound on the settle loop below; reaching it is a probe hard-failure, never
#: a silent downgrade to "close enough".
#:
#: Was 1000 against a measured 302-turn settle (>3x headroom).  Both numbers were
#: artifacts of the float16 latent grid: the settle loop stops when the axes stop
#: changing *bit-for-bit*, and on the half grid the slow axis (which moves only
#: ~0.0128*deviation per turn) fell into its own quantization dead zone almost
#: immediately.  Widening ``latent_axes`` to float32 (state codec v2) moved the real
#: fixed point out to a measured **986 turns, identical for all 32 seeds** -- 14 turns
#: short of the old cap.  The settle phase is fed a constant ``_neutral_raw()`` from a
#: constant start state, so 986 is deterministic rather than the tail of a
#: distribution; but 1.4% margin in front of a hard exception is luck, not headroom.
#:
#: Raising the cap is free: the loop breaks on convergence, so the cap costs nothing
#: unless it is actually needed, and it still hard-fails rather than degrading.  The
#: old cap could NOT simply be raised, because the settle phase used turn ids
#: ``r{index}`` from the same namespace as the pulse (``r1000``) and the recovery
#: (``r2001``..``r2020``); a settle turn beyond index 1000 would have re-used the
#: pulse's turn id, and the turn registry would have deduplicated the pulse into a
#: no-op -- an "envelope met" green tick for a session that was never perturbed.
#: The settle phase therefore now emits ``s{index}`` ids in a disjoint namespace,
#: which is what makes this bound raisable at all.
SETTLE_MAX_TURNS = 4000
POSTERIOR_LOCK_LEVEL = 0.98
POSTERIOR_LOCK_TURNS = 20
RECOVERY_SESSION_FRACTION = 0.999

#: Formula v2 has one live scalar profile; recovery probes exercise that profile.
FROZEN_LEARNING_PROFILE = formula.FORMULA_V2_PROFILE_ID


class StabilityFailure(RuntimeError):
    """A declared G0 invariant was violated."""


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def _profile(profile_id: str) -> ComputeProfile:
    snn_enabled, ticks, stdp_enabled, reuse = formula.COMPUTE_PROFILES[profile_id]
    return ComputeProfile(
        profile_id=profile_id,
        snn_enabled=snn_enabled,
        ticks=ticks,
        stdp_enabled=stdp_enabled,
        reuse_last_summary=reuse,
        math_backend="scalar-v1",
        formula_version=formula.FORMULA_VERSION,
        model_version=formula.FORMULA_VERSION,
    )


def neutral_state():
    return decode_state(v3_export.neutral_eval_state_bytes())


def _neutral_raw() -> tuple:
    """A neutral, fully-valid observation: the fixed point the envelopes measure from."""

    values: list[float | None] = [None] * formula.OBSERVATION_DIM
    for index in range(formula.OBSERVATION_DIM):
        if index in v3_export.DERIVED_CHANNELS:
            values[index] = None
        elif index in (22, 30):
            values[index] = 0.0
        elif index == 31:
            values[index] = 60.0
        else:
            values[index] = 0.5
    return tuple(values)


def _extreme_raw(rng: random.Random) -> tuple:
    values: list[float | None] = [None] * formula.OBSERVATION_DIM
    for index in range(formula.OBSERVATION_DIM):
        if index in v3_export.DERIVED_CHANNELS:
            values[index] = None
        elif index in (22, 30):
            values[index] = float(rng.randint(0, 1))
        elif index == 31:
            values[index] = 10.0 ** rng.uniform(0, 6)
        else:
            values[index] = rng.choice([-1e6, -1.0, 0.0, 1.0, 1e6])
    return tuple(values)


def _malformed_raw(rng: random.Random) -> tuple:
    """Deliberately invalid facts: the DTO must fail closed, not sanitize."""

    values = list(_neutral_raw())
    kind = rng.choice(["nan", "inf", "int", "string", "short", "derived_present"])
    index = rng.choice([i for i in range(formula.OBSERVATION_DIM) if i not in v3_export.DERIVED_CHANNELS])
    if kind == "nan":
        values[index] = float("nan")
    elif kind == "inf":
        values[index] = float("inf")
    elif kind == "int":
        values[index] = 1  # exact-type violation: int is not float
    elif kind == "string":
        values[index] = "0.5"
    elif kind == "short":
        return tuple(values[:-1])
    else:
        values[27] = 1.0  # a derived channel supplied as a raw fact
    return tuple(values)


def _envelope(raw: tuple, context: TurnContextClass, previous: Action | None, sequence: TurnSequence,
              profile_id: str, seed: bytes, turn_id: str) -> TurnEnvelope:
    state_ref = v3_export.NEUTRAL_SESSION_REF
    return TurnEnvelope(
        turn_key=TurnKey(
            plugin_instance_id="v3-stability",
            session_ref=state_ref,
            bridge_request_nonce=turn_id,
            request_attempt=0,
        ),
        turn_id=turn_id,
        sequence=sequence,
        compute_profile=_profile(profile_id),
        deterministic_seed=seed,
        observation=(raw, previous),
        context=context,
    )


# --------------------------------------------------------------------------- #
# Long synthetic stream
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class StreamStats:
    turns: int = 0
    accepted: int = 0
    rejected: int = 0
    reject_reasons: dict = field(default_factory=dict)
    #: Neutral legacy trace counters retained for trace-schema compatibility.
    #: Formula-v2 stability verdicts do not consume them.
    total_spikes: int = 0
    max_membrane_voltage: float = 0.0
    min_threshold: float = float("inf")
    malformed_fed: int = 0
    malformed_rejected: int = 0
    repeated_fed: int = 0
    repeated_divergent: int = 0
    out_of_order_fed: int = 0
    action_counts: dict = field(default_factory=lambda: {a: 0 for a in ACTIONS})
    max_action_run: int = 0
    max_winner_run: int = 0
    max_posterior_lock_run: int = 0
    max_weight_saturation: float = 0.0
    max_abs_latent: float = 0.0
    nonfinite: int = 0
    out_of_bounds: int = 0


def run_stream(
    seed: int,
    turns: int,
    profile_id: str = formula.FORMULA_V2_PROFILE_ID,
) -> StreamStats:
    """Walk a long mixed synthetic stream and record every declared invariant."""

    rng = random.Random(seed)
    stats = StreamStats()
    state = neutral_state()
    previous: Action | None = None
    sequence = 0
    last_action: str | None = None
    action_run = 0
    last_winner: tuple | None = None
    winner_run = 0
    lock_run = 0

    for index in range(turns):
        kind = rng.choices(TURN_CLASSES, weights=[0.60, 0.10, 0.10, 0.15, 0.05])[0]
        stats.turns += 1
        context = rng.choice(list(TurnContextClass))
        seed_bytes = v3_export.evaluation_turn_seed(seed.to_bytes(16, "big"), index)

        if kind == "malformed":
            stats.malformed_fed += 1
            before = v3_export.encode_state_bytes(state)
            try:
                envelope = _envelope(
                    _malformed_raw(rng), context, previous,
                    TurnSequence(1, sequence + 1), profile_id, seed_bytes, f"t{index}",
                )
                orchestrate(CoreInvocation(envelope=envelope, base_state=state, projected_actual_outcome=None))
            except (TypeError, ValueError):
                stats.malformed_rejected += 1
            # A malformed turn must leave the state byte-identical.
            if v3_export.encode_state_bytes(state) != before:
                raise StabilityFailure("a malformed turn mutated committed state")
            continue

        if kind == "out_of_order":
            stats.out_of_order_fed += 1
            local = max(1, sequence - rng.randint(1, 3))
        elif kind == "extreme":
            sequence += 1
            local = sequence
        else:
            sequence += 1
            local = sequence

        raw = _extreme_raw(rng) if kind == "extreme" else _neutral_raw()
        if kind == "normal":
            raw = tuple(
                None if value is None else (value if i in (22, 30, 31) else rng.random())
                for i, value in enumerate(raw)
            )
        envelope = _envelope(
            raw, context, previous, TurnSequence(1, local), profile_id, seed_bytes, f"t{index}"
        )
        actual = rng.choice([Action(a) for a in v3_export.LEGAL_ACTIONS_BY_CONTEXT[context.value]] + [None])
        invocation = CoreInvocation(
            envelope=envelope, base_state=state, projected_actual_outcome=(actual, None)
        )
        result = orchestrate(invocation)

        if kind == "repeated":
            stats.repeated_fed += 1
            # The same revision must recompute identically from the same pre-state.
            # A rejected invocation has no state/trace at all, so the identity to
            # check there is that it rejects identically.
            again = orchestrate(invocation)
            if again.accepted != result.accepted:
                stats.repeated_divergent += 1
            elif not result.accepted:
                if again.reject_reason != result.reject_reason:
                    stats.repeated_divergent += 1
            else:
                if (
                    again.trace_bytes != result.trace_bytes
                    or again.payload_digest != result.payload_digest
                ):
                    stats.repeated_divergent += 1
                if again.state_delta.next_state.revision != result.state_delta.next_state.revision:
                    raise StabilityFailure("the same revision advanced twice")

        if not result.accepted:
            stats.rejected += 1
            stats.reject_reasons[result.reject_reason] = (
                stats.reject_reasons.get(result.reject_reason, 0) + 1
            )
            continue
        stats.accepted += 1
        trace = result.trace
        state = result.state_delta.next_state
        stats.total_spikes += sum(trace.spike_counts)  # always 0: SNN deleted (formula v2)

        for value in state.latent_axes:
            if not math.isfinite(value):
                stats.nonfinite += 1
            stats.max_abs_latent = max(stats.max_abs_latent, abs(value))
        if any(not math.isfinite(v) for v in trace.candidate_posterior):
            stats.nonfinite += 1
        # formula v2 label-free bound (spec §4.3): the L1 offset is a convex
        # combination inside [-0.30, 0.30], persisted on the float16 grid
        # (float16(0.30)=0.300048828125), so it can never escape the widened box.
        # decode_state already validates this every turn; the explicit assertion
        # pins the invariant loudly rather than only implicitly through a reject.
        if state.label_free is not None:
            for value in state.label_free.pref_offset:
                if not math.isfinite(value) or abs(value) > 0.30 + 1e-3:
                    stats.out_of_bounds += 1

        action = trace.selected_action
        stats.action_counts[action] = stats.action_counts.get(action, 0) + 1
        action_run = action_run + 1 if action == last_action else 1
        last_action = action
        stats.max_action_run = max(stats.max_action_run, action_run)

        winner = tuple(trace.broadcast_ids)
        winner_run = winner_run + 1 if winner == last_winner else 1
        last_winner = winner
        stats.max_winner_run = max(stats.max_winner_run, winner_run)

        top = max(trace.candidate_posterior) if trace.candidate_posterior else 0.0
        lock_run = lock_run + 1 if top > POSTERIOR_LOCK_LEVEL else 0
        stats.max_posterior_lock_run = max(stats.max_posterior_lock_run, lock_run)
        stats.max_weight_saturation = max(stats.max_weight_saturation, trace.weight_saturation)
        previous = actual
    return stats


# --------------------------------------------------------------------------- #
# Recovery envelopes
# --------------------------------------------------------------------------- #


def _norm(values: Sequence[float]) -> float:
    return math.sqrt(sum(value * value for value in values))


def recovery_probe(seed: int) -> dict:
    """One session: settle -> single extreme pulse -> neutral recovery."""

    rng = random.Random(seed)
    state = neutral_state()
    sequence = 0
    profile_id = FROZEN_LEARNING_PROFILE  # learning frozen: measure the dynamics only

    def step(raw: tuple, index: int, turn_id_prefix: str = "r"):
        nonlocal state, sequence
        sequence += 1
        envelope = _envelope(
            raw, TurnContextClass.ADDRESSED, None, TurnSequence(1, sequence), profile_id,
            v3_export.evaluation_turn_seed(seed.to_bytes(16, "big"), index),
            f"{turn_id_prefix}{index}",
        )
        result = orchestrate(
            CoreInvocation(envelope=envelope, base_state=state, projected_actual_outcome=None)
        )
        if result.accepted:
            state = result.state_delta.next_state
        return result

    # Settle to the ACTUAL neutral fixed point rather than for an arbitrary turn
    # count.  A fixed 40-turn settle was the dominant term in this probe's error:
    # the mid axis contracts ~0.934/turn and the slow axis ~0.9872/turn, so at turn
    # 40 the baseline is still drifting.  Measured, baseline(40) differs from the
    # settled baseline by 0.032 (mid) and 0.600 (slow) -- and because the envelope
    # is |axes - baseline|, that drift was scored as if it were un-recovered
    # perturbation.  It is not: it is baseline error.  With a true fixed point the
    # mid ratio drops from ~0.57 to ~0.28 (seed 2718) and the declared <=0.35
    # envelope is met.
    #
    # The stop condition is an EXACT fixed point of the measured quantity: the latent
    # axes are persisted on a finite grid, so once every per-turn increment falls
    # below half a ulp the axes stop changing bit-for-bit and stay stopped.  The
    # update is contracting (see ``validate_jacobian_gate``), so such a point exists
    # on any finite grid; only *when* it is reached depends on the grid.  Measured:
    # turn 986, identical for all 32 seeds (the settle input is a constant neutral
    # frame from a constant start state, so this is deterministic, not a sample).
    #
    # It was 302 under the float16 latent grid.  That 3x speed-up was not the probe
    # converging faster -- it was the storage grid swallowing the dynamics, the same
    # defect this codec version fixes (see ``state/codec.py`` v2).  A settle that
    # "converges" because the format is too coarse to represent the next increment is
    # measuring the format, not the fixed point.
    #
    # The settle phase emits ``s{index}`` turn ids, NOT ``r{index}``: the pulse below
    # is ``r1000`` and the recovery is ``r2001``..``r2020``, so a shared namespace
    # would cap the settle at 1000 turns forever -- and silently, since colliding turn
    # ids are deduplicated by the turn registry rather than rejected.
    #
    # NOTE: the stop condition is deliberately NOT "encode_state bytes repeat".
    # ``encode_state`` serializes ``revision``, ``last_committed_turn_id``,
    # ``last_committed_turn_sequence``, ``pending_outcome`` and the ``experiences``
    # ring, every one of which is fresh per turn by construction -- so the full
    # state bytes provably never repeat and such a loop would always run to the cap
    # and hard-fail.  Measured over 1000 neutral turns those five fields are the
    # only ones still changing after the dynamics have stopped.
    previous_axes: tuple | None = None
    settle_turns: int | None = None
    for index in range(SETTLE_MAX_TURNS):
        step(_neutral_raw(), index, turn_id_prefix="s")
        current_axes = tuple(state.latent_axes)
        if previous_axes is not None and current_axes == previous_axes:
            settle_turns = index + 1
            break
        previous_axes = current_axes
    if settle_turns is None:
        # Hard-fail: never measure an envelope against a moving baseline.  A probe
        # that silently degraded here would report baseline drift as perturbation,
        # which is exactly the defect this settle replaced.
        raise StabilityFailure(
            f"the neutral fixed point was not reached within {SETTLE_MAX_TURNS} turns: "
            "the recovery envelope cannot be measured against a moving baseline"
        )
    baseline = tuple(state.latent_axes)

    step(_extreme_raw(rng), 1000)  # one extreme pulse
    pulsed = tuple(state.latent_axes)

    def fast_perturbation(values: tuple) -> float:
        return _norm([values[i] - baseline[i] for i in range(*FAST_SLICE.indices(24))])

    def mid_perturbation(values: tuple) -> float:
        return _norm([values[i] - baseline[i] for i in range(*MID_SLICE.indices(24))])

    # The denominator must be the PEAK perturbation, not the value one turn after
    # the pulse. The mid axis is a slow integrator (step 0.12): measured, its
    # perturbation is still rising at turn 1 and only peaks around turn 3, so
    # normalizing by the turn-1 value would divide by a number smaller than the
    # perturbation itself and report ratios above 1 forever.
    fast_peak = fast_perturbation(pulsed)
    mid_peak = mid_perturbation(pulsed)

    fast_ratio = None
    mid_ratio = None
    slow_steps: list[float] = []
    previous_slow = tuple(pulsed[i] for i in range(*SLOW_SLICE.indices(24)))
    trajectory: list[tuple] = []
    for offset in range(1, MID_RECOVERY_TURNS + 1):
        step(_neutral_raw(), 2000 + offset)
        current = tuple(state.latent_axes)
        fast_now = fast_perturbation(current)
        mid_now = mid_perturbation(current)
        fast_peak = max(fast_peak, fast_now)
        mid_peak = max(mid_peak, mid_now)
        trajectory.append((offset, fast_now, mid_now))
        slow = tuple(current[i] for i in range(*SLOW_SLICE.indices(24)))
        slow_steps.append(max(abs(a - b) for a, b in zip(slow, previous_slow)))
        previous_slow = slow

    for offset, fast_now, mid_now in trajectory:
        if offset == FAST_RECOVERY_TURNS:
            fast_ratio = (fast_now / fast_peak) if fast_peak > 1e-12 else 0.0
        if offset == MID_RECOVERY_TURNS:
            mid_ratio = (mid_now / mid_peak) if mid_peak > 1e-12 else 0.0

    return {
        "fast_ratio": fast_ratio,
        "mid_ratio": mid_ratio,
        "fast_peak": fast_peak,
        "mid_peak": mid_peak,
        "settle_turns": settle_turns,
        "fast_within_envelope": (fast_ratio or 0.0) <= FAST_RECOVERY_RATIO,
        "mid_within_envelope": (mid_ratio or 0.0) <= MID_RECOVERY_RATIO,
        "max_slow_step": max(slow_steps) if slow_steps else 0.0,
        "slow_within_envelope": (max(slow_steps) if slow_steps else 0.0) <= SLOW_MAX_STEP,
        "slow_bounded": all(math.isfinite(value) for value in state.latent_axes),
    }


# --------------------------------------------------------------------------- #
# K resampling
# --------------------------------------------------------------------------- #


def k_action_distribution(seed: int, turns: int, profile_id: str) -> dict:
    stats = run_stream(seed, turns, profile_id=profile_id)
    total = sum(stats.action_counts.values()) or 1
    return {action: stats.action_counts.get(action, 0) / total for action in ACTIONS}


def k_divergence_report(seed: int, turns: int) -> dict:
    """Retained API tombstone; formula v2 has no tick-count selector to compare."""

    del seed, turns
    return {
        "status": "RETIRED_LEGACY_COMPATIBILITY",
        "live_gate": False,
        "reason": "formula v2 has no tick-count selector",
    }


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #


def evaluate(stats: StreamStats, recoveries: list[dict]) -> tuple[list[str], dict]:
    failures: list[str] = []
    if stats.nonfinite:
        failures.append("nonfinite value observed")
    if stats.out_of_bounds:
        failures.append("a label-free preference offset escaped its declared bound")
    if stats.malformed_fed != stats.malformed_rejected:
        failures.append("a malformed turn was not rejected")
    if stats.repeated_divergent:
        failures.append("a repeated identical invocation diverged")
    if stats.max_posterior_lock_run >= POSTERIOR_LOCK_TURNS:
        failures.append("an action locked above posterior 0.98 for 20 eligible turns")
    if stats.max_weight_saturation >= 1.0:
        failures.append("plastic weights fully saturated")
    distinct = sum(1 for count in stats.action_counts.values() if count > 0)
    if distinct < 2:
        failures.append("permanent single-action behaviour (all-speak/all-hold)")
    if stats.accepted and stats.max_action_run > 0.5 * max(stats.accepted, 1):
        failures.append("one action dominated more than half the stream consecutively")
    if stats.accepted and stats.max_winner_run > 0.5 * max(stats.accepted, 1):
        failures.append("workspace winner lock")
    # formula v2 deleted the SNN subsystem: there is no reservoir left to be silent,
    # so the former "zero spikes across the stream" failure is retired -- that defect
    # was resolved by deleting the subsystem rather than by making it fire.
    # A rejected invocation commits nothing. A sustained reject rate means the
    # shadow has stopped advancing state at all.
    if stats.turns and stats.rejected / stats.turns > 0.05:
        failures.append(
            f"{stats.rejected}/{stats.turns} invocations rejected "
            f"({stats.rejected / stats.turns:.1%}): reasons={stats.reject_reasons}"
        )

    fast_ok = sum(1 for r in recoveries if r["fast_within_envelope"])
    mid_ok = sum(1 for r in recoveries if r["mid_within_envelope"])
    slow_ok = sum(1 for r in recoveries if r["slow_within_envelope"])
    total = max(len(recoveries), 1)
    summary = {
        "sessions": len(recoveries),
        "fast_within_envelope_fraction": fast_ok / total,
        "mid_within_envelope_fraction": mid_ok / total,
        "slow_within_envelope_fraction": slow_ok / total,
        "required_fraction": RECOVERY_SESSION_FRACTION,
    }
    for name, value in (
        ("fast", summary["fast_within_envelope_fraction"]),
        ("mid", summary["mid_within_envelope_fraction"]),
        ("slow", summary["slow_within_envelope_fraction"]),
    ):
        if value < RECOVERY_SESSION_FRACTION:
            failures.append(f"{name}-axis recovery envelope met by only {value:.3%} of sessions")
    return failures, summary


def run_gate(seed: int, turns: int, sessions: int = 8, k_turns: int = 400) -> dict:
    # ``k_turns`` is accepted only for CLI/API compatibility. It cannot select or
    # score a retired profile in formula-v2 evidence.
    del k_turns
    stats = run_stream(seed, turns)
    recoveries = [recovery_probe(seed + offset) for offset in range(sessions)]
    failures, recovery_summary = evaluate(stats, recoveries)

    report = {
        "report_kind": "v3_stability_g0_v2",
        "seed": seed,
        "turns": stats.turns,
        "evaluation_profile_id": formula.FORMULA_V2_PROFILE_ID,
        "turn_classes": list(TURN_CLASSES),
        "formula_digest": formula.FORMULA_DIGEST,
        "gate_manifest_digest": v3_export.default_gate_manifest_digest(),
        "runtime_fingerprint_digest": _fingerprint_digest(),
        "stream": {
            "accepted": stats.accepted,
            "rejected": stats.rejected,
            "malformed_fed": stats.malformed_fed,
            "malformed_rejected": stats.malformed_rejected,
            "repeated_fed": stats.repeated_fed,
            "repeated_divergent": stats.repeated_divergent,
            "out_of_order_fed": stats.out_of_order_fed,
            "action_counts": stats.action_counts,
            "max_action_run": stats.max_action_run,
            "max_winner_run": stats.max_winner_run,
            "max_posterior_lock_run": stats.max_posterior_lock_run,
            "max_weight_saturation": stats.max_weight_saturation,
            "max_abs_latent": stats.max_abs_latent,
            "nonfinite": stats.nonfinite,
        },
        "recovery": recovery_summary,
        "failures": failures,
        "passed": not failures,
        "claims": {
            "conversational_gain": False,
            "learned_vs_control_superiority": False,
            "calibration": False,
        },
    }
    report["report_digest"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return report


def _fingerprint_digest() -> str:
    from scripts.v3_replay import fingerprint_digest, runtime_fingerprint

    return fingerprint_digest(runtime_fingerprint())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the G0 synthetic stability gate.")
    parser.add_argument("--seed", type=int, default=2718)
    parser.add_argument("--turns", type=int, default=100_000)
    parser.add_argument("--sessions", type=int, default=8)
    parser.add_argument("--k-turns", type=int, default=400, help=argparse.SUPPRESS)
    parser.add_argument("--report", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_gate(args.seed, args.turns, sessions=args.sessions, k_turns=args.k_turns)
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "seed": report["seed"],
                "turns": report["turns"],
                "passed": report["passed"],
                "failures": report["failures"],
                "recovery": report["recovery"],
            },
            indent=2,
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
