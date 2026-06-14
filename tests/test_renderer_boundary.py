"""tests/test_renderer_boundary.py —— Renderer / HostSink 出口边界回归。

锁死设计 §4「内部结构 ↔ 用户可见消息唯一边界」的四类历史事故（contracts.py 行
210-215 列举的同一道根因），任何重写都不得复发：

  #1 裸 repr 泄漏    —— MessageChain / BodySnapshot / dict 被 str() 当正文发出。
  #2 静默装死        —— 主链产出为空时静默清空回复（分不清“出错空”与“故意不说”）。
  #4 内部对象漏出口  —— 非 str 负载混进对外消息分段。
  + draft 禁 SILENT  —— 宿主已生成草稿（被问），Sylanne 只调味不吞答。

renderer.py 未落地时整文件 skip（importorskip 兜底）；已落地则全用例生效。

【对齐契约】（已对实装 renderer.py 校准，签名变更须同步本文件而非绕断言）：
  - DefaultRenderer(*, fallback_text=..., register_defaults=True)
      .register_projector(projector)            # 实例方法；projector 自带 .source
      .render(ctx, draft=None) -> Reply          # total：永不抛、永不 None、必带 kind
  - Projector.project(intent, ctx) -> str | None   # 投影产物是 str，非 str 在二道闸被丢
  - ProjectionUnit(text: str, ...)                 # __post_init__ 拒非 str（#4 一道闸）
  - StateProjector.source == "state_query"；._narrate(body) -> str（纯模板，零 LLM，P11）
  - HostSink._to_chain(text: str) -> MessageChain | str
        非 str → AssertionError（#4）；astrbot 不在 sys.modules → 回退返原 str
  - 模式区分：draft 非 None = 被问必答(禁 SILENT)；draft is None = compose(可显式 SILENT)。
    compose 静默经 ctx.scratch["silent"]（str / dict{reason} / 真值）或 Intent flag 'silent'。

D8 冲突已被实装按【模式】消解：主控铁律“draft 禁 SILENT”落在 draft 模式；
D8“她得会装死”落在 compose 模式且 SILENT 必带 reason（强制留痕）。本文件双向都测。
"""

from __future__ import annotations

import pytest

from sylanne_alpha.v2core.contracts import (
    BeatContext,
    BodySnapshot,
    Intent,
    ReplyKind,
)

# renderer.py 是 Tier1 出口层，尚未落地时整文件 skip（草案先行，实装后自动生效）。
renderer = pytest.importorskip(
    "sylanne_alpha.v2core.renderer",
    reason="sylanne_alpha/v2core/renderer.py 未落地（Tier1 待实现）",
)

# ---------------------------------------------------------------------------
# 最小构造夹具
# ---------------------------------------------------------------------------

def _body(session_key: str = "u:test", **over: object) -> BodySnapshot:
    """构造一个最小 BodySnapshot；over 覆盖具名字段（如 warmth/personality）。"""
    base: dict[str, object] = {
        "session_key": session_key,
        "turns": 3,
        "warmth": 0.4,
        "tension": 0.2,
        "repair_pressure": 0.0,
        "intimacy_gravity": 0.6,
        "personality": {"warmth": 0.7, "openness": 0.5},
    }
    base.update(over)
    return BodySnapshot(**base)  # type: ignore[arg-type]


def _ctx(
    *,
    intents: list[Intent] | None = None,
    text: str = "在吗",
    scratch: dict[str, object] | None = None,
    body: BodySnapshot | None = None,
) -> BeatContext:
    """构造一个最小 BeatContext（contracts.BeatContext），供 render 直接消费。"""
    snap = body if body is not None else _body()
    ctx = BeatContext(
        session_key=snap.session_key,
        event=object(),                 # 渲染层不该真的去碰宿主事件
        body=snap,
        text=text,
        current_warmth=snap.warmth,
    )
    if intents:
        for it in intents:
            ctx.add(it)
    if scratch:
        ctx.scratch.update(scratch)
    return ctx


def _skip_unless(*names: str) -> None:
    """assumed 契约缺名即 skip（草案不误判：实装签名不同请同步本文件）。"""
    missing = [n for n in names if not hasattr(renderer, n)]
    if missing:
        pytest.skip(f"renderer 缺假定符号 {missing}，本用例待实装对齐")


# 假投影器：认领某个 source，把 payload['say'] 投影成 str（注册才出口的白名单路径）。
class _EchoProjector:
    """最小 Projector：取 payload['say'] 当正文，返回 str（契约：project -> str | None）。"""

    def __init__(self, source: str = "echo") -> None:
        self.source = source

    def project(self, intent: Intent, ctx: BeatContext) -> str | None:
        say = intent.payload.get("say")
        if not isinstance(say, str) or not say.strip():
            return None
        return say


def _mk_renderer(*projectors: object, register_defaults: bool = True):
    """构造 DefaultRenderer 并经实例方法注册 projector（实装 API：register_projector(proj)）。"""
    cls = getattr(renderer, "DefaultRenderer")
    inst = cls(register_defaults=register_defaults)
    for proj in projectors:
        inst.register_projector(proj)
    return inst


def _all_text(reply) -> str:  # noqa: ANN001
    """把 Reply.parts 拼平，断言时检“可见文本里有没有泄漏”。"""
    return "\n".join(reply.parts)


# ===========================================================================
# #2 装死：空 intents 且无 draft → FALLBACK 且有可见文本（绝非静默空）
# ===========================================================================

def test_empty_intents_no_draft_returns_visible_fallback() -> None:
    _skip_unless("DefaultRenderer")
    rnd = _mk_renderer()
    reply = rnd.render(_ctx(intents=[], scratch=None))

    assert reply is not None, "render 绝不返 None（出口必带 kind）"
    assert reply.kind is ReplyKind.FALLBACK, (
        f"空产出且无草稿应兜底 FALLBACK，实得 {reply.kind}（#2 装死复发）"
    )
    assert reply.kind is not ReplyKind.SILENT, "空≠静默：必须区分‘出错空’与‘故意不说’"
    visible = _all_text(reply)
    assert visible.strip(), "FALLBACK 必须有可见文本，不能是静默空回复（#2）"


def test_render_never_returns_none_on_degenerate_input() -> None:
    """退化输入（空文本 + 空 intents + 空 scratch）也必须给出带 kind 的 Reply。"""
    _skip_unless("DefaultRenderer")
    rnd = _mk_renderer()
    reply = rnd.render(_ctx(intents=[], text="", scratch={}))
    assert reply is not None
    assert isinstance(reply.kind, ReplyKind)
    assert reply.kind is not ReplyKind.SILENT, "无表达策略时的空产出不得静默吞掉"


# ===========================================================================
# #1 / #4 泄漏：未注册 source 的 Intent 不进 parts；非 str 分段被拒
# ===========================================================================

def test_unregistered_source_intent_not_in_reply_parts() -> None:
    """payload 带 dict/对象但 source 未注册 projector → 不得出现在 Reply.parts（#1/#4）。"""
    _skip_unless("DefaultRenderer", "ProjectionUnit")
    leaky = Intent(
        source="unregistered_tool",
        payload={"diagnostics": {"hot_pool": [1, 2, 3]}, "obj": object()},
        priority=0.9,
    )
    # 同时给一个已注册的正常意图，确保 render 本身在“说话”，只是不带泄漏内容。
    good = Intent(source="echo", payload={"say": "嗯，我在。"}, priority=0.5)
    rnd = _mk_renderer(_EchoProjector("echo"))
    reply = rnd.render(_ctx(intents=[good, leaky]))

    visible = _all_text(reply)
    assert "diagnostics" not in visible, "内部 diagnostics 不得泄漏进可见正文（#1）"
    assert "hot_pool" not in visible, "内部状态键不得泄漏进可见正文（#1）"
    assert "object at 0x" not in visible, "裸对象 repr 不得泄漏进可见正文（#1）"
    assert "{" not in visible and "}" not in visible, "dict 字面不得出现在正文（#4）"
    # 每个分段都必须是纯字符串（Reply.parts 的类型护栏在渲染层就该成立）。
    for p in reply.parts:
        assert isinstance(p, str), f"Reply.parts 含非 str 分段：{type(p)}（#4）"


def test_hostsink_to_chain_rejects_non_str_arg() -> None:
    """HostSink._to_chain 传非 str → AssertionError（出口处类型焊死，#4 一道闸）。"""
    _skip_unless("HostSink")
    sink = getattr(renderer, "HostSink")()
    to_chain = getattr(sink, "_to_chain", None)
    if to_chain is None:
        pytest.skip("HostSink 未暴露 _to_chain，待实装对齐")
    with pytest.raises(AssertionError):
        to_chain({"leak": "dict"})   # dict 当正文 → 必须炸（堵 diagnostics JSON 泄漏）
    with pytest.raises(AssertionError):
        to_chain(object())           # 裸对象 → 必须炸（堵 MessageChain repr 泄漏）
    with pytest.raises(AssertionError):
        to_chain(["已经是分段列表"])  # list 也非 str → 必须炸（_to_chain 只吃单段 str）


def test_hostsink_to_chain_accepts_pure_str() -> None:
    """纯 str 正文应被 HostSink 正常接受（正路不被护栏误伤），且回退仍是 str。"""
    _skip_unless("HostSink")
    sink = getattr(renderer, "HostSink")()
    to_chain = getattr(sink, "_to_chain", None)
    if to_chain is None:
        pytest.skip("HostSink 未暴露 _to_chain，待实装对齐")
    out = to_chain("第一段\n第二段")
    assert out is not None, "合法纯 str 不应被拒"
    # astrbot 未加载时按契约回退为原 str；已加载则可能是 MessageChain（不强断类型）。
    import sys
    if not any(m == "astrbot" or m.startswith("astrbot.") for m in sys.modules):
        assert isinstance(out, str) and "第一段" in out, "astrbot 缺位时须回退原 str"


# ===========================================================================
# draft 模式禁 SILENT：被问必答，Sylanne 只调味不吞答
# ---------------------------------------------------------------------------
# D8 冲突的消解（实装已落）：主控铁律“draft 禁 SILENT”与设计 D8“她得会装死”按【模式】
# 分治——draft 非 None = 被问必答(禁 SILENT，本节)；draft is None = compose(可显式 SILENT，
# 下一节)。两条路径本文件都测，互不矛盾。
# ===========================================================================

# draft 模式 SILENT 语义（D8 反转，2026-06-12 / REVIEW §P0-2）
# ---------------------------------------------------------------------------
# D8 锁定决议反转：draft 模式【也能】SILENT——有【显式】静默决策（scratch['silent'] /
# Intent silent flag，如 IgnitionArbiter 的 hold）时，被问也能"装死"，唯一要求显式决策 +
# reason + 强制日志。无显式静默决策时维持"被问必答"。两条路径本文件都测。
# ===========================================================================

def test_draft_present_honors_explicit_silent() -> None:
    """draft 非空 + 显式 scratch['silent'] → SILENT（D8 反转：被问也能装死，REVIEW §P0-2）。"""
    _skip_unless("DefaultRenderer")
    draft_text = "你刚问的那个配置，在 settings.yaml 的第 12 行。"
    rnd = _mk_renderer()
    # draft 经 render(ctx, draft=...) 传入；有【显式】静默决策（点火 hold）时 draft 模式也 SILENT。
    reply = rnd.render(
        _ctx(intents=[], text="配置在哪？", scratch={"silent": "ignition_hold"}),
        draft=draft_text,
    )
    assert reply.kind is ReplyKind.SILENT, (
        "draft 模式遇显式静默决策应 SILENT（D8 反转：被问也能装死）"
    )
    assert reply.meta.get("reason"), "SILENT 必带 reason（可观测）"


def test_draft_present_speaks_without_silent_decision() -> None:
    """draft 非空 + 无显式静默决策 → 被问必答（维持原语义不变）。"""
    _skip_unless("DefaultRenderer")
    draft_text = "你刚问的那个配置，在 settings.yaml 的第 12 行。"
    rnd = _mk_renderer()
    reply = rnd.render(_ctx(intents=[], text="配置在哪？", scratch={}), draft=draft_text)
    assert reply.is_speaking, "无显式静默 + 有草稿 → 必须真的说话（被问必答）"
    assert draft_text in _all_text(reply), "宿主草稿正文必须被保留（只调味不吞答）"


def test_silent_allowed_only_in_compose_mode() -> None:
    """compose 模式（draft=None）+ scratch['silent'] → 允许 SILENT 且必带 reason（D8 可观测）。"""
    _skip_unless("DefaultRenderer")
    rnd = _mk_renderer()
    reply = rnd.render(
        _ctx(intents=[], text="……", scratch={"silent": "withdrawn_by_mood"}),
    )
    assert reply is not None
    assert reply.kind is ReplyKind.SILENT, (
        f"compose 模式显式静默应落 SILENT（人格驱动装死），实得 {reply.kind}"
    )
    assert reply.meta.get("reason"), "SILENT 必须带 reason（可观测，区别于无声故障 FALLBACK）"


# ===========================================================================
# StateProjector：BodySnapshot 投影出的是人话 str，不含 json / 裸 repr（P11）
# ===========================================================================

def test_state_projector_emits_human_text_not_json() -> None:
    _skip_unless("StateProjector")
    proj = getattr(renderer, "StateProjector")()
    narrate = getattr(proj, "_narrate", None)
    if narrate is None:
        pytest.skip("StateProjector 未暴露 _narrate，待实装对齐")
    body = _body(warmth=0.6, tension=0.3, intimacy_gravity=0.7,
                 personality={"warmth": 0.8, "openness": 0.4})
    out = narrate(body)

    assert isinstance(out, str), "状态投影必须产出 str（人话），不得返回结构对象"
    assert out.strip(), "状态投影不得为空串"
    # 不含 JSON / dict 字面 / 裸 repr 痕迹。
    for bad in ("{", "}", "[", "]", "BodySnapshot(", "object at 0x",
                "warmth=", "session_key", "'", '"'):
        assert bad not in out, f"状态投影泄漏内部表征片段 {bad!r}：{out!r}"


def test_state_projector_through_render_no_leak() -> None:
    """经 render 全链投影状态：可见正文是人话，不得出现 BodySnapshot 字段名 / 裸 repr。"""
    _skip_unless("DefaultRenderer", "StateProjector")
    src = getattr(renderer, "StateProjector").source   # 实装 source == "state_query"
    state_intent = Intent(source=src, payload={}, priority=0.5)
    # StateProjector 默认已注册（register_defaults=True），其 project 读 ctx.body 而非 payload。
    rnd = _mk_renderer()
    reply = rnd.render(_ctx(intents=[state_intent], text="你现在怎么样？",
                            body=_body(warmth=0.6, intimacy_gravity=0.7)))
    assert reply.is_speaking, "状态查询应投影出可见自述"
    visible = _all_text(reply)
    for bad in ("BodySnapshot(", "session_key", "intimacy_gravity", "warmth=",
                "object at 0x", "{", "}"):
        assert bad not in visible, f"状态经 render 仍泄漏 {bad!r}：{visible!r}"


# ===========================================================================
# HostSink astrbot 缺失回退：返 str 而非崩溃（宿主依赖缺位时不连累出口）
# ===========================================================================

def test_hostsink_degrades_to_str_when_astrbot_missing(monkeypatch) -> None:  # noqa: ANN001
    """astrbot 不在 sys.modules 时 HostSink._to_chain 回退返原 str（不崩、不漏内部对象）。

    实装 _to_chain 经 sys.modules.get('astrbot.api.event') 取宿主组件（懒、可测）；
    故把这些键置 None 即可确定性地走“astrbot 缺位”分支，无需真卸载已加载模块。
    """
    _skip_unless("HostSink")
    sink = getattr(renderer, "HostSink")()
    to_chain = getattr(sink, "_to_chain", None)
    if to_chain is None:
        pytest.skip("HostSink 未暴露 _to_chain，待实装对齐")

    import sys
    # 强制“astrbot 组件不可用”分支（setitem None → sys.modules.get 返 None）。
    monkeypatch.setitem(sys.modules, "astrbot.api.event", None)
    monkeypatch.setitem(sys.modules, "astrbot.api.message_components", None)

    out = to_chain("纯文本回退分段")
    assert isinstance(out, str), "astrbot 缺位时应回退为 str，而非抛错或返回内部对象"
    assert out == "纯文本回退分段", "回退 str 须原样保留正文"

