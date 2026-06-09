"""Online reinforcement learning expression policy for SylannEngine.

Replaces the static threshold-based expression decision with a contextual
bandit that learns optimal expression timing from interaction feedback.

Theoretical grounding:
- Williams (1992): REINFORCE — policy gradient for discrete actions
- Sutton & Barto (2018): Contextual bandits as single-step RL
- Auer et al. (2002): Finite-time analysis of UCB — exploration/exploitation
- Friston (2010): Active inference — action selection under uncertainty

Design principles:
- State features capture the full expression context (~10 dims)
- Logistic policy: P(express | context) = sigmoid(w . context + bias)
- REINFORCE-style gradient update from accept/reject/ignore feedback
- Hard safety constraints override learned policy at extremes
- Epsilon-greedy exploration with decay for initial learning
- Personality modulates learning rate (openness -> faster adaptation)
- Trivial persistence: 10 weights + bias + metadata
"""

from __future__ import annotations

import math
import random
from collections import deque
from typing import Any

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
# Constants
# ---------------------------------------------------------------------------

# Feature names in canonical order
FEATURE_NAMES: list[str] = [
    "expression_drive",
    "expression_threshold",
    "phi",
    "sync_order",
    "energy",
    "ticks_since_last_expression",
    "ticks_since_last_user_message",
    "recent_accept_rate",
    "recent_reject_rate",
    "personality_extraversion",
]

N_FEATURES: int = len(FEATURE_NAMES)

# Hard constraint boundaries
_DRIVE_FORCE_EXPRESS: float = 0.95  # Always express above this
_DRIVE_FORCE_HOLD: float = 0.1  # Never express below this

# Exploration schedule
_EPSILON_START: float = 0.3
_EPSILON_END: float = 0.05
_EPSILON_DECAY_STEPS: int = 200

# Reward values
_REWARD_ACCEPTED: float = 1.0
_REWARD_REJECTED: float = -1.0
_REWARD_IGNORED: float = -0.3

# Rolling window size for rate tracking
_FEEDBACK_WINDOW: int = 30
_REWARD_WINDOW: int = 50


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid for a single float."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    exp_x = math.exp(x)
    return exp_x / (1.0 + exp_x)


def _dot(a: list[float], b: list[float]) -> float:
    """Dot product of two equal-length lists."""
    if _HAS_NUMPY:
        return float(np.dot(a, b))
    return sum(ai * bi for ai, bi in zip(a, b))


# ---------------------------------------------------------------------------
# ExpressionPolicy class
# ---------------------------------------------------------------------------


class ExpressionPolicy:
    """Contextual bandit that learns expression timing from feedback.

    State features (context vector, 10 dims):
      - expression_drive: current drive level from resonance field
      - expression_threshold: current adaptive threshold
      - phi: integrated information (meaningfulness)
      - sync_order: Kuramoto synchronization order parameter
      - energy: resonance field energy
      - ticks_since_last_expression: silence pressure
      - ticks_since_last_user_message: recency of user engagement
      - recent_accept_rate: rolling acceptance rate
      - recent_reject_rate: rolling rejection rate
      - personality_extraversion: trait modulating expressiveness

    Action: binary — express (1) or hold (0)

    Policy: logistic regression on context features
      P(express | context) = sigmoid(w . context + bias)

    Learning: REINFORCE-style policy gradient
      w += lr * reward * gradient_log_policy(action, context)
    """

    __slots__ = (
        "weights",
        "bias",
        "_learning_rate",
        "_base_learning_rate",
        "_openness_mod",
        "_epsilon",
        "_step_count",
        "_total_updates",
        "_feedback_history",
        "_reward_history",
        "_last_context",
        "_last_action",
        "_last_prob",
    )

    def __init__(
        self,
        learning_rate: float = 0.05,
        personality_openness: float = 0.5,
    ):
        """Initialize the expression policy.

        Args:
            learning_rate: Base learning rate for weight updates.
            personality_openness: Openness trait modulates adaptation speed.
        """
        # Policy parameters: weights for each feature + bias
        self.weights: list[float] = [0.0] * N_FEATURES
        self.bias: float = 0.0

        # Initialize with mild priors that encode reasonable heuristics:
        # - expression_drive should positively influence expression
        # - expression_threshold should negatively influence (higher bar = less expression)
        # - phi (meaningfulness) should positively influence
        # - ticks_since_last_expression should positively influence (silence pressure)
        self.weights[0] = 0.5   # expression_drive: express when drive is high
        self.weights[1] = -0.3  # expression_threshold: respect the threshold
        self.weights[2] = 0.2   # phi: meaningful states deserve expression
        self.weights[3] = 0.1   # sync_order: coherent states are expressive
        self.weights[4] = 0.1   # energy: high energy -> more expression
        self.weights[5] = 0.2   # ticks_since_last_expression: silence builds pressure
        self.weights[6] = -0.1  # ticks_since_last_user_message: don't talk to void
        self.weights[7] = 0.3   # recent_accept_rate: success breeds confidence
        self.weights[8] = -0.3  # recent_reject_rate: rejection breeds caution
        self.weights[9] = 0.2   # personality_extraversion: extraverts express more

        # Learning rate modulated by openness
        self._base_learning_rate = learning_rate
        self._openness_mod = 0.5 + personality_openness  # Range: [0.5, 1.5]
        self._learning_rate = learning_rate * self._openness_mod

        # Exploration
        self._epsilon = _EPSILON_START
        self._step_count = 0

        # Tracking
        self._total_updates = 0
        self._feedback_history: deque[str] = deque(maxlen=_FEEDBACK_WINDOW)
        self._reward_history: deque[float] = deque(maxlen=_REWARD_WINDOW)

        # Last decision state (needed for credit assignment)
        self._last_context: list[float] | None = None
        self._last_action: int | None = None
        self._last_prob: float = 0.5

    # ------------------------------------------------------------------
    # Policy computation
    # ------------------------------------------------------------------

    def _compute_probability(self, context: list[float]) -> float:
        """Compute P(express | context) = sigmoid(w . context + bias)."""
        logit = _dot(self.weights, context) + self.bias
        # Clamp logit to prevent overflow
        logit = max(-20.0, min(20.0, logit))
        return _sigmoid(logit)

    def decide(self, context: list[float]) -> tuple[bool, float]:
        """Make an expression decision given the current context.

        Args:
            context: Feature vector of length N_FEATURES. Values should be
                     roughly normalized to [0, 1] or [-1, 1] range.

        Returns:
            Tuple of (should_express, confidence) where confidence is
            how certain the policy is about its decision.

        Hard constraints override the learned policy:
          - drive > 0.95 -> always express (safety: extreme emotion must out)
          - drive < 0.1  -> never express (nothing to say)
        """
        if len(context) != N_FEATURES:
            raise ValueError(
                f"Context must have {N_FEATURES} features, got {len(context)}"
            )

        drive = context[0]  # expression_drive is feature 0

        # Hard constraint: extreme drive forces expression
        if drive > _DRIVE_FORCE_EXPRESS:
            self._last_context = list(context)
            self._last_action = 1
            self._last_prob = 1.0
            return True, 1.0

        # Hard constraint: negligible drive prevents expression
        if drive < _DRIVE_FORCE_HOLD:
            self._last_context = list(context)
            self._last_action = 0
            self._last_prob = 0.0
            return False, 1.0

        # Learned policy
        prob_express = self._compute_probability(context)

        # Epsilon-greedy exploration
        if random.random() < self._epsilon:
            # Explore: random action
            action = random.randint(0, 1)
        else:
            # Exploit: threshold at 0.5
            action = 1 if prob_express > 0.5 else 0

        # Store decision state for credit assignment
        self._last_context = list(context)
        self._last_action = action
        self._last_prob = prob_express
        self._step_count += 1

        # Decay epsilon
        self._epsilon = _EPSILON_END + (
            (_EPSILON_START - _EPSILON_END)
            * max(0.0, 1.0 - self._step_count / _EPSILON_DECAY_STEPS)
        )

        # Confidence: how far from 0.5 the probability is
        confidence = abs(prob_express - 0.5) * 2.0

        return bool(action == 1), confidence

    # ------------------------------------------------------------------
    # Learning from feedback
    # ------------------------------------------------------------------

    def update_from_feedback(
        self,
        outcome: str,
        context_at_decision: list[float] | None = None,
    ) -> None:
        """Update policy weights from interaction feedback.

        Uses REINFORCE-style policy gradient:
          w += lr * reward * d/dw log pi(a|s)

        For logistic policy:
          If action=1 (expressed): gradient = context * (1 - prob)
          If action=0 (held):      gradient = context * (-prob)

        Args:
            outcome: One of "accepted", "rejected", "ignored".
            context_at_decision: The context vector at the time of the decision.
                If None, uses the stored last context.
        """
        # Determine reward
        if outcome == "accepted":
            reward = _REWARD_ACCEPTED
        elif outcome == "rejected":
            reward = _REWARD_REJECTED
        elif outcome == "ignored":
            reward = _REWARD_IGNORED
        else:
            return  # Unknown outcome, skip

        # Track feedback
        self._feedback_history.append(outcome)
        self._reward_history.append(reward)
        self._total_updates += 1

        # Get context and action for this update
        context = context_at_decision if context_at_decision is not None else self._last_context
        action = self._last_action

        if context is None or action is None:
            return  # No decision to update from

        # Compute probability at the stored context
        prob = self._compute_probability(context)

        # REINFORCE gradient of log pi(a|s):
        # If action=1: d/dw log(prob) = (1 - prob) * context
        # If action=0: d/dw log(1 - prob) = -prob * context
        if action == 1:
            grad_scale = reward * (1.0 - prob)
        else:
            # For hold action, reward sign is flipped conceptually:
            # positive reward for holding means "good that we didn't express"
            # but our reward is defined relative to expression outcome,
            # so we use: gradient pushes AWAY from expressing when reward is negative
            grad_scale = reward * (-prob)

        # Update weights
        lr = self._learning_rate
        if _HAS_NUMPY:
            w_arr = np.array(self.weights, dtype=np.float64)
            c_arr = np.array(context, dtype=np.float64)
            w_arr += lr * grad_scale * c_arr
            # Clamp weights to prevent divergence
            w_arr = np.clip(w_arr, -5.0, 5.0)
            self.weights = w_arr.tolist()
        else:
            for i in range(N_FEATURES):
                self.weights[i] += lr * grad_scale * context[i]
                self.weights[i] = max(-5.0, min(5.0, self.weights[i]))

        # Update bias
        self.bias += lr * grad_scale * 1.0  # bias gradient is just the scale
        self.bias = max(-3.0, min(3.0, self.bias))

    # ------------------------------------------------------------------
    # Personality modulation
    # ------------------------------------------------------------------

    def set_personality(self, openness: float = 0.5) -> None:
        """Update personality modulation of learning rate.

        Args:
            openness: Openness trait value in [0, 1].
                Higher openness -> faster adaptation to feedback.
        """
        self._openness_mod = 0.5 + openness
        self._learning_rate = self._base_learning_rate * self._openness_mod

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    @property
    def policy_confidence(self) -> float:
        """How certain the policy is about the last decision.

        Returns value in [0, 1] where 1 = maximally confident.
        """
        if self._last_prob is None:
            return 0.0
        return abs(self._last_prob - 0.5) * 2.0

    @property
    def exploration_rate(self) -> float:
        """Current epsilon (exploration probability)."""
        return self._epsilon

    @property
    def recent_reward_avg(self) -> float:
        """Rolling average reward over recent interactions."""
        if not self._reward_history:
            return 0.0
        return sum(self._reward_history) / len(self._reward_history)

    @property
    def recent_accept_rate(self) -> float:
        """Rolling acceptance rate from feedback history."""
        if not self._feedback_history:
            return 0.0
        return sum(1 for f in self._feedback_history if f == "accepted") / len(
            self._feedback_history
        )

    @property
    def recent_reject_rate(self) -> float:
        """Rolling rejection rate from feedback history."""
        if not self._feedback_history:
            return 0.0
        return sum(1 for f in self._feedback_history if f == "rejected") / len(
            self._feedback_history
        )

    def weight_summary(self) -> list[tuple[str, float]]:
        """Feature importance ranking by absolute weight value.

        Returns:
            List of (feature_name, weight) tuples sorted by |weight| descending.
        """
        pairs = list(zip(FEATURE_NAMES, self.weights))
        pairs.sort(key=lambda p: abs(p[1]), reverse=True)
        return pairs

    def diagnostics(self) -> dict[str, Any]:
        """Full diagnostic snapshot of the policy state.

        Returns:
            Dict with policy parameters, performance metrics, and feature weights.
        """
        return {
            "weights": dict(zip(FEATURE_NAMES, [round(w, 4) for w in self.weights])),
            "bias": round(self.bias, 4),
            "learning_rate": round(self._learning_rate, 4),
            "epsilon": round(self._epsilon, 4),
            "step_count": self._step_count,
            "total_updates": self._total_updates,
            "recent_reward_avg": round(self.recent_reward_avg, 4),
            "recent_accept_rate": round(self.recent_accept_rate, 4),
            "recent_reject_rate": round(self.recent_reject_rate, 4),
            "policy_confidence": round(self.policy_confidence, 4),
            "top_features": [
                (name, round(w, 4)) for name, w in self.weight_summary()[:5]
            ],
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize policy state for persistence.

        The serialized form is compact: 10 weights + bias + metadata.
        """
        return {
            "weights": list(self.weights),
            "bias": self.bias,
            "base_learning_rate": self._base_learning_rate,
            "openness_mod": self._openness_mod,
            "epsilon": self._epsilon,
            "step_count": self._step_count,
            "total_updates": self._total_updates,
            "feedback_history": list(self._feedback_history),
            "reward_history": list(self._reward_history),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExpressionPolicy:
        """Reconstruct an ExpressionPolicy from serialized state.

        Args:
            data: Dict as produced by to_dict().

        Returns:
            Reconstructed ExpressionPolicy instance.
        """
        policy = cls(
            learning_rate=data.get("base_learning_rate", 0.05),
            personality_openness=(data.get("openness_mod", 1.0) - 0.5),
        )
        if "weights" in data:
            weights = list(data["weights"])
            # Handle dimension mismatch gracefully (future-proofing)
            if len(weights) < N_FEATURES:
                weights.extend([0.0] * (N_FEATURES - len(weights)))
            policy.weights = weights[:N_FEATURES]
        if "bias" in data:
            policy.bias = float(data["bias"])
        policy._epsilon = data.get("epsilon", _EPSILON_START)
        policy._step_count = data.get("step_count", 0)
        policy._total_updates = data.get("total_updates", 0)
        if "feedback_history" in data:
            policy._feedback_history = deque(data["feedback_history"], maxlen=_FEEDBACK_WINDOW)
        if "reward_history" in data:
            policy._reward_history = deque(
                data["reward_history"], maxlen=_REWARD_WINDOW
            )
        return policy

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"ExpressionPolicy(steps={self._step_count}, "
            f"epsilon={self._epsilon:.3f}, "
            f"reward_avg={self.recent_reward_avg:.3f})"
        )
