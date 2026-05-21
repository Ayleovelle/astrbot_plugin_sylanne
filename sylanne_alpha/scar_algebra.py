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

    __slots__ = (
        "base", "scars", "n_dims", "wound_threshold", "_tick",
        "_t_raw", "_t_closing", "_t_scarred",
        "_mlp_w1", "_mlp_w2", "_mlp_hidden_dim",
    )

    def __init__(self, n_dims: int = 8, wound_threshold: float = 0.6):
        self.n_dims = n_dims
        self.wound_threshold = wound_threshold
        self.base = [0.0] * n_dims
        self.scars: list[Scar] = []
        self._tick = 0
        # Configurable healing rates (defaults match original _STAGE_DURATION)
        self._t_raw: int = 10
        self._t_closing: int = 40
        self._t_scarred: int = 150
        # MLP parameters for base state evolution (initialized lazily)
        self._mlp_hidden_dim: int = 12
        self._mlp_w1: list[list[float]] | None = None
        self._mlp_w2: list[list[float]] | None = None

    def set_healing_rates(self, t_raw: int, t_closing: int, t_scarred: int) -> None:
        """Set configurable healing durations for each stage.

        Args:
            t_raw: Ticks to stay in RAW stage before advancing to CLOSING.
            t_closing: Ticks to stay in CLOSING stage before advancing to SCARRED.
            t_scarred: Ticks to stay in SCARRED stage before advancing to FADED.
        """
        self._t_raw = max(1, int(t_raw))
        self._t_closing = max(1, int(t_closing))
        self._t_scarred = max(1, int(t_scarred))

    def healing_duration(self, stage: "HealingStage", dim: int | None = None) -> int:
        """Get healing duration for a stage, optionally adjusted per-dimension.

        If a dimension has scar_count > 3, its healing is 1.5x slower.
        """
        base_duration = {
            HealingStage.RAW: self._t_raw,
            HealingStage.CLOSING: self._t_closing,
            HealingStage.SCARRED: self._t_scarred,
        }.get(stage, 0)
        if dim is not None and self.scar_count(dim) > 3:
            base_duration = int(base_duration * 1.5)
        return base_duration

    def scar_count(self, dim: int) -> int:
        """Count total scars on a given dimension."""
        return sum(1 for s in self.scars if s.dimension == dim)

    def _init_mlp_weights(self, seed: int = 42) -> None:
        """Initialize MLP weights from a deterministic seed with spectral normalization."""
        import random
        rng = random.Random(seed)
        input_dim = self.n_dims * 2  # [x; e_tilde] concatenated
        hidden_dim = self._mlp_hidden_dim

        # Layer 1: hidden_dim x input_dim
        self._mlp_w1 = [
            [rng.gauss(0, 0.5) for _ in range(input_dim)]
            for _ in range(hidden_dim)
        ]
        # Layer 2: n_dims x hidden_dim
        self._mlp_w2 = [
            [rng.gauss(0, 0.5) for _ in range(hidden_dim)]
            for _ in range(self.n_dims)
        ]
        # Apply spectral normalization to both weight matrices
        self._mlp_w1 = self._spectral_normalize(self._mlp_w1, max_sigma=0.7)
        self._mlp_w2 = self._spectral_normalize(self._mlp_w2, max_sigma=0.7)

    def _spectral_normalize(self, W: list[list[float]], max_sigma: float = 0.7) -> list[list[float]]:
        """Spectral normalization via power iteration.

        Estimates the largest singular value of W and scales W down
        if sigma > max_sigma. This ensures ||W||_2 <= max_sigma.
        """
        rows = len(W)
        cols = len(W[0]) if rows > 0 else 0
        if rows == 0 or cols == 0:
            return W

        # Power iteration (10 iterations is sufficient for convergence)
        # Initialize u as unit vector
        u = [1.0 / math.sqrt(rows)] * rows
        v = [0.0] * cols

        for _ in range(10):
            # v = W^T u / ||W^T u||
            for j in range(cols):
                v[j] = sum(W[i][j] * u[i] for i in range(rows))
            v_norm = math.sqrt(sum(x * x for x in v)) + 1e-12
            v = [x / v_norm for x in v]

            # u = W v / ||W v||
            for i in range(rows):
                u[i] = sum(W[i][j] * v[j] for j in range(cols))
            u_norm = math.sqrt(sum(x * x for x in u)) + 1e-12
            u = [x / u_norm for x in u]

        # Estimate sigma = u^T W v
        sigma = 0.0
        for i in range(rows):
            sigma += u[i] * sum(W[i][j] * v[j] for j in range(cols))

        # Scale if needed
        if sigma > max_sigma:
            scale = max_sigma / sigma
            return [[W[i][j] * scale for j in range(cols)] for i in range(rows)]
        return W

    def _evolve_base(self, x: list[float], e_tilde: list[float]) -> list[float]:
        """Evolve base state using 2-layer MLP with spectral normalization.

        Layer 1: hidden = tanh(W1 * [x; e_tilde])
        Layer 2: output = tanh(W2 * hidden)

        Convergence guarantee: ||W1||_2 * ||W2||_2 < 0.7 * 0.7 = 0.49 < 1
        """
        if self._mlp_w1 is None or self._mlp_w2 is None:
            self._init_mlp_weights()

        # Concatenate input: [x; e_tilde]
        inp = list(x) + list(e_tilde)
        hidden_dim = len(self._mlp_w1)
        out_dim = len(self._mlp_w2)

        # Layer 1: hidden = tanh(W1 * inp)
        hidden = [0.0] * hidden_dim
        for i in range(hidden_dim):
            val = sum(self._mlp_w1[i][j] * inp[j] for j in range(len(inp)))
            hidden[i] = math.tanh(val)

        # Layer 2: output = tanh(W2 * hidden)
        output = [0.0] * out_dim
        for i in range(out_dim):
            val = sum(self._mlp_w2[i][j] * hidden[j] for j in range(hidden_dim))
            output[i] = math.tanh(val)

        return output

    def modifier(self, dim: int) -> float:
        """Compute the cumulative scar modifier for a dimension."""
        product = 1.0
        for scar in self.scars:
            if scar.dimension == dim:
                product *= scar.alpha
        return product

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

        # Step 2: Base state evolution (2-layer MLP with spectral normalization)
        self.base = self._evolve_base(self.base, modulated)

        # Step 3: Scar formation (conditional)
        new_scars = []
        for d in range(self.n_dims):
            if abs(modulated[d]) > self.wound_threshold:
                scar = Scar(dimension=d, timestamp=timestamp)
                self.scars.append(scar)
                new_scars.append(d)

        # Step 4: Healing (using configurable per-dimension rates)
        healed = []
        for scar in self.scars:
            if scar.stage == HealingStage.FADED:
                continue
            scar.ticks_in_stage += 1
            threshold = self.healing_duration(scar.stage, dim=scar.dimension)
            if threshold > 0 and scar.ticks_in_stage >= threshold:
                scar.stage = HealingStage(scar.stage + 1)
                scar.ticks_in_stage = 0
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
            "t_raw": self._t_raw,
            "t_closing": self._t_closing,
            "t_scarred": self._t_scarred,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScarredState":
        state = cls(n_dims=data["n_dims"], wound_threshold=data["wound_threshold"])
        state.base = list(data["base"])
        state.scars = [Scar.from_dict(s) for s in data.get("scars", [])]
        state._tick = data.get("tick", 0)
        state._t_raw = data.get("t_raw", 10)
        state._t_closing = data.get("t_closing", 40)
        state._t_scarred = data.get("t_scarred", 150)
        return state
