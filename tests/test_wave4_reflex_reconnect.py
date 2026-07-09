"""Wave 4：重连 reflex_learn 到 RESPONSE_POST（apply_v2core_response）。

v1 清理后 reflex_learn 失去 caller（层次1 反应式学习名存实亡）。本文件钉死它在真出站
回复轮（SPEAK/FALLBACK）被调一次、SILENT 轮不调（没有 bot 回复，不能污染续聊间隔推断），
且接的是 agents.SelfCore（plugin._self_core），传 behavior=None 让 compute_behavior 自动推。
"""

from __future__ import annotations

import asyncio
import tempfile

from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost
from sylanne_alpha.v2core import integration as ig
from sylanne_alpha.v2core.contracts import ReplyKind


class _Resp:
    def __init__(self, t: str) -> None:
        self.completion_text = t


class _Ev:
    message_str = "在干嘛呀"
    unified_msg_origin = "sess:w4"


class _Lock:
    async def __aenter__(self):  # noqa: ANN204
        return self

    async def __aexit__(self, *a: object) -> None:
        return None


class _SpySelfCore:
    """记录 reflex_learn 调用的桩。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def reflex_learn(self, session_key: str, *, self_quality, behavior=None) -> None:  # noqa: ANN001
        self.calls.append({"session_key": session_key, "self_quality": self_quality, "behavior": behavior})


class _Plugin:
    def __init__(self, root: str) -> None:
        self._config = {"sylanne_enable_v2core": True}
        self._root = root
        self._h: dict = {}
        self._kv: dict = {}
        self._lock = _Lock()
        self._self_core = _SpySelfCore()

    def _session_key(self, _e: object) -> str:
        return "sess:w4"

    def _session_lock(self, _sk: str) -> _Lock:
        return self._lock

    def _host(self, sk: str) -> SylanneAlphaHost:
        if sk not in self._h:
            self._h[sk] = SylanneAlphaHost(root=self._root, session_key=sk)
        return self._h[sk]

    async def get_kv_data(self, key, default=None):  # noqa: ANN001
        return self._kv.get(key, default)

    async def put_kv_data(self, key, value) -> None:  # noqa: ANN001
        self._kv[key] = value


class _FakeReply:
    def __init__(self, kind: ReplyKind, parts: list[str]) -> None:
        self.kind = kind
        self.parts = parts
        self.meta: dict = {}


def _run_with_forced(kind: ReplyKind, *, quality: float | None,
                     completion: str = "草稿") -> _SpySelfCore:
    """patch decision 阶段强制 reply.kind，跑一轮 response，返回 spy。

    completion = 上游 LLM 草稿；空/纯空白 → apply_v2core_response 算出 draft=None
    （legacy empty_completion 静默丢弃路径）。
    """
    p = _Plugin(tempfile.mkdtemp(prefix="w4_"))
    rt = ig._runtime_for(p, "sess:w4")
    rt["loaded"] = True

    def fake_decision(ctx, draft=None, do_response_tick=True):  # noqa: ANN001
        if quality is not None:
            ctx.scratch["quality_score"] = quality
        return _FakeReply(kind, ["在的呀"] if kind is not ReplyKind.SILENT else [])

    rt["runner"].run_decision_stage = fake_decision  # type: ignore[method-assign]

    async def go() -> None:
        await ig.apply_v2core_response(p, _Ev(), _Resp(completion))

    asyncio.run(go())
    return p._self_core


def test_reflex_learn_fires_on_speak() -> None:
    """SPEAK 轮：reflex_learn 被调一次，session_key 对、behavior=None（自动推）、自评质量透传。"""
    spy = _run_with_forced(ReplyKind.SPEAK, quality=0.8)
    assert len(spy.calls) == 1, "SPEAK 轮该触发一次 reflex_learn"
    c = spy.calls[0]
    assert c["session_key"] == "sess:w4"
    assert c["behavior"] is None, "应传 None 让 compute_behavior 自动推续聊间隔（强信号）"
    assert c["self_quality"] == 0.8, "本轮自评质量该透传作弱信号"


def test_reflex_learn_skips_on_silent() -> None:
    """SILENT 轮：不触发——没有 bot 回复，mark_bot_reply 会污染续聊间隔推断。"""
    spy = _run_with_forced(ReplyKind.SILENT, quality=None)
    assert len(spy.calls) == 0, "SILENT 轮不该触发 reflex_learn"


def test_reflex_learn_fires_on_fallback_with_draft() -> None:
    """FALLBACK + 有上游草稿（legacy 真发草稿）：触发，self_quality=None（纯靠行为强信号学习）。"""
    spy = _run_with_forced(ReplyKind.FALLBACK, quality=None, completion="草稿")
    assert len(spy.calls) == 1
    assert spy.calls[0]["self_quality"] is None


def test_reflex_learn_skips_on_fallback_empty_draft() -> None:
    """FALLBACK + 空草稿（legacy empty_completion 静默丢弃，没有 bot 回复）：不触发。

    review wiring-correctness high：不然 mark_bot_reply 记下幽灵回复，污染续聊间隔推断
    （跟 SILENT 同源的危害，旧闸窄了一格只挡 SILENT）。
    """
    spy = _run_with_forced(ReplyKind.FALLBACK, quality=None, completion="   ")
    assert len(spy.calls) == 0, "空草稿 FALLBACK 没发消息，不该触发 reflex_learn"
