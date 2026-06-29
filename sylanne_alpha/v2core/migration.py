"""v2core 存档迁移器 + 持久 session 注册表（设计 §5.1，含 skeptic S2/S3 修复）。

绞杀式重写的存档无损搬运层（铁律4）。

S3 关键修正（body 在文件、不在 KV）：
  人格漂移史的权威源是 **文件** root/{safe}.alpha.json，由 host.__post_init__ 经
  runtime.load 自动恢复。KV 里的 sylanne_kernel_{safe} 只是「增量脏快照」副本，残缺。
  → 迁移器**不从 KV 搬 body**。body 无损 = 新引擎 data_dir 指向旧 root（文件连续性）。
  迁移器只搬真正在 KV 的三类：memory / evolution / buffer。

S2 关键修正（枚举不靠 KV 扫描，也不只靠空注册表）：
  AstrBot KV 无前缀枚举；旧架构从未写过 sylanne_known_sessions（注册表升级当下是空的）。
  → discover_sessions 主力**扫 data_dir 的 *.alpha.json 文件名**反推 session 集合（body 文件
  是每会话必有的最可靠枚举源），持久注册表作增量补充。两路并集，杜绝冷会话漏迁。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger("sylanne.v2core.migration")

# ---- 键名 / 文件名常量（锁定事实，§9）----
KNOWN_SESSIONS_KEY = "sylanne_known_sessions"          # 持久注册表（list[str]）
OLD_MEMORY_KEY_FMT = "sylanne_memory_state:{safe}"     # 三层记忆（在 KV）
OLD_EVOLUTION_KEY_FMT = "sylanne_evolution_{safe}"     # 进化档案/漂移偏置（在 KV，§9 定位）
OLD_BUFFER_KEY_FMT = "sylanne_buffer_{safe}"           # 对话缓冲（在 KV）
SESSION_STORE_KEY_FMT = "sylanne_v2_store_{safe}"      # 新 store
MIGRATION_MARKER_KEY_FMT = "sylanne_v2_migrated_{safe}"
MIGRATION_VERSION = 1
BODY_FILE_SUFFIX = ".alpha.json"                       # body 文件后缀（S2 枚举源）

_SECTION_MEMORY = "memory"
_SECTION_EVOLUTION = "evolution"
_SECTION_BUFFER = "buffer"
_SECTION_MIGRATION = "_migration"


def _safe_session_key(session_key: str) -> str:
    """复刻旧 StatePersistence._safe_session_key（路径分隔符替换）。须逐字符一致。"""
    return session_key.replace("/", "_").replace("\\", "_")

# <!-- MCHUNK1 -->


@runtime_checkable
class _KVLike(Protocol):
    """迁移器对 KV 的最小依赖面：精确键 get/put（无枚举，呼应 P13/S2）。"""

    async def get_kv_data(self, key: str, default: Any = None) -> Any: ...
    async def put_kv_data(self, key: str, value: Any) -> None: ...


class SessionRegistryStore:
    """持久 session 注册表（P13 增量补充源）。单键 sylanne_known_sessions -> list[str]。"""

    __slots__ = ("_kv",)

    def __init__(self, kv: _KVLike) -> None:
        self._kv = kv

    async def register(self, session_key: str) -> None:
        sessions = await self._read_list()
        if session_key in sessions:
            return
        sessions.append(session_key)
        await self._kv.put_kv_data(KNOWN_SESSIONS_KEY, sessions)

    async def all_sessions(self) -> list[str]:
        return list(await self._read_list())

    async def _read_list(self) -> list[str]:
        raw = await self._kv.get_kv_data(KNOWN_SESSIONS_KEY, None)
        if not isinstance(raw, list):
            return []
        return [s for s in raw if isinstance(s, str)]


# ---- 迁移结果数据结构 ----

class MigrationStatus(str, Enum):
    MIGRATED = "migrated"
    DEGRADED = "degraded"
    SKIPPED = "skipped"
    EMPTY = "empty"
    DRY_RUN = "dry_run"
    FAILED = "failed"


@dataclass(slots=True)
class SessionMigrationResult:
    session_key: str
    status: MigrationStatus
    migrated_parts: tuple[str, ...] = ()
    degraded_parts: tuple[str, ...] = ()
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status not in (MigrationStatus.DEGRADED, MigrationStatus.FAILED)


@dataclass(slots=True)
class MigrationReport:
    results: list[SessionMigrationResult] = field(default_factory=list)
    dry_run: bool = False

    def add(self, r: SessionMigrationResult) -> None:
        self.results.append(r)

    def _count(self, s: MigrationStatus) -> int:
        return sum(1 for r in self.results if r.status is s)

    @property
    def total(self) -> int:
        return len(self.results)

    def summary(self) -> dict[str, int]:
        return {
            "total": self.total,
            "migrated": self._count(MigrationStatus.MIGRATED),
            "degraded": self._count(MigrationStatus.DEGRADED),
            "skipped": self._count(MigrationStatus.SKIPPED),
            "empty": self._count(MigrationStatus.EMPTY),
            "dry_run": self._count(MigrationStatus.DRY_RUN),
            "failed": self._count(MigrationStatus.FAILED),
            # S8：dry_run 下也单独统计降级，不被 DRY_RUN status 掩盖
            "degraded_parts_seen": sum(1 for r in self.results if r.degraded_parts),
        }

# <!-- MCHUNK2 -->


class StateMigrator:
    """旧 KV 存档 → 新 SessionStore 搬运器（逐 session 隔离、幂等、可 dry_run）。

    S3：不搬 body（body 在文件 root/{safe}.alpha.json，由 host runtime.load 恢复；
        无损靠 data_dir 连续性，迁移器只搬 KV 里的 memory/evolution/buffer）。
    S2：discover_sessions 扫 data_dir/*.alpha.json 反推 session ∪ 持久注册表。
    """

    __slots__ = ("_kv", "_registry", "_data_dir", "_dry_run", "staged_writes")

    def __init__(
        self,
        kv: _KVLike,
        registry: SessionRegistryStore,
        data_dir: str | Path,
        *,
        dry_run: bool = False,
    ) -> None:
        self._kv = kv
        self._registry = registry
        self._data_dir = Path(data_dir)
        self._dry_run = dry_run
        self.staged_writes: dict[str, Any] = {}

    async def discover_sessions(self) -> list[str]:
        """枚举待迁 session：扫 body 文件名（主力）∪ 持久注册表（增量）。绝不扫 KV。"""
        found: set[str] = set()
        # 主力：data_dir 下的 *.alpha.json 文件名（每会话必有 body 文件）
        try:
            if self._data_dir.is_dir():
                for p in self._data_dir.glob(f"*{BODY_FILE_SUFFIX}"):
                    name = p.name[: -len(BODY_FILE_SUFFIX)]
                    if name and name != "default":
                        found.add(name)  # 注：此为 safe_filename 形态，迁移按 safe 直接用
        except OSError as exc:
            logger.error("Sylanne v2 迁移：扫描 %s 失败：%s", self._data_dir, exc)
        # 增量：持久注册表（可能含 body 文件已清但 KV 仍有档的边缘会话）
        for sk in await self._registry.all_sessions():
            found.add(_safe_session_key(sk))
        return sorted(found)

    async def migrate_all(self) -> MigrationReport:
        report = MigrationReport(dry_run=self._dry_run)
        sessions = await self.discover_sessions()
        logger.info("Sylanne v2 迁移开始：发现 %d 会话（dry_run=%s）", len(sessions), self._dry_run)
        for safe in sessions:
            try:
                report.add(await self.migrate_session(safe))
            except Exception as exc:  # 整 session 隔离，不连坐
                logger.error("Sylanne v2 迁移 [%s] 整体失败：%s", safe, exc, exc_info=True)
                report.add(SessionMigrationResult(
                    session_key=safe, status=MigrationStatus.FAILED, errors={"_session": repr(exc)}))
        logger.info("Sylanne v2 迁移结束：%s", report.summary())
        return report

    async def migrate_session(self, safe: str) -> SessionMigrationResult:
        """迁移单会话（入参已是 safe 形态）。幂等 → 读 KV 三类 → 归位。body 不在此（S3）。"""
        marker = await self._get(MIGRATION_MARKER_KEY_FMT.format(safe=safe))
        if marker is not None:
            return SessionMigrationResult(session_key=safe, status=MigrationStatus.SKIPPED)

        migrated: list[str] = []
        degraded: list[str] = []
        errors: dict[str, str] = {}
        store: dict[str, Any] = {}
        for section, fmt in (
            (_SECTION_MEMORY, OLD_MEMORY_KEY_FMT),
            (_SECTION_EVOLUTION, OLD_EVOLUTION_KEY_FMT),
            (_SECTION_BUFFER, OLD_BUFFER_KEY_FMT),
        ):
            try:
                raw = await self._get(fmt.format(safe=safe))
                if isinstance(raw, dict):
                    store[section] = raw
                    migrated.append(section)
            except Exception as exc:
                logger.error("Sylanne v2 迁移：读 %s 失败：%s", section, exc)
                degraded.append(section)
                errors[section] = repr(exc)

        if not store and not degraded:
            return SessionMigrationResult(session_key=safe, status=MigrationStatus.EMPTY)

        store[_SECTION_MIGRATION] = {
            "version": MIGRATION_VERSION, "safe": safe, "degraded_parts": list(degraded),
            "note": "body 不在此——由文件 root/{safe}.alpha.json 经 host.runtime.load 恢复（S3）",
        }
        await self._put(SESSION_STORE_KEY_FMT.format(safe=safe), store)
        await self._put(MIGRATION_MARKER_KEY_FMT.format(safe=safe),
                        {"version": MIGRATION_VERSION, "parts": list(migrated)})

        status = (MigrationStatus.DRY_RUN if self._dry_run
                  else MigrationStatus.DEGRADED if degraded else MigrationStatus.MIGRATED)
        logger.info("Sylanne v2 迁移 [%s]：%s parts=%s degraded=%s",
                    safe, status.value, migrated, degraded)
        return SessionMigrationResult(
            session_key=safe, status=status,
            migrated_parts=tuple(migrated), degraded_parts=tuple(degraded), errors=errors)

    async def _get(self, key: str) -> Any:
        return await self._kv.get_kv_data(key, None)

    async def _put(self, key: str, value: Any) -> None:
        if self._dry_run:                      # P10：dry_run 写走暂存，零写真实 KV
            self.staged_writes[key] = value
            return
        await self._kv.put_kv_data(key, value)


__all__ = [
    "KNOWN_SESSIONS_KEY", "OLD_MEMORY_KEY_FMT", "OLD_EVOLUTION_KEY_FMT",
    "OLD_BUFFER_KEY_FMT", "SESSION_STORE_KEY_FMT", "MIGRATION_MARKER_KEY_FMT",
    "MIGRATION_VERSION", "BODY_FILE_SUFFIX", "SessionRegistryStore",
    "MigrationStatus", "SessionMigrationResult", "MigrationReport", "StateMigrator",
]


