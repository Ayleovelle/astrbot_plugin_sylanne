"""Void-Scar Coupled Engine — Unified replacement for SSM + TDA layers.

Integrates Scar Algebra (irreversible state dynamics) with Void Calculus
(first-class absence computation) through bidirectional coupling:
  Γ: Void pressure → Scar wounding events
  Φ: Scar numbing → Void genesis sensitivity
"""
from __future__ import annotations

from typing import Any, Callable

from .scar_algebra import ScarredState
from .void_calculus import VoidSpace


class VoidScarEngine:
    """Coupled Void-Scar computation engine.

    Replaces the SSM (Layer 3) and TDA (Layer 4) in the computation spine.
    """

    __slots__ = (
        "scar_state", "void_space", "similarity_fn",
        "_coherence", "_last_event_vec", "_tick",
        "_void_pressure_coupling_rate",
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
        self._coherence = 1.0
        self._last_event_vec: bytes | None = None
        self._tick = 0
        self._void_pressure_coupling_rate = 0.3

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
        # Numbed dimensions lower void detection threshold
        numbed_count = sum(
            1 for d in range(self.scar_state.n_dims)
            if self.scar_state.is_numbed(d)
        )
        if numbed_count > 0:
            self.void_space._detection_threshold = max(
                0.1, 0.4 - numbed_count * 0.05
            )

        # --- Void Calculus step ---
        void_result = self.void_space.process(event_vec, surprise, prev_sim)

        # --- Coupling Γ: Void pressure → Scar wounding ---
        coupling_wounds: list[dict[str, Any]] = []
        for coupling in void_result["coupling_events"]:
            wound_event = [0.0] * self.scar_state.n_dims
            dim_hint = int(coupling.get("dim_hint", 0)) % self.scar_state.n_dims
            wound_event[dim_hint] = coupling["pressure"] * self._void_pressure_coupling_rate
            wound_result = self.scar_state.step(wound_event, timestamp)
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

    def observe(self) -> dict[str, float]:
        """Observable output for downstream layers."""
        obs = self.scar_state.observe()
        obs["coherence"] = self._coherence
        obs["void_pressure"] = self.void_space.total_pressure()
        obs["active_voids"] = float(len(self.void_space.voids))
        obs["ghost_count"] = float(len(self.void_space.ghosts))
        return obs

    def expression_drive(self) -> float:
        """Combined drive for the phase transition expression layer."""
        scar_drive = abs(self.scar_state.base[6]) if len(self.scar_state.base) > 6 else 0.0
        void_drive = min(1.0, self.void_space.total_pressure() / 50.0)
        return min(1.0, scar_drive + void_drive * 0.5)

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
                v.pressure *= 0.7
            feedback_vec = [0.3, 0.0, 0.2, -0.2, 0.1, -0.3, 0.0, 0.0]
        elif outcome == "ignored":
            for v in self.void_space.voids:
                v.depth += 0.05
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


def _default_similarity(a: bytes, b: bytes) -> float:
    """Hamming similarity for binary vectors."""
    if not a or not b:
        return 0.0
    min_len = min(len(a), len(b))
    xor_bits = sum(bin(a[i] ^ b[i]).count('1') for i in range(min_len))
    total_bits = min_len * 8
    return 1.0 - (xor_bits / total_bits) if total_bits > 0 else 0.0
