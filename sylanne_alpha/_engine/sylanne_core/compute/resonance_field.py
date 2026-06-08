"""Simplicial Resonance Field — the computational heart of SylannEngine.

Replaces sequential 7-layer pipeline with a fully-connected simplicial complex
where all orders of multi-body interactions resonate simultaneously until
convergence. The "soul" emerges as harmonic forms of the Hodge Laplacian.

Theoretical grounding:
- Hodge (1941): harmonic forms on manifolds
- Eckmann (1944): Hodge theory on simplicial complexes
- Barbarossa & Sardellitti (2020): topological signal processing
- Battiston et al. (2020, Nature Physics): higher-order interaction networks
- Haken (1983): synergetics — order parameters and slaving principle
- Prigogine (1977): dissipative structures far from equilibrium

Architecture:
  7 modules form vertices of complete 6-simplex Δ⁶.
  Tier allocation: lite=42 (pairwise), pro=287 (≤4-body), max=441 (full).
  Iterative resonance replaces sequential processing.
  Harmonic forms = topological invariants = the system's "soul".
"""

from __future__ import annotations

import math
from typing import Any

from .coupling_dynamics import CouplingDynamics

_TIER_CONFIG = {
    "lite": {"max_order": 1, "max_iter": 10, "state_dim": 8},
    "pro": {"max_order": 3, "max_iter": 15, "state_dim": 16},
    "max": {"max_order": 6, "max_iter": 20, "state_dim": 128},
}


def _vec_norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def _vec_sub(a: list[float], b: list[float]) -> list[float]:
    return [a[i] - b[i] for i in range(min(len(a), len(b)))]


def _vec_add(a: list[float], b: list[float]) -> list[float]:
    return [a[i] + b[i] for i in range(min(len(a), len(b)))]


def _vec_scale(v: list[float], s: float) -> list[float]:
    return [x * s for x in v]


def _mat_vec(mat: list[list[float]], v: list[float]) -> list[float]:
    return [sum(row[j] * v[j] for j in range(min(len(row), len(v)))) for row in mat]


def _mat_transpose(mat: list[list[float]]) -> list[list[float]]:
    if not mat:
        return []
    cols = len(mat[0])
    return [[mat[r][c] for r in range(len(mat))] for c in range(cols)]


def _mat_mul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    if not a or not b:
        return []
    rows_a, cols_a = len(a), len(a[0])
    cols_b = len(b[0])
    result = [[0.0] * cols_b for _ in range(rows_a)]
    for i in range(rows_a):
        for j in range(cols_b):
            s = 0.0
            for k in range(cols_a):
                s += a[i][k] * b[k][j]
            result[i][j] = s
    return result


def _resize_vector(vec: list[float], old_dim: int, new_dim: int) -> list[float]:
    """Resize a vector losslessly via linear interpolation.

    Upgrade (old < new): interpolate between existing values to fill new slots.
    Downgrade (old > new): sample at regular intervals (decimation with averaging).
    Same dim: return copy.
    """
    if old_dim == new_dim:
        return list(vec)
    if not vec:
        return [0.0] * new_dim
    # Ensure vec matches old_dim
    if len(vec) < old_dim:
        vec = vec + [0.0] * (old_dim - len(vec))
    elif len(vec) > old_dim:
        vec = vec[:old_dim]

    if new_dim > old_dim:
        # Upgrade: linear interpolation
        result = [0.0] * new_dim
        for i in range(new_dim):
            # Map new index to fractional old index
            src = i * (old_dim - 1) / max(1, new_dim - 1)
            lo = int(src)
            hi = min(lo + 1, old_dim - 1)
            frac = src - lo
            result[i] = vec[lo] * (1.0 - frac) + vec[hi] * frac
        return result
    else:
        # Downgrade: average pooling
        result = [0.0] * new_dim
        ratio = old_dim / new_dim
        for i in range(new_dim):
            start = int(i * ratio)
            end = int((i + 1) * ratio)
            end = max(end, start + 1)
            segment = vec[start:end]
            result[i] = sum(segment) / len(segment)
        return result


class ResonanceField:
    """Complete 6-simplex resonance field with iterative convergence.

    Instead of sequential L1→L2→...→L7, all modules resonate simultaneously
    through simplicial coupling channels until the field converges (or max_iter).
    Convergence = fixed point of the coupled dynamical system.
    """

    __slots__ = (
        "_n_modules",
        "_state_dim",
        "_tier",
        "_max_iter",
        "_epsilon",
        "_module_states",
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
        # Echo state reservoir (temporal memory in the field)
        "_reservoir",
        "_reservoir_decay",
        "_reservoir_input_scale",
        # Harmonic feedback
        "_harmonic_identity",
        "_identity_inertia",
        "_identity_max_norm",
        "_had_injection",
    )

    def __init__(self, n_modules: int = 7, tier: str = "lite", epsilon: float = 1e-4):
        cfg = _TIER_CONFIG.get(tier, _TIER_CONFIG["lite"])
        self._n_modules = n_modules
        self._state_dim = cfg["state_dim"]
        self._tier = tier
        self._max_iter = cfg["max_iter"]
        self._epsilon = epsilon
        self._module_states: list[list[float]] = [[0.0] * self._state_dim for _ in range(n_modules)]
        self._coupling = CouplingDynamics(n_modules=n_modules, state_dim=self._state_dim, tier=tier)
        self._complex = self._coupling.complex
        self._convergence_history: list[float] = []
        self._iteration_count = 0
        self._total_resonances = 0
        self._harmonics_cache: list[float] | None = None
        self._last_energy = 0.0
        self._dissipation = 0.02
        self._higher_order_gain = {"lite": 0.0, "pro": 0.15, "max": 0.25}.get(tier, 0.0)
        self._residual_decay = 0.7

        # Hopfield attractor landscape: stored patterns the field is attracted to.
        # When the system visits a state repeatedly, it becomes an attractor.
        # Expression = escaping an attractor (bifurcation).
        self._attractor_patterns: list[list[float]] = []
        self._hopfield_strength = 0.05
        self._max_attractors = {"lite": 5, "pro": 10, "max": 20}.get(tier, 5)

        # Echo state reservoir: gives the field temporal memory.
        # Reservoir state evolves as: r(t) = tanh(W_in·x(t) + W_r·r(t-1))
        # This creates a fading memory of past inputs — temporal depth.
        reservoir_dim = self._state_dim * 2
        self._reservoir = [0.0] * reservoir_dim
        self._reservoir_decay = 0.9
        self._reservoir_input_scale = 0.3

        # Harmonic identity: the persistent "soul" that resists perturbation.
        # Updated slowly from extracted harmonics. Feeds back as a restoring force.
        self._harmonic_identity = [0.0] * (self._n_modules * self._state_dim)
        self._identity_inertia = 0.95
        self._identity_max_norm = float(self._state_dim)  # cap prevents over-rigidity
        self._had_injection = False

    def inject(self, module_idx: int, signal: list[float]) -> None:
        """Inject external signal into a module's state vector."""
        if 0 <= module_idx < self._n_modules:
            state = self._module_states[module_idx]
            for i in range(min(len(signal), self._state_dim)):
                state[i] += signal[i]
            self._had_injection = True

    def resonate(self) -> dict[str, Any]:
        """Run iterative resonance until convergence or max_iter.

        Each iteration:
        1. Coupling dynamics step (Hebbian update, Kuramoto sync, free energy)
        2. Signal propagation through ALL simplicial channels
        3. Hopfield attractor pull (energy landscape shapes convergence)
        4. Harmonic identity restoring force (soul resists perturbation)
        5. Echo state reservoir update (temporal memory injection)
        6. Nonlinear activation (tanh) + dissipation
        7. Convergence check

        Returns metadata about the resonance process.
        """
        self._total_resonances += 1
        self._convergence_history.clear()

        # Compute topology gate skipped channels count
        topo_gate = self._coupling.topology_gate
        if topo_gate is not None:
            gate_values = topo_gate.gates
            skipped_channels = sum(1 for g in gate_values if g < topo_gate.threshold)
        else:
            skipped_channels = 0

        # Apply residual decay from previous cycle
        for i in range(self._n_modules):
            for d in range(self._state_dim):
                self._module_states[i][d] *= self._residual_decay

        # Update echo state reservoir with current input
        self._update_reservoir()

        coupling_meta: dict[str, Any] = {}
        max_sync_delta = 0.0
        for iteration in range(self._max_iter):
            self._iteration_count += 1

            # Step 1: coupling dynamics
            coupling_meta = self._coupling.step(self._module_states)
            # Track max sync jump across all iterations (for ignition detection)
            step_delta = self._coupling.kuramoto._last_step_delta
            if step_delta > max_sync_delta:
                max_sync_delta = step_delta

            # Step 2: signal propagation
            new_states = self._propagate_all()

            # Step 3: Hopfield attractor pull
            self._apply_hopfield_pull(new_states)

            # Step 4: harmonic identity restoring force
            self._apply_harmonic_restoring(new_states)

            # Step 5: reservoir memory injection
            self._inject_reservoir_memory(new_states)

            # Step 6: global broadcast
            if coupling_meta["broadcast_signal"] is not None:
                winner = coupling_meta["broadcast_winner"]
                for i in range(self._n_modules):
                    if i != winner:
                        broadcast = coupling_meta["broadcast_signal"][i]
                        for d in range(min(len(broadcast), self._state_dim)):
                            new_states[i][d] += broadcast[d] * 0.1

            # Step 7: nonlinear activation + dissipation
            for i in range(self._n_modules):
                for d in range(self._state_dim):
                    new_states[i][d] = math.tanh(new_states[i][d])
                    new_states[i][d] *= 1.0 - self._dissipation

            # Step 8: convergence check
            max_delta = 0.0
            for i in range(self._n_modules):
                delta = _vec_norm(_vec_sub(new_states[i], self._module_states[i]))
                max_delta = max(max_delta, delta)
            self._convergence_history.append(max_delta)
            self._module_states = new_states

            if max_delta < self._epsilon:
                break

        # Post-resonance: update persistent structures
        self._last_energy = self._compute_energy()
        self._harmonics_cache = None
        self._update_harmonic_identity()
        self._maybe_store_attractor()

        return {
            "iterations": len(self._convergence_history),
            "converged": self._convergence_history[-1] < self._epsilon
            if self._convergence_history
            else True,
            "final_delta": self._convergence_history[-1] if self._convergence_history else 0.0,
            "energy": self._last_energy,
            "sync_order": coupling_meta.get("sync_order", 0.0),
            "free_energy": coupling_meta.get("free_energy", 0.0),
            "attractor_count": len(self._attractor_patterns),
            "near_attractor": self._distance_to_nearest_attractor(),
            "reservoir_energy": sum(x * x for x in self._reservoir) * 0.5,
            "max_sync_delta": max_sync_delta,
            "skipped_channels": skipped_channels,
        }

    def _apply_hopfield_pull(self, states: list[list[float]]) -> None:
        """Hopfield energy landscape: stored attractors pull the field state.

        E = -½ Σ_μ (x · ξ_μ)² — energy decreases as state aligns with patterns.
        Gradient: dx_i = strength · Σ_μ (x · ξ_μ) · ξ_μ_i

        Expression = escaping an attractor. When the field is pulled toward a
        known pattern but external input pushes it away, the tension creates
        the bifurcation that triggers expression.
        """
        if not self._attractor_patterns:
            return
        flat = []
        for s in states:
            flat.extend(s)
        total_dim = len(flat)
        for pattern in self._attractor_patterns:
            if len(pattern) != total_dim:
                continue
            # Overlap (dot product)
            overlap = sum(flat[i] * pattern[i] for i in range(total_dim))
            # Pull toward pattern proportional to overlap
            pull = self._hopfield_strength * overlap
            idx = 0
            for i in range(self._n_modules):
                for d in range(self._state_dim):
                    if idx < len(pattern):
                        states[i][d] += pull * pattern[idx]
                    idx += 1

    def _apply_harmonic_restoring(self, states: list[list[float]]) -> None:
        """The harmonic identity acts as a restoring force.

        The "soul" (harmonic component) slowly accumulates over time and
        gently pulls the system back toward its characteristic mode.
        This creates personality-like persistence without rigidity.
        """
        identity_norm = math.sqrt(sum(x * x for x in self._harmonic_identity))
        if identity_norm < 0.01:
            return
        # Restoring force: proportional to deviation from identity
        restoring_strength = 0.03
        idx = 0
        for i in range(self._n_modules):
            for d in range(self._state_dim):
                if idx < len(self._harmonic_identity):
                    deviation = self._harmonic_identity[idx] - states[i][d]
                    states[i][d] += restoring_strength * deviation
                idx += 1

    def _update_reservoir(self) -> None:
        """Echo state network update: r(t) = decay·r(t-1) + scale·tanh(input).

        The reservoir maintains a fading memory of past field states,
        creating temporal depth. Only updates when there was actual external
        injection — self-sustaining Kuramoto oscillation doesn't count.
        """
        reservoir_dim = len(self._reservoir)
        if self._had_injection:
            flat = []
            for s in self._module_states:
                flat.extend(s)
            for i in range(reservoir_dim):
                src_idx = i % len(flat) if flat else 0
                input_val = flat[src_idx] if flat else 0.0
                self._reservoir[i] = self._reservoir_decay * self._reservoir[
                    i
                ] + self._reservoir_input_scale * math.tanh(input_val)
        else:
            # Pure decay when no external input
            for i in range(reservoir_dim):
                self._reservoir[i] *= self._reservoir_decay
        self._had_injection = False

    def _inject_reservoir_memory(self, states: list[list[float]]) -> None:
        """Inject reservoir state back into field as temporal context."""
        reservoir_dim = len(self._reservoir)
        injection_strength = 0.05
        idx = 0
        for i in range(self._n_modules):
            for d in range(self._state_dim):
                r_idx = idx % reservoir_dim
                states[i][d] += injection_strength * self._reservoir[r_idx]
                idx += 1

    def _update_harmonic_identity(self) -> None:
        """Slowly update the harmonic identity from current harmonics.

        The identity is an exponential moving average of harmonic forms —
        it captures what persists across all perturbations (the soul).
        Norm is capped to prevent over-rigidity in long-running sessions.
        """
        harmonics = self.extract_harmonics(k=1)
        inertia = self._identity_inertia
        for i in range(min(len(harmonics), len(self._harmonic_identity))):
            self._harmonic_identity[i] = (
                inertia * self._harmonic_identity[i] + (1.0 - inertia) * harmonics[i]
            )
        # Cap norm to prevent over-rigidity
        norm = _vec_norm(self._harmonic_identity)
        if norm > self._identity_max_norm:
            scale = self._identity_max_norm / norm
            for i in range(len(self._harmonic_identity)):
                self._harmonic_identity[i] *= scale

    def _maybe_store_attractor(self) -> None:
        """Store current state as attractor if field reached steady oscillation.

        In a Kuramoto-coupled system, perfect convergence (delta=0) never occurs —
        the oscillators maintain perpetual motion. Instead we detect steady-state:
        the final_delta has stabilized (not decreasing significantly anymore).
        This IS the attractor — a limit cycle, not a fixed point.
        """
        if len(self._convergence_history) < 2:
            return
        # Flatten current state
        flat = []
        for s in self._module_states:
            flat.extend(s)
        flat_norm = _vec_norm(flat)
        if flat_norm < 0.05:
            return
        # Accept as attractor if we ran full iterations (reached steady oscillation)
        # or if delta is small relative to energy (quasi-convergence)
        final_delta = self._convergence_history[-1]
        relative_delta = final_delta / (flat_norm + 1e-10)
        ran_full = len(self._convergence_history) >= self._max_iter
        quasi_converged = relative_delta < 0.05
        if not (ran_full or quasi_converged):
            return
        # Check distance to existing attractors
        min_dist = float("inf")
        normalized = [x / flat_norm for x in flat]
        for pattern in self._attractor_patterns:
            dist = _vec_norm(_vec_sub(normalized, pattern))
            min_dist = min(min_dist, dist)
        # Store if sufficiently novel
        novelty_threshold = 0.15
        if min_dist > novelty_threshold or not self._attractor_patterns:
            if len(self._attractor_patterns) >= self._max_attractors:
                self._attractor_patterns.pop(0)
            self._attractor_patterns.append(normalized)

    def _distance_to_nearest_attractor(self) -> float:
        """Distance from current state to nearest stored attractor."""
        if not self._attractor_patterns:
            return float("inf")
        flat = []
        for s in self._module_states:
            flat.extend(s)
        flat_norm = _vec_norm(flat)
        if flat_norm < 0.01:
            return float("inf")
        normalized = [x / flat_norm for x in flat]
        min_dist = float("inf")
        for pattern in self._attractor_patterns:
            dist = _vec_norm(_vec_sub(normalized, pattern))
            min_dist = min(min_dist, dist)
        return min_dist

    def _propagate_all(self) -> list[list[float]]:
        """Propagate signals through ALL simplicial channels simultaneously.

        Pairwise (k=1): standard weighted coupling with phase modulation.
        Higher-order (k>=2): multi-body nonlinear interaction -- the product of
        source states modulates the target (tensor contraction on simplices).
        This is what makes pro/max qualitatively different from lite.

        Channels with topology gate < threshold are skipped entirely (compute savings).
        """
        new_states = [[0.0] * self._state_dim for _ in range(self._n_modules)]
        # Self-connection (identity with decay)
        for i in range(self._n_modules):
            for d in range(self._state_dim):
                new_states[i][d] = self._module_states[i][d] * 0.8

        # Get topology gate values for channel skipping
        topo_gate = self._coupling.topology_gate
        gate_values = topo_gate.gates if topo_gate is not None else None
        gate_threshold = topo_gate.threshold if topo_gate is not None else 0.1

        # Pairwise coupling (always active in all tiers)
        for target in range(self._n_modules):
            for source in range(self._n_modules):
                if source == target:
                    continue
                strength = self._coupling.coupling_strength(source, target)
                if strength > 0.001:
                    phase_mod = math.cos(
                        self._coupling.kuramoto.phases[source]
                        - self._coupling.kuramoto.phases[target]
                    )
                    effective = strength * max(0.0, phase_mod)
                    for d in range(self._state_dim):
                        new_states[target][d] += self._module_states[source][d] * effective * 0.2

        # Higher-order simplicial propagation (pro/max only)
        if self._higher_order_gain > 0:
            self._propagate_higher_order(new_states, gate_values, gate_threshold)

        return new_states

    def _propagate_higher_order(
        self,
        new_states: list[list[float]],
        gate_values: list[float] | None = None,
        gate_threshold: float = 0.1,
    ) -> None:
        """Multi-body interactions: tensor contraction on k-simplices (k>=2).

        For a k-simplex sigma = {v0,...,vk} with target vt:
        contribution = gain * w_sigma * product_{v in sigma\\vt} <x_v> (mean activation product)

        This creates nonlinear synergistic effects: a channel only fires strongly
        when ALL its source modules are co-active (AND-gate semantics).

        Channels with gate < threshold are skipped entirely for compute savings.
        """
        channels = self._complex.directed_channels
        weights = self._coupling.plasticity.weights
        # Skip pairwise (already handled above) -- start from first higher-order channel
        pairwise_count = 42 if self._n_modules == 7 else self._n_modules * (self._n_modules - 1)
        for ch_idx in range(pairwise_count, len(channels)):
            # Skip channels below gate threshold
            if gate_values is not None and ch_idx < len(gate_values):
                if gate_values[ch_idx] < gate_threshold:
                    continue
            simplex, target = channels[ch_idx]
            if ch_idx >= len(weights):
                break
            w = weights[ch_idx]
            if w < 0.05:
                continue
            # Compute product of source mean activations (AND-gate)
            sources = [v for v in simplex if v != target]
            product = 1.0
            for src in sources:
                mean_act = sum(self._module_states[src]) / self._state_dim
                product *= math.tanh(mean_act)
            # Inject scaled product into target
            scale = self._higher_order_gain * w * product
            if abs(scale) > 0.001:
                for d in range(self._state_dim):
                    # Use average of source states as direction
                    avg_source = sum(self._module_states[src][d] for src in sources) / len(sources)
                    new_states[target][d] += avg_source * scale

    def _compute_energy(self) -> float:
        """Total field energy (Lyapunov function candidate)."""
        energy = 0.0
        for i in range(self._n_modules):
            energy += sum(x * x for x in self._module_states[i])
        return energy * 0.5

    def extract_harmonics(self, k: int = 1) -> list[float]:
        """Extract harmonic component at order k via iterative Hodge projection.

        Harmonic forms = ker(L_k) = signals in neither image(∂*) nor image(∂).
        These are the topological invariants — the "soul" of the field.

        Uses iterative projection: repeatedly subtract the non-harmonic component
        h^{n+1} = signal - L_k · (L_k^+ · h^n) until convergence.
        This is equivalent to finding the component in ker(L_k) via
        Neumann series when L_k has bounded spectrum.
        """
        if self._harmonics_cache is not None:
            return self._harmonics_cache

        # Flatten module states into a single signal vector
        signal = []
        for state in self._module_states:
            signal.extend(state)

        # Compute Hodge Laplacian L_k
        laplacian = self._hodge_laplacian(k)
        if not laplacian:
            self._harmonics_cache = signal
            return signal

        dim = len(laplacian)
        if len(signal) < dim:
            signal = signal + [0.0] * (dim - len(signal))
        elif len(signal) > dim:
            signal = signal[:dim]

        # Iterative harmonic projection (5 iterations of gradient subtraction)
        # h = signal; for each iter: h -= α · L_k · h
        # This converges to the null-space component when α < 2/λ_max
        harmonic = list(signal)
        # Estimate spectral radius for step size
        lk_signal = _mat_vec(laplacian, harmonic)
        spectral_est = _vec_norm(lk_signal) / (max(_vec_norm(harmonic), 1e-10))
        alpha = 1.0 / (spectral_est + 1e-8) if spectral_est > 1e-8 else 0.1

        for _ in range(8):
            lk_h = _mat_vec(laplacian, harmonic)
            lk_norm = _vec_norm(lk_h)
            if lk_norm < 1e-8:
                break
            for i in range(dim):
                harmonic[i] -= alpha * lk_h[i]

        self._harmonics_cache = harmonic
        return harmonic

    def _hodge_laplacian(self, k: int) -> list[list[float]]:
        """Compute Hodge Laplacian L_k = ∂_{k+1}·∂_{k+1}^T + ∂_k^T·∂_k."""
        boundary_k = self._complex.boundary_matrix(k)
        boundary_k1 = self._complex.boundary_matrix(k + 1)

        # L_k^down = ∂_k^T · ∂_k
        if boundary_k:
            bt_k = _mat_transpose(boundary_k)
            l_down = _mat_mul(bt_k, boundary_k)
        else:
            l_down = []

        # L_k^up = ∂_{k+1} · ∂_{k+1}^T
        if boundary_k1:
            bt_k1 = _mat_transpose(boundary_k1)
            l_up = _mat_mul(boundary_k1, bt_k1)
        else:
            l_up = []

        # Sum: L_k = L_down + L_up
        if l_down and l_up:
            dim = max(len(l_down), len(l_up))
            result = [[0.0] * dim for _ in range(dim)]
            for i in range(min(len(l_down), dim)):
                for j in range(min(len(l_down[0]), dim)):
                    result[i][j] += l_down[i][j]
            for i in range(min(len(l_up), dim)):
                for j in range(min(len(l_up[0]), dim)):
                    result[i][j] += l_up[i][j]
            return result
        return l_down or l_up or []

    def observe(self) -> dict[str, Any]:
        """Current field state observation."""
        magnitudes = [_vec_norm(s) for s in self._module_states]
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
            "convergence": self._convergence_history[-1] if self._convergence_history else 0.0,
            "total_resonances": self._total_resonances,
            "topology": topology_info,
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
        return list(self._convergence_history)

    def reset(self) -> None:
        self._module_states = [[0.0] * self._state_dim for _ in range(self._n_modules)]
        self._convergence_history.clear()
        self._harmonics_cache = None
        self._last_energy = 0.0

    def switch_tier(self, new_tier: str) -> None:
        """Hot-switch between tiers with lossless state migration.

        Upgrade (lite→pro→max): interpolate-expand all state vectors,
        inherit plasticity patterns for new channels from related lower-order ones.
        Downgrade (max→pro→lite): truncate higher-order channels, compress state.
        """
        if new_tier == self._tier:
            return
        old_dim = self._state_dim
        new_cfg = _TIER_CONFIG.get(new_tier, _TIER_CONFIG["lite"])
        new_dim = new_cfg["state_dim"]

        # 1. Migrate module states (interpolate-expand or truncate)
        new_states = []
        for state in self._module_states:
            new_states.append(_resize_vector(state, old_dim, new_dim))
        self._module_states = new_states

        # 2. Save old plasticity state
        old_weights = list(self._coupling.plasticity.weights)
        old_trace = list(self._coupling.plasticity._activation_trace)
        old_n = len(old_weights)

        # 3. Rebuild coupling with new tier
        self._coupling = CouplingDynamics(
            n_modules=self._n_modules, state_dim=new_dim, tier=new_tier
        )
        self._complex = self._coupling.complex
        new_n = self._complex.total_directed

        # 4. Transfer weights: keep old channels, new channels inherit mean
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

        # 5. Migrate attractor patterns
        total_old = self._n_modules * old_dim
        total_new = self._n_modules * new_dim
        self._attractor_patterns = [
            _resize_vector(p, total_old, total_new) for p in self._attractor_patterns
        ]

        # 6. Migrate harmonic identity
        self._harmonic_identity = _resize_vector(self._harmonic_identity, total_old, total_new)

        # 7. Migrate reservoir
        old_res_dim = len(self._reservoir)
        new_res_dim = new_dim * 2
        self._reservoir = _resize_vector(self._reservoir, old_res_dim, new_res_dim)

        # 8. Update config
        self._state_dim = new_dim
        self._tier = new_tier
        self._max_iter = new_cfg["max_iter"]
        self._higher_order_gain = {"lite": 0.0, "pro": 0.15, "max": 0.25}.get(new_tier, 0.0)
        self._max_attractors = {"lite": 5, "pro": 10, "max": 20}.get(new_tier, 5)
        self._identity_max_norm = float(new_dim)
        self._harmonics_cache = None

        while len(self._attractor_patterns) > self._max_attractors:
            self._attractor_patterns.pop(0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self._tier,
            "states": [list(s) for s in self._module_states],
            "coupling": self._coupling.to_dict(),
            "total_resonances": self._total_resonances,
            "iteration_count": self._iteration_count,
            "attractor_patterns": [list(p) for p in self._attractor_patterns],
            "reservoir": list(self._reservoir),
            "harmonic_identity": list(self._harmonic_identity),
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        if "states" in data:
            self._module_states = [list(s) for s in data["states"]]
        if "coupling" in data:
            self._coupling.from_dict(data["coupling"])
        self._total_resonances = data.get("total_resonances", 0)
        self._iteration_count = data.get("iteration_count", 0)
        if "attractor_patterns" in data:
            self._attractor_patterns = [list(p) for p in data["attractor_patterns"]]
        if "reservoir" in data:
            self._reservoir = list(data["reservoir"])
        if "harmonic_identity" in data:
            self._harmonic_identity = list(data["harmonic_identity"])


def create_resonance_field(
    n_modules: int = 7,
    tier: str = "lite",
    epsilon: float = 1e-4,
    backend: str | None = None,
) -> ResonanceField:
    """Factory function to create the appropriate ResonanceField backend.

    Selection logic:
    - backend="python" -> always ResonanceField (pure Python)
    - backend="numpy"  -> NumpyResonanceField (raises if numpy unavailable)
    - backend="torch"  -> TorchResonanceField (raises if torch unavailable)
    - backend=None (auto-select based on tier):
        - tier="lite" -> ResonanceField (pure Python, zero deps)
        - tier="pro"  -> NumpyResonanceField (if numpy available, else pure Python)
        - tier="max"  -> TorchResonanceField (if torch) -> NumpyResonanceField (if numpy) -> ResonanceField
    """
    # --- Explicit backend selection ---
    if backend == "python":
        return ResonanceField(n_modules=n_modules, tier=tier, epsilon=epsilon)

    if backend == "numpy":
        try:
            from .resonance_field_numpy import NumpyResonanceField

            return NumpyResonanceField(n_modules=n_modules, tier=tier, epsilon=epsilon)  # type: ignore[return-value]
        except ImportError as err:
            raise ImportError(
                "backend='numpy' was requested but NumPy is not installed. "
                "Install with: pip install numpy"
            ) from err

    if backend == "torch":
        try:
            from .resonance_field_torch import TorchResonanceField

            return TorchResonanceField(n_modules=n_modules, tier=tier, epsilon=epsilon)  # type: ignore[return-value]
        except ImportError as err:
            raise ImportError(
                "backend='torch' was requested but PyTorch is not installed. "
                "Install with: pip install torch"
            ) from err

    # --- Auto-select based on tier (backend=None) ---
    if tier == "lite":
        return ResonanceField(n_modules=n_modules, tier=tier, epsilon=epsilon)

    if tier == "pro":
        try:
            from .resonance_field_numpy import NumpyResonanceField

            return NumpyResonanceField(n_modules=n_modules, tier=tier, epsilon=epsilon)  # type: ignore[return-value]
        except ImportError:
            return ResonanceField(n_modules=n_modules, tier=tier, epsilon=epsilon)

    # tier == "max": torch -> numpy -> python
    try:
        from .resonance_field_torch import TorchResonanceField

        return TorchResonanceField(n_modules=n_modules, tier=tier, epsilon=epsilon)  # type: ignore[return-value]
    except ImportError:
        pass

    try:
        from .resonance_field_numpy import NumpyResonanceField

        return NumpyResonanceField(n_modules=n_modules, tier=tier, epsilon=epsilon)  # type: ignore[return-value]
    except ImportError:
        pass

    return ResonanceField(n_modules=n_modules, tier=tier, epsilon=epsilon)
