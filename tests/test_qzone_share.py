"""PR-Qzone：QQ 空间说说功能测试。

覆盖（设计存档 qzone_design.txt + 落地设计 5 大要点）：
  - 默认关零动作（qzone_enabled=False 全程 no-op，不调 LLM、不记候选）
  - 素材白名单：她的生活/经历/关系记忆 YES；person_shelf 语义(user_explicit)/
    open/internal/user_fact NO
  - 广播净化闸 qzone_broadcast_gate：拦第三方样例(已知 sender_id/昵称)、PII、
    群聊哨兵、名单缺失 fail-closed；干净草稿放行
  - owner 显式指令过目门（说说确认/说说取消）：非 owner 拒、空 sender_id 拒、
    超时静默丢弃、is_romantic 会话门控
  - g_tk 本地算法正确（DJB2 变种，纯本地手算校验，不依赖实现自证）
  - cookie 失效/缺失不自动抓取，只返回失败原因
  - 频率闸在 LLM 调用之前拦截（省 token）
  - 一键关（confirm 时安全兜底）

绝不真发帖：HTTP 全程走本文件内的假 aiohttp session（_FakeSession），
从不构造真实网络连接；cookie 均为假串，不使用/不需要任何真凭据。
事件均生产形态（只暴露 get_sender_id()，无裸 sender_id/user_id 属性）。

直调真函数（qzone_share.py 模块级函数），不 mock 被测逻辑本身。
"""

from __future__ import annotations

import asyncio
import time

from sylanne_alpha import qzone_share as QZ
from sylanne_alpha.life_simulation import LifeEvent, LifePrivacy, LifeSource, ShareIntent
from sylanne_alpha.memory_system import MemoryItem


# ---------------------------------------------------------------------------
# 通用测试替身（镜像 test_relationship_layer_prh.py / test_lifesim_routing_pri.py）
# ---------------------------------------------------------------------------


class _BoundedDictDouble:
    """极简 BoundedDict 替身：仅 qzone_share 用到的 get/set/has/pop 接口。"""

    def __init__(self):
        self._d: dict = {}

    def get(self, k, default=None):
        return self._d.get(k, default)

    def set(self, k, v):
        self._d[k] = v

    def has(self, k):
        return k in self._d

    def pop(self, k, default=None):
        return self._d.pop(k, default)


class _Reg:
    def __init__(self, d=None):
        self._d = dict(d or {})

    def get(self, k, default=None):
        return self._d.get(k, default)

    def set(self, k, v):
        self._d[k] = v


class _Store:
    def __init__(self):
        self.pending_qzone_draft = _BoundedDictDouble()
        self.relationship_register_state = _Reg()
        self.intimacy_override = _Reg()


class _SocialField:
    """known_other_sender_ids 替身：可控返回集合或抛错（模拟取不到名单）。"""

    def __init__(self, ids=None, raise_exc=None):
        self._ids = set(ids or [])
        self._raise = raise_exc

    def known_other_sender_ids(self):
        if self._raise is not None:
            raise self._raise
        return set(self._ids)


class _Pipeline:
    """_llm_request_pipeline 替身：只提供 qzone_share 用到的三个接口。"""

    def __init__(self, *, draft="今天天气不错，心情也跟着好了呀", target_session="priv:owner-1"):
        self.draft = draft
        self.target_session = target_session
        self.llm_calls: list[dict] = []

    async def _generic_llm_call(self, prompt, provider_config_keys, max_tokens=None,
                                 temperature=0.0, retries=1):
        self.llm_calls.append({
            "prompt": prompt, "provider_config_keys": list(provider_config_keys),
        })
        return self.draft

    def _most_recent_intimate_host_key(self):
        return self.target_session

    def _life_sim_persona_getter(self):
        return "一个虚构角色"


class _FakeCtx:
    """async context manager 替身：模拟 `async with session.post(...) as resp:`。"""

    def __init__(self, text, exc=None):
        self._text = text
        self._exc = exc

    async def __aenter__(self):
        if self._exc is not None:
            raise self._exc
        return self

    async def __aexit__(self, *_a):
        return False

    async def text(self):
        return self._text


class _FakeSession:
    """假 aiohttp ClientSession：只记录调用，绝不发真实网络请求。"""

    def __init__(self, response_text='_callback({"code":0,"tid":"abc123"})', raise_exc=None):
        self.calls: list[dict] = []
        self._response_text = response_text
        self._raise = raise_exc

    def post(self, url, headers=None, data=None, timeout=None):
        self.calls.append({"url": url, "headers": dict(headers or {}), "data": dict(data or {})})
        return _FakeCtx(self._response_text, self._raise)


class _MemSystemDouble:
    """MemorySystem 替身：只暴露 _l1/_l2（qzone_share._collect_memory_material
    只读遍历这两个属性，不调用 recall()）。"""

    def __init__(self, l1=None, l2=None):
        self._l1 = list(l1 or [])
        self._l2 = list(l2 or [])


class _Plugin:
    def __init__(self, *, owner="owner-1", enabled=True, cookie="p_skey=fakeskey123;uin=o123",
                 my_qq="123456", daily_max=1, weekly_max=3, min_score=0.55,
                 pipeline=None, social_field=None, http_session="default",
                 memory_system=None):
        self._store = _Store()
        self.config = {
            "sylanne_alpha_owner_id": owner,
            "sylanne_alpha_qzone_enabled": enabled,
            "sylanne_alpha_qzone_cookie": cookie,
            "sylanne_alpha_qzone_my_qq": my_qq,
            "sylanne_alpha_qzone_daily_max": daily_max,
            "sylanne_alpha_qzone_weekly_max": weekly_max,
            "sylanne_alpha_qzone_min_score": min_score,
        }
        self._llm_request_pipeline = pipeline if pipeline is not None else _Pipeline()
        self._social_field = social_field if social_field is not None else _SocialField()
        self._qzone_http_session = _FakeSession() if http_session == "default" else http_session
        self._qzone_audit = None
        self._qzone_audit_saves: list[dict] = []
        self._memory_system = memory_system

    def _memory_system_for_session(self, session_key):
        return self._memory_system

    def _session_key(self, event=None, session_key=""):
        return getattr(event, "_sk", "") or session_key

    async def _qzone_audit_throttled_save(self):
        audit = getattr(self, "_qzone_audit", None)
        if audit is not None:
            self._qzone_audit_saves.append(audit.to_dict())


class _Ev:
    """生产形态事件替身：无裸 sender_id/user_id 属性，只暴露 get_sender_id()。"""

    def __init__(self, sender_id="", sk="priv:owner-1"):
        self._sender_id = sender_id
        self._sk = sk

    def get_sender_id(self):
        return self._sender_id


def _run(coro):
    return asyncio.run(coro)


def _drain(gen):
    out = []

    async def _c():
        async for x in gen:
            out.append(x)

    asyncio.run(_c())
    return out


def _romantic(sender="owner-1"):
    return {"sender_id": sender, "romantic_conf": 0.8, "sample_count": 8}


def _life_event(**kwargs) -> LifeEvent:
    defaults = dict(
        text="今天读了本喜欢的小说",
        mood="平静",
        urgency=0.2,
        timestamp=time.time(),
        wants_to_share=True,
        privacy_level=LifePrivacy.SHAREABLE,
        source=LifeSource.PLANNED_TICK,
    )
    defaults.update(kwargs)
    return LifeEvent(**defaults)


def _intent(score=0.7) -> ShareIntent:
    return ShareIntent(final_score=score)


# ---------------------------------------------------------------------------
# 素材白名单
# ---------------------------------------------------------------------------


def test_life_event_eligible_shareable_planned_tick():
    ev = _life_event(privacy_level=LifePrivacy.SHAREABLE, source=LifeSource.PLANNED_TICK)
    assert QZ.life_event_eligible(ev) is True


def test_life_event_eligible_reflection_and_consolidation():
    assert QZ.life_event_eligible(
        _life_event(privacy_level=LifePrivacy.SHAREABLE, source=LifeSource.REFLECTION)
    ) is True
    assert QZ.life_event_eligible(
        _life_event(privacy_level=LifePrivacy.SHAREABLE, source=LifeSource.CONSOLIDATION)
    ) is True


def test_life_event_ineligible_user_interaction_source():
    """USER_INTERACTION 可能含用户/他人内容，比设计稿更收紧一档排除。"""
    ev = _life_event(privacy_level=LifePrivacy.SHAREABLE, source=LifeSource.USER_INTERACTION)
    assert QZ.life_event_eligible(ev) is False


def test_life_event_ineligible_legacy_source():
    ev = _life_event(privacy_level=LifePrivacy.SHAREABLE, source=LifeSource.LEGACY)
    assert QZ.life_event_eligible(ev) is False


def test_life_event_ineligible_internal_privacy():
    ev = _life_event(privacy_level=LifePrivacy.INTERNAL, source=LifeSource.PLANNED_TICK)
    assert QZ.life_event_eligible(ev) is False


def test_memory_item_eligible_her_experience_yes():
    assert QZ.memory_item_eligible("life_sim", "shareable") is True
    assert QZ.memory_item_eligible("life_reflection", "shareable") is True


def test_memory_item_ineligible_user_explicit():
    """user_explicit 常携第三方 PII/用户事实，不进候选（person_shelf 语义排除）。"""
    assert QZ.memory_item_eligible("user_explicit", "shareable") is False


def test_memory_item_ineligible_non_shareable_privacy():
    for privacy in ("open", "internal", "user_fact"):
        assert QZ.memory_item_eligible("life_sim", privacy) is False


def test_relationship_memory_eligible_requires_shareable():
    assert QZ.relationship_memory_eligible("shareable") is True
    assert QZ.relationship_memory_eligible("open") is False
    assert QZ.relationship_memory_eligible("user_fact") is False


def test_filter_memory_candidates_mixed_list():
    items = [
        {"source": "life_sim", "privacy_level": "shareable", "text": "her own day"},
        {"source": "user_explicit", "privacy_level": "shareable", "text": "third party fact"},
        {"source": "life_sim", "privacy_level": "internal", "text": "private thought"},
    ]

    class _Obj:
        def __init__(self, source, privacy_level):
            self.source = source
            self.privacy_level = privacy_level

    items.append(_Obj("life_reflection", "shareable"))
    out = QZ.filter_memory_candidates(items)
    assert len(out) == 2
    assert out[0]["text"] == "her own day"
    assert isinstance(out[1], _Obj)


def _mem_item(text, source, privacy_level, item_id="m1"):
    return MemoryItem(
        id=item_id, text=text, weight=0.8, temperature=0.2, age_ticks=0,
        embedding=None, created_at=time.time(), source=source, privacy_level=privacy_level,
    )


# ---------------------------------------------------------------------------
# 路径B：她的经历/心情记忆素材（不改 recall 签名，只读 _l1/_l2 后置过滤）
# ---------------------------------------------------------------------------


def test_collect_memory_material_filters_eligible_only():
    mem = _MemSystemDouble(
        l1=[
            _mem_item("她自己散步时的心情", "life_sim", "shareable", "m1"),
            _mem_item("用户告诉她的第三方隐私事实", "user_explicit", "shareable", "m2"),
        ],
        l2=[
            _mem_item("她夜里反思的一段心情", "life_reflection", "shareable", "m3"),
            _mem_item("私密的内心独白", "life_sim", "internal", "m4"),
        ],
    )
    plugin = _Plugin(memory_system=mem)
    snippets = QZ._collect_memory_material(plugin, "priv:owner-1")
    assert "用户告诉她的第三方隐私事实" not in snippets
    assert "私密的内心独白" not in snippets
    assert any("她自己散步时的心情" in s for s in snippets)
    assert any("她夜里反思的一段心情" in s for s in snippets)


def test_collect_memory_material_no_memory_system_returns_empty():
    plugin = _Plugin(memory_system=None)
    assert QZ._collect_memory_material(plugin, "priv:owner-1") == []


def test_collect_memory_material_missing_getter_returns_empty():
    class _NoGetterPlugin:
        pass

    assert QZ._collect_memory_material(_NoGetterPlugin(), "priv:owner-1") == []


def test_generate_draft_includes_eligible_memory_snippets_in_prompt():
    pipeline = _Pipeline(draft="今天心情不错")
    plugin = _Plugin(pipeline=pipeline, memory_system=_MemSystemDouble(
        l1=[_mem_item("她自己读书时的感想", "life_sim", "shareable", "m1")],
    ))
    event = _life_event()
    snippets = QZ._collect_memory_material(plugin, "priv:owner-1")
    _run(QZ._generate_draft(plugin, event, snippets))
    assert len(pipeline.llm_calls) == 1
    assert "她自己读书时的感想" in pipeline.llm_calls[0]["prompt"]


def test_candidate_happy_path_pulls_in_memory_material():
    """完整链路：候选处理时应把 best_key 对应会话的路径B素材喂进草稿 prompt。"""
    pipeline = _Pipeline(draft="今天读了本喜欢的小说，心情很平静。", target_session="priv:owner-1")
    mem = _MemSystemDouble(l1=[_mem_item("她自己上周散步时想到的事", "life_sim", "shareable", "m1")])
    plugin = _Plugin(pipeline=pipeline, memory_system=mem, enabled=True)
    event = _life_event()

    _run(QZ.handle_share_intent_candidate(plugin, event, _intent(0.9)))

    assert len(pipeline.llm_calls) == 1
    assert "她自己上周散步时想到的事" in pipeline.llm_calls[0]["prompt"]


# ---------------------------------------------------------------------------
# 广播净化闸 qzone_broadcast_gate
# ---------------------------------------------------------------------------


def test_gate_rejects_when_roster_unavailable():
    ok, reason = QZ.qzone_broadcast_gate("今天心情不错", known_other_names=None, known_other_sender_ids=set())
    assert ok is False
    assert reason == "no_roster_failclosed"
    ok2, reason2 = QZ.qzone_broadcast_gate("今天心情不错", known_other_names=set(), known_other_sender_ids=None)
    assert ok2 is False
    assert reason2 == "no_roster_failclosed"


def test_gate_rejects_known_other_name_third_party_sample():
    """张三离婚金样：草稿提到已知第三方昵称即拒。

    注意：本用例【手动注入】known_other_names={"张三"}，验证的是 gate 姓名子串
    通道的【逻辑正确性】——为将来若接上真实花名册预留。它【不代表生产行为】：
    生产上 _collect_known_others 恒返空名单（本仓库无花名册基建），该通道空转，
    见下方 test_gate_bare_third_party_name_passes_with_real_empty_roster。
    """
    draft = "张三今天离婚了，分了一大笔赡养金，好八卦"
    ok, reason = QZ.qzone_broadcast_gate(
        draft, known_other_names={"张三"}, known_other_sender_ids=set()
    )
    assert ok is False
    assert reason == "hit_known_other"


def test_gate_bare_third_party_name_passes_with_real_empty_roster():
    """诚实锁定生产真相：真实(空)花名册下,只以【裸姓名】提第三方、且不含
    数字/PII/群聊哨兵的草稿会【通过】广播闸——gate 逮不住散文体裸姓名。
    对这种泄露的真正防线是【来源白名单 + owner 人工过目】,不是本 gate。
    这条把 test_gate_rejects_known_other_name_third_party_sample 的手注名单
    可能造成的"gate 能拦裸姓名"假象显式钉死,防回归时误判 gate 是背板。
    """
    draft = "张三今天离婚了，分了一大笔赡养金，好八卦"
    # 生产口径：known_other_names 恒为空集合（_collect_known_others 真实返回）
    ok, reason = QZ.qzone_broadcast_gate(
        draft, known_other_names=set(), known_other_sender_ids=set()
    )
    assert ok is True  # gate 放行——这正是为什么来源白名单 + owner 过目才是背板
    assert reason == "ok"


def test_gate_rejects_known_other_sender_id_substring():
    draft = "今天和 10086 那位聊了好久"
    ok, reason = QZ.qzone_broadcast_gate(
        draft, known_other_names=set(), known_other_sender_ids={"10086"}
    )
    assert ok is False
    assert reason == "hit_known_other"


def test_gate_rejects_pii_phone():
    draft = "手机号是13800138000，随便写写"
    ok, reason = QZ.qzone_broadcast_gate(draft, known_other_names=set(), known_other_sender_ids=set())
    assert ok is False
    assert reason == "hit_pii"


def test_gate_rejects_pii_address_and_org():
    ok1, r1 = QZ.qzone_broadcast_gate(
        "住在幸福小区3号楼", known_other_names=set(), known_other_sender_ids=set()
    )
    assert (ok1, r1) == (False, "hit_pii")
    ok2, r2 = QZ.qzone_broadcast_gate(
        "在某某大学读书", known_other_names=set(), known_other_sender_ids=set()
    )
    assert (ok2, r2) == (False, "hit_pii")


def test_gate_rejects_group_sentinel():
    draft = "[群聊背景|某人]: 大家在聊什么"
    ok, reason = QZ.qzone_broadcast_gate(draft, known_other_names=set(), known_other_sender_ids=set())
    assert ok is False
    assert reason == "hit_group_sentinel"


def test_gate_rejects_empty_draft():
    ok, reason = QZ.qzone_broadcast_gate("   ", known_other_names=set(), known_other_sender_ids=set())
    assert ok is False
    assert reason == "empty_draft"


def test_gate_rejects_overlong_draft():
    draft = "今天" * 300
    ok, reason = QZ.qzone_broadcast_gate(draft, known_other_names=set(), known_other_sender_ids=set())
    assert ok is False
    assert reason == "hit_length"


def test_gate_allows_clean_draft():
    draft = "今天读了本喜欢的小说，心情很平静，也想起了和你的约定。"
    ok, reason = QZ.qzone_broadcast_gate(draft, known_other_names=set(), known_other_sender_ids=set())
    assert (ok, reason) == (True, "ok")


# ---------------------------------------------------------------------------
# g_tk 本地算法（DJB2 变种）—— 独立手算校验，不依赖实现自证
# ---------------------------------------------------------------------------


def test_g_tk_known_value_single_char():
    # hash=5381; hash += (5381<<5) + ord('a')(97) = 5381 + 172192 + 97 = 177670
    assert QZ.compute_g_tk("a") == 177670


def test_g_tk_empty_string_is_seed():
    assert QZ.compute_g_tk("") == 5381


def test_g_tk_matches_manual_djb2_variant():
    p_skey = "Abc9Z"
    h = 5381
    for ch in p_skey:
        h += (h << 5) + ord(ch)
    expected = h & 0x7FFFFFFF
    assert QZ.compute_g_tk(p_skey) == expected


def test_extract_p_skey_from_cookie():
    cookie = "uin=o123456; skey=@xyz; p_skey=abcDEF123; other=1"
    assert QZ.extract_p_skey(cookie) == "abcDEF123"


def test_extract_p_skey_missing_returns_empty():
    assert QZ.extract_p_skey("uin=o123456; skey=@xyz") == ""


# ---------------------------------------------------------------------------
# 发布 HTTP（假 session，绝不真发帖）+ cookie 失效不自动抓取
# ---------------------------------------------------------------------------


def test_publish_success_parses_jsonp():
    session = _FakeSession(response_text='_Callback({"code":0,"tid":"t123"});')
    ok, msg = _run(QZ.publish_qzone_post(session, cookie="p_skey=abc", my_qq="123", text="hi"))
    assert ok is True
    assert msg == "t123"
    assert len(session.calls) == 1
    assert "g_tk=" in session.calls[0]["url"]
    assert session.calls[0]["headers"]["cookie"] == "p_skey=abc"


def test_publish_failure_code_nonzero():
    session = _FakeSession(response_text='_Callback({"code":-3000,"message":"risk control"});')
    ok, msg = _run(QZ.publish_qzone_post(session, cookie="p_skey=abc", my_qq="123", text="hi"))
    assert ok is False
    assert "risk control" in msg


def test_publish_missing_cookie_p_skey_fails_without_network_call():
    session = _FakeSession()
    ok, msg = _run(QZ.publish_qzone_post(session, cookie="uin=123", my_qq="123", text="hi"))
    assert ok is False
    assert msg == "cookie_missing_p_skey"
    assert session.calls == []  # 没有 p_skey 直接失败，不发起 HTTP


def test_publish_http_error_does_not_raise():
    session = _FakeSession(raise_exc=ConnectionError("boom"))
    ok, msg = _run(QZ.publish_qzone_post(session, cookie="p_skey=abc", my_qq="123", text="hi"))
    assert ok is False
    assert msg.startswith("http_error:")


def test_no_automatic_cookie_fetching_in_module():
    """模块源码里不得出现任何 get_cookies(...) / call_action(...) 之类的凭据自动
    获取调用点（docstring 里提及"不要做什么"允许出现裸词，但不能出现实际调用）。"""
    import inspect

    src = inspect.getsource(QZ)
    assert "get_cookies(" not in src
    assert "call_action(" not in src
    assert ".bot.api" not in src


def test_do_publish_missing_credentials_returns_failure():
    plugin = _Plugin(cookie="", my_qq="")
    ok, msg = _run(QZ._do_publish(plugin, "hi"))
    assert ok is False
    assert msg == "credentials_missing"


# ---------------------------------------------------------------------------
# 频率闸（daily/weekly，草稿 LLM 调用之前拦截）
# ---------------------------------------------------------------------------


def test_frequency_gate_blocks_when_daily_cap_hit():
    state = QZ.QzoneAuditState()
    now = time.time()
    state.record_post(now)
    ok, reason = QZ.frequency_gate_ok(state, now, daily_max=1, weekly_max=3)
    assert ok is False
    assert reason == "freq_daily"


def test_frequency_gate_blocks_when_weekly_cap_hit():
    state = QZ.QzoneAuditState()
    now = time.time()
    for _ in range(3):
        state.record_post(now)
    ok, reason = QZ.frequency_gate_ok(state, now, daily_max=10, weekly_max=3)
    assert ok is False
    assert reason == "freq_weekly"


def test_frequency_gate_zero_cap_means_closed_not_unlimited():
    state = QZ.QzoneAuditState()
    ok, reason = QZ.frequency_gate_ok(state, time.time(), daily_max=0, weekly_max=3)
    assert ok is False
    assert reason == "freq_cap_zero"


def test_frequency_gate_ok_under_cap():
    state = QZ.QzoneAuditState()
    ok, reason = QZ.frequency_gate_ok(state, time.time(), daily_max=1, weekly_max=3)
    assert (ok, reason) == (True, "ok")


def test_handle_candidate_frequency_gate_blocks_before_llm_call():
    """频率闸必须在 LLM 调用之前拦——命中即整体不调 draft 生成。"""
    pipeline = _Pipeline()
    plugin = _Plugin(pipeline=pipeline, daily_max=1)
    plugin._qzone_audit = QZ.QzoneAuditState()
    plugin._qzone_audit.record_post(time.time())  # 已用满当日额度

    event = _life_event()
    _run(QZ.handle_share_intent_candidate(plugin, event, _intent(0.9)))

    assert pipeline.llm_calls == []  # 没有调用 LLM
    log_reasons = [e["reason_code"] for e in plugin._qzone_audit.log]
    assert any(r.startswith("rejected_freq") for r in log_reasons)


# ---------------------------------------------------------------------------
# 默认关零动作
# ---------------------------------------------------------------------------


def test_disabled_candidate_is_full_noop():
    pipeline = _Pipeline()
    plugin = _Plugin(pipeline=pipeline, enabled=False)
    event = _life_event()
    _run(QZ.handle_share_intent_candidate(plugin, event, _intent(0.99)))

    assert pipeline.llm_calls == []
    assert plugin._qzone_audit is None  # 完全没触碰审计状态
    assert plugin._store.pending_qzone_draft.get("priv:owner-1") is None


def test_candidate_none_intent_is_noop():
    pipeline = _Pipeline()
    plugin = _Plugin(pipeline=pipeline, enabled=True)
    event = _life_event()
    _run(QZ.handle_share_intent_candidate(plugin, event, None))
    assert pipeline.llm_calls == []


# ---------------------------------------------------------------------------
# 候选完整链路：过闸 → 入队 owner 过目
# ---------------------------------------------------------------------------


def test_candidate_happy_path_queues_pending_confirmation():
    pipeline = _Pipeline(draft="今天读了本喜欢的小说，心情很平静。", target_session="priv:owner-1")
    plugin = _Plugin(pipeline=pipeline, enabled=True)
    event = _life_event()

    _run(QZ.handle_share_intent_candidate(plugin, event, _intent(0.9)))

    assert len(pipeline.llm_calls) == 1
    pending = plugin._store.pending_qzone_draft.get("priv:owner-1")
    assert pending is not None
    assert pending["draft"] == "今天读了本喜欢的小说，心情很平静。"
    reasons = [e["reason_code"] for e in plugin._qzone_audit.log]
    assert QZ.REASON_AWAITING_CONFIRM in reasons


def test_candidate_rejected_by_gate_never_queues():
    """草稿命中第三方名单时，即便过了频率闸也绝不进入 owner 过目队列。"""
    pipeline = _Pipeline(draft="张三今天又请假了，真是的", target_session="priv:owner-1")
    social_field = _SocialField(ids={"张三"})
    plugin = _Plugin(pipeline=pipeline, social_field=social_field, enabled=True)
    event = _life_event()

    _run(QZ.handle_share_intent_candidate(plugin, event, _intent(0.9)))

    assert plugin._store.pending_qzone_draft.get("priv:owner-1") is None
    reasons = [e["reason_code"] for e in plugin._qzone_audit.log]
    assert any(r.startswith(QZ.REASON_REJECTED_GATE) for r in reasons)


def test_collect_known_others_failclosed_on_social_field_error():
    plugin = _Plugin(social_field=_SocialField(raise_exc=RuntimeError("boom")))
    names, ids = QZ._collect_known_others(plugin)
    assert names is None
    assert ids is None


def test_collect_known_others_excludes_owner_id():
    plugin = _Plugin(owner="owner-1", social_field=_SocialField(ids={"owner-1", "other-2"}))
    _names, ids = QZ._collect_known_others(plugin)
    assert ids == {"other-2"}


# ---------------------------------------------------------------------------
# owner 显式指令过目门：说说草稿 / 说说确认 / 说说取消
# ---------------------------------------------------------------------------


def _seed_pending(plugin, *, session_key="priv:owner-1", draft="待确认的草稿", expires_in=1800.0):
    now = time.time()
    plugin._store.pending_qzone_draft.set(session_key, {
        "kind": "qzone_draft", "draft": draft, "event_id": "e1", "intent_id": "i1",
        "queued_at": now, "expires_at": now + expires_in,
    })
    plugin._store.relationship_register_state.set(session_key, _romantic("owner-1"))


def test_confirm_rejects_nonowner_production_shaped_event():
    plugin = _Plugin(owner="owner-1")
    _seed_pending(plugin)
    out = _drain(QZ.confirm_command(plugin, _Ev(sender_id="attacker-9", sk="priv:owner-1")))
    assert any("不是我对象" in t for t in out)
    # 草稿仍在，没被消费
    assert plugin._store.pending_qzone_draft.get("priv:owner-1") is not None


def test_confirm_rejects_empty_sender_id_failclosed():
    plugin = _Plugin(owner="owner-1")
    _seed_pending(plugin)
    out = _drain(QZ.confirm_command(plugin, _Ev(sender_id="", sk="priv:owner-1")))
    assert any("没认出你是谁" in t for t in out)
    assert plugin._store.pending_qzone_draft.get("priv:owner-1") is not None


def test_confirm_rejects_when_owner_unset():
    plugin = _Plugin(owner="")
    _seed_pending(plugin)
    out = _drain(QZ.confirm_command(plugin, _Ev(sender_id="whoever", sk="priv:owner-1")))
    assert any("主人身份" in t for t in out)


def test_confirm_rejects_non_romantic_session():
    """双门②：is_romantic 再校验一次，即便 sender_id 正确，会话非亲密也拒。"""
    plugin = _Plugin(owner="owner-1")
    now = time.time()
    plugin._store.pending_qzone_draft.set("priv:owner-1", {
        "kind": "qzone_draft", "draft": "草稿", "event_id": "e1", "intent_id": "i1",
        "queued_at": now, "expires_at": now + 1800.0,
    })
    # 故意不设置 relationship_register_state → is_romantic 为 False
    out = _drain(QZ.confirm_command(plugin, _Ev(sender_id="owner-1", sk="priv:owner-1")))
    assert any("这窗口不算数" in t for t in out)
    assert plugin._store.pending_qzone_draft.get("priv:owner-1") is not None


def test_confirm_owner_happy_path_posts_and_clears_pending():
    session = _FakeSession(response_text='_cb({"code":0,"tid":"tid-1"})')
    plugin = _Plugin(owner="owner-1", http_session=session)
    _seed_pending(plugin, draft="今天心情不错")
    out = _drain(QZ.confirm_command(plugin, _Ev(sender_id="owner-1", sk="priv:owner-1")))
    assert any("发出去啦" in t for t in out)
    assert plugin._store.pending_qzone_draft.get("priv:owner-1") is None
    assert len(session.calls) == 1
    assert plugin._qzone_audit.daily_count(time.time()) == 1


def test_cancel_owner_happy_path_never_posts():
    session = _FakeSession()
    plugin = _Plugin(owner="owner-1", http_session=session)
    _seed_pending(plugin, draft="不想发的草稿")
    out = _drain(QZ.cancel_command(plugin, _Ev(sender_id="owner-1", sk="priv:owner-1")))
    assert any("不发了" in t for t in out)
    assert plugin._store.pending_qzone_draft.get("priv:owner-1") is None
    assert session.calls == []  # 取消绝不触发任何网络请求


def test_confirm_expired_pending_dropped_silently_no_post():
    session = _FakeSession()
    plugin = _Plugin(owner="owner-1", http_session=session)
    _seed_pending(plugin, expires_in=-10.0)  # 已过期
    out = _drain(QZ.confirm_command(plugin, _Ev(sender_id="owner-1", sk="priv:owner-1")))
    assert any("超时" in t for t in out)
    assert plugin._store.pending_qzone_draft.get("priv:owner-1") is None
    assert session.calls == []


def test_confirm_no_pending_draft_tells_user():
    plugin = _Plugin(owner="owner-1")
    plugin._store.relationship_register_state.set("priv:owner-1", _romantic("owner-1"))
    out = _drain(QZ.confirm_command(plugin, _Ev(sender_id="owner-1", sk="priv:owner-1")))
    assert any("没有等着确认" in t for t in out)


def test_status_command_shows_pending_draft():
    plugin = _Plugin(owner="owner-1")
    _seed_pending(plugin, draft="今天心情不错")
    out = _drain(QZ.status_command(plugin, _Ev(sender_id="owner-1", sk="priv:owner-1")))
    assert any("今天心情不错" in t for t in out)


# ---------------------------------------------------------------------------
# 一键关：确认时的安全兜底（即便 pending 还在，disabled 时绝不真发）
# ---------------------------------------------------------------------------


def test_confirm_refuses_to_post_when_disabled_even_with_pending():
    session = _FakeSession()
    plugin = _Plugin(owner="owner-1", enabled=False, http_session=session)
    _seed_pending(plugin, draft="关着的时候不该发出去")
    out = _drain(QZ.confirm_command(plugin, _Ev(sender_id="owner-1", sk="priv:owner-1")))
    assert any("关着的" in t for t in out)
    assert session.calls == []  # 一次网络请求都没有
    assert plugin._store.pending_qzone_draft.get("priv:owner-1") is None  # 已被消费，不会残留手滑二次确认
