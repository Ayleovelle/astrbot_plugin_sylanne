"""T4-02：通用变体池单测 + 三处落地点的接线回归。

覆盖：
- variant_pool.choose：recent-N 去重（不连续复读）+ condition 分桶 + 边界情形。
- ①空回复兜底（renderer.py DefaultRenderer / llm_response_pipeline.py）：变体池选取 +
  config 自定义兜底文案优先级不被新逻辑吞掉。
- ②proactive_bridge 踌躇词：去掉陌生人 register「在吗？我」+ 变体数 ≥10 + 去重接线。
- ③StateProjector 状态自述骨架：每档多变体 + 不泄漏内部表征（沿用既有边界测试）。
"""

from __future__ import annotations

import asyncio
import tempfile
import types

from sylanne_alpha.llm_response_pipeline import LLMResponsePipeline
from sylanne_alpha.proactive_bridge import ProactiveBridge, _HESITATION_FILLERS
from sylanne_alpha.rhythm_learner import RhythmLearner
from sylanne_alpha.session_state_store import SessionStateStore
from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase
from sylanne_alpha.v2core.renderer import (
    EMPTY_REPLY_FALLBACK_VARIANTS,
    DefaultRenderer,
    StateProjector,
    _DEFAULT_FALLBACK_TEXT,
)
from sylanne_alpha.variant_pool import choose, warmth_bucket


# ===========================================================================
# variant_pool.choose —— 纯函数核心行为
# ===========================================================================

def test_choose_no_immediate_repetition_over_many_draws() -> None:
    """recent-N 去重：只要桶里候选数 > recent_n，连续两次绝不选中同一个。"""
    variants = ["a", "b", "c", "d"]
    state: dict[str, list[str]] = {}
    prev = None
    for _ in range(200):
        picked = choose(variants, recent_key="k", state=state, recent_n=2)
        assert picked != prev, "连续两次选中同一变体（recent-N 去重失效）"
        prev = picked


def test_choose_condition_bucket_isolation() -> None:
    """condition 分桶：只从对应桶里选，不会串到别的桶。"""
    variants = {"warm": ["w1", "w2"], "cold": ["c1", "c2"]}
    for _ in range(30):
        assert choose(variants, recent_key="k", condition="warm") in ("w1", "w2")
        assert choose(variants, recent_key="k", condition="cold") in ("c1", "c2")


def test_choose_missing_condition_falls_back_to_default_bucket() -> None:
    variants = {"warm": ["w1"], None: ["n1", "n2"]}
    # condition 传了个桶里没有的 key → 退回 None 默认桶
    for _ in range(10):
        assert choose(variants, recent_key="k", condition="unknown") in ("n1", "n2")


def test_choose_empty_variants_returns_empty_string() -> None:
    assert choose([], recent_key="k") == ""
    assert choose({}, recent_key="k") == ""


def test_choose_state_none_is_stateless_but_safe() -> None:
    """state=None 时不去重，也不应抛异常（无 session 上下文可用时的兜底路径）。"""
    for _ in range(20):
        assert choose(["only"], recent_key="k", state=None) == "only"


def test_warmth_bucket_thresholds() -> None:
    assert warmth_bucket(0.5) == "warm"
    assert warmth_bucket(0.1) == "warm"
    assert warmth_bucket(-0.5) == "cold"
    assert warmth_bucket(-0.1) == "cold"
    assert warmth_bucket(0.0) == "neutral"
    assert warmth_bucket(None) is None


# ===========================================================================
# ①空回复兜底 —— renderer.py DefaultRenderer
# ===========================================================================

def _empty_draft_ctx() -> BeatContext:
    return BeatContext(
        session_key="s1", event=None,
        body=BodySnapshot(session_key="s1", turns=1, warmth=0.6),
        text="", phase=Phase.PERCEPT, domains={},
    )


def test_renderer_fallback_uses_variant_pool_when_unset() -> None:
    """未显式传 fallback_text（默认）→ 走 EMPTY_REPLY_FALLBACK_VARIANTS 池子。"""
    r = DefaultRenderer()
    ctx = _empty_draft_ctx()
    reply = r.render(ctx, draft="")  # 草稿被剥空 → empty_draft 分支
    all_variants = {v for bucket in EMPTY_REPLY_FALLBACK_VARIANTS.values() for v in bucket}
    assert "".join(reply.parts) in all_variants


def test_renderer_fallback_no_immediate_repeat_same_session() -> None:
    """同一 DefaultRenderer 实例（=同一会话）连续兜底不会连续撞同一句。"""
    r = DefaultRenderer()
    ctx = _empty_draft_ctx()
    prev = None
    for _ in range(30):
        reply = r.render(ctx, draft="")
        text = "".join(reply.parts)
        assert text != prev
        prev = text


def test_renderer_fallback_explicit_override_wins_and_is_stable() -> None:
    """显式传入 fallback_text（旧调用约定）→ 锁定固定文案，池子不介入（向后兼容）。"""
    r = DefaultRenderer(fallback_text="锁定的兜底文案")
    ctx = _empty_draft_ctx()
    for _ in range(5):
        reply = r.render(ctx, draft="")
        assert "".join(reply.parts) == "锁定的兜底文案"


def test_default_fallback_text_constant_still_exported() -> None:
    """_DEFAULT_FALLBACK_TEXT 仍是模块级可 import 常量（P0-2 回归测试依赖它)。"""
    assert isinstance(_DEFAULT_FALLBACK_TEXT, str) and _DEFAULT_FALLBACK_TEXT.strip()


# ===========================================================================
# ①空回复兜底 —— llm_response_pipeline.py（config 覆盖通道优先级）
# ===========================================================================

class _FakeEngine:
    def expression_drive(self) -> float:
        return 0.5


class _FakeComputation:
    def __init__(self) -> None:
        self.engine = _FakeEngine()


class _FakeKernel:
    def __init__(self) -> None:
        self.computation = _FakeComputation()


class _FakeHost:
    def __init__(self) -> None:
        self.kernel = _FakeKernel()


def _make_response_plugin(extra_cfg: dict | None = None) -> types.SimpleNamespace:
    cfg = {
        "sylanne_alpha_realtime_chat_enabled": True,
        "sylanne_alpha_realtime_intercept_llm_response": True,
    }
    cfg.update(extra_cfg or {})
    p = types.SimpleNamespace()
    p._config = cfg
    p._store = SessionStateStore()
    p._background_tasks: list = []
    p._rhythm_learner = RhythmLearner(intimacy_threshold=0.6)
    p._root = tempfile.mkdtemp(prefix="variant_pool_test_")

    def _host(_sk: str) -> _FakeHost:
        return _FakeHost()

    p._host = _host
    p._session_key = lambda ev: str(getattr(ev, "unified_msg_origin", "") or "")
    return p


def _run_empty_response(p: types.SimpleNamespace, session_key: str = "sess:vp") -> str:
    pipe = LLMResponsePipeline(p)  # type: ignore[arg-type]
    # 隔离：不真正跑分段发送/后台观测（与本卡无关的下游机制），只看兜底文案选取本身。
    pipe._dispatch_segmented_parts = types.MethodType(  # type: ignore[method-assign]
        lambda self, *a, **kw: _noop(), pipe
    )
    pipe._background_observe_response = types.MethodType(  # type: ignore[method-assign]
        lambda self, *a, **kw: _noop(), pipe
    )

    async def _noop() -> None:
        return None

    # <thinking> 包住答案、strip 后真空 → reason=stripped_to_empty，走兜底路径（非静默）；
    # 用这个而非纯空串，避开 empty_completion 分支的默认静默（该分支不进变体池，见分治注释）。
    resp = types.SimpleNamespace(completion_text="<thinking>internal reasoning only</thinking>")
    ev = types.SimpleNamespace(unified_msg_origin=session_key)
    asyncio.run(pipe._on_llm_response_inner(ev, resp))
    return resp.completion_text


def test_response_pipeline_empty_reply_uses_pool_by_default() -> None:
    p = _make_response_plugin()
    text = _run_empty_response(p)
    all_variants = {v for bucket in EMPTY_REPLY_FALLBACK_VARIANTS.values() for v in bucket}
    assert text in all_variants


def test_response_pipeline_custom_config_fallback_wins_over_pool() -> None:
    """config 显式设了 sylanne_ghost_fallback_text → 用它，变体池不介入（precedence）。"""
    p = _make_response_plugin({"sylanne_ghost_fallback_text": "用户自定义兜底文案"})
    for sk in ("sess:vp-1", "sess:vp-2", "sess:vp-3"):
        text = _run_empty_response(p, session_key=sk)
        assert text == "用户自定义兜底文案"


def test_response_pipeline_fallback_no_immediate_repeat_same_session() -> None:
    p = _make_response_plugin()
    prev = None
    for _ in range(20):
        text = _run_empty_response(p, session_key="sess:vp-dedup")
        assert text != prev
        prev = text


# ===========================================================================
# ②踌躇词 —— proactive_bridge.hesitation_plan
# ===========================================================================

def test_hesitation_fillers_no_stranger_register_and_enough_variants() -> None:
    assert len(_HESITATION_FILLERS) >= 10
    assert "在吗？我" not in _HESITATION_FILLERS


def test_hesitation_plan_filler_no_immediate_repeat() -> None:
    syl = types.SimpleNamespace(context=None)
    bridge = ProactiveBridge(syl)
    body = {"immunity": {"boundary_pressure": 1.0}, "needs": {}, "temperature": {"warmth": 0.0}}
    seen = []
    for _ in range(60):
        plan = bridge.hesitation_plan(body, session_key="sess:hesit")
        if plan["filler"]:
            seen.append(plan["filler"])
    assert len(seen) >= 2, "高犹豫强度下应能多次触发踌躇词试探（测试假设不成立）"
    for a, b in zip(seen, seen[1:]):
        assert a != b, "踌躇词连续复读（recent-N 去重失效）"


# ===========================================================================
# ③StateProjector 状态自述骨架 —— 每档多变体 + 不泄漏内部表征
# ===========================================================================

def test_state_projector_mood_has_multiple_variants_per_tier() -> None:
    proj = StateProjector()
    body = BodySnapshot(session_key="s", turns=1, warmth=0.6, tension=0.1, intimacy_gravity=0.9)
    seen = {proj._narrate(body) for _ in range(20)}
    assert len(seen) >= 2, "同一档位应有 ≥2 种表述在多次调用中出现"


def test_state_projector_no_internal_repr_leak() -> None:
    proj = StateProjector()
    body = BodySnapshot(session_key="s", turns=1, warmth=0.6, tension=0.3, intimacy_gravity=0.7)
    for _ in range(10):
        out = proj._narrate(body)
        assert isinstance(out, str) and out.strip()
        for bad in ("{", "}", "BodySnapshot(", "object at 0x"):
            assert bad not in out
