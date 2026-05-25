"""Hebbian adaptation convergence and stability tests."""
import sys
import math

from sylanne_alpha.hgt import (
    HeterogeneousGraphTransformer, TOKEN_TYPES, _N_EXPERTS, _NUM_TYPES,
    RouterAdaptation, AttentionPriorAdaptation, _derive_plasticity,
)

PERSONALITY = {
    "extraversion": 0.6, "neuroticism": 0.4,
    "conscientiousness": 0.5, "openness": 0.7, "agreeableness": 0.5,
}


def _make_tokens(scale=0.1):
    return [(t, [scale * (i + 1)] * 16) for i, t in enumerate(TOKEN_TYPES)]


class TestBCMAdaptation:
    def test_ltp_repeated_accepted(self):
        """Repeated 'accepted' should increase active expert bias."""
        hgt = HeterogeneousGraphTransformer()
        hgt.derive_params(PERSONALITY)
        tokens = _make_tokens()

        for _ in range(100):
            hgt.forward(tokens)
            hgt.adapt("accepted")

        state = hgt.adaptation_state()
        active = state["last_active_experts"]
        bias = state["router_bias"]
        assert bias[active[0]] > 0.001

    def test_ltd_repeated_rejected(self):
        """Repeated 'rejected' should decrease active expert bias."""
        hgt = HeterogeneousGraphTransformer()
        hgt.derive_params(PERSONALITY)
        tokens = _make_tokens()

        for _ in range(100):
            hgt.forward(tokens)
            hgt.adapt("rejected")

        state = hgt.adaptation_state()
        active = state["last_active_experts"]
        bias = state["router_bias"]
        assert bias[active[0]] < -0.001

    def test_sliding_threshold(self):
        """Activity EMA should track usage patterns."""
        ra = RouterAdaptation(5)
        ra.plasticity = 0.7
        gate = [0.4, 0.1, 0.1, 0.3, 0.1]
        initial_ema = list(ra.activity_ema)

        for _ in range(50):
            ra.adapt("accepted", [0, 3], gate)

        assert ra.activity_ema[0] != initial_ema[0]
        assert ra.activity_ema[3] != initial_ema[3]
        # Inactive experts' EMA unchanged
        assert ra.activity_ema[1] == initial_ema[1]

    def test_bias_bounded(self):
        """Router bias must stay within [-1, 1]."""
        ra = RouterAdaptation(5)
        ra.plasticity = 0.85
        gate = [0.8, 0.05, 0.05, 0.05, 0.05]
        for _ in range(10000):
            ra.adapt("accepted", [0], gate)
        assert -1.0 <= ra.bias[0] <= 1.0

    def test_decay_prevents_extremes(self):
        """Without new input, bias should decay toward zero."""
        ra = RouterAdaptation(5)
        ra.bias = [0.5, -0.5, 0.3, -0.3, 0.1]
        for _ in range(1000):
            ra.adapt("ignored", [], [0.2] * 5)
        assert all(abs(b) < 0.2 for b in ra.bias)


class TestOjaAdaptation:
    def test_convergence_bounded(self):
        """Attention drift must stay within [-0.3, 0.3]."""
        aa = AttentionPriorAdaptation(7)
        aa.plasticity = 0.85
        weights = [[0.2 if i != j else 0.0 for j in range(7)] for i in range(7)]
        for _ in range(10000):
            aa.adapt("accepted", weights)
        for i in range(7):
            for j in range(7):
                assert -0.3 <= aa.drift[i][j] <= 0.3

    def test_rejected_weakens_connections(self):
        """Rejected outcome should reduce drift values."""
        aa = AttentionPriorAdaptation(7)
        aa.plasticity = 0.7
        weights = [[0.3 if i != j else 0.0 for j in range(7)] for i in range(7)]
        # First build up some positive drift
        for _ in range(50):
            aa.adapt("accepted", weights)
        drift_after_accept = aa.drift[0][1]
        # Then reject
        for _ in range(50):
            aa.adapt("rejected", weights)
        assert aa.drift[0][1] < drift_after_accept

    def test_diagonal_never_adapts(self):
        """Intra-type mask: diagonal drift must always be 0."""
        aa = AttentionPriorAdaptation(7)
        aa.plasticity = 0.85
        weights = [[0.5] * 7 for _ in range(7)]
        for _ in range(100):
            aa.adapt("accepted", weights)
        for i in range(7):
            assert aa.drift[i][i] == 0.0

    def test_decay_toward_zero(self):
        """Without adaptation, drift decays."""
        aa = AttentionPriorAdaptation(7)
        aa.drift[0][1] = 0.2
        aa.drift[2][3] = -0.15
        weights = [[0.0] * 7 for _ in range(7)]
        for _ in range(1000):
            aa.adapt("ignored", weights)
        assert abs(aa.drift[0][1]) < 0.1
        assert abs(aa.drift[2][3]) < 0.08


class TestPlasticityModulation:
    def test_high_openness_fast_adaptation(self):
        """High openness personality should adapt faster."""
        hgt_open = HeterogeneousGraphTransformer()
        hgt_open.derive_params({"openness": 0.9, "conscientiousness": 0.2,
                                "extraversion": 0.5, "neuroticism": 0.5, "agreeableness": 0.5})
        hgt_closed = HeterogeneousGraphTransformer()
        hgt_closed.derive_params({"openness": 0.2, "conscientiousness": 0.9,
                                  "extraversion": 0.5, "neuroticism": 0.5, "agreeableness": 0.5})
        tokens = _make_tokens()
        for _ in range(50):
            hgt_open.forward(tokens)
            hgt_open.adapt("accepted")
            hgt_closed.forward(tokens)
            hgt_closed.adapt("accepted")

        bias_open = max(abs(b) for b in hgt_open.adaptation_state()["router_bias"])
        bias_closed = max(abs(b) for b in hgt_closed.adaptation_state()["router_bias"])
        assert bias_open > bias_closed


class TestLongRunStability:
    def test_10000_random_feedback(self):
        """10000 random feedbacks should not cause overflow or NaN."""
        import random
        random.seed(42)
        hgt = HeterogeneousGraphTransformer()
        hgt.derive_params(PERSONALITY)
        tokens = _make_tokens()
        outcomes = ["accepted", "ignored", "rejected"]

        for _ in range(10000):
            hgt.forward(tokens)
            hgt.adapt(random.choice(outcomes))

        state = hgt.adaptation_state()
        for b in state["router_bias"]:
            assert math.isfinite(b)
            assert -1.0 <= b <= 1.0
        for row in state["attention_drift"]:
            for v in row:
                assert math.isfinite(v)
                assert -0.3 <= v <= 0.3

    def test_expert_specialization_entropy(self):
        """Different input patterns should route to different experts."""
        hgt = HeterogeneousGraphTransformer()
        hgt.derive_params(PERSONALITY)

        expert_selections = set()
        for pattern in range(10):
            tokens = [(t, [0.1 * pattern * (i + 1)] * 16) for i, t in enumerate(TOKEN_TYPES)]
            hgt.forward(tokens)
            state = hgt.adaptation_state()
            expert_selections.add(tuple(sorted(state["last_active_experts"])))

        # At least 2 different expert pairs selected across 10 patterns
        assert len(expert_selections) >= 2
