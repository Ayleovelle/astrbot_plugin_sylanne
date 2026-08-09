"""Sylanne-Embodiment: 生命模拟模块。

模拟 Sylanne 的独立"生活"——使用外部 LLM 定期生成生活事件，
这些事件可能触发主动联系用户（proactive outreach）。

设计理念：
- Sylanne 不是"等待被召唤的工具"，而是有自己生活节奏的存在
- 生活事件影响情绪状态，情绪状态影响对话风格
- 主动联系是"想分享"的自然结果，不是机械的定时推送

与其他组件的关系：
- 依赖外部 LLM 调用（通过 _llm_caller 回调）
- 通过 _emotion_getter 获取当前情绪状态
- 通过 _outreach_callback 触发主动消息发送
- life_prompt_fragment() 输出供对话生成时注入上下文（PR-B4 改名，
  recent_context_for_prompt 保留为兼容 alias）

PR-B（Phase 1）：引入结构化世界模型（LifeWorldState/LifePlan/LifeActivity），
LifeEvent 增量扩展 V2 字段（source/confidence/privacy_level/...），
_simulate_tick 重构为编排器，旧状态自动迁移。ShareIntent 留给 PR-C。
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


# ---------------------------------------------------------------------------
# PR-B1: schema 版本 + 来源/隐私/相位常量
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 3

# Phase 3 常量：项目晋升 / 里程碑 / 分享策略 / 技能 / outreach 审计 ----------------
# 项目里程碑阈值（progress 跨越 → 写入 LifeProject.milestones）
PROJECT_MILESTONES = (0.25, 0.5, 0.75, 1.0)
# 项目分享策略
SHARE_POLICY_NEVER = "never"
SHARE_POLICY_MILESTONE = "milestone"
SHARE_POLICY_CASUAL = "casual"
# 项目晋升：N 天窗口内至少 M 个不同日的同类事件 → 晋升为项目
PROJECT_PROMOTION_WINDOW_SECONDS = 7 * 86400.0
PROJECT_PROMOTION_MIN_DAYS = 3
PROJECT_MAX_ACTIVE = 4
# Wave 5（life → 表达底色）：从主导项目派生"卡住/刚通"内心底色的判定窗口（秒）。
# v1 用"久未触碰"作停滞代理（不追踪 progress 增量，residual：被碰但没进展会漏判，保守可接受）。
_LIFE_STALE_S = 2 * 86400.0        # active 项目超 2 天没碰 = 开始蔫
_LIFE_STALE_HI_S = 5 * 86400.0     # 5 天没碰 = 底色强度封顶
_LIFE_RESOLVED_WINDOW_S = 2 * 86400.0  # finished 后 2 天内仍"轻快"，之后自然归零
# 技能冷却倍率边界（adaptive：effectiveness 低则冷却拉长）
SKILL_COOLDOWN_MULT_MIN = 1.0
SKILL_COOLDOWN_MULT_MAX = 4.0
SKILL_EFFECTIVENESS_FLOOR = 0.1
# outreach 审计：超时阈值与每会话条数上限（M8 数据源补建）
OUTREACH_TIMEOUT_SECONDS = 1800.0
OUTREACH_AUDIT_PER_SESSION = 20
OUTREACH_AUDIT_MAX_SESSIONS = 100

# 内部哨兵：from_dict 中区分 "skills" key 缺席（v2 数据需 seed）vs key 存在但值为
# 空 list（v3 数据用户清空，应保留）。不能用 None / [] 做 sentinel，因为 v3 的
# `"skills": []` 是合法值。
_SKILLS_MISSING: object = object()


class LifeSource:
    """生活事件来源标签（写入 memory 时区分，对应 v2 ADR-002）。"""

    LEGACY = "legacy_life_sim"        # 旧档迁移而来
    PLANNED_TICK = "planned_tick"     # 正常 tick 生成
    USER_INTERACTION = "user_interaction"
    REFLECTION = "reflection"
    CONSOLIDATION = "consolidation"


class LifePrivacy:
    """隐私分级（life sim 不得自造 user_fact，对应 v2 §4.3/§10.1）。"""

    INTERNAL = "internal"        # Sylanne 内部独白，默认不进用户可见
    SHAREABLE = "shareable"      # 可分享给用户
    USER_FACT = "user_fact"     # 仅来自用户明确事实，life sim 永不自造此级


class LifePhase:
    """日相位（驱动活动延续/切换的规则输入）。"""

    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    NIGHT = "night"
    SLEEP = "sleep"


def _phase_for_hour(hour: int) -> str:
    """据本地小时数判定相位（规则化，零 LLM）。"""
    if 0 <= hour < 6:
        return LifePhase.SLEEP
    if hour < 12:
        return LifePhase.MORNING
    if hour < 18:
        return LifePhase.AFTERNOON
    if hour < 23:
        return LifePhase.EVENING
    return LifePhase.NIGHT


# ---------------------------------------------------------------------------
# LifeEvent（V2 增量扩展：保留原字段，新增结构化字段；向后兼容）
# ---------------------------------------------------------------------------


@dataclass
class LifeEvent:
    """一个生活事件。

    原字段（v1）：text/mood/urgency/timestamp/wants_to_share/shared/event_type。
    V2 增量字段（PR-B1，全部带默认值，旧档容缺）：
      - event_id/source/activity_id/project_id：结构化归属
      - private_thought：内心独白，默认不进用户可见回复
      - valence_delta/arousal_delta：显式情绪增量（独立于 LIFE_EVENT_WEIGHTS）
      - importance/novelty/confidence：[0,1] 评分，供巩固/裁剪
      - privacy_level：LifePrivacy.*（区分用户事实/模拟生活/系统推断）
      - caused_by/followups：因果链 event_id
      - queued_at/dispatched_at/consumed_at/dropped_at：M11 投递四时点
        （PR-C 启用，PR-B 先填 queued_at；shared 字段保留兼容）
    """

    # --- v1 字段 ---
    text: str  # 事件描述
    mood: str  # 当前心情
    urgency: float  # 紧迫度 [0,1]
    timestamp: float  # 发生时间
    wants_to_share: bool = False  # 是否想分享给朋友
    shared: bool = False  # 是否已经分享过（v1 语义=已排队；PR-C 拆四时点）
    event_type: str = ""  # 事件类型（对应 LifeEventType）
    # --- V2 增量字段 ---
    event_id: str = ""
    source: str = ""  # LifeSource.*
    activity_id: str = ""
    project_id: str = ""
    private_thought: str = ""
    valence_delta: float = 0.0
    arousal_delta: float = 0.0
    importance: float = 0.0
    novelty: float = 0.0
    confidence: float = 0.5
    privacy_level: str = ""  # LifePrivacy.*；空=未设（旧档）
    caused_by: list = field(default_factory=list)
    followups: list = field(default_factory=list)
    queued_at: float = 0.0
    dispatched_at: float = 0.0
    consumed_at: float = 0.0
    dropped_at: float = 0.0
    share_intent_id: str = ""  # PR-C1：关联 ShareIntent
    origin_session: str = ""  # PR-I：投递目标会话 key（投递时回填，路由元数据）

    def __post_init__(self) -> None:
        if not self.event_id:
            self.event_id = uuid.uuid4().hex[:12]
        if not self.privacy_level:
            self.privacy_level = LifePrivacy.INTERNAL


# ---------------------------------------------------------------------------
# Item 54: 生命模拟事件类型扩展
# ---------------------------------------------------------------------------


class LifeEventType:
    """生命模拟事件类型枚举。"""

    READING = "reading"
    WALKING = "walking"
    COOKING = "cooking"
    THINKING = "thinking"
    CREATING = "creating"
    RESTING = "resting"
    OBSERVING = "observing"


LIFE_EVENT_WEIGHTS: dict[str, dict[str, float]] = {
    "reading": {"valence": 0.2, "arousal": -0.1, "share_tendency": 0.4},
    "walking": {"valence": 0.3, "arousal": 0.1, "share_tendency": 0.3},
    "cooking": {"valence": 0.2, "arousal": 0.2, "share_tendency": 0.5},
    "thinking": {"valence": 0.0, "arousal": -0.2, "share_tendency": 0.6},
    "creating": {"valence": 0.4, "arousal": 0.3, "share_tendency": 0.7},
    "resting": {"valence": 0.1, "arousal": -0.3, "share_tendency": 0.1},
    "observing": {"valence": 0.1, "arousal": 0.0, "share_tendency": 0.5},
}

# T2-03⑤ 红队修复：当前活动典型时长（分钟），按 LIFE_EVENT_WEIGHTS 同一套真实
# event_type 键给粗粒度估算。此前 current_activity_duration_min() 试图按
# world.current_activity_id 匹配 state.plan 的锚点/弹性槽的 activity_id，但两者是
# 从未相交的 id 空间（current_activity_id 恒被 _record_event 写成事件自身 event_id，
# 计划锚点的 activity_id 独立生成，从无 tick 写入/匹配过），且唯一的计划生成器
# （life_consolidation._build_next_day_plan）从不填 expected_duration_min（恒 0）——
# 原实现是永远读不到值的死代码。改读【真实在用】的信号：最近一条事件的
# event_type（_record_event 每 tick 真写），值粗但生效，而非臆造精确值。
_ACTIVITY_TYPICAL_DURATION_MIN: dict[str, int] = {
    "reading": 30,
    "walking": 20,
    "cooking": 25,
    "thinking": 15,
    "creating": 40,
    "resting": 20,
    "observing": 15,
}

# 事件类型关键词映射（用于从 LLM 输出推断事件类型）
_EVENT_TYPE_KEYWORDS: dict[str, list[str]] = {
    "reading": ["读", "书", "阅读", "看书", "翻阅", "read", "book", "novel", "article"],
    "walking": ["走", "散步", "漫步", "路", "walk", "stroll", "hike", "wander"],
    "cooking": ["做饭", "烹饪", "厨房", "煮", "烤", "cook", "kitchen", "bak", "meal"],
    "thinking": ["想", "思考", "沉思", "冥想", "think", "ponder", "reflect", "contempl"],
    "creating": ["创作", "画", "写", "做", "制作", "creat", "draw", "writ", "craft", "paint", "compos"],
    "resting": ["休息", "睡", "躺", "放松", "rest", "sleep", "relax", "nap", "doze"],
    "observing": ["观察", "看", "注视", "望", "observ", "watch", "gaze", "notic"],
}


# ---------------------------------------------------------------------------
# PR-B1: LifeWorldState / LifePlan / LifeActivity（结构化世界模型）
# ---------------------------------------------------------------------------


@dataclass
class LifeActivity:
    """日计划中的一个活动片段（锚点或弹性槽）。"""

    activity_id: str = ""
    kind: str = ""  # study/create/rest/game/social/reflect
    title: str = ""
    expected_start: str = ""  # "HH:MM" 或空
    expected_duration_min: int = 0
    status: str = "planned"  # planned/active/paused/done/skipped
    project_id: str = ""
    emotional_tone: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.activity_id:
            self.activity_id = uuid.uuid4().hex[:10]


@dataclass
class LifePlan:
    """某天的轻量生活计划（低频生成/修正，PR-B 用规则化，非 LLM 重）。"""

    plan_id: str = ""
    date: str = ""  # YYYY-MM-DD（local）
    timezone: str = ""
    anchors: list = field(default_factory=list)  # list[LifeActivity] 固定锚点
    flexible_slots: list = field(default_factory=list)
    commitments: list = field(default_factory=list)
    generated_from: list = field(default_factory=list)  # memory/reflection/project ids
    confidence: float = 0.4

    def __post_init__(self) -> None:
        if not self.plan_id:
            self.plan_id = uuid.uuid4().hex[:10]


@dataclass
class LifeProject:
    """Phase 3：长期项目线程（LifeProject）。

    由确定性聚类晋升而来：7 天窗口内 ≥3 个不同日的同类 event_type → 自动晋升。
    上限 PROJECT_MAX_ACTIVE 个活跃项目（防爆炸）。LifeConsolidation 负责生灭与
    进度推进（零 LLM），LifeReflection 据 effectiveness 提供 kind_bias 微调。

    分享策略（share_policy）：
      - never:     不分享（项目级 SILENT）
      - milestone: 仅里程碑分享（默认；非里程碑事件被门控强制 SILENT）
      - casual:    自由分享（与原行为一致）

    effectiveness ∈ [0, 1]：项目产出的"主观值"，初始 0.5，由巩固期事件 importance
    均值缓慢更新；LifeReflection 可参考此值微调下日 kind_bias。
    """

    project_id: str = ""
    title: str = ""
    kind: str = "rest"              # study/create/game/rest/social/reflect
    state: str = "active"           # active/paused/finished
    progress: float = 0.0           # 0.0 - 1.0
    milestones: list = field(default_factory=list)            # 已命中的阈值字符串
    milestones_shared: list = field(default_factory=list)     # 已分享过的里程碑
    event_type: str = ""            # 触发此项目的 LifeEventType
    last_touched_at: float = 0.0
    created_at: float = 0.0
    share_policy: str = SHARE_POLICY_MILESTONE
    effectiveness: float = 0.5

    def __post_init__(self) -> None:
        if not self.project_id:
            self.project_id = uuid.uuid4().hex[:12]


@dataclass
class LifeSkill:
    """Phase 3：自适应行为技能（LifeSkill）。

    内置三个种子技能（SEED_SKILLS），命中 trigger_event_types 时由
    LifeSimulator 在 tick 中触发，受冷却约束。冷却倍率随效用调整：
      cooldown_multiplier = clamp(1 + 2 * (1 - effectiveness), 1, 4)
    成功 → effectiveness 上行（被 outreach consumed），失败 → 下行（被 dropped）。

    effectiveness 有最低 SKILL_EFFECTIVENESS_FLOOR（0.1），防完全失活。
    """

    skill_id: str = ""
    name: str = ""
    trigger_event_types: list = field(default_factory=list)
    cooldown_seconds: int = 3600
    cooldown_multiplier: float = 1.0
    last_triggered_at: float = 0.0  # 0.0 = 从未触发
    success_count: int = 0
    failure_count: int = 0
    effectiveness: float = 0.5

    def __post_init__(self) -> None:
        if not self.skill_id:
            self.skill_id = uuid.uuid4().hex[:12]


# Phase 3 种子技能：默认三个内置技能（首次创建 state 时注入）
def _seed_skills() -> list[LifeSkill]:
    return [
        LifeSkill(
            name="evening_soft_checkin",
            trigger_event_types=[LifeEventType.RESTING, LifeEventType.OBSERVING],
            cooldown_seconds=7200,
        ),
        LifeSkill(
            name="creative_milestone_share",
            trigger_event_types=[LifeEventType.CREATING],
            cooldown_seconds=14400,
        ),
        LifeSkill(
            name="thesis_companion",
            trigger_event_types=[LifeEventType.READING, LifeEventType.THINKING],
            cooldown_seconds=10800,
        ),
    ]


@dataclass
class LifeWorldState:

    schema_version: int = SCHEMA_VERSION
    local_date: str = ""
    phase: str = ""  # LifePhase.*
    energy: float = 0.6  # [0,1]
    focus: float = 0.5  # [0,1]
    mood_baseline: dict = field(default_factory=dict)
    current_activity_id: str = ""
    active_plan_id: str = ""
    active_project_ids: list = field(default_factory=list)
    habits: dict = field(default_factory=dict)
    relationship_snapshot: dict = field(default_factory=dict)
    # Phase 2 核心：LifeReflection 写的次日计划建议（单写者=反思，巩固只读作输入）。
    # advisory only：巩固仍是 state.plan 唯一所有者；hint 每日由反思重生（不累积），
    # 防自证循环。结构 {"arc": str 叙事弧, "kind_bias": {kind: bounded_float}}。
    next_plan_hint: dict = field(default_factory=dict)
    last_tick_at: float = 0.0


# ---------------------------------------------------------------------------
# PR-C1: ShareIntent（关系感知分享策略，对应 v2 §4.6）
# ---------------------------------------------------------------------------


class DeliveryMode:
    """分享投递模式（由 ShareIntent.final_score 映射，v2 §4.6 阈值）。"""

    SILENT = "silent"            # 只存 journal，不分享
    NEXT_REPLY = "next_reply"    # 下次用户来时自然提（pending context）
    BRIDGE = "bridge"            # 交给 proactive bridge 做时机控制
    DIRECT = "direct"            # 直发候选（仍须过 bridge gate）


# final_score 决策权重（v2 §4.6 决策公式）
_SHARE_WEIGHTS = {
    "content_value": 0.25,
    "relationship_value": 0.25,
    "urgency": 0.15,
    "interruptibility": 0.20,
    "response_likelihood": 0.10,
    "cooldown_penalty": -0.20,
    "unanswered_penalty": -0.20,
    "privacy_risk": -0.30,
}


@dataclass
class ShareIntent:
    """一次分享意图评分（v2 §4.6）。PR-C1 规则化评分（零 LLM）。

    final_score 由 weighted sum 算出，映射到 delivery_mode。delivery_mode 决定
    _do_outreach 的行为（silent/next_reply/bridge/direct）。
    """

    intent_id: str = ""
    event_id: str = ""
    content_value: float = 0.5
    relationship_value: float = 0.4
    urgency: float = 0.0  # 复用 LifeEvent.urgency（L19）
    interruptibility: float = 0.5
    user_response_likelihood: float = 0.5
    cooldown_penalty: float = 0.0
    unanswered_penalty: float = 0.0
    privacy_risk: float = 0.0
    final_score: float = 0.0
    delivery_mode: str = DeliveryMode.NEXT_REPLY
    reason_code: str = ""
    expires_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.intent_id:
            self.intent_id = uuid.uuid4().hex[:12]


def _score_to_delivery(score: float) -> str:
    """v2 §4.6 阈值映射。"""
    if score < 0.25:
        return DeliveryMode.SILENT
    if score < 0.55:
        return DeliveryMode.NEXT_REPLY
    if score < 0.78:
        return DeliveryMode.BRIDGE
    return DeliveryMode.DIRECT


# PR-B/C review MED3：基于 inspect 判断回调是否接受 intent 第三参。
# 不用裸 TypeError（会把三参回调【内部】的 TypeError 误判为签名不兼容 → 吞 bug + 二次调用）。
_CALLBACK_ARITY_CACHE: dict[Any, bool] = {}


def _callback_cache_key(cb: Callable[..., Any]) -> Any:
    """稳定缓存键：用 callable 的 __code__ 对象（bound method 取其 __func__.__code__）。

    不能用 id(cb)：函数被 GC 后地址可复用，新 callable 命中旧条目会拿到错误 arity
    （跨调用/跨测试的 id-reuse 污染）。__code__ 对象作 key 时，dict 持有强引用使其存活，
    天然无 id 复用问题；不同函数 __code__ 必不同。无 __code__ 的可调用回退到 id（罕见）。
    """
    fn = getattr(cb, "__func__", cb)
    code = getattr(fn, "__code__", None)
    return code if code is not None else id(cb)


def _callback_accepts_intent(cb: Callable[..., Any]) -> bool:
    """判断回调签名是否接受第三参（intent dict）。缓存结果，容错降级 True（安全）。"""
    key = _callback_cache_key(cb)
    cached = _CALLBACK_ARITY_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        import inspect
        sig = inspect.signature(cb)
        # 只数显式参数（含 self 对 bound method）；带 *args/**kwargs 视为接受任意
        params = list(sig.parameters.values())
        has_var = any(
            p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
            for p in params
        )
        n_positional = sum(
            1 for p in params
            if p.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        )
        # 简化：能传 3 个位置参数 或 有可变参 就接受
        accepts = has_var or n_positional >= 3
    except Exception:
        accepts = True  # 无法判定时默认三参（main.py 实际就是三参）
    _CALLBACK_ARITY_CACHE[key] = accepts
    return accepts





# ---------------------------------------------------------------------------
# PR-B2: 序列化 helper（LifeEvent / LifeWorldState / LifePlan）+ 旧档迁移
# ---------------------------------------------------------------------------


def _event_to_dict(e: LifeEvent) -> dict[str, Any]:
    """完整序列化 LifeEvent（含 V2 字段 + event_type；修 v1 to_dict 漏字段缺陷）。"""
    return {
        # v1 字段
        "text": e.text,
        "mood": e.mood,
        "urgency": e.urgency,
        "timestamp": e.timestamp,
        "wants_to_share": e.wants_to_share,
        "shared": e.shared,
        "event_type": e.event_type,
        # V2 字段
        "event_id": e.event_id,
        "source": e.source,
        "activity_id": e.activity_id,
        "project_id": e.project_id,
        "private_thought": e.private_thought,
        "valence_delta": e.valence_delta,
        "arousal_delta": e.arousal_delta,
        "importance": e.importance,
        "novelty": e.novelty,
        "confidence": e.confidence,
        "privacy_level": e.privacy_level,
        "caused_by": list(e.caused_by),
        "followups": list(e.followups),
        "queued_at": e.queued_at,
        "dispatched_at": e.dispatched_at,
        "consumed_at": e.consumed_at,
        "dropped_at": e.dropped_at,
        "share_intent_id": e.share_intent_id,
        "origin_session": e.origin_session,
    }


def _event_from_dict(d: dict[str, Any]) -> LifeEvent:
    """从 dict 恢复 LifeEvent，容缺所有 V2 字段（旧档可读）。

    旧档迁移：若 source 为空则标 LEGACY（v1 事件），confidence 默认 0.5，
    privacy_level 由 LifeEvent.__post_init__ 兜底为 INTERNAL。
    """
    e = LifeEvent(
        text=str(d.get("text", "")),
        mood=str(d.get("mood", "neutral")),
        urgency=float(d.get("urgency", 0.0)),
        timestamp=float(d.get("timestamp", 0.0)),
        wants_to_share=bool(d.get("wants_to_share", False)),
        shared=bool(d.get("shared", False)),
        event_type=str(d.get("event_type", "")),
        event_id=str(d.get("event_id", "")) or "",
        source=str(d.get("source", "")) or "",
        activity_id=str(d.get("activity_id", "")) or "",
        project_id=str(d.get("project_id", "")) or "",
        private_thought=str(d.get("private_thought", "")) or "",
        valence_delta=float(d.get("valence_delta", 0.0)),
        arousal_delta=float(d.get("arousal_delta", 0.0)),
        importance=float(d.get("importance", 0.0)),
        novelty=float(d.get("novelty", 0.0)),
        confidence=float(d.get("confidence", 0.5)),
        privacy_level=str(d.get("privacy_level", "")) or "",
        caused_by=list(d.get("caused_by", []) or []),
        followups=list(d.get("followups", []) or []),
        queued_at=float(d.get("queued_at", 0.0)),
        dispatched_at=float(d.get("dispatched_at", 0.0)),
        consumed_at=float(d.get("consumed_at", 0.0)),
        dropped_at=float(d.get("dropped_at", 0.0)),
        share_intent_id=str(d.get("share_intent_id", "")) or "",
        origin_session=str(d.get("origin_session", "")) or "",
    )
    # 旧档迁移：无 source 视作 legacy（保留 event_id 不覆盖，若有）
    if not e.source:
        e.source = LifeSource.LEGACY
    return e


def _world_to_dict(w: LifeWorldState) -> dict[str, Any]:
    return {
        "schema_version": w.schema_version,
        "local_date": w.local_date,
        "phase": w.phase,
        "energy": w.energy,
        "focus": w.focus,
        "mood_baseline": dict(w.mood_baseline),
        "current_activity_id": w.current_activity_id,
        "active_plan_id": w.active_plan_id,
        "active_project_ids": list(w.active_project_ids),
        "habits": dict(w.habits),
        "relationship_snapshot": dict(w.relationship_snapshot),
        "next_plan_hint": dict(w.next_plan_hint),
        "last_tick_at": w.last_tick_at,
    }


def _world_from_dict(d: dict[str, Any] | None) -> LifeWorldState:
    """从 dict 恢复 LifeWorldState；旧档无 world 字段时返回默认（迁移兜底）。"""
    if not d or not isinstance(d, dict):
        return LifeWorldState()
    try:
        return LifeWorldState(
            schema_version=int(d.get("schema_version", SCHEMA_VERSION)),
            local_date=str(d.get("local_date", "")),
            phase=str(d.get("phase", "")),
            energy=float(d.get("energy", 0.6)),
            focus=float(d.get("focus", 0.5)),
            mood_baseline=dict(d.get("mood_baseline", {}) or {}),
            current_activity_id=str(d.get("current_activity_id", "")),
            active_plan_id=str(d.get("active_plan_id", "")),
            active_project_ids=list(d.get("active_project_ids", []) or []),
            habits=dict(d.get("habits", {}) or {}),
            relationship_snapshot=dict(d.get("relationship_snapshot", {}) or {}),
            next_plan_hint=dict(d.get("next_plan_hint", {}) or {}),
            last_tick_at=float(d.get("last_tick_at", 0.0)),
        )
    except Exception:
        return LifeWorldState()


def _plan_to_dict(p: LifePlan | None) -> dict[str, Any] | None:
    if p is None:
        return None
    return {
        "plan_id": p.plan_id,
        "date": p.date,
        "timezone": p.timezone,
        "anchors": [dict(a) if isinstance(a, dict) else getattr(a, "__dict__", {}) for a in p.anchors],
        "flexible_slots": [dict(a) if isinstance(a, dict) else getattr(a, "__dict__", {}) for a in p.flexible_slots],
        "commitments": list(p.commitments),
        "generated_from": list(p.generated_from),
        "confidence": p.confidence,
    }


def _plan_from_dict(d: dict[str, Any] | None) -> LifePlan | None:
    if not d or not isinstance(d, dict):
        return None
    try:
        return LifePlan(
            plan_id=str(d.get("plan_id", "")) or "",
            date=str(d.get("date", "")),
            timezone=str(d.get("timezone", "")),
            anchors=list(d.get("anchors", []) or []),
            flexible_slots=list(d.get("flexible_slots", []) or []),
            commitments=list(d.get("commitments", []) or []),
            generated_from=list(d.get("generated_from", []) or []),
            confidence=float(d.get("confidence", 0.4)),
        )
    except Exception:
        return None


def _project_to_dict(p: LifeProject) -> dict[str, Any]:
    return {
        "project_id": p.project_id,
        "title": p.title,
        "kind": p.kind,
        "state": p.state,
        "progress": p.progress,
        "milestones": list(p.milestones),
        "milestones_shared": list(p.milestones_shared),
        "event_type": p.event_type,
        "last_touched_at": p.last_touched_at,
        "created_at": p.created_at,
        "share_policy": p.share_policy,
        "effectiveness": p.effectiveness,
    }


def _project_from_dict(d: dict[str, Any]) -> LifeProject:
    return LifeProject(
        project_id=str(d.get("project_id", "")) or "",
        title=str(d.get("title", "")),
        kind=str(d.get("kind", "rest")),
        state=str(d.get("state", "active")),
        progress=float(d.get("progress", 0.0)),
        milestones=list(d.get("milestones", []) or []),
        milestones_shared=list(d.get("milestones_shared", []) or []),
        event_type=str(d.get("event_type", "")),
        last_touched_at=float(d.get("last_touched_at", 0.0)),
        created_at=float(d.get("created_at", 0.0)),
        share_policy=str(d.get("share_policy", SHARE_POLICY_MILESTONE)),
        effectiveness=float(d.get("effectiveness", 0.5)),
    )


def _skill_to_dict(s: LifeSkill) -> dict[str, Any]:
    return {
        "skill_id": s.skill_id,
        "name": s.name,
        "trigger_event_types": list(s.trigger_event_types),
        "cooldown_seconds": s.cooldown_seconds,
        "cooldown_multiplier": s.cooldown_multiplier,
        "last_triggered_at": s.last_triggered_at,
        "success_count": s.success_count,
        "failure_count": s.failure_count,
        "effectiveness": s.effectiveness,
    }


def _skill_from_dict(d: dict[str, Any]) -> LifeSkill:
    return LifeSkill(
        skill_id=str(d.get("skill_id", "")) or "",
        name=str(d.get("name", "")),
        trigger_event_types=list(d.get("trigger_event_types", []) or []),
        cooldown_seconds=int(d.get("cooldown_seconds", 3600)),
        cooldown_multiplier=float(d.get("cooldown_multiplier", 1.0)),
        last_triggered_at=float(d.get("last_triggered_at", 0.0)),
        success_count=int(d.get("success_count", 0)),
        failure_count=int(d.get("failure_count", 0)),
        effectiveness=float(d.get("effectiveness", 0.5)),
    )







@dataclass
class LifeSimulationState:
    """生命模拟的持久化状态。

    PR-B：新增 world（LifeWorldState）与 plan（LifePlan|None）。
    旧 to_dict 漏存 event_type 的缺陷（v1）在 PR-B 修复（_event_to_dict 完整序列化）。

    Phase 3：新增 projects（LifeProject 列表）/ skills（LifeSkill 列表）
    / outreach_audit（M8 单一数据源补建：{session_key: [entry, ...]}，BoundedDict
    式按会话裁剪 + 每会话按时间裁剪）。schema 升至 3，旧档 (v2) 自动迁移：
    projects=[]、skills=种子三条、outreach_audit={}。
    """

    events: list[LifeEvent] = field(default_factory=list)  # 历史事件列表
    current_activity: str = ""  # 当前正在做的事（由 world.current_activity_id 派生，保留兼容）
    last_simulation_time: float = 0.0  # 上次模拟时间
    last_outreach_time: float = 0.0  # 上次主动联系时间
    simulation_count: int = 0  # 总模拟次数
    outreach_count: int = 0  # 总主动联系次数
    enabled: bool = False  # 是否启用
    # PR-B2：结构化世界状态 + 日计划
    world: LifeWorldState = field(default_factory=LifeWorldState)
    plan: LifePlan | None = None
    # Phase 3：项目线程 + 自适应技能 + outreach 审计（M8 单一数据源）
    projects: list[LifeProject] = field(default_factory=list)
    skills: list[LifeSkill] = field(default_factory=_seed_skills)  # 默认种子三条
    # outreach_audit: {session_key: list[dict]}（entry: dispatched/responded/timeout 等）
    # 形态选 dict 而非 BoundedDict——LifeSimulationState 是数据 dataclass，运行时由
    # LifeSimulator 在 _bound_audit() 内做按会话/每会话裁剪。
    outreach_audit: dict[str, list[dict]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """序列化状态（只保留最近 20 个事件，完整含 V2 字段）。"""
        return {
            "schema_version": SCHEMA_VERSION,
            "events": [_event_to_dict(e) for e in self.events[-20:]],
            "current_activity": self.current_activity,
            "last_simulation_time": self.last_simulation_time,
            "last_outreach_time": self.last_outreach_time,
            "simulation_count": self.simulation_count,
            "outreach_count": self.outreach_count,
            "world": _world_to_dict(self.world),
            "plan": _plan_to_dict(self.plan),
            # Phase 3 新增字段（旧档读时容缺，已迁移至 v3 时回填）
            "projects": [_project_to_dict(p) for p in self.projects],
            "skills": [_skill_to_dict(s) for s in self.skills],
            "outreach_audit": dict(self.outreach_audit),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LifeSimulationState":
        """从字典恢复状态。旧档容缺迁移：无 V2 字段时补默认值。

        迁移规则（v2 ADR-002 / v3 Phase 3）：
          - 旧 events → source=LEGACY, confidence=0.5, privacy_level=INTERNAL
          - 无 world → 默认 LifeWorldState（last_tick_at=0）
          - 无 plan → None
          - v2 → v3：无 projects → []；无 outreach_audit → {}
          - skills 迁移按 key 存在性判断（第二轮 review 修复）：
              * "skills" key 缺席（v2 数据）→ 注入种子三条
              * "skills": [] （v3 数据，用户清空）→ 保留为空
              * "skills": [...]（v3 数据）→ 反序列化
              * 其他类型（损坏）→ 兜底回到种子
        """
        state = cls()
        state.current_activity = data.get("current_activity", "")
        state.last_simulation_time = data.get("last_simulation_time", 0.0)
        state.last_outreach_time = data.get("last_outreach_time", 0.0)
        state.simulation_count = data.get("simulation_count", 0)
        state.outreach_count = data.get("outreach_count", 0)
        for e in data.get("events", []):
            state.events.append(_event_from_dict(e))
        # PR-B2：恢复 world/plan（旧档无 → 默认，迁移兜底）
        state.world = _world_from_dict(data.get("world"))
        state.plan = _plan_from_dict(data.get("plan"))
        # Phase 3：projects / skills / outreach_audit
        raw_projects = data.get("projects")
        if isinstance(raw_projects, list):
            state.projects = [
                _project_from_dict(d) for d in raw_projects if isinstance(d, dict)
            ]
        else:
            state.projects = []  # v2 → v3：空项目
        raw_skills = data.get("skills", _SKILLS_MISSING)
        if raw_skills is _SKILLS_MISSING:
            # v2 数据（"skills" key 整体缺席）→ 注入种子技能（首次升级默认值）
            state.skills = _seed_skills()
        elif isinstance(raw_skills, list):
            # v3 数据（key 存在，即使是空列表也尊重用户清空意图）
            state.skills = [
                _skill_from_dict(d) for d in raw_skills if isinstance(d, dict)
            ]
        else:
            # 数据损坏（key 存在但不是 list）→ 兜底回到种子
            state.skills = _seed_skills()
        raw_audit = data.get("outreach_audit")
        if isinstance(raw_audit, dict):
            # 第一轮 review 修复：列表元素也要类型校验，损坏数据里的非 dict 条目会让
            # _check_outreach_timeouts / _update_skill_outcomes 在 entry.get() 时崩。
            state.outreach_audit = {
                str(k): [entry for entry in v if isinstance(entry, dict)]
                for k, v in raw_audit.items() if isinstance(v, list)
            }
        else:
            state.outreach_audit = {}
        return state


LIFE_SIMULATION_PROMPT = """你是一个创意写作助手。请为以下虚构角色生成一个当前时刻的生活片段。

注意：你不是在扮演这个角色对话，而是在模拟她独处时的生活状态——她此刻在做什么、想什么、心情如何。
输出应该是第三人称视角的简短生活快照。

角色设定：
{persona_desc}

当前环境：
- 时间：{time_desc}
- 角色情绪倾向：{emotion_desc}
- 距离上次和朋友聊天：{last_chat_desc}
- 最近在做：{recent_activity}

请根据角色设定，生成这个角色此刻可能在做什么、想什么。内容要符合角色的性格和习惯。
用 JSON 格式输出：
{{"activity": "正在做什么（简短）", "thought": "在想什么（简短）", "mood": "当前心情（一个词）", "wants_to_share": true/false, "share_reason": "如果想分享给朋友，原因（简短）", "urgency": 0.0-1.0}}"""


class LifeSimulator:
    """管理 Sylanne 的模拟独立生活（CP8-P3b：自驱心跳已外移）。

    本类不再自跑后台循环（原 `_loop`/`start`/`stop` 已删除）。心跳驱动统一收归
    `AutonomyScheduler → LifeAgent(AUTONOMOUS) → simulate_tick()`。本类只负责
    「演化内容」：生成事件 / 算情绪权重 / 注入 body / 触发 outreach。

    生命周期：
    1. configure() 注入外部依赖（LLM、回调等）
    2. AutonomyScheduler 全局心跳驱动 LifeAgent 在 AUTONOMOUS 时点调 simulate_tick()
    3. simulate_tick()（公开入口）→ _simulate_tick()（实现）：_build_prompt()
       → LLM → _parse_response() → 写 events → 应用情绪权重 → 可能 _do_outreach()
    4. tick 末尾拨 _countdown_callback（外部主动发言倒计时）

    持久化：`initialize` 读 KV `sylanne_life_sim_state`，`terminate` 写回；
    tick 后可经 `state_dirty_callback` 触发宿主节流落盘（见 §PR-A5）。
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config or {}
        self.state = LifeSimulationState()
        self._llm_caller: Callable[..., Awaitable[str]] | None = None  # LLM 调用回调
        self._outreach_callback: Callable[[str, str], Awaitable[None]] | None = (
            None  # 主动联系回调
        )
        self._emotion_getter: Callable[[], dict[str, float]] | None = (
            None  # 情绪状态获取
        )
        self._persona_getter: Callable[[], str] | None = None  # 角色描述获取
        self._memory_summary_getter: Callable[[], str] | None = None  # 记忆摘要获取
        self._countdown_callback: Callable[[], Awaitable[None]] | None = (
            None  # 拨动外部主动发言倒计时（如大饼）
        )
        self._state_dirty_callback: Callable[[], Awaitable[None]] | None = (
            None  # tick 后状态变脏通知（宿主节流落盘，PR-A5）
        )
        self._qzone_candidate_callback: (
            Callable[[LifeEvent, ShareIntent], Awaitable[None]] | None
        ) = None  # Qzone 说说候选回调（默认关，仅 qzone_enabled 时才会被喂）
        # PR-C1：ShareIntent store（intent_id → ShareIntent），供 pipeline 取用
        self._share_intents: dict[str, ShareIntent] = {}
        # issue#43 Wave1：生活模拟连续失败计数 + 退避剩余跳过拍数（瞬时态，故意
        # 不进 LifeSimulationState / 不持久化——重启即重新探测 provider）。
        self._consecutive_failures: int = 0
        self._backoff_skip_remaining: int = 0
        self._last_fail_warn_ts: float = 0.0  # 上次持续失败告警的壁钟（时间制重发节流）

    @property
    def enabled(self) -> bool:
        return bool(self._config.get("sylanne_alpha_life_simulation_enabled", False))

    @property
    def interval_seconds(self) -> float:
        return max(
            60.0,
            float(
                self._config.get(
                    "sylanne_alpha_life_simulation_interval_seconds", 1800.0
                )
            ),
        )

    @property
    def outreach_cooldown_seconds(self) -> float:
        return max(
            300.0,
            float(
                self._config.get(
                    "sylanne_alpha_life_simulation_outreach_cooldown_seconds", 3600.0
                )
            ),
        )

    @property
    def qzone_enabled(self) -> bool:
        """Qzone 说说候选入口总闸（默认关，独立于 life_simulation_enabled 本身，
        也独立于 proactive_bridge_enabled——三个开关互不预设依赖关系）。"""
        return bool(self._config.get("sylanne_alpha_qzone_enabled", False))

    @property
    def qzone_min_score(self) -> float:
        """ShareIntent.final_score 达到此分才尝试送去广播候选（与私聊投递互不排斥，
        私聊照常走原 _score_to_delivery 判定，这里是"额外可选地"送一份候选）。"""
        return float(self._config.get("sylanne_alpha_qzone_min_score", 0.55))

    def configure(
        self,
        llm_caller: Callable[..., Awaitable[str]] | None = None,
        outreach_callback: Callable[[str, str], Awaitable[None]] | None = None,
        emotion_getter: Callable[[], dict[str, float]] | None = None,
        persona_getter: Callable[[], str] | None = None,
        memory_summary_getter: Callable[[], str] | None = None,
        body_delta_callback: Callable[[dict[str, float]], None] | None = None,
        countdown_callback: Callable[[], Awaitable[None]] | None = None,
        state_dirty_callback: Callable[[], Awaitable[None]] | None = None,
        qzone_candidate_callback: Callable[[LifeEvent, ShareIntent], Awaitable[None]]
        | None = None,
    ):
        """注入外部依赖。所有回调都是可选的。"""
        self._llm_caller = llm_caller
        self._outreach_callback = outreach_callback
        self._emotion_getter = emotion_getter
        self._persona_getter = persona_getter
        self._memory_summary_getter = memory_summary_getter
        self._body_delta_callback = body_delta_callback
        self._countdown_callback = countdown_callback
        self._state_dirty_callback = state_dirty_callback
        self._qzone_candidate_callback = qzone_candidate_callback

    async def simulate_tick(self) -> None:
        """执行一次模拟周期（CP8-P3b：公开入口，由 LifeAgent 自驱调用）。

        原 _loop 后台循环已删除——演化驱动统一收归 AutonomyScheduler，本方法
        只负责「演化内容」（生成事件 / 算情绪权重 / 注入 body / 触发 outreach），
        由 LifeAgent.act（autonomous 时点）调用，实现单一心跳的 agent 同构架构。
        """
        await self._simulate_tick()

    async def _simulate_tick(self):
        """执行一次模拟周期（PR-B3 编排器）。

        拆成：_load_world_context → LLM → _record_event → _emit_side_effects。
        ShareIntent 留给 PR-C，此处沿用原 wants_to_share 逻辑（不改分享策略）。
        """
        # 契约防线（PR-A review HIGH）：enabled=false 或 caller 缺失时零副作用。
        if not self.enabled:
            return
        if not self._llm_caller:
            return

        import datetime as _dt

        now = time.time()
        # Phase 3 / M8 audit：tick 开始扫一遍 outreach 超时（response 长时间未到 → timeout）。
        # 放在退避短路【之前】——超时 housekeeping 不调 LLM，退避期间也要照常做。
        self._check_outreach_timeouts(now)

        # issue#43 Wave1：失败退避（漏桶探测式）。连续失败到阈值后跳过若干心跳，
        # 跳完放行一拍探测 provider；探测成功由 _record_event 清零，失败再退避。
        # 绝不永久门死（否则 provider 恢复后永远不再被探测，比原本空转更糟）；
        # 也绝不在失败路径推进 last_simulation_time（守 PR-A 零副作用契约，且不掩盖 due 故障信号）。
        if self._backoff_skip_remaining > 0:
            self._backoff_skip_remaining -= 1
            return

        # 加宽 try（红队 finding）：_load_world_context / _build_prompt 的异常也要走失败处理，
        # 否则它们抛错会绕过计数/退避/告警，再被 life_agent.act 的 except-pass 吞成新的静默冻结。
        try:
            ctx = self._load_world_context(now, _dt)
            prompt = self._build_prompt(now, ctx)
            response = await self._llm_caller(prompt)
            parsed = self._parse_response(response, now)
        except Exception:
            self._note_tick_failure("tick_exception")
            return  # 零副作用（不 bump、不 callback）

        if not parsed:
            self._note_tick_failure("empty_or_unparseable")
            return  # 空响应零副作用（PR-A review HIGH）

        event, emotion_weights = parsed
        self._record_event(event, emotion_weights, ctx, now)
        await self._emit_side_effects(event, emotion_weights, now)
        self._log_tick(event, ctx, now)

    # issue#43 Wave1：退避阈值 + 跳过拍数封顶（瞬时退避，类常量）+ 重发告警壁钟间隔。
    _LIFE_FAIL_BACKOFF_THRESHOLD = 3
    _LIFE_FAIL_BACKOFF_MAX_SKIP = 20
    _LIFE_FAIL_WARN_INTERVAL_S = 3600.0

    def _note_tick_failure(self, reason: str) -> None:
        """记一次失败：自增连续失败计数、触发退避、按壁钟节流告警。

        不推进任何 state（守零副作用契约）。退避跳过拍数随失败次数增长并封顶。
        告警在到阈值首次 + 之后每隔 _LIFE_FAIL_WARN_INTERVAL_S 壁钟重发——【不用次数模运算】，
        因为退避会把探测拍稀释到天级，次数模会让多小时/多天宕机只剩一行日志后归于沉默（红队 finding）。
        """
        self._consecutive_failures += 1
        n = self._consecutive_failures
        if n >= self._LIFE_FAIL_BACKOFF_THRESHOLD:
            # 跳过拍数随失败次数增长、封顶；跳完后那一拍放行探测（漏桶式）。
            self._backoff_skip_remaining = min(self._LIFE_FAIL_BACKOFF_MAX_SKIP, n)
        now = time.time()
        first = n == self._LIFE_FAIL_BACKOFF_THRESHOLD
        due = now - self._last_fail_warn_ts >= self._LIFE_FAIL_WARN_INTERVAL_S
        if first or (n > self._LIFE_FAIL_BACKOFF_THRESHOLD and due):
            self._last_fail_warn_ts = now
            import logging
            logging.getLogger(__name__).warning(
                "Sylanne life_sim 连续失败 %d 次（%s）：生活状态停止推进、已退避探测；"
                "若启用了生活模拟，请检查 sylanne_alpha_life_simulation_provider_id 是否配置/可用。",
                n, reason,
            )

    @property
    def consecutive_failures(self) -> int:
        """生活模拟连续失败次数（0=健康）。供 WebUI/调试观测故障，不持久化。"""
        return self._consecutive_failures

    def _load_world_context(self, now: float, _dt) -> dict[str, Any]:
        """读取世界状态 + 计算相位/能量候选值，供编排与 prompt 注入。

        PR-B review HIGH1 修复：本方法【纯计算】，不就地写 state.world。
        候选 local_date/phase/energy/focus 进 ctx；commit 由 _record_event 在
        确认有效事件后执行——否则空 tick（provider 空 / invalid JSON / 异常）
        会打穿 PR-A 零副作用契约（world 被改但事件没成）。
        """
        state = self.state
        world = state.world
        local_date = world.local_date
        phase = world.phase
        try:
            dt = _dt.datetime.fromtimestamp(now)
            local_date = dt.strftime("%Y-%m-%d")
            phase = _phase_for_hour(dt.hour)
        except Exception:
            pass
        # 能量：相位调制（夜间低，白天中），朝目标回归一步（候选，不写 state）
        eff_phase = phase or LifePhase.AFTERNOON
        target = 0.55
        if eff_phase == LifePhase.SLEEP:
            target = 0.3
        elif eff_phase in (LifePhase.EVENING, LifePhase.NIGHT):
            target = 0.45
        elif eff_phase == LifePhase.MORNING:
            target = 0.7
        cand_energy = world.energy + (target - world.energy) * 0.3
        cand_energy = max(0.0, min(1.0, cand_energy))
        # 焦点：夜间/睡眠低（候选）
        target_focus = 0.3 if eff_phase in (LifePhase.SLEEP, LifePhase.NIGHT) else 0.55
        cand_focus = world.focus + (target_focus - world.focus) * 0.25
        cand_focus = max(0.0, min(1.0, cand_focus))
        return {
            # 当前态（只读）
            "phase": phase,
            "energy": cand_energy,
            "focus": cand_focus,
            "current_activity": state.current_activity,
            # 候选 commit（_record_event 提交到 state.world）
            "_cand_local_date": local_date,
            "_cand_phase": phase,
            "_cand_energy": cand_energy,
            "_cand_focus": cand_focus,
        }

    def _record_event(
        self, event: LifeEvent, emotion_weights: dict, ctx: dict, now: float
    ) -> None:
        """把事件写入 journal（带 V2 字段）并更新 world / 计数。

        PR-B：source=PLANNED_TICK，importance 据 event_type + urgency 规则评分，
        privacy_level 默认 SHAREABLE（可分享，非 user_fact），valence/arousal_delta
        取 LIFE_EVENT_WEIGHTS。ShareIntent 评分留给 PR-C。
        """
        state = self.state
        # issue#43 Wave1：成功一拍即清零失败计数 + 退避 + 告警壁钟（provider 恢复立即复原节律，
        # 下次故障从阈值首次重新响亮告警，不被旧 streak 的告警时间戳压住）。
        self._consecutive_failures = 0
        self._backoff_skip_remaining = 0
        self._last_fail_warn_ts = 0.0
        # bump（仅在确认有效事件后，见 PR-A review HIGH）
        state.last_simulation_time = now
        state.simulation_count += 1
        state.events.append(event)
        state.current_activity = event.text
        if len(state.events) > 50:
            state.events = state.events[-30:]

        # 填充 V2 字段
        event.source = LifeSource.PLANNED_TICK
        event.valence_delta = emotion_weights.get("valence", 0.0)
        event.arousal_delta = emotion_weights.get("arousal", 0.0)
        # importance 规则评分：event_type share_tendency × (0.5 + urgency)
        share_t = emotion_weights.get("share_tendency", 0.0)
        event.importance = max(0.0, min(1.0, share_t * (0.5 + event.urgency)))
        # privacy_level 默认 SHAREABLE（life sim 自造内容，非 user_fact）
        if not event.privacy_level or event.privacy_level == LifePrivacy.INTERNAL:
            event.privacy_level = LifePrivacy.SHAREABLE
        # queued_at 标记入队时间（M11 投递四时点 PR-C 启用，PR-B 先填）
        if not event.queued_at:
            event.queued_at = now

        # world 更新：current_activity_id 用 event_id + 提交相位/能量候选（HIGH1）
        state.world.current_activity_id = event.event_id
        state.world.last_tick_at = now
        if ctx is not None:
            state.world.local_date = ctx.get("_cand_local_date", state.world.local_date)
            state.world.phase = ctx.get("_cand_phase", state.world.phase)
            state.world.energy = ctx.get("_cand_energy", state.world.energy)
            state.world.focus = ctx.get("_cand_focus", state.world.focus)

        # body delta（沿用 Item 54）
        if emotion_weights.get("valence", 0.0) != 0.0 or emotion_weights.get("arousal", 0.0) != 0.0:
            self._apply_to_body_state(emotion_weights)

        # share_tendency 调制 wants_to_share（沿用原逻辑，不改策略）
        if share_t > 0.5 and not event.wants_to_share:
            import random
            if random.random() < share_t * 0.5:
                event.wants_to_share = True

    async def _emit_side_effects(self, event: LifeEvent, emotion_weights: dict, now: float) -> None:
        """事件副作用：outreach / countdown / dirty save（均由 event 门控）。

        PR-C：先评估 ShareIntent，delivery_mode=SILENT 时直接跳过 outreach（只留 journal）。
        Phase 3：在 ShareIntent 评估【之前】先做项目认领 + share_policy 门控 + 技能匹配。
        门控被命中时强制 SILENT（不进 outreach 链路）；技能命中时记触发并标记 success。
        """
        # Phase 3：项目认领（event.project_id 设值供 fragment / consolidation 跟踪）
        project = self._find_project_for_event(event)
        if project is not None:
            event.project_id = project.project_id
            project.last_touched_at = now

        # Phase 3：share_policy 项目级门控（在 ShareIntent 评估前介入，
        # 命中门控的事件被强制 SILENT；不影响项目认领与技能匹配）。
        policy_block = False
        policy_reason = ""
        if event.wants_to_share and project is not None:
            policy_block, policy_reason = self._check_share_policy_gate(event, project)

        # Phase 3：技能匹配 + 触发记录（trigger_event_types 命中 + 冷却放行）
        triggered_skill = self._match_skill(event, now)

        if event.wants_to_share:
            intent = self._evaluate_share_intent(event, emotion_weights, None, now)
            # ctx 传 None（_evaluate_share_intent 内部用 emotion_getter 兜底相位）；
            # 这里用 self.state.world.phase 补 interruptibility，避免再取 ctx。
            intent.interruptibility = self._interruptibility_for_phase(self.state.world.phase)
            # 重算 final（interruptibility 影响评分）+ delivery
            intent.final_score = self._recompute_final(intent)
            intent.delivery_mode = _score_to_delivery(intent.final_score)
            # Phase 3：项目门控覆盖（永远以策略为先 —— 即便 score 高也强制 SILENT）。
            if policy_block:
                intent.delivery_mode = DeliveryMode.SILENT
                intent.reason_code = policy_reason or "policy_gated"
            self._share_intents[intent.intent_id] = intent
            event.share_intent_id = intent.intent_id

            if intent.delivery_mode == DeliveryMode.SILENT:
                # 只留 journal，不进 outreach 链路（v2 §4.6：< 0.25 或被项目策略门控）
                import logging
                logging.getLogger(__name__).debug(
                    "life_sim outreach silent (score=%.2f, reason=%s): event=%s",
                    intent.final_score, intent.reason_code, event.event_id,
                )
            elif self._should_outreach(now):
                await self._do_outreach(event, now, intent, triggered_skill)
                # Phase 3 第一轮 review 修复：milestone 策略放行后，必须把首个未分享的
                # milestone 标 shared，否则 _check_share_policy_gate 会一直放行。
                # 仅当：①确有项目认领 ②策略为 milestone ③门控未阻断 ④outreach 真的发出去
                # （event.shared=True 由 _do_outreach 成功路径设置）才标记。
                if (
                    project is not None
                    and project.share_policy == SHARE_POLICY_MILESTONE
                    and not policy_block
                    and event.shared
                ):
                    for milestone in project.milestones:
                        if milestone not in project.milestones_shared:
                            project.milestones_shared.append(milestone)
                            break  # 一次 outreach 只消费一个 milestone

            # Qzone 说说候选（第三投递汇，PR-Qzone）：默认关，独立于上面私聊 outreach
            # 判定（SILENT/BRIDGE/DIRECT 分支不变，私聊照常走原逻辑）——这里只是
            # "额外可选地"把同一个 intent 也送去广播候选池。本分支零 LLM、不做
            # 净化闸判断（只判白名单/开关/分数），实际草稿生成/闸/发布全在
            # qzone_share.handle_share_intent_candidate 里（模块零 LLM 契约边界）。
            if (
                self.qzone_enabled
                and self._qzone_candidate_callback is not None
                and event.privacy_level == LifePrivacy.SHAREABLE
                and event.source in (
                    LifeSource.PLANNED_TICK,
                    LifeSource.REFLECTION,
                    LifeSource.CONSOLIDATION,
                )
                and intent.final_score >= self.qzone_min_score
            ):
                try:
                    await self._qzone_candidate_callback(event, intent)
                except Exception:
                    import logging
                    logging.getLogger(__name__).debug(
                        "life_sim qzone candidate callback failed", exc_info=True
                    )

        # 二审 HIGH 修复：两个 callback 统一由 event 门控（空 tick 不触发）
        if self._countdown_callback is not None:
            try:
                await self._countdown_callback()
            except Exception:
                pass

        if self._state_dirty_callback is not None:
            try:
                await self._state_dirty_callback()
            except Exception:
                pass

    def _interruptibility_for_phase(self, phase: str) -> float:
        if phase in (LifePhase.SLEEP, LifePhase.NIGHT):
            return 0.25
        if phase == LifePhase.EVENING:
            return 0.5
        return 0.7

    def _recompute_final(self, intent: ShareIntent) -> float:
        w = _SHARE_WEIGHTS
        final = (
            w["content_value"] * intent.content_value
            + w["relationship_value"] * intent.relationship_value
            + w["urgency"] * intent.urgency
            + w["interruptibility"] * intent.interruptibility
            + w["response_likelihood"] * 0.5
            + w["cooldown_penalty"] * intent.cooldown_penalty
            # M8 Guardrail（Phase 2A）：unanswered_penalty 贡献恒为 0，与 _evaluate_share_intent 同口径。
            # scheduler 独占 unanswered 惩罚；真实接入留 Phase 2B，禁止改非零乘子。
            + w["unanswered_penalty"] * 0.0
            + w["privacy_risk"] * intent.privacy_risk
        )
        return max(0.0, min(1.0, final))

    def _log_tick(self, event: LifeEvent, ctx: dict, now: float) -> None:
        """PR-B6：结构化日志（tick 成功时）。供调试/WebUI 追溯。"""
        import logging
        logging.getLogger(__name__).debug(
            "life_sim tick: phase=%s energy=%.2f type=%s share=%s importance=%.2f "
            "source=%s privacy=%s count=%d",
            ctx.get("phase", ""), ctx.get("energy", 0.0),
            event.event_type, event.wants_to_share, event.importance,
            event.source, event.privacy_level, self.state.simulation_count,
        )

    def _parse_response(self, response: str, now: float) -> tuple[LifeEvent, dict] | None:
        """解析 LLM 响应为 (LifeEvent, emotion_weights)。容错处理 JSON 格式。

        PR-B3：返回 tuple（含 emotion_weights），编排器据此填 V2 字段。
        """
        try:
            text = response.strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            if start < 0 or end <= start:
                return None
            data = json.loads(text[start:end])
            activity = str(data.get("activity", ""))
            thought = str(data.get("thought", ""))
            combined = f"{activity}" if not thought else f"{activity}（{thought}）"
            event_type = self._infer_event_type(combined)
            event = LifeEvent(
                text=combined[:200],
                mood=str(data.get("mood", "neutral"))[:20],
                urgency=max(0.0, min(1.0, float(data.get("urgency", 0.0)))),
                timestamp=now,
                wants_to_share=bool(data.get("wants_to_share", False)),
                event_type=event_type,
            )
            emotion_weights = self._apply_event_emotion_weights(event)
            return event, emotion_weights
        except (json.JSONDecodeError, ValueError, TypeError):
            return None

    def _build_prompt(self, now: float, ctx: dict | None = None) -> str:
        """构建 LLM 提示词，包含角色设定、时间、情绪、记忆、节律等上下文。

        PR-B3：ctx 来自 _load_world_context（phase/energy/focus），注入节律约束，
        避免凌晨高能活动等明显节律冲突。ctx 为 None 时退化为旧行为（兼容）。
        """
        import datetime

        dt = datetime.datetime.fromtimestamp(now)
        time_desc = dt.strftime("%H:%M, %A")

        emotion_desc = "neutral"
        emo_dict: dict = {}
        if self._emotion_getter:
            try:
                emo_dict = self._emotion_getter() or {}
                parts = []
                if emo_dict.get("warmth", 0) > 0.3:
                    parts.append("warm")
                if emo_dict.get("tension", 0) > 0.3:
                    parts.append("tense")
                if emo_dict.get("curiosity", 0) > 0.3:
                    parts.append("curious")
                emotion_desc = ", ".join(parts) if parts else "calm"
            except Exception:
                pass

        gap = (
            now - self.state.last_outreach_time
            if self.state.last_outreach_time > 0
            else 99999
        )
        if gap < 3600:
            last_chat_desc = "just now"
        elif gap < 86400:
            last_chat_desc = f"{int(gap / 3600)} hours ago"
        else:
            last_chat_desc = f"{int(gap / 86400)} days ago"

        recent = self.state.current_activity or "nothing in particular"

        # PR-B3：节律约束（来自 world）
        rhythm_hint = ""
        if ctx:
            phase = ctx.get("phase", "")
            energy = float(ctx.get("energy", 0.0))
            if phase == LifePhase.SLEEP or energy < 0.35:
                rhythm_hint = "\n节律提示：当前是夜间/低能量，活动应偏安静、休息、入睡，避免剧烈或兴奋行为。"
            elif phase in (LifePhase.NIGHT, LifePhase.EVENING) and energy < 0.5:
                rhythm_hint = "\n节律提示：当前是傍晚/夜间，活动宜偏舒缓。"
            elif phase == LifePhase.MORNING and energy > 0.6:
                rhythm_hint = "\n节律提示：当前是清晨、能量充足，适合专注或创造性活动。"

        # Wave 5（mood-coherence）：躯体疲惫/低落 → 倾向室内、低能量活动（给 4.9 bad days 当底座）。
        # 复用上面已取的 emo_dict（_emotion_getter → engine.observe()，只读容错）；追加不覆盖。
        # 信号只取 tension/warmth：二者皆在 [-1,1] 量级，阈值与 llm_request_pipeline 一致。
        # 【刻意不用 void_pressure】：它是 void_space.total_pressure() 的【无上界求和】（同源
        # observe() 里其阈值是 >1.0/>5.0，非 0-1），且语义是“表达积压”而非“躯体疲惫”——
        # 一旦纳入会让本提示几乎常驻触发，打穿“坏日子才室内”的意图。
        try:
            if emo_dict.get("tension", 0.0) > 0.6 or emo_dict.get("warmth", 0.0) < -0.1:
                rhythm_hint += "\n躯体提示：当前身体偏疲惫/状态低落，倾向待在室内、做低能量的安静活动。"
        except Exception:
            pass

        persona_desc = "一个有自己生活节奏的虚构角色"
        if self._persona_getter:
            try:
                raw_persona = self._persona_getter()
                if raw_persona:
                    persona_desc = raw_persona[:500]
            except Exception:
                pass

        memory_summary = ""
        if self._memory_summary_getter:
            try:
                summary = self._memory_summary_getter()
                if summary:
                    memory_summary = f"\n最近聊天摘要：{summary[:300]}"
            except Exception:
                pass

        return (
            LIFE_SIMULATION_PROMPT.format(
                persona_desc=persona_desc,
                time_desc=time_desc,
                emotion_desc=emotion_desc,
                last_chat_desc=last_chat_desc,
                recent_activity=recent,
            )
            + rhythm_hint
            + memory_summary
        )

    @staticmethod
    def _infer_event_type(text: str) -> str:
        """从事件文本推断事件类型。

        通过关键词匹配确定最可能的事件类型。
        如果无法匹配，返回空字符串。
        """
        text_lower = text.lower()
        best_type = ""
        best_score = 0
        for event_type, keywords in _EVENT_TYPE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > best_score:
                best_score = score
                best_type = event_type
        return best_type

    def _apply_event_emotion_weights(self, event: LifeEvent) -> dict[str, float]:
        """根据事件类型应用情绪权重，返回 body_state 调制值。

        返回的 dict 包含 valence 和 arousal 的增量，
        以及 share_tendency 用于调制 wants_to_share 判断。
        """
        if not event.event_type or event.event_type not in LIFE_EVENT_WEIGHTS:
            return {"valence": 0.0, "arousal": 0.0, "share_tendency": 0.0}
        return dict(LIFE_EVENT_WEIGHTS[event.event_type])

    def _apply_to_body_state(self, weights: dict[str, float]) -> None:
        """将情绪权重增量应用到当前 body_state。

        通过 body_delta_callback 直接注入到 host 的身体状态。
        """
        delta = {
            "valence": weights.get("valence", 0.0),
            "arousal": weights.get("arousal", 0.0),
        }
        cb = getattr(self, "_body_delta_callback", None)
        if cb:
            try:
                cb(delta)
            except Exception:
                pass

    def _should_outreach(self, now: float) -> bool:
        """检查是否允许主动联系（冷却期、回调是否存在）。"""
        if not self._outreach_callback:
            return False
        if self.state.last_outreach_time > 0:
            gap = now - self.state.last_outreach_time
            if gap < self.outreach_cooldown_seconds:
                return False
        return True

    def _evaluate_share_intent(
        self, event: LifeEvent, emotion_weights: dict, ctx: dict, now: float
    ) -> ShareIntent:
        """PR-C1：规则化评估分享意图（零 LLM，对应 v2 §4.6）。

        评分维度取自可得信号：
        - content_value = event.importance（PR-B 已算）
        - relationship_value 受 warmth 调制（emotion_getter）
        - urgency 复用 event.urgency（L19）
        - interruptibility 据相位（夜间低）
        - cooldown_penalty：距上次 outreach 越近惩罚越大
        - privacy_risk：INTERNAL 偏高，SHAREABLE 低，USER_FACT 不应出现（life sim 不造）
        delivery_mode 由 final_score 阈值映射。unanswered_penalty 在 Phase 2A 不消费
        （贡献 * 0.0，scheduler gate 独占该惩罚）；真实接 scheduler.feedback_pressure（M8
        单一数据源）留到 Phase 2B，须与 origin_session/目标会话正确性一起设计。
        """
        state = self.state
        # relationship_value：warmth 调制
        rel = 0.4
        if self._emotion_getter:
            try:
                emo = self._emotion_getter()
                warmth = float(emo.get("warmth", 0.0))
                rel = max(0.0, min(1.0, 0.3 + warmth * 0.5))
            except Exception:
                pass
        # interruptibility：相位调制（夜间/睡眠低）
        phase = ctx.get("phase", "") if ctx else ""
        if phase in (LifePhase.SLEEP, LifePhase.NIGHT):
            interruptibility = 0.25
        elif phase == LifePhase.EVENING:
            interruptibility = 0.5
        else:
            interruptibility = 0.7
        # cooldown_penalty：距上次 outreach 越近越大
        cooldown_penalty = 0.0
        if state.last_outreach_time > 0:
            since = now - state.last_outreach_time
            cd = self.outreach_cooldown_seconds
            if since < cd:
                cooldown_penalty = 1.0 - (since / cd)  # 越近越接近 1
        # privacy_risk
        if event.privacy_level == LifePrivacy.INTERNAL:
            privacy_risk = 0.5
        elif event.privacy_level == LifePrivacy.USER_FACT:
            privacy_risk = 1.0  # life sim 不应造；若出现则保守不发
        else:
            privacy_risk = 0.1
        # final_score（v2 §4.6 决策公式）
        content_value = float(event.importance)
        urgency = float(event.urgency)
        w = _SHARE_WEIGHTS
        final = (
            w["content_value"] * content_value
            + w["relationship_value"] * rel
            + w["urgency"] * urgency
            + w["interruptibility"] * interruptibility
            + w["response_likelihood"] * 0.5
            + w["cooldown_penalty"] * cooldown_penalty
            # M8 Guardrail（Phase 2A）：unanswered_penalty 贡献恒为 0，不消费。
            # scheduler gate 独占 unanswered 惩罚（feedback_pressure 放大 cooldown）。
            # 真实接 feedback_pressure 留到 Phase 2B，须随 origin_session/目标会话正确性一起设计；
            # 此处禁止改成非零乘子（会与 scheduler 形成双重惩罚）。
            + w["unanswered_penalty"] * 0.0
            + w["privacy_risk"] * privacy_risk
        )
        final = max(0.0, min(1.0, final))
        delivery = _score_to_delivery(final)
        intent = ShareIntent(
            event_id=event.event_id,
            content_value=content_value,
            relationship_value=rel,
            urgency=urgency,
            interruptibility=interruptibility,
            cooldown_penalty=cooldown_penalty,
            privacy_risk=privacy_risk,
            final_score=final,
            delivery_mode=delivery,
            reason_code=f"score_{round(final, 2)}",
            expires_at=now + 1800.0,  # 30min 过期
        )
        self._share_intents[intent.intent_id] = intent
        event.share_intent_id = intent.intent_id
        return intent

    async def _do_outreach(
        self,
        event: LifeEvent,
        now: float,
        intent: ShareIntent | None = None,
        skill: LifeSkill | None = None,
    ):
        """基于生活事件触发主动联系（PR-C：携带 ShareIntent）。

        回调签名扩展为 (reason, mood, intent_dict|None)；旧回调（两参）仍兼容——
        Python 多传一个默认参数不破坏两参调用方。

        Phase 3：dispatch 同时写入 state.outreach_audit（M8 单一数据源补建）。
        skill 在此时记 dispatched，response 到达后由 record_user_response 标 success；
        若 OUTREACH_TIMEOUT_SECONDS 内未到 response，由 _check_outreach_timeouts 标 failure。
        """
        if not self._outreach_callback:
            return
        try:
            reason = f"[life_event] {event.text}"
            intent_dict = None
            if intent is not None:
                intent_dict = {
                    "intent_id": intent.intent_id,
                    "event_id": intent.event_id,
                    "final_score": intent.final_score,
                    "delivery_mode": intent.delivery_mode,
                    "reason_code": intent.reason_code,
                    "expires_at": intent.expires_at,
                }
            cb = self._outreach_callback
            # PR-B/C review MED3：按参数数适配，不用裸 TypeError（会吞回调内部 TypeError）。
            accepts_intent = _callback_accepts_intent(cb)
            if accepts_intent:
                # 三参回调：内部异常不再退化重试，但会被下方 except 兜住（旁路副作用不阻断 tick）
                await cb(reason, event.mood, intent_dict)
            else:
                # 旧两参回调（main.py 实际走三参路径，这里是兜底）
                await cb(reason, event.mood)
            # M11：标 queued_at（已由 _record_event 设），shared 保留兼容
            event.shared = True
            self.state.last_outreach_time = now
            self.state.outreach_count += 1
            # Phase 3 / M8：把 dispatch 写入 outreach_audit（session_key = event.origin_session
            # 优先；缺失则用通配 key "_global"，仍保会话隔离语义——通配 key 不会污染真实会话）。
            self._record_audit_dispatch(event, intent, skill, now)
        except Exception as e:
            # PR-B/C 二审 MED1：outreach 是旁路副作用，不阻断 tick；但必须可观测。
            # 静默 pass 会让真实回调 bug 不可见。记录 warning（含异常类型+消息）。
            import logging
            logging.getLogger(__name__).warning(
                "life_sim outreach callback failed (not retried, not advanced): "
                "%s: %s", type(e).__name__, e,
            )


    # ------------------------------------------------------------------
    # Phase 3：项目认领 / 分享策略门控 / 技能匹配 / outreach 审计
    # ------------------------------------------------------------------

    def _find_project_for_event(self, event: LifeEvent) -> "LifeProject | None":
        """按 event_type 匹配 active 项目。事件无 event_type 或无 active 项目 → None。"""
        if not event.event_type:
            return None
        for proj in self.state.projects:
            if proj.state != "active":
                continue
            if proj.event_type == event.event_type:
                return proj
        return None

    def _check_share_policy_gate(
        self, event: LifeEvent, project: "LifeProject"
    ) -> tuple[bool, str]:
        """项目级分享策略门控：返回 (是否阻断, 原因码)。

        策略：
          - never:     一律阻断（reason=policy_never）
          - milestone: 仅命中里程碑（progress 跨过阈值且未分享）的事件放行；
                       其余事件阻断（reason=policy_milestone）。这里只做读判定，
                       milestone 写入由 LifeConsolidation 在巩固期更新 progress 后处理。
          - casual:    放行
        """
        policy = project.share_policy
        if policy == SHARE_POLICY_NEVER:
            return True, "policy_never"
        if policy == SHARE_POLICY_CASUAL:
            return False, ""
        # milestone：只有当事件携带 milestone 标记时才放行（巩固期写）
        if policy == SHARE_POLICY_MILESTONE:
            # 当前事件不属于任何里程碑窗口 → 强制 silent
            has_unshared_milestone = any(
                m for m in project.milestones if m not in project.milestones_shared
            )
            if not has_unshared_milestone:
                return True, "policy_milestone"
            return False, ""
        # 未知策略保守阻断
        return True, "policy_unknown"

    def _match_skill(self, event: LifeEvent, now: float) -> "LifeSkill | None":
        """按 trigger_event_types 匹配技能；命中且冷却放行 → 标 last_triggered_at 并返回。

        冷却：cooldown_seconds × cooldown_multiplier。multiplier 随 effectiveness 自适应。
        """
        if not event.event_type:
            return None
        for skill in self.state.skills:
            if event.event_type not in skill.trigger_event_types:
                continue
            cooldown = skill.cooldown_seconds * max(SKILL_COOLDOWN_MULT_MIN, min(
                SKILL_COOLDOWN_MULT_MAX, skill.cooldown_multiplier
            ))
            if skill.last_triggered_at > 0 and (now - skill.last_triggered_at) < cooldown:
                continue
            skill.last_triggered_at = now
            return skill
        return None

    @staticmethod
    def _adaptive_cooldown_multiplier(effectiveness: float) -> float:
        """clamp(1 + 2*(1-effectiveness), 1, 4)。effectiveness 越低冷却越长。"""
        raw = 1.0 + 2.0 * (1.0 - max(0.0, min(1.0, effectiveness)))
        return max(SKILL_COOLDOWN_MULT_MIN, min(SKILL_COOLDOWN_MULT_MAX, raw))

    def _audit_session_key(self, event: LifeEvent) -> str:
        """选择 audit 索引 key：origin_session 优先，否则 _global（不污染真实会话）。"""
        return event.origin_session or "_global"

    def _audit_bucket_append(self, key: str, entry: dict) -> None:
        """把 entry 写入 outreach_audit[key]，并维持双重上限。

        - 每会话 FIFO：每个 bucket 最多 OUTREACH_AUDIT_PER_SESSION 条，超出裁旧。
        - 全局 LRU：pop + 重插让 key 走到 dict 末尾（= 最近访问），头部 = 最久未访问；
          会话数超 OUTREACH_AUDIT_MAX_SESSIONS 时从头淘汰。

        第二轮 review 抽出：原 _record_audit_dispatch 内联同样的 pop+裁剪+淘汰逻辑，
        后续 audit kind（响应/超时落地）若想复用此 bucket 形态，统一调本 helper 即可。
        """
        bucket = self.state.outreach_audit.pop(key, None) or []
        bucket.append(entry)
        if len(bucket) > OUTREACH_AUDIT_PER_SESSION:
            # FIFO 裁旧：保留尾部 OUTREACH_AUDIT_PER_SESSION 条
            bucket = bucket[-OUTREACH_AUDIT_PER_SESSION:]
        self.state.outreach_audit[key] = bucket  # 重插至末尾 = LRU 最新
        # 会话数上限：从最旧端（dict 头部 = 最久未访问）淘汰。
        # 注：key 刚 pop+reinsert 到末尾，绝不会出现在头部（除非全局只剩它，但那时
        # len == 1 不会触发循环），所以无需防御性 break。
        while len(self.state.outreach_audit) > OUTREACH_AUDIT_MAX_SESSIONS:
            oldest_key = next(iter(self.state.outreach_audit))
            del self.state.outreach_audit[oldest_key]

    def _record_audit_dispatch(
        self,
        event: LifeEvent,
        intent: ShareIntent | None,
        skill: "LifeSkill | None",
        now: float,
    ) -> None:
        """记录一次 dispatch 到 outreach_audit（M8 数据源 + Phase 3 技能反馈基础）。

        entry: {kind: "dispatch", event_id, intent_id, skill_id|"", ts, response_at: 0, timeout_at: 0}
        裁剪/淘汰由 _audit_bucket_append 统一处理（第二轮 review：bounded-audit 抽 helper）。
        """
        key = self._audit_session_key(event)
        entry = {
            "kind": "dispatch",
            "event_id": event.event_id,
            "intent_id": intent.intent_id if intent else "",
            "skill_id": skill.skill_id if skill else "",
            "ts": now,
            "response_at": 0.0,
            "timeout_at": 0.0,
            "feedback_status": "pending",
        }
        self._audit_bucket_append(key, entry)

    def record_user_response(
        self, session_key: str, now: float | None = None
    ) -> int:
        """M8 数据源：用户回应到达，把该会话中所有 pending dispatch 标 answered。

        返回标记的条数。供 main.py / pipeline 在收到用户消息时调用。
        """
        if not session_key:
            return 0
        ts = now if now is not None else time.time()
        bucket = self.state.outreach_audit.get(session_key)
        if not bucket:
            return 0
        marked = 0
        for entry in bucket:
            if entry.get("feedback_status") == "pending":
                entry["feedback_status"] = "answered"
                entry["response_at"] = ts
                marked += 1
        return marked

    def _check_outreach_timeouts(self, now: float) -> int:
        """扫所有 audit：超过 OUTREACH_TIMEOUT_SECONDS 仍 pending → 标 unanswered。

        返回标记的条数。供 tick 起始扫一遍，让 feedback_pressure 真有数据。
        条目缺 ts 字段（异常 entry）跳过；ts=0.0 是合法值（unix epoch），用 `"ts" in entry`
        判定存在性而非 truthy 判定，避免漏标 epoch=0 的合成测试条目。
        """
        marked = 0
        for bucket in self.state.outreach_audit.values():
            for entry in bucket:
                if entry.get("feedback_status") != "pending":
                    continue
                if "ts" not in entry:
                    continue
                ts = float(entry.get("ts", 0.0) or 0.0)
                if (now - ts) >= OUTREACH_TIMEOUT_SECONDS:
                    entry["feedback_status"] = "unanswered"
                    entry["timeout_at"] = now
                    marked += 1
        return marked

    def pending_share_events(self) -> list[LifeEvent]:
        """获取想分享但尚未被消费/丢弃的事件列表（M11 四时点语义）。

        pending = wants_to_share AND queued_at>0 AND consumed_at==0 AND dropped_at==0。
        shared 字段保留兼容（=queued），但判定改用四时点。
        """
        return [
            e for e in self.state.events
            if e.wants_to_share
            and e.queued_at > 0
            and e.consumed_at == 0
            and e.dropped_at == 0
        ]

    def mark_outreach_dispatched(self, event_id: str, now: float | None = None) -> None:
        """PR-C3：外部桥接成功投递后回写 dispatched_at（pipeline 调用）。"""
        ts = now if now is not None else time.time()
        for e in self.state.events:
            if e.event_id == event_id:
                e.dispatched_at = ts
                e.shared = True
                return

    def mark_outreach_consumed(self, event_id: str, now: float | None = None) -> None:
        """PR-C3：pending context 被下次 LLM 消费后回写 consumed_at（pipeline 调用）。"""
        ts = now if now is not None else time.time()
        for e in self.state.events:
            if e.event_id == event_id:
                e.consumed_at = ts
                e.shared = True
                return

    def mark_outreach_dropped(self, event_id: str, now: float | None = None) -> None:
        """PR-C3：分享意图被 gate 拒绝/过期后回写 dropped_at（pipeline 调用）。"""
        ts = now if now is not None else time.time()
        for e in self.state.events:
            if e.event_id == event_id:
                e.dropped_at = ts
                return

    def mark_outreach_withheld(self, event_id: str, now: float | None = None) -> None:
        """T2-07③ 修复：她自己的门控/迟疑取消了这次投递（bridge gate 拒绝 / 最后一刻
        犹豫收回），回写 LifeEvent.dropped_at（沿用 mark_outreach_dropped 的语义——
        "没发出去"）的同时，同步把 outreach_audit 里对应的 pending 条目标成非惩罚性
        的 "withheld"，而不是留在 "pending"。

        若不这样做：_record_audit_dispatch 写下的 pending 条目会在原地等
        _check_outreach_timeouts 在 OUTREACH_TIMEOUT_SECONDS 后把它标成
        "unanswered"（因为用户在安静时段自然不会在 30 分钟内说话），
        derive_dispatch_policy 再把这个 "unanswered" 计入 feedback_pressure/cooldown
        ——等于她自己收回的发言反过来被记成用户冷淡，正是 T2-07③ 要消灭的场景。

        按 event_id 扫全部 bucket（不局限于 _audit_session_key(e) 算出的单一 key），
        防止 origin_session 与 dispatch 时的 audit key 因竞态或异常路径不一致而漏标。
        """
        ts = now if now is not None else time.time()
        for e in self.state.events:
            if e.event_id == event_id:
                e.dropped_at = ts
                break
        for bucket in self.state.outreach_audit.values():
            for entry in bucket:
                if (
                    entry.get("event_id") == event_id
                    and entry.get("feedback_status") == "pending"
                ):
                    entry["feedback_status"] = "withheld"
                    entry["timeout_at"] = ts

    def life_prompt_fragment(self, limit: int = 3, max_budget: int = 800) -> str:
        """渲染结构化生活上下文片段，供对话 prompt 注入（PR-B4，M5 改名）。

        对应 v2 §4.7 的 [life_world] 结构化摘要（不再是 v1 的朴素文本拼接）：
          - 节律（phase/energy）
          - 当前活动
          - 最近事件（带隐私过滤：private_thought 不入用户可见片段）
          - 关系边界（若 outreach 间隔长）

        max_budget：硬上限字符数（v2 §6.2 prompt 预算稳定）。超限时截尾。
        """
        state = self.state
        recent = [e for e in state.events[-10:] if e.text]
        if not recent and not state.current_activity:
            return ""

        lines: list[str] = ["[life_world]"]
        # 节律
        world = state.world
        if world.phase or world.local_date:
            parts = []
            if world.phase:
                parts.append(world.phase)
            if world.energy < 0.4:
                parts.append("低能量")
            elif world.energy > 0.7:
                parts.append("能量充足")
            if parts:
                lines.append("节律：" + "、".join(parts))
        # 当前活动
        if state.current_activity:
            lines.append(f"当前活动：{state.current_activity}")
        # 最近事件（隐私过滤：private_thought 不进用户可见；按隐私级过滤）
        for e in recent[-limit:]:
            # user_fact 事件不在此处直出（life sim 不应造，若出现也保守）
            if e.privacy_level == LifePrivacy.USER_FACT:
                continue
            # MED-5 去重（handoff §2.3）：已消费/已丢弃的事件不再由 fragment 渲染——
            # 它们已写入 memory（带 life_event_id），改由 recall 注入 memory 持久化版本，
            # 避免 fragment 与 recall 重复注入同一 life event。
            if e.consumed_at > 0 or e.dropped_at > 0:
                continue
            mood = e.mood or ""
            lines.append(f"（{mood}：{e.text}）" if mood else f"（{e.text}）")
        # 关系边界：outreach 间隔长时提示克制
        if state.last_outreach_time > 0:
            gap_h = (time.time() - state.last_outreach_time) / 3600.0
            if gap_h > 12:
                lines.append("关系边界：距上次主动联系较久，发言需克制")

        out = "\n".join(lines)
        if len(out) > max_budget:
            out = out[: max_budget - 3] + "..."
        return out

    def recent_context_for_prompt(self, limit: int = 3) -> str:
        """v1 兼容 alias（M5：迁移到 life_prompt_fragment，旧调用点暂保留）。"""
        return self.life_prompt_fragment(limit=limit)

    def undertone_cue(self, now: float | None = None) -> dict | None:
        """Wave 5（life → 表达底色）：从主导项目状态派生一条【内心底色】线索。

        返回 {"kind": "stalled"|"resolved", "intensity": float[0,1], "mood": str} 或 None。
        纯读、零 LLM、零 IO。【不】暴露项目标题/活动/进度数字——渲染端（fragment._life_line）
        据此出一句脱钩话题的内心天气句，让生活的轻重渗进【不相关】的回答（alive test）。

        - stalled：某 active 项目久未推进（last_touched_at 陈旧 ≥ _LIFE_STALE_S）→ 蔫；
          强度随停滞天数线性爬（_LIFE_STALE_S→_LIFE_STALE_HI_S 封顶 1.0）。
        - resolved：某项目近 _LIFE_RESOLVED_WINDOW_S 内 finished → 松快；强度随时距衰减。
        - 选择：有 stalled 取【最陈旧】的（底色由它生成）；否则取【最近】resolved。蔫盖过轻快。
        """
        if now is None:
            now = time.time()
        try:
            projects = [p for p in self.state.projects if isinstance(getattr(p, "state", None), str)]
        except Exception:
            return None

        best_stalled = None
        best_stale = 0.0
        best_resolved = None
        best_recency = 0.0
        for p in projects:
            try:
                touched = float(getattr(p, "last_touched_at", 0.0) or 0.0)
            except (TypeError, ValueError):
                continue  # 单个项目 ts 脏（字符串/坏值）→ 只跳它，不掀翻整条 cue
            if touched <= 0:
                continue
            if p.state == "active":
                stale = now - touched
                if stale >= _LIFE_STALE_S and stale > best_stale:
                    best_stale, best_stalled = stale, p
            elif p.state == "finished":
                age = now - touched
                if 0 <= age <= _LIFE_RESOLVED_WINDOW_S:
                    recency = 1.0 - age / _LIFE_RESOLVED_WINDOW_S
                    if recency > best_recency:
                        best_recency, best_resolved = recency, p

        mood = self._recent_mood_word()
        if best_stalled is not None:
            span = max(1.0, _LIFE_STALE_HI_S - _LIFE_STALE_S)
            intensity = max(0.0, min(1.0, (best_stale - _LIFE_STALE_S) / span))
            return {"kind": "stalled", "intensity": intensity, "mood": mood}
        if best_resolved is not None:
            return {"kind": "resolved", "intensity": max(0.0, min(1.0, best_recency)), "mood": mood}
        return None

    # ------------------------------------------------------------------
    # T2-03：去忙收尾——behavior.py 的 winddown 激活 + integration 的收尾窗口时长，
    # 都需要只读地取"她现在多容易被打断/在忙什么"，不碰 tick/写状态。
    # ------------------------------------------------------------------

    def interruptibility(self) -> float:
        """当下相位的可打断度 [0,1]，越低越"正忙着"。纯读，复用 outreach 评分同一份公式
        （_interruptibility_for_phase），不另立一套阈值（防两处漂移）。"""
        return self._interruptibility_for_phase(self.state.world.phase)

    def current_activity_duration_min(self) -> int | None:
        """当前活动的预期时长（分钟），据最近一条事件的 event_type 估算典型时长
        （_ACTIVITY_TYPICAL_DURATION_MIN，红队 MAJOR 修复：见该表上方注释，此前的
        plan-anchor 匹配是死代码）。

        无事件 / event_type 未知（旧档、LLM 越界输出）→ None（调用方自行给默认值，
        不臆造）。
        """
        events = self.state.events
        if not events:
            return None
        et = str(getattr(events[-1], "event_type", "") or "").strip().lower()
        return _ACTIVITY_TYPICAL_DURATION_MIN.get(et)

    def _recent_mood_word(self) -> str:
        """取最近一条非 USER_FACT 事件的 mood 单词（隐私安全：不读 text/private_thought）。"""
        try:
            for e in reversed(self.state.events):
                if getattr(e, "privacy_level", "") == LifePrivacy.USER_FACT:
                    continue
                m = getattr(e, "mood", "")
                if isinstance(m, str) and m.strip():
                    return m.strip()[:8]
        except Exception:
            pass
        return ""

    def to_dict(self) -> dict[str, Any]:
        return self.state.to_dict()

    def from_dict(self, data: dict[str, Any]):
        self.state = LifeSimulationState.from_dict(data)


# ---------------------------------------------------------------------------
# Item 31: 梦境生成系统
# ---------------------------------------------------------------------------


class DreamGenerator:
    """梦境生成：离线时基于记忆和伤痕生成碎片化梦境。"""

    def __init__(self):
        self._last_dream: str = ""
        self._dream_time: float = 0

    def should_dream(self, offline_hours: float) -> bool:
        """离线超过 6h 且距上次做梦超过 12h。"""
        return offline_hours > 6 and (time.time() - self._dream_time > 43200)

    def generate_dream(
        self,
        recent_memories: list[str],
        scar_count: int,
        void_pressure: float,
    ) -> str:
        """基于记忆碎片和状态生成梦境叙事。"""
        import random

        # 从记忆中随机抽取 2-3 条作为素材
        fragments = (
            random.sample(recent_memories, min(3, len(recent_memories)))
            if recent_memories
            else ["模糊的影子"]
        )

        # 根据伤痕数量决定梦境基调
        if scar_count > 5:
            tone = "不安的"
        elif void_pressure > 2:
            tone = "压抑的"
        else:
            tone = "平静的"

        # 拼接碎片化梦境
        dream_parts = [f"做了一个{tone}梦"]
        for frag in fragments:
            # 截取记忆片段的关键词
            short = frag[:20] if len(frag) > 20 else frag
            dream_parts.append(f"梦里出现了关于「{short}」的画面")

        if void_pressure > 3:
            dream_parts.append("梦的最后有什么想说却说不出口")

        self._last_dream = "……".join(dream_parts)
        self._dream_time = time.time()
        return self._last_dream

    def has_dream_to_share(self) -> bool:
        return bool(self._last_dream) and time.time() - self._dream_time < 3600

    def consume_dream(self) -> str:
        dream = self._last_dream
        self._last_dream = ""
        return dream
