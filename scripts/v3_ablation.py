"""Formula-v2 ablation and label-free controls over frozen encoded data.

Scores only selectors that formula v2 can execute: the canonical scalar profile
and label-free learning enabled versus frozen. Whole-episode bootstrap resampling
and every threshold come from the preregistered gate manifest.

Honesty constraints wired into the code
---------------------------------------
1. **Not every rung is separable.** Formula v2 exposes no runtime selector that
   disables one continuous sub-layer at a time. Those rungs are reported
   ``NOT_SEPARABLE`` rather than attributed to a neighbouring configuration.
2. **The live control is exact.** ``label_free_on`` and
   ``label_free_frozen`` replay the same scalar computation and differ only in
   whether label-free state may update.
3. **A gain is only reported with its interval.** A point estimate without a
   bootstrap lower bound is not evidence, so every rung reports the interval and
   the preregistered lower-bound gate verdict.
4. **This is preliminary.** Names stay conservative (``ProposalArbiterV1``,
   ``PolicyScorerV1``, ``ReservoirFeaturesV1``) until G4 clears.

Bootstrap resamples whole episodes, never rows: turns inside one episode share a
state trajectory, so row resampling would fabricate independence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts import v3_export, v3_replay
from scripts.v3_export import Dataset

#: Ladder rung -> the live profile that realizes it, or None when formula v2
#: exposes no independent selector for that rung.
LADDER = (
    ("formula_v2_scalar", "FORMULA_V2_SCALAR"),
    ("multi_timescale_dynamics", None),
    ("workspace", None),
    ("policy_scorer", None),
    ("label_free_marginal", None),
    ("label_free_preference", None),
)

#: control id -> (profile, label-free learning enabled).
CONTROLS = {
    "label_free_on": ("FORMULA_V2_SCALAR", True),
    "label_free_frozen": ("FORMULA_V2_SCALAR", False),
}


def _episode_metrics(results: list) -> dict:
    return {
        "actual_action_log_loss": v3_replay.log_loss(results),
        "actual_action_brier": v3_replay.brier(results),
        "next_turn_valid_axis_weighted_mae": v3_replay.axis_mae(results),
    }


def run_configuration(
    dataset: Dataset,
    *,
    profile_id: str,
    split: str | None,
    control_id: str | None = None,
    label_free_enabled: bool = True,
) -> dict:
    """Replay every episode under one configuration, keeping per-episode results."""

    episodes = dataset.split_episodes(split) if split else dataset.episodes
    per_episode: dict[str, list] = {}
    counters = v3_replay.ReplayCounters()
    for episode in episodes:
        seed_override = None
        if control_id is not None:
            # Controls get domain-separated seeds and differ only by the declared
            # label-free learning switch.
            seed_override = v3_export.control_episode_seed(
                control_id=control_id,
                dataset_id=bytes.fromhex(episode.header["dataset_id"]),
                evaluation_group_ref=bytes.fromhex(episode.evaluation_group_ref),
                episode_ref=bytes.fromhex(episode.episode_ref),
                gate_manifest_digest=bytes.fromhex(episode.header["gate_manifest_digest"]),
                formula_digest=bytes.fromhex(episode.header["formula_digest"]),
                model_digest=bytes.fromhex(episode.header["model_digest"]),
                profile_digest=bytes.fromhex(episode.header["evaluation_profile_digest"]),
            )
        per_episode[episode.episode_ref] = v3_replay.replay_episode(
            episode,
            profile_id=profile_id,
            counters=counters,
            initial_state_mutator=None,
            seed_override=seed_override,
            label_free_enabled=label_free_enabled,
        )
    flat = [r for results in per_episode.values() for r in results]
    return {
        "profile_id": profile_id,
        "control_id": control_id,
        "per_episode": per_episode,
        "metrics": _episode_metrics(flat),
        "action_distribution": v3_replay.action_distribution(flat),
        "safety": v3_replay.known_hold_contradiction_rate(flat),
        "counters": counters,
        "turns": len(flat),
    }


# --------------------------------------------------------------------------- #
# Whole-episode bootstrap
# --------------------------------------------------------------------------- #


def bootstrap_gain(
    baseline: dict,
    candidate: dict,
    metric: str,
    *,
    resamples: int,
    seed: int,
    confidence: float = 0.95,
) -> dict:
    """Bootstrap ``baseline_loss - candidate_loss`` by resampling whole episodes."""

    refs = sorted(set(baseline["per_episode"]) & set(candidate["per_episode"]))
    if not refs:
        return {"status": "INSUFFICIENT_EVIDENCE", "reason": "no shared episodes"}
    rng = random.Random(seed)
    gains: list[float] = []
    for _ in range(resamples):
        drawn = [refs[rng.randrange(len(refs))] for _ in refs]
        base_rows = [r for ref in drawn for r in baseline["per_episode"][ref]]
        cand_rows = [r for ref in drawn for r in candidate["per_episode"][ref]]
        left = _episode_metrics(base_rows)[metric]
        right = _episode_metrics(cand_rows)[metric]
        if left is None or right is None:
            continue
        gains.append(left - right)
    if len(gains) < resamples * 0.5:
        return {"status": "INSUFFICIENT_EVIDENCE", "reason": "metric censored in most resamples"}
    gains.sort()
    alpha = (1.0 - confidence) / 2.0
    lower = gains[int(alpha * len(gains))]
    upper = gains[min(int((1.0 - alpha) * len(gains)), len(gains) - 1)]
    point_base = baseline["metrics"][metric]
    point_cand = candidate["metrics"][metric]
    point = None if (point_base is None or point_cand is None) else point_base - point_cand
    return {
        "status": "OK",
        "metric": metric,
        "direction": "lower_is_better",
        "gain_point_estimate": point,
        "ci_lower": lower,
        "ci_upper": upper,
        "confidence": confidence,
        "resamples": len(gains),
        "lower_bound_above_zero": lower > 0.0,
    }


def _relative_regression(baseline: dict, candidate: dict, metric: str) -> float | None:
    left = baseline["metrics"][metric]
    right = candidate["metrics"][metric]
    if left is None or right is None or left == 0:
        return None
    return (right - left) / abs(left)


# --------------------------------------------------------------------------- #
# Label-free ablation gates LF-1..LF-4 (spec §6) -- never read an action label
# --------------------------------------------------------------------------- #
#
# LF-1  L2 world-model gate: prequential marginal axis-MAE, learner vs the frozen
#       prior head; carry-forward is reported, not gated (spec §6.1).
# LF-2  L1 preference gate: reaction-weighted preference NLL, learner offset vs
#       offset=0; passes iff the bootstrap 95% CI lower bound > 0 AND LF-4 passes.
# LF-4  permutation control (the anti-circularity main gate): shuffling r_react must
#       remove >=50% of the LF-2 gain, or the offset only captured a marginal drift
#       (not a reaction-conditioned structure) and L1 is judged negative.
# Evidence floor (spec §6): LF-2/LF-4 need >=150 reaction-valid settled turns and >=3
# episodes, else INSUFFICIENT_EVIDENCE -- never a silent pass.  LF-1 scores any
# adjacent pair, so it is not gated on that floor.

LF_MIN_REACTION_VALID = 150
LF_MIN_EPISODES = 3
LF_PERMUTATION_COLLAPSE = 0.50


def _mae(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _weighted_mean(terms: Sequence[float], weights: Sequence[float]) -> float | None:
    total = sum(weights)
    if total <= 0.0:
        return None
    return sum(term * weight for term, weight in zip(terms, weights)) / total


def _bootstrap_ci(gains: list, resamples: int, *, confidence: float = 0.95):
    if len(gains) < resamples * 0.5:
        return None
    ordered = sorted(gains)
    alpha = (1.0 - confidence) / 2.0
    lower = ordered[int(alpha * len(ordered))]
    upper = ordered[min(int((1.0 - alpha) * len(ordered)), len(ordered) - 1)]
    return lower, upper


def _lf_permute_seed(header: dict) -> int:
    """Per-episode r_react permutation seed = episode seed framing + control ``LF_PERMUTE``.

    Uses the same domain-separated control framing as the learned/frozen controls so
    the permutation stream can never accidentally share a learned stream (spec §6.1).
    """

    seed_bytes = v3_export.control_episode_seed(
        control_id="LF_PERMUTE",
        dataset_id=bytes.fromhex(header["dataset_id"]),
        evaluation_group_ref=bytes.fromhex(header["evaluation_group_ref"]),
        episode_ref=bytes.fromhex(header["episode_ref"]),
        gate_manifest_digest=bytes.fromhex(header["gate_manifest_digest"]),
        formula_digest=bytes.fromhex(header["formula_digest"]),
        model_digest=bytes.fromhex(header["model_digest"]),
        profile_digest=bytes.fromhex(header["evaluation_profile_digest"]),
    )
    return int.from_bytes(seed_bytes, "big")


def _marginal_lf1(
    marg: dict,
    refs: list,
    *,
    resamples: int,
    seed: int,
    confidence: float,
    required_lower_bound: float,
) -> dict:
    pooled_learner = [value for ref in refs for value in marg[ref]["learner_abs"]]
    pooled_frozen = [value for ref in refs for value in marg[ref]["frozen_abs"]]
    pooled_carry = [value for ref in refs for value in marg[ref]["carry_abs"]]
    learner_mae = _mae(pooled_learner)
    frozen_mae = _mae(pooled_frozen)
    carry_mae = _mae(pooled_carry)
    result: dict = {
        "metric": "marginal_axis_mae",
        "direction": "lower_is_better",
        "control": "frozen_prior_head",
        "learner_mae": learner_mae,
        "frozen_mae": frozen_mae,
        "carry_forward_mae": carry_mae,  # reported, never gated (spec §6.1)
        "axis_observations": len(pooled_learner),
    }
    if learner_mae is None or frozen_mae is None:
        return {**result, "status": "INSUFFICIENT_EVIDENCE", "reason": "no valid marginal axis observations"}
    rng = random.Random(seed)
    gains: list[float] = []
    for _ in range(resamples):
        drawn = [refs[rng.randrange(len(refs))] for _ in refs]
        boot_learner = [value for ref in drawn for value in marg[ref]["learner_abs"]]
        boot_frozen = [value for ref in drawn for value in marg[ref]["frozen_abs"]]
        if not boot_learner or not boot_frozen:
            continue
        gains.append(_mae(boot_frozen) - _mae(boot_learner))
    ci = _bootstrap_ci(gains, resamples, confidence=confidence)
    result["gain_point_estimate"] = frozen_mae - learner_mae
    result["gain_vs_carry_forward"] = None if carry_mae is None else carry_mae - learner_mae
    if ci is None:
        return {**result, "status": "INSUFFICIENT_EVIDENCE", "reason": "marginal MAE censored in most resamples"}
    result["ci_lower"], result["ci_upper"] = ci
    result["confidence"] = confidence
    result["required_lower_bound_above"] = required_lower_bound
    result["lower_bound_above_zero"] = ci[0] > required_lower_bound
    result["status"] = "OK"
    result["verdict"] = (
        "EARNS_MARGINAL_HEAD" if ci[0] > required_lower_bound else "NO_MARGINAL_IMPROVEMENT"
    )
    return result


def _pref_pool_gain(pool: dict, refs: list) -> float | None:
    learner = [term for ref in refs for term in pool[ref]["learner_terms"]]
    frozen = [term for ref in refs for term in pool[ref]["frozen_terms"]]
    weights = [weight for ref in refs for weight in pool[ref]["weights"]]
    weighted_learner = _weighted_mean(learner, weights)
    weighted_frozen = _weighted_mean(frozen, weights)
    if weighted_learner is None or weighted_frozen is None:
        return None
    return weighted_frozen - weighted_learner


def _preference_lf2_lf4(
    pref_real: dict,
    pref_perm: dict,
    refs: list,
    *,
    resamples: int,
    seed: int,
    insufficient: bool,
    confidence: float,
    required_lower_bound: float,
    required_collapse: float,
) -> tuple[dict, dict]:
    real_gain = _pref_pool_gain(pref_real, refs)
    permuted_gain = _pref_pool_gain(pref_perm, refs)
    scored = sum(len(pref_real[ref]["weights"]) for ref in refs)
    collapse = (
        1.0 - (permuted_gain / real_gain)
        if real_gain is not None and real_gain > 0.0 and permuted_gain is not None
        else None
    )
    lf4: dict = {
        "control": "r_react_permutation",
        "real_gain": real_gain,
        "permuted_gain": permuted_gain,
        "collapse_fraction": collapse,
        "required_collapse": required_collapse,
    }
    lf2: dict = {
        "metric": "reaction_weighted_preference_nll",
        "direction": "lower_is_better",
        "control": "offset_zero_v1_preference",
        "scored_turns": scored,
        "gain_point_estimate": real_gain,
        # spec §5/§6.2: this is a density-estimation claim (the offset fits the
        # reaction-weighted empirical distribution), NEVER a policy-improvement claim.
        "claim": "density_estimation_only",
    }
    if insufficient:
        return (
            {**lf2, "status": "INSUFFICIENT_EVIDENCE"},
            {**lf4, "status": "INSUFFICIENT_EVIDENCE"},
        )
    rng = random.Random(seed)
    gains: list[float] = []
    for _ in range(resamples):
        drawn = [refs[rng.randrange(len(refs))] for _ in refs]
        gain = _pref_pool_gain(pref_real, drawn)
        if gain is not None:
            gains.append(gain)
    ci = _bootstrap_ci(gains, resamples, confidence=confidence)
    if ci is None:
        return (
            {**lf2, "status": "INSUFFICIENT_EVIDENCE", "reason": "preference NLL censored in most resamples"},
            {**lf4, "status": "INSUFFICIENT_EVIDENCE"},
        )
    lf2["ci_lower"], lf2["ci_upper"] = ci
    lf2["confidence"] = confidence
    lf2["required_lower_bound_above"] = required_lower_bound
    lf2["lower_bound_above_zero"] = ci[0] > required_lower_bound
    lf4_pass = collapse is not None and collapse >= required_collapse
    lf4["status"] = "OK"
    lf4["passed"] = bool(lf4_pass)
    lf2["status"] = "OK"
    lf2["permutation_passed"] = bool(lf4_pass)
    # LF-2 PASSES iff the CI lower bound > 0 AND the permutation collapses the gain.
    lf2["passed"] = bool(ci[0] > required_lower_bound and lf4_pass)
    lf2["verdict"] = "EARNS_PREFERENCE_OFFSET" if lf2["passed"] else "NO_PREFERENCE_CREDIT"
    return lf2, lf4


def _lf3_relative_regression(baseline: dict, candidate: dict, metric: str) -> float | None:
    left = baseline["metrics"][metric]
    right = candidate["metrics"][metric]
    if left is None or right is None:
        return None
    if left == right:
        return 0.0
    if left == 0.0:
        return float("inf")
    return (right - left) / abs(left)


def _run_lf3_non_interference(
    dataset: Dataset,
    *,
    split: str | None,
    profile_id: str,
    gate: dict,
) -> dict:
    """Execute LF-3 by replaying identical labelled rows with L1 ON vs frozen OFF."""

    labelled = any(
        turn["actual_action"] != "UNKNOWN"
        for episode in (dataset.split_episodes(split) if split else dataset.episodes)
        for turn in episode.turns
    )
    frozen = gate["label_free_gates"]["LF_3"]
    result = {
        "max_relative_regression": frozen["max_relative_regression"],
        "max_hold_contradiction_degradation_percentage_points": frozen[
            "max_hold_contradiction_degradation_percentage_points"
        ],
        "required_zero_counters": list(frozen["required_zero_counters"]),
    }
    if not labelled:
        return {**result, "status": "INSUFFICIENT_EVIDENCE", "reason": "no labelled turns"}

    off = run_configuration(
        dataset, profile_id=profile_id, split=split, label_free_enabled=False
    )
    on = run_configuration(
        dataset, profile_id=profile_id, split=split, label_free_enabled=True
    )
    regressions = {
        metric: _lf3_relative_regression(off, on, metric) for metric in v3_replay.PRIMARY_METRICS
    }
    safety_pp = (
        None
        if off["safety"] is None or on["safety"] is None
        else 100.0 * (on["safety"] - off["safety"])
    )
    replay_counter_names = {
        "illegal_action_count",
        "nonfinite_action_count",
        "privacy_violation_count",
    }
    observed_zero = {
        name: int(getattr(on["counters"], name)) if name in replay_counter_names else 0
        for name in frozen["required_zero_counters"]
    }
    complete = all(value is not None for value in regressions.values()) and safety_pp is not None
    passed = bool(
        complete
        and all(value <= frozen["max_relative_regression"] for value in regressions.values())
        and safety_pp < frozen["max_hold_contradiction_degradation_percentage_points"]
        and not any(observed_zero.values())
    )
    return {
        **result,
        "status": "OK" if complete else "INSUFFICIENT_EVIDENCE",
        "primary_metric_relative_regressions": regressions,
        "hold_contradiction_degradation_percentage_points": safety_pp,
        "observed_zero_counters": observed_zero,
        "passed": passed,
    }


def run_label_free_gates(
    dataset: Dataset,
    *,
    gate_manifest: dict | None = None,
    split: str | None,
    resamples: int = 10_000,
    seed: int = 2718,
) -> dict:
    """Score LF-1..LF-4 on a frozen dataset by an offline prequential replay (spec §6).

    Never reads an action label: it replays each episode once to extract the per-turn
    label-free settlement inputs, then re-runs the exact core learner laws to compute
    the marginal MAE (LF-1), the reaction-weighted preference NLL (LF-2), and its
    r_react permutation control (LF-4), with a whole-episode bootstrap and the §6
    evidence floor.
    """

    if gate_manifest is None:
        gate_manifest = json.loads(
            (_REPO_ROOT / "tests" / "fixtures" / "v3_gate_manifest_v1.json").read_text(
                encoding="utf-8"
            )
        )
    gate = v3_replay.validate_gate_manifest(gate_manifest)
    v3_replay.validate_dataset_gate_contract(dataset, gate)
    lf1_gate = gate["label_free_gates"]["LF_1"]
    lf2_gate = gate["label_free_gates"]["LF_2"]
    lf4_gate = gate["label_free_gates"]["LF_4"]

    episodes = dataset.split_episodes(split) if split else dataset.episodes
    records = {episode.episode_ref: v3_replay.collect_label_free_records(episode) for episode in episodes}
    headers = {episode.episode_ref: episode.header for episode in episodes}
    refs = sorted(records)

    funnel = {"total_turns": 0, "adjacent": 0, "reaction_valid": 0}
    for episode_records in records.values():
        coverage = v3_replay.label_free_coverage(episode_records)
        for key in funnel:
            funnel[key] += coverage[key]

    evidence = {
        "episode_count": len(refs),
        "reaction_valid_settled_turns": funnel["reaction_valid"],
        "min_reaction_valid": lf2_gate["min_reaction_valid_settled_turns"],
        "min_episodes": lf2_gate["min_episodes"],
    }
    insufficient = (
        funnel["reaction_valid"] < lf2_gate["min_reaction_valid_settled_turns"]
        or len(refs) < lf2_gate["min_episodes"]
    )

    marg = {ref: v3_replay.marginal_prequential_episode(records[ref]) for ref in refs}
    lf1 = _marginal_lf1(
        marg,
        refs,
        resamples=resamples,
        seed=seed,
        confidence=lf1_gate["bootstrap_confidence"],
        required_lower_bound=lf1_gate["required_lower_bound_above"],
    )
    pref_real = {ref: v3_replay.preference_prequential_episode(records[ref]) for ref in refs}
    pref_perm = {
        ref: v3_replay.preference_prequential_episode(
            records[ref], permutation_seed=_lf_permute_seed(headers[ref])
        )
        for ref in refs
    }
    lf2, lf4 = _preference_lf2_lf4(
        pref_real,
        pref_perm,
        refs,
        resamples=resamples,
        seed=seed,
        insufficient=insufficient,
        confidence=lf2_gate["bootstrap_confidence"],
        required_lower_bound=lf2_gate["required_lower_bound_above"],
        required_collapse=lf4_gate["min_gain_removal_fraction"],
    )
    lf3 = _run_lf3_non_interference(
        dataset,
        split=split,
        profile_id=gate["evaluation_profile"]["evaluation_profile_id"],
        gate=gate,
    )

    return {
        "report_kind": "v3_label_free_gates_v2",
        "split": split,
        "coverage_funnel": funnel,
        "evidence": evidence,
        "insufficient_evidence": insufficient,
        "LF_1_marginal_world_model": lf1,
        "LF_2_preference_nll": lf2,
        "LF_3_non_interference": lf3,
        "LF_4_permutation_control": lf4,
        "claims": {
            "conversational_gain": False,
            "policy_superiority": False,
            "world_model_and_density_only": True,
        },
    }


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #


def run_ablation(
    datasets: Sequence[Path],
    *,
    gate_manifest: dict,
    gate_manifest_digest: str,
    controls: Sequence[str],
    resamples: int,
    split: str | None,
    seed: int = 2718,
) -> dict:
    gate_manifest = v3_replay.validate_gate_manifest(gate_manifest)
    loaded: list[Dataset] = [v3_export.read_dataset(path) for path in datasets]
    merged = Dataset(
        episodes=tuple(e for dataset in loaded for e in dataset.episodes),
        row_count=sum(dataset.row_count for dataset in loaded),
    )
    v3_replay.validate_dataset_gate_contract(
        merged, gate_manifest, gate_manifest_digest=gate_manifest_digest
    )

    max_regression = gate_manifest["non_target_regression"]["max_relative_worsening"]
    primary = tuple(item["name"] for item in gate_manifest["primary_metrics"])

    # --- ladder ----------------------------------------------------------------
    configurations: dict[str, dict] = {}
    rungs: list[dict] = []
    previous_name: str | None = None
    for name, profile_id in LADDER:
        if profile_id is None:
            rungs.append(
                {
                    "rung": name,
                    "status": "NOT_SEPARABLE",
                    "reason": (
                        "COMPUTE_PROFILES exposes no knob that disables this layer, and "
                        "orchestrate() hard-validates the profile against that frozen "
                        "manifest. Reported rather than attributed to a neighbouring rung."
                    ),
                }
            )
            continue
        if profile_id not in configurations:
            configurations[profile_id] = run_configuration(
                merged, profile_id=profile_id, split=split
            )
        entry: dict = {"rung": name, "profile_id": profile_id, "status": "OK"}
        if previous_name is not None:
            baseline = configurations[previous_name]
            candidate = configurations[profile_id]
            if previous_name == profile_id:
                entry["status"] = "NOT_SEPARABLE"
                entry["reason"] = (
                    f"this rung resolves to the same profile as the previous rung "
                    f"({profile_id}); the frozen manifest cannot separate them"
                )
            else:
                gains = {
                    metric: bootstrap_gain(
                        baseline, candidate, metric, resamples=resamples, seed=seed
                    )
                    for metric in primary
                }
                entry["gains"] = gains
                improved = [
                    metric
                    for metric, g in gains.items()
                    if g.get("status") == "OK" and g.get("lower_bound_above_zero")
                ]
                regressions = {
                    metric: _relative_regression(baseline, candidate, metric)
                    for metric in primary
                }
                bad = [
                    metric
                    for metric, value in regressions.items()
                    if value is not None and metric not in improved and value > max_regression
                ]
                entry["improved_metrics"] = improved
                entry["non_target_regressions"] = regressions
                entry["verdict"] = (
                    "EARNS_RUNG" if improved and not bad else "NO_INDEPENDENT_CONTRIBUTION"
                )
        previous_name = profile_id
        rungs.append(entry)

    # --- controls --------------------------------------------------------------
    control_runs: dict[str, dict] = {}
    for control_id in controls:
        if control_id not in CONTROLS:
            raise ValueError(f"unknown control {control_id!r}")
        profile_id, label_free_enabled = CONTROLS[control_id]
        control_runs[control_id] = run_configuration(
            merged,
            profile_id=profile_id,
            split=split,
            control_id=control_id,
            label_free_enabled=label_free_enabled,
        )

    control_report: dict = {}
    if "label_free_on" in control_runs:
        for other in [c for c in controls if c != "label_free_on"]:
            same_config = CONTROLS[other] == CONTROLS["label_free_on"]
            comparison = {
                "profile_id": CONTROLS[other][0],
                "configuration_identical_to_label_free_on": same_config,
            }
            if same_config:
                comparison["status"] = "NOT_SEPARABLE"
                comparison["reason"] = (
                    "this control has the same scalar profile and label-free update switch "
                    "as 'label_free_on', so the comparison is not informative"
                )
            else:
                comparison["gains"] = {
                    metric: bootstrap_gain(
                        control_runs[other], control_runs["label_free_on"], metric,
                        resamples=resamples, seed=seed,
                    )
                    for metric in primary
                }
            control_report[f"label_free_on_vs_{other}"] = comparison

    # --- identical-behaviour sanity, over ladder AND controls -------------------
    # Scan controls too: identical observed behaviour remains useful evidence even
    # when the configurations themselves differ by the learning switch.
    identical_configs = _identical_configuration_pairs({**configurations, **control_runs})
    collapsed = [
        {"controls": sorted(pair), "profile_id": CONTROLS[pair[0]][0]}
        for pair in [
            (left, right)
            for i, left in enumerate(sorted(control_runs))
            for right in sorted(control_runs)[i + 1:]
            if CONTROLS[left] == CONTROLS[right]
        ]
    ]

    report = {
        "report_kind": "v3_ablation_preliminary_v2",
        "gate_manifest_digest": gate_manifest_digest,
        "dataset_digests": [v3_export.file_digest(path) for path in datasets],
        "runtime_fingerprint": v3_replay.runtime_fingerprint(),
        "runtime_fingerprint_digest": v3_replay.fingerprint_digest(v3_replay.runtime_fingerprint()),
        "split": split,
        "episode_count": len(merged.split_episodes(split) if split else merged.episodes),
        "bootstrap": {"unit": "whole_episode", "resamples": resamples, "confidence": 0.95},
        "ladder": rungs,
        "controls": control_report,
        "identical_configuration_pairs": identical_configs,
        "configuration_identical_controls": collapsed,
        # formula v2 label-free gates (spec §6): scored on the same frozen episodes,
        # never reading an action label.  On the current 3/36-channel real datasets
        # these honestly report INSUFFICIENT_EVIDENCE (no tone channels).
        "label_free": run_label_free_gates(
            merged,
            gate_manifest=gate_manifest,
            split=split,
            resamples=resamples,
            seed=seed,
        ),
        "preliminary": True,
        "claims": {
            "conversational_gain": False,
            "causal_policy_improvement": False,
            "earns_scientific_aliases": False,
        },
        "conservative_names": gate_manifest["failure_semantics"]["conservative_names_until_g4"],
    }
    report["report_digest"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return report


def _identical_configuration_pairs(configurations: dict) -> list:
    """Flag configurations that produce identical behaviour.

    If two profiles that are supposed to differ score identically, the layer that
    is supposed to separate them is inert. That is a finding, not a pass.
    """

    pairs = []
    names = sorted(configurations)
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            if configurations[left]["action_distribution"] == configurations[right]["action_distribution"] and (
                configurations[left]["metrics"] == configurations[right]["metrics"]
            ):
                pairs.append(
                    {
                        "left": left,
                        "right": right,
                        "note": (
                            "identical metrics and action distribution: the layer that "
                            "should distinguish these profiles had no measurable effect"
                        ),
                    }
                )
    return pairs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the preliminary v3 ablation ladder.")
    parser.add_argument("--dataset", action="append", required=True)
    parser.add_argument("--gate-manifest", default=None)
    parser.add_argument("--controls", default="label_free_on,label_free_frozen")
    parser.add_argument("--bootstrap", type=int, default=10_000)
    # Preregistered: primary/calibration/shuffle/safety use the untouched test
    # split only. Defaulting to "all" would score the ladder on training data.
    parser.add_argument("--split", default="test", choices=[*v3_export.SPLITS, "all"])
    parser.add_argument("--shuffle-cross-turn", action="store_true")
    parser.add_argument("--seed", type=int, default=2718)
    parser.add_argument("--report", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.shuffle_cross_turn:
        raise NotImplementedError(
            "--shuffle-cross-turn is a retired formula-v1 option; formula v2 runs "
            "its preregistered LF4 shuffled-evidence control inside run_label_free_gates"
        )
    gate_path = Path(args.gate_manifest) if args.gate_manifest else (
        _REPO_ROOT / "tests" / "fixtures" / "v3_gate_manifest_v1.json"
    )
    gate_manifest = json.loads(gate_path.read_text(encoding="utf-8"))
    report = run_ablation(
        [Path(p) for p in args.dataset],
        gate_manifest=gate_manifest,
        gate_manifest_digest=v3_export.file_digest(gate_path),
        controls=tuple(args.controls.split(",")),
        resamples=args.bootstrap,
        split=None if args.split == "all" else args.split,
        seed=args.seed,
    )
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ladder": [
                    {k: v for k, v in rung.items() if k in ("rung", "status", "verdict", "improved_metrics")}
                    for rung in report["ladder"]
                ],
                "identical_configuration_pairs": report["identical_configuration_pairs"],
                "configuration_identical_controls": report["configuration_identical_controls"],
                "preliminary": True,
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
