from __future__ import annotations

import json
from pathlib import Path
from typing import Any

WORKERS_SCHEMA_VERSION = "sylanne.alpha.workers.v1"


class BackgroundQueue:
    def __init__(self, root: Path | str, *, session_key: str, max_workers: int = 1) -> None:
        self.root = Path(root)
        self.session_key = session_key
        self.max_workers = max(1, min(8, int(max_workers)))
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / f"{self.session_key}.workers.json"
        self._pending: list[dict[str, Any]] = []
        self._inflight: list[dict[str, Any]] = []
        self._load()

    def enqueue(self, kind: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        job = {
            "id": f"job-{len(self._pending) + len(self._inflight) + 1}",
            "kind": str(kind),
            "payload": _strip_sensitive_fields(payload or {}),
            "attempts": 0,
        }
        self._pending.append(job)
        return job

    def lease_ready(self) -> list[dict[str, Any]]:
        available = max(0, self.max_workers - len(self._inflight))
        leased = self._pending[:available]
        self._pending = self._pending[available:]
        for job in leased:
            job["attempts"] = int(job.get("attempts") or 0) + 1
            self._inflight.append(job)
        return list(leased)

    def checkpoint(self) -> None:
        self.path.write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": WORKERS_SCHEMA_VERSION,
            "session_key": self.session_key,
            "max_workers": self.max_workers,
            "jobs": [*self._pending, *self._inflight],
            "pending": len(self._pending),
            "inflight": len(self._inflight),
        }

    def pending_count(self) -> int:
        return len(self._pending)

    def inflight_count(self) -> int:
        return len(self._inflight)

    def _load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        jobs = list(data.get("jobs") or [])
        self._pending = jobs
        self._inflight = []


def _strip_sensitive_fields(payload: dict[str, Any]) -> dict[str, Any]:
    safe = {}
    for key, value in payload.items():
        if key in {"text", "raw_text", "prompt", "request", "response"}:
            continue
        safe[str(key)] = value
    return safe


__all__ = ["BackgroundQueue", "WORKERS_SCHEMA_VERSION"]
