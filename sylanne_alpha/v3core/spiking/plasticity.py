"""Reward-gated STDP settlement (design section 8.3).

Only excitatory-to-excitatory synapses are plastic.  A committed turn's frozen
eligibility tensor settles exactly once at ``t+1``.  Credit is gated by the
originating STDP profile and shadow/actual action equality; the weight update
combines a credit term and a homeostatic pull toward ``W0`` and then applies a
deterministic per-postsynaptic incoming-budget projection in canonical
``synapse_id`` order, so per-edge bounds, Dale signs, and the incoming
absolute-weight limit ``<= 1.2`` all hold simultaneously after every update.

Pure stdlib math over immutable tuples: no NumPy, no I/O, no clocks, no
randomness, no callbacks.
"""

from __future__ import annotations

from ..contracts import Action
from ..formula_v1 import (
    PLASTIC_SYNAPSES,
    RECURRENT_TOPOLOGY,
    SNN_BASELINE_BOUNDS,
    SNN_BASELINE_DECAY,
    SNN_BASELINE_LEARN,
    SNN_EXCITATORY,
    SNN_EXCITATORY_WEIGHT_BOUNDS,
    SNN_INCOMING_L1_LIMIT,
    SNN_STDP_HOMEOSTASIS,
    SNN_STDP_INITIAL_WEIGHT,
    SNN_STDP_LEARNING_RATE,
    recurrent_initial_weight,
    recurrent_is_plastic,
)

_COUNT = len(PLASTIC_SYNAPSES)
_LO, _HI = SNN_EXCITATORY_WEIGHT_BOUNDS
_W0 = SNN_STDP_INITIAL_WEIGHT
_BASE_LO, _BASE_HI = SNN_BASELINE_BOUNDS


# --------------------------------------------------------------------------- #
# Precomputed per-postsynaptic projection structure (pure, from formula topology)
# --------------------------------------------------------------------------- #


def _build_plastic_by_post() -> tuple[tuple[int, ...], ...]:
    """Plastic synapse indices grouped by postsynaptic neuron in canonical order."""

    grouped: list[list[int]] = [[] for _ in range(SNN_EXCITATORY)]
    for index, (post, _pre) in enumerate(PLASTIC_SYNAPSES):
        grouped[post].append(index)
    return tuple(tuple(indices) for indices in grouped)


def _build_fixed_incoming_l1() -> tuple[float, ...]:
    """Immutable (non-plastic) incoming absolute weight sum per postsynaptic neuron."""

    return tuple(
        sum(
            abs(recurrent_initial_weight(post, pre))
            for pre in RECURRENT_TOPOLOGY[post]
            if not recurrent_is_plastic(post, pre)
        )
        for post in range(SNN_EXCITATORY)
    )


_PLASTIC_BY_POST = _build_plastic_by_post()
_FIXED_INCOMING_L1 = _build_fixed_incoming_l1()


def _clip(value: float, low: float, high: float) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


# --------------------------------------------------------------------------- #
# Credit gate, delta, baseline
# --------------------------------------------------------------------------- #


def compute_credit_gate(
    stdp_credit_enabled: bool,
    shadow_action: object,
    actual_action: object,
) -> bool:
    """Credit requires an STDP-enabled origin and shadow == known actual action."""

    return (
        bool(stdp_credit_enabled)
        and type(shadow_action) is Action
        and type(actual_action) is Action
        and shadow_action == actual_action
    )


def stdp_delta(reward: float, baseline_before: float, credit_gate: bool) -> float:
    """``credit_gate * (reward - baseline_before)`` (design 8.3)."""

    if type(reward) is not float or type(baseline_before) is not float:
        raise TypeError("reward and baseline_before must be floats")
    if not credit_gate:
        return 0.0
    return reward - baseline_before


def update_baseline(baseline: float, reward: float) -> float:
    """Bounded per-action exponential mean ``clip(0.95*baseline + 0.05*reward, -1, 1)``."""

    if type(baseline) is not float or type(reward) is not float:
        raise TypeError("baseline and reward must be floats")
    return _clip(SNN_BASELINE_DECAY * baseline + SNN_BASELINE_LEARN * reward, _BASE_LO, _BASE_HI)


# --------------------------------------------------------------------------- #
# One-shot weight update with canonical incoming-budget projection
# --------------------------------------------------------------------------- #


def _check_vector(values: object, name: str) -> None:
    if type(values) is not tuple or len(values) != _COUNT:
        raise ValueError(f"{name} must have exactly {_COUNT} entries")


def apply_stdp(
    plastic_weights: tuple[float, ...],
    eligibility: tuple[float, ...],
    delta: float,
) -> tuple[tuple[float, ...], float]:
    """Return the projected new plastic weights and the total projected-away mass.

    Per synapse ``candidate = clip(W + 0.002*delta*e - 1e-5*(W - W0), [0, 0.35])``.
    Then, per postsynaptic neuron, iterate the plastic incoming edges in canonical
    ``synapse_id`` order assigning ``W' = min(candidate, remaining_budget)`` with
    ``budget = 1.2 - fixed_incoming_l1``; once the budget reaches zero every later
    plastic candidate becomes zero.
    """

    _check_vector(plastic_weights, "plastic_weights")
    _check_vector(eligibility, "eligibility")
    if type(delta) is not float:
        raise TypeError("delta must be a float")

    candidates = [
        _clip(
            plastic_weights[index]
            + SNN_STDP_LEARNING_RATE * delta * eligibility[index]
            - SNN_STDP_HOMEOSTASIS * (plastic_weights[index] - _W0),
            _LO,
            _HI,
        )
        for index in range(_COUNT)
    ]

    projected = list(plastic_weights)
    clipped_mass = 0.0
    for post in range(SNN_EXCITATORY):
        remaining = SNN_INCOMING_L1_LIMIT - _FIXED_INCOMING_L1[post]
        if remaining < 0.0:
            remaining = 0.0
        for index in _PLASTIC_BY_POST[post]:
            candidate = candidates[index]
            assigned = candidate if candidate < remaining else remaining
            if assigned < 0.0:
                assigned = 0.0
            clipped_mass += candidate - assigned
            projected[index] = assigned
            remaining -= assigned
            if remaining < 0.0:
                remaining = 0.0
    return tuple(projected), clipped_mass


def settle_stdp(
    plastic_weights: tuple[float, ...],
    eligibility: tuple[float, ...],
    reward: float,
    baseline_before: float,
    credit_gate: bool,
) -> tuple[tuple[float, ...], float]:
    """One-shot settlement: derive the gated delta and project the weight update."""

    delta = stdp_delta(reward, baseline_before, credit_gate)
    return apply_stdp(plastic_weights, eligibility, delta)


__all__ = [
    "apply_stdp",
    "compute_credit_gate",
    "settle_stdp",
    "stdp_delta",
    "update_baseline",
]
