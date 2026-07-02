"""Deterministic Fusion — drop-in replacement for the Simplicial Resonance Field.

v2.5: the iterative six-mechanism resonance core (Kuramoto + Hopfield + free-energy
+ harmonic identity + echo-state reservoir + simplicial higher-order coupling) is
retired. Benchmarking showed the default (lite) tier phase-locked to an
input-insensitive fixed point with no objective function (steady-state sync
0.9991+-0.0001, 0% convergence), so the elaborate loop bought nothing it could be
held accountable for.

This class preserves the exact ``ResonanceField`` interface consumed by
``ResonanceSpine`` — same methods, same ``resonate()``/``observe()`` return-dict
keys, same ``to_dict``/``from_dict`` shape — but ``resonate()`` is a single
deterministic coherence pass instead of an iterate-to-convergence loop. Output
contract is preserved: ``route``/``assessment_source`` literals, key sets, types and
rounding are unchanged; only the (formerly noise-like) numeric values move.

The reach-in attributes that ``ResonanceSpine.apply_personality``/``feedback`` poke
(``_coupling.kuramoto._k1``, ``_coupling.plasticity.update`` ...) are kept as inert
stubs so the spine needs no edits beyond swapping the factory: those knobs only ever
tuned the deleted dynamics. The genuinely load-bearing outputs — per-module states,
energy, and a coherence-based ``sync_order`` — are produced deterministically so the
expression decision still receives non-degenerate inputs.
"""

from __future__ import annotations

import math
from typing import Any

_TIER_CONFIG = {
    "lite": {"state_dim": 8},
    "pro": {"state_dim": 16},
    "max": {"state_dim": 128},
}
_MAX_ATTRACTORS = {"lite": 5, "pro": 10, "max": 20}


def _vec_norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def _resize(vec: list[float], new_dim: int) -> list[float]:
    if len(vec) == new_dim:
        return list(vec)
    if len(vec) > new_dim:
        return list(vec[:new_dim])
    return list(vec) + [0.0] * (new_dim - len(vec))


# --- inert stand-ins for CouplingDynamics internals ---------------------------
# These exist only to absorb the personality/feedback reach-ins that previously
# tuned the resonance dynamics. They hold whatever is written to them and do
# nothing with it; the deleted loop was their only consumer.


class _Kuramoto:
    def __init__(self) -> None:
        self._k1 = 1.0
        self._k2 = 0.5
        self._k3 = 0.3
        self._last_step_delta = 0.0
        self._order = 0.0

    def order_parameter(self) -> float:
        return self._order


class _FreeEnergy:
    def __init__(self) -> None:
        self._precision = 1.0


class _Broadcast:
    def __init__(self) -> None:
        self._threshold = 0.8


class _Plasticity:
    def __init__(self, n_channels: int) -> None:
        self._eta = 0.01
        self._lambda_decay = 0.001
        self.weights = [0.0] * n_channels

    @property
    def active_ratio(self) -> float:
        return 0.0

    def update(self, deltas: list[float]) -> None:  # noqa: ARG002 — inert
        return None


class _Coupling:
    def __init__(self, n_channels: int) -> None:
        self.kuramoto = _Kuramoto()
        self.free_energy = _FreeEnergy()
        self.broadcast = _Broadcast()
        self.plasticity = _Plasticity(n_channels)
        self.topology_gate = None  # spine guards every access with `is not None`

    def set_criticality(self, value: float) -> None:  # noqa: ARG002 — inert
        return None

    def feedback_topology(self, outcome: str, active_channels: Any) -> None:  # noqa: ARG002
        return None


class _Complex:
    def __init__(self, total_directed: int) -> None:
        self.total_directed = total_directed


# --- the replacement field ----------------------------------------------------


class DeterministicFusion:
    """Single-pass deterministic fuser with the ResonanceField surface."""

    def __init__(self, n_modules: int = 7, tier: str = "lite", epsilon: float = 1e-4) -> None:
        cfg = _TIER_CONFIG.get(tier, _TIER_CONFIG["lite"])
        self._n_modules = n_modules
        self._state_dim = cfg["state_dim"]
        self._tier = tier
        self._epsilon = epsilon
        self._module_states: list[list[float]] = [[0.0] * self._state_dim for _ in range(n_modules)]
        n_channels = n_modules * (n_modules - 1)  # directed pairwise (matches legacy lite=42)
        self._coupling = _Coupling(n_channels)
        self._complex = _Complex(n_channels)
        self._total_resonances = 0
        self._iteration_count = 0
        self._last_energy = 0.0
        self._last_convergence = 0.0
        self._had_injection = False
        self._coherence_gain = 0.15

        # personality / meta-learner reach-in targets (inert: fed deleted dynamics)
        self._dissipation = 0.02
        self._residual_decay = 0.7
        self._hopfield_strength = 0.05
        self._identity_inertia = 0.95
        self._identity_max_norm = float(self._state_dim)
        self._max_attractors = _MAX_ATTRACTORS.get(tier, 5)

    def inject(self, module_idx: int, signal: list[float]) -> None:
        """Inject external signal into a module's state vector (additive)."""
        if 0 <= module_idx < self._n_modules:
            state = self._module_states[module_idx]
            for i in range(min(len(signal), self._state_dim)):
                state[i] += signal[i]
            self._had_injection = True

    def resonate(self) -> dict[str, Any]:
        """One deterministic coherence pass: share information across modules once,
        squash, dissipate. No iteration, no attractors, no convergence loop."""
        self._total_resonances += 1
        self._iteration_count += 1
        n, d = self._n_modules, self._state_dim

        # mean field across modules
        mean = [0.0] * d
        for s in self._module_states:
            for j in range(d):
                mean[j] += s[j]
        inv = 1.0 / n if n else 0.0
        mean = [m * inv for m in mean]

        # single coherence step: pull each module toward the mean, squash, dissipate
        g = self._coherence_gain
        keep = 1.0 - self._dissipation
        new_states = [
            [math.tanh(s[j] + g * (mean[j] - s[j])) * keep for j in range(d)]
            for s in self._module_states
        ]

        # energy: 0.5 * sum of squared norms (same scale/semantics as the old field)
        energy = 0.5 * sum(sum(x * x for x in s) for s in new_states)

        # sync_order: coherence proxy in [0,1] — how aligned modules are to the mean
        dists = [_vec_norm([new_states[i][j] - mean[j] for j in range(d)]) for i in range(n)]
        scale = (sum(_vec_norm(s) for s in new_states) / n if n else 0.0) + 1e-9
        sync = max(0.0, min(1.0, 1.0 - (sum(dists) / n) / scale))

        # residual decay for next tick (mirrors field semantics)
        rd = self._residual_decay
        for s in new_states:
            for j in range(d):
                s[j] *= rd

        self._module_states = new_states
        self._last_energy = energy
        self._last_convergence = 0.0
        self._coupling.kuramoto._order = sync
        self._had_injection = False

        return {
            "iterations": 1,
            "converged": True,
            "final_delta": 0.0,
            "energy": energy,
            "sync_order": sync,
            "free_energy": 0.0,
            "attractor_count": 0,
            "near_attractor": float("inf"),
            "reservoir_energy": 0.0,
            "max_sync_delta": 0.0,
            "skipped_channels": 0,
        }

    def observe(self) -> dict[str, Any]:
        """Current field state observation (same keys as ResonanceField.observe)."""
        return {
            "module_magnitudes": [_vec_norm(s) for s in self._module_states],
            "total_energy": self._last_energy,
            "sync_order": self._coupling.kuramoto.order_parameter(),
            "active_channels": self._complex.total_directed,
            "plasticity_ratio": self._coupling.plasticity.active_ratio,
            "convergence": self._last_convergence,
            "total_resonances": self._total_resonances,
            "topology": {"active_count": self._complex.total_directed, "sparsity": 0.0},
        }

    @property
    def module_states(self) -> list[list[float]]:
        return self._module_states

    @property
    def state_dim(self) -> int:
        return self._state_dim

    @property
    def active_channels(self) -> int:
        return self._complex.total_directed

    @property
    def convergence_history(self) -> list[float]:
        return [self._last_convergence]

    def reset(self) -> None:
        self._module_states = [[0.0] * self._state_dim for _ in range(self._n_modules)]
        self._last_energy = 0.0
        self._last_convergence = 0.0

    def switch_tier(self, new_tier: str) -> None:
        """Hot-switch tier: resize module states, update tier-derived params."""
        if new_tier == self._tier:
            return
        new_dim = _TIER_CONFIG.get(new_tier, _TIER_CONFIG["lite"])["state_dim"]
        self._module_states = [_resize(s, new_dim) for s in self._module_states]
        self._state_dim = new_dim
        self._tier = new_tier
        self._identity_max_norm = float(new_dim)
        self._max_attractors = _MAX_ATTRACTORS.get(new_tier, 5)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self._tier,
            "states": [list(s) for s in self._module_states],
            "total_resonances": self._total_resonances,
            "iteration_count": self._iteration_count,
            "dissipation": self._dissipation,
            "residual_decay": self._residual_decay,
            "hopfield_strength": self._hopfield_strength,
            "identity_inertia": self._identity_inertia,
            "kuramoto_k1": self._coupling.kuramoto._k1,
            "broadcast_threshold": self._coupling.broadcast._threshold,
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        # "states" is also present in legacy ResonanceField snapshots, so old saves
        # migrate gracefully — states load, the dropped field internals are ignored.
        if "states" in data:
            # Align loaded states to THIS instance's shape — BOTH per-state width and
            # module count. A snapshot from another tier (pro=16 / max=128) or a legacy
            # ResonanceField save must match, or the next resonate()/inject() reads past
            # the configured shape: range(state_dim) over a too-short state IndexErrors,
            # and range(n_modules) over too-few states (line ~178, `for i in range(n)`)
            # IndexErrors too. _resize fixes width; pad/truncate fixes the row count.
            # (Same _resize convention as switch_tier; count normalization mirrors it.)
            states = [_resize(s, self._state_dim) for s in data["states"]]
            if len(states) < self._n_modules:
                states += [[0.0] * self._state_dim for _ in range(self._n_modules - len(states))]
            self._module_states = states[: self._n_modules]
        self._total_resonances = data.get("total_resonances", 0)
        self._iteration_count = data.get("iteration_count", 0)
        self._dissipation = data.get("dissipation", self._dissipation)
        self._residual_decay = data.get("residual_decay", self._residual_decay)
        self._hopfield_strength = data.get("hopfield_strength", self._hopfield_strength)
        self._identity_inertia = data.get("identity_inertia", self._identity_inertia)
        self._coupling.kuramoto._k1 = data.get("kuramoto_k1", self._coupling.kuramoto._k1)
        self._coupling.broadcast._threshold = data.get(
            "broadcast_threshold", self._coupling.broadcast._threshold
        )


def create_deterministic_fusion(
    n_modules: int = 7,
    tier: str = "lite",
    epsilon: float = 1e-4,
    backend: str | None = None,  # noqa: ARG001 — pure Python at every tier
) -> DeterministicFusion:
    """Factory mirroring ``create_resonance_field``'s signature; backend ignored."""
    return DeterministicFusion(n_modules=n_modules, tier=tier, epsilon=epsilon)
