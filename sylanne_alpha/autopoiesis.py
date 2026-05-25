"""Sylanne-Embodiment computation layer: Autopoietic Boundary.

Personality as a self-maintaining computational process.
Not defined by external parameters, but by an ongoing self-repair loop.
Small perturbations are absorbed; large shocks may trigger phase transitions.
"""

from __future__ import annotations

import math
from typing import Any


class AutopoieticBoundary:
    __slots__ = (
        "identity_dim",
        "identity_kernel",
        "boundary_integrity",
        "internal_entropy",
        "repair_rate",
        "_phase_transitions",
        "_last_penetration",
        "_phase_threshold",
        "_rotation_angle",
    )

    def __init__(self, identity_dim: int = 32, agreeableness: float = 0.5):
        self.identity_dim = identity_dim
        # Identity kernel: self-referential constraint vector
        self.identity_kernel = self._init_kernel(identity_dim)
        # Initial integrity derived from personality: agreeable = more permeable
        self.boundary_integrity = 1.0 - agreeableness * 0.08
        self.internal_entropy = 0.0
        self.repair_rate = 0.05
        self._phase_transitions: list[dict[str, Any]] = []
        self._last_penetration: float = 0.0
        self._phase_threshold = 0.7
        self._rotation_angle = 0.1

    def perturb(self, force: list[float]) -> dict[str, Any]:
        """External perturbation acts on the boundary."""
        if len(force) < self.identity_dim:
            force = force + [0.0] * (self.identity_dim - len(force))
        force = force[: self.identity_dim]

        # Project force onto identity kernel's orthogonal complement
        dot = sum(f * k for f, k in zip(force, self.identity_kernel))
        orthogonal = [f - dot * k for f, k in zip(force, self.identity_kernel)]
        orth_norm = math.sqrt(sum(x * x for x in orthogonal) + 1e-12)

        # Penetration = orthogonal magnitude × (1 - integrity)
        penetration = orth_norm * (1.0 - self.boundary_integrity)
        self._last_penetration = penetration
        phase_transition = penetration > self._phase_threshold

        if phase_transition:
            self._reorganize(orthogonal, orth_norm)
            self.internal_entropy = min(1.0, self.internal_entropy + 0.3)
            self._phase_transitions.append(
                {
                    "penetration": penetration,
                    "entropy_after": self.internal_entropy,
                }
            )
            if len(self._phase_transitions) > 20:
                self._phase_transitions = self._phase_transitions[-20:]
        else:
            self.boundary_integrity = max(
                0.0, self.boundary_integrity - penetration * 0.1
            )
            self.internal_entropy = min(1.0, self.internal_entropy + penetration * 0.05)

        return {
            "penetration": round(penetration, 4),
            "phase_transition": phase_transition,
            "boundary_integrity": round(self.boundary_integrity, 4),
            "internal_entropy": round(self.internal_entropy, 4),
        }

    def self_repair(self):
        """Self-repair loop -- runs every tick.

        When under active stress (recent high penetration), only reduce
        entropy slowly without restoring boundary integrity -- the wound
        is still open and needs time to heal.
        """
        if self._last_penetration > 0.4:
            # Wound still open: slow healing, don't restore integrity yet
            self._last_penetration *= 0.8  # Gradually decay penetration memory
            self.internal_entropy = max(
                0.0, self.internal_entropy - self.repair_rate * 0.2
            )
            return
        # Normal repair — floor at 0.3 to prevent positive feedback collapse
        self.boundary_integrity = max(
            0.3, min(1.0, self.boundary_integrity + self.repair_rate)
        )
        self.internal_entropy = max(0.0, self.internal_entropy - self.repair_rate * 0.5)
        # Re-normalize identity kernel
        norm = math.sqrt(sum(x * x for x in self.identity_kernel) + 1e-12)
        self.identity_kernel = [x / norm for x in self.identity_kernel]

    def stability(self) -> float:
        """Overall stability score: high = resistant to change."""
        return self.boundary_integrity * (1.0 - self.internal_entropy)

    def phase_transition_count(self) -> int:
        return len(self._phase_transitions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "boundary_integrity": self.boundary_integrity,
            "internal_entropy": self.internal_entropy,
            "stability": self.stability(),
            "repair_rate": self.repair_rate,
            "phase_transitions": len(self._phase_transitions),
            "phase_transition_log": self._phase_transitions[-10:],
            "last_penetration": self._last_penetration,
            "identity_kernel": self.identity_kernel,
        }

    def from_dict(self, data: dict[str, Any]):
        self.boundary_integrity = float(data.get("boundary_integrity", 1.0))
        self.internal_entropy = float(data.get("internal_entropy", 0.0))
        self.repair_rate = float(data.get("repair_rate", 0.05))
        self._last_penetration = float(data.get("last_penetration", 0.0))
        if "phase_transition_log" in data and isinstance(
            data["phase_transition_log"], list
        ):
            self._phase_transitions = data["phase_transition_log"]
        if "identity_kernel" in data and isinstance(data["identity_kernel"], list):
            self.identity_kernel = [float(x) for x in data["identity_kernel"]]

    def _reorganize(self, force: list[float], force_norm: float):
        """Self-directed reorganization: rotate identity kernel slightly toward force."""
        angle = self._rotation_angle  # Max rotation per phase transition
        unit_force = [f / force_norm for f in force]
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        self.identity_kernel = [
            cos_a * k + sin_a * f for k, f in zip(self.identity_kernel, unit_force)
        ]
        # Re-normalize
        norm = math.sqrt(sum(x * x for x in self.identity_kernel) + 1e-12)
        self.identity_kernel = [x / norm for x in self.identity_kernel]

    @classmethod
    def create_shared_kernel(cls, dim: int) -> list[float]:
        """Create a deterministic identity kernel for sharing across instances."""
        return cls._init_kernel(dim)

    def set_identity_kernel(self, kernel: list[float]) -> None:
        """Replace the identity kernel with a shared one."""
        self.identity_kernel = list(kernel)

    def set_personality_params(
        self, repair_rate: float, phase_threshold: float, rotation_angle: float
    ):
        self.repair_rate = repair_rate
        self._phase_threshold = phase_threshold
        self._rotation_angle = rotation_angle

    @staticmethod
    def _init_kernel(dim: int) -> list[float]:
        """Deterministic initial identity kernel."""
        kernel = []
        state = 7919  # prime seed
        for i in range(dim):
            state = (state * 48271) % 2147483647
            kernel.append((state / 2147483647) * 2.0 - 1.0)
        norm = math.sqrt(sum(x * x for x in kernel))
        return [x / norm for x in kernel]
