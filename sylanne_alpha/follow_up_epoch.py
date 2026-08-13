"""Bridge AstrBot active-runner follow-ups to scoped delivery epochs.

AstrBot can absorb a new wake message into a running tool turn. Sylanne must
not fence the older reply until AstrBot has declined that capture. This module
contains only a no-write eligibility probe and event-extra compatibility reads.
"""

from __future__ import annotations

import logging
import time
from typing import Any

try:
    from astrbot.api import logger
except ImportError:  # pragma: no cover - standalone import fallback
    logger = logging.getLogger("astrbot_plugin_sylanne")


def event_extra(event: Any, key: str, default: Any = None) -> Any:
    """Read both AstrBot's one-argument API and permissive test doubles."""

    get_extra = getattr(event, "get_extra", None)
    if not callable(get_extra):
        return default
    try:
        value = get_extra(key)
    except TypeError:
        try:
            value = get_extra(key, default)
        except Exception:
            return default
    except Exception:
        return default
    return default if value is None else value


def register_inbound_event_once(plugin: Any, event: Any) -> bool:
    """Claim one compatibility-host event; return False for a duplicate delivery.

    The production scoped ingress has a Bot-bound duplicate fence in ``main``.
    This narrow helper remains for registry-free historical hosts and the PR #70
    follow-up bridge, which carry only their original event ownership markers.
    """

    if bool(event_extra(event, "_syl_inbound_registered", False)):
        return False

    set_extra = getattr(event, "set_extra", None)
    duplicate = False
    key = ""
    seen: Any = None
    registered_new = False
    try:
        umo = str(getattr(event, "unified_msg_origin", "") or "")
        mid = getattr(getattr(event, "message_obj", None), "message_id", None)
        key = (
            umo + "\x00" + mid
            if umo and isinstance(mid, str) and mid.strip()
            else ""
        )
        seen = getattr(plugin, "_inbound_seen", None)
        if key and seen is not None and callable(set_extra):
            duplicate = key in seen
            if not duplicate:
                seen[key] = time.time()
                registered_new = True
    except Exception:
        logger.warning(
            "Sylanne inbound epoch registration failed open",
            exc_info=True,
        )

    if callable(set_extra):
        try:
            set_extra("_syl_inbound_duplicate", duplicate)
            set_extra("_syl_inbound_registered", True)
        except Exception:
            if registered_new and not bool(
                event_extra(event, "_syl_inbound_registered", False)
            ):
                try:
                    seen.pop(key, None)
                except Exception:
                    pass
    return not duplicate


def active_follow_up_target(event: Any) -> tuple[bool, str]:
    """Mirror AstrBot follow-up eligibility without consuming the event.

    Sender values are compared only in local variables; they are never persisted
    or used to choose a Sylanne scope. AstrBot remains the sole owner of the
    real follow-up capture operation.
    """

    # Normal messages must never touch raw sender identity during on_message.
    # True candidates still follow AstrBot's same-sender check below.
    if not bool(getattr(event, "is_at_or_wake_command", False)):
        return False, ""
    try:
        from astrbot.core.pipeline.process_stage.follow_up import (
            _ACTIVE_AGENT_RUNNERS,
        )
    except ImportError:
        return False, ""
    try:
        sender_getter = getattr(event, "get_sender_id", None)
        sender_id = str(sender_getter() or "") if callable(sender_getter) else ""
        umo = str(getattr(event, "unified_msg_origin", "") or "")
        if not sender_id or not umo:
            return False, ""

        runner = _ACTIVE_AGENT_RUNNERS.get(umo)
        if runner is None:
            return False, ""
        done = getattr(runner, "done", None)
        if callable(done) and done():
            return False, ""

        run_context = getattr(runner, "run_context", None)
        runner_event = getattr(getattr(run_context, "context", None), "event", None)
        active_sender_getter = getattr(runner_event, "get_sender_id", None)
        active_sender_id = (
            str(active_sender_getter() or "")
            if callable(active_sender_getter)
            else ""
        )
        if not active_sender_id or active_sender_id != sender_id:
            return False, ""
        if bool(event_extra(runner_event, "agent_stop_requested", False)):
            return False, ""

        target_mid = getattr(
            getattr(runner_event, "message_obj", None),
            "message_id",
            None,
        )
        return True, str(target_mid) if target_mid is not None else ""
    except Exception:
        logger.warning(
            "Sylanne follow-up eligibility probe failed; treating inbound as new",
            exc_info=True,
        )
        return False, ""


def commit_inbound_delivery_epoch(
    plugin: Any,
    event: Any,
    session_key: str,
    *,
    reason: str,
) -> int:
    """Commit one registry-free inbound turn and interrupt an older delivery."""

    if bool(event_extra(event, "_syl_input_epoch_committed", False)):
        value = event_extra(event, "_syl_input_epoch", 0)
        return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0

    epochs = getattr(plugin._store, "conversation_input_epoch", None)
    input_epoch = 0
    if epochs is not None:
        try:
            input_epoch = int(epochs.get(session_key, 0) or 0) + 1
            epochs.set(session_key, input_epoch)
        except Exception:
            logger.warning(
                "Sylanne inbound epoch advance failed: session=%s",
                session_key,
                exc_info=True,
            )
            input_epoch = 0

    set_extra = getattr(event, "set_extra", None)
    if callable(set_extra):
        try:
            set_extra("_syl_input_epoch", input_epoch)
            set_extra("_syl_input_epoch_committed", True)
            set_extra("_syl_follow_up_deferred", False)
        except Exception:
            pass

    active_turns = getattr(plugin._store, "segmented_delivery_turns", None)
    if active_turns is None:
        return input_epoch
    try:
        turn = active_turns.get(session_key)
        interrupt = getattr(turn, "interrupt", None)
        if callable(interrupt):
            interrupt()
            logger.info(
                "Sylanne confirmed older reply interruption: "
                "session=%s epoch=%d reason=%s",
                session_key,
                input_epoch,
                reason,
            )
    except Exception:
        logger.warning(
            "Sylanne active delivery interrupt failed: session=%s",
            session_key,
            exc_info=True,
        )
    return input_epoch


def advance_inbound_delivery_epoch(plugin: Any, event: Any, session_key: str) -> None:
    """Immediately commit a real compatibility-host inbound message."""

    if register_inbound_event_once(plugin, event):
        commit_inbound_delivery_epoch(
            plugin,
            event,
            session_key,
            reason="new_inbound",
        )


def register_or_defer_inbound_delivery_epoch(
    plugin: Any,
    event: Any,
    session_key: str,
) -> None:
    """Defer a capturable follow-up until AstrBot resolves its ownership."""

    if not register_inbound_event_once(plugin, event):
        return

    is_follow_up, target_run_id = active_follow_up_target(event)
    if not is_follow_up:
        commit_inbound_delivery_epoch(
            plugin,
            event,
            session_key,
            reason="new_inbound",
        )
        return

    epochs = getattr(plugin._store, "conversation_input_epoch", None)
    current_epoch = 0
    if epochs is not None:
        try:
            current_epoch = int(epochs.get(session_key, 0) or 0)
        except Exception:
            current_epoch = 0

    set_extra = getattr(event, "set_extra", None)
    if callable(set_extra):
        try:
            set_extra("_syl_input_epoch", current_epoch)
            set_extra("_syl_input_epoch_committed", False)
            set_extra("_syl_follow_up_deferred", True)
            set_extra("_syl_follow_up_target_run_id", target_run_id)
            if not bool(event_extra(event, "_syl_follow_up_deferred", False)):
                raise RuntimeError("follow-up marker did not round-trip")
        except Exception:
            commit_inbound_delivery_epoch(
                plugin,
                event,
                session_key,
                reason="follow_up_marker_failed",
            )
    else:
        commit_inbound_delivery_epoch(
            plugin,
            event,
            session_key,
            reason="follow_up_marker_unavailable",
        )


__all__ = [
    "active_follow_up_target",
    "advance_inbound_delivery_epoch",
    "commit_inbound_delivery_epoch",
    "event_extra",
    "register_inbound_event_once",
    "register_or_defer_inbound_delivery_epoch",
]
