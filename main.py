from __future__ import annotations

import contextvars
import asyncio
import json
import time
from copy import deepcopy
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
        derive_initiative_policy,
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
    from .prompts import (
        ASSESSOR_SYSTEM_PROMPT,
        LOW_REASONING_ASSESSOR_SYSTEM_PROMPT,
        build_assessment_prompt,
        build_state_injection,
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
        derive_initiative_policy,
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
    from prompts import (
        ASSESSOR_SYSTEM_PROMPT,
        LOW_REASONING_ASSESSOR_SYSTEM_PROMPT,
        build_assessment_prompt,
        build_state_injection,
    )


PLUGIN_NAME = "astrbot_plugin_emotional_state"
_INTERNAL_LLM_CALL: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "astrbot_emotional_state_internal_llm_call",
    default=False,
)

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
    "0.1.0-beta",
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
        self._memory_cache: dict[str, EmotionState] = {}
        self._psychological_memory_cache: dict[str, PsychologicalScreeningState] = {}
        self._humanlike_memory_cache: dict[str, HumanlikeState] = {}
        self._lifelike_learning_memory_cache: dict[str, LifelikeLearningState] = {}
        self._personality_drift_memory_cache: dict[str, PersonalityDriftState] = {}
        self._moral_repair_memory_cache: dict[str, MoralRepairState] = {}
        self._fallibility_memory_cache: dict[str, FallibilityState] = {}
        self._engine_cache: dict[str, EmotionEngine] = {}
        self._provider_id_cache: dict[str, tuple[float, str | None]] = {}
        self._last_request_text: dict[str, str] = {}

    async def terminate(self):
        self._memory_cache.clear()
        self._psychological_memory_cache.clear()
        self._humanlike_memory_cache.clear()
        self._lifelike_learning_memory_cache.clear()
        self._personality_drift_memory_cache.clear()
        self._moral_repair_memory_cache.clear()
        self._fallibility_memory_cache.clear()
        self._engine_cache.clear()
        self._provider_id_cache.clear()
        self._last_request_text.clear()

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
        inject_state = self._cfg_bool("inject_state", True)
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
        session_key = self._session_key(event, request)
        context_text = self._request_to_text(request)
        self._last_request_text[session_key] = context_text
        needs_request_state = (
            assessment_timing in {"pre", "both"}
            or inject_state
            or humanlike_enabled
            or lifelike_enabled
            or moral_repair_enabled
            or personality_drift_enabled
            or fallibility_enabled
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
        current_text = self._event_text(event) or request.prompt or ""
        request_observation_text: str | None = None
        humanlike_state: HumanlikeState | None = None
        lifelike_learning_state: LifelikeLearningState | None = None
        moral_repair_state: MoralRepairState | None = None
        fallibility_state: FallibilityState | None = None

        if assessment_timing in {"pre", "both"}:
            observation = await self._assess_emotion(
                event=event,
                phase="pre_response",
                previous_state=state,
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

        auxiliary_load_tasks: dict[str, asyncio.Task[Any]] = {}
        if humanlike_enabled:
            auxiliary_load_tasks["humanlike"] = asyncio.create_task(
                self._load_humanlike_state(session_key, now=observed_at),
            )
        if lifelike_enabled:
            auxiliary_load_tasks["lifelike"] = asyncio.create_task(
                self._load_lifelike_learning_state(session_key, now=observed_at),
            )
        if moral_repair_enabled:
            auxiliary_load_tasks["moral_repair"] = asyncio.create_task(
                self._load_moral_repair_state(session_key, now=observed_at),
            )
        if fallibility_enabled:
            auxiliary_load_tasks["fallibility"] = asyncio.create_task(
                self._load_fallibility_state(session_key, now=observed_at),
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
            request.extra_user_content_parts.append(
                TextPart(
                    text=build_state_injection(
                        state,
                        safety_boundary=safety_boundary,
                    ),
                ).mark_as_temp(),
            )
            if humanlike_injection_enabled:
                humanlike_state = humanlike_state or await self._load_humanlike_state(
                    session_key,
                    now=observed_at,
                )
                request.extra_user_content_parts.append(
                    TextPart(
                        text=build_humanlike_prompt_fragment(
                            humanlike_state,
                            safety_boundary=safety_boundary,
                        ),
                    ).mark_as_temp(),
                )
            if lifelike_injection_enabled:
                lifelike_learning_state = (
                    lifelike_learning_state
                    or await self._load_lifelike_learning_state(
                        session_key,
                        now=observed_at,
                    )
                )
                request.extra_user_content_parts.append(
                    TextPart(
                        text=build_lifelike_prompt_fragment(lifelike_learning_state),
                    ).mark_as_temp(),
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
                request.extra_user_content_parts.append(
                    TextPart(
                        text=build_personality_drift_prompt_fragment(
                            personality_drift_state,
                        ),
                    ).mark_as_temp(),
                )
            if moral_repair_injection_enabled:
                moral_repair_state = (
                    moral_repair_state
                    or await self._load_moral_repair_state(
                        session_key,
                        now=observed_at,
                    )
                )
                request.extra_user_content_parts.append(
                    TextPart(
                        text=build_moral_repair_prompt_fragment(
                            moral_repair_state,
                            safety_boundary=safety_boundary,
                        ),
                    ).mark_as_temp(),
                )
            if fallibility_injection_enabled:
                fallibility_state = fallibility_state or await self._load_fallibility_state(
                    session_key,
                    now=observed_at,
                )
                request.extra_user_content_parts.append(
                    TextPart(
                        text=build_fallibility_prompt_fragment(
                            fallibility_state,
                            safety_boundary=safety_boundary,
                        ),
                    ).mark_as_temp(),
                )

    @filter.on_llm_response()
    async def on_llm_response(
        self,
        event: AstrMessageEvent,
        response: LLMResponse,
    ) -> None:
        if _INTERNAL_LLM_CALL.get() or not self._cfg_bool("enabled", True):
            return
        assessment_timing = self._assessment_timing()
        if assessment_timing not in {"post", "both"}:
            return

        response_text = getattr(response, "completion_text", "") or ""
        if not response_text.strip():
            return

        moral_repair_enabled = self._moral_repair_modeling_enabled()
        personality_drift_enabled = self._personality_drift_enabled()
        fallibility_enabled = self._fallibility_modeling_enabled()
        safety_boundary = self._safety_boundary_enabled()
        session_key = self._session_key(event)
        observed_at = self._observed_now()
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
        moral_repair_load_task: asyncio.Task[MoralRepairState] | None = None
        if moral_repair_enabled:
            moral_repair_load_task = asyncio.create_task(
                self._load_moral_repair_state(session_key, now=observed_at),
            )
        fallibility_load_task: asyncio.Task[FallibilityState] | None = None
        if fallibility_enabled:
            fallibility_load_task = asyncio.create_task(
                self._load_fallibility_state(session_key, now=observed_at),
            )

        try:
            observation = await self._assess_emotion(
                event=event,
                phase="post_response",
                previous_state=state,
                persona_profile=persona_profile,
                context_text=self._last_request_text.get(session_key, ""),
                current_text=response_text,
            )
            state = engine.update(
                state,
                observation,
                profile=persona_profile,
                now=observed_at,
            )
            await self._save_state(session_key, state)
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
                else await self._load_moral_repair_state(session_key, now=observed_at)
            )
            moral_repair_observation = heuristic_moral_repair_observation(
                response_text,
                source="llm_response",
            )
            moral_repair_state = self.moral_repair_engine.update(
                previous_moral_repair_state,
                moral_repair_observation,
                now=observed_at,
            )
            await self._save_moral_repair_state(session_key, moral_repair_state)
        if fallibility_enabled:
            previous_fallibility_state = (
                await fallibility_load_task
                if fallibility_load_task is not None
                else await self._load_fallibility_state(session_key, now=observed_at)
            )
            fallibility_observation = heuristic_fallibility_observation(
                response_text,
                source="llm_response",
            )
            fallibility_state = self.fallibility_engine.update(
                previous_fallibility_state,
                fallibility_observation,
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

    async def get_emotion_snapshot(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
        include_prompt_fragment: bool = False,
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
        prompt_fragment = (
            self._build_state_injection(
                state,
                safety_boundary=safety_boundary,
            )
            if include_prompt_fragment
            else None
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
        request.extra_user_content_parts.append(TextPart(text=fragment).mark_as_temp())

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
        return {
            "schema_version": "astrbot.shadow_diagnostics.v1",
            "kind": "shadow_diagnostics",
            "enabled": True,
            "session_key": resolved_session_key,
            "simulated_agent_state": True,
            "diagnostic": True,
            "executable_strategy_enabled": False,
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
            "not_allowed": [
                "generate_deception_strategy",
                "generate_manipulation_script",
                "generate_accountability_evasion_plan",
                "execute_shadow_impulses",
            ],
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
        previous_state = await self._load_humanlike_state(
            session_key,
            now=observed_at,
        )
        observation = heuristic_humanlike_observation(text, source=source)
        state = self.humanlike_engine.update(
            previous_state,
            observation,
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
        payload = state.to_public_dict(
            session_key=session_key,
            exposure=exposure,
            safety_boundary=safety_boundary,
        )
        if include_prompt_fragment:
            payload["prompt_fragment"] = build_moral_repair_prompt_fragment(
                state,
                safety_boundary=safety_boundary,
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
        previous_state = await self._load_moral_repair_state(
            session_key,
            now=observed_at,
        )
        observation = heuristic_moral_repair_observation(text, source=source)
        state = self.moral_repair_engine.update(
            previous_state,
            observation,
            now=observed_at,
        )
        if commit:
            await self._save_moral_repair_state(session_key, state)
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
        payload = state.to_public_dict(
            session_key=session_key,
            exposure=exposure,
            safety_boundary=safety_boundary,
        )
        if include_prompt_fragment:
            payload["prompt_fragment"] = build_fallibility_prompt_fragment(
                state,
                safety_boundary=safety_boundary,
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
        previous_state = await self._load_fallibility_state(
            session_key,
            now=observed_at,
        )
        observation = heuristic_fallibility_observation(text, source=source)
        state = self.fallibility_engine.update(
            previous_state,
            observation,
            now=observed_at,
        )
        if commit:
            await self._save_fallibility_state(session_key, state)
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
        previous_state = await self._load_psychological_state(session_key)
        observation = heuristic_psychological_observation(text, source=source)
        state = self.psychological_engine.update(
            previous_state,
            observation,
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
    ):
        """获取当前 bot 的可计算情绪状态，只读。

        Args:
            detail(string): 返回粒度，可填 summary 或 full
        """
        full = str(detail or "").strip().lower() == "full"
        snapshot = await self.get_emotion_snapshot(
            event,
            include_prompt_fragment=full,
        )
        if not full:
            snapshot.pop("prompt_fragment", None)
            snapshot["consequences"]["notes"] = snapshot["consequences"]["notes"][:2]
        yield event.plain_result(json.dumps(snapshot, ensure_ascii=False))

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
        yield event.plain_result(json.dumps(snapshot, ensure_ascii=False))

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
        yield event.plain_result(json.dumps(snapshot, ensure_ascii=False))

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
        yield event.plain_result(json.dumps(snapshot, ensure_ascii=False))

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
        yield event.plain_result(json.dumps(snapshot, ensure_ascii=False))

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
        yield event.plain_result(json.dumps(snapshot, ensure_ascii=False))

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
        yield event.plain_result(json.dumps(snapshot, ensure_ascii=False))

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
        yield event.plain_result(json.dumps(snapshot, ensure_ascii=False))

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
            "delta_t 为加权欧氏惊讶度；"
            "alpha_t = clamp(alpha_base,p * sigmoid(k(c_t-c0)) * (1+r_p delta_t), alpha_min, alpha_max)。\n"
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
        if not self._cfg_bool("persona_modeling", True):
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
            strength=self._cfg_float("persona_influence", 1.0),
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
            llm_resp = await asyncio.wait_for(
                self.context.llm_generate(
                    chat_provider_id=provider_id,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=self._cfg_float("assessor_temperature", 0.1),
                ),
                timeout=max(0.1, self._cfg_float("assessor_timeout_seconds", 4.0)),
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
    ) -> PsychologicalScreeningState:
        if session_key in self._psychological_memory_cache:
            return self._psychological_memory_cache[session_key]
        try:
            data = await self.get_kv_data(self._psychological_kv_key(session_key), None)
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: 心理筛查 KV 读取失败，使用空状态: {exc}")
            data = None
        state = PsychologicalScreeningState.from_dict(data)
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
        now: float | None = None,
    ) -> HumanlikeState:
        if session_key in self._humanlike_memory_cache:
            state = self._humanlike_memory_cache[session_key]
            if self._passive_load_is_fresh(state, now=now):
                return state
            decayed_state = self.humanlike_engine.passive_update(state, now=now)
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
        decayed_state = self.humanlike_engine.passive_update(state, now=now)
        if self._passive_update_changed(decayed_state, state):
            state = decayed_state
        self._humanlike_memory_cache[session_key] = state
        return state

    async def _save_humanlike_state(
        self,
        session_key: str,
        state: HumanlikeState,
    ) -> None:
        self._humanlike_memory_cache[session_key] = state
        try:
            await self.put_kv_data(self._humanlike_kv_key(session_key), state.to_dict())
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: humanlike KV write failed, keeping memory only: {exc}")

    async def _delete_humanlike_state(self, session_key: str) -> None:
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
        self._lifelike_learning_memory_cache[session_key] = state
        try:
            await self.put_kv_data(
                self._lifelike_learning_kv_key(session_key),
                state.to_dict(),
            )
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: lifelike learning KV write failed, keeping memory only: {exc}")

    async def _delete_lifelike_learning_state(self, session_key: str) -> None:
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
        self._personality_drift_memory_cache[session_key] = state
        try:
            await self.put_kv_data(
                self._personality_drift_kv_key(session_key),
                state.to_dict(),
            )
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: personality drift KV write failed, keeping memory only: {exc}")

    async def _delete_personality_drift_state(self, session_key: str) -> None:
        self._personality_drift_memory_cache.pop(session_key, None)
        try:
            await self.delete_kv_data(self._personality_drift_kv_key(session_key))
        except Exception as exc:
            logger.debug(f"{PLUGIN_NAME}: personality drift KV delete failed: {exc}")

    async def _load_moral_repair_state(
        self,
        session_key: str,
        *,
        now: float | None = None,
    ) -> MoralRepairState:
        if session_key in self._moral_repair_memory_cache:
            state = self._moral_repair_memory_cache[session_key]
            if self._passive_load_is_fresh(state, now=now):
                return state
            decayed_state = self.moral_repair_engine.passive_update(state, now=now)
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
        decayed_state = self.moral_repair_engine.passive_update(state, now=now)
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
        now: float | None = None,
    ) -> FallibilityState:
        if session_key in self._fallibility_memory_cache:
            state = self._fallibility_memory_cache[session_key]
            if self._passive_load_is_fresh(state, now=now):
                return state
            decayed_state = self.fallibility_engine.passive_update(state, now=now)
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
        decayed_state = self.fallibility_engine.passive_update(state, now=now)
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

    def _build_parameters(self) -> EmotionParameters:
        return EmotionParameters(
            alpha_base=self._cfg_float("alpha_base", 0.42),
            alpha_min=self._cfg_float("alpha_min", 0.06),
            alpha_max=self._cfg_float("alpha_max", 0.72),
            baseline_decay=self._cfg_float("baseline_decay", 0.035),
            baseline_half_life_seconds=self._cfg_float(
                "baseline_half_life_seconds",
                21600.0,
            ),
            reactivity=self._cfg_float("reactivity", 0.55),
            confidence_midpoint=self._cfg_float("confidence_midpoint", 0.5),
            confidence_slope=self._cfg_float("confidence_slope", 7.0),
            min_update_interval_seconds=self._cfg_float(
                "min_update_interval_seconds",
                8.0,
            ),
            rapid_update_half_life_seconds=self._cfg_float(
                "rapid_update_half_life_seconds",
                20.0,
            ),
            arousal_from_surprise=self._cfg_float("arousal_from_surprise", 0.18),
            dominance_control_coupling=self._cfg_float(
                "dominance_control_coupling",
                0.12,
            ),
            consequence_decay=self._cfg_float("consequence_decay", 0.68),
            consequence_half_life_seconds=self._cfg_float(
                "consequence_half_life_seconds",
                10800.0,
            ),
            consequence_threshold=self._cfg_float("consequence_threshold", 0.48),
            consequence_strength=self._cfg_float("consequence_strength", 1.0),
            cold_war_turns=self._cfg_int("cold_war_turns", 3),
            cold_war_duration_seconds=self._cfg_float(
                "cold_war_duration_seconds",
                1800.0,
            ),
            short_effect_duration_seconds=self._cfg_float(
                "short_effect_duration_seconds",
                900.0,
            ),
        )

    def _build_psychological_parameters(self) -> PsychologicalScreeningParameters:
        return PsychologicalScreeningParameters(
            alpha_base=self._cfg_float("psychological_alpha_base", 0.32),
            alpha_min=self._cfg_float("psychological_alpha_min", 0.04),
            alpha_max=self._cfg_float("psychological_alpha_max", 0.55),
            state_half_life_seconds=self._cfg_float(
                "psychological_state_half_life_seconds",
                604800.0,
            ),
            crisis_half_life_seconds=self._cfg_float(
                "psychological_crisis_half_life_seconds",
                2592000.0,
            ),
            trajectory_limit=self._cfg_int("psychological_trajectory_limit", 40),
        )

    def _build_humanlike_parameters(self) -> HumanlikeParameters:
        return HumanlikeParameters(
            alpha_base=self._cfg_float("humanlike_alpha_base", 0.30),
            alpha_min=self._cfg_float("humanlike_alpha_min", 0.03),
            alpha_max=self._cfg_float("humanlike_alpha_max", 0.46),
            confidence_midpoint=self._cfg_float(
                "humanlike_confidence_midpoint",
                0.5,
            ),
            confidence_slope=self._cfg_float("humanlike_confidence_slope", 6.0),
            state_half_life_seconds=self._cfg_float(
                "humanlike_state_half_life_seconds",
                21600.0,
            ),
            rapid_update_half_life_seconds=self._cfg_float(
                "humanlike_rapid_update_half_life_seconds",
                20.0,
            ),
            min_update_interval_seconds=self._cfg_float(
                "humanlike_min_update_interval_seconds",
                8.0,
            ),
            max_impulse_per_update=self._cfg_float(
                "humanlike_max_impulse_per_update",
                0.18,
            ),
            trajectory_limit=self._cfg_int("humanlike_trajectory_limit", 40),
        )

    def _build_lifelike_learning_parameters(self) -> LifelikeLearningParameters:
        return LifelikeLearningParameters(
            state_half_life_seconds=self._cfg_float(
                "lifelike_learning_half_life_seconds",
                2592000.0,
            ),
            min_update_interval_seconds=self._cfg_float(
                "lifelike_learning_min_update_interval_seconds",
                10.0,
            ),
            max_terms=self._cfg_int("lifelike_learning_max_terms", 120),
            trajectory_limit=self._cfg_int("lifelike_learning_trajectory_limit", 60),
            confidence_growth=self._cfg_float(
                "lifelike_learning_confidence_growth",
                0.25,
            ),
        )

    def _build_personality_drift_parameters(self) -> PersonalityDriftParameters:
        return PersonalityDriftParameters(
            state_half_life_seconds=self._cfg_float(
                "personality_drift_half_life_seconds",
                7776000.0,
            ),
            rapid_update_half_life_seconds=self._cfg_float(
                "personality_drift_rapid_update_half_life_seconds",
                86400.0,
            ),
            min_update_interval_seconds=self._cfg_float(
                "personality_drift_min_update_interval_seconds",
                21600.0,
            ),
            learning_rate=self._cfg_float("personality_drift_learning_rate", 0.055),
            event_threshold=self._cfg_float("personality_drift_event_threshold", 0.12),
            max_impulse_per_update=self._cfg_float(
                "personality_drift_max_impulse_per_update",
                0.015,
            ),
            max_trait_offset=self._cfg_float(
                "personality_drift_max_trait_offset",
                0.22,
            ),
            confidence_growth=self._cfg_float(
                "personality_drift_confidence_growth",
                0.10,
            ),
            trajectory_limit=self._cfg_int("personality_drift_trajectory_limit", 80),
        )

    def _build_moral_repair_parameters(self) -> MoralRepairParameters:
        return MoralRepairParameters(
            alpha_base=self._cfg_float("moral_repair_alpha_base", 0.28),
            alpha_min=self._cfg_float("moral_repair_alpha_min", 0.03),
            alpha_max=self._cfg_float("moral_repair_alpha_max", 0.42),
            confidence_midpoint=self._cfg_float(
                "moral_repair_confidence_midpoint",
                0.5,
            ),
            confidence_slope=self._cfg_float("moral_repair_confidence_slope", 6.0),
            state_half_life_seconds=self._cfg_float(
                "moral_repair_state_half_life_seconds",
                604800.0,
            ),
            rapid_update_half_life_seconds=self._cfg_float(
                "moral_repair_rapid_update_half_life_seconds",
                30.0,
            ),
            min_update_interval_seconds=self._cfg_float(
                "moral_repair_min_update_interval_seconds",
                8.0,
            ),
            max_impulse_per_update=self._cfg_float(
                "moral_repair_max_impulse_per_update",
                0.16,
            ),
            trajectory_limit=self._cfg_int("moral_repair_trajectory_limit", 40),
        )

    def _build_fallibility_parameters(self) -> FallibilityParameters:
        return FallibilityParameters(
            alpha_base=self._cfg_float("fallibility_alpha_base", 0.22),
            alpha_min=self._cfg_float("fallibility_alpha_min", 0.02),
            alpha_max=self._cfg_float("fallibility_alpha_max", 0.34),
            confidence_midpoint=self._cfg_float(
                "fallibility_confidence_midpoint",
                0.5,
            ),
            confidence_slope=self._cfg_float("fallibility_confidence_slope", 6.0),
            state_half_life_seconds=self._cfg_float(
                "fallibility_state_half_life_seconds",
                86400.0,
            ),
            rapid_update_half_life_seconds=self._cfg_float(
                "fallibility_rapid_update_half_life_seconds",
                45.0,
            ),
            min_update_interval_seconds=self._cfg_float(
                "fallibility_min_update_interval_seconds",
                10.0,
            ),
            max_impulse_per_update=self._cfg_float(
                "fallibility_max_impulse_per_update",
                0.12,
            ),
            max_error_pressure=self._cfg_float("fallibility_max_error_pressure", 0.55),
            trajectory_limit=self._cfg_int("fallibility_trajectory_limit", 40),
        )

    def _engine_for_persona(self, profile: PersonaProfile | None) -> EmotionEngine:
        if profile is None or not self._cfg_bool("persona_modeling", True):
            return self.engine
        if not hasattr(self, "_engine_cache"):
            self._engine_cache = {}
        cached = self._engine_cache.get(profile.fingerprint)
        if cached is not None:
            return cached
        parameters = apply_persona_to_parameters(self.base_parameters, profile)
        engine = EmotionEngine(parameters=parameters, baseline=profile.baseline)
        self._engine_cache[profile.fingerprint] = engine
        if len(self._engine_cache) > 16:
            first_key = next(iter(self._engine_cache))
            self._engine_cache.pop(first_key, None)
        return engine

    def _safety_boundary_enabled(self) -> bool:
        return self._cfg_bool("enable_safety_boundary", True)

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
        return self._cfg_bool("enable_humanlike_state", False)

    def _humanlike_injection_enabled(self) -> bool:
        return self._cfg_float("humanlike_injection_strength", 0.35) > 0.0

    def _humanlike_reset_allowed(self) -> bool:
        return self._cfg_bool("allow_humanlike_reset_backdoor", True)

    def _lifelike_learning_enabled(self) -> bool:
        return self._cfg_bool("enable_lifelike_learning", False)

    def _lifelike_learning_injection_enabled(self) -> bool:
        return self._cfg_float("lifelike_learning_injection_strength", 0.30) > 0.0

    def _lifelike_learning_reset_allowed(self) -> bool:
        return self._cfg_bool("allow_lifelike_learning_reset_backdoor", True)

    def _personality_drift_enabled(self) -> bool:
        return self._cfg_bool("enable_personality_drift", False)

    def _personality_drift_injection_enabled(self) -> bool:
        return self._cfg_float("personality_drift_injection_strength", 0.22) > 0.0

    def _personality_drift_reset_allowed(self) -> bool:
        return self._cfg_bool("allow_personality_drift_reset_backdoor", True)

    def _moral_repair_modeling_enabled(self) -> bool:
        return self._cfg_bool("enable_moral_repair_state", False)

    def _moral_repair_injection_enabled(self) -> bool:
        return self._cfg_float("moral_repair_injection_strength", 0.35) > 0.0

    def _moral_repair_reset_allowed(self) -> bool:
        return self._cfg_bool("allow_moral_repair_reset_backdoor", True)

    def _fallibility_modeling_enabled(self) -> bool:
        return self._cfg_bool("enable_fallibility_state", False)

    def _fallibility_injection_enabled(self) -> bool:
        return self._cfg_float("fallibility_injection_strength", 0.0) > 0.0

    def _fallibility_reset_allowed(self) -> bool:
        return self._cfg_bool("allow_fallibility_reset_backdoor", True)

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
        return build_state_injection(
            state,
            safety_boundary=(
                self._safety_boundary_enabled()
                if safety_boundary is None
                else safety_boundary
            ),
        )

    def _ensure_persona_state(
        self,
        state: EmotionState,
        profile: PersonaProfile | None,
    ) -> EmotionState:
        if not profile or not self._cfg_bool("persona_modeling", True):
            return state
        if state.persona_fingerprint == profile.fingerprint:
            state.persona_model = deepcopy(profile.personality_model)
            return state
        if self._cfg_bool("reset_on_persona_change", True):
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
        if not self._cfg_bool("persona_modeling", True):
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
            strength=self._cfg_float("persona_influence", 1.0),
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
            or not self._cfg_bool("persona_modeling", True)
            or not self._personality_drift_enabled()
        ):
            return profile
        drift_state = drift_state or await self._load_personality_drift_state(
            session_key,
            profile,
            now=now,
        )
        return self._apply_personality_drift(profile, drift_state)

    def _apply_personality_drift(
        self,
        profile: PersonaProfile,
        state: PersonalityDriftState | None,
    ) -> PersonaProfile:
        adapted = apply_personality_drift_to_profile(
            profile,
            state,
            strength=self._cfg_float("personality_drift_apply_strength", 0.65),
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
            return self._session_key(event_or_session, request)
        if request and getattr(request, "session_id", None):
            return str(request.session_id)
        return "global"

    def _session_key(
        self,
        event: AstrMessageEvent,
        request: ProviderRequest | None = None,
    ) -> str:
        if hasattr(event, "unified_msg_origin") and event.unified_msg_origin:
            return str(event.unified_msg_origin)
        if request and request.session_id:
            return str(request.session_id)
        return "global"

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

    def _clip(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: limit // 2] + "\n...\n" + text[-limit // 2 :]
