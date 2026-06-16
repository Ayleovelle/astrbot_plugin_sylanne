"""Phase G fixlist P0-2 测试：装死(SILENT)在实弹路径可达（REVIEW §P0-2，D8 反转）。

病：renderer 只在 compose 模式查 silent；integration 永远传 draft=completion_text → 永远
draft 模式 → IgnitionArbiter 写的 scratch['silent'] 被无视 → 实弹路径点火仲裁只剩 observability，
integration 的 SILENT 分支是死代码。修：显式静默决策优先于一切，draft 模式也能 SILENT；
空草稿不再强行注入兜底。验收走实弹路径 apply_v2core_response（mock response 对象）。
"""

from __future__ import annotations

import asyncio

from sylanne_alpha.v2core.renderer import DefaultRenderer
from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, ReplyKind


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.completion_text = text


def test_renderer_draft_mode_honors_explicit_silent() -> None:
    """单元：draft 模式 + 显式 scratch['silent'] → SILENT（D8 反转，被问也能装死）。"""
    r = DefaultRenderer()
    body = BodySnapshot(session_key="s", turns=1)
    ctx = BeatContext(session_key="s", event=None, body=body, text="在吗")
    ctx.scratch["silent"] = {"reason": "ignition_hold"}
    reply = r.render(ctx, draft="一条宿主草稿")     # draft 模式
    assert reply.kind is ReplyKind.SILENT
    assert reply.meta.get("reason") == "ignition_hold"


def test_renderer_draft_mode_speaks_without_silent_decision() -> None:
    """draft 模式无显式静默 → 维持被问必答（SPEAK 草稿）。"""
    r = DefaultRenderer()
    body = BodySnapshot(session_key="s", turns=1)
    ctx = BeatContext(session_key="s", event=None, body=body, text="在吗")
    reply = r.render(ctx, draft="我在的呀")
    assert reply.kind is ReplyKind.SPEAK
    assert "我在的呀" in "".join(reply.parts)


def test_live_path_can_silent_with_ignition_hold() -> None:
    """实弹路径：v2core 接管 + 点火 hold（注入 silent 决策的假能力）→ completion_text==''。"""
    from sylanne_alpha.v2core import integration as ig
    from sylanne_alpha.v2core.contracts import Intent, Phase

    # 假能力：DELIBERATE 写 scratch['silent']（模拟 IgnitionArbiter hold 判定）
    class _ForceHold:
        name = "force_hold"
        phases = (Phase.DELIBERATE,)
        def deliberate(self, ctx: BeatContext) -> Intent:
            ctx.scratch["silent"] = {"reason": "ignition_hold"}
            return Intent(source=self.name, priority=0.0)

    # 假 plugin：复用真 runtime 装配，但塞进 force_hold 能力
    from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost
    import tempfile

    class FakePlugin:
        _config = {"sylanne_enable_v2core": True}
        def __init__(self) -> None:
            self._root = tempfile.mkdtemp(prefix="sylp02_"); self._h = {}
        def _session_key(self, event) -> str:  # noqa: ANN001
            return "s"
        def _host(self, sk):  # noqa: ANN001
            if sk not in self._h:
                self._h[sk] = SylanneAlphaHost(root=self._root, session_key=sk)
            return self._h[sk]
        class _Pipe:
            @staticmethod
            def _text(event):  # noqa: ANN001
                return "在吗"
        _llm_response_pipeline = _Pipe()

    p = FakePlugin()
    rt = ig._runtime_for(p, "s")
    rt["runner"]._sc.register(_ForceHold())   # 注册强制 hold

    resp = _FakeResponse("宿主草稿：我在的")
    handled = asyncio.run(ig.apply_v2core_response(p, object(), resp))
    assert handled is True
    assert resp.completion_text == ""          # 装死：清空，非伪造兜底


def test_live_path_empty_draft_not_forced_speak() -> None:
    """实弹路径：上游空草稿 → 绝不冒出兜底文案。

    冷启动 body 表达驱力≈0，IgnitionArbiter 会判 hold → SILENT（completion_text=''）；
    若无静默决策则回落旧管线（False）。两种结局都【绝不】把渲染兜底 boilerplate 写进回复。
    这是 P0-2 连带修的真不变量："空草稿不再冒出兜底文案"。
    """
    from sylanne_alpha.v2core import integration as ig
    from sylanne_alpha.v2core.renderer import _DEFAULT_FALLBACK_TEXT
    from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost
    import tempfile

    class FakePlugin:
        _config = {"sylanne_enable_v2core": True}
        def __init__(self) -> None:
            self._root = tempfile.mkdtemp(prefix="sylp02b_"); self._h = {}
        def _session_key(self, event) -> str:  # noqa: ANN001
            return "s"
        def _host(self, sk):  # noqa: ANN001
            if sk not in self._h:
                self._h[sk] = SylanneAlphaHost(root=self._root, session_key=sk)
            return self._h[sk]
        class _Pipe:
            @staticmethod
            def _text(event):  # noqa: ANN001
                return "在吗"
        _llm_response_pipeline = _Pipe()

    p = FakePlugin()
    resp = _FakeResponse("")                    # 上游空草稿
    handled = asyncio.run(ig.apply_v2core_response(p, object(), resp))
    # 关键不变量：无论接管(SILENT)还是回落(False)，都没有伪造的兜底文案
    assert resp.completion_text == ""
    assert _DEFAULT_FALLBACK_TEXT not in resp.completion_text
