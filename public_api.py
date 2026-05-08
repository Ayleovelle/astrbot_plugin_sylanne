from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

try:
    from .psychological_screening import PUBLIC_RISK_BOOLEAN_FIELDS
except ImportError:
    from psychological_screening import PUBLIC_RISK_BOOLEAN_FIELDS


PLUGIN_NAME = "astrbot_plugin_emotional_state"
EMOTION_API_VERSION = "1.0"
EMOTION_SCHEMA_VERSION = "astrbot.emotion_state.v2"
EMOTION_MEMORY_SCHEMA_VERSION = "astrbot.emotion_memory.v1"
PERSONALITY_PROFILE_SCHEMA_VERSION = "astrbot.personality_profile.v1"
PSYCHOLOGICAL_SCREENING_SCHEMA_VERSION = "astrbot.psychological_screening.v1"
HUMANLIKE_STATE_SCHEMA_VERSION = "astrbot.humanlike_state.v1"
LIFELIKE_LEARNING_SCHEMA_VERSION = "astrbot.lifelike_learning_state.v1"
PERSONALITY_DRIFT_SCHEMA_VERSION = "astrbot.personality_drift_state.v1"
MORAL_REPAIR_STATE_SCHEMA_VERSION = "astrbot.moral_repair_state.v1"
INTEGRATED_SELF_SCHEMA_VERSION = "astrbot.integrated_self_state.v1"
PSYCHOLOGICAL_RISK_BOOLEAN_FIELDS = PUBLIC_RISK_BOOLEAN_FIELDS


def _has_expected_public_versions(plugin: Any, expected: dict[str, str]) -> bool:
    return all(getattr(plugin, name, None) == value for name, value in expected.items())


@runtime_checkable
class EmotionServiceProtocol(Protocol):
    emotion_api_version: str
    emotion_schema_version: str
    emotion_memory_schema_version: str
    personality_profile_schema_version: str
    psychological_screening_schema_version: str
    integrated_self_schema_version: str
    lifelike_learning_schema_version: str
    personality_drift_schema_version: str

    async def get_emotion_snapshot(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
        include_prompt_fragment: bool = False,
    ) -> dict[str, Any]:
        ...

    async def get_emotion_state(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
        as_dict: bool = True,
    ) -> dict[str, Any] | Any:
        ...

    async def get_emotion_values(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> dict[str, float]:
        ...

    async def get_emotion_consequences(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        ...

    async def get_emotion_relationship(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        ...

    async def get_emotion_prompt_fragment(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> str:
        ...

    async def build_emotion_memory_payload(
        self,
        event_or_session: Any = None,
        memory: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
        memory_text: str = "",
        source: str = "livingmemory",
        include_prompt_fragment: bool = False,
        include_raw_snapshot: bool = True,
        written_at: float | None = None,
    ) -> dict[str, Any]:
        ...

    async def inject_emotion_context(self, event: Any, request: Any) -> None:
        ...

    async def observe_emotion_text(
        self,
        event_or_session: Any = None,
        text: str = "",
        *,
        phase: str = "external",
        role: str = "plugin",
        source: str = "plugin",
        request: Any = None,
        context_text: str = "",
        session_key: str | None = None,
        persona_profile: Any = None,
        use_llm: bool = True,
        commit: bool = True,
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        ...

    async def get_psychological_screening_snapshot(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        ...

    async def get_psychological_screening_values(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> dict[str, float]:
        ...

    async def observe_psychological_text(
        self,
        event_or_session: Any = None,
        text: str = "",
        *,
        request: Any = None,
        session_key: str | None = None,
        source: str = "plugin",
        commit: bool = True,
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        ...

    async def simulate_psychological_update(
        self,
        event_or_session: Any = None,
        text: str = "",
        *,
        request: Any = None,
        session_key: str | None = None,
        source: str = "plugin",
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        ...

    async def reset_psychological_screening_state(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> bool:
        ...

    async def simulate_emotion_update(
        self,
        event_or_session: Any = None,
        text: str = "",
        *,
        phase: str = "simulation",
        role: str = "plugin",
        source: str = "plugin",
        request: Any = None,
        context_text: str = "",
        session_key: str | None = None,
        persona_profile: Any = None,
        use_llm: bool = True,
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        ...

    async def reset_emotion_state(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> bool:
        ...

    async def get_integrated_self_snapshot(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
        include_raw_snapshots: bool = False,
        degradation_profile: str | None = None,
    ) -> dict[str, Any]:
        ...

    async def get_integrated_self_prompt_fragment(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> str:
        ...

    async def get_integrated_self_policy_plan(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        ...

    async def build_integrated_self_replay_bundle(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
        scenario_name: str = "current",
    ) -> dict[str, Any]:
        ...

    async def replay_integrated_self_bundle(
        self,
        bundle: dict[str, Any],
    ) -> dict[str, Any]:
        ...

    async def probe_integrated_self_compatibility(
        self,
        payload: dict[str, Any] | None = None,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        ...

    async def export_integrated_self_diagnostics(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        ...

    async def get_lifelike_learning_snapshot(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
        exposure: str = "plugin_safe",
        include_prompt_fragment: bool = False,
    ) -> dict[str, Any]:
        ...

    async def get_lifelike_initiative_policy(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        ...

    async def get_lifelike_prompt_fragment(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> str:
        ...

    async def observe_lifelike_text(
        self,
        event_or_session: Any = None,
        text: str = "",
        *,
        request: Any = None,
        session_key: str | None = None,
        source: str = "plugin",
        commit: bool = True,
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        ...

    async def simulate_lifelike_update(
        self,
        event_or_session: Any = None,
        text: str = "",
        *,
        request: Any = None,
        session_key: str | None = None,
        source: str = "plugin",
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        ...

    async def reset_lifelike_learning_state(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> bool:
        ...

    async def get_personality_drift_snapshot(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
        exposure: str = "plugin_safe",
        include_prompt_fragment: bool = False,
    ) -> dict[str, Any]:
        ...

    async def get_personality_drift_values(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> dict[str, float]:
        ...

    async def get_personality_drift_prompt_fragment(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> str:
        ...

    async def observe_personality_drift_event(
        self,
        event_or_session: Any = None,
        text: str = "",
        *,
        request: Any = None,
        session_key: str | None = None,
        source: str = "plugin",
        trait_impulses: dict[str, float] | None = None,
        intensity: float | None = None,
        reliability: float | None = None,
        relationship_importance: float | None = None,
        commit: bool = True,
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        ...

    async def simulate_personality_drift_update(
        self,
        event_or_session: Any = None,
        text: str = "",
        *,
        request: Any = None,
        session_key: str | None = None,
        source: str = "plugin",
        trait_impulses: dict[str, float] | None = None,
        intensity: float | None = None,
        reliability: float | None = None,
        relationship_importance: float | None = None,
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        ...

    async def reset_personality_drift_state(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> bool:
        ...


@runtime_checkable
class HumanlikeStateServiceProtocol(EmotionServiceProtocol, Protocol):
    humanlike_state_schema_version: str

    async def get_humanlike_snapshot(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
        exposure: str = "plugin_safe",
        include_prompt_fragment: bool = False,
    ) -> dict[str, Any]:
        ...

    async def get_humanlike_values(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> dict[str, float]:
        ...

    async def get_humanlike_prompt_fragment(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> str:
        ...

    async def observe_humanlike_text(
        self,
        event_or_session: Any = None,
        text: str = "",
        *,
        request: Any = None,
        session_key: str | None = None,
        source: str = "plugin",
        commit: bool = True,
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        ...

    async def simulate_humanlike_update(
        self,
        event_or_session: Any = None,
        text: str = "",
        *,
        request: Any = None,
        session_key: str | None = None,
        source: str = "plugin",
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        ...

    async def reset_humanlike_state(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> bool:
        ...


@runtime_checkable
class MoralRepairStateServiceProtocol(EmotionServiceProtocol, Protocol):
    moral_repair_state_schema_version: str

    async def get_moral_repair_snapshot(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
        exposure: str = "plugin_safe",
        include_prompt_fragment: bool = False,
    ) -> dict[str, Any]:
        ...

    async def get_moral_repair_values(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> dict[str, float]:
        ...

    async def get_moral_repair_prompt_fragment(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> str:
        ...

    async def observe_moral_repair_text(
        self,
        event_or_session: Any = None,
        text: str = "",
        *,
        request: Any = None,
        session_key: str | None = None,
        source: str = "plugin",
        commit: bool = True,
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        ...

    async def simulate_moral_repair_update(
        self,
        event_or_session: Any = None,
        text: str = "",
        *,
        request: Any = None,
        session_key: str | None = None,
        source: str = "plugin",
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        ...

    async def reset_moral_repair_state(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> bool:
        ...


@runtime_checkable
class LifelikeLearningServiceProtocol(EmotionServiceProtocol, Protocol):
    lifelike_learning_schema_version: str

    async def get_lifelike_learning_snapshot(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
        exposure: str = "plugin_safe",
        include_prompt_fragment: bool = False,
    ) -> dict[str, Any]:
        ...

    async def get_lifelike_initiative_policy(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        ...

    async def get_lifelike_prompt_fragment(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> str:
        ...

    async def observe_lifelike_text(
        self,
        event_or_session: Any = None,
        text: str = "",
        *,
        request: Any = None,
        session_key: str | None = None,
        source: str = "plugin",
        commit: bool = True,
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        ...

    async def simulate_lifelike_update(
        self,
        event_or_session: Any = None,
        text: str = "",
        *,
        request: Any = None,
        session_key: str | None = None,
        source: str = "plugin",
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        ...

    async def reset_lifelike_learning_state(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> bool:
        ...


@runtime_checkable
class PersonalityDriftServiceProtocol(EmotionServiceProtocol, Protocol):
    personality_drift_schema_version: str

    async def get_personality_drift_snapshot(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
        exposure: str = "plugin_safe",
        include_prompt_fragment: bool = False,
    ) -> dict[str, Any]:
        ...

    async def get_personality_drift_values(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> dict[str, float]:
        ...

    async def get_personality_drift_prompt_fragment(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> str:
        ...

    async def observe_personality_drift_event(
        self,
        event_or_session: Any = None,
        text: str = "",
        *,
        request: Any = None,
        session_key: str | None = None,
        source: str = "plugin",
        trait_impulses: dict[str, float] | None = None,
        intensity: float | None = None,
        reliability: float | None = None,
        relationship_importance: float | None = None,
        commit: bool = True,
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        ...

    async def simulate_personality_drift_update(
        self,
        event_or_session: Any = None,
        text: str = "",
        *,
        request: Any = None,
        session_key: str | None = None,
        source: str = "plugin",
        trait_impulses: dict[str, float] | None = None,
        intensity: float | None = None,
        reliability: float | None = None,
        relationship_importance: float | None = None,
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        ...

    async def reset_personality_drift_state(
        self,
        event_or_session: Any = None,
        *,
        request: Any = None,
        session_key: str | None = None,
    ) -> bool:
        ...


def get_emotion_service(context: Any) -> EmotionServiceProtocol | None:
    """Return the activated emotion service plugin from an AstrBot Context."""
    getter = getattr(context, "get_registered_star", None)
    if not callable(getter):
        return None
    metadata = getter(PLUGIN_NAME)
    if not metadata or not getattr(metadata, "activated", True):
        return None
    plugin = getattr(metadata, "star_cls", None)
    required = (
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
    )
    expected_versions = {
        "emotion_api_version": EMOTION_API_VERSION,
        "emotion_schema_version": EMOTION_SCHEMA_VERSION,
        "emotion_memory_schema_version": EMOTION_MEMORY_SCHEMA_VERSION,
        "personality_profile_schema_version": PERSONALITY_PROFILE_SCHEMA_VERSION,
        "psychological_screening_schema_version": PSYCHOLOGICAL_SCREENING_SCHEMA_VERSION,
        "integrated_self_schema_version": INTEGRATED_SELF_SCHEMA_VERSION,
        "lifelike_learning_schema_version": LIFELIKE_LEARNING_SCHEMA_VERSION,
        "personality_drift_schema_version": PERSONALITY_DRIFT_SCHEMA_VERSION,
    }
    if (
        plugin
        and _has_expected_public_versions(plugin, expected_versions)
        and all(callable(getattr(plugin, name, None)) for name in required)
    ):
        return plugin
    return None


def get_humanlike_service(context: Any) -> HumanlikeStateServiceProtocol | None:
    """Return the activated optional humanlike-state service if available."""
    plugin = get_emotion_service(context)
    required = (
        "get_humanlike_snapshot",
        "get_humanlike_values",
        "get_humanlike_prompt_fragment",
        "observe_humanlike_text",
        "simulate_humanlike_update",
        "reset_humanlike_state",
    )
    if (
        plugin
        and getattr(plugin, "humanlike_state_schema_version", None) == HUMANLIKE_STATE_SCHEMA_VERSION
        and all(callable(getattr(plugin, name, None)) for name in required)
    ):
        return plugin
    return None


def get_moral_repair_service(context: Any) -> MoralRepairStateServiceProtocol | None:
    """Return the activated optional moral-repair service if available."""
    plugin = get_emotion_service(context)
    required = (
        "get_moral_repair_snapshot",
        "get_moral_repair_values",
        "get_moral_repair_prompt_fragment",
        "observe_moral_repair_text",
        "simulate_moral_repair_update",
        "reset_moral_repair_state",
    )
    if (
        plugin
        and getattr(plugin, "moral_repair_state_schema_version", None) == MORAL_REPAIR_STATE_SCHEMA_VERSION
        and all(callable(getattr(plugin, name, None)) for name in required)
    ):
        return plugin
    return None


def get_lifelike_learning_service(context: Any) -> LifelikeLearningServiceProtocol | None:
    """Return the activated lifelike-learning service if available."""
    plugin = get_emotion_service(context)
    required = (
        "get_lifelike_learning_snapshot",
        "get_lifelike_initiative_policy",
        "get_lifelike_prompt_fragment",
        "observe_lifelike_text",
        "simulate_lifelike_update",
        "reset_lifelike_learning_state",
    )
    if (
        plugin
        and getattr(plugin, "lifelike_learning_schema_version", None) == LIFELIKE_LEARNING_SCHEMA_VERSION
        and all(callable(getattr(plugin, name, None)) for name in required)
    ):
        return plugin
    return None


def get_personality_drift_service(context: Any) -> PersonalityDriftServiceProtocol | None:
    """Return the activated slow personality-drift service if available."""
    plugin = get_emotion_service(context)
    required = (
        "get_personality_drift_snapshot",
        "get_personality_drift_values",
        "get_personality_drift_prompt_fragment",
        "observe_personality_drift_event",
        "simulate_personality_drift_update",
        "reset_personality_drift_state",
    )
    if (
        plugin
        and getattr(plugin, "personality_drift_schema_version", None) == PERSONALITY_DRIFT_SCHEMA_VERSION
        and all(callable(getattr(plugin, name, None)) for name in required)
    ):
        return plugin
    return None
