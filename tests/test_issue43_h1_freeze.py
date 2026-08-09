"""issue#43 Wave1 回归：生活模拟在 LLM 持续失败时不再静默冻结 / 空转。

原 bug（issue#43「主动消息重复」根因 H1）：provider 没配 / 不可用时 _life_sim_llm_call
四处 `return ""` 全程零日志 → _simulate_tick 在 `not parsed` 静默退出 → state 冻结、
due 恒 True 每心跳空烧 LLM。本组覆盖四路径 + 契约：

- 失败可见：连续失败到阈值打 WARNING（不再零日志）
- 退避：失败后跳过若干心跳，不再每拍空烧 LLM
- 不饿死恢复：退避后仍放行探测拍，provider 恢复即复原（漏桶式，绝不永久门死）
- 零副作用契约：失败不推进 state（current_activity / last_simulation_time / count 不变）
- 对照组：正常 caller 推进 state + 失败计数清零
"""

import asyncio
import json
import logging

from sylanne_alpha.life_simulation import LifeSimulator

_FROZEN = "躺在地毯上蜷缩"


def _empty_caller():
    """模拟 provider 持续返回空串（_life_sim_llm_call 失败时的行为）。"""

    async def _c(prompt: str) -> str:
        _c.calls += 1
        return ""

    _c.calls = 0
    return _c


def _good_payload() -> str:
    return json.dumps(
        {
            "activity": "在宿舍写代码",
            "thought": "想他",
            "mood": "warm",
            "wants_to_share": True,
            "urgency": 0.6,
        }
    )


def _make_sim() -> LifeSimulator:
    sim = LifeSimulator(
        config={
            "sylanne_alpha_life_simulation_enabled": True,
            "sylanne_alpha_life_simulation_interval_seconds": 60,
        }
    )
    sim.state.current_activity = _FROZEN
    sim.state.last_simulation_time = 12345.0
    sim.state.simulation_count = 7
    return sim


def test_silent_failure_now_warns(caplog):
    sim = _make_sim()
    sim.configure(llm_caller=_empty_caller())
    with caplog.at_level(logging.WARNING, logger="sylanne_alpha.life_simulation"):
        for _ in range(3):
            asyncio.run(sim.simulate_tick())
    assert any("连续失败" in r.getMessage() for r in caplog.records), (
        "持续失败必须打 WARNING（issue#43：原本零日志静默冻结）"
    )
    assert sim.consecutive_failures >= 3


def test_backoff_throttles_caller():
    """退避后调用次数远小于心跳次数（原 bug：due 恒 True 每拍空烧）。"""
    sim = _make_sim()
    caller = _empty_caller()
    sim.configure(llm_caller=caller)
    for _ in range(30):
        asyncio.run(sim.simulate_tick())
    assert 0 < caller.calls < 30, "退避必须减少实际 LLM 调用，而不是每心跳都调"
    assert caller.calls <= 10


def test_recovery_not_starved():
    """退避绝不永久门死：provider 恢复后探测拍能放行，state 复原。"""
    sim = _make_sim()
    good = _good_payload()

    async def _c(prompt: str) -> str:
        _c.calls += 1
        return "" if _c.calls <= 3 else good

    _c.calls = 0
    sim.configure(llm_caller=_c)
    for _ in range(40):
        asyncio.run(sim.simulate_tick())
    assert sim.state.simulation_count > 7, "恢复后必须有成功 tick 推进（退避不能饿死恢复）"
    assert sim.consecutive_failures == 0
    assert sim.state.current_activity != _FROZEN


def test_failure_no_side_effects():
    """失败零副作用契约：current_activity / last_simulation_time / count 不被污染。"""
    sim = _make_sim()
    sim.configure(llm_caller=_empty_caller())
    for _ in range(5):
        asyncio.run(sim.simulate_tick())
    assert sim.state.current_activity == _FROZEN
    assert sim.state.last_simulation_time == 12345.0
    assert sim.state.simulation_count == 7


def test_control_good_caller_advances():
    sim = _make_sim()
    good = _good_payload()

    async def _c(prompt: str) -> str:
        return good

    sim.configure(llm_caller=_c)
    asyncio.run(sim.simulate_tick())
    assert sim.state.simulation_count == 8
    assert sim.state.current_activity != _FROZEN
    assert sim.consecutive_failures == 0


def test_setup_exception_routes_to_failure():
    """_load_world_context / _build_prompt 抛错也走失败处理（计数+退避），不被静默吞掉
    （否则会被 life_agent.act 的 except-pass 吞成新的 H1 静默冻结）。"""
    sim = _make_sim()

    async def _c(prompt: str) -> str:
        return _good_payload()  # 调不到——prompt 构建阶段就抛

    sim.configure(llm_caller=_c)

    def _boom(*a, **k):
        raise RuntimeError("boom in build_prompt")

    sim._build_prompt = _boom
    asyncio.run(sim.simulate_tick())
    assert sim.consecutive_failures == 1, "setup 异常必须计入失败（不再绕过计数/退避/告警）"
    assert sim.state.current_activity == _FROZEN, "失败零副作用"
    assert sim.state.simulation_count == 7


def test_counter_resets_on_success():
    sim = _make_sim()
    good = _good_payload()

    async def _c(prompt: str) -> str:
        _c.calls += 1
        return "" if _c.calls <= 2 else good

    _c.calls = 0
    sim.configure(llm_caller=_c)
    asyncio.run(sim.simulate_tick())  # fail 1
    asyncio.run(sim.simulate_tick())  # fail 2
    assert sim.consecutive_failures == 2
    asyncio.run(sim.simulate_tick())  # success（第 3 次调用返回正常 JSON）
    assert sim.consecutive_failures == 0
