"""MEM-01：记忆金档往返基座 + 迁移主脊——载荷矩阵 golden fixture 回归测试。

覆盖：
  - 载荷矩阵每一行（tests/fixtures/memory_golden/manifest.json 逐条对应）的
    load -> round-trip -> 语义相等 / quarantine 归account。
  - 版本分支行为（version 字段可观测但非受控流程，"旧代码读 v3"退化测试）。
  - v2->v3 首写前 CRC32 备份闸门（成功/失败两条路径）。
  - quarantine 侧车 KV 的端到端写入。

不引入新的运行时依赖：全程只用标准库 + 本仓库既有模块。
"""

from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path
from typing import Any

from sylanne_alpha.memory_legacy_formats import (
    normalize_memory_blob,
    salvage_memory_system_from_alpha_json,
)
from sylanne_alpha.memory_system import MemorySystem
from sylanne_alpha.memory_migration_spine import (
    FIELD_BACKFILL_DOCTRINE,
    MEMORY_KV_KEYS_MANIFEST,
    ROLLBACK_FLOOR_BUILD,
)
from sylanne_alpha.state_persistence import StatePersistence

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "memory_golden"


def _load_fixture(name: str) -> dict[str, Any]:
    with open(FIXTURES_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def _item_signature(item: Any) -> tuple:
    """MemoryItem 的语义比较签名（忽略 id 之外，覆盖决定"这是不是同一条记忆"的字段）。"""
    return (
        item.id,
        item.text,
        round(item.weight, 6),
        round(item.temperature, 6),
        round(item.importance, 6),
        round(item.confidence, 6),
        item.privacy_level,
    )


# ---------------------------------------------------------------------------
# manifest 自洽性：清单里声明的 fixture 文件必须真实存在
# ---------------------------------------------------------------------------


def test_manifest_fixtures_all_exist() -> None:
    manifest = _load_fixture("manifest.json")
    for entry in manifest["fixtures"]:
        path = FIXTURES_DIR / entry["file"]
        assert path.is_file(), f"manifest 声明的 fixture 缺失：{entry['file']}"


# ---------------------------------------------------------------------------
# 行 (a)：真实抽样的 v2 MemorySystem KV dict
# ---------------------------------------------------------------------------


def test_row_a_real_v2_sampled_load_and_roundtrip() -> None:
    raw = _load_fixture("real_v2_sampled_lifesim.json")
    normalized, quarantined, fmt = normalize_memory_blob(raw)
    assert fmt == "memory_system"
    assert quarantined == []

    mem = MemorySystem.create_from_dict(normalized)
    assert len(mem._l1) == 3
    assert mem._quarantine == []
    # 旧 v2 archive 缺 Phase-2A 字段：回填为合理默认值，而不是抛异常或悄悄清零。
    for item in mem._l1:
        assert 0.0 <= item.importance <= 1.0
        assert item.privacy_level == "open"
        assert item.confidence == 0.5  # 缺字段 -> 中性默认

    # round-trip：load -> to_dict -> reload -> 语义相等（条目数守恒、字段值一致）
    dumped = mem.to_dict()
    assert dumped["version"] == "3.0.0"
    reloaded = MemorySystem.create_from_dict(dumped)
    assert len(reloaded._l1) == len(mem._l1)
    assert [_item_signature(i) for i in reloaded._l1] == [
        _item_signature(i) for i in mem._l1
    ]


# ---------------------------------------------------------------------------
# 行 (b)：旧版 SylanneMemoryState（3.x 引擎，SYNTHETIC）
# ---------------------------------------------------------------------------


def test_row_b_legacy_sylanne_memory_state_migrates_and_quarantines() -> None:
    raw = _load_fixture("synthetic_legacy_sylanne_memory_state.json")
    normalized, quarantined, fmt = normalize_memory_blob(raw)
    assert fmt == "legacy_sylanne_memory_state"
    # 3 条 records：1 条可救、1 条文本全空不可救、1 条非 dict 垃圾 —— 2 条 quarantine
    assert len(quarantined) == 2

    assert normalized is not None
    mem = MemorySystem.create_from_dict(normalized)
    assert mem._quarantine == []  # 转换后交给 MemorySystem 的都已经是合法 dict
    assert len(mem._l2) == 1
    migrated = mem._l2[0]
    assert "看展览" in migrated.text
    assert migrated.confirmed is True
    assert 0.0 <= migrated.importance <= 1.0
    assert migrated.source == "dialogue"
    assert migrated.privacy_level == "open"

    # round-trip 之后应该是纯 MemorySystem v3 格式，不再需要走 legacy 转换
    dumped = mem.to_dict()
    assert dumped["version"] == "3.0.0"
    _, requarantined, refmt = normalize_memory_blob(dumped)
    assert refmt == "memory_system"
    assert requarantined == []


# ---------------------------------------------------------------------------
# 行 (d)：损坏变体——item 级 salvage + quarantine 归account
# ---------------------------------------------------------------------------


def test_row_d_corrupted_v3_item_level_salvage() -> None:
    raw = _load_fixture("synthetic_corrupted_v3_item_garbage.json")
    normalized, quarantined_pre, fmt = normalize_memory_blob(raw)
    assert fmt == "memory_system"
    assert quarantined_pre == []  # 顶层形状本身合法，垃圾在条目内部

    mem = MemorySystem.create_from_dict(normalized)

    # l1: 4 条原始 -> 2 条应该 salvage 成功（含"字段带垃圾值但仍可救"那条：
    # actr_acc=NaN / last_recalled_ts='garbage' / importance='not_a_number' 全部
    # 应该被 _safe_float 兜底成默认值，而不是让整条记录（进而整层）恢复失败）。
    assert len(mem._l1) == 2
    ids = {item.id for item in mem._l1}
    assert ids == {"good0001aaaa", "garbage_ts_0002"}
    garbage_item = next(i for i in mem._l1 if i.id == "garbage_ts_0002")
    assert garbage_item.last_recalled_ts == 0.0  # 垃圾字符串 -> 默认值，不抛异常
    assert garbage_item.actr_acc == 1.0  # NaN -> 默认值
    assert garbage_item.importance == 0.5  # 非数字 -> 中性默认

    # 2 条原始不可解析：非 dict 垃圾 + 缺失必需字段
    l1_quarantine = [q for q in mem._quarantine if q["layer"] == "l1"]
    assert len(l1_quarantine) == 2

    # 条目数守恒核算：raw 总数 == 恢复成功数 + quarantine 数
    assert len(raw["l1"]) == len(mem._l1) + len(l1_quarantine)

    # l3_nodes: 1 条好 + 1 条非 dict quarantine
    assert len(mem._l3_nodes) == 1
    assert "node_ok" in mem._l3_nodes
    l3_node_quarantine = [q for q in mem._quarantine if q["layer"] == "l3_nodes"]
    assert len(l3_node_quarantine) == 1

    # l3_edges: 1 条好 + 1 条缺字段（KeyError）quarantine
    assert len(mem._l3_edges) == 1
    l3_edge_quarantine = [q for q in mem._quarantine if q["layer"] == "l3_edges"]
    assert len(l3_edge_quarantine) == 1

    # round-trip：quarantine 不参与序列化（不是 MemorySystem 的持久状态），
    # 但已恢复的好条目应该在往返后依然存在、字段一致。
    dumped = mem.to_dict()
    reloaded = MemorySystem.create_from_dict(dumped)
    assert len(reloaded._l1) == 2
    assert reloaded._quarantine == []  # 已恢复的条目本身都是干净的，往返不再产生新 quarantine


# ---------------------------------------------------------------------------
# 行 (e)：kernel KV 部分快照——容忍缺失子系统，不误判为记忆数据
# ---------------------------------------------------------------------------


def test_row_e_kernel_partial_snapshot_not_misidentified_as_memory() -> None:
    raw = _load_fixture("synthetic_kernel_kv_partial_snapshot.json")
    normalized, quarantined, fmt = normalize_memory_blob(raw)
    # 只含 personality 脏子系统、无 l1/l2/l3_nodes/l3_edges、无 records ——
    # 必须被判定为"不认识"，而不是被误判成"合法的空记忆"（两者对上层告警/
    # 降级路径语义完全不同：前者应该保留旧数据不动，后者可能触发空写保护外的
    # 其他逻辑）。
    assert fmt == "unknown"
    assert normalized is None
    assert quarantined == []


def test_row_e_kernel_restore_tolerates_missing_body_key() -> None:
    """AlphaKernel.restore 面对缺 body 键的部分快照不应崩溃（既有属性，非本次改动，
    这里只做回归锁定，防止未来改动破坏这条"部分快照可安全恢复"的既有能力）。
    """
    from sylanne_alpha._engine.sylanne_core.compute.kernel import AlphaKernel

    raw = _load_fixture("synthetic_kernel_kv_partial_snapshot.json")
    kernel = AlphaKernel.restore(raw)
    assert kernel.body.memory.get("_memory_system") is None


# ---------------------------------------------------------------------------
# 行 (e)：休眠分片键——格式识别由内容形状驱动，不依赖 KV 键名
# ---------------------------------------------------------------------------


def test_row_e_dormant_shard_blob_recognized_by_shape_not_key() -> None:
    raw = _load_fixture("synthetic_dormant_shard_memory_blob.json")
    normalized, quarantined, fmt = normalize_memory_blob(raw)
    assert fmt == "memory_system"
    assert quarantined == []
    mem = MemorySystem.create_from_dict(normalized)
    assert len(mem._l1) == 1
    assert mem._l1[0].text == "[SYNTHETIC] 分片格式条目"


# ---------------------------------------------------------------------------
# 行 (c)：pre-CP1 .alpha.json body 内 memory['_memory_system'] 救援
# ---------------------------------------------------------------------------


def test_row_c_alpha_json_salvage_bypasses_kernel_whitelist() -> None:
    path = FIXTURES_DIR / "real_sampled_alpha_json_precp1_salvage.json"
    salvaged = salvage_memory_system_from_alpha_json(path)
    assert salvaged is not None
    assert salvaged["version"] == "3.0.0"
    mem = MemorySystem.create_from_dict(salvaged)
    assert len(mem._l1) == 1
    assert mem._l1[0].id == "precp1demo001"


def test_row_c_kernel_whitelist_actually_drops_memory_system_field() -> None:
    """回归锁定：证明 salvage 路径确有必要——AlphaBodyState.from_dict 的 memory
    白名单只认 relationship/shadow，会把 _memory_system/traces 静默丢弃。
    若未来 body.py 修复了这个白名单（让 kernel 恢复本身就保留这个字段），
    本测试会失败，届时应视为好消息并更新/移除这条回归锁定，而不是不假思索地
    修改断言让它通过。
    """
    from sylanne_alpha._engine.sylanne_core.compute.body import AlphaBodyState

    data = _load_fixture("real_sampled_alpha_json_precp1_salvage.json")
    body = AlphaBodyState.from_dict(data["body"])
    assert "_memory_system" not in body.memory
    assert "traces" not in body.memory
    # 但绕过 kernel 白名单直接读文件本身，仍然能救回来（上一条测试已验证）。


def test_row_c_alpha_json_salvage_missing_or_corrupt_file_returns_none() -> None:
    assert salvage_memory_system_from_alpha_json(FIXTURES_DIR / "does_not_exist.alpha.json") is None
    # 构造一份 JSON 损坏的临时文件
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".alpha.json", delete=False) as f:
        f.write("{not valid json!!")
        tmp_path = f.name
    try:
        assert salvage_memory_system_from_alpha_json(tmp_path) is None
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 版本分支行为
# ---------------------------------------------------------------------------


def test_unknown_higher_version_loads_known_fields_and_warns(caplog: Any) -> None:
    raw = _load_fixture("real_v2_sampled_lifesim.json")
    raw = dict(raw)
    raw["version"] = "99.0.0"  # 模拟"未来更高版本"的存档
    import logging

    with caplog.at_level(logging.WARNING, logger="astrbot_plugin_sylanne"):
        mem = MemorySystem.create_from_dict(raw)
    assert len(mem._l1) == 3  # 已知字段照常加载，绝不因为版本更高就清空
    assert any("version" in rec.message for rec in caplog.records)


def test_old_code_reads_v3_with_version_ignored_degrades_gracefully() -> None:
    """模拟"旧代码读 v3"退化测试：把 version 字段整个抹掉（等价于版本信息完全
    不存在/被忽略），当前恢复逻辑必须产出与"version 字段存在"时完全相同的结果
    ——版本字段目前只用于可观测性 WARN，不是任何字段恢复正确性的必要条件。
    """
    for fixture_name in (
        "real_v2_sampled_lifesim.json",
        "synthetic_corrupted_v3_item_garbage.json",
    ):
        raw = _load_fixture(fixture_name)
        with_version = MemorySystem.create_from_dict(raw)

        raw_no_version = dict(raw)
        raw_no_version.pop("version", None)
        without_version = MemorySystem.create_from_dict(raw_no_version)

        assert len(without_version._l1) == len(with_version._l1)
        assert len(without_version._l2) == len(with_version._l2)
        assert len(without_version._l3_nodes) == len(with_version._l3_nodes)
        assert len(without_version._l3_edges) == len(with_version._l3_edges)
        assert [_item_signature(i) for i in without_version._l1] == [
            _item_signature(i) for i in with_version._l1
        ]


# ---------------------------------------------------------------------------
# 迁移脊柱模块自洽性
# ---------------------------------------------------------------------------


def test_migration_spine_manifest_matches_state_persistence_key_generators() -> None:
    assert ROLLBACK_FLOOR_BUILD
    assert FIELD_BACKFILL_DOCTRINE == "lazy_per_field_backfill_never_one_shot_migration"
    assert "v2core_migration_target" not in MEMORY_KV_KEYS_MANIFEST
    assert "v2core_migration_marker" not in MEMORY_KV_KEYS_MANIFEST

    class _FakePlugin:
        pass

    sp = StatePersistence(_FakePlugin())
    safe = "test_session"
    assert MEMORY_KV_KEYS_MANIFEST["primary"].format(safe=safe) == sp.sylanne_memory_kv_key(
        safe
    )
    assert MEMORY_KV_KEYS_MANIFEST["v2_backup"].format(
        safe=safe
    ) == sp.sylanne_memory_backup_v2_kv_key(safe)
    from sylanne_alpha.memory_legacy_formats import quarantine_kv_key

    assert MEMORY_KV_KEYS_MANIFEST["quarantine"].format(safe=safe) == quarantine_kv_key(safe)


# ---------------------------------------------------------------------------
# v2->v3 首写前 CRC32 备份闸门（成功 / 失败两条路径）
# ---------------------------------------------------------------------------


class _KVPlugin:
    """带内存 KV 的假 plugin，复刻 tests/test_fixlist_p0_7_persistence.py 的写法。"""

    _config: dict = {}

    def __init__(self) -> None:
        self._kv: dict[str, Any] = {}
        self._store = _FakeStore()

    async def get_kv_data(self, key: str, default=None):  # noqa: ANN001
        return self._kv.get(key, default)

    async def put_kv_data(self, key: str, value) -> None:  # noqa: ANN001
        self._kv[key] = value


class _BoundedDictLike(dict):
    def set(self, k, v) -> None:  # noqa: ANN001
        self[k] = v


class _FakeStore:
    def __init__(self) -> None:
        self.sylanne_memory_cache = _BoundedDictLike()
        self.memory_systems = _BoundedDictLike()


def _make_memory_system_with_one_item(text: str) -> MemorySystem:
    mem = MemorySystem()
    mem.write_summary(text, source_turns=1, temperature=0.1)
    return mem


def test_v3_write_backs_up_existing_v2_blob_with_verified_crc() -> None:
    plugin = _KVPlugin()
    sp = StatePersistence(plugin)
    session_key = "backup_gate_session"
    kv_key = sp.sylanne_memory_kv_key(session_key)
    backup_key = sp.sylanne_memory_backup_v2_kv_key(session_key)

    # 预置一份"现存 v2 数据"（模拟这个 session 在 MEM-01 之前就已经落过盘）
    existing_v2 = {"version": "2.0.0", "tick": 1, "l1": [], "l2": [], "l3_nodes": {}, "l3_edges": []}
    plugin._kv[kv_key] = existing_v2

    mem = _make_memory_system_with_one_item("[TEST] 首次 v3 写入")
    mem._hydrated = True  # 绕开 MEM-02 的空写保护闸门，聚焦本测试的备份闸门

    asyncio.run(sp.save_sylanne_memory_state(session_key, mem))

    assert backup_key in plugin._kv
    backup_payload = plugin._kv[backup_key]
    assert backup_payload["data"] == existing_v2
    import zlib as _zlib

    expected_crc = _zlib.crc32(
        json.dumps(existing_v2, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ) & 0xFFFFFFFF
    assert backup_payload["_crc32"] == expected_crc

    # v3 写入本身应该成功落盘
    assert plugin._kv[kv_key]["version"] == "3.0.0"

    # 备份键此后只读：再写一次不应该覆盖它
    mem2 = _make_memory_system_with_one_item("[TEST] 第二次写入")
    mem2._hydrated = True
    asyncio.run(sp.save_sylanne_memory_state(session_key, mem2))
    assert plugin._kv[backup_key] == backup_payload


def test_v3_write_skipped_when_backup_verify_fails() -> None:
    plugin = _KVPlugin()
    sp = StatePersistence(plugin)
    session_key = "backup_gate_fail_session"
    kv_key = sp.sylanne_memory_kv_key(session_key)
    backup_key = sp.sylanne_memory_backup_v2_kv_key(session_key)

    existing_v2 = {"version": "2.0.0", "tick": 3, "l1": [], "l2": [], "l3_nodes": {}, "l3_edges": []}
    plugin._kv[kv_key] = existing_v2

    # 让 put_kv_data 在写 backup_key 时故意写入一份 CRC 对不上的数据（模拟
    # 备份回读校验失败的场景）——包装原 put 方法，仅对 backup_key 篡改。
    original_put = plugin.put_kv_data

    async def _tampering_put(key: str, value):  # noqa: ANN001
        if key == backup_key and isinstance(value, dict):
            value = dict(value)
            value["_crc32"] = (value.get("_crc32", 0) + 1) & 0xFFFFFFFF
        await original_put(key, value)

    plugin.put_kv_data = _tampering_put  # type: ignore[method-assign]

    mem = _make_memory_system_with_one_item("[TEST] 应该被 fail-closed 拦截")
    mem._hydrated = True

    asyncio.run(sp.save_sylanne_memory_state(session_key, mem))

    # 校验失败 -> fail-closed 跳过本次 v3 写入，旧数据原样保留
    assert plugin._kv[kv_key] == existing_v2
    assert plugin._kv[kv_key]["version"] == "2.0.0"


def test_v3_write_no_backup_needed_for_brand_new_session() -> None:
    plugin = _KVPlugin()
    sp = StatePersistence(plugin)
    session_key = "brand_new_session"
    kv_key = sp.sylanne_memory_kv_key(session_key)
    backup_key = sp.sylanne_memory_backup_v2_kv_key(session_key)

    mem = _make_memory_system_with_one_item("[TEST] 全新 session")
    mem._hydrated = True
    asyncio.run(sp.save_sylanne_memory_state(session_key, mem))

    assert backup_key not in plugin._kv  # 没有旧数据可备份，闸门应直接放行
    assert plugin._kv[kv_key]["version"] == "3.0.0"


# ---------------------------------------------------------------------------
# quarantine 侧车 KV 端到端写入（经 load_sylanne_memory_state 触发）
# ---------------------------------------------------------------------------


def test_load_persists_quarantine_sidecar_for_corrupted_kv() -> None:
    plugin = _KVPlugin()
    sp = StatePersistence(plugin)
    session_key = "quarantine_e2e_session"
    kv_key = sp.sylanne_memory_kv_key(session_key)
    from sylanne_alpha.memory_legacy_formats import quarantine_kv_key

    plugin._kv[kv_key] = _load_fixture("synthetic_corrupted_v3_item_garbage.json")

    state = asyncio.run(sp.load_sylanne_memory_state(session_key))
    assert state is not None
    assert len(state._l1) == 2

    q_key = quarantine_kv_key(sp._safe_session_key(session_key))
    assert q_key in plugin._kv
    stored = plugin._kv[q_key]
    assert stored["count"] >= 4  # l1(2) + l3_nodes(1) + l3_edges(1)


def test_load_migrates_legacy_and_persists_quarantine() -> None:
    plugin = _KVPlugin()
    sp = StatePersistence(plugin)
    session_key = "legacy_e2e_session"
    kv_key = sp.sylanne_memory_kv_key(session_key)
    from sylanne_alpha.memory_legacy_formats import quarantine_kv_key

    plugin._kv[kv_key] = _load_fixture("synthetic_legacy_sylanne_memory_state.json")

    state = asyncio.run(sp.load_sylanne_memory_state(session_key))
    assert state is not None
    assert len(state._l2) == 1

    q_key = quarantine_kv_key(sp._safe_session_key(session_key))
    assert q_key in plugin._kv
    assert plugin._kv[q_key]["count"] == 2


if __name__ == "__main__":
    import sys

    import pytest as _pytest

    sys.exit(_pytest.main([__file__, "-v"]))
