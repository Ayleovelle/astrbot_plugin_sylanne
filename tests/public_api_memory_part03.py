try:
    from tests.public_api_helpers import *
except ModuleNotFoundError:
    from public_api_helpers import *


class PublicApiMemoryPart03(MemoryPayloadPublicApiTests):
    def test_proactive_progress_check_without_evidence_is_downgraded(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from group_atmosphere_engine import GroupAtmosphereState
        from humanlike_engine import HumanlikeState
        from lifelike_learning_engine import LifelikeLearningState
        from main import EmotionalStatePlugin

        class FakeContext:
            async def llm_generate(self, **kwargs):
                return SimpleNamespace(
                    completion_text=(
                        '{"should_speak":true,"need_mode":"progress_check",'
                        '"topic_text":"","speech_intent":"关心进度",'
                        '"opening_style":"progress_check","topic_evidence":"没有明确证据",'
                        '"draft_message":"那、那个……你之前那件事现在进度还顺吗？",'
                        '"confidence":0.83,"reason":"模型想问进度"}'
                    ),
                )

        async def fake_provider_id(self, event):
            return "provider"

        async def fake_load_state(self, session_key, persona_profile=None, *, now=None):
            state = EmotionState.initial()
            state.values["affiliation"] = 0.7
            state.values["valence"] = 0.5
            return state

        async def fake_lifelike(self, session_key, *, now=None):
            state = LifelikeLearningState.initial()
            state.values.update(
                {
                    "rapport": 0.86,
                    "common_ground": 0.74,
                    "initiative_readiness": 0.88,
                    "boundary_sensitivity": 0.08,
                    "mutual_need_balance": 0.68,
                    "being_needed_readiness": 0.70,
                    "need_expression_readiness": 0.60,
                    "preference_confidence": 0.70,
                },
            )
            return state

        async def fake_humanlike(self, session_key, *, now=None):
            return HumanlikeState.initial()

        async def fake_group(self, session_key, *, now=None):
            state = GroupAtmosphereState.initial()
            state.values["joinability"] = 0.90
            state.values["bot_attention"] = 0.82
            state.values["playfulness"] = 0.76
            state.values["interrupt_risk"] = 0.04
            state.values["tension"] = 0.02
            return state

        originals = {
            "_provider_id": EmotionalStatePlugin._provider_id,
            "_load_state": EmotionalStatePlugin._load_state,
            "_load_lifelike_learning_state": EmotionalStatePlugin._load_lifelike_learning_state,
            "_load_humanlike_state": EmotionalStatePlugin._load_humanlike_state,
            "_load_group_atmosphere_state": EmotionalStatePlugin._load_group_atmosphere_state,
        }
        EmotionalStatePlugin._provider_id = fake_provider_id
        EmotionalStatePlugin._load_state = fake_load_state
        EmotionalStatePlugin._load_lifelike_learning_state = fake_lifelike
        EmotionalStatePlugin._load_humanlike_state = fake_humanlike
        EmotionalStatePlugin._load_group_atmosphere_state = fake_group
        try:
            plugin = self._new_plugin({"use_llm_assessor": True})
            plugin.context = FakeContext()
            decision = asyncio.run(
                plugin.get_proactive_speech_decision(
                    SimpleNamespace(unified_msg_origin="s-no-progress"),
                    candidate_context="刚才只是普通闲聊，话题已经结束。",
                ),
            )
        finally:
            for name, value in originals.items():
                setattr(EmotionalStatePlugin, name, value)

        judgement = decision["topic_judgement"]
        self.assertEqual(judgement["source"], "evidence_gate")
        self.assertIn(judgement["need_mode"], {"playful_ping", "prank_light", "silence"})
        self.assertNotEqual(judgement["need_mode"], "progress_check")
        self.assertNotIn("进度还顺", decision["dispatch_request"]["message_text"])


    def test_proactive_dispatch_policy_extends_cooldown_after_cold_feedback(self):
        self._install_astrbot_stubs()
        from main import EmotionalStatePlugin

        plugin = self._new_plugin()
        decision = {
            "score": 0.76,
            "signals": {
                "boundary": 0.08,
                "overload": 0.05,
                "repair_need": 0.0,
                "companionship_need": 0.55,
                "user_need_to_be_met": 0.50,
                "bot_need_to_express": 0.44,
            },
        }
        baseline = plugin._derive_proactive_dispatch_policy(
            decision,
            session_key="s-feedback",
        )
        plugin._proactive_dispatch_audit = {
            "s-feedback": deque(
                [
                    {"sent": True, "feedback_status": "cold_reply"},
                    {"sent": True, "feedback_status": "unanswered"},
                ],
                maxlen=24,
            ),
        }

        cooled = plugin._derive_proactive_dispatch_policy(
            decision,
            session_key="s-feedback",
        )

        self.assertGreater(cooled["feedback_pressure"], 0.0)
        self.assertGreater(cooled["cooldown_seconds"], baseline["cooldown_seconds"])


    def test_proactive_dispatch_respects_recent_activity_quiet_period(self):
        self._install_astrbot_stubs()

        plugin = self._new_plugin({"enable_proactive_speech_dispatch": True})
        plugin.context = SimpleNamespace(send_message=lambda *args, **kwargs: None)
        plugin._proactive_candidate_sessions = {
            "s-quiet": {
                "session_key": "s-quiet",
                "unified_msg_origin": "s-quiet",
                "last_seen_at": 1000.0,
            },
        }
        decision = {
            "should_speak": True,
            "action": "speak_now",
            "score": 0.74,
            "signals": {
                "boundary": 0.08,
                "overload": 0.05,
                "repair_need": 0.0,
                "companionship_need": 0.66,
                "user_need_to_be_met": 0.42,
                "bot_need_to_express": 0.58,
            },
            "topic_judgement": {
                "should_speak": True,
                "need_mode": "playful_ping",
                "opening_style": "playful_ping",
                "draft_message": "咦，我、我来轻轻敲一下门。你现在方便被打扰一下吗？",
                "topic_evidence": "轻松氛围信号",
            },
        }
        event = SimpleNamespace(unified_msg_origin="s-quiet")
        dispatch = plugin._build_proactive_dispatch_request(
            decision,
            event_or_session=event,
            session_key="s-quiet",
            candidate_context="刚刚结束闲聊。",
        )

        plugin._observed_now = lambda: 1100.0
        blocked = plugin._proactive_dispatch_blocked_reason(
            decision,
            dispatch,
            event_or_session=event,
            dry_run=False,
            force=False,
        )
        self.assertEqual(blocked, "recent_user_activity_quiet_period")
        self.assertIn("quiet_gate", dispatch)
        self.assertGreater(dispatch["quiet_gate"]["min_idle_seconds"], 100.0)

        plugin._observed_now = lambda: 20000.0
        allowed = plugin._proactive_dispatch_blocked_reason(
            decision,
            dispatch,
            event_or_session=event,
            dry_run=False,
            force=False,
        )
        self.assertEqual(allowed, "")


    def test_proactive_speech_dispatch_executes_when_enabled_and_records_cooldown(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from group_atmosphere_engine import GroupAtmosphereState
        from humanlike_engine import HumanlikeState
        from lifelike_learning_engine import LifelikeLearningState
        from main import EmotionalStatePlugin

        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, message))
                return {"ok": True}

        async def fake_load_state(self, session_key, persona_profile=None, *, now=None):
            state = EmotionState.initial()
            state.values["affiliation"] = 0.8
            state.values["valence"] = 0.4
            return state

        async def fake_lifelike(self, session_key, *, now=None):
            state = LifelikeLearningState.initial()
            state.values.update(
                {
                    "rapport": 0.9,
                    "common_ground": 0.82,
                    "initiative_readiness": 0.9,
                    "boundary_sensitivity": 0.05,
                    "mutual_need_balance": 0.76,
                    "being_needed_readiness": 0.78,
                    "need_expression_readiness": 0.64,
                    "preference_confidence": 0.7,
                },
            )
            state.user_profile.facts["project"] = "桥隧交叉项目进度"
            return state

        async def fake_humanlike(self, session_key, *, now=None):
            return HumanlikeState.initial()

        async def fake_group(self, session_key, *, now=None):
            state = GroupAtmosphereState.initial()
            state.values["joinability"] = 0.92
            state.values["bot_attention"] = 0.82
            state.values["playfulness"] = 0.72
            state.values["interrupt_risk"] = 0.05
            return state

        async def fake_judge(self, event_or_session, *, decision, topics, candidate_context, use_llm):
            return {
                "schema_version": "astrbot.proactive_topic_judgement.v1",
                "kind": "llm_topic_judgement",
                "should_speak": True,
                "need_mode": "progress_check",
                "topic_text": "桥隧交叉项目进度",
                "speech_intent": "关心用户近期项目进展",
                "opening_style": "progress_check",
                "topic_evidence": "用户画像事实里记录了项目进度线索",
                "draft_message": "那、那个……桥隧交叉项目现在进度还顺吗？",
                "confidence": 0.86,
                "reason": "进度线索明确且打扰风险低",
                "source": "llm",
            }

        saves = []

        async def fake_save_lifelike(self, session_key, state):
            saves.append((session_key, state.last_observation))

        originals = {
            "_load_state": EmotionalStatePlugin._load_state,
            "_load_lifelike_learning_state": EmotionalStatePlugin._load_lifelike_learning_state,
            "_load_humanlike_state": EmotionalStatePlugin._load_humanlike_state,
            "_load_group_atmosphere_state": EmotionalStatePlugin._load_group_atmosphere_state,
            "_judge_proactive_topic": EmotionalStatePlugin._judge_proactive_topic,
            "_save_lifelike_learning_state": EmotionalStatePlugin._save_lifelike_learning_state,
        }
        EmotionalStatePlugin._load_state = fake_load_state
        EmotionalStatePlugin._load_lifelike_learning_state = fake_lifelike
        EmotionalStatePlugin._load_humanlike_state = fake_humanlike
        EmotionalStatePlugin._load_group_atmosphere_state = fake_group
        EmotionalStatePlugin._judge_proactive_topic = fake_judge
        EmotionalStatePlugin._save_lifelike_learning_state = fake_save_lifelike
        try:
            plugin = self._new_plugin(
                {
                    "enable_realtime_chat": True,
                    "enable_proactive_speech_dispatch": True,
                    "proactive_speech_dispatch_cooldown_seconds": 1800.0,
                },
            )
            plugin.context = FakeContext()
            event = SimpleNamespace(unified_msg_origin="s-proactive")
            result = asyncio.run(
                plugin.request_proactive_speech_dispatch(
                    event,
                    candidate_context="用户正在推进桥隧交叉项目。",
                    use_llm=False,
                ),
            )
            second = asyncio.run(
                plugin.request_proactive_speech_dispatch(
                    event,
                    candidate_context="用户正在推进桥隧交叉项目。",
                    use_llm=False,
                ),
            )
        finally:
            for name, value in originals.items():
                setattr(EmotionalStatePlugin, name, value)

        self.assertTrue(result["sent"])
        self.assertEqual(sent[0][0], "s-proactive")
        sent_text = "\n".join(str(message) for _, message in sent)
        self.assertIn("桥隧交叉项目", sent_text)
        self.assertEqual(second["blocked_reason"], "cooldown_active")
        self.assertEqual(len(sent), result["dispatch_request"]["realtime_chat_plan"]["message_count"])
        self.assertEqual(saves[0][0], "s-proactive")


    def test_proactive_speech_dispatch_default_disabled_returns_request_only(self):
        self._install_astrbot_stubs()
        from main import EmotionalStatePlugin

        async def fake_decision(self, *args, **kwargs):
            return {
                "schema_version": "astrbot.proactive_speech_policy.v1",
                "kind": "proactive_speech_decision",
                "action": "speak_now",
                "should_speak": True,
                "score": 0.8,
                "reason": "test",
                "selected_topic": {"topic": "测试话题", "reason": "测试证据"},
                "topic_judgement": {
                    "should_speak": True,
                    "need_mode": "missing_user",
                    "opening_style": "light_question",
                    "speech_intent": "想念用户",
                    "topic_text": "测试话题",
                    "topic_evidence": "测试证据",
                    "draft_message": "那、那个……我只是确认一下你还好吗？",
                    "reason": "测试理由",
                },
            }

        called = []

        class FakeContext:
            async def send_message(self, origin, message):
                called.append((origin, message))

        original = EmotionalStatePlugin.get_proactive_speech_decision
        EmotionalStatePlugin.get_proactive_speech_decision = fake_decision
        try:
            plugin = self._new_plugin()
            plugin.context = FakeContext()
            result = asyncio.run(
                plugin.request_proactive_speech_dispatch(
                    SimpleNamespace(unified_msg_origin="s-disabled"),
                ),
            )
        finally:
            EmotionalStatePlugin.get_proactive_speech_decision = original

        self.assertFalse(result["sent"])
        self.assertEqual(result["blocked_reason"], "dispatch_disabled")
        self.assertTrue(result["dispatch_request"]["requested"])
        self.assertEqual(called, [])


    def test_low_reasoning_mode_does_not_change_local_state_dynamics(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState, build_persona_profile
        from main import EmotionalStatePlugin

        llm_payload = (
            '{"label":"anger","dimensions":{"valence":-0.55,"arousal":0.66,'
            '"dominance":0.12,"goal_congruence":-0.62,"certainty":0.58,'
            '"control":-0.35,"affiliation":-0.48},"confidence":0.82,'
            '"appraisal":{"relationship_decision":{"decision":"boundary",'
            '"intensity":0.54,"forgiveness":0.28,"reason":"fixed"}},'
            '"reason":"fixed observation"}'
        )

        async def fake_provider_id(self, event):
            return "provider"

        class FakeContext:
            async def llm_generate(self, **kwargs):
                return SimpleNamespace(completion_text=llm_payload)

        async def run_case(low_reasoning):
            plugin = self._new_plugin(
                {
                    "low_reasoning_friendly_mode": low_reasoning,
                    "low_reasoning_max_context_chars": 60,
                    "max_context_chars": 5000,
                },
            )
            plugin.context = FakeContext()
            persona_profile = build_persona_profile(
                persona_id="p",
                name="p",
                text="敏感 谨慎 但重视边界",
            )
            previous = EmotionState.initial(persona_profile)
            previous.updated_at = 1000.0
            observation = await plugin._assess_emotion(
                event=SimpleNamespace(unified_msg_origin="s1"),
                phase="pre_response",
                previous_state=previous,
                persona_profile=persona_profile,
                context_text="A" * 200,
                current_text="B" * 200,
            )
            state = plugin._engine_for_persona(persona_profile).update(
                previous,
                observation,
                profile=persona_profile,
                now=1020.0,
            )
            return state.to_dict()

        original_provider_id = EmotionalStatePlugin._provider_id
        EmotionalStatePlugin._provider_id = fake_provider_id
        try:
            normal = asyncio.run(run_case(False))
            low = asyncio.run(run_case(True))
        finally:
            EmotionalStatePlugin._provider_id = original_provider_id

        self.assertEqual(low["values"], normal["values"])
        self.assertEqual(low["label"], normal["label"])
        self.assertEqual(low["last_alpha"], normal["last_alpha"])
        self.assertEqual(low["last_surprise"], normal["last_surprise"])
        self.assertEqual(low["consequences"], normal["consequences"])
