"""CP8-P4-D/P4-E 实机端到端验证：真插件 + 真引擎 + 真 SelfCore/AutonomyScheduler，
只把 LLM 和 KV 换成可控假实现，跑完整自我进化闭环。

验证链路：
- P4-E 反思：累积决策样本 → 进 DROWSY 首拍 → 反思沉淀 reflection_bias → gate 读到变化。
- P4-E token 三道闸：首拍闸 / 每日预算池 / 唤醒即弃仍扣预算。
- P4-D 巩固：进 RETIRED → tick_decay + 进化档案落盘 KV → 新插件实例恢复偏置。

运行：PYTHONIOENCODING=utf-8 PYTHONPATH=G:/Bugfinders/AstrBot python tests/manual_evolution_e2e.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

_SYLANNE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "G:/Bugfinders/AstrBot")
sys.path.insert(0, _SYLANNE_ROOT)

PASS, FAIL = [], []


def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")


class FakeContext:
    def get_registered_star(self, name):
        return None
    def get_provider_by_id(self, pid):
        return None


def _install_fake_kv(plugin, store: dict):
    """用内存字典替换 AstrBot KV API（实机无 DB）。"""
    async def put_kv_data(key, val):
        store[key] = val
    async def get_kv_data(key, default=None):
        return store.get(key, default)
    plugin.put_kv_data = put_kv_data
    plugin.get_kv_data = get_kv_data


def _install_fake_llm(plugin, reply_holder: dict):
    """替换主评估 LLM 调用，返回 reply_holder['v']，并计数。"""
    async def fake_call(prompt):
        reply_holder["calls"] = reply_holder.get("calls", 0) + 1
        reply_holder["last_prompt"] = prompt
        return reply_holder.get("v", "")
    plugin._main_assessor_llm_call = fake_call


async def main():
    print("\n=== P4-D/P4-E 自我进化端到端实机验证 ===\n")
    from main import EmotionalStatePlugin

    kv_store: dict = {}
    llm: dict = {"v": "", "calls": 0}
    config = {
        "sylanne_alpha_life_simulation_enabled": False,
        "sylanne_webui_enabled": False,
        "sylanne_alpha_reflection_daily_budget": 2,
        "sylanne_alpha_autonomy_drowsy_after_seconds": 300.0,
        "sylanne_alpha_autonomy_retire_after_seconds": 1800.0,
    }
    plugin = EmotionalStatePlugin(context=FakeContext(), config=config)
    _install_fake_kv(plugin, kv_store)
    _install_fake_llm(plugin, llm)
    sc = plugin._self_core
    sched = plugin._autonomy_scheduler
    refl = sched._reflection
    consol = sched._consolidation
    sid = "test:Group:e2e"

    print("[1] 反应式学习累积决策样本（层次1，零 LLM）")
    for _ in range(8):
        sc.reflex_learn(sid, self_quality=0.2, behavior=-1.0)  # 持续低质量+被忽略
    store = sc._evo_stores.get(sid)
    samples = store.decision_samples() if store else []
    check("决策日志累积了样本", len(samples) >= 8)
    delta_before = sc.evo_delta(sid, "memory", "intimacy_threshold")
    check("反射 delta 已朝负向漂移（学会更主动）", delta_before < 0)

    print("\n[2] 进 DROWSY 首拍 → 反思沉淀 reflection_bias（层次2，LLM）")
    # 模拟空闲：上次用户消息在 10 分钟前（>drowsy 300s, <retire 1800s）
    now = time.time()
    plugin._store.last_user_message_time.set(sid, now - 600.0)
    phase = sc.autonomy_phase(sid, now)
    check("会话相位 = DROWSY", phase == sc.DROWSY)
    # 假 LLM 返回合法策略偏置 JSON
    llm["v"] = '{"deltas": {"memory.intimacy_threshold": -0.08}, "summary": "更主动些"}'
    bias_before = store.archive("memory").param_snapshot().get("intimacy_threshold", {}).get("reflection_bias", 0.0)
    ok = await refl.maybe_reflect(sid, now)
    check("反思执行成功", ok is True)
    check("反思调用了 LLM", llm["calls"] == 1)
    bias_after = store.archive("memory").param_snapshot()["intimacy_threshold"]["reflection_bias"]
    check("reflection_bias 已沉淀（朝 -0.08 插值）", bias_after < bias_before)
    delta_after = sc.evo_delta(sid, "memory", "intimacy_threshold")
    check("gate 读到的总偏置 = 反射+反思（叠加生效）",
          abs(delta_after - (delta_before + bias_after)) < 1e-6 and delta_after < delta_before)

    print("\n[3] token 三道闸：预算池（每日 2 次）")
    refl._min_interval = 0.0  # 关间隔闸单独验预算闸
    llm["v"] = '{"deltas": {"proactive.open_threshold": -0.03}}'
    ok2 = await refl.maybe_reflect(sid, now + 1)  # 第 2 次
    check("第 2 次反思成功（预算内）", ok2 is True)
    calls_at_2 = llm["calls"]
    ok3 = await refl.maybe_reflect(sid, now + 2)  # 第 3 次：预算耗尽
    check("第 3 次被预算闸拦截（返回 False）", ok3 is False)
    check("第 3 次未调 LLM（省 token）", llm["calls"] == calls_at_2)

    print("\n[4] token 闸：样本不足跳过 + 锁外 LLM 不死锁")
    sid2 = "test:Group:few"
    sc.reflex_learn(sid2, self_quality=0.5, behavior=0.0)  # 仅 1 条
    plugin._store.last_user_message_time.set(sid2, now - 600.0)
    calls_before2 = llm["calls"]
    ok4 = await refl.maybe_reflect(sid2, now)
    check("样本不足时跳过反思", ok4 is False)
    check("样本不足时不调 LLM", llm["calls"] == calls_before2)

    print("\n[5] 唤醒即弃：锁外 LLM 期间被唤醒 → 丢弃但仍扣预算")
    sid3 = "test:Group:wake"
    for _ in range(8):
        sc.reflex_learn(sid3, self_quality=0.2, behavior=-1.0)
    plugin._store.last_user_message_time.set(sid3, now - 600.0)
    store3 = sc._evo_stores[sid3]
    refl._min_interval = 0.0

    orig = plugin._main_assessor_llm_call
    async def wake_during(prompt):
        # 模拟 LLM 跑的同时用户发来新消息（刷新 last_user_message_time → 唤醒）
        plugin._store.last_user_message_time.set(sid3, time.time())
        return await orig(prompt)
    plugin._main_assessor_llm_call = wake_during
    llm["v"] = '{"deltas": {"memory.intimacy_threshold": -0.09}}'
    ok5 = await refl.maybe_reflect(sid3, now)
    plugin._main_assessor_llm_call = orig
    check("被唤醒 → 反思结果丢弃（返回 False）", ok5 is False)
    bias3 = store3.archive("memory").param_snapshot().get("intimacy_threshold", {}).get("reflection_bias", 0.0)
    check("唤醒丢弃 → reflection_bias 未提交", bias3 == 0.0)
    # 唤醒丢弃前已扣 1 次预算（调 LLM 前扣）：sid3 budget=2，扣 1 后还剩 1，仍有预算
    check("唤醒丢弃 → 但 LLM 已烧、预算已扣 1（防 token 悖论）",
          refl._daily_used.get(sid3, ["", 0])[1] == 1)

    print("\n[6] P4-D 深睡巩固：进 RETIRED → tick_decay + 进化档案落盘 KV")
    # 让 sid 进 RETIRED（上次消息 > 1800s 前）
    plugin._store.last_user_message_time.set(sid, now - 3600.0)
    check("会话相位 = RETIRED", sc.autonomy_phase(sid, now + 10) == sc.RETIRED)
    await consol.consolidate(sid, now + 10)
    safe = plugin._safe_session_key(sid)
    kv_key = f"sylanne_evolution_{safe}"
    check("进化档案已落盘 KV", kv_key in kv_store and bool(kv_store[kv_key]))
    saved_bias = kv_store[kv_key].get("memory", {}).get("params", {}).get(
        "intimacy_threshold", {}).get("reflection_bias", 0.0)
    check("落盘内容含反思偏置", saved_bias < 0)

    print("\n[7] P4-D 跨实例恢复：新插件实例从 KV 恢复进化档案")
    plugin2 = EmotionalStatePlugin(context=FakeContext(), config=config)
    _install_fake_kv(plugin2, kv_store)  # 共享同一份 KV
    consol2 = plugin2._autonomy_scheduler._consolidation
    await consol2.ensure_restored(sid)
    restored = plugin2._self_core.evo_delta(sid, "memory", "intimacy_threshold")
    check("新实例恢复出非零偏置（学习跨重启不丢）", restored < 0)
    # 二次 ensure_restored 应被一次性守卫拦截（不重复 IO）
    await consol2.ensure_restored(sid)
    check("ensure_restored 一次性守卫生效", sid in consol2._restored)

    print(f"\n=== 结果: {len(PASS)} PASS, {len(FAIL)} FAIL ===")
    if FAIL:
        print("失败项:", FAIL)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
