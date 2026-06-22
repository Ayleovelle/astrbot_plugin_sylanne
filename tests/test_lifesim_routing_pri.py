"""Phase 2B / PR-I：life-sim 路由（origin_session 迁移 + 亲密私聊单目标 + 群排除）测试。

覆盖 handoff §5.3：
- LifeEvent.origin_session roundtrip（_event_from_dict/_event_to_dict；旧档缺→""）
- _most_recent_intimate_host_key：排除群、仅亲密、无则 ""
- 群/陌生人不被选；共享 _most_recent_host_key 行为不变

直调真函数。
"""

from __future__ import annotations

from sylanne_alpha.life_simulation import LifeEvent, _event_from_dict, _event_to_dict
from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline


# ---- origin_session roundtrip ----

def test_origin_session_roundtrip():
    e = LifeEvent(text="t", mood="m", urgency=0.1, timestamp=1.0, origin_session="s1")
    assert _event_from_dict(_event_to_dict(e)).origin_session == "s1"


def test_origin_session_legacy_missing_defaults_empty():
    legacy = {"text": "t", "mood": "m", "urgency": 0.1, "timestamp": 1.0}
    assert _event_from_dict(legacy).origin_session == ""


# ---- _most_recent_intimate_host_key ----

class _Kernel:
    def __init__(self, now):
        self.last_event = {"now": now}


class _Host:
    def __init__(self, now):
        self.kernel = _Kernel(now)


class _Reg:
    def __init__(self):
        self._d = {}

    def get(self, k, default=None):
        return self._d.get(k, default)

    def set(self, k, v):
        self._d[k] = v


class _Hosts:
    def __init__(self, d):
        self._d = d

    def items(self):
        return self._d.items()

    def keys(self):
        return self._d.keys()

    def __len__(self):
        return len(self._d)


class _SF:
    def is_group_context_by_key(self, sk):
        return "Group" in sk or "group" in sk


class _Store:
    def __init__(self, hosts):
        self.hosts = _Hosts(hosts)
        self.relationship_register_state = _Reg()
        self.intimacy_override = _Reg()


class _Plugin:
    def __init__(self, hosts, owner="owner-1"):
        self._store = _Store(hosts)
        self._social_field = _SF()
        self.config = {"sylanne_alpha_owner_id": owner}

    def _session_key(self, event=None, session_key=""):
        return session_key


def _pipe(plugin):
    pipe = LLMRequestPipeline.__new__(LLMRequestPipeline)
    pipe._p = plugin
    return pipe


def _romantic(sender="owner-1"):
    return {"sender_id": sender, "romantic_conf": 0.8, "sample_count": 8}


def test_intimate_helper_picks_romantic_private():
    p = _Plugin({"priv:owner-1": _Host(100.0)})
    p._store.relationship_register_state.set("priv:owner-1", _romantic())
    assert _pipe(p)._most_recent_intimate_host_key() == "priv:owner-1"


def test_intimate_helper_excludes_group():
    p = _Plugin({"GroupMessage:g1:owner-1": _Host(200.0)})
    # 即便该群会话 register 是 romantic，群也不投
    p._store.relationship_register_state.set("GroupMessage:g1:owner-1", _romantic())
    assert _pipe(p)._most_recent_intimate_host_key() == ""


def test_intimate_helper_excludes_nonowner():
    p = _Plugin({"priv:attacker": _Host(100.0)})
    p._store.relationship_register_state.set("priv:attacker", _romantic("attacker"))
    assert _pipe(p)._most_recent_intimate_host_key() == ""


def test_intimate_helper_empty_when_none():
    p = _Plugin({"priv:owner-1": _Host(100.0)})  # 无 register → 非亲密
    assert _pipe(p)._most_recent_intimate_host_key() == ""


def test_shared_host_key_unchanged_picks_last_active():
    """共享 _most_recent_host_key 行为不变：选最近活跃，不管亲密/群。"""
    p = _Plugin({"a": _Host(50.0), "GroupMessage:g:x": _Host(300.0)})
    assert _pipe(p)._most_recent_host_key() == "GroupMessage:g:x"
