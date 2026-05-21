"""Verify ComputationSpine serialization round-trip completeness.

Ensures that to_dict/from_dict preserves all critical state across
SSM, boundary, expression, gate, and memory modules.
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

    # Process some data to build up state
    spine.process("hello world", 1000.0)
    spine.process("how are you today", 1001.0)
    spine.process("this is a longer message with more content", 1002.0)
    spine.feedback("accepted", 1.0)
    spine.feedback("ignored", 0.5)

    # Serialize
    data = spine.to_dict()
    serialized = json.dumps(data)

    # Deserialize into a fresh spine
    spine2 = ComputationSpine()
    spine2.from_dict(json.loads(serialized))

    # Compare SSM state
    assert spine.ssm.state == spine2.ssm.state, (
        f"SSM state mismatch:\n  original={spine.ssm.state}\n  restored={spine2.ssm.state}"
    )

    # Compare boundary
    assert abs(spine.boundary.boundary_integrity - spine2.boundary.boundary_integrity) < 1e-9, (
        f"Boundary integrity mismatch: {spine.boundary.boundary_integrity} vs {spine2.boundary.boundary_integrity}"
    )
    assert abs(spine.boundary.internal_entropy - spine2.boundary.internal_entropy) < 1e-9, (
        f"Boundary entropy mismatch: {spine.boundary.internal_entropy} vs {spine2.boundary.internal_entropy}"
    )

    # Compare expression
    assert abs(spine.expression.pressure - spine2.expression.pressure) < 1e-9, (
        f"Expression pressure mismatch: {spine.expression.pressure} vs {spine2.expression.pressure}"
    )
    assert abs(spine.expression.threshold - spine2.expression.threshold) < 1e-9, (
        f"Expression threshold mismatch: {spine.expression.threshold} vs {spine2.expression.threshold}"
    )

    # Compare gate
    assert abs(spine.gate.precision - spine2.gate.precision) < 1e-9, (
        f"Gate precision mismatch: {spine.gate.precision} vs {spine2.gate.precision}"
    )

    # Compare memory size
    assert spine.memory.size() == spine2.memory.size(), (
        f"Memory size mismatch: {spine.memory.size()} vs {spine2.memory.size()}"
    )

    # Compare tick count
    assert spine._tick_count == spine2._tick_count, (
        f"Tick count mismatch: {spine._tick_count} vs {spine2._tick_count}"
    )

    print("Serialization round-trip: ALL MATCH")


def test_empty_spine_serialization():
    """Fresh spine serializes and restores cleanly."""
    spine = ComputationSpine()
    data = spine.to_dict()
    serialized = json.dumps(data)

    spine2 = ComputationSpine()
    spine2.from_dict(json.loads(serialized))

    assert spine.ssm.state == spine2.ssm.state
    assert spine.memory.size() == spine2.memory.size() == 0
    assert spine._tick_count == spine2._tick_count == 0
    print("Empty spine serialization: OK")


def test_feedback_state_persists():
    """Feedback modifies SSM state and that state persists through serialization."""
    spine = ComputationSpine()
    spine.process("test input", 100.0)

    # Apply feedback
    spine.feedback("rejected", 2.0)
    state_after_feedback = list(spine.ssm.state)

    # Serialize and restore
    data = spine.to_dict()
    spine2 = ComputationSpine()
    spine2.from_dict(data)

    assert spine2.ssm.state == state_after_feedback, "Feedback state not preserved"
    print("Feedback state persistence: OK")


if __name__ == "__main__":
    test_serialization_round_trip()
    test_empty_spine_serialization()
    test_feedback_state_persists()
    print("\nAll serialization tests passed.")
