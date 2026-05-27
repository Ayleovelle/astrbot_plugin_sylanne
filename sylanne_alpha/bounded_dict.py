"""有界字典模块——带 LRU 驱逐和可选 TTL 过期机制。

用于 Sylanne 插件中需要限制内存占用的缓存场景（如 host 缓存、会话锁缓存、
记忆系统缓存等）。当条目数超过 maxsize 时自动驱逐最久未访问的条目；
当设置了 TTL 时，过期条目在下次访问时惰性删除。
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from typing import Any

try:
    from astrbot.api import logger  # type: ignore
except ImportError:
    logger = logging.getLogger("astrbot_plugin_sylanne")  # type: ignore


class BoundedDict(OrderedDict):
    """带最大容量（LRU 驱逐）和可选 TTL 过期的有序字典。

    继承自 OrderedDict，利用其 move_to_end 实现 O(1) 的 LRU 访问更新。
    驱逐时可触发 on_evict 回调，用于持久化被驱逐的对象（如将 host 状态写盘）。
    """

    def __init__(self, maxsize: int = 200, ttl: float = 0, on_evict=None):
        """初始化有界字典。

        Args:
            maxsize: 最大容量，超出时驱逐最旧条目。
            ttl: 条目存活时间（秒），0 表示不启用 TTL。
            on_evict: 驱逐回调 fn(key, value)，在条目被 LRU 驱逐时调用。
        """
        super().__init__()
        self.maxsize = maxsize
        self.ttl = ttl
        self._ts: dict[Any, float] = {}  # 记录每个 key 的写入时间戳（仅 TTL 模式）
        self._on_evict = on_evict

    def __setitem__(self, key: Any, value: Any) -> None:
        # 已存在的 key 更新时移到末尾，保持 LRU 语义
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        if self.ttl:
            self._ts[key] = time.time()
        # 超容量时循环驱逐最旧条目（队首）
        while len(self) > self.maxsize:
            oldest = next(iter(self))
            self._ts.pop(oldest, None)
            value_evicted = super().__getitem__(oldest)
            del self[oldest]
            if self._on_evict:
                try:
                    self._on_evict(oldest, value_evicted)
                except Exception as exc:
                    logger.warning(
                        "BoundedDict on_evict callback failed for key %r: %s",
                        oldest,
                        exc,
                    )

    def __getitem__(self, key: Any) -> Any:
        # TTL 检查：过期则惰性删除并抛出 KeyError
        if self.ttl and key in self._ts:
            if time.time() - self._ts[key] > self.ttl:
                self._ts.pop(key, None)
                del self[key]
                raise KeyError(key)
        # 访问时移到末尾，更新 LRU 顺序
        if key in self:
            self.move_to_end(key)
        return super().__getitem__(key)

    def get(self, key: Any, default: Any = None) -> Any:
        """获取值，不存在或已过期时返回 default。"""
        try:
            return self[key]
        except KeyError:
            return default

    def setdefault(self, key: Any, default: Any = None) -> Any:
        """若 key 不存在则设置为 default 并返回。"""
        if key not in self:
            self[key] = default
        return self[key]
