"""Sylanne-Embodiment 计算核心层：MoE-HGT 异构图 Transformer（L5 决策融合层）。

在 7 层计算栈中的位置：L5 决策融合层。
职责：将来自 L1-L4 各子系统的异构信号（伤痕、虚空、边界、人格、惊讶、表达、上下文）
融合为统一的 4 维决策向量，指导 L6/L7 的表达行为。

三阶段架构：
  Stage 1: 类型专家 FFN 编码（7 个类型各有独立的 FFN 专家）
  Stage 2: 真正的多头交叉注意力（4 头，每类型每头独立 Q/K/V 投影）
  Stage 3: 情境专家 MoE FFN（top-2 门控，5 个专家，池化输入）
  + 决策头（16 → 4 维输出）
  + Hebbian 慢适应（BCM 路由偏置 + Oja 注意力先验）

所有基础参数由人格 SHA-256 确定性派生。
运行时适应仅为增量 delta——基础参数永不在运行时改变。
"""

from __future__ import annotations

import hashlib
import math
import struct
from typing import Any

# Lazy numpy detection for pro/max mode acceleration
try:
    import numpy as _np  # noqa: F401

    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

# 7 种异构 token 类型，对应计算栈各子系统的输出
TOKEN_TYPES = (
    "scar",  # 伤痕状态
    "void",  # 虚空状态
    "boundary",  # 自创生边界状态
    "personality",  # 人格向量
    "surprise",  # 惊讶度
    "expression",  # 表达状态
    "context",  # HDC 上下文特征
)
_TYPE_INDEX = {t: i for i, t in enumerate(TOKEN_TYPES)}
_NUM_TYPES = len(TOKEN_TYPES)
_N_EXPERTS = 5
# Expert names: base 5 + extended for pro/max modes
_EXPERT_NAMES_BASE = ("defense", "curiosity", "social", "silence", "repair")
_EXPERT_NAMES_EXTENDED = (
    "defense",
    "curiosity",
    "social",
    "silence",
    "repair",
    "empathy",
    "analysis",
    "boundary",
    "novelty",
    "coherence",
    "energy",
    "timing",
    "trust",
    "growth",
    "safety",
    "meaning",
    "reciprocity",
    "vigilance",
    "flow",
    "depth",
    "ambivalence",
    "momentum",
    "anticipation",
    "recognition",
    "integration",
    "calibration",
    "resonance",
    "adaptation",
    "persistence",
    "release",
    "grounding",
    "perspective",
)

_exp = math.exp
_sqrt = math.sqrt
_tanh = math.tanh


def _deterministic_floats(seed: bytes, count: int) -> list[float]:
    """从种子确定性生成 [-1, 1] 范围的浮点数序列（用于权重初始化）。"""
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


def _make_flat(seed: bytes, rows: int, cols: int, scale: float = 1.0) -> list[float]:
    """生成扁平化权重矩阵（Xavier 初始化 + 确定性种子）。"""
    floats = _deterministic_floats(seed, rows * cols)
    xavier = scale * _sqrt(2.0 / (rows + cols))
    return [f * xavier for f in floats]


def _matmul_vec_flat(mat: list[float], vec: list[float], rows: int, cols: int) -> list[float]:
    """扁平化矩阵与向量的乘法：mat[rows×cols] × vec[cols] → result[rows]。"""
    result = [0.0] * rows
    idx = 0
    for r in range(rows):
        s = 0.0
        for c in range(cols):
            s += mat[idx] * vec[c]
            idx += 1
        result[r] = s
    return result


def _silu(x: float) -> float:
    """SiLU 激活函数（x * sigmoid(x)），带下溢保护。"""
    if x < -80.0:
        return 0.0
    return x / (1.0 + _exp(-x))


def _softmax(values: list[float]) -> list[float]:
    """数值稳定的 softmax（减去最大值防止溢出）。"""
    if not values:
        return []
    max_v = max(values)
    exps = [_exp(v - max_v) for v in values]
    total = sum(exps) + 1e-12
    return [e / total for e in exps]


def _rmsnorm_inplace(vec: list[float], gamma: list[float], n: int) -> None:
    """原地 RMSNorm：vec[i] = vec[i] / rms * gamma[i]（用于层归一化）。"""
    ss = 0.0
    for i in range(n):
        ss += vec[i] * vec[i]
    inv_rms = 1.0 / _sqrt(ss / n + 1e-6)
    for i in range(n):
        vec[i] = vec[i] * inv_rms * gamma[i]


def _rmsnorm(vec: list[float], gamma: list[float]) -> list[float]:
    n = len(vec)
    ss = sum(v * v for v in vec) / n
    inv_rms = 1.0 / _sqrt(ss + 1e-6)
    return [vec[i] * inv_rms * gamma[i] for i in range(n)]


def _vec_add(a: list[float], b: list[float]) -> list[float]:
    return [a[i] + b[i] for i in range(len(a))]


# === Stage 1: 类型专家 FFN（每种 token 类型有独立的 FFN） ===


class TypeExpertFFN:
    """类型专家前馈网络。

    每种 token 类型（scar/void/boundary/...）有独立的 2 层 FFN，
    用于将该类型的原始特征编码为统一的 d_model 维表示。
    结构：x → W1 → SiLU → W2 → 残差连接 → RMSNorm。
    """

    __slots__ = ("w1_flat", "w2_flat", "d_in", "d_hidden", "gamma")

    def __init__(self, d_in: int = 16, d_hidden: int = 24):
        self.d_in = d_in
        self.d_hidden = d_hidden
        self.w1_flat: list[float] = []
        self.w2_flat: list[float] = []
        self.gamma: list[float] = [1.0] * d_in

    def derive(self, seed: bytes) -> None:
        self.w1_flat = _make_flat(seed + b"W1", self.d_hidden, self.d_in)
        self.w2_flat = _make_flat(seed + b"W2", self.d_in, self.d_hidden)
        g_floats = _deterministic_floats(seed + b"GAMMA", self.d_in)
        self.gamma = [0.8 + 0.4 * (f * 0.5 + 0.5) for f in g_floats]

    def forward(self, x: list[float]) -> list[float]:
        hidden = _matmul_vec_flat(self.w1_flat, x, self.d_hidden, self.d_in)
        activated = [_silu(h) for h in hidden]
        out = _matmul_vec_flat(self.w2_flat, activated, self.d_in, self.d_hidden)
        result = [x[i] + out[i] for i in range(self.d_in)]
        _rmsnorm_inplace(result, self.gamma, self.d_in)
        return result


# === Stage 2: 多头交叉注意力（每类型每头独立 d_head×d_head 投影） ===


class MultiHeadCrossAttention:
    """真正的多头交叉注意力，每种类型、每个头有独立的 Q/K/V 投影矩阵。

    关键设计：同类型 token 之间不做注意力（scores[j] = -inf when ti == tj），
    强制不同子系统之间的信息交换。

    注意力先验（attention_prior）由人格参数派生，表示不同类型之间的
    "天然亲和力"——例如高神经质使 scar↔void 的注意力更强。
    """

    __slots__ = (
        "d_model",
        "n_heads",
        "d_head",
        "_wq",
        "_wk",
        "_wv",
        "_attention_prior",
        "_gamma",
    )

    def __init__(self, d_model: int = 16, n_heads: int = 4):
        self.d_model = d_model
        self.n_heads = n_heads
        self.d_head = d_model // n_heads
        self._wq: list[list[list[float]]] = []
        self._wk: list[list[list[float]]] = []
        self._wv: list[list[list[float]]] = []
        self._attention_prior: list[list[float]] = [[0.0] * _NUM_TYPES for _ in range(_NUM_TYPES)]
        self._gamma: list[float] = [1.0] * d_model

    def derive(self, base_seed: bytes, personality: dict[str, float]) -> None:
        d_h = self.d_head
        n_h = self.n_heads
        self._wq = []
        self._wk = []
        self._wv = []
        for t_idx, t_name in enumerate(TOKEN_TYPES):
            t_seed = base_seed + t_name.encode()
            q_heads = []
            k_heads = []
            v_heads = []
            for h in range(n_h):
                hs = struct.pack("<I", h)
                q_heads.append(_make_flat(t_seed + b"Q" + hs, d_h, d_h))
                k_heads.append(_make_flat(t_seed + b"K" + hs, d_h, d_h))
                v_heads.append(_make_flat(t_seed + b"V" + hs, d_h, d_h))
            self._wq.append(q_heads)
            self._wk.append(k_heads)
            self._wv.append(v_heads)
        g_floats = _deterministic_floats(base_seed + b"GAMMA2", self.d_model)
        self._gamma = [0.8 + 0.4 * (f * 0.5 + 0.5) for f in g_floats]
        self._derive_attention_prior(personality)

    def _derive_attention_prior(self, personality: dict[str, float]) -> None:
        N = float(personality.get("neuroticism", personality.get("perception_acuity", 0.5)))
        E = float(personality.get("extraversion", personality.get("expression_drive_trait", 0.5)))
        C = float(personality.get("conscientiousness", personality.get("inner_order", 0.5)))
        openness_val = float(
            personality.get("openness", personality.get("boundary_permeability", 0.5))
        )
        A = float(personality.get("agreeableness", personality.get("relational_gravity", 0.5)))
        mu = [[1.0] * _NUM_TYPES for _ in range(_NUM_TYPES)]
        si, vi, bi, pi, sui, ei, ci = range(_NUM_TYPES)
        mu[si][vi] += N * 1.5
        mu[vi][si] += N * 1.5
        mu[sui][si] += N * 1.0
        mu[si][sui] += N * 1.0
        for i in range(_NUM_TYPES):
            mu[i][ei] += E * 1.2
            mu[ei][i] += E * 0.8
            mu[i][ci] += C * 1.0
            mu[ci][i] += C * 0.6
            mu[i][sui] += openness_val * 0.8
        mu[bi][bi] = max(0.1, 1.0 - A * 0.5)
        for i in range(_NUM_TYPES):
            if i != bi:
                mu[i][i] = 0.0
        self._attention_prior = mu

    def forward(
        self,
        tokens: list[list[float]],
        types: list[int],
        prior_drift: list[list[float]] | None = None,
    ) -> tuple[list[list[float]], list[list[float]]]:
        """多头注意力前向传播（内联 4×4 逐头投影，手动展开以提高性能）。

        Args:
            tokens: 编码后的 token 列表，每个 [d_model] 维
            types: 每个 token 的类型索引
            prior_drift: Oja 适应产生的注意力先验漂移（可选）

        Returns:
            (输出 token 列表, 注意力权重矩阵)
        """
        n = len(tokens)
        d = self.d_model
        n_h = self.n_heads
        d_h = self.d_head
        scale = 1.0 / _sqrt(float(d_h))
        prior = self._attention_prior
        wq = self._wq
        wk = self._wk
        wv = self._wv

        attn_weights = [[0.0] * n for _ in range(n)]
        head_outputs = [[0.0] * d for _ in range(n)]
        inv_nh = 1.0 / n_h

        for h in range(n_h):
            h_off = h * d_h
            # Inline 4x4 Q/K/V projections (unrolled for d_head=4)
            q_vecs: list[Any] = [None] * n
            k_vecs: list[Any] = [None] * n
            v_vecs: list[Any] = [None] * n
            for i in range(n):
                ti = types[i]
                x0 = tokens[i][h_off]
                x1 = tokens[i][h_off + 1]
                x2 = tokens[i][h_off + 2]
                x3 = tokens[i][h_off + 3]
                wqi = wq[ti][h]
                wki = wk[ti][h]
                wvi = wv[ti][h]
                q_vecs[i] = (
                    wqi[0] * x0 + wqi[1] * x1 + wqi[2] * x2 + wqi[3] * x3,
                    wqi[4] * x0 + wqi[5] * x1 + wqi[6] * x2 + wqi[7] * x3,
                    wqi[8] * x0 + wqi[9] * x1 + wqi[10] * x2 + wqi[11] * x3,
                    wqi[12] * x0 + wqi[13] * x1 + wqi[14] * x2 + wqi[15] * x3,
                )
                k_vecs[i] = (
                    wki[0] * x0 + wki[1] * x1 + wki[2] * x2 + wki[3] * x3,
                    wki[4] * x0 + wki[5] * x1 + wki[6] * x2 + wki[7] * x3,
                    wki[8] * x0 + wki[9] * x1 + wki[10] * x2 + wki[11] * x3,
                    wki[12] * x0 + wki[13] * x1 + wki[14] * x2 + wki[15] * x3,
                )
                v_vecs[i] = (
                    wvi[0] * x0 + wvi[1] * x1 + wvi[2] * x2 + wvi[3] * x3,
                    wvi[4] * x0 + wvi[5] * x1 + wvi[6] * x2 + wvi[7] * x3,
                    wvi[8] * x0 + wvi[9] * x1 + wvi[10] * x2 + wvi[11] * x3,
                    wvi[12] * x0 + wvi[13] * x1 + wvi[14] * x2 + wvi[15] * x3,
                )

            for i in range(n):
                ti = types[i]
                qi = q_vecs[i]
                scores = [0.0] * n
                max_s = -1e30
                for j in range(n):
                    tj = types[j]
                    if ti == tj:
                        scores[j] = float("-inf")
                    else:
                        kj = k_vecs[j]
                        s = (qi[0] * kj[0] + qi[1] * kj[1] + qi[2] * kj[2] + qi[3] * kj[3]) * scale
                        bias = prior[ti][tj]
                        if prior_drift is not None:
                            bias += prior_drift[ti][tj]
                        scores[j] = s + bias
                    if scores[j] > max_s:
                        max_s = scores[j]

                exp_sum = 0.0
                for j in range(n):
                    scores[j] = _exp(scores[j] - max_s)
                    exp_sum += scores[j]
                inv_sum = 1.0 / (exp_sum + 1e-12)

                ho = head_outputs[i]
                for j in range(n):
                    w = scores[j] * inv_sum
                    attn_weights[i][j] += w * inv_nh
                    if w > 1e-9:
                        vj = v_vecs[j]
                        ho[h_off] += w * vj[0]
                        ho[h_off + 1] += w * vj[1]
                        ho[h_off + 2] += w * vj[2]
                        ho[h_off + 3] += w * vj[3]

        # Residual + RMSNorm
        outputs: list[list[float]] = []
        gamma = self._gamma
        for i in range(n):
            ho = head_outputs[i]
            out = [tokens[i][dd] + ho[dd] for dd in range(d)]
            _rmsnorm_inplace(out, gamma, d)
            outputs.append(out)

        return outputs, attn_weights


# === Stage 3: 情境专家 MoE FFN（在池化表示上操作） ===


class SituationExpert:
    """单个情境专家：2 层 FFN（SiLU 激活），对应一种行为策略。

    5 个专家分别对应：defense（防御）、curiosity（好奇）、
    social（社交）、silence（沉默）、repair（修复）。
    """

    __slots__ = ("w1_flat", "w2_flat", "d_in", "d_hidden")

    def __init__(self, d_in: int = 16, d_hidden: int = 24):
        self.d_in = d_in
        self.d_hidden = d_hidden
        self.w1_flat: list[float] = []
        self.w2_flat: list[float] = []

    def derive(self, seed: bytes) -> None:
        self.w1_flat = _make_flat(seed + b"W1", self.d_hidden, self.d_in)
        self.w2_flat = _make_flat(seed + b"W2", self.d_in, self.d_hidden)

    def forward(self, x: list[float]) -> list[float]:
        d_h = self.d_hidden
        d_in = self.d_in
        w1 = self.w1_flat
        w2 = self.w2_flat
        # Inline matmul + SiLU + matmul
        hidden = [0.0] * d_h
        idx = 0
        for r in range(d_h):
            s = 0.0
            for c in range(d_in):
                s += w1[idx] * x[c]
                idx += 1
            if s < -80.0:
                hidden[r] = 0.0
            else:
                hidden[r] = s / (1.0 + _exp(-s))
        result = [0.0] * d_in
        idx = 0
        for r in range(d_in):
            s = 0.0
            for c in range(d_h):
                s += w2[idx] * hidden[c]
                idx += 1
            result[r] = s
        return result


class MoELayer:
    """混合专家层：动态 top-k 门控选择 + 负载均衡 + 休眠专家唤醒。

    门控机制：
      1. 路由器计算每个专家的 logit
      2. 加入 BCM 适应偏置和休眠奖励
      3. softmax 后选择 top-k 专家（k 由输入复杂度动态决定）
      4. 选中专家的输出按归一化门控值加权求和
      5. 残差连接 + RMSNorm
    """

    __slots__ = (
        "experts",
        "router_flat",
        "d_model",
        "n_experts",
        "top_k_min",
        "top_k_max",
        "gamma",
        "_expert_last_active",
        "_dormancy_threshold",
        "_tick",
    )

    def __init__(
        self,
        d_model: int = 16,
        n_experts: int = _N_EXPERTS,
        top_k_min: int = 2,
        top_k_max: int = 2,
    ):
        self.d_model = d_model
        self.n_experts = n_experts
        self.top_k_min = top_k_min
        self.top_k_max = top_k_max
        d_hidden = max(24, d_model + 8)
        self.experts: list[SituationExpert] = [
            SituationExpert(d_model, d_hidden) for _ in range(n_experts)
        ]
        self.router_flat: list[float] = []
        self.gamma: list[float] = [1.0] * d_model
        self._expert_last_active: list[int] = [0] * n_experts
        self._dormancy_threshold: int = 50
        self._tick: int = 0

    def derive(self, base_seed: bytes) -> None:
        names = _EXPERT_NAMES_EXTENDED
        for i in range(self.n_experts):
            name = names[i] if i < len(names) else f"expert_{i}"
            self.experts[i].derive(base_seed + name.encode())
        self.router_flat = _make_flat(base_seed + b"ROUTER", self.n_experts, self.d_model)
        g_floats = _deterministic_floats(base_seed + b"GAMMA3", self.d_model)
        self.gamma = [0.8 + 0.4 * (f * 0.5 + 0.5) for f in g_floats]

    def _dynamic_k(self, gate_probs: list[float]) -> int:
        """Determine top-k based on input entropy (higher entropy = more experts needed)."""
        if self.top_k_min == self.top_k_max:
            return self.top_k_min
        entropy = 0.0
        for p in gate_probs:
            if p > 1e-9:
                entropy -= p * math.log(p)
        max_entropy = math.log(self.n_experts) if self.n_experts > 1 else 1.0
        normalized = entropy / max_entropy if max_entropy > 0 else 0.0
        k = self.top_k_min + int(normalized * (self.top_k_max - self.top_k_min) + 0.5)
        return min(k, self.top_k_max)

    def forward(
        self,
        pooled: list[float],
        router_bias: list[float] | None = None,
    ) -> tuple[list[float], list[int], list[float]]:
        """MoE 前向传播：动态 top-k 门控选择专家。

        Args:
            pooled: 池化后的 d_model 维输入
            router_bias: BCM 适应产生的路由偏置（可选）

        Returns:
            (d_model 维输出, 激活的专家索引列表, 门控概率列表)
        """
        d = self.d_model
        n_e = self.n_experts
        self._tick += 1

        logits = _matmul_vec_flat(self.router_flat, pooled, n_e, d)
        if router_bias is not None:
            for i in range(min(n_e, len(router_bias))):
                logits[i] += router_bias[i]

        # Load balancing: bonus for dormant experts
        tick = self._tick
        for i in range(n_e):
            if tick - self._expert_last_active[i] > self._dormancy_threshold:
                logits[i] += 0.15

        gate_probs = _softmax(logits)

        # Dynamic top-k selection
        k = self._dynamic_k(gate_probs)
        indexed = sorted(range(n_e), key=lambda i: gate_probs[i], reverse=True)
        top_indices = indexed[:k]

        # Update last active for selected experts
        for idx in top_indices:
            self._expert_last_active[idx] = tick

        # Normalize gate values for selected experts
        gate_sum = sum(gate_probs[i] for i in top_indices) + 1e-12
        weights = [gate_probs[i] / gate_sum for i in top_indices]

        # Weighted combination of expert outputs
        result = list(pooled)  # start with residual
        for rank, idx in enumerate(top_indices):
            e_out = self.experts[idx].forward(pooled)
            w = weights[rank]
            for dd in range(d):
                result[dd] += w * e_out[dd]

        _rmsnorm_inplace(result, self.gamma, d)
        return result, top_indices, gate_probs


# === Hebbian 慢适应机制 ===


class RouterAdaptation:
    """BCM 启发的路由器偏置适应。

    根据表达结果（accepted/ignored/rejected）调整路由器偏置：
      - accepted: 强化当前激活的专家（正向 BCM 更新）
      - rejected: 抑制当前激活的专家
      - ignored: 轻微抑制

    BCM 规则：delta = eta * y * (y - theta)，其中 theta 是活动度 EMA。
    全局衰减 0.998 防止偏置无限增长。
    """

    def __init__(self, n_experts: int = _N_EXPERTS):
        self.n_experts = n_experts
        self.bias: list[float] = [0.0] * n_experts
        self.activity_ema: list[float] = [0.2] * n_experts
        self.plasticity: float = 0.5

    def adapt(self, outcome: str, active_experts: list[int], gate_values: list[float]) -> None:
        eta = 0.008 * self.plasticity
        for idx in active_experts:
            if idx >= len(gate_values):
                continue
            y = gate_values[idx]
            theta = self.activity_ema[idx] if idx < len(self.activity_ema) else 0.2
            if outcome == "accepted":
                delta = eta * max(y, 0.05) * (y - theta)
            elif outcome == "rejected":
                delta = -eta * max(y, 0.05) * max(0.1, y)
            else:
                delta = -eta * 0.3 * max(y, 0.05)
            self.bias[idx] = max(-1.0, min(1.0, self.bias[idx] + delta))
            if idx < len(self.activity_ema):
                self.activity_ema[idx] = 0.99 * theta + 0.01 * (y * y)
        for i in range(self.n_experts):
            self.bias[i] *= 0.998

    def to_dict(self) -> dict[str, Any]:
        return {
            "bias": list(self.bias),
            "activity_ema": list(self.activity_ema),
            "plasticity": self.plasticity,
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        saved_bias = list(data.get("bias", []))
        saved_ema = list(data.get("activity_ema", []))
        # Handle size mismatch (e.g., upgrading from lite 5 experts to pro 16)
        self.bias = [0.0] * self.n_experts
        self.activity_ema = [0.2] * self.n_experts
        for i in range(min(len(saved_bias), self.n_experts)):
            self.bias[i] = float(saved_bias[i])
        for i in range(min(len(saved_ema), self.n_experts)):
            self.activity_ema[i] = float(saved_ema[i])
        self.plasticity = float(data.get("plasticity", 0.5))


class AttentionPriorAdaptation:
    """Oja 启发的注意力先验适应。

    根据表达结果调整类型间的注意力先验漂移：
      - accepted: 强化高注意力权重的类型对（Oja 规则）
      - rejected: 抑制所有注意力连接
      - ignored: 不更新

    漂移值 clamp 在 [-0.3, 0.3]，全局衰减 0.999 防止累积过大。
    """

    def __init__(self, n_types: int = _NUM_TYPES):
        self.n_types = n_types
        self.drift: list[list[float]] = [[0.0] * n_types for _ in range(n_types)]
        self.plasticity: float = 0.5

    def adapt(self, outcome: str, attention_weights: list[list[float]]) -> None:
        eta = 0.005 * self.plasticity
        n = self.n_types
        drift = self.drift
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                w = drift[i][j]
                y = attention_weights[i][j]
                if outcome == "accepted":
                    x = 1.0 if y > 0.15 else 0.0
                    delta = eta * y * (x - y * w)
                elif outcome == "rejected":
                    delta = -eta * y * 0.5
                else:
                    delta = 0.0
                drift[i][j] = max(-0.3, min(0.3, w + delta))
        for i in range(n):
            for j in range(n):
                drift[i][j] *= 0.999

    def to_dict(self) -> dict[str, Any]:
        return {
            "drift": [list(row) for row in self.drift],
            "plasticity": self.plasticity,
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        drift = data.get("drift")
        if drift and len(drift) == self.n_types:
            self.drift = [list(row) for row in drift]
        self.plasticity = float(data.get("plasticity", 0.5))


def _derive_plasticity(personality: dict[str, float]) -> float:
    """从人格参数派生可塑性：开放性↑ → 可塑性↑，尽责性↑ → 可塑性↓。"""
    openness_val = float(personality.get("openness", personality.get("boundary_permeability", 0.5)))
    C = float(personality.get("conscientiousness", personality.get("inner_order", 0.5)))
    base = 0.3 + openness_val * 0.5 - C * 0.3
    return max(0.05, min(0.85, base))


# === 主类 ===


class HeterogeneousGraphTransformer:
    """MoE-HGT：Sylanne 的完整决策融合模块。

    将 7 种异构 token（来自计算栈各层）融合为 4 维决策向量：
      d[0]: 表达驱动力修正（正值 = 鼓励表达）
      d[1]: 边界灵敏度修正（正值 = 更敏感）
      d[2]: 紧急度修正（保留）
      d[3]: 表达抑制信号（> 0.5 时否决表达）

    三阶段处理：
      1. TypeExpertFFN: 每种类型独立编码
      2. MultiHeadCrossAttention: 跨类型信息交换
      3. MoELayer: 情境专家决策 + 决策头投影

    适应机制：
      - RouterAdaptation: BCM 路由偏置（慢速学习哪些专家更有效）
      - AttentionPriorAdaptation: Oja 注意力先验（慢速学习哪些类型对更重要）
    """

    TOKEN_TYPES = TOKEN_TYPES

    __slots__ = (
        "d_model",
        "n_heads",
        "d_output",
        "_attention_rounds",
        "_type_experts",
        "_attention",
        "_moe",
        "_decision_flat",
        "_personality_cache",
        "_router_adapt",
        "_attn_adapt",
        "_last_attention_weights",
        "_last_active_experts",
        "_last_gate_values",
        "_use_numpy",
    )

    def __init__(
        self,
        d_model: int = 16,
        n_heads: int = 4,
        d_output: int = 4,
        n_experts: int = _N_EXPERTS,
        top_k_min: int = 2,
        top_k_max: int = 2,
        attention_rounds: int = 1,
    ):
        self.d_model = d_model
        self.n_heads = n_heads
        self.d_output = d_output
        self._attention_rounds = attention_rounds
        d_hidden = max(20, d_model + 4)
        self._type_experts: list[TypeExpertFFN] = [
            TypeExpertFFN(d_model, d_hidden) for _ in range(_NUM_TYPES)
        ]
        self._attention = MultiHeadCrossAttention(d_model, n_heads)
        self._moe = MoELayer(d_model, n_experts, top_k_min, top_k_max)
        self._decision_flat: list[float] = []
        self._personality_cache: str = ""
        self._router_adapt = RouterAdaptation(n_experts)
        self._attn_adapt = AttentionPriorAdaptation(_NUM_TYPES)
        self._last_attention_weights: list[list[float]] = []
        self._last_active_experts: list[int] = []
        self._last_gate_values: list[float] = []
        self._use_numpy: bool = _HAS_NUMPY

    def derive_params(self, personality: dict[str, float]) -> None:
        cache_key = str(sorted(personality.items()))
        if cache_key == self._personality_cache:
            return
        self._personality_cache = cache_key

        p_keys = sorted(personality.keys())
        seed_str = "|".join(
            f"{k}:{float(personality[k]):.6f}"
            for k in p_keys
            if isinstance(personality[k], (int, float))
        )
        base_seed = hashlib.sha256(seed_str.encode()).digest()

        for t_idx, t_name in enumerate(TOKEN_TYPES):
            self._type_experts[t_idx].derive(base_seed + t_name.encode() + b"TE")

        self._attention.derive(base_seed, personality)
        self._moe.derive(base_seed + b"MOE")

        self._decision_flat = _make_flat(
            base_seed + b"DECISION", self.d_output, self.d_model, scale=0.5
        )

        plasticity = _derive_plasticity(personality)
        self._router_adapt.plasticity = plasticity
        self._attn_adapt.plasticity = plasticity

    def forward(
        self,
        tokens: list[tuple[str, list[float]]],
        personality: dict[str, float] | None = None,
    ) -> list[float]:
        if personality is not None:
            self.derive_params(personality)

        if not tokens:
            return [0.0] * self.d_output

        d = self.d_model
        n = len(tokens)
        types: list[int] = []
        vecs: list[list[float]] = []
        for t_name, vec in tokens:
            t_idx = _TYPE_INDEX.get(t_name, 0)
            types.append(t_idx)
            if len(vec) < d:
                vecs.append(vec + [0.0] * (d - len(vec)))
            else:
                vecs.append(vec[:d])

        # Stage 1: Type-Expert FFN
        te = self._type_experts
        if self._use_numpy:
            from sylanne_core.compute.hgt_numpy import numpy_type_expert_forward

            encoded: list[list[float]] = [
                numpy_type_expert_forward(
                    vecs[i],
                    te[types[i]].w1_flat,
                    te[types[i]].w2_flat,
                    te[types[i]].gamma,
                    te[types[i]].d_in,
                    te[types[i]].d_hidden,
                )
                for i in range(n)
            ]
        else:
            encoded = [te[types[i]].forward(vecs[i]) for i in range(n)]

        # Stage 2: Multi-Head Cross-Attention (multi-round for pro/max)
        attended = encoded
        attn_weights: list[list[float]] = []
        if self._use_numpy:
            from sylanne_core.compute.hgt_numpy import numpy_multi_head_attention

            attn = self._attention
            for _round in range(self._attention_rounds):
                attended, attn_weights = numpy_multi_head_attention(
                    attended,
                    types,
                    attn._wq,
                    attn._wk,
                    attn._wv,
                    attn.n_heads,
                    attn.d_head,
                    attn._attention_prior,
                    self._attn_adapt.drift,
                    attn._gamma,
                )
        else:
            for _round in range(self._attention_rounds):
                attended, attn_weights = self._attention.forward(
                    attended,
                    types,
                    prior_drift=self._attn_adapt.drift,
                )
        self._last_attention_weights = attn_weights

        # Mean-pool attended tokens for Stage 3
        if self._use_numpy:
            import numpy as _np_local

            pooled = (_np_local.array(attended, dtype=_np_local.float64).mean(axis=0)).tolist()
        else:
            pooled = [0.0] * d
            for tok in attended:
                for dd in range(d):
                    pooled[dd] += tok[dd]
            inv_n = 1.0 / n
            for dd in range(d):
                pooled[dd] *= inv_n

        # Stage 3: Situation-Expert MoE (on pooled representation)
        # Routing logic (dynamic k, dormancy, load balancing) stays in pure Python
        # to preserve exact stateful behavior. Only expert computation is accelerated.
        moe = self._moe
        d_moe = moe.d_model
        n_e = moe.n_experts
        moe._tick += 1

        logits = _matmul_vec_flat(moe.router_flat, pooled, n_e, d_moe)
        router_bias = self._router_adapt.bias
        if router_bias is not None:
            for i in range(min(n_e, len(router_bias))):
                logits[i] += router_bias[i]

        tick = moe._tick
        for i in range(n_e):
            if tick - moe._expert_last_active[i] > moe._dormancy_threshold:
                logits[i] += 0.15

        gate_probs = _softmax(logits)
        k = moe._dynamic_k(gate_probs)
        indexed = sorted(range(n_e), key=lambda i: gate_probs[i], reverse=True)
        top_indices = indexed[:k]

        for idx in top_indices:
            moe._expert_last_active[idx] = tick

        gate_sum = sum(gate_probs[i] for i in top_indices) + 1e-12
        weights_moe = [gate_probs[i] / gate_sum for i in top_indices]

        if self._use_numpy:
            from sylanne_core.compute.hgt_numpy import numpy_moe_forward

            expert_w1s = [moe.experts[idx].w1_flat for idx in top_indices]
            expert_w2s = [moe.experts[idx].w2_flat for idx in top_indices]
            d_hidden = moe.experts[0].d_hidden
            moe_out = numpy_moe_forward(
                pooled,
                moe.router_flat,
                expert_w1s,
                expert_w2s,
                n_e,
                top_indices,
                weights_moe,
                d_moe,
                d_hidden,
                moe.gamma,
            )
        else:
            result_moe = list(pooled)
            for rank, idx in enumerate(top_indices):
                e_out = moe.experts[idx].forward(pooled)
                w = weights_moe[rank]
                for dd in range(d_moe):
                    result_moe[dd] += w * e_out[dd]
            _rmsnorm_inplace(result_moe, moe.gamma, d_moe)
            moe_out = result_moe

        active_experts = top_indices
        gate_values = gate_probs
        self._last_active_experts = active_experts
        self._last_gate_values = list(gate_values)

        # Decision Head: project → activate
        raw = _matmul_vec_flat(self._decision_flat, moe_out, self.d_output, d)
        decision = [_tanh(v) for v in raw]
        if len(decision) >= 4:
            clamped = max(-500.0, min(500.0, raw[3] * 3.0))
            decision[3] = 1.0 / (1.0 + _exp(-clamped))
        # Final clamp to [-1, 1]
        decision = [max(-1.0, min(1.0, d)) for d in decision]
        return decision

    def adapt(self, outcome: str, attention_snapshot: list[list[float]] | None = None) -> None:
        if outcome not in ("accepted", "ignored", "rejected"):
            return
        if self._last_active_experts and self._last_gate_values:
            self._router_adapt.adapt(outcome, self._last_active_experts, self._last_gate_values)
        weights = attention_snapshot if attention_snapshot else self._last_attention_weights
        if weights and len(weights) == _NUM_TYPES:
            self._attn_adapt.adapt(outcome, weights)

    def adaptation_state(self) -> dict[str, Any]:
        return {
            "router_bias": list(self._router_adapt.bias),
            "router_activity_ema": list(self._router_adapt.activity_ema),
            "attention_drift": [list(row) for row in self._attn_adapt.drift],
            "plasticity": self._router_adapt.plasticity,
            "last_active_experts": list(self._last_active_experts),
            "last_gate_values": list(self._last_gate_values),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "router_adapt": self._router_adapt.to_dict(),
            "attn_adapt": self._attn_adapt.to_dict(),
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        if "router_adapt" in data:
            self._router_adapt.from_dict(data["router_adapt"])
        if "attn_adapt" in data:
            self._attn_adapt.from_dict(data["attn_adapt"])

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
        """从计算脊柱各子系统状态构建类型化 token 列表。

        将各子系统的内部状态提取为统一的 16 维向量，附上类型标签，
        供 forward() 方法处理。
        """
        tokens: list[tuple[str, list[float]]] = []
        d = self.d_model

        scar_vec = [0.0] * d
        n_dims = min(scar_state.n_dims, d // 2)
        for dim_i in range(n_dims):
            raw_mod = scar_state.modifier(dim_i)
            scar_vec[dim_i] = min(1.0, math.log2(max(1.0, raw_mod)) / 2.5)
            if dim_i + n_dims < d:
                scar_vec[dim_i + n_dims] = (
                    scar_state.base[dim_i] if dim_i < len(scar_state.base) else 0.0
                )
        tokens.append(("scar", scar_vec))

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

        bnd_vec = [0.0] * d
        bnd_vec[0] = boundary.boundary_integrity
        bnd_vec[1] = boundary.internal_entropy
        bnd_vec[2] = boundary.repair_rate
        tokens.append(("boundary", bnd_vec))

        p_keys = [
            "extraversion",
            "neuroticism",
            "conscientiousness",
            "openness",
            "agreeableness",
        ]
        p_vec = [0.0] * d
        for i, k in enumerate(p_keys):
            if i < d:
                # Accept both legacy and new names
                alt_keys = {
                    "extraversion": "expression_drive_trait",
                    "neuroticism": "perception_acuity",
                    "conscientiousness": "inner_order",
                    "openness": "boundary_permeability",
                    "agreeableness": "relational_gravity",
                }
                p_vec[i] = personality.get(k, personality.get(alt_keys.get(k, ""), 0.5))
        tokens.append(("personality", p_vec))

        s_vec = [0.0] * d
        s_vec[0] = surprise
        s_vec[1] = surprise * surprise
        tokens.append(("surprise", s_vec))

        e_vec = [0.0] * d
        e_vec[0] = expression.pressure / max(0.01, expression.threshold)
        e_vec[1] = expression.threshold
        e_vec[2] = expression.expression_intensity()
        tokens.append(("expression", e_vec))

        c_vec = (hdc_features + [0.0] * d)[:d]
        tokens.append(("context", c_vec))

        return tokens
