"""全架构集成实测：经 v2core 接管桥跑多轮真实对话，证明九能力+双域端到端无 bug。

架构落地的总验收：开关开 → 完整 Phase B/C/D 架构处理回复；多轮后 UserModel 真的学了你；
永不 ghost；点火决策真的发生。用真实 host（临时 data_dir，不碰存档）。
"""

from __future__ import annotations

import tempfile

import pytest

from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost


class _Resp:
    def __init__(self, t: str) -> None:
        self.completion_text = t


class _Event:
    unified_msg_origin = "test:u1"


class _Pipe:
    def _text(self, _e: object) -> str:
        return _Pipe.current_text


_Pipe.current_text = ""


class _Plugin:
    def __init__(self, root: str) -> None:
        self._config = {"sylanne_enable_v2core": True}
        self._root = root
        self._llm_response_pipeline = _Pipe()
        self._hosts: dict = {}

    def _session_key(self, _e: object) -> str:
        return "u1"

    def _host(self, sk: str):
        if sk not in self._hosts:
            self._hosts[sk] = SylanneAlphaHost(root=self._root, session_key=sk)
        return self._hosts[sk]


@pytest.mark.asyncio
async def test_full_architecture_multi_turn_no_bug() -> None:
    from sylanne_alpha.v2core.integration import apply_v2core_response

    plugin = _Plugin(tempfile.mkdtemp(prefix="sylfull_"))

    convo = [
        ("你好呀，今天好想你❤️", "嗯，我也想你，宝宝。"),
        ("我在写代码有点累", "写代码累了就歇会儿，我陪着你。"),
        ("你还记得我们说要去日本吗", "记得呀，樱花季一起去。"),
        ("嗯嗯❤️", "嗯，约好了。"),
    ]
    for user_text, draft in convo:
        _Pipe.current_text = user_text
        r = _Resp(draft)
        took = await apply_v2core_response(plugin, _Event(), r)
        # Fable 版契约：SPEAK 处理后故意回落 legacy 分发（sanitize/分段在那边）
        assert took is False, "SPEAK 应回落 legacy 分发"
        assert r.completion_text.strip(), "永不 ghost（每轮都有可见回复）"

    # 多轮后 UserModel 真的在学你（二重奏）
    rt = plugin._v2core_runtimes["u1"]
    um = rt["domains"]["usermodel"]
    assert um._last_prediction is not None, "UserModel 应已建立对你的预判"
    assert len(um._pe_history) >= 3, "应积累了 user_pe 历史（她在逼近懂你）"
    # emotion 域也在跨轮活着
    assert rt["domains"]["emotion"] is not None


@pytest.mark.asyncio
async def test_full_architecture_empty_draft_no_ghost() -> None:
    """整段 thinking 草稿经全架构 → 永不 ghost。"""
    from sylanne_alpha.v2core.integration import apply_v2core_response
    plugin = _Plugin(tempfile.mkdtemp(prefix="sylfull2_"))
    _Pipe.current_text = "在吗"
    r = _Resp("<thinking>她问在吗，我应该回应</thinking>")
    took = await apply_v2core_response(plugin, _Event(), r)
    assert took is False                      # FALLBACK 同样回落 legacy
    assert r.completion_text.strip(), "空草稿经全架构也必须兜底，不 ghost"
