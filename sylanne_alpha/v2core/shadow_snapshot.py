"""Immutable, privacy-bounded v2 facts exported to the v3 shadow bridge.

This module owns copying only.  It never advances v2, reads AstrBot history,
touches the computation engine directly, or performs v3 repository work.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Any

V2_TURN_OBSERVATION_SCHEMA_V1 = "sylanne.v2.turn-observation.v1"
V2_SEED_SNAPSHOT_SCHEMA_V1 = "sylanne.v2.seed-snapshot.v1"
V2_RESPONSE_CANDIDATE_SCHEMA_V1 = "sylanne.v2.response-candidate.v1"

REPLY_KIND_TOKENS = ("SPEAK", "SILENT", "FALLBACK")
RESPONSE_ROUTE_KINDS = (
    "UNMATCHED",
    "SILENT",
    "ORDINARY_TEXT",
    "SEGMENTED_TEXT",
    "STREAMING",
    "TOOL",
    "MEDIA",
    "FALLBACK",
    "PROVIDER_FAILURE",
    "DELIVERY_FAILURE",
    "PROACTIVE",
)

FACT_PROVENANCE_VALUES = ("NONE", "AUTHORITATIVE_TURN")
FACT_PRIVACY_SCOPE_VALUES = (
    "NONE",
    "SESSION",
    "PERSON",
    "SAME_GROUP",
    "CROSS_GROUP",
)
_MAX_SAFE_INT = (1 << 63) - 1
_MAX_RESPONSE_PARTS = 256

_BODY_FLOAT_FIELDS = (
    "body_warmth",
    "body_tension",
    "body_repair_pressure",
    "body_intimacy_gravity",
    "body_surprise",
    "body_mean_surprise",
    "body_precision",
    "body_scar",
    "body_strain",
    "body_sovereignty",
    "body_exhaustion",
    "body_expression_drive",
    "body_threshold_drift",
    "body_void_pressure",
    "body_load",
    "body_plasticity",
    "body_boundary_pressure",
)
_TEXT_FLOAT_FIELDS = (
    "text_warm",
    "text_cold",
    "text_distress",
    "text_exclaim",
    "text_punct",
    "text_valence_cue",
    "text_engagement_cue",
)
_MEMORY_VALUE_FIELDS = (
    "memory_relevance",
    "memory_confidence",
    "memory_temperature",
    "memory_age_seconds",
)
_GROUP_VALUE_FIELDS = (
    "group_familiarity",
    "group_engagement",
    "group_tension",
    "group_activity",
)


class SeedSnapshotUnavailable(RuntimeError):
    """The live v2 seed could not be copied atomically and must be retried."""


def normalize_reply_kind_token(value: object) -> str | None:
    """Normalize current or pre-reload ReplyKind values to a stable token."""

    if value is None:
        return None
    candidates: tuple[object, ...]
    if isinstance(value, Enum):
        candidates = (value.name, value.value)
    else:
        candidates = (value,)
    for candidate in candidates:
        if type(candidate) is not str:
            continue
        token = candidate.strip().upper()
        if token in REPLY_KIND_TOKENS:
            return token
    raise ValueError("reply_kind is not a declared structured token")


def _require_exact(value: object, expected: type, name: str) -> None:
    if type(value) is not expected:
        raise TypeError(f"{name} must be {expected.__name__}, got {type(value).__name__}")


def _require_optional_float(value: object, name: str) -> None:
    if value is None:
        return
    if type(value) is not float:
        raise TypeError(f"{name} must be float or None, got {type(value).__name__}")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _require_optional_int(value: object, name: str) -> None:
    if value is None:
        return
    if type(value) is not int:
        raise TypeError(f"{name} must be int or None, got {type(value).__name__}")
    if not 0 <= value <= _MAX_SAFE_INT:
        raise ValueError(f"{name} must be a bounded non-negative integer")


def _require_optional_bool(value: object, name: str) -> None:
    if value is None:
        return
    if type(value) is not bool:
        raise TypeError(f"{name} must be bool or None, got {type(value).__name__}")


def _validate_fact_view(
    dto: object,
    *,
    prefix: str,
    value_fields: tuple[str, ...],
) -> None:
    values = tuple(getattr(dto, name) for name in value_fields)
    mask = getattr(dto, f"{prefix}_valid_mask")
    provenance = getattr(dto, f"{prefix}_provenance")
    revision = getattr(dto, f"{prefix}_source_revision")
    source_time = getattr(dto, f"{prefix}_source_time")
    privacy_scope = getattr(dto, f"{prefix}_privacy_scope")

    _require_exact(mask, int, f"{prefix}_valid_mask")
    if not 0 <= mask < (1 << len(values)):
        raise ValueError(f"{prefix}_valid_mask is outside its fixed-width mask")
    expected_mask = sum(1 << index for index, value in enumerate(values) if value is not None)
    if mask != expected_mask:
        raise ValueError(f"{prefix} values and valid mask disagree")

    _require_exact(provenance, str, f"{prefix}_provenance")
    if provenance not in FACT_PROVENANCE_VALUES:
        raise ValueError(f"{prefix}_provenance is not a declared token")
    _require_exact(privacy_scope, str, f"{prefix}_privacy_scope")
    if privacy_scope not in FACT_PRIVACY_SCOPE_VALUES:
        raise ValueError(f"{prefix}_privacy_scope is not a declared token")
    _require_optional_int(revision, f"{prefix}_source_revision")
    _require_optional_float(source_time, f"{prefix}_source_time")

    if revision is not None and revision < 0:
        raise ValueError(f"{prefix}_source_revision must be non-negative")
    if source_time is not None and source_time < 0.0:
        raise ValueError(f"{prefix}_source_time must be non-negative")
    if mask:
        if provenance == "NONE" or privacy_scope == "NONE":
            raise ValueError(f"{prefix} valid facts require provenance and privacy scope")
        if revision is None or source_time is None:
            raise ValueError(f"{prefix} valid facts require source revision and time")
    elif (
        provenance != "NONE"
        or privacy_scope != "NONE"
        or revision is not None
        or source_time is not None
    ):
        raise ValueError(f"{prefix} metadata cannot claim a source without valid facts")


@dataclass(frozen=True, slots=True)
class V2TurnObservationSnapshotV1:
    """Facts frozen at the normal request boundary, with no raw content or IDs."""

    schema_version: str = field(default=V2_TURN_OBSERVATION_SCHEMA_V1, init=False)

    body_warmth: float | None = None
    body_tension: float | None = None
    body_repair_pressure: float | None = None
    body_intimacy_gravity: float | None = None
    body_surprise: float | None = None
    body_mean_surprise: float | None = None
    body_precision: float | None = None
    body_scar: float | None = None
    body_strain: float | None = None
    body_sovereignty: float | None = None
    body_exhaustion: float | None = None
    body_expression_drive: float | None = None
    body_threshold_drift: float | None = None
    body_epoch: int | None = None
    body_void_pressure: float | None = None
    body_load: float | None = None
    body_plasticity: float | None = None
    body_boundary_pressure: float | None = None

    text_length: int | None = None
    text_warm: float | None = None
    text_cold: float | None = None
    text_distress: float | None = None
    text_question: bool | None = None
    text_exclaim: float | None = None
    text_punct: float | None = None
    text_valence_cue: float | None = None
    text_engagement_cue: float | None = None

    addressed: bool | None = None
    idle: bool | None = None
    proactive: bool | None = None
    history_present: bool | None = None
    gap_seconds: float | None = None

    memory_relevance: float | None = None
    memory_confidence: float | None = None
    memory_temperature: float | None = None
    memory_age_seconds: float | None = None
    memory_valid_mask: int = 0
    memory_provenance: str = "NONE"
    memory_source_revision: int | None = None
    memory_source_time: float | None = None
    memory_privacy_scope: str = "NONE"

    group_familiarity: float | None = None
    group_engagement: float | None = None
    group_tension: float | None = None
    group_activity: float | None = None
    group_valid_mask: int = 0
    group_provenance: str = "NONE"
    group_source_revision: int | None = None
    group_source_time: float | None = None
    group_privacy_scope: str = "NONE"

    def __post_init__(self) -> None:
        _require_exact(self.schema_version, str, "schema_version")
        if self.schema_version != V2_TURN_OBSERVATION_SCHEMA_V1:
            raise ValueError("unexpected turn observation schema")
        for name in (*_BODY_FLOAT_FIELDS, *_TEXT_FLOAT_FIELDS, *_MEMORY_VALUE_FIELDS, *_GROUP_VALUE_FIELDS):
            _require_optional_float(getattr(self, name), name)
        for name in ("body_epoch", "text_length"):
            value = getattr(self, name)
            _require_optional_int(value, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")
        for name in ("text_question", "addressed", "idle", "proactive", "history_present"):
            _require_optional_bool(getattr(self, name), name)
        _require_optional_float(self.gap_seconds, "gap_seconds")
        if self.gap_seconds is not None and self.gap_seconds < 0.0:
            raise ValueError("gap_seconds must be non-negative")
        if sum(value is True for value in (self.addressed, self.idle, self.proactive)) > 1:
            raise ValueError("addressed, idle, and proactive facts are mutually exclusive")
        if self.memory_age_seconds is not None and self.memory_age_seconds < 0.0:
            raise ValueError("memory_age_seconds must be non-negative")
        _validate_fact_view(self, prefix="memory", value_fields=_MEMORY_VALUE_FIELDS)
        _validate_fact_view(self, prefix="group", value_fields=_GROUP_VALUE_FIELDS)


@dataclass(frozen=True, slots=True)
class V2SeedSnapshotV1:
    """One-time, finite-only v2 initial facts for a future v3 migration."""

    schema_version: str = field(default=V2_SEED_SNAPSHOT_SCHEMA_V1, init=False)

    body_warmth: float | None = None
    body_tension: float | None = None
    body_repair_pressure: float | None = None
    body_intimacy_gravity: float | None = None
    body_surprise: float | None = None
    body_mean_surprise: float | None = None
    body_precision: float | None = None
    body_scar: float | None = None
    body_strain: float | None = None
    body_sovereignty: float | None = None
    body_exhaustion: float | None = None
    body_expression_drive: float | None = None
    body_threshold_drift: float | None = None
    body_epoch: int | None = None
    body_void_pressure: float | None = None
    body_load: float | None = None
    body_plasticity: float | None = None
    body_boundary_pressure: float | None = None

    emotion_fast_ema: float | None = None
    emotion_slow_ema: float | None = None
    emotion_unexpressed: float | None = None

    user_hesitation_ema: float | None = None
    user_bond_ema: float | None = None
    user_style_len: float | None = None
    user_style_punct: float | None = None
    user_style_warmth: float | None = None

    narrative_ossification_warmth: float | None = None
    narrative_ossification_tension: float | None = None
    narrative_ossification_repair_pressure: float | None = None
    narrative_baseline_curiosity: float | None = None
    narrative_baseline_warmth_bias: float | None = None
    narrative_baseline_sovereignty_guard: float | None = None
    narrative_baseline_patience: float | None = None

    adaptation_style_len: float | None = None
    adaptation_style_punct: float | None = None
    adaptation_style_warmth: float | None = None
    adaptation_expr_verbosity: float | None = None
    adaptation_expr_formality: float | None = None
    adaptation_expr_directness: float | None = None
    adaptation_coping_accompany_silence: float | None = None
    adaptation_coping_gentle_probe: float | None = None
    adaptation_coping_affirm_empathize: float | None = None
    adaptation_coping_self_disclose: float | None = None

    def __post_init__(self) -> None:
        _require_exact(self.schema_version, str, "schema_version")
        if self.schema_version != V2_SEED_SNAPSHOT_SCHEMA_V1:
            raise ValueError("unexpected seed snapshot schema")
        for item in fields(self):
            if item.name == "schema_version":
                continue
            if item.name == "body_epoch":
                _require_optional_int(self.body_epoch, "body_epoch")
                if self.body_epoch is not None and self.body_epoch < 0:
                    raise ValueError("body_epoch must be non-negative")
            else:
                _require_optional_float(getattr(self, item.name), item.name)


@dataclass(frozen=True, slots=True)
class V2ResponseCandidateV1:
    """Structured route evidence only; never generated text or a host response."""

    schema_version: str = field(default=V2_RESPONSE_CANDIDATE_SCHEMA_V1, init=False)
    route_kind: str = "UNMATCHED"
    reply_kind: str | None = None
    part_count: int = 0
    correlation_proven: bool = False
    after_message_sent: bool = False
    all_segments_succeeded: bool | None = None
    proactive_dispatched: bool | None = None
    duplicate_terminal_claim: bool = False

    def __post_init__(self) -> None:
        _require_exact(self.schema_version, str, "schema_version")
        if self.schema_version != V2_RESPONSE_CANDIDATE_SCHEMA_V1:
            raise ValueError("unexpected response candidate schema")
        _require_exact(self.route_kind, str, "route_kind")
        if self.route_kind not in RESPONSE_ROUTE_KINDS:
            raise ValueError("route_kind is not a declared token")
        object.__setattr__(self, "reply_kind", normalize_reply_kind_token(self.reply_kind))
        _require_exact(self.part_count, int, "part_count")
        if not 0 <= self.part_count <= _MAX_RESPONSE_PARTS:
            raise ValueError("part_count must be a bounded non-negative integer")
        for name in (
            "correlation_proven",
            "after_message_sent",
            "duplicate_terminal_claim",
        ):
            _require_exact(getattr(self, name), bool, name)
        _require_optional_bool(self.all_segments_succeeded, "all_segments_succeeded")
        _require_optional_bool(self.proactive_dispatched, "proactive_dispatched")

        if self.reply_kind == "SPEAK" and self.route_kind != "STREAMING" and self.part_count < 1:
            raise ValueError("SPEAK requires positive part_count")
        if self.reply_kind == "SILENT" and self.part_count != 0:
            raise ValueError("SILENT requires part_count zero")
        if self.reply_kind is None and self.part_count != 0:
            raise ValueError("part_count requires a structured reply kind")
        if self.route_kind == "UNMATCHED":
            if self.correlation_proven:
                raise ValueError("UNMATCHED route cannot claim proven correlation")
        elif not self.correlation_proven:
            raise ValueError(f"{self.route_kind} route requires proven correlation")

        if self.after_message_sent and self.route_kind != "ORDINARY_TEXT":
            raise ValueError("after_message_sent is valid only for ORDINARY_TEXT attempt evidence")
        if self.all_segments_succeeded is not None and self.route_kind != "SEGMENTED_TEXT":
            raise ValueError("all_segments_succeeded is valid only for SEGMENTED_TEXT")
        if self.proactive_dispatched is not None and self.route_kind != "PROACTIVE":
            raise ValueError("proactive_dispatched is valid only for PROACTIVE")

        if self.route_kind == "SILENT":
            if self.reply_kind != "SILENT" or self.part_count != 0:
                raise ValueError("SILENT route requires only a SILENT zero-part decision")
            if self.after_message_sent or self.all_segments_succeeded is not None:
                raise ValueError("SILENT route cannot contain delivery evidence")
        elif self.route_kind == "ORDINARY_TEXT":
            if self.reply_kind != "SPEAK" or self.part_count < 1:
                raise ValueError("ORDINARY_TEXT requires a positive-part SPEAK candidate")
        elif self.route_kind == "SEGMENTED_TEXT":
            if self.reply_kind != "SPEAK" or self.part_count < 1:
                raise ValueError("SEGMENTED_TEXT requires at least one SPEAK segment")
        elif self.route_kind in {"STREAMING", "MEDIA", "DELIVERY_FAILURE"}:
            if self.reply_kind != "SPEAK":
                raise ValueError(f"{self.route_kind} requires a SPEAK candidate")
        elif self.route_kind == "FALLBACK":
            if self.reply_kind != "FALLBACK":
                raise ValueError("FALLBACK route requires FALLBACK reply kind")
        elif self.route_kind == "PROVIDER_FAILURE":
            if self.reply_kind is not None or self.part_count != 0:
                raise ValueError("PROVIDER_FAILURE cannot contain a reply candidate")
        elif self.route_kind == "PROACTIVE":
            if self.reply_kind is not None or self.part_count != 0:
                raise ValueError("PROACTIVE cannot contain a v2 reply candidate")
        if self.route_kind != "PROACTIVE" and self.proactive_dispatched is not None:
            raise ValueError("only PROACTIVE may carry dispatched evidence")


def _finite_number(value: object) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        converted = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return converted if math.isfinite(converted) else None


def _nonnegative_int(value: object) -> int | None:
    if type(value) is not int or not 0 <= value <= _MAX_SAFE_INT:
        return None
    return value


def _exact_dict(value: object, source: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise SeedSnapshotUnavailable(f"{source} must be an owned dict")
    return value


def _domain_state(domains: dict[str, Any], name: str) -> dict[str, Any]:
    try:
        domain = domains[name]
        dumper = getattr(domain, "to_dict")
        if not callable(dumper):
            raise TypeError
        state = dumper()
    except Exception:
        raise SeedSnapshotUnavailable(f"{name} seed source failed") from None
    return _exact_dict(state, f"{name} seed state")


def _nested_number(state: dict[str, Any], section: str, name: str) -> float | None:
    nested = state.get(section)
    if type(nested) is not dict:
        raise SeedSnapshotUnavailable(f"{section} seed section is unavailable")
    return _finite_number(nested.get(name))


def _body_number(body: object | None, name: str) -> float | None:
    if body is None:
        raise SeedSnapshotUnavailable("body seed source is unavailable")
    try:
        value = getattr(body, name)
    except Exception:
        raise SeedSnapshotUnavailable(f"body {name} seed field failed") from None
    return _finite_number(value)


def _body_epoch(body: object | None) -> int | None:
    if body is None:
        raise SeedSnapshotUnavailable("body seed source is unavailable")
    try:
        value = getattr(body, "epoch")
    except Exception:
        raise SeedSnapshotUnavailable("body epoch seed field failed") from None
    return _nonnegative_int(value)


def freeze_seed_snapshot_owned(rt: object) -> V2SeedSnapshotV1:
    """Copy a seed while the caller already owns the production v2 turn lock."""

    runtime = _exact_dict(rt, "runtime")
    domains = _exact_dict(runtime.get("domains"), "runtime domains")
    try:
        body_port = runtime["body_port"]
        observe = getattr(body_port, "observe")
        if not callable(observe):
            raise TypeError
        body = observe()
        if body is None:
            raise TypeError
    except Exception:
        raise SeedSnapshotUnavailable("body seed source failed") from None

    emotion = _domain_state(domains, "emotion")
    user = _domain_state(domains, "usermodel")
    narrative = _domain_state(domains, "narrative")
    adaptation = _domain_state(domains, "adaptation")

    return V2SeedSnapshotV1(
        body_warmth=_body_number(body, "warmth"),
        body_tension=_body_number(body, "tension"),
        body_repair_pressure=_body_number(body, "repair_pressure"),
        body_intimacy_gravity=_body_number(body, "intimacy_gravity"),
        body_surprise=_body_number(body, "surprise"),
        body_mean_surprise=_body_number(body, "mean_surprise"),
        body_precision=_body_number(body, "precision"),
        body_scar=_body_number(body, "scar"),
        body_strain=_body_number(body, "strain"),
        body_sovereignty=_body_number(body, "sovereignty"),
        body_exhaustion=_body_number(body, "exhaustion"),
        body_expression_drive=_body_number(body, "expression_drive"),
        body_threshold_drift=_body_number(body, "threshold_drift"),
        body_epoch=_body_epoch(body),
        body_void_pressure=_body_number(body, "void_pressure"),
        body_load=_body_number(body, "load"),
        body_plasticity=_body_number(body, "plasticity"),
        body_boundary_pressure=_body_number(body, "boundary_pressure"),
        emotion_fast_ema=_finite_number(emotion.get("fast_ema")),
        emotion_slow_ema=_finite_number(emotion.get("slow_ema")),
        emotion_unexpressed=_finite_number(emotion.get("unexpressed")),
        user_hesitation_ema=_finite_number(user.get("hesitation_ema")),
        user_bond_ema=_finite_number(user.get("bond_ema")),
        user_style_len=_nested_number(user, "style_sketch", "len"),
        user_style_punct=_nested_number(user, "style_sketch", "punct"),
        user_style_warmth=_nested_number(user, "style_sketch", "warmth"),
        narrative_ossification_warmth=_nested_number(narrative, "ossification", "warmth"),
        narrative_ossification_tension=_nested_number(narrative, "ossification", "tension"),
        narrative_ossification_repair_pressure=_nested_number(
            narrative, "ossification", "repair_pressure"
        ),
        narrative_baseline_curiosity=_nested_number(narrative, "baseline_traits", "curiosity"),
        narrative_baseline_warmth_bias=_nested_number(
            narrative, "baseline_traits", "warmth_bias"
        ),
        narrative_baseline_sovereignty_guard=_nested_number(
            narrative, "baseline_traits", "sovereignty_guard"
        ),
        narrative_baseline_patience=_nested_number(narrative, "baseline_traits", "patience"),
        adaptation_style_len=_nested_number(adaptation, "style_target", "len"),
        adaptation_style_punct=_nested_number(adaptation, "style_target", "punct"),
        adaptation_style_warmth=_nested_number(adaptation, "style_target", "warmth"),
        adaptation_expr_verbosity=_nested_number(adaptation, "expr", "verbosity"),
        adaptation_expr_formality=_nested_number(adaptation, "expr", "formality"),
        adaptation_expr_directness=_nested_number(adaptation, "expr", "directness"),
        adaptation_coping_accompany_silence=_nested_number(
            adaptation, "coping", "accompany_silence"
        ),
        adaptation_coping_gentle_probe=_nested_number(adaptation, "coping", "gentle_probe"),
        adaptation_coping_affirm_empathize=_nested_number(
            adaptation, "coping", "affirm_empathize"
        ),
        adaptation_coping_self_disclose=_nested_number(
            adaptation, "coping", "self_disclose"
        ),
    )


async def freeze_seed_snapshot_fallback(
    plugin: object,
    session_key: str,
) -> V2SeedSnapshotV1:
    """Freeze from the live cache under ``plugin._session_lock(session_key)``."""

    _require_exact(session_key, str, "session_key")
    if not session_key:
        raise ValueError("session_key must not be empty")
    lock_factory = getattr(plugin, "_session_lock", None)
    if not callable(lock_factory):
        raise RuntimeError("plugin._session_lock is required for fallback seed freeze")
    lock = lock_factory(session_key)
    if not hasattr(lock, "__aenter__") or not hasattr(lock, "__aexit__"):
        raise TypeError("plugin._session_lock must return an async context manager")

    async with lock:
        try:
            runtimes = getattr(plugin, "_v2core_runtimes")
        except Exception:
            raise SeedSnapshotUnavailable("v2 runtime cache is unavailable") from None
        runtime_map = _exact_dict(runtimes, "v2 runtime cache")
        if session_key not in runtime_map:
            raise SeedSnapshotUnavailable("runtime is unavailable for seed freeze")
        return freeze_seed_snapshot_owned(runtime_map[session_key])


__all__ = [
    "FACT_PRIVACY_SCOPE_VALUES",
    "FACT_PROVENANCE_VALUES",
    "REPLY_KIND_TOKENS",
    "RESPONSE_ROUTE_KINDS",
    "SeedSnapshotUnavailable",
    "V2_RESPONSE_CANDIDATE_SCHEMA_V1",
    "V2_SEED_SNAPSHOT_SCHEMA_V1",
    "V2_TURN_OBSERVATION_SCHEMA_V1",
    "V2ResponseCandidateV1",
    "V2SeedSnapshotV1",
    "V2TurnObservationSnapshotV1",
    "freeze_seed_snapshot_fallback",
    "freeze_seed_snapshot_owned",
    "normalize_reply_kind_token",
]
