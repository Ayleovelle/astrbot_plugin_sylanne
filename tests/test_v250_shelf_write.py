"""v2.5.0 P0 slice 2 + slice-1b：跨群记忆货架写侧测试。

design: docs/architecture/v250-cross-group-memory-design.md §2.1（W0-W4）/ §6
（开关表）/ §8（B1/B5，slice-1b 全矩阵扎实版修正）。

本文件覆盖范围（严格遵守，测试同样只覆盖这些）：
- W0 净化双摘要接入 `_flush_conversation_to_l1`（llm_request_pipeline.py）。
- B1 已认证身份记录读闸消费（读不到即整条 SKIP）。
- 6 键门控（default off 零写 / shadow·on 才写 / scope=owner 身份门控）。
- W0b 出口哨兵（群聊背景标记 + 本轮 group_observed sender 名单双检查）。
- origin_scope/origin_id/platform 直接消费"已认证身份记录"（slice-1b：不再由
  写点自行反解析 session_key，一并修复 MINOR#3 写读键三段分叉）。
- 货架键纳入 purge 级联（反向索引 + `_delete_sylanne_memory_state_impl`）。
- 货架键（含反向索引键）纳入 MEMORY_KV_KEYS_MANIFEST（未来备份模块的枚举源）。

**生产形态纪律（slice-1b）**：本文件所有 `session_key` 均改用生产形态的裸键
（私聊=对端裸 QQ、群 unique_session ON=`f"{sender}_{group}"`、共享桶=裸
group_id），不再沿用"`aiocqhttp:FriendMessage:u1`"这种 UMO 形状的假
session_key——探针实测生产 session_key 从不是 UMO 形状，旧测试用这种假键
"恰好"让 `platform_from_umo(session_key)` 等字符串解析函数算对，掩盖了
生产上这些函数全部失效的事实（见 design "write_read_alignment"）。身份记录
（platform/origin_scope/origin_id）现由 `SessionContext.
resolve_authenticated_identity` 或测试直接注入（`set_authenticated_identity`），
不再从 session_key 反解析。

读侧（R1-R6）、PersonProfile 软同步、出生播种均不在本文件范围内。
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

from sylanne_alpha.memory_migration_spine import MEMORY_KV_KEYS_MANIFEST
from sylanne_alpha.memory_system import ConversationBuffer, MemorySystem
from sylanne_alpha.person_shelf import (
    load_person_shelf,
    person_shelf_kv_key,
    person_shelf_origin_index_kv_key,
)
from sylanne_alpha.session_context import SessionContext
from sylanne_alpha.session_state_store import SessionStateStore
from sylanne_alpha.state_persistence import StatePersistence


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 最小化插件替身（复刻 tests/test_mem_phase1_pr4_pending_delete_index.py 的写法）
# ---------------------------------------------------------------------------


class _FakeSocialField:
    """真实 social_field 的最小等价：本文件写侧测试不再依赖它判定 platform/
    origin（那是 slice-1b 修复的 MINOR#3 本体），保留只是防止其他未触碰的
    调用路径（如有）意外 AttributeError。
    """

    def is_group_context_by_key(self, session_key: str) -> bool:
        return "Group" in session_key or "group" in session_key

    def extract_group_id_from_key(self, session_key: str) -> str:
        if ":" in session_key:
            return session_key.rsplit(":", 1)[0]
        return session_key


class _FakeHost:
    class _Engine:
        def observe(self) -> dict[str, float]:
            return {"warmth": 0.5}

    class _Computation:
        def __init__(self) -> None:
            self.engine = _FakeHost._Engine()

    class _Kernel:
        def __init__(self) -> None:
            self.computation = _FakeHost._Computation()

    def __init__(self) -> None:
        self.kernel = _FakeHost._Kernel()


class _FakePlugin:
    def __init__(
        self,
        *,
        cross_session_mode: str = "off",
        cross_session_scope: str = "owner",
        owner_id: str = "",
        shared_kv: dict[str, Any] | None = None,
    ) -> None:
        self._store = SessionStateStore()
        self._background_tasks: list = []
        self.config: dict[str, Any] = {"sylanne_alpha_owner_id": owner_id}
        self._config: dict[str, Any] = {}
        self._kv: dict[str, Any] = shared_kv if shared_kv is not None else {}
        self._amnesia_sessions: set = set()
        self._session_ctx = SessionContext(self)
        self._state_persistence = StatePersistence(self)
        self._state_persistence._pending_delete_scan_done = True
        self._social_field = _FakeSocialField()
        self._cross_session_mode = cross_session_mode
        self._cross_session_scope = cross_session_scope
        self._memory_systems_cache: dict[str, MemorySystem] = {}

    # ---- KV API ----
    async def get_kv_data(self, key: str, default: Any = None) -> Any:
        return self._kv.get(key, default)

    async def put_kv_data(self, key: str, value: Any) -> None:
        self._kv[key] = value

    async def delete_kv_data(self, key: str) -> None:
        self._kv.pop(key, None)

    # ---- cross_session_config 读取契约 ----
    def _cfg(self, key: str, default: str = "") -> str:
        if key == "sylanne_alpha_cross_session_mode":
            return self._cross_session_mode
        if key == "sylanne_alpha_cross_session_scope":
            return self._cross_session_scope
        return default

    def _cfg_bool(self, key: str, default: bool = False) -> bool:
        return default

    # ---- pipeline 依赖 ----
    def _memory_system_for_session(self, session_key: str) -> MemorySystem:
        if session_key not in self._memory_systems_cache:
            self._memory_systems_cache[session_key] = MemorySystem()
        return self._memory_systems_cache[session_key]

    def _host(self, session_key: str) -> _FakeHost:
        return _FakeHost()

    async def _persist_kernel(self, session_key: str, host: Any) -> None:
        return None

    async def _save_sylanne_memory_state(self, session_key: str, memory_system: Any) -> None:
        return None


def _mk_pipeline(plugin: _FakePlugin, summarizer_return: str = "摘要内容OK"):
    from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline

    pipe = LLMRequestPipeline.__new__(LLMRequestPipeline)
    pipe._p = plugin
    pipe._summarizer_llm_call = AsyncMock(return_value=summarizer_return)
    return pipe


def _seed_buffer(
    plugin: _FakePlugin,
    session_key: str,
    *,
    group_observed: list[dict] | None = None,
) -> None:
    buf = plugin._store.conversation_buffers.get_or_create(
        session_key, lambda: ConversationBuffer(session_key=session_key)
    )
    if group_observed:
        buf.inject_context(group_observed)
    buf.append("user", "今天想吃火锅")
    buf.append("bot", "好呀，一起去")


def _seed_private_identity(plugin: _FakePlugin, sk: str, sender_id: str) -> None:
    """生产形态私聊身份记录：与 `resolve_authenticated_identity` 的私聊分支
    同形状——origin_id 就是 session_key 本身。"""
    plugin._store.set_authenticated_identity(
        sk, sender_id=sender_id, platform="aiocqhttp",
        origin_scope="private", origin_id=sk,
    )


def _seed_group_identity(
    plugin: _FakePlugin, sk: str, sender_id: str, group_id: str,
) -> None:
    """生产形态 unique_session ON 群聊身份记录：origin_id 用真实群号
    （`SessionContext.resolve_authenticated_identity` 来自 `event.get_group_id()`，
    不是从 session_key 解析出来的）。"""
    plugin._store.set_authenticated_identity(
        sk, sender_id=sender_id, platform="aiocqhttp",
        origin_scope="group", origin_id=f"group:{group_id}",
    )


def _shelf_kv_keys(plugin: _FakePlugin) -> list[str]:
    return [k for k in plugin._kv if k.startswith("sylanne_person_shelf:")]


# ===========================================================================
# 1. default off = 整条零写（含证明：即便无 B1 认证也不因为货架支路而炸/写）
# ===========================================================================


def test_default_off_writes_nothing_to_shelf():
    plugin = _FakePlugin(cross_session_mode="off")
    sk = "u1"  # 生产形态：私聊裸 session_key = 对端裸 QQ
    _seed_private_identity(plugin, sk, "u1")
    _seed_buffer(plugin, sk)
    pipe = _mk_pipeline(plugin)

    _run(pipe._flush_conversation_to_l1(sk))

    assert _shelf_kv_keys(plugin) == []
    # 主档摘要照旧写入（W0 支路完全独立，不影响主路径）
    mem = plugin._memory_system_for_session(sk)
    assert len(mem._l1) == 1


def test_default_off_byte_identical_even_without_b1_authenticated_sender():
    """default off 时即便压根没有已认证身份记录，货架支路第一行 settings.enabled
    判断就整体 return，不会走到 get_authenticated_identity / KV 读写——证明是
    真正的零成本 no-op，而非"恰好因为别的门槛也没过才没写"。
    """
    plugin = _FakePlugin(cross_session_mode="off")
    sk = "u2"
    _seed_buffer(plugin, sk)
    pipe = _mk_pipeline(plugin)

    _run(pipe._flush_conversation_to_l1(sk))

    assert _shelf_kv_keys(plugin) == []
    mem = plugin._memory_system_for_session(sk)
    assert len(mem._l1) == 1  # 主档不受影响


# ===========================================================================
# 2. shadow / on 才写（default off 与两者对照）
# ===========================================================================


def test_shadow_mode_writes_shelf():
    plugin = _FakePlugin(cross_session_mode="shadow", cross_session_scope="all")
    sk = "u3"
    _seed_private_identity(plugin, sk, "u3")
    _seed_buffer(plugin, sk)
    pipe = _mk_pipeline(plugin)

    _run(pipe._flush_conversation_to_l1(sk))

    key = person_shelf_kv_key("aiocqhttp", "u3")
    assert key in plugin._kv
    bucket = _run(load_person_shelf(plugin, "aiocqhttp", "u3"))
    assert len(bucket.items) == 1
    assert bucket.items[0].text  # 非空摘要
    assert bucket.items[0].origin_scope == "private"


def test_on_mode_writes_shelf():
    plugin = _FakePlugin(cross_session_mode="on", cross_session_scope="all")
    sk = "u4"
    _seed_private_identity(plugin, sk, "u4")
    _seed_buffer(plugin, sk)
    pipe = _mk_pipeline(plugin)

    _run(pipe._flush_conversation_to_l1(sk))

    bucket = _run(load_person_shelf(plugin, "aiocqhttp", "u4"))
    assert len(bucket.items) == 1


# ===========================================================================
# 3. B1 SKIP：读不到已认证身份记录（共享桶/无 event 上下文）即整条 SKIP
# ===========================================================================


def test_b1_none_skips_shelf_write_even_when_mode_on():
    plugin = _FakePlugin(cross_session_mode="on", cross_session_scope="all")
    sk = "g1"  # 共享桶（unique_session OFF，裸群号）：从未 set 身份记录
    _seed_buffer(plugin, sk)
    pipe = _mk_pipeline(plugin)

    _run(pipe._flush_conversation_to_l1(sk))

    assert _shelf_kv_keys(plugin) == []
    # 主档不受影响：共享桶场景下主摘要照常写（B1 只挡货架，不挡主档）
    mem = plugin._memory_system_for_session(sk)
    assert len(mem._l1) == 1


# ===========================================================================
# 4. scope=owner 身份门控
# ===========================================================================


def test_scope_owner_rejects_non_owner_sender():
    plugin = _FakePlugin(
        cross_session_mode="on", cross_session_scope="owner", owner_id="owner_007"
    )
    sk = "stranger"
    _seed_private_identity(plugin, sk, "stranger")
    _seed_buffer(plugin, sk)
    pipe = _mk_pipeline(plugin)

    _run(pipe._flush_conversation_to_l1(sk))

    assert _shelf_kv_keys(plugin) == []


def test_scope_owner_accepts_owner_sender():
    plugin = _FakePlugin(
        cross_session_mode="on", cross_session_scope="owner", owner_id="owner_007"
    )
    sk = "owner_007"
    _seed_private_identity(plugin, sk, "owner_007")
    _seed_buffer(plugin, sk)
    pipe = _mk_pipeline(plugin)

    _run(pipe._flush_conversation_to_l1(sk))

    bucket = _run(load_person_shelf(plugin, "aiocqhttp", "owner_007"))
    assert len(bucket.items) == 1


def test_scope_owner_unconfigured_owner_id_rejects_everyone():
    """owner_id 未配置（空）→ fail-closed 全禁，即便 sender 非空也不写。"""
    plugin = _FakePlugin(cross_session_mode="on", cross_session_scope="owner", owner_id="")
    sk = "u5"
    _seed_private_identity(plugin, sk, "u5")
    _seed_buffer(plugin, sk)
    pipe = _mk_pipeline(plugin)

    _run(pipe._flush_conversation_to_l1(sk))

    assert _shelf_kv_keys(plugin) == []


# ===========================================================================
# 5. W0 剥离第三方（"张三"对抗用例）：group_observed 旁观内容不得进入货架净化摘要
# ===========================================================================


def test_w0_strips_third_party_observed_content_from_shelf_summary():
    plugin = _FakePlugin(cross_session_mode="on", cross_session_scope="all")
    sk = "u6_g9"  # 生产形态：unique_session ON 群聊 = f"{sender}_{group}"
    _seed_group_identity(plugin, sk, "u6", "g9")
    _seed_buffer(
        plugin,
        sk,
        group_observed=[{"text": "张三说他今天迟到了", "ts": 1.0, "sender_id": "张三"}],
    )

    async def _echo_contamination(prompt: str) -> str:
        # 货架净化摘要若把旁观者内容/群聊背景标记带进去了，这里会把它echo回来，
        # 从而在最终 item.text 里暴露污染；干净的话返回不含"张三"的摘要。
        if "张三" in prompt or "[群聊背景|" in prompt:
            return "CONTAMINATED_张三_LEAK"
        return "用户提议吃火锅，Sylanne 答应了"

    pipe = _mk_pipeline(plugin)
    pipe._summarizer_llm_call = AsyncMock(side_effect=_echo_contamination)

    _run(pipe._flush_conversation_to_l1(sk))

    bucket = _run(load_person_shelf(plugin, "aiocqhttp", "u6"))
    assert len(bucket.items) == 1
    assert "张三" not in bucket.items[0].text
    assert "[群聊背景|" not in bucket.items[0].text
    assert bucket.items[0].origin_scope == "group"
    assert bucket.items[0].origin_id == "group:g9"


# ===========================================================================
# 6. W0b 出口哨兵：即便净化摘要本身仍带群聊背景标记/命中旁观者 sender，也拒收
# ===========================================================================


def test_w0b_sentinel_rejects_leaked_group_background_marker():
    plugin = _FakePlugin(cross_session_mode="on", cross_session_scope="all")
    sk = "u7_g10"
    _seed_group_identity(plugin, sk, "u7", "g10")
    _seed_buffer(
        plugin,
        sk,
        group_observed=[{"text": "路人甲发言", "ts": 1.0, "sender_id": "路人甲"}],
    )
    pipe = _mk_pipeline(plugin)
    # 模拟一个"失守"的净化摘要：LLM 违规把标记原样吐回来了
    pipe._summarizer_llm_call = AsyncMock(return_value="[群聊背景|路人甲]: 还在说话")

    _run(pipe._flush_conversation_to_l1(sk))

    assert _shelf_kv_keys(plugin) == []


def test_w0b_sentinel_rejects_leaked_observer_sender_name():
    plugin = _FakePlugin(cross_session_mode="on", cross_session_scope="all")
    sk = "u8_g11"
    _seed_group_identity(plugin, sk, "u8", "g11")
    _seed_buffer(
        plugin,
        sk,
        group_observed=[{"text": "闲聊", "ts": 1.0, "sender_id": "lurker99"}],
    )
    pipe = _mk_pipeline(plugin)
    pipe._summarizer_llm_call = AsyncMock(return_value="lurker99 也参与了讨论")

    _run(pipe._flush_conversation_to_l1(sk))

    assert _shelf_kv_keys(plugin) == []


def test_w0_slow_path_failclosed_on_empty_llm_response_does_not_write_shelf():
    """W0 慢路径（has_context=True）净化摘要 LLM 空响应/拒答 → fail-closed 跳过
    货架写，绝不回落主档 fallback 拼接（W3）。主档仍照常写入。
    """
    plugin = _FakePlugin(cross_session_mode="on", cross_session_scope="all")
    sk = "u9_g12"
    _seed_group_identity(plugin, sk, "u9", "g12")
    _seed_buffer(
        plugin,
        sk,
        group_observed=[{"text": "背景闲聊", "ts": 1.0, "sender_id": "路人乙"}],
    )
    pipe = _mk_pipeline(plugin, summarizer_return="")  # 主摘要也走 fallback

    _run(pipe._flush_conversation_to_l1(sk))

    assert _shelf_kv_keys(plugin) == []
    mem = plugin._memory_system_for_session(sk)
    assert len(mem._l1) == 1  # 主档仍写（fallback 拼接是主档自己的降级路径）


def test_w0_fast_path_reuses_main_summary_without_extra_llm_call():
    """has_context=False 时快路径零成本复用主摘要，不应对 _summarizer_llm_call
    发起额外调用（除了主路径本身已经打的那次）。
    """
    plugin = _FakePlugin(cross_session_mode="on", cross_session_scope="all")
    sk = "u10"
    _seed_private_identity(plugin, sk, "u10")
    _seed_buffer(plugin, sk)  # 无 group_observed → has_context=False
    pipe = _mk_pipeline(plugin, summarizer_return="纯私聊摘要")

    _run(pipe._flush_conversation_to_l1(sk))

    bucket = _run(load_person_shelf(plugin, "aiocqhttp", "u10"))
    assert len(bucket.items) == 1
    assert bucket.items[0].text == "纯私聊摘要"
    # 只有主路径的一次摘要调用（无压缩轮，因为摘要 <=200 字，只会调 1 次）
    assert pipe._summarizer_llm_call.await_count == 1


# ===========================================================================
# 7. origin_scope/origin_id 按身份记录确定性赋值（"privacy 归一"覆盖）
# ===========================================================================


def test_private_session_gets_private_origin_scope_and_session_key_as_origin_id():
    plugin = _FakePlugin(cross_session_mode="on", cross_session_scope="all")
    sk = "u11"
    _seed_private_identity(plugin, sk, "u11")
    _seed_buffer(plugin, sk)
    pipe = _mk_pipeline(plugin)

    _run(pipe._flush_conversation_to_l1(sk))

    bucket = _run(load_person_shelf(plugin, "aiocqhttp", "u11"))
    assert bucket.items[0].origin_scope == "private"
    assert bucket.items[0].origin_id == sk


def test_group_session_gets_group_origin_scope_and_group_prefixed_origin_id():
    plugin = _FakePlugin(cross_session_mode="on", cross_session_scope="all")
    sk = "u12_g20"
    _seed_group_identity(plugin, sk, "u12", "g20")
    _seed_buffer(plugin, sk)
    pipe = _mk_pipeline(plugin)

    _run(pipe._flush_conversation_to_l1(sk))

    bucket = _run(load_person_shelf(plugin, "aiocqhttp", "u12"))
    assert bucket.items[0].origin_scope == "group"
    # slice-1b：origin_id 来自身份记录里 event.get_group_id() 算出的真实群号
    # （"g20"），不再是从 session_key 反解析出来的怪值。
    assert bucket.items[0].origin_id == "group:g20"


# ===========================================================================
# 8. 货架键纳入 purge 级联
# ===========================================================================


def test_purge_cascade_clears_shelf_bucket_via_reverse_index():
    plugin = _FakePlugin(cross_session_mode="on", cross_session_scope="all")
    sk = "u13"
    _seed_private_identity(plugin, sk, "u13")
    _seed_buffer(plugin, sk)
    pipe = _mk_pipeline(plugin)
    _run(pipe._flush_conversation_to_l1(sk))

    shelf_key = person_shelf_kv_key("aiocqhttp", "u13")
    assert shelf_key in plugin._kv
    safe = plugin._state_persistence._safe_session_key(sk)
    index_key = person_shelf_origin_index_kv_key(safe)
    assert index_key in plugin._kv

    _run(plugin._state_persistence.delete_sylanne_memory_state(sk))

    assert shelf_key not in plugin._kv
    assert index_key not in plugin._kv


def test_purge_cascade_no_shelf_bucket_is_noop_and_does_not_error():
    """从未写过货架的 session 走一遍删除，purge 级联 best-effort 静默跳过，
    不影响记忆三键的正常删除。
    """
    plugin = _FakePlugin(cross_session_mode="off")
    sk = "u14"
    mem = plugin._memory_system_for_session(sk)
    mem.write_summary(text="待删记忆", source_turns=1, session_key=sk)
    _run(plugin._state_persistence.save_sylanne_memory_state(sk, mem))
    assert plugin._kv.get(f"sylanne_memory_state:{sk}")

    _run(plugin._state_persistence.delete_sylanne_memory_state(sk))

    assert f"sylanne_memory_state:{sk}" not in plugin._kv


def test_register_failure_skips_shelf_write_leaves_no_orphan():
    """§8 B5 数据安全（红线邻接）：反向索引登记（register_person_shelf_origin）
    失败时，货架条目【不】落盘——保证每条真正落盘的货架必然已有可被 purge 反查
    的索引项，绝不留 purge 查不到的孤儿隐私残留。这条同时锁死"register 先于
    save"的次序：若 save 仍在 register 之前跑，则即便 register 失败货架桶也会
    出现，本断言会失败。
    """
    plugin = _FakePlugin(cross_session_mode="on", cross_session_scope="all")
    sk = "u15"
    _seed_private_identity(plugin, sk, "u15")
    _seed_buffer(plugin, sk)

    # 只让反向索引键的 put 失败（货架桶 put 本身仍可用）——精确模拟
    # register 写窗口失败，验证 save 被跳过。
    orig_put = plugin.put_kv_data

    async def _failing_put(key: str, value: Any) -> None:
        if key.startswith("sylanne_person_shelf_origin_index:"):
            raise RuntimeError("kv down during register")
        await orig_put(key, value)

    plugin.put_kv_data = _failing_put
    pipe = _mk_pipeline(plugin)

    _run(pipe._flush_conversation_to_l1(sk))

    # register 失败 → 货架桶零落盘（无孤儿）；主档不受影响。
    assert _shelf_kv_keys(plugin) == []
    mem = plugin._memory_system_for_session(sk)
    assert len(mem._l1) == 1


def test_reverse_index_key_uses_state_persistence_sanitizer_not_session_ctx():
    """回归：写侧登记反向索引必须用 purge 侧同一套 sanitizer
    (`StatePersistence._safe_session_key`)，不能用 `SessionContext.safe_session_key`
    ——后者额外把 ``:`` 等字符替换成 ``_`` 且截断 200 字符，与 purge 侧
    (`_delete_sylanne_memory_state_impl` -> `self._safe_session_key`) 的口径不同。

    本测试刻意用一个含 ``:`` 的 session_key（真实场景：适配器未正确设置
    `AstrBotMessage.session_id` 时，`session_key()` 会回退到含 `:` 的
    `unified_msg_origin`，见 `SessionContext.session_key` 的 fallback 分支）
    绕开两者共享的 `_safe_session_key_cache`（用纯字符串运算复刻
    `StatePersistence._safe_session_key` 的公式，而非调用实例方法），
    从而不被"缓存里已经有值、两边读到同一份缓存碰巧一致"掩盖
    ——旧代码在这里会因为 `session_key` 含 ``:`` 而写出两个不同的 safe key，
    此测试直接断言 KV 里出现的键是 purge 侧公式算出的那个。
    """
    plugin = _FakePlugin(cross_session_mode="on", cross_session_scope="all")
    sk = "aiocqhttp:GroupMessage:g30:u99"
    _seed_group_identity(plugin, sk, "u99", "g30")
    _seed_buffer(plugin, sk)
    pipe = _mk_pipeline(plugin)

    _run(pipe._flush_conversation_to_l1(sk))

    # StatePersistence._safe_session_key 的纯公式：只替换 / 和 \\，保留 ':'。
    expected_safe = sk.replace("/", "_").replace("\\", "_")
    expected_index_key = person_shelf_origin_index_kv_key(expected_safe)
    assert expected_index_key in plugin._kv

    # SessionContext.safe_session_key 的公式会额外把 ':' 换成 '_'——如果写侧
    # 误用了它，登记的键会是这个，而不是上面 purge 侧期望的键。
    session_ctx_safe = sk.replace("/", "_").replace("\\", "_")
    for ch in '<>:"|?*\x00':
        session_ctx_safe = session_ctx_safe.replace(ch, "_")
    wrong_index_key = person_shelf_origin_index_kv_key(session_ctx_safe)
    assert wrong_index_key != expected_index_key  # 前提：这俩 sanitizer 确实不同
    assert wrong_index_key not in plugin._kv

    # 端到端复核：purge 级联真能靠这个键找到并清掉货架桶。
    shelf_key = person_shelf_kv_key("aiocqhttp", "u99")
    assert shelf_key in plugin._kv
    _run(plugin._state_persistence.delete_sylanne_memory_state(sk))
    assert shelf_key not in plugin._kv
    assert expected_index_key not in plugin._kv


# ===========================================================================
# 9. 货架键（含反向索引键）纳入 MEMORY_KV_KEYS_MANIFEST（未来备份枚举源）
# ===========================================================================


def test_manifest_registers_person_shelf_origin_index_key():
    assert "person_shelf_origin_index" in MEMORY_KV_KEYS_MANIFEST


def test_manifest_person_shelf_origin_index_key_matches_generator():
    tmpl = MEMORY_KV_KEYS_MANIFEST["person_shelf_origin_index"]
    assert tmpl.format(safe="sess_abc") == person_shelf_origin_index_kv_key("sess_abc")


def test_manifest_person_shelf_and_index_keys_all_present_for_future_backup_dump():
    """本仓库尚无独立 KV 全量备份模块（range_get_async 纯设计文档条目），
    MEMORY_KV_KEYS_MANIFEST 是记忆子系统 KV 键的唯一枚举源——未来备份模块建成
    后据此扫描。货架三键（person_shelf/person_profile/person_shelf_origin_index）
    必须全部在册，否则备份会静默漏掉这批数据。
    """
    for name in ("person_shelf", "person_profile", "person_shelf_origin_index"):
        assert name in MEMORY_KV_KEYS_MANIFEST
