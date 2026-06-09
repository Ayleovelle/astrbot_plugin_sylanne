"""Integration Bridge: Layer 0 <-> Full Engine natural transformation.

Implements a natural transformation (Mac Lane 1971) between the Layer 0
functor (SylanneCore -> SylanneState) and the full computation functor
(SylanneEngine -> Surface). This enables third-party implementations to:

- Feed SylanneCore output into PADProjector
- Convert full engine Surface to Layer 0 format
- Round-trip between representations
- Produce JSON-serializable interchange format

Axiom preservation:
- A1 (boundedness): all outputs clamped to valid ranges
- A2 (determinism): same input always produces same output
- A5 (compositionality): bridge operations compose with kernel operations

Theoretical basis:
  The bridge is a natural transformation eta: F => G where
  F = Layer 0 functor (SylanneCore.process)
  G = Full engine functor (SylanneEngine.process composed with PAD projection)
  Naturality square commutes up to clamping at boundaries.
"""

from __future__ import annotations

from typing import Any

from .compute.pad_interop import PADProjector, PADVector
from .standard import EmotionVector, SylanneState
from .types import Surface


def state_to_pad(
    state: SylanneState,
    projector: PADProjector | None = None,
) -> PADVector:
    """Map a Layer 0 SylanneState to PAD 3D space.

    The Layer 0 state already lives in PAD space (valence/arousal/dominance),
    so this is a direct extraction from the primary vector. When a projector
    is provided, it is used for consistency with the full engine's projection
    pipeline (applying personality modulation and bias terms).

    Args:
        state: Layer 0 kernel output (SylanneState).
        projector: Optional PADProjector for personality-modulated projection.
            If None, extracts PAD directly from state.primary.

    Returns:
        PADVector with values clamped to valid ranges.

    Preserves:
        - A1: PADVector.__post_init__ enforces bounds
        - A2: pure function, no side effects
        - A5: composes with SylanneCore.process
    """
    if projector is not None:
        # Use the projector's forward mapping for consistency with full engine.
        # Layer 0 state has 3 dims (V/A/D); pad them to projector's n_dims
        # using the primary vector as the first 3 dimensions.
        vec = [state.primary.valence, state.primary.arousal, state.primary.dominance]
        # Pad to projector's expected dimensionality with zeros
        if projector.n_dims > 3:
            vec.extend([0.0] * (projector.n_dims - 3))
        return projector.project(vec)

    # Direct extraction: Layer 0 primary IS already in PAD space
    return PADVector(
        valence=state.primary.valence,
        arousal=state.primary.arousal,
        dominance=state.primary.dominance,
    )


def surface_to_layer0(surface: Surface) -> SylanneState:
    """Convert a full engine Surface output to Layer 0 SylanneState.

    Extracts the affective state from the Surface and maps it to the
    Layer 0 representation. The 8-dim internal state is collapsed to
    3D PAD via the Surface's pad field, then wrapped as a SylanneState.

    This is the right adjoint of the bridge: it forgets fine-grained
    information (information loss is intentional at the interchange boundary).

    Args:
        surface: Full engine Surface output.

    Returns:
        SylanneState with primary/mood derived from Surface PAD output.

    Preserves:
        - A1: EmotionVector values clamped by _clamp_vector semantics
        - A2: pure function
        - A5: result can be fed back into SylanneCore pipeline
    """
    pad = surface.get("pad", {})
    state_data = surface.get("state", {})
    valence_data = state_data.get("valence", {})
    rhythm_data = state_data.get("rhythm", {})

    # Primary: from PAD output (the projected affective state)
    primary = EmotionVector(
        valence=max(-1.0, min(1.0, float(pad.get("valence", 0.0)))),
        arousal=max(0.0, min(1.0, float(pad.get("arousal", 0.0)))),
        dominance=max(0.0, min(1.0, float(pad.get("dominance", 0.5)))),
    )

    # Mood: approximate from body state (warmth as valence proxy,
    # rhythm stability as arousal proxy, boundary autonomy as dominance proxy)
    boundary_data = state_data.get("boundary", {})
    mood = EmotionVector(
        valence=max(-1.0, min(1.0, (float(valence_data.get("warmth", 0.45)) - 0.5) * 2.0)),
        arousal=max(0.0, min(1.0, float(rhythm_data.get("stability", 0.5)))),
        dominance=max(0.0, min(1.0, float(boundary_data.get("autonomy", 0.5)))),
    )

    # Delta: zero (not available from Surface; represents last change)
    delta = EmotionVector(0.0, 0.0, 0.0)

    # Confidence from PAD output
    confidence = max(0.0, min(1.0, float(pad.get("confidence", 0.5))))

    # Epoch from turns
    epoch = int(surface.get("turns", 0))

    return SylanneState(
        primary=primary,
        mood=mood,
        delta=delta,
        confidence=confidence,
        epoch=epoch,
    )


def layer0_to_interchange(state: SylanneState) -> dict[str, Any]:
    """Convert Layer 0 SylanneState to JSON-serializable interchange format.

    Produces a flat dictionary suitable for:
    - REST API responses
    - WebSocket messages
    - Cross-language serialization
    - Database storage

    The interchange format is the canonical wire representation for
    Layer 0 state. Any SPEC-conformant implementation can consume it.

    Args:
        state: Layer 0 kernel output.

    Returns:
        JSON-serializable dict with all state fields.

    Preserves:
        - A1: values already bounded by SylanneState invariants
        - A2: pure function
        - A5: round-trips with interchange_to_layer0 (lossless)
    """
    return {
        "version": "sylanne.interchange.v1",
        "primary": {
            "valence": state.primary.valence,
            "arousal": state.primary.arousal,
            "dominance": state.primary.dominance,
        },
        "mood": {
            "valence": state.mood.valence,
            "arousal": state.mood.arousal,
            "dominance": state.mood.dominance,
        },
        "delta": {
            "valence": state.delta.valence,
            "arousal": state.delta.arousal,
            "dominance": state.delta.dominance,
        },
        "confidence": state.confidence,
        "epoch": state.epoch,
        "pad": {
            "valence": state.primary.valence,
            "arousal": state.primary.arousal,
            "dominance": state.primary.dominance,
        },
    }
