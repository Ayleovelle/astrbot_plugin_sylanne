"""EmotionLedger —— 情绪领域 agent（observer-ledger：带内生动力学，非瞬时函数）。

设计定位（详见 detailed-design §1.4 / D5）：
- 情绪不是"读 body 算一个数"的纯函数。EmotionLedger 独占一块【情绪动力学状态】：
  快/慢双 EMA（各自惯性、独立时间常数）+ 未表达情绪的积分态。同一串 body 输入、不同
  历史，会给出不同的 volatility/trend/drive——这正是 observer-ledger 的 agent 性所在。
- 它是 observer 而非 active agent：不直接产 Intent 抢话，只把"情绪现状(view)"和"想表达
  的冲动(drive)"投影出去，供能力 agent / 编排器消费。active 性集中在 Memory+Intention。

铁律对齐：
- 铁律1 真 agent：独占 _fast_ema/_slow_ema/_unexpressed/_unexpressed_since，是其唯一写者。
- 铁律2 无内部安全闸：urgency=_unexpressed **不封顶**，沉默积分无上限，表达只按 decay 衰减；
  归一化只在 Drive.normalized() 里临时算（仅供排序），绝不回写、绝不 clamp 真值。
- 铁律3 SDK 红线：只经 BodySnapshot 读 body（warmth/tension/repair_pressure），不下探 kernel。
- 铁律4 存档无损：to_dict/load_dict 容缺，缺字段保持现值，旧档无此领域=空起步不崩。
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque

from sylanne_alpha.v2core.contracts import (
    BeatContext,
    BodySnapshot,
    Phase,
    ReplyKind,
)

# ---------------------------------------------------------------------------
# 内生动力学常量（领域私有；时间常数是动力学参数，不是情感闸）
# ---------------------------------------------------------------------------
_FAST_ALPHA = 0.5          # 快 EMA 步长：对当下情绪反应灵敏（短时记忆）
_SLOW_ALPHA = 0.05         # 慢 EMA 步长：情绪基线惯性，慢漂移（长时基调）
_SAMPLES_MAXLEN = 32       # 近期采样窗（算 volatility 的样本池，容量管理非情感闸）
_UNEXPRESSED_DECAY = 0.4   # SPEAK 后未表达积分的保留系数（表达释放 60%）
_UNEXPRESSED_RATE = 1.0    # SILENT 时未表达积分的增益尺度（× 当下情绪强度）
_DRIVE_EPSILON = 1e-3      # 低于此视作"无积分/无冲动"（是零判定，非封顶）


# ===========================================================================
# 只读视图 / 冲动 —— 全部 frozen slots（投影出去即不可被外部改写）
# ===========================================================================

@dataclass(frozen=True, slots=True)
class DomainView:
    """领域 agent 对外只读投影的基类：至少带领域标识，便于编排器归类。"""

    domain: str


@dataclass(frozen=True, slots=True)
class EmotionView(DomainView):
    """情绪现状视图：valence/arousal/tension/warmth 投影自 body；volatility/trend 来自账本。

    前四个是"此刻 body 的情绪切面"（瞬时投影）；后两个是"账本看到的情绪动态"——
    volatility 是近期采样的离散度，trend 是快慢 EMA 的背离（正=近期较基线升温）。
    """

    valence: float = 0.0       # 效价：body.warmth 的符号化投影（正=正向）
    arousal: float = 0.0       # 唤起：tension/repair_pressure 的混合投影
    tension: float = 0.0       # 张力：body.tension 直投
    warmth: float = 0.0        # 温度：body.warmth 直投
    volatility: float = 0.0    # 波动：近期采样标准差（账本内生）
    trend: float = 0.0         # 趋势：fast_ema - slow_ema（账本内生，有符号）


@dataclass(frozen=True, slots=True)
class Drive:
    """领域 agent 的内生冲动。urgency **不封顶**——归一只为排序，不改真值（铁律2）。"""

    domain: str
    name: str
    urgency: float                  # 急迫度：原始积分值，无上限
    target: str | None = None       # 冲动指向的对象/语义提示（可空）
    since_turn: int | None = None   # 该冲动从哪一轮开始累积（可空）

    def normalized(self, scale: float = 1.0) -> float:
        """仅供编排器排序：把不封顶的 urgency 用 tanh 压到 [0,1)，**不回写**真值。"""
        if scale <= 0.0:
            return 0.0
        return math.tanh(max(0.0, self.urgency) / scale)


# ===========================================================================
# EmotionLedger —— 情绪领域 agent（独占动力学状态，单一写者）
# ===========================================================================

class EmotionLedger:
    """情绪 observer-ledger：维护快慢双 EMA 与未表达情绪积分，投影 view/drive。"""

    name = "emotion"

    __slots__ = (
        "_samples",            # Deque[float]：近期效价采样（算 volatility）
        "_fast_ema",           # float|None：快惯性（None=未播种）
        "_slow_ema",           # float|None：慢惯性/基线（None=未播种）
        "_unexpressed",        # float：未表达情绪积分态（不封顶）
        "_unexpressed_since",  # int|None：积分起始轮次
    )

    def __init__(self) -> None:
        self._samples: Deque[float] = deque(maxlen=_SAMPLES_MAXLEN)
        self._fast_ema: float | None = None
        self._slow_ema: float | None = None
        self._unexpressed: float = 0.0
        self._unexpressed_since: int | None = None

    # ---- 读接口（PERCEPT/DELIBERATE 拍只读，不写状态）----

    def view(self, body: BodySnapshot) -> EmotionView:
        """投影情绪现状：body 切面 + 账本内生量（纯只读，不改状态）。"""
        warmth = float(body.warmth)
        arousal = float(body.tension) * 0.6 + float(body.repair_pressure) * 0.4
        return EmotionView(
            domain=self.name,
            valence=warmth,
            arousal=arousal,
            tension=float(body.tension),
            warmth=warmth,
            volatility=self._volatility(),
            trend=self._trend(),
        )

    def drive(self, body: BodySnapshot) -> Drive | None:
        """表达冲动：urgency=未表达积分（不封顶）。积分≈0 时无冲动，返回 None。"""
        if self._unexpressed <= _DRIVE_EPSILON:
            return None
        # target 给下游一个语义提示：当下情绪偏暖还是偏紧（不影响 urgency 真值）
        target = "express_warmth" if float(body.warmth) >= 0.0 else "express_strain"
        return Drive(
            domain=self.name,
            name="expression",
            urgency=self._unexpressed,
            target=target,
            since_turn=self._unexpressed_since,
        )

    def hold_free_energy(self, body: BodySnapshot) -> float:
        """把未表达积分投影成 'hold（沉默）这一行动的代价'。

        纯只读、不动状态。消费者：IgnitionArbiter 比较 g_hold vs g_speak、
        OutreachCapability 的 reach 压力。不封顶（铁律②）；当下情绪强度作轻微调制
        （强度高时同样的积分更"难憋"），主体仍是 _unexpressed 本身。
        """
        if self._unexpressed <= _DRIVE_EPSILON:
            return 0.0
        return self._unexpressed * (1.0 + self._intensity(body))

    # 情绪温度的 7 级领域词（[-1,1] 单调；比通用 LEVELS7 更像"她"的语言）
    _WARMTH_WORDS = ("冰凉", "很凉", "微凉", "平平", "微暖", "很暖", "滚烫")
    _TENSION_WORDS = ("松弛", "松弛", "微紧", "有点紧", "偏紧", "很紧", "绷到极限")
    # 冷端行为指令——与 _WARMTH_WORDS 同长同索引，level_index 一次取两样（词-指令
    # 永不撕裂）。为什么只有冷端有指令（AUDIT-20260612-001 行为标定的实测结论）：
    # 暖端线索 LLM 天然服从（微暖 0.90 / 很暖 0.92，分离清晰），冷端三档被人设
    # "温柔底色"整体盖掉（冰凉 0.72 ≈ 平平 0.72，客观裁判无法区分）。状态词对下游
    # LLM 是可忽略的线索，行为表征才是可执行的指令——故只给实测失效的冷端加指令
    # 刚度；已验证生效的暖端与中性保持纯线索（过度指令反伤自然度）。
    _WARMTH_DIRECTIVES = (
        "（此刻心是凉的：回得短、淡，别主动关心，收起所有软语气词，可以敷衍）",  # 冰凉
        "（心口发凉：话比平时少、比平时淡，收起撒娇和热络）",                    # 很凉
        "（兴致不高：语气比平时收敛，少一点软和黏）",                            # 微凉
        "", "", "", "",                                                          # 平平→滚烫：纯线索
    )

    def prompt_line(self, body: BodySnapshot) -> str:
        """心象片段"情绪"行（纯模板，零-LLM，零数字）。

        三元组编码（precision-for-wording > 裸浮点）：
        ① 级别：温度/张力 7 级序数；② 方向：快慢 EMA 背离 → 在升温/降温；
        ③ 基线偏离：当下 vs 慢 EMA（她自己的惯常底色）→ 比平时暖/凉。
        冷端三档额外携带行为指令（_WARMTH_DIRECTIVES，同索引取——标定实测冷端
        状态词被人设底色盖掉，见词表旁注释）。消费者：fragment.build_mind_fragment。
        """
        from sylanne_alpha.v2core.verbal import level7, level_index, trend_word, vs_baseline

        v = self.view(body)
        w_idx = level_index(v.warmth, -1.0, 1.0, n=len(self._WARMTH_WORDS))
        bits = [f"情绪:{self._WARMTH_WORDS[w_idx]}"]
        directive = self._WARMTH_DIRECTIVES[w_idx]
        # ③ 基线偏离（双档）：相对她自己的慢基线（绝对值不说明事，偏离才是措辞信息）
        if self._slow_ema is not None:
            dev = vs_baseline(v.warmth, self._slow_ema, band=0.25,
                              above="比平时暖", below="比平时凉",
                              strong_band=0.55,
                              above_strong="比平时暖得多", below_strong="比平时凉得多")
            if dev:
                bits.append(dev)
        # ② 方向（双档：缓升/骤升对措辞是两种局面）
        tr = trend_word(v.trend, eps=0.08, up="在升温", down="在降温",
                        strong_eps=0.3, up_strong="骤然升温", down_strong="骤然降温")
        if tr:
            bits.append(tr)
        # 张力只在离开松弛区时占 token
        if v.tension >= 0.33:
            bits.append(f"张力{level7(v.tension, 0.0, 1.0, self._TENSION_WORDS)}")
        # 未表达积分：3 档定性
        if self._unexpressed > 2.0:
            bits.append("憋了很多话")
        elif self._unexpressed > 0.5:
            bits.append("有话憋着")
        line = "·".join(bits)
        # 冷端行为指令贴行尾（非状态位，不进"·"序列；暖端/中性 directive 为空串）
        return line + directive if directive else line

    # ---- 写接口（仅 EVOLVE 拍：采样推进动力学 + 据表达结果调未表达积分）----

    def ingest(self, ctx: BeatContext) -> None:
        """EVOLVE 拍唯一写入口：更新 EMA/采样，并据 render_outcome 调未表达积分。

        可塑性策略落点：慢 EMA（情绪基线）的步长 × narrative.plasticity_scale("warmth")
        ——固化越深，情绪基线越改不动（"越用越像她自己"），认知量不受影响。
        读其它领域的只读接口是允许的（写仍只发生在本域）。
        """
        assert ctx.phase is Phase.EVOLVE, "EmotionLedger.ingest 只能在 EVOLVE 拍调用"
        body = ctx.body
        plasticity = 1.0
        narrative = ctx.domain("narrative")
        if narrative is not None and hasattr(narrative, "plasticity_scale"):
            try:
                plasticity = float(narrative.plasticity_scale("warmth"))
            except Exception:
                plasticity = 1.0
        self._observe(body, plasticity)

        # P15：Renderer 已把本轮表达结论写进 scratch['render_outcome']（ReplyKind 或其字符串）。
        # 未知（缺省）时只采样、不动积分——不臆测 SPEAK/SILENT，避免虚增或虚泄。
        outcome = ctx.scratch.get("render_outcome")
        if outcome is None:
            return

        if self._is_speak(outcome):
            # 表达即释放：未表达积分按 decay 衰减；落回零判定即清空起始轮
            self._unexpressed *= _UNEXPRESSED_DECAY
            if self._unexpressed <= _DRIVE_EPSILON:
                self._unexpressed = 0.0
                self._unexpressed_since = None
        else:
            # 沉默：当下情绪强度越高（drive 高），未表达积分增得越多（× intensity，无封顶）
            gain = _UNEXPRESSED_RATE * self._intensity(body)
            if gain > 0.0:
                if self._unexpressed <= _DRIVE_EPSILON:
                    self._unexpressed_since = int(getattr(body, "turns", 0) or 0)
                self._unexpressed += gain

    # ---- 内生动力学私有计算 ----

    def _observe(self, body: BodySnapshot, plasticity: float = 1.0) -> None:
        """采样当下效价(warmth)，推进快慢双 EMA。

        快 EMA（当下反应）不受固化影响；慢 EMA（基线，"她是什么底色"）步长
        × plasticity——固化越深基线越稳（可塑性策略，认知/情感分离的情感侧落点）。
        """
        x = float(body.warmth)
        self._samples.append(x)
        if self._fast_ema is None or self._slow_ema is None:
            # 首次播种：快慢同起点，避免从 0 基线伪造 trend
            self._fast_ema = x
            self._slow_ema = x
        else:
            self._fast_ema += _FAST_ALPHA * (x - self._fast_ema)
            self._slow_ema += _SLOW_ALPHA * max(0.0, min(1.0, plasticity)) * (x - self._slow_ema)

    def _volatility(self) -> float:
        """近期采样的总体标准差；不足两点记 0。"""
        n = len(self._samples)
        if n < 2:
            return 0.0
        mean = sum(self._samples) / n
        var = sum((s - mean) ** 2 for s in self._samples) / n
        return math.sqrt(var)

    def _trend(self) -> float:
        """快慢 EMA 背离（有符号）：>0 近期较基线升温，<0 降温；未播种记 0。"""
        if self._fast_ema is None or self._slow_ema is None:
            return 0.0
        return self._fast_ema - self._slow_ema

    @staticmethod
    def _intensity(body: BodySnapshot) -> float:
        """当下情绪强度（'drive 高'的连续代理）：取效价幅度/张力/修复压力之最大。"""
        return max(
            abs(float(body.warmth)),
            float(body.tension),
            float(body.repair_pressure),
        )

    @staticmethod
    def _is_speak(outcome: Any) -> bool:
        """容错判定本轮是否真的说了话（兼容 ReplyKind 实例与其字符串值）。"""
        if isinstance(outcome, ReplyKind):
            return outcome is ReplyKind.SPEAK
        return str(outcome).lower() == ReplyKind.SPEAK.value

    # ---- 持久化（容缺：缺字段保持现值，旧档无此领域=空起步）----

    def to_dict(self) -> dict[str, Any]:
        return {
            "samples": list(self._samples),
            "fast_ema": self._fast_ema,
            "slow_ema": self._slow_ema,
            "unexpressed": self._unexpressed,
            "unexpressed_since": self._unexpressed_since,
        }

    def load_dict(self, data: dict[str, Any]) -> None:
        if not data:
            return
        raw = data.get("samples")
        if isinstance(raw, (list, tuple)):
            self._samples.clear()
            for v in list(raw)[-_SAMPLES_MAXLEN:]:
                try:
                    self._samples.append(float(v))
                except (TypeError, ValueError):
                    continue
        self._fast_ema = _opt_float(data.get("fast_ema"), self._fast_ema)
        self._slow_ema = _opt_float(data.get("slow_ema"), self._slow_ema)
        ue = _opt_float(data.get("unexpressed"), None)
        if ue is not None:
            self._unexpressed = ue
        us = data.get("unexpressed_since")
        if us is not None:
            try:
                self._unexpressed_since = int(us)
            except (TypeError, ValueError):
                pass


def _opt_float(v: Any, default: float | None) -> float | None:
    """容缺解析：None/不可解析时回落到 default（保持现值，不破坏存档）。"""
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


__all__ = ["DomainView", "EmotionView", "Drive", "EmotionLedger"]
