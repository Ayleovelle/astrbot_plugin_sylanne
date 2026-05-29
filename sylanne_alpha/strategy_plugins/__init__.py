"""回复策略插件系统。

提供回复策略的抽象基类和管理器，支持第三方注册自定义回复策略。
策略按注册顺序依次应用，每个策略可以选择性激活并转换回复内容。
"""
from __future__ import annotations
from abc import ABC, abstractmethod


class ReplyStrategy(ABC):
    """回复策略抽象基类。"""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def should_activate(self, context: dict) -> bool:
        """判断是否应该激活此策略。"""
        ...

    @abstractmethod
    def transform_reply(self, reply: str, context: dict) -> str:
        """转换回复内容。"""
        ...


class StrategyManager:
    """回复策略管理器：注册、启用/禁用、按序应用策略。"""

    def __init__(self):
        self._strategies: list[ReplyStrategy] = []
        self._enabled: set[str] = set()

    def register(self, strategy: ReplyStrategy):
        """注册一个回复策略（默认启用）。"""
        self._strategies.append(strategy)
        self._enabled.add(strategy.name)

    def enable(self, name: str):
        """启用指定策略。"""
        self._enabled.add(name)

    def disable(self, name: str):
        """禁用指定策略。"""
        self._enabled.discard(name)

    def apply(self, reply: str, context: dict) -> str:
        """按注册顺序应用所有已启用且激活的策略。"""
        for s in self._strategies:
            if s.name in self._enabled and s.should_activate(context):
                reply = s.transform_reply(reply, context)
        return reply
