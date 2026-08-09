"""Autonomous-action refractory state transition (design section 10).

``rho_a`` is a separate autonomous-action refractory scalar for ``HOLD`` and
``REACH`` only; it is never the observation-likelihood variance ``R_a``.  It
starts at zero and updates once per committed turn:

* first decay ``rho_a_decay = 0.80 * rho_a``;
* the pre-score log-prior penalty entering policy scoring is ``2 * rho_a_decay``
  for ``HOLD``/``REACH`` in ``PROACTIVE``/``IDLE`` (bounded to ``[0,2]``) and
  ``0`` otherwise; and
* after the turn's action is selected, ``rho_a' = clip(rho_a_decay + 0.35 *
  1[context in {PROACTIVE,IDLE} and selected == a], 0, 1)``.

``ADDRESSED``/``AMBIENT`` turns only decay ``rho`` and never penalise ``SPEAK``.
Pure stdlib arithmetic: no I/O, no clocks, no callbacks.
"""

from __future__ import annotations

from ..contracts import Action, TurnContextClass
from ..formula_v1 import (
    RHO_BOUNDS,
    RHO_DECAY,
    RHO_PENALTY_CONTEXTS,
    RHO_POST_SELECTION_INCREMENT,
    RHO_PRE_SCORE_PENALTY_MULTIPLIER,
)

_RHO_LO, _RHO_HI = RHO_BOUNDS
_PENALTY_BOUND = 2.0
_AUTONOMOUS_ACTIONS = (Action.HOLD, Action.REACH)


def _clip(value: float, low: float, high: float) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


def rho_decay(rho: float) -> float:
    """Pre-update decay ``0.80 * rho``."""

    if type(rho) is not float:
        raise TypeError("rho must be a float")
    return RHO_DECAY * rho


def _is_penalty_context(context: TurnContextClass) -> bool:
    return context.value in RHO_PENALTY_CONTEXTS


def autonomous_refractory_penalty(
    context: object,
    action: object,
    rho_hold: float,
    rho_reach: float,
) -> float:
    """Bounded pre-score log-prior penalty for one legal action (design 10/11.3)."""

    if type(context) is not TurnContextClass:
        raise TypeError("context must have exact type TurnContextClass")
    if type(action) is not Action:
        raise TypeError("action must have exact type Action")
    if type(rho_hold) is not float or type(rho_reach) is not float:
        raise TypeError("rho values must be floats")
    if not _is_penalty_context(context) or action not in _AUTONOMOUS_ACTIONS:
        return 0.0
    rho = rho_hold if action is Action.HOLD else rho_reach
    penalty = RHO_PRE_SCORE_PENALTY_MULTIPLIER * rho_decay(rho)
    return _clip(penalty, 0.0, _PENALTY_BOUND)


def advance_autonomous_refractory(
    context: object,
    selected_action: object,
    rho_hold: float,
    rho_reach: float,
) -> tuple:
    """Return the committed ``(rho_hold', rho_reach')`` after this turn's decision."""

    if type(context) is not TurnContextClass:
        raise TypeError("context must have exact type TurnContextClass")
    if type(selected_action) is not Action:
        raise TypeError("selected_action must have exact type Action")
    if type(rho_hold) is not float or type(rho_reach) is not float:
        raise TypeError("rho values must be floats")

    decayed_hold = rho_decay(rho_hold)
    decayed_reach = rho_decay(rho_reach)
    increment = _is_penalty_context(context)
    next_hold = decayed_hold + (
        RHO_POST_SELECTION_INCREMENT if increment and selected_action is Action.HOLD else 0.0
    )
    next_reach = decayed_reach + (
        RHO_POST_SELECTION_INCREMENT if increment and selected_action is Action.REACH else 0.0
    )
    return _clip(next_hold, _RHO_LO, _RHO_HI), _clip(next_reach, _RHO_LO, _RHO_HI)


__all__ = [
    "advance_autonomous_refractory",
    "autonomous_refractory_penalty",
    "rho_decay",
]
