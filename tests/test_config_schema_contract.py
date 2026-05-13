import ast
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SYLANNE_MEMORY_OPERATIONAL_SCHEMA_KEYS = {
    "enable_sylanne_memory",
    "sylanne_memory_vector_retrieval_enabled",
    "sylanne_memory_embedding_provider_id",
    "sylanne_memory_debug_view_enabled",
    "allow_sylanne_memory_reset_backdoor",
}

SYLANNE_MEMORY_RESERVED_SCHEMA_KEYS = {
    "enable_sylanne_memory",
    "allow_sylanne_memory_reset_backdoor",
}

SYLANNE_MEMORY_CORE_HIDDEN_KEYS = {
    "sylanne_memory_salience_bias",
    "sylanne_memory_relationship_weight",
    "sylanne_memory_consolidation_gain",
    "sylanne_memory_decay_half_life_seconds",
    "sylanne_memory_decay_half_life_days",
    "sylanne_memory_recall_limit",
    "sylanne_memory_depth_threshold",
    "sylanne_memory_compression_threshold",
    "sylanne_memory_interference_sensitivity",
    "sylanne_memory_max_records",
    "sylanne_memory_prompt_max_chars",
    "sylanne_memory_max_prompt_chars",
}


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


def runtime_assessment_timing_options():
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "_assessment_timing":
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Compare):
                continue
            if not (
                isinstance(child.left, ast.Name)
                and child.left.id == "timing"
                and len(child.ops) == 1
                and isinstance(child.ops[0], ast.In)
                and len(child.comparators) == 1
                and isinstance(child.comparators[0], ast.Set)
            ):
                continue
            values = []
            for element in child.comparators[0].elts:
                if not isinstance(element, ast.Constant) or not isinstance(
                    element.value,
                    str,
                ):
                    continue
                values.append(element.value)
            return sorted(values)
    raise AssertionError("main.py _assessment_timing runtime options not found")


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


def readme_typed_config_rows():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    rows = {}
    valid_types = {"bool", "string", "int", "float"}
    for line in readme.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        key_cell, type_cell, default_cell = cells[:3]
        if not (
            key_cell.startswith("`")
            and key_cell.endswith("`")
            and type_cell in valid_types
            and default_cell.startswith("`")
            and default_cell.endswith("`")
        ):
            continue
        rows[key_cell.strip("`")] = {
            "type": type_cell,
            "default": default_cell.strip("`"),
        }
    return rows


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
        self.assertEqual(
            unused,
            {"humanlike_clinical_like_enabled"}
            | SYLANNE_MEMORY_RESERVED_SCHEMA_KEYS,
        )
        self.assertIn(
            "第一轮仅保留配置位",
            schema()["humanlike_clinical_like_enabled"].get("hint", ""),
        )

    def test_schema_has_core_default_values_and_types(self):
        cfg = schema()
        expected = {
            "enabled": ("bool", True),
            "use_llm_assessor": ("bool", True),
            "fast_assessor_provider_id": ("string", ""),
            "fast_assessor_max_context_chars": ("int", 600),
            "fast_assessor_timeout_seconds": ("float", 2.0),
            "fast_assessor_temperature": ("float", 0.0),
            "assessment_timing": ("string", "post"),
            "enable_proactive_speech_dispatch": ("bool", False),
            "enable_proactive_speech_scheduler": ("bool", False),
            "background_post_queue_limit": ("int", 0),
            "enable_dynamic_background_workers": ("bool", False),
            "background_post_queue_checkpoint_enabled": ("bool", True),
            "background_post_job_lease_seconds": ("float", 120.0),
            "background_post_job_timeout_seconds": ("float", 0.0),
            "background_post_retry_max_attempts": ("int", 3),
            "background_post_retry_base_delay_seconds": ("float", 2.0),
            "background_post_retry_max_delay_seconds": ("float", 60.0),
            "background_post_dead_letter_limit": ("int", 100),
            "background_post_diagnostics_warn_lag_count": ("int", 20),
            "background_post_diagnostics_warn_lag_seconds": ("float", 60.0),
            "enable_low_signal_light_assessment": ("bool", True),
            "low_signal_max_chars": ("int", 12),
            "agent_speaker_relationship_tracking": ("bool", True),
            "agent_include_speaker_in_assessment": ("bool", True),
            "agent_identity_profile_limit": ("int", 256),
            "agent_identity_ttl_seconds": ("float", 2592000.0),
            "enable_agent_causal_trail": ("bool", True),
            "agent_trail_limit": ("int", 80),
            "agent_trail_compaction_enabled": ("bool", True),
            "agent_trail_low_signal_delta_threshold": ("float", 0.03),
            "agent_trail_low_signal_window": ("int", 5),
            "inject_state": ("bool", True),
            "runtime_parameter_debug_override_enabled": ("bool", False),
            "state_injection_request_budget_chars": ("int", 32000),
            "state_injection_reserved_chars": ("int", 3000),
            "state_injection_max_added_chars": ("int", 2400),
            "state_injection_max_parts": ("int", 8),
            "llm_tool_response_max_chars": ("int", 16000),
            "enable_safety_boundary": ("bool", True),
            "block_deception_manipulation_evasion_actions": ("bool", True),
            "low_reasoning_friendly_mode": ("bool", False),
            "low_reasoning_max_context_chars": ("int", 1200),
            "sticker_llm_consistency_check_enabled": ("bool", True),
            "allow_emotion_reset_backdoor": ("bool", True),
            "enable_shadow_diagnostics": ("bool", False),
            "enable_sylanne_memory": ("bool", True),
            "sylanne_memory_debug_view_enabled": ("bool", False),
            "allow_sylanne_memory_reset_backdoor": ("bool", True),
            "humanlike_memory_write_enabled": ("bool", True),
            "allow_humanlike_reset_backdoor": ("bool", True),
            "enable_psychological_screening": ("bool", False),
            "enable_integrated_self_state": ("bool", True),
            "integrated_self_memory_write_enabled": ("bool", True),
            "provider_id_cache_ttl_seconds": ("float", 30.0),
            "passive_load_fresh_seconds": ("float", 1.0),
            "benchmark_enable_simulated_time": ("bool", False),
            "benchmark_time_offset_seconds": ("float", 0.0),
        }
        for key, (type_name, default) in expected.items():
            with self.subTest(key=key):
                self.assertEqual(cfg[key]["type"], type_name)
                self.assertEqual(cfg[key]["default"], default)

    def test_personality_expression_parameters_are_not_user_tunable(self):
        cfg = schema()
        hidden_keys = {
            *SYLANNE_MEMORY_CORE_HIDDEN_KEYS,
            "proactive_speech_dispatch_cooldown_seconds",
            "proactive_speech_dispatch_ttl_seconds",
            "proactive_speech_max_chars",
            "realtime_chat_max_parts",
            "realtime_chat_min_part_chars",
            "realtime_chat_max_part_chars",
            "realtime_chat_chars_per_second",
            "realtime_chat_min_delay_seconds",
            "realtime_chat_max_delay_seconds",
            "realtime_chat_jitter_ratio",
            "realtime_chat_session_cooldown_seconds",
            "sticker_send_probability",
            "state_injection_detail",
            "state_injection_compact_mode",
            "state_injection_diff_threshold",
            "group_atmosphere_injection_diff_threshold",
            "state_injection_diff_force_every_turns",
            "auxiliary_state_injection_detail",
        }
        self.assertFalse(hidden_keys & set(cfg))

    def test_sylanne_memory_schema_exposes_only_operational_switches(self):
        cfg = schema()
        exposed_memory_keys = {
            key
            for key in cfg
            if key.startswith("sylanne_memory_")
            or key in {
                "enable_sylanne_memory",
                "allow_sylanne_memory_reset_backdoor",
            }
        }

        self.assertEqual(
            exposed_memory_keys,
            SYLANNE_MEMORY_OPERATIONAL_SCHEMA_KEYS,
        )
        self.assertTrue(SYLANNE_MEMORY_CORE_HIDDEN_KEYS.isdisjoint(cfg))
        self.assertEqual(cfg["enable_sylanne_memory"]["default"], True)
        self.assertEqual(
            cfg["sylanne_memory_vector_retrieval_enabled"]["default"],
            True,
        )
        self.assertEqual(
            cfg["sylanne_memory_embedding_provider_id"]["default"],
            "",
        )
        self.assertEqual(
            cfg["sylanne_memory_debug_view_enabled"]["default"],
            False,
        )
        self.assertEqual(
            cfg["allow_sylanne_memory_reset_backdoor"]["default"],
            True,
        )
        self.assertNotIn("enable_livingmemory_recall_injection", cfg)
        self.assertIn(
            "不提供核心参数手动覆盖",
            cfg["sylanne_memory_debug_view_enabled"]["hint"],
        )

    def test_current_readme_uses_first_party_memory_contract(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        current_readme = readme.split("## 旧版迭代记录", 1)[0]

        self.assertIn("## Sylanne 自有长期记忆", current_readme)
        self.assertIn("source=\"sylanne_memory\"", current_readme)
        self.assertNotIn("enable_livingmemory_recall_injection", current_readme)
        self.assertNotIn("sylanne_livingmemory_recall", current_readme)
        self.assertNotIn("source=\"livingmemory\"", current_readme)

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
        runtime_options = runtime_assessment_timing_options()
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertEqual(sorted(cfg["assessment_timing"]["options"]), runtime_options)
        self.assertEqual(cfg["assessment_timing"]["default"], "post")
        self.assertIn("| `assessment_timing` | string | `post` |", readme)
        for option in runtime_options:
            self.assertIn(option, readme)

    def test_provider_schema_keeps_astrbot_selector_contract(self):
        cfg = schema()
        self.assertEqual(cfg["emotion_provider_id"]["type"], "string")
        self.assertEqual(cfg["emotion_provider_id"]["default"], "")
        self.assertEqual(cfg["emotion_provider_id"].get("_special"), "select_provider")
        self.assertEqual(cfg["fast_assessor_provider_id"]["type"], "string")
        self.assertEqual(cfg["fast_assessor_provider_id"]["default"], "")
        self.assertEqual(cfg["fast_assessor_provider_id"].get("_special"), "select_provider")
        self.assertEqual(
            cfg["sylanne_memory_embedding_provider_id"].get("_special"),
            "select_provider",
        )
        self.assertEqual(
            cfg["sylanne_memory_embedding_provider_id"].get("provider_type"),
            "embedding",
        )

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

    def test_readme_typed_config_table_covers_non_legacy_schema_keys(self):
        cfg = schema()
        typed_rows = readme_typed_config_rows()
        legacy_config_keys = {
            "baseline_decay",
            "consequence_decay",
            "cold_war_turns",
        }
        schema_only_operational_slots = (
            SYLANNE_MEMORY_OPERATIONAL_SCHEMA_KEYS
        )
        missing = (
            set(cfg)
            - set(typed_rows)
            - legacy_config_keys
            - schema_only_operational_slots
        )
        type_mismatches = {
            key: {
                "readme": row["type"],
                "schema": cfg[key]["type"],
            }
            for key, row in typed_rows.items()
            if key in cfg and row["type"] != cfg[key]["type"]
        }

        self.assertEqual(missing, set())
        self.assertEqual(type_mismatches, {})

    def test_humanlike_docs_match_current_schema_names(self):
        cfg = schema()
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        roadmap = (ROOT / "docs" / "humanlike_agent_model_roadmap.md").read_text(
            encoding="utf-8",
        )
        iteration_log = (
            ROOT / "docs" / "humanlike_agent_iteration_log.md"
        ).read_text(encoding="utf-8")
        combined = "\n".join((readme, roadmap, iteration_log))

        self.assertIn("humanlike_state_at_write", combined)
        self.assertNotIn("humanlike_at_write", combined)
        self.assertNotIn("humanlike_personification_level", readme)
        self.assertNotIn("humanlike_personification_level", roadmap)
        self.assertNotIn("humanlike_dependency_guard_level", readme)
        self.assertNotIn("humanlike_dependency_guard_level", roadmap)
        self.assertNotIn("dependency_guard_level", readme)
        self.assertNotIn("dependency_guard_level", roadmap)
        self.assertNotIn("daily_recovery_window", roadmap)
        self.assertNotIn("daily_recovery_window", iteration_log)
        self.assertNotIn("max_impulse_per_hour", roadmap)
        self.assertNotIn("max_impulse_per_hour", iteration_log)
        self.assertNotIn("simulation_flags", roadmap)
        self.assertNotIn("simulation_flags", iteration_log)
        self.assertIn("未进入当前 schema", iteration_log)
        self.assertIn("humanlike_updated_at", roadmap)
        self.assertIn("flags", roadmap)
        self.assertIn("flags", iteration_log)
        self.assertEqual(cfg["humanlike_memory_write_enabled"]["default"], True)
        self.assertIn('"humanlike_memory_write_enabled": true', roadmap)


if __name__ == "__main__":
    unittest.main()
