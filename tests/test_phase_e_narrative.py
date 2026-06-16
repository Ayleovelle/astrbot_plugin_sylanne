"""Phase E 测试：NarrativeSelfDomain（连续自我/固化/锚点）+ Reconsolidation（影子字段无损）。

架构 §3.2.2/§3.3，红线2（存档无损：original_text 不动）。
"""

from __future__ import annotations

from sylanne_alpha.v2core.capabilities.reconsolidation import ReconsolidationCapability
from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase
from sylanne_alpha.v2core.domains.memory import MemoryDomain
from sylanne_alpha.v2core.domains.narrative_self import NarrativeSelfDomain, SelfView


def _body(**kw) -> BodySnapshot:
    return BodySnapshot(session_key="u", turns=1, **kw)


def _evolve(body, *, scratch=None, domains=None) -> BeatContext:
    c = BeatContext(session_key="u", event=None, body=body, phase=Phase.EVOLVE, domains=domains or {})
    if scratch:
        c.scratch.update(scratch)
    return c


# ---- NarrativeSelfDomain ----

def test_self_prior_returns_selfview() -> None:
    """Fable 版纪元自持（实测 SDK surface 不暴露纪元概念，body.epoch 恒 0 是死字段）：
    纪元由真实里程碑推进——scar 台阶 + 锚点厚度，不再镜像 body.epoch。"""
    nd = NarrativeSelfDomain()
    v = nd.self_prior(_body(sovereignty=0.7, epoch=3))
    assert isinstance(v, SelfView)
    assert v.epoch == 0 and v.sovereignty_tone == 0.7   # 未经历任何里程碑 → 纪元 0


def test_epoch_advances_on_scar_milestones() -> None:
    """scar 越过台阶（0.15/0.30/…）→ 纪元 +1；回落不回退（只增）。"""
    nd = NarrativeSelfDomain()
    nd.ingest(_evolve(_body(scar=0.05)))
    assert nd.self_prior(_body()).epoch == 0
    nd.ingest(_evolve(_body(scar=0.35)))    # 越过 0.15 与 0.30 两个台阶
    assert nd.self_prior(_body()).epoch == 2
    nd.ingest(_evolve(_body(scar=0.1)))     # scar 回落，纪元不回退
    assert nd.self_prior(_body()).epoch == 2


def test_ossification_monotone_with_scar() -> None:
    """scar 越深 → 情感维固化度单调升（且只增不减，A6 不可逆精神）。"""
    nd = NarrativeSelfDomain()
    nd.ingest(_evolve(_body(scar=0.3)))
    o1 = nd.ossification("warmth")
    nd.ingest(_evolve(_body(scar=0.6)))
    o2 = nd.ossification("warmth")
    nd.ingest(_evolve(_body(scar=0.1)))   # scar 回落，固化不应回退
    o3 = nd.ossification("warmth")
    assert o2 > o1
    assert o3 >= o2, "固化只增不减（A6）"


def test_plasticity_scale_affective_vs_cognitive() -> None:
    """情感维 plasticity_scale=1−ossification；认知维（未列）恒 1.0。"""
    nd = NarrativeSelfDomain()
    nd.ingest(_evolve(_body(scar=0.5)))
    assert nd.plasticity_scale("warmth") < 1.0      # 情感维固化 → 改不动
    assert nd.plasticity_scale("some_cognitive_dim") == 1.0   # 认知维永远可塑


def test_anchor_registered_on_high_pe() -> None:
    """narrative_pe 超阈 → 登记锚点（只增）。"""
    nd = NarrativeSelfDomain()
    nd.ingest(_evolve(_body(warmth=0.5), scratch={"narrative_pe": 0.8}))
    assert nd.self_prior(_body()).anchor_count == 1
    nd.ingest(_evolve(_body(warmth=0.5), scratch={"narrative_pe": 0.1}))  # 低 pe 不登记
    assert nd.self_prior(_body()).anchor_count == 1


def test_narrative_persist_roundtrip() -> None:
    nd = NarrativeSelfDomain()
    nd.ingest(_evolve(_body(scar=0.4, epoch=2), scratch={"narrative_pe": 0.7}))
    d = nd.to_dict()
    nd2 = NarrativeSelfDomain()
    nd2.load_dict(d)
    assert nd2._epoch == nd._epoch
    assert nd2.self_prior(_body()).anchor_count == 1
    assert nd2.ossification("warmth") == nd.ossification("warmth")


# ---- Reconsolidation 影子字段（红线2）----

class _FakeMS:
    """最小 MemorySystem 桩：reconsolidate 不依赖它内部，但 to_dict/from_dict 需在。"""
    def to_dict(self): return {"items": ["原始记忆A", "原始记忆B"]}
    def from_dict(self, d): self._loaded = d


def test_reconsolidate_only_touches_overlay_not_original() -> None:
    """红线2：重固化只写影子层，original（_ms.to_dict 的 items）一字不动。"""
    md = MemoryDomain(_FakeMS())
    recalled = [{"text": "我们说要去日本", "temperature": 0.2}]
    n = md.reconsolidate(recalled, current_warmth=0.9, narrative_pe=0.8, pe_gate=0.5)
    assert n == 1
    ov = md.overlay_for("我们说要去日本")
    assert ov is not None and ov["overlay_warmth"] > 0.2   # 情绪向当下漂移了
    # original 没动
    assert md.system.to_dict()["items"] == ["原始记忆A", "原始记忆B"]


def test_reconsolidate_pe_gated() -> None:
    """narrative_pe < gate → 不改写（符合预期省算）。"""
    md = MemoryDomain(_FakeMS())
    n = md.reconsolidate([{"text": "x", "temperature": 0.0}],
                         current_warmth=0.9, narrative_pe=0.2, pe_gate=0.5)
    assert n == 0
    assert md.overlay_for("x") is None


def test_reconsolidate_cap() -> None:
    """单条改写次数封顶 _RECON_CAP。"""
    md = MemoryDomain(_FakeMS())
    for _ in range(30):
        md.reconsolidate([{"text": "k", "temperature": 0.0}],
                         current_warmth=0.9, narrative_pe=0.9, pe_gate=0.5)
    assert md.overlay_for("k")["rewrite_count"] == MemoryDomain._RECON_CAP


def test_overlay_persist_roundtrip() -> None:
    """影子层往返存档无损。"""
    md = MemoryDomain(_FakeMS())
    md.reconsolidate([{"text": "k", "temperature": 0.1}],
                     current_warmth=0.8, narrative_pe=0.9, pe_gate=0.5)
    d = md.to_dict()
    assert "_reconsolidation_overlay" in d
    md2 = MemoryDomain(_FakeMS())
    md2.load_dict(d)
    assert md2.overlay_for("k") is not None


def test_reconsolidation_capability_wires_pe() -> None:
    """能力把 narrative_pe 写进 scratch（供 NarrativeSelf 登记锚点）并触发改写。"""
    md = MemoryDomain(_FakeMS())
    nd = NarrativeSelfDomain()
    ctx = _evolve(_body(warmth=0.9),
                  scratch={"recalled": [{"text": "旧事", "temperature": 0.0}]},
                  domains={"memory": md, "narrative": nd})
    ReconsolidationCapability().evolve(ctx)
    assert "narrative_pe" in ctx.scratch
    assert ctx.scratch.get("reconsolidated_count", 0) >= 1
