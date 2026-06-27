"""assessor 输出 token 预算可配置（修复：推理模型把写死的 50/100 全花在隐藏推理上 →
正文空 → 情感读数恒落中性；改为读 sylanne_alpha_assessor_max_tokens，默认 1024）。"""

from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline


def _pipeline_with_config(cfg: dict) -> LLMRequestPipeline:
    """绕开重 __init__，只装一个带 _config 的假 plugin host 测预算解析。"""
    inst = object.__new__(LLMRequestPipeline)

    class _FakeP:
        _config = cfg

    inst._p = _FakeP()
    return inst


def test_default_is_reasoning_safe():
    # 未配置 → 默认 1024（覆盖实测最坏 ~852 token 的推理预算，远高于旧版写死的 50/100）
    assert _pipeline_with_config({})._assessor_max_tokens() == 1024


def test_config_override_respected():
    assert _pipeline_with_config({"sylanne_alpha_assessor_max_tokens": 2048})._assessor_max_tokens() == 2048


def test_zero_or_blank_falls_back_to_default():
    assert _pipeline_with_config({"sylanne_alpha_assessor_max_tokens": 0})._assessor_max_tokens() == 1024
    assert _pipeline_with_config({"sylanne_alpha_assessor_max_tokens": None})._assessor_max_tokens() == 1024


def test_string_value_coerced_to_int():
    # AstrBot 配置回传字符串时也要能用
    assert _pipeline_with_config({"sylanne_alpha_assessor_max_tokens": "1500"})._assessor_max_tokens() == 1500


def test_string_zero_and_negatives_fall_back():
    # gemini PR#46：`or 1024` 对字符串 "0" 失效（非空串为真值 → int("0")=0 绕过默认）；
    # 负数也无效。任何 <=0（含字符串/负数）都须回退 1024。
    assert _pipeline_with_config({"sylanne_alpha_assessor_max_tokens": "0"})._assessor_max_tokens() == 1024
    assert _pipeline_with_config({"sylanne_alpha_assessor_max_tokens": -10})._assessor_max_tokens() == 1024
    assert _pipeline_with_config({"sylanne_alpha_assessor_max_tokens": "-5"})._assessor_max_tokens() == 1024
    assert _pipeline_with_config({"sylanne_alpha_assessor_max_tokens": "abc"})._assessor_max_tokens() == 1024


def test_schema_declares_key():
    import json

    schema = json.load(open("_conf_schema.json", encoding="utf-8"))
    entry = schema.get("sylanne_alpha_assessor_max_tokens")
    assert entry is not None and entry.get("type") == "int" and entry.get("default") == 1024
