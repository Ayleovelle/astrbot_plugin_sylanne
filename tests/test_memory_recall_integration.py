"""集成接线回归测试（1/2/3）。

- 1：recall_mode 从配置注入（_resolve_recall_mode 接受字符串）。
- 2：SHADOW 影子差异滚动历史 + 聚合统计落到 get_debug_snapshot。
- 3：get_debug_snapshot 暴露 shadow_stats/shadow_history 供 WebUI 拉取。
"""

from __future__ import annotations

import time

from sylanne_alpha.memory_system import MemorySystem, RecallMode


# ---------------------------------------------------------------------------
# 1：配置注入 recall_mode
# ---------------------------------------------------------------------------

def test_recall_mode_from_string_config():
    """模拟配置传入字符串模式。"""
    assert MemorySystem(recall_mode="shadow")._recall_mode is RecallMode.SHADOW
    assert MemorySystem(recall_mode="activation")._recall_mode is RecallMode.ACTIVATION
    assert MemorySystem(recall_mode="legacy")._recall_mode is RecallMode.LEGACY


def test_recall_mode_none_defaults_legacy():
    """配置缺省（None）→ LEGACY。"""
    assert MemorySystem(recall_mode=None)._recall_mode is RecallMode.LEGACY


def test_recall_mode_env_override(monkeypatch):
    """无显式参数时读环境变量 SYLANNE_RECALL_MODE。"""
    monkeypatch.setenv("SYLANNE_RECALL_MODE", "shadow")
    assert MemorySystem()._recall_mode is RecallMode.SHADOW


def test_recall_mode_explicit_beats_env(monkeypatch):
    """显式参数优先于环境变量。"""
    monkeypatch.setenv("SYLANNE_RECALL_MODE", "activation")
    assert MemorySystem(recall_mode="legacy")._recall_mode is RecallMode.LEGACY


# ---------------------------------------------------------------------------
# 2/3：影子历史 + 统计 + 快照
# ---------------------------------------------------------------------------

def _seed(m: MemorySystem) -> None:
    m.write_summary("我们聊过去日本旅行", source_turns=2, temperature=0.4)
    m.write_summary("你说喜欢喝拿铁", source_turns=1, temperature=0.5)
    m.write_summary("那天你提到工作累", source_turns=2, temperature=-0.5, importance=0.7)


def test_shadow_history_accumulates():
    m = MemorySystem(recall_mode=RecallMode.SHADOW)
    _seed(m)
    for q in ("旅行", "拿铁", "工作"):
        m.recall(q, current_warmth=0.0, limit=3)
    snap = m.get_debug_snapshot()
    assert snap["shadow_stats"] is not None
    assert snap["shadow_stats"]["samples"] == 3
    assert 0.0 <= snap["shadow_stats"]["avg_overlap"] <= 1.0
    assert len(snap["shadow_history"]) == 3


def test_shadow_history_capped():
    """历史滚动缓冲不超过上限。"""
    m = MemorySystem(recall_mode=RecallMode.SHADOW)
    _seed(m)
    for _ in range(m._SHADOW_HISTORY_MAX + 20):
        m.recall("旅行", current_warmth=0.0, limit=3)
    assert len(m._shadow_history) == m._SHADOW_HISTORY_MAX


def test_shadow_diff_fields():
    m = MemorySystem(recall_mode=RecallMode.SHADOW)
    _seed(m)
    m.recall("旅行", current_warmth=0.0, limit=3)
    diff = m._last_shadow_diff
    assert diff is not None
    for key in ("query", "legacy_top", "activation_top", "overlap",
                "only_legacy", "only_activation", "ts"):
        assert key in diff


def test_legacy_mode_no_shadow_history():
    """LEGACY 模式不产生影子历史。"""
    m = MemorySystem(recall_mode=RecallMode.LEGACY)
    _seed(m)
    m.recall("旅行", limit=3)
    snap = m.get_debug_snapshot()
    assert snap["shadow_stats"] is None


def test_snapshot_includes_recall_mode_and_params():
    m = MemorySystem(recall_mode=RecallMode.ACTIVATION)
    _seed(m)
    snap = m.get_debug_snapshot()
    assert snap["recall_mode"] == "activation"
    # 阶段1-3 参数都应在 params 里可观测
    for key in ("actr_d", "theta_clear", "l1_confidence", "emotion_privilege_k"):
        assert key in snap["params"]


def test_shadow_is_pure_observation():
    """SHADOW 的 activation 影子计算不得污染记忆状态（observe_only）。

    返回 legacy 结果；且命中条目的 actr_acc/last_recalled_ts 不被影子引擎改动。
    """
    m = MemorySystem(recall_mode=RecallMode.SHADOW)
    _seed(m)
    item = next(it for it in m._l1 if "旅行" in it.text)
    acc_before = item.actr_acc
    ts_before = item.last_recalled_ts
    results = m.recall("旅行", current_warmth=0.0, limit=3)
    # 返回的是 legacy 结果（无 activation 填充）
    assert all(r.activation == 0.0 for r in results)
    # 影子引擎不留痕（actr_acc 仅被 legacy 路径影响，而 legacy 不碰 actr_acc）
    assert item.actr_acc == acc_before
    # legacy 召回会刷 last_recalled_ts（命中刷新），但 actr_acc 必须纹丝不动
    _ = ts_before  # legacy 刷新 last_recalled_ts 属正常行为，此处不约束
