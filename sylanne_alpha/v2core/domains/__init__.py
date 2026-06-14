"""v2core 底层领域 agent —— 各自独占一块领域状态，是该状态的唯一写者。

地基阶段先迁 MemoryAgent（记忆系统已是最干净、测试最全的模块，最适合第一个绞入，
且能用旧的 MemorySystem 当 oracle 双跑对照）。Emotion / Relation / Persona 后续逐个迁。
"""

from __future__ import annotations

from sylanne_alpha.v2core.domains.memory import MemoryDomain

__all__ = ["MemoryDomain"]
