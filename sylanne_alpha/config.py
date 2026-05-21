from __future__ import annotations

from typing import Any

CONFIG_SCHEMA_VERSION = "sylanne.alpha.config.v1"


def bool_setting(config: dict[str, Any], name: str, default: bool = False) -> bool:
    value = config.get(name, default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    return bool(value)


def int_setting(config: dict[str, Any], name: str, default: int, *, minimum: int = 0, maximum: int = 32) -> int:
    try:
        value = int(config.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def alpha_switches(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = dict(config or {})
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "realtime_chat": {
            "enabled": bool_setting(config, "sylanne_alpha_realtime_chat_enabled"),
            "intercept_llm_response": bool_setting(config, "sylanne_alpha_realtime_intercept_llm_response"),
        },
        "proactive_dispatch": {
            "enabled": bool_setting(config, "sylanne_alpha_proactive_dispatch_enabled"),
            "scheduler_enabled": bool_setting(config, "sylanne_alpha_proactive_scheduler_enabled"),
        },
        "embedding_memory": {
            "enabled": bool_setting(config, "sylanne_alpha_embedding_memory_enabled"),
            "provider_id": str(config.get("sylanne_alpha_embedding_memory_provider_id") or ""),
            "top_k": int_setting(config, "sylanne_alpha_embedding_memory_top_k", 5, minimum=1, maximum=20),
        },
        "assessor_llm": {
            "enabled": bool_setting(config, "sylanne_alpha_assessor_llm_enabled"),
            "provider_id": str(config.get("sylanne_alpha_assessor_provider_id") or ""),
        },
        "fast_assessor": {
            "enabled": bool_setting(config, "sylanne_alpha_fast_assessor_enabled", True),
            "provider_id": str(config.get("sylanne_alpha_fast_assessor_provider_id") or ""),
        },
        "background_workers": {
            "enabled": bool_setting(config, "sylanne_alpha_background_workers_enabled"),
            "max_workers": int_setting(config, "sylanne_alpha_background_max_workers", 1, minimum=1, maximum=8),
            "checkpoint_enabled": bool_setting(config, "sylanne_alpha_background_checkpoint_enabled", True),
        },
        "safety": {
            "relational_public_export": "blocked",
            "raw_dialogue_export": "blocked",
        },
    }


__all__ = ["CONFIG_SCHEMA_VERSION", "alpha_switches", "bool_setting", "int_setting"]
