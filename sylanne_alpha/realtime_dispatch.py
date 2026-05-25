"""Sylanne-Embodiment: Realtime chat dispatch logic.

Extracted from main.py to isolate realtime delivery, history shadow,
interrupted-reply breakpoints, and active dispatch context injection.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    pass  # plugin type is dynamic (Star subclass)

_CHINA_TZ = timezone(timedelta(hours=8))


class RealtimeDispatch:
    """Handles realtime chat delivery, segmented dispatch, and context injection."""

    def __init__(self, plugin: Any) -> None:
        self._p = plugin

    # ------------------------------------------------------------------
    # Segmented dispatch helpers
    # ------------------------------------------------------------------

    def extract_first_sentence(self, text: str) -> str:
        """Extract first complete sentence from buffer."""
        delimiters = "。！？!?；;"
        for i, ch in enumerate(text):
            if ch in delimiters and i > 0:
                if i + 1 < len(text) and text[i + 1] in delimiters:
                    continue
                return text[: i + 1]
            if ch == "\n" and i > 0:
                return text[:i]
        return ""

    async def send_first_sentence(self, origin: str, text: str) -> None:
        context = self._p.context
        if hasattr(context, "send_message"):
            message = self._p._astrbot_message(text)
            await context.send_message(origin, message)

    async def dispatch_segmented_parts(
        self, origin: str, parts: list[dict[str, Any]], session_key: str = ""
    ) -> None:
        context = self._p.context
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
            self._p.logger.info(
                f"Sylanne segmented reply part {idx}/{total}: {text[:60]}"
            )
            message = self._p._astrbot_message(text)
            await context.send_message(origin, message)
        # All parts sent successfully — clear unfinished marker
        if session_key:
            self._p._unfinished_replies.pop(session_key, None)

    # ------------------------------------------------------------------
    # Realtime chat plan delivery
    # ------------------------------------------------------------------

    async def send_realtime_chat_plan(
        self,
        event: Any,
        plan: dict[str, Any],
        *,
        source: str = "",
        record_history_shadow: bool = False,
    ) -> dict[str, Any]:
        p = self._p
        session_key = plan.get("session_key") or p._session_key(event)
        plan_epoch = plan.get("input_epoch", 0)
        parts = plan.get("message_parts", [])
        media_parts = plan.get("media_parts", [])
        message_count = 0
        media_count = 0
        media_results: list[dict[str, Any]] = []
        interrupted_reason = ""
        epochs = p._conversation_input_epoch

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
            send_fn = getattr(p, "_send_segmented_reply", None)
            if send_fn and callable(send_fn):
                await send_fn(event, text, source=source)
            else:
                reply_fn = getattr(p, "_reply", None)
                if reply_fn and callable(reply_fn):
                    await reply_fn(event, text)
                else:
                    context = getattr(p, "context", None)
                    if context and hasattr(context, "send_message"):
                        origin = str(
                            getattr(event, "unified_msg_origin", "") or session_key
                        )
                        msg = p._build_astrbot_message_chain(text)
                        await context.send_message(origin, msg)
            message_count += 1

        for media in media_parts:
            kind = media.get("kind", "")
            value = media.get("value", "")
            try:
                context = getattr(p, "context", None)
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
                                origin = str(
                                    getattr(event, "unified_msg_origin", "")
                                    or session_key
                                )
                                await context.send_message(origin, chain)
                                media_count += 1
                                media_results.append(
                                    {"kind": kind, "value": value, "sent": True}
                                )
                                continue
                    media_results.append(
                        {
                            "kind": kind,
                            "value": value,
                            "blocked_reason": "missing_local_media_file",
                        }
                    )
                else:
                    media_results.append(
                        {
                            "kind": kind,
                            "value": value,
                            "blocked_reason": "missing_local_media_file",
                        }
                    )
            except (FileNotFoundError, OSError):
                media_results.append(
                    {
                        "kind": kind,
                        "value": value,
                        "blocked_reason": "missing_local_media_file",
                    }
                )

        if interrupted_reason:
            sent_parts = [pt.get("text", "") for pt in parts[:message_count]]
            unsent_parts = [pt.get("text", "") for pt in parts[message_count:]]
            self.record_interrupted_reply_breakpoint(
                session_key,
                full_text=plan.get("full_text", ""),
                sent_parts=sent_parts,
                unsent_parts=unsent_parts,
                input_epoch=plan_epoch,
                reason=interrupted_reason,
            )
            dispatches = p._realtime_chat_active_dispatches
            dispatches[session_key] = [
                {
                    "sent_parts": sent_parts,
                    "unsent_parts": unsent_parts,
                    "interrupted_reason": interrupted_reason,
                }
            ]

        if record_history_shadow and message_count > 0:
            full_text = plan.get("full_text", "")
            if not full_text:
                full_text = " ".join(pt.get("text", "") for pt in parts[:message_count])
            self.record_realtime_ordinary_history_backfill(
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

    # ------------------------------------------------------------------
    # Recording helpers
    # ------------------------------------------------------------------

    def record_realtime_assistant_history_shadow(
        self,
        session_key: str,
        *,
        full_text: str = "",
        input_epoch: int = 0,
        message_parts: list[dict[str, Any]] | None = None,
        source: str = "",
        event_time: dict[str, Any] | None = None,
        delivery_status: str = "",
    ) -> None:
        p = self._p
        if not hasattr(p, "_realtime_assistant_history_shadows"):
            p._realtime_assistant_history_shadows: dict[str, list[dict[str, Any]]] = {}
        shadows = p._realtime_assistant_history_shadows.setdefault(session_key, [])
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

    def record_interrupted_reply_breakpoint(
        self,
        session_key: str,
        *,
        full_text: str = "",
        sent_parts: list[str] | None = None,
        unsent_parts: list[str] | None = None,
        input_epoch: int = 0,
        reason: str = "",
        event_time: dict[str, Any] | None = None,
        source: str = "",
    ) -> None:
        p = self._p
        if not hasattr(p, "_interrupted_reply_breakpoints"):
            p._interrupted_reply_breakpoints: dict[str, list[dict[str, Any]]] = {}
        bps = p._interrupted_reply_breakpoints.setdefault(session_key, [])
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

    def realtime_delivery_context_kv_key(self, session_key: str) -> str:
        return f"sylanne:realtime_delivery_context:{session_key}"

    def record_realtime_ordinary_history_backfill(
        self,
        session_key: str,
        *,
        role: str = "",
        content: str = "",
        input_epoch: int = 0,
        source: str = "",
        delivery_status: str = "",
    ) -> None:
        p = self._p
        if not hasattr(p, "_realtime_ordinary_history_backfills"):
            p._realtime_ordinary_history_backfills: dict[str, list[dict[str, Any]]] = {}
        entries = p._realtime_ordinary_history_backfills.setdefault(session_key, [])
        entries.append(
            {
                "role": role,
                "content": content,
                "input_epoch": input_epoch,
                "source": source,
            }
        )

    def record_active_agent_pending_user_turn(
        self,
        session_key: str,
        identity: Any = None,
        *,
        input_epoch: int = 0,
        text: str = "",
        observed_at: float = 0.0,
    ) -> None:
        p = self._p
        if not hasattr(p, "_active_agent_pending_user_turns"):
            p._active_agent_pending_user_turns: dict[str, list[dict[str, Any]]] = {}
        turns = p._active_agent_pending_user_turns.setdefault(session_key, [])
        turns.append(
            {
                "input_epoch": input_epoch,
                "text": text,
                "observed_at": observed_at,
                "identity": identity,
            }
        )

    # ------------------------------------------------------------------
    # Cache accessors
    # ------------------------------------------------------------------

    def realtime_assistant_history_shadow_cache(
        self,
    ) -> dict[str, list[dict[str, Any]]]:
        p = self._p
        if not hasattr(p, "_realtime_assistant_history_shadows"):
            p._realtime_assistant_history_shadows: dict[str, list[dict[str, Any]]] = {}
        return p._realtime_assistant_history_shadows

    def realtime_ordinary_history_backfill_cache(
        self,
    ) -> dict[str, list[dict[str, Any]]]:
        p = self._p
        if not hasattr(p, "_realtime_ordinary_history_backfills"):
            p._realtime_ordinary_history_backfills: dict[str, list[dict[str, Any]]] = {}
        return p._realtime_ordinary_history_backfills

    # ------------------------------------------------------------------
    # Context injection (append_*_if_any)
    # ------------------------------------------------------------------

    def append_realtime_assistant_history_shadow_if_any(
        self,
        request: Any,
        session_key: str,
        *,
        budget: Any = None,
        current_user_text: str = "",
    ) -> bool:
        cache = self.realtime_assistant_history_shadow_cache()
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
            event_time_line = (
                f"\nevent_local_time="
                f"{event_time.get('event_local_time', event_time.get('local_datetime', ''))}"
                f"\ntimezone={event_time.get('timezone', '')}"
            )
        prompt = str(getattr(request, "prompt", "") or "")
        request.prompt = (
            prompt
            + "\n[sylanne_realtime_assistant_history]"
            + event_time_line
            + "\n"
            + full_text
        )
        last["consumed"] = True
        last["consumed_reason"] = "injected"
        return True

    def append_interrupted_reply_breakpoint_if_any(
        self,
        request: Any,
        session_key: str,
        *,
        budget: Any = None,
    ) -> bool:
        bps = getattr(self._p, "_interrupted_reply_breakpoints", {})
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
            event_time_line = (
                f"\nevent_local_time="
                f"{event_time.get('event_local_time', event_time.get('local_datetime', ''))}"
                f"\ntimezone={event_time.get('timezone', '')}"
            )
        prompt = str(getattr(request, "prompt", "") or "")
        request.prompt = (
            prompt
            + "\n[sylanne_interrupted_reply_breakpoint]"
            + event_time_line
            + "\n"
            + full_text
        )
        last["consumed"] = True
        return True

    def build_realtime_delivery_envelope_text(
        self,
        text: str,
        *,
        session_key: str = "",
        input_epoch: int = 0,
        message_parts: list[dict[str, Any]] | None = None,
        event_time: dict[str, Any] | None = None,
    ) -> str:
        lines = ["[sylanne_realtime_delivery_envelope]"]
        if event_time:
            lines.append(
                f"event_local_time="
                f"{event_time.get('event_local_time', event_time.get('local_datetime', ''))}"
            )
            lines.append(f"timezone={event_time.get('timezone', '')}")
        lines.append(f"text={text}")
        lines.append(
            "note=realtime segmented delivery disabled or removed in alpha host"
        )
        return "\n".join(lines)

    def start_realtime_chat_active_dispatch(
        self,
        session_key: str,
        *,
        input_epoch: int = 0,
        full_text: str = "",
        source: str = "",
        event_time: dict[str, Any] | None = None,
    ) -> None:
        p = self._p
        if not hasattr(p, "_realtime_chat_active_dispatches"):
            p._realtime_chat_active_dispatches: dict[str, list[dict[str, Any]]] = {}
        dispatches = p._realtime_chat_active_dispatches.setdefault(session_key, [])
        entry: dict[str, Any] = {
            "input_epoch": input_epoch,
            "full_text": full_text,
            "source": source,
        }
        if event_time:
            entry["event_time"] = event_time
        dispatches.append(entry)

    def append_realtime_chat_active_dispatch_if_any(
        self,
        request: Any,
        session_key: str,
        *,
        budget: Any = None,
    ) -> bool:
        dispatches = self._p._realtime_chat_active_dispatches
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
            event_time_line = (
                f"\ntrigger_event_local_time="
                f"{event_time.get('event_local_time', event_time.get('local_datetime', ''))}"
                f"\ntrigger_timezone={event_time.get('timezone', '')}"
            )
        prompt = str(getattr(request, "prompt", "") or "")
        request.prompt = (
            prompt
            + "\n[sylanne_realtime_chat_active_dispatch]"
            + event_time_line
            + "\n"
            + full_text
        )
        last["consumed"] = True
        return True

    def append_realtime_continuity_context_if_any(
        self,
        request: Any,
        session_key: str,
        *,
        budget: Any = None,
        current_user_text: str = "",
    ) -> bool:
        cache = self.realtime_assistant_history_shadow_cache()
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
                + "上一轮 bot 刚提出了一个未闭合问题："
                + full_text
                + "\n"
                + "current_user_short_answer="
                + current_user_text
            )
            request.prompt = prompt + "\n" + injection
            return True
        return False

    def append_realtime_ordinary_history_backfills_if_any(
        self, request: Any, session_key: str = "", **kwargs: Any
    ) -> bool:
        backfills = self._p._realtime_ordinary_history_backfills
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
            request.prompt = f"{current}\n[sylanne_backfill_context]\n" + "\n".join(
                parts
            )
        backfills[session_key] = []
        return True

    # ------------------------------------------------------------------
    # Release / cleanup
    # ------------------------------------------------------------------

    async def release_realtime_temporary_context_after_background_post(
        self,
        session_key: str,
        *,
        input_epoch: int = 0,
        reason: str = "",
    ) -> None:
        cache = self.realtime_assistant_history_shadow_cache()
        shadows = cache.get(session_key, [])
        for shadow in shadows:
            if shadow.get("input_epoch") == input_epoch and not shadow.get("consumed"):
                shadow["consumed"] = True
                shadow["consumed_reason"] = reason
                break
        backfills = self.realtime_ordinary_history_backfill_cache()
        backfills.pop(session_key, None)

    def release_realtime_temporary_context_after_background_post_in_memory(
        self,
        session_key: str,
        *,
        input_epoch: int | None = 0,
        reason: str = "",
    ) -> bool:
        if input_epoch is None:
            return False
        cache = self.realtime_assistant_history_shadow_cache()
        shadows = cache.get(session_key, [])
        changed = False
        for shadow in shadows:
            if shadow.get("input_epoch") == input_epoch and not shadow.get("consumed"):
                shadow["consumed"] = True
                shadow["consumed_reason"] = reason
                changed = True
                break
        if changed:
            backfills = self.realtime_ordinary_history_backfill_cache()
            if session_key in backfills:
                backfills[session_key] = {
                    k: v for k, v in backfills[session_key].items() if k > input_epoch
                }
                if not backfills[session_key]:
                    del backfills[session_key]
        return changed

    # ------------------------------------------------------------------
    # Realtime input/response helpers
    # ------------------------------------------------------------------

    def build_realtime_input_completion_prompt(
        self, session_key: str = "", text: str = "", **kwargs: Any
    ) -> str:
        return text

    def extract_realtime_response_media_parts(self, response: Any = None) -> list[Any]:
        return []

    def build_group_atmosphere_injection_for_session(
        self, session_key: str = "", state: Any = None, **kwargs: Any
    ) -> str:
        p = self._p
        if state is None:
            return ""
        cache = p._group_atmosphere_injection_snapshot_cache
        previous = cache.get(session_key)
        cfg = p.config or {}
        diff_mode = str(cfg.get("state_injection_compact_mode", "")).lower() == "diff"
        values = getattr(state, "values", {}) if state else {}
        if diff_mode and previous is not None:
            threshold = float(
                cfg.get("group_atmosphere_injection_diff_threshold", 0.08)
            )
            prev_values = previous.get("values", {})
            max_delta = (
                max(abs(values.get(k, 0) - prev_values.get(k, 0)) for k in values)
                if values
                else 0
            )
            if max_delta < threshold:
                return '<bot_group_atmosphere detail="diff">No material room-mood change since last injection.</bot_group_atmosphere>'
        snapshot = {"values": dict(values)}
        cache[session_key] = snapshot
        if not hasattr(p, "_group_atmosphere_injection_snapshot_cache"):
            p._group_atmosphere_injection_snapshot_cache = {}
        p._group_atmosphere_injection_snapshot_cache[session_key] = snapshot
        lines = ["<bot_group_atmosphere>"]
        for k, v in values.items():
            lines.append(f"  {k}={v:.2f}" if isinstance(v, float) else f"  {k}={v}")
        lines.append("</bot_group_atmosphere>")
        return "\n".join(lines)

    def context_item_to_text(self, item: Any) -> str:
        if isinstance(item, dict):
            return str(item.get("content", "") or item.get("text", ""))
        if hasattr(item, "text"):
            return str(item.text)
        if hasattr(item, "content"):
            return str(item.content)
        return str(item)

    def conversation_time_payload(
        self, session_key_or_timestamp: Any = "", *, event: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        ts = None
        if (
            isinstance(session_key_or_timestamp, (int, float))
            and session_key_or_timestamp > 1000000000
        ):
            ts = datetime.fromtimestamp(session_key_or_timestamp, tz=_CHINA_TZ)
        elif event is not None and hasattr(event, "timestamp") and event.timestamp:
            ts = datetime.fromtimestamp(event.timestamp, tz=_CHINA_TZ)
        if ts is None:
            ts = datetime.now(_CHINA_TZ)
        offset_str = ts.strftime("%z")
        offset_formatted = (
            f"{offset_str[:3]}:{offset_str[3:]}" if len(offset_str) == 5 else offset_str
        )
        return {
            "local_time": ts.strftime("%H:%M:%S"),
            "local_date": ts.strftime("%Y-%m-%d"),
            "local_datetime": f"{ts.strftime('%Y-%m-%d %H:%M:%S')} {offset_formatted}",
            "timezone": "Asia/Shanghai",
            "event_local_time": f"{ts.strftime('%Y-%m-%d %H:%M:%S')} {offset_formatted}",
        }

    def napcat_recall_payload(self, event: Any = None) -> dict[str, Any]:
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

    async def observe_stickers_background(
        self, event: Any = None, stickers: Any = None, **kwargs: Any
    ) -> None:
        pass

    def extract_sticker_observations_from_event(
        self, event: Any = None
    ) -> list[dict[str, Any]]:
        return []

    def fast_assessor_max_context_chars(self) -> int:
        p = self._p
        return p._cfg_int("fast_assessor_max_context_chars", 240)

    def discard_conversation_pending_response_epoch(
        self, session_key: str, epoch: int = 0
    ) -> None:
        p = self._p
        epochs = p._conversation_pending_response_epochs
        if epochs and session_key in epochs:
            del epochs[session_key]

    def conversation_reply_is_stale(self, session_key: str, reply_epoch: int) -> bool:
        p = self._p
        epochs = p._conversation_input_epoch
        current = epochs.get(session_key, 0)
        return reply_epoch < current

    # ------------------------------------------------------------------
    # Background task scheduling
    # ------------------------------------------------------------------

    def schedule_background_task(self, coro: Any, *, label: str = "") -> Any:
        p = self._p

        async def _wrapper() -> None:
            try:
                await coro
            except asyncio.CancelledError:
                pass
            except Exception as e:
                import logging

                logging.getLogger("astrbot_plugin_sylanne").error(
                    f"Background task '{label or 'background_task'}' failed: {e}",
                    exc_info=True,
                )

        task = asyncio.ensure_future(_wrapper())
        p._background_tasks.append(task)
        task.add_done_callback(
            lambda t: (
                p._background_tasks.remove(t) if t in p._background_tasks else None
            )
        )
        return task

    def ensure_runtime_state_containers(self) -> None:
        p = self._p
        if not hasattr(p, "_sylanne_memory_pending_observations"):
            p._sylanne_memory_pending_observations: dict[str, Any] = {}
        if not hasattr(p, "_sylanne_memory_idle_generation"):
            p._sylanne_memory_idle_generation: dict[str, int] = {}

    def build_astrbot_message_chain(self, text: str = "", **kwargs: Any) -> Any:
        import sys

        p = self._p
        event_mod = sys.modules.get("astrbot.api.event")
        if event_mod:
            _Chain = getattr(event_mod, "MessageChain", None)
            if _Chain:
                chain = _Chain()
                if hasattr(chain, "message") and callable(chain.message):
                    chain.message(text)
                    return chain
        return p._astrbot_message(text)

    async def on_waiting_llm_request(self, event: Any, **kwargs: Any) -> None:
        pass
