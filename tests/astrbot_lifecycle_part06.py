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


class AstrBotLifecyclePart06(AstrBotLifecycleTests):
    def test_auxiliary_state_injection_off_skips_auxiliary_fragments(self):
        from lifelike_learning_engine import LifelikeLearningState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "runtime_parameter_debug_override_enabled": True,
                "enable_lifelike_learning": True,
                "lifelike_learning_injection_strength": 0.3,
                "auxiliary_state_injection_detail": "off",
            },
        )
        self._bind_common_state_hooks(plugin)

        async def fake_load_lifelike_state(self, session_key, **kwargs):
            return LifelikeLearningState.initial()

        async def fake_save_lifelike_state(self, session_key, state):
            pass

        bind_async(plugin, "_load_lifelike_learning_state", fake_load_lifelike_state)
        bind_async(plugin, "_save_lifelike_learning_state", fake_save_lifelike_state)
        request = fake_request(session_id="s-life-off", prompt="hello")

        asyncio.run(plugin.on_llm_request(FakeEvent("s-life-off"), request))

        texts = self._request_text_parts(request)
        state_texts = [
            text
            for text in texts
            if text.startswith("<bot_") or "bot_auxiliary_state" in text
        ]
        self.assertEqual(len(state_texts), 1)
        self.assertIn("bot_emotion_state", state_texts[0])


    def test_on_llm_request_overlaps_auxiliary_state_loads(self):
        from humanlike_engine import HumanlikeState
        from lifelike_learning_engine import LifelikeLearningState
        from moral_repair_engine import MoralRepairState
        from fallibility_engine import FallibilityState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_humanlike_state": True,
                "enable_lifelike_learning": True,
                "enable_moral_repair_state": True,
                "enable_fallibility_state": True,
                "humanlike_injection_strength": 0.0,
                "lifelike_learning_injection_strength": 0.0,
                "moral_repair_injection_strength": 0.0,
                "fallibility_injection_strength": 0.0,
            },
        )
        self._bind_common_state_hooks(plugin)
        saves = []

        async def slow_humanlike(self, session_key, **kwargs):
            await asyncio.sleep(0.05)
            return HumanlikeState.initial()

        async def slow_lifelike(self, session_key, **kwargs):
            await asyncio.sleep(0.05)
            return LifelikeLearningState.initial()

        async def slow_moral(self, session_key, **kwargs):
            await asyncio.sleep(0.05)
            return MoralRepairState.initial()

        async def slow_fallibility(self, session_key, **kwargs):
            await asyncio.sleep(0.05)
            return FallibilityState.initial()

        async def save_aux(self, session_key, state):
            saves.append((session_key, type(state).__name__))

        bind_async(plugin, "_load_humanlike_state", slow_humanlike)
        bind_async(plugin, "_load_lifelike_learning_state", slow_lifelike)
        bind_async(plugin, "_load_moral_repair_state", slow_moral)
        bind_async(plugin, "_load_fallibility_state", slow_fallibility)
        bind_async(plugin, "_save_humanlike_state", save_aux)
        bind_async(plugin, "_save_lifelike_learning_state", save_aux)
        bind_async(plugin, "_save_moral_repair_state", save_aux)
        bind_async(plugin, "_save_fallibility_state", save_aux)

        started = time.perf_counter()
        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("s-aux-overlap"),
                fake_request(session_id="s-aux-overlap", prompt="sorry, 桥隧猫 means bridge tunnel friend"),
            ),
        )
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 0.16)
        self.assertEqual(
            [state_name for _, state_name in saves],
            [
                "HumanlikeState",
                "LifelikeLearningState",
                "MoralRepairState",
                "FallibilityState",
            ],
        )


    def test_personality_drift_enabled_uses_real_time_state_without_forcing_prompt(self):
        from personality_drift_engine import (
            PersonalityDriftEngine,
            PersonalityDriftParameters,
            PersonalityDriftState,
        )

        plugin = new_plugin(
            {
                "assessment_timing": "post",
            },
        )
        plugin.personality_drift_engine = PersonalityDriftEngine(
            PersonalityDriftParameters(event_threshold=0.01),
        )
        self._bind_common_state_hooks(plugin)
        drift_saves = []

        async def fake_load_personality_drift_state(
            self,
            session_key,
            profile=None,
            **kwargs,
        ):
            return PersonalityDriftState.initial(
                persona_fingerprint=profile.fingerprint if profile else "default",
                now=0.0,
            )

        async def fake_save_personality_drift_state(self, session_key, state):
            drift_saves.append((session_key, state))

        bind_async(plugin, "_load_personality_drift_state", fake_load_personality_drift_state)
        bind_async(plugin, "_save_personality_drift_state", fake_save_personality_drift_state)
        event_text = "thank you, I trust you, and I want us to keep learning together"
        request = fake_request(session_id="s-drift", prompt=event_text)

        asyncio.run(plugin.on_llm_request(FakeEvent("s-drift", message=event_text), request))

        self.assertGreaterEqual(len(drift_saves), 1)
        self.assertEqual(drift_saves[-1][0], "s-drift")
        self.assertGreaterEqual(drift_saves[-1][1].evidence_count, 1)
        self._find_text_part(request, "bot_emotion_state")
        self._assert_no_text_part_contains(request, "personality drift modulation")


    def test_personality_drift_ignores_replayed_request_context_as_new_event(self):
        from personality_drift_engine import PersonalityDriftState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_personality_drift": True,
                "personality_drift_injection_strength": 0.0,
            },
        )
        self._bind_common_state_hooks(plugin)
        drift_saves = []

        async def fake_load_personality_drift_state(
            self,
            session_key,
            profile=None,
            **kwargs,
        ):
            return PersonalityDriftState.initial(
                persona_fingerprint=profile.fingerprint if profile else "default",
                now=0.0,
            )

        async def fake_save_personality_drift_state(self, session_key, state):
            drift_saves.append((session_key, state))

        bind_async(plugin, "_load_personality_drift_state", fake_load_personality_drift_state)
        bind_async(plugin, "_save_personality_drift_state", fake_save_personality_drift_state)
        request = fake_request(session_id="s-drift-context", prompt="普通新消息")
        request.contexts = [
            {
                "role": "user",
                "content": "谢谢你一直陪伴我，我信任你，也想一起继续学习。",
            },
        ]

        asyncio.run(plugin.on_llm_request(FakeEvent("s-drift-context"), request))

        self.assertEqual(drift_saves, [])


    def test_personality_drift_injects_when_enabled_and_strength_positive(self):
        from personality_drift_engine import PersonalityDriftState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_personality_drift": True,
                "personality_drift_injection_strength": 0.22,
            },
        )
        self._bind_common_state_hooks(plugin)

        async def fake_load_personality_drift_state(
            self,
            session_key,
            profile=None,
            **kwargs,
        ):
            state = PersonalityDriftState.initial(
                persona_fingerprint=profile.fingerprint if profile else "default",
                now=0.0,
            )
            state.trait_offsets["interpersonal_warmth"] = 0.06
            state.values["drift_intensity"] = 0.2
            return state

        async def fake_save_personality_drift_state(self, session_key, state):
            pass

        bind_async(plugin, "_load_personality_drift_state", fake_load_personality_drift_state)
        bind_async(plugin, "_save_personality_drift_state", fake_save_personality_drift_state)
        request = fake_request(session_id="s-drift-inject", prompt="谢谢你，继续一起研究。")

        asyncio.run(plugin.on_llm_request(FakeEvent("s-drift-inject"), request))

        self._find_text_part(request, "bot_emotion_state")
        auxiliary_text = self._find_text_part(
            request,
            'name="personality_drift"',
        )
        self.assertIn("bot_auxiliary_state", auxiliary_text)
        self.assertNotIn("query_agent_state(", auxiliary_text)
        self._assert_no_text_part_contains(request, "personality drift modulation")


    def test_personality_drift_request_reuses_loaded_state_for_runtime_update_and_injection(self):
        from personality_drift_engine import PersonalityDriftState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_personality_drift": True,
                "personality_drift_injection_strength": 0.22,
            },
        )
        self._bind_common_state_hooks(plugin)
        loads = []

        async def fake_load_personality_drift_state(
            self,
            session_key,
            profile=None,
            **kwargs,
        ):
            loads.append(session_key)
            state = PersonalityDriftState.initial(
                persona_fingerprint=profile.fingerprint if profile else "default",
                now=0.0,
            )
            state.trait_offsets["interpersonal_warmth"] = 0.04
            state.values["drift_intensity"] = 0.2
            return state

        async def fake_save_personality_drift_state(self, session_key, state):
            pass

        bind_async(plugin, "_load_personality_drift_state", fake_load_personality_drift_state)
        bind_async(plugin, "_save_personality_drift_state", fake_save_personality_drift_state)
        request = fake_request(session_id="s-drift-reuse", prompt="thank you")

        asyncio.run(plugin.on_llm_request(FakeEvent("s-drift-reuse"), request))

        self.assertEqual(loads, ["s-drift-reuse"])

    def test_personality_drift_injection_goes_through_kernel_host_boundary(self):
        from personality_drift_engine import PersonalityDriftState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_personality_drift": True,
                "personality_drift_injection_strength": 0.22,
            },
        )
        self._bind_common_state_hooks(plugin)
        calls = []

        async def fake_load_personality_drift_state(
            self,
            session_key,
            profile=None,
            **kwargs,
        ):
            return PersonalityDriftState.initial(
                persona_fingerprint=profile.fingerprint if profile else "default",
                now=0.0,
            )

        async def fake_save_personality_drift_state(self, session_key, state):
            pass

        def fake_append_personality_drift_auxiliary_state(
            self,
            request,
            personality_drift_state,
            *,
            injection_decision,
            injection_budget,
        ):
            calls.append(
                {
                    "state": personality_drift_state,
                    "decision": injection_decision,
                    "budget": injection_budget,
                },
            )
            return self._append_temp_text_part(
                request,
                '<bot_auxiliary_state private="true" name="personality_drift" detail="host-boundary">hosted</bot_auxiliary_state>',
                source="personality_drift",
                budget=injection_budget,
            )

        bind_async(plugin, "_load_personality_drift_state", fake_load_personality_drift_state)
        bind_async(plugin, "_save_personality_drift_state", fake_save_personality_drift_state)
        plugin._append_personality_drift_auxiliary_state = fake_append_personality_drift_auxiliary_state.__get__(plugin)
        request = fake_request(session_id="s-drift-host-boundary", prompt="thank you")

        asyncio.run(plugin.on_llm_request(FakeEvent("s-drift-host-boundary"), request))

        self.assertEqual(1, len(calls))
        self._find_text_part(request, 'name="personality_drift" detail="host-boundary"')


    def test_realtime_chat_plan_splits_reply_and_bounds_delay(self):
        plugin = new_plugin(
            {
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_max_parts": 4,
                "realtime_chat_max_part_chars": 18,
                "realtime_chat_min_delay_seconds": 0.1,
                "realtime_chat_max_delay_seconds": 1.0,
                "enable_sticker_reaction": False,
            },
        )

        plan = asyncio.run(
            plugin.get_realtime_chat_plan(
                "s-realtime-plan",
                "那、那个……我先确认一下。这个地方可以拆开说！然后再慢慢收束。",
            ),
        )

        self.assertEqual(plan["kind"], "realtime_chat_plan")
        self.assertGreaterEqual(plan["message_count"], 2)
        runtime_limit = plan["settings"]["max_part_chars"]
        for part in plan["message_parts"]:
            self.assertLessEqual(len(part["text"]), runtime_limit)
            self.assertLessEqual(part["delay_before_seconds"], 1.0)
            self.assertGreaterEqual(part["delay_before_seconds"], 0.0)


    def test_realtime_chat_plan_keeps_long_tail_without_ellipsis(self):
        plugin = new_plugin(
            {
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_max_parts": 3,
                "realtime_chat_max_part_chars": 8,
                "enable_sticker_reaction": False,
            },
        )

        plan = asyncio.run(
            plugin.get_realtime_chat_plan(
                "s-realtime-tail",
                "第一句短。第二句短。第三句短。第四句短。第五句短。第六句短。第七句短。第八句短。第九句短。第十句短。",
            ),
        )

        self.assertEqual(plan["kind"], "realtime_chat_plan")
        self.assertGreater(plan["message_count"], 3)
        runtime_limit = plan["settings"]["max_part_chars"]
        for part in plan["message_parts"]:
            self.assertLessEqual(len(part["text"]), runtime_limit)
        self.assertNotIn("...", plan["message_parts"][-1]["text"])


    def test_realtime_chat_plan_keeps_explicit_line_break_fragments(self):
        plugin = new_plugin(
            {
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_max_parts": 8,
                "realtime_chat_max_part_chars": 80,
                "enable_sticker_reaction": False,
            },
        )

        plan = asyncio.run(
            plugin.get_realtime_chat_plan(
                "s-realtime-line-fragments",
                "第一段先说。\n第二段单独发。\n第三段也拆开。\n第四段继续拆。"
                "\n第五段保持碎片。"
            ),
        )

        parts = [part["text"] for part in plan["message_parts"]]
        self.assertGreaterEqual(plan["message_count"], 5)
        self.assertIn("第一段先说。", parts[0])
        self.assertIn("第二段单独发。", parts[1])
        self.assertIn("第三段也拆开。", parts[2])
        self.assertTrue(all("\n" not in part for part in parts))


    def test_realtime_dispatch_force_splits_oversized_parts_before_send(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin({"enable_sticker_reaction": False})
        plugin.context = FakeContext()
        long_text = (
            "one very long realtime message without any helpful newline or markdown "
            "that must be split by the plugin before it reaches the chat platform"
        )
        plan = {
            "session_key": "s-force-split",
            "settings": {"max_part_chars": 24, "min_part_chars": 3},
            "message_parts": [
                {"index": 0, "text": long_text, "delay_before_seconds": 0.0},
            ],
        }

        asyncio.run(
            plugin._send_realtime_chat_plan(
                FakeEvent("s-force-split"),
                plan,
                source="unit_test",
            ),
        )

        self.assertGreater(len(sent), 1)
        self.assertTrue(
            all(len(message.replace("message:", "")) <= 24 for _, message in sent),
        )


    def test_realtime_chat_runtime_settings_are_personality_adaptive(self):
        plugin = new_plugin(
            {
                "enable_sticker_reaction": False,
                "realtime_chat_max_parts": 1,
                "realtime_chat_max_part_chars": 999,
                "realtime_chat_chars_per_second": 1.0,
                "realtime_chat_min_delay_seconds": 9.0,
                "realtime_chat_max_delay_seconds": 9.0,
            },
        )

        async def fake_runtime_profile(self, *args, **kwargs):
            return SimpleNamespace(
                personality_model={
                    "derived_factors": {
                        "expressiveness": 0.92,
                        "social_distance": 0.08,
                        "boundary_sensitivity": 0.18,
                        "instability": 0.22,
                    },
                    "trait_scores": {
                        "interpersonal_warmth": 0.82,
                        "agreeableness": 0.74,
                    },
                },
            )

        bind_async(plugin, "_public_runtime_persona_profile", fake_runtime_profile)

        plan = asyncio.run(
            plugin.get_realtime_chat_plan(
                FakeEvent("s-adaptive-chat"),
                "第一句。第二句！第三句也想分开说。第四句慢慢收束。",
            ),
        )

        adaptive = plan["adaptive"]["realtime_chat"]
        self.assertFalse(adaptive["debug_override_used"])
        self.assertEqual(adaptive["source"], "personality_emotion_atmosphere")
        self.assertGreater(plan["message_count"], 1)
        self.assertNotEqual(plan["typing"]["chars_per_second"], 1.0)
        self.assertLess(plan["settings"]["max_part_chars"], 999)
        self.assertLess(plan["typing"]["min_delay_seconds"], 9.0)


    def test_lifelike_learning_records_user_speaking_style(self):
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
            lifelike_saves.append(state)

        bind_async(plugin, "_load_lifelike_learning_state", fake_load_lifelike_state)
        bind_async(plugin, "_save_lifelike_learning_state", fake_save_lifelike_state)

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("s-speaking-style"),
                fake_request(
                    session_id="s-speaking-style",
                    prompt="嗯嗯。\n这个要拆开说！\n别写成长篇 markdown，短一点自然一点。",
                ),
            ),
        )

        style = lifelike_saves[-1].user_profile.speaking_style
        self.assertGreater(style["confidence"], 0.0)
        self.assertGreater(style["fragment_bias"], 0.3)
        self.assertGreater(style["short_turn_bias"], 0.1)


    def test_realtime_chat_adapts_split_strategy_to_user_speaking_style(self):
        from lifelike_learning_engine import LifelikeLearningState

        text = "第一句先说明问题。第二句补一点上下文。第三句再说处理方式。第四句慢慢收束。第五句留个余地。"

        async def fake_profile(self, *args, **kwargs):
            return None

        async def fake_emotion(self, *args, **kwargs):
            return {}

        async def fake_group(self, *args, **kwargs):
            return {}

        async def short_style_state(self, session_key, **kwargs):
            state = LifelikeLearningState.initial()
            state.user_profile.style_preferences = [
                "natural_conversational_style",
                "avoid_long_markdown_lists",
            ]
            state.user_profile.speaking_style = {
                "fragment_bias": 0.92,
                "short_turn_bias": 0.86,
                "formal_block_bias": 0.08,
                "typing_speed_bias": 0.48,
                "confidence": 0.95,
            }
            return state

        async def long_style_state(self, session_key, **kwargs):
            state = LifelikeLearningState.initial()
            state.user_profile.style_preferences = [
                "rigorous_engineering_detail_when_requested",
            ]
            state.user_profile.speaking_style = {
                "fragment_bias": 0.08,
                "short_turn_bias": 0.04,
                "formal_block_bias": 0.92,
                "typing_speed_bias": 0.68,
                "confidence": 0.95,
            }
            return state

        short_plugin = new_plugin({"enable_sticker_reaction": False})
        long_plugin = new_plugin({"enable_sticker_reaction": False})
        for plugin in (short_plugin, long_plugin):
            bind_async(plugin, "_public_runtime_persona_profile", fake_profile)
            bind_async(plugin, "get_emotion_values", fake_emotion)
            bind_async(plugin, "get_group_atmosphere_values", fake_group)
        bind_async(short_plugin, "_load_lifelike_learning_state", short_style_state)
        bind_async(long_plugin, "_load_lifelike_learning_state", long_style_state)

        short_plan = asyncio.run(short_plugin.get_realtime_chat_plan("s-short-style", text))
        long_plan = asyncio.run(long_plugin.get_realtime_chat_plan("s-long-style", text))

        short_adaptive = short_plan["adaptive"]["realtime_chat"]
        self.assertTrue(short_adaptive["user_style_adaptation"]["enabled"])
        self.assertLess(
            short_plan["settings"]["max_part_chars"],
            long_plan["settings"]["max_part_chars"],
        )
        self.assertGreaterEqual(
            short_plan["message_count"],
            long_plan["message_count"],
        )
        serialized = str(short_adaptive)
        self.assertNotIn("style_preferences", serialized)
        self.assertNotIn("speaking_style", serialized)


    def test_proactive_dispatch_policy_is_adaptive_not_fixed_config(self):
        plugin = new_plugin(
            {
                "proactive_speech_max_chars": 1,
                "proactive_speech_dispatch_ttl_seconds": 1,
                "proactive_speech_dispatch_cooldown_seconds": 1.0,
            },
        )
        decision = {
            "should_speak": True,
            "action": "speak_now",
            "score": 0.78,
            "signals": {
                "boundary": 0.18,
                "overload": 0.12,
                "repair_need": 0.08,
                "companionship_need": 0.66,
                "user_need_to_be_met": 0.52,
                "bot_need_to_express": 0.48,
            },
            "topic_judgement": {
                "should_speak": True,
                "need_mode": "mutual_need",
                "opening_style": "shared_context",
                "draft_message": "那、那个……我想确认一下，我们现在这样互相需要的节奏还舒服吗？",
                "topic_evidence": "mutual_need_balance 高",
            },
        }

        dispatch = plugin._build_proactive_dispatch_request(
            decision,
            event_or_session=FakeEvent("s-proactive-adaptive"),
            session_key="s-proactive-adaptive",
            candidate_context="",
        )

        self.assertIn("adaptive_policy", dispatch)
        self.assertFalse(dispatch["adaptive_policy"]["debug_override_used"])
        self.assertGreater(dispatch["max_chars"], 1)
        self.assertGreater(dispatch["ttl_seconds"], 1)
        self.assertGreater(dispatch["cooldown_seconds"], 1.0)


    def test_on_llm_request_registers_proactive_candidate_session(self):
        plugin = new_plugin({"assessment_timing": "post", "inject_state": False})
        request = fake_request(session_id="s-proactive-candidate", prompt="明天提醒我看实验。")

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "s-proactive-candidate",
                    message="明天提醒我看实验。",
                    sender_id="u-1",
                    sender_name="A.L",
                ),
                request,
            ),
        )

        candidate = plugin._proactive_candidate_sessions["s-proactive-candidate"]
        self.assertEqual(candidate["unified_msg_origin"], "s-proactive-candidate")
        self.assertIn("明天提醒我看实验", candidate["last_user_text_excerpt"])
        self.assertEqual(candidate["speaker_id"], "u-1")


    def test_proactive_scheduler_default_disabled_does_not_start(self):
        plugin = new_plugin({"assessment_timing": "post", "inject_state": False})

        async def fail_if_started(self):
            raise AssertionError("proactive scheduler should stay disabled by default")

        bind_async(plugin, "_proactive_scheduler_loop", fail_if_started)

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("s-proactive-disabled", message="只是普通聊天。"),
                fake_request(session_id="s-proactive-disabled", prompt="只是普通聊天。"),
            ),
        )

        self.assertIsNone(plugin._proactive_scheduler_task)
        self.assertEqual(plugin._background_tasks, set())


    def test_proactive_scheduler_defaults_are_low_frequency(self):
        import main

        plugin = new_plugin({"enable_proactive_speech_scheduler": True})

        self.assertLessEqual(main.PROACTIVE_SCHEDULER_WAKE_DELAY_SECONDS, 1.0)
        self.assertGreaterEqual(main.PROACTIVE_SCHEDULER_NORMAL_DELAY_SECONDS, 900.0)
        self.assertGreaterEqual(main.PROACTIVE_SCHEDULER_IDLE_DELAY_SECONDS, 1800.0)
        self.assertGreaterEqual(main.PROACTIVE_SCHEDULER_IDLE_EXIT_ROUNDS, 2)
        self.assertGreaterEqual(main.PROACTIVE_SCHEDULER_SESSION_RECHECK_SECONDS, 3600.0)
        self.assertEqual(main.PROACTIVE_SCHEDULER_MAX_CHECKS_PER_ROUND, 1)
        self.assertEqual(
            plugin._proactive_scheduler_next_delay({"checked": 0, "candidate_count": 0}),
            main.PROACTIVE_SCHEDULER_WAKE_DELAY_SECONDS,
        )
        self.assertEqual(
            plugin._proactive_scheduler_next_delay({"checked": 1, "candidate_count": 2}),
            main.PROACTIVE_SCHEDULER_NORMAL_DELAY_SECONDS,
        )


    def test_proactive_scheduler_idle_result_can_exit_loop(self):
        import main

        plugin = new_plugin({"enable_proactive_speech_scheduler": True})

        self.assertFalse(plugin._proactive_scheduler_should_exit_after_idle(1))
        self.assertTrue(
            plugin._proactive_scheduler_should_exit_after_idle(
                main.PROACTIVE_SCHEDULER_IDLE_EXIT_ROUNDS,
            ),
        )
