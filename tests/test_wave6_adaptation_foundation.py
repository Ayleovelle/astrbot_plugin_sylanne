"""Wave 6 PR-A【地基】：AdaptationDomain 骨架 + 持久化 + 进 integration domains dict。

钉死本 PR 的交付面（学习/注入/coping/facets 不在本 PR）：
- 四子结构的中性先验正确（emoji 维已砍 → expr 仅 3 维）；
- to_dict/load_dict 无损 round-trip；
- 容缺/脏类型加载不崩、保持先验（铁律④）；bool 不污染数值字段；
- topics LRU 超容时按 last_turn 留最新一批；
- 真 integration 路径：'adaptation' 进 domains dict 且随 _save/_load_domains 自动持久化。
"""

from __future__ import annotations

import asyncio
import tempfile

from sylanne_alpha.v2core.domains.adaptation import (
    AdaptationDomain, _COPING_STRATEGIES, _EXPR_PREFS, _TOPIC_CAP,
)


# ---- 先验 ------------------------------------------------------------------

def test_neutral_priors() -> None:
    ad = AdaptationDomain()
    assert ad._expr == {"verbosity": 0.5, "formality": 0.5, "directness": 0.5}
    assert set(_EXPR_PREFS) == {"verbosity", "formality", "directness"}  # emoji 维已砍
    assert ad._coping == {s: 0.5 for s in _COPING_STRATEGIES}
    assert len(_COPING_STRATEGIES) == 4
    assert ad._style_target == {}          # 尚未学到你的风格
    assert ad._topics == {}
    assert ad._coping_pending == []
    assert ad._last_proactive_topic == ""


# ---- round-trip ------------------------------------------------------------

def test_roundtrip_lossless() -> None:
    ad = AdaptationDomain()
    ad._style_target = {"len": 12.0, "punct": 3.0, "warmth": 4.0}   # 真尺度，不 clamp
    ad._topics = {"加班": {"aff": 0.7, "last_turn": 5, "raised_turn": 2}}
    ad._expr["verbosity"] = 0.9
    ad._coping["gentle_probe"] = 0.8
    ad._coping_pending = [{"strategy": "gentle_probe", "base_distress": 0.4, "turn": 5}]
    ad._last_proactive_topic = "加班"

    snap = ad.to_dict()
    fresh = AdaptationDomain()
    fresh.load_dict(snap)
    assert fresh.to_dict() == snap


# ---- 容缺 / 脏数据（铁律④）-------------------------------------------------

def test_load_empty_archive_keeps_priors() -> None:
    ad = AdaptationDomain()
    ad.load_dict({})
    ad.load_dict(None)  # type: ignore[arg-type]
    assert ad._expr == {"verbosity": 0.5, "formality": 0.5, "directness": 0.5}
    assert ad._coping == {s: 0.5 for s in _COPING_STRATEGIES}
    assert ad._topics == {}


def test_load_tolerates_garbage_types() -> None:
    ad = AdaptationDomain()
    ad.load_dict({
        "style_target": "notadict",
        "topics": 42,
        "expr": {"verbosity": "bad", "formality": True, "directness": 0.7},
        "coping": None,
        "coping_pending": "x",
        "last_proactive_topic": 99,
    })
    # bad 非数值 → 跳过保持先验；True 是 bool → 被 _is_num 排除，不污染
    assert ad._expr["verbosity"] == 0.5
    assert ad._expr["formality"] == 0.5
    assert ad._expr["directness"] == 0.7      # 唯一合法值被采纳
    assert ad._coping == {s: 0.5 for s in _COPING_STRATEGIES}
    assert ad._style_target == {}
    assert ad._topics == {}
    assert ad._last_proactive_topic == ""


def test_expr_clamped_to_unit() -> None:
    ad = AdaptationDomain()
    ad.load_dict({"expr": {"verbosity": 9.0, "formality": -3.0, "directness": 0.5}})
    assert ad._expr["verbosity"] == 1.0
    assert ad._expr["formality"] == 0.0
    assert ad._expr["directness"] == 0.5


def test_load_nonfinite_turn_does_not_crash() -> None:
    """机器人 review：'nan'/'inf' 字符串经 _num 变 float→ int() 抛 ValueError/OverflowError。

    回归：修复前 int(float('nan')) 废掉整条 load_dict；修复后 _num 把非有限回落 0。
    """
    ad = AdaptationDomain()
    ad.load_dict({
        "topics": {"x": {"aff": 0.5, "last_turn": "nan", "raised_turn": "inf"}},
        "coping_pending": [{"strategy": "gentle_probe", "base_distress": 0.3, "turn": "nan"}],
    })
    assert ad._topics["x"]["last_turn"] == 0
    assert ad._topics["x"]["raised_turn"] == 0
    assert ad._coping_pending[0]["turn"] == 0


def test_bool_does_not_pollute_topic_numbers() -> None:
    """机器人 review(gemini high)：topics/pending 直调 _num，bool 会污染数值字段。

    回归：修复前 _num(True)=1.0 → aff=1.0/last_turn=1；修复后 _num 挡 bool 回落 0。
    """
    ad = AdaptationDomain()
    ad.load_dict({"topics": {"x": {"aff": True, "last_turn": True, "raised_turn": 0}}})
    assert ad._topics["x"]["aff"] == 0.0
    assert ad._topics["x"]["last_turn"] == 0


def test_load_dict_rejects_nondict() -> None:
    """机器人 review(gemini medium)：非空非 dict（list/str）→ not data 为 False → .get 崩。

    回归：修复前 'corrupted'.get 抛 AttributeError；修复后 isinstance 守卫空起步。
    """
    ad = AdaptationDomain()
    ad.load_dict(["corrupted"])  # type: ignore[arg-type]
    ad.load_dict("corrupted")    # type: ignore[arg-type]
    assert ad._expr == {"verbosity": 0.5, "formality": 0.5, "directness": 0.5}
    assert ad._coping == {s: 0.5 for s in _COPING_STRATEGIES}


def test_nonfinite_in_expr_keeps_prior() -> None:
    """非有限 float 进 expr → _is_num 加 isfinite 后判 False → 保持先验，不被 clamp 成端值。"""
    ad = AdaptationDomain()
    ad.load_dict({"expr": {"verbosity": float("inf"),
                           "formality": float("nan"), "directness": 0.8}})
    assert ad._expr["verbosity"] == 0.5   # 修复前 _is_num(inf)=True → clamp 成 1.0
    assert ad._expr["formality"] == 0.5
    assert ad._expr["directness"] == 0.8


def test_topics_lru_capped_on_load() -> None:
    # 喂 30 个话题，last_turn 各不同 → 加载后只留 24 个（last_turn 最新的一批）
    big = {f"t{i}": {"aff": 0.3, "last_turn": i, "raised_turn": 0} for i in range(30)}
    ad = AdaptationDomain()
    ad.load_dict({"topics": big})
    assert len(ad._topics) == _TOPIC_CAP
    kept_turns = sorted(v["last_turn"] for v in ad._topics.values())
    assert kept_turns == list(range(30 - _TOPIC_CAP, 30))   # 留下 6..29


# ---- 真 integration 路径：注册 + 自动持久化 --------------------------------

class _KVPlugin:
    """带内存 KV 的假 plugin，复用真 host 装配 v2core 运行态（仿 test_fixlist_p0_7）。"""

    _config = {"sylanne_enable_v2core": True}

    def __init__(self, root: str) -> None:
        self._root = root
        self._h: dict = {}
        self._kv: dict = {}

    def _host(self, sk):  # noqa: ANN001
        from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost
        if sk not in self._h:
            self._h[sk] = SylanneAlphaHost(root=self._root, session_key=sk)
        return self._h[sk]

    async def get_kv_data(self, key, default=None):  # noqa: ANN001
        return self._kv.get(key, default)

    async def put_kv_data(self, key, value) -> None:  # noqa: ANN001
        self._kv[key] = value


def test_adaptation_registered_and_autopersisted() -> None:
    from sylanne_alpha.v2core import integration as ig

    root = tempfile.mkdtemp(prefix="wave6a_")
    p = _KVPlugin(root)
    sk = "sess:wave6a"

    async def go() -> dict:
        rt = ig._runtime_for(p, sk)
        assert "adaptation" in rt["domains"], "AdaptationDomain 未进 domains dict"
        ad = rt["domains"]["adaptation"]
        assert isinstance(ad, AdaptationDomain)
        # 学到东西
        ad._expr["verbosity"] = 0.9
        ad._coping["gentle_probe"] = 0.8
        ad._topics = {"加班": {"aff": 0.7, "last_turn": 5, "raised_turn": 2}}
        snap = ad.to_dict()
        # 走真落盘
        await ig._save_legacy_domains(p, sk, rt["domains"], {})
        assert any("v2core_domains" in k for k in p._kv)
        # 清运行态重建 → 从 KV 恢复
        p._v2core_runtimes = {}
        rt2 = ig._runtime_for(p, sk)
        await ig._load_legacy_domains(p, sk, rt2["domains"])
        return {"snap": snap, "restored": rt2["domains"]["adaptation"].to_dict()}

    out = asyncio.run(go())
    assert out["restored"] == out["snap"], "AdaptationDomain 跨重启未还原"
