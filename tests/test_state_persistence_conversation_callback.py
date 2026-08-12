from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from sylanne_alpha.plugin_services import PluginServices
from sylanne_alpha.state_persistence import StatePersistence


class _FakeConversationManager:
    def __init__(self) -> None:
        self.session_deleted_callback: Any = None

    def register_on_session_deleted(self, callback: Any) -> None:
        self.session_deleted_callback = callback

    async def delete_session(self, umo: str) -> None:
        assert self.session_deleted_callback is not None
        await self.session_deleted_callback(umo)


class _RecordingRegistry:
    def __init__(self) -> None:
        self.live_probes: list[object] = []
        self.releases: list[object] = []

    def is_live_session(self, scope: object) -> bool:
        self.live_probes.append(scope)
        return True

    def release_session(self, scope: object) -> None:
        self.releases.append(scope)


def test_constructed_persistence_registers_conversation_manager_callback() -> None:
    """A normally constructed persistence instance discovers the host callback."""
    manager = _FakeConversationManager()
    plugin = SimpleNamespace(
        _config={},
        context=SimpleNamespace(conversation_manager=manager),
    )

    persistence = StatePersistence(plugin)

    assert persistence.init_conversation_manager() is manager
    assert manager.session_deleted_callback is not None


@pytest.mark.asyncio
async def test_registered_callback_is_awaitable_and_raw_umo_releases_no_scope() -> None:
    manager = _FakeConversationManager()
    registry = _RecordingRegistry()
    persistence = object.__new__(StatePersistence)
    persistence._p = SimpleNamespace(
        _scope_runtime_registry=registry,
    )
    persistence._services = PluginServices(
        context=SimpleNamespace(conversation_manager=manager)
    )

    assert persistence.init_conversation_manager() is manager
    await manager.delete_session("aiocqhttp:group:123")

    assert registry.live_probes == []
    assert registry.releases == []


class _RecordingStore:
    def __init__(self) -> None:
        self.releases: list[str] = []

    def release_session(self, session_key: str) -> None:
        self.releases.append(session_key)


class _RecordingThroat:
    def __init__(self) -> None:
        self.bumped: list[tuple[str, object | None]] = []
        self.submitted: list[tuple[str, str]] = []

    def bump_epoch(self, session_key: str, *, occupant: object | None) -> None:
        self.bumped.append((session_key, occupant))

    def submit(
        self,
        session_key: str,
        operation: Any,
        *,
        kind: str,
        state: object | None,
    ) -> None:
        del operation, state
        self.submitted.append((session_key, kind))


@pytest.mark.asyncio
async def test_registered_callback_preserves_legacy_sync_cleanup() -> None:
    manager = _FakeConversationManager()
    store = _RecordingStore()
    throat = _RecordingThroat()
    cleaned_timers: list[str] = []
    persistence = object.__new__(StatePersistence)
    persistence._p = SimpleNamespace(
        _store=store,
    )
    persistence._services = PluginServices(
        context=SimpleNamespace(conversation_manager=manager)
    )
    persistence._throat = throat
    persistence._current_memory_occupant = lambda _session_key: None
    persistence._cleanup_pending_timers = cleaned_timers.append

    assert persistence.init_conversation_manager() is manager
    await manager.delete_session("legacy-session")

    assert store.releases == ["legacy-session"]
    assert throat.bumped == [("legacy-session", None)]
    assert cleaned_timers == ["legacy-session"]
    assert throat.submitted == [("legacy-session", "delete")]
