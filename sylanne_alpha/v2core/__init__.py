"""Sylanne v2core —— 绞杀式重写的新骨架（地基阶段）。

设计依据见 docs/rewrite-blueprint-v3.md 与多轮架构辩论收敛结论：

  Body(SDK 计算核, 原样保留)
    │ observe() → BodySnapshot(只读)
    ▼
  底层领域 agent (各自独占状态 + 单一写者): Memory / Emotion / Relation / Persona
    ▲ 只能通过接口读写
    │
  上层能力 agent (无独占状态, 实现 Capability 协议): Recall / Expression / Proactive ...
    │
    ├─ 主链: SelfCore 三拍相位编排 (Percept→Deliberate→Evolve)
    │        持 budget_ms 时钟; 拍3 集中写; 能力槽注册表驱动 (加能力=注册一行)
    └─ 后台: 独立 Scheduler beat 自驱; 消费已提交快照; 不抢热路径

本包在旧 sylanne_alpha 旁边独立生长，地基阶段【不依赖、不修改】任何旧业务模块，
只通过显式注入的 Port 与外界（SDK / 存储 / LLM）打交道。旧代码作为 oracle 对照，
逐模块绞杀迁移，禁 flag-day。
"""

from __future__ import annotations

__all__ = [
    "contracts",
    "lexicon",
    "fragment",
    "session_store",
    "body_port",
    "body_port_v2",
    "migration",
    "renderer",
    "self_core",
    "turn_runner",
    "integration",
]
