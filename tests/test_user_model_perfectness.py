"""UserModelDomain 关系感/犹豫测试 —— 把“完美感”的最后两块落成可验证约束。"""

from __future__ import annotations

from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase
from sylanne_alpha.v2core.domains.user_model import UserModelDomain


def _ctx(text: str, turn: int = 1, **kw) -> BeatContext:
    body = BodySnapshot(session_key="u", turns=turn, warmth=kw.get("warmth", 0.0), tension=kw.get("tension", 0.0),
                        repair_pressure=kw.get("repair_pressure", 0.0), surprise=kw.get("surprise", 0.0),
                        exhaustion=kw.get("exhaustion", 0.0), sovereignty=kw.get("sovereignty", 0.0))
    ctx = BeatContext(session_key="u", event=None, body=body, text=text, domains={"usermodel": None})
    ctx.phase = Phase.EVOLVE
    ctx.scratch["signals"] = None
    ctx.scratch["assessment"] = {"arousal": kw.get("arousal", 0.0)}
    return ctx


def test_prompt_line_exposes_hesitation_when_relationship_is_shaky() -> None:
    um = UserModelDomain()
    for i in range(3):
        um.ingest(_ctx("在吗……", turn=i + 1, arousal=0.7, warmth=-0.2, tension=0.4, distress=0.4))
    line = um.prompt_line()
    assert "犹豫" in line or "停一下" in line or "先想一想" in line or "话会变短" in line or "有点默契" in line or "认识很久" in line or "句子会断一下" in line


def test_prompt_line_exposes_bond_when_memes_and_sync_accumulate() -> None:
    um = UserModelDomain()
    um.load_dict({"sync_trace": [{"turn": 1.0, "sync": 0.7, "grip": 0.5, "user_pe": 0.1}]})
    for i in range(3):
        um.ingest(_ctx("贴贴失败学大师", turn=i + 1, arousal=0.8, warmth=0.2, tension=0.1))
        um.ingest(_ctx("又说了一次贴贴失败学大师", turn=i + 2, arousal=0.8, warmth=0.2, tension=0.1))
    line = um.prompt_line()
    assert "我们之间" in line or "开始有我们了" in line or "认识很久" in line or "有点默契" in line or "对我们" in line
