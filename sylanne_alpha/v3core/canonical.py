"""Canonical serialization and the pure-core DTO boundary."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any, TypeVar


_T = TypeVar("_T", bound=type[Any])
_DECLARED_DTO_TYPES: frozenset[type[Any]] = frozenset()
_DECLARED_ENUM_TYPES: frozenset[type[Enum]] = frozenset()
_REGISTRY_SEALED = False


def declared_dto(cls: _T) -> _T:
    """Reject dynamic DTO registration; the core allowlist is bootstrapped once."""
    raise RuntimeError("the canonical type registry is sealed")


def declared_enum(cls: _T) -> _T:
    """Reject dynamic enum registration; the core allowlist is bootstrapped once."""
    raise RuntimeError("the canonical type registry is sealed")


def _install_declared_types(
    *,
    dto_types: tuple[type[Any], ...],
    enum_types: tuple[type[Enum], ...],
) -> None:
    """Install and seal the explicit pure-core canonical vocabulary exactly once."""
    global _DECLARED_DTO_TYPES, _DECLARED_ENUM_TYPES, _REGISTRY_SEALED
    if _REGISTRY_SEALED:
        raise RuntimeError("the canonical type registry is sealed")
    for dto_type in dto_types:
        params = getattr(dto_type, "__dataclass_params__", None)
        if params is None or not params.frozen:
            raise TypeError("declared DTOs must be frozen dataclasses")
    for enum_type in enum_types:
        if not issubclass(enum_type, Enum):
            raise TypeError("declared enums must inherit enum.Enum")
        for member in enum_type:
            assert_valid_dto(member.value)
    if len(dto_types) != len(set(dto_types)) or len(enum_types) != len(set(enum_types)):
        raise ValueError("canonical type allowlists must not contain duplicates")
    _DECLARED_DTO_TYPES = frozenset(dto_types)
    _DECLARED_ENUM_TYPES = frozenset(enum_types)
    _REGISTRY_SEALED = True


def assert_exact_type(value: object, expected: type[Any] | tuple[type[Any], ...], field_name: str) -> None:
    """Require an exact semantic type so bool cannot impersonate an integer."""
    expected_types = expected if type(expected) is tuple else (expected,)
    if type(value) not in expected_types:
        names = ", ".join(item.__qualname__ for item in expected_types)
        raise TypeError(f"{field_name} must have exact type {names}")


def assert_valid_dto(value: object, _active: set[int] | None = None) -> None:
    """Reject every value outside the recursively closed DTO type set."""
    if value is None or type(value) in (bool, int, str, bytes):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("DTO floats must be finite")
        return
    if callable(value):
        raise TypeError("callables are not deterministic DTO values")
    if isinstance(value, Enum):
        if type(value) not in _DECLARED_ENUM_TYPES:
            raise TypeError(f"undeclared enum type: {type(value).__qualname__}")
        assert_valid_dto(value.value, _active)
        return
    if type(value) is tuple:
        active = set() if _active is None else _active
        marker = id(value)
        if marker in active:
            raise ValueError("cyclic DTO value")
        active.add(marker)
        try:
            for item in value:
                assert_valid_dto(item, active)
        finally:
            active.remove(marker)
        return
    if is_dataclass(value):
        value_type = type(value)
        if value_type not in _DECLARED_DTO_TYPES:
            raise TypeError(f"undeclared dataclass type: {value_type.__qualname__}")
        active = set() if _active is None else _active
        marker = id(value)
        if marker in active:
            raise ValueError("cyclic DTO value")
        active.add(marker)
        try:
            for field in fields(value):
                assert_valid_dto(getattr(value, field.name), active)
        finally:
            active.remove(marker)
        return
    raise TypeError(f"unsupported DTO type: {type(value).__qualname__}")


def _canonical_value(value: object) -> object:
    if value is None or type(value) in (bool, int, str):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("canonical JSON does not accept non-finite floats")
        return value
    if type(value) is bytes:
        return {"$bytes_hex": value.hex()}
    if isinstance(value, Enum):
        return _canonical_value(value.value)
    if is_dataclass(value):
        return {field.name: _canonical_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, Mapping):
        if not all(type(key) is str for key in value):
            raise TypeError("canonical JSON object keys must be strings")
        return {key: _canonical_value(value[key]) for key in sorted(value)}
    raise TypeError(f"unsupported canonical JSON type: {type(value).__qualname__}")


def canonical_json_bytes(value: object) -> bytes:
    """Encode a supported structure as stable UTF-8 JSON bytes."""
    normalized = _canonical_value(value)
    return json.dumps(
        normalized,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    """Return the lowercase SHA-256 digest of canonical JSON bytes."""
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()
