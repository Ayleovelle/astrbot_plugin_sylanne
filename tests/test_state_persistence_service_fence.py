from __future__ import annotations

import asyncio
import copy
import json
import tempfile
from types import SimpleNamespace
from typing import Any

from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost
from sylanne_alpha.memory_legacy_formats import quarantine_kv_key
from sylanne_alpha.memory_system import MemorySystem
from sylanne_alpha.plugin_services import PluginServices
from sylanne_alpha.session_state_store import SessionStateStore
from sylanne_alpha.state_persistence import (
    PENDING_DELETE_INDEX_KV_KEY,
    StatePersistence,
    mark_dirty,
)


class _Backend:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}
        self.calls: list[tuple[str, str]] = []

    async def get(self, key: str, default: Any = None) -> Any:
        self.calls.append(("get", key))
        return copy.deepcopy(self.values.get(key, default))

    async def put(self, key: str, value: Any) -> None:
        self.calls.append(("put", key))
        self.values[key] = copy.deepcopy(value)

    async def delete(self, key: str) -> None:
        self.calls.append(("delete", key))
        self.values.pop(key, None)


class _PluginWithoutKv:
    def __init__(self) -> None:
        self.config = {"sylanne_alpha_kernel_persist_debounce_seconds": 60.0}
        self._config = self.config
        self.context: Any = None
        self._store = SessionStateStore()
        self._hosts: dict[str, SylanneAlphaHost] = {}

    def _host(self, session_key: str) -> SylanneAlphaHost | None:
        return self._hosts.get(session_key)

    def _cfg(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def _cfg_bool(self, key: str, default: bool = False) -> bool:
        return bool(self.config.get(key, default))

    @staticmethod
    def _memory_system_has_content(memory: MemorySystem) -> bool:
        return bool(memory._l1 or memory._l2 or memory._l3_nodes or memory._l3_edges)


class _PluginWithDifferentKv(_PluginWithoutKv):
    def __init__(self, backend: _Backend) -> None:
        super().__init__()
        self._backend = backend

    async def get_kv_data(self, key: str, default: Any = None) -> Any:
        return await self._backend.get(key, default)

    async def put_kv_data(self, key: str, value: Any) -> None:
        await self._backend.put(key, value)

    async def delete_kv_data(self, key: str) -> None:
        await self._backend.delete(key)


class _LegacyShardKv:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}
        self.calls: list[tuple[str, str]] = []

    def get(self, key: str) -> Any:
        self.calls.append(("get", key))
        return copy.deepcopy(self.values.get(key))

    def set(self, key: str, value: Any) -> None:
        self.calls.append(("set", key))
        self.values[key] = copy.deepcopy(value)


class _PluginWithLegacyShardKv(_PluginWithoutKv):
    def __init__(self) -> None:
        super().__init__()
        self.kv = _LegacyShardKv()


class _ConversationManager:
    def __init__(self) -> None:
        self.callback: Any = None

    def register_on_session_deleted(self, callback: Any) -> None:
        self.callback = callback


def _services(backend: _Backend, *, context: Any = None) -> PluginServices:
    return PluginServices(
        config={"sylanne_alpha_kernel_persist_debounce_seconds": 60.0},
        context=context,
        get_kv_data=backend.get,
        put_kv_data=backend.put,
        delete_kv_data=backend.delete,
    )


def _partial_services(
    backend: _Backend,
    *,
    get: bool = True,
    put: bool = True,
    delete: bool = True,
) -> PluginServices:
    return PluginServices(
        config={"sylanne_alpha_kernel_persist_debounce_seconds": 60.0},
        get_kv_data=backend.get if get else None,
        put_kv_data=backend.put if put else None,
        delete_kv_data=backend.delete if delete else None,
    )


def _memory(text: str, session_key: str) -> MemorySystem:
    memory = MemorySystem()
    memory._hydrated = True
    memory.write_summary(text=text, source_turns=1, session_key=session_key)
    return memory


def _backend_bytes(backend: _Backend) -> bytes:
    return json.dumps(
        backend.values, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def test_explicit_services_fence_every_kv_operation_from_plugin_backend() -> None:
    async def go() -> None:
        plugin_backend = _Backend()
        service_backend = _Backend()
        plugin = _PluginWithDifferentKv(plugin_backend)
        persistence = StatePersistence(plugin, services=_services(service_backend))
        persistence._pending_delete_scan_done = True

        save_key = "sess:services-save"
        primary_key = persistence.sylanne_memory_kv_key(save_key)
        backup_key = persistence.sylanne_memory_backup_v2_kv_key(save_key)
        v2_blob = {"version": "2.0.0", "records": [{"text": "v2 archive"}]}
        service_backend.values[primary_key] = copy.deepcopy(v2_blob)
        await persistence.save_sylanne_memory_state(
            save_key, _memory("v3 replacement", save_key)
        )
        assert persistence._backup_blob_is_valid(service_backend.values.get(backup_key))
        assert service_backend.values[backup_key]["data"] == v2_blob
        assert service_backend.values[primary_key]["version"] == "3.0.0"

        hydrate_key = "sess:services-hydrate"
        hydrated_archive = _memory("hydrate from services", hydrate_key).to_dict()
        service_backend.values[persistence.sylanne_memory_kv_key(hydrate_key)] = (
            hydrated_archive
        )
        live = MemorySystem()
        plugin._store.memory_systems.set(hydrate_key, live)
        await persistence.hydrate_memory_system(hydrate_key)
        assert live._hydrated is True
        assert any(item.text == "hydrate from services" for item in live._l1)

        await persistence._register_pending_delete("sess:index", epoch=7)
        assert "sess:index" in service_backend.values[PENDING_DELETE_INDEX_KV_KEY][
            "entries"
        ]
        await persistence._clear_pending_delete("sess:index")

        profile_key = "sess:services-profile"
        plugin.config.update(
            {
                "sylanne_alpha_cross_session_mode": "on",
                "sylanne_alpha_cross_relationship": True,
            }
        )
        plugin._store.set_authenticated_identity(
            profile_key,
            sender_id="sender-a",
            platform="platform-a",
            origin_id="origin-a",
        )
        await persistence._soft_sync_person_profile(
            profile_key,
            SylanneAlphaHost(
                root=tempfile.mkdtemp(prefix="state_services_profile_"),
                session_key=profile_key,
            ),
            {"body": {"temperature": {"warmth": 0.7}}},
        )

        delete_key = "sess:services-delete"
        safe = persistence._safe_session_key(delete_key)
        delete_keys = (
            persistence.sylanne_memory_kv_key(delete_key),
            persistence.sylanne_memory_backup_v2_kv_key(delete_key),
            quarantine_kv_key(safe),
        )
        for key in delete_keys:
            service_backend.values[key] = {"secret": key}
        await persistence.delete_sylanne_memory_state(delete_key)
        assert all(key not in service_backend.values for key in delete_keys)

        kernel_key = "same-raw-session"
        host = SylanneAlphaHost(
            root=tempfile.mkdtemp(prefix="state_services_kernel_"),
            session_key=kernel_key,
        )
        plugin._store.hosts.set(kernel_key, host)
        persistence.mark_dirty("memory", kernel_key)
        await persistence.flush_pending_kernel_persists()
        assert persistence.kernel_kv_key(kernel_key) in service_backend.values

        assert plugin_backend.calls == []

    asyncio.run(go())


def test_explicit_services_guard_does_not_fail_open_when_plugin_has_no_kv() -> None:
    async def go() -> None:
        backend = _Backend()
        plugin = _PluginWithoutKv()
        persistence = StatePersistence(plugin, services=_services(backend))
        session_key = "sess:services-guard"
        primary_key = persistence.sylanne_memory_kv_key(session_key)
        archive = _memory("protected archive", session_key).to_dict()
        backend.values[primary_key] = copy.deepcopy(archive)

        empty = MemorySystem()
        assert empty._hydrated is False
        await persistence.save_sylanne_memory_state(session_key, empty)

        assert backend.values[primary_key] == archive

    asyncio.run(go())


def test_explicit_services_without_delete_preserve_bytes_and_pending_intent() -> None:
    async def go() -> None:
        service_backend = _Backend()
        plugin_backend = _Backend()
        plugin = _PluginWithDifferentKv(plugin_backend)
        persistence = StatePersistence(
            plugin,
            services=_partial_services(service_backend, delete=False),
        )
        persistence._pending_delete_scan_done = True
        session_key = "sess:missing-delete"
        safe = persistence._safe_session_key(session_key)
        protected_keys = (
            persistence.sylanne_memory_kv_key(session_key),
            persistence.sylanne_memory_backup_v2_kv_key(session_key),
            quarantine_kv_key(safe),
        )
        for key in protected_keys:
            service_backend.values[key] = {"protected": key}
        service_backend.values[PENDING_DELETE_INDEX_KV_KEY] = {
            "version": 1,
            "entries": {},
        }

        assert await persistence._delete_kv_key_with_retry(protected_keys[0]) is False
        await persistence.delete_sylanne_memory_state(session_key)

        assert all(key in service_backend.values for key in protected_keys)
        assert safe in persistence._pending_delete_mirror
        assert safe in service_backend.values[PENDING_DELETE_INDEX_KV_KEY]["entries"]
        before_clear = _backend_bytes(service_backend)
        assert await persistence._clear_pending_delete(session_key) is False
        assert _backend_bytes(service_backend) == before_clear
        assert plugin_backend.calls == []

    asyncio.run(go())


def test_explicit_services_without_get_cannot_hydrate_or_overwrite_archives() -> None:
    async def go() -> None:
        service_backend = _Backend()
        plugin_backend = _Backend()
        plugin = _PluginWithDifferentKv(plugin_backend)
        persistence = StatePersistence(
            plugin,
            services=_partial_services(service_backend, get=False),
        )

        hydrate_key = "sess:missing-get-hydrate"
        hydrate_primary = persistence.sylanne_memory_kv_key(hydrate_key)
        protected_hydrate = {
            "version": "2.0.0",
            "records": [{"text": "protected hydrate archive"}],
        }
        service_backend.values[hydrate_primary] = copy.deepcopy(protected_hydrate)
        live = MemorySystem()
        plugin._store.memory_systems.set(hydrate_key, live)

        await persistence.hydrate_memory_system(hydrate_key)
        assert live._hydrated is False
        await persistence.save_sylanne_memory_state(hydrate_key, live)
        assert service_backend.values[hydrate_primary] == protected_hydrate

        backup_key = "sess:missing-get-backup"
        backup_primary = persistence.sylanne_memory_kv_key(backup_key)
        protected_v2 = {
            "version": "2.0.0",
            "records": [{"text": "protected v2 archive"}],
        }
        service_backend.values[backup_primary] = copy.deepcopy(protected_v2)
        await persistence.save_sylanne_memory_state(
            backup_key,
            _memory("replacement must be refused", backup_key),
        )
        assert service_backend.values[backup_primary] == protected_v2
        assert (
            persistence.sylanne_memory_backup_v2_kv_key(backup_key)
            not in service_backend.values
        )
        assert plugin_backend.calls == []

    asyncio.run(go())


def test_malformed_pending_delete_index_stays_unresolved_and_immutable() -> None:
    malformed_blobs: tuple[Any, ...] = (
        "not-a-dict",
        {"version": 99, "entries": {}},
        {"version": 1, "entries": {"sess:bad-entry": "not-metadata"}},
    )

    async def probe(blob: Any) -> None:
        backend = _Backend()
        plugin = _PluginWithoutKv()
        persistence = StatePersistence(plugin, services=_services(backend))
        persistence._pending_delete_mirror["sess:existing"] = {
            "epoch": 7,
            "ts": 8.0,
        }
        backend.values[PENDING_DELETE_INDEX_KV_KEY] = copy.deepcopy(blob)
        before = _backend_bytes(backend)

        await persistence._scan_pending_deletes()
        assert persistence._pending_delete_scan_done is False
        assert "sess:existing" in persistence._pending_delete_mirror
        assert await persistence._clear_pending_delete_safe("sess:existing") is False
        assert _backend_bytes(backend) == before

    async def go() -> None:
        for blob in malformed_blobs:
            await probe(blob)

    asyncio.run(go())


def test_memory_shards_use_only_explicit_service_callbacks() -> None:
    async def go() -> None:
        backend = _Backend()
        plugin = _PluginWithLegacyShardKv()
        persistence = StatePersistence(plugin, services=_services(backend))
        session_key = "sess:shard-service"
        shard_key = persistence._shard_key(session_key, "memory")
        memory_data = {"items": [{"text": "service-owned"}]}

        assert await persistence.persist_memory_shard(session_key, memory_data) is True
        assert json.loads(backend.values[shard_key]) == memory_data
        assert await persistence.load_memory_shard(session_key) == memory_data
        assert plugin.kv.calls == []

        fenced = StatePersistence(
            plugin,
            services=_partial_services(backend, get=False, put=False),
        )
        backend_before = _backend_bytes(backend)
        assert await fenced.persist_memory_shard(session_key, {"blocked": True}) is False
        assert await fenced.load_memory_shard(session_key) is None
        assert _backend_bytes(backend) == backend_before
        assert plugin.kv.calls == []

    asyncio.run(go())


def test_explicit_services_context_owns_conversation_manager_registration() -> None:
    plugin_manager = _ConversationManager()
    service_manager = _ConversationManager()
    plugin = _PluginWithoutKv()
    plugin.context = SimpleNamespace(conversation_manager=plugin_manager)
    backend = _Backend()
    persistence = StatePersistence(
        plugin,
        services=_services(
            backend,
            context=SimpleNamespace(conversation_manager=service_manager),
        ),
    )

    assert persistence.init_conversation_manager() is service_manager
    assert service_manager.callback is not None
    assert plugin_manager.callback is None


def test_two_instances_fail_closed_for_ambiguous_module_mark_and_isolate_flush() -> None:
    async def go() -> None:
        backend_a = _Backend()
        backend_b = _Backend()
        plugin_a = _PluginWithoutKv()
        plugin_b = _PluginWithoutKv()
        persistence_a = StatePersistence(plugin_a, services=_services(backend_a))
        persistence_b = StatePersistence(plugin_b, services=_services(backend_b))
        session_key = "same-raw-session"

        host_a = SylanneAlphaHost(
            root=tempfile.mkdtemp(prefix="state_owner_a_"), session_key=session_key
        )
        host_b = SylanneAlphaHost(
            root=tempfile.mkdtemp(prefix="state_owner_b_"), session_key=session_key
        )
        plugin_a._store.hosts.set(session_key, host_a)
        plugin_b._store.hosts.set(session_key, host_b)
        before_a = _backend_bytes(backend_a)
        before_b = _backend_bytes(backend_b)

        mark_dirty("memory", session_key)
        await persistence_a.flush_pending_kernel_persists()
        await persistence_b.flush_pending_kernel_persists()
        assert _backend_bytes(backend_a) == before_a
        assert _backend_bytes(backend_b) == before_b

        persistence_a.mark_dirty("memory", session_key)
        await persistence_a.flush_pending_kernel_persists()
        assert persistence_a.kernel_kv_key(session_key) in backend_a.values
        assert _backend_bytes(backend_b) == before_b

    asyncio.run(go())
