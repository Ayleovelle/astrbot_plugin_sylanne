"""MLP vs tanh base state evolution comparison experiment.

Compares the original tanh(A*x + B*e) evolution with the new 2-layer
spectrally-normalized MLP evolution across 1000 conversation rounds.

Metrics:
- Convergence speed (ticks to reach equilibrium)
- Final state difference (L2 distance between final states)
- Expressiveness (number of distinguishable states produced)

Output: matplotlib figures saved to experiments/figures/
"""
from __future__ import annotations

import math
import os
import random
import sys
from dataclasses import dataclass

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass
class ExperimentConfig:
    n_dims: int = 8
    n_rounds: int = 1000
    wound_threshold: float = 0.6
    seed: int = 42
    convergence_epsilon: float = 1e-4


def tanh_linear_evolve(x: list[float], e_tilde: list[float],
                       A: list[list[float]], B: list[list[float]]) -> list[float]:
    """Original evolution: x' = tanh(A*x + B*e_tilde)."""
    n = len(x)
    result = [0.0] * n
    for i in range(n):
        val = sum(A[i][j] * x[j] for j in range(n))
        val += sum(B[i][j] * e_tilde[j] for j in range(n))
        result[i] = math.tanh(val)
    return result


def mlp_evolve(x: list[float], e_tilde: list[float],
               W1: list[list[float]], W2: list[list[float]]) -> list[float]:
    """New evolution: 2-layer MLP with spectral normalization.

    Layer 1: hidden = tanh(W1 * [x; e_tilde])
    Layer 2: output = tanh(W2 * hidden)
    """
    inp = list(x) + list(e_tilde)
    hidden_dim = len(W1)
    out_dim = len(W2)

    # Layer 1
    hidden = [0.0] * hidden_dim
    for i in range(hidden_dim):
        val = sum(W1[i][j] * inp[j] for j in range(len(inp)))
        hidden[i] = math.tanh(val)

    # Layer 2
    output = [0.0] * out_dim
    for i in range(out_dim):
        val = sum(W2[i][j] * hidden[j] for j in range(hidden_dim))
        output[i] = math.tanh(val)

    return output
def spectral_normalize(W: list[list[float]], max_sigma: float = 0.7) -> list[list[float]]:
    """Spectral normalization via power iteration."""
    rows = len(W)
    cols = len(W[0]) if rows > 0 else 0
    if rows == 0 or cols == 0:
        return W

    u = [1.0 / math.sqrt(rows)] * rows
    v = [0.0] * cols

    for _ in range(10):
        for j in range(cols):
            v[j] = sum(W[i][j] * u[i] for i in range(rows))
        v_norm = math.sqrt(sum(x * x for x in v)) + 1e-12
        v = [x / v_norm for x in v]

        for i in range(rows):
            u[i] = sum(W[i][j] * v[j] for j in range(cols))
        u_norm = math.sqrt(sum(x * x for x in u)) + 1e-12
        u = [x / u_norm for x in u]

    sigma = sum(u[i] * sum(W[i][j] * v[j] for j in range(cols)) for i in range(rows))

    if sigma > max_sigma:
        scale = max_sigma / sigma
        return [[W[i][j] * scale for j in range(cols)] for i in range(rows)]
    return W


def generate_weights_linear(n_dims: int, seed: int = 42):
    """Generate A, B matrices for linear evolution (||A||_2 < 1)."""
    rng = random.Random(seed)
    A = [[rng.gauss(0, 0.3) for _ in range(n_dims)] for _ in range(n_dims)]
    B = [[rng.gauss(0, 0.2) for _ in range(n_dims)] for _ in range(n_dims)]
    A = spectral_normalize(A, max_sigma=0.8)
    return A, B


def generate_weights_mlp(n_dims: int, hidden_dim: int = 12, seed: int = 42):
    """Generate W1, W2 for MLP evolution with spectral normalization."""
    rng = random.Random(seed)
    input_dim = n_dims * 2
    W1 = [[rng.gauss(0, 0.5) for _ in range(input_dim)] for _ in range(hidden_dim)]
    W2 = [[rng.gauss(0, 0.5) for _ in range(hidden_dim)] for _ in range(n_dims)]
    W1 = spectral_normalize(W1, max_sigma=0.7)
    W2 = spectral_normalize(W2, max_sigma=0.7)
    return W1, W2


def generate_conversation_events(n_rounds: int, n_dims: int, seed: int = 42) -> list[list[float]]:
    """Generate synthetic conversation events (varied emotional inputs)."""
    rng = random.Random(seed)
    events = []
    for t in range(n_rounds):
        # Mix of calm and intense events
        if rng.random() < 0.2:  # 20% intense events
            event = [rng.gauss(0, 0.8) for _ in range(n_dims)]
        elif rng.random() < 0.1:  # 10% wounding events
            event = [rng.gauss(0, 0.3) for _ in range(n_dims)]
            dim = rng.randint(0, n_dims - 1)
            event[dim] = rng.choice([-1.0, 1.0]) * rng.uniform(0.7, 1.0)
        else:  # 70% normal events
            event = [rng.gauss(0, 0.3) for _ in range(n_dims)]
        events.append(event)
    return events


def l2_distance(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((ai - bi) ** 2 for ai, bi in zip(a, b)))


def run_experiment(cfg: ExperimentConfig):
    """Run the full comparison experiment."""
    print(f"Running MLP vs tanh comparison: {cfg.n_rounds} rounds, {cfg.n_dims} dims")

    # Generate weights
    A, B = generate_weights_linear(cfg.n_dims, cfg.seed)
    W1, W2 = generate_weights_mlp(cfg.n_dims, hidden_dim=12, seed=cfg.seed)

    # Generate events
    events = generate_conversation_events(cfg.n_rounds, cfg.n_dims, cfg.seed)

    # Run both systems
    x_linear = [0.0] * cfg.n_dims
    x_mlp = [0.0] * cfg.n_dims

    history_linear: list[list[float]] = []
    history_mlp: list[list[float]] = []
    convergence_linear: list[float] = []
    convergence_mlp: list[float] = []

    for t in range(cfg.n_rounds):
        e = events[t]

        # Linear evolution
        x_linear_new = tanh_linear_evolve(x_linear, e, A, B)
        delta_linear = l2_distance(x_linear_new, x_linear)
        convergence_linear.append(delta_linear)
        x_linear = x_linear_new
        history_linear.append(list(x_linear))

        # MLP evolution
        x_mlp_new = mlp_evolve(x_mlp, e, W1, W2)
        delta_mlp = l2_distance(x_mlp_new, x_mlp)
        convergence_mlp.append(delta_mlp)
        x_mlp = x_mlp_new
        history_mlp.append(list(x_mlp))

    # Compute metrics
    # 1. Convergence speed: first tick where delta < epsilon for 10 consecutive ticks
    def find_convergence_tick(deltas, eps, window=10):
        for i in range(len(deltas) - window):
            if all(d < eps for d in deltas[i:i + window]):
                return i
        return len(deltas)  # Never converged

    conv_tick_linear = find_convergence_tick(convergence_linear, cfg.convergence_epsilon)
    conv_tick_mlp = find_convergence_tick(convergence_mlp, cfg.convergence_epsilon)

    # 2. Final state difference
    final_diff = l2_distance(x_linear, x_mlp)

    # 3. Expressiveness: count distinguishable states (quantize to grid)
    def count_distinct_states(history, resolution=0.05):
        seen = set()
        for state in history:
            quantized = tuple(round(v / resolution) * resolution for v in state)
            seen.add(quantized)
        return len(seen)

    distinct_linear = count_distinct_states(history_linear)
    distinct_mlp = count_distinct_states(history_mlp)

    print(f"\n{'='*60}")
    print(f"RESULTS ({cfg.n_rounds} rounds)")
    print(f"{'='*60}")
    print(f"Convergence speed (ticks to equilibrium):")
    print(f"  Linear tanh:  {conv_tick_linear}")
    print(f"  MLP (SN):     {conv_tick_mlp}")
    print(f"\nFinal state L2 distance between methods: {final_diff:.6f}")
    print(f"\nExpressiveness (distinct states visited):")
    print(f"  Linear tanh:  {distinct_linear}")
    print(f"  MLP (SN):     {distinct_mlp}")
    print(f"  Ratio (MLP/Linear): {distinct_mlp / max(1, distinct_linear):.2f}x")
    print(f"\nFinal states:")
    print(f"  Linear: {[round(v, 4) for v in x_linear]}")
    print(f"  MLP:    {[round(v, 4) for v in x_mlp]}")

    return {
        "convergence_linear": convergence_linear,
        "convergence_mlp": convergence_mlp,
        "history_linear": history_linear,
        "history_mlp": history_mlp,
        "conv_tick_linear": conv_tick_linear,
        "conv_tick_mlp": conv_tick_mlp,
        "final_diff": final_diff,
        "distinct_linear": distinct_linear,
        "distinct_mlp": distinct_mlp,
    }
def plot_results(results: dict, output_dir: str):
    """Generate comparison plots."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print("[WARN] matplotlib not available, skipping plots")
        return

    os.makedirs(output_dir, exist_ok=True)

    # Plot 1: Convergence speed (delta over time)
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    ax = axes[0, 0]
    ax.semilogy(results["convergence_linear"], alpha=0.7, label="Linear tanh", linewidth=0.8)
    ax.semilogy(results["convergence_mlp"], alpha=0.7, label="MLP (SN)", linewidth=0.8)
    ax.axhline(y=1e-4, color='r', linestyle='--', alpha=0.5, label="Convergence threshold")
    ax.set_xlabel("Tick")
    ax.set_ylabel("State delta (L2)")
    ax.set_title("Convergence Speed Comparison")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Plot 2: State trajectories (dim 0 and dim 3)
    ax = axes[0, 1]
    linear_d0 = [h[0] for h in results["history_linear"]]
    mlp_d0 = [h[0] for h in results["history_mlp"]]
    linear_d3 = [h[3] for h in results["history_linear"]]
    mlp_d3 = [h[3] for h in results["history_mlp"]]
    ax.plot(linear_d0, alpha=0.7, label="Linear dim0", linewidth=0.8)
    ax.plot(mlp_d0, alpha=0.7, label="MLP dim0", linewidth=0.8)
    ax.plot(linear_d3, alpha=0.5, label="Linear dim3", linewidth=0.8, linestyle='--')
    ax.plot(mlp_d3, alpha=0.5, label="MLP dim3", linewidth=0.8, linestyle='--')
    ax.set_xlabel("Tick")
    ax.set_ylabel("State value")
    ax.set_title("State Trajectories (dims 0, 3)")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # Plot 3: Expressiveness - state space coverage (2D projection)
    ax = axes[1, 0]
    linear_proj = [(h[0], h[1]) for h in results["history_linear"]]
    mlp_proj = [(h[0], h[1]) for h in results["history_mlp"]]
    ax.scatter([p[0] for p in linear_proj], [p[1] for p in linear_proj],
               alpha=0.3, s=5, label=f"Linear ({results['distinct_linear']} states)")
    ax.scatter([p[0] for p in mlp_proj], [p[1] for p in mlp_proj],
               alpha=0.3, s=5, label=f"MLP ({results['distinct_mlp']} states)")
    ax.set_xlabel("Dim 0")
    ax.set_ylabel("Dim 1")
    ax.set_title("State Space Coverage (2D projection)")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Plot 4: Summary bar chart
    ax = axes[1, 1]
    metrics = ["Conv. Speed\n(lower=faster)", "Distinct States\n(higher=better)"]
    linear_vals = [results["conv_tick_linear"], results["distinct_linear"]]
    mlp_vals = [results["conv_tick_mlp"], results["distinct_mlp"]]
    x = range(len(metrics))
    width = 0.35
    bars1 = ax.bar([i - width/2 for i in x], linear_vals, width, label="Linear tanh", color='#4C72B0')
    bars2 = ax.bar([i + width/2 for i in x], mlp_vals, width, label="MLP (SN)", color='#DD8452')
    ax.set_xticks(list(x))
    ax.set_xticklabels(metrics)
    ax.set_title("Summary Comparison")
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    # Add value labels on bars
    for bar in bars1:
        ax.annotate(f'{int(bar.get_height())}',
                    xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                    xytext=(0, 3), textcoords="offset points",
                    ha='center', va='bottom', fontsize=9)
    for bar in bars2:
        ax.annotate(f'{int(bar.get_height())}',
                    xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                    xytext=(0, 3), textcoords="offset points",
                    ha='center', va='bottom', fontsize=9)

    plt.tight_layout()
    fig_path = os.path.join(output_dir, "mlp_vs_tanh_comparison.png")
    plt.savefig(fig_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"\nFigure saved to: {fig_path}")


if __name__ == "__main__":
    cfg = ExperimentConfig()
    results = run_experiment(cfg)

    fig_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")
    plot_results(results, fig_dir)
    print("\nExperiment complete.")
