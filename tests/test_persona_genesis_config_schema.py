"""人格创生配置入口的 schema 契约。"""

import json
from pathlib import Path


def test_persona_genesis_schema_requires_explicit_paid_opt_in() -> None:
    schema_path = Path(__file__).resolve().parents[1] / "_conf_schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    enabled = schema["sylanne_alpha_persona_genesis_enabled"]
    assert enabled["type"] == "bool"
    assert enabled["default"] is False

    paid_opt_in = schema["sylanne_alpha_persona_genesis_paid_opt_in"]
    assert paid_opt_in["type"] == "bool"
    assert paid_opt_in["default"] is False
    assert "额外付费 LLM 调用" in paid_opt_in["hint"]
    assert "主动同意" in paid_opt_in["hint"]

    provider = schema["sylanne_alpha_persona_genesis_provider_id"]
    assert provider["type"] == "string"
    assert provider["default"] == ""
    assert provider["_special"] == "select_provider"
    assert provider["ui_tier"] == "advanced_provider"
    assert "留空" in provider["hint"]
    assert "共享辅助模型" in provider["hint"]
