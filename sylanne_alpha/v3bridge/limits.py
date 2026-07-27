"""Frozen bridge resource ceilings and plugin-wide budget arithmetic."""

from __future__ import annotations

from dataclasses import dataclass


MAX_ACTIVE_SESSIONS = 64
MAX_REPOSITORY_SESSIONS = 96
MAX_STATE_BYTES = 64 * 1024
TARGET_STATE_BYTES = 48 * 1024
MAX_TRACE_BYTES = 16 * 1024
MAX_GLOBAL_QUEUE = 128
MAX_PER_SESSION_QUEUE = 4
MAX_TURN_REGISTRY = 1024
TURN_REGISTRY_TTL_SECONDS = 15 * 60
WORKER_COUNT = 1
TRACE_SEGMENT_BYTES = 2 * 1024 * 1024
TRACE_SEGMENT_COUNT = 2
TELEMETRY_SEGMENT_BYTES = 1 * 1024 * 1024
TELEMETRY_SEGMENT_COUNT = 4
MAX_STAGING_BYTES = 4 * 1024 * 1024
V3_DEFAULT_BUDGET_BYTES = 24_000_000
NON_V3_RESERVE_BYTES = 2_000_000
DISK_HIGH_WATERMARK_BYTES = 22_000_000
DISK_HARD_WATERMARK_BYTES = 24_000_000

PLUGIN_DATA_CAP_BYTES = 50_000_000
MIN_ADMISSION_HARD_BYTES = 4 * 1024 * 1024
HIGH_WATERMARK_HEADROOM_BYTES = 2_000_000
RESOURCE_CEILINGS_ARE_SIMULTANEOUS_RESERVATIONS = False


@dataclass(frozen=True, slots=True)
class EffectiveV3Budget:
    hard_bytes: int
    high_bytes: int
    admission_enabled: bool

    def __post_init__(self) -> None:
        if type(self.hard_bytes) is not int or type(self.high_bytes) is not int:
            raise TypeError("budget byte counts must have exact type int")
        if type(self.admission_enabled) is not bool:
            raise TypeError("admission_enabled must have exact type bool")


def effective_v3_budget(
    non_v3_bytes: int,
    plugin_cap_bytes: int = PLUGIN_DATA_CAP_BYTES,
) -> EffectiveV3Budget:
    """Compute the v3 namespace cap without reserving individual ceilings."""
    if type(non_v3_bytes) is not int or type(plugin_cap_bytes) is not int:
        raise TypeError("budget inputs must be integer byte counts")
    if non_v3_bytes < 0 or plugin_cap_bytes < 0:
        raise ValueError("budget inputs must be non-negative")
    hard = max(
        0,
        min(
            V3_DEFAULT_BUDGET_BYTES,
            plugin_cap_bytes - non_v3_bytes - NON_V3_RESERVE_BYTES,
        ),
    )
    high = max(0, hard - HIGH_WATERMARK_HEADROOM_BYTES)
    return EffectiveV3Budget(
        hard_bytes=hard,
        high_bytes=high,
        admission_enabled=hard >= MIN_ADMISSION_HARD_BYTES,
    )


def effective_v3_hard_cap(non_v3_bytes: int, plugin_cap_bytes: int = PLUGIN_DATA_CAP_BYTES) -> int:
    return effective_v3_budget(non_v3_bytes, plugin_cap_bytes).hard_bytes


def effective_v3_high_watermark(non_v3_bytes: int, plugin_cap_bytes: int = PLUGIN_DATA_CAP_BYTES) -> int:
    return effective_v3_budget(non_v3_bytes, plugin_cap_bytes).high_bytes
