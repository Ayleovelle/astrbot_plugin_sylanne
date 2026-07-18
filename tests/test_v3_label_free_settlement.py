"""RED/GREEN tests for formula-v2 Slice C: the two-learner label-free settlement.

The 2026-07-18 spec §2/§3 adds a SECOND, label-free settlement path (path B) that
shares the existing pending/adjacency/CAS skeleton but never sees the action:

* :func:`settle_label_free` is label-free -- it is not given the pending outcome and
  reads only ``latent_axes`` / ``label_free`` of the pre-state (both
  action-independent), so it cannot see the action (§4.1 guarantee 2); the property
  test pins invariance even to the action-DERIVED refractory/style fields;
* the three learners have DIFFERENT gates: L1 (preference offset) needs the origin
  turn to be reaction-eligible AND a valid reaction; L2 (marginal EKF world model)
  runs on any adjacent turn with >=1 valid outcome axis -- NOT eligibility-gated
  (spec §3.3); the length baseline runs on inbound context + a valid length bit +
  ``same_sender != False`` -- also NOT eligibility-gated (spec §3.4);
* the orchestrator wires BOTH paths onto one commit: path A writes only
  ``action_beliefs``, path B writes only ``label_free`` (disjoint), an UNKNOWN-action
  turn still advances label_free (the hole this slice closes), and a non-adjacent
  turn censors both exactly like v1;
* the trace carries the five §4.3 label-free fields and round-trips; and
* ``FORMULA_DIGEST`` is deliberately UNCHANGED this slice (the fold is Slice D).
"""

from __future__ import annotations

import ast
import inspect
import random
from dataclasses import replace
from pathlib import Path

import pytest

from sylanne_alpha.v3core import formula_v1 as formula
from sylanne_alpha.v3core.contracts import (
    Action,
    ComputeProfile,
    CoreInvocation,
    ReactionFacts,
    SessionRef,
    TurnContextClass,
    TurnEnvelope,
    TurnKey,
    TurnSequence,
)
from sylanne_alpha.v3core.features import decision_state
from sylanne_alpha.v3core.inference import initial_action_beliefs
from sylanne_alpha.v3core.inference.policy_scorer import base_preference_c, generative_mu, preferences
from sylanne_alpha.v3core.learning.label_free import (
    LabelFreeSettlement,
    prior_label_free,
    settle_label_free,
)
from sylanne_alpha.v3core.learning.outcomes import ekf_transition_update, freeze_actual_prediction
from sylanne_alpha.v3core.observation.models import ObservationFrame, OutcomeFrame
from sylanne_alpha.v3core.orchestrator import orchestrate
from sylanne_alpha.v3core.state.models import LabelFreeState, PendingOutcome, V3State
from sylanne_alpha.v3core.trace.canonical import decode_trace_bytes
from sylanne_alpha.v3core.trace.models import TRACE_SCHEMA_VERSION


AXIS_DIM = formula.AXIS_DIM
_VALENCE = 25
_ENGAGEMENT = 26
_LENGTH = 18
_GAP = 31
FULL_OUTCOME_MASK = (1 << AXIS_DIM) - 1


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def _session_ref() -> SessionRef:
    return SessionRef(key_id="key-v1", session_digest=b"s" * 32, session_generation=1)


def _frame(values: dict[int, float], valid: set[int]) -> ObservationFrame:
    raw = [0.0] * 36
    for index, value in values.items():
        raw[index] = value
    mask = 0
    for index in valid:
        mask |= 1 << index
    return ObservationFrame(values=tuple(raw), valid_mask=mask)


def _outcome(y: tuple, mask: int = FULL_OUTCOME_MASK) -> OutcomeFrame:
    return OutcomeFrame(y=y, valid_mask=mask, projector_revision=formula.OUTCOME_PROJECTOR_REVISION)


def _state(
    *,
    latent: tuple | None = None,
    label_free: LabelFreeState | None = None,
    action_beliefs: object = None,
    pending: PendingOutcome | None = None,
) -> V3State:
    return V3State(
        session_ref=_session_ref(),
        state_generation_id="gen",
        latent_axes=latent if latent is not None else tuple(0.1 for _ in range(24)),
        label_free=label_free,
        action_beliefs=action_beliefs,
        pending_outcome=pending,
    )


def _label_free(offset: float = 0.0, *, marginal_count: int = 0, reaction_count: int = 0) -> LabelFreeState:
    prior = prior_label_free()
    return LabelFreeState(
        pref_offset=tuple(offset for _ in range(AXIS_DIM)),
        marginal_theta=prior.marginal_theta,
        marginal_sigma=prior.marginal_sigma,
        marginal_count=marginal_count,
        len_baseline=prior.len_baseline,
        reaction_count=reaction_count,
    )


# --------------------------------------------------------------------------- #
# Label-free by construction (§4.1 guarantee 2)
# --------------------------------------------------------------------------- #


def test_settle_label_free_signature_has_no_action_field() -> None:
    signature = inspect.signature(settle_label_free)
    assert list(signature.parameters) == [
        "pre_state", "frame", "outcome_frame", "context", "reaction_facts", "eligible",
    ]
    # ``eligible`` is a bool derived from context_t, not an action; no parameter is
    # Action-typed (every input is a plain ``object`` guard).
    for param in signature.parameters.values():
        annotation = "" if param.annotation is inspect.Parameter.empty else str(param.annotation)
        assert "Action" not in annotation


def test_label_free_module_never_references_the_action_type_or_the_pending() -> None:
    source = Path("sylanne_alpha/v3core/learning/label_free.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    accessed_attrs: set[str] = set()
    used_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Attribute):
            accessed_attrs.add(node.attr)
        elif isinstance(node, ast.Name):
            used_names.add(node.id)
    assert "Action" not in imported and "Action" not in used_names, "must be label-free"
    # It never reads the pending, the beliefs, or any action/shadow/refractory/style
    # attribute of the pre-state (docstrings are excluded by AST).
    for forbidden in (
        "pending_outcome", "action_beliefs", "projected_actual_action", "shadow_action",
        "action", "rho_hold", "rho_reach", "style_ring",
    ):
        assert forbidden not in accessed_attrs, f"label_free.py must not access .{forbidden}"


def test_settle_label_free_is_invariant_to_every_action_derived_pre_state_field() -> None:
    """§4.1 guarantee 2: perturbing the action, beliefs, refractory, or style ring --
    all functions of the chosen shadow action -- must not move the label-free output.
    """

    frame = _frame({_VALENCE: 0.9}, {_VALENCE})
    outcome = _outcome(tuple(0.5 for _ in range(AXIS_DIM)))
    common = dict(
        session_ref=_session_ref(),
        state_generation_id="gen",
        latent_axes=tuple(0.1 for _ in range(24)),
        label_free=None,
    )
    a = V3State(
        **common,
        action_beliefs=initial_action_beliefs(),
        rho_hold=0.0,
        rho_reach=0.0,
        style_ring=(),
        pending_outcome=PendingOutcome(
            origin_turn_id="t", sequence=TurnSequence(7, 10),
            action=Action.SPEAK, projected_actual_action=Action.SPEAK, label_free_eligible=True,
        ),
    )
    b = V3State(
        **common,
        action_beliefs=replace(initial_action_beliefs(), counts=(9, 9, 9, 9)),
        rho_hold=0.9,
        rho_reach=0.7,
        style_ring=((5, 6, 7, 8),),
        pending_outcome=PendingOutcome(
            origin_turn_id="t", sequence=TurnSequence(7, 10),
            action=Action.REACH, projected_actual_action=Action.HOLD, label_free_eligible=True,
        ),
    )
    left = settle_label_free(a, frame, outcome, TurnContextClass.ADDRESSED, None, True)
    right = settle_label_free(b, frame, outcome, TurnContextClass.ADDRESSED, None, True)
    assert left.new_label_free == right.new_label_free
    assert left.marginal_mu == right.marginal_mu
    assert (left.reaction_valid, left.reason, left.r_react) == (
        right.reaction_valid, right.reason, right.r_react,
    )
    assert type(left) is LabelFreeSettlement


# --------------------------------------------------------------------------- #
# L1 preference offset update law (§3.2)
# --------------------------------------------------------------------------- #


def test_l1_offset_moves_toward_the_reaction_weighted_target() -> None:
    latent = tuple(0.1 for _ in range(24))
    s_dec = decision_state(latent)
    base_c = base_preference_c(s_dec)
    y = tuple(0.5 for _ in range(AXIS_DIM))
    result = settle_label_free(
        _state(latent=latent, label_free=None),  # None -> prior offset 0
        _frame({_VALENCE: 0.9}, {_VALENCE}),  # r_react = 2*0.9-1 = 0.8
        _outcome(y),
        TurnContextClass.ADDRESSED,
        None,
        True,
    )
    r_react = 0.8
    eta = formula.PREF_ETA * abs(r_react)
    for axis in range(AXIS_DIM):
        target = max(-0.30, min(0.30, y[axis] - base_c[axis]))
        expected = (1.0 - eta) * 0.0 + eta * target
        assert result.new_label_free.pref_offset[axis] == pytest.approx(expected, abs=1e-12)
    assert result.reaction_valid is True
    assert result.r_react == pytest.approx(0.8)


def test_l1_negative_reaction_decays_offset_toward_zero_never_reversing() -> None:
    lf = _label_free(offset=0.2)
    result = settle_label_free(
        _state(label_free=lf),
        _frame({_VALENCE: 0.1}, {_VALENCE}),  # r_react = 2*0.1-1 = -0.8
        _outcome(tuple(0.5 for _ in range(AXIS_DIM))),
        TurnContextClass.ADDRESSED,
        None,
        True,
    )
    eta = formula.PREF_ETA * 0.8
    expected = (1.0 - eta) * 0.2 + eta * 0.0  # target is 0.0 for a negative reaction
    for value in result.new_label_free.pref_offset:
        assert value == pytest.approx(expected, abs=1e-12)
        assert 0.0 < value < 0.2  # shrank toward the prior anchor, did not reverse sign


def test_l1_offset_stays_in_its_declared_box_over_a_long_random_walk() -> None:
    rng = random.Random(2718)
    base = _state()
    lf: LabelFreeState | None = None
    for _ in range(10_000):
        valence = rng.random()  # any tone -> a valid reaction that moves the offset
        y = tuple(rng.uniform(-1.0, 1.0) for _ in range(AXIS_DIM))
        result = settle_label_free(
            replace(base, label_free=lf),
            _frame({_VALENCE: valence}, {_VALENCE}),
            _outcome(y),
            TurnContextClass.ADDRESSED,
            None,
            True,
        )
        lf = result.new_label_free
        for value in lf.pref_offset:
            assert -0.30 <= value <= 0.30


def test_l1_does_not_update_the_offset_when_the_reaction_is_invalid() -> None:
    lf = _label_free(offset=0.15)
    # Eligible, but no valence/engagement -> NO_TONE_EVIDENCE, so L1 must not move.
    result = settle_label_free(
        _state(label_free=lf),
        _frame({_LENGTH: 0.9}, {_LENGTH}),
        _outcome(tuple(0.5 for _ in range(AXIS_DIM))),
        TurnContextClass.ADDRESSED,
        None,
        True,
    )
    assert result.reaction_valid is False
    assert result.reason == formula.REACTION_REASON_NO_TONE_EVIDENCE
    assert result.new_label_free.pref_offset == lf.pref_offset


def test_l1_only_touches_valid_outcome_axes() -> None:
    result = settle_label_free(
        _state(label_free=None),
        _frame({_VALENCE: 0.9}, {_VALENCE}),
        _outcome(tuple(0.5 for _ in range(AXIS_DIM)), mask=0b00000001),  # only axis 0 valid
        TurnContextClass.ADDRESSED,
        None,
        True,
    )
    assert result.new_label_free.pref_offset[0] != 0.0
    for axis in range(1, AXIS_DIM):
        assert result.new_label_free.pref_offset[axis] == 0.0


def test_l1_credit_is_withheld_when_the_origin_turn_was_ineligible() -> None:
    """Spec §3.2: even a strong valid reaction does not move the offset if turn t was
    ineligible.  L2 / len still run (see below); only the preference credit waits.
    """

    lf = _label_free(offset=0.15, marginal_count=3)
    result = settle_label_free(
        _state(label_free=lf),
        _frame({_VALENCE: 0.9, _LENGTH: 0.9}, {_VALENCE, _LENGTH}),  # a valid, strong reaction
        _outcome(tuple(0.5 for _ in range(AXIS_DIM))),
        TurnContextClass.ADDRESSED,
        None,
        False,  # ineligible origin
    )
    assert result.reaction_valid is False
    assert result.reason == formula.LF_CENSOR_REASON_NOT_ELIGIBLE
    assert result.r_react == 0.0
    assert result.new_label_free.pref_offset == lf.pref_offset  # L1 credit withheld
    # ...but L2 and the length baseline are NOT eligibility-gated (spec §3.3/§3.4).
    assert result.new_label_free.marginal_count == 4
    assert result.new_label_free.reaction_count == lf.reaction_count + 1
    assert result.new_label_free.len_baseline != lf.len_baseline


# --------------------------------------------------------------------------- #
# L2 marginal EKF (§3.3): shared core, clamped, action- and eligibility-unconditioned
# --------------------------------------------------------------------------- #


def test_l2_marginal_matches_the_shared_ekf_core() -> None:
    latent = tuple(0.2 for _ in range(24))
    s_dec = decision_state(latent)
    prior = prior_label_free()
    g = tuple(prior.marginal_theta[2 * i] for i in range(AXIS_DIM))
    b = tuple(prior.marginal_theta[2 * i + 1] for i in range(AXIS_DIM))
    sigma_g = tuple(prior.marginal_sigma[2 * i] for i in range(AXIS_DIM))
    sigma_b = tuple(prior.marginal_sigma[2 * i + 1] for i in range(AXIS_DIM))
    outcome = _outcome(tuple(0.6 for _ in range(AXIS_DIM)))
    g2, b2, sg2, sb2, count2 = ekf_transition_update(g, b, sigma_g, sigma_b, 0, s_dec, outcome)

    result = settle_label_free(
        _state(latent=latent, label_free=None),
        _frame({_LENGTH: 0.5}, {_LENGTH}),  # reaction invalid; L2 must run anyway
        outcome,
        TurnContextClass.ADDRESSED,
        None,
        True,
    )
    theta = result.new_label_free.marginal_theta
    sigma = result.new_label_free.marginal_sigma
    assert tuple(theta[2 * i] for i in range(AXIS_DIM)) == g2
    assert tuple(theta[2 * i + 1] for i in range(AXIS_DIM)) == b2
    assert tuple(sigma[2 * i] for i in range(AXIS_DIM)) == sg2
    assert tuple(sigma[2 * i + 1] for i in range(AXIS_DIM)) == sb2
    assert result.new_label_free.marginal_count == count2 == 1
    # The pre-update marginal prediction is reported for the trace.
    assert result.marginal_mu == generative_mu(g, b, s_dec)


def test_l2_updates_even_when_reaction_invalid_but_l1_does_not() -> None:
    lf = _label_free(offset=0.1, marginal_count=3)
    result = settle_label_free(
        _state(label_free=lf),
        _frame({}, set()),  # no channels valid -> NO_TONE_EVIDENCE
        _outcome(tuple(0.4 for _ in range(AXIS_DIM))),
        TurnContextClass.ADDRESSED,
        None,
        True,
    )
    assert result.reaction_valid is False
    assert result.new_label_free.pref_offset == lf.pref_offset  # L1 frozen
    assert result.new_label_free.marginal_count == 4  # L2 still advanced
    assert result.new_label_free.marginal_theta != lf.marginal_theta


def test_l2_marginal_is_clamped_to_the_action_ekf_bounds() -> None:
    result = settle_label_free(
        _state(latent=tuple(1.0 for _ in range(24)), label_free=None),
        _frame({_VALENCE: 1.0}, {_VALENCE}),
        _outcome(tuple(1.0 for _ in range(AXIS_DIM))),  # extreme error drives g/b up
        TurnContextClass.ADDRESSED,
        None,
        True,
    )
    theta = result.new_label_free.marginal_theta
    sigma = result.new_label_free.marginal_sigma
    for i in range(AXIS_DIM):
        assert formula.ACTION_G_BOUNDS[0] <= theta[2 * i] <= formula.ACTION_G_BOUNDS[1]
        assert formula.ACTION_B_BOUNDS[0] <= theta[2 * i + 1] <= formula.ACTION_B_BOUNDS[1]
        assert formula.ACTION_SIGMA_BOUNDS[0] <= sigma[2 * i] <= formula.ACTION_SIGMA_BOUNDS[1]
        assert formula.ACTION_SIGMA_BOUNDS[0] <= sigma[2 * i + 1] <= formula.ACTION_SIGMA_BOUNDS[1]


def test_l2_does_not_advance_without_a_valid_outcome_axis() -> None:
    lf = _label_free(marginal_count=5)
    result = settle_label_free(
        _state(label_free=lf),
        _frame({_VALENCE: 0.9}, {_VALENCE}),
        _outcome(tuple(0.0 for _ in range(AXIS_DIM)), mask=0),  # no valid axis
        TurnContextClass.ADDRESSED,
        None,
        True,
    )
    assert result.new_label_free.marginal_count == 5  # unchanged
    assert result.new_label_free.marginal_theta == lf.marginal_theta


# --------------------------------------------------------------------------- #
# Length baseline (§3.4): EMA, count, and its gates
# --------------------------------------------------------------------------- #


def test_len_baseline_ema_and_reaction_count_advance_on_an_inbound_valid_length() -> None:
    lf = _label_free()
    result = settle_label_free(
        _state(label_free=lf),
        _frame({_VALENCE: 0.9, _LENGTH: 0.9}, {_VALENCE, _LENGTH}),
        _outcome(tuple(0.5 for _ in range(AXIS_DIM))),
        TurnContextClass.ADDRESSED,
        None,
        True,
    )
    expected = (1.0 - formula.LEN_BASELINE_ETA) * lf.len_baseline + formula.LEN_BASELINE_ETA * 0.9
    assert result.new_label_free.len_baseline == pytest.approx(expected)
    assert result.new_label_free.reaction_count == lf.reaction_count + 1


def test_len_baseline_frozen_on_sender_mismatch_and_non_inbound_context() -> None:
    lf = _label_free()
    mismatch = settle_label_free(
        _state(label_free=lf),
        _frame({_VALENCE: 0.9, _LENGTH: 0.9}, {_VALENCE, _LENGTH}),
        _outcome(tuple(0.5 for _ in range(AXIS_DIM))),
        TurnContextClass.ADDRESSED,
        ReactionFacts(same_sender=False),
        True,
    )
    assert mismatch.new_label_free.len_baseline == lf.len_baseline
    assert mismatch.new_label_free.reaction_count == lf.reaction_count

    idle = settle_label_free(
        _state(label_free=lf),
        _frame({_VALENCE: 0.9, _LENGTH: 0.9}, {_VALENCE, _LENGTH}),
        _outcome(tuple(0.5 for _ in range(AXIS_DIM))),
        TurnContextClass.IDLE,
        None,
        True,
    )
    assert idle.new_label_free.len_baseline == lf.len_baseline
    assert idle.reaction_valid is False
    assert idle.reason == formula.REACTION_REASON_NOT_INBOUND


# --------------------------------------------------------------------------- #
# preferences() offset regression anchor (§3.2 / §4.1)
# --------------------------------------------------------------------------- #


def test_preferences_offset_none_and_zero_match_formula_v1() -> None:
    # Equal under ``==`` and, on the reachable dynamics range, byte-identical to v1
    # (a null offset returns base_c unclipped; a zero offset clips base_c+0, which is
    # a no-op except for an IEEE signed zero on a state axis unreachable in practice).
    s = decision_state(tuple(0.3 for _ in range(24)))
    base = preferences(s)
    assert preferences(s, None) == base
    assert preferences(s, tuple(0.0 for _ in range(AXIS_DIM))) == base
    # A non-zero offset shifts the mean and is clipped to [-1,1].
    shifted_c, shifted_v = preferences(s, tuple(0.2 for _ in range(AXIS_DIM)))
    base_c = base_preference_c(s)
    assert shifted_v == base[1]
    for axis in range(AXIS_DIM):
        assert shifted_c[axis] == pytest.approx(max(-1.0, min(1.0, base_c[axis] + 0.2)))


# --------------------------------------------------------------------------- #
# Orchestrator wiring: dual paths, one commit, disjoint state (§2.3 / §4.1)
# --------------------------------------------------------------------------- #


def _raw_values(overrides: dict[int, float] | None = None) -> tuple:
    values: list[float | None] = [None] * 36
    for index in range(36):
        if index in (27, 28, 29, 32, 33, 34, 35):
            values[index] = None
        else:
            values[index] = 0.5
    values[30] = 1.0
    values[31] = 120.0
    for index, value in (overrides or {}).items():
        values[index] = value
    return tuple(values)


def _profile() -> ComputeProfile:
    snn_enabled, ticks, stdp_enabled, reuse = formula.COMPUTE_PROFILES["FULL_24_STDP"]
    return ComputeProfile(
        profile_id="FULL_24_STDP",
        snn_enabled=snn_enabled,
        ticks=ticks,
        stdp_enabled=stdp_enabled,
        reuse_last_summary=reuse,
        math_backend="scalar-v1",
        formula_version=formula.FORMULA_VERSION,
        model_version=formula.FORMULA_VERSION,
    )


def _envelope(context: TurnContextClass = TurnContextClass.ADDRESSED, local_sequence: int = 11) -> TurnEnvelope:
    return TurnEnvelope(
        turn_key=TurnKey(
            plugin_instance_id="plugin",
            session_ref=_session_ref(),
            bridge_request_nonce="nonce",
            request_attempt=0,
        ),
        turn_id=f"turn-{local_sequence:04d}",
        sequence=TurnSequence(writer_epoch=7, local_sequence=local_sequence),
        compute_profile=_profile(),
        deterministic_seed=b"d" * 16,
        observation=(_raw_values({_VALENCE: 5.0}), Action.SPEAK),  # strong positive reaction
        context=context,
    )


def _unknown_pending(eligible: bool = True) -> PendingOutcome:
    return PendingOutcome(
        origin_turn_id="t-prev",
        sequence=TurnSequence(7, 10),
        action=Action.SPEAK,
        projected_actual_action=None,  # UNKNOWN -> path A cannot fire
        label_free_eligible=eligible,
    )


def _labeled_pending(latent: tuple, eligible: bool = True) -> PendingOutcome:
    frozen = freeze_actual_prediction(initial_action_beliefs(), decision_state(latent), Action.SPEAK)
    return PendingOutcome(
        origin_turn_id="t-prev",
        sequence=TurnSequence(7, 10),
        action=Action.SPEAK,
        projected_actual_action=Action.SPEAK,
        c=frozen["c"],
        v_c=frozen["v_c"],
        preference_log_terms_before=frozen["preference_log_terms_before"],
        predictive_mu_actual=frozen["predictive_mu_actual"],
        predictive_v_actual=frozen["predictive_v_actual"],
        likelihood_r_actual=frozen["likelihood_r_actual"],
        label_free_eligible=eligible,
    )


def _orch_base(pending: PendingOutcome | None, label_free: LabelFreeState | None = None) -> V3State:
    return V3State(
        session_ref=_session_ref(),
        state_generation_id="gen-a",
        revision=4,
        writer_epoch=7,
        latent_axes=tuple(0.05 for _ in range(24)),
        action_beliefs=initial_action_beliefs(),
        pending_outcome=pending,
        label_free=label_free,
    )


def test_unknown_action_turn_advances_label_free_but_never_action_beliefs() -> None:
    """The verdict main clause: this is the hole Slice C closes.

    The prior turn's action was UNKNOWN so path A cannot settle -- yet the adjacent
    eligible reaction still teaches path B.  ``action_beliefs`` must not move.
    """

    base = _orch_base(_unknown_pending(eligible=True))
    result = orchestrate(
        CoreInvocation(
            envelope=_envelope(),
            base_state=base,
            projected_actual_outcome=None,
            reaction_facts=ReactionFacts(same_sender=None),
        )
    )
    assert result.accepted is True
    next_state = result.state_delta.next_state
    # Path A never ran: no per-action learning happened this turn.
    assert next_state.action_beliefs.counts == base.action_beliefs.counts == (0, 0, 0, 0)
    # Path B ran: label_free materialized and the L2 count advanced.
    assert next_state.label_free is not None
    assert next_state.label_free.marginal_count >= 1
    assert result.trace.lf_censor_reason == formula.REACTION_REASON_VALID
    assert result.trace.reaction_valid is True


def test_labeled_and_reaction_turn_settles_both_paths_in_one_commit() -> None:
    base = _orch_base(_labeled_pending(tuple(0.05 for _ in range(24)), eligible=True))
    result = orchestrate(
        CoreInvocation(
            envelope=_envelope(),
            base_state=base,
            projected_actual_outcome=(Action.SPEAK, None),
            reaction_facts=None,
        )
    )
    assert result.accepted is True
    next_state = result.state_delta.next_state
    # Path A learned the actual action (SPEAK, index 0) exactly once.
    assert next_state.action_beliefs.counts[0] == 1
    # Path B learned the marginal head, disjointly, in the same committed state.
    assert next_state.label_free is not None
    assert next_state.label_free.marginal_count >= 1


def test_paths_write_disjoint_state_fields() -> None:
    """Path B never touches action_beliefs and path A never touches label_free."""

    latent = tuple(0.05 for _ in range(24))
    env = _envelope()

    # Path A is independent of path B's L1 eligibility gate: identical labeled pending,
    # eligible vs ineligible -> identical action_beliefs; only label_free differs.
    eligible = orchestrate(
        CoreInvocation(
            envelope=env,
            base_state=_orch_base(_labeled_pending(latent, eligible=True)),
            projected_actual_outcome=(Action.SPEAK, None),
        )
    ).state_delta.next_state
    ineligible = orchestrate(
        CoreInvocation(
            envelope=env,
            base_state=_orch_base(_labeled_pending(latent, eligible=False)),
            projected_actual_outcome=(Action.SPEAK, None),
        )
    ).state_delta.next_state
    assert eligible.action_beliefs == ineligible.action_beliefs  # path B never wrote beliefs
    assert eligible.label_free != ineligible.label_free  # eligibility gated only path B's L1

    # Path B is independent of the action label: unknown vs labeled, both eligible ->
    # identical label_free; action_beliefs differ (only path A moved).
    unknown = orchestrate(
        CoreInvocation(
            envelope=env,
            base_state=_orch_base(_unknown_pending(eligible=True)),
            projected_actual_outcome=None,
        )
    ).state_delta.next_state
    assert unknown.label_free == eligible.label_free  # path A never wrote label_free
    assert unknown.action_beliefs.counts == (0, 0, 0, 0)
    assert eligible.action_beliefs.counts[0] == 1


def test_non_adjacent_pending_censors_both_paths() -> None:
    base = _orch_base(
        _labeled_pending(tuple(0.05 for _ in range(24)), eligible=True),
        label_free=_label_free(marginal_count=7),
    )
    # The pending is (7,10); an envelope at local_sequence 20 is not adjacent.
    result = orchestrate(
        CoreInvocation(
            envelope=_envelope(local_sequence=20),
            base_state=base,
            projected_actual_outcome=(Action.SPEAK, None),
            reaction_facts=None,
        )
    )
    next_state = result.state_delta.next_state
    assert next_state.action_beliefs.counts == (0, 0, 0, 0)  # path A censored
    assert next_state.label_free.marginal_count == 7  # path B censored, count frozen
    assert result.trace.lf_censor_reason == formula.LF_CENSOR_REASON_NON_ADJACENT
    assert result.trace.reaction_valid is False


def test_ineligible_origin_withholds_l1_credit_but_l2_still_learns() -> None:
    """Spec §3.3: L2 is NOT eligibility-gated -- an ineligible origin turn still
    advances the marginal world model (the red-team's concrete repro), while the L1
    preference credit is reported as NOT_ELIGIBLE.
    """

    base = _orch_base(_unknown_pending(eligible=False), label_free=_label_free(marginal_count=3))
    result = orchestrate(
        CoreInvocation(envelope=_envelope(), base_state=base, projected_actual_outcome=None)
    )
    next_state = result.state_delta.next_state
    assert result.trace.lf_censor_reason == formula.LF_CENSOR_REASON_NOT_ELIGIBLE
    assert result.trace.reaction_valid is False
    assert next_state.label_free.marginal_count == 4  # L2 advanced despite ineligibility
    # L1 credit withheld: the offset stays at its (zero) prior.
    assert next_state.label_free.pref_offset == _label_free(marginal_count=3).pref_offset


@pytest.mark.parametrize(
    "context,expected",
    [
        (TurnContextClass.ADDRESSED, True),
        (TurnContextClass.AMBIENT, True),
        (TurnContextClass.PROACTIVE, True),
        (TurnContextClass.IDLE, False),
    ],
)
def test_label_free_eligibility_is_frozen_from_the_origin_context(context, expected) -> None:
    result = orchestrate(
        CoreInvocation(
            envelope=_envelope(context=context),
            base_state=_orch_base(None),  # no pending: this turn only creates one
            projected_actual_outcome=None,
        )
    )
    assert result.state_delta.next_state.pending_outcome.label_free_eligible is expected


def test_sender_mismatch_censors_l1_and_len_but_l2_still_learns() -> None:
    base = _orch_base(_unknown_pending(eligible=True), label_free=_label_free(marginal_count=2))
    result = orchestrate(
        CoreInvocation(
            envelope=_envelope(),
            base_state=base,
            projected_actual_outcome=None,
            reaction_facts=ReactionFacts(same_sender=False),
        )
    )
    next_state = result.state_delta.next_state
    assert result.trace.lf_censor_reason == formula.REACTION_REASON_SENDER_MISMATCH
    assert result.trace.reaction_valid is False
    assert next_state.label_free.marginal_count == 3  # L2 ignores same_sender


# --------------------------------------------------------------------------- #
# Trace: the five §4.3 label-free fields round-trip
# --------------------------------------------------------------------------- #


def test_trace_carries_label_free_fields_and_round_trips() -> None:
    assert TRACE_SCHEMA_VERSION == 2
    result = orchestrate(
        CoreInvocation(
            envelope=_envelope(),
            base_state=_orch_base(_unknown_pending(eligible=True)),
            projected_actual_outcome=None,
        )
    )
    trace = result.trace
    assert trace.schema_version == 2
    assert -1.0 <= trace.r_react <= 1.0
    assert trace.reaction_valid is True
    assert trace.lf_censor_reason in formula.LF_TRACE_CENSOR_REASONS
    assert len(trace.pref_offset_after) == AXIS_DIM
    assert len(trace.marginal_mu) == AXIS_DIM
    reparsed = decode_trace_bytes(result.trace_bytes)
    assert reparsed == trace
    assert reparsed.r_react == trace.r_react
    assert reparsed.pref_offset_after == trace.pref_offset_after
    assert reparsed.marginal_mu == trace.marginal_mu


# --------------------------------------------------------------------------- #
# ReactionFacts contract + FORMULA_DIGEST stability
# --------------------------------------------------------------------------- #


def test_reaction_facts_is_a_frozen_bool_or_none_relation() -> None:
    assert ReactionFacts().same_sender is None
    assert ReactionFacts(same_sender=True).same_sender is True
    assert ReactionFacts(same_sender=False).same_sender is False
    with pytest.raises(TypeError):
        ReactionFacts(same_sender=1)  # type: ignore[arg-type]
    facts = ReactionFacts(same_sender=True)
    with pytest.raises(Exception):
        facts.same_sender = False  # type: ignore[misc]
    # CoreInvocation carries it as an optional field defaulting to None.
    inv = CoreInvocation(envelope=_envelope(), base_state=_orch_base(None), projected_actual_outcome=None)
    assert inv.reaction_facts is None


def test_formula_digest_is_unchanged_this_slice() -> None:
    # Slice C does NOT fold the labelfree block into the manifest (deferred to D).
    assert "labelfree" not in formula.FORMULA_MANIFEST
    assert formula.FORMULA_VERSION == "sylanne.v3.formula.v1"
    assert (
        formula.FORMULA_DIGEST
        == "d3998ec2f0fa00046abfeae2a224f7703013bb2bdd893367a025e238f72d5ea4"
    )
