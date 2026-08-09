"""LifeAgent：由全局自主心跳驱动生活模拟。"""

from __future__ import annotations

import random
import time
from typing import Any

from sylanne_alpha.agents.base import AUTONOMOUS, RULE, SKIP, CognitiveAgent


class LifeAgent(CognitiveAgent):
    name = "life"
    phases = (AUTONOMOUS,)

    def __init__(self, plugin: Any, *, life_simulator: Any = None) -> None:
        super().__init__(plugin)
        self._scoped_life_simulator = life_simulator

    def _simulator(self) -> Any:
        if self._scoped_life_simulator is not None:
            return self._scoped_life_simulator
        # Registry-free compatibility only.
        return getattr(self._p, "_life_simulator", None)

    def perceive(self, surface: dict[str, Any]) -> dict[str, Any]:
        sim = self._simulator()
        enabled = False
        due = False
        if sim is not None:
            try:
                enabled = bool(sim.enabled)
                now = time.time()
                last = float(getattr(sim.state, "last_simulation_time", 0.0) or 0.0)
                interval = sim.interval_seconds * random.uniform(0.4, 1.8)
                due = enabled and (now - last) >= interval
            except Exception:
                pass
        return {"enabled": enabled, "autonomy_due": due}

    def gate(self, perceived: dict[str, Any]) -> str:
        return RULE if perceived.get("autonomy_due") else SKIP

    async def act(
        self, session_key: str, mode: str, perceived: dict[str, Any]
    ) -> None:
        sim = self._simulator()
        if sim is None or not perceived.get("autonomy_due"):
            return
        try:
            await sim.simulate_tick()
        except Exception:
            pass
