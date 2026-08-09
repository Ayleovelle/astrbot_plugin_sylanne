"""Contracts for the inactive, gateway-bound host construction path.

The active AstrBot ingress is switched atomically in a later task.  These
tests instead prove that the construction seam is complete now: once a caller
holds a frozen ``ScopedPersistenceGateway``, host, conversation, and memory
operations have no raw-key, KV, or legacy-file escape hatch.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sylanne_alpha.memory_system import MemorySystem
from sylanne_alpha.host import SylanneAlphaHost as PublicSylanneAlphaHost
from sylanne_alpha.scope_repository import ScopeRepository, ScopedPersistenceGateway
from sylanne_alpha.scoped_host_runtime import ScopedAlphaRuntime, ScopedHostRuntime
from sylanne_alpha.state_persistence import (
    LegacyWriteForbidden,
    StatePersistence,
    mark_dirty,
    swap_dirty,
)
from tests.scope_fixtures import scopes


class _LegacyKvTrapPlugin:
    """Fake plugin whose AstrBot KV API records every forbidden scoped touch."""

    def __init__(self) -> None:
        self._store = SimpleNamespace(memory_systems=None)
        self.kv_calls: list[tuple[str, str]] = []

    async def get_kv_data(self, key: str, default=None):  # noqa: ANN001
        self.kv_calls.append(("get", key))
        raise AssertionError("scoped persistence must not read AstrBot KV")

    async def put_kv_data(self, key: str, value):  # noqa: ANN001
        self.kv_calls.append(("put", key))
        raise AssertionError("scoped persistence must not write AstrBot KV")


def test_conv_manager_umo_resolution_never_requires_a_host_argument() -> None:
    """The adjacent legacy helper remains a pure origin lookup.

    This guards against a scoped-persistence early branch being inserted into
    the wrong same-shaped ``try`` block and referencing an out-of-scope host.
    """

    plugin = SimpleNamespace(
        _store=SimpleNamespace(
            memory_systems=None,
            session_origins={"transport-session": "platform:room:user"},
        )
    )
    state = StatePersistence(plugin)  # type: ignore[arg-type]

    assert state._resolve_conv_mgr_umo("transport-session") == "platform:room:user"
    assert state._resolve_conv_mgr_umo("unmapped-session") == "unmapped-session"


def test_legacy_write_boundary_rejects_scoped_hosts_but_keeps_legacy_hosts_live(
    tmp_path,
    scopes,
) -> None:
    """The later atomic switch has one exact, non-global legacy-write gate."""

    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    scoped = ScopedHostRuntime(
        ScopedPersistenceGateway(repository, active),
        root=tmp_path / "scoped-root",
        profile=None,
        pel_enabled=False,
    ).build_host()
    state = StatePersistence(_LegacyKvTrapPlugin())  # type: ignore[arg-type]

    with pytest.raises(LegacyWriteForbidden, match="read-only to legacy"):
        state.require_legacy_write_allowed(scoped.session_key, scoped)

    legacy = PublicSylanneAlphaHost(root=tmp_path / "legacy-root", session_key="legacy")
    state.require_legacy_write_allowed(legacy.session_key, legacy)


def test_scoped_runtime_rejects_foreign_host_and_buffer_identity_payloads(
    tmp_path,
    scopes,
) -> None:
    """A gateway authorizes one scope's bytes, not a foreign scope's identity."""

    repository = ScopeRepository(tmp_path / "scope-v1")
    left_scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    right_scope = repository.create_scope(scopes.bot_b_persona_a, expected_absent=True)
    left = ScopedHostRuntime(
        ScopedPersistenceGateway(repository, left_scope),
        root=tmp_path / "left-root",
        profile=None,
        pel_enabled=False,
    ).build_session()
    right = ScopedHostRuntime(
        ScopedPersistenceGateway(repository, right_scope),
        root=tmp_path / "right-root",
        profile=None,
        pel_enabled=False,
    ).build_session()

    with pytest.raises(ValueError, match="host snapshot token"):
        left.runtime.save_snapshot(left.host.session_key, right.host.snapshot())
    with pytest.raises(ValueError, match="buffer session token"):
        left.save_buffer(
            {
                "session_key": right.host.session_key,
                "messages": [],
                "last_activity": 0.0,
                "turn_count": 0,
                "last_flush_ts": 0.0,
            }
        )

    # Repository bytes can be externally malformed even though normal scoped
    # callers never receive a raw write primitive.  Boot must fence that same
    # foreign identity before AlphaKernel.restore can expose it.
    corrupt_scope = repository.create_scope(scopes.bot_a_persona_b, expected_absent=True)
    corrupt_gateway = ScopedPersistenceGateway(repository, corrupt_scope)
    corrupt_gateway.save("host", expected_generation=0, payload=right.host.snapshot())
    with pytest.raises(ValueError, match="host snapshot token"):
        ScopedHostRuntime(
            corrupt_gateway,
            root=tmp_path / "corrupt-root",
            profile=None,
            pel_enabled=False,
        ).build_host()

    corrupt_gateway.save(
        "conversation",
        expected_generation=0,
        payload={
            "session_key": right.host.session_key,
            "messages": [],
            "last_activity": 0.0,
            "turn_count": 0,
            "last_flush_ts": 0.0,
        },
    )
    with pytest.raises(ValueError, match="buffer session token"):
        ScopedAlphaRuntime(corrupt_gateway, None, False).load_buffer(
            corrupt_scope.storage_token
        )


def test_scoped_host_uses_the_same_public_lite_profile_as_legacy_construction(
    tmp_path,
    scopes,
) -> None:
    """Gateway construction must not bypass the public host's profile policy."""

    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    scoped = ScopedHostRuntime(
        ScopedPersistenceGateway(repository, active),
        root=tmp_path / "scoped-root",
        profile=None,
        pel_enabled=False,
    ).build_host()
    legacy = PublicSylanneAlphaHost(root=tmp_path / "legacy-root", session_key="legacy")

    assert type(scoped) is PublicSylanneAlphaHost
    assert scoped.profile is legacy.profile
    assert scoped.runtime._profile is legacy.profile


@pytest.mark.asyncio
async def test_gateway_built_session_keeps_host_buffer_and_memory_inside_scope_cas(
    tmp_path,
    scopes,
) -> None:
    """One frozen gateway is the sole authority across all three local stores."""

    repository = ScopeRepository(tmp_path / "scope-v1")
    left_scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    right_scope = repository.create_scope(scopes.bot_b_persona_a, expected_absent=True)
    assert left_scope.session_ref.token == right_scope.session_ref.token

    legacy_root = tmp_path / "legacy-alpha"
    left = ScopedHostRuntime(
        ScopedPersistenceGateway(repository, left_scope),
        root=legacy_root,
        profile=None,
        pel_enabled=False,
    ).build_session()
    right = ScopedHostRuntime(
        ScopedPersistenceGateway(repository, right_scope),
        root=legacy_root,
        profile=None,
        pel_enabled=False,
    ).build_session()

    left.host.on_request({"text": "left only", "now": 1.0})
    legacy_plugin = _LegacyKvTrapPlugin()
    legacy_state = StatePersistence(legacy_plugin)  # type: ignore[arg-type]
    try:
        # A dirty marker makes the compatibility implementation attempt its
        # normal KV write.  The scoped branch must bypass it completely.
        mark_dirty("session")
        await legacy_state.persist_kernel(left.host.session_key, left.host)

        buffer = {
            "session_key": left.host.session_key,
            "messages": [{"role": "user", "content": "left buffer"}],
            "last_activity": 1.0,
            "turn_count": 1,
            "last_flush_ts": 1.0,
        }
        await legacy_state.persist_buffer(left.host.session_key, left.host, buffer)
        assert await legacy_state.load_buffer_data(left.host.session_key, left.host) == buffer

        memory = MemorySystem()
        memory.write("left memory")
        assert await left.memory.save_memory(memory) is True

        assert repository.read_component(left_scope, "host") is not None
        conversation = repository.read_component(left_scope, "conversation")
        assert conversation is not None and conversation.payload == buffer
        persisted_memory = repository.read_component(left_scope, "memory")
        assert persisted_memory is not None
        assert (await left.memory.load_memory()).to_dict() == memory.to_dict()

        # Same transport token under another Bot still starts entirely blank.
        assert right.load_buffer() is None
        assert await right.memory.load_memory() is None
        assert right.host.kernel.turns == 0

        restarted = ScopedHostRuntime(
            ScopedPersistenceGateway(repository, left_scope),
            root=tmp_path / "other-legacy-root",
            profile=None,
            pel_enabled=False,
        ).build_session()
        assert restarted.host.kernel.turns == left.host.kernel.turns
        assert restarted.load_buffer() == buffer
        restored_memory = await restarted.memory.load_memory()
        assert restored_memory is not None and restored_memory.to_dict() == memory.to_dict()
    finally:
        # This test deliberately owns the global dirty marker it raised.
        swap_dirty()

    assert legacy_plugin.kv_calls == []
    assert list(legacy_root.rglob("*.alpha.json")) == []
    assert list(legacy_root.rglob("*.buffer.json")) == []


@pytest.mark.asyncio
async def test_state_persistence_rejects_raw_mismatched_token_for_scoped_host(
    tmp_path,
    scopes,
) -> None:
    """A raw transport-looking token cannot retarget a frozen host capability."""

    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    session = ScopedHostRuntime(
        ScopedPersistenceGateway(repository, active),
        root=tmp_path / "legacy-alpha",
        profile=None,
        pel_enabled=False,
    ).build_session()
    legacy_state = StatePersistence(_LegacyKvTrapPlugin())  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="frozen scope"):
        await legacy_state.persist_kernel("raw-transport-token", session.host)
    with pytest.raises(ValueError, match="frozen scope"):
        await legacy_state.persist_buffer("raw-transport-token", session.host, {})
    with pytest.raises(ValueError, match="frozen scope"):
        await legacy_state.load_buffer_data("raw-transport-token", session.host)
