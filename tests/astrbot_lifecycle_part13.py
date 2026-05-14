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


class AstrBotLifecyclePart13(AstrBotLifecycleTests):
    def test_realtime_input_fragments_are_injected_as_one_user_turn(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
                "realtime_input_completion_probe_delay_seconds": 0.05,
                "realtime_input_completion_max_wait_seconds": 0.3,
            },
        )
        plugin._observed_now = lambda: 1000.0
        self._bind_common_state_hooks(plugin)
        requests = [
            fake_request(session_id="s-fragments", prompt=text)
            for text in ("你", "是", "🐷", "吗")
        ]

        async def run_fragments():
            tasks = []
            for request, text in zip(requests, ("你", "是", "🐷", "吗")):
                tasks.append(
                    asyncio.create_task(
                        plugin.on_llm_request(
                            FakeEvent("s-fragments", message=text, sender_id="u1"),
                            request,
                        ),
                    ),
                )
                await asyncio.sleep(0.01)
            await asyncio.gather(*tasks)

        asyncio.run(run_fragments())

        first_three = "\n".join(
            "\n".join(self._request_text_parts(request))
            for request in requests[:3]
        )
        final_injected = "\n".join(self._request_text_parts(requests[-1]))
        for request in requests[:3]:
            self.assertTrue(request._sylanne_realtime_input_hold)
        self.assertFalse(getattr(requests[-1], "_sylanne_realtime_input_hold", False))
        self.assertNotIn("sylanne_user_message_fragments", first_three)
        self.assertIn("sylanne_user_message_fragments", final_injected)
        self.assertIn("同一用户在很短时间内分多条发送", final_injected)
        self.assertIn("你 / 是 / 🐷 / 吗", final_injected)
        self.assertIn("merged_intent=你 是 🐷 吗", final_injected)
        self.assertLessEqual(len(final_injected), 520)


    def test_realtime_input_fragments_hold_request_and_skip_emotion_until_merged(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": True,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
                "realtime_input_completion_probe_delay_seconds": 0.05,
                "realtime_input_completion_max_wait_seconds": 0.2,
            },
        )
        clock = {"now": 3000.0}
        plugin._observed_now = lambda: clock["now"]
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        events = [FakeEvent("s-hold-fragments", message=text, sender_id="u1") for text in ("我！", "就！", "是！")]
        requests = [
            fake_request(session_id="s-hold-fragments", prompt=text)
            for text in ("我！", "就！", "是！")
        ]

        async def run_fragments():
            tasks = []
            for event, request in zip(events, requests):
                tasks.append(asyncio.create_task(plugin.on_llm_request(event, request)))
                await asyncio.sleep(0.01)
                clock["now"] += 0.2
            await asyncio.gather(*tasks)

        asyncio.run(run_fragments())

        self.assertTrue(events[0].stopped)
        self.assertTrue(events[1].stopped)
        self.assertFalse(events[2].stopped)
        self.assertTrue(requests[0]._sylanne_realtime_input_hold)
        self.assertTrue(requests[1]._sylanne_realtime_input_hold)
        self.assertEqual(requests[0]._sylanne_default_response_stop_reason, "realtime_input_fragment_waiting")
        self.assertEqual(requests[1]._sylanne_default_response_stop_reason, "realtime_input_fragment_waiting")
        self.assertEqual(len(assessment_calls), 1)
        self.assertGreaterEqual(len(saves), 1)
        self.assertIn("我！ 就！ 是！", assessment_calls[0]["current_text"])
        final_injected = "\n".join(self._request_text_parts(requests[-1]))
        self.assertIn("merged_intent=我！ 就！ 是！", final_injected)


    def test_realtime_input_local_incomplete_waits_beyond_probe_for_continuation(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
                "realtime_input_completion_probe_delay_seconds": 0.03,
                "realtime_input_completion_max_wait_seconds": 0.18,
            },
        )
        clock = {"now": 3300.0}
        plugin._observed_now = lambda: clock["now"]
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        first_event = FakeEvent("s-local-slow-fragments", message="感觉", sender_id="u1")
        second_event = FakeEvent("s-local-slow-fragments", message="你", sender_id="u1")
        first_request = fake_request(session_id="s-local-slow-fragments", prompt="感觉")
        second_request = fake_request(session_id="s-local-slow-fragments", prompt="你")

        async def run_two_fragments():
            first_task = asyncio.create_task(plugin.on_llm_request(first_event, first_request))
            await asyncio.sleep(0.08)
            clock["now"] += 0.8
            second_task = asyncio.create_task(plugin.on_llm_request(second_event, second_request))
            await asyncio.gather(first_task, second_task)

        asyncio.run(run_two_fragments())

        self.assertTrue(first_event.stopped)
        self.assertTrue(first_request._sylanne_realtime_input_hold)
        self.assertEqual(
            first_request._sylanne_default_response_stop_reason,
            "realtime_input_fragment_waiting",
        )
        self.assertEqual(len(assessment_calls), 1)
        self.assertGreaterEqual(len(saves), 1)
        self.assertIn("感觉 你", assessment_calls[0]["current_text"])


    def test_realtime_input_slow_short_phrase_releases_once_at_final_fragment(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
                "realtime_input_completion_probe_delay_seconds": 0.03,
                "realtime_input_completion_max_wait_seconds": 0.22,
            },
        )
        clock = {"now": 3400.0}
        plugin._observed_now = lambda: clock["now"]
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        texts = ["感觉", "你", "骂人", "像在", "撒娇", "宝贝"]
        events = [
            FakeEvent("s-slow-short-phrase", message=text, sender_id="u1")
            for text in texts
        ]
        requests = [
            fake_request(session_id="s-slow-short-phrase", prompt=text)
            for text in texts
        ]

        async def run_fragments():
            tasks = []
            for event, request in zip(events, requests):
                tasks.append(asyncio.create_task(plugin.on_llm_request(event, request)))
                await asyncio.sleep(0.08)
                clock["now"] += 0.8
            await asyncio.gather(*tasks)

        asyncio.run(run_fragments())

        for event in events[:-1]:
            self.assertTrue(event.stopped)
        self.assertFalse(events[-1].stopped)
        for request in requests[:-1]:
            self.assertTrue(request._sylanne_realtime_input_hold)
        self.assertFalse(getattr(requests[-1], "_sylanne_realtime_input_hold", False))
        first_five = "\n".join(
            "\n".join(self._request_text_parts(request))
            for request in requests[:-1]
        )
        final_injected = "\n".join(self._request_text_parts(requests[-1]))
        self.assertNotIn("sylanne_user_message_fragments", first_five)
        self.assertIn("sylanne_user_message_fragments", final_injected)
        self.assertIn("感觉 / 你 / 骂人 / 像在 / 撒娇 / 宝贝", final_injected)
        self.assertIn("merged_intent=感觉 你 骂人 像在 撒娇 宝贝", final_injected)
        self.assertEqual(len(assessment_calls), 1)
        self.assertGreaterEqual(len(saves), 1)
        self.assertIn("感觉 你 骂人 像在 撒娇 宝贝", assessment_calls[0]["current_text"])


    def test_stale_intercepted_reply_keeps_prior_user_turns_for_followup_merge(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "enable_sylanne_memory": False,
                "use_llm_assessor": False,
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 0.0,
            },
        )
        clock = {"now": 10_000.0}
        plugin._observed_now = lambda: clock["now"]
        self._bind_common_state_hooks(plugin)

        async def run_stale_reply_and_followup():
            first = fake_request(
                session_id="s-stale-followup",
                prompt="我论文还没修完捏",
            )
            await plugin.on_llm_request(
                FakeEvent(
                    "s-stale-followup",
                    message="我论文还没修完捏",
                    sender_id="u1",
                    platform_name="aiocqhttp",
                ),
                first,
            )
            clock["now"] += 1.0
            second = fake_request(session_id="s-stale-followup", prompt="得")
            await plugin.on_llm_request(
                FakeEvent(
                    "s-stale-followup",
                    message="得",
                    sender_id="u1",
                    platform_name="aiocqhttp",
                ),
                second,
            )
            stale_event = FakeEvent("s-stale-followup", platform_name="aiocqhttp")
            stale_event._sylanne_input_epoch = 1
            await plugin.on_llm_response(
                stale_event,
                SimpleNamespace(completion_text="现在先闭上眼睛！"),
            )
            clock["now"] += 1.0
            third = fake_request(
                session_id="s-stale-followup",
                prompt="熬夜奋战了",
            )
            await plugin.on_llm_request(
                FakeEvent(
                    "s-stale-followup",
                    message="熬夜奋战了",
                    sender_id="u1",
                    platform_name="aiocqhttp",
                ),
                third,
            )
            return third

        third = asyncio.run(run_stale_reply_and_followup())

        injected = "\n".join(self._request_text_parts(third))
        self.assertIn("sylanne_active_agent_followup_merge", injected)
        self.assertIn("previous_user[1]=我论文还没修完捏", injected)
        self.assertIn("previous_user[2]=得", injected)
        self.assertIn("merged_current_user=我论文还没修完捏 / 得 / 熬夜奋战了", injected)


    def test_stale_reply_without_event_epoch_does_not_poison_next_response(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
                "enable_realtime_chat": False,
                "enable_sylanne_memory": False,
            },
        )
        self._bind_common_state_hooks(plugin)

        async def run_stale_then_current_response():
            await plugin.on_llm_request(
                FakeEvent("s-stale-noevent", message="第一句"),
                fake_request(session_id="s-stale-noevent", prompt="第一句"),
            )
            await plugin.on_llm_request(
                FakeEvent("s-stale-noevent", message="第二句"),
                fake_request(session_id="s-stale-noevent", prompt="第二句"),
            )
            stale = SimpleNamespace(completion_text="第一句的旧回复")
            await plugin.on_llm_response(FakeEvent("s-stale-noevent"), stale)
            current = SimpleNamespace(completion_text="第二句的当前回复")
            await plugin.on_llm_response(FakeEvent("s-stale-noevent"), current)
            return stale, current

        stale, current = asyncio.run(run_stale_then_current_response())

        self.assertEqual(stale.completion_text, "")
        self.assertEqual(current.completion_text, "第二句的当前回复")
        self.assertNotIn("s-stale-noevent", plugin._conversation_pending_response_epochs)


    def test_stale_reply_without_event_epoch_still_merges_prior_user_turns(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "enable_sylanne_memory": False,
                "use_llm_assessor": False,
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 0.0,
            },
        )
        clock = {"now": 10_000.0}
        plugin._observed_now = lambda: clock["now"]
        self._bind_common_state_hooks(plugin)

        async def run_followup_after_unstamped_stale_reply():
            await plugin.on_llm_request(
                FakeEvent(
                    "s-stale-noevent-merge",
                    message="我论文还没修完捏",
                    sender_id="u1",
                    platform_name="aiocqhttp",
                ),
                fake_request(
                    session_id="s-stale-noevent-merge",
                    prompt="我论文还没修完捏",
                ),
            )
            clock["now"] += 1.0
            await plugin.on_llm_request(
                FakeEvent(
                    "s-stale-noevent-merge",
                    message="得",
                    sender_id="u1",
                    platform_name="aiocqhttp",
                ),
                fake_request(session_id="s-stale-noevent-merge", prompt="得"),
            )
            stale = SimpleNamespace(completion_text="旧回复")
            await plugin.on_llm_response(
                FakeEvent("s-stale-noevent-merge", platform_name="aiocqhttp"),
                stale,
            )
            clock["now"] += 1.0
            third = fake_request(
                session_id="s-stale-noevent-merge",
                prompt="熬夜奋战了",
            )
            await plugin.on_llm_request(
                FakeEvent(
                    "s-stale-noevent-merge",
                    message="熬夜奋战了",
                    sender_id="u1",
                    platform_name="aiocqhttp",
                ),
                third,
            )
            return third

        third = asyncio.run(run_followup_after_unstamped_stale_reply())

        injected = "\n".join(self._request_text_parts(third))
        self.assertIn("sylanne_active_agent_followup_merge", injected)
        self.assertIn("previous_user[1]=我论文还没修完捏", injected)
        self.assertIn("previous_user[2]=得", injected)
        self.assertIn("merged_current_user=我论文还没修完捏 / 得 / 熬夜奋战了", injected)


    def test_realtime_input_llm_gate_can_release_complete_short_fragment(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": True,
                "realtime_input_completion_llm_gate_enabled": True,
                "fast_assessor_enabled": True,
                "fast_assessor_provider_id": "fast-json-provider",
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 0.01,
            },
        )
        plugin._observed_now = lambda: 4000.0
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        calls = []

        async def fake_provider_id(self, event):
            return "provider"

        async def fake_call_llm(self, *, provider_id, prompt, system_prompt):
            calls.append((provider_id, prompt, system_prompt))
            return SimpleNamespace(
                completion_text='{"is_complete": true, "confidence": 0.91, "reason": "完整强调"}',
            )

        bind_async(plugin, "_provider_id", fake_provider_id)
        bind_async(plugin, "_call_internal_assessor_llm", fake_call_llm)
        event = FakeEvent("s-llm-release", message="我！", sender_id="u1")
        request = fake_request(session_id="s-llm-release", prompt="我！")

        asyncio.run(plugin.on_llm_request(event, request))

        self.assertFalse(event.stopped)
        self.assertFalse(getattr(request, "_sylanne_realtime_input_hold", False))
        self.assertEqual(plugin._realtime_input_fragment_windows, {})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "fast-json-provider")
        self.assertEqual(len(assessment_calls), 1)
        self.assertGreaterEqual(len(saves), 1)


    def test_fast_assessor_provider_is_opt_in_when_fast_unset(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": True,
                "emotion_provider_id": "judge-provider",
                "fast_assessor_enabled": True,
                "realtime_input_completion_llm_gate_enabled": True,
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 0.01,
            },
        )
        plugin._observed_now = lambda: 4010.0
        self._bind_common_state_hooks(plugin)
        calls = []

        async def fake_call_llm(self, *, provider_id, prompt, system_prompt):
            calls.append((provider_id, prompt, system_prompt))
            return SimpleNamespace(
                completion_text='{"is_complete": true, "confidence": 0.91, "reason": "完整短句"}',
            )

        bind_async(plugin, "_call_internal_assessor_llm", fake_call_llm)
        event = FakeEvent("s-llm-release-fallback", message="我！", sender_id="u1")
        request = fake_request(session_id="s-llm-release-fallback", prompt="我！")

        asyncio.run(plugin.on_llm_request(event, request))

        self.assertFalse(event.stopped)
        self.assertEqual(calls, [])


    def test_realtime_input_fast_assessor_prompt_uses_short_context_budget(self):
        plugin = new_plugin(
            {
                "enable_realtime_chat": True,
                "use_llm_assessor": True,
                "fast_assessor_enabled": True,
                "fast_assessor_provider_id": "fast-json-provider",
                "fast_assessor_max_context_chars": 260,
            },
        )
        payload = {
            "fragments": ["我只是想补充一下", "这段特别长" + "x" * 1200],
            "merged_intent": "我只是想补充一下 " + "y" * 1200,
        }

        prompt = plugin._build_realtime_input_completion_prompt(
            payload,
            max_chars=plugin._fast_assessor_max_context_chars(),
        )

        self.assertLessEqual(len(prompt), 260)
        self.assertIn("只输出 JSON", prompt)


    def test_realtime_input_complete_llm_gate_skips_remaining_max_wait(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": True,
                "realtime_input_completion_llm_gate_enabled": True,
                "fast_assessor_enabled": True,
                "fast_assessor_provider_id": "provider",
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 4.0,
            },
        )
        plugin._observed_now = lambda: 4050.0
        self._bind_common_state_hooks(plugin)
        waits = []

        async def fake_provider_id(self, event):
            return "provider"

        async def fake_call_llm(self, *, provider_id, prompt, system_prompt):
            return SimpleNamespace(
                completion_text='{"is_complete": true, "confidence": 0.96, "reason": "已经完整"}',
            )

        async def fake_wait(self, session_key, payload, wait_seconds):
            waits.append(wait_seconds)
            return True

        bind_async(plugin, "_provider_id", fake_provider_id)
        bind_async(plugin, "_call_internal_assessor_llm", fake_call_llm)
        bind_async(plugin, "_wait_realtime_input_window_unchanged", fake_wait)
        event = FakeEvent("s-llm-release-fast", message="我！", sender_id="u1")
        request = fake_request(session_id="s-llm-release-fast", prompt="我！")

        asyncio.run(plugin.on_llm_request(event, request))

        self.assertFalse(event.stopped)
        self.assertEqual(waits, [0.0])
        self.assertEqual(plugin._realtime_input_fragment_windows, {})


    def test_realtime_input_llm_gate_releases_incomplete_fragment_after_max_wait(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": True,
                "realtime_input_completion_llm_gate_enabled": True,
                "fast_assessor_enabled": True,
                "fast_assessor_provider_id": "provider",
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 0.02,
            },
        )
        plugin._observed_now = lambda: 4100.0
        saves, assessment_calls = self._bind_common_state_hooks(plugin)

        async def fake_provider_id(self, event):
            return "provider"

        async def fake_call_llm(self, *, provider_id, prompt, system_prompt):
            return SimpleNamespace(
                completion_text='{"is_complete": false, "confidence": 0.88, "reason": "还在铺垫"}',
            )

        bind_async(plugin, "_provider_id", fake_provider_id)
        bind_async(plugin, "_call_internal_assessor_llm", fake_call_llm)
        event = FakeEvent("s-llm-hold", message="我！", sender_id="u1")
        request = fake_request(session_id="s-llm-hold", prompt="我！")

        asyncio.run(plugin.on_llm_request(event, request))

        self.assertFalse(event.stopped)
        self.assertFalse(getattr(request, "_sylanne_realtime_input_hold", False))
        self.assertEqual(len(assessment_calls), 1)
        self.assertGreaterEqual(len(saves), 1)
        injected = "\n".join(self._request_text_parts(request))
        self.assertNotIn("sylanne_user_message_fragments", injected)
        self.assertIn("我！", assessment_calls[0]["current_text"])


    def test_realtime_input_llm_gate_stops_old_fragment_when_user_continues(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": True,
                "realtime_input_completion_llm_gate_enabled": True,
                "fast_assessor_enabled": True,
                "fast_assessor_provider_id": "provider",
                "realtime_input_completion_probe_delay_seconds": 0.05,
                "realtime_input_completion_max_wait_seconds": 0.2,
            },
        )
        plugin._observed_now = lambda: 4200.0
        saves, assessment_calls = self._bind_common_state_hooks(plugin)

        async def fake_provider_id(self, event):
            return "provider"

        async def fake_call_llm(self, *, provider_id, prompt, system_prompt):
            return SimpleNamespace(
                completion_text='{"is_complete": false, "confidence": 0.88, "reason": "还在铺垫"}',
            )

        bind_async(plugin, "_provider_id", fake_provider_id)
        bind_async(plugin, "_call_internal_assessor_llm", fake_call_llm)
        first_event = FakeEvent("s-llm-continues", message="我！", sender_id="u1")
        second_event = FakeEvent("s-llm-continues", message="就！", sender_id="u1")
        first_request = fake_request(session_id="s-llm-continues", prompt="我！")
        second_request = fake_request(session_id="s-llm-continues", prompt="就！")

        async def run_two_fragments():
            first_task = asyncio.create_task(plugin.on_llm_request(first_event, first_request))
            await asyncio.sleep(0.01)
            second_task = asyncio.create_task(plugin.on_llm_request(second_event, second_request))
            await asyncio.gather(first_task, second_task)

        asyncio.run(run_two_fragments())

        self.assertTrue(first_event.stopped)
        self.assertTrue(first_request._sylanne_realtime_input_hold)
        self.assertFalse(second_event.stopped)
        self.assertEqual(len(assessment_calls), 1)
        self.assertGreaterEqual(len(saves), 1)


    def test_realtime_input_llm_incomplete_gate_merges_slow_semantic_fragments(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": True,
                "realtime_input_completion_llm_gate_enabled": True,
                "fast_assessor_enabled": True,
                "fast_assessor_provider_id": "provider",
                "realtime_input_completion_probe_delay_seconds": 0.01,
                "realtime_input_completion_max_wait_seconds": 4.0,
            },
        )
        clock = {"now": 6000.0}
        plugin._observed_now = lambda: clock["now"]
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        calls = []

        async def fake_provider_id(self, event):
            return "provider"

        async def fake_call_llm(self, *, provider_id, prompt, system_prompt):
            calls.append((provider_id, prompt, system_prompt))
            complete = "是从哪里看来的" in prompt
            return SimpleNamespace(
                completion_text=(
                    '{"is_complete": true, "confidence": 0.93, "reason": "追问已经完整"}'
                    if complete
                    else '{"is_complete": false, "confidence": 0.92, "reason": "铺垫后还在补充追问"}'
                ),
            )

        bind_async(plugin, "_provider_id", fake_provider_id)
        bind_async(plugin, "_call_internal_assessor_llm", fake_call_llm)
        texts = ["我只是很纳闷", "为啥你要问我", "是从哪里看来的"]
        events = [
            FakeEvent("s-slow-semantic-fragments", message=text, sender_id="u1")
            for text in texts
        ]
        requests = [
            fake_request(session_id="s-slow-semantic-fragments", prompt=text)
            for text in texts
        ]

        async def run_fragments():
            first = asyncio.create_task(plugin.on_llm_request(events[0], requests[0]))
            await asyncio.sleep(0.03)
            clock["now"] += 1.5
            second = asyncio.create_task(plugin.on_llm_request(events[1], requests[1]))
            await asyncio.sleep(0.03)
            clock["now"] += 1.2
            third = asyncio.create_task(plugin.on_llm_request(events[2], requests[2]))
            await asyncio.gather(first, second, third)

        asyncio.run(run_fragments())

        self.assertTrue(events[0].stopped)
        self.assertTrue(events[1].stopped)
        self.assertFalse(events[2].stopped)
        final_injected = "\n".join(self._request_text_parts(requests[-1]))
        self.assertIn("sylanne_user_message_fragments", final_injected)
        self.assertIn("我只是很纳闷 / 为啥你要问我 / 是从哪里看来的", final_injected)
        self.assertIn(
            "merged_intent=我只是很纳闷 为啥你要问我 是从哪里看来的",
            final_injected,
        )
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(assessment_calls), 1)
        self.assertGreaterEqual(len(saves), 1)
