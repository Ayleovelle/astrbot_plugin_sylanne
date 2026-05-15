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


class AstrBotLifecyclePart08(AstrBotLifecycleTests):
    def test_on_llm_request_reinforces_recalled_sylanne_memory(self):
        from memory_engine import MemoryRecord, SylanneMemoryState

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
        plugin._observed_now = lambda: 20.0
        state = SylanneMemoryState.initial(now=0.0)
        state.records.append(
            MemoryRecord(
                text="用户说过插件文档页不要显示旧版本。",
                summary="插件文档页不要显示旧版本。",
                session_key="s-reinforce-request",
                speaker_id="u1",
                created_at=10.0,
                updated_at=10.0,
                depth=0.42,
                confidence=0.44,
                layers={"semantic": 0.8},
            ),
        )
        plugin._sylanne_memory_cache["s-reinforce-request"] = state
        saved = []

        async def fake_save_memory(self, session_key, saved_state):
            saved.append((session_key, saved_state.to_dict()))
            self._sylanne_memory_cache[session_key] = saved_state

        bind_async(plugin, "_save_sylanne_memory_state", fake_save_memory)
        request = fake_request(
            session_id="s-reinforce-request",
            prompt="为什么插件文档页还是旧版本",
        )

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "s-reinforce-request",
                    message="为什么插件文档页还是旧版本",
                    sender_id="u1",
                ),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("sylanne_memory_recall", injected)
        self.assertEqual(saved[-1][0], "s-reinforce-request")
        saved_record = saved[-1][1]["records"][0]
        self.assertEqual(saved_record["recall_count"], 1)
        self.assertGreater(saved_record["depth"], 0.42)


    def test_on_llm_request_can_include_associated_sylanne_memory(self):
        from memory_engine import MemoryRecord, SylanneMemoryState

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
        state = SylanneMemoryState.initial(now=0.0)
        state.dynamics.recall_limit = 1
        state.dynamics.associative_recall_limit = 1
        state.records.extend(
            [
                MemoryRecord(
                    memory_id="core-them",
                    text="用户解释过：他们指插件的其他用户，不是恋爱对象。",
                    summary="他们指插件的其他用户。",
                    session_key="s-associated-request",
                    created_at=10.0,
                    updated_at=10.0,
                    depth=0.91,
                    confidence=0.84,
                    associations={"tone-soft": 0.88},
                ),
                MemoryRecord(
                    memory_id="tone-soft",
                    text="用户希望 Sylanne 对插件使用者说话时温和一点，别像炫耀。",
                    summary="对插件使用者说话要温和，别炫耀。",
                    session_key="s-associated-request",
                    created_at=11.0,
                    updated_at=11.0,
                    depth=0.74,
                    confidence=0.70,
                ),
            ],
        )
        plugin._sylanne_memory_cache["s-associated-request"] = state
        request = fake_request(
            session_id="s-associated-request",
            prompt="那你想对他们说什么",
        )

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "s-associated-request",
                    message="那你想对他们说什么",
                    sender_id="u1",
                ),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("sylanne_memory_recall", injected)
        self.assertIn("他们指插件的其他用户", injected)
        self.assertIn("对插件使用者说话要温和", injected)
        self.assertLessEqual(len(injected), 1800)


    def test_on_llm_request_does_not_call_external_livingmemory(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
            },
        )
        self._bind_common_state_hooks(plugin)
        calls = []

        class FakeLivingMemory:
            async def search_memory(self, session_key=None, query="", limit=3):
                calls.append({"session_key": session_key, "query": query, "limit": limit})
                return [{"text": "should not be injected by default"}]

        class FakeContext:
            def get_registered_star(self, name):
                if name == "astrbot_plugin_livingmemory":
                    return SimpleNamespace(activated=True, star_cls=FakeLivingMemory())
                return None

        plugin.context = FakeContext()
        request = fake_request(session_id="s-request-memory-default-off", prompt="他们呢")

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("s-request-memory-default-off", message="他们呢", sender_id="u1"),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertEqual(calls, [])
        self.assertNotIn("sylanne_memory_recall", injected)


    def test_on_llm_request_sylanne_memory_recall_failure_silently_degrades(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
            },
        )
        self._bind_common_state_hooks(plugin)

        async def broken_load_memory(self, session_key, *, now=None):
            raise RuntimeError("sylanne memory unavailable")

        bind_async(plugin, "_load_sylanne_memory_state", broken_load_memory)
        request = fake_request(session_id="s-request-memory-fail", prompt="他们呢")

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("s-request-memory-fail", message="他们呢", sender_id="u1"),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertNotIn("sylanne_memory_recall", injected)


    def test_sylanne_memory_recall_query_excludes_existing_recall_parts(self):
        plugin = new_plugin()
        request = fake_request(session_id="s-memory-query", prompt="current prompt")
        request.contexts = [
            {"role": "user", "content": "recent user context"},
        ]
        request.extra_user_content_parts.extend(
            [
                SimpleNamespace(
                    text="[sylanne_memory_recall]\nold recalled memory must not become a query",
                ),
                SimpleNamespace(text="new temporary context can join query"),
            ],
        )

        query = plugin._sylanne_memory_recall_query_for_request(
            request,
            current_user_text="current prompt",
        )

        self.assertIn("new temporary context", query)
        self.assertNotIn("old recalled memory", query)
        self.assertNotIn("sylanne_memory_recall", query)


    def test_context_compression_summary_is_used_for_memory_query(self):
        plugin = new_plugin()
        request = fake_request(
            session_id="s-compressed-memory-query",
            prompt="what should I tell them now?",
        )
        request.contexts = [
            {
                "role": "system",
                "content": (
                    "AstrBot 自动压缩上下文摘要：用户刚才说明 them 指插件的其他使用者；"
                    "助手已经道歉并准备给插件使用者留一句话。"
                ),
            },
        ]

        query = plugin._sylanne_memory_recall_query_for_request(
            request,
            current_user_text="what should I tell them now?",
        )

        self.assertIn("自动压缩上下文摘要", query)
        self.assertIn("插件的其他使用者", query)
        self.assertIn("what should I tell them now?", query)


    def test_context_compression_summary_strips_sylanne_internal_blocks(self):
        plugin = new_plugin()
        request = fake_request(
            session_id="s-compressed-internal-strip",
            prompt="continue",
        )
        request.contexts = [
            {
                "role": "system",
                "content": (
                    "自动压缩上下文摘要：用户问的是插件使用者。\n"
                    "[sylanne_memory_recall]\n"
                    "old internal recall must not re-enter query\n"
                    "[sylanne_realtime_assistant_history]\n"
                    "old realtime shadow must not re-enter query\n"
                    "摘要结束。"
                ),
            },
        ]

        query = plugin._sylanne_memory_recall_query_for_request(
            request,
            current_user_text="continue",
        )

        self.assertIn("插件使用者", query)
        self.assertNotIn("old internal recall", query)
        self.assertNotIn("old realtime shadow", query)
        self.assertNotIn("sylanne_memory_recall", query)
        self.assertNotIn("sylanne_realtime_assistant_history", query)


    def test_context_compression_summary_strips_inline_sylanne_markers(self):
        plugin = new_plugin()
        request = fake_request(
            session_id="s-compressed-inline-strip",
            prompt="continue",
        )
        request.contexts = [
            {
                "role": "system",
                "content": (
                    "自动压缩上下文摘要：用户问的是插件使用者。"
                    "[sylanne_memory_recall] old inline recall must not re-enter query。"
                ),
            },
        ]

        query = plugin._sylanne_memory_recall_query_for_request(
            request,
            current_user_text="continue",
        )

        self.assertIn("插件使用者", query)
        self.assertNotIn("old inline recall", query)
        self.assertNotIn("sylanne_memory_recall", query)


    def test_sylanne_memory_recall_accumulates_within_active_round(self):
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
                session_key="s-memory-workset",
                created_at=10.0,
                updated_at=10.0,
                depth=0.86,
                confidence=0.82,
            ),
        )
        plugin._sylanne_memory_cache["s-memory-workset"] = state

        async def run_memory_workset():
            first = fake_request(
                session_id="s-memory-workset",
                prompt="我论文还没修完捏",
            )
            first_summary = await plugin._sylanne_memory_recall_summary_for_request(
                first,
                session_key="s-memory-workset",
                current_user_text="我论文还没修完捏",
            )
            second = fake_request(session_id="s-memory-workset", prompt="得")
            second_summary = await plugin._sylanne_memory_recall_summary_for_request(
                second,
                session_key="s-memory-workset",
                current_user_text="得",
            )
            return first_summary, second_summary

        first_summary, second_summary = asyncio.run(run_memory_workset())

        self.assertIn("论文还没修完", first_summary)
        self.assertIn("论文还没修完", second_summary)


    def test_sylanne_memory_recall_is_limited_side_note(self):
        from memory_engine import MemoryRecord, SylanneMemoryState
        import main

        plugin = new_plugin(
            {
                "enable_sylanne_memory": True,
                "sylanne_memory_vector_retrieval_enabled": False,
            },
        )
        state = SylanneMemoryState.initial(now=0.0)
        state.dynamics.recall_limit = 5
        state.dynamics.associative_recall_limit = 0
        for index in range(5):
            state.records.append(
                MemoryRecord(
                    memory_id=f"annoying-context-{index}",
                    text=f"用户说备用件很贵并且很烦，这是同一件事的记忆 {index}",
                    summary=f"备用件很贵导致烦躁 {index}",
                    session_key="s-memory-side-note",
                    created_at=10.0 + index,
                    updated_at=10.0 + index,
                    depth=0.86,
                    confidence=0.82,
                ),
            )
        plugin._sylanne_memory_cache["s-memory-side-note"] = state

        async def run_memory_recall():
            request = fake_request(
                session_id="s-memory-side-note",
                prompt="备用件好烦",
            )
            return await plugin._sylanne_memory_recall_summary_for_request(
                request,
                session_key="s-memory-side-note",
                current_user_text="备用件好烦",
            )

        summary = asyncio.run(run_memory_recall())

        self.assertIn("sylanne_memory_recall", summary)
        self.assertIn("result_count=3", summary)
        self.assertLessEqual(len(summary), main.SYLANNE_MEMORY_RECALL_INJECTION_MAX_CHARS)
        self.assertNotIn("备用件很贵导致烦躁 3", summary)
        self.assertNotIn("备用件很贵导致烦躁 4", summary)


    def test_sylanne_memory_observe_defers_fragmented_user_turn_until_idle_flush(self):
        from memory_engine import SylanneMemoryState

        stored = {}

        async def fake_get(self, key, default=None):
            return stored.get(key, default)

        async def fake_put(self, key, value):
            stored[key] = value

        plugin = new_plugin(
            {
                "enable_sylanne_memory": True,
                "sylanne_memory_vector_retrieval_enabled": False,
            },
        )
        bind_async(plugin, "get_kv_data", fake_get)
        bind_async(plugin, "put_kv_data", fake_put)

        async def run_deferred_memory():
            await plugin._observe_sylanne_memory_event_if_enabled(
                "s-idle-memory",
                "I say",
                speaker_id="user-1",
                observed_at=100.0,
                defer_until_idle=True,
            )
            await plugin._observe_sylanne_memory_event_if_enabled(
                "s-idle-memory",
                "you sound like teasing",
                speaker_id="user-1",
                observed_at=100.4,
                defer_until_idle=True,
            )
            key = plugin._sylanne_memory_kv_key("s-idle-memory")
            self.assertNotIn(key, stored)
            await plugin._flush_sylanne_memory_pending_observations(
                "s-idle-memory",
                force=True,
            )
            return SylanneMemoryState.from_dict(stored[key])

        state = asyncio.run(run_deferred_memory())

        self.assertEqual(len(state.records), 1)
        self.assertIn("I say", state.records[0].text)
        self.assertIn("you sound like teasing", state.records[0].text)


    def test_sylanne_memory_terminate_flushes_deferred_observations(self):
        stored = {}

        async def fake_get(self, key, default=None):
            return stored.get(key, default)

        async def fake_put(self, key, value):
            stored[key] = value

        plugin = new_plugin(
            {
                "enable_sylanne_memory": True,
                "sylanne_memory_vector_retrieval_enabled": False,
            },
        )
        bind_async(plugin, "get_kv_data", fake_get)
        bind_async(plugin, "put_kv_data", fake_put)

        async def run_terminate_flush():
            await plugin._observe_sylanne_memory_event_if_enabled(
                "s-terminate-memory",
                "flush me before update",
                speaker_id="user-1",
                observed_at=200.0,
                defer_until_idle=True,
            )
            key = plugin._sylanne_memory_kv_key("s-terminate-memory")
            self.assertNotIn(key, stored)
            await plugin.terminate()
            return key

        key = asyncio.run(run_terminate_flush())

        self.assertIn(key, stored)


    def test_context_compression_summary_prevents_duplicate_realtime_shadow(self):
        plugin = new_plugin({"enable_realtime_chat": True, "enable_sticker_reaction": False})
        plugin._record_realtime_assistant_history_shadow(
            "s-compressed-shadow",
            full_text="assistant already summarized by official compression",
            input_epoch=1,
            message_parts=[{"text": "assistant already summarized by official compression"}],
            source="unit_test",
        )
        request = fake_request(
            session_id="s-compressed-shadow",
            prompt="continue from that",
        )
        request.contexts = [
            {
                "role": "system",
                "content": (
                    "官方自动压缩上下文摘要：上一轮助手已经说过 "
                    "assistant already summarized by official compression。"
                    "[sylanne_realtime_assistant_history]"
                ),
            },
        ]

        appended = plugin._append_realtime_assistant_history_shadow_if_any(
            request,
            "s-compressed-shadow",
            budget=None,
            current_user_text="continue from that",
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertFalse(appended)
        self.assertNotIn("sylanne_realtime_assistant_history", injected)
        queue = plugin._realtime_assistant_history_shadow_cache()["s-compressed-shadow"]
        self.assertTrue(queue[-1]["consumed"])
        self.assertEqual(queue[-1]["consumed_reason"], "official_context_compression_summary")


    def test_short_answer_anchors_to_previous_realtime_choice_question(self):
        plugin = new_plugin({"enable_realtime_chat": True, "enable_sticker_reaction": False})
        plugin._record_realtime_assistant_history_shadow(
            "s-choice-anchor",
            full_text="你是用 IP 直连的，还是域名呀？",
            input_epoch=1,
            message_parts=[{"text": "你是用 IP 直连的，还是域名呀？"}],
            source="unit_test",
        )
        request = fake_request(session_id="s-choice-anchor", prompt="IP")

        appended = plugin._append_realtime_continuity_context_if_any(
            request,
            "s-choice-anchor",
            budget=None,
            current_user_text="IP",
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertTrue(appended)
        self.assertIn("sylanne_realtime_pending_bot_question", injected)
        self.assertIn("上一轮 bot 刚提出了一个未闭合问题", injected)
        self.assertIn("你是用 IP 直连的，还是域名呀？", injected)
        self.assertIn("current_user_short_answer=IP", injected)


    def test_on_llm_request_keeps_short_answer_context_for_previous_bot_question(self):
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
            "s-choice-request",
            full_text="你是用 IP 直连的，还是域名呀？",
            input_epoch=1,
            message_parts=[{"text": "你是用 IP 直连的，还是域名呀？"}],
            source="unit_test",
        )
        request = fake_request(session_id="s-choice-request", prompt="IP")

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("s-choice-request", message="IP", sender_id="u1"),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("sylanne_realtime_pending_bot_question", injected)
        self.assertIn("current_user_short_answer=IP", injected)
        self.assertIn("你是用 IP 直连的，还是域名呀？", injected)


    def test_short_answer_context_keeps_question_cluster_for_split_reply(self):
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
            "s-question-cluster",
            full_text=(
                "喝了杯什么呀？这么神奇，一喝就困？"
                "☕️ 可别告诉我你又是那种熬到天亮才去补觉的夜猫子模式。"
            ),
            input_epoch=1,
            message_parts=[
                {"text": "喝了杯什么呀？"},
                {"text": "这么神奇，"},
                {"text": "一喝就困？"},
                {"text": "☕️ 可别告诉我你又是那种熬到天亮才去补觉的夜猫子模式。"},
            ],
            source="unit_test",
        )
        request = fake_request(session_id="s-question-cluster", prompt="咖啡啊")

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("s-question-cluster", message="咖啡啊", sender_id="u1"),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("sylanne_realtime_pending_bot_question", injected)
        self.assertIn("喝了杯什么呀？", injected)
        self.assertIn("一喝就困？", injected)
        self.assertIn("current_user_short_answer=咖啡啊", injected)
        self.assertIn("不要把它当成用户正在发起新的行动", injected)


    def test_interrupted_reply_recovery_can_include_sylanne_memory_summary(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
            },
        )
        self._bind_common_state_hooks(plugin)
        plugin._record_interrupted_reply_breakpoint(
            "s-breakpoint-memory",
            full_text="刚才我误会了其他用户的意思，后面本来要补一句给插件使用者的话。",
            sent_parts=["刚才我误会了。"],
            unsent_parts=["后面本来要补一句给插件使用者的话。"],
            input_epoch=1,
            reason="user_interrupted",
        )
        from memory_engine import MemoryRecord, SylanneMemoryState

        class FakeLivingMemory:
            async def search_memory(self, session_key=None, query="", limit=3):
                raise AssertionError("interrupted recovery must use Sylanne memory")

        class FakeContext:
            def get_registered_star(self, name):
                if name == "astrbot_plugin_livingmemory":
                    return SimpleNamespace(activated=True, star_cls=FakeLivingMemory())
                return None

        plugin.context = FakeContext()
        state = SylanneMemoryState.initial(now=0.0)
        state.records.append(
            MemoryRecord(
                text="他们在这段对话里指插件的其他使用者。",
                summary="他们在这段对话里指插件的其他使用者。",
                session_key="s-breakpoint-memory",
                created_at=10.0,
                updated_at=10.0,
                depth=0.9,
                confidence=0.82,
            ),
        )
        plugin._sylanne_memory_cache["s-breakpoint-memory"] = state
        request = fake_request(session_id="s-breakpoint-memory", prompt="那他们呢")

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("s-breakpoint-memory", message="那他们呢", sender_id="u1"),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("sylanne_interrupted_reply_breakpoint", injected)
        self.assertIn("sylanne_memory_recall", injected)
        self.assertIn("其他使用者", injected)


    def test_proactive_scheduler_skips_missing_unified_origin(self):
        plugin = new_plugin(
            {
                "enable_proactive_speech_dispatch": True,
                "enable_proactive_speech_scheduler": True,
            },
        )
        plugin._background_post_resource_pressure = lambda: {
            "level": "normal",
            "worker_cap": 6,
            "reason": "unit_test_normal_pressure",
        }
        plugin._proactive_candidate_sessions = {
            "s-missing-origin": {
                "session_key": "s-missing-origin",
                "unified_msg_origin": "",
                "last_seen_at": plugin._observed_now(),
                "last_user_text_excerpt": "缺少 origin。",
            },
        }

        async def fail_if_dispatched(self, *args, **kwargs):
            raise AssertionError("missing origin candidate must not dispatch")

        bind_async(plugin, "request_proactive_speech_dispatch", fail_if_dispatched)

        result = asyncio.run(plugin._run_proactive_scheduler_once())

        self.assertEqual(result["checked"], 0)
        self.assertEqual(result["dispatched"], 0)


    def test_terminate_clears_proactive_scheduler_state(self):
        plugin = new_plugin({"enable_proactive_speech_scheduler": True})
        plugin._ensure_proactive_scheduler_state()
        plugin._proactive_candidate_sessions = {
            "s-old": {
                "session_key": "s-old",
                "unified_msg_origin": "s-old",
                "last_seen_at": plugin._observed_now(),
            },
        }
        plugin._proactive_scheduler_locks["s-old"] = asyncio.Lock()

        asyncio.run(plugin.terminate())

        self.assertIsNone(plugin._proactive_scheduler_task)
        self.assertEqual(plugin._proactive_candidate_sessions, {})
        self.assertEqual(plugin._proactive_scheduler_locks, {})


    def test_sticker_send_is_blocked_when_llm_consistency_rejects_candidate(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin()
        plugin.context = FakeContext()

        async def reject_sticker(self, *args, **kwargs):
            return {
                "approved": False,
                "reason": "candidate mood conflicts with reply",
                "source": "unit_test",
            }

        bind_async(plugin, "_judge_sticker_consistency", reject_sticker)
        plan = {
            "session_key": "s-sticker-check",
            "message_parts": [
                {"index": 0, "text": "那、那个……先慢慢来。", "delay_before_seconds": 0.0},
            ],
            "sticker": {
                "should_send": True,
                "intent": "comfort",
                "candidate": {
                    "path": "C:/tmp/angry.gif",
                    "name": "angry",
                    "tags": ["angry"],
                },
            },
        }

        result = asyncio.run(
            plugin._send_realtime_chat_plan(
                FakeEvent("s-sticker-check"),
                plan,
                source="unit_test",
            ),
        )

        self.assertEqual(len(sent), 1)
        self.assertEqual(result["sticker_result"]["sent"], False)
        self.assertEqual(result["sticker_result"]["blocked_reason"], "llm_rejected")
