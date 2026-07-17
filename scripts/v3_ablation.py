"""Preliminary ablation ladder and controls over frozen encoded data (design 17.2).

Scores the ablation rungs the *frozen profile manifest actually supports*, plus
the learned/frozen/random/zero-LR controls, with whole-episode bootstrap
resampling and preregistered gates read from the gate manifest.

Honesty constraints wired into the code
---------------------------------------
1. **Not every rung is separable.** Design 17.2's ladder is
   ``deterministic -> +dynamics -> +workspace -> +policy -> +SNN -> +STDP``, but
   ``ComputeProfile`` only exposes ``snn_enabled``/``ticks``/``stdp_enabled``/
   ``reuse_last_summary`` and ``orchestrate`` hard-validates against
   ``COMPUTE_PROFILES``. There is no knob that disables the workspace or the
   policy scorer, so those rungs are reported ``NOT_SEPARABLE`` rather than
   silently attributed to a neighbouring rung.
2. **``frozen`` and ``zero-lr`` are configuration-identical** under the frozen v1
   ladder: both are ``FULL_24_NO_STDP``. The learned-vs-frozen and
   STDP-vs-zero-LR comparisons are therefore the *same* comparison, and saying so
   is the whole point of a control.
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
from dataclasses import replace
from pathlib import Path
from typing import Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts import v3_export, v3_replay
from scripts.v3_export import Dataset
from sylanne_alpha.v3core import formula_v1 as formula
from sylanne_alpha.v3core.orchestrator import build_initial_snn_state

#: Ladder rung -> the profile that realizes it, or None when the frozen manifest
#: exposes no knob for that rung.
LADDER = (
    ("deterministic_baseline", "DETERMINISTIC_CONTINUOUS_ONLY"),
    ("multi_timescale_dynamics", "DETERMINISTIC_CONTINUOUS_ONLY"),
    ("workspace", None),
    ("policy_scorer", None),
    ("snn", "FULL_24_NO_STDP"),
    ("stdp", "FULL_24_STDP"),
)

#: control id -> (profile, randomize_initial_reservoir)
CONTROLS = {
    "learned": ("FULL_24_STDP", False),
    "frozen": ("FULL_24_NO_STDP", False),
    "random": ("FULL_24_NO_STDP", True),
    "zero-lr": ("FULL_24_NO_STDP", False),
}


def _random_reservoir_mutator(seed: bytes):
    """Randomize the initial plastic weights, seeded by the control's own seed."""

    def mutate(state):
        rng = random.Random(int.from_bytes(seed, "big"))
        low, high = formula.SNN_EXCITATORY_WEIGHT_BOUNDS
        snn = state.snn if state.snn is not None else build_initial_snn_state()
        weights = tuple(rng.uniform(low, high) for _ in snn.plastic_weights)
        return replace(state, snn=replace(snn, plastic_weights=weights))

    return mutate


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
    randomize_reservoir: bool = False,
) -> dict:
    """Replay every episode under one configuration, keeping per-episode results."""

    episodes = dataset.split_episodes(split) if split else dataset.episodes
    per_episode: dict[str, list] = {}
    counters = v3_replay.ReplayCounters()
    for episode in episodes:
        seed_override = None
        mutator = None
        if control_id is not None:
            # A control gets its own domain-separated seed so learned/frozen/random/
            # zero-LR can never share an accidental random stream.
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
            if randomize_reservoir:
                mutator = _random_reservoir_mutator(seed_override)
        per_episode[episode.episode_ref] = v3_replay.replay_episode(
            episode,
            profile_id=profile_id,
            counters=counters,
            initial_state_mutator=mutator,
            seed_override=seed_override,
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
    loaded: list[Dataset] = [v3_export.read_dataset(path) for path in datasets]
    merged = Dataset(
        episodes=tuple(e for dataset in loaded for e in dataset.episodes),
        row_count=sum(dataset.row_count for dataset in loaded),
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
        profile_id, randomize = CONTROLS[control_id]
        control_runs[control_id] = run_configuration(
            merged,
            profile_id=profile_id,
            split=split,
            control_id=control_id,
            randomize_reservoir=randomize,
        )

    control_report: dict = {}
    if "learned" in control_runs:
        for other in [c for c in controls if c != "learned"]:
            same_config = CONTROLS[other] == CONTROLS["learned"]
            comparison = {
                "profile_id": CONTROLS[other][0],
                "configuration_identical_to_learned": same_config,
            }
            if same_config:
                comparison["status"] = "NOT_SEPARABLE"
                comparison["reason"] = (
                    "this control resolves to the same ComputeProfile as 'learned' under "
                    "the frozen v1 ladder, so the comparison is not informative"
                )
            else:
                comparison["gains"] = {
                    metric: bootstrap_gain(
                        control_runs[other], control_runs["learned"], metric,
                        resamples=resamples, seed=seed,
                    )
                    for metric in primary
                }
            control_report[f"learned_vs_{other}"] = comparison

    # --- identical-behaviour sanity, over ladder AND controls -------------------
    # The controls are exactly where the docstring admits the collapse lives
    # (frozen and zero-lr are the same profile), so they must be scanned too.
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
        "report_kind": "v3_ablation_preliminary_v1",
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
    parser.add_argument("--controls", default="learned,frozen,random,zero-lr")
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
        # The gate manifest preregisters a >=50% persistent-SNN-gain-removal
        # threshold for this test. Accepting the flag without implementing it would
        # make that a declared-but-unenforced gate.
        raise NotImplementedError(
            "--shuffle-cross-turn is NOT IMPLEMENTED (cross-turn event-order shuffle, "
            "spec 17.3 / plan Task 17). Refusing rather than reporting an unshuffled "
            "run as if the falsification test had been applied."
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
