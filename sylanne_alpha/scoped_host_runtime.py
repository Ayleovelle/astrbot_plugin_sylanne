"""Scope-v1-only persistence adapters for the vendored Alpha host.

``AlphaRuntime`` remains the legacy file reader/exporter.  Active scoped hosts
receive this adapter instead, so neither host snapshots nor conversation buffers
can fall back to a raw session key, legacy KV, or ``*.alpha.json`` files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

from ._engine.sylanne_core.compute.kernel import AlphaKernel
from .host import SylanneAlphaHost
from .scope_repository import ScopedPersistenceGateway

if TYPE_CHECKING:
    from ._engine.sylanne_core.config import DimensionProfile
    from ._engine.sylanne_core.telemetry import DistillationSink
    from .memory_facade import ScopedMemoryFacade
    from .state_persistence import ScopedStatePersistence


class ScopedAlphaRuntime:
    """Alpha host runtime bound permanently to one scoped gateway generation."""

    def __init__(
        self,
        persistence: ScopedPersistenceGateway,
        profile: DimensionProfile | None,
        pel_enabled: bool,
    ) -> None:
        if type(persistence) is not ScopedPersistenceGateway:
            raise ValueError("persistence must be a ScopedPersistenceGateway")
        if type(pel_enabled) is not bool:
            raise ValueError("pel_enabled must be an exact bool")
        self._persistence = persistence
        self._profile = profile
        self._pel_enabled = pel_enabled
        self._generation = 0
        self._buffer_generation = 0
        self._observation_sink: Callable[[str, dict[str, Any]], None] | None = None

    @property
    def persistence(self) -> ScopedPersistenceGateway:
        """Expose the frozen capability for narrow diagnostics/test inspection."""

        return self._persistence

    def _require_session_token(self, session_key: str) -> None:
        if session_key != self._persistence.scope.storage_token:
            raise ValueError("host session token does not match frozen scope")

    def require_session_token(self, session_key: str) -> None:
        """Reject a raw key that does not name this exact frozen scope.

        This is intentionally public even though callers normally reach it via
        host operations.  The compatibility persistence layer uses it before
        deciding whether a legacy KV/file branch is even legal to enter.
        """

        self._require_session_token(session_key)

    def load(self, session_key: str) -> AlphaKernel:
        self._require_session_token(session_key)
        snapshot = self._persistence.load("host")
        if snapshot is None:
            return AlphaKernel.boot(
                session_key=session_key,
                profile=self._profile,
                pel_enabled=self._pel_enabled,
            )
        if snapshot.payload.get("session_key") != session_key:
            raise ValueError("host snapshot token does not match frozen scope")
        self._generation = snapshot.generation
        return AlphaKernel.restore(
            snapshot.payload,
            profile=self._profile,
            pel_enabled=self._pel_enabled,
        )

    def exists(self, session_key: str) -> bool:
        self._require_session_token(session_key)
        return self._persistence.load("host") is not None

    def save(self, kernel: AlphaKernel) -> None:
        self.save_snapshot(kernel.session_key, kernel.snapshot())

    def save_snapshot(self, session_key: str, snapshot: dict[str, Any]) -> None:
        self._require_session_token(session_key)
        if type(snapshot) is not dict:
            raise ValueError("host snapshot must be an exact dict")
        if snapshot.get("session_key") != session_key:
            raise ValueError("host snapshot token does not match frozen scope")
        self._generation = self._persistence.save(
            "host",
            expected_generation=self._generation,
            payload=snapshot,
        )
        if self._observation_sink is not None:
            self._observation_sink(session_key, snapshot)

    def load_buffer(self, session_key: str) -> dict[str, Any] | None:
        self._require_session_token(session_key)
        snapshot = self._persistence.load("conversation")
        if snapshot is None:
            return None
        persisted_token = snapshot.payload.get("session_key")
        if persisted_token is not None and persisted_token != session_key:
            raise ValueError("buffer session token does not match frozen scope")
        self._buffer_generation = snapshot.generation
        return dict(snapshot.payload)

    def save_buffer(self, session_key: str, buffer_data: dict[str, Any]) -> None:
        self._require_session_token(session_key)
        if type(buffer_data) is not dict:
            raise ValueError("buffer data must be an exact dict")
        persisted_token = buffer_data.get("session_key")
        if persisted_token is not None and persisted_token != session_key:
            raise ValueError("buffer session token does not match frozen scope")
        self._buffer_generation = self._persistence.save(
            "conversation",
            expected_generation=self._buffer_generation,
            payload=buffer_data,
        )

    def reset(self, session_key: str) -> AlphaKernel:
        self._require_session_token(session_key)
        kernel = AlphaKernel.boot(
            session_key=session_key,
            profile=self._profile,
            pel_enabled=self._pel_enabled,
        )
        self.save(kernel)
        return kernel

    def set_observation_sink(
        self,
        sink: Callable[[str, dict[str, Any]], None] | None,
    ) -> None:
        self._observation_sink = sink


@dataclass(frozen=True, slots=True)
class ScopedHostSession:
    """Complete, gateway-bound construction result for one inactive session.

    The host runtime owns the ``host`` and ``conversation`` components; the
    adjacent scoped state/facade own ``memory``.  Keeping those three objects
    together gives later ingress wiring one capability-only construction
    surface rather than a chance to reintroduce raw session-key persistence.
    """

    gateway: ScopedPersistenceGateway
    host: SylanneAlphaHost
    runtime: ScopedAlphaRuntime
    state: "ScopedStatePersistence"
    memory: "ScopedMemoryFacade"

    def __post_init__(self) -> None:
        if type(self.gateway) is not ScopedPersistenceGateway:
            raise ValueError("gateway must be a ScopedPersistenceGateway")
        if type(self.runtime) is not ScopedAlphaRuntime:
            raise ValueError("runtime must be a ScopedAlphaRuntime")
        if self.runtime.persistence is not self.gateway:
            raise ValueError("host runtime does not own the session gateway")
        self.runtime.require_session_token(self.host.session_key)

    def load_buffer(self) -> dict[str, Any] | None:
        """Load the conversation component without a raw-key fallback."""

        return self.runtime.load_buffer(self.host.session_key)

    def save_buffer(self, buffer_data: dict[str, Any]) -> None:
        """CAS-save the conversation component through this frozen runtime."""

        self.runtime.save_buffer(self.host.session_key, buffer_data)


@dataclass(frozen=True, slots=True)
class ScopedHostRuntime:
    """Construct one vendored host with a scope-v1-only runtime adapter.

    ``root`` is deliberately retained for the vendored host's constructor and
    compatibility diagnostics.  ``ScopedAlphaRuntime`` does not use it for any
    persistence operation.
    """

    persistence: ScopedPersistenceGateway
    root: Path | str
    profile: DimensionProfile | None
    pel_enabled: bool
    telemetry_sink: DistillationSink | None = None
    legacy_kv: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.persistence) is not ScopedPersistenceGateway:
            raise ValueError("persistence must be a ScopedPersistenceGateway")
        if type(self.pel_enabled) is not bool:
            raise ValueError("pel_enabled must be an exact bool")

    def build_host(self) -> SylanneAlphaHost:
        def runtime_factory(
            _root: Path,
            *,
            profile: DimensionProfile | None,
            pel_enabled: bool,
        ) -> ScopedAlphaRuntime:
            if pel_enabled is not self.pel_enabled:
                raise ValueError("public host changed scoped runtime parameters")
            # The public host applies the normal lite-profile default before
            # invoking its runtime factory.  Construct here—not before that
            # hook—so scoped and legacy hosts feed exactly the same profile to
            # AlphaKernel boot/restore.
            return ScopedAlphaRuntime(self.persistence, profile, pel_enabled)

        return SylanneAlphaHost(
            root=self.root,
            session_key=self.persistence.scope.storage_token,
            profile=self.profile,
            telemetry_sink=self.telemetry_sink,
            pel_enabled=self.pel_enabled,
            runtime_factory=runtime_factory,
        )

    def build_session(self) -> ScopedHostSession:
        """Build the host plus the only valid memory/buffer persistence seams."""

        from .memory_facade import ScopedMemoryFacade
        from .state_persistence import ScopedStatePersistence

        host = self.build_host()
        runtime = host.runtime
        if type(runtime) is not ScopedAlphaRuntime:
            raise RuntimeError("scoped host factory returned an unexpected runtime")
        state = ScopedStatePersistence(self.persistence)
        return ScopedHostSession(
            gateway=self.persistence,
            host=host,
            runtime=runtime,
            state=state,
            memory=ScopedMemoryFacade(state),
        )


__all__ = ["ScopedAlphaRuntime", "ScopedHostRuntime", "ScopedHostSession"]
