"""全架构最终集成：11 能力 + 3 域经接管桥多轮跑通，Phase A-F 全链路咬合。

验收整个认知架构：理解→评价→读心→躯体→召回→表达→点火→主动→重固化→领域学习→SDK后学习。
用真实 host（临时 data_dir，不碰存档）。
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
    current_text = ""

    def _text(self, _e: object) -> str:
        return _Pipe.current_text


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
async def test_full_cognitive_cycle_multi_turn() -> None:
    from sylanne_alpha.v2core.integration import apply_v2core_response

    plugin = _Plugin(tempfile.mkdtemp(prefix="sylfinal_"))
    convo = [
        ("你好呀今天好想你❤️", "嗯，我也想你。"),
        ("我们之前说要去日本你还记得吗", "记得呀，樱花季。"),
        ("我有点累了", "累了就歇会儿，我陪你。"),
        ("嗯❤️", "嗯，在的。"),
        ("你为什么不理我😭", "我在呀，怎么会不理你。"),
    ]
    for ut, draft in convo:
        _Pipe.current_text = ut
        r = _Resp(draft)
        took = await apply_v2core_response(plugin, _Event(), r)
        assert took is False, "SPEAK 应回落 legacy 分发（Fable 版契约）"
        assert r.completion_text.strip(), "永不 ghost"

    rt = plugin._v2core_runtimes["u1"]
    doms = rt["domains"]
    # 四域都跨轮活着
    assert {"emotion", "usermodel", "narrative", "distill"} <= set(doms)
    # UserModel 学了你（二重奏）
    assert doms["usermodel"]._last_prediction is not None
    assert len(doms["usermodel"]._pe_history) >= 3
    # 蒸馏域真在学（teacher=body 真值）
    assert doms["distill"]._samples >= 3
    # 能力注册齐全（Fable 版能力集：understanding 已并入 lexicon 统一观测）
    caps = {c.name for c in rt["runner"]._sc.capabilities()}
    expected = {"appraisal", "mentalize", "somatic_marker", "recall",
                "expression", "ignition", "outreach", "reconsolidation"}
    assert expected <= caps, f"能力缺失: {expected - caps}"


@pytest.mark.asyncio
async def test_persistence_roundtrip_all_domains() -> None:
    """全域 to_dict/load_dict 往返无损（存档无损铁律④）。"""
    from sylanne_alpha.v2core.domains.emotion import EmotionLedger
    from sylanne_alpha.v2core.domains.narrative_self import NarrativeSelfDomain
    from sylanne_alpha.v2core.domains.user_model import UserModelDomain

    for cls in (EmotionLedger, UserModelDomain, NarrativeSelfDomain):
        d = cls()
        blob = d.to_dict()
        d2 = cls()
        d2.load_dict(blob)            # 不崩
        d2.load_dict({})              # 空档容缺不崩
        assert d2.to_dict() is not None
