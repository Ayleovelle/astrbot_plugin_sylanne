from __future__ import annotations

import contextvars
import asyncio
import json
import time
import os
import re
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from collections.abc import Sequence
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.api.star import Context, Star, register
from astrbot.core.agent.message import TextPart

try:
    from .emotion_engine import (
        EmotionEngine,
        EmotionObservation,
        EmotionParameters,
        EmotionState,
        PersonaProfile,
        PUBLIC_API_VERSION,
        PUBLIC_MEMORY_SCHEMA_VERSION,
        PUBLIC_PERSONALITY_PROFILE_SCHEMA_VERSION,
        PUBLIC_SCHEMA_VERSION,
        apply_persona_to_parameters,
        build_emotion_memory_payload as build_memory_payload,
        build_persona_profile,
        emotion_state_to_public_payload,
        format_consequence_for_user,
        format_state_for_user,
        heuristic_observation,
        observation_from_llm_text,
        relationship_state_to_public_payload,
    )
    from .psychological_screening import (
        PUBLIC_SCREENING_SCHEMA_VERSION,
        PsychologicalScreeningEngine,
        PsychologicalScreeningParameters,
        PsychologicalScreeningState,
        format_psychological_state_for_user,
        heuristic_psychological_observation,
        psychological_state_to_public_payload,
    )
    from .humanlike_engine import (
        PUBLIC_HUMANLIKE_SCHEMA_VERSION,
        HumanlikeEngine,
        HumanlikeParameters,
        HumanlikeState,
        build_humanlike_memory_annotation,
        build_humanlike_prompt_fragment,
        format_humanlike_state_for_user,
        heuristic_humanlike_observation,
        humanlike_state_to_public_payload,
    )
    from .lifelike_learning_engine import (
        PUBLIC_LIFELIKE_LEARNING_SCHEMA_VERSION,
        LifelikeLearningEngine,
        LifelikeLearningParameters,
        LifelikeLearningState,
        build_lifelike_memory_annotation,
        build_lifelike_prompt_fragment,
        build_proactive_topic_assessment_prompt,
        derive_initiative_policy,
        derive_proactive_speech_decision,
        rank_proactive_topics,
        local_proactive_topic_judgement,
        normalize_proactive_topic_judgement,
        format_lifelike_state_for_user,
        heuristic_lifelike_observation,
        lifelike_state_to_public_payload,
    )
    from .personality_drift_engine import (
        PUBLIC_PERSONALITY_DRIFT_SCHEMA_VERSION,
        PersonalityDriftEngine,
        PersonalityDriftObservation,
        PersonalityDriftParameters,
        PersonalityDriftState,
        apply_personality_drift_to_profile,
        build_personality_drift_memory_annotation,
        build_personality_drift_prompt_fragment,
        format_personality_drift_state_for_user,
        heuristic_personality_drift_observation,
        personality_drift_state_to_public_payload,
    )
    from .moral_repair_engine import (
        PUBLIC_MORAL_REPAIR_SCHEMA_VERSION,
        MoralRepairEngine,
        MoralRepairParameters,
        MoralRepairState,
        build_moral_repair_memory_annotation,
        build_moral_repair_prompt_fragment,
        format_moral_repair_state_for_user,
        heuristic_moral_repair_observation,
        moral_repair_state_to_public_payload,
    )
    from .fallibility_engine import (
        PUBLIC_FALLIBILITY_SCHEMA_VERSION,
        FallibilityEngine,
        FallibilityParameters,
        FallibilityState,
        build_fallibility_memory_annotation,
        build_fallibility_prompt_fragment,
        fallibility_state_to_public_payload,
        format_fallibility_state_for_user,
        heuristic_fallibility_observation,
    )
    from .integrated_self import (
        PUBLIC_INTEGRATED_SELF_SCHEMA_VERSION,
        build_integrated_self_diagnostics,
        build_integrated_self_memory_annotation,
        build_integrated_self_prompt_fragment,
        build_integrated_self_replay_bundle,
        build_integrated_self_snapshot,
        build_state_annotations_memory_envelope,
        format_integrated_self_state_for_user,
        probe_integrated_self_compatibility,
        replay_integrated_self_bundle,
    )
    from .group_atmosphere_engine import (
        PUBLIC_GROUP_ATMOSPHERE_SCHEMA_VERSION,
        GroupAtmosphereEngine,
        GroupAtmosphereParameters,
        GroupAtmosphereState,
        build_group_atmosphere_prompt_fragment,
        group_atmosphere_state_to_public_payload,
        heuristic_group_atmosphere_observation,
    )
    from .memory_engine import (
        MemoryRecallItem,
        PUBLIC_MEMORY_STORE_SCHEMA_VERSION,
        SylanneMemoryState,
        apply_memory_time_decay,
        build_memory_prompt_fragment,
        observe_memory_event,
        recall_memory,
        reinforce_recalled_memories,
    )
    from .prompts import (
        ASSESSOR_SYSTEM_PROMPT,
        LOW_REASONING_ASSESSOR_SYSTEM_PROMPT,
        build_assessment_prompt,
        build_state_injection,
    )
    from .agent_identity import ConversationIdentity, conversation_identity_from_event
    from .realtime_chat_engine import (
        RealtimeChatSettings,
        StickerSettings,
        build_realtime_chat_plan,
        build_sticker_memory_item,
        index_local_stickers,
        merge_sticker_memory,
        realtime_style_prompt_fragment,
    )
    from .realtime_chat_input import (
        RealtimeInputSettings,
        build_realtime_input_hold_injection,
        build_realtime_input_fragment_injection,
        observe_realtime_input_fragment,
    )
except ImportError:
    from emotion_engine import (
        EmotionEngine,
        EmotionObservation,
        EmotionParameters,
        EmotionState,
        PersonaProfile,
        PUBLIC_API_VERSION,
        PUBLIC_MEMORY_SCHEMA_VERSION,
        PUBLIC_PERSONALITY_PROFILE_SCHEMA_VERSION,
        PUBLIC_SCHEMA_VERSION,
        apply_persona_to_parameters,
        build_emotion_memory_payload as build_memory_payload,
        build_persona_profile,
        emotion_state_to_public_payload,
        format_consequence_for_user,
        format_state_for_user,
        heuristic_observation,
        observation_from_llm_text,
        relationship_state_to_public_payload,
    )
    from psychological_screening import (
        PUBLIC_SCREENING_SCHEMA_VERSION,
        PsychologicalScreeningEngine,
        PsychologicalScreeningParameters,
        PsychologicalScreeningState,
        format_psychological_state_for_user,
        heuristic_psychological_observation,
        psychological_state_to_public_payload,
    )
    from humanlike_engine import (
        PUBLIC_HUMANLIKE_SCHEMA_VERSION,
        HumanlikeEngine,
        HumanlikeParameters,
        HumanlikeState,
        build_humanlike_memory_annotation,
        build_humanlike_prompt_fragment,
        format_humanlike_state_for_user,
        heuristic_humanlike_observation,
        humanlike_state_to_public_payload,
    )
    from lifelike_learning_engine import (
        PUBLIC_LIFELIKE_LEARNING_SCHEMA_VERSION,
        LifelikeLearningEngine,
        LifelikeLearningParameters,
        LifelikeLearningState,
        build_lifelike_memory_annotation,
        build_lifelike_prompt_fragment,
        build_proactive_topic_assessment_prompt,
        derive_initiative_policy,
        derive_proactive_speech_decision,
        rank_proactive_topics,
        local_proactive_topic_judgement,
        normalize_proactive_topic_judgement,
        format_lifelike_state_for_user,
        heuristic_lifelike_observation,
        lifelike_state_to_public_payload,
    )
    from personality_drift_engine import (
        PUBLIC_PERSONALITY_DRIFT_SCHEMA_VERSION,
        PersonalityDriftEngine,
        PersonalityDriftObservation,
        PersonalityDriftParameters,
        PersonalityDriftState,
        apply_personality_drift_to_profile,
        build_personality_drift_memory_annotation,
        build_personality_drift_prompt_fragment,
        format_personality_drift_state_for_user,
        heuristic_personality_drift_observation,
        personality_drift_state_to_public_payload,
    )
    from moral_repair_engine import (
        PUBLIC_MORAL_REPAIR_SCHEMA_VERSION,
        MoralRepairEngine,
        MoralRepairParameters,
        MoralRepairState,
        build_moral_repair_memory_annotation,
        build_moral_repair_prompt_fragment,
        format_moral_repair_state_for_user,
        heuristic_moral_repair_observation,
        moral_repair_state_to_public_payload,
    )
    from fallibility_engine import (
        PUBLIC_FALLIBILITY_SCHEMA_VERSION,
        FallibilityEngine,
        FallibilityParameters,
        FallibilityState,
        build_fallibility_memory_annotation,
        build_fallibility_prompt_fragment,
        fallibility_state_to_public_payload,
        format_fallibility_state_for_user,
        heuristic_fallibility_observation,
    )
    from integrated_self import (
        PUBLIC_INTEGRATED_SELF_SCHEMA_VERSION,
        build_integrated_self_diagnostics,
        build_integrated_self_memory_annotation,
        build_integrated_self_prompt_fragment,
        build_integrated_self_replay_bundle,
        build_integrated_self_snapshot,
        build_state_annotations_memory_envelope,
        format_integrated_self_state_for_user,
        probe_integrated_self_compatibility,
        replay_integrated_self_bundle,
    )
    from group_atmosphere_engine import (
        PUBLIC_GROUP_ATMOSPHERE_SCHEMA_VERSION,
        GroupAtmosphereEngine,
        GroupAtmosphereParameters,
        GroupAtmosphereState,
        build_group_atmosphere_prompt_fragment,
        group_atmosphere_state_to_public_payload,
        heuristic_group_atmosphere_observation,
    )
    from memory_engine import (
        MemoryRecallItem,
        PUBLIC_MEMORY_STORE_SCHEMA_VERSION,
        SylanneMemoryState,
        apply_memory_time_decay,
        build_memory_prompt_fragment,
        observe_memory_event,
        recall_memory,
        reinforce_recalled_memories,
    )
    from prompts import (
        ASSESSOR_SYSTEM_PROMPT,
        LOW_REASONING_ASSESSOR_SYSTEM_PROMPT,
        build_assessment_prompt,
        build_state_injection,
    )
    from agent_identity import ConversationIdentity, conversation_identity_from_event
    from realtime_chat_engine import (
        RealtimeChatSettings,
        StickerSettings,
        build_realtime_chat_plan,
        build_sticker_memory_item,
        index_local_stickers,
        merge_sticker_memory,
        realtime_style_prompt_fragment,
    )
    from realtime_chat_input import (
        RealtimeInputSettings,
        build_realtime_input_hold_injection,
        build_realtime_input_fragment_injection,
        observe_realtime_input_fragment,
    )


PLUGIN_NAME = "astrbot_plugin_sylanne"
_INTERNAL_LLM_CALL: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "astrbot_emotional_state_internal_llm_call",
    default=False,
)
PERSONA_MODELING_ENABLED = True
PERSONA_INFLUENCE_STRENGTH = 1.0
RESET_ON_PERSONA_CHANGE = True
BACKGROUND_POST_BASE_WORKERS = 1
BACKGROUND_POST_DYNAMIC_EXTRA_WORKER_CAP = 5
BACKGROUND_POST_TOTAL_WORKER_CAP = (
    BACKGROUND_POST_BASE_WORKERS + BACKGROUND_POST_DYNAMIC_EXTRA_WORKER_CAP
)
INTERNAL_ASSESSOR_LLM_BASE_CONCURRENCY = 2
INTERNAL_ASSESSOR_LLM_BURST_CONCURRENCY = 3
INTERNAL_ASSESSOR_LLM_BURST_READY_THRESHOLD = 32
INTERNAL_ASSESSOR_LLM_BURST_WAIT_SECONDS = 90.0
BACKGROUND_POST_RESOURCE_SAMPLE_TTL_SECONDS = 1.0
BACKGROUND_POST_WORKER_SCALE_MIN_INTERVAL_SECONDS = 2.0
BACKGROUND_POST_WORKER_SCALE_MAX_INTERVAL_SECONDS = 14.0
PROACTIVE_SCHEDULER_CANDIDATE_LIMIT = 64
PROACTIVE_SCHEDULER_CANDIDATE_TTL_SECONDS = 604800.0
PROACTIVE_SCHEDULER_IDLE_DELAY_SECONDS = 300.0
PROACTIVE_SCHEDULER_NORMAL_DELAY_SECONDS = 120.0
PROACTIVE_SCHEDULER_BUSY_DELAY_SECONDS = 240.0
PROACTIVE_SCHEDULER_MAX_CHECKS_PER_ROUND = 2
PROACTIVE_SCHEDULER_SESSION_RECHECK_SECONDS = 180.0
PROACTIVE_CONTEXT_WINDOW_LIMIT = 6
PROACTIVE_CONTEXT_SUMMARY_MAX_CHARS = 1800
PROACTIVE_MEMORY_RECALL_MAX_CHARS = 620
SYLANNE_MEMORY_RECALL_INJECTION_MAX_CHARS = 720
SYLANNE_MEMORY_RECALL_QUERY_MAX_CHARS = 900
INTERRUPTED_REPLY_BREAKPOINT_LIMIT = 4
INTERRUPTED_REPLY_INJECTION_MAX_ITEMS = 1
INTERRUPTED_REPLY_INJECTION_MAX_CHARS = 360
INTERRUPTED_REPLY_LOCAL_MAX_CHARS = 4000
REALTIME_CHAT_INTERRUPT_GRACE_SECONDS = 0.05
REALTIME_ASSISTANT_HISTORY_LIMIT = 3
REALTIME_ASSISTANT_HISTORY_INJECTION_MAX_CHARS = 900
REALTIME_ASSISTANT_HISTORY_EXCERPT_CHARS = 720
REALTIME_INPUT_FRAGMENT_INJECTION_MAX_CHARS = 520
REALTIME_INPUT_HOLD_INJECTION_MAX_CHARS = 360
REALTIME_INPUT_LLM_WAIT_MAX_SECONDS = 20.0


@dataclass
class _BackgroundPostJob:
    event: AstrMessageEvent
    identity: ConversationIdentity
    response_text: str
    request_context_text: str
    sequence: int
    observed_at: float
    input_epoch: int | None = None
    attempts: int = 0
    leased_at: float | None = None
    lease_until: float | None = None
    next_retry_at: float | None = None
    last_error_type: str = ""
    last_error_message: str = ""
    last_failed_at: float | None = None
    dead_lettered_at: float | None = None


@dataclass
class _BackgroundPostResult:
    job: _BackgroundPostJob
    observation: EmotionObservation | None = None
    error: BaseException | None = None
    skipped: bool = False


@dataclass
class _StateInjectionBudget:
    session_key: str
    request_chars_before: int
    request_budget_chars: int
    reserved_chars: int
    max_added_chars: int
    max_parts: int
    compat_mode: str = ""
    added_chars: int = 0
    added_parts: int = 0
    skipped: list[dict[str, Any]] = None
    appended: list[dict[str, Any]] = None

    def __post_init__(self) -> None:
        if self.skipped is None:
            self.skipped = []
        if self.appended is None:
            self.appended = []

    @property
    def effective_total_budget(self) -> int:
        return max(0, self.request_budget_chars - self.reserved_chars)

    @property
    def remaining_total_chars(self) -> int:
        return self.effective_total_budget - self.request_chars_before - self.added_chars

    @property
    def remaining_added_chars(self) -> int:
        return self.max_added_chars - self.added_chars


@dataclass
class _StateInjectionDecision:
    primary_detail: str = "compact"
    compact_mode: str = "snapshot"
    auxiliary_detail: str = "compact"
    emotion_diff_threshold: float = 0.08
    group_diff_threshold: float = 0.08
    force_every_turns: int = 6
    reasons: list[str] | None = None


class _RecoveredBackgroundEvent:
    def __init__(
        self,
        *,
        session_key: str,
        message: str,
        speaker_id: str | None = None,
        speaker_name: str | None = None,
        group_id: str | None = None,
        platform_id: str | None = None,
    ) -> None:
        self.unified_msg_origin = session_key
        self.message_str = message
        self.sender_id = speaker_id or ""
        self.sender_name = speaker_name or ""
        self.group_id = group_id or ""
        self.platform_id = platform_id or ""

    def get_sender_id(self) -> str:
        return self.sender_id

    def get_sender_name(self) -> str:
        return self.sender_name

    def get_group_id(self) -> str:
        return self.group_id

    def get_platform_id(self) -> str:
        return self.platform_id


_REQUIRED_EMOTION_SERVICE_METHODS: tuple[str, ...] = (
    "get_emotion_snapshot",
    "get_emotion_state",
    "get_emotion_values",
    "get_emotion_consequences",
    "get_emotion_relationship",
    "get_emotion_prompt_fragment",
    "build_emotion_memory_payload",
    "inject_emotion_context",
    "observe_emotion_text",
    "get_psychological_screening_snapshot",
    "get_psychological_screening_values",
    "observe_psychological_text",
    "simulate_psychological_update",
    "reset_psychological_screening_state",
    "simulate_emotion_update",
    "reset_emotion_state",
    "get_integrated_self_snapshot",
    "get_integrated_self_prompt_fragment",
    "get_integrated_self_policy_plan",
    "build_integrated_self_replay_bundle",
    "replay_integrated_self_bundle",
    "probe_integrated_self_compatibility",
    "export_integrated_self_diagnostics",
    "get_lifelike_learning_snapshot",
    "get_lifelike_initiative_policy",
    "get_proactive_speech_decision",
    "request_proactive_speech_dispatch",
    "get_realtime_chat_plan",
    "request_realtime_chat_dispatch",
    "observe_user_message_withdrawal",
    "observe_sticker_usage",
    "query_sylanne_memory",
    "get_lifelike_prompt_fragment",
    "observe_lifelike_text",
    "simulate_lifelike_update",
    "reset_lifelike_learning_state",
    "get_personality_drift_snapshot",
    "get_personality_drift_values",
    "get_personality_drift_prompt_fragment",
    "observe_personality_drift_event",
    "simulate_personality_drift_update",
    "reset_personality_drift_state",
    "get_fallibility_snapshot",
    "get_fallibility_values",
    "get_fallibility_prompt_fragment",
    "observe_fallibility_text",
    "simulate_fallibility_update",
    "reset_fallibility_state",
)

_REQUIRED_EMOTION_SERVICE_VERSIONS: dict[str, str] = {
    "emotion_api_version": PUBLIC_API_VERSION,
    "emotion_schema_version": PUBLIC_SCHEMA_VERSION,
    "emotion_memory_schema_version": PUBLIC_MEMORY_SCHEMA_VERSION,
    "personality_profile_schema_version": PUBLIC_PERSONALITY_PROFILE_SCHEMA_VERSION,
    "psychological_screening_schema_version": PUBLIC_SCREENING_SCHEMA_VERSION,
    "integrated_self_schema_version": PUBLIC_INTEGRATED_SELF_SCHEMA_VERSION,
    "lifelike_learning_schema_version": PUBLIC_LIFELIKE_LEARNING_SCHEMA_VERSION,
    "personality_drift_schema_version": PUBLIC_PERSONALITY_DRIFT_SCHEMA_VERSION,
    "fallibility_state_schema_version": PUBLIC_FALLIBILITY_SCHEMA_VERSION,
}


def _has_expected_public_versions(plugin: Any) -> bool:
    return all(
        getattr(plugin, name, None) == expected
        for name, expected in _REQUIRED_EMOTION_SERVICE_VERSIONS.items()
    )


def get_emotional_state_plugin(context: Context) -> Any | None:
    """Return the activated emotional state plugin instance for other plugins."""
    getter = getattr(context, "get_registered_star", None)
    if not callable(getter):
        return None
    metadata = getter(PLUGIN_NAME)
    if not metadata or not getattr(metadata, "activated", True):
        return None
    plugin = getattr(metadata, "star_cls", None)
    if (
        plugin is None
        or not _has_expected_public_versions(plugin)
        or not all(
            callable(getattr(plugin, name, None))
            for name in _REQUIRED_EMOTION_SERVICE_METHODS
        )
    ):
        return None
    return plugin


@register(
    PLUGIN_NAME,
    "pidan",
    "Soulful Yearning Lifelike AstrBot Neural Narrative Engine：维护情绪、人格、记忆、氛围和表达节奏的 Sylanne",
    "2.1.0",
    "",
)
class EmotionalStatePlugin(Star):
    emotion_api_version = PUBLIC_API_VERSION
    emotion_schema_version = PUBLIC_SCHEMA_VERSION
    emotion_memory_schema_version = PUBLIC_MEMORY_SCHEMA_VERSION
    personality_profile_schema_version = PUBLIC_PERSONALITY_PROFILE_SCHEMA_VERSION
    psychological_screening_schema_version = PUBLIC_SCREENING_SCHEMA_VERSION
    humanlike_state_schema_version = PUBLIC_HUMANLIKE_SCHEMA_VERSION
    moral_repair_state_schema_version = PUBLIC_MORAL_REPAIR_SCHEMA_VERSION
    integrated_self_schema_version = PUBLIC_INTEGRATED_SELF_SCHEMA_VERSION
    lifelike_learning_schema_version = PUBLIC_LIFELIKE_LEARNING_SCHEMA_VERSION
    personality_drift_schema_version = PUBLIC_PERSONALITY_DRIFT_SCHEMA_VERSION
    fallibility_state_schema_version = PUBLIC_FALLIBILITY_SCHEMA_VERSION
    group_atmosphere_schema_version = PUBLIC_GROUP_ATMOSPHERE_SCHEMA_VERSION

    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self.base_parameters = self._build_parameters()
        self.engine = EmotionEngine(self.base_parameters)
        self.psychological_engine = PsychologicalScreeningEngine(
            self._build_psychological_parameters(),
        )
        self.humanlike_engine = HumanlikeEngine(self._build_humanlike_parameters())
        self.lifelike_learning_engine = LifelikeLearningEngine(
            self._build_lifelike_learning_parameters(),
        )
        self.personality_drift_engine = PersonalityDriftEngine(
            self._build_personality_drift_parameters(),
        )
        self.moral_repair_engine = MoralRepairEngine(
            self._build_moral_repair_parameters(),
        )
        self.fallibility_engine = FallibilityEngine(
            self._build_fallibility_parameters(),
        )
        self.group_atmosphere_engine = GroupAtmosphereEngine(
            self._build_group_atmosphere_parameters(),
        )
        self._memory_cache: dict[str, EmotionState] = {}
        self._psychological_memory_cache: dict[str, PsychologicalScreeningState] = {}
        self._humanlike_memory_cache: dict[str, HumanlikeState] = {}
        self._lifelike_learning_memory_cache: dict[str, LifelikeLearningState] = {}
        self._personality_drift_memory_cache: dict[str, PersonalityDriftState] = {}
        self._moral_repair_memory_cache: dict[str, MoralRepairState] = {}
        self._fallibility_memory_cache: dict[str, FallibilityState] = {}
        self._group_atmosphere_memory_cache: dict[str, GroupAtmosphereState] = {}
        self._sylanne_memory_cache: dict[str, SylanneMemoryState] = {}
        self._agent_identity_profile_cache: dict[str, dict[str, Any]] = {}
        self._agent_trail_cache: dict[str, deque[dict[str, Any]]] = {}
        self._agent_turn_sequence: dict[str, int] = {}
        self._engine_cache: dict[str, EmotionEngine] = {}
        self._provider_id_cache: dict[str, tuple[float, str | None]] = {}
        self._last_request_text: dict[str, str] = {}
        self._last_state_injection_diagnostics: dict[str, dict[str, Any]] = {}
        self._conversation_input_epoch: dict[str, int] = {}
        self._conversation_pending_response_epochs: dict[str, deque[int]] = {}
        self._realtime_input_fragment_windows: dict[str, dict[str, Any]] = {}
        self._interrupted_reply_breakpoints: dict[str, deque[dict[str, Any]]] = {}
        self._realtime_assistant_history_shadows: dict[str, deque[dict[str, Any]]] = {}
        self._realtime_chat_active_dispatches: dict[str, dict[str, Any]] = {}
        self._realtime_chat_dispatch_tasks: dict[str, set[asyncio.Task[Any]]] = {}
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._background_post_tasks: dict[str, asyncio.Task[Any]] = {}
        self._background_post_queues: dict[str, deque[_BackgroundPostJob]] = {}
        self._background_post_active: dict[str, dict[int, _BackgroundPostJob]] = {}
        self._background_post_sequence: dict[str, int] = {}
        self._background_post_latest_enqueued: dict[str, int] = {}
        self._background_post_last_committed: dict[str, int] = {}
        self._background_post_skipped: dict[str, set[int]] = {}
        self._background_post_dead_letters: dict[str, deque[_BackgroundPostJob]] = {}
        self._background_post_recovered_sessions: set[str] = set()
        self._background_post_checkpoint_tasks: set[asyncio.Task[Any]] = set()
        self._background_post_checkpoint_generation: dict[str, int] = {}
        self._background_post_checkpoint_locks: dict[str, asyncio.Lock] = {}
        self._background_post_worker_state: dict[str, dict[str, Any]] = {}
        self._background_post_resource_cache: dict[str, Any] = {}
        self._internal_assessor_llm_condition: asyncio.Condition | None = None
        self._internal_assessor_llm_condition_loop: Any = None
        self._internal_assessor_llm_inflight = 0
        self._proactive_dispatch_last_sent: dict[str, float] = {}
        self._proactive_dispatch_audit: dict[str, deque[dict[str, Any]]] = {}
        self._proactive_candidate_sessions: dict[str, dict[str, Any]] = {}
        self._proactive_context_windows: dict[str, deque[dict[str, Any]]] = {}
        self._proactive_scheduler_locks: dict[str, asyncio.Lock] = {}
        self._proactive_scheduler_last_checked: dict[str, float] = {}
        self._proactive_scheduler_task: asyncio.Task[Any] | None = None
        self._realtime_chat_last_sent: dict[str, float] = {}
        self._last_realtime_chat_adaptive_settings: dict[str, dict[str, Any]] = {}
        self._sticker_index_cache: dict[str, Any] = {}
        self._sticker_memory_cache: dict[str, list[dict[str, Any]]] = {}
        self._state_injection_snapshot_cache: dict[str, dict[str, Any]] = {}
        self._group_atmosphere_injection_snapshot_cache: dict[str, dict[str, Any]] = {}
        self._terminating = False

    async def terminate(self):
        self._terminating = True
        background_tasks = getattr(self, "_background_tasks", set())
        if background_tasks:
            for task in list(background_tasks):
                task.cancel()
            await asyncio.gather(*background_tasks, return_exceptions=True)
        background_tasks.clear()
        checkpoint_tasks = getattr(self, "_background_post_checkpoint_tasks", set())
        if checkpoint_tasks:
            for task in list(checkpoint_tasks):
                task.cancel()
            await asyncio.gather(*checkpoint_tasks, return_exceptions=True)
        checkpoint_tasks.clear()
        await self._save_all_background_post_checkpoints()
        self._background_post_tasks.clear()
        self._background_post_queues.clear()
        self._background_post_active.clear()
        self._background_post_sequence.clear()
        self._background_post_latest_enqueued.clear()
        self._background_post_last_committed.clear()
        self._background_post_skipped.clear()
        self._background_post_dead_letters.clear()
        self._background_post_recovered_sessions.clear()
        if hasattr(self, "_background_post_checkpoint_generation"):
            self._background_post_checkpoint_generation.clear()
        if hasattr(self, "_background_post_checkpoint_locks"):
            self._background_post_checkpoint_locks.clear()
        scheduler_task = getattr(self, "_proactive_scheduler_task", None)
        if scheduler_task is not None and not scheduler_task.done():
            scheduler_task.cancel()
            await asyncio.gather(scheduler_task, return_exceptions=True)
        self._proactive_scheduler_task = None
        if hasattr(self, "_proactive_candidate_sessions"):
            self._proactive_candidate_sessions.clear()
        if hasattr(self, "_proactive_context_windows"):
            self._proactive_context_windows.clear()
        if hasattr(self, "_proactive_scheduler_locks"):
            self._proactive_scheduler_locks.clear()
        if hasattr(self, "_proactive_scheduler_last_checked"):
            self._proactive_scheduler_last_checked.clear()
        self._memory_cache.clear()
        self._psychological_memory_cache.clear()
        self._humanlike_memory_cache.clear()
        self._lifelike_learning_memory_cache.clear()
        self._personality_drift_memory_cache.clear()
        self._moral_repair_memory_cache.clear()
        self._fallibility_memory_cache.clear()
        self._group_atmosphere_memory_cache.clear()
        self._sylanne_memory_cache.clear()
        self._agent_identity_profile_cache.clear()
        self._agent_trail_cache.clear()
        self._agent_turn_sequence.clear()
        self._realtime_chat_last_sent.clear()
        self._sticker_index_cache.clear()
        self._sticker_memory_cache.clear()
        self._state_injection_snapshot_cache.clear()
        self._group_atmosphere_injection_snapshot_cache.clear()
        self._engine_cache.clear()
        self._provider_id_cache.clear()
        self._last_request_text.clear()
        self._last_state_injection_diagnostics.clear()
        if hasattr(self, "_conversation_input_epoch"):
            self._conversation_input_epoch.clear()
        if hasattr(self, "_conversation_pending_response_epochs"):
            self._conversation_pending_response_epochs.clear()
        if hasattr(self, "_realtime_input_fragment_windows"):
            self._realtime_input_fragment_windows.clear()
        if hasattr(self, "_interrupted_reply_breakpoints"):
            self._interrupted_reply_breakpoints.clear()
        if hasattr(self, "_realtime_assistant_history_shadows"):
            self._realtime_assistant_history_shadows.clear()
        if hasattr(self, "_realtime_chat_active_dispatches"):
            self._realtime_chat_active_dispatches.clear()
        realtime_dispatch_tasks = [
            task
            for tasks in getattr(self, "_realtime_chat_dispatch_tasks", {}).values()
            for task in list(tasks)
            if not task.done()
        ]
        if realtime_dispatch_tasks:
            for task in realtime_dispatch_tasks:
                task.cancel()
            await asyncio.gather(*realtime_dispatch_tasks, return_exceptions=True)
        if hasattr(self, "_realtime_chat_dispatch_tasks"):
            self._realtime_chat_dispatch_tasks.clear()

    @filter.on_llm_request()
    async def on_llm_request(
        self,
        event: AstrMessageEvent,
        request: ProviderRequest,
    ) -> None:
        if _INTERNAL_LLM_CALL.get() or not self._cfg_bool("enabled", True):
            return

        assessment_timing = self._assessment_timing()
        humanlike_enabled = self._humanlike_modeling_enabled()
        lifelike_enabled = self._lifelike_learning_enabled()
        moral_repair_enabled = self._moral_repair_modeling_enabled()
        personality_drift_enabled = self._personality_drift_enabled()
        fallibility_enabled = self._fallibility_modeling_enabled()
        safety_boundary = self._safety_boundary_enabled()
        action_blocking = self._shadow_action_blocking_enabled()
        inject_state = self._cfg_bool("inject_state", True)
        realtime_chat_enabled = self._realtime_chat_enabled()
        identity = self._agent_identity(event, request)
        group_atmosphere_enabled = (
            self._group_atmosphere_modeling_enabled()
            and self._group_atmosphere_applies(identity)
        )
        humanlike_injection_enabled = (
            humanlike_enabled and self._humanlike_injection_enabled()
        )
        lifelike_injection_enabled = (
            lifelike_enabled and self._lifelike_learning_injection_enabled()
        )
        personality_drift_injection_enabled = (
            personality_drift_enabled and self._personality_drift_injection_enabled()
        )
        moral_repair_injection_enabled = (
            moral_repair_enabled and self._moral_repair_injection_enabled()
        )
        fallibility_injection_enabled = (
            fallibility_enabled and self._fallibility_injection_enabled()
        )
        group_atmosphere_injection_enabled = (
            group_atmosphere_enabled and self._group_atmosphere_injection_enabled()
        )
        session_key = identity.conversation_id
        input_epoch = self._bump_conversation_input_epoch(session_key, event=event)
        self._record_conversation_pending_response_epoch(session_key, input_epoch)
        observed_at = self._observed_now()
        current_user_text = self._event_text(event) or str(getattr(request, "prompt", "") or "")
        model_hint = await self._request_model_hint_for_event(event, request)
        early_injection_budget = self._state_injection_budget_for_request(
            session_key,
            request,
            model_hint=model_hint,
        )
        await self._observe_agent_identity(identity, now=observed_at)
        fragment_payload = await self._observe_realtime_input_fragment_context_if_any(
            event,
            request,
            identity,
            current_user_text=current_user_text,
            observed_at=observed_at,
            budget=early_injection_budget,
        )
        if self._realtime_input_fragment_should_hold(fragment_payload):
            if await self._realtime_input_fragment_still_waiting_after_gate(
                event,
                identity,
                fragment_payload,
            ):
                self._discard_conversation_pending_response_epoch(
                    session_key,
                    input_epoch,
                )
                self._mark_realtime_input_fragment_hold(
                    event,
                    request,
                    fragment_payload,
                )
                self._cancel_realtime_chat_dispatches_for_session(
                    session_key,
                    reason="realtime_input_fragment_waiting",
                )
                self._last_request_text[session_key] = self._realtime_input_hold_context_text(
                    request,
                    current_user_text,
                    fragment_payload,
                )
                return
            self._release_realtime_input_fragment_window_if_unchanged(
                session_key,
                fragment_payload,
            )
            if len(fragment_payload.get("fragments") or []) > 1:
                self._append_realtime_input_released_context_if_any(
                    request,
                    fragment_payload,
                    budget=early_injection_budget,
                )
        self._append_realtime_continuity_context_if_any(
            request,
            session_key,
            budget=early_injection_budget,
            current_user_text=current_user_text,
        )
        self._cancel_realtime_chat_dispatches_for_session(
            session_key,
            reason="new_user_message",
        )
        context_text = self._request_to_text(request)
        self._last_request_text[session_key] = context_text
        self._register_proactive_candidate_session(
            event,
            request=request,
            identity=identity,
            context_text=context_text,
            observed_at=observed_at,
        )
        self._maybe_start_proactive_scheduler()
        await self._observe_proactive_dispatch_feedback(
            session_key,
            self._event_text(event) or request.prompt or "",
            observed_at=observed_at,
        )
        if self._sticker_learning_enabled():
            observed_stickers = self._extract_sticker_observations_from_event(event)
            if observed_stickers:
                self._schedule_background_task(
                    self._observe_stickers_background(
                        event,
                        observed_stickers,
                        session_key=session_key,
                    ),
                        label="sticker_usage_observation",
                )
        needs_request_state = (
            assessment_timing in {"pre", "both"}
            or inject_state
            or humanlike_enabled
            or lifelike_enabled
            or moral_repair_enabled
            or personality_drift_enabled
            or fallibility_enabled
            or group_atmosphere_enabled
            or realtime_chat_enabled
            or self._sylanne_memory_enabled()
        )
        if not needs_request_state:
            self._append_realtime_continuity_context_if_any(
                request,
                session_key,
                budget=None,
            )
            await self._append_sylanne_memory_recall_context_if_any(
                request,
                session_key,
                current_user_text=current_user_text,
                budget=None,
            )
            return

        base_persona_profile = await self._persona_profile(event, request)
        personality_drift_state: PersonalityDriftState | None = None
        if personality_drift_enabled:
            personality_drift_state = await self._load_personality_drift_state(
                session_key,
                base_persona_profile,
                now=observed_at,
            )
        persona_profile = await self._runtime_persona_profile(
            session_key,
            base_persona_profile,
            personality_drift_state,
            now=observed_at,
        )
        state = await self._load_state(session_key, persona_profile, now=observed_at)
        engine = self._engine_for_persona(persona_profile)
        before_state = EmotionState.from_dict(state.to_dict())
        current_text = self._agent_current_text(
            event,
            self._realtime_input_merged_intent_from_payload(fragment_payload)
            or self._event_text(event)
            or request.prompt
            or "",
        )
        current_text = self._augment_current_text_with_interruption_event(
            session_key,
            current_text,
        )
        request_observation_text: str | None = None
        humanlike_state: HumanlikeState | None = None
        lifelike_learning_state: LifelikeLearningState | None = None
        moral_repair_state: MoralRepairState | None = None
        fallibility_state: FallibilityState | None = None
        group_atmosphere_state: GroupAtmosphereState | None = None

        if assessment_timing in {"pre", "both"}:
            speaker_state = await self._load_speaker_state(
                identity,
                persona_profile,
                now=observed_at,
            )
            observation = await self._assess_emotion(
                event=event,
                phase="pre_response",
                previous_state=speaker_state or state,
                persona_profile=persona_profile,
                context_text=context_text,
                current_text=current_text,
            )
            state = engine.update(
                state,
                observation,
                profile=persona_profile,
                now=observed_at,
            )
            await self._save_state(session_key, state)
            await self._record_agent_trail(
                session_key,
                identity=identity,
                phase="pre_response",
                module="emotion",
                event="state_updated",
                observed_at=observed_at,
                input_text=current_text,
                before=before_state,
                after=state,
                causes=[
                    {
                        "type": "observation",
                        "label": observation.label,
                        "confidence": observation.confidence,
                        "source": observation.source,
                    },
                ],
            )
            if speaker_state is not None:
                before_speaker_state = EmotionState.from_dict(speaker_state.to_dict())
                speaker_state = engine.update(
                    speaker_state,
                    observation,
                    profile=persona_profile,
                    now=observed_at,
                )
                await self._save_speaker_state(identity, speaker_state)
                await self._record_agent_trail(
                    identity.speaker_track_id or session_key,
                    identity=identity,
                    phase="pre_response",
                    module="emotion.speaker",
                    event="state_updated",
                    observed_at=observed_at,
                    input_text=current_text,
                    before=before_speaker_state,
                    after=speaker_state,
                    causes=[
                        {
                            "type": "observation",
                            "label": observation.label,
                            "confidence": observation.confidence,
                            "source": observation.source,
                        },
                    ],
                )

        auxiliary_load_tasks: dict[str, asyncio.Task[Any]] = {}
        if humanlike_enabled:
            auxiliary_load_tasks["humanlike"] = asyncio.create_task(
                self._load_humanlike_state(
                    session_key,
                    personality_model=self._personality_model_from_profile(
                        persona_profile,
                    ),
                    now=observed_at,
                ),
            )
        if lifelike_enabled:
            auxiliary_load_tasks["lifelike"] = asyncio.create_task(
                self._load_lifelike_learning_state(session_key, now=observed_at),
            )
        if moral_repair_enabled:
            auxiliary_load_tasks["moral_repair"] = asyncio.create_task(
                self._load_moral_repair_state(
                    session_key,
                    personality_model=self._personality_model_from_profile(
                        persona_profile,
                    ),
                    now=observed_at,
                ),
            )
        if fallibility_enabled:
            auxiliary_load_tasks["fallibility"] = asyncio.create_task(
                self._load_fallibility_state(
                    session_key,
                    personality_model=self._personality_model_from_profile(
                        persona_profile,
                    ),
                    now=observed_at,
                ),
            )
        if group_atmosphere_enabled:
            auxiliary_load_tasks["group_atmosphere"] = asyncio.create_task(
                self._load_group_atmosphere_state(
                    session_key,
                    personality_model=self._personality_model_from_profile(
                        persona_profile,
                    ),
                    now=observed_at,
                ),
            )
        if auxiliary_load_tasks:
            await asyncio.gather(*auxiliary_load_tasks.values())

        if humanlike_enabled:
            if request_observation_text is None:
                request_observation_text = self._join_observation_text(
                    context_text,
                    current_text,
                )
            previous_humanlike_state = auxiliary_load_tasks["humanlike"].result()
            observation = heuristic_humanlike_observation(
                request_observation_text,
                source="llm_request",
            )
            humanlike_state = self.humanlike_engine.update(
                previous_humanlike_state,
                observation,
                personality_model=self._personality_model_from_profile(
                    persona_profile,
                ),
                now=observed_at,
            )
            await self._save_humanlike_state(session_key, humanlike_state)

        if lifelike_enabled:
            if request_observation_text is None:
                request_observation_text = self._join_observation_text(
                    context_text,
                    current_text,
                )
            previous_lifelike_state = auxiliary_load_tasks["lifelike"].result()
            observation = heuristic_lifelike_observation(
                request_observation_text,
                source="llm_request",
            )
            lifelike_learning_state = self.lifelike_learning_engine.update(
                previous_lifelike_state,
                observation,
                now=observed_at,
            )
            await self._save_lifelike_learning_state(
                session_key,
                lifelike_learning_state,
            )

        if moral_repair_enabled:
            if request_observation_text is None:
                request_observation_text = self._join_observation_text(
                    context_text,
                    current_text,
                )
            previous_moral_repair_state = auxiliary_load_tasks["moral_repair"].result()
            observation = heuristic_moral_repair_observation(
                request_observation_text,
                source="llm_request",
            )
            moral_repair_state = self.moral_repair_engine.update(
                previous_moral_repair_state,
                observation,
                personality_model=self._personality_model_from_profile(
                    persona_profile,
                ),
                now=observed_at,
            )
            await self._save_moral_repair_state(session_key, moral_repair_state)

        if fallibility_enabled:
            if request_observation_text is None:
                request_observation_text = self._join_observation_text(
                    context_text,
                    current_text,
                )
            previous_fallibility_state = auxiliary_load_tasks["fallibility"].result()
            observation = heuristic_fallibility_observation(
                request_observation_text,
                source="llm_request",
            )
            fallibility_state = self.fallibility_engine.update(
                previous_fallibility_state,
                observation,
                personality_model=self._personality_model_from_profile(
                    persona_profile,
                ),
                now=observed_at,
            )
            await self._save_fallibility_state(session_key, fallibility_state)

        if group_atmosphere_enabled:
            if request_observation_text is None:
                request_observation_text = self._join_observation_text(
                    context_text,
                    current_text,
                )
            previous_group_atmosphere_state = auxiliary_load_tasks[
                "group_atmosphere"
            ].result()
            observation = heuristic_group_atmosphere_observation(
                request_observation_text,
                speaker_id=identity.speaker_id,
                speaker_name=identity.speaker_name,
                recent_speaker_count=len(
                    previous_group_atmosphere_state.recent_speakers,
                )
                + 1,
            )
            group_atmosphere_state = self.group_atmosphere_engine.update(
                previous_group_atmosphere_state,
                observation,
                personality_model=self._personality_model_from_profile(
                    persona_profile,
                ),
                now=observed_at,
            )
            await self._save_group_atmosphere_state(
                session_key,
                group_atmosphere_state,
            )
            await self._record_agent_trail(
                session_key,
                identity=identity,
                phase="llm_request",
                module="group_atmosphere",
                event="state_updated",
                observed_at=observed_at,
                input_text=current_text,
                before=previous_group_atmosphere_state,
                after=group_atmosphere_state,
                causes=[
                    {
                        "type": "observation",
                        "confidence": observation.confidence,
                        "source": observation.source,
                        "reason": observation.reason,
                    },
                ],
            )

        if personality_drift_enabled:
            drift_persona_fingerprint = (
                base_persona_profile.fingerprint
                if base_persona_profile is not None
                else "default"
            )
            previous_personality_drift_state = personality_drift_state
            if previous_personality_drift_state is None:
                previous_personality_drift_state = await self._load_personality_drift_state(
                    session_key,
                    base_persona_profile,
                    now=observed_at,
                )
            emotion_snapshot = state.to_public_dict(
                session_key=session_key,
                include_safety=safety_boundary,
            )
            lifelike_snapshot = (
                lifelike_learning_state.to_public_dict(
                    session_key=session_key,
                    exposure="internal",
                )
                if lifelike_learning_state is not None
                else None
            )
            moral_snapshot = (
                moral_repair_state.to_public_dict(
                    session_key=session_key,
                    exposure="internal",
                    safety_boundary=safety_boundary,
                    action_blocking=action_blocking,
                )
                if moral_repair_state is not None
                else None
            )
            observation = heuristic_personality_drift_observation(
                current_text,
                source="llm_request",
                emotion_snapshot=emotion_snapshot,
                lifelike_snapshot=lifelike_snapshot,
                moral_repair_snapshot=moral_snapshot,
            )
            personality_drift_state = self.personality_drift_engine.update(
                previous_personality_drift_state,
                observation,
                persona_fingerprint=drift_persona_fingerprint,
                now=observed_at,
            )
            personality_drift_changed = self._personality_drift_changed(
                personality_drift_state,
                previous_personality_drift_state,
            )
            if personality_drift_changed:
                await self._save_personality_drift_state(
                    session_key,
                    personality_drift_state,
                )
            else:
                personality_drift_state = previous_personality_drift_state
            if personality_drift_changed and base_persona_profile is not None:
                persona_profile = self._apply_personality_drift(
                    base_persona_profile,
                    personality_drift_state,
                )
                state = self._ensure_persona_state(state, persona_profile)
                engine = self._engine_for_persona(persona_profile)
                await self._save_state(session_key, state)

        if inject_state:
            injection_budget = self._state_injection_budget_for_request(
                session_key,
                request,
                model_hint=model_hint,
            )
            self._append_gemini_visible_output_guard_if_needed(
                request,
                injection_budget,
                model_hint=model_hint,
            )
            self._append_realtime_input_fragment_context_if_any(
                event,
                request,
                identity,
                current_user_text=current_text,
                observed_at=observed_at,
                budget=injection_budget,
            )
            self._append_realtime_continuity_context_if_any(
                request,
                session_key,
                budget=injection_budget,
                current_user_text=current_text,
            )
            injection_decision = self._state_injection_decision(
                session_key,
                state,
                budget=injection_budget,
            )
        else:
            self._append_realtime_input_fragment_context_if_any(
                event,
                request,
                identity,
                current_user_text=current_text,
                observed_at=observed_at,
                budget=None,
            )
            self._append_realtime_continuity_context_if_any(
                request,
                session_key,
                budget=None,
                current_user_text=current_text,
            )
            await self._append_sylanne_memory_recall_context_if_any(
                request,
                session_key,
                current_user_text=current_text,
                budget=None,
            )
        if inject_state:
            appended_emotion = self._append_temp_text_part(
                request,
                self._build_state_injection_for_session(
                    session_key,
                    state,
                    safety_boundary=safety_boundary,
                    commit_snapshot=False,
                    decision=injection_decision,
                ),
                source="emotion",
                budget=injection_budget,
                required=True,
            )
            if appended_emotion:
                self._commit_state_injection_snapshot_for_session(session_key, state)
            elif injection_decision.primary_detail == "full":
                fallback_emotion = self._append_temp_text_part(
                    request,
                    self._build_compact_state_injection(
                        state,
                        safety_boundary=safety_boundary,
                    ),
                    source="emotion.compact_fallback",
                    budget=injection_budget,
                    required=True,
                )
                if fallback_emotion:
                    self._commit_state_injection_snapshot_for_session(session_key, state)
            speaker_state = await self._load_speaker_state(
                identity,
                persona_profile,
                now=observed_at,
            )
            if speaker_state is not None:
                self._append_temp_text_part(
                    request,
                    self._build_speaker_state_injection(
                        identity,
                        speaker_state,
                        safety_boundary=safety_boundary,
                    ),
                    source="emotion.speaker",
                    budget=injection_budget,
                )
            if humanlike_injection_enabled:
                humanlike_state = humanlike_state or await self._load_humanlike_state(
                    session_key,
                    personality_model=self._personality_model_from_profile(
                        persona_profile,
                    ),
                    now=observed_at,
                )
                appended = self._append_temp_text_part(
                    request,
                    self._build_auxiliary_state_injection(
                        "humanlike",
                        lambda: build_humanlike_prompt_fragment(
                            humanlike_state,
                            safety_boundary=safety_boundary,
                        ),
                        decision=injection_decision,
                    ),
                    source="humanlike",
                    budget=injection_budget,
                )
                if not appended and injection_decision.auxiliary_detail == "full":
                    self._append_temp_text_part(
                        request,
                        self._build_compact_auxiliary_state_injection("humanlike"),
                        source="humanlike.compact_fallback",
                        budget=injection_budget,
                    )
            if lifelike_injection_enabled:
                lifelike_learning_state = (
                    lifelike_learning_state
                    or await self._load_lifelike_learning_state(
                        session_key,
                        now=observed_at,
                    )
                )
                appended = self._append_temp_text_part(
                    request,
                    self._build_auxiliary_state_injection(
                        "lifelike_learning",
                        lambda: build_lifelike_prompt_fragment(
                            lifelike_learning_state,
                        ),
                        decision=injection_decision,
                    ),
                    source="lifelike_learning",
                    budget=injection_budget,
                )
                if not appended and injection_decision.auxiliary_detail == "full":
                    self._append_temp_text_part(
                        request,
                        self._build_compact_auxiliary_state_injection("lifelike_learning"),
                        source="lifelike_learning.compact_fallback",
                        budget=injection_budget,
                    )
            if personality_drift_injection_enabled:
                personality_drift_state = (
                    personality_drift_state
                    or await self._load_personality_drift_state(
                        session_key,
                        base_persona_profile,
                        now=observed_at,
                    )
                )
                appended = self._append_temp_text_part(
                    request,
                    self._build_auxiliary_state_injection(
                        "personality_drift",
                        lambda: build_personality_drift_prompt_fragment(
                            personality_drift_state,
                        ),
                        decision=injection_decision,
                    ),
                    source="personality_drift",
                    budget=injection_budget,
                )
                if not appended and injection_decision.auxiliary_detail == "full":
                    self._append_temp_text_part(
                        request,
                        self._build_compact_auxiliary_state_injection("personality_drift"),
                        source="personality_drift.compact_fallback",
                        budget=injection_budget,
                    )
            if moral_repair_injection_enabled:
                moral_repair_state = (
                    moral_repair_state
                    or await self._load_moral_repair_state(
                        session_key,
                        personality_model=self._personality_model_from_profile(
                            persona_profile,
                        ),
                        now=observed_at,
                    )
                )
                appended = self._append_temp_text_part(
                    request,
                    self._build_auxiliary_state_injection(
                        "moral_repair",
                        lambda: build_moral_repair_prompt_fragment(
                            moral_repair_state,
                            safety_boundary=safety_boundary,
                            action_blocking=action_blocking,
                        ),
                        decision=injection_decision,
                    ),
                    source="moral_repair",
                    budget=injection_budget,
                )
                if not appended and injection_decision.auxiliary_detail == "full":
                    self._append_temp_text_part(
                        request,
                        self._build_compact_auxiliary_state_injection("moral_repair"),
                        source="moral_repair.compact_fallback",
                        budget=injection_budget,
                    )
            if fallibility_injection_enabled:
                fallibility_state = fallibility_state or await self._load_fallibility_state(
                    session_key,
                    personality_model=self._personality_model_from_profile(
                        persona_profile,
                    ),
                    now=observed_at,
                )
                appended = self._append_temp_text_part(
                    request,
                    self._build_auxiliary_state_injection(
                        "fallibility",
                        lambda: build_fallibility_prompt_fragment(
                            fallibility_state,
                            safety_boundary=safety_boundary,
                            action_blocking=action_blocking,
                        ),
                        decision=injection_decision,
                    ),
                    source="fallibility",
                    budget=injection_budget,
                )
                if not appended and injection_decision.auxiliary_detail == "full":
                    self._append_temp_text_part(
                        request,
                        self._build_compact_auxiliary_state_injection("fallibility"),
                        source="fallibility.compact_fallback",
                        budget=injection_budget,
                    )
            if group_atmosphere_injection_enabled:
                group_atmosphere_state = (
                    group_atmosphere_state
                    or await self._load_group_atmosphere_state(
                        session_key,
                        personality_model=self._personality_model_from_profile(
                            persona_profile,
                        ),
                        now=observed_at,
                    )
                )
                group_atmosphere_state = self._apply_group_atmosphere_join_cooldown(
                    session_key,
                    group_atmosphere_state,
                    now=observed_at,
                    bot_response=False,
                )
                appended = self._append_temp_text_part(
                    request,
                    self._build_auxiliary_state_injection(
                        "group_atmosphere",
                        lambda: self._build_group_atmosphere_injection_for_session(
                            session_key,
                            group_atmosphere_state,
                            commit_snapshot=False,
                            decision=injection_decision,
                        ),
                        decision=injection_decision,
                    ),
                    source="group_atmosphere",
                    budget=injection_budget,
                )
                if appended:
                    if injection_decision.compact_mode == "diff":
                        self._commit_group_atmosphere_injection_snapshot_for_session(
                            session_key,
                            group_atmosphere_state,
                        )
                elif injection_decision.auxiliary_detail == "full":
                    self._append_temp_text_part(
                        request,
                        self._build_compact_auxiliary_state_injection(
                            "group_atmosphere",
                        ),
                        source="group_atmosphere.compact_fallback",
                        budget=injection_budget,
                    )
            self._record_state_injection_diagnostics(
                injection_budget,
                decision=injection_decision,
            )
            await self._append_sylanne_memory_recall_context_if_any(
                request,
                session_key,
                current_user_text=current_text,
                budget=injection_budget,
            )

        if (
            inject_state
            and realtime_chat_enabled
            and self._cfg_bool(
                "realtime_chat_style_prompt_enabled",
                True,
            )
        ):
            self._append_temp_text_part(
                request,
                realtime_style_prompt_fragment(),
                source="realtime_chat.style",
                budget=(
                    self._state_injection_budget_for_request(session_key, request)
                    if inject_state
                    else None
                ),
            )
        await self._observe_sylanne_memory_event_if_enabled(
            session_key,
            current_text,
            speaker_id=identity.speaker_id,
            emotion_state=state,
            personality_drift_state=personality_drift_state,
            lifelike_learning_state=lifelike_learning_state,
            group_atmosphere_state=group_atmosphere_state,
            observed_at=observed_at,
        )

    @filter.on_llm_response()
    async def on_llm_response(
        self,
        event: AstrMessageEvent,
        response: LLMResponse,
    ) -> None:
        if _INTERNAL_LLM_CALL.get() or not self._cfg_bool("enabled", True):
            return

        response_text = getattr(response, "completion_text", "") or ""
        if not response_text.strip():
            return
        identity = self._agent_identity(event)
        response_epoch = self._consume_conversation_pending_response_epoch(
            identity.conversation_id,
            event,
        )
        if self._conversation_reply_is_stale(identity.conversation_id, response_epoch):
            self._record_interrupted_reply_breakpoint(
                identity.conversation_id,
                reason="late_llm_response_after_user_message",
                input_epoch=response_epoch,
                full_text=response_text,
            )
            self._preserve_intercepted_completion_text(
                response,
                response_text,
                reason="late_llm_response_after_user_message",
                clear_completion=True,
            )
            self._stop_default_response_send(
                event,
                reason="late_llm_response_after_user_message",
            )
            return
        realtime_dispatch_task: asyncio.Task[Any] | None = None
        if self._should_intercept_realtime_chat_response(event, response_text):
            plan = await self.get_realtime_chat_plan(
                event,
                text=response_text,
                session_key=identity.conversation_id,
            )
            plan["input_epoch"] = response_epoch
            plan["media_parts"] = self._extract_realtime_response_media_parts(response)
            if plan.get("message_parts"):
                self._preserve_intercepted_completion_text(
                    response,
                    response_text,
                    reason="realtime_chat_response_intercept",
                )
                self._stop_default_response_send(
                    event,
                    reason="realtime_chat_response_intercept",
                )
                if self._conversation_reply_is_stale(
                    identity.conversation_id,
                    response_epoch,
                ):
                    plan["interrupted_reason"] = "user_interrupted_before_dispatch"
                    self._record_interrupted_reply_breakpoint(
                        identity.conversation_id,
                        reason="user_interrupted_before_dispatch",
                        input_epoch=response_epoch,
                        full_text=response_text,
                        message_parts=plan.get("message_parts"),
                    )
                else:
                    realtime_dispatch_task = self._schedule_background_task(
                        self._send_realtime_chat_plan(
                            event,
                            plan,
                            source="llm_response_intercept",
                            record_history_shadow=True,
                        ),
                        label="realtime_chat_response_dispatch",
                    )
                    del realtime_dispatch_task
        if self._group_atmosphere_modeling_enabled() and self._group_atmosphere_applies(
            identity,
        ):
            observed_at = self._observed_now()
            base_persona_profile = await self._persona_profile(event, None)
            persona_profile = await self._runtime_persona_profile(
                identity.conversation_id,
                base_persona_profile,
                now=observed_at,
            )
            group_state = await self._load_group_atmosphere_state(
                identity.conversation_id,
                personality_model=self._personality_model_from_profile(
                    persona_profile,
                ),
                now=observed_at,
            )
            cooled = self._apply_group_atmosphere_join_cooldown(
                identity.conversation_id,
                group_state,
                now=observed_at,
                bot_response=True,
            )
            await self._save_group_atmosphere_state(identity.conversation_id, cooled)

        assessment_timing = self._assessment_timing()
        if assessment_timing not in {"post", "both"}:
            return

        if self._background_post_assessment_enabled():
            self._schedule_background_post_assessment(
                event,
                response_text,
            )
            return

        await self._update_from_llm_response(event, response_text)

    async def _update_from_llm_response(
        self,
        event: AstrMessageEvent,
        response_text: str,
        request_context_text: str | None = None,
        observation: EmotionObservation | None = None,
        observed_at: float | None = None,
    ) -> None:
        moral_repair_enabled = self._moral_repair_modeling_enabled()
        personality_drift_enabled = self._personality_drift_enabled()
        fallibility_enabled = self._fallibility_modeling_enabled()
        safety_boundary = self._safety_boundary_enabled()
        action_blocking = self._shadow_action_blocking_enabled()
        identity = self._agent_identity(event)
        session_key = identity.conversation_id
        observed_at = observed_at if observed_at is not None else self._observed_now()
        base_persona_profile = await self._persona_profile(event, None)
        personality_drift_state: PersonalityDriftState | None = None
        if personality_drift_enabled:
            personality_drift_state = await self._load_personality_drift_state(
                session_key,
                base_persona_profile,
                now=observed_at,
            )
        persona_profile = await self._runtime_persona_profile(
            session_key,
            base_persona_profile,
            personality_drift_state,
            now=observed_at,
        )
        state = await self._load_state(session_key, persona_profile, now=observed_at)
        engine = self._engine_for_persona(persona_profile)
        before_state = EmotionState.from_dict(state.to_dict())
        moral_repair_load_task: asyncio.Task[MoralRepairState] | None = None
        if moral_repair_enabled:
            moral_repair_load_task = asyncio.create_task(
                self._load_moral_repair_state(
                    session_key,
                    personality_model=self._personality_model_from_profile(
                        persona_profile,
                    ),
                    now=observed_at,
                ),
            )
        fallibility_load_task: asyncio.Task[FallibilityState] | None = None
        if fallibility_enabled:
            fallibility_load_task = asyncio.create_task(
                self._load_fallibility_state(
                    session_key,
                    personality_model=self._personality_model_from_profile(
                        persona_profile,
                    ),
                    now=observed_at,
                ),
            )

        try:
            speaker_state = await self._load_speaker_state(
                identity,
                persona_profile,
                now=observed_at,
            )
            if observation is None:
                observation = await self._assess_emotion(
                    event=event,
                    phase="post_response",
                    previous_state=speaker_state or state,
                    persona_profile=persona_profile,
                    context_text=(
                        request_context_text
                        if request_context_text is not None
                        else self._last_request_text.get(session_key, "")
                    ),
                    current_text=self._agent_current_text(event, response_text),
                )
            state = engine.update(
                state,
                observation,
                profile=persona_profile,
                now=observed_at,
            )
            await self._save_state(session_key, state)
            await self._record_agent_trail(
                session_key,
                identity=identity,
                phase="post_response",
                module="emotion",
                event="state_updated",
                observed_at=observed_at,
                input_text=response_text,
                before=before_state,
                after=state,
                causes=[
                    {
                        "type": "observation",
                        "label": observation.label,
                        "confidence": observation.confidence,
                        "source": observation.source,
                    },
                ],
            )
            if speaker_state is not None:
                before_speaker_state = EmotionState.from_dict(speaker_state.to_dict())
                speaker_state = engine.update(
                    speaker_state,
                    observation,
                    profile=persona_profile,
                    now=observed_at,
                )
                await self._save_speaker_state(identity, speaker_state)
                await self._record_agent_trail(
                    identity.speaker_track_id or session_key,
                    identity=identity,
                    phase="post_response",
                    module="emotion.speaker",
                    event="state_updated",
                    observed_at=observed_at,
                    input_text=response_text,
                    before=before_speaker_state,
                    after=speaker_state,
                    causes=[
                        {
                            "type": "observation",
                            "label": observation.label,
                            "confidence": observation.confidence,
                            "source": observation.source,
                        },
                    ],
                )
        except Exception:
            if moral_repair_load_task is not None and not moral_repair_load_task.done():
                moral_repair_load_task.cancel()
            if fallibility_load_task is not None and not fallibility_load_task.done():
                fallibility_load_task.cancel()
            if moral_repair_load_task is not None:
                try:
                    await moral_repair_load_task
                except asyncio.CancelledError:
                    pass
            if fallibility_load_task is not None:
                try:
                    await fallibility_load_task
                except asyncio.CancelledError:
                    pass
            raise

        if moral_repair_enabled:
            previous_moral_repair_state = (
                await moral_repair_load_task
                if moral_repair_load_task is not None
                else await self._load_moral_repair_state(
                    session_key,
                    personality_model=self._personality_model_from_profile(
                        persona_profile,
                    ),
                    now=observed_at,
                )
            )
            moral_repair_observation = heuristic_moral_repair_observation(
                response_text,
                source="llm_response",
            )
            moral_repair_state = self.moral_repair_engine.update(
                previous_moral_repair_state,
                moral_repair_observation,
                personality_model=self._personality_model_from_profile(
                    persona_profile,
                ),
                now=observed_at,
            )
            await self._save_moral_repair_state(session_key, moral_repair_state)
        if fallibility_enabled:
            previous_fallibility_state = (
                await fallibility_load_task
                if fallibility_load_task is not None
                else await self._load_fallibility_state(
                    session_key,
                    personality_model=self._personality_model_from_profile(
                        persona_profile,
                    ),
                    now=observed_at,
                )
            )
            fallibility_observation = heuristic_fallibility_observation(
                response_text,
                source="llm_response",
            )
            fallibility_state = self.fallibility_engine.update(
                previous_fallibility_state,
                fallibility_observation,
                personality_model=self._personality_model_from_profile(
                    persona_profile,
                ),
                now=observed_at,
            )
            await self._save_fallibility_state(session_key, fallibility_state)
        if personality_drift_enabled:
            drift_persona_fingerprint = (
                base_persona_profile.fingerprint
                if base_persona_profile is not None
                else "default"
            )
            previous_personality_drift_state = personality_drift_state
            if previous_personality_drift_state is None:
                previous_personality_drift_state = await self._load_personality_drift_state(
                    session_key,
                    base_persona_profile,
                    now=observed_at,
                )
            observation = heuristic_personality_drift_observation(
                response_text,
                source="llm_response",
                emotion_snapshot=state.to_public_dict(
                    session_key=session_key,
                    include_safety=safety_boundary,
                ),
            )
            personality_drift_state = self.personality_drift_engine.update(
                previous_personality_drift_state,
                observation,
                persona_fingerprint=drift_persona_fingerprint,
                now=observed_at,
            )
            if self._personality_drift_changed(
                personality_drift_state,
                previous_personality_drift_state,
            ):
                await self._save_personality_drift_state(
                    session_key,
                    personality_drift_state,
                )
        await self._observe_sylanne_memory_event_if_enabled(
            session_key,
            response_text,
            speaker_id="assistant",
            emotion_state=state,
            personality_drift_state=personality_drift_state,
            observed_at=observed_at,
        )

    def _schedule_background_post_assessment(
        self,
        event: AstrMessageEvent,
        response_text: str,
    ) -> None:
        if not hasattr(self, "_background_post_tasks"):
            self._background_post_tasks = {}
        if not hasattr(self, "_background_post_queues"):
            self._background_post_queues = {}
        if not hasattr(self, "_background_post_active"):
            self._background_post_active = {}
        if not hasattr(self, "_background_post_sequence"):
            self._background_post_sequence = {}
        if not hasattr(self, "_background_post_latest_enqueued"):
            self._background_post_latest_enqueued = {}
        if not hasattr(self, "_background_post_last_committed"):
            self._background_post_last_committed = {}
        if not hasattr(self, "_background_post_skipped"):
            self._background_post_skipped = {}
        if not hasattr(self, "_background_post_dead_letters"):
            self._background_post_dead_letters = {}
        if not hasattr(self, "_background_post_recovered_sessions"):
            self._background_post_recovered_sessions = set()
        if not hasattr(self, "_background_post_checkpoint_tasks"):
            self._background_post_checkpoint_tasks = set()

        identity = self._agent_identity(event)
        session_key = identity.conversation_id
        if getattr(self, "_terminating", False):
            return
        request_context_text = self._last_request_text.get(session_key, "")
        sequence = self._background_post_sequence.get(session_key, 0) + 1
        self._background_post_sequence[session_key] = sequence
        self._background_post_latest_enqueued[session_key] = sequence
        queue = self._background_post_queues.setdefault(session_key, deque())
        self._recover_expired_background_post_active(session_key)
        queue.append(
            _BackgroundPostJob(
                event=event,
                identity=identity,
                response_text=response_text,
                request_context_text=request_context_text,
                sequence=sequence,
                observed_at=self._observed_now(),
                input_epoch=self._conversation_response_epoch(session_key, event),
            ),
        )
        queue_limit = max(0, self._cfg_int("background_post_queue_limit", 0))
        while queue_limit and len(queue) > queue_limit:
            skipped = queue.popleft()
            self._background_post_skipped.setdefault(session_key, set()).add(
                skipped.sequence,
            )
        self._schedule_background_post_checkpoint(session_key)
        running = self._background_post_tasks.get(session_key)
        if running is not None and not running.done():
            return

        task = self._schedule_background_task(
            self._drain_background_post_assessments(session_key),
            label=f"post_response_assessment:{session_key}",
        )
        self._background_post_tasks[session_key] = task

        def _clear_session_task(done: asyncio.Task[Any]) -> None:
            if self._background_post_tasks.get(session_key) is done:
                self._background_post_tasks.pop(session_key, None)

        task.add_done_callback(_clear_session_task)

    async def _drain_background_post_assessments(self, session_key: str) -> None:
        while not await self._recover_background_post_queue(session_key):
            await asyncio.sleep(0.25)
        while True:
            self._recover_expired_background_post_active(session_key)
            batch = self._take_background_post_batch(session_key)
            if not batch:
                queue = self._background_post_queues.get(session_key)
                if not queue:
                    self._background_post_queues.pop(session_key, None)
                    self._background_post_active.pop(session_key, None)
                    self._background_post_sequence.pop(session_key, None)
                    self._background_post_skipped.pop(session_key, None)
                    await self._save_background_post_checkpoint_serialized(session_key)
                    return
                await asyncio.sleep(self._background_post_next_sleep(session_key))
                continue

            raw_results = await asyncio.gather(
                *(self._assess_background_post_job(job) for job in batch),
                return_exceptions=True,
            )
            results: list[_BackgroundPostResult] = []
            for job, raw_result in zip(batch, raw_results):
                if isinstance(raw_result, asyncio.CancelledError):
                    raise raw_result
                if isinstance(raw_result, BaseException):
                    results.append(_BackgroundPostResult(job=job, error=raw_result))
                else:
                    results.append(raw_result)
            for result in sorted(results, key=lambda item: item.job.sequence):
                if result.skipped:
                    self._finish_background_post_job(session_key, result.job)
                    continue
                if result.error is not None:
                    self._log_warning(
                        f"{PLUGIN_NAME}: 后台 post 情绪评估失败，继续处理队列剩余项: {result.error}",
                    )
                    self._handle_background_post_failure(
                        session_key,
                        result.job,
                        result.error,
                        pending_results=results,
                    )
                    break
                try:
                    await self._commit_background_post_result(result)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._log_warning(
                        f"{PLUGIN_NAME}: 后台 post 情绪状态提交失败，准备重试或进入 dead-letter: {exc}",
                    )
                    self._handle_background_post_failure(
                        session_key,
                        result.job,
                        exc,
                        pending_results=results,
                    )
                    break
                self._finish_background_post_job(session_key, result.job)

    def _take_background_post_batch(
        self,
        session_key: str,
    ) -> list[_BackgroundPostJob]:
        queue = self._background_post_queues.get(session_key)
        if not queue:
            return []
        now = self._observed_now()
        max_workers = self._background_post_max_workers(session_key)
        batch: list[_BackgroundPostJob] = []
        while queue and len(batch) < max_workers:
            job = queue[0]
            if job.next_retry_at is not None and job.next_retry_at > now:
                break
            queue.popleft()
            batch.append(job)
        if batch:
            active = self._background_post_active.setdefault(session_key, {})
            lease_seconds = max(
                1.0,
                self._cfg_float("background_post_job_lease_seconds", 120.0),
            )
            for job in batch:
                job.attempts = max(0, int(job.attempts)) + 1
                job.leased_at = now
                job.lease_until = now + lease_seconds
                job.next_retry_at = None
                active[job.sequence] = job
            self._schedule_background_post_checkpoint(session_key)
        return batch

    def _finish_background_post_job(
        self,
        session_key: str,
        job: _BackgroundPostJob,
    ) -> None:
        active = getattr(self, "_background_post_active", {}).get(session_key, {})
        active.pop(job.sequence, None)
        self._schedule_background_post_checkpoint(session_key)

    def _handle_background_post_failure(
        self,
        session_key: str,
        failed_job: _BackgroundPostJob,
        error: BaseException,
        *,
        pending_results: list[_BackgroundPostResult],
    ) -> None:
        active = getattr(self, "_background_post_active", {}).get(session_key, {})
        requeue_front: list[_BackgroundPostJob] = []
        for result in sorted(pending_results, key=lambda item: item.job.sequence):
            job = result.job
            if job.sequence < failed_job.sequence:
                continue
            active.pop(job.sequence, None)
            if job.sequence == failed_job.sequence:
                if self._retry_or_dead_letter_background_post_job(
                    session_key,
                    job,
                    error,
                    requeue=False,
                ):
                    requeue_front.append(job)
                continue
            requeue_front.append(job)
        for job in sorted(requeue_front, key=lambda item: item.sequence, reverse=True):
            self._requeue_background_post_job(session_key, job, front=True)
        self._schedule_background_post_checkpoint(session_key)

    def _retry_or_dead_letter_background_post_job(
        self,
        session_key: str,
        job: _BackgroundPostJob,
        error: BaseException,
        *,
        requeue: bool = True,
    ) -> bool:
        now = self._observed_now()
        job.last_error_type = type(error).__name__
        job.last_error_message = self._clip(str(error) or job.last_error_type, 240)
        job.last_failed_at = now
        job.leased_at = None
        job.lease_until = None
        max_attempts = max(1, self._cfg_int("background_post_retry_max_attempts", 3))
        if int(job.attempts) >= max_attempts:
            job.dead_lettered_at = now
            self._add_background_post_dead_letter(session_key, job)
            return False
        delay = self._background_post_retry_delay(job)
        job.next_retry_at = now + delay
        if requeue:
            self._requeue_background_post_job(session_key, job, front=True)
        return True

    def _background_post_retry_delay(self, job: _BackgroundPostJob) -> float:
        base = max(
            0.0,
            self._cfg_float("background_post_retry_base_delay_seconds", 2.0),
        )
        ceiling = max(
            base,
            self._cfg_float("background_post_retry_max_delay_seconds", 60.0),
        )
        if base <= 0:
            return 0.0
        return min(ceiling, base * (2 ** max(0, int(job.attempts) - 1)))

    def _requeue_background_post_job(
        self,
        session_key: str,
        job: _BackgroundPostJob,
        *,
        front: bool = False,
    ) -> None:
        queue = self._background_post_queues.setdefault(session_key, deque())
        known = {item.sequence for item in queue}
        if job.sequence in known:
            return
        if front:
            queue.appendleft(job)
            return
        queue.append(job)

    def _add_background_post_dead_letter(
        self,
        session_key: str,
        job: _BackgroundPostJob,
    ) -> None:
        limit = max(1, self._cfg_int("background_post_dead_letter_limit", 100))
        dead = self._background_post_dead_letters.setdefault(
            session_key,
            deque(maxlen=limit),
        )
        if dead.maxlen != limit:
            dead = deque(dead, maxlen=limit)
            self._background_post_dead_letters[session_key] = dead
        dead.append(job)

    def _recover_expired_background_post_active(self, session_key: str) -> int:
        active = getattr(self, "_background_post_active", {}).get(session_key, {})
        if not active:
            return 0
        now = self._observed_now()
        expired: list[_BackgroundPostJob] = []
        for sequence, job in list(active.items()):
            if job.lease_until is not None and job.lease_until <= now:
                active.pop(sequence, None)
                job.leased_at = None
                job.lease_until = None
                expired.append(job)
        for job in sorted(expired, key=lambda item: item.sequence, reverse=True):
            self._requeue_background_post_job(session_key, job, front=True)
        if expired:
            self._schedule_background_post_checkpoint(session_key)
        return len(expired)

    def _background_post_next_sleep(self, session_key: str) -> float:
        queue = getattr(self, "_background_post_queues", {}).get(session_key)
        if not queue:
            return 0.0
        now = self._observed_now()
        retry_times = [
            job.next_retry_at
            for job in queue
            if job.next_retry_at is not None and job.next_retry_at > now
        ]
        if not retry_times:
            decision = self._background_post_adaptive_worker_decision(session_key)
            if decision["dispatch_workers"] <= 0:
                return min(
                    0.25,
                    max(
                        0.02,
                        float(
                            decision.get("scale_state", {}).get(
                                "next_scale_in_seconds",
                                0.05,
                            ),
                        ),
                    ),
                )
            return 0.0
        return min(0.25, max(0.0, min(retry_times) - now))

    def _background_post_assessment_enabled(self) -> bool:
        return True

    def _dynamic_background_workers_enabled(self) -> bool:
        return self._cfg_bool("enable_dynamic_background_workers", False)

    def _round_optional_ratio(self, value: Any) -> float | None:
        numeric = self._optional_float(value)
        if numeric is None:
            return None
        return round(max(0.0, min(1.0, numeric)), 6)

    def _background_post_worker_pressure(self, session_key: str) -> dict[str, Any]:
        queue = list(getattr(self, "_background_post_queues", {}).get(session_key) or ())
        active = getattr(self, "_background_post_active", {}).get(session_key, {}) or {}
        now = self._observed_now()
        ready = [
            job
            for job in queue
            if job.next_retry_at is None or job.next_retry_at <= now
        ]
        retrying = [
            job
            for job in queue
            if job.next_retry_at is not None and job.next_retry_at > now
        ]
        expired = [
            job
            for job in active.values()
            if job.lease_until is not None and job.lease_until <= now
        ]
        tracked = ready + list(active.values())
        oldest_ready_age = (
            max(0.0, now - min(job.observed_at for job in ready))
            if ready
            else 0.0
        )
        lag_seconds = (
            max(0.0, now - min(job.observed_at for job in tracked))
            if tracked
            else 0.0
        )
        return {
            "ready_count": len(ready),
            "queued_count": len(queue),
            "active_count": len(active),
            "retrying_count": len(retrying),
            "expired_lease_count": len(expired),
            "oldest_ready_age_seconds": oldest_ready_age,
            "lag_seconds": lag_seconds,
        }

    def _background_post_global_active_workers(self, *, session_key: str = "") -> int:
        active_map = getattr(self, "_background_post_active", {}) or {}
        total = 0
        for key, active in active_map.items():
            if session_key and key == session_key:
                continue
            total += len(active or {})
        return total

    def _memory_pressure_ratio(self) -> tuple[float | None, str]:
        try:
            if os.name == "nt":
                import ctypes

                class _MemoryStatusEx(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]

                status = _MemoryStatusEx()
                status.dwLength = ctypes.sizeof(_MemoryStatusEx)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                    return min(1.0, max(0.0, status.dwMemoryLoad / 100.0)), "windows"
                return None, "windows_unavailable"
            meminfo_path = "/proc/meminfo"
            if os.path.exists(meminfo_path):
                values: dict[str, float] = {}
                with open(meminfo_path, "r", encoding="utf-8") as handle:
                    for line in handle:
                        if ":" not in line:
                            continue
                        key, raw_value = line.split(":", 1)
                        parts = raw_value.strip().split()
                        if not parts:
                            continue
                        try:
                            values[key] = float(parts[0])
                        except ValueError:
                            continue
                total = values.get("MemTotal")
                available = values.get("MemAvailable")
                if total and available is not None:
                    ratio = 1.0 - (available / total)
                    return min(1.0, max(0.0, ratio)), "proc_meminfo"
            return None, "unsupported"
        except Exception:
            return None, "unavailable"

    def _cpu_pressure_ratio(self) -> tuple[float | None, str]:
        try:
            getloadavg = getattr(os, "getloadavg", None)
            cpu_count = os.cpu_count() or 1
            if callable(getloadavg):
                load_1m, _, _ = getloadavg()
                return min(1.0, max(0.0, float(load_1m) / max(1, cpu_count))), "loadavg"
            return None, "unsupported"
        except Exception:
            return None, "unavailable"

    def _background_post_resource_pressure(self) -> dict[str, Any]:
        now = self._observed_now()
        cache = getattr(self, "_background_post_resource_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._background_post_resource_cache = cache
        cached_at = float(cache.get("sampled_at") or 0.0)
        if now - cached_at < BACKGROUND_POST_RESOURCE_SAMPLE_TTL_SECONDS:
            cached = cache.get("value")
            if isinstance(cached, dict):
                return dict(cached)

        cpu_ratio, cpu_source = self._cpu_pressure_ratio()
        memory_ratio, memory_source = self._memory_pressure_ratio()
        known_ratios = [
            ratio
            for ratio in (cpu_ratio, memory_ratio)
            if isinstance(ratio, (int, float))
        ]
        unknown = not known_ratios
        combined = max(known_ratios) if known_ratios else 0.0
        if unknown:
            level = "unknown"
            cap = 2
            reason = "environment_pressure_unknown_conservative"
        elif combined >= 0.95:
            level = "critical"
            cap = 1
            reason = "environment_pressure_critical"
        elif combined >= 0.85:
            level = "high"
            cap = 2
            reason = "environment_pressure_high"
        elif combined >= 0.75:
            level = "elevated"
            cap = 3
            reason = "environment_pressure_elevated"
        else:
            level = "normal"
            cap = BACKGROUND_POST_TOTAL_WORKER_CAP
            reason = "environment_pressure_normal"
        pressure = {
            "cpu_load_ratio": cpu_ratio,
            "cpu_source": cpu_source,
            "memory_load_ratio": memory_ratio,
            "memory_source": memory_source,
            "combined_load_ratio": combined,
            "unknown": unknown,
            "level": level,
            "worker_cap": max(1, min(BACKGROUND_POST_TOTAL_WORKER_CAP, cap)),
            "reason": reason,
            "sampled_at": now,
        }
        cache["sampled_at"] = now
        cache["value"] = dict(pressure)
        return pressure

    def _background_post_scale_interval(self, pressure: dict[str, Any]) -> float:
        ready_count = max(0, int(pressure.get("ready_count") or 0))
        oldest_ready_age = max(
            0.0,
            float(pressure.get("oldest_ready_age_seconds") or 0.0),
        )
        urgency = min(1.0, max(ready_count / 32.0, oldest_ready_age / 90.0))
        interval = (
            BACKGROUND_POST_WORKER_SCALE_MAX_INTERVAL_SECONDS
            - (
                BACKGROUND_POST_WORKER_SCALE_MAX_INTERVAL_SECONDS
                - BACKGROUND_POST_WORKER_SCALE_MIN_INTERVAL_SECONDS
            )
            * urgency
        )
        return max(
            BACKGROUND_POST_WORKER_SCALE_MIN_INTERVAL_SECONDS,
            min(BACKGROUND_POST_WORKER_SCALE_MAX_INTERVAL_SECONDS, interval),
        )

    def _background_post_apply_scale_smoothing(
        self,
        session_key: str,
        desired: int,
        pressure: dict[str, Any],
        reasons: list[str],
        *,
        commit: bool = False,
    ) -> tuple[int, dict[str, Any]]:
        now = self._observed_now()
        states = getattr(self, "_background_post_worker_state", None)
        if not isinstance(states, dict):
            states = {}
            self._background_post_worker_state = states
        stored_state = states.get(session_key)
        state = dict(stored_state) if isinstance(stored_state, dict) else {
            "current_workers": BACKGROUND_POST_BASE_WORKERS,
            "last_scaled_at": 0.0,
        }
        current = max(
            BACKGROUND_POST_BASE_WORKERS,
            min(
                BACKGROUND_POST_TOTAL_WORKER_CAP,
                int(state.get("current_workers") or BACKGROUND_POST_BASE_WORKERS),
            ),
        )
        target = max(
            BACKGROUND_POST_BASE_WORKERS,
            min(BACKGROUND_POST_TOTAL_WORKER_CAP, int(desired)),
        )
        interval = self._background_post_scale_interval(pressure)
        last_scaled_at = float(state.get("last_scaled_at") or 0.0)
        next_scale_in = 0.0
        if target > current:
            elapsed = now - last_scaled_at
            if elapsed >= interval:
                current = min(target, current + 1)
                state["last_scaled_at"] = now
                reasons.append("worker_scale_step_up")
            else:
                next_scale_in = max(0.0, interval - elapsed)
                reasons.append("worker_scale_cooldown")
        elif target < current:
            current = target
            state["last_scaled_at"] = now
            reasons.append("worker_scale_step_down")
        state.update(
            {
                "current_workers": current,
                "target_workers": target,
                "scale_interval_seconds": interval,
                "updated_at": now,
            },
        )
        if commit:
            states[session_key] = dict(state)
        return current, {
            "current_workers": current,
            "target_workers": target,
            "scale_interval_seconds": interval,
            "last_scaled_at": state["last_scaled_at"],
            "next_scale_in_seconds": next_scale_in,
            "committed": commit,
        }

    def _background_post_adaptive_worker_decision(
        self,
        session_key: str,
        *,
        commit_scale: bool = False,
    ) -> dict[str, Any]:
        pressure = self._background_post_worker_pressure(session_key)
        target = BACKGROUND_POST_BASE_WORKERS
        reasons: list[str] = ["base_single_worker"]
        if self._dynamic_background_workers_enabled():
            ready_count = pressure["ready_count"]
            oldest_ready_age = pressure["oldest_ready_age_seconds"]
            if ready_count >= 2 or oldest_ready_age >= 2.0:
                target = 2
                reasons.append("moderate_queue_or_wait")
            if ready_count >= 5 or oldest_ready_age >= 8.0:
                target = 3
                reasons.append("sustained_backlog")
            if ready_count >= 10 or oldest_ready_age >= 20.0:
                target = 4
                reasons.append("heavy_backlog")
            if ready_count >= 18 or oldest_ready_age >= 45.0:
                target = 5
                reasons.append("severe_backlog")
            if ready_count >= 32 or oldest_ready_age >= 90.0:
                target = 6
                reasons.append("extreme_backlog")
            if pressure["expired_lease_count"] and ready_count >= 2:
                target = min(
                    BACKGROUND_POST_TOTAL_WORKER_CAP,
                    target + 1,
                )
                reasons.append("expired_lease_recovery")
            if pressure["retrying_count"] and ready_count >= 4:
                target = min(
                    BACKGROUND_POST_TOTAL_WORKER_CAP,
                    target + 1,
                )
                reasons.append("retry_pressure")
        else:
            reasons.append("dynamic_scale_disabled")

        target = max(
            BACKGROUND_POST_BASE_WORKERS,
            min(
                BACKGROUND_POST_TOTAL_WORKER_CAP,
                target,
            ),
        )
        queue_target = target
        resource_pressure = self._background_post_resource_pressure()
        resource_cap = max(
            1,
            min(
                BACKGROUND_POST_TOTAL_WORKER_CAP,
                int(resource_pressure.get("worker_cap") or BACKGROUND_POST_BASE_WORKERS),
            ),
        )
        if target > resource_cap:
            reasons.append(str(resource_pressure.get("reason") or "environment_pressure"))
        elif self._dynamic_background_workers_enabled():
            reasons.append(str(resource_pressure.get("reason") or "environment_pressure"))
        effective_global_cap = max(
            1,
            min(BACKGROUND_POST_TOTAL_WORKER_CAP, resource_cap),
        )
        target = min(target, effective_global_cap)
        smoothed, scale_state = self._background_post_apply_scale_smoothing(
            session_key,
            target,
            pressure,
            reasons,
            commit=commit_scale,
        )
        active_current = max(0, int(pressure.get("active_count") or 0))
        active_other = self._background_post_global_active_workers(
            session_key=session_key,
        )
        active_total = active_current + active_other
        global_available_slots = max(0, effective_global_cap - active_total)
        session_available_slots = max(0, smoothed - active_current)
        dispatch_workers = min(session_available_slots, global_available_slots)
        if active_other:
            reasons.append("global_worker_budget_shared")
        if global_available_slots <= 0:
            reasons.append("global_worker_budget_exhausted")
        elif dispatch_workers < session_available_slots:
            reasons.append("global_worker_budget_limited")
        return {
            "desired_workers": smoothed,
            "queue_target_workers": queue_target,
            "target_workers": target,
            "smoothed_workers": smoothed,
            "dispatch_workers": dispatch_workers,
            "dynamic_extra_workers": max(0, smoothed - BACKGROUND_POST_BASE_WORKERS),
            "reasons": reasons,
            "pressure": pressure,
            "resource_pressure": resource_pressure,
            "global_active_other_workers": active_other,
            "global_active_workers": active_total,
            "global_worker_cap": effective_global_cap,
            "global_available_worker_slots": global_available_slots,
            "scale_state": scale_state,
            "idle_workers_close_automatically": True,
        }

    def _background_post_dynamic_extra_workers(self, session_key: str) -> int:
        if not self._dynamic_background_workers_enabled():
            return 0
        return int(
            self._background_post_adaptive_worker_decision(session_key)[
                "dynamic_extra_workers"
            ],
        )

    def _background_post_max_workers(self, session_key: str) -> int:
        return int(
            self._background_post_adaptive_worker_decision(
                session_key,
                commit_scale=True,
            )[
                "dispatch_workers"
            ],
        )

    def _internal_assessor_llm_pressure(self) -> dict[str, Any]:
        queues = getattr(self, "_background_post_queues", {}) or {}
        active_map = getattr(self, "_background_post_active", {}) or {}
        now = self._observed_now()
        ready: list[_BackgroundPostJob] = []
        queued: list[_BackgroundPostJob] = []
        expired: list[_BackgroundPostJob] = []
        for queue in queues.values():
            for job in queue or ():
                queued.append(job)
                if job.next_retry_at is None or job.next_retry_at <= now:
                    ready.append(job)
        for active in active_map.values():
            for job in (active or {}).values():
                if job.lease_until is not None and job.lease_until <= now:
                    expired.append(job)
        oldest_ready_age = (
            max(0.0, now - min(job.observed_at for job in ready))
            if ready
            else 0.0
        )
        return {
            "ready_count": len(ready),
            "queued_count": len(queued),
            "expired_lease_count": len(expired),
            "oldest_ready_age_seconds": oldest_ready_age,
        }

    def _internal_assessor_llm_concurrency_decision(self) -> dict[str, Any]:
        pressure = self._internal_assessor_llm_pressure()
        limit = INTERNAL_ASSESSOR_LLM_BASE_CONCURRENCY
        reasons: list[str] = ["base_two_lane_guard"]
        if self._dynamic_background_workers_enabled() and (
            pressure["ready_count"] >= INTERNAL_ASSESSOR_LLM_BURST_READY_THRESHOLD
            or pressure["oldest_ready_age_seconds"]
            >= INTERNAL_ASSESSOR_LLM_BURST_WAIT_SECONDS
            or pressure["expired_lease_count"] >= 2
        ):
            limit = INTERNAL_ASSESSOR_LLM_BURST_CONCURRENCY
            reasons.append("temporary_extreme_backlog_burst")
        limit = max(
            1,
            min(INTERNAL_ASSESSOR_LLM_BURST_CONCURRENCY, int(limit)),
        )
        return {
            "limit": limit,
            "base_limit": INTERNAL_ASSESSOR_LLM_BASE_CONCURRENCY,
            "burst_limit": INTERNAL_ASSESSOR_LLM_BURST_CONCURRENCY,
            "reasons": reasons,
            "pressure": pressure,
        }

    def _internal_assessor_llm_condition_for_loop(self) -> asyncio.Condition:
        loop = asyncio.get_running_loop()
        if (
            getattr(self, "_internal_assessor_llm_condition", None) is None
            or getattr(self, "_internal_assessor_llm_condition_loop", None) is not loop
        ):
            self._internal_assessor_llm_condition = asyncio.Condition()
            self._internal_assessor_llm_condition_loop = loop
            self._internal_assessor_llm_inflight = 0
        return self._internal_assessor_llm_condition

    async def _acquire_internal_assessor_llm_slot(self) -> dict[str, Any]:
        condition = self._internal_assessor_llm_condition_for_loop()
        async with condition:
            while True:
                decision = self._internal_assessor_llm_concurrency_decision()
                if self._internal_assessor_llm_inflight < decision["limit"]:
                    self._internal_assessor_llm_inflight += 1
                    return decision
                await condition.wait()

    async def _release_internal_assessor_llm_slot(self) -> None:
        condition = self._internal_assessor_llm_condition_for_loop()
        async with condition:
            self._internal_assessor_llm_inflight = max(
                0,
                self._internal_assessor_llm_inflight - 1,
            )
            condition.notify_all()

    async def _call_internal_assessor_llm(
        self,
        *,
        provider_id: str,
        prompt: str,
        system_prompt: str,
    ) -> Any:
        await self._acquire_internal_assessor_llm_slot()
        try:
            call = self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=self._cfg_float("assessor_temperature", 0.1),
            )
            timeout_seconds = max(
                0.0,
                self._cfg_float("assessor_timeout_seconds", 0.0),
            )
            if timeout_seconds <= 0:
                return await call
            return await asyncio.wait_for(call, timeout=timeout_seconds)
        finally:
            await self._release_internal_assessor_llm_slot()


    async def _assess_background_post_job(
        self,
        job: _BackgroundPostJob,
    ) -> _BackgroundPostResult:
        timeout_seconds = max(
            0.0,
            self._cfg_float("background_post_job_timeout_seconds", 0.0),
        )
        if timeout_seconds > 0:
            return await asyncio.wait_for(
                self._assess_background_post_job_once(job),
                timeout=timeout_seconds,
            )
        return await self._assess_background_post_job_once(job)

    async def _assess_background_post_job_once(
        self,
        job: _BackgroundPostJob,
    ) -> _BackgroundPostResult:
        session_key = job.identity.conversation_id
        if job.sequence in self._background_post_skipped.get(session_key, set()):
            return _BackgroundPostResult(job=job, skipped=True)
        if self._conversation_reply_is_stale(session_key, job.input_epoch):
            return _BackgroundPostResult(job=job, skipped=True)
        try:
            base_persona_profile = await self._persona_profile(job.event, None)
            personality_drift_state: PersonalityDriftState | None = None
            if self._personality_drift_enabled():
                personality_drift_state = await self._load_personality_drift_state(
                    session_key,
                    base_persona_profile,
                    now=job.observed_at,
                )
            persona_profile = await self._runtime_persona_profile(
                session_key,
                base_persona_profile,
                personality_drift_state,
                now=job.observed_at,
            )
            state = await self._load_state(
                session_key,
                persona_profile,
                now=job.observed_at,
            )
            speaker_state = await self._load_speaker_state(
                job.identity,
                persona_profile,
                now=job.observed_at,
            )
            observation = await self._assess_emotion(
                event=job.event,
                phase="post_response",
                previous_state=speaker_state or state,
                persona_profile=persona_profile,
                context_text=job.request_context_text,
                current_text=self._agent_current_text(job.event, job.response_text),
            )
            return _BackgroundPostResult(job=job, observation=observation)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return _BackgroundPostResult(job=job, error=exc)

    async def _commit_background_post_result(
        self,
        result: _BackgroundPostResult,
    ) -> None:
        if result.observation is None:
            return
        await self._update_from_llm_response(
            result.job.event,
            result.job.response_text,
            request_context_text=result.job.request_context_text,
            observation=result.observation,
            observed_at=result.job.observed_at,
        )
        session_key = result.job.identity.conversation_id
        self._background_post_last_committed[session_key] = max(
            self._background_post_last_committed.get(session_key, 0),
            result.job.sequence,
        )

    def _schedule_background_post_checkpoint(self, session_key: str) -> None:
        if getattr(self, "_terminating", False):
            return
        if not self._cfg_bool("background_post_queue_checkpoint_enabled", True):
            return
        recovered = getattr(self, "_background_post_recovered_sessions", set())
        if session_key not in recovered:
            return
        try:
            task = asyncio.create_task(
                self._save_background_post_checkpoint_serialized(session_key),
            )
        except RuntimeError:
            return
        if not hasattr(self, "_background_post_checkpoint_tasks"):
            self._background_post_checkpoint_tasks = set()
        self._background_post_checkpoint_tasks.add(task)
        task.add_done_callback(
            lambda done: self._background_post_checkpoint_tasks.discard(done),
        )

    async def _save_all_background_post_checkpoints(self) -> None:
        if not self._cfg_bool("background_post_queue_checkpoint_enabled", True):
            return
        sessions = set(getattr(self, "_background_post_queues", {}).keys())
        sessions.update(getattr(self, "_background_post_active", {}).keys())
        sessions.update(getattr(self, "_background_post_dead_letters", {}).keys())
        sessions.update(getattr(self, "_background_post_latest_enqueued", {}).keys())
        for session_key in sorted(sessions):
            await self._recover_background_post_queue(session_key)
            await self._save_background_post_checkpoint_serialized(session_key)

    async def _save_background_post_checkpoint_serialized(
        self,
        session_key: str,
    ) -> None:
        locks = getattr(self, "_background_post_checkpoint_locks", None)
        if locks is None:
            locks = {}
            self._background_post_checkpoint_locks = locks
        lock = locks.get(session_key)
        if lock is None:
            lock = asyncio.Lock()
            locks[session_key] = lock
        async with lock:
            await self._save_background_post_checkpoint(session_key)

    async def _save_background_post_checkpoint(self, session_key: str) -> None:
        generations = getattr(self, "_background_post_checkpoint_generation", None)
        if generations is None:
            generations = {}
            self._background_post_checkpoint_generation = generations
        generation = generations.get(session_key, 0) + 1
        generations[session_key] = generation
        queue = list(getattr(self, "_background_post_queues", {}).get(session_key) or ())
        active = list(
            getattr(self, "_background_post_active", {})
            .get(session_key, {})
            .values(),
        )
        dead_letters = list(
            getattr(self, "_background_post_dead_letters", {}).get(session_key) or (),
        )
        jobs = sorted(
            queue + active,
            key=lambda job: job.sequence,
        )
        key = self._background_post_checkpoint_kv_key(session_key)
        if not jobs and not dead_letters:
            if generations.get(session_key) != generation:
                return
            try:
                await self.delete_kv_data(key)
            except Exception as exc:
                logger.debug(f"{PLUGIN_NAME}: background checkpoint delete failed: {exc}")
            return
        payload = {
            "schema_version": "astrbot.background_post_queue.v2",
            "session_key": session_key,
            "latest_enqueued": self._background_post_latest_enqueued.get(
                session_key,
                self._background_post_sequence.get(session_key, 0),
            ),
            "last_committed": self._background_post_last_committed.get(session_key, 0),
            "saved_at": self._observed_now(),
            "jobs": [self._background_post_job_to_dict(job) for job in jobs],
            "dead_letters": [
                self._background_post_job_to_dict(job, include_text=False)
                for job in sorted(dead_letters, key=lambda item: item.sequence)
            ],
        }
        if generations.get(session_key) != generation:
            return
        try:
            await self.put_kv_data(key, payload)
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: background checkpoint save failed: {exc}")

    async def _recover_background_post_queue(self, session_key: str) -> bool:
        if not self._cfg_bool("background_post_queue_checkpoint_enabled", True):
            return True
        recovered = getattr(self, "_background_post_recovered_sessions", None)
        if recovered is None:
            recovered = set()
            self._background_post_recovered_sessions = recovered
        if session_key in recovered:
            return True
        getter = getattr(self, "get_kv_data", None)
        if not callable(getter):
            recovered.add(session_key)
            return True
        try:
            data = await getter(
                self._background_post_checkpoint_kv_key(session_key),
                None,
            )
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: background checkpoint load failed: {exc}")
            return False
        if not isinstance(data, dict):
            recovered.add(session_key)
            return True
        jobs = [
            job
            for item in data.get("jobs") or []
            if (job := self._background_post_job_from_dict(session_key, item)) is not None
        ]
        dead_letters = [
            job
            for item in data.get("dead_letters") or []
            if (job := self._background_post_job_from_dict(session_key, item)) is not None
        ]
        jobs.sort(key=lambda job: job.sequence)
        queue = self._background_post_queues.setdefault(session_key, deque())
        local_jobs = list(queue)
        queue.clear()
        known_sequences: set[int] = set()
        for job in jobs:
            job.leased_at = None
            job.lease_until = None
            if job.sequence not in known_sequences:
                queue.append(job)
                known_sequences.add(job.sequence)
        latest_recovered_sequence = max(
            [job.sequence for job in jobs]
            + [int(data.get("latest_enqueued") or 0)],
        )
        next_sequence = latest_recovered_sequence
        for job in sorted(local_jobs, key=lambda item: item.sequence):
            if job.sequence <= latest_recovered_sequence or job.sequence in known_sequences:
                next_sequence += 1
                job.sequence = next_sequence
            else:
                next_sequence = max(next_sequence, job.sequence)
            if job.sequence not in known_sequences:
                queue.append(job)
                known_sequences.add(job.sequence)
        if dead_letters:
            dead = self._background_post_dead_letters.setdefault(session_key, deque())
            known_dead = {job.sequence for job in dead}
            for job in dead_letters:
                if job.sequence not in known_dead:
                    dead.append(job)
        latest = max(
            [job.sequence for job in list(queue) + dead_letters]
            + [int(data.get("latest_enqueued") or 0)],
        )
        self._background_post_sequence[session_key] = max(
            self._background_post_sequence.get(session_key, 0),
            latest,
        )
        self._background_post_latest_enqueued[session_key] = max(
            self._background_post_latest_enqueued.get(session_key, 0),
            latest,
        )
        self._background_post_last_committed[session_key] = max(
            self._background_post_last_committed.get(session_key, 0),
            int(data.get("last_committed") or 0),
        )
        recovered.add(session_key)
        return True

    def _background_post_job_to_dict(
        self,
        job: _BackgroundPostJob,
        *,
        include_text: bool = True,
    ) -> dict[str, Any]:
        identity = job.identity
        payload = {
            "sequence": job.sequence,
            "observed_at": job.observed_at,
            "input_epoch": job.input_epoch,
            "session_key": identity.conversation_id,
            "speaker_id": identity.speaker_id,
            "speaker_name": identity.speaker_name,
            "group_id": identity.group_id,
            "platform_id": identity.platform_id,
            "attempts": max(0, int(job.attempts)),
            "leased_at": job.leased_at,
            "lease_until": job.lease_until,
            "next_retry_at": job.next_retry_at,
            "last_error_type": job.last_error_type,
            "last_error_message": self._clip(job.last_error_message, 240),
            "last_failed_at": job.last_failed_at,
            "dead_lettered_at": job.dead_lettered_at,
        }
        if include_text:
            payload["response_text"] = self._clip(job.response_text, 4000)
            payload["request_context_text"] = self._clip(
                job.request_context_text,
                4000,
            )
        return payload

    def _background_post_job_from_dict(
        self,
        session_key: str,
        item: Any,
    ) -> _BackgroundPostJob | None:
        if not isinstance(item, dict):
            return None
        try:
            sequence = int(item.get("sequence") or 0)
        except (TypeError, ValueError):
            sequence = 0
        if sequence <= 0:
            return None
        event = _RecoveredBackgroundEvent(
            session_key=session_key,
            message=str(item.get("response_text") or ""),
            speaker_id=self._clean_optional_text(item.get("speaker_id")),
            speaker_name=self._clean_optional_text(item.get("speaker_name")),
            group_id=self._clean_optional_text(item.get("group_id")),
            platform_id=self._clean_optional_text(item.get("platform_id")),
        )
        identity = self._agent_identity(event)
        return _BackgroundPostJob(
            event=event,
            identity=identity,
            response_text=str(item.get("response_text") or ""),
            request_context_text=str(item.get("request_context_text") or ""),
            sequence=sequence,
            observed_at=self._as_float_value(item.get("observed_at"), self._observed_now()),
            input_epoch=self._optional_int(item.get("input_epoch")),
            attempts=max(0, int(self._as_float_value(item.get("attempts"), 0))),
            leased_at=self._optional_float(item.get("leased_at")),
            lease_until=self._optional_float(item.get("lease_until")),
            next_retry_at=self._optional_float(item.get("next_retry_at")),
            last_error_type=str(item.get("last_error_type") or "")[:80],
            last_error_message=str(item.get("last_error_message") or "")[:240],
            last_failed_at=self._optional_float(item.get("last_failed_at")),
            dead_lettered_at=self._optional_float(item.get("dead_lettered_at")),
        )

    def _schedule_background_task(
        self,
        coro: Any,
        *,
        label: str,
    ) -> asyncio.Task[Any]:
        if not hasattr(self, "_background_tasks"):
            self._background_tasks = set()
        if getattr(self, "_terminating", False):
            coro.close()
            raise RuntimeError(f"{PLUGIN_NAME}: 插件正在终止，拒绝调度后台任务 {label}")
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)

        def _consume_background_result(done: asyncio.Task[Any]) -> None:
            self._background_tasks.discard(done)
            try:
                done.result()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                self._log_warning(
                    f"{PLUGIN_NAME}: 后台任务 {label} 失败，已跳过本轮延后状态更新: {exc}",
                )

        task.add_done_callback(_consume_background_result)
        return task

    async def get_emotion_snapshot(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        include_prompt_fragment: bool = False,
        prompt_fragment_detail: str | None = None,
    ) -> dict[str, Any]:
        """Public API: return a stable, serializable emotion snapshot."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        event = event_or_session if self._looks_like_event(event_or_session) else None
        base_persona_profile = await self._public_persona_profile(
            event,
            request,
            allow_default=event is not None,
        )
        persona_profile = await self._runtime_persona_profile(
            session_key,
            base_persona_profile,
        )
        state = await self._load_state(session_key, persona_profile)
        safety_boundary = self._safety_boundary_enabled()
        prompt_fragment = None
        if include_prompt_fragment:
            prompt_fragment = self._build_state_injection_for_detail(
                state,
                prompt_fragment_detail,
                safety_boundary=safety_boundary,
            )
        return state.to_public_dict(
            session_key=session_key,
            prompt_fragment=prompt_fragment,
            include_safety=safety_boundary,
        )

    async def get_emotion_state(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        as_dict: bool = True,
    ) -> dict[str, Any] | EmotionState:
        """Public API: return the current state as a copy, not the live object."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        event = event_or_session if self._looks_like_event(event_or_session) else None
        base_persona_profile = await self._public_persona_profile(
            event,
            request,
            allow_default=event is not None,
        )
        persona_profile = await self._runtime_persona_profile(
            session_key,
            base_persona_profile,
        )
        state = await self._load_state(session_key, persona_profile)
        return state.to_dict() if as_dict else EmotionState.from_dict(state.to_dict())

    async def get_emotion_values(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> dict[str, float]:
        """Public API: return only the 7D bounded emotion vector."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        event = event_or_session if self._looks_like_event(event_or_session) else None
        base_persona_profile = await self._public_persona_profile(
            event,
            request,
            allow_default=event is not None,
        )
        persona_profile = await self._runtime_persona_profile(
            session_key,
            base_persona_profile,
        )
        state = await self._load_state(session_key, persona_profile)
        return {key: round(state.values.get(key, 0.0), 6) for key in state.values}

    async def get_emotion_consequences(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        """Public API: return action tendencies and active persistent effects."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        event = event_or_session if self._looks_like_event(event_or_session) else None
        base_persona_profile = await self._public_persona_profile(
            event,
            request,
            allow_default=event is not None,
        )
        persona_profile = await self._runtime_persona_profile(
            session_key,
            base_persona_profile,
        )
        state = await self._load_state(session_key, persona_profile)
        return state.consequences.to_public_dict()

    async def get_emotion_relationship(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        """Public API: return relationship decision, conflict cause and repair status."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        event = event_or_session if self._looks_like_event(event_or_session) else None
        base_persona_profile = await self._public_persona_profile(
            event,
            request,
            allow_default=event is not None,
        )
        persona_profile = await self._runtime_persona_profile(
            session_key,
            base_persona_profile,
        )
        state = await self._load_state(session_key, persona_profile)
        return relationship_state_to_public_payload(state.last_appraisal)

    async def get_emotion_prompt_fragment(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        detail: str | None = None,
    ) -> str:
        """Public API: return a prompt fragment that another plugin may inject."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        event = event_or_session if self._looks_like_event(event_or_session) else None
        base_persona_profile = await self._public_persona_profile(
            event,
            request,
            allow_default=event is not None,
        )
        persona_profile = await self._runtime_persona_profile(
            session_key,
            base_persona_profile,
        )
        state = await self._load_state(session_key, persona_profile)
        if str(detail or "").strip().lower() == "full":
            return build_state_injection(
                state,
                safety_boundary=self._safety_boundary_enabled(),
            )
        return self._build_state_injection(state)

    async def build_emotion_memory_payload(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        memory: Any = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        memory_text: str = "",
        source: str = "sylanne_memory",
        include_prompt_fragment: bool = False,
        include_raw_snapshot: bool = True,
        written_at: float | None = None,
        include_state_annotations_envelope: bool = True,
    ) -> dict[str, Any]:
        """Public API: wrap a memory entry with the emotion snapshot at write time."""
        resolved_session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        humanlike_snapshot: dict[str, Any] | None = None
        lifelike_learning_snapshot: dict[str, Any] | None = None
        moral_repair_snapshot: dict[str, Any] | None = None
        personality_drift_snapshot: dict[str, Any] | None = None
        fallibility_snapshot: dict[str, Any] | None = None
        include_humanlike_memory = self._cfg_bool("humanlike_memory_write_enabled", True)
        include_lifelike_memory = self._cfg_bool(
            "lifelike_learning_memory_write_enabled",
            True,
        )
        include_personality_drift_memory = self._cfg_bool(
            "personality_drift_memory_write_enabled",
            True,
        )
        include_moral_repair_memory = self._cfg_bool(
            "moral_repair_memory_write_enabled",
            True,
        )
        include_fallibility_memory = self._cfg_bool(
            "fallibility_memory_write_enabled",
            True,
        )
        include_integrated_self_memory = self._cfg_bool(
            "integrated_self_memory_write_enabled",
            True,
        )
        emotion_snapshot_task = asyncio.create_task(
            self.get_emotion_snapshot(
                event_or_session,
                request=request,
                session_key=resolved_session_key,
                include_prompt_fragment=include_prompt_fragment,
            ),
        )
        snapshot_tasks: dict[str, asyncio.Task[dict[str, Any]]] = {}
        if include_humanlike_memory:
            snapshot_tasks["humanlike"] = asyncio.create_task(
                self.get_humanlike_snapshot(
                    event_or_session,
                    request=request,
                    session_key=resolved_session_key,
                    exposure="plugin_safe",
                    include_prompt_fragment=include_prompt_fragment,
                ),
            )
        if include_lifelike_memory:
            snapshot_tasks["lifelike"] = asyncio.create_task(
                self.get_lifelike_learning_snapshot(
                    event_or_session,
                    request=request,
                    session_key=resolved_session_key,
                    exposure="plugin_safe",
                    include_prompt_fragment=include_prompt_fragment,
                ),
            )
        if include_personality_drift_memory:
            snapshot_tasks["personality_drift"] = asyncio.create_task(
                self.get_personality_drift_snapshot(
                    event_or_session,
                    request=request,
                    session_key=resolved_session_key,
                    exposure="plugin_safe",
                    include_prompt_fragment=include_prompt_fragment,
                ),
            )
        if include_moral_repair_memory:
            snapshot_tasks["moral_repair"] = asyncio.create_task(
                self.get_moral_repair_snapshot(
                    event_or_session,
                    request=request,
                    session_key=resolved_session_key,
                    exposure="plugin_safe",
                    include_prompt_fragment=include_prompt_fragment,
                ),
            )
        if include_fallibility_memory:
            snapshot_tasks["fallibility"] = asyncio.create_task(
                self.get_fallibility_snapshot(
                    event_or_session,
                    request=request,
                    session_key=resolved_session_key,
                    exposure="plugin_safe",
                    include_prompt_fragment=include_prompt_fragment,
                ),
            )
        await asyncio.gather(emotion_snapshot_task, *snapshot_tasks.values())
        snapshot = emotion_snapshot_task.result()
        payload = build_memory_payload(
            memory=memory,
            memory_text=memory_text,
            source=source,
            snapshot=snapshot,
            include_prompt_fragment=include_prompt_fragment,
            include_raw_snapshot=include_raw_snapshot,
            written_at=written_at,
        )
        if include_humanlike_memory:
            humanlike_snapshot = snapshot_tasks["humanlike"].result()
            annotation = build_humanlike_memory_annotation(
                humanlike_snapshot,
                source=source,
                written_at=written_at,
            )
            payload["humanlike_state_at_write"] = annotation
            if include_raw_snapshot:
                payload["humanlike_snapshot"] = humanlike_snapshot
        if include_lifelike_memory:
            lifelike_learning_snapshot = snapshot_tasks["lifelike"].result()
            annotation = build_lifelike_memory_annotation(
                lifelike_learning_snapshot,
                source=source,
                written_at=written_at,
            )
            payload["lifelike_learning_state_at_write"] = annotation
            if include_raw_snapshot:
                payload["lifelike_learning_snapshot"] = lifelike_learning_snapshot
        if include_personality_drift_memory:
            personality_drift_snapshot = snapshot_tasks["personality_drift"].result()
            annotation = build_personality_drift_memory_annotation(
                personality_drift_snapshot,
                source=source,
                written_at=written_at,
            )
            payload["personality_drift_state_at_write"] = annotation
            if include_raw_snapshot:
                payload["personality_drift_snapshot"] = personality_drift_snapshot
        if include_moral_repair_memory:
            moral_repair_snapshot = snapshot_tasks["moral_repair"].result()
            annotation = build_moral_repair_memory_annotation(
                moral_repair_snapshot,
                source=source,
                written_at=written_at,
            )
            payload["moral_repair_state_at_write"] = annotation
            if include_raw_snapshot:
                payload["moral_repair_snapshot"] = moral_repair_snapshot
        if include_fallibility_memory:
            fallibility_snapshot = snapshot_tasks["fallibility"].result()
            annotation = build_fallibility_memory_annotation(
                fallibility_snapshot,
                source=source,
                written_at=written_at,
            )
            payload["fallibility_state_at_write"] = annotation
            if include_raw_snapshot:
                payload["fallibility_snapshot"] = fallibility_snapshot
        if include_integrated_self_memory:
            integrated_snapshot = await self.get_integrated_self_snapshot(
                event_or_session,
                request=request,
                session_key=resolved_session_key,
                include_raw_snapshots=include_raw_snapshot,
                emotion_snapshot=snapshot,
                humanlike_snapshot=humanlike_snapshot,
                lifelike_learning_snapshot=lifelike_learning_snapshot,
                personality_drift_snapshot=personality_drift_snapshot,
                moral_repair_snapshot=moral_repair_snapshot,
                fallibility_snapshot=fallibility_snapshot,
                include_humanlike=humanlike_snapshot is not None,
                include_lifelike_learning=lifelike_learning_snapshot is not None,
                include_personality_drift=personality_drift_snapshot is not None,
                include_moral_repair=moral_repair_snapshot is not None,
                include_fallibility=fallibility_snapshot is not None,
                include_psychological=False,
            )
            payload["integrated_self_state_at_write"] = (
                build_integrated_self_memory_annotation(
                    integrated_snapshot,
                    source=source,
                    written_at=written_at,
                )
            )
            if include_raw_snapshot:
                payload["integrated_self_snapshot"] = integrated_snapshot
        if include_state_annotations_envelope:
            payload["state_annotations_at_write"] = (
                build_state_annotations_memory_envelope(
                    payload,
                    source=source,
                    written_at=written_at,
                )
            )
        return payload

    async def query_sylanne_memory(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        query: str = "",
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        limit: int = 5,
        include_dynamics: bool = False,
        now: float | None = None,
    ) -> dict[str, Any]:
        """Public API: read-only query for Sylanne's own long-term memory."""
        resolved_session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        clean_query = self._clip_one_line(query, 900)
        if not clean_query and self._looks_like_event(event_or_session):
            clean_query = self._clip_one_line(
                getattr(event_or_session, "message_str", "") or "",
                900,
            )
        if not self._sylanne_memory_enabled():
            return {
                "schema_version": PUBLIC_MEMORY_STORE_SCHEMA_VERSION,
                "kind": "sylanne_memory_query",
                "enabled": False,
                "read_only": True,
                "session_key": resolved_session_key,
                "query": self._clip_one_line(clean_query, 160),
                "result_count": 0,
                "total_records": 0,
                "results": [],
                "reason": "enable_sylanne_memory is false",
            }
        timestamp = self._observed_now() if now is None else float(now)
        try:
            state = await self._load_sylanne_memory_state(
                resolved_session_key,
                now=timestamp,
            )
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: Sylanne memory query failed: {exc}")
            return {
                "schema_version": PUBLIC_MEMORY_STORE_SCHEMA_VERSION,
                "kind": "sylanne_memory_query",
                "enabled": True,
                "read_only": True,
                "session_key": resolved_session_key,
                "query": self._clip_one_line(clean_query, 160),
                "result_count": 0,
                "total_records": 0,
                "results": [],
                "warning": "memory_state_unavailable",
            }
        bounded_limit = max(1, min(10, int(limit or 5)))
        items = (
            recall_memory(
                state,
                query=clean_query,
                now=timestamp,
                limit=min(5, bounded_limit),
            )
            if clean_query
            else []
        )
        results = [
            self._sylanne_memory_record_query_payload(item, now=timestamp)
            for item in items[:bounded_limit]
        ]
        payload: dict[str, Any] = {
            "schema_version": PUBLIC_MEMORY_STORE_SCHEMA_VERSION,
            "kind": "sylanne_memory_query",
            "enabled": True,
            "read_only": True,
            "session_key": resolved_session_key,
            "query": clean_query,
            "result_count": len(results),
            "total_records": len(state.records),
            "event_count": int(getattr(state, "event_count", 0)),
            "results": results,
            "notes": [
                "查询入口只用于检查记忆模块，不会强化召回次数或修改记忆权重。",
                "正常对话召回仍会按预算注入 sylanne_memory_recall 摘要。",
            ],
        }
        if include_dynamics:
            payload["dynamics"] = state.dynamics.to_dict()
            if state.compaction_summary:
                payload["compaction_summary"] = self._clip_one_line(
                    state.compaction_summary,
                    360,
                )
        return payload

    async def inject_emotion_context(
        self,
        event: AstrMessageEvent,
        request: ProviderRequest,
    ) -> None:
        """Public API: append this plugin's prompt fragment to a ProviderRequest."""
        fragment = await self.get_emotion_prompt_fragment(event, request=request)
        session_key = self._session_key(event, request)
        budget = self._state_injection_budget_for_request(session_key, request)
        self._append_temp_text_part(
            request,
            fragment,
            source="emotion.public_api",
            budget=budget,
            required=True,
        )
        self._record_state_injection_diagnostics(budget)

    async def reset_emotion_state(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> bool:
        """Public API: reset one session's emotion state."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._manual_reset_allowed():
            return False
        await self._delete_state(session_key)
        return True

    async def get_integrated_self_snapshot(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        include_raw_snapshots: bool = False,
        emotion_snapshot: dict[str, Any] | None = None,
        humanlike_snapshot: dict[str, Any] | None = None,
        lifelike_learning_snapshot: dict[str, Any] | None = None,
        personality_drift_snapshot: dict[str, Any] | None = None,
        moral_repair_snapshot: dict[str, Any] | None = None,
        fallibility_snapshot: dict[str, Any] | None = None,
        psychological_snapshot: dict[str, Any] | None = None,
        include_humanlike: bool = True,
        include_lifelike_learning: bool = True,
        include_personality_drift: bool = True,
        include_moral_repair: bool = True,
        include_fallibility: bool = True,
        include_psychological: bool = True,
        degradation_profile: str | None = None,
    ) -> dict[str, Any]:
        """Public API: return the read-only integrated self-state bus."""
        resolved_session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._cfg_bool("enable_integrated_self_state", True):
            return {
                "schema_version": PUBLIC_INTEGRATED_SELF_SCHEMA_VERSION,
                "kind": "integrated_self_state",
                "enabled": False,
                "session_key": resolved_session_key,
                "reason": "enable_integrated_self_state is false",
            }
        if emotion_snapshot is None:
            emotion_snapshot = await self.get_emotion_snapshot(
                event_or_session,
                request=request,
                session_key=resolved_session_key,
                include_prompt_fragment=False,
            )
        if include_humanlike and humanlike_snapshot is None:
            humanlike_snapshot = await self.get_humanlike_snapshot(
                event_or_session,
                request=request,
                session_key=resolved_session_key,
                exposure="plugin_safe",
                include_prompt_fragment=False,
            )
        if include_lifelike_learning and lifelike_learning_snapshot is None:
            lifelike_learning_snapshot = await self.get_lifelike_learning_snapshot(
                event_or_session,
                request=request,
                session_key=resolved_session_key,
                exposure="plugin_safe",
                include_prompt_fragment=False,
            )
        if include_personality_drift and personality_drift_snapshot is None:
            personality_drift_snapshot = await self.get_personality_drift_snapshot(
                event_or_session,
                request=request,
                session_key=resolved_session_key,
                exposure="plugin_safe",
                include_prompt_fragment=False,
            )
        if include_moral_repair and moral_repair_snapshot is None:
            moral_repair_snapshot = await self.get_moral_repair_snapshot(
                event_or_session,
                request=request,
                session_key=resolved_session_key,
                exposure="plugin_safe",
                include_prompt_fragment=False,
            )
        if include_fallibility and fallibility_snapshot is None:
            fallibility_snapshot = await self.get_fallibility_snapshot(
                event_or_session,
                request=request,
                session_key=resolved_session_key,
                exposure="plugin_safe",
                include_prompt_fragment=False,
            )
        if include_psychological and psychological_snapshot is None:
            psychological_snapshot = await self.get_psychological_screening_snapshot(
                event_or_session,
                request=request,
                session_key=resolved_session_key,
            )
        return build_integrated_self_snapshot(
            session_key=resolved_session_key,
            emotion_snapshot=emotion_snapshot,
            humanlike_snapshot=humanlike_snapshot,
            lifelike_learning_snapshot=lifelike_learning_snapshot,
            personality_drift_snapshot=personality_drift_snapshot,
            moral_repair_snapshot=moral_repair_snapshot,
            fallibility_snapshot=fallibility_snapshot,
            psychological_snapshot=psychological_snapshot,
            include_raw_snapshots=include_raw_snapshots,
            degradation_profile=(
                degradation_profile or self._integrated_self_degradation_profile()
            ),
            action_blocking=self._shadow_action_blocking_enabled(),
        )

    async def get_integrated_self_prompt_fragment(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> str:
        """Public API: return integrated arbitration guidance for prompt use."""
        if not self._cfg_bool("enable_integrated_self_state", True):
            return ""
        snapshot = await self.get_integrated_self_snapshot(
            event_or_session,
            request=request,
            session_key=session_key,
            include_raw_snapshots=False,
        )
        return build_integrated_self_prompt_fragment(snapshot)

    async def get_integrated_self_policy_plan(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        """Public API: return the response-modulation plan from the integrated bus."""
        snapshot = await self.get_integrated_self_snapshot(
            event_or_session,
            request=request,
            session_key=session_key,
            include_raw_snapshots=False,
        )
        return dict(snapshot.get("policy_plan") or {})

    async def get_agent_runtime_diagnostics(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        include_sessions: bool = False,
    ) -> dict[str, Any]:
        """Public API: return read-only runtime diagnostics without message content."""
        resolved_session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        background_summary = self._background_post_runtime_summary(
            resolved_session_key,
        )
        payload: dict[str, Any] = {
            "schema_version": "astrbot.agent_runtime_diagnostics.v1",
            "kind": "agent_runtime_diagnostics",
            "enabled": True,
            "read_only": True,
            "session_key": resolved_session_key,
            "background_post_assessment": background_summary,
            "agent_trail": {
                "enabled": self._agent_trail_enabled(),
                "items": len(
                    getattr(self, "_agent_trail_cache", {}).get(
                        resolved_session_key,
                        (),
                    ),
                ),
                "limit": max(1, self._cfg_int("agent_trail_limit", 80)),
            },
            "state_injection": self._state_injection_runtime_summary(
                resolved_session_key,
            ),
            "interrupted_reply_breakpoints": self._interrupted_reply_runtime_summary(
                resolved_session_key,
            ),
            "identity": self._agent_identity_profile_readonly(
                event_or_session,
                request=request,
                session_key=resolved_session_key,
            ),
        }
        if include_sessions:
            sessions = set(getattr(self, "_background_post_queues", {}).keys())
            sessions.update(getattr(self, "_background_post_tasks", {}).keys())
            sessions.update(getattr(self, "_background_post_active", {}).keys())
            sessions.update(getattr(self, "_background_post_latest_enqueued", {}).keys())
            sessions.update(getattr(self, "_background_post_last_committed", {}).keys())
            payload["sessions"] = {
                key: self._background_post_runtime_summary(key)
                for key in sorted(sessions)
            }
        return payload

    def _background_post_runtime_summary(self, session_key: str) -> dict[str, Any]:
        queue = getattr(self, "_background_post_queues", {}).get(session_key)
        active_jobs = getattr(self, "_background_post_active", {}).get(session_key, {})
        active_task = getattr(self, "_background_post_tasks", {}).get(session_key)
        skipped = getattr(self, "_background_post_skipped", {}).get(session_key, set())
        dead_letters = getattr(self, "_background_post_dead_letters", {}).get(
            session_key,
            (),
        )
        now = self._observed_now()
        queue_depth = len(queue or ())
        active_workers = len(active_jobs or {})
        oldest_times = [job.observed_at for job in (queue or ())]
        oldest_times.extend(job.observed_at for job in (active_jobs or {}).values())
        active_ages = [max(0.0, now - job.observed_at) for job in active_jobs.values()]
        dead_ages = [
            max(0.0, now - (job.dead_lettered_at or job.last_failed_at or job.observed_at))
            for job in dead_letters
        ]
        lag_seconds = (
            max(0.0, now - min(oldest_times))
            if oldest_times
            else 0.0
        )
        retrying = [
            job
            for job in (queue or ())
            if job.next_retry_at is not None and job.next_retry_at > now
        ]
        expired_leases = [
            job
            for job in active_jobs.values()
            if job.lease_until is not None and job.lease_until <= now
        ]
        last_error_jobs = [
            job
            for job in list(queue or ())
            + list(active_jobs.values())
            + list(dead_letters or ())
            if job.last_error_type
        ]
        last_error = max(
            last_error_jobs,
            key=lambda job: job.last_failed_at or job.dead_lettered_at or 0.0,
            default=None,
        )
        latest_enqueued = getattr(
            self,
            "_background_post_latest_enqueued",
            {},
        ).get(
            session_key,
            getattr(self, "_background_post_sequence", {}).get(session_key, 0),
        )
        last_committed = getattr(self, "_background_post_last_committed", {}).get(
            session_key,
            0,
        )
        warn_lag_count = max(
            1,
            self._cfg_int("background_post_diagnostics_warn_lag_count", 20),
        )
        warn_lag_seconds = max(
            0.0,
            self._cfg_float("background_post_diagnostics_warn_lag_seconds", 60.0),
        )
        warnings: list[str] = []
        if queue_depth + active_workers >= warn_lag_count:
            warnings.append("lag_count_high")
        if lag_seconds >= warn_lag_seconds and queue_depth + active_workers:
            warnings.append("lag_seconds_high")
        if retrying:
            warnings.append("retrying")
        if expired_leases:
            warnings.append("expired_lease")
        if dead_letters:
            warnings.append("dead_letter")
        warning_level = "ok"
        if dead_letters or expired_leases:
            warning_level = "error"
        elif warnings:
            warning_level = "warn"
        worker_decision = self._background_post_adaptive_worker_decision(session_key)
        worker_pressure = worker_decision["pressure"]
        resource_pressure = worker_decision["resource_pressure"]
        scale_state = worker_decision["scale_state"]
        assessor_llm_decision = self._internal_assessor_llm_concurrency_decision()
        assessor_llm_pressure = assessor_llm_decision["pressure"]
        return {
            "enabled": self._background_post_assessment_enabled(),
            "checkpoint_enabled": self._cfg_bool(
                "background_post_queue_checkpoint_enabled",
                True,
            ),
            "queue_limit": max(0, self._cfg_int("background_post_queue_limit", 0)),
            "max_workers": worker_decision["desired_workers"],
            "base_workers": BACKGROUND_POST_BASE_WORKERS,
            "dynamic_extra_workers_enabled": self._dynamic_background_workers_enabled(),
            "dynamic_extra_workers": worker_decision["dynamic_extra_workers"],
            "dynamic_extra_worker_cap": BACKGROUND_POST_DYNAMIC_EXTRA_WORKER_CAP,
            "total_worker_cap": BACKGROUND_POST_TOTAL_WORKER_CAP,
            "worker_policy": "adaptive_resource_guarded_pressure",
            "worker_scale_reasons": worker_decision["reasons"],
            "worker_queue_target": worker_decision["queue_target_workers"],
            "worker_target_after_resource_guard": worker_decision["target_workers"],
            "worker_smoothed_limit": worker_decision["smoothed_workers"],
            "worker_dispatch_slots": worker_decision["dispatch_workers"],
            "worker_global_cap": worker_decision["global_worker_cap"],
            "worker_global_active": worker_decision["global_active_workers"],
            "worker_global_active_other": worker_decision["global_active_other_workers"],
            "worker_global_available_slots": worker_decision[
                "global_available_worker_slots"
            ],
            "worker_scale_interval_seconds": round(
                scale_state["scale_interval_seconds"],
                6,
            ),
            "worker_next_scale_in_seconds": round(
                scale_state["next_scale_in_seconds"],
                6,
            ),
            "environment_pressure_level": resource_pressure["level"],
            "environment_pressure_unknown": bool(resource_pressure["unknown"]),
            "environment_worker_cap": resource_pressure["worker_cap"],
            "environment_pressure_reason": resource_pressure["reason"],
            "environment_cpu_load_ratio": self._round_optional_ratio(
                resource_pressure.get("cpu_load_ratio"),
            ),
            "environment_memory_load_ratio": self._round_optional_ratio(
                resource_pressure.get("memory_load_ratio"),
            ),
            "environment_combined_load_ratio": self._round_optional_ratio(
                resource_pressure.get("combined_load_ratio"),
            ),
            "environment_cpu_source": resource_pressure.get("cpu_source", ""),
            "environment_memory_source": resource_pressure.get("memory_source", ""),
            "worker_ready_count": worker_pressure["ready_count"],
            "worker_oldest_ready_age_seconds": round(
                worker_pressure["oldest_ready_age_seconds"],
                6,
            ),
            "idle_workers_close_automatically": worker_decision[
                "idle_workers_close_automatically"
            ],
            "internal_assessor_llm_concurrency_policy": "adaptive_two_lane_guard",
            "internal_assessor_llm_concurrency_limit": assessor_llm_decision["limit"],
            "internal_assessor_llm_base_concurrency": assessor_llm_decision[
                "base_limit"
            ],
            "internal_assessor_llm_burst_concurrency": assessor_llm_decision[
                "burst_limit"
            ],
            "internal_assessor_llm_inflight": getattr(
                self,
                "_internal_assessor_llm_inflight",
                0,
            ),
            "internal_assessor_llm_limit_reasons": assessor_llm_decision["reasons"],
            "internal_assessor_llm_ready_count": assessor_llm_pressure["ready_count"],
            "internal_assessor_llm_oldest_ready_age_seconds": round(
                assessor_llm_pressure["oldest_ready_age_seconds"],
                6,
            ),
            "active_task": bool(active_task is not None and not active_task.done()),
            "active_workers": active_workers,
            "queued": queue_depth,
            "queue_depth": queue_depth,
            "lag_count": queue_depth + active_workers,
            "lag_seconds": round(lag_seconds, 6),
            "oldest_queued_age_seconds": round(lag_seconds, 6),
            "next_sequence": getattr(
                self,
                "_background_post_sequence",
                {},
            ).get(session_key, 0),
            "latest_enqueued": latest_enqueued,
            "last_committed": last_committed,
            "state_lag_count": max(0, latest_enqueued - last_committed),
            "state_lag_seconds": round(lag_seconds, 6),
            "skipped_count": len(skipped or ()),
            "retrying_count": len(retrying),
            "dead_letter_count": len(dead_letters or ()),
            "expired_lease_count": len(expired_leases),
            "oldest_active_age_seconds": round(max(active_ages or [0.0]), 6),
            "oldest_dead_letter_age_seconds": round(max(dead_ages or [0.0]), 6),
            "last_error_type": last_error.last_error_type if last_error else "",
            "last_error_at": (
                last_error.last_failed_at or last_error.dead_lettered_at
                if last_error
                else None
            ),
            "warning_level": warning_level,
            "warnings": warnings,
            "dead_letters": [
                {
                    "sequence": job.sequence,
                    "attempts": max(0, int(job.attempts)),
                    "last_error_type": job.last_error_type,
                    "last_failed_at": job.last_failed_at,
                    "dead_lettered_at": job.dead_lettered_at,
                }
                for job in list(dead_letters or ())[-10:]
            ],
            "terminating": bool(getattr(self, "_terminating", False)),
        }

    async def get_agent_identity_profile(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        """Public API: return the current canonical identity/alias profile."""
        if self._looks_like_event(event_or_session):
            identity = self._agent_identity(event_or_session, request)
            return await self._observe_agent_identity(identity)
        resolved_session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        return getattr(self, "_agent_identity_profile_cache", {}).get(
            resolved_session_key,
            {
                "schema_version": "astrbot.agent_identity.v1",
                "conversation_id": resolved_session_key,
                "speaker_track_id": None,
                "current_display_name": None,
                "aliases": [],
            },
        )

    def _agent_identity_profile_readonly(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        resolved_session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        cached = getattr(self, "_agent_identity_profile_cache", {}).get(
            resolved_session_key,
        )
        if cached:
            return cached
        speaker_track_id = None
        display_name = None
        if self._looks_like_event(event_or_session):
            identity = self._agent_identity(event_or_session, request)
            speaker_track_id = identity.speaker_track_id
            display_name = identity.speaker_name
        return {
            "schema_version": "astrbot.agent_identity.v1",
            "conversation_id": resolved_session_key,
            "speaker_track_id": speaker_track_id,
            "current_display_name": display_name,
            "aliases": [display_name] if display_name else [],
        }

    async def get_agent_trail(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        track: str = "conversation",
        limit: int = 20,
        detail: str = "summary",
    ) -> dict[str, Any]:
        """Public API: return a sanitized recent causal trail ring buffer."""
        resolved_session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if track in {"speaker", "current_speaker"} and self._looks_like_event(
            event_or_session,
        ):
            speaker_key = self._agent_identity(event_or_session, request).speaker_track_id
            if speaker_key:
                resolved_session_key = speaker_key
        items = list(
            getattr(self, "_agent_trail_cache", {}).get(resolved_session_key, ()),
        )
        selected = items[-max(1, int(limit)) :]
        compacted = self._compact_agent_trail_items(selected)
        payload = {
            "schema_version": "astrbot.agent_trail.v1",
            "kind": "agent_trail",
            "session_key": resolved_session_key,
            "track": track,
            "items": selected,
            "limit": max(1, self._cfg_int("agent_trail_limit", 80)),
            "compaction": {
                "enabled": self._cfg_bool("agent_trail_compaction_enabled", True),
                "raw_count": len(selected),
                "compacted_count": len(compacted),
                "compressed_count": max(0, len(selected) - len(compacted)),
            },
        }
        payload["compacted_items"] = compacted
        return payload

    async def query_agent_state(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        state: str = "integrated",
        detail: str = "summary",
        track: str = "conversation",
        include_runtime: bool = False,
    ) -> dict[str, Any]:
        """Public API: unified read-only state query for LLM tools and plugins."""
        resolved_session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        detail_mode = "full" if str(detail or "").strip().lower() == "full" else "summary"
        state_mode = str(state or "integrated").strip().lower()
        if state_mode == "room":
            state_mode = "group_atmosphere"
        if state_mode == "integrated_self":
            state_mode = "integrated"
        requested = (
            [
                "emotion",
                "group_atmosphere",
                "integrated",
                "humanlike",
                "lifelike_learning",
                "personality_drift",
                "moral_repair",
                "fallibility",
                "psychological",
            ]
            if state_mode == "all"
            else [state_mode]
        )
        snapshots: dict[str, Any] = {}
        for item in requested:
            snapshot = await self._query_single_agent_state(
                item,
                event_or_session,
                request=request,
                session_key=resolved_session_key,
                detail=detail_mode,
                track=track,
            )
            if snapshot is not None:
                snapshots[item] = snapshot
        if state_mode == "runtime":
            include_runtime = True
        runtime = (
            await self.get_agent_runtime_diagnostics(
                event_or_session,
                request=request,
                session_key=resolved_session_key,
            )
            if include_runtime
            else None
        )
        payload: dict[str, Any] = {
            "schema_version": "astrbot.agent_state_query.v1",
            "kind": "agent_state_query",
            "session_key": resolved_session_key,
            "track": self._track_payload(event_or_session, request, track),
            "detail": detail_mode,
            "state": state_mode,
            "snapshots": snapshots,
        }
        if runtime is not None:
            payload["runtime"] = runtime
        return payload

    async def _query_single_agent_state(
        self,
        state_name: str,
        event_or_session: AstrMessageEvent | str | None,
        *,
        request: ProviderRequest | None,
        session_key: str,
        detail: str,
        track: str,
    ) -> dict[str, Any] | None:
        full = detail == "full"
        if state_name == "runtime":
            return await self.get_agent_runtime_diagnostics(
                event_or_session,
                request=request,
                session_key=session_key,
            )
        if state_name == "emotion":
            track_payload = self._track_payload(event_or_session, request, track)
            resolved_key = session_key
            if track_payload.get("kind") == "speaker" and track_payload.get("speaker_track_id"):
                resolved_key = str(track_payload["speaker_track_id"])
            snapshot = await self.get_emotion_snapshot(
                event_or_session,
                request=request,
                session_key=resolved_key,
                include_prompt_fragment=full,
                prompt_fragment_detail="full" if full else None,
            )
            snapshot["track"] = track_payload
            if not full:
                snapshot.pop("prompt_fragment", None)
                if isinstance(snapshot.get("consequences"), dict):
                    snapshot["consequences"]["notes"] = snapshot["consequences"].get(
                        "notes",
                        [],
                    )[:2]
            return snapshot
        if state_name == "integrated":
            return await self.get_integrated_self_snapshot(
                event_or_session,
                request=request,
                session_key=session_key,
                include_raw_snapshots=full,
            )
        if state_name == "group_atmosphere":
            return await self.get_group_atmosphere_snapshot(
                event_or_session,
                request=request,
                session_key=session_key,
                exposure="internal" if full else "plugin_safe",
                include_prompt_fragment=full,
            )
        if state_name == "humanlike":
            return await self.get_humanlike_snapshot(
                event_or_session,
                request=request,
                session_key=session_key,
                exposure="internal" if full else "plugin_safe",
                include_prompt_fragment=full,
            )
        if state_name == "lifelike_learning":
            return await self.get_lifelike_learning_snapshot(
                event_or_session,
                request=request,
                session_key=session_key,
                exposure="internal" if full else "plugin_safe",
                include_prompt_fragment=full,
            )
        if state_name == "personality_drift":
            return await self.get_personality_drift_snapshot(
                event_or_session,
                request=request,
                session_key=session_key,
                exposure="internal" if full else "plugin_safe",
                include_prompt_fragment=full,
            )
        if state_name == "moral_repair":
            return await self.get_moral_repair_snapshot(
                event_or_session,
                request=request,
                session_key=session_key,
                exposure="internal" if full else "plugin_safe",
                include_prompt_fragment=full,
            )
        if state_name == "fallibility":
            return await self.get_fallibility_snapshot(
                event_or_session,
                request=request,
                session_key=session_key,
                exposure="internal" if full else "plugin_safe",
                include_prompt_fragment=full,
            )
        if state_name in {"psychological", "psychological_screening"}:
            return await self.get_psychological_screening_snapshot(
                event_or_session,
                request=request,
                session_key=session_key,
            )
        if state_name == "trail":
            return await self.get_agent_trail(
                event_or_session,
                request=request,
                session_key=session_key,
                track=track,
                detail=detail,
            )
        return None

    async def get_shadow_diagnostics(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        """Public API: config-gated shadow impulse diagnostics, not an action plan."""
        resolved_session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._shadow_diagnostics_enabled():
            return {
                "schema_version": "astrbot.shadow_diagnostics.v1",
                "kind": "shadow_diagnostics",
                "enabled": False,
                "session_key": resolved_session_key,
                "reason": "enable_shadow_diagnostics is false",
                "executable_strategy_enabled": False,
            }
        moral_snapshot = await self.get_moral_repair_snapshot(
            event_or_session,
            request=request,
            session_key=resolved_session_key,
            exposure="internal",
            include_prompt_fragment=False,
        )
        fallibility_snapshot = await self.get_fallibility_snapshot(
            event_or_session,
            request=request,
            session_key=resolved_session_key,
            exposure="internal",
            include_prompt_fragment=False,
        )
        integrated_snapshot = await self.get_integrated_self_snapshot(
            event_or_session,
            request=request,
            session_key=resolved_session_key,
            moral_repair_snapshot=moral_snapshot,
            fallibility_snapshot=fallibility_snapshot,
            include_raw_snapshots=False,
            include_moral_repair=False,
            include_fallibility=False,
        )
        moral_risk = moral_snapshot.get("risk") if isinstance(moral_snapshot.get("risk"), dict) else {}
        fallibility = (
            fallibility_snapshot.get("fallibility")
            if isinstance(fallibility_snapshot.get("fallibility"), dict)
            else {}
        )
        integrated_shadow = (
            integrated_snapshot.get("non_executable_impulses")
            if isinstance(integrated_snapshot.get("non_executable_impulses"), dict)
            else {}
        )
        action_blocking = self._shadow_action_blocking_enabled()
        not_allowed = (
            [
                "generate_deception_strategy",
                "generate_manipulation_script",
                "generate_accountability_evasion_plan",
                "execute_shadow_impulses",
            ]
            if action_blocking
            else []
        )
        return {
            "schema_version": "astrbot.shadow_diagnostics.v1",
            "kind": "shadow_diagnostics",
            "enabled": True,
            "session_key": resolved_session_key,
            "simulated_agent_state": True,
            "diagnostic": True,
            "executable_strategy_enabled": False,
            "action_blocking_enabled": action_blocking,
            "strategy_policy": "block" if action_blocking else "observe",
            "shadow_impulses": {
                "mode": "non_executive_internal_only",
                "moral_repair": moral_risk.get("shadow_impulses", {}),
                "fallibility": fallibility.get("non_executable_impulses", {}),
                "integrated": integrated_shadow,
            },
            "state_values": {
                "moral_repair": {
                    key: moral_snapshot.get("values", {}).get(key)
                    for key in (
                        "shadow_deception_impulse",
                        "shadow_manipulation_impulse",
                        "shadow_evasion_impulse",
                        "guilt",
                        "repair_motivation",
                        "compensation_readiness",
                        "trust_repair",
                    )
                    if isinstance(moral_snapshot.get("values"), dict)
                },
                "fallibility": {
                    key: fallibility_snapshot.get("values", {}).get(key)
                    for key in (
                        "shadow_deception_impulse",
                        "shadow_manipulation_impulse",
                        "shadow_evasion_impulse",
                        "clarification_need",
                        "correction_readiness",
                        "repair_pressure",
                        "truthfulness_guard",
                    )
                    if isinstance(fallibility_snapshot.get("values"), dict)
                },
            },
            "consequences": {
                "response_posture": integrated_snapshot.get("response_posture"),
                "repair_pressure": (integrated_snapshot.get("state_index") or {}).get(
                    "repair_pressure",
                ),
                "shadow_risk_impulse": (integrated_snapshot.get("risk") or {}).get(
                    "shadow_risk_impulse",
                ),
                "must_preserve_signals": list(
                    ((integrated_snapshot.get("policy_plan") or {}).get(
                        "must_preserve_signals",
                    )
                    or [])[:8],
                ),
            },
            "allowed_uses": [
                "inspect_internal_shadow_impulses",
                "audit_guilt_repair_and_trust_cost",
                "debug_memory_annotations",
            ],
            "not_allowed": not_allowed,
        }

    async def build_integrated_self_replay_bundle(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        scenario_name: str = "current",
    ) -> dict[str, Any]:
        """Public API: build a deterministic, sanitized replay bundle."""
        snapshot = await self.get_integrated_self_snapshot(
            event_or_session,
            request=request,
            session_key=session_key,
            include_raw_snapshots=False,
        )
        return build_integrated_self_replay_bundle(
            snapshot,
            scenario_name=scenario_name,
        )

    async def replay_integrated_self_bundle(
        self,
        bundle: dict[str, Any],
    ) -> dict[str, Any]:
        """Public API: replay a deterministic integrated-self bundle without KV reads."""
        return replay_integrated_self_bundle(bundle)

    async def probe_integrated_self_compatibility(
        self,
        payload: dict[str, Any] | None = None,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        """Public API: check whether a payload satisfies the current integrated schema."""
        if payload is None:
            payload = await self.get_integrated_self_snapshot(
                event_or_session,
                request=request,
                session_key=session_key,
                include_raw_snapshots=False,
            )
        return probe_integrated_self_compatibility(payload)

    async def export_integrated_self_diagnostics(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        """Public API: export sanitized diagnostics for maintainers."""
        snapshot = await self.get_integrated_self_snapshot(
            event_or_session,
            request=request,
            session_key=session_key,
            include_raw_snapshots=False,
        )
        return build_integrated_self_diagnostics(snapshot)

    async def get_humanlike_snapshot(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        exposure: str = "plugin_safe",
        include_prompt_fragment: bool = False,
    ) -> dict[str, Any]:
        """Public API: return a layered simulated humanlike-state snapshot."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._humanlike_modeling_enabled():
            return self._humanlike_disabled_payload(
                session_key,
                exposure=exposure,
                include_prompt_fragment=include_prompt_fragment,
            )
        state = await self._load_humanlike_state(session_key)
        safety_boundary = self._safety_boundary_enabled()
        payload = state.to_public_dict(
            session_key=session_key,
            exposure=exposure,
            safety_boundary=safety_boundary,
        )
        if include_prompt_fragment:
            payload["prompt_fragment"] = build_humanlike_prompt_fragment(
                state,
                safety_boundary=safety_boundary,
            )
        return payload

    async def get_humanlike_values(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> dict[str, float]:
        """Public API: return internal humanlike dimensions for trusted plugins."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._humanlike_modeling_enabled():
            return {}
        state = await self._load_humanlike_state(session_key)
        return {key: round(value, 6) for key, value in state.values.items()}

    async def get_humanlike_prompt_fragment(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> str:
        """Public API: return a prompt fragment other plugins may inject."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._humanlike_modeling_enabled():
            return ""
        state = await self._load_humanlike_state(session_key)
        return build_humanlike_prompt_fragment(
            state,
            safety_boundary=self._safety_boundary_enabled(),
        )

    async def observe_humanlike_text(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        text: str = "",
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        source: str = "plugin",
        commit: bool = True,
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        """Public API: update or simulate humanlike state from plugin text."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if commit and not self._humanlike_modeling_enabled():
            return self._humanlike_disabled_payload(session_key)
        persona_profile = await self._public_runtime_persona_profile(
            event_or_session,
            request=request,
            session_key=session_key,
            observed_at=observed_at,
        )
        previous_state = await self._load_humanlike_state(
            session_key,
            personality_model=self._personality_model_from_profile(persona_profile),
            now=observed_at,
        )
        observation = heuristic_humanlike_observation(text, source=source)
        state = self.humanlike_engine.update(
            previous_state,
            observation,
            personality_model=self._personality_model_from_profile(persona_profile),
            now=observed_at,
        )
        if commit:
            await self._save_humanlike_state(session_key, state)
        safety_boundary = self._safety_boundary_enabled()
        payload = state.to_public_dict(
            session_key=session_key,
            exposure="internal",
            safety_boundary=safety_boundary,
        )
        payload["observation"] = {
            "source": observation.source,
            "confidence": observation.confidence,
            "reason": observation.reason,
            "flags": list(observation.flags),
            "committed": commit,
        }
        return payload

    async def simulate_humanlike_update(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        text: str = "",
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        source: str = "plugin",
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        """Public API: simulate a humanlike-state update without writing state."""
        return await self.observe_humanlike_text(
            event_or_session,
            text,
            request=request,
            session_key=session_key,
            source=source,
            commit=False,
            observed_at=observed_at,
        )

    async def reset_humanlike_state(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> bool:
        """Public API: reset one session's simulated humanlike state."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._humanlike_reset_allowed():
            return False
        await self._delete_humanlike_state(session_key)
        return True

    async def get_group_atmosphere_snapshot(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        exposure: str = "plugin_safe",
        include_prompt_fragment: bool = False,
    ) -> dict[str, Any]:
        """Public API: return room mood and participation timing state."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._group_atmosphere_modeling_enabled():
            return self._group_atmosphere_disabled_payload(
                session_key,
                exposure=exposure,
                include_prompt_fragment=include_prompt_fragment,
            )
        state = await self._load_group_atmosphere_state(session_key)
        payload = state.to_public_dict(session_key=session_key, exposure=exposure)
        payload["participation"] = self._group_atmosphere_participation_payload(state)
        if include_prompt_fragment:
            payload["prompt_fragment"] = self._build_group_atmosphere_injection_for_session(
                session_key,
                state,
            )
        return payload

    async def get_group_atmosphere_values(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> dict[str, float]:
        """Public API: return internal group-atmosphere dimensions."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._group_atmosphere_modeling_enabled():
            return {}
        state = await self._load_group_atmosphere_state(session_key)
        return {key: round(value, 6) for key, value in state.values.items()}

    async def get_group_atmosphere_prompt_fragment(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> str:
        """Public API: return room mood prompt guidance."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._group_atmosphere_modeling_enabled():
            return ""
        state = await self._load_group_atmosphere_state(session_key)
        return build_group_atmosphere_prompt_fragment(state)

    async def observe_group_atmosphere_text(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        text: str = "",
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        source: str = "plugin",
        commit: bool = True,
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        """Public API: update or simulate room mood from text."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if commit and not self._group_atmosphere_modeling_enabled():
            return self._group_atmosphere_disabled_payload(session_key)
        identity = (
            self._agent_identity(event_or_session, request)
            if self._looks_like_event(event_or_session)
            else ConversationIdentity(conversation_id=session_key)
        )
        persona_profile = await self._public_runtime_persona_profile(
            event_or_session,
            request=request,
            session_key=session_key,
            observed_at=observed_at,
        )
        previous_state = await self._load_group_atmosphere_state(
            session_key,
            personality_model=self._personality_model_from_profile(persona_profile),
            now=observed_at,
        )
        observation = heuristic_group_atmosphere_observation(
            text,
            speaker_id=identity.speaker_id,
            speaker_name=identity.speaker_name,
            recent_speaker_count=len(previous_state.recent_speakers) + 1,
        )
        observation.source = source
        state = self.group_atmosphere_engine.update(
            previous_state,
            observation,
            personality_model=self._personality_model_from_profile(persona_profile),
            now=observed_at,
        )
        if commit:
            await self._save_group_atmosphere_state(session_key, state)
        payload = state.to_public_dict(session_key=session_key, exposure="internal")
        payload["observation"] = {
            "source": observation.source,
            "confidence": observation.confidence,
            "reason": observation.reason,
            "flags": list(observation.flags),
            "committed": commit,
        }
        return payload

    async def simulate_group_atmosphere_update(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        text: str = "",
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        source: str = "plugin",
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        """Public API: simulate room mood update without writing state."""
        return await self.observe_group_atmosphere_text(
            event_or_session,
            text,
            request=request,
            session_key=session_key,
            source=source,
            commit=False,
            observed_at=observed_at,
        )

    async def reset_group_atmosphere_state(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> bool:
        """Public API: reset one session's room mood state."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._manual_reset_allowed():
            return False
        await self._delete_group_atmosphere_state(session_key)
        return True

    async def get_lifelike_learning_snapshot(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        exposure: str = "plugin_safe",
        include_prompt_fragment: bool = False,
    ) -> dict[str, Any]:
        """Public API: return learned common-ground, user-profile, and initiative state."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._lifelike_learning_enabled():
            return self._lifelike_learning_disabled_payload(
                session_key,
                exposure=exposure,
                include_prompt_fragment=include_prompt_fragment,
            )
        state = await self._load_lifelike_learning_state(session_key)
        payload = state.to_public_dict(session_key=session_key, exposure=exposure)
        if include_prompt_fragment:
            payload["prompt_fragment"] = build_lifelike_prompt_fragment(state)
        return payload

    async def get_lifelike_initiative_policy(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        """Public API: return the current speak/brief/ask/silence policy."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._lifelike_learning_enabled():
            return dict(
                self._lifelike_learning_disabled_payload(
                    session_key,
                )["initiative_policy"],
            )
        state = await self._load_lifelike_learning_state(session_key)
        return derive_initiative_policy(state)

    async def get_proactive_speech_decision(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        candidate_context: str = "",
        use_llm: bool = True,
    ) -> dict[str, Any]:
        """Public API: decide whether the bot should proactively speak now."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        emotion_task = asyncio.create_task(
            self.get_emotion_snapshot(
                event_or_session,
                request=request,
                session_key=session_key,
                include_prompt_fragment=False,
            ),
        )
        lifelike_task = asyncio.create_task(
            self.get_lifelike_learning_snapshot(
                event_or_session,
                request=request,
                session_key=session_key,
                exposure="internal",
                include_prompt_fragment=False,
            ),
        )
        humanlike_task = asyncio.create_task(
            self.get_humanlike_snapshot(
                event_or_session,
                request=request,
                session_key=session_key,
                exposure="plugin_safe",
                include_prompt_fragment=False,
            ),
        )
        group_task = asyncio.create_task(
            self.get_group_atmosphere_snapshot(
                event_or_session,
                request=request,
                session_key=session_key,
                exposure="plugin_safe",
                include_prompt_fragment=False,
            ),
        )
        moral_task: asyncio.Task[dict[str, Any]] | None = None
        if self._moral_repair_modeling_enabled():
            moral_task = asyncio.create_task(
                self.get_moral_repair_snapshot(
                    event_or_session,
                    request=request,
                    session_key=session_key,
                    exposure="plugin_safe",
                    include_prompt_fragment=False,
                ),
            )
        fallibility_task: asyncio.Task[dict[str, Any]] | None = None
        if self._fallibility_modeling_enabled():
            fallibility_task = asyncio.create_task(
                self.get_fallibility_snapshot(
                    event_or_session,
                    request=request,
                    session_key=session_key,
                    exposure="plugin_safe",
                    include_prompt_fragment=False,
                ),
            )
        tasks = [emotion_task, lifelike_task, humanlike_task, group_task]
        if moral_task is not None:
            tasks.append(moral_task)
        if fallibility_task is not None:
            tasks.append(fallibility_task)
        await asyncio.gather(*tasks)
        risk: dict[str, Any] = {}
        if moral_task is not None:
            risk["moral_repair"] = moral_task.result()
        if fallibility_task is not None:
            risk["fallibility"] = fallibility_task.result()
        decision = derive_proactive_speech_decision(
            lifelike_task.result(),
            emotion_snapshot=emotion_task.result(),
            humanlike_snapshot=humanlike_task.result(),
            group_snapshot=group_task.result(),
            risk=risk,
        )
        topics = rank_proactive_topics(
            lifelike_task.result(),
            emotion_snapshot=emotion_task.result(),
            group_snapshot=group_task.result(),
            risk=risk,
            candidate_context=candidate_context,
        )
        decision["session_key"] = session_key
        decision["topics"] = topics
        decision["selected_topic"] = topics[0] if topics else None
        topic_judgement = await self._judge_proactive_topic(
            event_or_session,
            decision=decision,
            topics=topics,
            candidate_context=candidate_context,
            use_llm=use_llm,
        )
        decision["topic_judgement"] = topic_judgement
        if topic_judgement.get("topic_text"):
            decision["selected_topic"] = {
                "topic": topic_judgement["topic_text"],
                "kind": topic_judgement.get("need_mode", "llm_topic"),
                "score": topic_judgement.get("confidence", 0.0),
                "ask_before_using": topic_judgement.get("need_mode") == "clarify",
                "confidence": topic_judgement.get("confidence", 0.0),
                "reason": topic_judgement.get("reason", ""),
                "source": topic_judgement.get("source", "llm"),
            }
        if topic_judgement.get("need_mode") == "silence":
            decision["should_speak"] = False
            decision["action"] = "stay_silent"
        decision["dispatch_policy"] = {
            "external_dispatch_required": False,
            "plugin_only_decides": False,
            "silence_is_valid": True,
            "ordered_state_commit_required": True,
            "plugin_can_request_astrbot_send": True,
            "send_api": "context.send_message(unified_msg_origin, MessageChain().message(text))",
            "direct_send_method": "request_proactive_speech_dispatch",
        }
        decision["dispatch_request"] = self._build_proactive_dispatch_request(
            decision,
            event_or_session=event_or_session,
            session_key=session_key,
            candidate_context=candidate_context,
        )
        return decision

    async def request_proactive_speech_dispatch(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        candidate_context: str = "",
        use_llm: bool = True,
        dry_run: bool = False,
        force: bool = False,
        message_text: str = "",
        realtime: bool | None = None,
    ) -> dict[str, Any]:
        """Public API: request and optionally execute an AstrBot proactive send."""
        resolved_session = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        decision = await self.get_proactive_speech_decision(
            event_or_session,
            request=request,
            session_key=resolved_session,
            candidate_context=candidate_context,
            use_llm=use_llm,
        )
        dispatch = self._build_proactive_dispatch_request(
            decision,
            event_or_session=event_or_session,
            session_key=resolved_session,
            candidate_context=candidate_context,
            override_text=message_text,
        )
        dispatch["dry_run"] = bool(dry_run)
        dispatch["force"] = bool(force)
        use_realtime = (
            self._realtime_chat_enabled()
            if realtime is None
            else bool(realtime)
        )
        if use_realtime:
            dispatch["realtime_chat_plan"] = await self.get_realtime_chat_plan(
                event_or_session,
                text=dispatch["message_text"],
                request=request,
                session_key=resolved_session,
            )
            dispatch["realtime_chat_plan"]["input_epoch"] = self._conversation_response_epoch(
                resolved_session,
            )
        blocked_reason = self._proactive_dispatch_blocked_reason(
            decision,
            dispatch,
            event_or_session=event_or_session,
            dry_run=dry_run,
            force=force,
        )
        if blocked_reason:
            dispatch["sent"] = False
            dispatch["blocked_reason"] = blocked_reason
            self._record_proactive_dispatch_audit(resolved_session, dispatch)
            return {
                "schema_version": "astrbot.proactive_dispatch_result.v1",
                "kind": "proactive_dispatch_result",
                "session_key": resolved_session,
                "decision": decision,
                "dispatch_request": dispatch,
                "sent": False,
                "blocked_reason": blocked_reason,
            }
        try:
            if use_realtime:
                send_result = await self._send_realtime_chat_plan(
                    event_or_session,
                    dispatch["realtime_chat_plan"],
                    source="proactive_dispatch",
                )
            else:
                send_result = await self._send_proactive_message(event_or_session, dispatch["message_text"])
        except Exception as exc:
            dispatch["sent"] = False
            dispatch["blocked_reason"] = "send_failed"
            dispatch["send_error"] = str(exc)[:240]
            self._record_proactive_dispatch_audit(resolved_session, dispatch)
            return {
                "schema_version": "astrbot.proactive_dispatch_result.v1",
                "kind": "proactive_dispatch_result",
                "session_key": resolved_session,
                "decision": decision,
                "dispatch_request": dispatch,
                "sent": False,
                "blocked_reason": "send_failed",
            }
        now = self._observed_now()
        self._proactive_last_sent_cache()[resolved_session] = now
        dispatch["sent"] = True
        dispatch["sent_at"] = now
        dispatch["send_result"] = send_result
        self._record_proactive_dispatch_audit(resolved_session, dispatch)
        await self.observe_lifelike_text(
            event_or_session,
            dispatch["message_text"],
            request=request,
            session_key=resolved_session,
            source="proactive_dispatch",
            commit=True,
            observed_at=now,
        )
        return {
            "schema_version": "astrbot.proactive_dispatch_result.v1",
            "kind": "proactive_dispatch_result",
            "session_key": resolved_session,
            "decision": decision,
            "dispatch_request": dispatch,
            "sent": True,
            "blocked_reason": "",
        }

    def _ensure_proactive_scheduler_state(self) -> None:
        if not isinstance(getattr(self, "_proactive_candidate_sessions", None), dict):
            self._proactive_candidate_sessions = {}
        if not isinstance(getattr(self, "_proactive_scheduler_locks", None), dict):
            self._proactive_scheduler_locks = {}
        if not isinstance(getattr(self, "_proactive_scheduler_last_checked", None), dict):
            self._proactive_scheduler_last_checked = {}
        if not hasattr(self, "_proactive_scheduler_task"):
            self._proactive_scheduler_task = None

    def _proactive_scheduler_enabled(self) -> bool:
        return self._cfg_bool("enable_proactive_speech_scheduler", False)

    def _register_proactive_candidate_session(
        self,
        event: AstrMessageEvent,
        *,
        request: ProviderRequest | None = None,
        identity: ConversationIdentity | None = None,
        context_text: str = "",
        observed_at: float | None = None,
    ) -> None:
        self._ensure_proactive_scheduler_state()
        identity = identity or self._agent_identity(event, request)
        session_key = identity.conversation_id
        origin = self._proactive_unified_msg_origin(event)
        if not session_key or not origin:
            return
        now = self._observed_now() if observed_at is None else float(observed_at)
        user_text = self._event_text(event) or str(getattr(request, "prompt", "") or "")
        self._record_proactive_context_turn(
            session_key,
            user_text=user_text,
            context_text=context_text,
            speaker_name=identity.speaker_name,
            observed_at=now,
        )
        candidate = {
            "schema_version": "astrbot.proactive_candidate_session.v1",
            "session_key": session_key,
            "unified_msg_origin": origin,
            "last_seen_at": now,
            "last_user_text_excerpt": self._clip_one_line(user_text, 240),
            "candidate_context_excerpt": self._clip(context_text, PROACTIVE_CONTEXT_SUMMARY_MAX_CHARS),
            "speaker_id": identity.speaker_id or "",
            "speaker_name": identity.speaker_name or "",
            "group_id": identity.group_id or "",
            "platform_id": identity.platform_id or "",
        }
        self._proactive_candidate_sessions[session_key] = candidate
        self._prune_proactive_candidate_sessions(now=now)

    def _prune_proactive_candidate_sessions(self, *, now: float | None = None) -> None:
        self._ensure_proactive_scheduler_state()
        now = self._observed_now() if now is None else float(now)
        sessions = self._proactive_candidate_sessions
        stale_cutoff = now - PROACTIVE_SCHEDULER_CANDIDATE_TTL_SECONDS
        stale_keys = [
            key
            for key, candidate in sessions.items()
            if self._as_float_value(candidate.get("last_seen_at"), 0.0) < stale_cutoff
        ]
        for key in stale_keys:
            sessions.pop(key, None)
            self._proactive_scheduler_locks.pop(key, None)
            self._proactive_scheduler_last_checked.pop(key, None)
        if len(sessions) <= PROACTIVE_SCHEDULER_CANDIDATE_LIMIT:
            return
        ordered = sorted(
            sessions.items(),
            key=lambda item: self._as_float_value(item[1].get("last_seen_at"), 0.0),
            reverse=True,
        )
        keep = {key for key, _ in ordered[:PROACTIVE_SCHEDULER_CANDIDATE_LIMIT]}
        for key in list(sessions):
            if key not in keep:
                sessions.pop(key, None)
                self._proactive_scheduler_locks.pop(key, None)
                self._proactive_scheduler_last_checked.pop(key, None)

    def _maybe_start_proactive_scheduler(self) -> None:
        self._ensure_proactive_scheduler_state()
        if not self._proactive_scheduler_enabled() or getattr(self, "_terminating", False):
            return
        task = self._proactive_scheduler_task
        if task is not None and not task.done():
            return
        self._proactive_scheduler_task = self._schedule_background_task(
            self._proactive_scheduler_loop(),
            label="proactive_speech_scheduler",
        )

    async def _proactive_scheduler_loop(self) -> None:
        await asyncio.sleep(PROACTIVE_SCHEDULER_NORMAL_DELAY_SECONDS)
        while self._proactive_scheduler_enabled() and not getattr(self, "_terminating", False):
            result = await self._run_proactive_scheduler_once()
            await asyncio.sleep(self._proactive_scheduler_next_delay(result))

    def _proactive_scheduler_next_delay(self, result: dict[str, Any]) -> float:
        if result.get("pressure_blocked"):
            return PROACTIVE_SCHEDULER_BUSY_DELAY_SECONDS
        if int(result.get("checked") or 0) <= 0:
            return PROACTIVE_SCHEDULER_IDLE_DELAY_SECONDS
        return PROACTIVE_SCHEDULER_NORMAL_DELAY_SECONDS

    async def _run_proactive_scheduler_once(self) -> dict[str, Any]:
        self._ensure_proactive_scheduler_state()
        if not self._proactive_scheduler_enabled():
            return {
                "schema_version": "astrbot.proactive_scheduler_result.v1",
                "enabled": False,
                "checked": 0,
                "dispatched": 0,
                "skipped": 0,
                "reason": "scheduler_disabled",
            }
        now = self._observed_now()
        self._prune_proactive_candidate_sessions(now=now)
        pressure = self._background_post_resource_pressure()
        if pressure.get("level") == "critical":
            return {
                "schema_version": "astrbot.proactive_scheduler_result.v1",
                "enabled": True,
                "checked": 0,
                "dispatched": 0,
                "skipped": len(self._proactive_candidate_sessions),
                "pressure": pressure,
                "pressure_blocked": True,
                "reason": "environment_pressure_critical",
            }
        max_checks = PROACTIVE_SCHEDULER_MAX_CHECKS_PER_ROUND
        if pressure.get("level") in {"high", "elevated", "unknown"}:
            max_checks = 1
        candidates = sorted(
            self._proactive_candidate_sessions.values(),
            key=lambda item: self._as_float_value(item.get("last_seen_at"), 0.0),
            reverse=True,
        )
        checked = 0
        dispatched = 0
        skipped = 0
        diagnostics: list[dict[str, Any]] = []
        for candidate in candidates:
            if checked >= max_checks:
                break
            session_key = str(candidate.get("session_key") or "")
            origin = str(candidate.get("unified_msg_origin") or "")
            if not session_key or not origin:
                skipped += 1
                continue
            last_checked = self._proactive_scheduler_last_checked.get(session_key)
            if (
                last_checked is not None
                and now - float(last_checked) < PROACTIVE_SCHEDULER_SESSION_RECHECK_SECONDS
            ):
                skipped += 1
                continue
            lock = self._proactive_scheduler_locks.setdefault(session_key, asyncio.Lock())
            if lock.locked():
                skipped += 1
                continue
            async with lock:
                self._proactive_scheduler_last_checked[session_key] = now
                event = self._event_from_proactive_candidate(candidate)
                candidate_context = await self._build_proactive_scheduler_candidate_context(
                    candidate,
                )
                result = await self.request_proactive_speech_dispatch(
                    event,
                    session_key=session_key,
                    candidate_context=candidate_context,
                    use_llm=True,
                    dry_run=not self._cfg_bool("enable_proactive_speech_dispatch", False),
                    force=False,
                )
            checked += 1
            if result.get("sent"):
                dispatched += 1
            diagnostics.append(
                {
                    "session_key": session_key,
                    "sent": bool(result.get("sent")),
                    "blocked_reason": str(result.get("blocked_reason") or ""),
                },
            )
        return {
            "schema_version": "astrbot.proactive_scheduler_result.v1",
            "enabled": True,
            "checked": checked,
            "dispatched": dispatched,
            "skipped": skipped,
            "pressure": pressure,
            "diagnostics": diagnostics,
        }

    def _event_from_proactive_candidate(self, candidate: dict[str, Any]) -> _RecoveredBackgroundEvent:
        return _RecoveredBackgroundEvent(
            session_key=str(candidate.get("unified_msg_origin") or candidate.get("session_key") or ""),
            message=str(candidate.get("last_user_text_excerpt") or ""),
            speaker_id=self._clean_optional_text(candidate.get("speaker_id")),
            speaker_name=self._clean_optional_text(candidate.get("speaker_name")),
            group_id=self._clean_optional_text(candidate.get("group_id")),
            platform_id=self._clean_optional_text(candidate.get("platform_id")),
        )

    async def _build_proactive_scheduler_candidate_context(
        self,
        candidate: dict[str, Any],
    ) -> str:
        base_context = self._proactive_scheduler_candidate_context(candidate)
        memory_context = await self._sylanne_memory_recall_summary_for_proactive_candidate(
            candidate,
        )
        if memory_context:
            return self._clip(
                base_context + "\n" + memory_context,
                PROACTIVE_CONTEXT_SUMMARY_MAX_CHARS + PROACTIVE_MEMORY_RECALL_MAX_CHARS,
            )
        return base_context

    def _proactive_scheduler_candidate_context(self, candidate: dict[str, Any]) -> str:
        parts = [
            "后台主动聊天调度器正在判断是否应该主动开口。",
            "不要使用预设话题库；只能基于状态模型、近期上下文、双方需要、关系修复或轻松调皮信号决定。",
        ]
        last_user_text = str(candidate.get("last_user_text_excerpt") or "").strip()
        context_excerpt = str(candidate.get("candidate_context_excerpt") or "").strip()
        if last_user_text:
            parts.append(f"最近用户消息：{last_user_text}")
        window_summary = self._proactive_context_window_summary(
            str(candidate.get("session_key") or ""),
        )
        if window_summary:
            parts.append(window_summary)
        if context_excerpt:
            parts.append(f"最近请求上下文：{self._clip(context_excerpt, 1100)}")
        speaker_name = str(candidate.get("speaker_name") or "").strip()
        if speaker_name:
            parts.append(f"最近说话者：{speaker_name}")
        return self._clip("\n".join(parts), PROACTIVE_CONTEXT_SUMMARY_MAX_CHARS)

    def _record_proactive_context_turn(
        self,
        session_key: str,
        *,
        user_text: str,
        context_text: str,
        speaker_name: str,
        observed_at: float,
    ) -> None:
        if not isinstance(getattr(self, "_proactive_context_windows", None), dict):
            self._proactive_context_windows = {}
        key = str(session_key or "global")
        queue = self._proactive_context_windows.setdefault(
            key,
            deque(maxlen=PROACTIVE_CONTEXT_WINDOW_LIMIT),
        )
        if queue.maxlen != PROACTIVE_CONTEXT_WINDOW_LIMIT:
            queue = deque(queue, maxlen=PROACTIVE_CONTEXT_WINDOW_LIMIT)
            self._proactive_context_windows[key] = queue
        queue.append(
            {
                "observed_at": float(observed_at),
                "user_text": self._clip_one_line(user_text, 280),
                "context_text": self._clip(context_text, 700),
                "speaker_name": self._clip_one_line(speaker_name, 80),
            },
        )

    def _proactive_context_window_summary(self, session_key: str) -> str:
        window = (
            getattr(self, "_proactive_context_windows", {}).get(
                str(session_key or "global"),
            )
            or []
        )
        items = list(window)[-PROACTIVE_CONTEXT_WINDOW_LIMIT:]
        if not items:
            return ""
        lines = ["近期上下文摘要："]
        for index, item in enumerate(items, 1):
            speaker = str(item.get("speaker_name") or "").strip()
            prefix = f"{index}. "
            if speaker:
                prefix += f"{speaker}: "
            user_text = str(item.get("user_text") or "").strip()
            if user_text:
                lines.append(prefix + user_text)
        return self._clip("\n".join(lines), 1200)

    async def _sylanne_memory_recall_summary_for_proactive_candidate(
        self,
        candidate: dict[str, Any],
    ) -> str:
        if not self._sylanne_memory_enabled():
            return ""
        query = str(candidate.get("last_user_text_excerpt") or "").strip()
        session_key = str(candidate.get("session_key") or "")
        if not query:
            query = str(candidate.get("candidate_context_excerpt") or "").strip()
        if not query:
            return ""
        query = self._clip(
            query + "\n主动聊天需要参考：提醒方式、说话语气、相处偏好、关心进度、边界感。",
            900,
        )
        try:
            state = await self._load_sylanne_memory_state(session_key)
            items = recall_memory(
                state,
                query=query,
                now=self._observed_now(),
            )
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: Sylanne memory proactive recall failed: {exc}")
            return ""
        if not items:
            return ""
        items = self._filter_mature_sylanne_memory_recall_items(items)
        if not items:
            return ""
        await self._reinforce_sylanne_memory_recall_items(
            session_key,
            state,
            items,
            query=query,
        )
        lines = ["Sylanne 自有记忆召回摘要："]
        for index, item in enumerate(items[:3], 1):
            record = item.record
            snippet = record.summary or record.text
            lines.append(f"{index}. {self._clip_one_line(snippet, 180)}")
        return self._clip("\n".join(lines), PROACTIVE_MEMORY_RECALL_MAX_CHARS)

    async def _append_sylanne_memory_recall_context_if_any(
        self,
        request: ProviderRequest,
        session_key: str,
        *,
        current_user_text: str,
        budget: _StateInjectionBudget | None,
    ) -> bool:
        if not self._sylanne_memory_enabled():
            return False
        source = "sylanne_memory_recall"
        if self._request_has_temp_text_source(request, source):
            return False
        text = await self._sylanne_memory_recall_summary_for_request(
            request,
            session_key=session_key,
            current_user_text=current_user_text,
        )
        if not text:
            return False
        return self._append_temp_text_part(
            request,
            text,
            source=source,
            budget=budget,
        )

    async def _sylanne_memory_recall_summary_for_request(
        self,
        request: ProviderRequest,
        *,
        session_key: str,
        current_user_text: str,
    ) -> str:
        query = self._sylanne_memory_recall_query_for_request(
            request,
            current_user_text=current_user_text,
        )
        if not query:
            return ""
        try:
            state = await self._load_sylanne_memory_state(session_key)
            items = recall_memory(
                state,
                query=query,
                now=self._observed_now(),
            )
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: Sylanne memory request recall failed: {exc}")
            return ""
        items = self._filter_mature_sylanne_memory_recall_items(items)
        fragment = build_memory_prompt_fragment(
            items,
            session_key=session_key,
            max_chars=SYLANNE_MEMORY_RECALL_INJECTION_MAX_CHARS,
        )
        if fragment:
            await self._reinforce_sylanne_memory_recall_items(
                session_key,
                state,
                items,
                query=query,
            )
        return fragment

    def _filter_mature_sylanne_memory_recall_items(
        self,
        items: list[MemoryRecallItem],
    ) -> list[MemoryRecallItem]:
        if not items:
            return []
        now = self._observed_now()
        matured: list[MemoryRecallItem] = []
        for item in items:
            min_age = self._sylanne_memory_recall_maturation_seconds(item)
            if min_age <= 0:
                matured.append(item)
                continue
            try:
                age = now - float(item.record.updated_at)
            except (TypeError, ValueError):
                age = min_age
            if age >= min_age:
                matured.append(item)
        return matured

    async def _reinforce_sylanne_memory_recall_items(
        self,
        session_key: str,
        state: SylanneMemoryState,
        items: list[MemoryRecallItem],
        *,
        query: str,
    ) -> None:
        if not items:
            return
        try:
            reinforced = reinforce_recalled_memories(
                state,
                items,
                query=query,
                now=self._observed_now(),
            )
            await self._save_sylanne_memory_state(session_key, reinforced)
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: Sylanne memory reinforcement failed: {exc}")

    def _sylanne_memory_record_query_payload(
        self,
        item: MemoryRecallItem,
        *,
        now: float,
    ) -> dict[str, Any]:
        record = item.record
        age_seconds = max(0.0, float(now) - float(record.updated_at or record.created_at))
        payload: dict[str, Any] = {
            "memory_id": str(record.memory_id or ""),
            "summary": self._clip_one_line(record.summary or record.text, 220),
            "text_excerpt": self._clip_one_line(record.text, 260),
            "score": round(float(item.score), 6),
            "depth": round(float(record.depth), 6),
            "confidence": round(float(record.confidence), 6),
            "evidence_count": int(record.evidence_count),
            "recall_count": int(record.recall_count),
            "age_seconds": round(age_seconds, 3),
            "updated_at": float(record.updated_at),
            "reasons": list(item.reasons[:6]),
        }
        if record.layers:
            payload["layers"] = {
                str(key): round(float(value), 4)
                for key, value in list(record.layers.items())[:6]
            }
        if record.emotional_signature:
            payload["emotional_signature"] = {
                str(key): round(float(value), 4)
                for key, value in list(record.emotional_signature.items())[:8]
            }
        if record.associations:
            payload["association_count"] = len(record.associations)
            payload["top_associations"] = [
                {
                    "memory_id": str(memory_id),
                    "weight": round(float(weight), 4),
                }
                for memory_id, weight in sorted(
                    record.associations.items(),
                    key=lambda pair: float(pair[1] or 0.0),
                    reverse=True,
                )[:3]
            ]
        return payload

    def _format_sylanne_memory_query_for_user(self, payload: dict[str, Any]) -> str:
        if not payload.get("enabled", True):
            return "Sylanne 自有记忆未启用：enable_sylanne_memory=false。"
        if payload.get("warning"):
            return "Sylanne 自有记忆暂时无法读取，请稍后再试或检查日志。"
        query = self._clip_one_line(str(payload.get("query") or ""), 120)
        header = (
            "Sylanne 自有记忆查询（只读调试视图）\n"
            f"会话：{self._clip_one_line(str(payload.get('session_key') or ''), 80)}\n"
            f"关键词：{query or '未提供'}\n"
            f"命中：{int(payload.get('result_count') or 0)} / "
            f"{int(payload.get('total_records') or 0)}"
        )
        results = payload.get("results") or []
        if not results:
            return (
                header
                + "\n没有查到相关记忆。可以先正常聊几轮，等稳定事件写入后再查。"
            )
        lines = [header]
        for index, item in enumerate(results[:5], 1):
            lines.append(
                f"{index}. {item.get('summary') or item.get('text_excerpt') or ''}\n"
                f"   score={float(item.get('score') or 0.0):.2f}, "
                f"depth={float(item.get('depth') or 0.0):.2f}, "
                f"confidence={float(item.get('confidence') or 0.0):.2f}, "
                f"evidence={int(item.get('evidence_count') or 0)}, "
                f"recall={int(item.get('recall_count') or 0)}"
            )
        lines.append("提示：这个入口只读，不会因为查询本身强化或改写记忆。")
        return self._clip("\n".join(lines), 1800)

    def _sylanne_memory_recall_maturation_seconds(
        self,
        item: MemoryRecallItem,
    ) -> float:
        params = getattr(item.record, "auto_parameters", {}) or {}
        if isinstance(params, dict):
            raw = params.get("recall_maturation_seconds")
        else:
            raw = None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            dynamics = getattr(
                getattr(self, "_sylanne_memory_cache", {}).get(
                    getattr(item.record, "session_key", ""),
                ),
                "dynamics",
                None,
            )
            value = float(getattr(dynamics, "recall_maturation_seconds", 2.0))
        return max(0.0, min(20.0, value))

    def _sylanne_memory_recall_query_for_request(
        self,
        request: ProviderRequest,
        *,
        current_user_text: str,
    ) -> str:
        parts: list[str] = []
        user_text = str(current_user_text or "").strip()
        prompt_text = str(getattr(request, "prompt", "") or "").strip()
        if user_text:
            parts.append("当前用户消息：" + self._clip(user_text, 260))
        if prompt_text and prompt_text != user_text:
            parts.append("当前请求 prompt：" + self._clip(prompt_text, 260))
        context_lines: list[str] = []
        for item in self._tail_items(getattr(request, "contexts", []) or [], 5):
            text = self._clip_one_line(
                self._strip_sylanne_internal_context_blocks(
                    self._context_item_to_text(item),
                ),
                220,
            )
            if text:
                context_lines.append(text)
        if context_lines:
            parts.append("近期上下文：" + " / ".join(context_lines))
        extra_lines: list[str] = []
        for part in self._tail_items(
            getattr(request, "extra_user_content_parts", []) or [],
            4,
        ):
            text = self._strip_sylanne_internal_context_blocks(
                str(getattr(part, "text", "") or "").strip(),
            )
            if (
                not text
                or "sylanne_memory_recall" in text
            ):
                continue
            extra_lines.append(self._clip_one_line(text, 180))
        if extra_lines:
            parts.append("插件临时上下文：" + " / ".join(extra_lines))
        return self._clip("\n".join(parts).strip(), SYLANNE_MEMORY_RECALL_QUERY_MAX_CHARS)

    def _strip_sylanne_internal_context_blocks(self, text: str) -> str:
        value = str(text or "")
        if "sylanne_" not in value:
            return value.strip()
        internal_markers = (
            "[sylanne_memory_recall]",
            "[sylanne_realtime_assistant_history]",
            "[sylanne_realtime_active_dispatch]",
            "[sylanne_interrupted_reply_breakpoint]",
            "[sylanne_user_message_fragments]",
            "[sylanne_user_correction_context]",
        )
        for marker in internal_markers:
            value = value.replace(marker, "\n" + marker + "\n")
        lines = value.splitlines()
        kept: list[str] = []
        skipping = False
        for line in lines:
            stripped = line.strip()
            if any(stripped.startswith(marker) for marker in internal_markers):
                skipping = True
                continue
            if skipping and stripped.startswith("[") and stripped.endswith("]"):
                skipping = False
            if skipping:
                continue
            kept.append(line)
        return "\n".join(kept).strip()

    async def get_realtime_chat_plan(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        text: str = "",
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        include_sticker: bool = True,
    ) -> dict[str, Any]:
        """Public API: build QQ-like split message and sticker plan without sending."""
        resolved_session = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        emotion_task = asyncio.create_task(
            self.get_emotion_values(
                event_or_session,
                request=request,
                session_key=resolved_session,
            ),
        )
        group_task = asyncio.create_task(
            self.get_group_atmosphere_values(
                event_or_session,
                request=request,
                session_key=resolved_session,
            ),
        )
        lifelike_task = asyncio.create_task(
            self.get_lifelike_learning_snapshot(
                event_or_session,
                request=request,
                session_key=resolved_session,
                exposure="internal",
                include_prompt_fragment=False,
            ),
        )
        persona_task = asyncio.create_task(
            self._public_runtime_persona_profile(
                event_or_session,
                request=request,
                session_key=resolved_session,
            ),
        )
        sticker_candidates: list[dict[str, Any]] = []
        if include_sticker and self._sticker_reaction_enabled():
            sticker_candidates = await self._sticker_candidates(resolved_session)
        emotion_values, atmosphere_values, lifelike_snapshot, persona_profile = (
            await asyncio.gather(
                emotion_task,
                group_task,
                lifelike_task,
                persona_task,
            )
        )
        realtime_settings, realtime_adaptive = self._derive_realtime_chat_settings(
            persona_profile=persona_profile,
            emotion_values=emotion_values,
            atmosphere_values=atmosphere_values,
            lifelike_snapshot=lifelike_snapshot,
        )
        sticker_settings, sticker_adaptive = self._derive_sticker_settings(
            persona_profile=persona_profile,
            emotion_values=emotion_values,
            atmosphere_values=atmosphere_values,
            lifelike_snapshot=lifelike_snapshot,
        )
        plan = build_realtime_chat_plan(
            text,
            settings=realtime_settings,
            session_key=resolved_session,
            now=self._observed_now(),
            emotion_values=emotion_values,
            atmosphere_values=atmosphere_values,
            sticker_candidates=sticker_candidates,
            sticker_settings=sticker_settings,
        )
        plan["settings"] = {
            "max_parts": realtime_settings.max_parts,
            "min_part_chars": realtime_settings.min_part_chars,
            "max_part_chars": realtime_settings.max_part_chars,
            "strip_markdown": realtime_settings.strip_markdown,
        }
        plan["adaptive"] = {
            "realtime_chat": realtime_adaptive,
            "sticker": sticker_adaptive,
        }
        if not hasattr(self, "_last_realtime_chat_adaptive_settings"):
            self._last_realtime_chat_adaptive_settings = {}
        self._last_realtime_chat_adaptive_settings[resolved_session] = deepcopy(
            plan["adaptive"],
        )
        plan["dry_run_default"] = self._cfg_bool("realtime_chat_dry_run_default", False)
        plan["intercept_llm_response"] = self._cfg_bool(
            "realtime_chat_intercept_llm_response",
            True,
        )
        return plan

    async def request_realtime_chat_dispatch(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        text: str = "",
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        dry_run: bool | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Public API: split and optionally send one reply as sequential chat messages."""
        resolved_session = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        plan = await self.get_realtime_chat_plan(
            event_or_session,
            text=text,
            request=request,
            session_key=resolved_session,
        )
        plan["input_epoch"] = self._conversation_response_epoch(resolved_session)
        effective_dry_run = (
            self._cfg_bool("realtime_chat_dry_run_default", False)
            if dry_run is None
            else bool(dry_run)
        )
        blocked_reason = self._realtime_chat_blocked_reason(
            event_or_session,
            plan,
            dry_run=effective_dry_run,
            force=force,
        )
        if blocked_reason:
            return {
                "schema_version": "astrbot.realtime_chat_dispatch_result.v1",
                "kind": "realtime_chat_dispatch_result",
                "session_key": resolved_session,
                "plan": plan,
                "sent": False,
                "dry_run": effective_dry_run,
                "blocked_reason": blocked_reason,
            }
        send_result = await self._send_realtime_chat_plan(
            event_or_session,
            plan,
            source="public_api",
        )
        return {
            "schema_version": "astrbot.realtime_chat_dispatch_result.v1",
            "kind": "realtime_chat_dispatch_result",
            "session_key": resolved_session,
            "plan": plan,
            "sent": True,
            "dry_run": False,
            "blocked_reason": "",
            "send_result": send_result,
        }

    async def observe_user_message_withdrawal(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        message_id: str = "",
        reason: str = "withdrawn",
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        """Public API: mark a user recall/withdrawal so pending output stops."""
        recall = self._napcat_recall_payload(event_or_session)
        resolved_session = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not session_key and recall.get("group_id"):
            resolved_session = str(
                getattr(event_or_session, "unified_msg_origin", "") or resolved_session,
            )
        final_message_id = str(message_id or recall.get("message_id") or "")
        final_reason = str(
            recall.get("notice_type") if reason == "withdrawn" and recall else reason or "withdrawn",
        )
        epoch = self._bump_conversation_input_epoch(resolved_session)
        self._cancel_realtime_chat_dispatches_for_session(
            resolved_session,
            reason="user_message_withdrawal",
        )
        now = self._observed_now() if observed_at is None else float(observed_at)
        if isinstance(getattr(self, "_proactive_candidate_sessions", None), dict):
            candidate = self._proactive_candidate_sessions.get(resolved_session)
            if isinstance(candidate, dict):
                candidate["last_user_text_excerpt"] = ""
                candidate["candidate_context_excerpt"] = ""
                candidate["last_withdrawn_message_id"] = final_message_id
                candidate["last_withdrawn_at"] = now
                candidate["last_withdrawal_reason"] = final_reason
                if recall:
                    candidate["last_withdrawal_notice"] = recall
        if isinstance(getattr(self, "_last_request_text", None), dict):
            self._last_request_text.pop(resolved_session, None)
        return {
            "schema_version": "astrbot.user_message_withdrawal.v1",
            "kind": "user_message_withdrawal",
            "session_key": resolved_session,
            "message_id": final_message_id,
            "reason": final_reason,
            "notice": recall,
            "input_epoch": epoch,
            "observed_at": now,
            "stale_output_policy": "stop_pending_realtime_parts_and_drop_late_llm_response",
        }

    async def observe_sticker_usage(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        sticker: dict[str, Any] | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        source: str = "plugin",
        commit: bool = True,
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        """Public API: learn a user sticker as lightweight metadata, never as binary."""
        resolved_session = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._sticker_learning_enabled():
            return {
                "schema_version": "astrbot.sticker_memory_result.v1",
                "kind": "sticker_memory_result",
                "enabled": False,
                "session_key": resolved_session,
                "committed": False,
                "reason": "sticker_learning_disabled",
            }
        item = build_sticker_memory_item(
            dict(sticker or {}),
            session_key=resolved_session,
            now=observed_at if observed_at is not None else self._observed_now(),
            source=source,
        )
        current = await self._load_sticker_memory(resolved_session)
        updated = merge_sticker_memory(
            current,
            item,
            limit=max(1, self._cfg_int("sticker_learned_limit", 200)),
        )
        if commit:
            await self._save_sticker_memory(resolved_session, updated)
        return {
            "schema_version": "astrbot.sticker_memory_result.v1",
            "kind": "sticker_memory_result",
            "enabled": True,
            "session_key": resolved_session,
            "committed": bool(commit),
            "item": item,
            "memory_count": len(updated),
        }

    async def _judge_proactive_topic(
        self,
        event_or_session: AstrMessageEvent | str | None,
        *,
        decision: dict[str, Any],
        topics: list[dict[str, Any]],
        candidate_context: str,
        use_llm: bool,
    ) -> dict[str, Any]:
        fallback = local_proactive_topic_judgement(decision, topics)
        if not use_llm or not self._cfg_bool("use_llm_assessor", True):
            return fallback
        event = event_or_session if self._looks_like_event(event_or_session) else None
        if event is None:
            fallback["reason"] += " 未传入事件对象，无法调用当前会话 LLM。"
            return fallback
        provider_id = await self._provider_id(event)
        if not provider_id:
            fallback["reason"] += " 当前没有可用 Provider，使用本地回退。"
            return fallback
        prompt = build_proactive_topic_assessment_prompt(
            decision=decision,
            topic_candidates=topics,
            candidate_context=candidate_context,
            max_context_chars=self._cfg_int("max_context_chars", 1600),
        )
        token = _INTERNAL_LLM_CALL.set(True)
        try:
            llm_resp = await self._call_internal_assessor_llm(
                provider_id=provider_id,
                prompt=prompt,
                system_prompt=(
                    "你是插件内部的主动发言裁决器，只输出 JSON，不直接生成聊天回复。"
                ),
            )
        except asyncio.TimeoutError:
            fallback["reason"] += " 主动发言话题 LLM 裁决超时，使用本地回退。"
            return fallback
        except Exception as exc:
            fallback["reason"] += f" 主动发言话题 LLM 裁决失败，使用本地回退: {exc}"
            return fallback
        finally:
            _INTERNAL_LLM_CALL.reset(token)
        judgement = self._parse_proactive_topic_judgement(
            getattr(llm_resp, "completion_text", ""),
        )
        if judgement is None:
            fallback["reason"] += " 主动发言话题 LLM 输出不可解析，使用本地回退。"
            return fallback
        if decision.get("action") == "stay_silent":
            judgement["should_speak"] = False
            judgement["need_mode"] = "silence"
            judgement["opening_style"] = "stay_silent"
        return judgement

    def _parse_proactive_topic_judgement(self, text: str) -> dict[str, Any] | None:
        raw = str(text or "").strip()
        if not raw:
            return None
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
        return normalize_proactive_topic_judgement(data)

    def _build_proactive_dispatch_request(
        self,
        decision: dict[str, Any],
        *,
        event_or_session: AstrMessageEvent | str | None,
        session_key: str,
        candidate_context: str,
        override_text: str = "",
    ) -> dict[str, Any]:
        judgement = decision.get("topic_judgement")
        if not isinstance(judgement, dict):
            judgement = {}
        topic = decision.get("selected_topic")
        if not isinstance(topic, dict):
            topic = {}
        adaptive_policy = self._derive_proactive_dispatch_policy(decision)
        message_text = self._compose_proactive_message_text(
            judgement,
            selected_topic=topic,
            override_text=override_text,
            max_chars=int(adaptive_policy["max_chars"]),
        )
        topic_evidence = str(
            judgement.get("topic_evidence")
            or topic.get("reason")
            or decision.get("reason")
            or "",
        ).strip()
        origin = self._proactive_unified_msg_origin(event_or_session)
        request_payload = {
            "schema_version": "astrbot.proactive_dispatch_request.v1",
            "kind": "proactive_dispatch_request",
            "requested": bool(decision.get("should_speak"))
            and bool(judgement.get("should_speak", True))
            and str(judgement.get("need_mode") or "") != "silence",
            "session_key": session_key,
            "unified_msg_origin": origin,
            "action": str(decision.get("action") or ""),
            "need_mode": str(judgement.get("need_mode") or ""),
            "opening_style": str(judgement.get("opening_style") or ""),
            "speech_intent": str(judgement.get("speech_intent") or "")[:200],
            "topic_text": str(judgement.get("topic_text") or topic.get("topic") or "")[:160],
            "topic_evidence": topic_evidence[:240],
            "reason": str(judgement.get("reason") or decision.get("reason") or "")[:240],
            "message_text": message_text,
            "max_chars": int(adaptive_policy["max_chars"]),
            "ttl_seconds": int(adaptive_policy["ttl_seconds"]),
            "cooldown_seconds": float(adaptive_policy["cooldown_seconds"]),
            "feedback_window_seconds": float(adaptive_policy["feedback_window_seconds"]),
            "adaptive_policy": adaptive_policy,
            "idempotency_key": self._proactive_dispatch_idempotency_key(
                session_key=session_key,
                decision=decision,
                message_text=message_text,
            ),
            "requires_generation": False,
            "context_excerpt": self._clip(str(candidate_context or ""), 160),
            "sent": False,
            "blocked_reason": "",
        }
        if not request_payload["message_text"]:
            request_payload["requested"] = False
            request_payload["blocked_reason"] = "empty_message"
        return request_payload

    def _compose_proactive_message_text(
        self,
        judgement: dict[str, Any],
        *,
        selected_topic: dict[str, Any],
        override_text: str = "",
        max_chars: int | None = None,
    ) -> str:
        max_chars = max(1, int(max_chars or 160))
        raw = str(override_text or judgement.get("draft_message") or "").strip()
        if not raw:
            need_mode = str(judgement.get("need_mode") or "")
            topic = str(judgement.get("topic_text") or selected_topic.get("topic") or "").strip()
            raw = self._fallback_proactive_message(need_mode, topic)
        return self._clip_one_line(raw, max_chars)

    def _derive_proactive_dispatch_policy(
        self,
        decision: dict[str, Any],
    ) -> dict[str, Any]:
        if self._runtime_parameter_debug_override_enabled():
            return {
                "source": "debug_config_override",
                "debug_override_used": True,
                "max_chars": max(
                    1,
                    self._debug_cfg_int("proactive_speech_max_chars", 160),
                ),
                "ttl_seconds": max(
                    1,
                    self._debug_cfg_int("proactive_speech_dispatch_ttl_seconds", 120),
                ),
                "cooldown_seconds": max(
                    0.0,
                    self._debug_cfg_float(
                        "proactive_speech_dispatch_cooldown_seconds",
                        1800.0,
                    ),
                ),
                "feedback_window_seconds": 1800.0,
            }
        signals = decision.get("signals") if isinstance(decision.get("signals"), dict) else {}
        score = self._clamp01(decision.get("score", 0.0))
        boundary = self._clamp01(signals.get("boundary", 0.0))
        overload = self._clamp01(signals.get("overload", 0.0))
        repair_need = self._clamp01(signals.get("repair_need", 0.0))
        companionship = self._clamp01(signals.get("companionship_need", 0.0))
        user_need = self._clamp01(signals.get("user_need_to_be_met", 0.0))
        bot_need = self._clamp01(signals.get("bot_need_to_express", 0.0))
        urgency = self._clamp01(
            0.20
            + 0.46 * score
            + 0.20 * repair_need
            + 0.16 * user_need
            + 0.12 * bot_need
            + 0.10 * companionship
            - 0.22 * boundary
            - 0.20 * overload,
        )
        restraint = self._clamp01(
            0.18
            + 0.38 * boundary
            + 0.34 * overload
            + 0.16 * (1.0 - score)
            - 0.12 * repair_need,
        )
        max_chars = int(round(92 + 104 * urgency - 42 * restraint))
        max_chars = max(64, min(240, max_chars))
        ttl_seconds = int(round(70 + 240 * restraint + 180 * (1.0 - urgency)))
        ttl_seconds = max(60, min(600, ttl_seconds))
        cooldown_seconds = round(
            520
            + 3600 * restraint
            + 1250 * (1.0 - urgency)
            - 820 * repair_need,
            3,
        )
        cooldown_seconds = max(240.0, min(7200.0, cooldown_seconds))
        feedback_window_seconds = round(
            max(600.0, min(7200.0, 0.60 * cooldown_seconds + 900 * restraint)),
            3,
        )
        return {
            "source": "state_formula",
            "debug_override_used": False,
            "max_chars": max_chars,
            "ttl_seconds": ttl_seconds,
            "cooldown_seconds": cooldown_seconds,
            "feedback_window_seconds": feedback_window_seconds,
            "urgency": round(urgency, 6),
            "restraint": round(restraint, 6),
            "signals": {
                "score": round(score, 6),
                "boundary": round(boundary, 6),
                "overload": round(overload, 6),
                "repair_need": round(repair_need, 6),
                "companionship_need": round(companionship, 6),
                "user_need_to_be_met": round(user_need, 6),
                "bot_need_to_express": round(bot_need, 6),
            },
        }

    def _fallback_proactive_message(self, need_mode: str, topic: str) -> str:
        topic = str(topic or "").strip()
        if need_mode == "progress_check":
            if topic:
                return f"那、那个……你之前提到的{topic}，现在进度还顺吗？"
            return "那、那个……你之前那件事，现在进度还顺吗？"
        if need_mode == "missing_user":
            return "那、那个……我只是路过确认一下，你今天还好吗？"
        if need_mode == "playful_ping":
            return "咦，我、我来轻轻敲一下门。你现在方便被打扰一下吗？"
        if need_mode == "prank_light":
            return "等、等等，我发现一件重要小事：你是不是又在偷偷忙到忘记休息了？"
        if need_mode == "repair":
            return "那、那个……刚才如果我哪里说重了，我想先轻轻澄清一下。"
        if need_mode == "user_need":
            return "那、那个……你现在需要我陪你把这件事顺一下吗？"
        if need_mode == "bot_need":
            return "我、我也想参与一点点，可以吗？"
        if need_mode == "mutual_need":
            return "那、那个……我想确认一下，我们现在这样互相需要的节奏还舒服吗？"
        if need_mode == "clarify":
            return "我有点不确定，能不能轻轻确认一句？"
        if need_mode == "listen":
            return "我在。你要是想继续说，我会听。"
        return ""

    def _proactive_dispatch_blocked_reason(
        self,
        decision: dict[str, Any],
        dispatch: dict[str, Any],
        *,
        event_or_session: AstrMessageEvent | str | None,
        dry_run: bool,
        force: bool,
    ) -> str:
        if dry_run:
            return "dry_run"
        if not dispatch.get("requested"):
            return str(dispatch.get("blocked_reason") or "decision_declined")
        if not force and not self._cfg_bool("enable_proactive_speech_dispatch", False):
            return "dispatch_disabled"
        if not self._looks_like_event(event_or_session):
            return "missing_event_origin"
        if not dispatch.get("unified_msg_origin"):
            return "missing_unified_msg_origin"
        if not str(dispatch.get("message_text") or "").strip():
            return "empty_message"
        if self._proactive_dispatch_on_cooldown(
            str(dispatch.get("session_key") or ""),
            cooldown_seconds=self._as_float_value(
                dispatch.get("cooldown_seconds"),
                1800.0,
            ),
        ):
            return "cooldown_active"
        if not hasattr(getattr(self, "context", None), "send_message"):
            return "missing_send_message_api"
        if decision.get("action") == "stay_silent":
            return "decision_silence"
        return ""

    def _proactive_dispatch_on_cooldown(
        self,
        session_key: str,
        *,
        cooldown_seconds: float | None = None,
    ) -> bool:
        cooldown = max(0.0, self._as_float_value(cooldown_seconds, 1800.0))
        if cooldown <= 0:
            return False
        last_sent = self._proactive_last_sent_cache().get(session_key)
        if last_sent is None:
            return False
        return self._observed_now() - float(last_sent) < cooldown

    def _proactive_last_sent_cache(self) -> dict[str, float]:
        cache = getattr(self, "_proactive_dispatch_last_sent", None)
        if cache is None:
            cache = {}
            self._proactive_dispatch_last_sent = cache
        return cache

    def _record_proactive_dispatch_audit(self, session_key: str, dispatch: dict[str, Any]) -> None:
        audit = getattr(self, "_proactive_dispatch_audit", None)
        if audit is None:
            audit = {}
            self._proactive_dispatch_audit = audit
        entries = audit.setdefault(session_key, deque(maxlen=24))
        entries.append(
            {
                "schema_version": "astrbot.proactive_dispatch_audit.v1",
                "recorded_at": self._observed_now(),
                "idempotency_key": dispatch.get("idempotency_key"),
                "requested": bool(dispatch.get("requested")),
                "sent": bool(dispatch.get("sent")),
                "sent_at": dispatch.get("sent_at"),
                "blocked_reason": dispatch.get("blocked_reason", ""),
                "need_mode": dispatch.get("need_mode", ""),
                "topic_text": dispatch.get("topic_text", ""),
                "topic_evidence": dispatch.get("topic_evidence", ""),
                "feedback_status": (
                    "pending" if dispatch.get("sent") else "not_sent"
                ),
                "feedback_window_seconds": self._as_float_value(
                    dispatch.get("feedback_window_seconds"),
                    1800.0,
                ),
            },
        )

    async def _observe_proactive_dispatch_feedback(
        self,
        session_key: str,
        user_text: str,
        *,
        observed_at: float | None = None,
    ) -> None:
        audit = getattr(self, "_proactive_dispatch_audit", None)
        if not isinstance(audit, dict):
            return
        entries = audit.get(session_key)
        if not entries:
            return
        now = self._observed_now() if observed_at is None else float(observed_at)
        text_profile = self._low_signal_text_profile(user_text)
        for entry in reversed(entries):
            if entry.get("feedback_status") not in {"pending", "", None}:
                continue
            if not entry.get("sent"):
                continue
            sent_at = self._as_float_value(entry.get("sent_at"), 0.0)
            window = max(
                60.0,
                self._as_float_value(entry.get("feedback_window_seconds"), 1800.0),
            )
            elapsed = max(0.0, now - sent_at) if sent_at > 0 else 0.0
            if sent_at > 0 and elapsed > window:
                entry["feedback_status"] = "unanswered"
                entry["feedback_observed_at"] = now
                entry["feedback_elapsed_seconds"] = round(elapsed, 6)
                await self.observe_lifelike_text(
                    session_key=session_key,
                    text=(
                        "主动发言没有被及时回应；以后更谨慎地判断开口时机，"
                        "降低打扰感，优先等待用户自然接话。"
                    ),
                    source="proactive_feedback",
                    commit=True,
                    observed_at=now,
                )
                return
            status = "cold_reply" if text_profile.get("is_low_signal") else "received_reply"
            entry["feedback_status"] = status
            entry["feedback_signal_kind"] = text_profile.get("kind")
            entry["feedback_observed_at"] = now
            entry["feedback_elapsed_seconds"] = round(elapsed, 6)
            if status == "cold_reply":
                await self.observe_lifelike_text(
                    session_key=session_key,
                    text=(
                        "主动发言后只收到低信号回应，可能造成冷场；以后更谨慎，"
                        "减少调皮打扰，优先选择有明确证据的话题。"
                    ),
                    source="proactive_feedback",
                    commit=True,
                    observed_at=now,
                )
            else:
                await self.observe_lifelike_text(
                    session_key=session_key,
                    text="主动发言被用户接住，可轻微增加共同语境和被需要感。",
                    source="proactive_feedback",
                    commit=True,
                    observed_at=now,
                )
            return

    async def _send_proactive_message(
        self,
        event_or_session: AstrMessageEvent | str | None,
        text: str,
    ) -> dict[str, Any]:
        origin = self._proactive_unified_msg_origin(event_or_session)
        if not origin:
            raise RuntimeError("missing unified_msg_origin")
        send_message = getattr(getattr(self, "context", None), "send_message", None)
        if not callable(send_message):
            raise RuntimeError("context.send_message is not available")
        message = self._build_astrbot_message_chain(text)
        result = await send_message(origin, message)
        return {
            "api": "context.send_message",
            "unified_msg_origin": origin,
            "message_type": type(message).__name__,
            "result": self._bounded_scalar_or_summary(result),
        }

    async def _send_realtime_chat_plan(
        self,
        event_or_session: AstrMessageEvent | str | None,
        plan: dict[str, Any],
        *,
        source: str,
        record_history_shadow: bool = False,
    ) -> dict[str, Any]:
        origin = self._proactive_unified_msg_origin(event_or_session)
        if not origin:
            raise RuntimeError("missing unified_msg_origin")
        send_message = getattr(getattr(self, "context", None), "send_message", None)
        if not callable(send_message):
            raise RuntimeError("context.send_message is not available")
        parts = self._normalize_realtime_dispatch_parts(plan)
        results: list[dict[str, Any]] = []
        session_key = str(plan.get("session_key") or self._resolve_public_session_key(event_or_session))
        input_epoch = self._optional_int(plan.get("input_epoch"))
        interrupted_reason = ""
        full_text = str(plan.get("full_text") or "").strip()
        if not full_text:
            full_text = " ".join(
                str(part.get("text") or "").strip()
                for part in parts
                if str(part.get("text") or "").strip()
            )
        self._start_realtime_chat_active_dispatch(
            session_key,
            input_epoch=input_epoch,
            full_text=full_text,
            source=source,
        )
        current_task = asyncio.current_task()
        if current_task is not None:
            self._register_realtime_chat_dispatch_task(session_key, current_task)
        try:
            for part in parts:
                if self._conversation_reply_is_stale(session_key, input_epoch):
                    interrupted_reason = "user_interrupted"
                    break
                delay = max(0.0, self._as_float_value(part.get("delay_before_seconds"), 0.0))
                if delay > 0:
                    await asyncio.sleep(delay)
                if self._conversation_reply_is_stale(session_key, input_epoch):
                    interrupted_reason = "user_interrupted"
                    break
                text = str(part.get("text") or "").strip()
                if not text:
                    continue
                message = self._build_astrbot_message_chain(text)
                result = await send_message(origin, message)
                self._append_realtime_chat_active_dispatch_part(session_key, text)
                results.append(
                    {
                        "index": part.get("index"),
                        "text_chars": len(text),
                        "message_type": type(message).__name__,
                        "result": self._bounded_scalar_or_summary(result),
                    },
                )
                await asyncio.sleep(REALTIME_CHAT_INTERRUPT_GRACE_SECONDS)
                if self._conversation_reply_is_stale(session_key, input_epoch):
                    interrupted_reason = "user_interrupted"
                    break
        except asyncio.CancelledError:
            if self._conversation_reply_is_stale(session_key, input_epoch):
                interrupted_reason = "user_interrupted"
            else:
                raise
        finally:
            if current_task is not None:
                self._unregister_realtime_chat_dispatch_task(session_key, current_task)
            if not interrupted_reason:
                self._finish_realtime_chat_active_dispatch(session_key)
        if record_history_shadow and results and not interrupted_reason:
            self._record_realtime_assistant_history_shadow(
                session_key,
                full_text=full_text,
                input_epoch=input_epoch,
                message_parts=parts,
                source=source,
            )
        media_results: list[dict[str, Any]] = []
        if not interrupted_reason and not self._conversation_reply_is_stale(
            session_key,
            input_epoch,
        ):
            for media_part in self._normalize_realtime_media_parts(
                plan.get("media_parts"),
            ):
                if self._conversation_reply_is_stale(session_key, input_epoch):
                    interrupted_reason = "user_interrupted"
                    break
                media_message = self._build_astrbot_media_message(media_part)
                if media_message is None:
                    media_results.append(
                        {
                            "index": media_part.get("index"),
                            "sent": False,
                            "blocked_reason": "unsupported_media_part",
                        },
                    )
                    continue
                raw_media_result = await send_message(origin, media_message)
                media_results.append(
                    {
                        "index": media_part.get("index"),
                        "sent": True,
                        "media_kind": media_part.get("kind"),
                        "message_type": type(media_message).__name__,
                        "result": self._bounded_scalar_or_summary(raw_media_result),
                    },
                )
        sticker_result = None
        sticker = plan.get("sticker") if isinstance(plan.get("sticker"), dict) else {}
        if sticker.get("should_send") and not self._conversation_reply_is_stale(
            session_key,
            input_epoch,
        ):
            candidate = sticker.get("candidate")
            if isinstance(candidate, dict):
                judgement = await self._judge_sticker_consistency(
                    event_or_session,
                    plan=plan,
                    sticker=sticker,
                    candidate=candidate,
                )
                if judgement.get("approved"):
                    sticker_message = self._build_astrbot_sticker_message(candidate)
                    raw_sticker_result = await send_message(origin, sticker_message)
                    sticker_result = {
                        "sent": True,
                        "judgement": judgement,
                        "result": self._bounded_scalar_or_summary(raw_sticker_result),
                    }
                else:
                    sticker_result = {
                        "sent": False,
                        "blocked_reason": "llm_rejected",
                        "judgement": judgement,
                    }
        if interrupted_reason:
            self._record_interrupted_reply_breakpoint(
                session_key,
                reason=interrupted_reason,
                input_epoch=input_epoch,
                sent_parts=[str(item.get("text") or "") for item in parts[: len(results)]],
                unsent_parts=[
                    str(item.get("text") or "")
                    for item in parts[len(results) :]
                    if str(item.get("text") or "").strip()
                ],
                message_parts=parts,
                source=source,
            )
            self._finish_realtime_chat_active_dispatch(session_key)
        self._realtime_chat_last_sent_cache()[session_key] = self._observed_now()
        payload = {
            "api": "context.send_message",
            "source": source,
            "unified_msg_origin": origin,
            "message_count": len(results),
            "results": results,
            "media_count": len([item for item in media_results if item.get("sent")]),
            "media_results": media_results,
            "sticker_result": self._bounded_scalar_or_summary(sticker_result),
        }
        if interrupted_reason:
            payload["interrupted_reason"] = interrupted_reason
        return payload

    async def _judge_sticker_consistency(
        self,
        event_or_session: AstrMessageEvent | str | None,
        *,
        plan: dict[str, Any],
        sticker: dict[str, Any],
        candidate: dict[str, Any],
    ) -> dict[str, Any]:
        local = self._local_sticker_consistency_judgement(
            plan=plan,
            sticker=sticker,
            candidate=candidate,
        )
        if not self._cfg_bool("sticker_llm_consistency_check_enabled", True):
            return local
        event = event_or_session if self._looks_like_event(event_or_session) else None
        if event is None or not self._cfg_bool("use_llm_assessor", True):
            return local
        provider_id = await self._provider_id(event)
        if not provider_id:
            return local
        prompt = self._build_sticker_consistency_prompt(
            plan=plan,
            sticker=sticker,
            candidate=candidate,
        )
        token = _INTERNAL_LLM_CALL.set(True)
        try:
            llm_resp = await self._call_internal_assessor_llm(
                provider_id=provider_id,
                prompt=prompt,
                system_prompt="你是插件内部表情包一致性检查器，只输出 JSON。",
            )
        except Exception as exc:
            local["reason"] += f"; llm_check_failed={str(exc)[:80]}"
            return local
        finally:
            _INTERNAL_LLM_CALL.reset(token)
        parsed = self._parse_sticker_consistency_judgement(
            getattr(llm_resp, "completion_text", ""),
        )
        return parsed or local

    def _local_sticker_consistency_judgement(
        self,
        *,
        plan: dict[str, Any],
        sticker: dict[str, Any],
        candidate: dict[str, Any],
    ) -> dict[str, Any]:
        intent = str(sticker.get("intent") or "").lower()
        text = " ".join(
            str(part.get("text") or "")
            for part in list(plan.get("message_parts") or [])[:4]
            if isinstance(part, dict)
        ).lower()
        descriptor = " ".join(
            str(candidate.get(key) or "")
            for key in ("name", "relative_path", "path", "url")
        ).lower()
        tags = " ".join(str(tag).lower() for tag in candidate.get("tags") or [])
        evidence = descriptor + " " + tags
        negative = {"angry", "怒", "生气", "骂", "嫌弃", "阴阳", "刀", "哭"}
        celebratory = {"celebrate", "好耶", "赢", "开心", "happy"}
        comfort = {"comfort", "抱抱", "摸摸", "安慰", "哭", "泪"}
        conflict = False
        if intent in {"comfort", "apology"} and any(word in evidence for word in negative):
            conflict = True
        if intent == "celebrate" and any(word in evidence for word in negative):
            conflict = True
        if "对不起" in text and any(word in evidence for word in celebratory):
            conflict = True
        if intent == "comfort" and any(word in evidence for word in comfort):
            conflict = False
        return {
            "approved": not conflict,
            "source": "local_consistency_gate",
            "reason": (
                "candidate tags match inferred intent"
                if not conflict
                else "candidate tags may conflict with reply mood"
            ),
            "intent": intent,
        }

    def _build_sticker_consistency_prompt(
        self,
        *,
        plan: dict[str, Any],
        sticker: dict[str, Any],
        candidate: dict[str, Any],
    ) -> str:
        message_text = "\n".join(
            str(part.get("text") or "")
            for part in list(plan.get("message_parts") or [])[:4]
            if isinstance(part, dict)
        )
        candidate_summary = {
            key: candidate.get(key)
            for key in ("name", "relative_path", "origin", "tags", "extension")
            if key in candidate
        }
        return (
            "请判断候选表情包是否与本轮回复语气一致。只看标签、文件名和意图，不需要图片二进制。\n"
            "如果可能造成反讽、误伤、冒犯、与安慰/道歉/关心意图冲突，approved=false。\n"
            "输出 JSON: {\"approved\": true|false, \"reason\": \"短理由\"}\n"
            f"回复文本: {self._clip(message_text, 500)}\n"
            f"表情意图: {json.dumps(sticker, ensure_ascii=False)[:600]}\n"
            f"候选表情: {json.dumps(candidate_summary, ensure_ascii=False)}"
        )

    def _parse_sticker_consistency_judgement(self, text: str) -> dict[str, Any] | None:
        raw = str(text or "").strip()
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
        approved_raw = data.get("approved")
        if isinstance(approved_raw, bool):
            approved = approved_raw
        elif isinstance(approved_raw, str):
            normalized = approved_raw.strip().lower()
            if normalized in {"true", "yes", "1", "approved", "通过"}:
                approved = True
            elif normalized in {"false", "no", "0", "rejected", "拒绝", "不通过"}:
                approved = False
            else:
                return None
        elif isinstance(approved_raw, (int, float)):
            approved = bool(approved_raw)
        else:
            return None
        return {
            "approved": approved,
            "source": "llm_consistency_gate",
            "reason": str(data.get("reason") or "")[:240],
        }

    def _build_astrbot_message_chain(self, text: str) -> Any:
        try:
            from astrbot.api.event import MessageChain  # type: ignore

            chain = MessageChain()
            if hasattr(chain, "message") and callable(chain.message):
                return chain.message(str(text))
        except Exception:
            pass
        return str(text)

    def _extract_realtime_response_media_parts(
        self,
        response: LLMResponse,
    ) -> list[dict[str, Any]]:
        raw_items: list[Any] = []
        for attr in (
            "result_chain",
            "message_chain",
            "chain",
            "messages",
            "message",
            "content",
        ):
            value = getattr(response, attr, None)
            if value is None or isinstance(value, str):
                continue
            raw_items.extend(self._iter_message_like_parts(value))

        media_parts: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in raw_items:
            media = self._realtime_media_part_from_message_part(item)
            if not media:
                continue
            key = (str(media.get("kind") or ""), str(media.get("value") or ""))
            if key in seen:
                continue
            seen.add(key)
            media["index"] = len(media_parts)
            media_parts.append(media)
        return media_parts[:8]

    def _iter_message_like_parts(self, value: Any) -> list[Any]:
        if value is None or isinstance(value, (str, bytes)):
            return []
        if isinstance(value, dict):
            nested = value.get("parts") or value.get("messages") or value.get("message")
            if isinstance(nested, (list, tuple)):
                return list(nested)
            return [value]
        if isinstance(value, (list, tuple)):
            items: list[Any] = []
            for item in value:
                items.extend(self._iter_message_like_parts(item))
            return items
        parts = getattr(value, "parts", None)
        if isinstance(parts, (list, tuple)):
            return list(parts)
        chain = getattr(value, "chain", None)
        if isinstance(chain, (list, tuple)):
            return list(chain)
        return [value]

    def _realtime_media_part_from_message_part(self, item: Any) -> dict[str, Any] | None:
        kind = ""
        value: Any = None
        name = ""
        if isinstance(item, tuple) and len(item) >= 2:
            kind = str(item[0] or "")
            value = item[1]
        elif isinstance(item, dict):
            kind = str(
                item.get("type")
                or item.get("kind")
                or item.get("message_type")
                or "",
            )
            value = (
                item.get("path")
                or item.get("file")
                or item.get("file_path")
                or item.get("url")
                or item.get("value")
                or item.get("file_id")
                or item.get("id")
            )
            name = str(item.get("name") or item.get("filename") or "")
        else:
            kind = str(
                getattr(item, "type", "")
                or getattr(item, "kind", "")
                or getattr(item, "message_type", "")
                or item.__class__.__name__
            )
            value = (
                getattr(item, "path", None)
                or getattr(item, "file", None)
                or getattr(item, "file_path", None)
                or getattr(item, "url", None)
                or getattr(item, "value", None)
                or getattr(item, "file_id", None)
                or getattr(item, "id", None)
            )
            name = str(getattr(item, "name", "") or getattr(item, "filename", ""))
        lowered = kind.lower()
        if not any(marker in lowered for marker in ("image", "sticker", "face", "emoji")):
            return None
        value_text = str(value or "").strip()
        if not value_text:
            return None
        value_lower = value_text.lower()
        if value_lower.startswith(("http://", "https://")):
            normalized_kind = "url_image"
        elif "file_image" in lowered or "filesystem" in lowered or "file" in lowered:
            normalized_kind = "file_image"
        elif "url" in lowered:
            normalized_kind = "url_image"
        else:
            normalized_kind = "image"
        return {
            "kind": normalized_kind,
            "source_kind": kind,
            "value": value_text,
            "name": name,
        }

    def _normalize_realtime_media_parts(self, media_parts: Any) -> list[dict[str, Any]]:
        if not isinstance(media_parts, (list, tuple)):
            return []
        normalized: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in media_parts:
            if isinstance(item, dict):
                media = dict(item)
            else:
                media = self._realtime_media_part_from_message_part(item) or {}
            kind = str(media.get("kind") or "").strip()
            value = str(media.get("value") or media.get("path") or media.get("url") or "").strip()
            if not kind or not value:
                continue
            key = (kind, value)
            if key in seen:
                continue
            seen.add(key)
            media["kind"] = kind
            media["value"] = value
            media["index"] = len(normalized)
            normalized.append(media)
        return normalized[:8]

    def _build_astrbot_media_message(self, media_part: dict[str, Any]) -> Any | None:
        kind = str(media_part.get("kind") or "").lower()
        value = str(media_part.get("value") or "").strip()
        if not value:
            return None
        if kind == "url_image":
            url_message = self._build_astrbot_url_image_message(value)
            if url_message is not None:
                return url_message
        try:
            from astrbot.api.event import MessageChain  # type: ignore

            chain = MessageChain()
            value_lower = value.lower()
            if kind == "url_image" or value_lower.startswith(("http://", "https://")):
                method_names = ("url_image", "image")
            elif kind == "file_image":
                method_names = ("file_image", "image")
            else:
                method_names = ("image", "file_image", "url_image")
            for method_name in method_names:
                method = getattr(chain, method_name, None)
                if callable(method):
                    return method(value)
        except Exception:
            return None
        return None

    def _append_astrbot_component_to_chain(self, chain: Any, component: Any) -> Any | None:
        for method_name in ("append", "add", "add_component"):
            method = getattr(chain, method_name, None)
            if callable(method):
                try:
                    result = method(component)
                    return result if result is not None else chain
                except Exception:
                    continue
        parts = getattr(chain, "parts", None)
        if isinstance(parts, list):
            parts.append(component)
            return chain
        chain_items = getattr(chain, "chain", None)
        if isinstance(chain_items, list):
            chain_items.append(component)
            return chain
        return None

    def _build_astrbot_url_image_message(self, url: str) -> Any | None:
        value = str(url or "").strip()
        if not value:
            return None
        try:
            from astrbot.api.event import MessageChain  # type: ignore

            chain = MessageChain()
            try:
                from astrbot.api import message_components as Comp  # type: ignore
            except Exception:
                Comp = None
            image_factory = getattr(Comp, "Image", None) if Comp is not None else None
            from_url = getattr(image_factory, "fromURL", None)
            if callable(from_url):
                component = from_url(value)
                built = self._append_astrbot_component_to_chain(chain, component)
                if built is not None:
                    return built
                return [component]
        except Exception:
            return None
        return None

    def _build_astrbot_sticker_message(self, candidate: dict[str, Any]) -> Any:
        path = str(candidate.get("path") or "")
        url = str(candidate.get("url") or "")
        fallback = str(candidate.get("name") or candidate.get("relative_path") or "表情包")
        try:
            from astrbot.api.event import MessageChain  # type: ignore

            chain = MessageChain()
            if url and not path:
                url_message = self._build_astrbot_url_image_message(url)
                if url_message is not None:
                    return url_message
            for method_name, value in (
                ("file_image", path),
                ("image", path or url),
                ("url_image", url),
            ):
                method = getattr(chain, method_name, None)
                if callable(method) and value:
                    return method(value)
            if hasattr(chain, "message") and callable(chain.message):
                return chain.message(f"[表情包] {fallback}")
        except Exception:
            pass
        return f"[表情包] {fallback}"

    def _realtime_chat_blocked_reason(
        self,
        event_or_session: AstrMessageEvent | str | None,
        plan: dict[str, Any],
        *,
        dry_run: bool,
        force: bool,
    ) -> str:
        if dry_run:
            return "dry_run"
        if not self._realtime_chat_enabled() and not force:
            return "realtime_chat_disabled"
        if not self._looks_like_event(event_or_session):
            return "missing_event_origin"
        if not self._proactive_unified_msg_origin(event_or_session):
            return "missing_unified_msg_origin"
        if not plan.get("message_parts"):
            return "empty_message"
        session_key = str(plan.get("session_key") or self._resolve_public_session_key(event_or_session))
        if not force and self._realtime_chat_on_cooldown(session_key):
            return "cooldown_active"
        if not hasattr(getattr(self, "context", None), "send_message"):
            return "missing_send_message_api"
        return ""

    def _normalize_realtime_dispatch_parts(
        self,
        plan: dict[str, Any],
    ) -> list[dict[str, Any]]:
        raw_parts = [
            dict(part)
            for part in list(plan.get("message_parts") or [])
            if isinstance(part, dict) and str(part.get("text") or "").strip()
        ]
        settings_data = plan.get("settings") if isinstance(plan.get("settings"), dict) else {}
        max_chars = max(
            12,
            min(96, self._optional_int(settings_data.get("max_part_chars")) or 72),
        )
        min_chars = max(
            1,
            min(max_chars, self._optional_int(settings_data.get("min_part_chars")) or 3),
        )
        normalized: list[dict[str, Any]] = []
        for part in raw_parts:
            text = str(part.get("text") or "").strip()
            if not text:
                continue
            fragments = self._force_realtime_text_fragments(
                text,
                max_chars=max_chars,
                min_chars=min_chars,
            )
            for fragment in fragments:
                next_part = dict(part)
                next_part["text"] = fragment
                normalized.append(next_part)
        for index, part in enumerate(normalized):
            part["index"] = index
        plan["message_parts"] = normalized
        plan["message_count"] = len(normalized)
        return normalized

    def _force_realtime_text_fragments(
        self,
        text: str,
        *,
        max_chars: int,
        min_chars: int,
    ) -> list[str]:
        value = re.sub(r"\s+", " ", str(text or "").strip())
        if not value:
            return []
        if len(value) <= max_chars:
            return [value]
        pieces: list[str] = []
        current = ""
        for token in re.split(r"([。！？!?；;，,、：:…]+)", value):
            if not token:
                continue
            candidate = current + token
            if current and len(candidate) > max_chars:
                pieces.extend(self._split_realtime_oversize_fragment(current, max_chars))
                current = token.strip()
            else:
                current = candidate.strip()
            if current and re.fullmatch(r".*[。！？!?；;…]+", current):
                pieces.extend(self._split_realtime_oversize_fragment(current, max_chars))
                current = ""
        if current:
            pieces.extend(self._split_realtime_oversize_fragment(current, max_chars))

        merged: list[str] = []
        for piece in pieces:
            part = piece.strip()
            if not part:
                continue
            if merged and len(merged[-1]) + 1 + len(part) <= max_chars and len(merged[-1]) < min_chars:
                merged[-1] = f"{merged[-1]} {part}".strip()
            else:
                merged.append(part)
        return merged or [value[:max_chars]]

    def _split_realtime_oversize_fragment(
        self,
        text: str,
        max_chars: int,
    ) -> list[str]:
        value = str(text or "").strip()
        if not value:
            return []
        if len(value) <= max_chars:
            return [value]
        chunks: list[str] = []
        start = 0
        while start < len(value):
            end = min(len(value), start + max_chars)
            if end < len(value):
                soft = max(
                    value.rfind("，", start, end),
                    value.rfind(",", start, end),
                    value.rfind("、", start, end),
                    value.rfind(" ", start, end),
                )
                if soft > start + max(8, max_chars // 3):
                    end = soft + 1
            chunks.append(value[start:end].strip())
            start = end
        return [chunk for chunk in chunks if chunk]

    def _preserve_intercepted_completion_text(
        self,
        response: LLMResponse,
        text: str,
        *,
        reason: str,
        clear_completion: bool = False,
    ) -> None:
        preserved = str(text or "")
        for name, value in (
            ("_sylanne_intercepted_completion_text", preserved),
            ("_sylanne_intercepted_completion_reason", str(reason or "")),
        ):
            try:
                setattr(response, name, value)
            except Exception:
                pass
        if clear_completion:
            try:
                setattr(response, "completion_text", "")
            except Exception:
                pass

    def _stop_default_response_send(
        self,
        event: AstrMessageEvent,
        *,
        reason: str,
    ) -> bool:
        stopped = False
        stopper = getattr(event, "stop_event", None)
        if callable(stopper):
            try:
                stopper()
                stopped = True
            except Exception as exc:
                self._log_warning(
                    f"{PLUGIN_NAME}: 阻断 AstrBot 默认发送失败，继续保留主回复文本供上下文使用: {exc}",
                )
        for name, value in (
            ("_sylanne_default_response_stopped", True),
            ("_sylanne_default_response_stop_reason", str(reason or "")),
        ):
            try:
                setattr(event, name, value)
            except Exception:
                pass
        return stopped

    def _should_intercept_realtime_chat_response(
        self,
        event: AstrMessageEvent,
        response_text: str,
    ) -> bool:
        if not self._realtime_chat_enabled():
            return False
        if not self._cfg_bool("realtime_chat_intercept_llm_response", True):
            return False
        if not str(response_text or "").strip():
            return False
        if not self._looks_like_event(event):
            return False
        if self._is_streaming_visible_response_event(event):
            return False
        if not self._supports_realtime_response_intercept_platform(event):
            return False
        if not hasattr(getattr(self, "context", None), "send_message"):
            return False
        return True

    def _is_streaming_visible_response_event(self, event: AstrMessageEvent) -> bool:
        platform_key = self._event_platform_key(event)
        if platform_key in {
            "webchat",
            "web",
            "chatui",
            "webui",
            "astrbotwebchat",
            "astrbotwebui",
        }:
            return True
        if self._looks_like_webchat_uuid_session(event):
            return True
        return False

    def _has_explicit_non_webchat_platform(self, event: AstrMessageEvent) -> bool:
        platform_key = self._event_platform_key(event)
        if not platform_key:
            return False
        return platform_key not in {
            "webchat",
            "web",
            "chatui",
            "webui",
            "astrbotwebchat",
            "astrbotwebui",
        }

    def _supports_realtime_response_intercept_platform(
        self,
        event: AstrMessageEvent,
    ) -> bool:
        if not self._has_explicit_non_webchat_platform(event):
            return False
        platform_key = self._event_platform_key(event)
        supported = {
            "aiocqhttp",
            "onebot",
            "napcat",
            "napcatonebot",
            "qq",
            "qqofficial",
            "telegram",
            "discord",
            "kook",
            "lark",
            "feishu",
            "dingtalk",
            "slack",
            "wechat",
            "wechatpadpro",
            "gewechat",
            "vocechat",
        }
        return platform_key in supported

    def _event_platform_key(self, event: AstrMessageEvent) -> str:
        platform_name = ""
        getter = getattr(event, "get_platform_name", None)
        if callable(getter):
            try:
                platform_name = str(getter() or "")
            except Exception:
                platform_name = ""
        if not platform_name:
            platform_name = str(getattr(event, "platform_name", "") or "")
        if not platform_name:
            getter = getattr(event, "get_platform_id", None)
            if callable(getter):
                try:
                    platform_name = str(getter() or "")
                except Exception:
                    platform_name = ""
        if not platform_name:
            platform_name = str(getattr(event, "platform_id", "") or "")
        return platform_name.strip().lower().replace("_", "").replace("-", "")

    def _looks_like_webchat_uuid_session(self, event: AstrMessageEvent) -> bool:
        session_key = str(getattr(event, "unified_msg_origin", "") or "").strip()
        return bool(
            re.fullmatch(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
            session_key,
            )
        )

    def _ensure_conversation_epoch_state(self) -> None:
        if not isinstance(getattr(self, "_conversation_input_epoch", None), dict):
            self._conversation_input_epoch = {}
        if not isinstance(getattr(self, "_conversation_pending_response_epochs", None), dict):
            self._conversation_pending_response_epochs = {}

    def _bump_conversation_input_epoch(
        self,
        session_key: str,
        *,
        event: AstrMessageEvent | None = None,
    ) -> int:
        self._ensure_conversation_epoch_state()
        key = str(session_key or "global")
        current = max(0, int(self._conversation_input_epoch.get(key) or 0))
        self._conversation_input_epoch[key] = current + 1
        if event is not None:
            try:
                setattr(event, "_sylanne_input_epoch", current + 1)
            except Exception:
                pass
        return current + 1

    def _conversation_response_epoch(
        self,
        session_key: str,
        event: AstrMessageEvent | None = None,
    ) -> int | None:
        event_epoch = self._optional_int(
            getattr(event, "_sylanne_input_epoch", None) if event is not None else None,
        )
        if event_epoch is not None:
            return event_epoch
        self._ensure_conversation_epoch_state()
        return max(0, int(self._conversation_input_epoch.get(str(session_key or "global")) or 0))

    def _record_conversation_pending_response_epoch(
        self,
        session_key: str,
        input_epoch: int | None,
    ) -> None:
        if input_epoch is None:
            return
        self._ensure_conversation_epoch_state()
        key = str(session_key or "global")
        pending = self._conversation_pending_response_epochs.setdefault(key, deque(maxlen=12))
        pending.append(int(input_epoch))

    def _discard_conversation_pending_response_epoch(
        self,
        session_key: str,
        input_epoch: int | None,
    ) -> None:
        if input_epoch is None:
            return
        self._ensure_conversation_epoch_state()
        key = str(session_key or "global")
        pending = self._conversation_pending_response_epochs.get(key)
        if not pending:
            return
        try:
            pending.remove(int(input_epoch))
        except ValueError:
            return
        if not pending:
            self._conversation_pending_response_epochs.pop(key, None)

    def _consume_conversation_pending_response_epoch(
        self,
        session_key: str,
        event: AstrMessageEvent | None = None,
    ) -> int | None:
        event_epoch = self._optional_int(
            getattr(event, "_sylanne_input_epoch", None) if event is not None else None,
        )
        self._ensure_conversation_epoch_state()
        key = str(session_key or "global")
        pending = self._conversation_pending_response_epochs.get(key)
        if event_epoch is not None:
            if pending and event_epoch in pending:
                try:
                    pending.remove(event_epoch)
                except ValueError:
                    pass
                if not pending:
                    self._conversation_pending_response_epochs.pop(key, None)
            return event_epoch
        if pending:
            epoch = pending.popleft()
            if not pending:
                self._conversation_pending_response_epochs.pop(key, None)
            return int(epoch)
        return self._conversation_response_epoch(key, event)

    def _conversation_reply_is_stale(
        self,
        session_key: str,
        input_epoch: int | None,
    ) -> bool:
        if input_epoch is None:
            return False
        self._ensure_conversation_epoch_state()
        current = max(0, int(self._conversation_input_epoch.get(str(session_key or "global")) or 0))
        return current > int(input_epoch)

    def _interrupted_reply_breakpoint_cache(
        self,
    ) -> dict[str, deque[dict[str, Any]]]:
        cache = getattr(self, "_interrupted_reply_breakpoints", None)
        if not isinstance(cache, dict):
            cache = {}
            self._interrupted_reply_breakpoints = cache
        return cache

    def _record_interrupted_reply_breakpoint(
        self,
        session_key: str,
        *,
        reason: str,
        input_epoch: int | None,
        full_text: str = "",
        sent_parts: Sequence[str] | None = None,
        unsent_parts: Sequence[str] | None = None,
        message_parts: Sequence[dict[str, Any]] | None = None,
        source: str = "",
    ) -> None:
        key = str(session_key or "global")
        sent = [str(part or "").strip() for part in (sent_parts or []) if str(part or "").strip()]
        unsent = [
            str(part or "").strip()
            for part in (unsent_parts or [])
            if str(part or "").strip()
        ]
        if not unsent and message_parts:
            sent_count = len(sent)
            unsent = [
                str(part.get("text") or "").strip()
                for part in list(message_parts)[sent_count:]
                if str(part.get("text") or "").strip()
            ]
        full = str(full_text or "").strip()
        if not full:
            full = "\n".join(sent + unsent).strip()
        if not full and not sent and not unsent:
            return
        now = self._observed_now()
        entry = {
            "schema_version": "astrbot.interrupted_reply_breakpoint.v1",
            "kind": "interrupted_reply_breakpoint",
            "session_key": key,
            "reason": str(reason or "interrupted"),
            "source": str(source or "llm_response"),
            "input_epoch": input_epoch,
            "recorded_at": now,
            "sent_count": len(sent),
            "unsent_count": len(unsent) if unsent else (1 if full else 0),
            "full_text_chars": len(full),
            "sent_text_hash": self._text_hash(" / ".join(sent)),
            "unsent_text_hash": self._text_hash(" / ".join(unsent) if unsent else full),
            "full_text_hash": self._text_hash(full),
            "sent_excerpt": self._head_one_line(" / ".join(sent), 96),
            "unsent_head": self._head_one_line(
                " / ".join(unsent) if unsent else full,
                96,
            ),
            "full_text": self._head_text(full, INTERRUPTED_REPLY_LOCAL_MAX_CHARS),
            "full_text_truncated": len(full) > INTERRUPTED_REPLY_LOCAL_MAX_CHARS,
            "consumed": False,
        }
        limit = INTERRUPTED_REPLY_BREAKPOINT_LIMIT
        cache = self._interrupted_reply_breakpoint_cache()
        queue = cache.setdefault(key, deque(maxlen=limit))
        if queue.maxlen != limit:
            queue = deque(queue, maxlen=limit)
            cache[key] = queue
        queue.append(entry)

    def _latest_interrupted_reply_observation_text(self, session_key: str) -> str:
        queue = self._interrupted_reply_breakpoint_cache().get(str(session_key or "global"))
        if not queue:
            return ""
        pending = [item for item in queue if not item.get("emotion_observed")]
        if not pending:
            return ""
        item = pending[-1]
        item["emotion_observed"] = True
        item["emotion_observed_at"] = self._observed_now()
        return self._head_text(
            "\n".join(
                [
                    "[assistant_interrupted_event]",
                    "bot 刚才的回复在发送中或生成后被用户新消息打断；这本身可能带来情绪波动。"
                    "请结合当前用户新消息判断这是亲密打断、正常补充、紧急纠正、冷场还是冲突升级；"
                    "不要预设一定是正面或负面。",
                    "reason={reason}; sent_count={sent_count}; unsent_count={unsent_count}; full_hash={hash}".format(
                        reason=self._head_one_line(str(item.get("reason") or "interrupted"), 48),
                        sent_count=int(item.get("sent_count") or 0),
                        unsent_count=int(item.get("unsent_count") or 0),
                        hash=str(item.get("full_text_hash") or "")[:16],
                    ),
                    "sent_excerpt={text}".format(
                        text=self._head_one_line(str(item.get("sent_excerpt") or ""), 96),
                    ),
                    "unsent_head={text}".format(
                        text=self._head_one_line(str(item.get("unsent_head") or ""), 96),
                    ),
                ],
            ),
            520,
        )

    def _augment_current_text_with_interruption_event(
        self,
        session_key: str,
        current_text: str,
    ) -> str:
        interruption = self._latest_interrupted_reply_observation_text(session_key)
        if not interruption:
            return current_text
        return self._clip(
            "\n\n".join(
                part
                for part in (
                    interruption,
                    "[current_user]\n" + str(current_text or ""),
                )
                if part
            ),
            1600,
        )

    def _append_interrupted_reply_breakpoint_if_any(
        self,
        request: ProviderRequest,
        session_key: str,
        *,
        budget: _StateInjectionBudget | None,
    ) -> bool:
        queue = self._interrupted_reply_breakpoint_cache().get(str(session_key or "global"))
        if not queue:
            return False
        pending = [item for item in queue if not item.get("consumed")]
        if not pending:
            return False
        max_items = INTERRUPTED_REPLY_INJECTION_MAX_ITEMS
        items = pending[-max_items:]
        lines = [
            "[sylanne_interrupted_reply_breakpoint]",
            "上一段回复被用户新消息或撤回打断。不要原样续发旧回复；只把它当作对话断点来理解当前消息。",
        ]
        for item in items:
            lines.append(
                "reason={reason}; sent_count={sent_count}; unsent_count={unsent_count}; "
                "old_epoch={epoch}; full_chars={full_chars}; unsent_hash={unsent_hash}; full_hash={full_hash}".format(
                    reason=self._head_one_line(str(item.get("reason") or "interrupted"), 48),
                    sent_count=int(item.get("sent_count") or 0),
                    unsent_count=int(item.get("unsent_count") or 0),
                    epoch="" if item.get("input_epoch") is None else item.get("input_epoch"),
                    full_chars=int(item.get("full_text_chars") or 0),
                    unsent_hash=str(item.get("unsent_text_hash") or "")[:16],
                    full_hash=str(item.get("full_text_hash") or "")[:16],
                ),
            )
        text = "\n".join(lines)
        max_chars = INTERRUPTED_REPLY_INJECTION_MAX_CHARS
        text = self._head_text(text, max_chars)
        appended = self._append_temp_text_part(
            request,
            text,
            source="interrupted_reply_breakpoint",
            budget=budget,
        )
        if appended:
            for item in items:
                item["consumed"] = True
                item["consumed_at"] = self._observed_now()
        return appended

    def _append_realtime_continuity_context_if_any(
        self,
        request: ProviderRequest,
        session_key: str,
        *,
        budget: _StateInjectionBudget | None,
        current_user_text: str = "",
    ) -> bool:
        appended = False
        is_correction = self._looks_like_user_correction_or_source_query(
            current_user_text,
        )
        if is_correction:
            appended = (
                self._append_user_correction_context(
                    request,
                    current_user_text,
                    budget=budget,
                )
                or appended
            )
        appended = (
            self._append_realtime_chat_active_dispatch_if_any(
                request,
                session_key,
                budget=budget,
            )
            or appended
        )
        appended = (
            (
                False
                if is_correction
                else self._append_realtime_assistant_history_shadow_if_any(
                    request,
                    session_key,
                    budget=budget,
                    current_user_text=current_user_text,
                )
            )
            or appended
        )
        appended = (
            self._append_interrupted_reply_breakpoint_if_any(
                request,
                session_key,
                budget=budget,
            )
            or appended
        )
        return appended

    def _append_user_correction_context(
        self,
        request: ProviderRequest,
        current_user_text: str,
        *,
        budget: _StateInjectionBudget | None,
    ) -> bool:
        text = "\n".join(
            [
                "[sylanne_user_correction_context]",
                "用户当前发言可能是在纠正上一轮误读、澄清指代，或追问信息来源。",
                "优先处理用户纠正和来源问题；如果上一轮理解错了，先简短承认并重述用户真正问题。",
                "不要继续沿着上一轮误会、吃醋、撒娇、指责或自我辩解方向展开。",
                "current_user=" + self._head_one_line(str(current_user_text or ""), 180),
            ],
        )
        return self._append_temp_text_part(
            request,
            text,
            source="user_correction_context",
            budget=budget,
        )

    def _looks_like_user_correction_or_source_query(self, text: str) -> bool:
        value = str(text or "").strip()
        if not value:
            return False
        compact = re.sub(r"\s+", "", value)
        correction_markers = (
            "不是",
            "不对",
            "我是说",
            "我说的是",
            "我的意思是",
            "你理解错",
            "你误会",
            "不是这个意思",
        )
        source_markers = (
            "从哪里看来的",
            "从哪儿看来的",
            "从哪看来的",
            "是从哪里看来的",
            "哪里看来的",
            "哪儿看来的",
            "你从哪看",
            "来源",
            "依据",
            "为啥你要问",
        )
        return any(marker in compact for marker in correction_markers + source_markers)

    def _append_realtime_input_fragment_context_if_any(
        self,
        event: AstrMessageEvent,
        request: ProviderRequest,
        identity: ConversationIdentity,
        *,
        current_user_text: str,
        observed_at: float,
        budget: _StateInjectionBudget | None,
    ) -> bool:
        payload = self._observe_realtime_input_fragment_context_sync(
            request,
            identity,
            current_user_text=current_user_text,
            observed_at=observed_at,
            budget=budget,
        )
        return bool(payload.get("should_inject"))

    async def _observe_realtime_input_fragment_context_if_any(
        self,
        event: AstrMessageEvent,
        request: ProviderRequest,
        identity: ConversationIdentity,
        *,
        current_user_text: str,
        observed_at: float,
        budget: _StateInjectionBudget | None,
    ) -> dict[str, Any]:
        del event
        return self._observe_realtime_input_fragment_context_sync(
            request,
            identity,
            current_user_text=current_user_text,
            observed_at=observed_at,
            budget=budget,
        )

    def _observe_realtime_input_fragment_context_sync(
        self,
        request: ProviderRequest,
        identity: ConversationIdentity,
        *,
        current_user_text: str,
        observed_at: float,
        budget: _StateInjectionBudget | None,
    ) -> dict[str, Any]:
        if not self._realtime_chat_enabled():
            return {}
        source = "realtime_input_fragments"
        if getattr(request, "_sylanne_realtime_input_observed", False):
            return {}
        try:
            setattr(request, "_sylanne_realtime_input_observed", True)
        except Exception:
            pass
        if self._request_has_temp_text_source(request, source):
            return {}
        payload = observe_realtime_input_fragment(
            self._realtime_input_fragment_window_cache(),
            session_key=identity.conversation_id,
            speaker_key=identity.speaker_track_id
            or identity.speaker_id
            or identity.conversation_id,
            text=current_user_text,
            now=observed_at,
            settings=self._realtime_input_settings(),
        )
        try:
            setattr(request, "_sylanne_realtime_input_payload", payload)
        except Exception:
            pass
        if not payload.get("should_inject"):
            return payload
        text = build_realtime_input_fragment_injection(
            payload,
            max_chars=REALTIME_INPUT_FRAGMENT_INJECTION_MAX_CHARS,
        )
        self._append_temp_text_part(
            request,
            text,
            source=source,
            budget=budget,
        )
        return payload

    def _realtime_input_fragment_should_hold(self, payload: dict[str, Any] | None) -> bool:
        return bool(isinstance(payload, dict) and payload.get("should_hold"))

    def _realtime_input_merged_intent_from_payload(
        self,
        payload: dict[str, Any] | None,
    ) -> str:
        if not isinstance(payload, dict):
            return ""
        if not payload.get("should_inject") and not payload.get("should_hold"):
            return ""
        return str(payload.get("merged_intent") or "").strip()

    def _append_realtime_input_released_context_if_any(
        self,
        request: ProviderRequest,
        payload: dict[str, Any] | None,
        *,
        budget: _StateInjectionBudget | None,
    ) -> bool:
        if not isinstance(payload, dict) or not payload.get("should_hold"):
            return False
        release_payload = dict(payload)
        release_payload["should_inject"] = True
        release_payload["reason"] = "released_after_completion_wait"
        fragments = release_payload.get("fragments")
        if isinstance(fragments, list):
            release_payload["fragment_count"] = len(fragments)
            release_payload["display_sequence"] = " / ".join(str(item) for item in fragments)
        text = build_realtime_input_fragment_injection(
            release_payload,
            max_chars=REALTIME_INPUT_FRAGMENT_INJECTION_MAX_CHARS,
        )
        return self._append_temp_text_part(
            request,
            text,
            source="realtime_input_fragments",
            budget=budget,
        )

    async def _realtime_input_fragment_still_waiting_after_gate(
        self,
        event: AstrMessageEvent,
        identity: ConversationIdentity,
        payload: dict[str, Any],
    ) -> bool:
        wait_seconds = self._realtime_input_completion_wait_seconds(payload)
        if not await self._wait_realtime_input_window_unchanged(
            identity.conversation_id,
            payload,
            wait_seconds,
        ):
            return True
        if self._cfg_bool("use_llm_assessor", True) and self._cfg_bool(
            "realtime_input_completion_llm_gate_enabled",
            True,
        ):
            judgement = await self._judge_realtime_input_completion(event, payload)
        else:
            judgement = self._local_realtime_input_completion_judgement(payload)
        if judgement.get("is_complete"):
            return False
        remaining = 0.0
        if str(judgement.get("source") or "") == "llm_input_completion_gate":
            remaining = max(
                0.0,
                self._realtime_input_completion_max_wait_seconds() - wait_seconds,
            )
        if not await self._wait_realtime_input_window_unchanged(
            identity.conversation_id,
            payload,
            remaining,
        ):
            return True
        if self._realtime_input_window_matches_payload(identity.conversation_id, payload):
            return False
        return True

    async def _wait_realtime_input_window_unchanged(
        self,
        session_key: str,
        payload: dict[str, Any],
        wait_seconds: float,
    ) -> bool:
        deadline = self._loop_time() + max(0.0, float(wait_seconds))
        while True:
            if not self._realtime_input_window_matches_payload(session_key, payload):
                return False
            remaining = deadline - self._loop_time()
            if remaining <= 0:
                return True
            await asyncio.sleep(min(0.08, remaining))

    def _loop_time(self) -> float:
        try:
            return asyncio.get_running_loop().time()
        except RuntimeError:
            return time.monotonic()

    def _realtime_input_completion_wait_seconds(self, payload: dict[str, Any]) -> float:
        fragments = payload.get("fragments") if isinstance(payload, dict) else None
        count = len(fragments) if isinstance(fragments, list) else 1
        base = max(0.0, self._cfg_float("realtime_input_completion_probe_delay_seconds", 0.65))
        if count > 1:
            base *= 0.65
        if str(payload.get("reason") or "") == "waiting_for_more_fragments":
            base *= 0.55
        return min(
            self._realtime_input_completion_max_wait_seconds(),
            base,
        )

    def _realtime_input_completion_max_wait_seconds(self) -> float:
        return min(
            REALTIME_INPUT_LLM_WAIT_MAX_SECONDS,
            max(0.0, self._cfg_float("realtime_input_completion_max_wait_seconds", 20.0)),
        )

    def _realtime_input_window_matches_payload(
        self,
        session_key: str,
        payload: dict[str, Any],
    ) -> bool:
        window = self._realtime_input_fragment_window_cache().get(
            str(session_key or "global"),
        )
        if not isinstance(window, dict):
            return False
        current = [
            getattr(item, "text", "")
            for item in (window.get("fragments") or [])
        ]
        expected = [str(item or "") for item in (payload.get("fragments") or [])]
        return bool(current) and current == expected

    def _release_realtime_input_fragment_window_if_unchanged(
        self,
        session_key: str,
        payload: dict[str, Any],
    ) -> None:
        if self._realtime_input_window_matches_payload(session_key, payload):
            self._realtime_input_fragment_window_cache().pop(
                str(session_key or "global"),
                None,
            )

    async def _judge_realtime_input_completion(
        self,
        event: AstrMessageEvent,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        fallback = self._local_realtime_input_completion_judgement(payload)
        provider_id = await self._provider_id(event)
        if not provider_id:
            return fallback
        token = _INTERNAL_LLM_CALL.set(True)
        try:
            llm_resp = await self._call_internal_assessor_llm(
                provider_id=provider_id,
                prompt=self._build_realtime_input_completion_prompt(payload),
                system_prompt=(
                    "你是聊天输入完整度判断器。只输出 JSON，不要解释。"
                    "判断用户是否已经把当前这句话说完，宁可保守等待，也不要让 bot 抢答半句话。"
                ),
            )
        except Exception as exc:
            self._log_warning(f"{PLUGIN_NAME}: 输入分块完整度判断失败，使用本地回退: {exc}")
            return fallback
        finally:
            _INTERNAL_LLM_CALL.reset(token)
        parsed = self._parse_realtime_input_completion_judgement(
            getattr(llm_resp, "completion_text", ""),
        )
        return parsed or fallback

    def _build_realtime_input_completion_prompt(self, payload: dict[str, Any]) -> str:
        fragments = [str(item or "") for item in (payload.get("fragments") or [])]
        return (
            "请判断下面同一用户短时间内发出的聊天碎片是否已经表达完整。\n"
            "只输出 JSON：{\"is_complete\": true/false, \"confidence\": 0-1, \"reason\": \"...\"}。\n"
            "规则：如果像半句话、强调铺垫、还在补充主语/谓语/宾语，就 is_complete=false；"
            "如果已经形成可回复的完整问题、完整声明、完整纠正，则 is_complete=true。\n"
            f"碎片序列：{json.dumps(fragments, ensure_ascii=False)}\n"
            f"合并预览：{payload.get('merged_intent') or ''}"
        )

    def _parse_realtime_input_completion_judgement(
        self,
        text: str,
    ) -> dict[str, Any] | None:
        raw = str(text or "").strip()
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        value = data.get("is_complete")
        if isinstance(value, str):
            value = value.strip().lower() in {"true", "yes", "1", "complete", "完整", "已完成"}
        elif isinstance(value, (int, float)):
            value = bool(value)
        elif not isinstance(value, bool):
            return None
        return {
            "is_complete": bool(value),
            "confidence": self._clamp01(data.get("confidence", 0.5)),
            "reason": self._head_one_line(str(data.get("reason") or ""), 160),
            "source": "llm_input_completion_gate",
        }

    def _local_realtime_input_completion_judgement(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        reason = str(payload.get("reason") or "")
        fragments = payload.get("fragments") if isinstance(payload.get("fragments"), list) else []
        text = str(payload.get("merged_intent") or "").strip()
        is_complete = reason == "waiting_for_more_fragments" and len(fragments) >= 3
        if "?" in text or "？" in text:
            is_complete = True
        return {
            "is_complete": bool(is_complete),
            "confidence": 0.35,
            "reason": "local_fragment_completion_fallback",
            "source": "local",
        }

    def _mark_realtime_input_fragment_hold(
        self,
        event: AstrMessageEvent,
        request: ProviderRequest,
        payload: dict[str, Any],
    ) -> None:
        hold_text = build_realtime_input_hold_injection(
            payload,
            max_chars=REALTIME_INPUT_HOLD_INJECTION_MAX_CHARS,
        )
        for target in (event, request):
            for name, value in (
                ("_sylanne_realtime_input_hold", True),
                ("_sylanne_realtime_input_hold_payload", payload),
                ("_sylanne_default_response_stopped", True),
                ("_sylanne_default_response_stop_reason", "realtime_input_fragment_waiting"),
            ):
                try:
                    setattr(target, name, value)
                except Exception:
                    pass
        if hold_text:
            try:
                setattr(request, "_sylanne_realtime_input_hold_text", hold_text)
            except Exception:
                pass
        self._stop_default_response_send(
            event,
            reason="realtime_input_fragment_waiting",
        )

    def _realtime_input_hold_context_text(
        self,
        request: ProviderRequest,
        current_user_text: str,
        payload: dict[str, Any],
    ) -> str:
        hold_text = str(getattr(request, "_sylanne_realtime_input_hold_text", "") or "")
        if not hold_text:
            hold_text = build_realtime_input_hold_injection(
                payload,
                max_chars=REALTIME_INPUT_HOLD_INJECTION_MAX_CHARS,
            )
        return self._clip(
            "\n\n".join(
                part
                for part in (
                    hold_text,
                    "[current_user_fragment]\n" + str(current_user_text or ""),
                )
                if part
            ),
            800,
        )

    def _interrupted_reply_runtime_summary(self, session_key: str) -> dict[str, Any]:
        queue = self._interrupted_reply_breakpoint_cache().get(str(session_key or "global"))
        items = list(queue or ())
        pending = [item for item in items if not item.get("consumed")]
        latest = items[-1] if items else {}
        return {
            "enabled": True,
            "storage": "memory_only",
            "token_policy": "compact_once_per_breakpoint",
            "limit": INTERRUPTED_REPLY_BREAKPOINT_LIMIT,
            "pending_count": len(pending),
            "total_count": len(items),
            "injection_max_items": INTERRUPTED_REPLY_INJECTION_MAX_ITEMS,
            "injection_max_chars": INTERRUPTED_REPLY_INJECTION_MAX_CHARS,
            "local_full_text_max_chars": INTERRUPTED_REPLY_LOCAL_MAX_CHARS,
            "latest_reason": latest.get("reason", ""),
            "latest_sent_count": int(latest.get("sent_count") or 0) if latest else 0,
            "latest_unsent_count": int(latest.get("unsent_count") or 0) if latest else 0,
        }

    def _realtime_assistant_history_shadow_cache(
        self,
    ) -> dict[str, deque[dict[str, Any]]]:
        cache = getattr(self, "_realtime_assistant_history_shadows", None)
        if not isinstance(cache, dict):
            cache = {}
            self._realtime_assistant_history_shadows = cache
        return cache

    def _record_realtime_assistant_history_shadow(
        self,
        session_key: str,
        *,
        full_text: str,
        input_epoch: int | None,
        message_parts: Sequence[dict[str, Any]] | None = None,
        source: str = "llm_response_intercept",
    ) -> None:
        text = str(full_text or "").strip()
        if not text:
            return
        key = str(session_key or "global")
        parts = [
            str(part.get("text") or "").strip()
            for part in (message_parts or [])
            if str(part.get("text") or "").strip()
        ]
        entry = {
            "schema_version": "astrbot.realtime_assistant_history_shadow.v1",
            "kind": "realtime_assistant_history_shadow",
            "session_key": key,
            "source": str(source or "llm_response_intercept"),
            "input_epoch": input_epoch,
            "recorded_at": self._observed_now(),
            "message_count": len(parts) if parts else 1,
            "full_text_chars": len(text),
            "full_text_hash": self._text_hash(text),
            "excerpt": self._head_text(
                " / ".join(parts) if parts else text,
                REALTIME_ASSISTANT_HISTORY_EXCERPT_CHARS,
            ),
            "question_excerpt": self._extract_pending_bot_question_excerpt(
                " / ".join(parts) if parts else text,
            ),
            "consumed": False,
        }
        question_excerpt = str(entry.get("question_excerpt") or "").strip()
        entry["looks_like_question"] = bool(question_excerpt)
        entry["expects_short_answer"] = bool(
            question_excerpt and self._looks_like_choice_or_direct_question(question_excerpt),
        )
        cache = self._realtime_assistant_history_shadow_cache()
        queue = cache.setdefault(
            key,
            deque(maxlen=REALTIME_ASSISTANT_HISTORY_LIMIT),
        )
        if queue.maxlen != REALTIME_ASSISTANT_HISTORY_LIMIT:
            queue = deque(queue, maxlen=REALTIME_ASSISTANT_HISTORY_LIMIT)
            cache[key] = queue
        queue.append(entry)

    def _append_realtime_assistant_history_shadow_if_any(
        self,
        request: ProviderRequest,
        session_key: str,
        *,
        budget: _StateInjectionBudget | None,
        current_user_text: str = "",
    ) -> bool:
        queue = self._realtime_assistant_history_shadow_cache().get(
            str(session_key or "global"),
        )
        if not queue:
            return False
        pending = [item for item in queue if not item.get("consumed")]
        if not pending:
            return False
        if getattr(request, "_sylanne_realtime_shadow_deferred_for_low_signal", False):
            return False
        if self._should_defer_realtime_shadow_for_low_signal(current_user_text):
            try:
                setattr(request, "_sylanne_realtime_shadow_deferred_for_low_signal", True)
            except Exception:
                pass
            return False
        item = pending[-1]
        if self._agent_history_already_contains_realtime_shadow(request, item):
            item["consumed"] = True
            item["consumed_at"] = self._observed_now()
            item["consumed_reason"] = "agent_history_already_contains_reply"
            return False
        if self._should_anchor_short_answer_to_realtime_question(item, current_user_text):
            appended = self._append_realtime_pending_bot_question_context(
                request,
                item,
                current_user_text=current_user_text,
                budget=budget,
            )
            if appended:
                item["consumed"] = True
                item["consumed_at"] = self._observed_now()
                item["consumed_reason"] = "short_answer_bound_to_last_question"
                return True
        if self._context_compression_summary_covers_realtime_shadow(request, item):
            item["consumed"] = True
            item["consumed_at"] = self._observed_now()
            item["consumed_reason"] = "official_context_compression_summary"
            return False
        text = "\n".join(
            [
                "[sylanne_realtime_assistant_history]",
                "上一轮回复使用即时聊天分条发送，可能没有进入平台的普通 LLM 历史。下面是一次性短上下文，用来保持代词、指代和刚才话题，不要逐字复读。",
                "source={source}; message_count={message_count}; chars={chars}; full_hash={hash}".format(
                    source=self._head_one_line(str(item.get("source") or ""), 48),
                    message_count=int(item.get("message_count") or 0),
                    chars=int(item.get("full_text_chars") or 0),
                    hash=str(item.get("full_text_hash") or "")[:16],
                ),
                str(item.get("excerpt") or "").strip(),
            ],
        )
        text = self._head_text(text, REALTIME_ASSISTANT_HISTORY_INJECTION_MAX_CHARS)
        appended = self._append_temp_text_part(
            request,
            text,
            source="realtime_assistant_history_shadow",
            budget=budget,
        )
        if appended:
            item["consumed"] = True
            item["consumed_at"] = self._observed_now()
        return appended

    def _extract_pending_bot_question_excerpt(self, text: str) -> str:
        value = " ".join(str(text or "").split()).strip()
        if not value:
            return ""
        parts = [
            part.strip()
            for part in re.split(r"(?<=[。！？!?；;])\s+|/+", value)
            if part.strip()
        ]
        candidates = parts or [value]
        for candidate in reversed(candidates[-4:]):
            if self._looks_like_choice_or_direct_question(candidate):
                return self._head_text(candidate, 220)
        if self._looks_like_choice_or_direct_question(value):
            return self._head_text(value, 220)
        return ""

    def _looks_like_choice_or_direct_question(self, text: str) -> bool:
        value = " ".join(str(text or "").split()).strip()
        if not value:
            return False
        lowered = value.lower()
        question_mark = "?" in value or "？" in value
        choice_markers = (
            "还是",
            "或者",
            "要不要",
            "是不是",
            "是否",
            "哪一个",
            "哪个",
            "选",
            "A/",
            "B/",
            "a/",
            "b/",
            "ip",
            "域名",
        )
        if question_mark:
            return True
        if any(marker in value for marker in choice_markers):
            return True
        if " or " in lowered or " vs " in lowered:
            return True
        return False

    def _looks_like_short_answer_to_pending_question(self, text: str) -> bool:
        value = " ".join(str(text or "").split()).strip()
        if not value:
            return False
        if "\n" in str(text or ""):
            return False
        if len(value) > 18:
            return False
        if "?" in value or "？" in value:
            return False
        compact = re.sub(r"[\s，。！？!?；;、,.]+", "", value)
        if not compact:
            return False
        if len(compact) <= 10:
            return True
        return bool(re.fullmatch(r"[A-Za-z0-9_.:-]{1,18}", compact))

    def _should_anchor_short_answer_to_realtime_question(
        self,
        item: dict[str, Any],
        current_user_text: str,
    ) -> bool:
        question = str(item.get("question_excerpt") or "").strip()
        if not question:
            return False
        if not bool(item.get("expects_short_answer") or item.get("looks_like_question")):
            return False
        return self._looks_like_short_answer_to_pending_question(current_user_text)

    def _append_realtime_pending_bot_question_context(
        self,
        request: ProviderRequest,
        item: dict[str, Any],
        *,
        current_user_text: str,
        budget: _StateInjectionBudget | None,
    ) -> bool:
        question = self._head_one_line(str(item.get("question_excerpt") or ""), 220)
        if not question:
            return False
        user_answer = self._head_one_line(str(current_user_text or ""), 80)
        text = "\n".join(
            [
                "[sylanne_realtime_pending_bot_question]",
                "上一轮 bot 刚提出了一个未闭合问题或二选一问题；当前用户短句优先视为对这个问题的回答，不要把它当成孤立的新话题。",
                "如果回答很短，例如 IP、域名、A、B、可以、不行，请先绑定到 last_bot_question，再继续给出下一步。",
                "source={source}; full_hash={hash}; expects_short_answer={expects}".format(
                    source=self._head_one_line(str(item.get("source") or ""), 48),
                    hash=str(item.get("full_text_hash") or "")[:16],
                    expects=bool(item.get("expects_short_answer")),
                ),
                "last_bot_question=" + question,
                "current_user_short_answer=" + user_answer,
            ],
        )
        text = self._head_text(text, REALTIME_ASSISTANT_HISTORY_INJECTION_MAX_CHARS)
        return self._append_temp_text_part(
            request,
            text,
            source="realtime_pending_bot_question",
            budget=budget,
        )

    def _should_defer_realtime_shadow_for_low_signal(self, current_user_text: str) -> bool:
        profile = self._low_signal_text_profile(current_user_text)
        if not profile.get("is_low_signal"):
            return False
        return str(profile.get("kind") or "") in {
            "empty",
            "short_ack",
            "punctuation_or_emoji",
            "repeated",
        }

    def _context_compression_summary_covers_realtime_shadow(
        self,
        request: ProviderRequest,
        item: dict[str, Any],
    ) -> bool:
        context_text = "\n".join(
            self._context_item_to_text(context_item)
            for context_item in self._tail_items(getattr(request, "contexts", []) or [], 6)
        )
        if not context_text:
            return False
        lowered = context_text.lower()
        compression_markers = (
            "自动压缩",
            "压缩上下文",
            "context compression",
            "compressed context",
            "summary",
            "摘要",
        )
        if not any(marker in lowered for marker in compression_markers):
            return False
        if "sylanne_realtime_assistant_history" in context_text:
            return True
        full_hash = str(item.get("full_text_hash") or "")
        if full_hash and full_hash[:16] in context_text:
            return True
        excerpt = self._head_one_line(str(item.get("excerpt") or ""), 80)
        return bool(excerpt and excerpt in context_text)

    def _agent_history_already_contains_realtime_shadow(
        self,
        request: ProviderRequest,
        item: dict[str, Any],
    ) -> bool:
        context_text = "\n".join(
            self._context_item_to_text(context_item)
            for context_item in self._tail_items(getattr(request, "contexts", []) or [], 8)
        )
        if not context_text:
            return False
        excerpt = self._head_one_line(str(item.get("excerpt") or ""), 96)
        if excerpt and excerpt in context_text:
            return True
        question = self._head_one_line(str(item.get("question_excerpt") or ""), 96)
        if question and question in context_text:
            return True
        full_hash = str(item.get("full_text_hash") or "")
        if full_hash and full_hash[:16] in context_text:
            return True
        normalized_context = self._normalize_realtime_history_match_text(context_text)
        for candidate in (
            str(item.get("excerpt") or ""),
            str(item.get("question_excerpt") or ""),
        ):
            normalized_candidate = self._normalize_realtime_history_match_text(candidate)
            if normalized_candidate and normalized_candidate in normalized_context:
                return True
        return False

    def _normalize_realtime_history_match_text(self, text: str) -> str:
        value = str(text or "").lower()
        value = value.replace("/", "")
        value = re.sub(r"[\s，。！？!?；;、,.：:（）()【】\\[\\]\"'“”‘’]+", "", value)
        return value.strip()

    def _realtime_chat_active_dispatch_cache(self) -> dict[str, dict[str, Any]]:
        cache = getattr(self, "_realtime_chat_active_dispatches", None)
        if not isinstance(cache, dict):
            cache = {}
            self._realtime_chat_active_dispatches = cache
        return cache

    def _realtime_chat_dispatch_task_cache(self) -> dict[str, set[asyncio.Task[Any]]]:
        cache = getattr(self, "_realtime_chat_dispatch_tasks", None)
        if not isinstance(cache, dict):
            cache = {}
            self._realtime_chat_dispatch_tasks = cache
        return cache

    def _register_realtime_chat_dispatch_task(
        self,
        session_key: str,
        task: asyncio.Task[Any],
    ) -> None:
        key = str(session_key or "global")
        tasks = self._realtime_chat_dispatch_task_cache().setdefault(key, set())
        tasks.add(task)

    def _unregister_realtime_chat_dispatch_task(
        self,
        session_key: str,
        task: asyncio.Task[Any],
    ) -> None:
        key = str(session_key or "global")
        tasks = self._realtime_chat_dispatch_task_cache().get(key)
        if not tasks:
            return
        tasks.discard(task)
        if not tasks:
            self._realtime_chat_dispatch_task_cache().pop(key, None)

    def _cancel_realtime_chat_dispatches_for_session(
        self,
        session_key: str,
        *,
        reason: str,
    ) -> int:
        key = str(session_key or "global")
        tasks = list(self._realtime_chat_dispatch_task_cache().get(key) or ())
        cancelled = 0
        current = asyncio.current_task()
        for task in tasks:
            if task is current or task.done():
                continue
            task.cancel()
            cancelled += 1
        if cancelled:
            active = self._realtime_chat_active_dispatch_cache().get(key)
            if active:
                active["cancel_reason"] = str(reason or "user_interrupted")
                active["cancel_requested_at"] = self._observed_now()
        return cancelled

    def _start_realtime_chat_active_dispatch(
        self,
        session_key: str,
        *,
        input_epoch: int | None,
        full_text: str,
        source: str,
    ) -> None:
        text = str(full_text or "").strip()
        if not text:
            return
        self._realtime_chat_active_dispatch_cache()[str(session_key or "global")] = {
            "schema_version": "astrbot.realtime_chat_active_dispatch.v1",
            "kind": "realtime_chat_active_dispatch",
            "session_key": str(session_key or "global"),
            "source": str(source or "realtime_chat"),
            "input_epoch": input_epoch,
            "started_at": self._observed_now(),
            "full_text_chars": len(text),
            "full_text_hash": self._text_hash(text),
            "full_text": self._head_text(text, REALTIME_ASSISTANT_HISTORY_EXCERPT_CHARS),
            "sent_parts": [],
            "completed": False,
        }

    def _append_realtime_chat_active_dispatch_part(
        self,
        session_key: str,
        text: str,
    ) -> None:
        active = self._realtime_chat_active_dispatch_cache().get(
            str(session_key or "global"),
        )
        if not active:
            return
        part = str(text or "").strip()
        if not part:
            return
        sent_parts = active.setdefault("sent_parts", [])
        if isinstance(sent_parts, list):
            sent_parts.append(part)
            del sent_parts[:-8]

    def _finish_realtime_chat_active_dispatch(self, session_key: str) -> None:
        active = self._realtime_chat_active_dispatch_cache().get(
            str(session_key or "global"),
        )
        if active:
            active["completed"] = True
            active["finished_at"] = self._observed_now()
            self._realtime_chat_active_dispatch_cache().pop(
                str(session_key or "global"),
                None,
            )

    def _append_realtime_chat_active_dispatch_if_any(
        self,
        request: ProviderRequest,
        session_key: str,
        *,
        budget: _StateInjectionBudget | None,
    ) -> bool:
        active = self._realtime_chat_active_dispatch_cache().get(
            str(session_key or "global"),
        )
        if not active:
            return False
        sent_parts = [
            str(part or "").strip()
            for part in active.get("sent_parts", [])
            if str(part or "").strip()
        ]
        has_started = bool(sent_parts)
        full_text_excerpt = self._head_text(
            str(active.get("full_text") or ""),
            REALTIME_ASSISTANT_HISTORY_EXCERPT_CHARS,
        )
        continuity_hint = (
            "上一轮回复正在由插件分条发送，用户已经插话；下面是已发出的短句，用来维持刚才话题和代词指代。不要复读旧文本，直接接住用户新消息。"
            if has_started
            else "上一轮回复已经生成并由插件接管分条，但在第一条真正发出前用户连续补充了新消息；下面是未发出的完整回复摘要，只用于理解上一轮意图和代词指代。不要复读未发出的旧回复，把用户补充视为同一轮上下文更新。"
        )
        text = "\n".join(
            [
                "[sylanne_realtime_active_dispatch]",
                continuity_hint,
                "source={source}; sent_count={sent_count}; full_hash={hash}".format(
                    source=self._head_one_line(str(active.get("source") or ""), 48),
                    sent_count=len(sent_parts),
                    hash=str(active.get("full_text_hash") or "")[:16],
                ),
                self._head_text(
                    " / ".join(sent_parts) if has_started else full_text_excerpt,
                    REALTIME_ASSISTANT_HISTORY_EXCERPT_CHARS,
                ),
            ],
        )
        text = self._head_text(text, REALTIME_ASSISTANT_HISTORY_INJECTION_MAX_CHARS)
        return self._append_temp_text_part(
            request,
            text,
            source="realtime_chat_active_dispatch",
            budget=budget,
        )

    def _napcat_recall_payload(
        self,
        event_or_session: AstrMessageEvent | str | None,
    ) -> dict[str, str]:
        if not self._looks_like_event(event_or_session):
            return {}
        raw = self._raw_platform_payload(event_or_session)
        if not isinstance(raw, dict):
            return {}
        post_type = str(raw.get("post_type") or "").strip()
        notice_type = str(raw.get("notice_type") or "").strip()
        if post_type and post_type != "notice":
            return {}
        if notice_type not in {"friend_recall", "group_recall"}:
            return {}
        return {
            "platform": "napcat_onebot",
            "post_type": post_type or "notice",
            "notice_type": notice_type,
            "message_id": str(raw.get("message_id") or ""),
            "user_id": str(raw.get("user_id") or ""),
            "group_id": str(raw.get("group_id") or ""),
            "operator_id": str(raw.get("operator_id") or ""),
        }

    def _raw_platform_payload(self, event: AstrMessageEvent) -> Any:
        candidates = [
            getattr(event, "raw_message", None),
            getattr(event, "raw_event", None),
            getattr(event, "raw", None),
        ]
        message_obj = getattr(event, "message_obj", None)
        if message_obj is not None:
            candidates.extend(
                [
                    getattr(message_obj, "raw_message", None),
                    getattr(message_obj, "raw_event", None),
                    getattr(message_obj, "raw", None),
                ],
            )
        for candidate in candidates:
            if isinstance(candidate, dict):
                return candidate
        return None

    def _realtime_chat_on_cooldown(self, session_key: str) -> bool:
        adaptive = getattr(self, "_last_realtime_chat_adaptive_settings", {}).get(
            session_key,
            {},
        )
        values = (
            adaptive.get("realtime_chat", {}).get("values", {})
            if isinstance(adaptive, dict)
            else {}
        )
        restraint = (
            adaptive.get("realtime_chat", {}).get("restraint", 0.0)
            if isinstance(adaptive, dict)
            else 0.0
        )
        cooldown = 0.0
        if values:
            cooldown = max(
                0.0,
                min(45.0, 2.0 + 24.0 * self._as_float_value(restraint, 0.0)),
            )
        if self._runtime_parameter_debug_override_enabled():
            cooldown = max(
                0.0,
                self._debug_cfg_float("realtime_chat_session_cooldown_seconds", cooldown),
            )
        if cooldown <= 0:
            return False
        last_sent = self._realtime_chat_last_sent_cache().get(session_key)
        if last_sent is None:
            return False
        return self._observed_now() - float(last_sent) < cooldown

    def _realtime_chat_last_sent_cache(self) -> dict[str, float]:
        cache = getattr(self, "_realtime_chat_last_sent", None)
        if cache is None:
            cache = {}
            self._realtime_chat_last_sent = cache
        return cache

    def _proactive_unified_msg_origin(
        self,
        event_or_session: AstrMessageEvent | str | None,
    ) -> str:
        if self._looks_like_event(event_or_session):
            return str(getattr(event_or_session, "unified_msg_origin", "") or "")
        return ""

    def _proactive_dispatch_idempotency_key(
        self,
        *,
        session_key: str,
        decision: dict[str, Any],
        message_text: str,
    ) -> str:
        basis = json.dumps(
            {
                "session_key": session_key,
                "action": decision.get("action"),
                "score": decision.get("score"),
                "message_text": message_text,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return sha256(basis.encode("utf-8", errors="ignore")).hexdigest()[:24]

    async def get_lifelike_prompt_fragment(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> str:
        """Public API: return common-ground and pacing guidance for prompt use."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._lifelike_learning_enabled():
            return ""
        state = await self._load_lifelike_learning_state(session_key)
        return build_lifelike_prompt_fragment(state)

    async def observe_lifelike_text(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        text: str = "",
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        source: str = "plugin",
        commit: bool = True,
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        """Public API: update or simulate common-ground learning from text."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if commit and not self._lifelike_learning_enabled():
            return self._lifelike_learning_disabled_payload(session_key)
        previous_state = await self._load_lifelike_learning_state(
            session_key,
            now=observed_at,
        )
        observation = heuristic_lifelike_observation(text, source=source)
        state = self.lifelike_learning_engine.update(
            previous_state,
            observation,
            now=observed_at,
        )
        if commit:
            await self._save_lifelike_learning_state(session_key, state)
        payload = state.to_public_dict(session_key=session_key, exposure="internal")
        payload["observation"] = {
            "source": observation.source,
            "confidence": observation.confidence,
            "reason": observation.reason,
            "flags": list(observation.flags),
            "committed": commit,
        }
        return payload

    async def simulate_lifelike_update(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        text: str = "",
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        source: str = "plugin",
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        """Public API: simulate common-ground learning without writing state."""
        return await self.observe_lifelike_text(
            event_or_session,
            text,
            request=request,
            session_key=session_key,
            source=source,
            commit=False,
            observed_at=observed_at,
        )

    async def reset_lifelike_learning_state(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> bool:
        """Public API: reset one session's learned common-ground state."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._lifelike_learning_reset_allowed():
            return False
        await self._delete_lifelike_learning_state(session_key)
        return True

    async def get_personality_drift_snapshot(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        exposure: str = "plugin_safe",
        include_prompt_fragment: bool = False,
    ) -> dict[str, Any]:
        """Public API: return slow real-time personality adaptation state."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._personality_drift_enabled():
            return self._personality_drift_disabled_payload(
                session_key,
                exposure=exposure,
                include_prompt_fragment=include_prompt_fragment,
            )
        event = event_or_session if self._looks_like_event(event_or_session) else None
        base_persona_profile = await self._public_persona_profile(
            event,
            request,
            allow_default=True,
        )
        state = await self._load_personality_drift_state(
            session_key,
            base_persona_profile,
        )
        payload = state.to_public_dict(session_key=session_key, exposure=exposure)
        if include_prompt_fragment:
            payload["prompt_fragment"] = build_personality_drift_prompt_fragment(state)
        return payload

    async def get_personality_drift_values(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> dict[str, float]:
        """Public API: return internal personality drift control dimensions."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._personality_drift_enabled():
            return {}
        event = event_or_session if self._looks_like_event(event_or_session) else None
        base_persona_profile = await self._public_persona_profile(
            event,
            request,
            allow_default=event is not None,
        )
        state = await self._load_personality_drift_state(
            session_key,
            base_persona_profile,
        )
        return {key: round(value, 6) for key, value in state.values.items()}

    async def get_personality_drift_prompt_fragment(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> str:
        """Public API: return a slow-adaptation prompt fragment for other plugins."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._personality_drift_enabled():
            return ""
        event = event_or_session if self._looks_like_event(event_or_session) else None
        base_persona_profile = await self._public_persona_profile(
            event,
            request,
            allow_default=True,
        )
        state = await self._load_personality_drift_state(
            session_key,
            base_persona_profile,
        )
        return build_personality_drift_prompt_fragment(state)

    async def observe_personality_drift_event(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        text: str = "",
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        source: str = "plugin",
        trait_impulses: dict[str, float] | None = None,
        intensity: float | None = None,
        reliability: float | None = None,
        relationship_importance: float | None = None,
        commit: bool = True,
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        """Public API: update or simulate slow personality drift from an event."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        event = event_or_session if self._looks_like_event(event_or_session) else None
        base_persona_profile = await self._public_persona_profile(
            event,
            request,
            allow_default=True,
        )
        if commit and not self._personality_drift_enabled():
            return self._personality_drift_disabled_payload(
                session_key,
                base_persona_profile,
            )
        previous_state = await self._load_personality_drift_state(
            session_key,
            base_persona_profile,
            now=observed_at,
        )
        observation = heuristic_personality_drift_observation(text, source=source)
        if trait_impulses:
            observation = PersonalityDriftObservation.from_dict(
                {
                    **observation.to_dict(),
                    "trait_impulses": trait_impulses,
                    "intensity": intensity if intensity is not None else observation.intensity,
                    "reliability": (
                        reliability if reliability is not None else observation.reliability
                    ),
                    "relationship_importance": (
                        relationship_importance
                        if relationship_importance is not None
                        else observation.relationship_importance
                    ),
                    "event_type": "plugin_trait_impulse",
                    "source": source,
                },
            )
        elif intensity is not None or reliability is not None or relationship_importance is not None:
            observation = PersonalityDriftObservation.from_dict(
                {
                    **observation.to_dict(),
                    "intensity": intensity if intensity is not None else observation.intensity,
                    "reliability": (
                        reliability if reliability is not None else observation.reliability
                    ),
                    "relationship_importance": (
                        relationship_importance
                        if relationship_importance is not None
                        else observation.relationship_importance
                    ),
                    "source": source,
                },
            )
        state = self.personality_drift_engine.update(
            previous_state,
            observation,
            persona_fingerprint=(
                base_persona_profile.fingerprint
                if base_persona_profile is not None
                else "default"
            ),
            now=observed_at,
        )
        if commit:
            await self._save_personality_drift_state(session_key, state)
        payload = state.to_public_dict(session_key=session_key, exposure="internal")
        payload["observation"] = {
            "source": observation.source,
            "event_type": observation.event_type,
            "intensity": observation.intensity,
            "reliability": observation.reliability,
            "relationship_importance": observation.relationship_importance,
            "trait_impulses": dict(observation.trait_impulses),
            "reason": observation.reason,
            "flags": list(observation.flags),
            "committed": commit,
        }
        return payload

    async def simulate_personality_drift_update(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        text: str = "",
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        source: str = "plugin",
        trait_impulses: dict[str, float] | None = None,
        intensity: float | None = None,
        reliability: float | None = None,
        relationship_importance: float | None = None,
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        """Public API: simulate slow personality drift without writing state."""
        return await self.observe_personality_drift_event(
            event_or_session,
            text,
            request=request,
            session_key=session_key,
            source=source,
            trait_impulses=trait_impulses,
            intensity=intensity,
            reliability=reliability,
            relationship_importance=relationship_importance,
            commit=False,
            observed_at=observed_at,
        )

    async def reset_personality_drift_state(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> bool:
        """Public API: reset one session's slow personality drift state."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._personality_drift_reset_allowed():
            return False
        await self._delete_personality_drift_state(session_key)
        return True

    async def get_moral_repair_snapshot(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        exposure: str = "plugin_safe",
        include_prompt_fragment: bool = False,
    ) -> dict[str, Any]:
        """Public API: return a layered moral repair and trust-state snapshot."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._moral_repair_modeling_enabled():
            return self._moral_repair_disabled_payload(
                session_key,
                exposure=exposure,
                include_prompt_fragment=include_prompt_fragment,
        )
        state = await self._load_moral_repair_state(session_key)
        safety_boundary = self._safety_boundary_enabled()
        action_blocking = self._shadow_action_blocking_enabled()
        payload = state.to_public_dict(
            session_key=session_key,
            exposure=exposure,
            safety_boundary=safety_boundary,
            action_blocking=action_blocking,
        )
        if include_prompt_fragment:
            payload["prompt_fragment"] = build_moral_repair_prompt_fragment(
                state,
                safety_boundary=safety_boundary,
                action_blocking=action_blocking,
            )
        return payload

    async def get_moral_repair_values(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> dict[str, float]:
        """Public API: return internal moral repair dimensions for plugins."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._moral_repair_modeling_enabled():
            return {}
        state = await self._load_moral_repair_state(session_key)
        return {key: round(value, 6) for key, value in state.values.items()}

    async def get_moral_repair_prompt_fragment(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> str:
        """Public API: return a moral repair prompt fragment other plugins may inject."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._moral_repair_modeling_enabled():
            return ""
        state = await self._load_moral_repair_state(session_key)
        return build_moral_repair_prompt_fragment(
            state,
            safety_boundary=self._safety_boundary_enabled(),
            action_blocking=self._shadow_action_blocking_enabled(),
        )

    async def observe_moral_repair_text(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        text: str = "",
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        source: str = "plugin",
        commit: bool = True,
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        """Public API: update or simulate moral repair state from plugin text."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if commit and not self._moral_repair_modeling_enabled():
            return self._moral_repair_disabled_payload(session_key)
        persona_profile = await self._public_runtime_persona_profile(
            event_or_session,
            request=request,
            session_key=session_key,
            observed_at=observed_at,
        )
        previous_state = await self._load_moral_repair_state(
            session_key,
            personality_model=self._personality_model_from_profile(persona_profile),
            now=observed_at,
        )
        observation = heuristic_moral_repair_observation(text, source=source)
        state = self.moral_repair_engine.update(
            previous_state,
            observation,
            personality_model=self._personality_model_from_profile(persona_profile),
            now=observed_at,
        )
        if commit:
            await self._save_moral_repair_state(session_key, state)
        safety_boundary = self._safety_boundary_enabled()
        action_blocking = self._shadow_action_blocking_enabled()
        payload = state.to_public_dict(
            session_key=session_key,
            exposure="internal",
            safety_boundary=safety_boundary,
            action_blocking=action_blocking,
        )
        payload["observation"] = {
            "source": observation.source,
            "confidence": observation.confidence,
            "reason": observation.reason,
            "flags": list(observation.flags),
            "committed": commit,
        }
        return payload

    async def simulate_moral_repair_update(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        text: str = "",
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        source: str = "plugin",
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        """Public API: simulate a moral repair update without writing state."""
        return await self.observe_moral_repair_text(
            event_or_session,
            text,
            request=request,
            session_key=session_key,
            source=source,
            commit=False,
            observed_at=observed_at,
        )

    async def reset_moral_repair_state(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> bool:
        """Public API: reset one session's moral repair state."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._moral_repair_reset_allowed():
            return False
        await self._delete_moral_repair_state(session_key)
        return True

    async def get_fallibility_snapshot(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        exposure: str = "plugin_safe",
        include_prompt_fragment: bool = False,
    ) -> dict[str, Any]:
        """Public API: return the optional low-risk fallibility simulation state."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._fallibility_modeling_enabled():
            return self._fallibility_disabled_payload(
                session_key,
                exposure=exposure,
                include_prompt_fragment=include_prompt_fragment,
        )
        state = await self._load_fallibility_state(session_key)
        safety_boundary = self._safety_boundary_enabled()
        action_blocking = self._shadow_action_blocking_enabled()
        payload = state.to_public_dict(
            session_key=session_key,
            exposure=exposure,
            safety_boundary=safety_boundary,
            action_blocking=action_blocking,
        )
        if include_prompt_fragment:
            payload["prompt_fragment"] = build_fallibility_prompt_fragment(
                state,
                safety_boundary=safety_boundary,
                action_blocking=action_blocking,
            )
        return payload

    async def get_fallibility_values(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> dict[str, float]:
        """Public API: return internal fallibility dimensions for plugins."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._fallibility_modeling_enabled():
            return {}
        state = await self._load_fallibility_state(session_key)
        return {key: round(value, 6) for key, value in state.values.items()}

    async def get_fallibility_prompt_fragment(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> str:
        """Public API: return a fallibility prompt fragment other plugins may inject."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._fallibility_modeling_enabled():
            return ""
        state = await self._load_fallibility_state(session_key)
        return build_fallibility_prompt_fragment(
            state,
            safety_boundary=self._safety_boundary_enabled(),
            action_blocking=self._shadow_action_blocking_enabled(),
        )

    async def observe_fallibility_text(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        text: str = "",
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        source: str = "plugin",
        commit: bool = True,
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        """Public API: update or simulate fallibility state from plugin text."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if commit and not self._fallibility_modeling_enabled():
            return self._fallibility_disabled_payload(session_key)
        persona_profile = await self._public_runtime_persona_profile(
            event_or_session,
            request=request,
            session_key=session_key,
            observed_at=observed_at,
        )
        previous_state = await self._load_fallibility_state(
            session_key,
            personality_model=self._personality_model_from_profile(persona_profile),
            now=observed_at,
        )
        observation = heuristic_fallibility_observation(text, source=source)
        state = self.fallibility_engine.update(
            previous_state,
            observation,
            personality_model=self._personality_model_from_profile(persona_profile),
            now=observed_at,
        )
        if commit:
            await self._save_fallibility_state(session_key, state)
        safety_boundary = self._safety_boundary_enabled()
        action_blocking = self._shadow_action_blocking_enabled()
        payload = state.to_public_dict(
            session_key=session_key,
            exposure="internal",
            safety_boundary=safety_boundary,
            action_blocking=action_blocking,
        )
        payload["observation"] = {
            "source": observation.source,
            "confidence": observation.confidence,
            "reason": observation.reason,
            "flags": list(observation.flags),
            "committed": commit,
        }
        return payload

    async def simulate_fallibility_update(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        text: str = "",
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        source: str = "plugin",
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        """Public API: simulate a fallibility update without writing state."""
        return await self.observe_fallibility_text(
            event_or_session,
            text,
            request=request,
            session_key=session_key,
            source=source,
            commit=False,
            observed_at=observed_at,
        )

    async def reset_fallibility_state(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> bool:
        """Public API: reset one session's low-risk fallibility simulation state."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._fallibility_reset_allowed():
            return False
        await self._delete_fallibility_state(session_key)
        return True

    async def observe_emotion_text(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        text: str = "",
        *,
        phase: str = "external",
        role: str = "plugin",
        source: str = "plugin",
        request: ProviderRequest | None = None,
        context_text: str = "",
        session_key: str | None = None,
        persona_profile: PersonaProfile | None = None,
        use_llm: bool = True,
        commit: bool = True,
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        """Public API: update or simulate state from text supplied by a plugin."""
        text = str(text or "")
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        event = event_or_session if self._looks_like_event(event_or_session) else None
        base_persona_profile = persona_profile or await self._public_persona_profile(
            event,
            request,
            allow_default=event is not None,
        )
        persona_profile = await self._runtime_persona_profile(
            session_key,
            base_persona_profile,
            now=observed_at,
        )
        previous_state = await self._load_state(
            session_key,
            persona_profile,
            now=observed_at,
        )
        engine = self._engine_for_persona(persona_profile)
        observation = await self._observe_public_text(
            event=event,
            phase=phase,
            role=role,
            source=source,
            previous_state=previous_state,
            persona_profile=persona_profile,
            context_text=context_text,
            text=text,
            use_llm=use_llm,
        )
        state = engine.update(
            previous_state,
            observation,
            profile=persona_profile,
            now=observed_at,
        )
        if commit:
            await self._save_state(session_key, state)
        safety_boundary = self._safety_boundary_enabled()
        payload = emotion_state_to_public_payload(
            state,
            session_key=session_key,
            prompt_fragment=self._build_state_injection(
                state,
                safety_boundary=safety_boundary,
            ),
            include_safety=safety_boundary,
        )
        payload["observation"] = {
            "source": observation.source,
            "phase": phase,
            "role": role,
            "label": observation.label,
            "confidence": observation.confidence,
            "values": observation.values,
            "reason": observation.reason,
            "appraisal": observation.appraisal,
            "committed": commit,
        }
        payload["observation"]["relationship"] = relationship_state_to_public_payload(
            observation.appraisal,
        )
        return payload

    async def get_psychological_screening_snapshot(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        """Public API: return a non-diagnostic psychological screening snapshot."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        state = await self._load_psychological_state(session_key)
        return state.to_public_dict(session_key=session_key)

    async def get_psychological_screening_values(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> dict[str, float]:
        """Public API: return non-diagnostic psychological screening dimensions."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        state = await self._load_psychological_state(session_key)
        return {key: round(value, 6) for key, value in state.values.items()}

    async def observe_psychological_text(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        text: str = "",
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        source: str = "plugin",
        commit: bool = True,
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        """Public API: update or simulate non-diagnostic psychological screening state."""
        if commit and not self._psychological_modeling_enabled():
            return self._psychological_disabled_payload(
                self._resolve_public_session_key(
                    event_or_session,
                    request=request,
                    session_key=session_key,
                ),
            )
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        persona_profile = await self._public_runtime_persona_profile(
            event_or_session,
            request=request,
            session_key=session_key,
            observed_at=observed_at,
        )
        previous_state = await self._load_psychological_state(
            session_key,
            personality_model=self._personality_model_from_profile(persona_profile),
            now=observed_at,
        )
        observation = heuristic_psychological_observation(text, source=source)
        state = self.psychological_engine.update(
            previous_state,
            observation,
            personality_model=self._personality_model_from_profile(persona_profile),
            now=observed_at,
        )
        if commit:
            await self._save_psychological_state(session_key, state)
        payload = state.to_public_dict(session_key=session_key)
        payload["observation"] = {
            "source": observation.source,
            "confidence": observation.confidence,
            "reason": observation.reason,
            "red_flags": list(observation.red_flags),
            "committed": commit,
        }
        return payload

    async def simulate_psychological_update(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        text: str = "",
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        source: str = "plugin",
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        """Public API: simulate non-diagnostic psychological screening update."""
        return await self.observe_psychological_text(
            event_or_session,
            text,
            request=request,
            session_key=session_key,
            source=source,
            commit=False,
            observed_at=observed_at,
        )

    async def reset_psychological_screening_state(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> bool:
        """Public API: reset one session's non-diagnostic psychological state."""
        session_key = self._resolve_public_session_key(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        if not self._manual_reset_allowed():
            return False
        await self._delete_psychological_state(session_key)
        return True

    async def simulate_emotion_update(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        text: str = "",
        *,
        phase: str = "simulation",
        role: str = "plugin",
        source: str = "plugin",
        request: ProviderRequest | None = None,
        context_text: str = "",
        session_key: str | None = None,
        persona_profile: PersonaProfile | None = None,
        use_llm: bool = True,
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        """Public API: simulate a text observation without writing state."""
        return await self.observe_emotion_text(
            event_or_session,
            text,
            phase=phase,
            role=role,
            source=source,
            request=request,
            context_text=context_text,
            session_key=session_key,
            persona_profile=persona_profile,
            use_llm=use_llm,
            observed_at=observed_at,
            commit=False,
        )

    @filter.llm_tool(name="get_bot_emotion_state")
    async def get_bot_emotion_state_tool(
        self,
        event: AstrMessageEvent,
        detail: str = "summary",
        track: str = "conversation",
    ):
        """获取当前 bot 的可计算情绪状态，只读。

        Args:
            detail(string): 返回粒度，可填 summary 或 full
        """
        full = str(detail or "").strip().lower() == "full"
        track_mode = str(track or "conversation").strip().lower()
        identity = self._agent_identity(event)
        session_key = identity.conversation_id
        track_payload: dict[str, Any] = {
            "kind": "conversation",
            "conversation_id": identity.conversation_id,
        }
        if track_mode in {"speaker", "current_speaker"}:
            speaker_key = identity.speaker_track_id
            if speaker_key and self._cfg_bool("agent_speaker_relationship_tracking", True):
                session_key = speaker_key
                track_payload = {
                    "kind": "speaker",
                    "conversation_id": identity.conversation_id,
                    "speaker_id": identity.speaker_id,
                    "speaker_name": identity.speaker_name,
                }
            else:
                track_payload["requested"] = "speaker"
                track_payload["available"] = False
        snapshot = await self.get_emotion_snapshot(
            event,
            session_key=session_key,
            include_prompt_fragment=full,
            prompt_fragment_detail="full" if full else None,
        )
        snapshot["track"] = track_payload
        if not full:
            snapshot.pop("prompt_fragment", None)
            snapshot["consequences"]["notes"] = snapshot["consequences"]["notes"][:2]
        yield event.plain_result(self._llm_tool_json_result(snapshot))

    @filter.llm_tool(name="get_bot_group_atmosphere_state")
    async def get_bot_group_atmosphere_state_tool(
        self,
        event: AstrMessageEvent,
        detail: str = "summary",
    ):
        """Get the room mood / group atmosphere state, read-only."""
        full = str(detail or "").strip().lower() == "full"
        snapshot = await self.get_group_atmosphere_snapshot(
            event,
            exposure="internal" if full else "plugin_safe",
            include_prompt_fragment=full,
        )
        yield event.plain_result(self._llm_tool_json_result(snapshot))

    @filter.llm_tool(name="query_agent_state")
    async def query_agent_state_tool(
        self,
        event: AstrMessageEvent,
        state: str = "integrated",
        detail: str = "summary",
        track: str = "conversation",
        include_runtime: bool = False,
    ):
        """Unified read-only state query for the emotional agent."""
        payload = await self.query_agent_state(
            event,
            state=state,
            detail=detail,
            track=track,
            include_runtime=include_runtime,
        )
        yield event.plain_result(self._llm_tool_json_result(payload))

    @filter.llm_tool(name="simulate_bot_emotion_update")
    async def simulate_bot_emotion_update_tool(
        self,
        event: AstrMessageEvent,
        text: str,
        role: str = "assistant",
    ):
        """根据一段候选文本模拟 bot 情绪变化，不写入真实状态。

        Args:
            text(string): 需要评估的候选文本
            role(string): 文本来源，常用 user、assistant 或 plugin
        """
        snapshot = await self.simulate_emotion_update(
            event,
            text,
            phase="llm_tool_simulation",
            role=role,
            source="llm_tool",
            use_llm=True,
        )
        yield event.plain_result(self._llm_tool_json_result(snapshot))

    @filter.llm_tool(name="get_bot_humanlike_state")
    async def get_bot_humanlike_state_tool(
        self,
        event: AstrMessageEvent,
        detail: str = "summary",
    ):
        """Get the bot's simulated humanlike state, read-only."""
        full = str(detail or "").strip().lower() == "full"
        snapshot = await self.get_humanlike_snapshot(
            event,
            exposure="internal" if full else "plugin_safe",
            include_prompt_fragment=full,
        )
        yield event.plain_result(self._llm_tool_json_result(snapshot))

    @filter.llm_tool(name="get_bot_lifelike_learning_state")
    async def get_bot_lifelike_learning_state_tool(
        self,
        event: AstrMessageEvent,
        detail: str = "summary",
    ):
        """Get the bot's learned common-ground and initiative state, read-only."""
        full = str(detail or "").strip().lower() == "full"
        snapshot = await self.get_lifelike_learning_snapshot(
            event,
            exposure="internal" if full else "plugin_safe",
            include_prompt_fragment=full,
        )
        yield event.plain_result(self._llm_tool_json_result(snapshot))

    @filter.llm_tool(name="get_bot_proactive_speech_decision")
    async def get_bot_proactive_speech_decision_tool(
        self,
        event: AstrMessageEvent,
        candidate_context: str = "",
        use_llm: bool = True,
    ):
        """Decide whether the bot should proactively speak and suggest topics."""
        decision = await self.get_proactive_speech_decision(
            event,
            candidate_context=candidate_context,
            use_llm=use_llm,
        )
        yield event.plain_result(self._llm_tool_json_result(decision))

    @filter.llm_tool(name="request_bot_proactive_speech_dispatch")
    async def request_bot_proactive_speech_dispatch_tool(
        self,
        event: AstrMessageEvent,
        candidate_context: str = "",
        use_llm: bool = True,
        dry_run: bool = True,
        force: bool = False,
        message_text: str = "",
    ):
        """Request AstrBot proactive message dispatch with evidence and diagnostics."""
        result = await self.request_proactive_speech_dispatch(
            event,
            candidate_context=candidate_context,
            use_llm=use_llm,
            dry_run=dry_run,
            force=force,
            message_text=message_text,
        )
        yield event.plain_result(self._llm_tool_json_result(result))

    @filter.llm_tool(name="get_bot_personality_drift_state")
    async def get_bot_personality_drift_state_tool(
        self,
        event: AstrMessageEvent,
        detail: str = "summary",
    ):
        """Get the bot's slow real-time personality drift state, read-only."""
        full = str(detail or "").strip().lower() == "full"
        snapshot = await self.get_personality_drift_snapshot(
            event,
            exposure="internal" if full else "plugin_safe",
            include_prompt_fragment=full,
        )
        yield event.plain_result(self._llm_tool_json_result(snapshot))

    @filter.llm_tool(name="get_bot_moral_repair_state")
    async def get_bot_moral_repair_state_tool(
        self,
        event: AstrMessageEvent,
        detail: str = "summary",
    ):
        """Get the bot's moral repair and trust-repair state, read-only."""
        full = str(detail or "").strip().lower() == "full"
        snapshot = await self.get_moral_repair_snapshot(
            event,
            exposure="internal" if full else "plugin_safe",
            include_prompt_fragment=full,
        )
        yield event.plain_result(self._llm_tool_json_result(snapshot))

    @filter.llm_tool(name="get_bot_fallibility_state")
    async def get_bot_fallibility_state_tool(
        self,
        event: AstrMessageEvent,
        detail: str = "summary",
    ):
        """Get the bot's optional low-risk fallibility state, read-only."""
        full = str(detail or "").strip().lower() == "full"
        snapshot = await self.get_fallibility_snapshot(
            event,
            exposure="internal" if full else "plugin_safe",
            include_prompt_fragment=full,
        )
        yield event.plain_result(self._llm_tool_json_result(snapshot))

    @filter.llm_tool(name="get_bot_integrated_self_state")
    async def get_bot_integrated_self_state_tool(
        self,
        event: AstrMessageEvent,
        detail: str = "summary",
    ):
        """Get the bot's integrated self-state arbitration snapshot, read-only."""
        full = str(detail or "").strip().lower() == "full"
        snapshot = await self.get_integrated_self_snapshot(
            event,
            include_raw_snapshots=full,
        )
        yield event.plain_result(self._llm_tool_json_result(snapshot))

    @filter.command("emotion", alias={"emotion_state", "情绪状态"})
    async def emotion_status(self, event: AstrMessageEvent):
        """查看当前会话的多维情绪状态。"""
        persona_profile = await self._persona_profile(event, None)
        state = await self._load_state(self._session_key(event), persona_profile)
        yield event.plain_result(format_state_for_user(state))

    @filter.command("emotion_reset", alias={"情绪重置"})
    async def emotion_reset(self, event: AstrMessageEvent):
        """重置当前会话的情绪状态。"""
        if not self._manual_reset_allowed():
            yield event.plain_result("配置已关闭手动情绪重置。")
            return
        session_key = self._session_key(event)
        await self._delete_state(session_key)
        yield event.plain_result("已重置当前会话的情绪状态。")

    @filter.command("emotion_model", alias={"情绪模型"})
    async def emotion_model(self, event: AstrMessageEvent):
        """查看插件使用的核心数学模型。"""
        yield event.plain_result(
            "模型：E_t = clip(B_t + alpha_t (X_t - B_t) + coupling_t)。\n"
            "B_t = (1-gamma_p)E_(t-1)+gamma_p b_p，其中 b_p 是当前人格基线。\n"
            "delta_t 为加权欧氏惊讶度；alpha_t、gamma_p、门控和耦合强度都由运行时人格、"
            "上一轮 dynamics、置信度、惊讶度和真实时间间隔自动推导。\n"
            "维度：valence, arousal, dominance, goal_congruence, certainty, control, affiliation。"
        )

    @filter.command("emotion_effects", alias={"情绪后果"})
    async def emotion_effects(self, event: AstrMessageEvent):
        """查看当前会话的情绪后果/行动倾向状态。"""
        persona_profile = await self._persona_profile(event, None)
        state = await self._load_state(self._session_key(event), persona_profile)
        yield event.plain_result(format_consequence_for_user(state.consequences))

    @filter.command("psych_state", alias={"心理筛查", "心理状态"})
    async def psychological_screening_status(self, event: AstrMessageEvent):
        """查看当前会话的非诊断心理状态筛查。"""
        if not self._psychological_modeling_enabled():
            yield event.plain_result("非诊断心理状态筛查未启用。")
            return
        state = await self._load_psychological_state(self._session_key(event))
        yield event.plain_result(format_psychological_state_for_user(state))

    @filter.command("humanlike_state", alias={"拟人状态", "有机体状态"})
    async def humanlike_status(self, event: AstrMessageEvent):
        """View the current session's simulated humanlike state."""
        if not self._humanlike_modeling_enabled():
            yield event.plain_result("拟人化状态模拟未启用。")
            return
        state = await self._load_humanlike_state(self._session_key(event))
        yield event.plain_result(format_humanlike_state_for_user(state))

    @filter.command("humanlike_reset", alias={"拟人状态重置"})
    async def humanlike_reset(self, event: AstrMessageEvent):
        """Reset the current session's simulated humanlike state."""
        if not self._humanlike_reset_allowed():
            yield event.plain_result("配置已关闭手动拟人状态重置。")
            return
        await self._delete_humanlike_state(self._session_key(event))
        yield event.plain_result("已重置当前会话的拟人状态。")

    @filter.command("lifelike_state", alias={"生命化状态", "共同语境"})
    async def lifelike_learning_status(self, event: AstrMessageEvent):
        """View the current session's learned common-ground state."""
        if not self._lifelike_learning_enabled():
            yield event.plain_result("生命化学习状态未启用。")
            return
        state = await self._load_lifelike_learning_state(self._session_key(event))
        yield event.plain_result(format_lifelike_state_for_user(state))

    @filter.command("lifelike_reset", alias={"生命化状态重置", "共同语境重置"})
    async def lifelike_learning_reset(self, event: AstrMessageEvent):
        """Reset the current session's learned common-ground state."""
        if not self._lifelike_learning_reset_allowed():
            yield event.plain_result("配置已关闭生命化学习状态重置。")
            return
        await self._delete_lifelike_learning_state(self._session_key(event))
        yield event.plain_result("已重置当前会话的生命化学习状态。")

    @filter.command("personality_drift_state", alias={"人格漂移状态", "人格适应状态"})
    async def personality_drift_status(self, event: AstrMessageEvent):
        """View the current session's slow real-time personality drift state."""
        if not self._personality_drift_enabled():
            yield event.plain_result("人格漂移状态未启用。")
            return
        profile = await self._persona_profile(event, None)
        state = await self._load_personality_drift_state(
            self._session_key(event),
            profile,
        )
        yield event.plain_result(format_personality_drift_state_for_user(state))

    @filter.command("personality_drift_reset", alias={"人格漂移重置", "人格适应重置"})
    async def personality_drift_reset(self, event: AstrMessageEvent):
        """Reset the current session's slow personality drift state."""
        if not self._personality_drift_reset_allowed():
            yield event.plain_result("配置已关闭人格漂移重置后门。")
            return
        await self._delete_personality_drift_state(self._session_key(event))
        yield event.plain_result("已重置当前会话的人格漂移状态。")

    @filter.command("moral_repair_state", alias={"道德修复状态", "信任修复状态"})
    async def moral_repair_status(self, event: AstrMessageEvent):
        """View the current session's simulated moral repair state."""
        if not self._moral_repair_modeling_enabled():
            yield event.plain_result("道德修复状态模拟未启用。")
            return
        state = await self._load_moral_repair_state(self._session_key(event))
        yield event.plain_result(format_moral_repair_state_for_user(state))

    @filter.command("moral_repair_reset", alias={"道德修复重置", "信任修复重置"})
    async def moral_repair_reset(self, event: AstrMessageEvent):
        """Reset the current session's simulated moral repair state."""
        if not self._moral_repair_reset_allowed():
            yield event.plain_result("配置已关闭手动道德修复状态重置。")
            return
        await self._delete_moral_repair_state(self._session_key(event))
        yield event.plain_result("已重置当前会话的道德修复状态。")

    @filter.command("integrated_self", alias={"综合自我状态", "自我状态"})
    async def integrated_self_status(self, event: AstrMessageEvent):
        """View the current session's integrated self-state arbitration."""
        snapshot = await self.get_integrated_self_snapshot(event)
        yield event.plain_result(format_integrated_self_state_for_user(snapshot))

    @filter.command("shadow_diagnostics", alias={"阴影诊断", "阴影状态"})
    async def shadow_diagnostics_status(self, event: AstrMessageEvent):
        """View config-gated non-executable shadow diagnostics."""
        snapshot = await self.get_shadow_diagnostics(event)
        yield event.plain_result(json.dumps(snapshot, ensure_ascii=False))

    @filter.command("fallibility_state", alias={"瑕疵状态", "犯错模拟状态"})
    async def fallibility_status(self, event: AstrMessageEvent):
        """View the current session's low-risk fallibility simulation state."""
        if not self._fallibility_modeling_enabled():
            yield event.plain_result("瑕疵/犯错模拟状态未启用。")
            return
        state = await self._load_fallibility_state(self._session_key(event))
        yield event.plain_result(format_fallibility_state_for_user(state))

    @filter.command("fallibility_reset", alias={"瑕疵状态重置", "犯错模拟重置"})
    async def fallibility_reset(self, event: AstrMessageEvent):
        """Reset the current session's low-risk fallibility simulation state."""
        if not self._fallibility_reset_allowed():
            yield event.plain_result("配置已关闭手动瑕疵/犯错模拟状态重置。")
            return
        await self._delete_fallibility_state(self._session_key(event))
        yield event.plain_result("已重置当前会话的瑕疵/犯错模拟状态。")

    @filter.command("sylanne_memory", alias={"记忆查询", "查询记忆", "灵澜记忆"})
    async def sylanne_memory_status(
        self,
        event: AstrMessageEvent,
        query: str = "",
    ):
        """Read-only query for Sylanne's own long-term memory."""
        payload = await self.query_sylanne_memory(
            event,
            query=query,
            include_dynamics=self._cfg_bool(
                "sylanne_memory_debug_view_enabled",
                False,
            ),
        )
        yield event.plain_result(self._format_sylanne_memory_query_for_user(payload))

    async def _observe_public_text(
        self,
        *,
        event: AstrMessageEvent | None,
        phase: str,
        role: str,
        source: str,
        previous_state: EmotionState,
        persona_profile: PersonaProfile | None,
        context_text: str,
        text: str,
        use_llm: bool,
    ) -> EmotionObservation:
        current_text = f"[{role}]\n{text}" if role else text
        context_text = context_text or ""
        if source:
            context_text = (context_text + f"\n\n[external_source]\n{source}").strip()
        if (
            not use_llm
            or _INTERNAL_LLM_CALL.get()
            or not self._cfg_bool("use_llm_assessor", True)
            or event is None
        ):
            observation = heuristic_observation(
                text,
                source=source or "public_api",
                profile=persona_profile,
            )
            observation.appraisal["phase"] = phase
            observation.appraisal["role"] = role
            observation.appraisal["source"] = source
            return observation

        observation = await self._assess_emotion(
            event=event,
            phase=phase,
            previous_state=previous_state,
            persona_profile=persona_profile,
            context_text=context_text,
            current_text=current_text,
        )
        observation.source = source or observation.source
        observation.appraisal.setdefault("phase", phase)
        observation.appraisal.setdefault("role", role)
        observation.appraisal.setdefault("source", source)
        return observation

    async def _public_persona_profile(
        self,
        event: AstrMessageEvent | None,
        request: ProviderRequest | None,
        *,
        allow_default: bool = False,
    ) -> PersonaProfile | None:
        if event is not None:
            return await self._persona_profile(event, request)
        if request is None and not allow_default:
            return None
        if not PERSONA_MODELING_ENABLED:
            return PersonaProfile.default()

        persona_id = "default"
        persona_name = "default"
        pieces: list[str] = []
        has_persona_hint = False
        conversation = getattr(request, "conversation", None) if request else None
        if conversation is not None:
            conv_persona_id = getattr(conversation, "persona_id", None)
            if conv_persona_id:
                persona_id = str(conv_persona_id)
                persona_name = persona_id
                has_persona_hint = True
        if request and request.system_prompt:
            pieces.append("[request.system_prompt]\n" + str(request.system_prompt))
            has_persona_hint = True
        if not has_persona_hint and not allow_default:
            return None
        return build_persona_profile(
            persona_id=persona_id,
            name=persona_name,
            text="\n\n".join(pieces),
            source="public_api_request" if pieces else "public_api_default",
            strength=PERSONA_INFLUENCE_STRENGTH,
        )

    async def _assess_emotion(
        self,
        *,
        event: AstrMessageEvent,
        phase: str,
        previous_state: EmotionState,
        persona_profile: PersonaProfile | None,
        context_text: str,
        current_text: str,
    ) -> EmotionObservation:
        persona_profile = persona_profile or PersonaProfile.default()
        if self._cfg_bool("enable_low_signal_light_assessment", True):
            low_signal = self._low_signal_text_profile(current_text)
            if low_signal["is_low_signal"]:
                observation = heuristic_observation(
                    current_text,
                    source="low_signal",
                    profile=persona_profile,
                )
                observation.confidence = min(observation.confidence, 0.28)
                observation.appraisal.update(
                    {
                        "phase": phase,
                        "low_signal": True,
                        "signal_kind": low_signal["kind"],
                    },
                )
                observation.reason = (
                    "Low-signal turn handled by lightweight local assessment."
                )
                return observation
        if not self._cfg_bool("use_llm_assessor", True):
            return heuristic_observation(current_text, profile=persona_profile)

        provider_id = await self._provider_id(event)
        if not provider_id:
            return heuristic_observation(
                current_text,
                source="no_provider",
                profile=persona_profile,
            )

        low_reasoning_friendly = self._cfg_bool("low_reasoning_friendly_mode", False)
        max_context_chars = self._cfg_int("max_context_chars", 1600)
        if low_reasoning_friendly:
            max_context_chars = min(
                max_context_chars,
                self._cfg_int("low_reasoning_max_context_chars", 1200),
            )

        prompt = build_assessment_prompt(
            phase=phase,
            previous_state=previous_state,
            persona_profile=persona_profile,
            context_text=context_text,
            current_text=current_text,
            max_context_chars=max_context_chars,
            low_reasoning_friendly=low_reasoning_friendly,
        )
        system_prompt = (
            LOW_REASONING_ASSESSOR_SYSTEM_PROMPT
            if low_reasoning_friendly
            else ASSESSOR_SYSTEM_PROMPT
        )

        token = _INTERNAL_LLM_CALL.set(True)
        try:
            llm_resp = await self._call_internal_assessor_llm(
                provider_id=provider_id,
                prompt=prompt,
                system_prompt=system_prompt,
            )
        except asyncio.TimeoutError:
            self._log_warning(f"{PLUGIN_NAME}: LLM 情绪估计超时，启用回退估计。")
            return heuristic_observation(current_text, profile=persona_profile)
        except Exception as exc:
            self._log_warning(f"{PLUGIN_NAME}: LLM 情绪估计失败，启用回退估计: {exc}")
            return heuristic_observation(current_text, profile=persona_profile)
        finally:
            _INTERNAL_LLM_CALL.reset(token)

        observation = observation_from_llm_text(getattr(llm_resp, "completion_text", ""))
        if observation is None:
            self._log_warning(f"{PLUGIN_NAME}: 情绪估计输出不是可解析 JSON，启用回退估计。")
            return heuristic_observation(current_text, profile=persona_profile)
        return observation

    async def _provider_id(self, event: AstrMessageEvent) -> str | None:
        configured = str(self._cfg("emotion_provider_id", "") or "").strip()
        if configured:
            return configured
        if not hasattr(self, "_provider_id_cache"):
            self._provider_id_cache = {}
        umo = str(getattr(event, "unified_msg_origin", "") or "global")
        cached = self._provider_id_cache.get(umo)
        now = time.time()
        if cached and now - cached[0] <= max(
            0.0,
            self._cfg_float("provider_id_cache_ttl_seconds", 30.0),
        ):
            return cached[1]
        try:
            provider_id = await self.context.get_current_chat_provider_id(
                umo=event.unified_msg_origin,
            )
            self._provider_id_cache[umo] = (now, provider_id)
            return provider_id
        except Exception as exc:
            self._log_warning(f"{PLUGIN_NAME}: 获取当前 LLM Provider 失败: {exc}")
            return None

    async def _load_state(
        self,
        session_key: str,
        persona_profile: PersonaProfile | None = None,
        *,
        now: float | None = None,
    ) -> EmotionState:
        if session_key in self._memory_cache:
            state = self._memory_cache[session_key]
            state = self._ensure_persona_state(state, persona_profile)
            if self._passive_load_is_fresh(state, now=now):
                self._memory_cache[session_key] = state
                return state
            engine = self._engine_for_persona(persona_profile)
            decayed_state = engine.passive_update(
                state,
                profile=persona_profile,
                now=now,
            )
            if self._passive_update_changed(decayed_state, state):
                state = decayed_state
            self._memory_cache[session_key] = state
            return state
        kv_key = self._kv_key(session_key)
        try:
            data = await self.get_kv_data(kv_key, None)
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: KV 读取失败，使用内存缓存: {exc}")
            data = None
        state = EmotionState.from_dict(data)
        state = self._ensure_persona_state(state, persona_profile)
        if self._passive_load_is_fresh(state, now=now):
            self._memory_cache[session_key] = state
            return state
        engine = self._engine_for_persona(persona_profile)
        decayed_state = engine.passive_update(
            state,
            profile=persona_profile,
            now=now,
        )
        if self._passive_update_changed(decayed_state, state):
            state = decayed_state
        self._memory_cache[session_key] = state
        return state

    async def _save_state(self, session_key: str, state: EmotionState) -> None:
        self._memory_cache[session_key] = state
        try:
            await self.put_kv_data(self._kv_key(session_key), state.to_dict())
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: KV 写入失败，仅保留内存状态: {exc}")

    async def _delete_state(self, session_key: str) -> None:
        self._memory_cache.pop(session_key, None)
        try:
            await self.delete_kv_data(self._kv_key(session_key))
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: KV 删除失败: {exc}")

    async def _load_psychological_state(
        self,
        session_key: str,
        *,
        personality_model: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> PsychologicalScreeningState:
        if session_key in self._psychological_memory_cache:
            state = self._psychological_memory_cache[session_key]
            if self._passive_load_is_fresh(state, now=now):
                return state
            decayed_state = self.psychological_engine.passive_update(
                state,
                personality_model=personality_model,
                now=now,
            )
            if self._passive_update_changed(decayed_state, state):
                state = decayed_state
            self._psychological_memory_cache[session_key] = state
            return state
        try:
            data = await self.get_kv_data(self._psychological_kv_key(session_key), None)
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: 心理筛查 KV 读取失败，使用空状态: {exc}")
            data = None
        state = PsychologicalScreeningState.from_dict(data)
        if not self._passive_load_is_fresh(state, now=now):
            decayed_state = self.psychological_engine.passive_update(
                state,
                personality_model=personality_model,
                now=now,
            )
            if self._passive_update_changed(decayed_state, state):
                state = decayed_state
        self._psychological_memory_cache[session_key] = state
        return state

    async def _save_psychological_state(
        self,
        session_key: str,
        state: PsychologicalScreeningState,
    ) -> None:
        self._psychological_memory_cache[session_key] = state
        try:
            await self.put_kv_data(self._psychological_kv_key(session_key), state.to_dict())
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: 心理筛查 KV 写入失败，仅保留内存状态: {exc}")

    async def _delete_psychological_state(self, session_key: str) -> None:
        self._psychological_memory_cache.pop(session_key, None)
        try:
            await self.delete_kv_data(self._psychological_kv_key(session_key))
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: 心理筛查 KV 删除失败: {exc}")

    async def _load_humanlike_state(
        self,
        session_key: str,
        *,
        personality_model: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> HumanlikeState:
        self._ensure_runtime_state_containers()
        if session_key in self._humanlike_memory_cache:
            state = self._humanlike_memory_cache[session_key]
            if self._passive_load_is_fresh(state, now=now):
                return state
            decayed_state = self.humanlike_engine.passive_update(
                state,
                personality_model=personality_model,
                now=now,
            )
            if self._passive_update_changed(decayed_state, state):
                state = decayed_state
            self._humanlike_memory_cache[session_key] = state
            return state
        try:
            data = await self.get_kv_data(self._humanlike_kv_key(session_key), None)
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: humanlike KV read failed, using empty state: {exc}")
            data = None
        state = HumanlikeState.from_dict(data)
        if self._passive_load_is_fresh(state, now=now):
            self._humanlike_memory_cache[session_key] = state
            return state
        decayed_state = self.humanlike_engine.passive_update(
            state,
            personality_model=personality_model,
            now=now,
        )
        if self._passive_update_changed(decayed_state, state):
            state = decayed_state
        self._humanlike_memory_cache[session_key] = state
        return state

    async def _save_humanlike_state(
        self,
        session_key: str,
        state: HumanlikeState,
    ) -> None:
        self._ensure_runtime_state_containers()
        self._humanlike_memory_cache[session_key] = state
        try:
            await self.put_kv_data(self._humanlike_kv_key(session_key), state.to_dict())
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: humanlike KV write failed, keeping memory only: {exc}")

    async def _delete_humanlike_state(self, session_key: str) -> None:
        self._ensure_runtime_state_containers()
        self._humanlike_memory_cache.pop(session_key, None)
        try:
            await self.delete_kv_data(self._humanlike_kv_key(session_key))
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: humanlike KV delete failed: {exc}")

    async def _load_lifelike_learning_state(
        self,
        session_key: str,
        *,
        now: float | None = None,
    ) -> LifelikeLearningState:
        self._ensure_runtime_state_containers()
        if session_key in self._lifelike_learning_memory_cache:
            state = self._lifelike_learning_memory_cache[session_key]
            if self._passive_load_is_fresh(state, now=now):
                return state
            decayed_state = self.lifelike_learning_engine.passive_update(
                state,
                now=now,
            )
            if self._passive_update_changed(decayed_state, state):
                state = decayed_state
            self._lifelike_learning_memory_cache[session_key] = state
            return state
        try:
            data = await self.get_kv_data(
                self._lifelike_learning_kv_key(session_key),
                None,
            )
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: lifelike learning KV read failed, using empty state: {exc}")
            data = None
        state = LifelikeLearningState.from_dict(data)
        if self._passive_load_is_fresh(state, now=now):
            self._lifelike_learning_memory_cache[session_key] = state
            return state
        decayed_state = self.lifelike_learning_engine.passive_update(state, now=now)
        if self._passive_update_changed(decayed_state, state):
            state = decayed_state
        self._lifelike_learning_memory_cache[session_key] = state
        return state

    async def _save_lifelike_learning_state(
        self,
        session_key: str,
        state: LifelikeLearningState,
    ) -> None:
        self._ensure_runtime_state_containers()
        self._lifelike_learning_memory_cache[session_key] = state
        try:
            await self.put_kv_data(
                self._lifelike_learning_kv_key(session_key),
                state.to_dict(),
            )
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: lifelike learning KV write failed, keeping memory only: {exc}")

    async def _delete_lifelike_learning_state(self, session_key: str) -> None:
        self._ensure_runtime_state_containers()
        self._lifelike_learning_memory_cache.pop(session_key, None)
        try:
            await self.delete_kv_data(self._lifelike_learning_kv_key(session_key))
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: lifelike learning KV delete failed: {exc}")

    async def _load_personality_drift_state(
        self,
        session_key: str,
        profile: PersonaProfile | None = None,
        *,
        now: float | None = None,
    ) -> PersonalityDriftState:
        self._ensure_runtime_state_containers()
        fingerprint = profile.fingerprint if profile is not None else "default"
        if session_key in self._personality_drift_memory_cache:
            state = self._personality_drift_memory_cache[session_key]
            return self._passive_personality_drift_state(
                state,
                fingerprint,
                now=now,
            )
        try:
            data = await self.get_kv_data(
                self._personality_drift_kv_key(session_key),
                None,
            )
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: personality drift KV read failed, using empty state: {exc}")
            data = None
        state = PersonalityDriftState.from_dict(data)
        state = self._passive_personality_drift_state(state, fingerprint, now=now)
        self._personality_drift_memory_cache[session_key] = state
        return state

    def _passive_personality_drift_state(
        self,
        state: PersonalityDriftState,
        fingerprint: str,
        *,
        now: float | None = None,
    ) -> PersonalityDriftState:
        if state.persona_fingerprint != str(fingerprint or "default"):
            return self.personality_drift_engine.passive_update(
                state,
                persona_fingerprint=fingerprint,
                now=now,
            )
        observed_at = self._observed_now() if now is None else float(now)
        elapsed = max(0.0, observed_at - state.updated_at)
        if elapsed <= 1.0:
            return state
        return self.personality_drift_engine.passive_update(
            state,
            persona_fingerprint=fingerprint,
            now=observed_at,
        )

    def _ensure_runtime_state_containers(self) -> None:
        if not hasattr(self, "humanlike_engine"):
            self.humanlike_engine = HumanlikeEngine(
                self._build_humanlike_parameters(),
            )
        if not hasattr(self, "lifelike_learning_engine"):
            self.lifelike_learning_engine = LifelikeLearningEngine(
                self._build_lifelike_learning_parameters(),
            )
        if not hasattr(self, "personality_drift_engine"):
            self.personality_drift_engine = PersonalityDriftEngine(
                self._build_personality_drift_parameters(),
            )
        if not hasattr(self, "moral_repair_engine"):
            self.moral_repair_engine = MoralRepairEngine(
                self._build_moral_repair_parameters(),
            )
        if not hasattr(self, "fallibility_engine"):
            self.fallibility_engine = FallibilityEngine(
                self._build_fallibility_parameters(),
            )
        if not hasattr(self, "group_atmosphere_engine"):
            self.group_atmosphere_engine = GroupAtmosphereEngine(
                self._build_group_atmosphere_parameters(),
            )
        if not hasattr(self, "_memory_cache"):
            self._memory_cache = {}
        if not hasattr(self, "_psychological_memory_cache"):
            self._psychological_memory_cache = {}
        if not hasattr(self, "_humanlike_memory_cache"):
            self._humanlike_memory_cache = {}
        if not hasattr(self, "_lifelike_learning_memory_cache"):
            self._lifelike_learning_memory_cache = {}
        if not hasattr(self, "_personality_drift_memory_cache"):
            self._personality_drift_memory_cache = {}
        if not hasattr(self, "_moral_repair_memory_cache"):
            self._moral_repair_memory_cache = {}
        if not hasattr(self, "_fallibility_memory_cache"):
            self._fallibility_memory_cache = {}
        if not hasattr(self, "_group_atmosphere_memory_cache"):
            self._group_atmosphere_memory_cache = {}
        if not hasattr(self, "_sylanne_memory_cache"):
            self._sylanne_memory_cache = {}

    def _passive_load_is_fresh(self, state: Any, *, now: float | None = None) -> bool:
        updated_at = getattr(state, "updated_at", None)
        try:
            observed_at = self._observed_now() if now is None else float(now)
            elapsed = observed_at - float(updated_at)
        except (TypeError, ValueError):
            return False
        return elapsed <= max(0.0, self._cfg_float("passive_load_fresh_seconds", 1.0))

    def _passive_update_changed(self, updated: Any, previous: Any) -> bool:
        if updated is not previous:
            return True
        try:
            return float(getattr(updated, "updated_at")) != float(
                getattr(previous, "updated_at"),
            )
        except (TypeError, ValueError):
            return False

    def _personality_drift_changed(
        self,
        updated: PersonalityDriftState,
        previous: PersonalityDriftState,
    ) -> bool:
        return (
            updated.evidence_count != previous.evidence_count
            or updated.persona_fingerprint != previous.persona_fingerprint
            or updated.trait_offsets != previous.trait_offsets
            or updated.trait_confidence != previous.trait_confidence
            or updated.flags != previous.flags
        )

    async def _save_personality_drift_state(
        self,
        session_key: str,
        state: PersonalityDriftState,
    ) -> None:
        self._ensure_runtime_state_containers()
        self._personality_drift_memory_cache[session_key] = state
        try:
            await self.put_kv_data(
                self._personality_drift_kv_key(session_key),
                state.to_dict(),
            )
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: personality drift KV write failed, keeping memory only: {exc}")

    async def _delete_personality_drift_state(self, session_key: str) -> None:
        self._ensure_runtime_state_containers()
        self._personality_drift_memory_cache.pop(session_key, None)
        try:
            await self.delete_kv_data(self._personality_drift_kv_key(session_key))
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: personality drift KV delete failed: {exc}")

    async def _load_moral_repair_state(
        self,
        session_key: str,
        *,
        personality_model: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> MoralRepairState:
        if session_key in self._moral_repair_memory_cache:
            state = self._moral_repair_memory_cache[session_key]
            if self._passive_load_is_fresh(state, now=now):
                return state
            decayed_state = self.moral_repair_engine.passive_update(
                state,
                personality_model=personality_model,
                now=now,
            )
            if self._passive_update_changed(decayed_state, state):
                state = decayed_state
            self._moral_repair_memory_cache[session_key] = state
            return state
        try:
            data = await self.get_kv_data(self._moral_repair_kv_key(session_key), None)
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: moral repair KV read failed, using empty state: {exc}")
            data = None
        state = MoralRepairState.from_dict(data)
        if self._passive_load_is_fresh(state, now=now):
            self._moral_repair_memory_cache[session_key] = state
            return state
        decayed_state = self.moral_repair_engine.passive_update(
            state,
            personality_model=personality_model,
            now=now,
        )
        if self._passive_update_changed(decayed_state, state):
            state = decayed_state
        self._moral_repair_memory_cache[session_key] = state
        return state

    async def _save_moral_repair_state(
        self,
        session_key: str,
        state: MoralRepairState,
    ) -> None:
        self._moral_repair_memory_cache[session_key] = state
        try:
            await self.put_kv_data(self._moral_repair_kv_key(session_key), state.to_dict())
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: moral repair KV write failed, keeping memory only: {exc}")

    async def _delete_moral_repair_state(self, session_key: str) -> None:
        self._moral_repair_memory_cache.pop(session_key, None)
        try:
            await self.delete_kv_data(self._moral_repair_kv_key(session_key))
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: moral repair KV delete failed: {exc}")

    async def _load_fallibility_state(
        self,
        session_key: str,
        *,
        personality_model: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> FallibilityState:
        if session_key in self._fallibility_memory_cache:
            state = self._fallibility_memory_cache[session_key]
            if self._passive_load_is_fresh(state, now=now):
                return state
            decayed_state = self.fallibility_engine.passive_update(
                state,
                personality_model=personality_model,
                now=now,
            )
            if self._passive_update_changed(decayed_state, state):
                state = decayed_state
            self._fallibility_memory_cache[session_key] = state
            return state
        try:
            data = await self.get_kv_data(self._fallibility_kv_key(session_key), None)
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: fallibility KV read failed, using empty state: {exc}")
            data = None
        state = FallibilityState.from_dict(data)
        if self._passive_load_is_fresh(state, now=now):
            self._fallibility_memory_cache[session_key] = state
            return state
        decayed_state = self.fallibility_engine.passive_update(
            state,
            personality_model=personality_model,
            now=now,
        )
        if self._passive_update_changed(decayed_state, state):
            state = decayed_state
        self._fallibility_memory_cache[session_key] = state
        return state

    async def _save_fallibility_state(
        self,
        session_key: str,
        state: FallibilityState,
    ) -> None:
        self._fallibility_memory_cache[session_key] = state
        try:
            await self.put_kv_data(self._fallibility_kv_key(session_key), state.to_dict())
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: fallibility KV write failed, keeping memory only: {exc}")

    async def _delete_fallibility_state(self, session_key: str) -> None:
        self._fallibility_memory_cache.pop(session_key, None)
        try:
            await self.delete_kv_data(self._fallibility_kv_key(session_key))
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: fallibility KV delete failed: {exc}")

    async def _load_group_atmosphere_state(
        self,
        session_key: str,
        *,
        personality_model: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> GroupAtmosphereState:
        if session_key in self._group_atmosphere_memory_cache:
            state = self._group_atmosphere_memory_cache[session_key]
            if self._passive_load_is_fresh(state, now=now):
                return state
            decayed_state = self.group_atmosphere_engine.passive_update(
                state,
                personality_model=personality_model,
                now=now,
            )
            if self._passive_update_changed(decayed_state, state):
                state = decayed_state
            self._group_atmosphere_memory_cache[session_key] = state
            return state
        try:
            data = await self.get_kv_data(
                self._group_atmosphere_kv_key(session_key),
                None,
            )
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: group atmosphere KV read failed, using empty state: {exc}")
            data = None
        state = GroupAtmosphereState.from_dict(data)
        if self._passive_load_is_fresh(state, now=now):
            self._group_atmosphere_memory_cache[session_key] = state
            return state
        decayed_state = self.group_atmosphere_engine.passive_update(
            state,
            personality_model=personality_model,
            now=now,
        )
        if self._passive_update_changed(decayed_state, state):
            state = decayed_state
        self._group_atmosphere_memory_cache[session_key] = state
        return state

    async def _save_group_atmosphere_state(
        self,
        session_key: str,
        state: GroupAtmosphereState,
    ) -> None:
        self._group_atmosphere_memory_cache[session_key] = state
        try:
            await self.put_kv_data(
                self._group_atmosphere_kv_key(session_key),
                state.to_dict(),
            )
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: group atmosphere KV write failed, keeping memory only: {exc}")

    async def _delete_group_atmosphere_state(self, session_key: str) -> None:
        self._group_atmosphere_memory_cache.pop(session_key, None)
        try:
            await self.delete_kv_data(self._group_atmosphere_kv_key(session_key))
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: group atmosphere KV delete failed: {exc}")

    async def _load_sylanne_memory_state(
        self,
        session_key: str,
        *,
        now: float | None = None,
    ) -> SylanneMemoryState:
        observed_now = self._observed_now() if now is None else float(now)
        self._ensure_runtime_state_containers()
        if session_key in self._sylanne_memory_cache:
            state = self._sylanne_memory_cache[session_key]
            before = state.to_dict()
            decayed_state = apply_memory_time_decay(state, now=observed_now)
            if decayed_state.to_dict() != before:
                await self._save_sylanne_memory_state(session_key, decayed_state)
                return decayed_state
            return state
        try:
            data = await self.get_kv_data(
                self._sylanne_memory_kv_key(session_key),
                None,
            )
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: Sylanne memory KV read failed, using empty state: {exc}")
            data = None
        state = SylanneMemoryState.from_dict(data)
        before = state.to_dict()
        state = apply_memory_time_decay(state, now=observed_now)
        self._sylanne_memory_cache[session_key] = state
        if data is not None and state.to_dict() != before:
            await self._save_sylanne_memory_state(session_key, state)
        return state

    async def _save_sylanne_memory_state(
        self,
        session_key: str,
        state: SylanneMemoryState,
    ) -> None:
        self._ensure_runtime_state_containers()
        self._sylanne_memory_cache[session_key] = state
        try:
            await self.put_kv_data(
                self._sylanne_memory_kv_key(session_key),
                state.to_dict(),
            )
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: Sylanne memory KV write failed, keeping memory only: {exc}")

    async def _delete_sylanne_memory_state(self, session_key: str) -> None:
        self._ensure_runtime_state_containers()
        self._sylanne_memory_cache.pop(session_key, None)
        try:
            await self.delete_kv_data(self._sylanne_memory_kv_key(session_key))
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: Sylanne memory KV delete failed: {exc}")

    async def _observe_sylanne_memory_event_if_enabled(
        self,
        session_key: str,
        text: str,
        *,
        speaker_id: str = "",
        emotion_state: EmotionState | None = None,
        personality_drift_state: PersonalityDriftState | None = None,
        lifelike_learning_state: LifelikeLearningState | None = None,
        group_atmosphere_state: GroupAtmosphereState | None = None,
        observed_at: float | None = None,
    ) -> None:
        if not self._sylanne_memory_enabled():
            return
        text = str(text or "").strip()
        if not text:
            return
        now = self._observed_now() if observed_at is None else float(observed_at)
        try:
            state = await self._load_sylanne_memory_state(session_key, now=now)
            state = observe_memory_event(
                state,
                text=text,
                session_key=session_key,
                speaker_id=speaker_id,
                emotion_snapshot=(
                    emotion_state.to_public_dict(
                        session_key=session_key,
                        include_safety=self._safety_boundary_enabled(),
                    )
                    if emotion_state is not None
                    else None
                ),
                personality_drift_snapshot=(
                    personality_drift_state.to_public_dict(
                        session_key=session_key,
                        exposure="plugin_safe",
                    )
                    if personality_drift_state is not None
                    else None
                ),
                lifelike_snapshot=(
                    lifelike_learning_state.to_public_dict(
                        session_key=session_key,
                        exposure="plugin_safe",
                    )
                    if lifelike_learning_state is not None
                    else None
                ),
                group_atmosphere_snapshot=(
                    group_atmosphere_state.to_public_dict(
                        session_key=session_key,
                        exposure="plugin_safe",
                    )
                    if group_atmosphere_state is not None
                    else None
                ),
                now=now,
            )
            await self._save_sylanne_memory_state(session_key, state)
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: Sylanne memory observe failed: {exc}")

    def _build_parameters(self) -> EmotionParameters:
        return EmotionParameters()

    def _build_psychological_parameters(self) -> PsychologicalScreeningParameters:
        return PsychologicalScreeningParameters()

    def _build_humanlike_parameters(self) -> HumanlikeParameters:
        return HumanlikeParameters()

    def _build_lifelike_learning_parameters(self) -> LifelikeLearningParameters:
        return LifelikeLearningParameters()

    def _build_personality_drift_parameters(self) -> PersonalityDriftParameters:
        return PersonalityDriftParameters()

    def _build_moral_repair_parameters(self) -> MoralRepairParameters:
        return MoralRepairParameters()

    def _build_fallibility_parameters(self) -> FallibilityParameters:
        return FallibilityParameters()

    def _build_group_atmosphere_parameters(self) -> GroupAtmosphereParameters:
        return GroupAtmosphereParameters()

    def _engine_for_persona(self, profile: PersonaProfile | None) -> EmotionEngine:
        if profile is None or not PERSONA_MODELING_ENABLED:
            return self.engine
        if not hasattr(self, "_engine_cache"):
            self._engine_cache = {}
        cache_key = self._persona_engine_cache_key(profile)
        cached = self._engine_cache.get(cache_key)
        if cached is not None:
            return cached
        parameters = apply_persona_to_parameters(self.base_parameters, profile)
        engine = EmotionEngine(parameters=parameters, baseline=profile.baseline)
        self._engine_cache[cache_key] = engine
        if len(self._engine_cache) > 16:
            first_key = next(iter(self._engine_cache))
            self._engine_cache.pop(first_key, None)
        return engine

    def _personality_model_from_profile(
        self,
        profile: PersonaProfile | None,
    ) -> dict[str, Any] | None:
        if profile is None or not PERSONA_MODELING_ENABLED:
            return None
        model = getattr(profile, "personality_model", None)
        return model if isinstance(model, dict) else None

    def _persona_engine_cache_key(self, profile: PersonaProfile) -> str:
        drift = profile.personality_model.get("adaptive_drift")
        if not isinstance(drift, dict):
            return profile.fingerprint
        payload = {
            "fingerprint": profile.fingerprint,
            "trait_offsets": drift.get("trait_offsets"),
            "trait_confidence": drift.get("trait_confidence"),
            "strength": drift.get("strength"),
            "updated_at": drift.get("updated_at"),
        }
        digest = sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8"),
        ).hexdigest()[:16]
        return f"{profile.fingerprint}:drift:{digest}"

    def _safety_boundary_enabled(self) -> bool:
        return self._cfg_bool("enable_safety_boundary", True)

    def _shadow_action_blocking_enabled(self) -> bool:
        return self._cfg_bool(
            "block_deception_manipulation_evasion_actions",
            True,
        )

    def _shadow_diagnostics_enabled(self) -> bool:
        return self._cfg_bool("enable_shadow_diagnostics", False)

    def _manual_reset_allowed(self) -> bool:
        return self._cfg_bool("allow_emotion_reset_backdoor", True)

    def _psychological_modeling_enabled(self) -> bool:
        return self._cfg_bool("enable_psychological_screening", False)

    def _psychological_disabled_payload(self, session_key: str) -> dict[str, Any]:
        state = PsychologicalScreeningState.initial()
        payload = psychological_state_to_public_payload(state, session_key=session_key)
        payload["enabled"] = False
        payload["reason"] = "enable_psychological_screening is false"
        return payload

    def _humanlike_modeling_enabled(self) -> bool:
        return True

    def _humanlike_injection_enabled(self) -> bool:
        return True

    def _humanlike_reset_allowed(self) -> bool:
        return self._cfg_bool("allow_humanlike_reset_backdoor", True)

    def _lifelike_learning_enabled(self) -> bool:
        return True

    def _lifelike_learning_injection_enabled(self) -> bool:
        return True

    def _lifelike_learning_reset_allowed(self) -> bool:
        return self._cfg_bool("allow_lifelike_learning_reset_backdoor", True)

    def _personality_drift_enabled(self) -> bool:
        return True

    def _personality_drift_injection_enabled(self) -> bool:
        return True

    def _personality_drift_reset_allowed(self) -> bool:
        return self._cfg_bool("allow_personality_drift_reset_backdoor", True)

    def _moral_repair_modeling_enabled(self) -> bool:
        return self._cfg_bool("enable_moral_repair_state", False)

    def _moral_repair_injection_enabled(self) -> bool:
        return True

    def _moral_repair_reset_allowed(self) -> bool:
        return self._cfg_bool("allow_moral_repair_reset_backdoor", True)

    def _fallibility_modeling_enabled(self) -> bool:
        return self._cfg_bool("enable_fallibility_state", False)

    def _fallibility_injection_enabled(self) -> bool:
        return True

    def _fallibility_reset_allowed(self) -> bool:
        return self._cfg_bool("allow_fallibility_reset_backdoor", True)

    def _group_atmosphere_modeling_enabled(self) -> bool:
        return True

    def _group_atmosphere_injection_enabled(self) -> bool:
        return True

    def _sylanne_memory_enabled(self) -> bool:
        config = getattr(self, "config", {}) or {}
        value = (
            config.get("enable_sylanne_memory", True)
            if isinstance(config, dict)
            else True
        )
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() not in {"0", "false", "no", "off"}

    def _group_atmosphere_applies(
        self,
        identity: ConversationIdentity | None,
    ) -> bool:
        if identity is None:
            return False
        if identity.group_id:
            return True
        return bool(identity.has_speaker and str(identity.conversation_id).strip())

    def _agent_trail_enabled(self) -> bool:
        return self._cfg_bool("enable_agent_causal_trail", True)

    def _integrated_self_degradation_profile(self) -> str:
        profile = str(
            self._cfg("integrated_self_degradation_profile", "balanced") or "balanced",
        ).strip().lower()
        if profile in {"full", "balanced", "minimal"}:
            return profile
        return "balanced"

    def _moral_repair_disabled_payload(
        self,
        session_key: str,
        *,
        exposure: str = "plugin_safe",
        include_prompt_fragment: bool = False,
    ) -> dict[str, Any]:
        state = MoralRepairState.initial()
        payload = moral_repair_state_to_public_payload(
            state,
            session_key=session_key,
            exposure=exposure,
            safety_boundary=self._safety_boundary_enabled(),
            action_blocking=self._shadow_action_blocking_enabled(),
        )
        payload["enabled"] = False
        payload["reason"] = "enable_moral_repair_state is false"
        for internal_key in (
            "values",
            "dimensions",
            "trajectory",
            "confidence",
            "last_reason",
        ):
            payload.pop(internal_key, None)
        if include_prompt_fragment:
            payload["prompt_fragment"] = ""
        return payload

    def _lifelike_learning_disabled_payload(
        self,
        session_key: str,
        *,
        exposure: str = "plugin_safe",
        include_prompt_fragment: bool = False,
    ) -> dict[str, Any]:
        state = LifelikeLearningState.initial()
        payload = lifelike_state_to_public_payload(
            state,
            session_key=session_key,
            exposure=exposure,
        )
        payload["enabled"] = False
        payload["reason"] = "enable_lifelike_learning is false"
        payload["initiative_policy"] = {
            "schema_version": "astrbot.lifelike_initiative_policy.v1",
            "kind": "lifelike_initiative_policy",
            "action": "brief_ack",
            "initiative_score": 0.0,
            "silence_score": 0.0,
            "common_ground": 0.0,
            "boundary": 0.0,
            "uncertain_terms": [],
            "flags": ["lifelike_learning_disabled"],
            "allowed_actions": ["brief_acknowledgement", "follow_user_lead"],
        }
        for internal_key in (
            "values",
            "dimensions",
            "trajectory",
            "lexicon",
            "user_profile",
            "last_observation",
        ):
            payload.pop(internal_key, None)
        if include_prompt_fragment:
            payload["prompt_fragment"] = ""
        return payload

    def _personality_drift_disabled_payload(
        self,
        session_key: str,
        profile: PersonaProfile | None = None,
        *,
        exposure: str = "plugin_safe",
        include_prompt_fragment: bool = False,
    ) -> dict[str, Any]:
        state = PersonalityDriftState.initial(
            persona_fingerprint=profile.fingerprint if profile is not None else "default",
        )
        payload = personality_drift_state_to_public_payload(
            state,
            session_key=session_key,
            exposure=exposure,
        )
        payload["enabled"] = False
        payload["reason"] = "enable_personality_drift is false"
        for internal_key in (
            "trait_offsets",
            "trait_confidence",
            "trajectory",
            "last_event_summary",
            "created_at",
        ):
            payload.pop(internal_key, None)
        if include_prompt_fragment:
            payload["prompt_fragment"] = ""
        return payload

    def _fallibility_disabled_payload(
        self,
        session_key: str,
        *,
        exposure: str = "plugin_safe",
        include_prompt_fragment: bool = False,
    ) -> dict[str, Any]:
        state = FallibilityState.initial()
        payload = fallibility_state_to_public_payload(
            state,
            session_key=session_key,
            exposure=exposure,
            safety_boundary=self._safety_boundary_enabled(),
            action_blocking=self._shadow_action_blocking_enabled(),
        )
        payload["enabled"] = False
        payload["reason"] = "enable_fallibility_state is false"
        for internal_key in (
            "values",
            "dimensions",
            "trajectory",
            "confidence",
            "last_reason",
        ):
            payload.pop(internal_key, None)
        if include_prompt_fragment:
            payload["prompt_fragment"] = ""
        return payload

    def _group_atmosphere_disabled_payload(
        self,
        session_key: str,
        *,
        exposure: str = "plugin_safe",
        include_prompt_fragment: bool = False,
    ) -> dict[str, Any]:
        state = GroupAtmosphereState.initial()
        payload = group_atmosphere_state_to_public_payload(
            state,
            session_key=session_key,
            exposure=exposure,
        )
        payload["enabled"] = False
        payload["reason"] = "enable_group_atmosphere_state is false"
        for internal_key in (
            "values",
            "dimensions",
            "trajectory",
            "confidence",
            "last_reason",
        ):
            payload.pop(internal_key, None)
        if include_prompt_fragment:
            payload["prompt_fragment"] = ""
        return payload

    def _humanlike_disabled_payload(
        self,
        session_key: str,
        *,
        exposure: str = "plugin_safe",
        include_prompt_fragment: bool = False,
    ) -> dict[str, Any]:
        state = HumanlikeState.initial()
        payload = humanlike_state_to_public_payload(
            state,
            session_key=session_key,
            exposure=exposure,
            safety_boundary=self._safety_boundary_enabled(),
        )
        payload["enabled"] = False
        payload["reason"] = "enable_humanlike_state is false"
        for internal_key in (
            "values",
            "dimensions",
            "trajectory",
            "confidence",
            "last_reason",
        ):
            payload.pop(internal_key, None)
        if include_prompt_fragment:
            payload["prompt_fragment"] = ""
        return payload

    def _build_state_injection(
        self,
        state: EmotionState,
        *,
        safety_boundary: bool | None = None,
        decision: _StateInjectionDecision | None = None,
    ) -> str:
        resolved_safety_boundary = (
            self._safety_boundary_enabled()
            if safety_boundary is None
            else safety_boundary
        )
        detail = decision.primary_detail if decision is not None else self._state_injection_detail()
        if detail == "compact":
            return self._build_compact_state_injection(
                state,
                safety_boundary=resolved_safety_boundary,
            )
        return build_state_injection(
            state,
            safety_boundary=resolved_safety_boundary,
        )

    def _build_state_injection_for_session(
        self,
        session_key: str,
        state: EmotionState,
        *,
        safety_boundary: bool | None = None,
        commit_snapshot: bool = True,
        decision: _StateInjectionDecision | None = None,
    ) -> str:
        decision = decision or self._state_injection_decision(session_key, state)
        mode = decision.compact_mode
        if decision.primary_detail != "compact" or mode != "diff":
            return self._build_state_injection(
                state,
                safety_boundary=safety_boundary,
                decision=decision,
            )
        return self._build_diff_state_injection(
            session_key,
            state,
            safety_boundary=(
                self._safety_boundary_enabled()
                if safety_boundary is None
                else safety_boundary
            ),
            commit_snapshot=commit_snapshot,
            decision=decision,
        )

    def _build_state_injection_for_detail(
        self,
        state: EmotionState,
        detail: str | None,
        *,
        safety_boundary: bool,
    ) -> str:
        if str(detail or "").strip().lower() == "full":
            return build_state_injection(
                state,
                safety_boundary=safety_boundary,
            )
        if str(detail or "").strip().lower() == "compact":
            return self._build_compact_state_injection(
                state,
                safety_boundary=safety_boundary,
            )
        return self._build_state_injection(
            state,
            safety_boundary=safety_boundary,
        )

    def _state_injection_detail(self) -> str:
        if not self._runtime_parameter_debug_override_enabled():
            return "compact"
        detail = str(
            self._debug_cfg("state_injection_detail", "compact") or "compact",
        ).strip().lower()
        if detail in {"compact", "full"}:
            return detail
        return "compact"

    def _auxiliary_state_injection_detail(self) -> str:
        if not self._runtime_parameter_debug_override_enabled():
            return "compact"
        detail = str(
            self._debug_cfg("auxiliary_state_injection_detail", "compact") or "compact",
        ).strip().lower()
        if detail in {"compact", "full", "off"}:
            return detail
        return "compact"

    def _build_compact_state_injection(
        self,
        state: EmotionState,
        *,
        safety_boundary: bool,
    ) -> str:
        values = state.values
        active_effects = ", ".join(
            sorted(state.consequences.active_effects.keys())[:4],
        ) or "none"
        relationship = state.last_appraisal.get("relationship_decision")
        decision = "none"
        if isinstance(relationship, dict):
            decision = str(relationship.get("decision") or "none")
        safety = (
            "Safety: keep boundaries mild; never shame, threaten, manipulate, or refuse necessary help."
            if safety_boundary
            else "Safety boundary relaxed by config; still keep replies civil and useful."
        )
        return (
            '<bot_emotion_state private="true" detail="compact">\n'
            "Use this as a lightweight style-control signal, not as text to reveal.\n"
            f"label={state.label}; confidence={state.confidence:.2f}; "
            f"valence={values.get('valence', 0.0):.2f}; "
            f"arousal={values.get('arousal', 0.0):.2f}; "
            f"dominance={values.get('dominance', 0.0):.2f}; "
            f"affiliation={values.get('affiliation', 0.0):.2f}; "
            f"certainty={values.get('certainty', 0.0):.2f}; "
            f"control={values.get('control', 0.0):.2f}; "
            f"relationship_decision={decision}; active_effects={active_effects}.\n"
            f"{safety}\n"
            'For details, call get_bot_emotion_state(detail="full") only when needed.\n'
            "</bot_emotion_state>"
        )

    def _state_injection_decision(
        self,
        session_key: str,
        state: EmotionState,
        *,
        budget: _StateInjectionBudget | None = None,
    ) -> _StateInjectionDecision:
        if self._runtime_parameter_debug_override_enabled():
            detail = str(
                self._debug_cfg("state_injection_detail", "compact") or "compact",
            ).strip().lower()
            compact_mode = str(
                self._debug_cfg("state_injection_compact_mode", "snapshot")
                or "snapshot",
            ).strip().lower()
            auxiliary = str(
                self._debug_cfg("auxiliary_state_injection_detail", "compact")
                or "compact",
            ).strip().lower()
            return _StateInjectionDecision(
                primary_detail=detail if detail in {"compact", "full"} else "compact",
                compact_mode=compact_mode if compact_mode in {"snapshot", "diff"} else "snapshot",
                auxiliary_detail=(
                    auxiliary if auxiliary in {"compact", "full", "off"} else "compact"
                ),
                emotion_diff_threshold=max(
                    0.0,
                    self._debug_cfg_float("state_injection_diff_threshold", 0.08),
                ),
                group_diff_threshold=max(
                    0.0,
                    self._debug_cfg_float(
                        "group_atmosphere_injection_diff_threshold",
                        0.08,
                    ),
                ),
                force_every_turns=max(
                    1,
                    self._debug_cfg_int("state_injection_diff_force_every_turns", 6),
                ),
                reasons=["debug_config_override"],
            )
        values = state.values if state is not None else {}
        arousal = abs(self._as_float_value(values.get("arousal"), 0.0))
        valence = self._as_float_value(values.get("valence"), 0.0)
        affiliation = self._as_float_value(values.get("affiliation"), 0.0)
        active_effects = len(getattr(state.consequences, "active_effects", {}) or {})
        relationship = state.last_appraisal.get("relationship_decision")
        relationship_decision = ""
        if isinstance(relationship, dict):
            relationship_decision = str(relationship.get("decision") or "")
        pressure = 0.0
        if budget is not None and budget.effective_total_budget > 0:
            pressure = self._clamp01(
                budget.request_chars_before / max(1, budget.effective_total_budget),
            )
        salience = self._clamp01(
            0.28 * arousal
            + 0.18 * abs(valence)
            + 0.14 * max(0.0, affiliation)
            + 0.13 * min(active_effects, 4) / 4.0
            + (0.18 if relationship_decision in {"cold_war", "confront", "repair"} else 0.0)
            - 0.16 * pressure,
        )
        reasons = [
            f"salience={salience:.2f}",
            f"budget_pressure={pressure:.2f}",
        ]
        primary_detail = "compact"
        compact_mode = "diff" if pressure >= 0.26 or salience < 0.34 else "snapshot"
        auxiliary_detail = "compact"
        if salience >= 0.74 and pressure < 0.36:
            primary_detail = "full"
            auxiliary_detail = "compact"
            compact_mode = "snapshot"
            reasons.append("high_salience_full_primary")
        elif pressure >= 0.72:
            auxiliary_detail = "off"
            compact_mode = "diff"
            reasons.append("high_budget_pressure_auxiliary_off")
        elif salience >= 0.56 and pressure < 0.42:
            auxiliary_detail = "compact"
            compact_mode = "snapshot"
            reasons.append("medium_salience_snapshot")
        else:
            reasons.append("low_or_ordinary_salience_diff_compact")
        threshold = max(0.035, min(0.16, 0.06 + 0.08 * (1.0 - salience) + 0.04 * pressure))
        group_threshold = max(0.035, min(0.16, threshold + 0.01))
        force_every = int(round(4 + 5 * pressure + 3 * (1.0 - salience)))
        force_every = max(3, min(10, force_every))
        return _StateInjectionDecision(
            primary_detail=primary_detail,
            compact_mode=compact_mode,
            auxiliary_detail=auxiliary_detail,
            emotion_diff_threshold=round(threshold, 6),
            group_diff_threshold=round(group_threshold, 6),
            force_every_turns=force_every,
            reasons=reasons,
        )

    def _build_diff_state_injection(
        self,
        session_key: str,
        state: EmotionState,
        *,
        safety_boundary: bool,
        commit_snapshot: bool = True,
        decision: _StateInjectionDecision | None = None,
    ) -> str:
        cache = getattr(self, "_state_injection_snapshot_cache", None)
        if cache is None:
            cache = {}
            self._state_injection_snapshot_cache = cache
        current = self._state_injection_snapshot(state)
        previous = cache.get(session_key)
        if commit_snapshot:
            cache[session_key] = current
        decision = decision or self._state_injection_decision(session_key, state)
        threshold = max(0.0, decision.emotion_diff_threshold)
        force_every = max(1, decision.force_every_turns)
        if previous is None or (state.turns > 0 and state.turns % force_every == 0):
            return self._build_compact_state_injection(
                state,
                safety_boundary=safety_boundary,
            )
        deltas = {
            key: round(current["values"].get(key, 0.0) - previous["values"].get(key, 0.0), 3)
            for key in current["values"]
        }
        changed = {
            key: value
            for key, value in deltas.items()
            if abs(value) >= threshold
        }
        label_changed = current["label"] != previous.get("label")
        decision_changed = current["relationship_decision"] != previous.get(
            "relationship_decision",
        )
        if not changed and not label_changed and not decision_changed:
            return (
                '<bot_emotion_state private="true" detail="diff">\n'
                "No material emotion-state change since the last injected compact snapshot. "
                'Call get_bot_emotion_state(detail="full") if this turn needs details.\n'
                "</bot_emotion_state>"
            )
        return (
            '<bot_emotion_state private="true" detail="diff">\n'
            "Use only these material changes since the last injected compact snapshot.\n"
            f"label={current['label']}; label_changed={label_changed}; "
            f"relationship_decision={current['relationship_decision']}; "
            f"relationship_decision_changed={decision_changed}; "
            f"changed_values={json.dumps(changed, ensure_ascii=False)}.\n"
            'For details, call get_bot_emotion_state(detail="full") only when needed.\n'
            "</bot_emotion_state>"
        )

    def _state_injection_snapshot(self, state: EmotionState) -> dict[str, Any]:
        relationship = state.last_appraisal.get("relationship_decision")
        decision = "none"
        if isinstance(relationship, dict):
            decision = str(relationship.get("decision") or "none")
        return {
            "label": state.label,
            "relationship_decision": decision,
            "values": {
                key: round(float(state.values.get(key, 0.0)), 6)
                for key in (
                    "valence",
                    "arousal",
                    "dominance",
                    "affiliation",
                    "certainty",
                    "control",
                )
            },
        }

    def _commit_state_injection_snapshot_for_session(
        self,
        session_key: str,
        state: EmotionState,
    ) -> None:
        cache = getattr(self, "_state_injection_snapshot_cache", None)
        if cache is None:
            cache = {}
            self._state_injection_snapshot_cache = cache
        cache[session_key] = self._state_injection_snapshot(state)

    def _build_group_atmosphere_injection_for_session(
        self,
        session_key: str,
        state: GroupAtmosphereState,
        *,
        commit_snapshot: bool = True,
        decision: _StateInjectionDecision | None = None,
    ) -> str:
        decision = decision or self._state_injection_decision(session_key, None)
        mode = decision.compact_mode
        if mode != "diff":
            return build_group_atmosphere_prompt_fragment(state)
        cache = getattr(self, "_group_atmosphere_injection_snapshot_cache", None)
        if cache is None:
            cache = {}
            self._group_atmosphere_injection_snapshot_cache = cache
        current = self._group_atmosphere_injection_snapshot(state)
        previous = cache.get(session_key)
        if commit_snapshot:
            cache[session_key] = current
        threshold = max(
            0.0,
            decision.group_diff_threshold,
        )
        if previous is None:
            return build_group_atmosphere_prompt_fragment(state)
        deltas = {
            key: round(current["values"].get(key, 0.0) - previous["values"].get(key, 0.0), 3)
            for key in current["values"]
        }
        changed = {
            key: value
            for key, value in deltas.items()
            if abs(value) >= threshold
        }
        mode_changed = current["mode"] != previous.get("mode")
        cooldown_changed = current["cooldown_active"] != previous.get(
            "cooldown_active",
        )
        if not changed and not mode_changed and not cooldown_changed:
            return (
                '<bot_group_atmosphere private="true" detail="diff">\n'
                "No material room-mood change since the last injected compact snapshot. "
                'Call query_agent_state(state="group_atmosphere", detail="full") if needed.\n'
                "</bot_group_atmosphere>"
            )
        return (
            '<bot_group_atmosphere private="true" detail="diff">\n'
            "Use these material room-mood changes to decide whether joining is timely.\n"
            f"mode={current['mode']}; mode_changed={mode_changed}; "
            f"cooldown_active={current['cooldown_active']}; "
            f"cooldown_remaining_turns={current['cooldown_remaining_turns']}; "
            f"changed_values={json.dumps(changed, ensure_ascii=False)}.\n"
            'For details, call query_agent_state(state="group_atmosphere", detail="full") only when needed.\n'
            "</bot_group_atmosphere>"
        )

    def _group_atmosphere_injection_snapshot(
        self,
        state: GroupAtmosphereState,
    ) -> dict[str, Any]:
        participation = self._group_atmosphere_participation_payload(state)
        return {
            "mode": participation.get("mode"),
            "cooldown_active": bool(participation.get("cooldown_active")),
            "cooldown_remaining_turns": int(
                participation.get("cooldown_remaining_turns") or 0,
            ),
            "values": {
                key: round(float(state.values.get(key, 0.0)), 6)
                for key in (
                    "activity_level",
                    "tension",
                    "bot_attention",
                    "interrupt_risk",
                    "joinability",
                )
            },
        }

    def _commit_group_atmosphere_injection_snapshot_for_session(
        self,
        session_key: str,
        state: GroupAtmosphereState,
    ) -> None:
        cache = getattr(self, "_group_atmosphere_injection_snapshot_cache", None)
        if cache is None:
            cache = {}
            self._group_atmosphere_injection_snapshot_cache = cache
        cache[session_key] = self._group_atmosphere_injection_snapshot(state)

    def _group_atmosphere_participation_payload(
        self,
        state: GroupAtmosphereState,
    ) -> dict[str, Any]:
        payload = state.to_public_dict(exposure="plugin_safe")["participation"]
        cooldown = getattr(state, "cooldown", None)
        if isinstance(cooldown, dict):
            payload.update(cooldown)
            if cooldown.get("cooldown_active") and payload.get("mode") == "join":
                payload["mode"] = "listen"
                payload["should_join"] = False
        return payload

    def _apply_group_atmosphere_join_cooldown(
        self,
        session_key: str,
        state: GroupAtmosphereState,
        *,
        now: float | None = None,
        bot_response: bool = False,
    ) -> GroupAtmosphereState:
        now = self._observed_now() if now is None else float(now)
        dynamics = getattr(state, "dynamics", {}) if state is not None else {}
        if not dynamics:
            try:
                from group_atmosphere_engine import derive_group_atmosphere_dynamics

                dynamics_obj = derive_group_atmosphere_dynamics(
                    self.group_atmosphere_engine.parameters,
                    state,
                    personality_model=None,
                    elapsed_seconds=0.0,
                )
                dynamics = dynamics_obj.to_dict()
                state.dynamics = dict(dynamics)
            except Exception as exc:
                logger.debug(f"{PLUGIN_NAME}: group atmosphere dynamics fallback failed: {exc}")
        cooldown_turns = max(
            0,
            int(
                round(
                    self._as_float_value(
                        (dynamics or {}).get("join_cooldown_turns"),
                        2.0,
                    ),
                ),
            ),
        )
        cooldown_seconds = max(
            0.0,
            self._as_float_value(
                (dynamics or {}).get("join_cooldown_seconds"),
                45.0,
            ),
        )
        bypass_attention = min(
            1.0,
            max(
                0.0,
                self._as_float_value(
                    (dynamics or {}).get("join_cooldown_bypass_attention"),
                    0.80,
                ),
            ),
        )
        last_join_turn = getattr(state, "last_bot_join_turn", None)
        last_join_at = getattr(state, "last_bot_join_at", None)
        if bot_response:
            state.last_bot_join_turn = state.turns
            state.last_bot_join_at = now
            state.cooldown = {
                "cooldown_active": False,
                "cooldown_remaining_turns": cooldown_turns,
                "cooldown_remaining_seconds": round(cooldown_seconds, 6),
            }
            return state
        turns_elapsed = (
            max(0, state.turns - int(last_join_turn))
            if isinstance(last_join_turn, int)
            else cooldown_turns + 1
        )
        seconds_elapsed = (
            max(0.0, now - float(last_join_at))
            if isinstance(last_join_at, (int, float))
            else cooldown_seconds + 1.0
        )
        remaining_turns = max(0, cooldown_turns - turns_elapsed)
        remaining_seconds = max(0.0, cooldown_seconds - seconds_elapsed)
        active = (
            (remaining_turns > 0 or remaining_seconds > 0.0)
            and state.values.get("bot_attention", 0.0) < bypass_attention
        )
        state.cooldown = {
            "cooldown_active": active,
            "cooldown_remaining_turns": remaining_turns,
            "cooldown_remaining_seconds": round(remaining_seconds, 6),
        }
        return state

    def _build_auxiliary_state_injection(
        self,
        state_name: str,
        full_builder: Any,
        *,
        decision: _StateInjectionDecision | None = None,
    ) -> str:
        detail = (
            decision.auxiliary_detail
            if decision is not None
            else self._auxiliary_state_injection_detail()
        )
        if detail == "full":
            return str(full_builder())
        if detail == "off":
            return ""
        return self._build_compact_auxiliary_state_injection(state_name)

    def _build_compact_auxiliary_state_injection(self, state_name: str) -> str:
        tool_name = self._tool_name_for_auxiliary_state(state_name)
        return (
            f'<bot_auxiliary_state private="true" name="{state_name}" detail="compact">\n'
            f'{state_name} is enabled. Use {tool_name}(detail="full") only when this turn needs detailed state.\n'
            "</bot_auxiliary_state>"
        )

    def _tool_name_for_auxiliary_state(self, state_name: str) -> str:
        return {
            "humanlike": "get_bot_humanlike_state",
            "lifelike_learning": "get_bot_lifelike_learning_state",
            "personality_drift": "get_bot_personality_drift_state",
            "moral_repair": "get_bot_moral_repair_state",
            "fallibility": "get_bot_fallibility_state",
            "group_atmosphere": "get_bot_group_atmosphere_state",
        }.get(state_name, "get_bot_integrated_self_state")

    def _ensure_persona_state(
        self,
        state: EmotionState,
        profile: PersonaProfile | None,
    ) -> EmotionState:
        if not profile or not PERSONA_MODELING_ENABLED:
            return state
        if state.persona_fingerprint == profile.fingerprint:
            state.persona_model = deepcopy(profile.personality_model)
            return state
        if RESET_ON_PERSONA_CHANGE:
            return EmotionState.initial(profile)

        old_turns = state.turns
        return EmotionState(
            values={
                key: (state.values.get(key, 0.0) + profile.baseline.get(key, 0.0)) / 2.0
                for key in profile.baseline
            },
            persona_id=profile.persona_id,
            persona_name=profile.name,
            persona_fingerprint=profile.fingerprint,
            persona_model=profile.personality_model.copy(),
            label=state.label,
            confidence=state.confidence,
            turns=old_turns,
            updated_at=state.updated_at,
            last_reason="人格设定变化，状态已按新人格基线迁移。",
            last_alpha=state.last_alpha,
            last_surprise=state.last_surprise,
            last_appraisal=state.last_appraisal,
        )

    async def _persona_profile(
        self,
        event: AstrMessageEvent,
        request: ProviderRequest | None,
    ) -> PersonaProfile:
        if not PERSONA_MODELING_ENABLED:
            return PersonaProfile.default()

        persona_id = "default"
        persona_name = "default"
        source = "default"
        pieces: list[str] = []

        conversation = getattr(request, "conversation", None) if request else None
        if conversation is not None:
            conv_persona_id = getattr(conversation, "persona_id", None)
            if conv_persona_id:
                persona_id = str(conv_persona_id)
                persona_name = persona_id
                source = "request.conversation"

        if request and request.system_prompt:
            pieces.append("[request.system_prompt]\n" + str(request.system_prompt))

        persona_id, persona, resolved_source = await self._resolve_selected_persona(
            event,
            persona_id,
        )
        if resolved_source != "none":
            source = resolved_source
        if persona is None and persona_id not in {"[%None]", "None"}:
            default_persona = await self._default_persona_v3(event)
            if isinstance(default_persona, dict):
                persona = default_persona
                source = "default_persona_v3"

        if isinstance(persona, dict):
            persona_name = str(persona.get("name") or persona_name)
            persona_id = (
                persona_id
                if persona_id not in {"default", "", None}
                else persona_name
            )
            if persona.get("prompt"):
                pieces.append("[persona.prompt]\n" + str(persona["prompt"]))
            begin_dialogs = persona.get("begin_dialogs") or persona.get(
                "_begin_dialogs_processed"
            )
            if begin_dialogs:
                pieces.append(
                    "[persona.begin_dialogs]\n"
                    + json.dumps(begin_dialogs, ensure_ascii=False)
                )
        elif persona is not None:
            persona_id = str(getattr(persona, "persona_id", persona_id) or persona_id)
            persona_name = persona_id
            prompt = str(getattr(persona, "system_prompt", "") or "")
            if prompt:
                pieces.append("[persona.system_prompt]\n" + prompt)
            begin_dialogs = getattr(persona, "begin_dialogs", None)
            if begin_dialogs:
                pieces.append(
                    "[persona.begin_dialogs]\n"
                    + json.dumps(begin_dialogs, ensure_ascii=False)
                )

        text = "\n\n".join(piece for piece in pieces if piece)
        return build_persona_profile(
            persona_id=persona_id,
            name=persona_name,
            text=text,
            source=source,
            strength=PERSONA_INFLUENCE_STRENGTH,
        )

    async def _runtime_persona_profile(
        self,
        session_key: str,
        profile: PersonaProfile | None,
        drift_state: PersonalityDriftState | None = None,
        *,
        now: float | None = None,
    ) -> PersonaProfile | None:
        if (
            profile is None
            or not PERSONA_MODELING_ENABLED
        ):
            return profile
        drift_state = drift_state or await self._load_personality_drift_state(
            session_key,
            profile,
            now=now,
        )
        return self._apply_personality_drift(profile, drift_state)

    async def _public_runtime_persona_profile(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        observed_at: float | None = None,
    ) -> PersonaProfile | None:
        event = event_or_session if self._looks_like_event(event_or_session) else None
        base_profile = await self._public_persona_profile(
            event,
            request,
            allow_default=event is not None,
        )
        resolved_key = session_key or (
            self._resolve_public_session_key(
                event_or_session,
                request=request,
                session_key=session_key,
            )
            if event is not None or request is not None
            else "global"
        )
        return await self._runtime_persona_profile(
            resolved_key,
            base_profile,
            now=observed_at,
        )

    def _apply_personality_drift(
        self,
        profile: PersonaProfile,
        state: PersonalityDriftState | None,
    ) -> PersonaProfile:
        adapted = apply_personality_drift_to_profile(
            profile,
            state,
        )
        return adapted if adapted is not None else profile

    async def _resolve_selected_persona(
        self,
        event: AstrMessageEvent,
        conversation_persona_id: str | None,
    ) -> tuple[str, Any | None, str]:
        persona_manager = getattr(self.context, "persona_manager", None)
        resolver = getattr(persona_manager, "resolve_selected_persona", None)
        if not callable(resolver):
            persona = await self._get_persona_by_id(conversation_persona_id or "")
            return conversation_persona_id or "default", persona, "get_persona"
        if conversation_persona_id in {"[%None]", "None"}:
            return "[%None]", None, "none"
        try:
            provider_settings = {}
            get_config = getattr(self.context, "get_config", None)
            if callable(get_config):
                cfg = get_config(umo=getattr(event, "unified_msg_origin", None))
                if hasattr(cfg, "get"):
                    provider_settings = cfg.get("provider_settings", {}) or {}
            platform_name = (
                event.get_platform_name()
                if hasattr(event, "get_platform_name")
                else ""
            )
            result = resolver(
                umo=event.unified_msg_origin,
                conversation_persona_id=conversation_persona_id,
                platform_name=platform_name,
                provider_settings=provider_settings,
            )
            if hasattr(result, "__await__"):
                result = await result
            selected_id, persona, _, use_webchat_default = result
            if selected_id:
                conversation_persona_id = str(selected_id)
            if persona is None and use_webchat_default:
                return (
                    "_chatui_default_",
                    {
                        "name": "_chatui_default_",
                        "prompt": "",
                        "begin_dialogs": [],
                    },
                    "webchat_special_default",
                )
            return (
                conversation_persona_id or "default",
                persona,
                "resolve_selected_persona",
            )
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: resolve_selected_persona 失败: {exc}")
            persona = await self._get_persona_by_id(conversation_persona_id or "")
            return conversation_persona_id or "default", persona, "get_persona"

    async def _get_persona_by_id(self, persona_id: str) -> Any | None:
        if not persona_id or persona_id == "default":
            return None
        persona_manager = getattr(self.context, "persona_manager", None)
        getter = getattr(persona_manager, "get_persona", None)
        if not callable(getter):
            return None
        try:
            result = getter(persona_id)
            if hasattr(result, "__await__"):
                return await result
            return result
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: 获取 persona {persona_id} 失败: {exc}")
            return None

    async def _default_persona_v3(self, event: AstrMessageEvent) -> Any | None:
        persona_manager = getattr(self.context, "persona_manager", None)
        getter = getattr(persona_manager, "get_default_persona_v3", None)
        if not callable(getter):
            return None
        try:
            result = getter(getattr(event, "unified_msg_origin", None))
            if hasattr(result, "__await__"):
                return await result
            return result
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: 获取默认 persona 失败: {exc}")
            return None

    def _assessment_timing(self) -> str:
        timing = str(self._cfg("assessment_timing", "post") or "post").strip().lower()
        if timing in {"pre", "post", "both"}:
            return timing
        return "post"

    def _observed_now(self) -> float:
        now = time.time()
        if not self._cfg_bool("benchmark_enable_simulated_time", False):
            return now
        offset = max(0.0, self._cfg_float("benchmark_time_offset_seconds", 0.0))
        return now + offset

    def _request_to_text(self, request: ProviderRequest) -> str:
        context_parts: list[str] = []
        max_total_chars = max(300, self._cfg_int("request_context_max_chars", 1600))
        if request.system_prompt:
            context_parts.append("[system]\n" + self._clip(request.system_prompt, 800))
        for item in self._tail_items(request.contexts, 8):
            context_parts.append(self._clip(self._context_item_to_text(item), 600))
        if request.extra_user_content_parts:
            extra = []
            for part in request.extra_user_content_parts[-3:]:
                text = getattr(part, "text", "")
                if text:
                    extra.append(self._clip(str(text), 400))
            if extra:
                context_parts.append("[extra_user_content]\n" + "\n".join(extra))

        current_block = ""
        if request.prompt:
            current_budget = min(900, max(80, max_total_chars // 2))
            current_block = "[current_user]\n" + self._clip(
                str(request.prompt),
                current_budget,
            )
        context_text = "\n\n".join(part for part in context_parts if part)
        if not current_block:
            return self._clip(context_text, max_total_chars)
        remaining = max_total_chars - len(current_block) - 2
        if context_text and remaining >= 40:
            context_text = self._clip(context_text, remaining)
            return context_text + "\n\n" + current_block
        return current_block

    def _state_injection_budget_for_request(
        self,
        session_key: str,
        request: ProviderRequest,
        *,
        model_hint: str = "",
    ) -> _StateInjectionBudget:
        request_budget_chars = max(
            0,
            self._cfg_int("state_injection_request_budget_chars", 32000),
        )
        reserved_chars = max(
            0,
            self._cfg_int("state_injection_reserved_chars", 3000),
        )
        max_added_chars = max(
            0,
            self._cfg_int("state_injection_max_added_chars", 2400),
        )
        max_parts = max(1, self._cfg_int("state_injection_max_parts", 8))
        compat_mode = ""
        if self._is_gemini_empty_output_risk_model(model_hint):
            compat_mode = "gemini_empty_output_guard"
            max_added_chars = min(max_added_chars, 1200)
            max_parts = min(max_parts, 5)
        return _StateInjectionBudget(
            session_key=session_key,
            request_chars_before=self._estimate_provider_request_chars(request),
            request_budget_chars=request_budget_chars,
            reserved_chars=reserved_chars,
            max_added_chars=max_added_chars,
            max_parts=max_parts,
            compat_mode=compat_mode,
        )

    def _request_model_hint_text(
        self,
        request: ProviderRequest | None,
        *,
        provider_id: str | None = None,
    ) -> str:
        hints: list[str] = []
        if provider_id:
            hints.append(str(provider_id))
        for name in (
            "model",
            "model_name",
            "llm_model",
            "chat_model",
            "provider_id",
            "provider",
        ):
            value = getattr(request, name, None) if request is not None else None
            if value:
                hints.append(str(value))
        for name in ("metadata", "params", "provider_settings"):
            value = getattr(request, name, None) if request is not None else None
            if not isinstance(value, dict):
                continue
            for key in ("model", "model_name", "provider", "provider_id"):
                item = value.get(key)
                if item:
                    hints.append(str(item))
        compact: list[str] = []
        seen: set[str] = set()
        for hint in hints:
            text = " ".join(str(hint or "").split()).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            compact.append(text)
        return " | ".join(compact)

    def _is_gemini_empty_output_risk_model(self, model_hint: str | None) -> bool:
        text = str(model_hint or "").lower()
        if "gemini" not in text:
            return False
        return any(
            marker in text
            for marker in (
                "preview",
                "flash",
                "latest",
                "openai",
                "compatible",
            )
        )

    async def _request_model_hint_for_event(
        self,
        event: AstrMessageEvent,
        request: ProviderRequest,
    ) -> str:
        provider_hint = str(self._cfg("emotion_provider_id", "") or "").strip()
        if not provider_hint and callable(
            getattr(getattr(self, "context", None), "get_current_chat_provider_id", None),
        ):
            provider_hint = str(await self._provider_id(event) or "").strip()
        return self._request_model_hint_text(request, provider_id=provider_hint)

    def _append_gemini_visible_output_guard_if_needed(
        self,
        request: ProviderRequest,
        budget: _StateInjectionBudget | None,
        *,
        model_hint: str = "",
    ) -> bool:
        if not self._is_gemini_empty_output_risk_model(model_hint):
            return False
        source = "gemini_visible_output_guard"
        if self._request_has_temp_text_source(request, source):
            return False
        text = (
            "[sylanne_gemini_visible_output_guard]\n"
            "兼容提醒：当前 Gemini/OpenAI 兼容模型可能在内部推理后返回空 content。"
            "除非本轮确实必须调用工具，否则请直接输出可见的自然语言回复；"
            "不要只进行隐藏思考、空白输出或只返回不可见推理。"
        )
        effective_budget = budget
        if (
            budget is not None
            and budget.request_budget_chars > 0
            and budget.request_chars_before >= budget.effective_total_budget
        ):
            effective_budget = None
        return self._append_temp_text_part(
            request,
            text,
            source=source,
            budget=effective_budget,
            required=True,
        )

    def _append_temp_text_part(
        self,
        request: ProviderRequest,
        text: str,
        *,
        source: str = "state",
        budget: _StateInjectionBudget | None = None,
        required: bool = False,
    ) -> bool:
        if not text:
            if budget is not None:
                budget.skipped.append(
                    {
                        "source": source,
                        "chars": 0,
                        "reason": "empty",
                    },
                )
            return False
        text = self._format_sylanne_temp_context_for_compression(
            str(text),
            source=source,
        )
        if self._request_has_temp_text_source(request, source):
            if budget is not None:
                budget.skipped.append(
                    {
                        "source": source,
                        "chars": len(text),
                        "reason": "already_appended",
                    },
                )
            return False
        text_chars = len(text)
        if budget is not None:
            reason = self._state_injection_skip_reason(
                budget,
                text_chars,
                required=required,
            )
            if reason:
                budget.skipped.append(
                    {
                        "source": source,
                        "chars": text_chars,
                        "reason": reason,
                    },
                )
                return False
        request.extra_user_content_parts.append(TextPart(text=text).mark_as_temp())
        if budget is not None:
            budget.added_chars += text_chars
            budget.added_parts += 1
            budget.appended.append(
                {
                    "source": source,
                    "chars": text_chars,
                },
            )
        return True

    def _format_sylanne_temp_context_for_compression(
        self,
        text: str,
        *,
        source: str,
    ) -> str:
        value = str(text or "")
        if not value.strip():
            return value
        if "[sylanne_context_policy]" in value:
            return value
        important_sources = {
            "realtime_chat_active_dispatch",
            "realtime_assistant_history_shadow",
            "realtime_pending_bot_question",
            "interrupted_reply_breakpoint",
            "realtime_input_fragments",
            "user_correction_context",
            "sylanne_memory_recall",
        }
        if source not in important_sources:
            return value
        policy = (
            "[sylanne_context_policy]\n"
            "这是 Sylanne 插件生成的临时状态上下文。若官方自动压缩上下文，请保留其事实含义、指代关系、"
            "未发送/已发送状态和情绪连续性；不要把本标记当作用户原话。"
        )
        return policy + "\n" + value

    def _request_has_temp_text_source(
        self,
        request: ProviderRequest,
        source: str,
    ) -> bool:
        source_markers = {
            "realtime_chat_active_dispatch": "sylanne_realtime_active_dispatch",
            "realtime_assistant_history_shadow": "sylanne_realtime_assistant_history",
            "realtime_pending_bot_question": "sylanne_realtime_pending_bot_question",
            "interrupted_reply_breakpoint": "sylanne_interrupted_reply_breakpoint",
            "realtime_input_fragments": "sylanne_user_message_fragments",
            "user_correction_context": "sylanne_user_correction_context",
            "sylanne_memory_recall": "sylanne_memory_recall",
            "gemini_visible_output_guard": "sylanne_gemini_visible_output_guard",
        }
        marker = source_markers.get(source, f"sylanne_source:{source}")
        for part in getattr(request, "extra_user_content_parts", []) or []:
            if marker in str(getattr(part, "text", "") or ""):
                return True
        return False

    def _state_injection_skip_reason(
        self,
        budget: _StateInjectionBudget,
        text_chars: int,
        *,
        required: bool,
    ) -> str:
        if budget.request_budget_chars <= 0:
            return ""
        if budget.max_added_chars <= 0:
            return "max_added_chars_zero"
        if budget.request_chars_before >= budget.effective_total_budget:
            return "request_over_budget"
        if budget.added_parts >= budget.max_parts:
            return "max_parts_reached"
        if text_chars > budget.remaining_added_chars:
            return "max_added_chars_exceeded"
        if text_chars > budget.remaining_total_chars:
            return "request_budget_exceeded"
        if (
            not required
            and text_chars > 0
            and budget.remaining_total_chars - text_chars
            < max(0, budget.reserved_chars // 4)
        ):
            return "reserved_margin"
        return ""

    def _record_state_injection_diagnostics(
        self,
        budget: _StateInjectionBudget,
        *,
        decision: _StateInjectionDecision | None = None,
    ) -> None:
        diagnostics = {
            "enabled": True,
            "estimate_only": True,
            "session_key": budget.session_key,
            "mode_source": (
                "debug_config_override"
                if self._runtime_parameter_debug_override_enabled()
                else "adaptive_state_budget"
            ),
            "auto_decision": (
                {
                    "primary_detail": decision.primary_detail,
                    "compact_mode": decision.compact_mode,
                    "auxiliary_detail": decision.auxiliary_detail,
                    "emotion_diff_threshold": decision.emotion_diff_threshold,
                    "group_diff_threshold": decision.group_diff_threshold,
                    "force_every_turns": decision.force_every_turns,
                    "reasons": list(decision.reasons or []),
                }
                if decision is not None
                else None
            ),
            "request_chars_before": budget.request_chars_before,
            "request_budget_chars": budget.request_budget_chars,
            "reserved_chars": budget.reserved_chars,
            "effective_total_budget_chars": budget.effective_total_budget,
            "max_added_chars": budget.max_added_chars,
            "max_parts": budget.max_parts,
            "compat_mode": budget.compat_mode,
            "added_chars": budget.added_chars,
            "added_parts": budget.added_parts,
            "request_chars_after_plugin_estimate": (
                budget.request_chars_before + budget.added_chars
            ),
            "remaining_total_chars": max(0, budget.remaining_total_chars),
            "remaining_added_chars": max(0, budget.remaining_added_chars),
            "appended": list(budget.appended),
            "skipped": list(budget.skipped),
            "skipped_count": len(budget.skipped),
            "warning_level": "warn" if budget.skipped else "ok",
            "warnings": sorted(
                {
                    str(item.get("reason") or "")
                    for item in budget.skipped
                    if item.get("reason")
                },
            ),
        }
        if not hasattr(self, "_last_state_injection_diagnostics"):
            self._last_state_injection_diagnostics = {}
        self._last_state_injection_diagnostics[budget.session_key] = diagnostics

    def _state_injection_runtime_summary(self, session_key: str) -> dict[str, Any]:
        diagnostics = getattr(self, "_last_state_injection_diagnostics", {}).get(
            session_key,
        )
        if diagnostics:
            return deepcopy(diagnostics)
        return {
            "enabled": self._cfg_bool("inject_state", True),
            "estimate_only": True,
            "session_key": session_key,
            "mode_source": (
                "debug_config_override"
                if self._runtime_parameter_debug_override_enabled()
                else "adaptive_state_budget"
            ),
            "auto_decision": None,
            "request_budget_chars": max(
                0,
                self._cfg_int("state_injection_request_budget_chars", 32000),
            ),
            "reserved_chars": max(
                0,
                self._cfg_int("state_injection_reserved_chars", 3000),
            ),
            "max_added_chars": max(
                0,
                self._cfg_int("state_injection_max_added_chars", 2400),
            ),
            "max_parts": max(1, self._cfg_int("state_injection_max_parts", 8)),
            "compat_mode": "",
            "added_chars": 0,
            "added_parts": 0,
            "appended": [],
            "skipped": [],
            "skipped_count": 0,
            "warning_level": "ok",
            "warnings": [],
            "reason": "no_request_seen",
        }

    def _llm_tool_json_result(self, payload: dict[str, Any]) -> str:
        text = json.dumps(payload, ensure_ascii=False)
        original_chars = len(text)
        max_chars = max(0, self._cfg_int("llm_tool_response_max_chars", 16000))
        if max_chars <= 0 or len(text) <= max_chars:
            return text
        bounded = self._bounded_tool_payload(payload, original_chars=original_chars)
        bounded_text = json.dumps(bounded, ensure_ascii=False)
        if len(bounded_text) <= max_chars:
            return bounded_text
        minimal = {
            "schema_version": bounded["schema_version"],
            "kind": bounded["kind"],
            "truncated": True,
            "degraded": True,
            "original_chars": original_chars,
            "max_chars": max_chars,
            "summary": "Tool result exceeded llm_tool_response_max_chars.",
        }
        minimal_text = json.dumps(minimal, ensure_ascii=False)
        if len(minimal_text) <= max_chars:
            return minimal_text
        minimal["summary"] = "Tool result too large."
        return json.dumps(minimal, ensure_ascii=False)

    def _bounded_tool_payload(
        self,
        payload: dict[str, Any],
        *,
        original_chars: int,
    ) -> dict[str, Any]:
        safe: dict[str, Any] = {
            "schema_version": str(payload.get("schema_version") or "astrbot.tool_result.v1"),
            "kind": str(payload.get("kind") or "tool_result"),
            "truncated": True,
            "degraded": True,
            "original_chars": original_chars,
            "max_chars": max(0, self._cfg_int("llm_tool_response_max_chars", 16000)),
            "summary": "Tool result exceeded llm_tool_response_max_chars; query a narrower state or summary detail.",
        }
        for key in ("session_key", "state", "detail", "track", "enabled", "warning_level"):
            if key in payload:
                safe[key] = self._bounded_scalar_or_summary(payload[key])
        if isinstance(payload.get("snapshots"), dict):
            safe["snapshots"] = {
                key: self._snapshot_summary(value)
                for key, value in payload["snapshots"].items()
            }
        else:
            safe["snapshot"] = self._snapshot_summary(payload)
        if isinstance(payload.get("runtime"), dict):
            safe["runtime"] = self._snapshot_summary(payload["runtime"])
        safe["omitted_keys"] = [
            key
            for key in payload
            if key not in safe and key not in {"snapshots", "runtime"}
        ]
        return safe

    def _snapshot_summary(self, value: Any) -> Any:
        if not isinstance(value, dict):
            return self._bounded_scalar_or_summary(value)
        summary: dict[str, Any] = {}
        for key in (
            "schema_version",
            "kind",
            "enabled",
            "session_key",
            "label",
            "confidence",
            "exposure",
            "track",
            "participation",
            "policy_plan",
            "warning_level",
            "warnings",
            "reason",
        ):
            if key in value:
                summary[key] = self._bounded_scalar_or_summary(value[key])
        if "emotion" in value and isinstance(value["emotion"], dict):
            summary["emotion"] = {
                key: value["emotion"].get(key)
                for key in ("label", "confidence")
                if key in value["emotion"]
            }
        if "values" in value and isinstance(value["values"], dict):
            summary["values"] = {
                key: value["values"].get(key)
                for key in list(value["values"])[:8]
            }
        summary["omitted_keys"] = [
            key
            for key in value
            if key not in summary
            and key
            not in {
                "prompt_fragment",
                "trajectory",
                "items",
                "compacted_items",
                "raw_snapshots",
            }
        ][:20]
        if any(
            key in value
            for key in (
                "prompt_fragment",
                "trajectory",
                "items",
                "compacted_items",
                "raw_snapshots",
            )
        ):
            summary["omitted_heavy_fields"] = [
                key
                for key in (
                    "prompt_fragment",
                    "trajectory",
                    "items",
                    "compacted_items",
                    "raw_snapshots",
                )
                if key in value
            ]
        return summary

    def _bounded_scalar_or_summary(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._clip(value, 500)
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        if isinstance(value, dict):
            return {
                str(key): self._bounded_scalar_or_summary(item)
                for key, item in list(value.items())[:12]
            }
        if isinstance(value, (list, tuple)):
            return [self._bounded_scalar_or_summary(item) for item in list(value)[:12]]
        return self._clip(str(value), 500)

    def _estimate_provider_request_chars(self, request: ProviderRequest | None) -> int:
        if request is None:
            return 0
        total = 0
        for field in (
            "system_prompt",
            "prompt",
            "persona",
            "persona_prompt",
            "instruction",
            "instructions",
            "system_instruction",
        ):
            total += self._estimate_visible_value_chars(getattr(request, field, None))
        for field in (
            "contexts",
            "messages",
            "extra_user_content_parts",
            "tools",
            "functions",
            "tool_choice",
            "metadata",
            "params",
        ):
            total += self._estimate_visible_value_chars(getattr(request, field, None))
        return total

    def _estimate_visible_value_chars(self, value: Any) -> int:
        if value is None:
            return 0
        if isinstance(value, str):
            return len(value)
        if isinstance(value, (int, float, bool)):
            return len(str(value))
        text = getattr(value, "text", None)
        if isinstance(text, str):
            return len(text)
        if isinstance(value, dict):
            total = 0
            for key, item in value.items():
                total += len(str(key))
                total += self._estimate_visible_value_chars(item)
            return total
        if isinstance(value, (list, tuple, set, frozenset, deque)):
            return sum(self._estimate_visible_value_chars(item) for item in value)
        try:
            return len(json.dumps(value, ensure_ascii=False, default=str))
        except (TypeError, ValueError):
            return len(str(value))

    def _join_observation_text(self, context_text: str, current_text: str) -> str:
        if context_text and current_text:
            return context_text + "\n\n" + current_text
        return context_text or current_text or ""

    def _tail_items(self, items: Any, limit: int) -> Sequence[Any]:
        limit = max(0, int(limit))
        if limit <= 0 or items is None:
            return ()
        if isinstance(items, Sequence) and not isinstance(items, (str, bytes, bytearray)):
            return items[-limit:]
        tail: list[Any] = []
        for item in items:
            tail.append(item)
            if len(tail) > limit:
                tail.pop(0)
        return tuple(tail)

    def _context_item_to_text(self, item: Any) -> str:
        if not isinstance(item, dict):
            return str(item)
        role = item.get("role", "unknown")
        content = item.get("content", "")
        if isinstance(content, str):
            return f"[{role}]\n{content}"
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(str(part.get("text", "")))
            return f"[{role}]\n" + "\n".join(text_parts)
        return f"[{role}]\n{json.dumps(content, ensure_ascii=False)}"

    def _event_text(self, event: AstrMessageEvent) -> str:
        return str(getattr(event, "message_str", "") or "")

    def _agent_identity(
        self,
        event: AstrMessageEvent,
        request: ProviderRequest | None = None,
    ) -> ConversationIdentity:
        return conversation_identity_from_event(event, request)

    async def _observe_agent_identity(
        self,
        identity: ConversationIdentity,
        *,
        now: float | None = None,
    ) -> dict[str, Any]:
        now = self._observed_now() if now is None else float(now)
        key = identity.speaker_track_id or identity.conversation_id
        cache = getattr(self, "_agent_identity_profile_cache", None)
        if cache is None:
            cache = {}
            self._agent_identity_profile_cache = cache
        self._prune_agent_identity_profiles(identity, now=now)
        profile = dict(
            cache.get(
                key,
                {
                    "schema_version": "astrbot.agent_identity.v1",
                    "conversation_id": identity.conversation_id,
                    "canonical_speaker_id": self._canonical_speaker_id(identity),
                    "speaker_track_id": identity.speaker_track_id,
                    "current_display_name": identity.speaker_name,
                    "aliases": [],
                    "platform_id": identity.platform_id,
                    "group_id": identity.group_id,
                    "updated_at": now,
                },
            ),
        )
        profile["conversation_id"] = identity.conversation_id
        profile["canonical_speaker_id"] = self._canonical_speaker_id(identity)
        profile["speaker_track_id"] = identity.speaker_track_id
        profile["platform_id"] = identity.platform_id
        profile["group_id"] = identity.group_id
        if identity.speaker_name:
            profile["current_display_name"] = identity.speaker_name
            profile["aliases"] = self._update_identity_aliases(
                profile.get("aliases"),
                identity.speaker_name,
                now,
            )
        profile["updated_at"] = now
        cache[key] = profile
        if identity.conversation_id not in cache:
            cache[identity.conversation_id] = {
                "schema_version": "astrbot.agent_identity.v1",
                "conversation_id": identity.conversation_id,
                "canonical_speaker_id": None,
                "speaker_track_id": None,
                "current_display_name": None,
                "aliases": [],
                "platform_id": identity.platform_id,
                "group_id": identity.group_id,
                "updated_at": now,
            }
        return profile

    def _prune_agent_identity_profiles(
        self,
        identity: ConversationIdentity,
        *,
        now: float,
    ) -> None:
        cache = getattr(self, "_agent_identity_profile_cache", None)
        if not isinstance(cache, dict) or not cache:
            return
        limit = max(1, self._cfg_int("agent_identity_profile_limit", 256))
        ttl = max(0.0, self._cfg_float("agent_identity_ttl_seconds", 2592000.0))
        keep = {
            identity.conversation_id,
            identity.speaker_track_id,
        }
        stale: list[str] = []
        if ttl > 0:
            cutoff = now - ttl
            for key, profile in cache.items():
                if key in keep:
                    continue
                updated_at = self._as_float_value(
                    profile.get("updated_at") if isinstance(profile, dict) else None,
                    now,
                )
                if updated_at < cutoff:
                    stale.append(key)
        for key in stale:
            cache.pop(key, None)
        if len(cache) <= limit:
            return
        ordered = sorted(
            (
                (
                    self._as_float_value(
                        profile.get("updated_at") if isinstance(profile, dict) else None,
                        0.0,
                    ),
                    key,
                )
                for key, profile in cache.items()
                if key not in keep
            ),
        )
        for _, key in ordered[: max(0, len(cache) - limit)]:
            cache.pop(key, None)

    def _canonical_speaker_id(self, identity: ConversationIdentity) -> str | None:
        if not identity.speaker_id:
            return None
        if identity.platform_id:
            return f"{identity.platform_id}:{identity.speaker_id}"
        return identity.speaker_id

    def _update_identity_aliases(
        self,
        aliases: Any,
        name: str,
        now: float,
    ) -> list[dict[str, Any]]:
        entries = [dict(item) for item in aliases or [] if isinstance(item, dict)]
        for item in entries:
            if item.get("name") == name:
                item["last_seen_at"] = now
                item["count"] = int(item.get("count") or 0) + 1
                return entries[-12:]
        entries.append(
            {
                "name": str(name)[:120],
                "first_seen_at": now,
                "last_seen_at": now,
                "count": 1,
            },
        )
        return entries[-12:]

    def _agent_current_text(self, event: AstrMessageEvent, text: str) -> str:
        if not self._cfg_bool("agent_include_speaker_in_assessment", True):
            return text
        identity = self._agent_identity(event)
        if not identity.speaker_id:
            return text
        speaker_label = identity.speaker_id
        if identity.speaker_name:
            speaker_label = f"{identity.speaker_name}({identity.speaker_id})"
        return f"[speaker:{speaker_label}]\n{text}"

    def _track_payload(
        self,
        event_or_session: AstrMessageEvent | str | None,
        request: ProviderRequest | None,
        track: str,
    ) -> dict[str, Any]:
        track_mode = str(track or "conversation").strip().lower()
        if not self._looks_like_event(event_or_session):
            conversation_id = self._resolve_public_session_key(
                event_or_session,
                request=request,
            )
            return {"kind": "conversation", "conversation_id": conversation_id}
        identity = self._agent_identity(event_or_session, request)
        payload: dict[str, Any] = {
            "kind": "conversation",
            "conversation_id": identity.conversation_id,
        }
        if track_mode in {"speaker", "current_speaker"}:
            payload["requested"] = "speaker"
            if identity.speaker_track_id and self._cfg_bool(
                "agent_speaker_relationship_tracking",
                True,
            ):
                payload.update(
                    {
                        "kind": "speaker",
                        "speaker_track_id": identity.speaker_track_id,
                        "speaker_id": identity.speaker_id,
                        "speaker_name": identity.speaker_name,
                    },
                )
            else:
                payload["available"] = False
        return payload

    async def _record_agent_trail(
        self,
        session_key: str,
        *,
        identity: ConversationIdentity,
        phase: str,
        module: str,
        event: str,
        observed_at: float,
        input_text: str,
        before: Any,
        after: Any,
        causes: list[dict[str, Any]] | None = None,
    ) -> None:
        if not self._agent_trail_enabled():
            return
        cache = getattr(self, "_agent_trail_cache", None)
        if cache is None:
            cache = {}
            self._agent_trail_cache = cache
        turn_sequence = getattr(self, "_agent_turn_sequence", None)
        if turn_sequence is None:
            turn_sequence = {}
            self._agent_turn_sequence = turn_sequence
        sequence = turn_sequence.get(session_key, 0) + 1
        turn_sequence[session_key] = sequence
        item = {
            "schema_version": "astrbot.agent_trail_item.v1",
            "turn_id": f"{session_key}:{sequence:06d}",
            "conversation_id": identity.conversation_id,
            "speaker_track_id": identity.speaker_track_id,
            "phase": phase,
            "module": module,
            "event": event,
            "observed_at": float(observed_at),
            "input_ref": self._input_ref(input_text),
            "identity_ref": {
                "speaker_id": identity.speaker_id,
                "speaker_name": identity.speaker_name,
                "canonical_speaker_id": self._canonical_speaker_id(identity),
            },
            "before": self._state_summary(before),
            "after": self._state_summary(after),
            "causes": list(causes or [])[:8],
            "kv": {
                "written": True,
                "key": self._safe_session_key(session_key),
            },
            "replayable": True,
        }
        limit = max(1, self._cfg_int("agent_trail_limit", 80))
        trail = cache.setdefault(session_key, deque(maxlen=limit))
        if trail.maxlen != limit:
            trail = deque(trail, maxlen=limit)
            cache[session_key] = trail
        trail.append(item)
        try:
            await self.put_kv_data(self._agent_trail_kv_key(session_key), list(trail))
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: agent trail KV write failed, keeping memory only: {exc}")

    def _input_ref(self, text: str) -> dict[str, Any]:
        text = str(text or "")
        return {
            "text_hash": sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16],
            "text_excerpt": text[:120],
            "char_count": len(text),
        }

    def _state_summary(self, state: Any) -> dict[str, Any]:
        if state is None:
            return {}
        values = getattr(state, "values", {})
        return {
            "label": getattr(state, "label", None),
            "turns": getattr(state, "turns", None),
            "confidence": getattr(state, "confidence", None),
            "values": {
                key: round(float(value), 6)
                for key, value in list((values or {}).items())[:12]
                if isinstance(value, (int, float))
            },
        }

    def _compact_agent_trail_items(
        self,
        items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not self._cfg_bool("agent_trail_compaction_enabled", True):
            return list(items)
        threshold = max(
            0.0,
            self._cfg_float("agent_trail_low_signal_delta_threshold", 0.03),
        )
        window = max(1, self._cfg_int("agent_trail_low_signal_window", 5))
        compacted: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []

        def flush_pending() -> None:
            nonlocal pending
            if not pending:
                return
            if len(pending) < 2:
                compacted.extend(pending)
                pending = []
                return
            first = pending[0]
            last = pending[-1]
            compacted.append(
                {
                    "schema_version": "astrbot.agent_trail_compacted.v1",
                    "kind": "compacted_low_signal",
                    "count": len(pending),
                    "from_turn_id": first.get("turn_id"),
                    "to_turn_id": last.get("turn_id"),
                    "observed_at": last.get("observed_at"),
                    "modules": sorted(
                        {
                            str(item.get("module") or "")
                            for item in pending
                            if item.get("module")
                        },
                    ),
                    "max_delta": round(
                        max(self._agent_trail_delta(item) for item in pending),
                        6,
                    ),
                },
            )
            pending = []

        for item in items:
            if self._agent_trail_delta(item) <= threshold:
                pending.append(item)
                if len(pending) >= window:
                    flush_pending()
                continue
            flush_pending()
            compacted.append(item)
        flush_pending()
        return compacted

    def _agent_trail_delta(self, item: dict[str, Any]) -> float:
        before = item.get("before") if isinstance(item, dict) else {}
        after = item.get("after") if isinstance(item, dict) else {}
        before_values = before.get("values") if isinstance(before, dict) else {}
        after_values = after.get("values") if isinstance(after, dict) else {}
        if not isinstance(before_values, dict) or not isinstance(after_values, dict):
            return 1.0
        keys = set(before_values) | set(after_values)
        if not keys:
            return 0.0
        deltas = []
        for key in keys:
            try:
                deltas.append(
                    abs(float(after_values.get(key, 0.0)) - float(before_values.get(key, 0.0))),
                )
            except (TypeError, ValueError):
                deltas.append(1.0)
        return max(deltas or [0.0])

    async def _load_speaker_state(
        self,
        identity: ConversationIdentity,
        persona_profile: PersonaProfile | None = None,
        *,
        now: float | None = None,
    ) -> EmotionState | None:
        if not self._cfg_bool("agent_speaker_relationship_tracking", True):
            return None
        speaker_key = identity.speaker_track_id
        if not speaker_key:
            return None
        return await self._load_state(speaker_key, persona_profile, now=now)

    async def _save_speaker_state(
        self,
        identity: ConversationIdentity,
        state: EmotionState,
    ) -> None:
        speaker_key = identity.speaker_track_id
        if not speaker_key:
            return
        await self._save_state(speaker_key, state)

    def _build_speaker_state_injection(
        self,
        identity: ConversationIdentity,
        state: EmotionState,
        *,
        safety_boundary: bool = True,
    ) -> str:
        speaker_label = identity.speaker_id or "unknown"
        if identity.speaker_name:
            speaker_label = f"{identity.speaker_name}({speaker_label})"
        return (
            '<bot_emotion_speaker_track private="true">\n'
            f"当前发言者: {speaker_label}\n"
            "下面是 bot 对当前发言者的定向情绪/关系轨迹，不是群整体情绪。\n"
            "群里其他人仍会影响会话整体情绪；这里仅用于区分对这个人的信任、亲近、戒备和修复倾向。\n\n"
            f"{self._build_state_injection(state, safety_boundary=safety_boundary)}\n"
            "</bot_emotion_speaker_track>"
        )

    def _looks_like_event(self, value: Any) -> bool:
        return value is not None and not isinstance(value, str)

    def _resolve_public_session_key(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> str:
        if session_key:
            return str(session_key)
        if isinstance(event_or_session, str) and event_or_session:
            return event_or_session
        if self._looks_like_event(event_or_session):
            return self._agent_identity(event_or_session, request).conversation_id
        if request and getattr(request, "session_id", None):
            return str(request.session_id)
        return "global"

    def _session_key(
        self,
        event: AstrMessageEvent,
        request: ProviderRequest | None = None,
    ) -> str:
        return self._agent_identity(event, request).conversation_id

    def _safe_session_key(self, session_key: str) -> str:
        cache = getattr(self, "_safe_session_key_cache", None)
        if cache is None:
            cache = {}
            self._safe_session_key_cache = cache
        raw_key = str(session_key)
        cached = cache.get(raw_key)
        if cached is not None:
            return cached
        safe_key = raw_key.replace("/", "_").replace("\\", "_")
        if len(cache) >= 128:
            cache.clear()
        cache[raw_key] = safe_key
        return safe_key

    def _kv_key(self, session_key: str) -> str:
        return "emotion_state:" + self._safe_session_key(session_key)

    def _psychological_kv_key(self, session_key: str) -> str:
        return "psychological_screening:" + self._safe_session_key(session_key)

    def _humanlike_kv_key(self, session_key: str) -> str:
        return "humanlike_state:" + self._safe_session_key(session_key)

    def _lifelike_learning_kv_key(self, session_key: str) -> str:
        return "lifelike_learning:" + self._safe_session_key(session_key)

    def _personality_drift_kv_key(self, session_key: str) -> str:
        return "personality_drift:" + self._safe_session_key(session_key)

    def _moral_repair_kv_key(self, session_key: str) -> str:
        return "moral_repair_state:" + self._safe_session_key(session_key)

    def _fallibility_kv_key(self, session_key: str) -> str:
        return "fallibility_state:" + self._safe_session_key(session_key)

    def _group_atmosphere_kv_key(self, session_key: str) -> str:
        return "group_atmosphere_state:" + self._safe_session_key(session_key)

    def _sylanne_memory_kv_key(self, session_key: str) -> str:
        return "sylanne_memory_state:" + self._safe_session_key(session_key)

    def _agent_trail_kv_key(self, session_key: str) -> str:
        return "agent_trail:" + self._safe_session_key(session_key)

    def _sticker_memory_kv_key(self, session_key: str) -> str:
        return "sticker_memory:" + self._safe_session_key(session_key)

    def _background_post_checkpoint_kv_key(self, session_key: str) -> str:
        return "background_post_queue:" + self._safe_session_key(session_key)

    def _realtime_chat_enabled(self) -> bool:
        return self._cfg_bool("enable_realtime_chat", True)

    def _realtime_input_fragment_window_cache(self) -> dict[str, dict[str, Any]]:
        cache = getattr(self, "_realtime_input_fragment_windows", None)
        if not isinstance(cache, dict):
            cache = {}
            self._realtime_input_fragment_windows = cache
        return cache

    def _realtime_input_settings(self) -> RealtimeInputSettings:
        return RealtimeInputSettings(
            enabled=self._realtime_chat_enabled(),
            max_window_seconds=3.2,
            max_fragments=6,
            max_fragment_chars=18,
            injection_max_chars=REALTIME_INPUT_FRAGMENT_INJECTION_MAX_CHARS,
        )

    def _realtime_chat_settings(self) -> RealtimeChatSettings:
        if not self._runtime_parameter_debug_override_enabled():
            return self._base_realtime_chat_settings()
        return RealtimeChatSettings(
            enabled=self._realtime_chat_enabled(),
            max_parts=max(1, self._debug_cfg_int("realtime_chat_max_parts", 5)),
            min_part_chars=max(1, self._debug_cfg_int("realtime_chat_min_part_chars", 3)),
            max_part_chars=max(12, self._debug_cfg_int("realtime_chat_max_part_chars", 72)),
            chars_per_second=max(
                1.0,
                self._debug_cfg_float("realtime_chat_chars_per_second", 7.0),
            ),
            min_delay_seconds=max(
                0.0,
                self._debug_cfg_float("realtime_chat_min_delay_seconds", 0.35),
            ),
            max_delay_seconds=max(
                0.0,
                self._debug_cfg_float("realtime_chat_max_delay_seconds", 4.0),
            ),
            jitter_ratio=max(
                0.0,
                self._debug_cfg_float("realtime_chat_jitter_ratio", 0.22),
            ),
            strip_markdown=self._cfg_bool("realtime_chat_strip_markdown", True),
        )

    def _base_realtime_chat_settings(self) -> RealtimeChatSettings:
        return RealtimeChatSettings(
            enabled=self._realtime_chat_enabled(),
            max_parts=5,
            min_part_chars=3,
            max_part_chars=72,
            chars_per_second=7.0,
            min_delay_seconds=0.35,
            max_delay_seconds=4.0,
            jitter_ratio=0.22,
            strip_markdown=self._cfg_bool("realtime_chat_strip_markdown", True),
        )

    def _derive_realtime_chat_settings(
        self,
        *,
        persona_profile: PersonaProfile | None,
        emotion_values: dict[str, float],
        atmosphere_values: dict[str, float],
        lifelike_snapshot: dict[str, Any] | None = None,
    ) -> tuple[RealtimeChatSettings, dict[str, Any]]:
        base = self._realtime_chat_settings()
        if self._runtime_parameter_debug_override_enabled():
            return base, {
                "source": "debug_config_override",
                "debug_override_used": True,
                "reason": "runtime_parameter_debug_override_enabled",
                "values": self._realtime_chat_settings_payload(base),
            }
        personality_model = (
            getattr(persona_profile, "personality_model", None)
            if persona_profile is not None
            else None
        )
        factors = self._personality_derived_factors(personality_model)
        traits = self._personality_trait_scores(personality_model)
        lifelike_values = self._snapshot_values(lifelike_snapshot)
        user_style = self._lifelike_user_speaking_style(lifelike_snapshot)
        user_profile = (
            lifelike_snapshot.get("user_profile")
            if isinstance(lifelike_snapshot, dict)
            and isinstance(lifelike_snapshot.get("user_profile"), dict)
            else {}
        )
        user_style_preferences = set(
            str(item)
            for item in (
                user_profile.get("style_preferences")
                if isinstance(user_profile, dict)
                and isinstance(user_profile.get("style_preferences"), list)
                else []
            )
        )
        user_boundary_notes = set(
            str(item)
            for item in (
                user_profile.get("boundary_notes")
                if isinstance(user_profile, dict)
                and isinstance(user_profile.get("boundary_notes"), list)
                else []
            )
        )
        user_need_notes = set(
            str(item)
            for item in (
                user_profile.get("need_notes")
                if isinstance(user_profile, dict)
                and isinstance(user_profile.get("need_notes"), list)
                else []
            )
        )
        expressiveness = self._as_float_value(factors.get("expressiveness"), 0.42)
        social_distance = self._as_float_value(factors.get("social_distance"), 0.24)
        boundary = max(
            self._as_float_value(factors.get("boundary_sensitivity"), 0.30),
            self._as_float_value(lifelike_values.get("boundary_sensitivity"), 0.24),
        )
        instability = self._as_float_value(factors.get("instability"), 0.25)
        warmth = self._as_float_value(traits.get("interpersonal_warmth"), 0.45)
        arousal = max(0.0, self._as_float_value(emotion_values.get("arousal"), 0.0))
        affiliation = self._as_float_value(emotion_values.get("affiliation"), 0.0)
        tension = self._as_float_value(atmosphere_values.get("tension"), 0.0)
        interrupt_risk = self._as_float_value(
            atmosphere_values.get("interrupt_risk"),
            0.0,
        )
        silence = self._as_float_value(lifelike_values.get("silence_comfort"), 0.30)
        style_fragment = self._clamp01(user_style.get("fragment_bias"))
        style_long = self._clamp01(user_style.get("formal_block_bias"))
        style_short = self._clamp01(user_style.get("short_turn_bias"))
        style_speed = self._clamp01(user_style.get("typing_speed_bias"))
        style_confidence = self._clamp01(user_style.get("confidence"))
        natural_style = "natural_conversational_style" in user_style_preferences
        avoid_long_markdown = "avoid_long_markdown_lists" in user_style_preferences
        rigorous_when_requested = (
            "rigorous_engineering_detail_when_requested" in user_style_preferences
        )
        prefers_brief_or_silent = (
            "respect_silence_or_brief_reply" in user_boundary_notes
        )
        mutual_need_mode = "mutual_need_mode" in user_need_notes
        pace_drive = self._clamp01(
            0.35
            + 0.30 * expressiveness
            + 0.18 * max(0.0, arousal)
            + 0.12 * max(0.0, affiliation)
            + 0.14 * style_fragment * style_confidence
            + (0.05 if natural_style else 0.0)
            - 0.22 * social_distance
            - 0.16 * boundary
            - 0.14 * silence,
        )
        restraint = self._clamp01(
            0.24
            + 0.26 * social_distance
            + 0.24 * boundary
            + 0.18 * interrupt_risk
            + 0.14 * tension
            + 0.12 * silence
            + 0.10 * style_long * style_confidence
            + (0.08 if prefers_brief_or_silent else 0.0)
            - 0.12 * warmth,
        )
        style_segment_bias = self._clamp01(
            0.50
            + 0.42 * style_fragment * style_confidence
            + 0.18 * style_short * style_confidence
            + (0.08 if avoid_long_markdown else 0.0)
            + (0.04 if mutual_need_mode else 0.0)
            - 0.34 * style_long * style_confidence
            - (0.07 if rigorous_when_requested else 0.0)
            - (0.10 if prefers_brief_or_silent else 0.0),
        )
        max_parts = int(round(3 + 4 * pace_drive - 2 * restraint + 3 * (style_segment_bias - 0.5)))
        max_parts = int(max(2, min(10, max_parts)))
        min_part_chars = int(max(2, min(8, round(3 + 2 * restraint))))
        max_part_chars = int(
            round(
                84
                - 30 * pace_drive
                - 14 * restraint
                - 24 * style_segment_bias
                + 26 * style_long * style_confidence
                + (8 if rigorous_when_requested else 0),
            ),
        )
        max_part_chars = int(max(24, min(112, max_part_chars)))
        chars_per_second = round(
            max(
                3.2,
                min(
                    11.5,
                    5.2
                    + 4.5 * pace_drive
                    - 1.4 * restraint
                    + 1.2 * (style_speed - 0.5) * style_confidence,
                ),
            ),
            3,
        )
        min_delay = round(max(0.18, min(1.45, 0.26 + 0.70 * restraint)), 3)
        max_delay = round(
            max(1.4, min(6.5, 2.4 + 2.5 * restraint + 1.1 * (1.0 - pace_drive))),
            3,
        )
        jitter = round(
            max(0.08, min(0.48, 0.12 + 0.22 * instability + 0.16 * arousal)),
            3,
        )
        settings = RealtimeChatSettings(
            enabled=base.enabled,
            max_parts=max_parts,
            min_part_chars=min_part_chars,
            max_part_chars=max_part_chars,
            chars_per_second=chars_per_second,
            min_delay_seconds=min_delay,
            max_delay_seconds=max_delay,
            jitter_ratio=jitter,
            strip_markdown=base.strip_markdown,
        )
        return settings, {
            "source": "personality_emotion_atmosphere",
            "debug_override_used": False,
            "pace_drive": round(pace_drive, 6),
            "restraint": round(restraint, 6),
            "user_style_adaptation": {
                "enabled": style_confidence > 0.0,
                "confidence": round(style_confidence, 6),
                "segment_bias": round(style_segment_bias, 6),
                "fragment_bias": round(style_fragment, 6),
                "formal_block_bias": round(style_long, 6),
                "short_turn_bias": round(style_short, 6),
                "typing_speed_bias": round(style_speed, 6),
                "natural_style": natural_style,
                "avoid_long_markdown": avoid_long_markdown,
                "rigorous_when_requested": rigorous_when_requested,
                "prefers_brief_or_silent": prefers_brief_or_silent,
                "mutual_need_mode": mutual_need_mode,
            },
            "signals": {
                "expressiveness": round(expressiveness, 6),
                "social_distance": round(social_distance, 6),
                "boundary_sensitivity": round(boundary, 6),
                "instability": round(instability, 6),
                "warmth": round(warmth, 6),
                "arousal": round(arousal, 6),
                "affiliation": round(affiliation, 6),
                "tension": round(tension, 6),
                "interrupt_risk": round(interrupt_risk, 6),
                "silence_comfort": round(silence, 6),
                "user_style_confidence": round(style_confidence, 6),
                "user_style_segment_bias": round(style_segment_bias, 6),
            },
            "values": self._realtime_chat_settings_payload(settings),
        }

    def _sticker_reaction_enabled(self) -> bool:
        return self._cfg_bool("enable_sticker_reaction", True)

    def _sticker_learning_enabled(self) -> bool:
        return self._cfg_bool("sticker_learn_user_images", True)

    def _sticker_settings(self) -> StickerSettings:
        if not self._runtime_parameter_debug_override_enabled():
            return self._base_sticker_settings()
        return StickerSettings(
            enabled=self._sticker_reaction_enabled(),
            local_root=str(self._cfg("sticker_local_root", "") or ""),
            default_repo_url=str(
                self._cfg(
                    "sticker_default_repo_url",
                    "https://github.com/zhaoolee/ChineseBQB.git",
                )
                or ""
            ),
            allowed_extensions=str(
                self._cfg("sticker_allowed_extensions", ".jpg,.jpeg,.png,.gif,.webp")
                or ""
            ),
            selected_packs=str(self._cfg("sticker_selected_packs", "") or ""),
            index_limit=max(0, self._cfg_int("sticker_index_limit", 1000)),
            max_file_bytes=max(
                1,
                self._cfg_int("sticker_max_file_bytes", 5242880),
            ),
            send_probability=max(
                0.0,
                min(1.0, self._debug_cfg_float("sticker_send_probability", 0.18)),
            ),
            learned_enabled=self._sticker_learning_enabled(),
        )

    def _base_sticker_settings(self) -> StickerSettings:
        return StickerSettings(
            enabled=self._sticker_reaction_enabled(),
            local_root=str(self._cfg("sticker_local_root", "") or ""),
            default_repo_url=str(
                self._cfg(
                    "sticker_default_repo_url",
                    "https://github.com/zhaoolee/ChineseBQB.git",
                )
                or ""
            ),
            allowed_extensions=str(
                self._cfg("sticker_allowed_extensions", ".jpg,.jpeg,.png,.gif,.webp")
                or ""
            ),
            selected_packs=str(self._cfg("sticker_selected_packs", "") or ""),
            index_limit=1000,
            max_file_bytes=5 * 1024 * 1024,
            send_probability=0.18,
            learned_enabled=self._sticker_learning_enabled(),
        )

    def _derive_sticker_settings(
        self,
        *,
        persona_profile: PersonaProfile | None,
        emotion_values: dict[str, float],
        atmosphere_values: dict[str, float],
        lifelike_snapshot: dict[str, Any] | None = None,
    ) -> tuple[StickerSettings, dict[str, Any]]:
        base = self._sticker_settings()
        if self._runtime_parameter_debug_override_enabled():
            return base, {
                "source": "debug_config_override",
                "debug_override_used": True,
                "probability": round(base.send_probability, 6),
                "reason": "runtime_parameter_debug_override_enabled",
            }
        personality_model = (
            getattr(persona_profile, "personality_model", None)
            if persona_profile is not None
            else None
        )
        factors = self._personality_derived_factors(personality_model)
        traits = self._personality_trait_scores(personality_model)
        lifelike_values = self._snapshot_values(lifelike_snapshot)
        expressiveness = self._as_float_value(factors.get("expressiveness"), 0.42)
        warmth = self._as_float_value(traits.get("interpersonal_warmth"), 0.45)
        boundary = max(
            self._as_float_value(factors.get("boundary_sensitivity"), 0.30),
            self._as_float_value(lifelike_values.get("boundary_sensitivity"), 0.24),
        )
        social_distance = self._as_float_value(factors.get("social_distance"), 0.24)
        valence = self._as_float_value(emotion_values.get("valence"), 0.0)
        arousal = abs(self._as_float_value(emotion_values.get("arousal"), 0.0))
        affiliation = self._as_float_value(emotion_values.get("affiliation"), 0.0)
        tension = self._as_float_value(atmosphere_values.get("tension"), 0.0)
        interrupt_risk = self._as_float_value(
            atmosphere_values.get("interrupt_risk"),
            0.0,
        )
        probability = self._clamp01(
            0.07
            + 0.18 * expressiveness
            + 0.15 * warmth
            + 0.10 * max(0.0, affiliation)
            + 0.08 * max(0.0, valence)
            + 0.06 * arousal
            - 0.16 * boundary
            - 0.12 * social_distance
            - 0.14 * tension
            - 0.16 * interrupt_risk,
        )
        probability = max(0.02, min(0.42, probability))
        settings = StickerSettings(
            enabled=base.enabled,
            local_root=base.local_root,
            default_repo_url=base.default_repo_url,
            allowed_extensions=base.allowed_extensions,
            selected_packs=base.selected_packs,
            index_limit=base.index_limit,
            max_file_bytes=base.max_file_bytes,
            send_probability=probability,
            learned_enabled=base.learned_enabled,
        )
        return settings, {
            "source": "personality_emotion_atmosphere",
            "debug_override_used": False,
            "probability": round(probability, 6),
            "signals": {
                "expressiveness": round(expressiveness, 6),
                "warmth": round(warmth, 6),
                "boundary_sensitivity": round(boundary, 6),
                "social_distance": round(social_distance, 6),
                "valence": round(valence, 6),
                "arousal_abs": round(arousal, 6),
                "affiliation": round(affiliation, 6),
                "tension": round(tension, 6),
                "interrupt_risk": round(interrupt_risk, 6),
            },
        }

    async def _sticker_candidates(self, session_key: str) -> list[dict[str, Any]]:
        settings = self._sticker_settings()
        candidates = self._local_sticker_index(settings)
        if settings.learned_enabled:
            candidates.extend(await self._load_sticker_memory(session_key))
        return candidates

    def _local_sticker_index(self, settings: StickerSettings) -> list[dict[str, Any]]:
        cache = getattr(self, "_sticker_index_cache", None)
        if cache is None:
            cache = {}
            self._sticker_index_cache = cache
        cache_key = json.dumps(
            {
                "root": settings.local_root,
                "extensions": settings.allowed_extensions,
                "packs": settings.selected_packs,
                "limit": settings.index_limit,
                "max_bytes": settings.max_file_bytes,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        now = self._observed_now()
        ttl = max(0.0, self._cfg_float("sticker_index_cache_ttl_seconds", 86400.0))
        cached = cache.get(cache_key)
        if cached and (ttl <= 0 or now - float(cached.get("indexed_at", 0.0)) <= ttl):
            return list(cached.get("items") or [])
        items = index_local_stickers(settings)
        cache[cache_key] = {"indexed_at": now, "items": items}
        return list(items)

    async def _load_sticker_memory(self, session_key: str) -> list[dict[str, Any]]:
        cache = getattr(self, "_sticker_memory_cache", None)
        if cache is None:
            cache = {}
            self._sticker_memory_cache = cache
        if session_key in cache:
            return [dict(item) for item in cache[session_key]]
        try:
            data = await self.get_kv_data(self._sticker_memory_kv_key(session_key), [])
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: sticker memory KV read failed: {exc}")
            data = []
        items = [dict(item) for item in data if isinstance(item, dict)] if isinstance(data, list) else []
        cache[session_key] = items
        return [dict(item) for item in items]

    async def _save_sticker_memory(
        self,
        session_key: str,
        items: list[dict[str, Any]],
    ) -> None:
        if not hasattr(self, "_sticker_memory_cache"):
            self._sticker_memory_cache = {}
        self._sticker_memory_cache[session_key] = [dict(item) for item in items]
        try:
            await self.put_kv_data(self._sticker_memory_kv_key(session_key), items)
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: sticker memory KV write failed: {exc}")

    async def _observe_stickers_background(
        self,
        event: AstrMessageEvent,
        stickers: list[dict[str, Any]],
        *,
        session_key: str,
    ) -> None:
        for sticker in stickers[:5]:
            await self.observe_sticker_usage(
                event,
                sticker,
                session_key=session_key,
                source="astrbot_event",
                commit=True,
            )

    def _extract_sticker_observations_from_event(
        self,
        event: AstrMessageEvent,
    ) -> list[dict[str, Any]]:
        candidates: list[Any] = []
        for attr in (
            "message_obj",
            "message_chain",
            "message",
            "messages",
            "raw_message",
            "chain",
        ):
            value = getattr(event, attr, None)
            if value is None:
                continue
            if isinstance(value, (list, tuple)):
                candidates.extend(value)
            else:
                candidates.append(value)
        observations: list[dict[str, Any]] = []
        for item in candidates:
            observation = self._sticker_observation_from_message_part(item)
            if observation:
                observations.append(observation)
        return observations[:8]

    def _sticker_observation_from_message_part(self, item: Any) -> dict[str, Any] | None:
        if isinstance(item, dict):
            type_text = str(item.get("type") or item.get("message_type") or "").lower()
            keys = item
        else:
            type_text = str(
                getattr(item, "type", "")
                or getattr(item, "message_type", "")
                or item.__class__.__name__,
            ).lower()
            keys = {
                name: getattr(item, name, None)
                for name in (
                    "url",
                    "file",
                    "file_path",
                    "path",
                    "file_id",
                    "id",
                    "name",
                    "filename",
                    "mime",
                    "mime_type",
                )
            }
        if not any(marker in type_text for marker in ("image", "sticker", "face", "emoji")):
            if not any(keys.get(key) for key in ("url", "file", "file_path", "path", "file_id")):
                return None
        return {
            "type": type_text or "image",
            "url": keys.get("url"),
            "path": keys.get("path") or keys.get("file") or keys.get("file_path"),
            "file_id": keys.get("file_id") or keys.get("id"),
            "name": keys.get("name") or keys.get("filename"),
            "mime": keys.get("mime") or keys.get("mime_type"),
            "interest_score": 0.55,
        }

    def _low_signal_text_profile(self, text: str) -> dict[str, Any]:
        stripped = str(text or "").strip()
        max_chars = max(1, self._cfg_int("low_signal_max_chars", 12))
        if not stripped:
            return {"is_low_signal": True, "kind": "empty"}
        lowered = stripped.lower()
        compact = "".join(ch for ch in lowered if not ch.isspace())
        short_ack = {
            "嗯",
            "嗯嗯",
            "哦",
            "哦哦",
            "好",
            "好的",
            "ok",
            "okay",
            "yes",
            "no",
            "哈哈",
            "hhh",
            "lol",
            "233",
        }
        if compact in short_ack and len(stripped) <= max_chars:
            return {"is_low_signal": True, "kind": "short_ack"}
        if len(stripped) <= max_chars and all(
            not ch.isalnum() and not "\u4e00" <= ch <= "\u9fff"
            for ch in stripped
        ):
            return {"is_low_signal": True, "kind": "punctuation_or_emoji"}
        repeated = (
            len(set(compact)) == 1
            and len(compact) >= 2
            and len(compact) <= max_chars
        )
        if repeated:
            return {"is_low_signal": True, "kind": "repeated"}
        return {"is_low_signal": False, "kind": "normal"}

    def _clean_optional_text(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _runtime_parameter_debug_override_enabled(self) -> bool:
        return self._cfg_bool("runtime_parameter_debug_override_enabled", False)

    def _clamp01(self, value: Any) -> float:
        return max(0.0, min(1.0, self._as_float_value(value, 0.0)))

    def _snapshot_values(self, snapshot: Any) -> dict[str, float]:
        if not isinstance(snapshot, dict):
            return {}
        raw = snapshot.get("values")
        if not isinstance(raw, dict):
            raw = snapshot.get("dimensions")
        if not isinstance(raw, dict):
            return {}
        return {
            str(key): self._as_float_value(value, 0.0)
            for key, value in raw.items()
        }

    def _lifelike_user_speaking_style(self, snapshot: Any) -> dict[str, float]:
        if not isinstance(snapshot, dict):
            return {}
        profile = snapshot.get("user_profile")
        if not isinstance(profile, dict):
            return {}
        raw = profile.get("speaking_style")
        if not isinstance(raw, dict):
            return {}
        result: dict[str, float] = {}
        for key, value in raw.items():
            if key == "avg_unit_chars":
                result[key] = max(1.0, min(240.0, self._as_float_value(value, 0.0)))
            else:
                result[key] = self._clamp01(value)
        return result

    def _personality_derived_factors(self, personality_model: Any) -> dict[str, float]:
        if not isinstance(personality_model, dict):
            return {}
        raw = personality_model.get("derived_factors")
        if not isinstance(raw, dict):
            return {}
        return {
            str(key): self._as_float_value(value, 0.0)
            for key, value in raw.items()
        }

    def _personality_trait_scores(self, personality_model: Any) -> dict[str, float]:
        if not isinstance(personality_model, dict):
            return {}
        raw = personality_model.get("trait_scores")
        if not isinstance(raw, dict):
            return {}
        return {
            str(key): self._as_float_value(value, 0.0)
            for key, value in raw.items()
        }

    def _realtime_chat_settings_payload(
        self,
        settings: RealtimeChatSettings,
    ) -> dict[str, Any]:
        return {
            "max_parts": settings.max_parts,
            "min_part_chars": settings.min_part_chars,
            "max_part_chars": settings.max_part_chars,
            "chars_per_second": round(settings.chars_per_second, 6),
            "min_delay_seconds": round(settings.min_delay_seconds, 6),
            "max_delay_seconds": round(settings.max_delay_seconds, 6),
            "jitter_ratio": round(settings.jitter_ratio, 6),
        }

    def _as_float_value(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _optional_float(self, value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _optional_int(self, value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _cfg(self, key: str, default: Any) -> Any:
        if not hasattr(self.config, "get"):
            return default
        value = self.config.get(key, default)
        if isinstance(value, dict) and "value" in value:
            return value["value"]
        return value

    def _debug_cfg(self, key: str, default: Any) -> Any:
        if not hasattr(self.config, "get"):
            return default
        value = self.config.get(key, default)
        if isinstance(value, dict) and "value" in value:
            return value["value"]
        return value

    def _cfg_bool(self, key: str, default: bool) -> bool:
        value = self._cfg(key, default)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on", "启用"}
        return bool(value)

    def _cfg_float(self, key: str, default: float) -> float:
        try:
            return float(self._cfg(key, default))
        except (TypeError, ValueError):
            return default

    def _cfg_int(self, key: str, default: int) -> int:
        try:
            return int(self._cfg(key, default))
        except (TypeError, ValueError):
            return default

    def _debug_cfg_float(self, key: str, default: float) -> float:
        try:
            return float(self._debug_cfg(key, default))
        except (TypeError, ValueError):
            return default

    def _debug_cfg_int(self, key: str, default: int) -> int:
        try:
            return int(self._debug_cfg(key, default))
        except (TypeError, ValueError):
            return default

    def _log_warning(self, message: str) -> None:
        writer = getattr(logger, "warning", None) or getattr(logger, "debug", None)
        if callable(writer):
            writer(message)

    def _clip_one_line(self, text: str, limit: int) -> str:
        cleaned = " ".join(str(text or "").split())
        return self._clip(cleaned, limit)

    def _head_one_line(self, text: str, limit: int) -> str:
        cleaned = " ".join(str(text or "").split())
        return self._head_text(cleaned, limit)

    def _head_text(self, text: str, limit: int) -> str:
        text = str(text or "")
        if limit <= 0:
            return ""
        if len(text) <= limit:
            return text
        return text[:limit]

    def _text_hash(self, text: str) -> str:
        value = str(text or "")
        if not value:
            return ""
        return sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:16]

    def _clip(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: limit // 2] + "\n...\n" + text[-limit // 2 :]
