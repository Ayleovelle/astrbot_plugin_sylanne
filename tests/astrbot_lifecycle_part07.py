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


class AstrBotLifecyclePart07(AstrBotLifecycleTests):
    def test_proactive_scheduler_dispatches_registered_session_when_enabled(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_proactive_speech_dispatch": True,
                "enable_proactive_speech_scheduler": True,
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
                "enable_sticker_reaction": False,
            },
        )
        plugin._background_post_resource_pressure = lambda: {
            "level": "normal",
            "worker_cap": 6,
            "reason": "unit_test_normal_pressure",
        }
        dispatched = []

        async def fake_dispatch(self, event_or_session, **kwargs):
            dispatched.append(
                {
                    "event": event_or_session,
                    "candidate_context": kwargs.get("candidate_context", ""),
                    "dry_run": kwargs.get("dry_run"),
                },
            )
            return {
                "schema_version": "astrbot.proactive_dispatch_result.v1",
                "kind": "proactive_dispatch_result",
                "session_key": "s-proactive-run",
                "sent": True,
                "blocked_reason": "",
            }

        bind_async(plugin, "request_proactive_speech_dispatch", fake_dispatch)

        async def run_once():
            await plugin.on_llm_request(
                FakeEvent("s-proactive-run", message="这周项目进度有点卡。"),
                fake_request(session_id="s-proactive-run", prompt="这周项目进度有点卡。"),
            )
            result = await plugin._run_proactive_scheduler_once()
            await plugin.terminate()
            return result

        result = asyncio.run(run_once())

        self.assertEqual(result["checked"], 1)
        self.assertEqual(result["dispatched"], 1)
        self.assertEqual(dispatched[0]["event"].unified_msg_origin, "s-proactive-run")
        self.assertFalse(dispatched[0]["dry_run"])
        self.assertIn("最近用户消息", dispatched[0]["candidate_context"])


    def test_proactive_scheduler_wakes_on_candidate_and_exits_when_idle(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_proactive_speech_dispatch": False,
                "enable_proactive_speech_scheduler": True,
            },
        )
        plugin._background_post_resource_pressure = lambda: {
            "level": "normal",
            "worker_cap": 6,
            "reason": "unit_test_normal_pressure",
        }
        calls = []

        async def fake_run_once(plugin_self):
            calls.append(len(calls))
            if len(calls) == 1:
                plugin_self._proactive_candidate_sessions.clear()
                return {
                    "schema_version": "astrbot.proactive_scheduler_result.v1",
                    "enabled": True,
                    "checked": 1,
                    "dispatched": 0,
                    "skipped": 0,
                    "candidate_count": 1,
                }
            return {
                "schema_version": "astrbot.proactive_scheduler_result.v1",
                "enabled": True,
                "checked": 0,
                "dispatched": 0,
                "skipped": 0,
                "candidate_count": 0,
            }

        bind_async(plugin, "_run_proactive_scheduler_once", fake_run_once)

        async def run_scheduler_lifecycle():
            import main

            original_wake = main.PROACTIVE_SCHEDULER_WAKE_DELAY_SECONDS
            original_idle = main.PROACTIVE_SCHEDULER_IDLE_DELAY_SECONDS
            try:
                main.PROACTIVE_SCHEDULER_WAKE_DELAY_SECONDS = 0.0
                main.PROACTIVE_SCHEDULER_IDLE_DELAY_SECONDS = 0.0
                await plugin.on_llm_request(
                    FakeEvent("s-proactive-idle-exit", message="wake scheduler"),
                    fake_request(session_id="s-proactive-idle-exit", prompt="wake scheduler"),
                )
                task = plugin._proactive_scheduler_task
                if task is not None:
                    await asyncio.wait_for(task, timeout=1.0)
            finally:
                main.PROACTIVE_SCHEDULER_WAKE_DELAY_SECONDS = original_wake
                main.PROACTIVE_SCHEDULER_IDLE_DELAY_SECONDS = original_idle

        asyncio.run(run_scheduler_lifecycle())

        self.assertGreaterEqual(len(calls), 1)
        self.assertIsNone(plugin._proactive_scheduler_task)
        self.assertEqual(plugin._proactive_scheduler_idle_rounds, 0)


    def test_proactive_scheduler_context_uses_recent_window_not_only_last_message(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_proactive_speech_dispatch": True,
                "enable_proactive_speech_scheduler": True,
            },
        )
        plugin._background_post_resource_pressure = lambda: {
            "level": "normal",
            "worker_cap": 6,
            "reason": "unit_test_normal_pressure",
        }
        dispatched = []

        async def fake_dispatch(self, event_or_session, **kwargs):
            dispatched.append(kwargs.get("candidate_context", ""))
            return {
                "schema_version": "astrbot.proactive_dispatch_result.v1",
                "kind": "proactive_dispatch_result",
                "session_key": "s-proactive-window",
                "sent": True,
                "blocked_reason": "",
            }

        bind_async(plugin, "request_proactive_speech_dispatch", fake_dispatch)

        async def run_window():
            for text in (
                "这周桥隧交叉实验卡在传感器数据清洗。",
                "我明天要给导师汇报，但是有点没底。",
                "如果晚上我没动静，你可以轻轻提醒我整理图表。",
            ):
                await plugin.on_llm_request(
                    FakeEvent("s-proactive-window", message=text, sender_id="u1"),
                    fake_request(session_id="s-proactive-window", prompt=text),
                )
            return await plugin._run_proactive_scheduler_once()

        result = asyncio.run(run_window())

        self.assertEqual(result["checked"], 1)
        context = dispatched[0]
        self.assertIn("近期上下文摘要", context)
        self.assertIn("传感器数据清洗", context)
        self.assertIn("导师汇报", context)
        self.assertIn("整理图表", context)
        self.assertGreater(len(context), 160)


    def test_proactive_scheduler_context_can_include_sylanne_memory_summary(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_proactive_speech_dispatch": True,
                "enable_proactive_speech_scheduler": True,
            },
        )
        plugin._background_post_resource_pressure = lambda: {
            "level": "normal",
            "worker_cap": 6,
            "reason": "unit_test_normal_pressure",
        }
        from memory_engine import MemoryRecord, SylanneMemoryState

        class FakeLivingMemory:
            async def search_memory(self, session_key=None, query="", limit=3):
                raise AssertionError("proactive scheduler must use Sylanne memory")

        class FakeContext:
            def get_registered_star(self, name):
                if name == "astrbot_plugin_livingmemory":
                    return SimpleNamespace(activated=True, star_cls=FakeLivingMemory())
                return None

        plugin.context = FakeContext()
        plugin._observed_now = lambda: 20.0
        state = SylanneMemoryState.initial(now=0.0)
        state.records.extend(
            [
                MemoryRecord(
                    text="用户之前说过，今晚改论文图表时容易焦虑。",
                    summary="用户今晚改论文图表时容易焦虑。",
                    session_key="s-proactive-memory",
                    created_at=10.0,
                    updated_at=10.0,
                    depth=0.9,
                    confidence=0.82,
                ),
                MemoryRecord(
                    text="用户喜欢被轻轻提醒，而不是被命令。",
                    summary="用户喜欢被轻轻提醒，而不是被命令。",
                    session_key="s-proactive-memory",
                    created_at=11.0,
                    updated_at=11.0,
                    depth=0.86,
                    confidence=0.8,
                ),
            ],
        )
        plugin._sylanne_memory_cache["s-proactive-memory"] = state
        dispatched = []

        async def fake_dispatch(self, event_or_session, **kwargs):
            dispatched.append(kwargs.get("candidate_context", ""))
            return {
                "schema_version": "astrbot.proactive_dispatch_result.v1",
                "kind": "proactive_dispatch_result",
                "session_key": "s-proactive-memory",
                "sent": True,
                "blocked_reason": "",
            }

        bind_async(plugin, "request_proactive_speech_dispatch", fake_dispatch)

        async def run_memory_context():
            await plugin.on_llm_request(
                FakeEvent("s-proactive-memory", message="今晚我可能要继续改图。", sender_id="u1"),
                fake_request(session_id="s-proactive-memory", prompt="今晚我可能要继续改图。"),
            )
            return await plugin._run_proactive_scheduler_once()

        result = asyncio.run(run_memory_context())

        self.assertEqual(result["checked"], 1)
        context = dispatched[0]
        self.assertIn("Sylanne 自有记忆召回摘要", context)
        self.assertIn("论文图表", context)
        self.assertIn("轻轻提醒", context)


    def test_proactive_scheduler_context_includes_recent_request_context_excerpt(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_proactive_speech_dispatch": True,
                "enable_proactive_speech_scheduler": True,
            },
        )
        plugin._background_post_resource_pressure = lambda: {
            "level": "normal",
            "worker_cap": 6,
            "reason": "unit_test_normal_pressure",
        }
        dispatched = []

        async def fake_dispatch(self, event_or_session, **kwargs):
            dispatched.append(kwargs.get("candidate_context", ""))
            return {
                "schema_version": "astrbot.proactive_dispatch_result.v1",
                "kind": "proactive_dispatch_result",
                "session_key": "s-proactive-context-excerpt",
                "sent": True,
                "blocked_reason": "",
            }

        bind_async(plugin, "request_proactive_speech_dispatch", fake_dispatch)

        async def run_context_excerpt():
            request = fake_request(
                session_id="s-proactive-context-excerpt",
                prompt="那你有什么想对他们说的吗",
            )
            request.contexts = [
                {
                    "role": "user",
                    "content": "刚才说的他们，是插件的其他用户，不是恋爱关系里的其他人。",
                },
                {
                    "role": "assistant",
                    "content": "我理解了，是想对插件使用者说一点话。",
                },
            ]
            await plugin.on_llm_request(
                FakeEvent(
                    "s-proactive-context-excerpt",
                    message="那你有什么想对他们说的吗",
                    sender_id="u1",
                ),
                request,
            )
            return await plugin._run_proactive_scheduler_once()

        result = asyncio.run(run_context_excerpt())

        self.assertEqual(result["checked"], 1)
        context = dispatched[0]
        self.assertIn("近期上下文摘要", context)
        self.assertIn("最近请求上下文", context)
        self.assertIn("插件的其他用户", context)


    def test_proactive_scheduler_marks_unanswered_before_repeating_topic(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_proactive_speech_dispatch": True,
                "enable_proactive_speech_scheduler": True,
            },
        )
        plugin._background_post_resource_pressure = lambda: {
            "level": "normal",
            "worker_cap": 6,
            "reason": "unit_test_normal_pressure",
        }
        plugin._observed_now = lambda: 1_000_000.0
        session_key = "s-proactive-unanswered"
        plugin._proactive_candidate_sessions[session_key] = {
            "schema_version": "astrbot.proactive_candidate_session.v1",
            "session_key": session_key,
            "unified_msg_origin": session_key,
            "last_seen_at": 999_000.0,
            "last_user_text_excerpt": "咖啡啊",
            "candidate_context_excerpt": "用户刚才说喝了咖啡反而想睡，话题已经被主动发言追问过。",
            "speaker_id": "u1",
            "speaker_name": "哀洛芙",
        }
        plugin._proactive_dispatch_audit = {
            session_key: collections.deque(
                [
                    {
                        "sent": True,
                        "sent_at": 999_100.0,
                        "feedback_status": "pending",
                        "feedback_window_seconds": 60.0,
                        "need_mode": "progress_check",
                        "topic_text": "咖啡反而变困",
                        "topic_evidence": "上一次用户聊到咖啡",
                    },
                ],
                maxlen=24,
            ),
        }
        dispatched = []
        lifelike_observations = []
        emotion_observations = []

        async def fake_dispatch(self, event_or_session, **kwargs):
            dispatched.append(kwargs.get("candidate_context", ""))
            return {
                "schema_version": "astrbot.proactive_dispatch_result.v1",
                "kind": "proactive_dispatch_result",
                "session_key": session_key,
                "sent": False,
                "blocked_reason": "unit_test",
            }

        async def fake_observe_lifelike_text(self, event_or_session=None, text="", **kwargs):
            lifelike_observations.append({"text": text, **kwargs})
            return {"ok": True}

        async def fake_observe_emotion_text(self, event_or_session=None, text="", **kwargs):
            emotion_observations.append({"text": text, **kwargs})
            return {"ok": True}

        bind_async(plugin, "request_proactive_speech_dispatch", fake_dispatch)
        bind_async(plugin, "observe_lifelike_text", fake_observe_lifelike_text)
        bind_async(plugin, "observe_emotion_text", fake_observe_emotion_text)

        result = asyncio.run(plugin._run_proactive_scheduler_once())

        self.assertEqual(result["checked"], 1)
        audit = plugin._proactive_dispatch_audit[session_key][-1]
        self.assertEqual(audit["feedback_status"], "unanswered")
        self.assertEqual(lifelike_observations[0]["source"], "proactive_feedback")
        self.assertEqual(emotion_observations[0]["source"], "proactive_unanswered_feedback")
        self.assertFalse(emotion_observations[0]["use_llm"])
        context = dispatched[0]
        self.assertIn("上一条主动发言没有得到回应", context)
        self.assertIn("咖啡反而变困", context)
        self.assertIn("不要重复同一个话题", context)
        self.assertIn("可能是在忙、休息或暂时不方便聊天", context)
        self.assertIn("如果只是想念用户", context)


    def test_proactive_scheduler_settles_unanswered_even_when_recheck_skips_session(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_proactive_speech_dispatch": True,
                "enable_proactive_speech_scheduler": True,
            },
        )
        plugin._background_post_resource_pressure = lambda: {
            "level": "normal",
            "worker_cap": 6,
            "reason": "unit_test_normal_pressure",
        }
        plugin._observed_now = lambda: 1_000_000.0
        session_key = "s-proactive-recheck-unanswered"
        plugin._proactive_candidate_sessions[session_key] = {
            "schema_version": "astrbot.proactive_candidate_session.v1",
            "session_key": session_key,
            "unified_msg_origin": session_key,
            "last_seen_at": 999_000.0,
            "last_user_text_excerpt": "coffee",
            "speaker_id": "u1",
        }
        plugin._proactive_scheduler_last_checked[session_key] = 999_999.0
        plugin._proactive_dispatch_audit = {
            session_key: collections.deque(
                [
                    {
                        "sent": True,
                        "sent_at": 999_100.0,
                        "feedback_status": "pending",
                        "feedback_window_seconds": 60.0,
                        "need_mode": "progress_check",
                        "topic_text": "coffee sleepy",
                    },
                ],
                maxlen=24,
            ),
        }
        lifelike_observations = []
        emotion_observations = []

        async def fake_observe_lifelike_text(self, event_or_session=None, text="", **kwargs):
            lifelike_observations.append({"text": text, **kwargs})
            return {"ok": True}

        async def fake_observe_emotion_text(self, event_or_session=None, text="", **kwargs):
            emotion_observations.append({"text": text, **kwargs})
            return {"ok": True}

        bind_async(plugin, "observe_lifelike_text", fake_observe_lifelike_text)
        bind_async(plugin, "observe_emotion_text", fake_observe_emotion_text)

        result = asyncio.run(plugin._run_proactive_scheduler_once())

        self.assertEqual(result["checked"], 0)
        audit = plugin._proactive_dispatch_audit[session_key][-1]
        self.assertEqual(audit["feedback_status"], "unanswered")
        self.assertEqual(lifelike_observations[0]["source"], "proactive_feedback")
        self.assertEqual(emotion_observations[0]["source"], "proactive_unanswered_feedback")


    def test_on_llm_request_can_include_sylanne_memory_summary(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 0.3,
            },
        )
        self._bind_common_state_hooks(plugin)
        from memory_engine import MemoryRecord, SylanneMemoryState

        calls = []

        class FakeLivingMemory:
            async def search_memory(self, session_key=None, query="", limit=3):
                calls.append({"session_key": session_key, "query": query, "limit": limit})
                raise AssertionError("on_llm_request must not call LivingMemory")

        class FakeContext:
            def get_registered_star(self, name):
                if name == "astrbot_plugin_livingmemory":
                    return SimpleNamespace(activated=True, star_cls=FakeLivingMemory())
                return None

        plugin.context = FakeContext()
        state = SylanneMemoryState.initial(now=0.0)
        state.records.extend(
            [
                MemoryRecord(
                    text="用户刚才解释过，“他们”指插件的其他用户。",
                    summary="用户刚才解释过，“他们”指插件的其他用户。",
                    session_key="s-request-memory",
                    created_at=10.0,
                    updated_at=10.0,
                    depth=0.9,
                    confidence=0.84,
                ),
                MemoryRecord(
                    text="用户希望 bot 回答时不要把插件用户误会成恋爱对象。",
                    summary="用户希望 bot 回答时不要把插件用户误会成恋爱对象。",
                    session_key="s-request-memory",
                    created_at=11.0,
                    updated_at=11.0,
                    depth=0.88,
                    confidence=0.81,
                ),
            ],
        )
        plugin._sylanne_memory_cache["s-request-memory"] = state
        request = fake_request(
            session_id="s-request-memory",
            prompt="那你有什么想对他们说的吗",
        )
        request.contexts = [
            {
                "role": "user",
                "content": "不是啊，我是说插件的其他用户。",
            },
        ]

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "s-request-memory",
                    message="那你有什么想对他们说的吗",
                    sender_id="u1",
                ),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertEqual(calls, [])
        self.assertIn("sylanne_memory_recall", injected)
        self.assertIn("用户刚才解释过", injected)
        self.assertIn("不要把插件用户误会成恋爱对象", injected)


    def test_on_llm_request_can_use_configured_embedding_provider_for_memory_recall(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
                "sylanne_memory_vector_retrieval_enabled": True,
                "sylanne_memory_embedding_provider_id": "embed-a",
            },
        )
        self._bind_common_state_hooks(plugin)
        from memory_engine import MemoryRecord, SylanneMemoryState

        class FakeEmbeddingProvider:
            provider_config = {"id": "embed-a", "provider_type": "embedding"}

            async def get_embedding(self, text):
                if "needle-query" in text or "alpha beta gamma" in text:
                    return [1.0, 0.0, 0.0]
                return [0.0, 1.0, 0.0]

            async def get_embeddings(self, texts):
                return [await self.get_embedding(text) for text in texts]

            def get_dim(self):
                return 3

        provider = FakeEmbeddingProvider()

        class FakeContext:
            def get_provider_by_id(self, provider_id):
                return provider if provider_id == "embed-a" else None

            def get_all_embedding_providers(self):
                return [provider]

        plugin.context = FakeContext()
        state = SylanneMemoryState.initial(now=0.0)
        state.records.extend(
            [
                MemoryRecord(
                    memory_id="dense-hit",
                    text="alpha beta gamma",
                    summary="alpha beta gamma",
                    session_key="s-vector-request",
                    created_at=10.0,
                    updated_at=10.0,
                    depth=0.52,
                    confidence=0.64,
                    semantic_embedding=[1.0, 0.0, 0.0],
                    embedding_provider_id="embed-a",
                    embedding_updated_at=10.0,
                    embedding_text_hash="dense-hit",
                ),
                MemoryRecord(
                    memory_id="dense-miss",
                    text="delta epsilon zeta",
                    summary="delta epsilon zeta",
                    session_key="s-vector-request",
                    created_at=11.0,
                    updated_at=11.0,
                    depth=0.92,
                    confidence=0.90,
                    semantic_embedding=[0.0, 1.0, 0.0],
                    embedding_provider_id="embed-a",
                    embedding_updated_at=11.0,
                    embedding_text_hash="dense-miss",
                ),
            ],
        )
        plugin._sylanne_memory_cache["s-vector-request"] = state
        saved = []

        async def fake_save_memory(self, session_key, saved_state):
            saved.append(saved_state.to_dict())
            self._sylanne_memory_cache[session_key] = saved_state

        bind_async(plugin, "_save_sylanne_memory_state", fake_save_memory)
        request = fake_request(
            session_id="s-vector-request",
            prompt="needle-query",
        )

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "s-vector-request",
                    message="needle-query",
                    sender_id="u1",
                ),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("sylanne_memory_recall", injected)
        self.assertIn("alpha beta gamma", injected)
        self.assertNotIn("delta epsilon zeta", injected)
        self.assertTrue(saved)
        saved_records = saved[-1]["records"]
        self.assertTrue(any(record["semantic_embedding"] for record in saved_records))
        self.assertTrue(
            all(record["embedding_provider_id"] == "embed-a" for record in saved_records),
        )
