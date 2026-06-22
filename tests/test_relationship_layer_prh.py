"""Phase 2B / PR-H：关系层 is_romantic 身份门控 + /bond + 持久化测试。

覆盖 handoff §5.2：
- 互惠/类型分类判定（romantic 累积过阈→亲密；friendly 不过阈）
- 身份门控防注入：非 owner sender_id 恒非亲密
- owner_id 空 → 全禁自动晋升 + /bond 拒绝（fail-closed，无 TOFU）
- override 优先；/bond·/unbond owner-gate
- 持久化 snapshot/restore roundtrip

直调真函数。
"""

from __future__ import annotations

import asyncio

from sylanne_alpha import relationship_layer as RL


class _Reg:
    def __init__(self, d=None):
        self._d = dict(d or {})

    def get(self, k, default=None):
        return self._d.get(k, default)

    def set(self, k, v):
        self._d[k] = v

    def snapshot_items(self):
        return list(self._d.items())


class _Store:
    def __init__(self):
        self.relationship_register_state = _Reg()
        self.intimacy_override = _Reg()


class _Plugin:
    def __init__(self, owner=""):
        self._store = _Store()
        self.config = {"sylanne_alpha_owner_id": owner}

    def _session_key(self, event=None, session_key=""):
        return getattr(event, "_sk", "") or session_key


class _Ev:
    def __init__(self, sender_id="", sk="s1"):
        self.sender_id = sender_id
        self._sk = sk


def _romantic_state(sender_id, conf=0.8, n=8):
    return {"sender_id": sender_id, "romantic_conf": conf, "sample_count": n}


# ---- is_romantic 自动晋升 + 身份门控 ----

def test_owner_romantic_session_is_intimate():
    p = _Plugin(owner="owner-1")
    p._store.relationship_register_state.set("s1", _romantic_state("owner-1"))
    assert RL.is_romantic(p, "s1") is True


def test_injection_nonowner_never_intimate():
    """非 owner 刷出 romantic 也恒非亲密（防对抗性注入，核心）。"""
    p = _Plugin(owner="owner-1")
    p._store.relationship_register_state.set("s1", _romantic_state("attacker-9"))
    assert RL.is_romantic(p, "s1") is False


def test_no_owner_all_autopromote_disabled():
    """owner_id 空 → 即便 romantic 满分也非亲密（fail-closed，无 TOFU）。"""
    p = _Plugin(owner="")
    p._store.relationship_register_state.set("s1", _romantic_state("anyone", conf=1.0))
    assert RL.is_romantic(p, "s1") is False


def test_low_conf_or_sample_not_intimate():
    p = _Plugin(owner="owner-1")
    p._store.relationship_register_state.set("s1", _romantic_state("owner-1", conf=0.3))
    assert RL.is_romantic(p, "s1") is False
    p._store.relationship_register_state.set("s2", _romantic_state("owner-1", n=2))
    assert RL.is_romantic(p, "s2") is False


def test_friendly_not_intimate():
    p = _Plugin(owner="owner-1")
    p._store.relationship_register_state.set(
        "s1", {"sender_id": "owner-1", "romantic_conf": 0.1, "friendly_conf": 0.9, "sample_count": 8}
    )
    assert RL.is_romantic(p, "s1") is False


# ---- override 优先（不另加身份门控，owner-gated /bond 写时已带身份）----

def test_override_true_wins():
    p = _Plugin(owner="owner-1")
    p._store.intimacy_override.set("s1", True)
    assert RL.is_romantic(p, "s1") is True


def test_override_false_wins_over_auto():
    p = _Plugin(owner="owner-1")
    p._store.relationship_register_state.set("s1", _romantic_state("owner-1"))
    p._store.intimacy_override.set("s1", False)
    assert RL.is_romantic(p, "s1") is False


# ---- /bond·/unbond owner-gate ----

def _run_cmd(gen):
    out = []

    async def _c():
        async for x in gen:
            out.append(x)

    asyncio.run(_c())
    return out


def test_bond_owner_gated():
    p = _Plugin(owner="owner-1")
    # 非 owner 被拒
    out = _run_cmd(RL.bond_command(p, _Ev(sender_id="attacker", sk="s1")))
    assert p._store.intimacy_override.get("s1") is None
    assert any("不是我对象" in t for t in out)
    # owner 放行
    out2 = _run_cmd(RL.bond_command(p, _Ev(sender_id="owner-1", sk="s1")))
    assert p._store.intimacy_override.get("s1") is True


def test_bond_refused_when_owner_unset():
    """owner_id 空 → /bond 拒绝，不自动确权（无 TOFU 抢注）。"""
    p = _Plugin(owner="")
    out = _run_cmd(RL.bond_command(p, _Ev(sender_id="whoever", sk="s1")))
    assert p._store.intimacy_override.get("s1") is None
    assert any("主人身份" in t for t in out)


def test_unbond_owner_gated():
    p = _Plugin(owner="owner-1")
    p._store.intimacy_override.set("s1", True)
    _run_cmd(RL.unbond_command(p, _Ev(sender_id="owner-1", sk="s1")))
    assert p._store.intimacy_override.get("s1") is False


# ---- 持久化 roundtrip ----

def test_snapshot_restore_roundtrip():
    p = _Plugin(owner="owner-1")
    p._store.relationship_register_state.set("s1", _romantic_state("owner-1"))
    p._store.intimacy_override.set("s2", True)
    snap = RL.snapshot(p)
    p2 = _Plugin(owner="owner-1")
    RL.restore(p2, snap)
    assert RL.is_romantic(p2, "s1") is True
    assert p2._store.intimacy_override.get("s2") is True


# ---- 解耦：关系层落盘独立于 life_sim（修 _life_sim_throttled_save 早返回耦合）----

def test_request_persist_noop_without_saver():
    """老宿主/测试桩无 _rel_state_throttled_save → request_persist 静默不崩。"""
    p = _Plugin(owner="owner-1")
    assert not hasattr(p, "_rel_state_throttled_save")
    RL.request_persist(p)  # 不抛即通过


def test_request_persist_fires_saver_when_lifesim_absent():
    """核心解耦验证：plugin 无 life_sim、life_sim 关闭，关系层落盘仍被触发。

    桩只提供 _rel_state_throttled_save（无 life_sim、无 life_sim 节流状态），
    模拟「life_sim 关掉」的现场。request_persist 必须照样把它派发掉。
    """
    fired = {"n": 0}

    class _SaverPlugin(_Plugin):
        async def _rel_state_throttled_save(self):
            fired["n"] += 1

    p = _SaverPlugin(owner="owner-1")

    async def _drive():
        RL.request_persist(p)
        # 让 safe_ensure_future 排的任务真正跑一轮
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(_drive())
    assert fired["n"] == 1


def test_bond_triggers_persist():
    """/bond 写 override 后必须派发落盘（而非只写内存等 terminate）。"""
    fired = {"n": 0}

    class _SaverPlugin(_Plugin):
        async def _rel_state_throttled_save(self):
            fired["n"] += 1

    p = _SaverPlugin(owner="owner-1")

    async def _drive():
        async for _ in RL.bond_command(p, _Ev(sender_id="owner-1", sk="s1")):
            pass
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(_drive())
    assert p._store.intimacy_override.get("s1") is True
    assert fired["n"] == 1
