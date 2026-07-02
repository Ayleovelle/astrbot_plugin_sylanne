"""UserModelDomain —— 她对【你这个人】的后验（Fable 重做版）。

做什么（诚实声明，不引用做不到的理论）：
- 维护一个 4 维处置后验（暖/投入/防御/苦恼）+ 各维精度，观测来自 lexicon 的统一
  文本信号（修掉了"提问=冷漠"的旧观测 bug）。
- 期望（expectation）就是后验均值——静态处置模型对下一条消息的最优预测就是它，
  不假装这是逆向规划 ToM。user_pe = 精度加权的期望失配，喂同步度与精度更新。
- 节律 EMA：你的回复时距画像，喂 reply_overdue（主动触达的超期感）。
- synchrony_trajectory() 形状保持不变（WebUI /api/twin_synchrony_trajectory 在消费）。

消费者清单（每个产物都有真实下游，无死信号）：
- predict_you()      → MentalizeCapability → 心象 prompt 片段（LLM 真的读到）
- expectation()      → AppraisalCapability（期望失配 = 评价的 expectancy 维）
- reply_overdue()    → OutreachCapability（空闲 reach 压力）
- synchrony()        → Mentalize 失同步求澄清 + WebUI 轨迹
- prompt_line()      → 心象片段（"对你"行，含"我们的说法"）
- memes()            → 心象 + D1 梦境巩固取材（2.2.0 设计 §二）

SharedLexicon（2.2.0-b "我们的梗"，挂本域——梗是关系的属性，不配独立域）：
"我们之间的语言"是教科书式的二元体信念：同一个词在不同关系里语义不同。
采集 = 本轮文本 2-4 字 n-gram（EVOLVE 拍，零新能力）；晋升 = 跨轮复现 ≥3 次
且【首现于高唤起轮】（情绪标记的语汇才是梗，arousal 取自 appraisal 的真实评价）；
衰减 = 30 轮未复现 count 减半（梗会过气——这是诚实动力学，不是清理策略）。
消费：心象"我们的说法"行（LLM 真的会用）。静态词表词（人人都说的）永不晋升。

铁律：①独占状态单一写者（写仅 EVOLVE）；③只读 BodySnapshot；④load_dict 容缺，
且与旧档字段名完全兼容（disposition/disp_precision/rhythm_ema/last_user_ts/
style_sketch/last_prediction/pe_history/sync_trace；meme_cands/memes 新键容缺）。
"""

from __future__ import annotations

import math
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque

from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase
from sylanne_alpha.v2core.domains.emotion import DomainView
from sylanne_alpha.v2core.lexicon import STATIC_WORDS, TextSignals, read_signals

_DISPOSITION_DIMS = ("warmth", "engagement", "defensiveness", "distress")
_RHYTHM_ALPHA = 0.2          # 回复时距慢 EMA
_STYLE_ALPHA = 0.1           # 风格慢漂
_DISP_ALPHA_BASE = 0.3       # 处置后验基础学习率（再被精度调制）
_PE_WINDOW = 16
_PRECISION_FLOOR = 0.05
_PRECISION_CEIL = 0.99
_SYNC_TRACE_MAXLEN = 200     # 同步度轨迹长度（WebUI 消费，FIFO）

# —— SharedLexicon（"我们的梗"）常量 ——
_MEME_CAND_CAP = 128         # 候选池容量（LRU 淘汰最旧触碰）
_MEME_CAP = 16               # 晋升梗容量
_MEME_MIN_COUNT = 3          # 晋升所需跨轮复现次数
_MEME_MIN_AROUSAL = 0.4      # 首现轮唤起门槛（情绪标记的语汇才是梗）
_MEME_STALE_TURNS = 30       # 超此轮数未复现 → count 减半（过气动力学）
_MEME_COUNT_CEIL = 99.0      # 复现计数封顶（防一个老梗永久霸榜）
_MEME_PROMPT_N = 2           # 心象最多带几条
# 中文功能字（gram 至少含 2 个非功能字才可能是"说法"而非语法粘连）
_MEME_STOP_CHARS = frozenset("的了是我你他她它们在有和就都也还这那不一个么吗呢吧啊呀哦嗯哈")
_MEME_SEG_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9]{1,11}")


def _overlap2(a: str, b: str) -> bool:
    """两个 gram 是否共享 ≥2 字的连续片段（同源碎片判定；中文 gram ≤4 字，O(1) 级）。"""
    if a in b or b in a:
        return True
    for i in range(len(a) - 1):
        if a[i:i + 2] in b:
            return True
    return False


def _extract_grams(text: str) -> set[str]:
    """从一条消息提取候选语汇：中文段 2-4 字滑窗 + 英文词（小写）。

    过滤：静态词表词（人人都说的不配当"我们的"）、功能字过密的语法粘连。
    纯函数，供 ingest 与测试共用。
    """
    grams: set[str] = set()
    for seg in _MEME_SEG_RE.findall(text or ""):
        if seg[0].isascii():
            low = seg.lower()
            if low not in STATIC_WORDS:
                grams.add(low)
            continue
        n = len(seg)
        for size in (2, 3, 4):
            for i in range(n - size + 1):
                g = seg[i:i + size]
                if g in STATIC_WORDS:
                    continue
                if sum(1 for c in g if c not in _MEME_STOP_CHARS) < 2:
                    continue
                grams.add(g)
    return grams


@dataclass(frozen=True, slots=True)
class UserView(DomainView):
    """对外只读投影：我对你的预期 + 把握度。frozen，外部改不动后验。"""

    predicted_disposition: dict[str, float] = field(default_factory=dict)
    grip: float = 0.5            # 把握度：各维精度均值 [0,1]
    surprised_by_you: float = 0.0  # canonical body.surprise（不重算）
    overdue: float = 0.0         # 回复超期度（沉默场景才 >0）
    synchrony: float = 0.5       # 近期期望失配越低越高


def evidence_from_signals(sig: TextSignals) -> dict[str, float]:
    """lexicon 信号 → 处置证据（唯一观测模型，全内核共用）。

    注意：提问计入 engagement（求回应=投入），不进 defensiveness——修旧观测 bug。
    """
    if sig.length == 0:
        return {}
    return {
        "warmth": sig.valence_cue,
        "engagement": min(1.3, sig.engagement_cue),
        "defensiveness": sig.cold,
        "distress": sig.distress,
    }


class UserModelDomain:
    """你的后验领域 agent。读：predict_you/expectation/synchrony/reply_overdue；写仅 EVOLVE。"""

    name = "usermodel"

    __slots__ = (
        "_disposition", "_disp_precision", "_rhythm_ema", "_last_user_ts",
        "_style_sketch", "_last_prediction", "_pe_history", "_sync_trace",
        "_meme_cands", "_memes", "_hesitation_ema", "_bond_ema", "_last_user_text",
    )

    def __init__(self) -> None:
        self._disposition: dict[str, float] = {d: 0.0 for d in _DISPOSITION_DIMS}
        self._disp_precision: dict[str, float] = {d: 0.3 for d in _DISPOSITION_DIMS}
        self._rhythm_ema: float | None = None
        self._last_user_ts: float | None = None
        self._style_sketch: dict[str, float] = {}
        self._last_prediction: dict[str, float] | None = None
        self._pe_history: Deque[float] = deque(maxlen=_PE_WINDOW)
        self._sync_trace: Deque[dict[str, float]] = deque(maxlen=_SYNC_TRACE_MAXLEN)
        # SharedLexicon："我们的梗"。候选 {gram: {count, first_arousal, last_turn}}，
        # 晋升表 {gram: {count, first_arousal, last_turn}}（dict 保插入序 = LRU 基础）
        self._meme_cands: dict[str, dict[str, float]] = {}
        self._memes: dict[str, dict[str, float]] = {}
        self._hesitation_ema: float = 0.0
        self._bond_ema: float = 0.0
        # T2-01①：上一条真实用户文本（不含空闲/主动轮），供 IgnitionArbiter 做零状态
        # 的"复读检测"（本轮文本与上轮文本相同 → 低信息量）。只在 EVOLVE 写，DELIBERATE
        # 读到的永远是"上一轮"的值（与 _last_user_ts 同一时序纪律，见 reply_overdue）。
        self._last_user_text: str = ""

    # ---- 读接口（PERCEPT/DELIBERATE，纯只读）----

    def expectation(self) -> dict[str, float]:
        """对你下一条消息处置的期望 = 当前后验均值（静态模型的诚实预测）。"""
        return dict(self._disposition)

    def bond(self) -> float:
        """关系质量代理（_bond_ema 裸值）。供 AdaptationDomain StyleMirror 的 CAT bond 闸。

        注意与 bond_hint() 区分：后者返回叠加 sync_trace/memes 派生分的【措辞串】，非裸 EMA。
        """
        return self._bond_ema

    def style_sketch(self) -> dict[str, float]:
        """你被观测到的风格三轴只读副本，键为 'len'/'punct'/'warmth'（首条消息前为空 dict）。"""
        return dict(self._style_sketch)

    def predict_you(self, ctx: BeatContext) -> UserView:
        """投影：结合本条文本浅证据的预判 + 把握度。只读，喂 Mentalize/心象片段。

        铁律（别重复 tokenize）：复用 make_context 预读进 scratch["signals"] 的 TextSignals，
        不在每轮热路径重新分词；scratch 缺位（极端容错）才回落 read_signals。
        """
        body = ctx.body
        sig: TextSignals = ctx.scratch.get("signals") or read_signals(ctx.text or "")
        ev = evidence_from_signals(sig)
        predicted = {
            d: self._disposition[d] + 0.3 * ev.get(d, 0.0) for d in _DISPOSITION_DIMS
        }
        return UserView(
            domain=self.name,
            predicted_disposition=predicted,
            grip=self._grip(),
            surprised_by_you=float(body.surprise),
            overdue=0.0,
            synchrony=self.synchrony(),
        )

    def synchrony(self) -> float:
        """同步度 = 1/(1+近期期望失配均值)。无历史 → 中性 0.5。"""
        if not self._pe_history:
            return 0.5
        mean_pe = sum(self._pe_history) / len(self._pe_history)
        return 1.0 / (1.0 + mean_pe)

    def synchrony_trajectory(self) -> list[dict[str, float]]:
        """同步度轨迹 [{turn,sync,grip,user_pe},…] 旧→新（WebUI 契约，勿改形状）。"""
        return [dict(p) for p in self._sync_trace]

    def memes(self, limit: int = _MEME_PROMPT_N) -> list[str]:
        """当前活跃的"我们的说法"，按热度（复现数）降序。

        消费者：prompt_line（心象）+ D1 梦境巩固取材 + WebUI/测试。纯只读。
        """
        ranked = sorted(self._memes.items(),
                        key=lambda kv: (-float(kv[1].get("count", 0.0)), -len(kv[0])))
        return [g for g, _ in ranked[:max(0, limit)]]

    def last_user_text(self) -> str:
        """上一条真实用户文本（本轮之前）；无历史 → 空串。消费者：ignition 低信息量/复读检测。"""
        return self._last_user_text

    def seconds_since_last_user(self, now: float) -> float | None:
        """距上一条真实用户消息过了多久（秒）；无历史/无效 now → None。

        消费者：ignition 的"连发轰炸"启发式（T2-01①）——不看节律 EMA 的相对超期，
        只看绝对间隔，冷启动（无 EMA）也能识别真连发。
        """
        if self._last_user_ts is None or now <= 0.0:
            return None
        gap = now - self._last_user_ts
        return gap if gap >= 0.0 else None

    def reply_overdue(self, body: BodySnapshot, now: float) -> float:
        """相对你的节律 EMA，本次沉默超期多少倍。无节律画像 → 0。不封顶（铁律②）。"""
        if self._rhythm_ema is None or self._last_user_ts is None or now <= 0.0:
            return 0.0
        if self._rhythm_ema <= 0.0:
            return 0.0
        elapsed = now - self._last_user_ts
        if elapsed <= self._rhythm_ema:
            return 0.0
        return (elapsed - self._rhythm_ema) / self._rhythm_ema

    # 把握/同步的领域词组（7 级单调，零数字）
    _GRIP_WORDS = ("素未谋面", "刚认识Ta", "还在认识Ta", "渐渐懂Ta",
                   "比较懂Ta", "很懂Ta", "对Ta了如指掌")
    _SYNC_WORDS = ("完全接不上Ta的频率", "频率对不上", "时常错频", "略有错频",
                   "大致合拍", "很合拍", "心有灵犀")

    def prompt_line(self) -> str:
        """心象片段"对你"行（纯模板，零-LLM，零数字）。

        三元组编码：① 级别——把握/同步 7 级序数（≈0.14 分辨率，对措辞已是满精度；
        系统内部仍持 float64，这里只是"说给 LLM 听"）；② 方向——同步度轨迹近窗
        斜率 → 越来越合拍 / 在错开；③ 画像——处置后验的定性印象。
        额外注入：称呼层级、犹豫、关系感、共同语汇对词气的反向塑形。
        """
        from sylanne_alpha.v2core.verbal import level7, trend_word

        grip_w = level7(self._grip(), 0.0, 1.0, self._GRIP_WORDS)
        sync_w = level7(self.synchrony(), 0.0, 1.0, self._SYNC_WORDS)
        dir_w = ""
        if len(self._sync_trace) >= 5:
            recent = self._sync_trace[-1]["sync"] - self._sync_trace[-5]["sync"]
            dir_w = trend_word(recent, eps=0.05, up="越来越合拍", down="最近在错开")
        d = self._disposition
        tone_bits: list[str] = []
        if d["warmth"] > 0.15:
            tone_bits.append("偏暖")
        elif d["warmth"] < -0.15:
            tone_bits.append("偏冷")
        if d["distress"] > 0.2:
            tone_bits.append("近来易疲惫")
        if d["defensiveness"] > 0.2:
            tone_bits.append("有点防备")
        hes = self.hesitation_hint()
        if hes:
            tone_bits.append(hes)
        tone = "、".join(tone_bits) if tone_bits else "印象还浅"

        addr = "对你"
        if self._bond_ema > 0.45:
            addr = "对我们"
        elif self._bond_ema > 0.28:
            addr = "对熟悉的你"
        elif self._bond_ema > 0.14:
            addr = "对你"

        parts = [f"{addr}:{grip_w}", sync_w]
        if dir_w:
            parts.append(dir_w)
        parts.append(f"印象:{tone}")
        bond = self.bond_hint()
        if bond:
            parts.append(f"关系:{bond}")
        mm = self.memes()
        if mm:
            parts.append("我们的说法:" + "、".join(mm))
            if len(mm) >= 2:
                parts.append("词气更像我们之间的说法")
        if d["distress"] > 0.3:
            parts = parts[:3] + ["话会变短"]
        elif d["distress"] > 0.15 and len(parts) > 4:
            parts.append("句子会断一下")
        # 微表达倾向（B 路径）：把"这句话怎么收放"作为行文倾向喂 LLM，让它自己写出
        # 半句/停顿/改口（比 renderer 的机械前缀自然；directive 与 A 路径同源单写）。
        directive = self.micro_expression().get("directive", "")
        if directive:
            parts.append("说话方式:" + directive)
        return "·".join(parts)

    # ---- 写接口（仅 EVOLVE，单一写者）----

    def ingest(self, ctx: BeatContext) -> None:
        """EVOLVE 唯一写：期望失配 → 精度加权更新后验/精度/节律/风格/轨迹。

        证据只来自你的文本（lexicon 统一观测），不掺她自己的 body 状态——后验是关于
        "你"的，不是关于"我们搅在一起"的。
        """
        assert ctx.phase is Phase.EVOLVE, "UserModelDomain.ingest 只能在 EVOLVE 拍调用"
        body = ctx.body
        text = ctx.text or ""
        now = float(ctx.scratch.get("now", 0.0) or 0.0)
        sig: TextSignals = ctx.scratch.get("signals") or read_signals(text)
        actual = evidence_from_signals(sig)

        # user_pe：精度加权 RMS（精度高的维失配更"刺眼"）。首轮无期望 → body.surprise 代理。
        if self._last_prediction is not None and actual:
            num = 0.0
            wsum = 0.0
            for d in _DISPOSITION_DIMS:
                w = self._disp_precision[d]
                err = actual.get(d, 0.0) - self._last_prediction.get(d, 0.0)
                num += w * err * err
                wsum += w
            user_pe = math.sqrt(num / wsum) if wsum > 0 else 0.0
        else:
            user_pe = float(body.surprise)
        self._pe_history.append(user_pe)

        # 分维更新：精度越高学习率越小（稳）；命中升精度、失配降精度。
        if actual:
            for d in _DISPOSITION_DIMS:
                prec = self._disp_precision[d]
                lr = _DISP_ALPHA_BASE * (1.0 - prec)
                a_d = actual.get(d, 0.0)
                pred_d = (self._last_prediction or {}).get(d, self._disposition[d])
                self._disposition[d] += lr * (a_d - self._disposition[d])
                hit_d = 1.0 / (1.0 + abs(a_d - pred_d))
                prec_new = prec + 0.1 * (hit_d - prec)
                self._disp_precision[d] = min(_PRECISION_CEIL, max(_PRECISION_FLOOR, prec_new))

        # 节律 EMA + 风格慢漂（只在真用户消息轮推进；空文本=主动/空闲轮不算）
        if now > 0.0 and text:
            if self._last_user_ts is not None:
                gap = now - self._last_user_ts
                if gap > 0.0:
                    self._rhythm_ema = (gap if self._rhythm_ema is None
                                        else (1 - _RHYTHM_ALPHA) * self._rhythm_ema
                                        + _RHYTHM_ALPHA * gap)
            self._last_user_ts = now
        if text:
            self._last_user_text = text
            self._update_style(sig)
            # SharedLexicon：唤起取 appraisal 的真实评价（PERCEPT 写 scratch，EVOLVE 读）
            arousal = 0.0
            a = ctx.scratch.get("assessment")
            if isinstance(a, dict):
                try:
                    arousal = float(a.get("arousal", 0.0) or 0.0)
                except (TypeError, ValueError):
                    arousal = 0.0
            self._ingest_memes(text, arousal, int(getattr(body, "turns", 0) or 0))
        self._update_hesitation(body, text, actual, user_pe)

        # 下一轮期望 = 当前后验
        self._last_prediction = dict(self._disposition)

        # 同步度轨迹采点（WebUI 消费）
        self._sync_trace.append({
            "turn": float(body.turns),
            "sync": round(self.synchrony(), 4),
            "grip": round(self._grip(), 4),
            "user_pe": round(user_pe, 4),
        })

    # ---- 内部 ----

    def _ingest_memes(self, text: str, arousal: float, turn: int) -> None:
        """SharedLexicon 写路径（仅 EVOLVE 拍经 ingest 调用，单一写者语义内）。

        ① 过气衰减：晋升梗超 _MEME_STALE_TURNS 轮未复现 → count 减半，掉破晋升线
           即移除（梗会过气，且过气是渐进的）。
        ② 复现计数：本轮 gram 命中候选/梗 → count+1（同轮多次只算一次：跨轮才算
           复现——一条消息刷十遍不是梗，隔三天还在说才是）。
        ③ 首登记：新 gram 记 {count:1, first_arousal:本轮唤起}。首现唤起是终生属性
           （梗的出身——它诞生于一个有情绪的时刻），后续不更新。
        ④ 晋升：count≥3 且 first_arousal≥0.4，按 (count, 长度) 优先；是已有梗的
           子串则不晋升（防"芝士雪豹"的碎片"士雪豹"霸位），吸收掉自己的子串梗。
        """
        # ① 过气衰减（只扫晋升表；候选池靠 LRU 容量 + 晋升新鲜度门自清）
        for g in list(self._memes.keys()):
            m = self._memes[g]
            if turn - float(m.get("last_turn", 0.0)) > _MEME_STALE_TURNS:
                m["count"] = float(m.get("count", 0.0)) * 0.5
                m["last_turn"] = float(turn)   # 衰减后重新计窗（每 30 轮减半一次）
                if m["count"] <= _MEME_MIN_COUNT * 0.5:
                    del self._memes[g]

        grams = _extract_grams(text)
        if not grams:
            return

        for g in grams:
            if g in self._memes:
                m = self._memes[g]
                if turn != int(m.get("last_turn", -1)):
                    m["count"] = min(_MEME_COUNT_CEIL, float(m.get("count", 0.0)) + 1.0)
                    m["last_turn"] = float(turn)
                continue
            c = self._meme_cands.get(g)
            if c is None:
                c = {"count": 1.0, "first_arousal": float(arousal), "last_turn": float(turn)}
            elif turn != int(c.get("last_turn", -1)):
                c["count"] = float(c.get("count", 0.0)) + 1.0
                c["last_turn"] = float(turn)
            # LRU：重插到末尾=最近触碰；超容量淘汰最旧
            self._meme_cands.pop(g, None)
            self._meme_cands[g] = c
            while len(self._meme_cands) > _MEME_CAND_CAP:
                self._meme_cands.pop(next(iter(self._meme_cands)), None)

        # ④ 晋升（按热度与长度降序考察，长 gram 优先吃掉碎片）。
        # 新鲜度门：候选最后复现距今超过过气窗 → 不晋升（三十轮前热过的词，
        # 现在才上位没有意义——这也堵死"老候选在衰减后复活补位"的洞）。
        eligible = [(g, c) for g, c in self._meme_cands.items()
                    if c["count"] >= _MEME_MIN_COUNT
                    and c["first_arousal"] >= _MEME_MIN_AROUSAL
                    and turn - c["last_turn"] <= _MEME_STALE_TURNS]
        eligible.sort(key=lambda kv: (-kv[1]["count"], -len(kv[0])))
        for g, c in eligible:
            if len(self._memes) >= _MEME_CAP and g not in self._memes:
                break
            # 同源碎片去冗：与已有梗共享 ≥2 字连续片段（"雪豹的一" vs "芝士雪豹"
            # 共享"雪豹"）→ 视为同一个梗的碎屑，不另占位。
            if any(_overlap2(g, m) for m in self._memes if m != g):
                continue
            for sub in [m for m in self._memes if m != g and m in g]:
                del self._memes[sub]   # 吸收自己的子串梗
            self._memes[g] = dict(c)
            self._meme_cands.pop(g, None)

    def _grip(self) -> float:
        return sum(self._disp_precision.values()) / len(self._disp_precision)

    def hesitation_hint(self) -> str:
        """犹豫行：把迟疑写成可被 LLM 感知的停顿/试探，不写成逻辑常量。"""
        score = self._hesitation_ema
        if score <= 0.08:
            return ""
        if score > 0.3:
            return "犹豫很重"
        if score > 0.18:
            return "说话会停一下"
        return "会先想一想"

    def bond_hint(self) -> str:
        """关系感行：根据共同经历与梗的活跃度，给出“我们正在形成”的提示。"""
        score = self._bond_ema
        if self._sync_trace:
            score = max(score, float(self._sync_trace[-1].get("sync", 0.0)) - 0.3)
        score = max(score, 0.05 * len(self._memes))
        if score <= 0.12:
            return ""
        if score > 0.45:
            return "像是已经认识很久"
        if score > 0.25:
            return "我们之间有点默契"
        return "开始有我们了"

    def _update_style(self, sig: TextSignals) -> None:
        obs = {"len": float(sig.length), "punct": sig.punct, "warmth": sig.warm}
        for k, v in obs.items():
            self._style_sketch[k] = ((1 - _STYLE_ALPHA) * self._style_sketch.get(k, v)
                                     + _STYLE_ALPHA * v)

    def phrase_length_hint(self) -> str:
        """消息长度感：把关系亲疏转成“会长一点 / 会收短一点”。"""
        if self._distress_bias() > 0.45:
            return "会很短"
        if self._distress_bias() > 0.22:
            return "会断一下"
        if self._bond_ema > 0.45:
            return "会多说一点"
        return ""

    def micro_expression(self) -> dict[str, Any]:
        """微表达倾向（主对话路径单一来源）：把关系慢变量压成"话本身怎么收放"。

        两条消费者，公式只此一份（吸取 F2 guard/soften 双写教训）：
        - A 路径 renderer 草稿调味：取 lead——在宿主 LLM 草稿前兜底前置一个停顿引子，
          仅【状态强迟疑】时非空；中性态 lead 空 = 草稿原样（守"被问必答不改正文"红线）。
        - B 路径 fragment/prompt_line：取 directive——作为行文倾向喂 LLM，让它自己写出
          半句、停顿、改口（比 A 的机械前缀自然；A 只兜底保证停顿真的出现）。
        二者读同一批底层 EMA（_hesitation_ema/_disposition/_bond_ema），只是渲染成不同
        受众的形式——非 F2 式"同一公式两地手写"。与 state_query 窄路径的 hesitation_hint/
        phrase_length_hint 各司其职：那组渲染"她现在怎么样"自述，本方法渲染"这句怎么说"。
        """
        hes = self._hesitation_ema
        dist = self._disposition["distress"]
        defs = self._disposition["defensiveness"]
        # 停顿强度：犹豫为主，苦恼次之（受伤的人开口也会顿一下）
        pause = max(hes, 0.6 * dist)
        if pause > 0.28:
            lead = "……"
        elif pause > 0.16:
            lead = "嗯……"
        else:
            lead = ""
        # 回撤倾向：犹豫很重，或又苦又防（想说又怕说错 → 一句话说到一半收回）
        withdraw = hes > 0.3 or (dist > 0.25 and defs > 0.2)
        # 长度倾向：苦恼收短，亲近放长（与 _distress_bias 同源，不另立阈值）
        if self._distress_bias() > 0.3:
            length = "short"
        elif self._bond_ema > 0.45:
            length = "long"
        else:
            length = ""
        bits: list[str] = []
        if lead:
            bits.append("话头会顿一下再开口")
        if withdraw:
            bits.append("有时一句话说到一半会收回、改口")
        if length == "short":
            bits.append("句子会短、会断")
        elif length == "long":
            bits.append("和你熟了，会自然多说两句")
        return {"lead": lead, "withdraw": withdraw, "length": length,
                "directive": "、".join(bits)}

    def _distress_bias(self) -> float:
        return max(0.0, self._disposition["distress"] + 0.6 * self._hesitation_ema - 0.25 * self._bond_ema)

    def _update_hesitation(self, body: BodySnapshot, text: str, actual: dict[str, float], user_pe: float) -> None:
        """把“犹豫”写成关系里的慢变量：失配大、语气重、文本短时更容易沉淀。"""
        base = 0.0
        if text:
            base += 0.15 if len(text) < 12 else 0.05
            if text.endswith(("……", "...", "。", "？", "?")):
                base += 0.08
        if actual.get("defensiveness", 0.0) > 0.2:
            base += 0.12
        if actual.get("distress", 0.0) > 0.2:
            base += 0.08
        base += min(0.25, max(0.0, user_pe) * 0.18)
        self._hesitation_ema = 0.85 * self._hesitation_ema + 0.15 * base

        bond = 0.0
        mm = self.memes()
        bond += min(0.2, 0.05 * len(mm))
        if self._sync_trace:
            recent = self._sync_trace[-1]["sync"]
            bond += max(0.0, recent - 0.5) * 0.3
        if self._pe_history:
            bond += max(0.0, 0.3 - (sum(self._pe_history) / len(self._pe_history))) * 0.25
        bond += 0.08 if len(text) > 0 else 0.0
        self._bond_ema = 0.9 * self._bond_ema + 0.1 * bond

    # ---- 持久化（字段名与旧档完全兼容，容缺，铁律④）----

    def to_dict(self) -> dict[str, Any]:
        return {
            "disposition": dict(self._disposition),
            "disp_precision": dict(self._disp_precision),
            "rhythm_ema": self._rhythm_ema,
            "last_user_ts": self._last_user_ts,
            "style_sketch": dict(self._style_sketch),
            "last_prediction": self._last_prediction,
            "pe_history": list(self._pe_history),
            "sync_trace": list(self._sync_trace),
            "hesitation_ema": self._hesitation_ema,
            "bond_ema": self._bond_ema,
            "meme_cands": {g: dict(c) for g, c in self._meme_cands.items()},
            "memes": {g: dict(m) for g, m in self._memes.items()},
            "last_user_text": self._last_user_text,
        }

    def load_dict(self, data: dict[str, Any]) -> None:
        if not data:
            return
        d = data.get("disposition")
        if isinstance(d, dict):
            for k in _DISPOSITION_DIMS:
                if k in d:
                    try:
                        self._disposition[k] = float(d[k])
                    except (TypeError, ValueError):
                        pass
        p = data.get("disp_precision")
        if isinstance(p, dict):
            for k in _DISPOSITION_DIMS:
                if k in p:
                    try:
                        self._disp_precision[k] = float(p[k])
                    except (TypeError, ValueError):
                        pass
        self._rhythm_ema = _opt_f(data.get("rhythm_ema"))
        self._last_user_ts = _opt_f(data.get("last_user_ts"))
        lut = data.get("last_user_text")
        if isinstance(lut, str):
            self._last_user_text = lut
        hes = _opt_f(data.get("hesitation_ema"))
        if hes is not None:
            self._hesitation_ema = hes
        bond = _opt_f(data.get("bond_ema"))
        if bond is not None:
            self._bond_ema = bond
        if isinstance(data.get("style_sketch"), dict):
            self._style_sketch = {
                str(k): v for k, v in (
                    (k, _opt_f(v)) for k, v in data["style_sketch"].items()
                ) if v is not None
            }
        if isinstance(data.get("last_prediction"), dict):
            self._last_prediction = {
                str(k): v for k, v in (
                    (k, _opt_f(v)) for k, v in data["last_prediction"].items()
                ) if v is not None
            }
        hist = data.get("pe_history")
        if isinstance(hist, list):
            vals = [v for v in (_opt_f(x) for x in hist) if v is not None]
            self._pe_history = deque(vals, maxlen=_PE_WINDOW)
        trace = data.get("sync_trace")
        if isinstance(trace, list):
            self._sync_trace = deque(
                ({"turn": float(pt.get("turn", 0.0)), "sync": float(pt.get("sync", 0.5)),
                  "grip": float(pt.get("grip", 0.5)), "user_pe": float(pt.get("user_pe", 0.0))}
                 for pt in trace if isinstance(pt, dict)),
                maxlen=_SYNC_TRACE_MAXLEN,
            )
        # SharedLexicon（新键容缺：旧档无梗=空起步，铁律④）
        for attr, key, cap in (("_meme_cands", "meme_cands", _MEME_CAND_CAP),
                               ("_memes", "memes", _MEME_CAP)):
            raw_m = data.get(key)
            if isinstance(raw_m, dict):
                clean: dict[str, dict[str, float]] = {}
                for g, c in raw_m.items():
                    if not isinstance(c, dict):
                        continue
                    try:
                        clean[str(g)] = {
                            "count": float(c.get("count", 0.0) or 0.0),
                            "first_arousal": float(c.get("first_arousal", 0.0) or 0.0),
                            "last_turn": float(c.get("last_turn", 0.0) or 0.0),
                        }
                    except (TypeError, ValueError):
                        continue
                    if len(clean) >= cap:
                        break
                setattr(self, attr, clean)


def _opt_f(v: Any) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


__all__ = ["UserView", "UserModelDomain", "evidence_from_signals"]
