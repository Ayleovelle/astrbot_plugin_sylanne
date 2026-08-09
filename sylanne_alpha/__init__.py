"""sylanne_alpha 包初始化模块。

导出 Sylanne 计算核心的公共符号。CP7 后计算实现统一为 vendored SylannEngine
共振场（_engine/sylanne_core），本包从 SDK 重导出等价符号（同源同名），旧的
sylanne_alpha 计算模块已删除：
- AlphaBodyState: 身体状态模型
- SylanneAlphaHost / SylanneAlphaHostEvent: 会话宿主（host.py 的共振场子类/重导出）
- AlphaKernel / AlphaKernelEvent: 计算核心调度器及其事件
- AlphaRuntime: 文件系统持久化运行时
"""

from __future__ import annotations

from sylanne_alpha._engine.sylanne_core.compute.body import AlphaBodyState
from sylanne_alpha._engine.sylanne_core.compute.kernel import (
    AlphaKernel,
    AlphaKernelEvent,
)
from sylanne_alpha._engine.sylanne_core.compute.runtime import AlphaRuntime

from .host import SylanneAlphaHost, SylanneAlphaHostEvent

__all__ = [
    "AlphaBodyState",
    "SylanneAlphaHost",
    "SylanneAlphaHostEvent",
    "AlphaKernel",
    "AlphaKernelEvent",
    "AlphaRuntime",
]
