"""
Experiment 11: Personality Feedback Loop Verification

Simulates personality drift under three conditions using the Big Five
personality model with scar/void/feedback-driven dynamics.

Generates: docs/experiments/fig10_personality_feedback.png
"""

import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

# ─── Parameters ───────────────────────────────────────────────────────────────

RNG = np.random.default_rng(42)
ETA = 0.0001  # base drift rate
K_STAR = 1.0  # scar normalization constant
DIM_LABELS = ["O", "C", "E", "A", "N"]
DIM_COLORS = ["#1f77b4", "#2ca02c", "#ff7f0e", "#9467bd", "#d62728"]


def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


# ─── Scenario A: Repeated Wounding ────────────────────────────────────────────

def simulate_wounding(ticks=500):
    """
    Repeated wounding increases scar density over time.
    N rises as neuroticism responds to accumulated scars.
    O drops as high-pressure void fraction grows under sustained damage.
    """
    pi = np.full((ticks, 5), 0.5)  # O, C, E, A, N

    # Simulate scar density accumulating with noise
    scar_density = np.zeros(ticks)
    void_pressure = np.zeros(ticks)

    for t in range(1, ticks):
        # Scar accumulates with some stochastic wounding events
        wound_event = RNG.random() < 0.7  # 70% chance of wound per tick
        scar_increment = RNG.exponential(0.003) if wound_event else 0.0
        scar_density[t] = scar_density[t - 1] + scar_increment

        # Void pressure grows as scars accumulate (nonlinear)
        void_pressure[t] = 0.3 * np.tanh(scar_density[t] / 2.0) + RNG.normal(0, 0.005)

        # Drift N upward: eta * max(0, scar_density/k_star - 0.5)
        n_drive = ETA * max(0, scar_density[t] / K_STAR - 0.5)
        # Add boundary penetration modifier (increases with damage)
        eta_mod = min(1.0, scar_density[t] / 1.5)
        n_drive *= (1.0 + eta_mod)

        # Drift O downward: eta * high_pressure_void_fraction
        o_drive = -ETA * max(0, void_pressure[t])

        # Copy previous state
        pi[t] = pi[t - 1].copy()

        # Apply drifts with small noise
        pi[t, 4] = clamp(pi[t, 4] + n_drive + RNG.normal(0, 0.0003))  # N
        pi[t, 0] = clamp(pi[t, 0] + o_drive + RNG.normal(0, 0.0002))  # O

        # Minor sympathetic drift on other dimensions
        pi[t, 1] += RNG.normal(0, 0.0001)  # C slight noise
        pi[t, 2] += RNG.normal(0, 0.0001)  # E slight noise
        pi[t, 3] += RNG.normal(0, 0.0001)  # A slight noise
        pi[t, 1:4] = np.clip(pi[t, 1:4], 0, 1)

    return pi


# ─── Scenario B: Sustained Acceptance ─────────────────────────────────────────

def simulate_acceptance(ticks=500):
    """
    Sustained acceptance drives E and A upward.
    E responds to (accept_rate - ignore_rate).
    A responds to (coherence - 0.5).
    """
    pi = np.full((ticks, 5), 0.5)

    for t in range(1, ticks):
        # Acceptance rate: high baseline with fluctuation
        accept_rate = 0.75 + RNG.normal(0, 0.05)
        ignore_rate = 0.15 + RNG.normal(0, 0.03)

        # Coherence builds over time (logistic growth)
        coherence = 0.5 + 0.35 * (1 - np.exp(-t / 200.0)) + RNG.normal(0, 0.01)

        # E drift: eta * (accept_rate - ignore_rate)
        e_drive = ETA * max(0, accept_rate - ignore_rate)
        # Amplify slightly as relationship stabilizes
        e_drive *= (1.0 + 0.3 * np.tanh(t / 300.0))

        # A drift: eta * (coherence - 0.5)
        a_drive = ETA * max(0, coherence - 0.5)

        pi[t] = pi[t - 1].copy()
        pi[t, 2] = clamp(pi[t, 2] + e_drive + RNG.normal(0, 0.0002))  # E
        pi[t, 3] = clamp(pi[t, 3] + a_drive + RNG.normal(0, 0.0002))  # A

        # Other dims: minor noise only
        pi[t, 0] += RNG.normal(0, 0.0001)
        pi[t, 1] += RNG.normal(0, 0.0001)
        pi[t, 4] += RNG.normal(0, 0.0001)
        pi[t, [0, 1, 4]] = np.clip(pi[t, [0, 1, 4]], 0, 1)

    return pi


# ─── Scenario C: Cross-Relational Contradiction ───────────────────────────────

def simulate_contradiction(ticks=200):
    """
    Cross-relational contradiction builds dissociation pressure,
    which erodes Conscientiousness.
    """
    pi = np.full((ticks, 5), 0.5)
    dissociation_pressure = np.zeros(ticks)

    for t in range(1, ticks):
        # Dissociation pressure grows as contradictions accumulate
        contradiction_event = RNG.random() < 0.8
        pressure_inc = RNG.exponential(0.008) if contradiction_event else 0.001
        dissociation_pressure[t] = dissociation_pressure[t - 1] + pressure_inc

        # C drift: -eta * dissociation_pressure
        c_drive = -ETA * dissociation_pressure[t]
        # Accelerate as pressure mounts (positive feedback)
        c_drive *= (1.0 + 0.5 * np.tanh(dissociation_pressure[t] / 1.0))

        pi[t] = pi[t - 1].copy()
        pi[t, 1] = clamp(pi[t, 1] + c_drive + RNG.normal(0, 0.0003))  # C

        # Other dims: minor noise
        pi[t, 0] += RNG.normal(0, 0.0001)
        pi[t, 2] += RNG.normal(0, 0.0001)
        pi[t, 3] += RNG.normal(0, 0.0001)
        pi[t, 4] += RNG.normal(0, 0.0001)
        pi[t, [0, 2, 3, 4]] = np.clip(pi[t, [0, 2, 3, 4]], 0, 1)

    return pi


# ─── Plotting ─────────────────────────────────────────────────────────────────

def main():
    pi_wound = simulate_wounding(500)
    pi_accept = simulate_acceptance(500)
    pi_contra = simulate_contradiction(200)

    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    fig.suptitle(
        "Personality Feedback Loop: Drift Under Different Conditions",
        fontsize=13, fontweight="bold", y=0.98,
    )

    # --- Subplot A: Repeated Wounding ---
    ax = axes[0]
    for i, (label, color) in enumerate(zip(DIM_LABELS, DIM_COLORS)):
        ax.plot(pi_wound[:, i], color=color, label=label, linewidth=1.2,
                alpha=0.9 if label in ("N", "O") else 0.5)
    ax.set_title("A: Repeated Wounding", fontsize=11)
    ax.set_xlabel("Tick")
    ax.set_ylabel("Personality Dimension Value")
    ax.set_ylim(0.3, 0.75)
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)

    # --- Subplot B: Sustained Acceptance ---
    ax = axes[1]
    for i, (label, color) in enumerate(zip(DIM_LABELS, DIM_COLORS)):
        ax.plot(pi_accept[:, i], color=color, label=label, linewidth=1.2,
                alpha=0.9 if label in ("E", "A") else 0.5)
    ax.set_title("B: Sustained Acceptance", fontsize=11)
    ax.set_xlabel("Tick")
    ax.set_ylim(0.4, 0.7)

    # --- Subplot C: Cross-Relational Contradiction ---
    ax = axes[2]
    for i, (label, color) in enumerate(zip(DIM_LABELS, DIM_COLORS)):
        ax.plot(pi_contra[:, i], color=color, label=label, linewidth=1.2,
                alpha=0.9 if label == "C" else 0.5)
    ax.set_title("C: Cross-Relational Contradiction", fontsize=11)
    ax.set_xlabel("Tick")
    ax.set_ylim(0.3, 0.6)

    plt.tight_layout(rect=[0, 0, 1, 0.94])

    out_path = Path(__file__).resolve().parent.parent / "docs" / "experiments" / "fig10_personality_feedback.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"[Experiment 11] Figure saved: {out_path}")


if __name__ == "__main__":
    main()
