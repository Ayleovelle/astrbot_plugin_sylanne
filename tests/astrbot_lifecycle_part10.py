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


class AstrBotLifecyclePart10(AstrBotLifecycleTests):
    def test_on_llm_response_suppresses_sylanne_tool_json_result(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        tool_json = (
            '{"schema_version":"astrbot.emotion_state.v2",'
            '"api_version":"1.0",'
            '"kind":"emotion_state",'
            '"emotion":{"values":{"valence":0.278675}},'
            '"persona":{"name":"小哀同学"}}'
        )
        response = SimpleNamespace(completion_text=tool_json)
        plugin._conversation_input_epoch = {"s-tool-json": 1}
        plugin._record_conversation_pending_response_epoch("s-tool-json", 1)
        event = FakeEvent("s-tool-json", platform_name="aiocqhttp")

        asyncio.run(plugin.on_llm_response(event, response))

        self.assertTrue(event.stopped)
        self.assertEqual(response.completion_text, "")
        self.assertEqual(
            getattr(response, "_sylanne_intercepted_completion_text", ""),
            tool_json,
        )
        self.assertEqual(
            getattr(response, "_sylanne_intercepted_completion_reason", ""),
            "sylanne_tool_json_result_suppressed",
        )
        self.assertEqual(
            getattr(event, "_sylanne_default_response_stop_reason", ""),
            "sylanne_tool_json_result_suppressed",
        )
        self.assertEqual(sent, [])
        self.assertEqual(
            list(plugin._conversation_pending_response_epochs["s-tool-json"]),
            [1],
        )


    def test_on_llm_response_leaves_structured_role_tool_result_to_agent_loop(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        response = SimpleNamespace(
            role="tool",
            tool_call_id="call_state",
            completion_text='{"kind":"tool_result","content":"internal state only"}',
        )
        plugin._conversation_input_epoch = {"s-role-tool": 1}
        plugin._record_conversation_pending_response_epoch("s-role-tool", 1)
        event = FakeEvent("s-role-tool", platform_name="aiocqhttp")

        asyncio.run(plugin.on_llm_response(event, response))

        self.assertFalse(event.stopped)
        self.assertEqual(
            response.completion_text,
            '{"kind":"tool_result","content":"internal state only"}',
        )
        self.assertFalse(hasattr(response, "_sylanne_intercepted_completion_text"))
        self.assertEqual(sent, [])
        self.assertEqual(
            list(plugin._conversation_pending_response_epochs["s-role-tool"]),
            [1],
        )


    def test_tool_call_response_bypass_preserves_pending_epoch_for_final_reply(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        plugin._conversation_input_epoch = {"s-tool-final": 1}
        plugin._record_conversation_pending_response_epoch("s-tool-final", 1)
        tool_response = SimpleNamespace(
            completion_text="正在调用工具。",
            message=SimpleNamespace(
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "query_sylanne_memory", "arguments": "{}"},
                    },
                ],
            ),
        )
        final_response = SimpleNamespace(completion_text="查到了。第一句。第二句。")
        first_event = FakeEvent("s-tool-final", platform_name="aiocqhttp")
        final_event = FakeEvent("s-tool-final", platform_name="aiocqhttp")

        async def run_turn():
            await plugin.on_llm_response(first_event, tool_response)
            await plugin.on_llm_response(final_event, final_response)
            await self._await_background_tasks(plugin)

        asyncio.run(run_turn())

        self.assertFalse(first_event.stopped)
        self.assertTrue(final_event.stopped)
        self.assertIn("sylanne_realtime_delivery_status", final_response.completion_text)
        self.assertIn("查到了。第一句。第二句。", final_response.completion_text)
        sent_text = "\n".join(item[1] for item in sent)
        self.assertIn("message:查到了。", sent_text)
        self.assertIn("message:第一句。", sent_text)
        self.assertIn("message:第二句。", sent_text)
        self.assertNotIn("s-tool-final", plugin._conversation_pending_response_epochs)


    def test_on_llm_response_intercept_writes_visible_realtime_logs(self):
        import main

        sent = []
        logs = []
        original_logger = main.logger

        class FakeLogger:
            def info(self, message):
                logs.append(str(message))

            def debug(self, message):
                logs.append(str(message))

            def warning(self, message):
                logs.append(str(message))

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        response = SimpleNamespace(completion_text="第一句。第二句。")

        async def run_response():
            await plugin.on_llm_response(
                FakeEvent("s-intercept-log", platform_name="aiocqhttp"),
                response,
            )
            await self._await_background_tasks(plugin)

        try:
            main.logger = FakeLogger()
            asyncio.run(run_response())
        finally:
            main.logger = original_logger

        joined = "\n".join(logs)
        self.assertIn("即时聊天接管主回复", joined)
        self.assertIn("准备分条发送", joined)
        self.assertIn("已发送分条 1/2", joined)
        self.assertIn("分条发送完成", joined)
        self.assertIn("第一句", joined)
        self.assertEqual(len(sent), 2)


    def test_on_llm_response_intercept_preserves_result_chain_images(self):
        from astrbot.api.event import MessageChain

        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message), list(getattr(message, "parts", []))))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        response = SimpleNamespace(
            completion_text="look at this image. it should still arrive.",
            result_chain=MessageChain()
            .message("look at this image. it should still arrive.")
            .file_image("C:/tmp/sylanne-image.png"),
        )

        async def run_response():
            await plugin.on_llm_response(
                FakeEvent("s-intercept-image", platform_name="aiocqhttp"),
                response,
            )
            await self._await_background_tasks(plugin)

        asyncio.run(run_response())

        self.assertIn("sylanne_realtime_delivery_status", response.completion_text)
        self.assertIn("look at this image. it should still arrive.", response.completion_text)
        self.assertEqual(
            getattr(response, "_sylanne_intercepted_completion_text", ""),
            "look at this image. it should still arrive.",
        )
        self.assertTrue(
            any(("file_image", "C:/tmp/sylanne-image.png") in parts for _, _, parts in sent),
        )
        self.assertTrue(
            any(
                kind == "message" and "look at this image" in str(value)
                for _, _, parts in sent
                for kind, value in parts
            ),
        )


    def test_realtime_chat_inserts_result_chain_image_at_text_anchor(self):
        from astrbot.api.event import MessageChain

        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append(list(getattr(message, "parts", [])))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_max_part_chars": 18,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        response = SimpleNamespace(
            completion_text="alpha sentence! beta sentence!",
            result_chain=MessageChain()
            .message("alpha sentence! beta sentence!")
            .file_image("C:/tmp/anchored-image.png"),
        )

        async def run_response():
            await plugin.on_llm_response(
                FakeEvent("s-intercept-image-anchor", platform_name="aiocqhttp"),
                response,
            )
            await self._await_background_tasks(plugin)

        asyncio.run(run_response())

        sent_order = [
            f"{kind}:{value}"
            for parts in sent
            for kind, value in parts
        ]
        self.assertEqual(
            sent_order,
            [
                "message:alpha sentence!",
                "message:beta sentence!",
                "file_image:C:/tmp/anchored-image.png",
            ],
        )


    def test_realtime_chat_sends_pre_text_result_chain_image_first(self):
        from astrbot.api.event import MessageChain

        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append(list(getattr(message, "parts", [])))
                return {"ok": True}

        plugin = new_plugin(
            {
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()
        plan = {
            "session_key": "s-pre-text-media",
            "full_text": "after image!",
            "message_parts": [
                {"index": 0, "text": "after image!", "delay_before_seconds": 0.0},
            ],
            "media_parts": plugin._extract_realtime_response_media_parts(
                SimpleNamespace(
                    result_chain=MessageChain()
                    .file_image("C:/tmp/pre-image.png")
                    .message("after image!"),
                ),
            ),
            "sticker": {"enabled": False, "should_send": False, "reason": "disabled"},
        }

        asyncio.run(
            plugin._send_realtime_chat_plan(
                FakeEvent("s-pre-text-media", platform_name="aiocqhttp"),
                plan,
                source="unit_test",
            ),
        )

        sent_order = [
            f"{kind}:{value}"
            for parts in sent
            for kind, value in parts
        ]
        self.assertEqual(
            sent_order,
            [
                "file_image:C:/tmp/pre-image.png",
                "message:after image!",
            ],
        )


    def test_on_llm_response_intercepts_even_when_realtime_send_cooldown_is_active(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_session_cooldown_seconds": 9999.0,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        plugin._last_realtime_chat_adaptive_settings = {
            "s-intercept-cooldown": {
                "realtime_chat": {
                    "values": {"valence": 0.2},
                    "restraint": 0.0,
                },
            },
        }
        plugin._realtime_chat_last_sent = {"s-intercept-cooldown": time.time()}
        response = SimpleNamespace(completion_text="第一句。第二句。")

        async def run_response():
            await plugin.on_llm_response(
                FakeEvent("s-intercept-cooldown", platform_name="aiocqhttp"),
                response,
            )
            await self._await_background_tasks(plugin)

        asyncio.run(run_response())

        self.assertIn("sylanne_realtime_delivery_status", response.completion_text)
        self.assertIn("planned_parts=2", response.completion_text)
        self.assertEqual(
            getattr(response, "_sylanne_intercepted_completion_text", ""),
            "第一句。第二句。",
        )
        self.assertTrue(sent)
        self.assertGreaterEqual(len(sent), 2)


    def test_realtime_intercept_preserves_assistant_context_for_next_turn(self):
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
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        response = SimpleNamespace(
            completion_text="我理解错了，你说的是插件的其他用户。我想对他们说：请先读 README。",
        )

        async def run_turns():
            await plugin.on_llm_response(
                FakeEvent("s-realtime-history", platform_name="aiocqhttp"),
                response,
            )
            await self._await_background_tasks(plugin)
            next_request = fake_request(
                session_id="s-realtime-history",
                prompt="那你有什么想对他们说的吗",
            )
            await plugin.on_llm_request(
                FakeEvent("s-realtime-history", message="那你有什么想对他们说的吗"),
                next_request,
            )
            duplicate_request = fake_request(
                session_id="s-realtime-history",
                prompt="再说一遍",
            )
            await plugin.on_llm_request(
                FakeEvent("s-realtime-history", message="再说一遍"),
                duplicate_request,
            )
            return next_request, duplicate_request

        next_request, duplicate_request = asyncio.run(run_turns())

        injected = "\n".join(self._request_text_parts(next_request))
        duplicate_injected = "\n".join(self._request_text_parts(duplicate_request))
        self.assertIn("sylanne_realtime_delivery_status", response.completion_text)
        self.assertIn("delivery_status=pending_dispatch", response.completion_text)
        self.assertIn(
            "插件的其他用户",
            getattr(response, "_sylanne_intercepted_completion_text", ""),
        )
        self.assertTrue(sent)
        self.assertIn("sylanne_realtime_assistant_history", injected)
        self.assertIn("插件的其他用户", injected)
        self.assertIn("请先读 README", injected)
        self.assertLessEqual(len(injected), 1100)
        self.assertNotIn("sylanne_realtime_assistant_history", duplicate_injected)


    def test_realtime_shadow_recovers_from_kv_after_plugin_reload(self):
        stored = {}
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        async def fake_get_kv(self, key, default=None):
            return stored.get(key, default)

        async def fake_put_kv(self, key, value):
            stored[key] = value

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()
        bind_async(plugin, "get_kv_data", fake_get_kv)
        bind_async(plugin, "put_kv_data", fake_put_kv)
        self._bind_common_state_hooks(plugin)
        response = SimpleNamespace(completion_text="更新前接管的回复，平台普通历史里没有。")

        async def run_and_reload():
            await plugin.on_llm_response(
                FakeEvent("s-reload-shadow", platform_name="aiocqhttp"),
                response,
            )
            await self._await_background_tasks(plugin)
            recovered = new_plugin(
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
            bind_async(recovered, "get_kv_data", fake_get_kv)
            bind_async(recovered, "put_kv_data", fake_put_kv)
            self._bind_common_state_hooks(recovered)
            request = fake_request(
                session_id="s-reload-shadow",
                prompt="刚才你说什么",
            )
            await recovered.on_llm_request(
                FakeEvent("s-reload-shadow", message="刚才你说什么", sender_id="u1"),
                request,
            )
            duplicate_request = fake_request(
                session_id="s-reload-shadow",
                prompt="再说一遍",
            )
            await recovered.on_llm_request(
                FakeEvent("s-reload-shadow", message="再说一遍", sender_id="u1"),
                duplicate_request,
            )
            return request, duplicate_request, recovered

        request, duplicate_request, recovered = asyncio.run(run_and_reload())

        saved_key = plugin._realtime_delivery_context_kv_key("s-reload-shadow")
        injected = "\n".join(self._request_text_parts(request))
        duplicate_injected = "\n".join(self._request_text_parts(duplicate_request))
        self.assertIn(saved_key, stored)
        self.assertIn("sylanne_realtime_assistant_history", injected)
        self.assertIn("更新前接管的回复", injected)
        self.assertNotIn("sylanne_realtime_assistant_history", duplicate_injected)
        recovered_payload = stored[saved_key]
        self.assertTrue(recovered_payload["shadows"][-1]["consumed"])
        self.assertIn("s-reload-shadow", recovered._realtime_assistant_history_shadow_cache())
