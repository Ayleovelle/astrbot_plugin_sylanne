"""Phase G fixlist P0-6 测试：重固化 PE 修真 + 影子层接通（REVIEW §P0-6）。

病：①recall 输出无情绪键 → _mean_recalled_warmth 恒空 → recalled_emotion=0 → npe=|warmth|
→ 暖聊每轮"超阈"spam 重固化+锚点（语义反了）；②overlay_for 零调用 → 写了没人读。
修：recall 补 temperature/emotional_weight；无基线→None→跳过；读侧 recall 附 overlay_warmth。
"""

from __future__ import annotations

from types import SimpleNamespace

from sylanne_alpha.v2core.capabilities.reconsolidation import (
    ReconsolidationCapability,
    _mean_recalled_warmth,
)
from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase
from sylanne_alpha.v2core.domains.memory import MemoryDomain
from sylanne_alpha.v2core.domains.narrative_self import NarrativeSelfDomain


class _FakeMS:
    """假 MemorySystem：recall 返回带/不带 temperature 的 MemoryResult 桩。"""

    def __init__(self, results) -> None:  # noqa: ANN001
        self._results = results

    def recall(self, text, _none, warmth, limit=3, **kwargs):  # noqa: ANN001
        return self._results[:limit]

    def to_dict(self):
        return {}

    def from_dict(self, d):  # noqa: ANN001
        pass

    def format_recall_injection(self, results, max_items=3):  # noqa: ANN001
        return ""


def _result(text, temperature=None, ew=0.5):  # noqa: ANN001
    return SimpleNamespace(text=text, confidence="clear", layer="l1",
                           activation=0.5, temperature=temperature, emotional_weight=ew)


def test_mean_recalled_warmth_none_without_emotion() -> None:
    """无任何有效情绪值 → None（不拿 0.0 充数）。"""
    assert _mean_recalled_warmth([{"text": "a"}, {"text": "b"}]) is None
    assert _mean_recalled_warmth([{"text": "a", "temperature": 0.6}]) == 0.6


def test_recall_carries_temperature() -> None:
    """recall 输出带 temperature/emotional_weight（重固化才有真实基线）。"""
    ms = _FakeMS([_result("旧事", temperature=0.7)])
    dom = MemoryDomain(ms)
    rows = dom.recall("提到旧事", warmth=0.2)
    assert rows[0]["temperature"] == 0.7
    assert "emotional_weight" in rows[0]


def test_no_reconsolidation_without_emotion_baseline() -> None:
    """召回无情绪基线（temperature=None）→ 零重固化、零锚点（不再 spam）。"""
    ms = _FakeMS([_result("无情绪的事", temperature=None)])
    dom = MemoryDomain(ms)
    narrative = NarrativeSelfDomain()
    cap = ReconsolidationCapability()

    body = BodySnapshot(session_key="s", turns=1, warmth=0.8)   # 暖聊
    ctx = BeatContext(session_key="s", event=None, body=body, text="提到旧事")
    ctx.phase = Phase.EVOLVE
    ctx.scratch["recalled"] = dom.recall("提到旧事", warmth=0.8)
    ctx.domains["memory"] = dom
    ctx.domains["narrative"] = narrative
    cap.evolve(ctx)
    # 无情绪基线 → 不算 npe、不重固化、不写锚点
    assert "narrative_pe" not in ctx.scratch
    assert dom.overlay_for("无情绪的事") is None


def test_reconsolidation_writes_overlay_and_visible_on_recall() -> None:
    """有情绪基线 + npe 超阈 → overlay 写入【且】下次 recall 可见 overlay_warmth。"""
    # 召回记忆情绪冷(−0.6)，当下暖(+0.8) → 大失配 → 超阈触发重固化
    ms = _FakeMS([_result("那次争吵", temperature=-0.6)])
    dom = MemoryDomain(ms)
    narrative = NarrativeSelfDomain()
    cap = ReconsolidationCapability()

    body = BodySnapshot(session_key="s", turns=1, warmth=0.8)
    ctx = BeatContext(session_key="s", event=None, body=body, text="想起那次争吵")
    ctx.phase = Phase.EVOLVE
    ctx.scratch["recalled"] = dom.recall("想起那次争吵", warmth=0.8)
    ctx.domains["memory"] = dom
    ctx.domains["narrative"] = narrative
    cap.evolve(ctx)

    # overlay 写入
    ov = dom.overlay_for("那次争吵")
    assert ov is not None, "npe 超阈但 overlay 没写入"
    assert ov["rewrite_count"] >= 1
    # 下次 recall 可见 overlay_warmth（读侧接通，原文不动）
    rows = dom.recall("想起那次争吵", warmth=0.8)
    assert "overlay_warmth" in rows[0], "overlay 写了没人读（影子层死信号）"
    # 情绪向当下暖漂移（−0.6 朝 +0.8）
    assert rows[0]["overlay_warmth"] > -0.6
