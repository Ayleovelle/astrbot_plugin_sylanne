"""v2core BodyPort（canonical 形态 + from_host 可跑形态）—— 把 SylanneHost 接成 BodyPort 契约。

为何另起文件、不动 body_port.py：
- body_port.py 的 KernelBodyPort 直接持**裸 kernel** 调 kernel.tick()——skeptic P2 证为真 bug：
  落盘是 host 职责（host._tick 后 _pending_snapshot→_maybe_flush），绕过 host 直调 kernel.tick
  只算不存，人格漂移永不落盘，进程一关全丢 → 破铁律4。
- 本文件的 CanonicalKernelBodyPort **持 host（非裸 kernel）**，tick 走 host.on_request /
  host.on_response，落盘链路正常。

两个构造入口：
- from_host(host, session_key)：**M0/Tier1 可跑路径**。直接包一个已有 host（与当前插件一样
  驱动 kernel/host），不依赖 canonical shared()——绕开 vendored 尚无 shared() 的阻塞，
  让 v2core 整轮现在就能在实机/测试里跑通。
- body_port_for_session(...)：D0 目标路径，经 canonical SylanneEngine.shared() 取进程级共享
  引擎。vendored 升级到 canonical 后启用；当前 shared() 缺失会抛清晰错误（预期，前置依赖）。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
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


# 一轮双 tick（§3.5）：request tick 吃用户消息，response tick 吃 LLM 回复 + 反馈。
_RESPONSE_FLAGS: frozenset[str] = frozenset({"response", "chat_response"})


def _is_response_phase(event: dict[str, Any]) -> bool:
    """判定本次 tick 是否 response 拍（否则 request 拍）。缺省按 request。

    S7 契约：response 拍的 event 必须显式带 phase="response"（或 flags 含 response）。
    调用方（SelfCore.turn）有义务正确标注；标错会把 LLM 回复当用户请求喂进 request 流水线。
    """
    if not isinstance(event, dict):
        return False
    if str(event.get("phase") or "") == "response":
        return True
    flags = event.get("flags") or ()
    try:
        return any(str(f) in _RESPONSE_FLAGS for f in flags)
    except TypeError:
        return False

# <!-- CHUNK1 -->


async def _resolve_shared(
    data_dir: str | Path,
    llm: Callable[[str, str], Awaitable[str]],
) -> Any:
    """取 canonical 权威门面 SylanneEngine.shared(data_dir, llm)；缺失 → 清晰错误。

    vendored 已同步到 canonical main（含 async shared()）。shared() 是协程，必须 await——
    否则返回未 await 的协程对象，后续 engine.status/start() 会抛 AttributeError（旧 bug）。
    """
    from sylanne_alpha._engine.sylanne_core import SylanneEngine

    shared = getattr(SylanneEngine, "shared", None)
    if shared is None or not callable(shared):
        raise RuntimeError(
            "SylanneEngine.shared() 缺失：当前 vendored _engine/sylanne_core 落后于 canonical main。\n"
            "v2core BodyPort 的 canonical 路径需 shared()。\n"
            "# 临时可跑路径：用 CanonicalKernelBodyPort.from_host(host, session_key) 直接包现有 host。"
        )
    return await shared(data_dir, llm)


async def body_port_for_session(
    session_key: str,
    *,
    data_dir: str | Path,
    llm: Callable[[str, str], Awaitable[str]],
) -> CanonicalKernelBodyPort:
    """D0 目标路径：经 canonical shared() 取共享引擎 → 下探 host → 包成 BodyPort。

    粒度（铁律§1.1）：引擎进程级共享（shared()），host 会话级，BodyPort 每会话。
    vendored 升级前本函数必抛（_resolve_shared 报错）——预期，用 from_host 跑。
    """
    engine = await _resolve_shared(data_dir, llm)
    if getattr(engine, "status", None) in (None, "init", "closed"):
        await engine.start()
    host = engine._get_or_create_host(session_key)
    return CanonicalKernelBodyPort(host, session_key)


class CanonicalKernelBodyPort:
    """把 SylanneHost 适配为 BodyPort（持 host，非裸 kernel——P2 修复）。

    三动词（铁律3，只经此碰 SDK）：
    - observe()  只读：host.diagnostics() → 类型化 BodySnapshot，无副作用。
    - tick()     唯一写：走 host.on_request / on_response（含落盘链）；一律 return observe()（P14）。
    - snapshot() 只读：host.snapshot() 导出可持久化状态。

    ⚠️ 三个坑（用错会静默丢状态/串话）：
    1. event-loop affine：host 绑创建它的事件循环，跨循环复用 → 锁失效/RuntimeError。
       后台线程起新循环时别共享同一 port 实例。
    2. 禁 async with engine：__aexit__ → shutdown() 会 flush 并清空所有会话。shared() 是
       进程级单例，永远经工厂取用，绝不上下文管理；优雅停机走 engine.shutdown() 一次性收口。
    3. 无 atexit flush：host 按阈值/显式 flush 落盘，无 atexit 兜底；进程被 kill 未停机 →
       最近不足阈值的 pending snapshot 丢。落盘持久性是编排层职责。

    ⚠️ S5 串行义务（最关键）：BodyPort.tick **只能在该会话 SessionLocks.turn 持有下调用**。
    v2 路径绕过 engine 自带 per-session 锁，turn 锁是同会话唯一串行点；否则并发双 tick 撕裂 kernel。
    """

    def __init__(self, host: Any, session_key: str) -> None:
        self._host = host          # 持 host（非裸 kernel）：落盘链路在 host 上
        self._session_key = session_key

    @classmethod
    def from_host(cls, host: Any, session_key: str) -> CanonicalKernelBodyPort:
        """可跑路径：直接包一个已有 host（当前插件已在用的 SylanneHost）。

        绕开 canonical shared() 阻塞 —— 让 v2core 整轮现在就能在实机/测试跑通。
        host 由调用方（插件或测试 harness）用现成的 runtime/data_dir 造好传入；
        data_dir 连续性=body 漂移史无损的保证（host.__post_init__ 经 runtime.load 从文件恢复）。
        """
        return cls(host, session_key)

    def observe(self) -> BodySnapshot:
        """取当前 body 的只读类型化快照（不推进计算）。

        canonical PE（surprise/precision）不在 surface dict 里——它在 kernel.computation 上。
        本方法是【唯一允许碰 SDK 内部的边界处】（红线：agent 禁止下探，适配器可投影）。
        在此读出经 extras 注入 snapshot_from_surface，全系统四模块从 BodySnapshot 派生不重算。
        """
        surface = self._host.diagnostics()
        return snapshot_from_surface(surface, self._session_key, extras=self._canonical_pe())

    def _canonical_pe(self) -> dict[str, Any]:
        """从 kernel.computation 读唯一一份 surprise/precision（§1.3 单一来源）。防御式判空降级。"""
        ext: dict[str, Any] = {}
        try:
            comp = getattr(self._host.kernel, "computation", None)
            if comp is not None:
                ls = getattr(comp, "_last_surprise", None)
                if ls is not None:
                    ext["surprise"] = float(ls)
                gate = getattr(comp, "_gate", None)
                if gate is not None:
                    prec = getattr(gate, "precision", None)
                    if prec is not None:
                        ext["precision"] = float(prec)
                    ms = getattr(gate, "mean_surprise", None)
                    if ms is not None:
                        ext["mean_surprise"] = float(ms)
        except Exception:
            pass  # PE 取不到 → snapshot_from_surface 降级中性值（fast-path 安全）
        return ext

    def tick(
        self, event: dict[str, Any], assessment: dict[str, Any] | None = None
    ) -> BodySnapshot:
        """喂事件推进不可逆计算，返回推进后新快照。

        路由（§3.5 双 tick）：response 拍走 host.on_response（反馈进 response tick，P5）；
        否则 request 拍走 host.on_request（assessment 仅 request 消费）。两者内部触发
        host CoW snapshot + _maybe_flush，落盘正常（P2）。P14：一律 return observe()。
        S5：调用方须在 SessionLocks.turn 持有下调本方法。
        """
        if _is_response_phase(event):
            self._host.on_response(event)
        else:
            self._host.on_request(event, assessment=assessment)
        return self.observe()

    def snapshot(self) -> dict[str, Any]:
        """导出可持久化的完整内部状态（只读，存档无损/SHADOW 用）。"""
        return self._host.snapshot()

    def learn(self, outcome: str, *, actual_expressed: bool | None = None,
              quality_signal: str | None = None) -> None:
        """真实用户反应反馈占位（L1 漂移已不经此）——canonical 迁移后语义变更。

        ⚠️ 迁移说明（2026-06-14，核查任务 wdjxyayf1）：旧实现经已退役的 `feedback_quality`
        后门把 expression_fired/sustained_silence/dialogue_quality_* 喂 DRIFT_SIGNALS。
        vendored 整树同步到 canonical main 后 `feedback_quality` 不存在了。漂移现在的唯一
        发生地是 `process` 内部（kernel.tick 末尾 _drift_embodiment），由三条信号驱动：
          - expression_fired ← process 自派生 result["should_express"]（每轮 request 拍自动）
          - dialogue_quality_high/low ← agent 经 event.values["dialogue_quality"] 数值注入
            （turn_runner 自评 → rt["pending_quality"] → 下轮 request tick；见 turn_runner/integration）
          - sustained_silence ← canonical 通道当前不可达（route 恒 resonance），记 SDK backlog
            （docs/SDK-BACKLOG-drift-gaps.md 缺口1），agent 层不 hack。
        故 learn() 不再驱动任何 embodiment 漂移。

        本方法仅保留为【真实用户反应】反馈入口：将来"用户是否接受了这条回复"可判定后
        （如下一轮用户反应/显式反馈），在此调 comp.feedback(reaction, actual_expressed=…)
        驱动 expression_policy 的 REINFORCE（off-policy 修正，T2 的 actual_expressed 届时生效）。
        本期桥内无此判定源 → 不调。绝不拿 expression_fired 等表达结果 outcome 喂 feedback()。
        任一不可用静默降级（防御式，绝不阻断 turn）。
        """
        _ = (outcome, actual_expressed, quality_signal)  # 预留参数，待真实反应判定源接入



__all__ = ["body_port_for_session", "CanonicalKernelBodyPort", "snapshot_from_surface"]

