"""Expression policy: numeric/bucket constraints only (design section 12).

``ExpressionPolicy`` converts the selected action and decision state into length,
pace, directness, warmth, and a hesitation flag.  It never emits literal
user-visible text, never inserts a fixed opening/hesitation prefix, and makes one
decision per turn.  Surface repetition is controlled by a bounded four-signature
style ring: when a candidate structural signature matches either of the last two
turns, hesitation becomes false and the length moves one bucket shorter.

Pure stdlib float math over immutable tuples: no I/O, no clocks, no randomness.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..canonical import assert_exact_type
from ..contracts import Action
from ..formula_v1 import (
    CLARIFY_EXPRESSION,
    CLARIFY_HESITATION_UNCERTAINTY_THRESHOLD,
    CLARIFY_WARMTH_COEFFS,
    EXPRESSION_LENGTH_BUCKETS,
    HOLD_EXPRESSION,
    OBSERVATION_DIM,
    REACH_AFFILIATION_MEDIUM_THRESHOLD,
    REACH_EXPRESSION,
    REACH_WARMTH_COEFFS,
    SPEAK_DIRECTNESS_COEFFS,
    SPEAK_LENGTH_THRESHOLDS,
    SPEAK_PACE_COEFFS,
    SPEAK_WARMTH_COEFFS,
    STYLE_REPEAT_SUPPRESSION_LOOKBACK,
    STYLE_SIGNATURE_RING_CAPACITY,
)

# Length-bucket codes (index into EXPRESSION_LENGTH_BUCKETS).
_NONE, _SHORT, _MEDIUM, _LONG = 0, 1, 2, 3
_ACTION_CODE = {Action.SPEAK: 0, Action.HOLD: 1, Action.CLARIFY: 2, Action.REACH: 3}
_DIRECTNESS_BUCKET_SCALE = 4


def _clip01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _center(value: float) -> float:
    return 2.0 * value - 1.0


@dataclass(frozen=True, slots=True)
class ExpressionConstraints:
    """Bounded, text-free expression constraints for one turn."""

    action: Action
    length_bucket: str
    pace: float
    directness: float
    warmth: float
    hesitation: bool
    style_signature: tuple

    def __post_init__(self) -> None:
        assert_exact_type(self.action, Action, "action")
        assert_exact_type(self.length_bucket, str, "length_bucket")
        if self.length_bucket not in EXPRESSION_LENGTH_BUCKETS:
            raise ValueError("length_bucket must be a declared bucket")
        for name in ("pace", "directness", "warmth"):
            value = getattr(self, name)
            assert_exact_type(value, float, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must lie in [0,1]")
        assert_exact_type(self.hesitation, bool, "hesitation")
        assert_exact_type(self.style_signature, tuple, "style_signature")
        if len(self.style_signature) != 4:
            raise ValueError("style_signature must have four fields")
        for value in self.style_signature:
            assert_exact_type(value, int, "style_signature entry")
            if not 0 <= value <= 255:
                raise ValueError("style_signature buckets must be unsigned 8-bit")


def _directness_bucket(directness: float) -> int:
    return int(round(directness * _DIRECTNESS_BUCKET_SCALE))


def _speak_length_code(expression_pressure: float) -> int:
    low, high = SPEAK_LENGTH_THRESHOLDS
    if expression_pressure < low:
        return _SHORT
    if expression_pressure < high:
        return _MEDIUM
    return _LONG


def _base_constraints(action: Action, s: tuple, frame_values: tuple, valid_mask: int) -> tuple:
    """Return ``(length_code, pace, directness, warmth, desired_hesitation)``."""

    valence, arousal, safety, affiliation, uncertainty, novelty, agency, expression_pressure = s
    if action is Action.HOLD:
        length, pace, directness, warmth, _ = HOLD_EXPRESSION
        return _NONE, float(pace), float(directness), float(warmth), False
    if action is Action.SPEAK:
        length_code = _speak_length_code(expression_pressure)
        base_p, w_arousal, w_exhaustion = SPEAK_PACE_COEFFS
        # Channel 10 (exhaustion) is a raw observation: gate it by valid_mask so an
        # invalid/missing channel contributes zero rather than leaking its semantic
        # default (0.0 -> center -1.0) as if it were real fatigue evidence (design §7).
        exhaustion_center = _center(frame_values[10]) if (valid_mask >> 10) & 1 else 0.0
        pace = _clip01(base_p + w_arousal * arousal + w_exhaustion * exhaustion_center)
        base_d, w_agency, w_uncertainty = SPEAK_DIRECTNESS_COEFFS
        directness = _clip01(base_d + w_agency * agency + w_uncertainty * uncertainty)
        base_w, w_affiliation, w_valence = SPEAK_WARMTH_COEFFS
        warmth = _clip01(base_w + w_affiliation * affiliation + w_valence * valence)
        return length_code, pace, directness, warmth, False
    if action is Action.CLARIFY:
        _bucket, pace, directness = CLARIFY_EXPRESSION
        base_w, w_affiliation = CLARIFY_WARMTH_COEFFS
        warmth = _clip01(base_w + w_affiliation * affiliation)
        desired = uncertainty > CLARIFY_HESITATION_UNCERTAINTY_THRESHOLD
        return _SHORT, float(pace), float(directness), warmth, desired
    if action is Action.REACH:
        _bucket, pace, directness = REACH_EXPRESSION
        length_code = _SHORT if affiliation < REACH_AFFILIATION_MEDIUM_THRESHOLD else _MEDIUM
        base_w, w_affiliation = REACH_WARMTH_COEFFS
        warmth = _clip01(base_w + w_affiliation * affiliation)
        return length_code, float(pace), float(directness), warmth, False
    raise ValueError("unsupported action for expression policy")


def expression_policy(
    action: object,
    decision_state: tuple,
    frame_values: tuple,
    style_ring: tuple,
    valid_mask: int = (1 << OBSERVATION_DIM) - 1,
) -> ExpressionConstraints:
    """Compute this turn's expression constraints and its final style signature.

    ``valid_mask`` is the observation frame's 36-bit validity mask; it gates the one
    raw-observation read in this policy (channel 10, exhaustion). It defaults to
    all-valid for callers holding a fully-valid frame; the orchestrator passes the
    real mask so a missing channel cannot leak its semantic default into pace.
    """

    if type(action) is not Action:
        raise TypeError("action must have exact type Action")
    if type(decision_state) is not tuple or len(decision_state) != 8:
        raise ValueError("decision_state must have exactly 8 entries")
    if type(frame_values) is not tuple or len(frame_values) < 36:
        raise ValueError("frame_values must be the 36 normalized observation values")
    if type(style_ring) is not tuple:
        raise TypeError("style_ring must be a tuple")
    if type(valid_mask) is not int:
        raise TypeError("valid_mask must be an int")

    length_code, pace, directness, warmth, desired_hesitation = _base_constraints(
        action, decision_state, frame_values, valid_mask
    )
    directness_bucket = _directness_bucket(directness)
    action_code = _ACTION_CODE[action]
    candidate_signature = (
        action_code,
        1 if desired_hesitation else 0,
        length_code,
        directness_bucket,
    )

    last_two = tuple(style_ring[-STYLE_REPEAT_SUPPRESSION_LOOKBACK:])
    suppressed = candidate_signature in last_two
    if suppressed:
        hesitation = False
        length_code = length_code - 1 if length_code >= _SHORT + 1 else length_code
        length_code = max(_SHORT, length_code) if action is not Action.HOLD else _NONE
    else:
        hesitation = desired_hesitation

    final_signature = (
        action_code,
        1 if hesitation else 0,
        length_code,
        directness_bucket,
    )
    return ExpressionConstraints(
        action=action,
        length_bucket=EXPRESSION_LENGTH_BUCKETS[length_code],
        pace=pace,
        directness=directness,
        warmth=warmth,
        hesitation=hesitation,
        style_signature=final_signature,
    )


def next_style_ring(style_ring: tuple, signature: tuple) -> tuple:
    """Append a signature and keep only the last four (design section 12)."""

    if type(style_ring) is not tuple:
        raise TypeError("style_ring must be a tuple")
    if type(signature) is not tuple or len(signature) != 4:
        raise ValueError("signature must have four fields")
    return tuple((style_ring + (signature,))[-STYLE_SIGNATURE_RING_CAPACITY:])


__all__ = ["ExpressionConstraints", "expression_policy", "next_style_ring"]
