"""MEM-01：记忆持久化「金档往返基座」的迁移脊柱文档 + 权威清单（可导入、可断言）。

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
3. 为什么不用 v2core/migration.py 的 StateMigrator 机制
═══════════════════════════════════════════════════════════════════════════

`sylanne_alpha/v2core/migration.py` 已经提供了一套完整的迁移基础设施：
`SessionRegistryStore`（持久 session 注册表）+ `StateMigrator`（幂等、按
session 隔离、支持 dry_run、写迁移完成 marker）。这套机制正确、好用，但它解决
的是**另一个粒度的问题**——把整段 KV 数据从旧架构（散落的 `sylanne_memory_state_*`
等键）**搬运**到新架构的 `sylanne_v2_store_{safe}` 单键存储，是"存储位置/组织
方式"的迁移，天然需要 marker（"这个 session 搬过了吗"）和 dry_run（"搬之前先
看看会搬出什么"）。

MEM-01 面对的是另一件事：**同一个 KV 键内部，MemorySystem 自身序列化形状的版本
演进**（v2 -> v3，以及未来的 v3 -> v4...）。这里没有"搬运"这个动作——数据始终
待在同一个 `sylanne_memory_state:{safe}` 键里，只是这个键里的 dict 形状在增加
可选字段。给这种场景套用 StateMigrator 的 marker/registry 机制是错配的重型
工具：不需要"哪些 session 迁移过"的注册表（每次 from_dict 调用本身就是幂等的
探测+回填），也不需要 dry_run（.get() 回填不会产生副作用，没有"预演"的必要）。

因此 MEM-01 选择的是"惰性逐字段回填"（见上一节），而不是复用/扩展
StateMigrator。两者并不冲突——如果未来记忆系统真的需要**搬运存储位置**（比如
把 `sylanne_memory_state:{safe}` 整体挪到 v2core 的 SessionStore 里），那才是
`StateMigrator` 该出场的时候，届时 `OLD_MEMORY_KEY_FMT` 常量已经预留了
`sylanne_memory_state:{safe}` 这个键名（`v2core/migration.py:30`），可以直接
复用其 registry/marker/dry-run 骨架，不需要重新发明。

═══════════════════════════════════════════════════════════════════════════
4. 迁移键清单（记忆子系统拥有的全部 KV 键）
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
    "Phase-0（MEM-01 金档往返基座 + MEM-02 恢复接线/fail-closed 守卫 + 迁移主脊）"
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
# §4 迁移键清单：记忆子系统拥有的全部 KV 键模板
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
    # v2core 迁移器（sylanne_alpha/v2core/migration.py）为"记忆搬运到新架构"预留
    # 的键名——与本清单里其余"记忆自身格式版本演进"用途不同，见 §3。
    "v2core_migration_target": "sylanne_v2_store_{safe}",
    "v2core_migration_marker": "sylanne_v2_migrated_{safe}",
}


__all__ = [
    "ROLLBACK_FLOOR_BUILD",
    "ROLLBACK_FLOOR_NOTE",
    "FIELD_BACKFILL_DOCTRINE",
    "MEMORY_KV_KEYS_MANIFEST",
]
