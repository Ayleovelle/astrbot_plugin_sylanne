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


class AstrBotLifecyclePart04(AstrBotLifecycleTests):
    def test_background_post_commit_failure_retries_and_preserves_following_order(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "background_post_assessment": True,
                "background_post_queue_checkpoint_enabled": True,
                "enable_dynamic_background_workers": True,
                "background_post_retry_base_delay_seconds": 0.0,
                "background_post_retry_max_attempts": 3,
            },
        )
        saves, _ = self._bind_common_state_hooks(plugin)
        stored = {}
        save_attempts = []

        async def fake_put_kv(self, key, value):
            stored[key] = value

        async def fake_delete_kv(self, key):
            stored.pop(key, None)

        async def fake_save_state(self, session_key, state):
            save_attempts.append(state.label)
            if state.label == "reply-1" and save_attempts.count("reply-1") == 1:
                raise RuntimeError("commit failed")
            saves.append((session_key, state))

        bind_async(plugin, "put_kv_data", fake_put_kv)
        bind_async(plugin, "delete_kv_data", fake_delete_kv)
        bind_async(plugin, "_save_state", fake_save_state)

        async def label_assess(self, **kwargs):
            return fake_observation(kwargs["current_text"])

        bind_async(plugin, "_assess_emotion", label_assess)

        async def run_retry():
            for index in range(1, 4):
                plugin._last_request_text["s-commit-retry"] = f"ctx-{index}"
                await plugin.on_llm_response(
                    FakeEvent("s-commit-retry"),
                    SimpleNamespace(completion_text=f"reply-{index}"),
                )
            task = next(iter(plugin._background_tasks))
            await asyncio.wait_for(task, timeout=1.0)

        asyncio.run(run_retry())

        self.assertEqual(
            save_attempts,
            ["reply-1", "reply-1", "reply-2", "reply-3"],
        )
        self.assertEqual(
            [state.label for _, state in saves],
            ["reply-1", "reply-2", "reply-3"],
        )
        self.assertEqual(plugin._background_post_last_committed["s-commit-retry"], 3)
        self.assertEqual(plugin._background_post_queues, {})
        self.assertEqual(plugin._background_post_active, {})
        self.assertNotIn(
            plugin._background_post_checkpoint_kv_key("s-commit-retry"),
            stored,
        )


    def test_background_post_failure_dead_letters_after_retry_limit(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "background_post_assessment": True,
                "background_post_queue_checkpoint_enabled": True,
                "background_post_retry_base_delay_seconds": 0.0,
                "background_post_retry_max_attempts": 2,
            },
        )
        self._bind_common_state_hooks(plugin)

        async def fail_assess(self, **kwargs):
            raise RuntimeError("assessor down")

        bind_async(plugin, "_assess_emotion", fail_assess)

        async def run_dead_letter():
            plugin._last_request_text["s-dead"] = "secret ctx"
            await plugin.on_llm_response(
                FakeEvent("s-dead", message="secret user text"),
                SimpleNamespace(completion_text="secret reply"),
            )
            await asyncio.wait_for(next(iter(plugin._background_tasks)), timeout=1.0)
            return await plugin.get_agent_runtime_diagnostics("s-dead")

        diagnostics = asyncio.run(run_dead_letter())
        bg = diagnostics["background_post_assessment"]

        self.assertEqual(bg["dead_letter_count"], 1)
        self.assertEqual(bg["warning_level"], "error")
        self.assertIn("dead_letter", bg["warnings"])
        self.assertEqual(bg["dead_letters"][0]["sequence"], 1)
        self.assertEqual(bg["dead_letters"][0]["attempts"], 2)
        serialized = str(bg)
        self.assertNotIn("secret user text", serialized)
        self.assertNotIn("secret reply", serialized)
        self.assertNotIn("secret ctx", serialized)


    def test_background_post_checkpoint_v2_preserves_retry_and_dead_letter_metadata(self):
        plugin = new_plugin({"background_post_queue_checkpoint_enabled": True})
        stored = {}

        async def fake_put_kv(self, key, value):
            stored[key] = value

        async def fake_get_kv(self, key, default=None):
            return stored.get(key, default)

        bind_async(plugin, "put_kv_data", fake_put_kv)
        bind_async(plugin, "get_kv_data", fake_get_kv)
        event = FakeEvent("s-checkpoint-v2", message="user", sender_id="u1")
        identity = plugin._agent_identity(event)
        from main import _BackgroundPostJob

        retrying = _BackgroundPostJob(event, identity, "reply", "ctx", 1, 100.0)
        retrying.attempts = 1
        retrying.next_retry_at = 123.0
        retrying.last_error_type = "RuntimeError"
        retrying.last_error_message = "temporary"
        retrying.last_failed_at = 120.0
        dead = _BackgroundPostJob(event, identity, "dead reply", "dead ctx", 2, 101.0)
        dead.attempts = 3
        dead.last_error_type = "TimeoutError"
        dead.last_failed_at = 130.0
        dead.dead_lettered_at = 131.0
        plugin._background_post_queues["s-checkpoint-v2"] = collections.deque([retrying])
        plugin._background_post_dead_letters["s-checkpoint-v2"] = collections.deque([dead])
        plugin._background_post_sequence["s-checkpoint-v2"] = 2
        plugin._background_post_latest_enqueued["s-checkpoint-v2"] = 2

        async def save_and_recover():
            await plugin._save_background_post_checkpoint("s-checkpoint-v2")
            recovered = new_plugin({"background_post_queue_checkpoint_enabled": True})
            bind_async(recovered, "get_kv_data", fake_get_kv)
            await recovered._recover_background_post_queue("s-checkpoint-v2")
            return recovered

        recovered = asyncio.run(save_and_recover())
        recovered_job = recovered._background_post_queues["s-checkpoint-v2"][0]
        recovered_dead = recovered._background_post_dead_letters["s-checkpoint-v2"][0]

        self.assertEqual(recovered_job.sequence, 1)
        self.assertEqual(recovered_job.attempts, 1)
        self.assertEqual(recovered_job.next_retry_at, 123.0)
        self.assertEqual(recovered_job.last_error_type, "RuntimeError")
        self.assertIsNone(recovered_job.leased_at)
        self.assertIsNone(recovered_job.lease_until)
        self.assertEqual(recovered_dead.sequence, 2)
        self.assertEqual(recovered_dead.attempts, 3)
        self.assertEqual(recovered_dead.last_error_type, "TimeoutError")
        checkpoint = stored[plugin._background_post_checkpoint_kv_key("s-checkpoint-v2")]
        self.assertEqual(checkpoint["schema_version"], "astrbot.background_post_queue.v2")
        self.assertNotIn("response_text", checkpoint["dead_letters"][0])
        self.assertNotIn("request_context_text", checkpoint["dead_letters"][0])


    def test_sylanne_memory_state_uses_dedicated_kv_cache_and_delete(self):
        from memory_engine import MemoryRecord, SylanneMemoryState

        plugin = new_plugin()
        stored = {}

        async def fake_get_kv(self, key, default=None):
            return stored.get(key, default)

        async def fake_put_kv(self, key, value):
            stored[key] = value

        async def fake_delete_kv(self, key):
            stored.pop(key, None)

        bind_async(plugin, "get_kv_data", fake_get_kv)
        bind_async(plugin, "put_kv_data", fake_put_kv)
        bind_async(plugin, "delete_kv_data", fake_delete_kv)
        state = SylanneMemoryState.initial(now=10.0)
        state.records.append(
            MemoryRecord(
                text="用户刚才解释过，他们指插件的其他用户。",
                summary="他们指插件的其他用户。",
                session_key="room/with\\slash",
                created_at=10.0,
                updated_at=10.0,
                depth=0.84,
                confidence=0.75,
            ),
        )

        asyncio.run(plugin._save_sylanne_memory_state("room/with\\slash", state))
        saved_key = plugin._sylanne_memory_kv_key("room/with\\slash")

        self.assertEqual(saved_key, "sylanne_memory_state:room_with_slash")
        self.assertIn(saved_key, stored)
        plugin._sylanne_memory_cache.clear()
        loaded = asyncio.run(plugin._load_sylanne_memory_state("room/with\\slash"))
        self.assertEqual(loaded.records[0].summary, "他们指插件的其他用户。")
        self.assertEqual(plugin._sylanne_memory_cache["room/with\\slash"], loaded)

        asyncio.run(plugin._delete_sylanne_memory_state("room/with\\slash"))

        self.assertNotIn(saved_key, stored)
        self.assertNotIn("room/with\\slash", plugin._sylanne_memory_cache)


    def test_sylanne_memory_load_persists_real_time_forgetting(self):
        from memory_engine import MemoryRecord, SylanneMemoryState

        plugin = new_plugin()
        stored = {}

        async def fake_get_kv(self, key, default=None):
            return stored.get(key, default)

        async def fake_put_kv(self, key, value):
            stored[key] = value

        bind_async(plugin, "get_kv_data", fake_get_kv)
        bind_async(plugin, "put_kv_data", fake_put_kv)
        state = SylanneMemoryState.initial(now=0.0)
        state.dynamics.decay_half_life_seconds = 10.0
        state.records.append(
            MemoryRecord(
                text="一次很弱的临时噪声。",
                summary="临时噪声。",
                session_key="s-forget-kv",
                created_at=0.0,
                updated_at=0.0,
                depth=0.05,
                confidence=0.06,
                auto_parameters={"decay_half_life_seconds": 10.0},
            ),
        )
        stored[plugin._sylanne_memory_kv_key("s-forget-kv")] = state.to_dict()

        loaded = asyncio.run(
            plugin._load_sylanne_memory_state("s-forget-kv", now=120.0),
        )

        saved = stored[plugin._sylanne_memory_kv_key("s-forget-kv")]
        self.assertEqual(loaded.records, [])
        self.assertEqual(saved["records"], [])
        self.assertIn("forgotten=1", saved["dynamics"]["notes"])


    def test_background_post_recovery_merges_checkpoint_before_new_local_job(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "background_post_assessment": True,
                "background_post_queue_checkpoint_enabled": True,
            },
        )
        saves, _ = self._bind_common_state_hooks(plugin)
        stored = {}
        event = FakeEvent("s-merge-recover", message="old user", sender_id="u1")
        identity = plugin._agent_identity(event)
        from main import _BackgroundPostJob

        old_job = _BackgroundPostJob(event, identity, "reply-old", "ctx-old", 1, 100.0)
        stored[plugin._background_post_checkpoint_kv_key("s-merge-recover")] = {
            "schema_version": "astrbot.background_post_queue.v2",
            "session_key": "s-merge-recover",
            "latest_enqueued": 1,
            "last_committed": 0,
            "jobs": [plugin._background_post_job_to_dict(old_job)],
            "dead_letters": [],
        }

        async def fake_get_kv(self, key, default=None):
            return stored.get(key, default)

        async def fake_put_kv(self, key, value):
            stored[key] = value

        async def fake_delete_kv(self, key):
            stored.pop(key, None)

        async def label_assess(self, **kwargs):
            return fake_observation(kwargs["current_text"])

        bind_async(plugin, "get_kv_data", fake_get_kv)
        bind_async(plugin, "put_kv_data", fake_put_kv)
        bind_async(plugin, "delete_kv_data", fake_delete_kv)
        bind_async(plugin, "_assess_emotion", label_assess)

        async def run_merge():
            plugin._last_request_text["s-merge-recover"] = "ctx-new"
            await plugin.on_llm_response(
                FakeEvent("s-merge-recover", message="new user", sender_id="u1"),
                SimpleNamespace(completion_text="reply-new"),
            )
            await asyncio.wait_for(next(iter(plugin._background_tasks)), timeout=1.0)

        asyncio.run(run_merge())

        self.assertEqual(
            [state.label.rsplit("\n", 1)[-1] for key, state in saves if key == "s-merge-recover"],
            ["reply-old", "reply-new"],
        )
        self.assertEqual(plugin._background_post_last_committed["s-merge-recover"], 2)
        self.assertNotIn(
            plugin._background_post_checkpoint_kv_key("s-merge-recover"),
            stored,
        )


    def test_background_post_recovery_retries_after_transient_kv_failure(self):
        plugin = new_plugin({"background_post_queue_checkpoint_enabled": True})
        event = FakeEvent("s-recover-retry", sender_id="u1")
        identity = plugin._agent_identity(event)
        from main import _BackgroundPostJob

        old_job = _BackgroundPostJob(event, identity, "reply-old", "ctx-old", 1, 100.0)
        checkpoint = {
            "schema_version": "astrbot.background_post_queue.v2",
            "session_key": "s-recover-retry",
            "latest_enqueued": 1,
            "last_committed": 0,
            "jobs": [plugin._background_post_job_to_dict(old_job)],
            "dead_letters": [],
        }
        calls = 0

        async def flaky_get_kv(self, key, default=None):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("temporary kv failure")
            return checkpoint

        bind_async(plugin, "get_kv_data", flaky_get_kv)

        async def recover_twice():
            first = await plugin._recover_background_post_queue("s-recover-retry")
            second = await plugin._recover_background_post_queue("s-recover-retry")
            return first, second

        first, second = asyncio.run(recover_twice())

        self.assertFalse(first)
        self.assertTrue(second)
        self.assertEqual(calls, 2)
        self.assertEqual(
            [job.sequence for job in plugin._background_post_queues["s-recover-retry"]],
            [1],
        )


    def test_terminate_saves_final_background_post_checkpoint(self):
        plugin = new_plugin({"background_post_queue_checkpoint_enabled": True})
        stored = {}
        event = FakeEvent("s-terminate-final", sender_id="u1")
        identity = plugin._agent_identity(event)
        from main import _BackgroundPostJob

        plugin._background_post_recovered_sessions.add("s-terminate-final")
        plugin._background_post_queues["s-terminate-final"] = collections.deque(
            [
                _BackgroundPostJob(event, identity, "reply-final", "ctx-final", 1, 100.0),
            ],
        )
        plugin._background_post_sequence["s-terminate-final"] = 1
        plugin._background_post_latest_enqueued["s-terminate-final"] = 1

        async def fake_put_kv(self, key, value):
            stored[key] = value

        async def fake_delete_kv(self, key):
            stored.pop(key, None)

        bind_async(plugin, "put_kv_data", fake_put_kv)
        bind_async(plugin, "delete_kv_data", fake_delete_kv)

        asyncio.run(plugin.terminate())

        checkpoint = stored[plugin._background_post_checkpoint_kv_key("s-terminate-final")]
        self.assertEqual(checkpoint["schema_version"], "astrbot.background_post_queue.v2")
        self.assertEqual([item["sequence"] for item in checkpoint["jobs"]], [1])
        self.assertEqual(plugin._background_post_queues, {})


    def test_background_post_expired_lease_requeues_job_in_sequence_order(self):
        plugin = new_plugin({"background_post_job_lease_seconds": 1.0})
        event = FakeEvent("s-lease")
        identity = plugin._agent_identity(event)
        from main import _BackgroundPostJob

        active_one = _BackgroundPostJob(event, identity, "reply-1", "ctx-1", 1, 100.0)
        active_two = _BackgroundPostJob(event, identity, "reply-2", "ctx-2", 2, 101.0)
        for job in (active_one, active_two):
            job.leased_at = 100.0
            job.lease_until = 101.0
        plugin._background_post_active["s-lease"] = {1: active_one, 2: active_two}
        plugin._background_post_queues["s-lease"] = collections.deque()
        plugin.config["benchmark_enable_simulated_time"] = True
        plugin.config["benchmark_time_offset_seconds"] = 1000.0

        recovered_count = plugin._recover_expired_background_post_active("s-lease")

        self.assertEqual(recovered_count, 2)
        self.assertEqual(
            [job.sequence for job in plugin._background_post_queues["s-lease"]],
            [1, 2],
        )


    def test_state_injection_diff_mode_sends_small_no_change_fragment(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "state_injection_detail": "compact",
                "state_injection_compact_mode": "diff",
                "state_injection_diff_force_every_turns": 99,
            },
        )
        self._bind_common_state_hooks(plugin)

        first = fake_request(session_id="s-diff", prompt="hello")
        second = fake_request(session_id="s-diff", prompt="again")

        asyncio.run(plugin.on_llm_request(FakeEvent("s-diff"), first))
        plugin._consume_conversation_pending_response_epoch("s-diff")
        asyncio.run(plugin.on_llm_request(FakeEvent("s-diff"), second))

        first_text = first.extra_user_content_parts[0].text
        second_text = second.extra_user_content_parts[0].text
        self.assertIn('detail="compact"', first_text)
        self.assertIn('detail="diff"', second_text)
        self.assertIn("No material emotion-state change", second_text)
        self.assertLess(len(second_text), len(first_text))


    def test_background_post_queue_limit_drops_oldest_only_when_configured(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "background_post_assessment": True,
                "background_post_queue_limit": 2,
            },
        )
        saves, _ = self._bind_common_state_hooks(plugin)
        release_assessment = asyncio.Event()
        assessment_calls = []

        async def pausing_assess(self, **kwargs):
            assessment_calls.append(kwargs)
            if len(assessment_calls) == 1:
                await release_assessment.wait()
            return fake_observation(kwargs["current_text"])

        bind_async(plugin, "_assess_emotion", pausing_assess)

        async def run_limited_queue():
            plugin._last_request_text["s-queue-limit"] = "ctx-1"
            await plugin.on_llm_response(
                FakeEvent("s-queue-limit"),
                SimpleNamespace(completion_text="reply-1"),
            )
            while not assessment_calls:
                await asyncio.sleep(0)
            for index in range(2, 5):
                plugin._last_request_text["s-queue-limit"] = f"ctx-{index}"
                await plugin.on_llm_response(
                    FakeEvent("s-queue-limit"),
                    SimpleNamespace(completion_text=f"reply-{index}"),
                )
            self.assertEqual(len(plugin._background_post_queues["s-queue-limit"]), 2)
            release_assessment.set()
            await asyncio.wait_for(next(iter(plugin._background_tasks)), timeout=1.0)

        asyncio.run(run_limited_queue())

        self.assertEqual(
            [call["current_text"] for call in assessment_calls],
            ["reply-1", "reply-3", "reply-4"],
        )
        self.assertEqual(
            [state.label for _, state in saves],
            ["reply-1", "reply-3", "reply-4"],
        )


    def test_background_post_assessment_handles_large_burst_with_adaptive_workers(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "background_post_assessment": True,
                "enable_dynamic_background_workers": True,
                "background_post_queue_checkpoint_enabled": False,
            },
        )
        self._bind_background_worker_environment(plugin, now=1000.0)
        saves, _ = self._bind_common_state_hooks(plugin)
        active = 0
        max_active = 0
        assessment_calls = []

        async def tracked_assess(self, **kwargs):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            assessment_calls.append(kwargs["current_text"])
            await asyncio.sleep(0)
            active -= 1
            return fake_observation(kwargs["current_text"])

        bind_async(plugin, "_assess_emotion", tracked_assess)

        async def run_burst():
            for index in range(50):
                plugin._last_request_text["s-pressure"] = f"ctx-{index}"
                await plugin.on_llm_response(
                    FakeEvent("s-pressure"),
                    SimpleNamespace(completion_text=f"reply-{index:02d}"),
                )
            diagnostics = await plugin.get_agent_runtime_diagnostics("s-pressure")
            bg = diagnostics["background_post_assessment"]
            self.assertEqual(bg["worker_policy"], "adaptive_resource_guarded_pressure")
            self.assertGreaterEqual(bg["max_workers"], 1)
            self.assertLessEqual(
                bg["active_workers"],
                bg["worker_global_cap"],
            )
            await asyncio.wait_for(next(iter(plugin._background_tasks)), timeout=2.0)

        asyncio.run(run_burst())

        self.assertEqual(len(assessment_calls), 50)
        self.assertEqual(
            [state.label for _, state in saves],
            [f"reply-{index:02d}" for index in range(50)],
        )
        self.assertGreater(max_active, 1)
        self.assertLessEqual(max_active, 6)
        diagnostics = asyncio.run(plugin.get_agent_runtime_diagnostics("s-pressure"))
        bg = diagnostics["background_post_assessment"]
        self.assertEqual(bg["lag_count"], 0)
        self.assertEqual(bg["state_lag_count"], 0)
        self.assertEqual(bg["latest_enqueued"], 50)
        self.assertEqual(bg["last_committed"], 50)


    def test_background_post_checkpoint_recovers_uncommitted_queue(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "background_post_assessment": True,
                "background_post_queue_checkpoint_enabled": True,
            },
        )
        saves, _ = self._bind_common_state_hooks(plugin)
        stored = {}

        async def fake_put_kv(self, key, value):
            stored[key] = value

        async def fake_get_kv(self, key, default=None):
            return stored.get(key, default)

        async def fake_delete_kv(self, key):
            stored.pop(key, None)

        bind_async(plugin, "put_kv_data", fake_put_kv)
        bind_async(plugin, "get_kv_data", fake_get_kv)
        bind_async(plugin, "delete_kv_data", fake_delete_kv)
        event = FakeEvent(
            "s-recover",
            message="user message",
            sender_id="user-a",
            sender_name="Alice",
        )
        identity = plugin._agent_identity(event)
        from main import _BackgroundPostJob

        plugin._background_post_queues["s-recover"] = collections.deque(
            [
                _BackgroundPostJob(event, identity, "reply-1", "ctx-1", 1, 100.0),
                _BackgroundPostJob(event, identity, "reply-2", "ctx-2", 2, 101.0),
            ],
        )
        plugin._background_post_sequence["s-recover"] = 2
        plugin._background_post_latest_enqueued["s-recover"] = 2

        async def save_then_recover():
            await plugin._save_background_post_checkpoint("s-recover")
            recovered = new_plugin(
                {
                    "assessment_timing": "post",
                    "background_post_assessment": True,
                    "background_post_queue_checkpoint_enabled": True,
                },
            )
            assessment_calls = []
            self._bind_common_state_hooks(
                recovered,
                saves=saves,
                assessment_calls=assessment_calls,
            )

            async def label_assess(self, **kwargs):
                assessment_calls.append(kwargs)
                return fake_observation(kwargs["current_text"])

            bind_async(recovered, "_assess_emotion", label_assess)
            bind_async(recovered, "put_kv_data", fake_put_kv)
            bind_async(recovered, "get_kv_data", fake_get_kv)
            bind_async(recovered, "delete_kv_data", fake_delete_kv)
            await recovered._recover_background_post_queue("s-recover")
            self.assertEqual(len(recovered._background_post_queues["s-recover"]), 2)
            task = recovered._schedule_background_task(
                recovered._drain_background_post_assessments("s-recover"),
                label="recover-test",
            )
            recovered._background_post_tasks["s-recover"] = task
            await asyncio.wait_for(task, timeout=1.0)
            return recovered

        recovered = asyncio.run(save_then_recover())

        self.assertEqual(
            [state.label.rsplit("\n", 1)[-1] for _, state in saves],
            ["reply-1", "reply-1", "reply-2", "reply-2"],
        )
        self.assertEqual(recovered._background_post_last_committed["s-recover"], 2)
        self.assertNotIn(
            recovered._background_post_checkpoint_kv_key("s-recover"),
            stored,
        )
