"""AutonomyScheduler：全局自驱心跳（CP8-P3b）。

让 Sylanne「没人说话也活着」——全局单 task 后台循环，定期：
1. 全局演化一次：驱动 LifeAgent 的 AUTONOMOUS 时点（作息/生活事件，一个 bot 一套）。
2. 三态扫会话：对每个活跃会话按 AWAKE/DROWSY/RETIRED 决定是否自驱演化
   （空 event 驱动 host 计算 + run_cycle(AUTONOMOUS)）。

防死锁纪律（避免 3.0 回归）：
- 单 task，while True + sleep + try/except CancelledError（对齐现有循环模式）。
- 不用全局锁——按会话 session_lock 串行化（与 reactive 后台 observe 同锁），
  对同一会话串行、不同会话并行，无交叉等待。
- 临界区（持锁期间）只做同步 tick + run_cycle，agent 的 LLM/IO 在 act 内可超时降级。
- RETIRED 会话移出迭代（资源归零）；用户消息经 reactive 路径自动唤醒（last_user_
  message_time 刷新 → autonomy_phase 回 AWAKE）。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from sylanne_alpha.agents.base import AUTONOMOUS

if TYPE_CHECKING:
    from sylanne_alpha.agents.self_core import SelfCore
    from sylanne_alpha.protocols import PluginHost

logger = logging.getLogger("astrbot_plugin_sylanne")


class AutonomyScheduler:
    """全局自驱心跳。单例，由 main 在 initialize 启动、terminate 回收。"""

    def __init__(self, plugin: PluginHost, self_core: SelfCore) -> None:
        self._p = plugin
        self._sc = self_core
        self._task: asyncio.Task | None = None
        self._tick_count = 0
        # 深睡巩固引擎（CP8-P4-D 层次3，零 LLM）：RETIRED 前沉淀经验
        from sylanne_alpha.agents.learning import ConsolidationEngine, ReflectionEngine
        self._consolidation = ConsolidationEngine(plugin)
        # 反思引擎（CP8-P4-E 层次2，低频 LLM）：AWAKE→DROWSY 首拍触发一次元认知
        self._reflection = ReflectionEngine(plugin, self_core)
        # 上一拍各会话相位（检测 AWAKE→DROWSY 跳变 = 反思首拍闸）
        self._prev_phase: dict[str, str] = {}

    @property
    def _base_interval(self) -> float:
        """扫描节拍（秒）。默认 30s，下限 0.1s（允许测试/激进配置）。"""
        try:
            return max(
                0.1,
                float((self._p.config or {}).get("sylanne_alpha_autonomy_scan_interval_seconds", 30.0)),
            )
        except Exception:
            return 30.0

    @property
    def _drowsy_divisor(self) -> int:
        """DROWSY 会话降频倍数：每 N 个扫描拍才演化一次。"""
        try:
            return max(1, int((self._p.config or {}).get("sylanne_alpha_autonomy_drowsy_divisor", 4)))
        except Exception:
            return 4

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        try:
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._loop(), name="autonomy_scheduler")
        except RuntimeError:
            pass  # 无运行中的 loop（测试/同步上下文），跳过

    def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._base_interval)
                self._tick_count += 1
                await self._scan_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Sylanne AutonomyScheduler tick error: %s", exc)
                await asyncio.sleep(60.0)

    async def _scan_once(self) -> None:
        now = time.time()
        # 1. 全局演化一次：LifeAgent 的 AUTONOMOUS 时点（作息/生活事件，全局一套）。
        #    用任一活跃会话的 surface 作上下文；无会话则用 default。
        await self._global_autonomy(now)

        # 2. 三态扫各会话：AWAKE 每拍 / DROWSY 降频 / RETIRED 跳过。
        try:
            sessions = self._p._store.hosts.snapshot_items()
        except Exception:
            sessions = []
        for sk, host in sessions:
            phase = self._sc.autonomy_phase(sk, now)
            prev = self._prev_phase.get(sk)
            self._prev_phase[sk] = phase
            if phase == self._sc.RETIRED:
                # 深睡：退休前跑一次巩固（记忆固化 + 进化档案落盘），再归零。
                # session_lock 串行化，与 reactive 互斥；巩固内部零 LLM 纯计算。
                if self._consolidation.needs_consolidation(sk, now):
                    lock = self._p._session_lock(sk)
                    async with lock:
                        await self._consolidation.consolidate(sk, now)
                continue  # 巩固后移出自驱，资源归零
            if phase == self._sc.DROWSY:
                # CP8-P4-E 首拍闸：仅 AWAKE→DROWSY 跳变的那一拍触发一次反思
                # （低频 LLM 元认知）。maybe_reflect 内部还有预算池 + 间隔兜底。
                if prev == self._sc.AWAKE:
                    await self._reflection.maybe_reflect(sk, now)
                if (self._tick_count % self._drowsy_divisor) != 0:
                    continue  # 降频
            await self._tick_session(sk, host, now)

    async def _global_autonomy(self, now: float) -> None:
        """驱动全局演化（LifeAgent AUTONOMOUS）。用 default 会话 surface 作上下文。"""
        try:
            host = self._p._store.hosts.get("default")
            if host is None:
                # 取任一活跃会话的 host
                items = self._p._store.hosts.snapshot_items()
                host = items[0][1] if items else None
            surface = host.kernel.surface() if host is not None else {}
            await self._sc.run_cycle("default", surface, phase=AUTONOMOUS)
        except Exception as exc:
            logger.debug("Sylanne global autonomy: %s", exc)

    async def _tick_session(self, session_key: str, host, now: float) -> None:
        """单会话自驱 tick：按会话锁串行化，空 event 驱动演化 + run_cycle。"""
        lock = self._p._session_lock(session_key)
        async with lock:
            try:
                # 空 event 驱动 host 纯演化（无文本，body 状态照常漂移）
                host.on_request(None)
                surface = host.kernel.surface()
                await self._sc.run_cycle(session_key, surface, phase=AUTONOMOUS)
            except Exception as exc:
                logger.debug("Sylanne autonomy tick [%s]: %s", session_key, exc)
