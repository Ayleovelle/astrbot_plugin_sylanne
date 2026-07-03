"""MEM-03 PR-1：记忆写入单写咽喉（MemoryWriteThroat）+ 化身栅栏原语。

设计见 docs/architecture/mem-phase1-write-throat-design.md。本模块提供两个正交原语：

- **咽喉**：per-session FIFO 写队列 + 单 drainer，把同一会话的所有记忆 KV 写按提交序
  串行化——根治 F2（v2→v3 备份门无锁 read-check-write 的 TOCTOU：两条并发首写在队列里
  天然串行，"backup_key 写一次此后只读"不变量恢复）。
- **化身栅栏**：per-session 单调纪元 `_epochs` + 每个 MemorySystem 活体的运行时印章
  `_incarnation_epoch` + bump-and-restamp + 执行前验章——根治 F3（删除后陈旧引用复活：
  光有 FIFO 顺序不够，delete 之后入队的 stale save 会被顺序【保证】执行，必须靠血统验章
  把携带旧印章的 op 丢弃）。

**PR-1 里栅栏生产惰性**：本 PR 不接任何 `bump_epoch` 生产调用方（那是 PR-2 的删除臂），
故纪元恒为 0、印章恒匹配、验章恒通过——PR-1 唯一的实际行为变化是 save/驱逐落盘两条
v3 首写被串行化（关掉 F2）+ off-loop 驱逐落盘从 `coro.close()` 静默丢改为经绑定 loop 执行
（fail-safe，仍受 `_refuse_unhydrated_overwrite` 守卫）。栅栏机制在 PR-1 就位并测试，PR-2
只需接上 bump 调用方即生效。

fail-closed 总纲：验章失败=丢弃不执行；loop 未绑定且 off-loop=丢弃不执行（等价今日
`coro.close()`）；op 异常逐 op 捕获并经 Future 传播，绝不杀 drainer。
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any, Awaitable, Callable

logger = logging.getLogger("astrbot_plugin_sylanne")

# op 携带的协程工厂：无参、返回一个待 await 的协程（通常是某个 _impl 方法调用）。
OpFactory = Callable[[], Awaitable[Any]]


class _Op:
    __slots__ = ("kind", "factory", "state", "future", "token")

    def __init__(
        self,
        kind: str,
        factory: OpFactory,
        *,
        state: Any = None,
        future: "asyncio.Future | None" = None,
    ) -> None:
        self.kind = kind  # 'write' | 'hydrate' | 'delete' | 'purge' | ...
        self.factory = factory
        # 写类 op 携带 MemorySystem 活体，验章比对其印章；无载荷 op 验入队时捕获的 token。
        self.state = state
        self.future = future
        self.token = 0  # 于 _enqueue 内（恒在 loop 上）捕获当时纪元


class MemoryWriteThroat:
    """记忆写入单写咽喉 + 化身栅栏。实例挂在 StatePersistence 上（每插件一个）。

    Args:
        occupant_getter: 同步返回某 session 在 store 里当前占位 MemorySystem 的回调
            （占位者权威兜底用；缺省 None 表示不做兜底——占位者恒视为 None）。
    """

    def __init__(self, occupant_getter: "Callable[[str], Any] | None" = None) -> None:
        self._loop: "asyncio.AbstractEventLoop | None" = None
        self._queues: dict[str, deque[_Op]] = {}
        self._drainers: dict[str, asyncio.Task] = {}
        # 纪元表：只为"发生过删除/purge 的会话"建条目（进程内即可——陈旧 Python 引用
        # 不可能跨进程存活；跨重启保护由 PR-4 的全局 pending-delete 索引负责）。
        # 【刻意不】注册进 session_state_store._maps：release_session 会 pop 登记容器，
        # 墓碑被 pop = fail-open（正是要防的事，见设计 §1/§2）。
        self._epochs: dict[str, int] = {}
        # 正在执行 op 的会话集合——防"drainer op 内部再 submit+await 同队列"自死锁
        # （含 op spawn 的子任务，因为按 session 判定与调用者 task 身份无关）。
        self._in_drainer: set[str] = set()
        self._occupant_getter = occupant_getter
        # 可观测计数（暴露到 admin inspect / 日志）。
        self.reject_count = 0
        self.rebuild_count = 0
        self.dropped_no_loop_count = 0

    # ------------------------------------------------------------------
    # loop 绑定
    # ------------------------------------------------------------------

    def bind_loop(self, loop: "asyncio.AbstractEventLoop") -> None:
        """权威绑定事件循环（main.py initialize() 里调）。幂等。"""
        self._loop = loop

    # ------------------------------------------------------------------
    # 化身栅栏原语
    # ------------------------------------------------------------------

    def current_epoch(self, session_key: str) -> int:
        return self._epochs.get(session_key, 0)

    def stamp(self, state: Any, session_key: str) -> None:
        """给活体盖上当前纪元印章。运行时属性，绝不序列化（不进 to_dict）。"""
        if state is None:
            return
        try:
            state._incarnation_epoch = self._epochs.get(session_key, 0)
        except Exception:  # noqa: BLE001 — 印章只是运行时优化，失败退化为 epoch==0 语义
            pass

    def bump_epoch(self, session_key: str, occupant: Any = None) -> int:
        """删除/purge 壳在提交瞬间同步调用：纪元 +1，并对当前占位者 bump-and-restamp。

        PR-1 无生产调用方（栅栏惰性）；PR-2 的删除臂接上后即生效。

        bump-and-restamp 语义 = "凡不是此刻占位者的引用全部出局"：meltdown/purge 是
        "原地清空活体 + 继续当占位者"，只 bump 不 restamp 会让 wipe 后继续聊天的新记忆
        因旧印章被永久拒写（比复活更糟）——故对占位者重新盖新章放行，对其余旧引用出局。
        """
        new_epoch = self._epochs.get(session_key, 0) + 1
        self._epochs[session_key] = new_epoch
        if occupant is None and self._occupant_getter is not None:
            try:
                occupant = self._occupant_getter(session_key)
            except Exception:  # noqa: BLE001
                occupant = None
        if occupant is not None:
            self.stamp(occupant, session_key)
        return new_epoch

    def _validate(self, op: _Op, session_key: str) -> bool:
        """执行前验章。delete/purge 自身豁免（定义 bump，幂等）；写类比对印章 + 占位者
        权威兜底；无载荷 op 比对入队 token。失败 = 丢弃（fail-closed）。
        """
        if op.kind in ("delete", "purge"):
            return True
        cur = self._epochs.get(session_key, 0)
        if op.state is not None:
            stamp = getattr(op.state, "_incarnation_epoch", 0)
            if stamp == cur:
                return True
            # 占位者权威兜底（红队 MINOR-5）：若这个对象【就是】此刻 store 占位者，
            # 说明它是被 meltdown/懒创建原地保留的当前化身，不该出局——重新盖章放行。
            # 杜绝 "off-loop 懒创建盖旧章 → 新记忆永久静默拒写" 的 fail-closed 数据丢失。
            occupant = None
            if self._occupant_getter is not None:
                try:
                    occupant = self._occupant_getter(session_key)
                except Exception:  # noqa: BLE001
                    occupant = None
            if occupant is not None and op.state is occupant:
                self.stamp(op.state, session_key)
                return True
            return False
        return op.token == cur

    # ------------------------------------------------------------------
    # 提交 / 入队 / drainer
    # ------------------------------------------------------------------

    def submit(
        self,
        session_key: str,
        factory: OpFactory,
        *,
        kind: str = "write",
        state: Any = None,
    ) -> "asyncio.Future | None":
        """把一个写 op 提交进 session 队列。

        双路径：
          - on-loop（调用发生在绑定 loop 上）：同步入队，返回可 await 的 Future。
          - off-loop（如 stdlib WebUI 工作线程）：经 `call_soon_threadsafe` 转入绑定 loop
            入队，fire-and-forget 返回 None（跨线程 Future 不安全，线程调用点本就 f&f）。
          - loop 未绑定且 off-loop：fail-closed 丢弃 + log（等价今日 coro.close()）。

        Returns:
            on-loop 返回 Future（op 完成/被拒/异常时 resolve）；off-loop 或丢弃返回 None。
        """
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None

        if running is not None:
            # 有 running loop = 本调用就在这个 loop 上执行 → on-loop 入队（在当前所在 loop 上
            # create_task/create_future 恒安全）。并把 _loop 重绑定到 running loop：让此后来自
            # 线程的 off-loop 提交用的是【当前活】loop——旧绑定可能已随上一个 asyncio.run 关闭
            # （红队条件③自绑定 + 多 loop 场景的正确性，绝不 call_soon_threadsafe 到闭 loop）。
            if self._loop is not running:
                self._loop = running
            # 红队 MAJOR-6 / 条件③：禁止在本 session drainer op 执行中再 submit 本队列
            # （含 op spawn 的子任务）——单 drainer 等只有自己能完成的 Future = 永久停摆。
            if session_key in self._in_drainer:
                raise RuntimeError(
                    f"MemoryWriteThroat: re-entrant submit to session {session_key!r} "
                    "from within its own drainer op (would deadlock)"
                )
            fut = running.create_future()
            op = _Op(kind, factory, state=state, future=fut)
            self._enqueue(session_key, op)
            return fut

        # 无 running loop → off-loop（如 stdlib WebUI 工作线程）→ 经绑定 loop 转入。
        loop = self._loop
        if loop is None or loop.is_closed():
            self.dropped_no_loop_count += 1
            logger.warning(
                "MemoryWriteThroat: no live bound loop, dropping %s op for %r (fail-closed, "
                "equivalent to legacy coro.close())",
                kind,
                session_key,
            )
            return None
        op = _Op(kind, factory, state=state, future=None)
        loop.call_soon_threadsafe(self._enqueue, session_key, op)
        return None

    def _enqueue(self, session_key: str, op: _Op) -> None:
        """恒在绑定 loop 上执行（on-loop 直调 / off-loop 经 call_soon_threadsafe）。
        在此捕获 token 保证"捕获与入队原子"，并确保 drainer 存在。
        """
        op.token = self._epochs.get(session_key, 0)
        q = self._queues.get(session_key)
        if q is None:
            q = deque()
            self._queues[session_key] = q
        q.append(op)
        self._ensure_drainer(session_key)

    def _ensure_drainer(self, session_key: str) -> None:
        t = self._drainers.get(session_key)
        if t is None:
            self._drainers[session_key] = self._loop.create_task(
                self._drain(session_key)
            )
        elif t.done():
            # 上一 drainer 已结束（正常自毁应已 pop 自身；这里兜底重建）。
            self.rebuild_count += 1
            self._drainers[session_key] = self._loop.create_task(
                self._drain(session_key)
            )

    async def _drain(self, session_key: str) -> None:
        q = self._queues.get(session_key)
        while q:
            op = q.popleft()
            if not self._validate(op, session_key):
                self.reject_count += 1
                logger.warning(
                    "MemoryWriteThroat: fence rejected %s op for %r "
                    "(stale incarnation stamp/token) — dropping to avoid resurrection",
                    op.kind,
                    session_key,
                )
                if op.future is not None and not op.future.done():
                    op.future.set_result(None)  # 被拒 = 无操作，不是错误
                q = self._queues.get(session_key)
                continue
            self._in_drainer.add(session_key)
            try:
                result = await op.factory()
                if op.future is not None and not op.future.done():
                    op.future.set_result(result)
            except Exception as e:  # noqa: BLE001 — 逐 op 隔离，绝不杀 drainer
                logger.error(
                    "MemoryWriteThroat: %s op for %r raised: %s",
                    op.kind,
                    session_key,
                    e,
                    exc_info=True,
                )
                if op.future is not None and not op.future.done():
                    op.future.set_exception(e)
            finally:
                self._in_drainer.discard(session_key)
            q = self._queues.get(session_key)
        # 原子自毁：while 退出时 q 已空，且此后【无 await】——单 loop 语义下 _enqueue
        # 不可能在这两步之间插入，故 pop 是安全的。下一次 submit 会经 _ensure_drainer 重建。
        if not self._queues.get(session_key):
            self._queues.pop(session_key, None)
            self._drainers.pop(session_key, None)

    # ------------------------------------------------------------------
    # 可观测
    # ------------------------------------------------------------------

    def queue_depth(self, session_key: str) -> int:
        q = self._queues.get(session_key)
        return len(q) if q is not None else 0

    def stats(self) -> dict[str, int]:
        return {
            "reject_count": self.reject_count,
            "rebuild_count": self.rebuild_count,
            "dropped_no_loop_count": self.dropped_no_loop_count,
            "active_sessions": len(self._drainers),
            "tracked_epochs": len(self._epochs),
        }


__all__ = ["MemoryWriteThroat"]
