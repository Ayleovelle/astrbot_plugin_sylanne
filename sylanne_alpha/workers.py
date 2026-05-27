"""后台工作队列模块（文件级持久化）。

提供 BackgroundQueue 类，实现简单的任务队列：入队 → 租约（lease）→ 完成/重试。
与 background_queue.py 中的 BackgroundPostQueue 不同，本模块面向通用后台任务，
使用文件 (.workers.json) 做 checkpoint，不依赖 KV 存储。

核心概念：
- pending: 等待执行的任务列表
- inflight: 已被 lease 正在执行的任务列表
- max_workers: 同时执行的最大任务数（即 inflight 上限）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

WORKERS_SCHEMA_VERSION = "sylanne.alpha.workers.v1"


class BackgroundQueue:
    """基于文件持久化的后台任务队列。

    每个 session 对应一个 .workers.json 文件，支持 enqueue/lease/complete
    的完整任务生命周期，以及 checkpoint 持久化和重启恢复。
    """

    def __init__(
        self, root: Path | str, *, session_key: str, max_workers: int = 1
    ) -> None:
        """初始化后台队列。

        Args:
            root: 持久化文件存储目录。
            session_key: 会话标识，决定文件名。
            max_workers: 最大并发工作数，钳位到 [1, 8]。
        """
        self.root = Path(root)
        self.session_key = session_key
        self.max_workers = max(1, min(8, int(max_workers)))
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / f"{self.session_key}.workers.json"
        self._pending: list[dict[str, Any]] = []
        self._inflight: list[dict[str, Any]] = []
        self._next_job_id: int = 1
        self._load()

    def enqueue(
        self, kind: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """将新任务加入待执行队列。

        Args:
            kind: 任务类型标识（如 "assess", "consolidate" 等）。
            payload: 任务负载数据，敏感字段会被自动剥离。

        Returns:
            创建的任务字典（含 id/kind/payload/attempts）。
        """
        job = {
            "id": f"job-{self._next_job_id}",
            "kind": str(kind),
            "payload": _strip_sensitive_fields(payload or {}),
            "attempts": 0,
        }
        self._next_job_id += 1
        self._pending.append(job)
        return job

    def lease_ready(self) -> list[dict[str, Any]]:
        """租约：从 pending 中取出可执行的任务，移入 inflight。

        取出数量 = min(pending 数量, max_workers - 当前 inflight 数量)。
        每次 lease 会递增任务的 attempts 计数。

        Returns:
            本次租约获得的任务列表。
        """
        available = max(0, self.max_workers - len(self._inflight))
        leased = self._pending[:available]
        self._pending = self._pending[available:]
        for job in leased:
            job["attempts"] = int(job.get("attempts") or 0) + 1
            self._inflight.append(job)
        return list(leased)

    def complete(self, job_id: str) -> bool:
        """标记任务完成，从 inflight 中移除。

        Args:
            job_id: 任务 ID。

        Returns:
            True 表示找到并移除成功，False 表示未找到。
        """
        for i, job in enumerate(self._inflight):
            if job.get("id") == job_id:
                self._inflight.pop(i)
                return True
        return False

    def checkpoint(self) -> None:
        """将当前队列状态持久化到 .workers.json 文件。"""
        self.path.write_text(
            json.dumps(self.snapshot(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def snapshot(self) -> dict[str, Any]:
        """生成当前队列状态的快照字典。

        Returns:
            包含 schema_version、session_key、max_workers、jobs 等字段的字典。
        """
        return {
            "schema_version": WORKERS_SCHEMA_VERSION,
            "session_key": self.session_key,
            "max_workers": self.max_workers,
            "jobs": [*self._pending, *self._inflight],
            "pending": len(self._pending),
            "inflight": len(self._inflight),
        }

    def pending_count(self) -> int:
        """返回待执行任务数。"""
        return len(self._pending)

    def inflight_count(self) -> int:
        """返回正在执行的任务数。"""
        return len(self._inflight)

    def _load(self) -> None:
        """从文件恢复队列状态。

        恢复时所有任务都回到 pending（因为 inflight 的任务在重启后
        无法确认是否已完成，需要重新执行）。同时恢复 job ID 计数器。
        """
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        jobs = list(data.get("jobs") or [])
        self._pending = jobs
        self._inflight = []
        for job in jobs:
            job_id = str(job.get("id", ""))
            if job_id.startswith("job-"):
                try:
                    num = int(job_id[4:])
                    self._next_job_id = max(self._next_job_id, num + 1)
                except ValueError:
                    pass


def _strip_sensitive_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """剥离 payload 中的敏感/大体积文本字段，避免持久化用户原始对话内容。"""
    safe = {}
    for key, value in payload.items():
        if key in {"text", "raw_text", "prompt", "request", "response"}:
            continue
        safe[str(key)] = value
    return safe


__all__ = ["BackgroundQueue", "WORKERS_SCHEMA_VERSION"]
