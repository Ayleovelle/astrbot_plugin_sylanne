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


class AstrBotLifecyclePart15(AstrBotLifecycleTests):
    def test_napcat_recall_payload_is_parsed_from_raw_notice(self):
        plugin = new_plugin()
        event = SimpleNamespace(
            unified_msg_origin="group_123",
            message_obj=SimpleNamespace(
                raw_message={
                    "post_type": "notice",
                    "notice_type": "group_recall",
                    "group_id": 123,
                    "user_id": 456,
                    "operator_id": 789,
                    "message_id": 10001,
                },
            ),
        )

        payload = plugin._napcat_recall_payload(event)

        self.assertEqual(payload["notice_type"], "group_recall")
        self.assertEqual(payload["message_id"], "10001")
        self.assertEqual(payload["group_id"], "123")
        self.assertEqual(payload["operator_id"], "789")


    def test_observe_user_message_withdrawal_uses_napcat_notice_type_by_default(self):
        plugin = new_plugin()
        event = SimpleNamespace(
            unified_msg_origin="friend_456",
            raw_message={
                "post_type": "notice",
                "notice_type": "friend_recall",
                "user_id": 456,
                "message_id": 20002,
            },
        )

        result = asyncio.run(plugin.observe_user_message_withdrawal(event))

        self.assertEqual(result["session_key"], "friend_456")
        self.assertEqual(result["message_id"], "20002")
        self.assertEqual(result["reason"], "friend_recall")


    def test_napcat_recall_is_injected_for_next_llm_turn(self):
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
        plugin._last_request_text = {"s-recall-context": "用户刚才撤回前的消息"}
        recall_event = FakeEvent("s-recall-context", message="", platform_name="aiocqhttp")
        recall_event.raw_message = {
            "post_type": "notice",
            "notice_type": "friend_recall",
            "user_id": "u1",
            "message_id": "m-recalled",
        }
        recall_request = fake_request(session_id="s-recall-context", prompt="")
        next_request = fake_request(session_id="s-recall-context", prompt="我重新说一下")

        async def run_recall_then_next_turn():
            await plugin.on_llm_request(recall_event, recall_request)
            await plugin.on_llm_request(
                FakeEvent("s-recall-context", message="我重新说一下", sender_id="u1"),
                next_request,
            )

        asyncio.run(run_recall_then_next_turn())

        injected = "\n".join(self._request_text_parts(next_request))
        self.assertTrue(recall_event.stopped)
        self.assertTrue(recall_request._sylanne_control_event)
        self.assertIn("sylanne_user_message_withdrawal", injected)
        self.assertIn("m-recalled", injected)
        self.assertIn("用户刚才撤回前的消息", injected)


    def test_napcat_input_status_is_held_without_creating_user_turn(self):
        plugin = new_plugin({"enable_realtime_chat": True})
        event = FakeEvent("s-input-status", message="", platform_name="aiocqhttp")
        event.raw_message = {
            "post_type": "notice",
            "notice_type": "notify",
            "sub_type": "input_status",
            "status_text": "对方正在输入",
            "event_type": "1",
            "user_id": "u1",
        }
        request = fake_request(session_id="s-input-status", prompt="")

        asyncio.run(plugin.on_llm_request(event, request))

        self.assertTrue(event.stopped)
        self.assertTrue(request._sylanne_control_event)
        self.assertEqual(
            request._sylanne_default_response_stop_reason,
            "user_typing_status",
        )
        self.assertNotIn("s-input-status", plugin._conversation_input_epoch)
        self.assertIn("s-input-status", plugin._realtime_user_typing_until)


    def test_empty_input_event_holds_without_interrupting_realtime_dispatch(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "realtime_empty_input_typing_hold_seconds": 0.02,
            },
        )
        plugin.context = FakeContext()
        plugin._conversation_input_epoch = {"s-empty-input": 1}
        plan = {
            "session_key": "s-empty-input",
            "input_epoch": 1,
            "message_parts": [
                {
                    "index": 0,
                    "text": "still sent after typing pause",
                    "delay_before_seconds": 0.05,
                },
            ],
        }

        async def run_empty_event_during_dispatch():
            send_task = asyncio.create_task(
                plugin._send_realtime_chat_plan(
                    FakeEvent("s-empty-input"),
                    plan,
                    source="unit_test",
                ),
            )
            await asyncio.sleep(0.01)
            event = FakeEvent("s-empty-input", message="", platform_name="aiocqhttp")
            request = fake_request(session_id="s-empty-input", prompt="")
            await plugin.on_llm_request(event, request)
            result = await asyncio.wait_for(send_task, timeout=1.0)
            return event, request, result

        event, request, result = asyncio.run(run_empty_event_during_dispatch())

        self.assertTrue(event.stopped)
        self.assertTrue(request._sylanne_control_event)
        self.assertEqual(
            request._sylanne_default_response_stop_reason,
            "user_typing_empty_event",
        )
        self.assertIn("typing_hold_until", request._sylanne_control_event_payload)
        self.assertEqual(plugin._conversation_input_epoch["s-empty-input"], 1)
        self.assertEqual(sent, [("s-empty-input", "message:still sent after typing pause")])
        self.assertNotIn("interrupted_reason", result)


    def test_empty_input_event_without_realtime_dispatch_does_not_create_typing_hold(self):
        plugin = new_plugin(
            {
                "enable_realtime_chat": True,
                "realtime_empty_input_typing_hold_seconds": 0.02,
            },
        )
        event = FakeEvent("s-empty-idle", message="", platform_name="aiocqhttp")
        request = fake_request(session_id="s-empty-idle", prompt="")

        asyncio.run(plugin.on_llm_request(event, request))

        self.assertTrue(event.stopped)
        self.assertTrue(request._sylanne_control_event)
        self.assertEqual(
            request._sylanne_default_response_stop_reason,
            "empty_input_event",
        )
        self.assertNotIn("typing_hold_until", request._sylanne_control_event_payload)
        self.assertNotIn("s-empty-idle", plugin._realtime_user_typing_until)
        self.assertNotIn("s-empty-idle", plugin._conversation_input_epoch)


    def test_observe_sticker_usage_stores_metadata_only(self):
        stored = {}

        async def fake_get(self, key, default=None):
            return stored.get(key, default)

        async def fake_put(self, key, value):
            stored[key] = value

        plugin = new_plugin({"sticker_learn_user_images": True})
        bind_async(plugin, "get_kv_data", fake_get)
        bind_async(plugin, "put_kv_data", fake_put)

        result = asyncio.run(
            plugin.observe_sticker_usage(
                "s-sticker",
                {
                    "url": "https://example.test/a.gif",
                    "name": "笑死",
                    "binary": "not stored",
                    "interest_score": 0.9,
                },
            ),
        )

        self.assertTrue(result["committed"])
        self.assertEqual(result["memory_count"], 1)
        saved = next(iter(stored.values()))[0]
        self.assertEqual(saved["url"], "https://example.test/a.gif")
        self.assertNotIn("binary", saved)
