"""v2core 上层能力 agent —— 无独占状态，通过领域 agent 接口读写，注册表驱动。

加新能力 = 在这里加一个实现 Capability 协议的类 + SelfCore.register(...) 一行。
不改 SelfCore.turn() 主体——这是"诚实零侵入扩展"。

地基阶段先迁 RecallCapability（走通"用户消息→召回"主链端到端）。
"""

from __future__ import annotations

from sylanne_alpha.v2core.capabilities.recall import RecallCapability

__all__ = ["RecallCapability"]
