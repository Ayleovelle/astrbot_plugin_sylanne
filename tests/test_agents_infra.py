"""AUTONOMOUS-only Agent 生命周期契约。"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
from types import SimpleNamespace

import sylanne_alpha.agents as agents
from sylanne_alpha.agents import (
    AUTONOMOUS,
    RULE,
    SKIP,
    CognitiveAgent,
    LifeAgent,
    SelfCore,
)
from sylanne_alpha.agents.autonomy_scheduler import AutonomyScheduler


class _StubPlugin:
    def __init__(self, life_simulator=None):
        self.config = {}
        self._life_simulator = life_simulator


class _SpyAgent(CognitiveAgent):
    name = "spy"

    def __init__(self, plugin, *, mode=RULE, fail=False):
        super().__init__(plugin)
        self._mode = mode
        self._fail = fail
        self.calls = 0

    def gate(self, perceived):
        return self._mode

    async def act(self, session_key, mode, perceived):
        self.calls += 1
        if self._fail:
            raise RuntimeError("boom")


def test_agent_package_exports_only_autonomous_contract() -> None:
    for retired in (
        "PRE",
        "POST",
        "RESPONSE_POST",
        "AgentIntent",
        "EventBus",
        "ComposedInputs",
    ):
        assert not hasattr(agents, retired)
    assert agents.AUTONOMOUS == "autonomous"
    assert importlib.util.find_spec("sylanne_alpha.agents.event_bus") is None


def test_self_core_runs_only_active_autonomous_workers() -> None:
    core = SelfCore(_StubPlugin())
    active = _SpyAgent(core._p)
    skipped = _SpyAgent(core._p, mode=SKIP)
    core.register(active)
    core.register(skipped)

    result = asyncio.run(core.run_autonomous_cycle("s1", {}))

    assert result is None
    assert active.calls == 1
    assert skipped.calls == 0


def test_autonomous_worker_failure_is_isolated() -> None:
    core = SelfCore(_StubPlugin())
    broken = _SpyAgent(core._p, fail=True)
    healthy = _SpyAgent(core._p)
    core.register(broken)
    core.register(healthy)

    asyncio.run(core.run_autonomous_cycle("s1", {}))

    assert broken.calls == 1
    assert healthy.calls == 1


def test_life_agent_has_no_reactive_phase_and_ticks_when_due() -> None:
    class _LifeSimulator:
        enabled = True
        interval_seconds = 1.0
        state = SimpleNamespace(last_simulation_time=0.0)

        def __init__(self):
            self.ticks = 0

        async def simulate_tick(self):
            self.ticks += 1

    simulator = _LifeSimulator()
    agent = LifeAgent(_StubPlugin(simulator))

    assert agent.phases == (AUTONOMOUS,)
    asyncio.run(agent.act("default", RULE, {"autonomy_due": True}))
    assert simulator.ticks == 1


def test_scheduler_calls_explicit_autonomous_cycle() -> None:
    source = inspect.getsource(AutonomyScheduler)
    assert "run_autonomous_cycle" in source
    assert "run_cycle" not in source
