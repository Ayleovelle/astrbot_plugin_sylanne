"""计算栈冒烟测试：验证 import 和基本 process 不崩溃。"""
import sys
sys.path.insert(0, '.')

def test_imports():
    from sylanne_alpha import computation_spine, personality, memory_system
    from sylanne_alpha import void_calculus, scar_algebra, social_field
    from sylanne_alpha import analytics

def test_spine_process():
    from sylanne_alpha.computation_spine import ComputationSpine
    spine = ComputationSpine()
    result = spine.process("你好世界", 0.0)
    assert isinstance(result, dict)
    assert "route" in result

def test_personality_drift():
    from sylanne_alpha.personality import compute_embodiment_drift, contradiction_tolerance
    val = contradiction_tolerance({"inner_order": 1.0})
    assert 0.19 <= val <= 1.0, f"contradiction_tolerance out of range: {val}"

def test_memory_temperature():
    from sylanne_alpha.memory_system import MemoryResult
    import time
    m = MemoryResult(text="test", layer="L1", weight=1.0, relevance=0.8, clarity=0.9, temperature=0.5, final_score=0.5, created_at=time.time(), recall_count=0, emotional_weight=0.5)
    assert m.memory_temperature in ("hot", "warm", "cold")

if __name__ == "__main__":
    test_imports()
    test_spine_process()
    test_personality_drift()
    test_memory_temperature()
    print("All smoke tests passed!")
