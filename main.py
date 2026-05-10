from __future__ import annotations

import contextvars
import asyncio
import json
import time
import os
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


PLUGIN_NAME = "astrbot_plugin_emotional_state"
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


@dataclass
class _BackgroundPostJob:
    event: AstrMessageEvent
    identity: ConversationIdentity
    response_text: str
    request_context_text: str
    sequence: int
    observed_at: float
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
    "observe_sticker_usage",
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
    "基于 PAD/OCC/appraisal 与情绪动力学的 AstrBot 多维情绪状态插件",
    "1.6.0",
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
        self._agent_identity_profile_cache: dict[str, dict[str, Any]] = {}
        self._agent_trail_cache: dict[str, deque[dict[str, Any]]] = {}
        self._agent_turn_sequence: dict[str, int] = {}
        self._engine_cache: dict[str, EmotionEngine] = {}
        self._provider_id_cache: dict[str, tuple[float, str | None]] = {}
        self._last_request_text: dict[str, str] = {}
        self._last_state_injection_diagnostics: dict[str, dict[str, Any]] = {}
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
        self._realtime_chat_last_sent: dict[str, float] = {}
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
        self._memory_cache.clear()
        self._psychological_memory_cache.clear()
        self._humanlike_memory_cache.clear()
        self._lifelike_learning_memory_cache.clear()
        self._personality_drift_memory_cache.clear()
        self._moral_repair_memory_cache.clear()
        self._fallibility_memory_cache.clear()
        self._group_atmosphere_memory_cache.clear()
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
        await self._observe_agent_identity(identity, now=self._observed_now())
        context_text = self._request_to_text(request)
        self._last_request_text[session_key] = context_text
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
        )
        if not needs_request_state:
            return

        observed_at = self._observed_now()
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
            self._event_text(event) or request.prompt or "",
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
            )
            appended_emotion = self._append_temp_text_part(
                request,
                self._build_state_injection_for_session(
                    session_key,
                    state,
                    safety_boundary=safety_boundary,
                    commit_snapshot=False,
                ),
                source="emotion",
                budget=injection_budget,
                required=True,
            )
            if appended_emotion:
                self._commit_state_injection_snapshot_for_session(session_key, state)
            elif self._state_injection_detail() == "full":
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
                    ),
                    source="humanlike",
                    budget=injection_budget,
                )
                if not appended and self._auxiliary_state_injection_detail() == "full":
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
                    ),
                    source="lifelike_learning",
                    budget=injection_budget,
                )
                if not appended and self._auxiliary_state_injection_detail() == "full":
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
                    ),
                    source="personality_drift",
                    budget=injection_budget,
                )
                if not appended and self._auxiliary_state_injection_detail() == "full":
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
                    ),
                    source="moral_repair",
                    budget=injection_budget,
                )
                if not appended and self._auxiliary_state_injection_detail() == "full":
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
                    ),
                    source="fallibility",
                    budget=injection_budget,
                )
                if not appended and self._auxiliary_state_injection_detail() == "full":
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
                        ),
                    ),
                    source="group_atmosphere",
                    budget=injection_budget,
                )
                if appended:
                    if self._auxiliary_state_injection_detail() == "full":
                        self._commit_group_atmosphere_injection_snapshot_for_session(
                            session_key,
                            group_atmosphere_state,
                        )
                elif self._auxiliary_state_injection_detail() == "full":
                    self._append_temp_text_part(
                        request,
                        self._build_compact_auxiliary_state_injection(
                            "group_atmosphere",
                        ),
                        source="group_atmosphere.compact_fallback",
                        budget=injection_budget,
                    )
            self._record_state_injection_diagnostics(injection_budget)

        if (
            inject_state
            and self._auxiliary_state_injection_detail() != "off"
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
        realtime_dispatch_task: asyncio.Task[Any] | None = None
        if self._should_intercept_realtime_chat_response(event, response_text):
            plan = await self.get_realtime_chat_plan(
                event,
                text=response_text,
                session_key=identity.conversation_id,
            )
            if plan.get("message_parts"):
                try:
                    setattr(response, "completion_text", "")
                except Exception:
                    pass
                realtime_dispatch_task = self._schedule_background_task(
                    self._send_realtime_chat_plan(
                        event,
                        plan,
                        source="llm_response_intercept",
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
        source: str = "livingmemory",
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
        sticker_candidates: list[dict[str, Any]] = []
        if include_sticker and self._sticker_reaction_enabled():
            sticker_candidates = await self._sticker_candidates(resolved_session)
        emotion_values, atmosphere_values = await asyncio.gather(emotion_task, group_task)
        plan = build_realtime_chat_plan(
            text,
            settings=self._realtime_chat_settings(),
            session_key=resolved_session,
            now=self._observed_now(),
            emotion_values=emotion_values,
            atmosphere_values=atmosphere_values,
            sticker_candidates=sticker_candidates,
            sticker_settings=self._sticker_settings(),
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
        message_text = self._compose_proactive_message_text(
            judgement,
            selected_topic=topic,
            override_text=override_text,
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
            "max_chars": max(1, self._cfg_int("proactive_speech_max_chars", 160)),
            "idempotency_key": self._proactive_dispatch_idempotency_key(
                session_key=session_key,
                decision=decision,
                message_text=message_text,
            ),
            "ttl_seconds": max(1, self._cfg_int("proactive_speech_dispatch_ttl_seconds", 120)),
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
    ) -> str:
        max_chars = max(1, self._cfg_int("proactive_speech_max_chars", 160))
        raw = str(override_text or judgement.get("draft_message") or "").strip()
        if not raw:
            need_mode = str(judgement.get("need_mode") or "")
            topic = str(judgement.get("topic_text") or selected_topic.get("topic") or "").strip()
            raw = self._fallback_proactive_message(need_mode, topic)
        return self._clip_one_line(raw, max_chars)

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
        if self._proactive_dispatch_on_cooldown(str(dispatch.get("session_key") or "")):
            return "cooldown_active"
        if not hasattr(getattr(self, "context", None), "send_message"):
            return "missing_send_message_api"
        if decision.get("action") == "stay_silent":
            return "decision_silence"
        return ""

    def _proactive_dispatch_on_cooldown(self, session_key: str) -> bool:
        cooldown = max(
            0.0,
            self._cfg_float("proactive_speech_dispatch_cooldown_seconds", 1800.0),
        )
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
                "blocked_reason": dispatch.get("blocked_reason", ""),
                "need_mode": dispatch.get("need_mode", ""),
                "topic_text": dispatch.get("topic_text", ""),
                "topic_evidence": dispatch.get("topic_evidence", ""),
            },
        )

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
    ) -> dict[str, Any]:
        origin = self._proactive_unified_msg_origin(event_or_session)
        if not origin:
            raise RuntimeError("missing unified_msg_origin")
        send_message = getattr(getattr(self, "context", None), "send_message", None)
        if not callable(send_message):
            raise RuntimeError("context.send_message is not available")
        parts = list(plan.get("message_parts") or [])
        results: list[dict[str, Any]] = []
        for part in parts:
            delay = max(0.0, self._as_float_value(part.get("delay_before_seconds"), 0.0))
            if delay > 0:
                await asyncio.sleep(delay)
            text = str(part.get("text") or "").strip()
            if not text:
                continue
            message = self._build_astrbot_message_chain(text)
            result = await send_message(origin, message)
            results.append(
                {
                    "index": part.get("index"),
                    "text_chars": len(text),
                    "message_type": type(message).__name__,
                    "result": self._bounded_scalar_or_summary(result),
                },
            )
        sticker_result = None
        sticker = plan.get("sticker") if isinstance(plan.get("sticker"), dict) else {}
        if sticker.get("should_send"):
            candidate = sticker.get("candidate")
            if isinstance(candidate, dict):
                sticker_message = self._build_astrbot_sticker_message(candidate)
                sticker_result = await send_message(origin, sticker_message)
        session_key = str(plan.get("session_key") or self._resolve_public_session_key(event_or_session))
        self._realtime_chat_last_sent_cache()[session_key] = self._observed_now()
        return {
            "api": "context.send_message",
            "source": source,
            "unified_msg_origin": origin,
            "message_count": len(results),
            "results": results,
            "sticker_result": self._bounded_scalar_or_summary(sticker_result),
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

    def _build_astrbot_sticker_message(self, candidate: dict[str, Any]) -> Any:
        path = str(candidate.get("path") or "")
        url = str(candidate.get("url") or "")
        fallback = str(candidate.get("name") or candidate.get("relative_path") or "表情包")
        try:
            from astrbot.api.event import MessageChain  # type: ignore

            chain = MessageChain()
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
        if not hasattr(getattr(self, "context", None), "send_message"):
            return False
        session_key = self._session_key(event)
        return not self._realtime_chat_on_cooldown(session_key)

    def _realtime_chat_on_cooldown(self, session_key: str) -> bool:
        cooldown = max(
            0.0,
            self._cfg_float("realtime_chat_session_cooldown_seconds", 0.0),
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
            False,
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
        return self._auxiliary_state_injection_detail() != "off"

    def _humanlike_reset_allowed(self) -> bool:
        return self._cfg_bool("allow_humanlike_reset_backdoor", True)

    def _lifelike_learning_enabled(self) -> bool:
        return True

    def _lifelike_learning_injection_enabled(self) -> bool:
        return self._auxiliary_state_injection_detail() != "off"

    def _lifelike_learning_reset_allowed(self) -> bool:
        return self._cfg_bool("allow_lifelike_learning_reset_backdoor", True)

    def _personality_drift_enabled(self) -> bool:
        return True

    def _personality_drift_injection_enabled(self) -> bool:
        return self._auxiliary_state_injection_detail() != "off"

    def _personality_drift_reset_allowed(self) -> bool:
        return self._cfg_bool("allow_personality_drift_reset_backdoor", True)

    def _moral_repair_modeling_enabled(self) -> bool:
        return self._cfg_bool("enable_moral_repair_state", False)

    def _moral_repair_injection_enabled(self) -> bool:
        return self._auxiliary_state_injection_detail() != "off"

    def _moral_repair_reset_allowed(self) -> bool:
        return self._cfg_bool("allow_moral_repair_reset_backdoor", True)

    def _fallibility_modeling_enabled(self) -> bool:
        return self._cfg_bool("enable_fallibility_state", False)

    def _fallibility_injection_enabled(self) -> bool:
        return self._auxiliary_state_injection_detail() != "off"

    def _fallibility_reset_allowed(self) -> bool:
        return self._cfg_bool("allow_fallibility_reset_backdoor", True)

    def _group_atmosphere_modeling_enabled(self) -> bool:
        return True

    def _group_atmosphere_injection_enabled(self) -> bool:
        return self._auxiliary_state_injection_detail() != "off"

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
    ) -> str:
        resolved_safety_boundary = (
            self._safety_boundary_enabled()
            if safety_boundary is None
            else safety_boundary
        )
        if self._state_injection_detail() == "compact":
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
    ) -> str:
        mode = str(
            self._cfg("state_injection_compact_mode", "snapshot") or "snapshot",
        ).strip().lower()
        if self._state_injection_detail() != "compact" or mode != "diff":
            return self._build_state_injection(
                state,
                safety_boundary=safety_boundary,
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
        return self._build_state_injection(
            state,
            safety_boundary=safety_boundary,
        )

    def _state_injection_detail(self) -> str:
        detail = str(
            self._cfg("state_injection_detail", "compact") or "compact",
        ).strip().lower()
        if detail in {"compact", "full"}:
            return detail
        return "compact"

    def _auxiliary_state_injection_detail(self) -> str:
        detail = str(
            self._cfg("auxiliary_state_injection_detail", "compact") or "compact",
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

    def _build_diff_state_injection(
        self,
        session_key: str,
        state: EmotionState,
        *,
        safety_boundary: bool,
        commit_snapshot: bool = True,
    ) -> str:
        cache = getattr(self, "_state_injection_snapshot_cache", None)
        if cache is None:
            cache = {}
            self._state_injection_snapshot_cache = cache
        current = self._state_injection_snapshot(state)
        previous = cache.get(session_key)
        if commit_snapshot:
            cache[session_key] = current
        threshold = max(0.0, self._cfg_float("state_injection_diff_threshold", 0.08))
        force_every = max(1, self._cfg_int("state_injection_diff_force_every_turns", 6))
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
    ) -> str:
        mode = str(
            self._cfg("state_injection_compact_mode", "snapshot") or "snapshot",
        ).strip().lower()
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
            self._cfg_float("group_atmosphere_injection_diff_threshold", 0.08),
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
    ) -> str:
        detail = self._auxiliary_state_injection_detail()
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
        return _StateInjectionBudget(
            session_key=session_key,
            request_chars_before=self._estimate_provider_request_chars(request),
            request_budget_chars=request_budget_chars,
            reserved_chars=reserved_chars,
            max_added_chars=max_added_chars,
            max_parts=max_parts,
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
        text = str(text)
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
    ) -> None:
        diagnostics = {
            "enabled": True,
            "estimate_only": True,
            "session_key": budget.session_key,
            "request_chars_before": budget.request_chars_before,
            "request_budget_chars": budget.request_budget_chars,
            "reserved_chars": budget.reserved_chars,
            "effective_total_budget_chars": budget.effective_total_budget,
            "max_added_chars": budget.max_added_chars,
            "max_parts": budget.max_parts,
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

    def _agent_trail_kv_key(self, session_key: str) -> str:
        return "agent_trail:" + self._safe_session_key(session_key)

    def _sticker_memory_kv_key(self, session_key: str) -> str:
        return "sticker_memory:" + self._safe_session_key(session_key)

    def _background_post_checkpoint_kv_key(self, session_key: str) -> str:
        return "background_post_queue:" + self._safe_session_key(session_key)

    def _realtime_chat_enabled(self) -> bool:
        return self._cfg_bool("enable_realtime_chat", True)

    def _realtime_chat_settings(self) -> RealtimeChatSettings:
        return RealtimeChatSettings(
            enabled=self._realtime_chat_enabled(),
            max_parts=max(1, self._cfg_int("realtime_chat_max_parts", 5)),
            min_part_chars=max(1, self._cfg_int("realtime_chat_min_part_chars", 3)),
            max_part_chars=max(12, self._cfg_int("realtime_chat_max_part_chars", 72)),
            chars_per_second=max(
                1.0,
                self._cfg_float("realtime_chat_chars_per_second", 7.0),
            ),
            min_delay_seconds=max(
                0.0,
                self._cfg_float("realtime_chat_min_delay_seconds", 0.35),
            ),
            max_delay_seconds=max(
                0.0,
                self._cfg_float("realtime_chat_max_delay_seconds", 4.0),
            ),
            jitter_ratio=max(
                0.0,
                self._cfg_float("realtime_chat_jitter_ratio", 0.22),
            ),
            strip_markdown=self._cfg_bool("realtime_chat_strip_markdown", True),
        )

    def _sticker_reaction_enabled(self) -> bool:
        return self._cfg_bool("enable_sticker_reaction", True)

    def _sticker_learning_enabled(self) -> bool:
        return self._cfg_bool("sticker_learn_user_images", True)

    def _sticker_settings(self) -> StickerSettings:
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
                min(1.0, self._cfg_float("sticker_send_probability", 0.18)),
            ),
            learned_enabled=self._sticker_learning_enabled(),
        )

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

    def _cfg(self, key: str, default: Any) -> Any:
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

    def _log_warning(self, message: str) -> None:
        writer = getattr(logger, "warning", None) or getattr(logger, "debug", None)
        if callable(writer):
            writer(message)

    def _clip_one_line(self, text: str, limit: int) -> str:
        cleaned = " ".join(str(text or "").split())
        return self._clip(cleaned, limit)

    def _clip(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: limit // 2] + "\n...\n" + text[-limit // 2 :]
