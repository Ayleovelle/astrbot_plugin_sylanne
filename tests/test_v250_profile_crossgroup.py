"""v2.5.0 跨群记忆：PersonProfile 半——关系/人格/瞬时情绪跨群测试。

design: docs/architecture/v250-cross-group-memory-design.md §3（关系+人格）/
§4（瞬时情绪 transient_affect）/ §8 B1（已认证身份暂存层）/ B3（幂等播种）/
B4（基线不污染）/ B5（purge 级联 + 物理拒绝播种）。

本文件覆盖范围：
- `persist_kernel` 落盘钩子的 profile 软同步（`StatePersistence._soft_sync_person_profile`）。
- `SessionContext.host()` 出生播种（`_schedule_person_profile_seed` /
  `_seed_person_profile_async`）：关系四计数 + Sylanne Six 只在真正首次出生播种，
  transient 走独立 LRU 重建守卫。
- `person_profile.py` 新增的纯合并函数（`merge_relationship_counts` /
  `mix_six_snapshot` / `apply_flush_observation` / `seed_transient_delta` /
  `reset_person_profile_transient`）。
- B5 purge 级联覆盖 transient 三维静态隐私面 + 硬 assert 物理拒绝播种。
- 默认全关 = 零成本 no-op（不产生任何调度/KV 读写）。

不覆盖（已有专门测试文件）：货架写侧（test_v250_shelf_write.py）、货架读侧 R1-R6
（test_v250_shelf_recall.py，含 R6 群号键三格式统一——已验证 37 条测试全绿，
本文件不重复）、B1 身份暂存层本体（test_inbound_dup_gate.py 等）。
"""

from __future__ import annotations

import asyncio
import tempfile
import time
from typing import Any

from sylanne_alpha.person_profile import (
    PersonProfile,
    _APPLY_CAP,
    apply_flush_observation,
    load_person_profile,
    merge_relationship_counts,
    mix_six_snapshot,
    person_profile_kv_key,
    reset_person_profile_transient,
    save_person_profile,
    seed_transient_delta,
)
from sylanne_alpha.person_shelf import person_shelf_origin_index_kv_key
from sylanne_alpha.session_context import SessionContext
from sylanne_alpha.session_state_store import SessionStateStore
from sylanne_alpha.state_persistence import StatePersistence


def _run(coro):
    return asyncio.run(coro)


async def _drain() -> None:
    """让所有已调度但尚未跑完的 fire-and-forget 任务跑到底（多轮，因为任务内部
    有多个 await 点：register_person_shelf_origin 的 get/put、load_person_profile
    的 get、save_person_profile 的 put）。
    """
    for _ in range(20):
        pending = [
            t
            for t in asyncio.all_tasks()
            if t is not asyncio.current_task() and not t.done()
        ]
        if not pending:
            return
        await asyncio.sleep(0)
    # 最后再等一次真正完成，暴露任何异常（而非静默吞掉）
    pending = [
        t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()
    ]
    if pending:
        await asyncio.gather(*pending)


# ---------------------------------------------------------------------------
# 最小化插件替身
# ---------------------------------------------------------------------------


class _FakeEngine:
    def __init__(self, obs: dict[str, float] | None = None) -> None:
        self._obs = obs or {"valence": 0.2, "arousal": 0.3, "tension": 0.1}

    def observe(self) -> dict[str, float]:
        return dict(self._obs)


class _FakeComputation:
    def __init__(self) -> None:
        self.engine = _FakeEngine()


class _FakeKernel:
    """`persist_kernel` 软同步测试专用的最小 kernel 替身——比构造真实
    `AlphaKernel` 更精简，只暴露 `_soft_sync_person_profile` 真正读取的字段。
    """

    def __init__(self) -> None:
        self.computation = _FakeComputation()


class _FakeHost:
    def __init__(self) -> None:
        self.kernel = _FakeKernel()


class _FakePlugin:
    _shared_encoder = None

    def __init__(
        self,
        *,
        cross_session_mode: str = "off",
        cross_relationship: bool = False,
        cross_personality: bool = False,
        owner_id: str = "",
        cross_session_scope: str = "owner",
        root: str | None = None,
    ) -> None:
        self._store = SessionStateStore()
        self._background_tasks: list = []
        self._MAX_HOSTS = 200
        self.config: dict[str, Any] = {
            "sylanne_alpha_owner_id": owner_id,
            "sylanne_alpha_root": root or tempfile.mkdtemp(prefix="v250_profile_"),
        }
        self._kv: dict[str, Any] = {}
        self._cross_session_mode = cross_session_mode
        self._cross_session_scope = cross_session_scope
        self._cross_relationship = cross_relationship
        self._cross_personality = cross_personality
        self._session_ctx = SessionContext(self)
        self._state_persistence = StatePersistence(self)
        self._state_persistence._pending_delete_scan_done = True

    async def get_kv_data(self, key: str, default: Any = None) -> Any:
        return self._kv.get(key, default)

    async def put_kv_data(self, key: str, value: Any) -> None:
        self._kv[key] = value

    async def delete_kv_data(self, key: str) -> None:
        self._kv.pop(key, None)

    def _cfg(self, key: str, default: str = "") -> str:
        if key == "sylanne_alpha_cross_session_mode":
            return self._cross_session_mode
        if key == "sylanne_alpha_cross_session_scope":
            return self._cross_session_scope
        return default

    def _cfg_bool(self, key: str, default: bool = False) -> bool:
        if key == "sylanne_alpha_cross_relationship":
            return self._cross_relationship
        if key == "sylanne_alpha_cross_personality":
            return self._cross_personality
        return default


def _seed_identity(
    plugin: _FakePlugin, sk: str, *, sender_id: str, platform: str = "aiocqhttp",
    origin_scope: str = "private", origin_id: str = "",
) -> None:
    plugin._store.set_authenticated_identity(
        sk, sender_id=sender_id, platform=platform,
        origin_scope=origin_scope, origin_id=origin_id or sk,
    )


# ===========================================================================
# 1. 纯函数：merge_relationship_counts / mix_six_snapshot
# ===========================================================================


def test_merge_relationship_counts_is_element_wise_max():
    profile = PersonProfile(preference_count=3, boundary_count=0, progress_count=5, repair_count=1)
    pref, bound, prog, repair, phase = merge_relationship_counts(
        profile, {"preference_count": 1, "boundary_count": 2, "progress_count": 5, "repair_count": 9}
    )
    assert (pref, bound, prog, repair) == (3, 2, 5, 9)
    assert phase in {"low_signal", "forming_continuity", "active_continuity"}


def test_merge_relationship_counts_none_input_preserves_existing():
    profile = PersonProfile(preference_count=4, boundary_count=1, progress_count=2, repair_count=0, phase="forming_continuity")
    result = merge_relationship_counts(profile, None)
    assert result == (4, 1, 2, 0, "forming_continuity")


def test_mix_six_snapshot_bootstraps_new_key_without_anchor():
    # 旧快照没有这个 trait，直接采纳新观测，不隐式当 old=0 参与混合
    merged = mix_six_snapshot({}, {"warmth_bias": 0.8}, alpha=0.3)
    assert merged["warmth_bias"] == 0.8


def test_mix_six_snapshot_blends_existing_key():
    merged = mix_six_snapshot({"warmth_bias": 0.5}, {"warmth_bias": 0.9}, alpha=0.3)
    assert abs(merged["warmth_bias"] - (0.5 * 0.7 + 0.9 * 0.3)) < 1e-9


def test_mix_six_snapshot_keeps_old_key_absent_from_new():
    merged = mix_six_snapshot({"edge": 0.4}, {}, alpha=0.3)
    assert merged["edge"] == 0.4


# ===========================================================================
# 2. apply_flush_observation：B4 顺序冻结 + update_relationship_affect 开关隔离
# ===========================================================================


def test_apply_flush_observation_baseline_excludes_already_applied_transient():
    """B4：baseline 采样点 = current_warmth - last_applied_transient，而不是
    current_warmth 本身——否则已经被跨群播种注入的 delta 会被基线重新吸收，
    造成漂移。"""
    profile = PersonProfile(warmth_baseline=0.5, last_applied_transient=0.1)
    # current_warmth 里含 0.1 是这次会话之前被跨群播种注入的
    new_profile = apply_flush_observation(
        profile, now=time.time(), current_warmth=0.6, current_volatility=0.0,
    )
    # baseline_sample = 0.6 - 0.1 = 0.5 == old baseline，EMA 混合后应几乎不变
    assert abs(new_profile.warmth_baseline - 0.5) < 1e-6


def test_apply_flush_observation_without_subtracting_would_drift_baseline():
    """反证：若采样点用 current_warmth 本身（忽略 last_applied_transient），
    基线会被拉高——本测试验证我们的实现【不】具有这个 bug。"""
    profile = PersonProfile(warmth_baseline=0.5, last_applied_transient=0.1)
    new_profile = apply_flush_observation(
        profile, now=time.time(), current_warmth=0.6, current_volatility=0.0,
    )
    naive_baseline_sample = 0.6  # 错误实现会用这个（忽略 last_applied_transient）
    naive_new_baseline = 0.5 * 0.9 + naive_baseline_sample * 0.1
    assert new_profile.warmth_baseline != naive_new_baseline


def test_apply_flush_observation_transient_excludes_already_applied_seed():
    """回归（MAJOR 修复）：`observed_warmth_transient` 必须与 baseline 采样点
    同样剔除 `last_applied_transient`——否则跨群播种注入的种子会被当作"这次
    会话自己的新偏离"重新计入 transient，种子的回声在下一次落盘时又被读回，
    永不衰减到零（是 B4 baseline 去种同款 bug 的姊妹坑）。

    场景：种子 0.15 已经被出生播种施加进 body（current_warmth = baseline +
    seed = 0.6），本次交互本身是中性的（没有产生任何新的情绪偏离）——修复后
    观测到的 transient 应该几乎是 0，而不是把种子本身当成新观测。
    """
    profile = PersonProfile(
        warmth_baseline=0.45, warmth_transient=0.0, last_applied_transient=0.15,
    )
    new_profile = apply_flush_observation(
        profile, now=time.time(), current_warmth=0.6, current_volatility=0.0,
    )
    assert abs(new_profile.warmth_transient) < 1e-6


def test_apply_flush_observation_transient_without_subtracting_would_echo_seed():
    """反证：若 `observed_warmth_transient` 不剔除 `last_applied_transient`
    （旧实现的 bug），会把种子本身算作新观测——本测试验证我们的实现【不】
    具有这个 bug。"""
    profile = PersonProfile(
        warmth_baseline=0.45, warmth_transient=0.0, last_applied_transient=0.15,
    )
    new_profile = apply_flush_observation(
        profile, now=time.time(), current_warmth=0.6, current_volatility=0.0,
    )
    naive_observed = 0.6 - 0.45  # 错误实现：忽略 last_applied_transient
    naive_new_transient = 0.0 * 0.5 + naive_observed * 0.5
    assert new_profile.warmth_transient != naive_new_transient


def test_apply_flush_observation_gated_off_preserves_baseline_and_transient():
    """update_relationship_affect=False（对应 cross_relationship 关闭）时，
    即便传了 current_warmth，也不应该改动 warmth_baseline/transient/
    last_interaction_ts——这些字段只挂在 cross_relationship 一个开关下。
    """
    profile = PersonProfile(warmth_baseline=0.5, warmth_transient=0.05, last_interaction_ts=None)
    new_profile = apply_flush_observation(
        profile, now=123.0, current_warmth=0.99, current_volatility=0.99,
        six_observed={"edge": 0.9}, update_relationship_affect=False,
    )
    assert new_profile.warmth_baseline == 0.5
    assert new_profile.warmth_transient == 0.05
    assert new_profile.last_interaction_ts is None
    assert new_profile.six_snapshot["edge"] == 0.9  # Six 仍然独立生效


def test_apply_flush_observation_advances_last_interaction_ts_when_gated_on():
    profile = PersonProfile()
    new_profile = apply_flush_observation(
        profile, now=999.0, current_warmth=0.5, current_volatility=0.0,
    )
    assert new_profile.last_interaction_ts == 999.0


def test_apply_flush_observation_valence_arousal_tension_only_store_latest():
    profile = PersonProfile(valence=0.1, arousal=0.1, tension=0.1)
    new_profile = apply_flush_observation(
        profile, now=1.0, current_warmth=0.5, current_volatility=0.0,
        valence=0.7, arousal=None, tension=-0.3,
    )
    assert new_profile.valence == 0.7  # 覆盖
    assert new_profile.arousal == 0.1  # None → 保留旧值
    assert new_profile.tension == -0.3


# ===========================================================================
# 3. seed_transient_delta：B3 幂等播种 + LRU 守卫 + B5 硬 assert
# ===========================================================================


def test_seed_transient_delta_guard_blocks_when_no_last_interaction_ts():
    profile = PersonProfile()  # last_interaction_ts=None
    assert seed_transient_delta(profile, now=100.0, kernel_last_activity=0.0) is None


def test_seed_transient_delta_guard_blocks_lru_rebuild_without_new_interaction():
    """LRU 驱逐重建守卫：profile 记录的最近互动不晚于该 kernel 自己的活动时间
    → 无新情绪需要播种，跳过（防自激）。"""
    profile = PersonProfile(last_interaction_ts=100.0, warmth_transient=0.2)
    assert seed_transient_delta(profile, now=200.0, kernel_last_activity=150.0) is None


def test_seed_transient_delta_passes_guard_on_true_birth():
    profile = PersonProfile(last_interaction_ts=100.0, warmth_transient=0.2)
    result = seed_transient_delta(profile, now=100.0, kernel_last_activity=0.0)
    assert result is not None
    delta, new_last_applied, new_last_applied_volatility = result
    assert set(delta.keys()) <= {"temperature.warmth", "temperature.volatility"}
    assert abs(new_last_applied) <= _APPLY_CAP + 1e-9
    assert abs(new_last_applied_volatility) <= _APPLY_CAP + 1e-9


def test_seed_transient_delta_never_produces_valence_arousal_tension_keys():
    """B5 硬 assert 的属性化测试：任意合法 profile 组合，返回 delta 的 key
    集合恒为 temperature.warmth/volatility 的子集，绝不含三个只存不施加的维度。
    """
    for warmth_t, vol_t, ts, activity in (
        (0.3, -0.3, 0.0, -100.0),
        (-0.25, 0.1, 50.0, 0.0),
        (0.02, 0.02, 1000.0, 999.0),
        (0.0, 0.0, 5.0, 0.0),
    ):
        profile = PersonProfile(
            warmth_transient=warmth_t, volatility_transient=vol_t, last_interaction_ts=ts,
        )
        result = seed_transient_delta(profile, now=ts + 1.0, kernel_last_activity=activity)
        if result is None:
            continue
        delta, _, _ = result
        assert not ({"valence", "arousal", "tension"} & delta.keys())


def test_seed_transient_delta_idempotent_no_double_apply_on_immediate_reseed():
    """B3：同一 profile 状态下连续两次播种（模拟同一未变化的 profile 被两次
    LRU 重建读到），第二次的净施加应为 0（不是把第一次的 delta 再叠一次）。
    """
    profile = PersonProfile(last_interaction_ts=100.0, warmth_transient=0.2)
    now = 100.0
    result1 = seed_transient_delta(profile, now=now, kernel_last_activity=0.0)
    assert result1 is not None
    delta1, new_last_applied, new_last_applied_volatility = result1

    # 把新的 last_applied_* 写回 profile（真实调用方在 apply 后就会做这一步）
    from dataclasses import replace as _replace

    updated_profile = _replace(
        profile,
        last_applied_transient=new_last_applied,
        last_applied_volatility_transient=new_last_applied_volatility,
    )
    # 第二次仍在同一时刻重新播种（例如极快连续两次 LRU 重建）
    result2 = seed_transient_delta(updated_profile, now=now, kernel_last_activity=0.0)
    assert result2 is not None
    delta2, _, _ = result2
    # 净施加恒等于当前衰减值：第二次的 delta 应接近 0（已经被第一次施加过了）
    assert abs(delta2.get("temperature.warmth", 0.0)) < 1e-9


def test_seed_transient_delta_cap_bounded_by_apply_cap():
    """存储帽 ±0.3 的极端 transient，目标施加值仍被夹到 ±0.15。"""
    profile = PersonProfile(last_interaction_ts=100.0, warmth_transient=0.3, volatility_transient=-0.3)
    result = seed_transient_delta(profile, now=100.0, kernel_last_activity=0.0)
    assert result is not None
    delta, new_last_applied, new_last_applied_volatility = result
    assert delta["temperature.warmth"] <= _APPLY_CAP + 1e-9
    assert delta["temperature.volatility"] >= -_APPLY_CAP - 1e-9


def test_seed_transient_delta_volatility_is_net_applied_not_reaccumulated():
    """回归（MAJOR 修复）：volatility 与 warmth 同一套净施加语义——重复播种
    （模拟 LRU 反复驱逐重建，guard 允许场景：该人在别处持续活跃）不应把
    `target_volatility` 逐次累加进 kernel，第二次净施加应接近 0。
    """
    from dataclasses import replace as _replace

    profile = PersonProfile(last_interaction_ts=100.0, volatility_transient=-0.3)
    now = 100.0
    result1 = seed_transient_delta(profile, now=now, kernel_last_activity=0.0)
    assert result1 is not None
    delta1, new_last_applied, new_last_applied_volatility = result1
    assert delta1["temperature.volatility"] <= -_APPLY_CAP + 1e-9  # 首次：满额净施加

    updated_profile = _replace(
        profile,
        last_applied_transient=new_last_applied,
        last_applied_volatility_transient=new_last_applied_volatility,
    )
    result2 = seed_transient_delta(updated_profile, now=now, kernel_last_activity=0.0)
    assert result2 is not None
    delta2, _, _ = result2
    # 已经被第一次施加过——第二次净施加应接近 0，不是再叠一次满额 target_volatility
    assert abs(delta2.get("temperature.volatility", 0.0)) < 1e-9


# ===========================================================================
# 4. reset_person_profile_transient（B5 purge 纯函数层）
# ===========================================================================


def test_reset_person_profile_transient_clears_only_transient_fields():
    plugin = _FakePlugin()

    async def go():
        profile = PersonProfile(
            preference_count=5, six_snapshot={"edge": 0.7}, warmth_baseline=0.6,
            warmth_transient=0.2, volatility_transient=-0.1,
            valence=0.5, arousal=0.4, tension=0.3, last_interaction_ts=42.0,
            last_applied_transient=0.05,
        )
        await save_person_profile(plugin, "aiocqhttp", "u1", profile)
        await reset_person_profile_transient(plugin, "aiocqhttp", "u1")
        reloaded = await load_person_profile(plugin, "aiocqhttp", "u1")
        assert reloaded.preference_count == 5  # 关系计数保留
        assert reloaded.six_snapshot == {"edge": 0.7}  # Six 保留
        assert reloaded.warmth_baseline == 0.6  # 长期基线保留
        assert reloaded.warmth_transient == 0.0
        assert reloaded.volatility_transient == 0.0
        assert reloaded.valence == 0.0
        assert reloaded.arousal == 0.0
        assert reloaded.tension == 0.0
        assert reloaded.last_interaction_ts is None
        assert reloaded.last_applied_transient == 0.0

    _run(go())


def test_reset_person_profile_transient_noop_when_already_clean():
    """已经是干净态时不产生写入（性能优化，不是正确性要求，但顺带验证不报错）。"""
    plugin = _FakePlugin()

    async def go():
        await reset_person_profile_transient(plugin, "aiocqhttp", "clean_u")
        assert person_profile_kv_key("aiocqhttp", "clean_u") not in plugin._kv

    _run(go())


# ===========================================================================
# 5. persist_kernel 软同步（StatePersistence._soft_sync_person_profile）
# ===========================================================================


def test_persist_kernel_soft_sync_default_off_writes_nothing():
    plugin = _FakePlugin(cross_session_mode="off")
    sk = "u_off"
    _seed_identity(plugin, sk, sender_id="u_off")
    host = _FakeHost()
    snapshot = {
        "body": {
            "temperature": {"warmth": 0.7, "volatility": 0.1},
            "memory": {"relationship": {"signals": {"preference_count": 3}}},
        },
        "personality": {"traits": {"edge": 0.9}},
    }

    _run(plugin._state_persistence._soft_sync_person_profile(sk, host, snapshot))

    assert person_profile_kv_key("aiocqhttp", "u_off") not in plugin._kv


def test_persist_kernel_soft_sync_mode_off_writes_nothing_even_if_bool_switches_on():
    """回归（BLOCKER 修复）：`mode="off"` 必须整体停写——即便部署者已经提前
    拧开了 `cross_relationship`/`cross_personality` 这两个 bool（常见的"先开
    细分开关、后拨主档位"部署顺序），只要主档位仍是 off，profile（含
    valence/arousal/tension 静态隐私面）就一律不得写进 KV（design §7"关闭
    语义：off = 停读停写旁挂层"）。
    """
    plugin = _FakePlugin(
        cross_session_mode="off", cross_relationship=True, cross_personality=True,
    )
    sk = "u_off_bool_on"
    _seed_identity(plugin, sk, sender_id="u_off_bool_on")
    host = _FakeHost()
    snapshot = {
        "body": {
            "temperature": {"warmth": 0.7, "volatility": 0.1},
            "memory": {"relationship": {"signals": {"preference_count": 3}}},
        },
        "personality": {"traits": {"edge": 0.9}},
    }

    _run(plugin._state_persistence._soft_sync_person_profile(sk, host, snapshot))

    assert person_profile_kv_key("aiocqhttp", "u_off_bool_on") not in plugin._kv


def test_persist_kernel_soft_sync_shadow_mode_still_writes_profile():
    """shadow 档：与货架写侧同一语义("货架照常写入，只拦注入")——soft-sync
    只是把观测写进 profile 存储层，不直接改动 host.kernel，因此 shadow 档
    应该照常写入（真正被拦的是出生播种对 kernel 的施加，见
    `_seed_person_profile_async` 的 shadow 分支测试）。
    """
    plugin = _FakePlugin(cross_session_mode="shadow", cross_relationship=True)
    sk = "u_shadow"
    _seed_identity(plugin, sk, sender_id="u_shadow", origin_id="shadow_origin")
    host = _FakeHost()
    snapshot = {
        "body": {
            "temperature": {"warmth": 0.7, "volatility": 0.1},
            "memory": {"relationship": {"signals": {"preference_count": 3}}},
        },
        "personality": {},
    }

    _run(plugin._state_persistence._soft_sync_person_profile(sk, host, snapshot))

    profile = _run(load_person_profile(plugin, "aiocqhttp", "u_shadow"))
    assert profile.preference_count == 3
    assert profile.last_interaction_ts is not None


def test_persist_kernel_soft_sync_no_identity_skips():
    plugin = _FakePlugin(cross_session_mode="on", cross_relationship=True, cross_personality=True)
    sk = "u_noid"  # 从未 set_authenticated_identity
    host = _FakeHost()
    snapshot = {"body": {"temperature": {"warmth": 0.7, "volatility": 0.1}}, "personality": {}}

    _run(plugin._state_persistence._soft_sync_person_profile(sk, host, snapshot))

    assert person_profile_kv_key("aiocqhttp", "u_noid") not in plugin._kv


def test_persist_kernel_soft_sync_cross_relationship_only_updates_relationship_and_warmth():
    plugin = _FakePlugin(cross_session_mode="on", cross_relationship=True, cross_personality=False)
    sk = "u_rel"
    _seed_identity(plugin, sk, sender_id="u_rel", origin_id="private_origin")
    host = _FakeHost()
    snapshot = {
        "body": {
            "temperature": {"warmth": 0.8, "volatility": 0.2},
            "memory": {"relationship": {"signals": {
                "preference_count": 2, "boundary_count": 0, "progress_count": 1, "repair_count": 0,
            }}},
        },
        "personality": {"traits": {"edge": 0.95}},
    }

    _run(plugin._state_persistence._soft_sync_person_profile(sk, host, snapshot))

    profile = _run(load_person_profile(plugin, "aiocqhttp", "u_rel"))
    assert profile.preference_count == 2
    assert profile.progress_count == 1
    # cross_personality 关闭 → Six 不应更新
    assert profile.six_snapshot == {}
    # warmth_baseline 应该已经从默认 0.45 往 0.8 方向移动（慢 EMA，非等于）
    assert profile.warmth_baseline != 0.45
    assert profile.last_interaction_ts is not None


def test_persist_kernel_soft_sync_cross_personality_only_updates_six_not_warmth():
    plugin = _FakePlugin(cross_session_mode="on", cross_relationship=False, cross_personality=True)
    sk = "u_person"
    _seed_identity(plugin, sk, sender_id="u_person", origin_id="private_origin2")
    host = _FakeHost()
    snapshot = {
        "body": {
            "temperature": {"warmth": 0.99, "volatility": 0.99},
            "memory": {"relationship": {"signals": {"preference_count": 9}}},
        },
        "personality": {"traits": {"edge": 0.88}},
    }

    _run(plugin._state_persistence._soft_sync_person_profile(sk, host, snapshot))

    profile = _run(load_person_profile(plugin, "aiocqhttp", "u_person"))
    assert profile.six_snapshot.get("edge") == 0.88
    # cross_relationship 关闭 → 关系计数/基线/transient 全部不变
    assert profile.preference_count == 0
    assert profile.warmth_baseline == 0.45
    assert profile.warmth_transient == 0.0
    assert profile.last_interaction_ts is None


def test_persist_kernel_soft_sync_registers_shelf_origin_index_entry():
    """B5：profile 落盘前必须先登记反向索引，供 purge 反查。"""
    plugin = _FakePlugin(cross_session_mode="on", cross_relationship=True)
    sk = "u_index"
    _seed_identity(plugin, sk, sender_id="u_index", origin_id="private_origin3")
    host = _FakeHost()
    snapshot = {
        "body": {"temperature": {"warmth": 0.5, "volatility": 0.0}, "memory": {}},
        "personality": {},
    }

    _run(plugin._state_persistence._soft_sync_person_profile(sk, host, snapshot))

    safe = plugin._state_persistence._safe_session_key(sk)
    assert person_shelf_origin_index_kv_key(safe) in plugin._kv


def test_persist_kernel_soft_sync_register_failure_skips_profile_write():
    plugin = _FakePlugin(cross_session_mode="on", cross_relationship=True)
    sk = "u_regfail"
    _seed_identity(plugin, sk, sender_id="u_regfail", origin_id="private_origin4")
    host = _FakeHost()
    snapshot = {
        "body": {"temperature": {"warmth": 0.9, "volatility": 0.0}, "memory": {}},
        "personality": {},
    }

    orig_put = plugin.put_kv_data

    async def _failing_put(key: str, value: Any) -> None:
        if key.startswith("sylanne_person_shelf_origin_index:"):
            raise RuntimeError("kv down")
        await orig_put(key, value)

    plugin.put_kv_data = _failing_put

    _run(plugin._state_persistence._soft_sync_person_profile(sk, host, snapshot))

    assert person_profile_kv_key("aiocqhttp", "u_regfail") not in plugin._kv


def test_persist_kernel_soft_sync_captures_valence_arousal_tension_only_store():
    plugin = _FakePlugin(cross_session_mode="on", cross_relationship=True)
    sk = "u_vat"
    _seed_identity(plugin, sk, sender_id="u_vat", origin_id="private_origin5")
    host = _FakeHost()
    host.kernel.computation.engine = _FakeEngine({"valence": 0.42, "arousal": 0.33, "tension": 0.11})
    snapshot = {
        "body": {"temperature": {"warmth": 0.5, "volatility": 0.0}, "memory": {}},
        "personality": {},
    }

    _run(plugin._state_persistence._soft_sync_person_profile(sk, host, snapshot))

    profile = _run(load_person_profile(plugin, "aiocqhttp", "u_vat"))
    assert profile.valence == 0.42
    assert profile.arousal == 0.33
    assert profile.tension == 0.11


# ===========================================================================
# 6. host() 出生播种：关系/Six 只在真正首次出生，transient 走独立守卫
# ===========================================================================


def test_host_birth_seeding_default_off_produces_byte_identical_kernel():
    """默认全关：host() 不应调度任何后台播种任务，kernel 人格/关系保持纯默认。"""
    plugin = _FakePlugin(cross_session_mode="off")
    sk = "birth_off"
    _seed_identity(plugin, sk, sender_id="birth_off")

    async def go():
        host = plugin._session_ctx.host(sk)
        await _drain()
        return host

    host = _run(go())
    assert host.kernel.body.memory.get("relationship", {}).get("signals") in ({}, None)


def test_host_birth_seeding_mode_off_skips_scheduling_even_if_bool_switches_on():
    """回归（BLOCKER 修复）：`mode="off"` 必须让 `_schedule_person_profile_seed`
    整体不调度——即便 `cross_relationship`/`cross_personality` 已被提前拧开、
    且该身份确实存在一份跨群档案，主档位仍是 off 时 kernel 也不应有任何
    播种痕迹。
    """
    root = tempfile.mkdtemp(prefix="v250_birth_off_bool_on_")
    plugin = _FakePlugin(
        cross_session_mode="off", cross_relationship=True, cross_personality=True, root=root,
    )

    async def seed_profile():
        profile = PersonProfile(
            preference_count=4, boundary_count=1,
            six_snapshot={"edge": 0.77}, warmth_transient=0.3,
            last_interaction_ts=time.time(),
        )
        await save_person_profile(plugin, "aiocqhttp", "off_bool_on_person", profile)

    _run(seed_profile())

    sk = "session_off_bool_on"
    _seed_identity(plugin, sk, sender_id="off_bool_on_person")

    async def go():
        host = plugin._session_ctx.host(sk)
        await _drain()
        return host

    host = _run(go())
    assert host.kernel.body.memory.get("relationship", {}).get("signals") in ({}, None)
    assert host.kernel.body.temperature.warmth == 0.45


def test_host_birth_seeding_shadow_mode_computes_but_does_not_mutate_kernel():
    """回归（BLOCKER 修复）：`mode="shadow"` 只计算"若施加会怎样"并落观测
    日志，绝不真的把关系计数/Sylanne Six/transient 写进 host.kernel（design
    §4.3"shadow 观测…不施加"），也不应回写 profile 的 `last_applied_*` 锚点
    （锚点只在真正施加后才推进——否则会让 shadow 观测期悄悄消耗掉 B3 的
    幂等预算，拨到 on 档时反而播种不足）。
    """
    root = tempfile.mkdtemp(prefix="v250_birth_shadow_")
    plugin = _FakePlugin(
        cross_session_mode="shadow", cross_relationship=True, cross_personality=True, root=root,
    )

    async def seed_profile():
        profile = PersonProfile(
            preference_count=4, boundary_count=1, progress_count=2, repair_count=0,
            six_snapshot={"edge": 0.77}, warmth_baseline=0.45,
            warmth_transient=0.3, volatility_transient=0.0,
            last_interaction_ts=time.time(),
        )
        await save_person_profile(plugin, "aiocqhttp", "shadow_person", profile)

    _run(seed_profile())

    sk = "session_shadow"
    _seed_identity(plugin, sk, sender_id="shadow_person")

    async def go():
        host = plugin._session_ctx.host(sk)
        await _drain()
        return host

    host = _run(go())
    # kernel 应保持纯默认——shadow 不施加
    assert host.kernel.body.memory.get("relationship", {}).get("signals") in ({}, None)
    assert host.kernel.personality.get("traits", {}).get("edge") != 0.77
    assert host.kernel.body.temperature.warmth == 0.45

    # profile 的 last_applied_transient 不应被 shadow 推进（没有真正施加）
    reloaded = _run(load_person_profile(plugin, "aiocqhttp", "shadow_person"))
    assert reloaded.last_applied_transient == 0.0
    assert reloaded.last_applied_volatility_transient == 0.0


def test_host_birth_seeding_seeds_relationship_and_six_cross_session():
    """先在 session A 里通过 persist_kernel 软同步落一份 profile，再在
    【不同 session_key、相同身份】的 session B 首次出生时，验证关系计数/
    Sylanne Six 被跨群播种进 B 的 kernel。"""
    root = tempfile.mkdtemp(prefix="v250_birth_")
    plugin = _FakePlugin(
        cross_session_mode="on", cross_relationship=True, cross_personality=True, root=root,
    )

    async def seed_profile():
        profile = PersonProfile(
            preference_count=4, boundary_count=1, progress_count=2, repair_count=0,
            six_snapshot={"edge": 0.77, "curiosity": 0.66},
            warmth_baseline=0.6, warmth_transient=0.0, last_interaction_ts=time.time(),
        )
        await save_person_profile(plugin, "aiocqhttp", "shared_person", profile)

    _run(seed_profile())

    sk_b = "session_b"
    _seed_identity(plugin, sk_b, sender_id="shared_person", origin_id="group:gX")

    async def go():
        host = plugin._session_ctx.host(sk_b)
        await _drain()
        return host

    host_b = _run(go())

    signals = host_b.kernel.body.memory.get("relationship", {}).get("signals", {})
    assert signals.get("preference_count") == 4
    assert signals.get("boundary_count") == 1
    traits = host_b.kernel.personality.get("traits", {})
    assert traits.get("edge") == 0.77
    assert traits.get("curiosity") == 0.66


def test_host_birth_seeding_nudges_warmth_via_transient():
    """出生播种应对 body.temperature.warmth 打一个有界 delta（transient 结算）。"""
    root = tempfile.mkdtemp(prefix="v250_birth_transient_")
    plugin = _FakePlugin(cross_session_mode="on", cross_relationship=True, root=root)

    async def seed_profile():
        profile = PersonProfile(
            warmth_baseline=0.45, warmth_transient=0.3, volatility_transient=0.0,
            last_interaction_ts=time.time(),
        )
        await save_person_profile(plugin, "aiocqhttp", "warm_person", profile)

    _run(seed_profile())

    sk = "session_warm"
    _seed_identity(plugin, sk, sender_id="warm_person")

    async def go():
        host = plugin._session_ctx.host(sk)
        await _drain()
        return host

    host = _run(go())
    # 默认 kernel 出生 warmth=0.45；transient 播种应把它往上推（capped ±0.15）
    assert host.kernel.body.temperature.warmth > 0.45
    assert host.kernel.body.temperature.warmth <= 0.45 + _APPLY_CAP + 1e-6


def test_host_birth_seeding_skips_when_no_profile_exists():
    """跨群开关全开，但该身份从未有过 profile——出生播种应静默 no-op，
    不应报错也不应产生非默认状态。
    """
    root = tempfile.mkdtemp(prefix="v250_birth_noprofile_")
    plugin = _FakePlugin(
        cross_session_mode="on", cross_relationship=True, cross_personality=True, root=root,
    )
    sk = "session_fresh"
    _seed_identity(plugin, sk, sender_id="never_seen_before")

    async def go():
        host = plugin._session_ctx.host(sk)
        await _drain()
        return host

    host = _run(go())
    assert host.kernel.body.memory.get("relationship", {}).get("signals") in ({}, None)
    assert host.kernel.body.temperature.warmth == 0.45


# ===========================================================================
# 7. B5 purge 级联覆盖 transient 三维静态隐私面
# ===========================================================================


def test_purge_cascade_resets_person_profile_transient_fields():
    plugin = _FakePlugin(cross_session_mode="on", cross_relationship=True)
    sk = "u_purge"
    _seed_identity(plugin, sk, sender_id="u_purge", origin_id="private_origin_purge")
    host = _FakeHost()
    snapshot = {
        "body": {"temperature": {"warmth": 0.8, "volatility": 0.3}, "memory": {
            "relationship": {"signals": {"preference_count": 6}}
        }},
        "personality": {"traits": {"edge": 0.5}},
    }
    host.kernel.computation.engine = _FakeEngine({"valence": 0.5, "arousal": 0.4, "tension": 0.3})

    _run(plugin._state_persistence._soft_sync_person_profile(sk, host, snapshot))
    profile_before = _run(load_person_profile(plugin, "aiocqhttp", "u_purge"))
    assert profile_before.valence == 0.5
    assert profile_before.last_interaction_ts is not None

    _run(plugin._state_persistence.delete_sylanne_memory_state(sk))

    profile_after = _run(load_person_profile(plugin, "aiocqhttp", "u_purge"))
    assert profile_after.valence == 0.0
    assert profile_after.arousal == 0.0
    assert profile_after.tension == 0.0
    assert profile_after.warmth_transient == 0.0
    assert profile_after.volatility_transient == 0.0
    assert profile_after.last_interaction_ts is None
    # 关系计数/warmth_baseline 是跨会话长期状态，purge 不应清除
    assert profile_after.preference_count == 6


def test_purge_cascade_dedupes_person_across_multiple_origin_entries():
    """同一 (platform, sender_id) 可能因货架/profile 各自登记了不同 origin_id
    而在反向索引里出现多条——purge 只应重置一次，不应报错。
    """
    plugin = _FakePlugin(cross_session_mode="on", cross_relationship=True)
    sk = "u_dedupe"
    _seed_identity(plugin, sk, sender_id="u_dedupe", origin_id="origin_A")
    host = _FakeHost()
    snapshot = {"body": {"temperature": {"warmth": 0.5, "volatility": 0.0}, "memory": {}}, "personality": {}}

    _run(plugin._state_persistence._soft_sync_person_profile(sk, host, snapshot))

    # 手动再登记一条不同 origin_id 的同一人记录，模拟货架也写过
    from sylanne_alpha.person_shelf import register_person_shelf_origin

    safe = plugin._state_persistence._safe_session_key(sk)
    _run(register_person_shelf_origin(plugin, safe, "aiocqhttp", "u_dedupe", "origin_B"))

    # 不应抛异常
    _run(plugin._state_persistence.delete_sylanne_memory_state(sk))
    profile_after = _run(load_person_profile(plugin, "aiocqhttp", "u_dedupe"))
    assert profile_after.last_interaction_ts is None


# ===========================================================================
# 8. R6 群号键三格式统一——回归确认（已在 test_v250_shelf_recall.py 验证 37 条全绿，
#    这里只做一条最小烟雾测试，确认 register_group_key_alias 仍然可用）
# ===========================================================================


def test_r6_group_key_alias_smoke():
    from sylanne_alpha.social_field import SocialFieldCollector

    sf = SocialFieldCollector()
    sf.collect(group_id="123456", sender_id="alice", text="hi", now=1.0)
    sf.register_group_key_alias("aiocqhttp:GroupMessage:123456", "123456")
    assert sf.peek_recent_group_senders("aiocqhttp:GroupMessage:123456") == {"alice"}
