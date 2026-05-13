import asyncio
import collections
import sys
import time
import types
from types import SimpleNamespace

try:
    from tests.astrbot_lifecycle_helpers import (
        AstrBotLifecycleTests,
        FakeEvent,
        bind_async,
        fake_observation,
        fake_request,
        new_plugin,
    )
except ModuleNotFoundError:
    from astrbot_lifecycle_helpers import (
        AstrBotLifecycleTests,
        FakeEvent,
        bind_async,
        fake_observation,
        fake_request,
        new_plugin,
    )


class AstrBotLifecyclePart03(AstrBotLifecycleTests):
    def test_background_post_assessment_returns_without_waiting_for_assessment(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "background_post_assessment": True,
            },
        )
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        completed = asyncio.Event()

        async def slow_assess(self, **kwargs):
            assessment_calls.append(kwargs)
            await asyncio.sleep(0.05)
            return fake_observation()

        bind_async(plugin, "_assess_emotion", slow_assess)
        plugin._last_request_text["s-background-post"] = "cached request context"

        async def run_response_hook():
            started = time.perf_counter()
            await plugin.on_llm_response(
                FakeEvent("s-background-post"),
                SimpleNamespace(completion_text="assistant completion"),
            )
            hook_elapsed = time.perf_counter() - started
            self.assertEqual(saves, [])
            self.assertEqual(len(plugin._background_tasks), 1)
            await asyncio.wait_for(next(iter(plugin._background_tasks)), timeout=1.0)
            completed.set()
            return hook_elapsed

        elapsed = asyncio.run(run_response_hook())

        self.assertLess(elapsed, 0.03)
        self.assertTrue(completed.is_set())
        self.assertEqual(len(saves), 1)
        self.assertEqual(saves[0][0], "s-background-post")
        self.assertEqual(assessment_calls[0]["phase"], "post_response")
        self.assertEqual(assessment_calls[0]["context_text"], "cached request context")


    def test_background_tasks_are_cancelled_on_terminate(self):
        plugin = new_plugin()

        async def never_finishes():
            await asyncio.Event().wait()

        async def run_terminate():
            plugin._schedule_background_task(
                never_finishes(),
                label="unit_test_never_finishes",
            )
            self.assertEqual(len(plugin._background_tasks), 1)
            await plugin.terminate()

        asyncio.run(run_terminate())

        self.assertEqual(plugin._background_tasks, set())
        self.assertEqual(plugin._background_post_tasks, {})
        self.assertEqual(plugin._background_post_queues, {})
        self.assertEqual(plugin._background_post_sequence, {})
        self.assertEqual(plugin._background_post_skipped, {})


    def test_background_post_assessment_freezes_request_context_at_schedule_time(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "background_post_assessment": True,
            },
        )
        self._bind_common_state_hooks(plugin)
        assessment_started = asyncio.Event()
        release_assessment = asyncio.Event()
        assessment_calls = []

        async def pausing_assess(self, **kwargs):
            assessment_calls.append(kwargs)
            assessment_started.set()
            await release_assessment.wait()
            return fake_observation()

        bind_async(plugin, "_assess_emotion", pausing_assess)
        plugin._last_request_text["s-background-race"] = "first request context"

        async def run_response_hook():
            await plugin.on_llm_response(
                FakeEvent("s-background-race"),
                SimpleNamespace(completion_text="assistant completion"),
            )
            await asyncio.wait_for(assessment_started.wait(), timeout=1.0)
            plugin._last_request_text["s-background-race"] = "second request context"
            release_assessment.set()
            await asyncio.wait_for(next(iter(plugin._background_tasks)), timeout=1.0)

        asyncio.run(run_response_hook())

        self.assertEqual(
            assessment_calls[0]["context_text"],
            "first request context",
        )


    def test_background_post_assessment_serializes_same_session_burst_fifo(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "background_post_assessment": True,
            },
        )
        saves = []
        self._bind_common_state_hooks(plugin, saves=saves)
        saves.clear()
        release_assessment = asyncio.Event()
        assessment_calls = []

        async def pausing_assess(self, **kwargs):
            assessment_calls.append(kwargs)
            if len(assessment_calls) == 1:
                await release_assessment.wait()
            return fake_observation(kwargs["current_text"])

        bind_async(plugin, "_assess_emotion", pausing_assess)

        async def run_burst():
            plugin._last_request_text["s-burst"] = "ctx-1"
            await plugin.on_llm_response(
                FakeEvent("s-burst"),
                SimpleNamespace(completion_text="reply-1"),
            )
            while not assessment_calls:
                await asyncio.sleep(0)

            plugin._last_request_text["s-burst"] = "ctx-2"
            await plugin.on_llm_response(
                FakeEvent("s-burst"),
                SimpleNamespace(completion_text="reply-2"),
            )
            plugin._last_request_text["s-burst"] = "ctx-3"
            await plugin.on_llm_response(
                FakeEvent("s-burst"),
                SimpleNamespace(completion_text="reply-3"),
            )

            self.assertEqual(len(plugin._background_tasks), 1)
            self.assertEqual(len(plugin._background_post_tasks), 1)
            self.assertEqual(len(plugin._background_post_queues["s-burst"]), 2)
            release_assessment.set()
            await asyncio.wait_for(next(iter(plugin._background_tasks)), timeout=1.0)

        asyncio.run(run_burst())

        self.assertEqual(
            [call["current_text"] for call in assessment_calls],
            ["reply-1", "reply-2", "reply-3"],
        )
        self.assertEqual(
            [call["context_text"] for call in assessment_calls],
            ["ctx-1", "ctx-2", "ctx-3"],
        )
        self.assertEqual(
            [state.label for _, state in saves],
            ["reply-1", "reply-2", "reply-3"],
        )
        self.assertEqual(plugin._background_tasks, set())
        self.assertEqual(plugin._background_post_tasks, {})
        self.assertEqual(plugin._background_post_queues, {})


    def test_background_post_assessment_keeps_sessions_parallel(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "background_post_assessment": True,
            },
        )
        self._bind_common_state_hooks(plugin)
        release_assessment = asyncio.Event()
        started_sessions = set()

        async def pausing_assess(self, **kwargs):
            started_sessions.add(kwargs["event"].unified_msg_origin)
            await release_assessment.wait()
            return fake_observation(kwargs["current_text"])

        bind_async(plugin, "_assess_emotion", pausing_assess)

        async def run_parallel_sessions():
            plugin._last_request_text["s-a"] = "ctx-a"
            plugin._last_request_text["s-b"] = "ctx-b"
            await plugin.on_llm_response(
                FakeEvent("s-a"),
                SimpleNamespace(completion_text="reply-a"),
            )
            await plugin.on_llm_response(
                FakeEvent("s-b"),
                SimpleNamespace(completion_text="reply-b"),
            )
            while started_sessions != {"s-a", "s-b"}:
                await asyncio.sleep(0)
            self.assertEqual(len(plugin._background_tasks), 2)
            self.assertEqual(len(plugin._background_post_tasks), 2)
            release_assessment.set()
            await asyncio.gather(*list(plugin._background_tasks))

        asyncio.run(run_parallel_sessions())

        self.assertEqual(started_sessions, {"s-a", "s-b"})


    def test_background_post_assessment_parallelizes_same_session_assessments(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "background_post_assessment": True,
                "enable_dynamic_background_workers": True,
            },
        )
        self._bind_background_worker_environment(plugin, now=1000.0)
        saves, _ = self._bind_common_state_hooks(plugin)
        release_assessment = asyncio.Event()
        started_texts = []

        async def pausing_assess(self, **kwargs):
            started_texts.append(kwargs["current_text"])
            await release_assessment.wait()
            return fake_observation(kwargs["current_text"])

        bind_async(plugin, "_assess_emotion", pausing_assess)

        async def run_same_session_workers():
            for index in range(1, 5):
                plugin._last_request_text["s-same-limit"] = f"ctx-{index}"
                await plugin.on_llm_response(
                    FakeEvent("s-same-limit"),
                    SimpleNamespace(completion_text=f"reply-{index}"),
                )
            expected_workers = plugin._background_post_max_workers("s-same-limit")
            while len(started_texts) < expected_workers:
                await asyncio.sleep(0)
            self.assertEqual(
                started_texts,
                [f"reply-{index}" for index in range(1, expected_workers + 1)],
            )
            self.assertEqual(len(plugin._background_tasks), 1)
            self.assertEqual(len(plugin._background_post_tasks), 1)
            release_assessment.set()
            await asyncio.wait_for(next(iter(plugin._background_tasks)), timeout=1.0)

        asyncio.run(run_same_session_workers())

        self.assertEqual(
            started_texts,
            ["reply-1", "reply-2", "reply-3", "reply-4"],
        )
        self.assertEqual(
            [state.label for _, state in saves],
            ["reply-1", "reply-2", "reply-3", "reply-4"],
        )


    def test_background_post_workers_stay_single_without_dynamic_scale(self):
        from main import _BackgroundPostJob

        plugin = new_plugin({"enable_dynamic_background_workers": False})
        self._bind_background_worker_environment(plugin, now=1000.0)
        event = FakeEvent("s-worker-default")
        identity = plugin._agent_identity(event)
        plugin._background_post_queues["s-worker-default"] = collections.deque(
            [
                _BackgroundPostJob(
                    event,
                    identity,
                    f"reply-{index}",
                    f"ctx-{index}",
                    index,
                    time.time(),
                )
                for index in range(1, 40)
            ],
        )

        decision = plugin._background_post_adaptive_worker_decision(
            "s-worker-default",
        )

        self.assertEqual(decision["desired_workers"], 1)
        self.assertEqual(decision["dynamic_extra_workers"], 0)
        self.assertIn("dynamic_scale_disabled", decision["reasons"])
        self.assertTrue(decision["idle_workers_close_automatically"])


    def test_background_post_workers_scale_by_pressure_when_enabled(self):
        from main import _BackgroundPostJob

        plugin = new_plugin({"enable_dynamic_background_workers": True})
        self._bind_background_worker_environment(plugin, now=1000.0)
        event = FakeEvent("s-worker-adaptive")
        identity = plugin._agent_identity(event)

        def set_ready_queue(size):
            plugin._background_post_queues["s-worker-adaptive"] = collections.deque(
                [
                    _BackgroundPostJob(
                        event,
                        identity,
                        f"reply-{index}",
                        f"ctx-{index}",
                        index,
                        time.time(),
                    )
                    for index in range(1, size + 1)
                ],
            )

        for size, expected_target in [(1, 1), (2, 2), (5, 3), (10, 4), (32, 6)]:
            with self.subTest(size=size):
                plugin._background_post_worker_state.clear()
                set_ready_queue(size)
                decision = plugin._background_post_adaptive_worker_decision(
                    "s-worker-adaptive",
                )
                self.assertEqual(decision["queue_target_workers"], expected_target)
                self.assertLessEqual(decision["desired_workers"], 2)
                self.assertGreaterEqual(decision["desired_workers"], 1)
                self.assertEqual(
                    decision["dynamic_extra_workers"],
                    max(0, decision["desired_workers"] - 1),
                )
                self.assertTrue(decision["idle_workers_close_automatically"])


    def test_background_post_workers_ramp_up_in_steps_and_cooldown(self):
        from main import _BackgroundPostJob

        plugin = new_plugin({"enable_dynamic_background_workers": True})
        self._bind_background_worker_environment(plugin, now=1000.0)
        event = FakeEvent("s-worker-ramp")
        identity = plugin._agent_identity(event)
        plugin._background_post_queues["s-worker-ramp"] = collections.deque(
            [
                _BackgroundPostJob(
                    event,
                    identity,
                    f"reply-{index}",
                    f"ctx-{index}",
                    index,
                    900.0,
                )
                for index in range(1, 40)
            ],
        )

        first = plugin._background_post_adaptive_worker_decision(
            "s-worker-ramp",
            commit_scale=True,
        )
        self.assertTrue(first["scale_state"]["committed"])
        second = plugin._background_post_adaptive_worker_decision(
            "s-worker-ramp",
            commit_scale=True,
        )
        plugin._test_now += first["scale_state"]["scale_interval_seconds"] + 0.01
        third = plugin._background_post_adaptive_worker_decision(
            "s-worker-ramp",
            commit_scale=True,
        )

        self.assertEqual(first["queue_target_workers"], 6)
        self.assertEqual(first["desired_workers"], 2)
        self.assertEqual(second["desired_workers"], 2)
        self.assertIn("worker_scale_cooldown", second["reasons"])
        self.assertEqual(third["desired_workers"], 3)
        self.assertIn("worker_scale_step_up", third["reasons"])


    def test_background_post_worker_preview_does_not_commit_scale_state(self):
        from main import _BackgroundPostJob

        plugin = new_plugin({"enable_dynamic_background_workers": True})
        self._bind_background_worker_environment(plugin, now=1000.0)
        event = FakeEvent("s-worker-preview")
        identity = plugin._agent_identity(event)
        plugin._background_post_queues["s-worker-preview"] = collections.deque(
            [
                _BackgroundPostJob(
                    event,
                    identity,
                    f"reply-{index}",
                    f"ctx-{index}",
                    index,
                    900.0,
                )
                for index in range(1, 40)
            ],
        )

        preview = plugin._background_post_adaptive_worker_decision("s-worker-preview")
        self.assertFalse(preview["scale_state"]["committed"])
        self.assertNotIn("s-worker-preview", plugin._background_post_worker_state)

        dispatch_slots = plugin._background_post_max_workers("s-worker-preview")

        self.assertEqual(dispatch_slots, 2)
        self.assertIn("s-worker-preview", plugin._background_post_worker_state)


    def test_background_post_workers_throttle_under_environment_pressure(self):
        from main import _BackgroundPostJob

        plugin = new_plugin({"enable_dynamic_background_workers": True})
        self._bind_background_worker_environment(
            plugin,
            level="high",
            worker_cap=2,
            cpu=0.91,
            memory=0.62,
            now=1000.0,
        )
        event = FakeEvent("s-worker-throttle")
        identity = plugin._agent_identity(event)
        plugin._background_post_queues["s-worker-throttle"] = collections.deque(
            [
                _BackgroundPostJob(
                    event,
                    identity,
                    f"reply-{index}",
                    f"ctx-{index}",
                    index,
                    900.0,
                )
                for index in range(1, 40)
            ],
        )

        decision = plugin._background_post_adaptive_worker_decision(
            "s-worker-throttle",
        )

        self.assertEqual(decision["queue_target_workers"], 6)
        self.assertEqual(decision["target_workers"], 2)
        self.assertLessEqual(decision["desired_workers"], 2)
        self.assertLessEqual(decision["dispatch_workers"], 2)
        self.assertEqual(decision["resource_pressure"]["level"], "high")
        self.assertIn("environment_pressure_high", decision["reasons"])


    def test_background_post_workers_respect_global_worker_budget(self):
        from main import _BackgroundPostJob

        plugin = new_plugin({"enable_dynamic_background_workers": True})
        self._bind_background_worker_environment(plugin, now=1000.0)
        event = FakeEvent("s-worker-budget")
        identity = plugin._agent_identity(event)
        plugin._background_post_active["busy-a"] = {
            index: _BackgroundPostJob(event, identity, "busy", "ctx", index, 990.0)
            for index in range(1, 4)
        }
        plugin._background_post_active["busy-b"] = {
            index: _BackgroundPostJob(event, identity, "busy", "ctx", index + 10, 990.0)
            for index in range(1, 4)
        }
        plugin._background_post_queues["s-worker-budget"] = collections.deque(
            [
                _BackgroundPostJob(
                    event,
                    identity,
                    f"reply-{index}",
                    f"ctx-{index}",
                    index,
                    900.0,
                )
                for index in range(1, 40)
            ],
        )

        decision = plugin._background_post_adaptive_worker_decision(
            "s-worker-budget",
        )

        self.assertEqual(decision["global_worker_cap"], 6)
        self.assertEqual(decision["global_active_other_workers"], 6)
        self.assertEqual(decision["dispatch_workers"], 0)
        self.assertIn("global_worker_budget_exhausted", decision["reasons"])


    def test_background_post_workers_use_conservative_cap_when_environment_unknown(self):
        from main import _BackgroundPostJob

        plugin = new_plugin({"enable_dynamic_background_workers": True})
        self._bind_background_worker_environment(
            plugin,
            level="unknown",
            worker_cap=2,
            cpu=None,
            memory=None,
            now=1000.0,
        )
        event = FakeEvent("s-worker-unknown")
        identity = plugin._agent_identity(event)
        plugin._background_post_queues["s-worker-unknown"] = collections.deque(
            [
                _BackgroundPostJob(
                    event,
                    identity,
                    f"reply-{index}",
                    f"ctx-{index}",
                    index,
                    900.0,
                )
                for index in range(1, 40)
            ],
        )

        decision = plugin._background_post_adaptive_worker_decision(
            "s-worker-unknown",
        )

        self.assertEqual(decision["resource_pressure"]["level"], "unknown")
        self.assertEqual(decision["target_workers"], 2)
        self.assertLessEqual(decision["dispatch_workers"], 2)
        self.assertIn("environment_pressure_unknown", decision["reasons"])


    def test_internal_assessor_llm_concurrency_uses_separate_guard(self):
        from main import _BackgroundPostJob

        plugin = new_plugin({"enable_dynamic_background_workers": True})
        self._bind_background_worker_environment(plugin, now=1000.0)
        event = FakeEvent("s-llm-guard")
        identity = plugin._agent_identity(event)
        plugin._background_post_queues["s-llm-guard"] = collections.deque(
            [
                _BackgroundPostJob(
                    event,
                    identity,
                    f"reply-{index}",
                    f"ctx-{index}",
                    index,
                    time.time(),
                )
                for index in range(1, 6)
            ],
        )

        worker_decision = plugin._background_post_adaptive_worker_decision(
            "s-llm-guard",
        )
        llm_decision = plugin._internal_assessor_llm_concurrency_decision()

        self.assertEqual(worker_decision["queue_target_workers"], 3)
        self.assertLessEqual(worker_decision["desired_workers"], 2)
        self.assertEqual(llm_decision["limit"], 2)
        self.assertEqual(llm_decision["base_limit"], 2)
        self.assertEqual(llm_decision["burst_limit"], 3)
        self.assertIn("base_two_lane_guard", llm_decision["reasons"])

        plugin._background_post_queues["s-llm-guard"] = collections.deque(
            [
                _BackgroundPostJob(
                    event,
                    identity,
                    f"reply-{index}",
                    f"ctx-{index}",
                    index,
                    time.time(),
                )
                for index in range(1, 34)
            ],
        )

        worker_decision = plugin._background_post_adaptive_worker_decision(
            "s-llm-guard",
        )
        llm_decision = plugin._internal_assessor_llm_concurrency_decision()

        self.assertEqual(worker_decision["queue_target_workers"], 6)
        self.assertLessEqual(worker_decision["desired_workers"], 3)
        self.assertEqual(llm_decision["limit"], 3)
        self.assertIn("temporary_extreme_backlog_burst", llm_decision["reasons"])


    def test_internal_assessor_llm_guard_limits_provider_concurrency(self):
        plugin = new_plugin({"enable_dynamic_background_workers": True})
        active = 0
        max_active = 0

        async def fake_generate(**kwargs):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            active -= 1
            return SimpleNamespace(completion_text="{}")

        plugin.context.llm_generate = fake_generate

        async def run_calls():
            await asyncio.gather(
                *(
                    plugin._call_internal_assessor_llm(
                        provider_id="provider",
                        prompt=f"prompt-{index}",
                        system_prompt="system",
                    )
                    for index in range(8)
                ),
            )

        asyncio.run(run_calls())

        self.assertEqual(max_active, 2)
        self.assertEqual(plugin._internal_assessor_llm_inflight, 0)
