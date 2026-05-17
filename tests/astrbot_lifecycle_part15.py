import asyncio
import collections
import datetime as dt
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


def _shanghai_epoch(year, month, day, hour, minute=0, second=0):
    return dt.datetime(
        year,
        month,
        day,
        hour,
        minute,
        second,
        tzinfo=dt.timezone(dt.timedelta(hours=8)),
    ).timestamp()


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

    def test_reply_only_payload_does_not_consume_shadow_memory_backfill(self):
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
        plugin._record_realtime_ordinary_history_backfill(
            "s-reply-only-backfill",
            role="assistant",
            content="上一轮已经送达，但仅引用事件不该消费这段 shadow memory。",
            input_epoch=2,
            source="unit_test",
            delivery_status="delivered",
        )
        event = FakeEvent("s-reply-only-backfill", message="", platform_name="aiocqhttp")
        event.message_obj = SimpleNamespace(
            message=[
                {
                    "type": "reply",
                    "data": {"id": "12345"},
                },
            ],
        )
        request = fake_request(session_id="s-reply-only-backfill", prompt="")

        asyncio.run(plugin.on_llm_request(event, request))

        injected = "\n".join(self._request_text_parts(request))
        self.assertNotIn("sylanne_shadow_memory", injected)
        self.assertIn(
            "s-reply-only-backfill",
            plugin._realtime_ordinary_history_backfill_cache(),
        )


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


    def test_observe_stickers_background_batches_single_memory_write(self):
        stored = {}
        put_calls = []

        async def fake_get(self, key, default=None):
            return stored.get(key, default)

        async def fake_put(self, key, value):
            put_calls.append((key, value))
            stored[key] = value

        plugin = new_plugin({"sticker_learn_user_images": True})
        bind_async(plugin, "get_kv_data", fake_get)
        bind_async(plugin, "put_kv_data", fake_put)

        asyncio.run(
            plugin._observe_stickers_background(
                FakeEvent("s-sticker-batch"),
                [
                    {"url": "https://example.test/a.gif", "name": "a"},
                    {"url": "https://example.test/b.gif", "name": "b"},
                    {"url": "https://example.test/c.gif", "name": "c"},
                ],
                session_key="s-sticker-batch",
            ),
        )

        self.assertEqual(len(put_calls), 1)
        self.assertEqual(len(next(iter(stored.values()))), 3)


    def test_sylanne_memory_idle_flush_batches_one_state_write(self):
        from memory_engine import SylanneMemoryState

        plugin = new_plugin({"enable_sylanne_memory": True})
        save_calls = []

        async def fake_load_memory(self, session_key, *, now=None, save_decay=True):
            return SylanneMemoryState.initial(now=now or 100.0)

        async def fake_save_memory(self, session_key, state):
            save_calls.append((session_key, state.to_dict()))
            self._sylanne_memory_cache[session_key] = state

        async def no_embedding_provider(self):
            return None, ""

        bind_async(plugin, "_load_sylanne_memory_state", fake_load_memory)
        bind_async(plugin, "_save_sylanne_memory_state", fake_save_memory)
        bind_async(plugin, "_sylanne_memory_embedding_provider", no_embedding_provider)
        plugin._ensure_runtime_state_containers()
        plugin._sylanne_memory_pending_observations["s-memory-batch"] = collections.deque(
            [
                {
                    "text": "user says the thesis format is still broken",
                    "speaker_id": "u1",
                    "observed_at": 100.0,
                    "event_time": {},
                },
                {
                    "text": "assistant answered with a checklist",
                    "speaker_id": "assistant",
                    "observed_at": 101.0,
                    "event_time": {},
                },
            ],
        )
        plugin._sylanne_memory_idle_generation["s-memory-batch"] = 1

        asyncio.run(
            plugin._flush_sylanne_memory_pending_observations(
                "s-memory-batch",
                generation=1,
                force=True,
            ),
        )

        self.assertEqual(len(save_calls), 1)
        self.assertEqual(save_calls[0][0], "s-memory-batch")
        self.assertEqual(save_calls[0][1]["event_count"], 2)

    def test_sylanne_memory_record_embeddings_are_budgeted_on_idle_commit(self):
        from memory_engine import SylanneMemoryState

        now_holder = [1000.0]
        plugin = new_plugin(
            {
                "enable_sylanne_memory": True,
                "sylanne_memory_vector_retrieval_enabled": True,
                "sylanne_memory_embedding_provider_id": "embed-a",
                "sylanne_memory_record_embedding_min_interval_seconds": 300.0,
                "sylanne_memory_record_embedding_max_per_flush": 1,
            },
        )
        plugin._observed_now = types.MethodType(lambda self: now_holder[0], plugin)

        class FakeEmbeddingProvider:
            provider_config = {"id": "embed-a", "provider_type": "embedding"}

            def __init__(self):
                self.calls = []

            async def get_embedding(self, text):
                self.calls.append(text)
                return [1.0, 0.0, 0.0]

        provider = FakeEmbeddingProvider()

        class FakeContext:
            def get_provider_by_id(self, provider_id):
                return provider if provider_id == "embed-a" else None

        plugin.context = FakeContext()

        async def fake_load_memory(self, session_key, *, now=None, save_decay=True):
            return self._sylanne_memory_cache.get(
                session_key,
                SylanneMemoryState.initial(now=now or now_holder[0]),
            )

        async def fake_save_memory(self, session_key, state):
            self._sylanne_memory_cache[session_key] = state

        bind_async(plugin, "_load_sylanne_memory_state", fake_load_memory)
        bind_async(plugin, "_save_sylanne_memory_state", fake_save_memory)

        async def commit_twice():
            await plugin._commit_sylanne_memory_observations_batch(
                "s-embedding-budget",
                [
                    {
                        "text": "first memory that may be vectorized",
                        "speaker_id": "u1",
                        "observed_at": now_holder[0],
                    },
                    {
                        "text": "second memory should wait for later indexing",
                        "speaker_id": "assistant",
                        "observed_at": now_holder[0] + 1.0,
                    },
                ],
            )
            now_holder[0] += 10.0
            await plugin._commit_sylanne_memory_observations_batch(
                "s-embedding-budget",
                [
                    {
                        "text": "third memory is inside the embedding cooldown",
                        "speaker_id": "u2",
                        "observed_at": now_holder[0],
                    },
                ],
            )

        asyncio.run(commit_twice())

        state = plugin._sylanne_memory_cache["s-embedding-budget"]
        vectorized = [record for record in state.records if record.semantic_embedding]
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(len(vectorized), 1)


    def test_current_event_time_is_injected_before_memory_recall_without_state_injection(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": False,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
            },
        )
        self._bind_common_state_hooks(plugin)
        plugin.context = SimpleNamespace(
            get_config=lambda *args, **kwargs: {"timezone": "Asia/Shanghai"},
        )

        async def fake_memory_summary(
            self,
            request,
            *,
            session_key,
            current_user_text,
            observed_at=None,
        ):
            return (
                "[sylanne_memory_recall]\n"
                "relative_time=4天前; 旧记忆只能当作旁注，不能覆盖当前事件时间。"
            )

        bind_async(plugin, "_sylanne_memory_recall_summary_for_request", fake_memory_summary)
        request = fake_request(session_id="s-current-before-memory", prompt="我刚醒")
        event = FakeEvent(
            "s-current-before-memory",
            message="我刚醒",
            sender_id="u1",
            timestamp=_shanghai_epoch(2026, 5, 16, 7, 20, 8),
        )

        asyncio.run(plugin.on_llm_request(event, request))

        parts = self._request_text_parts(request)
        joined = "\n".join(parts)
        self.assertIn("sylanne_current_event_time", joined)
        self.assertIn("event_local_time=2026-05-16 07:20:08 +08:00", joined)
        current_index = next(
            index for index, text in enumerate(parts) if "sylanne_current_event_time" in text
        )
        memory_index = next(
            index for index, text in enumerate(parts) if "sylanne_memory_recall" in text
        )
        self.assertLess(current_index, memory_index)


    def test_recency_sensitive_turn_does_not_inject_stale_realtime_shadow(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "enable_sylanne_memory": False,
                "use_llm_assessor": False,
            },
        )
        self._bind_common_state_hooks(plugin)
        plugin.context = SimpleNamespace(
            get_config=lambda *args, **kwargs: {"timezone": "Asia/Shanghai"},
        )
        old_epoch = _shanghai_epoch(2026, 5, 12, 4, 0, 0)
        current_epoch = _shanghai_epoch(2026, 5, 16, 7, 20, 8)
        old_event = FakeEvent("s-stale-shadow", timestamp=old_epoch)
        plugin._record_realtime_assistant_history_shadow(
            "s-stale-shadow",
            full_text="这一觉睡了整整四天，之前那个凌晨四点的小坏蛋去哪儿了呀？",
            input_epoch=1,
            message_parts=[
                {"text": "这一觉睡了整整四天，之前那个凌晨四点的小坏蛋去哪儿了呀？"},
            ],
            source="unit_test",
            event_time=plugin._conversation_time_payload(old_epoch, event=old_event),
        )
        request = fake_request(
            session_id="s-stale-shadow",
            prompt="啊啊啊啊啊一觉怎么睡到现在了",
        )
        event = FakeEvent(
            "s-stale-shadow",
            message="啊啊啊啊啊一觉怎么睡到现在了",
            sender_id="u1",
            timestamp=current_epoch,
        )

        asyncio.run(plugin.on_llm_request(event, request))

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("sylanne_current_event_time", injected)
        self.assertIn("event_local_time=2026-05-16 07:20:08 +08:00", injected)
        self.assertNotIn("这一觉睡了整整四天", injected)
        queue = plugin._realtime_assistant_history_shadow_cache()["s-stale-shadow"]
        self.assertTrue(queue[-1]["consumed"])
        self.assertEqual(
            queue[-1]["consumed_reason"],
            "stale_for_recency_sensitive_turn",
        )


    def test_missing_realtime_media_file_is_blocked_without_aborting_dispatch(self):
        sent = []
        missing_path = "/AstrBot/8D0141D4DFECE5CBDFF3F73B94A5D871.png"

        class FakeContext:
            async def send_message(self, origin, message):
                text = str(message)
                if missing_path in text:
                    raise FileNotFoundError(missing_path)
                sent.append((origin, text))
                return {"ok": True}

        plugin = new_plugin(
            {
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()
        plugin._conversation_input_epoch = {"s-missing-media": 1}
        plan = {
            "session_key": "s-missing-media",
            "input_epoch": 1,
            "full_text": "看到没！",
            "message_parts": [
                {"index": 0, "text": "看到没！", "delay_before_seconds": 0.0},
            ],
            "media_parts": [
                {"kind": "file_image", "value": missing_path, "after_text_index": 1},
            ],
        }

        result = asyncio.run(
            plugin._send_realtime_chat_plan(
                FakeEvent("s-missing-media"),
                plan,
                source="unit_test",
                record_history_shadow=True,
            ),
        )

        self.assertEqual(sent, [("s-missing-media", "message:看到没！")])
        self.assertEqual(result["message_count"], 1)
        self.assertEqual(result["media_count"], 0)
        self.assertEqual(
            result["media_results"][0]["blocked_reason"],
            "missing_local_media_file",
        )
        backfills = plugin._realtime_ordinary_history_backfill_cache()["s-missing-media"]
        self.assertIn("看到没！", backfills[-1]["content"])


    def test_missing_sticker_file_is_blocked_without_aborting_dispatch(self):
        sent = []
        missing_path = "/AstrBot/8D0141D4DFECE5CBDFF3F73B94A5D871.png"

        class FakeContext:
            async def send_message(self, origin, message):
                text = str(message)
                if missing_path in text:
                    raise FileNotFoundError(missing_path)
                sent.append((origin, text))
                return {"ok": True}

        plugin = new_plugin(
            {
                "enable_realtime_chat": True,
                "enable_sticker_reaction": True,
                "sticker_llm_consistency_check_enabled": False,
            },
        )
        plugin.context = FakeContext()
        plugin._conversation_input_epoch = {"s-missing-sticker": 1}
        plan = {
            "session_key": "s-missing-sticker",
            "input_epoch": 1,
            "full_text": "我在听呢。",
            "message_parts": [
                {"index": 0, "text": "我在听呢。", "delay_before_seconds": 0.0},
            ],
            "sticker": {
                "should_send": True,
                "intent": "comfort",
                "candidate": {
                    "id": "missing-sticker",
                    "path": missing_path,
                    "name": "missing",
                    "tags": ["comfort"],
                },
            },
        }

        result = asyncio.run(
            plugin._send_realtime_chat_plan(
                FakeEvent("s-missing-sticker"),
                plan,
                source="unit_test",
            ),
        )

        self.assertEqual(sent, [("s-missing-sticker", "message:我在听呢。")])
        self.assertEqual(result["message_count"], 1)
        self.assertEqual(
            result["sticker_result"]["blocked_reason"],
            "missing_local_media_file",
        )


    def test_memory_prompt_declares_relative_time_is_not_last_reply_time(self):
        from memory_engine import (
            MemoryRecallItem,
            MemoryRecord,
            build_memory_prompt_fragment,
        )

        now = _shanghai_epoch(2026, 5, 16, 7, 20, 8)
        old = _shanghai_epoch(2026, 5, 12, 4, 0, 0)
        record = MemoryRecord(
            text="四天前聊过凌晨四点的玩笑。",
            summary="四天前聊过凌晨四点的玩笑。",
            session_key="s-memory-guard",
            event_epoch=old,
            depth=0.8,
        )

        fragment = build_memory_prompt_fragment(
            [MemoryRecallItem(record=record, score=0.9)],
            session_key="s-memory-guard",
            now=now,
        )

        self.assertIn("relative_time=4天前", fragment)
        self.assertIn("不是用户上次回复时间", fragment)


    def test_current_event_time_precedes_memory_recall_with_state_injection(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": True,
                "enable_realtime_chat": False,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
            },
        )
        self._bind_common_state_hooks(plugin)
        plugin.context = SimpleNamespace(
            get_config=lambda *args, **kwargs: {"timezone": "Asia/Shanghai"},
        )

        async def fake_memory_summary(
            self,
            request,
            *,
            session_key,
            current_user_text,
            observed_at=None,
        ):
            return (
                "[sylanne_memory_recall]\n"
                "relative_time=4天前; 旧记忆只能当作旁注，不能覆盖当前事件时间。"
            )

        bind_async(plugin, "_sylanne_memory_recall_summary_for_request", fake_memory_summary)
        request = fake_request(session_id="s-current-before-memory-inject", prompt="我刚醒")
        event = FakeEvent(
            "s-current-before-memory-inject",
            message="我刚醒",
            sender_id="u1",
            timestamp=_shanghai_epoch(2026, 5, 16, 7, 20, 8),
        )

        asyncio.run(plugin.on_llm_request(event, request))

        parts = self._request_text_parts(request)
        joined = "\n".join(parts)
        self.assertIn("sylanne_current_event_time", joined)
        self.assertIn("sylanne_memory_recall", joined)
        current_index = next(
            index for index, text in enumerate(parts) if "sylanne_current_event_time" in text
        )
        memory_index = next(
            index for index, text in enumerate(parts) if "sylanne_memory_recall" in text
        )
        self.assertLess(current_index, memory_index)


    def test_memory_workset_does_not_bleed_into_unrelated_new_topic(self):
        from memory_engine import MemoryRecord, SylanneMemoryState

        plugin = new_plugin(
            {
                "enable_sylanne_memory": True,
                "sylanne_memory_vector_retrieval_enabled": False,
            },
        )
        state = SylanneMemoryState.initial(now=0.0)
        state.records.append(
            MemoryRecord(
                memory_id="thesis-night",
                text="论文还没修完，需要继续熬夜奋战。",
                summary="论文还没修完，需要熬夜奋战。",
                session_key="s-memory-topic-shift",
                created_at=10.0,
                updated_at=10.0,
                depth=0.86,
                confidence=0.82,
            ),
        )
        plugin._sylanne_memory_cache["s-memory-topic-shift"] = state

        async def run_topic_shift():
            first = fake_request(
                session_id="s-memory-topic-shift",
                prompt="我论文还没修完捏",
            )
            first_summary = await plugin._sylanne_memory_recall_summary_for_request(
                first,
                session_key="s-memory-topic-shift",
                current_user_text="我论文还没修完捏",
            )
            second = fake_request(
                session_id="s-memory-topic-shift",
                prompt="今天晚饭吃什么比较好",
            )
            second_summary = await plugin._sylanne_memory_recall_summary_for_request(
                second,
                session_key="s-memory-topic-shift",
                current_user_text="今天晚饭吃什么比较好",
            )
            return first_summary, second_summary

        first_summary, second_summary = asyncio.run(run_topic_shift())

        self.assertIn("论文还没修完", first_summary)
        self.assertIn("论文还没修完", second_summary)
