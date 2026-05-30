"""Sylanne-Embodiment: 社交场域参与动力学（SFPD）— 信号收集器。

从群聊上下文中收集社交场域信号，打包后交给计算栈的 L7 相变层处理。

关键设计决策：
- 是否发言的决定不在这里做——由 L7 的 should_express() 决定
- 本模块只负责"感知"社交场域的状态，不负责"行动"
- 社交场域信号会调制 L7 的表达阈值和驱力

与其他组件的关系：
- 输入：群聊消息事件（来自 AstrBot 事件系统）
- 输出：SocialSignals 数据包，供 L7 相变层使用
- 依赖 memory_system._tokenize 进行话题相关性计算
- 与 relational_sheaf 通过 sheaf_coupling 参数耦合
"""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass
class SocialSignals:
    """打包的社交场域信号，供 L7 相变层调制使用。

    各字段含义：
    - is_group: 是否群聊上下文
    - is_at_bot: 是否 @了机器人
    - name_mentioned: 是否提到了机器人名字
    - topic_relevance: 话题与机器人近期话题的相关度 [0,1]
    - continuation_strength: 对话延续强度（距上次回复的时间衰减）
    - group_noise_level: 群聊噪声水平（消息频率的 EMA）
    - social_void_pressure: 社交虚空压力（沉默积累的表达冲动）
    - sheaf_coupling: 来自关系层析的耦合强度
    """

    is_group: bool = False
    is_at_bot: bool = False
    name_mentioned: bool = False
    topic_relevance: float = 0.0
    continuation_strength: float = 0.0
    group_noise_level: float = 0.0
    social_void_pressure: float = 0.0
    sheaf_coupling: float = 0.0


class _GroupState:
    """单个群组的追踪状态（内部使用）。"""

    __slots__ = (
        "last_bot_reply_ts",
        "recent_bot_topics",
        "silence_ticks",
        "message_timestamps",
        "ema_rate",
        "social_void_pressure",
        "shadow_buffer",
    )

    def __init__(self):
        self.last_bot_reply_ts: float = 0.0  # 上次机器人回复的时间戳
        self.recent_bot_topics: deque[set[str]] = deque(maxlen=10)  # 近期机器人话题词集
        self.silence_ticks: int = 0  # 连续沉默的消息计数
        self.message_timestamps: deque[float] = deque(maxlen=30)  # 消息时间戳窗口
        self.ema_rate: float = 0.0  # 消息频率的指数移动平均
        self.social_void_pressure: float = 0.0  # 社交虚空压力累积
        self.shadow_buffer: deque[dict] = deque(maxlen=20)  # 旁观消息缓冲区


class SocialFieldCollector:
    """社交场域信号收集器。

    只收集和计算信号，不做发言决策。
    每个群组维护独立的状态追踪。

    与其他组件的关系：
    - 被插件主循环在每条群消息到达时调用 collect()
    - 机器人回复后调用 notify_bot_replied() 更新状态
    - drain_shadow_buffer() 供 ConversationBuffer 注入旁观上下文
    """

    def __init__(self, config: dict | None = None):
        self._groups: dict[str, _GroupState] = {}
        self._bot_names: list[str] = []
        self._continuation_tau: float = 60.0
        self._config: dict = {}
        self._pressure_rate: float = 0.1
        self._pressure_cap: float = 5.0
        self._post_reply_decay: float = 0.3
        self._inactive_decay: float = 0.98
        self._ema_alpha: float = 0.3
        if config:
            self.configure(config)

    def configure(self, config: dict) -> None:
        """从配置字典中提取机器人名字和参数。"""
        self._config = config
        persona = config.get("sylanne_persona_name", "")
        triggers = config.get("sylanne_group_attention_trigger_names", [])
        names: list[str] = []
        if persona:
            names.append(persona.lower())
        if isinstance(triggers, list):
            names.extend(n.lower() for n in triggers if n)
        elif isinstance(triggers, str) and triggers:
            names.append(triggers.lower())
        self._bot_names = names
        self._continuation_tau = float(config.get("continuation_tau", 60.0))

    def _get_group(self, group_id: str) -> _GroupState:
        """获取或创建群组状态。群组数上限 100，超出时淘汰最早的。"""
        if group_id not in self._groups:
            if len(self._groups) >= 100:
                oldest_key = next(iter(self._groups))
                del self._groups[oldest_key]
            self._groups[group_id] = _GroupState()
        return self._groups[group_id]

    def collect(
        self,
        *,
        group_id: str,
        sender_id: str,
        text: str,
        is_at_bot: bool = False,
        sheaf_coupling: float = 0.0,
        now: float | None = None,
    ) -> SocialSignals:
        """计算一条群消息的全部社交场域信号。

        参数:
            group_id: 群组标识
            sender_id: 发送者标识
            text: 消息文本
            is_at_bot: 是否 @了机器人
            sheaf_coupling: 来自关系层析的耦合强度
            now: 当前时间戳（默认 time.time()）

        返回:
            打包好的 SocialSignals 数据
        """
        if now is None:
            now = time.time()

        gs = self._get_group(group_id)

        # 更新消息频率（EMA）
        gs.message_timestamps.append(now)
        self._update_noise_level(gs, now)

        # 名字提及检测
        text_lower = text.lower()
        name_mentioned = any(name in text_lower for name in self._bot_names)

        # 话题相关性：与机器人近期话题的关键词重叠度
        topic_relevance = self._compute_topic_relevance(text, gs)

        # 对话延续强度：距上次机器人回复的指数衰减
        continuation_strength = 0.0
        if gs.last_bot_reply_ts > 0:
            delta_t = now - gs.last_bot_reply_ts
            tau = self._continuation_tau
            continuation_strength = math.exp(-delta_t / max(1.0, tau))

        # 社交虚空压力累积（Void Calculus 公理 3）
        # depth=消息频率, beta=话题不相关度, 沉默越久压力越大
        depth = gs.ema_rate
        beta = 1.0 - topic_relevance
        if depth > 0 and gs.silence_ticks > 0:
            gs.social_void_pressure += (
                depth * math.log(gs.silence_ticks + 1) * beta * self._pressure_rate
            )
        gs.social_void_pressure = min(self._pressure_cap, gs.social_void_pressure)

        # bot 未回复此消息 → 递增沉默计数
        self.tick_silence(group_id)

        # 记录到旁观缓冲区（供后续上下文注入）
        gs.shadow_buffer.append(
            {
                "sender_id": sender_id,
                "text": text[:300],
                "ts": now,
            }
        )

        return SocialSignals(
            is_group=True,
            is_at_bot=is_at_bot,
            name_mentioned=name_mentioned,
            topic_relevance=topic_relevance,
            continuation_strength=continuation_strength,
            group_noise_level=gs.ema_rate,
            social_void_pressure=gs.social_void_pressure,
            sheaf_coupling=sheaf_coupling,
        )

    def notify_bot_replied(self, group_id: str, reply_text: str) -> None:
        """机器人在群中发送回复后调用，重置相关状态。"""
        gs = self._get_group(group_id)
        gs.last_bot_reply_ts = time.time()
        gs.silence_ticks = 0
        gs.social_void_pressure *= self._post_reply_decay
        gs.shadow_buffer.clear()

        # 记录机器人话题词（用于后续话题相关性计算）
        from .memory_system import _tokenize

        tokens = _tokenize(reply_text)
        if tokens:
            gs.recent_bot_topics.append(tokens)

    def drain_shadow_buffer(self, group_id: str) -> list[dict]:
        """取出并清空旁观消息缓冲区，用于上下文注入。"""
        gs = self._groups.get(group_id)
        if not gs or not gs.shadow_buffer:
            return []
        entries = list(gs.shadow_buffer)
        gs.shadow_buffer.clear()
        return entries

    def tick_silence(self, group_id: str) -> None:
        """每条消息（即使不回复）都调用——追踪沉默计数。"""
        gs = self._get_group(group_id)
        gs.silence_ticks += 1
        gs.social_void_pressure *= self._inactive_decay

    def is_group_context(self, event: Any) -> bool:
        """从事件对象自动检测是群聊还是私聊。"""
        unified = getattr(event, "unified_msg_origin", "")
        if isinstance(unified, str) and "Group" in unified:
            return True
        raw = getattr(event, "raw_message", None)
        if raw is not None:
            gid = getattr(raw, "group_id", None)
            if gid:
                return True
        if isinstance(event, dict):
            if "Group" in str(event.get("unified_msg_origin", "")):
                return True
            if event.get("group_id"):
                return True
        return False

    def extract_group_id(self, event: Any) -> str:
        """从事件对象中提取 group_id。"""
        raw = getattr(event, "raw_message", None)
        if raw is not None:
            gid = getattr(raw, "group_id", None)
            if gid:
                return str(gid)
        if isinstance(event, dict):
            gid = event.get("group_id", "")
            if gid:
                return str(gid)
        unified = getattr(event, "unified_msg_origin", "")
        if isinstance(unified, str):
            return unified
        return ""

    def _update_noise_level(self, gs: _GroupState, now: float) -> None:
        """更新消息频率的指数移动平均（EMA）。

        归一化到 [0, 1]：20 条/分钟 = 1.0（极高噪声）。
        """
        if len(gs.message_timestamps) < 2:
            gs.ema_rate = 0.0
            return
        window = now - gs.message_timestamps[0]
        if window <= 0:
            gs.ema_rate = 0.0
            return
        raw_rate = len(gs.message_timestamps) / (window / 60.0)
        # Normalize to [0, 1] — 20 msg/min = 1.0
        normalized = min(1.0, raw_rate / 20.0)
        alpha = self._ema_alpha
        gs.ema_rate = alpha * normalized + (1.0 - alpha) * gs.ema_rate

    def _compute_topic_relevance(self, text: str, gs: _GroupState) -> float:
        """计算来消息与机器人近期话题的关键词重叠度。"""
        if not gs.recent_bot_topics:
            return 0.0
        from .memory_system import _tokenize

        incoming = _tokenize(text)
        if not incoming:
            return 0.0
        # Union of recent bot topic tokens
        bot_tokens: set[str] = set()
        for topic_set in gs.recent_bot_topics:
            bot_tokens.update(topic_set)
        if not bot_tokens:
            return 0.0
        overlap = len(incoming & bot_tokens)
        return min(1.0, overlap / max(1, min(len(incoming), len(bot_tokens))))

    def is_group_context_by_key(self, session_key: str) -> bool:
        return "Group" in session_key or "group" in session_key

    def extract_group_id_from_key(self, session_key: str) -> str:
        if ":" in session_key:
            return session_key.rsplit(":", 1)[0]
        return session_key

    def set_personality_params(
        self,
        pressure_rate: float,
        pressure_cap: float,
        post_reply_decay: float,
        inactive_decay: float,
        ema_alpha: float,
    ):
        """设置人格驱动的社交场域动力学参数。

        参数:
            pressure_rate: 虚空压力累积速率乘数
            pressure_cap: 虚空压力上限
            post_reply_decay: 回复后压力衰减因子
            inactive_decay: 群聊安静时每 tick 的压力衰减因子
            ema_alpha: 消息频率 EMA 的平滑因子
        """
        self._pressure_rate = pressure_rate
        self._pressure_cap = pressure_cap
        self._post_reply_decay = post_reply_decay
        self._inactive_decay = inactive_decay
        self._ema_alpha = ema_alpha


def emotional_resistance(current_intensity: float, inner_order: float) -> float:
    """计算情绪传染的抵抗力。

    当自身情绪强度高且内在秩序感强时，对外部情绪输入的抵抗力更大。
    resistance > 0.7 时，外部情绪输入的影响力应减半。

    Args:
        current_intensity: 当前情绪强度 [0, +inf)
        inner_order: 内在秩序感 [0, 1]

    Returns:
        抵抗力值 [0, 1]
    """
    return min(1.0, current_intensity * inner_order)


class EmotionalInertia:
    """情绪惯性模型——情绪持续越久，越难被外部冲击改变方向。

    类比物理惯性：情绪"质量"随持续时间对数增长，
    只有足够大的"冲量"才能突破惯性改变情绪方向。
    """

    __slots__ = ("_duration", "_direction")

    def __init__(self):
        self._duration: float = 0.0  # 当前情绪持续时间（秒）
        self._direction: float = 0.0  # 当前情绪方向（-1 到 1）

    def mass(self) -> float:
        """情绪质量随持续时间对数增长。

        刚开始时质量为 1.0（容易改变），
        持续 1 小时后质量约 1.69（需要更大冲击才能改变）。
        """
        return 1.0 + math.log1p(self._duration / 3600)

    def can_shift(self, impulse: float) -> bool:
        """判断 impulse 是否足以突破惯性。

        Args:
            impulse: 外部情绪冲量的绝对值

        Returns:
            True 表示冲量足以改变情绪方向
        """
        return abs(impulse) > self.mass() * 0.3

    def update(self, dt: float, new_direction: float) -> None:
        """更新惯性状态。

        如果方向一致则累积持续时间，方向反转则重置。

        Args:
            dt: 时间增量（秒）
            new_direction: 新的情绪方向 [-1, 1]
        """
        if self._direction * new_direction > 0:
            # 同方向，累积
            self._duration += dt
        else:
            # 方向反转，重置
            self._duration = 0.0
        self._direction = new_direction

    @property
    def duration(self) -> float:
        return self._duration

    @property
    def direction(self) -> float:
        return self._direction

    def attempt_shift(self, impulse: float, dt: float) -> tuple[bool, float]:
        """尝试突破情绪惯性。返回 (是否突破, 实际变化量)。

        先根据冲量方向更新惯性，再判断是否突破。
        同向冲量累积惯性；反向冲量不累积，只判断是否突破。

        Args:
            impulse: 外部情绪冲量（带方向）
            dt: 时间增量（秒）

        Returns:
            (breakthrough, actual_change) 元组
        """
        impulse_dir = 1.0 if impulse > 0 else (-1.0 if impulse < 0 else 0.0)
        self.update(dt, impulse_dir)
        if self.can_shift(impulse):
            breakthrough_multiplier = 1.0 + self.mass() * 0.3
            actual_change = impulse * breakthrough_multiplier
            self._duration = 0  # 重置持续时间
            self._direction = 1.0 if impulse > 0 else -1.0
            return True, actual_change
        else:
            # 未突破：只产生微小波动
            actual_change = impulse * 0.1
            return False, actual_change


# ---------------------------------------------------------------------------
# Item 100: 冲突事件溯源日志
# ---------------------------------------------------------------------------


@dataclass
class ConflictEvent:
    """单条冲突事件记录。"""

    timestamp: float
    trigger: str  # 用户输入摘要（截断至 100 字符）
    assessment: str  # 评估结果
    tension_delta: float  # 张力变化量


class ConflictTrace:
    """冲突事件溯源日志——记录张力显著升高的事件，供复盘和模式识别使用。

    只记录 tension_delta > 0.1 的事件，避免噪声淹没关键信号。
    使用固定长度 deque 自动淘汰旧事件。
    """

    def __init__(self, maxlen: int = 20):
        self._events: deque[ConflictEvent] = deque(maxlen=maxlen)

    def record(self, trigger: str, assessment: str, tension_delta: float) -> None:
        """记录一条冲突事件（仅当张力变化显著时）。

        Args:
            trigger: 触发冲突的用户输入摘要
            assessment: 系统对该事件的评估结果
            tension_delta: 张力变化量，>0.1 才会被记录
        """
        if tension_delta > 0.1:
            self._events.append(
                ConflictEvent(time.time(), trigger[:100], assessment, tension_delta)
            )

    def recent(self, n: int = 5) -> list[ConflictEvent]:
        """返回最近 n 条冲突事件。"""
        return list(self._events)[-n:]

    def to_dict(self) -> list[dict]:
        """序列化为字典列表，供持久化或诊断面板使用。"""
        return [
            {
                "timestamp": e.timestamp,
                "trigger": e.trigger,
                "assessment": e.assessment,
                "delta": e.tension_delta,
            }
            for e in self._events
        ]


# ---------------------------------------------------------------------------
# Item 136: 情绪传染方向性模型
# ---------------------------------------------------------------------------


def compute_influence_ratio(
    relationship_age_days: float,
    sylanne_intensity: float,
    user_intensity: float,
    relational_gravity: float,
) -> float:
    """计算情绪传染的方向性比率。

    返回 0-1 的值：
    - 0 = 用户完全影响 Sylanne（Sylanne 被动接收）
    - 1 = Sylanne 完全影响用户（Sylanne 主动辐射）

    默认偏向被用户影响（新关系时 ratio 低）。

    公式：
        ratio = 0.3 + relational_gravity * 0.3
                + min(relationship_age_days / 90, 1) * 0.2
                + (sylanne_intensity - user_intensity) * 0.2

    最终 clamp 到 [0.1, 0.9]，避免完全单向。

    Args:
        relationship_age_days: 关系存续天数（越久 Sylanne 影响力越大）。
        sylanne_intensity: Sylanne 当前情绪强度 [0, 1]。
        user_intensity: 用户当前情绪强度 [0, 1]。
        relational_gravity: 关系引力参数 [0, 1]（人格配置项）。

    Returns:
        影响力比率 [0.1, 0.9]。
    """
    age_factor = min(relationship_age_days / 90.0, 1.0)
    intensity_diff = sylanne_intensity - user_intensity

    ratio = (
        0.3
        + relational_gravity * 0.3
        + age_factor * 0.2
        + intensity_diff * 0.2
    )

    # Clamp to [0.1, 0.9]
    return max(0.1, min(0.9, ratio))


# ---------------------------------------------------------------------------
# Item 140: 情绪传染的延迟效应
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Item 56: 群聊角色感知
# ---------------------------------------------------------------------------


class RoleDetector:
    """群聊中识别每个人的角色：话题发起者/附和者/潜水者。"""

    def __init__(self):
        self._message_counts: dict[str, int] = {}  # speaker -> count
        self._topic_starts: dict[str, int] = {}  # speaker -> topic initiation count
        self._last_active: dict[str, float] = {}  # speaker -> last message time

    def observe(self, speaker: str, is_topic_start: bool, now: float):
        self._message_counts[speaker] = self._message_counts.get(speaker, 0) + 1
        if is_topic_start:
            self._topic_starts[speaker] = self._topic_starts.get(speaker, 0) + 1
        self._last_active[speaker] = now

    def get_role(self, speaker: str, now: float) -> str:
        count = self._message_counts.get(speaker, 0)
        topics = self._topic_starts.get(speaker, 0)
        last = self._last_active.get(speaker, 0)

        if now - last > 1800:  # 30min 没说话
            return "lurker"
        if topics > count * 0.3 and count > 3:
            return "initiator"
        if count > 0 and topics < count * 0.1:
            return "follower"
        return "participant"


# ---------------------------------------------------------------------------
# Item 140: 情绪传染的延迟效应
# ---------------------------------------------------------------------------


class ResonanceDetector:
    """检测用户情绪与 Sylanne 情绪的同步/反相模式。

    通过滑动窗口内的 Pearson 相关系数衡量两者情绪效价的共振程度。
    1 = 完全同步（情绪共鸣），-1 = 完全反相（情绪对抗），0 = 无关。
    """

    def __init__(self, window: int = 5):
        self._user_valences: deque[float] = deque(maxlen=window)
        self._sylanne_valences: deque[float] = deque(maxlen=window)

    def observe(self, user_valence: float, sylanne_valence: float):
        """记录一对情绪效价观测值。"""
        self._user_valences.append(user_valence)
        self._sylanne_valences.append(sylanne_valence)

    def resonance_score(self) -> float:
        """返回 -1 到 1 的共振分数。1=完全同步，-1=完全反相，0=无关。"""
        if len(self._user_valences) < 3:
            return 0.0
        # 简单 Pearson 相关系数
        n = len(self._user_valences)
        u = list(self._user_valences)
        s = list(self._sylanne_valences)
        u_mean = sum(u) / n
        s_mean = sum(s) / n
        cov = sum((u[i] - u_mean) * (s[i] - s_mean) for i in range(n)) / n
        u_std = (sum((x - u_mean) ** 2 for x in u) / n) ** 0.5
        s_std = (sum((x - s_mean) ** 2 for x in s) / n) ** 0.5
        if u_std < 0.01 or s_std < 0.01:
            return 0.0
        return max(-1.0, min(1.0, cov / (u_std * s_std)))

    def is_resonating(self) -> bool:
        """共振分数 > 0.6 时视为正在共振。"""
        return self.resonance_score() > 0.6


class EmotionalContagionDelay:
    """情绪传染延迟：用户情绪不立即传染，需要渗透期。

    模拟真实人际互动中情绪传染的时间延迟——
    对方的情绪不会瞬间影响你，而是需要一段"渗透时间"
    才能真正改变你的内在状态。

    使用固定长度 deque 存储待渗透的情绪信号，
    只有超过 penetration_time 的信号才被视为"已渗透"。
    """

    def __init__(self):
        self._pending_signals: deque[tuple[float, float]] = deque(maxlen=10)  # (timestamp, valence)

    def push(self, valence: float, now: float) -> None:
        """推入一个新的情绪信号。

        Args:
            valence: 情绪效价 [-1, 1]。
            now: 当前时间戳。
        """
        self._pending_signals.append((now, valence))

    def get_effective_valence(self, now: float, penetration_time: float = 120.0) -> float | None:
        """返回已渗透的情绪值。

        只有在队列中停留超过 penetration_time 的信号才被视为已渗透。
        返回所有已渗透信号的平均值。

        Args:
            now: 当前时间戳。
            penetration_time: 渗透时间（秒），默认 2 分钟。

        Returns:
            已渗透的平均情绪效价，或 None（无已渗透信号）。
        """
        matured = [v for t, v in self._pending_signals if now - t >= penetration_time]
        if not matured:
            return None
        return sum(matured) / len(matured)
