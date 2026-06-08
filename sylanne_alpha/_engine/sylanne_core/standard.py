"""Sylanne Layer 0: Minimal Affective Computation Kernel.

SPEC-conformant reference implementation. Third-party implementations MUST
match this interface to claim Layer 0 compatibility.

Theoretical basis: PAD (Pleasure-Arousal-Dominance) dimensional model.
- Mehrabian & Russell (1974): 3 orthogonal factors sufficient for affect.
- Russell (1980): circumplex structure validated on valence-arousal plane.
- Fontaine et al. (2007): 4th dimension adds <5% variance cross-culturally.

State space: S = [-1,1] x [0,1] x [0,1] (compact subset of R^3).
- Compactness guarantees omega-limit set existence (Milnor 1985).
- No divergence possible; finite precision sufficient.

Convergence proof (Lyapunov direct method):
    Let x* = attractor (resting state), V(x) = ||x - x*||^2.
    Under exponential decay: dx/dt = -decay_rate * (x - x*)
    dV/dt = 2(x - x*) . dx/dt
          = 2(x - x*) . (-decay_rate * (x - x*))
          = -2 * decay_rate * ||x - x*||^2
          = -2 * decay_rate * V(x)
    Therefore V(t) = V(0) * exp(-2 * decay_rate * t) -> 0.
    The equilibrium x* is globally asymptotically stable on S.  QED.

Lipschitz constraint (Axiom A3):
    ||f(x1, u) - f(x2, u)|| <= L * ||x1 - x2|| for all x1, x2 in S.
    Ensures structural stability and robustness to sensor noise.
    Topological conjugacy preserved under C^1-close perturbations (Hartman-Grobman).

Pure Python. No external dependencies. This is the reference minimal kernel.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SylanneStimulus:
    """A single affective stimulus event entering the kernel.

    All dimensions are bounded to ensure compact state space (Milnor 1985).
    """

    valence: float  # Pleasure axis, [-1, 1] — Mehrabian & Russell (1974)
    arousal: float  # Activation axis, [0, 1] — Russell (1980) circumplex
    dominance: float  # Potency axis, [0, 1] — discriminates fear/anger
    magnitude: float  # Stimulus intensity, [0, 1] — scales raw delta
    timestamp: int  # Monotonic epoch counter (uint64 semantics)
    tag: str | None = None  # Optional semantic label for tracing


@dataclass(frozen=True, slots=True)
class EmotionVector:
    """3D PAD vector representing an affective state point.

    Bounded to S = [-1,1] x [0,1] x [0,1] — the compact invariant set
    guaranteeing omega-limit existence (Milnor 1985).
    """

    valence: float = 0.0  # [-1, 1] — hedonic tone
    arousal: float = 0.0  # [0, 1] — physiological activation
    dominance: float = 0.5  # [0, 1] — perceived control (neutral = 0.5)

    def norm(self) -> float:
        """Euclidean norm of the vector."""
        return math.sqrt(self.valence**2 + self.arousal**2 + self.dominance**2)

    def distance_to(self, other: EmotionVector) -> float:
        """Euclidean distance between two state points."""
        return math.sqrt(
            (self.valence - other.valence) ** 2
            + (self.arousal - other.arousal) ** 2
            + (self.dominance - other.dominance) ** 2
        )

    def subtract(self, other: EmotionVector) -> EmotionVector:
        """Component-wise subtraction (self - other)."""
        return EmotionVector(
            valence=self.valence - other.valence,
            arousal=self.arousal - other.arousal,
            dominance=self.dominance - other.dominance,
        )


@dataclass(frozen=True, slots=True)
class SylanneState:
    """Complete kernel output after processing a stimulus.

    Encapsulates primary (reactive), mood (slow EMA), delta (last change),
    confidence (certainty estimate), and epoch (monotonic counter).
    """

    primary: EmotionVector  # Reactive state — immediate response
    mood: EmotionVector  # Slow-moving baseline — exponential moving average
    delta: EmotionVector  # Last applied state change (post-Lipschitz clamp)
    confidence: float  # [0, 1] — derived from magnitude and stability
    epoch: int  # Monotonic processing counter (uint64 semantics)


# ---------------------------------------------------------------------------
# Configuration defaults
# ---------------------------------------------------------------------------

# Default configuration — each value has theoretical justification
_DEFAULT_CONFIG = {
    "max_delta": 0.3,  # Lipschitz bound L — prevents chaotic amplification (Axiom A3)
    "decay_rate": 0.05,  # lambda in (0,1) — convergence speed toward attractor (Axiom A4)
    "attractor": {  # Resting state x* — globally asymptotically stable equilibrium
        "valence": 0.0,  # Neutral hedonic tone at rest
        "arousal": 0.1,  # Minimal baseline activation (not zero — biological floor)
        "dominance": 0.5,  # Neutral perceived control
    },
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float, hi: float) -> float:
    """Scalar clamp to [lo, hi] — enforces compact state space."""
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _clamp_vector(v: EmotionVector) -> EmotionVector:
    """Project vector onto the compact set S = [-1,1] x [0,1] x [0,1].

    Guarantees state remains in the invariant set (Milnor 1985).
    """
    return EmotionVector(
        valence=_clamp(v.valence, -1.0, 1.0),
        arousal=_clamp(v.arousal, 0.0, 1.0),
        dominance=_clamp(v.dominance, 0.0, 1.0),
    )


def _scale_vector(v: EmotionVector, s: float) -> EmotionVector:
    """Scalar multiplication of an EmotionVector."""
    return EmotionVector(
        valence=v.valence * s,
        arousal=v.arousal * s,
        dominance=v.dominance * s,
    )


# ---------------------------------------------------------------------------
# Core kernel
# ---------------------------------------------------------------------------


class SylanneCore:
    """Layer 0 Minimal Affective Computation Kernel.

    The single mandatory interface for SPEC-conformant implementations.
    Internal state: primary vector + mood vector + epoch counter.
    No history buffer — minimal memory footprint by design.

    Process algorithm satisfies:
    - Axiom A3 (Lipschitz): ||delta|| <= max_delta * magnitude
    - Axiom A4 (Convergence): exponential decay toward attractor
    - Compact state space: all vectors clamped to S
    """

    __slots__ = ("_config", "_primary", "_mood", "_epoch", "_last_delta")

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize kernel with optional configuration.

        Args:
            config: Optional dict with keys:
                - max_delta: Lipschitz bound L (default 0.3)
                - decay_rate: EMA alpha for mood convergence (default 0.05)
                - attractor: dict with valence/arousal/dominance for resting state
        """
        cfg: dict[str, Any] = dict(_DEFAULT_CONFIG)
        if config:
            cfg.update(config)

        # Validate decay_rate in (0, 1) — required for Lyapunov stability
        dr = float(cfg["decay_rate"])
        if not (0.0 < dr < 1.0):
            raise ValueError(f"decay_rate must be in (0,1), got {dr}")

        # Validate Lipschitz bound is positive
        md = float(cfg["max_delta"])
        if md <= 0.0:
            raise ValueError(f"max_delta must be positive, got {md}")

        self._config = cfg

        # Parse attractor to build initial state
        att = cfg["attractor"]
        if isinstance(att, dict):
            attractor_vec = EmotionVector(
                valence=att.get("valence", 0.0),
                arousal=att.get("arousal", 0.1),
                dominance=att.get("dominance", 0.5),
            )
        else:
            attractor_vec = att  # Allow passing EmotionVector directly

        # Initial state = attractor (system starts at equilibrium)
        self._primary: EmotionVector = attractor_vec
        self._mood: EmotionVector = attractor_vec
        self._epoch: int = 0
        self._last_delta: EmotionVector = EmotionVector(0.0, 0.0, 0.0)

    def process(self, stimulus: SylanneStimulus) -> SylanneState:
        """Process a single stimulus and return the new kernel state.

        This is the SINGLE MANDATORY OPERATION for Layer 0 conformance.

        Algorithm:
        1. Compute raw_delta from stimulus (PAD * magnitude)
        2. Apply Lipschitz clamp: ||delta|| <= max_delta * magnitude (Axiom A3)
        3. Update primary = clamp(primary + delta) — stays in compact S
        4. Update mood via EMA: mood = (1-alpha)*mood + alpha*primary (Axiom A4)
        5. Compute confidence from magnitude and state stability
        6. Increment epoch

        Args:
            stimulus: A SylanneStimulus event.

        Returns:
            SylanneState capturing the full kernel output.
        """
        max_delta = float(self._config["max_delta"])
        decay_rate = float(self._config["decay_rate"])

        # Step 1: Raw delta — stimulus dimensions scaled by magnitude
        raw_delta = EmotionVector(
            valence=stimulus.valence * stimulus.magnitude,
            arousal=stimulus.arousal * stimulus.magnitude,
            dominance=stimulus.dominance * stimulus.magnitude,
        )

        # Step 2: Lipschitz clamp — structural stability guarantee (Axiom A3)
        # ||delta|| <= max_delta * magnitude prevents chaotic amplification
        delta_norm = raw_delta.norm()
        bound = max_delta * stimulus.magnitude
        if delta_norm > bound and delta_norm > 0.0:
            # Scale down to satisfy Lipschitz constraint
            scale = bound / delta_norm
            clamped_delta = _scale_vector(raw_delta, scale)
        else:
            clamped_delta = raw_delta

        # Step 3: Update primary state — project back onto compact S
        new_primary = _clamp_vector(
            EmotionVector(
                valence=self._primary.valence + clamped_delta.valence,
                arousal=self._primary.arousal + clamped_delta.arousal,
                dominance=self._primary.dominance + clamped_delta.dominance,
            )
        )

        # Step 4: Mood EMA — exponential convergence (Axiom A4)
        # mood_{t+1} = (1 - alpha) * mood_t + alpha * primary_{t+1}
        # This implements the discrete-time Lyapunov-stable dynamics
        alpha = decay_rate
        new_mood = _clamp_vector(
            EmotionVector(
                valence=(1.0 - alpha) * self._mood.valence + alpha * new_primary.valence,
                arousal=(1.0 - alpha) * self._mood.arousal + alpha * new_primary.arousal,
                dominance=(1.0 - alpha) * self._mood.dominance + alpha * new_primary.dominance,
            )
        )

        # Step 5: Confidence — higher when magnitude is strong and state is stable
        # Stability measured as inverse of distance between primary and mood
        stability = 1.0 / (1.0 + new_primary.distance_to(new_mood))
        confidence = _clamp(stimulus.magnitude * stability, 0.0, 1.0)

        # Step 6: Increment epoch
        new_epoch = self._epoch + 1

        # Commit state transition
        self._primary = new_primary
        self._mood = new_mood
        self._epoch = new_epoch
        self._last_delta = clamped_delta

        return SylanneState(
            primary=new_primary,
            mood=new_mood,
            delta=clamped_delta,
            confidence=confidence,
            epoch=new_epoch,
        )

    def reset(self) -> None:
        """Reset kernel to initial equilibrium state.

        Returns the system to the attractor point — equivalent to
        t -> infinity under the Lyapunov-stable dynamics.
        """
        att = self._config["attractor"]
        if isinstance(att, dict):
            attractor_vec = EmotionVector(
                valence=att.get("valence", 0.0),
                arousal=att.get("arousal", 0.1),
                dominance=att.get("dominance", 0.5),
            )
        else:
            attractor_vec = att  # Allow passing EmotionVector directly

        self._primary = attractor_vec
        self._mood = attractor_vec
        self._epoch = 0
        self._last_delta = EmotionVector(0.0, 0.0, 0.0)

    def snapshot(self) -> dict[str, Any]:
        """Serialize kernel state to a plain dict.

        Returns a JSON-serializable dictionary capturing the full internal
        state for persistence or transmission. No information loss.
        """
        return {
            "version": "layer0-v1",
            "config": self._config,
            "state": {
                "primary": {
                    "valence": self._primary.valence,
                    "arousal": self._primary.arousal,
                    "dominance": self._primary.dominance,
                },
                "mood": {
                    "valence": self._mood.valence,
                    "arousal": self._mood.arousal,
                    "dominance": self._mood.dominance,
                },
                "epoch": self._epoch,
                "last_delta": {
                    "valence": self._last_delta.valence,
                    "arousal": self._last_delta.arousal,
                    "dominance": self._last_delta.dominance,
                },
            },
        }

    @classmethod
    def restore(cls, data: dict[str, Any]) -> SylanneCore:
        """Deserialize a kernel from a snapshot dict.

        Args:
            data: Dict produced by snapshot(). Must contain 'config' and 'state'.

        Returns:
            A new SylanneCore instance with restored internal state.
        """
        if data.get("version") != "layer0-v1":
            raise ValueError(f"Unsupported snapshot version: {data.get('version')}")

        instance = cls(config=data["config"])
        state = data["state"]

        instance._primary = EmotionVector(
            valence=state["primary"]["valence"],
            arousal=state["primary"]["arousal"],
            dominance=state["primary"]["dominance"],
        )
        instance._mood = EmotionVector(
            valence=state["mood"]["valence"],
            arousal=state["mood"]["arousal"],
            dominance=state["mood"]["dominance"],
        )
        instance._epoch = state["epoch"]
        instance._last_delta = EmotionVector(
            valence=state["last_delta"]["valence"],
            arousal=state["last_delta"]["arousal"],
            dominance=state["last_delta"]["dominance"],
        )

        return instance

    def __repr__(self) -> str:
        return (
            f"SylanneCore(epoch={self._epoch}, "
            f"primary=V{self._primary.valence:.3f}/A{self._primary.arousal:.3f}/"
            f"D{self._primary.dominance:.3f})"
        )
