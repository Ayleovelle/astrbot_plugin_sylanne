"""v2core 实时接管桥接测试（Fable 重做版语义）。

新契约：v2core 负责裁决，LLMResponsePipeline 负责唯一物理投递——
- SPEAK：v2core 写回 completion_text 后返回 False，继续 sanitize/分段/观测。
- SILENT：返回 True 终结本轮，防 no-ghost 把刻意装死复活。
- 已退役的开关值会被忽略；异常仍返回 False 且不阻断投递管线。
用真实 host（临时 data_dir）跑桥接验证。
"""

from __future__ import annotations

import tempfile

import pytest

from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost
from sylanne_alpha.v2core.integration import apply_v2core_response


class _Resp:
    def __init__(self, t: str) -> None:
        self.completion_text = t


class _Event:
    unified_msg_origin = "test:u1"


class _Pipe:
    def _text(self, _e: object) -> str:
        return "你好"


class _Plugin:
    """最小插件桩：提供桥接需要的 _config / _session_key / _host / _llm_response_pipeline。"""

    def __init__(self, *, retired_flag: bool | None, root: str) -> None:
        self._config = {}
        if retired_flag is not None:
            self._config["sylanne_enable_v2core"] = retired_flag
        self._root = root
        self._llm_response_pipeline = _Pipe()
        self._hosts: dict[str, SylanneAlphaHost] = {}

    def _session_key(self, _e: object) -> str:
        return "u1"

    def _host(self, sk: str) -> SylanneAlphaHost:
        if sk not in self._hosts:
            self._hosts[sk] = SylanneAlphaHost(root=self._root, session_key=sk)
        return self._hosts[sk]


def _plugin(retired_flag: bool | None = None) -> _Plugin:
    return _Plugin(retired_flag=retired_flag, root=tempfile.mkdtemp(prefix="sylbridge_"))


@pytest.mark.asyncio
async def test_speak_processes_then_falls_through() -> None:
    """SPEAK：v2core 处理（状态推进）后返回 False，正文续接投递管线。"""
    p = _plugin()
    r = _Resp("嗯，我在的，今天有点想你。")
    suppress_delivery = await apply_v2core_response(p, _Event(), r)
    assert suppress_delivery is False, "SPEAK 应继续下游物理投递"
    assert r.completion_text.strip(), "正文不应为空"
    # v2core 真的处理了本轮：运行态已建、情绪账本采样到本轮（不是无脑 False）
    rt = p._v2core_runtimes["u1"]
    assert rt["domains"]["emotion"]._fast_ema is not None, "v2core 没真跑（账本未采样）"


@pytest.mark.asyncio
async def test_empty_draft_no_ghost() -> None:
    """整段 thinking 草稿 → FALLBACK 兜底文本写回并继续投递，绝不 ghost。"""
    p = _plugin()
    r = _Resp("<thinking>我已拿到答案，但忘了写出来</thinking>")
    suppress_delivery = await apply_v2core_response(p, _Event(), r)
    assert suppress_delivery is False
    assert r.completion_text.strip(), "v2core 必须永不 ghost（剥空草稿也给兜底）"


@pytest.mark.asyncio
async def test_retired_false_flag_is_ignored() -> None:
    """旧配置即使残留 false，也不能阻止 v2core 推进本轮状态。"""
    p = _plugin(retired_flag=False)
    r = _Resp("嗯，我在。")
    suppress_delivery = await apply_v2core_response(p, _Event(), r)
    assert suppress_delivery is False
    assert r.completion_text.strip()
    rt = p._v2core_runtimes["u1"]
    assert rt["domains"]["emotion"]._fast_ema is not None
