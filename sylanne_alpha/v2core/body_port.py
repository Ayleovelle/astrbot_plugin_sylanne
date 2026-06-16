"""v2core BodyPort 实接 —— 把 SDK AlphaKernel 包成 BodyPort 契约。

这是绞杀式重写的第一根接线：新骨架通过本适配器读真实 Body，而不直接碰 kernel 内部。
SDK 一行不改（红线：SDK 是护城河，原样保留），只在外面套一层契约转换。

职责：
- observe()：调 kernel.surface()，把字符串键的裸 dict 提炼成类型化 BodySnapshot。
- tick()：喂事件推进不可逆计算，返回新快照。
- snapshot()：透传 kernel 的持久化导出。

提炼采用防御式读取（多路径 + 缺省）：SDK surface 的嵌套结构在不同 profile/版本下
略有差异，新骨架不该因为某个键缺失而崩——这正是旧架构 hp.get().get().get() 脆弱
穿透的反面：脆弱读取收敛到这一处适配器，BodySnapshot 之后是干净类型。
"""

from __future__ import annotations

from typing import Any

from sylanne_alpha.v2core.contracts import BodySnapshot


def _f(d: Any, *path: str, default: float = 0.0) -> float:
    """沿 path 安全下钻取 float，任何一层缺失/类型不符 → default。"""
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    try:
        return float(cur)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _ext_f(ext: dict, key: str, default: float) -> float:
    """extras 容错读取（性质测试抓出的洞：裸 float() 遇类型垃圾炸 ValueError，
    破 total 契约）。None/缺失/不可转 → default；0.0 是合法值，不被 `or` 偷换。"""
    v = ext.get(key)
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def snapshot_from_surface(
    surface: dict[str, Any], session_key: str,
    extras: dict[str, Any] | None = None,
) -> BodySnapshot:
    """把 kernel.surface() 的 dict 提炼成类型化 BodySnapshot（纯函数，便于测试）。

    提炼路径对照旧架构 MemoryAgent 读法：
    - warmth/repair_pressure ← host_payload.affect_dynamics.computation_emotion.*
    - tension               ← host_payload.integrated_self.state_index.* (risk/boundary 近似)
    - intimacy_gravity      ← host_payload.personality.traits.intimacy_gravity
    - personality(traits)   ← host_payload.personality.traits（整块只读暴露）

    2.1.0 认知扩展（Phase A）：躯体标记/叙事量从真实路径 surface["body"].* 投影；
    canonical PE（surprise/precision/mean_surprise）不在 surface 里——它在
    kernel.computation 上，由 body_port_v2 的 observe() 经 extras 注入（唯一边界处取，
    禁止 agent 下探 kernel）。extras 缺省时降级为中性值（fast-path 判空）。
    """
    hp = surface.get("host_payload") if isinstance(surface, dict) else None
    hp = hp if isinstance(hp, dict) else {}
    ext = extras if isinstance(extras, dict) else {}
    body = surface.get("body") if isinstance(surface, dict) else None
    body = body if isinstance(body, dict) else {}

    emo = hp.get("affect_dynamics", {})
    emo = emo.get("computation_emotion", {}) if isinstance(emo, dict) else {}

    persona = hp.get("personality", {})
    traits = persona.get("traits", {}) if isinstance(persona, dict) else {}
    traits = traits if isinstance(traits, dict) else {}
    # 归一化为 dict[str, float]
    clean_traits: dict[str, float] = {}
    for k, v in traits.items():
        try:
            clean_traits[str(k)] = float(v)
        except (TypeError, ValueError):
            continue

    state_index = hp.get("integrated_self", {})
    state_index = state_index.get("state_index", {}) if isinstance(state_index, dict) else {}

    warmth = _f(emo, "warmth")
    # P0(实机修复 2026-06-12)：真实温度在 body.temperature.warmth（[0,1] 中性≈0.5），
    # computation_emotion.warmth 是近零内部增量（实测 0.005，害得整个情绪/评价层饿死）。
    # 优先读真实躯体温度并映射成 [-1,1] 效价（0=中性）；旧路径仅在 body 缺该字段时兜底。
    body_temp = body.get("temperature") if isinstance(body, dict) else None
    if isinstance(body_temp, dict) and "warmth" in body_temp:
        try:
            raw_w = float(body_temp["warmth"])
            warmth = (raw_w - 0.5) * 2.0          # [0,1] 温度 → [-1,1] 效价
        except (TypeError, ValueError):
            pass
    repair_pressure = _f(emo, "repair_pressure")
    if repair_pressure == 0.0:
        repair_pressure = _f(state_index, "repair_pressure")
    # body 真实路径优先：需求层 need_repair / 伤口 repair（旧路径兜底）
    body_rp = max(_f(body, "needs", "need_repair"), _f(body, "wound", "repair"),
                  _f(body, "temperature", "repair_heat"))
    if body_rp > 0.0:
        repair_pressure = body_rp
    # tension 近似：用 risk 与 boundary_need 取较大（无专门 tension 字段时）
    tension = _f(emo, "tension")
    if tension == 0.0:
        tension = max(_f(state_index, "risk"), _f(state_index, "boundary_need"))
    # body 真实路径优先：脉搏拉伸 / 免疫边界压力（旧路径兜底）
    body_tn = max(_f(body, "pulse", "strain"), _f(body, "immunity", "boundary_pressure"))
    if body_tn > 0.0:
        tension = body_tn
    intimacy = clean_traits.get("intimacy_gravity")
    if intimacy is None:
        intimacy = _f(state_index, "relationship_signal_weight", default=0.5)

    # —— 2.1.0 认知扩展投影（真实路径，见 probe 核实）——
    body_cpl = hp.get("affect_dynamics", {})
    body_cpl = body_cpl.get("body_coupling", {}) if isinstance(body_cpl, dict) else {}
    try:
        turns = int(surface.get("turns") or 0)
    except (TypeError, ValueError):   # total 契约：垃圾 surface 不炸（性质测试抓的洞）
        turns = 0
    return BodySnapshot(
        session_key=str(surface.get("session_key") or session_key),
        turns=turns,
        warmth=max(-1.0, min(1.0, warmth)),
        tension=max(0.0, min(1.0, tension)),
        repair_pressure=max(0.0, min(1.0, repair_pressure)),
        intimacy_gravity=max(0.0, min(1.0, float(intimacy))),
        personality=clean_traits,
        # canonical PE（extras 注入；缺省中性，不 clamp 上限——铁律2，只容错降级）
        surprise=_ext_f(ext, "surprise", 0.0),
        mean_surprise=_ext_f(ext, "mean_surprise", 0.5),
        precision=_ext_f(ext, "precision", 0.5),
        # 躯体标记（body.* 真实路径）
        scar=_f(body, "wound", "scar"),
        strain=_f(body, "pulse", "strain"),
        sovereignty=_f(body, "immunity", "sovereignty", default=1.0),
        exhaustion=_f(body, "mortality", "exhaustion"),
        expression_drive=_f(body_cpl, "expression_drive"),
        # 叙事自我
        threshold_drift=_f(body, "nerve", "threshold_drift"),
        epoch=int(_ext_f(ext, "epoch", 0.0)),
        raw=hp,
    )


class KernelBodyPort:
    """把 AlphaKernel 适配为 BodyPort。

    构造时注入 kernel 实例（由调用方/工厂提供，本适配器不负责创建 kernel）。
    """

    def __init__(self, kernel: Any, session_key: str) -> None:
        self._kernel = kernel
        self._session_key = session_key

    def observe(self) -> BodySnapshot:
        surface = self._kernel.surface()
        return snapshot_from_surface(surface, self._session_key)

    def tick(
        self, event: dict[str, Any], assessment: dict[str, Any] | None = None
    ) -> BodySnapshot:
        self._kernel.tick(event, assessment)
        return self.observe()

    def snapshot(self) -> dict[str, Any]:
        return self._kernel.snapshot()


__all__ = ["KernelBodyPort", "snapshot_from_surface"]
