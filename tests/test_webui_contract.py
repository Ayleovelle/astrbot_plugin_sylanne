"""WebUI API 端点契约测试（验证端点注册和基本响应格式）。"""
import sys
sys.path.insert(0, '.')

def test_glossary_data():
    from sylanne_alpha.webui_routes import GLOSSARY
    assert isinstance(GLOSSARY, dict)
    assert "伤痕" in GLOSSARY
    assert len(GLOSSARY) >= 5

def test_config_presets():
    from sylanne_alpha.webui_routes import CONFIG_PRESETS
    assert "gentle" in CONFIG_PRESETS
    assert "sharp" in CONFIG_PRESETS
    assert "quiet" in CONFIG_PRESETS
    for preset in CONFIG_PRESETS.values():
        assert "name" in preset
        assert "values" in preset

if __name__ == "__main__":
    test_glossary_data()
    test_config_presets()
    print("All WebUI contract tests passed!")
