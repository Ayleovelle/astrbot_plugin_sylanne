"""Sylanne-Embodiment 计算核心层：预测编码门控（Predictive Coding Gate）。

在 7 层计算栈中的位置：L2 门控层。
职责：维护对下一条输入的预测向量，通过计算"惊讶度"（预测误差）来决定消息的计算路径：
  - 低惊讶 → fast path（仅轻量计算）
  - 中惊讶 → normal path（中等计算）
  - 高惊讶 → full path（全栈计算：HDC + VoidScar + HGT + 自创生检查）

核心思想来自 Karl Friston 的自由能原理：系统持续预测输入，预测误差驱动计算资源分配。
"""

from __future__ import annotations

import random
from typing import Any


class PredictiveCodingGate:
    """预测编码门控器。

    维护一个对下一条输入的预测向量（二进制超向量），通过计算预测误差（惊讶度）
    来决定消息应走哪条计算路径。

    与其他组件的关系：
      - 接收 L1 HDCEncoder 的输出作为输入
      - 输出路由决策（fast/normal/full）给 ComputationSpine 调度
      - 惊讶度值传递给 L3 VoidScarEngine 和 L5 HGT

    核心机制：
      - surprise(): 计算 Hamming 距离作为预测误差
      - update(): 通过概率性位翻转将预测向量向输入靠拢
      - route(): 根据惊讶度决定计算路径
    """

    __slots__ = (
        "dim",
        "_byte_dim",
        "_prediction",
        "precision",
        "decay",
        "_surprise_history",
        "_fast_threshold",
        "_full_threshold",
        "_rng",
    )

    def __init__(self, dim: int = 1024, decay: float = 0.92):
        """初始化预测编码门控器。

        Args:
            dim: 超向量维度（位数），必须是 8 的倍数
            decay: 精度衰减因子，控制精度更新的惯性（越大越保守）
        """
        self.dim = dim
        self._byte_dim = dim // 8
        self._prediction = bytearray(self._byte_dim)  # 完整预测向量（初始全零）
        self.precision = 0.5  # 预测精度（高精度 = 对惊讶更敏感）
        self.decay = decay
        self._surprise_history: list[float] = []
        self._fast_threshold = 0.15  # 低于此值走 fast path
        self._full_threshold = 0.45  # 高于此值走 full path
        self._rng: random.Random = random.Random(42)  # 确定性随机源

    def surprise(self, input_vec: bytearray | list[int]) -> float:
        """计算惊讶度：预测向量与实际输入之间的 Hamming 距离。

        Args:
            input_vec: 输入向量（bytearray 格式的 HDC 向量，或 list[int] 的密度表示）

        Returns:
            归一化惊讶度 [0.0, 1.0]，受 precision 调制
        """
        if not input_vec:
            return 0.0
        if isinstance(input_vec, bytearray):
            # 逐字节 XOR 后统计 1 的个数 = Hamming 距离
            xor_count = sum(
                (a ^ b).bit_count() for a, b in zip(input_vec, self._prediction)
            )
            raw = xor_count / self.dim
        else:
            # 回退路径：对 list[int] 输入使用密度差异近似惊讶度
            density = sum(input_vec) / len(input_vec)
            pred_ones = sum(b.bit_count() for b in self._prediction)
            pred_density = pred_ones / self.dim
            raw = abs(density - pred_density)
        # precision 放大惊讶度：高精度时对微小差异更敏感
        return min(1.0, raw * self.precision * 2.0)

    def update(self, input_vec: bytearray | list[int], surprise_value: float):
        """更新预测向量：通过概率性位翻转向输入靠拢。

        学习率与惊讶度正相关：高惊讶 → 更大的更新步长（因为预测明显错了）。
        同时更新 precision（预测精度）：低惊讶 → 精度上升，高惊讶 → 精度下降。

        Args:
            input_vec: 当前输入向量
            surprise_value: 本次计算的惊讶度
        """
        # 学习率：惊讶越大更新越快，但 clamp 在 [0.01, 0.3] 防止过激
        lr = min(0.3, max(0.01, surprise_value * 0.5))
        if isinstance(input_vec, bytearray):
            # 逐位概率翻转：只翻转预测与输入不同的位，翻转概率 = lr
            for i in range(min(len(input_vec), self._byte_dim)):
                diff = self._prediction[i] ^ input_vec[i]
                if diff:
                    mask = 0
                    for bit in range(8):
                        if (diff >> bit) & 1:
                            if self._rng.random() < lr:
                                mask |= 1 << bit
                    self._prediction[i] ^= mask
        else:
            # 回退路径：对 list[int] 输入按密度方向概率性翻转位
            density = sum(input_vec) / max(1, len(input_vec))
            # Set prediction bits to match target density probabilistically
            target_ones = int(density * self.dim)
            current_ones = sum(b.bit_count() for b in self._prediction)
            # Nudge toward target by flipping random bits
            if current_ones < target_ones:
                for i in range(self._byte_dim):
                    for bit in range(8):
                        if (
                            not (self._prediction[i] & (1 << bit))
                            and self._rng.random() < lr * 0.1
                        ):
                            self._prediction[i] |= 1 << bit
            elif current_ones > target_ones:
                for i in range(self._byte_dim):
                    for bit in range(8):
                        if (
                            self._prediction[i] & (1 << bit)
                        ) and self._rng.random() < lr * 0.1:
                            self._prediction[i] &= ~(1 << bit)
        # 更新精度：指数移动平均，低惊讶 → 精度上升（预测越来越准）
        self.precision = self.decay * self.precision + (1 - self.decay) * (
            1.0 - surprise_value
        )
        # clamp 精度到 [0.1, 1.0]，防止精度归零导致系统失灵
        self.precision = max(0.1, min(1.0, self.precision))
        self._surprise_history.append(surprise_value)
        # 只保留最近 50 条历史，用于冷启动检测和诊断
        if len(self._surprise_history) > 50:
            self._surprise_history = self._surprise_history[-50:]

    def route(self, surprise_value: float) -> str:
        """根据惊讶度决定计算路径。

        冷启动保护：前 15 条消息内预测模型未校准，惊讶值不可靠，
        最高只路由到 "normal" 以避免在噪声上浪费全栈计算。

        Args:
            surprise_value: 当前惊讶度

        Returns:
            "fast" | "normal" | "full" 三种路径之一
        """
        if surprise_value < self._fast_threshold:
            return "fast"  # 仅 SSM 轻量路径，跳过重计算
        if surprise_value < self._full_threshold:
            return "normal"  # SSM + 轻量注意力
        # 冷启动保护：预测模型需要约 15 个样本才能校准
        if len(self._surprise_history) < 15:
            return "normal"
        return "full"  # 全栈：SSM + TDA + HDC 召回 + 自创生检查

    def mean_surprise(self) -> float:
        """返回历史惊讶度的滑动平均值（用于诊断和自适应）。"""
        if not self._surprise_history:
            return 0.5
        return sum(self._surprise_history) / len(self._surprise_history)

    def set_route_thresholds(self, fast_threshold: float, full_threshold: float):
        self._fast_threshold = fast_threshold
        self._full_threshold = full_threshold

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典，用于持久化存储。"""
        import base64

        return {
            "decay": self.decay,
            "precision": self.precision,
            "prediction": base64.b64encode(bytes(self._prediction)).decode("ascii"),
            "surprise_history": list(self._surprise_history),
            "mean_surprise": self.mean_surprise(),
            "history_len": len(self._surprise_history),
        }

    def from_dict(self, data: dict[str, Any]):
        """从持久化状态恢复。"""
        import base64

        self.decay = float(data.get("decay", self.decay))
        self.precision = float(data.get("precision", 0.5))
        # Support new format (full prediction vector)
        if "prediction" in data:
            self._prediction = bytearray(base64.b64decode(data["prediction"]))
        elif "prediction_density" in data:
            # Legacy fallback: initialize prediction from density
            density = float(data["prediction_density"])
            target_ones = int(density * self.dim)
            self._prediction = bytearray(self._byte_dim)
            # Set bits to approximate the old density
            bits_set = 0
            for i in range(self._byte_dim):
                for bit in range(8):
                    if bits_set < target_ones:
                        self._prediction[i] |= 1 << bit
                        bits_set += 1
        history = data.get("surprise_history")
        if isinstance(history, list):
            self._surprise_history = [float(x) for x in history[-50:]]
