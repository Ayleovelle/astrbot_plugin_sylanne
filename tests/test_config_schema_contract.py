import ast
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def runtime_config_keys():
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    keys = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"_cfg", "_cfg_bool", "_cfg_float", "_cfg_int"}:
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            keys.add(first.value)
    return keys


def runtime_config_calls():
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    calls = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"_cfg", "_cfg_bool", "_cfg_float", "_cfg_int"}:
            continue
        if len(node.args) < 2:
            continue
        key_node = node.args[0]
        default_node = node.args[1]
        if not (
            isinstance(key_node, ast.Constant)
            and isinstance(key_node.value, str)
            and isinstance(default_node, ast.Constant)
        ):
            continue
        calls.setdefault(key_node.value, set()).add(
            (node.func.attr, default_node.value),
        )
    return calls


def schema():
    return json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))


def readme_config_defaults():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    defaults = {}
    pattern = re.compile(
        r"^\|\s*`(?P<key>[^`]+)`\s*\|"
        r"(?:\s*[^|`]+\s*\|)?"
        r"\s*`(?P<default>[^`]+)`\s*\|",
    )
    for line in readme.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        defaults.setdefault(match.group("key"), set()).add(match.group("default"))
    return defaults


def normalize_default(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if value == "":
        return '""'
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)
    return str(value)


def defaults_match(schema_value, readme_value):
    if normalize_default(schema_value) == readme_value:
        return True
    if isinstance(schema_value, (int, float)) and not isinstance(schema_value, bool):
        try:
            return float(schema_value) == float(readme_value)
        except ValueError:
            return False
    return False


class ConfigSchemaContractTests(unittest.TestCase):
    def test_runtime_config_keys_are_declared_in_schema(self):
        missing = runtime_config_keys() - set(schema())
        self.assertEqual(missing, set())

    def test_schema_unused_keys_are_explicit_reserved_slots(self):
        unused = set(schema()) - runtime_config_keys()
        self.assertEqual(unused, {"humanlike_clinical_like_enabled"})
        self.assertIn(
            "第一轮仅保留配置位",
            schema()["humanlike_clinical_like_enabled"].get("hint", ""),
        )

    def test_schema_has_core_default_values_and_types(self):
        cfg = schema()
        expected = {
            "enabled": ("bool", True),
            "use_llm_assessor": ("bool", True),
            "assessment_timing": ("string", "both"),
            "inject_state": ("bool", True),
            "enable_safety_boundary": ("bool", True),
            "low_reasoning_friendly_mode": ("bool", False),
            "low_reasoning_max_context_chars": ("int", 1200),
            "allow_emotion_reset_backdoor": ("bool", True),
            "enable_humanlike_state": ("bool", False),
            "humanlike_injection_strength": ("float", 0.35),
            "humanlike_memory_write_enabled": ("bool", True),
            "allow_humanlike_reset_backdoor": ("bool", True),
            "enable_psychological_screening": ("bool", False),
            "baseline_half_life_seconds": ("float", 21600),
            "consequence_half_life_seconds": ("float", 10800),
            "cold_war_duration_seconds": ("float", 1800),
            "short_effect_duration_seconds": ("float", 900),
            "min_update_interval_seconds": ("float", 8),
            "rapid_update_half_life_seconds": ("float", 20),
            "humanlike_state_half_life_seconds": ("float", 21600),
            "humanlike_trajectory_limit": ("int", 40),
            "psychological_state_half_life_seconds": ("float", 604800),
            "psychological_crisis_half_life_seconds": ("float", 2592000),
            "psychological_trajectory_limit": ("int", 40),
        }
        for key, (type_name, default) in expected.items():
            with self.subTest(key=key):
                self.assertEqual(cfg[key]["type"], type_name)
                self.assertEqual(cfg[key]["default"], default)

    def test_schema_defaults_match_runtime_fallbacks(self):
        cfg = schema()
        mismatches = {}
        for key, calls in runtime_config_calls().items():
            runtime_defaults = {default for _, default in calls}
            if len(runtime_defaults) != 1:
                mismatches[key] = sorted(runtime_defaults, key=repr)
                continue
            runtime_default = next(iter(runtime_defaults))
            if cfg[key]["default"] != runtime_default:
                mismatches[key] = {
                    "schema": cfg[key]["default"],
                    "runtime": runtime_default,
                }
        self.assertEqual(mismatches, {})

    def test_schema_types_match_runtime_helpers(self):
        cfg = schema()
        expected_by_helper = {
            "_cfg_bool": "bool",
            "_cfg_float": "float",
            "_cfg_int": "int",
        }
        mismatches = {}
        for key, calls in runtime_config_calls().items():
            helpers = {helper for helper, _ in calls}
            for helper in helpers:
                expected_type = expected_by_helper.get(helper)
                if expected_type and cfg[key]["type"] != expected_type:
                    mismatches[key] = {
                        "helper": helper,
                        "schema_type": cfg[key]["type"],
                        "expected_type": expected_type,
                    }
        self.assertEqual(mismatches, {})

    def test_assessment_timing_schema_matches_runtime_options(self):
        cfg = schema()
        self.assertEqual(cfg["assessment_timing"]["options"], ["pre", "post", "both"])
        self.assertEqual(cfg["assessment_timing"]["default"], "both")

    def test_provider_schema_keeps_astrbot_selector_contract(self):
        cfg = schema()
        self.assertEqual(cfg["emotion_provider_id"]["type"], "string")
        self.assertEqual(cfg["emotion_provider_id"]["default"], "")
        self.assertEqual(cfg["emotion_provider_id"].get("_special"), "select_provider")

    def test_readme_backticked_config_defaults_match_schema(self):
        cfg = schema()
        defaults = readme_config_defaults()
        mismatches = {}
        for key, values in defaults.items():
            if key not in cfg:
                continue
            schema_value = normalize_default(cfg[key]["default"])
            if not any(defaults_match(cfg[key]["default"], value) for value in values):
                mismatches[key] = {
                    "readme": sorted(values),
                    "schema": schema_value,
                }
        self.assertEqual(mismatches, {})

    def test_readme_lists_runtime_config_keys(self):
        defaults = readme_config_defaults()
        documented_runtime_keys = set(defaults)
        missing = runtime_config_keys() - documented_runtime_keys
        allowed_omissions = {
            "emotion_provider_id",
        }
        self.assertEqual(missing - allowed_omissions, set())


if __name__ == "__main__":
    unittest.main()
