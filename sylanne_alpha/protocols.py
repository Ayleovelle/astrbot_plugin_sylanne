"""Protocol 接口定义模块。

定义 Sylanne 插件子组件所需的最小接口契约，用 typing.Protocol 替代
原先 `plugin: Any` 的松散类型，使各模块间的依赖关系显式化、可静态检查
（CI 的 pyright 会按这些契约校验各模块对 `self._p.xxx` 的访问）。

分层设计：
- PluginConfig:        配置读取接口（~6 成员）
- PluginSessionAccess: 会话管理 + 运行时态访问接口（最大域）
- PluginPersistence:   状态持久化（KV / 状态加载删除）接口
- PluginWebUI:         WebUI 生命周期 / 页面 payload 接口
- PluginHost:          以上四者的并集，供跨域宽访问的重模块使用

注解策略：本文件已启用 `from __future__ import annotations`，所有注解
惰性求值（字符串化），因此业务返回类型（SylanneAlphaHost / MemorySystem
等）可放在 TYPE_CHECKING 块内 import，运行时零导入、彻底规避循环依赖。

注意（实现约束，勿违反）：
- runtime_checkable Protocol 只检查成员"存在性"不检查签名，勿依赖它做签名保证。
- `__class__` 是 object 内建属性，任何实现天然满足，不在 Protocol 中声明。
- main.py 中不存在、由子模块首次访问时惰性创建的字段（_safe_session_key_cache /
  _offline_buffers / _engine_cache / _cached_system_prompts）不声明为 Protocol
  成员，以免误导"已初始化"或将来 isinstance 误判。
- 名字像属性实为方法的成员（_observed_now / _persona_profile /
  _webui_runtime_info / _known_webui_sessions）必须声明为方法。
"""

from __future__ import annotations

import asyncio
import collections
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from sylanne_alpha.host import SylanneAlphaHost
    from sylanne_alpha.scope_contracts import SessionScope
    from sylanne_alpha.scope_identity import ScopeResolver
    from sylanne_alpha.scope_runtime import (
        PersonaRuntime,
        ScopeRuntimeRegistry,
        ScopedSessionRuntime,
    )
    from sylanne_alpha.session_state_store import SessionStateStore
    from sylanne_alpha.memory_system import MemorySystem


@runtime_checkable
class PluginConfig(Protocol):
    """配置访问接口。

    提供统一的配置读取方法，子组件通过此接口获取插件配置，
    而无需直接依赖插件实例的具体实现。
    """

    config: dict[str, Any]
    _config: dict[str, Any]
    logger: Any

    def _cfg(self, key: str, default: Any = "") -> Any: ...
    def _cfg_bool(self, key: str, default: bool = False) -> bool: ...
    def _cfg_float(self, key: str, default: float = 0.0) -> float: ...
    def _cfg_int(self, key: str, default: int = 0) -> int: ...


@runtime_checkable
class PluginSessionAccess(Protocol):
    """会话管理 + 运行时态访问接口。

    生产私有路径先取得冻结 ``SessionScope``，再通过 registry 绑定其唯一的
    PersonaRuntime/ScopedSessionRuntime。``_store``、``_host``、``_session_key``
    仅可在这个绑定内部使用；没有 scope 的兼容桩必须走名称明确的 legacy reader。
    """

    _store: SessionStateStore
    _scope_runtime_registry: ScopeRuntimeRegistry
    _scope_resolver_v1: ScopeResolver | None
    _background_tasks: list[asyncio.Task]
    _computation_logs: collections.deque

    def _session_key(self, event: Any = None, session_key: str = "") -> str: ...
    def _host(self, session_key: str) -> SylanneAlphaHost: ...
    def _memory_system_for_session(self, session_key: str) -> MemorySystem: ...
    def _runtime_for_event(self, event: Any) -> PersonaRuntime: ...
    def _session_runtime_for_event(self, event: Any) -> ScopedSessionRuntime: ...
    def _host_for_scope(self, scope: SessionScope) -> SylanneAlphaHost: ...
    def _memory_system_for_scope(self, scope: SessionScope) -> MemorySystem: ...
    def _bound_runtime(self) -> Any | None: ...
    async def observe_response(
        self,
        session_key: str,
        *,
        text: str = "",
        confidence: float = 0.0,
        flags: list[str] | None = None,
        now: float = 0.0,
    ) -> dict[str, Any]: ...


@runtime_checkable
class PluginPersistence(Protocol):
    """状态持久化接口（KV 键派生 / 会话键规范化 / KV 能力探测）。"""

    def _safe_session_key(self, session_key: str) -> str: ...
    def _kernel_kv_key(self, session_key: str) -> str: ...
    def _buffer_kv_key(self, session_key: str) -> str: ...
    def _has_kv_api(self) -> bool: ...


@runtime_checkable
class PluginWebUI(Protocol):
    """WebUI 生命周期 / 页面 payload 接口。

    注意：_webui_runtime_info / _known_webui_sessions / _persona_profile /
    _observed_now 名字像属性实为方法，必须声明为方法（见模块顶部约束）。
    """

    def _webui_runtime_info(self) -> dict[str, Any]: ...
    def _known_webui_sessions(self, requested: str = "") -> list[str]: ...
    def _persona_profile(self, event: Any = None) -> dict[str, Any]: ...
    def _observed_now(self) -> float: ...


@runtime_checkable
class PluginHost(
    PluginConfig,
    PluginSessionAccess,
    PluginPersistence,
    PluginWebUI,
    Protocol,
):
    """跨域宽访问插件接口（以上四者的并集）。

    供大量直穿 `self._p.xxx` 的重模块（llm_response_pipeline / webui_routes /
    state_persistence / background_queue / session_context 等）使用。窄访问
    模块可只依赖对应的细粒度 Protocol，以收紧契约。
    """
