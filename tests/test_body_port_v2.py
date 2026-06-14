"""body_port_v2 测试：CanonicalKernelBodyPort 三动词 + phase 路由 + from_host 可跑路径。

用临时 data_dir 起真实 host，绝不碰用户存档。验证 P2(持host不绕)/P14(tick返BodySnapshot)/
S7(phase路由) + canonical 路径在 vendored 无 shared() 时抛清晰错误（D0 预期）。
"""

from __future__ import annotations

import tempfile

import pytest

from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost
from sylanne_alpha.v2core.body_port_v2 import (
    CanonicalKernelBodyPort,
    _is_response_phase,
)
from sylanne_alpha.v2core.contracts import BodySnapshot


def _temp_host(sk: str = "t1") -> SylanneAlphaHost:
    return SylanneAlphaHost(root=tempfile.mkdtemp(prefix="sylv2_"), session_key=sk)


def test_phase_routing() -> None:
    assert _is_response_phase({"phase": "response"}) is True
    assert _is_response_phase({"flags": ["response"]}) is True
    assert _is_response_phase({"phase": "request"}) is False
    assert _is_response_phase({}) is False
    assert _is_response_phase("not a dict") is False  # type: ignore[arg-type]


def test_from_host_three_verbs() -> None:
    bp = CanonicalKernelBodyPort.from_host(_temp_host(), "t1")
    snap = bp.observe()
    assert isinstance(snap, BodySnapshot)
    assert snap.session_key == "t1"

    s_req = bp.tick({"phase": "request", "text": "你好"})
    assert isinstance(s_req, BodySnapshot)  # P14：tick 返回 BodySnapshot，不漏 surface dict
    s_resp = bp.tick({"phase": "response", "text": "嗯嗯"})
    assert s_resp.turns >= s_req.turns  # 双 tick 推进

    snap_dict = bp.snapshot()
    assert isinstance(snap_dict, dict) and snap_dict


def test_canonical_path_returns_body_port() -> None:
    """vendored 已同步 canonical（含 async shared()）→ canonical 路径成功返回 BodyPort。

    迁移 2026-06-14：旧测试断言"vendored 未升级时抛 shared 错误"，现 shared() 已存在且是
    async；body_port_for_session 已修为 await shared()。验证它真能下探 host 造出 BodyPort。
    """
    import asyncio
    from sylanne_alpha.v2core.body_port_v2 import (
        CanonicalKernelBodyPort,
        body_port_for_session,
    )

    async def _llm(_a: str, _b: str) -> str:
        return ""

    bp = asyncio.run(
        body_port_for_session("t1", data_dir=tempfile.mkdtemp(), llm=_llm)
    )
    assert isinstance(bp, CanonicalKernelBodyPort)
    # 三动词可用（observe 不崩、返回类型化快照）
    snap = bp.observe()
    assert snap is not None
