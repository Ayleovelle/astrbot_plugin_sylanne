"""grey.4: third-party agent conversation-history fallback."""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, Iterator

import pytest

from main import EmotionalStatePlugin
from sylanne_alpha.session_state_store import SessionStateStore
from sylanne_alpha.state_persistence import StatePersistence


UMO = "aiocqhttp:FriendMessage:grey4"


def _role(entry: dict[str, Any]) -> str:
    role = str(entry.get("role", ""))
    return "user" if role == "user" else "assistant"


def _text(entry: dict[str, Any]) -> str:
    content = entry.get("content")
    if isinstance(content, list):
        return "".join(
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict)
        )
    return str(content or "")


class FakeConversationManager:
    """Faithful narrow fake: history is returned as a JSON string."""

    def __init__(self, *, fail_update: bool = False) -> None:
        self._curr_ids: dict[str, str] = {}
        self._content: dict[str, list[dict[str, Any]]] = {}
        self._next_id = 1
        self.fail_update = fail_update
        self.update_count = 0

    async def get_curr_conversation_id(self, umo: str) -> str | None:
        return self._curr_ids.get(umo)

    async def new_conversation(self, umo: str) -> str:
        cid = f"conv_{self._next_id}"
        self._next_id += 1
        self._curr_ids[umo] = cid
        self._content[cid] = []
        return cid

    async def get_conversation(
        self, umo: str, cid: str, create_if_not_exists: bool = False
    ) -> SimpleNamespace | None:
        del umo, create_if_not_exists
        await asyncio.sleep(0)
        if cid not in self._content:
            return None
        return SimpleNamespace(
            history=json.dumps(self._content[cid], ensure_ascii=False)
        )

    async def update_conversation(
        self,
        umo: str,
        cid: str | None = None,
        history: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        del umo, kwargs
        self.update_count += 1
        await asyncio.sleep(0)
        if self.fail_update:
            raise RuntimeError("simulated DB write failure")
        assert cid is not None
        json.dumps(history, ensure_ascii=False)
        self._content[cid] = list(history or [])

    def history(self, umo: str = UMO) -> list[dict[str, Any]]:
        cid = self._curr_ids.get(umo)
        return list(self._content.get(cid or "", []))


class BlockingConversationManager(FakeConversationManager):
    def __init__(self) -> None:
        super().__init__()
        self.first_update_started = asyncio.Event()
        self.allow_first_update = asyncio.Event()

    async def update_conversation(self, *args: Any, **kwargs: Any) -> None:
        if self.update_count == 0:
            self.first_update_started.set()
            await self.allow_first_update.wait()
        await super().update_conversation(*args, **kwargs)


class _Event:
    def __init__(
        self,
        *,
        session_key: str,
        user_text: str,
        stopped: bool = False,
    ) -> None:
        self.session_key = session_key
        self.user_text = user_text
        self.unified_msg_origin = UMO
        self._stopped = stopped
        self._extras: dict[str, Any] = {
            "provider_request": SimpleNamespace(
                conversation=object(), tool_calls_result=None
            )
        }

    def get_extra(self, key: str, default: Any = None) -> Any:
        return self._extras.get(key, default)

    def set_extra(self, key: str, value: Any) -> None:
        self._extras[key] = value

    def is_stopped(self) -> bool:
        return self._stopped


class _Runner:
    def done(self) -> bool:
        return True

    def was_aborted(self) -> bool:
        return False


@contextmanager
def _active_internal_runner(umo: str) -> Iterator[None]:
    from astrbot.core.pipeline.process_stage.follow_up import _ACTIVE_AGENT_RUNNERS

    sentinel = object()
    previous = _ACTIVE_AGENT_RUNNERS.get(umo, sentinel)
    _ACTIVE_AGENT_RUNNERS[umo] = _Runner()
    try:
        yield
    finally:
        if previous is sentinel:
            _ACTIVE_AGENT_RUNNERS.pop(umo, None)
        else:
            _ACTIVE_AGENT_RUNNERS[umo] = previous


class _Plugin:
    _framework_will_persist_this_turn = (
        EmotionalStatePlugin._framework_will_persist_this_turn
    )
    _agent_was_aborted = EmotionalStatePlugin._agent_was_aborted
    _agent_run_done = EmotionalStatePlugin._agent_run_done

    def __init__(self, manager: FakeConversationManager) -> None:
        self._conv_mgr = manager
        self._store = SessionStateStore()
        self._state_persistence = StatePersistence(self)

    def _has_conversation_manager(self) -> bool:
        return True

    def _text(self, event: _Event) -> str:
        return event.user_text

    def _session_key(self, event: _Event) -> str:
        return event.session_key

    async def _sync_turn_to_conv_mgr(
        self, session_key: str, user_text: str, assistant_text: str = ""
    ) -> bool:
        method = getattr(self._state_persistence, "sync_turn_to_conv_mgr", None)
        assert callable(method), "StatePersistence.sync_turn_to_conv_mgr is missing"
        return await method(session_key, user_text, assistant_text)


async def _backfill(plugin: _Plugin, event: _Event, response: Any) -> None:
    method = getattr(EmotionalStatePlugin, "_backfill_turn_if_framework_skips", None)
    assert callable(method), "EmotionalStatePlugin turn backfill endpoint is missing"
    await method(plugin, event, response)


def _map(plugin: _Plugin, session_key: str) -> None:
    plugin._store.session_origins.set(session_key, UMO)


def _assert_history(
    manager: FakeConversationManager, expected: list[tuple[str, str]]
) -> None:
    actual = [(_role(entry), _text(entry)) for entry in manager.history()]
    assert actual == expected


@pytest.mark.asyncio
async def test_third_party_success_backfills_atomic_user_assistant_turn() -> None:
    manager = FakeConversationManager()
    plugin = _Plugin(manager)
    event = _Event(session_key="third-party", user_text="在吗")
    _map(plugin, event.session_key)
    response = SimpleNamespace(role="assistant", completion_text="在呀")

    assert plugin._framework_will_persist_this_turn(event, response) is False
    await _backfill(plugin, event, response)

    _assert_history(manager, [("user", "在吗"), ("assistant", "在呀")])
    assert manager.update_count == 1


@pytest.mark.asyncio
async def test_internal_runner_remains_framework_only_writer() -> None:
    manager = FakeConversationManager()
    plugin = _Plugin(manager)
    event = _Event(session_key="internal", user_text="在吗")
    _map(plugin, event.session_key)
    response = SimpleNamespace(role="assistant", completion_text="在呀")

    with _active_internal_runner(UMO):
        assert plugin._framework_will_persist_this_turn(event, response) is True
        await _backfill(plugin, event, response)

    assert manager.history() == []
    assert manager.update_count == 0


@pytest.mark.asyncio
async def test_silent_and_stopped_turns_backfill_user_only() -> None:
    for stopped, completion in ((False, ""), (True, "不会发送")):
        manager = FakeConversationManager()
        plugin = _Plugin(manager)
        event = _Event(
            session_key=f"quiet-{stopped}", user_text="还在吗", stopped=stopped
        )
        _map(plugin, event.session_key)

        await _backfill(
            plugin,
            event,
            SimpleNamespace(role="assistant", completion_text=completion),
        )

        _assert_history(manager, [("user", "还在吗")])
        assert manager.update_count == 1


@pytest.mark.asyncio
async def test_db_failure_does_not_consume_turn_guard() -> None:
    manager = FakeConversationManager(fail_update=True)
    plugin = _Plugin(manager)
    event = _Event(session_key="retry", user_text="重试一下")
    _map(plugin, event.session_key)
    response = SimpleNamespace(role="assistant", completion_text="好")

    await _backfill(plugin, event, response)

    assert event.get_extra("_syl_turn_backfilled") is None
    assert event.get_extra("_syl_user_backfilled") is None

    manager.fail_update = False
    await _backfill(plugin, event, response)

    _assert_history(manager, [("user", "重试一下"), ("assistant", "好")])
    assert manager.update_count == 2


@pytest.mark.asyncio
async def test_two_session_keys_mapped_to_one_umo_do_not_lose_concurrent_turns() -> None:
    manager = FakeConversationManager()
    plugin = _Plugin(manager)
    first = _Event(session_key="sk-a", user_text="第一问")
    second = _Event(session_key="sk-b", user_text="第二问")
    _map(plugin, first.session_key)
    _map(plugin, second.session_key)

    await asyncio.gather(
        _backfill(
            plugin,
            first,
            SimpleNamespace(role="assistant", completion_text="第一答"),
        ),
        _backfill(
            plugin,
            second,
            SimpleNamespace(role="assistant", completion_text="第二答"),
        ),
    )

    history = [(_role(entry), _text(entry)) for entry in manager.history()]
    assert len(history) == 4
    assert history in (
        [
            ("user", "第一问"),
            ("assistant", "第一答"),
            ("user", "第二问"),
            ("assistant", "第二答"),
        ],
        [
            ("user", "第二问"),
            ("assistant", "第二答"),
            ("user", "第一问"),
            ("assistant", "第一答"),
        ],
    )
    assert manager.update_count == 2


@pytest.mark.asyncio
async def test_shared_umo_lock_is_released_with_its_last_session() -> None:
    manager = FakeConversationManager()
    plugin = _Plugin(manager)
    first_key = "lock-owner-a"
    second_key = "lock-owner-b"
    _map(plugin, first_key)
    _map(plugin, second_key)

    assert await plugin._sync_turn_to_conv_mgr(first_key, "一", "甲") is True
    assert await plugin._sync_turn_to_conv_mgr(second_key, "二", "乙") is True
    shared_lock = plugin._store.conv_sync_locks.get(UMO)
    assert shared_lock is not None

    plugin._store.release_session(first_key)
    assert plugin._store.conv_sync_locks.get(UMO) is shared_lock

    plugin._store.release_session(second_key)
    assert plugin._store.conv_sync_locks.has(UMO) is False


@pytest.mark.asyncio
async def test_unmapped_session_releases_its_fallback_lock() -> None:
    manager = FakeConversationManager()
    plugin = _Plugin(manager)
    session_key = "unmapped-lock-owner"

    assert await plugin._sync_turn_to_conv_mgr(session_key, "问", "答") is True
    assert plugin._store.conv_sync_locks.has(session_key) is True

    plugin._store.release_session(session_key)
    assert plugin._store.conv_sync_locks.has(session_key) is False


@pytest.mark.asyncio
async def test_waiter_keeps_same_umo_lock_during_session_release() -> None:
    manager = BlockingConversationManager()
    plugin = _Plugin(manager)
    first_key = "handoff-a"
    second_key = "handoff-b"
    _map(plugin, first_key)
    _map(plugin, second_key)
    original_lock: asyncio.Lock | None = None

    async def first_sync_then_release() -> None:
        assert await plugin._sync_turn_to_conv_mgr(first_key, "一", "甲") is True
        plugin._store.release_session(first_key)
        plugin._store.release_session(second_key)
        assert plugin._store.conv_sync_locks.get(UMO) is original_lock

    first_task = asyncio.create_task(first_sync_then_release())
    await manager.first_update_started.wait()
    original_lock = plugin._store.conv_sync_locks.get(UMO)
    assert original_lock is not None

    second_task = asyncio.create_task(
        plugin._sync_turn_to_conv_mgr(second_key, "二", "乙")
    )
    await asyncio.sleep(0)
    manager.allow_first_update.set()

    first_result, second_result = await asyncio.gather(first_task, second_task)
    assert first_result is None
    assert second_result is True
    assert plugin._store.conv_sync_locks.has(UMO) is False


@pytest.mark.asyncio
async def test_same_event_is_backfilled_only_once() -> None:
    manager = FakeConversationManager()
    plugin = _Plugin(manager)
    event = _Event(session_key="once", user_text="只写一次")
    _map(plugin, event.session_key)
    response = SimpleNamespace(role="assistant", completion_text="收到")

    await _backfill(plugin, event, response)
    await _backfill(plugin, event, response)

    _assert_history(manager, [("user", "只写一次"), ("assistant", "收到")])
    assert manager.update_count == 1
    assert event.get_extra("_syl_turn_backfilled") is True
    assert event.get_extra("_syl_user_backfilled") is True
