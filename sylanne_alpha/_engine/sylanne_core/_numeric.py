"""Shared numeric-coercion helpers (leaf module, stdlib-only).

Lives at the package root so both the LLM assessor (``sylanne_core.assessor``) and
the compute core (``sylanne_core.compute.*``) can borrow the same None-safe float
coercion without an import cycle or a layering inversion — neither side has to reach
into the other for a small numeric guard.
"""

from __future__ import annotations

import math
from typing import Any


def _coerce_float(value: Any, lo: float, hi: float, default: float) -> float:
    """Best-effort float clamped to ``[lo, hi]``.

    Untrusted input falls back to ``default`` rather than raising OR leaking a
    garbage value:

    - missing/``None`` field or non-numeric string -> ``TypeError``/``ValueError``;
    - out-of-range integer (e.g. a 400-digit JSON number) -> ``OverflowError``;
    - non-finite float (``NaN`` / ``±inf``) — which ``float()`` accepts and ``json``
      even parses from the literals ``NaN``/``Infinity`` — would otherwise slip past
      the ``except`` and the clamp silently maps it to a bound (``NaN`` wound_risk
      -> ``1.0``), so a garbage read becomes a maxed-out signal.

    Keeps one malformed scalar from toppling, or quietly maxing out, the whole tick.
    """
    try:
        f_val = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(f_val):  # NaN / ±inf from untrusted input
        return default
    return max(lo, min(hi, f_val))
