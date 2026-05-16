import asyncio
import collections
import tempfile
import sys
import threading
import time
import types
from pathlib import Path
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


class AstrBotLifecyclePart09(AstrBotLifecycleTests):
    def test_realtime_chat_plan_sends_url_sticker_as_image_message(self):
        sent = []

        class StrictMessageChain:
            def __init__(self):
                self.parts = []

            def message(self, text):
                self.parts.append(("message", text))
                return self

            def file_image(self, path):
                self.parts.append(("file_image", path))
                return self

            def __str__(self):
                return "|".join(f"{kind}:{value}" for kind, value in self.parts)

        class FakeImage:
            @staticmethod
            def fromURL(url):
                return ("image_url_component", url)

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message), list(getattr(message, "parts", []))))
                return {"ok": True}

        plugin = new_plugin()
        plugin.context = FakeContext()

        async def approve_sticker(self, *args, **kwargs):
            return {
                "approved": True,
                "reason": "unit test accepts candidate",
                "source": "unit_test",
            }

        bind_async(plugin, "_judge_sticker_consistency", approve_sticker)
        plan = {
            "session_key": "s-url-sticker",
            "message_parts": [
                {"index": 0, "text": "look", "delay_before_seconds": 0.0},
            ],
            "sticker": {
                "should_send": True,
                "intent": "playful",
                "candidate": {
                    "url": "https://example.test/sylanne.png",
                    "name": "url-sticker",
                },
            },
        }

        event_module = sys.modules["astrbot.api.event"]
        old_chain = event_module.MessageChain
        component_module = types.ModuleType("astrbot.api.message_components")
        component_module.Image = FakeImage
        old_component_module = sys.modules.get("astrbot.api.message_components")
        event_module.MessageChain = StrictMessageChain
        sys.modules["astrbot.api.message_components"] = component_module
        try:
            result = asyncio.run(
                plugin._send_realtime_chat_plan(
                    FakeEvent("s-url-sticker"),
                    plan,
                    source="unit_test",
                ),
            )
        finally:
            event_module.MessageChain = old_chain
            if old_component_module is None:
                sys.modules.pop("astrbot.api.message_components", None)
            else:
                sys.modules["astrbot.api.message_components"] = old_component_module

        self.assertEqual(result["sticker_result"]["sent"], True)
        self.assertTrue(
            any(
                ("image_url_component", "https://example.test/sylanne.png") in parts
                for _, _, parts in sent
            ),
        )
        self.assertFalse(any("[表情包]" in text for _, text, _ in sent))


    def test_realtime_chat_plan_reports_missing_sticker_candidates(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "enable_realtime_chat": True,
                "enable_sticker_reaction": True,
                "sticker_local_root": "",
                "sticker_learn_user_images": False,
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()

        async def no_learned_stickers(self, session_key):
            return []

        bind_async(plugin, "_load_sticker_memory", no_learned_stickers)

        plan = asyncio.run(
            plugin.get_realtime_chat_plan(
                "s-no-sticker-candidates",
                "好耶，今天进展不错！",
            ),
        )
        result = asyncio.run(
            plugin._send_realtime_chat_plan(
                FakeEvent("s-no-sticker-candidates"),
                plan,
                source="unit_test",
            ),
        )

        self.assertEqual(plan["sticker"]["reason"], "no_sticker_candidates")
        self.assertEqual(result["sticker_result"]["sent"], False)
        self.assertEqual(
            result["sticker_result"]["blocked_reason"],
            "no_sticker_candidates",
        )
        self.assertEqual(len(sent), plan["message_count"])


    def test_sticker_auto_download_uses_cache_when_local_root_is_empty(self):
        plugin = new_plugin(
            {
                "enable_sticker_reaction": True,
                "sticker_local_root": "",
                "sticker_auto_download_enabled": True,
                "sticker_auto_download_repo_url": "https://example.test/stickers.git",
                "sticker_auto_download_cache_dir": "",
                "sticker_learn_user_images": False,
            },
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            cached_root = base / "auto-stickers"
            (cached_root / "pack").mkdir(parents=True)
            sticker_path = cached_root / "pack" / "happy.png"
            sticker_path.write_bytes(b"fake image")
            plugin._test_sticker_cache_base = base
            calls = []

            def fake_ensure(settings):
                calls.append(settings.auto_download_repo_url)
                return cached_root

            plugin._ensure_auto_downloaded_sticker_root = fake_ensure

            candidates = asyncio.run(plugin._sticker_candidates("s-auto-sticker"))

        self.assertEqual(calls, ["https://example.test/stickers.git"])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["name"], "happy")
        self.assertIn("auto-stickers", candidates[0]["path"])


    def test_sticker_auto_download_skips_when_learned_candidates_exist(self):
        plugin = new_plugin(
            {
                "enable_sticker_reaction": True,
                "sticker_local_root": "",
                "sticker_auto_download_enabled": True,
                "sticker_learn_user_images": True,
            },
        )
        calls = []

        async def learned_stickers(self, session_key):
            return [
                {
                    "id": "learned-1",
                    "origin": "learned_user_image",
                    "path": "https://example.test/learned.png",
                    "name": "learned",
                },
            ]

        def fail_ensure(settings):
            calls.append(settings.auto_download_repo_url)
            raise AssertionError("learned stickers should be used before auto-download")

        bind_async(plugin, "_load_sticker_memory", learned_stickers)
        plugin._ensure_auto_downloaded_sticker_root = fail_ensure

        candidates = asyncio.run(plugin._sticker_candidates("s-learned-first"))

        self.assertEqual(calls, [])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["origin"], "learned_user_image")


    def test_sticker_observation_extracts_onebot_nested_image_data(self):
        plugin = new_plugin({"sticker_learn_user_images": True})
        event = FakeEvent("s-onebot-nested")
        event.message_obj = SimpleNamespace(
            message=[
                {
                    "type": "image",
                    "data": {
                        "url": "https://example.test/sticker.png",
                        "file": "cache/sticker.png",
                        "file_id": "fid-123",
                        "summary": "happy",
                    },
                },
            ],
        )

        observations = plugin._extract_sticker_observations_from_event(event)

        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["url"], "https://example.test/sticker.png")
        self.assertEqual(observations[0]["path"], "cache/sticker.png")
        self.assertEqual(observations[0]["file_id"], "fid-123")


    def test_sticker_observation_classifies_napcat_mface_as_sticker(self):
        plugin = new_plugin({"sticker_learn_user_images": True})
        event = FakeEvent("s-napcat-mface")
        event.message_obj = SimpleNamespace(
            message=[
                {
                    "type": "mface",
                    "data": {
                        "url": "https://example.test/mface.gif",
                        "emoji_id": "emoji-123",
                        "summary": "[动画表情]捂脸",
                    },
                },
            ],
        )

        observations = plugin._extract_sticker_observations_from_event(event)

        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["media_kind"], "sticker")
        self.assertEqual(observations[0]["type"], "mface")
        self.assertEqual(observations[0]["url"], "https://example.test/mface.gif")
        self.assertEqual(observations[0]["file_id"], "emoji-123")
        self.assertIn("捂脸", observations[0]["name"])


    def test_current_sticker_payload_is_injected_as_cautious_context(self):
        plugin = new_plugin(
            {
                "inject_state": False,
                "use_llm_assessor": False,
                "enable_realtime_chat": False,
                "enable_sylanne_memory": False,
                "enable_sticker_reaction": False,
                "sticker_learn_user_images": False,
            },
        )
        event = FakeEvent("s-current-sticker", message="", platform_name="aiocqhttp")
        event.message_obj = SimpleNamespace(
            message=[
                {
                    "type": "mface",
                    "data": {
                        "url": "https://example.test/current.gif",
                        "emoji_id": "emoji-456",
                        "summary": "[动画表情]拍桌",
                    },
                },
            ],
        )
        request = fake_request(session_id="s-current-sticker", prompt="")

        asyncio.run(plugin.on_llm_request(event, request))

        injected = "\n".join(self._request_text_parts(request))
        self.assertFalse(event.stopped)
        self.assertIn("sylanne_current_user_media", injected)
        self.assertIn("表情包", injected)
        self.assertIn("拍桌", injected)
        self.assertIn("不要凭空描述", injected)


    def test_sticker_data_without_outer_type_uses_summary_for_kind(self):
        plugin = new_plugin({"sticker_learn_user_images": True})

        observation = plugin._sticker_observation_from_message_part(
            {
                "url": "https://example.test/raw-data.gif",
                "emoji_id": "emoji-789",
                "summary": "[动画表情]疑惑",
            },
        )

        self.assertIsNotNone(observation)
        self.assertEqual(observation["media_kind"], "sticker")
        self.assertIn("疑惑", observation["name"])


    def test_bad_learned_sticker_candidate_does_not_block_auto_download(self):
        plugin = new_plugin(
            {
                "enable_sticker_reaction": True,
                "sticker_local_root": "",
                "sticker_auto_download_enabled": True,
                "sticker_auto_download_repo_url": "https://example.test/stickers.git",
                "sticker_learn_user_images": True,
            },
        )

        async def bad_learned_stickers(self, session_key):
            return [
                {
                    "id": "bad-empty",
                    "origin": "observed_user_sticker",
                    "name": "empty metadata only",
                },
            ]

        bind_async(plugin, "_load_sticker_memory", bad_learned_stickers)
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            cached_root = base / "auto-stickers"
            (cached_root / "pack").mkdir(parents=True)
            (cached_root / "pack" / "happy.png").write_bytes(b"fake image")
            calls = []

            def fake_ensure(settings):
                calls.append(settings.auto_download_repo_url)
                return cached_root

            plugin._ensure_auto_downloaded_sticker_root = fake_ensure

            candidates = asyncio.run(plugin._sticker_candidates("s-bad-learned"))

        self.assertEqual(calls, ["https://example.test/stickers.git"])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["name"], "happy")


    def test_empty_sticker_index_cache_refreshes_when_files_appear(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plugin = new_plugin(
                {
                    "enable_sticker_reaction": True,
                    "sticker_local_root": str(root),
                    "sticker_learn_user_images": False,
                },
            )

            first = asyncio.run(plugin._sticker_candidates("s-empty-cache"))
            (root / "late.png").write_bytes(b"fake image")
            second = asyncio.run(plugin._sticker_candidates("s-empty-cache"))

        self.assertEqual(first, [])
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0]["name"], "late")


    def test_empty_sticker_index_uses_cache_instead_of_rescanning_same_directory(self):
        import main

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plugin = new_plugin(
                {
                    "enable_sticker_reaction": True,
                    "sticker_local_root": str(root),
                    "sticker_learn_user_images": False,
                    "sticker_index_cache_ttl_seconds": 86400.0,
                },
            )
            original = main.index_local_stickers
            calls = []

            def fake_index(settings):
                calls.append(settings.local_root)
                return []

            main.index_local_stickers = fake_index
            try:
                first = asyncio.run(plugin._sticker_candidates("s-empty-cache-repeat"))
                second = asyncio.run(plugin._sticker_candidates("s-empty-cache-repeat"))
            finally:
                main.index_local_stickers = original

        self.assertEqual(first, [])
        self.assertEqual(second, [])
        self.assertEqual(calls, [str(root)])


    def test_sticker_index_scan_runs_off_event_loop_thread(self):
        import main

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plugin = new_plugin(
                {
                    "enable_sticker_reaction": True,
                    "sticker_local_root": str(root),
                    "sticker_learn_user_images": False,
                },
            )
            original = main.index_local_stickers
            scan_threads = []

            def fake_index(settings):
                scan_threads.append(threading.get_ident())
                return []

            async def collect():
                loop_thread = threading.get_ident()
                candidates = await plugin._sticker_candidates("s-threaded-index")
                return loop_thread, candidates

            main.index_local_stickers = fake_index
            try:
                loop_thread, candidates = asyncio.run(collect())
            finally:
                main.index_local_stickers = original

        self.assertEqual(candidates, [])
        self.assertEqual(len(scan_threads), 1)
        self.assertNotEqual(scan_threads[0], loop_thread)


    def test_sticker_auto_download_reuses_completed_repo_even_when_pack_filter_misses(self):
        plugin = new_plugin(
            {
                "enable_sticker_reaction": True,
                "sticker_local_root": "",
                "sticker_auto_download_enabled": True,
                "sticker_auto_download_repo_url": "https://example.test/stickers.git",
                "sticker_selected_packs": "missing-pack",
                "sticker_learn_user_images": False,
            },
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            plugin._test_sticker_cache_base = base
            settings = plugin._sticker_settings()
            target = base / plugin._sticker_auto_download_repo_slug(settings.auto_download_repo_url)
            (target / "pack").mkdir(parents=True)
            (target / "pack" / "happy.png").write_bytes(b"fake image")
            (target / ".git").mkdir()
            calls = []

            def fail_download(repo_url, target_root, settings):
                calls.append(repo_url)
                raise AssertionError("completed sticker repo should not be cloned again")

            plugin._download_sticker_repo = fail_download

            candidates = asyncio.run(plugin._sticker_candidates("s-filter-miss"))

        self.assertEqual(calls, [])
        self.assertEqual(candidates, [])


    def test_sticker_consistency_parser_treats_string_false_as_rejected(self):
        plugin = new_plugin()

        judgement = plugin._parse_sticker_consistency_judgement(
            '{"approved": "false", "reason": "语气不一致"}',
        )

        self.assertIsNotNone(judgement)
        self.assertFalse(judgement["approved"])
        self.assertEqual(judgement["source"], "llm_consistency_gate")


    def test_sticker_consistency_skips_llm_when_local_gate_approves(self):
        plugin = new_plugin(
            {
                "use_llm_assessor": True,
                "sticker_llm_consistency_check_enabled": True,
            },
        )
        calls = []

        async def fake_provider_id(self, event):
            return "provider"

        async def fail_call_llm(self, **kwargs):
            calls.append(kwargs)
            raise AssertionError("approved local sticker should not call LLM")

        bind_async(plugin, "_provider_id", fake_provider_id)
        bind_async(plugin, "_call_internal_assessor_llm", fail_call_llm)

        judgement = asyncio.run(
            plugin._judge_sticker_consistency(
                FakeEvent("s-sticker-local-fast"),
                plan={
                    "message_parts": [
                        {"text": "今天进度不错，给你一个开心的表情。"},
                    ],
                },
                sticker={"intent": "celebrate"},
                candidate={
                    "name": "happy.png",
                    "tags": ["happy", "celebrate"],
                },
            ),
        )

        self.assertEqual(calls, [])
        self.assertTrue(judgement["approved"])
        self.assertEqual(judgement["source"], "local_consistency_gate")


    def test_sticker_consistency_uses_fast_assessor_for_llm_gate(self):
        plugin = new_plugin(
            {
                "use_llm_assessor": True,
                "fast_assessor_enabled": True,
                "sticker_llm_consistency_check_enabled": True,
                "fast_assessor_provider_id": "fast-json-provider",
                "fast_assessor_timeout_seconds": 1.25,
                "fast_assessor_temperature": 0.0,
            },
        )
        calls = []

        async def fake_provider_id(self, event):
            return "regular-provider"

        async def fake_call_llm(
            self,
            *,
            provider_id,
            prompt,
            system_prompt,
            temperature=None,
            timeout_seconds=None,
        ):
            calls.append((provider_id, prompt, system_prompt, temperature, timeout_seconds))
            return SimpleNamespace(
                completion_text='{"approved": true, "reason": "语气一致"}',
            )

        bind_async(plugin, "_provider_id", fake_provider_id)
        bind_async(plugin, "_call_internal_assessor_llm", fake_call_llm)

        judgement = asyncio.run(
            plugin._judge_sticker_consistency(
                FakeEvent("s-sticker-fast-assessor"),
                plan={
                    "message_parts": [
                        {"text": "我有点生气，不想笑。"},
                    ],
                },
                sticker={"intent": "celebrate"},
                candidate={
                    "name": "angry.png",
                    "tags": ["angry"],
                },
            ),
        )

        self.assertEqual(calls[0][0], "fast-json-provider")
        self.assertEqual(calls[0][3], 0.0)
        self.assertEqual(calls[0][4], 1.25)
        self.assertTrue(judgement["approved"])


    def test_fast_assessor_provider_requires_explicit_switch(self):
        plugin = new_plugin(
            {
                "use_llm_assessor": True,
                "sticker_llm_consistency_check_enabled": True,
                "fast_assessor_provider_id": "fast-json-provider",
            },
        )
        calls = []

        async def fake_call_llm(
            self,
            *,
            provider_id,
            prompt,
            system_prompt,
            temperature=None,
            timeout_seconds=None,
        ):
            calls.append((provider_id, prompt, system_prompt, temperature, timeout_seconds))
            return SimpleNamespace(
                completion_text='{"approved": true, "reason": "should not be called"}',
            )

        bind_async(plugin, "_call_internal_assessor_llm", fake_call_llm)

        judgement = asyncio.run(
            plugin._judge_sticker_consistency(
                FakeEvent("s-sticker-fast-disabled"),
                plan={
                    "message_parts": [
                        {"text": "我有点生气，不想笑。"},
                    ],
                },
                sticker={"intent": "celebrate"},
                candidate={
                    "name": "angry.png",
                    "tags": ["angry"],
                },
            ),
        )

        self.assertEqual(calls, [])
        self.assertFalse(judgement["approved"])
        self.assertEqual(judgement["source"], "local_consistency_gate")


    def test_proactive_cold_reply_is_recorded_as_lifelike_feedback(self):
        plugin = new_plugin()
        plugin._proactive_dispatch_audit = {
            "s-cold": collections.deque(
                [
                    {
                        "sent": True,
                        "sent_at": 100.0,
                        "feedback_status": "pending",
                        "feedback_window_seconds": 10.0,
                        "need_mode": "playful_ping",
                    },
                ],
                maxlen=24,
            ),
        }
        observations = []

        async def fake_observe_lifelike_text(self, event_or_session=None, text="", **kwargs):
            observations.append({"text": text, **kwargs})
            return {"ok": True}

        bind_async(plugin, "observe_lifelike_text", fake_observe_lifelike_text)

        asyncio.run(
            plugin._observe_proactive_dispatch_feedback(
                "s-cold",
                "嗯",
                observed_at=125.0,
            ),
        )

        audit = plugin._proactive_dispatch_audit["s-cold"][-1]
        self.assertEqual(audit["feedback_status"], "cold_reply")
        self.assertEqual(observations[0]["source"], "proactive_feedback")
        self.assertIn("更谨慎", observations[0]["text"])


    def test_realtime_chat_dispatch_dry_run_does_not_send(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, message))

        plugin = new_plugin({"enable_sticker_reaction": False})
        plugin.context = FakeContext()

        result = asyncio.run(
            plugin.request_realtime_chat_dispatch(
                FakeEvent("s-realtime-dry"),
                "第一句。第二句。",
                dry_run=True,
            ),
        )

        self.assertFalse(result["sent"])
        self.assertEqual(result["blocked_reason"], "dry_run")
        self.assertEqual(sent, [])


    def test_realtime_chat_dispatch_sends_parts_in_order(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "enable_realtime_chat": True,
                "runtime_parameter_debug_override_enabled": True,
                "enable_sticker_reaction": False,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()

        result = asyncio.run(
            plugin.request_realtime_chat_dispatch(
                FakeEvent("s-realtime-send"),
                "第一句。第二句！",
                dry_run=False,
            ),
        )

        self.assertTrue(result["sent"])
        self.assertEqual([origin for origin, _ in sent], ["s-realtime-send", "s-realtime-send"])
        self.assertIn("第一句", sent[0][1])
        self.assertIn("第二句", sent[1][1])


    def test_realtime_chat_explicit_dispatch_still_respects_cooldown(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "enable_realtime_chat": True,
                "runtime_parameter_debug_override_enabled": True,
                "enable_sticker_reaction": False,
                "realtime_chat_session_cooldown_seconds": 9999.0,
            },
        )
        plugin.context = FakeContext()
        plugin._last_realtime_chat_adaptive_settings = {
            "s-dispatch-cooldown": {
                "realtime_chat": {
                    "values": {"valence": 0.2},
                    "restraint": 0.0,
                },
            },
        }
        plugin._realtime_chat_last_sent = {"s-dispatch-cooldown": time.time()}

        result = asyncio.run(
            plugin.request_realtime_chat_dispatch(
                FakeEvent("s-dispatch-cooldown"),
                "第一句。第二句。",
                dry_run=False,
            ),
        )

        self.assertFalse(result["sent"])
        self.assertEqual(result["blocked_reason"], "cooldown_active")
        self.assertEqual(sent, [])


    def test_on_llm_response_intercepts_completion_and_schedules_realtime_send(self):
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
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        response = SimpleNamespace(completion_text="第一句。第二句。")

        event = FakeEvent("s-intercept", platform_name="aiocqhttp")

        async def run_response():
            await plugin.on_llm_response(event, response)
            await self._await_background_tasks(plugin)

        asyncio.run(run_response())

        self.assertIn("sylanne_realtime_delivery_status", response.completion_text)
        self.assertIn("delivery_status=pending_dispatch", response.completion_text)
        self.assertIn("planned_parts=2", response.completion_text)
        self.assertIn("这不等于已经全部发给用户", response.completion_text)
        self.assertEqual(
            getattr(response, "_sylanne_intercepted_completion_text", ""),
            "第一句。第二句。",
        )
        self.assertTrue(event.stopped)
        self.assertEqual(len(sent), 2)
        self.assertEqual(assessment_calls[0]["current_text"], "第一句。第二句。")
        self.assertEqual(saves[0][0], "s-intercept")


    def test_on_llm_response_repeated_hook_call_sends_realtime_reply_once(self):
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
        response = SimpleNamespace(completion_text="重复接管第一句。重复接管第二句。")

        async def run_response_twice():
            first_event = FakeEvent("s-intercept-once", platform_name="aiocqhttp")
            await plugin.on_llm_response(first_event, response)
            await self._await_background_tasks(plugin)
            first_sent_count = len(sent)
            second_event = FakeEvent("s-intercept-once", platform_name="aiocqhttp")
            await plugin.on_llm_response(second_event, response)
            await self._await_background_tasks(plugin)
            duplicate_response = SimpleNamespace(
                completion_text="重复接管第一句。重复接管第二句。",
            )
            third_event = FakeEvent("s-intercept-once", platform_name="aiocqhttp")
            await plugin.on_llm_response(third_event, duplicate_response)
            await self._await_background_tasks(plugin)
            return first_event, second_event, third_event, duplicate_response, first_sent_count

        (
            first_event,
            second_event,
            third_event,
            duplicate_response,
            first_sent_count,
        ) = asyncio.run(run_response_twice())

        self.assertTrue(first_event.stopped)
        self.assertTrue(second_event.stopped)
        self.assertTrue(third_event.stopped)
        self.assertEqual(len(sent), first_sent_count)
        self.assertEqual(first_sent_count, 2)
        sent_text = "\n".join(item[1] for item in sent)
        self.assertNotIn("sylanne_realtime_delivery_status", sent_text)
        self.assertEqual(
            getattr(response, "_sylanne_intercepted_completion_text", ""),
            "重复接管第一句。重复接管第二句。",
        )
        self.assertEqual(
            getattr(duplicate_response, "_sylanne_intercepted_completion_text", ""),
            "重复接管第一句。重复接管第二句。",
        )
        queue = plugin._realtime_assistant_history_shadow_cache()["s-intercept-once"]
        self.assertEqual(len(queue), 1)


    def test_on_llm_response_does_not_intercept_tool_call_response(self):
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
            completion_text="我需要调用工具查一下。",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "query_sylanne_memory", "arguments": "{}"},
                },
            ],
        )
        plugin._conversation_input_epoch = {"s-tool-call": 1}
        plugin._record_conversation_pending_response_epoch("s-tool-call", 1)
        event = FakeEvent("s-tool-call", platform_name="aiocqhttp")

        asyncio.run(plugin.on_llm_response(event, response))

        self.assertFalse(event.stopped)
        self.assertEqual(response.completion_text, "我需要调用工具查一下。")
        self.assertFalse(hasattr(response, "_sylanne_intercepted_completion_text"))
        self.assertEqual(sent, [])
        self.assertEqual(
            list(plugin._conversation_pending_response_epochs["s-tool-call"]),
            [1],
        )


    def test_external_tool_call_response_is_left_to_agent_loop(self):
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
            completion_text="",
            choices=[
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "call_img_1",
                                "type": "function",
                                "function": {
                                    "name": "aiimg_generate",
                                    "arguments": '{"mode":"edit_ref","prompt":"match face style"}',
                                },
                            },
                        ],
                    },
                },
            ],
        )
        plugin._conversation_input_epoch = {"s-external-tool-call": 1}
        plugin._record_conversation_pending_response_epoch("s-external-tool-call", 1)
        event = FakeEvent("s-external-tool-call", platform_name="aiocqhttp")

        asyncio.run(plugin.on_llm_response(event, response))

        self.assertFalse(event.stopped)
        self.assertEqual(response.completion_text, "")
        self.assertFalse(hasattr(response, "_sylanne_intercepted_completion_text"))
        self.assertEqual(sent, [])
        self.assertEqual(
            list(plugin._conversation_pending_response_epochs["s-external-tool-call"]),
            [1],
        )
