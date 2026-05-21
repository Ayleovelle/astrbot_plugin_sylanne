"""Relational Sheaf Theory — Experiments 7, 8, 9.

Validates three core predictions of the Relational Sheaf Theory:
  7. Cohomological Dissociation Detection — H^1 grows under contradictions
  8. Spectral Propagation Verification — exponential decay with distance
  9. Triadic Irreducibility — co-presence effects cannot be reduced to dyads

Output: matplotlib figures saved to docs/experiments/
"""
from __future__ import annotations

import copy
import math
import os
import random
import sys
from typing import Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sylanne_alpha.relational_sheaf import (
    ScarSheaf,
    _vec_norm,
    _vec_sub,
    _EDGE_STALK_DIM,
)

# ---------------------------------------------------------------------------
# Common setup
# ---------------------------------------------------------------------------

PERSONALITY = {
    "openness": 0.7,
    "conscientiousness": 0.5,
    "extraversion": 0.6,
    "agreeableness": 0.8,
    "neuroticism": 0.4,
}

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs", "experiments",
)


def setup_matplotlib():
    """Configure matplotlib for academic-quality output."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    try:
        plt.style.use("seaborn-v0_8-whitegrid")
    except OSError:
        plt.rcParams.update({
            "axes.grid": True,
            "grid.alpha": 0.3,
            "figure.facecolor": "white",
        })
    plt.rcParams.update({
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.labelsize": 11,
        "legend.fontsize": 9,
        "figure.dpi": 100,
    })
    return plt


# ===========================================================================
# Experiment 7: Cohomological Dissociation Detection
# ===========================================================================

def experiment_7_cohomological_dissociation():
    """Feed conflicting events to intimate vs adversarial relationships.

    Prediction: H^1 grows as contradictions accumulate, then plateaus
    when the presentation matrices can no longer reconcile the divergence.
    """
    print("=" * 60)
    print("Experiment 7: Cohomological Dissociation Detection")
    print("=" * 60)

    sheaf = ScarSheaf(n0=8, max_energy=50.0)
    sheaf.derive_params(PERSONALITY)

    # 3 relationships: intimate (1), friendly (2), adversarial (3)
    sheaf.add_relationship(1, rel_type="intimate")
    sheaf.add_relationship(2, rel_type="friendly")
    sheaf.add_relationship(3, rel_type="adversarial")

    # Add triangles so H^1 computation uses the full ker(d1)/im(d0) formula
    sheaf.complex.add_triangle(1, 2)
    sheaf.complex.add_triangle(1, 3)
    sheaf.complex.add_triangle(2, 3)
    while len(sheaf._triangle_stalks) < sheaf.complex.n_triangles:
        sheaf._triangle_stalks.append([0.0] * 4)

    n_ticks = 100
    h1_history = []
    dissoc_history = []
    inconsistency_history = []
    tick_indices = []

    rng = random.Random(42)

    for t in range(n_ticks):
        timestamp = 1000.0 + t * 1.0

        # Warmth event to intimate (positive on dims 0-3)
        warmth = [0.3 + rng.gauss(0, 0.05)] * 4 + [0.0] * 4
        sheaf.tick(0, warmth, timestamp=timestamp)

        # Hostility event to adversarial (negative on dims 0-3)
        hostility = [-0.3 + rng.gauss(0, 0.05)] * 4 + [0.0] * 4
        sheaf.tick(2, hostility, timestamp=timestamp + 0.5)

        # Observe after both events
        obs = sheaf.observe()
        h1_history.append(obs["h1_dim"])
        dissoc_history.append(obs["dissociation_pressure"])
        # Total inconsistency as a continuous proxy for cohomological tension
        incon = obs["inconsistency_per_edge"]
        inconsistency_history.append(sum(x for x in incon))
        tick_indices.append(t)

    print(f"  Final H^1 dimension: {h1_history[-1]}")
    print(f"  Final dissociation pressure: {dissoc_history[-1]:.4f}")
    print(f"  Max H^1 reached: {max(h1_history)}")
    print(f"  Final total inconsistency: {inconsistency_history[-1]:.4f}")
    # Plot
    plt = setup_matplotlib()
    fig, ax1 = plt.subplots(figsize=(10, 6))

    color_h1 = "#2C3E50"
    color_dp = "#E74C3C"
    color_incon = "#8E44AD"

    ax1.set_xlabel("Tick")
    ax1.set_ylabel("H$^1$ Dim / Inconsistency", color=color_h1)
    ax1.plot(tick_indices, h1_history, color=color_h1, linewidth=2.0,
             label="H$^1$ dim (irreducible contradictions)")
    ax1.plot(tick_indices, inconsistency_history, color=color_incon, linewidth=1.5,
             alpha=0.8, label="Total inconsistency (continuous)")
    ax1.tick_params(axis="y", labelcolor=color_h1)
    ax1.set_ylim(bottom=0)

    ax2 = ax1.twinx()
    ax2.set_ylabel("Dissociation Pressure", color=color_dp)
    ax2.plot(tick_indices, dissoc_history, color=color_dp, linewidth=1.5,
             linestyle="--", alpha=0.8, label="Dissociation pressure")
    ax2.tick_params(axis="y", labelcolor=color_dp)
    ax2.set_ylim(0, 1)

    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

    ax1.set_title("Experiment 7: Cohomological Dissociation Detection\n"
                  "(Conflicting warmth/hostility events across relationships)")
    plt.tight_layout()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    fig_path = os.path.join(OUTPUT_DIR, "fig7_cohomological_dissociation.png")
    plt.savefig(fig_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  Figure saved: {fig_path}")
    return h1_history, dissoc_history, inconsistency_history


# ===========================================================================
# Experiment 8: Spectral Propagation Verification
# ===========================================================================

def experiment_8_spectral_propagation():
    """Single large scar event on relationship 0, observe propagation to 1-4.

    Prediction: Perturbation decays exponentially with combinatorial distance,
    rate governed by spectral gap lambda_1.
    """
    print("\n" + "=" * 60)
    print("Experiment 8: Spectral Propagation Verification")
    print("=" * 60)

    # 5 relationships in a chain with triangles connecting adjacent pairs
    sheaf = ScarSheaf(n0=8, max_energy=100.0, propagation_rate=0.15)
    sheaf.derive_params(PERSONALITY)

    # Add 5 relationships (partners 1..5)
    for i in range(1, 6):
        sheaf.add_relationship(i, rel_type="friendly", maturity=0.3)

    # Add triangles between adjacent pairs: (0,1,2), (0,2,3), (0,3,4), (0,4,5)
    for i in range(1, 5):
        sheaf.complex.add_triangle(i, i + 1)
    # Ensure triangle stalks are sized
    while len(sheaf._triangle_stalks) < sheaf.complex.n_triangles:
        sheaf._triangle_stalks.append([0.0] * 4)

    # Record baseline edge stalks
    baseline_stalks = [list(s) for s in sheaf._edge_stalks]

    # Inject a large scar event on relationship 0 (edge index 0)
    scar_event = [0.8, 0.6, -0.5, 0.7, 0.3, -0.4, 0.2, 0.5]

    n_ticks = 50
    # Track perturbation magnitude at each relationship over time
    perturbations = {i: [] for i in range(5)}  # edge indices 0..4
    for t in range(n_ticks):
        timestamp = 1000.0 + t * 1.0
        if t == 0:
            # First tick: inject the scar event on edge 0
            sheaf.tick(0, scar_event, timestamp=timestamp)
        else:
            # Subsequent ticks: neutral events on edge 0 to allow propagation
            sheaf.tick(0, [0.0] * 8, timestamp=timestamp)

        # Measure perturbation at each edge relative to baseline
        for edge_idx in range(5):
            if edge_idx < len(sheaf._edge_stalks):
                diff = _vec_sub(sheaf._edge_stalks[edge_idx], baseline_stalks[edge_idx])
                perturbations[edge_idx].append(_vec_norm(diff))
            else:
                perturbations[edge_idx].append(0.0)

    # Compute spectral gap for theoretical bound
    gap = sheaf.spectral_gap()
    alpha = sheaf._propagation_rate
    print(f"  Spectral gap (lambda_1/lambda_max): {gap:.6f}")
    print(f"  Propagation rate alpha: {alpha:.4f}")
    for i in range(5):
        print(f"  Edge {i} final perturbation: {perturbations[i][-1]:.6f}")

    # Plot
    plt = setup_matplotlib()
    fig, ax = plt.subplots(figsize=(10, 6))

    colors = ["#E74C3C", "#E67E22", "#F1C40F", "#27AE60", "#2980B9"]
    labels = ["Rel 0 (source)", "Rel 1 (dist=2)", "Rel 2 (dist=4)",
              "Rel 3 (dist=6)", "Rel 4 (dist=8)"]

    for i in range(5):
        ax.plot(range(n_ticks), perturbations[i], color=colors[i],
                linewidth=2.0, label=labels[i])

    # Theoretical exponential decay bound: A * exp(-lambda_1 * distance * t)
    # distance is combinatorial: 2 hops per edge separation
    if gap > 0:
        t_range = list(range(n_ticks))
        peak_perturbation = max(perturbations[0]) if perturbations[0] else 1.0
        for dist_idx in range(1, 5):
            distance = dist_idx * 2  # combinatorial distance
            theoretical = [
                peak_perturbation * math.exp(-gap * alpha * distance * (t + 1))
                for t in t_range
            ]
            ax.plot(t_range, theoretical, color=colors[dist_idx],
                    linestyle=":", linewidth=1.0, alpha=0.6)
        # Add one dashed line to legend
        ax.plot([], [], color="gray", linestyle=":", linewidth=1.0,
                label="Theoretical bound (exp decay)")

    ax.set_xlabel("Tick")
    ax.set_ylabel("Perturbation Magnitude (L2 norm)")
    ax.set_title("Experiment 8: Spectral Propagation Verification\n"
                 "(Single scar event propagating through relationship chain)")
    ax.legend(loc="upper right")
    ax.set_ylim(bottom=0)

    fig_path = os.path.join(OUTPUT_DIR, "fig8_spectral_propagation.png")
    plt.savefig(fig_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  Figure saved: {fig_path}")
    return perturbations, gap


# ===========================================================================
# Experiment 9: Triadic Irreducibility
# ===========================================================================
def experiment_9_triadic_irreducibility():
    """Compare dyadic-only vs triadic (co-presence) evolution.

    Prediction: The triadic system produces states that cannot be explained
    as the sum of pairwise interactions — a non-zero irreducible residual.
    """
    print("\n" + "=" * 60)
    print("Experiment 9: Triadic Irreducibility")
    print("=" * 60)

    n_seeds = 10
    n_ticks = 50
    n_dims = _EDGE_STALK_DIM

    residuals_per_dim = [[] for _ in range(n_dims)]

    for seed in range(n_seeds):
        rng = random.Random(seed)

        # Generate random events for 3 relationships
        events = []
        for _ in range(n_ticks):
            ev = [[rng.gauss(0, 0.3) for _ in range(n_dims)] for _ in range(3)]
            events.append(ev)

        # --- Dyadic mode: run each relationship independently ---
        dyadic_final_stalks = []
        for rel_idx in range(3):
            sheaf_d = ScarSheaf(n0=8, max_energy=100.0)
            sheaf_d.derive_params(PERSONALITY)
            # Only add the one relationship
            sheaf_d.add_relationship(rel_idx + 1, rel_type="friendly", maturity=0.3)
            for t in range(n_ticks):
                sheaf_d.tick(0, events[t][rel_idx], timestamp=1000.0 + t)
            dyadic_final_stalks.append(list(sheaf_d._edge_stalks[0]))

        # Sum of dyadic vertex stalks (superposition hypothesis)
        dyadic_vertex_sum = [0.0] * 8
        for rel_idx in range(3):
            sheaf_d = ScarSheaf(n0=8, max_energy=100.0)
            sheaf_d.derive_params(PERSONALITY)
            sheaf_d.add_relationship(rel_idx + 1, rel_type="friendly", maturity=0.3)
            for t in range(n_ticks):
                sheaf_d.tick(0, events[t][rel_idx], timestamp=1000.0 + t)
            for d in range(8):
                dyadic_vertex_sum[d] += sheaf_d._vertex_stalk[d]

        # --- Triadic mode: all 3 relationships with triangle ---
        sheaf_t = ScarSheaf(n0=8, max_energy=100.0)
        sheaf_t.derive_params(PERSONALITY)
        sheaf_t.add_relationship(1, rel_type="friendly", maturity=0.3)
        sheaf_t.add_relationship(2, rel_type="friendly", maturity=0.3)
        sheaf_t.add_relationship(3, rel_type="friendly", maturity=0.3)
        # Add triangle (co-presence of all three)
        sheaf_t.complex.add_triangle(1, 2)
        sheaf_t.complex.add_triangle(1, 3)
        sheaf_t.complex.add_triangle(2, 3)
        while len(sheaf_t._triangle_stalks) < sheaf_t.complex.n_triangles:
            sheaf_t._triangle_stalks.append([0.0] * 4)
        for t in range(n_ticks):
            # Feed events to all 3 relationships each tick
            for rel_idx in range(3):
                sheaf_t.tick(rel_idx, events[t][rel_idx], timestamp=1000.0 + t + rel_idx * 0.1)

        triadic_vertex = list(sheaf_t._vertex_stalk)

        # Compute residual: triadic - sum(dyadic)
        for d in range(min(n_dims, 8)):
            residual = abs(triadic_vertex[d] - dyadic_vertex_sum[d])
            residuals_per_dim[d].append(residual)

    # Compute mean and std for each dimension
    means = []
    stds = []
    for d in range(n_dims):
        vals = residuals_per_dim[d]
        m = sum(vals) / len(vals) if vals else 0.0
        means.append(m)
        var = sum((v - m) ** 2 for v in vals) / max(1, len(vals) - 1)
        stds.append(math.sqrt(var))

    print(f"  Residual (triadic - sum(dyadic)) per dimension:")
    for d in range(n_dims):
        print(f"    Dim {d}: mean={means[d]:.6f}, std={stds[d]:.6f}")
    total_residual = sum(means)
    print(f"  Total residual (sum of means): {total_residual:.6f}")
    print(f"  Non-zero dims (mean > 0.01): {sum(1 for m in means if m > 0.01)}/{n_dims}")

    # Plot
    plt = setup_matplotlib()
    fig, ax = plt.subplots(figsize=(10, 6))

    x_pos = list(range(n_dims))
    bars = ax.bar(x_pos, means, yerr=stds, capsize=4,
                  color="#3498DB", edgecolor="#2C3E50", alpha=0.8,
                  error_kw={"linewidth": 1.5, "color": "#2C3E50"})

    # Highlight dimensions with significant residual
    for i, (m, bar) in enumerate(zip(means, bars)):
        if m > 0.01:
            bar.set_color("#E74C3C")
            bar.set_alpha(0.9)

    ax.axhline(y=0.01, color="#95A5A6", linestyle="--", linewidth=1.0,
               label="Significance threshold (0.01)")
    ax.set_xlabel("State Dimension")
    ax.set_ylabel("Residual |triadic - sum(dyadic)|")
    ax.set_title("Experiment 9: Triadic Irreducibility\n"
                 "(Red = dimensions where co-presence creates irreducible effects)")
    ax.set_xticks(x_pos)
    ax.set_xticklabels([f"d{i}" for i in range(n_dims)])
    ax.legend(loc="upper right")

    # Annotate total
    ax.text(0.98, 0.85, f"Total residual: {total_residual:.4f}\n"
            f"Non-zero dims: {sum(1 for m in means if m > 0.01)}/{n_dims}\n"
            f"Seeds: {n_seeds}",
            transform=ax.transAxes, ha="right", va="top",
            fontsize=9, bbox=dict(boxstyle="round,pad=0.3",
                                  facecolor="wheat", alpha=0.5))

    fig_path = os.path.join(OUTPUT_DIR, "fig9_triadic_irreducibility.png")
    plt.savefig(fig_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  Figure saved: {fig_path}")
    return means, stds


# ===========================================================================
# Main
# ===========================================================================

if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("Relational Sheaf Theory — Experiments 7, 8, 9")
    print(f"Output directory: {OUTPUT_DIR}\n")

    experiment_7_cohomological_dissociation()
    experiment_8_spectral_propagation()
    experiment_9_triadic_irreducibility()

    print("\n" + "=" * 60)
    print("All experiments complete. Figures saved to docs/experiments/")
    print("=" * 60)
