"""Bridge AstrBot active-runner follow-ups to scoped delivery epochs.

AstrBot can absorb a new wake message into a running tool turn. Sylanne must
not fence the older reply until AstrBot has declined that capture. This module
contains only a no-write eligibility probe and event-extra compatibility reads.
"""

from __future__ import annotations

import logging
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


__all__ = [
    "active_follow_up_target",
    "event_extra",
]
