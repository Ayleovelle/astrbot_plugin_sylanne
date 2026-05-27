"""共享工具函数模块。

提供 sylanne_alpha 各子模块通用的异步辅助工具，核心功能是安全地将协程
调度为后台 Task 并自动处理异常日志和生命周期清理。
"""

from __future__ import annotations

import asyncio
from typing import Any

try:
    from astrbot.api import logger  # type: ignore
except ImportError:
    import logging as _logging

    logger = _logging.getLogger("astrbot_plugin_sylanne")  # type: ignore


def safe_ensure_future(
    coro: Any, name: str = "task", task_list: list | None = None
) -> "asyncio.Task[Any]":
    """将协程安全地调度为 asyncio Task，并附加异常日志回调。

    Args:
        coro: 待调度的协程对象。
        name: 任务名称，用于异常日志标识。
        task_list: 可选的任务列表，任务创建时加入、完成时自动移除，
                   便于外部统一管理/取消后台任务。

    Returns:
        创建的 asyncio.Task 实例。
    """
    loop = asyncio.get_running_loop()
    task = loop.create_task(coro)
    if task_list is not None:
        task_list.append(task)

    def _done(t: "asyncio.Task[Any]") -> None:
        # 任务完成后从列表中移除，保持列表只含活跃任务
        if task_list is not None:
            try:
                task_list.remove(t)
            except ValueError:
                pass
        if t.cancelled():
            return
        exc = t.exception()
        if exc:
            logger.warning(f"Sylanne background task [{name}] failed: {exc}")

    task.add_done_callback(_done)
    return task
