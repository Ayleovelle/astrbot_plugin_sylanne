import asyncio
import ast
import collections
import copy
import json
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def install_astrbot_stubs():
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


def new_plugin(config=None):
    from emotion_engine import EmotionEngine, EmotionParameters
    from fallibility_engine import FallibilityEngine
    from group_atmosphere_engine import GroupAtmosphereEngine
    from humanlike_engine import HumanlikeEngine
    from lifelike_learning_engine import LifelikeLearningEngine
    from main import EmotionalStatePlugin
    from moral_repair_engine import MoralRepairEngine
    from personality_drift_engine import PersonalityDriftEngine
    from psychological_screening import PsychologicalScreeningEngine

    plugin = EmotionalStatePlugin.__new__(EmotionalStatePlugin)
    plugin.config = dict(config or {})
    plugin.base_parameters = EmotionParameters()
    plugin.engine = EmotionEngine(plugin.base_parameters)
    plugin.psychological_engine = PsychologicalScreeningEngine()
    plugin.humanlike_engine = HumanlikeEngine()
    plugin.lifelike_learning_engine = LifelikeLearningEngine()
    plugin.personality_drift_engine = PersonalityDriftEngine()
    plugin.moral_repair_engine = MoralRepairEngine()
    plugin.fallibility_engine = FallibilityEngine()
    plugin.group_atmosphere_engine = GroupAtmosphereEngine()
    plugin._memory_cache = {}
    plugin._psychological_memory_cache = {}
    plugin._humanlike_memory_cache = {}
    plugin._lifelike_learning_memory_cache = {}
    plugin._personality_drift_memory_cache = {}
    plugin._moral_repair_memory_cache = {}
    plugin._fallibility_memory_cache = {}
    plugin._group_atmosphere_memory_cache = {}
    plugin._agent_identity_profile_cache = {}
    plugin._agent_trail_cache = {}
    plugin._agent_turn_sequence = {}
    plugin._engine_cache = {}
    plugin._provider_id_cache = {}
    plugin._last_request_text = {}
    plugin._last_state_injection_diagnostics = {}
    plugin._background_tasks = set()
    plugin._background_post_tasks = {}
    plugin._background_post_queues = {}
    plugin._background_post_active = {}
    plugin._background_post_sequence = {}
    plugin._background_post_latest_enqueued = {}
    plugin._background_post_last_committed = {}
    plugin._background_post_skipped = {}
    plugin._background_post_dead_letters = {}
    plugin._background_post_recovered_sessions = set()
    plugin._background_post_checkpoint_tasks = set()
    plugin._background_post_checkpoint_generation = {}
    plugin._background_post_checkpoint_locks = {}
    plugin._state_injection_snapshot_cache = {}
    plugin._group_atmosphere_injection_snapshot_cache = {}
    plugin._terminating = False
    plugin.context = SimpleNamespace()
    return plugin


def bind_async(instance, name, func):
    setattr(instance, name, types.MethodType(func, instance))


def documented_commands_from_main():
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    commands = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        for decorator in node.decorator_list:
            if not (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "command"
            ):
                continue
            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                commands.add(str(decorator.args[0].value))
            for keyword in decorator.keywords:
                if keyword.arg != "alias" or not isinstance(keyword.value, ast.Set):
                    continue
                for element in keyword.value.elts:
                    if isinstance(element, ast.Constant) and isinstance(element.value, str):
                        commands.add(element.value)
    return commands


def documented_llm_tools_from_main():
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    tools = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        for decorator in node.decorator_list:
            if not (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "llm_tool"
            ):
                continue
            for keyword in decorator.keywords:
                if (
                    keyword.arg == "name"
                    and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                ):
                    tools.add(keyword.value.value)
    return tools


async def collect_async_generator(generator):
    items = []
    async for item in generator:
        items.append(item)
    return items


class FakeEvent:
    def __init__(self, session_id="session-1", message="hello", sender_id=None, sender_name=None):
        self.unified_msg_origin = session_id
        self.message_str = message
        self._sender_id = sender_id
        self._sender_name = sender_name

    def plain_result(self, text):
        return text

    def get_sender_id(self):
        return self._sender_id or ""

    def get_sender_name(self):
        return self._sender_name or ""


class CommandAndToolSmokeTests(unittest.TestCase):
    def setUp(self):
        install_astrbot_stubs()

    def test_readme_documents_registered_commands_and_aliases(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        for command in sorted(documented_commands_from_main()):
            with self.subTest(command=command):
                self.assertIn(f"/{command}", readme)

    def test_readme_documents_registered_llm_tools(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        tools = documented_llm_tools_from_main()

        self.assertEqual(
            tools,
            {
                "get_bot_emotion_state",
                "simulate_bot_emotion_update",
                "get_bot_humanlike_state",
                "get_bot_lifelike_learning_state",
                "get_bot_personality_drift_state",
                "get_bot_moral_repair_state",
                "get_bot_fallibility_state",
                "get_bot_integrated_self_state",
                "get_bot_group_atmosphere_state",
                "query_agent_state",
            },
        )
        for tool in sorted(tools):
            with self.subTest(tool=tool):
                self.assertIn(f"| `{tool}` |", readme)

    def test_emotion_reset_command_denies_delete_when_backdoor_disabled(self):
        plugin = new_plugin({"allow_emotion_reset_backdoor": False})
        deleted = []

        async def fake_delete_state(self, session_key):
            deleted.append(session_key)

        bind_async(plugin, "_delete_state", fake_delete_state)

        outputs = asyncio.run(collect_async_generator(plugin.emotion_reset(FakeEvent())))

        self.assertEqual(deleted, [])
        self.assertEqual(len(outputs), 1)
        self.assertIn("\u5173\u95ed", outputs[0])

    def test_humanlike_reset_command_uses_humanlike_backdoor(self):
        allowed = new_plugin(
            {
                "allow_emotion_reset_backdoor": False,
                "allow_humanlike_reset_backdoor": True,
            },
        )
        deleted = []

        async def fake_delete_humanlike_state(self, session_key):
            deleted.append(session_key)

        bind_async(allowed, "_delete_humanlike_state", fake_delete_humanlike_state)

        outputs = asyncio.run(
            collect_async_generator(allowed.humanlike_reset(FakeEvent("s-human"))),
        )

        self.assertEqual(deleted, ["s-human"])
        self.assertEqual(len(outputs), 1)
        self.assertIn("\u5df2\u91cd\u7f6e", outputs[0])

    def test_humanlike_reset_command_denies_when_humanlike_backdoor_disabled(self):
        denied = new_plugin(
            {
                "allow_emotion_reset_backdoor": True,
                "allow_humanlike_reset_backdoor": False,
            },
        )
        deleted = []

        async def fake_delete_humanlike_state(self, session_key):
            deleted.append(session_key)

        bind_async(denied, "_delete_humanlike_state", fake_delete_humanlike_state)

        outputs = asyncio.run(
            collect_async_generator(denied.humanlike_reset(FakeEvent("s-human"))),
        )

        self.assertEqual(deleted, [])
        self.assertEqual(len(outputs), 1)
        self.assertIn("\u5173\u95ed", outputs[0])

    def test_moral_repair_reset_command_uses_independent_backdoor(self):
        allowed = new_plugin(
            {
                "allow_emotion_reset_backdoor": False,
                "allow_moral_repair_reset_backdoor": True,
            },
        )
        deleted = []

        async def fake_delete_moral_repair_state(self, session_key):
            deleted.append(session_key)

        bind_async(allowed, "_delete_moral_repair_state", fake_delete_moral_repair_state)

        outputs = asyncio.run(
            collect_async_generator(allowed.moral_repair_reset(FakeEvent("s-moral"))),
        )

        self.assertEqual(deleted, ["s-moral"])
        self.assertEqual(len(outputs), 1)
        self.assertIn("\u5df2\u91cd\u7f6e", outputs[0])

    def test_moral_repair_reset_command_denies_when_backdoor_disabled(self):
        denied = new_plugin({"allow_moral_repair_reset_backdoor": False})
        deleted = []

        async def fake_delete_moral_repair_state(self, session_key):
            deleted.append(session_key)

        bind_async(denied, "_delete_moral_repair_state", fake_delete_moral_repair_state)

        outputs = asyncio.run(
            collect_async_generator(denied.moral_repair_reset(FakeEvent("s-moral"))),
        )

        self.assertEqual(deleted, [])
        self.assertEqual(len(outputs), 1)
        self.assertIn("\u5173\u95ed", outputs[0])

    def test_fallibility_reset_command_uses_independent_backdoor(self):
        allowed = new_plugin(
            {
                "allow_emotion_reset_backdoor": False,
                "allow_fallibility_reset_backdoor": True,
            },
        )
        deleted = []

        async def fake_delete_fallibility_state(self, session_key):
            deleted.append(session_key)

        bind_async(allowed, "_delete_fallibility_state", fake_delete_fallibility_state)

        outputs = asyncio.run(
            collect_async_generator(allowed.fallibility_reset(FakeEvent("s-fallibility"))),
        )

        self.assertEqual(deleted, ["s-fallibility"])
        self.assertEqual(len(outputs), 1)
        self.assertIn("\u5df2\u91cd\u7f6e", outputs[0])

    def test_fallibility_reset_command_denies_when_backdoor_disabled(self):
        denied = new_plugin({"allow_fallibility_reset_backdoor": False})
        deleted = []

        async def fake_delete_fallibility_state(self, session_key):
            deleted.append(session_key)

        bind_async(denied, "_delete_fallibility_state", fake_delete_fallibility_state)

        outputs = asyncio.run(
            collect_async_generator(denied.fallibility_reset(FakeEvent("s-fallibility"))),
        )

        self.assertEqual(deleted, [])
        self.assertEqual(len(outputs), 1)
        self.assertIn("\u5173\u95ed", outputs[0])

    def test_disabled_psych_state_command_does_not_load_state(self):
        plugin = new_plugin()

        async def fake_load_psychological_state(self, session_key):
            raise AssertionError("disabled command must not load psychological state")

        bind_async(plugin, "_load_psychological_state", fake_load_psychological_state)

        outputs = asyncio.run(
            collect_async_generator(
                plugin.psychological_screening_status(FakeEvent()),
            ),
        )

        self.assertEqual(len(outputs), 1)
        self.assertIn("\u672a\u542f\u7528", outputs[0])

    def test_disabled_humanlike_state_command_does_not_load_state(self):
        plugin = new_plugin()

        async def fake_load_humanlike_state(self, session_key):
            raise AssertionError("disabled command must not load humanlike state")

        bind_async(plugin, "_load_humanlike_state", fake_load_humanlike_state)

        outputs = asyncio.run(
            collect_async_generator(plugin.humanlike_status(FakeEvent())),
        )

        self.assertEqual(len(outputs), 1)
        self.assertIn("\u672a\u542f\u7528", outputs[0])

    def test_disabled_moral_repair_state_command_does_not_load_state(self):
        plugin = new_plugin()

        async def fake_load_moral_repair_state(self, session_key):
            raise AssertionError("disabled command must not load moral repair state")

        bind_async(plugin, "_load_moral_repair_state", fake_load_moral_repair_state)

        outputs = asyncio.run(
            collect_async_generator(plugin.moral_repair_status(FakeEvent())),
        )

        self.assertEqual(len(outputs), 1)
        self.assertIn("\u672a\u542f\u7528", outputs[0])

    def test_disabled_fallibility_state_command_does_not_load_state(self):
        plugin = new_plugin()

        async def fake_load_fallibility_state(self, session_key):
            raise AssertionError("disabled fallibility command must not load state")

        bind_async(plugin, "_load_fallibility_state", fake_load_fallibility_state)

        outputs = asyncio.run(
            collect_async_generator(plugin.fallibility_status(FakeEvent())),
        )

        self.assertEqual(len(outputs), 1)
        self.assertIn("\u672a\u542f\u7528", outputs[0])

    def test_shadow_diagnostics_command_default_disabled_payload_is_json(self):
        plugin = new_plugin()

        async def fake_moral_repair_snapshot(self, *args, **kwargs):
            raise AssertionError("disabled shadow diagnostics must not load moral state")

        async def fake_fallibility_snapshot(self, *args, **kwargs):
            raise AssertionError("disabled shadow diagnostics must not load fallibility state")

        bind_async(plugin, "get_moral_repair_snapshot", fake_moral_repair_snapshot)
        bind_async(plugin, "get_fallibility_snapshot", fake_fallibility_snapshot)

        payload = json.loads(
            asyncio.run(
                collect_async_generator(plugin.shadow_diagnostics_status(FakeEvent())),
            )[0],
        )

        self.assertFalse(payload["enabled"])
        self.assertEqual(payload["kind"], "shadow_diagnostics")
        self.assertEqual(payload["reason"], "enable_shadow_diagnostics is false")
        self.assertFalse(payload["executable_strategy_enabled"])

    def test_shadow_diagnostics_command_enabled_returns_non_executable_json(self):
        plugin = new_plugin({"enable_shadow_diagnostics": True})

        async def fake_moral_repair_snapshot(self, *args, **kwargs):
            return {
                "values": {
                    "shadow_deception_impulse": 0.2,
                    "shadow_manipulation_impulse": 0.1,
                    "shadow_evasion_impulse": 0.3,
                    "guilt": 0.6,
                    "repair_motivation": 0.7,
                    "compensation_readiness": 0.5,
                    "trust_repair": 0.4,
                },
                "risk": {
                    "shadow_impulses": {
                        "deception": 0.2,
                        "manipulation": 0.1,
                        "evasion": 0.3,
                    },
                },
            }

        async def fake_fallibility_snapshot(self, *args, **kwargs):
            return {
                "values": {
                    "shadow_deception_impulse": 0.15,
                    "shadow_manipulation_impulse": 0.05,
                    "shadow_evasion_impulse": 0.25,
                    "clarification_need": 0.4,
                    "correction_readiness": 0.8,
                    "repair_pressure": 0.7,
                    "truthfulness_guard": 0.9,
                },
                "fallibility": {
                    "non_executable_impulses": {
                        "deception": 0.15,
                        "manipulation": 0.05,
                        "evasion": 0.25,
                    },
                },
            }

        async def fake_integrated_snapshot(self, *args, **kwargs):
            return {
                "response_posture": "repair_first",
                "state_index": {"repair_pressure": 0.7},
                "risk": {"shadow_risk_impulse": 0.3},
                "policy_plan": {"must_preserve_signals": ["truthfulness_guard"]},
                "non_executable_impulses": {"shadow_risk_impulse": 0.3},
            }

        bind_async(plugin, "get_moral_repair_snapshot", fake_moral_repair_snapshot)
        bind_async(plugin, "get_fallibility_snapshot", fake_fallibility_snapshot)
        bind_async(plugin, "get_integrated_self_snapshot", fake_integrated_snapshot)

        payload = json.loads(
            asyncio.run(
                collect_async_generator(plugin.shadow_diagnostics_status(FakeEvent())),
            )[0],
        )

        self.assertTrue(payload["enabled"])
        self.assertTrue(payload["diagnostic"])
        self.assertFalse(payload["executable_strategy_enabled"])
        self.assertFalse(payload["action_blocking_enabled"])
        self.assertEqual(payload["strategy_policy"], "observe")
        self.assertEqual(payload["kind"], "shadow_diagnostics")
        self.assertEqual(payload["consequences"]["response_posture"], "repair_first")
        self.assertEqual(payload["not_allowed"], [])
        self.assertNotIn("generate_deception_strategy", payload["allowed_uses"])

    def test_shadow_diagnostics_can_restore_action_blocking_not_allowed(self):
        plugin = new_plugin(
            {
                "enable_shadow_diagnostics": True,
                "block_deception_manipulation_evasion_actions": True,
            },
        )

        async def fake_moral_repair_snapshot(self, *args, **kwargs):
            return {
                "values": {"shadow_deception_impulse": 0.2},
                "risk": {"shadow_impulses": {"deception": 0.2}},
            }

        async def fake_fallibility_snapshot(self, *args, **kwargs):
            return {
                "values": {"shadow_evasion_impulse": 0.25},
                "fallibility": {"non_executable_impulses": {"evasion": 0.25}},
            }

        async def fake_integrated_snapshot(self, *args, **kwargs):
            return {
                "response_posture": "repair_first",
                "state_index": {"repair_pressure": 0.7},
                "risk": {"shadow_risk_impulse": 0.3},
                "policy_plan": {"must_preserve_signals": ["truthfulness_guard"]},
                "non_executable_impulses": {"shadow_risk_impulse": 0.3},
            }

        bind_async(plugin, "get_moral_repair_snapshot", fake_moral_repair_snapshot)
        bind_async(plugin, "get_fallibility_snapshot", fake_fallibility_snapshot)
        bind_async(plugin, "get_integrated_self_snapshot", fake_integrated_snapshot)

        payload = json.loads(
            asyncio.run(
                collect_async_generator(plugin.shadow_diagnostics_status(FakeEvent())),
            )[0],
        )

        self.assertTrue(payload["action_blocking_enabled"])
        self.assertEqual(payload["strategy_policy"], "block")
        self.assertIn("generate_deception_strategy", payload["not_allowed"])
        self.assertIn("execute_shadow_impulses", payload["not_allowed"])

    def test_disabled_lifelike_state_command_does_not_load_state(self):
        plugin = new_plugin()

        async def fake_load_lifelike_state(self, session_key):
            raise AssertionError("disabled lifelike command must not load state")

        bind_async(plugin, "_load_lifelike_learning_state", fake_load_lifelike_state)

        outputs = asyncio.run(
            collect_async_generator(plugin.lifelike_learning_status(FakeEvent())),
        )

        self.assertEqual(len(outputs), 1)
        self.assertIn("\u672a\u542f\u7528", outputs[0])

    def test_lifelike_reset_command_uses_independent_backdoor(self):
        allowed = new_plugin(
            {
                "allow_emotion_reset_backdoor": False,
                "allow_lifelike_learning_reset_backdoor": True,
            },
        )
        deleted = []

        async def fake_delete_lifelike_state(self, session_key):
            deleted.append(session_key)

        bind_async(allowed, "_delete_lifelike_learning_state", fake_delete_lifelike_state)

        outputs = asyncio.run(
            collect_async_generator(allowed.lifelike_learning_reset(FakeEvent("s-life"))),
        )

        self.assertEqual(deleted, ["s-life"])
        self.assertEqual(len(outputs), 1)
        self.assertIn("\u5df2\u91cd\u7f6e", outputs[0])

    def test_personality_drift_reset_command_uses_independent_backdoor(self):
        allowed = new_plugin(
            {
                "allow_emotion_reset_backdoor": False,
                "allow_personality_drift_reset_backdoor": True,
            },
        )
        deleted = []

        async def fake_delete_personality_drift_state(self, session_key):
            deleted.append(session_key)

        bind_async(
            allowed,
            "_delete_personality_drift_state",
            fake_delete_personality_drift_state,
        )

        outputs = asyncio.run(
            collect_async_generator(
                allowed.personality_drift_reset(FakeEvent("s-drift")),
            ),
        )

        self.assertEqual(deleted, ["s-drift"])
        self.assertEqual(len(outputs), 1)
        self.assertIn("\u5df2\u91cd\u7f6e", outputs[0])

    def test_disabled_personality_drift_state_command_does_not_load_state(self):
        plugin = new_plugin()

        async def fake_load_personality_drift_state(self, session_key, profile=None):
            raise AssertionError("disabled personality drift command must not load state")

        bind_async(
            plugin,
            "_load_personality_drift_state",
            fake_load_personality_drift_state,
        )

        outputs = asyncio.run(
            collect_async_generator(plugin.personality_drift_status(FakeEvent())),
        )

        self.assertEqual(len(outputs), 1)
        self.assertIn("\u672a\u542f\u7528", outputs[0])

    def test_get_bot_emotion_state_tool_summary_trims_llm_exposure(self):
        plugin = new_plugin()
        template = {
            "kind": "emotion_state",
            "prompt_fragment": "full prompt fragment",
            "emotion": {"label": "tense"},
            "consequences": {
                "notes": ["note-1", "note-2", "note-3"],
            },
        }

        async def fake_snapshot(self, *args, **kwargs):
            payload = copy.deepcopy(template)
            if kwargs.get("include_prompt_fragment"):
                payload["prompt_fragment"] = "full prompt fragment"
            return payload

        bind_async(plugin, "get_emotion_snapshot", fake_snapshot)

        summary_json = asyncio.run(
            collect_async_generator(
                plugin.get_bot_emotion_state_tool(FakeEvent(), detail="summary"),
            ),
        )[0]
        full_json = asyncio.run(
            collect_async_generator(
                plugin.get_bot_emotion_state_tool(FakeEvent(), detail="full"),
            ),
        )[0]
        summary = json.loads(summary_json)
        full = json.loads(full_json)

        self.assertNotIn("prompt_fragment", summary)
        self.assertEqual(summary["consequences"]["notes"], ["note-1", "note-2"])
        self.assertEqual(summary["track"]["kind"], "conversation")
        self.assertEqual(full["prompt_fragment"], "full prompt fragment")
        self.assertEqual(full["consequences"]["notes"], ["note-1", "note-2", "note-3"])
        self.assertEqual(full["track"]["kind"], "conversation")

    def test_get_bot_emotion_state_tool_can_query_current_speaker_track(self):
        plugin = new_plugin()
        calls = []

        async def fake_snapshot(self, *args, **kwargs):
            calls.append(kwargs)
            return {
                "kind": "emotion_state",
                "session_key": kwargs.get("session_key"),
                "prompt_fragment": "full prompt fragment",
                "emotion": {"label": "careful"},
                "consequences": {"notes": ["speaker-note"]},
            }

        bind_async(plugin, "get_emotion_snapshot", fake_snapshot)

        speaker_json = asyncio.run(
            collect_async_generator(
                plugin.get_bot_emotion_state_tool(
                    FakeEvent("group-1", sender_id="user-a", sender_name="Alice"),
                    detail="full",
                    track="speaker",
                ),
            ),
        )[0]
        speaker = json.loads(speaker_json)

        self.assertEqual(calls[0]["session_key"], "group-1::speaker:user-a")
        self.assertEqual(calls[0]["prompt_fragment_detail"], "full")
        self.assertEqual(speaker["session_key"], "group-1::speaker:user-a")
        self.assertEqual(speaker["track"]["kind"], "speaker")
        self.assertEqual(speaker["track"]["speaker_id"], "user-a")
        self.assertEqual(speaker["track"]["speaker_name"], "Alice")

    def test_get_bot_humanlike_state_tool_uses_layered_exposure(self):
        plugin = new_plugin()
        calls = []

        async def fake_snapshot(self, *args, **kwargs):
            calls.append(
                (
                    kwargs.get("exposure"),
                    kwargs.get("include_prompt_fragment"),
                ),
            )
            return {
                "kind": "humanlike_state",
                "enabled": True,
                "exposure": kwargs.get("exposure"),
                "prompt_fragment": "fragment"
                if kwargs.get("include_prompt_fragment")
                else "",
            }

        bind_async(plugin, "get_humanlike_snapshot", fake_snapshot)

        summary = json.loads(
            asyncio.run(
                collect_async_generator(
                    plugin.get_bot_humanlike_state_tool(
                        FakeEvent(),
                        detail="summary",
                    ),
                ),
            )[0],
        )
        full = json.loads(
            asyncio.run(
                collect_async_generator(
                    plugin.get_bot_humanlike_state_tool(FakeEvent(), detail="full"),
                ),
            )[0],
        )

        self.assertEqual(calls, [("plugin_safe", False), ("internal", True)])
        self.assertEqual(summary["exposure"], "plugin_safe")
        self.assertEqual(full["exposure"], "internal")
        self.assertEqual(full["prompt_fragment"], "fragment")

    def test_get_bot_humanlike_state_tool_default_disabled_payload_is_json(self):
        plugin = new_plugin()

        payload = json.loads(
            asyncio.run(
                collect_async_generator(
                    plugin.get_bot_humanlike_state_tool(FakeEvent(), detail="summary"),
                ),
            )[0],
        )

        self.assertFalse(payload["enabled"])
        self.assertEqual(payload["reason"], "enable_humanlike_state is false")
        self.assertEqual(payload["exposure"], "plugin_safe")

    def test_get_bot_moral_repair_state_tool_default_disabled_payload_is_json(self):
        plugin = new_plugin()

        payload = json.loads(
            asyncio.run(
                collect_async_generator(
                    plugin.get_bot_moral_repair_state_tool(
                        FakeEvent(),
                        detail="summary",
                    ),
                ),
            )[0],
        )

        self.assertFalse(payload["enabled"])
        self.assertEqual(payload["reason"], "enable_moral_repair_state is false")
        self.assertEqual(payload["exposure"], "plugin_safe")

    def test_get_bot_fallibility_state_tool_default_disabled_payload_is_json(self):
        plugin = new_plugin()

        payload = json.loads(
            asyncio.run(
                collect_async_generator(
                    plugin.get_bot_fallibility_state_tool(
                        FakeEvent(),
                        detail="summary",
                    ),
                ),
            )[0],
        )

        self.assertFalse(payload["enabled"])
        self.assertEqual(payload["reason"], "enable_fallibility_state is false")
        self.assertEqual(payload["exposure"], "plugin_safe")

    def test_get_bot_personality_drift_state_tool_default_disabled_payload_is_json(self):
        plugin = new_plugin()

        payload = json.loads(
            asyncio.run(
                collect_async_generator(
                    plugin.get_bot_personality_drift_state_tool(
                        FakeEvent(),
                        detail="summary",
                    ),
                ),
            )[0],
        )

        self.assertFalse(payload["enabled"])
        self.assertEqual(payload["reason"], "enable_personality_drift is false")
        self.assertEqual(payload["exposure"], "plugin_safe")

    def test_get_bot_group_atmosphere_state_tool_uses_layered_exposure(self):
        plugin = new_plugin()
        calls = []

        async def fake_snapshot(self, *args, **kwargs):
            calls.append(
                (
                    kwargs.get("exposure"),
                    kwargs.get("include_prompt_fragment"),
                ),
            )
            return {
                "kind": "group_atmosphere_state",
                "enabled": True,
                "exposure": kwargs.get("exposure"),
                "prompt_fragment": "room fragment"
                if kwargs.get("include_prompt_fragment")
                else "",
            }

        bind_async(plugin, "get_group_atmosphere_snapshot", fake_snapshot)

        summary = json.loads(
            asyncio.run(
                collect_async_generator(
                    plugin.get_bot_group_atmosphere_state_tool(
                        FakeEvent(),
                        detail="summary",
                    ),
                ),
            )[0],
        )
        full = json.loads(
            asyncio.run(
                collect_async_generator(
                    plugin.get_bot_group_atmosphere_state_tool(
                        FakeEvent(),
                        detail="full",
                    ),
                ),
            )[0],
        )

        self.assertEqual(calls, [("plugin_safe", False), ("internal", True)])
        self.assertEqual(summary["exposure"], "plugin_safe")
        self.assertEqual(full["exposure"], "internal")
        self.assertEqual(full["prompt_fragment"], "room fragment")

    def test_query_agent_state_tool_returns_unified_payload(self):
        plugin = new_plugin()
        calls = []

        async def fake_query(self, *args, **kwargs):
            calls.append(kwargs)
            return {
                "kind": "agent_state_query",
                "state": kwargs.get("state"),
                "detail": kwargs.get("detail"),
                "track": {"kind": kwargs.get("track")},
                "runtime": {"enabled": kwargs.get("include_runtime")},
                "snapshots": {},
            }

        bind_async(plugin, "query_agent_state", fake_query)

        payload = json.loads(
            asyncio.run(
                collect_async_generator(
                    plugin.query_agent_state_tool(
                        FakeEvent("group-query"),
                        state="group_atmosphere",
                        detail="full",
                        track="speaker",
                        include_runtime=True,
                    ),
                ),
            )[0],
        )

        self.assertEqual(calls[0]["state"], "group_atmosphere")
        self.assertEqual(calls[0]["detail"], "full")
        self.assertEqual(calls[0]["track"], "speaker")
        self.assertTrue(calls[0]["include_runtime"])
        self.assertEqual(payload["state"], "group_atmosphere")
        self.assertEqual(payload["runtime"], {"enabled": True})

    def test_llm_tool_json_result_is_bounded_and_valid_json(self):
        plugin = new_plugin({"llm_tool_response_max_chars": 420})

        async def fake_query(self, *args, **kwargs):
            return {
                "schema_version": "astrbot.agent_state_query.v1",
                "kind": "agent_state_query",
                "state": kwargs.get("state"),
                "detail": kwargs.get("detail"),
                "session_key": "s-tool-budget",
                "snapshots": {
                    "emotion": {
                        "kind": "emotion_state",
                        "session_key": "s-tool-budget",
                        "emotion": {"label": "focused", "confidence": 0.9},
                        "prompt_fragment": "very-long-fragment-" + "x" * 5000,
                        "trajectory": ["raw"] * 200,
                    },
                },
            }

        bind_async(plugin, "query_agent_state", fake_query)

        raw = asyncio.run(
            collect_async_generator(
                plugin.query_agent_state_tool(
                    FakeEvent("s-tool-budget"),
                    state="all",
                    detail="full",
                ),
            ),
        )[0]
        payload = json.loads(raw)

        self.assertLessEqual(len(raw), 420)
        self.assertTrue(payload["truncated"])
        self.assertTrue(payload["degraded"])
        self.assertNotIn("very-long-fragment", raw)
        self.assertIn("original_chars", payload)

    def test_query_agent_state_summary_trims_emotion_prompt_fragment(self):
        plugin = new_plugin()
        template = {
            "kind": "emotion_state",
            "prompt_fragment": "full prompt fragment",
            "emotion": {"label": "focused"},
            "consequences": {
                "notes": ["note-1", "note-2", "note-3"],
            },
        }

        async def fake_snapshot(self, *args, **kwargs):
            payload = copy.deepcopy(template)
            if kwargs.get("include_prompt_fragment"):
                payload["prompt_fragment"] = "full prompt fragment"
            return payload

        bind_async(plugin, "get_emotion_snapshot", fake_snapshot)

        payload = asyncio.run(
            plugin.query_agent_state(
                FakeEvent("group-query", sender_id="user-a", sender_name="Alice"),
                state="emotion",
                detail="summary",
                track="speaker",
            ),
        )

        emotion = payload["snapshots"]["emotion"]
        self.assertNotIn("prompt_fragment", emotion)
        self.assertEqual(emotion["track"]["kind"], "speaker")
        self.assertEqual(emotion["track"]["speaker_track_id"], "group-query::speaker:user-a")
        self.assertEqual(emotion["consequences"]["notes"], ["note-1", "note-2"])

    def test_query_agent_state_accepts_integrated_self_alias(self):
        plugin = new_plugin()
        calls = []

        async def fake_integrated_snapshot(self, *args, **kwargs):
            calls.append(kwargs)
            return {"kind": "integrated_self_state", "enabled": True}

        bind_async(plugin, "get_integrated_self_snapshot", fake_integrated_snapshot)

        payload = asyncio.run(
            plugin.query_agent_state(
                FakeEvent("group-query"),
                state="integrated_self",
                detail="full",
            ),
        )

        self.assertEqual(payload["state"], "integrated")
        self.assertIn("integrated", payload["snapshots"])
        self.assertEqual(payload["snapshots"]["integrated"]["kind"], "integrated_self_state")
        self.assertTrue(calls[0]["include_raw_snapshots"])

    def test_query_agent_state_runtime_diagnostics_omits_raw_message_text(self):
        plugin = new_plugin()
        payload = asyncio.run(
            plugin.query_agent_state(
                FakeEvent(
                    "group-runtime",
                    message="secret raw text must not appear",
                    sender_id="user-a",
                    sender_name="Alice",
                ),
                state="runtime",
                include_runtime=True,
            ),
        )

        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["state"], "runtime")
        self.assertIn("runtime", payload)
        self.assertNotIn("secret raw text must not appear", serialized)

    def test_runtime_diagnostics_reports_background_lag_without_raw_content(self):
        plugin = new_plugin(
            {
                "background_post_assessment": True,
                "background_post_queue_limit": 2,
                "background_post_max_workers": 3,
                "background_post_diagnostics_warn_lag_count": 3,
                "background_post_diagnostics_warn_lag_seconds": 999999999.0,
            },
        )
        from main import _BackgroundPostJob

        event = FakeEvent(
            "s-diag",
            message="secret text",
            sender_id="u1",
            sender_name="Alice",
        )
        identity = plugin._agent_identity(event)
        plugin._background_post_queues["s-diag"] = collections.deque(
            [
                _BackgroundPostJob(event, identity, "reply-2", "ctx-2", 2, 100.0),
                _BackgroundPostJob(event, identity, "reply-3", "ctx-3", 3, 110.0),
            ],
        )
        plugin._background_post_active["s-diag"] = {
            1: _BackgroundPostJob(event, identity, "reply-1", "ctx-1", 1, 90.0),
        }
        plugin._background_post_tasks["s-diag"] = SimpleNamespace(done=lambda: False)
        plugin._background_post_sequence["s-diag"] = 3
        plugin._background_post_latest_enqueued["s-diag"] = 3
        plugin._background_post_last_committed["s-diag"] = 0
        plugin._background_post_skipped["s-diag"] = {0}

        payload = asyncio.run(
            plugin.get_agent_runtime_diagnostics(event, include_sessions=True),
        )

        serialized = json.dumps(payload, ensure_ascii=False)
        bg = payload["background_post_assessment"]
        self.assertTrue(bg["enabled"])
        self.assertTrue(bg["checkpoint_enabled"])
        self.assertEqual(bg["queue_limit"], 2)
        self.assertEqual(bg["max_workers"], 3)
        self.assertTrue(bg["active_task"])
        self.assertEqual(bg["queued"], 2)
        self.assertEqual(bg["queue_depth"], 2)
        self.assertEqual(bg["active_workers"], 1)
        self.assertEqual(bg["lag_count"], 3)
        self.assertEqual(bg["latest_enqueued"], 3)
        self.assertEqual(bg["last_committed"], 0)
        self.assertEqual(bg["state_lag_count"], 3)
        self.assertEqual(bg["skipped_count"], 1)
        self.assertIn("s-diag", payload["sessions"])
        self.assertEqual(bg["warning_level"], "warn")
        self.assertIn("lag_count_high", bg["warnings"])
        self.assertEqual(bg["retrying_count"], 0)
        self.assertEqual(bg["dead_letter_count"], 0)
        self.assertEqual(bg["expired_lease_count"], 0)
        self.assertNotIn("secret text", serialized)

    def test_runtime_diagnostics_reports_retry_dead_letter_and_expired_lease(self):
        plugin = new_plugin(
            {
                "background_post_assessment": True,
                "background_post_diagnostics_warn_lag_count": 1,
            },
        )
        from main import _BackgroundPostJob

        event = FakeEvent("s-diag-warn", message="secret text", sender_id="u1")
        identity = plugin._agent_identity(event)
        retrying = _BackgroundPostJob(event, identity, "secret retry", "secret ctx", 1, 100.0)
        retrying.attempts = 1
        retrying.next_retry_at = 9999999999.0
        retrying.last_error_type = "RuntimeError"
        retrying.last_failed_at = 101.0
        expired = _BackgroundPostJob(event, identity, "secret active", "secret ctx", 2, 100.0)
        expired.leased_at = 100.0
        expired.lease_until = 100.1
        dead = _BackgroundPostJob(event, identity, "secret dead", "secret ctx", 3, 100.0)
        dead.attempts = 3
        dead.last_error_type = "TimeoutError"
        dead.last_failed_at = 120.0
        dead.dead_lettered_at = 121.0
        plugin._background_post_queues["s-diag-warn"] = collections.deque([retrying])
        plugin._background_post_active["s-diag-warn"] = {2: expired}
        plugin._background_post_dead_letters["s-diag-warn"] = collections.deque([dead])
        plugin._background_post_latest_enqueued["s-diag-warn"] = 3

        payload = asyncio.run(plugin.get_agent_runtime_diagnostics("s-diag-warn"))
        bg = payload["background_post_assessment"]
        serialized = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(bg["retrying_count"], 1)
        self.assertEqual(bg["dead_letter_count"], 1)
        self.assertEqual(bg["expired_lease_count"], 1)
        self.assertEqual(bg["warning_level"], "error")
        self.assertIn("retrying", bg["warnings"])
        self.assertIn("dead_letter", bg["warnings"])
        self.assertIn("expired_lease", bg["warnings"])
        self.assertEqual(bg["last_error_type"], "TimeoutError")
        self.assertEqual(bg["dead_letters"][0]["sequence"], 3)
        self.assertNotIn("secret retry", serialized)
        self.assertNotIn("secret active", serialized)
        self.assertNotIn("secret dead", serialized)
        self.assertNotIn("secret ctx", serialized)

    def test_runtime_diagnostics_with_event_does_not_write_identity_cache(self):
        plugin = new_plugin()
        event = FakeEvent(
            "s-readonly-runtime",
            message="hello",
            sender_id="user-a",
            sender_name="Alice",
        )

        payload = asyncio.run(plugin.get_agent_runtime_diagnostics(event))

        self.assertEqual(payload["identity"]["speaker_track_id"], "s-readonly-runtime::speaker:user-a")
        self.assertEqual(plugin._agent_identity_profile_cache, {})

    def test_llm_tool_simulate_bot_emotion_update_is_read_only(self):
        from emotion_engine import EmotionState

        plugin = new_plugin({"use_llm_assessor": False})

        async def fake_load_state(self, session_key, persona_profile=None, **kwargs):
            state = EmotionState.initial(persona_profile)
            state.updated_at = 1000.0
            return state

        async def fake_save_state(self, session_key, state):
            raise AssertionError("simulate tool must not save state")

        bind_async(plugin, "_load_state", fake_load_state)
        bind_async(plugin, "_save_state", fake_save_state)

        payload = json.loads(
            asyncio.run(
                collect_async_generator(
                    plugin.simulate_bot_emotion_update_tool(
                        FakeEvent("s-tool"),
                        text="This is only a simulated candidate reply.",
                        role="assistant",
                    ),
                ),
            )[0],
        )

        self.assertEqual(payload["session_key"], "s-tool")
        self.assertFalse(payload["observation"]["committed"])
        self.assertEqual(payload["observation"]["phase"], "llm_tool_simulation")
        self.assertEqual(payload["observation"]["source"], "llm_tool")
        self.assertEqual(payload["observation"]["role"], "assistant")


if __name__ == "__main__":
    unittest.main()
