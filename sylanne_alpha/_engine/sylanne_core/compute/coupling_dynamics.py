"""Coupling dynamics for the simplicial resonance field.

Implements use-dependent plasticity (Hebbian strengthening + atrophy),
Kuramoto phase synchronization on simplicial complexes, and free energy
minimization across the complete 6-simplex coupling topology.

Theoretical grounding:
- Hebb (1949): neurons that fire together wire together
- Kuramoto (1975): coupled oscillator synchronization
- Millán et al. (2020): higher-order Kuramoto on simplicial complexes
- Friston (2006, 2010): free energy principle
- Edelman (1987): neural Darwinism / synaptic pruning
- Barbarossa & Sardellitti (2020): simplicial signal processing
"""

from __future__ import annotations

import math
from itertools import combinations
from typing import Any

_TIER_MAX_ORDER = {"lite": 1, "pro": 3, "max": 6}


class SimplicialComplex:
    """Complete simplicial complex on n vertices up to max_order."""

    __slots__ = ("n", "max_order", "simplices", "directed_channels", "_simplex_to_idx")

    def __init__(self, n: int = 7, max_order: int = 6):
        self.n = n
        self.max_order = min(max_order, n - 1)
        self.simplices: dict[int, list[tuple[int, ...]]] = {}
        self.directed_channels: list[tuple[tuple[int, ...], int]] = []
        self._simplex_to_idx: dict[tuple[int, ...], int] = {}
        self._build()

    def _build(self) -> None:
        vertices = list(range(self.n))
        idx = 0
        for k in range(1, self.max_order + 1):
            order_simplices = [s for s in combinations(vertices, k + 1)]
            self.simplices[k] = order_simplices
            for s in order_simplices:
                self._simplex_to_idx[s] = idx
                idx += 1
                for target_vertex in s:
                    self.directed_channels.append((s, target_vertex))

    @property
    def total_undirected(self) -> int:
        return sum(len(v) for v in self.simplices.values())

    @property
    def total_directed(self) -> int:
        return len(self.directed_channels)

    def boundary_matrix(self, k: int) -> list[list[float]]:
        """∂_k: C_k → C_{k-1} boundary operator matrix."""
        if k < 1 or k > self.max_order:
            return []
        k_simplices = self.simplices.get(k, [])
        km1_simplices = self.simplices.get(k - 1, []) if k > 1 else [(i,) for i in range(self.n)]
        if not k_simplices or not km1_simplices:
            return []
        km1_idx = {s: i for i, s in enumerate(km1_simplices)}
        rows = len(km1_simplices)
        cols = len(k_simplices)
        mat = [[0.0] * cols for _ in range(rows)]
        for j, sigma in enumerate(k_simplices):
            for face_idx in range(len(sigma)):
                face = sigma[:face_idx] + sigma[face_idx + 1 :]
                sign = (-1.0) ** face_idx
                if face in km1_idx:
                    mat[km1_idx[face]][j] = sign
        return mat


class HebbianPlasticity:
    """Use-dependent channel plasticity with strengthening and atrophy.

    Channels that co-activate strengthen (LTP). Channels unused decay (LTD).
    Implements STDP-like timing sensitivity and homeostatic scaling.

    w_ij(t+1) = w_ij(t) + η·pre_i·post_j - λ·w_ij(t) + noise
    Subject to: w_min ≤ w_ij ≤ w_max, Σw = const (homeostasis)
    """

    __slots__ = (
        "weights",
        "_n_channels",
        "_eta",
        "_lambda_decay",
        "_w_min",
        "_w_max",
        "_homeostatic_target",
        "_activation_trace",
        "_trace_decay",
        "_total_updates",
        "_pruned_count",
    )

    def __init__(
        self,
        n_channels: int,
        eta: float = 0.01,
        lambda_decay: float = 0.001,
        w_min: float = 0.01,
        w_max: float = 5.0,
    ):
        self._n_channels = n_channels
        self._eta = eta
        self._lambda_decay = lambda_decay
        self._w_min = w_min
        self._w_max = w_max
        self.weights = [1.0] * n_channels
        self._homeostatic_target = float(n_channels)
        self._activation_trace = [0.0] * n_channels
        self._trace_decay = 0.95
        self._total_updates = 0
        self._pruned_count = 0

    def update(self, activations: list[float]) -> None:
        """Hebbian update: strengthen active channels, decay inactive ones."""
        self._total_updates += 1
        for i in range(self._n_channels):
            self._activation_trace[i] = (
                self._trace_decay * self._activation_trace[i] + activations[i]
            )
            # LTP: strengthen proportional to activation
            delta_ltp = self._eta * activations[i] * self._activation_trace[i]
            # LTD: decay proportional to current weight (atrophy)
            delta_ltd = self._lambda_decay * self.weights[i]
            self.weights[i] += delta_ltp - delta_ltd
            self.weights[i] = max(self._w_min, min(self._w_max, self.weights[i]))
        self._homeostatic_rescale()

    def _homeostatic_rescale(self) -> None:
        """Maintain total synaptic weight budget (homeostatic plasticity)."""
        total = sum(self.weights)
        if total > 0 and abs(total - self._homeostatic_target) > 0.1:
            scale = self._homeostatic_target / total
            for i in range(self._n_channels):
                self.weights[i] *= scale
                self.weights[i] = max(self._w_min, self.weights[i])

    def prune(self, threshold: float = 0.05) -> list[int]:
        """Prune channels below threshold (neural Darwinism)."""
        pruned = []
        for i in range(self._n_channels):
            if self.weights[i] < threshold:
                pruned.append(i)
                self._pruned_count += 1
        return pruned

    @property
    def active_ratio(self) -> float:
        active = sum(1 for w in self.weights if w > 0.1)
        return active / max(1, self._n_channels)

    def to_dict(self) -> dict[str, Any]:
        return {
            "weights": list(self.weights),
            "trace": list(self._activation_trace),
            "updates": self._total_updates,
            "pruned": self._pruned_count,
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        if "weights" in data:
            self.weights = list(data["weights"])
            self._n_channels = len(self.weights)
        if "trace" in data:
            self._activation_trace = list(data["trace"])
        self._total_updates = data.get("updates", 0)
        self._pruned_count = data.get("pruned", 0)
        self._homeostatic_target = float(self._n_channels)


class KuramotoSync:
    """Higher-order Kuramoto synchronization on simplicial complexes.

    Extends classical Kuramoto (1975) with:
    - Pairwise: dθ_i/dt = ω_i + K₁ Σ_j w_ij sin(θ_j - θ_i)
    - 3-body (Millán et al. 2020): + K₂ Σ_{j,k∈Δ} sin(θ_j + θ_k - 2θ_i)
    - Higher-order: generalized simplicial phase coupling

    The higher-order terms create explosive synchronization transitions
    and multistability — essential for phase-transition-driven expression.
    """

    __slots__ = (
        "phases",
        "frequencies",
        "_n",
        "_dt",
        "_k1",
        "_k2",
        "_k3",
        "_simplices",
        "_prev_order",
        "_last_step_delta",
    )

    def __init__(self, n: int = 7, dt: float = 0.1, coupling: float = 1.0):
        self._n = n
        self._dt = dt
        self._k1 = coupling
        self._k2 = coupling * 0.5
        self._k3 = coupling * 0.25
        # Initialize phases SPREAD (not all zero) — prevents trivial sync
        self.phases = [(2.0 * math.pi * i / n) for i in range(n)]
        self.frequencies = [0.1 * (i + 1) for i in range(n)]
        self._simplices: dict[int, list[tuple[int, ...]]] = {}
        self._prev_order = self.order_parameter()
        self._last_step_delta = 0.0

    def set_simplices(self, simplices: dict[int, list[tuple[int, ...]]]) -> None:
        """Provide simplicial complex for higher-order coupling."""
        self._simplices = simplices

    def step(self, coupling_matrix: list[list[float]]) -> float:
        """Advance phases with pairwise + higher-order Kuramoto terms."""
        new_phases = [0.0] * self._n
        for i in range(self._n):
            dtheta = self.frequencies[i]
            # Pairwise (classical Kuramoto)
            for j in range(self._n):
                if i != j:
                    dtheta += (
                        self._k1 * coupling_matrix[i][j] * math.sin(self.phases[j] - self.phases[i])
                    )
            # 3-body: Millán et al. (2020) simplicial Kuramoto
            triangles = self._simplices.get(2, [])
            for tri in triangles:
                if i in tri:
                    others = [v for v in tri if v != i]
                    if len(others) == 2:
                        j, k = others
                        dtheta += self._k2 * math.sin(
                            self.phases[j] + self.phases[k] - 2.0 * self.phases[i]
                        )
            # 4-body: generalized higher-order
            tetrahedra = self._simplices.get(3, [])
            for tet in tetrahedra:
                if i in tet:
                    others = [v for v in tet if v != i]
                    phase_sum = sum(self.phases[v] for v in others)
                    dtheta += self._k3 * math.sin(phase_sum - len(others) * self.phases[i])
            new_phases[i] = self.phases[i] + self._dt * dtheta
        self.phases = [p % (2 * math.pi) for p in new_phases]
        new_order = self.order_parameter()
        self._last_step_delta = new_order - self._prev_order
        self._prev_order = new_order
        return new_order

    def sync_delta(self) -> float:
        """Accumulated sync change from the most recent step() call."""
        return self._last_step_delta

    def order_parameter(self) -> float:
        """Kuramoto order parameter r = |1/N Σ exp(iθ_j)|."""
        re = sum(math.cos(p) for p in self.phases) / self._n
        im = sum(math.sin(p) for p in self.phases) / self._n
        return math.sqrt(re * re + im * im)

    def inject_phase(self, idx: int, phase: float) -> None:
        self.phases[idx] = phase % (2 * math.pi)


class FreeEnergyMinimizer:
    """Variational free energy minimization (Friston 2006, 2010).

    F = E_q[log q(s) - log p(o,s)] = KL[q(s)||p(s|o)] - log p(o)
    Minimizes surprise by updating internal model (recognition density).
    """

    __slots__ = ("_beliefs", "_precision", "_n", "_learning_rate")

    def __init__(self, n: int = 7, precision: float = 1.0, lr: float = 0.05):
        self._n = n
        self._precision = precision
        self._learning_rate = lr
        self._beliefs = [0.0] * n

    def prediction_error(self, observed: list[float]) -> list[float]:
        """Compute precision-weighted prediction error."""
        return [
            self._precision * (observed[i] - self._beliefs[i])
            for i in range(min(len(observed), self._n))
        ]

    def update_beliefs(self, observed: list[float]) -> float:
        """Gradient descent on free energy. Returns total free energy."""
        errors = self.prediction_error(observed)
        fe = 0.0
        for i in range(len(errors)):
            self._beliefs[i] += self._learning_rate * errors[i]
            fe += errors[i] ** 2
        return 0.5 * fe

    @property
    def beliefs(self) -> list[float]:
        return list(self._beliefs)


class GlobalBroadcast:
    """Global Workspace Theory broadcast (Baars 1988, Dehaene 2001).

    Winning coalition broadcasts to all modules simultaneously.
    Implements ignition threshold and competition dynamics.
    """

    __slots__ = ("_threshold", "_last_broadcast", "_ignition_count", "_n")

    def __init__(self, n: int = 7, threshold: float = 0.6):
        self._n = n
        self._threshold = threshold
        self._last_broadcast: list[float] | None = None
        self._ignition_count = 0

    def compete(self, module_activations: list[float]) -> int | None:
        """Winner-take-all competition. Returns winning module index or None."""
        if not module_activations:
            return None
        max_val = max(module_activations)
        if max_val < self._threshold:
            return None
        return module_activations.index(max_val)

    def broadcast(self, winner_idx: int, signal: list[float]) -> list[list[float]]:
        """Broadcast winning signal to all modules."""
        self._ignition_count += 1
        self._last_broadcast = list(signal)
        return [list(signal) for _ in range(self._n)]

    @property
    def ignition_rate(self) -> float:
        return self._ignition_count


class CouplingDynamics:
    """Orchestrates all coupling mechanisms across the simplicial resonance field.

    Combines: Hebbian plasticity, higher-order Kuramoto sync, free energy
    minimization, global broadcast, topology gating, and criticality-modulated gain.
    Emergence feeds back: near-critical states amplify coupling (self-organized criticality).
    """

    __slots__ = (
        "complex",
        "plasticity",
        "kuramoto",
        "free_energy",
        "broadcast",
        "topology_gate",
        "_tier",
        "_n_modules",
        "_state_dim",
        "_coupling_matrix",
        "_criticality_gain",
        "_dissipation_rate",
    )

    def __init__(self, n_modules: int = 7, state_dim: int = 8, tier: str = "lite"):
        from .topology_gate import TopologyGate

        self._n_modules = n_modules
        self._state_dim = state_dim
        self._tier = tier
        max_order = _TIER_MAX_ORDER.get(tier, 1)
        self.complex = SimplicialComplex(n=n_modules, max_order=max_order)
        n_channels = self.complex.total_directed
        self.plasticity = HebbianPlasticity(n_channels=n_channels)
        self.kuramoto = KuramotoSync(n=n_modules)
        self.kuramoto.set_simplices(self.complex.simplices)
        self.free_energy = FreeEnergyMinimizer(n=n_modules)
        self.broadcast = GlobalBroadcast(n=n_modules)
        self.topology_gate: TopologyGate | None = TopologyGate(
            n_channels=n_channels, n_modules=n_modules
        )
        self._coupling_matrix = [[0.0] * n_modules for _ in range(n_modules)]
        self._criticality_gain = 1.0
        self._dissipation_rate = 0.05
        self._rebuild_coupling_matrix()

    def set_criticality(self, criticality: float) -> None:
        """Feedback from emergence: near-critical → amplify coupling."""
        self._criticality_gain = 1.0 + criticality * 0.5

    def _rebuild_coupling_matrix(self) -> None:
        """Derive pairwise coupling matrix from simplicial weights, gated by topology."""
        mat = [[0.0] * self._n_modules for _ in range(self._n_modules)]
        channels = self.complex.directed_channels
        gate_values = self.topology_gate.gates if self.topology_gate is not None else None
        for ch_idx, (simplex, target) in enumerate(channels):
            w = self.plasticity.weights[ch_idx] if ch_idx < len(self.plasticity.weights) else 1.0
            # Apply topology gate: effective_weight = weight * gate
            if gate_values is not None and ch_idx < len(gate_values):
                w *= gate_values[ch_idx]
            for source in simplex:
                if source != target:
                    mat[source][target] += w / len(simplex)
        # Apply criticality gain
        for i in range(self._n_modules):
            for j in range(self._n_modules):
                mat[i][j] *= self._criticality_gain
        self._coupling_matrix = mat

    def step(self, module_activations: list[list[float]]) -> dict[str, Any]:
        """One coupling dynamics step. Updates plasticity, sync, and free energy."""
        # Compute channel activations from module co-activation
        channel_acts = self._compute_channel_activations(module_activations)
        self.plasticity.update(channel_acts)
        self._rebuild_coupling_matrix()

        # Kuramoto sync step
        sync_r = self.kuramoto.step(self._coupling_matrix)

        # Free energy from module activation magnitudes
        magnitudes = [
            sum(abs(x) for x in state) / max(1, len(state)) for state in module_activations
        ]
        fe = self.free_energy.update_beliefs(magnitudes)

        # Global broadcast competition
        winner = self.broadcast.compete(magnitudes)
        broadcast_signal = None
        if winner is not None and winner < len(module_activations):
            broadcast_signal = self.broadcast.broadcast(winner, module_activations[winner])

        return {
            "sync_order": sync_r,
            "free_energy": fe,
            "broadcast_winner": winner,
            "broadcast_signal": broadcast_signal,
            "active_ratio": self.plasticity.active_ratio,
        }

    def _compute_channel_activations(self, module_states: list[list[float]]) -> list[float]:
        """Compute activation level for each directed channel."""
        channels = self.complex.directed_channels
        activations = [0.0] * len(channels)
        for ch_idx, (simplex, target) in enumerate(channels):
            # Channel activation = product of source magnitudes × target receptivity
            source_energy = 0.0
            for v in simplex:
                if v != target and v < len(module_states):
                    source_energy += sum(abs(x) for x in module_states[v]) / max(1, self._state_dim)
            target_receptivity = 0.0
            if target < len(module_states):
                target_receptivity = 1.0 - sum(abs(x) for x in module_states[target]) / (
                    self._state_dim * 2
                )
                target_receptivity = max(0.0, target_receptivity)
            activations[ch_idx] = source_energy * target_receptivity / max(1, len(simplex) - 1)
        return activations

    def coupling_strength(self, source: int, target: int) -> float:
        """Get effective coupling strength between two modules."""
        if 0 <= source < self._n_modules and 0 <= target < self._n_modules:
            return self._coupling_matrix[source][target]
        return 0.0

    def feedback_topology(self, outcome: str, active_channels: list[int] | None = None) -> None:
        """Delegate feedback to the topology gate for topology learning."""
        if self.topology_gate is not None:
            self.topology_gate.update_from_feedback(outcome, active_channels)  # type: ignore[arg-type]

    def propagate(
        self, source_idx: int, signal: list[float], module_states: list[list[float]]
    ) -> list[list[float]]:
        """Propagate signal from source through coupling topology."""
        result = [list(s) for s in module_states]
        for target in range(self._n_modules):
            if target == source_idx:
                continue
            strength = self._coupling_matrix[source_idx][target]
            if strength > 0.01:
                for d in range(min(len(signal), len(result[target]))):
                    result[target][d] += signal[d] * strength
        return result

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "tier": self._tier,
            "plasticity": self.plasticity.to_dict(),
            "phases": list(self.kuramoto.phases),
            "beliefs": self.free_energy.beliefs,
            "coupling_matrix": [list(row) for row in self._coupling_matrix],
        }
        if self.topology_gate is not None:
            result["topology_gate"] = self.topology_gate.to_dict()
        return result

    def from_dict(self, data: dict[str, Any]) -> None:
        from .topology_gate import TopologyGate

        if "plasticity" in data:
            self.plasticity.from_dict(data["plasticity"])
            self._rebuild_coupling_matrix()
        if "phases" in data:
            self.kuramoto.phases = list(data["phases"])
        if "beliefs" in data:
            self.free_energy._beliefs = list(data["beliefs"])
        if "topology_gate" in data:
            self.topology_gate = TopologyGate.from_dict(data["topology_gate"])
        elif self.topology_gate is None:
            n_channels = self.complex.total_directed
            self.topology_gate = TopologyGate(n_channels=n_channels, n_modules=self._n_modules)
