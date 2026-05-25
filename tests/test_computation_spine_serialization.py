"""Verify ComputationSpine serialization round-trip completeness.

Ensures that to_dict/from_dict preserves all critical state across
engine, boundary, expression, gate, and HGT modules.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sylanne_alpha.computation_spine import ComputationSpine


def test_serialization_round_trip():
    """Full round-trip: process data, serialize, deserialize, compare."""
    spine = ComputationSpine()

    spine.process("hello world", 1000.0)
    spine.process("how are you today", 1001.0)
    spine.process("this is a longer message with more content", 1002.0)
    spine.feedback("accepted", 1.0)
    spine.feedback("ignored", 0.5)

    data = spine.to_dict()
    serialized = json.dumps(data)

    spine2 = ComputationSpine()
    spine2.from_dict(json.loads(serialized))

    # Compare boundary
    assert abs(spine.boundary.boundary_integrity - spine2.boundary.boundary_integrity) < 1e-9
    assert abs(spine.boundary.internal_entropy - spine2.boundary.internal_entropy) < 1e-9

    # Compare expression
    assert abs(spine.expression.pressure - spine2.expression.pressure) < 1e-9
    assert abs(spine.expression.threshold - spine2.expression.threshold) < 1e-9

    # Compare gate
    assert abs(spine.gate.precision - spine2.gate.precision) < 1e-9

    # Compare tick count
    assert spine._tick_count == spine2._tick_count

    # Compare route counts
    assert spine._route_counts == spine2._route_counts


def test_empty_spine_serialization():
    """Fresh spine serializes and restores cleanly."""
    spine = ComputationSpine()
    data = spine.to_dict()
    serialized = json.dumps(data)

    spine2 = ComputationSpine()
    spine2.from_dict(json.loads(serialized))

    assert spine._tick_count == spine2._tick_count == 0
    assert spine.boundary.boundary_integrity == spine2.boundary.boundary_integrity


def test_feedback_state_persists():
    """Feedback modifies engine state and that state persists through serialization."""
    spine = ComputationSpine()
    spine.process("test input", 100.0)

    spine.feedback("rejected", 2.0)
    engine_state_after = spine.engine.to_dict()

    data = spine.to_dict()
    spine2 = ComputationSpine()
    spine2.from_dict(data)

    engine_state_restored = spine2.engine.to_dict()
    assert engine_state_after == engine_state_restored


if __name__ == "__main__":
    test_serialization_round_trip()
    test_empty_spine_serialization()
    test_feedback_state_persists()
    print("\nAll serialization tests passed.")
