"""Pure one-time v2 seeding: SeedFrame -> initial 24-dim latent -> V3State.

This module is strictly pure ``v3core``.  It imports no v2 or bridge type: the
bridge is responsible for reading the authoritative ``V2SeedSnapshotV1`` and
projecting it into an already-sanitized, core-owned :class:`SeedFrame` of plain
bounded values.  The projector then maps those values onto the 24-dimensional
continuous latent state (design section 15.2).

Every seed field is an already-centered deviation whose neutral value is ``0.0``:
a missing (``None``) fact and a present ``0.0`` fact both contribute nothing, so
neutral or missing input projects byte-identically to the all-zero neutral seed.
Any non-finite or wrong-typed field fails closed at :class:`SeedFrame`
construction.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, fields
from math import isfinite

from ..contracts import SessionRef
from ..formula_v1 import STATE_DIM
from .models import LATENT_DIM, STYLE_SIGNATURE_FIELDS, STYLE_RING_CAPACITY, V3State


SEED_LATENT_BOUND = 1.0

# The 24 latent axes are laid out as three contiguous timescale blocks
# ``[fast(0..7), mid(8..15), slow(16..23)]`` in axis order
# (valence, arousal, safety, affiliation, uncertainty, novelty, agency,
# expression_pressure).  Only the axes named by design 15.2 receive a seed; the
# rest stay at the neutral zero fixed point.
_FAST = 0
_MID = 8
_SLOW = 16
_VALENCE, _AROUSAL, _SAFETY, _AFFILIATION, _UNCERTAINTY = 0, 1, 2, 3, 4
_AGENCY = 6

# (latent_index, seed_frame_field) mapping.  Each maps one deviation onto exactly
# one latent axis so a single fact moves a single coordinate.
SEED_AXIS_MAP = (
    (_FAST + _AFFILIATION, "bond"),
    (_FAST + _UNCERTAINTY, "hesitation"),
    (_FAST + _VALENCE, "emotion_valence_fast"),
    (_FAST + _AROUSAL, "emotion_arousal_fast"),
    (_FAST + _SAFETY, "emotion_safety_fast"),
    (_MID + _VALENCE, "emotion_valence_slow"),
    (_MID + _AROUSAL, "emotion_arousal_slow"),
    (_MID + _SAFETY, "emotion_safety_slow"),
    (_SLOW + _AFFILIATION, "narrative"),
    (_SLOW + _AGENCY, "ossification"),
)

_SEED_FIELD_NAMES = tuple(name for _, name in SEED_AXIS_MAP)


def _to_half(value: float) -> float:
    """Snap to the float16 grid the codec persists so seeded state round-trips."""

    return struct.unpack(">e", struct.pack(">e", value))[0]


@dataclass(frozen=True, slots=True)
class SeedFrame:
    """Core-owned, sanitized projection of v2 seed facts (never a v2 DTO).

    Each fact is a signed deviation centered at ``0.0``; ``None`` means the fact
    was missing.  ``style_signature_seed`` optionally seeds one initial style
    ring signature.
    """

    bond: float | None = None
    hesitation: float | None = None
    emotion_valence_fast: float | None = None
    emotion_arousal_fast: float | None = None
    emotion_safety_fast: float | None = None
    emotion_valence_slow: float | None = None
    emotion_arousal_slow: float | None = None
    emotion_safety_slow: float | None = None
    narrative: float | None = None
    ossification: float | None = None
    style_signature_seed: tuple | None = None

    def __post_init__(self) -> None:
        for descriptor in fields(self):
            if descriptor.name == "style_signature_seed":
                continue
            value = getattr(self, descriptor.name)
            if value is None:
                continue
            if type(value) is not float:
                raise TypeError(f"{descriptor.name} must be a float deviation or None")
            if not isfinite(value):
                raise ValueError(f"{descriptor.name} must be finite")
        if self.style_signature_seed is not None:
            if type(self.style_signature_seed) is not tuple:
                raise TypeError("style_signature_seed must be a tuple or None")
            if len(self.style_signature_seed) != STYLE_SIGNATURE_FIELDS:
                raise ValueError("style_signature_seed must have the fixed field count")
            for bucket in self.style_signature_seed:
                if type(bucket) is not int or not 0 <= bucket <= 255:
                    raise ValueError("style_signature_seed buckets must be unsigned 8-bit ints")


def neutral_seed_frame() -> SeedFrame:
    """The all-missing seed frame that projects to the neutral state."""

    return SeedFrame()


def _clip(value: float) -> float:
    if value > SEED_LATENT_BOUND:
        return SEED_LATENT_BOUND
    if value < -SEED_LATENT_BOUND:
        return -SEED_LATENT_BOUND
    return value


class SeedProjector:
    """Pure projector from a :class:`SeedFrame` to the initial :class:`V3State`."""

    def project_latent(self, frame: object) -> tuple:
        """Project the seed frame onto exactly 24 bounded latent values."""

        if type(frame) is not SeedFrame:
            raise TypeError("project_latent requires a SeedFrame")
        latent = [0.0] * LATENT_DIM
        for axis_index, field_name in SEED_AXIS_MAP:
            value = getattr(frame, field_name)
            if value is None:
                continue
            latent[axis_index] = _to_half(_clip(value))
        assert len(latent) == STATE_DIM == LATENT_DIM
        return tuple(latent)

    def build_initial_state(
        self,
        frame: object,
        *,
        session_ref: SessionRef,
        state_generation_id: str,
        source_digest: str,
        session_generation: int = 0,
        writer_epoch: int = 0,
    ) -> V3State:
        """Build a complete neutral-payload initial state from a seed frame.

        The continuous latent axes carry the seed projection; the SNN and action
        beliefs are absent (per-session deviations from the shared immutable model
        start empty), no pending credit exists, the experience buffer is empty,
        and the refractory scalars start at zero per the frozen formula manifest.
        """

        if type(frame) is not SeedFrame:
            raise TypeError("build_initial_state requires a SeedFrame")
        latent = self.project_latent(frame)
        style_ring: tuple = ()
        if frame.style_signature_seed is not None:
            style_ring = (tuple(frame.style_signature_seed),)[:STYLE_RING_CAPACITY]
        return V3State(
            session_ref=session_ref,
            state_generation_id=state_generation_id,
            source_digest=source_digest,
            revision=0,
            writer_epoch=writer_epoch,
            session_generation=session_generation,
            latent_axes=latent,
            rho_hold=0.0,
            rho_reach=0.0,
            style_ring=style_ring,
            snn=None,
            action_beliefs=None,
            last_snn_summary=None,
            pending_outcome=None,
            experiences=(),
        )


__all__ = [
    "SEED_AXIS_MAP",
    "SEED_LATENT_BOUND",
    "SeedFrame",
    "SeedProjector",
    "neutral_seed_frame",
]
