"""Scope-v1 persistence for the V2 and V3 shadow snapshots.

The legacy V2/V3 paths carry a transport/session-shaped key through several
storage backends.  This adapter intentionally exposes none of that surface:
one instance is constructed with one immutable ``ScopedPersistenceGateway``
and can persist only the two allowlisted engine components below.

Keeping this adapter small and capability-shaped lets scoped construction avoid
retrofitting identity checks around legacy KV/file helpers.
"""

from __future__ import annotations

import asyncio
import json
import math
from dataclasses import asdict
from typing import Any, Coroutine

from .scope_repository import Snapshot, ScopedPersistenceGateway, StaleScopeWrite


class ScopedEnginePersistence:
    """Persist V2 and V3 shadow snapshots through one frozen scope gateway.

    Component generations are intentionally independent.  A V2 write cannot
    advance or overwrite the V3-shadow lineage, and vice versa.  The gateway
    itself owns all Bot/Persona/Session lifecycle validation; this class never
    receives, derives, or falls back to a transport/session/storage key.
    """

    _V2_COMPONENT = "v2"
    _V3_SHADOW_COMPONENT = "v3-shadow"
    _COMPONENTS = frozenset({_V2_COMPONENT, _V3_SHADOW_COMPONENT})

    # Scope-v1 already contains the authority record for these values.  Engine
    # payloads must not smuggle a second raw identity/fallback selector into a
    # durable snapshot.  The check is recursive and intentionally catches the
    # common separator variants too (``session-key`` / ``session_key``).
    _RAW_IDENTITY_KEYS = frozenset(
        {
            "session",
            "session_id",
            "session_key",
            "session_ref",
            "session_token",
            "transport_session_token",
            "storage",
            "storage_key",
            "storage_token",
            "token",
            "raw_token",
            "raw_session",
            "raw_session_key",
        }
    )

    def __init__(self, persistence: ScopedPersistenceGateway) -> None:
        # ``type`` rather than ``isinstance`` keeps the capability boundary
        # exact: a lookalike object cannot provide a current/default scope.
        if type(persistence) is not ScopedPersistenceGateway:
            raise ValueError("persistence must be a ScopedPersistenceGateway")
        self._persistence = persistence
        self._generation_by_component = {
            self._V2_COMPONENT: 0,
            self._V3_SHADOW_COMPONENT: 0,
        }

    @property
    def persistence(self) -> ScopedPersistenceGateway:
        """The sole durable-state capability owned by this adapter."""

        return self._persistence

    @classmethod
    def _require_component(cls, component: str) -> str:
        if component not in cls._COMPONENTS:
            raise ValueError("unsupported scoped engine component")
        return component

    @classmethod
    def _normalise_payload_input(cls, component: str, payload: object) -> object:
        """Accept exactly the public V2 seed DTO or a JSON object mapping."""

        if component == cls._V2_COMPONENT:
            # ``V2SeedSnapshotV1`` is a frozen, validated public snapshot
            # contract.  Convert it to an ordinary object before applying the
            # same recursive JSON/capability checks as a caller-supplied map.
            from .v2core.shadow_snapshot import V2SeedSnapshotV1

            if type(payload) is V2SeedSnapshotV1:
                return asdict(payload)
        return payload

    @classmethod
    def _validate_json_value(cls, value: object) -> None:
        """Require exact JSON types and exact string object keys recursively."""

        if value is None or type(value) in (str, bool, int):
            return
        if type(value) is float:
            if math.isfinite(value):
                return
            raise ValueError("payload must be JSON-safe")
        if type(value) is list:
            for item in value:
                cls._validate_json_value(item)
            return
        if type(value) is dict:
            for key, nested in value.items():
                if type(key) is not str:
                    raise ValueError("payload object keys must be exact str")
                canonical_key = key.lower().replace("-", "_")
                if canonical_key in cls._RAW_IDENTITY_KEYS:
                    raise ValueError("payload must not contain raw scope identity")
                cls._validate_json_value(nested)
            return
        raise ValueError("payload must be JSON-safe")

    @classmethod
    def _canonical_payload(cls, component: str, payload: object) -> dict[str, object]:
        """Validate and deep-copy a snapshot through canonical JSON bytes."""

        candidate = cls._normalise_payload_input(component, payload)
        if type(candidate) is not dict:
            raise ValueError("payload must be an exact JSON object")
        cls._validate_json_value(candidate)
        schema_version = candidate.get("schema_version")
        if type(schema_version) is not str or not schema_version:
            raise ValueError("payload schema_version must be a non-empty str")
        # Sorting gives a canonical object order, while this JSON round trip
        # severs every nested mutable reference held by the caller.
        encoded = json.dumps(
            candidate,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        decoded = json.loads(encoded)
        if type(decoded) is not dict:  # Defensive: the top-level check above proves it.
            raise ValueError("payload must be an exact JSON object")
        return decoded

    def _load(self, component: str) -> Snapshot | None:
        name = self._require_component(component)
        snapshot = self._persistence.load(name)
        if snapshot is None:
            self._generation_by_component[name] = 0
            return None
        payload = self._canonical_payload(name, snapshot.payload)
        self._generation_by_component[name] = snapshot.generation
        # Repository snapshots deliberately expose their payload as a normal
        # dict.  Return a new one so a consumer cannot mutate an object that a
        # future delayed save accidentally captures.
        return Snapshot(generation=snapshot.generation, payload=payload)

    def _save(
        self,
        component: str,
        payload: object,
        *,
        gateway: ScopedPersistenceGateway | None = None,
        expected_generation: int | None = None,
    ) -> int:
        name = self._require_component(component)
        captured_gateway = self._persistence if gateway is None else gateway
        if type(captured_gateway) is not ScopedPersistenceGateway:
            raise ValueError("persistence must be a ScopedPersistenceGateway")
        captured_generation = (
            self._generation_by_component[name] if expected_generation is None else expected_generation
        )
        if type(captured_generation) is not int or captured_generation < 0:
            raise ValueError("expected generation must be a non-negative int")
        snapshot_payload = self._canonical_payload(name, payload)
        next_generation = captured_gateway.save(
            name,
            expected_generation=captured_generation,
            payload=snapshot_payload,
        )
        if captured_gateway is self._persistence and self._generation_by_component[name] == captured_generation:
            self._generation_by_component[name] = next_generation
        return next_generation

    def load_v2(self) -> Snapshot | None:
        """Load only this gateway's V2 component and its independent CAS head."""

        return self._load(self._V2_COMPONENT)

    def save_v2(self, payload: object) -> int:
        """Direct V2 save: stale scope/CAS failures deliberately propagate."""

        return self._save(self._V2_COMPONENT, payload)

    def load_v3_shadow(self) -> Snapshot | None:
        """Load only this gateway's V3-shadow component and CAS head."""

        return self._load(self._V3_SHADOW_COMPONENT)

    def save_v3_shadow(self, payload: object) -> int:
        """Direct V3-shadow save: stale scope/CAS failures deliberately propagate."""

        return self._save(self._V3_SHADOW_COMPONENT, payload)

    def _save_delayed(
        self,
        component: str,
        payload: object,
    ) -> Coroutine[Any, Any, bool]:
        """Return a pre-captured delayed save; discard stale work.

        This is deliberately a regular method returning an inner coroutine.
        Capturing the capability, CAS head, and JSON bytes happens when the
        caller requests delayed work, not later when a task first gets CPU.
        """

        name = self._require_component(component)
        # Capture all three before yielding.  In particular, ``payload`` is
        # canonicalized now rather than read again after another turn changes
        # its nested values or the adapter's component generation.
        gateway = self._persistence
        generation = self._generation_by_component[name]
        snapshot_payload = self._canonical_payload(name, payload)
        async def commit() -> bool:
            await asyncio.sleep(0)
            try:
                self._save(
                    name,
                    snapshot_payload,
                    gateway=gateway,
                    expected_generation=generation,
                )
            except StaleScopeWrite:
                # Delayed work may never discover a replacement/latest scope.
                # It is valid only for the precise generation it captured above.
                return False
            return True

        return commit()

    @staticmethod
    def _require_delay(delay_seconds: object) -> float:
        if isinstance(delay_seconds, bool) or not isinstance(delay_seconds, (int, float)):
            raise ValueError("delay_seconds must be a non-negative finite number")
        delay = float(delay_seconds)
        if not math.isfinite(delay) or delay < 0.0:
            raise ValueError("delay_seconds must be a non-negative finite number")
        return delay

    def _schedule_delayed_save(
        self,
        component: str,
        payload: object,
        *,
        delay_seconds: float,
    ) -> asyncio.Task[bool]:
        """Create a delayed write after capturing gateway, CAS head, and JSON now."""

        name = self._require_component(component)
        delay = self._require_delay(delay_seconds)
        gateway = self._persistence
        generation = self._generation_by_component[name]
        snapshot_payload = self._canonical_payload(name, payload)

        async def commit() -> bool:
            await asyncio.sleep(delay)
            try:
                self._save(
                    name,
                    snapshot_payload,
                    gateway=gateway,
                    expected_generation=generation,
                )
            except StaleScopeWrite:
                return False
            return True

        return asyncio.create_task(commit(), name=f"scoped_engine_save_{name}")

    def schedule_v2_save(self, payload: object, *, delay_seconds: float = 0.0) -> asyncio.Task[bool]:
        """Schedule an immutable V2 snapshot; stale work is discarded."""

        return self._schedule_delayed_save(
            self._V2_COMPONENT,
            payload,
            delay_seconds=delay_seconds,
        )

    def schedule_v3_shadow_save(
        self,
        payload: object,
        *,
        delay_seconds: float = 0.0,
    ) -> asyncio.Task[bool]:
        """Schedule an immutable V3-shadow snapshot; stale work is discarded."""

        return self._schedule_delayed_save(
            self._V3_SHADOW_COMPONENT,
            payload,
            delay_seconds=delay_seconds,
        )

    def save_v2_delayed(self, payload: object) -> Coroutine[Any, Any, bool]:
        """Save a captured V2 snapshot, returning ``False`` when it went stale."""

        return self._save_delayed(self._V2_COMPONENT, payload)

    def save_v3_shadow_delayed(self, payload: object) -> Coroutine[Any, Any, bool]:
        """Save a captured V3-shadow snapshot, returning ``False`` if stale."""

        return self._save_delayed(self._V3_SHADOW_COMPONENT, payload)


__all__ = ["ScopedEnginePersistence"]
