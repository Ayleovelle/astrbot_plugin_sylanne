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
        # 键=记忆条目身份，优先 item.id（MEM-09 起）；text 兜底解析历史存档遗留的
        # 旧 text 键（迁移期只读兼容，见 reconsolidate()/_overlay_lookup()）。
        self._reconsolidation_overlay: dict[str, dict[str, Any]] = {}

    # ---- 读接口（热路径，内联同步，不调 LLM）----

    def recall(
        self, text: str, *, warmth: float = 0.0, limit: int = 3,
        query_embedding: list[float] | None = None,
        history_present: bool = True,
    ) -> list[dict[str, Any]]:
        """召回相关记忆，返回纯数据 dict 列表（不泄露 MemoryResult 内部对象）。

        P0-6 修复：①补情绪键 temperature/emotional_weight（MemoryResult 真有这两字段），
        重固化才有真实情绪基线算 narrative_pe，不再拿 0.0 充数 spam 锚点。②读侧接通影子层——
        每条查 overlay 命中则附 overlay_warmth（召回呈现/format_injection 用叠加值），
        original 字段照旧（红线2 不破）。

        MEM-09：新增 "id" 键（取自 MemoryResult.source_obj.id，底层 MemoryItem/GraphNode
        的稳定身份）；overlay 命中改为优先按 id 查，text 只作旧档兜底（见
        _overlay_lookup）。source_obj 缺失（如测试桩）时 id 退化为空串，行为等同
        MEM-09 之前（纯 text 键）。
        """
        if not text:
            return []
        results = self._ms.recall(
            text, query_embedding, warmth, limit=limit,
            history_present=history_present,
        )
        out: list[dict[str, Any]] = []
        for r in results:
            # 单一 v2core choke 点：情感旁路（ACTIVATION 模式 _apply_emotion_bypass）
            # 补回的 rel≈0 强情绪项若同时语义几乎不相关（relevance<0.15），在这里落地前
            # 丢弃——防止高 warmth 场景下每轮都被无关往事打断话题。不动 emotion_bypass
            # 本身（legacy 走 MemorySystem.recall 直连，不经本方法，行为不变）。
            if (
                getattr(r, "recall_reason", "") == "emotion_bypass"
                and getattr(r, "relevance", 0.0) < 0.15
            ):
                continue
            item_text = getattr(r, "text", str(r))
            item_id = str(getattr(getattr(r, "source_obj", None), "id", "") or "")
            # 情绪键：MemoryResult.temperature（透传）+ emotional_weight；取不到给 None（不充 0）
            temperature = getattr(r, "temperature", None)
            row: dict[str, Any] = {
                "text": item_text,
                "id": item_id,
                "confidence": getattr(r, "confidence", "clear"),
                "layer": getattr(r, "layer", ""),
                "activation": getattr(r, "activation", 0.0),
                "temperature": float(temperature) if isinstance(temperature, (int, float)) else None,
                "emotional_weight": float(getattr(r, "emotional_weight", 0.5)),
            }
            # 读侧接通影子层：优先按 id 查，miss 再退回旧 text 键（兼容 MEM-09 前存档）
            ov = self._overlay_lookup(item_id, item_text)
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
    # MEM-09：单次重固化的漂移幅度钳位（|Δoverlay_warmth| <= 此值）。retrieval-time
    # plasticity 本身是特性（Nader 2000）保留，但旧公式 (1-rate)*old+rate*current 在
    # old/current 反差大时单次漂移可达 ~0.6（[-1,1] 效价域的一大截），钳位后温度漂移
    # 变成小步累积而非一次到位，行为仍然"越回忆越贴近当下心境"，只是更缓。
    _RECON_DRIFT_CAP = 0.1

    def _overlay_lookup(self, primary_key: str, fallback_key: str) -> dict[str, Any] | None:
        """按 primary_key（item.id）查影子层，未命中且 fallback_key（text）不同时
        退回 fallback_key——兼容 MEM-09 之前纯 text 键的历史存档。两键都空时返回 None。
        """
        primary_key = str(primary_key or "")
        fallback_key = str(fallback_key or "")
        if primary_key:
            ov = self._reconsolidation_overlay.get(primary_key)
            if ov is not None:
                return ov
        if fallback_key and fallback_key != primary_key:
            return self._reconsolidation_overlay.get(fallback_key)
        return None

    def reconsolidate(self, recalled: list[dict[str, Any]], *, current_warmth: float,
                      narrative_pe: float, pe_gate: float) -> int:
        """PE 门控的记忆重固化（Nader 2000 / Sinclair&Barense 2018：提取即可改写窗口，
        改写由预测误差门控）。**只写影子层，original_text 一字不动（红线2）**。

        narrative_pe < pe_gate → 符合预期，不改。
        narrative_pe >= pe_gate → 被召回条目的情绪温度向当下 warmth 漂移（落 overlay，
          单次漂移幅度钳位 _RECON_DRIFT_CAP），rewrite_count++（封顶 _RECON_CAP）。
          召回呈现时由 overlay_warmth 叠加，迁移/回滚永远能回到原文+原始情绪。
          返回本次改写的条目数。

        基线修正（Fable 版）：条目无情绪温度（temperature/warmth 均为 None）时，
        初始 overlay 基线取 current_warmth（首次改写=向当下温度靠拢的中性起步），
        绝不拿 0.0 充数——0.0 在 [-1,1] 效价域是一个有语义的值。

        MEM-09：存储键优先 item.id（recalled dict 的 "id"），旧 text 键仅用于兜底
        解析 MEM-09 之前持久化的影子条目；一旦被 id 命中的旧 text 条目会原地迁移到
        id 键下（同条目不留两份），新写入一律落 id 键（无 id 时退回 text，与之前
        行为一致，兼容测试桩等不带底层对象引用的调用方）。
        """
        if narrative_pe < pe_gate or not recalled:
            return 0
        n = 0
        for r in recalled:
            item_id = str(r.get("id") or "").strip()
            text_key = str(r.get("text") or "")
            key = item_id or text_key
            if not key:
                continue
            ov = self._overlay_lookup(item_id, text_key)
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
            target = ((1 - self._RECON_RATE) * ov["overlay_warmth"]
                      + self._RECON_RATE * float(current_warmth))
            delta = max(-self._RECON_DRIFT_CAP,
                        min(self._RECON_DRIFT_CAP, target - ov["overlay_warmth"]))
            ov["overlay_warmth"] = ov["overlay_warmth"] + delta
            ov["rewrite_count"] += 1
            ov["last_pe"] = float(narrative_pe)
            # LRU 语义：重插到末尾=最近触碰；超限淘汰最旧（dict 保插入序）。
            # 同时清掉旧 text 键（若与新 key 不同）——把命中的旧档条目迁移到 id 键，
            # 避免同一条目在影子层同时留下 id 键与孤立的旧 text 键两份。
            self._reconsolidation_overlay.pop(key, None)
            if text_key != key:
                self._reconsolidation_overlay.pop(text_key, None)
            self._reconsolidation_overlay[key] = ov
            while len(self._reconsolidation_overlay) > self._OVERLAY_MAXLEN:
                oldest = next(iter(self._reconsolidation_overlay))
                self._reconsolidation_overlay.pop(oldest, None)
            n += 1
        return n

    def overlay_for(self, key: str, *, text_fallback: str | None = None) -> dict[str, Any] | None:
        """取某条目的重固化影子（召回呈现时叠加；无则 None=用原文原始情绪）。

        MEM-09：`key` 应传 item.id；`text_fallback` 可选传原文，未命中 id 时兜底按
        text 查（兼容旧档）。调用方只传单一 key（历史调用惯例）时行为等同直查该键。
        """
        ov = self._reconsolidation_overlay.get(str(key))
        if ov is not None:
            return ov
        if text_fallback is not None and text_fallback != key:
            return self._reconsolidation_overlay.get(str(text_fallback))
        return None

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
