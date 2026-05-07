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
PSYCHOLOGICAL_SCREENING_SCHEMA_VERSION = "astrbot.psychological_screening.v1"
HUMANLIKE_STATE_SCHEMA_VERSION = "astrbot.humanlike_state.v1"
MORAL_REPAIR_STATE_SCHEMA_VERSION = "astrbot.moral_repair_state.v1"
PSYCHOLOGICAL_RISK_BOOLEAN_FIELDS = PUBLIC_RISK_BOOLEAN_FIELDS


def _has_expected_public_versions(plugin: Any, expected: dict[str, str]) -> bool:
    return all(getattr(plugin, name, None) == value for name, value in expected.items())


@runtime_checkable
class EmotionServiceProtocol(Protocol):
    emotion_api_version: str
    emotion_schema_version: str
    emotion_memory_schema_version: str
    psychological_screening_schema_version: str

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
    )
    expected_versions = {
        "emotion_api_version": EMOTION_API_VERSION,
        "emotion_schema_version": EMOTION_SCHEMA_VERSION,
        "emotion_memory_schema_version": EMOTION_MEMORY_SCHEMA_VERSION,
        "psychological_screening_schema_version": PSYCHOLOGICAL_SCREENING_SCHEMA_VERSION,
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
