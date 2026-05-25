"""Void-Scar Coupled Engine — Unified replacement for SSM + TDA layers.

Integrates Scar Algebra (irreversible state dynamics) with Void Calculus
(first-class absence computation) through bidirectional coupling:
  Γ: Void pressure → Scar wounding events
  Φ: Scar numbing → Void genesis sensitivity
"""

from __future__ import annotations

import math
from typing import Any, Callable

from .scar_algebra import ScarredState
from .void_calculus import VoidSpace


class SocialVoid:
    """Group chat silence void — pressure accumulates when agent is silent in active group."""

    __slots__ = ("pressure", "silence_ticks", "group_activity", "topic_boundary")

    def __init__(self):
        self.pressure = 0.0
        self.silence_ticks = 0
        self.group_activity = 0.0
        self.topic_boundary = 0.5

    def tick(self, group_active: bool = True):
        if not group_active:
            self.pressure *= 0.95
            return
        self.silence_ticks += 1
        depth = self.group_activity
        beta = self.topic_boundary
        if depth > 0 and self.silence_ticks > 0:
            self.pressure += (
                depth * math.log(self.silence_ticks + 1) * (1.0 - beta) * 0.1
            )
        self.pressure = min(5.0, self.pressure)

    def reset(self):
        self.silence_ticks = 0
        self.pressure *= 0.3

    def to_dict(self) -> dict:
        return {
            "pressure": self.pressure,
            "silence_ticks": self.silence_ticks,
            "group_activity": self.group_activity,
            "topic_boundary": self.topic_boundary,
        }

    def from_dict(self, data: dict):
        self.pressure = float(data.get("pressure", 0.0))
        self.silence_ticks = int(data.get("silence_ticks", 0))
        self.group_activity = float(data.get("group_activity", 0.0))
        self.topic_boundary = float(data.get("topic_boundary", 0.5))


class VoidScarEngine:
    """Coupled Void-Scar computation engine.

    Replaces the SSM (Layer 3) and TDA (Layer 4) in the computation spine.
    """

    __slots__ = (
        "scar_state",
        "void_space",
        "social_void",
        "similarity_fn",
        "_coherence",
        "_last_event_vec",
        "_tick",
        "_void_pressure_coupling_rate",
        "_void_drive_weight",
        "_social_drive_weight",
        "_accepted_decay",
        "_ignored_deepening",
        "_personality_detection_floor",
    )

    def __init__(
        self,
        n_dims: int = 8,
        wound_threshold: float = 0.6,
        similarity_fn: Callable[[bytes, bytes], float] | None = None,
        max_voids: int = 50,
        pressure_threshold: float = 10.0,
    ):
        self.scar_state = ScarredState(n_dims=n_dims, wound_threshold=wound_threshold)
        self.similarity_fn = similarity_fn or _default_similarity
        self.void_space = VoidSpace(
            similarity_fn=self.similarity_fn,
            max_voids=max_voids,
            pressure_threshold=pressure_threshold,
        )
        self.social_void = SocialVoid()
        self._coherence = 1.0
        self._last_event_vec: bytes | None = None
        self._tick = 0
        self._void_pressure_coupling_rate = 0.3
        self._void_drive_weight = 0.5
        self._social_drive_weight = 0.3
        self._accepted_decay = 0.7
        self._ignored_deepening = 0.05
        self._personality_detection_floor: float = 0.1

    def process(
        self,
        event_vec: bytes,
        ssm_input: list[float],
        surprise: float,
        timestamp: float = 0.0,
    ) -> dict[str, Any]:
        """Process one event through the coupled Void-Scar engine.

        Args:
            event_vec: HDC-encoded event (for void boundary operations)
            ssm_input: 8-dim input vector (for scar state evolution)
            surprise: surprise from predictive coding gate
            timestamp: event timestamp

        Returns:
            Combined result with scar state, void state, and coupling info.
        """
        self._tick += 1

        # Compute similarity to previous event (for void detection)
        prev_sim = 0.0
        if self._last_event_vec is not None:
            prev_sim = self.similarity_fn(event_vec, self._last_event_vec)
        self._last_event_vec = event_vec

        # --- Coupling Φ: Scars → Void sensitivity ---
        # Numbed dimensions lower void detection threshold, but respect personality floor
        numbed_count = sum(
            1 for d in range(self.scar_state.n_dims) if self.scar_state.is_numbed(d)
        )
        if numbed_count > 0:
            # Phi coupling: numbed dims lower detection threshold, but respect floor
            personality_base = self.void_space._detection_threshold
            phi_floor = self._personality_detection_floor
            phi_adjusted = max(phi_floor, personality_base - numbed_count * 0.03)
            self.void_space._detection_threshold = phi_adjusted

        # --- Void Calculus step ---
        void_result = self.void_space.process(event_vec, surprise, prev_sim)

        # --- Coupling Γ: Void pressure → Scar wounding ---
        coupling_wounds: list[dict[str, Any]] = []
        for coupling in void_result["coupling_events"]:
            wound_event = [0.0] * self.scar_state.n_dims
            dim_hint = int(coupling.get("dim_hint", 0)) % self.scar_state.n_dims
            wound_event[dim_hint] = (
                coupling["pressure"] * self._void_pressure_coupling_rate
            )
            wound_result = self.scar_state.step(wound_event, timestamp, heal=False)
            coupling_wounds.append(wound_result)

        # --- Scar Algebra step (main event) ---
        scar_result = self.scar_state.step(ssm_input, timestamp)

        # --- Compute coherence (emergent resonance) ---
        self._coherence = self._compute_coherence()

        return {
            "scar": scar_result,
            "void": void_result,
            "coupling_wounds": coupling_wounds,
            "coherence": self._coherence,
            "observation": self.observe(),
        }

    # Canonical dimension names for the 8-dim emotion space
    _DIM_NAMES: tuple[str, ...] = (
        "warmth",
        "arousal",
        "valence",
        "tension",
        "curiosity",
        "repair_pressure",
        "expression_drive",
        "boundary_firmness",
    )

    def observe(self) -> dict[str, float]:
        """Observable output for downstream layers.

        Returns named emotion dimensions (warmth, arousal, valence, tension,
        curiosity, repair_pressure, expression_drive, boundary_firmness) plus
        coherence, void_pressure, active_voids, ghost_count.
        """
        raw = self.scar_state.observe()
        obs: dict[str, float] = {}
        # Map dim_N → named dimensions
        for i, name in enumerate(self._DIM_NAMES):
            obs[name] = raw.get(f"dim_{i}", 0.0)
        # Keep sensitivity values under named keys
        for i, name in enumerate(self._DIM_NAMES):
            obs[f"sensitivity_{name}"] = raw.get(f"sensitivity_{i}", 1.0)
        obs["total_scars"] = raw.get("total_scars", 0.0)
        obs["numbed_dimensions"] = raw.get("numbed_dimensions", 0.0)
        obs["coherence"] = self._coherence
        obs["void_pressure"] = self.void_space.total_pressure()
        obs["active_voids"] = float(len(self.void_space.voids))
        obs["ghost_count"] = float(len(self.void_space.ghosts))
        return obs

    def expression_drive(self) -> float:
        """Combined drive for the phase transition expression layer."""
        scar_drive = (
            abs(self.scar_state.base[6]) if len(self.scar_state.base) > 6 else 0.0
        )
        void_drive = min(1.0, self.void_space.total_pressure() / 50.0)
        social_drive = min(1.0, self.social_void.pressure / 3.0)
        return min(
            1.0,
            scar_drive
            + void_drive * self._void_drive_weight
            + social_drive * self._social_drive_weight,
        )

    def _compute_coherence(self) -> float:
        """Global coherence: alignment between what hurts and what's avoided.

        r → 1: voids and scars are aligned (system is coherent)
        r → 0: pressure builds in numbed areas (dissociation)
        """
        if not self.void_space.voids:
            return 1.0
        total_pressure = 0.0
        numbed_pressure = 0.0
        for v in self.void_space.voids:
            total_pressure += v.pressure
            dim_hint = len(v.boundary) % self.scar_state.n_dims
            if self.scar_state.modifier(dim_hint) < 0.5:
                numbed_pressure += v.pressure
        if total_pressure < 0.01:
            return 1.0
        return 1.0 - (numbed_pressure / total_pressure)

    def feedback(self, outcome: str, dt: float = 1.0) -> dict[str, float]:
        """Inject expression outcome as feedback.

        'accepted' → reduce void pressure, positive scar input
        'ignored' → increase void depth, neutral scar input
        'rejected' → wound event on scar state
        """
        if outcome == "accepted":
            for v in self.void_space.voids:
                v.pressure *= self._accepted_decay
            feedback_vec = [0.3, 0.0, 0.2, -0.2, 0.1, -0.3, 0.0, 0.0]
        elif outcome == "ignored":
            for v in self.void_space.voids:
                v.depth = min(5.0, v.depth + self._ignored_deepening)
            feedback_vec = [0.0, -0.1, -0.1, 0.2, -0.1, 0.0, -0.3, 0.0]
        elif outcome == "rejected":
            feedback_vec = [-0.3, 0.1, -0.3, 0.3, -0.1, 0.4, -0.2, 0.3]
        else:
            feedback_vec = [0.0] * 8

        self.scar_state.step(feedback_vec, 0.0)
        return self.scar_state.observe()

    def to_dict(self) -> dict[str, Any]:
        return {
            "scar": self.scar_state.to_dict(),
            "void": self.void_space.to_dict(),
            "social_void": self.social_void.to_dict(),
            "coherence": self._coherence,
            "tick": self._tick,
        }

    def diagnostics(self) -> dict[str, Any]:
        return {
            "scar": self.scar_state.observe(),
            "void": self.void_space.diagnostics(),
            "coherence": self._coherence,
            "expression_drive": self.expression_drive(),
            "tick": self._tick,
        }

    def set_personality_params(
        self,
        coupling_rate: float,
        pressure_threshold: float,
        void_drive_weight: float,
        social_drive_weight: float,
        accepted_decay: float,
        ignored_deepening: float,
    ):
        self._void_pressure_coupling_rate = coupling_rate
        self.void_space._pressure_threshold = pressure_threshold
        self._void_drive_weight = void_drive_weight
        self._social_drive_weight = social_drive_weight
        self._accepted_decay = accepted_decay
        self._ignored_deepening = ignored_deepening


def _default_similarity(a: bytes, b: bytes) -> float:
    """Hamming similarity for binary vectors."""
    if not a or not b:
        return 0.0
    min_len = min(len(a), len(b))
    xor_bits = sum(bin(a[i] ^ b[i]).count("1") for i in range(min_len))
    total_bits = min_len * 8
    return 1.0 - (xor_bits / total_bits) if total_bits > 0 else 0.0
