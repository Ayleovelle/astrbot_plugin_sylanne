"""Sylanne 多智能体认知架构（CP8-P3）。

SelfCore（主席/编排器）+ 9 个认知 worker（记忆/人格/情绪/主动/作息/社交/
节奏/自评/表达），围绕 SDK 共振场黑板协作。详见
G:\\claude-data\\plans\\cp8-multiagent-warplan.md §3。
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
from sylanne_alpha.agents.rhythm_agent import RhythmAgent
from sylanne_alpha.agents.emotion_agent import EmotionAgent
from sylanne_alpha.agents.memory_agent import MemoryAgent
from sylanne_alpha.agents.persona_agent import PersonaAgent
from sylanne_alpha.agents.proactive_agent import ProactiveAgent
from sylanne_alpha.agents.life_agent import LifeAgent
from sylanne_alpha.agents.social_agent import SocialAgent
from sylanne_alpha.agents.assessor_agent import AssessorAgent
from sylanne_alpha.agents.dialogue_agent import DialogueAgent

# 9 个认知 worker 的注册清单（供 main 一次性注册进 SelfCore）
ALL_AGENT_CLASSES = [
    RhythmAgent, EmotionAgent, MemoryAgent, PersonaAgent, ProactiveAgent,
    LifeAgent, SocialAgent, AssessorAgent, DialogueAgent,
]

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
    "RhythmAgent",
    "EmotionAgent",
    "MemoryAgent",
    "PersonaAgent",
    "ProactiveAgent",
    "LifeAgent",
    "SocialAgent",
    "AssessorAgent",
    "DialogueAgent",
    "ALL_AGENT_CLASSES",
]
