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

性能优化（2c2g 低配服务器适配）：
- _base_interval 默认 90s（原 30s），降低扫描频率
- AWAKE 会话加降频倍数（每 _awake_divisor 拍才 tick 一次，默认 2 → 实际 180s）
- DROWSY 降频倍数默认 6（原 4 → 实际 540s）
- 单次 scan 最多 tick _max_ticks_per_scan 个会话（默认 3），防 CPU burst
- 会话间 asyncio.sleep(0) yield 让出控制权，防阻塞 reactive 路径
- host.on_request(None) 跑在 executor 里防阻塞事件循环
"""

from __future__ import annotations

import asyncio
import functools
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
        # Phase 2 核心：生活巩固引擎（夜间零 LLM）——当天 LifeEvent → 次日 LifePlan + 关系摘要。
        # 与对话策略 ConsolidationEngine 独立命名/预算/KV namespace（proposal §4.4）。
        from sylanne_alpha.life_consolidation import LifeConsolidationEngine
        self._life_consolidation = LifeConsolidationEngine(plugin)
        # 反思引擎（CP8-P4-E 层次2，低频 LLM）：AWAKE→DROWSY 首拍触发一次元认知
        self._reflection = ReflectionEngine(plugin, self_core)
        # Phase 2 核心：生活反思引擎（白天/入睡前低频 LLM）——产次日计划建议 next_plan_hint。
        # 活在生活模拟域，与对话策略 ReflectionEngine 独立预算/KV（proposal §4.4 防污染）。
        from sylanne_alpha.life_reflection import LifeReflectionEngine
        self._life_reflection = LifeReflectionEngine(plugin)
        # 上一拍各会话相位（检测 AWAKE→DROWSY 跳变 = 反思首拍闸）
        self._prev_phase: dict[str, str] = {}

    @property
    def _base_interval(self) -> float:
        """扫描节拍（秒）。默认 90s（2c2g 适配），下限 0.1s（允许测试/激进配置）。"""
        try:
            return max(
                0.1,
                float((self._p.config or {}).get("sylanne_alpha_autonomy_scan_interval_seconds", 90.0)),
            )
        except Exception:
            return 90.0

    @property
    def _drowsy_divisor(self) -> int:
        """DROWSY 会话降频倍数：每 N 个扫描拍才演化一次（默认 6 → 实际 ~540s）。"""
        try:
            return max(1, int((self._p.config or {}).get("sylanne_alpha_autonomy_drowsy_divisor", 6)))
        except Exception:
            return 6

    @property
    def _awake_divisor(self) -> int:
        """AWAKE 会话降频倍数：每 N 个扫描拍才 tick 一次（默认 2 → 实际 ~180s）。"""
        try:
            return max(1, int((self._p.config or {}).get("sylanne_alpha_autonomy_awake_divisor", 2)))
        except Exception:
            return 2

    @property
    def _max_ticks_per_scan(self) -> int:
        """单次 scan 最多 tick 多少个会话（防 CPU burst，默认 3）。"""
        try:
            return max(1, int((self._p.config or {}).get("sylanne_alpha_autonomy_max_ticks_per_scan", 3)))
        except Exception:
            return 3

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

    def forget_session(self, session_key: str) -> None:
        """释放某会话在自驱层的残留态（CP8-P6：会话删除/驱逐时清理，防无界增长）。

        清 _prev_phase（相位跳变追踪）+ 转交反思/巩固引擎清各自的 per-session 守卫。
        """
        self._prev_phase.pop(session_key, None)
        try:
            self._reflection.forget_session(session_key)
        except Exception:
            pass
        try:
            self._consolidation.forget_session(session_key)
        except Exception:
            pass
        try:
            self._life_consolidation.forget_session(session_key)
        except Exception:
            pass
        try:
            self._life_reflection.forget_session(session_key)
        except Exception:
            pass

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

        # 2. 三态扫各会话：AWAKE 降频 / DROWSY 降频 / RETIRED 跳过。
        try:
            sessions = self._p._store.hosts.snapshot_items()
        except Exception:
            sessions = []
        ticked = 0
        max_ticks = self._max_ticks_per_scan
        for sk, host in sessions:
            phase = self._sc.autonomy_phase(sk, now)
            prev = self._prev_phase.get(sk)
            self._prev_phase[sk] = phase
            if phase == self._sc.RETIRED:
                # 深睡：退休前跑一次巩固（记忆固化 + 进化档案落盘），再归零。
                # CP8-P6 锁舞：持锁只做同步巩固 + 取快照，KV 落盘移到锁外
                # （避免 put_kv_data 的 IO 长占会话锁、阻塞 reactive 唤醒）。
                if self._consolidation.needs_consolidation(sk, now):
                    lock = self._p._session_lock(sk)
                    async with lock:
                        snapshot = self._consolidation.consolidate_sync(sk, now)
                    if snapshot:
                        try:
                            await self._consolidation._write_evolution(sk, snapshot)
                        except Exception as exc:
                            logger.debug("Sylanne consolidate write [%s]: %s", sk, exc)
                    # yield 让出控制权，防阻塞 reactive 路径
                    await asyncio.sleep(0)
                # Phase 2 核心：生活巩固（当天 LifeEvent → 次日 LifePlan）。独立守卫+锁舞，
                # 与对话策略巩固并列。锁内同步聚合取快照，锁外落盘（IO 不占会话锁）。
                if self._life_consolidation.needs_consolidation(sk, now):
                    lock = self._p._session_lock(sk)
                    async with lock:
                        life_snap = self._life_consolidation.consolidate_sync(sk, now)
                    if life_snap:
                        try:
                            await self._life_consolidation._write_state(sk, life_snap)
                        except Exception as exc:
                            logger.debug("Sylanne life consolidate write [%s]: %s", sk, exc)
                    await asyncio.sleep(0)
                continue  # 巩固后移出自驱，资源归零
            if phase == self._sc.DROWSY:
                # CP8-P4-E 首拍闸：仅 AWAKE→DROWSY 跳变的那一拍触发一次反思
                # （低频 LLM 元认知）。maybe_reflect 内部还有预算池 + 间隔兜底。
                if prev == self._sc.AWAKE:
                    await self._reflection.maybe_reflect(sk, now)
                    # Phase 2 核心：生活反思（独立预算，与对话反思隔离）。同首拍触发，
                    # 产 next_plan_hint 供晚些 RETIRED 巩固读（DROWSY 先于 RETIRED）。
                    try:
                        await self._life_reflection.maybe_reflect(sk, now)
                    except Exception as exc:
                        logger.debug("Sylanne life reflection [%s]: %s", sk, exc)
                if (self._tick_count % self._drowsy_divisor) != 0:
                    continue  # 降频
            elif phase == self._sc.AWAKE:
                # AWAKE 降频：每 _awake_divisor 拍才 tick 一次（默认 2 → 实际 180s）
                if (self._tick_count % self._awake_divisor) != 0:
                    continue
            # 并发上限：单次 scan 最多 tick N 个会话，防 CPU burst
            if ticked >= max_ticks:
                break
            await self._tick_session(sk, host, now)
            ticked += 1
            # 会话间 yield，让 reactive 路径有机会插入
            await asyncio.sleep(0)

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
        """单会话自驱 tick：空 event 驱动演化 + run_cycle。

        host.on_request(None) 跑在 executor 里防阻塞事件循环（2c2g 适配）。
        锁仍持有保证串行化，但 executor 让出 GIL 使其他协程可调度。
        """
        lock = self._p._session_lock(session_key)
        try:
            loop = asyncio.get_running_loop()
            async with lock:
                # executor 内跑纯计算，让出事件循环给 reactive 路径
                await loop.run_in_executor(None, host.on_request, None)
                surface = host.kernel.surface()
            # run_cycle 在锁外：AUTONOMOUS 时点 agent 不写本会话 host
            await self._sc.run_cycle(session_key, surface, phase=AUTONOMOUS)
        except Exception as exc:
            logger.debug("Sylanne autonomy tick [%s]: %s", session_key, exc)
