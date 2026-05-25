"""Social Field Participation Dynamics (SFPD) — Signal Collector.

Collects social field signals from group chat context and packages them
for the computation spine's L7 phase transition layer.

The decision to speak is NOT made here — it's made by L7's should_express()
with social field signals modulating the threshold and drive.
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass
class SocialSignals:
    """Packaged social field signals for L7 modulation."""
    is_group: bool = False
    is_at_bot: bool = False
    name_mentioned: bool = False
    topic_relevance: float = 0.0
    continuation_strength: float = 0.0
    group_noise_level: float = 0.0
    social_void_pressure: float = 0.0
    sheaf_coupling: float = 0.0


class _GroupState:
    """Per-group tracking state."""
    __slots__ = (
        "last_bot_reply_ts", "recent_bot_topics", "silence_ticks",
        "message_timestamps", "ema_rate", "social_void_pressure",
        "shadow_buffer",
    )

    def __init__(self):
        self.last_bot_reply_ts: float = 0.0
        self.recent_bot_topics: deque[set[str]] = deque(maxlen=10)
        self.silence_ticks: int = 0
        self.message_timestamps: deque[float] = deque(maxlen=30)
        self.ema_rate: float = 0.0
        self.social_void_pressure: float = 0.0
        self.shadow_buffer: deque[dict] = deque(maxlen=20)


class SocialFieldCollector:
    """Collects social field signals from group chat context.

    Does NOT decide whether to respond — only packages signals for L7.
    """

    def __init__(self, config: dict | None = None):
        self._groups: dict[str, _GroupState] = {}
        self._bot_names: list[str] = []
        self._continuation_tau: float = 60.0
        self._config: dict = {}
        if config:
            self.configure(config)

    def configure(self, config: dict) -> None:
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
        """Compute all social field signals for one incoming message."""
        if now is None:
            now = time.time()

        gs = self._get_group(group_id)

        # Update message rate (EMA)
        gs.message_timestamps.append(now)
        self._update_noise_level(gs, now)

        # Name mention detection
        text_lower = text.lower()
        name_mentioned = any(name in text_lower for name in self._bot_names)

        # Topic relevance via keyword overlap
        topic_relevance = self._compute_topic_relevance(text, gs)

        # Continuation strength: exponential decay since last bot reply
        continuation_strength = 0.0
        if gs.last_bot_reply_ts > 0:
            delta_t = now - gs.last_bot_reply_ts
            tau = self._continuation_tau
            continuation_strength = math.exp(-delta_t / max(1.0, tau))

        # Social void pressure accumulation (Void Calculus axiom 3)
        depth = gs.ema_rate
        beta = 1.0 - topic_relevance
        if depth > 0 and gs.silence_ticks > 0:
            gs.social_void_pressure += (
                depth * math.log(gs.silence_ticks + 1) * beta * 0.1
            )
        gs.social_void_pressure = min(5.0, gs.social_void_pressure)

        # Record to shadow buffer for context lookback
        gs.shadow_buffer.append({
            "sender_id": sender_id,
            "text": text[:300],
            "ts": now,
        })

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
        """Called after the bot sends a reply in a group."""
        gs = self._get_group(group_id)
        gs.last_bot_reply_ts = time.time()
        gs.silence_ticks = 0
        gs.social_void_pressure *= 0.3
        gs.shadow_buffer.clear()

        # Track bot topics for relevance computation
        from .memory_system import _tokenize
        tokens = _tokenize(reply_text)
        if tokens:
            gs.recent_bot_topics.append(tokens)

    def drain_shadow_buffer(self, group_id: str) -> list[dict]:
        """Drain and return shadow buffer entries for context injection."""
        gs = self._groups.get(group_id)
        if not gs or not gs.shadow_buffer:
            return []
        entries = list(gs.shadow_buffer)
        gs.shadow_buffer.clear()
        return entries

    def tick_silence(self, group_id: str) -> None:
        """Called per message even when not responding — tracks silence."""
        gs = self._get_group(group_id)
        gs.silence_ticks += 1
        # Decay void pressure slowly when group is quiet
        gs.social_void_pressure *= 0.98

    def is_group_context(self, event: Any) -> bool:
        """Auto-detect group vs private from event object."""
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
        """Extract group_id from event object."""
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
        """Update EMA of messages per minute."""
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
        """Keyword overlap between incoming text and recent bot topics."""
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

    def set_personality_params(self, pressure_rate: float, pressure_cap: float,
                               post_reply_decay: float, inactive_decay: float,
                               ema_alpha: float):
        """Set personality-derived social field dynamics.

        Args:
            pressure_rate: multiplier for void pressure accumulation per tick
            pressure_cap: maximum social void pressure
            post_reply_decay: pressure decay factor after bot replies
            inactive_decay: per-tick pressure decay when group is quiet
            ema_alpha: EMA smoothing factor for message rate
        """
        self._pressure_rate = pressure_rate
        self._pressure_cap = pressure_cap
        self._post_reply_decay = post_reply_decay
        self._inactive_decay = inactive_decay
        self._ema_alpha = ema_alpha
