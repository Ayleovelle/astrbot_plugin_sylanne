"""评价入体测试（Fable 重做版）：appraisal → assessment → 宿主 request tick 合并。

重做版的入体通道与旧版不同：不再有"response 阶段补打一拍空文本 request tick"
（那会污染 surprise/turns 统计）。评价在 PERCEPT（request 阶段）产出，经
integration.consume_pending_assessment 由 legacy 请求管线在它本来就要打的
host.on_request(assessment=…) 里合并入体——零额外 tick。

红线（铁律②点火不门控漂移）的新形态：assessment 在 PERCEPT 产出、点火在
DELIBERATE 之后——表达裁决【结构上不可能】拦截评价入体。本文件验证：
1. 评价真的评价文本（暖文本→正 valence；苦恼文本→wound_risk）。
2. 装死（hold）轮的评价照样可被取走入体。
3. 取走是一次性语义（不重复入体）。
"""

from __future__ import annotations

import asyncio
import tempfile

from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost
from sylanne_alpha.v2core import integration as ig
from sylanne_alpha.v2core.capabilities.mentalize import AppraisalCapability
from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase
from sylanne_alpha.v2core.domains.user_model import UserModelDomain
from sylanne_alpha.v2core.lexicon import read_signals


def _ctx(text: str, *, surprise: float = 0.3, domains: dict | None = None) -> BeatContext:
    ctx = BeatContext(
        session_key="s", event=None,
        body=BodySnapshot(session_key="s", turns=1, surprise=surprise),
        text=text, domains=domains or {},
    )
    ctx.phase = Phase.PERCEPT
    ctx.scratch["signals"] = read_signals(text)
    return ctx


def test_appraisal_appraises_the_text_not_body_echo() -> None:
    """评价的是【消息】：暖文本→正 valence；苦恼文本→wound_risk>0；与她自身心情无关。"""
    cap = AppraisalCapability()

    warm_ctx = _ctx("我好喜欢你呀❤️抱抱")
    cap.perceive(warm_ctx)
    a_warm = warm_ctx.scratch["assessment"]
    assert a_warm["valence"] > 0.0

    sad_ctx = _ctx("我好难过，想哭，今天太累了😭")
    cap.perceive(sad_ctx)
    a_sad = sad_ctx.scratch["assessment"]
    assert a_sad["wound_risk"] > 0.0
    assert a_sad["valence"] < a_warm["valence"]


def test_question_is_not_cold_evidence() -> None:
    """观测模型修正：提问是投入不是冷漠——纯问句不产生负 valence。"""
    cap = AppraisalCapability()
    ctx = _ctx("你今天过得怎么样？")
    cap.perceive(ctx)
    assert ctx.scratch["assessment"]["valence"] >= 0.0


def test_expectancy_violation_raises_arousal() -> None:
    """期望失配（你反常）→ 唤起升：习惯了暖的人突然发冷消息，arousal 更高。"""
    cap = AppraisalCapability()
    um = UserModelDomain()
    # 养成"你一向很暖"的后验
    for _ in range(8):
        c = _ctx("喜欢你❤️抱抱", domains={"usermodel": um})
        c.phase = Phase.EVOLVE
        c.scratch["now"] = 100.0
        um.ingest(c)
    cold_expected = _ctx("哼 烦 滚", domains={"usermodel": um})
    cap.perceive(cold_expected)
    a_violated = cold_expected.scratch["assessment"]

    um2 = UserModelDomain()   # 无画像（无期望可违背）
    cold_blank = _ctx("哼 烦 滚", domains={"usermodel": um2})
    cap.perceive(cold_blank)
    a_blank = cold_blank.scratch["assessment"]
    assert a_violated["arousal"] > a_blank["arousal"]


class _KVPlugin:
    _config = {"sylanne_enable_v2core": True}

    def __init__(self, root: str) -> None:
        self._root = root
        self._h: dict = {}
        self._kv: dict = {}

    def _session_key(self, event) -> str:  # noqa: ANN001
        return "sess:p03"

    def _host(self, sk):  # noqa: ANN001
        if sk not in self._h:
            self._h[sk] = SylanneAlphaHost(root=self._root, session_key=sk)
        return self._h[sk]

    async def get_kv_data(self, key, default=None):  # noqa: ANN001
        return self._kv.get(key, default)

    async def put_kv_data(self, key, value) -> None:  # noqa: ANN001
        self._kv[key] = value


class _Req:
    system_prompt = ""


class _Ev:
    message_str = "我好难过，想哭😭你怎么不理我"
    unified_msg_origin = "sess:p03"


def test_assessment_pending_and_consumed_once_live() -> None:
    """实弹：request 阶段后评价在暂存位 → consume 取走（一次性）→ 二次取为 None。"""
    p = _KVPlugin(tempfile.mkdtemp(prefix="p03_"))

    async def go() -> None:
        await ig.apply_v2core_request(p, _Ev(), _Req())
        a = ig.consume_pending_assessment(p, "sess:p03")
        assert a is not None and a.get("wound_risk", 0.0) > 0.0, "评价没到达入体暂存位"
        assert ig.consume_pending_assessment(p, "sess:p03") is None, "应为一次性语义"

    asyncio.run(go())


def test_silent_turn_does_not_gate_assessment() -> None:
    """铁律②结构保证：装死轮（hold）评价照常可入体——评价产出先于表达裁决。"""
    p = _KVPlugin(tempfile.mkdtemp(prefix="p03b_"))

    class _Resp:
        completion_text = "我在的呀"

    async def go() -> None:
        await ig.apply_v2core_request(p, _Ev(), _Req())
        # 评价已在暂存位（即使后续 response 阶段判 silent 也不影响它）
        rt = p._v2core_runtimes["sess:p03"]
        assert rt["pending_assessment"], "PERCEPT 评价缺失"
        # 强制本轮装死：直接往 pending ctx 写显式静默决策（模拟 ignition hold）
        rt["pending"]["ctx"].scratch["silent"] = {"reason": "test_hold"}
        handled = await ig.apply_v2core_response(p, _Ev(), _Resp())
        assert handled is True, "显式静默应由 v2core 终结本轮"
        # 评价暂存位不受表达裁决影响（仍可被请求管线取走——本测里没人取，仍在）
        assert ig.consume_pending_assessment(p, "sess:p03") is not None

    asyncio.run(go())
