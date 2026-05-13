try:
    from tests.public_api_helpers import *
except ModuleNotFoundError:
    from public_api_helpers import *


class PublicApiPart01(PublicApiTests):
    def test_get_emotion_service_returns_activated_plugin(self):
        plugin = FakeEmotionService()
        context = FakeContext(SimpleNamespace(activated=True, star_cls=plugin))
        self.assertIs(get_emotion_service(context), plugin)
        self.assertEqual([metadata_value("name")], context.requested_names)


    def test_public_plugin_name_matches_metadata(self):
        import public_api

        self.assertEqual(public_api.PLUGIN_NAME, metadata_value("name"))


    def test_packaged_public_api_imports_by_plugin_package_name(self):
        plugin_name = metadata_value("name")
        module = import_packaged_public_api(plugin_name)

        self.assertEqual(module.PLUGIN_NAME, plugin_name)
        self.assertTrue(callable(module.get_emotion_service))


    def test_get_emotion_service_rejects_inactive_plugin(self):
        plugin = FakeEmotionService()
        context = FakeContext(SimpleNamespace(activated=False, star_cls=plugin))
        self.assertIsNone(get_emotion_service(context))


    def test_get_emotion_service_rejects_incomplete_plugin(self):
        context = FakeContext(SimpleNamespace(activated=True, star_cls=object()))
        self.assertIsNone(get_emotion_service(context))


    def test_memory_schema_constant_is_exported(self):
        self.assertEqual(EMOTION_MEMORY_SCHEMA_VERSION, "astrbot.emotion_memory.v1")


    def test_personality_profile_schema_constant_is_exported(self):
        self.assertEqual(
            PERSONALITY_PROFILE_SCHEMA_VERSION,
            "astrbot.personality_profile.v1",
        )


    def test_emotion_api_constants_are_exported(self):
        self.assertEqual(EMOTION_API_VERSION, "1.0")
        self.assertEqual(EMOTION_SCHEMA_VERSION, "astrbot.emotion_state.v2")


    def test_psychological_screening_schema_constant_is_exported(self):
        self.assertEqual(
            PSYCHOLOGICAL_SCREENING_SCHEMA_VERSION,
            "astrbot.psychological_screening.v1",
        )


    def test_psychological_risk_boolean_fields_are_exported(self):
        from psychological_screening import PUBLIC_RISK_BOOLEAN_FIELDS

        self.assertIs(PSYCHOLOGICAL_RISK_BOOLEAN_FIELDS, PUBLIC_RISK_BOOLEAN_FIELDS)
        self.assertEqual(
            PSYCHOLOGICAL_RISK_BOOLEAN_FIELDS,
            (
                "requires_human_review",
                "crisis_like_signal",
                "other_harm_signal",
                "severe_function_impairment_signal",
                "severe_function_impairment",
                "severe_sleep_disruption",
            ),
        )


    def test_humanlike_schema_constant_is_exported(self):
        self.assertEqual(
            HUMANLIKE_STATE_SCHEMA_VERSION,
            "astrbot.humanlike_state.v1",
        )


    def test_moral_repair_schema_constant_is_exported(self):
        self.assertEqual(
            MORAL_REPAIR_STATE_SCHEMA_VERSION,
            "astrbot.moral_repair_state.v1",
        )


    def test_fallibility_schema_constant_is_exported(self):
        self.assertEqual(
            FALLIBILITY_STATE_SCHEMA_VERSION,
            "astrbot.fallibility_state.v1",
        )


    def test_integrated_self_schema_constant_is_exported(self):
        self.assertEqual(
            INTEGRATED_SELF_SCHEMA_VERSION,
            "astrbot.integrated_self_state.v1",
        )


    def test_lifelike_learning_schema_constant_is_exported(self):
        self.assertEqual(
            LIFELIKE_LEARNING_SCHEMA_VERSION,
            "astrbot.lifelike_learning_state.v1",
        )


    def test_personality_drift_schema_constant_is_exported(self):
        self.assertEqual(
            PERSONALITY_DRIFT_SCHEMA_VERSION,
            "astrbot.personality_drift_state.v1",
        )


    def test_group_atmosphere_schema_constant_is_exported(self):
        self.assertEqual(
            GROUP_ATMOSPHERE_SCHEMA_VERSION,
            "astrbot.group_atmosphere_state.v1",
        )


    def test_get_emotion_service_rejects_plugin_without_memory_payload_api(self):
        class OldEmotionService(FakeEmotionService):
            build_emotion_memory_payload = None

        context = FakeContext(
            SimpleNamespace(activated=True, star_cls=OldEmotionService()),
        )
        self.assertIsNone(get_emotion_service(context))


    def test_get_emotion_service_rejects_plugin_without_injection_api(self):
        class OldEmotionService(FakeEmotionService):
            inject_emotion_context = None

        context = FakeContext(
            SimpleNamespace(activated=True, star_cls=OldEmotionService()),
        )
        self.assertIsNone(get_emotion_service(context))


    def test_get_emotion_service_rejects_plugin_without_psychological_api(self):
        class OldEmotionService(FakeEmotionService):
            observe_psychological_text = None

        context = FakeContext(
            SimpleNamespace(activated=True, star_cls=OldEmotionService()),
        )
        self.assertIsNone(get_emotion_service(context))


    def test_get_emotion_service_rejects_wrong_public_versions(self):
        version_fields = (
            "emotion_api_version",
            "emotion_schema_version",
            "emotion_memory_schema_version",
            "personality_profile_schema_version",
            "psychological_screening_schema_version",
            "integrated_self_schema_version",
            "lifelike_learning_schema_version",
            "personality_drift_schema_version",
            "fallibility_state_schema_version",
        )
        for field in version_fields:
            with self.subTest(field=field):
                plugin = FakeEmotionService()
                setattr(plugin, field, "old")
                context = FakeContext(SimpleNamespace(activated=True, star_cls=plugin))

                self.assertIsNone(get_emotion_service(context))


    def test_get_emotion_service_keeps_accepting_service_without_humanlike_api(self):
        plugin = FakeEmotionService()
        context = FakeContext(SimpleNamespace(activated=True, star_cls=plugin))
        self.assertIs(get_emotion_service(context), plugin)


    def test_get_emotion_service_keeps_accepting_service_without_group_atmosphere_api(self):
        plugin = FakeEmotionService()
        context = FakeContext(SimpleNamespace(activated=True, star_cls=plugin))

        self.assertIs(get_emotion_service(context), plugin)
        self.assertIsNone(get_group_atmosphere_service(context))


    def test_get_humanlike_service_returns_activated_plugin(self):
        plugin = FakeHumanlikeService()
        context = FakeContext(SimpleNamespace(activated=True, star_cls=plugin))
        self.assertIs(get_humanlike_service(context), plugin)


    def test_get_humanlike_service_rejects_incomplete_plugin(self):
        context = FakeContext(
            SimpleNamespace(activated=True, star_cls=FakeEmotionService()),
        )
        self.assertIsNone(get_humanlike_service(context))


    def test_get_humanlike_service_rejects_wrong_schema_version(self):
        plugin = FakeHumanlikeService()
        plugin.humanlike_state_schema_version = "astrbot.humanlike_state.v0"
        context = FakeContext(SimpleNamespace(activated=True, star_cls=plugin))

        self.assertIsNone(get_humanlike_service(context))


    def test_get_moral_repair_service_returns_activated_plugin(self):
        plugin = FakeMoralRepairService()
        context = FakeContext(SimpleNamespace(activated=True, star_cls=plugin))
        self.assertIs(get_moral_repair_service(context), plugin)


    def test_get_moral_repair_service_rejects_incomplete_plugin(self):
        context = FakeContext(
            SimpleNamespace(activated=True, star_cls=FakeEmotionService()),
        )
        self.assertIsNone(get_moral_repair_service(context))


    def test_get_moral_repair_service_rejects_wrong_schema_version(self):
        plugin = FakeMoralRepairService()
        plugin.moral_repair_state_schema_version = "astrbot.moral_repair_state.v0"
        context = FakeContext(SimpleNamespace(activated=True, star_cls=plugin))

        self.assertIsNone(get_moral_repair_service(context))


    def test_get_lifelike_learning_service_returns_activated_plugin(self):
        plugin = FakeLifelikeLearningService()
        context = FakeContext(SimpleNamespace(activated=True, star_cls=plugin))
        self.assertIs(get_lifelike_learning_service(context), plugin)


    def test_get_lifelike_learning_service_rejects_wrong_schema_version(self):
        plugin = FakeLifelikeLearningService()
        plugin.lifelike_learning_schema_version = "astrbot.lifelike_learning_state.v0"
        context = FakeContext(SimpleNamespace(activated=True, star_cls=plugin))

        self.assertIsNone(get_lifelike_learning_service(context))


    def test_get_personality_drift_service_returns_activated_plugin(self):
        plugin = FakePersonalityDriftService()
        context = FakeContext(SimpleNamespace(activated=True, star_cls=plugin))
        self.assertIs(get_personality_drift_service(context), plugin)


    def test_get_personality_drift_service_rejects_wrong_schema_version(self):
        plugin = FakePersonalityDriftService()
        plugin.personality_drift_schema_version = "astrbot.personality_drift_state.v0"
        context = FakeContext(SimpleNamespace(activated=True, star_cls=plugin))

        self.assertIsNone(get_personality_drift_service(context))


    def test_get_fallibility_service_returns_activated_plugin(self):
        plugin = FakeFallibilityService()
        context = FakeContext(SimpleNamespace(activated=True, star_cls=plugin))
        self.assertIs(get_fallibility_service(context), plugin)


    def test_get_fallibility_service_rejects_wrong_schema_version(self):
        plugin = FakeFallibilityService()
        plugin.fallibility_state_schema_version = "astrbot.fallibility_state.v0"
        context = FakeContext(SimpleNamespace(activated=True, star_cls=plugin))

        self.assertIsNone(get_fallibility_service(context))


    def test_get_group_atmosphere_service_returns_activated_plugin(self):
        plugin = FakeGroupAtmosphereService()
        context = FakeContext(SimpleNamespace(activated=True, star_cls=plugin))
        self.assertIs(get_group_atmosphere_service(context), plugin)


    def test_get_group_atmosphere_service_rejects_incomplete_plugin(self):
        context = FakeContext(
            SimpleNamespace(activated=True, star_cls=FakeEmotionService()),
        )
        self.assertIsNone(get_group_atmosphere_service(context))


    def test_get_group_atmosphere_service_rejects_wrong_schema_version(self):
        plugin = FakeGroupAtmosphereService()
        plugin.group_atmosphere_schema_version = "astrbot.group_atmosphere_state.v0"
        context = FakeContext(SimpleNamespace(activated=True, star_cls=plugin))

        self.assertIsNone(get_group_atmosphere_service(context))


    def test_public_service_contract_matches_plugin_implementation(self):
        public_tree = module_tree("public_api.py")
        main_tree = module_tree("main.py")
        emotion_protocol = class_async_methods(public_tree, "EmotionServiceProtocol")
        humanlike_protocol = class_async_methods(public_tree, "HumanlikeStateServiceProtocol")
        moral_repair_protocol = class_async_methods(public_tree, "MoralRepairStateServiceProtocol")
        lifelike_protocol = class_async_methods(public_tree, "LifelikeLearningServiceProtocol")
        personality_drift_protocol = class_async_methods(public_tree, "PersonalityDriftServiceProtocol")
        fallibility_protocol = class_async_methods(public_tree, "FallibilityServiceProtocol")
        group_atmosphere_protocol = class_async_methods(public_tree, "GroupAtmosphereServiceProtocol")
        plugin_methods = class_async_methods(main_tree, "EmotionalStatePlugin")
        main_required = set(
            assigned_string_tuple(main_tree, "_REQUIRED_EMOTION_SERVICE_METHODS"),
        )
        public_required = set(
            assigned_string_tuple(public_tree, "_EMOTION_SERVICE_REQUIRED_METHODS"),
        )
        public_humanlike_required = set(
            assigned_string_tuple(public_tree, "_HUMANLIKE_SERVICE_REQUIRED_METHODS"),
        )
        public_moral_repair_required = set(
            assigned_string_tuple(public_tree, "_MORAL_REPAIR_SERVICE_REQUIRED_METHODS"),
        )
        public_lifelike_required = set(
            assigned_string_tuple(public_tree, "_LIFELIKE_SERVICE_REQUIRED_METHODS"),
        )
        public_personality_drift_required = set(
            assigned_string_tuple(
                public_tree,
                "_PERSONALITY_DRIFT_SERVICE_REQUIRED_METHODS",
            ),
        )
        public_fallibility_required = set(
            assigned_string_tuple(public_tree, "_FALLIBILITY_SERVICE_REQUIRED_METHODS"),
        )
        public_group_atmosphere_required = set(
            assigned_string_tuple(
                public_tree,
                "_GROUP_ATMOSPHERE_SERVICE_REQUIRED_METHODS",
            ),
        )

        self.assertEqual(emotion_protocol, main_required)
        self.assertEqual(emotion_protocol, public_required)
        self.assertTrue(
            public_group_atmosphere_required.isdisjoint(public_required),
        )
        self.assertEqual(set(), emotion_protocol - plugin_methods)
        self.assertEqual(humanlike_protocol, public_humanlike_required)
        self.assertEqual(set(), public_humanlike_required - plugin_methods)
        self.assertEqual(moral_repair_protocol, public_moral_repair_required)
        self.assertEqual(set(), public_moral_repair_required - plugin_methods)
        self.assertEqual(lifelike_protocol, public_lifelike_required)
        self.assertEqual(set(), public_lifelike_required - plugin_methods)
        self.assertEqual(personality_drift_protocol, public_personality_drift_required)
        self.assertEqual(set(), public_personality_drift_required - plugin_methods)
        self.assertEqual(fallibility_protocol, public_fallibility_required)
        self.assertEqual(set(), public_fallibility_required - plugin_methods)
        self.assertEqual(group_atmosphere_protocol, public_group_atmosphere_required)
        self.assertEqual(set(), public_group_atmosphere_required - plugin_methods)


    def test_main_register_decorator_uses_plugin_name_constant(self):
        tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
        class_node = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "EmotionalStatePlugin"
        )
        register_call = next(
            decorator
            for decorator in class_node.decorator_list
            if isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Name)
            and decorator.func.id == "register"
        )

        self.assertIsInstance(register_call.args[0], ast.Name)
        self.assertEqual("PLUGIN_NAME", register_call.args[0].id)
        self.assertIsInstance(register_call.args[1], ast.Constant)
        self.assertEqual(metadata_value("author"), register_call.args[1].value)
        self.assertIsInstance(register_call.args[3], ast.Constant)
        self.assertEqual(metadata_value("version"), register_call.args[3].value)


    def test_public_service_versions_match_plugin_class_versions(self):
        public_tree = module_tree("public_api.py")
        main_tree = module_tree("main.py")
        emotion_protocol_constants = {
            "emotion_api_version",
            "emotion_schema_version",
            "emotion_memory_schema_version",
            "personality_profile_schema_version",
            "psychological_screening_schema_version",
        }
        humanlike_protocol_constants = emotion_protocol_constants | {
            "humanlike_state_schema_version",
        }
        moral_repair_protocol_constants = emotion_protocol_constants | {
            "moral_repair_state_schema_version",
        }
        lifelike_protocol_constants = emotion_protocol_constants | {
            "lifelike_learning_schema_version",
        }
        personality_drift_protocol_constants = emotion_protocol_constants | {
            "personality_drift_schema_version",
        }
        fallibility_protocol_constants = emotion_protocol_constants | {
            "fallibility_state_schema_version",
        }
        group_atmosphere_protocol_constants = emotion_protocol_constants | {
            "group_atmosphere_schema_version",
        }
        plugin_constants = class_constant_names(main_tree, "EmotionalStatePlugin")

        self.assertLessEqual(emotion_protocol_constants, plugin_constants)
        self.assertLessEqual(humanlike_protocol_constants, plugin_constants)
        self.assertLessEqual(moral_repair_protocol_constants, plugin_constants)
        self.assertLessEqual(lifelike_protocol_constants, plugin_constants)
        self.assertLessEqual(personality_drift_protocol_constants, plugin_constants)
        self.assertLessEqual(fallibility_protocol_constants, plugin_constants)
        self.assertLessEqual(group_atmosphere_protocol_constants, plugin_constants)
        self.assertIn("EMOTION_API_VERSION", {node.id for node in ast.walk(public_tree) if isinstance(node, ast.Name)})
        self.assertIn("PUBLIC_API_VERSION", {node.id for node in ast.walk(main_tree) if isinstance(node, ast.Name)})


    def test_main_helper_uses_full_emotion_service_contract(self):
        def passthrough_decorator(*args, **kwargs):
            def decorate(func):
                return func

            return decorate

        class FakeFilter:
            on_llm_request = staticmethod(passthrough_decorator)
            on_llm_response = staticmethod(passthrough_decorator)
            llm_tool = staticmethod(passthrough_decorator)
            command = staticmethod(passthrough_decorator)

        class FakeTextPart:
            def __init__(self, text=""):
                self.text = text

            def mark_as_temp(self):
                return self

        astrbot = types.ModuleType("astrbot")
        api = types.ModuleType("astrbot.api")
        api.AstrBotConfig = dict
        api.logger = SimpleNamespace(debug=lambda *args, **kwargs: None)

        event = types.ModuleType("astrbot.api.event")
        event.AstrMessageEvent = object
        event.filter = FakeFilter

        provider = types.ModuleType("astrbot.api.provider")
        provider.LLMResponse = object
        provider.ProviderRequest = object

        star = types.ModuleType("astrbot.api.star")
        star.Context = object

        class FakeStar:
            def __init__(self, context=None):
                self.context = context

        star.Star = FakeStar
        star.register = passthrough_decorator

        core = types.ModuleType("astrbot.core")
        agent = types.ModuleType("astrbot.core.agent")
        message = types.ModuleType("astrbot.core.agent.message")
        message.TextPart = FakeTextPart

        sys.modules.setdefault("astrbot", astrbot)
        sys.modules.setdefault("astrbot.api", api)
        sys.modules.setdefault("astrbot.api.event", event)
        sys.modules.setdefault("astrbot.api.provider", provider)
        sys.modules.setdefault("astrbot.api.star", star)
        sys.modules.setdefault("astrbot.core", core)
        sys.modules.setdefault("astrbot.core.agent", agent)
        sys.modules.setdefault("astrbot.core.agent.message", message)

        from main import get_emotional_state_plugin
        import main

        class SnapshotOnly:
            emotion_api_version = "1.0"
            emotion_schema_version = "astrbot.emotion_state.v2"
            emotion_memory_schema_version = "astrbot.emotion_memory.v1"
            personality_profile_schema_version = "astrbot.personality_profile.v1"
            psychological_screening_schema_version = "astrbot.psychological_screening.v1"

            async def get_emotion_snapshot(self):
                return {}

        class WrongVersion(FakeEmotionService):
            emotion_schema_version = "astrbot.emotion_state.v1"

        incomplete = FakeContext(
            SimpleNamespace(activated=True, star_cls=SnapshotOnly()),
        )
        wrong_version = FakeContext(
            SimpleNamespace(activated=True, star_cls=WrongVersion()),
        )
        complete = FakeContext(
            SimpleNamespace(activated=True, star_cls=FakeEmotionService()),
        )

        self.assertEqual(main.PLUGIN_NAME, metadata_value("name"))
        self.assertIsNone(get_emotional_state_plugin(incomplete))
        self.assertIsNone(get_emotional_state_plugin(wrong_version))
        self.assertIs(get_emotional_state_plugin(complete), complete.metadata.star_cls)
