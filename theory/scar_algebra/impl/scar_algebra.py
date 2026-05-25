"""Scar Algebra — Reference Implementation.

A self-modifying operator algebra where past operations change
the semantics of future operations. Scars are irreversible marks
that modulate how the system processes future inputs.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class HealingStage(IntEnum):
    RAW = 0
    CLOSING = 1
    SCARRED = 2
    FADED = 3


_STAGE_ALPHA = {
    HealingStage.RAW: 2.0,
    HealingStage.CLOSING: 1.5,
    HealingStage.SCARRED: 1.0,
    HealingStage.FADED: 0.7,
}

_STAGE_DURATION = {
    HealingStage.RAW: 10,
    HealingStage.CLOSING: 40,
    HealingStage.SCARRED: 150,
}


@dataclass(slots=True)
class Scar:
    dimension: int
    timestamp: float
    stage: HealingStage = HealingStage.RAW
    ticks_in_stage: int = 0

    @property
    def alpha(self) -> float:
        return _STAGE_ALPHA[self.stage]

    def heal_tick(self) -> bool:
        """Advance healing by one tick. Returns True if stage changed."""
        if self.stage == HealingStage.FADED:
            return False
        self.ticks_in_stage += 1
        threshold = _STAGE_DURATION.get(self.stage)
        if threshold is not None and self.ticks_in_stage >= threshold:
            self.stage = HealingStage(self.stage + 1)
            self.ticks_in_stage = 0
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "timestamp": self.timestamp,
            "stage": self.stage.name,
            "ticks_in_stage": self.ticks_in_stage,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Scar":
        return cls(
            dimension=data["dimension"],
            timestamp=data["timestamp"],
            stage=HealingStage[data["stage"]],
            ticks_in_stage=data.get("ticks_in_stage", 0),
        )


class ScarredState:
    """The core Scar Algebra state: base vector + irreversible scar sequence."""

    __slots__ = ("base", "scars", "n_dims", "wound_threshold", "_tick", "_neuroticism")

    def __init__(self, n_dims: int = 8, wound_threshold: float = 0.6):
        self.n_dims = n_dims
        self.wound_threshold = wound_threshold
        self.base = [0.0] * n_dims
        self.scars: list[Scar] = []
        self._tick = 0
        self._neuroticism: float = 0.5

    def modifier(self, dim: int) -> float:
        """Compute the cumulative scar modifier for a dimension.

        Uses logarithmic compression with personality-driven cap to prevent
        unbounded exponential growth from product of scar alphas.
        """
        product = 1.0
        for scar in self.scars:
            if scar.dimension == dim:
                product *= scar.alpha
        if product <= 1.0:
            return product
        max_mod = 2.0 + self._neuroticism * 3.0
        return 1.0 + (max_mod - 1.0) * (1.0 - 1.0 / product)

    def modulate(self, event: list[float]) -> list[float]:
        """Apply scar modulation to an input event (Step 1 of ⊳)."""
        result = []
        for d in range(self.n_dims):
            e_d = event[d] if d < len(event) else 0.0
            result.append(e_d * self.modifier(d))
        return result

    def step(self, event: list[float], timestamp: float = 0.0) -> dict[str, Any]:
        """Apply the ⊳ operator: full state transition.

        Returns a diagnostic dict describing what happened.
        """
        self._tick += 1

        # Step 1: Scar-modulated input
        modulated = self.modulate(event)

        # Step 2: Base state evolution (bounded nonlinear map)
        for d in range(self.n_dims):
            raw = self.base[d] + modulated[d] * 0.3
            self.base[d] = math.tanh(raw)

        # Step 3: Scar formation (conditional)
        new_scars = []
        for d in range(self.n_dims):
            if abs(modulated[d]) > self.wound_threshold:
                scar = Scar(dimension=d, timestamp=timestamp)
                self.scars.append(scar)
                new_scars.append(d)

        # Step 4: Healing
        healed = []
        for scar in self.scars:
            if scar.heal_tick():
                healed.append(scar.dimension)

        return {
            "modulated": modulated,
            "new_scars": new_scars,
            "healed_dimensions": healed,
            "total_scars": len(self.scars),
            "base": list(self.base),
        }

    def observe(self) -> dict[str, float]:
        """Observable output: base state + per-dimension sensitivity."""
        obs = {}
        for d in range(self.n_dims):
            obs[f"dim_{d}"] = self.base[d]
            obs[f"sensitivity_{d}"] = self.modifier(d)
        obs["total_scars"] = float(len(self.scars))
        obs["numbed_dimensions"] = float(sum(
            1 for d in range(self.n_dims) if self.modifier(d) < 0.5
        ))
        return obs

    def is_numbed(self, dim: int) -> bool:
        """Whether a dimension has been scarred into numbness."""
        return self.modifier(dim) < 0.5

    def scar_density(self, dim: int) -> float:
        """Weighted scar density on a dimension."""
        weights = {HealingStage.RAW: 1.0, HealingStage.CLOSING: 0.8,
                   HealingStage.SCARRED: 0.5, HealingStage.FADED: 0.3}
        return sum(weights[s.stage] for s in self.scars if s.dimension == dim)

    def to_dict(self) -> dict[str, Any]:
        return {
            "base": list(self.base),
            "scars": [s.to_dict() for s in self.scars],
            "n_dims": self.n_dims,
            "wound_threshold": self.wound_threshold,
            "tick": self._tick,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScarredState":
        state = cls(n_dims=data["n_dims"], wound_threshold=data["wound_threshold"])
        state.base = list(data["base"])
        state.scars = [Scar.from_dict(s) for s in data.get("scars", [])]
        state._tick = data.get("tick", 0)
        return state
