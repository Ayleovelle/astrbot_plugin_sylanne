"""v2.5.0 P0 slice 3：跨群记忆货架读侧测试。

design: docs/architecture/v250-cross-group-memory-design.md §2.2（R1-R6）/ §6
（开关表）/ §8 B6（R6 默认范围修订）。

本 slice 边界（严格遵守，测试同样只覆盖这些）：
- `_prepare_memory_context` 加货架并行召回支路（新增 `event` 形参）。
- R1 身份闸（event 解析当前发言人，认不出即整条 SKIP）。
- R2 私聊闸 / R3 跨群闸 / R6 提及降级的组合判定矩阵（`person_shelf.shelf_item_visible`）。
- R4 独立 formatter + 反向指令（`person_shelf.format_shelf_injection`）。
- R5 双闸冗余（查询阶段 / 注入组装阶段各自独立 try/except）。
- 6 键门控：default off 零成本、shadow 只算不注、on 真注入、scope=owner 身份门控、
  cross_dialogue 独立开关、visibility_tier 三档。

写侧（W0-W4）、PersonProfile 播种/软同步均不在本 slice 范围内。
"""

from __future__ import annotations

import asyncio
from typing import Any

from sylanne_alpha.person_shelf import (
    PersonShelfBucket,
    ShelfItem,
    format_shelf_injection,
    group_id_from_origin,
    person_shelf_kv_key,
    save_person_shelf,
    shelf_item_visible,
)
from sylanne_alpha.session_state_store import SessionStateStore
from sylanne_alpha.social_field import SocialFieldCollector


def _run(coro):
    return asyncio.run(coro)


# ===========================================================================
# 0. 纯函数矩阵测试：shelf_item_visible / group_id_from_origin / format_shelf_injection
# ===========================================================================


def test_group_id_from_origin_parses_group_prefix():
    assert group_id_from_origin("group:aiocqhttp:GroupMessage:g1") == "aiocqhttp:GroupMessage:g1"


def test_group_id_from_origin_non_group_returns_empty():
    assert group_id_from_origin("aiocqhttp:FriendMessage:u1") == ""
    assert group_id_from_origin("") == ""


def _item(origin_scope: str, origin_id: str, text: str = "some text") -> ShelfItem:
    return ShelfItem(
        text=text, origin_scope=origin_scope, origin_id=origin_id,
        created_at=1.0, weight=1.0,
    )


def test_r2_private_item_visible_only_in_private_context():
    it = _item("private", "aiocqhttp:FriendMessage:u1")
    assert shelf_item_visible(
        it, is_private_context=True, current_group_id="", tier="same_group",
        known_other_senders=None,
    )
    assert not shelf_item_visible(
        it, is_private_context=False, current_group_id="G1", tier="same_group",
        known_other_senders=None,
    )


def test_r3_group_item_always_visible_in_private_context():
    it = _item("group", "group:G1")
    assert shelf_item_visible(
        it, is_private_context=True, current_group_id="", tier="same_group",
        known_other_senders=None,
    )


def test_r3_group_item_always_visible_in_own_origin_group():
    it = _item("group", "group:G1")
    assert shelf_item_visible(
        it, is_private_context=False, current_group_id="G1", tier="same_group",
        known_other_senders=None,
    )
    # 即便 known_other_senders 是 None（拿不到名单），在"原场合"里也不受 R6 影响。
    assert shelf_item_visible(
        it, is_private_context=False, current_group_id="G1", tier="cross_group",
        known_other_senders=None,
    )


def test_r3_same_group_tier_drops_other_group():
    it = _item("group", "group:G_other")
    assert not shelf_item_visible(
        it, is_private_context=False, current_group_id="G_cur", tier="same_group",
        known_other_senders=None,
    )


def test_r3_cross_group_tier_allows_when_r6_confirms_clean():
    it = _item("group", "group:G_other", text="今天天气不错")
    assert shelf_item_visible(
        it, is_private_context=False, current_group_id="G_cur", tier="cross_group",
        known_other_senders={"someone_else"},
    )


def test_r6_locks_when_text_mentions_known_sender():
    it = _item("group", "group:G_other", text="张三今天迟到了")
    assert not shelf_item_visible(
        it, is_private_context=False, current_group_id="G_cur", tier="cross_group",
        known_other_senders={"张三"},
    )


def test_r6_failclosed_when_no_reliable_sender_list():
    """design 勘察 B3：拿不到可靠名单（None）→ fail-closed，视为已命中锁定。"""
    it = _item("group", "group:G_other", text="随便什么内容")
    assert not shelf_item_visible(
        it, is_private_context=False, current_group_id="G_cur", tier="cross_group",
        known_other_senders=None,
    )


def test_strict_tier_same_as_cross_group_for_r3_gate():
    it_clean = _item("group", "group:G_other", text="干净内容")
    assert shelf_item_visible(
        it_clean, is_private_context=False, current_group_id="G_cur", tier="strict",
        known_other_senders={"x"},
    )
    it_locked = _item("group", "group:G_other", text="随便")
    assert not shelf_item_visible(
        it_locked, is_private_context=False, current_group_id="G_cur", tier="strict",
        known_other_senders=None,
    )


def test_format_shelf_injection_contains_header_and_reverse_instruction():
    block = format_shelf_injection([_item("private", "sk", text="一起吃了火锅")])
    assert "[跨场合记忆参考]" in block
    assert "不复述、不外传" in block
    assert "一起吃了火锅" in block


def test_format_shelf_injection_empty_items_returns_empty():
    assert format_shelf_injection([]) == ""


def test_format_shelf_injection_all_blank_text_returns_empty():
    assert format_shelf_injection([_item("private", "sk", text="   ")]) == ""


# ===========================================================================
# 集成测试：直调真实 _prepare_memory_context（不复刻逻辑）
# ===========================================================================


class _FakeEngine:
    def observe(self) -> dict[str, float]:
        return {"warmth": 0.5}


class _FakeComputation:
    engine = _FakeEngine()


class _FakeKernel:
    computation = _FakeComputation()


class _FakeHost:
    kernel = _FakeKernel()


class _FakeMemorySystem:
    """主召回路径的替身：恒不命中，隔离本 slice 只测货架支路。"""

    def recall(self, **kwargs: Any) -> list:
        return []

    def format_recall_injection(self, results: list, max_items: int = 3) -> str:
        return ""

    def consume_pending_followups_by_text(self, text: str) -> None:
        pass


class _FakeSocialField:
    def __init__(self, known_senders: dict[str, set[str]] | None = None) -> None:
        self._known = known_senders or {}

    def peek_recent_group_senders(self, group_id: str) -> set[str]:
        return set(self._known.get(group_id, set()))


class _FakeMessageType:
    """`getattr(mt, "name", "")` 是读侧 is_group/current_group_id 判定唯一读取
    方式，不必依赖真实 astrbot MessageType 枚举。"""

    def __init__(self, name: str) -> None:
        self.name = name


_FRIEND_MT = _FakeMessageType("FRIEND_MESSAGE")
_GROUP_MT = _FakeMessageType("GROUP_MESSAGE")


class _FakeEvent:
    """生产形态事件替身（slice-1b）：只暴露 get_sender_id()/get_message_type()/
    get_group_id()/get_platform_id()，绝不设裸 sender_id/user_id 属性——镜像
    真实 AstrMessageEvent 的可见接口。R1 身份闸的 platform/is_group/
    current_group_id 现在全部由这些方法算出，不再解析 session_key 字符串。
    """

    def __init__(
        self,
        sender_id: str = "",
        *,
        message_type: _FakeMessageType = _FRIEND_MT,
        group_id: str = "",
        platform_id: str = "aiocqhttp",
    ) -> None:
        self._sender_id = sender_id
        self._message_type = message_type
        self._group_id = group_id
        self._platform_id = platform_id

    def get_sender_id(self) -> str:
        return self._sender_id

    def get_message_type(self) -> _FakeMessageType:
        return self._message_type

    def get_group_id(self) -> str:
        return self._group_id

    def get_platform_id(self) -> str:
        return self._platform_id


class _FakePlugin:
    def __init__(
        self,
        *,
        mode: str = "off",
        scope: str = "owner",
        owner_id: str = "",
        tier: str = "same_group",
        cross_dialogue: bool = True,
        known_senders: dict[str, set[str]] | None = None,
        shared_kv: dict[str, Any] | None = None,
    ) -> None:
        self._store = SessionStateStore()
        self.config: dict[str, Any] = {
            "sylanne_alpha_owner_id": owner_id,
            "sylanne_enable_v2core": False,
        }
        self._config: dict[str, Any] = {}
        self._kv: dict[str, Any] = shared_kv if shared_kv is not None else {}
        self._kv_get_calls: list[str] = []
        self._social_field = _FakeSocialField(known_senders)
        self._mode = mode
        self._scope = scope
        self._tier = tier
        self._cross_dialogue = cross_dialogue
        self._mem = _FakeMemorySystem()
        self._host_obj = _FakeHost()

    async def get_kv_data(self, key: str, default: Any = None) -> Any:
        self._kv_get_calls.append(key)
        return self._kv.get(key, default)

    async def put_kv_data(self, key: str, value: Any) -> None:
        self._kv[key] = value

    async def delete_kv_data(self, key: str) -> None:
        self._kv.pop(key, None)

    def _cfg(self, key: str, default: str = "") -> str:
        if key == "sylanne_alpha_cross_session_mode":
            return self._mode
        if key == "sylanne_alpha_cross_session_scope":
            return self._scope
        if key == "sylanne_alpha_cross_visibility_tier":
            return self._tier
        return default

    def _cfg_bool(self, key: str, default: bool = False) -> bool:
        if key == "sylanne_alpha_cross_dialogue":
            return self._cross_dialogue
        return default

    def _memory_system_for_session(self, session_key: str) -> _FakeMemorySystem:
        return self._mem

    def _host(self, session_key: str) -> _FakeHost:
        return self._host_obj


def _mk_pipeline(plugin: _FakePlugin):
    from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline

    pipe = LLMRequestPipeline.__new__(LLMRequestPipeline)
    pipe._p = plugin
    return pipe


def _seed_shelf(plugin: _FakePlugin, platform: str, sender_id: str, items: list[ShelfItem]) -> None:
    _run(save_person_shelf(plugin, platform, sender_id, PersonShelfBucket(items=items)))


def _prepare(
    pipe, session_key: str, event: Any, *,
    message_text: str = "嗨", history_depth: int | None = None,
):
    return _run(
        pipe._prepare_memory_context(
            session_key, message_text, gap_seconds=1000.0, realtime_enabled=True,
            history_depth=history_depth, event=event,
        )
    )


# ---------------------------------------------------------------------------
# 1. default off = 零成本 no-op（不查 KV）
# ---------------------------------------------------------------------------


def test_default_off_never_touches_shelf_kv():
    plugin = _FakePlugin(mode="off")
    sk = "aiocqhttp:FriendMessage:u1"
    _seed_shelf(plugin, "aiocqhttp", "u1", [_item("private", sk, text="私房话")])
    pipe = _mk_pipeline(plugin)

    _unfinished, _outreach, memory_fragment = _prepare(pipe, sk, _FakeEvent(sender_id="u1"))

    assert "私房话" not in memory_fragment
    assert person_shelf_kv_key("aiocqhttp", "u1") not in plugin._kv_get_calls


def test_cross_dialogue_false_skips_even_when_mode_on():
    plugin = _FakePlugin(mode="on", scope="all", cross_dialogue=False)
    sk = "aiocqhttp:FriendMessage:u2"
    _seed_shelf(plugin, "aiocqhttp", "u2", [_item("private", sk, text="不该出现")])
    pipe = _mk_pipeline(plugin)

    _unfinished, _outreach, memory_fragment = _prepare(pipe, sk, _FakeEvent(sender_id="u2"))

    assert "不该出现" not in memory_fragment


# ---------------------------------------------------------------------------
# 2. R1：认不出发言人 → 整条 SKIP
# ---------------------------------------------------------------------------


def test_r1_no_event_skips_shelf_recall():
    plugin = _FakePlugin(mode="on", scope="all")
    sk = "aiocqhttp:FriendMessage:u3"
    _seed_shelf(plugin, "aiocqhttp", "u3", [_item("private", sk, text="悄悄话")])
    pipe = _mk_pipeline(plugin)

    _unfinished, _outreach, memory_fragment = _prepare(pipe, sk, event=None)

    assert "悄悄话" not in memory_fragment


def test_r1_never_recalls_another_persons_shelf():
    """R1 身份闸：即便 KV 里同时存着别人的货架，识别出的发言人也只能看到
    自己名下那桶——不存在"遍历/搜索其他 P"的代码路径，本测试用共享 KV
    存储直接钉住这一点（防止未来重构不小心把 sender_id 参数传错）。
    """
    shared_kv: dict[str, Any] = {}
    plugin = _FakePlugin(mode="on", scope="all", shared_kv=shared_kv)
    _seed_shelf(
        plugin, "aiocqhttp", "u3a", [_item("private", "aiocqhttp:FriendMessage:u3a", text="u3a的私事")],
    )
    _seed_shelf(
        plugin, "aiocqhttp", "u3b", [_item("private", "aiocqhttp:FriendMessage:u3b", text="u3b的私事")],
    )
    pipe = _mk_pipeline(plugin)

    sk = "aiocqhttp:FriendMessage:u3a"
    _unfinished, _outreach, memory_fragment = _prepare(pipe, sk, _FakeEvent(sender_id="u3a"))

    assert "u3a的私事" in memory_fragment
    assert "u3b的私事" not in memory_fragment
    assert person_shelf_kv_key("aiocqhttp", "u3b") not in plugin._kv_get_calls


def test_r1_unresolvable_sender_id_skips():
    plugin = _FakePlugin(mode="on", scope="all")
    sk = "aiocqhttp:FriendMessage:u4"
    _seed_shelf(plugin, "aiocqhttp", "u4", [_item("private", sk, text="悄悄话2")])
    pipe = _mk_pipeline(plugin)

    _unfinished, _outreach, memory_fragment = _prepare(pipe, sk, _FakeEvent())  # 空 sender_id/user_id

    assert "悄悄话2" not in memory_fragment


# ---------------------------------------------------------------------------
# 3. on 模式端到端：私聊放行 private + group 恒放行；群聊丢弃 private
# ---------------------------------------------------------------------------


def test_on_mode_private_context_shows_private_and_group_items():
    plugin = _FakePlugin(mode="on", scope="all")
    sk = "u5"
    _seed_shelf(
        plugin, "aiocqhttp", "u5",
        [
            _item("private", sk, text="私聊内容甲"),
            _item("group", "group:g1", text="群里聊过乙"),
        ],
    )
    pipe = _mk_pipeline(plugin)

    _unfinished, _outreach, memory_fragment = _prepare(pipe, sk, _FakeEvent(sender_id="u5"))

    assert "私聊内容甲" in memory_fragment
    assert "群里聊过乙" in memory_fragment
    assert "[跨场合记忆参考]" in memory_fragment


def test_on_mode_group_context_drops_private_items():
    plugin = _FakePlugin(mode="on", scope="all")
    sk = "u6_g2"  # 生产形态：unique_session ON 群聊 session_key
    _seed_shelf(
        plugin, "aiocqhttp", "u6",
        [
            _item("private", "u6", text="私聊内容丙"),
            _item("group", "group:g2", text="本群内容丁"),  # slice-1b：bare 群号
        ],
    )
    pipe = _mk_pipeline(plugin)

    ev = _FakeEvent(sender_id="u6", message_type=_GROUP_MT, group_id="g2")
    _unfinished, _outreach, memory_fragment = _prepare(pipe, sk, ev)

    assert "私聊内容丙" not in memory_fragment
    assert "本群内容丁" in memory_fragment


# ---------------------------------------------------------------------------
# 4. tier 档：same_group 丢弃跨群；cross_group 经 R6 放行/锁定
# ---------------------------------------------------------------------------


def test_same_group_tier_drops_cross_group_item():
    plugin = _FakePlugin(mode="on", scope="all", tier="same_group")
    sk = "u7_g3"
    _seed_shelf(
        plugin, "aiocqhttp", "u7",
        [_item("group", "group:g_other", text="别的群聊过的事")],
    )
    pipe = _mk_pipeline(plugin)

    ev = _FakeEvent(sender_id="u7", message_type=_GROUP_MT, group_id="g3")
    _unfinished, _outreach, memory_fragment = _prepare(pipe, sk, ev)

    assert "别的群聊过的事" not in memory_fragment


def test_cross_group_tier_allows_when_r6_confirms_clean_end_to_end():
    plugin = _FakePlugin(
        mode="on", scope="all", tier="cross_group",
        known_senders={"g_other": {"路人甲"}},
    )
    sk = "u8_g4"
    _seed_shelf(
        plugin, "aiocqhttp", "u8",
        [_item("group", "group:g_other", text="今天天气不错")],
    )
    pipe = _mk_pipeline(plugin)

    ev = _FakeEvent(sender_id="u8", message_type=_GROUP_MT, group_id="g4")
    _unfinished, _outreach, memory_fragment = _prepare(pipe, sk, ev)

    assert "今天天气不错" in memory_fragment


def test_cross_group_tier_r6_locks_when_text_mentions_known_sender_end_to_end():
    plugin = _FakePlugin(
        mode="on", scope="all", tier="cross_group",
        known_senders={"g_other": {"路人甲"}},
    )
    sk = "u9_g5"
    _seed_shelf(
        plugin, "aiocqhttp", "u9",
        [_item("group", "group:g_other", text="路人甲今天没来")],
    )
    pipe = _mk_pipeline(plugin)

    ev = _FakeEvent(sender_id="u9", message_type=_GROUP_MT, group_id="g5")
    _unfinished, _outreach, memory_fragment = _prepare(pipe, sk, ev)

    assert "路人甲今天没来" not in memory_fragment


def test_cross_group_tier_failclosed_when_no_known_sender_data_end_to_end():
    """origin 群 shadow_buffer 空（常态，见 SocialFieldCollector.peek_recent_group_senders
    文档字符串）→ R6 fail-closed 锁定，即便内容本身毫无敏感信息也不放行跨群。
    """
    plugin = _FakePlugin(mode="on", scope="all", tier="cross_group", known_senders={})
    sk = "u10_g6"
    _seed_shelf(
        plugin, "aiocqhttp", "u10",
        [_item("group", "group:g_other", text="完全无害的内容")],
    )
    pipe = _mk_pipeline(plugin)

    ev = _FakeEvent(sender_id="u10", message_type=_GROUP_MT, group_id="g6")
    _unfinished, _outreach, memory_fragment = _prepare(pipe, sk, ev)

    assert "完全无害的内容" not in memory_fragment


# ---------------------------------------------------------------------------
# 5. scope=owner 身份门控（与写侧同形态）
# ---------------------------------------------------------------------------


def test_scope_owner_rejects_non_owner_sender():
    plugin = _FakePlugin(mode="on", scope="owner", owner_id="owner_1")
    sk = "aiocqhttp:FriendMessage:stranger"
    _seed_shelf(plugin, "aiocqhttp", "stranger", [_item("private", sk, text="陌生人的私货")])
    pipe = _mk_pipeline(plugin)

    _unfinished, _outreach, memory_fragment = _prepare(pipe, sk, _FakeEvent(sender_id="stranger"))

    assert "陌生人的私货" not in memory_fragment


def test_scope_owner_accepts_owner_sender():
    plugin = _FakePlugin(mode="on", scope="owner", owner_id="owner_1")
    sk = "aiocqhttp:FriendMessage:owner_1"
    _seed_shelf(plugin, "aiocqhttp", "owner_1", [_item("private", sk, text="主人的记忆")])
    pipe = _mk_pipeline(plugin)

    _unfinished, _outreach, memory_fragment = _prepare(pipe, sk, _FakeEvent(sender_id="owner_1"))

    assert "主人的记忆" in memory_fragment


def test_scope_owner_unconfigured_owner_id_rejects_everyone():
    plugin = _FakePlugin(mode="on", scope="owner", owner_id="")
    sk = "aiocqhttp:FriendMessage:u11"
    _seed_shelf(plugin, "aiocqhttp", "u11", [_item("private", sk, text="谁都看不到")])
    pipe = _mk_pipeline(plugin)

    _unfinished, _outreach, memory_fragment = _prepare(pipe, sk, _FakeEvent(sender_id="u11"))

    assert "谁都看不到" not in memory_fragment


# ---------------------------------------------------------------------------
# 6. shadow 模式：闸照常算但不注入
# ---------------------------------------------------------------------------


def test_shadow_mode_queries_shelf_but_does_not_inject():
    plugin = _FakePlugin(mode="shadow", scope="all")
    sk = "aiocqhttp:FriendMessage:u12"
    _seed_shelf(plugin, "aiocqhttp", "u12", [_item("private", sk, text="影子模式内容")])
    pipe = _mk_pipeline(plugin)

    _unfinished, _outreach, memory_fragment = _prepare(pipe, sk, _FakeEvent(sender_id="u12"))

    assert "影子模式内容" not in memory_fragment
    # 但确实查过 KV（"闸照常算"，而非因为其他门槛没过导致零查询）。
    assert person_shelf_kv_key("aiocqhttp", "u12") in plugin._kv_get_calls


# ---------------------------------------------------------------------------
# 7. R5 双闸冗余：查询/组装阶段任一层异常 → 空手，不泄漏部分内容
# ---------------------------------------------------------------------------


def test_r5_query_stage_exception_yields_empty_not_crash(monkeypatch):
    plugin = _FakePlugin(mode="on", scope="all")
    sk = "aiocqhttp:FriendMessage:u13"
    _seed_shelf(plugin, "aiocqhttp", "u13", [_item("private", sk, text="不该泄漏的内容")])
    pipe = _mk_pipeline(plugin)

    async def _boom(*a, **k):
        raise RuntimeError("kv boom")

    monkeypatch.setattr("sylanne_alpha.person_shelf.load_person_shelf", _boom)

    _unfinished, _outreach, memory_fragment = _prepare(pipe, sk, _FakeEvent(sender_id="u13"))

    assert "不该泄漏的内容" not in memory_fragment


def test_r5_assembly_stage_exception_yields_empty_not_partial(monkeypatch):
    plugin = _FakePlugin(mode="on", scope="all")
    sk = "aiocqhttp:FriendMessage:u14"
    _seed_shelf(plugin, "aiocqhttp", "u14", [_item("private", sk, text="组装阶段应被拦下")])
    pipe = _mk_pipeline(plugin)

    def _boom(*a, **k):
        raise RuntimeError("format boom")

    monkeypatch.setattr("sylanne_alpha.person_shelf.format_shelf_injection", _boom)

    _unfinished, _outreach, memory_fragment = _prepare(pipe, sk, _FakeEvent(sender_id="u14"))

    assert "组装阶段应被拦下" not in memory_fragment


# ---------------------------------------------------------------------------
# 7b. MINOR#2 回归（slice-1b）：货架召回支路必须与主召回同门 gate _history_anchored
#
# 主召回（:1692 `history_present=_history_anchored`）在历史缺失/病态轮
# （/reset、空回吞轮把 req.contexts 打空）内部丢弃近期幽灵召回（leg-2a）。
# 货架支路此前未消费这个门——开跨群 + /reset 时会把跨场合记忆当幽灵注入，
# 把无锚短轮劫持到不相干话题（跳话题回归）。修复：货架支路与主召回同一个
# `_history_anchored` 判据短路（history_depth < _MIN_HISTORY_TURNS_FOR_ANCHOR
# 时 _history_anchored=False）。
# ---------------------------------------------------------------------------


def test_shelf_recall_skipped_when_history_not_anchored():
    plugin = _FakePlugin(mode="on", scope="all")
    sk = "u16"
    _seed_shelf(plugin, "aiocqhttp", "u16", [_item("private", sk, text="瘦历史轮不该看到这条")])
    pipe = _mk_pipeline(plugin)

    ev = _FakeEvent(sender_id="u16")
    # history_depth=0 < _MIN_HISTORY_TURNS_FOR_ANCHOR(2) → _history_anchored=False
    _unfinished, _outreach, memory_fragment = _prepare(pipe, sk, ev, history_depth=0)

    assert "瘦历史轮不该看到这条" not in memory_fragment
    # 与主召回同门：短路应发生在"查 KV"之前，而非查到后再过滤（零成本短路）。
    assert person_shelf_kv_key("aiocqhttp", "u16") not in plugin._kv_get_calls


def test_shelf_recall_allowed_when_history_anchored():
    plugin = _FakePlugin(mode="on", scope="all")
    sk = "u17"
    _seed_shelf(plugin, "aiocqhttp", "u17", [_item("private", sk, text="正常轮应该召回这条")])
    pipe = _mk_pipeline(plugin)

    ev = _FakeEvent(sender_id="u17")
    # history_depth=5 >= _MIN_HISTORY_TURNS_FOR_ANCHOR(2) → _history_anchored=True
    _unfinished, _outreach, memory_fragment = _prepare(pipe, sk, ev, history_depth=5)

    assert "正常轮应该召回这条" in memory_fragment


def test_shelf_recall_allowed_when_history_depth_unknown():
    """history_depth=None（多为单测直调）按"历史在场"处理，保持既有行为零变化。"""
    plugin = _FakePlugin(mode="on", scope="all")
    sk = "u18"
    _seed_shelf(plugin, "aiocqhttp", "u18", [_item("private", sk, text="未知历史深度也应召回")])
    pipe = _mk_pipeline(plugin)

    ev = _FakeEvent(sender_id="u18")
    _unfinished, _outreach, memory_fragment = _prepare(pipe, sk, ev, history_depth=None)

    assert "未知历史深度也应召回" in memory_fragment


# ---------------------------------------------------------------------------
# 8. 空货架 / 空 platform：无内容可召回时安静返回空
# ---------------------------------------------------------------------------


def test_empty_shelf_bucket_returns_empty_fragment():
    plugin = _FakePlugin(mode="on", scope="all")
    sk = "aiocqhttp:FriendMessage:u15"  # 从未写过货架
    pipe = _mk_pipeline(plugin)

    _unfinished, _outreach, memory_fragment = _prepare(pipe, sk, _FakeEvent(sender_id="u15"))

    assert memory_fragment == ""


# ---------------------------------------------------------------------------
# 9. R6 生产格式覆盖：SocialFieldCollector 真实类的群键别名机制
#
# 红线闸 MAJOR 复核发现：本文件上面所有 cross_group/strict 用例都用
# `_FakeSocialField`，它的 `peek_recent_group_senders` 直接拿传入的 key 查
# 自己的 dict——不模拟生产环境里 `_groups`（用 `extract_group_id(event)`，
# aiocqhttp 下多为原始数字 group_id）与货架 `origin_id`（用
# `extract_group_id_from_key(session_key)`，形如
# "aiocqhttp:GroupMessage:123456"）两种格式不一致这件事。于是即便
# `SocialFieldCollector.peek_recent_group_senders` 没有别名兜底，上面的端到端
# 用例也会"假阳性"通过。这里直接用真实 `SocialFieldCollector`，验证：
# 1) 格式不一致且未注册别名时确实查空（复现红线闸描述的故障模式）；
# 2) `register_group_key_alias` registered 后 `peek_recent_group_senders`
#    才能用货架格式的 key 查到真实群状态（修复生效）。
# ---------------------------------------------------------------------------


def test_peek_recent_group_senders_misses_without_alias_when_keys_differ():
    """复现红线闸描述的故障：写入用原始群 key（如 aiocqhttp 的数字 group_id），
    用货架/origin_id 格式的 key 去 peek，在没有别名登记时必然查空。
    """
    social = SocialFieldCollector()
    social.collect(group_id="g_other", sender_id="路人甲", text="随便聊聊")

    shelf_format_key = "aiocqhttp:GroupMessage:g_other"
    assert social.peek_recent_group_senders(shelf_format_key) == set()
    # 用原始格式查则能查到——证明数据确实在，只是 key 格式不同导致查不到。
    assert social.peek_recent_group_senders("g_other") == {"路人甲"}


def test_peek_recent_group_senders_resolves_via_registered_alias():
    """修复：`register_group_key_alias` 登记别名后，货架格式的 key 能正确
    解析到 `collect()` 建立的原始群状态。
    """
    social = SocialFieldCollector()
    social.collect(group_id="g_other", sender_id="路人甲", text="随便聊聊")

    shelf_format_key = "aiocqhttp:GroupMessage:g_other"
    social.register_group_key_alias(shelf_format_key, "g_other")

    assert social.peek_recent_group_senders(shelf_format_key) == {"路人甲"}


def test_register_group_key_alias_noop_when_formats_already_match():
    """alias_key == raw_group_id（如非 aiocqhttp 平台推导恰好一致）时不必
    登记，peek 走 `_groups` 直查即可命中，无需别名。
    """
    social = SocialFieldCollector()
    social.collect(group_id="same_fmt_g1", sender_id="路人乙", text="消息")

    social.register_group_key_alias("same_fmt_g1", "same_fmt_g1")

    assert social.peek_recent_group_senders("same_fmt_g1") == {"路人乙"}
    assert "same_fmt_g1" not in social._group_key_aliases
