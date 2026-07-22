"""formula v2 Slice A: label-free ReactionSignalV1 constants + pure function.

The t+1 user message is the real causal consequence of turn t's *executed*
interaction, so its tone / engagement / length / latency features score how the
user reacted without ever knowing which action the core chose.  These tests pin
the Slice A contract from ``docs/superpowers/specs/
2026-07-18-v3core-formula-v2-label-free-reaction-learning-spec.md`` §1.2:

* the reaction constants have their exact declared values and the gap-attenuator
  thresholds truly invert the encoder's ``_log_gap`` normalization;
* ``reaction_signal`` is bounded / finite / deterministic;
* the four INVALID reasons each fire in the declared precedence, and every
  INVALID result fails closed (``valid`` False, ``r_react`` exactly 0.0);
* latency is a monotone-non-increasing DAMPER (never evidence), missing gap is a
  neutral 1.0, the length term is suppressed during warm-up and is a relative
  baseline deviation afterwards, and the present-term weight renormalization is
  exact for one / two / three terms;
* the function never takes an Action-typed argument (label-free by construction);
* the ``labelfree`` manifest block is folded into formula v2 and the digest is
  pinned to the regenerated replay fixtures and benchmark evidence.
"""

from __future__ import annotations

import ast
from math import isfinite
from pathlib import Path

import pytest

from sylanne_alpha.v3core import formula_v1 as formula
from sylanne_alpha.v3core.contracts import TurnContextClass
from sylanne_alpha.v3core.observation.encoder import _log_gap
from sylanne_alpha.v3core.observation.models import ObservationFrame
from sylanne_alpha.v3core.learning.reaction import (
    ReactionResult,
    gap_attenuation,
    reaction_signal,
)


_LENGTH = 18
_VALENCE = 25
_ENGAGEMENT = 26
_GAP = 31


def _frame(values: dict[int, float], valid: set[int]) -> ObservationFrame:
    """Build a 36-channel frame with the given normalized values / validity."""

    raw = [0.0] * 36
    for index, value in values.items():
        raw[index] = value
    mask = 0
    for index in valid:
        mask |= 1 << index
    return ObservationFrame(values=tuple(raw), valid_mask=mask)


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #


def test_reaction_constants_have_their_exact_declared_values() -> None:
    assert formula.REACT_W_VALENCE == 0.5
    assert formula.REACT_W_ENGAGEMENT == 0.3
    assert formula.REACT_W_LENGTH == 0.2
    assert formula.REACT_LEN_GAIN == 3.0
    assert formula.REACT_GAP_ATTEN_LO == 0.62
    assert formula.REACT_GAP_ATTEN_HI == 0.78
    assert formula.REACT_WARMUP_COUNT == 5
    assert formula.LF_REACTION_CONTEXTS == ("ADDRESSED", "AMBIENT")
    assert formula.LF_ELIGIBLE_ORIGIN_CONTEXTS == ("ADDRESSED", "AMBIENT", "PROACTIVE")


def test_labelfree_learner_state_constants_are_exact() -> None:
    assert formula.PREF_OFFSET_BOUNDS == (-0.30, 0.30)
    assert formula.PREF_ETA == 0.05
    assert formula.LEN_BASELINE_ETA == 0.10
    assert formula.LEN_BASELINE_INIT == 0.60
    # the marginal world-model head reuses the per-action EKF numeric priors.
    assert formula.MARGINAL_INITIAL_G == formula.ACTION_INITIAL_G == 0.85
    assert formula.MARGINAL_INITIAL_B == 0.0
    assert formula.MARGINAL_INITIAL_V == formula.ACTION_INITIAL_V == 0.25
    assert formula.MARGINAL_INITIAL_R == formula.ACTION_INITIAL_R == 0.20
    assert formula.MARGINAL_SIGMA_INIT == (0.10, 0.10)
    assert formula.MARGINAL_Q_THETA == formula.ACTION_Q_THETA == 1e-4


def test_reaction_reason_vocabulary_is_closed_and_declared() -> None:
    assert formula.REACTION_REASON_VALID == "VALID"
    assert formula.REACTION_INVALID_REASONS == (
        "NOT_INBOUND",
        "SENDER_MISMATCH",
        "NO_TONE_EVIDENCE",
        "STALE_REACTION",
    )
    assert formula.REACTION_REASONS == ("VALID",) + formula.REACTION_INVALID_REASONS


def test_gap_thresholds_invert_the_encoder_log_gap_normalization() -> None:
    """LO/HI are declared in normalized u31 space; they must match ``_log_gap``.

    ~330 s (~5.5 min) -> full weight boundary; ~4270 s (~71 min) -> censor.
    """

    assert _log_gap(330.0) == pytest.approx(formula.REACT_GAP_ATTEN_LO, abs=5e-3)
    assert _log_gap(4270.0) == pytest.approx(formula.REACT_GAP_ATTEN_HI, abs=5e-3)


# --------------------------------------------------------------------------- #
# Gap attenuator (latency is a damper, never evidence)
# --------------------------------------------------------------------------- #


def test_gap_attenuation_endpoints_are_exact() -> None:
    assert gap_attenuation(True, formula.REACT_GAP_ATTEN_LO) == 1.0
    assert gap_attenuation(True, formula.REACT_GAP_ATTEN_HI) == 0.0
    midpoint = (formula.REACT_GAP_ATTEN_LO + formula.REACT_GAP_ATTEN_HI) / 2.0
    assert gap_attenuation(True, midpoint) == pytest.approx(0.5)
    # below LO clamps to full weight; above HI clamps to zero.
    assert gap_attenuation(True, 0.0) == 1.0
    assert gap_attenuation(True, 1.0) == 0.0


def test_gap_attenuation_missing_gap_is_a_neutral_one() -> None:
    # a missing gap channel is a declared noise exposure: neutral attenuator.
    assert gap_attenuation(False, 0.0) == 1.0
    assert gap_attenuation(False, 0.99) == 1.0


def test_gap_attenuation_is_monotone_non_increasing_in_gap() -> None:
    previous = 1.0
    for step in range(0, 101):
        u = step / 100.0
        current = gap_attenuation(True, u)
        assert 0.0 <= current <= 1.0
        assert current <= previous + 1e-12
        previous = current


# --------------------------------------------------------------------------- #
# reaction_signal: valid synthesis
# --------------------------------------------------------------------------- #


def test_valid_reaction_is_bounded_finite_and_deterministic() -> None:
    frame = _frame({_VALENCE: 0.9, _ENGAGEMENT: 0.8}, {_VALENCE, _ENGAGEMENT})
    first = reaction_signal(frame, TurnContextClass.ADDRESSED, 0.6, 0, None)
    second = reaction_signal(frame, TurnContextClass.ADDRESSED, 0.6, 0, None)
    assert first == second
    assert first.valid is True
    assert first.reason == "VALID"
    assert isfinite(first.r_react)
    assert -1.0 <= first.r_react <= 1.0
    assert first.r_react > 0.0  # positive tone -> positive reaction


def test_weight_renormalization_single_double_triple_terms() -> None:
    v, e, length = 0.75, 0.60, 0.90
    baseline = 0.60
    tv = 2.0 * v - 1.0
    te = 2.0 * e - 1.0
    # gap absent -> attenuator 1.0, so r_react == r_raw.
    single = reaction_signal(_frame({_VALENCE: v}, {_VALENCE}), TurnContextClass.AMBIENT, baseline, 0, None)
    assert single.r_react == pytest.approx(tv)

    double = reaction_signal(
        _frame({_VALENCE: v, _ENGAGEMENT: e}, {_VALENCE, _ENGAGEMENT}),
        TurnContextClass.AMBIENT,
        baseline,
        0,
        None,
    )
    assert double.r_react == pytest.approx((0.5 * tv + 0.3 * te) / 0.8)

    tl = max(-1.0, min(1.0, 3.0 * (length - baseline)))
    triple = reaction_signal(
        _frame({_VALENCE: v, _ENGAGEMENT: e, _LENGTH: length}, {_VALENCE, _ENGAGEMENT, _LENGTH}),
        TurnContextClass.AMBIENT,
        baseline,
        formula.REACT_WARMUP_COUNT,  # warm-up satisfied so the length term counts
        None,
        )
    assert triple.r_react == pytest.approx((0.5 * tv + 0.3 * te + 0.2 * tl) / 1.0)


def test_engagement_only_still_a_tone_term() -> None:
    e = 0.9
    result = reaction_signal(_frame({_ENGAGEMENT: e}, {_ENGAGEMENT}), TurnContextClass.ADDRESSED, 0.6, 0, None)
    assert result.valid is True
    assert result.r_react == pytest.approx(2.0 * e - 1.0)


# --------------------------------------------------------------------------- #
# reaction_signal: length term warm-up + relative baseline
# --------------------------------------------------------------------------- #


def test_length_term_is_suppressed_before_warmup() -> None:
    # a long message (well above baseline) must NOT move the signal before warm-up.
    below = reaction_signal(
        _frame({_VALENCE: 0.5, _LENGTH: 1.0}, {_VALENCE, _LENGTH}),
        TurnContextClass.ADDRESSED,
        0.2,
        formula.REACT_WARMUP_COUNT - 1,  # one short of warm-up
        None,
    )
    valence_only = reaction_signal(
        _frame({_VALENCE: 0.5}, {_VALENCE}),
        TurnContextClass.ADDRESSED,
        0.2,
        0,
        None,
    )
    assert below.r_react == pytest.approx(valence_only.r_react)


def test_length_term_is_a_relative_baseline_deviation_after_warmup() -> None:
    # identical channels, only the length-vs-baseline relation differs.
    long_message = reaction_signal(
        _frame({_VALENCE: 0.5, _LENGTH: 0.9}, {_VALENCE, _LENGTH}),
        TurnContextClass.ADDRESSED,
        0.3,
        formula.REACT_WARMUP_COUNT,
        None,
    )
    short_message = reaction_signal(
        _frame({_VALENCE: 0.5, _LENGTH: 0.1}, {_VALENCE, _LENGTH}),
        TurnContextClass.ADDRESSED,
        0.3,
        formula.REACT_WARMUP_COUNT,
        None,
    )
    # above baseline lifts the reaction; below baseline lowers it.
    assert long_message.r_react > short_message.r_react
    # at exactly the baseline the length term contributes nothing.
    at_baseline = reaction_signal(
        _frame({_VALENCE: 0.5, _LENGTH: 0.3}, {_VALENCE, _LENGTH}),
        TurnContextClass.ADDRESSED,
        0.3,
        formula.REACT_WARMUP_COUNT,
        None,
    )
    valence_only = reaction_signal(
        _frame({_VALENCE: 0.5}, {_VALENCE}),
        TurnContextClass.ADDRESSED,
        0.3,
        formula.REACT_WARMUP_COUNT,
        None,
    )
    assert at_baseline.r_react == pytest.approx(valence_only.r_react)


# --------------------------------------------------------------------------- #
# reaction_signal: the four INVALID reasons + fail-closed
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("context", [TurnContextClass.IDLE, TurnContextClass.PROACTIVE])
def test_non_inbound_context_is_invalid(context: TurnContextClass) -> None:
    frame = _frame({_VALENCE: 0.9, _ENGAGEMENT: 0.9}, {_VALENCE, _ENGAGEMENT})
    result = reaction_signal(frame, context, 0.6, 0, None)
    assert result.valid is False
    assert result.reason == "NOT_INBOUND"
    assert result.r_react == 0.0


def test_other_speaker_interjection_is_invalid() -> None:
    frame = _frame({_VALENCE: 0.9, _ENGAGEMENT: 0.9}, {_VALENCE, _ENGAGEMENT})
    result = reaction_signal(frame, TurnContextClass.ADDRESSED, 0.6, 0, same_sender=False)
    assert result.valid is False
    assert result.reason == "SENDER_MISMATCH"
    assert result.r_react == 0.0


def test_unknown_sender_none_is_admitted_as_declared_noise() -> None:
    frame = _frame({_VALENCE: 0.9}, {_VALENCE})
    result = reaction_signal(frame, TurnContextClass.ADDRESSED, 0.6, 0, same_sender=None)
    assert result.valid is True


def test_no_tone_evidence_is_invalid_even_with_a_length_term() -> None:
    # length term present + warm-up satisfied, but neither valence nor engagement.
    frame = _frame({_LENGTH: 0.9}, {_LENGTH})
    result = reaction_signal(frame, TurnContextClass.ADDRESSED, 0.3, formula.REACT_WARMUP_COUNT, None)
    assert result.valid is False
    assert result.reason == "NO_TONE_EVIDENCE"
    assert result.r_react == 0.0


def test_no_valid_channels_at_all_is_no_tone_evidence() -> None:
    frame = _frame({}, set())
    result = reaction_signal(frame, TurnContextClass.ADDRESSED, 0.6, 0, None)
    assert result.valid is False
    assert result.reason == "NO_TONE_EVIDENCE"
    assert result.r_react == 0.0


def test_stale_reaction_is_censored_when_the_gap_zeroes_the_attenuator() -> None:
    frame = _frame(
        {_VALENCE: 0.9, _GAP: formula.REACT_GAP_ATTEN_HI},
        {_VALENCE, _GAP},
    )
    result = reaction_signal(frame, TurnContextClass.ADDRESSED, 0.6, 0, None)
    assert result.valid is False
    assert result.reason == "STALE_REACTION"
    assert result.r_react == 0.0


def test_gap_below_the_high_threshold_still_attenuates_but_survives() -> None:
    v = 0.9
    tv = 2.0 * v - 1.0
    midpoint = (formula.REACT_GAP_ATTEN_LO + formula.REACT_GAP_ATTEN_HI) / 2.0
    frame = _frame({_VALENCE: v, _GAP: midpoint}, {_VALENCE, _GAP})
    result = reaction_signal(frame, TurnContextClass.ADDRESSED, 0.6, 0, None)
    assert result.valid is True
    assert result.r_react == pytest.approx(tv * 0.5)


def test_reason_precedence_context_beats_sender_beats_tone_beats_stale() -> None:
    # a frame that would trip STALE and NO_TONE, in a non-inbound context with a
    # sender mismatch, must report the earliest failing gate: NOT_INBOUND.
    frame = _frame({_GAP: 1.0}, {_GAP})
    result = reaction_signal(frame, TurnContextClass.IDLE, 0.6, 0, same_sender=False)
    assert result.reason == "NOT_INBOUND"
    # inbound + sender mismatch -> SENDER_MISMATCH before tone/stale.
    result = reaction_signal(frame, TurnContextClass.ADDRESSED, 0.6, 0, same_sender=False)
    assert result.reason == "SENDER_MISMATCH"
    # inbound + same sender, no tone but a stale gap -> NO_TONE before STALE.
    result = reaction_signal(frame, TurnContextClass.ADDRESSED, 0.6, 0, same_sender=True)
    assert result.reason == "NO_TONE_EVIDENCE"


# --------------------------------------------------------------------------- #
# Boundedness under stress + type discipline
# --------------------------------------------------------------------------- #


def test_extreme_channel_values_stay_bounded() -> None:
    frame = _frame(
        {_VALENCE: 1.0, _ENGAGEMENT: 1.0, _LENGTH: 1.0, _GAP: 0.0},
        {_VALENCE, _ENGAGEMENT, _LENGTH, _GAP},
    )
    result = reaction_signal(frame, TurnContextClass.ADDRESSED, 0.0, 999, None)
    assert result.valid is True
    assert -1.0 <= result.r_react <= 1.0
    frame = _frame(
        {_VALENCE: 0.0, _ENGAGEMENT: 0.0, _LENGTH: 0.0, _GAP: 0.0},
        {_VALENCE, _ENGAGEMENT, _LENGTH, _GAP},
    )
    result = reaction_signal(frame, TurnContextClass.ADDRESSED, 1.0, 999, None)
    assert result.valid is True
    assert -1.0 <= result.r_react <= 1.0


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(lambda: reaction_signal(object(), TurnContextClass.ADDRESSED, 0.6, 0, None), id="frame"),
        pytest.param(
            lambda: reaction_signal(
                _frame({_VALENCE: 0.9}, {_VALENCE}), "ADDRESSED", 0.6, 0, None
            ),
            id="context",
        ),
        pytest.param(
            lambda: reaction_signal(
                _frame({_VALENCE: 0.9}, {_VALENCE}), TurnContextClass.ADDRESSED, 0, 0, None
            ),
            id="baseline-int",
        ),
        pytest.param(
            lambda: reaction_signal(
                _frame({_VALENCE: 0.9}, {_VALENCE}), TurnContextClass.ADDRESSED, 0.6, True, None
            ),
            id="count-bool",
        ),
        pytest.param(
            lambda: reaction_signal(
                _frame({_VALENCE: 0.9}, {_VALENCE}), TurnContextClass.ADDRESSED, 0.6, 0, 1
            ),
            id="same-sender-int",
        ),
    ],
)
def test_reaction_signal_rejects_wrong_types(factory) -> None:
    with pytest.raises(TypeError):
        factory()


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(
            lambda: reaction_signal(
                _frame({_VALENCE: 0.9}, {_VALENCE}), TurnContextClass.ADDRESSED, 1.5, 0, None
            ),
            id="baseline-out-of-range",
        ),
        pytest.param(
            lambda: reaction_signal(
                _frame({_VALENCE: 0.9}, {_VALENCE}), TurnContextClass.ADDRESSED, 0.6, -1, None
            ),
            id="negative-count",
        ),
    ],
)
def test_reaction_signal_rejects_out_of_range_scalars(factory) -> None:
    with pytest.raises(ValueError):
        factory()


# --------------------------------------------------------------------------- #
# ReactionResult DTO is frozen, exact-typed, fail-closed
# --------------------------------------------------------------------------- #


def test_reaction_result_rejects_inconsistent_or_dirty_values() -> None:
    # valid must be true iff reason is VALID.
    with pytest.raises(ValueError):
        ReactionResult(valid=True, reason="NOT_INBOUND", r_react=0.0)
    with pytest.raises(ValueError):
        ReactionResult(valid=False, reason="VALID", r_react=0.0)
    # an invalid result must fail closed with r_react exactly 0.0.
    with pytest.raises(ValueError):
        ReactionResult(valid=False, reason="STALE_REACTION", r_react=0.4)
    # r_react must be finite and bounded.
    with pytest.raises(ValueError):
        ReactionResult(valid=True, reason="VALID", r_react=1.5)
    with pytest.raises(ValueError):
        ReactionResult(valid=True, reason="VALID", r_react=float("nan"))
    # unknown reason string is rejected.
    with pytest.raises(ValueError):
        ReactionResult(valid=True, reason="WHATEVER", r_react=0.0)
    # exact-type discipline: bool cannot impersonate, int cannot be r_react.
    with pytest.raises(TypeError):
        ReactionResult(valid=1, reason="VALID", r_react=0.0)
    with pytest.raises(TypeError):
        ReactionResult(valid=True, reason="VALID", r_react=0)


def test_reaction_result_is_frozen() -> None:
    result = ReactionResult(valid=True, reason="VALID", r_react=0.5)
    with pytest.raises(Exception):
        result.r_react = 0.1  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Label-free by construction: no Action-typed inputs (AST assertion)
# --------------------------------------------------------------------------- #


def test_reaction_module_never_references_the_action_type() -> None:
    source = Path("sylanne_alpha/v3core/learning/reaction.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert "Action" not in imported, "the reaction signal must be label-free"

    reaction_fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "reaction_signal"
    )
    annotations = [ast.dump(arg.annotation) for arg in reaction_fn.args.args if arg.annotation]
    assert not any("Action" in dump for dump in annotations)


# --------------------------------------------------------------------------- #
# Manifest / digest: block authored, fold DEFERRED to keep digest byte-stable
# --------------------------------------------------------------------------- #


def test_labelfree_manifest_block_is_authored_with_the_declared_semantics() -> None:
    block = formula.build_labelfree_manifest()
    reaction = block["reaction"]
    assert reaction["w_valence"] == formula.REACT_W_VALENCE
    assert reaction["w_engagement"] == formula.REACT_W_ENGAGEMENT
    assert reaction["w_length"] == formula.REACT_W_LENGTH
    assert reaction["len_gain"] == formula.REACT_LEN_GAIN
    assert reaction["gap_atten_lo"] == formula.REACT_GAP_ATTEN_LO
    assert reaction["gap_atten_hi"] == formula.REACT_GAP_ATTEN_HI
    assert reaction["warmup_count"] == formula.REACT_WARMUP_COUNT
    assert reaction["reaction_contexts"] == formula.LF_REACTION_CONTEXTS
    assert reaction["eligible_origin_contexts"] == formula.LF_ELIGIBLE_ORIGIN_CONTEXTS
    assert reaction["invalid_reasons"] == formula.REACTION_INVALID_REASONS
    learners = block["learners"]
    assert learners["pref_offset_bounds"] == formula.PREF_OFFSET_BOUNDS
    assert learners["pref_eta"] == formula.PREF_ETA
    assert learners["len_baseline_init"] == formula.LEN_BASELINE_INIT
    # the block must be canonical-serializable so Slice C/D can fold it verbatim.
    from sylanne_alpha.v3core.canonical import canonical_json_bytes

    assert canonical_json_bytes(block)


def test_labelfree_block_is_folded_into_the_v2_manifest() -> None:
    # Slice D folds the labelfree block into build_formula_manifest (spec §4.3): the
    # manifest now carries the ``labelfree`` key, FORMULA_VERSION is v2, and the
    # digest is the intentional v2 bump.  The folded block is byte-identical to the
    # standalone builder, so nothing is silently re-authored during the fold.
    assert "labelfree" in formula.FORMULA_MANIFEST
    assert formula.FORMULA_MANIFEST["labelfree"] == formula.build_labelfree_manifest()
    assert formula.FORMULA_VERSION == "sylanne.v3.formula.v2"
    assert (
        formula.FORMULA_DIGEST
        == "59fcaf3b2079619827df002a0832627d6d0cdbfdee573388b7a785e2c2de9485"
    )


def test_validate_formula_manifest_covers_the_labelfree_constants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # the global gate must reject a malformed labelfree constant (fail-closed).
    with monkeypatch.context() as scoped:
        scoped.setattr(formula, "REACT_GAP_ATTEN_HI", formula.REACT_GAP_ATTEN_LO)
        with pytest.raises(ValueError):
            formula.validate_formula_manifest()
    with monkeypatch.context() as scoped:
        scoped.setattr(formula, "REACT_W_VALENCE", -0.5)
        with pytest.raises(ValueError):
            formula.validate_formula_manifest()
    with monkeypatch.context() as scoped:
        scoped.setattr(formula, "REACT_WARMUP_COUNT", 0)
        with pytest.raises(ValueError):
            formula.validate_formula_manifest()
    with monkeypatch.context() as scoped:
        scoped.setattr(formula, "PREF_ETA", 1.5)
        with pytest.raises(ValueError):
            formula.validate_formula_manifest()
    # untouched, the gate still returns the analytic Jacobian bound.
    assert formula.validate_formula_manifest() == formula.JACOBIAN_STABILITY_BOUND
