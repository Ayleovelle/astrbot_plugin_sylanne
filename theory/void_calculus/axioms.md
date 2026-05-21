# Void Calculus — Formal Axiom System

## Definition 1: Void Space

A **Void Space** is a tuple $(V, B, \mathcal{O})$ where:

- $V$ is a set of voids (first-class absence objects)
- $B: V \to 2^H$ maps each void to its boundary (a subset of the HDC vector space $H$)
- $\mathcal{O} = \{contract, deepen, split, merge\}$ is the operation set

## Definition 2: Void

A **void** $v \in V$ is a tuple $(B_v, \delta_v, \pi_v, a_v, \beta_v)$ where:

- $B_v \subseteq H$: the boundary set (HDC vectors of things that surround the absence)
- $\delta_v \in \mathbb{R}_{\geq 0}$: depth (degree of avoidance)
- $\pi_v \in \mathbb{R}_{\geq 0}$: pressure (drive toward filling)
- $a_v \in \mathbb{N}$: age (ticks since creation)
- $\beta_v \in [0, 1]$: boundary completeness (how well-defined the void's edges are)

## Definition 3: Boundary Completeness

A void's boundary completeness $\beta_v$ measures how much of the void's "shape" is known:

$$\beta_v = \frac{|B_v|}{|B_v| + \hat{n}_v}$$

where $\hat{n}_v$ is the estimated total boundary size. A void with $\beta_v = 0$ is a **felt absence** (something is missing, but we don't know what). A void with $\beta_v = 1$ is a **named absence** (we know exactly what's not being said).

This is the key distinction from belief revision: **a void can exist before its boundary is known**.

## Definition 4: Void Operations

### 4.1 Contract

When an event $\mathbf{h} \in H$ touches the boundary of void $v$:

$$contract(v, \mathbf{h}) = (B_v \setminus \{b \in B_v : sim(\mathbf{h}, b) > \theta_c\}, \delta_v, \pi_v', a_v, \beta_v')$$

where:
- Boundary points similar to the event are removed (the topic was addressed)
- $\pi_v' = \pi_v \cdot (1 - |removed| / |B_v|)$: pressure decreases proportionally
- $\beta_v'$ is recomputed

**Void death condition:** $v$ dies when $|B_v| = 0$ (all boundary points addressed). But $\delta_v$ persists as a **void ghost** $\hat{v} = (\emptyset, \delta_v, 0, a_v, 0)$ — a memory that something was once avoided.

### 4.2 Deepen

When avoidance of void $v$ is detected (event steers away from boundary):

$$deepen(v, \epsilon) = (B_v, \delta_v + \epsilon, \pi_v, a_v, \beta_v)$$

**Irreversibility axiom:** There is no $shallow$ operation. $\delta_v$ is monotonically non-decreasing.

### 4.3 Split

When new information reveals that a void has internal structure:

$$split(v) = (v_1, v_2) \quad \text{where } B_{v_1} \cup B_{v_2} = B_v, \; B_{v_1} \cap B_{v_2} = \emptyset$$

with:
- $\delta_{v_1} = \delta_{v_2} = \delta_v$ (both inherit parent depth)
- $\pi_{v_i} = \pi_v / 2$ (pressure splits)
- $a_{v_i} = 0$ (new voids, fresh age)

**Split criterion:** $v$ splits when its boundary $B_v$ has two clusters with inter-cluster similarity below $\theta_s$.

### 4.4 Merge

When two voids' boundaries overlap:

$$merge(v_1, v_2) = v_3 \quad \text{where } B_{v_3} = B_{v_1} \cup B_{v_2}$$

with:
- $\delta_{v_3} = \max(\delta_{v_1}, \delta_{v_2})$ (deeper void dominates)
- $\pi_{v_3} = \pi_{v_1} + \pi_{v_2}$ (pressures add)
- $a_{v_3} = \max(a_{v_1}, a_{v_2})$ (older age preserved)

**Merge criterion:** $v_1, v_2$ merge when $\exists b_1 \in B_{v_1}, b_2 \in B_{v_2}: sim(b_1, b_2) > \theta_m$.

## Definition 5: Pressure Dynamics

Void pressure evolves autonomously each tick:

$$\pi_v(t+1) = \pi_v(t) + \delta_v \cdot \ln(a_v + 1) \cdot (1 - \beta_v)$$

Key properties:
- Deeper voids generate more pressure
- Older voids generate more pressure (logarithmic, not linear — avoidance becomes normalized over time)
- Less-defined voids ($\beta_v$ low) generate more pressure (the unknown is more anxious than the known-but-avoided)

## Definition 6: Void Detection (Genesis)

A new void is born when:

$$\exists \mathbf{h}_t \in H: \left(\frac{\partial sim(\mathbf{h}_t, \mathbf{h}_{t-1})}{\partial t} < -\theta_d\right) \wedge \left(surprise(\mathbf{h}_t) > \theta_s\right)$$

Interpretation: a sudden topic shift (negative similarity derivative) combined with high surprise indicates active avoidance — something was being approached and then deflected away from.

The newborn void's boundary is initialized with the "deflected-from" vector:

$$B_{v_{new}} = \{\mathbf{h}_{t-1}\}, \quad \delta_{v_{new}} = 0, \quad \beta_{v_{new}} = \frac{1}{1 + \hat{n}_{default}}$$

## Axiom 1: Existence Before Boundary (Primacy of Absence)

$$\exists v \in V: |B_v| = 0 \wedge \delta_v > 0$$

A void can exist with an empty boundary (void ghost). This is not representable in belief revision, where absence is always the complement of a known belief set.

## Axiom 2: Depth Irreversibility

$$\forall v \in V, \forall t_1 < t_2: \delta_v(t_1) \leq \delta_v(t_2)$$

Depth never decreases. A void can be contracted (boundary shrinks) or killed (boundary empties), but its depth — the record of how much it was avoided — is permanent.

## Axiom 3: Pressure Autonomy

$$\frac{d\pi_v}{dt} > 0 \quad \text{whenever } \delta_v > 0 \wedge a_v > 0$$

Voids generate pressure without external input. They are not passive data structures but active computational agents that influence the system's behavior.

## Axiom 4: Boundary Incompleteness

$$\beta_v < 1 \implies v \text{ is not reducible to } \neg\phi \text{ for any proposition } \phi$$

An incomplete void cannot be expressed as the negation of a known proposition. This is the formal statement of irreducibility to classical negation.

## Axiom 5: Ghost Persistence

$$death(v) \implies \hat{v} = (\emptyset, \delta_v, 0, a_v, 0) \in V$$

Dead voids leave ghosts. Ghosts have no boundary, no pressure, but retain depth. They modify the genesis threshold for future voids in the same region:

$$\theta_d^{local} = \theta_d \cdot (1 - 0.3 \cdot |\{\hat{v}: sim(B_{\hat{v}}^{last}, region) > 0.5\}|)$$

Interpretation: regions where voids have existed before are more sensitive to new void formation. Scar-like behavior emerges naturally.

## Axiom 6: Void-Scar Coupling

When a void's pressure exceeds threshold $\theta_p$, it generates a wounding event on the Scar Algebra's state:

$$\pi_v > \theta_p \implies \mathbf{e}_{wound} = \pi_v \cdot \hat{B}_v$$

where $\hat{B}_v$ is the centroid of the void's boundary projected into the SSM input space. This is the formal interface between Void Calculus and Scar Algebra.

## Key Properties (to be proven in theorems.md)

1. **Irreducibility to belief revision**: Boundary-incomplete voids cannot be represented in AGM contraction.
2. **Irreducibility to probabilistic logic**: Void pressure dynamics have no equivalent in Bayesian belief updating.
3. **Expressiveness**: Void Calculus can distinguish "never discussed" from "discussed and resolved" from "actively avoided" — three states that collapse to one in standard negative-information frameworks.
4. **Convergence**: Under bounded input, the void set reaches a stable topology (finite voids with bounded total pressure).
