"""Idle, zero-LLM, read-only replay sidecar (design section 13).

Replay is a strictly read-only evaluation pass over immutable
:class:`~sylanne_alpha.v3core.state.models.ExperienceRecord` snapshots.  It may
compute counterfactual, calibration, and novelty metrics, but it can never mutate
slow state, thresholds, SNN weights/eligibility, baselines, action beliefs,
pending outcomes, or any other ``V3_STATE``.  Metric emission is capped and
idempotent by ``(buffer_entry_digest, evaluator_version)``.  Replay-STDP is
prohibited: this module imports no weight-mutating entry point and returns only
metrics.

Pure stdlib ``hashlib``/``struct`` over frozen tuples: no NumPy, no I/O, no
clocks, no randomness, and no learning update of any kind.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from math import isfinite

from ..canonical import assert_exact_type
from ..state.models import ACTION_COUNT, ExperienceRecord


@dataclass(frozen=True, slots=True)
class ReplayMetric:
    """One read-only replay metric, identified by ``(entry_digest, evaluator_version)``.

    Self-validating pure result DTO (not registered): replay metrics never cross
    the persistence boundary as cognitive state.
    """

    entry_digest: str
    evaluator_version: str
    name: str
    value: float

    def __post_init__(self) -> None:
        assert_exact_type(self.entry_digest, str, "entry_digest")
        assert_exact_type(self.evaluator_version, str, "evaluator_version")
        assert_exact_type(self.name, str, "name")
        assert_exact_type(self.value, float, "value")
        if len(self.entry_digest) != 64:
            raise ValueError("entry_digest must be a 256-bit hex digest")
        if not self.evaluator_version or not self.name:
            raise ValueError("evaluator_version and name must not be empty")
        if not isfinite(self.value):
            raise ValueError("metric value must be finite")


_ENTRY_DOMAIN = b"SYL3\x01EXP\x00"
_S16_SCALE = 32767.0
REPLAY_METRIC_NAMES = ("counterfactual_action_match", "feature_energy", "reward_magnitude")


def experience_entry_digest(record: object) -> str:
    """Return the domain-separated canonical digest identifying one buffer entry."""

    if type(record) is not ExperienceRecord:
        raise TypeError("record must have exact type ExperienceRecord")
    chunks = [
        _ENTRY_DOMAIN,
        record.observation_digest,
        struct.pack(">%dh" % len(record.encoded_features), *record.encoded_features),
        struct.pack(">%dh" % len(record.workspace_broadcast), *record.workspace_broadcast),
        struct.pack(">B", record.shadow_action_code),
        struct.pack(">B", record.actual_action_code),
        struct.pack(">%dB" % len(record.next_observation), *record.next_observation),
        struct.pack(">%dh" % len(record.reward_components), *record.reward_components),
        struct.pack(">I", record.trace_revision),
        record.trace_turn_digest,
    ]
    return hashlib.sha256(b"".join(chunks)).hexdigest()


def _mean_abs_ratio(values: tuple) -> float:
    if not values:
        return 0.0
    return sum(abs(value) for value in values) / (len(values) * _S16_SCALE)


def _entry_metrics(record: ExperienceRecord, entry_digest: str, evaluator_version: str) -> list[ReplayMetric]:
    metrics: list[ReplayMetric] = []
    shadow = record.shadow_action_code
    actual = record.actual_action_code
    # Counterfactual agreement is censored unless both actions are known.
    if 0 <= shadow < ACTION_COUNT and 0 <= actual < ACTION_COUNT:
        metrics.append(
            ReplayMetric(
                entry_digest=entry_digest,
                evaluator_version=evaluator_version,
                name="counterfactual_action_match",
                value=1.0 if shadow == actual else 0.0,
            )
        )
    metrics.append(
        ReplayMetric(
            entry_digest=entry_digest,
            evaluator_version=evaluator_version,
            name="feature_energy",
            value=_mean_abs_ratio(record.encoded_features),
        )
    )
    metrics.append(
        ReplayMetric(
            entry_digest=entry_digest,
            evaluator_version=evaluator_version,
            name="reward_magnitude",
            value=_mean_abs_ratio(record.reward_components),
        )
    )
    return metrics


def replay_experiences(experiences: object, evaluator_version: str) -> tuple:
    """Compute read-only replay metrics, deduplicated by metric identity.

    Metrics are idempotent by ``(entry_digest, evaluator_version, name)`` so
    repeated entries or repeated calls never double-emit.  Nothing in the input
    buffer is mutated and no cognitive state is produced.
    """

    if type(evaluator_version) is not str or not evaluator_version:
        raise ValueError("evaluator_version must be a non-empty string")
    if type(experiences) is not tuple:
        raise TypeError("experiences must be a tuple of ExperienceRecord")

    seen: set = set()
    metrics: list[ReplayMetric] = []
    for record in experiences:
        if type(record) is not ExperienceRecord:
            raise TypeError("every experience must have exact type ExperienceRecord")
        entry_digest = experience_entry_digest(record)
        for metric in _entry_metrics(record, entry_digest, evaluator_version):
            key = (metric.entry_digest, metric.evaluator_version, metric.name)
            if key in seen:
                continue
            seen.add(key)
            metrics.append(metric)
    return tuple(metrics)


__all__ = [
    "REPLAY_METRIC_NAMES",
    "ReplayMetric",
    "experience_entry_digest",
    "replay_experiences",
]
