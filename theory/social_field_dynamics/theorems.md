# Social Field Participation Dynamics — Theorems and Proofs

---

## Theorem SF1: Guaranteed Response

**Statement.** If $\sigma_{call} = 1.0$ (direct @mention), then `should_express = True` regardless of internal pressure state.

### Proof

When `is_at_bot = True`, the implementation sets $\theta_{eff} = 0$ directly (hard override in `effective_threshold()`).

With $\theta_{eff} = 0$:
- `half_threshold = 0`
- Any $pressure > 0$ satisfies `pressure > half_threshold`
- Therefore `should_express() = True`

Since the bot always has residual pressure > 0 (from decay mechanics and minimum accumulation), the response is guaranteed. $\square$

**Corollary.** Name mention ($\sigma_{call} = 0.6 \times \theta_{group}$) does not guarantee response but significantly lowers the barrier:

$$\theta_{eff}^{name} = \theta_{group} - 0.6 \times \theta_{group} = 0.4 \times \theta_{group}$$

---

## Theorem SF2: Silence Breakthrough

**Statement.** For any finite $\theta_{eff}$ and active group ($\delta_{social} > 0$), there exists finite time $T$ such that the system expresses.

### Proof

Two mechanisms cooperate:

1. **Social void accumulation** (Axiom SF2):
   $\pi_{social}(t) = \gamma \cdot \ln(1 + t_{silent})$ grows without bound (though capped at 5.0 in implementation).
   Contribution to threshold reduction: $\sigma_{void} = \pi_{social} \times void\_coupling \times 0.2$

2. **Silence lowers threshold** (existing L7 mechanic):
   `silence_lowers_threshold()` reduces $\theta_{base}$ by $0.008$ per tick, with floor at $0.25$.

Combined: even if social void saturates at $\sigma_{void,max} = 5.0 \times 0.5 \times 0.2 = 0.5$, the threshold continues dropping via mechanism (2). Since $\theta_{base} \to 0.25$ and $\sigma_{void} \leq 0.5$:

$$\theta_{eff} \to 0.25 \times (1 + \mu) - 0.5 - \sigma_{sheaf}$$

For any $\mu < 1.0$ (which covers all personality configurations since $\mu = 0.7 - E \times 0.6 \leq 0.7$):

$$\theta_{eff} \to 0.25 \times 1.7 - 0.5 = -0.075 < 0$$

Therefore expression is guaranteed in finite time. $\square$

---

## Theorem SF3: Private Chat Invariance

**Statement.** When `is_group = False`, SFPD reduces exactly to standard L7 `PhaseTransitionExpression` behavior with no observable difference.

### Proof

In private chat mode, `effective_threshold()` checks:
```python
if not self._social_signals or not self._social_signals.is_group:
    return self.threshold
```

This returns $\theta_{base}$ unchanged. Therefore:
- `should_express()` uses $\theta_{base}$ (unchanged)
- `expression_intensity()` uses $\theta_{base}$ (unchanged)
- `express()` applies no `refractory_boost` (group-only branch not taken)
- `accumulate()` is unaffected (no social signal dependency)

All L7 methods produce identical results to pre-SFPD behavior. $\square$

---

## Theorem SF4: Personality Monotonicity

**Statement.** Higher extraversion strictly decreases the effective group threshold (monotone in E).

### Proof

The group threshold boost is:
$$\mu = 0.7 - E \times 0.6$$

Therefore:
$$\theta_{eff} = \theta_{base} \times (1 + 0.7 - 0.6E) - \Sigma\sigma$$

Taking the derivative with respect to $E$:
$$\frac{\partial \theta_{eff}}{\partial E} = \theta_{base} \times (-0.6) < 0$$

Since $\theta_{base} > 0$ always, the effective threshold is strictly decreasing in extraversion. $\square$

**Corollary.** For two agents with identical state but different extraversion $E_1 > E_2$:
$$\theta_{eff}(E_1) < \theta_{eff}(E_2)$$

The more extraverted agent always has a lower barrier to group participation.

---

## Theorem SF5: Refractory Period Prevents Flooding

**Statement.** After expression in group mode, the agent cannot immediately express again (refractory period).

### Proof

After `express()` in group mode:
$$\theta_{new} = \min(0.9, \theta_{old} + 0.03 + refractory\_boost)$$

where $refractory\_boost = sovereignty \times 0.05 \in [0, 0.05]$.

The pressure is reset to 0 after expression. For the agent to express again, it must accumulate pressure past $\theta_{new}/2$. Since:
- Pressure accumulates at rate $drive \times dt$ with $drive \leq 1.0$
- Natural decay removes $2\%$ per tick
- Net accumulation per tick $\leq 0.98$

The minimum time to re-express is:
$$T_{min} = \frac{\theta_{new}/2}{drive_{max} \times (1 - decay)} = \frac{\theta_{new}/2}{0.98}$$

For typical $\theta_{new} \approx 0.56$: $T_{min} \approx 0.29$ ticks minimum, ensuring no single-tick flooding. In practice, with realistic drives ($\approx 0.3$), the refractory period is several ticks. $\square$

---

## Theorem SF6: Sheaf Coupling Amplifies Participation in Tight Groups

**Statement.** The spectral gap of the relational sheaf Laplacian monotonically increases participation likelihood.

### Proof

From Axiom SF3:
$$\sigma_{sheaf} = sheaf\_coupling \times coupling\_strength \times 0.3$$

where $coupling\_strength = 0.1 + A \times 0.4$ and $sheaf\_coupling \in [0, 1]$ is the spectral gap.

Since $\sigma_{sheaf}$ enters the threshold formula as a subtraction:
$$\theta_{eff} = \theta_{group} - \sigma_{call} - \sigma_{sheaf} - \sigma_{void}$$

Higher spectral gap → higher $\sigma_{sheaf}$ → lower $\theta_{eff}$ → easier expression.

The effect is bounded: $\sigma_{sheaf,max} = 1.0 \times 0.5 \times 0.3 = 0.15$, preventing sheaf coupling alone from overwhelming the threshold. $\square$
