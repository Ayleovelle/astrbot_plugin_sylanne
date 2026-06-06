"""计算栈回归测试：验证已知输入的输出不变。"""
import sys
sys.path.insert(0, '.')

KNOWN_INPUT = "你好世界"
# 只验证结构和关键字段存在，不验证具体数值（因为有随机性）


def test_output_structure():
    from sylanne_alpha.computation_spine import ComputationSpine
    spine = ComputationSpine()
    result = spine.process(KNOWN_INPUT, 0.0)
    # 必须包含的字段
    required_keys = ["route", "hgt_decision"]
    for key in required_keys:
        assert key in result, f"Missing key: {key}"
    # route 必须是 fast/normal/full 之一
    assert result["route"] in ("fast", "normal", "full", "skip")


def test_empty_input():
    from sylanne_alpha.computation_spine import ComputationSpine
    spine = ComputationSpine()
    result = spine.process("", 0.0)
    assert result["route"] == "skip"


if __name__ == "__main__":
    test_output_structure()
    test_empty_input()
    print("Regression tests passed!")
