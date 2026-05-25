"""Bounded dictionary with LRU eviction and optional TTL."""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any


class BoundedDict(OrderedDict):
    """OrderedDict with max size (LRU eviction) and optional TTL expiry."""

    def __init__(self, maxsize: int = 200, ttl: float = 0):
        super().__init__()
        self.maxsize = maxsize
        self.ttl = ttl
        self._ts: dict[Any, float] = {}

    def __setitem__(self, key: Any, value: Any) -> None:
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        if self.ttl:
            self._ts[key] = time.time()
        while len(self) > self.maxsize:
            oldest = next(iter(self))
            self._ts.pop(oldest, None)
            del self[oldest]

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
