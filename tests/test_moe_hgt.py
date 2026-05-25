"""Unit tests for MoE-HGT architecture."""
import sys
import math

from sylanne_alpha.hgt import (
    HeterogeneousGraphTransformer, TOKEN_TYPES, _NUM_TYPES, _N_EXPERTS,
    TypeExpertFFN, MultiHeadCrossAttention, MoELayer, SituationExpert,
    RouterAdaptation, AttentionPriorAdaptation,
    _silu, _rmsnorm, _softmax, _make_flat, _matmul_vec_flat, _vec_add,
    _derive_plasticity,
)

PERSONALITY = {
    "extraversion": 0.6, "neuroticism": 0.4,
    "conscientiousness": 0.5, "openness": 0.7, "agreeableness": 0.5,
}


def _make_tokens(scale=0.1):
    return [(t, [scale * (i + 1)] * 16) for i, t in enumerate(TOKEN_TYPES)]


class TestUtilities:
    def test_silu_zero(self):
        assert _silu(0.0) == 0.0

    def test_silu_positive(self):
        assert _silu(2.0) > 1.5

    def test_silu_negative_large(self):
        assert _silu(-100.0) == 0.0

    def test_softmax_uniform(self):
        result = _softmax([1.0, 1.0, 1.0])
        assert all(abs(r - 1/3) < 1e-6 for r in result)

    def test_softmax_sums_to_one(self):
        result = _softmax([0.5, 1.2, -0.3, 2.1])
        assert abs(sum(result) - 1.0) < 1e-6

    def test_rmsnorm_unit_gamma(self):
        vec = [3.0, 4.0]
        gamma = [1.0, 1.0]
        result = _rmsnorm(vec, gamma)
        rms = math.sqrt((9 + 16) / 2)
        assert abs(result[0] - 3.0 / rms) < 1e-6

    def test_vec_add(self):
        assert _vec_add([1, 2, 3], [4, 5, 6]) == [5, 7, 9]

    def test_matmul_identity(self):
        mat = [1, 0, 0, 1]
        vec = [3.0, 7.0]
        result = _matmul_vec_flat(mat, vec, 2, 2)
        assert abs(result[0] - 3.0) < 1e-9
        assert abs(result[1] - 7.0) < 1e-9


class TestTypeExpertFFN:
    def test_output_dimension(self):
        expert = TypeExpertFFN(16, 24)
        expert.derive(b"test_seed")
        x = [0.5] * 16
        out = expert.forward(x)
        assert len(out) == 16

    def test_independence(self):
        e1 = TypeExpertFFN(16, 24)
        e2 = TypeExpertFFN(16, 24)
        e1.derive(b"scar")
        e2.derive(b"void")
        x = [0.3] * 16
        assert e1.forward(x) != e2.forward(x)

    def test_residual_connection(self):
        expert = TypeExpertFFN(16, 24)
        expert.derive(b"test_residual")
        x = [0.0] * 16
        out = expert.forward(x)
        # With zero input, SiLU(0)=0, so FFN output is 0, residual = x + 0 = 0
        # After RMSNorm of zero vector... it should handle gracefully
        assert all(math.isfinite(v) for v in out)

    def test_each_type_has_own_expert(self):
        hgt = HeterogeneousGraphTransformer()
        hgt.derive_params(PERSONALITY)
        # Verify 7 distinct experts exist
        seeds = set()
        for e in hgt._type_experts:
            seeds.add(tuple(e.w1_flat[:4]))
        assert len(seeds) == 7


class TestMultiHeadAttention:
    def test_output_shape(self):
        attn = MultiHeadCrossAttention(16, 4)
        import hashlib
        seed = hashlib.sha256(b"test").digest()
        attn.derive(seed, PERSONALITY)
        tokens = [[0.1 * i] * 16 for i in range(7)]
        types = list(range(7))
        out, weights = attn.forward(tokens, types)
        assert len(out) == 7
        assert all(len(t) == 16 for t in out)
        assert len(weights) == 7
        assert all(len(w) == 7 for w in weights)

    def test_intra_type_mask(self):
        attn = MultiHeadCrossAttention(16, 4)
        import hashlib
        seed = hashlib.sha256(b"mask_test").digest()
        attn.derive(seed, PERSONALITY)
        tokens = [[0.5] * 16 for _ in range(7)]
        types = list(range(7))
        _, weights = attn.forward(tokens, types)
        for i in range(7):
            assert weights[i][i] < 0.01

    def test_multihead_splits(self):
        attn = MultiHeadCrossAttention(16, 4)
        import hashlib
        seed = hashlib.sha256(b"heads").digest()
        attn.derive(seed, PERSONALITY)
        tokens = [[float(i + j) * 0.1 for j in range(16)] for i in range(7)]
        types = list(range(7))
        out, _ = attn.forward(tokens, types)
        # Each head processes d_head=4 dims independently
        assert len(out[0]) == 16

    def test_kv_projection_used(self):
        attn = MultiHeadCrossAttention(16, 4)
        import hashlib
        seed = hashlib.sha256(b"kv_test").digest()
        attn.derive(seed, PERSONALITY)
        # Verify K and V projections exist per type per head
        for t_idx in range(7):
            assert len(attn._wk[t_idx]) == 4  # 4 heads
            assert len(attn._wk[t_idx][0]) == 16  # 4x4 flat
            assert any(v != 0.0 for v in attn._wk[t_idx][0])


class TestMoELayer:
    def test_router_top2(self):
        moe = MoELayer(16, 5)
        import hashlib
        moe.derive(hashlib.sha256(b"moe_test").digest() + b"MOE")
        pooled = [0.3] * 16
        out, active, gates = moe.forward(pooled)
        assert len(active) == 2
        assert active[0] != active[1]
        assert all(0 <= idx < 5 for idx in active)

    def test_sparse_activation(self):
        moe = MoELayer(16, 5)
        import hashlib
        moe.derive(hashlib.sha256(b"sparse").digest() + b"MOE")
        pooled = [0.2] * 16
        _, active, gates = moe.forward(pooled)
        # Only 2 of 5 experts are active
        assert len(active) == 2
        # Gate values sum to 1
        assert abs(sum(gates) - 1.0) < 1e-6

    def test_output_dimension(self):
        moe = MoELayer(16, 5)
        import hashlib
        moe.derive(hashlib.sha256(b"dim").digest() + b"MOE")
        pooled = [0.1 * i for i in range(16)]
        out, _, _ = moe.forward(pooled)
        assert len(out) == 16

    def test_router_bias_affects_selection(self):
        moe = MoELayer(16, 5)
        import hashlib
        moe.derive(hashlib.sha256(b"bias_test").digest() + b"MOE")
        pooled = [0.2] * 16
        _, active_no_bias, _ = moe.forward(pooled)
        bias = [0.0, 0.0, 0.0, 0.0, 5.0]  # Strongly favor expert 4
        _, active_biased, _ = moe.forward(pooled, router_bias=bias)
        assert 4 in active_biased


class TestHGTFull:
    def test_interface_compat(self):
        hgt = HeterogeneousGraphTransformer(d_model=16, n_heads=4, d_output=4)
        hgt.derive_params(PERSONALITY)
        tokens = _make_tokens()
        result = hgt.forward(tokens)
        assert len(result) == 4
        # d0, d1, d2 bounded by tanh [-1, 1]
        for i in range(3):
            assert -1.0 <= result[i] <= 1.0
        # d3 bounded by sigmoid [0, 1]
        assert 0.0 <= result[3] <= 1.0

    def test_forward_with_personality_arg(self):
        hgt = HeterogeneousGraphTransformer()
        tokens = _make_tokens()
        result = hgt.forward(tokens, PERSONALITY)
        assert len(result) == 4

    def test_empty_tokens(self):
        hgt = HeterogeneousGraphTransformer()
        hgt.derive_params(PERSONALITY)
        result = hgt.forward([])
        assert result == [0.0, 0.0, 0.0, 0.0]

    def test_deterministic(self):
        hgt1 = HeterogeneousGraphTransformer()
        hgt2 = HeterogeneousGraphTransformer()
        tokens = _make_tokens()
        r1 = hgt1.forward(tokens, PERSONALITY)
        r2 = hgt2.forward(tokens, PERSONALITY)
        assert r1 == r2

    def test_no_nan_inf(self):
        hgt = HeterogeneousGraphTransformer()
        hgt.derive_params(PERSONALITY)
        # Extreme inputs
        tokens = [(t, [100.0] * 16) for t in TOKEN_TYPES]
        result = hgt.forward(tokens)
        assert all(math.isfinite(v) for v in result)
        tokens_neg = [(t, [-100.0] * 16) for t in TOKEN_TYPES]
        result_neg = hgt.forward(tokens_neg)
        assert all(math.isfinite(v) for v in result_neg)

    def test_different_personality_different_output(self):
        hgt = HeterogeneousGraphTransformer()
        tokens = _make_tokens()
        r1 = hgt.forward(tokens, PERSONALITY)
        p2 = dict(PERSONALITY)
        p2["neuroticism"] = 0.9
        hgt._personality_cache = ""
        r2 = hgt.forward(tokens, p2)
        assert r1 != r2


class TestPlasticity:
    def test_derive_plasticity_high_openness(self):
        p = {"openness": 0.9, "conscientiousness": 0.2}
        assert _derive_plasticity(p) > 0.6

    def test_derive_plasticity_high_conscientiousness(self):
        p = {"openness": 0.2, "conscientiousness": 0.9}
        assert _derive_plasticity(p) < 0.3

    def test_derive_plasticity_bounds(self):
        p_max = {"openness": 1.0, "conscientiousness": 0.0}
        p_min = {"openness": 0.0, "conscientiousness": 1.0}
        assert 0.05 <= _derive_plasticity(p_max) <= 0.85
        assert 0.05 <= _derive_plasticity(p_min) <= 0.85


class TestSerialization:
    def test_to_dict_from_dict(self):
        hgt = HeterogeneousGraphTransformer()
        hgt.derive_params(PERSONALITY)
        tokens = _make_tokens()
        hgt.forward(tokens)
        hgt.adapt("accepted")
        hgt.adapt("accepted")

        state = hgt.to_dict()
        hgt2 = HeterogeneousGraphTransformer()
        hgt2.from_dict(state)

        s1 = hgt.adaptation_state()
        s2 = hgt2.adaptation_state()
        assert s1["router_bias"] == s2["router_bias"]
        assert s1["attention_drift"] == s2["attention_drift"]

    def test_adaptation_state_keys(self):
        hgt = HeterogeneousGraphTransformer()
        hgt.derive_params(PERSONALITY)
        hgt.forward(_make_tokens())
        state = hgt.adaptation_state()
        assert "router_bias" in state
        assert "attention_drift" in state
        assert "plasticity" in state
        assert "last_active_experts" in state
        assert "last_gate_values" in state
