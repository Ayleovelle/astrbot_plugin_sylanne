from __future__ import annotations

import contextvars
import asyncio
import datetime as dt
import json
import time
import os
import re
import inspect
import shutil
import subprocess
from bisect import bisect_right
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from collections.abc import Sequence
from typing import Any

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - zoneinfo exists on supported Python, tzdata may not.
    ZoneInfo = None

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.api.star import Context, Star, register
from astrbot.core.agent.message import TextPart

if not hasattr(filter, "on_waiting_llm_request"):
    def _missing_waiting_llm_request_decorator(*args: Any, **kwargs: Any):
        del args, kwargs

        def decorate(func: Any) -> Any:
            return func

        return decorate

    filter.on_waiting_llm_request = _missing_waiting_llm_request_decorator

try:
    from quart import jsonify, request
except Exception:  # pragma: no cover - local unit tests install lightweight AstrBot stubs only.
    jsonify = None
    request = None

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
        apply_memory_record_embedding,
        apply_memory_time_decay,
        build_memory_prompt_fragment,
        memory_embedding_text,
        memory_record_needs_embedding,
        normalize_embedding,
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
        RealtimeInputFragment,
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
        apply_memory_record_embedding,
        apply_memory_time_decay,
        build_memory_prompt_fragment,
        memory_embedding_text,
        memory_record_needs_embedding,
        normalize_embedding,
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
        RealtimeInputFragment,
        RealtimeInputSettings,
        build_realtime_input_hold_injection,
        build_realtime_input_fragment_injection,
        observe_realtime_input_fragment,
    )


PLUGIN_NAME = "astrbot_plugin_sylanne"
SYLANNE_LLM_TOOL_NAMES = frozenset(
    {
        "get_bot_emotion_state",
        "get_bot_group_atmosphere_state",
        "query_agent_state",
        "simulate_bot_emotion_update",
        "get_bot_humanlike_state",
        "get_bot_lifelike_learning_state",
        "get_bot_proactive_speech_decision",
        "request_bot_proactive_speech_dispatch",
        "get_bot_personality_drift_state",
        "get_bot_moral_repair_state",
        "get_bot_fallibility_state",
        "get_bot_integrated_self_state",
    },
)
VISIBLE_SYLANNE_LLM_TOOL_NAMES = frozenset()
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
PROACTIVE_SCHEDULER_IDLE_DELAY_SECONDS = 1800.0
PROACTIVE_SCHEDULER_NORMAL_DELAY_SECONDS = 900.0
PROACTIVE_SCHEDULER_BUSY_DELAY_SECONDS = 1200.0
PROACTIVE_SCHEDULER_WAKE_DELAY_SECONDS = 0.25
PROACTIVE_SCHEDULER_IDLE_EXIT_ROUNDS = 2
PROACTIVE_SCHEDULER_MAX_CHECKS_PER_ROUND = 1
PROACTIVE_SCHEDULER_SESSION_RECHECK_SECONDS = 3600.0
PROACTIVE_CONTEXT_WINDOW_LIMIT = 6
PROACTIVE_CONTEXT_SUMMARY_MAX_CHARS = 1800
PROACTIVE_MEMORY_RECALL_MAX_CHARS = 620
SYLANNE_MEMORY_RECALL_INJECTION_MAX_CHARS = 520
SYLANNE_MEMORY_RECALL_QUERY_MAX_CHARS = 900
SYLANNE_MEMORY_RECALL_MAX_ITEMS = 3
SYLANNE_MEMORY_RECALL_WORKSET_LIMIT = 3
SYLANNE_MEMORY_QUERY_EMBEDDING_CACHE_TTL_SECONDS = 600.0
SYLANNE_MEMORY_QUERY_EMBEDDING_CACHE_LIMIT = 96
INTERRUPTED_REPLY_BREAKPOINT_LIMIT = 4
INTERRUPTED_REPLY_INJECTION_MAX_ITEMS = 1
INTERRUPTED_REPLY_INJECTION_MAX_CHARS = 720
INTERRUPTED_REPLY_LOCAL_MAX_CHARS = 4000
REALTIME_CHAT_INTERRUPT_GRACE_SECONDS = 0.05
REALTIME_ASSISTANT_HISTORY_LIMIT = 3
REALTIME_ORDINARY_HISTORY_BACKFILL_LIMIT = 4
REALTIME_ORDINARY_HISTORY_BACKFILL_TTL_SECONDS = 900.0
REALTIME_ORDINARY_HISTORY_BACKFILL_MAX_CHARS = 1200
REALTIME_ORDINARY_HISTORY_BACKFILL_MAX_ITEMS_PER_REQUEST = 2
REALTIME_ASSISTANT_HISTORY_INJECTION_MAX_CHARS = 900
REALTIME_ASSISTANT_HISTORY_EXCERPT_CHARS = 720
REALTIME_ASSISTANT_HISTORY_RECENCY_SENSITIVE_TTL_SECONDS = 3600.0
REALTIME_RESPONSE_INTERCEPT_DEDUP_LIMIT = 32
USER_MESSAGE_WITHDRAWAL_CONTEXT_LIMIT = 4
USER_MESSAGE_WITHDRAWAL_INJECTION_MAX_CHARS = 700
RECENT_USER_CORRECTION_LIMIT = 4
RECENT_USER_CORRECTION_TTL_SECONDS = 180.0
RECENT_USER_CORRECTION_INJECTION_MAX_CHARS = 520
RECENT_USER_SCENE_LIMIT = 4
RECENT_USER_SCENE_TTL_SECONDS = 300.0
RECENT_USER_SCENE_INJECTION_MAX_CHARS = 620
ACTIVE_AGENT_PENDING_USER_TURN_LIMIT = 8
ACTIVE_AGENT_PENDING_USER_TURN_TTL_SECONDS = 180.0
ACTIVE_AGENT_FOLLOWUP_INJECTION_MAX_CHARS = 900
REALTIME_INPUT_FRAGMENT_INJECTION_MAX_CHARS = 520
REALTIME_INPUT_HOLD_INJECTION_MAX_CHARS = 360
REALTIME_INPUT_LLM_WAIT_MAX_SECONDS = 4.0


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

    @property
    def agent_owned_context(self) -> bool:
        return False


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
    "Aylovelle.S.S",
    "Soulful Yearning Lifelike AstrBot Neural Narrative Engine：维护情绪、人格、记忆、氛围和表达节奏的 Sylanne",
    "2.6.1",
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
        self._sylanne_memory_recall_worksets: dict[str, deque[MemoryRecallItem]] = {}
        self._sylanne_memory_query_embedding_cache: dict[str, tuple[float, list[float]]] = {}
        self._sylanne_memory_record_embedding_last_at: dict[str, float] = {}
        self._sylanne_memory_pending_observations: dict[str, deque[dict[str, Any]]] = {}
        self._sylanne_memory_idle_tasks: dict[str, asyncio.Task[Any]] = {}
        self._sylanne_memory_idle_generation: dict[str, int] = {}
        self._agent_identity_profile_cache: dict[str, dict[str, Any]] = {}
        self._agent_trail_cache: dict[str, deque[dict[str, Any]]] = {}
        self._agent_turn_sequence: dict[str, int] = {}
        self._engine_cache: dict[str, EmotionEngine] = {}
        self._provider_id_cache: dict[str, tuple[float, str | None]] = {}
        self._last_request_text: dict[str, str] = {}
        self._last_state_injection_diagnostics: dict[str, dict[str, Any]] = {}
        self._conversation_input_epoch: dict[str, int] = {}
        self._conversation_pending_response_epochs: dict[str, deque[int]] = {}
        self._active_agent_pending_user_turns: dict[str, deque[dict[str, Any]]] = {}
        self._realtime_input_fragment_windows: dict[str, dict[str, Any]] = {}
        self._interrupted_reply_breakpoints: dict[str, deque[dict[str, Any]]] = {}
        self._realtime_assistant_history_shadows: dict[str, deque[dict[str, Any]]] = {}
        self._realtime_ordinary_history_backfills: dict[str, deque[dict[str, Any]]] = {}
        self._realtime_response_intercept_keys: dict[str, deque[str]] = {}
        self._realtime_delivery_context_dirty: set[str] = set()
        self._realtime_delivery_context_restored: set[str] = set()
        self._realtime_user_typing_until: dict[str, float] = {}
        self._user_message_withdrawals: dict[str, deque[dict[str, Any]]] = {}
        self._recent_user_corrections: dict[str, deque[dict[str, Any]]] = {}
        self._recent_user_scene_turns: dict[str, deque[dict[str, Any]]] = {}
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
        self._background_post_checkpoint_session_tasks: dict[str, asyncio.Task[Any]] = {}
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
        self._proactive_scheduler_idle_rounds = 0
        self._proactive_scheduler_task: asyncio.Task[Any] | None = None
        self._realtime_chat_last_sent: dict[str, float] = {}
        self._last_realtime_chat_adaptive_settings: dict[str, dict[str, Any]] = {}
        self._sticker_index_cache: dict[str, Any] = {}
        self._sticker_memory_cache: dict[str, list[dict[str, Any]]] = {}
        self._state_injection_snapshot_cache: dict[str, dict[str, Any]] = {}
        self._group_atmosphere_injection_snapshot_cache: dict[str, dict[str, Any]] = {}
        self._terminating = False
        self._register_sylanne_memory_settings_page_apis()

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
        if hasattr(self, "_background_post_checkpoint_session_tasks"):
            self._background_post_checkpoint_session_tasks.clear()
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
        self._proactive_scheduler_idle_rounds = 0
        self._memory_cache.clear()
        self._psychological_memory_cache.clear()
        self._humanlike_memory_cache.clear()
        self._lifelike_learning_memory_cache.clear()
        self._personality_drift_memory_cache.clear()
        self._moral_repair_memory_cache.clear()
        self._fallibility_memory_cache.clear()
        self._group_atmosphere_memory_cache.clear()
        if hasattr(self, "_sylanne_memory_idle_tasks"):
            for task in list(self._sylanne_memory_idle_tasks.values()):
                if task is not None and not task.done():
                    task.cancel()
            await asyncio.gather(*self._sylanne_memory_idle_tasks.values(), return_exceptions=True)
        if hasattr(self, "_sylanne_memory_pending_observations"):
            for pending_session in list(self._sylanne_memory_pending_observations):
                await self._flush_sylanne_memory_pending_observations(
                    pending_session,
                    force=True,
                )
            self._sylanne_memory_pending_observations.clear()
        if hasattr(self, "_sylanne_memory_idle_tasks"):
            self._sylanne_memory_idle_tasks.clear()
        if hasattr(self, "_sylanne_memory_idle_generation"):
            self._sylanne_memory_idle_generation.clear()
        self._sylanne_memory_cache.clear()
        if hasattr(self, "_sylanne_memory_recall_worksets"):
            self._sylanne_memory_recall_worksets.clear()
        if hasattr(self, "_sylanne_memory_query_embedding_cache"):
            self._sylanne_memory_query_embedding_cache.clear()
        if hasattr(self, "_sylanne_memory_record_embedding_last_at"):
            self._sylanne_memory_record_embedding_last_at.clear()
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
        if hasattr(self, "_active_agent_pending_user_turns"):
            self._active_agent_pending_user_turns.clear()
        if hasattr(self, "_realtime_input_fragment_windows"):
            self._realtime_input_fragment_windows.clear()
        if hasattr(self, "_interrupted_reply_breakpoints"):
            self._interrupted_reply_breakpoints.clear()
        if hasattr(self, "_realtime_assistant_history_shadows"):
            self._realtime_assistant_history_shadows.clear()
        if hasattr(self, "_realtime_ordinary_history_backfills"):
            self._realtime_ordinary_history_backfills.clear()
        if hasattr(self, "_realtime_response_intercept_keys"):
            self._realtime_response_intercept_keys.clear()
        if hasattr(self, "_realtime_delivery_context_dirty"):
            self._realtime_delivery_context_dirty.clear()
        if hasattr(self, "_realtime_delivery_context_restored"):
            self._realtime_delivery_context_restored.clear()
        if hasattr(self, "_realtime_user_typing_until"):
            self._realtime_user_typing_until.clear()
        if hasattr(self, "_user_message_withdrawals"):
            self._user_message_withdrawals.clear()
        if hasattr(self, "_recent_user_corrections"):
            self._recent_user_corrections.clear()
        if hasattr(self, "_recent_user_scene_turns"):
            self._recent_user_scene_turns.clear()
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

    @filter.on_waiting_llm_request()
    async def on_waiting_llm_request(self, event: AstrMessageEvent) -> None:
        """在 AstrBot session lock 前收住连续短碎片，避免旧半句先进 LLM。"""
        if _INTERNAL_LLM_CALL.get() or not self._cfg_bool("enabled", True):
            return
        if not self._realtime_chat_enabled():
            return
        if self._napcat_recall_payload(event) or self._napcat_input_status_payload(event):
            return
        current_user_text = self._event_text(event)
        if not current_user_text.strip():
            return
        identity = self._agent_identity(event)
        session_key = identity.conversation_id
        if self._current_user_text_answers_pending_realtime_question(
            session_key,
            current_user_text,
        ):
            return
        observed_at = self._event_observed_at(event)
        payload = observe_realtime_input_fragment(
            self._realtime_input_fragment_window_cache(),
            session_key=session_key,
            speaker_key=identity.speaker_track_id
            or identity.speaker_id
            or identity.conversation_id,
            text=current_user_text,
            now=observed_at,
            settings=self._realtime_input_settings(),
        )
        self._set_waiting_realtime_input_payload(event, payload)
        if self._realtime_input_fragment_should_hold(payload):
            if await self._realtime_input_fragment_still_waiting_after_gate(
                event,
                identity,
                payload,
            ):
                self._mark_realtime_input_fragment_hold(event, None, payload)
                self._cancel_realtime_chat_dispatches_for_session(
                    session_key,
                    reason="realtime_input_fragment_waiting",
                )
                return
            self._release_realtime_input_fragment_window_if_unchanged(
                session_key,
                payload,
            )
            release_payload = dict(payload)
            release_payload["should_inject"] = True
            release_payload["should_hold"] = False
            release_payload["reason"] = "released_after_waiting_llm_stage"
            self._set_waiting_realtime_input_payload(event, release_payload)
            return
        if payload.get("should_inject"):
            blocked_payload = await self._realtime_input_release_blocked_by_llm_gate(
                event,
                identity,
                payload,
            )
            if blocked_payload is not None:
                if await self._realtime_input_blocked_release_still_waiting(
                    identity,
                    blocked_payload,
                ):
                    self._mark_realtime_input_fragment_hold(event, None, blocked_payload)
                    self._cancel_realtime_chat_dispatches_for_session(
                        session_key,
                        reason="realtime_input_fragment_waiting",
                    )
                    return
                self._release_realtime_input_fragment_window_if_unchanged(
                    session_key,
                    blocked_payload,
                )
                release_payload = dict(blocked_payload)
                release_payload["should_inject"] = True
                release_payload["should_hold"] = False
                release_payload["reason"] = "released_after_waiting_llm_stage"
                self._set_waiting_realtime_input_payload(event, release_payload)

    @filter.on_llm_request()
    async def on_llm_request(
        self,
        event: AstrMessageEvent,
        request: ProviderRequest,
    ) -> None:
        """LLM 请求前合并上下文、注入状态，并处理撤回/输入等控制事件。"""
        if _INTERNAL_LLM_CALL.get() or not self._cfg_bool("enabled", True):
            return

        if self._napcat_recall_payload(event):
            withdrawal = await self.observe_user_message_withdrawal(event, request=request)
            self._mark_control_event_no_llm_response(
                event,
                request,
                reason="user_message_withdrawal",
                payload=withdrawal,
            )
            return

        input_status = self._napcat_input_status_payload(event)
        if input_status:
            session_key = self._resolve_public_session_key(event, request=request)
            self._record_realtime_user_typing_status(session_key, input_status)
            self._mark_control_event_no_llm_response(
                event,
                request,
                reason="user_typing_status",
                payload=input_status,
            )
            return

        empty_input_status = self._empty_input_typing_status_payload(event, request)
        if empty_input_status:
            session_key = self._resolve_public_session_key(event, request=request)
            reason = "empty_input_event"
            if empty_input_status.get("dispatch_in_flight"):
                self._record_realtime_user_typing_status(session_key, empty_input_status)
                reason = "user_typing_empty_event"
            self._mark_control_event_no_llm_response(
                event,
                request,
                reason=reason,
                payload=empty_input_status,
            )
            return

        waiting_fragment_payload = self._take_waiting_realtime_input_payload(event)
        if (
            getattr(event, "_sylanne_realtime_input_hold", False)
            and str(getattr(event, "_sylanne_default_response_stop_reason", "") or "")
            == "realtime_input_fragment_waiting"
            and not waiting_fragment_payload.get("should_inject")
        ):
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
        observed_at = self._event_observed_at(event)
        current_user_text = self._event_text(event) or str(getattr(request, "prompt", "") or "")
        current_user_media_observation_text = self._current_user_media_observation_text(event)
        if not current_user_text.strip() and current_user_media_observation_text:
            current_user_text = current_user_media_observation_text
        await self._restore_realtime_delivery_context_if_needed(session_key)
        if current_user_text.strip():
            self._append_realtime_ordinary_history_backfills_if_any(
                request,
                session_key,
                current_user_text=current_user_text,
            )
        active_followup_payload = self._active_agent_followup_merge_payload(
            session_key,
            identity,
            current_user_text=current_user_text,
            current_epoch=input_epoch,
            observed_at=observed_at,
        )
        model_hint = await self._request_model_hint_for_event(event, request)
        early_injection_budget = self._state_injection_budget_for_request(
            session_key,
            request,
            model_hint=model_hint,
        )
        self._append_current_user_media_context_if_any(
            request,
            event,
            budget=early_injection_budget,
        )
        await self._observe_agent_identity(identity, now=observed_at)
        fragment_payload = waiting_fragment_payload if waiting_fragment_payload else {}
        if not self._current_user_text_answers_pending_realtime_question(
            session_key,
            current_user_text,
        ) and not fragment_payload:
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
        elif fragment_payload.get("should_inject"):
            blocked_payload = await self._realtime_input_release_blocked_by_llm_gate(
                event,
                identity,
                fragment_payload,
            )
            if blocked_payload is not None:
                if await self._realtime_input_blocked_release_still_waiting(
                    identity,
                    blocked_payload,
                ):
                    self._discard_conversation_pending_response_epoch(
                        session_key,
                        input_epoch,
                    )
                    self._mark_realtime_input_fragment_hold(
                        event,
                        request,
                        blocked_payload,
                    )
                    self._cancel_realtime_chat_dispatches_for_session(
                        session_key,
                        reason="realtime_input_fragment_waiting",
                    )
                    self._last_request_text[session_key] = self._realtime_input_hold_context_text(
                        request,
                        current_user_text,
                        blocked_payload,
                    )
                    return
                self._release_realtime_input_fragment_window_if_unchanged(
                    session_key,
                    blocked_payload,
                )
                self._append_realtime_input_released_context_if_any(
                    request,
                    blocked_payload,
                    budget=early_injection_budget,
                )
            else:
                self._append_realtime_input_fragment_payload_context(
                    request,
                    fragment_payload,
                    budget=early_injection_budget,
                )
        current_user_observation_text = (
            self._realtime_input_merged_intent_from_payload(fragment_payload)
            or current_user_text
            or request.prompt
            or ""
        )
        current_user_observation_text = self._active_agent_followup_current_text(
            active_followup_payload,
            current_user_observation_text,
        )
        self._append_active_agent_followup_merge_if_any(
            request,
            active_followup_payload,
            budget=early_injection_budget,
        )
        self._append_recent_user_scene_context_if_any(
            request,
            session_key,
            identity,
            budget=early_injection_budget,
            current_user_text=current_user_observation_text,
            observed_at=observed_at,
        )
        self._append_realtime_continuity_context_if_any(
            request,
            session_key,
            budget=early_injection_budget,
            current_user_text=current_user_observation_text,
            observed_at=observed_at,
            event=event,
        )
        self._cancel_realtime_chat_dispatches_for_session(
            session_key,
            reason="new_user_message",
        )
        context_text = self._request_to_text(request)
        self._last_request_text[session_key] = context_text
        self._record_recent_user_scene_turn(
            session_key,
            identity,
            text=current_user_observation_text,
            observed_at=observed_at,
        )
        self._record_active_agent_pending_user_turn(
            session_key,
            identity,
            input_epoch=input_epoch,
            text=(
                self._realtime_input_merged_intent_from_payload(fragment_payload)
                or current_user_text
                or request.prompt
                or ""
            ),
            observed_at=observed_at,
        )
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
                current_user_text=current_user_observation_text,
                observed_at=observed_at,
                event=event,
            )
            await self._append_sylanne_memory_recall_context_if_any(
                request,
                session_key,
                current_user_text=current_user_observation_text,
                budget=None,
                observed_at=observed_at,
                event=event,
            )
            await self._save_realtime_delivery_context_if_dirty(session_key)
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
            current_user_observation_text,
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
            self._prune_hidden_sylanne_llm_tools_if_needed(
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
                observed_at=observed_at,
                event=event,
            )
            injection_decision = self._state_injection_decision(
                session_key,
                state,
                budget=injection_budget,
            )
        else:
            injection_budget = self._state_injection_budget_for_request(
                session_key,
                request,
                model_hint=model_hint,
            )
            self._prune_hidden_sylanne_llm_tools_if_needed(
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
                observed_at=observed_at,
                event=event,
            )
            await self._append_sylanne_memory_recall_context_if_any(
                request,
                session_key,
                current_user_text=current_text,
                budget=injection_budget,
                observed_at=observed_at,
                event=event,
            )
            self._record_state_injection_diagnostics(injection_budget)
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
                observed_at=observed_at,
                event=event,
            )

        if (
            inject_state
            and realtime_chat_enabled
            and self._cfg_bool(
                "realtime_chat_style_prompt_enabled",
                False,
            )
        ):
            self._append_temp_text_part(
                request,
                realtime_style_prompt_fragment(),
                source="realtime_chat.style",
                budget=injection_budget,
            )
            self._record_state_injection_diagnostics(
                injection_budget,
                decision=injection_decision,
            )
        await self._observe_sylanne_memory_event_if_enabled(
            session_key,
            current_text,
            event=event,
            speaker_id=identity.speaker_id,
            emotion_state=state,
            personality_drift_state=personality_drift_state,
            lifelike_learning_state=lifelike_learning_state,
            group_atmosphere_state=group_atmosphere_state,
            observed_at=observed_at,
            defer_until_idle=True,
        )
        if inject_state:
            self._append_current_event_time_context_if_any(
                request,
                event,
                session_key=session_key,
                observed_at=observed_at,
                budget=None if injection_budget.added_parts > 0 else injection_budget,
            )
        await self._save_realtime_delivery_context_if_dirty(session_key)

    @filter.on_llm_response()
    async def on_llm_response(
        self,
        event: AstrMessageEvent,
        response: LLMResponse,
    ) -> None:
        """LLM 响应后更新状态，接管即时聊天发送，并写入可恢复的影子上下文。"""
        if _INTERNAL_LLM_CALL.get() or not self._cfg_bool("enabled", True):
            return

        response_text = getattr(response, "completion_text", "") or ""
        if self._response_has_tool_call_payload(response):
            return
        if self._looks_like_sylanne_tool_json_result(response_text):
            self._preserve_intercepted_completion_text(
                response,
                response_text,
                reason="sylanne_tool_json_result_suppressed",
                clear_completion=True,
            )
            self._stop_default_response_send(
                event,
                reason="sylanne_tool_json_result_suppressed",
            )
            return

        if not response_text.strip():
            return
        if self._response_already_realtime_intercepted(response):
            original_text = str(
                getattr(response, "_sylanne_intercepted_completion_text", "") or response_text,
            )
            self._preserve_intercepted_completion_text(
                response,
                original_text,
                reason="realtime_chat_response_duplicate_intercept",
            )
            self._stop_default_response_send(
                event,
                reason="realtime_chat_response_duplicate_intercept",
            )
            return
        identity = self._agent_identity(event)
        observed_at = self._event_observed_at(event)
        response_event_time = self._conversation_time_payload(observed_at, event=event)
        response_epoch = self._peek_conversation_pending_response_epoch(
            identity.conversation_id,
            event,
        )
        active_runner_followups = self._astrbot_active_runner_followup_texts(
            event,
            fallback_observed_at=observed_at,
        )
        if active_runner_followups:
            self._record_active_agent_captured_followup_turns(
                identity.conversation_id,
                identity,
                input_epoch=response_epoch,
                texts=active_runner_followups,
                observed_at=observed_at,
            )
            self._record_interrupted_reply_breakpoint(
                identity.conversation_id,
                reason="active_agent_followup_pending_before_response",
                input_epoch=response_epoch,
                full_text=response_text,
                event_time=response_event_time,
            )
            self._record_realtime_assistant_history_shadow(
                identity.conversation_id,
                full_text=response_text,
                input_epoch=response_epoch,
                source="llm_response_intercept",
                delivery_status="interrupted",
                unsent_parts=[response_text],
                event_time=response_event_time,
            )
            self._discard_conversation_pending_response_epoch_only(
                identity.conversation_id,
                response_epoch,
            )
            await self._save_realtime_delivery_context_if_dirty(identity.conversation_id)
            self._preserve_intercepted_completion_text(
                response,
                response_text,
                reason="active_agent_followup_pending_before_response",
                clear_completion=True,
            )
            self._stop_default_response_send(
                event,
                reason="active_agent_followup_pending_before_response",
            )
            return
        if self._conversation_reply_is_stale(identity.conversation_id, response_epoch):
            self._record_interrupted_reply_breakpoint(
                identity.conversation_id,
                reason="late_llm_response_after_user_message",
                input_epoch=response_epoch,
                full_text=response_text,
                event_time=response_event_time,
            )
            self._discard_conversation_pending_response_epoch_only(
                identity.conversation_id,
                response_epoch,
            )
            await self._save_realtime_delivery_context_if_dirty(identity.conversation_id)
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
        response_epoch = self._consume_conversation_pending_response_epoch(
            identity.conversation_id,
            event,
        )
        realtime_dispatch_task: asyncio.Task[Any] | None = None
        realtime_response_intercepted = False
        if self._should_intercept_realtime_chat_response(event, response_text):
            if not self._claim_realtime_response_intercept(
                identity.conversation_id,
                input_epoch=response_epoch,
                response_text=response_text,
            ):
                self._preserve_intercepted_completion_text(
                    response,
                    response_text,
                    reason="realtime_chat_response_duplicate_intercept",
                    clear_completion=True,
                )
                self._stop_default_response_send(
                    event,
                    reason="realtime_chat_response_duplicate_intercept",
                )
                return
            realtime_response_intercepted = True
            plan = await self.get_realtime_chat_plan(
                event,
                text=response_text,
                session_key=identity.conversation_id,
            )
            plan["input_epoch"] = response_epoch
            plan["full_text"] = response_text
            plan["media_parts"] = self._extract_realtime_response_media_parts(response)
            if plan.get("message_parts"):
                self._log_info(
                    f"{PLUGIN_NAME}: 即时聊天接管主回复 "
                    f"session={identity.conversation_id} "
                    f"epoch={response_epoch if response_epoch is not None else 'none'} "
                    f"原文长度={len(response_text)} "
                    f"分条数={len(plan.get('message_parts') or [])} "
                    f"预览=\"{self._clip_one_line(response_text, 180)}\"",
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
                        event_time=plan.get("event_time"),
                    )
                    self._record_realtime_assistant_history_shadow(
                        identity.conversation_id,
                        full_text=response_text,
                        input_epoch=response_epoch,
                        message_parts=plan.get("message_parts"),
                        source="llm_response_intercept",
                        delivery_status="interrupted",
                        unsent_parts=[
                            str(part.get("text") or "")
                            for part in (plan.get("message_parts") or [])
                            if isinstance(part, dict)
                        ],
                        event_time=plan.get("event_time"),
                    )
                    await self._save_realtime_delivery_context_if_dirty(
                        identity.conversation_id,
                    )
                    self._preserve_intercepted_completion_text(
                        response,
                        response_text,
                        reason="user_interrupted_before_dispatch",
                        clear_completion=True,
                    )
                    self._stop_default_response_send(
                        event,
                        reason="user_interrupted_before_dispatch",
                    )
                else:
                    self._record_realtime_assistant_history_shadow(
                        identity.conversation_id,
                        full_text=response_text,
                        input_epoch=response_epoch,
                        message_parts=plan.get("message_parts"),
                        source="llm_response_intercept",
                        delivery_status="pending_dispatch",
                        unsent_parts=[
                            str(part.get("text") or "")
                            for part in (plan.get("message_parts") or [])
                            if isinstance(part, dict)
                        ],
                        event_time=plan.get("event_time"),
                    )
                    await self._save_realtime_delivery_context_if_dirty(
                        identity.conversation_id,
                    )
                    delivery_envelope = self._build_realtime_delivery_envelope_text(
                        response_text,
                        session_key=identity.conversation_id,
                        input_epoch=response_epoch,
                        message_parts=plan.get("message_parts"),
                        event_time=plan.get("event_time"),
                    )
                    self._preserve_intercepted_completion_text(
                        response,
                        response_text,
                        reason="realtime_chat_response_intercept",
                        completion_text_override=delivery_envelope,
                    )
                    self._stop_default_response_send(
                        event,
                        reason="realtime_chat_response_intercept",
                    )
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
            if not realtime_response_intercepted:
                self._discard_conversation_pending_response_epochs_through(
                    identity.conversation_id,
                    response_epoch,
                )
                self._clear_sylanne_memory_recall_workset(identity.conversation_id)
            return

        if self._background_post_assessment_enabled():
            self._schedule_background_post_assessment(
                event,
                response_text,
            )
            if not realtime_response_intercepted:
                self._discard_conversation_pending_response_epochs_through(
                    identity.conversation_id,
                    response_epoch,
                )
                self._clear_sylanne_memory_recall_workset(identity.conversation_id)
            return

        await self._update_from_llm_response(event, response_text, observed_at=observed_at)
        if not realtime_response_intercepted:
            self._discard_conversation_pending_response_epochs_through(
                identity.conversation_id,
                response_epoch,
            )
            self._clear_sylanne_memory_recall_workset(identity.conversation_id)

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
            event=event,
            speaker_id="assistant",
            emotion_state=state,
            personality_drift_state=personality_drift_state,
            observed_at=observed_at,
            defer_until_idle=True,
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
                    self._cancel_background_post_checkpoint_task(session_key)
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
                    await self._release_realtime_temporary_context_after_background_post(
                        session_key,
                        input_epoch=result.job.input_epoch,
                        reason="background_post_skipped",
                    )
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
            if self._release_realtime_temporary_context_after_background_post_in_memory(
                session_key,
                input_epoch=job.input_epoch,
                reason="background_post_dead_letter",
            ):
                self._schedule_background_task(
                    self._save_realtime_delivery_context_if_dirty(session_key),
                    label=f"realtime_context_release_after_dead_letter:{session_key}",
                )
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

    def _background_post_checkpoint_debounce_seconds(self) -> float:
        return max(
            0.0,
            min(
                10.0,
                self._cfg_float("background_post_checkpoint_debounce_seconds", 0.75),
            ),
        )

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
        temperature: float | None = None,
        timeout_seconds: float | None = None,
    ) -> Any:
        await self._acquire_internal_assessor_llm_slot()
        try:
            call = self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=(
                    self._cfg_float("assessor_temperature", 0.1)
                    if temperature is None
                    else float(temperature)
                ),
            )
            resolved_timeout = max(
                0.0,
                self._cfg_float("assessor_timeout_seconds", 0.0)
                if timeout_seconds is None
                else float(timeout_seconds),
            )
            if resolved_timeout <= 0:
                return await call
            return await asyncio.wait_for(call, timeout=resolved_timeout)
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
        await self._release_realtime_temporary_context_after_background_post(
            session_key,
            input_epoch=result.job.input_epoch,
            reason="background_post_committed",
        )

    def _schedule_background_post_checkpoint(self, session_key: str) -> None:
        if getattr(self, "_terminating", False):
            return
        if not self._cfg_bool("background_post_queue_checkpoint_enabled", True):
            return
        recovered = getattr(self, "_background_post_recovered_sessions", set())
        if session_key not in recovered:
            return
        key = str(session_key or "global")
        generations = getattr(self, "_background_post_checkpoint_generation", None)
        if generations is None:
            generations = {}
            self._background_post_checkpoint_generation = generations
        generations[key] = int(generations.get(key) or 0) + 1
        session_tasks = getattr(self, "_background_post_checkpoint_session_tasks", None)
        if not isinstance(session_tasks, dict):
            session_tasks = {}
            self._background_post_checkpoint_session_tasks = session_tasks
        running = session_tasks.get(key)
        if running is not None and not running.done():
            return
        try:
            task = asyncio.create_task(
                self._save_background_post_checkpoint_debounced(key),
            )
        except RuntimeError:
            return
        session_tasks[key] = task
        if not hasattr(self, "_background_post_checkpoint_tasks"):
            self._background_post_checkpoint_tasks = set()
        self._background_post_checkpoint_tasks.add(task)

        def _clear_checkpoint_task(done: asyncio.Task[Any]) -> None:
            self._background_post_checkpoint_tasks.discard(done)
            if self._background_post_checkpoint_session_tasks.get(key) is done:
                self._background_post_checkpoint_session_tasks.pop(key, None)
            try:
                done.result()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.debug(f"{PLUGIN_NAME}: background checkpoint task failed: {exc}")

        task.add_done_callback(_clear_checkpoint_task)

    def _cancel_background_post_checkpoint_task(self, session_key: str) -> None:
        key = str(session_key or "global")
        session_tasks = getattr(self, "_background_post_checkpoint_session_tasks", None)
        if not isinstance(session_tasks, dict):
            return
        task = session_tasks.pop(key, None)
        if task is not None and not task.done():
            task.cancel()

    async def _save_background_post_checkpoint_debounced(
        self,
        session_key: str,
    ) -> None:
        delay = self._background_post_checkpoint_debounce_seconds()
        if delay > 0:
            await asyncio.sleep(delay)
        generations = getattr(self, "_background_post_checkpoint_generation", {})
        while True:
            before_generation = int(generations.get(session_key) or 0)
            await self._save_background_post_checkpoint_serialized(session_key)
            if int(generations.get(session_key) or 0) == before_generation:
                return
            delay = self._background_post_checkpoint_debounce_seconds()
            if delay > 0:
                await asyncio.sleep(delay)

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
            try:
                await self._kv_delete_data(key, label="background checkpoint delete")
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
        try:
            await self._kv_put_data(key, payload, label="background checkpoint save")
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
        query_embedding: list[float] = []
        embedding_provider_id = ""
        embedding_changed = False
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
        if clean_query and not items:
            try:
                query_embedding, embedding_provider_id, embedding_changed = (
                    await self._sylanne_memory_vector_recall_inputs(
                        state,
                        query=clean_query,
                        now=timestamp,
                    )
                )
            except Exception as exc:
                logger.debug(f"{PLUGIN_NAME}: Sylanne memory public vector query failed: {exc}")
            if query_embedding:
                items = recall_memory(
                    state,
                    query=clean_query,
                    now=timestamp,
                    limit=min(5, bounded_limit),
                    query_embedding=query_embedding,
                    embedding_provider_id=embedding_provider_id,
                )
        if embedding_changed:
            try:
                await self._save_sylanne_memory_state(resolved_session_key, state)
            except Exception as exc:
                logger.debug(f"{PLUGIN_NAME}: Sylanne memory public vector save failed: {exc}")
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
        topic_judgement = self._apply_proactive_topic_evidence_gate(
            topic_judgement,
            decision=decision,
            topics=topics,
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
        if not isinstance(getattr(self, "_proactive_scheduler_idle_rounds", None), int):
            self._proactive_scheduler_idle_rounds = 0
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
        self._proactive_scheduler_idle_rounds = 0
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
        if not self._proactive_candidate_sessions:
            return
        task = self._proactive_scheduler_task
        if task is not None and not task.done():
            return
        self._proactive_scheduler_task = self._schedule_background_task(
            self._proactive_scheduler_loop(),
            label="proactive_speech_scheduler",
        )

    async def _proactive_scheduler_loop(self) -> None:
        idle_rounds = 0
        await asyncio.sleep(PROACTIVE_SCHEDULER_WAKE_DELAY_SECONDS)
        while self._proactive_scheduler_enabled() and not getattr(self, "_terminating", False):
            self._prune_proactive_candidate_sessions()
            if not self._proactive_candidate_sessions:
                break
            result = await self._run_proactive_scheduler_once()
            if not self._proactive_candidate_sessions:
                break
            if self._proactive_scheduler_result_is_idle(result):
                idle_rounds += 1
                self._proactive_scheduler_idle_rounds = idle_rounds
                if self._proactive_scheduler_should_exit_after_idle(idle_rounds):
                    break
            else:
                idle_rounds = 0
                self._proactive_scheduler_idle_rounds = 0
            await asyncio.sleep(self._proactive_scheduler_next_delay(result))
        self._proactive_scheduler_idle_rounds = 0
        current = asyncio.current_task()
        if self._proactive_scheduler_task is current:
            self._proactive_scheduler_task = None

    def _proactive_scheduler_result_is_idle(self, result: dict[str, Any]) -> bool:
        if not isinstance(result, dict):
            return True
        if result.get("pressure_blocked"):
            return False
        return (
            int(result.get("checked") or 0) <= 0
            and int(result.get("dispatched") or 0) <= 0
        )

    def _proactive_scheduler_should_exit_after_idle(self, idle_rounds: int) -> bool:
        return int(idle_rounds) >= max(1, int(PROACTIVE_SCHEDULER_IDLE_EXIT_ROUNDS))

    def _proactive_scheduler_next_delay(self, result: dict[str, Any]) -> float:
        if result.get("pressure_blocked"):
            return PROACTIVE_SCHEDULER_BUSY_DELAY_SECONDS
        if self._proactive_scheduler_result_is_idle(result):
            return PROACTIVE_SCHEDULER_WAKE_DELAY_SECONDS
        candidate_count = max(0, int(result.get("candidate_count") or 0))
        touched = max(0, int(result.get("checked") or 0)) + max(
            0,
            int(result.get("skipped") or 0),
        )
        if candidate_count <= touched:
            return PROACTIVE_SCHEDULER_WAKE_DELAY_SECONDS
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
                "candidate_count": 0,
                "reason": "scheduler_disabled",
            }
        now = self._observed_now()
        self._prune_proactive_candidate_sessions(now=now)
        candidate_count = len(self._proactive_candidate_sessions)
        pressure = self._background_post_resource_pressure()
        if pressure.get("level") == "critical":
            return {
                "schema_version": "astrbot.proactive_scheduler_result.v1",
                "enabled": True,
                "checked": 0,
                "dispatched": 0,
                "skipped": len(self._proactive_candidate_sessions),
                "candidate_count": candidate_count,
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
            lock = self._proactive_scheduler_locks.setdefault(session_key, asyncio.Lock())
            if lock.locked():
                skipped += 1
                continue
            async with lock:
                await self._settle_overdue_proactive_feedback(
                    session_key,
                    observed_at=now,
                )
                last_checked = self._proactive_scheduler_last_checked.get(session_key)
                if (
                    last_checked is not None
                    and now - float(last_checked) < PROACTIVE_SCHEDULER_SESSION_RECHECK_SECONDS
                ):
                    skipped += 1
                    continue
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
            "candidate_count": candidate_count,
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
        absence_summary = self._proactive_user_absence_context_summary(candidate)
        if absence_summary:
            parts.append(absence_summary)
        feedback_summary = self._proactive_feedback_context_summary(
            str(candidate.get("session_key") or ""),
        )
        if feedback_summary:
            parts.append(feedback_summary)
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

    def _proactive_user_absence_context_summary(self, candidate: dict[str, Any]) -> str:
        now = self._observed_now()
        last_seen = self._as_float_value(candidate.get("last_seen_at"), 0.0)
        if last_seen <= 0:
            return ""
        elapsed = max(0.0, now - last_seen)
        if elapsed < 600.0:
            return ""
        minutes = int(round(elapsed / 60.0))
        duration = f"{minutes} 分钟" if minutes < 120 else f"{round(minutes / 60.0, 1)} 小时"
        try:
            hour = time.localtime(now).tm_hour
        except Exception:
            hour = -1
        if 0 <= hour < 6:
            likely_state = "当前接近深夜/清晨，用户长时间没聊天更可能是在休息或已经睡了。"
        elif 6 <= hour < 9:
            likely_state = "当前像清晨时段，用户长时间没聊天可能是在睡觉、洗漱、通勤或准备开始忙。"
        elif 9 <= hour < 18:
            likely_state = "当前像白天时段，用户长时间没聊天可能是在学习、工作、改论文或处理现实事务。"
        elif 18 <= hour < 24:
            likely_state = "当前像晚上时段，用户长时间没聊天可能是在吃饭、休息、赶任务或暂时离开手机。"
        else:
            likely_state = "用户长时间没聊天时，只能保守猜测对方可能正在忙、休息或离开手机。"
        return self._clip(
            "\n".join(
                [
                    f"距离最近用户消息约 {duration}。",
                    likely_state,
                    "可能是在忙、休息或暂时不方便聊天；不要把沉默直接解读成冷淡、无视或需要继续追问。",
                    "如果没有新的明确证据，优先沉默；如果只是想念用户，只能用轻轻敲门式短句，不要继续抓住旧话题盘问。",
                ],
            ),
            700,
        )

    def _proactive_feedback_context_summary(self, session_key: str) -> str:
        audit = getattr(self, "_proactive_dispatch_audit", None)
        if not isinstance(audit, dict):
            return ""
        entries = list(audit.get(str(session_key or "global")) or [])
        if not entries:
            return ""
        for entry in reversed(entries[-6:]):
            status = str(entry.get("feedback_status") or "")
            if status not in {"unanswered", "cold_reply", "pending"}:
                continue
            topic = str(entry.get("topic_text") or "").strip()
            evidence = str(entry.get("topic_evidence") or "").strip()
            need_mode = str(entry.get("need_mode") or "").strip()
            if status == "unanswered":
                headline = "上一条主动发言没有得到回应。"
            elif status == "cold_reply":
                headline = "上一条主动发言只收到低信号回应。"
            else:
                headline = "上一条主动发言仍在等待用户自然回应。"
            details = []
            if need_mode:
                details.append(f"上次主动需求：{need_mode}")
            if topic:
                details.append(f"上次主动话题：{topic}")
            if evidence:
                details.append(f"上次话题证据：{evidence}")
            details.append("不要重复同一个话题，也不要把同一个进度/身体状态问题隔几个小时继续追问。")
            details.append("没有新证据时沉默更自然；如果只是想念用户，使用低压力、短、可不回复的轻触达。")
            return self._clip("\n".join([headline, *details]), 700)
        return ""

    def _sylanne_memory_vector_retrieval_enabled(self) -> bool:
        return self._cfg_bool("sylanne_memory_vector_retrieval_enabled", True)

    def _sylanne_memory_record_embedding_min_interval_seconds(self) -> float:
        return max(
            0.0,
            min(
                3600.0,
                self._cfg_float("sylanne_memory_record_embedding_min_interval_seconds", 300.0),
            ),
        )

    def _sylanne_memory_record_embedding_max_per_flush(self) -> int:
        return max(
            0,
            min(
                4,
                self._cfg_int("sylanne_memory_record_embedding_max_per_flush", 1),
            ),
        )

    def _sylanne_memory_record_embedding_budget_available(
        self,
        session_key: str,
        *,
        now: float,
    ) -> bool:
        max_records = self._sylanne_memory_record_embedding_max_per_flush()
        if max_records <= 0:
            return False
        key = str(session_key or "global")
        last_by_session = getattr(self, "_sylanne_memory_record_embedding_last_at", None)
        if last_by_session is None:
            last_by_session = {}
            self._sylanne_memory_record_embedding_last_at = last_by_session
        last_at = float(last_by_session.get(key) or 0.0)
        interval = self._sylanne_memory_record_embedding_min_interval_seconds()
        return interval <= 0.0 or max(0.0, float(now) - last_at) >= interval

    def _mark_sylanne_memory_record_embedding_attempt(
        self,
        session_key: str,
        *,
        now: float,
    ) -> None:
        last_by_session = getattr(self, "_sylanne_memory_record_embedding_last_at", None)
        if last_by_session is None:
            last_by_session = {}
            self._sylanne_memory_record_embedding_last_at = last_by_session
        last_by_session[str(session_key or "global")] = float(now)

    async def _sylanne_memory_embedding_provider(self) -> tuple[Any | None, str]:
        if not self._sylanne_memory_vector_retrieval_enabled():
            return None, ""
        context = getattr(self, "context", None)
        if context is None:
            return None, ""
        configured = str(
            self._cfg("sylanne_memory_embedding_provider_id", "") or "",
        ).strip()
        provider = None
        if configured:
            getter = getattr(context, "get_provider_by_id", None)
            if callable(getter):
                try:
                    provider = getter(configured)
                    if inspect.isawaitable(provider):
                        provider = await provider
                except Exception as exc:
                    logger.debug(
                        f"{PLUGIN_NAME}: Sylanne memory embedding provider lookup failed: {exc}",
                    )
                    provider = None
        else:
            getter = getattr(context, "get_all_embedding_providers", None)
            if callable(getter):
                try:
                    providers = getter()
                    if inspect.isawaitable(providers):
                        providers = await providers
                    provider = next(iter(providers or []), None)
                except Exception as exc:
                    logger.debug(
                        f"{PLUGIN_NAME}: Sylanne memory embedding provider list failed: {exc}",
                    )
                    provider = None
        if provider is None or not callable(getattr(provider, "get_embedding", None)):
            return None, ""
        provider_id = configured or self._sylanne_memory_embedding_provider_id(provider)
        if not provider_id:
            provider_id = "default_embedding_provider"
        return provider, str(provider_id)

    def _sylanne_memory_embedding_provider_id(self, provider: Any) -> str:
        for attr in ("provider_id", "id", "name"):
            value = getattr(provider, attr, None)
            if value:
                return str(value)
        config = getattr(provider, "provider_config", None)
        if isinstance(config, dict):
            for key in ("id", "provider_id", "name"):
                value = config.get(key)
                if value:
                    return str(value)
        return ""

    def _register_sylanne_memory_settings_page_apis(self) -> None:
        registrar = getattr(getattr(self, "context", None), "register_web_api", None)
        if not callable(registrar):
            return
        registrar(
            f"/{PLUGIN_NAME}/memory-settings",
            self._sylanne_memory_settings_page_get,
            ["GET"],
            "Sylanne 记忆设置页：读取 Embedding 提供商列表",
        )
        registrar(
            f"/{PLUGIN_NAME}/memory-settings",
            self._sylanne_memory_settings_page_post,
            ["POST"],
            "Sylanne 记忆设置页：保存 Embedding 提供商选择",
        )

    async def _sylanne_memory_settings_page_get(self) -> Any:
        payload = await self._sylanne_memory_settings_page_payload()
        if callable(jsonify):
            return jsonify(payload)
        return payload

    async def _sylanne_memory_settings_page_post(self) -> Any:
        body: Any = {}
        if request is not None:
            try:
                body = await request.get_json(silent=True)
            except TypeError:
                body = await request.get_json()
            except Exception as exc:
                body = {"_request_error": str(exc)}
        payload = await self._update_sylanne_memory_settings_from_page(body)
        if callable(jsonify):
            return jsonify(payload)
        return payload

    async def _sylanne_memory_settings_page_payload(self) -> dict[str, Any]:
        providers = await self._sylanne_memory_embedding_provider_page_items()
        current = str(
            self._cfg("sylanne_memory_embedding_provider_id", "") or "",
        ).strip()
        known_ids = {str(item.get("id") or "") for item in providers}
        return {
            "schema_version": "astrbot.sylanne_memory_settings_page.v1",
            "plugin_name": PLUGIN_NAME,
            "current_embedding_provider_id": current,
            "current_provider_known": not current or current in known_ids,
            "vector_retrieval_enabled": self._cfg_bool(
                "sylanne_memory_vector_retrieval_enabled",
                True,
            ),
            "embedding_providers": providers,
            "native_config_embedding_selector_available": False,
            "notes": [
                "AstrBot 当前配置 schema 没有公开 Embedding provider 专用选择器。",
                "本页只保存 sylanne_memory_embedding_provider_id，旧配置和手填 ID 仍然兼容。",
                "留空表示自动使用当前第一个可用 Embedding 提供商。",
            ],
        }

    async def _update_sylanne_memory_settings_from_page(
        self,
        body: Any,
    ) -> dict[str, Any]:
        if not isinstance(body, dict):
            body = {}
        provider_id = str(body.get("embedding_provider_id") or "").strip()
        providers = await self._sylanne_memory_embedding_provider_page_items()
        known_ids = {str(item.get("id") or "") for item in providers}
        if provider_id and provider_id not in known_ids:
            return {
                "ok": False,
                "error": "unknown_embedding_provider",
                "current_embedding_provider_id": str(
                    self._cfg("sylanne_memory_embedding_provider_id", "") or "",
                ).strip(),
                "embedding_providers": providers,
            }
        if hasattr(self.config, "__setitem__"):
            self.config["sylanne_memory_embedding_provider_id"] = provider_id
        saver = getattr(self.config, "save_config", None)
        if callable(saver):
            result = saver()
            if inspect.isawaitable(result):
                await result
        return {
            "ok": True,
            "current_embedding_provider_id": provider_id,
            "embedding_providers": providers,
        }

    async def _sylanne_memory_embedding_provider_page_items(
        self,
    ) -> list[dict[str, Any]]:
        context = getattr(self, "context", None)
        getter = getattr(context, "get_all_embedding_providers", None)
        if not callable(getter):
            return []
        try:
            providers = getter()
            if inspect.isawaitable(providers):
                providers = await providers
        except Exception as exc:
            logger.debug(
                f"{PLUGIN_NAME}: list embedding providers for memory settings failed: {exc}",
            )
            return []
        if isinstance(providers, dict):
            iterable = providers.values()
        else:
            iterable = providers or []
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for provider in iterable:
            if provider is None or not callable(getattr(provider, "get_embedding", None)):
                continue
            provider_id = self._sylanne_memory_embedding_provider_id(provider)
            if not provider_id or provider_id in seen:
                continue
            seen.add(provider_id)
            config = getattr(provider, "provider_config", None)
            if not isinstance(config, dict):
                config = {}
            items.append(
                {
                    "id": provider_id,
                    "name": str(
                        config.get("name")
                        or config.get("display_name")
                        or getattr(provider, "name", "")
                        or provider_id,
                    ),
                    "provider_type": str(
                        config.get("provider_type")
                        or getattr(provider, "provider_type", "")
                        or "embedding",
                    ),
                    "embedding_model": str(
                        config.get("embedding_model")
                        or config.get("model")
                        or getattr(provider, "embedding_model", "")
                        or "",
                    ),
                    "embedding_dimensions": self._optional_int(
                        config.get("embedding_dimensions")
                        or config.get("dimensions")
                        or getattr(provider, "embedding_dimensions", None),
                    ),
                },
            )
        return items

    async def _sylanne_memory_embedding_for_text(
        self,
        provider: Any,
        text: str,
    ) -> list[float]:
        text = self._clip(str(text or "").strip(), 1200)
        if not text or provider is None:
            return []
        getter = getattr(provider, "get_embedding", None)
        if not callable(getter):
            return []
        try:
            embedding = getter(text)
            if inspect.isawaitable(embedding):
                embedding = await embedding
            return normalize_embedding(embedding)
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: Sylanne memory query embedding failed: {exc}")
            return []

    def _sylanne_memory_query_embedding_cache_key(
        self,
        provider_id: str,
        text: str,
    ) -> str:
        digest = sha256(str(text or "").encode("utf-8", "ignore")).hexdigest()[:32]
        return f"{provider_id}:{digest}"

    def _sylanne_memory_vectorized_record_count(
        self,
        state: SylanneMemoryState,
        *,
        provider_id: str,
    ) -> int:
        provider_id = str(provider_id or "").strip()
        if not provider_id:
            return 0
        return sum(
            1
            for record in state.records
            if str(getattr(record, "embedding_provider_id", "") or "") == provider_id
            and bool(getattr(record, "semantic_embedding", None))
        )

    async def _sylanne_memory_embedding_for_query_text(
        self,
        provider: Any,
        *,
        provider_id: str,
        text: str,
        now: float,
    ) -> list[float]:
        self._ensure_runtime_state_containers()
        provider_id = str(provider_id or "").strip()
        if not provider_id:
            return []
        key = self._sylanne_memory_query_embedding_cache_key(provider_id, text)
        cache = self._sylanne_memory_query_embedding_cache
        cached = cache.get(key)
        ttl = SYLANNE_MEMORY_QUERY_EMBEDDING_CACHE_TTL_SECONDS
        if cached is not None:
            cached_at, vector = cached
            if max(0.0, float(now) - float(cached_at)) <= ttl:
                return list(vector)
            cache.pop(key, None)
        vector = await self._sylanne_memory_embedding_for_text(provider, text)
        if vector:
            cache[key] = (float(now), list(vector))
            while len(cache) > SYLANNE_MEMORY_QUERY_EMBEDDING_CACHE_LIMIT:
                first_key = next(iter(cache))
                cache.pop(first_key, None)
        return vector

    async def _ensure_sylanne_memory_record_embeddings(
        self,
        state: SylanneMemoryState,
        *,
        provider: Any,
        provider_id: str,
        now: float,
        max_records: int = 8,
    ) -> bool:
        if provider is None or not provider_id:
            return False
        candidates = [
            record
            for record in reversed(state.records[-32:])
            if memory_record_needs_embedding(record, provider_id=provider_id)
        ][: max(0, int(max_records))]
        if not candidates:
            return False
        texts = [memory_embedding_text(record) for record in candidates]
        vectors: list[Any] = []
        batch_getter = getattr(provider, "get_embeddings", None)
        if callable(batch_getter) and len(texts) > 1:
            try:
                result = batch_getter(texts)
                if inspect.isawaitable(result):
                    result = await result
                vectors = list(result or [])
            except Exception as exc:
                logger.debug(f"{PLUGIN_NAME}: Sylanne memory batch embedding failed: {exc}")
                vectors = []
        if len(vectors) != len(candidates):
            vectors = []
            for text in texts:
                vectors.append(await self._sylanne_memory_embedding_for_text(provider, text))
        changed = False
        for record, vector in zip(candidates, vectors):
            changed = (
                apply_memory_record_embedding(
                    record,
                    vector,
                    provider_id=provider_id,
                    now=now,
                )
                or changed
            )
        if changed:
            state.updated_at = max(float(getattr(state, "updated_at", 0.0) or 0.0), now)
        return changed

    async def _sylanne_memory_vector_recall_inputs(
        self,
        state: SylanneMemoryState,
        *,
        query: str,
        now: float,
        allow_record_backfill: bool = False,
    ) -> tuple[list[float], str, bool]:
        provider, provider_id = await self._sylanne_memory_embedding_provider()
        if provider is None or not provider_id:
            return [], "", False
        changed = False
        if allow_record_backfill:
            changed = await self._ensure_sylanne_memory_record_embeddings(
                state,
                provider=provider,
                provider_id=provider_id,
                now=now,
                max_records=2,
            )
        if self._sylanne_memory_vectorized_record_count(
            state,
            provider_id=provider_id,
        ) <= 0:
            return [], provider_id, changed
        query_embedding = await self._sylanne_memory_embedding_for_query_text(
            provider,
            provider_id=provider_id,
            text=query,
            now=now,
        )
        if not query_embedding:
            return [], "", changed
        return query_embedding, provider_id, changed

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
            now = self._observed_now()
            state = await self._load_sylanne_memory_state(session_key)
            items = recall_memory(
                state,
                query=query,
                now=now,
            )
            embedding_changed = False
            if not self._filter_mature_sylanne_memory_recall_items(items):
                query_embedding, embedding_provider_id, embedding_changed = (
                    await self._sylanne_memory_vector_recall_inputs(
                        state,
                        query=query,
                        now=now,
                    )
                )
                if query_embedding:
                    items = recall_memory(
                        state,
                        query=query,
                        now=now,
                        query_embedding=query_embedding,
                        embedding_provider_id=embedding_provider_id,
                    )
                if embedding_changed:
                    await self._save_sylanne_memory_state(session_key, state)
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
        observed_at: float | None = None,
        event: AstrMessageEvent | None = None,
    ) -> bool:
        if not self._sylanne_memory_enabled():
            return False
        source = "sylanne_memory_recall"
        if budget is not None and budget.agent_owned_context:
            budget.skipped.append(
                {
                    "source": source,
                    "chars": 0,
                    "reason": "agent_owned_context",
                },
            )
            return False
        if self._request_has_temp_text_source(request, source):
            return False
        text = await self._sylanne_memory_recall_summary_for_request(
            request,
            session_key=session_key,
            current_user_text=current_user_text,
            observed_at=observed_at,
        )
        if not text:
            return False
        if observed_at is not None:
            self._append_current_event_time_context_if_any(
                request,
                event,
                session_key=session_key,
                observed_at=observed_at,
                budget=None,
            )
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
        observed_at: float | None = None,
    ) -> str:
        query = self._sylanne_memory_recall_query_for_request(
            request,
            current_user_text=current_user_text,
        )
        if not query:
            return ""
        try:
            now = self._observed_now() if observed_at is None else float(observed_at)
            state = await self._load_sylanne_memory_state(session_key, now=now)
            items = recall_memory(
                state,
                query=query,
                now=now,
            )
            embedding_changed = False
            if not self._filter_mature_sylanne_memory_recall_items(items):
                query_embedding, embedding_provider_id, embedding_changed = (
                    await self._sylanne_memory_vector_recall_inputs(
                        state,
                        query=query,
                        now=now,
                    )
                )
                if query_embedding:
                    items = recall_memory(
                        state,
                        query=query,
                        now=now,
                        query_embedding=query_embedding,
                        embedding_provider_id=embedding_provider_id,
                    )
                if embedding_changed:
                    await self._save_sylanne_memory_state(session_key, state)
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: Sylanne memory request recall failed: {exc}")
            return ""
        items = self._filter_mature_sylanne_memory_recall_items(items)
        items = self._merge_sylanne_memory_recall_workset(session_key, items)
        items = items[:SYLANNE_MEMORY_RECALL_MAX_ITEMS]
        fragment = build_memory_prompt_fragment(
            items,
            session_key=session_key,
            max_chars=SYLANNE_MEMORY_RECALL_INJECTION_MAX_CHARS,
            max_items=SYLANNE_MEMORY_RECALL_MAX_ITEMS,
            reference_weight=state.dynamics.recall_reference_weight,
            now=now,
        )
        if fragment:
            await self._reinforce_sylanne_memory_recall_items(
                session_key,
                state,
                items,
                query=query,
            )
        return fragment

    def _sylanne_memory_recall_workset_cache(
        self,
    ) -> dict[str, deque[MemoryRecallItem]]:
        cache = getattr(self, "_sylanne_memory_recall_worksets", None)
        if not isinstance(cache, dict):
            cache = {}
            self._sylanne_memory_recall_worksets = cache
        return cache

    def _clear_sylanne_memory_recall_workset(self, session_key: str) -> None:
        self._sylanne_memory_recall_workset_cache().pop(
            str(session_key or "global"),
            None,
        )

    def _merge_sylanne_memory_recall_workset(
        self,
        session_key: str,
        items: list[MemoryRecallItem],
    ) -> list[MemoryRecallItem]:
        key = str(session_key or "global")
        cache = self._sylanne_memory_recall_workset_cache()
        previous = list(cache.get(key) or ())
        combined: list[MemoryRecallItem] = []
        seen: set[str] = set()

        def append_once(item: MemoryRecallItem) -> None:
            record = item.record
            identity = (
                str(record.memory_id or "").strip()
                or self._text_hash(record.summary or record.text)
            )
            if not identity or identity in seen:
                return
            seen.add(identity)
            combined.append(item)

        for item in items:
            append_once(item)
        for item in previous:
            append_once(item)

        if combined:
            cache[key] = deque(
                combined[:SYLANNE_MEMORY_RECALL_WORKSET_LIMIT],
                maxlen=SYLANNE_MEMORY_RECALL_WORKSET_LIMIT,
            )
        else:
            cache.pop(key, None)
        return combined[:SYLANNE_MEMORY_RECALL_WORKSET_LIMIT]

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
            "[sylanne_shadow_memory]",
            "[sylanne_realtime_assistant_history]",
            "[sylanne_realtime_active_dispatch]",
            "[sylanne_interrupted_reply_breakpoint]",
            "[sylanne_realtime_delivery_status]",
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
            if stripped == "[assistant_reply_original]":
                skipping = False
                continue
            if any(marker in stripped for marker in internal_markers):
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
        observed_at = (
            self._event_observed_at(event_or_session)
            if self._looks_like_event(event_or_session)
            else self._observed_now()
        )
        plan = build_realtime_chat_plan(
            text,
            settings=realtime_settings,
            session_key=resolved_session,
            now=observed_at,
            emotion_values=emotion_values,
            atmosphere_values=atmosphere_values,
            sticker_candidates=sticker_candidates,
            sticker_settings=sticker_settings,
        )
        plan["event_time"] = self._conversation_time_payload(
            observed_at,
            event=event_or_session if self._looks_like_event(event_or_session) else None,
        )
        plan["astrbot_event_time"] = dict(plan["event_time"])
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
            False,
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
        previous_context_text = ""
        if isinstance(getattr(self, "_last_request_text", None), dict):
            previous_context_text = str(
                self._last_request_text.get(resolved_session) or "",
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
        withdrawal = {
            "schema_version": "astrbot.user_message_withdrawal.v1",
            "kind": "user_message_withdrawal",
            "session_key": resolved_session,
            "message_id": final_message_id,
            "reason": final_reason,
            "notice": recall,
            "input_epoch": epoch,
            "observed_at": now,
            "previous_user_excerpt": self._head_text(
                previous_context_text,
                USER_MESSAGE_WITHDRAWAL_INJECTION_MAX_CHARS,
            ),
            "stale_output_policy": "stop_pending_realtime_parts_and_drop_late_llm_response",
        }
        self._record_user_message_withdrawal_context(resolved_session, withdrawal)
        if isinstance(getattr(self, "_last_request_text", None), dict):
            self._last_request_text.pop(resolved_session, None)
        return withdrawal

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

    def _apply_proactive_topic_evidence_gate(
        self,
        judgement: dict[str, Any],
        *,
        decision: dict[str, Any],
        topics: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if str(judgement.get("need_mode") or "") != "progress_check":
            return judgement
        if self._has_supported_progress_topic(topics):
            return judgement
        return self._downgrade_unsupported_progress_judgement(
            judgement,
            decision=decision,
            topics=topics,
        )

    def _has_supported_progress_topic(self, topics: list[dict[str, Any]]) -> bool:
        for topic in topics:
            if str(topic.get("kind") or "") != "progress_check":
                continue
            evidence = topic.get("evidence")
            if isinstance(evidence, dict) and evidence.get("sources"):
                return True
            if str(topic.get("topic") or "").strip() and str(topic.get("reason") or "").strip():
                return True
        return False

    def _downgrade_unsupported_progress_judgement(
        self,
        judgement: dict[str, Any],
        *,
        decision: dict[str, Any],
        topics: list[dict[str, Any]],
    ) -> dict[str, Any]:
        playful = self._select_proactive_alternative_topic(
            topics,
            kinds={"playful_ping", "prank_light"},
        )
        if playful and bool(decision.get("should_speak")):
            need_mode = str(playful.get("kind") or "playful_ping")
            opening_style = "tiny_prank" if need_mode == "prank_light" else "playful_ping"
            return {
                "schema_version": "astrbot.proactive_topic_judgement.v1",
                "kind": "llm_topic_judgement",
                "should_speak": True,
                "need_mode": need_mode,
                "topic_text": "",
                "speech_intent": "进度关心缺少明确证据，改成低压力的调皮轻打扰。",
                "opening_style": opening_style,
                "topic_evidence": str(playful.get("reason") or "轻松氛围信号")[:240],
                "draft_message": self._fallback_proactive_message(need_mode, ""),
                "confidence": self._clamp01(playful.get("confidence", judgement.get("confidence", 0.0))),
                "reason": "progress_check 缺少明确进度证据，已降级为轻打扰，避免莫名其妙关心进度。",
                "source": "evidence_gate",
            }
        return {
            "schema_version": "astrbot.proactive_topic_judgement.v1",
            "kind": "llm_topic_judgement",
            "should_speak": False,
            "need_mode": "silence",
            "topic_text": "",
            "speech_intent": "进度关心缺少明确证据，沉默比硬找话更像真人。",
            "opening_style": "stay_silent",
            "topic_evidence": "没有找到近期任务、期限、未完成事项或用户要求跟进的证据。",
            "draft_message": "",
            "confidence": self._clamp01(judgement.get("confidence", 0.0)),
            "reason": "progress_check 缺少明确证据，本地门控阻断主动关心进度。",
            "source": "evidence_gate",
        }

    def _select_proactive_alternative_topic(
        self,
        topics: list[dict[str, Any]],
        *,
        kinds: set[str],
    ) -> dict[str, Any] | None:
        candidates = [
            topic
            for topic in topics
            if str(topic.get("kind") or "") in kinds
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda topic: self._as_float_value(topic.get("score"), 0.0),
        )

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
        adaptive_policy = self._derive_proactive_dispatch_policy(
            decision,
            session_key=session_key,
        )
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
        *,
        session_key: str = "",
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
        feedback_pressure = self._proactive_feedback_pressure(session_key)
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
            + 0.30 * feedback_pressure
            - 0.12 * repair_need,
        )
        max_chars = int(round(92 + 104 * urgency - 42 * restraint))
        max_chars = max(64, min(240, max_chars))
        ttl_seconds = int(round(70 + 240 * restraint + 180 * (1.0 - urgency)))
        ttl_seconds = max(60, min(600, ttl_seconds))
        cooldown_seconds = round(
            3600
            + 12600 * restraint
            + 7200 * (1.0 - urgency)
            + 9000 * feedback_pressure
            - 1800 * repair_need,
            3,
        )
        cooldown_seconds = max(3600.0, min(43200.0, cooldown_seconds))
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
            "feedback_pressure": round(feedback_pressure, 6),
            "signals": {
                "score": round(score, 6),
                "boundary": round(boundary, 6),
                "overload": round(overload, 6),
                "repair_need": round(repair_need, 6),
                "companionship_need": round(companionship, 6),
                "user_need_to_be_met": round(user_need, 6),
                "bot_need_to_express": round(bot_need, 6),
                "feedback_pressure": round(feedback_pressure, 6),
            },
        }

    def _proactive_feedback_pressure(self, session_key: str) -> float:
        audit = getattr(self, "_proactive_dispatch_audit", None)
        if not isinstance(audit, dict):
            return 0.0
        entries = list(audit.get(str(session_key or "global")) or [])[-6:]
        if not entries:
            return 0.0
        pressure = 0.0
        for index, entry in enumerate(reversed(entries), 1):
            status = str(entry.get("feedback_status") or "")
            weight = 1.0 / index
            if status == "unanswered":
                pressure += 0.34 * weight
            elif status == "cold_reply":
                pressure += 0.24 * weight
            elif status == "pending":
                pressure += 0.18 * weight
            elif status == "received_reply":
                pressure -= 0.10 * weight
        return self._clamp01(pressure)

    def _proactive_recent_activity_blocked_reason(
        self,
        session_key: str,
        dispatch: dict[str, Any],
    ) -> str:
        sessions = getattr(self, "_proactive_candidate_sessions", None)
        if not isinstance(sessions, dict):
            return ""
        candidate = sessions.get(str(session_key or "global"))
        if not isinstance(candidate, dict):
            return ""
        last_seen = self._as_float_value(candidate.get("last_seen_at"), 0.0)
        if last_seen <= 0.0:
            return ""
        age = max(0.0, self._observed_now() - last_seen)
        min_idle = self._proactive_dispatch_min_idle_seconds(dispatch)
        dispatch["quiet_gate"] = {
            "schema_version": "astrbot.proactive_quiet_gate.v1",
            "age_seconds": round(age, 3),
            "min_idle_seconds": round(min_idle, 3),
            "need_mode": str(dispatch.get("need_mode") or ""),
            "reason": "recent user activity should not be followed by immediate proactive speech",
        }
        if age < min_idle:
            return "recent_user_activity_quiet_period"
        return ""

    def _proactive_dispatch_min_idle_seconds(self, dispatch: dict[str, Any]) -> float:
        need_mode = str(dispatch.get("need_mode") or "").strip()
        base_by_mode = {
            "repair": 600.0,
            "progress_check": 1800.0,
            "user_need": 1800.0,
            "clarify": 2400.0,
            "mutual_need": 3600.0,
            "bot_need": 5400.0,
            "missing_user": 7200.0,
            "playful_ping": 7200.0,
            "prank_light": 7200.0,
        }
        base = base_by_mode.get(need_mode, 5400.0)
        policy = dispatch.get("adaptive_policy")
        policy = policy if isinstance(policy, dict) else {}
        restraint = self._clamp01(policy.get("restraint", 0.0))
        feedback_pressure = self._clamp01(policy.get("feedback_pressure", 0.0))
        if not str(dispatch.get("topic_evidence") or "").strip():
            base += 1800.0
        base += 1800.0 * restraint + 3600.0 * feedback_pressure
        return max(600.0, min(21600.0, base))

    def _fallback_proactive_message(self, need_mode: str, topic: str) -> str:
        topic = str(topic or "").strip()
        if need_mode == "progress_check":
            if topic:
                return f"那、那个……你之前提到的{topic}，现在进度还顺吗？"
            return ""
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
        if not force:
            quiet_reason = self._proactive_recent_activity_blocked_reason(
                str(dispatch.get("session_key") or ""),
                dispatch,
            )
            if quiet_reason:
                return quiet_reason
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

    async def _settle_overdue_proactive_feedback(
        self,
        session_key: str,
        *,
        observed_at: float | None = None,
    ) -> bool:
        audit = getattr(self, "_proactive_dispatch_audit", None)
        if not isinstance(audit, dict):
            return False
        entries = audit.get(str(session_key or "global"))
        if not entries:
            return False
        now = self._observed_now() if observed_at is None else float(observed_at)
        for entry in reversed(entries):
            if entry.get("feedback_status") not in {"pending", "", None}:
                continue
            if not entry.get("sent"):
                continue
            sent_at = self._as_float_value(entry.get("sent_at"), 0.0)
            if sent_at <= 0:
                continue
            window = max(
                60.0,
                self._as_float_value(entry.get("feedback_window_seconds"), 1800.0),
            )
            elapsed = max(0.0, now - sent_at)
            if elapsed <= window:
                continue
            entry["feedback_status"] = "unanswered"
            entry["feedback_observed_at"] = now
            entry["feedback_elapsed_seconds"] = round(elapsed, 6)
            topic = str(entry.get("topic_text") or "").strip()
            topic_part = f" 上一次主动话题是：{topic}。" if topic else ""
            await self.observe_lifelike_text(
                session_key=session_key,
                text=(
                    "主动发言没有得到回应；以后要先把用户可能在忙、休息或不方便聊天作为默认解释，"
                    "更谨慎地判断开口时机，降低打扰感，优先等待用户自然接话。"
                    f"{topic_part}"
                ),
                source="proactive_feedback",
                commit=True,
                observed_at=now,
            )
            await self.observe_emotion_text(
                session_key=session_key,
                text=(
                    "主动开口后没有得到回应，应该轻微失落但不责怪用户；"
                    "把沉默理解为对方可能在忙或休息，主动退一步，不重复追问同一个话题。"
                ),
                source="proactive_unanswered_feedback",
                phase="proactive_feedback",
                role="plugin",
                use_llm=False,
                commit=True,
                observed_at=now,
            )
            return True
        return False

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
        event_time = self._normalize_conversation_time_payload(
            plan.get("event_time") or plan.get("astrbot_event_time"),
            observed_at=(
                self._event_observed_at(event_or_session)
                if self._looks_like_event(event_or_session)
                else None
            ),
            event=event_or_session if self._looks_like_event(event_or_session) else None,
        )
        interrupted_reason = ""
        full_text = str(plan.get("full_text") or "").strip()
        if not full_text:
            full_text = " ".join(
                str(part.get("text") or "").strip()
                for part in parts
                if str(part.get("text") or "").strip()
            )
        media_parts = self._normalize_realtime_media_parts(plan.get("media_parts"))
        media_by_after_text_index = self._realtime_media_parts_by_after_text_index(
            media_parts,
            parts,
            full_text=full_text,
        )
        media_results: list[dict[str, Any]] = []
        sticker = plan.get("sticker") if isinstance(plan.get("sticker"), dict) else {}
        self._log_info(
            f"{PLUGIN_NAME}: 准备分条发送 "
            f"session={session_key} "
            f"source={source} "
            f"origin={self._clip_one_line(origin, 120)} "
            f"分条数={len(parts)} "
            f"媒体数={len(media_parts)} "
            f"表情={bool(sticker.get('should_send'))} "
            f"预览=\"{self._clip_one_line(full_text, 180)}\"",
        )
        self._start_realtime_chat_active_dispatch(
            session_key,
            input_epoch=input_epoch,
            full_text=full_text,
            source=source,
            event_time=event_time,
        )
        current_task = asyncio.current_task()
        if current_task is not None:
            self._register_realtime_chat_dispatch_task(session_key, current_task)
        try:
            pre_text_media = media_by_after_text_index.pop(0, [])
            for media_part in pre_text_media:
                await self._wait_for_realtime_user_typing_window(
                    session_key,
                    input_epoch=input_epoch,
                )
                if self._conversation_reply_is_stale(session_key, input_epoch):
                    interrupted_reason = "user_interrupted"
                    break
                media_result = await self._send_realtime_chat_media_part(
                    origin,
                    media_part,
                    send_message=send_message,
                    session_key=session_key,
                )
                media_results.append(media_result)
            for part in parts:
                if interrupted_reason:
                    break
                await self._wait_for_realtime_user_typing_window(
                    session_key,
                    input_epoch=input_epoch,
                )
                if self._conversation_reply_is_stale(session_key, input_epoch):
                    interrupted_reason = "user_interrupted"
                    break
                delay = max(0.0, self._as_float_value(part.get("delay_before_seconds"), 0.0))
                if delay > 0:
                    await asyncio.sleep(delay)
                await self._wait_for_realtime_user_typing_window(
                    session_key,
                    input_epoch=input_epoch,
                )
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
                self._log_info(
                    f"{PLUGIN_NAME}: 已发送分条 "
                    f"{len(results)}/{len(parts)} "
                    f"session={session_key} "
                    f"chars={len(text)} "
                    f"文本=\"{self._clip_one_line(text, 180)}\"",
                )
                inline_media = media_by_after_text_index.pop(len(results), [])
                for media_part in inline_media:
                    if self._conversation_reply_is_stale(session_key, input_epoch):
                        interrupted_reason = "user_interrupted"
                        break
                    media_result = await self._send_realtime_chat_media_part(
                        origin,
                        media_part,
                        send_message=send_message,
                        session_key=session_key,
                    )
                    media_results.append(media_result)
                if interrupted_reason:
                    break
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
        if not interrupted_reason and not self._conversation_reply_is_stale(
            session_key,
            input_epoch,
        ):
            remaining_media_parts = [
                media_part
                for _, group in sorted(media_by_after_text_index.items())
                for media_part in group
            ]
            for media_part in remaining_media_parts:
                if self._conversation_reply_is_stale(session_key, input_epoch):
                    interrupted_reason = "user_interrupted"
                    break
                media_results.append(
                    await self._send_realtime_chat_media_part(
                        origin,
                        media_part,
                        send_message=send_message,
                        session_key=session_key,
                    ),
                )
        sticker_result = None
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
                    try:
                        raw_sticker_result = await send_message(origin, sticker_message)
                    except (FileNotFoundError, OSError) as exc:
                        sticker_result = self._realtime_sticker_send_failure_result(
                            candidate,
                            judgement,
                            exc,
                            session_key=session_key,
                            sticker_message=sticker_message,
                        )
                    else:
                        sticker_result = {
                            "sent": True,
                            "judgement": judgement,
                            "result": self._bounded_scalar_or_summary(raw_sticker_result),
                        }
                        self._log_info(
                            f"{PLUGIN_NAME}: 已发送实时聊天表情 "
                            f"session={session_key} "
                            f"id={self._clip_one_line(str(candidate.get('id') or candidate.get('path') or candidate.get('url') or ''), 120)}",
                        )
                else:
                    sticker_result = {
                        "sent": False,
                        "blocked_reason": "llm_rejected",
                        "judgement": judgement,
                    }
        elif sticker:
            sticker_result = {
                "sent": False,
                "blocked_reason": str(sticker.get("reason") or "not_selected"),
                "sticker": self._bounded_scalar_or_summary(sticker),
            }
        if interrupted_reason:
            sent_texts = [str(item.get("text") or "") for item in parts[: len(results)]]
            unsent_texts = [
                str(item.get("text") or "")
                for item in parts[len(results) :]
                if str(item.get("text") or "").strip()
            ]
            self._record_interrupted_reply_breakpoint(
                session_key,
                reason=interrupted_reason,
                input_epoch=input_epoch,
                sent_parts=sent_texts,
                unsent_parts=unsent_texts,
                message_parts=parts,
                source=source,
                event_time=event_time,
            )
            if record_history_shadow:
                self._record_realtime_assistant_history_shadow(
                    session_key,
                    full_text=full_text,
                    input_epoch=input_epoch,
                    message_parts=parts,
                    source=source,
                    delivery_status="interrupted",
                    sent_parts=sent_texts,
                    unsent_parts=unsent_texts,
                    event_time=event_time,
                )
            self._finish_realtime_chat_active_dispatch(session_key)
            self._log_info(
                f"{PLUGIN_NAME}: 分条发送被用户插话打断 "
                f"session={session_key} "
                f"reason={interrupted_reason} "
                f"已发={len(results)} "
                f"未发={max(0, len(parts) - len(results))}",
            )
        elif record_history_shadow:
            self._record_realtime_assistant_history_shadow(
                session_key,
                full_text=full_text,
                input_epoch=input_epoch,
                message_parts=parts,
                source=source,
                delivery_status="delivered",
                sent_parts=[str(item.get("text") or "") for item in parts],
                event_time=event_time,
            )
            await self._release_realtime_temporary_context_after_background_post(
                session_key,
                input_epoch=input_epoch,
                reason="realtime_dispatch_delivered",
            )
        if not interrupted_reason:
            self._discard_conversation_pending_response_epochs_through(
                session_key,
                input_epoch,
            )
            self._clear_sylanne_memory_recall_workset(session_key)
        await self._save_realtime_delivery_context_if_dirty(session_key)
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
            "event_time": event_time,
            "trigger_event_time": event_time,
        }
        if interrupted_reason:
            payload["interrupted_reason"] = interrupted_reason
        else:
            self._log_info(
                f"{PLUGIN_NAME}: 分条发送完成 "
                f"session={session_key} "
                f"已发={len(results)} "
                f"媒体={payload['media_count']} "
                f"表情={bool(sticker_result and sticker_result.get('sent'))}",
            )
        return payload

    async def _send_realtime_chat_media_part(
        self,
        origin: str,
        media_part: dict[str, Any],
        *,
        send_message: Any,
        session_key: str,
    ) -> dict[str, Any]:
        media_message = self._build_astrbot_media_message(media_part)
        if media_message is None:
            return {
                "index": media_part.get("index"),
                "sent": False,
                "blocked_reason": "unsupported_media_part",
            }
        try:
            raw_media_result = await send_message(origin, media_message)
        except (FileNotFoundError, OSError) as exc:
            return self._realtime_media_send_failure_result(
                media_part,
                exc,
                session_key=session_key,
                media_message=media_message,
            )
        self._log_info(
            f"{PLUGIN_NAME}: 已发送实时聊天媒体 "
            f"session={session_key} "
            f"index={media_part.get('index')} "
            f"kind={media_part.get('kind')}",
        )
        return {
            "index": media_part.get("index"),
            "sent": True,
            "media_kind": media_part.get("kind"),
            "message_type": type(media_message).__name__,
            "result": self._bounded_scalar_or_summary(raw_media_result),
        }

    def _realtime_media_send_failure_result(
        self,
        media_part: dict[str, Any],
        exc: OSError,
        *,
        session_key: str,
        media_message: Any,
    ) -> dict[str, Any]:
        missing = isinstance(exc, FileNotFoundError) or getattr(exc, "errno", None) == 2
        reason = "missing_local_media_file" if missing else "media_send_failed"
        value = str(
            media_part.get("value")
            or media_part.get("path")
            or media_part.get("url")
            or "",
        )
        self._log_warning(
            f"{PLUGIN_NAME}: 实时聊天媒体发送被跳过 "
            f"session={session_key} "
            f"reason={reason} "
            f"kind={media_part.get('kind')} "
            f"value={self._clip_one_line(value, 160)} "
            f"error={self._clip_one_line(str(exc), 160)}",
        )
        return {
            "index": media_part.get("index"),
            "sent": False,
            "blocked_reason": reason,
            "media_kind": media_part.get("kind"),
            "message_type": type(media_message).__name__,
            "value_excerpt": self._clip_one_line(value, 160),
            "error": self._clip_one_line(str(exc), 160),
        }

    def _realtime_sticker_send_failure_result(
        self,
        candidate: dict[str, Any],
        judgement: dict[str, Any],
        exc: OSError,
        *,
        session_key: str,
        sticker_message: Any,
    ) -> dict[str, Any]:
        missing = isinstance(exc, FileNotFoundError) or getattr(exc, "errno", None) == 2
        reason = "missing_local_media_file" if missing else "sticker_send_failed"
        value = str(candidate.get("path") or candidate.get("url") or candidate.get("id") or "")
        self._log_warning(
            f"{PLUGIN_NAME}: 实时聊天表情发送被跳过 "
            f"session={session_key} "
            f"reason={reason} "
            f"id={self._clip_one_line(value, 160)} "
            f"error={self._clip_one_line(str(exc), 160)}",
        )
        return {
            "sent": False,
            "blocked_reason": reason,
            "judgement": judgement,
            "message_type": type(sticker_message).__name__,
            "candidate": self._bounded_scalar_or_summary(candidate),
            "error": self._clip_one_line(str(exc), 160),
        }

    def _realtime_media_parts_by_after_text_index(
        self,
        media_parts: Sequence[dict[str, Any]],
        text_parts: Sequence[dict[str, Any]],
        *,
        full_text: str,
    ) -> dict[int, list[dict[str, Any]]]:
        if not media_parts:
            return {}
        text_count = len(list(text_parts or []))
        if text_count <= 0:
            return {0: [dict(item) for item in media_parts if isinstance(item, dict)]}
        text_ends = self._realtime_dispatch_text_part_end_offsets(text_parts, full_text)
        grouped: dict[int, list[dict[str, Any]]] = {}
        for media_part in media_parts:
            if not isinstance(media_part, dict):
                continue
            anchor_offset = self._optional_int(media_part.get("anchor_offset"))
            if anchor_offset is not None and text_ends:
                after_text_index = min(
                    text_count,
                    bisect_right(text_ends, max(0, anchor_offset)),
                )
            else:
                after_text_index = self._optional_int(media_part.get("after_text_index"))
                if after_text_index is None:
                    after_text_index = text_count
            after_text_index = max(0, min(text_count, int(after_text_index)))
            grouped.setdefault(after_text_index, []).append(dict(media_part))
        return grouped

    def _realtime_dispatch_text_part_end_offsets(
        self,
        text_parts: Sequence[dict[str, Any]],
        full_text: str,
    ) -> list[int]:
        source = str(full_text or "")
        cursor = 0
        ends: list[int] = []
        for part in text_parts:
            text = str(part.get("text") or "").strip() if isinstance(part, dict) else ""
            if not text:
                ends.append(cursor)
                continue
            position = source.find(text, cursor)
            if position < 0:
                position = source.find(text)
            if position < 0:
                cursor = min(len(source), cursor + len(text))
            else:
                cursor = position + len(text)
            ends.append(cursor)
        return ends

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
        if local.get("approved"):
            return local
        if not self._cfg_bool("sticker_llm_consistency_check_enabled", False):
            return local
        event = event_or_session if self._looks_like_event(event_or_session) else None
        if event is None or not self._cfg_bool("use_llm_assessor", True):
            return local
        provider_id = await self._fast_assessor_provider_id(event)
        if not provider_id:
            return local
        prompt = self._build_sticker_consistency_prompt(
            plan=plan,
            sticker=sticker,
            candidate=candidate,
        )
        prompt = prompt[: self._fast_assessor_max_context_chars()]
        token = _INTERNAL_LLM_CALL.set(True)
        try:
            llm_resp = await self._call_internal_assessor_llm(
                provider_id=provider_id,
                prompt=prompt,
                system_prompt="你是插件内部表情包一致性检查器，只输出 JSON。",
                temperature=self._cfg_float("fast_assessor_temperature", 0.0),
                timeout_seconds=self._cfg_float("fast_assessor_timeout_seconds", 2.0),
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
        text_seen_chars = 0
        text_item_count = 0
        for item in raw_items:
            text_value = self._realtime_text_from_message_part(item)
            if text_value:
                text_seen_chars += len(text_value)
                text_item_count += 1
                continue
            media = self._realtime_media_part_from_message_part(item)
            if not media:
                continue
            key = (str(media.get("kind") or ""), str(media.get("value") or ""))
            if key in seen:
                continue
            seen.add(key)
            media["index"] = len(media_parts)
            media["anchor_offset"] = text_seen_chars
            media["after_text_index"] = text_item_count
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

    def _realtime_text_from_message_part(self, item: Any) -> str:
        kind = ""
        value: Any = None
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
            value = item.get("text") or item.get("content") or item.get("value")
        else:
            kind = str(
                getattr(item, "type", "")
                or getattr(item, "kind", "")
                or getattr(item, "message_type", "")
                or item.__class__.__name__
            )
            value = (
                getattr(item, "text", None)
                or getattr(item, "content", None)
                or getattr(item, "value", None)
            )
        lowered = kind.lower()
        if not any(marker in lowered for marker in ("plain", "text", "message")):
            if any(marker in lowered for marker in ("image", "sticker", "face", "emoji")):
                return ""
        text = str(value or "").strip()
        return text

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
        if not url and path.lower().startswith(("http://", "https://")):
            url = path
            path = ""
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
        completion_text_override: str | None = None,
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
        elif completion_text_override is not None:
            try:
                setattr(response, "completion_text", str(completion_text_override or ""))
            except Exception:
                pass

    def _response_has_tool_call_payload(self, response: LLMResponse | Any) -> bool:
        for node in self._response_tool_call_candidate_nodes(response):
            role = str(self._read_response_field(node, "role") or "").strip().lower()
            if role in {"tool", "function"}:
                return True
            finish_reason = str(
                self._read_response_field(node, "finish_reason") or "",
            ).strip().lower()
            if finish_reason in {"tool_calls", "function_call"}:
                return True
            for field in (
                "tool_calls",
                "function_call",
                "tools_call_args",
                "tools_call_name",
                "tools_call_id",
                "tool_call_id",
            ):
                if self._response_field_has_payload(
                    self._read_response_field(node, field),
                ):
                    return True
        return False

    def _looks_like_sylanne_tool_json_result(self, text: str) -> bool:
        raw = str(text or "").strip()
        if not raw or not raw.startswith("{"):
            return False
        head = raw[:4096]
        if '"schema_version"' not in head or '"kind"' not in head:
            return False
        try:
            payload = json.loads(raw)
        except Exception:
            return False
        if not isinstance(payload, dict):
            return False
        schema = str(payload.get("schema_version") or "").strip()
        kind = str(payload.get("kind") or "").strip()
        if not schema or not kind or not schema.startswith("astrbot."):
            return False
        internal_schemas = {
            PUBLIC_SCHEMA_VERSION,
            PUBLIC_MEMORY_SCHEMA_VERSION,
            PUBLIC_PERSONALITY_PROFILE_SCHEMA_VERSION,
            PUBLIC_SCREENING_SCHEMA_VERSION,
            PUBLIC_HUMANLIKE_SCHEMA_VERSION,
            PUBLIC_MORAL_REPAIR_SCHEMA_VERSION,
            PUBLIC_INTEGRATED_SELF_SCHEMA_VERSION,
            PUBLIC_LIFELIKE_LEARNING_SCHEMA_VERSION,
            PUBLIC_PERSONALITY_DRIFT_SCHEMA_VERSION,
            PUBLIC_FALLIBILITY_SCHEMA_VERSION,
            PUBLIC_GROUP_ATMOSPHERE_SCHEMA_VERSION,
            PUBLIC_MEMORY_STORE_SCHEMA_VERSION,
            "astrbot.agent_state_query.v1",
            "astrbot.agent_runtime_diagnostics.v1",
            "astrbot.agent_identity.v1",
            "astrbot.agent_trail.v1",
            "astrbot.agent_trail_item.v1",
            "astrbot.agent_trail_compacted.v1",
            "astrbot.background_post_queue.v2",
            "astrbot.interrupted_reply_breakpoint.v1",
            "astrbot.proactive_candidate_session.v1",
            "astrbot.proactive_dispatch_audit.v1",
            "astrbot.proactive_dispatch_request.v1",
            "astrbot.proactive_dispatch_result.v1",
            "astrbot.proactive_quiet_gate.v1",
            "astrbot.proactive_scheduler_result.v1",
            "astrbot.proactive_topic_judgement.v1",
            "astrbot.realtime_assistant_history_shadow.v1",
            "astrbot.realtime_ordinary_history_backfill.v1",
            "astrbot.realtime_chat_active_dispatch.v1",
            "astrbot.realtime_chat_dispatch_result.v1",
            "astrbot.realtime_input_fragments.v1",
            "astrbot.shadow_diagnostics.v1",
            "astrbot.sticker_memory_result.v1",
            "astrbot.sylanne_memory_settings_page.v1",
            "astrbot.tool_result.v1",
            "astrbot.user_message_withdrawal.v1",
        }
        internal_kinds = {
            "agent_runtime_diagnostics",
            "agent_state_query",
            "agent_trail",
            "compacted_low_signal",
            "emotion_annotated_memory",
            "emotion_state",
            "fallibility_state",
            "fallibility_state_at_write",
            "group_atmosphere_state",
            "humanlike_state",
            "humanlike_state_at_write",
            "integrated_self_compatibility_probe",
            "integrated_self_diagnostics",
            "integrated_self_policy_plan",
            "integrated_self_replay_bundle",
            "integrated_self_replay_result",
            "integrated_self_state",
            "integrated_self_state_at_write",
            "interrupted_reply_breakpoint",
            "lifelike_initiative_policy",
            "lifelike_learning_state",
            "lifelike_learning_state_at_write",
            "llm_topic_judgement",
            "moral_repair_state",
            "moral_repair_state_at_write",
            "personality_drift_state",
            "personality_drift_state_at_write",
            "proactive_dispatch_request",
            "proactive_dispatch_result",
            "proactive_scheduler_result",
            "psychological_screening_state",
            "realtime_assistant_history_shadow",
            "realtime_ordinary_history_backfill",
            "realtime_chat_active_dispatch",
            "realtime_chat_dispatch_result",
            "realtime_chat_plan",
            "realtime_user_message_fragment_window",
            "realtime_user_message_fragments",
            "shadow_diagnostics",
            "state_annotations_at_write",
            "sticker_memory_item",
            "sticker_memory_result",
            "sylanne_memory_query",
            "tool_result",
            "user_message_withdrawal",
        }
        return schema in internal_schemas or kind in internal_kinds

    def _response_tool_call_candidate_nodes(self, response: Any) -> list[Any]:
        if response is None:
            return []
        nodes = [response]
        for field in ("message", "choice", "raw_response", "raw_completion"):
            value = self._read_response_field(response, field)
            if value is not None:
                nodes.append(value)
        choices = self._read_response_field(response, "choices")
        if isinstance(choices, Sequence) and not isinstance(choices, (str, bytes, bytearray)):
            for choice in list(choices)[:2]:
                nodes.append(choice)
                message = self._read_response_field(choice, "message")
                if message is not None:
                    nodes.append(message)
        return nodes

    def _read_response_field(self, node: Any, field: str) -> Any:
        if node is None:
            return None
        if isinstance(node, dict):
            return node.get(field)
        try:
            return getattr(node, field)
        except Exception:
            return None

    def _response_field_has_payload(self, value: Any) -> bool:
        if value is None or value is False:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, tuple, set, frozenset, dict)):
            return bool(value)
        return True

    def _build_realtime_delivery_envelope_text(
        self,
        text: str,
        *,
        session_key: str,
        input_epoch: int | None,
        message_parts: Sequence[dict[str, Any]] | None = None,
        event_time: dict[str, Any] | None = None,
    ) -> str:
        original = str(text or "").strip()
        parts = [
            str(part.get("text") or "").strip()
            for part in (message_parts or [])
            if str(part.get("text") or "").strip()
        ]
        planned_parts = len(parts) if parts else (1 if original else 0)
        time_fields = self._event_time_field_line(event_time)
        header = "\n".join(
            [
                "[sylanne_realtime_delivery_status]",
                "If Sylanne is disabled or removed later, keep this envelope as assistant shadow continuity metadata.",
                "以下是 bot 刚生成的完整回复原文，但已被 Sylanne 即时聊天模块接管；AstrBot 默认发送口已被阻断，这不等于已经全部发给用户。",
                "后续如果用户插话，请以 Sylanne 记录的实际已发送/未发送状态为准，不要假设用户已经读完整段回复。",
                (
                    "delivery_status=pending_dispatch; "
                    f"planned_parts={planned_parts}; sent_parts=0; "
                    f"unsent_parts={planned_parts}; input_epoch={'' if input_epoch is None else input_epoch}; "
                    f"session={self._head_one_line(str(session_key or 'global'), 80)}; "
                    f"full_hash={self._text_hash(original)[:16]}"
                    + (f"; {time_fields}" if time_fields else "")
                ),
                "[assistant_reply_original]",
            ],
        )
        return (header + "\n" + original).strip()

    def _stop_default_response_send(
        self,
        event: AstrMessageEvent,
        *,
        reason: str,
    ) -> bool:
        for name, value in (
            ("_sylanne_default_response_stopped", True),
            ("_sylanne_default_response_stop_reason", str(reason or "")),
        ):
            try:
                setattr(event, name, value)
            except Exception:
                pass
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
        return stopped

    def _should_intercept_realtime_chat_response(
        self,
        event: AstrMessageEvent,
        response_text: str,
    ) -> bool:
        if not self._realtime_chat_enabled():
            return False
        if not self._cfg_bool("realtime_chat_intercept_llm_response", False):
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

    def _conversation_has_pending_response_epoch(self, session_key: str) -> bool:
        self._ensure_conversation_epoch_state()
        key = str(session_key or "global")
        return bool(self._conversation_pending_response_epochs.get(key))

    def _peek_conversation_pending_response_epoch(
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
        key = str(session_key or "global")
        pending = self._conversation_pending_response_epochs.get(key)
        if pending:
            return int(pending[0])
        return self._conversation_response_epoch(key, event)

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
        self._discard_active_agent_pending_user_turn(key, int(input_epoch))

    def _discard_conversation_pending_response_epoch_only(
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
            self._discard_active_agent_pending_user_turn(key, event_epoch)
            return event_epoch
        if pending:
            epoch = pending.popleft()
            if not pending:
                self._conversation_pending_response_epochs.pop(key, None)
            self._discard_active_agent_pending_user_turn(key, int(epoch))
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

    def _active_agent_pending_user_turn_cache(
        self,
    ) -> dict[str, deque[dict[str, Any]]]:
        cache = getattr(self, "_active_agent_pending_user_turns", None)
        if not isinstance(cache, dict):
            cache = {}
            self._active_agent_pending_user_turns = cache
        return cache

    def _active_agent_speaker_key(self, identity: ConversationIdentity) -> str:
        return str(
            identity.speaker_track_id
            or identity.speaker_id
            or identity.conversation_id
            or "unknown",
        )

    def _prune_active_agent_pending_user_turns(
        self,
        session_key: str,
        *,
        now: float | None = None,
    ) -> None:
        key = str(session_key or "global")
        queue = self._active_agent_pending_user_turn_cache().get(key)
        if not queue:
            return
        observed_now = self._observed_now() if now is None else float(now)
        ttl = max(0.0, ACTIVE_AGENT_PENDING_USER_TURN_TTL_SECONDS)
        kept = [
            item
            for item in queue
            if ttl <= 0 or observed_now - float(item.get("observed_at") or 0.0) <= ttl
        ]
        if not kept:
            self._active_agent_pending_user_turn_cache().pop(key, None)
            return
        self._active_agent_pending_user_turn_cache()[key] = deque(
            kept[-ACTIVE_AGENT_PENDING_USER_TURN_LIMIT:],
            maxlen=ACTIVE_AGENT_PENDING_USER_TURN_LIMIT,
        )

    def _record_active_agent_pending_user_turn(
        self,
        session_key: str,
        identity: ConversationIdentity,
        *,
        input_epoch: int | None,
        text: str,
        observed_at: float,
    ) -> None:
        value = " ".join(str(text or "").split()).strip()
        if input_epoch is None or not value:
            return
        key = str(session_key or "global")
        self._prune_active_agent_pending_user_turns(key, now=observed_at)
        queue = self._active_agent_pending_user_turn_cache().setdefault(
            key,
            deque(maxlen=ACTIVE_AGENT_PENDING_USER_TURN_LIMIT),
        )
        if queue.maxlen != ACTIVE_AGENT_PENDING_USER_TURN_LIMIT:
            queue = deque(queue, maxlen=ACTIVE_AGENT_PENDING_USER_TURN_LIMIT)
            self._active_agent_pending_user_turn_cache()[key] = queue
        epoch = int(input_epoch)
        kept = [item for item in queue if int(item.get("input_epoch") or 0) != epoch]
        if len(kept) != len(queue):
            queue = deque(kept, maxlen=ACTIVE_AGENT_PENDING_USER_TURN_LIMIT)
            self._active_agent_pending_user_turn_cache()[key] = queue
        queue.append(
            {
                "schema_version": "astrbot.active_agent_pending_user_turn.v1",
                "kind": "active_agent_pending_user_turn",
                "session_key": key,
                "speaker_key": self._active_agent_speaker_key(identity),
                "input_epoch": epoch,
                "observed_at": float(observed_at),
                "text": self._head_one_line(value, 240),
                "hash": self._text_hash(value),
            },
        )

    def _record_active_agent_captured_followup_turns(
        self,
        session_key: str,
        identity: ConversationIdentity,
        *,
        input_epoch: int | None,
        texts: Sequence[Any],
        observed_at: float,
    ) -> None:
        entries: list[dict[str, Any]] = []
        for offset, item in enumerate(texts, start=1):
            if isinstance(item, dict):
                raw_text = item.get("text")
                item_observed_at = self._as_float_value(
                    item.get("observed_at"),
                    float(observed_at) + offset * 0.0001,
                )
                followup_order = int(item.get("followup_order") or item.get("order_seq") or offset)
            else:
                raw_text = item
                item_observed_at = float(observed_at) + offset * 0.0001
                followup_order = offset
            text = " ".join(str(raw_text or "").split()).strip()
            if not text:
                continue
            entries.append(
                {
                    "text": text,
                    "observed_at": item_observed_at,
                    "followup_order": followup_order,
                },
            )
        if input_epoch is None or not entries:
            return
        key = str(session_key or "global")
        self._prune_active_agent_pending_user_turns(key, now=observed_at)
        queue = self._active_agent_pending_user_turn_cache().setdefault(
            key,
            deque(maxlen=ACTIVE_AGENT_PENDING_USER_TURN_LIMIT),
        )
        if queue.maxlen != ACTIVE_AGENT_PENDING_USER_TURN_LIMIT:
            queue = deque(queue, maxlen=ACTIVE_AGENT_PENDING_USER_TURN_LIMIT)
            self._active_agent_pending_user_turn_cache()[key] = queue
        speaker_key = self._active_agent_speaker_key(identity)
        existing_keys = {
            (
                str(item.get("source") or ""),
                int(item.get("input_epoch") or 0),
                str(item.get("hash") or ""),
            )
            for item in queue
            if isinstance(item, dict)
        }
        epoch = int(input_epoch)
        for offset, entry in enumerate(entries, start=1):
            text = str(entry.get("text") or "")
            clipped = self._head_one_line(text, 240)
            text_hash = self._text_hash(clipped)
            dedup_key = ("astrbot_active_runner_followup", epoch, text_hash)
            if dedup_key in existing_keys:
                continue
            queue.append(
                {
                    "schema_version": "astrbot.active_agent_pending_user_turn.v1",
                    "kind": "active_agent_pending_user_turn",
                    "session_key": key,
                    "speaker_key": speaker_key,
                    "input_epoch": epoch,
                    "followup_order": int(entry.get("followup_order") or offset),
                    "observed_at": self._as_float_value(
                        entry.get("observed_at"),
                        float(observed_at) + offset * 0.0001,
                    ),
                    "text": clipped,
                    "hash": text_hash,
                    "source": "astrbot_active_runner_followup",
                },
            )
            existing_keys.add(dedup_key)

    def _discard_active_agent_pending_user_turn(
        self,
        session_key: str,
        input_epoch: int | None,
    ) -> None:
        if input_epoch is None:
            return
        key = str(session_key or "global")
        queue = self._active_agent_pending_user_turn_cache().get(key)
        if not queue:
            return
        epoch = int(input_epoch)
        kept = [item for item in queue if int(item.get("input_epoch") or 0) != epoch]
        if not kept:
            self._active_agent_pending_user_turn_cache().pop(key, None)
            return
        self._active_agent_pending_user_turn_cache()[key] = deque(
            kept[-ACTIVE_AGENT_PENDING_USER_TURN_LIMIT:],
            maxlen=ACTIVE_AGENT_PENDING_USER_TURN_LIMIT,
        )

    def _discard_active_agent_pending_user_turns_through(
        self,
        session_key: str,
        input_epoch: int | None,
    ) -> None:
        if input_epoch is None:
            return
        key = str(session_key or "global")
        queue = self._active_agent_pending_user_turn_cache().get(key)
        if not queue:
            return
        epoch = int(input_epoch)
        kept = [item for item in queue if int(item.get("input_epoch") or 0) > epoch]
        if not kept:
            self._active_agent_pending_user_turn_cache().pop(key, None)
            return
        self._active_agent_pending_user_turn_cache()[key] = deque(
            kept[-ACTIVE_AGENT_PENDING_USER_TURN_LIMIT:],
            maxlen=ACTIVE_AGENT_PENDING_USER_TURN_LIMIT,
        )

    def _discard_conversation_pending_response_epochs_through(
        self,
        session_key: str,
        input_epoch: int | None,
    ) -> None:
        if input_epoch is None:
            return
        self._ensure_conversation_epoch_state()
        key = str(session_key or "global")
        epoch = int(input_epoch)
        pending = self._conversation_pending_response_epochs.get(key)
        if pending:
            kept = [value for value in pending if int(value) > epoch]
            if kept:
                self._conversation_pending_response_epochs[key] = deque(
                    kept[-12:],
                    maxlen=12,
                )
            else:
                self._conversation_pending_response_epochs.pop(key, None)
        self._discard_active_agent_pending_user_turns_through(key, epoch)

    def _active_agent_followup_merge_payload(
        self,
        session_key: str,
        identity: ConversationIdentity,
        *,
        current_user_text: str,
        current_epoch: int | None,
        observed_at: float,
    ) -> dict[str, Any]:
        current = " ".join(str(current_user_text or "").split()).strip()
        if not current or current_epoch is None:
            return {}
        key = str(session_key or "global")
        self._prune_active_agent_pending_user_turns(key, now=observed_at)
        queue = self._active_agent_pending_user_turn_cache().get(key)
        if not queue:
            return {}
        speaker_key = self._active_agent_speaker_key(identity)
        previous = [
            item
            for item in queue
            if int(item.get("input_epoch") or 0) < int(current_epoch)
            and str(item.get("speaker_key") or "") == speaker_key
            and str(item.get("text") or "").strip()
        ]
        if not previous:
            return {}
        previous.sort(
            key=lambda item: (
                self._as_float_value(item.get("observed_at"), 0.0),
                int(item.get("input_epoch") or 0),
                int(item.get("followup_order") or 0),
            ),
        )
        previous = previous[-7:]
        previous_texts = [str(item.get("text") or "").strip() for item in previous]
        ordered_current_intent = [
            {
                "text": text,
                "observed_at": self._as_float_value(item.get("observed_at"), observed_at),
                "input_epoch": int(item.get("input_epoch") or 0),
                "followup_order": int(item.get("followup_order") or 0),
            }
            for item, text in zip(previous, previous_texts)
            if text
        ]
        ordered_current_intent.append(
            {
                "text": current,
                "observed_at": float(observed_at),
                "input_epoch": int(current_epoch),
                "followup_order": 0,
            },
        )
        ordered_current_intent.sort(
            key=lambda item: (
                self._as_float_value(item.get("observed_at"), 0.0),
                int(item.get("input_epoch") or 0),
                int(item.get("followup_order") or 0),
            ),
        )
        merged = self._head_one_line(
            " / ".join(str(item.get("text") or "") for item in ordered_current_intent),
            420,
        )
        return {
            "schema_version": "astrbot.active_agent_followup_merge.v1",
            "kind": "active_agent_followup_merge",
            "session_key": key,
            "speaker_key": speaker_key,
            "current_epoch": int(current_epoch),
            "pending_count": len(previous),
            "previous_turns": previous,
            "current_user": self._head_one_line(current, 240),
            "merged_current_user": merged,
            "merged_turn_order": ordered_current_intent,
            "observed_at": float(observed_at),
        }

    def _active_agent_followup_current_text(
        self,
        payload: dict[str, Any] | None,
        current_text: str,
    ) -> str:
        if not isinstance(payload, dict):
            return current_text
        merged = str(payload.get("merged_current_user") or "").strip()
        return merged or current_text

    def _append_active_agent_followup_merge_if_any(
        self,
        request: ProviderRequest,
        payload: dict[str, Any] | None,
        *,
        budget: _StateInjectionBudget | None,
    ) -> bool:
        if not isinstance(payload, dict) or not payload.get("merged_current_user"):
            return False
        lines = [
            "[sylanne_active_agent_followup_merge]",
            "用户在上一轮 LLM 尚未产出可用回复前继续补充；本轮应把这些消息视为同一个连续用户意图，不要只回复最后一句。",
            "pending_count={count}; current_epoch={epoch}; speaker={speaker}".format(
                count=int(payload.get("pending_count") or 0),
                epoch=payload.get("current_epoch", ""),
                speaker=self._head_one_line(str(payload.get("speaker_key") or ""), 96),
            ),
        ]
        for index, item in enumerate(payload.get("previous_turns") or [], start=1):
            lines.append(
                "previous_user[{index}]={text}; epoch={epoch}; hash={hash}".format(
                    index=index,
                    text=self._head_one_line(str(item.get("text") or ""), 180),
                    epoch=item.get("input_epoch", ""),
                    hash=str(item.get("hash") or "")[:16],
                ),
            )
        lines.append(
            "current_user="
            + self._head_one_line(str(payload.get("current_user") or ""), 180),
        )
        lines.append(
            "merged_current_user="
            + self._head_one_line(str(payload.get("merged_current_user") or ""), 260),
        )
        text = self._head_text(
            "\n".join(lines),
            ACTIVE_AGENT_FOLLOWUP_INJECTION_MAX_CHARS,
        )
        source = "active_agent_followup_merge"
        effective_budget = None if budget is not None and budget.agent_owned_context else budget
        appended = self._append_temp_text_part(
            request,
            text,
            source=source,
            budget=effective_budget,
            required=True,
        )
        if appended and budget is not None and budget.agent_owned_context:
            text_chars = len(
                self._format_sylanne_temp_context_for_compression(
                    text,
                    source=source,
                ),
            )
            budget.added_chars += text_chars
            budget.added_parts += 1
            budget.appended.append(
                {
                    "source": source,
                    "chars": text_chars,
                    "reason": "active_followup_agent_owned_context_override",
                },
            )
        return appended

    def _interrupted_reply_breakpoint_cache(
        self,
    ) -> dict[str, deque[dict[str, Any]]]:
        cache = getattr(self, "_interrupted_reply_breakpoints", None)
        if not isinstance(cache, dict):
            cache = {}
            self._interrupted_reply_breakpoints = cache
        return cache

    def _has_pending_interrupted_reply_breakpoint(self, session_key: str) -> bool:
        queue = self._interrupted_reply_breakpoint_cache().get(str(session_key or "global"))
        return any(not item.get("consumed") for item in list(queue or ()) if isinstance(item, dict))

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
        event_time: dict[str, Any] | None = None,
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
        event_time_payload = self._normalize_conversation_time_payload(event_time)
        interrupted_at_payload = self._conversation_time_payload(now)
        entry = {
            "schema_version": "astrbot.interrupted_reply_breakpoint.v1",
            "kind": "interrupted_reply_breakpoint",
            "session_key": key,
            "reason": str(reason or "interrupted"),
            "source": str(source or "llm_response"),
            "input_epoch": input_epoch,
            "recorded_at": now,
            "event_time": event_time_payload,
            "event_local_time": str(event_time_payload.get("local_time") or ""),
            "event_timezone": str(event_time_payload.get("timezone") or ""),
            "event_epoch": event_time_payload.get("epoch"),
            "interrupted_at": now,
            "interrupted_time": interrupted_at_payload,
            "interrupted_local_time": str(interrupted_at_payload.get("local_time") or ""),
            "interrupted_timezone": str(interrupted_at_payload.get("timezone") or ""),
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
        self._mark_realtime_delivery_context_dirty(key)

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
        event_time_line = self._event_time_field_line(item.get("event_time") or item)
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
                    event_time_line,
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
            "上一段回复被用户新消息或撤回打断，而且没有完整送达。不要原样续发旧回复；只把它当作对话断点来理解当前消息。",
        ]
        for item in items:
            event_time_line = self._event_time_field_line(item.get("event_time") or item)
            interrupted_time_line = self._event_time_field_line(
                item.get("interrupted_time") or {},
                local_key="interrupted_local_time",
                timezone_key="interrupted_timezone",
                epoch_key="interrupted_epoch",
            )
            lines.append(
                "reason={reason}; sent_count={sent_count}; unsent_count={unsent_count}; "
                "old_epoch={epoch}; full_chars={full_chars}; unsent_hash={unsent_hash}; full_hash={full_hash}{time_suffix}{interrupted_suffix}".format(
                    reason=self._head_one_line(str(item.get("reason") or "interrupted"), 48),
                    sent_count=int(item.get("sent_count") or 0),
                    unsent_count=int(item.get("unsent_count") or 0),
                    epoch="" if item.get("input_epoch") is None else item.get("input_epoch"),
                    full_chars=int(item.get("full_text_chars") or 0),
                    unsent_hash=str(item.get("unsent_text_hash") or "")[:16],
                    full_hash=str(item.get("full_text_hash") or "")[:16],
                    time_suffix=f"; {event_time_line}" if event_time_line else "",
                    interrupted_suffix=(
                        f"; {interrupted_time_line}" if interrupted_time_line else ""
                    ),
                ),
            )
            sent_excerpt = str(item.get("sent_excerpt") or "").strip()
            unsent_head = str(item.get("unsent_head") or "").strip()
            if sent_excerpt:
                lines.append("已发送摘要=" + self._head_one_line(sent_excerpt, 120))
            if unsent_head:
                lines.append("未发送开头=" + self._head_one_line(unsent_head, 120))
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
            self._consume_interrupted_realtime_shadows_for_breakpoints(
                session_key,
                items,
            )
            self._mark_realtime_delivery_context_dirty(session_key)
        return appended

    def _consume_interrupted_realtime_shadows_for_breakpoints(
        self,
        session_key: str,
        breakpoints: Sequence[dict[str, Any]],
    ) -> None:
        queue = self._realtime_assistant_history_shadow_cache().get(
            str(session_key or "global"),
        )
        if not queue:
            return
        epochs = {
            item.get("input_epoch")
            for item in breakpoints
            if isinstance(item, dict) and item.get("input_epoch") is not None
        }
        hashes = {
            str(item.get("full_text_hash") or "")
            for item in breakpoints
            if isinstance(item, dict) and str(item.get("full_text_hash") or "")
        }
        now = self._observed_now()
        consumed_any = False
        for item in queue:
            if not isinstance(item, dict) or item.get("consumed"):
                continue
            if str(item.get("delivery_status") or "") != "interrupted":
                continue
            same_epoch = item.get("input_epoch") in epochs if epochs else False
            same_hash = str(item.get("full_text_hash") or "") in hashes if hashes else False
            if not (same_epoch or same_hash):
                continue
            item["consumed"] = True
            item["consumed_at"] = now
            item["consumed_reason"] = "represented_by_interrupted_reply_breakpoint"
            consumed_any = True
        if consumed_any:
            self._mark_realtime_delivery_context_dirty(session_key)

    def _append_realtime_continuity_context_if_any(
        self,
        request: ProviderRequest,
        session_key: str,
        *,
        budget: _StateInjectionBudget | None,
        current_user_text: str = "",
        observed_at: float | None = None,
        event: AstrMessageEvent | None = None,
    ) -> bool:
        appended = self._append_user_message_withdrawal_context_if_any(
            request,
            session_key,
            budget=budget,
        )
        if (
            observed_at is not None
            and self._looks_like_recency_sensitive_turn(current_user_text)
            and self._realtime_assistant_history_shadow_cache().get(
                str(session_key or "global"),
            )
        ):
            appended = (
                self._append_current_event_time_context_if_any(
                    request,
                    event,
                    session_key=session_key,
                    observed_at=observed_at,
                    budget=budget,
                )
                or appended
            )
        is_correction = self._looks_like_user_correction_or_source_query(
            current_user_text,
        )
        if is_correction:
            self._append_realtime_assistant_history_context_message_if_any(
                request,
                session_key,
                budget=budget,
                current_user_text=current_user_text,
            )
            correction_appended = self._append_user_correction_context(
                request,
                current_user_text,
                budget=budget,
            )
            if correction_appended:
                self._record_recent_user_correction(session_key, current_user_text)
            appended = correction_appended or appended
        else:
            appended = (
                self._append_recent_user_correction_context_if_any(
                    request,
                    session_key,
                    budget=budget,
                    current_user_text=current_user_text,
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
                    observed_at=observed_at,
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

    def _current_user_text_answers_pending_realtime_question(
        self,
        session_key: str,
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
        return self._should_anchor_short_answer_to_realtime_question(
            pending[-1],
            current_user_text,
        )

    def _looks_like_recency_sensitive_turn(self, text: str) -> bool:
        value = str(text or "").strip()
        if not value:
            return False
        compact = re.sub(r"\s+", "", value)
        if not compact:
            return False
        direct_markers = (
            "一觉",
            "睡到现在",
            "刚醒",
            "刚睡醒",
            "醒到现在",
            "哪来的",
            "哪来",
            "昨天不是",
            "昨晚不是",
            "上次",
            "几天没",
            "几天不",
            "多久没",
            "没人回",
            "四天",
            "三天",
            "两天",
            "2天",
            "3天",
            "4天",
        )
        if any(marker in compact for marker in direct_markers):
            return True
        sleep_markers = ("睡", "睡觉", "起床", "醒")
        time_markers = (
            "昨天",
            "昨晚",
            "昨夜",
            "今天",
            "早上",
            "凌晨",
            "晚上",
            "现在",
            "刚才",
            "刚刚",
            "点",
        )
        return any(marker in compact for marker in sleep_markers) and any(
            marker in compact for marker in time_markers
        )

    def _realtime_shadow_anchor_epoch(self, item: dict[str, Any]) -> float:
        candidates = [
            item.get("event_epoch"),
            (item.get("event_time") or {}).get("epoch")
            if isinstance(item.get("event_time"), dict)
            else None,
            item.get("recorded_at"),
        ]
        for candidate in candidates:
            try:
                value = float(candidate)
            except (TypeError, ValueError):
                continue
            if value > 0.0:
                return value
        return 0.0

    def _realtime_shadow_stale_for_recency_sensitive_turn(
        self,
        item: dict[str, Any],
        current_user_text: str,
        *,
        observed_at: float | None = None,
    ) -> bool:
        if not self._looks_like_recency_sensitive_turn(current_user_text):
            return False
        if self._should_anchor_short_answer_to_realtime_question(item, current_user_text):
            return False
        anchor = self._realtime_shadow_anchor_epoch(item)
        if anchor <= 0.0:
            return False
        now = self._observed_now() if observed_at is None else float(observed_at)
        if now <= 0.0:
            return False
        age = max(0.0, now - anchor)
        return age > REALTIME_ASSISTANT_HISTORY_RECENCY_SENSITIVE_TTL_SECONDS

    def _append_realtime_assistant_history_usage_guard(
        self,
        request: ProviderRequest,
        *,
        current_user_text: str = "",
        budget: _StateInjectionBudget | None = None,
    ) -> bool:
        text = "\n".join(
            [
                "[sylanne_history_reuse_guard]",
                "上一轮 assistant 原文只用于事实承接、指代消解和理解刚才说过什么；不要复述上一轮的句式、比喻、昵称、表情和整段结构。",
                "如果用户正在二次澄清同一个对象或模块，优先回答用户刚澄清的具体对象，不要沿用上一轮误会或上一轮修辞。",
                "current_user=" + self._head_one_line(str(current_user_text or ""), 160),
            ],
        )
        return self._append_temp_text_part(
            request,
            text,
            source="realtime_assistant_history_usage_guard",
            budget=budget,
        )

    def _append_realtime_assistant_history_context_message_if_any(
        self,
        request: ProviderRequest,
        session_key: str,
        *,
        budget: _StateInjectionBudget | None = None,
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
        item = pending[-1]
        if self._agent_history_already_contains_realtime_shadow(request, item):
            return False
        appended = self._append_agent_context_message(
            request,
            role="assistant",
            content=str(item.get("full_text") or item.get("excerpt") or ""),
        )
        if appended:
            self._append_realtime_assistant_history_usage_guard(
                request,
                current_user_text=current_user_text,
                budget=budget,
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
                *self._user_correction_extra_instructions(current_user_text),
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
            "我没说",
            "我没讲",
            "我没有说",
            "我没有讲",
            "没说",
            "没讲",
            "没有说",
            "没有讲",
            "什么时候和你说",
            "什么时候跟你说",
            "什么时候说过",
            "什么时候讲过",
            "谁和你说",
            "谁跟你说",
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
        return (
            any(marker in compact for marker in correction_markers + source_markers)
            or self._looks_like_followup_clarification(value)
            or self._looks_like_sleep_fact_correction(value)
        )

    def _looks_like_followup_clarification(self, text: str) -> bool:
        value = str(text or "").strip()
        if not value:
            return False
        compact = re.sub(r"\s+", "", value)
        lowered = compact.lower()
        clarification_markers = (
            "我只是想",
            "我是想",
            "我就想",
            "我想确认",
            "我想问",
            "我说的是",
        )
        topic_markers = (
            "确认",
            "问",
            "说",
            "讲",
            "插件",
            "模块",
            "记忆",
            "嵌入",
            "embedding",
            "工具",
            "上下文",
        )
        return any(marker in compact for marker in clarification_markers) and any(
            marker in lowered for marker in topic_markers
        )

    def _user_correction_extra_instructions(self, text: str) -> list[str]:
        if self._looks_like_sleep_fact_correction(text):
            return [
                "用户正在纠正睡眠/作息事实；把这条事实当作高优先级上下文。",
                "不要再追问或暗示用户没睡、熬夜或刚才撒谎；后续回复应承认用户已经说明睡眠情况。",
            ]
        return []

    def _looks_like_sleep_fact_correction(self, text: str) -> bool:
        value = str(text or "").strip()
        if not value:
            return False
        compact = re.sub(r"\s+", "", value)
        first_person = any(marker in compact for marker in ("我", "俺", "人家"))
        sleep_markers = (
            "睡",
            "睡觉",
            "睡的",
            "睡了",
            "起床",
            "早起",
            "醒",
        )
        denies_no_sleep = compact.startswith(("没有", "没有啊", "没啊", "不是", "不对"))
        has_sleep_fact = any(marker in compact for marker in sleep_markers)
        has_time_fact = bool(
            re.search(
                r"(昨晚|昨天|昨夜|夜里|晚上|早上|今天|凌晨|点|十点|十一点|十二点|\d{1,2}[:：点])",
                compact,
            ),
        )
        has_early_wake_fact = any(
            marker in compact
            for marker in (
                "早早起床",
                "早起",
                "起床啦",
                "起来啦",
                "已经起",
            )
        )
        if first_person and has_sleep_fact and has_time_fact:
            return True
        if first_person and denies_no_sleep and (has_sleep_fact or has_early_wake_fact):
            return True
        return False

    def _recent_user_correction_cache(self) -> dict[str, deque[dict[str, Any]]]:
        cache = getattr(self, "_recent_user_corrections", None)
        if not isinstance(cache, dict):
            cache = {}
            self._recent_user_corrections = cache
        return cache

    def _record_recent_user_correction(self, session_key: str, text: str) -> None:
        value = " ".join(str(text or "").split()).strip()
        if not value:
            return
        key = str(session_key or "global")
        queue = self._recent_user_correction_cache().setdefault(
            key,
            deque(maxlen=RECENT_USER_CORRECTION_LIMIT),
        )
        if queue.maxlen != RECENT_USER_CORRECTION_LIMIT:
            queue = deque(queue, maxlen=RECENT_USER_CORRECTION_LIMIT)
            self._recent_user_correction_cache()[key] = queue
        queue.append(
            {
                "schema_version": "astrbot.recent_user_correction.v1",
                "kind": "recent_user_correction",
                "session_key": key,
                "text": self._head_one_line(value, 180),
                "recorded_at": self._observed_now(),
                "sleep_fact_correction": self._looks_like_sleep_fact_correction(value),
                "hash": self._text_hash(value),
            },
        )

    def _append_recent_user_correction_context_if_any(
        self,
        request: ProviderRequest,
        session_key: str,
        *,
        budget: _StateInjectionBudget | None,
        current_user_text: str = "",
    ) -> bool:
        key = str(session_key or "global")
        queue = self._recent_user_correction_cache().get(key)
        if not queue:
            return False
        now = self._observed_now()
        fresh = [
            item
            for item in queue
            if now - float(item.get("recorded_at") or 0.0)
            <= RECENT_USER_CORRECTION_TTL_SECONDS
        ]
        if not fresh:
            self._recent_user_correction_cache().pop(key, None)
            return False
        latest_items = fresh[-2:]
        lines = [
            "[sylanne_recent_user_correction_context]",
            "用户刚刚纠正过 bot 的误读；这类事实优先级高于旧模板、旧猜测和上一轮关心话术。",
            "如果当前用户在继续回答另一个问题，也必须保留这些纠正事实，不要在下一轮又复读被纠正的猜测。",
        ]
        if any(bool(item.get("sleep_fact_correction")) for item in latest_items):
            lines.append(
                "不要再追问或暗示用户没睡、熬夜或刚才撒谎；用户已经给过睡眠/作息事实。",
            )
        for item in latest_items:
            self._append_agent_context_message(
                request,
                role="user",
                content=str(item.get("text") or ""),
            )
            lines.append(
                "recent_correction={text}; hash={hash}".format(
                    text=self._head_one_line(str(item.get("text") or ""), 180),
                    hash=str(item.get("hash") or "")[:16],
                ),
            )
        if current_user_text:
            lines.append(
                "current_user="
                + self._head_one_line(str(current_user_text or ""), 120),
            )
        text = self._head_text(
            "\n".join(lines),
            RECENT_USER_CORRECTION_INJECTION_MAX_CHARS,
        )
        return self._append_temp_text_part(
            request,
            text,
            source="recent_user_correction_context",
            budget=budget,
        )

    def _recent_user_scene_cache(self) -> dict[str, deque[dict[str, Any]]]:
        cache = getattr(self, "_recent_user_scene_turns", None)
        if not isinstance(cache, dict):
            cache = {}
            self._recent_user_scene_turns = cache
        return cache

    def _record_recent_user_scene_turn(
        self,
        session_key: str,
        identity: ConversationIdentity,
        *,
        text: str,
        observed_at: float,
    ) -> None:
        value = " ".join(str(text or "").split()).strip()
        if not value:
            return
        if self._low_signal_text_profile(value).get("is_low_signal"):
            return
        key = str(session_key or "global")
        speaker_key = self._active_agent_speaker_key(identity)
        queue = self._recent_user_scene_cache().setdefault(
            key,
            deque(maxlen=RECENT_USER_SCENE_LIMIT),
        )
        if queue.maxlen != RECENT_USER_SCENE_LIMIT:
            queue = deque(queue, maxlen=RECENT_USER_SCENE_LIMIT)
            self._recent_user_scene_cache()[key] = queue
        queue.append(
            {
                "schema_version": "astrbot.recent_user_scene_turn.v1",
                "kind": "recent_user_scene_turn",
                "session_key": key,
                "speaker_key": speaker_key,
                "text": self._head_one_line(value, 200),
                "recorded_at": float(observed_at),
                "hash": self._text_hash(value),
            },
        )

    def _append_recent_user_scene_context_if_any(
        self,
        request: ProviderRequest,
        session_key: str,
        identity: ConversationIdentity,
        *,
        budget: _StateInjectionBudget | None,
        current_user_text: str = "",
        observed_at: float | None = None,
    ) -> bool:
        key = str(session_key or "global")
        queue = self._recent_user_scene_cache().get(key)
        if not queue:
            return False
        now = self._observed_now() if observed_at is None else float(observed_at)
        speaker_key = self._active_agent_speaker_key(identity)
        current_hash = self._text_hash(current_user_text)
        fresh = [
            item
            for item in queue
            if now - float(item.get("recorded_at") or 0.0)
            <= RECENT_USER_SCENE_TTL_SECONDS
        ]
        if len(fresh) != len(queue):
            if fresh:
                self._recent_user_scene_cache()[key] = deque(
                    fresh[-RECENT_USER_SCENE_LIMIT:],
                    maxlen=RECENT_USER_SCENE_LIMIT,
                )
            else:
                self._recent_user_scene_cache().pop(key, None)
        relevant = [
            item
            for item in fresh
            if str(item.get("speaker_key") or "") == speaker_key
            and str(item.get("text") or "").strip()
            and str(item.get("hash") or "") != current_hash
        ][-3:]
        if not relevant:
            return False
        if not self._should_use_recent_user_scene_context(
            current_user_text,
            relevant,
            observed_at=now,
        ):
            return False
        lines = [
            "[sylanne_recent_user_scene_context]",
            "用户最近几条短事实描述了当前活动、地点或感受；当前短句要承接这些事实，不要只看最后一句，也不要重新询问已经给出的场景。",
            "这只是会话内短时上下文，不是长期记忆；如果当前用户明显开启新话题，再自然切换。",
            "speaker={speaker}; recent_count={count}".format(
                speaker=self._head_one_line(speaker_key, 96),
                count=len(relevant),
            ),
        ]
        scene_parts: list[str] = []
        for index, item in enumerate(relevant, start=1):
            text = self._head_one_line(str(item.get("text") or ""), 180)
            scene_parts.append(text)
            lines.append(
                "recent_user[{index}]={text}; hash={hash}".format(
                    index=index,
                    text=text,
                    hash=str(item.get("hash") or "")[:16],
                ),
            )
        current = self._head_one_line(str(current_user_text or ""), 160)
        if current:
            lines.append("current_user=" + current)
            scene_parts.append(current)
        merged = self._head_one_line(" / ".join(scene_parts), 320)
        if merged:
            lines.append("merged_recent_scene=" + merged)
        text = self._head_text(
            "\n".join(lines),
            RECENT_USER_SCENE_INJECTION_MAX_CHARS,
        )
        return self._append_temp_text_part(
            request,
            text,
            source="recent_user_scene_context",
            budget=budget,
        )

    def _should_use_recent_user_scene_context(
        self,
        current_user_text: str,
        recent_items: Sequence[dict[str, Any]],
        *,
        observed_at: float,
    ) -> bool:
        value = " ".join(str(current_user_text or "").split()).strip()
        if not value:
            return False
        if self._low_signal_text_profile(value).get("is_low_signal"):
            return False
        compact = re.sub(r"[\s，。！？!?；;、,.~～…]+", "", value)
        if len(compact) <= 24:
            return True
        continuation_prefixes = (
            "不过",
            "但是",
            "可是",
            "然后",
            "而且",
            "所以",
            "因为",
            "我在",
            "我还",
            "还在",
            "正在",
            "刚刚",
            "现在",
            "这边",
            "那边",
            "这里",
            "外面",
            "里面",
        )
        if value.startswith(continuation_prefixes):
            return True
        scene_markers = (
            "外面",
            "里面",
            "路上",
            "排队",
            "食堂",
            "宿舍",
            "教室",
            "实验室",
            "热",
            "冷",
            "晒",
            "闷",
            "下雨",
            "买",
            "吃",
            "喝",
            "刚到",
        )
        if any(marker in value for marker in scene_markers):
            latest_at = max(
                float(item.get("recorded_at") or 0.0)
                for item in recent_items
            )
            return observed_at - latest_at <= 120.0
        return False

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
            append=True,
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
            append=False,
        )

    def _observe_realtime_input_fragment_context_sync(
        self,
        request: ProviderRequest,
        identity: ConversationIdentity,
        *,
        current_user_text: str,
        observed_at: float,
        budget: _StateInjectionBudget | None,
        append: bool = True,
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
        if not append:
            return payload
        self._append_realtime_input_fragment_payload_context(
            request,
            payload,
            budget=budget,
        )
        return payload

    def _set_waiting_realtime_input_payload(
        self,
        event: AstrMessageEvent,
        payload: dict[str, Any] | None,
    ) -> None:
        if not isinstance(payload, dict) or not (
            payload.get("should_inject") or payload.get("should_hold")
        ):
            return
        try:
            setattr(event, "_sylanne_waiting_realtime_input_payload", dict(payload))
        except Exception:
            pass

    def _take_waiting_realtime_input_payload(
        self,
        event: AstrMessageEvent,
    ) -> dict[str, Any]:
        payload = getattr(event, "_sylanne_waiting_realtime_input_payload", None)
        try:
            delattr(event, "_sylanne_waiting_realtime_input_payload")
        except Exception:
            pass
        if isinstance(payload, dict):
            return dict(payload)
        return {}

    def _append_realtime_input_fragment_payload_context(
        self,
        request: ProviderRequest,
        payload: dict[str, Any],
        *,
        budget: _StateInjectionBudget | None,
    ) -> bool:
        if not isinstance(payload, dict) or not payload.get("should_inject"):
            return False
        text = build_realtime_input_fragment_injection(
            payload,
            max_chars=REALTIME_INPUT_FRAGMENT_INJECTION_MAX_CHARS,
        )
        return self._append_temp_text_part(
            request,
            text,
            source="realtime_input_fragments",
            budget=budget,
        )

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

    async def _realtime_input_release_blocked_by_llm_gate(
        self,
        event: AstrMessageEvent,
        identity: ConversationIdentity,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not isinstance(payload, dict) or not payload.get("should_inject"):
            return None
        if not (
            self._cfg_bool("use_llm_assessor", True)
            and self._cfg_bool("realtime_input_completion_llm_gate_enabled", False)
        ):
            return None
        judgement = await self._judge_realtime_input_completion(event, payload)
        reliable_llm_gate = str(judgement.get("source") or "") == "llm_input_completion_gate"
        if reliable_llm_gate and judgement.get("is_complete"):
            return None
        hold_payload = dict(payload)
        hold_payload["should_inject"] = False
        hold_payload["should_hold"] = True
        hold_payload["reason"] = (
            "llm_completion_gate_incomplete"
            if reliable_llm_gate
            else "llm_completion_gate_unavailable"
        )
        hold_payload["completion_judgement"] = judgement
        self._restore_realtime_input_window_from_payload(
            identity.conversation_id,
            hold_payload,
        )
        self._mark_realtime_input_semantic_wait_window(
            identity.conversation_id,
            hold_payload,
            judgement,
        )
        return hold_payload

    async def _realtime_input_blocked_release_still_waiting(
        self,
        identity: ConversationIdentity,
        payload: dict[str, Any],
    ) -> bool:
        if not isinstance(payload, dict) or not payload.get("should_hold"):
            return False
        if not await self._wait_realtime_input_window_unchanged(
            identity.conversation_id,
            payload,
            self._realtime_input_completion_max_wait_seconds(),
        ):
            return True
        return not self._realtime_input_window_matches_payload(
            identity.conversation_id,
            payload,
        )

    def _restore_realtime_input_window_from_payload(
        self,
        session_key: str,
        payload: dict[str, Any],
    ) -> None:
        fragments = [
            str(item or "").strip()
            for item in (payload.get("fragments") or [])
            if str(item or "").strip()
        ]
        if not fragments:
            return
        speaker_key = str(payload.get("speaker_key") or session_key or "unknown")
        started_at = self._as_float_value(
            payload.get("started_at") or payload.get("updated_at"),
            self._observed_now(),
        )
        updated_at = self._as_float_value(
            payload.get("updated_at") or started_at,
            started_at,
        )
        span = max(0.0, updated_at - started_at)
        denominator = max(1, len(fragments) - 1)
        restored = [
            RealtimeInputFragment(
                text=text,
                speaker_key=speaker_key,
                observed_at=started_at + span * index / denominator,
                kind="short_text",
            )
            for index, text in enumerate(fragments)
        ]
        self._realtime_input_fragment_window_cache()[str(session_key or "global")] = {
            "schema_version": "astrbot.realtime_input_fragments.v1",
            "kind": "realtime_user_message_fragment_window",
            "session_key": str(session_key or "global"),
            "speaker_key": speaker_key,
            "started_at": started_at,
            "updated_at": updated_at,
            "fragments": restored,
        }

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
        llm_gate_enabled = self._cfg_bool("use_llm_assessor", True) and self._cfg_bool(
            "realtime_input_completion_llm_gate_enabled",
            False,
        )
        if llm_gate_enabled:
            judgement = await self._judge_realtime_input_completion(event, payload)
        else:
            judgement = self._local_realtime_input_completion_judgement(payload)
        reliable_llm_gate = str(judgement.get("source") or "") == "llm_input_completion_gate"
        fragments = payload.get("fragments") if isinstance(payload, dict) else None
        fragment_count = len(fragments) if isinstance(fragments, list) else 1
        strict_gate_wait = reliable_llm_gate or (llm_gate_enabled and fragment_count > 1)
        if judgement.get("is_complete") and (
            reliable_llm_gate or not llm_gate_enabled or not strict_gate_wait
        ):
            return False
        self._mark_realtime_input_semantic_wait_window(
            identity.conversation_id,
            payload,
            judgement,
        )
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

    def _mark_realtime_input_semantic_wait_window(
        self,
        session_key: str,
        payload: dict[str, Any],
        judgement: dict[str, Any],
    ) -> None:
        if str(judgement.get("source") or "") != "llm_input_completion_gate":
            fragments = payload.get("fragments") if isinstance(payload, dict) else None
            fragment_count = len(fragments) if isinstance(fragments, list) else 1
            if not (
                self._cfg_bool("use_llm_assessor", True)
                and self._cfg_bool("realtime_input_completion_llm_gate_enabled", False)
                and fragment_count > 1
            ):
                return
        if judgement.get("is_complete"):
            return
        window = self._realtime_input_fragment_window_cache().get(
            str(session_key or "global"),
        )
        if not isinstance(window, dict):
            return
        if not self._realtime_input_window_matches_payload(session_key, payload):
            return
        updated_at = self._as_float_value(
            payload.get("updated_at") or window.get("updated_at"),
            self._observed_now(),
        )
        wait_until = updated_at + self._realtime_input_completion_max_wait_seconds()
        window["semantic_wait_until"] = max(
            self._as_float_value(window.get("semantic_wait_until"), 0.0),
            wait_until,
        )
        window["semantic_wait_source"] = "llm_input_completion_gate"
        window["semantic_wait_confidence"] = self._clamp01(
            judgement.get("confidence", 0.5),
        )
        window["semantic_wait_reason"] = self._head_one_line(
            str(judgement.get("reason") or ""),
            160,
        )

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
        base = max(0.0, self._cfg_float("realtime_input_completion_probe_delay_seconds", 0.25))
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
            max(0.0, self._cfg_float("realtime_input_completion_max_wait_seconds", 4.0)),
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
        provider_id = await self._fast_assessor_provider_id(event)
        if not provider_id:
            return fallback
        token = _INTERNAL_LLM_CALL.set(True)
        try:
            assessor_kwargs = {
                "provider_id": provider_id,
                "prompt": self._build_realtime_input_completion_prompt(
                    payload,
                    max_chars=self._fast_assessor_max_context_chars(),
                ),
                "system_prompt": (
                    "你是聊天输入完整度判断器。只输出 JSON，不要解释。"
                    "判断用户是否已经把当前这句话说完，宁可保守等待，也不要让 bot 抢答半句话。"
                ),
            }
            try:
                signature = inspect.signature(self._call_internal_assessor_llm)
                parameters = signature.parameters
                supports_extra = any(
                    item.kind == inspect.Parameter.VAR_KEYWORD
                    for item in parameters.values()
                )
                if supports_extra or "temperature" in parameters:
                    assessor_kwargs["temperature"] = self._cfg_float(
                        "fast_assessor_temperature",
                        0.0,
                    )
                if supports_extra or "timeout_seconds" in parameters:
                    assessor_kwargs["timeout_seconds"] = self._cfg_float(
                        "fast_assessor_timeout_seconds",
                        2.0,
                    )
            except (TypeError, ValueError):
                pass
            llm_resp = await self._call_internal_assessor_llm(
                **assessor_kwargs,
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

    def _build_realtime_input_completion_prompt(
        self,
        payload: dict[str, Any],
        *,
        max_chars: int | None = None,
    ) -> str:
        fragments = [str(item or "") for item in (payload.get("fragments") or [])]
        prompt = (
            "请判断下面同一用户短时间内发出的聊天碎片是否已经表达完整。\n"
            "只输出 JSON：{\"is_complete\": true/false, \"confidence\": 0-1, \"reason\": \"...\"}。\n"
            "规则：如果像半句话、强调铺垫、还在补充主语/谓语/宾语，就 is_complete=false；"
            "如果已经形成可回复的完整问题、完整声明、完整纠正，则 is_complete=true。\n"
            f"碎片序列：{json.dumps(fragments, ensure_ascii=False)}\n"
            f"合并预览：{payload.get('merged_intent') or ''}"
        )
        if max_chars is None:
            return prompt
        limit = max(240, int(max_chars or 0))
        return prompt[:limit]

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
        is_complete = bool(payload.get("should_inject"))
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
        request: ProviderRequest | None,
        payload: dict[str, Any],
    ) -> None:
        hold_text = build_realtime_input_hold_injection(
            payload,
            max_chars=REALTIME_INPUT_HOLD_INJECTION_MAX_CHARS,
        )
        for target in (event, request):
            if target is None:
                continue
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
        if hold_text and request is not None:
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
            "storage": "memory_plus_kv_checkpoint",
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

    def _realtime_response_intercept_key_cache(self) -> dict[str, deque[str]]:
        cache = getattr(self, "_realtime_response_intercept_keys", None)
        if not isinstance(cache, dict):
            cache = {}
            self._realtime_response_intercept_keys = cache
        return cache

    def _claim_realtime_response_intercept(
        self,
        session_key: str,
        *,
        input_epoch: int | None,
        response_text: str,
    ) -> bool:
        key = str(session_key or "global")
        epoch_text = "" if input_epoch is None else str(int(input_epoch))
        dedup_key = "|".join((epoch_text, self._text_hash(response_text)))
        queue = self._realtime_response_intercept_key_cache().setdefault(
            key,
            deque(maxlen=REALTIME_RESPONSE_INTERCEPT_DEDUP_LIMIT),
        )
        if queue.maxlen != REALTIME_RESPONSE_INTERCEPT_DEDUP_LIMIT:
            queue = deque(queue, maxlen=REALTIME_RESPONSE_INTERCEPT_DEDUP_LIMIT)
            self._realtime_response_intercept_key_cache()[key] = queue
        if dedup_key in queue:
            return False
        queue.append(dedup_key)
        return True

    def _response_already_realtime_intercepted(self, response: LLMResponse) -> bool:
        reason = str(
            getattr(response, "_sylanne_intercepted_completion_reason", "") or "",
        )
        if reason.startswith("realtime_chat_response_intercept"):
            return True
        text = str(getattr(response, "completion_text", "") or "").lstrip()
        return text.startswith("[sylanne_realtime_delivery_status]")

    def _astrbot_active_runner_followup_texts(
        self,
        event: AstrMessageEvent,
        *,
        fallback_observed_at: float | None = None,
    ) -> list[dict[str, Any]]:
        umo = str(getattr(event, "unified_msg_origin", "") or "").strip()
        if not umo:
            return []
        try:
            from astrbot.core.pipeline.process_stage import follow_up as follow_up_stage  # type: ignore
        except Exception:
            return []
        runners = getattr(follow_up_stage, "_ACTIVE_AGENT_RUNNERS", None)
        if not isinstance(runners, dict):
            return []
        runner = runners.get(umo)
        if runner is None:
            return []
        tickets = getattr(runner, "_pending_follow_ups", None)
        if not isinstance(tickets, (list, tuple)):
            return []
        fallback_time = (
            self._event_observed_at(event)
            if fallback_observed_at is None
            else float(fallback_observed_at)
        )
        turns: list[dict[str, Any]] = []
        for offset, ticket in enumerate(tickets, start=1):
            consumed = (
                bool(ticket.get("consumed", False))
                if isinstance(ticket, dict)
                else bool(getattr(ticket, "consumed", False))
            )
            if consumed:
                continue
            text = self._active_runner_followup_ticket_text(ticket)
            if not text:
                continue
            order_seq = self._active_runner_followup_ticket_order(ticket, offset)
            turns.append(
                {
                    "text": self._head_one_line(text, 180),
                    "observed_at": self._active_runner_followup_ticket_observed_at(
                        ticket,
                        fallback_observed_at=fallback_time,
                        offset=offset,
                    ),
                    "followup_order": order_seq,
                    "source": "astrbot_active_runner_followup",
                },
            )
        turns.sort(
            key=lambda item: (
                self._as_float_value(item.get("observed_at"), fallback_time),
                int(item.get("followup_order") or 0),
                str(item.get("text") or ""),
            ),
        )
        return turns

    def _active_runner_followup_ticket_text(self, ticket: Any) -> str:
        candidates: list[Any] = []
        text_names = (
            "text",
            "message_text",
            "message_str",
            "raw_message",
            "prompt",
        )
        if isinstance(ticket, dict):
            for name in text_names:
                candidates.append(ticket.get(name))
        else:
            for name in text_names:
                candidates.append(getattr(ticket, name, None))
        for root in self._active_runner_followup_ticket_nested_events(ticket):
            if isinstance(root, dict):
                for name in text_names:
                    candidates.append(root.get(name))
                continue
            candidates.append(getattr(root, "message_str", None))
            candidates.append(getattr(root, "text", None))
        for value in candidates:
            if isinstance(value, (dict, list, tuple, set)):
                continue
            text = " ".join(str(value or "").split()).strip()
            if text:
                return text
        return ""

    def _active_runner_followup_ticket_order(
        self,
        ticket: Any,
        fallback_order: int,
    ) -> int:
        for name in ("order_seq", "followup_order", "order", "seq", "index"):
            value = ticket.get(name) if isinstance(ticket, dict) else getattr(ticket, name, None)
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return int(fallback_order)

    def _active_runner_followup_ticket_observed_at(
        self,
        ticket: Any,
        *,
        fallback_observed_at: float,
        offset: int,
    ) -> float:
        timestamp = self._extract_event_timestamp(ticket)
        if timestamp is not None:
            return timestamp
        for root in self._active_runner_followup_ticket_nested_events(ticket):
            timestamp = self._extract_event_timestamp(root)
            if timestamp is not None:
                return timestamp
        return float(fallback_observed_at) + int(offset) * 0.0001

    def _active_runner_followup_ticket_nested_events(self, ticket: Any) -> list[Any]:
        roots: list[Any] = []
        for name in (
            "event",
            "message_event",
            "astr_message_event",
            "source_event",
            "message_obj",
            "raw_event",
            "raw_message",
            "message",
        ):
            value = ticket.get(name) if isinstance(ticket, dict) else getattr(ticket, name, None)
            if value is not None and value is not ticket:
                roots.append(value)
        return roots

    def _user_message_withdrawal_context_cache(
        self,
    ) -> dict[str, deque[dict[str, Any]]]:
        cache = getattr(self, "_user_message_withdrawals", None)
        if not isinstance(cache, dict):
            cache = {}
            self._user_message_withdrawals = cache
        return cache

    def _record_user_message_withdrawal_context(
        self,
        session_key: str,
        withdrawal: dict[str, Any],
    ) -> None:
        if not isinstance(withdrawal, dict):
            return
        key = str(session_key or withdrawal.get("session_key") or "global")
        entry = {
            "schema_version": "astrbot.user_message_withdrawal_context.v1",
            "kind": "user_message_withdrawal",
            "session_key": key,
            "message_id": str(withdrawal.get("message_id") or ""),
            "reason": str(withdrawal.get("reason") or "withdrawn"),
            "notice": withdrawal.get("notice") if isinstance(withdrawal.get("notice"), dict) else {},
            "input_epoch": withdrawal.get("input_epoch"),
            "observed_at": self._as_float_value(
                withdrawal.get("observed_at"),
                self._observed_now(),
            ),
            "previous_user_excerpt": self._head_text(
                str(withdrawal.get("previous_user_excerpt") or ""),
                USER_MESSAGE_WITHDRAWAL_INJECTION_MAX_CHARS,
            ),
            "consumed": False,
        }
        cache = self._user_message_withdrawal_context_cache()
        queue = cache.setdefault(
            key,
            deque(maxlen=USER_MESSAGE_WITHDRAWAL_CONTEXT_LIMIT),
        )
        if queue.maxlen != USER_MESSAGE_WITHDRAWAL_CONTEXT_LIMIT:
            queue = deque(queue, maxlen=USER_MESSAGE_WITHDRAWAL_CONTEXT_LIMIT)
            cache[key] = queue
        queue.append(entry)
        self._mark_realtime_delivery_context_dirty(key)

    def _append_user_message_withdrawal_context_if_any(
        self,
        request: ProviderRequest,
        session_key: str,
        *,
        budget: _StateInjectionBudget | None,
    ) -> bool:
        key = str(session_key or "global")
        queue = self._user_message_withdrawal_context_cache().get(key)
        if not queue:
            return False
        pending = [item for item in queue if not item.get("consumed")]
        if not pending:
            return False
        items = pending[-USER_MESSAGE_WITHDRAWAL_CONTEXT_LIMIT:]
        lines = [
            "[sylanne_user_message_withdrawal]",
            "用户刚才撤回了一条或多条消息。撤回本身不是新的普通聊天内容；后续回复应把它当作会话事实，不要继续回应已撤回内容，也不要把平台空事件当成用户发言。",
        ]
        for index, item in enumerate(items, start=1):
            lines.append(
                "withdrawal[{index}]: reason={reason}; message_id={message_id}; input_epoch={epoch}".format(
                    index=index,
                    reason=self._head_one_line(str(item.get("reason") or "withdrawn"), 48),
                    message_id=self._head_one_line(str(item.get("message_id") or ""), 80),
                    epoch="" if item.get("input_epoch") is None else item.get("input_epoch"),
                ),
            )
            previous = str(item.get("previous_user_excerpt") or "").strip()
            if previous:
                lines.append(
                    "withdrawn_context_excerpt="
                    + self._head_one_line(previous, 220),
                )
        text = self._head_text(
            "\n".join(lines),
            USER_MESSAGE_WITHDRAWAL_INJECTION_MAX_CHARS,
        )
        appended = self._append_temp_text_part(
            request,
            text,
            source="user_message_withdrawal",
            budget=budget,
        )
        if appended:
            for item in items:
                item["consumed"] = True
                item["consumed_at"] = self._observed_now()
            self._mark_realtime_delivery_context_dirty(key)
        return appended

    def _realtime_ordinary_history_backfill_cache(
        self,
    ) -> dict[str, deque[dict[str, Any]]]:
        cache = getattr(self, "_realtime_ordinary_history_backfills", None)
        if not isinstance(cache, dict):
            cache = {}
            self._realtime_ordinary_history_backfills = cache
        return cache

    def _request_contexts_contain_text(
        self,
        request: ProviderRequest,
        text: str,
    ) -> bool:
        normalized = self._normalize_realtime_history_match_text(text)
        if not normalized:
            return False
        for item in self._tail_items(getattr(request, "contexts", []) or [], 20):
            existing = self._normalize_realtime_history_match_text(
                self._context_item_to_text(item),
            )
            if normalized in existing:
                return True
        return False

    def _record_realtime_ordinary_history_backfill(
        self,
        session_key: str,
        *,
        role: str,
        content: str,
        input_epoch: int | None,
        source: str,
        delivery_status: str,
        event_time: dict[str, Any] | None = None,
    ) -> bool:
        text = str(content or "").strip()
        if not text:
            return False
        key = str(session_key or "global")
        now = self._observed_now()
        content_hash = self._text_hash(text)
        event_time_payload = self._normalize_conversation_time_payload(event_time)
        entry = {
            "schema_version": "astrbot.realtime_ordinary_history_backfill.v1",
            "kind": "realtime_ordinary_history_backfill",
            "session_key": key,
            "role": str(role or "assistant"),
            "content": self._head_text(
                text,
                REALTIME_ORDINARY_HISTORY_BACKFILL_MAX_CHARS,
            ),
            "content_truncated": len(text) > REALTIME_ORDINARY_HISTORY_BACKFILL_MAX_CHARS,
            "content_hash": content_hash,
            "input_epoch": input_epoch,
            "source": str(source or "realtime_delivery"),
            "delivery_status": str(delivery_status or "delivered"),
            "recorded_at": now,
            "updated_at": now,
            "event_time": event_time_payload,
            "event_local_time": str(event_time_payload.get("local_time") or ""),
            "event_timezone": str(event_time_payload.get("timezone") or ""),
            "event_epoch": event_time_payload.get("epoch"),
            "append_count": 0,
        }
        cache = self._realtime_ordinary_history_backfill_cache()
        queue = cache.setdefault(
            key,
            deque(maxlen=REALTIME_ORDINARY_HISTORY_BACKFILL_LIMIT),
        )
        if queue.maxlen != REALTIME_ORDINARY_HISTORY_BACKFILL_LIMIT:
            queue = deque(queue, maxlen=REALTIME_ORDINARY_HISTORY_BACKFILL_LIMIT)
            cache[key] = queue
        for existing in reversed(queue):
            if not isinstance(existing, dict):
                continue
            if (
                str(existing.get("content_hash") or "") == content_hash
                and existing.get("input_epoch") == input_epoch
            ):
                existing.update(entry)
                self._mark_realtime_delivery_context_dirty(key)
                return True
        queue.append(entry)
        self._mark_realtime_delivery_context_dirty(key)
        return True

    def _prune_realtime_ordinary_history_backfills(self, session_key: str) -> bool:
        key = str(session_key or "global")
        queue = self._realtime_ordinary_history_backfill_cache().get(key)
        if not queue:
            return False
        now = self._observed_now()
        kept: list[dict[str, Any]] = []
        for item in queue:
            if not isinstance(item, dict):
                continue
            recorded_at = self._as_float_value(item.get("recorded_at"), now)
            if now - recorded_at > REALTIME_ORDINARY_HISTORY_BACKFILL_TTL_SECONDS:
                continue
            if not str(item.get("content") or "").strip():
                continue
            kept.append(item)
        if len(kept) == len(queue):
            return False
        if kept:
            self._realtime_ordinary_history_backfill_cache()[key] = deque(
                kept[-REALTIME_ORDINARY_HISTORY_BACKFILL_LIMIT:],
                maxlen=REALTIME_ORDINARY_HISTORY_BACKFILL_LIMIT,
            )
        else:
            self._realtime_ordinary_history_backfill_cache().pop(key, None)
        self._mark_realtime_delivery_context_dirty(key)
        return True

    def _append_realtime_ordinary_history_backfills_if_any(
        self,
        request: ProviderRequest,
        session_key: str,
        *,
        current_user_text: str = "",
    ) -> bool:
        key = str(session_key or "global")
        self._prune_realtime_ordinary_history_backfills(key)
        queue = self._realtime_ordinary_history_backfill_cache().get(key)
        if not queue:
            return False
        appended = False
        changed = False
        now = self._observed_now()
        valid_items: list[dict[str, Any]] = []
        for item in queue:
            if not isinstance(item, dict):
                changed = True
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                changed = True
                continue
            if self._request_contexts_contain_text(request, content):
                changed = True
                continue
            valid_items.append(item)
        selected = valid_items[-REALTIME_ORDINARY_HISTORY_BACKFILL_MAX_ITEMS_PER_REQUEST:]
        shadow_memory_lines = [
            "[sylanne_shadow_memory]",
            "上一轮实时回复已经确认送达，只作为临时连续性线索回到事件池，不直接接管 AstrBot 原生上下文。",
            "不要把 shadow memory 当作当前用户又说了一遍；其中的 assistant content 是上一轮旧回复，不是可复述素材。",
            "只用它理解用户正在回应或纠正哪句话；不要复述上一轮的句式、昵称、表情、比喻或整段情绪结构。",
            "如果当前用户文本与 shadow memory 冲突，必须以当前用户文本为准，并简短承认误读。",
        ]
        current_user = self._head_one_line(str(current_user_text or ""), 180)
        if current_user:
            shadow_memory_lines.append("current_user=" + current_user)
        item_count = 0
        for item in selected:
            content = self._head_text(
                str(item.get("content") or "").strip(),
                REALTIME_ORDINARY_HISTORY_BACKFILL_MAX_CHARS,
            )
            if not content:
                changed = True
                continue
            shadow_memory_lines.extend(
                [
                    "source={source}; delivery_status={status}; input_epoch={epoch}; role={role}; content_hash={hash}".format(
                        source=self._head_one_line(str(item.get("source") or ""), 48),
                        status=self._head_one_line(
                            str(item.get("delivery_status") or "delivered"),
                            32,
                        ),
                        epoch="" if item.get("input_epoch") is None else item.get("input_epoch"),
                        role=self._head_one_line(str(item.get("role") or "assistant"), 24),
                        hash=str(item.get("content_hash") or "")[:16],
                    ),
                    self._event_time_field_line(item.get("event_time") or item),
                    content,
                    "",
                ],
            )
            item["last_appended_at"] = now
            item["append_count"] = int(item.get("append_count") or 0) + 1
            item["updated_at"] = now
            appended = True
            changed = True
            item_count += 1
        if item_count:
            shadow_memory_text = self._head_text(
                "\n".join(shadow_memory_lines).strip(),
                REALTIME_ORDINARY_HISTORY_BACKFILL_MAX_CHARS,
            )
            if self._append_temp_text_part(
                request,
                shadow_memory_text,
                source="shadow_memory",
            ):
                changed = True
        if valid_items or selected:
            changed = True
        self._realtime_ordinary_history_backfill_cache().pop(key, None)
        if changed:
            self._mark_realtime_delivery_context_dirty(key)
        return appended and item_count > 0

    def _release_realtime_temporary_context_after_background_post_in_memory(
        self,
        session_key: str,
        *,
        input_epoch: int | None,
        reason: str,
    ) -> bool:
        if input_epoch is None:
            return False
        key = str(session_key or "global")
        queue = self._realtime_assistant_history_shadow_cache().get(key)
        if not queue:
            return False
        changed = False
        now = self._observed_now()
        for item in queue:
            if not isinstance(item, dict):
                continue
            if input_epoch is not None and item.get("input_epoch") != input_epoch:
                continue
            if str(item.get("delivery_status") or "") != "delivered":
                continue
            if str(item.get("consumed_reason") or "") == "agent_history_already_contains_reply":
                item["released_to_ordinary_context"] = True
                changed = True
                continue
            content = str(item.get("full_text") or item.get("excerpt") or "").strip()
            if content and not item.get("released_to_ordinary_context"):
                self._record_realtime_ordinary_history_backfill(
                    key,
                    role="assistant",
                    content=content,
                    input_epoch=self._optional_int(item.get("input_epoch")),
                    source=str(item.get("source") or "realtime_delivery"),
                    delivery_status=str(item.get("delivery_status") or "delivered"),
                    event_time=item.get("event_time") if isinstance(item.get("event_time"), dict) else item,
                )
            item["consumed"] = True
            item["consumed_at"] = now
            item["consumed_reason"] = "released_to_ordinary_context_after_background_post"
            item["released_to_ordinary_context"] = True
            item["released_reason"] = str(reason or "background_post_done")
            item["released_at"] = now
            changed = True
        if changed:
            self._mark_realtime_delivery_context_dirty(key)
        return changed

    async def _release_realtime_temporary_context_after_background_post(
        self,
        session_key: str,
        *,
        input_epoch: int | None,
        reason: str,
    ) -> bool:
        changed = self._release_realtime_temporary_context_after_background_post_in_memory(
            session_key,
            input_epoch=input_epoch,
            reason=reason,
        )
        if changed:
            await self._save_realtime_delivery_context_if_dirty(session_key)
        return changed

    def _realtime_delivery_context_dirty_cache(self) -> set[str]:
        dirty = getattr(self, "_realtime_delivery_context_dirty", None)
        if not isinstance(dirty, set):
            dirty = set()
            self._realtime_delivery_context_dirty = dirty
        return dirty

    def _mark_realtime_delivery_context_dirty(self, session_key: str) -> None:
        self._realtime_delivery_context_dirty_cache().add(str(session_key or "global"))

    def _realtime_delivery_context_restored_cache(self) -> set[str]:
        restored = getattr(self, "_realtime_delivery_context_restored", None)
        if not isinstance(restored, set):
            restored = set()
            self._realtime_delivery_context_restored = restored
        return restored

    def _realtime_delivery_context_payload(self, session_key: str) -> dict[str, Any]:
        key = str(session_key or "global")
        shadows = [
            dict(item)
            for item in list(
                self._realtime_assistant_history_shadow_cache().get(key) or (),
            )
            if isinstance(item, dict)
        ]
        breakpoints = [
            dict(item)
            for item in list(self._interrupted_reply_breakpoint_cache().get(key) or ())
            if isinstance(item, dict)
        ]
        withdrawals = [
            dict(item)
            for item in list(self._user_message_withdrawal_context_cache().get(key) or ())
            if isinstance(item, dict)
        ]
        ordinary_backfills = [
            dict(item)
            for item in list(self._realtime_ordinary_history_backfill_cache().get(key) or ())
            if isinstance(item, dict)
        ]
        return {
            "schema_version": "astrbot.realtime_delivery_context.v1",
            "kind": "realtime_delivery_context",
            "session_key": key,
            "updated_at": self._observed_now(),
            "shadows": shadows[-REALTIME_ASSISTANT_HISTORY_LIMIT:],
            "breakpoints": breakpoints[-INTERRUPTED_REPLY_BREAKPOINT_LIMIT:],
            "withdrawals": withdrawals[-USER_MESSAGE_WITHDRAWAL_CONTEXT_LIMIT:],
            "ordinary_backfills": ordinary_backfills[
                -REALTIME_ORDINARY_HISTORY_BACKFILL_LIMIT:
            ],
        }

    async def _restore_realtime_delivery_context_if_needed(
        self,
        session_key: str,
    ) -> None:
        key = str(session_key or "global")
        restored = self._realtime_delivery_context_restored_cache()
        if key in restored:
            return
        restored.add(key)
        if (
            self._realtime_assistant_history_shadow_cache().get(key)
            or self._interrupted_reply_breakpoint_cache().get(key)
            or self._user_message_withdrawal_context_cache().get(key)
        ):
            return
        try:
            data = await self._kv_get_data(
                self._realtime_delivery_context_kv_key(key),
                None,
                raise_on_error=True,
            )
        except Exception as exc:
            restored.discard(key)
            logger.debug(f"{PLUGIN_NAME}: realtime delivery context KV read failed: {exc}")
            return
        if not isinstance(data, dict):
            return
        shadows = [
            dict(item)
            for item in list(data.get("shadows") or [])[-REALTIME_ASSISTANT_HISTORY_LIMIT:]
            if isinstance(item, dict)
        ]
        breakpoints = [
            dict(item)
            for item in list(data.get("breakpoints") or [])[-INTERRUPTED_REPLY_BREAKPOINT_LIMIT:]
            if isinstance(item, dict)
        ]
        withdrawals = [
            dict(item)
            for item in list(data.get("withdrawals") or [])[-USER_MESSAGE_WITHDRAWAL_CONTEXT_LIMIT:]
            if isinstance(item, dict)
        ]
        ordinary_backfills = [
            dict(item)
            for item in list(data.get("ordinary_backfills") or [])[
                -REALTIME_ORDINARY_HISTORY_BACKFILL_LIMIT:
            ]
            if isinstance(item, dict)
        ]
        if shadows:
            self._realtime_assistant_history_shadow_cache()[key] = deque(
                shadows,
                maxlen=REALTIME_ASSISTANT_HISTORY_LIMIT,
            )
        if breakpoints:
            self._interrupted_reply_breakpoint_cache()[key] = deque(
                breakpoints,
                maxlen=INTERRUPTED_REPLY_BREAKPOINT_LIMIT,
            )
        if withdrawals:
            self._user_message_withdrawal_context_cache()[key] = deque(
                withdrawals,
                maxlen=USER_MESSAGE_WITHDRAWAL_CONTEXT_LIMIT,
            )
        if ordinary_backfills:
            self._realtime_ordinary_history_backfill_cache()[key] = deque(
                ordinary_backfills,
                maxlen=REALTIME_ORDINARY_HISTORY_BACKFILL_LIMIT,
            )

    async def _save_realtime_delivery_context_if_dirty(self, session_key: str) -> None:
        key = str(session_key or "global")
        dirty = self._realtime_delivery_context_dirty_cache()
        if key not in dirty:
            return
        payload = self._realtime_delivery_context_payload(key)
        try:
            await self._kv_put_data(self._realtime_delivery_context_kv_key(key), payload)
            dirty.discard(key)
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: realtime delivery context KV write failed: {exc}")

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
        delivery_status: str = "delivered",
        sent_parts: Sequence[str] | None = None,
        unsent_parts: Sequence[str] | None = None,
        event_time: dict[str, Any] | None = None,
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
        sent = [str(part or "").strip() for part in (sent_parts or []) if str(part or "").strip()]
        unsent = [
            str(part or "").strip()
            for part in (unsent_parts or [])
            if str(part or "").strip()
        ]
        if not sent and not unsent and parts:
            status = str(delivery_status or "delivered")
            if status == "delivered":
                sent = list(parts)
            else:
                unsent = list(parts)
        status = str(delivery_status or "delivered")
        sent_count = len(sent)
        unsent_count = len(unsent)
        full_hash = self._text_hash(text)
        event_time_payload = self._normalize_conversation_time_payload(event_time)
        entry = {
            "schema_version": "astrbot.realtime_assistant_history_shadow.v1",
            "kind": "realtime_assistant_history_shadow",
            "session_key": key,
            "source": str(source or "llm_response_intercept"),
            "input_epoch": input_epoch,
            "recorded_at": self._observed_now(),
            "event_time": event_time_payload,
            "event_local_time": str(event_time_payload.get("local_time") or ""),
            "event_timezone": str(event_time_payload.get("timezone") or ""),
            "event_epoch": event_time_payload.get("epoch"),
            "delivery_status": status,
            "message_count": len(parts) if parts else 1,
            "sent_count": sent_count,
            "unsent_count": unsent_count,
            "full_text_chars": len(text),
            "full_text_hash": full_hash,
            "sent_text_hash": self._text_hash(" / ".join(sent)),
            "unsent_text_hash": self._text_hash(" / ".join(unsent) if unsent else text),
            "full_text": self._head_text(text, INTERRUPTED_REPLY_LOCAL_MAX_CHARS),
            "full_text_truncated": len(text) > INTERRUPTED_REPLY_LOCAL_MAX_CHARS,
            "sent_excerpt": self._head_one_line(" / ".join(sent), 140),
            "unsent_head": self._head_one_line(
                " / ".join(unsent) if unsent else "",
                140,
            ),
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
        for existing in reversed(queue):
            if (
                isinstance(existing, dict)
                and str(existing.get("full_text_hash") or "") == full_hash
                and existing.get("input_epoch") == input_epoch
                and str(existing.get("source") or "") == entry["source"]
            ):
                consumed = bool(existing.get("consumed"))
                consumed_at = existing.get("consumed_at")
                existing.update(entry)
                existing["consumed"] = consumed
                if consumed_at is not None:
                    existing["consumed_at"] = consumed_at
                self._mark_realtime_delivery_context_dirty(key)
                return
        queue.append(entry)
        self._mark_realtime_delivery_context_dirty(key)

    def _append_realtime_assistant_history_shadow_if_any(
        self,
        request: ProviderRequest,
        session_key: str,
        *,
        budget: _StateInjectionBudget | None,
        current_user_text: str = "",
        observed_at: float | None = None,
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
        if self._realtime_shadow_stale_for_recency_sensitive_turn(
            item,
            current_user_text,
            observed_at=observed_at,
        ):
            item["consumed"] = True
            item["consumed_at"] = self._observed_now()
            item["consumed_reason"] = "stale_for_recency_sensitive_turn"
            self._mark_realtime_delivery_context_dirty(session_key)
            return False
        if (
            str(item.get("delivery_status") or "") == "interrupted"
            and self._has_pending_interrupted_reply_breakpoint(session_key)
        ):
            return False
        if self._context_compression_summary_covers_realtime_shadow(request, item):
            item["consumed"] = True
            item["consumed_at"] = self._observed_now()
            item["consumed_reason"] = "official_context_compression_summary"
            self._mark_realtime_delivery_context_dirty(session_key)
            return False
        if self._agent_history_already_contains_realtime_shadow(request, item):
            item["consumed"] = True
            item["consumed_at"] = self._observed_now()
            item["consumed_reason"] = "agent_history_already_contains_reply"
            self._mark_realtime_delivery_context_dirty(session_key)
            return False
        self._append_agent_context_message(
            request,
            role="assistant",
            content=str(item.get("full_text") or item.get("excerpt") or ""),
        )
        self._append_realtime_assistant_history_usage_guard(
            request,
            current_user_text=current_user_text,
            budget=budget,
        )
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
                self._mark_realtime_delivery_context_dirty(session_key)
                return True
        event_time_line = self._event_time_field_line(item.get("event_time") or item)
        text = "\n".join(
            [
                "[sylanne_realtime_assistant_history]",
                "上一轮回复使用即时聊天分条发送，可能没有进入平台的普通 LLM 历史。下面是一次性短上下文，用来保持代词、指代和刚才话题，不要逐字复读。",
                "source={source}; delivery_status={status}; message_count={message_count}; sent_count={sent}; unsent_count={unsent}; chars={chars}; full_hash={hash}".format(
                    source=self._head_one_line(str(item.get("source") or ""), 48),
                    status=self._head_one_line(str(item.get("delivery_status") or "delivered"), 32),
                    message_count=int(item.get("message_count") or 0),
                    sent=int(item.get("sent_count") or 0),
                    unsent=int(item.get("unsent_count") or 0),
                    chars=int(item.get("full_text_chars") or 0),
                    hash=str(item.get("full_text_hash") or "")[:16],
                ),
                event_time_line,
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
            self._mark_realtime_delivery_context_dirty(session_key)
        return appended

    def _extract_pending_bot_question_excerpt(self, text: str) -> str:
        value = " ".join(str(text or "").split()).strip()
        if not value:
            return ""
        parts = [
            part.strip()
            for part in re.split(r"(?<=[。！？!?；;])\s*|/+", value)
            if part.strip()
        ]
        candidates = parts or [value]
        start_index = max(0, len(candidates) - 5)
        for index in range(len(candidates) - 1, start_index - 1, -1):
            candidate = candidates[index]
            if self._looks_like_choice_or_direct_question(candidate):
                return self._head_text(
                    self._pending_bot_question_cluster(candidates, index),
                    220,
                )
        if self._looks_like_choice_or_direct_question(value):
            return self._head_text(value, 220)
        return ""

    def _pending_bot_question_cluster(
        self,
        candidates: Sequence[str],
        question_index: int,
    ) -> str:
        index = max(0, min(int(question_index), len(candidates) - 1))
        start = index
        while start > 0 and index - start < 3:
            previous = str(candidates[start - 1] or "").strip()
            if not previous:
                break
            cluster = " ".join(
                str(item or "").strip()
                for item in candidates[start - 1 : index + 1]
                if str(item or "").strip()
            )
            if len(cluster) > 220:
                break
            if not (
                self._looks_like_choice_or_direct_question(previous)
                or self._looks_like_question_lead_in_clause(previous)
            ):
                break
            start -= 1
        return " ".join(
            str(item or "").strip()
            for item in candidates[start : index + 1]
            if str(item or "").strip()
        )

    def _looks_like_question_lead_in_clause(self, text: str) -> bool:
        value = " ".join(str(text or "").split()).strip()
        if not value or len(value) > 28:
            return False
        return value.endswith(("，", ",", "、", "：", ":"))

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
        question_time_line = self._event_time_field_line(
            item.get("event_time") or item,
            local_key="question_event_local_time",
            timezone_key="question_timezone",
            epoch_key="question_event_epoch",
        )
        text = "\n".join(
            [
                "[sylanne_realtime_pending_bot_question]",
                "上一轮 bot 刚提出了一个未闭合问题或二选一问题；当前用户短句优先视为对这个问题的回答，不要把它当成孤立的新话题。",
                "如果回答很短，例如 IP、域名、A、B、可以、不行，请先绑定到 last_bot_question，再继续给出下一步。",
                "像“咖啡啊”“域名”“IP”“可以”这类名词或短答，默认是在补全上一轮问题的槽位；不要把它当成用户正在发起新的行动或命令。",
                "source={source}; full_hash={hash}; expects_short_answer={expects}".format(
                    source=self._head_one_line(str(item.get("source") or ""), 48),
                    hash=str(item.get("full_text_hash") or "")[:16],
                    expects=bool(item.get("expects_short_answer")),
                ),
                question_time_line,
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
        event_time: dict[str, Any] | None = None,
    ) -> None:
        text = str(full_text or "").strip()
        if not text:
            return
        started_at = self._observed_now()
        event_time_payload = self._normalize_conversation_time_payload(event_time)
        started_time_payload = self._conversation_time_payload(started_at)
        self._realtime_chat_active_dispatch_cache()[str(session_key or "global")] = {
            "schema_version": "astrbot.realtime_chat_active_dispatch.v1",
            "kind": "realtime_chat_active_dispatch",
            "session_key": str(session_key or "global"),
            "source": str(source or "realtime_chat"),
            "input_epoch": input_epoch,
            "started_at": started_at,
            "trigger_event_time": event_time_payload,
            "trigger_event_local_time": str(event_time_payload.get("local_time") or ""),
            "trigger_timezone": str(event_time_payload.get("timezone") or ""),
            "trigger_event_epoch": event_time_payload.get("epoch"),
            "dispatch_started_time": started_time_payload,
            "dispatch_started_local_time": str(started_time_payload.get("local_time") or ""),
            "dispatch_started_timezone": str(started_time_payload.get("timezone") or ""),
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
        trigger_time_line = self._event_time_field_line(
            active.get("trigger_event_time") or active,
            local_key="trigger_event_local_time",
            timezone_key="trigger_timezone",
            epoch_key="trigger_event_epoch",
        )
        dispatch_time_line = self._event_time_field_line(
            active.get("dispatch_started_time") or {},
            local_key="dispatch_started_local_time",
            timezone_key="dispatch_started_timezone",
            epoch_key="dispatch_started_epoch",
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
                trigger_time_line,
                dispatch_time_line,
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

    def _mark_control_event_no_llm_response(
        self,
        event: AstrMessageEvent,
        request: ProviderRequest,
        *,
        reason: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        for target in (event, request):
            for name, value in (
                ("_sylanne_control_event", True),
                ("_sylanne_control_event_payload", payload or {}),
                ("_sylanne_default_response_stopped", True),
                ("_sylanne_default_response_stop_reason", str(reason or "control_event")),
            ):
                try:
                    setattr(target, name, value)
                except Exception:
                    pass
        self._stop_default_response_send(event, reason=reason)

    def _record_realtime_user_typing_status(
        self,
        session_key: str,
        payload: dict[str, Any],
    ) -> None:
        key = str(session_key or "global")
        cache = getattr(self, "_realtime_user_typing_until", None)
        if not isinstance(cache, dict):
            cache = {}
            self._realtime_user_typing_until = cache
        configured_hold_seconds = self._cfg_float("realtime_user_typing_hold_seconds", 0.8)
        if "hold_seconds" in payload:
            configured_hold_seconds = self._as_float_value(
                payload.get("hold_seconds"),
                configured_hold_seconds,
            )
        hold_seconds = max(
            0.0,
            min(2.5, configured_hold_seconds),
        )
        if hold_seconds <= 0:
            return
        now = self._observed_now()
        until = now + hold_seconds
        cache[key] = max(float(cache.get(key) or 0.0), until)
        payload["typing_hold_until"] = cache[key]

    def _empty_input_typing_status_payload(
        self,
        event: AstrMessageEvent,
        request: ProviderRequest,
    ) -> dict[str, Any]:
        if not self._realtime_chat_enabled():
            return {}
        if self._event_has_current_user_payload(event):
            return {}
        if self._request_has_current_user_payload(request):
            return {}
        session_key = self._resolve_public_session_key(event, request=request)
        dispatch_in_flight = self._realtime_chat_dispatch_in_flight(session_key)
        hold_seconds = max(
            0.0,
            min(1.0, self._cfg_float("realtime_empty_input_typing_hold_seconds", 0.35)),
        )
        return {
            "platform": "generic",
            "kind": (
                "empty_input_typing_status"
                if dispatch_in_flight and hold_seconds > 0
                else "empty_input_event"
            ),
            "dispatch_in_flight": dispatch_in_flight,
            "hold_seconds": hold_seconds,
        }

    def _realtime_chat_dispatch_in_flight(self, session_key: str) -> bool:
        key = str(session_key or "global")
        active = self._realtime_chat_active_dispatch_cache().get(key)
        if isinstance(active, dict) and not active.get("completed"):
            return True
        tasks = self._realtime_chat_dispatch_task_cache().get(key)
        return any(not task.done() for task in list(tasks or ()))

    def _event_has_current_user_payload(self, event: AstrMessageEvent) -> bool:
        if self._event_text(event).strip():
            return True
        for holder in (event, getattr(event, "message_obj", None)):
            if holder is None:
                continue
            for name in ("message", "messages", "message_chain"):
                if self._value_has_current_user_payload(getattr(holder, name, None)):
                    return True
        raw = self._raw_platform_payload(event)
        return self._value_has_current_user_payload(raw)

    def _request_has_current_user_payload(self, request: ProviderRequest | None) -> bool:
        if request is None:
            return False
        if str(getattr(request, "prompt", "") or "").strip():
            return True
        for part in getattr(request, "extra_user_content_parts", []) or []:
            if self._value_has_current_user_payload(part):
                return True
        return False

    def _value_has_current_user_payload(self, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (bytes, bytearray)):
            return bool(value)
        if isinstance(value, dict):
            segment_type = str(
                value.get("type") or value.get("message_type") or "",
            ).strip().lower()
            if segment_type in {"text", "plain"}:
                data = value.get("data")
                if isinstance(data, dict):
                    return self._value_has_current_user_payload(data.get("text"))
                return self._value_has_current_user_payload(
                    value.get("text") or value.get("content"),
                )
            if segment_type in {
                "image",
                "record",
                "voice",
                "audio",
                "video",
                "file",
                "face",
                "mface",
                "reply",
                "at",
                "json",
                "xml",
            }:
                return True
            for name in (
                "text",
                "content",
                "message",
                "raw_message",
                "url",
                "file",
                "path",
                "base64",
                "data",
            ):
                if self._value_has_current_user_payload(value.get(name)):
                    return True
            return False
        if isinstance(value, (list, tuple, set)):
            return any(self._value_has_current_user_payload(item) for item in value)
        text = getattr(value, "text", None)
        if isinstance(text, str) and text.strip():
            return True
        for name in ("url", "file", "path", "image_url", "audio_url", "video_url"):
            if getattr(value, name, None):
                return True
        type_name = type(value).__name__.lower()
        return any(
            marker in type_name
            for marker in ("image", "audio", "voice", "video", "file", "sticker")
        )

    async def _wait_for_realtime_user_typing_window(
        self,
        session_key: str,
        *,
        input_epoch: int | None,
    ) -> None:
        key = str(session_key or "global")
        cache = getattr(self, "_realtime_user_typing_until", None)
        if not isinstance(cache, dict):
            return
        while not self._conversation_reply_is_stale(key, input_epoch):
            until = float(cache.get(key) or 0.0)
            now = self._observed_now()
            remaining = until - now
            if remaining <= 0:
                cache.pop(key, None)
                return
            await asyncio.sleep(min(0.25, remaining))

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

    def _napcat_input_status_payload(
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
        sub_type = str(raw.get("sub_type") or "").strip()
        if post_type and post_type != "notice":
            return {}
        if notice_type != "notify" or sub_type != "input_status":
            return {}
        return {
            "platform": "napcat_onebot",
            "post_type": post_type or "notice",
            "notice_type": notice_type,
            "sub_type": sub_type,
            "status_text": str(raw.get("status_text") or ""),
            "event_type": str(raw.get("event_type") or ""),
            "user_id": str(raw.get("user_id") or ""),
            "group_id": str(raw.get("group_id") or ""),
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

    async def _legacy_state_tool_snapshot(
        self,
        event: AstrMessageEvent,
        state_name: str,
        *,
        detail: str = "summary",
        track: str = "conversation",
    ) -> dict[str, Any] | None:
        detail_mode = "full" if str(detail or "").strip().lower() == "full" else "summary"
        session_key = self._resolve_public_session_key(event)
        return await self._query_single_agent_state(
            state_name,
            event,
            request=None,
            session_key=session_key,
            detail=detail_mode,
            track=track,
        )

    def _plain_tool_json_result(
        self,
        event: AstrMessageEvent,
        payload: dict[str, Any] | None,
    ) -> Any:
        return event.plain_result(self._llm_tool_json_result(payload or {}))

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
        snapshot = await self._legacy_state_tool_snapshot(
            event,
            "emotion",
            detail=detail,
            track=track,
        )
        yield self._plain_tool_json_result(event, snapshot)

    async def get_bot_group_atmosphere_state_tool(
        self,
        event: AstrMessageEvent,
        detail: str = "summary",
    ):
        """只读获取当前房间情绪与群聊氛围状态。"""
        snapshot = await self._legacy_state_tool_snapshot(
            event,
            "group_atmosphere",
            detail=detail,
        )
        yield self._plain_tool_json_result(event, snapshot)

    @filter.llm_tool(name="query_agent_state")
    async def query_agent_state_tool(
        self,
        event: AstrMessageEvent,
        state: str = "integrated",
        detail: str = "summary",
        track: str = "conversation",
        include_runtime: bool = False,
    ):
        """统一只读查询 Sylanne 情绪代理的状态快照。"""
        payload = await self.query_agent_state(
            event,
            state=state,
            detail=detail,
            track=track,
            include_runtime=include_runtime,
        )
        return self._llm_tool_json_result(payload)

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
        yield self._plain_tool_json_result(event, snapshot)

    async def get_bot_humanlike_state_tool(
        self,
        event: AstrMessageEvent,
        detail: str = "summary",
    ):
        """只读获取 bot 的拟人/有机体状态。"""
        snapshot = await self._legacy_state_tool_snapshot(
            event,
            "humanlike",
            detail=detail,
        )
        yield self._plain_tool_json_result(event, snapshot)

    async def get_bot_lifelike_learning_state_tool(
        self,
        event: AstrMessageEvent,
        detail: str = "summary",
    ):
        """只读获取 bot 的生命化学习、共同语境与主动性状态。"""
        snapshot = await self._legacy_state_tool_snapshot(
            event,
            "lifelike_learning",
            detail=detail,
        )
        yield self._plain_tool_json_result(event, snapshot)

    async def get_bot_proactive_speech_decision_tool(
        self,
        event: AstrMessageEvent,
        candidate_context: str = "",
        use_llm: bool = True,
    ):
        """判断 bot 是否应该主动发言，并给出候选话题。"""
        decision = await self.get_proactive_speech_decision(
            event,
            candidate_context=candidate_context,
            use_llm=use_llm,
        )
        yield self._plain_tool_json_result(event, decision)

    async def request_bot_proactive_speech_dispatch_tool(
        self,
        event: AstrMessageEvent,
        candidate_context: str = "",
        use_llm: bool = True,
        dry_run: bool = True,
        force: bool = False,
        message_text: str = "",
    ):
        """请求 AstrBot 主动发言调度，并返回证据与诊断。"""
        result = await self.request_proactive_speech_dispatch(
            event,
            candidate_context=candidate_context,
            use_llm=use_llm,
            dry_run=dry_run,
            force=force,
            message_text=message_text,
        )
        yield self._plain_tool_json_result(event, result)

    async def get_bot_personality_drift_state_tool(
        self,
        event: AstrMessageEvent,
        detail: str = "summary",
    ):
        """只读获取 bot 的慢速实时人格漂移状态。"""
        snapshot = await self._legacy_state_tool_snapshot(
            event,
            "personality_drift",
            detail=detail,
        )
        yield self._plain_tool_json_result(event, snapshot)

    async def get_bot_moral_repair_state_tool(
        self,
        event: AstrMessageEvent,
        detail: str = "summary",
    ):
        """只读获取 bot 的道德修复与信任修复状态。"""
        snapshot = await self._legacy_state_tool_snapshot(
            event,
            "moral_repair",
            detail=detail,
        )
        yield self._plain_tool_json_result(event, snapshot)

    async def get_bot_fallibility_state_tool(
        self,
        event: AstrMessageEvent,
        detail: str = "summary",
    ):
        """只读获取 bot 的低风险瑕疵/犯错模拟状态。"""
        snapshot = await self._legacy_state_tool_snapshot(
            event,
            "fallibility",
            detail=detail,
        )
        yield self._plain_tool_json_result(event, snapshot)

    async def get_bot_integrated_self_state_tool(
        self,
        event: AstrMessageEvent,
        detail: str = "summary",
    ):
        """只读获取 bot 的综合自我状态仲裁快照。"""
        snapshot = await self._legacy_state_tool_snapshot(
            event,
            "integrated",
            detail=detail,
        )
        yield self._plain_tool_json_result(event, snapshot)

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
        """查看当前会话的拟人/有机体状态。"""
        if not self._humanlike_modeling_enabled():
            yield event.plain_result("拟人化状态模拟未启用。")
            return
        state = await self._load_humanlike_state(self._session_key(event))
        yield event.plain_result(format_humanlike_state_for_user(state))

    @filter.command("humanlike_reset", alias={"拟人状态重置"})
    async def humanlike_reset(self, event: AstrMessageEvent):
        """重置当前会话的拟人/有机体状态。"""
        if not self._humanlike_reset_allowed():
            yield event.plain_result("配置已关闭手动拟人状态重置。")
            return
        await self._delete_humanlike_state(self._session_key(event))
        yield event.plain_result("已重置当前会话的拟人状态。")

    @filter.command("lifelike_state", alias={"生命化状态", "共同语境"})
    async def lifelike_learning_status(self, event: AstrMessageEvent):
        """查看当前会话的生命化学习与共同语境状态。"""
        if not self._lifelike_learning_enabled():
            yield event.plain_result("生命化学习状态未启用。")
            return
        state = await self._load_lifelike_learning_state(self._session_key(event))
        yield event.plain_result(format_lifelike_state_for_user(state))

    @filter.command("lifelike_reset", alias={"生命化状态重置", "共同语境重置"})
    async def lifelike_learning_reset(self, event: AstrMessageEvent):
        """重置当前会话的生命化学习与共同语境状态。"""
        if not self._lifelike_learning_reset_allowed():
            yield event.plain_result("配置已关闭生命化学习状态重置。")
            return
        await self._delete_lifelike_learning_state(self._session_key(event))
        yield event.plain_result("已重置当前会话的生命化学习状态。")

    @filter.command("personality_drift_state", alias={"人格漂移状态", "人格适应状态"})
    async def personality_drift_status(self, event: AstrMessageEvent):
        """查看当前会话的慢速实时人格漂移状态。"""
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
        """重置当前会话的慢速人格漂移状态。"""
        if not self._personality_drift_reset_allowed():
            yield event.plain_result("配置已关闭人格漂移重置后门。")
            return
        await self._delete_personality_drift_state(self._session_key(event))
        yield event.plain_result("已重置当前会话的人格漂移状态。")

    @filter.command("moral_repair_state", alias={"道德修复状态", "信任修复状态"})
    async def moral_repair_status(self, event: AstrMessageEvent):
        """查看当前会话的道德修复/信任修复状态。"""
        if not self._moral_repair_modeling_enabled():
            yield event.plain_result("道德修复状态模拟未启用。")
            return
        state = await self._load_moral_repair_state(self._session_key(event))
        yield event.plain_result(format_moral_repair_state_for_user(state))

    @filter.command("moral_repair_reset", alias={"道德修复重置", "信任修复重置"})
    async def moral_repair_reset(self, event: AstrMessageEvent):
        """重置当前会话的道德修复/信任修复状态。"""
        if not self._moral_repair_reset_allowed():
            yield event.plain_result("配置已关闭手动道德修复状态重置。")
            return
        await self._delete_moral_repair_state(self._session_key(event))
        yield event.plain_result("已重置当前会话的道德修复状态。")

    @filter.command("integrated_self", alias={"综合自我状态", "自我状态"})
    async def integrated_self_status(self, event: AstrMessageEvent):
        """查看当前会话的综合自我状态仲裁。"""
        snapshot = await self.get_integrated_self_snapshot(event)
        yield event.plain_result(format_integrated_self_state_for_user(snapshot))

    @filter.command("shadow_diagnostics", alias={"阴影诊断", "阴影状态"})
    async def shadow_diagnostics_status(self, event: AstrMessageEvent):
        """查看配置门控的只读阴影诊断。"""
        snapshot = await self.get_shadow_diagnostics(event)
        yield event.plain_result(json.dumps(snapshot, ensure_ascii=False))

    @filter.command("fallibility_state", alias={"瑕疵状态", "犯错模拟状态"})
    async def fallibility_status(self, event: AstrMessageEvent):
        """查看当前会话的低风险瑕疵/犯错模拟状态。"""
        if not self._fallibility_modeling_enabled():
            yield event.plain_result("瑕疵/犯错模拟状态未启用。")
            return
        state = await self._load_fallibility_state(self._session_key(event))
        yield event.plain_result(format_fallibility_state_for_user(state))

    @filter.command("fallibility_reset", alias={"瑕疵状态重置", "犯错模拟重置"})
    async def fallibility_reset(self, event: AstrMessageEvent):
        """重置当前会话的低风险瑕疵/犯错模拟状态。"""
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
        """只读查询 Sylanne 自有长期记忆。"""
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
            llm_resp = None
            for attempt in range(2):
                try:
                    llm_resp = await self._call_internal_assessor_llm(
                        provider_id=provider_id,
                        prompt=prompt,
                        system_prompt=system_prompt,
                    )
                    break
                except asyncio.TimeoutError:
                    self._log_warning(f"{PLUGIN_NAME}: LLM 情绪估计超时，启用回退估计。")
                    return heuristic_observation(current_text, profile=persona_profile)
                except Exception as exc:
                    if attempt == 0 and self._looks_like_empty_model_output_error(exc):
                        self._log_warning(
                            f"{PLUGIN_NAME}: LLM 情绪估计空输出，重试一次: {exc}",
                        )
                        continue
                    self._log_warning(f"{PLUGIN_NAME}: LLM 情绪估计失败，启用回退估计: {exc}")
                    return heuristic_observation(current_text, profile=persona_profile)
        finally:
            _INTERNAL_LLM_CALL.reset(token)

        observation = observation_from_llm_text(getattr(llm_resp, "completion_text", ""))
        if observation is None:
            self._log_warning(f"{PLUGIN_NAME}: 情绪估计输出不是可解析 JSON，启用回退估计。")
            return heuristic_observation(current_text, profile=persona_profile)
        return observation

    def _looks_like_empty_model_output_error(self, exc: BaseException) -> bool:
        text = f"{exc.__class__.__name__}: {exc}".lower()
        return (
            "emptymodeloutputerror" in text
            or "completion has no usable output" in text
            or "no usable output" in text
        )

    async def _provider_id(self, event: AstrMessageEvent) -> str | None:
        configured = str(self._cfg("emotion_provider_id", "") or "").strip()
        if configured:
            return configured
        return await self._chat_provider_id(event, use_cache=True)

    async def _fast_assessor_provider_id(self, event: AstrMessageEvent) -> str | None:
        if not self._cfg_bool("fast_assessor_enabled", False):
            return None
        configured = str(self._cfg("fast_assessor_provider_id", "") or "").strip()
        if configured:
            return configured
        return None

    def _fast_assessor_max_context_chars(self) -> int:
        return max(240, min(1200, self._cfg_int("fast_assessor_max_context_chars", 600)))

    async def _chat_provider_id(
        self,
        event: AstrMessageEvent,
        *,
        use_cache: bool,
    ) -> str | None:
        if not hasattr(self, "_provider_id_cache"):
            self._provider_id_cache = {}
        umo = str(getattr(event, "unified_msg_origin", "") or "global")
        cached = self._provider_id_cache.get(umo)
        now = time.time()
        if use_cache and cached and now - cached[0] <= max(
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
            data = await self._kv_get_data(kv_key, None)
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
            await self._kv_put_data(
                self._kv_key(session_key),
                state.to_dict(),
                label="emotion state KV write",
            )
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: KV 写入失败，仅保留内存状态: {exc}")

    async def _delete_state(self, session_key: str) -> None:
        self._memory_cache.pop(session_key, None)
        try:
            await self._kv_delete_data(self._kv_key(session_key))
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
            data = await self._kv_get_data(self._psychological_kv_key(session_key), None)
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
            await self._kv_put_data(self._psychological_kv_key(session_key), state.to_dict())
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: 心理筛查 KV 写入失败，仅保留内存状态: {exc}")

    async def _delete_psychological_state(self, session_key: str) -> None:
        self._psychological_memory_cache.pop(session_key, None)
        try:
            await self._kv_delete_data(self._psychological_kv_key(session_key))
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
            data = await self._kv_get_data(self._humanlike_kv_key(session_key), None)
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
            await self._kv_put_data(self._humanlike_kv_key(session_key), state.to_dict())
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: humanlike KV write failed, keeping memory only: {exc}")

    async def _delete_humanlike_state(self, session_key: str) -> None:
        self._ensure_runtime_state_containers()
        self._humanlike_memory_cache.pop(session_key, None)
        try:
            await self._kv_delete_data(self._humanlike_kv_key(session_key))
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
            data = await self._kv_get_data(
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
            await self._kv_put_data(
                self._lifelike_learning_kv_key(session_key),
                state.to_dict(),
            )
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: lifelike learning KV write failed, keeping memory only: {exc}")

    async def _delete_lifelike_learning_state(self, session_key: str) -> None:
        self._ensure_runtime_state_containers()
        self._lifelike_learning_memory_cache.pop(session_key, None)
        try:
            await self._kv_delete_data(self._lifelike_learning_kv_key(session_key))
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
            data = await self._kv_get_data(
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
        if not hasattr(self, "_sylanne_memory_query_embedding_cache"):
            self._sylanne_memory_query_embedding_cache = {}
        if not hasattr(self, "_sylanne_memory_record_embedding_last_at"):
            self._sylanne_memory_record_embedding_last_at = {}
        if not hasattr(self, "_sylanne_memory_pending_observations"):
            self._sylanne_memory_pending_observations = {}
        if not hasattr(self, "_sylanne_memory_idle_tasks"):
            self._sylanne_memory_idle_tasks = {}
        if not hasattr(self, "_sylanne_memory_idle_generation"):
            self._sylanne_memory_idle_generation = {}

    def _passive_load_is_fresh(self, state: Any, *, now: float | None = None) -> bool:
        updated_at = getattr(state, "updated_at", None)
        try:
            observed_at = self._observed_now() if now is None else float(now)
            elapsed = observed_at - float(updated_at)
        except (TypeError, ValueError):
            return False
        return elapsed <= max(0.0, self._cfg_float("passive_load_fresh_seconds", 1.0))

    async def _await_kv_operation(self, result: Any, *, label: str) -> Any:
        del label
        if not inspect.isawaitable(result):
            return result
        return await result

    async def _kv_get_data(
        self,
        key: str,
        default: Any = None,
        *,
        label: str = "KV read",
        raise_on_error: bool = False,
    ) -> Any:
        getter = getattr(self, "get_kv_data", None)
        if not callable(getter):
            return default
        try:
            return await self._await_kv_operation(
                getter(key, default),
                label=label,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if raise_on_error:
                raise
            logger.debug(f"{PLUGIN_NAME}: {label} failed for {key}: {exc}")
            return default

    async def _kv_put_data(
        self,
        key: str,
        value: Any,
        *,
        label: str = "KV write",
        raise_on_error: bool = False,
    ) -> bool:
        putter = getattr(self, "put_kv_data", None)
        if not callable(putter):
            return False
        try:
            await self._await_kv_operation(
                putter(key, value),
                label=label,
            )
            return True
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if raise_on_error:
                raise
            logger.debug(f"{PLUGIN_NAME}: {label} failed for {key}: {exc}")
            return False

    async def _kv_delete_data(
        self,
        key: str,
        *,
        label: str = "KV delete",
        raise_on_error: bool = False,
    ) -> bool:
        deleter = getattr(self, "delete_kv_data", None)
        if not callable(deleter):
            return False
        try:
            await self._await_kv_operation(
                deleter(key),
                label=label,
            )
            return True
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if raise_on_error:
                raise
            logger.debug(f"{PLUGIN_NAME}: {label} failed for {key}: {exc}")
            return False

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
            await self._kv_put_data(
                self._personality_drift_kv_key(session_key),
                state.to_dict(),
            )
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: personality drift KV write failed, keeping memory only: {exc}")

    async def _delete_personality_drift_state(self, session_key: str) -> None:
        self._ensure_runtime_state_containers()
        self._personality_drift_memory_cache.pop(session_key, None)
        try:
            await self._kv_delete_data(self._personality_drift_kv_key(session_key))
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
            data = await self._kv_get_data(self._moral_repair_kv_key(session_key), None)
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
            await self._kv_put_data(self._moral_repair_kv_key(session_key), state.to_dict())
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: moral repair KV write failed, keeping memory only: {exc}")

    async def _delete_moral_repair_state(self, session_key: str) -> None:
        self._moral_repair_memory_cache.pop(session_key, None)
        try:
            await self._kv_delete_data(self._moral_repair_kv_key(session_key))
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
            data = await self._kv_get_data(self._fallibility_kv_key(session_key), None)
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
            await self._kv_put_data(self._fallibility_kv_key(session_key), state.to_dict())
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: fallibility KV write failed, keeping memory only: {exc}")

    async def _delete_fallibility_state(self, session_key: str) -> None:
        self._fallibility_memory_cache.pop(session_key, None)
        try:
            await self._kv_delete_data(self._fallibility_kv_key(session_key))
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
            data = await self._kv_get_data(
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
            await self._kv_put_data(
                self._group_atmosphere_kv_key(session_key),
                state.to_dict(),
            )
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: group atmosphere KV write failed, keeping memory only: {exc}")

    async def _delete_group_atmosphere_state(self, session_key: str) -> None:
        self._group_atmosphere_memory_cache.pop(session_key, None)
        try:
            await self._kv_delete_data(self._group_atmosphere_kv_key(session_key))
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: group atmosphere KV delete failed: {exc}")

    async def _load_sylanne_memory_state(
        self,
        session_key: str,
        *,
        now: float | None = None,
        save_decay: bool = True,
    ) -> SylanneMemoryState:
        observed_now = self._observed_now() if now is None else float(now)
        self._ensure_runtime_state_containers()
        if session_key in self._sylanne_memory_cache:
            state = self._sylanne_memory_cache[session_key]
            before = state.to_dict()
            decayed_state = apply_memory_time_decay(state, now=observed_now)
            if decayed_state.to_dict() != before:
                if save_decay:
                    await self._save_sylanne_memory_state(session_key, decayed_state)
                else:
                    self._sylanne_memory_cache[session_key] = decayed_state
                return decayed_state
            return state
        try:
            data = await self._kv_get_data(
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
        if save_decay and data is not None and state.to_dict() != before:
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
            await self._kv_put_data(
                self._sylanne_memory_kv_key(session_key),
                state.to_dict(),
            )
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: Sylanne memory KV write failed, keeping memory only: {exc}")

    async def _delete_sylanne_memory_state(self, session_key: str) -> None:
        self._ensure_runtime_state_containers()
        self._sylanne_memory_cache.pop(session_key, None)
        try:
            await self._kv_delete_data(self._sylanne_memory_kv_key(session_key))
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: Sylanne memory KV delete failed: {exc}")

    async def _observe_sylanne_memory_event_if_enabled(
        self,
        session_key: str,
        text: str,
        *,
        event: AstrMessageEvent | None = None,
        speaker_id: str = "",
        emotion_state: EmotionState | None = None,
        personality_drift_state: PersonalityDriftState | None = None,
        lifelike_learning_state: LifelikeLearningState | None = None,
        group_atmosphere_state: GroupAtmosphereState | None = None,
        observed_at: float | None = None,
        defer_until_idle: bool = False,
    ) -> None:
        if not self._sylanne_memory_enabled():
            return
        text = str(text or "").strip()
        if not text:
            return
        now = self._observed_now() if observed_at is None else float(observed_at)
        observation = self._sylanne_memory_observation_payload(
            session_key,
            text,
            event=event,
            speaker_id=speaker_id,
            emotion_state=emotion_state,
            personality_drift_state=personality_drift_state,
            lifelike_learning_state=lifelike_learning_state,
            group_atmosphere_state=group_atmosphere_state,
            observed_at=now,
        )
        if defer_until_idle:
            self._queue_sylanne_memory_observation(session_key, observation)
            return
        await self._commit_sylanne_memory_observation(session_key, observation)

    def _sylanne_memory_observation_payload(
        self,
        session_key: str,
        text: str,
        *,
        event: AstrMessageEvent | None,
        speaker_id: str,
        emotion_state: EmotionState | None,
        personality_drift_state: PersonalityDriftState | None,
        lifelike_learning_state: LifelikeLearningState | None,
        group_atmosphere_state: GroupAtmosphereState | None,
        observed_at: float,
    ) -> dict[str, Any]:
        return {
            "session_key": str(session_key or "global"),
            "text": str(text or "").strip(),
            "speaker_id": str(speaker_id or ""),
            "observed_at": float(observed_at),
            "emotion_snapshot": (
                emotion_state.to_public_dict(
                    session_key=session_key,
                    include_safety=self._safety_boundary_enabled(),
                )
                if emotion_state is not None
                else None
            ),
            "personality_drift_snapshot": (
                personality_drift_state.to_public_dict(
                    session_key=session_key,
                    exposure="plugin_safe",
                )
                if personality_drift_state is not None
                else None
            ),
            "lifelike_snapshot": (
                lifelike_learning_state.to_public_dict(
                    session_key=session_key,
                    exposure="plugin_safe",
                )
                if lifelike_learning_state is not None
                else None
            ),
            "group_atmosphere_snapshot": (
                group_atmosphere_state.to_public_dict(
                    session_key=session_key,
                    exposure="plugin_safe",
                )
                if group_atmosphere_state is not None
                else None
            ),
            "event_time": self._conversation_time_payload(observed_at, event=event),
        }

    def _queue_sylanne_memory_observation(
        self,
        session_key: str,
        observation: dict[str, Any],
    ) -> None:
        self._ensure_runtime_state_containers()
        key = str(session_key or "global")
        queue = self._sylanne_memory_pending_observations.setdefault(
            key,
            deque(maxlen=24),
        )
        queue.append(dict(observation))
        generation = int(self._sylanne_memory_idle_generation.get(key) or 0) + 1
        self._sylanne_memory_idle_generation[key] = generation
        self._schedule_sylanne_memory_idle_commit(key, generation)

    def _schedule_sylanne_memory_idle_commit(
        self,
        session_key: str,
        generation: int,
    ) -> None:
        key = str(session_key or "global")
        task = self._sylanne_memory_idle_tasks.get(key)
        if task is not None and not task.done():
            task.cancel()
        if getattr(self, "_terminating", False):
            return
        task = asyncio.create_task(
            self._sylanne_memory_idle_commit_later(key, generation),
        )
        self._sylanne_memory_idle_tasks[key] = task

        def _consume_idle_memory_result(done: asyncio.Task[Any]) -> None:
            if self._sylanne_memory_idle_tasks.get(key) is done and done.done():
                self._sylanne_memory_idle_tasks.pop(key, None)
            try:
                done.result()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                self._log_warning(
                    f"{PLUGIN_NAME}: Sylanne memory idle commit failed: {exc}",
                )

        task.add_done_callback(_consume_idle_memory_result)

    async def _sylanne_memory_idle_commit_later(
        self,
        session_key: str,
        generation: int,
    ) -> None:
        await asyncio.sleep(self._sylanne_memory_idle_commit_delay_seconds())
        await self._flush_sylanne_memory_pending_observations(
            session_key,
            generation=generation,
        )

    def _sylanne_memory_idle_commit_delay_seconds(self) -> float:
        return max(
            0.25,
            min(20.0, self._cfg_float("sylanne_memory_idle_commit_delay_seconds", 4.0)),
        )

    async def _flush_sylanne_memory_pending_observations(
        self,
        session_key: str,
        *,
        generation: int | None = None,
        force: bool = False,
    ) -> None:
        self._ensure_runtime_state_containers()
        key = str(session_key or "global")
        if generation is not None and generation != self._sylanne_memory_idle_generation.get(key):
            return
        if not force and self._conversation_has_pending_response_epoch(key):
            self._schedule_sylanne_memory_idle_commit(
                key,
                int(self._sylanne_memory_idle_generation.get(key) or 0),
            )
            return
        if not force and key in self._realtime_input_fragment_window_cache():
            self._schedule_sylanne_memory_idle_commit(
                key,
                int(self._sylanne_memory_idle_generation.get(key) or 0),
            )
            return
        current_task = None
        try:
            current_task = asyncio.current_task()
        except RuntimeError:
            current_task = None
        task = self._sylanne_memory_idle_tasks.pop(key, None)
        if force and task is not None and task is not current_task and not task.done():
            task.cancel()
        pending = list(self._sylanne_memory_pending_observations.pop(key, deque()))
        if not pending:
            self._sylanne_memory_idle_generation.pop(key, None)
            return
        await self._commit_sylanne_memory_observations_batch(
            key,
            self._coalesce_sylanne_memory_observations(pending),
        )
        self._sylanne_memory_idle_generation.pop(key, None)

    def _coalesce_sylanne_memory_observations(
        self,
        observations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        ordered = sorted(
            [dict(item) for item in observations if isinstance(item, dict)],
            key=lambda item: self._as_float_value(item.get("observed_at"), 0.0),
        )
        merged: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for item in ordered:
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            speaker = str(item.get("speaker_id") or "")
            can_merge = bool(
                current is not None
                and speaker
                and speaker == str(current.get("speaker_id") or "")
                and speaker != "assistant"
            )
            if can_merge:
                current["text"] = self._merge_sylanne_memory_observation_texts(
                    str(current.get("text") or ""),
                    text,
                )
                current["observed_at"] = item.get("observed_at")
                current["event_time"] = item.get("event_time")
                for key in (
                    "emotion_snapshot",
                    "personality_drift_snapshot",
                    "lifelike_snapshot",
                    "group_atmosphere_snapshot",
                ):
                    if item.get(key) is not None:
                        current[key] = item.get(key)
                continue
            if current is not None:
                merged.append(current)
            current = item
        if current is not None:
            merged.append(current)
        return merged

    def _merge_sylanne_memory_observation_texts(self, previous: str, current: str) -> str:
        first = " ".join(str(previous or "").split()).strip()
        second = " ".join(str(current or "").split()).strip()
        if not first:
            return second
        if not second or second in first:
            return first
        if first in second:
            return second
        return f"{first} {second}".strip()

    async def _commit_sylanne_memory_observation(
        self,
        session_key: str,
        observation: dict[str, Any],
    ) -> None:
        await self._commit_sylanne_memory_observations_batch(
            session_key,
            [observation],
        )

    async def _commit_sylanne_memory_observations_batch(
        self,
        session_key: str,
        observations: list[dict[str, Any]],
    ) -> None:
        cleaned = [dict(item) for item in observations if isinstance(item, dict)]
        if not cleaned:
            return
        latest_now = self._observed_now()
        for observation in cleaned:
            latest_now = max(
                latest_now,
                self._as_float_value(observation.get("observed_at"), latest_now),
            )
        changed = False
        state: SylanneMemoryState | None = None
        try:
            state = await self._load_sylanne_memory_state(
                session_key,
                now=latest_now,
                save_decay=False,
            )
            for observation in cleaned:
                text = str(observation.get("text") or "").strip()
                if not text:
                    continue
                now = self._as_float_value(
                    observation.get("observed_at"),
                    latest_now,
                )
                state = observe_memory_event(
                    state,
                    text=text,
                    session_key=session_key,
                    speaker_id=str(observation.get("speaker_id") or ""),
                    emotion_snapshot=observation.get("emotion_snapshot"),
                    personality_drift_snapshot=observation.get("personality_drift_snapshot"),
                    lifelike_snapshot=observation.get("lifelike_snapshot"),
                    group_atmosphere_snapshot=observation.get("group_atmosphere_snapshot"),
                    now=now,
                    event_time=observation.get("event_time"),
                )
                changed = True
            if not changed:
                return
            if self._sylanne_memory_record_embedding_budget_available(
                session_key,
                now=latest_now,
            ):
                self._mark_sylanne_memory_record_embedding_attempt(
                    session_key,
                    now=latest_now,
                )
                provider, provider_id = await self._sylanne_memory_embedding_provider()
                if provider is not None and provider_id:
                    await self._ensure_sylanne_memory_record_embeddings(
                        state,
                        provider=provider,
                        provider_id=provider_id,
                        now=latest_now,
                        max_records=min(
                            self._sylanne_memory_record_embedding_max_per_flush(),
                            len(cleaned),
                        ),
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
            "Detailed state remains internal; rely on this compact state unless the Agent supplies more.\n"
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
                "Detailed state remains internal; rely on the existing compact state unless the Agent supplies more.\n"
                "</bot_emotion_state>"
            )
        return (
            '<bot_emotion_state private="true" detail="diff">\n'
            "Use only these material changes since the last injected compact snapshot.\n"
            f"label={current['label']}; label_changed={label_changed}; "
            f"relationship_decision={current['relationship_decision']}; "
            f"relationship_decision_changed={decision_changed}; "
            f"changed_values={json.dumps(changed, ensure_ascii=False)}.\n"
            "Detailed state remains internal; rely on these material changes unless the Agent supplies more.\n"
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
                "Detailed room state remains internal; rely on the existing compact state unless the Agent supplies more.\n"
                "</bot_group_atmosphere>"
            )
        return (
            '<bot_group_atmosphere private="true" detail="diff">\n'
            "Use these material room-mood changes to decide whether joining is timely.\n"
            f"mode={current['mode']}; mode_changed={mode_changed}; "
            f"cooldown_active={current['cooldown_active']}; "
            f"cooldown_remaining_turns={current['cooldown_remaining_turns']}; "
            f"changed_values={json.dumps(changed, ensure_ascii=False)}.\n"
            "Detailed room state remains internal; rely on these material changes unless the Agent supplies more.\n"
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
        return (
            f'<bot_auxiliary_state private="true" name="{state_name}" detail="compact">\n'
            f"{state_name} is enabled. Detailed state-tool access is internal; rely on compact state unless the Agent supplies more.\n"
            "</bot_auxiliary_state>"
        )

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

    def _event_observed_at(self, event: AstrMessageEvent | None) -> float:
        if self._cfg_bool("benchmark_enable_simulated_time", False):
            return self._observed_now()
        event_time = self._extract_event_timestamp(event)
        return event_time if event_time is not None else self._observed_now()

    def _extract_event_timestamp(self, event: Any) -> float | None:
        if event is None:
            return None
        candidates: list[Any] = []
        for method_name in (
            "get_timestamp",
            "get_time",
            "get_message_time",
            "get_event_time",
        ):
            method = getattr(event, method_name, None)
            if callable(method):
                try:
                    candidates.append(method())
                except Exception:
                    pass
        direct_names = (
            "timestamp",
            "time",
            "message_time",
            "event_time",
            "created_at",
            "send_time",
            "message_timestamp",
        )
        if isinstance(event, dict):
            for name in direct_names:
                candidates.append(event.get(name))
            for name in (
                "event",
                "message_event",
                "astr_message_event",
                "source_event",
                "message_obj",
                "raw_message",
                "raw_event",
                "message",
            ):
                nested = event.get(name)
                if isinstance(nested, dict):
                    for timestamp_name in direct_names:
                        candidates.append(nested.get(timestamp_name))
                    sender = nested.get("sender")
                    if isinstance(sender, dict):
                        for timestamp_name in direct_names:
                            candidates.append(sender.get(timestamp_name))
                elif nested is not None:
                    for timestamp_name in direct_names:
                        candidates.append(getattr(nested, timestamp_name, None))
        for name in direct_names:
            candidates.append(getattr(event, name, None))
        nested_roots = (
            getattr(event, "message_obj", None),
            getattr(event, "message", None),
            getattr(event, "raw_message", None),
            getattr(event, "raw_event", None),
        )
        for root in nested_roots:
            if root is None:
                continue
            if isinstance(root, dict):
                for name in direct_names:
                    candidates.append(root.get(name))
                sender = root.get("sender")
                if isinstance(sender, dict):
                    for name in direct_names:
                        candidates.append(sender.get(name))
                continue
            for name in direct_names:
                candidates.append(getattr(root, name, None))
        for value in candidates:
            coerced = self._coerce_event_timestamp(value)
            if coerced is not None:
                return coerced
        return None

    def _coerce_event_timestamp(self, value: Any) -> float | None:
        if value is None or value == "":
            return None
        if isinstance(value, dt.datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=dt.timezone.utc)
            return value.timestamp()
        if isinstance(value, dt.date):
            return dt.datetime.combine(
                value,
                dt.time(),
                tzinfo=dt.timezone.utc,
            ).timestamp()
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                numeric = float(text)
            except ValueError:
                try:
                    parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
                except ValueError:
                    return None
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=dt.timezone.utc)
                return parsed.timestamp()
        else:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                return None
        if not numeric or numeric < 0:
            return None
        timestamp = float(numeric)
        if timestamp > 10_000_000_000_000_000:
            timestamp /= 1_000_000_000.0
        elif timestamp > 10_000_000_000_000:
            timestamp /= 1_000_000.0
        elif timestamp > 10_000_000_000:
            timestamp /= 1_000.0
        if timestamp < 946684800.0 or timestamp > 32503680000.0:
            return None
        return timestamp

    def _astrbot_timezone_name(self, event: Any | None = None) -> str:
        candidates: list[Any] = []
        for cfg in self._context_config_candidates(event):
            found = self._find_timezone_name(cfg)
            if found:
                candidates.append(found)
        candidates.extend(
            [
                os.environ.get("TZ", ""),
                "Asia/Shanghai",
            ],
        )
        for value in candidates:
            name = str(value or "").strip()
            if name:
                return name
        return "Asia/Shanghai"

    def _context_config_candidates(self, event: Any | None = None) -> list[Any]:
        candidates: list[Any] = []
        context = getattr(self, "context", None)
        if context is None:
            return candidates
        getter = getattr(context, "get_config", None)
        umo = getattr(event, "unified_msg_origin", None)
        if callable(getter):
            for args, kwargs in (
                ((), {"umo": umo}),
                ((umo,), {}),
                ((), {}),
            ):
                try:
                    candidates.append(getter(*args, **kwargs))
                except TypeError:
                    continue
                except Exception:
                    continue
        for name in ("config", "settings", "astrbot_config"):
            value = getattr(context, name, None)
            if value is not None:
                candidates.append(value)
        return candidates

    def _find_timezone_name(self, value: Any, *, depth: int = 0) -> str:
        if value is None or depth > 4:
            return ""
        keys = ("timezone", "time_zone", "timeZone", "tz", "time-zone")
        if hasattr(value, "get"):
            for key in keys:
                try:
                    found = value.get(key)
                except Exception:
                    found = None
                if found:
                    return str(found).strip()
            try:
                items = list(value.values())
            except Exception:
                items = []
            for item in items:
                found = self._find_timezone_name(item, depth=depth + 1)
                if found:
                    return found
        else:
            for key in keys:
                found = getattr(value, key, None)
                if found:
                    return str(found).strip()
        return ""

    def _timezone_for_name(self, timezone_name: str) -> dt.tzinfo:
        name = str(timezone_name or "").strip()
        if ZoneInfo is not None and name:
            try:
                return ZoneInfo(name)
            except Exception:
                pass
        fixed_offsets = {
            "Asia/Shanghai": 8,
            "Asia/Chongqing": 8,
            "Asia/Harbin": 8,
            "Asia/Urumqi": 6,
            "UTC": 0,
            "Etc/UTC": 0,
        }
        if name in fixed_offsets:
            return dt.timezone(
                dt.timedelta(hours=fixed_offsets[name]),
                name=name,
            )
        match = re.fullmatch(r"UTC([+-])(\d{1,2})(?::?(\d{2}))?", name, re.I)
        if match:
            sign = 1 if match.group(1) == "+" else -1
            hours = int(match.group(2))
            minutes = int(match.group(3) or 0)
            return dt.timezone(
                sign * dt.timedelta(hours=hours, minutes=minutes),
                name=name,
            )
        try:
            return dt.datetime.now().astimezone().tzinfo or dt.timezone.utc
        except Exception:
            return dt.timezone.utc

    def _conversation_time_payload(
        self,
        observed_at: float | None = None,
        *,
        event: Any | None = None,
    ) -> dict[str, Any]:
        timestamp = self._observed_now() if observed_at is None else float(observed_at)
        timezone_name = self._astrbot_timezone_name(event)
        tzinfo = self._timezone_for_name(timezone_name)
        local = dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc).astimezone(
            tzinfo,
        )
        offset = local.strftime("%z")
        if len(offset) == 5:
            offset = offset[:3] + ":" + offset[3:]
        local_text = local.strftime("%Y-%m-%d %H:%M:%S")
        return {
            "epoch": round(timestamp, 6),
            "timezone": timezone_name,
            "local_time": f"{local_text} {offset}".strip(),
            "iso": local.isoformat(timespec="seconds"),
            "weekday": local.strftime("%A"),
        }

    def _normalize_conversation_time_payload(
        self,
        event_time: Any = None,
        *,
        observed_at: float | None = None,
        event: Any | None = None,
    ) -> dict[str, Any]:
        if isinstance(event_time, dict):
            local_time = str(
                event_time.get("local_time")
                or event_time.get("event_local_time")
                or event_time.get("trigger_event_local_time")
                or "",
            ).strip()
            timezone_name = str(
                event_time.get("timezone")
                or event_time.get("event_timezone")
                or event_time.get("trigger_timezone")
                or "",
            ).strip()
            epoch = event_time.get("epoch")
            if epoch is None:
                epoch = event_time.get("event_epoch")
            if epoch is None:
                epoch = event_time.get("trigger_event_epoch")
            if local_time and timezone_name:
                payload = {
                    "epoch": epoch,
                    "timezone": timezone_name,
                    "local_time": local_time,
                    "iso": str(event_time.get("iso") or ""),
                    "weekday": str(event_time.get("weekday") or ""),
                }
                return {key: value for key, value in payload.items() if value not in (None, "")}
            coerced = self._coerce_event_timestamp(epoch)
            if coerced is not None:
                return self._conversation_time_payload(coerced, event=event)
        if observed_at is not None:
            return self._conversation_time_payload(observed_at, event=event)
        return {}

    def _event_time_field_line(
        self,
        event_time: Any,
        *,
        local_key: str = "event_local_time",
        timezone_key: str = "timezone",
        epoch_key: str = "event_epoch",
    ) -> str:
        payload = self._normalize_conversation_time_payload(event_time)
        if not payload:
            return ""
        fields: list[str] = []
        local_time = str(payload.get("local_time") or "").strip()
        timezone_name = str(payload.get("timezone") or "").strip()
        epoch = payload.get("epoch")
        if local_time:
            fields.append(f"{local_key}={local_time}")
        if timezone_name:
            fields.append(f"{timezone_key}={timezone_name}")
        if epoch not in (None, ""):
            fields.append(f"{epoch_key}={epoch}")
        return "; ".join(fields)

    def _append_current_event_time_context_if_any(
        self,
        request: ProviderRequest,
        event: AstrMessageEvent | None,
        *,
        session_key: str,
        observed_at: float,
        budget: _StateInjectionBudget | None,
    ) -> bool:
        payload = self._conversation_time_payload(observed_at, event=event)
        text = "\n".join(
            [
                "[sylanne_current_event_time]",
                "Use this AstrBot event time as the authoritative timestamp for the current user message.",
                "When judging recency, sleep/wake wording, 昨天/刚才/上次聊天, prefer the current AstrBot context and this event time over memory relative_time.",
                "event_local_time={local}; timezone={tz}; epoch={epoch}; session={session}".format(
                    local=payload["local_time"],
                    tz=payload["timezone"],
                    epoch=payload["epoch"],
                    session=self._head_one_line(str(session_key or "global"), 80),
                ),
            ],
        )
        return self._append_temp_text_part(
            request,
            text,
            source="current_event_time",
            budget=budget,
        )

    def _append_current_user_media_context_if_any(
        self,
        request: ProviderRequest,
        event: AstrMessageEvent | None,
        *,
        budget: _StateInjectionBudget | None,
    ) -> bool:
        text = self._current_user_media_context_text(event)
        if not text:
            return False
        return self._append_temp_text_part(
            request,
            text,
            source="current_user_media_context",
            budget=budget,
            required=True,
        )

    def _current_user_media_observation_text(
        self,
        event: AstrMessageEvent | None,
    ) -> str:
        observations = self._extract_sticker_observations_from_event(event) if event is not None else []
        if not observations:
            return ""
        labels: list[str] = []
        for observation in observations[:3]:
            kind = "表情包" if observation.get("media_kind") == "sticker" else "图片"
            summary = self._sticker_observation_summary(observation)
            labels.append(f"{kind}：{summary}" if summary else kind)
        return "用户发送了" + "、".join(labels)

    def _current_user_media_context_text(
        self,
        event: AstrMessageEvent | None,
    ) -> str:
        observations = self._extract_sticker_observations_from_event(event) if event is not None else []
        if not observations:
            return ""
        lines = [
            "[sylanne_current_user_media]",
            "当前用户消息包含图片或表情包。把它当作本轮用户输入的一部分；如果主模型没有可靠视觉输入或平台摘要很粗略，不要凭空描述画面内容。",
        ]
        for index, observation in enumerate(observations[:4], start=1):
            kind = "表情包" if observation.get("media_kind") == "sticker" else "图片"
            summary = self._sticker_observation_summary(observation)
            type_text = self._head_one_line(str(observation.get("type") or ""), 32)
            fields = [
                f"kind={kind}",
                f"platform_type={type_text or 'unknown'}",
            ]
            if summary:
                fields.append(f"summary={self._head_one_line(summary, 80)}")
            if observation.get("url"):
                fields.append("has_url=true")
            if observation.get("path"):
                fields.append(f"path={self._head_one_line(str(observation.get('path')), 96)}")
            if observation.get("file_id"):
                fields.append(f"file_id={self._head_one_line(str(observation.get('file_id')), 64)}")
            lines.append(f"- item{index}: " + "; ".join(fields))
        lines.append("回应策略：可以承认收到了表情包/图片；只有在摘要明确时才引用摘要，不要把文件名、旧记忆或猜测当成真实画面。")
        return "\n".join(lines)

    def _sticker_observation_summary(self, observation: dict[str, Any]) -> str:
        for key in ("summary", "name", "filename", "file_id"):
            value = str(observation.get(key) or "").strip()
            if value:
                return value
        path = str(observation.get("path") or "").strip()
        if path:
            try:
                return Path(path).name
            except OSError:
                return path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        url = str(observation.get("url") or "").strip()
        if url:
            return url.rstrip("/").rsplit("/", 1)[-1]
        return ""

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

    async def _request_model_hint_for_event(
        self,
        event: AstrMessageEvent,
        request: ProviderRequest,
    ) -> str:
        chat_provider_hint = ""
        if callable(
            getattr(getattr(self, "context", None), "get_current_chat_provider_id", None),
        ):
            chat_provider_hint = str(
                await self._chat_provider_id(event, use_cache=False) or "",
            ).strip()
        return self._request_model_hint_text(request, provider_id=chat_provider_hint)

    def _request_has_tool_context(self, request: ProviderRequest | None) -> bool:
        if request is None:
            return False
        for field in ("tools", "functions"):
            if self._response_field_has_payload(getattr(request, field, None)):
                return True
        tool_choice = getattr(request, "tool_choice", None)
        if isinstance(tool_choice, str):
            if tool_choice.strip().lower() not in {"", "none", "null", "false"}:
                return True
        elif self._response_field_has_payload(tool_choice):
            return True
        for field in ("metadata", "params", "provider_settings"):
            value = getattr(request, field, None)
            if not isinstance(value, dict):
                continue
            if self._response_field_has_payload(value.get("tools")):
                return True
            if self._response_field_has_payload(value.get("functions")):
                return True
            nested_choice = value.get("tool_choice")
            if isinstance(nested_choice, str):
                if nested_choice.strip().lower() not in {"", "none", "null", "false"}:
                    return True
            elif self._response_field_has_payload(nested_choice):
                return True
        for field in ("contexts", "messages"):
            if self._value_contains_tool_context(getattr(request, field, None)):
                return True
        return False

    def _prune_hidden_sylanne_llm_tools_if_needed(
        self,
        request: ProviderRequest | None,
        budget: _StateInjectionBudget | None,
        *,
        model_hint: str = "",
    ) -> int:
        if request is None:
            return 0
        visible_names = self._visible_sylanne_llm_tool_names_for_request(
            model_hint=model_hint,
        )
        removed: list[str] = []
        for field in ("tools", "functions"):
            value = getattr(request, field, None)
            pruned, names = self._pruned_sylanne_tool_items(
                value,
                visible_names=visible_names,
            )
            if names:
                try:
                    setattr(request, field, pruned)
                except Exception:
                    continue
                removed.extend(names)
        for field in ("metadata", "params", "provider_settings"):
            value = getattr(request, field, None)
            if not isinstance(value, dict):
                continue
            for key in ("tools", "functions"):
                pruned, names = self._pruned_sylanne_tool_items(
                    value.get(key),
                    visible_names=visible_names,
                )
                if names:
                    value[key] = pruned
                    removed.extend(names)
            for key in ("tool_choice", "function_call"):
                if self._tool_choice_references_sylanne_tool(
                    value.get(key),
                    visible_names=visible_names,
                ):
                    value[key] = (
                        "auto" if self._request_has_tool_definitions(request) else "none"
                    )
        for field in ("tool_choice", "function_call"):
            if self._tool_choice_references_sylanne_tool(
                getattr(request, field, None),
                visible_names=visible_names,
            ):
                try:
                    setattr(
                        request,
                        field,
                        "auto" if self._request_has_tool_definitions(request) else "none",
                    )
                except Exception:
                    pass
        if not removed:
            return 0
        unique_removed = sorted({name for name in removed if name})
        if budget is not None:
            budget.skipped.append(
                {
                    "source": "sylanne_llm_tools",
                    "chars": 0,
                    "reason": "hidden_detail_tool_schema_pruned",
                    "removed_count": len(removed),
                    "tools": unique_removed,
                },
            )
        self._log_info(
            f"{PLUGIN_NAME}: 已隐藏 Sylanne 细分 LLM 工具 schema "
            f"removed={len(removed)} tools={','.join(unique_removed[:6])}",
        )
        return len(removed)

    def _visible_sylanne_llm_tool_names_for_request(
        self,
        *,
        model_hint: str = "",
    ) -> frozenset[str]:
        del model_hint
        return VISIBLE_SYLANNE_LLM_TOOL_NAMES

    def _pruned_sylanne_tool_items(
        self,
        value: Any,
        *,
        visible_names: frozenset[str] = VISIBLE_SYLANNE_LLM_TOOL_NAMES,
    ) -> tuple[Any, list[str]]:
        if not isinstance(value, (list, tuple)):
            return value, []
        kept: list[Any] = []
        removed: list[str] = []
        for item in value:
            name = self._request_tool_name(item)
            if name in SYLANNE_LLM_TOOL_NAMES and name not in visible_names:
                removed.append(name)
                continue
            if isinstance(item, dict):
                pruned_item = dict(item)
                item_removed: list[str] = []
                for key in ("function_declarations", "functionDeclarations"):
                    nested = item.get(key)
                    if not isinstance(nested, (list, tuple)):
                        continue
                    pruned_nested, nested_removed = self._pruned_sylanne_tool_items(
                        nested,
                        visible_names=visible_names,
                    )
                    if nested_removed:
                        pruned_item[key] = pruned_nested
                        item_removed.extend(nested_removed)
                if item_removed:
                    removed.extend(item_removed)
                    if not any(
                        self._response_field_has_payload(pruned_item.get(key))
                        for key in ("function_declarations", "functionDeclarations")
                    ):
                        continue
                    kept.append(pruned_item)
                    continue
            kept.append(item)
        if isinstance(value, tuple):
            return tuple(kept), removed
        return kept, removed

    def _request_has_tool_definitions(self, request: ProviderRequest | None) -> bool:
        if request is None:
            return False
        for field in ("tools", "functions"):
            if self._response_field_has_payload(getattr(request, field, None)):
                return True
        for field in ("metadata", "params", "provider_settings"):
            value = getattr(request, field, None)
            if not isinstance(value, dict):
                continue
            if self._response_field_has_payload(value.get("tools")):
                return True
            if self._response_field_has_payload(value.get("functions")):
                return True
        return False

    def _tool_choice_references_sylanne_tool(
        self,
        value: Any,
        *,
        visible_names: frozenset[str] = VISIBLE_SYLANNE_LLM_TOOL_NAMES,
    ) -> bool:
        if value is None or value is False:
            return False
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"", "auto", "none", "null", "false"}:
                return False
            name = value.strip()
            return name in SYLANNE_LLM_TOOL_NAMES and name not in visible_names
        name = self._request_tool_name(value)
        return name in SYLANNE_LLM_TOOL_NAMES and name not in visible_names

    def _request_tool_name(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, dict):
            direct = value.get("name")
            if direct:
                return str(direct)
            function = value.get("function")
            if isinstance(function, dict):
                nested = function.get("name")
                return str(nested or "")
            nested = getattr(function, "name", "")
            return str(nested or "")
        direct = getattr(value, "name", "")
        if direct:
            return str(direct)
        function = getattr(value, "function", None)
        if isinstance(function, dict):
            return str(function.get("name") or "")
        return str(getattr(function, "name", "") or "")

    def _value_contains_tool_context(self, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, dict):
            role = str(value.get("role") or "").strip().lower()
            if role in {"tool", "function"}:
                return True
            for key in (
                "tool_calls",
                "function_call",
                "tools_call_args",
                "tools_call_name",
                "tools_call_id",
                "tool_call_id",
            ):
                if self._response_field_has_payload(value.get(key)):
                    return True
            return any(self._value_contains_tool_context(item) for item in value.values())
        if isinstance(value, (list, tuple, set, frozenset, deque)):
            return any(self._value_contains_tool_context(item) for item in value)
        role = getattr(value, "role", None)
        if str(role or "").strip().lower() in {"tool", "function"}:
            return True
        for key in (
            "tool_calls",
            "function_call",
            "tools_call_args",
            "tools_call_name",
            "tools_call_id",
            "tool_call_id",
        ):
            if self._response_field_has_payload(getattr(value, key, None)):
                return True
        return False

    def _append_temp_text_part(
        self,
        request: ProviderRequest,
        text: str,
        *,
        source: str = "state",
        budget: _StateInjectionBudget | None = None,
        required: bool = False,
    ) -> bool:
        budget_override = self._temp_context_source_allows_budget_override(source)
        if budget is not None and budget.agent_owned_context:
            budget.skipped.append(
                {
                    "source": source,
                    "chars": len(str(text or "")),
                    "reason": "agent_owned_context",
                },
            )
            return False
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
                allow_over_budget=budget_override,
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
            appended_item = {
                "source": source,
                "chars": text_chars,
            }
            if budget_override and budget.request_chars_before >= budget.effective_total_budget:
                appended_item["reason"] = "critical_context_over_budget_override"
            budget.appended.append(
                appended_item,
            )
        return True

    def _temp_context_source_allows_budget_override(self, source: str) -> bool:
        """关键连续性上下文允许在长历史场景下保底注入。"""
        return str(source or "") in {
            "realtime_chat_active_dispatch",
            "realtime_assistant_history_shadow",
            "shadow_memory",
            "realtime_assistant_history_usage_guard",
            "realtime_pending_bot_question",
            "interrupted_reply_breakpoint",
            "active_agent_followup_merge",
            "realtime_input_fragments",
            "user_correction_context",
            "recent_user_correction_context",
            "recent_user_scene_context",
            "user_message_withdrawal",
            "current_user_media_context",
        }

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
            "current_event_time",
            "realtime_chat_active_dispatch",
            "realtime_assistant_history_shadow",
            "shadow_memory",
            "realtime_assistant_history_usage_guard",
            "realtime_pending_bot_question",
            "interrupted_reply_breakpoint",
            "active_agent_followup_merge",
            "realtime_input_fragments",
            "user_correction_context",
            "recent_user_correction_context",
            "recent_user_scene_context",
            "user_message_withdrawal",
            "sylanne_memory_recall",
            "current_user_media_context",
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
            "shadow_memory": "sylanne_shadow_memory",
            "realtime_assistant_history_usage_guard": "sylanne_history_reuse_guard",
            "realtime_pending_bot_question": "sylanne_realtime_pending_bot_question",
            "interrupted_reply_breakpoint": "sylanne_interrupted_reply_breakpoint",
            "active_agent_followup_merge": "sylanne_active_agent_followup_merge",
            "realtime_input_fragments": "sylanne_user_message_fragments",
            "user_message_withdrawal": "sylanne_user_message_withdrawal",
            "user_correction_context": "sylanne_user_correction_context",
            "recent_user_correction_context": "sylanne_recent_user_correction_context",
            "recent_user_scene_context": "sylanne_recent_user_scene_context",
            "sylanne_memory_recall": "sylanne_memory_recall",
            "current_event_time": "sylanne_current_event_time",
            "current_user_media_context": "sylanne_current_user_media",
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
        allow_over_budget: bool = False,
    ) -> str:
        if budget.request_budget_chars <= 0:
            return ""
        if budget.max_added_chars <= 0:
            return "max_added_chars_zero"
        if (
            budget.request_chars_before >= budget.effective_total_budget
            and not allow_over_budget
        ):
            return "request_over_budget"
        if budget.added_parts >= budget.max_parts:
            return "max_parts_reached"
        if text_chars > budget.remaining_added_chars:
            return "max_added_chars_exceeded"
        if text_chars > budget.remaining_total_chars and not allow_over_budget:
            return "request_budget_exceeded"
        if (
            not required
            and not allow_over_budget
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
            "context_owner": (
                "agent" if budget.agent_owned_context else "sylanne_plugin"
            ),
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

    def _append_agent_context_message(
        self,
        request: ProviderRequest,
        *,
        role: str,
        content: str,
    ) -> bool:
        text = str(content or "").strip()
        if not text:
            return False
        contexts = getattr(request, "contexts", None)
        if not isinstance(contexts, list):
            contexts = []
            try:
                setattr(request, "contexts", contexts)
            except Exception:
                return False
        normalized = self._normalize_realtime_history_match_text(text)
        for item in self._tail_items(contexts, 10):
            existing = self._normalize_realtime_history_match_text(
                self._context_item_to_text(item),
            )
            if normalized and normalized in existing:
                return False
        contexts.append({"role": str(role or "assistant"), "content": text})
        return True

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
            await self._kv_put_data(self._agent_trail_kv_key(session_key), list(trail))
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

    def _realtime_delivery_context_kv_key(self, session_key: str) -> str:
        return "realtime_delivery_context:" + self._safe_session_key(session_key)

    def _realtime_chat_enabled(self) -> bool:
        return self._cfg_bool("enable_realtime_chat", False)

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
            max_fragments=8,
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
        return self._cfg_bool("enable_sticker_reaction", False)

    def _sticker_learning_enabled(self) -> bool:
        return self._cfg_bool("sticker_learn_user_images", False)

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
            auto_download_enabled=self._cfg_bool("sticker_auto_download_enabled", False),
            auto_download_repo_url=str(
                self._cfg(
                    "sticker_auto_download_repo_url",
                    "https://github.com/zhaoolee/ChineseBQB.git",
                )
                or ""
            ),
            auto_download_cache_dir=str(
                self._cfg("sticker_auto_download_cache_dir", "") or "",
            ),
            auto_download_timeout_seconds=max(
                1.0,
                min(300.0, self._cfg_float("sticker_auto_download_timeout_seconds", 30.0)),
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
            auto_download_enabled=self._cfg_bool("sticker_auto_download_enabled", False),
            auto_download_repo_url=str(
                self._cfg(
                    "sticker_auto_download_repo_url",
                    "https://github.com/zhaoolee/ChineseBQB.git",
                )
                or ""
            ),
            auto_download_cache_dir=str(
                self._cfg("sticker_auto_download_cache_dir", "") or "",
            ),
            auto_download_timeout_seconds=max(
                1.0,
                min(300.0, self._cfg_float("sticker_auto_download_timeout_seconds", 30.0)),
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
            auto_download_enabled=base.auto_download_enabled,
            auto_download_repo_url=base.auto_download_repo_url,
            auto_download_cache_dir=base.auto_download_cache_dir,
            auto_download_timeout_seconds=base.auto_download_timeout_seconds,
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
        candidates = self._sendable_sticker_candidates(
            await self._local_sticker_index(settings),
        )
        if settings.learned_enabled:
            candidates.extend(
                self._sendable_sticker_candidates(
                    await self._load_sticker_memory(session_key),
                ),
            )
        if not candidates:
            auto_root = await asyncio.to_thread(
                self._ensure_auto_downloaded_sticker_root,
                settings,
            )
            if auto_root is not None:
                auto_settings = StickerSettings(
                    enabled=settings.enabled,
                    local_root=str(auto_root),
                    default_repo_url=settings.default_repo_url,
                    auto_download_enabled=settings.auto_download_enabled,
                    auto_download_repo_url=settings.auto_download_repo_url,
                    auto_download_cache_dir=settings.auto_download_cache_dir,
                    auto_download_timeout_seconds=settings.auto_download_timeout_seconds,
                    allowed_extensions=settings.allowed_extensions,
                    selected_packs=settings.selected_packs,
                    index_limit=settings.index_limit,
                    max_file_bytes=settings.max_file_bytes,
                    send_probability=settings.send_probability,
                    learned_enabled=settings.learned_enabled,
                )
                candidates = self._sendable_sticker_candidates(
                    await self._local_sticker_index(auto_settings),
                )
        return candidates

    def _sendable_sticker_candidates(
        self,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        sendable: list[dict[str, Any]] = []
        seen: set[str] = set()
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            normalized = self._normalize_sendable_sticker_candidate(candidate)
            if normalized is None:
                continue
            identity = str(
                normalized.get("url")
                or normalized.get("path")
                or normalized.get("id")
                or normalized.get("relative_path")
                or "",
            )
            if identity and identity in seen:
                continue
            if identity:
                seen.add(identity)
            sendable.append(normalized)
        return sendable

    def _normalize_sendable_sticker_candidate(
        self,
        candidate: dict[str, Any],
    ) -> dict[str, Any] | None:
        normalized = dict(candidate)
        url = str(normalized.get("url") or "").strip()
        path = str(normalized.get("path") or "").strip()
        if not url and path.lower().startswith(("http://", "https://")):
            url = path
            path = ""
            normalized["url"] = url
            normalized["path"] = ""
        if url.lower().startswith(("http://", "https://")):
            return normalized
        if path:
            try:
                if Path(path).expanduser().exists():
                    return normalized
            except OSError:
                return None
        return None

    def _ensure_auto_downloaded_sticker_root(self, settings: StickerSettings) -> Path | None:
        if not settings.enabled or not settings.auto_download_enabled:
            return None
        if str(settings.local_root or "").strip():
            return None
        repo_url = str(settings.auto_download_repo_url or settings.default_repo_url or "").strip()
        if not self._sticker_auto_download_repo_allowed(repo_url):
            self._log_warning(f"{PLUGIN_NAME}: 表情包自动下载跳过，不支持的仓库地址: {self._clip_one_line(repo_url, 120)}")
            return None
        cache_root = self._sticker_auto_download_cache_root(settings)
        if cache_root is None:
            return None
        target = cache_root / self._sticker_auto_download_repo_slug(repo_url)
        if self._sticker_auto_download_repo_is_completed(target):
            return target
        if self._sticker_auto_download_root_has_images(target, settings):
            return target
        lock_path = target.with_suffix(".lock")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with lock_path.open("x", encoding="utf-8") as lock_file:
                lock_file.write(str(time.time()))
        except FileExistsError:
            if self._sticker_auto_download_repo_is_completed(target):
                return target
            if self._sticker_auto_download_root_has_images(target, settings):
                return target
            self._log_warning(f"{PLUGIN_NAME}: 表情包自动下载已有进行中的锁，暂时跳过")
            return None
        except OSError as exc:
            self._log_warning(f"{PLUGIN_NAME}: 表情包自动下载无法创建缓存目录: {exc}")
            return None
        try:
            self._download_sticker_repo(repo_url, target, settings)
        except Exception as exc:
            self._log_warning(f"{PLUGIN_NAME}: 表情包自动下载失败: {self._clip_one_line(str(exc), 160)}")
            if target.exists() and not self._sticker_auto_download_root_has_images(target, settings):
                shutil.rmtree(target, ignore_errors=True)
            return None
        finally:
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                pass
        return target if self._sticker_auto_download_root_has_images(target, settings) else None

    def _sticker_auto_download_repo_allowed(self, repo_url: str) -> bool:
        lowered = str(repo_url or "").strip().lower()
        return lowered.startswith(("https://", "http://", "git://")) and not any(
            marker in lowered
            for marker in (";", "&&", "||", "`", "$(", "\n", "\r")
        )

    def _sticker_auto_download_cache_root(self, settings: StickerSettings) -> Path | None:
        configured = str(settings.auto_download_cache_dir or "").strip()
        if configured:
            root = Path(configured).expanduser()
        else:
            test_base = getattr(self, "_test_sticker_cache_base", None)
            if test_base:
                root = Path(test_base)
            else:
                root = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
                root = root / PLUGIN_NAME / "stickers"
        try:
            resolved = root.resolve()
        except OSError:
            return None
        if self._sticker_auto_download_cache_dir_is_unsafe(resolved):
            self._log_warning(f"{PLUGIN_NAME}: 表情包自动下载缓存目录不安全，已跳过: {resolved}")
            return None
        return resolved

    def _sticker_auto_download_cache_dir_is_unsafe(self, path: Path) -> bool:
        try:
            root = Path(__file__).resolve().parent
            resolved = path.resolve()
        except OSError:
            return True
        unsafe_roots = [
            root,
            root / "docs",
            root / "pages",
            root / "dist",
            root / "output",
        ]
        return any(resolved == item or item in resolved.parents for item in unsafe_roots)

    def _sticker_auto_download_repo_slug(self, repo_url: str) -> str:
        cleaned = re.sub(r"\.git$", "", str(repo_url or "").strip().rstrip("/"))
        tail = cleaned.rsplit("/", 1)[-1] or "stickers"
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", tail).strip("._-")
        digest = sha256(cleaned.encode("utf-8", errors="ignore")).hexdigest()[:10]
        return f"{safe or 'stickers'}-{digest}"

    def _sticker_auto_download_repo_is_completed(self, root: Path) -> bool:
        if not root.exists() or not root.is_dir():
            return False
        return (root / ".git").exists() or (root / ".sylanne_sticker_download_complete").exists()

    def _sticker_auto_download_root_has_images(
        self,
        root: Path,
        settings: StickerSettings,
    ) -> bool:
        if not root.exists() or not root.is_dir():
            return False
        probe_settings = StickerSettings(
            enabled=settings.enabled,
            local_root=str(root),
            default_repo_url=settings.default_repo_url,
            auto_download_enabled=settings.auto_download_enabled,
            auto_download_repo_url=settings.auto_download_repo_url,
            auto_download_cache_dir=settings.auto_download_cache_dir,
            auto_download_timeout_seconds=settings.auto_download_timeout_seconds,
            allowed_extensions=settings.allowed_extensions,
            selected_packs=settings.selected_packs,
            index_limit=1,
            max_file_bytes=settings.max_file_bytes,
            send_probability=settings.send_probability,
            learned_enabled=settings.learned_enabled,
        )
        return bool(index_local_stickers(probe_settings))

    def _download_sticker_repo(
        self,
        repo_url: str,
        target: Path,
        settings: StickerSettings,
    ) -> None:
        git = shutil.which("git")
        if not git:
            raise RuntimeError("git executable not found")
        tmp_target = target.with_name(target.name + ".tmp")
        if tmp_target.exists():
            shutil.rmtree(tmp_target, ignore_errors=True)
        command = [
            git,
            "clone",
            "--depth",
            "1",
            "--filter=blob:none",
            "--",
            repo_url,
            str(tmp_target),
        ]
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=max(1.0, float(settings.auto_download_timeout_seconds)),
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "git clone failed")[:240])
        (tmp_target / ".sylanne_sticker_download_complete").write_text(
            "ok\n",
            encoding="utf-8",
        )
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        tmp_target.replace(target)

    def _sticker_index_root_signature(self, settings: StickerSettings) -> tuple[Any, ...]:
        root_text = str(settings.local_root or "").strip()
        if not root_text:
            return ("empty",)
        try:
            root = Path(root_text).expanduser()
            stat = root.stat()
        except OSError:
            return ("missing", root_text)
        if not root.is_dir():
            return ("not_dir", root_text, getattr(stat, "st_mtime_ns", 0), stat.st_size)
        try:
            resolved = str(root.resolve())
        except OSError:
            resolved = str(root)
        return ("dir", resolved, getattr(stat, "st_mtime_ns", 0), stat.st_size)

    async def _local_sticker_index(self, settings: StickerSettings) -> list[dict[str, Any]]:
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
        root_signature = self._sticker_index_root_signature(settings)
        cached = cache.get(cache_key)
        if (
            cached
            and (ttl <= 0 or now - float(cached.get("indexed_at", 0.0)) <= ttl)
            and tuple(cached.get("root_signature") or ()) == root_signature
        ):
            return list(cached.get("items") or [])
        items = await asyncio.to_thread(index_local_stickers, settings)
        cache[cache_key] = {
            "indexed_at": now,
            "items": items,
            "root_signature": root_signature,
        }
        return list(items)

    async def _load_sticker_memory(self, session_key: str) -> list[dict[str, Any]]:
        cache = getattr(self, "_sticker_memory_cache", None)
        if cache is None:
            cache = {}
            self._sticker_memory_cache = cache
        if session_key in cache:
            return [dict(item) for item in cache[session_key]]
        try:
            data = await self._kv_get_data(self._sticker_memory_kv_key(session_key), [])
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
            await self._kv_put_data(self._sticker_memory_kv_key(session_key), items)
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: sticker memory KV write failed: {exc}")

    async def _observe_stickers_background(
        self,
        event: AstrMessageEvent,
        stickers: list[dict[str, Any]],
        *,
        session_key: str,
    ) -> None:
        if not self._sticker_learning_enabled():
            return
        resolved_session = self._resolve_public_session_key(
            event,
            session_key=session_key,
        )
        current = await self._load_sticker_memory(resolved_session)
        updated = current
        changed = False
        for sticker in stickers[:5]:
            item = build_sticker_memory_item(
                dict(sticker or {}),
                session_key=resolved_session,
                now=self._observed_now(),
                source="astrbot_event",
            )
            updated = merge_sticker_memory(
                updated,
                item,
                limit=max(1, self._cfg_int("sticker_learned_limit", 200)),
            )
            changed = True
        if changed:
            await self._save_sticker_memory(resolved_session, updated)

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
            self._collect_sticker_observation_candidates(value, candidates)
        observations: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in candidates:
            observation = self._sticker_observation_from_message_part(item)
            if observation:
                identity = str(
                    observation.get("url")
                    or observation.get("path")
                    or observation.get("file_id")
                    or observation.get("name")
                    or "",
                )
                if identity and identity in seen:
                    continue
                if identity:
                    seen.add(identity)
                observations.append(observation)
        return observations[:8]

    def _collect_sticker_observation_candidates(
        self,
        value: Any,
        output: list[Any],
        *,
        depth: int = 0,
    ) -> None:
        if value is None or depth > 4:
            return
        if isinstance(value, (str, bytes)):
            output.append(value.decode("utf-8", errors="ignore") if isinstance(value, bytes) else value)
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                self._collect_sticker_observation_candidates(
                    item,
                    output,
                    depth=depth + 1,
                )
            return
        output.append(value)
        if isinstance(value, dict):
            type_text = str(
                value.get("type")
                or value.get("message_type")
                or (
                    value.get("data", {}).get("type")
                    if isinstance(value.get("data"), dict)
                    else ""
                )
                or (
                    value.get("data", {}).get("message_type")
                    if isinstance(value.get("data"), dict)
                    else ""
                )
                or "",
            ).strip().lower()
            if type_text in {"reply", "quote", "reference"}:
                return
            nested_values = [
                value.get(name)
                for name in (
                    "data",
                    "message",
                    "messages",
                    "message_chain",
                    "raw_message",
                    "chain",
                )
            ]
        else:
            nested_values = [
                getattr(value, name, None)
                for name in (
                    "data",
                    "message",
                    "messages",
                    "message_chain",
                    "raw_message",
                    "chain",
                )
            ]
        for nested in nested_values:
            if nested is value or nested is None:
                continue
            self._collect_sticker_observation_candidates(
                nested,
                output,
                depth=depth + 1,
            )

    def _sticker_observation_from_message_part(self, item: Any) -> dict[str, Any] | None:
        if isinstance(item, str):
            return self._sticker_observation_from_cq_text(item)
        if isinstance(item, dict):
            data = item.get("data") if isinstance(item.get("data"), dict) else {}
            type_text = str(
                item.get("type")
                or item.get("message_type")
                or data.get("type")
                or data.get("message_type")
                or "",
            ).lower()
            if type_text in {"reply", "quote", "reference"}:
                return None
            keys = dict(data)
            keys.update({key: value for key, value in item.items() if key != "data"})
        else:
            data = getattr(item, "data", None)
            data = data if isinstance(data, dict) else {}
            type_text = str(
                getattr(item, "type", "")
                or getattr(item, "message_type", "")
                or data.get("type")
                or data.get("message_type")
                or item.__class__.__name__,
            ).lower()
            if type_text in {"reply", "quote", "reference"}:
                return None
            keys = dict(data)
            keys.update({
                name: getattr(item, name, None)
                for name in (
                    "url",
                    "file",
                    "file_path",
                    "path",
                    "file_id",
                    "emoji_id",
                    "emojiId",
                    "id",
                    "name",
                    "filename",
                    "summary",
                    "sub_type",
                    "subType",
                    "mime",
                    "mime_type",
                )
            })
        url = keys.get("url")
        path = keys.get("path") or keys.get("file") or keys.get("file_path")
        file_id = keys.get("file_id") or keys.get("emoji_id") or keys.get("emojiId") or keys.get("id")
        name = keys.get("name") or keys.get("filename") or keys.get("summary")
        media_kind = self._sticker_observation_media_kind(type_text, keys)
        if media_kind == "unknown":
            if not any((url, path, file_id)):
                return None
            media_kind = "image"
        if not any((url, path, file_id, name)):
            return None
        return {
            "type": type_text or "image",
            "media_kind": media_kind,
            "url": url,
            "path": path,
            "file_id": file_id,
            "name": name,
            "summary": keys.get("summary"),
            "mime": keys.get("mime") or keys.get("mime_type"),
            "interest_score": 0.55,
        }

    def _sticker_observation_media_kind(
        self,
        type_text: str,
        keys: dict[str, Any],
    ) -> str:
        type_text = str(type_text or "").strip().lower()
        if any(marker in type_text for marker in ("mface", "marketface", "sticker", "emoji", "face")):
            return "sticker"
        if "image" in type_text:
            combined = " ".join(
                str(keys.get(name) or "")
                for name in (
                    "summary",
                    "name",
                    "filename",
                    "sub_type",
                    "subType",
                    "emoji_id",
                    "emojiId",
                    "file",
                    "path",
                    "url",
                )
            ).lower()
            if any(
                marker in combined
                for marker in (
                    "表情",
                    "动画表情",
                    "sticker",
                    "emoji",
                    "mface",
                    "marketface",
                    "bface",
                    "face",
                )
            ):
                return "sticker"
            return "image"
        combined = " ".join(
            str(keys.get(name) or "")
            for name in (
                "summary",
                "name",
                "filename",
                "sub_type",
                "subType",
                "emoji_id",
                "emojiId",
            )
        ).lower()
        if any(
            marker in combined
            for marker in (
                "表情",
                "动画表情",
                "sticker",
                "emoji",
                "mface",
                "marketface",
                "bface",
            )
        ):
            return "sticker"
        if any(marker in type_text for marker in ("picture", "photo", "pic")):
            return "image"
        return "unknown"

    def _sticker_observation_from_cq_text(self, text: str) -> dict[str, Any] | None:
        value = str(text or "")
        match = re.search(r"\[CQ:(image|sticker|face|emoji),([^\]]+)\]", value, re.I)
        if not match:
            return None
        attrs: dict[str, str] = {}
        for chunk in match.group(2).split(","):
            if "=" not in chunk:
                continue
            key, raw = chunk.split("=", 1)
            attrs[key.strip()] = raw.strip()
        return self._sticker_observation_from_message_part(
            {
                "type": match.group(1).lower(),
                "data": attrs,
            },
        )

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

    def _log_info(self, message: str) -> None:
        writer = getattr(logger, "info", None) or getattr(logger, "debug", None)
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
