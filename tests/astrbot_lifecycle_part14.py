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


class AstrBotLifecyclePart14(AstrBotLifecycleTests):
    def test_realtime_input_llm_gate_blocks_premature_emphasis_release_until_complete(self):
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
        clock = {"now": 7000.0}
        plugin._observed_now = lambda: clock["now"]
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        calls = []

        async def fake_provider_id(self, event):
            return "provider"

        async def fake_call_llm(self, *, provider_id, prompt, system_prompt):
            calls.append(prompt)
            complete = "人！！！" in prompt
            return SimpleNamespace(
                completion_text=(
                    '{"is_complete": true, "confidence": 0.97, "reason": "否定句补完为老人"}'
                    if complete
                    else '{"is_complete": false, "confidence": 0.9, "reason": "否定句还没补完"}'
                ),
            )

        bind_async(plugin, "_provider_id", fake_provider_id)
        bind_async(plugin, "_call_internal_assessor_llm", fake_call_llm)
        texts = ["我！", "不！", "是！", "老！", "年", "人！！！"]
        events = [
            FakeEvent("s-emphasis-fragments", message=text, sender_id="u1")
            for text in texts
        ]
        requests = [
            fake_request(session_id="s-emphasis-fragments", prompt=text)
            for text in texts
        ]

        async def run_fragments():
            tasks = []
            for index, (event, request) in enumerate(zip(events, requests)):
                tasks.append(asyncio.create_task(plugin.on_llm_request(event, request)))
                await asyncio.sleep(0.03)
                if index < len(texts) - 1:
                    clock["now"] += [1.5, 1.0, 1.8, 2.4, 1.9][index]
            await asyncio.gather(*tasks)

        asyncio.run(run_fragments())

        for event in events[:-1]:
            self.assertTrue(event.stopped)
        self.assertFalse(events[-1].stopped)
        final_injected = "\n".join(self._request_text_parts(requests[-1]))
        self.assertIn("sylanne_user_message_fragments", final_injected)
        self.assertIn("我！ / 不！ / 是！ / 老！ / 年 / 人！！！", final_injected)
        self.assertIn("merged_intent=我！ 不！ 是！ 老！ 年 人！！！", final_injected)
        self.assertGreaterEqual(len(calls), 4)
        self.assertEqual(len(assessment_calls), 1)
        self.assertGreaterEqual(len(saves), 1)


    def test_realtime_input_llm_incomplete_release_after_max_wait_when_user_stops(self):
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
                "realtime_input_completion_max_wait_seconds": 0.12,
            },
        )
        clock = {"now": 8000.0}
        plugin._observed_now = lambda: clock["now"]
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        calls = []

        async def fake_provider_id(self, event):
            return "provider"

        async def fake_call_llm(self, *, provider_id, prompt, system_prompt):
            calls.append(prompt)
            return SimpleNamespace(
                completion_text=(
                    '{"is_complete": false, "confidence": 0.91, '
                    '"reason": "仍像强调铺垫，但用户没有继续输入"}'
                ),
            )

        bind_async(plugin, "_provider_id", fake_provider_id)
        bind_async(plugin, "_call_internal_assessor_llm", fake_call_llm)
        texts = ["我！", "不！", "是！", "老！", "年", "人！！！"]
        events = [
            FakeEvent("s-incomplete-timeout-release", message=text, sender_id="u1")
            for text in texts
        ]
        requests = [
            fake_request(session_id="s-incomplete-timeout-release", prompt=text)
            for text in texts
        ]

        async def run_fragments():
            tasks = []
            for index, (event, request) in enumerate(zip(events, requests)):
                tasks.append(asyncio.create_task(plugin.on_llm_request(event, request)))
                clock["now"] += 0.4 + index * 0.1
                if index < len(events) - 1:
                    await asyncio.sleep(0.02)
            await asyncio.gather(*tasks)

        asyncio.run(run_fragments())

        self.assertFalse(events[-1].stopped)
        final_injected = "\n".join(self._request_text_parts(requests[-1]))
        self.assertIn("sylanne_user_message_fragments", final_injected)
        self.assertIn("我！ / 不！ / 是！ / 老！ / 年 / 人！！！", final_injected)
        self.assertGreaterEqual(len(calls), 1)
        self.assertEqual(len(assessment_calls), 1)
        self.assertGreaterEqual(len(saves), 1)


    def test_realtime_input_low_signal_followup_does_not_consume_history_shadow(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
            },
        )
        self._bind_common_state_hooks(plugin)
        plugin._record_realtime_assistant_history_shadow(
            "s-low-signal-shadow",
            full_text="刚才说的是插件的其他用户，不是恋爱关系里的别人。",
            input_epoch=1,
            message_parts=[
                {"text": "刚才说的是插件的其他用户。"},
            ],
            source="unit_test",
        )
        low_request = fake_request(session_id="s-low-signal-shadow", prompt="?")
        content_request = fake_request(
            session_id="s-low-signal-shadow",
            prompt="他们会怎么看这个插件",
        )

        async def run_requests():
            await plugin.on_llm_request(
                FakeEvent("s-low-signal-shadow", message="?", sender_id="u1"),
                low_request,
            )
            await plugin.on_llm_request(
                FakeEvent(
                    "s-low-signal-shadow",
                    message="他们会怎么看这个插件",
                    sender_id="u1",
                ),
                content_request,
            )

        asyncio.run(run_requests())

        low_injected = "\n".join(self._request_text_parts(low_request))
        content_injected = "\n".join(self._request_text_parts(content_request))
        self.assertNotIn("sylanne_realtime_assistant_history", low_injected)
        self.assertIn("sylanne_realtime_assistant_history", content_injected)
        self.assertIn("插件的其他用户", content_injected)


    def test_user_correction_suppresses_assistant_history_shadow(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 0.0,
            },
        )
        self._bind_common_state_hooks(plugin)
        plugin._record_realtime_assistant_history_shadow(
            "s-correction-shadow",
            full_text="哼，你是不是又在乱想，我才没有其他用户呢。",
            input_epoch=1,
            message_parts=[{"text": "哼，你是不是又在乱想。"}],
            source="unit_test",
        )
        request = fake_request(
            session_id="s-correction-shadow",
            prompt="不是，我是说插件的其他用户，你是从哪里看来的",
        )

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "s-correction-shadow",
                    message="不是，我是说插件的其他用户，你是从哪里看来的",
                    sender_id="u1",
                ),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("sylanne_user_correction_context", injected)
        self.assertNotIn("sylanne_realtime_assistant_history", injected)
        self.assertIn("优先处理用户纠正", injected)


    def test_followup_clarification_gets_repetition_guard(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
            },
        )
        self._bind_common_state_hooks(plugin)
        plugin._record_realtime_assistant_history_shadow(
            "s-memory-clarification",
            full_text=(
                "原来你说的是那个具体的底层功能呀！那个模块就像我们的共同记忆库，"
                "帮我把琐碎的瞬间都沉淀下来。"
            ),
            input_epoch=1,
            message_parts=[
                {"text": "原来你说的是那个具体的底层功能呀！"},
                {"text": "那个模块就像我们的共同记忆库。"},
            ],
            source="unit_test",
        )
        request = fake_request(
            session_id="s-memory-clarification",
            prompt="我只是想好好确认一下嘛 我给你做的嵌入模型记忆模块",
        )

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "s-memory-clarification",
                    message="我只是想好好确认一下嘛 我给你做的嵌入模型记忆模块",
                    sender_id="u1",
                ),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        context_text = "\n".join(str(item) for item in request.contexts)
        self.assertIn("sylanne_user_correction_context", injected)
        self.assertIn("sylanne_history_reuse_guard", injected)
        self.assertIn("不要复述上一轮", injected)
        self.assertIn("二次澄清", injected)
        self.assertIn("原来你说的是那个具体的底层功能", context_text)


    def test_sleep_fact_correction_suppresses_repeated_no_sleep_guess(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
            },
        )
        self._bind_common_state_hooks(plugin)
        plugin._record_realtime_assistant_history_shadow(
            "s-sleep-correction",
            full_text="五点多的早起和四点多的没睡很难区分，你是刚起床还是根本就没睡呀？",
            input_epoch=1,
            message_parts=[
                {"text": "你是刚起床还是根本就没睡呀？"},
            ],
            source="unit_test",
        )
        request = fake_request(
            session_id="s-sleep-correction",
            prompt="我昨晚十点多睡的啦",
        )

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "s-sleep-correction",
                    message="我昨晚十点多睡的啦",
                    sender_id="u1",
                ),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("sylanne_user_correction_context", injected)
        self.assertIn("我昨晚十点多睡的啦", injected)
        self.assertIn("不要再追问或暗示用户没睡", injected)
        self.assertNotIn("sylanne_realtime_assistant_history", injected)
        context_text = "\n".join(str(item) for item in request.contexts)
        self.assertIn("你是刚起床还是根本就没睡呀？", context_text)


    def test_recent_sleep_correction_is_carried_into_next_fragment_answer(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
            },
        )
        self._bind_common_state_hooks(plugin)
        plugin._record_realtime_assistant_history_shadow(
            "s-sleep-then-thesis",
            full_text="你今天是准备继续改论文，还是单纯来找我撒娇呀？",
            input_epoch=1,
            message_parts=[
                {"text": "你今天是准备继续改论文，还是单纯来找我撒娇呀？"},
            ],
            source="unit_test",
        )
        correction_request = fake_request(
            session_id="s-sleep-then-thesis",
            prompt="我昨晚十点多睡的啦",
        )
        thesis_request = fake_request(
            session_id="s-sleep-then-thesis",
            prompt="我今天打算改论文",
        )

        async def run_requests():
            await plugin.on_llm_request(
                FakeEvent(
                    "s-sleep-then-thesis",
                    message="我昨晚十点多睡的啦",
                    sender_id="u1",
                ),
                correction_request,
            )
            await plugin.on_llm_request(
                FakeEvent(
                    "s-sleep-then-thesis",
                    message="我今天打算改论文",
                    sender_id="u1",
                ),
                thesis_request,
            )

        asyncio.run(run_requests())

        injected = "\n".join(self._request_text_parts(thesis_request))
        self.assertIn("sylanne_active_agent_followup_merge", injected)
        self.assertIn("sylanne_user_correction_context", injected)
        self.assertIn("我昨晚十点多睡的啦", injected)
        self.assertIn("不要再追问或暗示用户没睡", injected)
        self.assertIn("merged_current_user=我昨晚十点多睡的啦 / 我今天打算改论文", injected)
        context_text = "\n".join(str(item) for item in thesis_request.contexts)
        self.assertIn("你今天是准备继续改论文", context_text)


    def test_short_scene_followup_keeps_recent_user_activity_context(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 0.0,
            },
        )
        clock = {"now": 3000.0}
        plugin._observed_now = lambda: clock["now"]
        self._bind_common_state_hooks(plugin)
        first_request = fake_request(
            session_id="s-user-scene-context",
            prompt="正在排队买蜜雪捏",
        )
        second_request = fake_request(
            session_id="s-user-scene-context",
            prompt="不过今天有点热",
        )
        third_request = fake_request(
            session_id="s-user-scene-context",
            prompt="我在外面",
        )

        async def run_scene_turns():
            await plugin.on_llm_request(
                FakeEvent(
                    "s-user-scene-context",
                    message="正在排队买蜜雪捏",
                    sender_id="u1",
                ),
                first_request,
            )
            plugin._discard_conversation_pending_response_epoch(
                "s-user-scene-context",
                1,
            )
            clock["now"] += 12.0
            await plugin.on_llm_request(
                FakeEvent(
                    "s-user-scene-context",
                    message="不过今天有点热",
                    sender_id="u1",
                ),
                second_request,
            )
            plugin._discard_conversation_pending_response_epoch(
                "s-user-scene-context",
                2,
            )
            plugin._record_realtime_assistant_history_shadow(
                "s-user-scene-context",
                full_text="你那边现在是晒得热，还是闷闷的那种热呀？",
                input_epoch=2,
                message_parts=[
                    {"text": "你那边现在是晒得热，还是闷闷的那种热呀？"},
                ],
                source="unit_test",
            )
            clock["now"] += 20.0
            await plugin.on_llm_request(
                FakeEvent(
                    "s-user-scene-context",
                    message="我在外面",
                    sender_id="u1",
                ),
                third_request,
            )

        asyncio.run(run_scene_turns())

        injected = "\n".join(self._request_text_parts(third_request))
        self.assertIn("sylanne_recent_user_scene_context", injected)
        self.assertIn("正在排队买蜜雪捏", injected)
        self.assertIn("不过今天有点热", injected)
        self.assertIn("current_user=我在外面", injected)
        self.assertIn("sylanne_realtime_pending_bot_question", injected)
        self.assertNotIn("sylanne_active_agent_followup_merge", injected)


    def test_short_answer_to_pending_question_skips_fragment_completion_gate(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": True,
                "realtime_input_completion_llm_gate_enabled": True,
                "fast_assessor_provider_id": "provider",
                "realtime_input_completion_probe_delay_seconds": 0.65,
                "realtime_input_completion_max_wait_seconds": 4.0,
            },
        )
        self._bind_common_state_hooks(plugin)
        plugin._record_realtime_assistant_history_shadow(
            "s-short-answer-no-gate",
            full_text="喝了杯什么呀？",
            input_epoch=1,
            message_parts=[{"text": "喝了杯什么呀？"}],
            source="unit_test",
        )
        waits = []

        async def fake_provider_id(self, event):
            return "provider"

        async def fail_call_llm(self, **kwargs):
            raise AssertionError("short answer should not call completion gate")

        async def fake_wait(self, session_key, payload, wait_seconds):
            waits.append(wait_seconds)
            return True

        bind_async(plugin, "_provider_id", fake_provider_id)
        bind_async(plugin, "_call_internal_assessor_llm", fail_call_llm)
        bind_async(plugin, "_wait_realtime_input_window_unchanged", fake_wait)
        request = fake_request(session_id="s-short-answer-no-gate", prompt="咖啡啊")

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("s-short-answer-no-gate", message="咖啡啊", sender_id="u1"),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertFalse(getattr(request, "_sylanne_realtime_input_hold", False))
        self.assertEqual(waits, [])
        self.assertIn("sylanne_realtime_pending_bot_question", injected)
        self.assertIn("current_user_short_answer=咖啡啊", injected)


    def test_realtime_input_fragments_do_not_merge_across_speakers_or_timeout(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
            },
        )
        clock = {"now": 2000.0}
        plugin._observed_now = lambda: clock["now"]
        self._bind_common_state_hooks(plugin)
        first_request = fake_request(session_id="s-fragment-boundary", prompt="你")
        second_request = fake_request(session_id="s-fragment-boundary", prompt="是")
        late_request = fake_request(session_id="s-fragment-boundary", prompt="吗")

        async def run_boundaries():
            await plugin.on_llm_request(
                FakeEvent("s-fragment-boundary", message="你", sender_id="u1"),
                first_request,
            )
            clock["now"] += 0.4
            await plugin.on_llm_request(
                FakeEvent("s-fragment-boundary", message="是", sender_id="u2"),
                second_request,
            )
            clock["now"] += 8.0
            await plugin.on_llm_request(
                FakeEvent("s-fragment-boundary", message="吗", sender_id="u2"),
                late_request,
            )

        asyncio.run(run_boundaries())

        self.assertNotIn(
            "sylanne_user_message_fragments",
            "\n".join(self._request_text_parts(second_request)),
        )
        self.assertNotIn(
            "sylanne_user_message_fragments",
            "\n".join(self._request_text_parts(late_request)),
        )


    def test_observe_user_message_withdrawal_invalidates_pending_output(self):
        plugin = new_plugin()
        plugin._conversation_input_epoch = {"s-withdraw": 1}
        plugin._last_request_text = {"s-withdraw": "错字消息"}
        plugin._proactive_candidate_sessions = {
            "s-withdraw": {
                "session_key": "s-withdraw",
                "unified_msg_origin": "s-withdraw",
                "last_user_text_excerpt": "错字消息",
                "candidate_context_excerpt": "旧上下文",
            },
        }

        result = asyncio.run(
            plugin.observe_user_message_withdrawal(
                session_key="s-withdraw",
                message_id="m-100",
                reason="napcat_friend_recall",
            ),
        )

        self.assertEqual(result["input_epoch"], 2)
        self.assertTrue(plugin._conversation_reply_is_stale("s-withdraw", 1))
        self.assertNotIn("s-withdraw", plugin._last_request_text)
        candidate = plugin._proactive_candidate_sessions["s-withdraw"]
        self.assertEqual(candidate["last_user_text_excerpt"], "")
        self.assertEqual(candidate["last_withdrawn_message_id"], "m-100")


    def test_withdrawal_cancels_sleeping_realtime_dispatch_task(self):
        sent = []
        first_sent = asyncio.Event()

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                first_sent.set()
                return {"ok": True}

        plugin = new_plugin({"enable_realtime_chat": True, "enable_sticker_reaction": False})
        plugin.context = FakeContext()
        plugin._conversation_input_epoch = {"s-withdraw-cancel": 1}
        plan = {
            "session_key": "s-withdraw-cancel",
            "input_epoch": 1,
            "message_parts": [
                {"index": 0, "text": "old first", "delay_before_seconds": 0.0},
                {"index": 1, "text": "old withdrawn tail", "delay_before_seconds": 30.0},
            ],
        }

        async def run_withdrawal_cancel():
            send_task = asyncio.create_task(
                plugin._send_realtime_chat_plan(
                    FakeEvent("s-withdraw-cancel"),
                    plan,
                    source="unit_test",
                ),
            )
            await first_sent.wait()
            await asyncio.sleep(0.12)
            withdrawal = await plugin.observe_user_message_withdrawal(
                session_key="s-withdraw-cancel",
                message_id="m-200",
            )
            result = await asyncio.wait_for(send_task, timeout=0.25)
            return withdrawal, result

        withdrawal, result = asyncio.run(run_withdrawal_cancel())

        self.assertEqual(withdrawal["input_epoch"], 2)
        self.assertEqual(sent, [("s-withdraw-cancel", "message:old first")])
        self.assertEqual(result["message_count"], 1)
        self.assertEqual(result["interrupted_reason"], "user_interrupted")
