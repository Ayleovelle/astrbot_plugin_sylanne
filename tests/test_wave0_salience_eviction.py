"""Wave 0 + Wave 1 装配保证 —— 真·过预算场景下的显著性淘汰 + 钉行永生 + Wave 1 余量。

现有 test_presence_* / test_focus_line_survives_truncation 因领域行自限长，实际从未
真把 STATE 撑过 _MAX_CHARS——它们只验"恒在常量在"。本文件用受控长度的桩领域故意撑爆
预算，钉死 Wave 0/1 的真实契约：

- PINNED（表达倾向/话头/临场态度）在 STATE 真溢出时永生；
- STATE 按最低显著性整行淘汰（自我行最先丢，召回行最后丢）；
- 幸存行【整行完整】出现，绝无半句残断（mid-sentence cut 像坏掉的 AI，铁律禁止）；
- Wave 1：临场态度移出预算分母后，STATE 拿回 ~200 字——旧实现会截掉的中等长度状态今全留。
"""

from __future__ import annotations

from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase
from sylanne_alpha.v2core.fragment import (
    build_mind_fragment,
    _PRESENCE,
    _MAX_CHARS,
    _HEADER,
)


# --------------------------------------------------------------------------
# 受控长度桩领域：prompt_line 直接吐定长串，便于精确撑爆预算 + 子串校验
# --------------------------------------------------------------------------

def _line(token: str, n: int = 150) -> str:
    """造一条带唯一标记、定长 n 的状态行（标记在头，便于断言整行幸存/被淘汰）。"""
    body = "测" * max(0, n - len(token))
    return token + body


class _Emo:
    def __init__(self, text: str) -> None:
        self.text = text

    def prompt_line(self, body) -> str:  # noqa: ANN001
        return self.text


class _UM:
    def __init__(self, text: str) -> None:
        self.text = text

    def prompt_line(self) -> str:
        return self.text


class _Narr:
    def __init__(self, text: str) -> None:
        self.text = text

    def prompt_line(self) -> str:
        return self.text


class _Mem:
    def __init__(self, text: str) -> None:
        self.text = text

    def recall_prompt_line(self, recalled, **kw) -> str:  # noqa: ANN001
        return self.text


class _Foc:
    """话头桩（FocusDomain）：build_mind_fragment 以 ctx.text 调 prompt_line 取话头行。"""

    def __init__(self, text: str) -> None:
        self.text = text

    def prompt_line(self, text: str) -> str:  # noqa: ANN001
        return self.text


def _ctx(body: BodySnapshot, domains: dict, *, recalled: bool = False) -> BeatContext:
    c = BeatContext(session_key="u", event=None, body=body, text="测试文本",
                    phase=Phase.PERCEPT, domains=domains)
    if recalled:
        c.scratch["recalled"] = [{"id": "m1"}]
    return c


# guard=0.85（>0.45）→「措辞带防备」；tension=0.9（>0.5）→「语气偏紧」；warmth 高→情绪行显著性高
_GUARDED_HOT = dict(sovereignty=0.3, strain=0.5, warmth=0.9, tension=0.9)


def test_style_line_survives_genuine_state_overflow() -> None:
    """Wave 0 keystone：4 条 ~150 字 STATE 撑爆预算时，表达倾向(PINNED)永生。

    这是旧实现做不到的——旧实现 _style_line 最后入列、盲截尾巴时第一个死。
    """
    emo = _Emo(_line("情绪EMOTOKEN"))
    um = _UM(_line("对你UMTOKEN"))
    narr = _Narr(_line("自我NARRTOKEN"))
    mem = _Mem(_line("记忆MEMTOKEN"))
    domains = {"emotion": emo, "usermodel": um, "narrative": narr, "memory": mem}
    body = BodySnapshot(session_key="u", turns=1, **_GUARDED_HOT)
    frag = build_mind_fragment(_ctx(body, domains, recalled=True), domains)

    # PINNED 全在
    assert "表达倾向" in frag and "措辞带防备" in frag, "表达倾向行(PINNED)被淘汰了——Wave 0 失败"
    assert _PRESENCE in frag, "临场态度(PINNED)被淘汰了"


def test_focus_line_survives_genuine_state_overflow() -> None:
    """Wave 0 keystone：focus_line(PINNED 话头) 在 STATE 真溢出时永生。

    补全 PINNED 覆盖——原 style 用例只钉 style 行，此条钉 focus_line：4 条 ~150 字 STATE
    撑爆预算时，话头行绝不被淘汰，靠丢最低显著性 STATE(自我行) 恢复预算。
    """
    foc = _Foc(_line("话头FOCUSTOKEN"))
    emo = _Emo(_line("情绪EMOTOKEN"))
    um = _UM(_line("对你UMTOKEN"))
    narr = _Narr(_line("自我NARRTOKEN"))
    mem = _Mem(_line("记忆MEMTOKEN"))
    domains = {"focus": foc, "emotion": emo, "usermodel": um, "narrative": narr, "memory": mem}
    body = BodySnapshot(session_key="u", turns=1, **_GUARDED_HOT)
    frag = build_mind_fragment(_ctx(body, domains, recalled=True), domains)

    assert "话头FOCUSTOKEN" in frag, "话头行(PINNED)在 STATE 溢出时被淘汰了——Wave 0 失败"
    assert "自我NARRTOKEN" not in frag, "最低显著性 STATE(自我行) 该先丢给 PINNED 让预算"


def test_lowest_salience_evicted_first() -> None:
    """STATE 按显著性整行淘汰：召回(3.0)/情绪(~2.0) 留，对你(0.8)/自我(0.4) 先丢。"""
    emo = _Emo(_line("情绪EMOTOKEN"))
    um = _UM(_line("对你UMTOKEN"))
    narr = _Narr(_line("自我NARRTOKEN"))
    mem = _Mem(_line("记忆MEMTOKEN"))
    domains = {"emotion": emo, "usermodel": um, "narrative": narr, "memory": mem}
    body = BodySnapshot(session_key="u", turns=1, **_GUARDED_HOT)
    frag = build_mind_fragment(_ctx(body, domains, recalled=True), domains)

    # 高显著性幸存
    assert "记忆MEMTOKEN" in frag, "召回行(显著性最高)不该被淘汰"
    assert "情绪EMOTOKEN" in frag, "高温情绪行(显著性高)不该被淘汰"
    # 低显著性被淘汰
    assert "自我NARRTOKEN" not in frag, "自我行(显著性最低)该最先被淘汰"
    assert "对你UMTOKEN" not in frag, "对你行(次低显著性)该被淘汰"
    # 幸存 STATE 保持 canonical 渲染序：记忆(order1) 在 情绪(order2) 之前（淘汰只动成员、不乱序）
    assert frag.index("记忆MEMTOKEN") < frag.index("情绪EMOTOKEN"), "STATE 渲染序被打乱了(记忆应在情绪前)"


def test_no_mid_sentence_cut_on_survivors() -> None:
    """幸存行整行完整出现——绝不切半句（铁律：mid-sentence cut 像坏掉的 AI）。"""
    emo_text = _line("情绪EMOTOKEN")
    mem_text = _line("记忆MEMTOKEN")
    domains = {
        "emotion": _Emo(emo_text),
        "usermodel": _UM(_line("对你UMTOKEN")),
        "narrative": _Narr(_line("自我NARRTOKEN")),
        "memory": _Mem(mem_text),
    }
    body = BodySnapshot(session_key="u", turns=1, **_GUARDED_HOT)
    frag = build_mind_fragment(_ctx(body, domains, recalled=True), domains)

    # 幸存的两行必须【完整】在片段里（而非被截成前缀）
    assert emo_text in frag, "情绪行被切成了半句"
    assert mem_text in frag, "召回行被切成了半句"


def test_total_length_bounded() -> None:
    """总长有界：header + 活体块(≤_MAX_CHARS) + 临场态度。"""
    domains = {
        "emotion": _Emo(_line("情绪EMOTOKEN")),
        "usermodel": _UM(_line("对你UMTOKEN")),
        "narrative": _Narr(_line("自我NARRTOKEN")),
        "memory": _Mem(_line("记忆MEMTOKEN")),
    }
    body = BodySnapshot(session_key="u", turns=1, **_GUARDED_HOT)
    frag = build_mind_fragment(_ctx(body, domains, recalled=True), domains)
    # header(25)+空格(1)+活体块(≤420)+" | "(3)+临场态度(218) 的宽松上界
    assert len(frag) <= _MAX_CHARS + len(_PRESENCE) + len(_HEADER) + 10, f"超界:{len(frag)}"


def test_wave1_state_headroom_reclaimed() -> None:
    """Wave 1：临场态度移出预算分母后，中等长度 STATE 全留（旧实现会截掉）。

    旧实现 reserved 含 len(_PRESENCE)=218，无 focus/memory 时 STATE 预算仅 ~168 字。
    两条 ~150 字状态(共~300)旧实现必截一半；新实现 STATE 预算 ~390，两条整留。
    """
    emo_text = _line("情绪EMOTOKEN", 150)
    um_text = _line("对你UMTOKEN", 150)
    domains = {"emotion": _Emo(emo_text), "usermodel": _UM(um_text)}
    body = BodySnapshot(session_key="u", turns=1, warmth=0.5)
    frag = build_mind_fragment(_ctx(body, domains), domains)

    assert emo_text in frag, "Wave 1 预算回收失败：中等长度情绪行被截"
    assert um_text in frag, "Wave 1 预算回收失败：中等长度对你行被截"
    assert _PRESENCE in frag


def _pad(prefix: str, n: int = 150) -> str:
    return prefix + "测" * max(0, n - len(prefix))


def test_loud_emotion_line_outranks_moderate_usermodel() -> None:
    """情绪行响度来自行文本(trend/比平时/未表达)，不只瞬时躯体——补分后滚烫情绪压过中等对你行。

    钉死 review behavior-diff 的修复：body.warmth≈0/tension≈0 时，若只看瞬时躯体，情绪只得 1.0，
    会输给处置较响的对你行(0.8+0.5+0.3=1.6)被淘汰；从行文本嗅"骤然/暖得多/憋了很多话"补分到
    ~2.5 后，滚烫情绪反超存活、对你行被淘汰。
    """
    emo_text = _pad("情绪EMOTOKEN骤然升温比平时暖得多憋了很多话")  # 含响度词
    um_text = _pad("对你UMTOKEN印象还浅")
    mem_text = _pad("记忆MEMTOKEN")
    domains = {"emotion": _Emo(emo_text), "usermodel": _UM(um_text), "memory": _Mem(mem_text)}
    body = BodySnapshot(session_key="u", turns=1, warmth=0.0, tension=0.0)
    ctx = _ctx(body, domains, recalled=True)
    ctx.scratch["you_probably"] = {"disposition": {"warmth": 0.5, "distress": 0.3}}
    frag = build_mind_fragment(ctx, domains)

    assert "情绪EMOTOKEN" in frag, "滚烫情绪行该靠响度补分存活（修复失败则它被误淘汰）"
    assert "记忆MEMTOKEN" in frag, "召回行(最高显著性)恒存活"
    assert "对你UMTOKEN" not in frag, "中等显著性对你行该让位给更响的情绪行"


def test_cold_start_still_only_presence() -> None:
    """冷启动（无状态）：片段仅 header + 临场态度，不空、不报错。"""
    body = BodySnapshot(session_key="u", turns=0)
    frag = build_mind_fragment(_ctx(body, {}), {})
    assert frag and _PRESENCE in frag
    assert frag.startswith(_HEADER)
