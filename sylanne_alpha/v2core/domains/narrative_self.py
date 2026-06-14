"""NarrativeSelfDomain —— 最慢的先验：连续自我（Fable 重做版）。

她"是谁"的慢变量层：自传锚点（只增）、关系纪元、情感固化度、人格基线慢漂。

与旧实现的关键差别（诚实修正）：
- 旧版镜像 body.epoch——但实测 SDK surface 根本不暴露纪元概念，那个字段恒 0，
  整条"随纪元固化"是死的。本版纪元【自持】：由真实经历里程碑推进——
  scar 每越过一个台阶（0.15/0.30/0.45/0.60/0.75）+1，自传锚点每攒满 16 条 +1。
  纪元 = 结构性伤痕台阶数 + 经历厚度台阶数，单调只增（A6 精神）。
- 固化的"岁月"分量改用锚点数（真实经历厚度），不再依赖死字段。

消费者清单（无死信号）：
- self_prior()/prompt_line() → 心象 prompt 片段（"自我"行，LLM 真的读到）
- plasticity_scale()         → EmotionLedger.ingest 的慢基线步长（可塑性策略真落点）
                               + 本域人格基线慢漂步长
- narrative_pe()/阈值        → ReconsolidationCapability 门控
- ingest 读 scratch["narrative_pe"] 登记锚点（Reconsolidation 写入）

铁律：①独占状态单一写者（写仅 EVOLVE）；③只读 BodySnapshot；
④load_dict 与旧档字段名兼容（anchors/epoch/ossification/baseline_traits）。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque

from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase
from sylanne_alpha.v2core.domains.emotion import DomainView

_ANCHORS_MAXLEN = 64           # 自传锚点上界（FIFO；纪元计数不受淘汰影响，见 _anchor_total）
_ANCHORS_PER_EPOCH = 16        # 每攒满 16 条锚点 → 纪元 +1（经历厚度台阶）
_SCAR_EPOCH_STEPS = (0.15, 0.30, 0.45, 0.60, 0.75)  # scar 台阶 → 各 +1 纪元
_BASELINE_HALFLIFE = 200.0     # 人格基线慢漂半衰期（轮）
_BASELINE_ALPHA = 0.693147 / _BASELINE_HALFLIFE
_NARR_PE_THRESHOLD = 0.5       # 叙事失配超此 → 登记锚点 + 开重固化窗口
_AFFECTIVE_DIMS = ("warmth", "tension", "repair_pressure")   # 情感域（会固化）


@dataclass(frozen=True, slots=True)
class Anchor:
    """自传锚点：一个高叙事失配时刻的索引（非原文，存档无损）。"""

    turn: int
    epoch: int
    narrative_pe: float
    valence: float
    note: str = ""


@dataclass(frozen=True, slots=True)
class SelfView(DomainView):
    """对外只读投影："我现在大体是谁"。"""

    epoch: int = 0
    sovereignty_tone: float = 1.0
    affective_rigidity: float = 0.0
    anchor_count: int = 0
    narrative_pe: float = 0.0
    baseline_traits: dict[str, float] = field(default_factory=dict)


class NarrativeSelfDomain:
    """连续自我领域 agent。读：self_prior/ossification/plasticity_scale；写仅 EVOLVE。"""

    name = "narrative"

    __slots__ = ("_anchors", "_epoch", "_ossification", "_baseline_traits",
                 "_anchor_total", "_scar_steps_crossed", "_last_dream_anchor_total")

    def __init__(self) -> None:
        self._anchors: Deque[Anchor] = deque(maxlen=_ANCHORS_MAXLEN)
        self._epoch: int = 0
        self._ossification: dict[str, float] = {d: 0.0 for d in _AFFECTIVE_DIMS}
        self._baseline_traits: dict[str, float] = {}
        self._anchor_total: int = 0          # 历史登记总数（不随 FIFO 淘汰减少）
        self._scar_steps_crossed: int = 0    # 已越过的 scar 台阶数（只增）
        self._last_dream_anchor_total: int = 0   # 上次成梦时的经历水位（梦境巩固守卫）

    # ---- 读接口（PERCEPT/DELIBERATE，纯只读）----

    def self_prior(self, body: BodySnapshot) -> SelfView:
        rigidity = (sum(self._ossification.values()) / len(self._ossification)
                    if self._ossification else 0.0)
        return SelfView(
            domain=self.name,
            epoch=self._epoch,
            sovereignty_tone=float(body.sovereignty),
            affective_rigidity=rigidity,
            anchor_count=len(self._anchors),
            narrative_pe=0.0,
            baseline_traits=dict(self._baseline_traits),
        )

    def ossification(self, dim: str) -> float:
        return self._ossification.get(dim, 0.0)

    def plasticity_scale(self, dim: str) -> float:
        """情感维学习幅度乘子 = 1−固化度；认知维恒 1.0（终生可塑）。

        消费者：EmotionLedger.ingest（慢基线步长）+ 本域基线慢漂步长。
        """
        if dim not in self._ossification:
            return 1.0
        return max(0.0, 1.0 - self._ossification[dim])

    def narrative_pe(self, recalled_emotion: float, body: BodySnapshot) -> float:
        """召回记忆情绪 vs 当下情绪的失配（派生量，不重算 SDK）。"""
        return abs(float(recalled_emotion) - float(body.warmth))

    @property
    def reconsolidation_threshold(self) -> float:
        return _NARR_PE_THRESHOLD

    def prompt_line(self) -> str:
        """心象片段"自我"行（纯模板，零-LLM）。"""
        rigidity = (sum(self._ossification.values()) / len(self._ossification)
                    if self._ossification else 0.0)
        if rigidity >= 0.6:
            shape = "性子基本定了"
        elif rigidity >= 0.3:
            shape = "性子在慢慢成形"
        else:
            shape = "还在被经历塑形"
        return f"自我:纪元{self._epoch}·{shape}·经历{self._anchor_total}枚"

    # ---- 写接口（仅 EVOLVE，单一写者）----

    def ingest(self, ctx: BeatContext) -> None:
        """EVOLVE 唯一写：推进纪元/固化/基线；高叙事失配登记锚点（只增）。"""
        assert ctx.phase is Phase.EVOLVE, "NarrativeSelfDomain.ingest 只能在 EVOLVE 拍调用"
        body = ctx.body
        scar = float(body.scar)

        # —— 纪元推进（自持里程碑，不依赖 SDK 未暴露的字段）——
        steps_now = sum(1 for th in _SCAR_EPOCH_STEPS if scar >= th)
        if steps_now > self._scar_steps_crossed:
            self._epoch += steps_now - self._scar_steps_crossed
            self._scar_steps_crossed = steps_now

        # —— 固化度推进：scar（结构性伤痕）+ 经历厚度（锚点数），只增不减（A6）——
        experience_age = min(0.5, self._anchor_total * 0.01)
        for d in _AFFECTIVE_DIMS:
            target = min(0.95, scar + experience_age)
            self._ossification[d] = max(self._ossification[d], target)

        # —— 人格基线慢漂（半衰期~200轮），固化维漂得更慢（可塑性策略落点）——
        for k, v in (body.personality or {}).items():
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            cur = self._baseline_traits.get(k, fv)
            alpha = _BASELINE_ALPHA * self.plasticity_scale(k)
            self._baseline_traits[k] = (1 - alpha) * cur + alpha * fv

        # —— 锚点登记（Reconsolidation 写入 scratch["narrative_pe"]）——
        npe = float(ctx.scratch.get("narrative_pe", 0.0) or 0.0)
        if npe >= _NARR_PE_THRESHOLD:
            self._anchors.append(Anchor(
                turn=int(body.turns), epoch=self._epoch, narrative_pe=npe,
                valence=float(body.warmth),
                note=str(ctx.scratch.get("narrative_note", "") or "")[:40],
            ))
            self._anchor_total += 1
            if self._anchor_total % _ANCHORS_PER_EPOCH == 0:
                self._epoch += 1

    # ---- 梦境巩固写接口（2.2.0-a；深睡拍经 v2core.dream 调用，零 LLM）----

    def register_dream(self, note: str) -> bool:
        """深睡成梦：把"今天"压成一枚"梦:"锚点写进自传。

        守卫：自上次梦以来 anchor_total 无增量 → 无梦返回 False——没有新经历的
        夜晚不值得伪造一个梦（梦是对白天的巩固，不是日历事件）。
        梦锚点【不计入】_anchor_total：纪元厚度只算清醒经历，否则每天一梦
        十六天白涨一纪元——成长不能靠睡觉刷出来。
        单一写者纪律：本方法是域自己的写接口（与 ingest 同级），调用方仅深睡拍。
        """
        if self._anchor_total <= self._last_dream_anchor_total:
            return False
        last_turn = self._anchors[-1].turn if self._anchors else 0
        text = ("梦:" + (note.strip() if note and note.strip() else "无言的一夜"))[:40]
        self._anchors.append(Anchor(
            turn=last_turn, epoch=self._epoch,
            narrative_pe=0.0, valence=0.0, note=text,
        ))
        self._last_dream_anchor_total = self._anchor_total
        return True

    # ---- 持久化（旧档字段名兼容 + 新字段容缺，铁律④）----

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchors": [{"turn": a.turn, "epoch": a.epoch, "narrative_pe": a.narrative_pe,
                         "valence": a.valence, "note": a.note} for a in self._anchors],
            "epoch": self._epoch,
            "ossification": dict(self._ossification),
            "baseline_traits": dict(self._baseline_traits),
            "anchor_total": self._anchor_total,
            "scar_steps_crossed": self._scar_steps_crossed,
            "last_dream_anchor_total": self._last_dream_anchor_total,
        }

    def load_dict(self, data: dict[str, Any]) -> None:
        if not data:
            return
        anchors = data.get("anchors")
        if isinstance(anchors, list):
            self._anchors = deque(
                (Anchor(turn=int(a.get("turn", 0)), epoch=int(a.get("epoch", 0)),
                        narrative_pe=float(a.get("narrative_pe", 0.0)),
                        valence=float(a.get("valence", 0.0)), note=str(a.get("note", "")))
                 for a in anchors if isinstance(a, dict)),
                maxlen=_ANCHORS_MAXLEN,
            )
        if "epoch" in data:
            try:
                self._epoch = int(data["epoch"])
            except (TypeError, ValueError):
                pass
        oss = data.get("ossification")
        if isinstance(oss, dict):
            for d in _AFFECTIVE_DIMS:
                if d in oss:
                    try:
                        self._ossification[d] = float(oss[d])
                    except (TypeError, ValueError):
                        pass
        bt = data.get("baseline_traits")
        if isinstance(bt, dict):
            cleaned: dict[str, float] = {}
            for k, v in bt.items():
                try:
                    cleaned[str(k)] = float(v)
                except (TypeError, ValueError):
                    continue
            self._baseline_traits = cleaned
        # 新字段容缺：旧档没有 → 从可见状态保守推断。推断只数【清醒经历】锚
        # （"梦:"锚不计经历厚度——见 register_dream；混进推断会让守卫水位错位，
        # 重启后同一晚的梦重复做）。旧档无梦锚时与原推断逐位等价。
        lived = sum(1 for a in self._anchors if not a.note.startswith("梦:"))
        try:
            self._anchor_total = max(int(data.get("anchor_total", 0)), lived)
        except (TypeError, ValueError):
            self._anchor_total = lived
        try:
            self._scar_steps_crossed = max(0, int(data.get("scar_steps_crossed", 0)))
        except (TypeError, ValueError):
            self._scar_steps_crossed = 0
        try:
            self._last_dream_anchor_total = max(0, int(data.get("last_dream_anchor_total", 0)))
        except (TypeError, ValueError):
            self._last_dream_anchor_total = 0


__all__ = ["Anchor", "SelfView", "NarrativeSelfDomain"]
