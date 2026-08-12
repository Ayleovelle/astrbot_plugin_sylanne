"""Wave-L2/T2-05（她记得你要去面试）+ T2-06（晚安仪式感）测试。

T2-05 —— user_followup 跟进线索：
  ① memory_system.write_summary 命中承诺关键词 + 未来时间词时记一条待跟进线索
     （{topic_snippet, due_ts_estimate, session_key, created_ts}），cap 10。
  ② 到期后 ProactiveBridge.infer_reason_code 返回 'user_followup'（见
     test_proactive_bridge.py 的 TestInferReasonCode 补充用例）；winddown 抑制
     见 test_wave_l2_t2_01_t2_03_silence_winddown.py 的补充用例（consult_idle_reach
     不因跟进线索到期而多一条绕过路径）。
  ③ consume-on-mention：用户主动提起同一话题时静默消费。

T2-06 —— 晚安仪式感：
  ④ 早安/晚安关键词观察 → 已认证 RelationRuntime 的 RitualRegistry.observe_pattern。
     偏差：SDK assessor 的 greeting/farewell flag 在插件运行时路径不可达，改用关键词兜底
     （见 session_context._detect_greeting_ritual_pattern 的注释）。
  ④'：一旦自动注册（≥3 次观测），只向所属 exact ScopedSessionRuntime 的 scheduler
     注册 timing hint，
     使既有 reason_code='ritual' 缺席检测（check_ritual_absence）真正可达
     （此前 RitualRegistry 是孤岛，从无调用方把它接到调度器）。
  ⑤ RitualRegistry 随 RelationScope 的 ``ritual`` 组件 CAS 持久化并在重启后恢复，
     不使用插件全局 registry 或 KV 周期存档。
"""

from __future__ import annotations

import asyncio
import time
import types
from datetime import datetime, timedelta, timezone

import sylanne_alpha.memory_system as _memory_system_mod
import sylanne_alpha.proactive_scheduler as _sched_mod
from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline
from sylanne_alpha.memory_system import MemorySystem
from sylanne_alpha.proactive_bridge import ProactiveBridge
from sylanne_alpha.proactive_scheduler import ProactiveScheduler
from sylanne_alpha.scope_contracts import VerifiedSubjectInput
from sylanne_alpha.scope_identity import ScopeIdentityKey
from sylanne_alpha.scope_repository import ScopeRepository
from sylanne_alpha.scope_runtime import RitualRegistry, ScopeRuntimeRegistry
from sylanne_alpha.session_context import SessionContext
from sylanne_alpha.session_state_store import SessionStateStore
from tests.scope_fixtures import scopes


def _ts(y, mo, d, h, mi=0) -> float:
    return time.mktime(datetime(y, mo, d, h, mi, 0).timetuple())


# ===========================================================================
# T2-05①：承诺关键词 + 未来时间词 → 记一条待跟进线索
# ===========================================================================


class TestPendingFollowupCreation:
    def test_commitment_and_future_word_creates_thread(self):
        ms = MemorySystem()
        ms.write_summary("我答应你明天一定去面试", source_turns=2, temperature=0.5)
        assert len(ms._pending_followups) == 1
        entry = ms._pending_followups[0]
        assert "面试" in entry["topic_snippet"]
        assert entry["due_ts_estimate"] > time.time()
        assert entry["created_ts"] > 0.0

    def test_commitment_without_future_word_creates_nothing(self):
        """只有承诺关键词、没有时间点 → 不创建线索（避免"喜欢猫"这种也被当成待办）。"""
        ms = MemorySystem()
        ms.write_summary("我喜欢猫", source_turns=1, temperature=0.3)
        assert ms._pending_followups == []

    def test_future_word_without_commitment_creates_nothing(self):
        # 用"晚上"而非"明天"：后者本身也在 _COMMITMENT_KW 里，会与本用例的
        # "无承诺关键词"前提矛盾（两张表刻意有重叠词，见 memory_system.py 注释）。
        ms = MemorySystem()
        ms.write_summary("晚上天气应该不错", source_turns=1, temperature=0.0)
        assert ms._pending_followups == []

    def test_life_sim_source_excluded(self):
        """Sylanne 自己的生活模拟不算"用户的承诺"（同 ADR-002 精神），即使文本
        字面命中承诺+未来时间词也不该创建跟进线索。"""
        ms = MemorySystem()
        ms.write_summary(
            "我答应自己明天一定要早起", source_turns=1, temperature=0.3,
            source="life_sim", privacy_level="shareable",
        )
        assert ms._pending_followups == []

    def test_cap_evicts_oldest(self):
        """cap ~10，超出淘汰最旧。"""
        ms = MemorySystem()
        for i in range(13):
            ms.write_summary(f"我答应你明天第{i}件事一定做到", source_turns=1, temperature=0.0)
        assert len(ms._pending_followups) == 10
        # 最旧的（第0/1/2件）应已被淘汰，保留最新的
        snippets = " ".join(e["topic_snippet"] for e in ms._pending_followups)
        assert "第12件" in snippets
        assert "第0件" not in snippets

    def test_due_pending_followup_only_returns_after_due(self):
        ms = MemorySystem()
        ms.write_summary("我答应你明天一定去面试", source_turns=1, temperature=0.0)
        assert ms.due_pending_followup(now=time.time()) is None  # 还没到
        far_future = ms._pending_followups[0]["due_ts_estimate"] + 1.0
        due = ms.due_pending_followup(now=far_future)
        assert due is not None
        assert "面试" in due["topic_snippet"]

    def test_consume_pending_followup_removes_entry(self):
        ms = MemorySystem()
        ms.write_summary("我答应你明天一定去面试", source_turns=1, temperature=0.0)
        entry = ms._pending_followups[0]
        assert ms.consume_pending_followup(entry) is True
        assert ms._pending_followups == []
        # 二次消费同一条 → False（已经不在列表里）
        assert ms.consume_pending_followup(entry) is False


# ===========================================================================
# 时区回归：_estimate_due_ts 必须用中国时区（_CHINA_TZ）解读 now/构造 due_dt，
# 不能依赖 datetime.fromtimestamp(now) 隐式读取的宿主系统时区——否则 UTC 部署下
# "明天晚上"这类相对时段词会被整体算错（日期+8 小时都可能偏）。
# ===========================================================================


class TestEstimateDueTsChinaTimezone:
    def test_uses_china_tz_not_system_tz(self, monkeypatch) -> None:
        """Windows 无 time.tzset()，无法可移植地把真实系统时区改成非中国时区来验证。
        用一个模拟"宿主系统时区=UTC"的 datetime 桩替换模块内 datetime 名字：只在
        没有显式传 tz（旧 bug 的裸调用方式）时退化为纯 UTC 解释；显式传 tz 时原样
        委托真实实现（真实 datetime.fromtimestamp(ts, tz=...) 本就不依赖系统时区）。

        已知 UTC 时刻 2026-07-02 20:00:00Z == 中国时区 2026-07-03 04:00（次日凌晨）。
        文本"明天晚上"应算出中国时区 2026-07-04 20:00——如果退化成裸系统时区
        （模拟 UTC）解读，"今天"会被误判成 07-02，"明天"变成 07-03，整整错一天。
        """
        real_datetime = _memory_system_mod.datetime

        class _FakeSystemUTCDatetime(real_datetime):
            @classmethod
            def fromtimestamp(cls, ts, tz=None):
                if tz is None:
                    return real_datetime.fromtimestamp(ts, tz=timezone.utc).replace(
                        tzinfo=None
                    )
                return real_datetime.fromtimestamp(ts, tz=tz)

        monkeypatch.setattr(_memory_system_mod, "datetime", _FakeSystemUTCDatetime)

        now = real_datetime(2026, 7, 2, 20, 0, 0, tzinfo=timezone.utc).timestamp()
        due_ts = _memory_system_mod._estimate_due_ts("明天晚上一起吃饭吧", now=now)
        due_cst = real_datetime.fromtimestamp(due_ts, tz=timezone(timedelta(hours=8)))
        assert (due_cst.year, due_cst.month, due_cst.day, due_cst.hour) == (
            2026, 7, 4, 20,
        )


# ===========================================================================
# MAJOR-1 rider：72h TTL 自愈兜底——发送点 consume 万一被漏调，due_pending_followup
# 扫描时自己丢掉早已到期太久的僵尸线索，不再无限期复读同一个 user_followup 标签。
# ===========================================================================


class TestFollowupTTLBackstop:
    def test_stale_entry_past_ttl_is_dropped_on_scan(self):
        ms = MemorySystem()
        ms.write_summary("我答应你明天一定去面试", source_turns=1, temperature=0.0)
        due_ts = ms._pending_followups[0]["due_ts_estimate"]
        stale_now = due_ts + ms._FOLLOWUP_TTL_SECONDS + 1.0
        assert ms.due_pending_followup(now=stale_now) is None
        # 自愈丢弃：不是"到期但不返回"，而是整条从列表里被清掉
        assert ms._pending_followups == []

    def test_entry_within_ttl_still_returned(self):
        """刚过期没多久（TTL 内）仍正常返回，不误伤——TTL 只兜底真正被遗忘的线索。"""
        ms = MemorySystem()
        ms.write_summary("我答应你明天一定去面试", source_turns=1, temperature=0.0)
        due_ts = ms._pending_followups[0]["due_ts_estimate"]
        within_ttl_now = due_ts + ms._FOLLOWUP_TTL_SECONDS - 10.0
        due = ms.due_pending_followup(now=within_ttl_now)
        assert due is not None
        assert "面试" in due["topic_snippet"]
        assert len(ms._pending_followups) == 1

    def test_ttl_drop_does_not_disturb_other_valid_entries(self):
        """僵尸线索只丢自己那条，同会话里其它仍在 TTL 内的线索不受影响。"""
        ms = MemorySystem()
        ms.write_summary("我答应你明天一定去面试", source_turns=1, temperature=0.0)
        ms.write_summary("我保证后天一定还钱", source_turns=1, temperature=0.0)
        stale_entry, fresh_entry = ms._pending_followups[0], ms._pending_followups[1]
        # 把第一条推到 TTL 之外，第二条保持刚到期（TTL 内）
        stale_now = stale_entry["due_ts_estimate"] + ms._FOLLOWUP_TTL_SECONDS + 1.0
        fresh_entry["due_ts_estimate"] = stale_now - 5.0

        due = ms.due_pending_followup(now=stale_now)
        assert due is not None
        assert "还钱" in due["topic_snippet"]
        assert len(ms._pending_followups) == 1
        assert "面试" not in ms._pending_followups[0]["topic_snippet"]


# ===========================================================================
# MINOR rider (a)：restore 时过滤 due_ts_estimate 非有限数的条目——None/NaN/±inf
# （例如损坏的存档）此前会让 due_pending_followup 的比较 TypeError，被调用方
# try/except 静默吞掉，效果是"user_followup 标签能力全体失效"。
# ===========================================================================


class TestFollowupRestoreFiltersNonFiniteDueTs:
    def test_none_due_ts_dropped_at_restore(self):
        ms = MemorySystem()
        ms.write_summary("我答应你明天一定去面试", source_turns=1, temperature=0.0)
        blob = ms.to_dict()
        blob["pending_followups"][0]["due_ts_estimate"] = None
        restored = MemorySystem.create_from_dict(blob)
        assert restored._pending_followups == []
        # 且不会因为坏条目混进去而让 due_pending_followup 整体 TypeError
        assert restored.due_pending_followup() is None

    def test_nan_due_ts_dropped_at_restore(self):
        ms = MemorySystem()
        ms.write_summary("我答应你明天一定去面试", source_turns=1, temperature=0.0)
        blob = ms.to_dict()
        blob["pending_followups"][0]["due_ts_estimate"] = float("nan")
        restored = MemorySystem.create_from_dict(blob)
        assert restored._pending_followups == []

    def test_inf_due_ts_dropped_at_restore(self):
        ms = MemorySystem()
        ms.write_summary("我答应你明天一定去面试", source_turns=1, temperature=0.0)
        blob = ms.to_dict()
        blob["pending_followups"][0]["due_ts_estimate"] = float("inf")
        restored = MemorySystem.create_from_dict(blob)
        assert restored._pending_followups == []

    def test_bad_entry_does_not_take_down_valid_sibling(self):
        """坏条目只丢自己那条，不连累同一存档里其它有效的跟进线索。"""
        ms = MemorySystem()
        ms.write_summary("我答应你明天一定去面试", source_turns=1, temperature=0.0)
        ms.write_summary("我保证后天一定还钱", source_turns=1, temperature=0.0)
        blob = ms.to_dict()
        blob["pending_followups"][0]["due_ts_estimate"] = None
        restored = MemorySystem.create_from_dict(blob)
        assert len(restored._pending_followups) == 1
        assert "还钱" in restored._pending_followups[0]["topic_snippet"]


# ===========================================================================
# T2-05③：consume-on-mention —— 用户主动提起同一话题时静默消费
# ===========================================================================


class TestConsumeOnMention:
    def test_overlapping_mention_consumes_silently(self):
        ms = MemorySystem()
        ms.write_summary("我答应你明天一定去面试", source_turns=1, temperature=0.0)
        assert len(ms._pending_followups) == 1
        consumed = ms.consume_pending_followups_by_text("面试怎么样了呀明天")
        assert consumed == 1
        assert ms._pending_followups == []

    def test_unrelated_mention_does_not_consume(self):
        ms = MemorySystem()
        ms.write_summary("我答应你明天一定去面试", source_turns=1, temperature=0.0)
        consumed = ms.consume_pending_followups_by_text("今天中午吃了什么呢")
        assert consumed == 0
        assert len(ms._pending_followups) == 1

    def test_empty_text_no_op(self):
        ms = MemorySystem()
        ms.write_summary("我答应你明天一定去面试", source_turns=1, temperature=0.0)
        assert ms.consume_pending_followups_by_text("") == 0
        assert len(ms._pending_followups) == 1

    # -- MAJOR-2 红队实测：触发词（明天/一定/答应/数字）撑过阈值的假阳性 --------

    def test_probe_明天见_does_not_falsely_consume(self):
        """仅靠触发词『明天』撑过旧阈值，跟话题内容（面试）毫无关系。"""
        ms = MemorySystem()
        ms.write_summary("我答应你明天一定去面试", source_turns=1, temperature=0.0)
        assert ms.consume_pending_followups_by_text("明天见！") == 0
        assert len(ms._pending_followups) == 1

    def test_probe_明天再说吧_does_not_falsely_consume(self):
        ms = MemorySystem()
        ms.write_summary("我答应你明天一定去面试", source_turns=1, temperature=0.0)
        assert ms.consume_pending_followups_by_text("明天再说吧") == 0
        assert len(ms._pending_followups) == 1

    def test_probe_我明天有空_does_not_falsely_consume(self):
        ms = MemorySystem()
        ms.write_summary("我答应你明天一定去面试", source_turns=1, temperature=0.0)
        assert ms.consume_pending_followups_by_text("我明天有空") == 0
        assert len(ms._pending_followups) == 1

    def test_probe_一定哦_does_not_falsely_consume(self):
        ms = MemorySystem()
        ms.write_summary("我答应你明天一定去面试", source_turns=1, temperature=0.0)
        assert ms.consume_pending_followups_by_text("一定哦") == 0
        assert len(ms._pending_followups) == 1

    def test_fallback_tokenizer_trigger_only_mentions_do_not_consume(self, monkeypatch):
        """无 jieba 时，承诺/时间触发短语本身仍不能冒充话题内容。"""
        monkeypatch.setattr(_memory_system_mod, "_jieba", None)
        for text in ("明天见！", "明天再说吧", "我明天有空", "一定哦"):
            ms = MemorySystem()
            ms.write_summary("我答应你明天一定去面试", source_turns=1, temperature=0.0)
            assert ms.consume_pending_followups_by_text(text) == 0
            assert len(ms._pending_followups) == 1

    def test_true_positive_content_mention_still_consumes(self, monkeypatch):
        """无 jieba 时真提到实质内容（面试）仍应正常消费。"""
        monkeypatch.setattr(_memory_system_mod, "_jieba", None)
        ms = MemorySystem()
        ms.write_summary("我答应你明天一定去面试", source_turns=1, temperature=0.0)
        consumed = ms.consume_pending_followups_by_text("面试过了,还挺顺利")
        assert consumed == 1
        assert ms._pending_followups == []


# ===========================================================================
# T2-05③ message-ingest 接线：LLMRequestPipeline._prepare_memory_context
# ===========================================================================


class _FakeEngine:
    def observe(self):
        return {"warmth": 0.0}


class _FakeComputation:
    engine = _FakeEngine()


class _FakeKernel:
    computation = _FakeComputation()
    last_event = {"now": 0.0}


class _FakeHost:
    kernel = _FakeKernel()


def _make_pipe(mem_sys: MemorySystem):
    store = SessionStateStore()

    class _FakePlugin:
        _store = store
        config = {}
        _config = {}

        def _host(self, sk):
            return _FakeHost()

        def _memory_system_for_session(self, sk):
            return mem_sys

    pipe = LLMRequestPipeline.__new__(LLMRequestPipeline)
    pipe._p = _FakePlugin()
    return pipe, store


class TestConsumeOnMentionPipelineWiring:
    def test_prepare_memory_context_consumes_matching_thread(self) -> None:
        """直调真实 _prepare_memory_context：本轮消息命中话题关键词 → 静默消费。"""
        mem_sys = MemorySystem()
        mem_sys.write_summary("我答应你明天一定去面试", source_turns=1, temperature=0.0)
        pipe, store = _make_pipe(mem_sys)
        store.memory_systems.set("s1", mem_sys)  # 模拟该会话已有 memory_system 实例

        asyncio.run(
            pipe._prepare_memory_context(
                "s1", "面试怎么样了呀明天", gap_seconds=0.0, realtime_enabled=False
            )
        )
        assert mem_sys._pending_followups == []

    def test_prepare_memory_context_unrelated_text_keeps_thread(self) -> None:
        mem_sys = MemorySystem()
        mem_sys.write_summary("我答应你明天一定去面试", source_turns=1, temperature=0.0)
        pipe, store = _make_pipe(mem_sys)
        store.memory_systems.set("s1", mem_sys)

        asyncio.run(
            pipe._prepare_memory_context(
                "s1", "今天中午吃了什么", gap_seconds=0.0, realtime_enabled=False
            )
        )
        assert len(mem_sys._pending_followups) == 1

    def test_prepare_memory_context_does_not_create_memory_system_for_new_session(
        self,
    ) -> None:
        """全新会话（_store.memory_systems 尚无实例）不该因 consume-on-mention
        检查而提前创建 memory_system——没有实例就意味着没有待办，零开销跳过。"""
        mem_sys = MemorySystem()
        pipe, store = _make_pipe(mem_sys)
        # 故意不调用 store.memory_systems.set(...)

        asyncio.run(
            pipe._prepare_memory_context(
                "brand_new", "随便聊聊", gap_seconds=0.0, realtime_enabled=False
            )
        )
        assert not store.memory_systems.has("brand_new")


# ===========================================================================
# T2-05 persistence：随 MemorySystem 自身 to_dict/from_dict 周期往返
# ===========================================================================


class TestPendingFollowupPersistence:
    def test_roundtrip_preserves_pending_followups(self):
        ms = MemorySystem()
        ms.write_summary("我答应你明天一定去面试", source_turns=1, temperature=0.0)
        blob = ms.to_dict()
        assert "pending_followups" in blob
        restored = MemorySystem.create_from_dict(blob)
        assert len(restored._pending_followups) == 1
        assert "面试" in restored._pending_followups[0]["topic_snippet"]

    def test_load_compat_missing_key_defaults_empty(self):
        """旧存档没有 pending_followups 字段——容缺，不炸。"""
        ms = MemorySystem()
        ms.write_summary("普通闲聊", source_turns=1, temperature=0.0)
        blob = ms.to_dict()
        blob.pop("pending_followups", None)
        restored = MemorySystem.create_from_dict(blob)
        assert restored._pending_followups == []


# ===========================================================================
# T2-06④/④'：早安/晚安观察 → RitualRegistry → 接线进 ProactiveScheduler
# ===========================================================================


class _RecordingRelationScheduler:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int, int]] = []

    def register_ritual(
        self,
        owner_token: str,
        pattern: str,
        hour_start: int,
        hour_end: int,
    ) -> None:
        self.calls.append((owner_token, pattern, hour_start, hour_end))


def _relation_context(tmp_path, scopes):
    repository = ScopeRepository(tmp_path / "scope-v1")
    session_scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    identity = ScopeIdentityKey(key_id="ritual-test-key", secret=b"r" * 32)
    subject = identity.authenticated_subject(
        session_scope.bot_ref,
        VerifiedSubjectInput(platform_realm="adapter", subject_id="ritual-person"),
    )
    assert subject is not None
    registry = ScopeRuntimeRegistry(repository=repository)
    relation = registry.relation_for(session_scope, subject)
    assert relation is not None
    session_runtime = registry.exact_session(session_scope)
    scheduler = _RecordingRelationScheduler()
    object.__setattr__(session_runtime, "proactive_scheduler", scheduler)

    class _Plugin:
        _scope_runtime_registry = registry
        config = {}

        def _active_scoped_session_runtime(self):
            return session_runtime

        def _active_relation_runtime(self):
            return relation

    return repository, session_scope, relation, scheduler, SessionContext(_Plugin())


class TestRitualObservationWiring:
    def test_below_threshold_does_not_register_or_reach_scheduler(self, tmp_path, scopes) -> None:
        _, _, relation, scheduler, context = _relation_context(tmp_path, scopes)
        context.observe_ritual_pattern("ignored", 22, "night_farewell")
        context.observe_ritual_pattern("ignored", 22, "night_farewell")
        assert relation.ritual("night_farewell") is None
        assert scheduler.calls == []

    def test_third_observation_is_relation_local_and_only_hints_owner_scheduler(
        self,
        tmp_path,
        scopes,
    ) -> None:
        _, _, relation, scheduler, context = _relation_context(tmp_path, scopes)
        for _ in range(3):
            context.observe_ritual_pattern("foreign-session", 22, "night_farewell")

        assert relation.ritual("night_farewell") == {
            "hour_start": 22,
            "hour_end": 23,
            "pattern": "night_farewell",
        }
        assert scheduler.calls == [
            (relation.scope.relation_ref.token, "night_farewell", 22, 23)
        ]
        assert ":" not in scheduler.calls[0][0]

    def test_detect_and_observe_from_text_uses_china_hour_without_session_namespace(
        self,
        tmp_path,
        scopes,
        monkeypatch,
    ) -> None:
        _, _, relation, _, context = _relation_context(tmp_path, scopes)
        ts = datetime(2026, 7, 2, 23, 30, 0, tzinfo=timezone.utc).timestamp()

        def _boom(_ts=None):
            raise AssertionError("不应再调用依赖系统时区的 time.localtime()")

        monkeypatch.setattr(time, "localtime", _boom)
        for _ in range(3):
            context.detect_and_observe_ritual_from_text("foreign", "早安呀！", now=ts)
        assert relation.ritual("morning_greeting") == {
            "hour_start": 7,
            "hour_end": 8,
            "pattern": "morning_greeting",
        }

    def test_detect_and_observe_from_text_registers_night_on_active_relation(
        self,
        tmp_path,
        scopes,
    ) -> None:
        _, _, relation, scheduler, context = _relation_context(tmp_path, scopes)
        ts = datetime(2026, 7, 3, 15, 0, 0, tzinfo=timezone.utc).timestamp()

        for _ in range(3):
            context.detect_and_observe_ritual_from_text(
                "foreign",
                "晚安啦，睡了",
                now=ts,
            )

        assert relation.ritual("night_farewell") == {
            "hour_start": 23,
            "hour_end": 0,
            "pattern": "night_farewell",
        }
        assert scheduler.calls == [
            (relation.scope.relation_ref.token, "night_farewell", 23, 0)
        ]

    def test_non_ritual_text_is_noop_for_active_relation(
        self,
        tmp_path,
        scopes,
    ) -> None:
        _, _, relation, scheduler, context = _relation_context(tmp_path, scopes)
        ts = datetime(2026, 7, 3, 4, 0, 0, tzinfo=timezone.utc).timestamp()

        for _ in range(3):
            context.detect_and_observe_ritual_from_text(
                "foreign",
                "中午吃什么呢",
                now=ts,
            )

        assert relation.ritual("morning_greeting") is None
        assert relation.ritual("night_farewell") is None
        assert scheduler.calls == []

    def test_missing_relation_is_a_noop(self, tmp_path) -> None:
        context = SessionContext(types.SimpleNamespace(config={}))
        context.detect_and_observe_ritual_from_text("foreign", "早安呀！", now=time.time())


class TestRitualRegistrySerialization:
    def test_roundtrip_uses_pattern_only(self) -> None:
        reg = RitualRegistry()
        for _ in range(3):
            reg.observe_pattern(22, "night_farewell", observed_at=1.0)
        blob = reg.to_dict()
        restored = RitualRegistry.from_dict(blob)
        assert restored.get_ritual("night_farewell") == reg.get_ritual("night_farewell")
        assert set(blob["rituals"]) == {"night_farewell"}

    def test_from_dict_tolerates_garbage(self) -> None:
        reg = RitualRegistry.from_dict({"rituals": "not-a-dict", "observations": None})
        assert reg.get_active_rituals() == []
        reg2 = RitualRegistry.from_dict(None)
        assert reg2.get_active_rituals() == []


# ===========================================================================
# 冷却闸门不因跟进线索存在而失效
# ===========================================================================


class TestCooldownStillGatesDespiteDueFollowup:
    def test_request_dispatch_cooldown_blocks_before_reason_code(self) -> None:
        """冷却期内，即使该会话有一条已到期的跟进线索，request_dispatch 也应在
        dispatch_blocked_reason 阶段就被挡下——根本不会走到
        get_speech_decision/infer_reason_code，新增的 user_followup 检查不能
        成为绕过冷却的旁路。"""
        mem = MemorySystem()
        mem.write_summary("我答应你明天一定去面试", source_turns=1, temperature=0.0)
        mem._pending_followups[0]["due_ts_estimate"] = time.time() - 10.0

        now = time.time()
        p = types.SimpleNamespace()
        p.config = {
            "enable_proactive_speech_dispatch": True,
            "proactive_speech_dispatch_cooldown_seconds": 1800.0,
        }
        p._observed_now = lambda: now
        p._store = types.SimpleNamespace(
            proactive_candidate_sessions={}, hosts={},
        )
        # 5 秒前刚发过，远小于 1800s 冷却
        p._proactive_dispatch_last_sent = {"sessA": now - 5.0}
        p._memory_system_for_session = lambda sk: mem

        class _Ev:
            unified_msg_origin = "sessA"

        sched = ProactiveScheduler(p)
        result = asyncio.run(
            sched.request_dispatch(event_or_session=_Ev(), session_key="sessA")
        )
        assert result["dispatched"] is False
        assert result["reason"] == "cooldown_active"
        # 到期线索仍原封不动地留着（没有被误消费/误发出）
        assert len(mem._pending_followups) == 1


# ===========================================================================
# MAJOR-1：user_followup 标签的消息真正发出后，消费掉产生该标签的那条线索
#
# 两条可达 dispatch 路径都要接：这里覆盖 proactive_scheduler.request_dispatch；
# llm_request_pipeline._life_sim_outreach 的 5min fallback 直发分支见
# tests/test_lifesim_routing_pri.py 的
# test_life_sim_outreach_consumes_followup_after_bridge_dispatch。
# ===========================================================================


class TestMajorOneConsumeOnDispatchWiring:
    def test_request_dispatch_consumes_thread_after_real_send(self) -> None:
        """dispatch 真正成功（result['dispatched'] is True）后，产生 user_followup
        标签的那条待跟进线索应被消费掉——否则它会一直"到期"，让接下来经这条
        路径触发的每一次主动发言都被重新贴上一模一样的标签文案（issue-43 同源
        的内容复读）。只 stub 掉"是否真的连上了大饼"的机制细节（bridge.available/
        should_dispatch_now/dispatch，已有 test_proactive_bridge.py 覆盖），
        infer_reason_code / build_motivation_text / consume_followup_on_dispatch
        全部走真实实现。
        """
        mem = MemorySystem()
        mem.write_summary("我答应你明天一定去面试", source_turns=2, temperature=0.5)
        mem._pending_followups[0]["due_ts_estimate"] = time.time() - 10.0

        class _FakeHost:
            def diagnostics(self) -> dict:
                return {"body": {"pulse": {"mood_label": "平静"}}}

        p = types.SimpleNamespace()
        p.config = {
            "enable_proactive_speech_dispatch": True,
            "sylanne_alpha_proactive_bridge_enabled": True,
        }
        p._store = SessionStateStore()
        p._store.memory_systems.set("sessA", mem)
        p._observed_now = lambda: time.time()
        p._proactive_dispatch_last_sent = {}
        p._host = lambda sk: _FakeHost()
        p._memory_system_for_session = lambda sk: mem

        sched = ProactiveScheduler(p)

        async def _fake_get_speech_decision(*args, **kwargs):
            return {"action": "reach_out", "allowed": True}

        sched.get_speech_decision = _fake_get_speech_decision  # type: ignore[method-assign]

        bridge = ProactiveBridge(p)
        bridge.available = lambda: True  # type: ignore[method-assign]
        bridge.should_dispatch_now = lambda sk: (True, "ok")  # type: ignore[method-assign]

        async def _fake_dispatch(sk: str, motivation: str) -> dict:
            return {"dispatched": True, "reason": "ok"}

        bridge.dispatch = _fake_dispatch  # type: ignore[method-assign]
        p._proactive_bridge = bridge

        class _Ev:
            unified_msg_origin = "sessA"

        result = asyncio.run(sched.request_dispatch(_Ev(), force=True))

        assert result["dispatched"] is True
        # 产生 user_followup 标签的那条线索应已被真正消费——不再等在列表里。
        assert mem._pending_followups == []

    def test_request_dispatch_does_not_consume_when_not_dispatched(self) -> None:
        """反证：桥接没有真的发出去（dispatched=False）时绝不消费——没发出去
        不该消费掉"记得要问"的线索。"""
        mem = MemorySystem()
        mem.write_summary("我答应你明天一定去面试", source_turns=2, temperature=0.5)
        mem._pending_followups[0]["due_ts_estimate"] = time.time() - 10.0

        class _FakeHost:
            def diagnostics(self) -> dict:
                return {"body": {"pulse": {"mood_label": "平静"}}}

        p = types.SimpleNamespace()
        p.config = {
            "enable_proactive_speech_dispatch": True,
            "sylanne_alpha_proactive_bridge_enabled": True,
        }
        p._store = SessionStateStore()
        p._store.memory_systems.set("sessA", mem)
        p._observed_now = lambda: time.time()
        p._proactive_dispatch_last_sent = {}
        p._host = lambda sk: _FakeHost()
        p._memory_system_for_session = lambda sk: mem

        sched = ProactiveScheduler(p)

        async def _fake_get_speech_decision(*args, **kwargs):
            return {"action": "reach_out", "allowed": True}

        sched.get_speech_decision = _fake_get_speech_decision  # type: ignore[method-assign]

        bridge = ProactiveBridge(p)
        bridge.available = lambda: True  # type: ignore[method-assign]
        bridge.should_dispatch_now = lambda sk: (True, "ok")  # type: ignore[method-assign]

        async def _fake_dispatch_fails(sk: str, motivation: str) -> dict:
            return {"dispatched": False, "reason": "error:boom"}

        bridge.dispatch = _fake_dispatch_fails  # type: ignore[method-assign]
        p._proactive_bridge = bridge

        class _Ev:
            unified_msg_origin = "sessA"

        result = asyncio.run(sched.request_dispatch(_Ev(), force=True))

        assert result["dispatched"] is False
        assert len(mem._pending_followups) == 1
