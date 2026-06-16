"""Wave 2 Tier 收口：后门默认关、主动时间戳对齐、工具消毒。"""

from __future__ import annotations

import asyncio

from sylanne_alpha.proactive_scheduler import ProactiveScheduler
from sylanne_alpha.public_api import PublicAPI
from sylanne_alpha.session_state_store import SessionStateStore


def test_emotion_reset_backdoor_default_off() -> None:
    class _P:
        config = {}

        def _session_key(self, event=None, session_key: str = "") -> str:  # noqa: ANN001
            return session_key or "s"

    api = PublicAPI(_P())  # type: ignore[arg-type]

    async def go() -> str:
        chunks = []
        async for c in api.emotion_reset():
            chunks.append(str(c))
        return "".join(chunks)

    msg = asyncio.run(go())
    assert "已关闭" in msg


def test_proactive_scheduler_reads_store_timestamp() -> None:
    class _P:
        _store = SessionStateStore()

    p = _P()
    p._store.last_user_message_time.set("sess/a", 1000.0)
    sched = ProactiveScheduler(p)  # type: ignore[arg-type]
    assert sched._last_user_ts("sess/a") == 1000.0


def test_dispatch_tool_yields_tool_json_shape() -> None:
    class _P:
        config = {}

        async def request_proactive_speech_dispatch(self, event=None, dry_run=True):  # noqa: ANN001
            return {"dispatched": False, "dry_run": dry_run, "reason": "test"}

    api = PublicAPI(_P())  # type: ignore[arg-type]

    async def go() -> str:
        chunks = []
        async for c in api.request_bot_proactive_speech_dispatch_tool():
            chunks.append(str(c))
        return "".join(chunks)

    raw = asyncio.run(go())
    assert raw.startswith("{")
    assert "proactive_speech_dispatch" in raw or "dispatched" in raw
    assert "note" in raw  # _tool_json 消毒附注
