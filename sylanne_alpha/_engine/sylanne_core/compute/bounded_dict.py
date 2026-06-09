"""Bounded LRU dictionary with optional TTL."""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from typing import Any

logger = logging.getLogger("sylanne_core")


class BoundedDict(OrderedDict[Any, Any]):
    def __init__(self, maxsize: int = 200, ttl: float = 0, on_evict: Any = None) -> None:
        super().__init__()
        self.maxsize = maxsize
        self.ttl = ttl
        self._ts: dict[Any, float] = {}
        self._on_evict = on_evict

    def __setitem__(self, key: Any, value: Any) -> None:
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        if self.ttl:
            self._ts[key] = time.time()
        while len(self) > self.maxsize:
            oldest = next(iter(self))
            self._ts.pop(oldest, None)
            value_evicted = super().__getitem__(oldest)
            del self[oldest]
            if self._on_evict:
                try:
                    self._on_evict(oldest, value_evicted)
                except Exception as exc:
                    logger.warning("BoundedDict on_evict failed for %r: %s", oldest, exc)

    def __getitem__(self, key: Any) -> Any:
        if self.ttl and key in self._ts:
            if time.time() - self._ts[key] > self.ttl:
                self._ts.pop(key, None)
                del self[key]
                raise KeyError(key)
        if key in self:
            self.move_to_end(key)
        return super().__getitem__(key)

    def get(self, key: Any, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def setdefault(self, key: Any, default: Any = None) -> Any:
        if key not in self:
            self[key] = default
        return self[key]
