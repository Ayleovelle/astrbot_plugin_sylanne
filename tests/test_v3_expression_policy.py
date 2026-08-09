"""RED/GREEN tests for Task 9 expression policy (design section 12).

``ExpressionPolicy`` returns only numeric/bucket constraints and a bounded style
signature; it never stores or emits literal reply text or a deterministic
hesitation prefix.  Repetition control comes purely from the four-signature style
ring: a candidate matching either of the last two turns loses hesitation and
moves one length bucket shorter.
"""

from __future__ import annotations

from dataclasses import fields
from math import isclose

from sylanne_alpha.v3core import formula_v1 as formula
from sylanne_alpha.v3core.contracts import Action
from sylanne_alpha.v3core.expression import (
    ExpressionConstraints,
    expression_policy,
    next_style_ring,
)


def _frame_values(exhaustion: float = 0.5) -> tuple:
    values = [0.5 for _ in range(36)]
    values[10] = exhaustion
    return tuple(values)


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


# --------------------------------------------------------------------------- #
# No literal text is ever produced
# --------------------------------------------------------------------------- #


def test_constraints_carry_no_literal_text() -> None:
    s = (0.2, 0.3, 0.1, 0.4, 0.6, 0.0, 0.5, 0.5)
    constraints = expression_policy(Action.CLARIFY, s, _frame_values(), ())
    field_names = {f.name for f in fields(constraints)}
    assert field_names == {
        "action",
        "length_bucket",
        "pace",
        "directness",
        "warmth",
        "hesitation",
        "style_signature",
    }
    # No field is free text: length_bucket is a fixed enum-like bucket token.
    assert constraints.length_bucket in formula.EXPRESSION_LENGTH_BUCKETS


# --------------------------------------------------------------------------- #
# Per-action constraints
# --------------------------------------------------------------------------- #


def test_hold_constraints_are_fixed() -> None:
    s = (0.9, 0.9, -0.9, 0.9, 0.9, 0.9, 0.9, 0.9)
    constraints = expression_policy(Action.HOLD, s, _frame_values(), ())
    assert constraints.length_bucket == "NONE"
    assert constraints.pace == 0.0
    assert constraints.directness == 0.50
    assert constraints.warmth == 0.50
    assert constraints.hesitation is False


def test_speak_length_thresholds_and_formulas() -> None:
    low, high = formula.SPEAK_LENGTH_THRESHOLDS
    for ep, expected in ((low - 0.1, "SHORT"), ((low + high) / 2, "MEDIUM"), (high + 0.1, "LONG")):
        s = (0.4, 0.5, 0.0, 0.6, 0.3, 0.0, 0.7, ep)
        c = expression_policy(Action.SPEAK, s, _frame_values(0.5), ())
        assert c.length_bucket == expected
        assert isclose(c.pace, _clip01(0.5 + 0.2 * 0.5 - 0.2 * 0.0), abs_tol=1e-12)
        assert isclose(c.directness, _clip01(0.5 + 0.25 * 0.7 - 0.2 * 0.3), abs_tol=1e-12)
        assert isclose(c.warmth, _clip01(0.5 + 0.25 * 0.6 + 0.15 * 0.4), abs_tol=1e-12)


def test_clarify_hesitation_requires_uncertainty_threshold() -> None:
    threshold = formula.CLARIFY_HESITATION_UNCERTAINTY_THRESHOLD
    s_low = (0.0, 0.0, 0.0, 0.3, threshold, 0.0, 0.0, 0.0)  # not strictly above threshold
    assert expression_policy(Action.CLARIFY, s_low, _frame_values(), ()).hesitation is False
    s_high = (0.0, 0.0, 0.0, 0.3, threshold + 0.1, 0.0, 0.0, 0.0)
    c = expression_policy(Action.CLARIFY, s_high, _frame_values(), ())
    assert c.hesitation is True
    assert c.length_bucket == "SHORT"
    assert isclose(c.warmth, _clip01(0.5 + 0.2 * 0.3), abs_tol=1e-12)
    assert c.pace == 0.45 and c.directness == 0.75


def test_reach_length_by_affiliation() -> None:
    thr = formula.REACH_AFFILIATION_MEDIUM_THRESHOLD
    s_short = (0.0, 0.0, 0.0, thr - 0.1, 0.0, 0.0, 0.0, 0.0)
    s_medium = (0.0, 0.0, 0.0, thr + 0.1, 0.0, 0.0, 0.0, 0.0)
    assert expression_policy(Action.REACH, s_short, _frame_values(), ()).length_bucket == "SHORT"
    assert expression_policy(Action.REACH, s_medium, _frame_values(), ()).length_bucket == "MEDIUM"
    c = expression_policy(Action.REACH, s_medium, _frame_values(), ())
    assert isclose(c.warmth, _clip01(0.7 + 0.2 * (thr + 0.1)), abs_tol=1e-12)
    assert c.pace == 0.40 and c.directness == 0.45


# --------------------------------------------------------------------------- #
# Style ring suppression
# --------------------------------------------------------------------------- #


def test_repeat_signature_drops_hesitation_and_shortens_length() -> None:
    s = (0.0, 0.0, 0.0, 0.3, 0.9, 0.0, 0.0, 0.0)  # CLARIFY hesitation desired
    fresh = expression_policy(Action.CLARIFY, s, _frame_values(), ())
    assert fresh.hesitation is True
    # Put the candidate signature into the last-two window -> suppression.
    ring = (fresh.style_signature,)
    suppressed = expression_policy(Action.CLARIFY, s, _frame_values(), ring)
    assert suppressed.hesitation is False


def test_speak_length_moves_one_bucket_shorter_on_repeat() -> None:
    s = (0.4, 0.5, 0.0, 0.6, 0.3, 0.0, 0.7, 0.9)  # LONG SPEAK
    fresh = expression_policy(Action.SPEAK, s, _frame_values(), ())
    assert fresh.length_bucket == "LONG"
    # The candidate (LONG, no hesitation) signature is what would repeat.
    candidate_sig = fresh.style_signature
    shorter = expression_policy(Action.SPEAK, s, _frame_values(), (candidate_sig,))
    assert shorter.length_bucket == "MEDIUM"


def test_repeat_only_checks_last_two_turns() -> None:
    s = (0.4, 0.5, 0.0, 0.6, 0.3, 0.0, 0.7, 0.9)
    fresh = expression_policy(Action.SPEAK, s, _frame_values(), ())
    sig = fresh.style_signature
    # sig three turns back (positions -3) is outside the lookback window.
    ring = (sig, (1, 0, 0, 0), (2, 0, 1, 3))
    assert expression_policy(Action.SPEAK, s, _frame_values(), ring).length_bucket == "LONG"


def test_next_style_ring_keeps_last_four() -> None:
    ring: tuple = ()
    for index in range(6):
        ring = next_style_ring(ring, (index % 4, 0, 1, 2))
    assert len(ring) == formula.STYLE_SIGNATURE_RING_CAPACITY
    assert ring[-1] == (5 % 4, 0, 1, 2)


def test_returns_expression_constraints_type() -> None:
    s = (0.0,) * 8
    assert isinstance(expression_policy(Action.HOLD, s, _frame_values(), ()), ExpressionConstraints)


def test_invalid_exhaustion_channel_is_gated_out_of_pace() -> None:
    """E (Task15 privacy/perf finding): channel 10 (exhaustion) is the one raw
    observation read here; it must be gated by valid_mask. When invalid, its
    semantic default (0.0 -> center -1.0) must NOT leak into SPEAK pace as fake
    'not tired' evidence (design §7: invalid channels are never interpreted)."""
    s = (0.2, 0.6, 0.1, 0.4, 0.3, 0.0, 0.5, 0.9)  # arousal=s[1]=0.6, high pressure -> SPEAK
    all_valid = (1 << 36) - 1
    invalid_ch10 = all_valid & ~(1 << 10)

    # Non-interference: with channel 10 invalid, its raw value cannot move pace.
    p_a = expression_policy(Action.SPEAK, s, _frame_values(0.0), (), invalid_ch10).pace
    p_b = expression_policy(Action.SPEAK, s, _frame_values(1.0), (), invalid_ch10).pace
    assert p_a == p_b

    # Gated pace equals the neutral pace (exhaustion term contributes exactly zero).
    base_p, w_arousal, _w_exhaustion = formula.SPEAK_PACE_COEFFS
    expected = _clip01(base_p + w_arousal * s[1])
    assert isclose(p_a, expected, abs_tol=1e-9)

    # Gate is real, not a no-op: when channel 10 IS valid its value does move pace.
    p_valid = expression_policy(Action.SPEAK, s, _frame_values(0.0), (), all_valid).pace
    assert not isclose(p_valid, expected, abs_tol=1e-9)
