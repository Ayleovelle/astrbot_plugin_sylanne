"""Stub for social_field types used in TYPE_CHECKING."""

from __future__ import annotations

from typing import Protocol


class SocialSignals(Protocol):
    is_group: bool
    is_at_bot: bool
    name_mentioned: bool
    topic_relevance: float
    continuation_strength: float
    group_noise_level: float
    social_void_pressure: float
    sheaf_coupling: float
    group_size: int
    activity_level: float
    topic_coherence: float
    speaker_diversity: float
