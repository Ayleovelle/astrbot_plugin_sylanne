"""Delayed-credit outcome settlement (design sections 8.3 / 11.2)."""

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

__all__ = [
    "SettlementResult",
    "ekf_transition_update",
    "freeze_actual_prediction",
    "posterior_dim",
    "preference_expected_log_term",
    "predictive_preference_terms",
    "settle_reward",
    "settle_with",
]
