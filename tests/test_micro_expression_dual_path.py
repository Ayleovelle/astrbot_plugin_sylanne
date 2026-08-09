"""micro_expression 双路调味测试 —— 半句/停顿/回撤进入"话本身"（A+B 双路单源）。

背景：在此之前，user_model 的关系慢变量（犹豫/苦恼/亲密）只进了两处——
心象 prompt_line（给 LLM 读的"对你"行）与窄窄的 state_query 自述路径。用户 99%
会走的【主对话 draft 路径】对"话本身怎么说"零影响。

本次接线把同一批 EMA 经 UserModelDomain.micro_expression() 渲染成两种受众形式：
- B 路径：directive → prompt_line "说话方式:" 行，作为行文倾向喂 LLM 自己写半句/改口；
- A 路径：lead → DefaultRenderer 在 draft 草稿【前】兜底前置停顿引子，只前置不改正文。

红线（本文件钉死，任何重写不得复发）：
- 中性态 / 无 usermodel 域 → A 路径 lead 空 = 草稿【原样】透传（守 test_renderer_boundary
  #247"被问必答不吞答"：draft 原文恒为结果子串）；
- micro_expression 是【单一来源】：A 的 lead 与 B 的 directive 读同一批底层 EMA，
  公式只此一份（吸取 F2 guard/soften 双写教训）。
"""

from __future__ import annotations

from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase
from sylanne_alpha.v2core.domains.user_model import UserModelDomain
from sylanne_alpha.v2core.renderer import DefaultRenderer
from sylanne_alpha.v2core.contracts import ReplyKind


def _ctx(text: str, turn: int = 1, **kw) -> BeatContext:
    body = BodySnapshot(session_key="u", turns=turn, warmth=kw.get("warmth", 0.0),
                        tension=kw.get("tension", 0.0))
    ctx = BeatContext(session_key="u", event=None, body=body, text=text,
                      domains={"usermodel": None})
    ctx.phase = Phase.EVOLVE
    ctx.scratch["signals"] = None
    ctx.scratch["assessment"] = {"arousal": kw.get("arousal", 0.0)}
    return ctx


def _shaky(um: UserModelDomain) -> None:
    """确定性注入一个"受伤又防备"的关系态（仿真用 load_dict，避开 EMA 爬升速度
    与词表读数的不确定——同 test_v2_verbal_mapping 直接 load_dict 的惯例）。

    hesitation_ema=0.35 → pause>0.28（lead="……"）且 withdraw（>0.3）；
    distress=0.4 → _distress_bias≈0.61>0.3（length="short"）。三者同时点亮 directive。
    """
    um.load_dict({
        "hesitation_ema": 0.35,
        "disposition": {"warmth": -0.3, "engagement": 0.0,
                        "defensiveness": 0.3, "distress": 0.4},
    })


def _shaky_via_ingest(um: UserModelDomain, rounds: int = 12) -> None:
    """真·ingest 路径把 hesitation 喂过阈值——证实强迟疑态在实弹路径可达
    （非只靠 load_dict 构造）。慢 EMA 需约 8+ 轮短促带刺消息累积。"""
    for i in range(rounds):
        um.ingest(_ctx("别问了……", turn=i + 1, arousal=0.7, warmth=-0.3,
                       tension=0.5))


# ===========================================================================
# micro_expression：单一来源，三态字段齐全
# ===========================================================================

def test_micro_expression_neutral_is_empty() -> None:
    """冷启动中性态：lead 空、directive 空——A 路径据此原样透传，B 路径不占提示位。"""
    mx = UserModelDomain().micro_expression()
    assert mx["lead"] == ""
    assert mx["directive"] == ""
    assert mx["withdraw"] is False
    assert mx["length"] == ""


def test_micro_expression_shaky_emits_pause_and_directive() -> None:
    """强迟疑态：lead 出现停顿引子，directive 描述"顿一下/收短"——两者同源。"""
    um = UserModelDomain()
    _shaky(um)
    mx = um.micro_expression()
    assert mx["lead"] in ("……", "嗯……"), f"强迟疑应给停顿引子，实得 {mx['lead']!r}"
    assert mx["directive"], "强迟疑应给行文倾向 directive"
    assert "顿" in mx["directive"] or "短" in mx["directive"] or "收回" in mx["directive"]


def test_micro_expression_single_source_lead_matches_pause() -> None:
    """A(lead) 与 B(directive) 读同一状态：lead 非空 ⇒ directive 必含"顿"字（同源不漂移）。"""
    um = UserModelDomain()
    _shaky(um)
    mx = um.micro_expression()
    if mx["lead"]:
        assert "顿" in mx["directive"], "lead 与 directive 必须同源：有停顿引子就该有顿一下的倾向"


def test_shaky_state_reachable_via_real_ingest() -> None:
    """可达性：强迟疑态不只靠 load_dict 构造——真 ingest 路径累积短促带刺消息后，
    micro_expression 真的点亮停顿/收短倾向（证实非死态，实弹可达）。"""
    um = UserModelDomain()
    _shaky_via_ingest(um)
    mx = um.micro_expression()
    assert mx["lead"] or mx["directive"], (
        "连续短促带刺消息后应累积出迟疑/收短倾向，实得全空（信道未生效）"
    )


# ===========================================================================
# B 路径：directive 进 prompt_line "说话方式:" 行
# ===========================================================================

def test_prompt_line_carries_speaking_style_when_shaky() -> None:
    """强迟疑态 prompt_line 带出"说话方式:"行（喂 LLM 写半句/改口的行文倾向）。"""
    um = UserModelDomain()
    _shaky(um)
    line = um.prompt_line()
    assert "说话方式:" in line, f"强迟疑态应注入说话方式行: {line}"


def test_prompt_line_no_speaking_style_when_neutral() -> None:
    """中性态 prompt_line 不臆造"说话方式:"行（directive 空就不占提示位）。"""
    line = UserModelDomain().prompt_line()
    assert "说话方式:" not in line


# ===========================================================================
# A 路径：renderer draft 调味——红线 #247 与中性透传
# ===========================================================================

def _draft_ctx(um, text: str = "你问的那个在 settings.yaml 第 12 行。") -> BeatContext:
    body = BodySnapshot(session_key="u", turns=3)
    ctx = BeatContext(session_key="u", event=None, body=body, text="配置在哪？",
                      domains={"usermodel": um} if um is not None else {})
    return ctx


def test_draft_passthrough_when_no_usermodel_domain() -> None:
    """无 usermodel 域（测试态/冷启动）：草稿原样透传，原文恒为结果子串（#247）。"""
    rnd = DefaultRenderer()
    draft = "你问的那个在 settings.yaml 第 12 行。"
    reply = rnd.render(_draft_ctx(None, draft), draft=draft)
    assert reply.kind is ReplyKind.SPEAK
    assert draft in "".join(reply.parts), "无域时草稿必须原样保留（被问必答不改正文）"


def test_draft_passthrough_when_neutral_state() -> None:
    """有 usermodel 域但中性态：lead 空 → 草稿仍原样透传（中性不调味）。"""
    rnd = DefaultRenderer()
    um = UserModelDomain()                       # 冷启动中性
    draft = "你问的那个在 settings.yaml 第 12 行。"
    reply = rnd.render(_draft_ctx(um, draft), draft=draft)
    assert draft in "".join(reply.parts), "中性态不该改动草稿"
    assert not "".join(reply.parts).startswith(("…", "嗯…")), "中性态不该前置停顿"


def test_draft_gets_pause_lead_when_shaky() -> None:
    """强迟疑态：草稿【前】兜底前置停顿引子，且草稿原文仍完整保留（只前置不改正文）。"""
    rnd = DefaultRenderer()
    um = UserModelDomain()
    _shaky(um)
    draft = "你问的那个在 settings.yaml 第 12 行。"
    reply = rnd.render(_draft_ctx(um, draft), draft=draft)
    joined = "".join(reply.parts)
    assert draft in joined, "红线 #247：草稿原文必须完整保留（只前置不改正文）"
    assert joined.startswith(("…", "嗯…")), f"强迟疑应前置停顿引子: {joined!r}"


def test_draft_no_double_pause_when_draft_already_hesitant() -> None:
    """草稿已自带开头停顿 → 不重复堆叠（避免"…………"）。"""
    rnd = DefaultRenderer()
    um = UserModelDomain()
    _shaky(um)
    draft = "……我想想，应该在第 12 行。"
    reply = rnd.render(_draft_ctx(um, draft), draft=draft)
    joined = "".join(reply.parts)
    assert joined == draft, f"草稿已自带停顿不应再叠加: {joined!r}"
