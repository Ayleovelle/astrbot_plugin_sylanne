"""Async utility helpers and shared functions."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

_SAFE_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")


def safe_filename(session_key: str) -> str:
    """Convert session_key to filesystem-safe name using percent-encoding."""
    if not session_key:
        return "default"
    parts = []
    for ch in session_key[:128]:
        if ch in _SAFE_CHARS:
            parts.append(ch)
        else:
            parts.append(f"%{ord(ch):02X}")
    return "".join(parts) or "default"


logger = logging.getLogger("sylanne_core")


def safe_ensure_future(
    coro: Any, name: str = "task", task_list: list[Any] | None = None
) -> asyncio.Task[Any]:
    loop = asyncio.get_running_loop()
    task = loop.create_task(coro)
    if task_list is not None:
        task_list.append(task)

    def _done(t: asyncio.Task[Any]) -> None:
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
