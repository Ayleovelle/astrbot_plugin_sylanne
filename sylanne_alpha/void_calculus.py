"""Void Calculus — Reference Implementation.

Absence as a first-class computational primitive. Voids are not derived
from what exists — they are independent objects with their own lifecycle,
pressure dynamics, and coupling to the Scar Algebra.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(slots=True)
class Void:
    """A first-class absence object."""
    boundary: list[bytes]
    depth: float = 0.0
    pressure: float = 0.0
    age: int = 0
    beta: float = 0.0
    _estimated_boundary_size: int = 5

    @property
    def is_ghost(self) -> bool:
        return len(self.boundary) == 0 and self.depth > 0

    @property
    def is_alive(self) -> bool:
        return len(self.boundary) > 0

    @property
    def boundary_completeness(self) -> float:
        if self._estimated_boundary_size <= 0:
            return 1.0
        return len(self.boundary) / (len(self.boundary) + self._estimated_boundary_size)

    def tick(self):
        """Age the void and accumulate pressure."""
        self.age += 1
        self.beta = self.boundary_completeness
        if self.depth > 0 and self.age > 0:
            self.pressure += self.depth * math.log(self.age + 1) * (1.0 - self.beta)

    def to_dict(self) -> dict[str, Any]:
        return {
            "boundary_count": len(self.boundary),
            "depth": self.depth,
            "pressure": self.pressure,
            "age": self.age,
            "beta": self.beta,
            "is_ghost": self.is_ghost,
        }


@dataclass(slots=True)
class VoidGhost:
    """Residue of a dead void — permanent, no pressure, affects future detection."""
    depth: float
    age_at_death: int
    last_boundary_hash: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "depth": self.depth,
            "age_at_death": self.age_at_death,
        }


class VoidSpace:
    """The Void Calculus engine: manages active voids, ghosts, and operations."""

    __slots__ = (
        "voids", "ghosts", "similarity_fn",
        "_contract_threshold", "_split_threshold", "_merge_threshold",
        "_detection_threshold", "_pressure_threshold",
        "_max_voids", "_tick",
    )

    def __init__(
        self,
        similarity_fn: Callable[[bytes, bytes], float],
        max_voids: int = 50,
        contract_threshold: float = 0.6,
        split_threshold: float = 0.3,
        merge_threshold: float = 0.7,
        detection_threshold: float = 0.4,
        pressure_threshold: float = 10.0,
    ):
        self.similarity_fn = similarity_fn
        self.voids: list[Void] = []
        self.ghosts: list[VoidGhost] = []
        self._contract_threshold = contract_threshold
        self._split_threshold = split_threshold
        self._merge_threshold = merge_threshold
        self._detection_threshold = detection_threshold
        self._pressure_threshold = pressure_threshold
        self._max_voids = max_voids
        self._tick = 0

    def process(self, event_vec: bytes, surprise: float, prev_similarity: float) -> dict[str, Any]:
        """Main entry: process one event through the void space.

        Args:
            event_vec: HDC-encoded event vector
            surprise: surprise value from predictive coding gate
            prev_similarity: similarity between current and previous event
        """
        self._tick += 1
        result: dict[str, Any] = {
            "voids_contracted": 0,
            "voids_deepened": 0,
            "voids_born": 0,
            "voids_died": 0,
            "total_pressure": 0.0,
            "coupling_events": [],
        }

        # Age all voids (pressure accumulates)
        for v in self.voids:
            v.tick()

        # Contract: event touches void boundaries
        result["voids_contracted"] = self._contract_all(event_vec)

        # Deepen: detect avoidance (sudden topic shift + high surprise)
        if prev_similarity < -self._detection_threshold and surprise > self._detection_threshold:
            result["voids_deepened"] = self._deepen_nearby(event_vec)

        # Genesis: detect new void formation
        if self._should_create_void(event_vec, surprise, prev_similarity):
            self._create_void(event_vec)
            result["voids_born"] = 1

        # Kill dead voids (empty boundary)
        result["voids_died"] = self._reap_dead()

        # Merge overlapping voids
        self._merge_pass()

        # Split voids with bimodal boundaries
        self._split_pass()

        # Compute coupling events (voids that exceed pressure threshold)
        for v in self.voids:
            if v.pressure > self._pressure_threshold:
                result["coupling_events"].append({
                    "pressure": v.pressure,
                    "depth": v.depth,
                    "boundary_size": len(v.boundary),
                })

        result["total_pressure"] = sum(v.pressure for v in self.voids)
        result["active_voids"] = len(self.voids)
        result["ghosts"] = len(self.ghosts)
        return result

    def _contract_all(self, event_vec: bytes) -> int:
        """Remove boundary points similar to the event."""
        contracted = 0
        for v in self.voids:
            before = len(v.boundary)
            v.boundary = [
                b for b in v.boundary
                if self.similarity_fn(event_vec, b) < self._contract_threshold
            ]
            if len(v.boundary) < before:
                contracted += 1
                removed = before - len(v.boundary)
                v.pressure *= (1.0 - removed / max(1, before))
        return contracted

    def _deepen_nearby(self, event_vec: bytes) -> int:
        """Deepen voids whose boundary is near the avoided topic."""
        deepened = 0
        for v in self.voids:
            for b in v.boundary:
                if self.similarity_fn(event_vec, b) > self._split_threshold:
                    v.depth += 0.1
                    deepened += 1
                    break
        return deepened

    def _should_create_void(self, event_vec: bytes, surprise: float, prev_sim: float) -> bool:
        """Void genesis: sudden deflection from a topic."""
        if len(self.voids) >= self._max_voids:
            return False
        if surprise < self._detection_threshold:
            return False
        if prev_sim > -self._detection_threshold:
            return False
        # Ghost sensitivity: lower threshold near previous voids
        ghost_bonus = sum(
            0.1 for g in self.ghosts if g.depth > 0.5
        )
        effective_threshold = max(0.1, self._detection_threshold - ghost_bonus)
        return surprise > effective_threshold

    def _create_void(self, deflected_from: bytes):
        """Birth a new void with the deflected-from vector as initial boundary."""
        v = Void(
            boundary=[deflected_from],
            depth=0.0,
            pressure=0.0,
            age=0,
            beta=0.0,
        )
        self.voids.append(v)

    def _reap_dead(self) -> int:
        """Kill voids with empty boundaries, leave ghosts."""
        dead = [v for v in self.voids if not v.boundary]
        for v in dead:
            if v.depth > 0:
                ghost = VoidGhost(
                    depth=v.depth,
                    age_at_death=v.age,
                    last_boundary_hash=hash(bytes(v.boundary[0])) if v.boundary else 0,
                )
                self.ghosts.append(ghost)
        self.voids = [v for v in self.voids if v.boundary]
        return len(dead)

    def _merge_pass(self):
        """Merge voids with overlapping boundaries."""
        if len(self.voids) < 2:
            return
        merged_indices: set[int] = set()
        new_voids: list[Void] = []
        for i in range(len(self.voids)):
            if i in merged_indices:
                continue
            for j in range(i + 1, len(self.voids)):
                if j in merged_indices:
                    continue
                if self._boundaries_overlap(self.voids[i], self.voids[j]):
                    merged = self._merge_two(self.voids[i], self.voids[j])
                    new_voids.append(merged)
                    merged_indices.add(i)
                    merged_indices.add(j)
                    break
            else:
                new_voids.append(self.voids[i])
        self.voids = new_voids

    def _boundaries_overlap(self, v1: Void, v2: Void) -> bool:
        for b1 in v1.boundary:
            for b2 in v2.boundary:
                if self.similarity_fn(b1, b2) > self._merge_threshold:
                    return True
        return False

    def _merge_two(self, v1: Void, v2: Void) -> Void:
        return Void(
            boundary=list(set(v1.boundary + v2.boundary)),
            depth=max(v1.depth, v2.depth),
            pressure=v1.pressure + v2.pressure,
            age=max(v1.age, v2.age),
            beta=0.0,
        )

    def _split_pass(self):
        """Split voids with bimodal boundaries."""
        new_voids: list[Void] = []
        for v in self.voids:
            if len(v.boundary) < 4:
                new_voids.append(v)
                continue
            cluster_a, cluster_b = self._try_split(v)
            if cluster_a is not None:
                new_voids.append(Void(
                    boundary=cluster_a, depth=v.depth,
                    pressure=v.pressure / 2, age=0, beta=0.0,
                ))
                new_voids.append(Void(
                    boundary=cluster_b, depth=v.depth,
                    pressure=v.pressure / 2, age=0, beta=0.0,
                ))
            else:
                new_voids.append(v)
        self.voids = new_voids

    def _try_split(self, v: Void) -> tuple[list[bytes] | None, list[bytes] | None]:
        """Simple 2-means split attempt on boundary vectors."""
        if len(v.boundary) < 4:
            return None, None
        pivot = v.boundary[0]
        near = [b for b in v.boundary if self.similarity_fn(b, pivot) > 0.5]
        far = [b for b in v.boundary if self.similarity_fn(b, pivot) <= 0.5]
        if not near or not far:
            return None, None
        avg_inter = sum(
            self.similarity_fn(n, f) for n in near[:3] for f in far[:3]
        ) / max(1, min(9, len(near) * len(far)))
        if avg_inter < self._split_threshold:
            return near, far
        return None, None

    def total_pressure(self) -> float:
        return sum(v.pressure for v in self.voids)

    def coupling_output(self) -> list[dict[str, float]]:
        """Voids exceeding pressure threshold — ready to wound the scar state."""
        return [
            {"pressure": v.pressure, "depth": v.depth, "dim_hint": len(v.boundary) % 8}
            for v in self.voids if v.pressure > self._pressure_threshold
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "voids": [v.to_dict() for v in self.voids],
            "ghosts": [g.to_dict() for g in self.ghosts],
            "tick": self._tick,
        }

    def diagnostics(self) -> dict[str, Any]:
        return {
            "active_voids": len(self.voids),
            "ghosts": len(self.ghosts),
            "total_pressure": self.total_pressure(),
            "max_depth": max((v.depth for v in self.voids), default=0.0),
            "tick": self._tick,
        }
