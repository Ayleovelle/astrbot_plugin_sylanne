"""Numpy-accelerated implementations of HGT hot-path operations.

Used when backend="numpy" (pro/max mode). Falls back to pure-Python in lite mode.
All functions produce numerically equivalent results to the pure-Python path
(within float32 tolerance).
"""

from __future__ import annotations

try:
    import numpy as np

    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False


def numpy_multi_head_attention(
    tokens: list[list[float]],
    types: list[int],
    wq: list[list[list[float]]],
    wk: list[list[list[float]]],
    wv: list[list[list[float]]],
    n_heads: int,
    d_head: int,
    prior: list[list[float]],
    prior_drift: list[list[float]] | None,
    gamma: list[float],
) -> tuple[list[list[float]], list[list[float]]]:
    """Numpy-accelerated multi-head cross-attention.

    Args:
        tokens: list of token vectors, each [d_model] dim
        types: type index for each token
        wq/wk/wv: weight matrices [n_types][n_heads][d_head*d_head] flat
        n_heads: number of attention heads
        d_head: dimension per head
        prior: attention prior matrix [n_types x n_types]
        prior_drift: Oja adaptation drift (or None)
        gamma: RMSNorm gamma [d_model]

    Returns:
        (output tokens, attention weights matrix)
    """
    n = len(tokens)
    d_model = n_heads * d_head

    # Convert inputs to numpy arrays
    X = np.array(tokens, dtype=np.float64)  # [n, d_model]
    types_arr = np.array(types, dtype=np.int32)  # [n]
    gamma_arr = np.array(gamma, dtype=np.float64)  # [d_model]

    # Build combined prior+drift bias matrix
    prior_arr = np.array(prior, dtype=np.float64)  # [n_types, n_types]
    if prior_drift is not None:
        prior_arr = prior_arr + np.array(prior_drift, dtype=np.float64)

    # Precompute bias for each token pair from type-based prior
    # bias_matrix[i, j] = prior_arr[types[i], types[j]]
    bias_matrix = prior_arr[types_arr[:, None], types_arr[None, :]]  # [n, n]

    # Same-type mask: -inf where types[i] == types[j]
    same_type_mask = types_arr[:, None] == types_arr[None, :]  # [n, n] bool

    # Accumulate attention weights and head outputs
    attn_weights = np.zeros((n, n), dtype=np.float64)
    head_outputs = np.zeros((n, d_model), dtype=np.float64)
    scale = 1.0 / np.sqrt(float(d_head))
    inv_nh = 1.0 / n_heads

    # Precompute W matrices as numpy arrays indexed by type
    # wq[type_idx][head_idx] is a flat list of d_head*d_head floats
    n_types = len(wq)
    wq_np = np.array(wq, dtype=np.float64).reshape(n_types, n_heads, d_head, d_head)
    wk_np = np.array(wk, dtype=np.float64).reshape(n_types, n_heads, d_head, d_head)
    wv_np = np.array(wv, dtype=np.float64).reshape(n_types, n_heads, d_head, d_head)

    for h in range(n_heads):
        h_off = h * d_head
        x_slice = X[:, h_off : h_off + d_head]  # [n, d_head]

        # Compute Q, K, V for each token using its type-specific weight matrix
        Q = np.zeros((n, d_head), dtype=np.float64)
        K = np.zeros((n, d_head), dtype=np.float64)
        V = np.zeros((n, d_head), dtype=np.float64)

        # Group tokens by type for batched matmul
        for t_idx in range(n_types):
            mask = types_arr == t_idx
            if not np.any(mask):
                continue
            x_t = x_slice[mask]  # [count, d_head]
            Q[mask] = x_t @ wq_np[t_idx, h].T
            K[mask] = x_t @ wk_np[t_idx, h].T
            V[mask] = x_t @ wv_np[t_idx, h].T

        # Attention scores: Q @ K^T * scale + bias
        scores = (Q @ K.T) * scale + bias_matrix  # [n, n]

        # Apply same-type mask
        scores[same_type_mask] = -np.inf

        # Numerically stable softmax
        max_s = np.max(scores, axis=1, keepdims=True)  # [n, 1]
        exp_scores = np.exp(scores - max_s)
        sum_exp = np.sum(exp_scores, axis=1, keepdims=True) + 1e-12
        weights = exp_scores / sum_exp  # [n, n]

        # Accumulate attention weights (averaged over heads)
        attn_weights += weights * inv_nh

        # Weighted sum of values
        head_out = weights @ V  # [n, d_head]
        head_outputs[:, h_off : h_off + d_head] = head_out

    # Residual connection + RMSNorm
    output = X + head_outputs
    rms = np.sqrt(np.mean(output**2, axis=1, keepdims=True) + 1e-6)
    output = output / rms * gamma_arr[None, :]

    # Convert back to list of lists
    outputs_list = output.tolist()
    attn_list = attn_weights.tolist()
    return outputs_list, attn_list


def numpy_type_expert_forward(
    x: list[float],
    w1_flat: list[float],
    w2_flat: list[float],
    gamma: list[float],
    d_in: int,
    d_hidden: int,
) -> list[float]:
    """Numpy-accelerated TypeExpertFFN forward pass.

    Structure: x -> W1 -> SiLU -> W2 -> residual -> RMSNorm
    """
    x_arr = np.array(x, dtype=np.float64)
    w1 = np.array(w1_flat, dtype=np.float64).reshape(d_hidden, d_in)
    w2 = np.array(w2_flat, dtype=np.float64).reshape(d_in, d_hidden)
    gamma_arr = np.array(gamma, dtype=np.float64)

    # W1 @ x -> SiLU
    hidden = w1 @ x_arr
    # SiLU: x * sigmoid(x) with underflow protection
    sigmoid = np.where(hidden < -80.0, 0.0, 1.0 / (1.0 + np.exp(-hidden)))
    activated = hidden * sigmoid

    # W2 @ activated
    out = w2 @ activated

    # Residual + RMSNorm
    result = x_arr + out
    rms = np.sqrt(np.mean(result**2) + 1e-6)
    result = result / rms * gamma_arr

    return result.tolist()  # type: ignore[no-any-return]


def numpy_moe_forward(
    pooled: list[float],
    router_flat: list[float],
    expert_w1s: list[list[float]],
    expert_w2s: list[list[float]],
    n_experts: int,
    top_indices: list[int],
    weights: list[float],
    d_model: int,
    d_hidden: int,
    gamma: list[float],
) -> list[float]:
    """Numpy-accelerated MoE expert computation (after routing decision).

    This handles the weighted combination of expert outputs.
    Routing logic (dynamic k, dormancy, etc.) stays in pure Python.

    Args:
        pooled: pooled input vector [d_model]
        router_flat: not used here (routing already done)
        expert_w1s: list of W1 flat weights for each selected expert
        expert_w2s: list of W2 flat weights for each selected expert
        n_experts: total number of experts (unused, for API compat)
        top_indices: indices of selected experts (unused, for reference)
        weights: normalized gate weights for selected experts
        d_model: model dimension
        d_hidden: hidden dimension of experts
        gamma: RMSNorm gamma

    Returns:
        MoE output vector [d_model]
    """
    x_arr = np.array(pooled, dtype=np.float64)
    gamma_arr = np.array(gamma, dtype=np.float64)

    # Start with residual
    result = x_arr.copy()

    # Compute weighted expert outputs
    for rank, idx in enumerate(top_indices):
        w1 = np.array(expert_w1s[rank], dtype=np.float64).reshape(d_hidden, d_model)
        w2 = np.array(expert_w2s[rank], dtype=np.float64).reshape(d_model, d_hidden)

        # Expert forward: W1 -> SiLU -> W2
        hidden = w1 @ x_arr
        sigmoid = np.where(hidden < -80.0, 0.0, 1.0 / (1.0 + np.exp(-hidden)))
        activated = hidden * sigmoid
        e_out = w2 @ activated

        result += weights[rank] * e_out

    # RMSNorm
    rms = np.sqrt(np.mean(result**2) + 1e-6)
    result = result / rms * gamma_arr

    return result.tolist()  # type: ignore[no-any-return]
