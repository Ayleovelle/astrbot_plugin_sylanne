"""Wave 6 PR-B：StyleMirror（口吻镜像）+ TopicAffinity（话题亲和）学习 + 心象注入。

四路径覆盖（团队规范 §四路径）：
- 正常：bond 闸内收敛 / 话题亲和涨-衰减-LRU / prompt_line 出风格&话题提示 / 端到端进 fragment；
- 异常：bond 不够不动 / 敌意背离 / sketch 空不动 / 非 EVOLVE 不写 / 长 gist 不当话题报；
- 兼容：PR-A 旧档（无 style_target/topics）空起步后 PR-B ingest 照常 + 新状态 round-trip；
- 回退：缺 usermodel/focus 不崩 / 脏 scratch 降级 / 跨域 getter 抛错只跳该子步 / prompt_line 异常返空。
"""

from __future__ import annotations

from types import SimpleNamespace

from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase
from sylanne_alpha.v2core.domains.adaptation import AdaptationDomain
from sylanne_alpha.v2core.fragment import build_mind_fragment
from sylanne_alpha.v2core.lexicon import read_signals


def _um(bond: float = 0.5, sketch: dict | None = None, defensiveness: float = 0.0):
    sk = {} if sketch is None else dict(sketch)
    return SimpleNamespace(
        bond=lambda: bond,
        style_sketch=lambda: dict(sk),
        expectation=lambda: {"warmth": 0.0, "engagement": 0.0,
                             "defensiveness": defensiveness, "distress": 0.0},
    )


def _focus(current: str = ""):
    return SimpleNamespace(current=current)


def _ctx(*, domains=None, scratch=None, text: str = "", turns: int = 1,
         phase: Phase = Phase.EVOLVE) -> BeatContext:
    c = BeatContext(session_key="u", event=None,
                    body=BodySnapshot(session_key="u", turns=turns),
                    text=text, phase=phase, domains=domains or {})
    if scratch:
        c.scratch.update(scratch)
    return c


# ---- 正常路径 -------------------------------------------------------------

def test_style_lazy_init_then_converges() -> None:
    ad = AdaptationDomain()
    ad.ingest(_ctx(domains={"usermodel": _um(0.5, {"len": 10.0, "punct": 2.0, "warmth": 3.0}),
                            "focus": _focus("")}))
    assert ad._style_target == {"len": 10.0, "punct": 2.0, "warmth": 3.0}  # 惰性初始化为首观测
    # 改 sketch → 向新值收敛一步 0.03：10 + 0.03*(20-10) = 10.3
    ad.ingest(_ctx(domains={"usermodel": _um(0.5, {"len": 20.0, "punct": 2.0, "warmth": 3.0}),
                            "focus": _focus("")}))
    assert abs(ad._style_target["len"] - 10.3) < 1e-6


def test_topic_affinity_rises_then_decays_and_records_new() -> None:
    ad = AdaptationDomain()
    ad.ingest(_ctx(domains={"usermodel": _um(), "focus": _focus("毕设")},
                   scratch={"signals": read_signals("我今天在搞毕业设计"),
                            "assessment": {"arousal": 0.5}}, turns=5))
    aff1 = ad._topics["毕设"]["aff"]
    assert aff1 > 0.0
    ad.ingest(_ctx(domains={"usermodel": _um(), "focus": _focus("原神")},
                   scratch={"signals": read_signals("打原神"), "assessment": {}}, turns=6))
    assert ad._topics["毕设"]["aff"] < aff1   # 没碰 → 衰减
    assert "原神" in ad._topics


def test_topics_lru_caps_during_ingest() -> None:
    ad = AdaptationDomain()
    for i in range(30):
        ad.ingest(_ctx(domains={"usermodel": _um(), "focus": _focus(f"题{i:02d}话")},
                       scratch={"signals": read_signals("聊点啥"), "assessment": {}}, turns=i))
    assert len(ad._topics) == 24   # _TOPIC_CAP


def test_prompt_line_style_hint_gated_by_bond() -> None:
    ad = AdaptationDomain()
    ad._style_target = {"len": 10.0}      # 已学到你的风格
    assert "往你那边靠" in ad.prompt_line(current_text="随便说点啥", bond=0.5)
    assert "往你那边靠" not in ad.prompt_line(current_text="随便说点啥", bond=0.1)  # bond 不够


def test_prompt_line_topic_hint_on_lowinfo() -> None:
    ad = AdaptationDomain()
    ad._topics = {"原神": {"aff": 0.6, "last_turn": 5, "raised_turn": 0}}
    line = ad.prompt_line(current_text="嗯", bond=0.0)   # 低信息 → 可往热门话题带
    assert "原神" in line and "往那带" in line
    # 实义消息（有话可接）→ 不硬转话题
    assert "原神" not in ad.prompt_line(current_text="我想认真聊聊量子测量问题", bond=0.0)


def test_adaptation_line_reaches_fragment_end_to_end() -> None:
    ad = AdaptationDomain()
    ad._style_target = {"len": 10.0}
    doms = {"adaptation": ad, "usermodel": _um(bond=0.5)}
    frag = build_mind_fragment(_ctx(domains=doms, text="嗯", phase=Phase.PERCEPT), doms)
    assert "往你那边靠" in frag


# ---- 异常路径 -------------------------------------------------------------

def test_style_no_move_below_bond_floor() -> None:
    ad = AdaptationDomain()
    ad.ingest(_ctx(domains={"usermodel": _um(0.1, {"len": 10.0}), "focus": _focus("")}))
    assert ad._style_target == {}   # 陌生人不趋同


def test_style_diverges_on_hostility() -> None:
    ad = AdaptationDomain()
    ad.ingest(_ctx(domains={"usermodel": _um(0.5, {"len": 10.0}), "focus": _focus("")}))
    assert ad._style_target["len"] == 10.0
    ad.ingest(_ctx(domains={"usermodel": _um(0.5, {"len": 20.0}, defensiveness=0.5),
                            "focus": _focus("")}))
    assert abs(ad._style_target["len"] - 9.8) < 1e-6   # 背离：10 - 0.02*(20-10)


def test_style_no_move_when_sketch_empty() -> None:
    ad = AdaptationDomain()
    ad.ingest(_ctx(domains={"usermodel": _um(0.5, {}), "focus": _focus("")}))
    assert ad._style_target == {}


def test_ingest_non_evolve_is_noop() -> None:
    ad = AdaptationDomain()
    ad.ingest(_ctx(domains={"usermodel": _um(0.5, {"len": 10.0})}, phase=Phase.PERCEPT))
    assert ad._style_target == {}


def test_topic_hint_skips_long_gist() -> None:
    ad = AdaptationDomain()
    ad._topics = {"我今天加班到很晚真的好累不想说话": {"aff": 0.9, "last_turn": 5, "raised_turn": 0}}
    assert "往那带" not in ad.prompt_line(current_text="嗯", bond=0.0)   # >12 字 gist 不当话题


# ---- 兼容路径 -------------------------------------------------------------

def test_pre_pr_b_archive_empty_then_ingests_and_roundtrips() -> None:
    ad = AdaptationDomain()
    ad.load_dict({"expr": {"verbosity": 0.7}})   # PR-A 旧档：无 style_target/topics
    assert ad._style_target == {} and ad._topics == {}
    ad.ingest(_ctx(domains={"usermodel": _um(0.5, {"len": 10.0}), "focus": _focus("毕设")},
                   scratch={"signals": read_signals("毕设"), "assessment": {}}, turns=2))
    assert ad._style_target == {"len": 10.0}
    assert "毕设" in ad._topics
    fresh = AdaptationDomain()
    fresh.load_dict(ad.to_dict())
    assert fresh.to_dict() == ad.to_dict()   # 新学到的 style/topic 状态无损 round-trip


# ---- 回退路径 -------------------------------------------------------------

def test_ingest_survives_missing_domains() -> None:
    ad = AdaptationDomain()
    ad.ingest(_ctx(domains={}))   # 无 usermodel / focus
    assert ad._style_target == {} and ad._topics == {}


def test_ingest_survives_garbage_scratch() -> None:
    ad = AdaptationDomain()
    ad.ingest(_ctx(domains={"usermodel": _um(0.5, {"len": 10.0}), "focus": _focus("毕设")},
                   scratch={"signals": "garbage", "assessment": "garbage"}, turns=3))
    assert ad._style_target == {"len": 10.0}   # style 不受 scratch 影响
    assert "毕设" in ad._topics                 # 话题仍记，arousal/eng 降级为 0


def test_ingest_style_failure_does_not_block_topics() -> None:
    def _boom():
        raise RuntimeError("usermodel down")
    bad_um = SimpleNamespace(bond=_boom, style_sketch=lambda: {}, expectation=lambda: {})
    ad = AdaptationDomain()
    ad.ingest(_ctx(domains={"usermodel": bad_um, "focus": _focus("毕设")},
                   scratch={"signals": read_signals("毕设进展"), "assessment": {}}, turns=4))
    assert ad._style_target == {}      # style 子步被隔离
    assert "毕设" in ad._topics         # topics 子步照常


def test_prompt_line_returns_empty_on_internal_error() -> None:
    ad = AdaptationDomain()
    ad._topics = {"x": "notadict"}     # select_proactive_topic 遍历时本会 TypeError
    assert ad.prompt_line(current_text="嗯", bond=0.0) == ""


# ---- review 回归（gemini + sourcery #42）-----------------------------------

def test_divergence_clamps_len_punct_nonneg() -> None:
    """持续敌意背离不得把 len/punct 推成负数（物理非负，gemini review）。warmth 可负不夹。"""
    ad = AdaptationDomain()
    ad._style_target = {"len": 0.1, "punct": 0.1, "warmth": 0.0}
    for _ in range(50):  # 反复背离：sketch 比当前大 → 背离把目标往下推
        ad.ingest(_ctx(domains={"usermodel": _um(0.5, {"len": 9.0, "punct": 9.0, "warmth": 0.0},
                                                  defensiveness=0.6), "focus": _focus("")}))
    assert ad._style_target["len"] >= 0.0
    assert ad._style_target["punct"] >= 0.0


def test_new_topic_raised_turn_is_current() -> None:
    """新话题 raised_turn 记当前轮次（非硬编码 0，gemini review）。"""
    ad = AdaptationDomain()
    ad.ingest(_ctx(domains={"usermodel": _um(), "focus": _focus("毕设")},
                   scratch={"signals": read_signals("毕设"), "assessment": {}}, turns=7))
    assert ad._topics["毕设"]["raised_turn"] == 7


def test_malformed_topic_record_does_not_abort_decay() -> None:
    """单条畸形话题记录被跳过，不中断其余话题的衰减/更新（sourcery review）。"""
    ad = AdaptationDomain()
    ad._topics = {"好": {"aff": 0.8, "last_turn": 1, "raised_turn": 1}, "坏": "notadict"}
    ad.ingest(_ctx(domains={"usermodel": _um(), "focus": _focus("新话题")},
                   scratch={"signals": read_signals("新话题"), "assessment": {}}, turns=9))
    assert abs(ad._topics["好"]["aff"] - 0.8 * 0.98) < 1e-6   # 好记录照常衰减
    assert "新话题" in ad._topics                              # 新话题照常记录
    # 畸形记录不绊倒读方法
    assert isinstance(ad.top_topics(), list)
    assert isinstance(ad.select_proactive_topic(), str)
