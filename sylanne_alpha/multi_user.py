"""Sylanne-Embodiment: Multi-user state isolation.

Each user gets an independent ComputationSpine (SSM state, memory, expression),
while sharing the same HDCEncoder (stateless atom vectors) and the same
identity_kernel from AutopoieticBoundary (personality core is shared).

LRU eviction ensures bounded memory when user count exceeds max_users.
Evicted states are persisted to disk and restored on next access.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .autopoiesis import AutopoieticBoundary
from .computation_spine import ComputationSpine
from .hdc import HDCEncoder


class MultiUserSpine:
    """Manages per-user ComputationSpine instances with shared components."""

    __slots__ = (
        "_shared_encoder",
        "_shared_identity_kernel",
        "_spines",
        "_access_order",
        "max_users",
        "_root",
    )

    def __init__(self, max_users: int = 50, root: str = ".sylanne_alpha_state"):
        self.max_users = max_users
        self._root = root
        # Shared stateless encoder (atom vectors are deterministic)
        self._shared_encoder = HDCEncoder(dim=2048)
        # Shared identity kernel (personality core)
        self._shared_identity_kernel = AutopoieticBoundary.create_shared_kernel(32)
        # Per-user spines
        self._spines: dict[str, ComputationSpine] = {}
        # LRU tracking: list of user_ids, most-recent at end
        self._access_order: list[str] = []

    def process(
        self, user_id: str, text: str, timestamp: float = 0.0
    ) -> dict[str, Any]:
        """Process a message for a specific user."""
        spine = self._get_or_create(user_id)
        self._touch(user_id)
        return spine.process(text, timestamp)

    def get_spine(self, user_id: str) -> ComputationSpine:
        """Get the spine for a user (creates if needed, restores from disk if evicted)."""
        spine = self._get_or_create(user_id)
        self._touch(user_id)
        return spine

    def active_users(self) -> list[str]:
        """Return list of active user_ids in LRU order (most recent last)."""
        return list(self._access_order)

    def evict(self, user_id: str):
        """Manually evict a user's state (persists to disk)."""
        if user_id in self._spines:
            self._persist_spine(user_id, self._spines[user_id])
            del self._spines[user_id]
        if user_id in self._access_order:
            self._access_order.remove(user_id)

    def _get_or_create(self, user_id: str) -> ComputationSpine:
        """Get existing spine or create a new one with shared components."""
        if user_id in self._spines:
            return self._spines[user_id]

        # Evict LRU if at capacity
        while len(self._spines) >= self.max_users:
            self._evict_lru()

        # Try to restore from disk
        spine = self._restore_spine(user_id)
        if spine is None:
            # Create new spine with shared encoder and identity kernel
            spine = ComputationSpine()
        spine.replace_encoder(self._shared_encoder)
        spine.boundary.set_identity_kernel(self._shared_identity_kernel)
        self._spines[user_id] = spine
        return spine

    def _touch(self, user_id: str):
        """Move user_id to end of access order (most recent)."""
        if user_id in self._access_order:
            self._access_order.remove(user_id)
        self._access_order.append(user_id)

    def _evict_lru(self):
        """Evict the least recently used user, persisting state to disk."""
        if self._access_order:
            oldest = self._access_order.pop(0)
            spine = self._spines.pop(oldest, None)
            if spine is not None:
                self._persist_spine(oldest, spine)

    def _evicted_path(self, user_id: str) -> Path:
        """Return the file path for an evicted user's state."""
        safe = (
            "".join(
                ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in user_id
            )
            or "default"
        )
        return Path(self._root) / "evicted" / f"{safe}.json"

    def _persist_spine(self, user_id: str, spine: ComputationSpine):
        """Serialize and write spine state to disk."""
        path = self._evicted_path(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = spine.to_dict()
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def _restore_spine(self, user_id: str) -> ComputationSpine | None:
        """Try to restore a spine from disk. Returns None if no evicted file."""
        path = self._evicted_path(user_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            spine = ComputationSpine()
            spine.from_dict(data)
            # Remove the evicted file after successful restore
            os.remove(path)
            return spine
        except (json.JSONDecodeError, OSError, KeyError, TypeError):
            return None
