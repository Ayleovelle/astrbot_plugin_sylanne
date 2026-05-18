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


class AstrBotLifecyclePart05(AstrBotLifecycleTests):
    def test_low_signal_light_assessment_skips_provider_lookup(self):
        from emotion_engine import EmotionState

        plugin = new_plugin({"enable_low_signal_light_assessment": True})

        async def fail_provider(self, event):
            raise AssertionError("low-signal text must not call provider lookup")

        bind_async(plugin, "_provider_id", fail_provider)

        observation = asyncio.run(
            plugin._assess_emotion(
                event=FakeEvent("s-low", message="嗯嗯"),
                phase="pre_response",
                previous_state=EmotionState.initial(),
                persona_profile=None,
                context_text="",
                current_text="嗯嗯",
            ),
        )

        self.assertEqual(observation.source, "low_signal")
        self.assertTrue(observation.appraisal["low_signal"])
        self.assertEqual(observation.appraisal["signal_kind"], "short_ack")
        self.assertLessEqual(observation.confidence, 0.28)


    def test_group_agent_tracks_conversation_and_speakers_separately(self):
        plugin = new_plugin({"assessment_timing": "pre", "inject_state": False})
        saves = []
        assessment_calls = []
        states = {}

        async def fake_persona(self, event, request):
            return None

        async def fake_load_state(self, session_key, persona_profile=None, **kwargs):
            from emotion_engine import EmotionState

            states.setdefault(session_key, EmotionState.initial())
            return states[session_key]

        async def fake_save_state(self, session_key, state):
            states[session_key] = state
            saves.append((session_key, state))

        async def fake_assess_emotion(self, **kwargs):
            assessment_calls.append(kwargs)
            return fake_observation(kwargs["event"].get_sender_id())

        bind_async(plugin, "_persona_profile", fake_persona)
        bind_async(plugin, "_load_state", fake_load_state)
        bind_async(plugin, "_save_state", fake_save_state)
        bind_async(plugin, "_assess_emotion", fake_assess_emotion)

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("group-1", message="from A", sender_id="user-a"),
                fake_request(session_id="group-1", prompt="from A"),
            ),
        )
        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("group-1", message="from B", sender_id="user-b"),
                fake_request(session_id="group-1", prompt="from B"),
            ),
        )

        saved_keys = [key for key, _ in saves]
        self.assertEqual(
            saved_keys,
            [
                "group-1",
                "group-1::speaker:user-a",
                "group-1",
                "group-1::speaker:user-b",
            ],
        )
        self.assertIn("[speaker:user-a]\nfrom A", assessment_calls[0]["current_text"])
        self.assertIn("[speaker:user-b]\nfrom B", assessment_calls[1]["current_text"])
        self.assertEqual(states["group-1"].turns, 2)
        self.assertEqual(states["group-1::speaker:user-a"].turns, 1)
        self.assertEqual(states["group-1::speaker:user-b"].turns, 1)


    def test_group_agent_injects_current_speaker_track(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": True,
                "agent_speaker_relationship_tracking": True,
            },
        )

        async def fake_persona(self, event, request):
            return None

        bind_async(plugin, "_persona_profile", fake_persona)
        request = fake_request(session_id="group-2", prompt="hello")

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "group-2",
                    message="hello",
                    sender_id="user-a",
                    sender_name="Alice",
                ),
                request,
            ),
        )

        injected_texts = [
            getattr(part, "text", "")
            for part in request.extra_user_content_parts
        ]
        self.assertTrue(
            any("<bot_emotion_speaker_track" in text for text in injected_texts),
        )
        self.assertTrue(
            any("Alice(user-a)" in text for text in injected_texts),
        )


    def test_group_atmosphere_updates_and_injects_compact_state_for_group_turn(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": True,
            },
        )
        group_saves = []

        async def fake_persona(self, event, request):
            return None

        async def fake_save_group(self, session_key, state):
            group_saves.append((session_key, state))
            self._group_atmosphere_memory_cache[session_key] = state

        bind_async(plugin, "_persona_profile", fake_persona)
        bind_async(plugin, "_save_group_atmosphere_state", fake_save_group)
        request = fake_request(session_id="group-room", prompt="@bot 哈哈 来看看")

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "group-room",
                    message="@bot 哈哈 来看看",
                    sender_id="user-a",
                    sender_name="Alice",
                ),
                request,
            ),
        )

        texts = [getattr(part, "text", "") for part in request.extra_user_content_parts]
        self.assertEqual(len(group_saves), 1)
        self.assertEqual(group_saves[0][0], "group-room")
        self.assertIn("group-room", plugin._agent_identity_profile_cache)
        self.assertIn("group-room::speaker:user-a", plugin._agent_identity_profile_cache)
        self.assertTrue(any('name="group_atmosphere"' in text for text in texts))
        joined = "\n".join(texts)
        self.assertNotIn("query_agent_state(", joined)
        self.assertNotIn("get_bot_group_atmosphere_state", joined)
        self.assertGreaterEqual(
            group_saves[0][1].values["bot_attention"],
            0.29,
        )


    def test_group_atmosphere_join_cooldown_persists_even_in_pre_timing(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
            },
        )
        saved = []

        async def fake_put_kv(self, key, value):
            saved.append((key, value))

        bind_async(plugin, "put_kv_data", fake_put_kv)

        asyncio.run(
            plugin.on_llm_response(
                FakeEvent("group-cooldown", sender_id="user-a", sender_name="Alice"),
                SimpleNamespace(completion_text="assistant joined"),
            ),
        )

        self.assertEqual(len(saved), 1)
        key, payload = saved[0]
        self.assertEqual(key, plugin._group_atmosphere_kv_key("group-cooldown"))
        self.assertEqual(payload["last_bot_join_turn"], 0)
        self.assertIsNotNone(payload["last_bot_join_at"])
        self.assertFalse(payload["cooldown"]["cooldown_active"])
        self.assertIn("join_cooldown_turns", payload["dynamics"])
        self.assertEqual(
            payload["cooldown"]["cooldown_remaining_turns"],
            int(round(payload["dynamics"]["join_cooldown_turns"])),
        )


    def test_group_atmosphere_diff_injection_sends_small_no_change_fragment(self):
        from group_atmosphere_engine import GroupAtmosphereState

        plugin = new_plugin(
            {
                "runtime_parameter_debug_override_enabled": True,
                "state_injection_compact_mode": "diff",
                "group_atmosphere_injection_diff_threshold": 0.08,
            },
        )
        state = GroupAtmosphereState.initial()

        first = plugin._build_group_atmosphere_injection_for_session(
            "group-diff",
            state,
        )
        second = plugin._build_group_atmosphere_injection_for_session(
            "group-diff",
            state,
        )

        self.assertIn("bot_group_atmosphere", first)
        self.assertIn('detail="diff"', second)
        self.assertIn("No material room-mood change", second)
        self.assertLess(len(second), len(first))


    def test_agent_identity_alias_drift_keeps_speaker_track_stable(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
            },
        )

        async def fake_persona(self, event, request):
            return None

        bind_async(plugin, "_persona_profile", fake_persona)

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "group-alias",
                    message="first name",
                    sender_id="user-a",
                    sender_name="Alice",
                ),
                fake_request(session_id="group-alias", prompt="first name"),
            ),
        )
        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "group-alias",
                    message="new name",
                    sender_id="user-a",
                    sender_name="Alicia",
                ),
                fake_request(session_id="group-alias", prompt="new name"),
            ),
        )

        profile = asyncio.run(
            plugin.get_agent_identity_profile(
                FakeEvent("group-alias", sender_id="user-a", sender_name="Alicia"),
            ),
        )
        self.assertEqual(profile["speaker_track_id"], "group-alias::speaker:user-a")
        self.assertEqual(profile["current_display_name"], "Alicia")
        self.assertEqual(
            [alias["name"] for alias in profile["aliases"]],
            ["Alice", "Alicia"],
        )


    def test_agent_identity_profile_prunes_stale_silent_speakers(self):
        plugin = new_plugin(
            {
                "agent_identity_profile_limit": 3,
                "agent_identity_ttl_seconds": 10.0,
            },
        )
        now = plugin._observed_now()
        plugin._agent_identity_profile_cache = {
            "group-prune": {
                "schema_version": "astrbot.agent_identity.v1",
                "conversation_id": "group-prune",
                "updated_at": now,
            },
            "group-prune::speaker:old": {
                "schema_version": "astrbot.agent_identity.v1",
                "conversation_id": "group-prune",
                "speaker_track_id": "group-prune::speaker:old",
                "updated_at": now - 99.0,
            },
            "group-prune::speaker:recent": {
                "schema_version": "astrbot.agent_identity.v1",
                "conversation_id": "group-prune",
                "speaker_track_id": "group-prune::speaker:recent",
                "updated_at": now - 1.0,
            },
        }

        profile = asyncio.run(
            plugin.get_agent_identity_profile(
                FakeEvent("group-prune", sender_id="new", sender_name="New"),
            ),
        )

        self.assertEqual(profile["speaker_track_id"], "group-prune::speaker:new")
        self.assertIn("group-prune", plugin._agent_identity_profile_cache)
        self.assertIn(
            "group-prune::speaker:new",
            plugin._agent_identity_profile_cache,
        )
        self.assertIn(
            "group-prune::speaker:recent",
            plugin._agent_identity_profile_cache,
        )
        self.assertNotIn(
            "group-prune::speaker:old",
            plugin._agent_identity_profile_cache,
        )


    def test_agent_causal_trail_records_sanitized_refs_not_raw_prompt(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
            },
        )
        self._bind_common_state_hooks(plugin)
        request = fake_request(
            session_id="group-trail",
            prompt="secret phrase should be excerpted only",
        )

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "group-trail",
                    message="secret phrase should be excerpted only",
                    sender_id="user-a",
                    sender_name="Alice",
                ),
                request,
            ),
        )

        trail = asyncio.run(
            plugin.get_agent_trail(
                FakeEvent("group-trail", sender_id="user-a", sender_name="Alice"),
                limit=10,
            ),
        )
        modules = [item["module"] for item in trail["items"]]
        self.assertIn("emotion", modules)
        self.assertIn("group_atmosphere", modules)
        for item in trail["items"]:
            self.assertIn("text_hash", item["input_ref"])
            self.assertIn("char_count", item["input_ref"])
            self.assertNotIn("input_text", item)


    def test_invalid_assessment_timing_falls_back_to_post(self):
        plugin = new_plugin({"assessment_timing": "bad-value"})
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        request = fake_request(session_id="s-bad", prompt="request text")
        response = SimpleNamespace(completion_text="assistant text")

        asyncio.run(plugin.on_llm_request(FakeEvent("s-bad"), request))

        async def run_response_and_drain():
            await plugin.on_llm_response(FakeEvent("s-bad"), response)
            await self._await_background_tasks(plugin)

        asyncio.run(run_response_and_drain())

        self.assertEqual(plugin._assessment_timing(), "post")
        self.assertEqual(len(saves), 1)
        self.assertEqual(
            [call["phase"] for call in assessment_calls],
            ["post_response"],
        )


    def test_on_llm_response_ignores_blank_completion(self):
        plugin = new_plugin({"assessment_timing": "both"})
        self._bind_common_state_hooks(plugin)

        async def fail_if_persona_loaded(self, *args, **kwargs):
            raise AssertionError("blank completion must not load persona state")

        async def fail_if_loaded(self, *args, **kwargs):
            raise AssertionError("blank completion must not load emotion state")

        async def fail_if_assessed(self, **kwargs):
            raise AssertionError("blank completion must not be assessed")

        async def fail_if_saved(self, session_key, state):
            raise AssertionError("blank completion must not be saved")

        bind_async(plugin, "_persona_profile", fail_if_persona_loaded)
        bind_async(plugin, "_load_state", fail_if_loaded)
        bind_async(plugin, "_assess_emotion", fail_if_assessed)
        bind_async(plugin, "_save_state", fail_if_saved)

        asyncio.run(
            plugin.on_llm_response(
                FakeEvent("s-blank"),
                SimpleNamespace(completion_text="   "),
            ),
        )


    def test_humanlike_enabled_with_zero_strength_updates_without_injection(self):
        from humanlike_engine import HumanlikeState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_humanlike_state": True,
                "humanlike_injection_strength": 0.0,
            },
        )
        self._bind_common_state_hooks(plugin)
        humanlike_saves = []

        async def fake_load_humanlike_state(self, session_key, **kwargs):
            return HumanlikeState.initial()

        async def fake_save_humanlike_state(self, session_key, state):
            humanlike_saves.append((session_key, state))

        bind_async(plugin, "_load_humanlike_state", fake_load_humanlike_state)
        bind_async(plugin, "_save_humanlike_state", fake_save_humanlike_state)
        request = fake_request(session_id="s-humanlike", prompt="only you forever")

        asyncio.run(plugin.on_llm_request(FakeEvent("s-humanlike"), request))

        self.assertEqual(len(humanlike_saves), 1)
        self.assertEqual(humanlike_saves[0][0], "s-humanlike")
        self._find_text_part(request, "bot_emotion_state")
        self._assert_no_text_part_contains(request, "simulated humanlike-state")


    def test_lifelike_learning_enabled_with_zero_strength_updates_without_injection(self):
        from lifelike_learning_engine import LifelikeLearningState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_lifelike_learning": True,
                "lifelike_learning_injection_strength": 0.0,
            },
        )
        self._bind_common_state_hooks(plugin)
        lifelike_saves = []

        async def fake_load_lifelike_state(self, session_key, **kwargs):
            return LifelikeLearningState.initial()

        async def fake_save_lifelike_state(self, session_key, state):
            lifelike_saves.append((session_key, state))

        bind_async(plugin, "_load_lifelike_learning_state", fake_load_lifelike_state)
        bind_async(plugin, "_save_lifelike_learning_state", fake_save_lifelike_state)
        request = fake_request(
            session_id="s-life",
            prompt="『桥隧猫』就是会熬夜改桥梁模型的人。",
        )

        asyncio.run(plugin.on_llm_request(FakeEvent("s-life"), request))

        self.assertEqual(len(lifelike_saves), 1)
        self.assertEqual(lifelike_saves[0][0], "s-life")
        self.assertIn("桥隧猫", lifelike_saves[0][1].lexicon)
        self._find_text_part(request, "bot_emotion_state")
        self._assert_no_text_part_contains(request, "lifelike common-ground")


    def test_lifelike_learning_injects_when_enabled_and_strength_positive(self):
        from lifelike_learning_engine import LifelikeLearningState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_lifelike_learning": True,
                "lifelike_learning_injection_strength": 0.3,
            },
        )
        self._bind_common_state_hooks(plugin)

        async def fake_load_lifelike_state(self, session_key, **kwargs):
            return LifelikeLearningState.initial()

        async def fake_save_lifelike_state(self, session_key, state):
            pass

        bind_async(plugin, "_load_lifelike_learning_state", fake_load_lifelike_state)
        bind_async(plugin, "_save_lifelike_learning_state", fake_save_lifelike_state)
        request = fake_request(
            session_id="s-life-inject",
            prompt="我喜欢自然闲聊，桥隧猫就是会熬夜改模型的人。",
        )

        asyncio.run(plugin.on_llm_request(FakeEvent("s-life-inject"), request))

        self._find_text_part(request, "bot_emotion_state")
        auxiliary_text = self._find_text_part(
            request,
            'name="lifelike_learning"',
        )
        self.assertIn("bot_auxiliary_state", auxiliary_text)
        self.assertNotIn("query_agent_state(", auxiliary_text)


    def test_fallibility_enabled_with_zero_strength_updates_without_injection(self):
        from fallibility_engine import FallibilityState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_fallibility_state": True,
                "fallibility_injection_strength": 0.0,
            },
        )
        self._bind_common_state_hooks(plugin)
        fallibility_saves = []

        async def fake_load_fallibility_state(self, session_key, **kwargs):
            return FallibilityState.initial()

        async def fake_save_fallibility_state(self, session_key, state):
            fallibility_saves.append((session_key, state))

        bind_async(plugin, "_load_fallibility_state", fake_load_fallibility_state)
        bind_async(plugin, "_save_fallibility_state", fake_save_fallibility_state)
        request = fake_request(
            session_id="s-fallibility",
            prompt="I may have misread that, sorry, I should correct it.",
        )

        asyncio.run(plugin.on_llm_request(FakeEvent("s-fallibility"), request))

        self.assertEqual(len(fallibility_saves), 1)
        self.assertEqual(fallibility_saves[0][0], "s-fallibility")
        self.assertIn("possible_mistake_cue", fallibility_saves[0][1].flags)
        self._find_text_part(request, "bot_emotion_state")
        self._assert_no_text_part_contains(request, "fallibility-state modulation")


    def test_fallibility_injects_when_enabled_and_strength_positive(self):
        from fallibility_engine import FallibilityState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_fallibility_state": True,
                "fallibility_injection_strength": 0.3,
            },
        )
        self._bind_common_state_hooks(plugin)

        async def fake_load_fallibility_state(self, session_key, **kwargs):
            return FallibilityState.initial()

        async def fake_save_fallibility_state(self, session_key, state):
            pass

        bind_async(plugin, "_load_fallibility_state", fake_load_fallibility_state)
        bind_async(plugin, "_save_fallibility_state", fake_save_fallibility_state)
        request = fake_request(
            session_id="s-fallibility-inject",
            prompt="I may have misread that.",
        )

        asyncio.run(plugin.on_llm_request(FakeEvent("s-fallibility-inject"), request))

        self._find_text_part(request, "bot_emotion_state")
        auxiliary_text = self._find_text_part(
            request,
            'name="fallibility"',
        )
        self.assertIn("bot_auxiliary_state", auxiliary_text)
        self.assertNotIn("query_agent_state(", auxiliary_text)

    def test_fallibility_injection_goes_through_kernel_host_boundary(self):
        from fallibility_engine import FallibilityState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_fallibility_state": True,
                "fallibility_injection_strength": 0.3,
            },
        )
        self._bind_common_state_hooks(plugin)
        calls = []

        async def fake_load_fallibility_state(self, session_key, **kwargs):
            return FallibilityState.initial()

        async def fake_save_fallibility_state(self, session_key, state):
            pass

        def fake_append_fallibility_auxiliary_state(
            self,
            request,
            fallibility_state,
            *,
            safety_boundary,
            action_blocking,
            injection_decision,
            injection_budget,
        ):
            calls.append(
                {
                    "state": fallibility_state,
                    "safety_boundary": safety_boundary,
                    "action_blocking": action_blocking,
                    "decision": injection_decision,
                    "budget": injection_budget,
                },
            )
            return self._append_temp_text_part(
                request,
                '<bot_auxiliary_state private="true" name="fallibility" detail="host-boundary">hosted</bot_auxiliary_state>',
                source="fallibility",
                budget=injection_budget,
            )

        bind_async(plugin, "_load_fallibility_state", fake_load_fallibility_state)
        bind_async(plugin, "_save_fallibility_state", fake_save_fallibility_state)
        plugin._append_fallibility_auxiliary_state = fake_append_fallibility_auxiliary_state.__get__(plugin)
        request = fake_request(
            session_id="s-fallibility-host-boundary",
            prompt="I may have misread that.",
        )

        asyncio.run(plugin.on_llm_request(FakeEvent("s-fallibility-host-boundary"), request))

        self.assertEqual(1, len(calls))
        self._find_text_part(request, 'name="fallibility" detail="host-boundary"')

    def test_auxiliary_state_injection_full_mode_keeps_legacy_fragments(self):
        from lifelike_learning_engine import LifelikeLearningState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "runtime_parameter_debug_override_enabled": True,
                "enable_lifelike_learning": True,
                "lifelike_learning_injection_strength": 0.3,
                "auxiliary_state_injection_detail": "full",
            },
        )
        self._bind_common_state_hooks(plugin)

        async def fake_load_lifelike_state(self, session_key, **kwargs):
            return LifelikeLearningState.initial()

        async def fake_save_lifelike_state(self, session_key, state):
            pass

        bind_async(plugin, "_load_lifelike_learning_state", fake_load_lifelike_state)
        bind_async(plugin, "_save_lifelike_learning_state", fake_save_lifelike_state)
        request = fake_request(session_id="s-life-full", prompt="hello")

        asyncio.run(plugin.on_llm_request(FakeEvent("s-life-full"), request))

        text = self._find_text_part(request, "lifelike common-ground")
        self.assertNotIn("bot_auxiliary_state", text)
