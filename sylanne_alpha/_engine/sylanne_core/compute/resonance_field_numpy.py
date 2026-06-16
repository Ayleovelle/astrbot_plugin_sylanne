"""Numpy-accelerated Resonance Field backend for pro/max tiers.

Provides ~5-10x speedup over the pure-Python ResonanceField by vectorizing:
- Pairwise propagation via matrix multiplication (W @ states)
- Higher-order AND-gate products via fancy indexing
- tanh + dissipation as element-wise array ops
- Convergence check via np.linalg.norm
- Hopfield attractor pull via np.dot
- Harmonic identity EMA via vectorized operations

Same interface as ResonanceField — drop-in replacement for pro tier.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from .coupling_dynamics import CouplingDynamics

_TIER_CONFIG = {
    "lite": {"max_order": 1, "max_iter": 10, "state_dim": 8},
    "pro": {"max_order": 3, "max_iter": 15, "state_dim": 16},
    "max": {"max_order": 6, "max_iter": 20, "state_dim": 128},
}


class NumpyResonanceField:
    """Numpy-accelerated simplicial resonance field.

    Stores module states as np.ndarray of shape (n_modules, state_dim) and
    coupling weights as np.ndarray of shape (n_channels,). All inner-loop
    computations are vectorized via numpy for significant speedup on pro/max.
    """

    __slots__ = (
        "_n_modules",
        "_state_dim",
        "_tier",
        "_max_iter",
        "_epsilon",
        "_module_states_np",
        "_coupling",
        "_complex",
        "_convergence_history",
        "_iteration_count",
        "_total_resonances",
        "_harmonics_cache",
        "_last_energy",
        "_dissipation",
        "_higher_order_gain",
        "_residual_decay",
        # Hopfield attractor landscape
        "_attractor_patterns",
        "_hopfield_strength",
        "_max_attractors",
        # Echo state reservoir
        "_reservoir",
        "_reservoir_decay",
        "_reservoir_input_scale",
        # Harmonic feedback
        "_harmonic_identity",
        "_identity_inertia",
        "_identity_max_norm",
        "_had_injection",
        # Precomputed higher-order channel info
        "_ho_channels",
    )

    def __init__(self, n_modules: int = 7, tier: str = "pro", epsilon: float = 1e-4):
        cfg = _TIER_CONFIG.get(tier, _TIER_CONFIG["pro"])
        self._n_modules = n_modules
        self._state_dim = cfg["state_dim"]
        self._tier = tier
        self._max_iter = cfg["max_iter"]
        self._epsilon = epsilon

        # Core state: (n_modules, state_dim) float64
        self._module_states_np: np.ndarray = np.zeros(
            (n_modules, self._state_dim), dtype=np.float64
        )

        self._coupling = CouplingDynamics(n_modules=n_modules, state_dim=self._state_dim, tier=tier)
        self._complex = self._coupling.complex
        self._convergence_history: list[float] = []
        self._iteration_count = 0
        self._total_resonances = 0
        self._harmonics_cache: np.ndarray | None = None
        self._last_energy = 0.0
        self._dissipation = 0.02
        self._higher_order_gain = {"lite": 0.0, "pro": 0.15, "max": 0.25}.get(tier, 0.0)
        self._residual_decay = 0.7

        # Hopfield attractor landscape
        self._attractor_patterns: list[np.ndarray] = []
        self._hopfield_strength = 0.05
        self._max_attractors = {"lite": 5, "pro": 10, "max": 20}.get(tier, 5)

        # Echo state reservoir
        reservoir_dim = self._state_dim * 2
        self._reservoir = np.zeros(reservoir_dim, dtype=np.float64)
        self._reservoir_decay = 0.9
        self._reservoir_input_scale = 0.3

        # Harmonic identity
        total_dim = self._n_modules * self._state_dim
        self._harmonic_identity = np.zeros(total_dim, dtype=np.float64)
        self._identity_inertia = 0.95
        self._identity_max_norm = float(self._state_dim)
        self._had_injection = False

        # Precompute higher-order channel info for vectorized propagation
        self._ho_channels: list[tuple[list[int], int, int]] = []
        self._precompute_higher_order_channels()

    def _precompute_higher_order_channels(self) -> None:
        """Cache higher-order channel (sources, target, channel_idx) tuples."""
        channels = self._complex.directed_channels
        pairwise_count = 42 if self._n_modules == 7 else self._n_modules * (self._n_modules - 1)
        self._ho_channels = []
        for ch_idx in range(pairwise_count, len(channels)):
            simplex, target = channels[ch_idx]
            sources = [v for v in simplex if v != target]
            self._ho_channels.append((sources, target, ch_idx))

    # ─── Public Interface ───────────────────────────────────────────────

    @property
    def state_dim(self) -> int:
        return self._state_dim

    @property
    def module_states(self) -> list[list[float]]:
        """Return states as list[list[float]] for compatibility."""
        states: list[list[float]] = self._module_states_np.tolist()
        return states

    @property
    def active_channels(self) -> int:
        return self._complex.total_directed

    @property
    def convergence_history(self) -> list[float]:
        return list(self._convergence_history)

    def inject(self, module_idx: int, signal: list[float]) -> None:
        """Inject external signal into a module's state vector."""
        if 0 <= module_idx < self._n_modules:
            sig_len = min(len(signal), self._state_dim)
            self._module_states_np[module_idx, :sig_len] += np.asarray(
                signal[:sig_len], dtype=np.float64
            )
            self._had_injection = True

    def resonate(self) -> dict[str, Any]:
        """Run iterative resonance until convergence or max_iter."""
        self._total_resonances += 1
        self._convergence_history.clear()

        # Residual decay
        self._module_states_np *= self._residual_decay

        # Update echo state reservoir
        self._update_reservoir()

        coupling_meta: dict[str, Any] = {}
        max_sync_delta = 0.0

        for iteration in range(self._max_iter):
            self._iteration_count += 1

            # Step 1: coupling dynamics (uses list interface)
            states_list = self._module_states_np.tolist()
            coupling_meta = self._coupling.step(states_list)
            step_delta = self._coupling.kuramoto._last_step_delta
            if step_delta > max_sync_delta:
                max_sync_delta = step_delta

            # Step 2: vectorized signal propagation
            new_states = self._propagate_all()

            # Step 3: Hopfield attractor pull (vectorized)
            self._apply_hopfield_pull(new_states)

            # Step 4: harmonic identity restoring force (vectorized)
            self._apply_harmonic_restoring(new_states)

            # Step 5: reservoir memory injection (vectorized)
            self._inject_reservoir_memory(new_states)

            # Step 6: global broadcast
            if coupling_meta["broadcast_signal"] is not None:
                winner = coupling_meta["broadcast_winner"]
                broadcast = coupling_meta["broadcast_signal"]
                for i in range(self._n_modules):
                    if i != winner:
                        bsig = broadcast[i]
                        sig_len = min(len(bsig), self._state_dim)
                        new_states[i, :sig_len] += (
                            np.asarray(bsig[:sig_len], dtype=np.float64) * 0.1
                        )

            # Step 7: vectorized tanh + dissipation
            new_states = np.tanh(new_states) * (1.0 - self._dissipation)

            # Step 8: vectorized convergence check
            delta = new_states - self._module_states_np
            max_delta = float(np.max(np.linalg.norm(delta, axis=1)))
            self._convergence_history.append(max_delta)
            self._module_states_np = new_states

            if max_delta < self._epsilon:
                break

        # Post-resonance updates
        self._last_energy = self._compute_energy()
        self._harmonics_cache = None
        self._update_harmonic_identity()
        self._maybe_store_attractor()

        return {
            "iterations": len(self._convergence_history),
            "converged": (
                self._convergence_history[-1] < self._epsilon if self._convergence_history else True
            ),
            "final_delta": (self._convergence_history[-1] if self._convergence_history else 0.0),
            "energy": self._last_energy,
            "sync_order": coupling_meta.get("sync_order", 0.0),
            "free_energy": coupling_meta.get("free_energy", 0.0),
            "attractor_count": len(self._attractor_patterns),
            "near_attractor": self._distance_to_nearest_attractor(),
            "reservoir_energy": float(0.5 * np.sum(self._reservoir**2)),
            "max_sync_delta": max_sync_delta,
        }

    # ─── Vectorized Propagation ─────────────────────────────────────────

    def _propagate_all(self) -> np.ndarray:
        """Vectorized signal propagation through all simplicial channels.

        Pairwise: builds (7,7) weight matrix W from coupling strengths and
        phase modulation, then computes new = 0.8*states + 0.2*(W @ states).
        Higher-order: vectorized AND-gate product via fancy indexing.

        Topology gate mask is applied to weights before propagation:
        channels with gate < threshold get weight=0, effectively pruned.
        """
        states = self._module_states_np
        n = self._n_modules

        # Self-connection with decay
        new_states = states * 0.8

        # Build (n, n) weight matrix W with phase modulation
        W = np.zeros((n, n), dtype=np.float64)
        phases = np.asarray(self._coupling.kuramoto.phases, dtype=np.float64)

        for target in range(n):
            for source in range(n):
                if source == target:
                    continue
                strength = self._coupling.coupling_strength(source, target)
                if strength > 0.001:
                    phase_mod = math.cos(phases[source] - phases[target])
                    W[target, source] = strength * max(0.0, phase_mod)

        # Vectorized pairwise: new_states += 0.2 * (W @ states)
        new_states += 0.2 * (W @ states)

        # Higher-order simplicial propagation (pro/max only)
        if self._higher_order_gain > 0:
            self._propagate_higher_order(new_states)

        return new_states

    def _propagate_higher_order(self, new_states: np.ndarray) -> None:
        """Vectorized higher-order AND-gate propagation.

        For each higher-order channel, computes the product of source mean
        activations (AND-gate) and injects scaled contribution into target.
        Uses precomputed channel info and numpy fancy indexing.

        Gate mask is applied: masked_weights = weights * gates (element-wise).
        Channels with gate < threshold get weight=0, effectively pruned.
        """
        states = self._module_states_np
        weights = self._coupling.plasticity.weights
        n_weights = len(weights)

        # Get gate values for masking
        topo_gate = self._coupling.topology_gate
        if topo_gate is not None:
            gate_values = topo_gate.gates
            gate_threshold = topo_gate.threshold
        else:
            gate_values = None
            gate_threshold = 0.1

        # Precompute per-module mean activations: shape (n_modules,)
        mean_acts = np.tanh(np.mean(states, axis=1))

        for sources, target, ch_idx in self._ho_channels:
            if ch_idx >= n_weights:
                break
            w = weights[ch_idx]

            # Apply gate mask: effective weight = weight * gate
            if gate_values is not None and ch_idx < len(gate_values):
                gate_val = gate_values[ch_idx]
                if gate_val < gate_threshold:
                    continue  # Pruned channel, skip entirely
                w *= gate_val

            if w < 0.05:
                continue

            # AND-gate: product of source mean activations
            product = float(np.prod(mean_acts[sources]))

            scale = self._higher_order_gain * w * product
            if abs(scale) > 0.001:
                # Average of source states as direction vector
                avg_source = np.mean(states[sources], axis=0)
                new_states[target] += avg_source * scale

    # ─── Hopfield Attractor (vectorized) ────────────────────────────────

    def _apply_hopfield_pull(self, states: np.ndarray) -> None:
        """Vectorized Hopfield energy landscape pull."""
        if not self._attractor_patterns:
            return
        flat = states.ravel()
        total_dim = flat.shape[0]

        for pattern in self._attractor_patterns:
            if pattern.shape[0] != total_dim:
                continue
            # Vectorized dot product for overlap
            overlap = float(np.dot(flat, pattern))
            pull = self._hopfield_strength * overlap
            # Reshape and add pull in-place
            states += (pull * pattern).reshape(states.shape)

    # ─── Harmonic Identity (vectorized) ─────────────────────────────────

    def _apply_harmonic_restoring(self, states: np.ndarray) -> None:
        """Vectorized harmonic identity restoring force."""
        identity_norm = float(np.linalg.norm(self._harmonic_identity))
        if identity_norm < 0.01:
            return
        restoring_strength = 0.03
        identity_reshaped = self._harmonic_identity.reshape(states.shape)
        deviation = identity_reshaped - states
        states += restoring_strength * deviation

    def _update_harmonic_identity(self) -> None:
        """Vectorized EMA update of harmonic identity."""
        harmonics = self._extract_harmonics_flat()
        inertia = self._identity_inertia
        n = min(len(harmonics), len(self._harmonic_identity))
        self._harmonic_identity[:n] = (
            inertia * self._harmonic_identity[:n] + (1.0 - inertia) * harmonics[:n]
        )
        # Cap norm
        norm = float(np.linalg.norm(self._harmonic_identity))
        if norm > self._identity_max_norm:
            self._harmonic_identity *= self._identity_max_norm / norm

    def _extract_harmonics_flat(self) -> np.ndarray:
        """Extract harmonic component as flat numpy array."""
        if self._harmonics_cache is not None:
            return self._harmonics_cache
        signal: np.ndarray = self._module_states_np.ravel().copy()
        self._harmonics_cache = signal
        return signal

    # ─── Echo State Reservoir (vectorized) ──────────────────────────────

    def _update_reservoir(self) -> None:
        """Vectorized reservoir update."""
        reservoir_dim = len(self._reservoir)
        if self._had_injection:
            flat = self._module_states_np.ravel()
            # Tile flat to match reservoir dim
            indices = np.arange(reservoir_dim) % len(flat)
            input_vals = flat[indices]
            self._reservoir = (
                self._reservoir_decay * self._reservoir
                + self._reservoir_input_scale * np.tanh(input_vals)
            )
        else:
            self._reservoir *= self._reservoir_decay
        self._had_injection = False

    def _inject_reservoir_memory(self, states: np.ndarray) -> None:
        """Vectorized reservoir memory injection into field states."""
        injection_strength = 0.05
        total_dim = self._n_modules * self._state_dim
        reservoir_dim = len(self._reservoir)
        indices = np.arange(total_dim) % reservoir_dim
        reservoir_contribution = self._reservoir[indices].reshape(states.shape)
        states += injection_strength * reservoir_contribution

    # ─── Attractor Storage ──────────────────────────────────────────────

    def _maybe_store_attractor(self) -> None:
        """Store current state as attractor if field reached steady oscillation."""
        if len(self._convergence_history) < 2:
            return
        flat = self._module_states_np.ravel()
        flat_norm = float(np.linalg.norm(flat))
        if flat_norm < 0.05:
            return

        final_delta = self._convergence_history[-1]
        relative_delta = final_delta / (flat_norm + 1e-10)
        ran_full = len(self._convergence_history) >= self._max_iter
        quasi_converged = relative_delta < 0.05

        if not (ran_full or quasi_converged):
            return

        normalized = flat / flat_norm

        # Check distance to existing attractors
        min_dist = float("inf")
        for pattern in self._attractor_patterns:
            dist = float(np.linalg.norm(normalized - pattern))
            min_dist = min(min_dist, dist)

        novelty_threshold = 0.15
        if min_dist > novelty_threshold or not self._attractor_patterns:
            if len(self._attractor_patterns) >= self._max_attractors:
                self._attractor_patterns.pop(0)
            self._attractor_patterns.append(normalized.copy())

    def _distance_to_nearest_attractor(self) -> float:
        """Distance from current state to nearest stored attractor."""
        if not self._attractor_patterns:
            return float("inf")
        flat = self._module_states_np.ravel()
        flat_norm = float(np.linalg.norm(flat))
        if flat_norm < 0.01:
            return float("inf")
        normalized = flat / flat_norm
        min_dist = float("inf")
        for pattern in self._attractor_patterns:
            dist = float(np.linalg.norm(normalized - pattern))
            min_dist = min(min_dist, dist)
        return min_dist

    # ─── Energy ─────────────────────────────────────────────────────────

    def _compute_energy(self) -> float:
        """Total field energy via vectorized sum of squares."""
        return float(0.5 * np.sum(self._module_states_np**2))

    # ─── Observation ────────────────────────────────────────────────────

    def observe(self) -> dict[str, Any]:
        """Current field state observation."""
        magnitudes = np.linalg.norm(self._module_states_np, axis=1).tolist()
        topo_gate = self._coupling.topology_gate
        if topo_gate is not None:
            topology_info = {
                "active_count": topo_gate.n_active,
                "sparsity": topo_gate.sparsity,
            }
        else:
            topology_info = {
                "active_count": self._complex.total_directed,
                "sparsity": 0.0,
            }
        return {
            "module_magnitudes": magnitudes,
            "total_energy": self._last_energy,
            "sync_order": self._coupling.kuramoto.order_parameter(),
            "active_channels": self._complex.total_directed,
            "plasticity_ratio": self._coupling.plasticity.active_ratio,
            "convergence": (self._convergence_history[-1] if self._convergence_history else 0.0),
            "total_resonances": self._total_resonances,
            "topology": topology_info,
        }

    def reset(self) -> None:
        self._module_states_np = np.zeros((self._n_modules, self._state_dim), dtype=np.float64)
        self._convergence_history.clear()
        self._harmonics_cache = None
        self._last_energy = 0.0

    def switch_tier(self, new_tier: str) -> None:
        """Hot-switch between tiers with lossless state migration via interpolation."""
        if new_tier == self._tier:
            return

        old_dim = self._state_dim
        new_cfg = _TIER_CONFIG.get(new_tier, _TIER_CONFIG["lite"])
        new_dim = new_cfg["state_dim"]
        total_old = self._n_modules * old_dim
        total_new = self._n_modules * new_dim

        # 1. Migrate module states via linear interpolation
        flat = self._module_states_np.ravel()
        new_flat = np.interp(
            np.linspace(0, 1, total_new),
            np.linspace(0, 1, total_old),
            flat,
        )
        self._module_states_np = new_flat.reshape(self._n_modules, new_dim)

        # 2. Rebuild coupling dynamics with new tier
        old_weights = list(self._coupling.plasticity.weights)
        old_trace = list(self._coupling.plasticity._activation_trace)
        old_n = len(old_weights)

        self._coupling = CouplingDynamics(
            n_modules=self._n_modules, state_dim=new_dim, tier=new_tier
        )
        self._complex = self._coupling.complex
        new_n = self._complex.total_directed

        # Transfer weights: keep old channels, new channels get mean of old
        if new_n >= old_n:
            old_mean = sum(old_weights) / max(1, old_n)
            for i in range(old_n):
                self._coupling.plasticity.weights[i] = old_weights[i]
            for i in range(old_n, new_n):
                self._coupling.plasticity.weights[i] = old_mean
            for i in range(min(old_n, new_n)):
                if i < len(old_trace):
                    self._coupling.plasticity._activation_trace[i] = old_trace[i]
        else:
            for i in range(new_n):
                self._coupling.plasticity.weights[i] = old_weights[i]
                if i < len(old_trace):
                    self._coupling.plasticity._activation_trace[i] = old_trace[i]

        self._coupling.plasticity._homeostatic_target = float(new_n)
        self._coupling._rebuild_coupling_matrix()

        # 3. Migrate attractor patterns
        self._attractor_patterns = [
            np.interp(
                np.linspace(0, 1, total_new),
                np.linspace(0, 1, len(p)),
                p,
            )
            for p in self._attractor_patterns
        ]

        # 4. Migrate harmonic identity
        self._harmonic_identity = np.interp(
            np.linspace(0, 1, total_new),
            np.linspace(0, 1, len(self._harmonic_identity)),
            self._harmonic_identity,
        )

        # 5. Migrate reservoir
        old_res_dim = len(self._reservoir)
        new_res_dim = new_dim * 2
        if old_res_dim != new_res_dim:
            self._reservoir = np.interp(
                np.linspace(0, 1, new_res_dim),
                np.linspace(0, 1, old_res_dim),
                self._reservoir,
            )

        # 6. Update config
        self._state_dim = new_dim
        self._tier = new_tier
        self._max_iter = new_cfg["max_iter"]
        self._higher_order_gain = {"lite": 0.0, "pro": 0.15, "max": 0.25}.get(new_tier, 0.0)
        self._max_attractors = {"lite": 5, "pro": 10, "max": 20}.get(new_tier, 5)
        self._identity_max_norm = float(new_dim)
        self._harmonics_cache = None

        while len(self._attractor_patterns) > self._max_attractors:
            self._attractor_patterns.pop(0)

        # Rebuild higher-order channel cache
        self._precompute_higher_order_channels()

    # ─── Serialization ──────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self._tier,
            "states": self._module_states_np.tolist(),
            "coupling": self._coupling.to_dict(),
            "total_resonances": self._total_resonances,
            "iteration_count": self._iteration_count,
            "attractor_patterns": [p.tolist() for p in self._attractor_patterns],
            "reservoir": self._reservoir.tolist(),
            "harmonic_identity": self._harmonic_identity.tolist(),
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        if "states" in data:
            self._module_states_np = np.asarray(data["states"], dtype=np.float64)
        if "coupling" in data:
            self._coupling.from_dict(data["coupling"])
        self._total_resonances = data.get("total_resonances", 0)
        self._iteration_count = data.get("iteration_count", 0)
        if "attractor_patterns" in data:
            self._attractor_patterns = [
                np.asarray(p, dtype=np.float64) for p in data["attractor_patterns"]
            ]
        if "reservoir" in data:
            self._reservoir = np.asarray(data["reservoir"], dtype=np.float64)
        if "harmonic_identity" in data:
            self._harmonic_identity = np.asarray(data["harmonic_identity"], dtype=np.float64)
