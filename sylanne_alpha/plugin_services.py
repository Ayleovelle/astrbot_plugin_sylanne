"""PluginServices —— 只读服务容器，供各子模块共享插件级依赖。

将原先通过 ``self._p.xxx`` 散落访问的只读服务集中到一个轻量数据类中，
使依赖关系显式化，便于测试时注入 mock，也为后续进一步解耦做准备。

设计决策：
  - 不使用 frozen=True：config 字典本身可变（运行时热更新），冻结会阻止赋值。
  - 使用 slots=True：减少实例内存开销，属性访问更快。
  - 类型全部标注为 Any：避免循环导入（实际类型分布在 astrbot、sylanne_alpha 等包中）。
  - 可调用字段（put_kv_data 等）使用 Optional[Callable]：部分宿主环境不提供 KV 存储。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass(slots=True)
class PluginServices:
    """各子模块共享的只读插件服务引用。

    Attributes:
        config: 插件配置字典，运行时可能被热更新（所有模块读取）。
        logger: 日志记录器实例（多数模块使用模块级 logger，此处为备用注入点）。
        context: AstrBot 平台上下文对象，提供平台 API 访问。
        rhythm_learner: 节奏学习器，提供自适应分段/打字节奏参数。
        social_field: 社交场域引擎，管理群聊上下文和回复决策。
        put_kv_data: 持久化 KV 写入回调（async callable）。
        get_kv_data: 持久化 KV 读取回调（async callable）。
        delete_kv_data: 持久化 KV 删除回调（async callable）。
    """

    config: dict = field(default_factory=dict)
    logger: Any = None
    context: Any = None
    rhythm_learner: Any = None
    social_field: Any = None
    put_kv_data: Optional[Callable[..., Any]] = None
    get_kv_data: Optional[Callable[..., Any]] = None
    delete_kv_data: Optional[Callable[..., Any]] = None
