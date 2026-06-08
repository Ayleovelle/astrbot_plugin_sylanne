"""Emergence detection for the simplicial resonance field.

Tracks and quantifies emergent properties: integrated information (Φ),
order parameters (Haken synergetics), attractor landscapes, resonance
detection, and temporal narrative depth.

Theoretical grounding:
- Tononi (2004, 2008): Integrated Information Theory (IIT)
- Haken (1983): synergetics, order parameters, slaving principle
- Strogatz (2000): nonlinear dynamics and chaos
- Prigogine (1977): dissipative structures, self-organization
- Maturana & Varela (1980): autopoiesis
- Hopfield (1982): energy-based attractor networks
- Friston (2010): free energy and active inference
"""

from __future__ import annotations

import math
from collections import deque
from typing import Any


class PhiCalculator:
    """Integrated Information (Φ) approximation.

    Φ measures how much a system is "more than the sum of its parts."
    Full IIT computation is NP-hard; we use a two-component approximation:

    1. Geometric: cross-module correlation (modules that move together = integrated)
    2. Temporal: mutual predictability across time (integrated systems are predictable)

    Φ = correlation_component * temporal_component
    This avoids the naive variance-ratio which can't distinguish "truly integrated"
    from "all driven by same input."
    """

    __slots__ = ("_history", "_window", "_last_phi")

    def __init__(self, window: int = 20):
        self._window = window
        self._history: deque[list[list[float]]] = deque(maxlen=window)
        self._last_phi = 0.0

    def update(self, module_states: list[list[float]]) -> float:
        """Compute Φ from current and historical module states."""
        self._history.append([list(s) for s in module_states])
        if len(self._history) < 3:
            return 0.0

        # Component 1: Cross-module correlation (spatial integration)
        # High when modules co-vary (not just co-driven)
        n_modules = len(module_states)
        total_corr = 0.0
        pairs = 0
        for i in range(n_modules):
            for j in range(i + 1, n_modules):
                corr = self._correlation(module_states[i], module_states[j])
                total_corr += abs(corr)
                pairs += 1
        spatial_phi = total_corr / max(1, pairs)

        # Component 2: Temporal coherence (does the whole predict better than parts?)
        # Compare: can we predict current from t-1 whole vs t-1 parts?
        temporal_phi = 0.0
        if len(self._history) >= 3:
            prev = self._history[-2]
            # Whole-system prediction error
            flat_prev = []
            flat_curr = []
            for s in prev:
                flat_prev.extend(s)
            for s in module_states:
                flat_curr.extend(s)
            whole_error = sum((a - b) ** 2 for a, b in zip(flat_curr, flat_prev))
            # Sum of per-module prediction errors
            parts_error = 0.0
            for i in range(n_modules):
                parts_error += sum(
                    (module_states[i][d] - prev[i][d]) ** 2
                    for d in range(min(len(module_states[i]), len(prev[i])))
                )
            # If whole predicts better than parts, system is integrated
            if parts_error > 0:
                temporal_phi = max(0.0, 1.0 - whole_error / parts_error)

        # Combined Φ: geometric mean of spatial and temporal
        phi = math.sqrt(max(0.0, spatial_phi) * max(0.0, spatial_phi + temporal_phi * 0.5))
        phi = min(1.0, phi)
        self._last_phi = phi
        return phi

    @staticmethod
    def _correlation(a: list[float], b: list[float]) -> float:
        n = min(len(a), len(b))
        if n == 0:
            return 0.0
        mean_a = sum(a[:n]) / n
        mean_b = sum(b[:n]) / n
        cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n))
        var_a = sum((a[i] - mean_a) ** 2 for i in range(n))
        var_b = sum((b[i] - mean_b) ** 2 for i in range(n))
        denom = math.sqrt(var_a * var_b)
        if denom < 1e-10:
            return 0.0
        return cov / denom

    @property
    def phi(self) -> float:
        return self._last_phi


class OrderParameterTracker:
    """Haken synergetics: track macroscopic order parameters.

    Near critical points, a few order parameters "enslave" the fast-relaxing
    modes. We track: synchronization (r), coherence (C), and criticality (χ).
    """

    __slots__ = (
        "_sync_history",
        "_coherence_history",
        "_criticality",
        "_window",
        "_last_order",
    )

    def __init__(self, window: int = 50):
        self._window = window
        self._sync_history: deque[float] = deque(maxlen=window)
        self._coherence_history: deque[float] = deque(maxlen=window)
        self._criticality = 0.0
        self._last_order: dict[str, float] = {}

    def update(self, sync_r: float, module_states: list[list[float]]) -> dict[str, float]:
        """Update order parameters from current field state."""
        self._sync_history.append(sync_r)

        # Coherence: average pairwise correlation between modules
        coherence = self._compute_coherence(module_states)
        self._coherence_history.append(coherence)

        # Criticality: variance of sync (high variance = near critical point)
        if len(self._sync_history) > 5:
            sync_list = list(self._sync_history)
            mean_s = sum(sync_list) / len(sync_list)
            var_s = sum((x - mean_s) ** 2 for x in sync_list) / len(sync_list)
            self._criticality = min(1.0, var_s * 10.0)
        else:
            self._criticality = 0.0

        self._last_order = {
            "synchronization": sync_r,
            "coherence": coherence,
            "criticality": self._criticality,
        }
        return self._last_order

    @staticmethod
    def _compute_coherence(states: list[list[float]]) -> float:
        n = len(states)
        if n < 2:
            return 0.0
        total_corr = 0.0
        pairs = 0
        for i in range(n):
            for j in range(i + 1, n):
                dot = sum(a * b for a, b in zip(states[i], states[j]))
                norm_i = math.sqrt(sum(x * x for x in states[i])) + 1e-10
                norm_j = math.sqrt(sum(x * x for x in states[j])) + 1e-10
                total_corr += dot / (norm_i * norm_j)
                pairs += 1
        return total_corr / max(1, pairs)

    @property
    def is_critical(self) -> bool:
        return self._criticality > 0.5

    @property
    def order(self) -> dict[str, float]:
        return dict(self._last_order)


class ResonanceDetector:
    """Detects resonance events: phase-locking, mode-locking, bifurcations.

    A resonance event occurs when the system transitions between attractors
    or achieves sudden synchronization (ignition in GWT terms).
    """

    __slots__ = (
        "_energy_history",
        "_sync_history",
        "_events",
        "_window",
        "_ignition_threshold",
    )

    def __init__(self, window: int = 30, ignition_threshold: float = 0.3):
        self._window = window
        self._ignition_threshold = ignition_threshold
        self._energy_history: deque[float] = deque(maxlen=window)
        self._sync_history: deque[float] = deque(maxlen=window)
        self._events: deque[dict[str, Any]] = deque(maxlen=100)

    def update(self, energy: float, sync_r: float, iteration: int) -> dict[str, Any] | None:
        """Check for resonance events. Returns event dict if detected."""
        self._energy_history.append(energy)
        self._sync_history.append(sync_r)

        event = None

        # Ignition: sudden sync jump
        if len(self._sync_history) > 2:
            delta_sync = sync_r - self._sync_history[-2]
            if delta_sync > self._ignition_threshold:
                event = {
                    "type": "ignition",
                    "delta_sync": delta_sync,
                    "iteration": iteration,
                    "energy": energy,
                }

        # Bifurcation: energy landscape shift
        if len(self._energy_history) > 5:
            recent = list(self._energy_history)[-5:]
            mean_e = sum(recent) / len(recent)
            if abs(energy - mean_e) > mean_e * 0.5 and mean_e > 0.01:
                event = event or {
                    "type": "bifurcation",
                    "energy_shift": energy - mean_e,
                    "iteration": iteration,
                }

        if event:
            self._events.append(event)
        return event

    @property
    def recent_events(self) -> list[dict[str, Any]]:
        return list(self._events)

    @property
    def event_rate(self) -> float:
        return len(self._events) / max(1, self._window)


class AttractorLandscape:
    """Tracks the system's attractor landscape via energy minima.

    Maintains a library of visited attractors (energy basins).
    Detects transitions between attractors and measures basin depth.
    """

    __slots__ = ("_attractors", "_current_basin", "_transition_count", "_max_attractors")

    def __init__(self, max_attractors: int = 20):
        self._attractors: list[dict[str, Any]] = []
        self._current_basin: int = -1
        self._transition_count = 0
        self._max_attractors = max_attractors

    def update(self, state_snapshot: list[float], energy: float) -> int:
        """Classify current state into attractor basin. Returns basin index."""
        # Find nearest attractor
        best_idx = -1
        best_dist = float("inf")
        for idx, attractor in enumerate(self._attractors):
            center = attractor["center"]
            dist = math.sqrt(
                sum((a - b) ** 2 for a, b in zip(state_snapshot[: len(center)], center))
            )
            if dist < best_dist:
                best_dist = dist
                best_idx = idx

        # Threshold for "same basin"
        basin_radius = 0.5
        if best_dist < basin_radius and best_idx >= 0:
            # Update attractor center (running average)
            attractor = self._attractors[best_idx]
            alpha = 0.1
            for i in range(len(attractor["center"])):
                if i < len(state_snapshot):
                    attractor["center"][i] = (1 - alpha) * attractor["center"][
                        i
                    ] + alpha * state_snapshot[i]
            attractor["visits"] += 1
            attractor["min_energy"] = min(attractor["min_energy"], energy)
            if best_idx != self._current_basin:
                self._transition_count += 1
            self._current_basin = best_idx
        else:
            # New attractor discovered
            if len(self._attractors) < self._max_attractors:
                self._attractors.append(
                    {
                        "center": list(state_snapshot[:16]),
                        "min_energy": energy,
                        "visits": 1,
                    }
                )
                new_idx = len(self._attractors) - 1
                if self._current_basin >= 0:
                    self._transition_count += 1
                self._current_basin = new_idx
            else:
                # Replace least-visited attractor
                min_visits = min(a["visits"] for a in self._attractors)
                for idx, a in enumerate(self._attractors):
                    if a["visits"] == min_visits:
                        self._attractors[idx] = {
                            "center": list(state_snapshot[:16]),
                            "min_energy": energy,
                            "visits": 1,
                        }
                        self._current_basin = idx
                        self._transition_count += 1
                        break

        return self._current_basin

    @property
    def n_attractors(self) -> int:
        return len(self._attractors)

    @property
    def current_basin(self) -> int:
        return self._current_basin

    @property
    def transition_rate(self) -> float:
        total_visits = sum(a["visits"] for a in self._attractors) if self._attractors else 1
        return self._transition_count / max(1, total_visits)


class TemporalNarrative:
    """Temporal depth and irreversible memory formation.

    Tracks the system's history as a narrative arc with:
    - Irreversibility: entropy production rate
    - Memory depth: how far back the current state "remembers"
    - Narrative tension: distance from equilibrium
    """

    __slots__ = (
        "_state_history",
        "_entropy_production",
        "_window",
        "_narrative_tension",
        "_memory_depth",
    )

    def __init__(self, window: int = 100):
        self._window = window
        self._state_history: deque[list[float]] = deque(maxlen=window)
        self._entropy_production: deque[float] = deque(maxlen=window)
        self._narrative_tension = 0.0
        self._memory_depth = 0

    def update(self, state: list[float]) -> dict[str, float]:
        """Update temporal narrative with new state."""
        self._state_history.append(list(state))

        # Entropy production: irreversibility measure
        if len(self._state_history) > 1:
            prev = self._state_history[-2]
            delta = [state[i] - prev[i] for i in range(min(len(state), len(prev)))]
            entropy_prod = sum(abs(d) for d in delta)
            self._entropy_production.append(entropy_prod)
        else:
            self._entropy_production.append(0.0)

        # Memory depth: autocorrelation decay length
        self._memory_depth = self._compute_memory_depth()

        # Narrative tension: distance from time-averaged state
        if len(self._state_history) > 5:
            n = len(self._state_history)
            dim = len(state)
            mean_state = [0.0] * dim
            for s in self._state_history:
                for i in range(min(dim, len(s))):
                    mean_state[i] += s[i]
            mean_state = [x / n for x in mean_state]
            self._narrative_tension = math.sqrt(
                sum((state[i] - mean_state[i]) ** 2 for i in range(dim))
            )
        else:
            self._narrative_tension = 0.0

        return {
            "entropy_production": self._entropy_production[-1],
            "memory_depth": self._memory_depth,
            "narrative_tension": self._narrative_tension,
            "irreversibility": self._irreversibility(),
        }

    def _compute_memory_depth(self) -> int:
        """How many steps back the current state correlates with."""
        if len(self._state_history) < 3:
            return 0
        current = self._state_history[-1]
        threshold = 0.3
        depth = 0
        for lag in range(1, min(20, len(self._state_history))):
            past = self._state_history[-(lag + 1)]
            corr = self._correlation(current, past)
            if corr > threshold:
                depth = lag
            else:
                break
        return depth

    @staticmethod
    def _correlation(a: list[float], b: list[float]) -> float:
        n = min(len(a), len(b))
        if n == 0:
            return 0.0
        dot = sum(a[i] * b[i] for i in range(n))
        norm_a = math.sqrt(sum(x * x for x in a[:n])) + 1e-10
        norm_b = math.sqrt(sum(x * x for x in b[:n])) + 1e-10
        return dot / (norm_a * norm_b)

    def _irreversibility(self) -> float:
        """Time-asymmetry measure: how different is forward vs backward."""
        if len(self._entropy_production) < 5:
            return 0.0
        prods = list(self._entropy_production)
        mean_prod = sum(prods) / len(prods)
        return min(1.0, mean_prod * 2.0)

    @property
    def tension(self) -> float:
        return self._narrative_tension

    @property
    def depth(self) -> int:
        return self._memory_depth


class EmergenceTracker:
    """Unified emergence tracking combining all detectors."""

    __slots__ = ("phi", "order", "resonance", "landscape", "narrative")

    def __init__(self, window: int = 50):
        self.phi = PhiCalculator(window=window)
        self.order = OrderParameterTracker(window=window)
        self.resonance = ResonanceDetector(window=window)
        self.landscape = AttractorLandscape()
        self.narrative = TemporalNarrative(window=window * 2)

    def update(
        self,
        module_states: list[list[float]],
        energy: float,
        sync_r: float,
        iteration: int,
    ) -> dict[str, Any]:
        """Full emergence update. Returns comprehensive emergence metrics."""
        phi_val = self.phi.update(module_states)
        order_params = self.order.update(sync_r, module_states)
        event = self.resonance.update(energy, sync_r, iteration)

        # Flatten for attractor/narrative tracking
        flat = []
        for s in module_states:
            flat.extend(s[:4])
        basin = self.landscape.update(flat, energy)
        temporal = self.narrative.update(flat)

        return {
            "phi": phi_val,
            "order_parameters": order_params,
            "resonance_event": event,
            "attractor_basin": basin,
            "n_attractors": self.landscape.n_attractors,
            "temporal": temporal,
            "is_critical": self.order.is_critical,
        }
