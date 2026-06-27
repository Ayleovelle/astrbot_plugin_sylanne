"""MemoryDomain —— 记忆领域 agent（v2core 第一个绞入的领域）。

设计纪律：
- 独占记忆状态（三层 MemorySystem），是其唯一写者。别的 agent 只能通过本类接口读写。
- 复用已加固的 MemorySystem（ACT-R 激活核 / 扩散激活 / 软召回 / 灰度开关全部保留）——
  绞杀式不重造记忆轮子，只把它收进干净的领域边界，斩断旧架构 self._p 穿透。
- to_dict / load_dict 直接委托 MemorySystem 的成熟序列化（存档向前兼容，用户养成的
  记忆不丢——这是迁移红线）。

接口面（供能力 agent 调用，全部不暴露 MemorySystem 内部）：
- recall(text, warmth, limit) → list[dict]   读，热路径，内联同步
- intimacy_ok(snapshot)                       读，亲密度门控判断
- write_summary(...)                          写（仅 EVOLVE 拍经此提交）
- tick_decay()                                写（维护，EVOLVE 拍）
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sylanne_alpha.v2core.contracts import BodySnapshot

if TYPE_CHECKING:
    from sylanne_alpha.memory_system import MemorySystem


class MemoryDomain:
    """记忆领域 agent。包裹一个 MemorySystem 实例，对外只暴露领域接口。"""

    name = "memory"

    # 亲密度召回门控基线（人格函数：感知/关系越深，越早愿意主动翻记忆）
    _INTIMACY_BASE = 0.35

    def __init__(self, memory_system: "MemorySystem") -> None:
        self._ms = memory_system
        # 重固化影子层（红线2：original_text 永不动；改写只落这里，召回时叠加）。
        # 键=记忆条目身份(text 或 id)，值={overlay_warmth, rewrite_count, last_pe}。
        self._reconsolidation_overlay: dict[str, dict[str, Any]] = {}

    # ---- 读接口（热路径，内联同步，不调 LLM）----

    def recall(
        self, text: str, *, warmth: float = 0.0, limit: int = 3,
        query_embedding: list[float] | None = None,
    ) -> list[dict[str, Any]]:
        """召回相关记忆，返回纯数据 dict 列表（不泄露 MemoryResult 内部对象）。

        P0-6 修复：①补情绪键 temperature/emotional_weight（MemoryResult 真有这两字段），
        重固化才有真实情绪基线算 narrative_pe，不再拿 0.0 充数 spam 锚点。②读侧接通影子层——
        每条查 overlay_for(key) 命中则附 overlay_warmth（召回呈现/format_injection 用叠加值），
        original 字段照旧（红线2 不破）。
        """
        if not text:
            return []
        results = self._ms.recall(text, query_embedding, warmth, limit=limit)
        out: list[dict[str, Any]] = []
        for r in results:
            item_text = getattr(r, "text", str(r))
            # 情绪键：MemoryResult.temperature（透传）+ emotional_weight；取不到给 None（不充 0）
            temperature = getattr(r, "temperature", None)
            row: dict[str, Any] = {
                "text": item_text,
                "confidence": getattr(r, "confidence", "clear"),
                "layer": getattr(r, "layer", ""),
                "activation": getattr(r, "activation", 0.0),
                "temperature": float(temperature) if isinstance(temperature, (int, float)) else None,
                "emotional_weight": float(getattr(r, "emotional_weight", 0.5)),
            }
            # 读侧接通影子层：命中则附 overlay_warmth（呈现叠加值）
            ov = self._reconsolidation_overlay.get(item_text)
            if ov is not None:
                row["overlay_warmth"] = float(ov.get("overlay_warmth", 0.0))
            out.append(row)
        return out

    def intimacy_ok(self, body: BodySnapshot, *, bias: float = 0.0) -> bool:
        """关系是否够亲密到主动翻记忆（阈值=人格函数基线 + 进化偏置）。

        #29：bias = reflex/反思 学到的 memory.intimacy_threshold 偏置（叠加在基线上，
        调用方经 ctx.evo_bias 取并已二次钳位 ±0.15）。负偏置=降门槛=更早愿意翻记忆
        （更主动）；缺省 0.0 = 纯人格基线（向后兼容旧调用与测试）。
        """
        return body.intimacy_gravity >= self._INTIMACY_BASE + bias

    def format_injection(self, results: list[Any], max_items: int = 3) -> str:
        """委托 MemorySystem 的分级注入格式化（clear/vague/tot 措辞）。"""
        return self._ms.format_recall_injection(results, max_items=max_items)

    def recall_prompt_line(self, recalled: list[dict[str, Any]], *, max_items: int = 2) -> str:
        """从 PERCEPT 召回 dict 列表压成心象一行（零-LLM，不泄露内部结构）。"""
        if not recalled:
            return ""
        parts: list[str] = []
        for r in recalled[:max_items]:
            if not isinstance(r, dict):
                continue
            t = str(r.get("text") or "").strip()
            if not t:
                continue
            conf = str(r.get("confidence") or "clear")
            if conf == "tot":
                parts.append("舌尖：好像有件和你有关的事一时记不清")
            elif conf == "vague":
                parts.append(f"依稀：{t[:50]}")
            else:
                parts.append(t[:80])
            ov = r.get("overlay_warmth")
            if ov is not None:
                try:
                    ow = float(ov)
                    if ow > 0.2:
                        parts[-1] += "（带着暖意）"
                    elif ow < -0.2:
                        parts[-1] += "（有点沉）"
                except (TypeError, ValueError):
                    pass
        if not parts:
            return ""
        return "记忆线索:" + "；".join(parts)

    # ---- 写接口（仅 EVOLVE 拍 / 维护循环经此，单一写者）----

    def write_summary(self, text: str, **kw: Any) -> Any:
        return self._ms.write_summary(text, **kw)

    def tick_decay(self) -> None:
        """记忆衰减维护（必跑，不受亲密度门控）。"""
        self._ms.tick_decay()

    # ---- 重固化（红线2：影子字段方案，存档无损）----

    _RECON_RATE = 0.3            # 情绪温度向当下漂移的比例（Nader 2000 重固化窗口）
    _RECON_CAP = 20              # 单条最多重固化次数（呼应旧 MemoryItem.rewrite_count 上限）
    _OVERLAY_MAXLEN = 256        # 影子层条目上限（LRU 淘汰最旧；防无界膨胀+永久落盘垃圾）

    def reconsolidate(self, recalled: list[dict[str, Any]], *, current_warmth: float,
                      narrative_pe: float, pe_gate: float) -> int:
        """PE 门控的记忆重固化（Nader 2000 / Sinclair&Barense 2018：提取即可改写窗口，
        改写由预测误差门控）。**只写影子层，original_text 一字不动（红线2）**。

        narrative_pe < pe_gate → 符合预期，不改。
        narrative_pe >= pe_gate → 被召回条目的情绪温度向当下 warmth 漂移（落 overlay），
          rewrite_count++（封顶 _RECON_CAP）。召回呈现时由 overlay_warmth 叠加，迁移/回滚
          永远能回到原文+原始情绪。返回本次改写的条目数。

        基线修正（Fable 版）：条目无情绪温度（temperature/warmth 均为 None）时，
        初始 overlay 基线取 current_warmth（首次改写=向当下温度靠拢的中性起步），
        绝不拿 0.0 充数——0.0 在 [-1,1] 效价域是一个有语义的值。
        """
        if narrative_pe < pe_gate or not recalled:
            return 0
        n = 0
        for r in recalled:
            key = str(r.get("text") or r.get("id") or "")
            if not key:
                continue
            ov = self._reconsolidation_overlay.get(key)
            if ov is None:
                base_raw = r.get("temperature")
                if base_raw is None:
                    base_raw = r.get("warmth")
                try:
                    base = float(base_raw) if base_raw is not None else float(current_warmth)
                except (TypeError, ValueError):
                    base = float(current_warmth)
                ov = {"overlay_warmth": base, "rewrite_count": 0, "last_pe": 0.0}
            if ov["rewrite_count"] >= self._RECON_CAP:
                continue
            ov["overlay_warmth"] = ((1 - self._RECON_RATE) * ov["overlay_warmth"]
                                    + self._RECON_RATE * float(current_warmth))
            ov["rewrite_count"] += 1
            ov["last_pe"] = float(narrative_pe)
            # LRU 语义：重插到末尾=最近触碰；超限淘汰最旧（dict 保插入序）
            self._reconsolidation_overlay.pop(key, None)
            self._reconsolidation_overlay[key] = ov
            while len(self._reconsolidation_overlay) > self._OVERLAY_MAXLEN:
                oldest = next(iter(self._reconsolidation_overlay))
                self._reconsolidation_overlay.pop(oldest, None)
            n += 1
        return n

    def overlay_for(self, key: str) -> dict[str, Any] | None:
        """取某条目的重固化影子（召回呈现时叠加；无则 None=用原文原始情绪）。"""
        return self._reconsolidation_overlay.get(str(key))

    # ---- 影子层独立持久化（P0-7：域状态落盘，但 memory 域只存 overlay）----
    # MemorySystem 自有持久化键（sylanne_memory_state:*），域状态总键不重复存它（双写冲突），
    # 只把重固化影子层 _reconsolidation_overlay 存进域总键。to_dict 仍委托底层供 oracle 对照。

    def overlay_to_dict(self) -> dict[str, Any]:
        """仅导出重固化影子层（供 P0-7 域状态总键存储；不含底层 MemorySystem）。"""
        return {"_reconsolidation_overlay": dict(self._reconsolidation_overlay)}

    def overlay_load_dict(self, data: dict[str, Any]) -> None:
        """仅恢复重固化影子层（容缺，旧档无此键=空起步）。"""
        if not data:
            return
        ov = data.get("_reconsolidation_overlay")
        if isinstance(ov, dict):
            self._reconsolidation_overlay = {
                str(k): dict(v) for k, v in ov.items() if isinstance(v, dict)
            }

    # ---- 持久化（委托成熟序列化，存档向前兼容）----

    def to_dict(self) -> dict[str, Any]:
        d = self._ms.to_dict()
        # 影子层单独存（与 original 正交；旧档无此键=空起步，铁律④）
        if self._reconsolidation_overlay:
            d = dict(d)
            d["_reconsolidation_overlay"] = self._reconsolidation_overlay
        return d

    def load_dict(self, data: dict[str, Any]) -> None:
        if not data:
            return
        ov = data.get("_reconsolidation_overlay")
        if isinstance(ov, dict):
            self._reconsolidation_overlay = {
                str(k): dict(v) for k, v in ov.items() if isinstance(v, dict)
            }
        # original 记忆走成熟反序列化（影子键它不认，无害）
        self._ms.from_dict(data)

    # ---- 逃生舱：迁移期偶尔需要底层引用（迁移完成后应清零）----

    @property
    def system(self) -> "MemorySystem":
        return self._ms


__all__ = ["MemoryDomain"]
