"""v2.5.0 P0 slice 1：跨群记忆地基测试。

design: docs/architecture/v250-cross-group-memory-design.md §8（B1/B2/B3）+ §6（6 开关）。

本 slice 边界（严格遵守，测试同样只覆盖这些）：
- B1：已认证实时 sender 暂存层（session_state_store.py + main.py on_message 接线）。
- ShelfItem / PersonShelfBucket（person_shelf.py）：dataclass + KV 读写 + B2 载入加固。
- PersonProfile（person_profile.py）：dataclass + KV 读写 + B2 载入加固 + 衰减纯函数。
- 6 个跨群开关默认值（_conf_schema.json + cross_session_config.py）。
- MEMORY_KV_KEYS_MANIFEST 新增两键与本模块键生成函数一致（golden 测试同款断言）。

三写点（货架写/profile 软同步/出生播种）、W0 净化、R1-R6 读闸、purge 级联、
播种到 body 均 **不在本 slice 范围内**，本文件不测试这些（留后续 slice）。
"""

from __future__ import annotations

import asyncio
import json
import math
import time
import types
from pathlib import Path
from typing import Any

import main as main_mod
from sylanne_alpha.cross_session_config import CrossSessionSettings, cross_session_settings
from sylanne_alpha.memory_migration_spine import MEMORY_KV_KEYS_MANIFEST
from sylanne_alpha.person_profile import (
    VOLATILITY_HALF_LIFE_SECONDS,
    WARMTH_HALF_LIFE_SECONDS,
    PersonProfile,
    compute_delta_t,
    decay_profile_transient,
    decay_transient,
    load_person_profile,
    person_profile_kv_key,
    save_person_profile,
)
from sylanne_alpha.person_shelf import (
    PersonShelfBucket,
    ShelfItem,
    load_person_shelf,
    person_shelf_kv_key,
    platform_from_umo,
    save_person_shelf,
)
from sylanne_alpha.rhythm_learner import RhythmLearner
from sylanne_alpha.session_context import SessionContext
from sylanne_alpha.session_state_store import SessionStateStore

_REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# 假 KV 插件（供 person_shelf / person_profile 的读写测试用）
# ---------------------------------------------------------------------------


class _FakeKVPlugin:
    def __init__(self) -> None:
        self._kv: dict[str, Any] = {}

    async def get_kv_data(self, key: str, default: Any = None) -> Any:
        return self._kv.get(key, default)

    async def put_kv_data(self, key: str, value: Any) -> None:
        self._kv[key] = value


# ===========================================================================
# B1：已认证实时 sender 暂存层
# ===========================================================================


def test_store_stash_authenticated_identity_noop_on_none():
    store = SessionStateStore()
    store.stash_authenticated_identity("sk1", None)
    assert store.get_authenticated_sender("sk1") is None
    assert store.get_authenticated_identity("sk1") is None


def test_store_set_authenticated_identity_roundtrip():
    store = SessionStateStore()
    store.set_authenticated_identity(
        "sk1", sender_id="u1", platform="aiocqhttp",
        origin_scope="private", origin_id="sk1",
    )
    assert store.get_authenticated_sender("sk1") == "u1"
    rec = store.get_authenticated_identity("sk1")
    assert rec == {
        "sender_id": "u1", "platform": "aiocqhttp",
        "origin_scope": "private", "origin_id": "sk1",
    }


def test_store_get_authenticated_sender_missing_key_returns_none():
    store = SessionStateStore()
    assert store.get_authenticated_sender("nope") is None
    assert store.get_authenticated_identity("nope") is None


def test_store_set_authenticated_identity_rejects_empty_sender_or_platform():
    store = SessionStateStore()
    store.set_authenticated_identity("sk1", sender_id="", platform="aiocqhttp")
    assert store.get_authenticated_identity("sk1") is None
    store.set_authenticated_identity("sk2", sender_id="u1", platform="")
    assert store.get_authenticated_identity("sk2") is None


def test_store_stash_authenticated_identity_flip_sender_collapses():
    """次判据：同一 session_key 先后两次主判据放行但 sender_id 不同（发言人
    翻脸）→ 判定该 session_key 实为共享桶，坍缩后旧暂存被清、且标记坍缩。
    """
    store = SessionStateStore()
    ident_a = {"sender_id": "alice", "platform": "aiocqhttp",
               "origin_scope": "group", "origin_id": "group:g1"}
    ident_b = {"sender_id": "bob", "platform": "aiocqhttp",
               "origin_scope": "group", "origin_id": "group:g1"}
    store.stash_authenticated_identity("weird_shared_sid", ident_a)
    assert store.get_authenticated_sender("weird_shared_sid") == "alice"
    assert not store.is_collapsed_shared_session("weird_shared_sid")

    store.stash_authenticated_identity("weird_shared_sid", ident_b)
    assert store.get_authenticated_sender("weird_shared_sid") is None
    assert store.is_collapsed_shared_session("weird_shared_sid")


def test_store_collapsed_session_stays_skipped_even_for_original_sender():
    """一旦坍缩，此后永久 SKIP——即便"翻脸"过去的原发言人又发言，也不再暂存
    （单调收紧，不会解除坍缩标记）。
    """
    store = SessionStateStore()
    ident_a = {"sender_id": "alice", "platform": "aiocqhttp",
               "origin_scope": "group", "origin_id": "group:g1"}
    ident_b = {"sender_id": "bob", "platform": "aiocqhttp",
               "origin_scope": "group", "origin_id": "group:g1"}
    store.stash_authenticated_identity("weird_shared_sid", ident_a)
    store.stash_authenticated_identity("weird_shared_sid", ident_b)  # 坍缩
    store.stash_authenticated_identity("weird_shared_sid", ident_a)  # alice 再来一次
    assert store.get_authenticated_sender("weird_shared_sid") is None
    assert store.is_collapsed_shared_session("weird_shared_sid")


# ---------------------------------------------------------------------------
# 生产形态事件替身：只暴露 get_sender_id()/get_message_type()/get_group_id()/
# get_platform_id()/session_id/unified_msg_origin，绝不设裸 sender_id/user_id
# 属性——镜像真实 AstrMessageEvent 的可见接口（astr_message_event.py:183-207）。
# 本次要修的哑火缺陷正是被"假事件带裸 sender_id 属性"掩盖过一次（见 design
# 背景段），故本文件所有 on_message 测试改用这套替身，禁止再靠裸属性造 per-user。
# ---------------------------------------------------------------------------


class _ProdMessageType:
    """`getattr(mt, "name", "")` 是 resolve_authenticated_identity 唯一读取
    方式，故只需还原"有 .name 属性的对象"这个接口形状，不必依赖真实 astrbot
    MessageType 枚举（真实值：GROUP_MESSAGE/FRIEND_MESSAGE/OTHER_MESSAGE）。
    """

    def __init__(self, name: str) -> None:
        self.name = name


_FRIEND_MT = _ProdMessageType("FRIEND_MESSAGE")
_GROUP_MT = _ProdMessageType("GROUP_MESSAGE")
_OTHER_MT = _ProdMessageType("OTHER_MESSAGE")


class _ProdEvent:
    """生产形态事件替身（无裸 sender_id/user_id 属性）。"""

    def __init__(
        self,
        *,
        sender_id: str,
        message_type: _ProdMessageType,
        session_id: str,
        group_id: str = "",
        platform_id: str = "aiocqhttp",
        text: str = "hi",
    ) -> None:
        self._sender_id = sender_id
        self._message_type = message_type
        self.session_id = session_id
        self._group_id = group_id
        self._platform_id = platform_id
        self.message_str = text
        self.unified_msg_origin = (
            f"{platform_id}:{message_type.name}:{session_id}"
        )

    def get_sender_id(self) -> str:
        return self._sender_id

    def get_message_type(self) -> _ProdMessageType:
        return self._message_type

    def get_group_id(self) -> str:
        return self._group_id

    def get_platform_id(self) -> str:
        return self._platform_id


def _private_event(sender_id: str, text: str = "hi") -> _ProdEvent:
    """私聊：session_id = 对端自己的裸 QQ（真实 aiocqhttp 适配器形状）。"""
    return _ProdEvent(
        sender_id=sender_id, message_type=_FRIEND_MT, session_id=sender_id, text=text,
    )


def _group_event(
    sender_id: str, group_id: str, *, unique_session: bool, text: str = "hi",
) -> _ProdEvent:
    """群聊：unique_session OFF 时 session_id == 裸 group_id（共享桶，B1 红线场景）；
    ON 时框架已在插件 handler 之前把 session_id 改写成 f"{sender}_{group}"。
    """
    session_id = f"{sender_id}_{group_id}" if unique_session else group_id
    return _ProdEvent(
        sender_id=sender_id, message_type=_GROUP_MT,
        session_id=session_id, group_id=group_id, text=text,
    )


def _other_event(sender_id: str = "u1") -> _ProdEvent:
    return _ProdEvent(
        sender_id=sender_id, message_type=_OTHER_MT, session_id="sess_other",
    )


def _mk_on_message_plugin() -> Any:
    """构造仅含 on_message 依赖的最小 fake plugin（沿用 test_wave_l1_g1_liveness.py 的
    既有模式：把插件真实方法用 MethodType 绑到最小 fake plugin，测真实逻辑）。
    """
    p = types.SimpleNamespace()
    p._session_ctx = SessionContext(p)
    p._store = SessionStateStore()
    p._life_simulator = None
    p._rhythm_learner = RhythmLearner(intimacy_threshold=0.6)

    async def _noop_save() -> None:
        return None

    p._rhythm_learner_throttled_save = _noop_save
    p.on_message = types.MethodType(main_mod.EmotionalStatePlugin.on_message, p)
    return p


def test_on_message_private_event_stashes_identity():
    """私聊天生 per-user：主判据首条即放行，暂存 sender/platform/origin=private。"""
    p = _mk_on_message_plugin()
    ev = _private_event("2300184498")
    asyncio.run(p.on_message(ev))
    session_key = p._session_ctx.session_key(ev)
    assert session_key == "2300184498"  # 生产上无裸属性，session_key 不再叠加后缀
    rec = p._store.get_authenticated_identity(session_key)
    assert rec == {
        "sender_id": "2300184498", "platform": "aiocqhttp",
        "origin_scope": "private", "origin_id": session_key,
    }


def test_on_message_group_unique_session_on_stashes_identity_with_group_origin():
    """群聊 unique_session ON（session_id != 裸 group_id）：per-user，放行暂存，
    origin_scope=group、origin_id=group:{真实群号}。
    """
    p = _mk_on_message_plugin()
    ev = _group_event("2300184498", "123456", unique_session=True)
    asyncio.run(p.on_message(ev))
    session_key = p._session_ctx.session_key(ev)
    assert session_key == "2300184498_123456"
    rec = p._store.get_authenticated_identity(session_key)
    assert rec == {
        "sender_id": "2300184498", "platform": "aiocqhttp",
        "origin_scope": "group", "origin_id": "group:123456",
    }


def test_on_message_group_unique_session_off_does_not_stash_shared_bucket():
    """B1 红线核心用例：群聊 unique_session OFF（session_id == 裸 group_id，
    共享桶）——首条消息即确定性 SKIP，不依赖任何历史/一致性积累（无冷启动洞）。
    """
    p = _mk_on_message_plugin()
    ev = _group_event("2300184498", "123456", unique_session=False)
    asyncio.run(p.on_message(ev))
    session_key = p._session_ctx.session_key(ev)
    assert session_key == "123456"  # 塌缩桶：裸群号，多用户共享
    assert p._store.get_authenticated_identity(session_key) is None
    assert p._store.get_authenticated_sender(session_key) is None


def test_on_message_group_unique_session_off_multiple_senders_never_leak():
    """同一共享桶下多个不同真实发言人轮流发言，暂存层始终为空（不会有任何
    一人被错误钉成"已认证 sender"）。
    """
    p = _mk_on_message_plugin()
    for sender in ("alice", "bob", "carol"):
        ev = _group_event(sender, "g_shared", unique_session=False)
        asyncio.run(p.on_message(ev))
    session_key = "g_shared"
    assert p._store.get_authenticated_identity(session_key) is None


def test_on_message_other_message_type_does_not_stash():
    """OTHER_MESSAGE（系统/未知类型）保守不放行。"""
    p = _mk_on_message_plugin()
    ev = _other_event("u1")
    asyncio.run(p.on_message(ev))
    session_key = p._session_ctx.session_key(ev)
    assert p._store.get_authenticated_identity(session_key) is None


def test_on_message_private_and_group_do_not_cross_contaminate():
    """私聊与共享群桶落在不同 session_key，暂存互不污染。"""
    p = _mk_on_message_plugin()
    asyncio.run(p.on_message(_group_event("u42", "g1", unique_session=False)))
    asyncio.run(p.on_message(_private_event("u42")))

    assert p._store.get_authenticated_identity("g1") is None
    assert p._store.get_authenticated_sender("u42") == "u42"


def test_on_message_survives_missing_sender_attrs_without_crashing():
    """事件完全没有 unified_msg_origin/sender 相关字段时也不应炸（on_message 外层
    已有 try/except，这里断言不抛异常且暂存层保持空)。
    """
    p = _mk_on_message_plugin()
    ev = types.SimpleNamespace(message_str="hi")
    asyncio.run(p.on_message(ev))  # 不应抛异常
    assert len(p._store.authenticated_senders) == 0


def test_on_message_secondary_heuristic_collapses_shared_bucket_misjudged_as_per_user():
    """次判据兜底（design open_risks）：某假想平台的 unique_session 语义特殊，
    共享群的 session_id 恰好也不等于 group_id（主判据误判为 per-user）——同一
    session_key 先后来自两个不同真实发言人时，第二条起判定坍缩，此后永久 SKIP。
    """
    p = _mk_on_message_plugin()
    weird_group_ev_alice = _ProdEvent(
        sender_id="alice", message_type=_GROUP_MT,
        session_id="weird_shared_sid", group_id="g_weird",
    )
    weird_group_ev_bob = _ProdEvent(
        sender_id="bob", message_type=_GROUP_MT,
        session_id="weird_shared_sid", group_id="g_weird",
    )
    asyncio.run(p.on_message(weird_group_ev_alice))
    assert p._store.get_authenticated_sender("weird_shared_sid") == "alice"

    asyncio.run(p.on_message(weird_group_ev_bob))
    assert p._store.get_authenticated_sender("weird_shared_sid") is None
    assert p._store.is_collapsed_shared_session("weird_shared_sid")

    # 坍缩后 alice 再发言也不再被暂存（单调收紧，不解除坍缩）。
    asyncio.run(p.on_message(weird_group_ev_alice))
    assert p._store.get_authenticated_sender("weird_shared_sid") is None


def test_on_message_real_astrbot_shaped_event_now_stashes_instead_of_leaking():
    """曾是哑火根因的回归用例（反向重写）：此前的实现用"裸属性判空"代理 B1
    判定，真实 AstrBot 事件（只暴露 get_sender_id()，无裸属性）对**所有**
    事件都会判定为空——包括私聊和 unique_session ON 的群聊，导致货架写点
    在生产上永久 SKIP，连本该天生 per-user 的私聊都不例外（连"跨群"都没
    跨到，插件在生产上从未真正写过一条货架）。

    修复：改用 `resolve_authenticated_identity`（get_sender_id + get_message_type
    + get_group_id + session_id 的组合矩阵），不再依赖裸属性。同一份"只暴露
    get_sender_id()"的生产形态事件，私聊/unique-on 群现在应该真正 stash；只有
    unique_session OFF 的共享桶（session_id == group_id）才继续 SKIP——B1 红线
    没有被放松，只是判定方式从"裸属性代理"换成了"事件方法直判"。
    """

    class _RealisticFriendEvent:
        unified_msg_origin = "aiocqhttp:FriendMessage:real_u7"
        message_str = "hi"
        session_id = "real_u7"

        def get_sender_id(self) -> str:
            return "real_u7"

        def get_message_type(self):
            return _FRIEND_MT

        def get_group_id(self) -> str:
            return ""

        def get_platform_id(self) -> str:
            return "aiocqhttp"

    class _RealisticSharedGroupEvent:
        unified_msg_origin = "aiocqhttp:GroupMessage:g3"
        message_str = "hi"
        session_id = "g3"  # unique_session OFF：与 group_id 相同

        def get_sender_id(self) -> str:
            return "real_u7"

        def get_message_type(self):
            return _GROUP_MT

        def get_group_id(self) -> str:
            return "g3"

        def get_platform_id(self) -> str:
            return "aiocqhttp"

    p = _mk_on_message_plugin()

    friend_ev = _RealisticFriendEvent()
    asyncio.run(p.on_message(friend_ev))
    friend_sk = p._session_ctx.session_key(friend_ev)
    assert friend_sk == "real_u7"  # session_key() 自身未改（既有行为）
    assert p._store.get_authenticated_sender(friend_sk) == "real_u7"  # 修复：现在真写入

    p2 = _mk_on_message_plugin()
    group_ev = _RealisticSharedGroupEvent()
    asyncio.run(p2.on_message(group_ev))
    group_sk = p2._session_ctx.session_key(group_ev)
    assert group_sk == "g3"  # 塌缩桶：裸 base，未变
    # B1 红线保留：共享桶（session_id == group_id）依旧零暂存。
    assert p2._store.get_authenticated_sender(group_sk) is None


# ===========================================================================
# person_shelf.py：ShelfItem / PersonShelfBucket + B2 载入加固
# ===========================================================================


def test_platform_from_umo_extracts_first_segment():
    assert platform_from_umo("aiocqhttp:GroupMessage:12345") == "aiocqhttp"
    assert platform_from_umo("qq") == "qq"


def test_platform_from_umo_failcloses_on_empty_or_malformed():
    assert platform_from_umo("") == ""
    assert platform_from_umo(None) == ""  # type: ignore[arg-type]


def test_person_shelf_kv_key_rejects_empty_platform_or_sender():
    assert person_shelf_kv_key("", "u1") == ""
    assert person_shelf_kv_key("qq", "") == ""
    assert person_shelf_kv_key("qq", "u1") == "sylanne_person_shelf:qq:u1"


def test_shelf_item_rejects_nan_inf_created_at_and_weight():
    item = ShelfItem(
        text="hi", origin_scope="private", origin_id="p1",
        created_at=float("nan"), weight=float("inf"),
    )
    assert item.created_at == 0.0
    assert item.weight == 0.0


def test_shelf_item_rejects_negative_infinity_weight():
    item = ShelfItem(
        text="hi", origin_scope="private", origin_id="p1",
        created_at=1.0, weight=float("-inf"),
    )
    assert item.weight == 0.0


def test_shelf_item_normalizes_missing_origin_scope_to_private():
    item = ShelfItem(text="a", origin_scope=None, origin_id="", created_at=1.0, weight=0.5)  # type: ignore[arg-type]
    assert item.origin_scope == "private"


def test_shelf_item_normalizes_illegal_origin_scope_to_private():
    item = ShelfItem(text="a", origin_scope="bogus", origin_id="", created_at=1.0, weight=0.5)
    assert item.origin_scope == "private"


def test_shelf_item_keeps_legal_group_origin_scope():
    item = ShelfItem(text="a", origin_scope="group", origin_id="group:G", created_at=1.0, weight=0.5)
    assert item.origin_scope == "group"


def test_shelf_item_from_dict_missing_fields_uses_defaults():
    item = ShelfItem.from_dict({})
    assert item.text == ""
    assert item.origin_scope == "private"
    assert item.origin_id == ""
    assert item.created_at == 0.0
    assert item.weight == 0.0
    assert item.schema_ver == 1


def test_person_shelf_bucket_from_dict_skips_non_dict_items():
    raw = {
        "items": [
            {"text": "ok", "origin_scope": "private", "origin_id": "p", "created_at": 1.0, "weight": 0.5},
            "not-a-dict",
            {"text": "bad_created", "origin_scope": "group", "origin_id": "g", "created_at": float("nan"), "weight": 0.2},
        ],
        "schema_ver": 1,
    }
    bucket = PersonShelfBucket.from_dict(raw)
    # "not-a-dict" 被跳过；"bad_created" 仍保留但 created_at 归零（单字段消毒，非整条拒绝）
    assert len(bucket.items) == 2
    assert bucket.items[1].created_at == 0.0


def test_person_shelf_bucket_from_dict_non_dict_input_returns_empty():
    assert PersonShelfBucket.from_dict(None).items == []
    assert PersonShelfBucket.from_dict("garbage").items == []


def test_person_shelf_bucket_truncates_oversized_keeps_newest():
    items = [
        {"text": f"t{i}", "origin_scope": "private", "origin_id": "p", "created_at": float(i), "weight": 0.1}
        for i in range(250)
    ]
    bucket = PersonShelfBucket.from_dict({"items": items, "schema_ver": 1})
    assert len(bucket.items) == 200
    assert bucket.items[0].created_at == 249.0  # 最新的排最前


def test_person_shelf_kv_roundtrip():
    plugin = _FakeKVPlugin()
    bucket = PersonShelfBucket(
        items=[ShelfItem(text="hi", origin_scope="private", origin_id="priv:1", created_at=1.0, weight=0.4)]
    )
    asyncio.run(save_person_shelf(plugin, "aiocqhttp", "u1", bucket))
    loaded = asyncio.run(load_person_shelf(plugin, "aiocqhttp", "u1"))
    assert len(loaded.items) == 1
    assert loaded.items[0].text == "hi"
    assert loaded.items[0].origin_scope == "private"


def test_person_shelf_load_fail_closed_when_no_kv_api():
    plugin = types.SimpleNamespace()  # 无 get_kv_data
    loaded = asyncio.run(load_person_shelf(plugin, "qq", "u1"))
    assert loaded.items == []


def test_person_shelf_load_fail_closed_on_empty_platform_or_sender():
    plugin = _FakeKVPlugin()
    loaded = asyncio.run(load_person_shelf(plugin, "", "u1"))
    assert loaded.items == []


def test_person_shelf_save_noop_when_no_kv_api():
    plugin = types.SimpleNamespace()  # 无 put_kv_data
    # 不应抛异常
    asyncio.run(save_person_shelf(plugin, "qq", "u1", PersonShelfBucket()))


# ===========================================================================
# person_profile.py：PersonProfile + B2 载入加固
# ===========================================================================


def test_person_profile_rejects_nan_inf_transient_fields():
    profile = PersonProfile(
        warmth_transient=float("nan"),
        volatility_transient=float("inf"),
        valence=float("-inf"),
        arousal=float("nan"),
        tension=float("nan"),
    )
    assert profile.warmth_transient == 0.0
    assert profile.volatility_transient == 0.0
    assert profile.valence == 0.0
    assert profile.arousal == 0.0
    assert profile.tension == 0.0


def test_person_profile_last_interaction_ts_none_stays_none():
    profile = PersonProfile(last_interaction_ts=None)
    assert profile.last_interaction_ts is None


def test_person_profile_last_interaction_ts_nonfinite_normalizes_to_none():
    profile = PersonProfile(last_interaction_ts=float("nan"))
    assert profile.last_interaction_ts is None
    profile2 = PersonProfile(last_interaction_ts=float("inf"))
    assert profile2.last_interaction_ts is None


def test_person_profile_last_interaction_ts_valid_value_preserved():
    profile = PersonProfile(last_interaction_ts=123.0)
    assert profile.last_interaction_ts == 123.0


def test_person_profile_phase_illegal_failcloses_to_low_signal():
    profile = PersonProfile(phase="bogus")
    assert profile.phase == "low_signal"


def test_person_profile_phase_legal_values_preserved():
    for phase in ("low_signal", "forming_continuity", "active_continuity"):
        assert PersonProfile(phase=phase).phase == phase


def test_person_profile_six_snapshot_filters_unknown_keys_and_nonfinite():
    profile = PersonProfile(
        six_snapshot={"warmth_bias": 1.5, "unknown_trait": 0.9, "edge": float("nan")}
    )
    # unknown_trait 丢弃；edge(NaN) 丢弃；warmth_bias clamp 到 [0,1] 上限
    assert profile.six_snapshot == {"warmth_bias": 1.0}


def test_person_profile_six_snapshot_non_dict_input_normalizes_to_empty():
    profile = PersonProfile(six_snapshot="garbage")  # type: ignore[arg-type]
    assert profile.six_snapshot == {}


def test_person_profile_last_applied_transient_clamped_to_apply_cap():
    profile = PersonProfile(last_applied_transient=5.0)
    assert profile.last_applied_transient == 0.15
    profile2 = PersonProfile(last_applied_transient=-5.0)
    assert profile2.last_applied_transient == -0.15


def test_person_profile_counts_reject_negative_and_garbage():
    profile = PersonProfile(preference_count=-3, boundary_count="garbage")  # type: ignore[arg-type]
    assert profile.preference_count == 0
    assert profile.boundary_count == 0


def test_person_profile_to_dict_from_dict_roundtrip():
    profile = PersonProfile(
        preference_count=3,
        phase="forming_continuity",
        six_snapshot={"warmth_bias": 0.6},
        warmth_baseline=0.5,
        warmth_transient=0.1,
        volatility_transient=0.05,
        last_interaction_ts=1000.0,
        last_applied_transient=0.05,
    )
    restored = PersonProfile.from_dict(profile.to_dict())
    assert restored == profile


def test_person_profile_from_dict_missing_fields_uses_defaults():
    profile = PersonProfile.from_dict({})
    assert profile == PersonProfile()


def test_person_profile_kv_key_rejects_empty_platform_or_sender():
    assert person_profile_kv_key("", "u1") == ""
    assert person_profile_kv_key("qq", "") == ""
    assert person_profile_kv_key("qq", "u1") == "sylanne_person_profile:qq:u1"


def test_person_profile_kv_roundtrip():
    plugin = _FakeKVPlugin()
    profile = PersonProfile(warmth_baseline=0.6, phase="active_continuity")
    asyncio.run(save_person_profile(plugin, "qq", "u1", profile))
    loaded = asyncio.run(load_person_profile(plugin, "qq", "u1"))
    assert loaded == profile


def test_person_profile_load_fail_closed_when_no_kv_api():
    plugin = types.SimpleNamespace()
    loaded = asyncio.run(load_person_profile(plugin, "qq", "u1"))
    assert loaded == PersonProfile()


def test_person_profile_load_fail_closed_on_non_dict_raw():
    plugin = _FakeKVPlugin()
    key = person_profile_kv_key("qq", "u1")
    asyncio.run(plugin.put_kv_data(key, "garbage-not-a-dict"))
    loaded = asyncio.run(load_person_profile(plugin, "qq", "u1"))
    assert loaded == PersonProfile()


# ===========================================================================
# 衰减纯函数（design §4.2）
# ===========================================================================


def test_compute_delta_t_none_when_last_interaction_ts_none():
    assert compute_delta_t(100.0, None) is None


def test_compute_delta_t_none_when_nonfinite_inputs():
    assert compute_delta_t(float("nan"), 10.0) is None
    assert compute_delta_t(100.0, float("inf")) is None


def test_compute_delta_t_clamps_negative_to_zero():
    """时钟回拨（now < last_interaction_ts）：下限截断至 0，不放大衰减/不产生负值。"""
    assert compute_delta_t(90.0, 100.0) == 0.0


def test_compute_delta_t_normal_case():
    assert compute_delta_t(150.0, 100.0) == 50.0


def test_decay_transient_rejects_nonfinite_value_explicitly():
    """非有限值必须显式判定归零（不能依赖 abs(nan)<eps 的隐式判断）。"""
    assert decay_transient(float("nan"), 100.0, 3600.0) == 0.0
    assert decay_transient(float("inf"), 100.0, 3600.0) == 0.0


def test_decay_transient_rejects_nonfinite_delta_t():
    assert decay_transient(0.2, float("nan"), 3600.0) == 0.0
    assert decay_transient(0.2, float("inf"), 3600.0) == 0.0


def test_decay_transient_zero_delta_preserves_value():
    assert math.isclose(decay_transient(0.25, 0.0, 3600.0), 0.25)


def test_decay_transient_exact_half_life_halves_value():
    val = decay_transient(0.28, WARMTH_HALF_LIFE_SECONDS, WARMTH_HALF_LIFE_SECONDS)
    assert math.isclose(val, 0.14, rel_tol=1e-9)


def test_decay_transient_two_half_lives_quarters_value():
    val = decay_transient(0.28, WARMTH_HALF_LIFE_SECONDS * 2, WARMTH_HALF_LIFE_SECONDS)
    assert math.isclose(val, 0.07, rel_tol=1e-9)


def test_decay_transient_long_downtime_underflows_to_zero_safely():
    """长停机（Δt 巨大）是安全的——2^(-巨大) 浮点下溢趋近 0，不抛异常/不产生 inf
    （design §4.2 红队诚实纠正：真正危险的只有 Δt<0 与 NaN，不是长停机本身）。
    """
    huge_dt = 1e15
    val = decay_transient(0.3, huge_dt, WARMTH_HALF_LIFE_SECONDS)
    assert val == 0.0


def test_decay_transient_below_eps_snaps_to_zero():
    """约 10 个半衰期后 |value| < 0.02 归零阈值，视为归零。"""
    dt = WARMTH_HALF_LIFE_SECONDS * 10
    val = decay_transient(0.3, dt, WARMTH_HALF_LIFE_SECONDS)
    assert val == 0.0


def test_decay_transient_result_reclamped_to_storage_cap():
    """结果都要重新钳 ±0.3（存储帽）——不是只在写入时钳一次就假设后续计算维持不变量。"""
    val = decay_transient(0.5, 0.0, 3600.0)  # 衰减因子=1，原值 0.5 超出存储帽
    assert val == 0.3
    val_neg = decay_transient(-0.5, 0.0, 3600.0)
    assert val_neg == -0.3


def test_decay_transient_defends_against_negative_delta_t_internally():
    """即便调用方未经 compute_delta_t 直接传负 Δt，_decay_factor 内部仍下限截断至 0
    （双保险，见 person_profile._decay_factor）。
    """
    val = decay_transient(0.2, -500.0, WARMTH_HALF_LIFE_SECONDS)
    assert val == 0.2  # dt<0 截断为 0，衰减因子=1，原值不变


def test_decay_profile_transient_skips_when_last_interaction_ts_none():
    profile = PersonProfile(warmth_transient=0.2, volatility_transient=0.1, last_interaction_ts=None)
    out = decay_profile_transient(profile, time.time())
    assert out is profile  # 原样返回同一实例，不构造新对象


def test_decay_profile_transient_delegates_per_channel_half_life():
    now = 1_000_000.0
    last = now - 1000.0
    profile = PersonProfile(warmth_transient=0.25, volatility_transient=0.2, last_interaction_ts=last)
    out = decay_profile_transient(profile, now)
    assert out.warmth_transient == decay_transient(0.25, 1000.0, WARMTH_HALF_LIFE_SECONDS)
    assert out.volatility_transient == decay_transient(0.2, 1000.0, VOLATILITY_HALF_LIFE_SECONDS)
    assert out.warmth_transient != 0.25  # 确实衰减了（dt != 0）


def test_decay_profile_transient_does_not_mutate_input():
    profile = PersonProfile(warmth_transient=0.25, volatility_transient=0.2, last_interaction_ts=1000.0)
    decay_profile_transient(profile, 2000.0)
    assert profile.warmth_transient == 0.25  # 入参未被就地修改
    assert profile.volatility_transient == 0.2


def test_decay_profile_transient_does_not_touch_valence_arousal_tension():
    """valence/arousal/tension 本期"只存不施加"，没有定义半衰期，衰减函数不动它们。"""
    profile = PersonProfile(
        warmth_transient=0.2, volatility_transient=0.1,
        valence=0.4, arousal=0.3, tension=0.2,
        last_interaction_ts=1000.0,
    )
    out = decay_profile_transient(profile, 2000.0)
    assert out.valence == 0.4
    assert out.arousal == 0.3
    assert out.tension == 0.2


# ===========================================================================
# 6 个跨群开关：_conf_schema.json 默认值 + cross_session_config helper
# ===========================================================================


def test_conf_schema_has_six_cross_session_keys_all_conservative_default():
    schema = json.loads((_REPO_ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
    assert schema["sylanne_alpha_cross_session_mode"]["default"] == "off"
    assert schema["sylanne_alpha_cross_session_mode"]["options"] == ["off", "shadow", "on"]
    assert schema["sylanne_alpha_cross_session_scope"]["default"] == "owner"
    assert schema["sylanne_alpha_cross_session_scope"]["options"] == ["owner", "all"]
    assert schema["sylanne_alpha_cross_dialogue"]["default"] is False
    assert schema["sylanne_alpha_cross_relationship"]["default"] is False
    assert schema["sylanne_alpha_cross_personality"]["default"] is False
    assert schema["sylanne_alpha_cross_visibility_tier"]["default"] == "same_group"
    assert schema["sylanne_alpha_cross_visibility_tier"]["options"] == [
        "same_group", "cross_group", "strict",
    ]


def test_cross_session_settings_defaults_all_conservative():
    class _P:
        pass

    settings = cross_session_settings(_P())
    assert settings == CrossSessionSettings()
    assert settings.mode == "off"
    assert settings.scope == "owner"
    assert settings.cross_dialogue is False
    assert settings.cross_relationship is False
    assert settings.cross_personality is False
    assert settings.visibility_tier == "same_group"
    assert settings.enabled is False


def test_cross_session_settings_reads_real_plugin_cfg_helpers():
    class _P:
        def _cfg(self, key: str, default: str = "") -> str:
            vals = {
                "sylanne_alpha_cross_session_mode": "shadow",
                "sylanne_alpha_cross_visibility_tier": "strict",
            }
            return vals.get(key, default)

        def _cfg_bool(self, key: str, default: bool = False) -> bool:
            return True if key == "sylanne_alpha_cross_dialogue" else default

    settings = cross_session_settings(_P())
    assert settings.mode == "shadow"
    assert settings.visibility_tier == "strict"
    assert settings.cross_dialogue is True
    assert settings.cross_relationship is False
    assert settings.enabled is True


def test_cross_session_settings_fail_closed_on_illegal_enum_value():
    class _P:
        def _cfg(self, key: str, default: str = "") -> str:
            return "bogus_mode" if key == "sylanne_alpha_cross_session_mode" else default

        def _cfg_bool(self, key: str, default: bool = False) -> bool:
            return default

    settings = cross_session_settings(_P())
    assert settings.mode == "off"  # 非法枚举值 fail-closed 回退默认（最保守）


def test_cross_session_settings_missing_cfg_helpers_falls_back_to_defaults():
    """插件对象缺 _cfg/_cfg_bool（异常构造）时同样回退全默认（= 全关）。"""
    settings = cross_session_settings(object())
    assert settings == CrossSessionSettings()


# ===========================================================================
# MEMORY_KV_KEYS_MANIFEST 一致性（golden 测试同款断言）
# ===========================================================================


def test_manifest_registers_person_shelf_and_profile_keys():
    assert "person_shelf" in MEMORY_KV_KEYS_MANIFEST
    assert "person_profile" in MEMORY_KV_KEYS_MANIFEST


def test_manifest_person_shelf_key_matches_generator():
    tmpl = MEMORY_KV_KEYS_MANIFEST["person_shelf"]
    assert tmpl.format(platform="qq", sender_id="u1") == person_shelf_kv_key("qq", "u1")


def test_manifest_person_profile_key_matches_generator():
    tmpl = MEMORY_KV_KEYS_MANIFEST["person_profile"]
    assert tmpl.format(platform="qq", sender_id="u1") == person_profile_kv_key("qq", "u1")
