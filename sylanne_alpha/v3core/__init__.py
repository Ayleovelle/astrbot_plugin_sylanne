"""Pure deterministic contracts and formula manifest for Sylanne v3."""

from .canonical import _install_declared_types
from .contracts import (
    Action,
    ComputeProfile,
    CoreInvocation,
    SessionRef,
    TurnContextClass,
    TurnEnvelope,
    TurnKey,
    TurnSequence,
)
from .effects.models import EffectBundle, V3MetricEffect, V3StateEffect, V3TraceEffect
from .state.models import (
    ActionBeliefs,
    ExperienceRecord,
    LabelFreeState,
    PendingOutcome,
    V3State,
)


_install_declared_types(
    dto_types=(
        SessionRef,
        TurnSequence,
        TurnKey,
        ComputeProfile,
        TurnEnvelope,
        CoreInvocation,
        V3StateEffect,
        V3TraceEffect,
        V3MetricEffect,
        EffectBundle,
        PendingOutcome,
        ActionBeliefs,
        ExperienceRecord,
        LabelFreeState,
        V3State,
    ),
    enum_types=(Action, TurnContextClass),
)

from .formula_v1 import FORMULA_DIGEST, FORMULA_VERSION  # noqa: E402

__all__ = ["FORMULA_DIGEST", "FORMULA_VERSION"]
