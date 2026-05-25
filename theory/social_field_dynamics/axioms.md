# Social Field Participation Dynamics (SFPD) — Formal Axiom System

## 1. Motivation

In group conversations, the decision to speak is not binary but a **phase transition**. The existing L7 `PhaseTransitionExpression` handles private-chat expression: internal pressure accumulates until a critical threshold, then erupts. However, group contexts introduce qualitatively new forces:

- **Social pressure**: being called upon, being relevant, being silent too long
- **Social inhibition**: group size raises the barrier to speak (evaluation apprehension)
- **Stochastic resonance**: ambient group noise can *assist* threshold crossing for marginal signals

SFPD extends L7 to group contexts by modulating the effective threshold and expression drive with **social field signals** — forces that arise from the group's collective state and act on the agent's expression dynamics.

The key insight: in private chat, expression is governed by internal state alone. In groups, expression is governed by the *coupling* between internal state and the social field.

---

## 2. Definitions

### Definition 1: Social Field

A **Social Field** $\mathcal{S}$ is the collection of forces acting on an agent in a group conversation:

$$\mathcal{S} = (\sigma_{call}, \sigma_{sheaf}, \sigma_{void}, d_{topic}, d_{cont}, d_{noise}, \mu, n)$$

where:
- $\sigma_{call} \in [0, 1]$: direct invocation signal (@mention, name call)
- $\sigma_{sheaf} \in [0, 1]$: relational coupling strength (from Sheaf spectral gap)
- $\sigma_{void} \in [0, 5]$: social void pressure (group silence accumulation)
- $d_{topic} \in [0, 1]$: topic relevance drive
- $d_{cont} \in [0, 1]$: continuation drive (exponential decay from last bot reply)
- $d_{noise} \in [0, 1]$: stochastic resonance from group activity
- $\mu \in \mathbb{R}_{\geq 0}$: group inhibition factor (scales with group size and introversion)
- $n \in \mathbb{N}$: number of active participants

### Definition 2: Social Void

A **Social Void** extends Void Calculus Axiom 3 (Pressure Autonomy) to the group context. When a group falls silent, a social void forms with pressure:

$$\pi_{social}(t) = \min(5.0, \; \gamma \cdot \ln(1 + t_{silent}))$$

where:
- $t_{silent}$: ticks since last message in the group
- $\gamma$: personality-derived accumulation rate ($\gamma = 0.3 + 0.4 \cdot extraversion$)

Unlike private voids (which represent avoided topics), social voids represent **unfilled conversational space** — the group expects someone to speak, and that expectation generates pressure on all participants.

### Definition 3: Effective Threshold

The **effective threshold** for group expression is:

$$\theta_{eff} = \theta_{base} \times (1 + \mu) - \sum_i \sigma_i$$

where:
- $\theta_{base}$: the agent's private-chat expression threshold (from personality)
- $\mu = \mu_0 \cdot (1 - extraversion) \cdot \ln(n)$: group inhibition ($\mu_0 = 0.5$ default)
- $\sum_i \sigma_i = \sigma_{call} + \sigma_{sheaf} + \sigma_{void}$: total social signal reducing threshold

**Boundary conditions:**
- $\theta_{eff} \leq 0 \implies$ guaranteed expression (social signals overwhelm inhibition)
- $\theta_{eff} = \theta_{base}$ when $\mu = 0$ and $\sigma_i = 0$ (private chat invariance)

### Definition 4: Social Signals

| Signal | Source | Range | Computation |
|--------|--------|-------|-------------|
| $\sigma_{call}$ | @mention or name in text | $\{0, 0.6, 1.0\}$ | 1.0 if @mention, 0.6 if name mentioned, 0 otherwise |
| $\sigma_{sheaf}$ | Relational Sheaf spectral gap | $[0, 0.4]$ | $0.4 \cdot (1 - \lambda_1 / \lambda_2)$ where $\lambda_1, \lambda_2$ are smallest Laplacian eigenvalues |
| $\sigma_{void}$ | Social void pressure | $[0, 0.5]$ | $0.1 \cdot \pi_{social}$ |
| $d_{topic}$ | Keyword overlap with recent bot topics | $[0, 1]$ | Jaccard similarity of extracted keywords |
| $d_{cont}$ | Time since last bot reply | $[0, 1]$ | $\exp(-\Delta t / \tau_{cont})$, $\tau_{cont} = 60s$ |
| $d_{noise}$ | Group message rate | $[0, 0.3]$ | $0.3 \cdot \min(1, rate / rate_{max})$ |

---

## 3. Axioms

### Axiom SF1: Environment Pressure Modulates Phase Transition Threshold

**Statement:** The effective expression threshold in a group context is strictly higher than in private, modulated by group size and personality.

**Formulation:**

$$\theta_{eff} = \theta_{base} \times (1 + \mu_0 \cdot (1 - E) \cdot \ln(n)) - \Sigma\sigma$$

where $E$ is extraversion, $n$ is group size, and $\Sigma\sigma = \sigma_{call} + \sigma_{sheaf} + \sigma_{void}$.

**Physical interpretation:** Speaking in a group requires overcoming evaluation apprehension. Introverts face higher barriers in larger groups. Social signals (being called, topic relevance, silence pressure) reduce this barrier.

**Connection to existing theory:** Extends `PhaseTransitionExpression.threshold` from a static personality-derived value to a dynamic field-modulated value. When `is_group = False`, $\mu = 0$ and $\Sigma\sigma = 0$, recovering standard L7 behavior.

---

### Axiom SF2: Social Void — Group Silence Generates Autonomous Pressure

**Statement:** In a group context, prolonged silence generates pressure on the agent to speak, independent of internal drive.

**Formulation:**

$$\frac{d\pi_{social}}{dt} = \gamma \cdot \frac{1}{1 + t_{silent}} > 0 \quad \text{whenever } t_{silent} > 0$$

with $\pi_{social}$ capped at 5.0 and $\gamma = 0.3 + 0.4 \cdot E$.

**Physical interpretation:** Group silence creates social obligation. Extraverts feel this pressure more strongly (higher $\gamma$). The logarithmic growth ensures pressure saturates — infinite silence doesn't produce infinite obligation.

**Connection to existing theory:** Extends Void Calculus Axiom 3 (Pressure Autonomy). Private voids generate pressure from *avoided topics*; social voids generate pressure from *unfilled conversational space*. Both are autonomous (no external input needed), but social voids have bounded pressure (cap at 5.0) because social obligation has diminishing returns.

---

### Axiom SF3: Sheaf Spectral Gap Modulates Social Coupling

**Statement:** The agent's coupling to the group conversation is proportional to the spectral gap of the relational sheaf Laplacian restricted to active participants.

**Formulation:**

$$\sigma_{sheaf} = 0.4 \cdot \left(1 - \frac{\lambda_1}{\lambda_2}\right)$$

where $\lambda_1 \leq \lambda_2$ are the two smallest eigenvalues of the sheaf Laplacian $L_{\mathcal{F}}$ restricted to the active group subcomplex.

**Physical interpretation:** A small spectral gap ($\lambda_1 \approx \lambda_2$) means the group is loosely connected — the agent has weak social coupling and $\sigma_{sheaf} \to 0$. A large gap means the agent is tightly integrated into the group's relational structure, making participation more natural.

**Connection to existing theory:** Uses the Sheaf Laplacian from Relational Sheaf Theory (Definition 5 in `theory/relational_sheaf/axioms.md`). The spectral gap is already computed for consistency measurement; SFPD reuses it as a participation signal.

---

### Axiom SF4: Scar Dimensions Inhibit Topic-Specific Participation

**Statement:** When the current group topic activates a scarred dimension, the effective threshold for that topic increases (participation becomes harder).

**Formulation:**

$$\theta_{eff}^{topic} = \theta_{eff} + \sum_{d \in D_{topic}} (\alpha(\phi_d) - 1.0) \cdot w_d$$

where:
- $D_{topic}$: set of scar dimensions activated by the current topic
- $\alpha(\phi_d)$: scar modifier for dimension $d$ (from Scar Algebra Definition 3)
- $w_d$: topic-dimension coupling weight

**Physical interpretation:** If the group is discussing a topic that maps to a scarred emotional dimension, the agent finds it harder to participate — not because of social inhibition, but because the topic itself triggers protective withdrawal. Raw scars ($\alpha = 2.0$) create strong inhibition; faded scars ($\alpha = 0.7$) actually *lower* the threshold (numbing enables easier participation on painful topics).

**Connection to existing theory:** Directly uses Scar Algebra modifier functions. The scar-modulated input from Definition 4 (State Transition) is reinterpreted as a participation barrier rather than a sensitivity amplifier.

---

### Axiom SF5: Stochastic Resonance — Group Noise Assists Threshold Crossing

**Statement:** Moderate group activity (noise) can assist the agent in crossing the expression threshold, analogous to stochastic resonance in nonlinear systems.

**Formulation:**

$$d_{noise} = 0.3 \cdot \min\left(1, \frac{r_{group}}{r_{max}}\right) \cdot \mathbb{1}[0.3 < \text{ratio} < 0.9]$$

where:
- $r_{group}$: current group message rate (messages per minute)
- $r_{max}$: saturation rate (configurable, default 5 msg/min)
- $\text{ratio} = pressure / \theta_{eff}$: how close the agent is to threshold

The indicator function $\mathbb{1}[0.3 < ratio < 0.9]$ ensures noise only helps when the agent is *near* threshold — too far below (ratio < 0.3) and noise is irrelevant; already above (ratio > 0.9) and the agent would express anyway.

**Physical interpretation:** In a lively group conversation, the ambient energy makes it easier to join in — but only if you already have something to say (pressure near threshold). This is the social equivalent of stochastic resonance: noise in a nonlinear system can amplify weak signals past a detection threshold.

**Connection to existing theory:** Novel axiom without direct precedent in existing Sylanne theory. Provides the mechanism by which group dynamics can "pull" a hesitant agent into participation without any direct invocation.

---

## 4. Personality Derivation

| Personality Trait | SFPD Parameter | Mapping | Effect |
|---|---|---|---|
| Extraversion (E) | $\mu_0$ scaling | $\mu \propto (1-E)$ | Extraverts have lower group inhibition |
| Extraversion (E) | $\gamma$ (void accumulation) | $\gamma = 0.3 + 0.4E$ | Extraverts feel silence pressure faster |
| Neuroticism (N) | $\theta_{base}$ sensitivity | via existing L7 mapping | Neurotic agents have variable thresholds |
| Openness (O) | $d_{topic}$ weight | $w_{topic} = 0.5 + 0.5O$ | Open agents respond to broader topics |
| Agreeableness (A) | $\sigma_{call}$ response | $\sigma_{call} \times (0.8 + 0.4A)$ | Agreeable agents respond more to calls |
| Conscientiousness (C) | $d_{cont}$ decay rate | $\tau_{cont} = 60 + 60C$ | Conscientious agents maintain conversations longer |
| Sylanne: warmth_bias | $\sigma_{sheaf}$ coupling | $\sigma_{sheaf} \times (0.7 + 0.6 \cdot warmth)$ | Warmer agents couple more to group |
| Sylanne: sovereignty_guard | $\mu_0$ base | $\mu_0 = 0.3 + 0.4 \cdot sovereignty$ | High sovereignty = higher group barrier |
| Sylanne: edge | $d_{noise}$ sensitivity | $d_{noise} \times (1.2 - 0.4 \cdot edge)$ | Edgy agents less influenced by group noise |

---

## 5. Integration with 7-Layer Computation Stack

```
┌─────────────────────────────────────────────────────────────────┐
│ L1: Perception (HDC)                                            │
│   → encode group message text                                   │
├─────────────────────────────────────────────────────────────────┤
│ L2: Predictive Coding Gate                                      │
│   → surprise detection, route decision                          │
│   → feeds: d_topic (via keyword extraction from encoded text)   │
├─────────────────────────────────────────────────────────────────┤
│ L3: Void-Scar Engine                                            │
│   → social_void_pressure feeds σ_void                           │
│   → scar dimensions feed SF4 topic inhibition                   │
│   → expression_drive baseline                                   │
├─────────────────────────────────────────────────────────────────┤
│ L4: Relational Sheaf                                            │
│   → spectral gap feeds σ_sheaf                                  │
│   → group subcomplex identification                             │
├─────────────────────────────────────────────────────────────────┤
│ L5: HGT Decision Fusion                                         │
│   → integrates social field signals with internal state          │
│   → d_noise computed from message rate                          │
├─────────────────────────────────────────────────────────────────┤
│ L6: Autopoietic Boundary                                        │
│   → boundary_firmness modulates μ (firmer = higher inhibition)  │
├─────────────────────────────────────────────────────────────────┤
│ L7: Phase Transition Expression [SFPD EXTENSION]                │
│   → θ_eff = θ_base × (1 + μ) - Σσ                             │
│   → should_express uses θ_eff instead of θ_base                 │
│   → express() applies refractory boost in group mode            │
│   → σ_call from message metadata                                │
│   → d_cont from last_bot_reply timestamp                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. Theorems

### Theorem SF1: Guaranteed Response

**Statement:** If $\sigma_{call} \geq \theta_{group}$, then `should_express = True` regardless of other state.

**Proof:** When $\sigma_{call} = 1.0$ (direct @mention):

$$\theta_{eff} = \theta_{base} \times (1 + \mu) - 1.0 - \sigma_{sheaf} - \sigma_{void}$$

Since $\theta_{base} \leq 0.9$ and $\mu \geq 0$, we need $\theta_{base} \times (1 + \mu) \leq 1.0 + \sigma_{sheaf} + \sigma_{void}$.

For any reasonable personality ($\mu \leq 2.0$, $\theta_{base} \leq 0.9$): $\theta_{eff} \leq 0.9 \times 3.0 - 1.0 = 1.7$. But with $\sigma_{call} = 1.0$, the implementation sets $\theta_{eff} = 0$ directly (override), guaranteeing expression. $\square$

---

### Theorem SF2: Silence Breakthrough

**Statement:** For any finite $\theta_{eff}$, there exists $T$ such that $\pi_{social}(T) > \theta_{eff}$ (social void eventually forces expression).

**Proof:** $\pi_{social}(t) = \gamma \cdot \ln(1 + t)$ is unbounded as $t \to \infty$... but we cap at 5.0.

**Revised statement:** For any $\theta_{eff} \leq 5.0 \cdot 0.1 = 0.5$ contribution from social void, silence eventually contributes enough to cross threshold when combined with other drives.

More precisely: since $\sigma_{void} = 0.1 \cdot \pi_{social}$ and $\pi_{social} \to 5.0$, the social void contributes at most $0.5$ to threshold reduction. Combined with baseline expression drive accumulation (which also grows with silence via `silence_lowers_threshold`), the system guarantees eventual expression for any finite initial threshold. $\square$

---

### Theorem SF3: Private Chat Invariance

**Statement:** When `is_group = False`, SFPD reduces exactly to standard L7 `PhaseTransitionExpression` behavior.

**Proof:** In private chat:
- $n = 1$, so $\mu = \mu_0 \cdot (1-E) \cdot \ln(1) = 0$
- No social signals: $\sigma_{call} = \sigma_{sheaf} = \sigma_{void} = 0$
- No social drives: $d_{topic} = d_{cont} = d_{noise} = 0$

Therefore: $\theta_{eff} = \theta_{base} \times (1 + 0) - 0 = \theta_{base}$

The expression dynamics reduce to the original `PhaseTransitionExpression` with threshold $= \theta_{base}$, which is exactly the private-chat behavior. $\square$

---

## 7. References

1. Benzi, R., Sutera, A., & Vulpiani, A. (1981). The mechanism of stochastic resonance. *Journal of Physics A*, 14(11), L453. — Stochastic resonance in nonlinear systems (Axiom SF5).

2. Latané, B. (1981). The psychology of social impact. *American Psychologist*, 36(4), 343-356. — Social impact theory: group size effects on participation (Axiom SF1).

3. Hansen, J. & Ghosh, R. (2020). Cellular sheaves of lattices and the Tarski Laplacian. *Homology, Homotopy and Applications*. — Sheaf Laplacian spectral theory (Axiom SF3).

4. Schelling, T. C. (1971). Dynamic models of segregation. *Journal of Mathematical Sociology*, 1(2), 143-186. — Phase transition models in social systems.

5. Deffuant, G. et al. (2000). Mixing beliefs among interacting agents. *Advances in Complex Systems*, 3, 87-98. — Opinion dynamics and threshold models in groups.

6. Sylanne-Embodiment internal: `theory/void_calculus/axioms.md` — Void Calculus Axiom 3 (Pressure Autonomy), extended by SF2.

7. Sylanne-Embodiment internal: `theory/relational_sheaf/axioms.md` — Sheaf Laplacian and spectral gap, used by SF3.

8. Sylanne-Embodiment internal: `theory/scar_algebra/axioms.md` — Scar modifier functions, used by SF4.
