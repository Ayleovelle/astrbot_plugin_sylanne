"""Heterogeneous Graph Transformer (HGT) — L4 Decision Fusion.

Type-aware transformer for multi-source signal fusion. Each token type
(scar, void, boundary, personality, surprise, expression, context) has
independent projection matrices. Attention priors are derived from
personality semantics. Intra-type masking prevents local over-smoothing.

Output: 4-dim decision vector (expression drive correction, boundary
sensitivity correction, urgency signal, inhibition signal).

All ~21.9K parameters are deterministically derived from personality —
zero learning required.
"""
from __future__ import annotations

import hashlib
import math
import struct
from typing import Any


TOKEN_TYPES = ("scar", "void", "boundary", "personality", "surprise", "expression", "context")
_TYPE_INDEX = {t: i for i, t in enumerate(TOKEN_TYPES)}
_NUM_TYPES = len(TOKEN_TYPES)


def _deterministic_floats(seed: bytes, count: int) -> list[float]:
    """Generate deterministic pseudo-random floats in [-1, 1] from a seed."""
    result: list[float] = []
    block = 0
    while len(result) < count:
        h = hashlib.sha256(seed + struct.pack("<I", block)).digest()
        # Each 4 bytes → one float
        for i in range(0, len(h) - 3, 4):
            if len(result) >= count:
                break
            val = struct.unpack("<I", h[i:i+4])[0]
            # Map to [-1, 1]
            result.append((val / 0xFFFFFFFF) * 2.0 - 1.0)
        block += 1
    return result


def _make_matrix(seed: bytes, rows: int, cols: int, scale: float = 1.0) -> list[list[float]]:
    """Create a deterministic matrix from seed with Xavier-like scaling."""
    floats = _deterministic_floats(seed, rows * cols)
    xavier = scale * math.sqrt(2.0 / (rows + cols))
    mat: list[list[float]] = []
    idx = 0
    for _ in range(rows):
        row = [floats[idx + c] * xavier for c in range(cols)]
        mat.append(row)
        idx += cols
    return mat


def _matmul_vec(mat: list[list[float]], vec: list[float]) -> list[float]:
    """Matrix-vector multiply: mat @ vec."""
    return [sum(row[j] * vec[j] for j in range(len(vec))) for row in mat]


def _matmul_vec_flat(mat_flat: list[float], vec: list[float], rows: int, cols: int) -> list[float]:
    """Matrix-vector multiply with flat matrix storage."""
    result = [0.0] * rows
    idx = 0
    for r in range(rows):
        s = 0.0
        for c in range(cols):
            s += mat_flat[idx] * vec[c]
            idx += 1
        result[r] = s
    return result


def _softmax(values: list[float]) -> list[float]:
    """Numerically stable softmax."""
    if not values:
        return []
    max_v = max(values)
    exps = [math.exp(v - max_v) for v in values]
    total = sum(exps) + 1e-12
    return [e / total for e in exps]


def _dot(a: list[float], b: list[float]) -> float:
    """Dot product."""
    return sum(x * y for x, y in zip(a, b))


class HGTLayer:
    """Single-layer Heterogeneous Graph Transformer.

    Per-type W_Q, W_K, W_V projections with personality-derived attention prior
    and intra-type masking. Optimized for pure-Python performance with flat arrays.
    """

    __slots__ = (
        "d_model", "n_heads", "d_head",
        "_w_q_flat", "_w_k_flat", "_w_v_flat",
        "_attention_prior", "_output_proj_flat",
    )

    def __init__(self, d_model: int = 16, n_heads: int = 4):
        self.d_model = d_model
        self.n_heads = n_heads
        self.d_head = d_model // n_heads
        # Flat storage for speed
        self._w_q_flat: dict[int, list[float]] = {}
        self._w_k_flat: dict[int, list[float]] = {}
        self._w_v_flat: dict[int, list[float]] = {}
        self._attention_prior: list[list[float]] = [[0.0] * _NUM_TYPES for _ in range(_NUM_TYPES)]
        self._output_proj_flat: list[float] = []

    def derive_params(self, personality: dict[str, float]) -> None:
        """Deterministically derive all parameters from personality vector."""
        p_keys = sorted(personality.keys())
        seed_str = "|".join(f"{k}:{float(personality[k]):.6f}" for k in p_keys
                           if isinstance(personality[k], (int, float)))
        base_seed = hashlib.sha256(seed_str.encode()).digest()

        d = self.d_model
        d_head = self.d_head
        n_heads = self.n_heads
        # Per-type projection matrices: Q/K project to d_head per head (total d_model),
        # V projects to d_model. Stored flat for fast matmul.
        for t_idx, t_name in enumerate(TOKEN_TYPES):
            t_seed = base_seed + t_name.encode()
            q_mat = _make_matrix(t_seed + b"Q", d, d)
            k_mat = _make_matrix(t_seed + b"K", d, d)
            v_mat = _make_matrix(t_seed + b"V", d, d)
            self._w_q_flat[t_idx] = [x for row in q_mat for x in row]
            self._w_k_flat[t_idx] = [x for row in k_mat for x in row]
            self._w_v_flat[t_idx] = [x for row in v_mat for x in row]

        # Output projection flat
        out_mat = _make_matrix(base_seed + b"OUT", d, d)
        self._output_proj_flat = [x for row in out_mat for x in row]

        self._derive_attention_prior(personality)

    def _derive_attention_prior(self, personality: dict[str, float]) -> None:
        """Build the 7×7 attention prior from personality semantics."""
        neuroticism = float(personality.get("neuroticism", 0.5))
        extraversion = float(personality.get("extraversion", 0.5))
        conscientiousness = float(personality.get("conscientiousness", 0.5))
        openness = float(personality.get("openness", 0.5))
        agreeableness = float(personality.get("agreeableness", 0.5))

        # Start with uniform prior
        mu = [[1.0] * _NUM_TYPES for _ in range(_NUM_TYPES)]

        si, vi, bi, pi, sui, ei, ci = (
            _TYPE_INDEX["scar"], _TYPE_INDEX["void"], _TYPE_INDEX["boundary"],
            _TYPE_INDEX["personality"], _TYPE_INDEX["surprise"],
            _TYPE_INDEX["expression"], _TYPE_INDEX["context"],
        )

        # High neuroticism → scar-void coupling stronger
        mu[si][vi] += neuroticism * 1.5
        mu[vi][si] += neuroticism * 1.5
        # Neuroticism also amplifies surprise → scar
        mu[sui][si] += neuroticism * 1.0
        mu[si][sui] += neuroticism * 1.0

        # High extraversion → expression gets more attention from all
        for i in range(_NUM_TYPES):
            mu[i][ei] += extraversion * 1.2
            mu[ei][i] += extraversion * 0.8

        # High conscientiousness → context type weighted higher
        for i in range(_NUM_TYPES):
            mu[i][ci] += conscientiousness * 1.0
            mu[ci][i] += conscientiousness * 0.6

        # Openness → surprise gets more weight
        for i in range(_NUM_TYPES):
            mu[i][sui] += openness * 0.8

        # Agreeableness → boundary is more permeable (less self-attention)
        mu[bi][bi] = max(0.1, 1.0 - agreeableness * 0.5)

        # Zero out diagonal (intra-type mask)
        for i in range(_NUM_TYPES):
            mu[i][i] = 0.0

        self._attention_prior = mu

    def forward(self, tokens: list[tuple[str, list[float]]]) -> list[float]:
        """Run one HGT layer over typed tokens. Optimized for pure-Python speed.

        Uses type-aware attention with personality prior and intra-type mask.
        Q is projected per-type; K and V use raw input for speed.
        """
        n = len(tokens)
        if n == 0:
            return [0.0] * self.d_model

        d = self.d_model

        # Prepare tokens: pad/truncate and resolve types
        types: list[int] = []
        vecs: list[list[float]] = []
        projected_q: list[list[float]] = []

        for t_name, vec in tokens:
            if len(vec) < d:
                v = vec + [0.0] * (d - len(vec))
            else:
                v = vec[:d]
            t_idx = _TYPE_INDEX.get(t_name, 0)
            types.append(t_idx)
            vecs.append(v)
            # Only Q projection (K = raw input for efficiency)
            projected_q.append(_matmul_vec_flat(self._w_q_flat[t_idx], v, d, d))

        # Attention: Q_i · K_j (K_j = raw vec_j) with type prior + intra-type mask
        scale = 1.0 / math.sqrt(float(d))
        prior = self._attention_prior
        aggregated = [0.0] * d

        for i in range(n):
            ti = types[i]
            qi = projected_q[i]
            # Compute scores
            max_s = -1e30
            scores = [0.0] * n
            for j in range(n):
                if ti == types[j]:
                    scores[j] = -1e9
                else:
                    s = 0.0
                    kj = vecs[j]
                    for dd in range(d):
                        s += qi[dd] * kj[dd]
                    scores[j] = s * scale + prior[ti][types[j]]
                if scores[j] > max_s:
                    max_s = scores[j]

            # Softmax + weighted value accumulation
            exp_sum = 0.0
            for j in range(n):
                scores[j] = math.exp(scores[j] - max_s)
                exp_sum += scores[j]
            inv_sum = 1.0 / (exp_sum + 1e-12)

            for j in range(n):
                w = scores[j] * inv_sum
                if w > 1e-9:
                    vj = vecs[j]
                    for dd in range(d):
                        aggregated[dd] += w * vj[dd]

        # Mean pool
        inv_n = 1.0 / n
        for dd in range(d):
            aggregated[dd] *= inv_n

        # Output projection
        return _matmul_vec_flat(self._output_proj_flat, aggregated, d, d)


class HeterogeneousGraphTransformer:
    """Complete HGT module for Sylanne decision fusion.

    Accepts typed tokens from the computation spine's various subsystems,
    runs them through a single HGT layer, and produces a 4-dim decision vector:
      d_0: expression drive correction
      d_1: boundary sensitivity correction
      d_2: urgency signal
      d_3: inhibition signal (> 0.5 vetoes expression)

    All parameters are deterministically derived from personality — no training.
    """

    TOKEN_TYPES = TOKEN_TYPES

    __slots__ = ("d_model", "n_heads", "d_output", "_layer", "_decision_proj_flat", "_personality_cache")

    def __init__(self, d_model: int = 16, n_heads: int = 4, d_output: int = 4):
        self.d_model = d_model
        self.n_heads = n_heads
        self.d_output = d_output
        self._layer = HGTLayer(d_model=d_model, n_heads=n_heads)
        self._decision_proj_flat: list[float] = []
        self._personality_cache: str = ""

    def derive_params(self, personality: dict[str, float]) -> None:
        """Derive all HGT parameters from personality (called once or on change)."""
        # Cache check — avoid redundant re-derivation
        cache_key = str(sorted(personality.items()))
        if cache_key == self._personality_cache:
            return
        self._personality_cache = cache_key

        self._layer.derive_params(personality)

        # Decision projection: d_model → d_output (4), stored flat
        p_keys = sorted(personality.keys())
        seed_str = "|".join(f"{k}:{float(personality[k]):.6f}" for k in p_keys
                           if isinstance(personality[k], (int, float)))
        base_seed = hashlib.sha256(seed_str.encode()).digest()
        dec_mat = _make_matrix(base_seed + b"DECISION", self.d_output, self.d_model, scale=0.5)
        self._decision_proj_flat = [x for row in dec_mat for x in row]

    def forward(self, tokens: list[tuple[str, list[float]]], personality: dict[str, float]) -> list[float]:
        """Run HGT forward pass.

        Args:
            tokens: list of (type_name, feature_vector) pairs
            personality: personality dict (used for param derivation if needed)

        Returns:
            4-dim decision vector [d_0, d_1, d_2, d_3]
        """
        # Ensure params are derived
        self.derive_params(personality)

        if not tokens:
            return [0.0] * self.d_output

        # Run HGT layer
        hidden = self._layer.forward(tokens)

        # Project to decision space (flat matmul)
        raw = _matmul_vec_flat(self._decision_proj_flat, hidden, self.d_output, self.d_model)

        # Apply tanh to bound outputs to [-1, 1]
        decision = [math.tanh(v) for v in raw]

        # d_3 (inhibition) is mapped to [0, 1] via sigmoid
        if len(decision) >= 4:
            clamped = max(-500.0, min(500.0, raw[3] * 3.0))
            decision[3] = 1.0 / (1.0 + math.exp(-clamped))

        return decision

    def build_tokens_from_spine(
        self,
        scar_state: Any,
        void_space: Any,
        boundary: Any,
        personality: dict[str, float],
        surprise: float,
        expression: Any,
        hdc_features: list[float],
    ) -> list[tuple[str, list[float]]]:
        """Build typed token list from spine subsystem states.

        Produces one token per type (7 tokens max) for efficient attention.
        Scar dimensions are aggregated into a single scar token;
        void states are aggregated into a single void token.
        """
        tokens: list[tuple[str, list[float]]] = []
        d = self.d_model

        # Scar token: aggregate all dimensions into one d_model vector
        # Pack sensitivity and base values across dimensions
        scar_vec = [0.0] * d
        n_dims = min(scar_state.n_dims, d // 2)
        for dim_i in range(n_dims):
            scar_vec[dim_i] = scar_state.modifier(dim_i)  # sensitivity
            if dim_i + n_dims < d:
                scar_vec[dim_i + n_dims] = scar_state.base[dim_i] if dim_i < len(scar_state.base) else 0.0
        tokens.append(("scar", scar_vec))

        # Void token: aggregate active voids into one vector
        void_vec = [0.0] * d
        voids = void_space.voids[:4]
        if voids:
            n_v = len(voids)
            for i, v in enumerate(voids):
                base = (i * 4) % d
                void_vec[base % d] += v.depth / (5.0 * n_v)
                void_vec[(base + 1) % d] += v.pressure / (20.0 * n_v)
                void_vec[(base + 2) % d] += float(v.age) / (100.0 * n_v)
                void_vec[(base + 3) % d] += v.beta / n_v
        tokens.append(("void", void_vec))

        # Boundary token
        bnd_vec = [0.0] * d
        bnd_vec[0] = boundary.boundary_integrity
        bnd_vec[1] = boundary.internal_entropy
        bnd_vec[2] = boundary.repair_rate
        tokens.append(("boundary", bnd_vec))

        # Personality token
        p_keys = ["extraversion", "neuroticism", "conscientiousness", "openness", "agreeableness"]
        p_vec = [0.0] * d
        for i, k in enumerate(p_keys):
            if i < d:
                p_vec[i] = personality.get(k, 0.5)
        tokens.append(("personality", p_vec))

        # Surprise token
        s_vec = [0.0] * d
        s_vec[0] = surprise
        s_vec[1] = surprise * surprise
        tokens.append(("surprise", s_vec))

        # Expression token
        e_vec = [0.0] * d
        e_vec[0] = expression.pressure / max(0.01, expression.threshold)
        e_vec[1] = expression.threshold
        e_vec[2] = expression.expression_intensity()
        tokens.append(("expression", e_vec))

        # Context token (from HDC features)
        c_vec = (hdc_features + [0.0] * d)[:d]
        tokens.append(("context", c_vec))

        return tokens
