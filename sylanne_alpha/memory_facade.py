"""MEM-03 PR-6：MemoryFacade 门面——薄转发层，签名逐字不变。

设计见 docs/architecture/mem-phase1-write-throat-design.md §6：main.py 的四条
记忆委托方法改转发本门面同名方法，本门面内部再转发到真正的实现方——
`SessionContext.memory_system_for_session`（同步 accessor，冻结契约，不能改
async）与 `StatePersistence` 的三个记忆持久化方法（写走单写咽喉 + 化身栅栏）。

本模块【不】新增任何逻辑/状态/fail-open——纯转发。`MemorySystem.recall` /
`write_summary` 不搬进本门面（v2core/domains/memory.py:62 的 positional 调用
依赖它们留在原处，冻结面）。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sylanne_alpha.memory_system import MemorySystem
    from sylanne_alpha.protocols import PluginHost
    from sylanne_alpha.scope_repository import ScopedPersistenceGateway
    from sylanne_alpha.state_persistence import ScopedStatePersistence


class MemoryFacade:
    """记忆子系统门面：转发到 SessionContext（同步 accessor）+ StatePersistence（持久化）。

    通过 self._p 引用插件实例，与 SessionContext/StatePersistence 等既有委托模块
    同款构造模式。
    """

    def __init__(self, plugin: "PluginHost") -> None:
        self._p = plugin

    def memory_system_for_session(self, session_key: str) -> "MemorySystem":
        """获取指定会话的记忆系统实例（懒创建）。

        MEM-02①冻结同步契约：本方法必须保持同步（无 await）——
        session_context.py:793-799 的懒创建热路径依赖同步返回。
        """
        return self._p._session_ctx.memory_system_for_session(session_key)

    async def save_sylanne_memory_state(self, session_key: str, state: Any = None) -> None:
        """保存 Sylanne 记忆状态（经单写咽喉串行化 + 化身栅栏验章）。"""
        await self._p._state_persistence.save_sylanne_memory_state(session_key, state)

    async def load_sylanne_memory_state(self, session_key: str, *, now: float = 0.0) -> Any:
        """加载 Sylanne 记忆状态，支持多级回退（见 StatePersistence 同名方法文档）。"""
        return await self._p._state_persistence.load_sylanne_memory_state(
            session_key, now=now
        )

    async def delete_sylanne_memory_state(self, session_key: str) -> None:
        """删除 Sylanne 记忆状态——记忆子系统拥有的全部三个 KV 键 + 内存缓存。"""
        await self._p._state_persistence.delete_sylanne_memory_state(session_key)


class ScopedMemoryFacade:
    """Gateway-only memory facade for inactive scoped ingress.

    Unlike :class:`MemoryFacade`, this API deliberately has no session-key
    parameter and therefore cannot resolve a current/default session or enter
    the legacy KV/file persistence path.
    """

    __slots__ = ("_state",)

    def __init__(self, state: "ScopedStatePersistence") -> None:
        from .state_persistence import ScopedStatePersistence

        if type(state) is not ScopedStatePersistence:
            raise ValueError("state must be a ScopedStatePersistence")
        self._state = state

    @property
    def gateway(self) -> "ScopedPersistenceGateway":
        """Expose the frozen gateway for integration wiring only."""

        return self._state.gateway

    async def load_memory(self) -> "MemorySystem | None":
        return await self._state.load_memory()

    async def save_memory(self, memory: "MemorySystem") -> bool:
        return await self._state.save_memory(memory)

    def schedule_memory_save(
        self,
        memory: "MemorySystem",
        *,
        delay_seconds: float,
    ) -> "asyncio.Task[bool]":
        return self._state.schedule_memory_save(memory, delay_seconds=delay_seconds)


__all__ = ["MemoryFacade", "ScopedMemoryFacade"]
