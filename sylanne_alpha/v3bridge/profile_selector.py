"""Load-pressure selection with hysteresis for the formula-v2 scalar bridge.

The bridge freezes exactly one versioned :class:`ComputeProfile` per turn before the
core runs.  Formula v2 has one live compute identity, ``FORMULA_V2_SCALAR``; pressure
levels 0..4 remain operational telemetry and hysteresis state, but must never revive
the retired SNN/STDP/reuse profiles.  Level 5 still skips the turn:

    scalar@pressure-0 -> scalar@pressure-1 -> ... -> scalar@pressure-4 -> SKIP_V3_TURN

Degradation is *immediate*: the selector jumps to the worst level whose
``(fill, age_ms, p95_ms)`` threshold is crossed.  Recovery is *slow*: it moves at
most one level up after 32 consecutive snapshots below 80% of the current level's
entry threshold.  A repository hard-stop always forces ``SKIP`` and records the turn
as ``DROPPED``.  Legacy profile IDs remain readable only at codec/core compatibility
boundaries; this live selector neither produces nor branches on them.

The selector is a pure, single-threaded bridge object (called only from the v3
worker between named stages); it never touches the core, a clock, or the filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass

from sylanne_alpha.v3bridge.models import LoadSnapshotV1, RepositoryAdmissionState
from sylanne_alpha.v3core import formula_v1 as formula
from sylanne_alpha.v3core.contracts import ComputeProfile


MATH_BACKEND_V1 = "scalar-v1"
SKIP_PROFILE_NAME = formula.REPOSITORY_HARD_STOP_PROFILE  # "SKIP_V3_TURN"
#: Pressure ladder identity: levels 0..4 all execute the one live scalar profile.
LADDER = (formula.FORMULA_V2_PROFILE_ID,) * 5 + (SKIP_PROFILE_NAME,)
#: Entry thresholds for ladder levels 1..5 as (fill, age_ms, p95_ms) tuples.
LOAD_THRESHOLDS = formula.LOAD_THRESHOLDS
RECOVERY_CONSECUTIVE_SNAPSHOTS = formula.RECOVERY_CONSECUTIVE_SNAPSHOTS
RECOVERY_THRESHOLD_RATIO = formula.RECOVERY_THRESHOLD_RATIO


def build_compute_profile(name: str) -> ComputeProfile:
    """Build a live formula-v2 profile; legacy IDs are decode-only."""

    if name == SKIP_PROFILE_NAME:
        raise ValueError("SKIP_V3_TURN has no compute profile")
    spec = formula.LIVE_COMPUTE_PROFILES.get(name)
    if spec is None:
        raise KeyError(f"{name!r} is not a declared compute profile")
    snn_enabled, ticks, stdp_enabled, reuse_last_summary = spec
    return ComputeProfile(
        profile_id=name,
        snn_enabled=snn_enabled,
        ticks=ticks,
        stdp_enabled=stdp_enabled,
        reuse_last_summary=reuse_last_summary,
        math_backend=MATH_BACKEND_V1,
        formula_version=formula.FORMULA_VERSION,
        model_version=formula.ACTION_MODEL_REVISION,
    )


def immediate_load_level(snapshot: LoadSnapshotV1) -> int:
    """The worst ladder level (0..5) whose entry threshold the snapshot crosses.

    A level is entered when *any* of fill/age/p95 reaches its threshold.  Level 0
    is nominal pressure.
    """

    level = 0
    for index, (fill_t, age_t, p95_t) in enumerate(LOAD_THRESHOLDS):
        if (
            snapshot.global_queue_fill >= fill_t
            or snapshot.oldest_job_age_ms >= age_t
            or snapshot.committed_compute_p95_ms >= p95_t
        ):
            level = index + 1
    return level


def _below_recovery_threshold(snapshot: LoadSnapshotV1, level: int) -> bool:
    """True iff the snapshot sits below 80% of ``level``'s entry threshold on all axes."""

    if level < 1:
        return True
    fill_t, age_t, p95_t = LOAD_THRESHOLDS[level - 1]
    return (
        snapshot.global_queue_fill < RECOVERY_THRESHOLD_RATIO * fill_t
        and snapshot.oldest_job_age_ms < RECOVERY_THRESHOLD_RATIO * age_t
        and snapshot.committed_compute_p95_ms < RECOVERY_THRESHOLD_RATIO * p95_t
    )


@dataclass(frozen=True, slots=True)
class ProfileSelection:
    """One frozen selection: the level, the chosen profile, and why."""

    level: int
    profile_name: str
    profile: ComputeProfile | None  # None iff skip
    skip: bool
    dropped: bool  # repository hard-stop records the turn DROPPED
    reason: str

    def __post_init__(self) -> None:
        if type(self.level) is not int or not 0 <= self.level <= 5:
            raise ValueError("selection level must be an integer in [0,5]")
        if self.skip and self.profile is not None:
            raise ValueError("a skipped selection must not carry a compute profile")
        if not self.skip and type(self.profile) is not ComputeProfile:
            raise TypeError("a non-skip selection must carry a ComputeProfile")


class ProfileSelector:
    """Stateful degrade-immediately / recover-slowly ladder selector (design 14.2)."""

    __slots__ = ("_level", "_recovery_run")

    def __init__(self) -> None:
        self._level = 0
        self._recovery_run = 0

    @property
    def level(self) -> int:
        return self._level

    def select(self, snapshot: LoadSnapshotV1) -> ProfileSelection:
        if type(snapshot) is not LoadSnapshotV1:
            raise TypeError("select requires a LoadSnapshotV1")

        # Repository hard-stop overrides the ladder entirely: SKIP + DROPPED.
        if snapshot.repository_admission is RepositoryAdmissionState.HARD_STOP:
            # A hard stop pins the effective level at SKIP without disturbing the
            # load-driven hysteresis state used once the repository reopens.
            self._level = 5
            self._recovery_run = 0
            return ProfileSelection(
                level=5,
                profile_name=SKIP_PROFILE_NAME,
                profile=None,
                skip=True,
                dropped=True,
                reason="REPOSITORY_HARD_STOP",
            )

        immediate = immediate_load_level(snapshot)
        if immediate >= self._level:
            self._level = immediate
            self._recovery_run = 0
        elif _below_recovery_threshold(snapshot, self._level):
            self._recovery_run += 1
            if self._recovery_run >= RECOVERY_CONSECUTIVE_SNAPSHOTS:
                self._level -= 1
                self._recovery_run = 0
        else:
            self._recovery_run = 0

        level = self._level
        if level >= 5:
            return ProfileSelection(
                level=5,
                profile_name=SKIP_PROFILE_NAME,
                profile=None,
                skip=True,
                dropped=False,
                reason="LOAD_SKIP",
            )

        name = formula.FORMULA_V2_PROFILE_ID
        reason = "NOMINAL" if level == 0 else "LOAD_PRESSURE"
        return ProfileSelection(
            level=level,
            profile_name=name,
            profile=build_compute_profile(name),
            skip=False,
            dropped=False,
            reason=reason,
        )


__all__ = [
    "LADDER",
    "LOAD_THRESHOLDS",
    "MATH_BACKEND_V1",
    "SKIP_PROFILE_NAME",
    "ProfileSelection",
    "ProfileSelector",
    "build_compute_profile",
    "immediate_load_level",
]
