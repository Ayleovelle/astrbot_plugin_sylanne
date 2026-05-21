"""Sylanne-Embodiment: Life Simulation Module.

Simulates Sylanne's independent "life" using an external LLM.
Periodically generates life events that may trigger proactive outreach.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable


@dataclass
class LifeEvent:
    text: str
    mood: str
    urgency: float
    timestamp: float
    wants_to_share: bool = False
    shared: bool = False


@dataclass
class LifeSimulationState:
    events: list[LifeEvent] = field(default_factory=list)
    current_activity: str = ""
    last_simulation_time: float = 0.0
    last_outreach_time: float = 0.0
    simulation_count: int = 0
    outreach_count: int = 0
    enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": [
                {"text": e.text, "mood": e.mood, "urgency": e.urgency,
                 "timestamp": e.timestamp, "wants_to_share": e.wants_to_share, "shared": e.shared}
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
        state = cls()
        state.current_activity = data.get("current_activity", "")
        state.last_simulation_time = data.get("last_simulation_time", 0.0)
        state.last_outreach_time = data.get("last_outreach_time", 0.0)
        state.simulation_count = data.get("simulation_count", 0)
        state.outreach_count = data.get("outreach_count", 0)
        for e in data.get("events", []):
            state.events.append(LifeEvent(
                text=e.get("text", ""),
                mood=e.get("mood", "neutral"),
                urgency=float(e.get("urgency", 0.0)),
                timestamp=float(e.get("timestamp", 0.0)),
                wants_to_share=e.get("wants_to_share", False),
                shared=e.get("shared", False),
            ))
        return state


LIFE_SIMULATION_PROMPT = """你是一个创意写作助手。请为以下虚构角色生成一个当前时刻的生活片段。

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
    """Manages Sylanne's simulated independent life."""

    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config or {}
        self.state = LifeSimulationState()
        self._running = False
        self._task: asyncio.Task | None = None
        self._llm_caller: Callable[..., Awaitable[str]] | None = None
        self._outreach_callback: Callable[[str, str], Awaitable[None]] | None = None
        self._emotion_getter: Callable[[], dict[str, float]] | None = None
        self._persona_getter: Callable[[], str] | None = None
        self._memory_summary_getter: Callable[[], str] | None = None

    @property
    def enabled(self) -> bool:
        return bool(self._config.get("sylanne_alpha_life_simulation_enabled", False))

    @property
    def interval_seconds(self) -> float:
        return max(60.0, float(self._config.get("sylanne_alpha_life_simulation_interval_seconds", 1800.0)))

    @property
    def outreach_cooldown_seconds(self) -> float:
        return max(300.0, float(self._config.get("sylanne_alpha_life_simulation_outreach_cooldown_seconds", 3600.0)))

    def configure(
        self,
        llm_caller: Callable[..., Awaitable[str]] | None = None,
        outreach_callback: Callable[[str, str], Awaitable[None]] | None = None,
        emotion_getter: Callable[[], dict[str, float]] | None = None,
        persona_getter: Callable[[], str] | None = None,
        memory_summary_getter: Callable[[], str] | None = None,
    ):
        """Wire up external dependencies."""
        self._llm_caller = llm_caller
        self._outreach_callback = outreach_callback
        self._emotion_getter = emotion_getter
        self._persona_getter = persona_getter
        self._memory_summary_getter = memory_summary_getter

    def start(self):
        """Start the background simulation loop."""
        if not self.enabled or self._running:
            return
        self._running = True
        self._task = asyncio.ensure_future(self._loop())

    def stop(self):
        """Stop the simulation loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None

    async def _loop(self):
        """Background loop: simulate life events at random intervals."""
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
            except Exception:
                await asyncio.sleep(60.0)

    async def _simulate_tick(self):
        """Run one simulation cycle."""
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

            if event.wants_to_share and self._should_outreach(now):
                await self._do_outreach(event, now)

    def _build_prompt(self, now: float) -> str:
        """Build the LLM prompt for life simulation."""
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

        gap = now - self.state.last_outreach_time if self.state.last_outreach_time > 0 else 99999
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

        return LIFE_SIMULATION_PROMPT.format(
            persona_desc=persona_desc,
            time_desc=time_desc,
            emotion_desc=emotion_desc,
            last_chat_desc=last_chat_desc,
            recent_activity=recent,
        ) + memory_summary

    def _parse_response(self, response: str, now: float) -> LifeEvent | None:
        """Parse LLM response into a LifeEvent."""
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
            return LifeEvent(
                text=combined[:200],
                mood=str(data.get("mood", "neutral"))[:20],
                urgency=max(0.0, min(1.0, float(data.get("urgency", 0.0)))),
                timestamp=now,
                wants_to_share=bool(data.get("wants_to_share", False)),
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            return None

    def _should_outreach(self, now: float) -> bool:
        """Check if outreach is allowed (cooldown, callback exists)."""
        if not self._outreach_callback:
            return False
        if self.state.last_outreach_time > 0:
            gap = now - self.state.last_outreach_time
            if gap < self.outreach_cooldown_seconds:
                return False
        return True

    async def _do_outreach(self, event: LifeEvent, now: float):
        """Trigger proactive outreach based on life event."""
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
        """Get events that want to be shared but haven't been yet."""
        return [e for e in self.state.events if e.wants_to_share and not e.shared]

    def recent_context_for_prompt(self, limit: int = 3) -> str:
        """Get recent life events as context for LLM prompt injection."""
        recent = [e for e in self.state.events[-10:] if e.text]
        if not recent:
            return ""
        lines = [f"（Sylanne 最近的生活：{self.state.current_activity}）"] if self.state.current_activity else []
        for e in recent[-limit:]:
            lines.append(f"（{e.mood}：{e.text}）")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return self.state.to_dict()

    def from_dict(self, data: dict[str, Any]):
        self.state = LifeSimulationState.from_dict(data)
