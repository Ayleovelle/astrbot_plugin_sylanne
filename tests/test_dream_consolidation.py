"""梦境巩固（2.2.0-a 零 LLM 段）实弹测试 —— 设计 §一验收判据。

她睡着时把白天收进自传：有新经历的夜晚成一枚"梦:"锚点，
没有素材的夜晚不伪造梦，纪元厚度不能靠睡觉刷，重启后梦还在。
"""

from __future__ import annotations

from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase
from sylanne_alpha.v2core.domains.narrative_self import NarrativeSelfDomain
from sylanne_alpha.v2core.domains.user_model import UserModelDomain
from sylanne_alpha.v2core.dream import weave_and_register_dream, weave_dream_note


def _lived_day(nd: NarrativeSelfDomain, *, turn: int = 5) -> None:
    """白天的经历：一枚高失配锚点（梦的素材）。"""
    ctx = BeatContext(session_key="u", event=None,
                      body=BodySnapshot(session_key="u", turns=turn, warmth=0.4),
                      phase=Phase.EVOLVE)
    ctx.scratch["narrative_pe"] = 0.8
    ctx.scratch["narrative_note"] = "说好春天去看樱花"
    nd.ingest(ctx)


def test_dream_registered_after_lived_day() -> None:
    """判据1：有新经历 → 成梦，自传末尾是"梦:"锚点。"""
    nd = NarrativeSelfDomain()
    _lived_day(nd)
    assert nd.register_dream("和Ta越来越合拍") is True
    assert nd._anchors[-1].note.startswith("梦:")
    assert "合拍" in nd._anchors[-1].note


def test_no_dream_without_new_experience() -> None:
    """判据2：没有素材的夜晚不伪造梦；连续两晚第二晚无梦。"""
    nd = NarrativeSelfDomain()
    assert nd.register_dream("x") is False          # 从未有经历 → 无梦
    _lived_day(nd)
    assert nd.register_dream("第一晚") is True
    assert nd.register_dream("第二晚") is False     # 两梦之间无新经历 → 无梦
    _lived_day(nd, turn=9)
    assert nd.register_dream("第三晚") is True      # 又活了一天 → 又能做梦


def test_dream_does_not_inflate_epoch_thickness() -> None:
    """判据3：梦锚点不计入 anchor_total——成长不能靠睡觉刷出来。"""
    nd = NarrativeSelfDomain()
    _lived_day(nd)
    before = nd._anchor_total
    nd.register_dream("一个梦")
    assert nd._anchor_total == before
    assert len(nd._anchors) == before + 1   # 梦在自传里，但不算经历厚度


def test_empty_note_dream_still_honest() -> None:
    """素材编不出词（四域全空）→ 梦记落"无言的一夜"，不臆造内容。"""
    nd = NarrativeSelfDomain()
    _lived_day(nd)
    assert nd.register_dream("") is True
    assert nd._anchors[-1].note == "梦:无言的一夜"


def test_dream_survives_restart() -> None:
    """判据4：梦与守卫水位经存档往返无损（重启后不重复做同一晚的梦）。"""
    nd = NarrativeSelfDomain()
    _lived_day(nd)
    nd.register_dream("好梦")
    d = nd.to_dict()
    nd2 = NarrativeSelfDomain()
    nd2.load_dict(d)
    assert any(a.note.startswith("梦:") for a in nd2._anchors)
    assert nd2.register_dream("重启后") is False    # 守卫水位还原 → 无新经历无梦


def test_weave_note_takes_memes_and_synchrony() -> None:
    """织梦取材：最热的"我们的说法"+ 合拍程度真的进梦记。"""
    um = UserModelDomain()
    for i, text in enumerate(("芝士雪豹来了", "快看芝士雪豹", "芝士雪豹好可爱")):
        ctx = BeatContext(session_key="u", event=None,
                          body=BodySnapshot(session_key="u", turns=i + 1),
                          text=text, phase=Phase.EVOLVE)
        ctx.scratch["now"] = 1000.0 + i * 60.0
        ctx.scratch["assessment"] = {"arousal": 0.8}
        um.ingest(ctx)
    note = weave_dream_note({"usermodel": um})
    assert "芝士雪豹" in note


def test_full_chain_via_plugin_stub() -> None:
    """整链：深睡入口 weave_and_register_dream 经 plugin 桩走通（v2core 关 → 静默 False）。"""
    nd = NarrativeSelfDomain()
    _lived_day(nd)

    class _Plugin:
        _v2core_runtimes = {"s1": {"domains": {"narrative": nd, "usermodel": UserModelDomain()}}}

    assert weave_and_register_dream(_Plugin(), "s1") is True
    assert nd._anchors[-1].note.startswith("梦:")

    class _NoV2:
        pass

    assert weave_and_register_dream(_NoV2(), "s1") is False   # v2core 未启用 → 无梦不报错
