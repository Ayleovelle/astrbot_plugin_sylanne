"""MEM-03 PR-1：MemoryWriteThroat（单写咽喉）+ 化身栅栏 单元测试。

覆盖：on-loop 提交执行、drainer 异常经 Future 传播、原子自毁、化身栅栏拒陈旧印章、
占位者权威兜底放行、off-loop（线程）提交经绑定 loop 执行、re-entrancy 自死锁防护、
化身印章绝不序列化（格式零变化）。
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from sylanne_alpha.memory_system import MemorySystem
from sylanne_alpha.memory_write_throat import MemoryWriteThroat


def test_incarnation_epoch_not_serialized() -> None:
    """化身印章是运行时属性，绝不进 to_dict——保证 blob 格式零变化、回滚地板不破。"""
    ms = MemorySystem()
    ms._incarnation_epoch = 7
    d = ms.to_dict()
    assert not any("incarnation" in str(k).lower() for k in d.keys())


def test_on_loop_submit_executes_and_self_destructs() -> None:
    throat = MemoryWriteThroat(occupant_getter=lambda sk: None)

    async def go() -> None:
        ran = []

        async def op() -> str:
            ran.append(1)
            return "ok"

        fut = throat.submit("s", op, kind="write")
        assert fut is not None
        assert await fut == "ok"
        assert ran == [1]
        # 原子自毁：队列/drainer 条目已清空。
        assert throat.queue_depth("s") == 0
        assert "s" not in throat._drainers

        # 再提交 → drainer 重建，照跑。
        async def op2() -> str:
            return "again"

        assert await throat.submit("s", op2) == "again"

    asyncio.run(go())


def test_throat_serializes_concurrent_same_session_ops() -> None:
    """核心保证 + gate T3-1 回归：同 session 两个并发提交（各含 await 挂起点）被咽喉
    【串行】执行、不交错——无锁 read-modify-write 不丢更新。这是 F2 根治的机制本体。
    关键：并发同 session 提交必须【入队串行】而【非】被 re-entrancy 误判拒绝丢弃
    （旧 _in_drainer 集合判据把正常并发也当 re-entrant 拒掉，是 gate 现场复现的真 bug）。
    """
    throat = MemoryWriteThroat()

    async def go() -> None:
        shared = {"v": 0}
        order: list[str] = []

        def make_op(tag: str):
            async def op() -> None:
                x = shared["v"]
                await asyncio.sleep(0)  # 挂起点：无串行化则另一 op 在此插进来读到同一 x
                await asyncio.sleep(0)
                shared["v"] = x + 1
                order.append(tag)

            return op

        # 两个并发提交（来自同一调用任务，非 drainer 任务）——必须都入队，都不被拒。
        f1 = throat.submit("s", make_op("a"), kind="write")
        f2 = throat.submit("s", make_op("b"), kind="write")
        assert f1 is not None and f2 is not None, "并发同 session 提交被 re-entrancy 误拒（T3-1）"
        await asyncio.gather(f1, f2)
        assert shared["v"] == 2, "并发 op 交错丢更新——咽喉未真正串行化"
        assert len(order) == 2

    asyncio.run(go())


def test_drainer_exception_propagates_and_does_not_kill_drainer() -> None:
    throat = MemoryWriteThroat()

    async def go() -> None:
        async def boom() -> None:
            raise ValueError("kaboom")

        fut = throat.submit("s", boom)
        with pytest.raises(ValueError, match="kaboom"):
            await fut

        # drainer 没被 op 异常杀掉：后续 op 正常执行。
        async def ok() -> int:
            return 42

        assert await throat.submit("s", ok) == 42

    asyncio.run(go())


def test_fence_rejects_stale_stamp() -> None:
    """未占位的陈旧印章 op 被验章丢弃（不执行）——fail-closed，防删除后陈旧引用复活。"""
    store: dict = {}
    throat = MemoryWriteThroat(occupant_getter=store.get)

    async def go() -> None:
        ms = MemorySystem()
        throat.stamp(ms, "s")  # 盖 epoch 0
        # 模拟删除臂 bump（无占位者：纪元升到 1，ms 印章仍是 0 = 陈旧血统）。
        throat.bump_epoch("s")
        ran = []

        async def op() -> None:
            ran.append(1)

        fut = throat.submit("s", op, kind="write", state=ms)
        await fut
        assert ran == []  # 被验章拒，未执行
        assert throat.reject_count >= 1

    asyncio.run(go())


def test_fence_occupant_authoritative_allows() -> None:
    """陈旧印章但对象【就是】当前占位者 → restamp 放行——防 wipe 后新记忆永久静默拒写。"""
    store: dict = {}
    throat = MemoryWriteThroat(occupant_getter=store.get)

    async def go() -> None:
        ms = MemorySystem()
        store["s"] = ms  # ms 是 store 占位者
        throat.bump_epoch("s", occupant=ms)  # 纪元 1，bump-and-restamp 把 ms 盖成 1
        ms._incarnation_epoch = 0  # 人为设回陈旧印章，模拟占位者印章滞后
        ran = []

        async def op() -> None:
            ran.append(1)

        fut = throat.submit("s", op, kind="write", state=ms)
        await fut
        assert ran == [1]  # 占位者兜底放行

    asyncio.run(go())


def test_delete_op_exempt_from_fence() -> None:
    """delete/purge op 自身豁免验章（它们定义 bump，重复删除幂等无害）。"""
    throat = MemoryWriteThroat()

    async def go() -> None:
        throat.bump_epoch("s")  # 纪元 1
        ran = []

        async def dop() -> None:
            ran.append(1)

        # 无 state、kind='delete' → 豁免，照跑（不因 token 0 != epoch 1 被拒）。
        await throat.submit("s", dop, kind="delete")
        assert ran == [1]

    asyncio.run(go())


def test_off_loop_submit_from_thread_executes() -> None:
    """stdlib 线程 off-loop 提交经绑定 loop 的 call_soon_threadsafe 执行——修今日
    safe_ensure_future 在无 running loop 线程 coro.close() 静默丢弃落盘的暗病。
    """
    throat = MemoryWriteThroat()
    ran = []

    async def go() -> None:
        loop = asyncio.get_running_loop()
        throat.bind_loop(loop)
        done = loop.create_future()

        async def op() -> None:
            ran.append(1)
            if not done.done():
                done.set_result(True)

        def worker() -> None:
            # 线程内无 running loop → submit 走 off-loop 路径。
            throat.submit("s", op, kind="write")

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        await asyncio.wait_for(done, timeout=3.0)
        assert ran == [1]

    asyncio.run(go())


def test_reentrant_submit_from_within_op_raises() -> None:
    """op 内再 submit 同 session 队列 → 立即抛 RuntimeError（防单 drainer 自死锁）。"""
    throat = MemoryWriteThroat()

    async def go() -> None:
        async def inner() -> None:
            pass

        async def outer() -> None:
            throat.submit("s", inner, kind="write")  # 应抛

        fut = throat.submit("s", outer)
        with pytest.raises(RuntimeError, match="re-entrant"):
            await fut

    asyncio.run(go())


def test_drainer_cancellation_resolves_inflight_future() -> None:
    """MINOR-2：drainer 被取消（关停/reload）时，正在执行的 op Future 被解决（取消）
    而非永久挂起——否则 save/persist 壳里 await fut 的调用方会一直卡住。
    """
    throat = MemoryWriteThroat()

    async def go() -> None:
        started = asyncio.Event()

        async def slow_op() -> None:
            started.set()
            await asyncio.sleep(10)  # 长挂起点，等被取消

        fut = throat.submit("s", slow_op, kind="write")
        assert fut is not None
        await started.wait()  # 确保 op 已开始执行
        drainer = throat._drainers.get("s")
        assert drainer is not None
        drainer.cancel()
        # op Future 必须被解决（取消）；不加 MINOR-2 修复的话这里会永久挂起。
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(fut, timeout=3.0)

    asyncio.run(go())


def test_unbound_loop_off_loop_drops_fail_closed() -> None:
    """未绑定 loop 时线程 off-loop 提交 fail-closed 丢弃（等价今日 coro.close()），不炸。"""
    throat = MemoryWriteThroat()  # 未 bind_loop
    result = {}

    def worker() -> None:
        # 线程内无 running loop 且 throat 未绑定 → 丢弃，返回 None，不抛。
        result["ret"] = throat.submit("s", lambda: None, kind="write")

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert result["ret"] is None
    assert throat.dropped_no_loop_count == 1
