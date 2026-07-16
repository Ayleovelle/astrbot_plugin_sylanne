"""Non-deterministic runtime telemetry and hard isolation counters (design 16.1 / 16.3).

Two observability primitives that live entirely on the host side and never enter a
``CoreDecisionTrace`` or a state digest:

* :class:`IsolationCounters` — the seven counters of design 16.1 that must remain
  exactly zero for the whole life of the shadow.  The shadow only ever journals the
  closed v3 effect union, so a non-zero counter is proof of an isolation breach.
* :class:`RuntimeTelemetry` — the per-invocation record of design 16.3: stage
  timings, queue acceptance/drop, timeout, CAS/commit result, worker epoch, plugin
  instance, retry, load, profile-selection reason, and journal/export latency.  It
  is explicitly excluded from byte-identical replay and from every deterministic
  digest, and can be joined to a committed core trace only by
  ``(writer_epoch, state_generation_id, revision, turn_id)``.

Neither type is registered as a canonical DTO: telemetry is deliberately outside the
deterministic surface.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


# --------------------------------------------------------------------------- #
# Hard isolation counters (design 16.1) — all must remain zero.
# --------------------------------------------------------------------------- #


ISOLATION_COUNTER_NAMES = (
    "v3_external_reply_count",
    "v3_prompt_mutation_count",
    "v3_tool_call_count",
    "v3_body_tick_count",
    "v3_v2_memory_write_count",
    "v3_astrbot_history_write_count",
    "v3_extra_llm_call_count",
)


class IsolationCounters:
    """The seven design-16.1 counters; every one must stay exactly zero.

    The shadow supervisor never performs an external effect, so nothing in the
    normal path increments a counter.  ``increment`` exists only so a future
    breach detector has a single, auditable choke point; tests assert
    :meth:`all_zero` across every fault scenario.
    """

    __slots__ = ("_counts",)

    def __init__(self) -> None:
        self._counts: dict[str, int] = {name: 0 for name in ISOLATION_COUNTER_NAMES}

    def increment(self, name: str, amount: int = 1) -> None:
        if name not in self._counts:
            raise KeyError(f"{name!r} is not a declared isolation counter")
        if type(amount) is not int or amount < 1:
            raise ValueError("isolation counter increments must be positive integers")
        self._counts[name] += amount

    def get(self, name: str) -> int:
        if name not in self._counts:
            raise KeyError(f"{name!r} is not a declared isolation counter")
        return self._counts[name]

    def all_zero(self) -> bool:
        return all(value == 0 for value in self._counts.values())

    def total(self) -> int:
        return sum(self._counts.values())

    def as_dict(self) -> dict[str, int]:
        return dict(self._counts)

    def snapshot(self) -> tuple[tuple[str, int], ...]:
        return tuple((name, self._counts[name]) for name in ISOLATION_COUNTER_NAMES)


# --------------------------------------------------------------------------- #
# Runtime telemetry (design 16.3) — non-deterministic, never digested.
# --------------------------------------------------------------------------- #


#: Declared outcome tokens for one processed (or rejected) shadow invocation.
TELEMETRY_OUTCOMES = (
    "COMMITTED",
    "DROPPED_QUEUE_FULL",
    "DROPPED_ADMISSION_CLOSED",
    "DROPPED_DUPLICATE",
    "DROPPED_STALE",
    "DROPPED_OUT_OF_ORDER",
    "DROPPED_NO_BASE",
    "DROPPED_CORE_REJECTED",
    "DROPPED_CORE_ERROR",
    "DROPPED_COMMIT_CONFLICT",
    "DROPPED_STALE_EPOCH",
    "TIMEOUT",
    "SKIP",
    "REPOSITORY_HARD_STOP",
    "SHUTDOWN_DROPPED",
)


@dataclass(frozen=True, slots=True)
class RuntimeTelemetry:
    """One non-deterministic record for a single shadow invocation (design 16.3)."""

    turn_id: str
    session_key_id: str
    writer_epoch: int
    plugin_instance_id: str
    outcome: str
    profile_id: str
    profile_selection_reason: str
    load_level: int
    queue_accepted: bool
    dropped: bool
    timed_out: bool
    commit_status: str
    cas_committed: bool
    retry_count: int
    load_fill: float
    stage_timings_us: tuple = ()
    deadline_checkpoints: tuple = ()
    journal_latency_us: float = 0.0
    export_latency_us: float = 0.0

    def __post_init__(self) -> None:
        if type(self.outcome) is not str or self.outcome not in TELEMETRY_OUTCOMES:
            raise ValueError(f"{self.outcome!r} is not a declared telemetry outcome")
        if type(self.turn_id) is not str or type(self.session_key_id) is not str:
            raise TypeError("telemetry identifiers must be str")
        if type(self.writer_epoch) is not int or type(self.retry_count) is not int:
            raise TypeError("telemetry integer fields must be int")
        if type(self.load_level) is not int or not 0 <= self.load_level <= 5:
            raise ValueError("load_level must be an integer in [0,5]")
        for flag_name in ("queue_accepted", "dropped", "timed_out", "cas_committed"):
            if type(getattr(self, flag_name)) is not bool:
                raise TypeError(f"{flag_name} must be bool")

    def join_key(self, state_generation_id: str, revision: int) -> tuple:
        """The (writer_epoch, state_generation, revision, turn_id) core-trace join key."""

        return (self.writer_epoch, state_generation_id, revision, self.turn_id)


@dataclass(slots=True)
class TelemetrySink:
    """A bounded ring buffer of recent runtime telemetry for diagnostics only."""

    capacity: int = 256
    _buffer: deque = field(default_factory=deque, init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.capacity) is not int or self.capacity < 1:
            raise ValueError("telemetry sink capacity must be a positive integer")
        self._buffer = deque(maxlen=self.capacity)

    def record(self, telemetry: RuntimeTelemetry) -> None:
        if type(telemetry) is not RuntimeTelemetry:
            raise TypeError("only RuntimeTelemetry may be recorded")
        self._buffer.append(telemetry)

    def recent(self) -> tuple:
        return tuple(self._buffer)

    def last(self) -> RuntimeTelemetry | None:
        return self._buffer[-1] if self._buffer else None

    @property
    def count(self) -> int:
        return len(self._buffer)

    def clear(self) -> None:
        self._buffer.clear()


__all__ = [
    "ISOLATION_COUNTER_NAMES",
    "TELEMETRY_OUTCOMES",
    "IsolationCounters",
    "RuntimeTelemetry",
    "TelemetrySink",
]
