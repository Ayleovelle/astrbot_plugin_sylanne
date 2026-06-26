"""Telemetry: opt-in, privacy-safe local data capture for offline distillation.

The only public surface is :class:`DistillationSink` plus the schema helpers.
Importing this package pulls in stdlib only — no network, no heavy deps.
"""

from __future__ import annotations

from .sink import (
    AFFECT_CONTEXT_FIELDS,
    FEATURE_SCHEMA_VERSION,
    DistillationSink,
    anonymize_session,
)

__all__ = [
    "AFFECT_CONTEXT_FIELDS",
    "FEATURE_SCHEMA_VERSION",
    "DistillationSink",
    "anonymize_session",
]
