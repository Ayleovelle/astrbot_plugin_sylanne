"""formula v2 label-free reaction signal (``ReactionSignalV1``).

Section 1 of the 2026-07-18 label-free reaction-learning spec.  The user's ``t+1``
message is the real causal consequence of turn ``t``'s *executed* interaction, so
its tone / engagement / length / latency features score how the user reacted
WITHOUT knowing which action the core chose.  This is the Slice A deliverable: the
reaction-signal pure function, its frozen result DTO, and the gap attenuator.

It reads only four channels of the ``t+1`` :class:`ObservationFrame` -- 18
(text.length), 25 (text.valence_cue), 26 (text.engagement_cue), 31 (gap_seconds).
It never sees an :class:`Action`, a shadow decision, or any identity: the signal
is label-free by construction (§4.1 guarantee 2).

Latency is a DAMPER, never evidence (§1.3): a gap up to ~5.5 min keeps full
weight, a gap beyond ~71 min clears the weight and censors the reaction, and a
missing gap channel takes the neutral ``1.0`` (a declared noise exposure).  The
length term is a deviation from the user's *own* rolling baseline and is inert
until ``REACT_WARMUP_COUNT`` valid samples have accumulated; at least one of
valence / engagement must be present for any tone evidence to exist.

Fail-closed: whenever the signal is not admissible the result is an explicit
INVALID (reason set, ``r_react`` exactly ``0.0``), never a dirty value.  Every
consumer MUST gate on :attr:`ReactionResult.valid` -- a valid reaction may itself
be ``0.0`` (a genuinely neutral reaction), so the scalar alone is not a
discriminator.

Pure stdlib float math over immutable tuples: no NumPy, no I/O, no clocks.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from ..canonical import assert_exact_type
from ..contracts import TurnContextClass
from ..formula_v1 import (
    LF_REACTION_CONTEXTS,
    REACT_GAP_ATTEN_HI,
    REACT_GAP_ATTEN_LO,
    REACT_LEN_GAIN,
    REACT_W_ENGAGEMENT,
    REACT_W_LENGTH,
    REACT_W_VALENCE,
    REACT_WARMUP_COUNT,
    REACTION_INVALID_REASONS,
    REACTION_REASON_NO_TONE_EVIDENCE,
    REACTION_REASON_NOT_INBOUND,
    REACTION_REASON_SENDER_MISMATCH,
    REACTION_REASON_STALE_REACTION,
    REACTION_REASON_VALID,
    REACTION_REASONS,
)
from ..observation.models import ObservationFrame


# Channel indices in the design section-7 normalization schema.
_LENGTH_CHANNEL = 18
_VALENCE_CHANNEL = 25
_ENGAGEMENT_CHANNEL = 26
_GAP_CHANNEL = 31

# The inbound contexts that admit a reaction, resolved to their enum members once.
_REACTION_CONTEXTS = frozenset(TurnContextClass(name) for name in LF_REACTION_CONTEXTS)
_INVALID_REASONS = frozenset(REACTION_INVALID_REASONS)


def _clip(value: float, low: float, high: float) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


@dataclass(frozen=True, slots=True)
class ReactionResult:
    """One reaction signal: a validity bit, a closed reason, and the scalar.

    Fail-closed contract: ``valid`` is true iff ``reason`` is ``VALID``; an invalid
    result carries ``r_react == 0.0`` exactly.  A valid reaction may legitimately be
    ``0.0``, so consumers discriminate on :attr:`valid`, never on the scalar.
    """

    valid: bool
    reason: str
    r_react: float

    def __post_init__(self) -> None:
        assert_exact_type(self.valid, bool, "valid")
        assert_exact_type(self.reason, str, "reason")
        assert_exact_type(self.r_react, float, "r_react")
        if self.reason not in REACTION_REASONS:
            raise ValueError("reason must be a declared reaction reason")
        if not isfinite(self.r_react):
            raise ValueError("r_react must be finite")
        if not -1.0 <= self.r_react <= 1.0:
            raise ValueError("r_react must lie in [-1,1]")
        if self.valid != (self.reason == REACTION_REASON_VALID):
            raise ValueError("valid must be true iff reason is VALID")
        if not self.valid and self.r_react != 0.0:
            raise ValueError("an invalid reaction must fail closed with r_react 0.0")


def _invalid(reason: str) -> ReactionResult:
    return ReactionResult(valid=False, reason=reason, r_react=0.0)


def gap_attenuation(gap_valid: bool, u_gap: float) -> float:
    """Latency attenuator in ``[0,1]`` -- latency is a damper, never evidence (§1.3).

    Full weight (``1.0``) at or below :data:`REACT_GAP_ATTEN_LO` (~5.5 min), ramping
    linearly to ``0.0`` at or above :data:`REACT_GAP_ATTEN_HI` (~71 min).  A missing
    gap channel is a declared noise exposure and takes the neutral ``1.0``.
    """

    assert_exact_type(gap_valid, bool, "gap_valid")
    if not gap_valid:
        return 1.0
    assert_exact_type(u_gap, float, "u_gap")
    span = REACT_GAP_ATTEN_HI - REACT_GAP_ATTEN_LO
    ramp = _clip((u_gap - REACT_GAP_ATTEN_LO) / span, 0.0, 1.0)
    return 1.0 - ramp


def reaction_signal(
    frame: ObservationFrame,
    context: TurnContextClass,
    len_baseline: float,
    reaction_count: int,
    same_sender: bool | None,
) -> ReactionResult:
    """Score the ``t+1`` inbound reaction to turn ``t`` from four u' channels.

    ``len_baseline`` / ``reaction_count`` are the caller-resolved label-free state
    scalars (``None`` label_free state resolves to :data:`LEN_BASELINE_INIT` and
    ``0``; that resolution belongs to the Slice C caller, not this pure function).
    ``same_sender`` is the bridge's frozen relational fact: ``False`` censors, and
    ``None`` (bridge could not decide) is admitted as declared group-chat noise.
    """

    if type(frame) is not ObservationFrame:
        raise TypeError("frame must have exact type ObservationFrame")
    assert_exact_type(context, TurnContextClass, "context")
    assert_exact_type(len_baseline, float, "len_baseline")
    assert_exact_type(reaction_count, int, "reaction_count")
    assert_exact_type(same_sender, (bool, type(None)), "same_sender")
    if not isfinite(len_baseline) or not 0.0 <= len_baseline <= 1.0:
        raise ValueError("len_baseline must be a normalized value in [0,1]")
    if reaction_count < 0:
        raise ValueError("reaction_count must be non-negative")

    # Gate order is the declared reason precedence (§1.2 / §2.4).
    if context not in _REACTION_CONTEXTS:
        return _invalid(REACTION_REASON_NOT_INBOUND)
    if same_sender is False:
        return _invalid(REACTION_REASON_SENDER_MISMATCH)

    values = frame.values
    weights: list[float] = []
    contributions: list[float] = []
    has_tone = False

    if frame.is_valid(_VALENCE_CHANNEL):
        weights.append(REACT_W_VALENCE)
        contributions.append(2.0 * values[_VALENCE_CHANNEL] - 1.0)
        has_tone = True
    if frame.is_valid(_ENGAGEMENT_CHANNEL):
        weights.append(REACT_W_ENGAGEMENT)
        contributions.append(2.0 * values[_ENGAGEMENT_CHANNEL] - 1.0)
        has_tone = True
    if frame.is_valid(_LENGTH_CHANNEL) and reaction_count >= REACT_WARMUP_COUNT:
        weights.append(REACT_W_LENGTH)
        contributions.append(
            _clip(REACT_LEN_GAIN * (values[_LENGTH_CHANNEL] - len_baseline), -1.0, 1.0)
        )

    # Valence / engagement is the only admissible tone evidence; length alone is not.
    if not has_tone:
        return _invalid(REACTION_REASON_NO_TONE_EVIDENCE)

    total_weight = sum(weights)  # >= REACT_W_ENGAGEMENT > 0 because has_tone holds
    r_raw = sum(weight * value for weight, value in zip(weights, contributions)) / total_weight

    a_gap = gap_attenuation(frame.is_valid(_GAP_CHANNEL), values[_GAP_CHANNEL])
    if a_gap == 0.0:
        return _invalid(REACTION_REASON_STALE_REACTION)

    r_react = _clip(_clip(r_raw, -1.0, 1.0) * a_gap, -1.0, 1.0)
    return ReactionResult(valid=True, reason=REACTION_REASON_VALID, r_react=r_react)


__all__ = ["ReactionResult", "gap_attenuation", "reaction_signal"]
