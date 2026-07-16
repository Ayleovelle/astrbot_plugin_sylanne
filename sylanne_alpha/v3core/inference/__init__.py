"""Finite-action active inference (design section 11)."""

from .models import (
    ActionCandidate,
    PolicyScorerResult,
    ReservoirFeaturesV1,
    TransitionBelief,
)
from .policy_scorer import (
    PolicyScorerV1,
    action_params,
    efe_ambiguity,
    generative_mu,
    information_gain,
    initial_action_beliefs,
    kl_risk,
    likelihood_variance,
    predictive_variance,
    preferences,
    score_policy,
)

__all__ = [
    "ActionCandidate",
    "PolicyScorerResult",
    "PolicyScorerV1",
    "ReservoirFeaturesV1",
    "TransitionBelief",
    "action_params",
    "efe_ambiguity",
    "generative_mu",
    "information_gain",
    "initial_action_beliefs",
    "kl_risk",
    "likelihood_variance",
    "predictive_variance",
    "preferences",
    "score_policy",
]
