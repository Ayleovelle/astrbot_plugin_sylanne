"""Sylanne serialization validator — zero-dependency implementation.

Provides a JSON Schema (draft 2020-12 compatible) as a Python dict and a minimal
recursive validator that checks structure, types, numeric bounds, and patterns
without requiring the `jsonschema` library.

Public API:
    SYLANNE_SCHEMA: dict — the schema definition
    validate(document) -> (bool, list[str])
    validate_cross_field(document) -> (bool, list[str])
    migrate(document, target_version) -> dict
"""

from __future__ import annotations

import copy
import re
from typing import Any

# ---------------------------------------------------------------------------
# Schema definition (mirrors schemas/sylanne_interchange_v1.json)
# ---------------------------------------------------------------------------

_SEMVER_PATTERN = (
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)(\.(0|[1-9]\d*))?(-[a-zA-Z0-9.]+)?(\+[a-zA-Z0-9.]+)?$"
)

SYLANNE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://sylanne.dev/schemas/interchange/v1",
    "title": "Sylanne Affective State Interchange Document",
    "type": "object",
    "required": [
        "sylanne_version",
        "schema_version",
        "session_key",
        "personality",
        "state",
        "scars",
        "metadata",
    ],
    "additionalProperties": False,
    "properties": {
        "sylanne_version": {
            "type": "string",
            "pattern": _SEMVER_PATTERN,
        },
        "schema_version": {
            "type": "integer",
            "minimum": 1,
        },
        "session_key": {
            "type": "string",
            "minLength": 1,
        },
        "personality": {
            "type": "object",
            "required": ["openness", "warmth", "assertiveness", "stability", "sensitivity"],
            "additionalProperties": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "properties": {
                "openness": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "warmth": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "assertiveness": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "stability": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "sensitivity": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            },
        },
        "state": {
            "type": "object",
            "required": ["primary", "mood", "confidence", "epoch"],
            "additionalProperties": False,
            "properties": {
                "primary": {
                    "type": "object",
                    "required": ["valence", "arousal", "dominance"],
                    "additionalProperties": False,
                    "properties": {
                        "valence": {"type": "number", "minimum": -1.0, "maximum": 1.0},
                        "arousal": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "dominance": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    },
                },
                "mood": {
                    "type": "object",
                    "required": ["valence", "arousal", "dominance"],
                    "additionalProperties": False,
                    "properties": {
                        "valence": {"type": "number", "minimum": -1.0, "maximum": 1.0},
                        "arousal": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "dominance": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    },
                },
                "delta": {
                    "type": "object",
                    "required": ["valence", "arousal", "dominance"],
                    "additionalProperties": False,
                    "properties": {
                        "valence": {"type": "number", "minimum": -2.0, "maximum": 2.0},
                        "arousal": {"type": "number", "minimum": -1.0, "maximum": 1.0},
                        "dominance": {"type": "number", "minimum": -1.0, "maximum": 1.0},
                    },
                },
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "epoch": {"type": "integer", "minimum": 0},
            },
        },
        "scars": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["dimension", "intensity", "created_at", "source_tag"],
                "additionalProperties": False,
                "properties": {
                    "dimension": {"type": "integer", "minimum": 0},
                    "intensity": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "created_at": {"type": "integer", "minimum": 0},
                    "source_tag": {"type": "string", "minLength": 1},
                },
            },
        },
        "hot_pool": {
            "type": "object",
            "required": ["temperature", "volume", "pressure"],
            "additionalProperties": True,
            "properties": {
                "temperature": {"type": "number", "minimum": 0.0},
                "volume": {"type": "number", "minimum": 0.0},
                "pressure": {"type": "number", "minimum": 0.0},
            },
        },
        "metadata": {
            "type": "object",
        },
    },
}


# Current schema version
CURRENT_SCHEMA_VERSION = 1

# Optional fields at the top level (not in "required" but allowed)
_OPTIONAL_TOP_LEVEL = {"hot_pool"}


# ---------------------------------------------------------------------------
# Minimal recursive validator (zero external dependencies)
# ---------------------------------------------------------------------------


def _check_type(value: Any, expected: str) -> bool:
    """Check if value matches the expected JSON Schema type."""
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def _validate_node(
    value: Any,
    schema: dict[str, Any],
    path: str,
    errors: list[str],
) -> None:
    """Recursively validate a value against a schema node."""
    # Type check
    if "type" in schema:
        if not _check_type(value, schema["type"]):
            errors.append(f"{path}: expected type '{schema['type']}', got {type(value).__name__}")
            return  # Cannot validate further if type is wrong

    # String constraints
    if schema.get("type") == "string" and isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: string length {len(value)} < minLength {schema['minLength']}")
        if "pattern" in schema and not re.match(schema["pattern"], value):
            errors.append(f"{path}: string does not match pattern '{schema['pattern']}'")

    # Numeric constraints
    if schema.get("type") in ("number", "integer") and isinstance(value, (int, float)):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: value {value} < minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: value {value} > maximum {schema['maximum']}")

    # Object constraints
    if schema.get("type") == "object" and isinstance(value, dict):
        # Required fields
        for req in schema.get("required", []):
            if req not in value:
                errors.append(f"{path}: missing required field '{req}'")

        # additionalProperties check
        additional = schema.get("additionalProperties")
        declared_props = set(schema.get("properties", {}).keys())

        if additional is False:
            # Only allow declared properties (+ optional schema-level ones at root)
            for key in value:
                if key not in declared_props:
                    errors.append(f"{path}: unexpected property '{key}'")
        elif isinstance(additional, dict):
            # Additional properties must conform to the sub-schema
            for key in value:
                if key not in declared_props:
                    _validate_node(value[key], additional, f"{path}.{key}", errors)

        # Validate declared properties
        props = schema.get("properties", {})
        for prop_name, prop_schema in props.items():
            if prop_name in value:
                _validate_node(value[prop_name], prop_schema, f"{path}.{prop_name}", errors)

    # Array constraints
    if schema.get("type") == "array" and isinstance(value, list):
        items_schema = schema.get("items")
        if items_schema:
            for i, item in enumerate(value):
                _validate_node(item, items_schema, f"{path}[{i}]", errors)


def validate(document: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate a document against SYLANNE_SCHEMA.

    Returns:
        (is_valid, list_of_errors). Empty error list means valid.
    """
    errors: list[str] = []
    if not isinstance(document, dict):
        errors.append("$: document must be a dict")
        return False, errors

    _validate_node(document, SYLANNE_SCHEMA, "$", errors)
    is_valid = len(errors) == 0
    return is_valid, errors


# ---------------------------------------------------------------------------
# Cross-field (semantic) validation
# ---------------------------------------------------------------------------


def validate_cross_field(document: dict[str, Any]) -> tuple[bool, list[str]]:
    """Semantic validations beyond structural schema.

    Checks:
        - All personality values in [0, 1]
        - Personality is not degenerate (all-zero or all-one)
        - Scars ordered by created_at (ascending, equal timestamps allowed)
        - epoch is non-negative integer
        - schema_version matches expected (CURRENT_SCHEMA_VERSION)

    Returns:
        (is_valid, list_of_errors). Empty error list means valid.
    """
    errors: list[str] = []

    # Personality range and degeneracy
    personality = document.get("personality")
    if isinstance(personality, dict):
        trait_values: list[float] = []
        for key, val in personality.items():
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                if val < 0.0 or val > 1.0:
                    errors.append(f"personality.{key}: value {val} outside [0, 1]")
                trait_values.append(float(val))
        if trait_values and all(v == 0.0 for v in trait_values):
            errors.append("personality_all_zero: all trait values are 0.0")
        if trait_values and all(v == 1.0 for v in trait_values):
            errors.append("personality_all_one: all trait values are 1.0")

    # Scar temporal ordering
    scars = document.get("scars")
    if isinstance(scars, list):
        for i in range(1, len(scars)):
            prev_ts = scars[i - 1].get("created_at", 0)
            curr_ts = scars[i].get("created_at", 0)
            if curr_ts < prev_ts:
                errors.append(
                    f"scar_order: scar[{i}].created_at={curr_ts} < "
                    f"scar[{i - 1}].created_at={prev_ts}"
                )

    # Epoch must be non-negative integer
    state = document.get("state")
    if isinstance(state, dict):
        epoch = state.get("epoch")
        if epoch is not None:
            if not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < 0:
                errors.append(f"state.epoch: must be non-negative integer, got {epoch!r}")

        # Initial state rule: confidence must be 0 when epoch is 0
        if epoch == 0:
            confidence = state.get("confidence")
            if confidence is not None and confidence != 0.0:
                errors.append("initial_confidence: confidence must be 0.0 when epoch is 0")

    # schema_version check
    sv = document.get("schema_version")
    if sv is not None and sv != CURRENT_SCHEMA_VERSION:
        errors.append(f"schema_version: expected {CURRENT_SCHEMA_VERSION}, got {sv}")

    is_valid = len(errors) == 0
    return is_valid, errors


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def migrate(
    document: dict[str, Any], target_version: int = CURRENT_SCHEMA_VERSION
) -> dict[str, Any]:
    """Migrate a document from its schema_version to target_version.

    Currently only version 1 exists. The framework supports future versions
    via chained version checks with setdefault() for new fields.

    Args:
        document: The document to migrate.
        target_version: The desired schema_version.

    Returns:
        A new dict representing the migrated document.

    Raises:
        ValueError: If no migration path exists.
    """
    current = document.get("schema_version", 1)
    if current == target_version:
        return copy.deepcopy(document)

    result = copy.deepcopy(document)

    # Future migration example:
    # if current < 2:
    #     result.setdefault("new_field", default_value)
    #     result["schema_version"] = 2
    #     current = 2

    if result.get("schema_version") != target_version:
        raise ValueError(
            f"No migration path from schema_version {document.get('schema_version')} "
            f"to {target_version}."
        )

    return result
