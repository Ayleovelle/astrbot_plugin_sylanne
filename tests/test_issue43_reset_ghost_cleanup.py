"""issue43 PRIMARY 修复回归：AstrBot /reset 幽灵源清理。

覆盖：
- MemorySystem._gather_pool 纪元门控：pre-reset 记忆不再自动浮现，但物理保留。
- MemorySystem.clear_l1_hot_pool：清空 L1 热池。
- main.py 的 after_message_sent 钩子：读 event.get_extra("_clean_ltm_session")
  触发 _on_session_reset，且只在该标记为真时才动作（不误清无关会话）。
- _on_session_reset 清 L1/纪元边界/ConversationBuffer/pending_outreach_context，
  不触碰 L2/L3 记忆本体与关系/人格状态（冻结面之外的东西完全不摸）。
"""

from __future__ import annotations

import asyncio
import importlib
import sys
import time
from types import SimpleNamespace

from sylanne_alpha.memory_system import ConversationBuffer, MemorySystem


# ---------------------------------------------------------------------------
# MemorySystem 层：纪元门控 + L1 清空
# ---------------------------------------------------------------------------


def test_epoch_boundary_default_zero_no_behavior_change():
    """未触发过 /reset 的 MemorySystem：边界恒 0.0，召回行为零变化。"""
    mem = MemorySystem()
    assert mem._recall_epoch_boundary == 0.0
    mem.write_summary("普通的一句话", session_key="s1")
    results = mem.recall(query="普通的一句话", current_warmth=0.0, limit=5)
    assert any("普通的一句话" in r.text for r in results)


def test_epoch_boundary_gates_l1_temporal_proximity_ghost():
    """核心回归：/reset 后同一 unrelated query 不再靠 temporal_proximity 捞出幽灵。"""
    mem = MemorySystem()
    mem.write_summary("我们聊到了去日本旅行的计划", session_key="s1")

    # pre-reset baseline：unrelated query 靠 temporal_proximity 强制入池（复现根因）。
    before = mem.recall(query="今天天气怎么样", current_warmth=0.0, limit=5)
    assert any("日本旅行" in r.text for r in before)

    time.sleep(0.02)
    mem.set_recall_epoch_boundary(time.time())
    mem.clear_l1_hot_pool()

    after = mem.recall(query="今天天气怎么样", current_warmth=0.0, limit=5)
    assert not any("日本旅行" in r.text for r in after)


def test_epoch_boundary_gates_l2_but_does_not_delete():
    """L2（已下沉）同样被纪元门控挡在自动召回外，但条目本身不删除。"""
    mem = MemorySystem()
    mem.write_summary("承诺过要一起去看流星雨", session_key="s1")
    item = mem._l1[-1]
    mem._l2.append(item)

    time.sleep(0.02)
    mem.set_recall_epoch_boundary(time.time())

    after = mem.recall(query="流星", current_warmth=0.0, limit=5)
    assert not any("流星雨" in r.text for r in after)
    # 非破坏：条目仍在 L2 里，没被删除/清零。
    assert any("流星雨" in it.text for it in mem._l2)


def test_epoch_boundary_does_not_block_fresh_post_reset_memory():
    """门控只挡 created_at < epoch 的旧条目，重置后的新记忆正常召回。"""
    mem = MemorySystem()
    mem.set_recall_epoch_boundary(time.time())
    time.sleep(0.02)
    mem.write_summary("我们聊到了猫咪叫小豆", session_key="s1")
    results = mem.recall(query="猫咪叫什么名字", current_warmth=0.0, limit=5)
    assert any("小豆" in r.text for r in results)


def test_clear_l1_hot_pool_empties_l1_returns_count():
    mem = MemorySystem()
    mem.write_summary("第一条", session_key="s1")
    mem.write_summary("第二条", session_key="s1")
    assert len(mem._l1) == 2
    cleared = mem.clear_l1_hot_pool()
    assert cleared == 2
    assert len(mem._l1) == 0


# ---------------------------------------------------------------------------
# main.py 集成：hook 读取 extra + _on_session_reset 清理范围
# ---------------------------------------------------------------------------


def _load_main_module():
    """按需导入 main 模块。

    刻意不做 `sys.modules.pop("main")` 强制重载——本仓已知的 sys.path 结构下
    存在与外部 AstrBot 安装同名的 main.py（G:/Bugfinders/AstrBot/main.py），
    在某些测试收集顺序下 pop 后的裸 import 可能拾到错误的那个（与本次修复
    无关的既有环境脆弱性，其他文件如 test_astrbot_manager_integration.py 也有
    同样的 pop 用法，但单独跑时不触发）。这里复用 pytest 会话中已缓存的正确
    sys.modules["main"]（若尚未导入过则走一次全新 import，同样安全——本仓
    main.py 首次被导入时会把插件目录塞进 sys.path[0]，足以保证首次 import
    拿到正确文件）。
    """
    if "main" in sys.modules:
        return sys.modules["main"]
    return importlib.import_module("main")


def _make_plugin(main_mod):
    return main_mod.EmotionalStatePlugin(context=SimpleNamespace(), config={})


def test_on_session_reset_clears_l1_epoch_and_buffers_preserves_l2():
    main_mod = _load_main_module()
    plugin = _make_plugin(main_mod)
    session_key = "room:reset_test"

    mem = plugin._memory_system_for_session(session_key)
    mem.write_summary("幽灵话题：去日本旅行", session_key=session_key)
    ghost_item = mem._l1[-1]
    mem._l2.append(ghost_item)  # 模拟已下沉的一份

    conv_buf = plugin._store.conversation_buffers.get_or_create(
        session_key, lambda: ConversationBuffer(session_key=session_key)
    )
    conv_buf.append("user", "还记得日本旅行吗")
    assert conv_buf.messages

    plugin._store.pending_outreach_context.set(
        session_key, {"reason": "life_event ghost", "mood": "开心", "event_id": "e1"}
    )

    plugin._on_session_reset(session_key)

    # L1 清空
    assert len(mem._l1) == 0
    # 纪元边界已推进（非零）
    assert mem._recall_epoch_boundary > 0.0
    # ConversationBuffer 已清空
    assert conv_buf.messages == []
    # pending_outreach_context 已清除
    assert plugin._store.pending_outreach_context.get(session_key) is None
    # 非破坏：L2 条目仍然存在（只是纪元门控，不删除）
    assert any("日本旅行" in it.text for it in mem._l2)
    # 门控确实生效：unrelated query 不再自动召回该 L2 条目
    after = mem.recall(query="今天天气如何", current_warmth=0.0, limit=5)
    assert not any("日本旅行" in r.text for r in after)


def test_after_message_sent_hook_triggers_on_clean_ltm_session_extra():
    """钩子只在 event.get_extra('_clean_ltm_session') 为真时才触发清理。"""
    main_mod = _load_main_module()
    plugin = _make_plugin(main_mod)
    session_key = "room:hook_test"

    mem = plugin._memory_system_for_session(session_key)
    mem.write_summary("幽灵：上次聊的项目", session_key=session_key)
    assert len(mem._l1) == 1

    class _FakeEvent:
        def __init__(self, extra: dict, session_id: str):
            self._extra = extra
            self.session_id = session_id
            self.unified_msg_origin = session_id

        def get_extra(self, key, default=None):
            return self._extra.get(key, default)

    # 未设置标记：不应清理。
    ev_noop = _FakeEvent({}, session_key)
    asyncio.run(
        plugin.on_after_message_sent_reset_ghost_cleanup(ev_noop)
    )
    assert len(mem._l1) == 1, "未设置 _clean_ltm_session 时不应清理"

    # 设置标记（复刻 AstrBot 内置 /reset 的 set_extra 行为）：应清理。
    ev_reset = _FakeEvent({"_clean_ltm_session": True}, session_key)
    asyncio.run(
        plugin.on_after_message_sent_reset_ghost_cleanup(ev_reset)
    )
    assert len(mem._l1) == 0, "设置 _clean_ltm_session=True 后应清空 L1"
    assert mem._recall_epoch_boundary > 0.0


def test_on_session_reset_does_not_touch_l3_nodes_object_identity():
    """L3 图谱节点对象本身不被清空/替换（只在门控条件下不再入池，不动数据结构）。"""
    main_mod = _load_main_module()
    plugin = _make_plugin(main_mod)
    session_key = "room:l3_test"
    mem = plugin._memory_system_for_session(session_key)

    from sylanne_alpha.memory_system import GraphNode

    node = GraphNode(
        id="n1", label="日本旅行", type="event", temporal_type="episodic",
        clarity=0.9, emotion_weight=0.5, created_at=time.time(),
        last_recalled_ts=0.0, recall_count=0,
    )
    mem._l3_nodes["n1"] = node

    plugin._on_session_reset(session_key)

    assert "n1" in mem._l3_nodes
    assert mem._l3_nodes["n1"] is node
