"""Sylanne 多智能体认知架构（CP8-P3）。

SelfCore（主席/编排器）+ 9 个认知 worker（记忆/人格/情绪/主动/作息/社交/
节奏/自评/表达），围绕 SDK 共振场黑板协作。详见
G:\\claude-data\\plans\\cp8-multiagent-warplan.md §3。
"""

from sylanne_alpha.agents.base import (
    LLM,
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

__all__ = [
    "AgentIntent",
    "CognitiveAgent",
    "VALID_FLAGS",
    "SKIP",
    "RULE",
    "LLM",
    "EventBus",
    "AgentEvent",
    "ResponseObserved",
    "BoundaryBreached",
    "ExpressionDriveHigh",
    "OutreachReady",
    "SelfCore",
    "ComposedInputs",
]
