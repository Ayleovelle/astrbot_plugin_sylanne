"""Pure multi-timescale dynamics for Sylanne v3 (design section 9)."""

from .models import MultiscaleAdvance
from .multiscale import (
    advance_dynamics,
    advance_state,
    compute_drive,
    jacobian_absolute_upper_bound_full,
    multiscale_jacobian_bound,
    select_valid_next_axes,
    spectral_l2_upper_bound,
    validate_jacobian_gate,
)

__all__ = [
    "MultiscaleAdvance",
    "advance_dynamics",
    "advance_state",
    "compute_drive",
    "jacobian_absolute_upper_bound_full",
    "multiscale_jacobian_bound",
    "select_valid_next_axes",
    "spectral_l2_upper_bound",
    "validate_jacobian_gate",
]
