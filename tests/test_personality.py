"""人格漂移单元测试。"""
import sys
sys.path.insert(0, '.')

def test_drift_cap():
    """极端信号不越界。"""
    from sylanne_alpha.personality import compute_embodiment_drift, TraitMemory
    traits = {
        "expression_drive_trait": TraitMemory(0.95),
        "perception_acuity": TraitMemory(0.05),
    }
    # 模拟极端正向信号
    signals = {"valence": 1.0, "arousal": 1.0, "tension": 1.0}
    compute_embodiment_drift(traits, signals, tick_count=100)
    for name, tm in traits.items():
        assert 0.0 <= tm.value <= 1.0, f"Trait {name} out of bounds: {tm.value}"

def test_seasonal_modulation():
    from sylanne_alpha.personality import _seasonal_modulation, TraitMemory
    traits = {
        "inner_order": TraitMemory(0.5),
        "expression_drive_trait": TraitMemory(0.5),
        "boundary_permeability": TraitMemory(0.5),
        "perception_acuity": TraitMemory(0.5),
    }
    original_values = {k: tm.value for k, tm in traits.items()}
    _seasonal_modulation(traits)
    # 应该有一个维度变化了 0.01
    diffs = [abs(traits[k].value - original_values[k]) for k in traits]
    assert any(d > 0.005 for d in diffs)

def test_contradiction_tolerance():
    from sylanne_alpha.personality import contradiction_tolerance
    assert abs(contradiction_tolerance({"inner_order": 0.0}) - 1.0) < 1e-9
    assert abs(contradiction_tolerance({"inner_order": 1.0}) - 0.2) < 1e-9

if __name__ == "__main__":
    test_drift_cap()
    test_seasonal_modulation()
    test_contradiction_tolerance()
    print("All personality tests passed!")
