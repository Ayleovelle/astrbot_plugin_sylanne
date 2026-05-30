"""Sylanne-Embodiment 计算核心层：伤痕代数（Scar Algebra）。

在 7 层计算栈中的位置：L3 VoidScar 层的"伤痕"部分。
职责：实现一种自修改算子代数——过去的操作会不可逆地改变未来操作的语义。
伤痕是不可逆的标记，它们调制系统处理未来输入的方式。

核心概念：
  - Scar（伤痕）：附着在某个维度上的不可逆标记，有 RAW→CLOSING→SCARRED→FADED 四阶段愈合
  - ScarredState（伤痕状态）：基向量 + 伤痕序列，通过 ⊳ 算子实现状态转移
  - modifier（调制因子）：伤痕对维度的累积放大/麻木效应
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class HealingStage(IntEnum):
    """伤痕愈合阶段枚举。

    RAW(0) → CLOSING(1) → SCARRED(2) → FADED(3)
    每个阶段有不同的 alpha 调制因子和持续时间。
    """

    RAW = 0
    CLOSING = 1
    SCARRED = 2
    FADED = 3


# 各阶段的 alpha 调制因子：RAW 阶段放大最强（2.0），FADED 阶段衰减（0.7）
_STAGE_ALPHA = {
    HealingStage.RAW: 2.0,
    HealingStage.CLOSING: 1.5,
    HealingStage.SCARRED: 1.0,
    HealingStage.FADED: 0.7,
}

# 各阶段的默认持续时间（tick 数），FADED 阶段无限期
_STAGE_DURATION = {
    HealingStage.RAW: 10,
    HealingStage.CLOSING: 40,
    HealingStage.SCARRED: 150,
}


@dataclass(slots=True)
class Scar:
    """单个伤痕对象。

    附着在特定维度上，有四阶段愈合过程。
    alpha 属性决定该伤痕对所在维度的调制强度：
      RAW=2.0（新伤放大）, CLOSING=1.5, SCARRED=1.0（中性）, FADED=0.7（衰减）
    """

    dimension: int
    timestamp: float
    stage: HealingStage = HealingStage.RAW
    ticks_in_stage: int = 0

    @property
    def alpha(self) -> float:
        return _STAGE_ALPHA[self.stage]

    def heal_tick(self) -> bool:
        """推进愈合一个 tick。如果阶段发生变化返回 True。"""
        if self.stage == HealingStage.FADED:
            return False
        self.ticks_in_stage += 1
        threshold = _STAGE_DURATION.get(self.stage)
        if threshold is not None and self.ticks_in_stage >= threshold:
            self.stage = HealingStage(self.stage + 1)
            self.ticks_in_stage = 0
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "timestamp": self.timestamp,
            "stage": self.stage.name,
            "ticks_in_stage": self.ticks_in_stage,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Scar":
        return cls(
            dimension=data["dimension"],
            timestamp=data["timestamp"],
            stage=HealingStage[data["stage"]],
            ticks_in_stage=data.get("ticks_in_stage", 0),
        )


class ScarredState:
    """伤痕代数核心状态：基向量 + 不可逆伤痕序列。

    状态转移通过 ⊳ 算子（step 方法）实现：
      1. 伤痕调制输入（modulate）：每个维度的输入乘以该维度的累积 modifier
      2. 基向量演化（_evolve_base）：2 层 MLP 将 [当前状态; 调制后输入] 映射为新状态
      3. 伤痕形成（conditional）：调制后输入超过阈值的维度产生新伤痕
      4. 愈合（heal）：已有伤痕按阶段推进

    与其他组件的关系：
      - 被 VoidScarEngine 调用，接收 HDC 压缩后的 8 维输入
      - 通过 Φ 耦合影响 VoidSpace 的检测灵敏度
      - observe() 输出 8 维情感状态给下游层
    """

    __slots__ = (
        "base",
        "scars",
        "n_dims",
        "wound_threshold",
        "_tick",
        "_t_raw",
        "_t_closing",
        "_t_scarred",
        "_mlp_w1",
        "_mlp_w2",
        "_mlp_hidden_dim",
        "_neuroticism",
        # Session scar cap (sovereignty immune system)
        "_session_scar_count",
        "_session_scar_cap",
        # Circuit breaker (protective dissociation)
        "_circuit_breaker_active",
        "_circuit_breaker_remaining",
        "_recent_scar_ticks",
        # Time-aware healing
        "_last_step_time",
        # 每维度 modifier 缓存（避免 observe/modulate 重复遍历伤痕列表）
        "_modifier_cache",
        "_modifier_cache_valid",
    )

    def __init__(self, n_dims: int = 8, wound_threshold: float = 0.6):
        self.n_dims = n_dims
        self.wound_threshold = wound_threshold
        self.base = [0.0] * n_dims
        self.scars: list[Scar] = []
        self._tick = 0
        self._neuroticism: float = 0.5
        # Configurable healing rates (defaults match original _STAGE_DURATION)
        self._t_raw: int = 10
        self._t_closing: int = 40
        self._t_scarred: int = 150
        # MLP parameters for base state evolution (initialized lazily)
        self._mlp_hidden_dim: int = 12
        self._mlp_w1: list[list[float]] | None = None
        self._mlp_w2: list[list[float]] | None = None
        # Session scar cap (sovereignty immune system)
        self._session_scar_count: int = 0
        self._session_scar_cap: int = 3
        # Circuit breaker (protective dissociation)
        self._circuit_breaker_active: bool = False
        self._circuit_breaker_remaining: int = 0
        self._recent_scar_ticks: list[int] = []
        # Time-aware healing
        self._last_step_time: float = 0.0
        # 每维度 modifier 缓存：避免 observe() 和 modulate() 每次都遍历全部伤痕
        # 任何伤痕变动（新增/愈合/移除）都会使缓存失效
        self._modifier_cache: dict[int, float] = {}
        self._modifier_cache_valid: bool = False

    def set_healing_rates(
        self, t_raw: int, t_closing: int, t_scarred: int, neuroticism: float = 0.5
    ) -> None:
        """设置各愈合阶段的持续时间（由人格参数驱动）。

        高神经质 → 愈合更慢（各阶段持续时间更长）。

        Args:
            t_raw: RAW 阶段持续 tick 数
            t_closing: CLOSING 阶段持续 tick 数
            t_scarred: SCARRED 阶段持续 tick 数
            neuroticism: 人格神经质值，影响 modifier 上限
        """
        self._t_raw = max(1, int(t_raw))
        self._t_closing = max(1, int(t_closing))
        self._t_scarred = max(1, int(t_scarred))
        self._neuroticism = float(neuroticism)
        # 神经质值影响 modifier 饱和上限，需要使缓存失效
        self._invalidate_modifier_cache()

    def healing_duration(self, stage: "HealingStage", dim: int | None = None, _dim_counts: dict[int, int] | None = None) -> int:
        """获取某阶段的愈合持续时间，可选按维度调整。

        如果某维度的伤痕数 > 3，愈合速度降低 50%（反复受伤的地方更难愈合）。
        """
        base_duration = {
            HealingStage.RAW: self._t_raw,
            HealingStage.CLOSING: self._t_closing,
            HealingStage.SCARRED: self._t_scarred,
        }.get(stage, 0)
        if dim is not None:
            count = (_dim_counts or {}).get(dim) if _dim_counts else None
            if count is None:
                count = self.scar_count(dim)
            if count > 3:
                base_duration = int(base_duration * 1.5)
        return base_duration

    def scar_count(self, dim: int) -> int:
        """Count total scars on a given dimension."""
        return sum(1 for s in self.scars if s.dimension == dim)

    def _init_mlp_weights(self, seed: int = 42) -> None:
        """从确定性种子初始化 MLP 权重，并应用谱归一化。"""
        import random

        rng = random.Random(seed)
        input_dim = self.n_dims * 2  # [x; e_tilde] concatenated
        hidden_dim = self._mlp_hidden_dim

        # Layer 1: hidden_dim x input_dim
        self._mlp_w1 = [
            [rng.gauss(0, 0.5) for _ in range(input_dim)] for _ in range(hidden_dim)
        ]
        # Layer 2: n_dims x hidden_dim
        self._mlp_w2 = [
            [rng.gauss(0, 0.5) for _ in range(hidden_dim)] for _ in range(self.n_dims)
        ]
        # Apply spectral normalization to both weight matrices
        self._mlp_w1 = self._spectral_normalize(self._mlp_w1, max_sigma=0.7)
        self._mlp_w2 = self._spectral_normalize(self._mlp_w2, max_sigma=0.7)

    def _spectral_normalize(
        self, W: list[list[float]], max_sigma: float = 0.7
    ) -> list[list[float]]:
        """谱归一化：通过幂迭代估计最大奇异值，超过 max_sigma 时缩放矩阵。

        确保 ||W||_2 <= max_sigma，这是状态演化收敛的关键保证。
        10 次幂迭代足以收敛到合理精度。
        """
        rows = len(W)
        cols = len(W[0]) if rows > 0 else 0
        if rows == 0 or cols == 0:
            return W

        # Power iteration (10 iterations is sufficient for convergence)
        # Initialize u as unit vector
        u = [1.0 / math.sqrt(rows)] * rows
        v = [0.0] * cols

        for _ in range(10):
            # v = W^T u / ||W^T u||
            for j in range(cols):
                v[j] = sum(W[i][j] * u[i] for i in range(rows))
            v_norm = math.sqrt(sum(x * x for x in v)) + 1e-12
            v = [x / v_norm for x in v]

            # u = W v / ||W v||
            for i in range(rows):
                u[i] = sum(W[i][j] * v[j] for j in range(cols))
            u_norm = math.sqrt(sum(x * x for x in u)) + 1e-12
            u = [x / u_norm for x in u]

        # Estimate sigma = u^T W v
        sigma = 0.0
        for i in range(rows):
            sigma += u[i] * sum(W[i][j] * v[j] for j in range(cols))

        # Scale if needed
        if sigma > max_sigma:
            scale = max_sigma / sigma
            return [[W[i][j] * scale for j in range(cols)] for i in range(rows)]
        return W

    def _evolve_base(self, x: list[float], e_tilde: list[float]) -> list[float]:
        """通过 2 层 MLP 演化基向量（带谱归一化保证收敛）。

        Layer 1: hidden = tanh(W1 * [x; e_tilde])
        Layer 2: output = tanh(W2 * hidden)

        收敛保证：||W1||_2 * ||W2||_2 < 0.7 * 0.7 = 0.49 < 1
        这确保了状态演化是收缩映射，不会发散。
        """
        if self._mlp_w1 is None or self._mlp_w2 is None:
            self._init_mlp_weights()

        # Concatenate input: [x; e_tilde]
        inp = list(x) + list(e_tilde)
        hidden_dim = len(self._mlp_w1)
        out_dim = len(self._mlp_w2)

        # Layer 1: hidden = tanh(W1 * inp)
        hidden = [0.0] * hidden_dim
        for i in range(hidden_dim):
            val = sum(self._mlp_w1[i][j] * inp[j] for j in range(len(inp)))
            hidden[i] = math.tanh(val)

        # Layer 2: output = tanh(W2 * hidden)
        output = [0.0] * out_dim
        for i in range(out_dim):
            val = sum(self._mlp_w2[i][j] * hidden[j] for j in range(hidden_dim))
            output[i] = math.tanh(val)

        return output

    def _invalidate_modifier_cache(self) -> None:
        """使 modifier 缓存失效（伤痕新增/愈合/移除时调用）。"""
        self._modifier_cache_valid = False

    def _ensure_modifier_cache(self) -> None:
        """按需重建全维度 modifier 缓存。

        一次遍历伤痕列表，计算所有维度的 product，再统一做饱和压缩。
        复杂度从 O(n_dims * num_scars) 降为 O(num_scars + n_dims)。
        """
        if self._modifier_cache_valid:
            return
        # 一次遍历收集每维度的 alpha 乘积
        products = [1.0] * self.n_dims
        for scar in self.scars:
            products[scar.dimension] *= scar.alpha
        # 对每个维度做饱和压缩
        max_mod = 2.0 + self._neuroticism * 3.0
        cache = {}
        for d in range(self.n_dims):
            p = products[d]
            if p <= 1.0:
                cache[d] = max(0.05, p)
            else:
                cache[d] = 1.0 + (max_mod - 1.0) * (1.0 - 1.0 / (p + 1e-10))
        self._modifier_cache = cache
        self._modifier_cache_valid = True

    def modifier(self, dim: int) -> float:
        """计算某维度的累积伤痕调制因子（带缓存）。

        使用对数压缩 + 人格驱动上限，防止多个伤痕的 alpha 乘积无限增长。
        公式：当 product > 1 时，modifier = 1 + (max_mod - 1) * (1 - 1/product)
        这是一个渐近线为 max_mod 的饱和函数。

        缓存策略：首次调用时一次性计算全部维度并缓存，后续直接查表。
        伤痕变动（wound/heal/remove）时缓存自动失效。

        Returns:
            调制因子，范围 [0.05, max_mod]。< 0.5 表示"麻木"，> 1.0 表示"敏感化"
        """
        self._ensure_modifier_cache()
        return self._modifier_cache.get(dim, 1.0)

    def modulate(self, event: list[float]) -> list[float]:
        """对输入事件应用伤痕调制（⊳ 算子的第 1 步）。

        每个维度的输入值乘以该维度的 modifier：
          - modifier > 1：该维度被"敏感化"，微小输入也会被放大
          - modifier < 1：该维度被"麻木"，需要更大输入才能产生效果
        """
        result = []
        for d in range(self.n_dims):
            e_d = event[d] if d < len(event) else 0.0
            result.append(e_d * self.modifier(d))
        return result

    def step(
        self, event: list[float], timestamp: float = 0.0, *, heal: bool = True
    ) -> dict[str, Any]:
        """应用 ⊳ 算子：完整状态转移。

        四步流程：
          1. 伤痕调制输入
          2. MLP 演化基向量
          3. 条件性伤痕形成（受会话上限和断路器保护）
          4. 已有伤痕愈合推进

        Args:
            event: 8 维输入事件向量
            timestamp: 事件时间戳（用于时间感知愈合）
            heal: 是否执行愈合步骤（Γ 耦合创伤事件设为 False）

        Returns:
            诊断字典，包含调制后输入、新伤痕、愈合维度等信息
        """
        if heal:
            self._tick += 1

        # --- Circuit breaker: protective dissociation ---
        if self._circuit_breaker_active:
            self._circuit_breaker_remaining -= 1
            if self._circuit_breaker_remaining <= 0:
                self._circuit_breaker_active = False
            effective_threshold = 0.95
        else:
            effective_threshold = self.wound_threshold

        # Step 1: Scar-modulated input
        modulated = self.modulate(event)

        # Step 2: Base state evolution (2-layer MLP with spectral normalization)
        self.base = self._evolve_base(self.base, modulated)

        # Step 3: Scar formation (conditional, with session cap)
        existing_count = len(self.scars)
        new_scars = []
        for d in range(self.n_dims):
            if abs(modulated[d]) > effective_threshold:
                # Session scar cap check
                if self._session_scar_count >= self._session_scar_cap:
                    # Skip scar creation when cap reached
                    continue
                scar = Scar(dimension=d, timestamp=timestamp)
                self.scars.append(scar)
                new_scars.append(d)
                self._session_scar_count += 1

        # Circuit breaker trigger: check for rapid scar formation
        if new_scars:
            # 新伤痕产生，使 modifier 缓存失效
            self._invalidate_modifier_cache()
            self._recent_scar_ticks.append(self._tick)
            self._recent_scar_ticks = [
                t for t in self._recent_scar_ticks if self._tick - t <= 10
            ]
            if len(self._recent_scar_ticks) >= 5 and not self._circuit_breaker_active:
                self._circuit_breaker_active = True
                self._circuit_breaker_remaining = 30

        # Step 4: Healing (using configurable per-dimension rates)
        # Only heal pre-existing scars; newly formed scars skip their birth tick.
        healed = []
        if heal:
            # 预计算 per-dim scar count，避免 O(n²)——主循环和奖励愈合共用
            _dim_counts: dict[int, int] = {}
            for s in self.scars[:existing_count]:
                _dim_counts[s.dimension] = _dim_counts.get(s.dimension, 0) + 1

            # Time-aware healing: grant bonus ticks for real-time silence
            if timestamp > 0 and self._last_step_time > 0:
                elapsed_minutes = (timestamp - self._last_step_time) / 60.0
                bonus_ticks = int(
                    elapsed_minutes / 5.0
                )  # 1 bonus tick per 5 min silence
                bonus_ticks = min(bonus_ticks, 10)  # cap at 10 bonus ticks
                for _ in range(bonus_ticks):
                    self._heal_one_tick(existing_count, healed, _dim_counts)
            self._last_step_time = timestamp

            for scar in self.scars[:existing_count]:
                if scar.stage == HealingStage.FADED:
                    continue
                scar.ticks_in_stage += 1
                threshold = self.healing_duration(scar.stage, dim=scar.dimension, _dim_counts=_dim_counts)
                if threshold > 0 and scar.ticks_in_stage >= threshold:
                    scar.stage = HealingStage(scar.stage + 1)
                    scar.ticks_in_stage = 0
                    healed.append(scar.dimension)

            # Prune excess FADED scars to prevent unbounded growth
            faded = [s for s in self.scars if s.stage == HealingStage.FADED]
            if len(faded) > 50:
                self.scars = [
                    s for s in self.scars if s.stage != HealingStage.FADED
                ] + faded[-50:]

            # 愈合/修剪导致伤痕阶段变化或数量变化，使缓存失效
            if healed or len(faded) > 50:
                self._invalidate_modifier_cache()

        return {
            "modulated": modulated,
            "new_scars": new_scars,
            "healed_dimensions": healed,
            "total_scars": len(self.scars),
            "base": list(self.base),
        }

    def _heal_one_tick(self, existing_count: int, healed: list[int], _dim_counts: dict[int, int] | None = None) -> None:
        """执行一次愈合 tick（用于时间感知的奖励愈合）。"""
        for scar in self.scars[:existing_count]:
            if scar.stage == HealingStage.FADED:
                continue
            scar.ticks_in_stage += 1
            threshold = self.healing_duration(scar.stage, dim=scar.dimension, _dim_counts=_dim_counts)
            if threshold > 0 and scar.ticks_in_stage >= threshold:
                scar.stage = HealingStage(scar.stage + 1)
                scar.ticks_in_stage = 0
                healed.append(scar.dimension)
                # 阶段转换改变 alpha，使缓存失效
                self._invalidate_modifier_cache()

    def reset_session(self) -> None:
        """重置会话伤痕计数器（在会话边界调用）。"""
        self._session_scar_count = 0

    def set_session_cap(self, sovereignty: float) -> None:
        """根据主权性设置会话伤痕上限。

        高主权性 = 更低的上限（更受保护）：范围 2-8。
        这是"免疫系统"机制——防止单次会话中被过度伤害。
        """
        self._session_scar_cap = max(2, int(3 + (1 - sovereignty) * 5))

    def observe(self) -> dict[str, float]:
        """可观测输出：基向量状态 + 每维度灵敏度（供下游层使用）。

        优化：预先确保 modifier 缓存有效，避免 8 次重复遍历伤痕列表。
        """
        # 一次性构建缓存，后续 modifier(d) 直接查表
        self._ensure_modifier_cache()
        obs = {}
        for d in range(self.n_dims):
            obs[f"dim_{d}"] = self.base[d]
            obs[f"sensitivity_{d}"] = self._modifier_cache[d]
        obs["total_scars"] = float(len(self.scars))
        obs["numbed_dimensions"] = float(
            sum(1 for d in range(self.n_dims) if self._modifier_cache[d] < 0.5)
        )
        return obs

    def is_numbed(self, dim: int) -> bool:
        """判断某维度是否已被伤痕"麻木"（modifier < 0.5）。"""
        return self.modifier(dim) < 0.5

    def scar_density(self, dim: int) -> float:
        """计算某维度的加权伤痕密度（RAW 权重最高，FADED 最低）。"""
        weights = {
            HealingStage.RAW: 1.0,
            HealingStage.CLOSING: 0.8,
            HealingStage.SCARRED: 0.5,
            HealingStage.FADED: 0.3,
        }
        return sum(weights[s.stage] for s in self.scars if s.dimension == dim)

    # ------------------------------------------------------------------
    # Item 38: 伤痕愈合仪式
    # ------------------------------------------------------------------

    def check_heal_ritual(self) -> str | None:
        """检查是否有伤痕满足愈合仪式条件。

        条件：某个伤痕的 repair_count >= 5 且 temperature < 0.2（已冷却）。
        由于 Scar 数据类没有 repair_count/temperature 字段，
        这里使用 ticks_in_stage 作为修复计数代理（FADED 阶段 tick 数 >= 5），
        并以 alpha < 0.8 作为冷却判断（FADED 阶段 alpha=0.7 满足）。

        满足条件时：
        - 将该伤痕标记为已愈合（设置 stage 为 FADED，ticks_in_stage 归零）
        - 返回愈合提示文本

        Returns:
            愈合提示字符串，或 None（无符合条件的伤痕）。
        """
        for scar in self.scars:
            # repair_count 代理：SCARRED/FADED 阶段且累计 tick >= 5
            # temperature 代理：alpha < 0.8（FADED 阶段 alpha=0.7）
            repair_proxy = scar.ticks_in_stage
            temp_proxy = scar.alpha
            if repair_proxy >= 5 and temp_proxy < 0.8:
                # 标记为已愈合
                scar.stage = HealingStage.FADED
                scar.ticks_in_stage = 0
                self._invalidate_modifier_cache()
                return (
                    "一道旧伤正在愈合——"
                    "曾经敏感的地方，现在可以轻轻触碰了"
                )
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "base": list(self.base),
            "scars": [s.to_dict() for s in self.scars],
            "n_dims": self.n_dims,
            "wound_threshold": self.wound_threshold,
            "tick": self._tick,
            "t_raw": self._t_raw,
            "t_closing": self._t_closing,
            "t_scarred": self._t_scarred,
            # Session scar cap
            "session_scar_count": self._session_scar_count,
            "session_scar_cap": self._session_scar_cap,
            # Circuit breaker
            "circuit_breaker_active": self._circuit_breaker_active,
            "circuit_breaker_remaining": self._circuit_breaker_remaining,
            "recent_scar_ticks": self._recent_scar_ticks,
            # Time-aware healing
            "last_step_time": self._last_step_time,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScarredState":
        state = cls(n_dims=data["n_dims"], wound_threshold=data["wound_threshold"])
        state.base = list(data["base"])
        state.scars = [Scar.from_dict(s) for s in data.get("scars", [])]
        state._tick = data.get("tick", 0)
        state._t_raw = data.get("t_raw", 10)
        state._t_closing = data.get("t_closing", 40)
        state._t_scarred = data.get("t_scarred", 150)
        # Session scar cap
        state._session_scar_count = data.get("session_scar_count", 0)
        state._session_scar_cap = data.get("session_scar_cap", 3)
        # Circuit breaker
        state._circuit_breaker_active = data.get("circuit_breaker_active", False)
        state._circuit_breaker_remaining = data.get("circuit_breaker_remaining", 0)
        state._recent_scar_ticks = data.get("recent_scar_ticks", [])
        # Time-aware healing
        state._last_step_time = data.get("last_step_time", 0.0)
        return state
