try:
    from tests.public_api_helpers import *
except ModuleNotFoundError:
    from public_api_helpers import *


class PublicApiMemoryPart01(MemoryPayloadPublicApiTests):
    def test_integrated_self_snapshot_fuses_always_on_auxiliary_modules(self):
        self._install_astrbot_stubs()
        plugin = self._new_plugin()

        snapshot = asyncio.run(
            plugin.get_integrated_self_snapshot(session_key="s-integrated"),
        )

        self.assertEqual(snapshot["schema_version"], "astrbot.integrated_self_state.v1")
        self.assertTrue(snapshot["enabled"])
        self.assertEqual(snapshot["session_key"], "s-integrated")
        self.assertEqual(snapshot["modules"]["emotion"]["enabled"], True)
        self.assertEqual(snapshot["modules"]["humanlike"]["enabled"], True)
        self.assertEqual(snapshot["modules"]["lifelike_learning"]["enabled"], True)
        self.assertEqual(snapshot["modules"]["personality_drift"]["enabled"], True)
        self.assertEqual(snapshot["modules"]["moral_repair"]["enabled"], False)
        self.assertIn("response_posture", snapshot)
        self.assertIn("connection_readiness", snapshot["state_index"])
        self.assertIn("causal_trace", snapshot)
        self.assertIn("policy_plan", snapshot)
        self.assertIn("compatibility", snapshot)


    def test_integrated_self_can_be_disabled_without_loading_snapshots(self):
        self._install_astrbot_stubs()
        from main import EmotionalStatePlugin

        async def forbidden_load_state(self, session_key, persona_profile=None):
            raise AssertionError("disabled integrated self must not load emotion state")

        original_load_state = EmotionalStatePlugin._load_state
        EmotionalStatePlugin._load_state = forbidden_load_state
        try:
            plugin = self._new_plugin({"enable_integrated_self_state": False})
            snapshot = asyncio.run(
                plugin.get_integrated_self_snapshot(session_key="s-disabled"),
            )
        finally:
            EmotionalStatePlugin._load_state = original_load_state

        self.assertFalse(snapshot["enabled"])
        self.assertEqual(snapshot["reason"], "enable_integrated_self_state is false")


    def test_integrated_self_memory_annotation_is_included_by_default(self):
        self._install_astrbot_stubs()
        plugin = self._new_plugin({"humanlike_memory_write_enabled": False})

        payload = asyncio.run(
            plugin.build_emotion_memory_payload(
                session_key="livingmemory:integrated",
                memory={"text": "memory"},
                source="livingmemory",
                written_at=88.0,
                include_raw_snapshot=False,
            ),
        )

        self.assertIn("integrated_self_state_at_write", payload)
        self.assertIn("personality_drift_state_at_write", payload)
        self.assertIn("state_annotations_at_write", payload)
        annotation = payload["integrated_self_state_at_write"]
        self.assertEqual(annotation["schema_version"], "astrbot.integrated_self_state.v1")
        self.assertEqual(annotation["source"], "livingmemory")
        self.assertEqual(annotation["written_at"], 88.0)
        self.assertIn("response_posture", annotation)
        self.assertIn("causal_trace_summary", annotation)
        self.assertNotIn("integrated_self_snapshot", payload)
        envelope = payload["state_annotations_at_write"]
        self.assertIn("emotion_at_write", envelope["annotation_keys"])
        self.assertIn("personality_drift_state_at_write", envelope["annotation_keys"])
        self.assertIn("integrated_self_state_at_write", envelope["annotation_keys"])
        self.assertNotIn("integrated_self_snapshot", envelope["annotations"])


    def test_memory_payload_fetches_optional_snapshots_concurrently(self):
        self._install_astrbot_stubs()
        plugin = self._new_plugin()

        async def slow_snapshot(kind):
            await asyncio.sleep(0.05)
            return {
                "schema_version": f"astrbot.{kind}.v1",
                "kind": kind,
                "enabled": True,
                "session_key": "s-memory-overlap",
                "values": {},
            }

        async def fake_humanlike(*args, **kwargs):
            return await slow_snapshot("humanlike_state")

        async def fake_lifelike(*args, **kwargs):
            return await slow_snapshot("lifelike_learning_state")

        async def fake_personality_drift(*args, **kwargs):
            return await slow_snapshot("personality_drift_state")

        async def fake_moral_repair(*args, **kwargs):
            return await slow_snapshot("moral_repair_state")

        async def fake_fallibility(*args, **kwargs):
            return await slow_snapshot("fallibility_state")

        plugin.get_humanlike_snapshot = fake_humanlike
        plugin.get_lifelike_learning_snapshot = fake_lifelike
        plugin.get_personality_drift_snapshot = fake_personality_drift
        plugin.get_moral_repair_snapshot = fake_moral_repair
        plugin.get_fallibility_snapshot = fake_fallibility

        started = time.perf_counter()
        payload = asyncio.run(
            plugin.build_emotion_memory_payload(
                session_key="s-memory-overlap",
                source="livingmemory",
                include_raw_snapshot=False,
                include_state_annotations_envelope=True,
            ),
        )
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 0.16)
        self.assertIn("humanlike_state_at_write", payload)
        self.assertIn("lifelike_learning_state_at_write", payload)
        self.assertIn("personality_drift_state_at_write", payload)
        self.assertIn("moral_repair_state_at_write", payload)
        self.assertIn("fallibility_state_at_write", payload)
        self.assertIn("state_annotations_at_write", payload)


    def test_memory_payload_overlaps_emotion_snapshot_with_optional_snapshots(self):
        self._install_astrbot_stubs()
        plugin = self._new_plugin()

        async def slow_snapshot(kind):
            await asyncio.sleep(0.05)
            return {
                "schema_version": f"astrbot.{kind}.v1",
                "kind": kind,
                "enabled": True,
                "session_key": "s-memory-emotion-overlap",
                "values": {},
            }

        async def fake_emotion(*args, **kwargs):
            return await slow_snapshot("emotion_state")

        async def fake_humanlike(*args, **kwargs):
            return await slow_snapshot("humanlike_state")

        async def fake_lifelike(*args, **kwargs):
            return await slow_snapshot("lifelike_learning_state")

        async def fake_personality_drift(*args, **kwargs):
            return await slow_snapshot("personality_drift_state")

        async def fake_moral_repair(*args, **kwargs):
            return await slow_snapshot("moral_repair_state")

        async def fake_fallibility(*args, **kwargs):
            return await slow_snapshot("fallibility_state")

        plugin.get_emotion_snapshot = fake_emotion
        plugin.get_humanlike_snapshot = fake_humanlike
        plugin.get_lifelike_learning_snapshot = fake_lifelike
        plugin.get_personality_drift_snapshot = fake_personality_drift
        plugin.get_moral_repair_snapshot = fake_moral_repair
        plugin.get_fallibility_snapshot = fake_fallibility

        started = time.perf_counter()
        payload = asyncio.run(
            plugin.build_emotion_memory_payload(
                session_key="s-memory-emotion-overlap",
                source="livingmemory",
                include_raw_snapshot=False,
                include_state_annotations_envelope=True,
            ),
        )
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 0.16)
        self.assertIn("emotion_at_write", payload)
        self.assertIn("humanlike_state_at_write", payload)
        self.assertIn("fallibility_state_at_write", payload)


    def test_integrated_self_public_policy_replay_compat_and_diagnostics(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from main import EmotionalStatePlugin

        async def fake_load_state(self, session_key, persona_profile=None):
            state = EmotionState.initial()
            state.label = "protective"
            state.updated_at = 10.0
            state.values["valence"] = -0.3
            state.consequences.active_effects["cold_war"] = 600
            state.consequences.effect_expires_at["cold_war"] = 700.0
            state.consequences.updated_at = 12.0
            return state

        original_load_state = EmotionalStatePlugin._load_state
        EmotionalStatePlugin._load_state = fake_load_state
        try:
            plugin = self._new_plugin(
                {
                    "integrated_self_degradation_profile": "minimal",
                    "humanlike_memory_write_enabled": False,
                    "moral_repair_memory_write_enabled": False,
                    "personality_drift_memory_write_enabled": False,
                },
            )
            plan = asyncio.run(plugin.get_integrated_self_policy_plan(session_key="s1"))
            bundle = asyncio.run(
                plugin.build_integrated_self_replay_bundle(
                    session_key="s1",
                    scenario_name="unit",
                ),
            )
            replay = asyncio.run(plugin.replay_integrated_self_bundle(bundle))
            compat = asyncio.run(plugin.probe_integrated_self_compatibility(bundle["core"]))
            diagnostics = asyncio.run(plugin.export_integrated_self_diagnostics(session_key="s1"))
        finally:
            EmotionalStatePlugin._load_state = original_load_state

        self.assertEqual(plan["degradation_profile"], "minimal")
        self.assertIn("relationship_boundary_active", plan["must_preserve_signals"])
        self.assertTrue(bundle["deterministic"])
        self.assertTrue(replay["matches_bundle_checksum"])
        self.assertFalse(compat["compatible"])
        self.assertTrue(diagnostics["sanitized"])
        self.assertNotIn("snapshots", diagnostics)
        self.assertNotIn("self_interpretation", diagnostics)
        self.assertNotIn("turning_point", diagnostics)
        self.assertNotIn("relational_time_layer", diagnostics)
        self.assertNotIn("turning_point_memory_replay", diagnostics)
        self.assertNotIn("internal_coevolution_signal", str(diagnostics))
        self.assertNotIn("relationship_time_weight", str(diagnostics))

    def test_public_integrated_self_diagnostics_can_explicitly_export_relational_self_at_user_risk(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from main import EmotionalStatePlugin

        async def fake_load_state(self, session_key, persona_profile=None):
            return EmotionState.initial()

        original_load_state = EmotionalStatePlugin._load_state
        EmotionalStatePlugin._load_state = fake_load_state
        try:
            diagnostics = asyncio.run(
                self._new_plugin(
                    {"allow_relational_self_public_export": True},
                ).export_integrated_self_diagnostics(
                    session_key="s-public-risk",
                ),
            )
        finally:
            EmotionalStatePlugin._load_state = original_load_state

        self.assertIn("self_interpretation", diagnostics)
        self.assertIn("self_interpretation", diagnostics["excluded"])
        self.assertEqual(
            diagnostics["self_interpretation"]["kind"],
            "self_interpretation",
        )


    def test_public_api_contract_does_not_expose_relational_self_inference_methods(self):
        import public_api

        public_names = set(public_api._EMOTION_SERVICE_REQUIRED_METHODS)
        forbidden = {
            "get_self_interpretation",
            "get_relational_turning_point",
            "query_relational_turning_points",
            "export_self_interpretation",
            "dump_relational_self_state",
            "list_relational_self_inferences",
            "get_relational_time_layer",
            "query_relational_time_layer",
            "export_relational_time_layer",
            "list_relational_time_events",
            "get_coevolution_model",
            "query_coevolution_state",
            "export_coevolution_model",
            "list_coevolution_events",
            "get_turning_point_memory_replay",
            "query_turning_point_memory_replay",
            "export_turning_point_memory_replay",
            "list_turning_point_replay_events",
        }

        self.assertTrue(public_names.isdisjoint(forbidden))
        self.assertFalse(hasattr(public_api.EmotionServiceProtocol, "get_self_interpretation"))
        self.assertFalse(hasattr(public_api.EmotionServiceProtocol, "get_relational_turning_point"))

    def test_state_annotations_envelope_can_be_disabled(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from main import EmotionalStatePlugin

        async def fake_load_state(self, session_key, persona_profile=None, **kwargs):
            return EmotionState.initial()

        original_load_state = EmotionalStatePlugin._load_state
        EmotionalStatePlugin._load_state = fake_load_state
        try:
            payload = asyncio.run(
                self._new_plugin(
                    {
                        "humanlike_memory_write_enabled": False,
                        "moral_repair_memory_write_enabled": False,
                        "personality_drift_memory_write_enabled": False,
                        "integrated_self_memory_write_enabled": False,
                    },
                ).build_emotion_memory_payload(
                    session_key="s-envelope-off",
                    memory="memory",
                    include_state_annotations_envelope=False,
                ),
            )
        finally:
            EmotionalStatePlugin._load_state = original_load_state

        self.assertNotIn("state_annotations_at_write", payload)


    def test_plugin_method_uses_explicit_session_key_without_writing_state(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from main import EmotionalStatePlugin

        calls = []

        async def fake_load_state(self, session_key, persona_profile=None):
            calls.append((session_key, persona_profile))
            state = EmotionState.initial()
            state.label = "calm"
            state.updated_at = 10.0
            state.dynamics = {"alpha_base": 0.33, "baseline_half_life_seconds": 7200.0}
            return state

        original_load_state = EmotionalStatePlugin._load_state
        original_save_state = EmotionalStatePlugin._save_state
        EmotionalStatePlugin._load_state = fake_load_state
        EmotionalStatePlugin._save_state = (
            lambda self, session_key, state: (_ for _ in ()).throw(
                AssertionError("memory payload must be read-only"),
            )
        )
        try:
            plugin = self._new_plugin()
            payload = asyncio.run(
                plugin.build_emotion_memory_payload(
                    session_key="livingmemory:user-1",
                    memory={"text": "memory"},
                    source="livingmemory",
                    written_at=20.0,
                ),
            )
        finally:
            EmotionalStatePlugin._load_state = original_load_state
            EmotionalStatePlugin._save_state = original_save_state

        self.assertEqual(calls[0][0], "livingmemory:user-1")
        self.assertEqual(payload["session_key"], "livingmemory:user-1")
        self.assertEqual(payload["emotion_at_write"]["label"], "calm")
        self.assertIn("dynamics", payload["emotion_at_write"])
        self.assertEqual(payload["emotion_at_write"]["dynamics"]["alpha_base"], 0.33)
        self.assertEqual(payload["emotion_at_write"]["written_at"], 20.0)
        self.assertEqual(payload["memory"]["text"], "memory")


    def test_on_llm_request_updates_and_injects_always_on_auxiliary_states_by_default(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from humanlike_engine import HumanlikeState
        from lifelike_learning_engine import LifelikeLearningState
        from personality_drift_engine import PersonalityDriftState
        from main import EmotionalStatePlugin

        saves = []

        async def fake_persona(self, event, request):
            return None

        async def fake_load_state(self, session_key, persona_profile=None, **kwargs):
            return EmotionState.initial()

        async def fake_save_state(self, session_key, state):
            pass

        async def fake_load_humanlike(self, session_key, **kwargs):
            return HumanlikeState.initial()

        async def fake_save_humanlike(self, session_key, state):
            saves.append(("humanlike", session_key, state))

        async def fake_load_lifelike(self, session_key, **kwargs):
            return LifelikeLearningState.initial()

        async def fake_save_lifelike(self, session_key, state):
            saves.append(("lifelike", session_key, state))

        async def fake_load_drift(self, session_key, profile=None, **kwargs):
            return PersonalityDriftState.initial()

        async def fake_save_drift(self, session_key, state):
            saves.append(("drift", session_key, state))

        original_persona = EmotionalStatePlugin._persona_profile
        original_load_state = EmotionalStatePlugin._load_state
        original_save_state = EmotionalStatePlugin._save_state
        original_load_humanlike = EmotionalStatePlugin._load_humanlike_state
        original_save_humanlike = EmotionalStatePlugin._save_humanlike_state
        original_load_lifelike = EmotionalStatePlugin._load_lifelike_learning_state
        original_save_lifelike = EmotionalStatePlugin._save_lifelike_learning_state
        original_load_drift = EmotionalStatePlugin._load_personality_drift_state
        original_save_drift = EmotionalStatePlugin._save_personality_drift_state
        EmotionalStatePlugin._persona_profile = fake_persona
        EmotionalStatePlugin._load_state = fake_load_state
        EmotionalStatePlugin._save_state = fake_save_state
        EmotionalStatePlugin._load_humanlike_state = fake_load_humanlike
        EmotionalStatePlugin._save_humanlike_state = fake_save_humanlike
        EmotionalStatePlugin._load_lifelike_learning_state = fake_load_lifelike
        EmotionalStatePlugin._save_lifelike_learning_state = fake_save_lifelike
        EmotionalStatePlugin._load_personality_drift_state = fake_load_drift
        EmotionalStatePlugin._save_personality_drift_state = fake_save_drift
        try:
            plugin = self._new_plugin(
                {"use_llm_assessor": False, "assessment_timing": "pre"},
            )
            event = SimpleNamespace(unified_msg_origin="s1", message_str="你好")
            request = SimpleNamespace(
                system_prompt="",
                contexts=[],
                prompt="你好",
                extra_user_content_parts=[],
                session_id="s1",
            )
            asyncio.run(plugin.on_llm_request(event, request))
        finally:
            EmotionalStatePlugin._persona_profile = original_persona
            EmotionalStatePlugin._load_state = original_load_state
            EmotionalStatePlugin._save_state = original_save_state
            EmotionalStatePlugin._load_humanlike_state = original_load_humanlike
            EmotionalStatePlugin._save_humanlike_state = original_save_humanlike
            EmotionalStatePlugin._load_lifelike_learning_state = original_load_lifelike
            EmotionalStatePlugin._save_lifelike_learning_state = original_save_lifelike
            EmotionalStatePlugin._load_personality_drift_state = original_load_drift
            EmotionalStatePlugin._save_personality_drift_state = original_save_drift

        self.assertIn("humanlike", [item[0] for item in saves])
        self.assertIn("lifelike", [item[0] for item in saves])
        self.assertGreaterEqual(len(request.extra_user_content_parts), 3)
        self.assertIn("bot_emotion_state", request.extra_user_content_parts[0].text)
        self.assertIn(
            "bot_auxiliary_state",
            "\n".join(part.text for part in request.extra_user_content_parts[1:]),
        )
