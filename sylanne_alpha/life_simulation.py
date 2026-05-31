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
- recent_context_for_prompt() 输出供对话生成时注入上下文
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


@dataclass
class LifeEvent:
    """一个生活事件。"""

    text: str  # 事件描述
    mood: str  # 当前心情
    urgency: float  # 紧迫度 [0,1]
    timestamp: float  # 发生时间
    wants_to_share: bool = False  # 是否想分享给朋友
    shared: bool = False  # 是否已经分享过
    event_type: str = ""  # 事件类型（对应 LifeEventType）


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


@dataclass
class LifeSimulationState:
    """生命模拟的持久化状态。"""

    events: list[LifeEvent] = field(default_factory=list)  # 历史事件列表
    current_activity: str = ""  # 当前正在做的事
    last_simulation_time: float = 0.0  # 上次模拟时间
    last_outreach_time: float = 0.0  # 上次主动联系时间
    simulation_count: int = 0  # 总模拟次数
    outreach_count: int = 0  # 总主动联系次数
    enabled: bool = False  # 是否启用
    _pending_emotion_delta: dict = field(default_factory=dict)  # 待应用的情绪增量

    def to_dict(self) -> dict[str, Any]:
        """序列化状态（只保留最近 20 个事件）。"""
        return {
            "events": [
                {
                    "text": e.text,
                    "mood": e.mood,
                    "urgency": e.urgency,
                    "timestamp": e.timestamp,
                    "wants_to_share": e.wants_to_share,
                    "shared": e.shared,
                }
                for e in self.events[-20:]
            ],
            "current_activity": self.current_activity,
            "last_simulation_time": self.last_simulation_time,
            "last_outreach_time": self.last_outreach_time,
            "simulation_count": self.simulation_count,
            "outreach_count": self.outreach_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LifeSimulationState":
        """从字典恢复状态。"""
        state = cls()
        state.current_activity = data.get("current_activity", "")
        state.last_simulation_time = data.get("last_simulation_time", 0.0)
        state.last_outreach_time = data.get("last_outreach_time", 0.0)
        state.simulation_count = data.get("simulation_count", 0)
        state.outreach_count = data.get("outreach_count", 0)
        for e in data.get("events", []):
            state.events.append(
                LifeEvent(
                    text=e.get("text", ""),
                    mood=e.get("mood", "neutral"),
                    urgency=float(e.get("urgency", 0.0)),
                    timestamp=float(e.get("timestamp", 0.0)),
                    wants_to_share=e.get("wants_to_share", False),
                    shared=e.get("shared", False),
                )
            )
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
    """管理 Sylanne 的模拟独立生活。

    通过后台异步循环定期调用 LLM 生成生活片段，
    当生成的事件标记为"想分享"时，触发主动联系。

    生命周期：
    1. configure() 注入外部依赖（LLM、回调等）
    2. start() 启动后台循环
    3. 循环中：_simulate_tick() → _build_prompt() → LLM → _parse_response()
    4. 如果事件 wants_to_share 且冷却期已过 → _do_outreach()
    5. stop() 停止循环
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config or {}
        self.state = LifeSimulationState()
        self._running = False
        self._task: asyncio.Task | None = None
        self._llm_caller: Callable[..., Awaitable[str]] | None = None  # LLM 调用回调
        self._outreach_callback: Callable[[str, str], Awaitable[None]] | None = (
            None  # 主动联系回调
        )
        self._emotion_getter: Callable[[], dict[str, float]] | None = (
            None  # 情绪状态获取
        )
        self._persona_getter: Callable[[], str] | None = None  # 角色描述获取
        self._memory_summary_getter: Callable[[], str] | None = None  # 记忆摘要获取

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

    def configure(
        self,
        llm_caller: Callable[..., Awaitable[str]] | None = None,
        outreach_callback: Callable[[str, str], Awaitable[None]] | None = None,
        emotion_getter: Callable[[], dict[str, float]] | None = None,
        persona_getter: Callable[[], str] | None = None,
        memory_summary_getter: Callable[[], str] | None = None,
        body_delta_callback: Callable[[dict[str, float]], None] | None = None,
    ):
        """注入外部依赖。所有回调都是可选的。"""
        self._llm_caller = llm_caller
        self._outreach_callback = outreach_callback
        self._emotion_getter = emotion_getter
        self._persona_getter = persona_getter
        self._memory_summary_getter = memory_summary_getter
        self._body_delta_callback = body_delta_callback

    def start(self):
        """启动后台模拟循环。"""
        if not self.enabled or self._running:
            return
        self._running = True
        try:
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._loop())
        except RuntimeError:
            pass

    def stop(self):
        """停止模拟循环。"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None

    async def _loop(self):
        """后台循环：以随机间隔模拟生活事件。"""
        import random

        while self._running and self.enabled:
            try:
                base = self.interval_seconds
                jitter = random.uniform(0.4, 1.8)
                wait = base * jitter
                await asyncio.sleep(wait)
                if not self._running:
                    break
                await self._simulate_tick()
            except asyncio.CancelledError:
                break
            except Exception as _exc:
                import logging

                logging.getLogger(__name__).debug(
                    "life_simulation tick error: %s", _exc
                )
                await asyncio.sleep(60.0)

    async def _simulate_tick(self):
        """执行一次模拟周期。"""
        if not self._llm_caller:
            return

        now = time.time()
        self.state.last_simulation_time = now
        self.state.simulation_count += 1

        prompt = self._build_prompt(now)
        try:
            response = await self._llm_caller(prompt)
            event = self._parse_response(response, now)
        except Exception:
            return

        if event:
            self.state.events.append(event)
            self.state.current_activity = event.text
            if len(self.state.events) > 50:
                self.state.events = self.state.events[-30:]

            # Item 54: 根据事件类型应用情绪权重到 body_state
            emotion_weights = self._apply_event_emotion_weights(event)
            if emotion_weights.get("valence", 0.0) != 0.0 or emotion_weights.get("arousal", 0.0) != 0.0:
                self._apply_to_body_state(emotion_weights)

            # share_tendency 调制 wants_to_share
            share_tendency = emotion_weights.get("share_tendency", 0.0)
            if share_tendency > 0.5 and not event.wants_to_share:
                # 高分享倾向的事件类型可以覆盖 LLM 的判断
                import random
                if random.random() < share_tendency * 0.5:
                    event.wants_to_share = True

            if event.wants_to_share and self._should_outreach(now):
                await self._do_outreach(event, now)

    def _build_prompt(self, now: float) -> str:
        """构建 LLM 提示词，包含角色设定、时间、情绪、记忆等上下文。"""
        import datetime

        dt = datetime.datetime.fromtimestamp(now)
        time_desc = dt.strftime("%H:%M, %A")

        emotion_desc = "neutral"
        if self._emotion_getter:
            try:
                emo = self._emotion_getter()
                parts = []
                if emo.get("warmth", 0) > 0.3:
                    parts.append("warm")
                if emo.get("tension", 0) > 0.3:
                    parts.append("tense")
                if emo.get("curiosity", 0) > 0.3:
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
            + memory_summary
        )

    def _parse_response(self, response: str, now: float) -> LifeEvent | None:
        """解析 LLM 响应为 LifeEvent。容错处理 JSON 格式。"""
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
            return LifeEvent(
                text=combined[:200],
                mood=str(data.get("mood", "neutral"))[:20],
                urgency=max(0.0, min(1.0, float(data.get("urgency", 0.0)))),
                timestamp=now,
                wants_to_share=bool(data.get("wants_to_share", False)),
                event_type=event_type,
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            return None

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
        self.state._pending_emotion_delta = delta

    def _should_outreach(self, now: float) -> bool:
        """检查是否允许主动联系（冷却期、回调是否存在）。"""
        if not self._outreach_callback:
            return False
        if self.state.last_outreach_time > 0:
            gap = now - self.state.last_outreach_time
            if gap < self.outreach_cooldown_seconds:
                return False
        return True

    async def _do_outreach(self, event: LifeEvent, now: float):
        """基于生活事件触发主动联系。"""
        if not self._outreach_callback:
            return
        try:
            reason = f"[life_event] {event.text}"
            await self._outreach_callback(reason, event.mood)
            event.shared = True
            self.state.last_outreach_time = now
            self.state.outreach_count += 1
        except Exception:
            pass

    def pending_share_events(self) -> list[LifeEvent]:
        """获取想分享但尚未分享的事件列表。"""
        return [e for e in self.state.events if e.wants_to_share and not e.shared]

    def recent_context_for_prompt(self, limit: int = 3) -> str:
        """获取近期生活事件作为 LLM 提示词注入的上下文。"""
        recent = [e for e in self.state.events[-10:] if e.text]
        if not recent:
            return ""
        lines = (
            [f"（Sylanne 最近的生活：{self.state.current_activity}）"]
            if self.state.current_activity
            else []
        )
        for e in recent[-limit:]:
            lines.append(f"（{e.mood}：{e.text}）")
        return "\n".join(lines)

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
