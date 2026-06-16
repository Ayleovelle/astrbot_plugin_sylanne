"""ReconsolidationCapability —— 活的记忆：PE 门控的重固化（架构 §3.3 Phase E）。

EVOLVE 拍：仅当本轮发生召回 且 narrative_pe 超阈，经 MemoryDomain.reconsolidate 改写被
召回条目的情绪温度——**走影子字段，original_text 不动（红线2，存档无损）**。

理论：Nader et al. 2000（提取即进入不稳定窗口，可被改写）；Sinclair & Barense 2018
（改写由预测误差门控——与 A1 同源）。这让"她回忆时记忆会变"——人与数据库的根本区别。

无独占态，经 ctx.domain() 取域。narrative_pe 由 NarrativeSelfDomain 算（派生不重算 SDK）。
"""

from __future__ import annotations

from sylanne_alpha.v2core.contracts import BeatContext, Phase


class ReconsolidationCapability:
    """重固化能力：EVOLVE 拍据 narrative_pe 门控改写召回记忆的情绪（影子字段）。无独占态。"""

    name = "reconsolidation"
    phases = (Phase.EVOLVE,)

    def evolve(self, ctx: BeatContext) -> None:
        recalled = ctx.scratch.get("recalled")
        if not recalled:
            return                      # 本轮没召回 → 无重固化窗口
        memory = ctx.domain("memory")
        narrative = ctx.domain("narrative")
        if memory is None or not hasattr(memory, "reconsolidate"):
            return

        # narrative_pe：召回记忆情绪 vs 当下情绪（NarrativeSelfDomain 算；缺域时用 surprise 代理）
        body = ctx.body
        if narrative is not None and hasattr(narrative, "narrative_pe"):
            # P0-6 修复：取召回集的真实平均情绪当"被回忆起的情绪"。无任何有效情绪基线 → None，
            # 直接跳过（绝不拿 0.0 充数——否则暖聊+召回每轮 |0−warmth| 恒超阈，spam 重固化+锚点）。
            recalled_emotion = _mean_recalled_warmth(recalled)
            if recalled_emotion is None:
                return                      # 无情绪基线 → 不算 npe、不重固化、不登记锚点
            npe = float(narrative.narrative_pe(recalled_emotion, body))
            pe_gate = float(getattr(narrative, "reconsolidation_threshold", 0.5))
        else:
            npe = float(body.surprise)
            pe_gate = 0.5
        ctx.scratch["narrative_pe"] = npe   # 供 NarrativeSelfDomain.ingest 登记锚点
        # 锚点注记（review F4：接活死读）：高失配时刻"是关于什么的"——取首条召回
        # 记忆的文本片段。没有它，锚点只有数字没有线索（自传索引失去可回看性）。
        # NarrativeSelfDomain.ingest 读 scratch["narrative_note"]（截 40 字）收进 Anchor.note。
        first = recalled[0] if isinstance(recalled[0], dict) else {}
        note = str(first.get("text", "") or "").strip()
        if note:
            ctx.scratch["narrative_note"] = note[:40]

        n = memory.reconsolidate(
            list(recalled), current_warmth=float(body.warmth),
            narrative_pe=npe, pe_gate=pe_gate,
        )
        if n:
            ctx.scratch["reconsolidated_count"] = n   # 消费者：实弹测试断言 + 调试


def _mean_recalled_warmth(recalled: list) -> float | None:
    """召回集的平均情绪温度。P0-6：无任何有效值返回 None（不拿 0.0 充数）。"""
    vals = []
    for r in recalled:
        if isinstance(r, dict):
            v = r.get("temperature", r.get("warmth"))
            if v is not None:
                try:
                    vals.append(float(v))
                except (TypeError, ValueError):
                    pass
    return sum(vals) / len(vals) if vals else None


__all__ = ["ReconsolidationCapability"]
