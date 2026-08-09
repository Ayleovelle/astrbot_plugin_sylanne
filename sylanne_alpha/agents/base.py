"""AUTONOMOUS worker 的最小生命周期契约。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sylanne_alpha.protocols import PluginHost

SKIP = "skip"
RULE = "rule"
LLM = "llm"
AUTONOMOUS = "autonomous"


class CognitiveAgent:
    """只在自主心跳中运行的感知—门控—行动 worker。"""

    name: str = "base"
    phases: tuple[str, ...] = (AUTONOMOUS,)

    def __init__(self, plugin: PluginHost) -> None:
        self._p = plugin

    def perceive(self, surface: dict[str, Any]) -> dict[str, Any]:
        """从只读 surface 抽取本 worker 关心的信号。"""
        return {}

    def gate(self, perceived: dict[str, Any]) -> str:
        """返回 SKIP/RULE/LLM；门控本身不执行 IO。"""
        return SKIP

    async def act(
        self, session_key: str, mode: str, perceived: dict[str, Any]
    ) -> None:
        """执行一次自主动作。"""
        return None
