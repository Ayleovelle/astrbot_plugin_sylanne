"""状态持久化委托层模块。

处理 kernel 和对话缓冲区的持久化，采用 AstrBot KV 存储（主路径）+
文件 IO（回退路径）的双写策略。同时提供所有引擎状态的 KV 键生成辅助方法
和 load/save/delete 包装器，覆盖：情感、类人、心理筛查、类生命学习、
人格漂移、道德修复、易错性、群体氛围、Sylanne 记忆等子系统状态。

此外集成 AstrBot 的 ConversationManager 和 PersonaManager，
实现对话历史和人格状态的平行同步。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import zlib
from typing import TYPE_CHECKING, Any

from sylanne_alpha.memory_migration_spine import MEMORY_KV_KEYS_MANIFEST
from sylanne_alpha.utils import safe_ensure_future

if TYPE_CHECKING:
    from .host import SylanneAlphaHost
    from .protocols import PluginHost

logger = logging.getLogger("astrbot_plugin_sylanne")

# MEM-03 PR-4：单键全局跨重启 pending-delete 索引的 KV 键——不属于任何单一
# session（详见 memory_migration_spine.MEMORY_KV_KEYS_MANIFEST 里的注释）。
PENDING_DELETE_INDEX_KV_KEY: str = MEMORY_KV_KEYS_MANIFEST["pending_delete_index"]

# ---------------------------------------------------------------------------
# 增量持久化 dirty-flag 机制（Item 12）
# ---------------------------------------------------------------------------

_VALID_SUBSYSTEMS = frozenset({"personality", "memory", "spine", "session"})


class _DirtyTracker:
    """实例级脏标记追踪器，避免模块级全局状态在多实例/热重载时污染。"""

    __slots__ = ("_subsystems", "_lock")

    def __init__(self):
        import threading

        self._subsystems: set[str] = set()
        self._lock = threading.Lock()

    def mark(self, subsystem: str) -> None:
        if subsystem in _VALID_SUBSYSTEMS:
            with self._lock:
                self._subsystems.add(subsystem)

    def swap(self) -> set[str]:
        """原子地取出当前脏集合并清空，避免 get+clear 之间的竞态。"""
        with self._lock:
            taken = self._subsystems
            self._subsystems = set()
            return taken

    def restore(self, subsystems: set[str]) -> None:
        if not subsystems:
            return
        with self._lock:
            self._subsystems.update(subsystems)

    def is_dirty(self) -> bool:
        with self._lock:
            return bool(self._subsystems)


# 模块级实例——StatePersistence.__init__ 中会替换为自己的实例
_dirty = _DirtyTracker()

# 模块级活跃持久化实例引用——StatePersistence.__init__ 中绑定。
# 让向后兼容的模块级 mark_dirty() 能触达实例级的合并落盘调度（debounce），
# 无需调用方持有 StatePersistence 句柄。多实例/热重载时指向最后一次构造的实例。
_active_persistence: StatePersistence | None = None


def mark_dirty(subsystem: str, session_key: str | None = None) -> None:
    """标记某子系统为脏（需要持久化）。向后兼容的模块级 API。

    Args:
        subsystem: 子系统名称（personality/memory/spine/session）。
        session_key: 可选会话标识。提供时额外触发该会话的合并 kernel 落盘
            （debounce 窗口内的多次脏标记合并为一次 persist_kernel），
            缓解多会话并发直写 KV/文件造成的 IO 突发。不提供时仅标记脏集合
            （完全向后兼容旧调用）。
    """
    _dirty.mark(subsystem)
    if session_key is not None and _active_persistence is not None:
        _active_persistence.schedule_kernel_persist(session_key)


def is_dirty() -> bool:
    """是否有任何子系统需要持久化。"""
    return _dirty.is_dirty()


def swap_dirty() -> set[str]:
    """原子地取出当前脏集合并清空。"""
    return _dirty.swap()


def _kv_archive_has_content(data: Any) -> bool:
    """MEM-02②：判断一份 KV 归档 dict 是否包含非空的记忆内容。

    覆盖新版 MemorySystem 格式（l1/l2/l3_nodes/l3_edges）与旧版
    SylanneMemoryState 格式（records）——两种都可能出现在存量 KV 数据里。
    """
    if not isinstance(data, dict):
        return False
    if any(data.get(k) for k in ("l1", "l2", "l3_nodes", "l3_edges")):
        return True
    return bool(data.get("records"))


# ---------------------------------------------------------------------------
# Item 73: 端到端加密记忆存储（简化版）
# ---------------------------------------------------------------------------


class EncryptedStorage:
    """可选的加密存储层。优先使用 Fernet (AES-128-CBC)，不可用时回退到 XOR。"""

    def __init__(self, password: str | None = None):
        self._key: bytes | None = None
        self._fernet = None
        if password:
            try:
                from hashlib import pbkdf2_hmac
                import os
                self._salt = os.urandom(16)
                raw_key = pbkdf2_hmac('sha256', password.encode(), self._salt, 100000)
                self._key = raw_key
                try:
                    import base64
                    from cryptography.fernet import Fernet
                    fernet_key = base64.urlsafe_b64encode(raw_key[:32])
                    self._fernet = Fernet(fernet_key)
                except ImportError:
                    pass
            except Exception:
                pass

    @property
    def enabled(self) -> bool:
        return self._key is not None

    def encrypt(self, data: bytes) -> bytes:
        if not self._key:
            return data
        if self._fernet:
            return self._fernet.encrypt(data)
        key_len = len(self._key)
        return bytes(b ^ self._key[i % key_len] for i, b in enumerate(data))

    def decrypt(self, data: bytes) -> bytes:
        if not self._key:
            return data
        if self._fernet:
            return self._fernet.decrypt(data)
        return self.encrypt(data)


class StatePersistence:
    """封装从插件委托出来的 kernel/buffer 持久化逻辑。

    采用双写策略：KV 存储为主路径（支持分布式/快速查询），
    文件 IO 为回退路径（向后兼容/离线可用）。
    通过 self._p 委托访问插件实例。
    """

    def __init__(self, plugin: PluginHost) -> None:
        """初始化持久化层。

        Args:
            plugin: Sylanne 插件实例。
        """
        self._p = plugin
        self._buffer_persist_timers: dict[str, asyncio.TimerHandle] = {}
        # 防抖 kernel 落盘的 per-session 定时器表（合并 kernel 持久化）。
        # 多会话并发标记脏时，窗口内合并为单次 persist_kernel，缓解 2 核 2G VPS
        # 上的 IO 突发。键为 session_key，值为待触发的 TimerHandle。
        self._kernel_persist_timers: dict[str, asyncio.TimerHandle] = {}
        # 绑定模块级活跃实例引用，让 mark_dirty(subsystem, session_key) 能触达
        # 本实例的合并落盘调度，无需调用方持有 StatePersistence 句柄。
        global _active_persistence
        _active_persistence = self
        # MEM-02③：_store.memory_systems 是 BoundedDict(maxsize=100)，超容量时
        # LRU 驱逐——驱逐前若无回调，被逐出的会话记忆直接从内存态消失（未落盘的
        # 最长 9 个 tick 静默丢失），且下次访问该 session 会重建全新空 MemorySystem，
        # 反过来有覆盖 KV 归档的风险。这里挂 on_evict 做 fire-and-forget 持久化，
        # 补上这条驱逐链路（BoundedDict 原生支持 on_evict，无需新造机制）。
        self._wire_memory_eviction_persistence()
        # MEM-03 PR-1：记忆写入单写咽喉 + 化身栅栏。所有记忆 KV 写按 session 串行化
        # （根治 F2 备份门 TOCTOU），占位者兜底回调返回 store 当前占位 MemorySystem。
        # loop 由 main.py initialize() 里 throat.bind_loop() 权威绑定；未绑定前 off-loop
        # 提交 fail-closed 丢弃（等价今日 coro.close()），on-loop 提交自绑定。
        from .memory_write_throat import MemoryWriteThroat

        self._throat = MemoryWriteThroat(occupant_getter=self._current_memory_occupant)
        # MEM-03 PR-4：跨重启 pending-delete 持久索引——进程内镜像（键=safe session
        # key）+ 全局锁（单键 KV，被所有 per-session drainer 并发改动，锁保护
        # "镜像镜像快照→整体落盘"这段临界区，防丢更新，见 §4/红队 must-fix）。
        # `asyncio.Lock()` 在 py>=3.10 无需 running loop 即可构造，此处在 __init__
        # （无 loop）里创建是安全的。
        self._pending_delete_mirror: dict[str, dict] = {}
        self._pending_delete_lock: asyncio.Lock = asyncio.Lock()
        # PR-4 gate（startup-ordering fail-open）：镜像由 initialize() 的
        # _scan_pending_deletes 载入；扫描完成前为空。在此之前 WebUI load 一律不准入
        # store（只返回游离副本渲染），防抢跑的读把崩溃残留的删除意图漏检、复活归档。
        self._pending_delete_scan_done: bool = False

    def _current_memory_occupant(self, session_key: str) -> Any:
        """返回某 session 在 store 里当前占位的 MemorySystem（占位者权威兜底用）。"""
        store = getattr(self._p, "_store", None)
        systems = getattr(store, "memory_systems", None) if store is not None else None
        if systems is None:
            return None
        try:
            return systems.get(session_key)
        except Exception:  # noqa: BLE001
            return None

    def _wire_memory_eviction_persistence(self) -> None:
        """把 memory_systems 的 LRU 驱逐接到落盘回调（幂等，可重复调用）。"""
        store = getattr(self._p, "_store", None)
        memory_map = getattr(store, "memory_systems", None)
        set_on_evict = getattr(memory_map, "set_on_evict", None)
        if callable(set_on_evict):
            set_on_evict(self._on_memory_system_evicted)

    def _on_memory_system_evicted(self, session_key: str, memory_system: Any) -> None:
        """memory_systems BoundedDict LRU 驱逐单个 session 条目时的回调。

        同步回调（BoundedDict.__setitem__ 内部触发，不能 await），驱逐前先判断
        是否有实际内容再决定是否 fire-and-forget 落盘，避免驱逐一堆空对象时
        制造无意义的 KV 写入。
        """
        has_content_fn = getattr(self._p, "_memory_system_has_content", None)
        try:
            has_content = (
                bool(has_content_fn(memory_system)) if callable(has_content_fn) else True
            )
        except Exception:
            has_content = True
        if not has_content:
            return
        # MEM-03 PR-1：直接经咽喉提交（双路径 submit 覆盖 on/off-loop）。驱逐回调可能在
        # stdlib WebUI 工作线程触发（off-loop），旧的 safe_ensure_future 在无 running loop
        # 的线程里会 coro.close() 静默丢弃这次落盘（暗病）；throat.submit 走绑定 loop 的
        # call_soon_threadsafe 保证真执行。fire-and-forget（驱逐语义本就不等待）。
        from .memory_system import MemorySystem

        fut = self._throat.submit(
            session_key,
            lambda: self._persist_memory_kv_only_impl(session_key, memory_system),
            kind="write",
            state=memory_system if isinstance(memory_system, MemorySystem) else None,
        )
        # MINOR-1：驱逐落盘是 fire-and-forget。on-loop 提交会返回一个无人 await 的 Future；
        # 若该 op 落盘失败，drainer 会 set_exception，未被检取则触发 asyncio "Future exception
        # was never retrieved" GC 噪音（错误本身已在 drainer 内 log）。挂个 done 回调消费掉
        # 异常/取消，消除噪音；off-loop 返回 None 时跳过。
        if fut is not None:
            fut.add_done_callback(lambda f: f.cancelled() or f.exception())

    async def _persist_memory_kv_only(self, session_key: str, state: Any) -> None:
        """只写 KV，不touch `_store` 的活体引用——专供驱逐场景使用。

        `save_sylanne_memory_state` 常规路径会顺手把 state 写回
        `_store.memory_systems` / `sylanne_memory_cache`（保持缓存与 KV 一致，
        绝大多数调用点需要这个副作用）。但驱逐场景恰恰是"这个对象正在或已经离开
        活体 store"——如果落盘复用那个方法，会在 pop 之后又把它重新塞回 store，
        制造出"明明驱逐了、entry 却还在"的假象。这里绕开 store 写回，只落 KV，
        语义更贴合调用现场。

        MEM-03 PR-1：公开壳，经单写咽喉串行化（与 save 同队列）。驱逐回调改为直接
        throat.submit（见 _on_memory_system_evicted）——off-loop 线程侧驱逐也能经绑定
        loop 执行，顺手修好今日线程侧驱逐落盘被 coro.close() 静默丢的暗病。

        MEM-03 PR-2：会话删除路径（`_on_session_deleted`）此前也会先调本壳做落盘
        桥接，再走清理删除——那正是 F4 窗口（persist 与 cleanup 无序竞态）的成因，
        现已废除（真删除的终态就是"已删除"，见 `_on_session_deleted`/
        `_session_deleted_delete_op`）。本壳目前唯一的生产调用方是驱逐回调；保留
        公开壳签名不删，避免破坏可能存在的直接调用方/未来复用。
        """
        if state is None:
            return
        from .memory_system import MemorySystem

        fut = self._throat.submit(
            session_key,
            lambda: self._persist_memory_kv_only_impl(session_key, state),
            kind="write",
            state=state if isinstance(state, MemorySystem) else None,
        )
        if fut is not None:
            await fut

    async def _persist_memory_kv_only_impl(self, session_key: str, state: Any) -> None:
        """驱逐/释放落盘真逻辑——只准经咽喉 op 调用。"""
        if state is None:
            return
        # MEM-02② (FIX E)：驱逐/释放落盘同样是一条真实 KV 写路径。若一个未补水的实例
        # 在补水任务跑完前就被 LRU 挤出（挤出后挂起的 hydrate 会因活体不在而 no-op），
        # 用它覆盖非空归档就是那条"驱逐清零"链路——这里套同一个 fail-closed 守卫拦住。
        if not await self._refuse_unhydrated_overwrite(session_key, state):
            return
        kv_key = self.sylanne_memory_kv_key(session_key)
        put_fn = getattr(self._p, "put_kv_data", None)
        if put_fn and callable(put_fn):
            data = state.to_dict() if hasattr(state, "to_dict") else state
            # MEM-01：与 save_sylanne_memory_state 同一条闸门——驱逐/释放场景也是
            # 一条真实的 KV 写入路径，不能因为绕开了 store 写回就也绕开备份闸门。
            if isinstance(data, dict) and data.get("version") == "3.0.0":
                backup_key = self.sylanne_memory_backup_v2_kv_key(session_key)
                gate_ok = await self._ensure_v2_backup_before_v3_write(
                    session_key, kv_key, backup_key
                )
                if not gate_ok:
                    return
            await put_fn(kv_key, data)

    # ------------------------------------------------------------------
    # KV 键生成辅助方法
    # ------------------------------------------------------------------

    def kernel_kv_key(self, session_key: str) -> str:
        """生成 kernel 状态的 KV 存储键。"""
        safe = self._safe_session_key(session_key)
        return f"sylanne_kernel_{safe}"

    def buffer_kv_key(self, session_key: str) -> str:
        """生成对话缓冲区的 KV 存储键。"""
        safe = self._safe_session_key(session_key)
        return f"sylanne_buffer_{safe}"

    def has_kv_api(self) -> bool:
        """检查 AstrBot KV 存储 API 是否可用。"""
        return hasattr(self._p, "put_kv_data") and callable(self._p.put_kv_data)

    # ------------------------------------------------------------------
    # 各引擎子系统的 KV 键生成
    # ------------------------------------------------------------------

    def kv_key(self, session_key: str) -> str:
        """情感状态 KV 键。"""
        safe = self._safe_session_key(session_key)
        return f"emotion_state:{safe}"

    def humanlike_kv_key(self, session_key: str) -> str:
        """类人状态 KV 键。"""
        safe = self._safe_session_key(session_key)
        return f"humanlike_state:{safe}"

    def lifelike_learning_kv_key(self, session_key: str) -> str:
        """类生命学习状态 KV 键。"""
        safe = self._safe_session_key(session_key)
        return f"lifelike_learning:{safe}"

    def personality_drift_kv_key(self, session_key: str) -> str:
        """人格漂移状态 KV 键。"""
        safe = self._safe_session_key(session_key)
        return f"personality_drift:{safe}"

    def moral_repair_kv_key(self, session_key: str) -> str:
        """道德修复状态 KV 键。"""
        safe = self._safe_session_key(session_key)
        return f"moral_repair_state:{safe}"

    def fallibility_kv_key(self, session_key: str) -> str:
        """易错性状态 KV 键。"""
        safe = self._safe_session_key(session_key)
        return f"fallibility_state:{safe}"

    def psychological_kv_key(self, session_key: str) -> str:
        """心理筛查状态 KV 键。"""
        safe = self._safe_session_key(session_key)
        return f"psychological_screening:{safe}"

    def sylanne_memory_kv_key(self, session_key: str) -> str:
        """Sylanne 记忆状态 KV 键。"""
        safe = session_key.replace("/", "_").replace("\\", "_")
        return f"sylanne_memory_state:{safe}"

    def sylanne_memory_backup_v2_kv_key(self, session_key: str) -> str:
        """MEM-01：v2→v3 首写前备份键（此后只读，永不被覆盖）。"""
        safe = session_key.replace("/", "_").replace("\\", "_")
        return f"sylanne_memory_state_backup_v2:{safe}"

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    def _safe_session_key(self, session_key: str) -> str:
        """将 session_key 转换为 KV 键安全的字符串（带缓存）。"""
        cache = getattr(self._p, "_safe_session_key_cache", None)
        if cache is None:
            self._p._safe_session_key_cache = {}
            cache = self._p._safe_session_key_cache
        if session_key in cache:
            return cache[session_key]
        safe = session_key.replace("/", "_").replace("\\", "_")
        cache[session_key] = safe
        return safe

    # ------------------------------------------------------------------
    # Kernel 持久化
    # ------------------------------------------------------------------

    async def persist_kernel(self, session_key: str, host: SylanneAlphaHost) -> None:
        """保存 kernel 状态：KV 存储（主路径）+ 文件 IO（回退路径）。

        双写确保：KV 存储提供快速查询，文件提供向后兼容和离线恢复能力。
        使用增量持久化：仅当 dirty set 非空时执行 save，save 后清空 dirty set。
        使用 CRC32 校验和确保数据完整性。

        Args:
            session_key: 会话标识。
            host: 包含 kernel 和 runtime 的 Host 实例。
        """
        import json as _json

        dirty_set = swap_dirty() if is_dirty() else set()
        snapshot = host.kernel.snapshot()

        if dirty_set and self.has_kv_api():
            try:
                # 只序列化 dirty 子系统对应的数据
                partial_snapshot = self._extract_dirty_snapshot(snapshot, dirty_set)
                # 计算 CRC32 校验和
                data_bytes = _json.dumps(
                    partial_snapshot, ensure_ascii=False, sort_keys=True
                ).encode("utf-8")
                checksum = zlib.crc32(data_bytes) & 0xFFFFFFFF
                partial_snapshot["_checksum"] = checksum

                kv_key = self.kernel_kv_key(session_key)
                # 保存备份（上一次成功的数据）
                backup_key = f"{kv_key}_backup"
                try:
                    existing = await self._p.get_kv_data(kv_key, None)
                    if existing and isinstance(existing, dict):
                        await self._p.put_kv_data(backup_key, existing)
                except Exception:
                    pass  # 备份失败不阻塞主路径

                await self._p.put_kv_data(kv_key, partial_snapshot)
            except Exception as e:
                _dirty.restore(dirty_set)
                logger.warning(f"Sylanne kernel KV persist: {e}", exc_info=True)
        # 始终写文件（向后兼容/回退），offload 到线程避免阻塞事件循环
        try:
            await asyncio.to_thread(host.runtime.save, host.kernel)
        except Exception as e:
            logger.warning(f"Sylanne kernel file persist: {e}", exc_info=True)

    def _extract_dirty_snapshot(
        self, snapshot: dict[str, Any], dirty_set: set[str]
    ) -> dict[str, Any]:
        """根据 dirty set 提取需要持久化的子系统数据。

        Args:
            snapshot: 完整的 kernel 快照。
            dirty_set: 需要持久化的子系统名称集合。

        Returns:
            仅包含脏子系统数据的部分快照。
        """
        # 映射子系统名称到快照中的键
        subsystem_keys = {
            "personality": ["personality", "moral_repair", "fallibility"],
            "memory": ["body"],
            "spine": ["computation", "audit"],
            "session": [
                "session_key",
                "turns",
                "last_event",
                "previous_event",
                "relational_time",
            ],
        }
        # 始终包含 schema_version 和 session_key
        result: dict[str, Any] = {
            "schema_version": snapshot.get("schema_version"),
            "session_key": snapshot.get("session_key"),
            "_dirty_subsystems": list(dirty_set),
        }
        for subsystem in dirty_set:
            for key in subsystem_keys.get(subsystem, []):
                if key in snapshot:
                    result[key] = snapshot[key]
        return result

    def persist_kernel_sync(self, session_key: str, host: SylanneAlphaHost) -> None:
        """同步写入 kernel 状态（仅文件 IO，用于 LRU 驱逐等非异步上下文）。

        Args:
            session_key: 会话标识。
            host: Host 实例。
        """
        try:
            host.runtime.save(host.kernel)
        except Exception as e:
            logger.warning(f"Sylanne kernel sync persist: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Buffer 持久化
    # ------------------------------------------------------------------

    async def persist_buffer(
        self, session_key: str, host: SylanneAlphaHost, buf_dict: dict[str, Any]
    ) -> None:
        """保存对话缓冲区：KV 存储（主路径）+ 文件 IO（回退路径）。

        Args:
            session_key: 会话标识。
            host: Host 实例。
            buf_dict: 缓冲区序列化字典。
        """
        if self.has_kv_api():
            try:
                await self._p.put_kv_data(self.buffer_kv_key(session_key), buf_dict)
            except Exception as e:
                logger.warning(f"Sylanne buffer KV persist: {e}", exc_info=True)
        # 始终写文件（向后兼容/回退），offload 到线程避免阻塞事件循环
        try:
            await asyncio.to_thread(host.runtime.save_buffer, session_key, buf_dict)
        except Exception as e:
            logger.warning(f"Sylanne buffer file persist: {e}", exc_info=True)

    async def load_buffer_data(
        self, session_key: str, host: SylanneAlphaHost
    ) -> dict[str, Any] | None:
        """加载对话缓冲区：KV 存储（主路径）+ 文件 IO（回退路径）。

        Args:
            session_key: 会话标识。
            host: Host 实例。

        Returns:
            缓冲区字典，无数据时返回 None。
        """
        if self.has_kv_api():
            try:
                data = await self._p.get_kv_data(self.buffer_kv_key(session_key), None)
                if data and isinstance(data, dict):
                    return data
            except Exception as e:
                logger.debug(f"Sylanne skip: {e}")
        # 回退到文件 IO
        return await asyncio.to_thread(host.runtime.load_buffer, session_key)

    # ------------------------------------------------------------------
    # 防抖 Buffer 持久化调度
    # ------------------------------------------------------------------

    def schedule_buffer_persist(self, session_key: str) -> None:
        """调度防抖的 buffer 持久化——等待 5 秒，合并多次写入为一次。

        高频对话场景下避免每条消息都触发 IO，通过 call_later 延迟执行，
        新的调度会取消前一个未执行的定时器。

        Args:
            session_key: 会话标识。
        """
        if session_key in self._buffer_persist_timers:
            self._buffer_persist_timers[session_key].cancel()
        try:
            loop = asyncio.get_running_loop()
            self._buffer_persist_timers[session_key] = loop.call_later(
                5.0,
                lambda sk=session_key: safe_ensure_future(
                    self._do_buffer_persist(sk), name="buffer_persist"
                ),
            )
        except RuntimeError:
            pass  # 无事件循环时静默跳过（如测试环境）

    async def _do_buffer_persist(self, session_key: str) -> None:
        """实际执行 buffer 持久化（由 schedule_buffer_persist 延迟触发）。"""
        self._buffer_persist_timers.pop(session_key, None)
        buf = self._p._store.conversation_buffers.get(session_key)
        if not buf:
            return
        host = self._p._store.hosts.get(session_key)
        if not host or not hasattr(host, "runtime"):
            return
        buf_dict = buf.to_dict()
        await self.persist_buffer(session_key, host, buf_dict)

    # ------------------------------------------------------------------
    # 防抖 Kernel 持久化调度（合并落盘，缓解 IO 突发）
    # ------------------------------------------------------------------

    def _kernel_persist_debounce_seconds(self) -> float:
        """读取 kernel 防抖窗口（秒），默认 4.0。"""
        cfg = getattr(self._p, "config", None) or {}
        try:
            return float(cfg.get("sylanne_alpha_kernel_persist_debounce_seconds", 4.0))
        except (TypeError, ValueError):
            return 4.0

    def schedule_kernel_persist(self, session_key: str) -> None:
        """调度防抖的 kernel 持久化——窗口内多次脏标记合并为一次 persist_kernel。

        与 schedule_buffer_persist 不同：这里采用「首个调度赢」策略——若该会话已有
        待触发的定时器则跳过，不重置窗口。这样窗口内累积的多次 mark_dirty 共享同一个
        dirty set，到点一次性落盘，避免高频脏标记把落盘无限期推后（饥饿）。

        Args:
            session_key: 会话标识。
        """
        if session_key in self._kernel_persist_timers:
            return  # 已有待触发定时器，合并到该次落盘
        try:
            loop = asyncio.get_running_loop()
            delay = self._kernel_persist_debounce_seconds()
            self._kernel_persist_timers[session_key] = loop.call_later(
                delay,
                lambda sk=session_key: safe_ensure_future(
                    self._do_kernel_persist(sk), name="kernel_persist"
                ),
            )
        except RuntimeError:
            pass  # 无事件循环时静默跳过（如测试环境）

    async def _do_kernel_persist(self, session_key: str) -> None:
        """实际执行 kernel 持久化（由 schedule_kernel_persist 延迟触发）。"""
        self._kernel_persist_timers.pop(session_key, None)
        host = self._p._store.hosts.get(session_key)
        if not host or not hasattr(host, "runtime"):
            return
        await self.persist_kernel(session_key, host)

    async def flush_pending_kernel_persists(self) -> None:
        """卸载/关闭前立即排干所有待触发的 kernel 落盘。

        取消所有挂起的定时器，并对每个会话同步执行一次 persist_kernel，
        保证 debounce 窗口内累积但尚未落盘的脏状态不随关机丢失。
        须在后台任务被 cancel 之前调用（否则 fire-and-forget 落盘会被反手取消）。
        """
        timers = self._kernel_persist_timers
        self._kernel_persist_timers = {}
        pending_keys = list(timers.keys())
        for handle in timers.values():
            try:
                handle.cancel()
            except Exception:
                pass
        for sk in pending_keys:
            host = self._p._store.hosts.get(sk)
            if not host or not hasattr(host, "runtime"):
                continue
            try:
                await self.persist_kernel(sk, host)
            except Exception as e:
                logger.warning(
                    f"Sylanne kernel flush on terminate ({sk}): {e}", exc_info=True
                )

    def _cleanup_pending_timers(self, session_key: str) -> None:
        """取消某会话在会话释放时的待触发 buffer/kernel 防抖定时器（CP8-P3）。

        session 释放时确保防抖队列中该 session 的定时器被立即取消，
        避免防抖定时器在会话被清理后仍在事件循环中触发，导致"释放后访问"或
        失孤 fire-and-forget 任务。在 _on_session_deleted 中被调用，且须在
        p._store.release_session 之后（后者清理 hosts 等，防抖落盘任务会检查 hosts.get）。

        Args:
            session_key: 会话标识。
        """
        # 取消 buffer 防抖定时器（若存在）
        if session_key in self._buffer_persist_timers:
            try:
                self._buffer_persist_timers[session_key].cancel()
            except Exception:
                pass
            self._buffer_persist_timers.pop(session_key, None)

        # 取消 kernel 防抖定时器（若存在）
        if session_key in self._kernel_persist_timers:
            try:
                self._kernel_persist_timers[session_key].cancel()
            except Exception:
                pass
            self._kernel_persist_timers.pop(session_key, None)

    # ------------------------------------------------------------------
    # 启动时 Buffer 恢复
    # ------------------------------------------------------------------

    def restore_buffers_on_boot(self) -> None:
        """插件启动时从文件恢复对话缓冲区（同步回退路径）。

        KV 数据通过 persist_buffer 保持同步，此处文件 IO 等效。
        异步 KV 加载在同步上下文中不可用，故使用文件回退。
        """
        from .memory_system import ConversationBuffer

        for sk, host in self._p._store.hosts.snapshot_items():
            if not hasattr(host, "runtime"):
                continue
            data = host.runtime.load_buffer(sk)
            if data and isinstance(data, dict):
                self._p._store.conversation_buffers.set(sk, ConversationBuffer.from_dict(data))

    # ------------------------------------------------------------------
    # 引擎状态：加载/保存/删除（情感核心）
    # ------------------------------------------------------------------

    async def load_state(
        self, session_key: str, persona_profile: Any = None, *, now: float = 0.0
    ) -> Any:
        """加载情感引擎状态（带内存缓存和 CRC32 完整性校验）。

        优先从内存缓存读取，缓存未命中时查询 KV 存储。
        加载时验证 CRC32 校验和，不匹配则尝试加载备份。

        Args:
            session_key: 会话标识。
            persona_profile: 人格配置（预留参数）。
            now: 当前时间戳（预留参数）。

        Returns:
            情感状态数据，无数据时返回 None。
        """
        import json as _json

        cache = getattr(self._p, "_engine_cache", None)
        if cache is None:
            self._p._engine_cache = {}
            cache = self._p._engine_cache
        if session_key in cache:
            return cache[session_key]
        key = self.kv_key(session_key)
        get_kv = getattr(self._p, "get_kv_data", None)
        if get_kv and callable(get_kv):
            data = await get_kv(key, None)
            # CRC32 完整性校验
            if data is not None and isinstance(data, dict):
                stored_checksum = data.pop("_checksum", None)
                if stored_checksum is not None:
                    data_bytes = _json.dumps(
                        data, ensure_ascii=False, sort_keys=True
                    ).encode("utf-8")
                    computed_checksum = zlib.crc32(data_bytes) & 0xFFFFFFFF
                    if computed_checksum != stored_checksum:
                        logger.error(
                            f"Sylanne CRC32 mismatch for {key}: "
                            f"stored={stored_checksum}, computed={computed_checksum}. "
                            f"Attempting backup load."
                        )
                        # 尝试加载备份
                        backup_key = f"{key}_backup"
                        backup_data = await get_kv(backup_key, None)
                        if backup_data and isinstance(backup_data, dict):
                            backup_checksum = backup_data.pop("_checksum", None)
                            if backup_checksum is not None:
                                backup_bytes = _json.dumps(
                                    backup_data, ensure_ascii=False, sort_keys=True
                                ).encode("utf-8")
                                backup_computed = (
                                    zlib.crc32(backup_bytes) & 0xFFFFFFFF
                                )
                                if backup_computed == backup_checksum:
                                    logger.info(
                                        f"Sylanne backup CRC32 valid for {key}, "
                                        f"using backup data."
                                    )
                                    data = backup_data
                                else:
                                    logger.error(
                                        f"Sylanne backup CRC32 also invalid for {key}."
                                    )
                            else:
                                # 备份无校验和，直接使用
                                data = backup_data
        else:
            data = None
        if data is not None:
            cache[session_key] = data
            return data
        return data

    async def save_state(self, session_key: str, state: Any = None) -> None:
        """保存情感引擎状态（占位，当前为空实现）。"""
        pass

    async def delete_state(self, session_key: str) -> None:
        """删除情感引擎状态（占位，当前为空实现）。"""
        pass

    # ------------------------------------------------------------------
    # 类人状态（占位接口）
    # ------------------------------------------------------------------

    async def load_humanlike_state(self, session_key: str) -> Any:
        """加载类人状态。"""
        return None

    async def save_humanlike_state(self, session_key: str, state: Any = None) -> None:
        """保存类人状态。"""
        pass

    async def delete_humanlike_state(self, session_key: str) -> None:
        """删除类人状态。"""
        pass

    # ------------------------------------------------------------------
    # 心理筛查状态（占位接口）
    # ------------------------------------------------------------------

    async def load_psychological_state(self, session_key: str) -> Any:
        """加载心理筛查状态。"""
        return None

    async def save_psychological_state(
        self, session_key: str, state: Any = None
    ) -> None:
        """保存心理筛查状态。"""
        pass

    async def delete_psychological_state(self, session_key: str) -> None:
        """删除心理筛查状态。"""
        pass

    # ------------------------------------------------------------------
    # 类生命学习状态（占位接口）
    # ------------------------------------------------------------------

    async def load_lifelike_learning_state(
        self, session_key: str, **kwargs: Any
    ) -> Any:
        """加载类生命学习状态。"""
        return None

    async def save_lifelike_learning_state(
        self, session_key: str, state: Any = None
    ) -> None:
        """保存类生命学习状态。"""
        pass

    async def delete_lifelike_learning_state(self, session_key: str) -> None:
        """删除类生命学习状态。"""
        pass

    # ------------------------------------------------------------------
    # 人格漂移状态（占位接口）
    # ------------------------------------------------------------------

    async def load_personality_drift_state(
        self, session_key: str, **kwargs: Any
    ) -> Any:
        """加载人格漂移状态。"""
        return None

    async def save_personality_drift_state(
        self, session_key: str, state: Any = None
    ) -> None:
        """保存人格漂移状态。"""
        pass

    async def delete_personality_drift_state(self, session_key: str) -> None:
        """删除人格漂移状态。"""
        pass

    # ------------------------------------------------------------------
    # 道德修复状态（占位接口）
    # ------------------------------------------------------------------

    async def load_moral_repair_state(self, session_key: str) -> Any:
        """加载道德修复状态。"""
        return None

    async def save_moral_repair_state(
        self, session_key: str, state: Any = None
    ) -> None:
        """保存道德修复状态。"""
        pass

    async def delete_moral_repair_state(self, session_key: str) -> None:
        """删除道德修复状态。"""
        pass

    # ------------------------------------------------------------------
    # 易错性状态（占位接口）
    # ------------------------------------------------------------------

    async def load_fallibility_state(self, session_key: str) -> Any:
        """加载易错性状态。"""
        return None

    async def save_fallibility_state(self, session_key: str, state: Any = None) -> None:
        """保存易错性状态。"""
        pass

    async def delete_fallibility_state(self, session_key: str) -> None:
        """删除易错性状态。"""
        pass

    # ------------------------------------------------------------------
    # 群体氛围状态（占位接口）
    # ------------------------------------------------------------------

    async def load_group_atmosphere_state(self, session_key: str) -> Any:
        """加载群体氛围状态。"""
        return None

    # ------------------------------------------------------------------
    # Sylanne 记忆状态
    # ------------------------------------------------------------------

    async def _refuse_unhydrated_overwrite(self, session_key: str, state: Any) -> bool:
        """MEM-02② fail-closed 守卫：返回 True 表示可以安全落盘 `state`；False 表示
        本次落盘会覆盖一份尚未合并进活体的非空 KV 归档，应跳过。

        一个 `_hydrated=False` 的 MemorySystem 意味着补水（hydrate_memory_system）
        还没把 KV 归档合并进来——它的 to_dict()（空、或只含本会话补水前零星写入的
        几条新内容）一旦写回 KV，就把那份尚未合并的历史抹掉了。所以：

          - 已 `_hydrated`（或不是 MemorySystem）→ 放行（归档已合并 / 不适用）。
          - 未补水，但成功读到 KV 归档且**为空** → 放行（没有可保护的内容；不在此处
            翻 `_hydrated`，把该标记的唯一权威留给 hydrate_memory_system，避免与补水
            任务竞争地设置同一标记）。
          - 未补水且 KV 归档**非空** → 拒绝（无论活体当前是空还是只有零星内容，都
            不能盖掉未合并的归档）。
          - 读 KV 归档时**抛异常** → 拒绝（fail-closed）。绝不把"读失败"当成"归档不
            存在"——那正是重启清零 bug 的 fail-open 根因。
        """
        from .memory_system import MemorySystem

        if not isinstance(state, MemorySystem):
            return True
        if getattr(state, "_hydrated", True):
            return True
        get_fn = getattr(self._p, "get_kv_data", None)
        if not callable(get_fn):
            return True  # 无 KV 读 API——本守卫不适用
        kv_key = self.sylanne_memory_kv_key(session_key)
        try:
            existing = await get_fn(kv_key, None)
        except Exception as e:
            logger.warning(
                "Sylanne memory guard: 读取现有 KV 归档失败，fail-closed 跳过本次落盘 "
                f"（未补水实例，无法证明归档为空，拒绝覆盖）({session_key!r}): {e}"
            )
            return False
        if _kv_archive_has_content(existing):
            if not getattr(state, "_empty_write_warned", False):
                logger.warning(
                    "Sylanne memory: refused to overwrite non-empty KV archive for "
                    f"session {session_key!r} with an un-hydrated MemorySystem "
                    "(hydration still pending/failed); skipping this persist"
                )
                try:
                    state._empty_write_warned = True
                except Exception:
                    pass
            return False
        return True

    def _backup_blob_is_valid(self, blob: Any) -> bool:
        """MEM-01 (FIX D)：校验一份既有 v2 备份 blob 是否结构完整且 CRC 自洽。

        备份门 step-1 不能只凭 `backup_key` 存在就放行 v3 写入——一次失败的备份写入
        可能在 `backup_key` 上留下损坏 blob，若只看"非空"就放行，等于在没有可信备份
        的情况下继续覆盖旧数据。这里对既有备份重新算 CRC 比对，只有自洽才算数。
        """
        if not isinstance(blob, dict) or "data" not in blob or "_crc32" not in blob:
            return False
        try:
            import json as _json

            payload = _json.dumps(
                blob.get("data"), ensure_ascii=False, sort_keys=True
            ).encode("utf-8")
            return (zlib.crc32(payload) & 0xFFFFFFFF) == blob.get("_crc32")
        except Exception:
            return False

    async def _delete_kv_best_effort(self, key: str) -> None:
        """尽力删除一个 KV 键（无删除 API 或删除失败都只 debug 记录，不抛）。"""
        delete_fn = getattr(self._p, "delete_kv_data", None)
        if callable(delete_fn):
            try:
                await delete_fn(key)
            except Exception as e:
                logger.debug(
                    f"Sylanne memory: best-effort delete of {key!r} failed: {e}"
                )

    async def save_sylanne_memory_state(
        self, session_key: str, state: Any = None
    ) -> None:
        """保存 Sylanne 记忆状态到缓存和 KV 存储。

        同时更新内存缓存和 _memory_systems 引用，确保后续读取一致。

        MEM-03 PR-1：公开壳，签名不变。经单写咽喉把真逻辑（_impl）按 session 串行化——
        同一会话的周期 save 与驱逐落盘不再并发穿插备份门（关掉 F2）。栅栏携带 state 印章，
        执行前验章（PR-1 惰性：无 bump 调用方，恒通过）。

        Args:
            session_key: 会话标识。
            state: MemorySystem 实例或可序列化的状态对象。
        """
        if state is None:
            return
        from .memory_system import MemorySystem

        fut = self._throat.submit(
            session_key,
            lambda: self._save_sylanne_memory_state_impl(session_key, state),
            kind="write",
            state=state if isinstance(state, MemorySystem) else None,
        )
        if fut is not None:
            await fut

    async def _save_sylanne_memory_state_impl(self, session_key: str, state: Any) -> None:
        """save 真逻辑——只准经咽喉 op 调用（勿直接 await，会绕过串行化与栅栏）。"""
        from .memory_system import MemorySystem

        # MEM-02② (强化 fail-closed)：单点闸门——详见 _refuse_unhydrated_overwrite。
        # 一个尚未补水（_hydrated=False）的 MemorySystem 还没把 KV 归档合并进来，用它
        # 的 to_dict()（空、或只含补水前零星新内容）覆盖一份非空归档 = 丢失尚未合并的
        # 历史。守卫 fail-closed：连"归档是否为空"都读不到（KV 读异常）时也拒绝写入，
        # 绝不把异常当成"归档不存在"（那正是重启清零的 fail-open 根因）。显式清除
        # （WebUI meltdown）走 delete_sylanne_memory_state，不经过本方法，不受影响。
        if not await self._refuse_unhydrated_overwrite(session_key, state):
            return

        self._p._store.sylanne_memory_cache.set(session_key, state)
        if isinstance(state, MemorySystem):
            self._p._store.memory_systems.set(session_key, state)
        kv_key = self.sylanne_memory_kv_key(session_key)
        put_fn = getattr(self._p, "put_kv_data", None)
        if put_fn and callable(put_fn):
            data = state.to_dict() if hasattr(state, "to_dict") else state
            # MEM-01：写入 v3 格式前的一次性备份 + CRC32 校验闸门（write-gate，
            # 不是"写了就算"）。只在即将写入 v3 且尚未做过这次备份时触发；backup
            # 验证失败 fail-closed 跳过本次写入，旧数据原样保留在 kv_key 上不动。
            # PR-1：备份门整段现在在咽喉 op 内执行——同 session 并发首写天然串行，
            # 其 TOCTOU（Phase-0 遗留 F2）由串行化根治。
            if isinstance(data, dict) and data.get("version") == "3.0.0":
                backup_key = self.sylanne_memory_backup_v2_kv_key(session_key)
                gate_ok = await self._ensure_v2_backup_before_v3_write(
                    session_key, kv_key, backup_key
                )
                if not gate_ok:
                    return
            await put_fn(kv_key, data)

    async def _ensure_v2_backup_before_v3_write(
        self, session_key: str, kv_key: str, backup_key: str
    ) -> bool:
        """MEM-01：v3 首写前的备份 + CRC32 验证闸门。

        流程：
          1. backup_key 已存在（此前已经做过备份）——直接放行，backup_key 此后只读，
             不会被本方法或任何其他路径覆盖。
          2. kv_key 现有内容为空（全新 session，没有旧数据可备份）——直接放行。
          3. 否则：读现有 winning KV blob → 算 CRC32 → 写入 backup_key（连同 CRC）→
             立刻读回 backup_key → 比对 CRC。只有验证通过才放行调用方继续写 v3。

        任何一步读/写异常，或 CRC 校验不一致，一律 fail-closed 返回 False——调用方
        应放弃本次 v3 写入，宁可这次的新内容暂不落盘，也不能在没有验证过的备份
        凭据下就先斩后奏地覆盖旧数据。

        【已知局限，Phase-0 不修，留 Phase-1/MEM-03 单写咽喉解决】本方法是无锁的
        read-check-write，跨多个 await 挂起点。同一 session 若在"首次 v3 写入"这一拍
        有并发落盘（周期 save + fire-and-forget 驱逐/释放落盘），理论上存在 TOCTOU：
        后到者 step-1 读到 stale=None、在前者写完 v2 备份后又用 v3 快照覆盖 backup_key，
        破坏"备份写一次此后只读"的不变量。影响面仅限【回滚快照】——主键 v3 内容不丢、
        用户在线记忆不受影响，故不构成红线数据丢失；根治需 per-session 写序列化，属
        MEM-03 单一写咽喉的职责，本阶段仅记录不引入锁（避免热路径加锁的新风险面）。

        Returns:
            True 表示可以安全继续写入 v3；False 表示应跳过本次写入。
        """
        import json as _json

        get_fn = getattr(self._p, "get_kv_data", None)
        put_fn = getattr(self._p, "put_kv_data", None)
        if not callable(get_fn) or not callable(put_fn):
            return True  # 无 KV API（如纯文件回退环境）——本闸门不适用，不阻塞写入

        try:
            already_backed_up = await get_fn(backup_key, None)
        except Exception as e:
            logger.warning(
                f"Sylanne memory v3 backup: 读取已有备份键失败，fail-closed 跳过 "
                f"本次写入 ({session_key!r}): {e}"
            )
            return False
        if already_backed_up is not None:
            # FIX D：不能只凭 backup_key 存在就放行——一次失败的备份写可能在此留下
            # 损坏 blob，若照放行等于在没有可信备份的情况下继续覆盖旧数据。重新校验
            # CRC，只有自洽的既有备份才算数；损坏的删掉、往下重新备份（此刻 kv_key
            # 尚未被 v3 写过、仍是 v2，重新备份快照的正是那份 v2，语义正确）。
            if self._backup_blob_is_valid(already_backed_up):
                return True
            logger.warning(
                "Sylanne memory v3 backup: 既有备份完整性校验失败（损坏/CRC 不符），"
                f"删除后重新备份再放行 v3 写入 ({session_key!r})"
            )
            await self._delete_kv_best_effort(backup_key)

        try:
            existing = await get_fn(kv_key, None)
        except Exception as e:
            logger.warning(
                f"Sylanne memory v3 backup: 读取现有 KV 归档失败，fail-closed 跳过 "
                f"本次写入 ({session_key!r}): {e}"
            )
            return False
        if existing is None:
            return True  # 没有旧数据可备份

        try:
            payload_bytes = _json.dumps(
                existing, ensure_ascii=False, sort_keys=True
            ).encode("utf-8")
            checksum = zlib.crc32(payload_bytes) & 0xFFFFFFFF
            await put_fn(backup_key, {"data": existing, "_crc32": checksum})
            verify = await get_fn(backup_key, None)
            if not isinstance(verify, dict):
                logger.error(
                    "Sylanne memory v3 backup: 回读备份失败（非 dict），fail-closed "
                    f"跳过本次 v3 写入 ({session_key!r})"
                )
                # FIX D：删掉这次写坏的备份 blob，否则下次 step-1 会把它当"已备份"
                # 而放行 v3 写入（在没有可信备份下覆盖旧数据）——校验失败必须让
                # backup_key 回到"没有备份"状态，下次重新完整地备份一遍。
                await self._delete_kv_best_effort(backup_key)
                return False
            verify_bytes = _json.dumps(
                verify.get("data"), ensure_ascii=False, sort_keys=True
            ).encode("utf-8")
            verify_checksum = zlib.crc32(verify_bytes) & 0xFFFFFFFF
            if verify_checksum != verify.get("_crc32") or verify_checksum != checksum:
                logger.error(
                    "Sylanne memory v3 backup: CRC32 校验不一致 "
                    f"(write={checksum} verify_stored={verify.get('_crc32')} "
                    f"verify_recomputed={verify_checksum})，fail-closed 跳过本次 "
                    f"v3 写入 ({session_key!r})，旧数据原样保留"
                )
                await self._delete_kv_best_effort(backup_key)  # FIX D：清掉坏备份
                return False
        except Exception as e:
            logger.error(
                f"Sylanne memory v3 backup: 备份/校验过程异常，fail-closed 跳过 "
                f"本次写入 ({session_key!r}): {e}",
                exc_info=True,
            )
            await self._delete_kv_best_effort(backup_key)  # FIX D：清掉可能的半写备份
            return False

        logger.info(
            f"Sylanne memory: v2→v3 首次写入前备份已验证通过 "
            f"(session={session_key!r}, backup_key={backup_key!r})"
        )
        return True

    async def _persist_memory_quarantine(
        self, session_key: str, entries: list[dict[str, Any]]
    ) -> None:
        """MEM-01：把记忆恢复期间摘除的坏记录写入 quarantine 侧车 KV。

        合并追加而非覆盖（同一 session 多次加载都可能产生新的 quarantine 条目），
        cap 500 条防止无界增长——quarantine 只是审计留痕，不是主存储。

        MEM-03 PR-3（design §3 臂⑧）：本方法自身签名/内部逻辑不变（仍是无锁的
        get→merge→put），调用方决定是否/何时调它才是本 PR 收编的重点，两条路径
        分别处理：
          - `hydrate_memory_system`：本身整体是一个 `kind="hydrate"` 咽喉 op 的
            factory，调用处内联 `await`（而非 fire-and-forget），让这次侧车写钉在
            本 op 的执行窗口内，不会被同 session 后面排队的 delete op 抢先执行
            后又被姗姗来迟的写入穿越复活。
          - `load_sylanne_memory_state`：本身不是咽喉 op（无法直接借咽喉的顺序化
            保证），调用处改为在 `token`/`has_pending_delete` 双条件（见
            `_load_admit_ok`）放行时才调用——会话删除进行中/已过期的归档，其
            quarantine 明文条目也不再另行落盘。仍不完全排除"两次并发 load 各自
            get→merge→put 互相覆盖"这类与删除无关的既有竞态（未被本 PR 处理，
            见 PR-3 交付说明的已知局限）。
        """
        if not entries:
            return
        if not self.has_kv_api():
            return
        from .memory_legacy_formats import quarantine_kv_key

        safe = self._safe_session_key(session_key)
        key = quarantine_kv_key(safe)
        get_fn = getattr(self._p, "get_kv_data", None)
        put_fn = getattr(self._p, "put_kv_data", None)
        if not callable(get_fn) or not callable(put_fn):
            return
        try:
            existing = await get_fn(key, None)
            existing_list = (
                existing.get("items", []) if isinstance(existing, dict) else []
            )
            if not isinstance(existing_list, list):
                existing_list = []
            merged = existing_list + list(entries)
            merged = merged[-500:]
            await put_fn(key, {"items": merged, "count": len(merged)})
        except Exception as e:
            logger.debug(
                f"Sylanne memory quarantine persist failed for {session_key!r}: {e}"
            )

    # ------------------------------------------------------------------
    # MEM-03 PR-4：跨重启 pending-delete 持久索引
    # ------------------------------------------------------------------
    #
    # 设计 §4 + 红队 must-fix：进程内咽喉的 `_epochs`/`has_pending_delete` 只在
    # 本次进程运行期间有效——若进程在 delete/purge op 跑到一半时崩溃（或有界
    # 重试耗尽、或 drainer 被取消），残留的 KV 键连同"这个 session 正在被删"
    # 这条信号会一起随进程消失，重启后一次 WebUI 读（hydrate/load-admit）可能
    # 把还没删干净的归档重新当作合法内容对待。这里补一个**持久化**的单键全局
    # 索引：delete-class op 提交执行时先登记（register）、全部键删 + scrub 都
    # 成功之后才摘除（clear）；`initialize()` 里的 `_scan_pending_deletes` 在
    # 每次启动时把索引里的未决 entry 载入本节的进程内镜像，让 hydrate/admit
    # 对这些 session 继续 fail-closed，直到扫描把它们解决掉或管理员手动 purge。
    #
    # 硬性红线（务必不要在后续修改里踩）：
    #   - 【绝不】在 save 路径调用 `_clear_pending_delete`——那是"证据销毁"洞：
    #     一次复活后的 save 会把"这里曾经请求过一次 wipe"的唯一记录抹掉。
    #     entry 只能由 (a) 对应 delete/purge op 跑完全部步骤、(b) 启动扫描确认
    #     primary 已空后补完删除、(c) 管理员 purge 决断 三种方式摘除。
    #   - 索引是【单个全局键】，被【每 session 一个】的 drainer 并发改动——所有
    #     改动必须经 `self._pending_delete_lock` 串行，否则并发 register/clear
    #     的"镜像快照→整体落盘"会互相踩踏丢更新（见
    #     tests/test_mem_phase1_pr4_pending_delete_index.py 的锁竞态回归）。
    #   - register/clear 本身只是普通 KV 读写，【绝不】经 `self._throat.submit`
    #     ——它们被 delete-class op 自身在其执行体内部调用（跑在 per-session
    #     drainer 任务里），反过来 submit 同一 session 队列会命中
    #     re-entrancy 断言（永久停摆）。

    async def _persist_pending_delete_index_locked(self) -> None:
        """把当前 `self._pending_delete_mirror` 整体写回索引 KV。

        调用方必须已经持有 `self._pending_delete_lock`——本方法自身不加锁
        （`asyncio.Lock` 不可重入，调用方与本方法重复加锁会死锁）。用进程内
        镜像整体覆盖写，而不是"读现有 KV blob→合并→写回"：镜像本身已经是
        在锁保护下维护的权威状态，直接整体落盘既避免了一次多余的 KV 读，也
        避免了"读到的 KV 快照与当前镜像不一致"这另一类 TOCTOU。

        Fail-safe：KV 写失败只记 warning，绝不向上抛出——不能让索引记账失败
        中断调用方所在的 delete/purge op 的其余步骤。进程内镜像已经是最新
        状态，本进程内的 fail-closed 判定不受影响；只有"跨重启"这一层保护
        会打折扣（这次落盘失败、进程恰好又崩溃，则这条 entry 在下次启动的
        索引里不可见）——这与本索引本身"尽力而为的跨重启防护"定位一致，
        不是本次改动新增的数据丢失风险。
        """
        put_fn = getattr(self._p, "put_kv_data", None)
        if not callable(put_fn):
            return
        blob = {"version": 1, "entries": dict(self._pending_delete_mirror)}
        try:
            await put_fn(PENDING_DELETE_INDEX_KV_KEY, blob)
        except Exception as e:
            logger.warning(
                "Sylanne memory pending-delete index KV persist failed (in-process "
                f"mirror still updated; cross-restart protection degraded for this "
                f"entry until next successful persist): {e}"
            )

    async def _register_pending_delete_safe(self, safe: str, epoch: int) -> None:
        """按已经安全化的 key 登记（scan 只知道 safe，不知道原始 session_key）。"""
        async with self._pending_delete_lock:
            self._pending_delete_mirror[safe] = {"epoch": epoch, "ts": time.time()}
            await self._persist_pending_delete_index_locked()

    async def _clear_pending_delete_safe(self, safe: str) -> None:
        """按已经安全化的 key 摘除（scan 只知道 safe，不知道原始 session_key）。"""
        async with self._pending_delete_lock:
            self._pending_delete_mirror.pop(safe, None)
            await self._persist_pending_delete_index_locked()

    async def _register_pending_delete(self, session_key: str, epoch: int) -> None:
        """delete-class op 的【首步】——登记本 session 的跨重启 pending-delete
        entry（进程内镜像 + 持久化索引 KV 双写，全局锁串行）。必须在任何记忆键
        删除动作之前调用，见各 op（`_delete_sylanne_memory_state_op` /
        `_purge_session_after_meltdown_impl` / `_session_deleted_delete_op`）
        开头的调用点。
        """
        await self._register_pending_delete_safe(self._safe_session_key(session_key), epoch)

    async def _clear_pending_delete(self, session_key: str) -> None:
        """delete-class op 的【末步】——仅在该 op 的全部记忆键删除 + kernel 文件
        scrub（以及 purge/session-delete 各自的非记忆键清理）都跑完之后才调用。
        【绝不】在 save 路径调用——见本节顶部"证据销毁"红线。
        """
        await self._clear_pending_delete_safe(self._safe_session_key(session_key))

    def _has_unresolved_pending_delete(self, session_key: str) -> bool:
        """PR-4 红队 must-fix 核心闸门：判定某 session 是否存在【任一来源】的
        未决删除信号——

          - 进程内咽喉 `throat.has_pending_delete`：本进程本次运行期间提交、
            排队中或正在执行的 delete/purge op（PR-3 已有，覆盖"进程没重启"
            场景）。
          - 持久索引镜像 `self._pending_delete_mirror`：跨重启信号——本进程
            启动时 `_scan_pending_deletes` 从 KV 索引载入的、上一次运行遗留
            且尚未被扫描解决（primary 非空，交管理员）或本次扫描期间正在
            处理的未决 entry。

        命中任一个都判定为未决——hydrate（`hydrate_memory_system`）与 load
        准入（`_load_admit_ok`）都用它做 fail-closed 门禁：宁可这次读到的
        内容只用来临时展示/暂不合并，也不能把一份可能仍在被删、或已经被
        崩溃中断删除的归档重新当作活体的合法内容用。
        """
        if self._throat.has_pending_delete(session_key):
            return True
        return self._safe_session_key(session_key) in self._pending_delete_mirror

    async def _scan_pending_deletes(self) -> None:
        """PR-4 启动扫描——由 `main.py initialize()` 在绑定咽喉 loop 之后调用
        （有 running loop，早于任何用户消息/WebUI 请求）。读取全局 pending-delete
        索引，对每条未决 entry 做出决断。

        **绝不盲重放**是本方法存在的意义：一次失败重试耗尽/进程崩溃，KV 里
        可能残留一条"删除意图"记录，但如果直接无脑重放"删掉这个 session 的
        记忆"，会把"回滚到 Phase-0 期间、用户在这段时间产生的合法新记忆，
        再次升级后重新看到这条陈旧 entry"这种情况下的新数据一起摧毁——这正
        是本卡片的头号红线（design §7 回滚地板 + 本卡片 HARD CONSTRAINTS）。

        两条分支：
          - primary 键**缺失或为空**——delete 显然已经开始执行（至少清空/
            删掉了主键，只是没跑完剩下的步骤就中断了），视为"崩溃在删除
            中途"：补完 backup_v2/quarantine 两个侧车键 + kernel 文件 scrub
            （复用 `_delete_sylanne_memory_state_impl`，它对已经不存在的键
            重复删除是幂等的），成功后摘除索引 entry。
          - primary 键**非空**——**绝不重放**。保留 entry、记 error 日志，
            并把它载入进程内镜像，让本进程后续对这个 session 的 hydrate/
            load-admit 继续 fail-closed，交管理员经 admin purge 决断（design
            §9："诚实遗留"，不在启动扫描里自动决断歧义 entry）。

        本方法只处理【记忆三键】（primary/v2_backup/quarantine）+ kernel 文件
        scrub——索引本身是记忆子系统专属的残留检测，非记忆键（kernel/buffer/
        emotion/v2core_domains 等）的崩溃残留不在本索引追踪范围内：those 残留
        按设计文档 §9"诚实遗留"处理（admin inspect 可见、手动 purge 补删），
        不在启动扫描里盲目扩大清理范围到本索引从未记录过的键——宁可留有非
        记忆键残留，也不错删本不该删的会话状态（例如一次单纯的 WebUI
        /api/purge_data 记忆清除，从未打算清掉 kernel/人格状态）。

        读索引本身失败（KV 抖动）——整体放弃本次扫描（下次重启再试），不假设
        "读失败=无残留"。单条 entry 的 primary 读失败同样保守处理为"不确定"
        分支（保留 + fail-closed），绝不能把读异常误判成"缺失"从而误触发
        补删/重放。

        已知局限（诚实标注）：索引/镜像只按 `_safe_session_key` 的输出建索引
        （register/clear 的调用方知道原始 session_key，但 KV 索引本身、以及
        本方法从 KV 读出来的 entries，都只有 safe key）。本方法对"缺失/空"
        分支调用 `_delete_sylanne_memory_state_impl(safe)`——safe 本身没有
        '/' 或 '\\' 时（AstrBot 常见 session_key 用 ':' 分隔，不含这两个字符）
        与传入原始 session_key 完全等价；理论上若原始 session_key 恰好含有
        这两个字符，`_scrub_kernel_alpha_json_memory` 内部按 safe 去查
        `self._p._host()` 可能查不到真正对应的 host（kernel 文件 scrub 这一
        步会静默 no-op），但三个记忆 KV 键的生成本身对 safe 输入是幂等的，
        删除仍然正确——这是 safe-key 方案本身既有的边界情况，非本 PR 引入。

        实现细节（自我审查踩中的一个真实排序坑，记录下来防止后续修改踩回去）：
        本方法【先】把索引里全部 entry 原样批量载入 `self._pending_delete_mirror`
        （一次性、在锁下，见下方第一段 `async with`），【然后】才逐条决断
        finish/keep。不能反过来"边遍历边决定要不要 clear"——若还没轮到的
        entry C 此刻还不在镜像里，而排在它前面的 entry B 恰好被 finish 后调
        `_clear_pending_delete_safe`（会把【当前镜像快照】整体重新落盘 KV），
        这次落盘会用一份【还没包含 C】的镜像覆盖 KV，C 的持久 entry 就在这次
        扫描过程中被意外抹掉——即便 C 最终会在稍后的循环里被正确判定为"非空
        primary，需要保留"并写回镜像，那也只是进程内镜像正确，KV 上的持久
        记录已经在中途丢了一拍，若进程恰好在那之后崩溃，C 的证据就没了。先
        整体载入再逐条 finish，保证任何一次 clear 触发的整体快照落盘都已经
        包含了全部尚未处理的 entry。
        """
        get_fn = getattr(self._p, "get_kv_data", None)
        if not callable(get_fn):
            # 无 KV API = 无持久索引可扫、无跨重启残留可能——放行 load-admit（无风险）。
            self._pending_delete_scan_done = True
            return
        try:
            blob = await get_fn(PENDING_DELETE_INDEX_KV_KEY, None)
        except Exception as e:
            logger.error(
                "Sylanne memory pending-delete scan: index read failed, aborting "
                f"scan (will retry next restart): {e}"
            )
            # 索引读失败：scan_done 保持 False → load-admit 继续 fail-closed（WebUI 只读
            # 渲染仍可用），绝不因读不到索引就 fail-open 准入。
            return
        if not isinstance(blob, dict):
            self._pending_delete_scan_done = True  # 索引不存在/损坏=无未决残留，放行 load-admit
            return
        raw_entries = blob.get("entries")
        if not isinstance(raw_entries, dict) or not raw_entries:
            self._pending_delete_scan_done = True  # 空索引=无未决残留，放行
            return

        valid_entries: dict[str, dict] = {}
        for safe, meta in raw_entries.items():
            if not isinstance(safe, str) or not isinstance(meta, dict):
                continue
            try:
                epoch = int(meta.get("epoch", 0))
            except (TypeError, ValueError):
                epoch = 0
            try:
                ts = float(meta.get("ts", 0.0))
            except (TypeError, ValueError):
                ts = 0.0
            valid_entries[safe] = {"epoch": epoch, "ts": ts}
        if not valid_entries:
            self._pending_delete_scan_done = True  # 无有效 entry，放行
            return

        # 先整体载入镜像（不落盘——KV 里已经是这份内容，原样镜像不算改动），
        # 再逐条决断，避免上面文档段落说明的排序坑。
        async with self._pending_delete_lock:
            self._pending_delete_mirror.update(valid_entries)
        # 镜像已载入全部未决 entry——【此处】放行 load-admit（在此之前一律 fail-closed）。
        # 必须在镜像载入【之后】、且不能提前到"读到 blob 就放行"（那样镜像还没填、有
        # await 窗口会 fail-open）。resolve 循环对每条 finish/keep 不再改变"哪些 session
        # 未决"的判定面（keep 保留、finish 删完清 entry），故放在循环之前即安全。
        self._pending_delete_scan_done = True

        for safe in list(valid_entries.keys()):
            try:
                primary = await get_fn(self.sylanne_memory_kv_key(safe), None)
            except Exception as e:
                logger.error(
                    "Sylanne memory pending-delete scan: primary read failed for "
                    f"{safe!r}, keeping entry fail-closed (admin must resolve via "
                    f"purge): {e}"
                )
                continue  # 已在镜像里（上面批量载入），保持不动即可。

            if _kv_archive_has_content(primary):
                logger.error(
                    "Sylanne memory pending-delete scan: primary key for "
                    f"{safe!r} is NON-EMPTY — refusing to replay delete intent "
                    "(a rolled-back build may have written legitimate new data "
                    "in the meantime); entry kept, admin must resolve via purge"
                )
                continue  # 同上：绝不重放，保留在镜像里，不摘索引。

            logger.warning(
                "Sylanne memory pending-delete scan: primary key for "
                f"{safe!r} missing/empty — finishing crash-interrupted delete "
                "(backup_v2/quarantine + kernel-file scrub)"
            )
            try:
                finished_ok = await self._delete_sylanne_memory_state_impl(safe)
            except Exception as e:
                logger.error(
                    "Sylanne memory pending-delete scan: finishing delete for "
                    f"{safe!r} raised, keeping entry for retry on next restart: {e}"
                )
                continue  # 补删抛异常——保留在镜像里（已批量载入），下次重启再试。

            # PR-4 gate CRITICAL：impl fail-safe 不抛，补删失败也会正常返回 False——只有
            # 全删成功才摘 entry，否则保留交下次重启重试（旧版无条件 clear 会在补删失败时
            # 摘掉 entry、残留幸存 = 复活/泄漏，且那个 except 分支形同虚设）。
            if finished_ok:
                await self._clear_pending_delete_safe(safe)
            else:
                logger.error(
                    "Sylanne memory pending-delete scan: finishing delete for "
                    f"{safe!r} incomplete (KV delete/scrub failed), keeping entry for "
                    "retry on next restart / admin purge"
                )

        # 扫描正常跑完（含空索引/无残留）——镜像已载入全部未决 entry，放行 load-admit
        # （在此之前一律 fail-closed，防抢跑的 WebUI load 漏检崩溃残留而复活）。
        self._pending_delete_scan_done = True

    def _load_admit_ok(self, session_key: str, token: int) -> bool:
        """MEM-03 PR-3（design §3 臂⑦，红队 MAJOR-3/MAJOR-7 的核心闸门）：判定一次
        `load_sylanne_memory_state` 的 KV/文件回退命中【此刻】是否还可信任——供
        `_admit_loaded_state`（store 准入）与 load 内三处 quarantine 侧车写共用。

        `token` 是调用方在 `load_sylanne_memory_state` 最开头、【第一次 await 之前】
        用 `self._throat.current_epoch(session_key)` 捕获的纪元快照。

        两个条件都要满足，缺一不可：

          - `token == self._throat.current_epoch(session_key)`：捕获"load 执行期间
            发生的 bump"——KV 读、归一化、`create_from_dict` 都经过 await，这段时间
            如果这个 session 被删（bump_epoch 同步执行），纪元会先于本次判定变化，
            token 就不再等于当前纪元。

          - `not self._throat.has_pending_delete(session_key)`：捕获"load 开始之前
            就已经提交、但尚未执行完的 delete/purge"——这是本卡真正的难点：
            `bump_epoch` 在删除类公开壳里是【提交瞬间同步】执行的（设计 §2），不是
            等 delete op 真正跑到才 bump。也就是说，如果一次 delete 在 load 开始之前
            的哪怕一瞬间就已经 submit 了，`token`（此刻捕获）会拿到的就已经是【bump
            之后】的纪元值——它和"稍后再读一次 current_epoch"必然相等，单看 token
            这一条件永远判不出"有一个 delete 正压在这个 session 头上、只是还没轮到
            它清空 KV"。`has_pending_delete` 直接查队列 + in-flight 集合，跟纪元数值
            无关，专门补上这个盲区。没有它，一次 WebUI overview 读（遍历全部
            session）就可能在 delete op 真正执行、清空 KV 之前，把这份"即将被删"的
            归档重新写回 `_store`（活体/占位者），成为下一次 save 的落盘来源——delete
            跑完了，新的一份"复活"副本已经在店里了。

        两个条件都必须为真才放行；任一为假一律拒绝——fail-closed，宁可这次读到的
        内容只用来临时展示，也不落进 store / 不重新持久化 quarantine。

        MEM-03 PR-4（红队 must-fix）：`has_pending_delete` 只覆盖【本进程本次
        运行期间】的删除信号——若上一次进程运行中一个 delete/purge 因崩溃/有界
        重试耗尽而没跑完，KV 里可能残留一条持久化的 pending-delete entry，但
        本进程重启后全新的咽喉 `_epochs`/队列对此一无所知（`has_pending_delete`
        会天真地返回 False）。用 `_has_unresolved_pending_delete` 替换原来单独
        的 `has_pending_delete` 检查——它在此基础上多查一层进程内镜像
        `self._pending_delete_mirror`（由 `initialize()` 的 `_scan_pending_deletes`
        载入未决 entry），把"跨重启"这条线也并进同一个 fail-closed 判定。
        """
        if token != self._throat.current_epoch(session_key):
            return False
        if self._has_unresolved_pending_delete(session_key):
            return False
        return True

    def _admit_loaded_state(self, session_key: str, state: Any, token: int) -> Any:
        """MEM-03 PR-3（design §3 臂⑦）：load 路径的 SYNC（无 await）store 准入闸门。

        取代此前三处 `load_sylanne_memory_state` KV/文件回退命中处各自内联的
        `memory_systems.set` + `sylanne_memory_cache.set` 写回对——那对写回完全
        绕过咽喉与化身栅栏，是红队 MAJOR-3/MAJOR-7 打的洞：WebUI 记忆页/overview
        遍历全部 session 时的一次读，能在会话删除进行中把注定被删的归档重新塞回
        店面当活体/占位者，下一次 save 就把它重新持久化 = 复活。

        判定见 `_load_admit_ok`（token + has_pending_delete 双条件，fail-closed）。

        - 准入通过：写回 `_store.memory_systems` / `_store.sylanne_memory_cache`
          （与此前行为一致），并用 `self._throat.stamp` 盖上【当前】纪元印章——
          保证这个新晋占位者此后的 save 能通过验章（而不是继续带着 load 开始时的
          旧 token）。
        - 准入拒绝：完全不碰 `_store`（不 set，不动既有占位者，也不动 `_hydrated`），
          原样返回 `state` 本身——它是一个刚从 KV/文件反序列化出来、从未被塞进任何
          登记容器的对象，天然就是"游离展示副本"：调用方（WebUI `_state_for_display`
          等只读渲染路径）可以照常读它的 `_l1`/`_l2`/`_l3_nodes` 渲染，它只是永远
          不会成为 store 里的占位者，也不会被后续任何 save 当作"当前活体"落盘
          （没人再持有它、也没人把它传给 save）。

        必须保持纯同步、零 await——`load_sylanne_memory_state` 本身不是咽喉 op，
        这里如果反过来调用 `throat.submit(...)` 再 await，等于把一次读路径伪装成
        写路径去挤咽喉队列，徒增复杂度和潜在的重入面；简单的字典写就是这里要做的
        全部事情，和它替换掉的原地内联写回等价，只是多了准入判定这一步。
        """
        if not self._load_admit_ok(session_key, token):
            return state
        # PR-4 gate（startup-ordering fail-open）：跨重启 pending-delete 镜像由
        # initialize() 的 _scan_pending_deletes 载入；扫描【完成之前】镜像为空，一次抢跑
        # 的 WebUI load 会漏检崩溃残留的删除意图、把注定被删的归档【准入 store】= 复活。
        # 仅 store 准入这条【复活向量】需要这道额外闸门——扫描完成前只返回游离副本供 WebUI
        # 只读渲染（无副作用、不占位），扫描失败也保持 fail-closed，绝不 fail-open 复活。
        # （load 内的 quarantine 侧车审计写不经此闸门：它是审计留痕、不是复活源，只受
        #  `_load_admit_ok` 的 token+has_pending_delete 双条件约束。）
        if not self._pending_delete_scan_done:
            return state
        self._p._store.memory_systems.set(session_key, state)
        self._p._store.sylanne_memory_cache.set(session_key, state)
        self._throat.stamp(state, session_key)
        return state

    async def load_sylanne_memory_state(
        self, session_key: str, *, now: float = 0.0
    ) -> Any:
        """加载 Sylanne 记忆状态，支持多级回退。

        查找顺序：
        1. 内存缓存 (_sylanne_memory_cache)
        2. 活跃记忆系统 (_memory_systems)
        3. KV 存储（经 memory_legacy_formats.normalize_memory_blob 统一识别：当前
           v2/v3 MemorySystem 形状，或旧版 SylanneMemoryState「records」格式）
        4. kernel body.memory 中的持久化数据（若非空）
        5. MEM-01 救援：绕过 kernel 恢复白名单，直接读裸 .alpha.json 文件本身

        MEM-01：`now` 参数目前保留仅为向后兼容旧调用签名——历史上曾用于对旧版
        SylanneMemoryState 执行半衰期衰减遗忘，但那条代码路径依赖的
        `from memory_engine import SylanneMemoryState` 早已因模块归档而恒定
        ImportError（被 except 静默吞掉，从未真正执行过）。旧格式现在改走
        `memory_legacy_formats.legacy_state_to_v3_dict` 的一次性迁移读取，不再
        重放半衰期衰减——这是有意的保守选择：宁可多保留一些旧记录，也不要在
        "从来没跑通过的历史逻辑"基础上继续演化衰减细节。

        Args:
            session_key: 会话标识。
            now: 保留参数，当前实现不使用（见上）。

        Returns:
            记忆状态对象，无数据时返回 None。
        """
        del now
        from .memory_system import MemorySystem

        # MEM-03 PR-3（design §3 臂⑦）：load 准入栅栏令牌——在本方法【任何 await 之前】
        # 捕获当前纪元。三处 KV/文件回退命中会把新读出的 MemorySystem 写回
        # `_store`（memory_systems/sylanne_memory_cache），这条写回本身此前完全绕过
        # 咽喉与化身栅栏——一次 WebUI 读（overview 会遍历全部 session）可能在会话
        # 删除进行中，把即将被删的归档重新写回活体，之后一次 save 就把它再持久化
        # 回 KV = 复活。`token` 与 `_admit_loaded_state`/`_load_admit_ok` 配合把这条
        # 写回也纳入 fail-closed 判定，见下方两个方法的注释。
        token = self._throat.current_epoch(session_key)

        def has_content(state: Any) -> bool:
            """检查状态对象是否包含有效内容。"""
            if state is None:
                return False
            if (
                hasattr(state, "_l1")
                or hasattr(state, "_l2")
                or hasattr(state, "_l3_nodes")
            ):
                return bool(
                    list(getattr(state, "_l1", []) or [])
                    or list(getattr(state, "_l2", []) or [])
                    or dict(getattr(state, "_l3_nodes", {}) or {})
                    or list(getattr(state, "_l3_edges", []) or [])
                )
            return bool(list(getattr(state, "records", []) or []))

        cached_state = self._p._store.sylanne_memory_cache.get(session_key)
        if has_content(cached_state):
            return cached_state
        # 检查活跃记忆系统
        live_state = self._p._store.memory_systems.get(session_key)
        if has_content(live_state):
            return live_state
        # 从 KV 存储加载
        kv_key = self.sylanne_memory_kv_key(session_key)
        get_fn = getattr(self._p, "get_kv_data", None)
        if get_fn and callable(get_fn):
            data = await get_fn(kv_key, None)
            if data is not None:
                # MEM-01：统一归一化入口——覆盖当前 v2/v3 MemorySystem 形状（原样
                # 直通）与旧版 SylanneMemoryState 格式（records 结构，替代已死的
                # `from memory_engine import SylanneMemoryState` import——那个模块
                # 早已归档到 archive/3x_engines/，旧分支过去必炸 ImportError、被
                # 静默吞掉，等价于遇到旧格式直接放弃）。
                from .memory_legacy_formats import normalize_memory_blob

                normalized, quarantined_raw, detected_format = normalize_memory_blob(
                    data
                )
                if normalized is not None:
                    try:
                        state = MemorySystem.create_from_dict(normalized)
                    except Exception as e:
                        logger.debug(f"Sylanne skip: {e}")
                        state = None
                    if state is not None:
                        combined_quarantine = [
                            {"layer": "legacy_record", "raw": r, "error": ""}
                            for r in quarantined_raw
                        ] + list(getattr(state, "_quarantine", []) or [])
                        # MEM-03 PR-3（arm ⑧）：同一 fail-closed 判定门槛也挡这条
                        # quarantine 侧车写——若这份归档注定不被准入（会话删除
                        # 进行中/已错过纪元），没理由把它的 quarantine 明文条目
                        # 另行落盘（那本身也是一次"复活"，只是复活到侧车键而非
                        # 主键）。见 `_load_admit_ok` 注释。
                        if combined_quarantine and self._load_admit_ok(
                            session_key, token
                        ):
                            await self._persist_memory_quarantine(
                                session_key, combined_quarantine
                            )
                        if detected_format == "legacy_sylanne_memory_state":
                            logger.info(
                                f"Sylanne memory: session {session_key!r} 从旧版 "
                                f"SylanneMemoryState 格式迁移读取，l2={len(state._l2)} "
                                f"条，quarantine={len(combined_quarantine)} 条"
                            )
                        return self._admit_loaded_state(session_key, state, token)
                elif isinstance(data, dict):
                    logger.debug(
                        f"Sylanne memory: session {session_key!r} 的 KV 数据不属于"
                        "任何已知记忆格式（既非当前 MemorySystem 形状，也非旧版"
                        "SylanneMemoryState），跳过（既不当作有效数据用，也不当空覆盖）"
                    )
        # 回退：从 kernel body.memory 中加载
        state_from_body = None
        try:
            host = self._p._host(session_key)
            data = host.kernel.body.memory.get("_memory_system")
            if isinstance(data, dict):
                state_from_body = MemorySystem.create_from_dict(data)
                if getattr(state_from_body, "_quarantine", None) and self._load_admit_ok(
                    session_key, token
                ):
                    await self._persist_memory_quarantine(
                        session_key, list(state_from_body._quarantine)
                    )
                return self._admit_loaded_state(session_key, state_from_body, token)
        except Exception as e:
            logger.debug(f"Sylanne skip: {e}")
        # MEM-01 最后回退（row c）：AlphaBodyState.from_dict（sylanne_core/compute/
        # body.py）恢复 body.memory 时只认 relationship/shadow 两个子键，会把
        # _memory_system/traces 静默丢弃——上面 host.kernel.body.memory 的读取因此
        # 在"kernel 已经走过一次 restore/boot"之后几乎总是落空。KV 与 body.memory
        # 两条路径都没有数据时，绕开 kernel 反序列化，直接读裸 .alpha.json 文件本身
        # 做最后的救援读取（只读、不改动 body.py 的既有恢复契约）。
        try:
            from .memory_legacy_formats import salvage_memory_system_from_alpha_json

            host = self._p._host(session_key)
            runtime = getattr(host, "runtime", None)
            path_fn = getattr(runtime, "_path", None) if runtime is not None else None
            if callable(path_fn):
                alpha_path = path_fn(session_key)
                raw_mem_data = salvage_memory_system_from_alpha_json(alpha_path)
                if isinstance(raw_mem_data, dict):
                    state = MemorySystem.create_from_dict(raw_mem_data)
                    if getattr(state, "_quarantine", None) and self._load_admit_ok(
                        session_key, token
                    ):
                        await self._persist_memory_quarantine(
                            session_key, list(state._quarantine)
                        )
                    state = self._admit_loaded_state(session_key, state, token)
                    logger.info(
                        f"Sylanne memory: session {session_key!r} 从 .alpha.json "
                        "原始文件救援读取记忆存档（body.memory 白名单丢弃路径的补救）"
                    )
                    return state
        except Exception as e:
            logger.debug(f"Sylanne memory alpha.json salvage skip: {e}")
        # 返回任何可用的缓存状态（即使为空）
        if cached_state is not None:
            return cached_state
        if live_state is not None:
            return live_state
        return None

    async def hydrate_memory_system(self, session_key: str) -> None:
        """MEM-02①：后台补水——把 KV 归档非破坏性地合并进当前活体 MemorySystem。

        由 `SessionContext.memory_system_for_session` 在首次为某 session 创建
        MemorySystem 时以 fire-and-forget 后台任务调度（该 accessor 是冻结的同步
        契约，不能改成 async；调 KV 的 get_kv_data 是 async，只能异步补水）。

        与直接调用 `load_sylanne_memory_state`（会把 `_store.memory_systems[key]`
        整体替换成新对象）不同——这里刻意只读 KV、不碰 store 的对象引用，全程原地
        合并进已经在 store 里、可能已经被其他并发请求持有引用并写入的那个活体
        实例，避免"KV 加载出的新对象 replace 掉 store 引用，旧引用的持有者继续写
        旧对象、最终一次 save 又把刚加载出来的归档盖掉"这条二次归零链路。

        补水【成功读到 KV】后才把 `_hydrated` 翻 True（合并了归档、或确认归档为空）；
        KV 读【失败】时刻意保持 `_hydrated=False`，让 `save_sylanne_memory_state` 的
        fail-closed 守卫继续挡着，绝不让一次瞬时读失败被当成"归档不存在"而解除保护
        （FIX A：重启清零 bug 的 fail-open 根因）。识别范围经 normalize_memory_blob
        覆盖当前 v2/v3 形状与旧版 SylanneMemoryState（records）格式（FIX F）。

        MEM-03 PR-4（红队 must-fix）：若该 session 存在未决 pending-delete
        （`_has_unresolved_pending_delete`——本进程内咽喉的 in-flight/排队信号，
        或跨重启持久索引镜像），拒绝合并——这份 KV 归档可能正在被删、或是上一次
        进程崩溃时删了一半留下的残局，绝不能把它合并进活体当作合法内容。保持
        `_hydrated=False`，`_refuse_unhydrated_overwrite` 继续挡住任何后续 save
        覆盖归档；entry 会由 `_scan_pending_deletes`（下次重启）或管理员 purge
        解决，绝不由本方法自作主张地推进。
        """
        from .memory_system import MemorySystem

        store = getattr(self._p, "_store", None)
        memory_map = getattr(store, "memory_systems", None) if store is not None else None
        live = memory_map.get(session_key) if memory_map is not None else None
        if live is None or not isinstance(live, MemorySystem):
            return
        if getattr(live, "_hydrated", False):
            return
        if self._has_unresolved_pending_delete(session_key):
            logger.debug(
                f"Sylanne memory hydrate: unresolved pending-delete for "
                f"{session_key!r} (in-process and/or persistent index) — refusing "
                "to merge KV archive (fail-closed); leaving un-hydrated so the "
                "save-side guard keeps protecting the archive until resolved"
            )
            return

        read_ok = True
        data: Any = None
        try:
            kv_key = self.sylanne_memory_kv_key(session_key)
            get_fn = getattr(self._p, "get_kv_data", None)
            if callable(get_fn):
                data = await get_fn(kv_key, None)
        except Exception as e:
            # FIX A：读失败 ≠ 归档不存在。把异常吞成 data=None 再走"空归档→翻
            # _hydrated"的老路，会让一次瞬时 DB 抖动就解除守卫、复活重启清零。
            logger.warning(f"Sylanne memory hydrate KV read failed for {session_key!r}: {e}")
            read_ok = False
            data = None

        # await 期间该 session 可能已被别的路径显式恢复/清空/替换——重新取一次
        # 活体引用，且若已经在这段时间内被标记 hydrated（例如 WebUI meltdown
        # 或并发的另一次补水），直接放弃，不做任何合并，避免把过期数据合并回去。
        live = memory_map.get(session_key) if memory_map is not None else None
        if live is None or not isinstance(live, MemorySystem):
            return
        if getattr(live, "_hydrated", False):
            return

        if not read_ok:
            # FIX A：读失败——刻意【不】翻 _hydrated，让 save 侧 fail-closed 守卫继续
            # 挡着（空/零星活体不得覆盖可能非空的归档），本次不合并，等下次补水/重启
            # 重试。宁可这个 session 本进程内暂时读不到历史，也绝不因一次读失败而覆盖。
            logger.debug(
                f"Sylanne memory hydrate: KV read failed for {session_key!r}, "
                "leaving un-hydrated (guard stays active), will retry on restart"
            )
            return

        if not _kv_archive_has_content(data):
            # 读成功且归档确实为空——没什么可保护的，标记为已尝试过，避免后续每次
            # save 都重复付一次 KV 读代价。
            live._hydrated = True
            return

        # FIX F：识别 + 归一化【任何】已知归档形状——不只是内联的 l1/l2/l3 子集，
        # 还包括旧版 SylanneMemoryState（records 结构）。normalize_memory_blob 是
        # load_sylanne_memory_state（WebUI 路径）已经在用的同一个统一入口；补水
        # （聊天恢复路径）此前没接它，导致旧 records 档在聊天路径永远不迁移、不加载
        # （"开 WebUI 记忆才时有时无"根因之一）。
        from .memory_legacy_formats import normalize_memory_blob

        normalized, quarantined_raw, detected_format = normalize_memory_blob(data)
        if normalized is None:
            # 被 _kv_archive_has_content 判为有内容、但 normalize 认不出的真·未知格式——
            # 刻意【不】翻 _hydrated，让 fail-closed 守卫继续挡着，绝不用活体覆盖一份
            # 读得到、但解析不了的归档。
            logger.debug(
                f"Sylanne memory hydrate: unrecognized KV format for "
                f"{session_key!r}, leaving un-hydrated (guard stays active)"
            )
            return

        try:
            live.merge_kv_archive(normalized)
        except Exception as e:
            # FIX(F1/F3) 防御纵深：即便下游合并意外崩溃，也绝不让补水任务猝死 + session
            # 永久冻结。保持 _hydrated=False（守卫继续护住归档，不被空/脏活体覆盖），记
            # error 待排查。经 from_dict/_merge_items_by_id 的 fail-closed 清洗后正常不该
            # 到这里；到了就是真·未知损坏——宁可本进程这个 session 读不到历史，也绝不覆盖。
            logger.error(
                f"Sylanne memory hydrate: merge_kv_archive crashed for {session_key!r}, "
                f"leaving un-hydrated (guard stays active): {e}",
                exc_info=True,
            )
            return
        combined_quarantine: list[dict[str, Any]] = []
        if quarantined_raw:
            combined_quarantine += [
                {"layer": "legacy_record", "raw": r, "error": ""}
                for r in quarantined_raw
            ]
        # FIX(F4)：把 merge_kv_archive 本次摘除的坏记录也一并落 quarantine 侧车，
        # 与 load_sylanne_memory_state 路径的 quarantine 语义对齐（不再静默湮灭）。
        merge_q = getattr(live, "_last_merge_quarantine", None)
        if merge_q:
            combined_quarantine += merge_q
        if combined_quarantine:
            # MEM-03 PR-3（arm ⑧）：内联 await 而非 fire-and-forget。
            # `hydrate_memory_system` 现在整体作为一个 `kind="hydrate"` 咽喉 op 的
            # factory 执行（session_context.py `_schedule_memory_hydration` 经
            # `throat.submit` 提交）——在本 op 的 drainer 还没跑到"这个 await 之后
            # 的下一行"之前，同 session 的下一个排队 op（哪怕是紧随其后的 delete）都
            # 不会被处理，因为单 drainer 严格串行、一次只处理一个 op。若像原来那样
            # `safe_ensure_future` 出去，这个 quarantine 写就成了一个独立任务，drain
            # 循环会在它派生的瞬间就继续处理队列里的下一个 op；一旦那是个 delete，
            # 它可能先把 quarantine 键删掉，随后这个游离任务才姗姗来迟地把明文条目
            # 重新 put 回去——delete 跑完了，明文侧车键却复活了。inline 等待把这次
            # 写钉死在本 op 的执行窗口内，保证它要么在下一个 op（可能是 delete）开始
            # 之前完成，要么随本 op 的异常一起被 drainer 的逐 op try/except 捕获，
            # 两种情况都不会被后面的删除穿越。
            await self._persist_memory_quarantine(session_key, combined_quarantine)
        live._hydrated = True
        logger.info(
            f"Sylanne memory: hydrated session {session_key!r} from KV archive "
            f"(format={detected_format})"
        )

    async def _delete_kv_key_with_retry(self, key: str, *, attempts: int = 3) -> bool:
        """有界重试删除单个 KV 键（≤3 次，`await asyncio.sleep(0)` 退避）。

        MEM-03 PR-2（design §4 结论提前落地）：废弃"失败即丢/靠 WAL 事后盲重放"，
        改为一次瞬时删除失败就地重试。fail-safe：重试耗尽只记日志，绝不向上抛出——
        不能让一个键的删除失败中断整个 delete/purge/session-deleted op 的其余步骤。

        PR-4 gate CRITICAL 修复：返回【是否删除成功】。以前无返回值 + fail-safe 不抛，
        调用方（op 壳 / scan）据此【无条件】摘除 pending-delete 索引 entry——一次瞬时
        KV 删除故障就会让 entry 被摘、非空归档幸存 = hydrate/load 复活。现在把成败上抛，
        调用方只在【真删掉了】才 clear entry。True=已删（或无 KV API 无键可删）；
        False=重试耗尽仍失败。
        """
        delete_fn = getattr(self._p, "delete_kv_data", None)
        if not callable(delete_fn):
            return True  # 无 KV API：无键可删，视为成功（不阻塞 entry 摘除）
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                await delete_fn(key)
                return True
            except Exception as e:  # noqa: BLE001 — fail-safe：绝不让删除失败中断 op
                last_exc = e
                if attempt < attempts - 1:
                    await asyncio.sleep(0)
        logger.warning(
            f"Sylanne memory delete: {key!r} failed after {attempts} attempts: {last_exc}"
        )
        return False

    async def _scrub_kernel_alpha_json_memory(self, session_key: str) -> bool:
        """清空 kernel 文件（.alpha.json）里的 body.memory['_memory_system'] + traces。

        PR-4 gate CRITICAL：返回是否清扫成功（True=已清或无 host 无残留；False=host
        在但清扫/落盘失败，.alpha.json 残留可能仍在）——供 _delete_..._impl 汇总，
        决定是否可安全摘除 pending-delete 索引 entry。

        红队 must-fix（第 4 条复活臂）：`load_sylanne_memory_state` 第 5 级回退
        （见该方法 MEM-01 救援段）会绕开 KV / body.memory 白名单，直接读裸
        .alpha.json 文件本身救援记忆——一个已删除会话若这份文件仍留着旧
        `_memory_system` blob，WebUI overview salvage 会把它读回来、再被下一次
        周期性 save 写回 KV，等于"删除"从未发生。`purge_session_after_meltdown`
        与 `_on_session_deleted` 的删除/清除 op 都必须清掉这份文件残留，故抽成
        共享辅助方法，避免各自漏一处。
        """
        host = None
        try:
            host = self._p._host(session_key)
        except Exception:
            pass
        if host is None:
            return True  # 无 host = 无 .alpha.json 文件残留可救援，视为已清扫
        try:
            host.kernel.body.memory.pop("_memory_system", None)
            host.kernel.body.memory["traces"] = []
            await asyncio.to_thread(host.runtime.save, host.kernel)
            return True
        except Exception as e:
            logger.debug(
                f"Sylanne memory kernel file scrub failed for {session_key!r}: {e}"
            )
            return False

    async def delete_sylanne_memory_state(self, session_key: str) -> None:
        """删除 Sylanne 记忆状态——记忆子系统拥有的【全部三个】KV 键 + 内存缓存。

        FIX(F5，第三条清除路径)：本方法是"删除某会话记忆"的规范原语，所有清除入口
        （meltdown、AstrBot 会话删除、WebUI /api/purge_data 显式抹除）最终都汇到这里。
        因此必须一并删掉 MEM-01 新增的 backup_v2 / quarantine 侧车键——否则任一入口都会
        留下完整可恢复的记忆明文副本（隐私/留存违约）。三键清单见
        memory_migration_spine.MEMORY_KV_KEYS_MANIFEST（primary/v2_backup/quarantine）。

        MEM-03 PR-2：公开壳，签名不变。提交瞬间【同步】bump_epoch（激活化身栅栏——
        PR-1 里栅栏无生产调用方、恒惰性；本方法是三条删除类壳之一，接上后即生效）：
        bump 必须发生在 submit 之前，让"delete 入队后、真正执行前"提交的陈旧血统
        save/hydrate 立即失效，而不是等 delete op 真正跑到才失效——根治 F3（删除后
        陈旧引用把已删记忆写回）。真逻辑见 `_delete_sylanne_memory_state_op`（PR-4：
        首尾包裹跨重启 pending-delete 索引 register/clear），只准经咽喉 op 调用；
        delete kind 自身豁免验章（定义 bump，幂等，见 `MemoryWriteThroat._validate`）。

        Args:
            session_key: 会话标识。
        """
        self._throat.bump_epoch(
            session_key, occupant=self._current_memory_occupant(session_key)
        )
        fut = self._throat.submit(
            session_key,
            lambda: self._delete_sylanne_memory_state_op(session_key),
            kind="delete",
            state=None,
        )
        if fut is not None:
            await fut

    async def _delete_sylanne_memory_state_op(self, session_key: str) -> None:
        """standalone 删除 op（PR-4）——`delete_sylanne_memory_state` 壳提交的
        factory 本体。首尾包裹跨重启 pending-delete 索引记账：register（首步）→
        `_delete_sylanne_memory_state_impl`（三键删除 + kernel 文件 scrub）→
        clear（末步，仅在全部删除成功跑完之后才摘除 entry——若中途抛异常，
        clear 这一行不会被执行到，entry 按设计意图【原样保留】，交下次启动的
        `_scan_pending_deletes` 或管理员 purge 决断）。

        只准经咽喉 op 调用（勿直接 await `_delete_sylanne_memory_state_impl` 再
        自行 register/clear——那会绕开这里统一的记账时机）。
        """
        await self._register_pending_delete(
            session_key, epoch=self._throat.current_epoch(session_key)
        )
        deleted_ok = await self._delete_sylanne_memory_state_impl(session_key)
        # PR-4 gate CRITICAL：只有记忆三键 + scrub 全删成功才摘除 entry。impl fail-safe
        # 不抛（一次瞬时 KV 删除故障不异常），故不能无条件 clear——否则 entry 被摘、
        # 非空归档幸存 = hydrate/load 复活。失败则保留 entry，交下次启动
        # _scan_pending_deletes / 管理员 purge 重试。
        if deleted_ok:
            await self._clear_pending_delete(session_key)

    async def _delete_sylanne_memory_state_impl(self, session_key: str) -> bool:
        """delete 真逻辑——只准经咽喉 op 调用（勿直接 await，会绕过串行化 + 栅栏
        bump 记账）。记忆子系统全部三键，primary-first 顺序
        （primary → backup_v2 → quarantine，design §4 固定顺序），每键有界重试删除；
        并清扫 .alpha.json 里的 _memory_system 救援残留（见下）。

        PR-4 gate CRITICAL 修复：返回 True 【仅当】三键删除 + .alpha.json scrub 全部
        成功。调用方（三个 op 壳 + _scan_pending_deletes）据此 gate `_clear_pending_delete`：
        任一失败则 entry【原样保留】——fail-closed，宁可留着索引让下次启动/管理员重试，
        也绝不在非空归档/残留仍在的情况下摘除保护、让 hydrate/load 把它复活。

        MEM-03 PR-4：本方法【不】做 pending-delete 索引 register/clear——它被
        三个不同的"逻辑删除单元"共用（standalone 删除 `_delete_sylanne_memory_state_op`
        / meltdown 后 `_purge_session_after_meltdown_impl` / 会话删除
        `_session_deleted_delete_op`），后两者在调用本方法之后还有各自的非记忆键
        清理要做——如果 register/clear 钉在本方法内部，purge/session-delete 会在
        它们的非记忆键还没删完时就提前摘除索引 entry，让"崩溃发生在非记忆键清理
        阶段"这类窗口漏检。register/clear 因此上提到三个调用方各自的顶层（首尾
        包裹整个逻辑删除单元），本方法保持"只删记忆三键 + scrub"的单一职责。
        """
        from .memory_legacy_formats import quarantine_kv_key

        self._p._store.sylanne_memory_cache.pop(session_key, None)
        safe = self._safe_session_key(session_key)
        all_deleted = True
        for key in (
            self.sylanne_memory_kv_key(session_key),
            self.sylanne_memory_backup_v2_kv_key(session_key),
            quarantine_kv_key(safe),
        ):
            if not await self._delete_kv_key_with_retry(key):
                all_deleted = False
        # 红队 must-fix（第 4 条复活臂）/ PR-2 gate：.alpha.json 里的 _memory_system 是
        # load 第 5 级救援的读取源，已删会话若留着它会被 WebUI overview salvage 读回、
        # 再周期 save 写回 KV = 删除从未发生。收进本【规范删除原语】——所有清除入口
        # （含 WebUI /api/purge_data 走的独立 delete_sylanne_memory_state 路径，此前只有
        # meltdown / session-delete 两条 op 各自 scrub、漏了 purge_data）自动获得清扫，
        # 不再各自漏一处。host 不存在时 scrub 内部安全早返回。
        scrub_ok = await self._scrub_kernel_alpha_json_memory(session_key)

        # v2.5.0 P0 slice 2（design §8 B5 数据安全红线）：per-person 货架桶按
        # (platform, sender_id) 存，与本方法的 session_key 粒度是两套键空间，
        # 靠反向索引反查级联删除。best-effort、不 gate 上面 all_deleted/scrub_ok
        # ——货架级联失败不应该阻塞记忆三键删除的 pending-delete entry 摘除
        # （同 :2099-2104 / :2216-2227 非记忆键清理的既定 best-effort 模式）。
        try:
            from .person_shelf import (
                clear_person_shelf_origin_index,
                load_person_shelf_origin_index,
                purge_person_shelf_by_origin,
            )

            shelf_origins = await load_person_shelf_origin_index(self._p, safe)
            for entry in shelf_origins:
                try:
                    await purge_person_shelf_by_origin(
                        self._p,
                        entry["platform"],
                        entry["sender_id"],
                        entry["origin_id"],
                    )
                except Exception as exc:
                    logger.debug(
                        f"Sylanne person_shelf purge cascade skipped for "
                        f"{session_key!r} entry {entry!r}: {exc}"
                    )
            if shelf_origins:
                await clear_person_shelf_origin_index(self._p, safe)
        except Exception as exc:
            logger.debug(
                f"Sylanne person_shelf purge cascade failed for {session_key!r}: {exc}"
            )

        return all_deleted and scrub_ok

    async def purge_session_after_meltdown(self, session_key: str) -> None:
        """记忆清除后同步抹掉专用 KV、kernel KV、域状态 KV 与 v2core 运行时缓存（T1-13）。

        MEM-03 PR-2：公开壳，签名不变。提交瞬间同步 bump_epoch——bump-and-restamp
        当前占位者（meltdown 语义是"原地清空活体 + 继续当占位者"：调用方在此之前
        已经原地清空了 MemorySystem 的内容但复用同一个对象，见 webui_routes.py /
        webui_server.py 的 meltdown handler）。只 bump 不 restamp 会让 meltdown 后
        继续聊天写入的新记忆因旧印章被永久拒写（比复活更糟）；bump_epoch 内部已经
        处理 restamp，这里无需额外操作。真逻辑经复合 op（kind="purge"，与 delete 同样
        栅栏豁免、幂等）串行执行，见 `_purge_session_after_meltdown_impl`。
        """
        self._throat.bump_epoch(
            session_key, occupant=self._current_memory_occupant(session_key)
        )
        fut = self._throat.submit(
            session_key,
            lambda: self._purge_session_after_meltdown_impl(session_key),
            kind="purge",
            state=None,
        )
        if fut is not None:
            await fut

    async def _purge_session_after_meltdown_impl(self, session_key: str) -> None:
        """purge 真逻辑——只准经咽喉 op 调用。

        内部调用 `_delete_sylanne_memory_state_impl`（【绝不】调用公开壳
        `delete_sylanne_memory_state`，也【不】调用 `_delete_sylanne_memory_state_op`）：
        本 op 已经跑在本 session 的 drainer 任务内部，若改调壳，壳会对同一 session
        队列再 submit + await，命中 `MemoryWriteThroat.submit()` 的 task-identity
        re-entrancy 断言（立即 RuntimeError）——单 drainer 等一个只有自己能完成的
        Future 本就是永久停摆，该断言正是为拦这个真实会发生的场景。不调用
        `_delete_sylanne_memory_state_op` 则是为了避免 PR-4 索引记账被内层再
        register/clear 一次（见下）。

        MEM-03 PR-4：register/clear 钉在本方法【首尾】，而非内层
        `_delete_sylanne_memory_state_impl`——本 op 是"记忆三键删除 + kernel/
        domain 键清理"合成的单一逻辑删除单元，若 register/clear 放在内层，会在
        三键删完、kernel/domain 键还没删时就提前摘除索引 entry，让"崩溃恰好发生
        在 kernel/domain 键清理阶段"这个窗口从索引里漏检。clear 只在下面全部步骤
        无异常跑完后才会被执行到——中途抛异常则 entry 按设计意图原样保留，交
        `_scan_pending_deletes` 或管理员 purge 决断。
        """
        await self._register_pending_delete(
            session_key, epoch=self._throat.current_epoch(session_key)
        )
        deleted_ok = await self._delete_sylanne_memory_state_impl(session_key)
        delete_fn = getattr(self._p, "delete_kv_data", None)
        if delete_fn and callable(delete_fn) and self.has_kv_api():
            safe = self._safe_session_key(session_key)
            for key in (
                self.kernel_kv_key(session_key),
                f"{self.kernel_kv_key(session_key)}_backup",
                f"sylanne_v2core_domains:{safe}",
            ):
                await self._delete_kv_key_with_retry(key)  # 非记忆键 best-effort，不 gate entry
        cache = getattr(self._p, "_v2core_runtimes", None)
        if isinstance(cache, dict):
            cache.pop(session_key, None)
        # .alpha.json 清扫已在 _delete_sylanne_memory_state_impl 里做过（规范原语），此处不再重复。
        # PR-4 gate CRITICAL：仅当记忆三键 + scrub 全删成功才摘 entry（非记忆键 best-effort、
        # scan 只重试记忆键，故只 gate 记忆 impl）；失败保留 entry 交下次启动/admin。
        if deleted_ok:
            await self._clear_pending_delete(session_key)

    # ------------------------------------------------------------------
    # AstrBot ConversationManager 集成
    # ------------------------------------------------------------------

    def init_conversation_manager(self) -> Any:
        """初始化 AstrBot ConversationManager（如果可用）。

        检测 AstrBot 上下文中是否存在 conversation_manager，
        存在则启用对话历史的平行同步。

        Returns:
            ConversationManager 实例，不可用时返回 None。
        """
        p = self._p
        context = getattr(p, "context", None)
        if context is None:
            return None
        conv_mgr = getattr(context, "conversation_manager", None)
        if conv_mgr is not None:
            logger.info(
                "Sylanne: AstrBot ConversationManager detected, parallel sync enabled"
            )
            register_fn = getattr(conv_mgr, "register_on_session_deleted", None)
            if register_fn and callable(register_fn):
                register_fn(self._on_session_deleted)
                logger.info("Sylanne: registered on_session_deleted callback")
        return conv_mgr

    def _on_session_deleted(self, session_key: str) -> None:
        """AstrBot 会话删除回调——释放 Sylanne 侧的会话资源。

        会话态容器统一收口于 p._store.release_session（CP8-P2），结构性登记保证
        新增容器自动纳入清理，杜绝原反射式 _SESSION_KEYED_CONTAINERS 手抄元组的
        漏登记静默泄漏（曾漏 3 个无界裸 dict）。

        MEM-03 PR-2（废除死的 persist-then-cleanup，design §3 臂⑥ / §8 PR-2 行）：
        此前这里会在 release_session 前先 fire-and-forget 落盘一份"释放前快照"，
        再串行走清理删除——那是 F4 窗口的成因本身（persist 现在还多走守卫 + 备份门
        若干 await，理论上能在同一毫秒窗口内被后到的补水/请求读到"待删但仍非空"的
        归档并合并回活体）。一次真正的会话删除，终态就该是"已删除"——persist 完
        马上又删掉纯属多此一举，不落这个 persist 步骤反而从根上关掉这个窗口。

        bump_epoch 必须在 release_session【之后】（design §2 + PR-2 gate 修正）：
        此刻占位者已被 release_session pop，occupant_getter 返回 None，bump-and-restamp
        无对象可 restamp，于是【全部旧引用出局】。若在 release 之前 bump（会取到待删的
        当前占位者并把它 restamp 成新纪元），pipeline 跨多秒 LLM await 持有的那个正是
        这个占位者引用，其后续 save 携新印章反被放行 = 复活已删记忆——正是 F3/BLOCKER-1
        要关的洞。真删除类操作里，占位者要被丢弃，绝不能 restamp。随后 submit 一个
        kind="delete" 复合 op：记忆三键（经 _impl）+ 非记忆键（原 _cleanup_kv_for_session
        的职责折进来）+ kernel .alpha.json 文件 scrub（红队 must-fix 第 4 条复活臂）+
        sylanne_v2core_domains 侧车键（红队 MINOR-3：reconsolidation overlay legacy 键含
        原始记忆 TEXT，普通会话删除此前漏删，明文残留）。fire-and-forget（本方法是同步
        回调，不 await），异常经 done_callback 消费掉，避免 "Future exception was never
        retrieved" 噪音（详见 _on_memory_system_evicted 同款模式的 MINOR-1 注释）。
        """
        p = self._p
        p._store.release_session(session_key)
        p._amnesia_sessions.discard(session_key)
        # bump 在 release 之后：占位者已 pop → occupant=None → 不 restamp → 旧引用全出局。
        self._throat.bump_epoch(
            session_key, occupant=self._current_memory_occupant(session_key)
        )
        # CP8-P3：防抖定时器清理——取消该 session 在 buffer/kernel 防抖队列中的
        # 待触发定时器，避免会话被清理后定时器仍在事件循环中触发。须在
        # release_session 之后调用（hosts.get 会返回 None，防抖任务不执行落盘）。
        self._cleanup_pending_timers(session_key)
        # CP8-P6：进化层 per-session 状态挂在引擎对象上（非 store 登记容器），
        # release_session 碰不到，显式 fan-out 清理防无界泄漏。
        forget = getattr(p, "_forget_evolution_session", None)
        if callable(forget):
            try:
                forget(session_key)
            except Exception as e:
                logger.debug(f"Sylanne evolution forget on delete failed: {e}")

        fut = self._throat.submit(
            session_key,
            lambda: self._session_deleted_delete_op(session_key),
            kind="delete",
            state=None,
        )
        if fut is not None:
            fut.add_done_callback(lambda f: f.cancelled() or f.exception())
        logger.debug(f"Sylanne: session resources released for {session_key}")

    async def _session_deleted_delete_op(self, session_key: str) -> None:
        """`_on_session_deleted` 的复合删除 op——只准经咽喉调用（跑在本 session 的
        drainer 任务内）。折合原 `_cleanup_kv_for_session` 的非记忆键清理 + 记忆三键
        删除（经 `_delete_sylanne_memory_state_impl`，非公开壳，也非
        `_delete_sylanne_memory_state_op`——原因同 `_purge_session_after_meltdown_impl`
        的同款注释：避免 PR-4 索引记账被内层重复 register/clear）+ kernel .alpha.json
        文件 scrub + `sylanne_v2core_domains` 侧车键，一次性删干净。

        MEM-03 PR-4：register/clear 钉在本方法【首尾】——本 op 是"记忆三键删除 +
        kernel/buffer/emotion/domain 非记忆键清理"合成的单一逻辑删除单元，clear
        只在全部步骤无异常跑完后才会被执行到；中途抛异常则 entry 原样保留，交
        `_scan_pending_deletes`（下次重启）或管理员 purge 决断。
        """
        await self._register_pending_delete(
            session_key, epoch=self._throat.current_epoch(session_key)
        )
        deleted_ok = await self._delete_sylanne_memory_state_impl(session_key)
        if self.has_kv_api():
            safe = self._safe_session_key(session_key)
            for key in (
                f"sylanne_kernel_{safe}",
                f"sylanne_kernel_{safe}_backup",
                f"sylanne_buffer_{safe}",
                f"emotion_state:{safe}",
                # 红队 MINOR-3：普通会话删除此前漏删这个键，reconsolidation overlay
                # 的 legacy 键含原始记忆 TEXT，留下明文残留。
                f"sylanne_v2core_domains:{safe}",
            ):
                await self._delete_kv_key_with_retry(key)  # 非记忆键 best-effort，不 gate entry
        # .alpha.json 清扫已在上面的 _delete_sylanne_memory_state_impl 里做过（规范原语），此处不再重复。
        # PR-4 gate CRITICAL：仅当记忆三键 + scrub 全删成功才摘 entry；失败保留交下次启动/admin。
        if deleted_ok:
            await self._clear_pending_delete(session_key)

    def has_conversation_manager(self) -> bool:
        """检查 AstrBot ConversationManager 是否可用。"""
        return getattr(self._p, "_conv_mgr", None) is not None

    async def sync_message_to_conv_mgr(
        self, session_key: str, role: str, text: str
    ) -> None:
        """将消息同步到 AstrBot 的 ConversationManager（平行路径）。

        保持 AstrBot 对话系统同步，但不替代 Sylanne 自身的 ConversationBuffer
        （后者仍用于 flush/consolidation 逻辑）。

        Args:
            session_key: 会话标识。
            role: 消息角色（"user" 或 "assistant"）。
            text: 消息文本内容。
        """
        p = self._p
        conv_mgr = getattr(p, "_conv_mgr", None)
        if conv_mgr is None:
            return

        # AstrBot ConversationManager 按 unified_msg_origin 建索引，插件内部的
        # session_key 不是同一个 key 空间——且不止群聊场景：session_context.py:
        # session_key() 的 base 取的是 event.session_id（取不到才退化到
        # unified_msg_origin），本身就常常与 unified_msg_origin 不同；":sender_id"
        # 后缀只要 event 带 sender_id/user_id（私聊消息通常也带）就会追加，并非
        # "仅群聊"才有。两条差异叠加，session_key 在真实平台上几乎不可能等于
        # unified_msg_origin。llm_request_pipeline 在每次
        # 请求时都会把 session_key → unified_msg_origin 的映射写进
        # p._store.session_origins（见 llm_request_pipeline.py:846-849），这里
        # 取出来对齐，取不到时才退化用 session_key 自己（好过完全不同步）。
        umo = session_key
        try:
            store = getattr(p, "_store", None)
            origins = getattr(store, "session_origins", None) if store else None
            if origins is not None:
                mapped = origins.get(session_key, "")
                if mapped:
                    umo = str(mapped)
        except Exception:
            pass  # 映射查询失败不阻断同步，退化用 session_key

        # 取 per-session 同步锁，串行化同一会话的"读历史→append→写回"。
        # 拿不到锁容器（旧版/测试环境无 _store）时降级为无锁——绝不能因为锁机制
        # 本身报错而阻断同步。锁挂在 store 上跨多次 sync 调用持久存在。锁本身仍按
        # 插件内部 session_key 取（同一 session_key 必然映射到同一 umo，用哪个
        # 做锁名不影响互斥语义，session_key 是插件内部本来就有的稳定粒度）。
        lock = None
        try:
            store = getattr(p, "_store", None)
            if store is not None:
                lock = store.get_conv_sync_lock(session_key)
        except Exception as e:
            # 降级无锁是有意取向（绝不因锁机制本身报错而阻断同步），但不能静默：
            # 恰是高并发时最易触发，无日志运维无从发现并发覆盖风险。
            lock = None
            logger.warning(
                "Sylanne conv-sync 取锁失败，降级为无锁同步（并发写回可能互相覆盖）：%s",
                e,
            )

        if lock is not None:
            async with lock:
                await self._do_sync_to_conv_mgr(conv_mgr, umo, role, text)
        else:
            await self._do_sync_to_conv_mgr(conv_mgr, umo, role, text)

    @staticmethod
    def _extract_conv_history_list(conversation: Any) -> list | None:
        """把 conv_mgr.get_conversation() 返回对象的 history 字段规整成 list。

        真实 AstrBot ConversationManager.get_conversation() 返回的是从内部
        ConversationV2（content 字段为 list）转换出的 V1 Conversation dataclass，
        其 history 字段是 JSON 字符串——conversation_mgr.py:
        `history=json.dumps(conv_v2.content or [])`，不是 list。对着一个字符串
        直接 `list(...)` 会把它拆成单字符列表，写回时把整段历史污染成字符垃圾。
        这里显式区分字符串 / list / None 三种可能形状。

        fail-closed（round-4 adjudicated 修复）：JSON 解析失败、解析结果不是
        list、或者 history 字段本身是既非 str 又非 list 的意外类型，一律返回
        None——这些都是"数据损坏，无法安全判断真实历史长啥样"，绝不能当成
        "空历史"处理。旧实现在这些分支统一返回 `[]`，调用方
        `_do_sync_to_conv_mgr` 会在这个"看似合法的空列表"后面 append 本次新
        消息再整体写回，等价于用只含一条新消息的历史覆盖写回，把损坏之外原本
        可能仍然完好的历史数据一并静默摧毁。真正合法的"没有历史"（conversation
        为 None、history 字段为 None、history 是空/纯空白字符串）不受影响，
        仍然返回 `[]`。
        """
        if conversation is None:
            return []
        raw = getattr(conversation, "history", None)
        if raw is None:
            return []
        if isinstance(raw, str):
            if not raw.strip():
                return []
            try:
                parsed = json.loads(raw)
            except (TypeError, ValueError):
                return None
            return list(parsed) if isinstance(parsed, list) else None
        if isinstance(raw, list):
            return list(raw)
        return None

    @staticmethod
    def _history_entry_signature(entry: Any) -> tuple[str, str] | None:
        """提取历史条目的 (归一化 role, 纯文本 content) 签名，供幂等去重比较。

        dict-fallback 路径（AstrBot 消息类型 import 失败时）落库的 role 是调用方
        原始传入值（"user"/"bot"）；AstrBot 消息类型路径落库后固定是
        "user"/"assistant"（AssistantMessageSegment.role 字面量约束）——两者不是
        同一命名空间，比较前先归一化（非 "user" 一律视为 assistant 侧），否则
        同一次真实重叠写因两条构造路径落库方式不同，永远比不出"相同"，guard 形
        同虚设。content 同样兼容纯字符串 / TextPart.model_dump() 产出的
        [{"type": "text", "text": ...}] 分段列表两种形状。

        entry 不是 dict（遗留裸 pydantic 对象、意外字符串垃圾等）时返回 None，
        调用方应放行不比较——不确定的东西不能拿来判等，宁可不去重也不误杀。
        """
        if not isinstance(entry, dict):
            return None
        role = str(entry.get("role", ""))
        norm_role = "user" if role == "user" else "assistant"
        content = entry.get("content")
        if isinstance(content, list):
            content_str = "".join(
                # .get("text") or "" ——键存在但值为 None 时 .get("text", "")
                # 会返回 None，str(None) == "None" 混进签名字符串，污染幂等比较。
                str(part.get("text") or "")
                for part in content
                if isinstance(part, dict) and "text" in part
            )
        else:
            content_str = str(content or "")
        return norm_role, content_str

    # framework 侧非对话角色（AstrBot core/agent/message.py）：round-2 的幂等守卫
    # 硬编码 history[-1] 时漏考虑了这些——internal.py:481-488 在保存历史时，可能在
    # assistant 消息【之后】追加一条 CheckpointMessageSegment（role="_checkpoint"），
    # 使真正的最后一条 assistant/user 消息并不在数组末尾。
    _NON_CONVERSATIONAL_ROLES = frozenset({"_checkpoint", "system", "tool"})

    @classmethod
    def _last_conversational_entry(cls, history: list) -> Any:
        """从历史末尾往前跳过尾随的非对话 role 条目，取真正最后一条
        user/assistant 消息用于幂等比较。

        round-2 MINOR：guard 曾直接用 `history[-1]` 当"框架刚写的那条"，但框架的
        _save_to_history（AstrBot core/pipeline/.../internal.py:481-488）在正常
        assistant 消息之后可能再追加一条 CheckpointMessageSegment
        （role="_checkpoint"，用于恢复用的 checkpoint 标记，不代表一轮对话内容）。
        若末条恰好是这类记录，`_history_entry_signature(history[-1])` 会拿一个
        checkpoint/system 条目的内容去跟本次要同步的 bot 文本比较——两者天然不同，
        guard 因此永远判定"不同"，真正应该被识别为重复的框架写入被漏检、照样又
        追加一次，产生连续两条 assistant 记录。这里改为从末尾向前扫，跳过
        _NON_CONVERSATIONAL_ROLES 里的角色，取第一条"真"消息用于比较。

        Returns:
            最后一条非 checkpoint/system/tool 的历史条目；全是非对话条目或历史为
            空时返回 None（调用方应视为"无可比较对象"，不阻止追加）。
        """
        for entry in reversed(history):
            if (
                isinstance(entry, dict)
                and str(entry.get("role", "")) in cls._NON_CONVERSATIONAL_ROLES
            ):
                continue
            return entry
        return None

    async def _do_sync_to_conv_mgr(
        self, conv_mgr: Any, umo: str, role: str, text: str
    ) -> None:
        """实际执行 ConversationManager 同步的"读→append→写回"。

        必须在 per-session 同步锁内调用（由 sync_message_to_conv_mgr 负责），
        以避免并发整表写回互相覆盖。`umo` 必须是框架的 unified_msg_origin
        （由调用方 sync_message_to_conv_mgr 完成 session_key → umo 的映射），
        不是插件内部 session_key。
        """
        try:
            # 获取或创建当前会话
            curr_cid = await conv_mgr.get_curr_conversation_id(umo)
            if not curr_cid:
                curr_cid = await conv_mgr.new_conversation(umo)

            # 尝试使用 AstrBot 消息类型；不可用时回退到普通字典
            try:
                from astrbot.core.agent.message import (
                    AssistantMessageSegment,
                    TextPart,
                    UserMessageSegment,
                )

                if role == "user":
                    msg_obj = UserMessageSegment(content=[TextPart(text=text)])
                else:
                    msg_obj = AssistantMessageSegment(content=[TextPart(text=text)])
                # 立即拍平成普通 dict：整条历史最终要经 SQLAlchemy JSON 列落库
                # （默认 json.dumps 序列化器），直接把 pydantic 对象塞进历史列表
                # 会在写库时炸 TypeError，且被本方法自己的 except 静默吞掉——
                # 表现为"同步看起来成功，实际上库里什么都没写"。
                msg = msg_obj.model_dump()
            except ImportError:
                # 旧版 AstrBot 或测试环境：使用普通字典
                msg = {"role": role, "content": text}

            conversation = await conv_mgr.get_conversation(umo, curr_cid)
            history = self._extract_conv_history_list(conversation)
            if history is None:
                # round-4 adjudicated fail-closed：history 字段损坏（JSON 解析
                # 失败 / 解析结果不是 list / 意外类型），无法安全判断真实历史
                # 长啥样。整体放弃本次同步——绝不能用只含这一条新消息的重建
                # 历史去覆盖写回，那样会把损坏之外原本可能仍然完好的历史数据
                # 也一并静默摧毁。宁可这一条消息暂时不同步，也不能丢历史。
                logger.debug(
                    "Sylanne conv-sync 跳过：umo=%s 的 history 字段无法安全解析"
                    "（疑似损坏），fail-closed 放弃本次同步以避免覆盖写摧毁"
                    "已存储历史",
                    umo,
                )
                return
            # fix/context-integrity round-2 MAJOR② / round-3 纠偏：幂等守卫（第二道
            # 防线）。round-2 曾以为第一道防线（llm_response_pipeline.py 非拦截分支的
            # skip_conv_sync）已经让【本方法只会在拦截/分段发送分支被调用】、且那条
            # 路径是插件唯一写入者——两个前提都不成立：round-3 复审确认框架的
            # _save_to_history 不区分拦截/非拦截分支，两条路径的完整正常回复都会
            # 被框架保存，本方法当前的两个调用点因此都已改成 skip_conv_sync=True。
            # 但本方法本身（sync_message_to_conv_mgr → _do_sync_to_conv_mgr）仍然是
            # 一个独立的读-改-写，只要调用方哪天新增一条"框架确定不会保存"的路径
            # （见 llm_response_pipeline.py::_append_bot_reply_buffer 的
            # skip_conv_sync docstring），本方法就可能与框架 _save_to_history 并发写
            # 同一个 conv_mgr.update_conversation：若我们这次的读恰好发生在框架那次
            # 全量覆盖写之后，history 末条会已经是这次要追加的同一条消息，再 append
            # 一次会产生连续两条相同 role 记录（已知 Gemini 连续 assistant turn
            # 结构雷区）——这道守卫就是为这种时序兜底，与当前是否有调用点真的会
            # 触发并发无关，属于防御性纵深。末条签名完全一致就直接跳过、不追加也不
            # 写回——原样保留框架那次写（可能更全，含 tool_calls/多模态/checkpoint），
            # 不去覆盖它。
            #
            # round-2 MINOR（本轮修复）：判"末条"时不能直接取 history[-1]。AstrBot
            # 的 _save_to_history（core/pipeline/.../internal.py:481-488）可能在
            # assistant 消息之后再追加一条 CheckpointMessageSegment
            # （role="_checkpoint"），framework 那次写完之后数组末尾就不是 assistant
            # 消息本身。改用 _last_conversational_entry 从末尾向前跳过
            # checkpoint/system/tool 等非对话角色，取真正最后一条 user/assistant
            # 消息来比较，避免这类尾随记录让 guard 误判"不同"从而漏检真实重复。
            #
            # 刻意只对非 "user" 一侧（bot/assistant）生效。
            # 【2.4.1 修正】原注释断言"request 阶段的 user 同步发生在 LLM 调用之前，
            # 压根不存在并发写这回事"——该假设是错的，正是 leg-3 跨锁双写 bug 的根源：
            # 请求期那次 user 同步是 fire-and-forget，可被调度到框架 _save_to_history
            # 之后，读到 [.., u, b] 再 append 一条 u，写出悬挂重复 user，下一轮模型遂把
            # 已答问题当新问题重答。2.4.1 已删除请求期无条件 user 写，改为响应期收口
            # （main.py::_backfill_user_if_framework_skips）仅在框架本轮不落库时补写，
            # 且该补写在框架 per-umo session_lock 内 await 完成 —— 故【单轮内】它是唯一的
            # user 写者，与框架的整表覆盖写不再跨锁双写。注意：跨轮并发的多个补写仍会
            # 并发进入本方法（同 umo 多轮均 SILENT 时），由调用方 sync_message_to_conv_mgr
            # 取的 conv_sync_lock 把这段读-改-写串行化——真进程灰测实测：绕过该锁立刻
            # 丢失并发写。下面豁免 user 的【真正理由】自始至终是另一条：
            # 若不加这条限制，用户
            # 连续两轮发完全相同的文字（例如中间那轮 bot 恰好 SILENT、没有任何
            # assistant 记录夹在中间）会被这条 guard 误判成"重复"而丢掉第二条真实
            # 用户消息——这是比它防的竞态更容易踩中的真实回归，必须避免。
            if role != "user" and history:
                last_entry = self._last_conversational_entry(history)
                new_sig = self._history_entry_signature(msg)
                last_sig = (
                    self._history_entry_signature(last_entry)
                    if last_entry is not None
                    else None
                )
                if new_sig is not None and last_sig is not None and last_sig == new_sig:
                    logger.debug(
                        "Sylanne conv-sync 幂等跳过：末条（跳过尾随 checkpoint/"
                        "system/tool 记录后）已是同 role+content (umo=%s)，"
                        "疑似与框架 _save_to_history 并发写重叠",
                        umo,
                    )
                    return
            history.append(msg)
            # 防御竞态：本方法与 AstrBot 自身 _save_to_history 无锁并发，可能读到
            # tool 循环中途的快照（含 assistant tool_calls 但尚无 tool 响应）。写回前
            # 清除破损的 tool_calls/tool 配对，避免把孤儿持久化进历史（fixes #18）。
            try:
                from sylanne_alpha.llm_request_pipeline import (
                    sanitize_tool_call_pairing,
                )

                history = sanitize_tool_call_pairing(history)
            except Exception:
                pass
            await conv_mgr.update_conversation(umo, curr_cid, history=history)
        except Exception as e:
            # 2.4.1 红线闸 finding：此处曾是 debug 级别，会把"该补写却因瞬时
            # DB/IO 故障吞掉"的 SILENT 补写失败静默藏起来（fail-open by design，
            # 不改变吞异常的行为——上游 _backfill_user_if_framework_skips 仍要保证
            # 补写失败不阻断回复——但至少要能在 ops 侧被看见）。升级为 warning。
            logger.warning(
                f"Sylanne: ConversationManager sync failed: {e}", exc_info=True
            )

    # ------------------------------------------------------------------
    # AstrBot PersonaManager 集成
    # ------------------------------------------------------------------

    def init_persona_manager(self) -> Any:
        """初始化 AstrBot PersonaManager（如果可用）。

        检测 AstrBot 上下文中是否存在 persona_manager，
        存在则启用人格状态的同步。

        Returns:
            PersonaManager 实例，不可用时返回 None。
        """
        p = self._p
        context = getattr(p, "context", None)
        if context is None:
            return None
        persona_mgr = getattr(context, "persona_manager", None)
        if persona_mgr is not None:
            logger.info(
                "Sylanne: AstrBot PersonaManager detected, personality sync enabled"
            )
        return persona_mgr

    def has_persona_manager(self) -> bool:
        """检查 AstrBot PersonaManager 是否可用。"""
        return getattr(self._p, "_persona_mgr", None) is not None

    def sync_personality_to_persona_mgr(self, session_key: str) -> None:
        """将 Sylanne 人格状态同步到 AstrBot 的 PersonaManager。

        在人格漂移更新后调用，创建或更新 Sylanne persona 条目，
        使 AstrBot 的 persona 系统感知当前人格状态。

        Args:
            session_key: 会话标识。
        """
        p = self._p
        persona_mgr = getattr(p, "_persona_mgr", None)
        if persona_mgr is None:
            return
        try:
            host = p._store.hosts.get(session_key)
            if not host:
                return
            personality = (
                host.kernel._personality()
                if hasattr(host.kernel, "_personality")
                else {}
            )
            if not personality or not isinstance(personality, dict):
                return

            traits = personality.get("traits", {})
            voice = personality.get("voice", {})

            trait_lines = []
            for k, v in traits.items():
                if isinstance(v, (int, float)):
                    trait_lines.append(f"{k}={v:.3f}")
                elif isinstance(v, dict) and "value" in v:
                    trait_lines.append(f"{k}={v['value']:.3f}")
            trait_summary = ", ".join(trait_lines) if trait_lines else "default"

            safe_sk = self._safe_session_key(session_key)
            persona_id = f"sylanne_embodiment_{safe_sk}"
            system_prompt = (
                f"[Sylanne Personality State]\n"
                f"Traits: {trait_summary}\n"
                f"Voice: {voice if voice else 'default'}"
            )

            import asyncio
            import inspect

            async def _do_sync() -> None:
                try:
                    existing = persona_mgr.get_persona(persona_id)
                    if inspect.isawaitable(existing):
                        existing = await existing
                    if existing:
                        ret = persona_mgr.update_persona(persona_id, system_prompt=system_prompt)
                        if inspect.isawaitable(ret):
                            await ret
                    else:
                        ret = persona_mgr.create_persona(
                            persona_id=persona_id,
                            system_prompt=system_prompt,
                            begin_dialogs=[],
                            tools=None,
                        )
                        if inspect.isawaitable(ret):
                            await ret
                except Exception:
                    try:
                        ret = persona_mgr.create_persona(
                            persona_id=persona_id,
                            system_prompt=system_prompt,
                        )
                        if inspect.isawaitable(ret):
                            await ret
                    except Exception:
                        pass

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_do_sync())
            except RuntimeError:
                pass
        except Exception as e:
            logger.debug(f"Sylanne: PersonaManager sync failed: {e}")

    # ------------------------------------------------------------------
    # Provider ID 解析
    # ------------------------------------------------------------------

    async def provider_id(self, event: Any = None) -> str:
        """解析当前聊天的 LLM provider ID（带 TTL 缓存）。

        通过 AstrBot 上下文的 get_current_chat_provider_id 获取，
        结果缓存 30 秒（可配置）避免频繁查询。

        Args:
            event: 当前事件对象。

        Returns:
            Provider ID 字符串，不可用时返回空字符串。
        """
        import time

        p = self._p
        cache = getattr(p, "_provider_id_cache", None)
        if cache is None:
            p._provider_id_cache = {}
            cache = p._provider_id_cache
        sk = p._session_key(event)
        cached = cache.get(sk)
        if cached:
            ts, val = cached
            ttl = float((p.config or {}).get("provider_id_cache_ttl_seconds", 30.0))
            if time.time() - ts < ttl:
                return val
        context = getattr(p, "context", None) or p.context
        if hasattr(context, "get_current_chat_provider_id"):
            try:
                umo = str(getattr(event, "unified_msg_origin", "") or sk)
                result = await context.get_current_chat_provider_id(umo=umo)
                val = str(result or "")
                cache[sk] = (time.time(), val)
                return val
            except Exception as e:
                logger.debug(f"Sylanne skip: {e}")
        return ""

    # ------------------------------------------------------------------
    # 配置默认值初始化
    # ------------------------------------------------------------------

    def load_config_defaults(self) -> None:
        """初始化所有配置键的默认值。

        在插件启动时调用，确保所有配置项都有合理的默认值，
        避免运行时因缺失配置而出错。覆盖 WebUI、评估器、实时聊天、
        后台队列、安全边界、记忆系统等全部子系统的配置。
        """
        p = self._p
        p._cfg_bool("sylanne_webui_enabled", False)
        p._cfg("sylanne_webui_host", "127.0.0.1")
        p._cfg_int("sylanne_webui_port", 2718)
        p._cfg_bool("enabled", True)
        p._cfg_bool("use_llm_assessor", True)
        p._cfg("emotion_provider_id", "")
        p._cfg_bool("fast_assessor_enabled", False)
        p._cfg("fast_assessor_provider_id", "")
        p._cfg_int("fast_assessor_max_context_chars", 600)
        p._cfg_float("fast_assessor_timeout_seconds", 2.0)
        p._cfg_float("fast_assessor_temperature", 0.0)
        p._cfg_bool("low_reasoning_friendly_mode", False)
        p._cfg_int("low_reasoning_max_context_chars", 1200)
        p._cfg("assessment_timing", "post")
        p._cfg_bool("enable_proactive_speech_dispatch", False)
        p._cfg_bool("enable_proactive_speech_scheduler", False)
        p._cfg_bool("enable_realtime_chat", False)
        p._cfg_bool("realtime_chat_style_prompt_enabled", False)
        p._cfg_bool("realtime_chat_intercept_llm_response", False)
        p._cfg_bool("realtime_input_completion_llm_gate_enabled", False)
        p._cfg_float("realtime_input_completion_probe_delay_seconds", 0.25)
        p._cfg_float("realtime_input_completion_max_wait_seconds", 4.0)
        p._cfg_float("realtime_user_typing_hold_seconds", 0.8)
        p._cfg_float("realtime_empty_input_typing_hold_seconds", 0.35)
        p._cfg_bool("realtime_chat_dry_run_default", False)
        p._cfg_bool("realtime_chat_strip_markdown", True)
        p._cfg_bool("enable_sticker_reaction", False)
        p._cfg_int("background_post_queue_limit", 0)
        p._cfg_bool("enable_dynamic_background_workers", False)
        p._cfg_bool("background_post_queue_checkpoint_enabled", True)
        p._cfg_float("background_post_checkpoint_debounce_seconds", 0.75)
        p._cfg_float("background_post_job_lease_seconds", 120.0)
        p._cfg_float("background_post_job_timeout_seconds", 0.0)
        p._cfg_int("background_post_retry_max_attempts", 3)
        p._cfg_float("background_post_retry_base_delay_seconds", 2.0)
        p._cfg_float("background_post_retry_max_delay_seconds", 60.0)
        p._cfg_int("background_post_dead_letter_limit", 100)
        p._cfg_int("background_post_diagnostics_warn_lag_count", 20)
        p._cfg_float("background_post_diagnostics_warn_lag_seconds", 60.0)
        p._cfg_bool("enable_low_signal_light_assessment", True)
        p._cfg_int("low_signal_max_chars", 12)
        p._cfg_bool("sylanne_alpha_assessor_llm_enabled", False)
        p._cfg("sylanne_alpha_assessor_provider_id", "")
        p._cfg_float("sylanne_alpha_assessor_timeout_seconds", 2.0)
        p._cfg_float("sylanne_alpha_fast_assessor_timeout_seconds", 1.5)
        p._cfg_bool("sylanne_alpha_main_assessor_enabled", False)
        p._cfg("sylanne_alpha_main_assessor_provider_id", "")
        p._cfg_float("sylanne_alpha_main_assessor_timeout_seconds", 3.0)
        p._cfg_float("sylanne_alpha_kernel_persist_debounce_seconds", 4.0)
        p._cfg_bool("agent_speaker_relationship_tracking", True)
        p._cfg_bool("agent_include_speaker_in_assessment", True)
        p._cfg_int("agent_identity_profile_limit", 256)
        p._cfg_float("agent_identity_ttl_seconds", 2592000.0)
        p._cfg_bool("enable_agent_causal_trail", True)
        p._cfg_int("agent_trail_limit", 80)
        p._cfg_bool("agent_trail_compaction_enabled", True)
        p._cfg_float("agent_trail_low_signal_delta_threshold", 0.03)
        p._cfg_int("agent_trail_low_signal_window", 5)
        p._cfg_bool("inject_state", True)
        p._cfg_bool("runtime_parameter_debug_override_enabled", False)
        p._cfg_int("state_injection_request_budget_chars", 32000)
        p._cfg_int("state_injection_reserved_chars", 3000)
        p._cfg_int("state_injection_max_added_chars", 2400)
        p._cfg_int("state_injection_max_parts", 8)
        p._cfg_int("llm_tool_response_max_chars", 16000)
        p._cfg_bool("enable_safety_boundary", True)
        p._cfg_bool("block_deception_manipulation_evasion_actions", True)
        p._cfg_int("max_context_chars", 1600)
        p._cfg_int("request_context_max_chars", 1600)
        p._cfg_float("assessor_timeout_seconds", 0.0)
        p._cfg_float("assessor_temperature", 0.1)
        p._cfg_float("provider_id_cache_ttl_seconds", 30.0)
        p._cfg_float("passive_load_fresh_seconds", 1.0)
        p._cfg_bool("benchmark_enable_simulated_time", False)
        p._cfg_float("benchmark_time_offset_seconds", 0.0)
        p._cfg_bool("allow_emotion_reset_backdoor", False)
        p._cfg_bool("enable_psychological_screening", False)
        p._cfg_float("sylanne_memory_idle_commit_delay_seconds", 4.0)
        p._cfg_bool("sylanne_memory_vector_retrieval_enabled", True)
        p._cfg("sylanne_memory_embedding_provider_id", "")
        p._cfg_float("sylanne_memory_record_embedding_min_interval_seconds", 300.0)
        p._cfg_int("sylanne_memory_record_embedding_max_per_flush", 1)
        p._cfg_bool("sylanne_memory_debug_view_enabled", False)
        p._cfg_bool("humanlike_memory_write_enabled", True)
        p._cfg_bool("allow_humanlike_reset_backdoor", False)
        p._cfg_bool("lifelike_learning_memory_write_enabled", True)
        p._cfg_bool("allow_lifelike_learning_reset_backdoor", True)
        p._cfg_bool("personality_drift_memory_write_enabled", True)
        p._cfg_bool("allow_personality_drift_reset_backdoor", True)
        p._cfg_bool("enable_moral_repair_state", False)
        p._cfg_bool("moral_repair_memory_write_enabled", True)
        p._cfg_bool("allow_moral_repair_reset_backdoor", True)
        p._cfg_bool("enable_fallibility_state", False)
        p._cfg_bool("fallibility_memory_write_enabled", True)
        p._cfg_bool("allow_fallibility_reset_backdoor", True)
        p._cfg_bool("enable_shadow_diagnostics", False)
        p._cfg_bool("enable_integrated_self_state", True)
        p._cfg_bool("allow_relational_self_public_export", False)
        p._cfg_bool("integrated_self_memory_write_enabled", True)
        p._cfg("integrated_self_degradation_profile", "balanced")
        p._cfg_bool("sylanne_alpha_auto_detect_group_context", True)
        # v2.5.0 P0 slice 1：跨群记忆 6 个开关（design §6），全默认关/最保守档，
        # 本 slice 不被任何生产读写路径读取——注册默认值只是为了配置面板/WebUI
        # 展示与后续 slice 接线时零意外，对现网行为零影响。
        p._cfg("sylanne_alpha_cross_session_mode", "off")
        p._cfg("sylanne_alpha_cross_session_scope", "owner")
        p._cfg_bool("sylanne_alpha_cross_dialogue", False)
        p._cfg_bool("sylanne_alpha_cross_relationship", False)
        p._cfg_bool("sylanne_alpha_cross_personality", False)
        p._cfg("sylanne_alpha_cross_visibility_tier", "same_group")

    # ------------------------------------------------------------------
    # Item 18: 记忆系统分片存储
    # ------------------------------------------------------------------

    @staticmethod
    def _shard_key(session_key: str, subsystem: str) -> str:
        """生成分片存储键。"""
        safe_key = session_key.replace(":", "_").replace("/", "_")[:50]
        return f"sylanne_shard_{safe_key}_{subsystem}"

    def persist_memory_shard(self, session_key: str, memory_data: dict) -> None:
        """按 session_key 分片存储记忆数据。"""
        key = self._shard_key(session_key, "memory")
        # 通过 plugin 的 KV 接口存储
        kv = getattr(self._p, 'kv', None) or getattr(self._p, '_kv', None)
        if kv and hasattr(kv, 'set'):
            import json
            kv.set(key, json.dumps(memory_data))

    def load_memory_shard(self, session_key: str) -> dict | None:
        """加载指定 session 的记忆分片。"""
        key = self._shard_key(session_key, "memory")
        kv = getattr(self._p, 'kv', None) or getattr(self._p, '_kv', None)
        if kv and hasattr(kv, 'get'):
            import json
            raw = kv.get(key)
            if raw:
                return json.loads(raw)
        return None

    # ------------------------------------------------------------------
    # AstrBot 群聊上下文检测
    # ------------------------------------------------------------------

    def detect_astrbot_group_context(self) -> bool:
        """检测 AstrBot 内置的群聊上下文感知是否已启用。

        通过多种方式探测 AstrBot 配置：
        1. Context.get_config() 方法
        2. context.platform_settings 属性
        3. context.config_manager.config 字典

        Returns:
            True 表示 AstrBot 已启用群聊上下文感知。
        """
        p = self._p
        if not p._cfg_bool("sylanne_alpha_auto_detect_group_context", True):
            return False
        try:
            context = getattr(p, "context", None)
            if context is None:
                return False
            # Method 1: AstrBot Context.get_config()
            get_config_fn = getattr(context, "get_config", None)
            if callable(get_config_fn):
                cfg = get_config_fn()
                if isinstance(cfg, dict):
                    if cfg.get("enable_group_context") or cfg.get(
                        "group_context_enabled"
                    ):
                        return True
            # Method 2: Check platform_settings on context
            platform_settings = getattr(context, "platform_settings", None)
            if isinstance(platform_settings, dict):
                if platform_settings.get(
                    "group_context_enabled"
                ) or platform_settings.get("enable_group_context"):
                    return True
            # Method 3: Check context._config or context.config_manager
            config_mgr = getattr(context, "config_manager", None)
            if config_mgr is not None:
                global_cfg = getattr(config_mgr, "config", None)
                if isinstance(global_cfg, dict):
                    if global_cfg.get("enable_group_context") or global_cfg.get(
                        "group_context_enabled"
                    ):
                        return True
        except Exception:
            pass  # cleanup: config introspection failure acceptable
        return False

    # ------------------------------------------------------------------
    # 终止/清理
    # ------------------------------------------------------------------

    async def terminate(self) -> None:
        """优雅关闭：取消任务、保存检查点、清理状态。

        关闭顺序：
        1. 取消主动调度器任务
        2. 取消所有后台任务并等待完成
        3. 保存后台评估队列的最终检查点
        4. 清理后台队列状态
        5. 停止 WebUI 服务器
        """
        p = self._p
        # 先排干合并 kernel 落盘：debounce 窗口内累积的脏状态须在 cancel 后台任务
        # 之前同步落盘，否则待触发的定时器和 fire-and-forget 落盘会被反手取消而丢失。
        try:
            await self.flush_pending_kernel_persists()
        except Exception as e:
            logger.warning(f"Sylanne kernel flush on terminate: {e}", exc_info=True)
        task = getattr(p, "_proactive_scheduler_task", None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        p._proactive_scheduler_task = None
        p._store.proactive_candidate_sessions.clear()
        p._store.proactive_scheduler_locks.clear()
        # Cancel all background tasks
        tasks = getattr(p, "_background_tasks", [])
        for t in list(tasks):
            if not t.done():
                t.cancel()
        if tasks:
            await asyncio.gather(*list(tasks), return_exceptions=True)
        if isinstance(tasks, set):
            tasks.clear()
        elif isinstance(tasks, list):
            tasks.clear()
        p._background_tasks = []
        # Save final checkpoints for background post queues
        bg_queues = p._store.background_post_queues
        checkpoint_enabled = bool(
            (p.config or {}).get("background_post_queue_checkpoint_enabled")
        )
        recovered = p._background_post_recovered_sessions
        if checkpoint_enabled:
            for sk in list(bg_queues.keys()):
                if sk in recovered or bg_queues.get(sk):
                    try:
                        await p._save_background_post_checkpoint(sk)
                    except Exception:
                        pass
        # Clean up background post state
        p._background_post_tasks = {}
        p._store.background_post_queues.clear()
        p._store.background_post_sequence.clear()
        p._background_post_skipped = {}
        p._terminating = True
        try:
            from sylanne_alpha.webui_server import stop_webui_server

            await stop_webui_server()
        except Exception:
            pass
