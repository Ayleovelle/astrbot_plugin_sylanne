"""Closed effect vocabulary emitted by the deterministic core."""

from __future__ import annotations

from dataclasses import dataclass

from ..canonical import assert_exact_type, assert_valid_dto


@dataclass(frozen=True, slots=True)
class V3StateEffect:
    payload: bytes

    def __post_init__(self) -> None:
        assert_exact_type(self.payload, bytes, "payload")
        assert_valid_dto(self)


@dataclass(frozen=True, slots=True)
class V3TraceEffect:
    payload: bytes

    def __post_init__(self) -> None:
        assert_exact_type(self.payload, bytes, "payload")
        assert_valid_dto(self)


@dataclass(frozen=True, slots=True)
class V3MetricEffect:
    name: str
    value: int | float

    def __post_init__(self) -> None:
        assert_exact_type(self.name, str, "name")
        assert_exact_type(self.value, (int, float), "value")
        assert_valid_dto(self)
        if not self.name:
            raise ValueError("metric name must not be empty")


Effect = V3StateEffect | V3TraceEffect | V3MetricEffect
EFFECT_TYPES = (V3StateEffect, V3TraceEffect, V3MetricEffect)


@dataclass(frozen=True, slots=True)
class EffectBundle:
    effects: tuple[Effect, ...]

    def __post_init__(self) -> None:
        if type(self.effects) is not tuple or not all(type(effect) in EFFECT_TYPES for effect in self.effects):
            raise TypeError("EffectBundle accepts only the closed v3 effect union")
        assert_valid_dto(self)
