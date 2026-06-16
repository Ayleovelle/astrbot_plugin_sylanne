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

from sylanne_alpha.v2core.body_port import snapshot_from_surface
from sylanne_alpha.v2core.contracts import BodySnapshot

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



__all__ = ["body_port_for_session", "CanonicalKernelBodyPort"]

