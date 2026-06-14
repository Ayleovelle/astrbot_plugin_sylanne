"""migration 测试：S2 文件扫描枚举 / S3 不搬 body / dry_run 零写 / 幂等。

用临时 data_dir + 内存假 KV，绝不碰真实存档。
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from sylanne_alpha.v2core.migration import (
    MIGRATION_MARKER_KEY_FMT,
    OLD_EVOLUTION_KEY_FMT,
    OLD_MEMORY_KEY_FMT,
    SESSION_STORE_KEY_FMT,
    MigrationStatus,
    SessionRegistryStore,
    StateMigrator,
)


class _FakeKV:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    async def get_kv_data(self, key: str, default: Any = None) -> Any:
        return self.store.get(key, default)

    async def put_kv_data(self, key: str, value: Any) -> None:
        self.store[key] = value


def _mk_data_dir(*safe_names: str) -> str:
    d = tempfile.mkdtemp(prefix="sylmig_")
    for n in safe_names:
        (Path(d) / f"{n}.alpha.json").write_text("{}", encoding="utf-8")
    return d


@pytest.mark.asyncio
async def test_discover_scans_body_files() -> None:
    """S2：枚举来自 data_dir 的 *.alpha.json 文件名（不靠 KV，不靠空注册表）。"""
    d = _mk_data_dir("userA", "userB")
    kv = _FakeKV()
    mig = StateMigrator(kv, SessionRegistryStore(kv), d)
    found = await mig.discover_sessions()
    assert set(found) == {"userA", "userB"}, "应从 body 文件名枚举出两个会话"


@pytest.mark.asyncio
async def test_migrate_pulls_kv_not_body() -> None:
    """S3：搬 memory/evolution（KV），不搬 body；store 不含 body 段。"""
    d = _mk_data_dir("u1")
    kv = _FakeKV()
    kv.store[OLD_MEMORY_KEY_FMT.format(safe="u1")] = {"l1": [1, 2]}
    kv.store[OLD_EVOLUTION_KEY_FMT.format(safe="u1")] = {"reflection_bias": 0.3}
    mig = StateMigrator(kv, SessionRegistryStore(kv), d)
    r = await mig.migrate_session("u1")
    assert r.status is MigrationStatus.MIGRATED
    assert set(r.migrated_parts) == {"memory", "evolution"}
    store = kv.store[SESSION_STORE_KEY_FMT.format(safe="u1")]
    assert "body" not in store, "S3：body 绝不进 store（在文件里）"
    assert store["memory"] == {"l1": [1, 2]}
    assert store["evolution"] == {"reflection_bias": 0.3}


@pytest.mark.asyncio
async def test_dry_run_zero_write() -> None:
    """P10：dry_run 不写真实 KV，全进 staged_writes。"""
    d = _mk_data_dir("u1")
    kv = _FakeKV()
    kv.store[OLD_MEMORY_KEY_FMT.format(safe="u1")] = {"l1": []}
    before = dict(kv.store)
    mig = StateMigrator(kv, SessionRegistryStore(kv), d, dry_run=True)
    r = await mig.migrate_session("u1")
    assert r.status is MigrationStatus.DRY_RUN
    assert kv.store == before, "dry_run 不得改真实 KV"
    assert SESSION_STORE_KEY_FMT.format(safe="u1") in mig.staged_writes


@pytest.mark.asyncio
async def test_idempotent_skip() -> None:
    """marker 已存在 → 跳过。"""
    d = _mk_data_dir("u1")
    kv = _FakeKV()
    kv.store[MIGRATION_MARKER_KEY_FMT.format(safe="u1")] = {"version": 1}
    mig = StateMigrator(kv, SessionRegistryStore(kv), d)
    r = await mig.migrate_session("u1")
    assert r.status is MigrationStatus.SKIPPED
