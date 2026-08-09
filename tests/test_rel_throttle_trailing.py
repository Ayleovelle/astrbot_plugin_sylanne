"""Phase 2B / PR-H trailing-edge：关系层节流落盘的尾边缘补落测试。

吸收 PR #30 gemini high：节流窗内被丢弃的变更（如 /bond 后紧接 /unbond）
不能永久丢——标脏 + 窗口末兜底落盘。

把 SylannePlugin._rel_state_throttled_save 真实方法用 MethodType 绑到最小 fake
plugin（只造该方法依赖的属性/方法），测真实时序逻辑而非复刻品。
"""

from __future__ import annotations

import asyncio
import types

import main as main_mod


class _FakeRL:
    _KV_KEY = "sylanne_relationship_state"

    @staticmethod
    def snapshot(plugin):
        return {"register_state": {}, "override": dict(plugin._override)}


def _make_plugin(monkeypatch_gap=None):
    """造最小 plugin：仅含 _rel_state_throttled_save 依赖的属性 + 方法。"""
    p = types.SimpleNamespace()
    p._rel_state_last_save_ts = 0.0
    p._rel_state_dirty_in_flight = False
    p._rel_state_pending_dirty = False
    p._override = {"sk": True}
    p._kv_writes = []  # 每次 put_kv_data 记一笔

    async def _put_kv_data(key, value):
        p._kv_writes.append((key, value))

    def _has_kv_api():
        return True

    p.put_kv_data = _put_kv_data
    p._has_kv_api = _has_kv_api
    # 绑定真实方法（trailing_save 内部调 _do_rel_state_save，两者都需绑）
    p._rel_state_throttled_save = types.MethodType(
        main_mod.EmotionalStatePlugin._rel_state_throttled_save, p
    )
    p._do_rel_state_save = types.MethodType(
        main_mod.EmotionalStatePlugin._do_rel_state_save, p
    )
    return p


def test_throttled_save_first_call_writes():
    """首次调用（无节流）立即落盘。"""
    p = _make_plugin()
    asyncio.run(p._rel_state_throttled_save())
    assert len(p._kv_writes) == 1
    assert p._kv_writes[0][0] == "sylanne_relationship_state"


def test_throttled_trailing_edge_not_lost():
    """核心：节流窗内的第二次改不丢——标脏 + 兜底落盘补上。

    确定性驱动（不赌墙钟 asyncio.sleep 赛跑，避免全量负载下 flaky）：
    - 第一次 save → 落盘（leading edge），更新 last_save_ts
    - 紧接第二次 → 命中节流窗 → 标脏 + 调度 trailing 任务
    - 直接 await _do_rel_state_save()（模拟 trailing 任务窗末触发）→ 第二次落盘
    """
    import main as m
    orig_gap = m._REL_STATE_SAVE_MIN_GAP_SECONDS
    m._REL_STATE_SAVE_MIN_GAP_SECONDS = 9999.0  # 大窗：确保第二次必命中节流
    try:
        p = _make_plugin()

        async def _drive():
            await p._rel_state_throttled_save()         # 第一次：落盘
            assert len(p._kv_writes) == 1
            await p._rel_state_throttled_save()          # 第二次：命中节流→标脏
            assert p._rel_state_pending_dirty is True    # 已标脏（尾改未丢）
            assert len(p._kv_writes) == 1                # 还没落（在窗内）
            # 模拟 trailing 任务窗末触发：强制落盘
            await p._do_rel_state_save()
            assert len(p._kv_writes) == 2                # 尾改补落
            assert p._rel_state_pending_dirty is False   # 补落后清脏

        asyncio.run(_drive())
    finally:
        m._REL_STATE_SAVE_MIN_GAP_SECONDS = orig_gap

