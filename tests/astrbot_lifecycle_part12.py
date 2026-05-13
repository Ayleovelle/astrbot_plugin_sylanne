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


class AstrBotLifecyclePart12(AstrBotLifecycleTests):
    def test_active_agent_followup_merges_pending_user_turn_before_tool_request(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 0.0,
            },
        )
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        first_request = fake_request(
            session_id="s-active-tool-followup",
            prompt="[引用消息] 我得意思是这张图的脸也要相同风格处理 脸的细节太多了 整体不统一",
        )
        second_request = fake_request(
            session_id="s-active-tool-followup",
            prompt="所以图片捏",
        )
        second_request.tools = [
            {
                "type": "function",
                "function": {
                    "name": "aiimg_generate",
                    "description": "generate or edit images",
                    "parameters": {"type": "object"},
                },
            },
        ]

        async def run_followup():
            await plugin.on_llm_request(
                FakeEvent(
                    "s-active-tool-followup",
                    message=(
                        "[引用消息] 我得意思是这张图的脸也要相同风格处理 "
                        "脸的细节太多了 整体不统一"
                    ),
                    sender_id="u1",
                ),
                first_request,
            )
            await plugin.on_llm_request(
                FakeEvent(
                    "s-active-tool-followup",
                    message="所以图片捏",
                    sender_id="u1",
                ),
                second_request,
            )

        asyncio.run(run_followup())

        injected = "\n".join(self._request_text_parts(second_request))
        self.assertIn("sylanne_active_agent_followup_merge", injected)
        self.assertIn("这张图的脸也要相同风格处理", injected)
        self.assertIn("所以图片捏", injected)
        self.assertIn("merged_current_user=", injected)
        self.assertIn("这张图", plugin._last_request_text["s-active-tool-followup"])
        self.assertIn("所以图片捏", plugin._last_request_text["s-active-tool-followup"])
        self.assertGreaterEqual(len(saves), 2)
        self.assertEqual(len(assessment_calls), 2)
        self.assertIn("这张图的脸也要相同风格处理", assessment_calls[-1]["current_text"])
        self.assertIn("所以图片捏", assessment_calls[-1]["current_text"])


    def test_stale_reply_is_kept_as_compact_breakpoint_for_next_turn(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
            },
        )
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        stale_response = SimpleNamespace(
            completion_text="old-answer-start " + ("x" * 1200) + " old-answer-end",
        )

        async def run_interrupt_and_next_turn():
            await plugin.on_llm_request(
                FakeEvent("s-stale-breakpoint", message="first question"),
                fake_request(session_id="s-stale-breakpoint", prompt="first question"),
            )
            await plugin.on_llm_request(
                FakeEvent("s-stale-breakpoint", message="new message interrupts"),
                fake_request(
                    session_id="s-stale-breakpoint",
                    prompt="new message interrupts",
                ),
            )
            await plugin.on_llm_response(
                FakeEvent("s-stale-breakpoint", message="first response wrapper"),
                stale_response,
            )
            next_request = fake_request(
                session_id="s-stale-breakpoint",
                prompt="continue from the new message",
            )
            await plugin.on_llm_request(
                FakeEvent("s-stale-breakpoint", message="continue from the new message"),
                next_request,
            )
            duplicate_request = fake_request(
                session_id="s-stale-breakpoint",
                prompt="another follow up",
            )
            await plugin.on_llm_request(
                FakeEvent("s-stale-breakpoint", message="another follow up"),
                duplicate_request,
            )
            return next_request, duplicate_request

        next_request, duplicate_request = asyncio.run(run_interrupt_and_next_turn())

        injected = "\n".join(self._request_text_parts(next_request))
        duplicate_injected = "\n".join(self._request_text_parts(duplicate_request))
        self.assertEqual(stale_response.completion_text, "")
        self.assertTrue(
            getattr(
                stale_response,
                "_sylanne_intercepted_completion_text",
                "",
            ).startswith("old-answer-start"),
        )
        self.assertEqual(sent, [])
        self.assertIn("sylanne_interrupted_reply_breakpoint", injected)
        self.assertIn("late_llm_response_after_user_message", injected)
        self.assertIn("unsent_count=1", injected)
        self.assertIn("full_hash=", injected)
        breakpoint_text = self._find_text_part(next_request, "sylanne_interrupted_reply_breakpoint")
        self.assertLessEqual(len(breakpoint_text), 900)
        self.assertNotIn("x" * 300, injected)
        self.assertNotIn("...", injected)
        self.assertNotIn("sylanne_interrupted_reply_breakpoint", duplicate_injected)


    def test_realtime_chat_plan_stops_remaining_parts_when_user_interrupts(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin({"enable_sticker_reaction": False})
        plugin.context = FakeContext()
        plugin._conversation_input_epoch = {"s-part-interrupt": 1}
        plan = {
            "session_key": "s-part-interrupt",
            "input_epoch": 1,
            "message_parts": [
                {"index": 0, "text": "第一句", "delay_before_seconds": 0.0},
                {"index": 1, "text": "第二句", "delay_before_seconds": 0.0},
            ],
        }

        original_chain = plugin._build_astrbot_message_chain

        def interrupt_after_first(text):
            message = original_chain(text)
            plugin._conversation_input_epoch["s-part-interrupt"] = 2
            return message

        plugin._build_astrbot_message_chain = interrupt_after_first

        result = asyncio.run(
            plugin._send_realtime_chat_plan(
                FakeEvent("s-part-interrupt"),
                plan,
                source="unit_test",
            ),
        )

        self.assertEqual(len(sent), 1)
        self.assertEqual(result["message_count"], 1)
        self.assertEqual(result["interrupted_reason"], "user_interrupted")
        request = fake_request(session_id="s-part-interrupt", prompt="用户插话")
        appended = plugin._append_interrupted_reply_breakpoint_if_any(
            request,
            "s-part-interrupt",
            budget=None,
        )
        injected = "\n".join(self._request_text_parts(request))
        self.assertTrue(appended)
        self.assertIn("sent_count=1", injected)
        self.assertIn("unsent_count=1", injected)
        self.assertIn("已发送摘要=", injected)
        self.assertIn("未发送开头=", injected)
        self.assertIn("没有完整送达", injected)


    def test_new_request_cancels_sleeping_realtime_dispatch_task(self):
        sent = []
        first_sent = asyncio.Event()

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                first_sent.set()
                return {"ok": True}

        plugin = new_plugin({"enable_realtime_chat": True, "enable_sticker_reaction": False})
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        plugin._conversation_input_epoch = {"s-cancel-sleep": 1}
        plan = {
            "session_key": "s-cancel-sleep",
            "input_epoch": 1,
            "message_parts": [
                {"index": 0, "text": "old first", "delay_before_seconds": 0.0},
                {"index": 1, "text": "old delayed tail", "delay_before_seconds": 30.0},
            ],
        }

        async def run_cancel():
            send_task = asyncio.create_task(
                plugin._send_realtime_chat_plan(
                    FakeEvent("s-cancel-sleep"),
                    plan,
                    source="unit_test",
                ),
            )
            await first_sent.wait()
            await asyncio.sleep(0.12)
            next_request = fake_request(
                session_id="s-cancel-sleep",
                prompt="new message while old reply is sleeping",
            )
            await plugin.on_llm_request(
                FakeEvent("s-cancel-sleep", message="new message while old reply is sleeping"),
                next_request,
            )
            result = await asyncio.wait_for(send_task, timeout=0.25)
            return result, next_request

        result, next_request = asyncio.run(run_cancel())

        injected = "\n".join(self._request_text_parts(next_request))
        self.assertEqual(sent, [("s-cancel-sleep", "message:old first")])
        self.assertEqual(result["message_count"], 1)
        self.assertEqual(result["interrupted_reason"], "user_interrupted")
        self.assertIn("sylanne_realtime_active_dispatch", injected)
        self.assertIn("old first", injected)


    def test_new_request_before_first_chunk_keeps_unsent_reply_context(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin({"enable_realtime_chat": True, "enable_sticker_reaction": False})
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        plugin._conversation_input_epoch = {"s-before-first": 1}
        plan = {
            "session_key": "s-before-first",
            "input_epoch": 1,
            "full_text": "unsent reply mentions plugin users and should remain as context",
            "message_parts": [
                {"index": 0, "text": "unsent reply mentions plugin users", "delay_before_seconds": 30.0},
                {"index": 1, "text": "and should remain as context", "delay_before_seconds": 0.0},
            ],
        }

        async def run_cancel_before_first_chunk():
            send_task = asyncio.create_task(
                plugin._send_realtime_chat_plan(
                    FakeEvent("s-before-first"),
                    plan,
                    source="unit_test",
                ),
            )
            await asyncio.sleep(0.05)
            next_request = fake_request(
                session_id="s-before-first",
                prompt="new user supplement before first chunk",
            )
            await plugin.on_llm_request(
                FakeEvent("s-before-first", message="new user supplement before first chunk"),
                next_request,
            )
            result = await asyncio.wait_for(send_task, timeout=0.25)
            return result, next_request

        result, next_request = asyncio.run(run_cancel_before_first_chunk())

        injected = "\n".join(self._request_text_parts(next_request))
        self.assertEqual(sent, [])
        self.assertEqual(result["message_count"], 0)
        self.assertEqual(result["interrupted_reason"], "user_interrupted")
        self.assertIn("sylanne_realtime_active_dispatch", injected)
        self.assertIn("第一条真正发出前", injected)
        self.assertIn("plugin users", injected)


    def test_zero_sent_interrupted_realtime_reply_becomes_next_turn_breakpoint(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin({"enable_realtime_chat": True, "enable_sticker_reaction": False})
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        plugin._conversation_input_epoch = {"s-zero-breakpoint": 1}
        plan = {
            "session_key": "s-zero-breakpoint",
            "input_epoch": 1,
            "full_text": "unsent intent should survive plugin update",
            "message_parts": [
                {
                    "index": 0,
                    "text": "unsent intent should survive",
                    "delay_before_seconds": 30.0,
                },
                {
                    "index": 1,
                    "text": "plugin update",
                    "delay_before_seconds": 0.0,
                },
            ],
        }

        async def run_zero_sent_interruption():
            send_task = asyncio.create_task(
                plugin._send_realtime_chat_plan(
                    FakeEvent("s-zero-breakpoint"),
                    plan,
                    source="unit_test",
                ),
            )
            await asyncio.sleep(0.05)
            interrupt_request = fake_request(
                session_id="s-zero-breakpoint",
                prompt="new user correction before first chunk",
            )
            await plugin.on_llm_request(
                FakeEvent(
                    "s-zero-breakpoint",
                    message="new user correction before first chunk",
                ),
                interrupt_request,
            )
            result = await asyncio.wait_for(send_task, timeout=0.25)
            next_request = fake_request(
                session_id="s-zero-breakpoint",
                prompt="what did you mean",
            )
            await plugin.on_llm_request(
                FakeEvent("s-zero-breakpoint", message="what did you mean"),
                next_request,
            )
            duplicate_request = fake_request(
                session_id="s-zero-breakpoint",
                prompt="again",
            )
            await plugin.on_llm_request(
                FakeEvent("s-zero-breakpoint", message="again"),
                duplicate_request,
            )
            return result, interrupt_request, next_request, duplicate_request

        result, interrupt_request, next_request, duplicate_request = asyncio.run(
            run_zero_sent_interruption(),
        )

        interrupt_injected = "\n".join(self._request_text_parts(interrupt_request))
        injected = "\n".join(self._request_text_parts(next_request))
        duplicate_injected = "\n".join(self._request_text_parts(duplicate_request))
        self.assertEqual(sent, [])
        self.assertEqual(result["message_count"], 0)
        self.assertEqual(result["interrupted_reason"], "user_interrupted")
        self.assertIn("sylanne_interrupted_reply_breakpoint", interrupt_injected)
        self.assertIn("sent_count=0", interrupt_injected)
        self.assertIn("unsent_count=2", interrupt_injected)
        self.assertIn("unsent intent should survive", interrupt_injected)
        self.assertEqual(interrupt_request.prompt, "new user correction before first chunk")
        self.assertNotIn("sylanne_realtime_assistant_history", injected)
        self.assertNotIn("sylanne_interrupted_reply_breakpoint", duplicate_injected)


    def test_realtime_chat_active_dispatch_is_visible_to_interrupting_request(self):
        sent = []
        first_sent = asyncio.Event()

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                first_sent.set()
                return {"ok": True}

        plugin = new_plugin({"enable_realtime_chat": True, "enable_sticker_reaction": False})
        plugin.context = FakeContext()
        plugin._conversation_input_epoch = {"s-active-interrupt": 1}
        plan = {
            "session_key": "s-active-interrupt",
            "input_epoch": 1,
            "message_parts": [
                {"index": 0, "text": "我理解错了，你说的是插件的其他用户。", "delay_before_seconds": 0.0},
                {"index": 1, "text": "我想对他们说：请先读 README。", "delay_before_seconds": 0.2},
            ],
        }

        async def run_interrupting_request():
            send_task = asyncio.create_task(
                plugin._send_realtime_chat_plan(
                    FakeEvent("s-active-interrupt"),
                    plan,
                    source="unit_test",
                ),
            )
            await first_sent.wait()
            interrupt_request = fake_request(
                session_id="s-active-interrupt",
                prompt="那你有什么想对他们说的吗",
            )
            await plugin.on_llm_request(
                FakeEvent("s-active-interrupt", message="那你有什么想对他们说的吗"),
                interrupt_request,
            )
            plugin._conversation_input_epoch["s-active-interrupt"] = 2
            result = await send_task
            return interrupt_request, result

        interrupt_request, result = asyncio.run(run_interrupting_request())

        injected = "\n".join(self._request_text_parts(interrupt_request))
        self.assertEqual(
            sent,
            [("s-active-interrupt", "message:我理解错了，你说的是插件的其他用户。")],
        )
        self.assertIn("sylanne_realtime_active_dispatch", injected)
        self.assertIn("插件的其他用户", injected)
        self.assertEqual(result["interrupted_reason"], "user_interrupted")


    def test_gemini_followup_tool_request_keeps_prior_image_edit_context(self):
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
            "s-image-edit-followup",
            full_text=(
                "确实，刚才那张图的脸部渲染太写实，和几何色块整体不统一。"
                "我这就把脸也处理成相同的几何抽象风格。"
            ),
            input_epoch=1,
            message_parts=[
                {"text": "刚才那张图的脸部渲染太写实。"},
                {"text": "我这就把脸也处理成相同的几何抽象风格。"},
            ],
            source="unit_test",
        )

        async def fake_get_current_chat_provider_id(*, umo):
            return "哈基米/gemini-3-flash-preview"

        plugin.context = SimpleNamespace(
            get_current_chat_provider_id=fake_get_current_chat_provider_id,
        )
        request = fake_request(
            session_id="s-image-edit-followup",
            prompt="所以图片捏",
        )
        request.tools = [
            {
                "type": "function",
                "function": {
                    "name": "aiimg_generate",
                    "description": "generate or edit images",
                    "parameters": {"type": "object"},
                },
            },
        ]
        request.contexts = [
            {
                "role": "user",
                "content": (
                    "[引用消息] 我得意思是这张图的脸也要相同风格处理 "
                    "脸的细节太多了 你这个整体不统一的"
                ),
            },
        ]

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "s-image-edit-followup",
                    message="所以图片捏",
                    sender_id="u1",
                ),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("sylanne_realtime_assistant_history", injected)
        self.assertIn("刚才那张图", injected)
        self.assertIn("几何抽象风格", injected)
        self.assertNotIn("sylanne_gemini_visible_output_guard", injected)


    def test_realtime_chat_interruption_records_low_token_resume_breakpoint(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_sticker_reaction": False,
            },
        )
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        plugin._conversation_input_epoch = {"s-part-breakpoint": 1}
        plan = {
            "session_key": "s-part-breakpoint",
            "input_epoch": 1,
            "message_parts": [
                {"index": 0, "text": "first part", "delay_before_seconds": 0.0},
                {
                    "index": 1,
                    "text": "second unsent part " + ("y" * 900),
                    "delay_before_seconds": 0.0,
                },
            ],
        }

        original_chain = plugin._build_astrbot_message_chain

        def interrupt_after_first(text):
            message = original_chain(text)
            plugin._conversation_input_epoch["s-part-breakpoint"] = 2
            return message

        async def run_interruption_and_next_turn():
            plugin._build_astrbot_message_chain = interrupt_after_first
            result = await plugin._send_realtime_chat_plan(
                FakeEvent("s-part-breakpoint"),
                plan,
                source="unit_test",
            )
            plugin._build_astrbot_message_chain = original_chain
            next_request = fake_request(
                session_id="s-part-breakpoint",
                prompt="what were you saying",
            )
            await plugin.on_llm_request(
                FakeEvent("s-part-breakpoint", message="what were you saying"),
                next_request,
            )
            return result, next_request

        result, next_request = asyncio.run(run_interruption_and_next_turn())

        injected = "\n".join(self._request_text_parts(next_request))
        self.assertEqual(len(sent), 1)
        self.assertEqual(result["message_count"], 1)
        self.assertEqual(result["interrupted_reason"], "user_interrupted")
        self.assertIn("sylanne_interrupted_reply_breakpoint", injected)
        self.assertIn("sent_count=1", injected)
        self.assertIn("unsent_count=1", injected)
        self.assertIn("unsent_hash=", injected)
        self.assertLessEqual(len(injected), 720)
        self.assertNotIn("y" * 300, injected)
        self.assertNotIn("...", injected)


    def test_interrupted_realtime_reply_becomes_emotion_observation_context(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 0.0,
            },
        )
        saves = []
        assessment_calls = []
        self._bind_common_state_hooks(plugin, saves=saves, assessment_calls=assessment_calls)
        plugin._record_interrupted_reply_breakpoint(
            "s-interrupt-emotion",
            reason="user_interrupted",
            input_epoch=1,
            sent_parts=["我刚才想说"],
            unsent_parts=["后面还没说完"],
            source="unit_test",
        )
        request = fake_request(session_id="s-interrupt-emotion", prompt="不是，我补充一下")

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("s-interrupt-emotion", message="不是，我补充一下", sender_id="u1"),
                request,
            ),
        )

        self.assertEqual(len(assessment_calls), 1)
        current_text = assessment_calls[0]["current_text"]
        self.assertIn("assistant_interrupted_event", current_text)
        self.assertIn("可能带来情绪波动", current_text)
        self.assertIn("不要预设一定是正面或负面", current_text)
        self.assertIn("不是，我补充一下", current_text)
