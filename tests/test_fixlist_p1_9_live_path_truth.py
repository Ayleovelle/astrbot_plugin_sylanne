"""Phase G fixlist P1-9 测试：全栈实弹路径补真（REVIEW §P1-9 + §四 艺术品过线判据）。

原则：每条新机制至少一条断言走 apply_v2core_response 实弹路径（部件隔离测试不计完成）。
本文件一轮真实接管里同时验证 P0-1/3/4/7 的接线在 live path 上活着。
"""

from __future__ import annotations

import asyncio
import tempfile

from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost
from sylanne_alpha.v2core import integration as ig


class _Resp:
    def __init__(self, t: str) -> None:
        self.completion_text = t


class _KVPlugin:
    _config = {"sylanne_enable_v2core": True}

    def __init__(self, root: str) -> None:
        self._root = root
        self._h: dict = {}
        self._kv: dict = {}
        self._background_tasks: list = []

    def _session_key(self, event) -> str:  # noqa: ANN001
        return "sess:live"

    def _host(self, sk):  # noqa: ANN001
        if sk not in self._h:
            self._h[sk] = SylanneAlphaHost(root=self._root, session_key=sk)
        return self._h[sk]

    class _Pipe:
        @staticmethod
        def _text(event):  # noqa: ANN001
            return "我好喜欢你呀❤️😊抱抱你今天怎么样"
    _llm_response_pipeline = _Pipe()

    async def get_kv_data(self, key, default=None):  # noqa: ANN001
        return self._kv.get(key, default)

    async def put_kv_data(self, key, value) -> None:  # noqa: ANN001
        self._kv[key] = value


def test_full_corrected_stack_one_live_turn() -> None:
    """一轮 apply_v2core_response：节律时钟落、质量自评注入链路活、域状态落盘——全活。

    诚实说明（canonical 迁移 2026-06-14，核查任务 wdjxyayf1）：
    - P0-3 affect 入体【通道】由 test_loser_affect_reaches_bodyport 验证（单轮幅度低于阈值，不在此断言）。
    - P0-4 自我进化漂移：旧版靠 learn("expression_fired") 必漂；canonical 迁移后 expression_fired
      经 process 自派生 result["should_express"]（live 不可靠，记 SDK backlog 缺口2），漂移的可靠
      agent 通道是 dialogue_quality 数值滞后注入（本轮自评 → rt["pending_quality"] → 下轮 request
      tick）。本测试是 response-only，无下一轮 request tick 消费 pending_quality，故此处验证
      【质量自评→漂移注入链路接对了】（rt["pending_quality"] 被设为 float）；端到端漂移由
      test_fixlist_p0_4 的 tick 注入测试覆盖。
    """
    p = _KVPlugin(tempfile.mkdtemp(prefix="p19_"))

    async def go() -> None:
        for _ in range(4):
            await ig.apply_v2core_response(p, object(), _Resp("嗯嗯我也好喜欢你~"))
        # Fable 版：落盘任务锚定在模块级 _PENDING_SAVES（不再挂 _background_tasks，
        # 因为 main.terminate 对那张表做的是 cancel）；测试里显式排干。
        await ig.drain_pending_saves()

        rt = p._v2core_runtimes["sess:live"]
        um = rt["domains"]["usermodel"]
        # P0-1：节律时钟落到 live path（last_user_ts 被设）
        assert um._last_user_ts is not None, "P0-1 节律时钟没落到 live path"
        # P0-4：质量自评 → 漂移注入链路在 live path 活着（SPEAK 轮自评出 float 质量分，
        # 经 rt["pending_quality"]={"score":float,"ts":float} 待下轮注入；带 ts 防陈旧串话）
        pq = rt.get("pending_quality")
        assert isinstance(pq, dict) and isinstance(pq.get("score"), float), \
            "P0-4 质量自评→漂移注入链路断在 live path（pending_quality 没被设）"
        # P0-7：域状态落盘
        assert any("v2core_domains" in k for k in p._kv), "P0-7 域状态没落盘"
        # distill 学到了
        assert rt["domains"]["distill"]._samples == 4

    asyncio.run(go())


def test_canonical_pe_single_source_live() -> None:
    """canonical PE 单一来源：BodySnapshot.surprise/precision 来自 kernel.computation（不重算）。"""
    from sylanne_alpha.v2core.body_port_v2 import CanonicalKernelBodyPort
    h = SylanneAlphaHost(root=tempfile.mkdtemp(prefix="p19b_"), session_key="s")
    bp = CanonicalKernelBodyPort.from_host(h, "s")
    bp.tick({"phase": "request", "text": "测试一下惊奇", "now": 1.0})
    snap = bp.observe()
    comp = h.kernel.computation
    # snapshot 的 surprise 应等于 kernel 的 _last_surprise（单一来源，非各自算）
    ls = getattr(comp, "_last_surprise", None)
    if ls is not None:
        assert abs(snap.surprise - float(ls)) < 1e-9, "surprise 不是 canonical 单一来源"
