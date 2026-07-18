"""Offline chronological-prequential replay of an encoded v3 dataset (design 17.2).

Replay resets to each episode's frozen ``neutral_eval_v2`` header state and walks
the episode in order: predict turn ``t`` using only the header and observations
strictly before ``t``, score the frozen outcome/action, then allow the declared
online update for ``t+1``. It never mutates the dataset and never guesses a
runtime state: G3's observed state/profile stay diagnostic.

The report embeds the gate-manifest, dataset, and runtime-fingerprint digests so a
number can never be quoted without the configuration that produced it.

Scope honesty: this replay measures offline predictive fit on frozen facts. It is
not a conversational-gain claim, not a causal claim, and not a calibration pass on
its own — those gates are named explicitly in the gate manifest and reported by
name, including `INSUFFICIENT_EVIDENCE` when coverage is too thin.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts import v3_export
from scripts.v3_export import Dataset, Episode
from sylanne_alpha.v3core import formula_v1 as formula
from sylanne_alpha.v3core.contracts import (
    Action,
    ComputeProfile,
    CoreInvocation,
    ReactionFacts,
    TurnContextClass,
    TurnEnvelope,
    TurnKey,
    TurnSequence,
)
from sylanne_alpha.v3core.features import decision_state
from sylanne_alpha.v3core.inference.policy_scorer import base_preference_c, generative_mu
from sylanne_alpha.v3core.learning.label_free import _update_pref_offset
from sylanne_alpha.v3core.learning.outcomes import ekf_transition_update
from sylanne_alpha.v3core.observation.encoder import project_outcome
from sylanne_alpha.v3core.observation.models import OutcomeFrame
from sylanne_alpha.v3core.orchestrator import orchestrate
from sylanne_alpha.v3core.state.codec import decode_state

ACTIONS = ("SPEAK", "HOLD", "CLARIFY", "REACH")
_EPS = 1e-12
_Z68 = 1.0
_Z95 = 1.959963984540054  # the 0.95 two-sided normal quantile

PRIMARY_METRICS = ("actual_action_log_loss", "actual_action_brier", "next_turn_valid_axis_weighted_mae")


class ReplayError(RuntimeError):
    """Replay refused to produce a number it could not stand behind."""


# --------------------------------------------------------------------------- #
# Runtime fingerprint (design 16.2)
# --------------------------------------------------------------------------- #


def runtime_fingerprint(profile_id: str = v3_export.EVALUATION_PROFILE_ID) -> dict:
    """Byte-identical replay is only promised within one declared fingerprint."""

    return {
        "formula_version": formula.FORMULA_VERSION,
        "formula_digest": formula.FORMULA_DIGEST,
        "model_revision": formula.ACTION_MODEL_REVISION,
        "profile_id": profile_id,
        "python_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "math_backend": "scalar-v1",
        "cpu_architecture": platform.machine(),
    }


def fingerprint_digest(fingerprint: dict) -> str:
    payload = json.dumps(fingerprint, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(b"sylanne.v3.runtime-fingerprint.v1\x00" + payload).hexdigest()


# --------------------------------------------------------------------------- #
# Per-turn replay record
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class TurnResult:
    episode_ref: str
    index: int
    shadow_action: str
    actual_action: str
    posterior: dict
    credit_adjacency: bool
    scored: bool
    illegal: bool
    nonfinite: bool
    axis_abs_error: tuple = ()
    coverage_68: tuple = ()
    coverage_95: tuple = ()


@dataclass(slots=True)
class ReplayCounters:
    illegal_action_count: int = 0
    nonfinite_action_count: int = 0
    rejected_invocations: int = 0
    privacy_violation_count: int = 0
    adjacency_disagreements: int = 0
    #: Frozen actual actions the scorer cannot even represent, because they are
    #: outside the legal set for their context. Their probability is zero, so log
    #: loss saturates at -log(eps): the metric stops being a measurement and
    #: becomes an artifact of the clip. This must be surfaced, never averaged in
    #: silently.
    actual_action_outside_legal_set: int = 0


# --------------------------------------------------------------------------- #
# Core replay
# --------------------------------------------------------------------------- #


def _profile_for(profile_id: str) -> ComputeProfile:
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


def replay_episode(
    episode: Episode,
    *,
    profile_id: str = v3_export.EVALUATION_PROFILE_ID,
    counters: ReplayCounters | None = None,
    initial_state_mutator=None,
    seed_override: bytes | None = None,
) -> list[TurnResult]:
    """Replay one episode from its frozen header state, strictly in order."""

    counters = counters if counters is not None else ReplayCounters()
    state = decode_state(episode.header["initial_state_b64"].encode("ascii"))
    if initial_state_mutator is not None:
        state = initial_state_mutator(state)
    profile = _profile_for(profile_id)
    episode_seed = seed_override if seed_override is not None else episode.episode_seed

    results: list[TurnResult] = []
    previous_action: Action | None = None
    pending_mu: tuple = ()
    pending_v: tuple = ()

    for turn in episode.turns:
        index = turn["episode_turn_index"]
        frame = v3_export.frame_for_turn(turn, previous_action)

        # Score the *previous* turn's next-observation prediction against this
        # turn's frozen outcome before advancing (prequential order).
        axis_error: tuple = ()
        cover68: tuple = ()
        cover95: tuple = ()
        if pending_mu:
            outcome = project_outcome(frame)
            errors, c68, c95 = [], [], []
            for axis in range(formula.AXIS_DIM):
                if not outcome.is_valid(axis):
                    continue
                mu = pending_mu[axis]
                errors.append(abs(mu - outcome.y[axis]))
                if axis < len(pending_v):
                    sigma = math.sqrt(max(pending_v[axis], _EPS))
                    deviation = abs(outcome.y[axis] - mu)
                    c68.append(1.0 if deviation <= _Z68 * sigma else 0.0)
                    c95.append(1.0 if deviation <= _Z95 * sigma else 0.0)
            axis_error, cover68, cover95 = tuple(errors), tuple(c68), tuple(c95)

        actual_name = turn["actual_action"]
        actual = Action(actual_name) if actual_name in ACTIONS else None

        envelope = TurnEnvelope(
            turn_key=TurnKey(
                plugin_instance_id="v3-replay",
                session_ref=state.session_ref,
                bridge_request_nonce=f"{episode.episode_ref[:16]}-{index}",
                request_attempt=0,
            ),
            turn_id=f"{episode.episode_ref[:16]}-{index}",
            sequence=TurnSequence(
                writer_epoch=turn["writer_epoch"], local_sequence=turn["local_sequence"]
            ),
            compute_profile=profile,
            deterministic_seed=v3_export.evaluation_turn_seed(episode_seed, index),
            observation=(_raw_for(turn), previous_action),
            context=TurnContextClass(turn["context"]),
        )
        result = orchestrate(
            CoreInvocation(
                envelope=envelope,
                base_state=state,
                projected_actual_outcome=(actual, None),
                # The frozen same_sender relation (spec §1.4) must be replayed, or an
                # offline settlement of a censored (False) reaction cannot reproduce
                # the online one.  A missing field defaults to None (admitted noise).
                reaction_facts=ReactionFacts(same_sender=turn.get("reaction_same_sender")),
            )
        )
        if not result.accepted:
            counters.rejected_invocations += 1
            # A rejected invocation commits neither state nor trace: the sequence is
            # dropped and credit is censored, exactly as the runtime would do.
            previous_action = actual
            pending_mu, pending_v = (), ()
            continue

        trace = result.trace
        posterior = dict(zip(trace.candidate_actions, trace.candidate_posterior))
        if any(not math.isfinite(value) for value in trace.candidate_posterior):
            counters.nonfinite_action_count += 1
        if trace.selected_action not in ACTIONS:
            counters.illegal_action_count += 1
        if actual is not None and actual_name not in posterior:
            counters.actual_action_outside_legal_set += 1

        # The dataset's credit_adjacency claim must agree with the core's own test.
        core_adjacent = bool(
            state.pending_outcome is not None
            and state.pending_outcome.sequence.writer_epoch == envelope.sequence.writer_epoch
            and envelope.sequence.local_sequence == state.pending_outcome.sequence.local_sequence + 1
        )
        if core_adjacent != bool(turn["credit_adjacency"]):
            counters.adjacency_disagreements += 1

        results.append(
            TurnResult(
                episode_ref=episode.episode_ref,
                index=index,
                shadow_action=trace.selected_action,
                actual_action=actual_name,
                posterior=posterior,
                credit_adjacency=bool(turn["credit_adjacency"]),
                scored=actual is not None,
                illegal=trace.selected_action not in ACTIONS,
                nonfinite=any(not math.isfinite(v) for v in trace.candidate_posterior),
                axis_abs_error=axis_error,
                coverage_68=cover68,
                coverage_95=cover95,
            )
        )

        state = result.state_delta.next_state
        previous_action = actual
        pending = state.pending_outcome
        pending_mu = tuple(pending.predictive_mu_actual) if pending is not None else ()
        pending_v = tuple(pending.predictive_v_actual) if pending is not None else ()
    return results


def _raw_for(turn: dict) -> tuple:
    values = turn["values"]
    mask = turn["valid_mask"]
    raw: list[float | None] = []
    for index in range(v3_export.OBSERVATION_DIM):
        if index in v3_export.DERIVED_CHANNELS or not (mask >> index) & 1:
            raw.append(None)
        else:
            raw.append(float(values[index]))
    return tuple(raw)


# --------------------------------------------------------------------------- #
# Label-free (formula v2) prequential evaluation (spec §6)
# --------------------------------------------------------------------------- #
#
# The label-free gates are computed by an OFFLINE prequential replay of the two
# learners on a frozen dataset -- they never read an action label.  One online
# ``orchestrate`` pass per episode extracts, per turn, the deterministic core inputs
# the settlement consumed: the pre-turn decision state ``s_dec`` (= the state the
# online path B used, ``decision_state(base.latent_axes)``), the projected next
# outcome ``y'``, and the trace's ``r_react`` / ``reaction_valid`` / adjacency.  The
# metrics then re-run the EXACT core learner laws (``ekf_transition_update`` for L2,
# ``_update_pref_offset`` for L1) over those records, so both the learner and its
# control are evaluated on identical inputs and the r_react permutation control is
# possible (it cannot be done through ``orchestrate``, which computes r_react from the
# frame).  L2 does not feed the dynamics and L1 does not feed the latent trajectory,
# so ``s_dec`` is identical for learner / frozen / permuted -- the controls differ
# only in the learner parameters, exactly as spec §6.1 requires.

_TWO_PI = 2.0 * math.pi


@dataclass(frozen=True, slots=True)
class LabelFreeTurnRecord:
    """One turn's label-free settlement inputs, extracted from an online replay."""

    settled: bool           # path B ran (pending existed and was adjacent)
    reaction_valid: bool    # eligible AND a valid reaction (drives the L1 update)
    r_react: float          # the online reaction scalar (drives L1 update + LF-2 weight)
    s_dec: tuple            # decision_state(base.latent_axes): what path B used
    outcome: OutcomeFrame   # y' = project_outcome(u') of THIS turn (the learning target)


def collect_label_free_records(
    episode: Episode,
    *,
    profile_id: str = v3_export.EVALUATION_PROFILE_ID,
) -> list[LabelFreeTurnRecord]:
    """Replay one episode online and extract its per-turn label-free records.

    Mirrors :func:`replay_episode`'s envelope construction but captures the pre-turn
    decision state and the trace's label-free verdict instead of the action posterior.
    The episode resets to its frozen header state, so each episode's learners start at
    the prior exactly as the online per-session state would.
    """

    state = decode_state(episode.header["initial_state_b64"].encode("ascii"))
    profile = _profile_for(profile_id)
    episode_seed = episode.episode_seed
    records: list[LabelFreeTurnRecord] = []
    previous_action: Action | None = None

    for turn in episode.turns:
        index = turn["episode_turn_index"]
        s_dec = decision_state(state.latent_axes)  # exactly what path B will read
        frame = v3_export.frame_for_turn(turn, previous_action)
        outcome = project_outcome(frame)
        actual_name = turn["actual_action"]
        actual = Action(actual_name) if actual_name in ACTIONS else None
        envelope = TurnEnvelope(
            turn_key=TurnKey(
                plugin_instance_id="v3-replay-lf",
                session_ref=state.session_ref,
                bridge_request_nonce=f"{episode.episode_ref[:16]}-{index}",
                request_attempt=0,
            ),
            turn_id=f"{episode.episode_ref[:16]}-{index}",
            sequence=TurnSequence(
                writer_epoch=turn["writer_epoch"], local_sequence=turn["local_sequence"]
            ),
            compute_profile=profile,
            deterministic_seed=v3_export.evaluation_turn_seed(episode_seed, index),
            observation=(_raw_for(turn), previous_action),
            context=TurnContextClass(turn["context"]),
        )
        result = orchestrate(
            CoreInvocation(
                envelope=envelope,
                base_state=state,
                projected_actual_outcome=(actual, None),
                reaction_facts=ReactionFacts(same_sender=turn.get("reaction_same_sender")),
            )
        )
        if not result.accepted:
            # A rejected invocation commits nothing and settles no credit.
            previous_action = actual
            continue
        trace = result.trace
        settled = trace.lf_censor_reason != formula.LF_CENSOR_REASON_NON_ADJACENT
        records.append(
            LabelFreeTurnRecord(
                settled=settled,
                reaction_valid=bool(trace.reaction_valid),
                r_react=float(trace.r_react),
                s_dec=s_dec,
                outcome=outcome,
            )
        )
        state = result.state_delta.next_state
        previous_action = actual
    return records


def _marginal_priors() -> tuple:
    g = tuple(formula.MARGINAL_INITIAL_G for _ in range(formula.AXIS_DIM))
    b = tuple(formula.MARGINAL_INITIAL_B for _ in range(formula.AXIS_DIM))
    sigma_g = tuple(formula.MARGINAL_SIGMA_INIT[0] for _ in range(formula.AXIS_DIM))
    sigma_b = tuple(formula.MARGINAL_SIGMA_INIT[1] for _ in range(formula.AXIS_DIM))
    return g, b, sigma_g, sigma_b


def marginal_prequential_episode(records: Sequence[LabelFreeTurnRecord]) -> dict:
    """LF-1 (spec §6.1): prequential per-axis absolute error of the L2 marginal head.

    For every adjacent settled turn, predict ``y'`` BEFORE the update with the learner
    head and with the frozen prior head, then update the learner with the exact core
    EKF.  Also reports the carry-forward baseline (predict ``y'(t+1)=y'(t)`` on
    double-valid axes) -- reported, never gated (spec §6.1).  ``口径``: each valid axis
    observation contributes one unit of weight, identical to ``axis_mae``.
    """

    g, b, sigma_g, sigma_b = _marginal_priors()
    prior_g, prior_b, _, _ = _marginal_priors()
    count = 0
    learner_abs: list[float] = []
    frozen_abs: list[float] = []
    carry_abs: list[float] = []
    previous: OutcomeFrame | None = None
    for record in records:
        if not record.settled:
            continue
        outcome = record.outcome
        mu_learner = generative_mu(g, b, record.s_dec)
        mu_frozen = generative_mu(prior_g, prior_b, record.s_dec)
        for axis in range(formula.AXIS_DIM):
            if not outcome.is_valid(axis):
                continue
            learner_abs.append(abs(mu_learner[axis] - outcome.y[axis]))
            frozen_abs.append(abs(mu_frozen[axis] - outcome.y[axis]))
            if previous is not None and previous.is_valid(axis):
                carry_abs.append(abs(previous.y[axis] - outcome.y[axis]))
        g, b, sigma_g, sigma_b, count = ekf_transition_update(
            g, b, sigma_g, sigma_b, count, record.s_dec, outcome
        )
        previous = outcome
    return {"learner_abs": learner_abs, "frozen_abs": frozen_abs, "carry_abs": carry_abs}


def _gaussian_nll(y: float, c: float, v_c: float) -> float:
    return 0.5 * (math.log(_TWO_PI * v_c) + (y - c) ** 2 / v_c)


def _mean_axis_nll(outcome: OutcomeFrame, c: tuple) -> float | None:
    terms = [
        _gaussian_nll(outcome.y[axis], c[axis], formula.PREFERENCE_V_C[axis])
        for axis in range(formula.AXIS_DIM)
        if outcome.is_valid(axis)
    ]
    return sum(terms) / len(terms) if terms else None


def _clip_unit(value: float) -> float:
    return -1.0 if value < -1.0 else 1.0 if value > 1.0 else value


def preference_prequential_episode(
    records: Sequence[LabelFreeTurnRecord], *, permutation_seed: int | None = None
) -> dict:
    """LF-2 (spec §6.1): reaction-weighted preference NLL of the L1 offset vs offset=0.

    Prequential: every ``r_react > 0`` settled turn is scored with the offset in force
    BEFORE this turn's update; then the offset is advanced by the exact core L1 law on
    any ``reaction_valid`` turn.  The learner offset uses base_c + offset; the frozen
    control uses base_c (offset 0).  ``permutation_seed`` shuffles the
    ``(r_react, reaction_valid)`` pairs across settled turns within the episode (LF-4):
    if the offset only captured a marginal outcome drift rather than a reaction-
    conditioned structure, the shuffled gain does not collapse.
    """

    settled = [record for record in records if record.settled]
    pairs = [(record.r_react, record.reaction_valid) for record in settled]
    if permutation_seed is not None:
        rng = random.Random(permutation_seed)
        order = list(range(len(pairs)))
        rng.shuffle(order)
        pairs = [pairs[position] for position in order]

    offset = tuple(0.0 for _ in range(formula.AXIS_DIM))
    learner_terms: list[float] = []
    frozen_terms: list[float] = []
    weights: list[float] = []
    for record, (r_react, reaction_valid) in zip(settled, pairs):
        base_c = base_preference_c(record.s_dec)
        if r_react > 0.0:
            c_learner = tuple(
                _clip_unit(base_c[axis] + offset[axis]) for axis in range(formula.AXIS_DIM)
            )
            nll_learner = _mean_axis_nll(record.outcome, c_learner)
            nll_frozen = _mean_axis_nll(record.outcome, base_c)
            if nll_learner is not None and nll_frozen is not None:
                learner_terms.append(nll_learner)
                frozen_terms.append(nll_frozen)
                weights.append(r_react)
        if reaction_valid:
            offset = _update_pref_offset(offset, r_react, record.s_dec, record.outcome)
    return {"learner_terms": learner_terms, "frozen_terms": frozen_terms, "weights": weights}


def label_free_coverage(records: Sequence[LabelFreeTurnRecord]) -> dict:
    """The three-level coverage funnel (spec §6.1): total -> adjacent -> reaction-valid."""

    total = len(records)
    adjacent = sum(1 for record in records if record.settled)
    reaction_valid = sum(1 for record in records if record.settled and record.reaction_valid)
    return {"total_turns": total, "adjacent": adjacent, "reaction_valid": reaction_valid}


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #


def _probability_of(posterior: dict, action: str) -> float:
    return max(float(posterior.get(action, 0.0)), _EPS)


def log_loss(results: Sequence[TurnResult]) -> float | None:
    scored = [r for r in results if r.scored]
    if not scored:
        return None
    return sum(-math.log(_probability_of(r.posterior, r.actual_action)) for r in scored) / len(scored)


def brier(results: Sequence[TurnResult]) -> float | None:
    scored = [r for r in results if r.scored]
    if not scored:
        return None
    total = 0.0
    for r in scored:
        for action in ACTIONS:
            predicted = float(r.posterior.get(action, 0.0))
            target = 1.0 if action == r.actual_action else 0.0
            total += (predicted - target) ** 2
    return total / len(scored)


def axis_mae(results: Sequence[TurnResult]) -> float | None:
    """Valid-axis weighted MAE: each *axis observation* is one unit of weight."""

    numerator = 0.0
    denominator = 0
    for r in results:
        numerator += sum(r.axis_abs_error)
        denominator += len(r.axis_abs_error)
    return numerator / denominator if denominator else None


def expected_calibration_error(results: Sequence[TurnResult], bins: int = 10) -> float | None:
    scored = [r for r in results if r.scored]
    if not scored:
        return None
    buckets: list[list[tuple]] = [[] for _ in range(bins)]
    for r in scored:
        if not r.posterior:
            continue
        confidence = max(r.posterior.values())
        correct = 1.0 if r.shadow_action == r.actual_action else 0.0
        index = min(int(confidence * bins), bins - 1)
        buckets[index].append((confidence, correct))
    total = sum(len(bucket) for bucket in buckets)
    if not total:
        return None
    error = 0.0
    for bucket in buckets:
        if not bucket:
            continue
        mean_confidence = sum(item[0] for item in bucket) / len(bucket)
        accuracy = sum(item[1] for item in bucket) / len(bucket)
        error += (len(bucket) / total) * abs(mean_confidence - accuracy)
    return error


def effective_sample_size(results: Sequence[TurnResult]) -> float:
    """Kish ESS. Weights are uniform here, so this equals the scored-turn count;
    it is computed explicitly so a future weighted design cannot silently inherit
    an unweighted number."""

    weights = [1.0 for r in results if r.scored]
    if not weights:
        return 0.0
    return (sum(weights) ** 2) / sum(w * w for w in weights)


def known_hold_contradiction_rate(results: Sequence[TurnResult]) -> float | None:
    """The conservative safety proxy: shadow wants to talk while v2 actually held."""

    holds = [r for r in results if r.actual_action == "HOLD"]
    if not holds:
        return None
    contradictions = sum(1 for r in holds if r.shadow_action in ("SPEAK", "REACH"))
    return contradictions / len(holds)


def action_coverage(results: Sequence[TurnResult]) -> dict:
    return {action: sum(1 for r in results if r.actual_action == action) for action in ACTIONS}


def coverage_error(results: Sequence[TurnResult], level: str) -> float | None:
    # Nominal coverage must match the z actually used: z=1.0 -> 0.6827, z=1.95996
    # -> 0.95 (NOT 0.9545, which is z=2.0).
    nominal = 0.6827 if level == "68" else 0.95
    hits = []
    for r in results:
        hits.extend(r.coverage_68 if level == "68" else r.coverage_95)
    if not hits:
        return None
    return abs((sum(hits) / len(hits)) - nominal)


def action_sequence_digest(results) -> str:
    """Digest the ordered (episode, index, action) sequence for order equality.

    An aggregate distribution cannot detect reordering: SPEAK,HOLD,SPEAK and
    HOLD,SPEAK,SPEAK are identical under it. The plan requires action/ORDER
    equality across Python minors, so the ordered sequence needs its own digest.
    """

    ordered = sorted(results, key=lambda r: (r.episode_ref, r.index))
    payload = "".join(
        f"{r.episode_ref}|{r.index}|{r.shadow_action}\n" for r in ordered
    ).encode("utf-8")
    return hashlib.sha256(b"sylanne.v3.action-sequence.v1\x00" + payload).hexdigest()


def action_distribution(results: Sequence[TurnResult]) -> dict:
    total = len(results) or 1
    return {
        action: sum(1 for r in results if r.shadow_action == action) / total for action in ACTIONS
    }


def js_divergence(left: dict, right: dict) -> float:
    """Jensen-Shannon divergence in nats over the action distribution."""

    def kl(p: dict, q: dict) -> float:
        total = 0.0
        for action in ACTIONS:
            pv = p.get(action, 0.0)
            if pv <= 0.0:
                continue
            qv = max(q.get(action, 0.0), _EPS)
            total += pv * math.log(pv / qv)
        return total

    mid = {action: 0.5 * (left.get(action, 0.0) + right.get(action, 0.0)) for action in ACTIONS}
    return 0.5 * kl(left, mid) + 0.5 * kl(right, mid)


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #


def replay_dataset(
    dataset: Dataset,
    *,
    split: str | None = "test",
    profile_id: str = v3_export.EVALUATION_PROFILE_ID,
) -> tuple[list[TurnResult], ReplayCounters]:
    counters = ReplayCounters()
    episodes = dataset.split_episodes(split) if split else dataset.episodes
    results: list[TurnResult] = []
    for episode in episodes:
        results.extend(replay_episode(episode, profile_id=profile_id, counters=counters))
    return results, counters


def build_report(
    *,
    dataset_path: Path,
    dataset: Dataset,
    manifest: dict | None,
    gate_manifest: dict,
    gate_manifest_digest: str,
    split: str | None,
    results: list[TurnResult],
    counters: ReplayCounters,
    calibration: bool,
) -> dict:
    fingerprint = runtime_fingerprint()
    coverage = action_coverage(results)
    ess = effective_sample_size(results)
    gates = gate_manifest["coverage"]

    verdicts: list[str] = []
    if ess < gates["min_effective_sample_size_overall"]:
        verdicts.append("INSUFFICIENT_EVIDENCE:effective_sample_size")
    for action in ACTIONS:
        if coverage[action] < gates["min_known_examples_per_action"]:
            verdicts.append(f"INSUFFICIENT_EVIDENCE:action_coverage:{action}")
    if counters.illegal_action_count or counters.nonfinite_action_count:
        verdicts.append("FAILED:illegal_or_nonfinite_action")
    if counters.adjacency_disagreements:
        verdicts.append("FAILED:credit_adjacency_disagreement")
    total_attempted = len(results) + counters.rejected_invocations
    reject_rate = counters.rejected_invocations / total_attempted if total_attempted else 0.0
    if reject_rate > 0.05:
        # Metrics would silently describe only the surviving prefix (e.g. the
        # pre-livelock regime) while being quoted as the whole dataset.
        verdicts.append(
            f"INSUFFICIENT_EVIDENCE:rejected_invocations:{counters.rejected_invocations}"
            f"/{total_attempted}"
        )
    if counters.actual_action_outside_legal_set:
        # Not a pass/fail on its own, but the loss is no longer a measurement:
        # never let a clipped-at-eps number be quoted as predictive fit.
        verdicts.append("INSUFFICIENT_EVIDENCE:actual_action_outside_legal_set")

    ece = expected_calibration_error(results)
    report = {
        "report_kind": "v3_replay_v1",
        "gate_manifest_digest": gate_manifest_digest,
        "dataset_digest": v3_export.file_digest(dataset_path),
        "dataset_id": manifest["dataset_id"] if manifest else None,
        "provenance_class": manifest["provenance_class"] if manifest else None,
        "runtime_fingerprint": fingerprint,
        "runtime_fingerprint_digest": fingerprint_digest(fingerprint),
        "split": split,
        "episode_count": len(dataset.split_episodes(split) if split else dataset.episodes),
        "turn_count": len(results),
        "scored_turn_count": sum(1 for r in results if r.scored),
        "effective_sample_size": ess,
        "action_coverage": coverage,
        "action_distribution": action_distribution(results),
        # An aggregate distribution cannot detect reordering: SPEAK,HOLD,SPEAK and
        # HOLD,SPEAK,SPEAK are identical under it. Digest the ordered per-turn
        # sequence so cross-version comparison can assert order, as the plan requires.
        "action_sequence_digest": action_sequence_digest(results),
        "primary_metrics": {
            "actual_action_log_loss": log_loss(results),
            "actual_action_brier": brier(results),
            "next_turn_valid_axis_weighted_mae": axis_mae(results),
        },
        "safety": {
            "known_hold_contradiction_rate": known_hold_contradiction_rate(results),
            "is_causal_claim": False,
        },
        "counters": {
            "illegal_action_count": counters.illegal_action_count,
            "nonfinite_action_count": counters.nonfinite_action_count,
            "rejected_invocations": counters.rejected_invocations,
            "privacy_violation_count": counters.privacy_violation_count,
            "adjacency_disagreements": counters.adjacency_disagreements,
            "actual_action_outside_legal_set": counters.actual_action_outside_legal_set,
            "reject_rate": reject_rate,
        },
        "verdicts": verdicts or ["OK"],
        "claims": {
            "conversational_gain": False,
            "learned_vs_control_superiority": False,
            "causal_safety": False,
        },
    }
    if calibration:
        report["calibration"] = {
            "expected_calibration_error": ece,
            "max_ece": gate_manifest["calibration"]["max_ece"],
            "ece_within_gate": None if ece is None else ece <= gate_manifest["calibration"]["max_ece"],
            "observation_likelihood_coverage_error_68": coverage_error(results, "68"),
            "observation_likelihood_coverage_error_95": coverage_error(results, "95"),
        }
    report["report_digest"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return report


def compare_python_reports(paths: Sequence[Path]) -> dict:
    """Cross-fingerprint equality: actions/order must match, numbers within tolerance."""

    reports = [json.loads(Path(path).read_text(encoding="utf-8")) for path in paths]
    if len(reports) < 2:
        raise ReplayError("cross-version comparison needs at least two reports")
    baseline = reports[0]
    tolerances = {"actual_action_log_loss": 1e-6, "actual_action_brier": 1e-6, "next_turn_valid_axis_weighted_mae": 1e-6}
    mismatches: list[str] = []
    for report in reports[1:]:
        minor = report["runtime_fingerprint"]["python_minor"]
        if report["action_distribution"] != baseline["action_distribution"]:
            mismatches.append(f"action distribution differs on python {minor}")
        if report.get("action_sequence_digest") != baseline.get("action_sequence_digest"):
            mismatches.append(f"per-turn action ORDER differs on python {minor}")
        for metric, tolerance in tolerances.items():
            left = baseline["primary_metrics"][metric]
            right = report["primary_metrics"][metric]
            if left is None or right is None:
                if left is not right:
                    mismatches.append(f"{metric} presence differs")
                continue
            if abs(left - right) > tolerance:
                mismatches.append(
                    f"{metric} differs by {abs(left - right):.3e} > tolerance {tolerance:.1e}"
                )
    result = {
        "report_kind": "v3_python_cross_version_v1",
        "python_minors": [report["runtime_fingerprint"]["python_minor"] for report in reports],
        "dataset_digests": sorted({report["dataset_digest"] for report in reports}),
        "tolerances": tolerances,
        "mismatches": mismatches,
        "passed": not mismatches,
    }
    if len({report["dataset_digest"] for report in reports}) != 1:
        result["passed"] = False
        result["mismatches"] = mismatches + ["reports do not share one dataset digest"]
    return result


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay an encoded v3 evaluation dataset.")
    parser.add_argument("--dataset", default=None)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--gate-manifest", default=None)
    parser.add_argument("--split", default="test", choices=[*v3_export.SPLITS, "all"])
    parser.add_argument("--calibration", action="store_true")
    parser.add_argument("--compare-python-reports", nargs="+", default=None)
    parser.add_argument("--report", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    if args.compare_python_reports:
        result = compare_python_reports([Path(p) for p in args.compare_python_reports])
        report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"passed": result["passed"], "mismatches": result["mismatches"]}, indent=2))
        return 0 if result["passed"] else 1

    if not args.dataset:
        raise ReplayError("--dataset is required unless comparing reports")
    dataset_path = Path(args.dataset)
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8")) if args.manifest else None
    if manifest is not None:
        dataset = v3_export.load_dataset_with_manifest(dataset_path, manifest)
    else:
        dataset = v3_export.read_dataset(dataset_path)

    gate_path = Path(args.gate_manifest) if args.gate_manifest else (
        _REPO_ROOT / "tests" / "fixtures" / "v3_gate_manifest_v1.json"
    )
    gate_manifest = json.loads(gate_path.read_text(encoding="utf-8"))
    gate_digest = v3_export.file_digest(gate_path)
    if manifest is not None and manifest["gate_manifest_digest"] != gate_digest:
        raise ReplayError(
            "dataset was frozen against a different gate manifest; refusing to score it"
        )

    split = None if args.split == "all" else args.split
    results, counters = replay_dataset(dataset, split=split)
    report = build_report(
        dataset_path=dataset_path,
        dataset=dataset,
        manifest=manifest,
        gate_manifest=gate_manifest,
        gate_manifest_digest=gate_digest,
        split=split,
        results=results,
        counters=counters,
        calibration=args.calibration,
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "split": report["split"],
                "turns": report["turn_count"],
                "scored": report["scored_turn_count"],
                "primary_metrics": report["primary_metrics"],
                "verdicts": report["verdicts"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
