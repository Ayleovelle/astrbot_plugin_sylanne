"""Central, fail-closed provider selection for Sylanne auxiliary work.

The router deliberately depends on only the provider-management subset exposed
by AstrBot 4.26.5's ``Context``.  It does not import AstrBot implementation
classes, so its precedence and type-safety rules remain cheap to unit test.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Protocol


class ProviderFeature(str, Enum):
    """Text capabilities that may own an advanced provider override."""

    ASSESSOR = "assessor"
    MAIN_ASSESSOR = "main_assessor"
    LIFE = "life"
    RELATIONSHIP = "relationship"
    QZONE = "qzone"
    TRANSCRIPTION = "transcription"


@dataclass(frozen=True, slots=True)
class ProviderResolution:
    """A provider choice plus a stable explanation for UI and telemetry."""

    provider: Any | None
    provider_id: str
    mode: str
    reason: str
    explicit_invalid: bool = False


class ProviderContext(Protocol):
    """AstrBot v4.26.5 provider APIs consumed by the router."""

    def get_provider_by_id(self, provider_id: str) -> Any | Awaitable[Any]: ...

    def get_current_chat_provider_id(self, umo: str) -> str | Awaitable[str]: ...

    def get_using_provider(self, umo: str | None = None) -> Any | Awaitable[Any]: ...

    def get_all_providers(self) -> list[Any] | Awaitable[list[Any]]: ...

    def get_all_embedding_providers(self) -> list[Any] | Awaitable[list[Any]]: ...


TextProviderContext = ProviderContext
MultimodalDetector = Callable[[Any], bool | Awaitable[bool]]


# Each entry is (raw configuration key, reported mode).  The hidden aliases
# keep older installs working, but no legacy enable boolean is consulted here.
_FEATURE_PROVIDER_KEYS: Mapping[
    ProviderFeature, tuple[tuple[str, str], ...]
] = MappingProxyType(
    {
        ProviderFeature.ASSESSOR: (
            ("sylanne_alpha_assessor_provider_id", "legacy"),
            ("emotion_provider_id", "legacy"),
        ),
        ProviderFeature.MAIN_ASSESSOR: (
            ("sylanne_alpha_main_assessor_provider_id", "explicit"),
            ("sylanne_alpha_assessor_provider_id", "legacy"),
            ("emotion_provider_id", "legacy"),
        ),
        ProviderFeature.LIFE: (
            ("sylanne_alpha_life_simulation_provider_id", "explicit"),
        ),
        ProviderFeature.RELATIONSHIP: (
            ("sylanne_alpha_rel_register_provider_id", "explicit"),
            ("sylanne_alpha_assessor_provider_id", "legacy"),
            ("emotion_provider_id", "legacy"),
        ),
        ProviderFeature.QZONE: (
            ("sylanne_alpha_qzone_provider_id", "explicit"),
            ("sylanne_alpha_life_simulation_provider_id", "legacy"),
            ("sylanne_alpha_main_assessor_provider_id", "legacy"),
            ("sylanne_alpha_assessor_provider_id", "legacy"),
            ("emotion_provider_id", "legacy"),
        ),
        ProviderFeature.TRANSCRIPTION: (
            ("sylanne_alpha_transcription_provider_id", "explicit"),
        ),
    }
)


def _clean_id(value: Any) -> str:
    return str(value or "").strip()


def _coerce_feature(feature: ProviderFeature | str) -> ProviderFeature:
    try:
        return feature if isinstance(feature, ProviderFeature) else ProviderFeature(feature)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"unsupported provider feature: {feature!r}") from exc


async def _await_if_needed(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _accepts_keyword(signature: inspect.Signature, name: str) -> bool:
    """Return whether ``name`` can be passed without invoking the callable."""

    if any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    ):
        return True
    parameter = signature.parameters.get(name)
    return parameter is not None and parameter.kind in {
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    }


async def call_text_provider_once(
    provider: Any,
    *,
    prompt: str,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> Any:
    """Call ``provider.text_chat`` exactly once with signature-safe options.

    Some legacy AstrBot providers accept only ``prompt``.  Optional sampling
    arguments are therefore selected by local signature inspection before the
    call.  A ``TypeError`` raised *inside* a provider is never treated as a
    signature probe, because the request may already have reached a paid API.
    """

    call = getattr(provider, "text_chat", None)
    if not callable(call):
        raise TypeError("provider.text_chat is unavailable")

    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = {}
    try:
        signature = inspect.signature(call)
    except (TypeError, ValueError):
        # Unknown callable shape: the smallest historical AstrBot contract is
        # the safest single attempt.  Never probe by making a second call.
        kwargs["prompt"] = prompt
    else:
        prompt_parameter = signature.parameters.get("prompt")
        if (
            prompt_parameter is not None
            and prompt_parameter.kind is inspect.Parameter.POSITIONAL_ONLY
        ):
            args = (prompt,)
        else:
            kwargs["prompt"] = prompt
        if max_tokens is not None and _accepts_keyword(signature, "max_tokens"):
            kwargs["max_tokens"] = max_tokens
        if temperature is not None and _accepts_keyword(signature, "temperature"):
            kwargs["temperature"] = temperature

    return await _await_if_needed(call(*args, **kwargs))


def _provider_id(provider: Any) -> str:
    """Extract an AstrBot provider ID without assuming one adapter shape."""

    if provider is None:
        return ""
    meta_fn = getattr(provider, "meta", None)
    if callable(meta_fn):
        try:
            meta = meta_fn()
        except Exception:
            meta = None
        provider_id = _clean_id(getattr(meta, "id", ""))
        if provider_id:
            return provider_id
    config = getattr(provider, "provider_config", None)
    if isinstance(config, Mapping):
        provider_id = _clean_id(config.get("id") or config.get("provider_id"))
        if provider_id:
            return provider_id
    return _clean_id(
        getattr(provider, "provider_id", "") or getattr(provider, "id", "")
    )


async def _inventory(
    context: ProviderContext,
    getter_name: str,
) -> tuple[list[Any] | None, str]:
    getter = getattr(context, getter_name, None)
    if not callable(getter):
        return None, f"{getter_name}_unavailable"
    try:
        value = await _await_if_needed(getter())
        if value is None:
            return [], ""
        if isinstance(value, (str, bytes, Mapping)):
            return None, f"{getter_name}_invalid"
        return list(value), ""
    except Exception:
        return None, f"{getter_name}_error"


async def _lookup_provider(
    context: ProviderContext,
    provider_id: str,
) -> tuple[Any | None, str]:
    getter = getattr(context, "get_provider_by_id", None)
    if not callable(getter):
        return None, "provider_lookup_unavailable"
    try:
        provider = await _await_if_needed(getter(provider_id))
    except Exception:
        return None, "provider_lookup_error"
    if provider is None:
        return None, "provider_missing"
    return provider, ""


def _inventory_contains(provider: Any, inventory: list[Any]) -> bool:
    if any(candidate is provider for candidate in inventory):
        return True
    provider_id = _provider_id(provider)
    return bool(provider_id) and any(
        _provider_id(candidate) == provider_id for candidate in inventory
    )


async def _resolve_selected_chat_id(
    *,
    context: ProviderContext,
    provider_id: str,
    mode: str,
    reason: str,
) -> ProviderResolution:
    provider, error = await _lookup_provider(context, provider_id)
    if provider is None:
        return ProviderResolution(
            provider=None,
            provider_id=provider_id,
            mode="unavailable",
            reason=error,
            explicit_invalid=error == "provider_missing",
        )

    chat_inventory, inventory_error = await _inventory(context, "get_all_providers")
    if chat_inventory is None:
        return ProviderResolution(
            provider=None,
            provider_id=provider_id,
            mode="unavailable",
            reason=inventory_error,
        )
    if not _inventory_contains(provider, chat_inventory):
        return ProviderResolution(
            provider=None,
            provider_id=provider_id,
            mode="unavailable",
            reason="provider_type_mismatch",
            explicit_invalid=True,
        )
    return ProviderResolution(
        provider=provider,
        provider_id=provider_id,
        mode=mode,
        reason=reason,
    )


async def _using_provider(context: ProviderContext, umo: str | None) -> Any | None:
    getter = getattr(context, "get_using_provider", None)
    if not callable(getter):
        return None
    try:
        return await _await_if_needed(getter(umo=umo))
    except TypeError:
        try:
            return await _await_if_needed(getter(umo))
        except Exception:
            return None
    except Exception:
        return None


async def _current_chat_provider_id(context: ProviderContext, umo: str) -> str:
    getter = getattr(context, "get_current_chat_provider_id", None)
    if not callable(getter):
        return ""
    try:
        return _clean_id(await _await_if_needed(getter(umo=umo)))
    except TypeError:
        try:
            return _clean_id(await _await_if_needed(getter(umo)))
        except Exception:
            return ""
    except Exception:
        return ""


async def resolve_chat_provider(
    *,
    context: ProviderContext,
    umo: str | None = None,
) -> ProviderResolution:
    """Resolve the active AstrBot chat provider for a conversation."""

    normalized_umo = _clean_id(umo)
    if normalized_umo:
        current_id = await _current_chat_provider_id(context, normalized_umo)
        if current_id:
            return await _resolve_selected_chat_id(
                context=context,
                provider_id=current_id,
                mode="current_conversation",
                reason="astrbot_current_conversation",
            )

        provider = await _using_provider(context, normalized_umo)
        provider_id = _provider_id(provider)
        if provider is not None and provider_id:
            return ProviderResolution(
                provider=provider,
                provider_id=provider_id,
                mode="current_conversation",
                reason="astrbot_current_conversation",
            )

    provider = await _using_provider(context, None)
    provider_id = _provider_id(provider)
    if provider is not None and provider_id:
        return ProviderResolution(
            provider=provider,
            provider_id=provider_id,
            mode="default",
            reason="astrbot_global_default",
        )

    return ProviderResolution(
        provider=None,
        provider_id="",
        mode="unavailable",
        reason="no_chat_provider",
    )


async def resolve_auxiliary_provider(
    *,
    config: Mapping[str, Any],
    context: ProviderContext,
    umo: str | None = None,
) -> ProviderResolution:
    """Resolve the optional shared auxiliary model, inheriting chat when blank."""

    provider_id = _clean_id(config.get("sylanne_alpha_aux_provider_id"))
    if provider_id:
        return await _resolve_selected_chat_id(
            context=context,
            provider_id=provider_id,
            mode="auxiliary",
            reason="config:sylanne_alpha_aux_provider_id",
        )
    return await resolve_chat_provider(context=context, umo=umo)


async def resolve_text_provider(
    *,
    feature: ProviderFeature | str,
    config: Mapping[str, Any],
    context: ProviderContext,
    umo: str | None = None,
) -> ProviderResolution:
    """Resolve ``feature override -> auxiliary -> current chat``.

    The assessor's real fail-closed gate is enforced here.  Deprecated UI
    booleans are deliberately ignored so stale configuration can never enable
    a paid assessor call by itself.  Background assessment work additionally
    requires an explicit feature provider, the shared auxiliary provider, or
    the real assessor owner gate before it may inherit the chat provider.  This
    keeps an upgrade from silently creating new paid requests.
    """

    resolved_feature = _coerce_feature(feature)
    if (
        resolved_feature is ProviderFeature.ASSESSOR
        and config.get("sylanne_alpha_assessor_llm_enabled") is not True
    ):
        return ProviderResolution(
            provider=None,
            provider_id="",
            mode="disabled",
            reason="assessor_disabled",
        )

    feature_keys = _FEATURE_PROVIDER_KEYS[resolved_feature]
    if resolved_feature in {
        ProviderFeature.MAIN_ASSESSOR,
        ProviderFeature.RELATIONSHIP,
    }:
        has_feature_override = any(
            _clean_id(config.get(key)) for key, _mode in feature_keys
        )
        background_opted_in = bool(
            has_feature_override
            or _clean_id(config.get("sylanne_alpha_aux_provider_id"))
            or config.get("sylanne_alpha_assessor_llm_enabled") is True
        )
        if not background_opted_in:
            return ProviderResolution(
                provider=None,
                provider_id="",
                mode="disabled",
                reason="background_assessment_disabled",
            )

    for key, mode in feature_keys:
        provider_id = _clean_id(config.get(key))
        if provider_id:
            return await _resolve_selected_chat_id(
                context=context,
                provider_id=provider_id,
                mode=mode,
                reason=f"config:{key}",
            )

    return await resolve_auxiliary_provider(
        config=config,
        context=context,
        umo=umo,
    )


async def resolve_embedding_provider(
    *,
    config: Mapping[str, Any],
    context: ProviderContext,
) -> ProviderResolution:
    """Resolve only from AstrBot's dedicated embedding-provider inventory."""

    selected_id = _clean_id(
        config.get("sylanne_alpha_embedding_memory_provider_id")
    )
    providers, inventory_error = await _inventory(
        context,
        "get_all_embedding_providers",
    )
    if providers is None:
        return ProviderResolution(
            provider=None,
            provider_id=selected_id,
            mode="unavailable",
            reason=inventory_error.replace(
                "get_all_embedding_providers", "embedding_inventory"
            ),
        )

    if selected_id:
        for provider in providers:
            if _provider_id(provider) == selected_id:
                return ProviderResolution(
                    provider=provider,
                    provider_id=selected_id,
                    mode="explicit",
                    reason="config:sylanne_alpha_embedding_memory_provider_id",
                )
        return ProviderResolution(
            provider=None,
            provider_id=selected_id,
            mode="unavailable",
            reason="embedding_provider_missing",
            explicit_invalid=True,
        )

    if not providers:
        return ProviderResolution(
            provider=None,
            provider_id="",
            mode="disabled",
            reason="no_embedding_provider",
        )
    if len(providers) == 1:
        provider = providers[0]
        return ProviderResolution(
            provider=provider,
            provider_id=_provider_id(provider),
            mode="auto",
            reason="single_embedding_provider",
        )
    return ProviderResolution(
        provider=None,
        provider_id="",
        mode="selection_required",
        reason="multiple_embedding_providers",
    )


async def _detector_matches(
    detector: MultimodalDetector,
    provider: Any,
) -> tuple[bool, bool]:
    try:
        return bool(await _await_if_needed(detector(provider))), False
    except Exception:
        return False, True


async def resolve_transcription_provider(
    *,
    config: Mapping[str, Any],
    context: ProviderContext,
    multimodal_detector: MultimodalDetector | None,
    umo: str | None = None,
) -> ProviderResolution:
    """Resolve image transcription without inferring capability from names.

    A transcription-specific override is authoritative.  Automatic selection
    requires the caller's existing capability detector callback; the router
    intentionally contains no model-name or adapter-name heuristics.
    """

    explicit_id = _clean_id(config.get("sylanne_alpha_transcription_provider_id"))
    if explicit_id:
        return await _resolve_selected_chat_id(
            context=context,
            provider_id=explicit_id,
            mode="explicit",
            reason="config:sylanne_alpha_transcription_provider_id",
        )

    if multimodal_detector is None:
        return ProviderResolution(
            provider=None,
            provider_id="",
            mode="unavailable",
            reason="capability_detector_unavailable",
        )

    providers, inventory_error = await _inventory(context, "get_all_providers")
    if providers is None:
        return ProviderResolution(
            provider=None,
            provider_id="",
            mode="unavailable",
            reason=inventory_error.replace("get_all_providers", "chat_inventory"),
        )

    candidates: list[tuple[Any, str, str]] = []
    auxiliary_id = _clean_id(config.get("sylanne_alpha_aux_provider_id"))
    if auxiliary_id:
        auxiliary = await _resolve_selected_chat_id(
            context=context,
            provider_id=auxiliary_id,
            mode="auxiliary",
            reason="config:sylanne_alpha_aux_provider_id",
        )
        if auxiliary.provider is not None:
            candidates.append((auxiliary.provider, "auxiliary", auxiliary.reason))

    chat = await resolve_chat_provider(context=context, umo=umo)
    if chat.provider is not None:
        candidates.append((chat.provider, chat.mode, chat.reason))

    candidates.extend(
        (provider, "auto", "first_multimodal_provider") for provider in providers
    )

    seen: set[tuple[str, int]] = set()
    detector_failed = False
    for provider, mode, reason in candidates:
        identity = (_provider_id(provider), id(provider))
        if identity in seen:
            continue
        seen.add(identity)
        matches, failed = await _detector_matches(multimodal_detector, provider)
        detector_failed = detector_failed or failed
        if matches:
            return ProviderResolution(
                provider=provider,
                provider_id=_provider_id(provider),
                mode=mode,
                reason=reason,
            )

    return ProviderResolution(
        provider=None,
        provider_id="",
        mode="unavailable",
        reason=(
            "capability_detector_error"
            if detector_failed
            else "no_multimodal_provider"
        ),
    )


__all__ = [
    "MultimodalDetector",
    "ProviderContext",
    "ProviderFeature",
    "ProviderResolution",
    "TextProviderContext",
    "call_text_provider_once",
    "resolve_auxiliary_provider",
    "resolve_chat_provider",
    "resolve_embedding_provider",
    "resolve_text_provider",
    "resolve_transcription_provider",
]
