"""临场态度恒在测试 —— "沉浸 > 办任务、够用 > 完美"焊进人格（用户 2026-06-13 拍板）。

设计立场：她钻牛角尖调 29 次工具不开口，根因是【追求完美答案】，而完美主义最不像人。
修复不是只靠 max_agent_step 硬砍（那是给机器装刹车），而是把"够用就说话、不必求全"
做成人格常量注入——系统提示在工具循环里一直在，LLM 每步决定"要不要再搜"时都读得到。

本文件钉死：
- 临场态度【恒在】，冷启动无任何状态也注入（性子不依赖状态存在）；
- 态度常量【永不被 _MAX_CHARS 截断】（状态行先削，给态度留位）；
- 关键意图词在位（不必查全求证、工具没查到照样开口、人无完人）。
"""

from __future__ import annotations

from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase
from sylanne_alpha.v2core.fragment import build_mind_fragment, _PRESENCE, _MAX_CHARS
from sylanne_alpha.v2core.domains.emotion import EmotionLedger
from sylanne_alpha.v2core.domains.user_model import UserModelDomain


def _ctx(body: BodySnapshot, domains: dict | None = None) -> BeatContext:
    c = BeatContext(session_key="u", event=None, body=body, text="看比赛看比赛",
                    phase=Phase.PERCEPT, domains=domains or {})
    return c


def _body(**kw) -> BodySnapshot:
    return BodySnapshot(session_key="u", turns=1, **kw)


def test_presence_always_injected_on_cold_start() -> None:
    """冷启动（无任何 domain/状态）：片段仍含临场态度——她的性子不依赖状态存在。"""
    frag = build_mind_fragment(_ctx(_body()), {})
    assert frag, "冷启动也该有临场态度，不该空"
    assert _PRESENCE in frag, "临场态度常量必须恒在"


def test_presence_intent_words_present() -> None:
    """关键意图词在位——直接劝退工具死锁的那几句话。"""
    frag = build_mind_fragment(_ctx(_body()), {})
    assert "不必" in frag and ("查全" in frag or "求证" in frag), "缺'不必查全求证'"
    assert "照样开口" in frag, "缺'工具没查到照样开口'（劝退死锁核心）"
    assert "人本无完人" in frag, "缺'人无完人'立场"
    assert "沉浸" in frag, "缺'沉浸进去'（沉浸 > 办任务）"


def test_presence_carbon_stepping_discipline() -> None:
    """更彻底的工具纪律（memory: tool-usage-carbon-stepping）：碳步途中也要认怂。

    不只是"一开始没工具就认怂"，还要在试错途中察觉自己在原地打转就收手——
    同一件事试两三回不成、或系统提醒重复调用同一工具，重复本身就是"做不到"信号。
    钉死这条引导词在位，且明确不是"把工具规划得更聪明"（那是逞强的另一种形式）。
    """
    frag = build_mind_fragment(_ctx(_body()), {})
    assert "做不到" in frag, "缺'做不到'坦白权"
    assert "重复" in frag, "缺'重复本身就是做不到信号'（碳步认怂核心）"
    assert "停手" in frag, "缺'停手认了就行'（劝退越钻越细）"
    # 反向：不该把它写成"规划纪律 / 先列计划 / 想清楚再动手"那种逞强话术
    for forbidden in ("先规划", "列计划", "想清楚再"):
        assert forbidden not in frag, f"工具纪律不该写成规划话术（逞强变体）: {forbidden}"



def test_presence_coexists_with_state_lines() -> None:
    """有状态时：状态行 + 临场态度共存（态度不挤掉状态线索）。"""
    emo = EmotionLedger()
    emo.load_dict({"fast_ema": 0.6, "slow_ema": -0.5, "unexpressed": 3.0})
    domains = {"emotion": emo, "usermodel": UserModelDomain()}
    body = _body(warmth=0.8, tension=0.6)
    frag = build_mind_fragment(_ctx(body, domains), domains)
    assert _PRESENCE in frag, "态度必须在"
    assert "暖" in frag, "状态线索也该在（态度不该挤掉状态）"


def test_presence_survives_truncation() -> None:
    """极端长状态：状态行被 _MAX_CHARS 截断，但临场态度常量完整保留。"""
    # 构造一个状态超长的场景：塞一堆 meme 把 usermodel 行撑长
    um = UserModelDomain()
    big_memes = {f"梗{i}超长说法字串{i}": {"count": 9.0, "first_arousal": 0.9, "last_turn": 1.0}
                 for i in range(20)}
    um.load_dict({"memes": big_memes,
                  "disp_precision": {"warmth": 0.9, "engagement": 0.9,
                                     "defensiveness": 0.9, "distress": 0.9}})
    emo = EmotionLedger()
    emo.load_dict({"fast_ema": 0.9, "slow_ema": -0.9, "unexpressed": 9.0})
    domains = {"emotion": emo, "usermodel": um}
    frag = build_mind_fragment(_ctx(_body(warmth=0.9, tension=0.9), domains), domains)
    assert _PRESENCE in frag, "无论状态多长，临场态度常量必须完整保留（永不被截）"


def test_presence_style_discipline_present() -> None:
    """T4-01 反AI味文风底色：_PRESENCE 恒带一条口吻纪律行——QQ 短句、不排比列点、
    不总分总、不说『首先/其次』、不解释自己为什么这么说；且它随 _PRESENCE 一起
    豁免于 _MAX_CHARS 预算（不会被状态行挤没）。
    """
    frag = build_mind_fragment(_ctx(_body()), {})
    assert "QQ 短句" in frag, "缺文风底色行"
    assert "不排比" in frag and "不列点" in frag
    assert "首先/其次" in frag
    assert "文风：QQ 短句" in _PRESENCE, "文风行必须焊在 _PRESENCE 常量内（继承预算豁免）"


def test_fragment_within_reasonable_bound() -> None:
    """片段总长有界（态度常量 + 截断后状态行，不会无限膨胀）。"""
    um = UserModelDomain()
    big_memes = {f"超长梗说法{i}xxxxxxxx": {"count": 9.0, "first_arousal": 0.9, "last_turn": 1.0}
                 for i in range(30)}
    um.load_dict({"memes": big_memes})
    domains = {"usermodel": um}
    frag = build_mind_fragment(_ctx(_body(), domains), domains)
    # 态度常量恒在末尾不被截，但状态行被削——总长 ≈ header + 预算 + 态度，留余量
    assert len(frag) <= _MAX_CHARS + len(_PRESENCE) + 20, f"片段超界: {len(frag)}"
