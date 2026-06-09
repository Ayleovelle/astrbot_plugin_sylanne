"""Agent 间 typed 事件总线（CP8-P3a）。

fire-forget 异步广播：发布者 publish 后立即返回不阻塞，订阅者异步处理。
单向广播无回环 = 无死锁（防 3.0 服务器死锁回归）。事件是固定 schema 的
dataclass（typed），不发自由文本——借 Claude Code「工具化接口」铁律。

agent 间的"通讯"本质是提示：消息影响订阅者下一轮的 decide，最终真相仍由
共振场 tick 收口，消息不构成第二条绕过 tick 的状态通道。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger("astrbot_plugin_sylanne")


# ── 事件契约（typed，固定 schema）──
@dataclass(slots=True)
class AgentEvent:
    """agent 间消息基类。子类用具体字段表达不同信号。"""

    source: str
    session_key: str


@dataclass(slots=True)
class ResponseObserved(AgentEvent):
    """检测到一次回复产出（DialogueAgent → 全队）。"""

    text: str = ""
    confidence: float = 0.0


@dataclass(slots=True)
class BoundaryBreached(AgentEvent):
    """边界压力越界（EmotionAgent → ProactiveAgent 等）。"""

    pressure: float = 0.0


@dataclass(slots=True)
class ExpressionDriveHigh(AgentEvent):
    """表达驱动走高（EmotionAgent → ProactiveAgent / DialogueAgent）。"""

    drive: float = 0.0


@dataclass(slots=True)
class OutreachReady(AgentEvent):
    """主动开口意图就绪（ProactiveAgent → DialogueAgent）。"""

    reason: str = ""
    mood: str = ""


Handler = Callable[[AgentEvent], None]


class EventBus:
    """同步 fire-forget 发布订阅。

    publish 立即把事件分发给所有订阅者（同步调用 handler 但不等返回值语义、
    不 await），handler 异常被吞并记日志，绝不阻塞或冒泡到发布者。
    """

    def __init__(self) -> None:
        self._subs: dict[type, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: Handler) -> None:
        self._subs[event_type].append(handler)

    def publish(self, event: AgentEvent) -> None:
        """fire-forget 广播。handler 异常被隔离，不影响发布者或其他订阅者。"""
        for handler in self._subs.get(type(event), ()):
            try:
                handler(event)
            except Exception as exc:  # 隔离单个 handler 故障
                logger.warning(
                    "Sylanne EventBus: handler %r failed on %s: %s",
                    handler, type(event).__name__, exc,
                )

    def clear(self) -> None:
        self._subs.clear()
