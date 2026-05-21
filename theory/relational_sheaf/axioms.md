# Relational Sheaf Theory — Formal Axiom System

## Motivation

Scar Algebra and Void Calculus operate on a single relational dyad. When an agent maintains multiple concurrent relationships, the naive extension (independent copies) fails to capture:

1. **Cross-relational influence**: trauma in one relationship alters perception in others
2. **Irreducible multi-party states**: group interactions produce states not decomposable into pairwise components
3. **Consistency pressure**: maintaining contradictory self-presentations across relationships has measurable cost

We formalize multi-relational dynamics using **cellular sheaves on simplicial complexes**, providing:
- Local behavior governed by existing Scar Algebra (per-edge)
- Global consistency measured by sheaf cohomology
- Propagation dynamics governed by the sheaf Laplacian

---

## Definition 1: Relational Complex

A **relational complex** is a finite abstract simplicial complex $K = (V, \Sigma_K)$ where:

- $V = \{v_0, v_1, \ldots, v_N\}$ is the vertex set. $v_0$ is the agent (bot); $v_1, \ldots, v_N$ are interaction partners.
- $\Sigma_K \subseteq 2^V$ is closed under taking faces, containing:
  - **0-simplices** $\{v_i\}$: individual entities
  - **1-simplices** $\{v_0, v_i\}$: dyadic relationships (agent with partner $i$)
  - **2-simplices** $\{v_0, v_i, v_j\}$: triadic co-presence (agent with partners $i, j$ simultaneously)
  - Higher simplices for $k$-party co-presence

**Remark.** We require $v_0 \in \sigma$ for all $\sigma \in \Sigma_K$ with $\dim(\sigma) \geq 1$. The agent participates in every relationship. Edges $\{v_i, v_j\}$ with $i, j \neq 0$ are not modeled (we track the agent's relational state, not the social network).

---

## Definition 2: Scar Sheaf

A **Scar Sheaf** $\mathcal{F}$ on relational complex $K$ assigns:

### Stalks (state spaces)

To each simplex $\sigma \in \Sigma_K$, a real vector space $\mathcal{F}(\sigma)$:

- **Vertex stalks:** $\mathcal{F}(\{v_0\}) = \mathbb{R}^{n_0}$ (agent's internal state — personality core, energy, global mood)
- **Edge stalks:** $\mathcal{F}(\{v_0, v_i\}) = S_i = \mathbb{R}^n \times \Sigma_i^*$ (full Scar Algebra state for relationship $i$)
- **Triangle stalks:** $\mathcal{F}(\{v_0, v_i, v_j\}) = \mathbb{R}^{n_{ij}}$ (co-presence state, dimension $n_{ij} \leq n$)

### Restriction Maps

For each face relation $\tau \subseteq \sigma$, a linear map $\mathcal{F}_{\tau \trianglelefteq \sigma}: \mathcal{F}(\sigma) \to \mathcal{F}(\tau)$:

- $\rho_0^i: \mathcal{F}(\{v_0, v_i\}) \to \mathcal{F}(\{v_0\})$ — projects relationship state to agent's internal contribution
- $\rho_{ij}^i: \mathcal{F}(\{v_0, v_i, v_j\}) \to \mathcal{F}(\{v_0, v_i\})$ — restricts co-presence state to dyadic view

Concretely, $\rho_0^i$ extracts the "self-presentation vector" — how the agent presents itself within relationship $i$:

$$\rho_0^i(s_i) = P_i \cdot \mathbf{x}_i$$

where $P_i \in \mathbb{R}^{n_0 \times n}$ is the **presentation matrix** for relationship $i$, and $\mathbf{x}_i$ is the base state vector of $s_i$.

---

## Definition 3: Consistency and Coboundary

The **0-cochain space** is $C^0(K, \mathcal{F}) = \bigoplus_{v \in V} \mathcal{F}(\{v\})$.

The **1-cochain space** is $C^1(K, \mathcal{F}) = \bigoplus_{\{v_0, v_i\} \in \Sigma_K} \mathcal{F}(\{v_0, v_i\})$.

The **coboundary operator** $\delta^0: C^0 \to C^1$ is defined on each edge $e = \{v_0, v_i\}$:

$$(\delta^0 \mathbf{x})_e = \mathcal{F}_{v_0 \trianglelefteq e}(\mathbf{x}_{v_0}) - \mathcal{F}_{v_i \trianglelefteq e}(\mathbf{x}_{v_i})$$

For our setting (only $v_0$ has meaningful internal state contributing to edges):

$$(\delta^0 \mathbf{x})_e = P_i^T \cdot \mathbf{x}_0 - \mathbf{x}_i^{(ext)}$$

where $\mathbf{x}_i^{(ext)}$ is the external signal from partner $v_i$.

The **1-coboundary** $\delta^1: C^1 \to C^2$ measures inconsistency across triangles:

$$(\delta^1 \mathbf{s})_\sigma = \rho_{ij}^i(s_{ij}) - \rho_i^{ij}(s_i) + \rho_j^{ij}(s_j)$$

for triangle $\sigma = \{v_0, v_i, v_j\}$.

---

## Definition 4: Sheaf Laplacian

The **sheaf Laplacian** $L_\mathcal{F}: C^0(K, \mathcal{F}) \to C^0(K, \mathcal{F})$ is:

$$L_\mathcal{F} = \delta^{0*} \delta^0$$

Expanding for vertex $v_0$:

$$L_\mathcal{F}(\mathbf{x}_0) = \sum_{i: \{v_0, v_i\} \in \Sigma_K} P_i^T P_i \cdot \mathbf{x}_0 - P_i^T \cdot \rho_0^i(s_i)$$

This is a **weighted graph Laplacian** where the weights are the presentation matrices $P_i^T P_i$.

### Spectral Properties

Let $0 = \lambda_0 \leq \lambda_1 \leq \cdots \leq \lambda_{n_0}$ be eigenvalues of $L_\mathcal{F}$.

- $\lambda_0 = 0$ iff there exists a global section (perfectly consistent self-presentation)
- $\lambda_1 > 0$ (algebraic connectivity) measures the minimum inconsistency cost
- The **spectral gap** $\lambda_1 / \lambda_{\max}$ quantifies relational isolation

---

## Definition 5: Sheaf Cohomology

$$H^0(K, \mathcal{F}) = \ker(\delta^0) = \{\text{global sections}\}$$
$$H^1(K, \mathcal{F}) = \ker(\delta^1) / \text{im}(\delta^0)$$

**Interpretation:**

- $\dim H^0 > 0$: a consistent global self-presentation exists
- $\dim H^1 > 0$: there exist **irreducible relational contradictions** — inconsistencies that cannot be resolved by adjusting the agent's internal state alone

---

## Definition 6: Personality-Derived Presentation Matrices

The presentation matrices $P_i$ are not free parameters. They are derived from:

1. **Agent personality** $\boldsymbol{\pi} \in \mathbb{R}^5$ (Big Five: O, C, E, A, N)
2. **Relationship type** $\tau_i \in \{\text{intimate}, \text{friendly}, \text{formal}, \text{adversarial}\}$
3. **Relationship maturity** $m_i \in [0, 1]$ (derived from interaction count and coherence)

$$P_i = P_{base}(\boldsymbol{\pi}) + \Delta P(\tau_i) + m_i \cdot \Delta P_{mature}(\boldsymbol{\pi}, \tau_i)$$

where:
- $P_{base}(\boldsymbol{\pi})$: personality determines baseline self-presentation
- $\Delta P(\tau_i)$: relationship type modulates which dimensions are exposed
- $\Delta P_{mature}$: mature relationships reveal more of the true self (higher rank $P_i$)

**Axiom (Personality Consistency):** For all $i, j$:

$$\|P_i - P_j\|_F \leq \kappa(\boldsymbol{\pi}) \cdot (1 + d(\tau_i, \tau_j))$$

where $\kappa(\boldsymbol{\pi})$ is a personality-dependent consistency bound. High agreeableness → low $\kappa$ (more consistent across relationships). High neuroticism → high $\kappa$ (more variable self-presentation).

---

## Axiom System

**Axiom S1 (Local Scar Dynamics).** Within each edge stalk $\mathcal{F}(\{v_0, v_i\})$, the state evolves according to Scar Algebra axioms (Axioms 1–6 of the Scar Algebra axiom system). The sheaf structure does not modify local dynamics.

**Axiom S2 (Propagation via Laplacian).** Cross-relational influence is governed by the sheaf Laplacian diffusion:

$$\frac{\partial \mathbf{x}_0}{\partial t} = -\alpha \cdot L_\mathcal{F}(\mathbf{x}_0) + \mathbf{f}_{local}(t)$$

where $\alpha > 0$ is the propagation rate and $\mathbf{f}_{local}$ is the local forcing from the currently active relationship.

**Axiom S3 (Cohomological Constraint).** When $\dim H^1(K, \mathcal{F}) > 0$, the system must resolve the obstruction by one of:
- (a) Void genesis on the contradicting dimensions (Void Calculus coupling)
- (b) Dissociation: splitting the agent's internal state into relationship-specific projections (increasing $\kappa$)
- (c) Neither — the contradiction persists as measurable **relational tension**

**Axiom S4 (Irreversibility of Propagation).** Once a scar propagates from relationship $i$ to relationship $j$ via the Laplacian, the propagated effect is itself irreversible (inherits Scar Algebra Axiom 3). Cross-relational healing requires independent repair in each affected relationship.

**Axiom S5 (Energy Conservation).** The agent has finite relational energy $\mathcal{E} \in \mathbb{R}_{>0}$. Each active relationship consumes energy at rate $c_i > 0$. The total consumption is bounded:

$$\sum_{i} c_i(t) \leq \mathcal{E}(t)$$

When energy is depleted, expression drive across all relationships drops to zero (the agent "goes quiet").

**Axiom S6 (Presentation Matrix Evolution).** $P_i$ evolves as relationships mature:

$$P_i(t+1) = P_i(t) + \eta \cdot \nabla_{P_i} \mathcal{L}_{consistency}$$

where $\mathcal{L}_{consistency} = \|\delta^0 \mathbf{x}\|^2$ is the total inconsistency loss. The system naturally evolves toward more consistent self-presentation — but this evolution is constrained by personality ($\kappa$) and can be disrupted by trauma (scar events reset $P_i$ partially).
