from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


PLUGIN_NAME = "astrbot_plugin_emotional_state"
EMOTION_API_VERSION = "1.0"
EMOTION_SCHEMA_VERSION = "astrbot.emotion_state.v2"
EMOTION_MEMORY_SCHEMA_VERSION = "astrbot.emotion_memory.v1"
PSYCHOLOGICAL_SCREENING_SCHEMA_VERSION = "astrbot.psychological_screening.v1"


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
    ) -> dict[str, Any]:
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
        "observe_emotion_text",
        "get_psychological_screening_snapshot",
        "get_psychological_screening_values",
        "observe_psychological_text",
        "simulate_psychological_update",
        "reset_psychological_screening_state",
        "simulate_emotion_update",
        "reset_emotion_state",
    )
    if plugin and all(callable(getattr(plugin, name, None)) for name in required):
        return plugin
    return None
