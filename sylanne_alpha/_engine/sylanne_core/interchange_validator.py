"""Sylanne interchange format validator.

Validates JSON state documents against the formal schema (draft 2020-12)
and enforces cross-field semantic rules that JSON Schema alone cannot express.

Requires: jsonschema >= 4.20 (with referencing support for draft 2020-12).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator, ValidationError
except ImportError as e:
    raise ImportError(
        "jsonschema >= 4.20 is required for interchange validation. "
        "Install with: pip install 'jsonschema[format]>=4.20'"
    ) from e

_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"
_SCHEMA_V1_PATH = _SCHEMA_DIR / "sylanne_interchange_v1.json"

# Cache the compiled validator
_validator_cache: dict[int, Draft202012Validator] = {}


def _load_schema(version: int = 1) -> dict[str, Any]:
    """Load the JSON Schema for the given schema_version."""
    if version != 1:
        raise ValueError(f"Unsupported schema_version: {version}. Only version 1 is defined.")
    with open(_SCHEMA_V1_PATH, encoding="utf-8") as f:
        return json.load(f)  # type: ignore[no-any-return]


def _get_validator(version: int = 1) -> Draft202012Validator:
    """Return a cached Draft202012Validator instance."""
    if version not in _validator_cache:
        schema = _load_schema(version)
        Draft202012Validator.check_schema(schema)
        _validator_cache[version] = Draft202012Validator(schema)
    return _validator_cache[version]


# ---------------------------------------------------------------------------
# Cross-field semantic rules (beyond JSON Schema expressiveness)
# ---------------------------------------------------------------------------


class SemanticValidationError(Exception):
    """Raised when a document passes schema validation but violates semantic rules."""

    def __init__(self, rule: str, message: str):
        self.rule = rule
        super().__init__(f"[{rule}] {message}")


def _check_initial_state_confidence(doc: dict[str, Any]) -> None:
    """Rule: confidence must be 0 when epoch is 0 (initial state)."""
    state = doc.get("state", {})
    if state.get("epoch", -1) == 0 and state.get("confidence", -1) != 0.0:
        raise SemanticValidationError(
            "initial_confidence",
            "confidence must be 0.0 when epoch is 0 (initial state).",
        )


def _check_personality_degeneracy(doc: dict[str, Any]) -> None:
    """Rule: personality traits must not all be 0 or all be 1 (degenerate)."""
    traits = doc.get("personality", {})
    values = [v for v in traits.values() if isinstance(v, (int, float))]
    if not values:
        return
    if all(v == 0.0 for v in values):
        raise SemanticValidationError(
            "personality_all_zero",
            "All personality trait values are 0.0 — degenerate configuration.",
        )
    if all(v == 1.0 for v in values):
        raise SemanticValidationError(
            "personality_all_one",
            "All personality trait values are 1.0 — degenerate configuration.",
        )


def _check_scar_temporal_order(doc: dict[str, Any]) -> None:
    """Rule: scars must be ordered by created_at (ascending)."""
    scars = doc.get("scars", [])
    for i in range(1, len(scars)):
        if scars[i]["created_at"] < scars[i - 1]["created_at"]:
            raise SemanticValidationError(
                "scar_order",
                f"Scar at index {i} has created_at={scars[i]['created_at']} "
                f"< previous scar created_at={scars[i - 1]['created_at']}. "
                "Scars must be ordered by creation time.",
            )


_SEMANTIC_CHECKS = [
    _check_initial_state_confidence,
    _check_personality_degeneracy,
    _check_scar_temporal_order,
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate(doc: dict[str, Any], *, semantic: bool = True) -> list[str]:
    """Validate a Sylanne interchange document.

    Args:
        doc: The parsed JSON document to validate.
        semantic: If True, also run cross-field semantic checks.

    Returns:
        Empty list on success; list of error messages on failure.

    Raises:
        SemanticValidationError: If semantic=True and a semantic rule is violated.
            (Only raised for semantic violations; schema errors are returned as strings.)
    """
    version = doc.get("schema_version", 1)
    try:
        validator = _get_validator(version)
    except ValueError:
        # Unknown schema_version — validate against v1 so the schema itself
        # reports the minimum-violation error on the schema_version field.
        validator = _get_validator(1)

    # Structural validation via JSON Schema
    errors: list[str] = []
    for error in validator.iter_errors(doc):
        errors.append(f"{error.json_path}: {error.message}")

    if errors:
        return errors

    # Semantic validation (only if structure is valid)
    if semantic:
        for check in _SEMANTIC_CHECKS:
            check(doc)

    return []


def validate_strict(doc: dict[str, Any]) -> None:
    """Validate and raise on first error (schema or semantic)."""
    errors = validate(doc, semantic=False)
    if errors:
        raise ValidationError(errors[0])
    for check in _SEMANTIC_CHECKS:
        check(doc)


# ---------------------------------------------------------------------------
# Migration support
# ---------------------------------------------------------------------------


def migrate(doc: dict[str, Any], target_version: int = 1) -> dict[str, Any]:
    """Migrate a document to the target schema_version.

    Strategy:
    - Version 1 is the baseline; no migration needed.
    - Future versions add fields with defaults (backwards compatible).
    - Breaking changes bump major sylanne_version and require explicit migration.

    Returns:
        A new dict representing the migrated document.
    """
    current = doc.get("schema_version", 1)
    if current == target_version:
        return doc

    result = dict(doc)

    # Future: migration from v1 -> v2 would add new fields with defaults here.
    # Example pattern:
    # if current < 2:
    #     result.setdefault("new_field", default_value)
    #     result["schema_version"] = 2
    #     current = 2

    if result.get("schema_version") != target_version:
        raise ValueError(
            f"Cannot migrate from schema_version {doc.get('schema_version')} "
            f"to {target_version}. No migration path defined."
        )

    return result
