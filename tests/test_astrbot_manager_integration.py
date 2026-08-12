"""Tests for AstrBot ConversationManager and PersonaManager integration.

Verifies that Sylanne correctly detects, initializes, and syncs with
AstrBot's official manager APIs when available, and gracefully falls
back when they are not.
"""

from __future__ import annotations

import asyncio
import importlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from sylanne_alpha import transient_context
from sylanne_alpha.scope_contracts import ResolvedScope
from sylanne_alpha.scope_identity import PersonaSource
from sylanne_alpha.scope_repository import ScopeRepository
from sylanne_alpha.scope_runtime import ScopeRuntimeRegistry
from tests.scope_fixtures import scopes as build_scopes


class FakeConversationManager:
    """Mock AstrBot ConversationManager with the official API surface."""

    def __init__(self):
        self.conversations: dict[str, dict] = {}
        self._curr_ids: dict[str, str] = {}
        self._next_id = 1

    async def get_curr_conversation_id(self, uid: str) -> str | None:
        return self._curr_ids.get(uid)

    async def new_conversation(self, uid: str) -> str:
        cid = f"conv_{self._next_id}"
        self._next_id += 1
        self._curr_ids[uid] = cid
        self.conversations[cid] = {"uid": uid, "history": []}
        return cid

    async def get_conversation(self, uid: str, cid: str):
        data = self.conversations.get(cid)
        if data is None:
            return None
        return SimpleNamespace(history=data["history"])

    async def update_conversation(self, uid: str, cid: str, history=None, title=None):
        if cid in self.conversations:
            if history is not None:
                self.conversations[cid]["history"] = history


class FakePersonaManager:
    """Mock AstrBot PersonaManager with the official API surface."""

    def __init__(self):
        self.personas: dict[str, dict] = {}
        self.create_calls = 0
        self.update_calls = 0

    def get_persona(self, persona_id: str):
        return self.personas.get(persona_id)

    def create_persona(self, persona_id: str, system_prompt: str = "", **kwargs):
        self.create_calls += 1
        self.personas[persona_id] = {"system_prompt": system_prompt, **kwargs}

    def update_persona(self, persona_id: str, system_prompt: str = "", **kwargs):
        self.update_calls += 1
        if persona_id in self.personas:
            self.personas[persona_id]["system_prompt"] = system_prompt

    def get_all_personas(self):
        return list(self.personas.values())


class TestConversationManagerIntegration(unittest.TestCase):
    def _make_plugin(self, conv_mgr=None, persona_mgr=None, config=None):
        main = importlib.import_module("main")
        ctx = SimpleNamespace()
        if conv_mgr is not None:
            ctx.conversation_manager = conv_mgr
        if persona_mgr is not None:
            ctx.persona_manager = persona_mgr
        cfg = config or {}
        return main.EmotionalStatePlugin(context=ctx, config=cfg)

    def test_init_detects_conversation_manager_when_present(self):
        conv_mgr = FakeConversationManager()
        plugin = self._make_plugin(conv_mgr=conv_mgr)
        self.assertTrue(plugin._has_conversation_manager())
        self.assertIs(plugin._conv_mgr, conv_mgr)

    def test_init_returns_none_when_no_conversation_manager(self):
        plugin = self._make_plugin()
        self.assertFalse(plugin._has_conversation_manager())
        self.assertIsNone(plugin._conv_mgr)

    def test_init_detects_persona_manager_when_present(self):
        persona_mgr = FakePersonaManager()
        plugin = self._make_plugin(persona_mgr=persona_mgr)
        self.assertTrue(plugin._has_persona_manager())
        self.assertIs(plugin._persona_mgr, persona_mgr)

    def test_init_returns_none_when_no_persona_manager(self):
        plugin = self._make_plugin()
        self.assertFalse(plugin._has_persona_manager())
        self.assertIsNone(plugin._persona_mgr)

    def test_sync_user_message_creates_conversation_and_appends(self):
        conv_mgr = FakeConversationManager()
        plugin = self._make_plugin(conv_mgr=conv_mgr)
        asyncio.run(plugin._sync_message_to_conv_mgr("session:1", "user", "hello"))
        self.assertEqual(len(conv_mgr.conversations), 1)
        cid = conv_mgr._curr_ids["session:1"]
        history = conv_mgr.conversations[cid]["history"]
        self.assertEqual(len(history), 1)

    def test_sync_bot_message_appends_to_existing_conversation(self):
        conv_mgr = FakeConversationManager()
        plugin = self._make_plugin(conv_mgr=conv_mgr)
        asyncio.run(plugin._sync_message_to_conv_mgr("session:1", "user", "hello"))
        asyncio.run(plugin._sync_message_to_conv_mgr("session:1", "bot", "hi there"))
        cid = conv_mgr._curr_ids["session:1"]
        history = conv_mgr.conversations[cid]["history"]
        self.assertEqual(len(history), 2)

    def test_sync_does_not_crash_when_conv_mgr_is_none(self):
        plugin = self._make_plugin()
        asyncio.run(plugin._sync_message_to_conv_mgr("session:1", "user", "hello"))

    def test_sync_handles_conv_mgr_exception_gracefully(self):
        conv_mgr = FakeConversationManager()

        async def broken_get(uid):
            raise RuntimeError("simulated failure")

        conv_mgr.get_curr_conversation_id = broken_get
        plugin = self._make_plugin(conv_mgr=conv_mgr)
        # Should not raise
        asyncio.run(plugin._sync_message_to_conv_mgr("session:1", "user", "hello"))


class _FrameworkTextPart:
    def __init__(self, text: str) -> None:
        self.text = text
        self._no_save = False

    def mark_as_temp(self) -> "_FrameworkTextPart":
        self._no_save = True
        return self


def test_bound_request_never_creates_or_updates_persona_manager(monkeypatch):
    main = importlib.import_module("main")
    persona_mgr = FakePersonaManager()
    plugin = main.EmotionalStatePlugin(
        context=SimpleNamespace(persona_manager=persona_mgr), config={}
    )
    registry = ScopeRuntimeRegistry.for_test()
    plugin._scope_runtime_registry = registry
    scope = build_scopes.__wrapped__().bot_a_persona_a
    view = registry.issue_request_view(
        ResolvedScope(
            scope=scope,
            persona_source=PersonaSource(
                persona_id="manager-test",
                prompt="static persona",
                begin_dialogs=(),
                tools=None,
                skills=None,
                resolution_source="test",
            ),
            identity_quality="event_self_id",
            resolution_source="test",
            resolved_at_ms=1,
            private_scope_enabled=True,
            disabled_reason=None,
            turn_generation=1,
        ),
        subject=None,
        relation_runtime=None,
    )
    request = SimpleNamespace(
        system_prompt="static persona",
        prompt="actual user words",
        contexts=[{"role": "user", "content": "actual user words"}],
        extra_user_content_parts=[],
    )
    monkeypatch.setattr(transient_context, "_make_text_part", _FrameworkTextPart)

    with plugin._bind_request_runtime_view(view, request=request):
        assert plugin._set_transient_context_budget(request, 1_000) is True
        assert plugin._add_transient_context(
            request, "state", "present", "test", 20
        ) is True
        assert plugin._commit_transient_context(request) is True

    assert persona_mgr.personas == {}
    assert persona_mgr.create_calls == 0
    assert persona_mgr.update_calls == 0


class TestIntegrationFallback(unittest.TestCase):
    """Test that the plugin works correctly without managers (backwards compat)."""

    def test_full_lifecycle_without_managers(self):
        main = importlib.import_module("main")
        plugin = main.EmotionalStatePlugin(context=SimpleNamespace(), config={})
        repository = ScopeRepository(Path(tempfile.mkdtemp(prefix="manager-scope-")))
        plugin._scope_runtime_registry.bind_repository(repository)
        scope = repository.create_scope(
            build_scopes.__wrapped__().bot_a_persona_a,
            expected_absent=True,
        )
        with plugin._bind_runtime_for_scope(scope):
            result = asyncio.run(
                plugin.observe_request(
                    scope.storage_token,
                    text="test",
                    confidence=0.7,
                    flags=["safe"],
                    now=1.0,
                )
            )
            self.assertEqual(result["schema_version"], "sylanne.alpha.body.v1")
            result2 = asyncio.run(
                plugin.observe_response(
                    scope.storage_token,
                    text="reply",
                    confidence=0.8,
                    flags=["safe"],
                    now=2.0,
                )
            )
        self.assertGreater(result2["turns"], result["turns"])


if __name__ == "__main__":
    unittest.main()
