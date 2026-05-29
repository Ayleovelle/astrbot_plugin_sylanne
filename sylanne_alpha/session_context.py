"""会话管理模块。

提供 SessionContext 类，封装 Sylanne 插件的会话生命周期管理：
- session key 派生（从事件对象提取唯一会话标识）
- 每会话锁（防止同一会话并发处理）
- host 实例管理（LRU 缓存 + 懒加载 + 编码器共享）
- 记忆系统注水（从持久化 traces 恢复记忆状态）

所有方法通过 self._p 委托访问插件实例的属性和方法。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

try:
    from astrbot.api import logger  # type: ignore
    from astrbot.core.utils.astrbot_path import get_astrbot_data_path  # type: ignore
except ImportError:
    import logging as _logging

    logger = _logging.getLogger("astrbot_plugin_sylanne")  # type: ignore

    def get_astrbot_data_path() -> Path:  # type: ignore
        return Path.home()


from sylanne_alpha.host import SylanneAlphaHost
from sylanne_alpha.memory_system import ConversationBuffer, MemorySystem


class SessionContext:
    """封装 Sylanne 插件的会话管理逻辑。

    作为插件实例的委托层，将会话相关的复杂逻辑（key 派生、锁管理、
    host 生命周期、记忆系统初始化）从主插件类中解耦出来。
    """

    def __init__(self, plugin: Any) -> None:
        """初始化会话上下文。

        Args:
            plugin: Sylanne 插件实例，通过 self._p 访问其内部状态。
        """
        self._p = plugin

    # ------------------------------------------------------------------
    # Session key 派生
    # ------------------------------------------------------------------

    def session_key(self, event: Any = None, session_key: str = "") -> str:
        """从事件对象派生会话标识。

        派生规则：
        1. 显式传入 session_key 时直接使用
        2. 从 event 中提取 session_id / unified_msg_origin
        3. 群聊场景下追加 sender_id，确保每个用户独立的计算脊柱

        Args:
            event: AstrBot 事件对象。
            session_key: 显式指定的会话键（优先级最高）。

        Returns:
            派生出的会话标识字符串。
        """
        if session_key:
            return session_key
        if event is not None:
            base = str(
                getattr(event, "session_id", "")
                or getattr(event, "unified_msg_origin", "")
                or "default"
            )
            # 群聊中追加 sender_id，使每个用户拥有独立的 host/kernel/计算脊柱
            sender_id = str(
                getattr(event, "sender_id", "") or getattr(event, "user_id", "") or ""
            )
            if sender_id and base != "default":
                return f"{base}:{sender_id}"
            return base
        return "default"

    # ------------------------------------------------------------------
    # 每会话锁
    # ------------------------------------------------------------------

    def session_lock(self, session_key: str) -> asyncio.Lock:
        """获取指定会话的异步锁（懒创建）。

        当锁字典超过 500 个条目时，清理未锁定的旧条目到 400 以下，
        防止长期运行时内存泄漏。

        Args:
            session_key: 会话标识。

        Returns:
            该会话对应的 asyncio.Lock 实例。
        """
        locks = self._p._session_locks
        if session_key not in locks:
            locks[session_key] = asyncio.Lock()
            # 锁字典过大时清理未使用的旧锁，防止内存泄漏
            if len(locks) > 500:
                to_remove = []
                for k, lock in locks.items():
                    if k != session_key and not lock.locked():
                        to_remove.append(k)
                    if len(locks) - len(to_remove) <= 400:
                        break
                for k in to_remove:
                    del locks[k]
        return locks[session_key]

    # ------------------------------------------------------------------
    # 文件系统安全的 session key
    # ------------------------------------------------------------------

    def safe_session_key(self, session_key: str) -> str:
        """将 session_key 转换为文件系统安全的字符串。

        移除 <>:"|?* 等不安全字符，将 / \\ 替换为 _，
        截断到 200 字符防止路径过长。结果会被缓存。

        Args:
            session_key: 原始会话标识。

        Returns:
            文件系统安全的会话标识。
        """
        cache = getattr(self._p, "_safe_session_key_cache", None)
        if cache is None:
            self._p._safe_session_key_cache = {}
            cache = self._p._safe_session_key_cache
        if session_key in cache:
            return cache[session_key]
        # 移除文件系统不安全字符
        unsafe = '<>:"|?*\x00'
        safe = session_key.replace("/", "_").replace("\\", "_")
        for ch in unsafe:
            safe = safe.replace(ch, "_")
        # 截断防止路径过长
        if len(safe) > 200:
            safe = safe[:200]
        cache[session_key] = safe
        # 缓存过大时全量清空（简单策略，避免复杂 LRU）
        if len(cache) > 512:
            cache.clear()
        return safe

    # ------------------------------------------------------------------
    # 公共 session key 解析（用于 WebUI 等外部接口）
    # ------------------------------------------------------------------

    def resolve_public_session_key(
        self, event: Any = None, *, request: Any = None, session_key: str = ""
    ) -> str:
        """解析公共会话标识，用于 WebUI 等外部接口。

        与 session_key() 不同，此方法不追加 sender_id，返回的是
        "公共"级别的会话标识（如群聊的 unified_msg_origin）。

        Args:
            event: 事件对象或字符串。
            request: 请求对象（备选来源）。
            session_key: 显式指定的会话键。

        Returns:
            公共会话标识，无法确定时返回 "global"。
        """
        if session_key:
            return session_key
        if event is not None:
            if isinstance(event, str):
                return event
            umo = getattr(event, "unified_msg_origin", None)
            if umo:
                return str(umo)
        if request is not None:
            sid = getattr(request, "session_id", None)
            if sid:
                return str(sid)
        return "global"

    # ------------------------------------------------------------------
    # 记忆系统辅助方法
    # ------------------------------------------------------------------

    def memory_system_for_session(self, session_key: str) -> MemorySystem:
        """获取指定会话的记忆系统实例（懒创建）。

        Args:
            session_key: 会话标识。

        Returns:
            该会话对应的 MemorySystem 实例。
        """
        if not session_key:
            session_key = "default"
        systems = getattr(self._p, "_memory_systems", None)
        if systems is None:
            self._p._memory_systems = {}
            systems = self._p._memory_systems
        if session_key not in systems:
            systems[session_key] = MemorySystem()
        return systems[session_key]

    def memory_system_has_content(self, memory_system: Any) -> bool:
        """检查记忆系统是否包含有效内容（L1/L2/L3 任一非空）。

        Args:
            memory_system: MemorySystem 实例。

        Returns:
            True 表示至少有一层包含数据。
        """
        if memory_system is None:
            return False
        return bool(
            list(getattr(memory_system, "_l1", []) or [])
            or list(getattr(memory_system, "_l2", []) or [])
            or dict(getattr(memory_system, "_l3_nodes", {}) or {})
            or list(getattr(memory_system, "_l3_edges", []) or [])
        )

    def hydrate_memory_system_from_body_traces(
        self, session_key: str, memory_system: MemorySystem, traces: Any
    ) -> None:
        """从 body.memory.traces 注水记忆系统。

        当记忆系统为空但 kernel body 中存有历史 traces 时，
        将最近 50 条 trace 写入记忆系统以恢复状态。

        Args:
            session_key: 会话标识。
            memory_system: 目标记忆系统实例。
            traces: body.memory["traces"] 列表。
        """
        if self.memory_system_has_content(memory_system):
            return
        # 只取最近 50 条，避免冷启动时大量写入
        for trace in list(traces or [])[-50:]:
            if not isinstance(trace, dict):
                continue
            text = str(trace.get("text") or "").strip()
            if not text:
                continue
            try:
                temperature = float(
                    trace.get("temperature", trace.get("warmth", 0.5)) or 0.5
                )
            except (TypeError, ValueError):
                temperature = 0.5
            memory_system.write(
                text=text,
                embedding=trace.get("embedding"),
                temperature=max(0.0, min(1.0, temperature)),
            )
            # 恢复原始权重和创建时间
            if memory_system._l1:
                item = memory_system._l1[-1]
                try:
                    item.weight = max(
                        0.0, min(1.0, float(trace.get("weight", 1.0) or 1.0))
                    )
                except (TypeError, ValueError):
                    item.weight = 1.0
                try:
                    created_at = float(
                        trace.get("created_at", trace.get("updated_at", 0.0)) or 0.0
                    )
                    if created_at > 0:
                        item.created_at = created_at
                except (TypeError, ValueError):
                    pass

    # ------------------------------------------------------------------
    # 已知 WebUI 会话列表
    # ------------------------------------------------------------------

    def known_webui_sessions(self, requested: str = "") -> list[str]:
        """收集所有已知的会话标识，用于 WebUI 会话列表展示。

        从多个来源聚合：hosts 缓存、memory_systems、memory_cache、
        runtime 导出数据、磁盘 .alpha.json 文件。

        Args:
            requested: 当前请求的会话标识（确保包含在结果中）。

        Returns:
            去重后的会话标识列表。
        """
        sessions: list[str] = []

        def add(value: Any) -> None:
            text = str(value or "").strip()
            if text and text not in sessions:
                sessions.append(text)

        add(requested)
        for key in getattr(self._p, "_hosts", {}).keys():
            add(key)
        for key in getattr(self._p, "_memory_systems", {}).keys():
            add(key)
        cache = self._p._sylanne_memory_cache
        if isinstance(cache, dict):
            for key in cache.keys():
                add(key)
        # 从 runtime 导出中提取持久化过的 session
        for host in list(getattr(self._p, "_hosts", {}).values()):
            runtime = getattr(host, "runtime", None)
            export_all = getattr(runtime, "export_all", None)
            if not callable(export_all):
                continue
            try:
                exported = export_all()
            except Exception:
                continue
            persisted = (
                exported.get("sessions", {}) if isinstance(exported, dict) else {}
            )
            if isinstance(persisted, dict):
                for key in persisted.keys():
                    add(key)
        # 从磁盘文件名中提取 session key
        try:
            cfg = (
                self._p.config
                if hasattr(self._p, "_config")
                else getattr(self._p, "config", {}) or {}
            )
            root = Path(
                str(
                    cfg.get("sylanne_alpha_root")
                    or Path(get_astrbot_data_path()) / "sylanne_alpha"
                )
            )
            if root.exists():
                for path in root.glob("*.alpha.json"):
                    add(path.name[: -len(".alpha.json")])
        except Exception as e:
            logger.debug(f"Sylanne skip: {e}")
        if not sessions:
            add("default")
        return sessions

    # ------------------------------------------------------------------
    # Host 管理
    # ------------------------------------------------------------------

    def host(self, session_key: str) -> SylanneAlphaHost:
        """获取指定会话的 Host 实例（懒加载 + LRU 缓存）。

        首次访问时创建 Host 并执行以下初始化：
        1. LRU 驱逐：超过 _MAX_HOSTS 时持久化并移除最旧的 host
        2. 编码器共享：所有 host 共用同一个 encoder 实例节省内存
        3. 人格驱动记忆参数：从 personality 派生记忆系统参数
        4. 记忆恢复：从持久化数据或 body traces 恢复记忆状态
        5. 对话缓冲区恢复：从文件加载历史对话缓冲

        Args:
            session_key: 会话标识。

        Returns:
            该会话对应的 SylanneAlphaHost 实例。
        """
        if not session_key:
            session_key = "default"
        if not hasattr(self._p, "_hosts"):
            self._p._hosts = {}
        if session_key not in self._p._hosts:
            # LRU 驱逐：超容量时持久化并移除最旧的 host
            if len(self._p._hosts) >= self._p._MAX_HOSTS:
                oldest_key = next(iter(self._p._hosts))
                old_host = self._p._hosts.pop(oldest_key)
                self._p._persist_kernel_sync(oldest_key, old_host)
            cfg = (
                self._p.config
                if hasattr(self._p, "_config")
                else getattr(self._p, "config", {}) or {}
            )
            root = cfg.get("sylanne_alpha_root") or str(
                Path(get_astrbot_data_path()) / "sylanne_alpha"
            )
            host = SylanneAlphaHost(root=root, session_key=session_key)
            # 编码器共享：避免每个 host 各持有一份 encoder 浪费内存
            plugin_cls = type(self._p)
            if plugin_cls._shared_encoder is None:
                plugin_cls._shared_encoder = host.kernel.computation.encoder
            else:
                host.kernel.computation.replace_encoder(plugin_cls._shared_encoder)
            # 从人格状态派生记忆系统参数（人格驱动全参数）
            personality = (
                host.kernel._personality()
                if hasattr(host.kernel, "_personality")
                else {}
            )
            memory_system = self.memory_system_for_session(session_key)
            if personality and isinstance(personality, dict):
                memory_system.derive_params(personality)
            # 从持久化数据恢复记忆系统状态
            mem_data = host.kernel.body.memory.get("_memory_system")
            if mem_data and isinstance(mem_data, dict):
                memory_system.from_dict(mem_data)
            # 若记忆系统仍为空，尝试从 body traces 注水
            if not self.memory_system_has_content(memory_system):
                self.hydrate_memory_system_from_body_traces(
                    session_key,
                    memory_system,
                    host.kernel.body.memory.get("traces", []),
                )
                if self.memory_system_has_content(memory_system):
                    host.kernel.body.memory["_memory_system"] = memory_system.to_dict()
                    self._p._persist_kernel_sync(session_key, host)
            self._p._hosts[session_key] = host
            # 恢复对话缓冲区（文件回退；KV 保持同步）
            if session_key not in self._p._conversation_buffers:
                buf_data = host.runtime.load_buffer(session_key)
                if buf_data and isinstance(buf_data, dict):
                    self._p._conversation_buffers[session_key] = (
                        ConversationBuffer.from_dict(buf_data)
                    )
        else:
            # 已存在：移到末尾更新 LRU 顺序
            host = self._p._hosts.pop(session_key)
            self._p._hosts[session_key] = host
        return self._p._hosts[session_key]
