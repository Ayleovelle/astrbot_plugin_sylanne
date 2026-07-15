"""Frozen bridge-side admission observations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sylanne_alpha.v3core.canonical import assert_exact_type


class RepositoryAdmissionState(Enum):
    OPEN = "OPEN"
    HIGH_WATERMARK = "HIGH_WATERMARK"
    HARD_STOP = "HARD_STOP"


@dataclass(frozen=True, slots=True)
class LoadSnapshotV1:
    global_queue_fill: float
    oldest_job_age_ms: float
    committed_compute_p95_ms: float
    repository_admission: RepositoryAdmissionState

    def __post_init__(self) -> None:
        assert_exact_type(self.global_queue_fill, float, "global_queue_fill")
        assert_exact_type(self.oldest_job_age_ms, float, "oldest_job_age_ms")
        assert_exact_type(self.committed_compute_p95_ms, float, "committed_compute_p95_ms")
        assert_exact_type(self.repository_admission, RepositoryAdmissionState, "repository_admission")
        if not 0.0 <= self.global_queue_fill <= 1.0:
            raise ValueError("global_queue_fill must be in [0,1]")
        if self.oldest_job_age_ms < 0.0 or self.committed_compute_p95_ms < 0.0:
            raise ValueError("load durations must be non-negative")
