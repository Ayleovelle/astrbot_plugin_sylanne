"""Protocol 接口定义模块。

定义 Sylanne 插件子组件所需的最小接口契约，用 typing.Protocol 替代
原先 `plugin: Any` 的松散类型，使各模块间的依赖关系显式化、可静态检查。

三个 Protocol 分别覆盖：
- PluginConfig: 配置读取接口
- PluginSessionAccess: 会话管理与运行时状态访问接口
- PluginPersistence: 状态持久化（KV 存储键派生）接口
"""

from __future__ import annotations

import asyncio
import collections
from typing import Any, Protocol, runtime_checkable

from sylanne_alpha.bounded_dict import BoundedDict


@runtime_checkable
class PluginConfig(Protocol):
    """配置访问接口。

    提供统一的配置读取方法，子组件通过此接口获取插件配置，
    而无需直接依赖插件实例的具体实现。
    """

    config: dict[str, Any]

    def _cfg(self, key: str, default: Any = "") -> Any: ...
    def _cfg_bool(self, key: str, default: bool = False) -> bool: ...
    def _cfg_float(self, key: str, default: float = 0.0) -> float: ...
    def _cfg_int(self, key: str, default: int = 0) -> int: ...


@runtime_checkable
class PluginSessionAccess(Protocol):
    """会话管理接口，供子组件访问运行时会话状态。

    包含 host 缓存、会话锁、记忆系统、对话缓冲区、后台任务列表
    以及计算日志等核心运行时数据结构的类型声明。
    """

    _hosts: BoundedDict
    _session_locks: dict[str, asyncio.Lock]
    _memory_systems: BoundedDict
    _conversation_buffers: BoundedDict
    _background_tasks: set[asyncio.Task]
    _computation_logs: collections.deque

    def _session_key(self, event: Any = None, session_key: str = "") -> str: ...
    def _host(self, session_key: str) -> Any: ...
    def _memory_system_for_session(self, session_key: str) -> Any: ...


@runtime_checkable
class PluginPersistence(Protocol):
    """持久化接口，定义 KV 存储键生成和可用性检查的契约。

    子组件通过此接口判断 KV API 是否可用，并获取标准化的存储键名。
    """

    def _has_kv_api(self) -> bool: ...
    def _kernel_kv_key(self, session_key: str) -> str: ...
    def _buffer_kv_key(self, session_key: str) -> str: ...
