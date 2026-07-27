"""Build immutable core observation facts from authorized v2 snapshot facts.

The adapter reads the frozen ``V2TurnObservationSnapshotV1``, resolves the
authoritative ``TurnContextClass`` (rejecting any snapshot context bit that
contradicts it), maps the bridge ``ActualAction`` to a core ``Action`` (UNKNOWN /
UNMATCHED collapse to a cleared previous action), and hands only immutable core
DTOs to ``sylanne_alpha.v3core``.  It holds no host handle and imports nothing
capable of I/O.
"""

from __future__ import annotations

from sylanne_alpha.v2core.shadow_snapshot import V2TurnObservationSnapshotV1
from sylanne_alpha.v3bridge.actual_action import ActualAction
from sylanne_alpha.v3core.contracts import Action, TurnContextClass
from sylanne_alpha.v3core.observation.encoder import encode_observation, project_outcome
from sylanne_alpha.v3core.observation.models import ObservationFacts, ObservationFrame, OutcomeFrame

# UNKNOWN / UNMATCHED_RESPONSE intentionally absent: they clear the previous action.
_PREVIOUS_ACTION_MAP = {
    ActualAction.SPEAK: Action.SPEAK,
    ActualAction.HOLD: Action.HOLD,
    ActualAction.CLARIFY: Action.CLARIFY,
    ActualAction.REACH: Action.REACH,
}

# (addressed, idle, proactive) expected boolean encoding of each context class.
_EXPECTED_CONTEXT_BITS = {
    TurnContextClass.ADDRESSED: (True, False, False),
    TurnContextClass.AMBIENT: (False, False, False),
    TurnContextClass.IDLE: (False, True, False),
    TurnContextClass.PROACTIVE: (False, False, True),
}

# Value-bearing raw channels (index -> snapshot attribute) copied verbatim.
_DIRECT_CHANNELS = {
    0: "body_warmth",
    1: "body_tension",
    2: "body_repair_pressure",
    3: "body_intimacy_gravity",
    4: "body_surprise",
    5: "body_mean_surprise",
    6: "body_precision",
    7: "body_scar",
    8: "body_strain",
    9: "body_sovereignty",
    10: "body_exhaustion",
    11: "body_expression_drive",
    12: "body_threshold_drift",
    14: "body_void_pressure",
    15: "body_load",
    16: "body_plasticity",
    17: "body_boundary_pressure",
    19: "text_warm",
    20: "text_cold",
    21: "text_distress",
    23: "text_exclaim",
    24: "text_punct",
    25: "text_valence_cue",
    26: "text_engagement_cue",
    31: "gap_seconds",
}


def _bool_channel(value: bool | None) -> float | None:
    if value is None:
        return None
    return 1.0 if value else 0.0


def _verify_context(snapshot: V2TurnObservationSnapshotV1, context: TurnContextClass) -> None:
    expected = _EXPECTED_CONTEXT_BITS[context]
    for name, expected_bit in zip(("addressed", "idle", "proactive"), expected):
        actual = getattr(snapshot, name)
        if actual is not None and actual != expected_bit:
            raise ValueError("snapshot context bit contradicts the authoritative context class")


def build_observation_facts(
    snapshot: V2TurnObservationSnapshotV1,
    context: TurnContextClass,
    previous_action: ActualAction,
) -> ObservationFacts:
    """Assemble immutable ObservationFacts from authorized snapshot facts."""

    if type(snapshot) is not V2TurnObservationSnapshotV1:
        raise TypeError("snapshot must have exact type V2TurnObservationSnapshotV1")
    if type(context) is not TurnContextClass:
        raise TypeError("context must have exact type TurnContextClass")
    if type(previous_action) is not ActualAction:
        raise TypeError("previous_action must have exact type ActualAction")

    _verify_context(snapshot, context)

    raw: list[float | None] = [None] * 36
    for index, attribute in _DIRECT_CHANNELS.items():
        raw[index] = getattr(snapshot, attribute)
    raw[13] = None if snapshot.body_epoch is None else float(snapshot.body_epoch)
    raw[18] = None if snapshot.text_length is None else float(snapshot.text_length)
    raw[22] = _bool_channel(snapshot.text_question)
    raw[30] = _bool_channel(snapshot.history_present)

    resolved = _PREVIOUS_ACTION_MAP.get(previous_action)
    return ObservationFacts(raw_values=tuple(raw), context=context, previous_action=resolved)


def encode_snapshot(
    snapshot: V2TurnObservationSnapshotV1,
    context: TurnContextClass,
    previous_action: ActualAction,
) -> ObservationFrame:
    """Build facts and encode them into the fixed 36-channel observation frame."""

    return encode_observation(build_observation_facts(snapshot, context, previous_action))


def build_outcome_frame(next_frame: ObservationFrame) -> OutcomeFrame:
    """Supply the eight-axis OutcomeFrame via the pure core projection."""

    return project_outcome(next_frame)


__all__ = [
    "build_observation_facts",
    "build_outcome_frame",
    "encode_snapshot",
]
