"""SharedLexicon（2.2.0-b "我们的梗"）实弹测试 —— 设计 §二验收判据全覆盖。

她学会"我们之间才懂的话"：高唤起轮诞生的语汇、跨轮复现才算数、
人人都说的词永不晋升、不用会过气、重启不丢。
"""

from __future__ import annotations

from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase
from sylanne_alpha.v2core.domains.user_model import UserModelDomain, _extract_grams


def _evolve(um: UserModelDomain, text: str, *, turn: int, arousal: float = 0.5) -> None:
    ctx = BeatContext(
        session_key="u", event=None,
        body=BodySnapshot(session_key="u", turns=turn),
        text=text, phase=Phase.EVOLVE,
    )
    ctx.scratch["now"] = 1000.0 + turn * 60.0
    ctx.scratch["assessment"] = {"arousal": arousal}
    um.ingest(ctx)


def test_meme_promoted_after_recurrence_and_in_prompt() -> None:
    """判据1：高唤起首现 + 跨轮复现 3 次 → 晋升，心象出现"我们的说法"。

    句式逐轮变化（贴真实用法）：变化语境中的不变量才是梗——
    跨词边界的偶然 gram（"也是芝士"）不会跨句式复现，自然被淘汰。
    """
    um = UserModelDomain()
    _evolve(um, "今天也是芝士雪豹的一天", turn=1, arousal=0.7)
    _evolve(um, "芝士雪豹真的太好笑了", turn=2, arousal=0.7)
    _evolve(um, "想变成芝士雪豹躺平", turn=3, arousal=0.7)
    assert "芝士雪豹" in um.memes(limit=16)
    assert "我们的说法" in um.prompt_line()
    assert "芝士雪豹" in um.prompt_line()


def test_static_lexicon_word_never_promotes() -> None:
    """判据2：静态词表词（人人都说的"谢谢"）永不晋升为"我们的"。"""
    um = UserModelDomain()
    for i in range(6):
        _evolve(um, "谢谢", turn=i + 1, arousal=0.9)
    assert "谢谢" not in um.memes(limit=16)


def test_low_arousal_birth_never_promotes() -> None:
    """梗的出身：首现于低唤起轮（没有情绪标记）→ 复现再多也只是常用语。"""
    um = UserModelDomain()
    for i in range(8):
        _evolve(um, "明天开会记得带电脑", turn=i + 1, arousal=0.05)
    assert um.memes(limit=16) == []


def test_same_turn_repetition_counts_once() -> None:
    """跨轮才算复现：一条消息里刷十遍不是梗。"""
    um = UserModelDomain()
    _evolve(um, "芝士雪豹芝士雪豹芝士雪豹芝士雪豹芝士雪豹", turn=1, arousal=0.8)
    assert um.memes(limit=16) == []   # count 仍为 1，未过晋升线


def test_meme_fades_when_unused() -> None:
    """判据3：30+ 轮不用 → 热度减半直至跌出（梗会过气）。"""
    um = UserModelDomain()
    _evolve(um, "你就是失败学大师吧", turn=1, arousal=0.7)
    _evolve(um, "失败学大师又来了", turn=2, arousal=0.7)
    _evolve(um, "不愧是失败学大师", turn=3, arousal=0.7)
    assert um.memes(limit=16), "前置：梗已晋升"
    # 一个 30+ 轮窗口没再说它 → count 3→1.5 ≤ 晋升线一半 → 淘汰
    _evolve(um, "聊点别的吧最近怎么样", turn=40, arousal=0.1)
    assert um.memes(limit=16) == []


def test_substring_fragment_not_promoted() -> None:
    """碎片抑制：完整梗在位时，同源碎片（子串/共片段 gram）不再晋升霸位。"""
    um = UserModelDomain()
    _evolve(um, "芝士雪豹来了", turn=1, arousal=0.8)
    _evolve(um, "快看芝士雪豹", turn=2, arousal=0.8)
    _evolve(um, "芝士雪豹好可爱", turn=3, arousal=0.8)
    _evolve(um, "永远爱芝士雪豹", turn=4, arousal=0.8)
    mm = um.memes(limit=16)
    assert mm, "前置：有梗晋升"
    full = max(mm, key=len)
    assert "雪豹" in full
    assert all(m == full or m not in full for m in mm), f"碎片混进梗表: {mm}"


def test_meme_archive_roundtrip_and_legacy_archive() -> None:
    """判据4：存档往返梗无损；旧档无此键 → 空起步不崩（铁律④）。"""
    um = UserModelDomain()
    for i in range(3):
        _evolve(um, "今天也是芝士雪豹的一天", turn=i + 1, arousal=0.7)
    d = um.to_dict()
    um2 = UserModelDomain()
    um2.load_dict(d)
    assert um2.memes(limit=16) == um.memes(limit=16)

    legacy = {"disposition": {"warmth": 0.2}}   # 旧档：无 meme 键
    um3 = UserModelDomain()
    um3.load_dict(legacy)
    assert um3.memes(limit=16) == []
    _evolve(um3, "继续正常推进", turn=1, arousal=0.5)   # 加载后仍可正常 ingest


def test_extract_grams_filters() -> None:
    """提取器：滤静态词表/功能字粘连；中英混合可提取。"""
    grams = _extract_grams("那个mukbang视频里的了的了")
    assert "mukbang" in grams
    assert "的了" not in grams and "了的" not in grams
    assert all(g not in ("抱抱", "谢谢") for g in _extract_grams("抱抱谢谢"))
