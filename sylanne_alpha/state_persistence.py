"""State persistence helpers extracted from main.py.

Handles kernel and conversation-buffer persistence via AstrBot KV storage
(primary) with file I/O fallback.  Also provides all engine-state KV key
helpers and load/save/delete wrappers for emotion, humanlike, psychological,
lifelike-learning, personality-drift, moral-repair, fallibility, group-
atmosphere, and Sylanne memory states.
"""

from __future__ import annotations

import asyncio
import logging
import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .host import SylanneAlphaHost

logger = logging.getLogger("astrbot_plugin_sylanne")


def _safe_ensure_future(coro: Any, name: str = "task") -> "asyncio.Task[Any]":
    """Wrap a coroutine in ensure_future with exception logging."""

    async def _wrapper() -> None:
        try:
            await coro
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Background task '{name}' failed: {e}", exc_info=True)

    return asyncio.ensure_future(_wrapper())


class StatePersistence:
    """Encapsulates kernel/buffer persistence logic delegated from the plugin."""

    def __init__(self, plugin: Any) -> None:
        self._p = plugin
        self._buffer_persist_timers: dict[str, asyncio.TimerHandle] = {}

    # ------------------------------------------------------------------
    # KV key helpers
    # ------------------------------------------------------------------

    def kernel_kv_key(self, session_key: str) -> str:
        safe = self._safe_session_key(session_key)
        return f"sylanne_kernel_{safe}"

    def buffer_kv_key(self, session_key: str) -> str:
        safe = self._safe_session_key(session_key)
        return f"sylanne_buffer_{safe}"

    def has_kv_api(self) -> bool:
        """Check if AstrBot KV storage API is available."""
        return hasattr(self._p, "put_kv_data") and callable(self._p.put_kv_data)

    # ------------------------------------------------------------------
    # Engine-state KV key helpers
    # ------------------------------------------------------------------

    def kv_key(self, session_key: str) -> str:
        safe = self._safe_session_key(session_key)
        return f"emotion_state:{safe}"

    def humanlike_kv_key(self, session_key: str) -> str:
        safe = self._safe_session_key(session_key)
        return f"humanlike_state:{safe}"

    def lifelike_learning_kv_key(self, session_key: str) -> str:
        safe = self._safe_session_key(session_key)
        return f"lifelike_learning:{safe}"

    def personality_drift_kv_key(self, session_key: str) -> str:
        safe = self._safe_session_key(session_key)
        return f"personality_drift:{safe}"

    def moral_repair_kv_key(self, session_key: str) -> str:
        safe = self._safe_session_key(session_key)
        return f"moral_repair_state:{safe}"

    def fallibility_kv_key(self, session_key: str) -> str:
        safe = self._safe_session_key(session_key)
        return f"fallibility_state:{safe}"

    def psychological_kv_key(self, session_key: str) -> str:
        safe = self._safe_session_key(session_key)
        return f"psychological_screening:{safe}"

    def sylanne_memory_kv_key(self, session_key: str) -> str:
        safe = session_key.replace("/", "_").replace("\\", "_")
        return f"sylanne_memory_state:{safe}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _safe_session_key(self, session_key: str) -> str:
        """Sanitize session key for use in KV keys (delegates to plugin cache)."""
        cache = getattr(self._p, "_safe_session_key_cache", None)
        if cache is None:
            self._p._safe_session_key_cache = {}
            cache = self._p._safe_session_key_cache
        if session_key in cache:
            return cache[session_key]
        safe = session_key.replace("/", "_").replace("\\", "_")
        cache[session_key] = safe
        return safe

    # ------------------------------------------------------------------
    # Kernel persistence
    # ------------------------------------------------------------------

    async def persist_kernel(self, session_key: str, host: SylanneAlphaHost) -> None:
        """Save kernel state: KV storage (primary) with file I/O fallback."""
        snapshot = host.kernel.snapshot()
        if self.has_kv_api():
            try:
                await self._p.put_kv_data(self.kernel_kv_key(session_key), snapshot)
            except Exception as e:
                logger.warning(f"Sylanne kernel KV persist: {e}", exc_info=True)
        # Always write to file as well (backwards compat / fallback)
        try:
            host.runtime.save(host.kernel)
        except Exception as e:
            logger.warning(f"Sylanne kernel file persist: {e}", exc_info=True)

    def persist_kernel_sync(self, session_key: str, host: SylanneAlphaHost) -> None:
        """Sync-only kernel save (for LRU eviction in non-async context)."""
        try:
            host.runtime.save(host.kernel)
        except Exception as e:
            logger.warning(f"Sylanne kernel sync persist: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Buffer persistence
    # ------------------------------------------------------------------

    async def persist_buffer(
        self, session_key: str, host: SylanneAlphaHost, buf_dict: dict[str, Any]
    ) -> None:
        """Save conversation buffer: KV storage (primary) with file I/O fallback."""
        if self.has_kv_api():
            try:
                await self._p.put_kv_data(self.buffer_kv_key(session_key), buf_dict)
            except Exception as e:
                logger.warning(f"Sylanne buffer KV persist: {e}", exc_info=True)
        # Always write to file as well (backwards compat / fallback)
        try:
            host.runtime.save_buffer(session_key, buf_dict)
        except Exception as e:
            logger.warning(f"Sylanne buffer file persist: {e}", exc_info=True)

    async def load_buffer_data(
        self, session_key: str, host: SylanneAlphaHost
    ) -> dict[str, Any] | None:
        """Load conversation buffer: KV storage (primary) with file I/O fallback."""
        if self.has_kv_api():
            try:
                data = await self._p.get_kv_data(self.buffer_kv_key(session_key), None)
                if data and isinstance(data, dict):
                    return data
            except Exception as e:
                logger.debug(f"Sylanne skip: {e}")
        # Fallback to file I/O
        return host.runtime.load_buffer(session_key)

    # ------------------------------------------------------------------
    # Debounced buffer persist scheduling
    # ------------------------------------------------------------------

    def schedule_buffer_persist(self, session_key: str) -> None:
        """Debounced buffer persist -- waits 5s, coalesces multiple writes."""
        if session_key in self._buffer_persist_timers:
            self._buffer_persist_timers[session_key].cancel()
        try:
            loop = asyncio.get_running_loop()
            self._buffer_persist_timers[session_key] = loop.call_later(
                5.0,
                lambda sk=session_key: _safe_ensure_future(
                    self._do_buffer_persist(sk), name="buffer_persist"
                ),
            )
        except RuntimeError:
            pass

    async def _do_buffer_persist(self, session_key: str) -> None:
        """Actually write buffer: KV storage (primary) with file I/O fallback."""
        self._buffer_persist_timers.pop(session_key, None)
        buf = self._p._conversation_buffers.get(session_key)
        if not buf:
            return
        host = self._p._hosts.get(session_key)
        if not host or not hasattr(host, "runtime"):
            return
        buf_dict = buf.to_dict()
        await self.persist_buffer(session_key, host, buf_dict)

    # ------------------------------------------------------------------
    # Boot-time buffer restoration
    # ------------------------------------------------------------------

    def restore_buffers_on_boot(self) -> None:
        """Restore conversation buffers from file on plugin load (sync fallback).

        KV-based buffer data is always kept in sync via persist_buffer,
        so file I/O here is equivalent. Async KV load is not possible in
        this sync context.
        """
        from .memory_system import ConversationBuffer

        for sk, host in list(self._p._hosts.items()):
            if not hasattr(host, "runtime"):
                continue
            data = host.runtime.load_buffer(sk)
            if data and isinstance(data, dict):
                self._p._conversation_buffers[sk] = ConversationBuffer.from_dict(data)

    # ------------------------------------------------------------------
    # Engine state: load / save / delete (emotion core)
    # ------------------------------------------------------------------

    async def load_state(
        self, session_key: str, persona_profile: Any = None, *, now: float = 0.0
    ) -> Any:
        cache = getattr(self._p, "_engine_cache", None)
        if cache is None:
            self._p._engine_cache = {}
            cache = self._p._engine_cache
        if session_key in cache:
            return cache[session_key]
        key = self.kv_key(session_key)
        get_kv = getattr(self._p, "get_kv_data", None)
        if get_kv and callable(get_kv):
            data = await get_kv(key, None)
        else:
            data = None
        if data is not None:
            cache[session_key] = data
            return data
        cache[session_key] = data
        return data

    async def save_state(self, session_key: str, state: Any = None) -> None:
        pass

    async def delete_state(self, session_key: str) -> None:
        pass

    # ------------------------------------------------------------------
    # Humanlike state
    # ------------------------------------------------------------------

    async def load_humanlike_state(self, session_key: str) -> Any:
        return None

    async def save_humanlike_state(self, session_key: str, state: Any = None) -> None:
        pass

    async def delete_humanlike_state(self, session_key: str) -> None:
        pass

    # ------------------------------------------------------------------
    # Psychological state
    # ------------------------------------------------------------------

    async def load_psychological_state(self, session_key: str) -> Any:
        return None

    async def save_psychological_state(
        self, session_key: str, state: Any = None
    ) -> None:
        pass

    async def delete_psychological_state(self, session_key: str) -> None:
        pass

    # ------------------------------------------------------------------
    # Lifelike learning state
    # ------------------------------------------------------------------

    async def load_lifelike_learning_state(
        self, session_key: str, **kwargs: Any
    ) -> Any:
        return None

    async def save_lifelike_learning_state(
        self, session_key: str, state: Any = None
    ) -> None:
        pass

    async def delete_lifelike_learning_state(self, session_key: str) -> None:
        pass

    # ------------------------------------------------------------------
    # Personality drift state
    # ------------------------------------------------------------------

    async def load_personality_drift_state(
        self, session_key: str, **kwargs: Any
    ) -> Any:
        return None

    async def save_personality_drift_state(
        self, session_key: str, state: Any = None
    ) -> None:
        pass

    async def delete_personality_drift_state(self, session_key: str) -> None:
        pass

    # ------------------------------------------------------------------
    # Moral repair state
    # ------------------------------------------------------------------

    async def load_moral_repair_state(self, session_key: str) -> Any:
        return None

    async def save_moral_repair_state(
        self, session_key: str, state: Any = None
    ) -> None:
        pass

    async def delete_moral_repair_state(self, session_key: str) -> None:
        pass

    # ------------------------------------------------------------------
    # Fallibility state
    # ------------------------------------------------------------------

    async def load_fallibility_state(self, session_key: str) -> Any:
        return None

    async def save_fallibility_state(self, session_key: str, state: Any = None) -> None:
        pass

    async def delete_fallibility_state(self, session_key: str) -> None:
        pass

    # ------------------------------------------------------------------
    # Group atmosphere state
    # ------------------------------------------------------------------

    async def load_group_atmosphere_state(self, session_key: str) -> Any:
        return None

    # ------------------------------------------------------------------
    # Sylanne memory state
    # ------------------------------------------------------------------

    async def save_sylanne_memory_state(
        self, session_key: str, state: Any = None
    ) -> None:
        if state is None:
            return
        from .memory_system import MemorySystem

        cache = self._p._sylanne_memory_cache
        if not isinstance(cache, dict):
            cache = {}
        self._p._sylanne_memory_cache = cache
        cache[session_key] = state
        if isinstance(state, MemorySystem):
            self._p._memory_systems[session_key] = state
        kv_key = self.sylanne_memory_kv_key(session_key)
        put_fn = getattr(self._p, "put_kv_data", None)
        if put_fn and callable(put_fn):
            data = state.to_dict() if hasattr(state, "to_dict") else state
            await put_fn(kv_key, data)

    async def load_sylanne_memory_state(
        self, session_key: str, *, now: float = 0.0
    ) -> Any:
        from .memory_system import MemorySystem

        def has_content(state: Any) -> bool:
            if state is None:
                return False
            if (
                hasattr(state, "_l1")
                or hasattr(state, "_l2")
                or hasattr(state, "_l3_nodes")
            ):
                return bool(
                    list(getattr(state, "_l1", []) or [])
                    or list(getattr(state, "_l2", []) or [])
                    or dict(getattr(state, "_l3_nodes", {}) or {})
                    or list(getattr(state, "_l3_edges", []) or [])
                )
            return bool(list(getattr(state, "records", []) or []))

        cache = self._p._sylanne_memory_cache
        if not isinstance(cache, dict):
            cache = {}
        self._p._sylanne_memory_cache = cache
        cached_state = cache.get(session_key) if isinstance(cache, dict) else None
        if has_content(cached_state):
            return cache[session_key]
        system_cache = getattr(self._p, "_memory_systems", {}) or {}
        live_state = (
            system_cache.get(session_key) if isinstance(system_cache, dict) else None
        )
        if has_content(live_state):
            return live_state
        kv_key = self.sylanne_memory_kv_key(session_key)
        get_fn = getattr(self._p, "get_kv_data", None)
        put_fn = getattr(self._p, "put_kv_data", None)
        if get_fn and callable(get_fn):
            data = await get_fn(kv_key, None)
            if data is not None:
                if isinstance(data, dict) and {
                    "l1",
                    "l2",
                    "l3_nodes",
                    "l3_edges",
                }.issubset(data.keys()):
                    try:
                        state = MemorySystem.create_from_dict(data)
                        self._p._memory_systems[session_key] = state
                        cache[session_key] = state
                        return state
                    except Exception as e:
                        logger.debug(f"Sylanne skip: {e}")
                try:
                    from memory_engine import SylanneMemoryState

                    state = SylanneMemoryState.from_dict(data)
                    if now and hasattr(state, "records"):
                        original_count = len(state.records)
                        surviving = []
                        for rec in state.records:
                            auto_params = getattr(rec, "auto_parameters", None) or {}
                            half_life = float(
                                auto_params.get("decay_half_life_seconds", 0)
                            )
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
                            if hasattr(state, "dynamics") and hasattr(
                                state.dynamics, "notes"
                            ):
                                state.dynamics.notes = f"forgotten={forgotten_count}"
                            if put_fn and callable(put_fn):
                                save_data = state.to_dict()
                                await put_fn(kv_key, save_data)
                    cache[session_key] = state
                    return state
                except Exception as e:
                    logger.debug(f"Sylanne skip: {e}")
        try:
            host = self._p._host(session_key)
            data = host.kernel.body.memory.get("_memory_system")
            if isinstance(data, dict):
                state = MemorySystem.create_from_dict(data)
                self._p._memory_systems[session_key] = state
                cache[session_key] = state
                return state
        except Exception as e:
            logger.debug(f"Sylanne skip: {e}")
        if cached_state is not None:
            return cached_state
        if live_state is not None:
            return live_state
        return None

    async def delete_sylanne_memory_state(self, session_key: str) -> None:
        cache = self._p._sylanne_memory_cache
        cache.pop(session_key, None)
        kv_key = self.sylanne_memory_kv_key(session_key)
        delete_fn = getattr(self._p, "delete_kv_data", None)
        if delete_fn and callable(delete_fn):
            await delete_fn(kv_key)

    # ------------------------------------------------------------------
    # AstrBot ConversationManager integration
    # ------------------------------------------------------------------

    def init_conversation_manager(self) -> Any:
        """Initialize AstrBot ConversationManager if available."""
        p = self._p
        context = getattr(p, "context", None)
        if context is None:
            return None
        conv_mgr = getattr(context, "conversation_manager", None)
        if conv_mgr is not None:
            logger.info(
                "Sylanne: AstrBot ConversationManager detected, parallel sync enabled"
            )
        return conv_mgr

    def has_conversation_manager(self) -> bool:
        """Check if AstrBot ConversationManager is available."""
        return getattr(self._p, "_conv_mgr", None) is not None

    async def sync_message_to_conv_mgr(
        self, session_key: str, role: str, text: str
    ) -> None:
        """Sync a message to AstrBot's ConversationManager (parallel path).

        This keeps AstrBot's conversation system in sync without replacing
        Sylanne's own ConversationBuffer (which is still needed for flush/
        consolidation logic).
        """
        p = self._p
        conv_mgr = getattr(p, "_conv_mgr", None)
        if conv_mgr is None:
            return
        try:
            # Get or create conversation for this session
            curr_cid = await conv_mgr.get_curr_conversation_id(session_key)
            if not curr_cid:
                curr_cid = await conv_mgr.new_conversation(session_key)

            # Try to use AstrBot message types; fall back to plain dicts
            try:
                from astrbot.core.agent.message import (
                    AssistantMessageSegment,
                    TextPart,
                    UserMessageSegment,
                )

                if role == "user":
                    msg = UserMessageSegment(content=[TextPart(text=text)])
                else:
                    msg = AssistantMessageSegment(content=[TextPart(text=text)])
            except ImportError:
                # Older AstrBot or test environment: use plain dict
                msg = {"role": role, "content": text}

            conversation = await conv_mgr.get_conversation(session_key, curr_cid)
            history = list(
                getattr(conversation, "history", None) or [] if conversation else []
            )
            history.append(msg)
            await conv_mgr.update_conversation(session_key, curr_cid, history=history)
        except Exception as e:
            logger.debug(f"Sylanne: ConversationManager sync failed: {e}")

    # ------------------------------------------------------------------
    # AstrBot PersonaManager integration
    # ------------------------------------------------------------------

    def init_persona_manager(self) -> Any:
        """Initialize AstrBot PersonaManager if available."""
        p = self._p
        context = getattr(p, "context", None)
        if context is None:
            return None
        persona_mgr = getattr(context, "persona_manager", None)
        if persona_mgr is not None:
            logger.info(
                "Sylanne: AstrBot PersonaManager detected, personality sync enabled"
            )
        return persona_mgr

    def has_persona_manager(self) -> bool:
        """Check if AstrBot PersonaManager is available."""
        return getattr(self._p, "_persona_mgr", None) is not None

    def sync_personality_to_persona_mgr(self, session_key: str) -> None:
        """Sync Sylanne personality state to AstrBot's PersonaManager.

        Called after personality drift updates. Creates or updates a
        Sylanne persona entry so AstrBot's persona system is aware of
        the current personality state.
        """
        p = self._p
        persona_mgr = getattr(p, "_persona_mgr", None)
        if persona_mgr is None:
            return
        try:
            host = p._hosts.get(session_key)
            if not host:
                return
            # Extract personality data from kernel
            personality = (
                host.kernel._personality()
                if hasattr(host.kernel, "_personality")
                else {}
            )
            if not personality or not isinstance(personality, dict):
                return

            traits = personality.get("traits", {})
            voice = personality.get("voice", {})

            # Build system prompt fragment from personality state
            trait_lines = []
            for k, v in traits.items():
                if isinstance(v, (int, float)):
                    trait_lines.append(f"{k}={v:.3f}")
                elif isinstance(v, dict) and "value" in v:
                    trait_lines.append(f"{k}={v['value']:.3f}")
            trait_summary = ", ".join(trait_lines) if trait_lines else "default"

            safe_sk = self._safe_session_key(session_key)
            persona_id = f"sylanne_embodiment_{safe_sk}"
            system_prompt = (
                f"[Sylanne Personality State]\n"
                f"Traits: {trait_summary}\n"
                f"Voice: {voice if voice else 'default'}"
            )

            # Try update first, create if not exists
            try:
                existing = persona_mgr.get_persona(persona_id)
                if existing:
                    persona_mgr.update_persona(persona_id, system_prompt=system_prompt)
                else:
                    persona_mgr.create_persona(
                        persona_id=persona_id,
                        system_prompt=system_prompt,
                        begin_dialogs=[],
                        tools=None,
                    )
            except Exception:
                # create_persona may not accept all args in older versions
                try:
                    persona_mgr.create_persona(
                        persona_id=persona_id,
                        system_prompt=system_prompt,
                    )
                except Exception:
                    pass  # cleanup: persona sync failure acceptable
        except Exception as e:
            logger.debug(f"Sylanne: PersonaManager sync failed: {e}")

    # ------------------------------------------------------------------
    # Provider ID resolution
    # ------------------------------------------------------------------

    async def provider_id(self, event: Any = None) -> str:
        import time

        p = self._p
        cache = getattr(p, "_provider_id_cache", None)
        if cache is None:
            p._provider_id_cache = {}
            cache = p._provider_id_cache
        sk = p._session_key(event)
        cached = cache.get(sk)
        if cached:
            ts, val = cached
            ttl = float((p.config or {}).get("provider_id_cache_ttl_seconds", 30.0))
            if time.time() - ts < ttl:
                return val
        context = getattr(p, "context", None) or p.context
        if hasattr(context, "get_current_chat_provider_id"):
            try:
                umo = str(getattr(event, "unified_msg_origin", "") or sk)
                result = await context.get_current_chat_provider_id(umo=umo)
                val = str(result or "")
                cache[sk] = (time.time(), val)
                return val
            except Exception as e:
                logger.debug(f"Sylanne skip: {e}")
        return ""

    # ------------------------------------------------------------------
    # Config defaults initialization
    # ------------------------------------------------------------------

    def load_config_defaults(self) -> None:
        """Initialize all config keys with their default values."""
        p = self._p
        p._cfg_bool("sylanne_webui_enabled", False)
        p._cfg("sylanne_webui_host", "0.0.0.0")
        p._cfg_int("sylanne_webui_port", 2718)
        p._cfg_bool("enabled", True)
        p._cfg_bool("use_llm_assessor", True)
        p._cfg("emotion_provider_id", "")
        p._cfg_bool("fast_assessor_enabled", False)
        p._cfg("fast_assessor_provider_id", "")
        p._cfg_int("fast_assessor_max_context_chars", 600)
        p._cfg_float("fast_assessor_timeout_seconds", 2.0)
        p._cfg_float("fast_assessor_temperature", 0.0)
        p._cfg_bool("low_reasoning_friendly_mode", False)
        p._cfg_int("low_reasoning_max_context_chars", 1200)
        p._cfg("assessment_timing", "post")
        p._cfg_bool("enable_proactive_speech_dispatch", False)
        p._cfg_bool("enable_proactive_speech_scheduler", False)
        p._cfg_bool("enable_realtime_chat", False)
        p._cfg_bool("realtime_chat_style_prompt_enabled", False)
        p._cfg_bool("realtime_chat_intercept_llm_response", False)
        p._cfg_bool("realtime_input_completion_llm_gate_enabled", False)
        p._cfg_float("realtime_input_completion_probe_delay_seconds", 0.25)
        p._cfg_float("realtime_input_completion_max_wait_seconds", 4.0)
        p._cfg_float("realtime_user_typing_hold_seconds", 0.8)
        p._cfg_float("realtime_empty_input_typing_hold_seconds", 0.35)
        p._cfg_bool("realtime_chat_dry_run_default", False)
        p._cfg_bool("realtime_chat_strip_markdown", True)
        p._cfg_bool("enable_sticker_reaction", False)
        p._cfg_int("background_post_queue_limit", 0)
        p._cfg_bool("enable_dynamic_background_workers", False)
        p._cfg_bool("background_post_queue_checkpoint_enabled", True)
        p._cfg_float("background_post_checkpoint_debounce_seconds", 0.75)
        p._cfg_float("background_post_job_lease_seconds", 120.0)
        p._cfg_float("background_post_job_timeout_seconds", 0.0)
        p._cfg_int("background_post_retry_max_attempts", 3)
        p._cfg_float("background_post_retry_base_delay_seconds", 2.0)
        p._cfg_float("background_post_retry_max_delay_seconds", 60.0)
        p._cfg_int("background_post_dead_letter_limit", 100)
        p._cfg_int("background_post_diagnostics_warn_lag_count", 20)
        p._cfg_float("background_post_diagnostics_warn_lag_seconds", 60.0)
        p._cfg_bool("enable_low_signal_light_assessment", True)
        p._cfg_int("low_signal_max_chars", 12)
        p._cfg_bool("sylanne_alpha_assessor_llm_enabled", False)
        p._cfg("sylanne_alpha_assessor_provider_id", "")
        p._cfg_float("sylanne_alpha_assessor_timeout_seconds", 2.0)
        p._cfg_float("sylanne_alpha_fast_assessor_timeout_seconds", 1.5)
        p._cfg_bool("sylanne_alpha_main_assessor_enabled", False)
        p._cfg("sylanne_alpha_main_assessor_provider_id", "")
        p._cfg_float("sylanne_alpha_main_assessor_timeout_seconds", 3.0)
        p._cfg_bool("agent_speaker_relationship_tracking", True)
        p._cfg_bool("agent_include_speaker_in_assessment", True)
        p._cfg_int("agent_identity_profile_limit", 256)
        p._cfg_float("agent_identity_ttl_seconds", 2592000.0)
        p._cfg_bool("enable_agent_causal_trail", True)
        p._cfg_int("agent_trail_limit", 80)
        p._cfg_bool("agent_trail_compaction_enabled", True)
        p._cfg_float("agent_trail_low_signal_delta_threshold", 0.03)
        p._cfg_int("agent_trail_low_signal_window", 5)
        p._cfg_bool("inject_state", True)
        p._cfg_bool("runtime_parameter_debug_override_enabled", False)
        p._cfg_int("state_injection_request_budget_chars", 32000)
        p._cfg_int("state_injection_reserved_chars", 3000)
        p._cfg_int("state_injection_max_added_chars", 2400)
        p._cfg_int("state_injection_max_parts", 8)
        p._cfg_int("llm_tool_response_max_chars", 16000)
        p._cfg_bool("enable_safety_boundary", True)
        p._cfg_bool("block_deception_manipulation_evasion_actions", True)
        p._cfg_int("max_context_chars", 1600)
        p._cfg_int("request_context_max_chars", 1600)
        p._cfg_float("assessor_timeout_seconds", 0.0)
        p._cfg_float("assessor_temperature", 0.1)
        p._cfg_float("provider_id_cache_ttl_seconds", 30.0)
        p._cfg_float("passive_load_fresh_seconds", 1.0)
        p._cfg_bool("benchmark_enable_simulated_time", False)
        p._cfg_float("benchmark_time_offset_seconds", 0.0)
        p._cfg_bool("allow_emotion_reset_backdoor", True)
        p._cfg_bool("enable_psychological_screening", False)
        p._cfg_float("sylanne_memory_idle_commit_delay_seconds", 4.0)
        p._cfg_bool("sylanne_memory_vector_retrieval_enabled", True)
        p._cfg("sylanne_memory_embedding_provider_id", "")
        p._cfg_float("sylanne_memory_record_embedding_min_interval_seconds", 300.0)
        p._cfg_int("sylanne_memory_record_embedding_max_per_flush", 1)
        p._cfg_bool("sylanne_memory_debug_view_enabled", False)
        p._cfg_bool("humanlike_memory_write_enabled", True)
        p._cfg_bool("allow_humanlike_reset_backdoor", True)
        p._cfg_bool("lifelike_learning_memory_write_enabled", True)
        p._cfg_bool("allow_lifelike_learning_reset_backdoor", True)
        p._cfg_bool("personality_drift_memory_write_enabled", True)
        p._cfg_bool("allow_personality_drift_reset_backdoor", True)
        p._cfg_bool("enable_moral_repair_state", False)
        p._cfg_bool("moral_repair_memory_write_enabled", True)
        p._cfg_bool("allow_moral_repair_reset_backdoor", True)
        p._cfg_bool("enable_fallibility_state", False)
        p._cfg_bool("fallibility_memory_write_enabled", True)
        p._cfg_bool("allow_fallibility_reset_backdoor", True)
        p._cfg_bool("enable_shadow_diagnostics", False)
        p._cfg_bool("enable_integrated_self_state", True)
        p._cfg_bool("allow_relational_self_public_export", False)
        p._cfg_bool("integrated_self_memory_write_enabled", True)
        p._cfg("integrated_self_degradation_profile", "balanced")
        p._cfg_bool("sylanne_alpha_auto_detect_group_context", True)

    # ------------------------------------------------------------------
    # AstrBot group context detection
    # ------------------------------------------------------------------

    def detect_astrbot_group_context(self) -> bool:
        """Detect if AstrBot's built-in group chat context awareness is enabled."""
        p = self._p
        if not p._cfg_bool("sylanne_alpha_auto_detect_group_context", True):
            return False
        try:
            context = getattr(p, "context", None)
            if context is None:
                return False
            # Method 1: AstrBot Context.get_config()
            get_config_fn = getattr(context, "get_config", None)
            if callable(get_config_fn):
                cfg = get_config_fn()
                if isinstance(cfg, dict):
                    if cfg.get("enable_group_context") or cfg.get(
                        "group_context_enabled"
                    ):
                        return True
            # Method 2: Check platform_settings on context
            platform_settings = getattr(context, "platform_settings", None)
            if isinstance(platform_settings, dict):
                if platform_settings.get(
                    "group_context_enabled"
                ) or platform_settings.get("enable_group_context"):
                    return True
            # Method 3: Check context._config or context.config_manager
            config_mgr = getattr(context, "config_manager", None)
            if config_mgr is not None:
                global_cfg = getattr(config_mgr, "config", None)
                if isinstance(global_cfg, dict):
                    if global_cfg.get("enable_group_context") or global_cfg.get(
                        "group_context_enabled"
                    ):
                        return True
        except Exception:
            pass  # cleanup: config introspection failure acceptable
        return False

    # ------------------------------------------------------------------
    # Terminate / cleanup
    # ------------------------------------------------------------------

    async def terminate(self) -> None:
        """Graceful shutdown: cancel tasks, save checkpoints, clean up state."""
        p = self._p
        task = getattr(p, "_proactive_scheduler_task", None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        p._proactive_scheduler_task = None
        p._proactive_candidate_sessions = {}
        p._proactive_scheduler_locks = {}
        # Cancel all background tasks
        tasks = getattr(p, "_background_tasks", [])
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
        p._background_tasks = []
        # Save final checkpoints for background post queues
        bg_queues = p._background_post_queues
        checkpoint_enabled = bool(
            (p.config or {}).get("background_post_queue_checkpoint_enabled")
        )
        recovered = p._background_post_recovered_sessions
        if checkpoint_enabled:
            for sk in list(bg_queues.keys()):
                if sk in recovered or bg_queues.get(sk):
                    try:
                        await p._save_background_post_checkpoint(sk)
                    except Exception:
                        pass
        # Clean up background post state
        p._background_post_tasks = {}
        p._background_post_queues = {}
        p._background_post_sequence = {}
        p._background_post_skipped = {}
        p._terminating = True
        try:
            from sylanne_alpha.webui_server import stop_webui_server

            await stop_webui_server()
        except Exception:
            pass
