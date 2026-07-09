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

The genuinely load-bearing outputs — per-module states, energy, and a
coherence-based ``sync_order`` — are produced deterministically so the expression
decision still receives non-degenerate inputs.

2.5 cleanup: the ``_Kuramoto``/``_Plasticity``/``_FreeEnergy`` inert stand-ins (and
the personality/feedback/meta-learner reach-ins that only ever wrote into them) have
been removed — they had exactly one writer and one reader each (both inside this
module or a same-shape self-loop), zero behavioural consumers, and the mechanisms
they named (Kuramoto phase sync, Hebbian plasticity, active-inference free energy)
were deleted along with the iterative resonance core they belonged to. ``sync_order``
is unaffected: it is still the mean-field coherence proxy computed in ``resonate()``
below, now cached directly on the fusion object instead of round-tripping through a
dead ``_Kuramoto._order`` field.
"""

from __future__ import annotations

import math
from typing import Any

_TIER_CONFIG = {
    "lite": {"state_dim": 8},
    "pro": {"state_dim": 16},
    "max": {"state_dim": 128},
}


def _vec_norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def _resize(vec: list[float], new_dim: int) -> list[float]:
    if len(vec) == new_dim:
        return list(vec)
    if len(vec) > new_dim:
        return list(vec[:new_dim])
    return list(vec) + [0.0] * (new_dim - len(vec))


# --- inert stand-in for CouplingDynamics internals ----------------------------
# _Broadcast/topology_gate absorb personality/feedback reach-ins that are still
# read elsewhere (broadcast._threshold feeds the meta-learner loop; topology_gate
# is guarded `is not None` at every call site). The Kuramoto/plasticity/free-energy
# stand-ins that had zero live consumers were removed in the 2.5 cleanup — see the
# module docstring.


class _Broadcast:
    def __init__(self) -> None:
        self._threshold = 0.8


class _Coupling:
    def __init__(self) -> None:
        self.broadcast = _Broadcast()
        self.topology_gate = None  # spine guards every access with `is not None`

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
        self._coupling = _Coupling()
        self._complex = _Complex(n_channels)
        self._total_resonances = 0
        self._iteration_count = 0
        self._last_energy = 0.0
        self._last_convergence = 0.0
        self._last_sync_order = 0.0
        self._had_injection = False
        self._coherence_gain = 0.15

        # personality / meta-learner reach-in targets (inert: fed deleted dynamics)
        self._dissipation = 0.02
        self._residual_decay = 0.7

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
        self._last_sync_order = sync
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
            "sync_order": self._last_sync_order,
            "active_channels": self._complex.total_directed,
            "plasticity_ratio": 0.0,
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self._tier,
            "states": [list(s) for s in self._module_states],
            "total_resonances": self._total_resonances,
            "iteration_count": self._iteration_count,
            "dissipation": self._dissipation,
            "residual_decay": self._residual_decay,
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
        # NOTE: legacy snapshots may still carry "kuramoto_k1", "hopfield_strength",
        # "identity_inertia" and similar keys (written by pre-2.5 saves); they are
        # intentionally ignored here — the fields they fed were dead stubs with zero
        # consumers and have been removed (see module docstring). data.get() on these
        # keys is simply never called, so the residual keys are silently dropped
        # without a KeyError.
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
