# Void Calculus — Theorems and Formal Proofs

---

## Theorem 1: Irreducibility to AGM Belief Revision

**Statement.** There exists a void configuration $v \in V$ such that no AGM belief revision operation (contraction, expansion, or revision) on any belief set $K$ over any propositional language $\mathcal{L}$ can represent $v$'s behavioral signature.

### Formal Setup

**Definition (AGM Contraction).** Given a belief set $K$ (deductively closed set of sentences) and a sentence $\phi \in \mathcal{L}$, the contraction $K \div \phi$ satisfies the AGM postulates (closure, inclusion, vacuity, success, recovery, extensionality).

**Definition (Behavioral Signature).** The behavioral signature of a void $v$ is the tuple $\text{sig}(v) = (\delta_v, \pi_v(t), \beta_v, \text{genesis\_sensitivity})$ — its depth, time-dependent pressure, boundary completeness, and effect on future void detection.

### Proof

We construct a void that violates a necessary property of any AGM-representable absence.

**Property of AGM:** Every contraction $K \div \phi$ satisfies the *recovery postulate*: $(K \div \phi) + \phi = K$. This means the "absence" created by contraction is always *recoverable* — adding $\phi$ back restores the original state.

**Property of AGM (implicit):** The object of contraction $\phi$ must be a well-formed formula in $\mathcal{L}$. You cannot contract by "something, but I don't know what."

**Construction.** Consider a void $v$ with:

- $\beta_v = 0$ (boundary completeness zero)
- $\delta_v = 0.8$ (high depth — strong avoidance detected)
- $|B_v| = 0$ (no boundary points — we don't know what's being avoided)

This void was created by detecting avoidance behavior (sudden topic deflections) without identifying the avoided topic. Its behavioral signature includes:

1. Pressure accumulation: $\pi_v(t) = \pi_v(t-1) + 0.8 \cdot \ln(a_v + 1) \cdot 1.0 > 0$
2. Genesis sensitivity modification: future voids near this region form more easily
3. No recovery path: since $B_v = \emptyset$, there is no event that can "contract" this void (no boundary to address)

**Impossibility argument:**

Suppose for contradiction that there exists a belief set $K$ and formula $\phi$ such that $K \div \phi$ represents $v$. Then:

(i) By the recovery postulate, $(K \div \phi) + \phi = K$. This means there exists a specific $\phi$ whose addition "resolves" the absence.

(ii) But $v$ has $\beta_v = 0$: there is no identified content to the absence. No specific proposition $\phi$ can be named as "what's missing."

(iii) One might argue: represent $v$ as $K \div \exists x. P(x)$ for some predicate $P$. But then recovery requires adding $\exists x. P(x)$, which requires knowing $P$. The void's behavioral signature does not determine any $P$ — different future events could "fill" the void in different ways, and the void itself does not constrain which.

(iv) More fundamentally: in AGM, the *absence* of $\phi$ from $K \div \phi$ is a *static* property — it doesn't generate pressure, doesn't modify future operations, and doesn't have autonomous dynamics. The behavioral signature of $v$ includes time-dependent pressure $\pi_v(t) \to \infty$ as $t \to \infty$, which has no AGM counterpart.

**Formal separation:** Define the property $\mathcal{P}_{autonomous}$: "the representation of absence generates monotonically increasing influence on system behavior without external input." AGM contractions satisfy $\neg\mathcal{P}_{autonomous}$ (a contracted belief set is static until new information arrives). Void $v$ satisfies $\mathcal{P}_{autonomous}$ (pressure grows autonomously). Therefore $v$ is not AGM-representable.

$\square$

---

## Theorem 2: Irreducibility to Bayesian Belief Updating

**Statement.** There is no probability space $(\Omega, \mathcal{F}, P)$ and no Bayesian updating rule such that the void pressure dynamics $\pi_v(t+1) = \pi_v(t) + \delta_v \cdot \ln(a_v + 1) \cdot (1 - \beta_v)$ can be derived as a posterior quantity under any prior and likelihood model.

### Proof

**Bayesian framework.** In Bayesian updating, given prior $P(\theta)$ and observation $x_t$:
$$P(\theta | x_{1:t}) = \frac{P(x_t | \theta) P(\theta | x_{1:t-1})}{P(x_t | x_{1:t-1})}$$

The key property: **without new observations, the posterior is unchanged:**
$$P(\theta | x_{1:t}) = P(\theta | x_{1:t}) \quad \text{(tautology: no update without data)}$$

**Void pressure property.** Between events (no new observations), void pressure increases:
$$\pi_v(t+1) - \pi_v(t) = \delta_v \cdot \ln(a_v + 1) \cdot (1 - \beta_v) > 0$$

This is an *autonomous* increase with no conditioning on new data.

**Attempted Bayesian encoding.** Suppose we encode void pressure as a posterior quantity $\pi_v(t) = f(P(\theta_v | x_{1:t}))$ for some function $f$ and latent variable $\theta_v$ ("the avoided topic exists and is significant").

For $\pi_v$ to increase without new data, we need:
$$f(P(\theta_v | x_{1:t}, \text{no new data at } t+1)) > f(P(\theta_v | x_{1:t}))$$

But $P(\theta_v | x_{1:t}, \text{no new data}) = P(\theta_v | x_{1:t})$ by definition of Bayesian updating. Therefore $f$ must be time-dependent: $f_t \neq f_{t+1}$.

**But a time-dependent $f_t$ is not Bayesian inference** — it's an external deterministic process applied to a posterior. This is equivalent to:
$$\pi_v(t) = h(t, P(\theta_v | x_{1:t}))$$

where $h$ is a non-Bayesian accumulator. The "Bayesian" part ($P(\theta_v | x_{1:t})$) is doing no work — the pressure dynamics are entirely in $h$, which is exactly the Void Calculus pressure equation reimplemented outside the probabilistic framework.

**Formal separation:** Define $\mathcal{P}_{silence}$: "absence of observation increases the system's confidence/influence regarding a hypothesis." Standard Bayesian updating satisfies $\neg\mathcal{P}_{silence}$ (no observation → no update). Void Calculus satisfies $\mathcal{P}_{silence}$ (no observation → pressure increases). Any "Bayesian" system satisfying $\mathcal{P}_{silence}$ must include a non-Bayesian component that performs the actual pressure accumulation, making the Bayesian framing vacuous.

$\square$

---

## Theorem 3: Three-Way Expressiveness Distinction

**Statement.** Void Calculus distinguishes three relational states that are pairwise behaviorally distinct and that collapse to at most two states in any system based on (a) classical negation, (b) probabilistic belief, or (c) AGM revision.

The three states:

- $S_1$ (Never discussed): $v = (B_v, 0, \pi_0, a, \beta)$ with $\delta_v = 0$
- $S_2$ (Resolved): ghost $\hat{v} = (\emptyset, \delta > 0, 0, a, 0)$
- $S_3$ (Actively avoided): $v = (B_v, \delta > 0, \pi > 0, a, \beta)$

### Proof

**Part A: Pairwise behavioral distinction in Void Calculus.**

Define the behavioral output function $\mathcal{B}(state) = (pressure\_contribution, genesis\_modifier, scar\_coupling)$:

- $\mathcal{B}(S_1) = (0, 0, 0)$: no pressure (depth = 0), no ghost effect, no coupling
- $\mathcal{B}(S_2) = (0, \Delta\theta_d, 0)$: no pressure (ghost has $\pi = 0$), but lowers detection threshold by $\Delta\theta_d = 0.3 \cdot \delta > 0$, no active coupling
- $\mathcal{B}(S_3) = (\pi_v > 0, 0, \Gamma(v))$: active pressure, no ghost modifier (not dead yet), active scar coupling when $\pi_v > \theta_p$

All three outputs are pairwise distinct:
- $S_1 \neq S_2$: second component differs ($0$ vs $\Delta\theta_d > 0$)
- $S_1 \neq S_3$: first component differs ($0$ vs $\pi_v > 0$)
- $S_2 \neq S_3$: first and second components both differ

**Part B: Collapse in classical negation.**

In classical logic, a proposition $\phi$ is either in the theory $T$ or not: $\phi \in T$ or $\phi \notin T$. All three states map to $\phi \notin T$ (the topic is not "present" in any of them). Classical negation cannot distinguish the three.

**Part C: Collapse in probabilistic belief.**

In a Bayesian system with $P(\phi) \in [0,1]$:
- $S_1$ (never discussed): $P(\phi) = P_0$ (prior, unchanged)
- $S_2$ (resolved): $P(\phi) \approx 1$ (evidence was eventually provided)
- $S_3$ (actively avoided): $P(\phi) = ?$

For $S_3$: active avoidance provides no direct evidence about $\phi$. Under standard Bayesian updating, $P(\phi | \text{avoidance observed})$ depends on the likelihood model $P(\text{avoidance} | \phi)$. If avoidance is modeled as evidence *for* $\phi$ (people avoid true uncomfortable things), then $P(\phi)$ increases. If not modeled, $P(\phi) = P_0$.

In either case: $S_1$ and $S_3$ are *indistinguishable* if avoidance is not in the likelihood model (both have $P(\phi) = P_0$). Even if avoidance is modeled, the distinction between $S_1$ and $S_3$ is only in the posterior value — there is no *structural* difference (both are just numbers in $[0,1]$). The autonomous pressure dynamics of $S_3$ have no Bayesian counterpart (Theorem 2).

Probabilistic belief distinguishes at most $S_2$ from $\{S_1, S_3\}$ — a two-way distinction, not three-way.

**Part D: Collapse in AGM revision.**

In AGM:
- $S_1$: $\phi \notin K$ (never added)
- $S_2$: $\phi \in K$ (was contracted then re-expanded) — but AGM has no "ghost" mechanism; after recovery, the state is identical to never having contracted
- $S_3$: $K \div \phi$ (contracted)

AGM's recovery postulate means $S_2$ is indistinguishable from "never contracted" after recovery: $(K \div \phi) + \phi = K$. Therefore $S_1$ and $S_2$ collapse in AGM (both result in $\phi \in K$ or $\phi \notin K$ with no residual trace).

AGM distinguishes at most $\{S_1, S_2\}$ from $S_3$ — again a two-way distinction.

$\square$

---

## Theorem 4: Void Set Convergence (Bounded Steady State)

**Statement.** Under the following conditions:

- Bounded input rate: at most $R$ events per unit time
- Positive contraction rate: each boundary point is addressed with probability $\geq p > 0$ per event
- Finite initial boundary: $|B_v| \leq B_{max}$ for all newly created voids

The void set reaches a bounded steady state: $\mathbb{E}[|V_t|] \leq N^*$ for all $t$ sufficiently large, where $N^* = R \cdot B_{max} / (p \cdot R) = B_{max} / p$.

### Proof

**Void lifetime.** A void $v$ with initial boundary size $|B_v| = b$ dies when all boundary points are contracted. Under the assumption that each event contracts each boundary point independently with probability $p$, the expected number of events until all $b$ points are contracted is the *coupon collector* problem:
$$\mathbb{E}[\text{lifetime}(v)] = \frac{1}{p} \cdot H_b \leq \frac{1}{p} \cdot (\ln b + 1) \leq \frac{\ln B_{max} + 1}{p}$$

where $H_b$ is the $b$-th harmonic number.

**Steady-state void count.** Voids are created at rate $\leq R$ (at most one per event, worst case). Voids die at rate $|V_t| / \mathbb{E}[\text{lifetime}]$. At steady state:
$$R = \frac{N^*}{\mathbb{E}[\text{lifetime}]} \implies N^* = R \cdot \frac{\ln B_{max} + 1}{p}$$

**Total pressure bound.** Individual void pressure at death:
$$\pi_v^{max} = \sum_{t=0}^{\text{lifetime}} \delta_v \cdot \ln(t+1) \cdot (1-\beta_v) \leq \delta_{max} \cdot \text{lifetime} \cdot \ln(\text{lifetime})$$

Since $\delta_v$ is bounded by the maximum deepening rate ($\leq R \cdot \epsilon_{deepen}$ per tick), and lifetime is bounded:
$$\Pi_{max} = N^* \cdot \pi_v^{max} < \infty$$

$\square$

**Remark.** The bound is conservative. In practice, most voids have $\delta_v \approx 0$ (never actively avoided) and die quickly. The pressure landscape is dominated by a few long-lived, deep voids.

---

## Theorem 5: Ghost Set Growth and Pruning Correctness

**Statement.**

(a) The ghost set $|\hat{V}_t|$ grows without bound: $|\hat{V}_t| \to \infty$ as $t \to \infty$.

(b) Pruning ghosts with $\delta_{\hat{v}} < \epsilon$ preserves the behavioral signature of the void space up to an error bounded by $\epsilon \cdot |\text{pruned}|$ in the genesis sensitivity modification.

### Proof

**(a) Unbounded growth.**

Every void that dies with $\delta_v > 0$ creates a ghost (Axiom 5). By Theorem 4, voids are created at rate $\leq R$ and die at a positive rate. Over infinite time, infinitely many voids are created and die. Not all have $\delta_v = 0$ (any void that experiences at least one deepening event has $\delta_v > 0$). Under the assumption that a positive fraction $q > 0$ of voids experience at least one deepening event:
$$|\hat{V}_t| \geq q \cdot \text{(total voids ever created by time } t) \to \infty$$

**(b) Pruning correctness.**

The behavioral effect of a ghost $\hat{v}$ is solely through genesis sensitivity modification:
$$\theta_d^{local} = \theta_d \cdot (1 - 0.3 \cdot |\{\hat{v}: \text{relevant}\}|)$$

A ghost with $\delta_{\hat{v}} < \epsilon$ contributes at most $0.3$ to the threshold reduction. Removing it changes the effective threshold by at most $0.3$.

More precisely: define the *behavioral distance* between void spaces $V$ and $V'$ as:
$$d(V, V') = \sup_{\text{event sequences}} |\text{genesis\_count}(V) - \text{genesis\_count}(V')|$$

Pruning a ghost with depth $\delta < \epsilon$ changes the genesis threshold by $\leq 0.3$. The probability that this threshold change causes an additional void genesis on any single event is bounded by:
$$\Delta P \leq \frac{0.3}{\theta_d} \cdot P(\text{surprise} \in [\theta_d - 0.3, \theta_d])$$

Over $T$ events, the expected behavioral difference is:
$$\mathbb{E}[d(V, V')] \leq T \cdot \Delta P \cdot |\text{pruned}|$$

For $\epsilon$-depth ghosts, this is $O(\epsilon \cdot |\text{pruned}| \cdot T)$ — linear in the number pruned and the time horizon, but controllable by choosing $\epsilon$ small.

$\square$

---

## Theorem 6: Void-Scar Coupling Creates Path-Dependent Hysteresis

**Statement.** In the coupled Void-Scar system, the response to topic $T$ at time $t$ depends on the *path* by which the system arrived at its current state, even when the current void set and scar state are identical in their "present" components.

### Proof

**Construction.** Consider two histories leading to the same "present" state:

**History A (direct):** Topic $T$ is discussed normally at time $t_0$. No void forms, no scars related to $T$.

**History B (avoidance then resolution):**
1. Time $t_1 < t_0$: Topic $T$ is actively avoided. Void $v_T$ forms with boundary $B_T$.
2. Time $t_1$ to $t_2$: Void deepens ($\delta_T$ increases). Pressure accumulates.
3. Time $t_2$: Pressure exceeds $\theta_p$. Coupling $\Gamma$ fires: wound event on scar state.
4. Time $t_3$: Topic $T$ is finally addressed. Void contracts and dies. Ghost $\hat{v}_T$ remains.
5. Time $t_4$: Scar from step 3 heals to $faded$.

**At time $t > t_4$, "present" comparison:**

| Component | History A | History B |
|-----------|-----------|-----------|
| Active voids on $T$ | None | None |
| Scar state base vector | $x_A$ | $x_B$ (different due to wound) |
| Scar on relevant dim | None | 1 faded scar ($\alpha = 0.7$) |
| Ghost near $T$ | None | $\hat{v}_T$ with $\delta > 0$ |

**Behavioral difference at time $t$:**

If topic $T$ is raised again:

- **History A response:** Input is unmodified ($M_d = 1.0$). No ghost effect. Normal processing.
- **History B response:** Input is attenuated ($M_d = 0.7$ from faded scar). Ghost lowers detection threshold — system is more sensitive to avoidance patterns near $T$. If the topic is deflected again, a new void forms more easily.

The response differs in:
1. Magnitude (0.7× attenuation from scar)
2. Sensitivity (lower genesis threshold from ghost)
3. Future trajectory (easier to re-enter avoidance pattern)

**This is hysteresis:** the system's response depends on its history, not just its current "observable" state. The ghost and faded scar are *residues* of the path that permanently alter future dynamics.

**Formal statement:** Define the response function $R(s, e) = s \triangleright e$. For states $s_A$ (from History A) and $s_B$ (from History B):
$$R(s_A, e_T) \neq R(s_B, e_T)$$

even though both states have no active void on $T$ and the base vectors may be arbitrarily close (the scar's effect on the base vector decays, but the modifier $0.7$ persists forever).

The hysteresis is *permanent*: no finite sequence of future events can make $s_A$ and $s_B$ behaviorally equivalent, because the faded scar's modifier is irreversible (Scar Axiom 1) and the ghost is permanent (Void Axiom 5).

$\square$

---

## Complexity Results

**Proposition 7.** Decision problems in Void Calculus:

| Problem | Complexity |
|---------|-----------|
| "Is void $v$ alive?" | $O(1)$ — check $\|B_v\| > 0$ |
| "Will void $v$ generate coupling this tick?" | $O(1)$ — check $\pi_v > \theta_p$ |
| "Does event $e$ contract void $v$?" | $O(\|B_v\|)$ — scan boundary |
| "Should a new void be created?" | $O(1)$ — check surprise + prev\_sim |
| "Find all voids contractable by event $e$" | $O(\|V\| \cdot B_{avg})$ |
| "Compute total pressure" | $O(\|V\|)$ |
| "Are two void spaces behaviorally equivalent?" | coNP-hard (conjecture) |

**Justification for coNP-hardness conjecture:** Two void spaces are behaviorally equivalent iff they produce identical genesis decisions, pressure outputs, and coupling events on *all* possible future event sequences. Verifying equivalence requires checking all possible inputs (universal quantification), suggesting coNP-hardness. A formal reduction from a known coNP-complete problem (e.g., TAUTOLOGY) remains an open problem.

---

## Open Problems

1. **Void algebra completeness:** Is the operation set $\{contract, deepen, split, merge\}$ complete — i.e., can every reachable void configuration be reached from any initial configuration using these operations?

2. **Behavioral equivalence complexity:** Prove or disprove that void space behavioral equivalence is coNP-hard.

3. **Optimal ghost pruning:** What is the pruning strategy that minimizes behavioral error for a given memory budget? (This is likely an instance of the knapsack problem.)

4. **Void detection false positive rate:** Under what distributional assumptions on input sequences does the genesis criterion (negative similarity derivative + high surprise) have bounded false positive rate $\leq \alpha$?
