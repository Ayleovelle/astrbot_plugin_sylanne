"""Delayed-credit outcome settlement (design sections 8.3 / 11.2) and the
formula-v2 label-free reaction signal (spec 2026-07-18 §1)."""

from .outcomes import (
    SettlementResult,
    ekf_transition_update,
    freeze_actual_prediction,
    posterior_dim,
    preference_expected_log_term,
    predictive_preference_terms,
    settle_reward,
    settle_with,
)
from .reaction import ReactionResult, gap_attenuation, reaction_signal

__all__ = [
    "ReactionResult",
    "SettlementResult",
    "ekf_transition_update",
    "freeze_actual_prediction",
    "gap_attenuation",
    "posterior_dim",
    "preference_expected_log_term",
    "predictive_preference_terms",
    "reaction_signal",
    "settle_reward",
    "settle_with",
]
