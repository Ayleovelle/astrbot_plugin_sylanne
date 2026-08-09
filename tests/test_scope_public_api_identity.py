"""Public API must consume only the request-bound opaque subject in scoped mode."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sylanne_alpha.public_api import PublicAPI
from sylanne_alpha.scope_contracts import AuthenticatedSubject, RelationRef, RelationScope
from sylanne_alpha.scope_runtime import RelationRuntime, ScopeRuntimeRegistry
from tests.scope_fixtures import scopes


class _SenderTrapEvent:
    sender_id = "RAW-SENDER-MUST-NOT-BE-READ"
    user_id = "RAW-USER-MUST-NOT-BE-READ"
    unified_msg_origin = "RAW-UMO-MUST-NOT-BE-READ"
    session_id = "RAW-SESSION-MUST-NOT-BE-READ"

    def get_sender_id(self):
        raise AssertionError("scoped public API must not re-read sender identity")

    def get_sender_name(self):
        raise AssertionError("scoped public API must not re-read sender display name")


@pytest.mark.asyncio
async def test_scoped_identity_profile_trail_and_speaker_track_are_opaque(scopes) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    scope = scopes.bot_a_persona_a
    session = registry.exact_session(scope)
    subject = AuthenticatedSubject(
        relation_ref=RelationRef("relation_v1_public_api", scope.bot_ref),
        identity_quality="event_get_sender_id",
    )
    relation = RelationRuntime(
        RelationScope(
            bot_ref=scope.bot_ref,
            persona_ref=scope.persona_ref,
            relation_ref=subject.relation_ref,
            relation_generation=0,
        )
    )
    binding = SimpleNamespace(
        scope=scope,
        session_runtime=session,
        relation_runtime=relation,
        subject=subject,
    )

    class _Plugin:
        _scope_runtime_registry = registry
        config: dict[str, object] = {}

        def _bound_runtime(self):
            return binding

        def _session_key(self, _event=None, _session_key=""):
            return scope.storage_token

        def _observed_now(self):
            return 1.0

        async def get_emotion_snapshot(self, **_kwargs):
            return {"kind": "emotion"}

    api = PublicAPI(_Plugin())
    event = _SenderTrapEvent()

    assert api._agent_identity(event) == subject.relation_ref.token
    profile = await api.get_agent_identity_profile(event)
    trail = await api.get_agent_trail(event)
    speaker = await api._query_single_agent_state(
        "emotion",
        event,
        track="speaker",
    )

    rendered = repr((profile, trail, speaker))
    assert subject.relation_ref.token in rendered
    assert scope.storage_token in rendered
    assert "RAW-SENDER" not in rendered
    assert "RAW-UMO" not in rendered


@pytest.mark.asyncio
async def test_scoped_identity_surfaces_fail_closed_without_bound_relation(scopes) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    registry.exact_session(scopes.bot_a_persona_a)
    plugin = SimpleNamespace(
        _scope_runtime_registry=registry,
        _bound_runtime=lambda: None,
    )
    api = PublicAPI(plugin)

    assert api._agent_identity(_SenderTrapEvent()) == "unknown"
    assert await api.get_agent_identity_profile(_SenderTrapEvent()) == {
        "ok": False,
        "error": "scope_unavailable",
    }
    assert await api.get_agent_trail(_SenderTrapEvent()) == {
        "ok": False,
        "error": "scope_unavailable",
    }
