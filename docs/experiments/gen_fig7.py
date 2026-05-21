"""Generate Figure 7: Cohomological Dissociation Under Contradictory Relationships.

Demonstrates H^1 emergence when presentation matrix evolution is disabled
and strongly contradictory events are fed across multiple relationships.
"""
import sys
import os
import math

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from sylanne_alpha.relational_sheaf import ScarSheaf, INTIMATE, FRIENDLY, ADVERSARIAL

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


class FrozenSheaf(ScarSheaf):
    """ScarSheaf with presentation matrix evolution disabled."""

    __slots__ = ()

    def _evolve_presentation_matrices(self, dt: float) -> None:
        """No-op: disable consistency-seeking evolution for experiment."""
        pass

    def _rebuild_presentation_matrix(self, edge_idx: int) -> None:
        """Only allow rebuild during initial setup (tick == 0)."""
        if self._tick > 0:
            return
        super()._rebuild_presentation_matrix(edge_idx)


def run_experiment(n_ticks: int = 200) -> dict:
    """Run the cohomological dissociation experiment."""
    sheaf = FrozenSheaf(max_energy=100.0)  # high energy so we don't deplete

    # High neuroticism personality -> high kappa (allows more inconsistency)
    personality = {
        "neuroticism": 0.95,
        "agreeableness": 0.2,
        "extraversion": 0.6,
        "openness": 0.5,
        "conscientiousness": 0.3,
    }
    sheaf.derive_params(personality)

    # Add 3 relationships: intimate (1), friendly (2), adversarial (3)
    sheaf.add_relationship(1, rel_type=INTIMATE, maturity=0.5)
    sheaf.add_relationship(2, rel_type=FRIENDLY, maturity=0.3)
    sheaf.add_relationship(3, rel_type=ADVERSARIAL, maturity=0.4)

    # Storage
    h1_history = []
    inconsistency_energy_history = []
    dissociation_pressure_history = []

    for t in range(n_ticks):
        # Determine which relationship is active and what event to send
        # Cycle through relationships with strongly contradictory signals
        # Use ramping amplitude to show gradual accumulation
        phase = t % 3
        ramp = min(1.0, t / 60.0)  # ramp up over first 60 ticks

        if phase == 0:
            # Intimate: strong warmth signal (positive valence)
            active_idx = 0  # edge index for partner 1
            a = 0.4 * ramp
            event = [a, a * 0.9, a * 0.7, a * 0.6, a * 0.5, a * 0.4, a * 0.3, a * 0.2]
        elif phase == 1:
            # Adversarial: strong hostility signal (opposite direction)
            active_idx = 2  # edge index for partner 3
            a = -0.4 * ramp
            event = [a, a * 0.9, a * 0.1, a * 0.8, a * 0.7, a * 0.2, a * 0.6, a * 0.5]
        else:
            # Friendly: neutral/mild signal (orthogonal to both)
            active_idx = 1  # edge index for partner 2
            a = 0.15 * ramp
            event = [a, a, a, a, a, a, a, a]

        sheaf.tick(active_idx, event, timestamp=float(t))

        # Measure
        obs = sheaf.observe()
        h1_history.append(obs["h1_dim"])

        # Compute total inconsistency energy (sum of squared coboundary norms)
        incon_vec = sheaf.inconsistency_vector()
        incon_energy = sum(x * x for x in incon_vec)
        inconsistency_energy_history.append(incon_energy)

        dissociation_pressure_history.append(obs["dissociation_pressure"])

    return {
        "h1": h1_history,
        "inconsistency_energy": inconsistency_energy_history,
        "dissociation_pressure": dissociation_pressure_history,
        "n_ticks": n_ticks,
        "kappa": sheaf._kappa,
    }


def plot_figure(data: dict, output_path: str) -> None:
    """Generate the dual-axis figure."""
    plt.style.use("seaborn-v0_8-whitegrid")

    n_ticks = data["n_ticks"]
    ticks = list(range(n_ticks))
    h1 = data["h1"]
    incon_energy = data["inconsistency_energy"]
    dissoc = data["dissociation_pressure"]

    fig, ax1 = plt.subplots(figsize=(10, 6))

    # Determine if H^1 ever becomes non-zero
    h1_max = max(h1)
    use_h1_as_primary = h1_max > 0

    # Left axis: H^1 or inconsistency energy
    color_left = "#2c3e50"
    color_incon = "#e74c3c"
    color_h1 = "#2980b9"

    if use_h1_as_primary:
        # Plot H^1 as step and inconsistency as secondary line
        ax1.step(ticks, h1, where="post", color=color_h1, linewidth=2.0,
                 label=r"$\dim\, H^1$ (irreducible contradictions)", zorder=3)
        ax1.set_ylabel(r"$\dim\, H^1$", color=color_h1, fontsize=12)
        ax1.tick_params(axis="y", labelcolor=color_h1)

        # Add inconsistency energy as a thin secondary line on same axis (normalized)
        incon_max = max(incon_energy) if max(incon_energy) > 0 else 1.0
        incon_normalized = [x / incon_max * h1_max for x in incon_energy]
        ax1.plot(ticks, incon_normalized, color=color_incon, linewidth=1.0,
                 alpha=0.5, linestyle="--",
                 label=f"Inconsistency energy (normalized, max={incon_max:.1f})")
    else:
        # H^1 stays 0 — use inconsistency energy as primary signal
        ax1.plot(ticks, incon_energy, color=color_incon, linewidth=2.0,
                 label="Total inconsistency energy", zorder=3)
        ax1.set_ylabel("Inconsistency energy", color=color_incon, fontsize=12)
        ax1.tick_params(axis="y", labelcolor=color_incon)

        # Show H^1 = 0 as annotation
        ax1.axhline(y=0, color=color_h1, linewidth=1.0, alpha=0.3)
        ax1.annotate(r"$H^1 = 0$ (below critical threshold)",
                     xy=(n_ticks * 0.5, max(incon_energy) * 0.9),
                     fontsize=9, color=color_h1, alpha=0.7,
                     ha="center")

    ax1.set_xlabel("Tick", fontsize=12)
    ax1.set_xlim(0, n_ticks)

    # Right axis: dissociation pressure
    ax2 = ax1.twinx()
    color_right = "#8e44ad"
    ax2.plot(ticks, dissoc, color=color_right, linewidth=1.8, alpha=0.85,
             label="Dissociation pressure")
    ax2.set_ylabel("Dissociation pressure", color=color_right, fontsize=12)
    ax2.tick_params(axis="y", labelcolor=color_right)
    ax2.set_ylim(0, 1.0)

    # Title
    fig.suptitle("Cohomological Dissociation Under Contradictory Relationships",
                 fontsize=13, fontweight="bold", y=0.97)

    # Subtitle with parameters
    subtitle = (f"Personality: N=0.95, A=0.2 | "
                f"$\\kappa$={data['kappa']:.3f} | "
                f"P-matrix evolution: disabled | "
                f"3 relationships (intimate/friendly/adversarial)")
    ax1.set_title(subtitle, fontsize=9, color="gray", pad=8)

    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2,
               loc="upper left", fontsize=9, framealpha=0.9)

    # Caption
    if not use_h1_as_primary:
        caption = (
            "Note: $H^1$ is a discrete topological invariant that only changes at "
            "critical thresholds.\nInconsistency energy provides the continuous "
            "signal of accumulating contradictions."
        )
    else:
        caption = (
            "H^1 emergence indicates irreducible relational contradictions that "
            "cannot be resolved\nby any consistent self-presentation across all "
            "relationships simultaneously."
        )
    fig.text(0.5, 0.01, caption, ha="center", fontsize=8.5, color="gray",
             style="italic")

    plt.tight_layout(rect=[0, 0.04, 1, 0.95])
    plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"Saved: {output_path}")
    print(f"  H^1 max: {h1_max}")
    print(f"  Inconsistency energy final: {incon_energy[-1]:.4f}")
    print(f"  Dissociation pressure final: {dissoc[-1]:.4f}")


if __name__ == "__main__":
    data = run_experiment(n_ticks=200)
    output = os.path.join(os.path.dirname(__file__), "fig7_cohomological_dissociation.png")
    plot_figure(data, output)
