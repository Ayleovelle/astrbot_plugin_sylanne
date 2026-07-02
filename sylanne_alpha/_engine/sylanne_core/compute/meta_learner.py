"""Online meta-learning of resonance field hyperparameters.

Replaces the static personality-to-hyperparameter mapping with an adaptive
system that uses personality as initialization (seed) and learns optimal
values from interaction feedback via exponential moving average updates.

Theoretical grounding:
- Finn et al. (2017): MAML — personality as meta-learned initialization
- Xu et al. (2018): Meta-gradient RL — online hyperparameter adaptation
- Sutton (1992): Adapting bias by gradient descent — incremental meta-learning
- Friston (2010): Free energy principle — regularization toward prior (personality)

Design principles:
- Personality provides the SEED (initialization), not the final value
- Feedback drives slow EMA adaptation toward empirically good settings
- Elastic regularization prevents drift beyond 30% of seed value
- Context-dependent: tracks param-reward correlations for directed updates
- Minimal state: 7 params x (seed + current + correlation) + metadata
"""

from __future__ import annotations

import random
from collections import deque
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Managed hyperparameter names
PARAM_NAMES: list[str] = [
    "expression_threshold",
    "dissipation",
    "residual_decay",
    "hopfield_strength",
    "identity_inertia",
    "kuramoto_k1",
    "broadcast_threshold",
]

N_PARAMS: int = len(PARAM_NAMES)

# Parameter bounds: (min, max) for each managed hyperparameter
PARAM_BOUNDS: dict[str, tuple[float, float]] = {
    "expression_threshold": (0.15, 0.95),
    "dissipation": (0.005, 0.05),
    "residual_decay": (0.4, 0.95),
    "hopfield_strength": (0.01, 0.12),
    "identity_inertia": (0.85, 1.0),
    "kuramoto_k1": (0.3, 2.0),
    "broadcast_threshold": (0.4, 0.85),
}

# Maximum drift from seed (fraction of seed value)
_MAX_DRIFT_FRACTION: float = 0.3

# Adaptation rates
_BASE_ADAPTATION_RATE: float = 0.03
_MIN_ADAPTATION_RATE: float = 0.01
_MAX_ADAPTATION_RATE: float = 0.05

# Feedback reward mapping
_REWARD_ACCEPTED: float = 1.0
_REWARD_REJECTED: float = -1.0
_REWARD_IGNORED: float = -0.2

# Correlation tracking window
_CORRELATION_WINDOW: int = 50

# Noise scale for exploration after rejection
_REJECTION_NOISE_SCALE: float = 0.02


# ---------------------------------------------------------------------------
# MetaLearner class
# ---------------------------------------------------------------------------


class MetaLearner:
    """Online adaptation of resonance field hyperparameters from feedback.

    Personality provides the seed (initialization) for 7 key hyperparameters.
    Interaction feedback drives slow EMA adaptation toward empirically optimal
    values, with elastic regularization preventing excessive drift from the
    personality-derived seed.

    Managed parameters:
      - expression_threshold: when to speak (lower = more expressive)
      - dissipation: how fast emotions fade (lower = longer emotional memory)
      - residual_decay: memory persistence (higher = more persistent)
      - hopfield_strength: attractor pull (higher = more habitual patterns)
      - identity_inertia: personality stability (higher = more consistent)
      - kuramoto_k1: coupling strength (higher = more inter-module influence)
      - broadcast_threshold: global ignition threshold (lower = easier ignition)

    Attributes:
        seed_values: Personality-derived initial values (immutable after init).
        current_values: Adapted values (updated by feedback).
        adaptation_count: Total number of feedback updates applied.
    """

    __slots__ = (
        "seed_values",
        "current_values",
        "adaptation_count",
        "_adaptation_rate",
        "_base_adaptation_rate",
        "_openness_mod",
        "_correlations",
        "_reward_history",
        "_param_history",
        "_feedback_counts",
    )

    def __init__(
        self,
        adaptation_rate: float = _BASE_ADAPTATION_RATE,
    ):
        """Initialize the meta-learner with default (neutral) seed values.

        Args:
            adaptation_rate: Base rate for EMA updates. Modulated by openness.
        """
        self.seed_values: dict[str, float] = {}
        self.current_values: dict[str, float] = {}
        self.adaptation_count: int = 0
        self._base_adaptation_rate = adaptation_rate
        self._adaptation_rate = adaptation_rate
        self._openness_mod: float = 1.0

        # Running correlation: param_value * reward (per param)
        self._correlations: dict[str, deque[float]] = {
            name: deque(maxlen=_CORRELATION_WINDOW) for name in PARAM_NAMES
        }
        # Reward history for baseline subtraction
        self._reward_history: deque[float] = deque(maxlen=_CORRELATION_WINDOW)
        # Param snapshot at each feedback (for correlation tracking)
        self._param_history: deque[dict[str, float]] = deque(maxlen=_CORRELATION_WINDOW)
        # Feedback counts
        self._feedback_counts: dict[str, int] = {
            "accepted": 0,
            "rejected": 0,
            "ignored": 0,
        }

    # ------------------------------------------------------------------
    # Initialization from personality
    # ------------------------------------------------------------------

    def init_from_personality(self, personality: dict[str, float]) -> None:
        """Compute seed values from personality using the canonical formulas.

        These are the SAME formulas used in ResonanceSpine.apply_personality(),
        but stored as mutable starting points rather than fixed values.

        Args:
            personality: Dict with Big Five traits (values in [0, 1]).
                Keys: extraversion, openness, neuroticism, conscientiousness,
                      agreeableness.
        """
        extraversion = float(personality.get("extraversion", 0.5))
        openness = float(personality.get("openness", 0.5))
        neuroticism = float(personality.get("neuroticism", 0.5))
        conscientiousness = float(personality.get("conscientiousness", 0.5))
        agreeableness = float(personality.get("agreeableness", 0.5))

        # Canonical formulas (from resonance_integration.apply_personality)
        seeds = {
            "expression_threshold": 0.9 - extraversion * 0.6,
            "dissipation": 0.03 - neuroticism * 0.02,
            "residual_decay": 0.6 + (1.0 - openness) * 0.2,
            "hopfield_strength": 0.03 + extraversion * 0.04,
            "identity_inertia": 0.9 + conscientiousness * 0.08,
            "kuramoto_k1": 0.5 + openness * 1.0,
            "broadcast_threshold": 0.8 - agreeableness * 0.3,
        }

        # Clamp seeds to valid bounds
        for name in PARAM_NAMES:
            lo, hi = PARAM_BOUNDS[name]
            seeds[name] = max(lo, min(hi, seeds[name]))

        self.seed_values = dict(seeds)
        self.current_values = dict(seeds)

        # Openness modulates adaptation rate (more open = faster learning)
        self._openness_mod = 0.5 + openness  # Range: [0.5, 1.5]
        self._adaptation_rate = max(
            _MIN_ADAPTATION_RATE,
            min(_MAX_ADAPTATION_RATE, self._base_adaptation_rate * self._openness_mod),
        )

    # ------------------------------------------------------------------
    # Feedback-driven adaptation
    # ------------------------------------------------------------------

    def update(self, outcome: str) -> None:
        """Update hyperparameters based on interaction feedback.

        Adaptation mechanism:
          - "accepted": current params worked well, reinforce (EMA toward current)
          - "rejected": current params led to bad outcome, perturb toward seed + noise
          - "ignored": slight regression toward seed (conservative pull)

        Args:
            outcome: One of "accepted", "rejected", "ignored".
        """
        if outcome not in ("accepted", "rejected", "ignored"):
            return

        self._feedback_counts[outcome] = self._feedback_counts.get(outcome, 0) + 1
        self.adaptation_count += 1

        # Determine reward signal
        if outcome == "accepted":
            reward = _REWARD_ACCEPTED
        elif outcome == "rejected":
            reward = _REWARD_REJECTED
        else:
            reward = _REWARD_IGNORED

        # Store for correlation tracking
        self._reward_history.append(reward)
        self._param_history.append(dict(self.current_values))

        # Update correlations
        for name in PARAM_NAMES:
            if name in self.current_values:
                self._correlations[name].append(self.current_values[name] * reward)

        # Apply adaptation per parameter
        alpha = self._adaptation_rate

        for name in PARAM_NAMES:
            seed = self.seed_values.get(name, 0.5)
            current = self.current_values.get(name, seed)
            lo, hi = PARAM_BOUNDS[name]

            if outcome == "accepted":
                # Reinforce: slight consolidation (stay near current)
                # Also incorporate correlation signal
                corr_signal = self._correlation_signal(name)
                # Move slightly in the direction that correlates with reward
                new_val = current + alpha * 0.5 * corr_signal
            elif outcome == "rejected":
                # Move toward seed + random perturbation
                noise = random.gauss(0.0, _REJECTION_NOISE_SCALE)
                new_val = current + alpha * 2.0 * (seed - current) + noise
            else:  # ignored
                # Gentle regression toward seed
                new_val = current + alpha * 0.5 * (seed - current)

            # Apply elastic regularization (max drift constraint)
            new_val = self._apply_elastic_bound(name, new_val)

            # Clamp to parameter bounds
            new_val = max(lo, min(hi, new_val))

            self.current_values[name] = new_val

    # ------------------------------------------------------------------
    # Context-dependent adaptation helpers
    # ------------------------------------------------------------------

    def _correlation_signal(self, name: str) -> float:
        """Compute running correlation between param value and reward.

        Returns a signal in [-1, 1] indicating whether higher values of this
        param correlate with positive or negative outcomes.

        Positive correlation -> param should increase.
        Negative correlation -> param should decrease.
        """
        corr_data = self._correlations.get(name)
        if not corr_data or len(corr_data) < 3:
            return 0.0

        # Simple: mean of (param * reward) normalized by param variance
        mean_pr = sum(corr_data) / len(corr_data)

        # Normalize by param range to get a [-1, 1] signal
        lo, hi = PARAM_BOUNDS[name]
        param_range = hi - lo
        if param_range < 1e-8:
            return 0.0

        # Scale so that the signal is meaningful relative to param range
        signal = mean_pr / (param_range * 0.5)
        return max(-1.0, min(1.0, signal))

    def _apply_elastic_bound(self, name: str, value: float) -> float:
        """Apply elastic regularization: prevent drift beyond max_drift of seed.

        The parameter cannot move more than _MAX_DRIFT_FRACTION * |seed| away
        from its seed value (with a minimum absolute drift allowance for
        near-zero seeds).

        Args:
            name: Parameter name.
            value: Proposed new value.

        Returns:
            Value clamped to the elastic bound.
        """
        seed = self.seed_values.get(name, 0.5)

        # Max drift is 30% of seed value, with a floor for near-zero seeds
        max_drift = max(0.01, abs(seed) * _MAX_DRIFT_FRACTION)

        lower = seed - max_drift
        upper = seed + max_drift

        return max(lower, min(upper, value))

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    @property
    def drift_from_seed(self) -> dict[str, float]:
        """How far each parameter has drifted from its personality seed.

        Returns:
            Dict mapping param name to absolute drift (always >= 0).
        """
        result = {}
        for name in PARAM_NAMES:
            seed = self.seed_values.get(name, 0.0)
            current = self.current_values.get(name, seed)
            result[name] = abs(current - seed)
        return result

    @property
    def relative_drift(self) -> dict[str, float]:
        """Drift as a fraction of the maximum allowed drift per parameter.

        Returns:
            Dict mapping param name to relative drift in [0, 1].
            1.0 means the param is at its elastic bound.
        """
        result = {}
        for name in PARAM_NAMES:
            seed = self.seed_values.get(name, 0.5)
            current = self.current_values.get(name, seed)
            max_drift = max(0.01, abs(seed) * _MAX_DRIFT_FRACTION)
            result[name] = min(1.0, abs(current - seed) / max_drift)
        return result

    def param_summary(self) -> list[dict[str, Any]]:
        """Summary of all managed parameters: seed, current, drift, bounds.

        Returns:
            List of dicts, one per parameter, with keys:
            name, seed, current, drift, relative_drift, bounds.
        """
        summary = []
        rel_drift = self.relative_drift
        abs_drift = self.drift_from_seed
        for name in PARAM_NAMES:
            summary.append(
                {
                    "name": name,
                    "seed": round(self.seed_values.get(name, 0.0), 6),
                    "current": round(self.current_values.get(name, 0.0), 6),
                    "drift": round(abs_drift.get(name, 0.0), 6),
                    "relative_drift": round(rel_drift.get(name, 0.0), 4),
                    "bounds": PARAM_BOUNDS[name],
                }
            )
        return summary

    def diagnostics(self) -> dict[str, Any]:
        """Full diagnostic snapshot of the meta-learner state.

        Returns:
            Dict with adaptation metadata, parameter states, and correlations.
        """
        return {
            "adaptation_count": self.adaptation_count,
            "adaptation_rate": round(self._adaptation_rate, 4),
            "openness_mod": round(self._openness_mod, 4),
            "feedback_counts": dict(self._feedback_counts),
            "params": {
                name: {
                    "seed": round(self.seed_values.get(name, 0.0), 6),
                    "current": round(self.current_values.get(name, 0.0), 6),
                    "drift": round(self.drift_from_seed.get(name, 0.0), 6),
                    "correlation": round(self._correlation_signal(name), 4),
                }
                for name in PARAM_NAMES
            },
            "total_drift": round(sum(self.drift_from_seed.values()), 6),
            "mean_relative_drift": round(sum(self.relative_drift.values()) / max(1, N_PARAMS), 4),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize meta-learner state for persistence.

        Returns:
            Dict containing all state needed to reconstruct the learner.
        """
        return {
            "seed_values": dict(self.seed_values),
            "current_values": dict(self.current_values),
            "adaptation_count": self.adaptation_count,
            "base_adaptation_rate": self._base_adaptation_rate,
            "openness_mod": self._openness_mod,
            "feedback_counts": dict(self._feedback_counts),
            "correlations": {name: list(dq) for name, dq in self._correlations.items()},
            "reward_history": list(self._reward_history),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MetaLearner:
        """Reconstruct a MetaLearner from serialized state.

        Args:
            data: Dict as produced by to_dict().

        Returns:
            Reconstructed MetaLearner instance.
        """
        learner = cls(
            adaptation_rate=data.get("base_adaptation_rate", _BASE_ADAPTATION_RATE),
        )
        learner.seed_values = dict(data.get("seed_values", {}))
        learner.current_values = dict(data.get("current_values", {}))
        learner.adaptation_count = data.get("adaptation_count", 0)
        learner._openness_mod = data.get("openness_mod", 1.0)
        learner._adaptation_rate = max(
            _MIN_ADAPTATION_RATE,
            min(
                _MAX_ADAPTATION_RATE,
                learner._base_adaptation_rate * learner._openness_mod,
            ),
        )
        learner._feedback_counts = data.get(
            "feedback_counts",
            {"accepted": 0, "rejected": 0, "ignored": 0},
        )
        # Restore correlations
        if "correlations" in data:
            for name, values in data["correlations"].items():
                if name in learner._correlations:
                    learner._correlations[name] = deque(values, maxlen=_CORRELATION_WINDOW)
        # Restore reward history
        if "reward_history" in data:
            learner._reward_history = deque(data["reward_history"], maxlen=_CORRELATION_WINDOW)
        return learner

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        total_drift = sum(self.drift_from_seed.values()) if self.seed_values else 0.0
        return (
            f"MetaLearner(params={N_PARAMS}, "
            f"updates={self.adaptation_count}, "
            f"total_drift={total_drift:.4f})"
        )
