"""FocusDomain 话语焦点域测试 —— 抗跳话题根因修复的行为契约。

核心契约：
1. 实义消息立/换话头；表情/短应答不夺话头（"😋"接在"早饭好吃吗"后仍指向早饭）。
2. prompt_line 仅在【当前消息低信息】时钉锚；当前是实义新消息时不钉（防反向漂移）。
3. 心象片段集成：话头行进 system_prompt，且永不被状态预算截断。
4. 持久化往返 + 旧档无此域=空起步（铁律④）。
"""

from __future__ import annotations

from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase
from sylanne_alpha.v2core.domains.focus import FocusDomain, is_substantive


def _ctx(text: str, *, phase: Phase = Phase.EVOLVE, turns: int = 1) -> BeatContext:
    body = BodySnapshot(session_key="s", turns=turns)
    ctx = BeatContext(session_key="s", event=None, body=body, text=text)
    ctx.phase = phase
    return ctx


# --------------------------------------------------------------------------
# is_substantive：实义判定
# --------------------------------------------------------------------------

def test_emoji_not_substantive() -> None:
    assert not is_substantive("😋")
    assert not is_substantive("😋😋😋")
    assert not is_substantive("？！…")


def test_ack_words_not_substantive() -> None:
    for w in ("嗯", "嗯嗯", "哈哈", "好的", "ok", "OK", "知道了", "哦哦"):
        assert not is_substantive(w), f"{w!r} 不该算实义话头"


def test_real_topic_substantive() -> None:
    assert is_substantive("早饭好吃吗")
    assert is_substantive("今天去爬山了")
    assert is_substantive("这段代码报错了")
    assert is_substantive("加班")
    assert is_substantive("开会")
    assert is_substantive("好饿")


# --------------------------------------------------------------------------
# 核心：表情接在实义话题后，话头不丢
# --------------------------------------------------------------------------

def test_emoji_keeps_prior_topic() -> None:
    """😋 跟在"早饭好吃吗"后 → 话头仍是早饭，且 prompt_line 钉住它。"""
    d = FocusDomain()
    d.ingest(_ctx("早饭好吃吗"))
    assert d.current == "早饭好吃吗"
    # 下一轮用户发 😋（非实义）——话头不该被夺走
    d.ingest(_ctx("😋"))
    assert d.current == "早饭好吃吗", "表情夺走了话头——跳话题根因没修住"


def test_promptline_anchors_only_on_low_info_current() -> None:
    """当前消息低信息时钉锚；当前是实义新消息时不钉（防反向漂移）。"""
    d = FocusDomain()
    d.ingest(_ctx("早饭好吃吗"))
    # 当前是 😋（低信息）→ 钉住早饭
    line = d.prompt_line("😋")
    assert line and "早饭好吃吗" in line, "低信息当前轮没钉住旧话头"
    assert "别拐回" in line
    # 当前是实义新消息 → 不钉（新话题自己承载）
    assert d.prompt_line("我们聊聊晚饭吧") == "", "实义新消息被旧话头压住=反向漂移"


def test_promptline_empty_on_cold_start() -> None:
    """无存量话头（冷启动）→ 空串，不瞎钉。"""
    d = FocusDomain()
    assert d.prompt_line("😋") == ""


def test_substantive_replaces_topic() -> None:
    d = FocusDomain()
    d.ingest(_ctx("早饭好吃吗"))
    d.ingest(_ctx("下午开会几点"))
    assert d.current == "下午开会几点"
    assert d.recent_topics == ("早饭好吃吗", "下午开会几点")


def test_ingest_only_evolve() -> None:
    """写只在 EVOLVE 拍（铁律①）。"""
    d = FocusDomain()
    d.ingest(_ctx("早饭好吃吗", phase=Phase.PERCEPT))
    assert d.current == "", "PERCEPT 拍不该写话头"


def test_long_message_gist_capped() -> None:
    d = FocusDomain()
    long = "今天" * 50
    d.ingest(_ctx(long))
    assert len(d.current) <= 40


# --------------------------------------------------------------------------
# 持久化往返 + 向前兼容
# --------------------------------------------------------------------------

def test_persistence_roundtrip() -> None:
    d = FocusDomain()
    d.ingest(_ctx("早饭好吃吗"))
    d.ingest(_ctx("下午开会几点"))
    blob = d.to_dict()
    d2 = FocusDomain()
    d2.load_dict(blob)
    assert d2.current == "下午开会几点"
    assert d2.recent_topics == ("早饭好吃吗", "下午开会几点")


def test_load_empty_archive() -> None:
    """旧档无此域 → 空起步不报错（铁律④）。"""
    d = FocusDomain()
    d.load_dict({})
    d.load_dict(None)  # type: ignore[arg-type]
    assert d.current == ""


# --------------------------------------------------------------------------
# 心象片段集成：话头行进 system_prompt 且不被截
# --------------------------------------------------------------------------

def test_focus_line_reaches_mind_fragment() -> None:
    from sylanne_alpha.v2core.fragment import build_mind_fragment

    foc = FocusDomain()
    foc.ingest(_ctx("早饭好吃吗"))
    domains = {"focus": foc}
    # 当前轮是 😋（低信息）→ 心象里应带话头锚
    ctx = _ctx("😋", phase=Phase.PERCEPT)
    frag = build_mind_fragment(ctx, domains)
    assert "话头" in frag and "早饭好吃吗" in frag
    assert "[心象" in frag


def test_focus_line_survives_truncation() -> None:
    """状态行很长时话头行 + 临场态度仍不被截（都是受截区间外）。"""
    from sylanne_alpha.v2core.fragment import build_mind_fragment, _PRESENCE, _MAX_CHARS

    foc = FocusDomain()
    foc.ingest(_ctx("早饭好吃吗"))

    class _FatEmotion:
        def prompt_line(self, body):  # noqa: ANN001
            return "情绪:" + "很满很满" * 60   # 故意撑爆预算

    domains = {"focus": foc, "emotion": _FatEmotion()}
    ctx = _ctx("😋", phase=Phase.PERCEPT)
    frag = build_mind_fragment(ctx, domains)
    assert "早饭好吃吗" in frag, "话头行被状态预算截掉了"
    assert _PRESENCE in frag, "临场态度被截掉了"


def test_no_focus_line_when_current_substantive() -> None:
    """当前是实义消息 → 心象不带话头锚（不压新话题）。"""
    from sylanne_alpha.v2core.fragment import build_mind_fragment

    foc = FocusDomain()
    foc.ingest(_ctx("早饭好吃吗"))
    domains = {"focus": foc}
    ctx = _ctx("我们聊聊晚饭吧", phase=Phase.PERCEPT)
    frag = build_mind_fragment(ctx, domains)
    assert "话头" not in frag
