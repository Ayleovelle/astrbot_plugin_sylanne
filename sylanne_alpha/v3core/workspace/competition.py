"""Deterministic global-workspace competition (design section 10).

``ProposalArbiterV1`` builds at most eight legal, present proposals from the
decision state, the observation frame, and an optional SNN summary; runs four
bounded winner-take-all iterations with cross-proposal inhibition and a
persistent source-refractory penalty; and emits a registration-order-invariant
:class:`WorkspaceBroadcast`.  The workspace never selects the action itself; it
only produces per-legal-action support and a bounded log-evidence contribution
consumed by ``PolicyScorerV1``.

Pure stdlib float math over immutable tuples: no NumPy, no I/O, no clocks, no
callbacks, no randomness.

Two design points that section 10 fixes only structurally are pinned here as the
single formula-v1 interpretation and are traced/tested:

* the competition potential is initialised to ``0.0`` (an assumption-free neutral
  start; the four iterations then integrate the effective salience); and
* the ambiguous (top-2) branch "adds an evidence term to CLARIFY" by crediting
  ``support[CLARIFY]`` with the runner-up broadcast activation, a bounded value
  derived purely from the competition output with no new magic constant.
"""

from __future__ import annotations

from math import exp

from ..contracts import Action, TurnContextClass
from ..formula_v1 import (
    CONTEXT_ACTION_PRIORS,
    PROPOSAL_ACTIONS,
    PROPOSAL_COUNT,
    PROPOSAL_IDS,
    PROPOSAL_KEYS,
    PROPOSAL_REQUIRED_BITS,
    PROPOSAL_SALIENCE_BOUNDS,
    SOURCE_REFRACTORY_DECAY,
    SOURCE_REFRACTORY_INCREMENT,
    WORKSPACE_CAPACITY,
    WORKSPACE_INHIBITION_WEIGHT,
    WORKSPACE_ITERATIONS,
    WORKSPACE_POTENTIAL_CLIP,
    WORKSPACE_POTENTIAL_GAIN,
    WORKSPACE_POTENTIAL_INITIAL,
    WORKSPACE_POTENTIAL_LEAK,
    WORKSPACE_REFRACTORY_WEIGHT,
    WORKSPACE_SOFTMAX_TEMPERATURE,
    WORKSPACE_TOP1_ACTIVATION,
    WORKSPACE_TOP1_MARGIN,
)
from ..observation.models import ObservationFrame
from .models import WorkspaceBroadcast, WorkspaceProposal

# Competition constants (design section 10) sourced from the frozen manifest.
_ITERATIONS = WORKSPACE_ITERATIONS
_U_INITIAL = WORKSPACE_POTENTIAL_INITIAL
_U_LEAK = WORKSPACE_POTENTIAL_LEAK
_U_GAIN = WORKSPACE_POTENTIAL_GAIN
_INHIBITION_WEIGHT = WORKSPACE_INHIBITION_WEIGHT
_REFRACTORY_WEIGHT = WORKSPACE_REFRACTORY_WEIGHT
_U_CLIP = WORKSPACE_POTENTIAL_CLIP
_SOFTMAX_TEMPERATURE = WORKSPACE_SOFTMAX_TEMPERATURE
_TOP1_ACTIVATION = WORKSPACE_TOP1_ACTIVATION
_TOP1_MARGIN = WORKSPACE_TOP1_MARGIN
_SOURCE_DECAY = SOURCE_REFRACTORY_DECAY
_SOURCE_INCREMENT = SOURCE_REFRACTORY_INCREMENT
_SALIENCE_LO, _SALIENCE_HI = PROPOSAL_SALIENCE_BOUNDS

# Canonical order used for every support / log-evidence mapping so the output is
# deterministic and registration-order independent.
_ACTION_ORDER = (Action.SPEAK, Action.HOLD, Action.CLARIFY, Action.REACH)
_PROPOSAL_ACTION_ENUMS = tuple(Action[name] for name in PROPOSAL_ACTIONS)


def _clip(value: float, low: float, high: float) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        return 1.0 / (1.0 + exp(-value))
    scaled = exp(value)
    return scaled / (1.0 + scaled)


def _center(value: float) -> float:
    return 2.0 * value - 1.0


def _legal_actions(context: TurnContextClass) -> tuple:
    names = CONTEXT_ACTION_PRIORS[context.value]
    legal = frozenset(Action[name] for name in names)
    return tuple(action for action in _ACTION_ORDER if action in legal)


# --------------------------------------------------------------------------- #
# Proposal salience and construction
# --------------------------------------------------------------------------- #


def proposal_salience(
    index: int,
    decision_state: tuple,
    frame: object,
) -> tuple:
    """Return ``(clipped_salience, present)`` for one proposal.

    ``present`` is ``False`` when a required observation bit is invalid; the
    salience is still a finite clipped float in that case but the proposal is not
    constructed.  (formula v2 deleted the ``snn-novelty`` proposal and its
    SNN-summary presence gate; every surviving proposal reads only the decision
    state and the observation frame.)
    """

    if type(index) is not int or not 0 <= index < PROPOSAL_COUNT:
        raise ValueError("index must be a workspace proposal index")
    if type(frame) is not ObservationFrame:
        raise TypeError("frame must have exact type ObservationFrame")

    present = True
    for bit in PROPOSAL_REQUIRED_BITS[index]:
        if not frame.is_valid(bit):
            present = False

    s = decision_state
    v = frame.values
    if index == 0:  # body-speak
        raw = 1.2 * s[7] + 0.5 * s[1] + 0.3 * _center(v[11])
    elif index == 1:  # affect-speak
        raw = 0.9 * abs(s[0]) + 0.7 * s[3] + 0.4 * s[2]
    elif index == 2:  # uncertainty-clarify
        raw = 1.4 * s[4] + 0.4 * s[5]
    elif index == 3:  # boundary-hold
        raw = -1.3 * s[2] - 0.6 * s[6] + 0.5 * _center(v[17])
    elif index == 4:  # fatigue-hold
        raw = 1.4 * _center(v[10]) - 0.4 * s[7]
    elif index == 5:  # affiliation-reach
        raw = 1.1 * s[3] + 0.8 * s[7] + 0.3 * s[5]
    else:  # continuity-speak (index 6; old index 7 before snn-novelty deletion)
        raw = 0.8 * _center(v[30]) + 0.6 * _center(v[26]) + 0.4 * s[3]
    return _clip(raw, _SALIENCE_LO, _SALIENCE_HI), present


def _check_decision_state(decision_state: object) -> None:
    if type(decision_state) is not tuple or len(decision_state) != 8:
        raise ValueError("decision_state must have exactly 8 entries")
    for value in decision_state:
        if type(value) is not float:
            raise TypeError("decision_state entries must be floats")


def build_proposals(
    decision_state: tuple,
    frame: object,
    context: object,
) -> tuple:
    """Build the legal, present proposals for a turn (context masks illegal actions)."""

    _check_decision_state(decision_state)
    if type(context) is not TurnContextClass:
        raise TypeError("context must have exact type TurnContextClass")
    legal = frozenset(_legal_actions(context))
    proposals: list[WorkspaceProposal] = []
    for index in range(PROPOSAL_COUNT):
        action = _PROPOSAL_ACTION_ENUMS[index]
        if action not in legal:
            continue
        salience, present = proposal_salience(index, decision_state, frame)
        if not present:
            continue
        confidence = _clip(0.5 + 0.25 * abs(salience), 0.0, 1.0)
        proposals.append(
            WorkspaceProposal(
                proposal_id=PROPOSAL_IDS[index],
                action=action,
                source_index=index,
                salience=salience,
                confidence=confidence,
                key=PROPOSAL_KEYS[index],
            )
        )
    return tuple(proposals)


# --------------------------------------------------------------------------- #
# Competition and broadcast
# --------------------------------------------------------------------------- #


def _similarity(key_p: tuple, key_q: tuple) -> float:
    dot = sum(key_p[i] * key_q[i] for i in range(len(key_p)))
    return dot if dot > 0.0 else 0.0


def _softmax(potentials: tuple) -> tuple:
    scaled = [value / _SOFTMAX_TEMPERATURE for value in potentials]
    peak = max(scaled)
    exps = [exp(value - peak) for value in scaled]
    total = sum(exps)
    return tuple(value / total for value in exps)


def _next_source_refractory(
    source_refractory: tuple,
    broadcast_sources: frozenset,
) -> tuple:
    return tuple(
        _clip(
            _SOURCE_DECAY * source_refractory[index]
            + (_SOURCE_INCREMENT if index in broadcast_sources else 0.0),
            0.0,
            1.0,
        )
        for index in range(WORKSPACE_CAPACITY)
    )


def _support_and_evidence(
    proposals: tuple,
    activation: tuple,
    broadcast_ids: tuple,
    mode: str,
    context: TurnContextClass,
) -> tuple:
    legal = _legal_actions(context)
    support = {action: 0.0 for action in legal}
    id_to_index = {proposal.proposal_id: index for index, proposal in enumerate(proposals)}
    for pid in broadcast_ids:
        proposal = proposals[id_to_index[pid]]
        if proposal.action in support:
            support[proposal.action] += activation[id_to_index[pid]]
    # Ambiguous branch: add a bounded CLARIFY evidence term (runner-up activation)
    # so the workspace signals "clarify" instead of directly selecting the top-1.
    if mode == "TOP2_AMBIGUOUS" and Action.CLARIFY in support:
        runner_up = proposals[id_to_index[broadcast_ids[1]]]
        support[Action.CLARIFY] += activation[id_to_index[broadcast_ids[1]]]
        # ``runner_up`` is referenced only for clarity in the trace narrative.
        del runner_up
    mean_support = (sum(support.values()) / len(support)) if support else 0.0
    support_tuple = tuple((action.value, support[action]) for action in legal)
    log_evidence = tuple(
        (action.value, _clip(2.0 * (support[action] - mean_support), -2.0, 2.0))
        for action in legal
    )
    return support_tuple, log_evidence


def arbitrate(
    proposals: object,
    context: object,
    source_refractory: tuple,
) -> WorkspaceBroadcast:
    """Run the four-iteration competition and produce the bounded broadcast."""

    if type(context) is not TurnContextClass:
        raise TypeError("context must have exact type TurnContextClass")
    if type(source_refractory) is not tuple or len(source_refractory) != WORKSPACE_CAPACITY:
        raise ValueError("source_refractory must have one entry per source")
    proposal_list = tuple(proposals)
    for proposal in proposal_list:
        if type(proposal) is not WorkspaceProposal:
            raise TypeError("every proposal must have exact type WorkspaceProposal")
    # Canonical, registration-order-invariant ordering by proposal_id.
    ordered = tuple(sorted(proposal_list, key=lambda proposal: proposal.proposal_id))
    count = len(ordered)

    if count == 0:
        support, log_evidence = _support_and_evidence((), (), (), "EMPTY", context)
        return WorkspaceBroadcast(
            proposals=(),
            effective_salience=(),
            activation=(),
            inhibition=(),
            broadcast_ids=(),
            mode="EMPTY",
            support=support,
            log_evidence=log_evidence,
            source_refractory_next=_next_source_refractory(source_refractory, frozenset()),
        )

    effective_salience = tuple(
        proposal.salience * (0.5 + 0.5 * proposal.confidence) for proposal in ordered
    )
    keys = tuple(proposal.key for proposal in ordered)
    similarity = tuple(
        tuple(_similarity(keys[p], keys[q]) if p != q else 0.0 for q in range(count))
        for p in range(count)
    )
    refractory_penalty = tuple(source_refractory[proposal.source_index] for proposal in ordered)

    potentials = [_U_INITIAL] * count
    inhibition = [0.0] * count
    for _ in range(_ITERATIONS):
        gated = [_sigmoid(value) for value in potentials]
        new_potentials: list[float] = []
        for p in range(count):
            inhibition_term = _INHIBITION_WEIGHT * sum(
                similarity[p][q] * gated[q] for q in range(count) if q != p
            )
            inhibition[p] = inhibition_term
            drive = (
                effective_salience[p]
                - inhibition_term
                - _REFRACTORY_WEIGHT * refractory_penalty[p]
            )
            new_potentials.append(_clip(_U_LEAK * potentials[p] + _U_GAIN * drive, -_U_CLIP, _U_CLIP))
        potentials = new_potentials

    activation = _softmax(tuple(potentials))

    if count == 1:
        mode = "SINGLE_LEGAL"
        broadcast_ids = (ordered[0].proposal_id,)
    else:
        ranked = sorted(
            range(count),
            key=lambda index: (-activation[index], ordered[index].proposal_id),
        )
        p1 = activation[ranked[0]]
        p2 = activation[ranked[1]]
        if p1 >= _TOP1_ACTIVATION and (p1 - p2) >= _TOP1_MARGIN:
            mode = "TOP1"
            broadcast_ids = (ordered[ranked[0]].proposal_id,)
        else:
            mode = "TOP2_AMBIGUOUS"
            broadcast_ids = (ordered[ranked[0]].proposal_id, ordered[ranked[1]].proposal_id)

    support, log_evidence = _support_and_evidence(
        ordered, activation, broadcast_ids, mode, context
    )
    id_to_proposal = {proposal.proposal_id: proposal for proposal in ordered}
    broadcast_sources = frozenset(id_to_proposal[pid].source_index for pid in broadcast_ids)
    return WorkspaceBroadcast(
        proposals=ordered,
        effective_salience=effective_salience,
        activation=activation,
        inhibition=tuple(inhibition),
        broadcast_ids=broadcast_ids,
        mode=mode,
        support=support,
        log_evidence=log_evidence,
        source_refractory_next=_next_source_refractory(source_refractory, broadcast_sources),
    )


def run_workspace(
    decision_state: tuple,
    frame: object,
    context: object,
    source_refractory: tuple,
) -> WorkspaceBroadcast:
    """Build proposals then arbitrate them (the full section-10 stage)."""

    proposals = build_proposals(decision_state, frame, context)
    return arbitrate(proposals, context, source_refractory)


class ProposalArbiterV1:
    """Named finite-capacity arbiter (design section 18 terminology gate).

    The scientific ``GlobalWorkspace`` alias is withheld until the G4 ablation
    gates prove finite capacity, real broadcast consumers, inhibition, and
    registration-order invariance.
    """

    def build(self, decision_state: tuple, frame: object, context: object) -> tuple:
        return build_proposals(decision_state, frame, context)

    def arbitrate(self, proposals: object, context: object, source_refractory: tuple) -> WorkspaceBroadcast:
        return arbitrate(proposals, context, source_refractory)

    def run(
        self,
        decision_state: tuple,
        frame: object,
        context: object,
        source_refractory: tuple,
    ) -> WorkspaceBroadcast:
        return run_workspace(decision_state, frame, context, source_refractory)


__all__ = [
    "ProposalArbiterV1",
    "arbitrate",
    "build_proposals",
    "proposal_salience",
    "run_workspace",
]
