"""Wave 1/2 live 接线：bot buffer、mark_dirty KV、proactive_sylanne reach、request_dispatch。"""

from __future__ import annotations

import asyncio
import tempfile
import time

from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost
from sylanne_alpha.llm_response_pipeline import LLMResponsePipeline
from sylanne_alpha.memory_system import ConversationBuffer
from sylanne_alpha.session_state_store import SessionStateStore
from sylanne_alpha.state_persistence import StatePersistence
from sylanne_alpha.v2core import integration as ig


class _Resp:
    def __init__(self, t: str) -> None:
        self.completion_text = t


class _Ev:
    unified_msg_origin = "sess:wave1"


class _BufferPlugin:
    """非 realtime 拦截路径：bot 回复仍应进 conversation_buffers。"""

    def __init__(self, root: str) -> None:
        self._config = {
            "sylanne_alpha_realtime_chat_enabled": False,
            "sylanne_alpha_realtime_intercept_llm_response": False,
        }
        self._store = SessionStateStore()
        self._background_tasks: list = []
        self._root = root
        self._h: dict = {}
        self.logger = __import__("logging").getLogger("test")

    def _session_key(self, _e: object) -> str:
        return "sess:wave1"

    def _host(self, sk: str) -> SylanneAlphaHost:
        if sk not in self._h:
            self._h[sk] = SylanneAlphaHost(root=self._root, session_key=sk)
        return self._h[sk]

    def _has_conversation_manager(self) -> bool:
        return False

    def _schedule_buffer_persist(self, _sk: str) -> None:
        pass


def test_non_intercept_path_appends_bot_buffer() -> None:
    """T1-3：拦截关时 early return 仍写入 conversation_buffers（不 double tick）。"""
    p = _BufferPlugin(tempfile.mkdtemp(prefix="w1_buf_"))
    pipe = LLMResponsePipeline(p)  # type: ignore[arg-type]
    resp = _Resp("嗯，我在呢。")

    async def go() -> None:
        await pipe._on_llm_response_inner(_Ev(), resp)
        if p._background_tasks:
            await asyncio.gather(*p._background_tasks)

    asyncio.run(go())
    buf = p._store.conversation_buffers.get("sess:wave1")
    assert buf is not None, "非 intercept 路径未写入 conversation_buffers"
    assert any(m.get("role") == "bot" and "我在" in m.get("text", "") for m in buf.messages)


class _KVPlugin:
    _config: dict = {}

    def __init__(self) -> None:
        self._kv: dict = {}

    async def get_kv_data(self, key: str, default=None):  # noqa: ANN001
        return self._kv.get(key, default)

    async def put_kv_data(self, key: str, value) -> None:  # noqa: ANN001
        self._kv[key] = value

    async def delete_kv_data(self, key: str) -> None:
        self._kv.pop(key, None)


def test_default_persistence_binds_all_plugin_kv_callbacks() -> None:
    """Default construction retains the host's complete KV callback contract."""
    plugin = _KVPlugin()
    persistence = StatePersistence(plugin)  # type: ignore[arg-type]

    assert persistence.has_kv_api()
    assert persistence._services.put_kv_data == plugin.put_kv_data
    assert persistence._services.get_kv_data == plugin.get_kv_data
    assert persistence._services.delete_kv_data == plugin.delete_kv_data


def test_mark_dirty_triggers_kv_partial_write() -> None:
    """T0-2：mark_dirty('memory') 后 persist_kernel 写 KV 增量快照。"""
    root = tempfile.mkdtemp(prefix="w1_dirty_")
    p = _KVPlugin()
    sp = StatePersistence(p)  # type: ignore[arg-type]
    host = SylanneAlphaHost(root=root, session_key="sess:dirty")
    host.kernel.body.memory["_memory_system"] = {"tick": 1, "items": []}
    sp.swap_dirty()
    sp.mark_dirty("memory")

    async def go() -> None:
        await sp.persist_kernel("sess:dirty", host)

    asyncio.run(go())
    keys = [k for k in p._kv if "kernel" in k and "backup" not in k]
    assert keys, "mark_dirty 后 KV 仍无写入"
    blob = p._kv[keys[0]]
    assert "memory" in blob.get("_dirty_subsystems", []) or "body" in blob


def test_proactive_sylanne_merges_idle_reach() -> None:
    """T1-8 live：proactive_sylanne 在 reach 胜出时升格 action=reach_out。"""
    from sylanne_alpha.public_api import PublicAPI

    root = tempfile.mkdtemp(prefix="w1_reach_")

    class _P:
        config = {"sylanne_enable_v2core": True}
        _config = config
        _observed_now = staticmethod(lambda: time.time())

        def __init__(self) -> None:
            self._h: dict = {}

        def _host(self, sk: str) -> SylanneAlphaHost:
            if sk not in self._h:
                self._h[sk] = SylanneAlphaHost(root=root, session_key=sk)
            return self._h[sk]

        def _session_key(self, _e: object) -> str:
            return "sess:fw"

        def _event_time(self, _now: float) -> dict:
            return {}

        async def get_kv_data(self, key, default=None):  # noqa: ANN001
            return None

        async def put_kv_data(self, key, value) -> None:  # noqa: ANN001
            pass

    p = _P()
    ig._runtime_for(p, "sess:fw")
    p._host("sess:fw").on_request({"phase": "request", "text": "x", "now": 1.0})

    async def go() -> dict:
        rt = ig._runtime_for(p, "sess:fw")
        rt["loaded"] = True
        import time as _t

        rt["domains"]["emotion"].load_dict({"unexpressed": 3.0})
        rt["domains"]["usermodel"].load_dict({
            "rhythm_ema": 10.0,
            "last_user_ts": _t.time() - 1000.0,
        })
        api = PublicAPI(p)  # type: ignore[arg-type]
        return await api.proactive_sylanne(session_key="sess:fw")

    out = asyncio.run(go())
    decision = out.get("decision", {})
    assert decision.get("v2core_reach", {}).get("reach") is True
    if decision.get("allowed", True):
        assert decision["action"] == "reach_out"


def test_request_dispatch_dry_run_reports_would_dispatch() -> None:
    """request_dispatch dry_run 在 reach 胜出时返回 would_dispatch。"""
    from sylanne_alpha.proactive_scheduler import ProactiveScheduler

    root = tempfile.mkdtemp(prefix="w1_disp_")

    class _P:
        config = {
            "sylanne_enable_v2core": True,
            "enable_proactive_speech_dispatch": True,
        }
        _config = config
        _observed_now = staticmethod(lambda: time.time())
        _proactive_dispatch_last_sent: dict = {}

        def __init__(self) -> None:
            self._h: dict = {}
            from sylanne_alpha.session_state_store import SessionStateStore

            self._store = SessionStateStore()

        def _host(self, sk: str) -> SylanneAlphaHost:
            if sk not in self._h:
                self._h[sk] = SylanneAlphaHost(root=root, session_key=sk)
            return self._h[sk]

    p = _P()
    p._host("sess:fw").on_request({"phase": "request", "text": "x", "now": 1.0})

    async def go() -> dict:
        rt = ig._runtime_for(p, "sess:fw")
        rt["loaded"] = True
        import time as _t

        rt["domains"]["emotion"].load_dict({"unexpressed": 3.0})
        rt["domains"]["usermodel"].load_dict({
            "rhythm_ema": 10.0,
            "last_user_ts": _t.time() - 1000.0,
        })
        sched = ProactiveScheduler(p)  # type: ignore[arg-type]
        ev = type("_E", (), {"unified_msg_origin": "sess:fw"})()
        return await sched.request_dispatch(ev, dry_run=True)

    result = asyncio.run(go())
    assert result.get("dry_run") is True
    assert result.get("would_dispatch") is True
    assert result.get("decision", {}).get("action") == "reach_out"
