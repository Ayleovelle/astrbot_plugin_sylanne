"""DistillationDomain —— L3 学生编码器：文本 → 体感的廉价线性逼近（Fable 重做版）。

诚实定位（不过度包装）：8 特征 NLMS 在线线性回归（Haykin《Adaptive Filter Theory》）。
teacher = SDK 计算核每轮真实算出的 body 维度（warmth/tension/repair_pressure/surprise，
经 BodySnapshot 只读取得）；student = 线性映射 w·feats。它在学"这类文本通常会让我的
身体怎么动"。精神上呼应蒸馏/摊还推断，形式上不是 soft-label 蒸馏，不宣称等同。

与旧版的关键差别：
- 特征统一来自 lexicon.distill_features()（全内核唯一观测模型；维序与旧档权重一致，
  旧档可直接加载，铁律④）。
- 砍掉了"跳 LLM 迭代"门控——那个信号在旧实现里没有任何真实消费者（升级 LLM 精理解
  的路径根本不存在），是装饰。本版蒸馏的【真实消费者】是 AppraisalCapability：
  atypicality(text, body) = 学生预测 vs 本轮真实体感的失配。学得越好，这个量越能
  回答"这条消息对我的触动是不是反常"——异常触动是评价层的 novelty 证据之一。

铁律：①独占权重单一写者（写仅 EVOLVE）；③teacher 只经 BodySnapshot；④容缺加载。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase
from sylanne_alpha.v2core.domains.emotion import DomainView
from sylanne_alpha.v2core.lexicon import N_DISTILL_FEATURES, distill_features

_TARGET_DIMS = ("warmth", "tension", "repair_pressure", "surprise")
_TARGET_BOUNDS = {
    "warmth": (-1.0, 1.0),
    "tension": (0.0, 1.0),
    "repair_pressure": (0.0, 1.0),
    "surprise": (0.0, 1.0),
}
_LR_BASE = 0.3          # NLMS 步长 μ；归一化后与特征量级无关
_NLMS_EPS = 1.0         # 归一化分母正则
_W_CLIP = 8.0           # 权重裁剪（数值保险，正常不触发）
_ERR_ALPHA = 0.1        # 误差 EMA
_FIDELITY_WARMUP = 12   # 样本数不足时保真度压低（没学够别信）


@dataclass(frozen=True, slots=True)
class DistilledPrior(DomainView):
    """对外只读投影：对本条文本的体感预测 + 保真度。"""

    predicted: dict[str, float] = field(default_factory=dict)
    fidelity: float = 0.0
    samples: int = 0
    last_error: float = 1.0


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else (hi if v > hi else v)


def _dot(w: list[float], feats: list[float]) -> float:
    return sum(wi * fi for wi, fi in zip(w, feats))


class DistillationDomain:
    """L3 学生编码器领域 agent。读：predict/fidelity/atypicality；写仅 EVOLVE。"""

    name = "distill"

    __slots__ = ("_w", "_err_ema", "_samples")

    def __init__(self) -> None:
        self._w: dict[str, list[float]] = {d: [0.0] * N_DISTILL_FEATURES for d in _TARGET_DIMS}
        self._err_ema: dict[str, float] = {d: 1.0 for d in _TARGET_DIMS}
        self._samples: int = 0

    # ---- 读接口（PERCEPT/DELIBERATE，纯只读）----

    def predict(self, text: str) -> DistilledPrior:
        feats = distill_features(text)
        predicted: dict[str, float] = {}
        for d in _TARGET_DIMS:
            lo, hi = _TARGET_BOUNDS[d]
            predicted[d] = _clamp(_dot(self._w[d], feats), lo, hi)
        return DistilledPrior(
            domain=self.name,
            predicted=predicted,
            fidelity=self.fidelity(),
            samples=self._samples,
            last_error=sum(self._err_ema.values()) / len(self._err_ema),
        )

    def fidelity(self) -> float:
        """整体保真度 [0,1]：样本够 + 误差低 → 高。warmup 内压低，冷启动不可信。"""
        warmup = min(1.0, self._samples / float(_FIDELITY_WARMUP))
        mean_err = sum(self._err_ema.values()) / len(self._err_ema)
        return warmup * (1.0 / (1.0 + mean_err))

    def atypicality(self, text: str, body: BodySnapshot) -> float:
        """本轮触动的反常度 ∈ [0,1]·fidelity：学生预测 vs 真实体感的平均失配 × 保真度。

        唯一消费者：AppraisalCapability 的 novelty 证据（"这条消息对我的触动不寻常"）。
        保真度乘进去 = 冷启动时该信号自动趋零（没学够就不发言）。
        """
        fid = self.fidelity()
        if fid <= 0.0:
            return 0.0
        feats = distill_features(text)
        err = 0.0
        for d in _TARGET_DIMS:
            lo, hi = _TARGET_BOUNDS[d]
            pred = _clamp(_dot(self._w[d], feats), lo, hi)
            err += abs(float(getattr(body, d, 0.0)) - pred) / (hi - lo)
        return (err / len(_TARGET_DIMS)) * fid

    # ---- 写接口（仅 EVOLVE，单一写者）----

    def ingest(self, ctx: BeatContext) -> None:
        """EVOLVE 唯一写：以本轮真实 body 维为 teacher，surprise 加权 NLMS 在线纠偏。"""
        assert ctx.phase is Phase.EVOLVE, "DistillationDomain.ingest 只能在 EVOLVE 拍调用"
        body = ctx.body
        text = ctx.text or ""
        if not text:
            return  # 空文本轮（空闲/主动）无监督信号
        feats = distill_features(text)
        surprise = _clamp(float(body.surprise), 0.0, 1.0)
        mu = _LR_BASE * (0.5 + surprise)
        energy = sum(f * f for f in feats) + _NLMS_EPS
        for d in _TARGET_DIMS:
            target = float(getattr(body, d, 0.0))
            pred = _dot(self._w[d], feats)
            err = target - pred
            step = mu * err / energy
            for i in range(N_DISTILL_FEATURES):
                self._w[d][i] = _clamp(self._w[d][i] + step * feats[i], -_W_CLIP, _W_CLIP)
            self._err_ema[d] = (1 - _ERR_ALPHA) * self._err_ema[d] + _ERR_ALPHA * abs(err)
        self._samples += 1

    # ---- 持久化（与旧档键名/维序一致，容缺，铁律④）----

    def to_dict(self) -> dict[str, Any]:
        return {
            "w": {d: list(self._w[d]) for d in _TARGET_DIMS},
            "err_ema": dict(self._err_ema),
            "samples": self._samples,
        }

    def load_dict(self, data: dict[str, Any]) -> None:
        if not data:
            return
        w = data.get("w")
        if isinstance(w, dict):
            for d in _TARGET_DIMS:
                row = w.get(d)
                if isinstance(row, list) and len(row) == N_DISTILL_FEATURES:
                    try:
                        self._w[d] = [_clamp(float(x), -_W_CLIP, _W_CLIP) for x in row]
                    except (TypeError, ValueError):
                        pass
        e = data.get("err_ema")
        if isinstance(e, dict):
            for d in _TARGET_DIMS:
                if d in e:
                    try:
                        self._err_ema[d] = float(e[d])
                    except (TypeError, ValueError):
                        pass
        try:
            self._samples = max(0, int(data.get("samples", 0)))
        except (TypeError, ValueError):
            self._samples = 0


__all__ = ["DistilledPrior", "DistillationDomain"]
