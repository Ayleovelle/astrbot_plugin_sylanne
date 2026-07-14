"""Single immutable source for every Sylanne v3 formula-v1 constant."""

from __future__ import annotations

import hashlib
import struct
from math import inf, log, sqrt
from types import MappingProxyType

from .canonical import canonical_json_bytes


FORMULA_VERSION = "sylanne.v3.formula.v1"
OBSERVATION_DIM = 36
AXIS_DIM = 8
STATE_DIM = 24
SNN_NEURONS = 96
SNN_EXCITATORY = 77
SNN_INHIBITORY = 19
SNN_DEFAULT_TICKS = 24
SNN_ALLOWED_TICKS = (16, 24, 32)
SNN_SUMMARY_DIM = 16
WORKSPACE_CAPACITY = 8
EXPERIENCE_CAPACITY = 64

TAU_MEMBRANE = -1.0 / (24.0 * log(0.90))
TAU_PRE = -1.0 / (24.0 * log(0.90))
TAU_POST = -1.0 / (24.0 * log(0.90))
TAU_ELIGIBILITY = -1.0 / (24.0 * log(0.95))

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
Q_MATRIX = tuple(
    tuple(0.20 if column == 2 * row else 0.10 if column == 2 * row + 1 else 0.0 for column in range(16))
    for row in range(8)
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

RECURRENT_HASH_DOMAIN = b"SYL3\x01REC\x00"
INPUT_HASH_DOMAIN = b"SYL3\x01INPUT\x00"
RECURRENT_HIGH_FAN_IN_POSTS = 58
RECURRENT_HIGH_FAN_IN = 8
RECURRENT_LOW_FAN_IN = 7
RECURRENT_EE_WEIGHT = 0.06
RECURRENT_OTHER_EXCITATORY_WEIGHT = 0.08
RECURRENT_INHIBITORY_WEIGHT = -0.12
RECURRENT_FIXED_INCOMING_L1_LIMIT = 1.2
POPULATION_INPUT_COUNT = 108
INPUT_TARGETS_PER_CHANNEL = 4
INPUT_WEIGHT = 0.50


def recurrent_sources(post: int) -> tuple[int, ...]:
    """Return the formula-defined presynaptic indices for one neuron."""
    if type(post) is not int or not 0 <= post < SNN_NEURONS:
        raise ValueError("post must be a valid neuron index")
    fan_in = RECURRENT_HIGH_FAN_IN if post < RECURRENT_HIGH_FAN_IN_POSTS else RECURRENT_LOW_FAN_IN
    ranked = sorted(
        (
            hashlib.sha256(RECURRENT_HASH_DOMAIN + struct.pack(">HH", post, pre)).digest(),
            pre,
        )
        for pre in range(SNN_NEURONS)
        if pre != post
    )
    return tuple(pre for _, pre in ranked[:fan_in])


def recurrent_initial_weight(post: int, pre: int) -> float:
    """Return the Dale-compliant formula-v1 initial weight for an edge."""
    if type(post) is not int or type(pre) is not int or not 0 <= post < SNN_NEURONS or not 0 <= pre < SNN_NEURONS:
        raise ValueError("post and pre must be valid neuron indices")
    if pre >= SNN_EXCITATORY:
        return RECURRENT_INHIBITORY_WEIGHT
    if post < SNN_EXCITATORY:
        return RECURRENT_EE_WEIGHT
    return RECURRENT_OTHER_EXCITATORY_WEIGHT


def recurrent_is_plastic(post: int, pre: int) -> bool:
    return 0 <= post < SNN_EXCITATORY and 0 <= pre < SNN_EXCITATORY


def input_targets(input_index: int) -> tuple[int, ...]:
    """Return the four deterministic targets for one population input."""
    if type(input_index) is not int or not 0 <= input_index < POPULATION_INPUT_COUNT:
        raise ValueError("input_index must be in [0,108)")
    ranked = sorted(
        (
            hashlib.sha256(INPUT_HASH_DOMAIN + struct.pack(">HH", input_index, target)).digest(),
            target,
        )
        for target in range(SNN_NEURONS)
    )
    return tuple(target for _, target in ranked[:INPUT_TARGETS_PER_CHANNEL])


SNN_SUMMARY_POOLS = tuple((start, start + 6) for start in range(0, 48, 6))
SNN_SUMMARY_DEFINITION = (
    "rate[p]=clip(mean(spike_count_i/K),0,1)",
    "latency[8+p]=0 if no spike else 1-min(first_latency_i)/(K-1)",
    "missing channels emit no spikes",
)

PROPOSAL_IDS = (
    "body-speak",
    "affect-speak",
    "uncertainty-clarify",
    "boundary-hold",
    "fatigue-hold",
    "affiliation-reach",
    "snn-novelty",
    "continuity-speak",
)
PROPOSAL_ACTIONS = ("SPEAK", "SPEAK", "CLARIFY", "HOLD", "HOLD", "REACH", "CLARIFY", "SPEAK")
PROPOSAL_ACTION_BASIS = (0, 1, 2, 3)
PROPOSAL_ACTION_COORDS = (0, 0, 2, 1, 1, 3, 2, 0)
PROPOSAL_SOURCE_BASIS = tuple(range(4, 12))
PROPOSAL_GROUP_COORDS = (12, 12, 13, 14, 12, 15, 13, 15)
PROPOSAL_KEY_WEIGHTS = (1.0, 0.75, 0.50)
PROPOSAL_REQUIRED_BITS = ((11,), (), (), (17,), (10,), (), (), (26, 30))
PROPOSAL_REQUIRES_VALID_SNN_SUMMARY = (False, False, False, False, False, False, True, False)
PROPOSAL_SALIENCE_BOUNDS = (-4.0, 4.0)
PROPOSAL_CONFIDENCE_FORMULA = "clip01(0.5 + 0.25*abs(salience))"
PROPOSAL_SALIENCE_FORMULAS = (
    ("body-speak", "1.2*expression_pressure + 0.5*arousal + 0.3*center(expression_drive)"),
    ("affect-speak", "0.9*abs(valence) + 0.7*affiliation + 0.4*safety"),
    ("uncertainty-clarify", "1.4*uncertainty + 0.4*novelty"),
    ("boundary-hold", "-1.3*safety - 0.6*agency + 0.5*center(boundary_pressure)"),
    ("fatigue-hold", "1.4*center(exhaustion) - 0.4*expression_pressure"),
    ("affiliation-reach", "1.1*affiliation + 0.8*expression_pressure + 0.3*novelty"),
    ("snn-novelty", "1.2*snn_summary[10] + 0.6*novelty"),
    ("continuity-speak", "0.8*center(history_present) + 0.6*center(engagement) + 0.4*affiliation"),
)


def _proposal_key(index: int) -> tuple[float, ...]:
    raw = [0.0] * 16
    raw[PROPOSAL_ACTION_COORDS[index]] = PROPOSAL_KEY_WEIGHTS[0]
    raw[PROPOSAL_SOURCE_BASIS[index]] = PROPOSAL_KEY_WEIGHTS[1]
    raw[PROPOSAL_GROUP_COORDS[index]] = PROPOSAL_KEY_WEIGHTS[2]
    norm = sqrt(sum(value * value for value in raw))
    return tuple(value / norm for value in raw)


PROPOSAL_KEYS = tuple(_proposal_key(index) for index in range(WORKSPACE_CAPACITY))


def center(value: float) -> float:
    return 2.0 * value - 1.0


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


def validate_formula_manifest() -> float:
    """Validate dimensions, topology invariants, and the analytic Jacobian gate."""
    if len(P_MATRIX) != AXIS_DIM or any(len(row) != OBSERVATION_DIM for row in P_MATRIX):
        raise ValueError("P matrix dimensions do not match the formula")
    if len(Q_MATRIX) != AXIS_DIM or any(len(row) != SNN_SUMMARY_DIM for row in Q_MATRIX):
        raise ValueError("Q matrix dimensions do not match the formula")
    for post in range(SNN_NEURONS):
        sources = recurrent_sources(post)
        if post in sources or len(sources) != len(set(sources)):
            raise ValueError("recurrent topology contains a self-loop or duplicate")
        fixed_l1 = sum(
            abs(recurrent_initial_weight(post, pre))
            for pre in sources
            if not recurrent_is_plastic(post, pre)
        )
        if fixed_l1 > RECURRENT_FIXED_INCOMING_L1_LIMIT:
            raise ValueError("fixed incoming L1 exceeds the formula limit")
    jacobian = jacobian_absolute_upper_bound()
    norm_one = max(sum(jacobian[row][column] for row in range(STATE_DIM)) for column in range(STATE_DIM))
    norm_infinity = max(sum(row) for row in jacobian)
    bound = sqrt(norm_one * norm_infinity)
    if bound >= JACOBIAN_STABILITY_LIMIT:
        raise ValueError("formula fails the analytic Jacobian stability gate")
    return bound


_formula_manifest_data = {
    "action_belief": (
        ACTION_INITIAL_G,
        ACTION_INITIAL_V,
        ACTION_INITIAL_R,
        ACTION_INITIAL_COVARIANCE,
        ACTION_INITIAL_COUNT,
        ACTION_INITIAL_BASELINE,
        ACTION_Q_THETA,
        ACTION_REWARD_SCALE,
        ACTION_BIAS,
        ACTION_MODEL_REVISION,
    ),
    "axes": AXIS_NAMES,
    "dimensions": (
        OBSERVATION_DIM,
        AXIS_DIM,
        STATE_DIM,
        SNN_NEURONS,
        SNN_EXCITATORY,
        SNN_INHIBITORY,
        SNN_SUMMARY_DIM,
        WORKSPACE_CAPACITY,
        EXPERIENCE_CAPACITY,
    ),
    "dynamics": (
        P_TRIPLES,
        Q_MATRIX,
        W_FAST,
        W_MID,
        W_SLOW,
        U_FAST,
        U_MID,
        U_SLOW,
        DYNAMICS_STEP_SIZES,
        "rows=targets;columns=sources",
        JACOBIAN_VALIDATION_METHOD,
        JACOBIAN_STABILITY_LIMIT,
    ),
    "expression": (
        EXPRESSION_REVISION,
        HOLD_EXPRESSION,
        SPEAK_LENGTH_THRESHOLDS,
        SPEAK_PACE_FORMULA,
        SPEAK_DIRECTNESS_FORMULA,
        SPEAK_WARMTH_FORMULA,
        CLARIFY_EXPRESSION,
        CLARIFY_WARMTH_FORMULA,
        CLARIFY_HESITATION_UNCERTAINTY_THRESHOLD,
        REACH_AFFILIATION_MEDIUM_THRESHOLD,
        REACH_EXPRESSION,
        REACH_WARMTH_FORMULA,
        STYLE_SIGNATURE_RING_CAPACITY,
        STYLE_REPEAT_SUPPRESSION_LOOKBACK,
        STYLE_REPEAT_RESPONSE,
        EXPRESSION_LITERAL_OPENING_ALLOWED,
    ),
    "formula_version": FORMULA_VERSION,
    "load_shedding": (
        FULL_24_STDP,
        FULL_24_NO_STDP,
        SNN_16_NO_STDP,
        REUSE_LAST_SNN_SUMMARY,
        DETERMINISTIC_CONTINUOUS_ONLY,
        PROFILE_LADDER,
        LOAD_THRESHOLDS[:-1] + ((1.0, 500.0, "inf"),),
        RECOVERY_CONSECUTIVE_SNAPSHOTS,
        RECOVERY_THRESHOLD_RATIO,
        REPOSITORY_HARD_STOP_PROFILE,
    ),
    "proposals": (
        PROPOSAL_IDS,
        PROPOSAL_ACTIONS,
        PROPOSAL_SALIENCE_FORMULAS,
        PROPOSAL_SALIENCE_BOUNDS,
        PROPOSAL_CONFIDENCE_FORMULA,
        PROPOSAL_KEY_WEIGHTS,
        PROPOSAL_ACTION_BASIS,
        PROPOSAL_SOURCE_BASIS,
        PROPOSAL_GROUP_COORDS,
        PROPOSAL_REQUIRED_BITS,
        PROPOSAL_REQUIRES_VALID_SNN_SUMMARY,
        PROPOSAL_KEYS,
    ),
    "reward": (
        PREFERENCE_REVISION,
        OUTCOME_PROJECTOR_REVISION,
        REWARD_BRANCHES,
        WORKSPACE_EVIDENCE_FORMULA,
        RHO_HOLD_INITIAL,
        RHO_REACH_INITIAL,
        RHO_DECAY,
        RHO_PRE_SCORE_PENALTY_MULTIPLIER,
        RHO_POST_SELECTION_INCREMENT,
        RHO_BOUNDS,
        RHO_PENALTY_CONTEXTS,
        RHO_DECAY_ONLY_CONTEXTS,
    ),
    "snn_summary": (SNN_SUMMARY_POOLS, SNN_SUMMARY_DEFINITION),
    "spiking": (
        SNN_DEFAULT_TICKS,
        SNN_ALLOWED_TICKS,
        TAU_MEMBRANE,
        TAU_PRE,
        TAU_POST,
        TAU_ELIGIBILITY,
        RECURRENT_HASH_DOMAIN,
        RECURRENT_HIGH_FAN_IN_POSTS,
        RECURRENT_HIGH_FAN_IN,
        RECURRENT_LOW_FAN_IN,
        RECURRENT_EE_WEIGHT,
        RECURRENT_OTHER_EXCITATORY_WEIGHT,
        RECURRENT_INHIBITORY_WEIGHT,
        RECURRENT_FIXED_INCOMING_L1_LIMIT,
        INPUT_HASH_DOMAIN,
        POPULATION_INPUT_COUNT,
        INPUT_TARGETS_PER_CHANNEL,
        INPUT_WEIGHT,
    ),
}
FORMULA_MANIFEST = MappingProxyType(_formula_manifest_data)
FORMULA_CANONICAL_JSON = canonical_json_bytes(FORMULA_MANIFEST)
FORMULA_DIGEST = hashlib.sha256(FORMULA_CANONICAL_JSON).hexdigest()
del _formula_manifest_data
