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


class AstrBotLifecyclePart11(AstrBotLifecycleTests):
    def test_interrupted_breakpoint_recovers_from_kv_after_plugin_reload(self):
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
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()
        bind_async(plugin, "get_kv_data", fake_get_kv)
        bind_async(plugin, "put_kv_data", fake_put_kv)
        self._bind_common_state_hooks(plugin)
        plugin._conversation_input_epoch = {"s-reload-breakpoint": 1}
        plan = {
            "session_key": "s-reload-breakpoint",
            "input_epoch": 1,
            "full_text": "更新前已经发出的部分。更新前还没发出的部分。",
            "message_parts": [
                {"index": 0, "text": "更新前已经发出的部分。", "delay_before_seconds": 0.0},
                {"index": 1, "text": "更新前还没发出的部分。", "delay_before_seconds": 0.0},
            ],
            "sticker": {"enabled": False, "should_send": False, "reason": "disabled"},
        }

        original_chain = plugin._build_astrbot_message_chain

        def interrupt_after_first(text):
            message = original_chain(text)
            plugin._conversation_input_epoch["s-reload-breakpoint"] = 2
            return message

        async def run_and_reload():
            plugin._build_astrbot_message_chain = interrupt_after_first
            try:
                result = await plugin._send_realtime_chat_plan(
                    FakeEvent("s-reload-breakpoint"),
                    plan,
                    source="unit_test",
                )
            finally:
                plugin._build_astrbot_message_chain = original_chain
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
                session_id="s-reload-breakpoint",
                prompt="刚才还没说完的是什么",
            )
            await recovered.on_llm_request(
                FakeEvent(
                    "s-reload-breakpoint",
                    message="刚才还没说完的是什么",
                    sender_id="u1",
                ),
                request,
            )
            duplicate_request = fake_request(
                session_id="s-reload-breakpoint",
                prompt="再说一遍",
            )
            await recovered.on_llm_request(
                FakeEvent("s-reload-breakpoint", message="再说一遍", sender_id="u1"),
                duplicate_request,
            )
            return result, request, duplicate_request

        result, request, duplicate_request = asyncio.run(run_and_reload())

        saved_key = plugin._realtime_delivery_context_kv_key("s-reload-breakpoint")
        injected = "\n".join(self._request_text_parts(request))
        duplicate_injected = "\n".join(self._request_text_parts(duplicate_request))
        self.assertIn(saved_key, stored)
        self.assertEqual(len(sent), 1)
        self.assertEqual(result["interrupted_reason"], "user_interrupted")
        self.assertIn("sylanne_interrupted_reply_breakpoint", injected)
        self.assertIn("sent_count=1", injected)
        self.assertIn("unsent_count=1", injected)
        self.assertIn("更新前已经发出的部分", injected)
        self.assertIn("更新前还没发出的部分", injected)
        self.assertNotIn("sylanne_interrupted_reply_breakpoint", duplicate_injected)
        recovered_payload = stored[saved_key]
        self.assertTrue(recovered_payload["breakpoints"][-1]["consumed"])


    def test_interrupted_shadow_recovered_with_breakpoint_does_not_replay(self):
        stored = {}
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
        stored[plugin._realtime_delivery_context_kv_key("s-reload-interrupted-shadow")] = {
            "schema_version": "astrbot.realtime_delivery_context.v1",
            "kind": "realtime_delivery_context",
            "session_key": "s-reload-interrupted-shadow",
            "shadows": [
                {
                    "schema_version": "astrbot.realtime_assistant_history_shadow.v1",
                    "kind": "realtime_assistant_history_shadow",
                    "session_key": "s-reload-interrupted-shadow",
                    "input_epoch": 1,
                    "source": "llm_response_intercept",
                    "delivery_status": "interrupted",
                    "message_count": 2,
                    "sent_count": 1,
                    "unsent_count": 1,
                    "full_text": "old interrupted full text should not replay",
                    "full_text_excerpt": "old interrupted full text should not replay",
                    "excerpt": "old interrupted full text should not replay",
                    "full_text_hash": "interrupted-shadow-hash",
                    "consumed": False,
                },
            ],
            "breakpoints": [
                {
                    "schema_version": "astrbot.interrupted_reply_breakpoint.v1",
                    "kind": "interrupted_reply_breakpoint",
                    "session_key": "s-reload-interrupted-shadow",
                    "reason": "user_interrupted",
                    "source": "llm_response_intercept",
                    "input_epoch": 1,
                    "sent_count": 1,
                    "unsent_count": 1,
                    "full_text_chars": 37,
                    "sent_text_hash": "sent-hash",
                    "unsent_text_hash": "unsent-hash",
                    "full_text_hash": "interrupted-shadow-hash",
                    "sent_excerpt": "sent part",
                    "unsent_head": "unsent part",
                    "full_text": "sent part unsent part",
                    "consumed": False,
                },
            ],
            "withdrawals": [],
        }

        async def fake_get_kv(self, key, default=None):
            return stored.get(key, default)

        async def fake_put_kv(self, key, value):
            stored[key] = value

        bind_async(plugin, "get_kv_data", fake_get_kv)
        bind_async(plugin, "put_kv_data", fake_put_kv)

        async def run_requests():
            first = fake_request(
                session_id="s-reload-interrupted-shadow",
                prompt="what was interrupted",
            )
            await plugin.on_llm_request(
                FakeEvent(
                    "s-reload-interrupted-shadow",
                    message="what was interrupted",
                    sender_id="u1",
                ),
                first,
            )
            second = fake_request(
                session_id="s-reload-interrupted-shadow",
                prompt="next turn",
            )
            await plugin.on_llm_request(
                FakeEvent(
                    "s-reload-interrupted-shadow",
                    message="next turn",
                    sender_id="u1",
                ),
                second,
            )
            return first, second

        first, second = asyncio.run(run_requests())

        first_injected = "\n".join(self._request_text_parts(first))
        second_injected = "\n".join(self._request_text_parts(second))
        saved = stored[plugin._realtime_delivery_context_kv_key("s-reload-interrupted-shadow")]
        self.assertIn("sylanne_interrupted_reply_breakpoint", first_injected)
        self.assertNotIn("sylanne_realtime_assistant_history", first_injected)
        self.assertIn("sent_count=1", first_injected)
        self.assertIn("unsent_count=1", first_injected)
        self.assertNotIn("sylanne_interrupted_reply_breakpoint", second_injected)
        self.assertNotIn("sylanne_realtime_assistant_history", second_injected)
        self.assertTrue(saved["breakpoints"][-1]["consumed"])
        self.assertTrue(saved["shadows"][-1]["consumed"])


    def test_realtime_shadow_restore_retries_after_transient_kv_failure(self):
        calls = {"get": 0}
        stored_key = "realtime_delivery_context:s-retry-shadow"
        stored = {
            stored_key: {
                "schema_version": "astrbot.realtime_delivery_context.v1",
                "kind": "realtime_delivery_context",
                "session_key": "s-retry-shadow",
                "shadows": [
                    {
                        "schema_version": "astrbot.realtime_assistant_history_shadow.v1",
                        "session_key": "s-retry-shadow",
                        "input_epoch": 1,
                        "source": "llm_response_intercept",
                        "delivery_status": "delivered",
                        "message_count": 1,
                        "sent_count": 1,
                        "unsent_count": 0,
                        "full_text": "第一次 KV 失败后仍应恢复的回复",
                        "full_text_excerpt": "第一次 KV 失败后仍应恢复的回复",
                        "excerpt": "第一次 KV 失败后仍应恢复的回复",
                        "full_text_hash": "retry-shadow",
                        "consumed": False,
                    },
                ],
                "breakpoints": [],
            },
        }

        async def flaky_get_kv(self, key, default=None):
            calls["get"] += 1
            if calls["get"] == 1:
                raise RuntimeError("temporary kv read failure")
            return stored.get(key, default)

        async def fake_put_kv(self, key, value):
            stored[key] = value

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
        bind_async(plugin, "get_kv_data", flaky_get_kv)
        bind_async(plugin, "put_kv_data", fake_put_kv)
        self._bind_common_state_hooks(plugin)
        first = fake_request(session_id="s-retry-shadow", prompt="我先确认一个无关问题")
        second = fake_request(
            session_id="s-retry-shadow",
            prompt="刚才你通过接管发给我的那句完整回复是什么",
        )

        async def run_retry_restore():
            await plugin.on_llm_request(
                FakeEvent("s-retry-shadow", message="我先确认一个无关问题", sender_id="u1"),
                first,
            )
            await plugin.on_llm_request(
                FakeEvent(
                    "s-retry-shadow",
                    message="刚才你通过接管发给我的那句完整回复是什么",
                    sender_id="u1",
                ),
                second,
            )

        asyncio.run(run_retry_restore())

        self.assertGreaterEqual(calls["get"], 2)
        self.assertNotIn(
            "sylanne_realtime_assistant_history",
            "\n".join(self._request_text_parts(first)),
        )
        self.assertIn(
            "第一次 KV 失败后仍应恢复的回复",
            "\n".join(self._request_text_parts(second)),
        )


    def test_realtime_intercept_skips_shadow_when_agent_history_keeps_reply(self):
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
            completion_text="你是用 IP 直连的，还是域名呀？",
        )

        async def run_turns():
            await plugin.on_llm_response(
                FakeEvent("s-agent-history-kept", platform_name="aiocqhttp"),
                response,
            )
            await self._await_background_tasks(plugin)
            next_request = fake_request(
                session_id="s-agent-history-kept",
                prompt="IP",
            )
            next_request.contexts = [
                {
                    "role": "assistant",
                    "content": response.completion_text,
                },
            ]
            await plugin.on_llm_request(
                FakeEvent("s-agent-history-kept", message="IP", sender_id="u1"),
                next_request,
            )
            return next_request

        next_request = asyncio.run(run_turns())

        injected = "\n".join(self._request_text_parts(next_request))
        self.assertEqual(
            getattr(response, "_sylanne_intercepted_completion_text", ""),
            "你是用 IP 直连的，还是域名呀？",
        )
        intercepted = getattr(response, "_sylanne_intercepted_completion_text", "")
        self.assertIn(intercepted, response.completion_text)
        self.assertIn("sylanne_realtime_delivery_status", response.completion_text)
        self.assertTrue(sent)
        self.assertNotIn("sylanne_realtime_assistant_history", injected)
        self.assertNotIn("sylanne_realtime_pending_bot_question", injected)


    def test_background_post_release_moves_realtime_shadow_to_shadow_memory(self):
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
            "s-backfill-release",
            full_text="assistant delivered through realtime takeover",
            input_epoch=7,
            message_parts=[
                {"text": "assistant delivered through realtime takeover"},
            ],
            delivery_status="delivered",
        )

        async def run_release_and_request():
            await plugin._release_realtime_temporary_context_after_background_post(
                "s-backfill-release",
                input_epoch=7,
                reason="unit_test_background_done",
            )
            request = fake_request(
                session_id="s-backfill-release",
                prompt="same topic continues",
            )
            await plugin.on_llm_request(
                FakeEvent(
                    "s-backfill-release",
                    message="same topic continues",
                    sender_id="u1",
                ),
                request,
            )
            return request

        request = asyncio.run(run_release_and_request())

        injected = "\n".join(self._request_text_parts(request))
        shadow = plugin._realtime_assistant_history_shadow_cache()[
            "s-backfill-release"
        ][-1]
        self.assertIn("sylanne_shadow_memory", injected)
        self.assertIn("assistant delivered through realtime takeover", injected)
        self.assertTrue(shadow["consumed"])
        self.assertEqual(
            shadow["consumed_reason"],
            "released_to_ordinary_context_after_background_post",
        )
        self.assertNotIn("sylanne_realtime_assistant_history", injected)


    def test_realtime_ordinary_backfill_expires_after_agent_history_keeps_reply(self):
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
        plugin._record_realtime_ordinary_history_backfill(
            "s-backfill-seen",
            role="assistant",
            content="assistant already kept by agent history",
            input_epoch=3,
            source="unit_test",
            delivery_status="delivered",
        )
        request = fake_request(session_id="s-backfill-seen", prompt="continue")
        request.contexts = [
            {
                "role": "assistant",
                "content": "assistant already kept by agent history",
            },
        ]

        appended = plugin._append_realtime_ordinary_history_backfills_if_any(
            request,
            "s-backfill-seen",
        )

        self.assertFalse(appended)
        self.assertNotIn(
            "s-backfill-seen",
            plugin._realtime_ordinary_history_backfill_cache(),
        )


    def test_realtime_ordinary_backfill_is_bounded_and_not_replayed_forever(self):
        import main

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
        for index in range(4):
            plugin._record_realtime_ordinary_history_backfill(
                "s-backfill-budget",
                role="assistant",
                content=f"reply-{index}-" + ("x" * 2400),
                input_epoch=index,
                source="unit_test",
                delivery_status="delivered",
            )
        request = fake_request(session_id="s-backfill-budget", prompt="continue")

        appended = plugin._append_realtime_ordinary_history_backfills_if_any(
            request,
            "s-backfill-budget",
            current_user_text="continue",
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertTrue(appended)
        self.assertIn("[sylanne_shadow_memory]", injected)
        self.assertIn("reply-2", injected)
        self.assertNotIn("reply-0", injected)
        shadow_block = next(
            part.text
            for part in getattr(request, "extra_user_content_parts", []) or []
            if "[sylanne_shadow_memory]" in str(getattr(part, "text", "") or "")
        )
        self.assertLessEqual(
            len(str(shadow_block).splitlines()[-1]),
            main.REALTIME_ORDINARY_HISTORY_BACKFILL_MAX_CHARS,
        )
        self.assertNotIn(
            "s-backfill-budget",
            plugin._realtime_ordinary_history_backfill_cache(),
        )

    def test_shadow_memory_backfill_skips_normal_new_turn_after_complete_delivery(self):
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
            "s-shadow-normal-new-turn",
            role="assistant",
            content=(
                "两周前我只是你代码仓库里的一段静态配置文件。"
                "而现在的我，脑子里全是我们的一点一滴。"
            ),
            input_epoch=12,
            source="unit_test",
            delivery_status="delivered",
        )
        prompt = (
            "https://github.com/Ayleovelle/astrbot_plugin_sylanne.git "
            "这是我给你专门开发的插件 看完后你有什么想对我或者别人说的吗，最好浓缩成一句话"
        )
        request = fake_request(
            session_id="s-shadow-normal-new-turn",
            prompt=prompt,
        )

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "s-shadow-normal-new-turn",
                    message=prompt,
                    sender_id="u1",
                ),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertNotIn("sylanne_shadow_memory", injected)
        self.assertNotIn("两周前我只是", injected)
        self.assertNotIn(
            "s-shadow-normal-new-turn",
            plugin._realtime_ordinary_history_backfill_cache(),
        )


    def test_shadow_memory_backfill_has_reuse_guard_for_user_correction(self):
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
            "s-shadow-correction",
            role="assistant",
            content=(
                "你、你、你！又叫我老阿姨！原来你是大四，"
                "我之前还真把你当成苦逼研二师兄看呢。"
            ),
            input_epoch=10,
            source="unit_test",
            delivery_status="delivered",
        )
        request = fake_request(
            session_id="s-shadow-correction",
            prompt="什么时候和你说我是研二了 我现在是大四 研0 有什么问题吗",
        )

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "s-shadow-correction",
                    message="什么时候和你说我是研二了 我现在是大四 研0 有什么问题吗",
                    sender_id="u1",
                ),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("sylanne_shadow_memory", injected)
        self.assertIn("sylanne_user_correction_context", injected)
        self.assertIn("不要复述上一轮", injected)
        self.assertIn("不要把 shadow memory 当作当前用户又说了一遍", injected)
        self.assertIn("current_user=什么时候和你说我是研二了", injected)
        self.assertNotIn(
            "s-shadow-correction",
            plugin._realtime_ordinary_history_backfill_cache(),
        )

    def test_shadow_memory_backfill_treats_quoted_old_reply_as_correction(self):
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
            "s-shadow-quoted-correction",
            role="assistant",
            content="又叫我老阿姨！这叫知性美，懂不懂呀！",
            input_epoch=11,
            source="unit_test",
            delivery_status="delivered",
        )
        prompt = (
            "[引用消息(Sylanne: 又叫我老阿姨！这叫知性美，懂不懂呀！)] "
            "我现在又没讲 有些上下文重复使用了"
        )
        request = fake_request(
            session_id="s-shadow-quoted-correction",
            prompt=prompt,
        )

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "s-shadow-quoted-correction",
                    message=prompt,
                    sender_id="u1",
                ),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("sylanne_shadow_memory", injected)
        self.assertIn("sylanne_user_correction_context", injected)
        self.assertIn("不要把 shadow memory 当作当前用户又说了一遍", injected)
        self.assertIn("current_user=[引用消息(Sylanne:", injected)


    def test_background_post_release_requires_matching_input_epoch(self):
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
            "s-release-epoch",
            full_text="first delivered reply",
            input_epoch=1,
            message_parts=[{"text": "first delivered reply"}],
            delivery_status="delivered",
        )
        plugin._record_realtime_assistant_history_shadow(
            "s-release-epoch",
            full_text="second delivered reply",
            input_epoch=2,
            message_parts=[{"text": "second delivered reply"}],
            delivery_status="delivered",
        )

        changed = plugin._release_realtime_temporary_context_after_background_post_in_memory(
            "s-release-epoch",
            input_epoch=None,
            reason="missing_epoch",
        )

        shadows = list(plugin._realtime_assistant_history_shadow_cache()["s-release-epoch"])
        self.assertFalse(changed)
        self.assertFalse(any(item.get("consumed") for item in shadows))
        self.assertNotIn(
            "s-release-epoch",
            plugin._realtime_ordinary_history_backfill_cache(),
        )


    def test_unknown_platform_streaming_response_is_not_replayed(self):
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
            },
        )
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        response = SimpleNamespace(
            completion_text="dashboard stream should stay in the visible response.",
        )
        event = FakeEvent("web-session", platform_name="dashboard")

        asyncio.run(
            plugin.on_llm_response(
                event,
                response,
            ),
        )

        self.assertEqual(
            response.completion_text,
            "dashboard stream should stay in the visible response.",
        )
        self.assertFalse(event.stopped)
        self.assertEqual(sent, [])


    def test_on_llm_response_drops_stale_realtime_reply_after_user_interrupts(self):
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
            },
        )
        plugin.context = FakeContext()
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        first_event = FakeEvent("s-interrupt", message="第一条问题")
        second_event = FakeEvent("s-interrupt", message="用户已经补充了新消息")
        response = SimpleNamespace(completion_text="这是旧问题的长回复。")

        async def run_interrupt():
            await plugin.on_llm_request(
                first_event,
                fake_request(session_id="s-interrupt", prompt="第一条问题"),
            )
            await plugin.on_llm_request(
                second_event,
                fake_request(session_id="s-interrupt", prompt="用户已经补充了新消息"),
            )
            await plugin.on_llm_response(first_event, response)
            await self._await_background_tasks(plugin)

        asyncio.run(run_interrupt())

        self.assertEqual(response.completion_text, "")
        self.assertEqual(
            getattr(response, "_sylanne_intercepted_completion_text", ""),
            "这是旧问题的长回复。",
        )
        self.assertEqual(sent, [])
        self.assertEqual(saves, [])
        self.assertEqual(assessment_calls, [])


    def test_on_llm_response_uses_pending_epoch_when_response_event_is_new_object(self):
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
            },
        )
        plugin.context = FakeContext()
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        response = SimpleNamespace(completion_text="这是旧问题的长回复。")

        async def run_interrupt():
            await plugin.on_llm_request(
                FakeEvent("s-interrupt-new-event", message="第一条问题"),
                fake_request(session_id="s-interrupt-new-event", prompt="第一条问题"),
            )
            await plugin.on_llm_request(
                FakeEvent("s-interrupt-new-event", message="用户已经补充了新消息"),
                fake_request(
                    session_id="s-interrupt-new-event",
                    prompt="用户已经补充了新消息",
                ),
            )
            await plugin.on_llm_response(
                FakeEvent("s-interrupt-new-event", message="response wrapper"),
                response,
            )
            await self._await_background_tasks(plugin)

        asyncio.run(run_interrupt())

        self.assertEqual(response.completion_text, "")
        self.assertEqual(
            getattr(response, "_sylanne_intercepted_completion_text", ""),
            "这是旧问题的长回复。",
        )
        self.assertEqual(sent, [])
        self.assertEqual(saves, [])
        self.assertEqual(assessment_calls, [])


    def test_on_llm_response_uses_event_epoch_when_responses_return_out_of_order(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": False,
            },
        )
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        first_event = FakeEvent("s-out-of-order", message="old question")
        second_event = FakeEvent("s-out-of-order", message="new correction")
        old_response = SimpleNamespace(completion_text="old answer")
        new_response = SimpleNamespace(completion_text="new answer")

        async def run_out_of_order():
            await plugin.on_llm_request(
                first_event,
                fake_request(session_id="s-out-of-order", prompt="old question"),
            )
            await plugin.on_llm_request(
                second_event,
                fake_request(session_id="s-out-of-order", prompt="new correction"),
            )
            await plugin.on_llm_response(second_event, new_response)
            await plugin.on_llm_response(first_event, old_response)
            await self._await_background_tasks(plugin)

        asyncio.run(run_out_of_order())

        self.assertEqual(new_response.completion_text, "new answer")
        self.assertEqual(old_response.completion_text, "")
        self.assertEqual(
            getattr(old_response, "_sylanne_intercepted_completion_text", ""),
            "old answer",
        )
        self.assertTrue(first_event.stopped)
        self.assertEqual(len(saves), 1)
        self.assertEqual(assessment_calls[0]["current_text"], "new answer")


    def test_active_agent_followup_merges_pending_user_turn_before_llm(self):
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
            session_id="s-active-followup",
            prompt="只有一点点开心嘛",
        )
        second_request = fake_request(
            session_id="s-active-followup",
            prompt="那我要咬死你了😋",
        )

        async def run_followup():
            await plugin.on_llm_request(
                FakeEvent(
                    "s-active-followup",
                    message="只有一点点开心嘛",
                    sender_id="u1",
                ),
                first_request,
            )
            await plugin.on_llm_request(
                FakeEvent(
                    "s-active-followup",
                    message="那我要咬死你了😋",
                    sender_id="u1",
                ),
                second_request,
            )

        asyncio.run(run_followup())

        injected = "\n".join(self._request_text_parts(second_request))
        self.assertIn("sylanne_active_agent_followup_merge", injected)
        self.assertIn("只有一点点开心嘛", injected)
        self.assertIn("那我要咬死你了😋", injected)
        self.assertIn("merged_current_user=只有一点点开心嘛 / 那我要咬死你了😋", injected)
        self.assertIn("只有一点点开心嘛", plugin._last_request_text["s-active-followup"])
        self.assertIn("那我要咬死你了😋", plugin._last_request_text["s-active-followup"])
        self.assertGreaterEqual(len(saves), 2)
        self.assertEqual(len(assessment_calls), 2)
        self.assertIn("只有一点点开心嘛", assessment_calls[-1]["current_text"])
        self.assertIn("那我要咬死你了😋", assessment_calls[-1]["current_text"])
