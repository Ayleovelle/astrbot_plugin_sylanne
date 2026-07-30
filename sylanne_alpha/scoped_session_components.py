"""Gateway-only persistence for scoped session component owners.

The life, rhythm, social, and scheduler constructors use this small capability
adapter when their owning runtime supplies a frozen scope gateway.  It accepts
no raw session identifier, storage path, or legacy KV object.
"""

from __future__ import annotations

import asyncio
import json
import math

from .scope_repository import ScopedPersistenceGateway, StaleScopeWrite


_COMPONENTS = frozenset({"life", "rhythm", "social", "scheduler"})


class ScopedSessionComponentStore:
    """CAS-backed snapshots for four exact components of one frozen scope.

    The constructor captures an immutable :class:`ScopedPersistenceGateway`.
    Consequently, delayed work cannot find a newer runtime after a reset: it
    can only commit through the original gateway, where the repository rejects
    it as stale.
    """

    __slots__ = ("_gateway", "_generations")

    def __init__(self, gateway: ScopedPersistenceGateway) -> None:
        if type(gateway) is not ScopedPersistenceGateway:
            raise ValueError("gateway must be a ScopedPersistenceGateway")
        self._gateway = gateway
        self._generations: dict[str, int] = {
            component: 0 for component in _COMPONENTS
        }

    @property
    def gateway(self) -> ScopedPersistenceGateway:
        """Return the one immutable capability owned by this store."""

        return self._gateway

    @classmethod
    def _require_component(cls, component: object) -> str:
        if type(component) is not str or component not in _COMPONENTS:
            raise ValueError("unsupported scoped session component")
        return component

    @staticmethod
    def _snapshot_payload(payload: object) -> dict[str, object]:
        """Make one canonical, JSON-safe deep copy before persistence work.

        JSON encoding is both the schema boundary and the copy mechanism.  It
        rejects NaN, arbitrary objects, and other non-durable values before a
        caller can schedule work that would otherwise observe later mutation.
        """

        if type(payload) is not dict:
            raise ValueError("payload must be an exact dict")
        ScopedSessionComponentStore._require_exact_object_keys(payload)
        try:
            encoded = json.dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            copied = json.loads(encoded)
        except (TypeError, ValueError) as exc:
            raise ValueError("payload must be canonical JSON") from exc
        if type(copied) is not dict:  # Defensive: the exact-dict input forbids it.
            raise ValueError("payload must be an exact dict")
        return copied

    @staticmethod
    def _require_exact_object_keys(value: object) -> None:
        """Reject lossy JSON-object keys before the JSON round trip.

        Python's encoder silently stringifies integer mapping keys.  That would
        turn a caller's payload into a different document, so every nested JSON
        object must already use an exact ``str`` key.  ``json.dumps`` remains
        responsible for rejecting cycles and unsupported container values.
        """

        pending = [value]
        inspected: set[int] = set()
        while pending:
            current = pending.pop()
            if isinstance(current, dict):
                object_id = id(current)
                if object_id in inspected:
                    continue
                inspected.add(object_id)
                for key, nested in current.items():
                    if type(key) is not str:
                        raise ValueError("JSON object keys must be exact str")
                    pending.append(nested)
            elif isinstance(current, (list, tuple)):
                object_id = id(current)
                if object_id in inspected:
                    continue
                inspected.add(object_id)
                pending.extend(current)

    @staticmethod
    def _require_delay(delay_seconds: object) -> float:
        if isinstance(delay_seconds, bool) or not isinstance(
            delay_seconds,
            (int, float),
        ):
            raise ValueError("delay_seconds must be a non-negative finite number")
        delay = float(delay_seconds)
        if not math.isfinite(delay) or delay < 0.0:
            raise ValueError("delay_seconds must be a non-negative finite number")
        return delay

    def generation(self, component: str) -> int:
        """Return this store's last loaded/saved CAS generation for a component."""

        name = self._require_component(component)
        return self._generations[name]

    def load(self, component: str) -> dict[str, object] | None:
        """Load exactly one component through the frozen gateway only."""

        name = self._require_component(component)
        snapshot = self._gateway.load(name)
        if snapshot is None:
            self._generations[name] = 0
            return None
        payload = self._snapshot_payload(snapshot.payload)
        self._generations[name] = snapshot.generation
        return payload

    def save(self, component: str, payload: dict[str, object]) -> int:
        """Directly save one component and surface stale writers to the caller."""

        name = self._require_component(component)
        captured_payload = self._snapshot_payload(payload)
        expected_generation = self._generations[name]
        next_generation = self._gateway.save(
            name,
            expected_generation=expected_generation,
            payload=captured_payload,
        )
        if self._generations[name] == expected_generation:
            self._generations[name] = next_generation
        return next_generation

    def schedule_save(
        self,
        component: str,
        payload: dict[str, object],
        *,
        delay_seconds: float,
    ) -> asyncio.Task[bool]:
        """Schedule a write bound to the captured gateway, CAS, and payload.

        A direct stale write is an error.  A delayed stale write is intentionally
        disposable: it returns ``False`` rather than searching for any current
        session, scope, or replacement component snapshot.
        """

        name = self._require_component(component)
        delay = self._require_delay(delay_seconds)
        gateway = self._gateway
        expected_generation = self._generations[name]
        captured_payload = self._snapshot_payload(payload)

        async def delayed_save() -> bool:
            await asyncio.sleep(delay)
            try:
                next_generation = gateway.save(
                    name,
                    expected_generation=expected_generation,
                    payload=captured_payload,
                )
            except StaleScopeWrite:
                return False
            if gateway is self._gateway and self._generations[name] == expected_generation:
                self._generations[name] = next_generation
            return True

        return asyncio.create_task(
            delayed_save(),
            name=f"scoped_session_component_save_{name}",
        )


__all__ = ["ScopedSessionComponentStore"]
