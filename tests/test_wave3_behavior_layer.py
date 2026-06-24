"""Wave 3b：缺陷行为层（select_behavior 互斥 + 不应期；_behavior_line 渲染进 PINNED）。

钉死：10 个行为各在其躯体组合下点燃、最高激活胜出（互斥）、不应期内不复发、中性 body 不触发、
低于激活门不出手、选中的指令真进 system_prompt PINNED 层。

guard = (1-sovereignty) + 0.3*strain；soften = repair_pressure + 0.2*scar（somatic 单源公式）。
"""

from __future__ import annotations

from sylanne_alpha.v2core.behavior import select_behavior
from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase
from sylanne_alpha.v2core.fragment import build_mind_fragment, _behavior_line


def _body(**kw) -> BodySnapshot:
    return BodySnapshot(session_key="u", turns=3, **kw)


def _sel(body: BodySnapshot, scratch=None, now: float = 1000.0):
    return select_behavior(body, scratch or {}, {}, now)


def test_neutral_body_no_behavior() -> None:
    """中性 body → 不点燃任何缺陷行为。"""
    assert _sel(_body()) is None


def test_laziness() -> None:
    sel = _sel(_body(exhaustion=0.9, load=0.9, expression_drive=0.0))
    assert sel and sel["id"] == "laziness"


def test_teasing() -> None:
    sel = _sel(_body(warmth=0.85, tension=0.05, intimacy_gravity=0.75))
    assert sel and sel["id"] == "teasing"


def test_clock_back_does_not_block_behavior() -> None:
    """gemini review：系统时钟回拨(now < last_fired)不该把行为永久门住。

    last 落在未来(模拟 NTP/VM 回拨) → now-last 为负 → 旧式 `<refr` 恒真把行为门死。
    `0<=(now-last)<refr` 下界守卫把回拨视为不应期失效，行为照常可点燃。移除守卫时本测试 FAIL。
    """
    body = _body(exhaustion=0.9, load=0.9, expression_drive=0.0)   # 触发 laziness
    last_fired = {"laziness": 5000.0}                              # 未来 ts = 时钟已回拨
    sel = select_behavior(body, {}, last_fired, 1000.0)           # now=1000 < last=5000
    assert sel and sel["id"] == "laziness", "时钟回拨不应把行为永久门住"


def test_impulse_leak() -> None:
    # 表达驱力高(可达的 0.9，≤1.0) + 防备低(sovereignty=1→guard=0) + 空腔压力抬升(归一后)。
    sel = _sel(_body(expression_drive=0.9, void_pressure=18.0))
    assert sel and sel["id"] == "impulse"


def test_impulse_reachable_at_real_max_drive() -> None:
    """回归：expression_drive 实际 clamp 在 [0,1]，最大 1.0 也得能点燃 impulse（防死代码复发）。"""
    sel = _sel(_body(expression_drive=1.0, void_pressure=20.0, sovereignty=1.0))
    assert sel and sel["id"] == "impulse"


def test_vulnerable_apology_when_guard_low() -> None:
    # 修复压力高 + 防备低(sovereignty=1→guard=0)→ 拉得下脸直接认。
    sel = _sel(_body(repair_pressure=0.8, sovereignty=1.0))
    assert sel and sel["id"] == "vulnerable"


def test_oblique_repair_when_guard_high() -> None:
    # 同样修复压力高，但防备高(sovereignty=0.2→guard=0.8)→ 拉不下脸，迂回。
    sel = _sel(_body(repair_pressure=0.8, sovereignty=0.2))
    assert sel and sel["id"] == "oblique"


def test_jealousy() -> None:
    sel = _sel(_body(boundary_pressure=0.7, intimacy_gravity=0.8))
    assert sel and sel["id"] == "jealousy"


def test_lying_denial() -> None:
    # 高防备(sovereignty=0.25→guard=0.75) + 冷 + 伤疤。
    sel = _sel(_body(sovereignty=0.25, warmth=-0.5, scar=0.7))
    assert sel and sel["id"] == "lying"


def test_grudge_with_recall() -> None:
    sel = _sel(_body(scar=0.6, tension=0.7), scratch={"recalled": [{"id": "m1"}]})
    assert sel and sel["id"] == "grudge"


def test_bad_day() -> None:
    # 偏冷 + 空腔压力(归一后真高) + 低唤起(tension=0)→ 闷。
    sel = _sel(_body(warmth=-0.4, void_pressure=15.0, tension=0.0))
    assert sel and sel["id"] == "bad_day"


def test_avoidance() -> None:
    # 高位空腔(已麻木) AND 被顶(boundary 高)——合取，缺一不发。
    sel = _sel(_body(void_pressure=24.0, boundary_pressure=0.7))
    assert sel and sel["id"] == "avoidance"


def test_avoidance_needs_push_not_void_alone() -> None:
    """回归：高 void 但无被推信号(boundary/冷) → 逃避不发（不再单信号刷屏）。"""
    sel = _sel(_body(void_pressure=24.0, warmth=0.1))  # 高 void、不冷、无 boundary
    assert sel is None or sel["id"] != "avoidance"


def test_avoidance_silent_at_low_void() -> None:
    """回归：低 void（哪怕被顶）→ 没麻木，不逃避。"""
    sel = _sel(_body(void_pressure=2.0, boundary_pressure=0.7))
    assert sel is None or sel["id"] != "avoidance"


def test_mutual_exclusion_highest_wins() -> None:
    """多个可点燃 → 只返回一个（最高激活），不是列表。impulse(0.875) > avoidance(0.6)。"""
    sel = _sel(_body(expression_drive=0.9, void_pressure=24.0, boundary_pressure=0.7))
    assert sel and sel["id"] == "impulse"


def test_vulnerable_oblique_no_dead_band() -> None:
    """回归：guard 中段(0.55)+高修复压力 → 两者必有一个点燃（消除原来的死带）。"""
    sel = _sel(_body(repair_pressure=0.9, sovereignty=0.45))  # guard=0.55
    assert sel and sel["id"] in ("vulnerable", "oblique")


def test_refractory_blocks_refire() -> None:
    """刚发过的行为在不应期内不复发；若它是唯一可发的 → 返回 None。"""
    body = _body(exhaustion=0.9, load=0.9, expression_drive=0.0)
    last_fired: dict[str, float] = {}
    s1 = select_behavior(body, {}, last_fired, 1000.0)
    assert s1 and s1["id"] == "laziness"
    assert last_fired.get("laziness") == 1000.0
    # 5 分钟后（<30min 不应期）同 body → laziness 被挡，无其它可发 → None
    s2 = select_behavior(body, {}, last_fired, 1000.0 + 300.0)
    assert s2 is None
    # 31 分钟后不应期过 → 复发
    s3 = select_behavior(body, {}, last_fired, 1000.0 + 31 * 60.0)
    assert s3 and s3["id"] == "laziness"


def test_min_activation_gate() -> None:
    """勉强够不到激活门 → 不出手。"""
    # exhaustion=0.5 恰好 ramp 起点 → laziness≈0 <0.5
    assert _sel(_body(exhaustion=0.5)) is None


def test_grudge_has_longer_refractory() -> None:
    """记仇用更长不应期（≤一周一次量级）：1 小时后（默认 30min 已过、但 grudge 4 天没过）仍被挡。"""
    body = _body(scar=0.6, tension=0.7)
    scr = {"recalled": [{"id": "m1"}]}
    lf: dict[str, float] = {}
    s1 = select_behavior(body, scr, lf, 1000.0)
    assert s1 and s1["id"] == "grudge"
    # 1 小时后（>默认 1800s，但 < grudge 的 4 天 override）→ 仍不复发
    s2 = select_behavior(body, scr, lf, 1000.0 + 3600.0)
    assert s2 is None


def test_behavior_last_fired_persists_roundtrip() -> None:
    """不应期表随域 blob 落盘 + 恢复（重启不清零，敏感行为长不应期才真生效）。"""
    import asyncio
    from sylanne_alpha.v2core import integration as ig

    class _KVPlugin:
        def __init__(self) -> None:
            self._kv: dict = {}

        async def get_kv_data(self, k, d=None):  # noqa: ANN001
            return self._kv.get(k, d)

        async def put_kv_data(self, k, v) -> None:  # noqa: ANN001
            self._kv[k] = v

    p = _KVPlugin()

    async def go():
        await ig._save_domains(p, "s", {}, {"grudge": 1000.0, "lying": 2000.0})
        return await ig._load_domains(p, "s", {})

    restored = asyncio.run(go())
    assert restored.get("grudge") == 1000.0 and restored.get("lying") == 2000.0


# ---- fragment 渲染（端到端：scratch → PINNED）----

def _ctx(directive: str | None) -> BeatContext:
    c = BeatContext(session_key="u", event=None, body=_body(), text="x",
                    phase=Phase.PERCEPT, domains={})
    if directive is not None:
        c.scratch["behavior_directive"] = directive
    return c


def test_behavior_line_reads_scratch() -> None:
    assert _behavior_line(_ctx("[此刻:测试指令]")) == "[此刻:测试指令]"
    assert _behavior_line(_ctx(None)) == ""


def test_behavior_directive_reaches_pinned_fragment() -> None:
    """选中的行为指令真进 system_prompt 片段（PINNED，不被状态预算挤掉）。"""
    frag = build_mind_fragment(_ctx("[此刻:会下意识否认]"), {})
    assert "[此刻:会下意识否认]" in frag


def test_no_behavior_line_when_absent() -> None:
    frag = build_mind_fragment(_ctx(None), {})
    assert "此刻" not in frag or "behavior" not in frag  # 没塞就不出现行为指令
