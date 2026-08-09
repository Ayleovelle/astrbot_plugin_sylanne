"""Tests for AstrBot ConversationManager and PersonaManager integration.

Verifies that Sylanne correctly detects, initializes, and syncs with
AstrBot's official manager APIs when available, and gracefully falls
back when they are not.
"""

from __future__ import annotations

import asyncio
import importlib
import unittest
from types import SimpleNamespace


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

    def get_persona(self, persona_id: str):
        return self.personas.get(persona_id)

    def create_persona(self, persona_id: str, system_prompt: str = "", **kwargs):
        self.personas[persona_id] = {"system_prompt": system_prompt, **kwargs}

    def update_persona(self, persona_id: str, system_prompt: str = "", **kwargs):
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


class TestPersonaManagerIntegration(unittest.TestCase):
    def _make_plugin(self, persona_mgr=None, config=None):
        main = importlib.import_module("main")
        ctx = SimpleNamespace()
        if persona_mgr is not None:
            ctx.persona_manager = persona_mgr
        cfg = config or {}
        return main.EmotionalStatePlugin(context=ctx, config=cfg)

    def test_sync_personality_creates_persona_entry(self):
        persona_mgr = FakePersonaManager()
        plugin = self._make_plugin(persona_mgr=persona_mgr)
        # Initialize a host so personality data is available
        asyncio.run(
            plugin.observe_request(
                "room:persona",
                text="test",
                confidence=0.7,
                flags=["safe"],
                now=1.0,
            )
        )
        # observe_request already triggers sync; check result
        self.assertGreater(len(persona_mgr.personas), 0)
        persona_id = list(persona_mgr.personas.keys())[0]
        self.assertIn(
            "Sylanne Personality State",
            persona_mgr.personas[persona_id]["system_prompt"],
        )

    def test_sync_personality_updates_existing_persona(self):
        persona_mgr = FakePersonaManager()
        plugin = self._make_plugin(persona_mgr=persona_mgr)
        asyncio.run(
            plugin.observe_request(
                "room:p2",
                text="test",
                confidence=0.7,
                flags=["safe"],
                now=1.0,
            )
        )
        count_after_first = len(persona_mgr.personas)
        # Second observe triggers another sync (update, not create)
        asyncio.run(
            plugin.observe_request(
                "room:p2",
                text="again",
                confidence=0.7,
                flags=["safe"],
                now=2.0,
            )
        )
        self.assertEqual(len(persona_mgr.personas), count_after_first)

    def test_sync_does_not_crash_when_persona_mgr_is_none(self):
        plugin = self._make_plugin()
        plugin._sync_personality_to_persona_mgr("room:x")

    def test_sync_does_not_crash_when_no_host(self):
        persona_mgr = FakePersonaManager()
        plugin = self._make_plugin(persona_mgr=persona_mgr)
        plugin._sync_personality_to_persona_mgr("nonexistent_session")
        self.assertEqual(len(persona_mgr.personas), 0)

    def test_observe_response_triggers_persona_sync(self):
        persona_mgr = FakePersonaManager()
        plugin = self._make_plugin(persona_mgr=persona_mgr)
        asyncio.run(
            plugin.observe_request(
                "room:resp",
                text="hi",
                confidence=0.7,
                flags=["safe"],
                now=1.0,
            )
        )
        persona_mgr.personas.clear()
        asyncio.run(
            plugin.observe_response(
                "room:resp",
                text="hello",
                confidence=0.8,
                flags=["safe"],
                now=2.0,
            )
        )
        self.assertGreater(len(persona_mgr.personas), 0)


class TestIntegrationFallback(unittest.TestCase):
    """Test that the plugin works correctly without managers (backwards compat)."""

    def test_full_lifecycle_without_managers(self):
        main = importlib.import_module("main")
        plugin = main.EmotionalStatePlugin(context=SimpleNamespace(), config={})
        result = asyncio.run(
            plugin.observe_request(
                "room:fallback",
                text="test",
                confidence=0.7,
                flags=["safe"],
                now=1.0,
            )
        )
        self.assertEqual(result["schema_version"], "sylanne.alpha.body.v1")
        result2 = asyncio.run(
            plugin.observe_response(
                "room:fallback",
                text="reply",
                confidence=0.8,
                flags=["safe"],
                now=2.0,
            )
        )
        self.assertGreater(result2["turns"], result["turns"])


if __name__ == "__main__":
    unittest.main()
