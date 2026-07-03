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
import zlib
from typing import TYPE_CHECKING, Any

from sylanne_alpha.utils import safe_ensure_future

if TYPE_CHECKING:
    from .host import SylanneAlphaHost
    from .protocols import PluginHost

logger = logging.getLogger("astrbot_plugin_sylanne")

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
                        if combined_quarantine:
                            await self._persist_memory_quarantine(
                                session_key, combined_quarantine
                            )
                        if detected_format == "legacy_sylanne_memory_state":
                            logger.info(
                                f"Sylanne memory: session {session_key!r} 从旧版 "
                                f"SylanneMemoryState 格式迁移读取，l2={len(state._l2)} "
                                f"条，quarantine={len(combined_quarantine)} 条"
                            )
                        self._p._store.memory_systems.set(session_key, state)
                        self._p._store.sylanne_memory_cache.set(session_key, state)
                        return state
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
                if getattr(state_from_body, "_quarantine", None):
                    await self._persist_memory_quarantine(
                        session_key, list(state_from_body._quarantine)
                    )
                self._p._store.memory_systems.set(session_key, state_from_body)
                self._p._store.sylanne_memory_cache.set(session_key, state_from_body)
                return state_from_body
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
                    if getattr(state, "_quarantine", None):
                        await self._persist_memory_quarantine(
                            session_key, list(state._quarantine)
                        )
                    self._p._store.memory_systems.set(session_key, state)
                    self._p._store.sylanne_memory_cache.set(session_key, state)
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
        """
        from .memory_system import MemorySystem

        store = getattr(self._p, "_store", None)
        memory_map = getattr(store, "memory_systems", None) if store is not None else None
        live = memory_map.get(session_key) if memory_map is not None else None
        if live is None or not isinstance(live, MemorySystem):
            return
        if getattr(live, "_hydrated", False):
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
            safe_ensure_future(
                self._persist_memory_quarantine(session_key, combined_quarantine),
                name=f"memory_hydrate_quarantine_{session_key}",
                task_list=getattr(self._p, "_background_tasks", None),
            )
        live._hydrated = True
        logger.info(
            f"Sylanne memory: hydrated session {session_key!r} from KV archive "
            f"(format={detected_format})"
        )

    async def _delete_kv_key_with_retry(self, key: str, *, attempts: int = 3) -> None:
        """有界重试删除单个 KV 键（≤3 次，`await asyncio.sleep(0)` 退避）。

        MEM-03 PR-2（design §4 结论提前落地）：废弃"失败即丢/靠 WAL 事后盲重放"，
        改为一次瞬时删除失败就地重试。fail-safe：重试耗尽只记日志，绝不向上抛出——
        不能让一个键的删除失败中断整个 delete/purge/session-deleted op 的其余步骤。
        """
        delete_fn = getattr(self._p, "delete_kv_data", None)
        if not callable(delete_fn):
            return
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                await delete_fn(key)
                return
            except Exception as e:  # noqa: BLE001 — fail-safe：绝不让删除失败中断 op
                last_exc = e
                if attempt < attempts - 1:
                    await asyncio.sleep(0)
        logger.warning(
            f"Sylanne memory delete: {key!r} failed after {attempts} attempts: {last_exc}"
        )

    async def _scrub_kernel_alpha_json_memory(self, session_key: str) -> None:
        """清空 kernel 文件（.alpha.json）里的 body.memory['_memory_system'] + traces。

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
            return
        try:
            host.kernel.body.memory.pop("_memory_system", None)
            host.kernel.body.memory["traces"] = []
            await asyncio.to_thread(host.runtime.save, host.kernel)
        except Exception as e:
            logger.debug(
                f"Sylanne memory kernel file scrub failed for {session_key!r}: {e}"
            )

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
        陈旧引用把已删记忆写回）。真逻辑见 `_delete_sylanne_memory_state_impl`，只准
        经咽喉 op 调用；delete kind 自身豁免验章（定义 bump，幂等，见
        `MemoryWriteThroat._validate`）。

        Args:
            session_key: 会话标识。
        """
        self._throat.bump_epoch(
            session_key, occupant=self._current_memory_occupant(session_key)
        )
        fut = self._throat.submit(
            session_key,
            lambda: self._delete_sylanne_memory_state_impl(session_key),
            kind="delete",
            state=None,
        )
        if fut is not None:
            await fut

    async def _delete_sylanne_memory_state_impl(self, session_key: str) -> None:
        """delete 真逻辑——只准经咽喉 op 调用（勿直接 await，会绕过串行化 + 栅栏
        bump 记账）。记忆子系统全部三键，primary-first 顺序
        （primary → backup_v2 → quarantine，design §4 固定顺序），每键有界重试删除；
        并清扫 .alpha.json 里的 _memory_system 救援残留（见下）。
        """
        from .memory_legacy_formats import quarantine_kv_key

        self._p._store.sylanne_memory_cache.pop(session_key, None)
        safe = self._safe_session_key(session_key)
        for key in (
            self.sylanne_memory_kv_key(session_key),
            self.sylanne_memory_backup_v2_kv_key(session_key),
            quarantine_kv_key(safe),
        ):
            await self._delete_kv_key_with_retry(key)
        # 红队 must-fix（第 4 条复活臂）/ PR-2 gate：.alpha.json 里的 _memory_system 是
        # load 第 5 级救援的读取源，已删会话若留着它会被 WebUI overview salvage 读回、
        # 再周期 save 写回 KV = 删除从未发生。收进本【规范删除原语】——所有清除入口
        # （含 WebUI /api/purge_data 走的独立 delete_sylanne_memory_state 路径，此前只有
        # meltdown / session-delete 两条 op 各自 scrub、漏了 purge_data）自动获得清扫，
        # 不再各自漏一处。host 不存在时 scrub 内部安全早返回。
        await self._scrub_kernel_alpha_json_memory(session_key)

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
        `delete_sylanne_memory_state`）：本 op 已经跑在本 session 的 drainer 任务
        内部，若改调壳，壳会对同一 session 队列再 submit + await，命中
        `MemoryWriteThroat.submit()` 的 task-identity re-entrancy 断言（立即
        RuntimeError）——单 drainer 等一个只有自己能完成的 Future 本就是永久停摆，
        该断言正是为拦这个真实会发生的场景。
        """
        await self._delete_sylanne_memory_state_impl(session_key)
        delete_fn = getattr(self._p, "delete_kv_data", None)
        if delete_fn and callable(delete_fn) and self.has_kv_api():
            safe = self._safe_session_key(session_key)
            for key in (
                self.kernel_kv_key(session_key),
                f"{self.kernel_kv_key(session_key)}_backup",
                f"sylanne_v2core_domains:{safe}",
            ):
                await self._delete_kv_key_with_retry(key)
        cache = getattr(self._p, "_v2core_runtimes", None)
        if isinstance(cache, dict):
            cache.pop(session_key, None)
        # .alpha.json 清扫已在 _delete_sylanne_memory_state_impl 里做过（规范原语），此处不再重复。

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
        删除（经 `_delete_sylanne_memory_state_impl`，非公开壳）+ kernel .alpha.json
        文件 scrub + `sylanne_v2core_domains` 侧车键，一次性删干净。
        """
        await self._delete_sylanne_memory_state_impl(session_key)
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
                await self._delete_kv_key_with_retry(key)
        # .alpha.json 清扫已在上面的 _delete_sylanne_memory_state_impl 里做过（规范原语），此处不再重复。

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
            # 刻意只对非 "user" 一侧（bot/assistant）生效：会真正跟框架
            # _save_to_history 并发写的只有 bot 侧同步（request 阶段的 user 同步
            # 发生在 LLM 调用之前，压根不存在并发写这回事）。若不加这条限制，用户
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
            logger.debug(f"Sylanne: ConversationManager sync failed: {e}")

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
