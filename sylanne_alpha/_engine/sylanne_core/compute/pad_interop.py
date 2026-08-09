"""Sylanne-Embodiment 计算核心层：PAD 互操作层（PAD Interop Layer）。

提供 Sylanne 内部 N 维情感状态与标准 PAD（Pleasure-Arousal-Dominance）
三维空间之间的双向映射。

理论基础：
  PAD 是保留分类情感区分的最低维空间（Mehrabian & Russell 1974）。
  三因子解释了情感语义差异评分中 68% 的方差。
  Russell 环形模型（1980）表明 P 和 A 分离大多数基本情感；
  Dominance 添加了区分恐惧与愤怒所需的能动性轴。
  Fontaine et al.（2007）发现第四因子（不可预测性）仅增加约 7% 方差——
  不足以为互操作目的增加复杂性。

设计决策：
  - 前向映射（Internal → PAD）：线性投影 pad = W @ x + b
  - 逆映射（PAD → Internal）：Moore-Penrose 伪逆（最小范数解）
  - W 矩阵由人格 SHA-256 确定性派生（与 HGT 权重初始化一致）
  - 默认 W 基于 Russell & Mehrabian（1977）和 Watson & Tellegen（1985）的因子载荷
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# PAD Vector dataclass
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PADVector:
    """标准 PAD 三维情感向量。

    Attributes:
        valence: 愉悦度，范围 [-1, 1]。Mehrabian & Russell 1974。
        arousal: 唤醒度，范围 [0, 1]。Russell 1980 circumplex model。
        dominance: 支配度，范围 [0, 1]。Mehrabian 1996 PAD temperament model。
    """

    valence: float  # [-1, 1] — Pleasure axis (Mehrabian & Russell 1974)
    arousal: float  # [0, 1] — Arousal axis (Russell 1980)
    dominance: float  # [0, 1] — Dominance axis (Mehrabian 1996)

    def __post_init__(self) -> None:
        self.valence = max(-1.0, min(1.0, self.valence))
        self.arousal = max(0.0, min(1.0, self.arousal))
        self.dominance = max(0.0, min(1.0, self.dominance))

    def to_list(self) -> list[float]:
        return [self.valence, self.arousal, self.dominance]

    def to_dict(self) -> dict[str, float]:
        return {"valence": self.valence, "arousal": self.arousal, "dominance": self.dominance}


# ---------------------------------------------------------------------------
# Categorical emotion regions in PAD space
# Based on Russell & Mehrabian 1977 factor analysis of 151 emotion terms
# ---------------------------------------------------------------------------

CATEGORICAL_REGIONS: dict[str, dict[str, tuple[float, float]]] = {
    # "joy": high pleasure, moderate arousal, high dominance
    # Russell & Mehrabian 1977 Table 2: happiness cluster
    "joy": {
        "valence": (0.3, 1.0),
        "arousal": (0.3, 0.7),
        "dominance": (0.4, 1.0),
    },
    # "anger": negative valence, high arousal, high dominance
    # Mehrabian 1997: anger = -P +A +D
    "anger": {
        "valence": (-1.0, -0.2),
        "arousal": (0.6, 1.0),
        "dominance": (0.6, 1.0),
    },
    # "sadness": negative valence, low arousal, low dominance
    # Russell & Mehrabian 1977: sadness = -P -A -D
    "sadness": {
        "valence": (-1.0, -0.2),
        "arousal": (0.0, 0.4),
        "dominance": (0.0, 0.4),
    },
    # "fear": negative valence, high arousal, low dominance
    # Mehrabian 1997: fear = -P +A -D (distinguishes from anger by D)
    "fear": {
        "valence": (-1.0, -0.2),
        "arousal": (0.5, 1.0),
        "dominance": (0.0, 0.4),
    },
    # "surprise": valence-neutral, very high arousal
    # Fontaine et al. 2007: surprise loads primarily on arousal
    "surprise": {
        "valence": (-1.0, 1.0),
        "arousal": (0.7, 1.0),
        "dominance": (0.0, 1.0),
    },
    # "disgust": strong negative valence, moderate arousal, moderate-high dominance
    # Mehrabian 1997: disgust = -P, moderate A, +D (rejection with agency)
    "disgust": {
        "valence": (-1.0, -0.4),
        "arousal": (0.3, 0.6),
        "dominance": (0.4, 1.0),
    },
    # "neutral": near-zero valence, moderate arousal
    # Baseline state per Russell 1980 circumplex origin
    "neutral": {
        "valence": (-0.2, 0.2),
        "arousal": (0.3, 0.5),
        "dominance": (0.0, 1.0),
    },
}


# ---------------------------------------------------------------------------
# Default projection matrix W (N=8, lite mode)
# Derived from factor loadings in Russell & Mehrabian 1977 and Watson & Tellegen 1985.
# Columns: [joy, sadness, anger, fear, surprise, disgust, trust, anticipation]
# These correspond to Sylanne's 8 lite emotion dimensions.
# ---------------------------------------------------------------------------

# Row 0: Valence (Pleasure) loadings — Russell & Mehrabian 1977 Table 3
_W_VALENCE_8 = [0.85, -0.80, -0.55, -0.65, 0.20, -0.70, 0.60, 0.30]
# Row 1: Arousal loadings — Watson & Tellegen 1985 two-factor model
_W_AROUSAL_8 = [0.35, -0.30, 0.75, 0.80, 0.85, 0.40, 0.10, 0.65]
# Row 2: Dominance loadings — Mehrabian 1996 PAD temperament scales
_W_DOMINANCE_8 = [0.45, -0.50, 0.60, -0.70, 0.10, -0.20, 0.55, 0.35]

_W_DEFAULT_8: list[list[float]] = [_W_VALENCE_8, _W_AROUSAL_8, _W_DOMINANCE_8]


# ---------------------------------------------------------------------------
# Deterministic weight generation (same approach as HGT _deterministic_floats)
# ---------------------------------------------------------------------------


def _deterministic_floats(seed: bytes, count: int) -> list[float]:
    """Generate deterministic [-1, 1] floats from seed (SHA-256 based)."""
    result: list[float] = []
    block = 0
    while len(result) < count:
        h = hashlib.sha256(seed + struct.pack("<I", block)).digest()
        for i in range(0, len(h) - 3, 4):
            if len(result) >= count:
                break
            val = struct.unpack("<I", h[i : i + 4])[0]
            result.append((val / 0xFFFFFFFF) * 2.0 - 1.0)
        block += 1
    return result


# ---------------------------------------------------------------------------
# Matrix utilities (pure Python, no numpy required)
# ---------------------------------------------------------------------------


def _matmul_3xN(w: list[list[float]], vec: list[float]) -> list[float]:
    """Multiply 3xN matrix by N-vector, return 3-vector."""
    result = [0.0, 0.0, 0.0]
    for row in range(3):
        s = 0.0
        w_row = w[row]
        for col in range(len(w_row)):
            if col < len(vec):
                s += w_row[col] * vec[col]
        result[row] = s
    return result


def _transpose(w: list[list[float]]) -> list[list[float]]:
    """Transpose a 3xN matrix to NxN_cols (N rows, 3 cols)."""
    if not w or not w[0]:
        return []
    n_cols = len(w[0])
    return [[w[row][col] for row in range(3)] for col in range(n_cols)]


def _mat3x3_mul_vec(m: list[list[float]], v: list[float]) -> list[float]:
    """Multiply 3x3 matrix by 3-vector."""
    return [
        m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
        m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
        m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2],
    ]


def _mat3x3_inverse(m: list[list[float]]) -> list[list[float]]:
    """Invert a 3x3 matrix using Cramer's rule."""
    a, b, c = m[0][0], m[0][1], m[0][2]
    d, e, f = m[1][0], m[1][1], m[1][2]
    g, h, i = m[2][0], m[2][1], m[2][2]

    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-12:
        # Singular matrix fallback: return identity
        return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]

    inv_det = 1.0 / det
    return [
        [
            (e * i - f * h) * inv_det,
            (c * h - b * i) * inv_det,
            (b * f - c * e) * inv_det,
        ],
        [
            (f * g - d * i) * inv_det,
            (a * i - c * g) * inv_det,
            (c * d - a * f) * inv_det,
        ],
        [
            (d * h - e * g) * inv_det,
            (b * g - a * h) * inv_det,
            (a * e - b * d) * inv_det,
        ],
    ]


def _wwt(w: list[list[float]]) -> list[list[float]]:
    """Compute W @ W^T (3x3 result from 3xN matrix)."""
    n = len(w[0]) if w else 0
    result = [[0.0] * 3 for _ in range(3)]
    for i in range(3):
        for j in range(3):
            s = 0.0
            for k in range(n):
                s += w[i][k] * w[j][k]
            result[i][j] = s
    return result


# ---------------------------------------------------------------------------
# PADProjector class
# ---------------------------------------------------------------------------


class PADProjector:
    """PAD 投影器：内部 N 维情感状态与 PAD 三维空间的双向映射。

    前向映射：pad = W @ state（线性投影，然后 clamp 到有效范围）
    逆映射：state = W^T @ (W @ W^T)^{-1} @ (pad - b)（Moore-Penrose 伪逆）

    W 矩阵由人格 SHA-256 确定性派生，默认值基于维度情感理论的因子载荷。
    """

    __slots__ = ("n_dims", "_w", "_b", "_personality_hash")

    def __init__(self, n_dims: int, personality: dict[str, float] | None = None):
        """初始化 PAD 投影器。

        Args:
            n_dims: 内部情感状态维度数（8/16/32）。
            personality: 可选人格参数字典，用于调制投影矩阵。
        """
        self.n_dims = n_dims
        self._w: list[list[float]] = []
        self._b: list[float] = [0.0, 0.0, 0.0]  # Tonic mood offset (Mehrabian 1996)
        self._personality_hash: str = ""
        self._build_projection_matrix(personality)

    def _build_projection_matrix(
        self, personality: dict[str, float] | None = None
    ) -> list[list[float]]:
        """构建 3xN 投影矩阵 W。

        对于 N=8，使用基于文献的默认因子载荷。
        对于 N>8，扩展维度使用接近零的权重（信息在互操作边界有意丢失）。
        人格参数通过确定性哈希调制权重。

        Returns:
            3xN 投影矩阵。
        """
        n = self.n_dims

        if personality:
            p_hash = hashlib.sha256(
                "|".join(
                    f"{k}:{float(v):.6f}"
                    for k, v in sorted(personality.items())
                    if isinstance(v, (int, float))
                ).encode()
            ).hexdigest()
        else:
            p_hash = ""

        self._personality_hash = p_hash

        # Start with default 8-dim loadings
        if n <= 8:
            w = [row[:n] for row in _W_DEFAULT_8]
        else:
            # Extend: first 8 dims use literature values,
            # remaining dims get near-zero weights (intentional information loss
            # at interchange boundary — Fontaine et al. 2007 4th factor < 7% variance)
            seed = b"PAD_EXTEND_" + (p_hash.encode() if p_hash else b"default")
            extra_count = (n - 8) * 3
            extra_floats = _deterministic_floats(seed, extra_count)
            # Scale extra dims to ~0.05 (negligible contribution)
            # This reflects that fine-grained dimensions collapse under projection
            scale = 0.05  # Near-zero: fine-grained dims are interchange-irrelevant
            w = []
            for row_idx in range(3):
                base_row = list(_W_DEFAULT_8[row_idx])
                offset = row_idx * (n - 8)
                extension = [extra_floats[offset + i] * scale for i in range(n - 8)]
                w.append(base_row + extension)

        # Personality modulation of W (if personality provided)
        if personality:
            self._apply_personality_modulation(w, personality)

        self._w = w
        return w

    def _apply_personality_modulation(
        self, w: list[list[float]], personality: dict[str, float]
    ) -> None:
        """Apply personality-driven modulation to projection matrix.

        Based on:
        - Watson & Clark 1997: extraversion shifts arousal baseline up
        - Rusting & Larsen 1997: neuroticism shifts valence baseline down
        - McCrae & Costa 1997: openness widens projection spread
        """
        ext = float(personality.get("extraversion", personality.get("expression_drive_trait", 0.5)))
        neu = float(personality.get("neuroticism", personality.get("perception_acuity", 0.5)))
        opn = float(personality.get("openness", personality.get("boundary_permeability", 0.5)))

        # Watson & Clark 1997: extraversion → tonic arousal elevation
        self._b[1] = (ext - 0.5) * 0.15  # Arousal bias shift

        # Rusting & Larsen 1997: neuroticism → negative valence bias
        self._b[0] = -(neu - 0.5) * 0.12  # Valence bias shift

        # McCrae & Costa 1997: openness → wider spread (scale W rows)
        spread_factor = 0.9 + opn * 0.2  # Range [0.9, 1.1]
        n = len(w[0]) if w else 0
        for row in range(3):
            for col in range(n):
                w[row][col] *= spread_factor

        # Personality-seeded perturbation for individual differences
        # (deterministic from personality hash — same personality = same W)
        if self._personality_hash:
            seed = bytes.fromhex(self._personality_hash)
            perturbations = _deterministic_floats(seed + b"PAD_PERTURB", 3 * n)
            perturb_scale = 0.03  # Small perturbation preserving factor structure
            for row in range(3):
                for col in range(n):
                    w[row][col] += perturbations[row * n + col] * perturb_scale

    def project(self, internal_state: list[float]) -> PADVector:
        """前向映射：内部 N 维状态 → PAD 三维向量。

        Implements: pad = W @ state + b, then clamp to valid ranges.

        Args:
            internal_state: N 维内部情感状态向量。

        Returns:
            PADVector，值已 clamp 到有效范围。
        """
        raw = _matmul_3xN(self._w, internal_state)
        # Add tonic mood bias (Mehrabian 1996 PAD temperament model)
        raw[0] += self._b[0]
        raw[1] += self._b[1]
        raw[2] += self._b[2]

        # Clamp to valid PAD ranges
        valence = max(-1.0, min(1.0, raw[0]))
        # Arousal: map from raw [-inf, inf] to [0, 1] via shifted sigmoid
        # Literature convention: arousal is unipolar (Russell 1980)
        arousal = max(0.0, min(1.0, (raw[1] + 1.0) / 2.0))
        # Dominance: similarly unipolar (Mehrabian 1996)
        dominance = max(0.0, min(1.0, (raw[2] + 1.0) / 2.0))

        return PADVector(valence=valence, arousal=arousal, dominance=dominance)

    def inverse(self, pad: PADVector) -> list[float]:
        """逆映射：PAD 三维向量 → 内部 N 维状态（最小范数解）。

        Uses Moore-Penrose pseudoinverse (Penrose 1955):
            state = W^T @ (W @ W^T)^{-1} @ (pad - b)

        This yields the minimum-norm internal state consistent with the given
        PAD coordinates. Properties:
          - Unique for any given W
          - Minimizes ||state||_2 among all solutions
          - Round-trip: project(inverse(pad)) ≈ pad (exact up to clamping)
          - Information loss: fine-grained dimensions default to zero

        Args:
            pad: PAD 三维向量。

        Returns:
            N 维内部状态向量（最小范数解）。
        """
        # Convert PAD back to raw projection space (undo the [0,1] mapping)
        raw_pad = [
            pad.valence - self._b[0],
            pad.arousal * 2.0 - 1.0 - self._b[1],  # Undo (raw+1)/2 mapping
            pad.dominance * 2.0 - 1.0 - self._b[2],  # Undo (raw+1)/2 mapping
        ]

        # Compute pseudoinverse: W^T @ (W @ W^T)^{-1}
        # Step 1: W @ W^T (3x3)
        gram = _wwt(self._w)
        # Step 2: (W @ W^T)^{-1} (3x3)
        gram_inv = _mat3x3_inverse(gram)
        # Step 3: (W @ W^T)^{-1} @ raw_pad (3-vector)
        intermediate = _mat3x3_mul_vec(gram_inv, raw_pad)
        # Step 4: W^T @ intermediate (N-vector)
        wt = _transpose(self._w)
        n = self.n_dims
        result = [0.0] * n
        for i in range(n):
            s = 0.0
            for j in range(3):
                s += wt[i][j] * intermediate[j]
            result[i] = s

        return result

    def classify(self, pad: PADVector) -> str:
        """将 PAD 向量分类为最匹配的分类情感标签。

        使用 CATEGORICAL_REGIONS 中定义的边界框，计算每个区域的匹配度
        （PAD 值落入区域范围内的维度数），返回最佳匹配。

        Args:
            pad: PAD 三维向量。

        Returns:
            最匹配的情感标签字符串。
        """
        best_label = "neutral"
        best_score = -1.0

        pad_values = {"valence": pad.valence, "arousal": pad.arousal, "dominance": pad.dominance}

        for label, bounds in CATEGORICAL_REGIONS.items():
            score = 0.0
            for dim_name, (lo, hi) in bounds.items():
                val = pad_values[dim_name]
                if lo <= val <= hi:
                    # Score by how centered the value is within the range
                    mid = (lo + hi) / 2.0
                    half_range = (hi - lo) / 2.0
                    if half_range > 0:
                        # 1.0 at center, 0.0 at edges
                        score += 1.0 - abs(val - mid) / half_range
                    else:
                        score += 1.0
                else:
                    # Penalty for being outside range
                    dist = min(abs(val - lo), abs(val - hi))
                    score -= dist * 2.0

            if score > best_score:
                best_score = score
                best_label = label

        return best_label

    def update_personality(self, personality: dict[str, float]) -> None:
        """用新人格参数重建投影矩阵 W。

        调制效应（基于文献）：
          - extraversion: 提升唤醒基线（Watson & Clark 1997）
          - neuroticism: 降低愉悦基线（Rusting & Larsen 1997）
          - openness: 扩大投影展幅（McCrae & Costa 1997）

        Args:
            personality: 人格参数字典。
        """
        new_hash = hashlib.sha256(
            "|".join(
                f"{k}:{float(v):.6f}"
                for k, v in sorted(personality.items())
                if isinstance(v, (int, float))
            ).encode()
        ).hexdigest()

        if new_hash == self._personality_hash:
            return  # No change

        self._b = [0.0, 0.0, 0.0]
        self._build_projection_matrix(personality)
