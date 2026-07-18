"""Single immutable source for every Sylanne v3 formula-v1 constant."""

from __future__ import annotations

import hashlib
from math import inf, isfinite, sqrt
from types import MappingProxyType

from .canonical import canonical_json_bytes


FORMULA_VERSION = "sylanne.v3.formula.v2"
OBSERVATION_DIM = 36
AXIS_DIM = 8
STATE_DIM = 24
# formula v2 deleted the SNN cognitive subsystem (reservoir, STDP, snn-novelty
# proposal, Q coupling).  Two dimensions survive purely as *telemetry layout*
# constants: ``SNN_NEURONS`` sizes the (now always-neutral) per-neuron spike
# arrays the trace still records, and ``SNN_SUMMARY_DIM`` sizes the vestigial
# ``last_snn_summary`` reuse slot the load-shedding profile plumbing still reads.
# Neither drives cognition any longer; see the deletion note further below.
SNN_NEURONS = 96
SNN_SUMMARY_DIM = 16
WORKSPACE_CAPACITY = 8
EXPERIENCE_CAPACITY = 64

AXIS_NAMES = (
    "valence",
    "arousal",
    "safety",
    "affiliation",
    "uncertainty",
    "novelty",
    "agency",
    "expression_pressure",
)

P_TRIPLES = (
    (0, 25, 0.55),
    (0, 0, 0.45),
    (1, 23, 0.35),
    (1, 21, 0.35),
    (1, 4, 0.30),
    (2, 1, -0.40),
    (2, 2, -0.35),
    (2, 17, -0.25),
    (3, 0, 0.35),
    (3, 19, 0.35),
    (3, 20, -0.25),
    (3, 26, 0.20),
    (4, 22, 0.30),
    (4, 4, 0.35),
    (4, 6, -0.35),
    (5, 4, 0.70),
    (5, 5, -0.30),
    (6, 9, 0.70),
    (6, 17, -0.30),
    (7, 11, 0.50),
    (7, 14, 0.30),
    (7, 10, -0.20),
)


def _sparse_matrix(
    row_count: int,
    column_count: int,
    triples: tuple[tuple[int, int, float], ...],
) -> tuple[tuple[float, ...], ...]:
    matrix = [[0.0 for _ in range(column_count)] for _ in range(row_count)]
    for row, column, value in triples:
        matrix[row][column] = value
    return tuple(tuple(row) for row in matrix)


P_MATRIX = _sparse_matrix(AXIS_DIM, OBSERVATION_DIM, P_TRIPLES)
SEMANTIC_DEFAULTS = (
    0.5,
    0.0,
    0.0,
    0.5,
    0.0,
    0.5,
    0.5,
    0.0,
    0.0,
    1.0,
    0.0,
    0.5,
    0.5,
    0.0,
    0.0,
    0.0,
    0.5,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.5,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
)
CENTER_SCALE = 2.0
CENTER_OFFSET = -1.0
P_BIAS = tuple(
    -sum(weight * SEMANTIC_DEFAULTS[column] for column, weight in enumerate(row))
    for row in P_MATRIX
)
SELF_DIAGONALS = (0.30, 0.35, 0.36)
OFF_DIAGONAL_COUPLINGS = (
    (0, 2, 0.06),
    (0, 3, 0.06),
    (1, 4, 0.06),
    (4, 2, -0.06),
    (6, 3, 0.05),
    (7, 6, 0.05),
)
OFF_DIAGONAL_SCALES = (1.0, 5.0 / 6.0, 0.5)
U_DIAGONALS = (0.80, 0.75, 0.65)
DYNAMICS_STEP_SIZES = (0.50, 0.12, 0.02)

# Design section 11.2 versioned decision-state blend: the eight-dimensional
# decision state read by downstream inference is
# ``s = clip(0.50*fast + 0.30*mid + 0.20*slow, -1, 1)``.  It is kept here as the
# single source of truth (used by ``features.decision_state``) but is *not*
# folded into ``build_formula_manifest`` so ``FORMULA_DIGEST`` remains stable;
# the inference task (section 11) that owns this blend may add it to the manifest
# with an intentional digest bump.
DECISION_STATE_BLEND = (0.50, 0.30, 0.20)


def _self_matrix(diagonal: float, off_diagonal_scale: float) -> tuple[tuple[float, ...], ...]:
    triples = tuple(
        [(index, index, diagonal) for index in range(AXIS_DIM)]
        + [(target, source, value * off_diagonal_scale) for target, source, value in OFF_DIAGONAL_COUPLINGS]
    )
    return _sparse_matrix(AXIS_DIM, AXIS_DIM, triples)


def _diagonal_matrix(diagonal: float) -> tuple[tuple[float, ...], ...]:
    return tuple(
        tuple(diagonal if row == column else 0.0 for column in range(AXIS_DIM))
        for row in range(AXIS_DIM)
    )


W_FAST = _self_matrix(SELF_DIAGONALS[0], OFF_DIAGONAL_SCALES[0])
W_MID = _self_matrix(SELF_DIAGONALS[1], OFF_DIAGONAL_SCALES[1])
W_SLOW = _self_matrix(SELF_DIAGONALS[2], OFF_DIAGONAL_SCALES[2])
U_FAST = _diagonal_matrix(U_DIAGONALS[0])
U_MID = _diagonal_matrix(U_DIAGONALS[1])
U_SLOW = _diagonal_matrix(U_DIAGONALS[2])

# --------------------------------------------------------------------------- #
# SNN cognitive subsystem — DELETED in formula v2 (behaviour change, not a
# no-op).  The spiking reservoir was structurally incapable of firing through
# ``orchestrate`` (max membrane ~0.32 vs a 0.65 threshold floor), so ``snn_summary``
# was permanently zero and ``Q_MATRIX @ summary`` was inert.  But the summary had a
# SECOND consumer: the ``snn-novelty`` proposal was gated on ``snn_summary is not
# None`` (not on whether anything spiked) and carried live ``0.6*novelty`` salience,
# so it was a real workspace competitor whose key collided with uncertainty-clarify.
# Removing it shifts the action distribution (measured JS ~0.021, CLARIFY +~16.7pp).
# This deletion removed: the reservoir topology + LIF/STDP/coding constants, the four
# ``TAU_*`` time constants, ``Q_MATRIX``, the ``snn-novelty`` proposal, ``SnnState``
# and its codec segment, and the ``spiking/`` package.  Only the per-action reward
# baseline constants below survive, because ``ActionBeliefs.baselines`` (an inference
# belief field, not SNN state) still evolves.
# --------------------------------------------------------------------------- #

# Per-action reward baseline EMA (formerly design 8.3): bounded exponential mean
# ``clip(0.95*baseline + 0.05*reward, -1, 1)`` stored on ``ActionBeliefs``.
BASELINE_DECAY = 0.95
BASELINE_LEARN = 0.05
BASELINE_BOUNDS = (-1.0, 1.0)

# formula v2 deleted the ``snn-novelty`` proposal (old index 6).  The survivors
# are NOT renumbered in key space: their ``(ACTION_COORDS, SOURCE_BASIS,
# GROUP_COORDS)`` key triples are byte-identical to formula v1, so every survivor's
# 16-dimensional key is unchanged.  In particular ``continuity-speak`` keeps source
# basis 11 (not shifted down to 10), and key coordinate 10 — the slot snn-novelty
# occupied — is now a PERMANENT TOMBSTONE that no proposal uses.  ``PROPOSAL_SOURCE_BASIS``
# is therefore written explicitly as (4,5,6,7,8,9,11), skipping 10, rather than as a
# contiguous range.
PROPOSAL_IDS = (
    "body-speak",
    "affect-speak",
    "uncertainty-clarify",
    "boundary-hold",
    "fatigue-hold",
    "affiliation-reach",
    "continuity-speak",
)
PROPOSAL_COUNT = len(PROPOSAL_IDS)
PROPOSAL_ACTIONS = ("SPEAK", "SPEAK", "CLARIFY", "HOLD", "HOLD", "REACH", "SPEAK")
PROPOSAL_ACTION_BASIS = (0, 1, 2, 3)
PROPOSAL_ACTION_COORDS = (0, 0, 2, 1, 1, 3, 0)
PROPOSAL_SOURCE_BASIS = (4, 5, 6, 7, 8, 9, 11)  # 10 is the snn-novelty tombstone
PROPOSAL_GROUP_COORDS = (12, 12, 13, 14, 12, 15, 15)
PROPOSAL_KEY_WEIGHTS = (1.0, 0.75, 0.50)
PROPOSAL_REQUIRED_BITS = ((11,), (), (), (17,), (10,), (), (26, 30))
PROPOSAL_SALIENCE_BOUNDS = (-4.0, 4.0)
PROPOSAL_CONFIDENCE_FORMULA = "clip01(0.5 + 0.25*abs(salience))"
PROPOSAL_SALIENCE_FORMULAS = (
    ("body-speak", "1.2*expression_pressure + 0.5*arousal + 0.3*center(expression_drive)"),
    ("affect-speak", "0.9*abs(valence) + 0.7*affiliation + 0.4*safety"),
    ("uncertainty-clarify", "1.4*uncertainty + 0.4*novelty"),
    ("boundary-hold", "-1.3*safety - 0.6*agency + 0.5*center(boundary_pressure)"),
    ("fatigue-hold", "1.4*center(exhaustion) - 0.4*expression_pressure"),
    ("affiliation-reach", "1.1*affiliation + 0.8*expression_pressure + 0.3*novelty"),
    ("continuity-speak", "0.8*center(history_present) + 0.6*center(engagement) + 0.4*affiliation"),
)


def _proposal_key(index: int) -> tuple[float, ...]:
    raw = [0.0] * 16
    raw[PROPOSAL_ACTION_COORDS[index]] = PROPOSAL_KEY_WEIGHTS[0]
    raw[PROPOSAL_SOURCE_BASIS[index]] = PROPOSAL_KEY_WEIGHTS[1]
    raw[PROPOSAL_GROUP_COORDS[index]] = PROPOSAL_KEY_WEIGHTS[2]
    norm = sqrt(sum(value * value for value in raw))
    return tuple(value / norm for value in raw)


PROPOSAL_KEYS = tuple(_proposal_key(index) for index in range(PROPOSAL_COUNT))


def center(value: float) -> float:
    return CENTER_SCALE * value + CENTER_OFFSET


EXPRESSION_REVISION = FORMULA_VERSION
HOLD_EXPRESSION = (0, 0.0, 0.50, 0.50, False)
SPEAK_LENGTH_THRESHOLDS = (-0.25, 0.45)
SPEAK_PACE_FORMULA = "clip01(0.50+0.20*arousal-0.20*center(exhaustion))"
SPEAK_DIRECTNESS_FORMULA = "clip01(0.50+0.25*agency-0.20*uncertainty)"
SPEAK_WARMTH_FORMULA = "clip01(0.50+0.25*affiliation+0.15*valence)"
CLARIFY_EXPRESSION = ("SHORT", 0.45, 0.75)
CLARIFY_WARMTH_FORMULA = "clip01(0.50+0.20*affiliation)"
CLARIFY_HESITATION_UNCERTAINTY_THRESHOLD = 0.55
REACH_AFFILIATION_MEDIUM_THRESHOLD = 0.60
REACH_EXPRESSION = ("SHORT_OR_MEDIUM", 0.40, 0.45)
REACH_WARMTH_FORMULA = "clip01(0.70+0.20*affiliation)"
STYLE_SIGNATURE_RING_CAPACITY = 4
STYLE_REPEAT_SUPPRESSION_LOOKBACK = 2
STYLE_REPEAT_RESPONSE = ("hesitation=false", "length=one_bucket_shorter")
EXPRESSION_LITERAL_OPENING_ALLOWED = False

ACTION_INITIAL_G = 0.85
ACTION_INITIAL_V = 0.25
ACTION_INITIAL_R = 0.20
ACTION_INITIAL_COVARIANCE = (0.10, 0.10)
ACTION_INITIAL_COUNT = 0
ACTION_INITIAL_BASELINE = 0.0
ACTION_Q_THETA = 1e-4
ACTION_REWARD_SCALE = 1.0
ACTION_BIAS = (
    ("SPEAK", (0.05, 0.05, 0.05, 0.08, -0.05, 0.05, 0.03, 0.08)),
    ("HOLD", (0.00, -0.05, 0.08, 0.00, -0.05, -0.05, 0.05, -0.08)),
    ("CLARIFY", (0.00, 0.00, 0.05, 0.02, -0.12, 0.02, 0.02, -0.02)),
    ("REACH", (0.05, 0.05, 0.03, 0.12, -0.03, 0.08, 0.02, 0.10)),
)
PREFERENCE_REVISION = FORMULA_VERSION
OUTCOME_PROJECTOR_REVISION = FORMULA_VERSION
ACTION_MODEL_REVISION = FORMULA_VERSION
REWARD_BRANCHES = (
    "no valid outcome dimension -> censored",
    "invalid quality_score -> r_preference",
    "otherwise clip(0.70*r_preference+0.30*(2*quality_score-1),-1,1)",
)
WORKSPACE_EVIDENCE_FORMULA = "clip(2*(support_a-mean_legal_support),-2,2)"
RHO_HOLD_INITIAL = 0.0
RHO_REACH_INITIAL = 0.0
RHO_DECAY = 0.80
RHO_PRE_SCORE_PENALTY_MULTIPLIER = 2.0
RHO_POST_SELECTION_INCREMENT = 0.35
RHO_BOUNDS = (0.0, 1.0)
RHO_PENALTY_CONTEXTS = ("PROACTIVE", "IDLE")
RHO_DECAY_ONLY_CONTEXTS = ("ADDRESSED", "AMBIENT")
CONTEXT_ACTION_PRIORS = MappingProxyType(
    {
        "ADDRESSED": MappingProxyType({"SPEAK": 0.55, "CLARIFY": 0.25, "HOLD": 0.20}),
        "AMBIENT": MappingProxyType({"HOLD": 0.75, "SPEAK": 0.25}),
        "PROACTIVE": MappingProxyType({"HOLD": 0.80, "REACH": 0.20}),
        "IDLE": MappingProxyType({"HOLD": 1.0}),
    }
)
ACTION_TIE_ORDER = ("HOLD", "CLARIFY", "SPEAK", "REACH")

# --------------------------------------------------------------------------- #
# Section 10 workspace competition, section 11.2/11.3 active-inference, section
# 11.2 preferences, the EKF box/variance bounds, and the section 12 expression
# formula coefficients.
#
# Exactly like ``DECISION_STATE_BLEND`` above, these are the single formula-v1
# source for the Task 9 cognitive modules and are
# never hard-coded elsewhere.  They are intentionally *not* folded into
# ``build_formula_manifest`` so ``FORMULA_DIGEST`` stays byte-stable at the value
# locked by Task 1's golden test; the owning evaluation task may fold them into
# the manifest later with an intentional digest bump when the gate manifest is
# frozen.  The workspace competition potential initialises to ``0.0`` and the
# ambiguous branch credits ``support[CLARIFY]`` with the runner-up broadcast
# activation (both fixed here as the single formula-v1 interpretation).
# --------------------------------------------------------------------------- #

# Section 10 competition.
WORKSPACE_ITERATIONS = 4
WORKSPACE_POTENTIAL_INITIAL = 0.0
WORKSPACE_POTENTIAL_LEAK = 0.4
WORKSPACE_POTENTIAL_GAIN = 0.6
WORKSPACE_INHIBITION_WEIGHT = 0.60
WORKSPACE_REFRACTORY_WEIGHT = 0.45
WORKSPACE_POTENTIAL_CLIP = 8.0
WORKSPACE_SOFTMAX_TEMPERATURE = 0.35
WORKSPACE_TOP1_ACTIVATION = 0.45
WORKSPACE_TOP1_MARGIN = 0.08
SOURCE_REFRACTORY_DECAY = 0.72
SOURCE_REFRACTORY_INCREMENT = 0.45

# Section 11.2 preferences p_C(s') = Normal(c, diag(V_C)).  Axes 0 (valence) and
# 3 (affiliation) copy the current decision state; every other axis is fixed.
PREFERENCE_C_CONSTANT = (0.0, 0.0, 0.6, 0.0, 0.0, 0.0, 0.4, 0.0)
PREFERENCE_C_STATE_AXES = (0, 3)
PREFERENCE_V_C = (0.50, 0.25, 0.20, 0.50, 0.20, 0.50, 0.25, 0.25)

# Section 11.2 decision-state blend already lives in DECISION_STATE_BLEND above.
# Section 11.3 EFE / policy posterior.
POLICY_GAMMA = 1.0
POLICY_TEMPERATURE = 1.0
POLICY_WORKSPACE_EVIDENCE_BOUNDS = (-2.0, 2.0)
POLICY_REFRACTORY_PENALTY_BOUNDS = (0.0, 2.0)

# Section 11.2 EKF box-projection and variance bounds.
ACTION_G_BOUNDS = (0.5, 1.2)
ACTION_B_BOUNDS = (-0.5, 0.5)
ACTION_V_BOUNDS = (0.02, 1.0)
ACTION_R_BOUNDS = (0.02, 1.0)
ACTION_SIGMA_BOUNDS = (1e-4, 1.0)
ACTION_ETA_COUNT_CAP = 64
ACTION_ETA_OFFSET = 4
ACTION_COUNT_CAP = 65535

# Section 12 expression formula coefficients (base, per-input weights).  The
# HOLD/CLARIFY/REACH pace and directness scalars already live in
# HOLD_EXPRESSION / CLARIFY_EXPRESSION / REACH_EXPRESSION above.
SPEAK_PACE_COEFFS = (0.50, 0.20, -0.20)  # base, arousal, center(exhaustion)
SPEAK_DIRECTNESS_COEFFS = (0.50, 0.25, -0.20)  # base, agency, uncertainty
SPEAK_WARMTH_COEFFS = (0.50, 0.25, 0.15)  # base, affiliation, valence
CLARIFY_WARMTH_COEFFS = (0.50, 0.20)  # base, affiliation
REACH_WARMTH_COEFFS = (0.70, 0.20)  # base, affiliation
EXPRESSION_LENGTH_BUCKETS = ("NONE", "SHORT", "MEDIUM", "LONG")

# --------------------------------------------------------------------------- #
# formula v2 label-free reaction learning channel (design
# 2026-07-18-v3core-formula-v2-label-free-reaction-learning-spec).
#
# The user's t+1 message is the real causal consequence of turn t's *executed*
# interaction, so its tone / engagement / length / latency features score how the
# user reacted WITHOUT knowing which action the core chose.  Slice A shipped the
# constants below plus the ``ReactionSignalV1`` pure function in
# ``learning.reaction``.
#
# DIGEST FOLD (Slice D, spec §4.3): the ``labelfree`` block IS now folded into
# ``build_formula_manifest`` (see ``build_labelfree_manifest`` -> the ``labelfree``
# key), so ``FORMULA_DIGEST`` intentionally changed and ``FORMULA_VERSION`` is now
# ``"sylanne.v3.formula.v2"``.  The connected revision aliases
# (``PREFERENCE_REVISION`` / ``OUTCOME_PROJECTOR_REVISION`` / ``ACTION_MODEL_REVISION``
# / ``EXPRESSION_REVISION``, all ``= FORMULA_VERSION``) follow the bump.  The bump is
# coupled to the isolated v2 evaluation dataset + ``neutral_eval_v2`` regeneration
# (Slice D); the episode seed already frames ``formula_digest``, so the v2 dataset is
# naturally isolated from any v1 dataset.
# --------------------------------------------------------------------------- #

# §1.2 reaction-signal synthesis constants.
REACT_W_VALENCE = 0.5
REACT_W_ENGAGEMENT = 0.3
REACT_W_LENGTH = 0.2
REACT_LEN_GAIN = 3.0
REACT_GAP_ATTEN_LO = 0.62  # normalized u31 (_log_gap) space; ~330 s (~5.5 min): full weight
REACT_GAP_ATTEN_HI = 0.78  # ~4270 s (~71 min): weight clears and the reaction is censored
REACT_WARMUP_COUNT = 5  # valid length samples required before the length term counts
LF_REACTION_CONTEXTS = ("ADDRESSED", "AMBIENT")  # t+1 must be a real inbound message
LF_ELIGIBLE_ORIGIN_CONTEXTS = ("ADDRESSED", "AMBIENT", "PROACTIVE")  # t-turn eligibility

# Closed reaction-reason vocabulary (also the trace ``lf_censor_reason`` domain).
REACTION_REASON_VALID = "VALID"
REACTION_REASON_NOT_INBOUND = "NOT_INBOUND"
REACTION_REASON_SENDER_MISMATCH = "SENDER_MISMATCH"
REACTION_REASON_NO_TONE_EVIDENCE = "NO_TONE_EVIDENCE"
REACTION_REASON_STALE_REACTION = "STALE_REACTION"
REACTION_INVALID_REASONS = (
    REACTION_REASON_NOT_INBOUND,
    REACTION_REASON_SENDER_MISMATCH,
    REACTION_REASON_NO_TONE_EVIDENCE,
    REACTION_REASON_STALE_REACTION,
)
REACTION_REASONS = (REACTION_REASON_VALID,) + REACTION_INVALID_REASONS

# Orchestration-level label-free settlement reasons (spec §2.4): the trace's
# ``lf_censor_reason`` domain is the reaction reasons PLUS these two, which record
# why the免标签 path B did not run at all -- non-adjacent (or no pending), mirroring
# path A's adjacency censoring, and adjacent-but-not-eligible.  They are NOT folded
# into ``build_formula_manifest`` (like every other Slice A/C label-free constant),
# so ``FORMULA_DIGEST`` stays byte-stable until Slice D's intentional bump.
LF_CENSOR_REASON_NON_ADJACENT = "NON_ADJACENT"
LF_CENSOR_REASON_NOT_ELIGIBLE = "NOT_ELIGIBLE"
LF_TRACE_CENSOR_REASONS = REACTION_REASONS + (
    LF_CENSOR_REASON_NON_ADJACENT,
    LF_CENSOR_REASON_NOT_ELIGIBLE,
)
REACTION_SIGNAL_FORMULA = (
    "r_raw = sum(w_i*t_i)/sum(w_i) over present terms; "
    "t_valence=2*u25-1 (w=REACT_W_VALENCE), t_engagement=2*u26-1 (w=REACT_W_ENGAGEMENT), "
    "t_length=clip(REACT_LEN_GAIN*(u18-len_baseline),-1,1) (w=REACT_W_LENGTH, warmup-gated); "
    "a_gap=1 if u31 invalid else 1-clip((u31-LO)/(HI-LO),0,1); "
    "r_react=clip(r_raw,-1,1)*a_gap; "
    "INVALID: NOT_INBOUND -> SENDER_MISMATCH -> NO_TONE_EVIDENCE -> STALE_REACTION"
)

# §3.1 label-free learner state constants (consumed by Slices B/C; centralized
# here per spec §4.3).  Bounds that persist through the codec's float16 grid are
# widened at the storage boundary by ``state.models.quantization_safe_bounds``.
PREF_OFFSET_BOUNDS = (-0.30, 0.30)
PREF_ETA = 0.05
LEN_BASELINE_ETA = 0.10
LEN_BASELINE_INIT = 0.60
MARGINAL_INITIAL_G = ACTION_INITIAL_G  # 0.85, reuse the per-action EKF value
MARGINAL_INITIAL_B = 0.0
MARGINAL_INITIAL_V = ACTION_INITIAL_V  # 0.25
MARGINAL_INITIAL_R = ACTION_INITIAL_R  # 0.20
MARGINAL_SIGMA_INIT = (0.10, 0.10)
MARGINAL_Q_THETA = ACTION_Q_THETA  # 1e-4
# Marginal-head box/variance bounds reuse the per-action EKF bounds verbatim
# (spec §3.1/§3.3): ACTION_G_BOUNDS / ACTION_B_BOUNDS / ACTION_SIGMA_BOUNDS.
LABELFREE_UPDATE_LAWS = (
    (
        "L1_preference_offset",
        "target=clip(y'-base_c,-0.30,0.30) if r_react>=0 else 0.0; "
        "eta=PREF_ETA*|r_react|; off'=(1-eta)*off+eta*target; off in PREF_OFFSET_BOUNDS",
    ),
    (
        "L2_marginal_outcome",
        "mu_m=tanh(gm*s+bm); diagonal EKF update reusing ekf_transition_update math "
        "with MARGINAL_* priors; adjacency-gated, action-unconditioned",
    ),
    (
        "len_baseline",
        "len_baseline'=clip((1-LEN_BASELINE_ETA)*len_baseline+LEN_BASELINE_ETA*u18,0,1); "
        "reaction_count'=min(reaction_count+1,65535); gated on inbound+bit18+same_sender!=False",
    ),
)

FULL_24_STDP = (True, 24, True, False)
FULL_24_NO_STDP = (True, 24, False, False)
SNN_16_NO_STDP = (True, 16, False, False)
REUSE_LAST_SNN_SUMMARY = (False, 0, False, True)
DETERMINISTIC_CONTINUOUS_ONLY = (False, 0, False, False)
PROFILE_LADDER = (
    "FULL_24_STDP",
    "FULL_24_NO_STDP",
    "SNN_16_NO_STDP",
    "REUSE_LAST_SNN_SUMMARY",
    "DETERMINISTIC_CONTINUOUS_ONLY",
    "SKIP_V3_TURN",
)
LOAD_THRESHOLDS = (
    (0.25, 25.0, 2.5),
    (0.50, 50.0, 3.5),
    (0.70, 100.0, 5.0),
    (0.85, 200.0, 8.0),
    (1.0, 500.0, inf),
)
RECOVERY_CONSECUTIVE_SNAPSHOTS = 32
RECOVERY_THRESHOLD_RATIO = 0.80
REPOSITORY_HARD_STOP_PROFILE = "SKIP_V3_TURN"
COMPUTE_PROFILE_FIELDS = ("snn_enabled", "ticks", "stdp_enabled", "reuse_last_summary")
COMPUTE_PROFILES = MappingProxyType(
    {
        "FULL_24_STDP": FULL_24_STDP,
        "FULL_24_NO_STDP": FULL_24_NO_STDP,
        "SNN_16_NO_STDP": SNN_16_NO_STDP,
        "REUSE_LAST_SNN_SUMMARY": REUSE_LAST_SNN_SUMMARY,
        "DETERMINISTIC_CONTINUOUS_ONLY": DETERMINISTIC_CONTINUOUS_ONLY,
    }
)
REUSE_LAST_SUMMARY_FALLBACK = "DETERMINISTIC_CONTINUOUS_ONLY"
JACOBIAN_VALIDATION_METHOD = "abs-block-sqrt-l1-linf"
JACOBIAN_STABILITY_LIMIT = 0.995


def jacobian_absolute_upper_bound() -> tuple[tuple[float, ...], ...]:
    """Build the complete entrywise absolute 24x24 triangular Jacobian bound."""

    def self_block(
        matrix: tuple[tuple[float, ...], ...],
        alpha: float,
    ) -> tuple[tuple[float, ...], ...]:
        return tuple(
            tuple(
                (1.0 - alpha if target == source else 0.0) + alpha * abs(matrix[target][source])
                for source in range(AXIS_DIM)
            )
            for target in range(AXIS_DIM)
        )

    def feedforward_block(
        matrix: tuple[tuple[float, ...], ...],
        alpha: float,
    ) -> tuple[tuple[float, ...], ...]:
        return tuple(tuple(alpha * abs(value) for value in row) for row in matrix)

    def multiply(
        left: tuple[tuple[float, ...], ...],
        right: tuple[tuple[float, ...], ...],
    ) -> tuple[tuple[float, ...], ...]:
        return tuple(
            tuple(
                sum(left[target][item] * right[item][source] for item in range(AXIS_DIM))
                for source in range(AXIS_DIM)
            )
            for target in range(AXIS_DIM)
        )

    block_a = self_block(W_FAST, DYNAMICS_STEP_SIZES[0])
    block_b = self_block(W_MID, DYNAMICS_STEP_SIZES[1])
    block_f = self_block(W_SLOW, DYNAMICS_STEP_SIZES[2])
    mid_coupling = feedforward_block(U_MID, DYNAMICS_STEP_SIZES[1])
    slow_coupling = feedforward_block(U_SLOW, DYNAMICS_STEP_SIZES[2])
    block_c = multiply(mid_coupling, block_a)
    block_d = multiply(slow_coupling, block_b)
    block_e = multiply(slow_coupling, block_c)
    zero = tuple((0.0,) * AXIS_DIM for _ in range(AXIS_DIM))
    return tuple(
        [block_a[row] + zero[row] + zero[row] for row in range(AXIS_DIM)]
        + [block_c[row] + block_b[row] + zero[row] for row in range(AXIS_DIM)]
        + [block_e[row] + block_d[row] + block_f[row] for row in range(AXIS_DIM)]
    )


JACOBIAN_ABSOLUTE_UPPER_BOUND = jacobian_absolute_upper_bound()
_jacobian_norm_one = max(
    sum(JACOBIAN_ABSOLUTE_UPPER_BOUND[row][column] for row in range(STATE_DIM))
    for column in range(STATE_DIM)
)
_jacobian_norm_infinity = max(sum(row) for row in JACOBIAN_ABSOLUTE_UPPER_BOUND)
JACOBIAN_STABILITY_BOUND = sqrt(_jacobian_norm_one * _jacobian_norm_infinity)
del _jacobian_norm_one, _jacobian_norm_infinity


def _is_finite_number(value: object) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def _validate_matrix_shape_and_values(
    name: str,
    matrix: tuple[tuple[float, ...], ...],
    row_count: int,
    column_count: int,
) -> None:
    if type(matrix) is not tuple or len(matrix) != row_count:
        raise ValueError(f"{name} dimensions do not match the formula")
    for row in matrix:
        if type(row) is not tuple or len(row) != column_count:
            raise ValueError(f"{name} dimensions do not match the formula")
        if any(not _is_finite_number(value) for value in row):
            raise ValueError(f"{name} must contain only finite numeric values")


def _validate_labelfree() -> None:
    """Fail-closed sanity checks for the formula-v2 label-free constants (§1.2/§3.1).

    These are validated by the global gate even though they are not folded into
    ``FORMULA_DIGEST`` yet, so a malformed reaction constant can never reach the
    ``ReactionSignalV1`` pure function or the Slice C learners.
    """

    weights = (REACT_W_VALENCE, REACT_W_ENGAGEMENT, REACT_W_LENGTH)
    if any(not _is_finite_number(weight) or weight <= 0.0 for weight in weights):
        raise ValueError("label-free reaction weights must be positive finite values")
    if not _is_finite_number(REACT_LEN_GAIN) or REACT_LEN_GAIN <= 0.0:
        raise ValueError("REACT_LEN_GAIN must be a positive finite value")
    if not (
        _is_finite_number(REACT_GAP_ATTEN_LO)
        and _is_finite_number(REACT_GAP_ATTEN_HI)
        and 0.0 <= REACT_GAP_ATTEN_LO < REACT_GAP_ATTEN_HI <= 1.0
    ):
        raise ValueError("gap attenuator thresholds must satisfy 0 <= LO < HI <= 1")
    if type(REACT_WARMUP_COUNT) is not int or REACT_WARMUP_COUNT < 1:
        raise ValueError("REACT_WARMUP_COUNT must be a positive integer")

    declared_contexts = frozenset(("ADDRESSED", "AMBIENT", "PROACTIVE", "IDLE"))
    reaction_contexts = frozenset(LF_REACTION_CONTEXTS)
    eligible_contexts = frozenset(LF_ELIGIBLE_ORIGIN_CONTEXTS)
    if not reaction_contexts <= declared_contexts or not eligible_contexts <= declared_contexts:
        raise ValueError("label-free contexts must name declared TurnContextClass values")
    if not reaction_contexts <= eligible_contexts:
        raise ValueError("every reaction context must itself be an eligible origin context")
    if "IDLE" in eligible_contexts:
        raise ValueError("IDLE turns have no reaction-eligible interaction")

    offset_low, offset_high = PREF_OFFSET_BOUNDS
    if not (offset_low < 0.0 < offset_high) or offset_low != -offset_high:
        raise ValueError("PREF_OFFSET_BOUNDS must be a symmetric interval about 0")
    for name, eta in (("PREF_ETA", PREF_ETA), ("LEN_BASELINE_ETA", LEN_BASELINE_ETA)):
        if not _is_finite_number(eta) or not 0.0 < eta < 1.0:
            raise ValueError(f"{name} must be a learning rate in (0,1)")
    if not _is_finite_number(LEN_BASELINE_INIT) or not 0.0 <= LEN_BASELINE_INIT <= 1.0:
        raise ValueError("LEN_BASELINE_INIT must be a normalized value in [0,1]")


def validate_formula_manifest() -> float:
    """Validate dimensions, topology invariants, and the analytic Jacobian gate."""
    if (OBSERVATION_DIM, AXIS_DIM, STATE_DIM) != (36, 8, 24) or STATE_DIM != 3 * AXIS_DIM:
        raise ValueError("continuous-state dimensions do not match formula v1")
    if type(SEMANTIC_DEFAULTS) is not tuple or len(SEMANTIC_DEFAULTS) != OBSERVATION_DIM:
        raise ValueError("semantic defaults do not match the observation dimension")
    if any(not _is_finite_number(value) for value in SEMANTIC_DEFAULTS):
        raise ValueError("semantic defaults must contain only finite numeric values")

    _validate_matrix_shape_and_values("P matrix", P_MATRIX, AXIS_DIM, OBSERVATION_DIM)
    for name, matrix in (
        ("W_FAST", W_FAST),
        ("W_MID", W_MID),
        ("W_SLOW", W_SLOW),
        ("U_FAST", U_FAST),
        ("U_MID", U_MID),
        ("U_SLOW", U_SLOW),
    ):
        _validate_matrix_shape_and_values(name, matrix, AXIS_DIM, AXIS_DIM)
    if (
        type(DYNAMICS_STEP_SIZES) is not tuple
        or len(DYNAMICS_STEP_SIZES) != 3
        or any(
            not _is_finite_number(step_size) or not 0.0 < step_size <= 1.0
            for step_size in DYNAMICS_STEP_SIZES
        )
    ):
        raise ValueError("dynamics step sizes must be three finite values in (0,1]")
    _validate_matrix_shape_and_values(
        "materialized Jacobian",
        JACOBIAN_ABSOLUTE_UPPER_BOUND,
        STATE_DIM,
        STATE_DIM,
    )

    expected_bias = tuple(
        -sum(weight * SEMANTIC_DEFAULTS[column] for column, weight in enumerate(row))
        for row in P_MATRIX
    )
    if (
        type(P_BIAS) is not tuple
        or len(P_BIAS) != AXIS_DIM
        or any(not _is_finite_number(value) for value in P_BIAS)
        or P_BIAS != expected_bias
    ):
        raise ValueError("P_BIAS does not cancel the semantic-default projection")

    expected_context_actions = {
        "ADDRESSED": ("SPEAK", "CLARIFY", "HOLD"),
        "AMBIENT": ("HOLD", "SPEAK"),
        "PROACTIVE": ("HOLD", "REACH"),
        "IDLE": ("HOLD",),
    }
    try:
        context_names = tuple(CONTEXT_ACTION_PRIORS.keys())
    except (AttributeError, TypeError) as exc:
        raise ValueError("context priors must be a mapping") from exc
    if frozenset(context_names) != frozenset(expected_context_actions):
        raise ValueError("context priors do not define the exact formula contexts")
    for context, expected_actions in expected_context_actions.items():
        prior = CONTEXT_ACTION_PRIORS[context]
        try:
            actions = tuple(prior.keys())
            probabilities = tuple(prior[action] for action in actions)
        except (AttributeError, KeyError, TypeError) as exc:
            raise ValueError(f"context prior for {context} must be a mapping") from exc
        if frozenset(actions) != frozenset(expected_actions):
            raise ValueError(f"context prior for {context} has illegal actions")
        if any(not _is_finite_number(probability) or probability <= 0.0 for probability in probabilities):
            raise ValueError(f"context prior for {context} must contain positive finite probabilities")
        if abs(sum(probabilities) - 1.0) > 1e-12:
            raise ValueError(f"context prior for {context} must sum to one")
    if ACTION_TIE_ORDER != ("HOLD", "CLARIFY", "SPEAK", "REACH"):
        raise ValueError("context action tie order does not match formula v1")

    try:
        jacobian = jacobian_absolute_upper_bound()
    except Exception as exc:
        raise ValueError("Jacobian construction failed") from exc
    _validate_matrix_shape_and_values("Jacobian", jacobian, STATE_DIM, STATE_DIM)
    if jacobian != JACOBIAN_ABSOLUTE_UPPER_BOUND:
        raise ValueError("materialized Jacobian differs from the live formula")
    norm_one = max(sum(jacobian[row][column] for row in range(STATE_DIM)) for column in range(STATE_DIM))
    norm_infinity = max(sum(row) for row in jacobian)
    bound = sqrt(norm_one * norm_infinity)
    if not _is_finite_number(JACOBIAN_STABILITY_BOUND) or bound != JACOBIAN_STABILITY_BOUND:
        raise ValueError("Jacobian bound does not match the materialized bound")
    if JACOBIAN_STABILITY_LIMIT != 0.995 or bound >= JACOBIAN_STABILITY_LIMIT:
        raise ValueError("formula fails the analytic Jacobian stability gate")
    _validate_labelfree()
    return bound


def _named_mapping(**values: object) -> MappingProxyType[str, object]:
    return MappingProxyType(values)


def build_formula_manifest() -> MappingProxyType[str, object]:
    """Build a fresh, recursively read-only manifest from live formula semantics."""
    return _named_mapping(
        formula_version=FORMULA_VERSION,
        dimensions=_named_mapping(
            observation=OBSERVATION_DIM,
            axes=AXIS_DIM,
            state=STATE_DIM,
            workspace=WORKSPACE_CAPACITY,
            experience=EXPERIENCE_CAPACITY,
        ),
        observation=_named_mapping(
            dimension=OBSERVATION_DIM,
            semantic_defaults=SEMANTIC_DEFAULTS,
            center_scale=CENTER_SCALE,
            center_offset=CENTER_OFFSET,
        ),
        axes=AXIS_NAMES,
        dynamics=_named_mapping(
            matrix_orientation="rows=targets;columns=sources",
            p_triples=P_TRIPLES,
            p_matrix=P_MATRIX,
            p_bias=P_BIAS,
            w_fast=W_FAST,
            w_mid=W_MID,
            w_slow=W_SLOW,
            u_fast=U_FAST,
            u_mid=U_MID,
            u_slow=U_SLOW,
            step_sizes=DYNAMICS_STEP_SIZES,
        ),
        proposals=_named_mapping(
            ids=PROPOSAL_IDS,
            actions=PROPOSAL_ACTIONS,
            salience_formulas=PROPOSAL_SALIENCE_FORMULAS,
            salience_bounds=PROPOSAL_SALIENCE_BOUNDS,
            confidence_formula=PROPOSAL_CONFIDENCE_FORMULA,
            key_weights=PROPOSAL_KEY_WEIGHTS,
            action_basis=PROPOSAL_ACTION_BASIS,
            source_basis=PROPOSAL_SOURCE_BASIS,
            group_coords=PROPOSAL_GROUP_COORDS,
            required_bits=PROPOSAL_REQUIRED_BITS,
            materialized_keys=PROPOSAL_KEYS,
        ),
        action_selection=_named_mapping(
            context_priors=CONTEXT_ACTION_PRIORS,
            tie_order=ACTION_TIE_ORDER,
        ),
        expression=_named_mapping(
            revision=EXPRESSION_REVISION,
            hold=HOLD_EXPRESSION,
            speak_length_thresholds=SPEAK_LENGTH_THRESHOLDS,
            speak_pace_formula=SPEAK_PACE_FORMULA,
            speak_directness_formula=SPEAK_DIRECTNESS_FORMULA,
            speak_warmth_formula=SPEAK_WARMTH_FORMULA,
            clarify=CLARIFY_EXPRESSION,
            clarify_warmth_formula=CLARIFY_WARMTH_FORMULA,
            clarify_hesitation_uncertainty_threshold=CLARIFY_HESITATION_UNCERTAINTY_THRESHOLD,
            clarify_hesitation_semantics=(
                "hesitation is true iff action is CLARIFY and uncertainty >= threshold"
            ),
            reach_affiliation_medium_threshold=REACH_AFFILIATION_MEDIUM_THRESHOLD,
            reach=REACH_EXPRESSION,
            reach_warmth_formula=REACH_WARMTH_FORMULA,
            style_signature_ring_capacity=STYLE_SIGNATURE_RING_CAPACITY,
            style_repeat_suppression_lookback=STYLE_REPEAT_SUPPRESSION_LOOKBACK,
            style_repeat_response=STYLE_REPEAT_RESPONSE,
            literal_opening_allowed=EXPRESSION_LITERAL_OPENING_ALLOWED,
        ),
        action_belief=_named_mapping(
            initial_g=ACTION_INITIAL_G,
            initial_v=ACTION_INITIAL_V,
            initial_r=ACTION_INITIAL_R,
            initial_covariance=ACTION_INITIAL_COVARIANCE,
            initial_count=ACTION_INITIAL_COUNT,
            initial_baseline=ACTION_INITIAL_BASELINE,
            q_theta=ACTION_Q_THETA,
            reward_scale=ACTION_REWARD_SCALE,
            action_bias=ACTION_BIAS,
            model_revision=ACTION_MODEL_REVISION,
        ),
        reward=_named_mapping(
            preference_revision=PREFERENCE_REVISION,
            outcome_projector_revision=OUTCOME_PROJECTOR_REVISION,
            branches=REWARD_BRANCHES,
            workspace_evidence_formula=WORKSPACE_EVIDENCE_FORMULA,
            rho_hold_initial=RHO_HOLD_INITIAL,
            rho_reach_initial=RHO_REACH_INITIAL,
            rho_decay=RHO_DECAY,
            rho_pre_score_penalty_multiplier=RHO_PRE_SCORE_PENALTY_MULTIPLIER,
            rho_post_selection_increment=RHO_POST_SELECTION_INCREMENT,
            rho_bounds=RHO_BOUNDS,
            rho_penalty_contexts=RHO_PENALTY_CONTEXTS,
            rho_decay_only_contexts=RHO_DECAY_ONLY_CONTEXTS,
        ),
        load_shedding=_named_mapping(
            profile_fields=COMPUTE_PROFILE_FIELDS,
            profiles=COMPUTE_PROFILES,
            profile_ladder=PROFILE_LADDER,
            reuse_last_summary_fallback=REUSE_LAST_SUMMARY_FALLBACK,
            load_thresholds=LOAD_THRESHOLDS[:-1] + ((1.0, 500.0, "inf"),),
            recovery_consecutive_snapshots=RECOVERY_CONSECUTIVE_SNAPSHOTS,
            recovery_threshold_ratio=RECOVERY_THRESHOLD_RATIO,
            repository_hard_stop_profile=REPOSITORY_HARD_STOP_PROFILE,
        ),
        validation=_named_mapping(
            jacobian_method=JACOBIAN_VALIDATION_METHOD,
            jacobian_stability_limit=JACOBIAN_STABILITY_LIMIT,
            jacobian_absolute_upper_bound=JACOBIAN_ABSOLUTE_UPPER_BOUND,
            jacobian_stability_bound=JACOBIAN_STABILITY_BOUND,
        ),
        # formula v2 (spec §4.3): the label-free reaction-learning block is folded
        # into the digested manifest (Slice D).  This is the intentional v2 digest
        # bump; the section-1.2 reaction constants and the L1/L2 learner priors +
        # update laws are now part of ``FORMULA_DIGEST``.
        labelfree=build_labelfree_manifest(),
    )


def build_labelfree_manifest() -> MappingProxyType[str, object]:
    """Build the recursively read-only formula-v2 ``labelfree`` manifest block.

    Authored now (Slice A) but deliberately NOT folded into
    ``build_formula_manifest`` so ``FORMULA_DIGEST`` stays byte-stable; Slice C/D
    fold this verbatim with the intentional v2 digest bump (spec §4.3).
    """

    return _named_mapping(
        reaction=_named_mapping(
            w_valence=REACT_W_VALENCE,
            w_engagement=REACT_W_ENGAGEMENT,
            w_length=REACT_W_LENGTH,
            len_gain=REACT_LEN_GAIN,
            gap_atten_lo=REACT_GAP_ATTEN_LO,
            gap_atten_hi=REACT_GAP_ATTEN_HI,
            warmup_count=REACT_WARMUP_COUNT,
            reaction_contexts=LF_REACTION_CONTEXTS,
            eligible_origin_contexts=LF_ELIGIBLE_ORIGIN_CONTEXTS,
            invalid_reasons=REACTION_INVALID_REASONS,
            formula=REACTION_SIGNAL_FORMULA,
        ),
        learners=_named_mapping(
            pref_offset_bounds=PREF_OFFSET_BOUNDS,
            pref_eta=PREF_ETA,
            len_baseline_eta=LEN_BASELINE_ETA,
            len_baseline_init=LEN_BASELINE_INIT,
            marginal_initial_g=MARGINAL_INITIAL_G,
            marginal_initial_b=MARGINAL_INITIAL_B,
            marginal_initial_v=MARGINAL_INITIAL_V,
            marginal_initial_r=MARGINAL_INITIAL_R,
            marginal_sigma_init=MARGINAL_SIGMA_INIT,
            marginal_q_theta=MARGINAL_Q_THETA,
            update_laws=LABELFREE_UPDATE_LAWS,
        ),
    )


FORMULA_MANIFEST = build_formula_manifest()
FORMULA_CANONICAL_JSON = canonical_json_bytes(FORMULA_MANIFEST)
FORMULA_DIGEST = hashlib.sha256(FORMULA_CANONICAL_JSON).hexdigest()
LABELFREE_MANIFEST = build_labelfree_manifest()
