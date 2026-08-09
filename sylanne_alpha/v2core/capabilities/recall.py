"""RecallCapability —— 记忆召回能力 agent（v2core 第一个绞入的能力）。

挂在 DELIBERATE 拍（热路径）：关系够亲密时，通过 MemoryDomain 接口召回记忆，
产出 Intent（payload 带召回结果，供下游 ExpressionCapability / prompt 注入消费）。

纪律：
- 无独占状态：召回结果只挂在 BeatContext.scratch / Intent.payload，不自存。
- 内联同步直读 MemoryDomain.recall（热路径，不跨内部消息总线、不调 LLM）。
- 只读：召回不写任何状态；记忆衰减(tick_decay)是 EVOLVE 拍 MemoryDomain 自己的事。
- 受 SelfCore 的 budget_ms 时钟约束（超预算时本能力被跳过，不拖慢回复）。

对照旧架构 MemoryAgent：等价逻辑，但不再 self._p._store.last_user_texts /
self._p._memory_system_for_session 反向穿透——依赖（MemoryDomain）显式注入。
"""

from __future__ import annotations

from sylanne_alpha.v2core.contracts import (
    BeatContext,
    Intent,
    Phase,
)
from sylanne_alpha.v2core.domains.memory import MemoryDomain


class RecallCapability:
    """召回能力：DELIBERATE 拍按亲密度门控召回记忆。"""

    name = "recall"
    phases = (Phase.DELIBERATE,)

    def __init__(self, *, limit: int = 3, priority: float = 0.4) -> None:
        # P1 修复：能力 agent 全局无状态、不构造期注入单会话领域；每轮经 ctx.domain() 取域。
        self._limit = limit
        self._priority = priority

    def deliberate(self, ctx: BeatContext) -> Intent | None:
        memory: MemoryDomain | None = ctx.domain("memory")
        if memory is None:
            return None
        # 关系够亲密才主动翻记忆（门控由领域 agent 按人格判定）。
        # #29：叠加学到的 memory.intimacy_threshold 进化偏置（更主动 → 更早愿意翻记忆）。
        if not memory.intimacy_ok(ctx.body, bias=ctx.evo_bias("memory", "intimacy_threshold")):
            return None
        text = ctx.text
        if not text:
            return None
        # 躯体标记偏置（连续，非二元门）：结疤/拉伤深时回避翻旧事——
        # approach_recall 很负则本轮不召回；轻负则收窄召回条数。
        limit = self._limit
        bias = ctx.scratch.get("somatic_bias")
        approach = float(getattr(bias, "approach_recall", 0.5) or 0.0)
        if approach <= -0.5:
            return None
        if approach < 0.0:
            limit = max(1, self._limit - 1)
        results = memory.recall(text, warmth=ctx.current_warmth, limit=limit)
        if not results:
            return None
        # 消费者：ReconsolidationCapability（重固化窗口）+ ExpressionCapability（has_recall）
        ctx.scratch["recalled_deliberate"] = results
        return Intent(
            source=self.name,
            payload={"recalled": results},
            priority=self._priority,
        )


__all__ = ["RecallCapability"]
