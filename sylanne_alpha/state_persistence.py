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
import logging
import math
import zlib
from typing import TYPE_CHECKING, Any

from sylanne_alpha.utils import safe_ensure_future

if TYPE_CHECKING:
    from .host import SylanneAlphaHost

logger = logging.getLogger("astrbot_plugin_sylanne")

# ---------------------------------------------------------------------------
# 增量持久化 dirty-flag 机制（Item 12）
# ---------------------------------------------------------------------------

_VALID_SUBSYSTEMS = frozenset({"personality", "memory", "spine", "session"})


class _DirtyTracker:
    """实例级脏标记追踪器，避免模块级全局状态在多实例/热重载时污染。"""

    __slots__ = ("_subsystems",)

    def __init__(self):
        self._subsystems: set[str] = set()

    def mark(self, subsystem: str) -> None:
        if subsystem in _VALID_SUBSYSTEMS:
            self._subsystems.add(subsystem)

    def swap(self) -> set[str]:
        """原子地取出当前脏集合并清空，避免 get+clear 之间的竞态。"""
        taken = self._subsystems
        self._subsystems = set()
        return taken

    def is_dirty(self) -> bool:
        return bool(self._subsystems)


# 模块级实例——StatePersistence.__init__ 中会替换为自己的实例
_dirty = _DirtyTracker()


def mark_dirty(subsystem: str) -> None:
    """标记某子系统为脏（需要持久化）。向后兼容的模块级 API。"""
    _dirty.mark(subsystem)


def is_dirty() -> bool:
    """是否有任何子系统需要持久化。"""
    return _dirty.is_dirty()


def swap_dirty() -> set[str]:
    """原子地取出当前脏集合并清空。"""
    return _dirty.swap()


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

    def __init__(self, plugin: Any) -> None:
        """初始化持久化层。

        Args:
            plugin: Sylanne 插件实例。
        """
        self._p = plugin
        self._buffer_persist_timers: dict[str, asyncio.TimerHandle] = {}

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

        # 增量持久化：dirty set 为空时跳过 save（减少无变化时的 IO）
        if not is_dirty():
            return

        dirty_set = swap_dirty()
        snapshot = host.kernel.snapshot()

        if self.has_kv_api():
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
        buf = self._p._conversation_buffers.get(session_key)
        if not buf:
            return
        host = self._p._hosts.get(session_key)
        if not host or not hasattr(host, "runtime"):
            return
        buf_dict = buf.to_dict()
        await self.persist_buffer(session_key, host, buf_dict)

    # ------------------------------------------------------------------
    # 启动时 Buffer 恢复
    # ------------------------------------------------------------------

    def restore_buffers_on_boot(self) -> None:
        """插件启动时从文件恢复对话缓冲区（同步回退路径）。

        KV 数据通过 persist_buffer 保持同步，此处文件 IO 等效。
        异步 KV 加载在同步上下文中不可用，故使用文件回退。
        """
        from .memory_system import ConversationBuffer

        for sk, host in list(self._p._hosts.items()):
            if not hasattr(host, "runtime"):
                continue
            data = host.runtime.load_buffer(sk)
            if data and isinstance(data, dict):
                self._p._conversation_buffers[sk] = ConversationBuffer.from_dict(data)

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
        cache[session_key] = data
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

    async def save_sylanne_memory_state(
        self, session_key: str, state: Any = None
    ) -> None:
        """保存 Sylanne 记忆状态到缓存和 KV 存储。

        同时更新内存缓存和 _memory_systems 引用，确保后续读取一致。

        Args:
            session_key: 会话标识。
            state: MemorySystem 实例或可序列化的状态对象。
        """
        if state is None:
            return
        from .memory_system import MemorySystem

        cache = self._p._sylanne_memory_cache
        if not isinstance(cache, dict):
            cache = {}
        self._p._sylanne_memory_cache = cache
        cache[session_key] = state
        if isinstance(state, MemorySystem):
            self._p._memory_systems[session_key] = state
        kv_key = self.sylanne_memory_kv_key(session_key)
        put_fn = getattr(self._p, "put_kv_data", None)
        if put_fn and callable(put_fn):
            data = state.to_dict() if hasattr(state, "to_dict") else state
            await put_fn(kv_key, data)

    async def load_sylanne_memory_state(
        self, session_key: str, *, now: float = 0.0
    ) -> Any:
        """加载 Sylanne 记忆状态，支持多级回退和衰减遗忘。

        查找顺序：
        1. 内存缓存 (_sylanne_memory_cache)
        2. 活跃记忆系统 (_memory_systems)
        3. KV 存储（支持 MemorySystem 和旧版 SylanneMemoryState 两种格式）
        4. kernel body.memory 中的持久化数据

        当提供 now 参数时，对旧版格式执行半衰期衰减遗忘。

        Args:
            session_key: 会话标识。
            now: 当前时间戳，用于衰减计算（0 表示不执行衰减）。

        Returns:
            记忆状态对象，无数据时返回 None。
        """
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

        cache = self._p._sylanne_memory_cache
        if not isinstance(cache, dict):
            cache = {}
        self._p._sylanne_memory_cache = cache
        cached_state = cache.get(session_key) if isinstance(cache, dict) else None
        if has_content(cached_state):
            return cache[session_key]
        # 检查活跃记忆系统
        system_cache = getattr(self._p, "_memory_systems", {}) or {}
        live_state = (
            system_cache.get(session_key) if isinstance(system_cache, dict) else None
        )
        if has_content(live_state):
            return live_state
        # 从 KV 存储加载
        kv_key = self.sylanne_memory_kv_key(session_key)
        get_fn = getattr(self._p, "get_kv_data", None)
        put_fn = getattr(self._p, "put_kv_data", None)
        if get_fn and callable(get_fn):
            data = await get_fn(kv_key, None)
            if data is not None:
                # 尝试作为新版 MemorySystem 格式解析
                if isinstance(data, dict) and {
                    "l1",
                    "l2",
                    "l3_nodes",
                    "l3_edges",
                }.issubset(data.keys()):
                    try:
                        state = MemorySystem.create_from_dict(data)
                        self._p._memory_systems[session_key] = state
                        cache[session_key] = state
                        return state
                    except Exception as e:
                        logger.debug(f"Sylanne skip: {e}")
                # 尝试作为旧版 SylanneMemoryState 格式解析
                try:
                    from memory_engine import SylanneMemoryState

                    state = SylanneMemoryState.from_dict(data)
                    # 执行半衰期衰减遗忘
                    if now and hasattr(state, "records"):
                        original_count = len(state.records)
                        surviving = []
                        for rec in state.records:
                            auto_params = getattr(rec, "auto_parameters", None) or {}
                            half_life = float(
                                auto_params.get("decay_half_life_seconds", 0)
                            )
                            if half_life > 0:
                                created = getattr(rec, "created_at", 0.0)
                                elapsed = now - created
                                # 指数衰减：exp(-ln2 * elapsed / half_life)
                                decay = math.exp(-0.693 * elapsed / half_life)
                                effective_depth = getattr(rec, "depth", 0.5) * decay
                                if effective_depth < 0.01:
                                    continue  # 衰减到阈值以下，遗忘
                            surviving.append(rec)
                        forgotten_count = original_count - len(surviving)
                        state.records = surviving
                        # 记录遗忘数量并回写 KV
                        if forgotten_count > 0:
                            if hasattr(state, "dynamics") and hasattr(
                                state.dynamics, "notes"
                            ):
                                state.dynamics.notes = f"forgotten={forgotten_count}"
                            if put_fn and callable(put_fn):
                                save_data = state.to_dict()
                                await put_fn(kv_key, save_data)
                    cache[session_key] = state
                    return state
                except Exception as e:
                    logger.debug(f"Sylanne skip: {e}")
        # 最后回退：从 kernel body.memory 中加载
        try:
            host = self._p._host(session_key)
            data = host.kernel.body.memory.get("_memory_system")
            if isinstance(data, dict):
                state = MemorySystem.create_from_dict(data)
                self._p._memory_systems[session_key] = state
                cache[session_key] = state
                return state
        except Exception as e:
            logger.debug(f"Sylanne skip: {e}")
        # 返回任何可用的缓存状态（即使为空）
        if cached_state is not None:
            return cached_state
        if live_state is not None:
            return live_state
        return None

    async def delete_sylanne_memory_state(self, session_key: str) -> None:
        """删除 Sylanne 记忆状态（缓存 + KV 存储）。

        Args:
            session_key: 会话标识。
        """
        cache = self._p._sylanne_memory_cache
        cache.pop(session_key, None)
        kv_key = self.sylanne_memory_kv_key(session_key)
        delete_fn = getattr(self._p, "delete_kv_data", None)
        if delete_fn and callable(delete_fn):
            await delete_fn(kv_key)

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

    # 会话删除时需要清理的容器属性名注册表
    _SESSION_KEYED_CONTAINERS: tuple[str, ...] = (
        "_hosts", "_memory_systems", "_conversation_buffers",
        "_unfinished_replies", "_stream_buffers", "_stream_first_sent",
        "_segmented_tasks", "_last_request_budgets",
        "_last_understanding_closed_loop", "_last_bot_expression_time",
        "_last_user_texts", "_last_bot_texts",
        "_conversation_input_epoch", "_last_request_text",
        "_user_message_withdrawals", "_background_post_queues",
        "_background_post_dead_letters", "_background_post_sequence",
        "_background_post_latest_enqueued", "_background_post_last_committed",
        "_background_post_active", "_background_post_worker_state",
        "_pending_outreach_context", "_proactive_candidate_sessions",
        "_last_user_message_time", "_sylanne_memory_cache",
        "_conversation_pending_response_epochs",
        "_group_atmosphere_injection_snapshot_cache",
        "_realtime_ordinary_history_backfills",
        "_realtime_chat_active_dispatches",
    )

    def _on_session_deleted(self, session_key: str) -> None:
        """AstrBot 会话删除回调——释放 Sylanne 侧的会话资源。"""
        p = self._p
        for attr in self._SESSION_KEYED_CONTAINERS:
            container = getattr(p, attr, None)
            if container is None:
                continue
            if isinstance(container, dict):
                container.pop(session_key, None)
            elif hasattr(container, "pop"):
                try:
                    container.pop(session_key, None)
                except Exception:
                    pass
        p._amnesia_sessions.discard(session_key)
        p._session_locks.pop(session_key, None)
        # 异步清理 KV 存储中的持久化数据
        safe_ensure_future(
            self._cleanup_kv_for_session(session_key),
            name=f"kv_cleanup_{session_key}",
        )
        logger.debug(f"Sylanne: session resources released for {session_key}")

    async def _cleanup_kv_for_session(self, session_key: str) -> None:
        """删除 KV 存储中该 session 的所有持久化数据。"""
        if not self.has_kv_api():
            return
        safe = self._safe_session_key(session_key)
        keys_to_delete = [
            f"sylanne_kernel_{safe}",
            f"sylanne_kernel_{safe}_backup",
            f"sylanne_buffer_{safe}",
            f"emotion_state:{safe}",
            f"sylanne_memory_state:{safe}",
        ]
        delete_fn = getattr(self._p, "delete_kv_data", None)
        if not delete_fn:
            return
        for key in keys_to_delete:
            try:
                await delete_fn(key)
            except Exception:
                pass

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
        try:
            # 获取或创建当前会话
            curr_cid = await conv_mgr.get_curr_conversation_id(session_key)
            if not curr_cid:
                curr_cid = await conv_mgr.new_conversation(session_key)

            # 尝试使用 AstrBot 消息类型；不可用时回退到普通字典
            try:
                from astrbot.core.agent.message import (
                    AssistantMessageSegment,
                    TextPart,
                    UserMessageSegment,
                )

                if role == "user":
                    msg = UserMessageSegment(content=[TextPart(text=text)])
                else:
                    msg = AssistantMessageSegment(content=[TextPart(text=text)])
            except ImportError:
                # 旧版 AstrBot 或测试环境：使用普通字典
                msg = {"role": role, "content": text}

            conversation = await conv_mgr.get_conversation(session_key, curr_cid)
            history = list(
                getattr(conversation, "history", None) or [] if conversation else []
            )
            history.append(msg)
            await conv_mgr.update_conversation(session_key, curr_cid, history=history)
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
            host = p._hosts.get(session_key)
            if not host:
                return
            # 从 kernel 提取人格数据
            personality = (
                host.kernel._personality()
                if hasattr(host.kernel, "_personality")
                else {}
            )
            if not personality or not isinstance(personality, dict):
                return

            traits = personality.get("traits", {})
            voice = personality.get("voice", {})

            # 从人格状态构建 system prompt 片段
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

            # 先尝试更新，不存在则创建
            try:
                existing = persona_mgr.get_persona(persona_id)
                if existing:
                    persona_mgr.update_persona(persona_id, system_prompt=system_prompt)
                else:
                    persona_mgr.create_persona(
                        persona_id=persona_id,
                        system_prompt=system_prompt,
                        begin_dialogs=[],
                        tools=None,
                    )
            except Exception:
                # 旧版 API 可能不接受所有参数
                try:
                    persona_mgr.create_persona(
                        persona_id=persona_id,
                        system_prompt=system_prompt,
                    )
                except Exception:
                    pass  # persona 同步失败可接受
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
        p._cfg_bool("allow_emotion_reset_backdoor", True)
        p._cfg_bool("enable_psychological_screening", False)
        p._cfg_float("sylanne_memory_idle_commit_delay_seconds", 4.0)
        p._cfg_bool("sylanne_memory_vector_retrieval_enabled", True)
        p._cfg("sylanne_memory_embedding_provider_id", "")
        p._cfg_float("sylanne_memory_record_embedding_min_interval_seconds", 300.0)
        p._cfg_int("sylanne_memory_record_embedding_max_per_flush", 1)
        p._cfg_bool("sylanne_memory_debug_view_enabled", False)
        p._cfg_bool("humanlike_memory_write_enabled", True)
        p._cfg_bool("allow_humanlike_reset_backdoor", True)
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
        task = getattr(p, "_proactive_scheduler_task", None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        p._proactive_scheduler_task = None
        p._proactive_candidate_sessions = {}
        p._proactive_scheduler_locks = {}
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
        bg_queues = p._background_post_queues
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
        p._background_post_queues = {}
        p._background_post_sequence = {}
        p._background_post_skipped = {}
        p._terminating = True
        try:
            from sylanne_alpha.webui_server import stop_webui_server

            await stop_webui_server()
        except Exception:
            pass
