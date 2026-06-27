"""v2core 核心契约：所有跨层类型的单一真相源。

这里只放【数据类型 + 协议接口】，不放任何实现。三层（Body / 领域 agent / 能力 agent）
和编排器都依赖本模块，但本模块不依赖任何它们——保证依赖单向、无环。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

# #29 进化偏置喂回 live 门控时的二次硬钳位：live 门控见到的学习偏置绝不超过 ±此值，
# 保证"人格显函数是主项、学习只微调"。比 EvolutionStore 总 cap(0.20)更紧，是 gate 侧
# 的最后一道刹车（即使上游 cap 将来调整也兜得住）。
_EVO_BIAS_CAP = 0.15


# ===========================================================================
# 相位（主链三拍）—— 控制流节律，不是边界、不是子系统（辩论收敛结论）
# ===========================================================================

class Phase(str, Enum):
    """主链认知周期的三拍。能力 agent 注册到某一拍的能力槽。

    PERCEPT    — 知觉：只读 BodySnapshot + 领域 agent 接口，抽取信号。并发安全。
    DELIBERATE — 审议：决定怎么回应（召回/措辞/共情…）。热路径，受 budget_ms 约束。
    EVOLVE     — 进化：唯一写相位。集中提交对领域 agent 的写（情绪漂移/人格 append）。
    """

    PERCEPT = "percept"
    DELIBERATE = "deliberate"
    EVOLVE = "evolve"


# ===========================================================================
# BodySnapshot —— SDK 计算核 observe() 的只读快照（类型化，替代裸 dict 穿透）
# ===========================================================================

@dataclass(frozen=True, slots=True)
class BodySnapshot:
    """Body(SDK) 在某一 tick 的不可变只读快照。

    所有 agent 吃的是这个类型化对象，而不是旧架构里 surface()['host_payload'] 那种
    字符串键的裸 dict（消除 hp.get('personality',{}).get('traits',{}) 式脆弱穿透）。

    字段是 SDK surface 的提炼投影；新增字段时在这里显式扩展，agent 才能类型安全地读。
    """

    session_key: str
    turns: int
    # —— 情绪/生理（来自 hot_pool / void-scar）——
    warmth: float = 0.0          # 温度 [-1,1]，正=温暖
    tension: float = 0.0         # 张力/压力 [0,1]
    repair_pressure: float = 0.0  # 修复压力 [0,1]
    # —— 关系（来自 relational_sheaf / 人格）——
    intimacy_gravity: float = 0.5  # 关系引力/亲密度 [0,1]
    # —— 人格向量（Big Five / Embodiment Five），只读 ——
    personality: dict[str, float] = field(default_factory=dict)
    # ═══ 2.1.0 认知科学根基扩展（Phase A 地基；详见 docs/sylanne-2.1.0-cognitive-architecture.md）═══
    # 主动推断 canonical PE（理论1，唯一来源 kernel.computation；四模块派生不重算）
    surprise: float = 0.0          # 本 tick 预测误差 [0,1]（Friston 2017）
    mean_surprise: float = 0.5     # 滑动均值基线
    precision: float = 0.5         # 注意增益（Feldman&Friston 2013；=0.3+neuroticism*0.5）
    # 躯体标记（理论5，Damasio 1996；body.* 真实路径）
    scar: float = 0.0              # 不可逆伤疤（A6，只增）
    strain: float = 0.0            # 张力/拉伤（body.pulse.strain）
    sovereignty: float = 1.0       # 主权（body.immunity.sovereignty）
    exhaustion: float = 0.0        # 耗竭（body.mortality.exhaustion）
    expression_drive: float = 0.0  # 表达驱力（affect_dynamics.body_coupling）
    # 叙事自我（理论6，Conway 2000 / Nader 2000 重固化）
    threshold_drift: float = 0.0   # 阈值漂移（body.nerve.threshold_drift）
    epoch: int = 0                 # 关系纪元（情感域固化程度 age_decay 来源）
    # ═══ Wave 3 缺陷行为层所需信号（2026-06-24；SDK 真实路径，仅 body_port_v2 适配器投影）═══
    # 这些 SDK 早已在算，但此前未投影进 BodySnapshot，fragment 读不到 → 缺陷行为触发不了。
    void_pressure: float = 0.0     # 空腔压力（VoidScarEngine；冲动泄露/示弱道歉/逃避 触发）
    load: float = 0.0              # 负荷（body.mortality.load；犯懒 触发）
    plasticity: float = 0.5        # 可塑性（body.nerve.plasticity；低=过滤差→冲动 触发；中性默认 0.5）
    boundary_pressure: float = 0.0 # 边界压力（body.immunity.boundary_pressure；吃醋 触发）
    # —— 原始 surface（逃生舱：迁移期暂存完整 dict，迁移完成后逐步收窄到具名字段）——
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def trait(self, name: str, default: float = 0.5) -> float:
        """安全读人格维度，缺失给中性默认。"""
        v = self.personality.get(name, default)
        try:
            return float(v)
        except (TypeError, ValueError):
            return default


# ===========================================================================
# Intent —— agent 之间传递的显式意图（保留旧设计里这个好东西）
# ===========================================================================

@dataclass(slots=True)
class Intent:
    """能力 agent 产出的意图贡献。由编排器在拍内收集、融合。

    不可让 agent 直接改别人的状态——所有跨 agent 影响都经由 Intent 显式表达，
    再由 EVOLVE 拍的单一写者落地。这是杜绝上帝对象反向穿透的核心纪律。
    """

    source: str                              # 产出此意图的能力 agent 名
    # 高层结构化负载（如召回到的记忆、共情线索），SDK 吃不下、供 prompt 注入/下游消费
    payload: dict[str, Any] = field(default_factory=dict)
    # 喂回 SDK 计算的情绪/信号贡献（按 priority 加权融合）
    affect: dict[str, float] = field(default_factory=dict)
    priority: float = 0.5                    # 融合权重 [0,1]
    confidence: float | None = None          # 该意图的置信，None=不表态
    flags: tuple[str, ...] = ()              # 给 SDK event 的标志位


@dataclass(slots=True)
class BeatContext:
    """一轮（一条用户消息）的可变上下文，贯穿三拍。

    PERCEPT/DELIBERATE 拍只读 body、往 intents 追加；EVOLVE 拍读 intents 落地写。
    budget_ms 由 SelfCore 持有并在热路径上扣减——唯一的"本轮时钟"，谁也别想偷偷拖慢。
    """

    session_key: str
    event: Any                               # 宿主传入的原始事件（AstrBot event）
    body: BodySnapshot
    text: str = ""                           # 本轮用户文本
    current_warmth: float = 0.0
    phase: Phase = Phase.PERCEPT
    intents: list[Intent] = field(default_factory=list)
    # 各能力往这里挂只读产物（如召回结果），同拍内后续能力可读
    scratch: dict[str, Any] = field(default_factory=dict)
    budget_ms: float = 5.0                   # 本轮热路径预算（剩余）
    # 本会话领域 agent 表（P1：能力 agent 经此【每轮取域】，绝不构造期注入单会话依赖）。
    # 键=领域名（"memory"/"emotion"/…），值=领域 agent 实例。SelfCore 建 ctx 时注入。
    domains: dict[str, Any] = field(default_factory=dict)
    groups: Any = None                       # 跨会话群场入口（GroupDomain，P8；无群=None）

    def add(self, intent: Intent | None) -> None:
        if intent is not None:
            self.intents.append(intent)

    def domain(self, name: str) -> Any:
        """取本会话某领域 agent；缺失返 None（能力按需判空降级）。"""
        return self.domains.get(name)

    def evo_bias(self, agent: str, key: str) -> float:
        """读某门控参数学到的进化偏置（#29：reflex/反思 学到的偏置喂回 live 门控）。

        语义约定（叠加在人格函数基线上的小偏置）：effective_threshold = baseline + bias。
        负偏置＝降低门槛＝更主动（与 reflex/反思 "更主动=delta 负" 的既有约定一致，见
        manual_evolution_e2e[1] 与 reflection prompt）；正偏置＝抬高门槛＝更收敛。

        provider 由 integration 建 ctx 时注入 scratch["evo_delta"]（callable(agent,key)->float，
        背后是 agents.SelfCore.evo_delta，读 EvolutionStore 的 反射 delta + 反思 reflection_bias）。
        未注入（测试/旧路径）或异常 → 0.0（live 门控落回纯人格基线，零行为变化）。

        二次钳位（_EVO_BIAS_CAP）：即使 EvolutionStore 总 cap 将来放宽，live 门控见到的偏置
        也绝不超过 ±0.15——人格显函数永远是主项，学习只能微调不能改写。
        """
        fn = self.scratch.get("evo_delta")
        if not callable(fn):
            return 0.0
        try:
            v = float(fn(agent, key))
        except Exception:
            return 0.0
        if v > _EVO_BIAS_CAP:
            return _EVO_BIAS_CAP
        if v < -_EVO_BIAS_CAP:
            return -_EVO_BIAS_CAP
        return v


# ===========================================================================
# Capability 协议 —— 上层能力 agent（无独占状态，注册表驱动，加能力=注册一行）
# ===========================================================================

@runtime_checkable
class Capability(Protocol):
    """上层能力 agent 协议。三个钩子全部可选（按需实现对应相位）。

    设计纪律（辩论收敛）：
    - 能力 agent **无独占状态**，所有状态读写都经由领域 agent 的接口（注入获得）。
    - 注册到某一拍的能力槽；SelfCore 遍历能力表调用，受统一 budget_ms 约束。
    - 加新能力 = 新增一个实现本协议的类 + 注册表加一行，**不改 SelfCore.turn() 主体**。
      这是"诚实的零侵入扩展"：改动看得见、受预算兜底、可被砍超时——而非事件总线那种
      把延迟暗债挪进运行时的假零改动。
    """

    name: str
    phases: tuple[Phase, ...]   # 本能力参与哪些拍

    def perceive(self, ctx: BeatContext) -> Intent | None:
        """PERCEPT 拍：只读 body/领域接口，抽取信号，产出意图。默认无操作。"""
        ...

    def deliberate(self, ctx: BeatContext) -> Intent | None:
        """DELIBERATE 拍：热路径决策（召回/措辞/共情）。受 budget_ms 约束。"""
        ...

    def evolve(self, ctx: BeatContext) -> None:
        """EVOLVE 拍：通过领域 agent 接口提交写（无返回，副作用集中在此拍）。"""
        ...


# ===========================================================================
# 领域 agent 协议 —— 底层（各自独占状态 + 单一写者）
# ===========================================================================

@runtime_checkable
class DomainAgent(Protocol):
    """底层领域 agent 协议：守护一块领域状态，是该状态的唯一写者。

    别的 agent 绝不直接读写其内部状态，只能通过其公开接口（各领域自定义）。
    领域 agent 之间也不互相穿透——跨领域影响经 Intent + EVOLVE 拍编排。
    """

    name: str

    def to_dict(self) -> dict[str, Any]:
        """序列化自身状态（供持久化 / oracle 对照）。"""
        ...

    def load_dict(self, data: dict[str, Any]) -> None:
        """从持久化数据恢复（须对旧存档向前兼容——用户养成的 Sylanne 不能丢）。"""
        ...


# ===========================================================================
# Ports —— 对外能力的注入接口（agent 不知道"我在 AstrBot 里"，只知道有这些工具）
# ===========================================================================

@runtime_checkable
class BodyPort(Protocol):
    """SDK 计算核的封装：agent 通过它读 body / 推进 tick，不直接碰 kernel。"""

    def observe(self) -> BodySnapshot:
        """取当前 body 的只读类型化快照。"""
        ...

    def tick(self, event: dict[str, Any], assessment: dict[str, Any] | None = None) -> BodySnapshot:
        """喂事件推进不可逆计算，返回推进后的新快照。"""
        ...

    def snapshot(self) -> dict[str, Any]:
        """导出可持久化的完整内部状态。"""
        ...


@runtime_checkable
class StoragePort(Protocol):
    """KV 持久化抽象：agent 通过它存取，不直接碰 AstrBot 的 conv_mgr / KV。"""

    async def get(self, key: str) -> dict[str, Any] | None: ...
    async def put(self, key: str, value: dict[str, Any]) -> None: ...


@runtime_checkable
class LLMPort(Protocol):
    """LLM 调用抽象：能力 agent 通过它调模型，不知道底层是哪个 provider。

    零-LLM 纪律：热路径默认不调；调用方须显式承担 token 代价并有降级路径。
    """

    async def complete(self, prompt: str, **kw: Any) -> str: ...


# ===========================================================================
# Outbound / Reply 契约 —— 内部结构 ↔ 用户可见消息之间唯一的边界
# ===========================================================================
#
# 旧架构三类事故的同一道根因：内部结构直接漏成对外消息。
#   - 内部 diagnostics JSON 被直接 plain_result 给用户（"乱码"）
#   - 主链产出为空时静默清空 completion_text（"装死"，分不清"出错空"与"故意不说"）
#   - MessageChain 等内部对象被 str() 当正文发出（裸 repr 泄漏）
# 本节用类型把这道边界焊死：Reply 是唯一出口类型，Renderer 是唯一产出它的地方。

class ReplyKind(str, Enum):
    """对"本轮要不要说话"的显式表态——构造 Reply 必填，消灭"空=静默"的歧义。

    SPEAK    — 有内容要说。
    SILENT   — 明确决定本轮不回（表达阈值未到 / 主动沉默等）。是决策，不是出错。
    FALLBACK — 渲染兜底：输入为空或异常时的安全回复，而非静默吞掉。
    """

    SPEAK = "speak"
    SILENT = "silent"
    FALLBACK = "fallback"


@dataclass(frozen=True, slots=True)
class Reply:
    """对外消息的唯一出口类型。能力 agent/工具绝不自己拼它——只有 Renderer 产出。

    frozen + parts 限定为纯字符串分段 → 内部对象（BodySnapshot / MessageChain /
    diagnostics dict）在类型层就进不来，杜绝裸 repr 泄漏。
    kind 必填 → "产出为空"必须显式说明是 SILENT 还是 FALLBACK，不存在静默空回复。
    """

    kind: ReplyKind
    parts: tuple[str, ...] = ()              # 分段文本（对应宿主的分段发送）
    meta: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def is_speaking(self) -> bool:
        """是否真的要向用户发送可见内容。"""
        return self.kind is ReplyKind.SPEAK and any(p.strip() for p in self.parts)

    @classmethod
    def speak(cls, *parts: str, **meta: Any) -> Reply:
        """有内容要说。空白分段会被滤除；若全空则降级为 FALLBACK 由调用方兜底。"""
        clean = tuple(p for p in parts if p and p.strip())
        if not clean:
            return cls(kind=ReplyKind.FALLBACK, meta={"reason": "empty_speak", **meta})
        return cls(kind=ReplyKind.SPEAK, parts=clean, meta=meta)

    @classmethod
    def silent(cls, reason: str = "") -> Reply:
        """明确本轮不回（非出错）。reason 记入 meta 供可观测。"""
        return cls(kind=ReplyKind.SILENT, meta={"reason": reason} if reason else {})

    @classmethod
    def fallback(cls, text: str, **meta: Any) -> Reply:
        """渲染兜底：输入为空/异常时给一句安全回复，绝不静默。"""
        return cls(kind=ReplyKind.FALLBACK, parts=(text,) if text and text.strip() else (), meta=meta)


@runtime_checkable
class Renderer(Protocol):
    """内部 BeatContext → 对外 Reply 的唯一翻译步骤（内部↔外部的唯一边界）。

    纪律：
    - 能力 agent 只产 Intent（内部结构）；把 Intent/payload/affect 翻译成用户可见
      文本，是且仅是 Renderer 的职责。
    - 内部结构（snapshot / diagnostics / 领域状态）经此**只能投影成文本**，绝不
      原样 dump。需要向用户暴露状态的工具，也产 Intent 走这里投影，而非直接发送。
    - render 永远返回 Reply（带 kind）；输入为空/异常时返回 SILENT 或 FALLBACK，
      不允许返回 None、不允许静默。
    """

    def render(self, ctx: BeatContext) -> Reply: ...


__all__ = [
    "Phase",
    "BodySnapshot",
    "Intent",
    "BeatContext",
    "Capability",
    "DomainAgent",
    "BodyPort",
    "StoragePort",
    "LLMPort",
    "ReplyKind",
    "Reply",
    "Renderer",
]
