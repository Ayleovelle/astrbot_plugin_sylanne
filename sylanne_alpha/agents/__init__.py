"""Sylanne 多智能体认知架构（CP8-P3）。

SelfCore（主席/编排器）+ LifeAgent（唯一保留的 AUTONOMOUS 时点 worker），
围绕 SDK 共振场黑板协作。旧的 8 个 per-turn agent（情绪/审议/人格/记忆/
节奏/主动/社交/表达）已退役。
"""

from sylanne_alpha.agents.base import (
    AUTONOMOUS,
    LLM,
    POST,
    PRE,
    RESPONSE_POST,
    RULE,
    SKIP,
    VALID_FLAGS,
    AgentIntent,
    CognitiveAgent,
)
from sylanne_alpha.agents.event_bus import (
    AgentEvent,
    BoundaryBreached,
    EventBus,
    ExpressionDriveHigh,
    OutreachReady,
    ResponseObserved,
)
from sylanne_alpha.agents.self_core import ComposedInputs, SelfCore
from sylanne_alpha.agents.autonomy_scheduler import AutonomyScheduler
from sylanne_alpha.agents.life_agent import LifeAgent

__all__ = [
    "AgentIntent",
    "CognitiveAgent",
    "VALID_FLAGS",
    "SKIP",
    "RULE",
    "LLM",
    "PRE",
    "POST",
    "RESPONSE_POST",
    "AUTONOMOUS",
    "EventBus",
    "AgentEvent",
    "ResponseObserved",
    "BoundaryBreached",
    "ExpressionDriveHigh",
    "OutreachReady",
    "SelfCore",
    "ComposedInputs",
    "AutonomyScheduler",
    "LifeAgent",
]
