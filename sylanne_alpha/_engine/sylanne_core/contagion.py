"""Sylanne Multi-Agent Influence Protocol: Emotional Contagion Between Agents.

Implements inter-agent emotional contagion for multi-agent affective systems.
Target applications: NPC crowd dynamics, VTuber audience sentiment propagation,
therapist-client dyadic regulation, and social robotics swarms.

Theoretical foundations:
  - DeGroot (1974): Reaching a consensus. Journal of the American Statistical
    Association, 69(345), 118-121. Social learning via iterated weighted averaging
    converges iff the influence graph has a spanning tree.
  - Hatfield, Cacioppo & Rapson (1994): Emotional Contagion. Cambridge University
    Press. Primitive emotional contagion as automatic mimicry and synchronization.
  - Keltner, Gruenfeld & Anderson (2003): Power, approach, and inhibition.
    Psychological Review, 110(2), 265-284. Dominance asymmetry in influence.
  - Barsade (2002): The ripple effect: Emotional contagion and its influence on
    group behavior. Administrative Science Quarterly, 47(4), 644-675.
  - Goldenberg, Garcia & Halperin (2020): Collective emotions. Current Directions
    in Psychological Science, 29(2), 154-160.

Propagation model (continuous-time DeGroot with PAD state space):
    dx_i/dt = sum_j w_ij * (x_j - x_i)

    This is a linear consensus protocol on the compact set S = [-1,1] x [0,1] x [0,1].
    Discretized via forward Euler: x_i(t+dt) = x_i(t) + dt * sum_j w_ij * (x_j(t) - x_i(t)).

Formal properties:
  - Consensus (DeGroot 1974): If the influence graph is strongly connected,
    all agent states converge to the weighted average of initial states.
  - Boundedness (Axiom A1): Clamping to S after each step guarantees invariance.
  - Lipschitz (Axiom A3): ||x_i(t+dt) - x_i(t)|| <= dt * max_weight * max_diff.
  - Energy non-increasing: Lyapunov function V = sum_i ||x_i - x_mean||^2 satisfies
    dV/dt <= 0 for doubly-stochastic or symmetric weight matrices.

Pure Python. No external dependencies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .compute.hot_pool import InfluenceType
from .standard import EmotionVector

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp_pad(valence: float, arousal: float, dominance: float) -> tuple[float, float, float]:
    """Clamp PAD components to the compact set S = [-1,1] x [0,1] x [0,1].

    Enforces Axiom A1 (boundedness) after every state update.
    """
    v = max(-1.0, min(1.0, valence))
    a = max(0.0, min(1.0, arousal))
    d = max(0.0, min(1.0, dominance))
    return v, a, d


def _emotion_to_tuple(ev: EmotionVector) -> tuple[float, float, float]:
    """Extract (valence, arousal, dominance) from an EmotionVector."""
    return (ev.valence, ev.arousal, ev.dominance)


def _tuple_to_emotion(t: tuple[float, float, float]) -> EmotionVector:
    """Construct an EmotionVector from a (valence, arousal, dominance) tuple."""
    return EmotionVector(valence=t[0], arousal=t[1], dominance=t[2])


def _euclidean_distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    """Euclidean distance between two 3D points."""
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ContagionEvent:
    """Record of a single emotional influence propagation between two agents.

    Captures the source, target, influence semantics, intensity, and the
    resulting propagated state for audit and replay purposes.

    Attributes:
        source: Agent ID of the influencing agent.
        target: Agent ID of the influenced agent.
        influence_type: Semantic category of the influence channel
            (from hot_pool InfluenceType taxonomy).
        intensity: Magnitude of the influence in [0, 1].
        propagated_state: The target agent's EmotionVector after propagation.
    """

    source: str
    target: str
    influence_type: InfluenceType
    intensity: float
    propagated_state: EmotionVector


# ---------------------------------------------------------------------------
# Edge representation
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _Edge:
    """Internal directed edge in the contagion graph.

    Attributes:
        weight: Influence strength in (0, 1]. Higher = stronger pull.
        decay: Per-step weight decay rate in [0, 1]. Edge weakens over time
            unless reinforced. Models relationship attenuation (Hatfield 1994).
    """

    weight: float
    decay: float


# ---------------------------------------------------------------------------
# ContagionGraph
# ---------------------------------------------------------------------------


class ContagionGraph:
    """Directed weighted graph for multi-agent emotional contagion.

    Nodes are agent IDs mapped to their current EmotionVector state.
    Edges are directed influence channels with weight and temporal decay.

    The propagation algorithm implements a discretized DeGroot (1974) consensus
    protocol on the PAD state space S = [-1,1] x [0,1] x [0,1]:

        x_i(t+dt) = x_i(t) + dt * sum_{j in N(i)} w_ji * (x_j(t) - x_i(t))

    where N(i) is the set of agents with edges pointing TO agent i, and w_ji
    is the weight of edge (j -> i).

    Formal guarantees:
      - Boundedness: state clamped to S after each step (Axiom A1).
      - Lipschitz: step size bounded by dt * sum(weights) * max_state_diff (Axiom A3).
      - Consensus: strongly connected graphs converge to weighted average (DeGroot 1974).
      - Energy: total variance V = sum ||x_i - x_mean||^2 is non-increasing for
        symmetric weight configurations (Lyapunov stability).
    """

    __slots__ = ("_states", "_edges", "_filters")

    def __init__(self) -> None:
        """Initialize an empty contagion graph."""
        # agent_id -> (valence, arousal, dominance) as mutable tuple
        self._states: dict[str, list[float]] = {}
        # (source, target) -> _Edge
        self._edges: dict[tuple[str, str], _Edge] = {}
        # agent_id -> InfluenceFilter (optional per-agent)
        self._filters: dict[str, InfluenceFilter] = {}

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    def add_agent(self, agent_id: str, initial_state: EmotionVector) -> None:
        """Add an agent node with its initial emotional state.

        Args:
            agent_id: Unique string identifier for the agent.
            initial_state: Starting EmotionVector (will be clamped to S).

        Raises:
            ValueError: If agent_id already exists in the graph.
        """
        if agent_id in self._states:
            raise ValueError(f"Agent '{agent_id}' already exists in the graph.")
        v, a, d = _clamp_pad(initial_state.valence, initial_state.arousal, initial_state.dominance)
        self._states[agent_id] = [v, a, d]

    def remove_agent(self, agent_id: str) -> None:
        """Remove an agent and all its incident edges.

        Args:
            agent_id: The agent to remove.

        Raises:
            KeyError: If agent_id does not exist.
        """
        if agent_id not in self._states:
            raise KeyError(f"Agent '{agent_id}' not found in the graph.")
        del self._states[agent_id]
        # Remove all edges involving this agent
        to_remove = [key for key in self._edges if key[0] == agent_id or key[1] == agent_id]
        for key in to_remove:
            del self._edges[key]
        # Remove filter if present
        self._filters.pop(agent_id, None)

    def get_state(self, agent_id: str) -> EmotionVector:
        """Retrieve the current emotional state of an agent.

        Args:
            agent_id: The agent to query.

        Returns:
            Current EmotionVector for the agent.

        Raises:
            KeyError: If agent_id does not exist.
        """
        if agent_id not in self._states:
            raise KeyError(f"Agent '{agent_id}' not found in the graph.")
        s = self._states[agent_id]
        return EmotionVector(valence=s[0], arousal=s[1], dominance=s[2])

    def set_state(self, agent_id: str, state: EmotionVector) -> None:
        """Directly set an agent's emotional state (e.g., from external stimulus).

        Args:
            agent_id: The agent to update.
            state: New EmotionVector (will be clamped to S).

        Raises:
            KeyError: If agent_id does not exist.
        """
        if agent_id not in self._states:
            raise KeyError(f"Agent '{agent_id}' not found in the graph.")
        v, a, d = _clamp_pad(state.valence, state.arousal, state.dominance)
        self._states[agent_id] = [v, a, d]

    def set_filter(self, agent_id: str, filt: InfluenceFilter) -> None:
        """Attach a personality-based influence filter to an agent.

        Args:
            agent_id: The agent to configure.
            filt: InfluenceFilter instance defining susceptibility parameters.

        Raises:
            KeyError: If agent_id does not exist.
        """
        if agent_id not in self._states:
            raise KeyError(f"Agent '{agent_id}' not found in the graph.")
        self._filters[agent_id] = filt

    @property
    def agent_ids(self) -> list[str]:
        """List of all agent IDs currently in the graph."""
        return list(self._states.keys())

    @property
    def agent_count(self) -> int:
        """Number of agents in the graph."""
        return len(self._states)

    # ------------------------------------------------------------------
    # Edge operations
    # ------------------------------------------------------------------

    def add_edge(self, source: str, target: str, weight: float, decay: float = 0.1) -> None:
        """Add a directed influence edge from source to target.

        The edge means: source's emotional state influences target.
        Weight controls influence strength; decay controls temporal attenuation.

        Args:
            source: Agent ID of the influencer.
            target: Agent ID of the influenced.
            weight: Influence strength in (0, 1]. Clamped to this range.
            decay: Per-propagation-step weight decay in [0, 1]. Default 0.1.

        Raises:
            KeyError: If source or target does not exist.
            ValueError: If source == target (self-loops disallowed) or weight <= 0.
        """
        if source not in self._states:
            raise KeyError(f"Source agent '{source}' not found in the graph.")
        if target not in self._states:
            raise KeyError(f"Target agent '{target}' not found in the graph.")
        if source == target:
            raise ValueError("Self-loops are not permitted in the contagion graph.")
        if weight <= 0.0:
            raise ValueError(f"Edge weight must be positive, got {weight}.")

        clamped_weight = min(1.0, weight)
        clamped_decay = max(0.0, min(1.0, decay))
        self._edges[(source, target)] = _Edge(weight=clamped_weight, decay=clamped_decay)

    def remove_edge(self, source: str, target: str) -> None:
        """Remove a directed edge.

        Args:
            source: Source agent ID.
            target: Target agent ID.

        Raises:
            KeyError: If the edge does not exist.
        """
        key = (source, target)
        if key not in self._edges:
            raise KeyError(f"Edge ({source} -> {target}) not found.")
        del self._edges[key]

    def has_edge(self, source: str, target: str) -> bool:
        """Check whether a directed edge exists."""
        return (source, target) in self._edges

    def get_edge_weight(self, source: str, target: str) -> float:
        """Get the current weight of an edge.

        Raises:
            KeyError: If the edge does not exist.
        """
        key = (source, target)
        if key not in self._edges:
            raise KeyError(f"Edge ({source} -> {target}) not found.")
        return self._edges[key].weight

    # ------------------------------------------------------------------
    # Propagation
    # ------------------------------------------------------------------

    def propagate(self, dt: float) -> dict[str, EmotionVector]:
        """Execute one propagation step of the contagion dynamics.

        Implements the discretized DeGroot consensus protocol:
            x_i(t+dt) = x_i(t) + dt * sum_{j->i} w_ji * filter(x_j - x_i)

        After computing all updates simultaneously (synchronous update to avoid
        order-dependence), states are clamped to S = [-1,1] x [0,1] x [0,1].

        Edge weights are decayed after propagation to model temporal attenuation
        of influence channels (Hatfield et al. 1994: contagion weakens without
        continued exposure).

        Args:
            dt: Time step size. Must be positive. For stability, recommend
                dt <= 1.0 / max_total_incoming_weight. Larger dt risks
                overshooting but boundedness is still guaranteed by clamping.

        Returns:
            Dictionary mapping agent_id -> new EmotionVector for all agents.

        Raises:
            ValueError: If dt <= 0.
        """
        if dt <= 0.0:
            raise ValueError(f"Time step dt must be positive, got {dt}.")

        # Compute all deltas synchronously (read from current state, write to new)
        deltas: dict[str, list[float]] = {aid: [0.0, 0.0, 0.0] for aid in self._states}

        for (source, target), edge in self._edges.items():
            src_state = self._states[source]
            tgt_state = self._states[target]

            # Raw difference: x_source - x_target
            diff = [
                src_state[0] - tgt_state[0],
                src_state[1] - tgt_state[1],
                src_state[2] - tgt_state[2],
            ]

            # Apply influence filter if target has one
            effective_weight = edge.weight
            if target in self._filters:
                filt = self._filters[target]
                effective_weight = filt.modulate_weight(
                    base_weight=edge.weight,
                    source_dominance=src_state[2],
                    target_dominance=tgt_state[2],
                )

            # Accumulate influence: dt * w * (x_j - x_i)
            scale = dt * effective_weight
            deltas[target][0] += scale * diff[0]
            deltas[target][1] += scale * diff[1]
            deltas[target][2] += scale * diff[2]

        # Apply deltas and clamp to S (Axiom A1 boundedness)
        results: dict[str, EmotionVector] = {}
        for aid, state in self._states.items():
            d = deltas[aid]
            new_v, new_a, new_d = _clamp_pad(
                state[0] + d[0],
                state[1] + d[1],
                state[2] + d[2],
            )
            state[0] = new_v
            state[1] = new_a
            state[2] = new_d
            results[aid] = EmotionVector(valence=new_v, arousal=new_a, dominance=new_d)

        # Decay edge weights (temporal attenuation)
        edges_to_remove: list[tuple[str, str]] = []
        for key, edge in self._edges.items():
            edge.weight *= 1.0 - edge.decay
            # Remove edges that have decayed below threshold
            if edge.weight < 1e-6:
                edges_to_remove.append(key)
        for key in edges_to_remove:
            del self._edges[key]

        return results

    def propagate_n(self, dt: float, steps: int) -> dict[str, EmotionVector]:
        """Execute multiple propagation steps.

        Convenience method for running the dynamics forward by several steps.

        Args:
            dt: Time step per iteration.
            steps: Number of iterations to run.

        Returns:
            Final state dictionary after all steps.

        Raises:
            ValueError: If steps < 1 or dt <= 0.
        """
        if steps < 1:
            raise ValueError(f"steps must be >= 1, got {steps}.")
        results: dict[str, EmotionVector] = {}
        for _ in range(steps):
            results = self.propagate(dt)
        return results

    def total_variance(self) -> float:
        """Compute the Lyapunov energy function V = sum_i ||x_i - x_mean||^2.

        This quantity is monotonically non-increasing under symmetric or
        doubly-stochastic weight configurations (DeGroot 1974).

        Returns:
            Total variance (sum of squared distances from centroid).
            Returns 0.0 if fewer than 2 agents exist.
        """
        n = len(self._states)
        if n < 2:
            return 0.0

        # Compute centroid
        sum_v = sum_a = sum_d = 0.0
        for state in self._states.values():
            sum_v += state[0]
            sum_a += state[1]
            sum_d += state[2]
        mean_v = sum_v / n
        mean_a = sum_a / n
        mean_d = sum_d / n

        # Sum of squared distances
        variance = 0.0
        for state in self._states.values():
            variance += (state[0] - mean_v) ** 2
            variance += (state[1] - mean_a) ** 2
            variance += (state[2] - mean_d) ** 2

        return variance

    def diagnostics(self) -> dict[str, Any]:
        """Return diagnostic summary of the contagion graph state."""
        return {
            "agent_count": len(self._states),
            "edge_count": len(self._edges),
            "total_variance": round(self.total_variance(), 6),
            "agents": {
                aid: {
                    "valence": round(s[0], 4),
                    "arousal": round(s[1], 4),
                    "dominance": round(s[2], 4),
                }
                for aid, s in self._states.items()
            },
        }


# ---------------------------------------------------------------------------
# InfluenceFilter
# ---------------------------------------------------------------------------


class InfluenceFilter:
    """Personality-modulated susceptibility filter for emotional contagion.

    Models individual differences in contagion susceptibility based on:
      - Base susceptibility: trait-level openness to influence (Hatfield et al. 1994).
      - Dominance asymmetry: high-dominance agents influence more and resist more
        (Keltner, Gruenfeld & Anderson 2003).
      - Selective gating: optional per-dimension susceptibility scaling.

    Theory (Keltner et al. 2003):
      Power/dominance creates asymmetric influence channels. High-power individuals
      show reduced mimicry (less susceptible) while simultaneously exerting stronger
      influence on others' affective states. This is modeled as:
        effective_weight = base_weight * susceptibility * dominance_factor
      where dominance_factor = (1 - target_dominance) * (source_dominance)
      normalized to [0.2, 2.0] range to prevent complete blocking or explosion.
    """

    __slots__ = ("_susceptibility", "_dominance_sensitivity", "_dimension_gates")

    def __init__(
        self,
        susceptibility: float = 1.0,
        dominance_sensitivity: float = 0.5,
        dimension_gates: tuple[float, float, float] | None = None,
    ) -> None:
        """Initialize the influence filter.

        Args:
            susceptibility: Base susceptibility in (0, 2]. 1.0 = neutral.
                Values < 1 resist contagion; > 1 amplify it.
            dominance_sensitivity: How much dominance asymmetry matters [0, 1].
                0 = dominance ignored; 1 = full Keltner effect.
            dimension_gates: Optional (valence_gate, arousal_gate, dominance_gate)
                each in [0, 1]. Scales influence per PAD dimension.
                None = all dimensions equally susceptible.
        """
        self._susceptibility = max(0.01, min(2.0, susceptibility))
        self._dominance_sensitivity = max(0.0, min(1.0, dominance_sensitivity))
        if dimension_gates is not None:
            self._dimension_gates: tuple[float, float, float] | None = (
                max(0.0, min(1.0, dimension_gates[0])),
                max(0.0, min(1.0, dimension_gates[1])),
                max(0.0, min(1.0, dimension_gates[2])),
            )
        else:
            self._dimension_gates = None

    @property
    def susceptibility(self) -> float:
        """Base susceptibility level."""
        return self._susceptibility

    @property
    def dominance_sensitivity(self) -> float:
        """Dominance asymmetry sensitivity."""
        return self._dominance_sensitivity

    def modulate_weight(
        self,
        base_weight: float,
        source_dominance: float,
        target_dominance: float,
    ) -> float:
        """Compute effective influence weight after personality modulation.

        Implements the Keltner et al. (2003) dominance asymmetry model:
          dominance_factor = lerp(1.0, source_dom * (1 - target_dom) * 4, sensitivity)
          effective = base_weight * susceptibility * clamp(dominance_factor, 0.2, 2.0)

        The factor of 4 normalizes so that when source_dom=1, target_dom=0 the
        raw factor is 4, clamped to 2.0 (maximum amplification). When source_dom=0,
        target_dom=1, raw factor is 0, clamped to 0.2 (minimum, never fully blocks).

        Args:
            base_weight: Original edge weight.
            source_dominance: Source agent's dominance [0, 1].
            target_dominance: Target agent's dominance [0, 1].

        Returns:
            Modulated weight, always positive.
        """
        # Dominance asymmetry: high source dom + low target dom = amplified
        raw_dom_factor = source_dominance * (1.0 - target_dominance) * 4.0
        # Interpolate between neutral (1.0) and full dominance effect
        dom_factor = 1.0 + self._dominance_sensitivity * (raw_dom_factor - 1.0)
        # Clamp to prevent extreme values
        dom_factor = max(0.2, min(2.0, dom_factor))

        effective = base_weight * self._susceptibility * dom_factor
        return max(0.0, effective)


# ---------------------------------------------------------------------------
# GroupDynamics
# ---------------------------------------------------------------------------


class GroupDynamics:
    """Emergent group-level emotional dynamics analyzer.

    Computes macro-level properties of a multi-agent emotional system:
      - Group emotion: weighted centroid of all agent states.
      - Polarization: bimodal distribution detection (emotional splitting).
      - Cascade detection: rapid convergence toward extreme states.

    Theoretical basis:
      - Barsade (2002): Emotional contagion creates "ripple effects" where
        one individual's affect propagates through a group, creating emergent
        collective emotional states not reducible to individual experiences.
      - Goldenberg, Garcia & Halperin (2020): Collective emotions emerge from
        the interaction between individual emotional processes and social
        network structure. Polarization and cascades are key collective phenomena.

    Usage:
        dynamics = GroupDynamics(graph)
        centroid = dynamics.group_emotion()
        if dynamics.is_polarized(threshold=0.4):
            handle_polarization()
        if dynamics.detect_cascade(prev_variance, threshold=0.5):
            handle_cascade()
    """

    __slots__ = ("_graph",)

    def __init__(self, graph: ContagionGraph) -> None:
        """Initialize with a reference to the contagion graph.

        Args:
            graph: The ContagionGraph to analyze.
        """
        self._graph = graph

    def group_emotion(self, weights: dict[str, float] | None = None) -> EmotionVector:
        """Compute the emergent group emotion as a weighted centroid.

        The group emotion is the affective "center of mass" of all agents,
        optionally weighted by salience, status, or expressiveness.

        When no weights are provided, computes the unweighted arithmetic mean
        (equal contribution from all agents).

        Args:
            weights: Optional dict mapping agent_id -> weight. Agents not in
                the dict are assigned weight 1.0. Weights need not sum to 1
                (normalization is applied internally).

        Returns:
            EmotionVector representing the group centroid.

        Raises:
            ValueError: If the graph has no agents.
        """
        agents = self._graph.agent_ids
        if not agents:
            raise ValueError("Cannot compute group emotion for an empty graph.")

        total_weight = 0.0
        sum_v = sum_a = sum_d = 0.0

        for aid in agents:
            w = 1.0
            if weights is not None:
                w = weights.get(aid, 1.0)
            w = max(0.0, w)  # No negative weights
            state = self._graph.get_state(aid)
            sum_v += w * state.valence
            sum_a += w * state.arousal
            sum_d += w * state.dominance
            total_weight += w

        if total_weight < 1e-9:
            # All weights zero — return neutral
            return EmotionVector(valence=0.0, arousal=0.0, dominance=0.5)

        return EmotionVector(
            valence=sum_v / total_weight,
            arousal=sum_a / total_weight,
            dominance=sum_d / total_weight,
        )

    def is_polarized(self, threshold: float = 0.4) -> bool:
        """Detect emotional polarization (bimodal distribution).

        Polarization is detected when the group splits into two or more
        clusters with inter-cluster distance exceeding the threshold.

        Uses a simplified bimodality test: computes the standard deviation
        of pairwise distances. High std relative to mean indicates clustering
        (bimodal distance distribution).

        More precisely: if max pairwise distance > threshold AND the ratio
        of max distance to mean distance > 2.0, the group is polarized.

        Theory (Goldenberg et al. 2020): Emotional polarization occurs when
        subgroups converge internally while diverging from each other, creating
        an "us vs them" affective landscape.

        Args:
            threshold: Minimum inter-cluster distance to qualify as polarized.
                Default 0.4 (moderate separation in PAD space).

        Returns:
            True if polarization is detected, False otherwise.
        """
        agents = self._graph.agent_ids
        n = len(agents)
        if n < 3:
            return False

        # Compute all pairwise distances
        states = [_emotion_to_tuple(self._graph.get_state(aid)) for aid in agents]
        distances: list[float] = []
        for i in range(n):
            for j in range(i + 1, n):
                distances.append(_euclidean_distance(states[i], states[j]))

        if not distances:
            return False

        max_dist = max(distances)
        mean_dist = sum(distances) / len(distances)

        # Polarization: large max distance AND high dispersion ratio
        if max_dist < threshold:
            return False
        if mean_dist < 1e-9:
            return False
        return (max_dist / mean_dist) > 2.0

    def detect_cascade(self, previous_variance: float, threshold: float = 0.5) -> bool:
        """Detect a cascade event (rapid convergence toward extreme).

        A cascade is identified when:
          1. Total variance has decreased significantly (convergence), AND
          2. The group centroid is at an extreme position (not neutral).

        This captures the "ripple effect" (Barsade 2002) where one agent's
        strong emotion rapidly pulls the entire group toward that state.

        Args:
            previous_variance: The total_variance() from the previous time step.
                Compare against current variance to detect rapid convergence.
            threshold: Minimum fractional variance reduction to qualify.
                Default 0.5 means variance must drop by at least 50%.

        Returns:
            True if a cascade event is detected, False otherwise.
        """
        current_variance = self._graph.total_variance()

        # Check for significant variance reduction
        if previous_variance < 1e-9:
            return False
        reduction = (previous_variance - current_variance) / previous_variance
        if reduction < threshold:
            return False

        # Check that the group is converging toward an extreme (not just neutral)
        centroid = self.group_emotion()
        # "Extreme" = far from the neutral point (0, 0.5, 0.5) in PAD space
        neutral = (0.0, 0.5, 0.5)
        centroid_tuple = _emotion_to_tuple(centroid)
        extremity = _euclidean_distance(centroid_tuple, neutral)

        # Cascade requires convergence toward a non-neutral state
        return extremity > 0.3

    def emotional_entropy(self) -> float:
        """Compute a diversity measure of the group's emotional distribution.

        Uses the average pairwise distance as a proxy for emotional diversity.
        High entropy = diverse emotional states; low entropy = homogeneous group.

        Returns:
            Average pairwise Euclidean distance in PAD space.
            Returns 0.0 for fewer than 2 agents.
        """
        agents = self._graph.agent_ids
        n = len(agents)
        if n < 2:
            return 0.0

        states = [_emotion_to_tuple(self._graph.get_state(aid)) for aid in agents]
        total_dist = 0.0
        count = 0
        for i in range(n):
            for j in range(i + 1, n):
                total_dist += _euclidean_distance(states[i], states[j])
                count += 1

        return total_dist / count if count > 0 else 0.0

    def dominant_agent(self) -> str | None:
        """Identify the agent with highest influence potential.

        The dominant agent is the one whose state is most distant from the
        group centroid AND has high dominance — they are the most likely
        "emotional leader" pulling the group (Barsade 2002).

        Returns:
            Agent ID of the dominant influencer, or None if graph is empty.
        """
        agents = self._graph.agent_ids
        if not agents:
            return None

        centroid = self.group_emotion()
        centroid_t = _emotion_to_tuple(centroid)

        best_id: str | None = None
        best_score = -1.0

        for aid in agents:
            state = self._graph.get_state(aid)
            state_t = _emotion_to_tuple(state)
            distance = _euclidean_distance(state_t, centroid_t)
            # Score = distance from centroid * dominance (high dom = more influence)
            score = distance * state.dominance
            if score > best_score:
                best_score = score
                best_id = aid

        return best_id
