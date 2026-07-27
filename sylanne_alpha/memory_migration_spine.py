"""MEM-01：记忆持久化「金档往返基座」的当前契约 + 权威清单（可导入、可断言）。

这不是一份装饰性说明文档——`MEMORY_KV_KEYS_MANIFEST` / `ROLLBACK_FLOOR_BUILD` /
`FIELD_BACKFILL_DOCTRINE` 都是真实常量，测试（tests/test_memory_golden_roundtrip.py）
会 import 并断言它们，防止这份"设计意图"与代码实际行为脱节漂移。

═══════════════════════════════════════════════════════════════════════════
1. 回滚地板（Rollback Floor）
═══════════════════════════════════════════════════════════════════════════

    回滚地板 = 本次 MEM-01 改动所在的这次 Phase-0 构建，**绝不能再往前**。

原因：MEM-01 之前的任何构建，`state_persistence.py::load_sylanne_memory_state`
的旧版格式分支执行 `from memory_engine import SylanneMemoryState`——该模块早已
归档到 `archive/3x_engines/memory_engine.py`（commit 26d7423），import 恒定
ImportError，被外层 `except Exception: logger.debug(...)` 静默吞掉。也就是说：
**任何早于本次改动的历史构建，一旦遇到旧版 SylanneMemoryState 格式的 KV 归档，
都会把它当成"读不到数据"直接跳过**，而不会真的解析出记忆内容。

这意味着（回滚地板是【数据安全】硬地板，不是"少几个救援功能"的软降级——合并前
对抗闸 L2-5 指出：早前版本的自我论证把这里写反了，据此更正）：
  - **回滚到本次 Phase-0（MEM-01 金档基座 + MEM-02 恢复接线/fail-closed 守卫）之前的
    构建会主动损坏数据，不是"安全忽略"。** 那些构建的聊天恢复路径根本不从 KV 补水
    （hydrate_memory_system 是本阶段新增的）——重启后懒创建的活体永远是空的；而它们
    又没有本阶段的 fail-closed 空覆盖守卫，于是第一次周期性 save（`_tick % 10 == 0`）
    就把这个空活体写回 `sylanne_memory_state:{safe}`，用空档覆盖掉本阶段保住/迁移出的
    v3 归档。这正是本阶段要止血的"重启即清零 + 空档覆盖"链路本身——回滚到地板以下
    ＝ 把这条链路重新放出来。
  - 别拿"v3 blob 顶层键与 v2 同形、旧构建能 key-subset 嗅探读"当回滚安全的凭据：那条
    嗅探只在 load_sylanne_memory_state（WebUI 记忆页三个调用点）里，聊天主路径从不
    经过它。WebUI 没打开时，聊天路径照样在重启后第一条消息附近空档覆盖 v3 归档。
    "WebUI 能读" ≠ "回滚安全"。
  - 因此回滚地板的真正含义是：**本阶段及之后的版本，才【同时】具备"从 KV 补水"与
    "空/未补水活体不得覆盖非空归档（fail-closed）"这两件保命装置；回滚到更早的构建
    会同时失去这两者，导致 v3 归档在重启后被空档覆盖。** 旧版 SylanneMemoryState /
    .alpha.json 救援 / quarantine 侧车等新增读取路径不可用只是附带影响，真正的硬约束
    是"别让归档被空档覆盖"。

═══════════════════════════════════════════════════════════════════════════
2. 未来新字段的迁移原则：惰性逐字段回填，不做一次性迁移
═══════════════════════════════════════════════════════════════════════════

    FIELD_BACKFILL_DOCTRINE：给 MemoryItem/GraphNode/GraphEdge/MemorySystem 加
    新字段时，**只在 from_dict 里加一行 `d.get("new_field", <合理默认值>)`**，
    绝不写"一次性迁移脚本 + 迁移完成标记"这种模式。

理由（这条纪律在 memory_system.py 里已经有活的先例——importance/confidence/
privacy_level/life_event_id/actr_acc 全部是这么加进来的，MEM-01 只是把它显式
成文）：

  - 记忆存档没有统一的"迁移窗口"：不同 session 的 KV blob 在不同时刻被写入/读出，
    没有一个所有存档同时离线、可以批量跑迁移脚本的时间点。
  - 一次性迁移 + 标记这种模式的失败模式是"标记翻了但迁移没跑完/跑错"——那样比
    从来没迁移过更危险（旧代码看到标记会认为"已经是新格式"，从而跳过本该有的
    兼容分支，静默读到不完整数据）。
  - 惰性逐字段回填在设计上不可能出现"半途而废"的中间态：每次 from_dict 调用
    都是独立、完整、幂等的——不管这个字段是老早加的还是刚加的，`.get(key, default)`
    的语义完全一致，没有"迁移进度"这个概念需要维护。

新增字段 checklist（复制 importance/confidence 这几个字段的做法）：
  1. dataclass 里给字段一个合理默认值（__post_init__ 里做 clamp/fail-closed 归一，
     不要依赖构造者总是传合法值）。
  2. to_dict() 里加进去（永远输出，哪怕是默认值——不要"只在非默认时才写"，
     否则旧代码读到时的"缺字段=默认"语义会和新代码的"缺字段=默认"产生歧义）。
  3. from_dict() 里 `d.get(key, default)`，绝不用裸 `d[key]`（除非这个字段从
     MemorySystem 诞生第一天就存在，如 id/text/weight/temperature/age_ticks/
     created_at——那些字段的"必需"语义是历史契约，新字段不应该模仿）。
  4. 若字段值需要数值转换，用 `_safe_float`（本模块同目录 memory_system.py 里
     的模块级函数），不要用裸 `float()`——否则一条脏记录会拖垮整层恢复
     （MEM-01 修复的正是这一类问题，别在新字段上重蹈覆辙）。

═══════════════════════════════════════════════════════════════════════════
3. 当前记忆键清单
═══════════════════════════════════════════════════════════════════════════

见下方 `MEMORY_KV_KEYS_MANIFEST`——枚举记忆子系统在 AstrBot KV 存储里拥有的
全部键名模板。任何新增/废弃记忆相关 KV 键，都应该同步更新这份清单（测试会
对照 state_persistence.py 里的实际键生成方法做一致性检查，防止清单本身腐烂）。
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# §1 回滚地板
# ---------------------------------------------------------------------------

ROLLBACK_FLOOR_BUILD: Final[str] = (
    "Phase-0（MEM-01 金档往返基座 + MEM-02 恢复接线/fail-closed 守卫）"
)
ROLLBACK_FLOOR_NOTE: Final[str] = (
    "回滚不得早于本次 Phase-0 构建——这是【数据安全】硬地板，不是软降级。"
    "早于此点的构建，聊天恢复路径不从 KV 补水、也没有空覆盖守卫：重启后空活体会在"
    "第一次周期性 save 时把 sylanne_memory_state:{safe} 的 v3 归档覆盖成空（重启清零 + "
    "空档覆盖链路复活）。WebUI 的 key-subset 嗅探读得到 v3 blob 也救不了聊天主路径。"
    "旧版 SylanneMemoryState / .alpha.json 救援 / quarantine 侧车不可用只是附带影响。"
)

# ---------------------------------------------------------------------------
# §2 惰性逐字段回填教条（供代码引用/断言，而非仅供人读）
# ---------------------------------------------------------------------------

FIELD_BACKFILL_DOCTRINE: Final[str] = "lazy_per_field_backfill_never_one_shot_migration"

# ---------------------------------------------------------------------------
# §3 当前键清单：记忆子系统拥有的全部 KV 键模板
#
# {safe} = StatePersistence._safe_session_key(session_key) 的输出
#          （session_key.replace("/", "_").replace("\\", "_")）。
# ---------------------------------------------------------------------------

MEMORY_KV_KEYS_MANIFEST: Final[dict[str, str]] = {
    "primary": "sylanne_memory_state:{safe}",
    # MEM-01 新增：v2→v3 首写前的一次性备份（CRC32 校验，此后只读，永不覆盖）。
    "v2_backup": "sylanne_memory_state_backup_v2:{safe}",
    # MEM-01 新增：逐条 salvage 时摘除的坏记录侧车（审计留痕，cap 500 条）。
    "quarantine": "sylanne_memory_quarantine:{safe}",
    # 休眠：state_persistence.py::persist_memory_shard/load_memory_shard 当前无
    # 任何调用点（dead code path），键名用独立的 50 字符截断 + 冒号替换但不替换
    # 反斜杠的第三种 sanitizer 变体（与 _safe_session_key / sylanne_memory_kv_key
    # 两种既有变体并存，历史遗留，未统一）。若未来复活，payload 形状与 primary
    # 键完全一致（见 tests/fixtures/memory_golden/synthetic_dormant_shard_memory_blob.json）。
    "dormant_shard": "sylanne_shard_{safe:.50}_memory",
    # MEM-03 PR-4 新增：单键全局跨重启 pending-delete 索引（design §4/§9 红队
    # must-fix）——**不属于任何单一 session**，模板不含 {safe} 占位符（对不含该
    # 占位符的字符串调用 `.format(safe=...)` 是 no-op，调用方无需特判）。value
    # 形状为 `{"version": 1, "entries": {safe: {"epoch": int, "ts": float}}}`，
    # 供进程重启后的 `_scan_pending_deletes` 完成/驳回崩溃中断的删除意图，见
    # state_persistence.py 同名方法与 `_register_pending_delete`/`_clear_pending_delete`。
    "pending_delete_index": "sylanne_memory_pending_deletes",
    # v2.5.0 P0 slice 1 新增：旁挂人核 v2（design docs/architecture/
    # v250-cross-group-memory-design.md §1.2）的两个 identity-keyed 旁挂存储。
    # 占位符与其余项不同（{platform}/{sender_id} 而非 {safe}）——Python str.format()
    # 对未引用的多余关键字参数不报错，与本清单其余项的 `.format(safe=safe)` 调用点
    # 共存不冲突（本清单没有"一次 format() 覆盖全表"的现成调用点）。
    "person_shelf": "sylanne_person_shelf:{platform}:{sender_id}",
    "person_profile": "sylanne_person_profile:{platform}:{sender_id}",
    # v2.5.0 P0 slice 2 新增：per-session → per-person 反向索引（design §8 B5
    # 数据安全红线）。purge 级联只知道 session_key，货架按 platform:sender_id
    # 存，两套键空间无直接映射——这个索引记录"该 session 写过哪些货架桶"，
    # 供 state_persistence._delete_sylanne_memory_state_impl 反查级联删除。
    # 占位符是 {safe}（与 primary/backup_v2/quarantine 同一变体），不是
    # {platform}/{sender_id}。
    "person_shelf_origin_index": "sylanne_person_shelf_origin_index:{safe}",
}


__all__ = [
    "ROLLBACK_FLOOR_BUILD",
    "ROLLBACK_FLOOR_NOTE",
    "FIELD_BACKFILL_DOCTRINE",
    "MEMORY_KV_KEYS_MANIFEST",
]
