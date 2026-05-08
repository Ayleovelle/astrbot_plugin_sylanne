from __future__ import annotations

import asyncio
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.test_astrbot_lifecycle import FakeEvent, fake_observation, fake_request
from tests.test_command_tools import bind_async, install_astrbot_stubs, new_plugin


async def _bind_fast_state_hooks(plugin, *, drift_saves: list | None = None) -> None:
    from emotion_engine import EmotionState
    from humanlike_engine import HumanlikeState
    from lifelike_learning_engine import LifelikeLearningState
    from moral_repair_engine import MoralRepairState
    from personality_drift_engine import PersonalityDriftState

    drift_saves = drift_saves if drift_saves is not None else []

    async def fake_persona(self, event, request):
        return None

    async def fake_load_state(self, session_key, persona_profile=None):
        state = EmotionState.initial()
        state.updated_at = time.time()
        return state

    async def fake_save_state(self, session_key, state):
        return None

    async def fake_assess_emotion(self, **kwargs):
        return fake_observation()

    async def fake_load_humanlike_state(self, session_key):
        return HumanlikeState.initial()

    async def fake_save_humanlike_state(self, session_key, state):
        return None

    async def fake_load_lifelike_state(self, session_key):
        return LifelikeLearningState.initial()

    async def fake_save_lifelike_state(self, session_key, state):
        return None

    async def fake_load_moral_repair_state(self, session_key):
        return MoralRepairState.initial()

    async def fake_save_moral_repair_state(self, session_key, state):
        return None

    async def fake_load_personality_drift_state(self, session_key, profile=None):
        return PersonalityDriftState.initial(
            persona_fingerprint=profile.fingerprint if profile else "default",
            now=time.time(),
        )

    async def fake_save_personality_drift_state(self, session_key, state):
        drift_saves.append((session_key, state))

    bind_async(plugin, "_persona_profile", fake_persona)
    bind_async(plugin, "_load_state", fake_load_state)
    bind_async(plugin, "_save_state", fake_save_state)
    bind_async(plugin, "_assess_emotion", fake_assess_emotion)
    bind_async(plugin, "_load_humanlike_state", fake_load_humanlike_state)
    bind_async(plugin, "_save_humanlike_state", fake_save_humanlike_state)
    bind_async(plugin, "_load_lifelike_learning_state", fake_load_lifelike_state)
    bind_async(plugin, "_save_lifelike_learning_state", fake_save_lifelike_state)
    bind_async(plugin, "_load_moral_repair_state", fake_load_moral_repair_state)
    bind_async(plugin, "_save_moral_repair_state", fake_save_moral_repair_state)
    bind_async(plugin, "_load_personality_drift_state", fake_load_personality_drift_state)
    bind_async(plugin, "_save_personality_drift_state", fake_save_personality_drift_state)


async def _run_request_case(config: dict, *, iterations: int, prompt: str) -> dict:
    plugin = new_plugin(config)
    await _bind_fast_state_hooks(plugin)
    samples: list[float] = []
    for index in range(iterations):
        request = fake_request(session_id="bench-session", prompt=prompt)
        request.contexts = [
            {"role": "user", "content": "old context " + "x" * 120},
            {"role": "assistant", "content": "old answer " + "y" * 120},
        ]
        event = FakeEvent("bench-session", message=prompt)
        started = time.perf_counter()
        await plugin.on_llm_request(event, request)
        samples.append((time.perf_counter() - started) * 1000.0)
    return _summarize(samples)


async def _run_request_slow_aux_case(
    config: dict,
    *,
    iterations: int,
    prompt: str,
) -> dict:
    from humanlike_engine import HumanlikeState
    from lifelike_learning_engine import LifelikeLearningState
    from moral_repair_engine import MoralRepairState

    plugin = new_plugin(config)
    await _bind_fast_state_hooks(plugin)

    async def slow_humanlike(self, session_key):
        await asyncio.sleep(0.02)
        return HumanlikeState.initial()

    async def slow_lifelike(self, session_key):
        await asyncio.sleep(0.02)
        return LifelikeLearningState.initial()

    async def slow_moral(self, session_key):
        await asyncio.sleep(0.02)
        return MoralRepairState.initial()

    bind_async(plugin, "_load_humanlike_state", slow_humanlike)
    bind_async(plugin, "_load_lifelike_learning_state", slow_lifelike)
    bind_async(plugin, "_load_moral_repair_state", slow_moral)
    samples: list[float] = []
    for _ in range(iterations):
        request = fake_request(session_id="bench-session", prompt=prompt)
        event = FakeEvent("bench-session", message=prompt)
        started = time.perf_counter()
        await plugin.on_llm_request(event, request)
        samples.append((time.perf_counter() - started) * 1000.0)
    return _summarize(samples)


async def _run_response_case(config: dict, *, iterations: int, text: str) -> dict:
    plugin = new_plugin(config)
    await _bind_fast_state_hooks(plugin)
    plugin._last_request_text["bench-session"] = "cached request context"
    samples: list[float] = []
    for _ in range(iterations):
        response = SimpleNamespace(completion_text=text)
        started = time.perf_counter()
        await plugin.on_llm_response(FakeEvent("bench-session"), response)
        samples.append((time.perf_counter() - started) * 1000.0)
    return _summarize(samples)


async def _run_response_slow_moral_case(
    config: dict,
    *,
    iterations: int,
    text: str,
) -> dict:
    from moral_repair_engine import MoralRepairState

    plugin = new_plugin(config)
    await _bind_fast_state_hooks(plugin)
    plugin._last_request_text["bench-session"] = "cached request context"

    async def slow_assessor(self, **kwargs):
        await asyncio.sleep(0.02)
        return fake_observation()

    async def slow_moral(self, session_key):
        await asyncio.sleep(0.02)
        return MoralRepairState.initial()

    bind_async(plugin, "_assess_emotion", slow_assessor)
    bind_async(plugin, "_load_moral_repair_state", slow_moral)
    samples: list[float] = []
    for _ in range(iterations):
        response = SimpleNamespace(completion_text=text)
        started = time.perf_counter()
        await plugin.on_llm_response(FakeEvent("bench-session"), response)
        samples.append((time.perf_counter() - started) * 1000.0)
    return _summarize(samples)


async def _run_slow_assessor_case(config: dict, *, iterations: int, text: str) -> dict:
    from main import EmotionalStatePlugin

    plugin = new_plugin(config)
    await _bind_fast_state_hooks(plugin)
    plugin._last_request_text["bench-session"] = "cached request context"
    plugin._assess_emotion = EmotionalStatePlugin._assess_emotion.__get__(
        plugin,
        type(plugin),
    )

    async def fake_provider_id(self, event):
        return "slow-provider"

    async def slow_llm_generate(**kwargs):
        await asyncio.sleep(0.2)
        return SimpleNamespace(completion_text='{"label":"late"}')

    bind_async(plugin, "_provider_id", fake_provider_id)
    plugin.context = SimpleNamespace(llm_generate=slow_llm_generate)
    samples: list[float] = []
    for _ in range(iterations):
        response = SimpleNamespace(completion_text=text)
        started = time.perf_counter()
        await plugin.on_llm_response(FakeEvent("bench-session"), response)
        samples.append((time.perf_counter() - started) * 1000.0)
    return _summarize(samples)


async def _run_memory_slow_snapshot_case(config: dict, *, iterations: int) -> dict:
    plugin = new_plugin(config)

    async def slow_snapshot(kind):
        await asyncio.sleep(0.02)
        return {
            "schema_version": f"astrbot.{kind}.v1",
            "kind": kind,
            "enabled": True,
            "session_key": "bench-session",
            "values": {},
        }

    async def fake_humanlike(*args, **kwargs):
        return await slow_snapshot("humanlike_state")

    async def fake_lifelike(*args, **kwargs):
        return await slow_snapshot("lifelike_learning_state")

    async def fake_drift(*args, **kwargs):
        return await slow_snapshot("personality_drift_state")

    async def fake_moral(*args, **kwargs):
        return await slow_snapshot("moral_repair_state")

    plugin.get_humanlike_snapshot = fake_humanlike
    plugin.get_lifelike_learning_snapshot = fake_lifelike
    plugin.get_personality_drift_snapshot = fake_drift
    plugin.get_moral_repair_snapshot = fake_moral
    samples: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter()
        await plugin.build_emotion_memory_payload(
            session_key="bench-session",
            source="livingmemory",
            include_raw_snapshot=False,
        )
        samples.append((time.perf_counter() - started) * 1000.0)
    return _summarize(samples)


def _summarize(samples: list[float]) -> dict:
    ordered = sorted(samples)
    return {
        "iterations": len(samples),
        "mean_ms": round(statistics.fmean(samples), 3),
        "p50_ms": round(ordered[len(ordered) // 2], 3),
        "p95_ms": round(ordered[max(0, int(len(ordered) * 0.95) - 1)], 3),
        "max_ms": round(max(samples), 3),
    }


async def main() -> int:
    install_astrbot_stubs()
    iterations = 200
    cases = {
        "request_default_post_inject": await _run_request_case(
            {"assessment_timing": "post"},
            iterations=iterations,
            prompt="hello",
        ),
        "request_no_request_work": await _run_request_case(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_humanlike_state": False,
                "enable_lifelike_learning": False,
                "enable_moral_repair_state": False,
                "enable_personality_drift": False,
            },
            iterations=iterations,
            prompt="hello",
        ),
        "request_optional_modules_enabled": await _run_request_case(
            {
                "assessment_timing": "post",
                "enable_humanlike_state": True,
                "enable_lifelike_learning": True,
                "enable_moral_repair_state": True,
                "enable_personality_drift": True,
                "humanlike_injection_strength": 0.0,
                "lifelike_learning_injection_strength": 0.0,
                "moral_repair_injection_strength": 0.0,
                "personality_drift_injection_strength": 0.0,
            },
            iterations=iterations,
            prompt="hello",
        ),
        "request_slow_aux_load_fanout": await _run_request_slow_aux_case(
            {
                "assessment_timing": "post",
                "enable_humanlike_state": True,
                "enable_lifelike_learning": True,
                "enable_moral_repair_state": True,
                "humanlike_injection_strength": 0.0,
                "lifelike_learning_injection_strength": 0.0,
                "moral_repair_injection_strength": 0.0,
            },
            iterations=20,
            prompt="sorry, 桥隧猫 means bridge tunnel friend",
        ),
        "response_post_assessment": await _run_response_case(
            {"assessment_timing": "post"},
            iterations=iterations,
            text="assistant response",
        ),
        "response_slow_moral_load_fanout": await _run_response_slow_moral_case(
            {
                "assessment_timing": "post",
                "enable_moral_repair_state": True,
            },
            iterations=20,
            text="assistant response sorry repair",
        ),
        "response_slow_assessor_timeout_guard": await _run_slow_assessor_case(
            {"assessment_timing": "post", "assessor_timeout_seconds": 0.05},
            iterations=20,
            text="assistant response",
        ),
        "memory_slow_snapshot_fanout": await _run_memory_slow_snapshot_case(
            {},
            iterations=20,
        ),
    }
    for name, summary in cases.items():
        metrics = " ".join(f"{key}={value}" for key, value in summary.items())
        print(f"{name}: {metrics}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
