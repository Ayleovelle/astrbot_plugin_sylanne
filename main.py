"""Sylanne-Embodiment 4.0 alpha -- thin host layer for AstrBot plugin.

This module replaces the old 3.x EmotionalStatePlugin with a minimal host
that delegates all body/kernel/memory logic to sylanne_alpha/.
"""
from __future__ import annotations

import os
import sys

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

import asyncio
import collections
import contextvars
import json
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

# ---------------------------------------------------------------------------
# AstrBot imports -- graceful fallback when astrbot is not installed
# ---------------------------------------------------------------------------
try:
    from astrbot.api import logger  # type: ignore
    from astrbot.api.event import filter, AstrMessageEvent, MessageChain  # type: ignore
    from astrbot.api.star import Context, Star, register  # type: ignore
    from astrbot.api.message_components import Plain  # type: ignore
except ImportError:
    import logging as _logging
    logger = _logging.getLogger("astrbot_plugin_sylanne")  # type: ignore

    class _FakeFilter:
        def command(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

        def on_llm_request(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

        def on_llm_response(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

        def llm_tool(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

    filter = _FakeFilter()  # type: ignore

    class AstrMessageEvent:  # type: ignore
        pass

    class MessageChain:  # type: ignore
        def __init__(self):
            self.chain = []

        def message(self, text):
            self.chain.append(text)
            return self

    class Plain:  # type: ignore
        def __init__(self, text=""):
            self.text = text

    class Context:  # type: ignore
        pass

    class Star:  # type: ignore
        pass

    def register(*args, **kwargs):  # type: ignore
        def decorator(cls):
            return cls
        return decorator

# ---------------------------------------------------------------------------
# Sylanne alpha imports
# ---------------------------------------------------------------------------
from sylanne_alpha.host import SylanneAlphaHost, SylanneAlphaHostEvent
from sylanne_alpha.assessor_async import AsyncAssessor
from sylanne_alpha.compat import (
    build_memory_payload,
    command_surface,
    emotion_values,
    memory_surface,
    proactive_decision,
    realtime_dispatch,
    realtime_plan,
    reset_surface,
    simulate_update,
)
from sylanne_alpha.compat import strip_draft_blocks
from sylanne_alpha.embedding_memory import recall_with_embedding_assist
from sylanne_alpha.life_simulation import LifeSimulator
from sylanne_alpha.rhythm_learner import RhythmLearner
from sylanne_alpha.webui import WEBUI_HTML
from sylanne_alpha.webui_server import start_webui_background

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PLUGIN_NAME = "astrbot_plugin_sylanne"
PUBLIC_API_VERSION = "1.0"
MAX_LLM_REQUEST_PROMPT_CHARS = 12000
_MAX_PAYLOAD_SERIALIZED_CHARS = 60000
_MAX_UNFINISHED_CONTEXT_CHARS = 2000
_CHINA_TZ = timezone(timedelta(hours=8))

_INTERNAL_LLM_CALL: contextvars.ContextVar[bool] = contextvars.ContextVar("_INTERNAL_LLM_CALL", default=False)
PROACTIVE_SCHEDULER_WAKE_DELAY_SECONDS = 30.0
PROACTIVE_SCHEDULER_IDLE_DELAY_SECONDS = 1800.0





class _BackgroundPostJob:
    __slots__ = (
        "event", "identity", "reply_text", "context_key", "sequence", "enqueued_at",
        "attempts", "next_retry_at", "last_error_type", "last_error_message",
        "last_failed_at", "dead_lettered_at", "leased_at", "lease_until",
    )

    def __init__(self, event: Any, identity: str, reply_text: str, context_key: str, sequence: int, enqueued_at: float):
        self.event = event
        self.identity = identity
        self.reply_text = reply_text
        self.context_key = context_key
        self.sequence = sequence
        self.enqueued_at = enqueued_at
        self.attempts = 0
        self.next_retry_at = 0.0
        self.last_error_type = ""
        self.last_error_message = ""
        self.last_failed_at = 0.0
        self.dead_lettered_at = 0.0
        self.leased_at = 0.0
        self.lease_until = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "reply_text": self.reply_text,
            "context_key": self.context_key,
            "sequence": self.sequence,
            "enqueued_at": self.enqueued_at,
            "attempts": self.attempts,
            "next_retry_at": self.next_retry_at,
            "last_error_type": self.last_error_type,
            "last_error_message": self.last_error_message,
            "last_failed_at": self.last_failed_at,
            "dead_lettered_at": self.dead_lettered_at,
        }


_REQUIRED_EMOTION_SERVICE_METHODS = (
    "get_emotion_snapshot",
    "get_emotion_state",
    "get_emotion_values",
    "get_emotion_consequences",
    "get_emotion_relationship",
    "get_emotion_prompt_fragment",
    "build_emotion_memory_payload",
    "inject_emotion_context",
    "observe_emotion_text",
    "get_psychological_screening_snapshot",
    "get_psychological_screening_values",
    "observe_psychological_text",
    "simulate_psychological_update",
    "reset_psychological_screening_state",
    "simulate_emotion_update",
    "reset_emotion_state",
    "get_integrated_self_snapshot",
    "get_integrated_self_prompt_fragment",
    "get_integrated_self_policy_plan",
    "build_integrated_self_replay_bundle",
    "replay_integrated_self_bundle",
    "probe_integrated_self_compatibility",
    "export_integrated_self_diagnostics",
    "get_agent_runtime_diagnostics",
    "get_lifelike_learning_snapshot",
    "get_lifelike_initiative_policy",
    "get_proactive_speech_decision",
    "request_proactive_speech_dispatch",
    "get_realtime_chat_plan",
    "request_realtime_chat_dispatch",
    "observe_user_message_withdrawal",
    "observe_sticker_usage",
    "query_sylanne_memory",
    "get_lifelike_prompt_fragment",
    "observe_lifelike_text",
    "simulate_lifelike_update",
    "reset_lifelike_learning_state",
    "get_personality_drift_snapshot",
    "get_personality_drift_values",
    "get_personality_drift_prompt_fragment",
    "observe_personality_drift_event",
    "simulate_personality_drift_update",
    "reset_personality_drift_state",
    "get_fallibility_snapshot",
    "get_fallibility_values",
    "get_fallibility_prompt_fragment",
    "observe_fallibility_text",
    "simulate_fallibility_update",
    "reset_fallibility_state",
)


_EMOTION_SERVICE_EXPECTED_VERSIONS = {
    "emotion_api_version": "1.0",
    "emotion_schema_version": "astrbot.emotion_state.v2",
    "emotion_memory_schema_version": "astrbot.emotion_memory.v1",
    "personality_profile_schema_version": "astrbot.personality_profile.v1",
    "psychological_screening_schema_version": "astrbot.psychological_screening.v1",
    "integrated_self_schema_version": "astrbot.integrated_self_state.v1",
    "lifelike_learning_schema_version": "astrbot.lifelike_learning_state.v1",
    "personality_drift_schema_version": "astrbot.personality_drift_state.v1",
    "fallibility_state_schema_version": "astrbot.fallibility_state.v1",
}


def get_emotional_state_plugin(context: Any) -> Any:
    """Retrieve the registered plugin instance from AstrBot context."""
    star_context = getattr(context, "star_context", None)
    if isinstance(star_context, dict) and PLUGIN_NAME in star_context:
        return star_context[PLUGIN_NAME]
    getter = getattr(context, "get_registered_star", None)
    if not callable(getter):
        return None
    metadata = getter(PLUGIN_NAME)
    if not metadata or not getattr(metadata, "activated", True):
        return None
    plugin = getattr(metadata, "star_cls", None)
    if (
        plugin
        and all(
            getattr(plugin, name, None) == value
            for name, value in _EMOTION_SERVICE_EXPECTED_VERSIONS.items()
        )
        and all(
            callable(getattr(plugin, name, None))
            for name in _REQUIRED_EMOTION_SERVICE_METHODS
        )
    ):
        return plugin
    return None


# ---------------------------------------------------------------------------
# StateInjectionBudget -- tracks what was injected/skipped per request
# ---------------------------------------------------------------------------
class _StateInjectionBudget:
    __slots__ = ("session_key", "compat_mode", "injected", "skipped", "model_hint",
                 "max_added_chars", "max_parts", "added_chars", "appended", "warnings",
                 "context_owner")

    def __init__(self, session_key: str = "", model_hint: str = ""):
        self.session_key = session_key
        self.compat_mode = ""
        self.injected: list[dict[str, Any]] = []
        self.skipped: list[dict[str, Any]] = []
        self.model_hint = model_hint
        self.max_added_chars: int = 2400
        self.max_parts: int = 8
        self.added_chars: int = 0
        self.appended: list[dict[str, Any]] = []
        self.warnings: list[str] = []
        self.context_owner: str = "sylanne_plugin"


# ---------------------------------------------------------------------------
# EmotionalStatePlugin -- Sylanne 4.0 alpha thin host
# ---------------------------------------------------------------------------
@register("astrbot_plugin_sylanne", "Aylovelle.S.S", "Sylanne 4.0 alpha: sovereign emotional body runtime.", "4.0.0-Sylanne_Embodiment", "https://github.com/Ayleovelle/astrbot_plugin_sylanne")
class EmotionalStatePlugin(Star):
    emotion_api_version = "1.0"
    emotion_schema_version = "astrbot.emotion_state.v2"
    emotion_memory_schema_version = "astrbot.emotion_memory.v1"
    personality_profile_schema_version = "astrbot.personality_profile.v1"
    psychological_screening_schema_version = "astrbot.psychological_screening.v1"
    integrated_self_schema_version = "astrbot.integrated_self_state.v1"
    humanlike_state_schema_version = "astrbot.humanlike_state.v1"
    lifelike_learning_schema_version = "astrbot.lifelike_learning_state.v1"
    personality_drift_schema_version = "astrbot.personality_drift_state.v1"
    fallibility_state_schema_version = "astrbot.fallibility_state.v1"
    moral_repair_state_schema_version = "astrbot.moral_repair_state.v1"
    group_atmosphere_schema_version = "astrbot.group_atmosphere_state.v1"

    def __init__(self, context: Any = None, config: Any = None):
        super().__init__(context)
        self.config = config or {}
        self._config = self.config
        self._hosts: dict[str, SylanneAlphaHost] = {}
        self._background_tasks: list[asyncio.Task] = []
        self._unfinished_replies: dict[str, str] = {}
        self._stream_buffers: dict[str, str] = {}
        self._stream_first_sent: dict[str, str] = {}
        self._segmented_tasks: dict[str, asyncio.Task] = {}
        self._last_request_budgets: dict[str, _StateInjectionBudget] = {}
        self._last_understanding_closed_loop: dict[str, Any] = {}
        self._last_bot_expression_time: dict[str, float] = {}
        self._rhythm_learner = RhythmLearner(intimacy_threshold=0.6)
        self.logger = logger
        self._life_simulator = LifeSimulator(config=self._config)
        self._life_simulator_started = False
        self._async_assessor = AsyncAssessor(config=self._config)
        if hasattr(context, "register_web_api"):
            context.register_web_api(
                f"/{PLUGIN_NAME}/observatory-status",
                self._observatory_route_handler,
                ["GET"],
                "Sylanne observatory readonly status",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/memory-settings",
                self._memory_settings_get_handler,
                ["GET"],
                "Sylanne memory settings page data",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/memory-settings",
                self._memory_settings_post_handler,
                ["POST"],
                "Update Sylanne memory settings",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/lineage-observatory",
                self._lineage_observatory_handler,
                ["GET"],
                "Sylanne lineage observatory readonly",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/webui",
                self._webui_page_handler,
                ["GET"],
                "Sylanne-Embodiment WebUI dashboard",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/api/state",
                self._webui_state_handler,
                ["GET"],
                "Sylanne-Embodiment WebUI state API",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/api/settings",
                self._webui_settings_get_handler,
                ["GET"],
                "Sylanne-Embodiment WebUI settings read",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/api/settings",
                self._webui_settings_post_handler,
                ["POST"],
                "Sylanne-Embodiment WebUI settings write",
            )
        self._load_config_defaults()

    @property
    def config(self) -> dict[str, Any]:
        try:
            return self._config
        except AttributeError:
            self._config = {}
            return self._config

    @config.setter
    def config(self, value: Any) -> None:
        if isinstance(value, dict):
            self._config = value
        else:
            self._config = dict(value) if value else {}

    # ------------------------------------------------------------------
    # Config helpers (schema contract compatibility)
    # ------------------------------------------------------------------
    def _cfg(self, key: str, default: Any = "") -> Any:
        return self._config.get(key, default)

    def _cfg_bool(self, key: str, default: bool = False) -> bool:
        val = self._config.get(key, default)
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ("true", "1", "yes")
        return bool(val)

    def _cfg_float(self, key: str, default: float = 0.0) -> float:
        val = self._config.get(key, default)
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    def _cfg_int(self, key: str, default: int = 0) -> int:
        val = self._config.get(key, default)
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    def _load_config_defaults(self) -> None:
        self._cfg_bool("enabled", True)
        self._cfg_bool("use_llm_assessor", True)
        self._cfg("emotion_provider_id", "")
        self._cfg_bool("fast_assessor_enabled", False)
        self._cfg("fast_assessor_provider_id", "")
        self._cfg_int("fast_assessor_max_context_chars", 600)
        self._cfg_float("fast_assessor_timeout_seconds", 2.0)
        self._cfg_float("fast_assessor_temperature", 0.0)
        self._cfg_bool("low_reasoning_friendly_mode", False)
        self._cfg_int("low_reasoning_max_context_chars", 1200)
        self._cfg("assessment_timing", "post")
        self._cfg_bool("enable_proactive_speech_dispatch", False)
        self._cfg_bool("enable_proactive_speech_scheduler", False)
        self._cfg_bool("enable_realtime_chat", False)
        self._cfg_bool("realtime_chat_style_prompt_enabled", False)
        self._cfg_bool("realtime_chat_intercept_llm_response", False)
        self._cfg_bool("realtime_input_completion_llm_gate_enabled", False)
        self._cfg_float("realtime_input_completion_probe_delay_seconds", 0.25)
        self._cfg_float("realtime_input_completion_max_wait_seconds", 4.0)
        self._cfg_float("realtime_user_typing_hold_seconds", 0.8)
        self._cfg_float("realtime_empty_input_typing_hold_seconds", 0.35)
        self._cfg_bool("realtime_chat_dry_run_default", False)
        self._cfg_bool("realtime_chat_strip_markdown", True)
        self._cfg_bool("enable_sticker_reaction", False)
        self._cfg_int("background_post_queue_limit", 0)
        self._cfg_bool("enable_dynamic_background_workers", False)
        self._cfg_bool("background_post_queue_checkpoint_enabled", True)
        self._cfg_float("background_post_checkpoint_debounce_seconds", 0.75)
        self._cfg_float("background_post_job_lease_seconds", 120.0)
        self._cfg_float("background_post_job_timeout_seconds", 0.0)
        self._cfg_int("background_post_retry_max_attempts", 3)
        self._cfg_float("background_post_retry_base_delay_seconds", 2.0)
        self._cfg_float("background_post_retry_max_delay_seconds", 60.0)
        self._cfg_int("background_post_dead_letter_limit", 100)
        self._cfg_int("background_post_diagnostics_warn_lag_count", 20)
        self._cfg_float("background_post_diagnostics_warn_lag_seconds", 60.0)
        self._cfg_bool("enable_low_signal_light_assessment", True)
        self._cfg_int("low_signal_max_chars", 12)
        self._cfg_bool("sylanne_alpha_assessor_llm_enabled", False)
        self._cfg("sylanne_alpha_assessor_provider_id", "")
        self._cfg_float("sylanne_alpha_assessor_timeout_seconds", 2.0)
        self._cfg_float("sylanne_alpha_fast_assessor_timeout_seconds", 1.5)
        self._cfg_bool("sylanne_alpha_main_assessor_enabled", False)
        self._cfg("sylanne_alpha_main_assessor_provider_id", "")
        self._cfg_float("sylanne_alpha_main_assessor_timeout_seconds", 3.0)
        self._cfg_bool("agent_speaker_relationship_tracking", True)
        self._cfg_bool("agent_include_speaker_in_assessment", True)
        self._cfg_int("agent_identity_profile_limit", 256)
        self._cfg_float("agent_identity_ttl_seconds", 2592000.0)
        self._cfg_bool("enable_agent_causal_trail", True)
        self._cfg_int("agent_trail_limit", 80)
        self._cfg_bool("agent_trail_compaction_enabled", True)
        self._cfg_float("agent_trail_low_signal_delta_threshold", 0.03)
        self._cfg_int("agent_trail_low_signal_window", 5)
        self._cfg_bool("inject_state", True)
        self._cfg_bool("runtime_parameter_debug_override_enabled", False)
        self._cfg_int("state_injection_request_budget_chars", 32000)
        self._cfg_int("state_injection_reserved_chars", 3000)
        self._cfg_int("state_injection_max_added_chars", 2400)
        self._cfg_int("state_injection_max_parts", 8)
        self._cfg_int("llm_tool_response_max_chars", 16000)
        self._cfg_bool("enable_safety_boundary", True)
        self._cfg_bool("block_deception_manipulation_evasion_actions", True)
        self._cfg_int("max_context_chars", 1600)
        self._cfg_int("request_context_max_chars", 1600)
        self._cfg_float("assessor_timeout_seconds", 0.0)
        self._cfg_float("assessor_temperature", 0.1)
        self._cfg_float("provider_id_cache_ttl_seconds", 30.0)
        self._cfg_float("passive_load_fresh_seconds", 1.0)
        self._cfg_bool("benchmark_enable_simulated_time", False)
        self._cfg_float("benchmark_time_offset_seconds", 0.0)
        self._cfg_bool("allow_emotion_reset_backdoor", True)
        self._cfg_bool("enable_psychological_screening", False)
        self._cfg_float("sylanne_memory_idle_commit_delay_seconds", 4.0)
        self._cfg_bool("sylanne_memory_vector_retrieval_enabled", True)
        self._cfg("sylanne_memory_embedding_provider_id", "")
        self._cfg_float("sylanne_memory_record_embedding_min_interval_seconds", 300.0)
        self._cfg_int("sylanne_memory_record_embedding_max_per_flush", 1)
        self._cfg_bool("sylanne_memory_debug_view_enabled", False)
        self._cfg_bool("humanlike_memory_write_enabled", True)
        self._cfg_bool("allow_humanlike_reset_backdoor", True)
        self._cfg_bool("lifelike_learning_memory_write_enabled", True)
        self._cfg_bool("allow_lifelike_learning_reset_backdoor", True)
        self._cfg_bool("personality_drift_memory_write_enabled", True)
        self._cfg_bool("allow_personality_drift_reset_backdoor", True)
        self._cfg_bool("enable_moral_repair_state", False)
        self._cfg_bool("moral_repair_memory_write_enabled", True)
        self._cfg_bool("allow_moral_repair_reset_backdoor", True)
        self._cfg_bool("enable_fallibility_state", False)
        self._cfg_bool("fallibility_memory_write_enabled", True)
        self._cfg_bool("allow_fallibility_reset_backdoor", True)
        self._cfg_bool("enable_shadow_diagnostics", False)
        self._cfg_bool("enable_integrated_self_state", True)
        self._cfg_bool("allow_relational_self_public_export", False)
        self._cfg_bool("integrated_self_memory_write_enabled", True)
        self._cfg("integrated_self_degradation_profile", "balanced")

    def _assessment_timing(self) -> str:
        timing = str(self._cfg("assessment_timing", "post") or "post").strip().lower()
        if timing in {"pre", "post", "both"}:
            return timing
        return "post"

    # ------------------------------------------------------------------
    # Web API route handlers (memory-settings, lineage-observatory)
    # ------------------------------------------------------------------
    async def _memory_settings_get_handler(self) -> dict[str, Any]:
        return await self._sylanne_memory_settings_page_payload()

    async def _memory_settings_post_handler(self) -> dict[str, Any]:
        from quart import request as quart_request
        body = await quart_request.get_json(silent=True) or {}
        return await self._update_sylanne_memory_settings_from_page(body)

    async def _lineage_observatory_handler(self) -> dict[str, Any]:
        session_key = "default"
        return self._sylanne_lineage_observatory_page_payload(session_key)

    # ------------------------------------------------------------------
    # WebUI route handlers
    # ------------------------------------------------------------------
    async def _webui_page_handler(self) -> Any:
        """Return the full WebUI HTML page."""
        from quart import Response
        return Response(WEBUI_HTML, content_type="text/html; charset=utf-8")

    async def _webui_state_handler(self) -> dict[str, Any]:
        """Return full state JSON for the WebUI dashboard."""
        all_sessions = list(self._hosts.keys()) if hasattr(self, "_hosts") else []
        if not all_sessions:
            all_sessions = ["default"]
        session_key = all_sessions[0] if all_sessions else "default"
        host = self._host(session_key)
        comp = host.kernel.computation

        # Emotion from Void-Scar Engine
        emotion = comp.engine.observe()

        # Gate stats
        gate_dict = comp.gate.to_dict()
        gate_info = {
            "precision": round(gate_dict.get("precision", 0.0), 4),
            "mean_surprise": round(gate_dict.get("mean_surprise", 0.0), 4),
            "history_len": gate_dict.get("history_len", 0),
        }

        # Route stats
        route_stats = {"fast": 0, "normal": 0, "full": 0, "skip": 0}
        history = gate_dict.get("history", [])
        if isinstance(history, list):
            for entry in history:
                r = entry.get("route", "fast") if isinstance(entry, dict) else "fast"
                if r in route_stats:
                    route_stats[r] += 1

        # Void-Scar state as memory equivalent
        engine_diag = comp.engine.diagnostics()
        void_info = engine_diag.get("void", {})
        mem_info = {
            "size": int(emotion.get("active_voids", 0)),
            "connectivity": comp.engine._coherence,
            "holes_count": int(emotion.get("active_voids", 0)),
            "ghost_count": int(emotion.get("ghost_count", 0)),
        }
        recent_recall = []
        comp_result = getattr(host.kernel, "_last_computation_result", None) or {}
        recalled_items = comp_result.get("recalled", [])
        recent_recall = [str(r.get("text", ""))[:60] for r in recalled_items if isinstance(r, dict)]

        # Boundary
        boundary_dict = comp.boundary.to_dict()
        boundary_info = {
            "integrity": round(boundary_dict.get("integrity", 1.0), 4),
            "entropy": round(boundary_dict.get("entropy", 0.0), 4),
            "stability": round(boundary_dict.get("stability", 1.0), 4),
            "phase_transitions": boundary_dict.get("phase_transitions", 0),
        }

        # Expression
        expr_state = comp.expression.state()
        expr_info = {
            "pressure": round(expr_state.get("pressure", 0.0), 4),
            "threshold": round(expr_state.get("threshold", 0.6), 4),
            "ratio": round(expr_state.get("pressure", 0.0) / max(0.01, expr_state.get("threshold", 0.6)), 4),
            "mode": expr_state.get("mode", "silent"),
            "count": expr_state.get("count", 0),
        }

        # Timing
        timing = comp.timing_stats()

        # Feedback (from SSM diagnostics or computation diagnostics)
        comp_diag = comp.diagnostics()
        feedback_raw = comp_diag.get("feedback", {})
        if not feedback_raw:
            # Try to derive from body diagnostics
            surface = host.kernel.surface()
            diag = surface.get("diagnostics", {})
            feedback_raw = diag.get("feedback", {})
        feedback = {
            "accepted": int(feedback_raw.get("accepted", 0)),
            "ignored": int(feedback_raw.get("ignored", 0)),
            "rejected": int(feedback_raw.get("rejected", 0)),
        }

        return {
            "emotion": {k: round(v, 4) for k, v in emotion.items()},
            "gate": gate_info,
            "route_stats": route_stats,
            "memory": {
                "size": len(mem_points),
                "connectivity": round(connectivity, 4),
                "holes_count": len(holes) if isinstance(holes, list) else int(holes or 0),
                "recent_recall": recent_recall,
            },
            "boundary": boundary_info,
            "expression": expr_info,
            "timing": timing,
            "feedback": feedback,
            "sessions": all_sessions,
            "life_simulation": self._life_simulator.to_dict(),
        }

    async def _webui_settings_get_handler(self) -> dict[str, Any]:
        """Return current config values and schema for the settings panel."""
        schema = self._load_conf_schema()
        values = {}
        for key in schema:
            values[key] = self._config.get(key, schema[key].get("default"))
        return {"schema": schema, "values": values}

    async def _webui_settings_post_handler(self) -> dict[str, Any]:
        """Update config values from the settings panel."""
        from quart import request as quart_request
        body = await quart_request.get_json(silent=True) or {}
        schema = self._load_conf_schema()
        updated = []
        for key, value in body.items():
            if key not in schema:
                continue
            meta = schema[key]
            # Type coercion
            if meta.get("type") == "bool":
                value = bool(value)
            elif meta.get("type") == "int":
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    continue
            elif meta.get("type") == "float":
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    continue
            else:
                value = str(value)
            self._config[key] = value
            updated.append(key)
        # Persist if possible
        config = self.config if hasattr(self, "config") else self._config
        if isinstance(config, dict):
            for key in updated:
                config[key] = self._config[key]
        if hasattr(config, "save_config"):
            config.save_config()
        return {"ok": True, "updated": updated}

    def _load_conf_schema(self) -> dict[str, Any]:
        """Load _conf_schema.json from plugin directory."""
        schema_path = Path(_PLUGIN_DIR) / "_conf_schema.json"
        if schema_path.exists():
            try:
                return json.loads(schema_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    async def _sylanne_memory_settings_page_payload(self) -> dict[str, Any]:
        providers = []
        context = getattr(self, "context", None) or self.context
        if hasattr(context, "get_all_embedding_providers"):
            for p in context.get_all_embedding_providers():
                cfg = getattr(p, "provider_config", {})
                providers.append({
                    "id": cfg.get("id", ""),
                    "model": cfg.get("embedding_model", ""),
                    "dimensions": cfg.get("embedding_dimensions", 0),
                })
        current_id = str(self._config.get("sylanne_memory_embedding_provider_id") or "")
        return {
            "embedding_providers": providers,
            "current_embedding_provider_id": current_id,
            "native_config_embedding_selector_available": False,
        }

    async def _update_sylanne_memory_settings_from_page(self, body: dict[str, Any]) -> dict[str, Any]:
        provider_id = str(body.get("embedding_provider_id") or "")
        context = getattr(self, "context", None) or self.context
        valid_ids = set()
        if hasattr(context, "get_all_embedding_providers"):
            for p in context.get_all_embedding_providers():
                cfg = getattr(p, "provider_config", {})
                valid_ids.add(cfg.get("id", ""))
        if provider_id and provider_id not in valid_ids:
            return {"ok": False, "error": "unknown_embedding_provider"}
        self._config["sylanne_memory_embedding_provider_id"] = provider_id
        config = self.config if hasattr(self, "config") else self._config
        if isinstance(config, dict):
            config["sylanne_memory_embedding_provider_id"] = provider_id
        if hasattr(config, "save_config"):
            config.save_config()
        return {"ok": True}

    def _sylanne_lineage_observatory_page_payload(self, session_key: str) -> dict[str, Any]:
        loop_data = self._last_understanding_closed_loop.get(session_key, {})
        observatory = loop_data.get("turning_point_lineage_observatory", {})
        lineage = observatory.get("lineage", {})
        raw_branches = observatory.get("branches", [])
        sanitized_branches = []
        for branch in raw_branches:
            sanitized = {k: v for k, v in branch.items() if k not in ("relationship_time_weight", "isolation_key")}
            sanitized_branches.append(sanitized)
        return {
            "read_only": True,
            "internal_only": True,
            "public_api_eligible": False,
            "lineage": lineage,
            "branches": sanitized_branches,
        }

    def _understanding_closed_loop_diagnostics(self, session_key: str) -> dict[str, Any]:
        loop_data = dict(self._last_understanding_closed_loop.get(session_key, {}))
        if "turning_point_memory_replay" in loop_data:
            loop_data["turning_point_memory_replay"] = {}
        if "turning_point_lineage_observatory" in loop_data:
            loop_data["turning_point_lineage_observatory"] = {}
        if "turning_point_memory_replay_history" in loop_data:
            loop_data["turning_point_memory_replay_history"] = []
        return loop_data

    # ------------------------------------------------------------------
    # Host management
    # ------------------------------------------------------------------
    _MAX_HOSTS = 50
    _shared_encoder = None

    def _host(self, session_key: str) -> SylanneAlphaHost:
        if not hasattr(self, "_hosts"):
            self._hosts = {}
        if session_key not in self._hosts:
            # LRU eviction: persist and remove oldest host if over limit
            if len(self._hosts) >= self._MAX_HOSTS:
                oldest_key = next(iter(self._hosts))
                old_host = self._hosts.pop(oldest_key)
                try:
                    old_host.runtime.save(old_host.kernel)
                except Exception:
                    pass
            cfg = self.config if hasattr(self, "_config") else getattr(self, "config", {}) or {}
            root = cfg.get("sylanne_alpha_root") or str(Path.home() / ".sylanne_alpha")
            host = SylanneAlphaHost(root=root, session_key=session_key)
            # Share encoder across all hosts to save memory
            if EmotionalStatePlugin._shared_encoder is None:
                EmotionalStatePlugin._shared_encoder = host.kernel.computation.encoder
            else:
                host.kernel.computation.replace_encoder(EmotionalStatePlugin._shared_encoder)
            self._hosts[session_key] = host
        else:
            # Touch: move to end for LRU ordering
            host = self._hosts.pop(session_key)
            self._hosts[session_key] = host
        return self._hosts[session_key]

    def _session_key(self, event: Any = None, session_key: str = "") -> str:
        if session_key:
            return session_key
        if event is not None:
            base = str(getattr(event, "session_id", "") or getattr(event, "unified_msg_origin", "") or "default")
            # For group chats, include sender_id so each user gets an
            # independent host/kernel/computation spine.
            sender_id = str(getattr(event, "sender_id", "") or getattr(event, "user_id", "") or "")
            if sender_id and base != "default":
                return f"{base}:{sender_id}"
            return base
        return "default"

    # ------------------------------------------------------------------
    # Core observe lifecycle
    # ------------------------------------------------------------------
    async def observe_request(self, session_key: str, *, text: str = "", confidence: float = 0.0, flags: list[str] | None = None, now: float = 0.0) -> dict[str, Any]:
        host = self._host(session_key)
        effective_now = now or time.time()
        event = SylanneAlphaHostEvent(text=text, confidence=confidence, flags=list(flags or []), now=effective_now, event_time=self._event_time(now))
        # Feedback loop: trigger based on time since last bot expression
        if not hasattr(self, "_last_bot_expression_time"):
            self._last_bot_expression_time = {}
        last_expr_time = self._last_bot_expression_time.get(session_key, 0.0)
        if last_expr_time > 0:
            gap = effective_now - last_expr_time
            if gap < 30.0:
                # User replied quickly -> accepted
                dt = max(0.1, min(10.0, gap / 60.0))
                host.kernel.computation.feedback("accepted", dt=dt)
            elif gap > 300.0:
                # User took very long -> ignored
                dt = max(0.1, min(10.0, gap / 60.0))
                host.kernel.computation.feedback("ignored", dt=dt)
            # 30-300s: neutral, no feedback triggered
        return host.on_request(event)

    async def observe_response(self, session_key: str, *, text: str = "", confidence: float = 0.0, flags: list[str] | None = None, now: float = 0.0) -> dict[str, Any]:
        host = self._host(session_key)
        effective_now = now or time.time()
        event = SylanneAlphaHostEvent(text=text, confidence=confidence, flags=list(flags or []), now=effective_now, event_time=self._event_time(now))
        # Record bot expression time for feedback loop
        if not hasattr(self, "_last_bot_expression_time"):
            self._last_bot_expression_time = {}
        self._last_bot_expression_time[session_key] = effective_now
        return host.on_response(event)

    # ------------------------------------------------------------------
    # Immediate chat
    # ------------------------------------------------------------------
    async def chat_sylanne(self, *, session_key: str, text: str = "", now: float = 0.0) -> dict[str, Any]:
        host = self._host(session_key)
        event = SylanneAlphaHostEvent(text=text, confidence=0.7, flags=["safe", "chat_request"], now=now or time.time(), event_time=self._event_time(now))
        return host.on_chat(event)

    # ------------------------------------------------------------------
    # Command surfaces
    # ------------------------------------------------------------------
    async def emotion(self, *, session_key: str) -> dict[str, Any]:
        return command_surface(self._host(session_key), "emotion")

    async def psych_state(self, *, session_key: str) -> dict[str, Any]:
        return command_surface(self._host(session_key), "psych_state")

    async def humanlike_state(self, *, session_key: str) -> dict[str, Any]:
        return command_surface(self._host(session_key), "humanlike_state")

    async def lifelike_state(self, *, session_key: str) -> dict[str, Any]:
        return command_surface(self._host(session_key), "lifelike_state")

    async def personality_drift_state(self, *, session_key: str) -> dict[str, Any]:
        return command_surface(self._host(session_key), "personality_drift_state")

    async def moral_repair_state(self, *, session_key: str) -> dict[str, Any]:
        return command_surface(self._host(session_key), "moral_repair_state")

    async def integrated_self(self, *, session_key: str) -> dict[str, Any]:
        return command_surface(self._host(session_key), "integrated_self")

    async def shadow_diagnostics(self, *, session_key: str) -> dict[str, Any]:
        return command_surface(self._host(session_key), "shadow_diagnostics")

    async def fallibility_state(self, *, session_key: str) -> dict[str, Any]:
        return command_surface(self._host(session_key), "fallibility_state")

    async def _humanlike_reset_impl(self, session_key: str) -> dict[str, Any]:
        return reset_surface(self._host(session_key), "humanlike_state")

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------
    async def sylanne_memory(self, *, session_key: str, query: str = "", limit: int = 5) -> dict[str, Any]:
        return memory_surface(self._host(session_key), query=query, limit=limit)

    async def query_sylanne_memory(self, *, session_key: str, query: str = "", limit: int = 5, now: float = 0.0) -> dict[str, Any]:
        host = self._host(session_key)
        traces = host.kernel.body.memory.get("traces", [])
        enabled = bool(self._config.get("sylanne_alpha_embedding_memory_enabled"))
        provider_id = str(self._config.get("sylanne_alpha_embedding_memory_provider_id") or "")

        async def _embed(text: str) -> list[float]:
            provider = self._get_embedding_provider(provider_id)
            if provider is None:
                return []
            return await provider.get_embedding(text)

        def _sync_embed(text: str) -> list[float]:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, _embed(text))
                    return future.result()
            return asyncio.run(_embed(text))

        result = recall_with_embedding_assist(
            query=query,
            records=traces,
            enabled=enabled,
            embed_query=_sync_embed if enabled and provider_id else None,
            limit=limit,
        )
        return {
            "schema_version": "sylanne.alpha.compat.memory.v1",
            "session_key": session_key,
            "slice": "sylanne_memory",
            "query": query,
            "source": result["source"],
            "matches": result["matches"],
            "count": result["count"],
        }

    def _get_embedding_provider(self, provider_id: str) -> Any:
        if not provider_id:
            return None
        context = self.context
        if hasattr(context, "get_provider_by_id"):
            return context.get_provider_by_id(provider_id)
        return None

    # ------------------------------------------------------------------
    # Public API facade
    # ------------------------------------------------------------------
    async def observe_emotion_text(self, session_key: str = "", *, text: str = "", confidence: float = 0.0, now: float = 0.0, use_llm: bool = True, observed_at: float = 0.0, **kwargs: Any) -> dict[str, Any]:
        effective_now = observed_at or now
        surface = await self.observe_request(session_key, text=text, confidence=confidence, flags=["safe"], now=effective_now)
        return command_surface(self._host(session_key), "emotion")

    async def get_emotion_snapshot(self, *, session_key: str, include_prompt_fragment: bool = False, **kwargs: Any) -> dict[str, Any]:
        host = self._host(session_key)
        payload = command_surface(host, "emotion")
        payload["turns"] = host.kernel.turns
        return payload

    async def get_emotion_state(self, *, session_key: str, as_dict: bool = True, **kwargs: Any) -> Any:
        import copy
        state = await self._load_state(session_key)
        if not as_dict and state is not None and not isinstance(state, dict):
            return copy.deepcopy(state)
        values = emotion_values(self._host(session_key))
        return {"values": values}

    async def get_emotion_values(self, *, session_key: str) -> dict[str, float]:
        return emotion_values(self._host(session_key))

    async def build_emotion_memory_payload(self, event_or_session: Any = None, *, session_key: str = "", query: str = "", limit: int = 5, memory: Any = None, source: str = "", written_at: float = 0.0, include_raw_snapshot: bool = True, include_state_annotations_envelope: bool = True, memory_text: str = "", **kwargs: Any) -> dict[str, Any]:
        sk = session_key or (str(getattr(event_or_session, "unified_msg_origin", "")) if event_or_session else "") or "default"
        host = self._host(sk)
        enabled = bool(self._config.get("sylanne_alpha_embedding_memory_enabled"))
        provider_id = str(self._config.get("sylanne_alpha_embedding_memory_provider_id") or "")
        traces = host.kernel.body.memory.get("traces", [])

        async def _embed(text: str) -> list[float]:
            provider = self._get_embedding_provider(provider_id)
            if provider is None:
                return []
            return await provider.get_embedding(text)

        def _sync_embed(text: str) -> list[float]:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, _embed(text))
                    return future.result()
            return asyncio.run(_embed(text))

        result = recall_with_embedding_assist(
            query=query,
            records=traces,
            enabled=enabled,
            embed_query=_sync_embed if enabled and provider_id else None,
            limit=limit,
        )
        matches = result["matches"]
        prompt_fragment = self._embedding_prompt_fragment(matches, query)
        return {
            "schema_version": "sylanne.alpha.compat.memory.v1",
            "session_key": sk,
            "slice": "sylanne_memory",
            "query": query,
            "source": result["source"],
            "matches": matches,
            "count": result["count"],
            "prompt_fragment": prompt_fragment,
        }

    def _embedding_prompt_fragment(self, matches: list[dict[str, Any]], query: str = "") -> str:
        if not matches:
            return ""
        lines = ["[retrieved_conversation_context]", "检索到的记忆参考（旧记忆只作旁注，冲突时以当前用户输入为准，不要把旧记忆当成用户的新请求）："]
        for match in matches[:5]:
            text = str(match.get("text") or "")[:200]
            lines.append(f"- {text}")
        return "\n".join(lines)

    async def get_proactive_speech_decision(self, event_or_session: Any = None, *, session_key: str = "", now: float = 0.0, candidate_context: str = "", **kwargs: Any) -> dict[str, Any]:
        sk = session_key or (str(getattr(event_or_session, "unified_msg_origin", "")) if event_or_session else "") or "default"
        host = self._host(sk)
        surface = host.diagnostics()
        return proactive_decision(surface)

    async def get_realtime_chat_plan(self, session_key: str, text: str, **kwargs) -> dict[str, Any]:
        cfg = getattr(self, "config", None) or getattr(self, "_config", {}) or {}
        max_part_chars = int(kwargs.pop("max_part_chars", cfg.get("realtime_chat_max_part_chars", 48)))
        if max_part_chars < 4:
            max_part_chars = 4
        max_delay = float(cfg.get("realtime_chat_max_delay_seconds", 4.2))
        min_delay = float(cfg.get("realtime_chat_min_delay_seconds", 0.0))
        plan = realtime_plan(session_key, text, max_part_chars=max_part_chars, **kwargs)
        for part in plan["message_parts"]:
            d = part["delay_before_seconds"]
            part["delay_before_seconds"] = round(min(max_delay, max(min_delay if d > 0 else 0.0, d)), 3)
        plan["settings"] = {"max_part_chars": max_part_chars}
        return plan

    async def request_realtime_chat_dispatch(self, session_key: str, text: str) -> dict[str, Any]:
        return realtime_dispatch(session_key, text)

    async def inject_emotion_context(self, event: Any = None, request: Any = None, *, session_key: str = "") -> dict[str, Any]:
        sk = session_key or self._session_key(event)
        if request is None:
            return {"prompt": ""}
        # Build memory-based injection - use last event text as query hint
        host = self._host(sk)
        last_text = str(host.kernel.last_event.get("text") or "")
        query_hint = last_text[:100] if last_text else str(getattr(request, "prompt", "") or "")[:100]
        memory_result = await self.query_sylanne_memory(session_key=sk, query=query_hint, limit=3)
        fragment = self._memory_prompt_fragment(memory_result)
        self._append_request_prompt_fragment(request, fragment)
        return {"prompt": str(getattr(request, "prompt", "") or "")}

    async def simulate_emotion_update(self, *, session_key: str, text: str = "", flags: list[str] | None = None, confidence: float = 0.5, role: str = "user", source: str = "", observed_at: float = 0.0, **kwargs: Any) -> dict[str, Any]:
        host = self._host(session_key)
        return simulate_update(host, text=text, flags=flags, confidence=confidence)

    # ------------------------------------------------------------------
    # Diagnostics / Export / Import / Control
    # ------------------------------------------------------------------
    async def sylanne_diagnostics(self, *, session_key: str) -> dict[str, Any]:
        host = self._host(session_key)
        return host.diagnostics()

    async def export_sylanne_alpha(self, *, session_key: str) -> dict[str, Any]:
        host = self._host(session_key)
        snapshot = host.snapshot()
        snapshot["session_key"] = session_key
        return snapshot

    async def import_sylanne_legacy(self, legacy: dict[str, Any], *, session_key: str) -> dict[str, Any]:
        root = self._config.get("sylanne_alpha_root") or str(Path.home() / ".sylanne_alpha")
        self._hosts[session_key] = SylanneAlphaHost(root=root, session_key=session_key, legacy=legacy)
        return self._hosts[session_key].snapshot()

    async def pause_sylanne(self, *, session_key: str) -> dict[str, Any]:
        host = self._host(session_key)
        host.kernel.body.immunity.paused = True
        host.runtime.save(host.kernel)
        return host.diagnostics()

    async def resume_sylanne(self, *, session_key: str) -> dict[str, Any]:
        host = self._host(session_key)
        host.kernel.body.immunity.paused = False
        host.runtime.save(host.kernel)
        return host.diagnostics()

    async def cooldown_sylanne(self, *, session_key: str) -> dict[str, Any]:
        host = self._host(session_key)
        host.kernel.body.immunity.cooldown = max(host.kernel.body.immunity.cooldown, 0.5)
        host.runtime.save(host.kernel)
        return host.diagnostics()

    async def reset_sylanne(self, *, session_key: str) -> dict[str, Any]:
        host = self._host(session_key)
        host.kernel = host.runtime.reset(session_key)
        return host.diagnostics()

    async def proactive_sylanne(self, *, session_key: str, now: float = 0.0) -> dict[str, Any]:
        host = self._host(session_key)
        event = SylanneAlphaHostEvent(
            text="", confidence=0.5, flags=["proactive", "safe"],
            now=now or time.time(), event_time=self._event_time(now),
        )
        surface = host.on_proactive_check(event)
        decision_payload = proactive_decision(surface)
        # Add reason_code from host_payload
        decision_payload["reason_code"] = surface["host_payload"].get("reason_code", "life_rhythm")
        return {
            **surface,
            "host_payload": surface["host_payload"],
            "decision": decision_payload,
        }

    async def sylanne_smoke(self, *, session_key: str) -> dict[str, Any]:
        host = self._host(session_key)
        return {"ok": True, "session_key": session_key, "turns": host.kernel.turns}

    # ------------------------------------------------------------------
    # on_llm_request hook
    # ------------------------------------------------------------------
    @filter.on_llm_request()
    async def on_llm_request(self, event: Any, request: Any) -> None:
        try:
            await self._on_llm_request_inner(event, request)
        except Exception as e:
            logger.warning(f"Sylanne on_llm_request error: {e}")
            return

    async def _on_llm_request_inner(self, event: Any, request: Any) -> None:
        if not hasattr(self, "_stream_buffers"):
            self._stream_buffers = {}
        if not hasattr(self, "_stream_first_sent"):
            self._stream_first_sent = {}
        if not hasattr(self, "_segmented_tasks"):
            self._segmented_tasks = {}
        if not hasattr(self, "_unfinished_replies"):
            self._unfinished_replies = {}
        if not hasattr(self, "_background_tasks"):
            self._background_tasks = []
        if not hasattr(self, "_last_request_budgets"):
            self._last_request_budgets = {}
        if not hasattr(self, "_fragment_buffers"):
            self._fragment_buffers = {}
        if not hasattr(self, "_fragment_timers"):
            self._fragment_timers = {}
        session_key = self._session_key(event)
        message_text = str(getattr(event, "message_str", "") or "")
        realtime_enabled = bool((self.config or {}).get("sylanne_alpha_realtime_chat_enabled"))
        hajide = bool((self.config or {}).get("sylanne_alpha_hajide_compat_mode"))
        intercept = bool((self.config or {}).get("sylanne_alpha_realtime_intercept_llm_response"))

        # Fragment debounce: wait for user to finish typing
        if realtime_enabled and message_text:
            probe_delay = float((self.config or {}).get("realtime_input_completion_probe_delay_seconds", 1.5))
            max_wait = float((self.config or {}).get("realtime_input_completion_max_wait_seconds", 4.0))

            # Cancel previous timer for this session
            old_timer = self._fragment_timers.pop(session_key, None)
            if old_timer and not old_timer.done():
                old_timer.cancel()

            # Accumulate fragment
            if session_key not in self._fragment_buffers:
                self._fragment_buffers[session_key] = {"texts": [], "start_time": time.time(), "event": event, "request": request}
            self._fragment_buffers[session_key]["texts"].append(message_text)
            self._fragment_buffers[session_key]["event"] = event
            self._fragment_buffers[session_key]["request"] = request

            elapsed = time.time() - self._fragment_buffers[session_key]["start_time"]
            if elapsed >= max_wait:
                # Max wait exceeded, process now
                merged = " ".join(self._fragment_buffers.pop(session_key)["texts"])
                event.message_str = merged
                message_text = merged
                logger.info(f"Sylanne fragment merged (max_wait): {merged[:60]}")
            else:
                # Set timer to wait for more fragments
                async def _process_after_delay(sk=session_key):
                    await asyncio.sleep(probe_delay)
                    buf = self._fragment_buffers.pop(sk, None)
                    if buf:
                        merged = " ".join(buf["texts"])
                        buf["event"].message_str = merged
                        logger.info(f"Sylanne fragment merged (debounce): {merged[:60]}")
                        await self._process_llm_request_final(buf["event"], buf["request"], merged, sk, realtime_enabled, hajide, intercept)

                timer = asyncio.ensure_future(_process_after_delay())
                self._fragment_timers[session_key] = timer
                self._background_tasks.append(timer)
                timer.add_done_callback(lambda t: self._background_tasks.remove(t) if t in self._background_tasks else None)
                return  # Don't process yet, wait for debounce

            # If we got here via max_wait, fall through to process

        await self._process_llm_request_final(event, request, message_text, session_key, realtime_enabled, hajide, intercept)

    async def _process_llm_request_final(self, event: Any, request: Any, message_text: str, session_key: str, realtime_enabled: bool, hajide: bool, intercept: bool) -> None:

        # Clear stream state for this session
        self._stream_buffers.pop(session_key, None)
        self._stream_first_sent.pop(session_key, None)

        # Schedule background observation (non-blocking)
        if message_text:
            task = asyncio.ensure_future(self._background_observe_request(session_key, message_text))
            self._background_tasks.append(task)
            task.add_done_callback(lambda t: self._background_tasks.remove(t) if t in self._background_tasks else None)

        # Cancel stale segmented reply tasks
        stale_task = self._segmented_tasks.pop(session_key, None)
        if stale_task and not stale_task.done():
            stale_task.cancel()

        # Wrap event.send_streaming if first-sentence dispatch is enabled
        stream_first = bool((self._config or {}).get("sylanne_alpha_stream_first_sentence_enabled"))
        if stream_first and intercept and hasattr(event, "send_streaming"):
            original_send_streaming = event.send_streaming
            plugin = self
            origin = str(getattr(event, "unified_msg_origin", "") or "")

            async def wrapped_send_streaming(generator, use_fallback=False):
                buffer = ""
                first_sent = False

                async def intercepted_generator():
                    nonlocal buffer, first_sent
                    async for chunk in generator:
                        yield chunk
                        if not first_sent:
                            buffer += str(chunk)
                            first_sentence = plugin._extract_first_sentence(buffer)
                            if first_sentence:
                                first_sent = True
                                plugin._stream_first_sent[session_key] = first_sentence
                                t = asyncio.ensure_future(plugin._send_first_sentence(origin, first_sentence))
                                plugin._background_tasks.append(t)
                                t.add_done_callback(lambda tt: plugin._background_tasks.remove(tt) if tt in plugin._background_tasks else None)

                await original_send_streaming(intercepted_generator(), use_fallback=use_fallback)

            event.send_streaming = wrapped_send_streaming

        if request is None:
            return

        # Detect model hint for Claude compat
        model_hint = ""
        if hajide:
            model_hint = await self._get_model_hint(event)

        # Create budget and normalize if needed
        budget = self._state_injection_budget_for_request(session_key, request, model_hint=model_hint)
        self._last_request_budgets[session_key] = budget

        if hajide or budget.compat_mode:
            self._normalize_claude_request_payload(request, budget=budget)

        # Inject time context
        time_fragment = self._time_context_fragment(session_key)
        current_prompt = str(getattr(request, "prompt", "") or "")

        # Inject unfinished reply context
        unfinished = self._unfinished_replies.pop(session_key, "")
        unfinished_fragment = ""
        if unfinished:
            # Record shadow signal for interruption only (followup comes from the text observe)
            host = self._host(session_key)
            host.kernel.body.observe_shadow_signal(text="", flags=["unfinished_reply"], kind="interruption")
            host.runtime.save(host.kernel)
            capped = unfinished[:_MAX_UNFINISHED_CONTEXT_CHARS]
            if len(unfinished) > _MAX_UNFINISHED_CONTEXT_CHARS:
                capped += "\n[sylanne_trimmed_fragment]"
            unfinished_fragment = f"\n上一轮回复没有说完，以下是未发送的部分（自然续接即可）：\n{capped}"

        # Consume pending outreach context (from life simulation)
        outreach_fragment = ""
        pending_outreach = getattr(self, "_pending_outreach_context", {})
        outreach_ctx = pending_outreach.pop(session_key, None)
        if outreach_ctx:
            reason = outreach_ctx.get("reason", "")
            mood = outreach_ctx.get("mood", "")
            outreach_fragment = (
                f"[life_event_context] Sylanne 刚刚经历了一件事想分享：{reason}（心情：{mood}）。"
                f"请自然地在回复中提及或表达这件事，用你自己的语气。"
            )

        # Use computation spine's recall result (already computed in kernel.tick)
        # instead of calling embedding provider again — avoids duplicate work
        memory_fragment = ""
        if realtime_enabled and message_text:
            host = self._host(session_key)
            comp_result = getattr(host.kernel, "_last_computation_result", None) or {}
            recalled = comp_result.get("recalled", [])
            if recalled:
                mem_lines = [f">{str(r.get('text',''))[:120]}" for r in recalled[:3] if r.get("text")]
                if mem_lines:
                    memory_fragment = "\n".join(mem_lines)

        # User's current message — always last for recency priority
        user_anchor = ""
        if message_text and realtime_enabled:
            user_anchor = f"当前：{message_text}"

        # Assemble final prompt: background context FIRST, user message LAST
        # LLM recency bias ensures current message gets highest attention
        bg_parts = []
        if time_fragment:
            bg_parts.append(time_fragment)
        if outreach_fragment:
            bg_parts.append(outreach_fragment)
        if memory_fragment:
            bg_parts.append(memory_fragment)
        if unfinished_fragment:
            bg_parts.append(unfinished_fragment)

        background = "\n".join(bg_parts) if bg_parts else ""

        # Structure: [original prompt] [background as parenthetical] [user's current message last]
        new_prompt = current_prompt

        if background:
            new_prompt = f"{new_prompt}\n（{background}）"
        if user_anchor:
            new_prompt = f"{new_prompt}\n{user_anchor}"

        new_prompt = new_prompt.strip()

        request.prompt = new_prompt

        # Start life simulator once (lazy init on first LLM request)
        if not getattr(self, "_life_simulator_started", False):
            self._life_simulator_started = True
            life_sim = getattr(self, "_life_simulator", None)
            if life_sim is not None:
                life_sim.configure(
                    llm_caller=self._life_sim_llm_call,
                    outreach_callback=self._life_sim_outreach,
                    emotion_getter=self._life_sim_emotion,
                )
                life_sim.start()
                self.logger.info(f"Sylanne life simulator: enabled={life_sim.enabled}, interval={life_sim.interval_seconds}s")

    async def _get_model_hint(self, event: Any = None) -> str:
        context = getattr(self, "context", None) or getattr(self, "_context", None)
        if hasattr(context, "get_current_chat_provider_id"):
            try:
                umo = str(getattr(event, "unified_msg_origin", "") or "") if event else ""
                if umo:
                    result = await context.get_current_chat_provider_id(umo=umo)
                else:
                    result = await context.get_current_chat_provider_id()
                return str(result or "")
            except Exception:
                pass
        return ""

    async def _background_observe_request(self, session_key: str, text: str) -> None:
        """Observe user message with two-level LLM assessment (bounded timeouts).

        Level 1 (fast): runs on every message, small model, 1.5s timeout.
        Level 2 (main): runs only when gate routes to "full", strong model, 3s timeout.

        Results are merged (main overrides fast) and passed to the computation
        spine to modulate Void-Scar state precisely. If both time out, the
        spine uses HDC coarse judgment only.
        """
        try:
            fast_result: dict = {}
            main_result: dict = {}

            # Fast assessor (always runs if enabled)
            fast_enabled = self._cfg_bool("sylanne_alpha_assessor_llm_enabled")
            if fast_enabled and text:
                fast_result = await self._async_assessor.assess_fast(
                    text, self._assessor_llm_call,
                )

            # Determine if main assessor should run (full path heuristic)
            # We check the gate's last route -- if it was "full", run main assessor
            host = self._host(session_key)
            last_route = host.kernel.computation._last_route
            main_enabled = self._cfg_bool("sylanne_alpha_main_assessor_enabled")
            if main_enabled and text and last_route == "full":
                # Gather recent context lines for richer assessment
                context_lines = self._recent_context_lines(session_key)
                main_result = await self._async_assessor.assess_main(
                    text, context_lines, self._main_assessor_llm_call,
                )

            # Merge: main overrides fast
            assessment = {**fast_result, **main_result}
            # Remove internal metadata
            assessment.pop("_level", None)
            assessment.pop("assessed_at", None)

            # Feed into computation spine with assessment
            now = time.time()
            event = SylanneAlphaHostEvent(
                text=text, confidence=0.7, flags=["safe"],
                now=now, event_time=self._event_time(now),
            )
            host.on_request(event, assessment=assessment if assessment else None)

            # Rhythm learning: observe user message timing for adaptive segmentation
            engine_obs = host.kernel.computation.engine.observe()
            self._rhythm_learner.observe_user_message(session_key, text, now, engine_obs)
        except Exception:
            # Fallback: observe without assessment
            try:
                await self.observe_request(
                    session_key, text=text, confidence=0.7,
                    flags=["safe"], now=time.time(),
                )
            except Exception:
                pass

    def _recent_context_lines(self, session_key: str) -> list[str]:
        """Get recent conversation lines for main assessor context."""
        host = self._host(session_key)
        traces = host.kernel.body.memory.get("traces", [])
        lines: list[str] = []
        for trace in traces[-3:]:
            text = str(trace.get("text") or "")[:100]
            if text:
                lines.append(text)
        return lines

    # ------------------------------------------------------------------
    # Assessor LLM callback
    # ------------------------------------------------------------------
    async def _assessor_llm_call(self, prompt: str) -> str:
        """Call configured LLM provider for fast semantic assessment.

        Uses max_tokens=50 and temperature=0 for fast, deterministic output.
        """
        provider_id = str(
            self._config.get("sylanne_alpha_assessor_provider_id")
            or self._config.get("emotion_provider_id")
            or ""
        )
        if not provider_id:
            return ""
        context = self.context
        if not hasattr(context, "get_provider_by_id"):
            return ""
        provider = context.get_provider_by_id(provider_id)
        if provider is None:
            return ""
        try:
            resp = await provider.text_chat(
                prompt=prompt,
                max_tokens=50,
                temperature=0.0,
            )
            return str(getattr(resp, "completion_text", "") or "")
        except TypeError:
            # Provider doesn't support max_tokens/temperature kwargs -- retry without
            try:
                resp = await provider.text_chat(prompt=prompt)
                return str(getattr(resp, "completion_text", "") or "")
            except Exception:
                return ""
        except Exception:
            return ""

    async def _main_assessor_llm_call(self, prompt: str) -> str:
        """Call configured LLM provider for main (deep) semantic assessment.

        Uses a stronger model with slightly more tokens allowed.
        """
        provider_id = str(
            self._config.get("sylanne_alpha_main_assessor_provider_id")
            or self._config.get("sylanne_alpha_assessor_provider_id")
            or self._config.get("emotion_provider_id")
            or ""
        )
        if not provider_id:
            return ""
        context = self.context
        if not hasattr(context, "get_provider_by_id"):
            return ""
        provider = context.get_provider_by_id(provider_id)
        if provider is None:
            return ""
        try:
            resp = await provider.text_chat(
                prompt=prompt,
                max_tokens=100,
                temperature=0.0,
            )
            return str(getattr(resp, "completion_text", "") or "")
        except TypeError:
            try:
                resp = await provider.text_chat(prompt=prompt)
                return str(getattr(resp, "completion_text", "") or "")
            except Exception:
                return ""
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Life Simulator callbacks
    # ------------------------------------------------------------------
    async def _life_sim_llm_call(self, prompt: str) -> str:
        """Call configured LLM provider for life simulation inference."""
        provider_id = str(self._config.get("sylanne_alpha_life_simulation_provider_id") or "")
        if not provider_id:
            return ""
        context = self.context
        if not hasattr(context, "get_provider_by_id"):
            return ""
        provider = context.get_provider_by_id(provider_id)
        if provider is None:
            return ""
        try:
            resp = await provider.text_chat(prompt=prompt)
            return str(getattr(resp, "completion_text", "") or "")
        except Exception:
            return ""

    async def _life_sim_outreach(self, reason: str, mood: str) -> None:
        """Store life event as pending outreach context for next LLM call.

        Instead of sending raw life event text directly, we store it so the
        next on_llm_request injects it as context -- letting the main chat
        model express it in Sylanne's voice.

        If no LLM request comes within a reasonable window, fall back to
        direct send via context.send_message (if available).
        """
        if not self._hosts:
            logger.info("Sylanne life_sim_outreach: no active hosts, skipping")
            return
        best_key = ""
        best_time = 0.0
        for sk, host in self._hosts.items():
            last_now = float(host.kernel.last_event.get("now") or 0.0)
            if last_now > best_time:
                best_time = last_now
                best_key = sk
        if not best_key:
            best_key = next(iter(self._hosts))

        # Store pending outreach context for injection into next LLM request
        if not hasattr(self, "_pending_outreach_context"):
            self._pending_outreach_context: dict[str, dict[str, str]] = {}
        self._pending_outreach_context[best_key] = {
            "reason": reason,
            "mood": mood,
        }
        logger.info(f"Sylanne life_sim_outreach: stored pending context for session={best_key}, mood={mood}")

        # Fallback: if no LLM request picks this up within 5 minutes,
        # send directly (scheduled as background task)
        async def _fallback_direct_send(session_key: str, r: str, m: str):
            await asyncio.sleep(300.0)
            pending = getattr(self, "_pending_outreach_context", {})
            if session_key in pending and pending[session_key].get("reason") == r:
                # Still not consumed -- send directly
                pending.pop(session_key, None)
                context = self.context
                if hasattr(context, "send_message"):
                    # Use LLM to generate in-character message if possible
                    generated = await self._generate_outreach_message(r, m)
                    if generated:
                        message = self._astrbot_message(generated)
                    else:
                        message = self._astrbot_message(f"[{m}] {r}")
                    try:
                        await context.send_message(session_key, message)
                    except Exception:
                        pass
                else:
                    logger.info("Sylanne life_sim_outreach fallback: context.send_message not available")

        task = asyncio.ensure_future(_fallback_direct_send(best_key, reason, mood))
        self._background_tasks.append(task)
        task.add_done_callback(lambda t: self._background_tasks.remove(t) if t in self._background_tasks else None)

    async def _generate_outreach_message(self, reason: str, mood: str) -> str:
        """Use LLM to generate an in-character outreach message from life event."""
        provider_id = str(self._config.get("sylanne_alpha_life_simulation_provider_id") or "")
        if not provider_id:
            return ""
        context = self.context
        if not hasattr(context, "get_provider_by_id"):
            return ""
        provider = context.get_provider_by_id(provider_id)
        if provider is None:
            return ""
        prompt = (
            f"你是 Sylanne，一个有自己生活的角色。你刚刚经历了一件事想和朋友分享。\n"
            f"事件：{reason}\n心情：{mood}\n"
            f"请用你自然的语气写一条简短的消息给朋友（不要解释你是AI，不要用括号标注心情）。"
            f"直接输出消息内容，不要加任何前缀。"
        )
        try:
            resp = await provider.text_chat(prompt=prompt)
            text = str(getattr(resp, "completion_text", "") or "").strip()
            return text[:200] if text else ""
        except Exception:
            return ""

    def _life_sim_emotion(self) -> dict[str, float]:
        """Get emotion state from the most recently active host's computation spine."""
        if not self._hosts:
            return {}
        best_key = ""
        best_time = 0.0
        for sk, host in self._hosts.items():
            last_now = float(host.kernel.last_event.get("now") or 0.0)
            if last_now > best_time:
                best_time = last_now
                best_key = sk
        if not best_key:
            best_key = next(iter(self._hosts))
        host = self._hosts[best_key]
        try:
            return host.kernel.computation.engine.observe()
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # on_llm_response hook -- segmented reply dispatch
    # ------------------------------------------------------------------
    @filter.on_llm_response()
    async def on_llm_response(self, event: Any, response: Any) -> None:
        if not hasattr(self, "_stream_first_sent"):
            self._stream_first_sent = {}
        if not hasattr(self, "_unfinished_replies"):
            self._unfinished_replies = {}
        if not hasattr(self, "_background_tasks"):
            self._background_tasks = []
        if not hasattr(self, "_segmented_tasks"):
            self._segmented_tasks = {}
        session_key = self._session_key(event)
        cfg = self._config or {}
        realtime_enabled = bool(cfg.get("sylanne_alpha_realtime_chat_enabled") or cfg.get("enable_realtime_chat"))
        intercept = bool(cfg.get("sylanne_alpha_realtime_intercept_llm_response") or cfg.get("realtime_chat_intercept_llm_response"))

        if not realtime_enabled or not intercept:
            # Still filter thinking/draft blocks
            if response is not None:
                text = str(getattr(response, "completion_text", "") or "")
                cleaned = strip_draft_blocks(text)
                if cleaned != text:
                    response.completion_text = cleaned
            return

        if response is None:
            return

        text = str(getattr(response, "completion_text", "") or "")
        cleaned = strip_draft_blocks(text)
        self.logger.info(f"Sylanne on_llm_response: len={len(cleaned)} session={session_key}")

        if not cleaned.strip():
            response.completion_text = ""
            return

        # Check if first sentence was already sent via streaming
        first_sent = self._stream_first_sent.pop(session_key, "")
        if first_sent:
            # First sentence already dispatched via streaming -- don't re-send
            # Store unfinished remainder
            remainder = cleaned
            if remainder.startswith(first_sent):
                remainder = remainder[len(first_sent):].strip()
            elif first_sent.rstrip("。！？!?.") in remainder:
                idx = remainder.find(first_sent.rstrip("。！？!?."))
                end_idx = idx + len(first_sent)
                if end_idx < len(remainder):
                    remainder = remainder[end_idx:].strip()
                else:
                    remainder = ""
            if remainder:
                self._unfinished_replies[session_key] = remainder
            # Don't modify completion_text, don't stop event
            return

        # Segment and dispatch
        origin = str(getattr(event, "unified_msg_origin", "") or "")
        cfg = self._config or {}
        default_max_part = int(cfg.get("realtime_chat_max_part_chars", 48))
        default_cps = 7.5
        max_part_chars, cps = self._rhythm_learner.get_rhythm_params(
            session_key, default_max_part=default_max_part, default_cps=default_cps,
        )
        plan = realtime_plan(session_key, cleaned, max_part_chars=max_part_chars, chars_per_second=cps)
        parts = plan.get("message_parts", [])

        if not parts:
            response.completion_text = cleaned
            return

        # Keep completion_text intact for AstrBot's context history recording.
        # Clear result_chain to prevent AstrBot from sending the full message
        # (we handle sending via segmented dispatch instead).
        response.completion_text = cleaned
        if hasattr(response, "result_chain"):
            response.result_chain = None
        if hasattr(response, "chain"):
            response.chain = None

        # Store unfinished for next round if multi-part
        if len(parts) > 1:
            sent_first = parts[0]["text"]
            rest = cleaned
            if rest.startswith(sent_first):
                rest = rest[len(sent_first):].strip()
            self._unfinished_replies[session_key] = rest

        # Dispatch segments in background
        self.logger.info(f"Sylanne segmented reply queued: session={session_key} parts={len(parts)}")
        task = asyncio.ensure_future(self._dispatch_segmented_parts(origin, parts))
        self._background_tasks.append(task)
        task.add_done_callback(lambda t: self._background_tasks.remove(t) if t in self._background_tasks else None)
        self._segmented_tasks[session_key] = task

        # Schedule observation off the hot path
        obs_task = asyncio.ensure_future(self._background_observe_response(session_key, cleaned))
        self._background_tasks.append(obs_task)
        obs_task.add_done_callback(lambda t: self._background_tasks.remove(t) if t in self._background_tasks else None)

    async def _background_observe_response(self, session_key: str, text: str) -> None:
        try:
            await self.observe_response(session_key, text=text[:500], confidence=0.7, flags=["safe"], now=time.time())
        except Exception:
            pass

    # ------------------------------------------------------------------
    # on_llm_stream_chunk hook -- dispatch first sentence early
    # ------------------------------------------------------------------
    async def on_llm_stream_chunk(self, event: Any, chunk: Any) -> None:
        session_key = self._session_key(event)
        intercept = bool(self._config.get("sylanne_alpha_realtime_intercept_llm_response"))
        if not intercept:
            return

        delta = str(getattr(chunk, "delta", "") or "")
        if not delta:
            return

        buffer = self._stream_buffers.get(session_key, "") + delta
        self._stream_buffers[session_key] = buffer

        # Check if we have a complete first sentence
        first_sentence = self._extract_first_sentence(buffer)
        if first_sentence and session_key not in self._stream_first_sent:
            self._stream_first_sent[session_key] = first_sentence
            self._stream_buffers.pop(session_key, None)
            origin = str(getattr(event, "unified_msg_origin", "") or "")
            task = asyncio.ensure_future(self._send_first_sentence(origin, first_sentence))
            self._background_tasks.append(task)
            task.add_done_callback(lambda t: self._background_tasks.remove(t) if t in self._background_tasks else None)

    def _extract_first_sentence(self, text: str) -> str:
        """Extract first complete sentence from buffer."""
        delimiters = "。！？!?；;"
        for i, ch in enumerate(text):
            if ch in delimiters and i > 0:
                # Check if next char is not also a delimiter (e.g. "！？")
                if i + 1 < len(text) and text[i + 1] in delimiters:
                    continue
                return text[:i + 1]
            if ch == "\n" and i > 0:
                return text[:i]
        return ""

    async def _send_first_sentence(self, origin: str, text: str) -> None:
        context = self.context
        if hasattr(context, "send_message"):
            message = self._astrbot_message(text)
            await context.send_message(origin, message)

    # ------------------------------------------------------------------
    # Segmented dispatch
    # ------------------------------------------------------------------
    async def _dispatch_segmented_parts(self, origin: str, parts: list[dict[str, Any]]) -> None:
        context = self.context
        if not hasattr(context, "send_message"):
            return
        total = len(parts)
        for idx, part in enumerate(parts, 1):
            delay = float(part.get("delay_before_seconds", 0))
            if delay > 0:
                await asyncio.sleep(delay)
            text = str(part.get("text", ""))
            if not text:
                continue
            self.logger.info(f"Sylanne segmented reply part {idx}/{total}: {text[:60]}")
            message = self._astrbot_message(text)
            await context.send_message(origin, message)

    # ------------------------------------------------------------------
    # Memory prompt fragment
    # ------------------------------------------------------------------
    def _memory_prompt_fragment(self, payload: dict[str, Any]) -> str:
        matches = payload.get("matches", [])
        query = str(payload.get("query") or "")
        if not matches:
            return ""
        lines = [
            "[M:ref/pri=current]",
        ]
        for match in matches[:3]:
            text = str(match.get("text") or "")[:120]
            lines.append(f">{text}")
        return "\n".join(line for line in lines if line)

    def _append_request_prompt_fragment(self, request: Any, fragment: str) -> None:
        if not fragment:
            return
        current = str(getattr(request, "prompt", "") or "")
        request.prompt = f"{current}\n{fragment}".strip()

    # ------------------------------------------------------------------
    # Time context
    # ------------------------------------------------------------------
    def _time_context_fragment(self, session_key: str) -> str:
        now = datetime.now(_CHINA_TZ)
        weekday_names = ["一", "二", "三", "四", "五", "六", "日"]
        weekday = weekday_names[now.weekday()]
        time_str = now.strftime("%H:%M")
        date_str = now.strftime("%m-%d")

        host = self._host(session_key)
        kernel = host.kernel
        last_event = kernel.last_event or {}
        has_previous = bool(last_event.get("now") or last_event.get("text"))
        if has_previous:
            last_now = float(last_event.get("now") or 0.0)
            gap_seconds = max(0.0, time.time() - last_now) if last_now else 0.0
            gap_label = self._gap_label_from_seconds(gap_seconds, True)
        else:
            gap_label = "首次"

        return f"[T:{date_str}-W{now.weekday()}-{time_str}/gap:{gap_label}]"

    def _gap_label_from_seconds(self, seconds: float, has_previous: bool) -> str:
        if not has_previous:
            return "first_event"
        if seconds < 900:
            return "刚刚"
        if seconds < 7200:
            return "刚才"
        if seconds < 86400:
            return "隔了一阵"
        if seconds < 259200:
            return "隔天"
        return "隔了很久"

    def _event_time(self, now: float = 0.0) -> dict[str, Any]:
        ts = datetime.now(_CHINA_TZ)
        return {
            "local_datetime": ts.isoformat(),
            "timezone": "Asia/Shanghai",
            "epoch": now or time.time(),
        }

    # ------------------------------------------------------------------
    # Payload capping
    # ------------------------------------------------------------------
    def _cap_llm_request_payload(self, request: Any) -> None:
        locked = self._config.get("sylanne_alpha_locked_persona_prompt")
        locked_system = str(locked) if locked else None

        system_prompt = getattr(request, "system_prompt", None)
        prompt = getattr(request, "prompt", None)

        for pass_num in range(5):
            try:
                serialized = json.dumps(request.__dict__, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                break
            if len(serialized) <= _MAX_PAYLOAD_SERIALIZED_CHARS:
                break

            text_limit = max(200, 5000 // (pass_num + 1))

            extra = getattr(request, "extra_user_content_parts", None)
            if isinstance(extra, list) and extra:
                request.extra_user_content_parts = self._trim_payload_list(extra, keep_items=1, text_limit=text_limit)

            if pass_num >= 2:
                keep = max(4, 8 - pass_num * 2)
                contexts = getattr(request, "contexts", None)
                if isinstance(contexts, list) and contexts:
                    request.contexts = self._trim_payload_list(contexts, keep_items=keep, text_limit=text_limit)
                messages = getattr(request, "messages", None)
                if isinstance(messages, list) and messages:
                    filtered = [m for m in messages if not isinstance(m, str)]
                    request.messages = self._trim_payload_list(filtered, keep_items=keep, text_limit=text_limit)

    def _trim_payload_list(self, items: list, keep_items: int = 2, text_limit: int = 5000) -> list:
        if not items:
            return items
        if len(items) <= keep_items:
            # Just cap text length
            return [self._cap_item_text(item, text_limit) for item in items]

        # Strategy: keep first `keep_items` items + 1 marker replacing the rest
        kept = [self._cap_item_text(items[i], text_limit) for i in range(min(keep_items, len(items)))]
        # Always keep the last item if it's different from what we already kept
        tail = self._cap_item_text(items[-1], text_limit)
        marker = self._make_trim_marker(items)

        # If keep_items >= 2, result = kept[:-1] + [marker] + [tail]
        # If keep_items == 1, result = [kept[0], marker]  (tail is sacrificed)
        if keep_items >= 2:
            result = [kept[0], marker, tail]
            if keep_items > 2 and len(kept) > 1:
                result = kept[:-1] + [marker, tail]
        else:
            # keep_items == 1: just head + marker
            result = [kept[0], marker]

        return result

    def _cap_item_text(self, item: Any, limit: int) -> Any:
        if isinstance(item, dict):
            # Check both "content" and "text" keys
            for key in ("content", "text"):
                val = item.get(key, "")
                if isinstance(val, str) and len(val) > limit:
                    item = dict(item)
                    item[key] = val[:limit] + "\n[sylanne_payload_context_trimmed]"
            return item
        if hasattr(item, "text"):
            text = str(getattr(item, "text", "") or "")
            if len(text) > limit:
                try:
                    item.text = text[:limit] + "\n[sylanne_payload_context_trimmed]"
                except (AttributeError, TypeError):
                    pass
            return item
        if hasattr(item, "content"):
            content = str(getattr(item, "content", "") or "")
            if len(content) > limit:
                try:
                    item.content = content[:limit] + "\n[sylanne_payload_context_trimmed]"
                except (AttributeError, TypeError):
                    pass
            return item
        return item

    def _make_trim_marker(self, items: list) -> Any:
        """Create a trim marker matching the type of items in the list."""
        sample = items[1] if len(items) > 1 else items[0]
        if isinstance(sample, dict):
            role = sample.get("role", "user")
            return {"role": role, "content": "[sylanne_payload_context_trimmed]"}
        if hasattr(sample, "text"):
            # Try to create same type
            try:
                marker = type(sample)(text="[sylanne_payload_context_trimmed]")
                return marker
            except (TypeError, ValueError):
                return SimpleNamespace(text="[sylanne_payload_context_trimmed]")
        return {"role": "user", "content": "[sylanne_payload_context_trimmed]"}

    # ------------------------------------------------------------------
    # Observatory (WebUI readonly)
    # ------------------------------------------------------------------
    async def sylanne_observatory(self, *, session_key: str) -> dict[str, Any]:
        host = self._host(session_key)
        surface = host.diagnostics()
        body = surface["body"]
        diagnostics = surface["diagnostics"]
        memory_traces = body["memory"]["traces"]

        cards = [
            {"id": "body", "title": "身体感", "summary": f"warmth={body['temperature']['warmth']:.2f}; pulse={body['pulse']['rhythm']:.2f}"},
            {"id": "memory", "title": "记忆", "summary": f"traces={len(memory_traces)}"},
            {"id": "drift", "title": "人格漂移", "summary": f"plasticity={diagnostics['vector_summary']['plasticity']:.3f}"},
            {"id": "space", "title": "神经网络空间感", "summary": f"vitality={diagnostics['vector_summary']['vitality']:.3f}"},
        ]

        memory_nodes = [
            {"id": trace.get("id", f"node-{i}"), "label": f"trace-{i}", "strength": float(trace.get("weight", 0.2))}
            for i, trace in enumerate(memory_traces[-8:])
        ] or [{"id": "empty", "label": "等待记忆点", "strength": 0.2}]

        config_controls = [
            {"id": "sylanne_alpha_realtime_chat_enabled", "title": "即时聊天", "enabled": bool(self._config.get("sylanne_alpha_realtime_chat_enabled"))},
            {"id": "sylanne_alpha_proactive_dispatch_enabled", "title": "主动发言", "enabled": bool(self._config.get("sylanne_alpha_proactive_dispatch_enabled"))},
            {"id": "sylanne_alpha_embedding_memory_enabled", "title": "向量记忆", "enabled": bool(self._config.get("sylanne_alpha_embedding_memory_enabled"))},
        ]

        # Sanitize body to remove raw text
        sanitized_body = dict(body)
        sanitized_body["memory"] = {"trace_count": len(memory_traces)}
        # Sanitize body_state
        body_state = dict(diagnostics["body_state"])
        # Sanitize memory_state
        memory_state = {"trace_count": len(memory_traces)}

        return {
            "schema_version": "sylanne.alpha.observatory.v1",
            "session_key": session_key,
            "mode": "readonly",
            "read_only": True,
            "body": sanitized_body,
            "body_state": body_state,
            "memory_state": memory_state,
            "persona_drift_state": diagnostics["vector_summary"],
            "network_space_state": {"vitality": diagnostics["vector_summary"]["vitality"]},
            "decision": surface["decision"],
            "guard": surface["guard"],
            "memory": {"trace_count": len(memory_traces)},
            "switches": {"paused": body["immunity"]["paused"], "realtime": bool(self._config.get("sylanne_alpha_realtime_chat_enabled"))},
            "cards": cards,
            "visualization": {
                "token_flow": {"title": "Token 分段使用", "tokens": [f"t{i}" for i in range(min(5, len(memory_traces)))]},
                "memory_nodes": memory_nodes,
                "persona_model": {"traits": {"plasticity": diagnostics["vector_summary"]["plasticity"], "vitality": diagnostics["vector_summary"]["vitality"]}},
            },
            "config_controls": config_controls,
            "constraints": ["no_raw_conversation_text", "readonly_only"],
        }

    async def _observatory_route_handler(self) -> dict[str, Any]:
        session_key = "default"
        if self._hosts:
            session_key = next(iter(self._hosts))
        return await self.sylanne_observatory(session_key=session_key)

    # ------------------------------------------------------------------
    # Claude/hajide compat stubs (minimal implementation)
    # ------------------------------------------------------------------
    def _state_injection_budget_for_request(self, session_key: str, request: Any, model_hint: str = "") -> _StateInjectionBudget:
        budget = _StateInjectionBudget(session_key=session_key, model_hint=model_hint)
        cfg = self.config or {}
        budget.max_added_chars = int(cfg.get("state_injection_max_added_chars", 2400))
        budget.max_parts = int(cfg.get("state_injection_max_parts", 8))
        hajide = bool(cfg.get("sylanne_alpha_hajide_compat_mode"))
        is_claude = "claude" in model_hint.lower() or "anthropic" in model_hint.lower() or "哈基德" in model_hint
        if hajide and is_claude:
            budget.compat_mode = "claude_agent_owned_context"
        elif is_claude:
            budget.compat_mode = "claude_advisory"
        return budget

    def _append_temp_text_part(self, request: Any, text: str, source: str = "", budget: _StateInjectionBudget | None = None) -> bool:
        if budget and budget.compat_mode == "claude_agent_owned_context":
            budget.skipped.append({"source": source, "reason": "claude_agent_owned_context"})
            return False
        if budget and budget.compat_mode == "claude_advisory":
            # For claude advisory mode, append to prompt with advisory marker
            current = str(getattr(request, "prompt", "") or "")
            if "[claude_advisory_context]" not in current:
                request.prompt = f"{current}\n[claude_advisory_context]\n{text}".strip()
            else:
                request.prompt = f"{current}\n{text}".strip()
            if budget:
                budget.injected.append({"source": source})
            return True
        # Normal mode: append to extra_user_content_parts
        parts = getattr(request, "extra_user_content_parts", None)
        if isinstance(parts, list):
            parts.append(SimpleNamespace(text=text))
        if budget:
            budget.injected.append({"source": source})
        return True

    def _normalize_claude_request_payload(self, request: Any, budget: _StateInjectionBudget | None = None) -> None:
        hajide = bool(self._config.get("sylanne_alpha_hajide_compat_mode"))

        # Flatten extra_user_content_parts into prompt
        extra = getattr(request, "extra_user_content_parts", None)
        if isinstance(extra, list) and extra:
            texts = []
            for part in extra:
                if hasattr(part, "text"):
                    texts.append(str(part.text))
                elif isinstance(part, dict) and "text" in part:
                    texts.append(str(part["text"]))
            if texts:
                current = str(getattr(request, "prompt", "") or "")
                request.prompt = f"{current}\n" + "\n".join(texts)
            request.extra_user_content_parts = []

        # Flatten contents into prompt
        contents = getattr(request, "contents", None)
        if isinstance(contents, list) and contents:
            texts = []
            for item in contents:
                if isinstance(item, dict) and "text" in item:
                    texts.append(str(item["text"]))
                elif hasattr(item, "text"):
                    texts.append(str(item.text))
            if texts:
                current = str(getattr(request, "prompt", "") or "")
                request.prompt = f"{current}\n" + "\n".join(texts)
            request.contents = []

        # Flatten contexts with system role into system_prompt
        contexts = getattr(request, "contexts", None)
        if isinstance(contexts, list) and contexts:
            system_parts = []
            remaining = []
            for ctx in contexts:
                role = ctx.get("role", "") if isinstance(ctx, dict) else str(getattr(ctx, "role", ""))
                content = ctx.get("content", "") if isinstance(ctx, dict) else str(getattr(ctx, "content", ""))
                if role == "system":
                    system_parts.append(content)
                else:
                    remaining.append(ctx)
            if system_parts:
                sys_prompt = str(getattr(request, "system_prompt", "") or "")
                request.system_prompt = f"{sys_prompt}\n" + "\n".join(system_parts) if sys_prompt else "\n".join(system_parts)
            request.contexts = remaining if not hajide else []

        # Sanitize messages
        messages = getattr(request, "messages", None)
        if isinstance(messages, list) and messages:
            clean = []
            for msg in messages:
                if isinstance(msg, dict):
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if hajide:
                        # In hajide mode, skip tool/function messages and assistant with tool_calls
                        if role in ("tool", "function"):
                            continue
                        if role == "assistant" and "tool_calls" in msg:
                            continue
                    # Convert system to system_prompt
                    if role == "system":
                        sys_prompt = str(getattr(request, "system_prompt", "") or "")
                        request.system_prompt = f"{sys_prompt}\n{content}" if sys_prompt else content
                        continue
                    # Normalize content
                    if isinstance(content, list):
                        text_parts = [str(p.get("text", "")) if isinstance(p, dict) else str(getattr(p, "text", "")) for p in content]
                        content = "\n".join(text_parts)
                    # Map non-standard roles to user
                    mapped_role = role if role in ("user", "assistant") else "user"
                    clean.append({"role": mapped_role, "content": content})
                elif hasattr(msg, "role"):
                    role = str(getattr(msg, "role", ""))
                    content = getattr(msg, "content", "")
                    if hajide and role in ("tool", "function"):
                        continue
                    if isinstance(content, list):
                        text_parts = [str(p.get("text", "")) if isinstance(p, dict) else str(getattr(p, "text", "")) for p in content]
                        content = "\n".join(text_parts)
                    mapped_role = role if role in ("user", "assistant") else "user"
                    clean.append({"role": mapped_role, "content": str(content)})
            request.messages = clean

        # Hajide mode: prune sylanne tools
        if hajide:
            self._prune_hajide_tools(request, budget)

    def _prune_hajide_tools(self, request: Any, budget: _StateInjectionBudget | None = None) -> None:
        _SYLANNE_TOOL_PREFIXES = ("query_agent_state", "get_bot_emotion", "get_bot_integrated", "get_bot_humanlike", "get_bot_lifelike", "get_bot_personality")

        def _is_sylanne_tool(name: str) -> bool:
            return any(name.startswith(prefix) for prefix in _SYLANNE_TOOL_PREFIXES)

        # Prune tools list
        tools = getattr(request, "tools", None)
        if isinstance(tools, list):
            request.tools = [t for t in tools if not (isinstance(t, dict) and _is_sylanne_tool(t.get("function", {}).get("name", "")))]
            if budget:
                budget.skipped.append({"source": "sylanne_llm_tools", "reason": "hajide_compat"})

        # Prune functions list
        functions = getattr(request, "functions", None)
        if isinstance(functions, list):
            request.functions = [f for f in functions if not (isinstance(f, dict) and _is_sylanne_tool(f.get("name", "")))]

        # Reset tool_choice if it pointed to a pruned tool
        tool_choice = getattr(request, "tool_choice", None)
        if isinstance(tool_choice, dict):
            name = tool_choice.get("function", {}).get("name", "") if isinstance(tool_choice.get("function"), dict) else ""
            if _is_sylanne_tool(name) or name:
                request.tool_choice = "auto"
        elif tool_choice == "required":
            request.tool_choice = "auto"

        # Reset function_call
        function_call = getattr(request, "function_call", None)
        if isinstance(function_call, dict):
            request.function_call = "auto"

        # Handle nested params.extra_body
        params = getattr(request, "params", None)
        if isinstance(params, dict) and "extra_body" in params:
            extra_body = params["extra_body"]
            if isinstance(extra_body, dict):
                if "tools" in extra_body and isinstance(extra_body["tools"], list):
                    extra_body["tools"] = [t for t in extra_body["tools"] if not (isinstance(t, dict) and _is_sylanne_tool(t.get("function", {}).get("name", "")))]
                if "tool_choice" in extra_body and isinstance(extra_body["tool_choice"], dict):
                    extra_body["tool_choice"] = "auto"

        # Handle metadata.tool_choice
        metadata = getattr(request, "metadata", None)
        if isinstance(metadata, dict) and "tool_choice" in metadata:
            if isinstance(metadata["tool_choice"], dict):
                metadata["tool_choice"] = "auto"

        # Handle provider_settings.function_call
        provider_settings = getattr(request, "provider_settings", None)
        if isinstance(provider_settings, dict) and "function_call" in provider_settings:
            if isinstance(provider_settings["function_call"], dict):
                provider_settings["function_call"] = "auto"

        # Disable func_tool
        func_tool = getattr(request, "func_tool", None)
        if func_tool is not None:
            # Check if it has sylanne tools
            names = []
            if hasattr(func_tool, "names"):
                names = func_tool.names()
            elif hasattr(func_tool, "funcs") and isinstance(func_tool.funcs, dict):
                names = list(func_tool.funcs.keys())
            if names and any(_is_sylanne_tool(n) for n in names):
                request.func_tool = None
                if hasattr(request, "tool_choice"):
                    request.tool_choice = "auto"
                if budget:
                    budget.skipped.append({"source": "sylanne_func_tool", "reason": "hajide_compat"})


    # ------------------------------------------------------------------
    # Text extraction from event
    # ------------------------------------------------------------------
    def _text(self, event: Any) -> str:
        """Extract text from event, including forward messages and JSON links."""
        parts: list[str] = []
        message_str = str(getattr(event, "message_str", "") or "")
        if message_str:
            parts.append(message_str)

        chain = getattr(event, "message_chain", None)
        if isinstance(chain, list):
            for component in chain:
                comp_type = str(getattr(component, "type", "") or "")
                if comp_type == "Plain":
                    text = str(getattr(component, "text", "") or "")
                    if text and text not in parts:
                        parts.append(text)
                elif comp_type == "Forward":
                    nodes = getattr(component, "nodes", [])
                    if isinstance(nodes, list):
                        for node in nodes:
                            if isinstance(node, dict):
                                content = node.get("content", "")
                                if content:
                                    parts.append(str(content))
                            elif hasattr(node, "message"):
                                msg_list = getattr(node, "message", [])
                                if isinstance(msg_list, list):
                                    for m in msg_list:
                                        t = str(getattr(m, "text", "") or "")
                                        if t:
                                            parts.append(t)
                elif comp_type == "Json":
                    data = getattr(component, "data", None)
                    if isinstance(data, dict):
                        meta = data.get("meta", {})
                        if isinstance(meta, dict):
                            news = meta.get("news", {})
                            if isinstance(news, dict):
                                title = str(news.get("title", "") or "")
                                desc = str(news.get("desc", "") or "")
                                if title:
                                    parts.append(title)
                                if desc:
                                    parts.append(desc)

        return " ".join(parts) if parts else ""

    # ------------------------------------------------------------------
    # AstrBot message building
    # ------------------------------------------------------------------
    def _astrbot_message(self, text: str) -> Any:
        """Build a message suitable for context.send_message."""
        import sys
        comp_mod = sys.modules.get("astrbot.api.message_components")
        event_mod = sys.modules.get("astrbot.api.event")
        if comp_mod and event_mod:
            _Plain = getattr(comp_mod, "Plain", None)
            _Chain = getattr(event_mod, "MessageChain", None)
            if _Plain and _Chain:
                chain = _Chain()
                part = _Plain(text)
                # Support both .chain and .parts attributes
                if hasattr(chain, "chain") and isinstance(chain.chain, list):
                    chain.chain.append(part)
                elif hasattr(chain, "parts") and isinstance(chain.parts, list):
                    chain.parts.append(part)
                else:
                    # Try append method
                    if hasattr(chain, "append"):
                        chain.append(part)
                return chain
        # Fallback: just return the text string
        return text

    # ------------------------------------------------------------------
    # Stub methods for AstrBot decorator compatibility
    # ------------------------------------------------------------------
    async def sylanne_status(self, *args, **kwargs) -> dict[str, Any]:
        return {"ok": True}

    async def sylanne_proactive(self, *args, **kwargs) -> dict[str, Any]:
        return {"ok": True}

    # ------------------------------------------------------------------
    # Public API protocol stubs
    # ------------------------------------------------------------------
    async def get_emotion_consequences(self, *args, **kwargs) -> dict[str, Any]:
        sk = self._session_key(kwargs.get("event_or_session"), kwargs.get("session_key", ""))
        return command_surface(self._host(sk), "emotion")

    async def get_emotion_relationship(self, *args, **kwargs) -> dict[str, Any]:
        sk = self._session_key(kwargs.get("event_or_session"), kwargs.get("session_key", ""))
        return command_surface(self._host(sk), "emotion")

    async def get_emotion_prompt_fragment(self, *args, **kwargs) -> str:
        return ""

    async def get_psychological_screening_snapshot(self, *args, **kwargs) -> dict[str, Any]:
        sk = self._session_key(kwargs.get("event_or_session"), kwargs.get("session_key", ""))
        return command_surface(self._host(sk), "psych_state")

    async def get_psychological_screening_values(self, *args, **kwargs) -> dict[str, float]:
        return {}

    async def observe_psychological_text(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def simulate_psychological_update(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def reset_psychological_screening_state(self, *args, **kwargs) -> bool:
        return True

    async def reset_emotion_state(self, *args, **kwargs) -> bool:
        sk = self._session_key(kwargs.get("event_or_session"), kwargs.get("session_key", ""))
        await self.reset_sylanne(session_key=sk)
        return True

    async def get_integrated_self_snapshot(self, *args, **kwargs) -> dict[str, Any]:
        sk = self._session_key(kwargs.get("event_or_session"), kwargs.get("session_key", ""))
        return command_surface(self._host(sk), "integrated_self")

    async def get_integrated_self_prompt_fragment(self, *args, **kwargs) -> str:
        return ""

    async def get_integrated_self_policy_plan(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def build_integrated_self_replay_bundle(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def replay_integrated_self_bundle(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def probe_integrated_self_compatibility(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def export_integrated_self_diagnostics(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def get_lifelike_learning_snapshot(self, *args, **kwargs) -> dict[str, Any]:
        sk = self._session_key(kwargs.get("event_or_session"), kwargs.get("session_key", ""))
        result = command_surface(self._host(sk), "lifelike_state")
        result.setdefault("enabled", True)
        result.setdefault("exposure", kwargs.get("exposure", "plugin_safe"))
        return result

    async def get_lifelike_initiative_policy(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def request_proactive_speech_dispatch(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def observe_user_message_withdrawal(self, *args, **kwargs) -> dict[str, Any]:
        event = args[0] if args else None
        session_key = kwargs.get("session_key", "")
        message_id = kwargs.get("message_id", "")
        reason = kwargs.get("reason", "")
        if event and not session_key:
            session_key = str(getattr(event, "unified_msg_origin", "") or "")
            raw = getattr(event, "raw_message", None) or {}
            if not raw:
                msg_obj = getattr(event, "message_obj", None)
                if msg_obj:
                    raw = getattr(msg_obj, "raw_message", None) or {}
            if not message_id:
                message_id = str(raw.get("message_id", ""))
            if not reason:
                reason = str(raw.get("notice_type", ""))
        epochs = getattr(self, "_conversation_input_epoch", {})
        current_epoch = epochs.get(session_key, 0)
        new_epoch = current_epoch + 1
        epochs[session_key] = new_epoch
        last_text = getattr(self, "_last_request_text", {})
        last_text.pop(session_key, None)
        withdrawals = getattr(self, "_user_message_withdrawals", {})
        withdrawals[session_key] = {
            "message_id": message_id,
            "reason": reason,
            "input_epoch": new_epoch,
        }
        candidates = getattr(self, "_proactive_candidate_sessions", {})
        if session_key in candidates:
            candidates[session_key]["last_user_text_excerpt"] = ""
            candidates[session_key]["last_withdrawn_message_id"] = message_id
        return {"input_epoch": new_epoch, "message_id": message_id, "reason": reason, "session_key": session_key}

    async def observe_sticker_usage(self, *args, **kwargs) -> dict[str, Any]:
        return {"committed": False, "memory_count": 0}

    async def get_lifelike_prompt_fragment(self, *args, **kwargs) -> str:
        return ""

    async def observe_lifelike_text(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def simulate_lifelike_update(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def reset_lifelike_learning_state(self, *args, **kwargs) -> bool:
        return True

    async def get_personality_drift_snapshot(self, *args, **kwargs) -> dict[str, Any]:
        sk = self._session_key(kwargs.get("event_or_session"), kwargs.get("session_key", ""))
        result = command_surface(self._host(sk), "personality_drift_state")
        result.setdefault("enabled", True)
        result.setdefault("exposure", kwargs.get("exposure", "plugin_safe"))
        return result

    async def get_personality_drift_values(self, *args, **kwargs) -> dict[str, float]:
        return {}

    async def get_personality_drift_prompt_fragment(self, *args, **kwargs) -> str:
        return ""

    async def observe_personality_drift_event(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def simulate_personality_drift_update(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def reset_personality_drift_state(self, *args, **kwargs) -> bool:
        return True

    async def get_fallibility_snapshot(self, *args, **kwargs) -> dict[str, Any]:
        sk = self._session_key(kwargs.get("event_or_session"), kwargs.get("session_key", ""))
        return command_surface(self._host(sk), "fallibility_state")

    async def get_fallibility_values(self, *args, **kwargs) -> dict[str, float]:
        return {}

    async def get_fallibility_prompt_fragment(self, *args, **kwargs) -> str:
        return ""

    async def observe_fallibility_text(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def simulate_fallibility_update(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def reset_fallibility_state(self, *args, **kwargs) -> bool:
        return True

    async def get_humanlike_snapshot(self, *args, **kwargs) -> dict[str, Any]:
        sk = self._session_key(kwargs.get("event_or_session"), kwargs.get("session_key", ""))
        result = command_surface(self._host(sk), "humanlike_state")
        result.setdefault("enabled", True)
        exposure = kwargs.get("exposure", "plugin_safe")
        result.setdefault("exposure", exposure)
        return result

    async def get_humanlike_values(self, *args, **kwargs) -> dict[str, float]:
        return {}

    async def get_humanlike_prompt_fragment(self, *args, **kwargs) -> str:
        return ""

    async def observe_humanlike_text(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def simulate_humanlike_update(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def reset_humanlike_state(self, *args, **kwargs) -> bool:
        return True

    async def get_moral_repair_snapshot(self, *args, **kwargs) -> dict[str, Any]:
        sk = self._session_key(kwargs.get("event_or_session"), kwargs.get("session_key", ""))
        return command_surface(self._host(sk), "moral_repair_state")

    async def get_moral_repair_values(self, *args, **kwargs) -> dict[str, float]:
        return {}

    async def get_moral_repair_prompt_fragment(self, *args, **kwargs) -> str:
        return ""

    async def observe_moral_repair_text(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def simulate_moral_repair_update(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def reset_moral_repair_state(self, *args, **kwargs) -> bool:
        return True

    async def get_group_atmosphere_snapshot(self, *args, **kwargs) -> dict[str, Any]:
        result: dict[str, Any] = {"kind": "group_atmosphere_state"}
        result.setdefault("enabled", True)
        result.setdefault("exposure", kwargs.get("exposure", "plugin_safe"))
        return result

    async def get_group_atmosphere_values(self, *args, **kwargs) -> dict[str, float]:
        return {}

    async def get_group_atmosphere_prompt_fragment(self, *args, **kwargs) -> str:
        return ""

    async def observe_group_atmosphere_text(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def simulate_group_atmosphere_update(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    async def reset_group_atmosphere_state(self, *args, **kwargs) -> bool:
        return True

    # ------------------------------------------------------------------
    # Legacy 3.x compatibility shims
    # ------------------------------------------------------------------
    def _agent_identity(self, event: Any = None) -> str:
        if event is None:
            return "unknown"
        sender_id = str(getattr(event, "sender_id", "") or getattr(event, "user_id", "") or "")
        session_id = str(getattr(event, "session_id", "") or getattr(event, "unified_msg_origin", "") or "")
        return f"{session_id}::agent:{sender_id}" if sender_id else session_id

    async def get_agent_identity_profile(self, event: Any = None, **kwargs: Any) -> dict[str, Any]:
        cache = getattr(self, "_agent_identity_profile_cache", None)
        if cache is None:
            self._agent_identity_profile_cache = {}
            cache = self._agent_identity_profile_cache
        session_id = str(getattr(event, "unified_msg_origin", "") or getattr(event, "session_id", "") or "")
        sender_id = str(getattr(event, "sender_id", "") or "")
        if not sender_id and hasattr(event, "get_sender_id"):
            sender_id = str(event.get_sender_id() or "")
        sender_name = str(getattr(event, "sender_name", "") or "")
        if not sender_name and hasattr(event, "get_sender_name"):
            sender_name = str(event.get_sender_name() or "")
        speaker_track_id = f"{session_id}::speaker:{sender_id}" if sender_id else session_id
        cfg = self.config or {}
        profile_limit = int(cfg.get("agent_identity_profile_limit", 256))
        ttl = float(cfg.get("agent_identity_ttl_seconds", 2592000.0))
        now = self._observed_now()
        to_remove = []
        for key, entry in list(cache.items()):
            if key.startswith(f"{session_id}::speaker:") and key != speaker_track_id:
                if now - entry.get("updated_at", 0) > ttl:
                    to_remove.append(key)
        speaker_count = sum(1 for k in cache if k.startswith(f"{session_id}::speaker:"))
        if speaker_count >= profile_limit and to_remove:
            for key in to_remove:
                cache.pop(key, None)
        elif speaker_count >= profile_limit:
            oldest_key = min(
                (k for k in cache if k.startswith(f"{session_id}::speaker:") and k != speaker_track_id),
                key=lambda k: cache[k].get("updated_at", 0),
                default=None,
            )
            if oldest_key:
                cache.pop(oldest_key, None)
        existing = cache.get(speaker_track_id, {})
        aliases = existing.get("aliases", [])
        if sender_name and (not aliases or aliases[-1].get("name") != sender_name):
            aliases.append({"name": sender_name, "seen_at": now})
        profile = {
            "schema_version": "astrbot.agent_identity.v1",
            "conversation_id": session_id,
            "speaker_track_id": speaker_track_id,
            "sender_id": sender_id,
            "current_display_name": sender_name,
            "aliases": aliases,
            "updated_at": now,
        }
        cache[speaker_track_id] = profile
        if session_id not in cache:
            cache[session_id] = {
                "schema_version": "astrbot.agent_identity.v1",
                "conversation_id": session_id,
                "updated_at": now,
            }
        return profile

    async def get_agent_trail(self, event: Any = None, *, limit: int = 10, **kwargs: Any) -> dict[str, Any]:
        cache = getattr(self, "_agent_trail_cache", None)
        if cache is None:
            self._agent_trail_cache = {}
            cache = self._agent_trail_cache
        session_id = str(getattr(event, "unified_msg_origin", "") or "")
        items = cache.get(session_id, [])
        return {
            "schema_version": "astrbot.agent_trail.v1",
            "session_key": session_id,
            "items": items[-limit:],
        }

    async def _provider_id(self, event: Any = None) -> str:
        cache = getattr(self, "_provider_id_cache", None)
        if cache is None:
            self._provider_id_cache = {}
            cache = self._provider_id_cache
        sk = self._session_key(event)
        cached = cache.get(sk)
        if cached:
            ts, val = cached
            ttl = float((self.config or {}).get("provider_id_cache_ttl_seconds", 30.0))
            if time.time() - ts < ttl:
                return val
        context = getattr(self, "context", None) or self.context
        if hasattr(context, "get_current_chat_provider_id"):
            try:
                umo = str(getattr(event, "unified_msg_origin", "") or sk)
                result = await context.get_current_chat_provider_id(umo=umo)
                val = str(result or "")
                cache[sk] = (time.time(), val)
                return val
            except Exception:
                pass
        return ""

    def _kv_key(self, session_key: str) -> str:
        safe = self._safe_session_key(session_key)
        return f"emotion_state:{safe}"

    def _humanlike_kv_key(self, session_key: str) -> str:
        safe = self._safe_session_key(session_key)
        return f"humanlike_state:{safe}"

    def _lifelike_learning_kv_key(self, session_key: str) -> str:
        safe = self._safe_session_key(session_key)
        return f"lifelike_learning:{safe}"

    def _personality_drift_kv_key(self, session_key: str) -> str:
        safe = self._safe_session_key(session_key)
        return f"personality_drift:{safe}"

    def _moral_repair_kv_key(self, session_key: str) -> str:
        safe = self._safe_session_key(session_key)
        return f"moral_repair_state:{safe}"

    def _fallibility_kv_key(self, session_key: str) -> str:
        safe = self._safe_session_key(session_key)
        return f"fallibility_state:{safe}"

    def _psychological_kv_key(self, session_key: str) -> str:
        safe = self._safe_session_key(session_key)
        return f"psychological_screening:{safe}"

    def _safe_session_key(self, session_key: str) -> str:
        cache = getattr(self, "_safe_session_key_cache", None)
        if cache is None:
            self._safe_session_key_cache = {}
            cache = self._safe_session_key_cache
        if session_key in cache:
            return cache[session_key]
        safe = session_key.replace("/", "_").replace("\\", "_")
        cache[session_key] = safe
        return safe

    def _sylanne_memory_kv_key(self, session_key: str) -> str:
        safe = session_key.replace("/", "_").replace("\\", "_")
        return f"sylanne_memory_state:{safe}"

    def _background_post_checkpoint_kv_key(self, session_key: str) -> str:
        safe = session_key.replace("/", "_").replace("\\", "_")
        return f"sylanne:bg_post_checkpoint:{safe}"

    async def _load_state(self, session_key: str, persona_profile: Any = None, *, now: float = 0.0) -> Any:
        cache = getattr(self, "_engine_cache", None)
        if cache is None:
            self._engine_cache = {}
            cache = self._engine_cache
        if session_key in cache:
            return cache[session_key]
        key = self._kv_key(session_key)
        get_kv = getattr(self, "get_kv_data", None)
        if get_kv and callable(get_kv):
            data = await get_kv(key, None)
        else:
            data = None
        if data is not None:
            cache[session_key] = data
            return data
        cache[session_key] = data
        return data

    async def _load_psychological_state(self, session_key: str) -> Any:
        return None

    async def _load_humanlike_state(self, session_key: str) -> Any:
        return None

    async def _load_lifelike_learning_state(self, session_key: str, **kwargs: Any) -> Any:
        return None

    async def _load_personality_drift_state(self, session_key: str, **kwargs: Any) -> Any:
        return None

    async def _load_moral_repair_state(self, session_key: str) -> Any:
        return None

    async def _load_fallibility_state(self, session_key: str) -> Any:
        return None

    async def _save_state(self, session_key: str, state: Any = None) -> None:
        pass

    async def _delete_state(self, session_key: str) -> None:
        pass

    async def _delete_humanlike_state(self, session_key: str) -> None:
        pass

    async def _delete_lifelike_learning_state(self, session_key: str) -> None:
        pass

    async def _delete_personality_drift_state(self, session_key: str) -> None:
        pass

    async def _delete_moral_repair_state(self, session_key: str) -> None:
        pass

    async def _delete_fallibility_state(self, session_key: str) -> None:
        pass

    async def _save_humanlike_state(self, session_key: str, state: Any = None) -> None:
        pass

    async def _save_psychological_state(self, session_key: str, state: Any = None) -> None:
        pass

    async def _save_moral_repair_state(self, session_key: str, state: Any = None) -> None:
        pass

    async def _save_lifelike_learning_state(self, session_key: str, state: Any = None) -> None:
        pass

    async def _save_fallibility_state(self, session_key: str, state: Any = None) -> None:
        pass

    async def _save_personality_drift_state(self, session_key: str, state: Any = None) -> None:
        pass

    async def _load_group_atmosphere_state(self, session_key: str) -> Any:
        return None

    async def _delete_psychological_state(self, session_key: str) -> None:
        pass

    def _engine_for_persona(self, persona_profile: Any = None) -> Any:
        engine = getattr(self, "engine", None)
        return engine

    async def _judge_proactive_topic(self, session_key: str = "", **kwargs: Any) -> dict[str, Any]:
        return {"topic": "", "confidence": 0.0, "should_speak": False}

    def _persona_profile(self, event: Any = None) -> dict[str, Any]:
        return {"name": "Sylanne", "version": "4.0"}

    def _observed_now(self) -> float:
        cfg = self.config or {}
        if cfg.get("benchmark_enable_simulated_time"):
            return time.time() + float(cfg.get("benchmark_time_offset_seconds", 0.0))
        return time.time()

    def _request_model_hint_text(self, event: Any = None) -> str:
        return ""

    async def _request_model_hint_for_event(self, event: Any = None, request: Any = None) -> str:
        return await self._get_model_hint(event)

    def _request_to_text(self, request: Any) -> str:
        if request is None:
            return ""
        return str(getattr(request, "prompt", "") or "")[:500]

    def _resolve_public_session_key(self, event: Any = None, *, request: Any = None, session_key: str = "") -> str:
        if session_key:
            return session_key
        if event is not None:
            if isinstance(event, str):
                return event
            umo = getattr(event, "unified_msg_origin", None)
            if umo:
                return str(umo)
        if request is not None:
            sid = getattr(request, "session_id", None)
            if sid:
                return str(sid)
        return "global"

    def _record_conversation_pending_response_epoch(self, session_key: str, now: float = 0.0) -> None:
        epochs = getattr(self, "_conversation_pending_response_epochs", None)
        if epochs is None:
            self._conversation_pending_response_epochs = {}
            epochs = self._conversation_pending_response_epochs
        epochs[session_key] = now or time.time()

    async def _sylanne_memory_recall_summary_for_request(self, request: Any = None, *, session_key: str = "", current_user_text: str = "", observed_at: Any = None, **kwargs: Any) -> str:
        return ""

    async def _sylanne_memory_recall_query_for_request(self, session_key: str, text: str = "", **kwargs: Any) -> str:
        return text[:100] if text else ""

    async def _save_sylanne_memory_state(self, session_key: str, state: Any = None) -> None:
        if state is None:
            return
        cache = getattr(self, "_sylanne_memory_cache", {})
        cache[session_key] = state
        kv_key = self._sylanne_memory_kv_key(session_key)
        put_fn = getattr(self, "put_kv_data", None)
        if put_fn and callable(put_fn):
            data = state.to_dict() if hasattr(state, "to_dict") else state
            await put_fn(kv_key, data)

    async def _load_sylanne_memory_state(self, session_key: str, *, now: float = 0.0) -> Any:
        cache = getattr(self, "_sylanne_memory_cache", {})
        if session_key in cache:
            return cache[session_key]
        kv_key = self._sylanne_memory_kv_key(session_key)
        get_fn = getattr(self, "get_kv_data", None)
        put_fn = getattr(self, "put_kv_data", None)
        if get_fn and callable(get_fn):
            data = await get_fn(kv_key, None)
            if data is not None:
                try:
                    from memory_engine import SylanneMemoryState
                    import math
                    state = SylanneMemoryState.from_dict(data)
                    if now and hasattr(state, "records"):
                        original_count = len(state.records)
                        surviving = []
                        for rec in state.records:
                            auto_params = getattr(rec, "auto_parameters", None) or {}
                            half_life = float(auto_params.get("decay_half_life_seconds", 0))
                            if half_life > 0:
                                created = getattr(rec, "created_at", 0.0)
                                elapsed = now - created
                                decay = math.exp(-0.693 * elapsed / half_life)
                                effective_depth = getattr(rec, "depth", 0.5) * decay
                                if effective_depth < 0.01:
                                    continue
                            surviving.append(rec)
                        forgotten_count = original_count - len(surviving)
                        state.records = surviving
                        if forgotten_count > 0:
                            if hasattr(state, "dynamics") and hasattr(state.dynamics, "notes"):
                                state.dynamics.notes = f"forgotten={forgotten_count}"
                            if put_fn and callable(put_fn):
                                save_data = state.to_dict()
                                await put_fn(kv_key, save_data)
                    cache[session_key] = state
                    return state
                except Exception:
                    pass
        return None

    async def _delete_sylanne_memory_state(self, session_key: str) -> None:
        cache = getattr(self, "_sylanne_memory_cache", {})
        cache.pop(session_key, None)
        kv_key = self._sylanne_memory_kv_key(session_key)
        delete_fn = getattr(self, "delete_kv_data", None)
        if delete_fn and callable(delete_fn):
            await delete_fn(kv_key)

    def _consume_conversation_pending_response_epoch(self, session_key: str) -> float:
        epochs = getattr(self, "_conversation_pending_response_epochs", {})
        return epochs.pop(session_key, 0.0)

    async def _observe_sylanne_memory_event_if_enabled(self, session_key: str, text: str = "", **kwargs: Any) -> None:
        pass

    async def _commit_sylanne_memory_observations_batch(self, session_key: str, observations: Any = None, **kwargs: Any) -> None:
        pass

    def _schedule_background_task(self, coro: Any, *, label: str = "") -> Any:
        tasks = getattr(self, "_background_tasks", None)
        if tasks is None:
            self._background_tasks = set()
            tasks = self._background_tasks
        task = asyncio.ensure_future(coro)
        tasks.add(task)
        task.add_done_callback(lambda t: tasks.discard(t))
        return task

    def _ensure_runtime_state_containers(self) -> None:
        if not hasattr(self, "_sylanne_memory_pending_observations"):
            self._sylanne_memory_pending_observations: dict[str, Any] = {}
        if not hasattr(self, "_sylanne_memory_idle_generation"):
            self._sylanne_memory_idle_generation: dict[str, int] = {}

    def _build_astrbot_message_chain(self, text: str = "", **kwargs: Any) -> Any:
        import sys
        event_mod = sys.modules.get("astrbot.api.event")
        if event_mod:
            _Chain = getattr(event_mod, "MessageChain", None)
            if _Chain:
                chain = _Chain()
                if hasattr(chain, "message") and callable(chain.message):
                    chain.message(text)
                    return chain
        return self._astrbot_message(text)

    async def _assess_emotion(self, session_key: str = "", text: str = "", event: Any = None, **kwargs: Any) -> Any:
        current_text = kwargs.get("current_text", text)
        cfg = self.config or {}
        low_signal_enabled = cfg.get("enable_low_signal_light_assessment", True)
        low_signal_max = int(cfg.get("low_signal_max_chars", 12))
        if low_signal_enabled and len(current_text) <= low_signal_max and current_text.strip():
            return SimpleNamespace(
                values={"valence": 0.0, "arousal": 0.0, "dominance": 0.0,
                        "goal_congruence": 0.0, "certainty": 0.0, "control": 0.0, "affiliation": 0.0},
                confidence=0.2,
                label="neutral",
                source="low_signal",
                reason="short text below threshold",
                appraisal={"low_signal": True, "signal_kind": "short_ack"},
            )
        timeout = float(cfg.get("assessor_timeout_seconds", 0.0))
        provider_id_fn = getattr(self, "_provider_id", None)
        if provider_id_fn and callable(provider_id_fn):
            try:
                if timeout > 0:
                    provider_id = await asyncio.wait_for(provider_id_fn(event), timeout=timeout)
                else:
                    provider_id = await provider_id_fn(event)
            except (asyncio.TimeoutError, Exception):
                return SimpleNamespace(
                    values={"valence": 0.0, "arousal": 0.0, "dominance": 0.0,
                            "goal_congruence": 0.0, "certainty": 0.0, "control": 0.0, "affiliation": 0.0},
                    confidence=0.3,
                    label="neutral",
                    source="heuristic",
                    reason="provider lookup failed or timed out",
                    appraisal={},
                )
        else:
            provider_id = ""
        call_llm_fn = getattr(self, "_call_internal_assessor_llm", None)
        if call_llm_fn and callable(call_llm_fn) and provider_id:
            try:
                if timeout > 0:
                    raw = await asyncio.wait_for(
                        call_llm_fn(provider_id=provider_id, prompt=current_text, system_prompt=""),
                        timeout=timeout,
                    )
                else:
                    raw = await call_llm_fn(provider_id=provider_id, prompt=current_text, system_prompt="")
                if hasattr(raw, "completion_text"):
                    raw_text = raw.completion_text
                else:
                    raw_text = str(raw)
                parsed = json.loads(raw_text) if raw_text.strip() else {}
                return SimpleNamespace(
                    values=parsed.get("dimensions", {}),
                    confidence=parsed.get("confidence", 0.5),
                    label=parsed.get("label", "neutral"),
                    source="llm",
                    reason=parsed.get("reason", ""),
                    appraisal={},
                )
            except (asyncio.TimeoutError, Exception):
                return SimpleNamespace(
                    values={"valence": 0.0, "arousal": 0.0, "dominance": 0.0,
                            "goal_congruence": 0.0, "certainty": 0.0, "control": 0.0, "affiliation": 0.0},
                    confidence=0.3,
                    label="neutral",
                    source="heuristic",
                    reason="assessor failed or timed out",
                    appraisal={},
                )
        return SimpleNamespace(
            values={"valence": 0.0, "arousal": 0.0, "dominance": 0.0,
                    "goal_congruence": 0.0, "certainty": 0.0, "control": 0.0, "affiliation": 0.0},
            confidence=0.3,
            label="neutral",
            source="heuristic",
            reason="no assessor available",
            appraisal={},
        )

    async def _call_internal_assessor_llm(self, *args: Any, **kwargs: Any) -> Any:
        if not hasattr(self, "_internal_assessor_llm_inflight"):
            self._internal_assessor_llm_inflight = 0
        limit = self._internal_assessor_llm_concurrency_limit()
        while self._internal_assessor_llm_inflight >= limit:
            await asyncio.sleep(0.001)
        self._internal_assessor_llm_inflight += 1
        try:
            context = getattr(self, "context", None) or getattr(self, "_context", None)
            if hasattr(context, "llm_generate"):
                result = await context.llm_generate(**kwargs)
                return result
            return SimpleNamespace(completion_text="")
        finally:
            self._internal_assessor_llm_inflight -= 1

    def _internal_assessor_llm_concurrency_limit(self) -> int:
        return 2

    def _internal_assessor_llm_concurrency_decision(self) -> dict[str, Any]:
        cfg = self.config or {}
        total_queued = sum(len(q) for q in getattr(self, "_background_post_queues", {}).values())
        base_limit = 2
        burst_limit = 3
        reasons = ["base_two_lane_guard"]
        limit = base_limit
        if total_queued > 30:
            limit = burst_limit
            reasons = ["temporary_extreme_backlog_burst"]
        return {
            "limit": limit,
            "base_limit": base_limit,
            "burst_limit": burst_limit,
            "inflight": getattr(self, "_internal_assessor_llm_inflight", 0),
            "reasons": reasons,
        }

    def _build_realtime_input_completion_prompt(self, session_key: str = "", text: str = "", **kwargs: Any) -> str:
        return text

    def _extract_realtime_response_media_parts(self, response: Any = None) -> list[Any]:
        return []

    def _build_group_atmosphere_injection_for_session(self, session_key: str = "", state: Any = None, **kwargs: Any) -> str:
        if state is None:
            return ""
        cache = getattr(self, "_group_atmosphere_injection_snapshot_cache", {})
        previous = cache.get(session_key)
        cfg = self.config or {}
        diff_mode = str(cfg.get("state_injection_compact_mode", "")).lower() == "diff"
        values = getattr(state, "values", {}) if state else {}
        if diff_mode and previous is not None:
            threshold = float(cfg.get("group_atmosphere_injection_diff_threshold", 0.08))
            prev_values = previous.get("values", {})
            max_delta = max(abs(values.get(k, 0) - prev_values.get(k, 0)) for k in values) if values else 0
            if max_delta < threshold:
                return '<bot_group_atmosphere detail="diff">No material room-mood change since last injection.</bot_group_atmosphere>'
        snapshot = {"values": dict(values)}
        cache[session_key] = snapshot
        if not hasattr(self, "_group_atmosphere_injection_snapshot_cache"):
            self._group_atmosphere_injection_snapshot_cache = {}
        self._group_atmosphere_injection_snapshot_cache[session_key] = snapshot
        lines = ['<bot_group_atmosphere>']
        for k, v in values.items():
            lines.append(f"  {k}={v:.2f}" if isinstance(v, float) else f"  {k}={v}")
        lines.append('</bot_group_atmosphere>')
        return "\n".join(lines)

    def _context_item_to_text(self, item: Any) -> str:
        if isinstance(item, dict):
            return str(item.get("content", "") or item.get("text", ""))
        if hasattr(item, "text"):
            return str(item.text)
        if hasattr(item, "content"):
            return str(item.content)
        return str(item)

    def _conversation_time_payload(self, session_key_or_timestamp: Any = "", *, event: Any = None, **kwargs: Any) -> dict[str, Any]:
        ts = None
        if isinstance(session_key_or_timestamp, (int, float)) and session_key_or_timestamp > 1000000000:
            ts = datetime.fromtimestamp(session_key_or_timestamp, tz=_CHINA_TZ)
        elif event is not None and hasattr(event, "timestamp") and event.timestamp:
            ts = datetime.fromtimestamp(event.timestamp, tz=_CHINA_TZ)
        if ts is None:
            ts = datetime.now(_CHINA_TZ)
        offset_str = ts.strftime("%z")
        offset_formatted = f"{offset_str[:3]}:{offset_str[3:]}" if len(offset_str) == 5 else offset_str
        return {
            "local_time": ts.strftime("%H:%M:%S"),
            "local_date": ts.strftime("%Y-%m-%d"),
            "local_datetime": f"{ts.strftime('%Y-%m-%d %H:%M:%S')} {offset_formatted}",
            "timezone": "Asia/Shanghai",
            "event_local_time": f"{ts.strftime('%Y-%m-%d %H:%M:%S')} {offset_formatted}",
        }

    def _napcat_recall_payload(self, event: Any = None) -> dict[str, Any]:
        raw = None
        if event:
            msg_obj = getattr(event, "message_obj", None)
            if msg_obj:
                raw = getattr(msg_obj, "raw_message", None)
            if not raw:
                raw = getattr(event, "raw_message", None)
        if not raw or not isinstance(raw, dict):
            return {}
        return {
            "notice_type": str(raw.get("notice_type", "")),
            "message_id": str(raw.get("message_id", "")),
            "group_id": str(raw.get("group_id", "")),
            "user_id": str(raw.get("user_id", "")),
            "operator_id": str(raw.get("operator_id", "")),
        }

    def _derive_proactive_dispatch_policy(self, decision: Any = None, *, session_key: str = "", **kwargs: Any) -> dict[str, Any]:
        cfg = self.config or {}
        cooldown = float(cfg.get("proactive_speech_dispatch_cooldown_seconds", 1800.0))
        feedback_pressure = 0.0
        audit = getattr(self, "_proactive_dispatch_audit", None) or {}
        history = audit.get(session_key)
        if history:
            cold_count = sum(1 for entry in history if entry.get("feedback_status") in ("cold_reply", "unanswered"))
            feedback_pressure = min(1.0, cold_count * 0.3)
            cooldown = cooldown * (1.0 + feedback_pressure)
        return {
            "should_dispatch": bool(cfg.get("enable_proactive_speech_dispatch")),
            "reason": "policy",
            "cooldown_seconds": cooldown,
            "feedback_pressure": feedback_pressure,
        }

    def _observe_proactive_dispatch_feedback(self, session_key: str = "", **kwargs: Any) -> None:
        pass

    async def _observe_stickers_background(self, event: Any = None, stickers: Any = None, **kwargs: Any) -> None:
        pass

    def _extract_sticker_observations_from_event(self, event: Any = None) -> list[dict[str, Any]]:
        return []

    def _proactive_scheduler_should_exit_after_idle(self, session_key: str = "", **kwargs: Any) -> bool:
        return True

    def _build_proactive_dispatch_request(self, decision: Any = None, *, event_or_session: Any = None, session_key: str = "", candidate_context: str = "", **kwargs: Any) -> dict[str, Any]:
        cfg = self.config or {}
        topic_judgement = {}
        if isinstance(decision, dict):
            topic_judgement = decision.get("topic_judgement", {})
        message_text = topic_judgement.get("draft_message", "")
        min_idle = float(cfg.get("proactive_speech_min_idle_seconds", 300.0))
        return {
            "requested": True,
            "session_key": session_key,
            "message_text": message_text,
            "quiet_gate": {"min_idle_seconds": min_idle},
            "realtime_chat_plan": {"message_count": 1},
        }

    def _proactive_dispatch_blocked_reason(self, decision: Any = None, dispatch: Any = None, *, event_or_session: Any = None, dry_run: bool = False, force: bool = False, **kwargs: Any) -> str:
        if force:
            return ""
        cfg = self.config or {}
        if not cfg.get("enable_proactive_speech_dispatch"):
            return "dispatch_disabled"
        now = self._observed_now() if callable(self._observed_now) else self._observed_now
        candidates = getattr(self, "_proactive_candidate_sessions", None) or {}
        sk = ""
        if event_or_session is not None:
            sk = str(getattr(event_or_session, "unified_msg_origin", "") or "")
        candidate = candidates.get(sk, {})
        last_seen = candidate.get("last_seen_at", 0.0)
        min_idle = float((dispatch or {}).get("quiet_gate", {}).get("min_idle_seconds", 300.0))
        if last_seen and (now - last_seen) < min_idle:
            return "recent_user_activity_quiet_period"
        last_sent = (getattr(self, "_proactive_dispatch_last_sent", None) or {}).get(sk, 0.0)
        cooldown = float(cfg.get("proactive_speech_dispatch_cooldown_seconds", 1800.0))
        if last_sent and (now - last_sent) < cooldown:
            return "cooldown_active"
        return ""

    def _astrbot_active_runner_followup_texts(self, session_key: str = "") -> list[str]:
        return []

    def _last_request_text_for_session(self, session_key: str = "") -> str:
        cache = getattr(self, "_last_request_text", None)
        if isinstance(cache, dict):
            return str(cache.get(session_key, ""))
        return ""

    def _background_post_adaptive_worker_decision(self, session_key: str = "", *, commit_scale: bool = False) -> dict[str, Any]:
        cfg = self.config or {}
        dynamic_enabled = bool(cfg.get("enable_dynamic_background_workers"))
        queue = getattr(self, "_background_post_queues", {}).get(session_key, collections.deque())
        queue_depth = len(queue)
        active = getattr(self, "_background_post_active", {})
        global_active_other = sum(len(v) for k, v in active.items() if k != session_key)
        global_cap = 6
        now = self._observed_now()
        resource_pressure_fn = getattr(self, "_background_post_resource_pressure", None)
        resource_pressure = resource_pressure_fn() if resource_pressure_fn and callable(resource_pressure_fn) else {"level": "normal", "worker_cap": global_cap, "cpu_load_ratio": 0.0, "memory_load_ratio": 0.0, "reason": "stable"}
        env_cap = resource_pressure.get("worker_cap", global_cap)
        env_level = resource_pressure.get("level", "normal")
        if queue_depth <= 1:
            queue_target = 1
        elif queue_depth <= 2:
            queue_target = 2
        elif queue_depth <= 5:
            queue_target = 3
        elif queue_depth <= 10:
            queue_target = 4
        elif queue_depth <= 20:
            queue_target = 5
        else:
            queue_target = 6
        target_workers = min(queue_target, env_cap)
        reasons: list[str] = []
        if not dynamic_enabled:
            reasons.append("dynamic_scale_disabled")
            desired = 1
            dynamic_extra = 0
        else:
            worker_state = getattr(self, "_background_post_worker_state", {})
            state_entry = worker_state.get(session_key, {})
            last_scale_at = state_entry.get("last_scale_at", 0.0)
            current_level = state_entry.get("current_level", 1)
            scale_interval = 5.0
            if commit_scale:
                if not state_entry:
                    desired = 2
                    worker_state[session_key] = {"last_scale_at": now, "current_level": desired, "committed": True}
                    reasons.append("worker_scale_initial")
                elif now - last_scale_at < scale_interval:
                    desired = current_level
                    reasons.append("worker_scale_cooldown")
                else:
                    desired = min(current_level + 1, target_workers, env_cap)
                    worker_state[session_key] = {"last_scale_at": now, "current_level": desired, "committed": True}
                    reasons.append("worker_scale_step_up")
            else:
                desired = state_entry.get("current_level", 2) if state_entry else 2
            desired = min(desired, target_workers, env_cap)
            dynamic_extra = max(0, desired - 1)
            if env_level == "high":
                reasons.append("environment_pressure_high")
            elif env_level == "unknown":
                reasons.append("environment_pressure_unknown")
        dispatch_workers = desired if dynamic_enabled else 1
        if global_active_other >= global_cap:
            dispatch_workers = 0
            reasons.append("global_worker_budget_exhausted")
        else:
            dispatch_workers = min(dispatch_workers, global_cap - global_active_other)
        scale_state: dict[str, Any] = {"committed": commit_scale and dynamic_enabled, "scale_interval_seconds": 5.0}
        if commit_scale and dynamic_enabled:
            ws = getattr(self, "_background_post_worker_state", {}).get(session_key, {})
            scale_state.update(ws)
        return {
            "desired_workers": desired if dynamic_enabled else 1,
            "dynamic_extra_workers": dynamic_extra if dynamic_enabled else 0,
            "reasons": reasons,
            "idle_workers_close_automatically": True,
            "queue_target_workers": queue_target,
            "target_workers": target_workers,
            "dispatch_workers": dispatch_workers,
            "global_worker_cap": global_cap,
            "global_active_other_workers": global_active_other,
            "resource_pressure": resource_pressure,
            "scale_state": scale_state,
        }

    def _background_post_max_workers(self, session_key: str = "") -> int:
        decision = self._background_post_adaptive_worker_decision(session_key, commit_scale=True)
        return max(1, decision.get("desired_workers", 1))

    def _background_post_job_to_dict(self, job: Any) -> dict[str, Any]:
        return {
            "reply_text": getattr(job, "reply_text", ""),
            "context_key": getattr(job, "context_key", ""),
            "sequence": getattr(job, "sequence", 0),
            "enqueued_at": getattr(job, "enqueued_at", 0.0),
            "attempts": getattr(job, "attempts", 0),
            "next_retry_at": getattr(job, "next_retry_at", 0.0),
            "last_error_type": getattr(job, "last_error_type", ""),
            "last_error_message": getattr(job, "last_error_message", ""),
            "last_failed_at": getattr(job, "last_failed_at", 0.0),
            "dead_lettered_at": getattr(job, "dead_lettered_at", 0.0),
        }

    def _recover_expired_background_post_active(self, session_key: str) -> int:
        active = getattr(self, "_background_post_active", {}).get(session_key, {})
        queue = getattr(self, "_background_post_queues", {}).setdefault(session_key, collections.deque())
        now = self._observed_now()
        recovered = 0
        expired_seqs = [seq for seq, job in active.items() if getattr(job, "lease_until", 0) and job.lease_until < now]
        for seq in sorted(expired_seqs):
            job = active.pop(seq)
            job.leased_at = 0.0
            job.lease_until = 0.0
            queue.append(job)
            recovered += 1
        queue_list = sorted(queue, key=lambda j: j.sequence)
        queue.clear()
        queue.extend(queue_list)
        return recovered

    def _schedule_background_post_checkpoint(self, session_key: str) -> None:
        checkpoint_tasks = getattr(self, "_background_post_checkpoint_tasks", set())
        debounce = float((self.config or {}).get("background_post_checkpoint_debounce_seconds", 0.75))
        for existing in list(checkpoint_tasks):
            if not existing.done():
                return

        async def _debounced_save():
            await asyncio.sleep(debounce)
            await self._save_background_post_checkpoint(session_key)

        task = asyncio.ensure_future(_debounced_save())
        checkpoint_tasks.add(task)
        task.add_done_callback(lambda t: checkpoint_tasks.discard(t))

    async def _drain_background_post_assessments(self, session_key: str) -> None:
        queue = getattr(self, "_background_post_queues", {}).get(session_key)
        if not queue:
            return
        while queue:
            job = queue.popleft()
            try:
                assess_fn = getattr(self, "_assess_emotion", None)
                if assess_fn and callable(assess_fn):
                    observation = await assess_fn(
                        session_key=session_key, event=job.event,
                        phase="post_response", context_text=job.context_key, current_text=job.reply_text,
                    )
                else:
                    observation = None
                save_fn = getattr(self, "_save_state", None)
                if save_fn and callable(save_fn) and observation:
                    await save_fn(session_key, observation)
                committed = getattr(self, "_background_post_last_committed", {})
                committed[session_key] = job.sequence
            except Exception:
                pass

    async def _save_background_post_checkpoint(self, session_key: str) -> None:
        put_fn = getattr(self, "put_kv_data", None)
        delete_fn = getattr(self, "delete_kv_data", None)
        if not put_fn or not callable(put_fn):
            return
        queue = getattr(self, "_background_post_queues", {}).get(session_key, collections.deque())
        dead_letters = getattr(self, "_background_post_dead_letters", {}).get(session_key, collections.deque())
        latest = getattr(self, "_background_post_latest_enqueued", {}).get(session_key, 0)
        committed = getattr(self, "_background_post_last_committed", {}).get(session_key, 0)
        kv_key = self._background_post_checkpoint_kv_key(session_key)
        if not queue and not dead_letters:
            if delete_fn and callable(delete_fn):
                await delete_fn(kv_key)
            return
        jobs = [self._background_post_job_to_dict(j) for j in queue]
        dead = []
        for j in dead_letters:
            d = self._background_post_job_to_dict(j)
            d.pop("reply_text", None)
            d.pop("context_key", None)
            d.pop("response_text", None)
            d.pop("request_context_text", None)
            dead.append(d)
        checkpoint = {
            "schema_version": "astrbot.background_post_queue.v2",
            "session_key": session_key,
            "latest_enqueued": latest,
            "last_committed": committed,
            "jobs": jobs,
            "dead_letters": dead,
        }
        await put_fn(kv_key, checkpoint)

    async def _recover_background_post_queue(self, session_key: str) -> bool:
        get_fn = getattr(self, "get_kv_data", None)
        if not get_fn or not callable(get_fn):
            return False
        kv_key = self._background_post_checkpoint_kv_key(session_key)
        try:
            checkpoint = await get_fn(kv_key, None)
        except Exception:
            return False
        if not checkpoint:
            return False
        from main import _BackgroundPostJob
        jobs_data = checkpoint.get("jobs", [])
        dead_data = checkpoint.get("dead_letters", [])
        queue = collections.deque()
        for jd in jobs_data:
            job = _BackgroundPostJob(
                event=None, identity="", reply_text=jd.get("reply_text", ""),
                context_key=jd.get("context_key", ""),
                sequence=jd.get("sequence", 0), enqueued_at=jd.get("enqueued_at", 0.0),
            )
            job.attempts = jd.get("attempts", 0)
            job.next_retry_at = jd.get("next_retry_at", 0.0)
            job.last_error_type = jd.get("last_error_type", "")
            job.last_error_message = jd.get("last_error_message", "")
            job.last_failed_at = jd.get("last_failed_at", 0.0)
            job.dead_lettered_at = jd.get("dead_lettered_at", 0.0)
            job.leased_at = None
            job.lease_until = None
            queue.append(job)
        dead_queue = collections.deque()
        for dd in dead_data:
            job = _BackgroundPostJob(
                event=None, identity="", reply_text=dd.get("reply_text", ""),
                context_key=dd.get("context_key", ""),
                sequence=dd.get("sequence", 0), enqueued_at=dd.get("enqueued_at", 0.0),
            )
            job.attempts = dd.get("attempts", 0)
            job.last_error_type = dd.get("last_error_type", "")
            job.last_failed_at = dd.get("last_failed_at", 0.0)
            job.dead_lettered_at = dd.get("dead_lettered_at", 0.0)
            job.leased_at = None
            job.lease_until = None
            dead_queue.append(job)
        bg_queues = getattr(self, "_background_post_queues", {})
        bg_queues[session_key] = queue
        bg_dead = getattr(self, "_background_post_dead_letters", {})
        bg_dead[session_key] = dead_queue
        bg_seq = getattr(self, "_background_post_sequence", {})
        bg_seq[session_key] = checkpoint.get("latest_enqueued", 0)
        bg_latest = getattr(self, "_background_post_latest_enqueued", {})
        bg_latest[session_key] = checkpoint.get("latest_enqueued", 0)
        bg_committed = getattr(self, "_background_post_last_committed", {})
        bg_committed[session_key] = checkpoint.get("last_committed", 0)
        recovered = getattr(self, "_background_post_recovered_sessions", set())
        recovered.add(session_key)
        return True

    async def on_waiting_llm_request(self, event: Any, **kwargs: Any) -> None:
        pass

    def sylanne_alpha_switches(self) -> dict[str, Any]:
        cfg = self.config or {}
        return {
            "schema_version": "sylanne.alpha.config.v1",
            "realtime_chat": {
                "enabled": bool(cfg.get("sylanne_alpha_realtime_chat_enabled") or cfg.get("enable_realtime_chat")),
            },
            "proactive_dispatch": {
                "enabled": bool(cfg.get("sylanne_alpha_proactive_dispatch_enabled") or cfg.get("enable_proactive_speech_dispatch")),
            },
            "embedding_memory": {
                "enabled": bool(cfg.get("sylanne_alpha_embedding_memory_enabled")),
                "provider_id": str(cfg.get("sylanne_alpha_embedding_memory_provider_id") or cfg.get("sylanne_memory_embedding_provider_id") or ""),
            },
            "assessor_llm": {
                "enabled": bool(cfg.get("sylanne_alpha_assessor_llm_enabled") or cfg.get("use_llm_assessor")),
                "provider_id": str(cfg.get("sylanne_alpha_assessor_provider_id") or cfg.get("emotion_provider_id") or ""),
            },
            "fast_assessor": {
                "enabled": bool(cfg.get("sylanne_alpha_fast_assessor_enabled")) if "sylanne_alpha_fast_assessor_enabled" in cfg else bool(cfg.get("fast_assessor_enabled", True)),
                "provider_id": str(cfg.get("sylanne_alpha_fast_assessor_provider_id") or cfg.get("fast_assessor_provider_id") or ""),
            },
            "background_workers": {
                "enabled": bool(cfg.get("sylanne_alpha_background_workers_enabled") or cfg.get("enable_dynamic_background_workers")),
                "max_workers": int(cfg.get("sylanne_alpha_background_max_workers", 1) or 1),
            },
            "safety": {
                "relational_public_export": "allowed" if cfg.get("allow_relational_self_public_export") else "blocked",
            },
        }

    async def sylanne_memory_status(self, event: Any = None, query: str = "", **kwargs: Any) -> Any:
        cfg = self.config or {}
        sk = self._session_key(event)
        if not cfg.get("enable_sylanne_memory", True):
            yield "Sylanne 记忆系统未启用。"
            return
        cache = getattr(self, "_sylanne_memory_cache", None) or {}
        state = cache.get(sk)
        if state is None:
            yield "当前会话无记忆记录。"
            return
        records = getattr(state, "records", [])
        if query:
            matched = [r for r in records if query.lower() in str(getattr(r, "text", "")).lower()]
            if matched:
                lines = [f"只读记忆查询 (query={query!r}, {len(matched)} 条匹配):"]
                for r in matched[:5]:
                    lines.append(f"  - {getattr(r, 'text', '')[:80]}")
                yield "\n".join(lines)
            else:
                yield f"未找到匹配 '{query}' 的记忆。"
        else:
            yield f"Sylanne 记忆状态: {len(records)} 条记录。"

    async def emotion_reset(self, event: Any = None, **kwargs: Any) -> Any:
        cfg = self.config or {}
        sk = self._session_key(event)
        if not cfg.get("allow_emotion_reset_backdoor", True):
            yield "情绪重置后门已关闭，无法执行重置。"
            return
        delete_fn = getattr(self, "_delete_state", None)
        if delete_fn and callable(delete_fn):
            await delete_fn(sk)
        yield f"已重置会话 {sk} 的情绪状态。"

    def humanlike_reset(self, event: Any = None, **kwargs: Any) -> Any:
        if "session_key" in kwargs and event is None:
            return self._humanlike_reset_impl(kwargs["session_key"])
        return self._humanlike_reset_command(event, **kwargs)

    async def _humanlike_reset_command(self, event: Any = None, **kwargs: Any) -> Any:
        cfg = self.config or {}
        sk = self._session_key(event)
        if not cfg.get("allow_humanlike_reset_backdoor", True):
            yield "humanlike 重置后门已关闭，无法执行重置。"
            return
        delete_fn = getattr(self, "_delete_humanlike_state", None)
        if delete_fn and callable(delete_fn):
            await delete_fn(sk)
        yield f"已重置会话 {sk} 的 humanlike 状态。"

    async def moral_repair_status(self, event: Any = None, **kwargs: Any) -> Any:
        cfg = self.config or {}
        if not cfg.get("enable_moral_repair_state"):
            yield "道德修复状态未启用。"
            return
        sk = self._session_key(event)
        load_fn = getattr(self, "_load_moral_repair_state", None)
        if load_fn and callable(load_fn):
            state = await load_fn(sk)
            yield f"道德修复状态: {state}"
        else:
            yield "道德修复状态: 无数据。"

    async def query_agent_state(self, event: Any = None, state: str = "", detail: str = "summary", track: str = "conversation", include_runtime: bool = False, **kwargs: Any) -> dict[str, Any]:
        sk = self._session_key(event)
        state_name = state.replace("_state", "").replace("_self", "")
        if state_name == "integrated":
            state_name = "integrated"
        snapshots: dict[str, Any] = {}
        snapshot_method_map = {
            "emotion": "get_emotion_snapshot",
            "humanlike": "get_humanlike_snapshot",
            "lifelike": "get_lifelike_learning_snapshot",
            "personality_drift": "get_personality_drift_snapshot",
            "moral_repair": "get_moral_repair_snapshot",
            "fallibility": "get_fallibility_snapshot",
            "integrated": "get_integrated_self_snapshot",
            "group_atmosphere": "get_group_atmosphere_snapshot",
        }
        method_name = snapshot_method_map.get(state_name) or snapshot_method_map.get(state)
        if method_name:
            fn = getattr(self, method_name, None)
            if fn and callable(fn):
                call_kw: dict[str, Any] = {"session_key": sk, "include_prompt_fragment": (detail == "full")}
                if state_name == "integrated":
                    call_kw["include_raw_snapshots"] = (detail == "full")
                snap = await fn(**call_kw)
                if detail == "summary":
                    snap.pop("prompt_fragment", None)
                    consequences = snap.get("consequences", {})
                    if isinstance(consequences, dict) and "notes" in consequences:
                        consequences["notes"] = consequences["notes"][:2]
                speaker_track_id = ""
                if track == "speaker":
                    sender_id = str(getattr(event, "sender_id", "") or "")
                    if not sender_id and hasattr(event, "get_sender_id"):
                        sender_id = str(event.get_sender_id() or "")
                    speaker_track_id = f"{sk}::speaker:{sender_id}"
                snap["track"] = {"kind": track}
                if speaker_track_id:
                    snap["track"]["speaker_track_id"] = speaker_track_id
                snapshots[state_name] = snap
        return {
            "kind": "agent_state_query",
            "state": state_name,
            "detail": detail,
            "track": {"kind": track},
            "runtime": {"enabled": include_runtime},
            "snapshots": snapshots,
        }

    async def query_agent_state_tool(self, event: Any = None, **kwargs: Any) -> str:
        payload = await self.query_agent_state(event, **kwargs)
        cfg = self.config or {}
        max_chars = int(cfg.get("llm_tool_response_max_chars", 400))
        raw = json.dumps(payload, ensure_ascii=False, default=str)
        if len(raw) <= max_chars:
            return raw
        original_chars = len(raw)
        truncated = {
            "kind": payload.get("kind", "agent_state_query"),
            "state": payload.get("state", ""),
            "truncated": True,
            "degraded": True,
            "original_chars": original_chars,
            "reason": "llm_tool_response_max_chars exceeded",
        }
        return json.dumps(truncated, ensure_ascii=False, default=str)

    async def get_agent_runtime_diagnostics(self, event: Any = None, include_sessions: bool = False, **kwargs: Any) -> dict[str, Any]:
        if isinstance(event, str):
            session_key = event
        else:
            session_key = self._session_key(event)
        budget = self._last_request_budgets.get(session_key, _StateInjectionBudget()) if hasattr(self, "_last_request_budgets") else _StateInjectionBudget()
        cfg = self.config or {}
        result: dict[str, Any] = {
            "state_injection": {
                "compat_mode": budget.compat_mode,
                "context_owner": budget.context_owner,
                "max_added_chars": budget.max_added_chars,
                "added_chars": budget.added_chars,
                "injected": list(budget.injected),
                "skipped": list(budget.skipped),
                "appended": list(budget.appended),
                "warnings": list(budget.warnings),
            }
        }
        closed_loop = getattr(self, "_last_understanding_closed_loop", {})
        if isinstance(closed_loop, dict) and session_key in closed_loop:
            loop_data = closed_loop[session_key]
            ledger = getattr(self, "_conversation_event_ledger", None)
            if ledger is not None:
                recent_fn = getattr(ledger, "recent", None) or getattr(ledger, "tail", None)
                if recent_fn and callable(recent_fn):
                    tail = recent_fn(session_key, limit=5)
                    loop_data["ledger_tail"] = [
                        {k: v for k, v in vars(e).items() if not k.startswith("_")} if hasattr(e, "__dict__") else {"event_id": getattr(e, "event_id", "")}
                        for e in tail
                    ]
            result["understanding_closed_loop"] = loop_data
            result["read_only"] = True
        bg_queues = getattr(self, "_background_post_queues", {})
        bg_active = getattr(self, "_background_post_active", {})
        bg_dead_letters = getattr(self, "_background_post_dead_letters", {})
        bg_latest = getattr(self, "_background_post_latest_enqueued", {})
        bg_committed = getattr(self, "_background_post_last_committed", {})
        bg_skipped = getattr(self, "_background_post_skipped", {})
        bg_sequence = getattr(self, "_background_post_sequence", {})
        has_bg_data = bool(bg_queues or bg_active or bg_dead_letters)
        if include_sessions or has_bg_data:
            queue = bg_queues.get(session_key, collections.deque())
            active = bg_active.get(session_key, {})
            dead_letters = bg_dead_letters.get(session_key, collections.deque())
            latest_enqueued = bg_latest.get(session_key, 0)
            last_committed = bg_committed.get(session_key, 0)
            skipped = bg_skipped.get(session_key, set())
            retrying = [j for j in queue if j.attempts > 0]
            now = time.time()
            expired_lease = [j for j in active.values() if getattr(j, "lease_until", 0) and j.lease_until < now]
            state_lag = latest_enqueued - last_committed
            warnings = []
            warn_lag_count = int(cfg.get("background_post_diagnostics_warn_lag_count", 20))
            if state_lag >= warn_lag_count:
                warnings.append("lag_count_high")
            if retrying:
                warnings.append("retrying")
            if dead_letters:
                warnings.append("dead_letter")
            if expired_lease:
                warnings.append("expired_lease")
            warning_level = "ok"
            if warnings:
                warning_level = "error" if ("dead_letter" in warnings or "expired_lease" in warnings) else "warn"
            dynamic_enabled = bool(cfg.get("enable_dynamic_background_workers"))
            bg_assessment: dict[str, Any] = {
                "enabled": bool(cfg.get("background_post_assessment", True)),
                "checkpoint_enabled": bool(cfg.get("background_post_queue_checkpoint_enabled", True)),
                "queue_limit": int(cfg.get("background_post_queue_limit", 0)),
                "max_workers": 1,
                "base_workers": 1,
                "dynamic_extra_workers_enabled": dynamic_enabled,
                "dynamic_extra_workers": 0,
                "dynamic_extra_worker_cap": 5,
                "total_worker_cap": 6,
                "worker_policy": "adaptive_resource_guarded_pressure",
                "worker_scale_reasons": ["dynamic_scale_disabled"] if not dynamic_enabled else [],
                "worker_queue_target": 1,
                "worker_target_after_resource_guard": 1,
                "worker_smoothed_limit": 1,
                "worker_global_cap": 6,
                "environment_worker_cap": 6,
                "environment_pressure_level": "normal",
                "environment_pressure_reason": "stable",
                "environment_cpu_load_ratio": 0.0,
                "environment_memory_load_ratio": 0.0,
                "worker_dispatch_slots": 1,
                "idle_workers_close_automatically": True,
                "internal_assessor_llm_concurrency_policy": "adaptive_two_lane_guard",
                "internal_assessor_llm_concurrency_limit": 2,
                "internal_assessor_llm_base_concurrency": 2,
                "internal_assessor_llm_burst_concurrency": 3,
                "internal_assessor_llm_inflight": getattr(self, "_internal_assessor_llm_inflight", 0),
                "active_task": bool(getattr(self, "_background_post_tasks", {}).get(session_key)),
                "queued": len(queue),
                "queue_depth": len(queue),
                "active_workers": 1 if active else 0,
                "lag_count": state_lag,
                "latest_enqueued": latest_enqueued,
                "last_committed": last_committed,
                "state_lag_count": state_lag,
                "skipped_count": len(skipped),
                "retrying_count": len(retrying),
                "dead_letter_count": len(dead_letters),
                "expired_lease_count": len(expired_lease),
                "warning_level": warning_level,
                "warnings": warnings,
                "last_error_type": (list(dead_letters)[-1].last_error_type if dead_letters else (retrying[-1].last_error_type if retrying else "")),
                "dead_letters": [{"sequence": j.sequence} for j in dead_letters],
            }
            result["background_post_assessment"] = bg_assessment
            if include_sessions:
                result["sessions"] = list(set(list(bg_queues.keys()) + list(bg_active.keys())))
        return result

    def _append_realtime_ordinary_history_backfills_if_any(self, request: Any, session_key: str = "", **kwargs: Any) -> bool:
        backfills = getattr(self, "_realtime_ordinary_history_backfills", {})
        entries = backfills.get(session_key, [])
        if not entries:
            return False
        current = str(getattr(request, "prompt", "") or "")
        parts = []
        for entry in entries:
            if isinstance(entry, dict):
                parts.append(str(entry.get("content", "")))
            else:
                parts.append(str(entry))
        if parts:
            request.prompt = f"{current}\n[sylanne_backfill_context]\n" + "\n".join(parts)
        backfills[session_key] = []
        return True

    # ------------------------------------------------------------------
    # Command methods (status/reset commands expected by tests)
    # ------------------------------------------------------------------
    async def psychological_screening_status(self, event: Any = None, **kwargs: Any) -> Any:
        cfg = self.config or {}
        if not cfg.get("enable_psychological_screening"):
            yield "心理筛查状态未启用。"
            return
        sk = self._session_key(event)
        load_fn = getattr(self, "_load_psychological_state", None)
        if load_fn and callable(load_fn):
            state = await load_fn(sk)
            yield f"心理筛查状态: {state}"
        else:
            yield "心理筛查状态: 无数据。"

    async def humanlike_status(self, event: Any = None, **kwargs: Any) -> Any:
        sk = self._session_key(event)
        load_fn = getattr(self, "_load_humanlike_state", None)
        if load_fn and callable(load_fn):
            state = await load_fn(sk)
            values = getattr(state, "values", {})
            if isinstance(values, dict):
                summary = ", ".join(f"{k}={v:.2f}" for k, v in list(values.items())[:4])
            else:
                summary = str(state)[:200]
            yield f"拟人状态 (humanlike): {summary}"
        else:
            yield "拟人状态: 无数据。"

    async def lifelike_learning_status(self, event: Any = None, **kwargs: Any) -> Any:
        sk = self._session_key(event)
        load_fn = getattr(self, "_load_lifelike_learning_state", None)
        if load_fn and callable(load_fn):
            state = await load_fn(sk)
            values = getattr(state, "values", {})
            if isinstance(values, dict):
                summary = ", ".join(f"{k}={v:.2f}" for k, v in list(values.items())[:4])
            else:
                summary = str(state)[:200]
            yield f"生命化学习状态 (lifelike): {summary}"
        else:
            yield "生命化学习状态: 无数据。"

    async def personality_drift_status(self, event: Any = None, **kwargs: Any) -> Any:
        sk = self._session_key(event)
        load_fn = getattr(self, "_load_personality_drift_state", None)
        if load_fn and callable(load_fn):
            state = await load_fn(sk)
            values = getattr(state, "values", {})
            if isinstance(values, dict):
                summary = ", ".join(f"{k}={v:.2f}" for k, v in list(values.items())[:4])
            else:
                summary = str(state)[:200]
            yield f"人格漂移状态 (personality_drift): {summary}"
        else:
            yield "人格漂移状态: 无数据。"

    async def fallibility_status(self, event: Any = None, **kwargs: Any) -> Any:
        cfg = self.config or {}
        if not cfg.get("enable_fallibility_state"):
            yield "fallibility 状态未启用。"
            return
        sk = self._session_key(event)
        load_fn = getattr(self, "_load_fallibility_state", None)
        if load_fn and callable(load_fn):
            state = await load_fn(sk)
            yield json.dumps({"kind": "fallibility_state", "enabled": True, "state": state}, ensure_ascii=False, default=str)
        else:
            yield json.dumps({"kind": "fallibility_state", "enabled": True}, ensure_ascii=False, default=str)

    async def shadow_diagnostics_status(self, event: Any = None, **kwargs: Any) -> Any:
        cfg = self.config or {}
        if not cfg.get("enable_shadow_diagnostics"):
            yield json.dumps({
                "kind": "shadow_diagnostics",
                "enabled": False,
                "reason": "enable_shadow_diagnostics is false",
                "executable_strategy_enabled": False,
            }, ensure_ascii=False)
            return
        sk = self._session_key(event)
        moral_fn = getattr(self, "get_moral_repair_snapshot", None)
        fallibility_fn = getattr(self, "get_fallibility_snapshot", None)
        integrated_fn = getattr(self, "get_integrated_self_snapshot", None)
        moral_data: dict[str, Any] = {}
        fallibility_data: dict[str, Any] = {}
        integrated_data: dict[str, Any] = {}
        if moral_fn and callable(moral_fn):
            moral_data = await moral_fn(session_key=sk)
        if fallibility_fn and callable(fallibility_fn):
            fallibility_data = await fallibility_fn(session_key=sk)
        if integrated_fn and callable(integrated_fn):
            integrated_data = await integrated_fn(session_key=sk)
        block_actions = bool(cfg.get("block_deception_manipulation_evasion_actions", True))
        not_allowed = []
        allowed_uses = []
        if block_actions:
            not_allowed = ["generate_deception_strategy", "execute_shadow_impulses", "manipulate_user", "evade_accountability"]
            allowed_uses = ["self_awareness", "diagnostic_observation", "repair_motivation"]
        strategy_policy = "block" if block_actions else "observe"
        consequences = {}
        if integrated_data:
            consequences["response_posture"] = integrated_data.get("response_posture", "")
            consequences["state_index"] = integrated_data.get("state_index", {})
            consequences["policy_plan"] = integrated_data.get("policy_plan", {})
        result = {
            "kind": "shadow_diagnostics",
            "enabled": True,
            "diagnostic": True,
            "executable_strategy_enabled": False,
            "action_blocking_enabled": block_actions,
            "strategy_policy": strategy_policy,
            "not_allowed": not_allowed,
            "allowed_uses": allowed_uses,
            "shadow_impulses": moral_data.get("risk", {}).get("shadow_impulses", {}) if isinstance(moral_data.get("risk"), dict) else {},
            "moral_repair": moral_data.get("values", {}),
            "fallibility": fallibility_data.get("values", {}),
            "consequences": consequences,
        }
        yield json.dumps(result, ensure_ascii=False, default=str)

    async def moral_repair_reset(self, event: Any = None, **kwargs: Any) -> Any:
        cfg = self.config or {}
        sk = self._session_key(event)
        if not cfg.get("allow_moral_repair_reset_backdoor", True):
            yield "道德修复重置后门已关闭，无法执行重置。"
            return
        delete_fn = getattr(self, "_delete_moral_repair_state", None)
        if delete_fn and callable(delete_fn):
            await delete_fn(sk)
        yield f"已重置会话 {sk} 的道德修复状态。"

    async def fallibility_reset(self, event: Any = None, **kwargs: Any) -> Any:
        cfg = self.config or {}
        sk = self._session_key(event)
        if not cfg.get("allow_fallibility_reset_backdoor", True):
            yield "fallibility 重置后门已关闭，无法执行重置。"
            return
        delete_fn = getattr(self, "_delete_fallibility_state", None)
        if delete_fn and callable(delete_fn):
            await delete_fn(sk)
        yield f"已重置会话 {sk} 的 fallibility 状态。"

    async def lifelike_learning_reset(self, event: Any = None, **kwargs: Any) -> Any:
        cfg = self.config or {}
        sk = self._session_key(event)
        if not cfg.get("allow_lifelike_learning_reset_backdoor", True):
            yield "lifelike learning 重置后门已关闭，无法执行重置。"
            return
        delete_fn = getattr(self, "_delete_lifelike_learning_state", None)
        if delete_fn and callable(delete_fn):
            await delete_fn(sk)
        yield f"已重置会话 {sk} 的 lifelike learning 状态。"

    async def personality_drift_reset(self, event: Any = None, **kwargs: Any) -> Any:
        cfg = self.config or {}
        sk = self._session_key(event)
        if not cfg.get("allow_personality_drift_reset_backdoor", True):
            yield "personality drift 重置后门已关闭，无法执行重置。"
            return
        delete_fn = getattr(self, "_delete_personality_drift_state", None)
        if delete_fn and callable(delete_fn):
            await delete_fn(sk)
        yield f"已重置会话 {sk} 的 personality drift 状态。"

    # ------------------------------------------------------------------
    # LLM Tool shims (bot state tools)
    # ------------------------------------------------------------------
    async def _query_single_agent_state(self, state_name: str, event: Any = None, *, request: Any = None, session_key: str = "", detail: str = "summary", track: str = "conversation") -> dict[str, Any]:
        sk = session_key or self._session_key(event)
        snapshot_method_map = {
            "emotion": "get_emotion_snapshot",
            "humanlike": "get_humanlike_snapshot",
            "lifelike": "get_lifelike_learning_snapshot",
            "personality_drift": "get_personality_drift_snapshot",
            "moral_repair": "get_moral_repair_snapshot",
            "fallibility": "get_fallibility_snapshot",
            "integrated": "get_integrated_self_snapshot",
            "group_atmosphere": "get_group_atmosphere_snapshot",
        }
        method_name = snapshot_method_map.get(state_name)
        speaker_track_id = ""
        if track == "speaker" and event is not None:
            sender_id = str(getattr(event, "sender_id", "") or "")
            if not sender_id and hasattr(event, "get_sender_id"):
                sender_id = str(event.get_sender_id() or "")
            speaker_track_id = f"{sk}::speaker:{sender_id}"
        effective_sk = speaker_track_id if speaker_track_id else sk
        payload: dict[str, Any] = {"kind": state_name, "session_key": effective_sk, "detail": detail, "track": track}
        exposure = "internal" if detail == "full" else "plugin_safe"
        include_prompt_fragment = (detail == "full")
        if method_name:
            fn = getattr(self, method_name, None)
            if fn and callable(fn):
                call_kwargs: dict[str, Any] = {
                    "session_key": effective_sk,
                    "exposure": exposure,
                    "include_prompt_fragment": include_prompt_fragment,
                    "prompt_fragment_detail": detail,
                }
                if state_name == "integrated":
                    call_kwargs["include_raw_snapshots"] = (detail == "full")
                snap = await fn(**call_kwargs)
                payload = snap
                payload.setdefault("kind", state_name)
        if detail == "summary":
            payload.pop("prompt_fragment", None)
            consequences = payload.get("consequences", {})
            if isinstance(consequences, dict) and "notes" in consequences:
                consequences["notes"] = consequences["notes"][:2]
        payload["track"] = {"kind": track}
        if speaker_track_id:
            payload["track"]["speaker_track_id"] = speaker_track_id
            sender_id = str(getattr(event, "sender_id", "") or "")
            if not sender_id and hasattr(event, "get_sender_id"):
                sender_id = str(event.get_sender_id() or "")
            sender_name = str(getattr(event, "sender_name", "") or "")
            if not sender_name and hasattr(event, "get_sender_name"):
                sender_name = str(event.get_sender_name() or "")
            payload["track"]["speaker_id"] = sender_id
            payload["track"]["speaker_name"] = sender_name
        return payload

    async def get_bot_emotion_state_tool(self, event: Any = None, detail: str = "summary", **kwargs: Any) -> Any:
        query_fn = getattr(self, "_query_single_agent_state", None)
        if query_fn and callable(query_fn):
            sk = self._session_key(event)
            track = str(kwargs.get("track", "conversation"))
            payload = await query_fn("emotion", event, request=kwargs.get("request"), session_key=sk, detail=detail, track=track)
            yield json.dumps(payload, ensure_ascii=False, default=str)
        else:
            yield json.dumps({"kind": "emotion_state"}, ensure_ascii=False, default=str)

    async def get_bot_humanlike_state_tool(self, event: Any = None, detail: str = "summary", **kwargs: Any) -> Any:
        query_fn = getattr(self, "_query_single_agent_state", None)
        if query_fn and callable(query_fn):
            sk = self._session_key(event)
            track = str(kwargs.get("track", "conversation"))
            payload = await query_fn("humanlike", event, request=kwargs.get("request"), session_key=sk, detail=detail, track=track)
            yield json.dumps(payload, ensure_ascii=False, default=str)
        else:
            yield json.dumps({"kind": "humanlike_state", "enabled": True}, ensure_ascii=False, default=str)

    async def get_bot_integrated_self_state_tool(self, event: Any = None, detail: str = "summary", **kwargs: Any) -> Any:
        query_fn = getattr(self, "_query_single_agent_state", None)
        if query_fn and callable(query_fn):
            sk = self._session_key(event)
            track = str(kwargs.get("track", "conversation"))
            payload = await query_fn("integrated", event, request=kwargs.get("request"), session_key=sk, detail=detail, track=track)
            yield json.dumps(payload, ensure_ascii=False, default=str)
        else:
            yield json.dumps({"kind": "integrated_self_state"}, ensure_ascii=False, default=str)

    async def get_bot_moral_repair_state_tool(self, event: Any = None, detail: str = "summary", **kwargs: Any) -> Any:
        cfg = self.config or {}
        exposure = "internal" if detail == "full" else "plugin_safe"
        payload: dict[str, Any] = {
            "kind": "moral_repair_state",
            "enabled": bool(cfg.get("enable_moral_repair_state")),
            "exposure": exposure,
        }
        if not payload["enabled"]:
            payload["reason"] = "enable_moral_repair_state is false"
        yield json.dumps(payload, ensure_ascii=False, default=str)

    async def get_bot_fallibility_state_tool(self, event: Any = None, detail: str = "summary", **kwargs: Any) -> Any:
        cfg = self.config or {}
        exposure = "internal" if detail == "full" else "plugin_safe"
        payload: dict[str, Any] = {
            "kind": "fallibility_state",
            "enabled": bool(cfg.get("enable_fallibility_state")),
            "exposure": exposure,
        }
        if not payload["enabled"]:
            payload["reason"] = "enable_fallibility_state is false"
        yield json.dumps(payload, ensure_ascii=False, default=str)

    async def get_bot_personality_drift_state_tool(self, event: Any = None, detail: str = "summary", **kwargs: Any) -> Any:
        query_fn = getattr(self, "_query_single_agent_state", None)
        if query_fn and callable(query_fn):
            sk = self._session_key(event)
            track = str(kwargs.get("track", "conversation"))
            payload = await query_fn("personality_drift", event, request=kwargs.get("request"), session_key=sk, detail=detail, track=track)
            yield json.dumps(payload, ensure_ascii=False, default=str)
        else:
            yield json.dumps({"kind": "personality_drift_state", "enabled": True}, ensure_ascii=False, default=str)

    async def get_bot_group_atmosphere_state_tool(self, event: Any = None, detail: str = "summary", **kwargs: Any) -> Any:
        query_fn = getattr(self, "_query_single_agent_state", None)
        if query_fn and callable(query_fn):
            sk = self._session_key(event)
            track = str(kwargs.get("track", "conversation"))
            payload = await query_fn("group_atmosphere", event, request=kwargs.get("request"), session_key=sk, detail=detail, track=track)
            yield json.dumps(payload, ensure_ascii=False, default=str)
        else:
            yield json.dumps({"kind": "group_atmosphere_state"}, ensure_ascii=False, default=str)

    async def simulate_bot_emotion_update_tool(self, event: Any = None, text: str = "", role: str = "user", **kwargs: Any) -> Any:
        sk = self._session_key(event)
        payload = {
            "kind": "simulate_emotion_update",
            "read_only": True,
            "applied": False,
            "session_key": sk,
            "observation": {
                "committed": False,
                "phase": "llm_tool_simulation",
                "source": "llm_tool",
                "role": role,
                "text": text[:200],
            },
        }
        yield json.dumps(payload, ensure_ascii=False, default=str)

    async def request_bot_proactive_speech_dispatch_tool(self, event: Any = None, **kwargs: Any) -> Any:
        dispatch_fn = getattr(self, "request_proactive_speech_dispatch", None)
        if dispatch_fn and callable(dispatch_fn):
            result = await dispatch_fn(event, dry_run=True)
            yield json.dumps(result, ensure_ascii=False, default=str)
        else:
            yield json.dumps({"kind": "proactive_speech_dispatch", "dry_run": True, "dispatched": False}, ensure_ascii=False, default=str)

    # ------------------------------------------------------------------
    # Proactive scheduler / realtime delivery shims
    # ------------------------------------------------------------------
    def _ensure_proactive_scheduler_state(self) -> None:
        if not hasattr(self, "_proactive_scheduler_task"):
            self._proactive_scheduler_task: asyncio.Task | None = None
        if not hasattr(self, "_proactive_candidate_sessions"):
            self._proactive_candidate_sessions: dict[str, Any] = {}
        if not hasattr(self, "_proactive_scheduler_locks"):
            self._proactive_scheduler_locks: dict[str, asyncio.Lock] = {}

    async def _run_proactive_scheduler_once(self) -> dict[str, Any]:
        self._ensure_proactive_scheduler_state()
        candidates = dict(self._proactive_candidate_sessions)
        checked = 0
        dispatched = 0
        for sk, info in candidates.items():
            checked += 1
            dispatch_fn = getattr(self, "request_proactive_speech_dispatch", None)
            if dispatch_fn and callable(dispatch_fn):
                event = info.get("event") or type("_E", (), {"unified_msg_origin": sk, "session_id": sk})()
                result = await dispatch_fn(event, dry_run=False)
                if result.get("dispatched"):
                    dispatched += 1
        return {"checked": checked, "dispatched": dispatched}

    async def terminate(self) -> None:
        task = getattr(self, "_proactive_scheduler_task", None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._proactive_scheduler_task = None
        self._proactive_candidate_sessions = {}
        self._proactive_scheduler_locks = {}
        # Cancel all background tasks
        tasks = getattr(self, "_background_tasks", set())
        for t in list(tasks):
            if not t.done():
                t.cancel()
        for t in list(tasks):
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        if isinstance(tasks, set):
            tasks.clear()
        elif isinstance(tasks, list):
            tasks.clear()
        self._background_tasks = set()
        # Save final checkpoints for background post queues
        bg_queues = getattr(self, "_background_post_queues", {})
        checkpoint_enabled = bool((self.config or {}).get("background_post_queue_checkpoint_enabled"))
        recovered = getattr(self, "_background_post_recovered_sessions", set())
        if checkpoint_enabled:
            for sk in list(bg_queues.keys()):
                if sk in recovered or bg_queues.get(sk):
                    try:
                        await self._save_background_post_checkpoint(sk)
                    except Exception:
                        pass
        # Clean up background post state
        self._background_post_tasks = {}
        self._background_post_queues = {}
        self._background_post_sequence = {}
        self._background_post_skipped = {}
        self._terminating = True

    async def _send_realtime_chat_plan(self, event: Any, plan: dict[str, Any], *, source: str = "", record_history_shadow: bool = False) -> dict[str, Any]:
        session_key = plan.get("session_key") or self._session_key(event)
        plan_epoch = plan.get("input_epoch", 0)
        parts = plan.get("message_parts", [])
        media_parts = plan.get("media_parts", [])
        message_count = 0
        media_count = 0
        media_results: list[dict[str, Any]] = []
        interrupted_reason = ""
        epochs = getattr(self, "_conversation_input_epoch", {})

        for part in parts:
            if plan_epoch and epochs.get(session_key, 0) > plan_epoch:
                interrupted_reason = "user_interrupted"
                break
            text = part.get("text", "")
            delay = part.get("delay_before_seconds", 0.0)
            if delay > 0 and message_count > 0:
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    interrupted_reason = "user_interrupted"
                    break
            if plan_epoch and epochs.get(session_key, 0) > plan_epoch:
                interrupted_reason = "user_interrupted"
                break
            send_fn = getattr(self, "_send_segmented_reply", None)
            if send_fn and callable(send_fn):
                await send_fn(event, text, source=source)
            else:
                reply_fn = getattr(self, "_reply", None)
                if reply_fn and callable(reply_fn):
                    await reply_fn(event, text)
                else:
                    context = getattr(self, "context", None)
                    if context and hasattr(context, "send_message"):
                        origin = str(getattr(event, "unified_msg_origin", "") or session_key)
                        msg = self._build_astrbot_message_chain(text)
                        await context.send_message(origin, msg)
            message_count += 1

        for media in media_parts:
            kind = media.get("kind", "")
            value = media.get("value", "")
            try:
                context = getattr(self, "context", None)
                if context and hasattr(context, "send_message"):
                    import sys
                    event_mod = sys.modules.get("astrbot.api.event")
                    if event_mod:
                        _Chain = getattr(event_mod, "MessageChain", None)
                        if _Chain:
                            chain = _Chain()
                            media_fn = getattr(chain, kind, None)
                            if media_fn and callable(media_fn):
                                media_fn(value)
                                origin = str(getattr(event, "unified_msg_origin", "") or session_key)
                                await context.send_message(origin, chain)
                                media_count += 1
                                media_results.append({"kind": kind, "value": value, "sent": True})
                                continue
                    media_results.append({"kind": kind, "value": value, "blocked_reason": "missing_local_media_file"})
                else:
                    media_results.append({"kind": kind, "value": value, "blocked_reason": "missing_local_media_file"})
            except (FileNotFoundError, OSError):
                media_results.append({"kind": kind, "value": value, "blocked_reason": "missing_local_media_file"})

        if interrupted_reason:
            sent_parts = [p.get("text", "") for p in parts[:message_count]]
            unsent_parts = [p.get("text", "") for p in parts[message_count:]]
            self._record_interrupted_reply_breakpoint(
                session_key,
                full_text=plan.get("full_text", ""),
                sent_parts=sent_parts,
                unsent_parts=unsent_parts,
                input_epoch=plan_epoch,
                reason=interrupted_reason,
            )
            dispatches = getattr(self, "_realtime_chat_active_dispatches", {})
            dispatches[session_key] = {
                "sent_parts": sent_parts,
                "unsent_parts": unsent_parts,
                "interrupted_reason": interrupted_reason,
            }

        if record_history_shadow and message_count > 0:
            full_text = plan.get("full_text", "")
            if not full_text:
                full_text = " ".join(p.get("text", "") for p in parts[:message_count])
            self._record_realtime_ordinary_history_backfill(
                session_key,
                role="assistant",
                content=full_text,
                input_epoch=plan_epoch,
                source=source,
            )

        result: dict[str, Any] = {
            "message_count": message_count,
            "interrupted_reason": interrupted_reason,
        }
        if media_parts:
            result["media_count"] = media_count
            result["media_results"] = media_results
        return result

    async def _flush_sylanne_memory_pending_observations(self, session_key: str, *, generation: int = 0, force: bool = False) -> None:
        flush_fn = getattr(self, "_flush_memory_observations", None)
        if flush_fn and callable(flush_fn):
            await flush_fn(session_key, force=force)

    def _record_realtime_assistant_history_shadow(
        self, session_key: str, *, full_text: str = "", input_epoch: int = 0,
        message_parts: list[dict[str, Any]] | None = None, source: str = "",
        event_time: dict[str, Any] | None = None, delivery_status: str = "",
    ) -> None:
        if not hasattr(self, "_realtime_assistant_history_shadows"):
            self._realtime_assistant_history_shadows: dict[str, list[dict[str, Any]]] = {}
        shadows = self._realtime_assistant_history_shadows.setdefault(session_key, [])
        entry: dict[str, Any] = {
            "full_text": full_text,
            "input_epoch": input_epoch,
            "message_parts": message_parts or [],
            "source": source,
        }
        if event_time:
            entry["event_time"] = event_time
        if delivery_status:
            entry["delivery_status"] = delivery_status
        shadows.append(entry)

    def _record_interrupted_reply_breakpoint(
        self, session_key: str, *, full_text: str = "", sent_parts: list[str] | None = None,
        unsent_parts: list[str] | None = None, input_epoch: int = 0, reason: str = "",
        event_time: dict[str, Any] | None = None, source: str = "",
    ) -> None:
        if not hasattr(self, "_interrupted_reply_breakpoints"):
            self._interrupted_reply_breakpoints: dict[str, list[dict[str, Any]]] = {}
        bps = self._interrupted_reply_breakpoints.setdefault(session_key, [])
        entry: dict[str, Any] = {
            "full_text": full_text,
            "sent_parts": sent_parts or [],
            "unsent_parts": unsent_parts or [],
            "input_epoch": input_epoch,
            "reason": reason,
        }
        if event_time:
            entry["event_time"] = event_time
        bps.append(entry)

    def _realtime_delivery_context_kv_key(self, session_key: str) -> str:
        return f"sylanne:realtime_delivery_context:{session_key}"

    def _record_realtime_ordinary_history_backfill(
        self, session_key: str, *, role: str = "", content: str = "",
        input_epoch: int = 0, source: str = "", delivery_status: str = "",
    ) -> None:
        if not hasattr(self, "_realtime_ordinary_history_backfills"):
            self._realtime_ordinary_history_backfills: dict[str, list[dict[str, Any]]] = {}
        entries = self._realtime_ordinary_history_backfills.setdefault(session_key, [])
        entries.append({
            "role": role,
            "content": content,
            "input_epoch": input_epoch,
            "source": source,
        })

    def _record_active_agent_pending_user_turn(
        self, session_key: str, identity: Any = None, *,
        input_epoch: int = 0, text: str = "", observed_at: float = 0.0,
    ) -> None:
        if not hasattr(self, "_active_agent_pending_user_turns"):
            self._active_agent_pending_user_turns: dict[str, list[dict[str, Any]]] = {}
        turns = self._active_agent_pending_user_turns.setdefault(session_key, [])
        turns.append({
            "input_epoch": input_epoch,
            "text": text,
            "observed_at": observed_at,
            "identity": identity,
        })

    def _fast_assessor_max_context_chars(self) -> int:
        return self._cfg_int("fast_assessor_max_context_chars", 240)

    def _discard_conversation_pending_response_epoch(self, session_key: str, epoch: int = 0) -> None:
        epochs = getattr(self, "_conversation_pending_response_epochs", None)
        if epochs and session_key in epochs:
            del epochs[session_key]

    def _conversation_reply_is_stale(self, session_key: str, reply_epoch: int) -> bool:
        epochs = getattr(self, "_conversation_input_epoch", {})
        current = epochs.get(session_key, 0)
        return reply_epoch < current

    def _realtime_assistant_history_shadow_cache(self) -> dict[str, list[dict[str, Any]]]:
        if not hasattr(self, "_realtime_assistant_history_shadows"):
            self._realtime_assistant_history_shadows: dict[str, list[dict[str, Any]]] = {}
        return self._realtime_assistant_history_shadows

    def _append_realtime_assistant_history_shadow_if_any(
        self, request: Any, session_key: str, *, budget: Any = None, current_user_text: str = "",
    ) -> bool:
        cache = self._realtime_assistant_history_shadow_cache()
        shadows = cache.get(session_key, [])
        if not shadows:
            return False
        last = shadows[-1]
        if last.get("consumed"):
            return False
        contexts = getattr(request, "contexts", []) or []
        for ctx in contexts:
            if isinstance(ctx, dict):
                ctx_content = str(ctx.get("content") or "")
                if "[sylanne_realtime_assistant_history]" in ctx_content:
                    last["consumed"] = True
                    last["consumed_reason"] = "official_context_compression_summary"
                    return False
        full_text = last.get("full_text", "")
        event_time = last.get("event_time", {})
        event_time_line = ""
        if event_time:
            event_time_line = f"\nevent_local_time={event_time.get('event_local_time', event_time.get('local_datetime', ''))}\ntimezone={event_time.get('timezone', '')}"
        prompt = str(getattr(request, "prompt", "") or "")
        request.prompt = prompt + "\n[sylanne_realtime_assistant_history]" + event_time_line + "\n" + full_text
        last["consumed"] = True
        last["consumed_reason"] = "injected"
        return True

    def _append_interrupted_reply_breakpoint_if_any(
        self, request: Any, session_key: str, *, budget: Any = None,
    ) -> bool:
        bps = getattr(self, "_interrupted_reply_breakpoints", {})
        entries = bps.get(session_key, [])
        if not entries:
            return False
        last = entries[-1]
        if last.get("consumed"):
            return False
        full_text = last.get("full_text", "")
        event_time = last.get("event_time", {})
        event_time_line = ""
        if event_time:
            event_time_line = f"\nevent_local_time={event_time.get('event_local_time', event_time.get('local_datetime', ''))}\ntimezone={event_time.get('timezone', '')}"
        prompt = str(getattr(request, "prompt", "") or "")
        request.prompt = prompt + "\n[sylanne_interrupted_reply_breakpoint]" + event_time_line + "\n" + full_text
        last["consumed"] = True
        return True

    def _build_realtime_delivery_envelope_text(
        self, text: str, *, session_key: str = "", input_epoch: int = 0,
        message_parts: list[dict[str, Any]] | None = None,
        event_time: dict[str, Any] | None = None,
    ) -> str:
        lines = ["[sylanne_realtime_delivery_envelope]"]
        if event_time:
            lines.append(f"event_local_time={event_time.get('event_local_time', event_time.get('local_datetime', ''))}")
            lines.append(f"timezone={event_time.get('timezone', '')}")
        lines.append(f"text={text}")
        lines.append("note=realtime segmented delivery disabled or removed in alpha host")
        return "\n".join(lines)

    def _start_realtime_chat_active_dispatch(
        self, session_key: str, *, input_epoch: int = 0, full_text: str = "",
        source: str = "", event_time: dict[str, Any] | None = None,
    ) -> None:
        if not hasattr(self, "_realtime_chat_active_dispatches"):
            self._realtime_chat_active_dispatches: dict[str, list[dict[str, Any]]] = {}
        dispatches = self._realtime_chat_active_dispatches.setdefault(session_key, [])
        entry: dict[str, Any] = {
            "input_epoch": input_epoch,
            "full_text": full_text,
            "source": source,
        }
        if event_time:
            entry["event_time"] = event_time
        dispatches.append(entry)

    def _append_realtime_chat_active_dispatch_if_any(
        self, request: Any, session_key: str, *, budget: Any = None,
    ) -> bool:
        dispatches = getattr(self, "_realtime_chat_active_dispatches", {})
        entries = dispatches.get(session_key, [])
        if not entries:
            return False
        last = entries[-1]
        if last.get("consumed"):
            return False
        full_text = last.get("full_text", "")
        event_time = last.get("event_time", {})
        event_time_line = ""
        if event_time:
            event_time_line = f"\ntrigger_event_local_time={event_time.get('event_local_time', event_time.get('local_datetime', ''))}\ntrigger_timezone={event_time.get('timezone', '')}"
        prompt = str(getattr(request, "prompt", "") or "")
        request.prompt = prompt + "\n[sylanne_realtime_chat_active_dispatch]" + event_time_line + "\n" + full_text
        last["consumed"] = True
        return True

    def _append_realtime_continuity_context_if_any(
        self, request: Any, session_key: str, *, budget: Any = None, current_user_text: str = "",
    ) -> bool:
        cache = self._realtime_assistant_history_shadow_cache()
        shadows = cache.get(session_key, [])
        if not shadows:
            return False
        last = shadows[-1]
        full_text = last.get("full_text", "")
        if not full_text:
            return False
        if "？" in full_text or "?" in full_text:
            prompt = str(getattr(request, "prompt", "") or "")
            injection = (
                "[sylanne_realtime_pending_bot_question]\n"
                + "上一轮 bot 刚提出了一个未闭合问题：" + full_text + "\n"
                + "current_user_short_answer=" + current_user_text
            )
            request.prompt = prompt + "\n" + injection
            return True
        return False

    def _realtime_ordinary_history_backfill_cache(self) -> dict[str, list[dict[str, Any]]]:
        if not hasattr(self, "_realtime_ordinary_history_backfills"):
            self._realtime_ordinary_history_backfills: dict[str, list[dict[str, Any]]] = {}
        return self._realtime_ordinary_history_backfills

    async def _release_realtime_temporary_context_after_background_post(
        self, session_key: str, *, input_epoch: int = 0, reason: str = "",
    ) -> None:
        cache = self._realtime_assistant_history_shadow_cache()
        shadows = cache.get(session_key, [])
        for shadow in shadows:
            if shadow.get("input_epoch") == input_epoch and not shadow.get("consumed"):
                shadow["consumed"] = True
                shadow["consumed_reason"] = reason
                break
        backfills = self._realtime_ordinary_history_backfill_cache()
        backfills.pop(session_key, None)

    def _release_realtime_temporary_context_after_background_post_in_memory(
        self, session_key: str, *, input_epoch: int | None = 0, reason: str = "",
    ) -> bool:
        if input_epoch is None:
            return False
        cache = self._realtime_assistant_history_shadow_cache()
        shadows = cache.get(session_key, [])
        changed = False
        for shadow in shadows:
            if shadow.get("input_epoch") == input_epoch and not shadow.get("consumed"):
                shadow["consumed"] = True
                shadow["consumed_reason"] = reason
                changed = True
                break
        if changed:
            backfills = self._realtime_ordinary_history_backfill_cache()
            if session_key in backfills:
                backfills[session_key] = {
                    k: v for k, v in backfills[session_key].items() if k > input_epoch
                }
                if not backfills[session_key]:
                    del backfills[session_key]
        return changed

    # ------------------------------------------------------------------
    # LLM Tool: query_agent_state
    # ------------------------------------------------------------------
    @filter.llm_tool(name="query_agent_state")
    async def _llm_tool_query_agent_state(self, event: Any) -> Any:
        session_key = self._session_key(event)
        host = self._host(session_key)
        payload = host.diagnostics()
        max_chars = self._cfg_int("llm_tool_response_max_chars", 16000)
        result = json.dumps(payload, ensure_ascii=False, default=str)
        if len(result) > max_chars:
            result = result[:max_chars - 50] + "\n[sylanne_tool_response_trimmed]"
        return event.plain_result(result) if hasattr(event, "plain_result") else result

