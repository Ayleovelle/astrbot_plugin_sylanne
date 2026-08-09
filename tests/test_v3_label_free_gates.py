"""formula-v2 Slice D: the label-free ablation gates LF-1..LF-4 (spec §6).

These gates are the falsifiable core of the label-free channel and they NEVER read
an action label.  They are exercised here exclusively on synthetic corpora built in
this file (no real user history is ever touched):

* a PLANTED corpus with a real reaction-conditioned structure -- high-valence turns
  (a high ``r_react``) co-occur with a high next-turn outcome on the novelty/
  uncertainty axes, low-valence turns with a low one -- so L1 must recover a positive
  preference offset, LF-2 must pass, and its r_react permutation control (LF-4) must
  collapse the gain (the anti-circularity gate);
* a NULL corpus with the same volume but no reaction/outcome pairing, where LF-2 must
  honestly NOT pass; and
* a THIN corpus below the §6 evidence floor, where both gates must report
  ``INSUFFICIENT_EVIDENCE`` rather than silently passing.

The metric machinery re-runs the EXACT core learner laws (``ekf_transition_update``
for L2, ``_update_pref_offset`` for L1) over inputs extracted from one online replay,
so the learner and its controls are scored on identical inputs.
"""

from __future__ import annotations

import ast
import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from scripts import v3_ablation, v3_export, v3_replay
from sylanne_alpha.v3core.features import decision_state
from sylanne_alpha.v3core.learning.label_free import _update_pref_offset


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _gate_manifest() -> dict:
    return json.loads((FIXTURE_DIR / "v3_gate_manifest_v1.json").read_text(encoding="utf-8"))

# The reaction is driven by ENGAGEMENT (channel 26), which feeds r_react but NO
# outcome axis (project_outcome never reads channel 26), so a planted engagement<->
# outcome correlation is a genuinely NON-circular reaction-conditioned signal -- it
# deliberately avoids the valence-axis circularity spec §6.2 warns about (channel 25
# feeds both r_react and outcome axis 0).  The outcome is driven by SURPRISE (channel
# 4), which pins the novelty (axis 5) and uncertainty (axis 4) outcomes to +/-0.9.
_HIGH_ENGAGEMENT = 1.3  # -> u26 = 1.0 -> r_react ~ +1
_LOW_ENGAGEMENT = 0.0   # -> u26 = 0.0 -> r_react ~ -1
_HIGH_SURPRISE = 0.95   # -> y'_4 = y'_5 = +0.9
_LOW_SURPRISE = 0.05    # -> y'_4 = y'_5 = -0.9
_ENGAGEMENT_CHANNEL = 26
_SURPRISE_CHANNEL = 4
_LENGTH_CHANNEL = 18


def _turn(local_sequence: int, *, channels: dict, same_sender: bool | None = True):
    values = [0.0] * v3_export.OBSERVATION_DIM
    mask = 0
    for channel, value in channels.items():
        values[channel] = float(value)
        mask |= 1 << channel
    return v3_export.SourceTurn(
        values=tuple(values),
        valid_mask=mask,
        context="ADDRESSED",  # inbound + reaction-eligible origin
        actual_action="UNKNOWN",  # label-free: no action receipt, so only path B settles
        writer_epoch=1,
        local_sequence=local_sequence,
        dropped_gap_count=0,
        reaction_same_sender=same_sender,
        source_components=(f"lf-{local_sequence}",),
    )


def _planted_turns(count: int):
    turns = []
    for index in range(count):
        if index % 2 == 0:  # Type A: high reaction, high outcome
            channels = {_ENGAGEMENT_CHANNEL: _HIGH_ENGAGEMENT, _SURPRISE_CHANNEL: _HIGH_SURPRISE}
        else:  # Type B: opposite reaction, opposite outcome (balanced -> marginal mean ~0)
            channels = {_ENGAGEMENT_CHANNEL: _LOW_ENGAGEMENT, _SURPRISE_CHANNEL: _LOW_SURPRISE}
        turns.append(_turn(index + 1, channels=channels))
    return tuple(turns)


def _null_turns(count: int, seed: int):
    import random

    rng = random.Random(seed)
    turns = []
    for index in range(count):
        # Engagement (r_react) and surprise (outcome) vary INDEPENDENTLY, so r_react
        # carries no information about the next-turn outcome: the offset can only fit
        # a marginal drift, which the permutation control does not remove.
        turns.append(
            _turn(
                index + 1,
                channels={
                    _ENGAGEMENT_CHANNEL: rng.uniform(0.0, _HIGH_ENGAGEMENT),
                    _SURPRISE_CHANNEL: rng.uniform(0.0, 1.0),
                },
            )
        )
    return tuple(turns)


def _no_tone_turns(count: int):
    """The current real-export shape: only text.length (channel 18), no tone channel.

    With no valence/engagement cue every reaction is NO_TONE_EVIDENCE, so no reaction
    is ever valid -- the honest ``INSUFFICIENT_EVIDENCE`` case the acceptance item
    calls for on the existing 3/36-channel real datasets.
    """

    return tuple(
        _turn(index + 1, channels={_LENGTH_CHANNEL: float(20 + index)}) for index in range(count)
    )


def _dataset(episodes, tmp_path: Path, name: str):
    link_key = v3_export.synthetic_link_key(4242)
    rows = v3_export._build_records(
        episodes,
        link_key=link_key,
        source_key=b"\x33" * 32,
        dataset_id=b"\x44" * 16,
        provenance_class="SYNTHETIC_V1",
        gate_manifest_digest=v3_export.default_gate_manifest_digest(),
    )
    path = tmp_path / f"{name}.jsonl"
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
    return v3_export.read_dataset(path)


def _planted_dataset(tmp_path: Path, *, episodes: int = 8, turns: int = 24):
    return _dataset(
        [
            v3_export.SourceEpisode(
                privacy_scope="SYNTHETIC",
                session_identity=f"planted-{ordinal}",
                ordinal=ordinal,
                turns=_planted_turns(turns),
            )
            for ordinal in range(episodes)
        ],
        tmp_path,
        "planted",
    )


def _null_dataset(tmp_path: Path, *, episodes: int = 8, turns: int = 24):
    return _dataset(
        [
            v3_export.SourceEpisode(
                privacy_scope="SYNTHETIC",
                session_identity=f"null-{ordinal}",
                ordinal=ordinal,
                turns=_null_turns(turns, seed=1000 + ordinal),
            )
            for ordinal in range(episodes)
        ],
        tmp_path,
        "null",
    )


def _no_tone_dataset(tmp_path: Path, *, episodes: int = 8, turns: int = 24):
    return _dataset(
        [
            v3_export.SourceEpisode(
                privacy_scope="SYNTHETIC",
                session_identity=f"notone-{ordinal}",
                ordinal=ordinal,
                turns=_no_tone_turns(turns),
            )
            for ordinal in range(episodes)
        ],
        tmp_path,
        "notone",
    )


def _labeled_no_tone_dataset(tmp_path: Path, *, episodes: int = 4, turns: int = 12):
    """A labelled corpus where label-free ON/OFF must be directly comparable."""

    return _dataset(
        [
            v3_export.SourceEpisode(
                privacy_scope="SYNTHETIC",
                session_identity=f"lf3-{ordinal}",
                ordinal=ordinal,
                turns=tuple(
                    replace(
                        _turn(
                            index + 1,
                            channels={
                                _LENGTH_CHANNEL: float(20 + index),
                                _SURPRISE_CHANNEL: 0.35 + 0.3 * (index % 2),
                            },
                        ),
                        actual_action="HOLD" if index % 2 else "SPEAK",
                    )
                    for index in range(turns)
                ),
            )
            for ordinal in range(episodes)
        ],
        tmp_path,
        "lf3-labeled",
    )


# --------------------------------------------------------------------------- #
# Frozen formula-v2 gate contract
# --------------------------------------------------------------------------- #


def test_preregistered_gate_is_formula_v2_codec4_and_freezes_lf1_to_lf4() -> None:
    gate = _gate_manifest()

    validated = v3_replay.validate_gate_manifest(gate)

    assert validated["initial_state"]["initial_state_id"] == "neutral_eval_v2"
    assert validated["initial_state"]["state_schema_version"] == 2
    assert validated["initial_state"]["state_codec_version"] == 4
    assert validated["initial_state"]["formula_version"] == "sylanne.v3.formula.v2"
    assert validated["evaluation_profile"]["evaluation_profile_id"] == "FORMULA_V2_SCALAR"
    assert set(validated["label_free_gates"]) == {"LF_1", "LF_2", "LF_3", "LF_4"}
    assert validated["label_free_gates"]["LF_1"]["metric"] == "marginal_axis_mae"
    assert validated["label_free_gates"]["LF_2"]["min_reaction_valid_settled_turns"] == 150
    assert validated["label_free_gates"]["LF_3"]["max_relative_regression"] == 0.005
    assert validated["label_free_gates"]["LF_4"]["min_gain_removal_fraction"] == 0.50


@pytest.mark.parametrize(
    ("path", "legacy_value"),
    (
        (("initial_state", "initial_state_id"), "neutral_eval_v1"),
        (("initial_state", "state_codec_version"), 3),
        (("initial_state", "formula_version"), "sylanne.v3.formula.v1"),
        (("evaluation_profile", "evaluation_profile_id"), "FULL_24_STDP"),
    ),
)
def test_gate_manifest_validation_rejects_legacy_formula_v1_semantics(
    path: tuple[str, str], legacy_value: object
) -> None:
    gate = _gate_manifest()
    gate[path[0]][path[1]] = legacy_value

    with pytest.raises(v3_replay.ReplayError, match="formula-v2 gate manifest"):
        v3_replay.validate_gate_manifest(gate)


def test_formula_v2_evaluation_profile_has_no_retired_snn_stdp_semantics() -> None:
    profile = v3_export.evaluation_profile()

    assert profile.profile_id == "FORMULA_V2_SCALAR"
    assert profile.snn_enabled is False
    assert profile.ticks == 0
    assert profile.stdp_enabled is False
    assert profile.reuse_last_summary is False


def test_formula_v2_ablation_and_gate_have_no_live_retired_selector() -> None:
    gate_text = json.dumps(_gate_manifest(), sort_keys=True).lower()
    assert "snn" not in gate_text
    assert "stdp" not in gate_text
    assert all("snn" not in name.lower() and "stdp" not in name.lower() for name, _ in v3_ablation.LADDER)
    assert set(v3_ablation.CONTROLS) == {"label_free_on", "label_free_frozen"}


def test_label_free_gates_consume_the_manifest_evidence_floor(tmp_path: Path) -> None:
    dataset = _planted_dataset(tmp_path, episodes=1, turns=8)
    strict = _gate_manifest()
    relaxed = copy.deepcopy(strict)
    relaxed["label_free_gates"]["LF_2"]["min_reaction_valid_settled_turns"] = 1
    relaxed["label_free_gates"]["LF_2"]["min_episodes"] = 1

    strict_report = v3_ablation.run_label_free_gates(
        dataset, gate_manifest=strict, split=None, resamples=100, seed=7
    )
    relaxed_report = v3_ablation.run_label_free_gates(
        dataset, gate_manifest=relaxed, split=None, resamples=100, seed=7
    )

    assert strict_report["insufficient_evidence"] is True
    assert relaxed_report["insufficient_evidence"] is False
    assert relaxed_report["evidence"]["min_reaction_valid"] == 1
    assert relaxed_report["evidence"]["min_episodes"] == 1
    assert (
        relaxed_report["LF_4_permutation_control"]["required_collapse"]
        == relaxed["label_free_gates"]["LF_4"]["min_gain_removal_fraction"]
    )


def test_lf3_non_interference_is_executed_from_frozen_thresholds(tmp_path: Path) -> None:
    gate = _gate_manifest()
    report = v3_ablation.run_label_free_gates(
        _labeled_no_tone_dataset(tmp_path),
        gate_manifest=gate,
        split=None,
        resamples=100,
        seed=7,
    )

    lf3 = report["LF_3_non_interference"]
    frozen = gate["label_free_gates"]["LF_3"]
    assert lf3["status"] == "OK"
    assert lf3["max_relative_regression"] == frozen["max_relative_regression"]
    assert (
        lf3["max_hold_contradiction_degradation_percentage_points"]
        == frozen["max_hold_contradiction_degradation_percentage_points"]
    )
    assert set(lf3["required_zero_counters"]) == set(frozen["required_zero_counters"])
    assert all(value == 0 for value in lf3["observed_zero_counters"].values())
    assert lf3["passed"] is True


# --------------------------------------------------------------------------- #
# Planted corpus: LF-2 passes, LF-4 collapses, L1 recovers the offset direction
# --------------------------------------------------------------------------- #


def test_planted_corpus_lf2_passes_and_lf4_permutation_collapses(tmp_path: Path) -> None:
    dataset = _planted_dataset(tmp_path)
    report = v3_ablation.run_label_free_gates(dataset, split=None, resamples=1500, seed=7)

    assert report["insufficient_evidence"] is False
    assert report["evidence"]["reaction_valid_settled_turns"] >= v3_ablation.LF_MIN_REACTION_VALID

    lf2 = report["LF_2_preference_nll"]
    assert lf2["status"] == "OK"
    assert lf2["gain_point_estimate"] > 0.0  # the learned offset fits the reaction-weighted density
    assert lf2["lower_bound_above_zero"] is True
    assert lf2["passed"] is True
    # Honesty: LF-2 is a density-estimation claim, never a policy-superiority one.
    assert lf2["claim"] == "density_estimation_only"

    lf4 = report["LF_4_permutation_control"]
    assert lf4["status"] == "OK"
    assert lf4["passed"] is True
    # Shuffling r_react must remove at least half the gain.
    assert lf4["collapse_fraction"] >= v3_ablation.LF_PERMUTATION_COLLAPSE
    assert lf4["permuted_gain"] <= 0.5 * lf4["real_gain"]


def test_planted_corpus_l1_recovers_the_positive_offset_direction(tmp_path: Path) -> None:
    dataset = _planted_dataset(tmp_path)
    records = v3_replay.collect_label_free_records(dataset.episodes[0])
    # Replay the exact core L1 law over this episode (as the online path B would).
    offset = tuple(0.0 for _ in range(8))
    for record in records:
        if record.settled and record.reaction_valid:
            offset = _update_pref_offset(offset, record.r_react, record.s_dec, record.outcome)
    # Axis 5 (novelty) has a constant base preference (0.0) and was planted to sit
    # high on high-reaction turns, so the learned residual must be positive and inside
    # the declared [-0.30, 0.30] box.
    assert offset[5] > 0.05
    assert -0.30 <= offset[5] <= 0.30 + 1e-6


def test_lf1_marginal_head_reports_a_well_formed_verdict(tmp_path: Path) -> None:
    dataset = _planted_dataset(tmp_path)
    report = v3_ablation.run_label_free_gates(dataset, split=None, resamples=1500, seed=7)
    lf1 = report["LF_1_marginal_world_model"]
    assert lf1["status"] in ("OK", "INSUFFICIENT_EVIDENCE")
    # The carry-forward baseline is reported, never gated (spec §6.1).
    assert "carry_forward_mae" in lf1
    assert lf1["control"] == "frozen_prior_head"
    if lf1["status"] == "OK":
        assert lf1["verdict"] in ("EARNS_MARGINAL_HEAD", "NO_MARGINAL_IMPROVEMENT")
        assert lf1["frozen_mae"] is not None and lf1["learner_mae"] is not None


# --------------------------------------------------------------------------- #
# Null corpus: no reaction-conditioned structure -> LF-2 honestly does not pass
# --------------------------------------------------------------------------- #


def test_null_corpus_lf2_does_not_pass(tmp_path: Path) -> None:
    dataset = _null_dataset(tmp_path)
    report = v3_ablation.run_label_free_gates(dataset, split=None, resamples=1500, seed=7)
    # Enough turns to clear the evidence floor, so this is a real NEGATIVE, not a
    # thin-data abstention.
    assert report["insufficient_evidence"] is False
    lf2 = report["LF_2_preference_nll"]
    assert lf2["status"] == "OK"
    assert lf2["passed"] is False


# --------------------------------------------------------------------------- #
# Evidence floor: below 150 reaction-valid turns / 3 episodes -> abstain honestly
# --------------------------------------------------------------------------- #


def test_thin_corpus_reports_insufficient_evidence(tmp_path: Path) -> None:
    dataset = _planted_dataset(tmp_path, episodes=2, turns=8)  # far below 150 valid turns
    report = v3_ablation.run_label_free_gates(dataset, split=None, resamples=1500, seed=7)
    assert report["insufficient_evidence"] is True
    assert report["LF_2_preference_nll"]["status"] == "INSUFFICIENT_EVIDENCE"
    assert report["LF_4_permutation_control"]["status"] == "INSUFFICIENT_EVIDENCE"


def test_current_real_export_shape_reports_insufficient_evidence(tmp_path: Path) -> None:
    """The acceptance item: on the existing 3/36-channel real datasets (length only,
    no tone channel) the gates must honestly report INSUFFICIENT_EVIDENCE -- "reporting
    hunger" is itself the deliverable (task Slice D GREEN)."""

    dataset = _no_tone_dataset(tmp_path)
    report = v3_ablation.run_label_free_gates(dataset, split=None, resamples=800, seed=7)
    # No tone channel -> every reaction is NO_TONE_EVIDENCE -> zero reaction-valid turns.
    assert report["coverage_funnel"]["reaction_valid"] == 0
    assert report["insufficient_evidence"] is True
    assert report["LF_2_preference_nll"]["status"] == "INSUFFICIENT_EVIDENCE"
    assert report["LF_4_permutation_control"]["status"] == "INSUFFICIENT_EVIDENCE"
    assert report["LF_2_preference_nll"].get("passed") is not True


# --------------------------------------------------------------------------- #
# Coverage funnel + honesty
# --------------------------------------------------------------------------- #


def test_coverage_funnel_is_a_monotone_three_level_funnel(tmp_path: Path) -> None:
    dataset = _planted_dataset(tmp_path)
    report = v3_ablation.run_label_free_gates(dataset, split=None, resamples=200, seed=7)
    funnel = report["coverage_funnel"]
    assert funnel["total_turns"] >= funnel["adjacent"] >= funnel["reaction_valid"] > 0
    assert report["claims"]["policy_superiority"] is False
    assert report["claims"]["conversational_gain"] is False


def test_label_free_gates_are_wired_into_the_ablation_report(tmp_path: Path) -> None:
    dataset_path = tmp_path / "planted.jsonl"
    _planted_dataset(tmp_path)  # writes tmp_path/planted.jsonl
    report = v3_ablation.run_ablation(
        [dataset_path],
        gate_manifest=json.loads((FIXTURE_DIR / "v3_gate_manifest_v1.json").read_text(encoding="utf-8")),
        gate_manifest_digest=v3_export.file_digest(FIXTURE_DIR / "v3_gate_manifest_v1.json"),
        controls=("label_free_on", "label_free_frozen"),
        resamples=200,
        split=None,
    )
    assert "label_free" in report
    assert report["label_free"]["report_kind"] == "v3_label_free_gates_v2"


def test_the_label_free_record_carries_no_action_field() -> None:
    """The by-construction label-free guarantee: the record the metrics consume has no
    action field, so no metric can branch on the action no matter what it does."""

    fields = set(v3_replay.LabelFreeTurnRecord.__dataclass_fields__)
    assert fields == {"settled", "reaction_valid", "r_react", "s_dec", "outcome"}
    forbidden = {"action", "actual_action", "shadow_action", "projected_actual_action"}
    assert not (fields & forbidden)


def test_the_gate_metric_functions_never_read_an_action_label() -> None:
    """The prequential metric functions must not branch on any action field.

    (``collect_label_free_records`` is excluded: it faithfully replays the dataset, so
    it legitimately reads ``turn["actual_action"]`` to drive ``orchestrate`` -- but the
    record it emits, checked above, is action-independent, and s_dec/outcome/r_react are
    all provably independent of the chosen action.)
    """

    source = Path(v3_replay.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    lf_functions = {
        "marginal_prequential_episode",
        "preference_prequential_episode",
        "label_free_coverage",
        "_marginal_priors",
        "_mean_axis_nll",
    }
    forbidden = {"actual_action", "shadow_action", "projected_actual_action", "selected_action", "action"}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in lf_functions:
            names = {
                child.attr for child in ast.walk(node) if isinstance(child, ast.Attribute)
            } | {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}
            leaked = names & forbidden
            assert not leaked, f"{node.name} reads an action label: {leaked}"
