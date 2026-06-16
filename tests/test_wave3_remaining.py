"""Wave 3 + 剩余 Tier1/2：历史稀释、PERCEPT 召回、工具面、meltdown KV。"""

from __future__ import annotations

import asyncio
import tempfile

from sylanne_alpha.history_dilution import dilute_dense_contexts
from sylanne_alpha.public_api import PublicAPI
from sylanne_alpha.state_persistence import StatePersistence
from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot
from sylanne_alpha.v2core.domains.memory import MemoryDomain
from sylanne_alpha.v2core.fragment import build_mind_fragment
from sylanne_alpha.v2core.integration import _percept_recall


def test_dilute_only_on_low_info_message() -> None:
    long_old = "这是一段很长的旧告白" * 20
    contexts = [
        {"role": "user", "content": long_old},
        {"role": "assistant", "content": long_old},
        {"role": "user", "content": "最近还好"},
        {"role": "assistant", "content": "嗯"},
        {"role": "user", "content": "😋"},
    ]
    out = dilute_dense_contexts(contexts, "😋")
    assert out is not None
    assert "已压缩" in out[0]["content"]
    assert out[-1]["content"] == "😋"

    # 实义新话题不稀释
    same = dilute_dense_contexts(contexts, "明天开会几点")
    assert same == contexts


def test_percept_recall_populates_scratch() -> None:
    class _MS:
        def recall(self, text, query_embedding=None, current_warmth=0.0, limit=3):
            return [type("R", (), {"text": "上次聊过猫", "confidence": "clear",
                                   "layer": "L2", "activation": 1.0,
                                   "temperature": 0.2, "emotional_weight": 0.5})()]

        def format_recall_injection(self, results, max_items=3):
            return "[记忆参考]\n" + results[0].text

    ms = _MS()
    mem = MemoryDomain(ms)  # type: ignore[arg-type]
    body = BodySnapshot(session_key="s1", turns=1, intimacy_gravity=0.9)
    ctx = BeatContext(
        session_key="s1",
        event=None,
        text="你还记得猫吗",
        body=body,
        scratch={},
        domains={"memory": mem},
    )
    ctx.current_warmth = 0.5

    class _P:
        config = {}

    async def go() -> None:
        await _percept_recall(_P(), ctx, {"memory": mem}, "你还记得猫吗")

    asyncio.run(go())
    assert ctx.scratch.get("recalled")
    line = mem.recall_prompt_line(ctx.scratch["recalled"])
    assert "猫" in line


def test_fragment_includes_memory_line() -> None:
    body = BodySnapshot(session_key="s1", turns=1, intimacy_gravity=0.5)
    ctx = BeatContext(
        session_key="s1",
        event=None,
        text="嗯",
        body=body,
        scratch={"recalled": [{"text": "加班很累", "confidence": "clear"}]},
        domains={},
    )

    class _Mem:
        def recall_prompt_line(self, recalled, max_items=2):
            return "记忆线索:加班很累"

    frag = build_mind_fragment(ctx, {"memory": _Mem()})
    assert "记忆线索" in frag


def test_tool_detail_full_clamped() -> None:
    class _P:
        config = {}

    api = PublicAPI(_P())  # type: ignore[arg-type]
    assert api._clamp_llm_tool_detail("full") == "summary"
    assert api._clamp_llm_tool_detail("summary") == "summary"


def test_meltdown_purge_deletes_kv() -> None:
    class _P:
        _store = type("S", (), {"sylanne_memory_cache": {}})()
        _v2core_runtimes = {"sess/m": {}}

        async def delete_kv_data(self, key: str) -> None:
            self._kv.pop(key, None)

        def __init__(self) -> None:
            self._kv = {
                "sylanne_memory_state:sess_m": {"x": 1},
                "sylanne_kernel_sess_m": {"y": 2},
                "sylanne_kernel_sess_m_backup": {"z": 3},
            }

    p = _P()
    sp = StatePersistence(p)  # type: ignore[arg-type]

    async def go() -> None:
        await sp.purge_session_after_meltdown("sess/m")

    asyncio.run(go())
    assert "sylanne_memory_state:sess_m" not in p._kv
    assert "sess/m" not in p._v2core_runtimes
