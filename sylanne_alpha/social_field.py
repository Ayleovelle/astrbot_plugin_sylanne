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
        self._groups: dict[str, _GroupState] = {}  # group_id → 群组状态
        self._bot_names: list[str] = []  # 机器人名字列表（用于提及检测）
        self._continuation_tau: float = 60.0  # 对话延续的时间常数（秒）
        self._config: dict = {}
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
                depth * math.log(gs.silence_ticks + 1) * beta * 0.1
            )
        gs.social_void_pressure = min(5.0, gs.social_void_pressure)

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
        gs.social_void_pressure *= 0.3  # 回复后虚空压力大幅衰减
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
        # 群聊安静时虚空压力缓慢衰减
        gs.social_void_pressure *= 0.98

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
        alpha = 0.3
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
