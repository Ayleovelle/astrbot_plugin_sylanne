import asyncio
import ast
import contextlib
import importlib
import sys
import tempfile
import time
import types
import unittest
import zipfile
from collections import deque
from pathlib import Path
from types import SimpleNamespace

from public_api import (
    EMOTION_API_VERSION,
    EMOTION_MEMORY_SCHEMA_VERSION,
    EMOTION_SCHEMA_VERSION,
    FALLIBILITY_STATE_SCHEMA_VERSION,
    GROUP_ATMOSPHERE_SCHEMA_VERSION,
    HUMANLIKE_STATE_SCHEMA_VERSION,
    INTEGRATED_SELF_SCHEMA_VERSION,
    LIFELIKE_LEARNING_SCHEMA_VERSION,
    MORAL_REPAIR_STATE_SCHEMA_VERSION,
    PERSONALITY_DRIFT_SCHEMA_VERSION,
    PERSONALITY_PROFILE_SCHEMA_VERSION,
    PSYCHOLOGICAL_RISK_BOOLEAN_FIELDS,
    PSYCHOLOGICAL_SCREENING_SCHEMA_VERSION,
    get_emotion_service,
    get_fallibility_service,
    get_group_atmosphere_service,
    get_humanlike_service,
    get_lifelike_learning_service,
    get_moral_repair_service,
    get_personality_drift_service,
)


ROOT = Path(__file__).resolve().parents[1]


def metadata_value(name: str) -> str:
    for line in (ROOT / "metadata.yaml").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}:"):
            return line.split(":", 1)[1].strip().strip('"')
    raise AssertionError(f"metadata.yaml missing {name}")


def module_tree(name: str) -> ast.Module:
    return ast.parse((ROOT / name).read_text(encoding="utf-8"))


def class_async_methods(tree: ast.Module, class_name: str) -> set[str]:
    return {
        item.name
        for item in class_node(tree, class_name).body
        if isinstance(item, ast.AsyncFunctionDef)
    }


def class_node(tree: ast.Module, class_name: str) -> ast.ClassDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    raise AssertionError(f"{class_name} not found")


def class_constant_names(tree: ast.Module, class_name: str) -> set[str]:
    return {
        target.id
        for item in class_node(tree, class_name).body
        if isinstance(item, ast.Assign)
        for target in item.targets
        if isinstance(target, ast.Name)
    }


def target_is_name(target: ast.expr, name: str) -> bool:
    return isinstance(target, ast.Name) and target.id == name


def assignment_matches_name(node: ast.AST, name: str) -> bool:
    if isinstance(node, ast.Assign):
        return any(target_is_name(target, name) for target in node.targets)
    if isinstance(node, ast.AnnAssign):
        return target_is_name(node.target, name)
    return False


def assignment_node_value(node: ast.AST) -> ast.expr | None:
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        return node.value
    return None


def assignment_value(tree: ast.Module, name: str) -> ast.expr:
    for node in tree.body:
        if assignment_matches_name(node, name):
            value = assignment_node_value(node)
            if value is not None:
                return value
    raise AssertionError(f"{name} assignment not found")


def string_tuple_from_node(value: ast.expr) -> tuple[str, ...]:
    if not isinstance(value, ast.Tuple):
        return ()
    return tuple(
        element.value
        for element in value.elts
        if isinstance(element, ast.Constant) and isinstance(element.value, str)
    )


def assigned_string_tuple(tree: ast.Module, name: str) -> tuple[str, ...]:
    value = assignment_value(tree, name)
    result = string_tuple_from_node(value)
    if result:
        return result
    raise AssertionError(f"{name} tuple assignment not found")


def function_node(tree: ast.Module, function_name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return node
    raise AssertionError(f"{function_name} function not found")


def assigned_tuple_from_node(node: ast.AST, name: str) -> tuple[str, ...] | None:
    if not assignment_matches_name(node, name):
        return None
    value = assignment_node_value(node)
    if value is None:
        return None
    return string_tuple_from_node(value)


def function_required_tuple(tree: ast.Module, function_name: str) -> tuple[str, ...]:
    for node in ast.walk(function_node(tree, function_name)):
        result = assigned_tuple_from_node(node, "required")
        if result:
            return result
    raise AssertionError(f"{function_name} required tuple not found")


def package_module_names(plugin_name: str) -> list[str]:
    return [
        name
        for name in sys.modules
        if name == plugin_name or name.startswith(f"{plugin_name}.")
    ]


def remove_package_modules(plugin_name: str) -> dict[str, types.ModuleType]:
    old_modules = {name: sys.modules[name] for name in package_module_names(plugin_name)}
    for name in old_modules:
        sys.modules.pop(name, None)
    return old_modules


@contextlib.contextmanager
def isolated_package_import_path(plugin_name: str, extract_dir: Path):
    original_path = list(sys.path)
    old_modules = remove_package_modules(plugin_name)
    sys.path = [str(extract_dir)] + [
        path for path in original_path if Path(path or ".").resolve() != ROOT
    ]
    try:
        yield
    finally:
        sys.path = original_path
        for name in package_module_names(plugin_name):
            sys.modules.pop(name, None)
        sys.modules.update(old_modules)


def import_packaged_public_api(plugin_name: str):
    from scripts.package_plugin import build_package

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        zip_path = temp_path / f"{plugin_name}.zip"
        extract_dir = temp_path / "extract"
        build_package(zip_path)
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(extract_dir)
        with isolated_package_import_path(plugin_name, extract_dir):
            return importlib.import_module(f"{plugin_name}.public_api")


class FakeContext:
    def __init__(self, metadata):
        self.metadata = metadata
        self.requested_names = []

    def get_registered_star(self, name):
        self.requested_names.append(name)
        if name == metadata_value("name"):
            return self.metadata
        return None


class FakeEmotionService:
    emotion_api_version = "1.0"
    emotion_schema_version = "astrbot.emotion_state.v2"
    emotion_memory_schema_version = "astrbot.emotion_memory.v1"
    personality_profile_schema_version = "astrbot.personality_profile.v1"
    psychological_screening_schema_version = "astrbot.psychological_screening.v1"
    integrated_self_schema_version = "astrbot.integrated_self_state.v1"
    lifelike_learning_schema_version = "astrbot.lifelike_learning_state.v1"
    personality_drift_schema_version = "astrbot.personality_drift_state.v1"
    fallibility_state_schema_version = "astrbot.fallibility_state.v1"

    async def get_emotion_snapshot(self, *args, **kwargs):
        return {}

    async def get_emotion_state(self, *args, **kwargs):
        return {}

    async def get_emotion_values(self, *args, **kwargs):
        return {}

    async def get_emotion_consequences(self, *args, **kwargs):
        return {}

    async def get_emotion_relationship(self, *args, **kwargs):
        return {}

    async def get_emotion_prompt_fragment(self, *args, **kwargs):
        return ""

    async def build_emotion_memory_payload(self, *args, **kwargs):
        return {}

    async def inject_emotion_context(self, *args, **kwargs):
        return None

    async def observe_emotion_text(self, *args, **kwargs):
        return {}

    async def get_psychological_screening_snapshot(self, *args, **kwargs):
        return {}

    async def get_psychological_screening_values(self, *args, **kwargs):
        return {}

    async def observe_psychological_text(self, *args, **kwargs):
        return {}

    async def simulate_psychological_update(self, *args, **kwargs):
        return {}

    async def reset_psychological_screening_state(self, *args, **kwargs):
        return True

    async def simulate_emotion_update(self, *args, **kwargs):
        return {}

    async def reset_emotion_state(self, *args, **kwargs):
        return True

    async def get_integrated_self_snapshot(self, *args, **kwargs):
        return {}

    async def get_integrated_self_prompt_fragment(self, *args, **kwargs):
        return ""

    async def get_integrated_self_policy_plan(self, *args, **kwargs):
        return {}

    async def build_integrated_self_replay_bundle(self, *args, **kwargs):
        return {}

    async def replay_integrated_self_bundle(self, *args, **kwargs):
        return {}

    async def probe_integrated_self_compatibility(self, *args, **kwargs):
        return {}

    async def export_integrated_self_diagnostics(self, *args, **kwargs):
        return {}

    async def get_lifelike_learning_snapshot(self, *args, **kwargs):
        return {}

    async def get_lifelike_initiative_policy(self, *args, **kwargs):
        return {}

    async def get_proactive_speech_decision(self, *args, **kwargs):
        return {}

    async def request_proactive_speech_dispatch(self, *args, **kwargs):
        return {}

    async def get_realtime_chat_plan(self, *args, **kwargs):
        return {}

    async def request_realtime_chat_dispatch(self, *args, **kwargs):
        return {}

    async def observe_user_message_withdrawal(self, *args, **kwargs):
        return {}

    async def observe_sticker_usage(self, *args, **kwargs):
        return {}

    async def query_sylanne_memory(self, *args, **kwargs):
        return {}

    async def get_lifelike_prompt_fragment(self, *args, **kwargs):
        return ""

    async def observe_lifelike_text(self, *args, **kwargs):
        return {}

    async def simulate_lifelike_update(self, *args, **kwargs):
        return {}

    async def reset_lifelike_learning_state(self, *args, **kwargs):
        return True

    async def get_personality_drift_snapshot(self, *args, **kwargs):
        return {}

    async def get_personality_drift_values(self, *args, **kwargs):
        return {}

    async def get_personality_drift_prompt_fragment(self, *args, **kwargs):
        return ""

    async def observe_personality_drift_event(self, *args, **kwargs):
        return {}

    async def simulate_personality_drift_update(self, *args, **kwargs):
        return {}

    async def reset_personality_drift_state(self, *args, **kwargs):
        return True

    async def get_fallibility_snapshot(self, *args, **kwargs):
        return {}

    async def get_fallibility_values(self, *args, **kwargs):
        return {}

    async def get_fallibility_prompt_fragment(self, *args, **kwargs):
        return ""

    async def observe_fallibility_text(self, *args, **kwargs):
        return {}

    async def simulate_fallibility_update(self, *args, **kwargs):
        return {}

    async def reset_fallibility_state(self, *args, **kwargs):
        return True


class FakeHumanlikeService(FakeEmotionService):
    humanlike_state_schema_version = "astrbot.humanlike_state.v1"

    async def get_humanlike_snapshot(self, *args, **kwargs):
        return {}

    async def get_humanlike_values(self, *args, **kwargs):
        return {}

    async def get_humanlike_prompt_fragment(self, *args, **kwargs):
        return ""

    async def observe_humanlike_text(self, *args, **kwargs):
        return {}

    async def simulate_humanlike_update(self, *args, **kwargs):
        return {}

    async def reset_humanlike_state(self, *args, **kwargs):
        return True


class FakeMoralRepairService(FakeEmotionService):
    moral_repair_state_schema_version = "astrbot.moral_repair_state.v1"

    async def get_moral_repair_snapshot(self, *args, **kwargs):
        return {}

    async def get_moral_repair_values(self, *args, **kwargs):
        return {}

    async def get_moral_repair_prompt_fragment(self, *args, **kwargs):
        return ""

    async def observe_moral_repair_text(self, *args, **kwargs):
        return {}

    async def simulate_moral_repair_update(self, *args, **kwargs):
        return {}

    async def reset_moral_repair_state(self, *args, **kwargs):
        return True


class FakeLifelikeLearningService(FakeEmotionService):
    lifelike_learning_schema_version = "astrbot.lifelike_learning_state.v1"


class FakePersonalityDriftService(FakeEmotionService):
    personality_drift_schema_version = "astrbot.personality_drift_state.v1"


class FakeFallibilityService(FakeEmotionService):
    fallibility_state_schema_version = "astrbot.fallibility_state.v1"


class FakeGroupAtmosphereService(FakeEmotionService):
    group_atmosphere_schema_version = "astrbot.group_atmosphere_state.v1"

    async def get_group_atmosphere_snapshot(self, *args, **kwargs):
        return {}

    async def get_group_atmosphere_values(self, *args, **kwargs):
        return {}

    async def get_group_atmosphere_prompt_fragment(self, *args, **kwargs):
        return ""

    async def observe_group_atmosphere_text(self, *args, **kwargs):
        return {}

    async def simulate_group_atmosphere_update(self, *args, **kwargs):
        return {}

    async def reset_group_atmosphere_state(self, *args, **kwargs):
        return True




# ?????????????????????????????
class PublicApiTests(unittest.TestCase):
    pass


class MemoryPayloadPublicApiTests(unittest.TestCase):
    def _install_astrbot_stubs(self):
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


    def _new_plugin(self, config=None):
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
        plugin._last_state_injection_diagnostics = {}
        plugin._proactive_dispatch_last_sent = {}
        plugin._proactive_dispatch_audit = {}
        plugin._internal_assessor_llm_condition = None
        plugin._internal_assessor_llm_condition_loop = None
        plugin._internal_assessor_llm_inflight = 0
        plugin.context = SimpleNamespace()
        return plugin
