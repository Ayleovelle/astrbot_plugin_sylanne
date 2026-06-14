"""Learnable coupling topology gate for the simplicial resonance field.

Discovers optimal sparse topologies from interaction feedback by maintaining
differentiable gate parameters for each of the 441 directed channels in the
complete 6-simplex. Channels are smoothly masked via sigmoid gates, allowing
gradient-free learning from accept/reject/ignore feedback signals.

Theoretical grounding:
- Louizos et al. (2018): Learning Sparse Networks Through L0 Regularization
- Frankle & Carlin (2019): Lottery Ticket Hypothesis
- Edelman (1987): Neural Darwinism — selective stabilization
- Friston (2006): Free energy and synaptic pruning
- Zador (2019): A critique of pure learning — innate priors matter

Design principles:
- Gates are stored as logits (unconstrained) and passed through sigmoid
- Personality provides an innate prior (nature), feedback provides learning (nurture)
- Homeostatic regularization prevents catastrophic pruning
- Minimum connectivity per module ensures no module becomes isolated
"""

from __future__ import annotations

import math
from typing import Any, Literal

# ---------------------------------------------------------------------------
# NumPy availability detection — fall back to pure Python math
# ---------------------------------------------------------------------------

try:
    import numpy as np

    _HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore[assignment]
    _HAS_NUMPY = False


# ---------------------------------------------------------------------------
# Utility functions (dual-mode: numpy or pure Python)
# ---------------------------------------------------------------------------


def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid for a single float."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    exp_x = math.exp(x)
    return exp_x / (1.0 + exp_x)


def _sigmoid_vec(logits: list[float]) -> list[float]:
    """Apply sigmoid element-wise to a list of logits."""
    if _HAS_NUMPY:
        arr = np.array(logits, dtype=np.float64)
        result: list[float] = (1.0 / (1.0 + np.exp(-np.clip(arr, -500, 500)))).tolist()
        return result
    return [_sigmoid(x) for x in logits]


def _channel_order(channel_idx: int, n_modules: int = 7) -> int:
    """Determine the simplex order (k) for a given directed channel index.

    For 7 modules, the channel layout is:
    - Order 1 (pairwise): 7*6 = 42 channels (indices 0..41)
    - Order 2 (3-body):   C(7,3)*3 = 105 channels (indices 42..146)
    - Order 3 (4-body):   C(7,4)*4 = 140 channels (indices 147..286)
    - Order 4 (5-body):   C(7,5)*5 = 105 channels (indices 287..391)
    - Order 5 (6-body):   C(7,6)*6 = 42 channels (indices 392..433)
    - Order 6 (7-body):   C(7,7)*7 = 7 channels (indices 434..440)
    """
    # Precomputed cumulative counts for n=7
    if n_modules == 7:
        boundaries = [42, 147, 287, 392, 434, 441]
        for order, boundary in enumerate(boundaries, start=1):
            if channel_idx < boundary:
                return order
    # Fallback: compute dynamically
    cumulative = 0
    for k in range(1, n_modules):
        from math import comb

        count = comb(n_modules, k + 1) * (k + 1)
        cumulative += count
        if channel_idx < cumulative:
            return k
    return n_modules - 1


def _channel_target_module(channel_idx: int, n_modules: int = 7) -> int:
    """Determine which module is the target of a given directed channel.

    Uses the same layout as SimplicialComplex._build(): for each simplex,
    channels are created for each vertex in the simplex as target.
    """
    from itertools import combinations

    idx = 0
    for k in range(1, n_modules):
        for simplex in combinations(range(n_modules), k + 1):
            for target_vertex in simplex:
                if idx == channel_idx:
                    return target_vertex
                idx += 1
    return 0


# ---------------------------------------------------------------------------
# Personality-to-prior mapping
# ---------------------------------------------------------------------------


def personality_to_gate_prior(personality: dict[str, float], n_channels: int = 441) -> list[float]:
    """Convert personality traits to initial gate logits (innate prior).

    Args:
        personality: Dict with keys like "openness", "conscientiousness",
                     "extraversion", "agreeableness", "neuroticism".
                     Values in [0, 1].
        n_channels: Number of directed channels (default 441 for full 6-simplex).

    Returns:
        List of logit values (pre-sigmoid) for each channel.

    Mapping logic:
    - High openness -> more channels start open (positive logit bias)
    - High conscientiousness -> moderate initial gates (conservative start)
    - Pairwise channels get higher prior than higher-order ones
    - The prior encodes "nature" — feedback provides "nurture"
    """
    openness = personality.get("openness", 0.5)
    conscientiousness = personality.get("conscientiousness", 0.5)
    extraversion = personality.get("extraversion", 0.5)

    # Base logit: openness shifts the overall activation level
    # sigmoid(0) = 0.5, sigmoid(2) ≈ 0.88, sigmoid(-2) ≈ 0.12
    base_logit = (openness - 0.5) * 4.0  # Range: [-2, 2]

    # Conscientiousness modulates spread: high C -> tighter distribution
    spread_factor = 1.0 - conscientiousness * 0.5  # Range: [0.5, 1.0]

    # Extraversion boosts pairwise (social) channels
    pairwise_boost = extraversion * 1.5

    logits = [0.0] * n_channels
    for i in range(n_channels):
        order = _channel_order(i)
        # Higher-order channels get progressively lower prior
        # Order 1: full base, Order 6: base - 3.0
        order_penalty = (order - 1) * 0.6 * spread_factor
        logit = base_logit - order_penalty
        # Pairwise boost from extraversion
        if order == 1:
            logit += pairwise_boost
        logits[i] = logit

    return logits


# ---------------------------------------------------------------------------
# TopologyGate class
# ---------------------------------------------------------------------------


class TopologyGate:
    """Learnable gate over the 441 directed channels of the resonance field.

    Each channel has a gate parameter g_i in (0, 1) stored internally as a
    logit (pre-sigmoid) for unconstrained optimization. The effective channel
    weight is: effective_weight_i = original_weight_i * sigmoid(logit_i).

    Channels with gate < threshold are considered inactive (pruned).
    The system learns which channels to keep from interaction feedback.

    Attributes:
        n_channels: Number of directed channels (441 for complete 6-simplex).
        threshold: Gate value below which a channel is considered inactive.
        n_modules: Number of modules in the simplex (default 7).
        min_channels_per_module: Minimum incoming channels per module.
        max_total_active: Optional upper bound on total active channels.
    """

    __slots__ = (
        "n_channels",
        "n_modules",
        "threshold",
        "min_channels_per_module",
        "max_total_active",
        "_logits",
        "_learning_rate",
        "_decay_rate",
        "_openness_lr_mod",
        "_conscientiousness_decay_mod",
        "_total_updates",
        "_feedback_counts",
    )

    def __init__(
        self,
        n_channels: int = 441,
        n_modules: int = 7,
        threshold: float = 0.1,
        min_channels_per_module: int = 3,
        max_total_active: int | None = None,
        personality: dict[str, float] | None = None,
        learning_rate: float = 0.1,
        decay_rate: float = 0.01,
    ):
        """Initialize the topology gate.

        Args:
            n_channels: Number of directed channels to gate.
            n_modules: Number of modules (vertices) in the simplex.
            threshold: Gate activation threshold for considering a channel active.
            min_channels_per_module: Minimum active incoming channels per module.
            max_total_active: Optional cap on total active channels.
            personality: Optional personality dict for prior initialization.
            learning_rate: Base learning rate for feedback updates.
            decay_rate: Rate of entropy-regularization decay on "ignored" feedback.
        """
        self.n_channels = n_channels
        self.n_modules = n_modules
        self.threshold = threshold
        self.min_channels_per_module = min_channels_per_module
        self.max_total_active = max_total_active
        self._learning_rate = learning_rate
        self._decay_rate = decay_rate
        self._total_updates = 0
        self._feedback_counts: dict[str, int] = {
            "accepted": 0,
            "rejected": 0,
            "ignored": 0,
        }

        # Personality modulation
        openness = 0.5
        conscientiousness = 0.5
        if personality is not None:
            openness = personality.get("openness", 0.5)
            conscientiousness = personality.get("conscientiousness", 0.5)

        # Openness -> faster learning (more plastic)
        self._openness_lr_mod = 0.5 + openness  # Range: [0.5, 1.5]
        # Conscientiousness -> slower gate decay (harder to prune)
        self._conscientiousness_decay_mod = 1.0 - conscientiousness * 0.7  # Range: [0.3, 1.0]

        # Initialize logits from personality prior or default
        if personality is not None:
            self._logits = personality_to_gate_prior(personality, n_channels)
        else:
            # Default: all channels start moderately open (sigmoid(1.0) ≈ 0.73)
            self._logits = [1.0] * n_channels

        # Enforce minimum connectivity constraint on initialization
        self._enforce_min_connectivity()

    # ------------------------------------------------------------------
    # Core gate computation
    # ------------------------------------------------------------------

    @property
    def gates(self) -> list[float]:
        """Current gate values (sigmoid of logits), each in (0, 1)."""
        return _sigmoid_vec(self._logits)

    @property
    def active_mask(self) -> list[bool]:
        """Boolean mask: True if gate > threshold."""
        gate_values = self.gates
        return [g > self.threshold for g in gate_values]

    @property
    def n_active(self) -> int:
        """Number of currently active channels."""
        return sum(self.active_mask)

    @property
    def sparsity(self) -> float:
        """Fraction of channels that are inactive (pruned)."""
        return 1.0 - self.n_active / max(1, self.n_channels)

    # ------------------------------------------------------------------
    # Integration hooks
    # ------------------------------------------------------------------

    def apply_gates(self, weights: list[float] | Any) -> list[float]:
        """Multiply channel weights by their gate values (smooth masking).

        Args:
            weights: Original channel weights (list or numpy array).

        Returns:
            Gated weights as a list of floats.
        """
        gate_values = self.gates
        if _HAS_NUMPY and hasattr(weights, "__array__"):
            w_arr = np.asarray(weights, dtype=np.float64)
            g_arr = np.array(gate_values, dtype=np.float64)
            gated: list[float] = (w_arr * g_arr).tolist()
            return gated
        # Pure Python path
        n = min(len(weights), len(gate_values))
        return [weights[i] * gate_values[i] for i in range(n)]

    def get_active_channels(self) -> list[int]:
        """Return indices of channels with gate > threshold."""
        gate_values = self.gates
        return [i for i, g in enumerate(gate_values) if g > self.threshold]

    # ------------------------------------------------------------------
    # Learning from feedback
    # ------------------------------------------------------------------

    def update_from_feedback(
        self,
        outcome: Literal["accepted", "rejected", "ignored"],
        active_channels: list[int] | None = None,
    ) -> None:
        """Update gate logits based on interaction feedback.

        Args:
            outcome: The feedback signal.
                - "accepted": reinforce gates of active channels (they contributed
                  to a good expression).
                - "rejected": weaken gates of active channels (they led to a bad
                  expression).
                - "ignored": slight decay on all gates (entropy regularization,
                  encourages pruning of unused channels).
            active_channels: Indices of channels that were active during this tick.
                If None, uses all currently active channels.
        """
        self._total_updates += 1
        self._feedback_counts[outcome] = self._feedback_counts.get(outcome, 0) + 1

        effective_lr = self._learning_rate * self._openness_lr_mod

        if outcome == "accepted":
            # Reinforce: increase logits of active channels
            channels = (
                active_channels if active_channels is not None else self.get_active_channels()
            )
            for idx in channels:
                if 0 <= idx < self.n_channels:
                    self._logits[idx] += effective_lr * 0.5

        elif outcome == "rejected":
            # Weaken: decrease logits of active channels
            channels = (
                active_channels if active_channels is not None else self.get_active_channels()
            )
            for idx in channels:
                if 0 <= idx < self.n_channels:
                    self._logits[idx] -= effective_lr * 0.3

        elif outcome == "ignored":
            # Entropy regularization: slight decay on ALL gates
            decay = self._decay_rate * self._conscientiousness_decay_mod
            if _HAS_NUMPY:
                arr = np.array(self._logits, dtype=np.float64)
                arr -= decay
                self._logits = arr.tolist()
            else:
                for i in range(self.n_channels):
                    self._logits[i] -= decay

        # Post-update: enforce constraints
        self._enforce_min_connectivity()
        self._homeostatic_normalization()

    # ------------------------------------------------------------------
    # Topology regularization
    # ------------------------------------------------------------------

    def _enforce_min_connectivity(self) -> None:
        """Ensure each module has at least min_channels_per_module incoming channels.

        If a module drops below the minimum, boost its weakest gates back
        above threshold. This prevents module isolation.
        """
        gate_values = self.gates
        # Group channels by target module
        for module_idx in range(self.n_modules):
            incoming_indices = []
            for ch_idx in range(self.n_channels):
                target = _channel_target_module(ch_idx, self.n_modules)
                if target == module_idx:
                    incoming_indices.append(ch_idx)

            # Count active incoming channels for this module
            active_incoming = [idx for idx in incoming_indices if gate_values[idx] > self.threshold]

            if len(active_incoming) < self.min_channels_per_module:
                # Need to boost some channels
                deficit = self.min_channels_per_module - len(active_incoming)
                # Sort inactive incoming by gate value (boost the strongest inactive ones)
                inactive = [idx for idx in incoming_indices if gate_values[idx] <= self.threshold]
                inactive.sort(key=lambda i: gate_values[i], reverse=True)
                for idx in inactive[:deficit]:
                    # Set logit so that sigmoid(logit) = threshold + 0.1
                    target_gate = self.threshold + 0.1
                    # logit = log(p / (1-p))
                    target_gate = max(0.01, min(0.99, target_gate))
                    self._logits[idx] = math.log(target_gate / (1.0 - target_gate))

    def _homeostatic_normalization(self) -> None:
        """Asymmetric homeostatic plasticity for the topology gate.

        Prevents runaway reinforcement (gates saturating at 1.0) while still
        allowing selective pruning. Only applies upward correction when total
        mass drops below the minimum connectivity floor (catastrophic collapse
        prevention). Applies downward correction when mass exceeds the upper
        bound (prevents all gates from saturating).

        This asymmetry is key: the system can prune channels freely as long as
        minimum connectivity is maintained, but cannot reinforce all channels
        to saturation.
        """
        gate_values = self.gates
        total_mass = sum(gate_values)

        if total_mass < 1e-8:
            return

        # Floor: minimum connectivity requires min_channels_per_module * n_modules
        # active channels, each with gate > threshold. Use a soft floor above this.
        min_mass = self.min_channels_per_module * self.n_modules * 0.3
        # Ceiling: prevent saturation — cap at 70% of theoretical max
        max_mass = self.n_channels * 0.7

        if total_mass > max_mass:
            # Too much reinforcement — gently push down
            ratio = max_mass / total_mass
            correction = math.log(ratio) * 0.1  # Damped downward
            if _HAS_NUMPY:
                arr = np.array(self._logits, dtype=np.float64)
                arr += correction
                self._logits = arr.tolist()
            else:
                for i in range(self.n_channels):
                    self._logits[i] += correction
        elif total_mass < min_mass:
            # Catastrophic collapse — push back up
            ratio = min_mass / total_mass
            correction = math.log(ratio) * 0.2  # Stronger upward correction
            if _HAS_NUMPY:
                arr = np.array(self._logits, dtype=np.float64)
                arr += correction
                self._logits = arr.tolist()
            else:
                for i in range(self.n_channels):
                    self._logits[i] += correction

    # ------------------------------------------------------------------
    # Topology export and summary
    # ------------------------------------------------------------------

    def get_topology_summary(self) -> dict[str, Any]:
        """Statistics about the current learned topology.

        Returns:
            Dict with keys: n_active, n_total, sparsity, per_order_active,
            per_module_incoming, feedback_counts, total_updates.
        """
        gate_values = self.gates
        mask = [g > self.threshold for g in gate_values]

        # Per-order breakdown
        per_order: dict[int, dict[str, int]] = {}
        for i in range(self.n_channels):
            order = _channel_order(i, self.n_modules)
            if order not in per_order:
                per_order[order] = {"total": 0, "active": 0}
            per_order[order]["total"] += 1
            if mask[i]:
                per_order[order]["active"] += 1

        # Per-module incoming count
        per_module_incoming: dict[int, int] = {m: 0 for m in range(self.n_modules)}
        for i in range(self.n_channels):
            if mask[i]:
                target = _channel_target_module(i, self.n_modules)
                per_module_incoming[target] += 1

        return {
            "n_active": sum(mask),
            "n_total": self.n_channels,
            "sparsity": 1.0 - sum(mask) / max(1, self.n_channels),
            "per_order_active": per_order,
            "per_module_incoming": per_module_incoming,
            "feedback_counts": dict(self._feedback_counts),
            "total_updates": self._total_updates,
        }

    def export_sparse_config(self) -> dict[str, Any]:
        """Export learned topology as a sparse configuration.

        Suitable for deploying on lite hardware where only active channels
        are instantiated (no need to store/compute inactive ones).

        Returns:
            Dict with active_indices, gate_values (only active), and metadata.
        """
        gate_values = self.gates
        active_indices = [i for i, g in enumerate(gate_values) if g > self.threshold]
        active_gates = [gate_values[i] for i in active_indices]

        # Group by order for structured deployment
        by_order: dict[int, list[dict[str, Any]]] = {}
        for idx, gate in zip(active_indices, active_gates):
            order = _channel_order(idx, self.n_modules)
            if order not in by_order:
                by_order[order] = []
            by_order[order].append({"channel_idx": idx, "gate": gate})

        return {
            "n_active": len(active_indices),
            "n_total": self.n_channels,
            "sparsity": 1.0 - len(active_indices) / max(1, self.n_channels),
            "active_indices": active_indices,
            "active_gates": active_gates,
            "by_order": by_order,
            "threshold": self.threshold,
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize gate state for persistence.

        Returns:
            Dict containing all state needed to reconstruct the gate.
        """
        return {
            "n_channels": self.n_channels,
            "n_modules": self.n_modules,
            "threshold": self.threshold,
            "min_channels_per_module": self.min_channels_per_module,
            "max_total_active": self.max_total_active,
            "logits": list(self._logits),
            "learning_rate": self._learning_rate,
            "decay_rate": self._decay_rate,
            "openness_lr_mod": self._openness_lr_mod,
            "conscientiousness_decay_mod": self._conscientiousness_decay_mod,
            "total_updates": self._total_updates,
            "feedback_counts": dict(self._feedback_counts),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TopologyGate:
        """Reconstruct a TopologyGate from serialized state.

        Args:
            data: Dict as produced by to_dict().

        Returns:
            Reconstructed TopologyGate instance.
        """
        gate = cls(
            n_channels=data.get("n_channels", 441),
            n_modules=data.get("n_modules", 7),
            threshold=data.get("threshold", 0.1),
            min_channels_per_module=data.get("min_channels_per_module", 3),
            max_total_active=data.get("max_total_active"),
            learning_rate=data.get("learning_rate", 0.1),
            decay_rate=data.get("decay_rate", 0.01),
        )
        if "logits" in data:
            gate._logits = list(data["logits"])
        gate._openness_lr_mod = data.get("openness_lr_mod", 1.0)
        gate._conscientiousness_decay_mod = data.get("conscientiousness_decay_mod", 1.0)
        gate._total_updates = data.get("total_updates", 0)
        gate._feedback_counts = data.get(
            "feedback_counts",
            {
                "accepted": 0,
                "rejected": 0,
                "ignored": 0,
            },
        )
        return gate

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"TopologyGate(n_channels={self.n_channels}, "
            f"active={self.n_active}/{self.n_channels}, "
            f"sparsity={self.sparsity:.2%})"
        )
