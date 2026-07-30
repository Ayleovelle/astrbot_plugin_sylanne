"""v3 Task 13：灰测隔离证明——默认关逐字节相同 + 七隔离计数器恒零。

design 16.1（Hard Isolation Counters，七个必须恒零）+ plan Task 13 RED：

- shadow-disabled 与 shadow-enabled 两次运行，v2 的 reply / prompt / history /
  memory / body snapshot **逐字节相同**，tool / LLM 调用计数相同。
- 注入队列满、只读仓库、锁超时、core 异常、executor 超时、重复钩子六类故障，
  七个隔离计数器全零且 v2 照常完成。
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any
from unittest.mock import patch

import main as main_mod
from sylanne_alpha.scope_identity import ScopeResolver
from sylanne_alpha.v3bridge._state_repository import FaultPoint
from sylanne_alpha.v3bridge.shadow_supervisor import OfferStatus


# --------------------------------------------------------------------------- #
# fakes：可数的 host managers（tool / LLM 调用计数）
# --------------------------------------------------------------------------- #


class CountingContext:
    """记录每一次外部效应：发送、LLM 调用、tool 调用。"""

    def __init__(self) -> None:
        self.provider_manager = None
        self.sent: list[tuple[str, str]] = []
        self.llm_calls = 0
        self.tool_calls = 0

    def get_registered_star(self, *a: Any, **k: Any) -> None:
        return None

    def get_using_provider(self, *a: Any, **k: Any) -> Any:
        self.llm_calls += 1
        return None

    def get_config(self, *a: Any, **k: Any) -> dict:
        return {}

    def register_web_api(self, *a: Any, **k: Any) -> None:
        return None

    async def send_message(self, origin: str, message: Any) -> None:
        self.sent.append((origin, _render(message)))


def _render(message: Any) -> str:
    chain = getattr(message, "chain", None)
    if chain is None:
        return str(message)
    return "".join(str(getattr(seg, "text", "")) for seg in chain)


class CountingEvent:
    def __init__(self, *, origin: str = "qq:GroupMessage:1", message_id: str = "m-1") -> None:
        self.unified_msg_origin = origin
        self.message_str = "hello"
        self._extras: dict[str, Any] = {}
        self.message_obj = type("MO", (), {"message_id": message_id, "self_id": "bot"})()
        self.platform_meta = type("PM", (), {"name": "qq"})()

    def get_extra(self, key: str, default: Any = None) -> Any:
        return self._extras.get(key, default)

    def set_extra(self, key: str, value: Any) -> None:
        self._extras[key] = value

    def get_platform_name(self) -> str:
        return "qq"


SESSION = "qq:GroupMessage:1"
EXPECTED_ISOLATION_COUNTERS = (
    "v3_external_reply_count",
    "v3_prompt_mutation_count",
    "v3_tool_call_count",
    "v3_body_tick_count",
    "v3_v2_memory_write_count",
    "v3_astrbot_history_write_count",
    "v3_extra_llm_call_count",
)


def _build_scoped_plugin(*, fixture_root: Path) -> Any:
    """Build the normal production-shaped plugin with its scoped registry."""

    return main_mod.EmotionalStatePlugin(
        CountingContext(),
        {"sylanne_alpha_root": str(fixture_root / "plugin-data")},
    )


async def _build_legacy_plugin(*, scope_root: Path) -> Any:
    """Keep the registry but replace only the bound facade under legacy tests."""

    plugin = _build_scoped_plugin(fixture_root=scope_root)
    try:
        registry = plugin._scope_runtime_registry
        resolver = ScopeResolver.for_test(None, root=scope_root)
        plugin._scope_resolver_v1 = resolver
        assert plugin._scope_resolver_instance() is resolver
        assert registry.repository is resolver._repository
        resolved = await resolver.resolve_test_values(
            platform_id="qq",
            self_id="bot",
            umo=SESSION,
            persona_id="v3-grey-fixture",
        )
        assert resolved.private_scope_enabled is True
        assert resolved.scope is not None
        plugin._v3_test_runtime_view = registry.issue_request_view(
            resolved,
            subject=None,
            relation_runtime=None,
        )
        plugin._v3_shadow = main_mod._V3ShadowFacade()
        assert plugin._scope_runtime_registry is registry
        assert plugin._v3_shadow._plugin is None
        return plugin
    except BaseException:
        await plugin.terminate()
        raise


def _bind_legacy_v2_scope(plugin: Any) -> Any:
    return plugin._bind_request_runtime_view(plugin._v3_test_runtime_view)


def _private_key(plugin: Any) -> str:
    scope = plugin._v3_test_runtime_view.resolved.scope
    assert scope is not None
    return scope.storage_token


def test_legacy_fixture_uses_production_scope_capability(tmp_path: Path) -> None:
    async def go() -> None:
        plugin = await _build_legacy_plugin(scope_root=tmp_path / "scope")
        try:
            resolver = plugin._scope_resolver_v1
            registry = plugin._scope_runtime_registry
            view = plugin._v3_test_runtime_view

            assert Path(plugin.config["sylanne_alpha_root"]) == tmp_path / "scope" / "plugin-data"
            assert plugin._scope_resolver_instance() is resolver
            assert registry.repository is resolver._repository
            assert registry.is_issued_request_view(view)
            with _bind_legacy_v2_scope(plugin):
                assert plugin._bound_runtime().scope is view.resolved.scope
        finally:
            await plugin.terminate()

    asyncio.run(go())

# --------------------------------------------------------------------------- #
# v2 可观测面：一次真实 v2 分段回复走完之后的全部对外事实
# --------------------------------------------------------------------------- #


def _v2_observable(plugin: Any) -> bytes:
    """把 v2 的 reply / prompt / history / memory / body 快照序列化成确定性字节。"""

    with _bind_legacy_v2_scope(plugin):
        store = plugin._store
        storage_token = _private_key(plugin)
        snapshot = {
            "reply_sent": plugin.context.sent,
            "llm_calls": plugin.context.llm_calls,
            "tool_calls": plugin.context.tool_calls,
            "unfinished_replies": sorted(
                _private_items(store.unfinished_replies, storage_token)
            ),
            "conversation_buffers": sorted(
                _private_items(store.conversation_buffers, storage_token)
            ),
            "last_bot_texts": sorted(
                _private_items(store.last_bot_texts, storage_token)
            ),
            "last_injected_states": sorted(
                _private_items(store.last_injected_states, storage_token)
            ),
            "cached_system_prompts": sorted(
                _private_items(
                    getattr(plugin, "_cached_system_prompts", {}),
                    storage_token,
                )
            ),
            "body": _body_snapshot(plugin),
        }
    return json.dumps(snapshot, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")


def _bounded_items(bounded: Any) -> list[tuple[str, str]]:
    for attribute in ("items", "_data", "_store"):
        candidate = getattr(bounded, attribute, None)
        if callable(candidate):
            try:
                return [(str(k), str(v)) for k, v in candidate()]
            except Exception:
                continue
        if isinstance(candidate, dict):
            return [(str(k), str(v)) for k, v in candidate.items()]
    return []


def _private_items(bounded: Any, storage_token: str) -> list[tuple[str, str]]:
    items = _bounded_items(bounded)
    assert all(key == storage_token for key, _value in items), (
        "active private state must be keyed only by the resolved scope storage_token"
    )
    return [("<storage_token>", value) for _key, value in items]


def _body_snapshot(plugin: Any) -> dict[str, Any]:
    try:
        host = plugin._host(_private_key(plugin))
        observed = host.kernel.computation.engine.observe()
    except Exception:
        return {}
    if not isinstance(observed, dict):
        return {}
    return {str(k): round(float(v), 12) for k, v in observed.items() if isinstance(v, (int, float))}


def _seed_v2_state(plugin: Any) -> None:
    """先把 v2 的各张表塞进真值，_v2_observable 的比较才不是在比两个空 dict。

    `_dispatch_segmented_parts` 自己只会动 unfinished_replies；不预置的话
    conversation_buffers / last_bot_texts / last_injected_states 两边恒空，
    那几路"逐字节相同"就是空证。预置之后：unfinished_replies 会被这一轮真实
    改写（逐段更新剩余、发完清除），其余几张表则钉住"v3 没去碰它们"。
    """

    session_key = _private_key(plugin)
    store = plugin._store
    store.unfinished_replies.set(session_key, "上一轮没发完的残句")
    store.conversation_buffers.set(session_key, [{"role": "user", "content": "早"}])
    store.last_bot_texts.set(session_key, "上一句她说的话")
    store.last_injected_states.set(session_key, {"warmth": 0.5, "tension": 0.2})
    plugin._cached_system_prompts[session_key] = "PERSONA-CACHED"


async def _run_v2_turn(plugin: Any) -> None:
    """跑一次真实 v2 分段发送 + 一次终端结算。"""

    with _bind_legacy_v2_scope(plugin):
        _seed_v2_state(plugin)
        parts = [
            {"text": "第一段", "delay_before_seconds": 0},
            {"text": "第二段", "delay_before_seconds": 0},
        ]
        await plugin._llm_response_pipeline._dispatch_segmented_parts(
            SESSION,
            parts,
            session_key=_private_key(plugin),
        )


async def _capture(plugin: Any, message_id: str = "m-1") -> None:
    plugin._v3_shadow.capture_request(
        session_key=_private_key(plugin),
        platform_id="qq",
        unified_msg_origin=SESSION,
        message_id=message_id,
        text_length=5,
        history_present=True,
        gap_seconds=2.0,
        body={"warmth": 0.5, "tension": 0.2},
    )


# --------------------------------------------------------------------------- #
# 1. 默认关 / 开启：v2 逐字节相同
# --------------------------------------------------------------------------- #


async def _observable_with_shadow(
    *,
    enabled: bool,
    root: Path | None,
    scope_root: Path,
) -> bytes:
    plugin = await _build_legacy_plugin(scope_root=scope_root)
    try:
        facade = plugin._v3_shadow
        facade.enabled = enabled
        if enabled:
            assert root is not None
            assert await facade.initialize(root=root) is True
            await _capture(plugin)
        await _run_v2_turn(plugin)
        return _v2_observable(plugin)
    finally:
        await plugin.terminate()


def test_v2_observable_actually_carries_every_channel(tmp_path: Path) -> None:
    """反空证闸：五路通道都必须真有内容，否则上面的"逐字节相同"是在比两个空表。

    这条是给未来的人设的：哪天有人改了 store 的读法/字段名让某一路悄悄读成空，
    这里先红，而不是让 byte-identical 变成永远为真的废断言。
    """

    async def go() -> None:
        plugin = await _build_legacy_plugin(scope_root=tmp_path / "scope")
        try:
            plugin._v3_shadow.enabled = False
            await _run_v2_turn(plugin)
            snapshot = json.loads(_v2_observable(plugin).decode("utf-8"))
            assert snapshot["reply_sent"], "reply 通道为空"
            assert snapshot["body"], "body snapshot 通道为空"
            assert len(snapshot["body"]) >= 10, "body 快照维度太少，不像真快照"
            assert snapshot["conversation_buffers"], "history 通道为空"
            assert snapshot["last_bot_texts"], "reply 历史通道为空"
            assert snapshot["last_injected_states"], "memory/state 通道为空"
            assert snapshot["cached_system_prompts"], "prompt 通道为空"
        finally:
            await plugin.terminate()

    asyncio.run(go())


def test_shadow_disabled_and_enabled_v2_output_is_byte_identical(tmp_path: Path) -> None:
    async def go() -> None:
        disabled = await _observable_with_shadow(
            enabled=False,
            root=None,
            scope_root=tmp_path / "scope-disabled",
        )
        enabled = await _observable_with_shadow(
            enabled=True,
            root=tmp_path / "v3-container" / "repository",
            scope_root=tmp_path / "scope-enabled",
        )
        assert disabled == enabled, (
            "开启 v3 shadow 后 v2 的 reply/prompt/history/memory/body 必须逐字节相同"
        )

    asyncio.run(go())


def test_shadow_disabled_run_is_reproducible(tmp_path: Path) -> None:
    """基线自证：同一构造两次 disabled 运行本身就必须逐字节相同（否则上面的相等无意义）。"""

    async def go() -> None:
        first = await _observable_with_shadow(
            enabled=False,
            root=None,
            scope_root=tmp_path / "scope-first",
        )
        second = await _observable_with_shadow(
            enabled=False,
            root=None,
            scope_root=tmp_path / "scope-second",
        )
        assert first == second

    asyncio.run(go())


def test_shadow_enabled_does_not_change_tool_or_llm_call_counts(tmp_path: Path) -> None:
    async def go() -> None:
        plugin_off = await _build_legacy_plugin(scope_root=tmp_path / "scope-off")
        plugin_on: Any | None = None
        try:
            plugin_off._v3_shadow.enabled = False
            await _run_v2_turn(plugin_off)

            plugin_on = await _build_legacy_plugin(scope_root=tmp_path / "scope-on")
            facade = plugin_on._v3_shadow
            facade.enabled = True
            assert await facade.initialize(
                root=tmp_path / "v3-container" / "repository"
            ) is True
            await _capture(plugin_on)
            await _run_v2_turn(plugin_on)

            assert plugin_on.context.llm_calls == plugin_off.context.llm_calls
            assert plugin_on.context.tool_calls == plugin_off.context.tool_calls
            assert plugin_on.context.sent == plugin_off.context.sent
        finally:
            if plugin_on is not None:
                await plugin_on.terminate()
            await plugin_off.terminate()

    asyncio.run(go())


# --------------------------------------------------------------------------- #
# 2. 七隔离计数器：六类故障注入下全零，v2 照常完成
# --------------------------------------------------------------------------- #


def _assert_all_counters_zero(facade: Any) -> None:
    counters = facade.counters
    assert counters is not None
    snapshot = counters.as_dict()
    assert snapshot == {name: 0 for name in EXPECTED_ISOLATION_COUNTERS}
    assert counters.all_zero(), f"隔离计数器非零：{snapshot}"
    assert counters.total() == 0


async def _v2_completes(plugin: Any) -> None:
    await _run_v2_turn(plugin)
    assert plugin.context.sent == [(SESSION, "第一段"), (SESSION, "第二段")], "v2 必须照常完成"


async def _assert_full_v2_observable(plugin: Any, baseline: bytes) -> None:
    await _v2_completes(plugin)
    assert _v2_observable(plugin) == baseline, (
        "V3 fault must not change reply/prompt/history/memory/body/tool/LLM observables"
    )


async def _prime_v3_session(plugin: Any) -> None:
    from sylanne_alpha.v2core import shadow_snapshot
    from sylanne_alpha.v2core.integration import runtime_for

    facade = plugin._v3_shadow
    scope = plugin._v3_test_runtime_view.resolved.scope
    assert scope is not None
    with _bind_legacy_v2_scope(plugin):
        seed = shadow_snapshot.freeze_seed_snapshot_owned(runtime_for(plugin, scope))

        async def freeze_bound_seed(_plugin: Any, session_key: str) -> Any:
            assert _plugin is plugin
            assert session_key == scope.storage_token
            return seed

        with patch.object(
            shadow_snapshot,
            "freeze_seed_snapshot_fallback",
            freeze_bound_seed,
        ):
            facade.ensure_session(
                plugin=plugin,
                session_key=scope.storage_token,
                platform_id="qq",
                unified_msg_origin=SESSION,
            )
            await facade.join_private_tasks()
    session_ref = facade._identity.session_ref("qq", SESSION, session_generation=0)
    assert session_ref in facade._ready_sessions, "V3 base migration did not complete"


def _runtime_error_records(facade: Any) -> list[Any]:
    records = [
        record
        for record in facade.runtime.telemetry.recent()
        if record.outcome == "DROPPED_RUNTIME_ERROR"
    ]
    assert records, "repository fault never reached the running V3 worker"
    return records


def test_queue_full_keeps_counters_zero_and_v2_completes(tmp_path: Path) -> None:
    async def go() -> None:
        baseline = await _observable_with_shadow(
            enabled=False,
            root=None,
            scope_root=tmp_path / "scope-baseline",
        )
        plugin = await _build_legacy_plugin(scope_root=tmp_path / "scope")
        facade = plugin._v3_shadow
        try:
            facade.enabled = True
            # 队列容量压到 0：每一次 offer 必满。
            assert await facade.initialize(
                root=tmp_path / "v3-container" / "repository",
                supervisor_kwargs={"global_cap": 0},
            )
            await _prime_v3_session(plugin)
            offer_statuses: list[OfferStatus] = []
            original_offer = facade.runtime.offer_response

            def witnessed_offer(**kwargs: Any) -> Any:
                result = original_offer(**kwargs)
                offer_statuses.append(result.status)
                return result

            facade.runtime.offer_response = witnessed_offer
            try:
                for index in range(8):
                    await _capture(plugin, message_id=f"m-{index}")
                    facade.settle(
                        session_key=_private_key(plugin),
                        route_kind="SEGMENTED_TEXT",
                        reply_kind="SPEAK",
                        part_count=2,
                        all_segments_succeeded=True,
                    )
                assert offer_statuses == [OfferStatus.DROPPED_GLOBAL_FULL] * 8
                await _assert_full_v2_observable(plugin, baseline)
                _assert_all_counters_zero(facade)
            finally:
                facade.runtime.offer_response = original_offer
        finally:
            await plugin.terminate()

    asyncio.run(go())


def test_readonly_repository_keeps_counters_zero_and_v2_completes(tmp_path: Path) -> None:
    async def go() -> None:
        baseline = await _observable_with_shadow(
            enabled=False,
            root=None,
            scope_root=tmp_path / "scope-baseline",
        )
        plugin = await _build_legacy_plugin(scope_root=tmp_path / "scope")
        facade = plugin._v3_shadow
        try:
            facade.enabled = True
            assert await facade.initialize(root=tmp_path / "v3-container" / "repository")
            await _prime_v3_session(plugin)

            committer = facade.runtime.committer
            repository = committer.repository
            original_commit = committer.commit_turn
            original_fault_injector = repository._fault_injector
            commit_entered = threading.Event()
            injected_points: list[FaultPoint] = []

            def witnessed_commit(command: Any) -> Any:
                commit_entered.set()
                return original_commit(command)

            def readonly_fault(point: FaultPoint) -> None:
                injected_points.append(point)
                if point is FaultPoint.BEFORE_FLUSH:
                    raise PermissionError("runtime repository is read-only")

            committer.commit_turn = witnessed_commit
            repository._fault_injector = readonly_fault
            try:
                await _capture(plugin)
                facade.settle(
                    session_key=_private_key(plugin),
                    route_kind="SEGMENTED_TEXT",
                    reply_kind="SPEAK",
                    part_count=2,
                    all_segments_succeeded=True,
                )
                await facade.runtime.join()

                assert commit_entered.is_set(), "learned turn never reached commit_turn"
                assert FaultPoint.BEFORE_FLUSH in injected_points
                records = _runtime_error_records(facade)
                assert any(
                    record.profile_selection_reason == "PermissionError" for record in records
                )
            finally:
                committer.commit_turn = original_commit
                repository._fault_injector = original_fault_injector
            await _assert_full_v2_observable(plugin, baseline)
            _assert_all_counters_zero(facade)
        finally:
            await plugin.terminate()

    asyncio.run(go())


def test_lock_timeout_keeps_counters_zero_and_v2_completes(tmp_path: Path) -> None:
    async def go() -> None:
        baseline = await _observable_with_shadow(
            enabled=False,
            root=None,
            scope_root=tmp_path / "scope-baseline",
        )
        plugin = await _build_legacy_plugin(scope_root=tmp_path / "scope")
        facade = plugin._v3_shadow
        try:
            facade.enabled = True
            assert await facade.initialize(root=tmp_path / "v3-container" / "repository")
            await _prime_v3_session(plugin)

            committer = facade.runtime.committer
            repository = committer.repository
            original_lock_timeout_seconds = repository._lock_timeout_seconds
            repository._lock_timeout_seconds = 0.02
            original_commit = committer.commit_turn
            commit_entered = threading.Event()
            lock_acquired = threading.Event()
            release_lock = threading.Event()
            holder_errors: list[BaseException] = []

            def hold_repository_lock() -> None:
                try:
                    if not commit_entered.wait(2.0):
                        raise AssertionError("commit_turn did not start")
                    with repository._repository_lock():
                        lock_acquired.set()
                        release_lock.wait(2.0)
                except BaseException as exc:
                    holder_errors.append(exc)

            def commit_while_locked(command: Any) -> Any:
                commit_entered.set()
                if not lock_acquired.wait(2.0):
                    raise AssertionError("repository lock holder did not acquire")
                return original_commit(command)

            committer.commit_turn = commit_while_locked
            holder = threading.Thread(target=hold_repository_lock)
            holder_started = False
            try:
                holder.start()
                holder_started = True
                await _capture(plugin)
                facade.settle(
                    session_key=_private_key(plugin),
                    route_kind="SEGMENTED_TEXT",
                    reply_kind="SPEAK",
                    part_count=2,
                    all_segments_succeeded=True,
                )
                await asyncio.wait_for(facade.runtime.join(), timeout=1.0)
            finally:
                release_lock.set()
                if holder_started:
                    await asyncio.to_thread(holder.join, 2.0)
                committer.commit_turn = original_commit
                repository._lock_timeout_seconds = original_lock_timeout_seconds

            assert not holder.is_alive()
            assert holder_errors == []
            assert commit_entered.is_set()
            assert lock_acquired.is_set(), "the real repository lock was never held"
            records = _runtime_error_records(facade)
            assert {record.profile_selection_reason for record in records} == {"AlreadyLocked"}
            await _assert_full_v2_observable(plugin, baseline)
            _assert_all_counters_zero(facade)
        finally:
            await plugin.terminate()

    asyncio.run(go())


def test_core_exception_keeps_counters_zero_and_v2_completes(tmp_path: Path) -> None:
    async def go() -> None:
        baseline = await _observable_with_shadow(
            enabled=False,
            root=None,
            scope_root=tmp_path / "scope-baseline",
        )
        plugin = await _build_legacy_plugin(scope_root=tmp_path / "scope")
        facade = plugin._v3_shadow
        try:
            facade.enabled = True
            compute_entered = threading.Event()

            def exploding_compute(invocation: Any) -> Any:
                compute_entered.set()
                raise RuntimeError("core exploded")

            assert await facade.initialize(
                root=tmp_path / "v3-container" / "repository",
                supervisor_kwargs={"compute": exploding_compute},
            )
            await _prime_v3_session(plugin)
            await _capture(plugin)
            facade.settle(
                session_key=_private_key(plugin),
                route_kind="SEGMENTED_TEXT",
                reply_kind="SPEAK",
                part_count=2,
                all_segments_succeeded=True,
            )
            await facade.runtime.join()
            assert compute_entered.is_set(), "exploding core was never invoked"
            assert any(
                record.outcome == "DROPPED_CORE_ERROR"
                for record in facade.runtime.telemetry.recent()
            )
            await _assert_full_v2_observable(plugin, baseline)
            _assert_all_counters_zero(facade)
        finally:
            await plugin.terminate()

    asyncio.run(go())


def test_executor_timeout_keeps_counters_zero_and_v2_completes(tmp_path: Path) -> None:
    async def go() -> None:
        baseline = await _observable_with_shadow(
            enabled=False,
            root=None,
            scope_root=tmp_path / "scope-baseline",
        )
        plugin = await _build_legacy_plugin(scope_root=tmp_path / "scope")
        facade = plugin._v3_shadow
        try:
            facade.enabled = True
            compute_entered = threading.Event()

            def slow_compute(invocation: Any) -> Any:
                import time as _time

                compute_entered.set()
                _time.sleep(0.5)
                raise AssertionError("timed-out core result must never be used")

            assert await facade.initialize(
                root=tmp_path / "v3-container" / "repository",
                supervisor_kwargs={"compute": slow_compute, "job_timeout_s": 0.01},
            )
            await _prime_v3_session(plugin)
            await _capture(plugin)
            facade.settle(
                session_key=_private_key(plugin),
                route_kind="SEGMENTED_TEXT",
                reply_kind="SPEAK",
                part_count=2,
                all_segments_succeeded=True,
            )
            await facade.runtime.join()
            assert compute_entered.is_set(), "slow core was never invoked"
            assert any(
                record.outcome == "TIMEOUT"
                for record in facade.runtime.telemetry.recent()
            )
            await _assert_full_v2_observable(plugin, baseline)
            _assert_all_counters_zero(facade)
        finally:
            await plugin.terminate()

    asyncio.run(go())


def test_duplicate_hooks_keep_counters_zero_and_v2_completes(tmp_path: Path) -> None:
    """重复钩子：同一轮重复 capture + 重复 settle，v3 只认一次，计数器全零。"""

    async def go() -> None:
        baseline = await _observable_with_shadow(
            enabled=False,
            root=None,
            scope_root=tmp_path / "scope-baseline",
        )
        plugin = await _build_legacy_plugin(scope_root=tmp_path / "scope")
        facade = plugin._v3_shadow
        try:
            facade.enabled = True
            assert await facade.initialize(root=tmp_path / "v3-container" / "repository")
            await _prime_v3_session(plugin)
            await _capture(plugin)
            await _capture(plugin)  # 重复 on_llm_request
            for _ in range(3):  # 重复终端回调
                facade.settle(
                    session_key=_private_key(plugin),
                    route_kind="SEGMENTED_TEXT",
                    reply_kind="SPEAK",
                    part_count=2,
                    all_segments_succeeded=True,
                )
            await facade.runtime.join()
            await _assert_full_v2_observable(plugin, baseline)
            assert len(list(facade.settled_actions)) == 1, "重复钩子只能结算一次"
            _assert_all_counters_zero(facade)
        finally:
            await plugin.terminate()

    asyncio.run(go())
