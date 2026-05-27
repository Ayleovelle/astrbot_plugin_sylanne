"""sylanne_alpha 包初始化模块。

导出 Sylanne-Embodiment 计算核心的公共符号：
- AlphaBodyState: 身体状态模型（脉搏/神经/免疫/伤口/需求等子系统）
- SylanneAlphaHost / SylanneAlphaHostEvent: 会话宿主对象及其事件
- import_legacy_body: 旧版 3.x 数据迁移导入器
- AlphaKernel / AlphaKernelEvent: 计算核心调度器及其事件
- AlphaRuntime: 文件系统持久化运行时
"""

from __future__ import annotations

from .body import AlphaBodyState
from .host import SylanneAlphaHost, SylanneAlphaHostEvent
from .importer import import_legacy_body
from .kernel import AlphaKernel, AlphaKernelEvent
from .runtime import AlphaRuntime

__all__ = [
    "AlphaBodyState",
    "SylanneAlphaHost",
    "SylanneAlphaHostEvent",
    "import_legacy_body",
    "AlphaKernel",
    "AlphaKernelEvent",
    "AlphaRuntime",
]
