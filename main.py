from __future__ import annotations

import contextvars
import json
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


def get_emotional_state_plugin(context: Context) -> Any | None:
    """Return the activated emotional state plugin instance for other plugins."""
    getter = getattr(context, "get_registered_star", None)
    if not callable(getter):
        return None
    metadata = getter(PLUGIN_NAME)
    if not metadata or not getattr(metadata, "activated", True):
        return None
    plugin = getattr(metadata, "star_cls", None)
    if plugin is None or not hasattr(plugin, "get_emotion_snapshot"):
        return None
    return plugin


@register(
    PLUGIN_NAME,
    "pidan",
    "基于 PAD/OCC/appraisal 与情绪动力学的 AstrBot 多维情绪状态插件",
    "1.0.0",
    "",
)
class EmotionalStatePlugin(Star):
    emotion_api_version = PUBLIC_API_VERSION
    emotion_schema_version = PUBLIC_SCHEMA_VERSION
    emotion_memory_schema_version = PUBLIC_MEMORY_SCHEMA_VERSION
    psychological_screening_schema_version = PUBLIC_SCREENING_SCHEMA_VERSION

    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self.base_parameters = self._build_parameters()
        self.engine = EmotionEngine(self.base_parameters)
        self.psychological_engine = PsychologicalScreeningEngine(
            self._build_psychological_parameters(),
        )
        self._memory_cache: dict[str, EmotionState] = {}
        self._psychological_memory_cache: dict[str, PsychologicalScreeningState] = {}
        self._last_request_text: dict[str, str] = {}

    async def terminate(self):
        self._memory_cache.clear()
        self._psychological_memory_cache.clear()
        self._last_request_text.clear()

    @filter.on_llm_request()
    async def on_llm_request(
        self,
        event: AstrMessageEvent,
        request: ProviderRequest,
    ) -> None:
        if _INTERNAL_LLM_CALL.get() or not self._cfg_bool("enabled", True):
            return

        session_key = self._session_key(event, request)
        persona_profile = await self._persona_profile(event, request)
        state = await self._load_state(session_key, persona_profile)
        engine = self._engine_for_persona(persona_profile)
        context_text = self._request_to_text(request)
        current_text = self._event_text(event) or request.prompt or ""
        self._last_request_text[session_key] = context_text

        if self._assessment_timing() in {"pre", "both"}:
            observation = await self._assess_emotion(
                event=event,
                phase="pre_response",
                previous_state=state,
                persona_profile=persona_profile,
                context_text=context_text,
                current_text=current_text,
            )
            state = engine.update(state, observation, profile=persona_profile)
            await self._save_state(session_key, state)

        if self._cfg_bool("inject_state", True):
            request.extra_user_content_parts.append(
                TextPart(text=self._build_state_injection(state)).mark_as_temp(),
            )

    @filter.on_llm_response()
    async def on_llm_response(
        self,
        event: AstrMessageEvent,
        response: LLMResponse,
    ) -> None:
        if _INTERNAL_LLM_CALL.get() or not self._cfg_bool("enabled", True):
            return
        if self._assessment_timing() not in {"post", "both"}:
            return

        session_key = self._session_key(event)
        persona_profile = await self._persona_profile(event, None)
        state = await self._load_state(session_key, persona_profile)
        engine = self._engine_for_persona(persona_profile)
        response_text = getattr(response, "completion_text", "") or ""
        if not response_text.strip():
            return

        observation = await self._assess_emotion(
            event=event,
            phase="post_response",
            previous_state=state,
            persona_profile=persona_profile,
            context_text=self._last_request_text.get(session_key, ""),
            current_text=response_text,
        )
        state = engine.update(state, observation, profile=persona_profile)
        await self._save_state(session_key, state)

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
        persona_profile = await self._public_persona_profile(
            event,
            request,
            allow_default=event is not None,
        )
        state = await self._load_state(session_key, persona_profile)
        prompt_fragment = (
            self._build_state_injection(state) if include_prompt_fragment else None
        )
        return state.to_public_dict(
            session_key=session_key,
            prompt_fragment=prompt_fragment,
            include_safety=self._safety_boundary_enabled(),
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
        persona_profile = await self._public_persona_profile(
            event,
            request,
            allow_default=event is not None,
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
        snapshot = await self.get_emotion_snapshot(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        return dict(snapshot["emotion"]["values"])

    async def get_emotion_consequences(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        """Public API: return action tendencies and active persistent effects."""
        snapshot = await self.get_emotion_snapshot(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        return dict(snapshot["consequences"])

    async def get_emotion_relationship(
        self,
        event_or_session: AstrMessageEvent | str | None = None,
        *,
        request: ProviderRequest | None = None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        """Public API: return relationship decision, conflict cause and repair status."""
        snapshot = await self.get_emotion_snapshot(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        return dict(snapshot["relationship"])

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
        persona_profile = await self._public_persona_profile(
            event,
            request,
            allow_default=event is not None,
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
    ) -> dict[str, Any]:
        """Public API: wrap a memory entry with the emotion snapshot at write time."""
        snapshot = await self.get_emotion_snapshot(
            event_or_session,
            request=request,
            session_key=session_key,
            include_prompt_fragment=include_prompt_fragment,
        )
        return build_memory_payload(
            memory=memory,
            memory_text=memory_text,
            source=source,
            snapshot=snapshot,
            include_prompt_fragment=include_prompt_fragment,
            include_raw_snapshot=include_raw_snapshot,
            written_at=written_at,
        )

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
        persona_profile = persona_profile or await self._public_persona_profile(
            event,
            request,
            allow_default=event is not None,
        )
        previous_state = await self._load_state(session_key, persona_profile)
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
        payload = emotion_state_to_public_payload(
            state,
            session_key=session_key,
            prompt_fragment=self._build_state_injection(state),
            include_safety=self._safety_boundary_enabled(),
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
        snapshot = await self.get_psychological_screening_snapshot(
            event_or_session,
            request=request,
            session_key=session_key,
        )
        return dict(snapshot["values"])

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
        persona_profile: PersonaProfile,
        context_text: str,
        current_text: str,
    ) -> EmotionObservation:
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
        max_context_chars = self._cfg_int("max_context_chars", 2600)
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
            llm_resp = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=self._cfg_float("assessor_temperature", 0.1),
            )
        except Exception as exc:
            logger.warning(f"{PLUGIN_NAME}: LLM 情绪估计失败，启用回退估计: {exc}")
            return heuristic_observation(current_text, profile=persona_profile)
        finally:
            _INTERNAL_LLM_CALL.reset(token)

        observation = observation_from_llm_text(getattr(llm_resp, "completion_text", ""))
        if observation is None:
            logger.warning(f"{PLUGIN_NAME}: 情绪估计输出不是可解析 JSON，启用回退估计。")
            return heuristic_observation(current_text, profile=persona_profile)
        return observation

    async def _provider_id(self, event: AstrMessageEvent) -> str | None:
        configured = str(self._cfg("emotion_provider_id", "") or "").strip()
        if configured:
            return configured
        try:
            return await self.context.get_current_chat_provider_id(
                umo=event.unified_msg_origin,
            )
        except Exception as exc:
            logger.warning(f"{PLUGIN_NAME}: 获取当前 LLM Provider 失败: {exc}")
            return None

    async def _load_state(
        self,
        session_key: str,
        persona_profile: PersonaProfile | None = None,
    ) -> EmotionState:
        if session_key in self._memory_cache:
            state = self._memory_cache[session_key]
            state = self._ensure_persona_state(state, persona_profile)
            engine = self._engine_for_persona(persona_profile)
            decayed_state = engine.passive_update(state, profile=persona_profile)
            if decayed_state.to_dict() != state.to_dict():
                state = decayed_state
                await self._save_state(session_key, state)
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
        engine = self._engine_for_persona(persona_profile)
        decayed_state = engine.passive_update(state, profile=persona_profile)
        if decayed_state.to_dict() != state.to_dict():
            state = decayed_state
            await self._save_state(session_key, state)
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

    def _engine_for_persona(self, profile: PersonaProfile | None) -> EmotionEngine:
        if profile is None or not self._cfg_bool("persona_modeling", True):
            return self.engine
        parameters = apply_persona_to_parameters(self.base_parameters, profile)
        return EmotionEngine(parameters=parameters, baseline=profile.baseline)

    def _safety_boundary_enabled(self) -> bool:
        return self._cfg_bool("enable_safety_boundary", True)

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

    def _build_state_injection(self, state: EmotionState) -> str:
        return build_state_injection(
            state,
            safety_boundary=self._safety_boundary_enabled(),
        )

    def _ensure_persona_state(
        self,
        state: EmotionState,
        profile: PersonaProfile | None,
    ) -> EmotionState:
        if not profile or not self._cfg_bool("persona_modeling", True):
            return state
        if state.persona_fingerprint == profile.fingerprint:
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
        timing = str(self._cfg("assessment_timing", "both") or "both").strip().lower()
        if timing in {"pre", "post", "both"}:
            return timing
        return "both"

    def _request_to_text(self, request: ProviderRequest) -> str:
        parts: list[str] = []
        if request.system_prompt:
            parts.append("[system]\n" + self._clip(request.system_prompt, 800))
        for item in list(request.contexts or [])[-8:]:
            parts.append(self._context_item_to_text(item))
        if request.prompt:
            parts.append("[current_user]\n" + request.prompt)
        if request.extra_user_content_parts:
            extra = []
            for part in request.extra_user_content_parts[-3:]:
                text = getattr(part, "text", "")
                if text:
                    extra.append(text)
            if extra:
                parts.append("[extra_user_content]\n" + "\n".join(extra))
        return "\n\n".join(part for part in parts if part)

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

    def _kv_key(self, session_key: str) -> str:
        return "emotion_state:" + session_key.replace("/", "_").replace("\\", "_")

    def _psychological_kv_key(self, session_key: str) -> str:
        return "psychological_screening:" + session_key.replace("/", "_").replace("\\", "_")

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

    def _clip(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: limit // 2] + "\n...\n" + text[-limit // 2 :]
