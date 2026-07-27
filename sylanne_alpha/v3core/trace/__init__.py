"""Deterministic canonical decision trace (design section 16.2)."""

from .canonical import (
    TRACE_CODEC_MAGIC,
    TRACE_CODEC_VERSION,
    TRACE_HARD_CAP_BYTES,
    TraceOverflowError,
    canonical_trace_bytes,
    compute_journal_digest,
    decode_trace_bytes,
    trace_digest_hex,
)
from .models import CoreDecisionTrace, TRACE_SCHEMA_VERSION

__all__ = [
    "CoreDecisionTrace",
    "TRACE_CODEC_MAGIC",
    "TRACE_CODEC_VERSION",
    "TRACE_HARD_CAP_BYTES",
    "TRACE_SCHEMA_VERSION",
    "TraceOverflowError",
    "canonical_trace_bytes",
    "compute_journal_digest",
    "decode_trace_bytes",
    "trace_digest_hex",
]
