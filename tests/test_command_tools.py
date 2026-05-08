import asyncio
import ast
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
    plugin._memory_cache = {}
    plugin._psychological_memory_cache = {}
    plugin._humanlike_memory_cache = {}
    plugin._lifelike_learning_memory_cache = {}
    plugin._personality_drift_memory_cache = {}
    plugin._moral_repair_memory_cache = {}
    plugin._fallibility_memory_cache = {}
    plugin._last_request_text = {}
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
    def __init__(self, session_id="session-1", message="hello"):
        self.unified_msg_origin = session_id
        self.message_str = message

    def plain_result(self, text):
        return text


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
        self.assertEqual(payload["kind"], "shadow_diagnostics")
        self.assertEqual(payload["consequences"]["response_posture"], "repair_first")
        self.assertIn("generate_deception_strategy", payload["not_allowed"])
        self.assertIn("execute_shadow_impulses", payload["not_allowed"])
        self.assertNotIn("generate_deception_strategy", payload["allowed_uses"])

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
        self.assertEqual(full["prompt_fragment"], "full prompt fragment")
        self.assertEqual(full["consequences"]["notes"], ["note-1", "note-2", "note-3"])

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
