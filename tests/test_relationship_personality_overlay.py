"""Tests for per-relationship personality overlays in ComputationSpine.

Verifies that:
- effective_personality returns base when no session_key
- relationship deltas evolve on feedback with session_key
- deltas are capped at +/-0.1
- process() with session_key applies overlay temporarily
- serialization round-trips relationship_deltas
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sylanne_alpha.computation_spine import ComputationSpine


def test_effective_personality_returns_base_without_session():
    spine = ComputationSpine()
    base = dict(spine._personality)
    effective = spine.effective_personality()
    assert effective == base
    effective2 = spine.effective_personality("")
    assert effective2 == base


def test_effective_personality_returns_base_for_unknown_session():
    spine = ComputationSpine()
    base = dict(spine._personality)
    effective = spine.effective_personality("unknown_session")
    assert effective == base


def test_feedback_with_session_key_creates_delta():
    spine = ComputationSpine()
    spine.process("hello", 1000.0)
    spine.feedback("accepted", 1.0, session_key="user_a")

    assert "user_a" in spine._relationship_deltas
    delta = spine._relationship_deltas["user_a"]
    assert delta["extraversion"] > 0.0
    assert delta["agreeableness"] > 0.0


def test_feedback_without_session_key_no_delta():
    spine = ComputationSpine()
    spine.process("hello", 1000.0)
    spine.feedback("accepted", 1.0)

    assert spine._relationship_deltas == {}


def test_rejected_feedback_decreases_extraversion_increases_neuroticism():
    spine = ComputationSpine()
    spine.process("hello", 1000.0)
    spine.feedback("rejected", 1.0, session_key="user_b")

    delta = spine._relationship_deltas["user_b"]
    assert delta["extraversion"] < 0.0
    assert delta["neuroticism"] > 0.0


def test_ignored_feedback_decreases_extraversion():
    spine = ComputationSpine()
    spine.process("hello", 1000.0)
    spine.feedback("ignored", 1.0, session_key="user_c")

    delta = spine._relationship_deltas["user_c"]
    assert delta["extraversion"] < 0.0


def test_delta_capped_at_plus_minus_0_1():
    spine = ComputationSpine()
    spine.process("hello", 1000.0)

    # Apply many accepted feedbacks to push extraversion delta to cap
    for _ in range(200):
        spine.feedback("accepted", 1.0, session_key="user_d")

    delta = spine._relationship_deltas["user_d"]
    assert delta["extraversion"] <= 0.1
    assert delta["agreeableness"] <= 0.1

    # Apply many rejected feedbacks to push extraversion delta to negative cap
    for _ in range(400):
        spine.feedback("rejected", 1.0, session_key="user_d")

    delta = spine._relationship_deltas["user_d"]
    assert delta["extraversion"] >= -0.1
    assert delta["neuroticism"] <= 0.1


def test_effective_personality_applies_delta():
    spine = ComputationSpine()
    spine._relationship_deltas["user_e"] = {
        "extraversion": 0.05,
        "neuroticism": -0.03,
        "conscientiousness": 0.0,
        "openness": 0.0,
        "agreeableness": 0.02,
    }

    base = dict(spine._personality)
    effective = spine.effective_personality("user_e")

    assert abs(effective["extraversion"] - (base["extraversion"] + 0.05)) < 1e-9
    assert abs(effective["neuroticism"] - (base["neuroticism"] - 0.03)) < 1e-9
    assert abs(effective["agreeableness"] - (base["agreeableness"] + 0.02)) < 1e-9
    # Unchanged traits stay the same
    assert effective["openness"] == base["openness"]


def test_effective_personality_clamps_to_bounds():
    spine = ComputationSpine()
    # Set base near ceiling
    spine._personality["extraversion"] = 0.92
    spine._relationship_deltas["user_f"] = {
        "extraversion": 0.1,
        "neuroticism": 0.0,
        "conscientiousness": 0.0,
        "openness": 0.0,
        "agreeableness": 0.0,
    }

    effective = spine.effective_personality("user_f")
    assert effective["extraversion"] <= 0.95

    # Set base near floor
    spine._personality["neuroticism"] = 0.06
    spine._relationship_deltas["user_f"]["neuroticism"] = -0.1
    effective = spine.effective_personality("user_f")
    assert effective["neuroticism"] >= 0.05


def test_process_with_session_key_restores_personality():
    spine = ComputationSpine()
    spine._relationship_deltas["user_g"] = {
        "extraversion": 0.08,
        "neuroticism": -0.05,
        "conscientiousness": 0.0,
        "openness": 0.0,
        "agreeableness": 0.0,
    }
    base_before = dict(spine._personality)

    result = spine.process("test message", 1000.0, session_key="user_g")

    # After process, base personality trait VALUES should be restored
    # (apply_personality may normalize/expand keys, but original values are intact)
    for trait, value in base_before.items():
        assert abs(spine._personality[trait] - value) < 0.02, (
            f"{trait}: expected ~{value}, got {spine._personality[trait]}"
        )
    # Result should still be valid
    assert "tick" in result
    assert result["route"] in ("fast", "normal", "full", "skip")


def test_process_without_session_key_unchanged():
    spine = ComputationSpine()

    spine.process("test message", 1000.0)

    # Personality may drift via embodiment system, but relationship deltas stay empty
    assert spine._relationship_deltas == {}


def test_different_sessions_have_independent_deltas():
    spine = ComputationSpine()
    spine.process("hello", 1000.0)

    # user_a gets accepted feedback
    for _ in range(10):
        spine.feedback("accepted", 1.0, session_key="user_a")

    # user_b gets rejected feedback
    for _ in range(10):
        spine.feedback("rejected", 1.0, session_key="user_b")

    delta_a = spine._relationship_deltas["user_a"]
    delta_b = spine._relationship_deltas["user_b"]

    # user_a should be more extraverted, user_b less
    assert delta_a["extraversion"] > 0
    assert delta_b["extraversion"] < 0


def test_serialization_round_trip_with_relationship_deltas():
    spine = ComputationSpine()
    spine.process("hello", 1000.0)
    spine.feedback("accepted", 1.0, session_key="user_x")
    spine.feedback("rejected", 1.0, session_key="user_y")

    data = spine.to_dict()
    serialized = json.dumps(data)

    spine2 = ComputationSpine()
    spine2.from_dict(json.loads(serialized))

    assert spine2._relationship_deltas == spine._relationship_deltas
    assert "user_x" in spine2._relationship_deltas
    assert "user_y" in spine2._relationship_deltas


def test_empty_serialization_has_empty_deltas():
    spine = ComputationSpine()
    data = spine.to_dict()

    assert data["relationship_deltas"] == {}

    spine2 = ComputationSpine()
    spine2.from_dict(data)
    assert spine2._relationship_deltas == {}


if __name__ == "__main__":
    test_effective_personality_returns_base_without_session()
    test_effective_personality_returns_base_for_unknown_session()
    test_feedback_with_session_key_creates_delta()
    test_feedback_without_session_key_no_delta()
    test_rejected_feedback_decreases_extraversion_increases_neuroticism()
    test_ignored_feedback_decreases_extraversion()
    test_delta_capped_at_plus_minus_0_1()
    test_effective_personality_applies_delta()
    test_effective_personality_clamps_to_bounds()
    test_process_with_session_key_restores_personality()
    test_process_without_session_key_unchanged()
    test_different_sessions_have_independent_deltas()
    test_serialization_round_trip_with_relationship_deltas()
    test_empty_serialization_has_empty_deltas()
    print("\nAll relationship personality overlay tests passed.")
