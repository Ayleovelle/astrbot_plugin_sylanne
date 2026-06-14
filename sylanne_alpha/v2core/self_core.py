"""v2core SelfCore —— 三拍相位编排器（Fable 重做版）。

职责（保持小）：能力注册表 + 三拍逐能力调度 + 意图融合。
不持会话状态（会话态在领域 agent / 存储），每会话一个实例只是为了绑定该会话的 BodyPort。

与旧版的差别：
- 三拍拆成独立入口 run_percept / run_deliberate / run_evolve——因为本架构把
  PERCEPT 放在宿主 request 阶段（影响 prompt）、DELIBERATE/EVOLVE 放在 response
  阶段（裁决草稿+学习），两拍不再总是同一时刻发生。
- make_context 统一构造 BeatContext，并把 lexicon 文本信号预读进 scratch["signals"]
  （全内核唯一观测，能力不许自算词典）。
- turn()/run_until_deliberate 保留为单次跑完的便捷入口（测试/compose 场景用）。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sylanne_alpha.v2core.contracts import (
    BeatContext,
    BodyPort,
    Capability,
    Intent,
    Phase,
)
from sylanne_alpha.v2core.lexicon import read_signals

logger = logging.getLogger("astrbot_plugin_sylanne")


class SelfCore:
    """三拍编排器：register 一行加能力，逐拍调度，DELIBERATE 受 budget_ms 约束。"""

    def __init__(self, body: BodyPort, *, default_budget_ms: float = 5.0) -> None:
        self._body = body
        self._default_budget_ms = default_budget_ms
        self._slots: dict[Phase, list[Capability]] = {
            Phase.PERCEPT: [],
            Phase.DELIBERATE: [],
            Phase.EVOLVE: [],
        }

    # ------------------------------------------------------------------
    # 扩展入口：加新能力 = 这一行
    # ------------------------------------------------------------------
    def register(self, capability: Capability) -> None:
        for phase in capability.phases:
            if phase not in self._slots:
                raise ValueError(f"unknown phase {phase!r} from capability {capability.name!r}")
            self._slots[phase].append(capability)
        logger.debug(
            "Sylanne v2 register capability %r → phases %s",
            capability.name, [p.value for p in capability.phases],
        )

    def capabilities(self, phase: Phase | None = None) -> list[Capability]:
        if phase is not None:
            return list(self._slots[phase])
        seen: dict[int, Capability] = {}
        for caps in self._slots.values():
            for c in caps:
                seen[id(c)] = c
        return list(seen.values())

    # ------------------------------------------------------------------
    # 上下文构造 + 三拍入口
    # ------------------------------------------------------------------
    def make_context(
        self, session_key: str, event: Any, text: str, *,
        domains: dict[str, Any] | None = None,
        groups: Any = None,
        budget_ms: float | None = None,
        now: float | None = None,
    ) -> BeatContext:
        """构造一轮 BeatContext：observe body + 预读文本信号 + 落时钟。"""
        body = self._body.observe()
        ctx = BeatContext(
            session_key=session_key,
            event=event,
            body=body,
            text=text,
            current_warmth=body.warmth,
            budget_ms=budget_ms if budget_ms is not None else self._default_budget_ms,
            domains=domains if domains is not None else {},
            groups=groups,
        )
        ctx.scratch["now"] = float(now) if now is not None else time.time()
        # 全内核唯一文本观测（lexicon）：能力一律读它，不自算词典
        ctx.scratch["signals"] = read_signals(text)
        return ctx

    def refresh_body(self, ctx: BeatContext) -> None:
        """重读 body 快照（PERCEPT 与 DELIBERATE 之间隔了宿主 tick 时调用）。

        BeatContext.body 是 frozen dataclass 字段但 ctx 本身可变——直接替换引用。
        """
        ctx.body = self._body.observe()
        ctx.current_warmth = ctx.body.warmth

    def run_percept(self, ctx: BeatContext) -> None:
        """PERCEPT 拍：只读，抽信号（不计预算：纯算术）。"""
        ctx.phase = Phase.PERCEPT
        for cap in self._slots[Phase.PERCEPT]:
            ctx.add(self._run_sync(cap, "perceive", ctx))

    def run_deliberate(self, ctx: BeatContext) -> None:
        """DELIBERATE 拍：热路径决策，逐能力扣预算，超支跳过后续。"""
        ctx.phase = Phase.DELIBERATE
        for cap in self._slots[Phase.DELIBERATE]:
            if ctx.budget_ms <= 0:
                logger.debug("Sylanne v2 budget exhausted, skip deliberate cap %r", cap.name)
                continue
            t0 = time.perf_counter()
            ctx.add(self._run_sync(cap, "deliberate", ctx))
            ctx.budget_ms -= (time.perf_counter() - t0) * 1000.0

    def run_evolve(self, ctx: BeatContext) -> None:
        """EVOLVE 拍：唯一写相位（能力的 evolve 钩子；领域 ingest 由 TurnRunner 驱动）。"""
        ctx.phase = Phase.EVOLVE
        for cap in self._slots[Phase.EVOLVE]:
            try:
                cap.evolve(ctx)
            except Exception as exc:
                logger.warning("Sylanne v2 evolve cap %r failed: %s", cap.name, exc)

    # ------------------------------------------------------------------
    # 便捷入口（单次跑完；测试/compose 场景）
    # ------------------------------------------------------------------
    async def run_until_deliberate(
        self, session_key: str, event: Any, text: str, *,
        budget_ms: float | None = None,
        domains: dict[str, Any] | None = None,
        groups: Any = None,
        now: float | None = None,
    ) -> BeatContext:
        ctx = self.make_context(session_key, event, text, domains=domains,
                                groups=groups, budget_ms=budget_ms, now=now)
        self.run_percept(ctx)
        self.run_deliberate(ctx)
        return ctx

    async def turn(
        self, session_key: str, event: Any, text: str, *,
        budget_ms: float | None = None,
        domains: dict[str, Any] | None = None,
        groups: Any = None,
        now: float | None = None,
    ) -> BeatContext:
        """跑完整三拍（不含领域 ingest/render——那是 TurnRunner 的事）。"""
        ctx = await self.run_until_deliberate(
            session_key, event, text,
            budget_ms=budget_ms, domains=domains, groups=groups, now=now,
        )
        self.run_evolve(ctx)
        return ctx

    @staticmethod
    def _run_sync(cap: Capability, method: str, ctx: BeatContext) -> Intent | None:
        fn = getattr(cap, method, None)
        if fn is None:
            return None
        try:
            return fn(ctx)
        except Exception as exc:
            logger.warning("Sylanne v2 cap %r %s failed: %s", cap.name, method, exc)
            return None

    # ------------------------------------------------------------------
    # 意图融合
    # ------------------------------------------------------------------
    @staticmethod
    def fuse(intents: list[Intent]) -> dict[str, Any]:
        """flags 并集 / confidence 加权均值 / affect 加权累加 / payload 托管。"""
        flags: set[str] = set()
        conf_w = 0.0
        conf_acc = 0.0
        affect: dict[str, float] = {}
        carried: dict[str, dict[str, Any]] = {}
        for it in intents:
            flags.update(it.flags)
            if it.confidence is not None:
                conf_acc += it.confidence * it.priority
                conf_w += it.priority
            for k, v in it.affect.items():
                affect[k] = affect.get(k, 0.0) + v * it.priority
            if it.payload:
                carried[it.source] = it.payload
        return {
            "flags": sorted(flags),
            "confidence": (conf_acc / conf_w) if conf_w else None,
            "affect": affect,
            "carried": carried,
        }
