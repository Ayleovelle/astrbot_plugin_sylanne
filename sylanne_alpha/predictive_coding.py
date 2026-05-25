"""Sylanne-Embodiment computation layer: Predictive Coding gate.

Maintains a prediction of the next input and routes messages based on
surprise (prediction error). Low surprise → fast path, high surprise → full path.
"""

from __future__ import annotations

from typing import Any


class PredictiveCodingGate:
    __slots__ = (
        "dim",
        "_byte_dim",
        "_prediction",
        "precision",
        "decay",
        "_surprise_history",
        "_fast_threshold",
        "_full_threshold",
    )

    def __init__(self, dim: int = 1024, decay: float = 0.92):
        self.dim = dim
        self._byte_dim = dim // 8
        self._prediction = bytearray(self._byte_dim)  # Full prediction vector
        self.precision = 0.5
        self.decay = decay
        self._surprise_history: list[float] = []
        self._fast_threshold = 0.15
        self._full_threshold = 0.45

    def surprise(self, input_vec: bytearray | list[int]) -> float:
        """Compute surprise as Hamming distance between prediction and input."""
        if not input_vec:
            return 0.0
        if isinstance(input_vec, bytearray):
            # Hamming distance between prediction and input
            xor_count = sum(
                bin(a ^ b).count("1") for a, b in zip(input_vec, self._prediction)
            )
            raw = xor_count / self.dim
        else:
            # Fallback for list[int] inputs: use density difference
            density = sum(input_vec) / len(input_vec)
            pred_ones = sum(bin(b).count("1") for b in self._prediction)
            pred_density = pred_ones / self.dim
            raw = abs(density - pred_density)
        return min(1.0, raw * self.precision * 2.0)

    def update(self, input_vec: bytearray | list[int], surprise_value: float):
        """Update prediction vector toward input using probabilistic bit flipping."""
        import random

        lr = min(0.3, max(0.01, surprise_value * 0.5))
        if isinstance(input_vec, bytearray):
            # Blend prediction toward input: flip differing bits with probability lr
            for i in range(min(len(input_vec), self._byte_dim)):
                diff = self._prediction[i] ^ input_vec[i]
                if diff:
                    mask = 0
                    for bit in range(8):
                        if (diff >> bit) & 1:
                            if random.random() < lr:
                                mask |= 1 << bit
                    self._prediction[i] ^= mask
        else:
            # Fallback for list[int]: update prediction density-wise
            density = sum(input_vec) / max(1, len(input_vec))
            # Set prediction bits to match target density probabilistically
            target_ones = int(density * self.dim)
            current_ones = sum(bin(b).count("1") for b in self._prediction)
            # Nudge toward target by flipping random bits
            if current_ones < target_ones:
                for i in range(self._byte_dim):
                    for bit in range(8):
                        if (
                            not (self._prediction[i] & (1 << bit))
                            and random.random() < lr * 0.1
                        ):
                            self._prediction[i] |= 1 << bit
            elif current_ones > target_ones:
                for i in range(self._byte_dim):
                    for bit in range(8):
                        if (
                            self._prediction[i] & (1 << bit)
                        ) and random.random() < lr * 0.1:
                            self._prediction[i] &= ~(1 << bit)
        # Update precision
        self.precision = self.decay * self.precision + (1 - self.decay) * (
            1.0 - surprise_value
        )
        self.precision = max(0.1, min(1.0, self.precision))
        self._surprise_history.append(surprise_value)
        if len(self._surprise_history) > 50:
            self._surprise_history = self._surprise_history[-50:]

    def route(self, surprise_value: float) -> str:
        """Decide computation path based on surprise level.

        During cold start (first 15 messages), the prediction model is
        uncalibrated so surprise values are unreliable. Cap routing at
        "normal" to avoid wasting full-path computation on noise.
        """
        if surprise_value < self._fast_threshold:
            return "fast"  # SSM only, skip heavy computation
        if surprise_value < self._full_threshold:
            return "normal"  # SSM + tiny attention
        # Cold start guard: prediction model needs ~15 samples to calibrate
        if len(self._surprise_history) < 15:
            return "normal"
        return "full"  # Full stack: SSM + TDA + HDC recall + autopoiesis check

    def mean_surprise(self) -> float:
        """Running average surprise (useful for diagnostics)."""
        if not self._surprise_history:
            return 0.5
        return sum(self._surprise_history) / len(self._surprise_history)

    def set_route_thresholds(self, fast_threshold: float, full_threshold: float):
        self._fast_threshold = fast_threshold
        self._full_threshold = full_threshold

    def to_dict(self) -> dict[str, Any]:
        """Serialize for persistence."""
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
        """Restore from persisted state."""
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
