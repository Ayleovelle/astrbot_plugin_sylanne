"""Provider routing policy tests.

These tests keep AstrBot itself out of the unit-test boundary.  The fake context
implements the small subset of the v4.26.5 ``Context`` provider API consumed by
the router.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from sylanne_alpha.provider_routing import (
    ProviderFeature,
    resolve_auxiliary_provider,
    resolve_chat_provider,
    resolve_embedding_provider,
    resolve_text_provider,
    resolve_transcription_provider,
)


@dataclass(frozen=True)
class _Meta:
    id: str


@dataclass(frozen=True)
class _Provider:
    provider_id: str
    provider_type: str = "chat"
    multimodal: bool = False

    def meta(self) -> _Meta:
        return _Meta(id=self.provider_id)


class _FakeContext:
    def __init__(
        self,
        provider_ids: tuple[str, ...] = (),
        *,
        current_by_umo: dict[str, str] | None = None,
        default_id: str = "",
        lookup_error_ids: tuple[str, ...] = (),
        embedding_ids: tuple[str, ...] = (),
        multimodal_ids: tuple[str, ...] = (),
        inventory_error: bool = False,
    ) -> None:
        self.providers = {
            provider_id: _Provider(
                provider_id,
                multimodal=provider_id in multimodal_ids,
            )
            for provider_id in provider_ids
        }
        self.embedding_providers = {
            provider_id: _Provider(provider_id, provider_type="embedding")
            for provider_id in embedding_ids
        }
        self.current_by_umo = current_by_umo or {}
        self.default_id = default_id
        self.lookup_error_ids = set(lookup_error_ids)
        self.inventory_error = inventory_error
        self.lookup_calls: list[str] = []
        self.current_calls: list[str] = []
        self.using_calls: list[str | None] = []

    def get_provider_by_id(self, provider_id: str) -> _Provider | None:
        self.lookup_calls.append(provider_id)
        if provider_id in self.lookup_error_ids:
            raise RuntimeError("provider registry unavailable")
        return self.providers.get(provider_id) or self.embedding_providers.get(provider_id)

    async def get_current_chat_provider_id(self, umo: str) -> str:
        self.current_calls.append(umo)
        return self.current_by_umo.get(umo, "")

    def get_using_provider(self, umo: str | None = None) -> _Provider | None:
        self.using_calls.append(umo)
        provider_id = self.current_by_umo.get(umo, "") if umo else self.default_id
        return self.providers.get(provider_id)

    def get_all_providers(self) -> list[_Provider]:
        if self.inventory_error:
            raise RuntimeError("chat inventory unavailable")
        return list(self.providers.values())

    def get_all_embedding_providers(self) -> list[_Provider]:
        if self.inventory_error:
            raise RuntimeError("embedding inventory unavailable")
        return list(self.embedding_providers.values())


def _resolve_text(
    *,
    feature: ProviderFeature | str,
    config: dict[str, Any],
    context: _FakeContext,
    umo: str | None = "qq:friend:1",
):
    return asyncio.run(
        resolve_text_provider(
            feature=feature,
            config=config,
            context=context,
            umo=umo,
        )
    )


def test_chat_route_is_the_current_conversation_provider() -> None:
    context = _FakeContext(
        ("current", "default"),
        current_by_umo={"qq:friend:1": "current"},
        default_id="default",
    )

    resolved = asyncio.run(resolve_chat_provider(context=context, umo="qq:friend:1"))

    assert resolved.provider is context.providers["current"]
    assert resolved.provider_id == "current"
    assert resolved.mode == "current_conversation"


def test_auxiliary_route_prefers_explicit_then_inherits_chat() -> None:
    context = _FakeContext(
        ("aux", "current"),
        current_by_umo={"qq:friend:1": "current"},
    )

    explicit = asyncio.run(
        resolve_auxiliary_provider(
            config={"sylanne_alpha_aux_provider_id": " aux "},
            context=context,
            umo="qq:friend:1",
        )
    )
    inherited = asyncio.run(
        resolve_auxiliary_provider(
            config={"sylanne_alpha_aux_provider_id": "  "},
            context=context,
            umo="qq:friend:1",
        )
    )

    assert (explicit.provider_id, explicit.mode) == ("aux", "auxiliary")
    assert (inherited.provider_id, inherited.mode) == (
        "current",
        "current_conversation",
    )


def test_text_routes_reject_an_embedding_provider_id() -> None:
    context = _FakeContext(embedding_ids=("embedding-only",))

    resolved = _resolve_text(
        feature=ProviderFeature.LIFE,
        config={"sylanne_alpha_life_simulation_provider_id": "embedding-only"},
        context=context,
    )

    assert resolved.provider is None
    assert resolved.provider_id == "embedding-only"
    assert resolved.mode == "unavailable"
    assert resolved.reason == "provider_type_mismatch"
    assert resolved.explicit_invalid is True


@pytest.mark.parametrize(
    ("feature", "config", "expected", "expected_mode"),
    [
        (
            ProviderFeature.LIFE,
            {"sylanne_alpha_life_simulation_provider_id": "life"},
            "life",
            "explicit",
        ),
        (
            ProviderFeature.LIFE,
            {"sylanne_alpha_aux_provider_id": "aux"},
            "aux",
            "auxiliary",
        ),
        (
            ProviderFeature.RELATIONSHIP,
            {"emotion_provider_id": "legacy"},
            "legacy",
            "legacy",
        ),
        (
            ProviderFeature.QZONE,
            {
                "sylanne_alpha_life_simulation_provider_id": "life",
                "sylanne_alpha_aux_provider_id": "aux",
            },
            "life",
            "legacy",
        ),
    ],
)
def test_text_provider_precedence(
    feature: ProviderFeature,
    config: dict[str, Any],
    expected: str,
    expected_mode: str,
) -> None:
    context = _FakeContext(("life", "aux", "legacy", "default"), default_id="default")

    resolved = _resolve_text(feature=feature, config=config, context=context)

    assert resolved.provider_id == expected
    assert resolved.provider is context.providers[expected]
    assert resolved.mode == expected_mode
    assert resolved.explicit_invalid is False


def test_first_nonblank_feature_override_wins_over_lower_priority_values() -> None:
    context = _FakeContext(("qzone", "life", "main", "legacy", "aux", "default"), default_id="default")
    config = {
        "sylanne_alpha_qzone_provider_id": "qzone",
        "sylanne_alpha_life_simulation_provider_id": "life",
        "sylanne_alpha_main_assessor_provider_id": "main",
        "emotion_provider_id": "legacy",
        "sylanne_alpha_aux_provider_id": "aux",
    }

    resolved = _resolve_text(feature=ProviderFeature.QZONE, config=config, context=context)

    assert resolved.provider_id == "qzone"
    assert context.lookup_calls == ["qzone"]


def test_deleted_explicit_override_fails_closed_without_default_fallback() -> None:
    context = _FakeContext(("aux", "default"), default_id="default")
    config = {
        "sylanne_alpha_life_simulation_provider_id": "deleted",
        "sylanne_alpha_aux_provider_id": "aux",
    }

    resolved = _resolve_text(feature=ProviderFeature.LIFE, config=config, context=context)

    assert resolved.provider is None
    assert resolved.provider_id == "deleted"
    assert resolved.mode == "unavailable"
    assert resolved.explicit_invalid is True
    assert context.lookup_calls == ["deleted"]
    assert context.current_calls == []
    assert context.using_calls == []


def test_existing_manual_provider_id_is_resolved_normally() -> None:
    context = _FakeContext(("custom-manual",))

    resolved = _resolve_text(
        feature=ProviderFeature.LIFE,
        config={"sylanne_alpha_life_simulation_provider_id": " custom-manual "},
        context=context,
    )

    assert resolved.provider is context.providers["custom-manual"]
    assert resolved.provider_id == "custom-manual"
    assert resolved.mode == "explicit"


def test_invalid_auxiliary_provider_fails_closed() -> None:
    context = _FakeContext(("current",), current_by_umo={"qq:friend:1": "current"})

    resolved = _resolve_text(
        feature=ProviderFeature.LIFE,
        config={"sylanne_alpha_aux_provider_id": "deleted-aux"},
        context=context,
    )

    assert resolved.provider is None
    assert resolved.provider_id == "deleted-aux"
    assert resolved.explicit_invalid is True
    assert context.current_calls == []


def test_event_bound_text_work_uses_current_conversation_provider() -> None:
    context = _FakeContext(("current", "default"), current_by_umo={"qq:friend:1": "current"}, default_id="default")

    resolved = _resolve_text(feature=ProviderFeature.LIFE, config={}, context=context)

    assert resolved.provider is context.providers["current"]
    assert resolved.provider_id == "current"
    assert resolved.mode == "current_conversation"
    assert context.current_calls == ["qq:friend:1"]


def test_background_text_work_uses_global_default_provider() -> None:
    context = _FakeContext(("default",), default_id="default")

    resolved = _resolve_text(feature=ProviderFeature.LIFE, config={}, context=context, umo=None)

    assert resolved.provider is context.providers["default"]
    assert resolved.provider_id == "default"
    assert resolved.mode == "default"
    assert context.using_calls == [None]


def test_assessor_is_disabled_unless_real_fail_closed_gate_is_true() -> None:
    context = _FakeContext(("aux", "default"), default_id="default")

    resolved = _resolve_text(
        feature=ProviderFeature.ASSESSOR,
        config={
            "sylanne_alpha_fast_assessor_enabled": True,
            "sylanne_alpha_aux_provider_id": "aux",
        },
        context=context,
    )

    assert resolved.provider is None
    assert resolved.mode == "disabled"
    assert resolved.reason == "assessor_disabled"
    assert context.lookup_calls == []


def test_removed_fast_provider_key_is_ignored_in_favor_of_auxiliary() -> None:
    context = _FakeContext(("fast-page", "aux"))
    config = {
        "sylanne_alpha_assessor_llm_enabled": True,
        "sylanne_alpha_fast_assessor_provider_id": "fast-page",
        "sylanne_alpha_aux_provider_id": "aux",
    }

    resolved = _resolve_text(feature=ProviderFeature.ASSESSOR, config=config, context=context)

    assert resolved.provider is context.providers["aux"]
    assert resolved.provider_id == "aux"
    assert resolved.mode == "auxiliary"


@pytest.mark.parametrize(
    "feature",
    [ProviderFeature.MAIN_ASSESSOR, ProviderFeature.RELATIONSHIP],
)
def test_background_assessment_does_not_inherit_chat_without_owner_opt_in(
    feature: ProviderFeature,
) -> None:
    context = _FakeContext(("default",), default_id="default")

    resolved = _resolve_text(feature=feature, config={}, context=context, umo=None)

    assert resolved.provider is None
    assert resolved.mode == "disabled"
    assert resolved.reason == "background_assessment_disabled"
    assert context.using_calls == []


@pytest.mark.parametrize(
    "feature",
    [ProviderFeature.MAIN_ASSESSOR, ProviderFeature.RELATIONSHIP],
)
def test_explicit_shared_auxiliary_is_background_assessment_opt_in(
    feature: ProviderFeature,
) -> None:
    context = _FakeContext(("aux", "default"), default_id="default")

    resolved = _resolve_text(
        feature=feature,
        config={"sylanne_alpha_aux_provider_id": "aux"},
        context=context,
        umo=None,
    )

    assert resolved.provider is context.providers["aux"]
    assert resolved.mode == "auxiliary"


def test_explicit_lookup_exception_fails_closed_without_fallback() -> None:
    context = _FakeContext(
        ("broken", "aux", "default"),
        default_id="default",
        lookup_error_ids=("broken",),
    )
    config = {
        "sylanne_alpha_life_simulation_provider_id": "broken",
        "sylanne_alpha_aux_provider_id": "aux",
    }

    resolved = _resolve_text(feature=ProviderFeature.LIFE, config=config, context=context)

    assert resolved.provider is None
    assert resolved.provider_id == "broken"
    assert resolved.mode == "unavailable"
    assert resolved.reason == "provider_lookup_error"
    assert resolved.explicit_invalid is False
    assert context.lookup_calls == ["broken"]


def test_unknown_feature_is_rejected_before_provider_lookup() -> None:
    context = _FakeContext(("default",), default_id="default")

    with pytest.raises(ValueError, match="unsupported provider feature"):
        _resolve_text(feature="unknown", config={}, context=context)

    assert context.lookup_calls == []


# ---- Embedding inventory routing ----


def test_embedding_without_registered_provider_is_disabled() -> None:
    resolved = asyncio.run(resolve_embedding_provider(config={}, context=_FakeContext()))

    assert resolved.provider is None
    assert resolved.provider_id == ""
    assert resolved.mode == "disabled"
    assert resolved.reason == "no_embedding_provider"
    assert resolved.explicit_invalid is False


def test_single_embedding_provider_is_selected_automatically() -> None:
    context = _FakeContext(embedding_ids=("emb-1",))

    resolved = asyncio.run(resolve_embedding_provider(config={}, context=context))

    assert resolved.provider is context.embedding_providers["emb-1"]
    assert resolved.provider_id == "emb-1"
    assert resolved.mode == "auto"


def test_multiple_embedding_providers_require_an_explicit_selection() -> None:
    context = _FakeContext(embedding_ids=("emb-1", "emb-2"))

    resolved = asyncio.run(resolve_embedding_provider(config={}, context=context))

    assert resolved.provider is None
    assert resolved.provider_id == ""
    assert resolved.mode == "selection_required"


def test_explicit_embedding_provider_is_selected_from_embedding_inventory() -> None:
    context = _FakeContext(embedding_ids=("emb-1", "emb-2"))

    resolved = asyncio.run(
        resolve_embedding_provider(
            config={"sylanne_alpha_embedding_memory_provider_id": "emb-2"},
            context=context,
        )
    )

    assert resolved.provider is context.embedding_providers["emb-2"]
    assert resolved.provider_id == "emb-2"
    assert resolved.mode == "explicit"


def test_chat_provider_with_same_id_is_never_used_for_embedding() -> None:
    context = _FakeContext(("shared-id",))

    resolved = asyncio.run(
        resolve_embedding_provider(
            config={"sylanne_alpha_embedding_memory_provider_id": "shared-id"},
            context=context,
        )
    )

    assert resolved.provider is None
    assert resolved.provider_id == "shared-id"
    assert resolved.mode == "unavailable"
    assert resolved.explicit_invalid is True
    assert context.lookup_calls == []


def test_embedding_inventory_exception_is_bounded() -> None:
    resolved = asyncio.run(
        resolve_embedding_provider(
            config={},
            context=_FakeContext(inventory_error=True),
        )
    )

    assert resolved.provider is None
    assert resolved.mode == "unavailable"
    assert resolved.reason == "embedding_inventory_error"


# ---- Capability-aware transcription routing ----


def _is_multimodal(provider: _Provider) -> bool:
    return provider.multimodal


def test_explicit_transcription_override_does_not_need_name_or_capability_guessing() -> None:
    context = _FakeContext(("manual-vision",))

    resolved = asyncio.run(
        resolve_transcription_provider(
            config={"sylanne_alpha_transcription_provider_id": "manual-vision"},
            context=context,
            multimodal_detector=None,
        )
    )

    assert resolved.provider is context.providers["manual-vision"]
    assert resolved.provider_id == "manual-vision"
    assert resolved.mode == "explicit"


def test_deleted_transcription_override_fails_closed() -> None:
    context = _FakeContext(("auto-vision",), multimodal_ids=("auto-vision",))

    resolved = asyncio.run(
        resolve_transcription_provider(
            config={"sylanne_alpha_transcription_provider_id": "deleted"},
            context=context,
            multimodal_detector=_is_multimodal,
        )
    )

    assert resolved.provider is None
    assert resolved.provider_id == "deleted"
    assert resolved.mode == "unavailable"
    assert resolved.explicit_invalid is True


def test_automatic_transcription_uses_first_capability_match() -> None:
    context = _FakeContext(
        ("text-only", "vision"),
        multimodal_ids=("vision",),
    )

    resolved = asyncio.run(
        resolve_transcription_provider(
            config={},
            context=context,
            multimodal_detector=_is_multimodal,
        )
    )

    assert resolved.provider is context.providers["vision"]
    assert resolved.provider_id == "vision"
    assert resolved.mode == "auto"


def test_auxiliary_provider_is_preferred_only_when_capability_compatible() -> None:
    context = _FakeContext(
        ("aux", "vision"),
        multimodal_ids=("vision",),
    )

    resolved = asyncio.run(
        resolve_transcription_provider(
            config={"sylanne_alpha_aux_provider_id": "aux"},
            context=context,
            multimodal_detector=_is_multimodal,
        )
    )

    assert resolved.provider is context.providers["vision"]
    assert resolved.provider_id == "vision"
    assert resolved.mode == "auto"


def test_compatible_auxiliary_provider_precedes_other_automatic_matches() -> None:
    context = _FakeContext(
        ("vision", "aux"),
        multimodal_ids=("vision", "aux"),
    )

    resolved = asyncio.run(
        resolve_transcription_provider(
            config={"sylanne_alpha_aux_provider_id": "aux"},
            context=context,
            multimodal_detector=_is_multimodal,
        )
    )

    assert resolved.provider is context.providers["aux"]
    assert resolved.provider_id == "aux"
    assert resolved.mode == "auxiliary"


def test_transcription_awaits_async_capability_detector() -> None:
    context = _FakeContext(("vision",))

    async def detector(provider: _Provider) -> bool:
        return provider.provider_id == "vision"

    resolved = asyncio.run(
        resolve_transcription_provider(
            config={},
            context=context,
            multimodal_detector=detector,
        )
    )

    assert resolved.provider_id == "vision"
    assert resolved.mode == "auto"


def test_transcription_never_inferrs_capability_from_model_like_id() -> None:
    context = _FakeContext(("gpt-4o",))

    resolved = asyncio.run(
        resolve_transcription_provider(
            config={},
            context=context,
            multimodal_detector=_is_multimodal,
        )
    )

    assert resolved.provider is None
    assert resolved.mode == "unavailable"
    assert resolved.reason == "no_multimodal_provider"


def test_transcription_without_detector_is_unavailable_not_guessed() -> None:
    context = _FakeContext(("vision",), multimodal_ids=("vision",))

    resolved = asyncio.run(
        resolve_transcription_provider(
            config={},
            context=context,
            multimodal_detector=None,
        )
    )

    assert resolved.provider is None
    assert resolved.mode == "unavailable"
    assert resolved.reason == "capability_detector_unavailable"
