"""PEL-Core — Predictive-Encoding Latent core (v2.5).

A two-layer predictive-coding micro-circuit that evolves an 8-dim latent belief
``mu`` and an observed emotion read-out ``z`` (which downstream writes into
``scar_state.base``). This module is **pure Python** (``math`` + list-of-lists,
no numpy) so it can live in the lite tier, and is **fully mypy-strict typed**.

It is intentionally *standalone* at P0: nothing here couples to the rest of the
SDK yet. The maths implemented are the techspec (``v25-pel-core-techspec.md``):

* §2  — K=2 free-energy descent (``e0``, ``e1``, gradient ``g``, ``mu`` update;
        bounded read-out ``z``).
* §4  — online three-factor surprise-gated ``W_gen`` Hebbian plasticity + a
        10-iteration power-method spectral clamp to ``rho=0.9``; online
        precision updates; free energy ``F``.
* §4.3 — personality init: ``pi`` from Big-Five, ``W_gen = 0.5*I + structured
        off-diagonal`` (spectral-clamped <= 0.9), ``Pi = ones``, ``mu0 = pi``;
        plus the D-8 slow allostatic ``pi`` drift.

Boundedness & contraction are structural (techspec §3): both active states are
leaky ``tanh`` convex updates so ``mu, z in [-1, 1]^8`` is forward-invariant, and
the latent Jacobian obeys ``||J_mu||_2 <= 1 - alpha*delta`` while
``||J_z||_2 = 1 - beta`` for every admissible weight/precision/input.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

# --- dimensionality -----------------------------------------------------------
N: int = 8  # emotion / latent dimensionality (frozen dim order, see design §2)

# --- snapshot schema version (only ever incremented, never reshaped) ----------
PEL_SCHEMA_VERSION: int = 2  # v2: +pi0 (trait anchor), +theta (BCM), +s_bar (gate)

# --- working point (D-4 / D-5, techspec §1) -----------------------------------
ALPHA: float = 0.3  # latent leak / descent step mix
BETA: float = 0.4  # read-out leak mix
K: int = 2  # inner free-energy descent iterations (fixed, ignores _mlp_passes)
KAPPA: float = 0.1  # gradient step size inside tanh
PI_MAX: float = 5.0  # precision ceiling
PI_MIN: float = 0.1  # precision floor
DELTA: float = 0.05  # strict-contraction leak on the descent branch
RHO_P: float = 0.05  # online precision EMA rate
EPS: float = 1e-3  # precision update numerical floor
W_IN: float = 0.6  # input pass-through gain, W_in = diag(0.6)

# --- D-8 slow allostatic pi drift ---------------------------------------------
RHO_PI: float = 1e-3  # pi drift rate (very small, bounded; in snapshot)
Z_EMA_RATE: float = 0.05  # EMA rate for <z> feeding the pi drift

# --- plasticity & spectral clamp ----------------------------------------------
W_SPECTRAL_MAX: float = 0.9  # ||W_gen||_2 ceiling (must keep kappa*Pi_max <= 0.5)
_POWER_ITERS: int = 10  # power-iteration count for the spectral clamp

# --- 更脑 v2 (M1): divisive-normalization precision (Heeger 1992; Carandini &
# Heeger 2012). Budget-conserving competitive attention — de-saturates the dead
# flat [PI_MAX]*8 the legacy inverse-variance rule pins on the real path.
PRECISION_DIVISIVE: bool = True  # ablation knob; False => legacy inverse-variance (byte-identical)
PI_BUDGET: float = float(N)  # conserved total precision; mean target 1.0 == ones-init
_PI_GAIN: float = PI_BUDGET - N * PI_MIN  # 7.2; affine budget-share multiplier
ETA_W_DIVISIVE_GAIN: float = PI_MAX / (PI_BUDGET / N)  # 5.0; restores mean Hebbian magnitude
# NB: _PI_GAIN / ETA_W_DIVISIVE_GAIN are DERIVED at import, so PI_BUDGET / PI_MIN /
# PI_MAX are compile-time dials (monkeypatching them post-import won't propagate).
# The runtime-ablatable knobs are the booleans/scalars: PRECISION_DIVISIVE,
# LAMBDA_BCM, RHO_ANCHOR, SURPRISE_GATE (each read as a live global inside step()).

# --- 更脑 v2 (M2): BCM-inspired sliding-threshold metaplastic gain (Bienenstock+
# 1982; Abraham 2008). At LAMBDA_BCM=1 the gain m_i in [0, 2] is non-negative (no
# LTD/sign-flip); it gates the Hebbian *rate* per dim, never the descent direction.
LAMBDA_BCM: float = 1.0  # gain depth; 0.0 => exact legacy three-factor Hebbian
GAMMA_BCM: float = 0.5  # relative-surprise sensitivity inside tanh
RHO_THETA: float = 0.01  # theta EMA rate (~100-tick medium timescale)
THETA_INIT: float = 0.01  # initial sliding threshold (~ typical e0^2)
THETA_FLOOR: float = 1e-4  # ratio-denominator numerical floor

# --- 更脑 v2 (M3): anchored allostatic pi (Sterling 2012; discrete OU/AR(1) mean
# reversion). Drifts toward <z> AND restores toward the frozen trait prior pi0 —
# stops the identity erosion the legacy leak-to-<z> rule caused (~80% pi0 retained).
RHO_ANCHOR: float = 4e-3  # trait-prior restoring force; 0.0 => legacy leak-to-<z>
SURPRISE_GATE: bool = False  # optional drift gate; default OFF (surprise is flat on real path)
RHO_S: float = 0.02  # slow surprise EMA rate (only used when SURPRISE_GATE)

# --- v2.5 redesign (B): assessor as a precision-weighted TOP-DOWN semantic prior.
# The design arena's headline "root-cause fix" was: x_t echoing the assessor
# (c*a_vec+(1-c)*s*h_t) kills M1 precision, so re-point x_t=s*h_t and route the
# assessor in as a THIRD top-down error e2 = mu - a_vec (precision pi_a = c*PI_MAX,
# ON mu not through W_gen, so the Hessian only gains diag(pi_a) — contraction stays
# kappa*lambda_max(H) <= kappa*(||W||^2*PI_MAX + 2*PI_MAX) < 2).
#
# SHIPPED OFF (default False) — the fix was EMPIRICALLY REFUTED on this build (the
# falsify-or-cut red-lines both failed, measure_B.py): (1) precision did NOT revive —
# 更脑 v2's divisive M1 had already de-saturated it (pstd ~0.50), and the a_vec blend
# was actually ADDING cross-dim heterogeneity, so x_t=s*h_t made precision WORSE
# (pstd 0.50 -> 0.29); (2) routing the assessor through the e2 prior instead of the
# direct base write collapsed assessor->z[2] fidelity from d~+0.26 to d~+0.001 (~200x)
# — trading the ~10x load-bearing signal for no precision gain. So the value-blend x_t
# + direct assessor write (更脑 v2) stay the default. The e2 machinery is kept as a
# bounded, byte-identical-when-off, ablatable OPTION, not shipped. (Arena PEC/LIMBUS
# kill-shots called this exactly.)
SEMANTIC_PRIOR: bool = False  # REFUTED on this build; off => 更脑 v2 default (proven)

# Big-Five canonical keys with their legacy Embodiment-Five aliases. P0 reads
# personality robustly from whichever naming the caller supplies.
_TRAIT_ALIASES: dict[str, str] = {
    "openness": "boundary_permeability",
    "neuroticism": "perception_acuity",
    "extraversion": "expression_drive_trait",
    "agreeableness": "relational_gravity",
    "conscientiousness": "inner_order",
}


def _trait(personality: dict[str, float], name: str, default: float = 0.5) -> float:
    """Read a Big-Five trait, falling back to its legacy alias then a default."""
    if name in personality:
        return float(personality[name])
    alias = _TRAIT_ALIASES.get(name)
    if alias is not None and alias in personality:
        return float(personality[alias])
    return default


def _dot(row: list[float], vec: list[float]) -> float:
    """Plain dot product of two equal-length vectors."""
    return sum(row[i] * vec[i] for i in range(len(vec)))


def _divisive_precision(errs: list[float]) -> list[float]:
    """Budget-conserving divisive-normalization target precision (Heeger 1992).

    Each dim gets ``PI_MIN`` plus a share of a FIXED budget proportional to its
    relative reliability ``r_i = 1/(e_i^2 + EPS)``. ``sum_i target == PI_BUDGET``
    (mean ``1.0`` == the ``ones`` init), so precision is a *redistribution* of a
    fixed attention budget, not an absolute magnitude that can all-pin at
    ``PI_MAX``. Each ``target_i`` lands in ``[PI_MIN, PI_MIN + _PI_GAIN]``.
    """
    r = [1.0 / (errs[i] ** 2 + EPS) for i in range(N)]
    s = sum(r) + 1e-12
    return [PI_MIN + _PI_GAIN * (r[i] / s) for i in range(N)]


def spectral_clamp(weight: list[list[float]], rho: float = W_SPECTRAL_MAX) -> list[list[float]]:
    """Return a copy of ``weight`` scaled so its spectral norm is ``<= rho``.

    Uses the same 10-iteration power method as the legacy MLP weights
    (``scar_algebra._spectral_normalize``), replicated numpy-free. A single
    power iteration only yields a *lower* bound on sigma and could silently let
    ``||W|| > rho`` slip through and break the contraction guarantee, so the
    full 10-iteration estimate is used deliberately (techspec §4 must-fix).
    """
    rows = len(weight)
    cols = len(weight[0]) if rows > 0 else 0
    if rows == 0 or cols == 0:
        return [list(r) for r in weight]

    u = [1.0 / math.sqrt(rows)] * rows
    v = [0.0] * cols
    for _ in range(_POWER_ITERS):
        for j in range(cols):
            v[j] = sum(weight[i][j] * u[i] for i in range(rows))
        v_norm = math.sqrt(sum(x * x for x in v)) + 1e-12
        v = [x / v_norm for x in v]
        for i in range(rows):
            u[i] = sum(weight[i][j] * v[j] for j in range(cols))
        u_norm = math.sqrt(sum(x * x for x in u)) + 1e-12
        u = [x / u_norm for x in u]

    sigma = 0.0
    for i in range(rows):
        sigma += u[i] * sum(weight[i][j] * v[j] for j in range(cols))

    if sigma > rho:
        scale = rho / sigma
        return [[weight[i][j] * scale for j in range(cols)] for i in range(rows)]
    return [list(r) for r in weight]


def descent_step(
    mu: list[float],
    x_t: list[float],
    w_gen: list[list[float]],
    pi_obs: list[float],
    pi_top: list[float],
    pi: list[float],
    a_vec: list[float] | None = None,
    pi_a: list[float] | None = None,
) -> list[float]:
    """One inner free-energy descent step on the latent belief ``mu``.

    ``e0 = x_t - W_gen mu`` (bottom-up), ``e1 = mu - pi`` (top-down to the
    personality prior). The gradient of ``-F`` w.r.t. ``mu`` is
    ``g = W_genᵀ (Pi_obs ⊙ e0) - Pi_top ⊙ e1``; the update is the leaky,
    bounded convex step

        mu <- (1 - alpha) mu + alpha * tanh( (1 - delta) * (mu + kappa * g) ).

    v2.5 redesign (B): when ``a_vec``/``pi_a`` are supplied, a THIRD top-down term
    ``e2 = mu - a_vec`` (the precision-weighted assessor semantic prior) is added,
    ``g -= Pi_a ⊙ e2``. It enters ON ``mu`` (not through ``W_gen``), so the Hessian
    gains only ``diag(Pi_a)`` and the contraction bound stays
    ``kappa*lambda_max(H) <= kappa*(||W||^2*PI_MAX + 2*PI_MAX) < 2``. ``a_vec=None``
    reproduces the 更脑 v2 step byte-for-byte.

    The ``(1 - delta)`` leak on the descent branch is what makes the latent
    Jacobian uniformly strictly contractive (``||J_mu|| <= 1 - alpha*delta``)
    even at ``tanh' = 1``; see techspec §3.2. Exposed at module scope so tests
    can finite-difference the *real* recursion (including the ``kappa*H`` term).
    """
    e0 = [x_t[i] - _dot(w_gen[i], mu) for i in range(N)]
    e1 = [mu[i] - pi[i] for i in range(N)]
    pe0 = [pi_obs[i] * e0[i] for i in range(N)]
    if a_vec is not None and pi_a is not None:
        g = [
            sum(w_gen[j][i] * pe0[j] for j in range(N))
            - pi_top[i] * e1[i]
            - pi_a[i] * (mu[i] - a_vec[i])
            for i in range(N)
        ]
    else:
        g = [sum(w_gen[j][i] * pe0[j] for j in range(N)) - pi_top[i] * e1[i] for i in range(N)]
    return [
        (1.0 - ALPHA) * mu[i] + ALPHA * math.tanh((1.0 - DELTA) * (mu[i] + KAPPA * g[i]))
        for i in range(N)
    ]


def readout_step(
    z_prev: list[float], mu: list[float], x_t: list[float], w_gen: list[list[float]]
) -> list[float]:
    """Bounded emotion read-out: ``z <- (1-beta) z + beta tanh(W_gen mu + W_in x)``.

    The recursion in ``z_{t-1}`` is a pure leak (``z_hat`` depends on ``mu`` not
    ``z_{t-1}``), so ``J_z = (1 - beta) I`` with spectral norm ``1 - beta``.
    """
    z_hat = [_dot(w_gen[i], mu) for i in range(N)]
    return [(1.0 - BETA) * z_prev[i] + BETA * math.tanh(z_hat[i] + W_IN * x_t[i]) for i in range(N)]


@dataclass
class PELState:
    """Mutable plastic state of one PEL-Core (one session/host).

    All matrices are plain list-of-lists; the whole live state is < 1 KB and is
    snapshot-serialisable (P1). ``z_ema`` and the (drifting) ``pi`` participate
    in the D-8 slow allostatic update and therefore belong in the snapshot.
    """

    mu: list[float]
    z: list[float]
    w_gen: list[list[float]]
    pi_obs: list[float]
    pi_top: list[float]
    pi: list[float]
    z_ema: list[float]
    eta_w: float
    free_energy: float = 0.0
    # 更脑 v2 plastic state (defaulted so the bare boundedness-fuzz construction
    # stays valid; production paths set all three explicitly via from_personality).
    pi0: list[float] = field(default_factory=lambda: [0.0] * N)  # frozen trait-prior anchor (M3)
    theta: list[float] = field(
        default_factory=lambda: [THETA_INIT] * N
    )  # BCM sliding thresholds (M2)
    s_bar: float = 0.0  # slow surprise EMA (M3 gate only)


@dataclass
class PELCore:
    """Owns a :class:`PELState` and runs the per-tick PEL update."""

    state: PELState
    # last per-dim diagnostics (bottom-up / top-down errors), for observability.
    last_e0: list[float] = field(default_factory=lambda: [0.0] * N)
    last_e1: list[float] = field(default_factory=lambda: [0.0] * N)
    # last per-dim BCM metaplastic gain m_i (M2); recomputed each tick, NOT
    # persisted. Surfaced for the product-spread production witness (must-fix #9).
    last_m: list[float] = field(default_factory=lambda: [1.0] * N)

    # -- construction ----------------------------------------------------------
    @classmethod
    def from_personality(
        cls, personality: dict[str, float], base: list[float] | None = None
    ) -> PELCore:
        """Initialise from Big-Five traits (techspec §4.3).

        ``pi`` is the personality attractor centre; ``W_gen = 0.5*I +`` a small
        deterministic structured off-diagonal band (spectral-clamped <= 0.9);
        ``Pi_obs = Pi_top = ones``; ``mu0 = pi``; ``z0 = base`` (or zeros).
        ``eta_W = 0.002*(0.5 + openness)``.
        """
        openness = _trait(personality, "openness")
        neuroticism = _trait(personality, "neuroticism")
        extraversion = _trait(personality, "extraversion")
        agreeableness = _trait(personality, "agreeableness")
        sovereignty = _trait(personality, "sovereignty_guard", default=0.5)

        pi_raw = [
            0.30 * agreeableness - 0.20 * neuroticism,  # 0 warmth
            0.10 + 0.20 * extraversion + 0.20 * neuroticism,  # 1 arousal
            0.40 * (extraversion - neuroticism),  # 2 valence
            0.40 * neuroticism,  # 3 tension
            0.40 * openness,  # 4 curiosity
            0.20 * neuroticism,  # 5 repair_pressure
            0.30 * extraversion - 0.20 * (1.0 - agreeableness),  # 6 expression_drive
            0.50 * (1.0 - agreeableness) + 0.30 * sovereignty,  # 7 boundary_firmness
        ]
        pi = [math.tanh(v) for v in pi_raw]

        w_gen = cls._init_w_gen()
        pi_obs = [1.0] * N
        pi_top = [1.0] * N
        mu = list(pi)
        z = list(base) if base is not None else [0.0] * N
        # 更脑 v2 (M1/eta_w): divisive precision means a per-dim share of a fixed
        # budget (mean 1.0) instead of a pinned PI_MAX scalar, so the Hebbian's
        # precision gate no longer inflates the rate 5x. Restore the *designed*
        # mean magnitude by the matching gain (ETA_W_DIVISIVE_GAIN = 5.0). Pure
        # pre-clamp scale — proof-free (spectral_clamp is unconditional and last).
        eta_w_base = 0.002 * (0.5 + openness)
        eta_w = eta_w_base * (ETA_W_DIVISIVE_GAIN if PRECISION_DIVISIVE else 1.0)

        state = PELState(
            mu=mu,
            z=z,
            w_gen=w_gen,
            pi_obs=pi_obs,
            pi_top=pi_top,
            pi=pi,
            z_ema=list(z),
            eta_w=eta_w,
            pi0=list(pi),  # 更脑 v2 (M3): freeze the true trait prior as the anchor
            theta=[THETA_INIT] * N,  # 更脑 v2 (M2): BCM thresholds start at typical e0^2
        )
        return cls(state=state)

    @staticmethod
    def _init_w_gen() -> list[list[float]]:
        """``0.5*I`` plus a small deterministic structured off-diagonal band."""
        w = [[0.0] * N for _ in range(N)]
        for i in range(N):
            w[i][i] = 0.5
            w[i][(i + 1) % N] = 0.06
            w[i][(i - 1) % N] = -0.04
        return spectral_clamp(w, W_SPECTRAL_MAX)

    # -- per-tick update -------------------------------------------------------
    def step(
        self,
        x_t: list[float],
        surprise: float,
        a_vec: list[float] | None = None,
        confidence: float = 0.0,
    ) -> tuple[list[float], float]:
        """Advance one main tick: K-step latent descent, read-out, plasticity.

        Returns ``(z, F)`` where ``z`` is the new bounded emotion read-out and
        ``F`` is the (diagnostic) free energy. ``surprise`` in ``[0, 1]`` gates
        the three-factor ``W_gen`` Hebbian update.

        v2.5 redesign (B): ``a_vec`` (the assessor's affect read) + ``confidence``
        in ``[0, 1]`` add a precision-weighted top-down semantic prior to the
        descent (``pi_a = confidence * PI_MAX``). Inert when ``SEMANTIC_PRIOR`` is
        off, ``a_vec is None``, or ``confidence == 0`` — so legacy/no-read ticks
        reproduce the 更脑 v2 step exactly.
        """
        st = self.state
        if SEMANTIC_PRIOR and a_vec is not None and confidence > 0.0:
            a_prior: list[float] | None = [a_vec[i] if i < len(a_vec) else 0.0 for i in range(N)]
            pi_a: list[float] | None = [confidence * PI_MAX] * N
        else:
            a_prior = None
            pi_a = None
        mu = list(st.mu)
        for _k in range(K):
            mu = descent_step(mu, x_t, st.w_gen, st.pi_obs, st.pi_top, st.pi, a_prior, pi_a)

        z = readout_step(st.z, mu, x_t, st.w_gen)

        # final per-dim errors (used by plasticity, precisions, and F)
        e0f = [x_t[i] - _dot(st.w_gen[i], mu) for i in range(N)]
        e1f = [mu[i] - st.pi[i] for i in range(N)]

        # 更脑 v2 (M2): BCM-inspired metaplastic GAIN on the three-factor F-gradient
        # Hebbian. m_i potentiates dims whose squared error exceeds their own sliding
        # threshold theta_i and pauses those below; theta_i = EMA(e0^2) self-modifies
        # plasticity on a ~100-tick timescale. m_i in [1-LAMBDA_BCM, 1+LAMBDA_BCM] =
        # [0, 2] at default. theta_i is read BEFORE its own EMA update (the threshold
        # reflects PAST error energy). Direction stays +e0*mu (free-energy descent) —
        # M2 gates the rate only, never the sign, so no aimless Hebb is reintroduced.
        m = [1.0] * N
        for i in range(N):
            a_i = e0f[i] * e0f[i]  # PC error-unit activity^2
            g_i = math.tanh(GAMMA_BCM * (a_i - st.theta[i]) / (st.theta[i] + THETA_FLOOR))
            m_i = 1.0 + LAMBDA_BCM * g_i
            m[i] = m_i
            factor = st.eta_w * surprise * st.pi_obs[i] * e0f[i] * m_i
            row = st.w_gen[i]
            for j in range(N):
                row[j] += factor * mu[j]
            st.theta[i] = (1.0 - RHO_THETA) * st.theta[i] + RHO_THETA * a_i  # lags activity
        st.w_gen = spectral_clamp(st.w_gen, W_SPECTRAL_MAX)  # UNCHANGED, unconditional, last

        # 更脑 v2 (M1): divisive-normalization precision — competitive, budget-
        # conserving. The RHO_P EMA and the [PI_MIN, PI_MAX] clip are UNCHANGED; only
        # the per-dim *target* changes (relative budget share vs raw inverse-variance).
        # The OFF branch keeps the committed build's SINGLE-DIVISION form
        # (RHO_P / (e^2+EPS), NOT RHO_P*(1/(e^2+EPS))) so PRECISION_DIVISIVE=False is
        # bit-for-bit identical to the committed precision update — a*(1/b) vs a/b would
        # otherwise differ by <=1 ULP in IEEE-754 and slowly leak into w_gen / F.
        if PRECISION_DIVISIVE:
            tgt_obs = _divisive_precision(e0f)
            tgt_top = _divisive_precision(e1f)
            for i in range(N):
                st.pi_obs[i] = _clip(
                    (1.0 - RHO_P) * st.pi_obs[i] + RHO_P * tgt_obs[i], PI_MIN, PI_MAX
                )
                st.pi_top[i] = _clip(
                    (1.0 - RHO_P) * st.pi_top[i] + RHO_P * tgt_top[i], PI_MIN, PI_MAX
                )
        else:
            for i in range(N):
                st.pi_obs[i] = _clip(
                    (1.0 - RHO_P) * st.pi_obs[i] + RHO_P / (e0f[i] ** 2 + EPS), PI_MIN, PI_MAX
                )
                st.pi_top[i] = _clip(
                    (1.0 - RHO_P) * st.pi_top[i] + RHO_P / (e1f[i] ** 2 + EPS), PI_MIN, PI_MAX
                )

        # free energy (diagnostic / D-1 surfaceable)
        free_energy = (
            0.5 * sum(st.pi_obs[i] * e0f[i] ** 2 for i in range(N))
            + 0.5 * sum(st.pi_top[i] * e1f[i] ** 2 for i in range(N))
            - 0.5 * sum(math.log(st.pi_obs[i]) + math.log(st.pi_top[i]) for i in range(N))
        )
        if a_prior is not None and pi_a is not None:
            # v2.5 (B): the semantic-prior term the descent also minimized this tick.
            free_energy += 0.5 * sum(pi_a[i] * (mu[i] - a_prior[i]) ** 2 for i in range(N))

        # 更脑 v2 (M3): anchored allostatic pi — mean-reverts toward <z> AND back to
        # the frozen trait prior pi0 (no identity erosion). The update is a convex
        # blend (coeffs >= 0, sum 1 since drift + RHO_ANCHOR <= 1), so pi stays in
        # [-1,1]^8 forward-invariantly; the slow fixed point retains a/(d+a) ~ 80% of
        # pi0. Surprise gate default OFF (flat surprise => constant rescale = theater).
        # RHO_ANCHOR=0 reduces to the legacy leak-to-<z> rule (erosion).
        drift = RHO_PI
        if SURPRISE_GATE:
            st.s_bar = (1.0 - RHO_S) * st.s_bar + RHO_S * surprise
            drift = RHO_PI * st.s_bar
        for i in range(N):
            st.z_ema[i] = (1.0 - Z_EMA_RATE) * st.z_ema[i] + Z_EMA_RATE * z[i]
            st.pi[i] = _clip(
                st.pi[i] + drift * (st.z_ema[i] - st.pi[i]) - RHO_ANCHOR * (st.pi[i] - st.pi0[i]),
                -1.0,
                1.0,
            )

        st.mu = mu
        st.z = z
        st.free_energy = free_energy
        self.last_e0 = e0f
        self.last_e1 = e1f
        self.last_m = m  # 更脑 v2 (M2): per-dim metaplastic gain, for the product witness
        return z, free_energy

    # -- persistence -----------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """Serialise the full plastic state (snapshot-safe, additive sub-key).

        The whole live state round-trips: ``mu``/``z`` (latent + read-out),
        ``w_gen``/precisions/``pi`` (plastic params) and the D-8 drift bookkeeping
        (``z_ema``, ``eta_w``). ``v`` is the schema version for forward migration.
        """
        st = self.state
        return {
            "mu": list(st.mu),
            "z": list(st.z),
            "w_gen": [list(row) for row in st.w_gen],
            "pi_obs": list(st.pi_obs),
            "pi_top": list(st.pi_top),
            "pi": list(st.pi),
            "z_ema": list(st.z_ema),
            "eta_w": st.eta_w,
            "free_energy": st.free_energy,
            # 更脑 v2 plastic state
            "pi0": list(st.pi0),
            "theta": list(st.theta),
            "s_bar": st.s_bar,
            "v": PEL_SCHEMA_VERSION,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PELCore:
        """Reconstruct a :class:`PELCore` from :meth:`to_dict` output.

        v2 adds ``pi0``/``theta``/``s_bar`` with back-compat fallbacks so v1
        snapshots round-trip. **Migration caveat (must-fix #2):** a v1 snapshot
        has no ``pi0``, so the anchor falls back to the *current* (possibly
        already-eroded) ``pi`` — the no-washout guarantee then freezes the
        drifted identity rather than restoring the true trait prior. To recover
        the genuine ``pi0`` after migrating a long-running v1 session, the host
        should re-call :meth:`ScarredState.set_pel_priors` (which has the
        personality) on first load; the fallback only prevents a hard failure.
        """
        state = PELState(
            mu=[float(x) for x in data["mu"]],
            z=[float(x) for x in data["z"]],
            w_gen=[[float(x) for x in row] for row in data["w_gen"]],
            pi_obs=[float(x) for x in data["pi_obs"]],
            pi_top=[float(x) for x in data["pi_top"]],
            pi=[float(x) for x in data["pi"]],
            z_ema=[float(x) for x in data["z_ema"]],
            eta_w=float(data["eta_w"]),
            free_energy=float(data.get("free_energy", 0.0)),
            # 更脑 v2 back-compat: v1 dicts lack these. pi0 falls back to pi (see
            # the migration caveat above), theta to its init, s_bar to 0.
            pi0=[float(x) for x in data.get("pi0", data["pi"])],
            theta=[float(x) for x in data.get("theta", [THETA_INIT] * N)],
            s_bar=float(data.get("s_bar", 0.0)),
        )
        return cls(state=state)

    # -- observability ---------------------------------------------------------
    def diagnostics(self) -> dict[str, float]:
        """Lightweight scalar diagnostics (no contract coupling at P0)."""
        return {
            "free_energy": self.state.free_energy,
            "mean_abs_e0": sum(abs(v) for v in self.last_e0) / N,
            "mean_abs_e1": sum(abs(v) for v in self.last_e1) / N,
        }


def _clip(value: float, low: float, high: float) -> float:
    """Clamp ``value`` into ``[low, high]``."""
    if value < low:
        return low
    if value > high:
        return high
    return value
